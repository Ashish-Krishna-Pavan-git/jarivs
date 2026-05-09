"""
app.py
Flask web server + JARVIS orchestrator launcher.

WEBHOOK MODE:
  Telegram pushes updates to /telegram/<token> — much more reliable than polling
  from HF Spaces, which has intermittent outbound connectivity issues.
  
  Set HF_SPACE_URL in Space secrets:
    HF_SPACE_URL = https://akp-07-jarvis-agent.hf.space

BUG FIX:
  If webhook registration fails (e.g. timeout at startup), HF_SPACE_URL is
  cleared from the environment before launching the scheduler subprocess.
  This ensures bot_listener.start_listener() falls back to polling mode,
  so /start and /status commands are never silently ignored.
"""

import subprocess
import sys
import os
import time
import threading
import requests
from flask import Flask, request, jsonify
from storage_backend import pull_state, is_configured

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
HF_SPACE_URL   = os.getenv("HF_SPACE_URL", "").rstrip("/")


# ─────────────────────────────────────────────────────────────
# HEALTH ROUTES
# ─────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return "✅ JARVIS Intelligence System Online"

@app.route("/ping")
def ping():
    return "pong"

@app.route("/health")
def health():
    return jsonify({"status": "ok", "telegram_token": bool(TELEGRAM_TOKEN)})


# ─────────────────────────────────────────────────────────────
# TELEGRAM WEBHOOK ENDPOINT
# ─────────────────────────────────────────────────────────────

@app.route(f"/telegram/<token>", methods=["POST"])
def telegram_webhook(token):
    """
    Telegram pushes every update here as a POST request.
    Much more reliable than long-polling from HF Spaces.
    """
    if token != TELEGRAM_TOKEN:
        return "Unauthorized", 403

    try:
        update = request.get_json(force=True)
        if update:
            from bot_listener import handle_update
            threading.Thread(
                target=handle_update, args=(update,), daemon=True
            ).start()
    except Exception as e:
        print(f"[WEBHOOK] Error processing update: {e}")

    return "ok", 200


# ─────────────────────────────────────────────────────────────
# WEBHOOK REGISTRATION
# ─────────────────────────────────────────────────────────────

def register_webhook() -> bool:
    """
    Register our public HF Space URL as the Telegram webhook.
    Tries twice with escalating timeouts before giving up.
    """
    if not TELEGRAM_TOKEN:
        print("[WEBHOOK] No TELEGRAM_TOKEN — skipping webhook registration")
        return False

    if not HF_SPACE_URL:
        print("[WEBHOOK] No HF_SPACE_URL set — falling back to polling mode")
        print("          Add HF_SPACE_URL=https://akp-07-jarvis-agent.hf.space to Space secrets")
        return False

    webhook_url = f"{HF_SPACE_URL}/telegram/{TELEGRAM_TOKEN}"
    api_url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"

    for attempt, timeout in enumerate([15, 25], start=1):
        try:
            r = requests.post(
                api_url,
                json={
                    "url":             webhook_url,
                    "allowed_updates": ["message", "channel_post", "edited_message", "edited_channel_post"],
                    "drop_pending_updates": False,
                },
                timeout=timeout,
            )
            data = r.json()
            if data.get("ok"):
                print(f"[WEBHOOK] ✓ Registered: {webhook_url}")
                return True
            else:
                print(f"[WEBHOOK] ✗ Registration failed: {data.get('description')}")
                return False
        except requests.exceptions.Timeout:
            if attempt == 1:
                print(f"[WEBHOOK] Attempt {attempt} timed out — retrying once...")
                time.sleep(3)
                continue
            print("[WEBHOOK] ✗ All registration attempts timed out")
            return False
        except Exception as e:
            print(f"[WEBHOOK] ✗ Registration error: {e}")
            return False

    return False


def delete_webhook():
    """Remove webhook so polling mode works (call if switching back)."""
    if not TELEGRAM_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
            timeout=10,
        )
    except Exception:
        pass


def send_startup_message():
    """Send a boot notification to verify Telegram connectivity on startup."""
    if not TELEGRAM_TOKEN:
        return

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        return

    time.sleep(5)   # give Flask time to start

    for attempt in range(1, 4):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id":    chat_id,
                    "text":       "🤖 *JARVIS Online* — Intelligence system started. First cycle beginning...",
                    "parse_mode": "Markdown",
                },
                timeout=20,
            )
            if r.status_code == 200:
                print("[STARTUP] ✓ Telegram connectivity verified — boot message sent")
                return
            else:
                print(f"[STARTUP] Attempt {attempt}: HTTP {r.status_code}")
        except Exception as e:
            print(f"[STARTUP] Attempt {attempt} error: {e}")
        time.sleep(attempt * 5)

    print("[STARTUP] ✗ All boot message attempts failed — check TELEGRAM_TOKEN/network")


# ─────────────────────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[CLOUD] Starting JARVIS Bot...")

    if is_configured():
        print("[CLOUD] Restoring persisted HF state before webhook startup...")
        pull_state()

    # 1. Try to register Telegram webhook (best mode for HF Spaces)
    webhook_ok = register_webhook()

    # ── KEY FIX ───────────────────────────────────────────────────────────────
    # When webhook registration fails, HF_SPACE_URL is still set in os.environ.
    # The scheduler subprocess inherits this env, so bot_listener.start_listener()
    # assumes webhook mode and NEVER starts the polling loop.
    # Result: bot is completely deaf — /start and /status get no response.
    #
    # Fix: clear HF_SPACE_URL from env before Popen so the child process
    # inherits an empty value and correctly starts the polling fallback.
    # ─────────────────────────────────────────────────────────────────────────
    if not webhook_ok and HF_SPACE_URL:
        print("[CLOUD] Webhook failed — clearing HF_SPACE_URL so scheduler uses polling mode")
        os.environ["HF_SPACE_URL"] = ""

    # 2. Start scheduler subprocess (inherits current env, with cleared HF_SPACE_URL if needed)
    scheduler_proc = subprocess.Popen(
        [sys.executable, "scheduler.py"],
        env=os.environ.copy(),
    )
    print(f"[CLOUD] Scheduler started (pid={scheduler_proc.pid})")

    # 3. Test Telegram connectivity on boot (non-blocking)
    threading.Thread(target=send_startup_message, daemon=True).start()

    if not webhook_ok:
        print("[CLOUD] Mode: polling (scheduler handles bot commands via getUpdates loop)")
    else:
        print(f"[CLOUD] Mode: webhook → {HF_SPACE_URL}/telegram/<token>")

    # 4. Start Flask (receives webhook POSTs + health checks)
    print("[CLOUD] Starting web server on port 7860...")
    app.run(host="0.0.0.0", port=7860)
