"""
config.py
Centralised configuration.
/tmp/jarvis/data/ is used for all runtime data — writable on HF Spaces.
State files (seen.json, digest_state.json, telemetry.json) are synced
to HF Dataset by storage_backend.py so they survive restarts.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# PLATFORM DETECTION
# ─────────────────────────────────────────────────────────────

IS_WINDOWS = sys.platform == "win32"
IS_TERMUX  = "com.termux" in os.environ.get("PREFIX", "")
IS_HF      = os.path.exists("/usr/local/lib/python3.10")  # HF Spaces indicator
PLATFORM   = "windows" if IS_WINDOWS else ("termux" if IS_TERMUX else "linux")

# ─────────────────────────────────────────────────────────────
# AI API KEYS
# ─────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")

# ─────────────────────────────────────────────────────────────
# HUGGING FACE PERSISTENCE
# ─────────────────────────────────────────────────────────────

HF_TOKEN        = os.getenv("HF_TOKEN", "")
HF_STORAGE_REPO = os.getenv("HF_STORAGE_REPO", "")   # e.g. "AKP-07/jarvis-data"

# ─────────────────────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────────────────────

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ─────────────────────────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────────────────────────

CYCLE_HOURS        = int(os.getenv("CYCLE_HOURS", 8))
CYCLE_INTERVAL     = CYCLE_HOURS * 3600
DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", 7))   # 7 AM IST

# ─────────────────────────────────────────────────────────────
# SEVERITY ROUTING
# ─────────────────────────────────────────────────────────────

IMMEDIATE_ALERT_LEVELS = {"CRITICAL", "HIGH"}
DIGEST_LEVELS          = {"MEDIUM", "LOW"}
RECORD_ONLY_LEVELS     = {"MINIMAL"}

# ─────────────────────────────────────────────────────────────
# SCRAPER
# ─────────────────────────────────────────────────────────────

SCRAPE_TIMEOUT     = 15
SCRAPE_MAX_CHARS   = 6000
RSS_FALLBACK_CHARS = 3000

# ─────────────────────────────────────────────────────────────
# AI
# ─────────────────────────────────────────────────────────────

AI_MAX_CONTENT_CHARS = 4000
AI_TIMEOUT           = 120
AI_TEMPERATURE       = 0.1
AI_MAX_TOKENS        = 800

# Provider pacing and quotas are configurable from env so HF deployments can
# be tuned without code edits.
GEMINI_MIN_INTERVAL = float(os.getenv("GEMINI_MIN_INTERVAL", "4.5"))
GROQ_MIN_INTERVAL   = float(os.getenv("GROQ_MIN_INTERVAL", "2.5"))

GEMINI_SYNTHESIS_MODEL         = os.getenv("GEMINI_SYNTHESIS_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODEL          = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash-lite")
GROQ_ARTICLE_MODEL             = os.getenv("GROQ_ARTICLE_MODEL", "llama-3.1-8b-instant")
GROQ_ARTICLE_FALLBACK_MODEL    = os.getenv("GROQ_ARTICLE_FALLBACK_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_SYNTHESIS_MODEL           = os.getenv("GROQ_SYNTHESIS_MODEL", "llama-3.3-70b-versatile")
GROQ_TEXT_MODEL                = os.getenv("GROQ_TEXT_MODEL", "llama-3.3-70b-versatile")

GEMINI_SYNTHESIS_HOURLY_LIMIT  = int(os.getenv("GEMINI_SYNTHESIS_HOURLY_LIMIT", "6"))
GEMINI_SYNTHESIS_DAILY_LIMIT   = int(os.getenv("GEMINI_SYNTHESIS_DAILY_LIMIT", "20"))
GEMINI_SYNTHESIS_WEEKLY_LIMIT  = int(os.getenv("GEMINI_SYNTHESIS_WEEKLY_LIMIT", "100"))
GEMINI_GENERAL_HOURLY_LIMIT    = int(os.getenv("GEMINI_GENERAL_HOURLY_LIMIT", "4"))
GEMINI_GENERAL_DAILY_LIMIT     = int(os.getenv("GEMINI_GENERAL_DAILY_LIMIT", "16"))
GEMINI_COOLDOWN_429_SECONDS    = int(os.getenv("GEMINI_COOLDOWN_429_SECONDS", "1800"))
GEMINI_COOLDOWN_DAILY_SECONDS  = int(os.getenv("GEMINI_COOLDOWN_DAILY_SECONDS", "28800"))
GROQ_HOURLY_LIMIT              = int(os.getenv("GROQ_HOURLY_LIMIT", "500"))
GROQ_DAILY_LIMIT               = int(os.getenv("GROQ_DAILY_LIMIT", "5000"))
GROQ_COOLDOWN_429_SECONDS      = int(os.getenv("GROQ_COOLDOWN_429_SECONDS", "120"))

# ─────────────────────────────────────────────────────────────
# PATHS  (/tmp/jarvis/ survives within a session & is always writable)
# ─────────────────────────────────────────────────────────────

_BASE = os.getenv("JARVIS_DATA_DIR", "/tmp/jarvis/data")

DATA_DIR      = _BASE
PROCESSED_DIR = os.path.join(_BASE, "processed")
DAILY_DIR     = os.path.join(_BASE, "daily")
ARCHIVE_DIR   = os.path.join(_BASE, "archive")
RAW_DIR       = os.path.join(_BASE, "raw_articles")

# State files live in CWD (working dir of the space).
# storage_backend syncs these to HF Dataset for persistence.
SEEN_FILE         = "seen.json"
TELEMETRY_FILE    = "telemetry.json"
QUEUE_FILE        = "queue.json"          # Not used (in-memory queue)
DIGEST_STATE_FILE = "digest_state.json"
PROVIDER_STATE_FILE = "provider_state.json"
SUBSCRIBERS_FILE    = os.path.join("data", "subscribers.json")

# Ensure data dirs exist at import time
for _d in [PROCESSED_DIR, DAILY_DIR, ARCHIVE_DIR, RAW_DIR]:
    os.makedirs(_d, exist_ok=True)
os.makedirs(os.path.dirname(SUBSCRIBERS_FILE), exist_ok=True)
