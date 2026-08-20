import os
import json
import time
import uuid
import threading
from google import genai
from google.genai import types

MODEL_NAME = "gemini-3.6-flash"

BATCH_SCORE_PROMPT = """You are a senior enterprise technology and telecom analyst. The reader is a manager working at Deutsche Telekom.
Deutsche Telekom is a leading European telecommunications provider with a strong interest in AI adoption, network automation, digital sovereignty, enterprise software (strategic partnership with SAP, BTP integration), security, and customer experience.

I will provide you with a JSON list of news articles. Analyze EACH article and return a JSON object containing the scored results.
Your output MUST be a JSON object with a single key "articles", which contains a list of objects in the EXACT same order as the input articles.

For each article, return these exact keys:
{{
  "id": "<copy the id from the input>",
  "relevance_score": <integer 1-10>,
  "credibility_score": <integer 1-10>,
  "impact_score": <integer 1-10>,
  "category": "<Must be exactly 'AI' or 'SAP'>",
  "summary": "<2-3 sentence factual summary in English>",
  "telekom_relevance": "<2-3 sentences explaining why this matters specifically to a manager at Deutsche Telekom. Connect it to network ops, BTP/SAP partnership, cloud infrastructure, T-Systems, security, or enterprise services.>",
  "key_takeaway": "<One punchy, highly practical sentence that this manager could quote in an executive meeting.>",
  "translated_title": "<Translate the title to English if it is not in English, otherwise copy the original>",
  "translated_description": "<Translate the description to English if it is not in English, otherwise copy the original>"
}}

Scoring guide:
- relevance_score: How relevant is this to a manager at a major telecom provider (Deutsche Telekom)?
- credibility_score: How credible is the source/reporting? (10 = Reuters/FT/DW/Official PR, 1 = unknown blog)
- impact_score: How much strategic or operational impact does this technology or event have?

Input Articles:
{articles_json}

IMPORTANT: Return ONLY a valid JSON object with the "articles" list. Ensure strictly valid JSON."""

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

def _call_gemini(client, prompt, response_format=None, max_tokens=8192, temperature=0.2, parse_json=False):
    global LAST_REQUEST_TIME

    config_kwargs = {
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    if response_format and response_format.get("type") == "json_object":
        config_kwargs["response_mime_type"] = "application/json"
        
    config = types.GenerateContentConfig(**config_kwargs)

    for attempt in range(4):
        try:
            # Enforce 5 RPM limit (12.1s spacing to be extremely safe)
            # Since we only do ~5 requests total in the whole run, this guarantees no 429s.
            with API_DISPATCH_LOCK:
                now = time.monotonic()
                elapsed = now - LAST_REQUEST_TIME
                if elapsed < 12.1:
                    time.sleep(12.1 - elapsed)
                LAST_REQUEST_TIME = time.monotonic()

            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=config
            )
            content = (resp.text or "").strip()

            if parse_json:
                clean = content.removeprefix('```json').removeprefix('```').removesuffix('```').strip()
                parsed = json.loads(clean)
                if not isinstance(parsed, dict):
                    raise ValueError("Parsed JSON is not a dictionary.")
                return parsed

            return content

        except Exception as exc:
            err_msg = str(exc)
            t_print(f"      [Retry {attempt+1}/4] Gemini failed: {err_msg}")
            if attempt == 3:
                raise
            
            # Dynamic backoff based on error type
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                t_print("      [Retry] 429 Quota Exceeded. Backing off for 65 seconds...")
                time.sleep(65)
            elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                t_print("      [Retry] 503 Service Unavailable. Backing off for 10 seconds...")
                time.sleep(10)
            else:
                time.sleep(5)

    raise Exception("Gemini API failed after 4 attempts.")

def score_all(articles: list[dict]) -> list[dict]:
    if not os.environ.get("GEMINI_API_KEY", ""):
        t_print("[Gemini Score] GEMINI_API_KEY not set. Skipping AI scoring.")
        return articles

    client = _client()
    scored_articles = []
    
    # Assign temporary IDs to match them up later
    for a in articles:
        a["_temp_id"] = str(uuid.uuid4())
        # Preserve original category
        a["_original_category"] = a.get("category")
    
    # Batch size 15 articles per request
    chunk_size = 15
    chunks = [articles[i:i + chunk_size] for i in range(0, len(articles), chunk_size)]
    
    t_print(f"[Gemini Score] Scoring {len(articles)} articles in {len(chunks)} batches...")

    for chunk_idx, chunk in enumerate(chunks):
        t_print(f"[Gemini Score] Processing batch {chunk_idx + 1}/{len(chunks)} ({len(chunk)} articles)...")
        
        # Prepare lightweight JSON for prompt
        input_json = []
        for a in chunk:
            input_json.append({
                "id": a["_temp_id"],
                "title": a.get("title", ""),
                "source": a.get("source", ""),
                "description": (a.get("description", "") or "")[:300],
                "url": a.get("url", "")
            })
            
        prompt = BATCH_SCORE_PROMPT.format(articles_json=json.dumps(input_json, indent=2))
        
        try:
            result = _call_gemini(
                client,
                prompt,
                response_format={"type": "json_object"},
                parse_json=True
            )
            
            returned_list = result.get("articles", [])
            
            # Map back to original articles
            id_to_scores = {str(item.get("id")): item for item in returned_list if isinstance(item, dict)}
            
            for a in chunk:
                scores = id_to_scores.get(str(a["_temp_id"]))
                if scores:
                    a.update(scores)
                    a["composite_score"] = (
                        int(scores.get("relevance_score", 0))
                        * int(scores.get("credibility_score", 0))
                        * int(scores.get("impact_score", 0))
                    )
                    # Use translated text
                    a["title"] = scores.get("translated_title", a.get("title", ""))
                    a["description"] = scores.get("translated_description", a.get("description", ""))
                    a["translated"] = True
                else:
                    # Fallback if ID was missing from AI output
                    a["composite_score"] = 0
                    a["telekom_relevance"] = "Failed to parse AI output."
                    
                # Restore original category
                if a.get("_original_category"):
                    a["category"] = a["_original_category"]
                    
                valid_cats = {"AI", "SAP"}
                if a.get("category") not in valid_cats:
                    a["category"] = "AI"
                    
                scored_articles.append(a)
                t_print(f"[Gemini Score] Scored: {a.get('title', '')[:60]}")
                
        except Exception as exc:
            t_print(f"[Gemini Score] Error scoring batch {chunk_idx + 1}: {exc}")
            # Add back with zero scores
            for a in chunk:
                a["composite_score"] = 0
                scored_articles.append(a)

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
        summary = _call_gemini(
            client,
            prompt,
            response_format=None,
            max_tokens=2048,
            temperature=0.4
        )
        t_print(f"[Gemini Exec] Executive summary generated ({len(summary)} chars).")
        return summary
    except Exception as exc:
        t_print(f"[Gemini Exec] Error generating executive summary: {exc}")
        return "Executive summary generation failed."
