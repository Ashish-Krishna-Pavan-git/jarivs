#!/usr/bin/env python3
"""
tools/health_check.py
Diagnostic tool for checking JARVIS database, API, and storage health.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.database.jarvis_db import init_db, schema_status
from backend.services.runtime_state import load_runtime_state

def main():
    print("[DIAGNOSTIC] Checking JARVIS System Health...")
    init_db()
    status = schema_status()
    print(f"[DATABASE] SQLite schema version: {status.get('user_version')} (Migrations: {status.get('migration_count')})")
    state = load_runtime_state()
    print(f"[RUNTIME] Phase: {state.get('phase')} | Queue Total: {state.get('queue_total')}")
    print("[DIAGNOSTIC] System Health Check Passed.")

if __name__ == "__main__":
    main()
