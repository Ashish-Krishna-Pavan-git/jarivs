"""
dedupe.py
Fingerprint-based deduplication. Tracks seen articles in seen.json.
BUG FIXED: mark_as_seen() is now called correctly after processing.
"""

import json
import os
import hashlib

from config import SEEN_FILE


def _load_seen():
    if not os.path.exists(SEEN_FILE):
        return set()
    try:
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()


def _save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def _fingerprint(article):
    base = (article.get("title", "")[:120] + article.get("link", "")).lower()
    fp   = hashlib.md5(base.encode()).hexdigest()
    return fp


def get_new_articles(data):
    """Filter out already-seen articles. Stamps fp on new ones."""
    seen     = _load_seen()
    new_items = []

    for d in data:
        fp = _fingerprint(d)
        if fp not in seen:
            d["fp"] = fp
            new_items.append(d)

    print(f"[DEDUPE] {len(new_items)} new / {len(data) - len(new_items)} skipped")
    return new_items


def mark_as_seen(articles):
    """Call this AFTER processing to prevent reprocessing next cycle."""
    seen = _load_seen()
    added = 0

    for a in articles:
        fp = a.get("fp")
        if fp:
            seen.add(fp)
            added += 1

    _save_seen(seen)
    print(f"[DEDUPE] Marked {added} articles as seen (total: {len(seen)})")


def seen_count():
    return len(_load_seen())
