"""
bot_listener.py
Telegram bot: /start /stop /status /deepdive /quiz

WEBHOOK MODE (preferred for HF Spaces):
  Telegram pushes updates to Flask /telegram/<token> endpoint.
  No outbound polling from HF Spaces — much more reliable.
  Requires HF_SPACE_URL secret set.

POLLING FALLBACK:
  Used if HF_SPACE_URL is not set.
  Uses 15s long-poll timeout + 40s requests timeout (HF Spaces safe).

FIX: setMyCommands now called safely with short timeout (won't crash on failure).
FIX: Polling allowed_updates matches webhook config.
FIX: Uses subscriber_store for HF-synced subscriber management.
FIX: handle_update handles message + channel_post + edited variants.
"""

import os
import time
import json
import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from queue_manager import stats as queue_stats
from telemetry import get_stats as tele_stats
from storage import load_last_n_hours
from ai_router import local_call, local_call_text, extract_json
from subscriber_store import load_subscribers, subscribe, unsubscribe

HF_SPACE_URL = os.getenv("HF_SPACE_URL", "").rstrip("/")

# Allowed update types — consistent between webhook and polling
_ALLOWED_UPDATES = ["message", "channel_post", "edited_message", "edited_channel_post"]

# Shared session with auto-retry (handles transient network errors)
_session = requests.Session()
_adapter = HTTPAdapter(max_retries=Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"],
))
_session.mount("https://", _adapter)


