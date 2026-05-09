"""
runtime_state.py
Lightweight persisted runtime status for scheduler and Telegram /status.
"""

import json
import os
import threading
from datetime import datetime, timezone

from config import RUNTIME_STATE_FILE

_lock = threading.RLock()


def _default_state():
    return {
        "phase": "idle",
        "current_cycle_number": 0,
        "current_cycle_slot": "",
        "current_cycle_date_ist": "",
        "current_item_title": "",
        "queue_total": 0,
        "queue_done": 0,
        "queue_failed": 0,
        "next_cycle_at_ist": "",
        "last_cycle_started_at": "",
        "last_cycle_finished_at": "",
        "last_daily_run_ist": "",
        "updated_at": "",
    }


def load_runtime_state():
    if not os.path.exists(RUNTIME_STATE_FILE):
        return _default_state()
    try:
        with open(RUNTIME_STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _default_state()

    state = _default_state()
    state.update(data if isinstance(data, dict) else {})
    return state


def save_runtime_state(state: dict):
    with _lock:
        payload = _default_state()
        payload.update(state or {})
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(RUNTIME_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)


def update_runtime_state(**kwargs):
    with _lock:
        state = load_runtime_state()
        state.update(kwargs)
        save_runtime_state(state)


def reset_processing_state():
    update_runtime_state(
        phase="idle",
        current_item_title="",
        queue_total=0,
        queue_done=0,
        queue_failed=0,
    )
