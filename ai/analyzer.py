import os
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

MODEL_NAME = "gemini-3.5-flash-lite"

class ArticleScore(BaseModel):
    relevance_score: int = Field(..., description="1-10 integer")
    credibility_score: int = Field(..., description="1-10 integer")
    impact_score: int = Field(..., description="1-10 integer")
    category: str = Field(..., description="Exactly 'AI' or 'SAP'")
    summary: str = Field(..., description="2-3 sentence factual summary in English")
    telekom_relevance: str = Field(..., description="2-3 sentences explaining why this matters specifically to a manager at Deutsche Telekom.")
    key_takeaway: str = Field(..., description="One punchy, highly practical sentence.")
    translated_title: str = Field(..., description="Translate the title to English if it is not in English, otherwise copy the original")
    translated_description: str = Field(..., description="Translate the description to English if it is not in English, otherwise copy the original")


SCORE_PROMPT = """You are a senior enterprise technology and telecom analyst. The reader is a manager working at Deutsche Telekom.
Deutsche Telekom is a leading European telecommunications provider with a strong interest in AI adoption, network automation, digital sovereignty, enterprise software (strategic partnership with SAP, BTP integration), security, and customer experience.

Analyze the following article and return a JSON object containing the scored results.
Your output MUST be a JSON object that strictly adheres to the requested schema.

Scoring guide:
- relevance_score: How relevant is this to a manager at a major telecom provider (Deutsche Telekom)? (1-10)
- credibility_score: How credible is the source/reporting? (10 = Reuters/FT/DW/Official PR, 1 = unknown blog)
- impact_score: How much strategic or operational impact does this technology or event have? (1-10)

Input Article:
{article_json}

IMPORTANT: Extract information verbatim where possible. Do NOT infer or make up facts. Return ONLY a valid JSON object matching the required schema:
{schema_json}"""

EXEC_SUMMARY_PROMPT = """You are a senior technology analyst writing a daily briefing for a Deutsche Telekom manager.

Below are today's top AI and SAP news articles.

Write a concise executive briefing in plain text. It must be exactly 2 sentences long. The first sentence should summarize today's technology landscape (AI/SAP), and the second sentence must be a funny, witty, or humorous remark related to today's news.

Articles:
{articles_text}

Rules: plain text only, no markdown headers, no asterisks, no bold tags."""


API_DISPATCH_LOCK = threading.Lock()
LAST_REQUEST_TIME = 0.0

PRINT_LOCK = threading.Lock()

def t_print(*args, **kwargs):
    """Thread-safe print wrapper."""
    with PRINT_LOCK:
        print(*args, **kwargs)

def _client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=api_key)

def _call_gemini_score(client, prompt: str) -> ArticleScore:
    global LAST_REQUEST_TIME

    config = types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=8192,
        response_mime_type="application/json",
        response_schema=ArticleScore,
    )

    for attempt in range(4):
        try:
            with API_DISPATCH_LOCK:
                now = time.monotonic()
                wake_time = max(now, LAST_REQUEST_TIME + 4.1)
                LAST_REQUEST_TIME = wake_time

            sleep_duration = wake_time - time.monotonic()
            if sleep_duration > 0:
                time.sleep(sleep_duration)

            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=config
            )
            content = (resp.text or "").strip()
            
            # Clean possible markdown wrap just in case
            clean = content.removeprefix('```json').removeprefix('```').removesuffix('```').strip()
            parsed_dict = json.loads(clean)
            
            # Pydantic validation guarantees NO slop
            validated_score = ArticleScore.model_validate(parsed_dict)
            return validated_score

        except ValidationError as ve:
            t_print(f"      [Retry {attempt+1}/4] Gemini failed Pydantic validation: {ve}")
            if attempt == 3:
                raise
            time.sleep(2)
        except Exception as exc:
            err_msg = str(exc)
            t_print(f"      [Retry {attempt+1}/4] Gemini failed: {err_msg}")
            if attempt == 3:
                raise
            
            # Dynamic backoff
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                t_print("      [Retry] 429 Quota Exceeded. Backing off for 15 seconds...")
                time.sleep(15)
            elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                t_print("      [Retry] 503 Service Unavailable. Backing off for 10 seconds...")
                time.sleep(10)
            else:
                time.sleep(5)

    raise Exception("Gemini API failed after 4 attempts.")

def score_article(client, article: dict) -> dict:
    input_json = {
        "title": article.get("title", ""),
        "source": article.get("source", ""),
        "description": (article.get("description", "") or "")[:500],
        "url": article.get("url", "")
    }
    prompt = SCORE_PROMPT.format(
        article_json=json.dumps(input_json, indent=2),
        schema_json=json.dumps(ArticleScore.model_json_schema(), indent=2)
    )
    
    try:
        validated = _call_gemini_score(client, prompt)
        # Update article with validated schema values
        article.update(validated.model_dump())
        article["composite_score"] = (
            validated.relevance_score * validated.credibility_score * validated.impact_score
        )
        article["title"] = validated.translated_title
        article["description"] = validated.translated_description
        article["translated"] = True
        
        # Restore original category if missing or changed, but trust validated category if valid
        orig_cat = article.get("_original_category")
        if orig_cat and validated.category not in ["AI", "SAP"]:
            article["category"] = orig_cat
        
        t_print(f"[Gemini Score] Scored: {article.get('title', '')[:60]}")
    except Exception as exc:
        t_print(f"[Gemini Score] Error scoring article: {exc}")
        article["composite_score"] = 0
        article["telekom_relevance"] = "Failed to parse AI output."

    return article

def score_all(articles: list[dict]) -> list[dict]:
    if not os.environ.get("GEMINI_API_KEY", ""):
        t_print("[Gemini Score] GEMINI_API_KEY not set. Skipping AI scoring.")
        return articles

    client = _client()
    scored_articles = []
    
    for a in articles:
        a["_original_category"] = a.get("category")
    
    t_print(f"[Gemini Score] Scoring {len(articles)} articles individually using Gemini 3.5 Flash-Lite...")

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(score_article, client, a): a for a in articles}
        for future in as_completed(futures):
            scored = future.result()
            scored_articles.append(scored)

    return scored_articles

def generate_executive_summary(articles: list[dict]) -> str:
    if not os.environ.get("GEMINI_API_KEY", ""):
        return "Executive summary not available: GEMINI_API_KEY is not set."
    client = _client()
    articles_text = "\n".join(
        f"- [{a.get('category', 'AI')}] {a.get('title', '')} | {a.get('telekom_relevance', '')[:200]}"
        for a in articles
    )
    prompt = EXEC_SUMMARY_PROMPT.format(articles_text=articles_text)
    try:
        # Standard completion, no JSON needed
        config = types.GenerateContentConfig(
            temperature=0.4,
            max_output_tokens=2048
        )
        resp = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=config
        )
        summary = (resp.text or "").strip()
        t_print(f"[Gemini Exec] Executive summary generated ({len(summary)} chars).")
        return summary
    except Exception as exc:
        t_print(f"[Gemini Exec] Error generating executive summary: {exc}")
        return "Executive summary generation failed."
