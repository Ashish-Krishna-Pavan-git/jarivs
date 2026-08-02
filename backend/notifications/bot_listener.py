"""
bot_listener.py — Telegram bot handler.
FIXES:
- Deletes stale webhook before polling → eliminates 409 Conflict spam
- AI chat: any non-command message gets an intelligent JARVIS reply
- 409 handler auto-deletes webhook then resumes (self-healing)
- Polling: 15s long-poll + 40s request timeout (HF Spaces safe)
- Uses subscriber_store for HF-synced subscriber persistence
"""
import os, time, threading, requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from queue_manager import stats as queue_stats
from telemetry import get_stats as tele_stats
from storage import load_last_n_hours
from ai_router import local_call, local_call_text, extract_json
from subscriber_store import load_subscribers, subscribe, unsubscribe

from backend.utils.telegram_client import telegram_get, telegram_post

HF_SPACE_URL     = os.getenv("HF_SPACE_URL", "").rstrip("/")
_ALLOWED_UPDATES = ["message", "channel_post", "edited_message", "edited_channel_post"]


# ─── Sender ───────────────────────────────────────────────────────────────────
def send_reply(chat_id, text):
    if not TELEGRAM_TOKEN:
        return
    text = str(text)
    parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in parts:
        for parse_mode in ["Markdown", None]:
            payload = {"chat_id": chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            res = telegram_post("sendMessage", TELEGRAM_TOKEN, payload=payload, timeout=(3.0, 15.0), max_retries=1)
            if res.get("ok"):
                break
            if not res.get("ok") and parse_mode == "Markdown":
                continue
        time.sleep(0.3)


# ─── Deep Dive ────────────────────────────────────────────────────────────────
def execute_deepdive(chat_id, keyword):
    send_reply(chat_id, f"🔍 *Deep Dive: {keyword}*\nSearching intelligence database...")
    items    = load_last_n_hours(168)
    relevant = [i for i in items if keyword.lower() in str(i).lower()]
    if not relevant:
        send_reply(chat_id, f"⚠️ No data on *{keyword}* in the last 7 days.\nTry: `/deepdive Ransomware` or `/deepdive CVE`")
        return
    send_reply(chat_id, f"📚 Found *{len(relevant)}* articles — compiling dossier...")
    context = ""
    for item in relevant[:20]:
        summary = item.get("summary_text","") or " | ".join(item.get("summary",[]))
        cves    = ", ".join(item.get("cves",[]))
        context += f"[{item.get('severity','?')}] {item.get('title','')}\n"
        if cves: context += f"CVEs: {cves}\n"
        context += f"{summary[:300]}\n\n"
    prompt = f"""You are JARVIS — a senior threat intelligence analyst.
Write a formal Intelligence Dossier on: "{keyword}"

Source material:
{context}

Plain prose only — no JSON, no backticks.

EXECUTIVE OVERVIEW
[2-3 sentence threat landscape summary]

KEY FINDINGS
• [Finding 1]
• [Finding 2]
• [Finding 3]

THREAT ACTORS
[Named actors or "None identified"]

OPERATIONAL IMPACT
[Consequences for defenders]

RECOMMENDED ACTIONS
1. [Immediate]
2. [Short-term]
3. [Strategic]

CVEs: [All CVE IDs found, or "None"]
Tone: precise, professional, factual. Under 400 words."""
    report = local_call_text(prompt)
    if report and len(report.strip()) > 50 and not report.strip().startswith("{"):
        send_reply(chat_id, f"📊 *INTELLIGENCE DOSSIER: {keyword.upper()}*\n\n{report}")
    else:
        send_reply(chat_id, "⚠️ Analysis failed. Please try again.")


# ─── Quiz ─────────────────────────────────────────────────────────────────────
def execute_quiz(chat_id):
    send_reply(chat_id, "🧠 *Generating intelligence quiz...*")
    items     = load_last_n_hours(24)
    crit_high = [i for i in items if i.get("severity") in ("CRITICAL","HIGH")] or items[:10]
    if not crit_high:
        send_reply(chat_id, "⚠️ Insufficient data. Try again after the next cycle.")
        return
    context = "\n".join(f"• {i.get('title','')}: {(i.get('summary_text','') or '')[:200]}" for i in crit_high[:5])
    raw  = local_call(f"""Based on these intelligence items, create ONE multiple-choice quiz question.
Items:\n{context}
Return ONLY this JSON:
{{"question":"<under 200 chars>","options":["A","B","C","D"],"correct_index":0,"explanation":"<under 200 chars>"}}""")
    data = extract_json(raw)
    if data and "question" in data and len(data.get("options",[]))>=2:
        try:
            _session.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPoll", json={
                "chat_id":chat_id,"question":data["question"][:300],
                "options":data["options"][:10],"type":"quiz",
                "correct_option_id":int(data.get("correct_index",0)),
                "explanation":str(data.get("explanation",""))[:200],"is_anonymous":False,
            }, timeout=40)
        except Exception as e:
            send_reply(chat_id, f"⚠️ Quiz delivery error: {e}")
    else:
        send_reply(chat_id, "⚠️ Quiz generation failed. Try `/quiz` again.")


