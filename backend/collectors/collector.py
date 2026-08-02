"""
collector.py
Fetches RSS feeds from 25+ curated sources across
Cybersec, AI, Tech, Phones, Hardware, Newsletters.
"""

import feedparser
import hashlib
import time

# ─────────────────────────────────────────────────────────────
# SOURCES — Curated & verified, no paywalled-only feeds
# ─────────────────────────────────────────────────────────────

FALLBACK_SOURCES = [

    # ── CYBERSECURITY ────────────────────────────────────────
    ("TheHackerNews",     "https://feeds.feedburner.com/TheHackersNews"),
    ("BleepingComputer",  "https://www.bleepingcomputer.com/feed/"),
    ("KrebsOnSecurity",   "https://krebsonsecurity.com/feed/"),
    ("SecurityWeek",      "https://feeds.feedburner.com/securityweek"),
    ("DarkReading",       "https://www.darkreading.com/rss.xml"),
    ("CISAAdvisories",    "https://www.cisa.gov/cybersecurity-advisories/advisories.xml"),
    ("Threatpost",        "https://threatpost.com/feed/"),
    ("RecordedFuture",    "https://therecord.media/feed"),
    ("Sophos",            "https://news.sophos.com/en-us/feed/"),
    ("Schneier",          "https://www.schneier.com/feed/atom/"),

    # ── ARTIFICIAL INTELLIGENCE ──────────────────────────────
    ("MITTechReview",     "https://www.technologyreview.com/feed/"),
    ("VentureBeat_AI",    "https://venturebeat.com/category/ai/feed/"),
    ("AIWeekly",          "https://aiweekly.co/issues.rss"),
    ("TheAIEdge",         "https://newsletter.theaiedge.io/rss"),
    ("ImportAI",          "https://importai.substack.com/feed"),

    # ── TECH / GENERAL ───────────────────────────────────────
    ("ArsTechnica",       "http://feeds.arstechnica.com/arstechnica/index"),
    ("TheVerge",          "https://www.theverge.com/rss/index.xml"),
    ("TechCrunch",        "https://techcrunch.com/feed/"),
    ("Wired",             "https://www.wired.com/feed/rss"),
    ("HackerNews_Top",    "https://hnrss.org/frontpage"),

    # ── PHONES / MOBILE ──────────────────────────────────────
    ("GSMArena",          "https://www.gsmarena.com/rss-news-reviews.php3"),
    ("AndroidAuthority",  "https://www.androidauthority.com/feed/"),
    ("9to5Google",        "https://9to5google.com/feed/"),
    ("GSMArenaReviews",   "https://www.gsmarena.com/rss-reviews.php3"),
    ("PhoneArena",        "https://www.phonearena.com/phones/reviewed"),

    # ── HARDWARE / LAPTOPS ───────────────────────────────────
    ("AnandTech",         "https://www.anandtech.com/rss/"),
    ("TomsHardware",      "https://www.tomshardware.com/feeds/all"),
    ("NotebookCheck",     "https://www.notebookcheck.net/News.267.0.html?feed=rss"),
    ("HardwareTimes",     "https://www.hardwaretimes.com/feed/"),

    # ── NEWSLETTERS / TRENDS ─────────────────────────────────
    ("TLDRNewsletter",    "https://tldr.tech/rss"),
    ("MorningBrew",       "https://www.morningbrew.com/daily/rss"),
    ("Stratechery",       "https://stratechery.com/feed/"),
]

SOURCES = FALLBACK_SOURCES


def get_sources():
    """Return only enabled sources from the database.

    Deleted or disabled sources are never resurrected: an empty DB list means
    "no collection", not "fall back to the hardcoded list". The hardcoded
    fallback list is used only when the database itself is unreachable.
    """
    try:
        from jarvis_db import init_db, list_enabled_sources
        init_db()
        return list_enabled_sources()
    except Exception as exc:
        print(f"[COLLECT] DB source load failed; using fallback sources: {exc}")
        return FALLBACK_SOURCES


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def normalize(text, limit=3000):
    if not text:
        return ""
    text = text.replace("\n", " ").replace("\r", " ").strip()
    return text[:limit]


def make_id(title, link):
    return hashlib.sha256((title + link).encode()).hexdigest()


# ─────────────────────────────────────────────────────────────
# MAIN COLLECTOR
# ─────────────────────────────────────────────────────────────

import urllib.parse

def is_valid_source_url(url: str) -> bool:
    """Validate source configuration before fetching."""
    try:
        parsed = urllib.parse.urlparse(str(url or "").strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def collect_all(limit_per_source=40):
    data = []

    sources = get_sources()
    valid_sources = []
    for item in sources:
        name, url = item[0], item[1]
        if not is_valid_source_url(url):
            print(f"[WARN] Skipping invalid source URL for '{name}': {url}")
            try:
                from jarvis_db import log_event
                log_event("WARN", "collector", f"Invalid source URL skipped: {name}", {"url": url})
            except Exception:
                pass
            continue
        valid_sources.append((name, url))

    for name, url in valid_sources:
        try:
            feed    = feedparser.parse(url)
            entries = feed.entries[:limit_per_source]

            print(f"[COLLECT] {name}: {len(entries)} articles")

            for e in entries:
                title   = normalize(e.get("title", ""), 300)
                link    = e.get("link", "").strip()
                summary = normalize(
                    e.get("summary", "") or e.get("description", "")
                )

                if not title or not link:
                    continue

                data.append({
                    "id":        make_id(title, link),
                    "title":     title,
                    "link":      link,
                    "source":    name,
                    "rss_summary": summary,
                    "content":   "",          # filled by scraper
                    "timestamp": int(time.time()),
                })

        except Exception as e:
            print(f"[WARN] {name} failed: {e}")
            try:
                from jarvis_db import log_event
                log_event("WARN", "collector", f"Fetch failed for {name}", {"url": url, "error": str(e)})
            except Exception:
                pass

    print(f"[COLLECT] Total: {len(data)} articles from {len(valid_sources)} valid sources")
    return data

