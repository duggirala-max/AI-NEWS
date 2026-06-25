import os
import requests
from datetime import datetime, timedelta

NEWSAPI_ENDPOINT = "https://newsapi.org/v2/everything"

QUERIES = [
    # query, category
    ("generative AI enterprise", "AI"),
    ("artificial intelligence telecom", "AI"),
    ("SAP S/4HANA cloud", "SAP"),
    ("SAP Business Technology Platform", "SAP"),
]

def fetch_articles() -> list[dict]:
    api_key = os.environ.get("NEWSAPI_KEY", "")
    if not api_key:
        print("[NewsAPI] NEWSAPI_KEY not set — skipping.")
        return []

    # Fetch up to 7 days back to cover the gaps between Mon and Thu runs, including weekends/holidays.
    from_date = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    seen_urls = set()
    articles = []

    for query, category in QUERIES:
        params = {
            "q": query,
            "from": from_date,
            "sortBy": "relevancy",
            "language": "en",
            "pageSize": 20,
            "apiKey": api_key,
        }
        try:
            resp = requests.get(NEWSAPI_ENDPOINT, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("articles", []):
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    articles.append({
                        "title": item.get("title", ""),
                        "url": url,
                        "source": item.get("source", {}).get("name", "NewsAPI"),
                        "category": category,
                        "published_at": item.get("publishedAt", ""),
                        "description": item.get("description", "") or "",
                    })
        except Exception as exc:
            print(f"[NewsAPI] Error fetching '{query}': {exc}")

    print(f"[NewsAPI] Fetched {len(articles)} articles.")
    return articles
