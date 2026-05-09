"""
bot_listener.py
Telegram bot: /start /stop /status /deepdive /quiz

WEBHOOK MODE (preferred for HF Spaces):
  Telegram pushes updates to Flask /telegram/<token> endpoint.
  No outbound polling from HF Spaces — much more reliable.
  Requires HF_SPACE_URL secret set (e.g. https://akp-07-jarvis-agent.hf.space)

POLLING FALLBACK:
  Used if HF_SPACE_URL is not set.

Uses requests.Session + HTTPAdapter(Retry) for connection stability.
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
from ai_router import local_call_general_json, local_call_text, extract_json, get_provider_status
from subscriber_store import load_subscribers, subscribe, unsubscribe
from runtime_state import load_runtime_state

HF_SPACE_URL = os.getenv("HF_SPACE_URL", "").rstrip("/")

# Shared session with auto-retry (handles transient network errors)
_session = requests.Session()
_adapter = HTTPAdapter(max_retries=Retry(
    total=5,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"],
))
_session.mount("https://", _adapter)


HELP_TEXT = (
    "🤖 JARVIS Commands\n\n"
    "/start - Subscribe this chat to alerts and reports\n"
    "/stop - Unsubscribe this chat\n"
    "/status - Show live queue, phase, cycle, provider, and subscriber status\n"
    "/today - Show today's article and severity summary\n"
    "/top - Show top high-priority items from the last 24 hours\n"
    "/quiz - Generate an intelligence quiz from recent items\n"
    "/deepdive <topic> - Build a dossier from the last 7 days\n"
    "/limits - Show Groq and Gemini usage/cooldown status\n"
    "/help - Show this help message\n\n"
    "Schedule (IST):\n"
    "- 7:00 AM: Daily summary + newsletter\n"
    "- 8:00 AM: Cycle 1 digest\n"
    "- 3:00 PM: Cycle 2 digest\n"
    "- 9:00 PM: Cycle 3 digest\n\n"
    "Tips:\n"
    "- In groups, use commands like /status@YourBotName if needed.\n"
    "- For best control, talk to the bot in a private chat first with /start."
)

MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "/status"}, {"text": "/today"}, {"text": "/top"}],
        [{"text": "/quiz"}, {"text": "/limits"}],
        [{"text": "/deepdive ransomware"}, {"text": "/help"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}


def _normalize_command(text: str) -> tuple[str, str]:
    text = (text or "").strip()
    if not text.startswith("/"):
        return "", text

    parts = text.split(None, 1)
    command = parts[0].split("@", 1)[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    return command, args


def _format_provider_line(name: str, status: dict) -> str:
    blocked = status.get("blocked_until") or "ready"
    usage = status.get("usage", {})
    return (
        f"{name}: state={status.get('state', 'unknown')} | "
        f"hour={usage.get('hour', 0)} | day={usage.get('day', 0)} | "
        f"blocked_until={blocked}"
    )


def register_bot_commands():
    if not TELEGRAM_TOKEN:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setMyCommands"
    commands = [
        {"command": "start", "description": "Subscribe this chat"},
        {"command": "stop", "description": "Unsubscribe this chat"},
        {"command": "status", "description": "System and provider status"},
        {"command": "today", "description": "Today's article summary"},
        {"command": "top", "description": "Top high-priority items"},
        {"command": "quiz", "description": "Generate an intel quiz"},
        {"command": "deepdive", "description": "Research a topic from recent data"},
        {"command": "limits", "description": "Show API cooldown and quota status"},
        {"command": "help", "description": "Show usage help"},
    ]
    try:
        _session.post(url, json={"commands": commands}, timeout=20)
    except Exception as e:
        print(f"[BOT] setMyCommands failed: {e}")


def send_reply(chat_id, text, reply_markup=None):
    """Send reply to one chat with stronger retry handling for HF Spaces."""
    if not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    max_len = 4000
    text = str(text)
    parts = [text[i:i+max_len] for i in range(0, len(text), max_len)] if len(text) > max_len else [text]

    for chunk_index, chunk in enumerate(parts, 1):
        sent = False
        for parse_mode in ["Markdown", None]:
            payload = {"chat_id": chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_markup and chunk_index == 1:
                payload["reply_markup"] = reply_markup
            for attempt in range(1, 4):
                try:
                    r = _session.post(url, json=payload, timeout=60)
                    if r.status_code == 200:
                        sent = True
                        break
                    if r.status_code == 400 and parse_mode == "Markdown":
                        break
                    if r.status_code == 429:
                        retry_after = r.json().get("parameters", {}).get("retry_after", 10)
                        print(f"[BOT] Reply rate limited — waiting {retry_after}s")
                        time.sleep(retry_after)
                        continue
                    if r.status_code in (500, 502, 503, 504):
                        wait = attempt * 5
                        print(f"[BOT] Reply HTTP {r.status_code}, retrying in {wait}s")
                        time.sleep(wait)
                        continue
                    print(f"[BOT] Reply HTTP {r.status_code}: {r.text[:120]}")
                    break
                except requests.exceptions.ReadTimeout:
                    wait = attempt * 5
                    print(f"[BOT] Reply read timeout, retrying in {wait}s")
                    time.sleep(wait)
                except requests.exceptions.ConnectionError as e:
                    wait = attempt * 5
                    print(f"[BOT] Reply connection error: {e}; retrying in {wait}s")
                    time.sleep(wait)
                except Exception as e:
                    print(f"[BOT] Reply error: {e}")
                    break
            if sent:
                break
        if not sent:
            print(f"[BOT] Failed to send reply to {chat_id}")
        time.sleep(0.2)


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

    raw  = local_call_general_json(prompt)
    data = extract_json(raw)

    if data and "question" in data and len(data.get("options", [])) >= 2:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPoll"
        try:
            _session.post(url, data={
                "chat_id":           chat_id,
                "question":          data["question"][:300],
                "options":           json.dumps(data["options"][:10]),
                "type":              "quiz",
                "correct_option_id": int(data.get("correct_index", 0)),
                "explanation":       str(data.get("explanation", ""))[:200],
                "is_anonymous":      "false",
            }, timeout=30)
        except Exception as e:
            send_reply(chat_id, f"⚠️ Quiz send error: {e}")
    else:
        send_reply(chat_id, "⚠️ AI failed to format quiz. Try `/quiz` again.")


def _today_summary_text():
    items = load_last_n_hours(24)
    if not items:
        return "📭 No processed articles in the last 24 hours yet."

    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "MINIMAL": 0}
    for item in items:
        severity = item.get("severity", "LOW")
        counts[severity] = counts.get(severity, 0) + 1

    return "\n".join([
        "🗓 Today So Far",
        f"📦 Total articles: {len(items)}",
        f"🚨 Critical: {counts.get('CRITICAL', 0)}",
        f"⚠️ High: {counts.get('HIGH', 0)}",
        f"📌 Medium: {counts.get('MEDIUM', 0)}",
        f"📄 Low: {counts.get('LOW', 0)}",
        f"ℹ️ Minimal: {counts.get('MINIMAL', 0)}",
    ])


def _top_items_text():
    items = load_last_n_hours(24)
    if not items:
        return "📭 No processed articles in the last 24 hours yet."

    severity_rank = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "MINIMAL": 1}
    top_items = sorted(
        items,
        key=lambda item: (severity_rank.get(item.get("severity", "LOW"), 0), item.get("confidence", 0)),
        reverse=True,
    )[:8]

    lines = ["🔥 Top Items (Last 24h)"]
    for item in top_items:
        lines.append(f"• [{item.get('severity', 'LOW')}] {str(item.get('title', ''))[:120]}")
    return "\n".join(lines)


def handle_message(text, chat_id, first_name):
    cmd, args = _normalize_command(text)
    subs = load_subscribers()

    if cmd == "/start":
        subs = subscribe(chat_id)
        send_reply(chat_id,
            f"👋 *Welcome to JARVIS, {first_name}!*\n\n"
            "🟢 *You are now SUBSCRIBED to intelligence alerts.*\n\n"
            "📋 *Commands:*\n"
            "• /status — System health\n"
            "• /today — Today's totals\n"
            "• /top — Top priority items\n"
            "• /quiz — Daily intel quiz\n"
            "• /deepdive topic — Research dossier\n"
            "• /limits — API quota and cooldown status\n"
            "• /help — Full usage guide\n"
            "• /stop — Unsubscribe\n\n"
            "🕒 Schedule: Daily at 7:00 AM IST, cycles at 8:00 AM, 3:00 PM, and 9:00 PM IST.\n\n"
            "🤖 CRITICAL/HIGH alerts are immediate. Cycle, daily, and weekly reports stay subscribed.",
            reply_markup=MAIN_KEYBOARD)

    elif cmd == "/stop":
        unsubscribe(chat_id)
        send_reply(chat_id, "🛑 *Unsubscribed.* Send /start to re-subscribe anytime.")

    elif cmd == "/status":
        qs  = queue_stats()
        ts  = tele_stats()
        rt  = load_runtime_state()
        sev = " | ".join(f"{k}:{v}" for k, v in ts.get("by_severity", {}).items() if v > 0) or "none yet"
        mode = "webhook" if HF_SPACE_URL else "polling"
        providers = get_provider_status()
        gemini_line = _format_provider_line("Gemini", providers.get("gemini", {}))
        groq_line = _format_provider_line("Groq", providers.get("groq", {}))
        send_reply(chat_id,
            f"📊 *JARVIS Status*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👥 Subscribers: {len(subs)}\n"
            f"⚙️ Phase: {rt.get('phase', 'idle')}\n"
            f"🔁 Cycle #: {rt.get('current_cycle_number', 0)}\n"
            f"🕒 Current slot: {rt.get('current_cycle_slot') or 'not running'}\n"
            f"⏭ Next cycle: {rt.get('next_cycle_at_ist') or 'not scheduled'}\n"
            f"🧾 Current item: {rt.get('current_item_title', '')[:80] or 'n/a'}\n"
            f"📥 Queue: {qs.get('pending', 0)} pending\n"
            f"📦 Runtime progress: {rt.get('queue_done', 0)}/{rt.get('queue_total', 0)} done | failed {rt.get('queue_failed', 0)}\n"
            f"✅ Processed: {ts.get('total_processed', 0)} total\n"
            f"🔄 Cycles: {ts.get('cycles_run', 0)}\n"
            f"📈 By severity: {sev}\n"
            f"🕐 Last cycle: {ts.get('last_cycle_at', 'never')}\n"
            f"🌅 Last daily run: {rt.get('last_daily_run_ist') or 'not yet'}\n"
            f"📡 Mode: {mode}\n\n"
            f"🔌 Providers:\n"
            f"• {groq_line}\n"
            f"• {gemini_line}")

    elif cmd == "/help":
        send_reply(chat_id, HELP_TEXT, reply_markup=MAIN_KEYBOARD)

    elif cmd == "/limits":
        providers = get_provider_status()
        gemini = providers.get("gemini", {})
        groq = providers.get("groq", {})
        send_reply(
            chat_id,
            "📏 API Limits\n\n"
            f"Groq\n"
            f"• State: {groq.get('state', 'unknown')}\n"
            f"• Hour/Day: {groq.get('usage', {}).get('hour', 0)}/{groq.get('usage', {}).get('day', 0)}\n"
            f"• Blocked until: {groq.get('blocked_until') or 'ready'}\n\n"
            f"Gemini\n"
            f"• State: {gemini.get('state', 'unknown')}\n"
            f"• Hour/Day: {gemini.get('usage', {}).get('hour', 0)}/{gemini.get('usage', {}).get('day', 0)}\n"
            f"• Cycle today: {gemini.get('usage', {}).get('cycle_day', 0)}\n"
            f"• Priority today: {gemini.get('usage', {}).get('priority_day', 0)}\n"
            f"• Blocked until: {gemini.get('blocked_until') or 'ready'}\n"
        )

    elif cmd == "/today":
        send_reply(chat_id, _today_summary_text())

    elif cmd == "/top":
        send_reply(chat_id, _top_items_text())

    elif cmd == "/quiz":
        threading.Thread(target=execute_quiz, args=(chat_id,), daemon=True).start()

    elif cmd.startswith("/deepdive"):
        if args:
            threading.Thread(target=execute_deepdive, args=(chat_id, args), daemon=True).start()
        else:
            send_reply(chat_id, "⚠️ Usage: `/deepdive <topic>`\nExample: `/deepdive Ransomware`")

    elif cmd.startswith("/"):
        send_reply(chat_id, HELP_TEXT, reply_markup=MAIN_KEYBOARD)

    elif text and text.strip().lower() in {"help", "commands", "menu"}:
        send_reply(chat_id, HELP_TEXT, reply_markup=MAIN_KEYBOARD)


def handle_update(update):
    """Entry point for both webhook and polling modes."""
    try:
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
        user  = msg.get("from", {})
        fname = user.get("first_name") or chat.get("title") or "Agent"
        if text and cid:
            print(f"[BOT] Incoming from {cid}: {text[:120]}")
            handle_message(text, str(cid), fname)
    except Exception as e:
        print(f"[BOT] handle_update error: {e}")


def _poll_loop():
    if not TELEGRAM_TOKEN:
        return
    url    = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    offset = None
    print("[BOT] Polling loop started")
    while True:
        try:
            params = {"timeout": 20, "allowed_updates": ["message", "channel_post", "edited_message", "edited_channel_post"]}
            if offset:
                params["offset"] = offset
            r = _session.get(url, params=params, timeout=30)
            if r.status_code == 200:
                for update in r.json().get("result", []):
                    offset = update["update_id"] + 1
                    handle_update(update)
        except requests.exceptions.Timeout:
            pass
        except Exception as e:
            print(f"[BOT] Poll error: {e}")
            time.sleep(5)
        time.sleep(0.5)


def start_listener():
    register_bot_commands()
    if HF_SPACE_URL:
        print(f"[BOT] Webhook mode — listening at {HF_SPACE_URL}/telegram/<token>")
    else:
        threading.Thread(target=_poll_loop, daemon=True).start()
        print("[BOT] Polling mode started (add HF_SPACE_URL secret for webhook mode)")
