"""
scraper.py
Fetches full article content from URLs.
Detects paywalls, falls back to RSS summary if blocked.
"""

import re
import requests
from config import SCRAPE_TIMEOUT, SCRAPE_MAX_CHARS, RSS_FALLBACK_CHARS

try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False
    print("[WARN] beautifulsoup4 not installed — using fallback text extraction")


# ─────────────────────────────────────────────────────────────
# PAYWALL SIGNATURES
# ─────────────────────────────────────────────────────────────

PAYWALL_DOMAINS = {
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "nytimes.com",
    "washingtonpost.com",
    "economist.com",
    "businessinsider.com",
    "thetimes.co.uk",
}

PAYWALL_MARKERS = [
    "subscribe to read",
    "subscribe to continue",
    "create a free account",
    "sign in to read",
    "premium content",
    "this article is for subscribers",
    "already a subscriber",
    "paywall",
    "members only",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def is_paywalled_domain(url):
    for domain in PAYWALL_DOMAINS:
        if domain in url:
            return True
    return False


def has_paywall_marker(text):
    lower = text.lower()
    for marker in PAYWALL_MARKERS:
        if marker in lower:
            return True
    return False


def extract_text_bs4(html):
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise
    for tag in soup(["script", "style", "nav", "footer",
                     "header", "aside", "form", "iframe",
                     "noscript", "meta", "link"]):
        tag.decompose()

    # Try article body first
    for selector in [
        "article", "main",
        '[class*="article-body"]',
        '[class*="post-content"]',
        '[class*="entry-content"]',
        '[class*="story-body"]',
        '[class*="article__body"]',
        '[itemprop="articleBody"]',
    ]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 200:
                return text

    # Fallback: full body text
    return soup.get_text(separator=" ", strip=True)


def extract_text_simple(html):
    # Strip tags with regex if bs4 unavailable
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_text(text, limit):
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


# ─────────────────────────────────────────────────────────────
# MAIN SCRAPER
# ─────────────────────────────────────────────────────────────

def scrape_article(article):
    """
    Returns article dict with 'content' field populated.
    Falls back to rss_summary if scraping fails/paywalled.
    """

    url     = article.get("link", "")
    fallback = clean_text(
        article.get("rss_summary", ""),
        RSS_FALLBACK_CHARS
    )

    if not url:
        article["content"] = fallback
        article["scraped"] = False
        return article

    if is_paywalled_domain(url):
        print(f"  [SCRAPE] Paywall domain — using RSS: {url[:60]}")
        article["content"] = fallback
        article["scraped"] = False
        article["paywall"] = True
        return article

    try:
        resp = requests.get(
            url,
            headers=HEADERS,
            timeout=SCRAPE_TIMEOUT,
            allow_redirects=True
        )

        if resp.status_code != 200:
            article["content"] = fallback
            article["scraped"] = False
            return article

        html = resp.text

        if has_paywall_marker(html):
            print(f"  [SCRAPE] Paywall detected — using RSS: {url[:60]}")
            article["content"] = fallback
            article["scraped"] = False
            article["paywall"] = True
            return article

        if BS4_OK:
            raw = extract_text_bs4(html)
        else:
            raw = extract_text_simple(html)

        content = clean_text(raw, SCRAPE_MAX_CHARS)

        if len(content) < 150:
            # Too little extracted — use RSS
            article["content"] = fallback
            article["scraped"] = False
        else:
            article["content"] = content
            article["scraped"] = True

    except Exception as e:
        print(f"  [SCRAPE] Error for {url[:60]}: {e}")
        article["content"] = fallback
        article["scraped"] = False

    return article


def scrape_batch(articles, delay=1.0):
    """Scrape a list of articles with a small delay between requests."""
    results = []
    total   = len(articles)

    for i, article in enumerate(articles, 1):
        print(f"  [SCRAPE] {i}/{total} — {article['title'][:60]}")
        article = scrape_article(article)
        results.append(article)

        import time
        time.sleep(delay)

    scraped_count = sum(1 for a in results if a.get("scraped"))
    print(f"[SCRAPE] Done: {scraped_count}/{total} full articles, rest from RSS")
    return results
