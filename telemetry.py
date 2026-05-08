"""
telemetry.py — Runtime statistics tracker.
"""

import json
import os
from datetime import datetime

from config import TELEMETRY_FILE


def _load():
    if not os.path.exists(TELEMETRY_FILE):
        return {
            "total_processed": 0,
            "total_failed":    0,
            "total_scraped":   0,
            "cycles_run":      0,
            "by_severity":     {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "MINIMAL": 0},
            "last_cycle_at":   None,
            "last_update":     None,
        }
    try:
        with open(TELEMETRY_FILE, "r") as f:
            return json.load(f)
    except:
        return _load.__wrapped__() if hasattr(_load, "__wrapped__") else {}


def _save(data):
    with open(TELEMETRY_FILE, "w") as f:
        json.dump(data, f, indent=2)


def update(event, severity=None):
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
        data["cycles_run"]    += 1
        data["last_cycle_at"]  = datetime.utcnow().isoformat()
    data["last_update"] = datetime.utcnow().isoformat()
    _save(data)


def get_stats():
    return _load()


def print_stats():
    d = _load()
    print("\n[TELEMETRY]")
    print(f"  Processed : {d.get('total_processed', 0)}")
    print(f"  Failed    : {d.get('total_failed', 0)}")
    print(f"  Scraped   : {d.get('total_scraped', 0)}")
    print(f"  Cycles    : {d.get('cycles_run', 0)}")
    print(f"  By Severity: {d.get('by_severity', {})}")
    print(f"  Last cycle: {d.get('last_cycle_at', 'never')}\n")
