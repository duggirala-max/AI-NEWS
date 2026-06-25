import os
import sys
import datetime
import holidays
from dotenv import load_dotenv

# Load env vars before loading other modules
load_dotenv()

from scrapers import newsapi_scraper, rss_scraper, google_news_scraper
from ai import analyzer
from email_sender import send_digest
import dedup_cache

def _deduplicate(articles: list[dict]) -> list[dict]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique = []
    for a in articles:
        url = a.get("url", "").strip()
        title = a.get("title", "").strip().lower()[:80]
        if url and url in seen_urls:
            continue
        if title and title in seen_titles:
            continue
        if url:
            seen_urls.add(url)
        if title:
            seen_titles.add(title)
        unique.append(a)
    return unique

def run() -> None:
    print("=" * 60)
    print("Telekom AI & SAP News Intelligence Pipeline — Starting")
    print("=" * 60)

    # Only enforce schedule limits if running via a scheduled cron job
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        today = datetime.date.today()

        # Check for German holidays
        de_holidays = holidays.Germany()
        if today in de_holidays:
            print(f"Today ({today}) is a German holiday ({de_holidays.get(today)}). Skipping run.")
            sys.exit(0)

        # Enforce Monday/Thursday schedule (in case of timezone drift)
        # 0 = Monday, 3 = Thursday
        if today.weekday() not in [0, 3]:
            print(f"Today ({today}) is not Monday or Thursday. Skipping run.")
            sys.exit(0)
    else:
        print("Manual trigger detected (or running locally). Bypassing schedule checks.")

    # 1. Collect
    print("\n[Step 1] Collecting articles from all sources...")
    all_articles: list[dict] = []
    all_articles += rss_scraper.fetch_articles()
    all_articles += google_news_scraper.fetch_articles()
    all_articles += newsapi_scraper.fetch_articles()
    print(f"\nTotal collected (before run deduplication): {len(all_articles)}")

    # 2. Deduplicate within run
    print("\n[Step 2] Deduplicating within current run...")
    unique_articles = _deduplicate(all_articles)
    print(f"After run dedup: {len(unique_articles)} articles")

    # 3. Cross-day deduplication
    print("\n[Step 2.5] Filtering previously seen articles (cross-day cache)...")
    unseen_articles = dedup_cache.filter_unseen_articles(unique_articles)
    print(f"After cross-day filter: {len(unseen_articles)} articles")

    if not unseen_articles:
        print("No new articles found. Exiting.")
        return

    # Cap raw articles to analyze (e.g. 50 maximum) to conserve API tokens
    MAX_TO_SCORE = 50
    if len(unseen_articles) > MAX_TO_SCORE:
        print(f"Capping to {MAX_TO_SCORE} articles before scoring (was {len(unseen_articles)}).")
        # Split by category to ensure we don't starve SAP (which are appended last)
        ai_unseen = [a for a in unseen_articles if a.get("category") == "AI"]
        sap_unseen = [a for a in unseen_articles if a.get("category") == "SAP"]
        
        # Take up to 35 AI and up to 15 SAP
        unseen_articles = ai_unseen[:35] + sap_unseen[:15]

    # 4. Score
    print(f"\n[Step 3] Scoring {len(unseen_articles)} articles with Groq AI...")
    scored_articles = analyzer.score_all(unseen_articles)

    # 5. Rank and split: Top 7 AI + Top 3 SAP
    print("\n[Step 4] Ranking and partitioning by category...")
    ai_scored = [a for a in scored_articles if a.get("category") == "AI"]
    sap_scored = [a for a in scored_articles if a.get("category") == "SAP"]

    ai_sorted = sorted(ai_scored, key=lambda x: x.get("composite_score", 0), reverse=True)
    sap_sorted = sorted(sap_scored, key=lambda x: x.get("composite_score", 0), reverse=True)

    top_ai = ai_sorted[:7]
    top_sap = sap_sorted[:3]
    top_articles = top_ai + top_sap

    if not top_articles:
        print("No articles met scoring requirements. Exiting.")
        return

    print(f"\nSelected {len(top_articles)} articles for digest:")
    print("🤖 AI Section:")
    for i, a in enumerate(top_ai, 1):
        print(f"  {i}. [{a.get('composite_score',0):>4}] {a.get('title','')[:70]}")
    print("💼 SAP Section:")
    for i, a in enumerate(top_sap, 1):
        print(f"  {i}. [{a.get('composite_score',0):>4}] {a.get('title','')[:70]}")

    # 6. Executive summary
    print("\n[Step 5] Generating executive summary...")
    executive_summary = analyzer.generate_executive_summary(top_articles)
    if executive_summary:
        print("\nExecutive Summary:\n" + executive_summary)

    # 7. Send
    print("\n[Step 6] Sending email digest with PDF attachment...")
    try:
        send_digest(top_articles, executive_summary)
        # Mark only the sent articles as seen so we don't repeat them
        dedup_cache.add_seen_articles(top_articles)
    except Exception as exc:
        print(f"[Email] Failed to send digest: {exc}")
        raise

    print("\n[Done] Pipeline completed successfully.")

if __name__ == "__main__":
    run()
