#!/usr/bin/env python3
"""
scripts/start_backend.py
Helper entry point to start the JARVIS backend server.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import main

if __name__ == "__main__":
    main()