# ─── AI Chat ──────────────────────────────────────────────────────────────────
def execute_ai_chat(chat_id, user_message, first_name):
    """Any plain-text message → concise JARVIS AI reply."""
    try:
        prompt = f"""You are JARVIS — an elite technology and intelligence analyst assistant.
Answer the following question from {first_name} concisely and professionally (under 250 words).
For cybersecurity/AI/tech: provide expert-level analysis with precise terminology.
For general questions: be direct and helpful.
Do not use markdown backticks or JSON. Plain readable text only.

Question: {user_message}"""
        response = local_call_text(prompt)
        if response and len(response.strip()) > 10:
            send_reply(chat_id, f"🤖 *JARVIS:*\n\n{response.strip()}")
        else:
            send_reply(chat_id, "⚠️ Unable to process that query right now. Try rephrasing.")
    except Exception as e:
        print(f"[BOT] AI chat error: {e}")
        send_reply(chat_id, "⚠️ AI temporarily unavailable. Try `/status` or `/deepdive <topic>`.")


# ─── Command Router ───────────────────────────────────────────────────────────
def handle_message(text, chat_id, first_name):
    cmd  = text.lower().strip()
    subs = load_subscribers()

    if cmd == "/start":
        subscribe(chat_id)
        send_reply(chat_id,
            f"👋 *Welcome to JARVIS, {first_name}!*\n\n"
            "🟢 *Subscribed to intelligence alerts.*\n\n"
            "📋 *Commands:*\n"
            "• /status — System health\n"
            "• /quiz — Daily intel quiz\n"
            "• /deepdive `<topic>` — Threat dossier\n"
            "• /stop — Unsubscribe\n\n"
            "💬 *Or just type any question — JARVIS will answer.*\n\n"
            "🔔 CRITICAL/HIGH alerts: immediate\n"
            "📰 Cycle digests: 08:00 · 15:00 · 21:00 IST\n"
            "🗓 Daily report: 07:00 IST")

    elif cmd == "/stop":
        unsubscribe(chat_id)
        send_reply(chat_id, "🛑 *Unsubscribed.* Send /start to re-subscribe anytime.")

    elif cmd == "/status":
        qs   = queue_stats()
        ts   = tele_stats()
        sev  = " | ".join(f"{k}:{v}" for k,v in ts.get("by_severity",{}).items() if v>0) or "none yet"
        mode = "webhook" if HF_SPACE_URL else "polling"
        send_reply(chat_id,
            f"📊 *JARVIS System Status*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Subscribers    : {len(subs)}\n"
            f"📥 Queue pending  : {qs.get('pending',0)}\n"
            f"✅ Total processed : {ts.get('total_processed',0)}\n"
            f"🔄 Cycles run     : {ts.get('cycles_run',0)}\n"
            f"📈 By severity    : {sev}\n"
            f"🕐 Last cycle     : {ts.get('last_cycle_at','never')}\n"
            f"📡 Bot mode       : {mode}\n"
            f"🗓 Schedule (IST) : 07:00 daily · 08:00 · 15:00 · 21:00 cycles")

    elif cmd == "/quiz":
        threading.Thread(target=execute_quiz, args=(chat_id,), daemon=True).start()

    elif cmd.startswith("/deepdive"):
        parts = text.strip().split(None,1)
        if len(parts)>1:
            threading.Thread(target=execute_deepdive, args=(chat_id,parts[1].strip()), daemon=True).start()
        else:
            send_reply(chat_id, "⚠️ Usage: `/deepdive <topic>`\nExample: `/deepdive Ransomware`")

    elif cmd.startswith("/"):
        send_reply(chat_id, "❓ Commands: /status · /quiz · /deepdive `<topic>` · /start · /stop\n💬 Or just type a question.")

    else:
        # General conversation → AI reply
        threading.Thread(target=execute_ai_chat, args=(chat_id, text, first_name), daemon=True).start()


