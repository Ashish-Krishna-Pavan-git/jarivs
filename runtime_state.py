"""
runtime_state.py
Lightweight runtime state — phase, queue progress, current item, cycle info.
Written to RUNTIME_STATE_FILE on every update so /status can read it in real time.
Thread-safe via a module-level lock.

FIX: RUNTIME_STATE_FILE is now defined in config.py (was missing — caused ImportError).
FIX: Default state includes last_cycle_started_at + last_cycle_finished_at fields.
"""

import json
import os
import threading
from datetime import datetime, timezone, timedelta

from config import RUNTIME_STATE_FILE

IST   = timezone(timedelta(hours=5, minutes=30))
_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────
# DEFAULT STATE
# ─────────────────────────────────────────────────────────────

def _default() -> dict:
    return {
        "phase":                   "idle",
        "current_cycle_number":    0,
        "current_cycle_slot":      None,
        "next_cycle_at_ist":       None,
        "current_item_title":      "",
        "queue_total":             0,
        "queue_done":              0,
        "queue_failed":            0,
        "last_daily_run_ist":      None,
        "last_cycle_started_at":   "",    # FIX: new field
        "last_cycle_finished_at":  "",    # FIX: new field
        "updated_at":              None,
    }


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def load_runtime_state() -> dict:
    """Read the current state from disk. Returns defaults on any error."""
    if not os.path.exists(RUNTIME_STATE_FILE):
        return _default()
    try:
        with open(RUNTIME_STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        # Back-fill any keys added in later versions
        for k, v in _default().items():
            data.setdefault(k, v)
        return data
    except Exception:
        return _default()


def update_runtime_state(**kwargs):
    """
    Merge kwargs into the persisted state.
    Adds an 'updated_at' IST timestamp automatically.
    """
    with _lock:
        state = load_runtime_state()
        state.update(kwargs)
        state["updated_at"] = datetime.now(IST).isoformat()
        try:
            with open(RUNTIME_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[RUNTIME_STATE] Write error: {e}")
