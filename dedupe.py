"""
dedupe.py
Fingerprint-based deduplication backed by seen.json.
Synced to HF Dataset by storage_backend — survives restarts.

CHANGE: Auto-prunes seen.json to last 30,000 entries
so the file doesn't grow forever on a long-running space.
"""

import json
import os
import hashlib

from config import SEEN_FILE

MAX_SEEN = 30_000   # Prune if more than this many fingerprints


# ─────────────────────────────────────────────────────────────
# INTERNAL
# ─────────────────────────────────────────────────────────────

def _load_seen() -> set:
    if not os.path.exists(SEEN_FILE):
        return set()
    try:
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_seen(seen: set):
    data = list(seen)
    # Prune to most recent MAX_SEEN entries (list order = insertion order approximation)
    if len(data) > MAX_SEEN:
        data = data[-MAX_SEEN:]
    with open(SEEN_FILE, "w") as f:
        json.dump(data, f)


def _fingerprint(article: dict) -> str:
    base = (article.get("title", "")[:120] + article.get("link", "")).lower()
    return hashlib.md5(base.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def get_new_articles(data: list) -> list:
    """Filter out already-seen articles. Stamps fp on new ones."""
    seen      = _load_seen()
    new_items = []

    for d in data:
        fp = _fingerprint(d)
        if fp not in seen:
            d["fp"] = fp
            new_items.append(d)

    skipped = len(data) - len(new_items)
    print(f"[DEDUPE] {len(new_items)} new / {skipped} already seen (total seen: {len(seen)})")
    return new_items


def mark_as_seen(articles: list):
    """Mark articles as seen AFTER processing to prevent reprocessing next cycle."""
    seen  = _load_seen()
    added = 0
    for a in articles:
        fp = a.get("fp")
        if fp:
            seen.add(fp)
            added += 1
    _save_seen(seen)
    print(f"[DEDUPE] Marked {added} new articles as seen (total: {len(seen)})")


def seen_count() -> int:
    return len(_load_seen())