def send_reply(chat_id, text):
    """Send reply to one chat. Tries Markdown first, falls back to plain text."""
    if not TELEGRAM_TOKEN:
        return
    url   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    MAX   = 4000
    text  = str(text)
    parts = [text[i:i+MAX] for i in range(0, len(text), MAX)] if len(text) > MAX else [text]

    for chunk in parts:
        sent = False
        for parse_mode in ["Markdown", None]:
            payload = {"chat_id": chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            try:
                r = _session.post(url, json=payload, timeout=40)
                if r.status_code == 200:
                    sent = True
                    break
                elif r.status_code == 400 and parse_mode == "Markdown":
                    continue  # Retry without Markdown formatting
                else:
                    print(f"[BOT] Reply HTTP {r.status_code}: {r.text[:60]}")
                    break
            except Exception as e:
                print(f"[BOT] Reply error: {e}")
                if parse_mode is None:
                    time.sleep(2)
        if not sent:
            print(f"[BOT] Failed to send reply to {chat_id}")
        time.sleep(0.3)


def execute_deepdive(chat_id, keyword):
    send_reply(chat_id, f"🔍 *Deep Dive: '{keyword}'*\nSearching database...")
    items    = load_last_n_hours(168)
    relevant = [i for i in items if keyword.lower() in str(i).lower()]

    if not relevant:
        send_reply(chat_id, f"⚠️ No intelligence on *'{keyword}'* in the last 7 days.\nTry: `/deepdive Ransomware` or `/deepdive CVE`")
        return

    send_reply(chat_id, f"📚 Found *{len(relevant)}* articles. Generating AI dossier...")

    context = ""
    for item in relevant[:20]:
        summary = item.get("summary_text", "") or " | ".join(item.get("summary", []))
        cves    = ", ".join(item.get("cves", []))
        context += f"[{item.get('severity','?')}] {item.get('title','')}\n"
        if cves:
            context += f"CVEs: {cves}\n"
        context += f"{summary[:300]}\n\n"

    prompt = f"""You are an elite cyber intelligence analyst. Write a professional Intelligence Dossier on: "{keyword}"

Based ONLY on these recent reports:
{context}

Write in plain readable text (NOT JSON, NOT markdown backticks):

OVERVIEW
[What is {keyword} and why it matters now]

KEY THREATS
- [Finding 1 from the reports]
- [Finding 2 from the reports]
- [Finding 3 from the reports]

THREAT ACTORS
[Any named actors from the reports]

IMPACT
[Real-world consequences]

RECOMMENDATIONS
1. [Action 1]
2. [Action 2]

CVEs: [List any from reports]

Under 400 words. Factual only. Plain text output."""

    report = local_call_text(prompt)

    if report and len(report.strip()) > 50 and not report.strip().startswith("{"):
        send_reply(chat_id, f"📊 *DEEP DIVE: {keyword.upper()}*\n\n{report}")
    else:
        send_reply(chat_id, "⚠️ AI returned unexpected format. Try again in a moment.")


def execute_quiz(chat_id):
    send_reply(chat_id, "🧠 *Generating daily intel quiz...*")
    items     = load_last_n_hours(24)
    crit_high = [i for i in items if i.get("severity") in ("CRITICAL", "HIGH")] or items[:10]

    if not crit_high:
        send_reply(chat_id, "⚠️ Not enough data yet. Try after the next cycle!")
        return

    context = "\n".join(
        f"• {i.get('title','')}: {(i.get('summary_text','') or '')[:200]}"
        for i in crit_high[:5]
    )
    prompt = f"""Based on these recent news items, create ONE multiple-choice trivia question.

News:
{context}

Return ONLY this JSON:
{{
  "question": "Specific trivia question (under 200 chars)",
  "options": ["Option A", "Option B", "Option C", "Option D"],
  "correct_index": 0,
  "explanation": "Brief explanation of correct answer (under 200 chars)"
}}"""

    raw  = local_call(prompt)
    data = extract_json(raw)

    if data and "question" in data and len(data.get("options", [])) >= 2:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPoll"
        try:
            _session.post(url, json={
                "chat_id":           chat_id,
                "question":          data["question"][:300],
                "options":           data["options"][:10],
                "type":              "quiz",
                "correct_option_id": int(data.get("correct_index", 0)),
                "explanation":       str(data.get("explanation", ""))[:200],
                "is_anonymous":      False,
            }, timeout=40)
        except Exception as e:
            send_reply(chat_id, f"⚠️ Quiz send error: {e}")
    else:
        send_reply(chat_id, "⚠️ AI failed to format quiz. Try `/quiz` again.")


def handle_message(text, chat_id, first_name):
    cmd  = text.lower().strip()
    subs = load_subscribers()

    if cmd == "/start":
        subscribe(chat_id)
        send_reply(chat_id,
            f"👋 *Welcome to JARVIS, {first_name}!*\n\n"
            "🟢 *You are now SUBSCRIBED to intelligence alerts.*\n\n"
            "📋 *Commands:*\n"
            "• /status — System health\n"
            "• /quiz — Daily intel quiz\n"
            "• /deepdive topic — Research dossier\n"
            "• /stop — Unsubscribe\n\n"
            "🤖 CRITICAL/HIGH alerts sent immediately. 8hr digests every cycle.")

    elif cmd == "/stop":
        unsubscribe(chat_id)
        send_reply(chat_id, "🛑 *Unsubscribed.* Send /start to re-subscribe anytime.")

    elif cmd == "/status":
        qs   = queue_stats()
        ts   = tele_stats()
        sev  = " | ".join(f"{k}:{v}" for k, v in ts.get("by_severity", {}).items() if v > 0) or "none yet"
        mode = "webhook" if HF_SPACE_URL else "polling"
        send_reply(chat_id,
            f"📊 *JARVIS Status*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👥 Subscribers: {len(subs)}\n"
            f"📥 Queue: {qs.get('pending', 0)} pending\n"
            f"✅ Processed: {ts.get('total_processed', 0)} total\n"
            f"🔄 Cycles: {ts.get('cycles_run', 0)}\n"
            f"📈 By severity: {sev}\n"
            f"🕐 Last cycle: {ts.get('last_cycle_at', 'never')}\n"
            f"📡 Mode: {mode}")

    elif cmd == "/quiz":
        threading.Thread(target=execute_quiz, args=(chat_id,), daemon=True).start()

    elif cmd.startswith("/deepdive"):
        parts = text.strip().split(None, 1)
        if len(parts) > 1:
            threading.Thread(target=execute_deepdive, args=(chat_id, parts[1].strip()), daemon=True).start()
        else:
            send_reply(chat_id, "⚠️ Usage: `/deepdive <topic>`\nExample: `/deepdive Ransomware`")

    elif cmd.startswith("/"):
        send_reply(chat_id, "❓ Commands: /status /quiz /deepdive <topic> /start /stop")


def handle_update(update):
    """
    Entry point for both webhook and polling modes.
    Handles message + channel_post + edited variants.
    FIX: was only checking 'message' — channel_post silently dropped.
    """
    try:
        # Try all possible message containers in priority order
        msg = (
            update.get("message")
            or update.get("channel_post")
            or update.get("edited_message")
            or update.get("edited_channel_post")
            or {}
        )
        text  = msg.get("text")
        chat  = msg.get("chat", {})
        cid   = chat.get("id")
        fname = chat.get("first_name") or chat.get("title") or "Agent"
        if text and cid:
            handle_message(text, str(cid), fname)
    except Exception as e:
        print(f"[BOT] handle_update error: {e}")


def _poll_loop():
    """
    Long-poll loop for fallback mode.
    FIX: long-poll timeout reduced to 15s (HF Spaces kills idle connections).
    FIX: requests timeout = 40s (15s poll + 25s buffer).
    FIX: allowed_updates consistent with webhook config.
    """
    if not TELEGRAM_TOKEN:
        return
    url    = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    offset = None
    print("[BOT] Polling loop started")

    while True:
        try:
            params = {
                "timeout":         15,            # FIX: was 20; shorter = fewer HF timeout kills
                "allowed_updates": _ALLOWED_UPDATES,
            }
            if offset:
                params["offset"] = offset

            # FIX: requests timeout = poll_timeout + 25s safety margin
            r = _session.get(url, params=params, timeout=40)

            if r.status_code == 200:
                for update in r.json().get("result", []):
                    offset = update["update_id"] + 1
                    threading.Thread(
                        target=handle_update, args=(update,), daemon=True
                    ).start()
            elif r.status_code == 409:
                # Conflict: another instance is polling (webhook might have taken over)
                print("[BOT] 409 Conflict — another poller running. Pausing 30s.")
                time.sleep(30)
            else:
                print(f"[BOT] Poll HTTP {r.status_code}")
                time.sleep(5)

        except requests.exceptions.Timeout:
            # Expected occasionally — just loop again immediately
            pass
        except requests.exceptions.ConnectionError as e:
            print(f"[BOT] Poll connection error: {e}")
            time.sleep(10)
        except Exception as e:
            print(f"[BOT] Poll error: {e}")
            time.sleep(5)

        time.sleep(0.3)   # Small gap between polls


def _set_commands():
    """
    Register bot commands with BotFather so they appear in the menu.
    FIX: was blocking with long timeout — now short, non-fatal on failure.
    """
    if not TELEGRAM_TOKEN:
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setMyCommands",
            json={"commands": [
                {"command": "start",     "description": "Subscribe to alerts"},
                {"command": "stop",      "description": "Unsubscribe from alerts"},
                {"command": "status",    "description": "System health & stats"},
                {"command": "quiz",      "description": "Daily intel quiz"},
                {"command": "deepdive",  "description": "Research dossier on a topic"},
            ]},
            timeout=15,   # FIX: short timeout — startup should never hang on this
        )
        if r.status_code == 200:
            print("[BOT] ✓ Commands registered with Telegram")
        else:
            print(f"[BOT] setMyCommands HTTP {r.status_code} — non-fatal, continuing")
    except Exception as e:
        print(f"[BOT] setMyCommands failed (non-fatal): {e}")


def start_listener():
    # Register commands in background — never blocks startup
    threading.Thread(target=_set_commands, daemon=True).start()

    if HF_SPACE_URL:
        print(f"[BOT] Webhook mode — listening at {HF_SPACE_URL}/telegram/<token>")
    else:
        threading.Thread(target=_poll_loop, daemon=True).start()
        print("[BOT] Polling mode started (add HF_SPACE_URL secret for webhook mode)")
