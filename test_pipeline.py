"""
test_pipeline.py — 10 tests for the Telekom AI & SAP News Intelligence pipeline.
Run: python3 test_pipeline.py
Must print 10/10 PASSED.
"""
import os
import sys
import time

# Ensure we can import project modules
sys.path.insert(0, os.path.dirname(__file__))

passed = 0
failed = 0

def run_test(name: str, fn):
    global passed, failed
    try:
        fn()
        print(f"  ✓ {name}")
        passed += 1
    except Exception as exc:
        print(f"  ✗ {name}: {exc}")
        import traceback
        traceback.print_exc()
        failed += 1

# ── Test 1: RSS scraper returns articles with category field ─────────────────
def test_rss_category():
    from scrapers.rss_scraper import fetch_articles
    articles = fetch_articles()
    assert len(articles) > 0, "RSS scraper returned 0 articles"
    missing = [a for a in articles if "category" not in a]
    assert len(missing) == 0, f"{len(missing)} articles missing category"

# ── Test 2: AI feeds configuration check ──────────────────────────────────────
def test_ai_feeds_configured():
    from scrapers.rss_scraper import AI_RSS_FEEDS
    assert len(AI_RSS_FEEDS) >= 5, f"Expected >=5 AI feeds configured, found {len(AI_RSS_FEEDS)}"

# ── Test 3: SAP feeds configuration check ─────────────────────────────────────
def test_sap_feeds_configured():
    from scrapers.rss_scraper import SAP_RSS_FEEDS
    assert len(SAP_RSS_FEEDS) >= 2, f"Expected >=2 SAP feeds configured, found {len(SAP_RSS_FEEDS)}"

# ── Test 4: translate_article returns English or unchanged without key ────────
def test_translate_article():
    from ai.analyzer import translate_article
    article = {
        "title": "Künstliche Intelligenz in der Telekommunikation",
        "description": "Wie KI die Netzwerke optimiert.",
        "category": "AI",
    }
    result = translate_article(article)
    assert "title" in result
    assert "description" in result

# ── Test 5: score_article returns key fields ──────────────────────────────────
def test_score_article_fields():
    from ai.analyzer import score_article
    article = {
        "title": "NVIDIA launches new AI chips for enterprise",
        "url": "https://example.com/test-ai-nvidia",
        "source": "Tech Source",
        "description": "NVIDIA announced new Blackwell enterprise chips.",
        "category": "AI",
    }
    result = score_article(article)
    assert "relevance_score" in result, "relevance_score field missing"
    assert "credibility_score" in result, "credibility_score field missing"
    assert "impact_score" in result, "impact_score field missing"
    assert "telekom_relevance" in result, "telekom_relevance field missing"
    assert "key_takeaway" in result, "key_takeaway field missing"

# ── Test 6: category values validation ────────────────────────────────────────
def test_category_valid_values():
    from ai.analyzer import score_article
    article = {
        "title": "SAP BTP updates for Q3 2026",
        "url": "https://example.com/sap-btp-q3",
        "source": "SAP news",
        "description": "SAP releases updates on Business Technology Platform.",
        "category": "SAP",
    }
    result = score_article(article)
    cat = result.get("category", "")
    assert cat in {"AI", "SAP"}, f"Invalid category returned: '{cat}'"

# ── Test 7: PDF generation returns valid bytes ───────────────────────────────
def test_pdf_generation():
    from email_sender import build_pdf
    sample_articles = [
        {
            "title": "AI in Telecom Networks",
            "url": "https://example.com/1",
            "source": "TechCrunch",
            "published_at": "2026-06-17",
            "description": "Test AI article",
            "summary": "AI is changing how telcos run network routing.",
            "relevance_score": 8, "credibility_score": 8, "impact_score": 9,
            "composite_score": 576, "category": "AI",
            "telekom_relevance": "Direct impact on Deutsche Telekom routing efficiencies.",
            "key_takeaway": "Telekom should pilot routing AI immediately.",
        },
        {
            "title": "SAP S/4HANA Cloud release",
            "url": "https://example.com/2",
            "source": "SAP News",
            "published_at": "2026-06-17",
            "description": "Test SAP article",
            "summary": "SAP announced their S/4HANA release.",
            "relevance_score": 7, "credibility_score": 9, "impact_score": 8,
            "composite_score": 504, "category": "SAP",
            "telekom_relevance": "Highly relevant for Telekom ERP systems.",
            "key_takeaway": "Telekom ERP teams should schedule this update.",
        },
    ]
    pdf_bytes = build_pdf(sample_articles, executive_summary="Test briefing.")
    assert isinstance(pdf_bytes, bytes), "PDF output is not bytes"
    assert len(pdf_bytes) > 1000, f"PDF too small: {len(pdf_bytes)} bytes"

