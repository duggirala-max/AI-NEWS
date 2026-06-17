import feedparser
import re

AI_RSS_FEEDS = [
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("VentureBeat", "http://feeds.venturebeat.com/VentureBeat"),
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
    ("OpenAI News", "https://openai.com/news/rss.xml"),
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("MarkTechPost", "https://www.marktechpost.com/feed/"),
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
    ("BBC Business", "http://feeds.bbci.co.uk/news/business/rss.xml"),
]

SAP_RSS_FEEDS = [
    ("SAP News Center", "https://news.sap.com/feed"),
    ("ERP News", "https://erpnews.com/feed"),
    ("SAP Community Blogs", "https://community.sap.com/khhcw49343/rss/Community?interaction.style=blog"),
]

AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "llm", "generative ai",
    "deep learning", "neural network", "gpt", "chatbot", "copilot", 
    "foundation model", "agentic", "claud", "gemini", "llama", "nvidia"
]

def _is_ai_relevant(title: str, description: str) -> bool:
    combined = (title + " " + description).lower()
    for kw in AI_KEYWORDS:
        # Match as word boundaries to avoid false positives on words like "said" or "main"
        if re.search(r'\b' + re.escape(kw) + r'\b', combined):
            return True
    return False

def fetch_articles() -> list[dict]:
    seen_urls = set()
    articles = []

    # 1. Fetch AI feeds
    for source_name, feed_url in AI_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                title = entry.get("title", "")
                description = entry.get("summary", "") or entry.get("description", "") or ""
                published = entry.get("published", "") or entry.get("updated", "") or ""

                if not url or url in seen_urls:
                    continue
                
                # For general business feeds, filter strictly. For AI feeds, we can be more lenient but still filter
                # to keep high relevance.
                is_general = "Reuters" in source_name or "BBC" in source_name
                if is_general and not _is_ai_relevant(title, description):
                    continue
                if not is_general and not _is_ai_relevant(title, description) and not any(kw in (title + " " + description).lower() for kw in ["ai", "model", "intelligence"]):
                    continue

                seen_urls.add(url)
                articles.append({
                    "title": title,
                    "url": url,
                    "source": source_name,
                    "category": "AI",
                    "published_at": published,
                    "description": description[:500],
                })
        except Exception as exc:
            print(f"[RSS AI] Error fetching '{source_name}': {exc}")

    # 2. Fetch SAP feeds
    for source_name, feed_url in SAP_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                title = entry.get("title", "")
                description = entry.get("summary", "") or entry.get("description", "") or ""
                published = entry.get("published", "") or entry.get("updated", "") or ""

                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)
                articles.append({
                    "title": title,
                    "url": url,
                    "source": source_name,
                    "category": "SAP",
                    "published_at": published,
                    "description": description[:500],
                })
        except Exception as exc:
            print(f"[RSS SAP] Error fetching '{source_name}': {exc}")

    print(f"[RSS] Fetched {len(articles)} relevant articles (AI/SAP).")
    return articles
