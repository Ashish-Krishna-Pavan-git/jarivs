import os
import sys

from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────
# PLATFORM DETECTION
# ─────────────────────────────────────────

IS_WINDOWS = sys.platform == "win32"
IS_TERMUX  = "com.termux" in os.environ.get("PREFIX", "")
PLATFORM   = "windows" if IS_WINDOWS else ("termux" if IS_TERMUX else "linux")

# ─────────────────────────────────────────
# LOCAL AI ENDPOINTS
# ─────────────────────────────────────────

OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "phi4-mini")

LLAMACPP_URL = os.getenv("LLAMACPP_URL", "http://localhost:8080")

# ─────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ─────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────

CYCLE_HOURS        = int(os.getenv("CYCLE_HOURS", 8))
CYCLE_INTERVAL     = CYCLE_HOURS * 3600
DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", 7))  # 7 AM UTC

# ─────────────────────────────────────────
# SEVERITY ROUTING
# ─────────────────────────────────────────

# CRITICAL, HIGH  → immediate Telegram alert
# MEDIUM, LOW     → 8hr digest only
# MINIMAL         → saved/recorded, not sent

IMMEDIATE_ALERT_LEVELS = {"CRITICAL", "HIGH"}
DIGEST_LEVELS          = {"MEDIUM", "LOW"}
RECORD_ONLY_LEVELS     = {"MINIMAL"}

# ─────────────────────────────────────────
# SCRAPER
# ─────────────────────────────────────────

SCRAPE_TIMEOUT     = 15
SCRAPE_MAX_CHARS   = 6000
RSS_FALLBACK_CHARS = 3000

# ─────────────────────────────────────────
# AI
# ─────────────────────────────────────────

AI_MAX_CONTENT_CHARS = 4000
AI_TIMEOUT           = 120
AI_TEMPERATURE       = 0.1
AI_MAX_TOKENS        = 800

# ─────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────

DATA_DIR           = "data"
PROCESSED_DIR      = os.path.join(DATA_DIR, "processed")
DAILY_DIR          = os.path.join(DATA_DIR, "daily")
ARCHIVE_DIR        = os.path.join(DATA_DIR, "archive")
RAW_DIR            = os.path.join(DATA_DIR, "raw_articles")

QUEUE_FILE         = "queue.json"
SEEN_FILE          = "seen.json"
TELEMETRY_FILE     = "telemetry.json"
DIGEST_STATE_FILE  = "digest_state.json"
