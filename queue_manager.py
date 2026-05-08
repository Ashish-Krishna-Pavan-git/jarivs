"""
queue_manager.py
Persistent JSON queue with atomic writes.
"""

import json
import os
from datetime import datetime

from config import QUEUE_FILE


def _load():
    if not os.path.exists(QUEUE_FILE):
        return []
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def _save(queue):
    tmp = QUEUE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)
    os.replace(tmp, QUEUE_FILE)


def add_to_queue(article):
    queue = _load()
    queue.append({
        "id":        article.get("fp", article.get("id", "")),
        "timestamp": datetime.utcnow().isoformat(),
        "status":    "pending",
        "article":   article,
    })
    _save(queue)


def add_batch(articles):
    queue = _load()
    for article in articles:
        queue.append({
            "id":        article.get("fp", article.get("id", "")),
            "timestamp": datetime.utcnow().isoformat(),
            "status":    "pending",
            "article":   article,
        })
    _save(queue)
    print(f"[QUEUE] Added {len(articles)} items (total: {len(queue)})")


def get_next_item():
    queue = _load()
    for item in queue:
        if item["status"] == "pending":
            item["status"] = "processing"
            _save(queue)
            return item
    return None


def get_pending_count():
    return sum(1 for i in _load() if i["status"] == "pending")


def mark_done(item_id):
    queue = _load()
    for item in queue:
        if item["id"] == item_id:
            item["status"] = "done"
    _save(queue)


def mark_failed(item_id):
    queue = _load()
    for item in queue:
        if item["id"] == item_id:
            item["status"] = "failed"
    _save(queue)


def reset_stuck():
    """Reset 'processing' items back to 'pending' on restart."""
    queue = _load()
    reset = 0
    for item in queue:
        if item["status"] == "processing":
            item["status"] = "pending"
            reset += 1
    if reset:
        _save(queue)
        print(f"[QUEUE] Reset {reset} stuck items to pending")


def clear_done(keep_failed=True):
    """Remove completed items to keep queue file small."""
    queue = _load()
    if keep_failed:
        queue = [i for i in queue if i["status"] != "done"]
    else:
        queue = [i for i in queue if i["status"] == "pending"]
    _save(queue)


def stats():
    queue = _load()
    s = {"pending": 0, "processing": 0, "done": 0, "failed": 0}
    for item in queue:
        s[item.get("status", "pending")] += 1
    return s
