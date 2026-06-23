# AI News Pipeline: File Explanations

This document explains what each file in the repository does and exactly *when* it is executed during the pipeline's run. You can use this as a reference or a cheat sheet during your presentation.

## 1. Orchestration

### `main.py`
- **What it does:** This is the core orchestrator (the "brain") of the entire project. It defines the step-by-step pipeline logic: collecting articles, deduplicating them, capping the maximum number sent to AI, triggering the AI scoring, ranking the results, triggering the executive summary, and calling the email sender.
- **When it runs:** This is the entry point. It is executed first (e.g., `python main.py`) and drives the entire process from start to finish.

## 2. Data Collection (Scrapers)

### `scrapers/google_news_scraper.py`
- **What it does:** Connects to Google News to scrape relevant articles based on predefined search queries or topics (like "Telekom", "SAP", "AI").
- **When it runs:** In **Step 1** of `main.py`. The pipeline calls its `fetch_articles()` function to gather a raw list of news articles.

### `scrapers/newsapi_scraper.py`
- **What it does:** Uses the NewsAPI service to pull structured news data via API requests.
- **When it runs:** In **Step 1** of `main.py`, alongside the other scrapers, to enrich the pool of collected articles.

### `scrapers/rss_scraper.py`
- **What it does:** Parses configured RSS feeds (which are standard web feed formats) from selected tech or business news outlets.
- **When it runs:** In **Step 1** of `main.py`.

## 3. Data Processing & Management

### `dedup_cache.py`
- **What it does:** Manages a local cache to prevent the same article from being processed multiple times across different runs. It generates an MD5 hash for each article's URL.
- **When it runs:** 
  - In **Step 2.5** of `main.py`, it filters the newly collected articles against the cache to remove ones we've already seen in the last 3 days.
  - In **Step 6** of `main.py` (at the very end), it updates the cache to save the newly sent articles.

### `seen_articles.json`
- **What it does:** A simple local JSON file used as a lightweight database by `dedup_cache.py`. It stores the URL hashes and timestamps of articles that have already been sent in digests.
- **When it runs:** Read and written to continuously whenever `dedup_cache.py` operates.

## 4. Artificial Intelligence

### `ai/analyzer.py`
- **What it does:** Integrates with the **Groq API** (using the `llama-3.3-70b-versatile` model). It has three main jobs:
  1. Translates non-English articles to English.
  2. Scores every unseen article out of 10 for Relevance, Credibility, and Impact, and provides a "Telekom Relevance" explanation and "Key Takeaway".
  3. Generates a final concise "Executive Summary" based on the top-ranked articles.
- **When it runs:**
  - In **Step 3** of `main.py` to evaluate and score the pool of unseen articles.
  - In **Step 5** of `main.py` to write the overarching briefing text for the email.

## 5. Delivery

### `email_sender.py`
- **What it does:** Handles all formatting and delivery of the final product. It builds a styled HTML email and dynamically generates a beautifully formatted PDF report (using `reportlab`) containing the Telekom-styled (magenta) tables, scores, and takeaways. Finally, it connects to a Gmail SMTP server to send the email with the PDF attached.
- **When it runs:** In **Step 6** of `main.py`, after all articles have been ranked and the executive summary is generated.

## 6. Utilities & Environment

### `requirements.txt`
- **What it does:** Lists all the external Python libraries required to run the pipeline (e.g., `openai`, `reportlab`, `python-dotenv`).
- **When it runs:** Used only during the initial setup/installation (`pip install -r requirements.txt`).

### `.env.example`
- **What it does:** A template showing which secret environment variables are needed (like `GROQ_API_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `RECIPIENT_EMAIL`). Users copy this to a `.env` file to store their actual secrets safely.
- **When it runs:** Loaded by `main.py` right when the script starts using the `dotenv` library.

### `test_pipeline.py`
- **What it does:** A testing script designed to run the pipeline components (likely with mocked data or safe endpoints) to verify that the logic works without actually sending emails to executives.
- **When it runs:** Run manually by a developer when making changes or verifying the setup.
