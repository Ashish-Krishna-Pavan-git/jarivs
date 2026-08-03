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
# NOTIFICATION ARCHITECTURE (SLACK PRIMARY, TELEGRAM OPTIONAL)
# ─────────────────────────────────────────────────────────────

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_MODE    = os.getenv("TELEGRAM_MODE", "polling") # "polling" or "webhook"

def _resolve_notification_provider() -> str:
    env_prov = os.getenv("NOTIFICATION_PROVIDER", "").strip().lower()
    if env_prov in ("slack", "telegram", "both", "none"):
        return env_prov
        
    if os.getenv("ENABLE_TELEGRAM") is not None or os.getenv("ENABLE_SLACK") is not None:
        enable_tg = os.getenv("ENABLE_TELEGRAM", "").strip().lower() in ("true", "1", "yes")
        enable_sl = os.getenv("ENABLE_SLACK", "true").strip().lower() in ("true", "1", "yes")
        if enable_tg and enable_sl: return "both"
        elif enable_tg: return "telegram"
        elif enable_sl: return "slack"
        else: return "none"
        
    try:
        if os.path.exists("runtime_state.json"):
            with open("runtime_state.json", encoding="utf-8") as f:
                saved = json.load(f).get("notification_provider")
                if saved in ("slack", "telegram", "both", "none"):
                    return saved
    except Exception:
        pass

    if IS_HF or os.getenv("HF_SPACE_URL") or os.getenv("SPACE_ID"):
        return "slack"
    return "both"

NOTIFICATION_PROVIDER = _resolve_notification_provider()
IS_SLACK_ENABLED = NOTIFICATION_PROVIDER in ("slack", "both")
IS_TELEGRAM_ENABLED = NOTIFICATION_PROVIDER in ("telegram", "both")

def get_notification_provider_info() -> dict:
    prov = _resolve_notification_provider()
    return {
        "provider": prov,
        "slack_enabled": prov in ("slack", "both"),
        "telegram_enabled": prov in ("telegram", "both"),
        "is_hf": IS_HF or bool(os.getenv("HF_SPACE_URL") or os.getenv("SPACE_ID")),
    }

def set_notification_provider(provider: str) -> dict:
    provider = str(provider or "").strip().lower()
    if provider not in ("slack", "telegram", "both", "none"):
        return {"ok": False, "error": f"Invalid provider '{provider}'. Must be slack, telegram, both, or none."}
    
    os.environ["NOTIFICATION_PROVIDER"] = provider
    try:
        from runtime_state import update_runtime_state
        update_runtime_state(notification_provider=provider)
    except Exception:
        pass
    
    global NOTIFICATION_PROVIDER, IS_SLACK_ENABLED, IS_TELEGRAM_ENABLED
    NOTIFICATION_PROVIDER = provider
    IS_SLACK_ENABLED = provider in ("slack", "both")
    IS_TELEGRAM_ENABLED = provider in ("telegram", "both")
    
    return {"ok": True, "provider": provider, "slack_enabled": IS_SLACK_ENABLED, "telegram_enabled": IS_TELEGRAM_ENABLED}

def reload_config() -> dict:
    """Reload .env and refresh module-level configuration variables in place."""
    load_dotenv(override=True)

    global GEMINI_API_KEY, GROQ_API_KEY, HF_TOKEN, HF_STORAGE_REPO
    global TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_MODE
    global NOTIFICATION_PROVIDER, IS_SLACK_ENABLED, IS_TELEGRAM_ENABLED
    global CYCLE_HOURS, CYCLE_INTERVAL, DAILY_SUMMARY_HOUR

    GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
    GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
    HF_TOKEN        = os.getenv("HF_TOKEN", "")
    HF_STORAGE_REPO = os.getenv("HF_STORAGE_REPO", "")

    TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    TELEGRAM_MODE    = os.getenv("TELEGRAM_MODE", "polling")

    NOTIFICATION_PROVIDER = _resolve_notification_provider()
    IS_SLACK_ENABLED     = NOTIFICATION_PROVIDER in ("slack", "both")
    IS_TELEGRAM_ENABLED  = NOTIFICATION_PROVIDER in ("telegram", "both")

    CYCLE_HOURS        = int(os.getenv("CYCLE_HOURS", 8))
    CYCLE_INTERVAL     = CYCLE_HOURS * 3600
    DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", 7))

    return {
        "ok": True,
        "provider": NOTIFICATION_PROVIDER,
        "slack_enabled": IS_SLACK_ENABLED,
        "telegram_enabled": IS_TELEGRAM_ENABLED,
        "is_hf": IS_HF or bool(os.getenv("HF_SPACE_URL") or os.getenv("SPACE_ID")),
    }

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

# Gemini free tier: 15 RPM → 4.0s minimum between calls (use 4.5 for safety)
# Groq free tier:  30 RPM → 2.0s minimum between calls (use 2.5 for safety)
GEMINI_MIN_INTERVAL = 4.5
GROQ_MIN_INTERVAL   = 2.5

# ─────────────────────────────────────────────────────────────
# PATHS  (/tmp/jarvis/ survives within a session & is always writable)
# ─────────────────────────────────────────────────────────────

_BASE = os.getenv("JARVIS_DATA_DIR", "/tmp/jarvis/data")

DATA_DIR      = _BASE
PROCESSED_DIR = os.path.join(_BASE, "processed")
DAILY_DIR     = os.path.join(_BASE, "daily")
ARCHIVE_DIR   = os.path.join(_BASE, "archive")
RAW_DIR       = os.path.join(_BASE, "raw_articles")

# ─────────────────────────────────────────────────────────────
# STATE FILES  (CWD — synced to HF Dataset for persistence)
# ─────────────────────────────────────────────────────────────

SEEN_FILE          = "seen.json"
TELEMETRY_FILE     = "telemetry.json"
QUEUE_FILE         = "queue.json"           # Not used (in-memory queue)
DIGEST_STATE_FILE  = "digest_state.json"
RUNTIME_STATE_FILE = "runtime_state.json"   # FIX: was missing — crashed runtime_state.py
SUBSCRIBERS_FILE   = os.path.join("data", "subscribers.json")  # FIX: was missing — crashed subscriber_store.py

# Ensure data dirs exist at import time
for _d in [PROCESSED_DIR, DAILY_DIR, ARCHIVE_DIR, RAW_DIR, os.path.dirname(SUBSCRIBERS_FILE)]:
    os.makedirs(_d, exist_ok=True)
