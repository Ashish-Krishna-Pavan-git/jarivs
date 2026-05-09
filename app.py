"""
app.py
Flask web server + JARVIS orchestrator launcher.

WEBHOOK MODE:
  Telegram pushes updates to /telegram/<token> — much more reliable than polling
  from HF Spaces, which has intermittent outbound connectivity issues.
  
  Set HF_SPACE_URL in Space secrets:
    HF_SPACE_URL = https://akp-07-jarvis-agent.hf.space
"""

import subprocess
import os
import threading
import requests
from flask import Flask, request, jsonify

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
            # Process in a thread so Flask returns 200 immediately
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

def register_webhook():
    """Register our public HF Space URL as the Telegram webhook."""
    if not TELEGRAM_TOKEN:
        print("[WEBHOOK] No TELEGRAM_TOKEN — skipping webhook registration")
        return False

    if not HF_SPACE_URL:
        print("[WEBHOOK] No HF_SPACE_URL set — falling back to polling mode")
        print("          Add HF_SPACE_URL=https://akp-07-jarvis-agent.hf.space to Space secrets")
        return False

    webhook_url = f"{HF_SPACE_URL}/telegram/{TELEGRAM_TOKEN}"
    api_url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"

    try:
        r = requests.post(
            api_url,
            json={
                "url":             webhook_url,
                "allowed_updates": ["message"],
                "drop_pending_updates": True,
            },
            timeout=30,
        )
        data = r.json()
        if data.get("ok"):
            print(f"[WEBHOOK] ✓ Registered: {webhook_url}")
            return True
        else:
            print(f"[WEBHOOK] ✗ Registration failed: {data.get('description')}")
            return False
    except Exception as e:
        print(f"[WEBHOOK] ✗ Registration error: {e}")
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

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "🤖 *JARVIS Online* — Intelligence system started. First cycle beginning...",
                "parse_mode": "Markdown",
            },
            timeout=15,
        )
        if r.status_code == 200:
            print("[STARTUP] ✓ Telegram connectivity verified — boot message sent")
        else:
            print(f"[STARTUP] ✗ Telegram send failed: HTTP {r.status_code} — {r.text[:100]}")
    except Exception as e:
        print(f"[STARTUP] ✗ Telegram unreachable: {e}")
        print("[STARTUP]   Check TELEGRAM_TOKEN and network connectivity")


# ─────────────────────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("[CLOUD] Starting JARVIS Bot...")

    # 1. Try to register Telegram webhook (best mode for HF Spaces)
    webhook_ok = register_webhook()

    # 2. Start scheduler in background
    scheduler_proc = subprocess.Popen(["python", "scheduler.py"])

    # 3. Test Telegram connectivity on boot
    threading.Thread(target=send_startup_message, daemon=True).start()

    # 4. If webhook failed, scheduler will start polling mode automatically
    if not webhook_ok:
        print("[CLOUD] Webhook not registered — scheduler will use polling mode")

    # 5. Start Flask (receives webhook POSTs + health checks)
    print("[CLOUD] Starting web server on port 7860...")
    app.run(host="0.0.0.0", port=7860)
