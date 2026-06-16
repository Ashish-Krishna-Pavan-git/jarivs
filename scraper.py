"""
scraper.py
Attempts to scrape full article text from URL.
Falls back to RSS summary on any error, paywall, or short content.

Extraction priority:
  1. trafilatura  (best quality, pip install trafilatura)
  2. BeautifulSoup + lxml/html.parser  (wide availability)
  3. Regex-based raw strip  (stdlib-only fallback)
"""

import re
import requests

from config import SCRAPE_TIMEOUT, SCRAPE_MAX_CHARS, RSS_FALLBACK_CHARS

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}

_PAYWALL_SIGNALS = [
    "subscribe to read", "subscription required", "become a member",
    "sign in to read", "login to continue", "premium content",
    "to unlock this article", "this content is for subscribers",
    "create a free account", "register to read", "paywall",
]

_SKIP_DOMAINS = {
    "twitter.com", "x.com", "facebook.com", "instagram.com",
    "tiktok.com", "reddit.com", "youtube.com",
}


# ─────────────────────────────────────────────────────────────
# EXTRACTION HELPERS
# ─────────────────────────────────────────────────────────────

def _extract_trafilatura(raw: bytes) -> str:
    try:
        import trafilatura
        text = trafilatura.extract(
            raw,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        return text or ""
    except ImportError:
        return ""
    except Exception:
        return ""


def _extract_bs4(raw: bytes) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw, "html.parser")

        # Remove noise tags
        for tag in soup(["script", "style", "nav", "footer", "header",
                         "aside", "form", "noscript", "iframe"]):
            tag.decompose()

        # Try to find main article body first
        main = (
            soup.find("article")
            or soup.find("main")
            or soup.find(class_=re.compile(r"article|post|content|body", re.I))
            or soup.find(id=re.compile(r"article|post|content|body", re.I))
            or soup.body
        )
        if main:
            text = main.get_text(separator=" ", strip=True)
        else:
            text = soup.get_text(separator=" ", strip=True)

        return re.sub(r"\s+", " ", text).strip()
    except ImportError:
        return ""
    except Exception:
        return ""


def _extract_regex(raw: bytes) -> str:
    try:
        html = raw.decode("utf-8", errors="ignore")
        html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>",   " ", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        return ""


def _extract_text(raw: bytes) -> str:
    for extractor in (_extract_trafilatura, _extract_bs4, _extract_regex):
        text = extractor(raw)
        if text and len(text) > 200:
            return text
    return ""


def _is_paywall(text: str) -> bool:
    sample = text[:600].lower()
    return any(signal in sample for signal in _PAYWALL_SIGNALS)


def _skip_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lstrip("www.")
        return any(host.endswith(d) for d in _SKIP_DOMAINS)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def scrape_article(article: dict) -> dict:
    """
    Fetch full article text from article["link"].
    Mutates and returns the article dict with:
        content  – full text (or RSS fallback)
        scraped  – True if successfully scraped (not a paywall)
        paywall  – True if paywall detected
    """
    url          = (article.get("link") or "").strip()
    rss_fallback = str(article.get("rss_summary") or "")[:RSS_FALLBACK_CHARS]

    # Default: use RSS content
    article["content"] = rss_fallback
    article["scraped"]  = False
    article["paywall"]  = False

    if not url or _skip_url(url):
        return article

    try:
        r = requests.get(
            url,
            timeout=SCRAPE_TIMEOUT,
            headers=_HEADERS,
            allow_redirects=True,
            stream=False,
        )

        if r.status_code not in (200, 203):
            return article

        text = _extract_text(r.content)

        if not text or len(text) < 150:
            return article

        if _is_paywall(text):
            article["paywall"] = True
            # Keep RSS fallback for paywalled content
            return article

        article["content"] = text[:SCRAPE_MAX_CHARS]
        article["scraped"]  = True

    except requests.exceptions.Timeout:
        pass   # RSS fallback already set
    except requests.exceptions.TooManyRedirects:
        pass
    except requests.exceptions.ConnectionError:
        pass
    except Exception as exc:
        print(f"  [SCRAPER] Unexpected error ({url[:60]}): {exc}")

    return article
