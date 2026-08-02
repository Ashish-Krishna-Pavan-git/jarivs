"""
telemetry.py — Runtime statistics tracker.
FIXED: Removed broken _load.__wrapped__() self-reference.
"""

import json
import os
from datetime import datetime, timezone

from config import TELEMETRY_FILE


def _default() -> dict:
    return {
        "total_processed": 0,
        "total_failed":    0,
        "total_scraped":   0,
        "cycles_run":      0,
        "by_severity":     {
            "CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "MINIMAL": 0
        },
        "last_cycle_at":   None,
        "last_update":     None,
    }


def _load() -> dict:
    if not os.path.exists(TELEMETRY_FILE):
        return _default()
    try:
        with open(TELEMETRY_FILE) as f:
            data = json.load(f)
        # Ensure all keys exist (handles old files with missing fields)
        defaults = _default()
        for k, v in defaults.items():
            if k not in data:
                data[k] = v
        return data
    except Exception:
        return _default()


def _save(data: dict):
    with open(TELEMETRY_FILE, "w") as f:
        json.dump(data, f, indent=2)


def update(event: str, severity: str = None):
    data = _load()

    if event == "processed":
        data["total_processed"] += 1
        if severity and severity in data["by_severity"]:
            data["by_severity"][severity] += 1

    elif event == "failed":
        data["total_failed"] += 1

    elif event == "scraped":
        data["total_scraped"] += 1

    elif event == "cycle_start":
        data["cycles_run"]   += 1
        data["last_cycle_at"] = datetime.now(timezone.utc).isoformat()

    data["last_update"] = datetime.now(timezone.utc).isoformat()
    _save(data)


def get_stats() -> dict:
    return _load()


def reset_telemetry() -> dict:
    data = _default()
    _save(data)
    return data


def print_stats():
    d = _load()
    print("\n[TELEMETRY]")
    print(f"  Processed  : {d.get('total_processed', 0)}")
    print(f"  Failed     : {d.get('total_failed', 0)}")
    print(f"  Scraped    : {d.get('total_scraped', 0)}")
    print(f"  Cycles     : {d.get('cycles_run', 0)}")
    print(f"  By Severity: {d.get('by_severity', {})}")
    print(f"  Last cycle : {d.get('last_cycle_at', 'never')}\n")
