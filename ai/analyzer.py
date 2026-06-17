import os
import json
from openai import OpenAI

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.3-70b-versatile"

SCORE_PROMPT = """You are a senior enterprise technology and telecom analyst. The reader is a manager working at Deutsche Telekom.
Deutsche Telekom is a leading European telecommunications provider with a strong interest in AI adoption, network automation, digital sovereignty, enterprise software (strategic partnership with SAP, BTP integration), security, and customer experience.

Analyze the news article below and return ONLY a valid JSON object with these exact keys:
{{
  "relevance_score": 8,
  "credibility_score": 9,
  "impact_score": 7,
  "category": "AI",
  "summary": "<2-3 sentence factual summary in English>",
  "telekom_relevance": "<2-3 sentences explaining why this matters specifically to a manager at Deutsche Telekom. Connect it to network ops, BTP/SAP partnership, cloud infrastructure, T-Systems, security, or enterprise services.>",
  "key_takeaway": "<One punchy, highly practical sentence that this manager could quote in an executive meeting.>"
}}

Replace the example values with your actual scores (integers 1-10) and correct category string.
category MUST be exactly one of: "AI" or "SAP".

Scoring guide:
- relevance_score: How relevant is this to a manager at a major telecom provider (Deutsche Telekom) and its systems?
- credibility_score: How credible is the source/reporting? (10 = Reuters/FT/DW/Official PR, 1 = unknown blog)
- impact_score: How much strategic or operational impact does this technology or event have?

If the article is in a language other than English (e.g. German), translate the title and description to English before analysis.

Article title: {title}
Source: {source}
Description: {description}
URL: {url}

Return ONLY the JSON object, no markdown fences, no explanation."""

EXEC_SUMMARY_PROMPT = """You are a senior technology analyst writing a daily briefing for a Deutsche Telekom manager.

Below are today's top AI and SAP news articles (titles, categories, and Telekom-relevance notes).

Write a concise executive briefing in plain text with exactly this structure:
1. Two sentences summarising today's overall technology/enterprise landscape (specifically AI and SAP developments).
2. Between 3 and 5 bullet points (use "• " prefix). Each bullet names ONE development, its category, and a concise action/insight for a Telekom manager.
3. One final line starting with "TOP INSIGHT: " — the single most critical thing for a Telekom manager to know or act on today.

Articles:
{articles_text}

Rules: plain text only, no markdown headers, no asterisks, no bold tags."""

def _client() -> OpenAI:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set.")
    return OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)

def translate_article(article: dict) -> dict:
    """Translate title and description to English if non-ASCII characters are detected."""
    title = article.get("title", "")
    description = article.get("description", "")
    has_non_ascii = any(ord(c) > 127 for c in title + description)
    if not has_non_ascii:
        return article
    if not os.environ.get("GROQ_API_KEY", ""):
        return article
    try:
        client = _client()
        prompt = (
            "Translate the following news article fields from their original language to English. "
            "Return ONLY a valid JSON object with keys \"title\" and \"description\".\n\n"
            f"title: {title}\ndescription: {description[:300]}"
        )
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content.strip())
        article["title"] = data.get("title", title)
        article["description"] = data.get("description", description)
        article["translated"] = True
        print(f"[Translate] Translated: {article['title'][:60]}")
    except Exception as exc:
        print(f"[Translate] Error translating '{title[:40]}': {exc}")
    return article

def score_article(article: dict) -> dict:
    if not os.environ.get("GROQ_API_KEY", ""):
        # Fallback values if API key is not present
        article.update({
            "relevance_score": 5,
            "credibility_score": 5,
            "impact_score": 5,
            "composite_score": 125,
            "summary": article.get("description", "") or "No description available.",
            "telekom_relevance": "N/A — GROQ_API_KEY not set. Relevance cannot be assessed.",
            "key_takeaway": "N/A — GROQ_API_KEY not set."
        })
        return article

    # Translate first if needed
    article = translate_article(article)

    client = _client()
    prompt = SCORE_PROMPT.format(
        title=article.get("title", ""),
        source=article.get("source", ""),
        description=(article.get("description", "") or "")[:300],
        url=article.get("url", ""),
    )
    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content.strip()
        scores = json.loads(raw)
        article.update(scores)
        
        # Calculate composite score (relevance * credibility * impact)
        article["composite_score"] = (
            int(scores.get("relevance_score", 0))
            * int(scores.get("credibility_score", 0))
            * int(scores.get("impact_score", 0))
        )
        
        # Ensure category is normalized
        valid_cats = {"AI", "SAP"}
        if article.get("category") not in valid_cats:
            article["category"] = article.get("category", "AI")
    except Exception as exc:
        print(f"[Groq Score] Error scoring '{article.get('title', '')}': {exc}")
        # Error fallback
        article.update({
            "relevance_score": 0,
            "credibility_score": 0,
            "impact_score": 0,
            "composite_score": 0,
            "summary": article.get("description", "") or "Error during analysis.",
            "telekom_relevance": "Error evaluating Telekom relevance.",
            "key_takeaway": "Error evaluating key takeaway.",
        })
    return article

def score_all(articles: list[dict]) -> list[dict]:
    scored = []
    for i, article in enumerate(articles):
        print(f"[Groq Score] Scoring {i+1}/{len(articles)}: {article.get('title', '')[:60]}")
        scored.append(score_article(article))
    return scored

def generate_executive_summary(articles: list[dict]) -> str:
    if not os.environ.get("GROQ_API_KEY", ""):
        return "Executive summary not available: GROQ_API_KEY is not set."
    client = _client()
    articles_text = "\n".join(
        f"- [{a.get('category', 'AI')}] {a.get('title', '')} | {a.get('telekom_relevance', '')[:200]}"
        for a in articles
    )
    prompt = EXEC_SUMMARY_PROMPT.format(articles_text=articles_text)
    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        summary = resp.choices[0].message.content.strip()
        print(f"[Groq Exec] Executive summary generated ({len(summary)} chars).")
        return summary
    except Exception as exc:
        print(f"[Groq Exec] Error generating executive summary: {exc}")
        return "Error generating executive briefing."
