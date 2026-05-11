"""
queue_manager.py
Pure in-memory queue — rebuilt each cycle.
No file I/O per operation = much faster processing of 200-1200 articles.
The queue is ephemeral by design; it only needs to live for one cycle.
"""

import threading
from datetime import datetime

_lock  = threading.Lock()
_queue: list[dict] = []


# ─────────────────────────────────────────────────────────────
# INTERNAL
# ─────────────────────────────────────────────────────────────

def _new_entry(article: dict) -> dict:
    return {
        "id":        article.get("fp", article.get("id", "")),
        "timestamp": datetime.utcnow().isoformat(),
        "status":    "pending",
        "article":   article,
    }


# ─────────────────────────────────────────────────────────────
# PUBLIC API  (thread-safe)
# ─────────────────────────────────────────────────────────────

def add_to_queue(article: dict):
    with _lock:
        _queue.append(_new_entry(article))


def add_batch(articles: list[dict]):
    with _lock:
        for article in articles:
            _queue.append(_new_entry(article))
    print(f"[QUEUE] Added {len(articles)} items (total in queue: {len(_queue)})")


def get_next_item() -> dict | None:
    with _lock:
        for item in _queue:
            if item["status"] == "pending":
                item["status"] = "processing"
                return item
    return None


def get_pending_count() -> int:
    with _lock:
        return sum(1 for i in _queue if i["status"] == "pending")


def mark_done(item_id: str):
    with _lock:
        for item in _queue:
            if item["id"] == item_id:
                item["status"] = "done"
                return


def mark_failed(item_id: str):
    with _lock:
        for item in _queue:
            if item["id"] == item_id:
                item["status"] = "failed"
                return


def reset_stuck():
    """Reset any 'processing' items back to 'pending' (safety net on cycle start)."""
    with _lock:
        reset = 0
        for item in _queue:
            if item["status"] == "processing":
                item["status"] = "pending"
                reset += 1
    if reset:
        print(f"[QUEUE] Reset {reset} stuck items to pending")


def clear_done(keep_failed: bool = True):
    with _lock:
        global _queue
        if keep_failed:
            _queue = [i for i in _queue if i["status"] != "done"]
        else:
            _queue = [i for i in _queue if i["status"] == "pending"]


def clear_all():
    """Wipe the queue completely (call at start of each cycle)."""
    with _lock:
        _queue.clear()


def stats() -> dict:
    with _lock:
        s = {"pending": 0, "processing": 0, "done": 0, "failed": 0, "total": len(_queue)}
        for item in _queue:
            s[item.get("status", "pending")] = s.get(item.get("status", "pending"), 0) + 1
        return s
