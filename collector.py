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

SOURCES = [

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

def collect_all(limit_per_source=40):
    data = []

    for name, url in SOURCES:
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

    print(f"[COLLECT] Total: {len(data)} articles from {len(SOURCES)} sources")
    return data
