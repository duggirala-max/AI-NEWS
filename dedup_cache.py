import os
import json
import hashlib
import time

CACHE_FILE = "seen_articles.json"
MAX_AGE_DAYS = 3
MAX_AGE_SECONDS = MAX_AGE_DAYS * 24 * 60 * 60

def _load_cache() -> dict:
    """Load the deduplication cache from seen_articles.json."""
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Cache] Error loading cache: {e}. Starting clean.")
        return {}

def _save_cache(cache: dict) -> None:
    """Save the cache dict to seen_articles.json."""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"[Cache] Error saving cache: {e}")

def get_hash(url: str) -> str:
    """Generate a stable MD5 hash of the URL."""
    return hashlib.md5(url.strip().encode('utf-8')).hexdigest()

def filter_unseen_articles(articles: list[dict]) -> list[dict]:
    """Filter out articles that have already been seen in the last MAX_AGE_DAYS."""
    cache = _load_cache()
    now = time.time()
    
    # Clean up old entries
    cleaned_cache = {url_hash: timestamp for url_hash, timestamp in cache.items() 
                     if now - timestamp < MAX_AGE_SECONDS}
    
    unseen = []
    for a in articles:
        url = a.get("url", "").strip()
        if not url:
            continue
        url_hash = get_hash(url)
        if url_hash in cleaned_cache:
            continue
        unseen.append(a)
        
    _save_cache(cleaned_cache)
    return unseen

def add_seen_articles(articles: list[dict]) -> None:
    """Mark a list of articles as seen in the cache."""
    if not articles:
        return
    cache = _load_cache()
    now = time.time()
    for a in articles:
        url = a.get("url", "").strip()
        if url:
            url_hash = get_hash(url)
            cache[url_hash] = now
    _save_cache(cache)