# ── Test 8: PDF split logic check ─────────────────────────────────────────────
def test_pdf_sections_split():
    from email_sender import _split_by_category
    sample_articles = [
        {"title": "A", "category": "AI"},
        {"title": "B", "category": "SAP"},
        {"title": "C", "category": "AI"},
    ]
    ai, sap = _split_by_category(sample_articles)
    assert len(ai) == 2, f"Expected 2 AI articles, got {len(ai)}"
    assert len(sap) == 1, f"Expected 1 SAP article, got {len(sap)}"

# ── Test 9: HTML email contains section headers ──────────────────────────────
def test_html_sections():
    from email_sender import _build_html
    sample_articles = [
        {"title": "A", "category": "AI", "relevance_score": 5, "credibility_score": 5, "impact_score": 5, "composite_score": 125},
        {"title": "B", "category": "SAP", "relevance_score": 5, "credibility_score": 5, "impact_score": 5, "composite_score": 125},
    ]
    html = _build_html(sample_articles)
    assert "Top AI Intelligence News" in html, "HTML missing AI section header"
    assert "Top SAP Enterprise News" in html, "HTML missing SAP section header"

# ── Test 10: Deduplication & Cache integration ───────────────────────────────
def test_cache_dedup():
    import dedup_cache
    
    # Save current cache file if it exists so we don't destroy real run history during tests
    cache_existed = os.path.exists(dedup_cache.CACHE_FILE)
    backup_data = None
    if cache_existed:
        try:
            with open(dedup_cache.CACHE_FILE, "r") as f:
                backup_data = f.read()
        except:
            pass
            
    # Clean test run
    if os.path.exists(dedup_cache.CACHE_FILE):
        os.remove(dedup_cache.CACHE_FILE)
        
    try:
        articles = [
            {"url": "https://example.com/unique-1", "title": "First Unique"},
            {"url": "https://example.com/unique-2", "title": "Second Unique"},
        ]
        
        # Initial filter
        filtered = dedup_cache.filter_unseen_articles(articles)
        assert len(filtered) == 2, f"Expected 2 unseen, got {len(filtered)}"
        
        # Add to seen
        dedup_cache.add_seen_articles([articles[0]])
        
        # Second filter
        filtered_again = dedup_cache.filter_unseen_articles(articles)
        assert len(filtered_again) == 1, f"Expected 1 unseen, got {len(filtered_again)}"
        assert filtered_again[0]["url"] == "https://example.com/unique-2"
        
    finally:
        # Restore backup cache
        if cache_existed and backup_data is not None:
            try:
                with open(dedup_cache.CACHE_FILE, "w") as f:
                    f.write(backup_data)
            except:
                pass
        elif os.path.exists(dedup_cache.CACHE_FILE):
            os.remove(dedup_cache.CACHE_FILE)

# ── Run all tests ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n=== Telekom AI & SAP News Intelligence — Test Suite ===\n")
    
    print("[Group 1] Scrapers")
    run_test("RSS returns category field", test_rss_category)
    run_test("AI feeds configured", test_ai_feeds_configured)
    run_test("SAP feeds configured", test_sap_feeds_configured)
    
    print("\n[Group 2] AI Analyzer")
    run_test("translate_article works", test_translate_article)
    run_test("score_article returns key fields", test_score_article_fields)
    run_test("category values validation", test_category_valid_values)
    
    print("\n[Group 3] Email & PDF")
    run_test("PDF generation returns valid bytes", test_pdf_generation)
    run_test("PDF category partition split", test_pdf_sections_split)
    run_test("HTML contains category sections", test_html_sections)
    
    print("\n[Group 4] Cache Deduplication")
    run_test("Deduplication and cache filter flow", test_cache_dedup)
    
    total = passed + failed
    print(f"\n{'='*48}")
    print(f"  Result: {passed}/{total} PASSED  |  {failed} FAILED")
    print(f"{'='*48}\n")
    if failed > 0:
        sys.exit(1)