# ─── Update Entry Point ───────────────────────────────────────────────────────
def handle_update(update):
    try:
        msg = (update.get("message") or update.get("channel_post")
               or update.get("edited_message") or update.get("edited_channel_post") or {})
        text  = msg.get("text")
        chat  = msg.get("chat",{})
        cid   = chat.get("id")
        fname = chat.get("first_name") or chat.get("title") or "Agent"
        if text and cid:
            handle_message(text, str(cid), fname)
    except Exception as e:
        print(f"[BOT] handle_update error: {e}")


# ─── Webhook Delete ───────────────────────────────────────────────────────────
def _delete_webhook():
    if not TELEGRAM_TOKEN:
        return False
    res = telegram_post("deleteWebhook", TELEGRAM_TOKEN, payload={"drop_pending_updates": False}, timeout=(3.0, 12.0), max_retries=2)
    return bool(res.get("ok"))


# ─── Poll Loop ────────────────────────────────────────────────────────────────
def _poll_loop():
    if not TELEGRAM_TOKEN:
        return
    offset = None
    consecutive_409 = 0
    print("[BOT] Polling loop started (IPv4 enforced)")

    while True:
        try:
            params = {"timeout": 15, "allowed_updates": _ALLOWED_UPDATES}
            if offset:
                params["offset"] = offset
            r = telegram_get("getUpdates", TELEGRAM_TOKEN, params=params, timeout=(3.0, 25.0), max_retries=1)

            if r.get("ok"):
                consecutive_409 = 0
                for upd in r.get("result", []):
                    offset = upd["update_id"] + 1
                    threading.Thread(target=handle_update, args=(upd,), daemon=True).start()

            elif r.get("status") == 409:
                consecutive_409 += 1
                if _delete_webhook():
                    print(f"[BOT] ✓ 409 resolved — stale webhook deleted (attempt {consecutive_409})")
                    consecutive_409 = 0
                else:
                    wait = min(30 * consecutive_409, 120)
                    print(f"[BOT] 409 unresolved — waiting {wait}s")
                    time.sleep(wait)
            else:
                time.sleep(5)

        except Exception as e:
            print(f"[BOT] Poll error: {e}")
            time.sleep(5)
        time.sleep(0.3)


# ─── Start ────────────────────────────────────────────────────────────────────
def _set_commands():
    if not TELEGRAM_TOKEN:
        return
    res = telegram_post("setMyCommands", TELEGRAM_TOKEN, payload={
        "commands": [
            {"command": "start", "description": "Subscribe to JARVIS alerts"},
            {"command": "stop", "description": "Unsubscribe from alerts"},
            {"command": "status", "description": "System health & statistics"},
            {"command": "quiz", "description": "Daily intelligence quiz"},
            {"command": "deepdive", "description": "Threat research dossier on any topic"},
        ]
    }, timeout=(3.0, 15.0), max_retries=2)
    if res.get("ok"):
        print("[BOT] ✓ Commands registered")


def start_listener():
    threading.Thread(target=_set_commands, daemon=True).start()
    if HF_SPACE_URL:
        print(f"[BOT] Webhook mode — {HF_SPACE_URL}/telegram/<token>")
    else:
        if TELEGRAM_TOKEN:
            ok = _delete_webhook()
            print(f"[BOT] Pre-poll webhook clear: {'✓' if ok else 'failed (will self-heal on first 409)'}")
        threading.Thread(target=_poll_loop, daemon=True).start()
        print("[BOT] Polling mode started")
