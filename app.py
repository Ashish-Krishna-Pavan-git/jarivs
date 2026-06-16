"""
app.py
Flask web server + JARVIS orchestrator launcher.

CRITICAL FIX: delete_webhook() is now called when webhook registration fails.
Previously, a webhook registered in a prior run stayed active. When the new
instance started polling, Telegram returned 409 Conflict on every getUpdates
call — flooding logs and blocking all bot replies.

Fix: always delete the stale webhook before falling back to polling mode.
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
# WEBHOOK MANAGEMENT
# ─────────────────────────────────────────────────────────────

def register_webhook() -> bool:
    if not TELEGRAM_TOKEN:
        print("[WEBHOOK] No TELEGRAM_TOKEN — skipping webhook registration")
        return False
    if not HF_SPACE_URL:
        print("[WEBHOOK] No HF_SPACE_URL set — falling back to polling mode")
        return False

    webhook_url = f"{HF_SPACE_URL}/telegram/{TELEGRAM_TOKEN}"
    api_url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"

    for attempt, timeout in enumerate([15, 25], start=1):
        try:
            r = requests.post(
                api_url,
                json={
                    "url":                  webhook_url,
                    "allowed_updates":      ["message", "channel_post", "edited_message", "edited_channel_post"],
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
    """
    Remove any registered webhook.
    CRITICAL: must be called before starting polling to prevent 409 Conflict.
    """
    if not TELEGRAM_TOKEN:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
            json={"drop_pending_updates": False},
            timeout=15,
        )
        if r.status_code == 200 and r.json().get("ok"):
            print("[WEBHOOK] ✓ Stale webhook deleted — polling mode is clear")
        else:
            print(f"[WEBHOOK] deleteWebhook response: {r.text[:80]}")
    except Exception as e:
        print(f"[WEBHOOK] deleteWebhook error (non-fatal): {e}")


def send_startup_message():
    if not TELEGRAM_TOKEN:
        return
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not chat_id:
        return

    time.sleep(8)

    for attempt in range(1, 4):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id":    chat_id,
                    "text":       "🤖 *JARVIS Online* — Intelligence system restarted. Boot cycle starting in 90s.",
                    "parse_mode": "Markdown",
                },
                timeout=20,
            )
            if r.status_code == 200:
                print("[STARTUP] ✓ Boot message sent to Telegram")
                return
            else:
                print(f"[STARTUP] Attempt {attempt}: HTTP {r.status_code}")
        except Exception as e:
            print(f"[STARTUP] Attempt {attempt} error: {e}")
        time.sleep(attempt * 5)

    print("[STARTUP] ✗ Boot message failed — check TELEGRAM_TOKEN/network")


# ─────────────────────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[CLOUD] Starting JARVIS Bot...")

    if is_configured():
        print("[CLOUD] Restoring persisted HF state before webhook startup...")
        pull_state()

    # 1. Try to register Telegram webhook
    webhook_ok = register_webhook()

    if not webhook_ok:
        # CRITICAL FIX: delete any stale webhook from previous runs BEFORE polling.
        # Without this, Telegram keeps the old webhook active while we poll → 409 Conflict
        # on every getUpdates call, flooding logs and silencing all bot replies.
        print("[CLOUD] Webhook failed — deleting stale webhook and switching to polling mode")
        delete_webhook()
        os.environ["HF_SPACE_URL"] = ""

    # 2. Start scheduler subprocess (inherits env with cleared HF_SPACE_URL)
    scheduler_proc = subprocess.Popen(
        [sys.executable, "scheduler.py"],
        env=os.environ.copy(),
    )
    print(f"[CLOUD] Scheduler started (pid={scheduler_proc.pid})")

    # 3. Send boot notification (non-blocking)
    threading.Thread(target=send_startup_message, daemon=True).start()

    if not webhook_ok:
        print("[CLOUD] Mode: polling (stale webhook cleared ✓)")
    else:
        print(f"[CLOUD] Mode: webhook → {HF_SPACE_URL}/telegram/<token>")

    # 4. Start Flask
    print("[CLOUD] Starting web server on port 7860...")
    app.run(host="0.0.0.0", port=7860)
