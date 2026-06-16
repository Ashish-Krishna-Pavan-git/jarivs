"""
dedupe.py
Fingerprint-based deduplication.

OPTIMISATION: seen.json is loaded ONCE per cycle into a module-level cache.
mark_as_seen() updates the in-memory cache only.
flush_seen() writes to disk — called ONCE at end of cycle, not per-article.

This eliminates 440 separate file reads + writes per cycle.
"""

import json
import os
import hashlib

from config import SEEN_FILE

MAX_SEEN = 30_000   # Prune if more than this many fingerprints

# ── In-memory cache (loaded once per cycle) ──
_seen_cache = None


def _load_seen():
    global _seen_cache
    if _seen_cache is not None:
        return _seen_cache
    if not os.path.exists(SEEN_FILE):
        _seen_cache = set()
        return _seen_cache
    try:
        with open(SEEN_FILE) as f:
            _seen_cache = set(json.load(f))
    except Exception:
        _seen_cache = set()
    return _seen_cache


def _save_seen(seen):
    data = list(seen)
    if len(data) > MAX_SEEN:
        data = data[-MAX_SEEN:]
    with open(SEEN_FILE, "w") as f:
        json.dump(data, f)


def _fingerprint(article):
    base = (article.get("title", "")[:120] + article.get("link", "")).lower()
    return hashlib.md5(base.encode()).hexdigest()


def reset_cache():
    """Call at START of each cycle to force fresh load from disk."""
    global _seen_cache
    _seen_cache = None


def get_new_articles(data):
    """Filter out already-seen articles. Stamps fp on new ones."""
    seen = _load_seen()
    new_items = []
    for d in data:
        fp = _fingerprint(d)
        if fp not in seen:
            d["fp"] = fp
            new_items.append(d)
    skipped = len(data) - len(new_items)
    print(f"[DEDUPE] {len(new_items)} new / {skipped} already seen (total seen: {len(seen)})")
    return new_items


def mark_as_seen(articles):
    """Update in-memory cache only. No disk write. Call flush_seen() at end of cycle."""
    seen = _load_seen()
    for a in articles:
        fp = a.get("fp")
        if fp:
            seen.add(fp)


def flush_seen():
    """Write in-memory cache to disk. Call ONCE at end of cycle."""
    global _seen_cache
    if _seen_cache is None:
        return
    _save_seen(_seen_cache)
    print(f"[DEDUPE] Flushed {len(_seen_cache)} fingerprints to disk")


def seen_count():
    return len(_load_seen())
