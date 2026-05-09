"""
bot_listener.py
Telegram bot: /start /stop /status /deepdive /quiz

FIXES vs original:
  - execute_deepdive uses local_call_TEXT (not JSON mode) → returns formatted markdown
  - execute_quiz uses local_call JSON mode (correct — needs structured options)
  - deepdive dossier now renders as clean readable text in Telegram
  - All commands work correctly
"""

import os
import time
import json
import threading
import requests

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from queue_manager import stats as queue_stats
from telemetry import get_stats as tele_stats
from storage import load_last_n_hours
from ai_router import local_call, local_call_text, extract_json

SUBS_FILE = os.path.join("data", "subscribers.json")


# ─────────────────────────────────────────────────────────────
# SUBSCRIBER MANAGEMENT
# ─────────────────────────────────────────────────────────────

def _load_subs() -> set:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(SUBS_FILE):
        default = [str(TELEGRAM_CHAT_ID)] if TELEGRAM_CHAT_ID else []
        _save_subs(default)
        return set(default)
    try:
        with open(SUBS_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_subs(subs):
    os.makedirs("data", exist_ok=True)
    with open(SUBS_FILE, "w") as f:
        json.dump(list(subs), f)


def send_reply(chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # Split if too long
    MAX = 4000
    chunks = [text[i:i+MAX] for i in range(0, len(text), MAX)] if len(text) > MAX else [text]
    for i, chunk in enumerate(chunks):
        for attempt in range(3):
            try:
                r = requests.post(
                    url,
                    json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
                    timeout=60,
                )
                if r.status_code == 200:
                    break
                elif r.status_code == 400:
                    # Markdown parse error — retry without parse_mode
                    requests.post(
                        url,
                        json={"chat_id": chat_id, "text": chunk},
                        timeout=60,
                    )
                    break
                time.sleep(2 ** attempt * 3)
            except Exception as e:
                print(f"[BOT] send_reply error: {e}")
                time.sleep(2 ** attempt * 3)
        time.sleep(0.3)


# ─────────────────────────────────────────────────────────────
# /deepdive  — FIXED: uses local_call_text (plain markdown output)
# ─────────────────────────────────────────────────────────────

def execute_deepdive(chat_id: str, keyword: str):
    """
    Searches local database and generates a professional intelligence dossier.
    Uses TEXT mode AI so output is formatted markdown, not raw JSON.
    """
    send_reply(chat_id, f"🔍 *Deep Dive: '{keyword}'*\nSearching intelligence database...")

    items    = load_last_n_hours(168)   # 7 days
    relevant = [i for i in items if keyword.lower() in str(i).lower()]

    if not relevant:
        send_reply(
            chat_id,
            f"⚠️ No recent intelligence found on *'{keyword}'*.\n"
            f"Try a broader term: `/deepdive Ransomware`, `/deepdive Microsoft`, `/deepdive CVE`"
        )
        return

    send_reply(chat_id, f"📚 Found *{len(relevant)}* articles. Generating dossier...")

    # Build context from the matched articles
    context = ""
    for item in relevant[:20]:
        summary = item.get("summary_text", "") or " | ".join(item.get("summary", []))
        cves    = ", ".join(item.get("cves", []))
        context += f"• [{item.get('severity','?')}] {item.get('title', '')}\n"
        if cves:
            context += f"  CVEs: {cves}\n"
        context += f"  {summary[:300]}\n\n"

    prompt = f"""You are an elite cyber intelligence analyst. Write a detailed, professional Intelligence Dossier on the topic: "{keyword}"

Base your analysis ONLY on the following recent intelligence reports:

{context}

Format your response as clean markdown:

## 🎯 Overview
[2-3 sentences on what "{keyword}" is in current threat landscape context]

## ⚠️ Key Threats & Findings
[3-4 bullet points with specific details from the reports]

## 🎭 Threat Actor Activity
[Who is involved, if applicable]

## 💥 Real-World Impact
[What this means for defenders and organizations]

## ✅ Recommendations
[2-3 concrete actions to take]

## 🔴 Related CVEs
[List any CVEs from the reports]

Keep it sharp, factual, and analytical. Under 500 words total.
Do NOT return JSON. Return clean markdown text only."""

    # Use TEXT mode — this is the critical fix (was local_call which forces JSON)
    report = local_call_text(prompt)

    if report and len(report.strip()) > 50:
        # Clean up any residual JSON brackets that may leak
        if report.strip().startswith("{"):
            report = "⚠️ AI returned unexpected format. Please try again."

        send_reply(chat_id, f"📊 *DEEP DIVE DOSSIER: {keyword.upper()}*\n\n{report}")
    else:
        send_reply(chat_id, "⚠️ AI engine failed to generate the dossier. Try again in a moment.")


# ─────────────────────────────────────────────────────────────
# /quiz  — Correct: uses JSON mode (needs structured options)
# ─────────────────────────────────────────────────────────────

def execute_quiz(chat_id: str):
    """Generates a native Telegram quiz from today's high-priority news."""
    send_reply(chat_id, "🧠 *Generating daily intel quiz...*")

    items     = load_last_n_hours(24)
    crit_high = [i for i in items if i.get("severity") in ("CRITICAL", "HIGH")]

    if len(crit_high) < 2:
        # Fall back to any items
        crit_high = items[:10]

    if not crit_high:
        send_reply(chat_id, "⚠️ Not enough intelligence data yet. Check back after the next cycle!")
        return

    context = ""
    for item in crit_high[:5]:
        summary = item.get("summary_text", "") or " | ".join(item.get("summary", []))
        context += f"• {item.get('title', '')}: {summary[:200]}\n"

    prompt = f"""Based on these recent cybersecurity and tech news items, create ONE multiple-choice trivia question.

News:
{context}

Return ONLY this exact JSON (no other text):
{{
  "question": "A specific trivia question about one of the news items above (under 200 chars)",
  "options": ["Option A", "Option B", "Option C", "Option D"],
  "correct_index": 0,
  "explanation": "Brief explanation of the correct answer citing the specific news (under 200 chars)"
}}

RULES:
- correct_index must be an integer 0-3
- The question must be answerable from the news items
- Make the wrong answers plausible but clearly incorrect
- Return ONLY the JSON object"""

    raw  = local_call(prompt)
    data = extract_json(raw)

    if data and "question" in data and len(data.get("options", [])) >= 2:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPoll"
        payload = {
            "chat_id":           chat_id,
            "question":          data["question"][:300],
            "options":           json.dumps(data["options"][:10]),
            "type":              "quiz",
            "correct_option_id": int(data.get("correct_index", 0)),
            "explanation":       str(data.get("explanation", ""))[:200],
            "is_anonymous":      False,
        }
        try:
            r = requests.post(url, data=payload, timeout=60)
            if r.status_code != 200:
                send_reply(chat_id, f"⚠️ Quiz send failed (HTTP {r.status_code}). Try again.")
        except Exception as e:
            send_reply(chat_id, f"⚠️ Quiz send error: {e}")
    else:
        send_reply(chat_id, "⚠️ AI failed to format the quiz. Try `/quiz` again.")


# ─────────────────────────────────────────────────────────────
# COMMAND ROUTER
# ─────────────────────────────────────────────────────────────

def handle_message(text: str, chat_id: str, first_name: str):
    cmd = text.lower().strip()
    subs = _load_subs()

    if cmd == "/start":
        subs.add(str(chat_id))
        _save_subs(subs)
        welcome = (
            f"👋 *Welcome to JARVIS, {first_name}!*\n\n"
            "🟢 *You are now SUBSCRIBED to intelligence alerts.*\n\n"
            "📋 *Available Commands:*\n"
            "• `/status` — System health & stats\n"
            "• `/quiz` — Daily intel knowledge quiz\n"
            "• `/deepdive <topic>` — Custom research dossier\n"
            "  _Examples: `/deepdive Ransomware` `/deepdive NVIDIA` `/deepdive CVE-2025`_\n"
            "• `/stop` — Unsubscribe from alerts\n\n"
            "🤖 JARVIS runs 24/7 — alerts auto-sent on CRITICAL/HIGH events."
        )
        send_reply(chat_id, welcome)

    elif cmd == "/stop":
        subs.discard(str(chat_id))
        _save_subs(subs)
        send_reply(chat_id, "🛑 *Unsubscribed.* You won't receive further alerts.\nSend /start to re-subscribe.")

    elif cmd == "/status":
        qs = queue_stats()
        ts = tele_stats()
        by_sev = ts.get("by_severity", {})
        sev_str = " | ".join(
            f"{k}:{v}" for k, v in by_sev.items() if v > 0
        )
        msg = (
            "📊 *JARVIS System Status*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 *Subscribers:* {len(subs)}\n"
            f"📥 *Queue pending:* {qs.get('pending', 0)}\n"
            f"✅ *Total processed:* {ts.get('total_processed', 0)}\n"
            f"🕷️ *Full scrapes:* {ts.get('total_scraped', 0)}\n"
            f"🔄 *Cycles run:* {ts.get('cycles_run', 0)}\n"
            f"📈 *By severity:* {sev_str or 'none yet'}\n"
            f"🕐 *Last cycle:* {ts.get('last_cycle_at', 'never')}"
        )
        send_reply(chat_id, msg)

    elif cmd == "/quiz":
        threading.Thread(target=execute_quiz, args=(chat_id,), daemon=True).start()

    elif cmd.startswith("/deepdive"):
        parts = text.strip().split(None, 1)   # Use original text (not lowered) for keyword
        if len(parts) > 1:
            keyword = parts[1].strip()
            threading.Thread(
                target=execute_deepdive, args=(chat_id, keyword), daemon=True
            ).start()
        else:
            send_reply(
                chat_id,
                "⚠️ Please provide a topic.\n"
                "Examples:\n"
                "• `/deepdive Ransomware`\n"
                "• `/deepdive Apple`\n"
                "• `/deepdive CVE-2025`"
            )

    else:
        # Unknown command
        if cmd.startswith("/"):
            send_reply(
                chat_id,
                "❓ Unknown command. Available: /status /quiz /deepdive <topic> /stop /start"
            )


# ─────────────────────────────────────────────────────────────
# LONG-POLL LISTENER
# ─────────────────────────────────────────────────────────────

def poll_telegram():
    if not TELEGRAM_TOKEN:
        print("[BOT] No Telegram token — listener disabled")
        return

    url    = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    offset = None
    print("[BOT] Listener started")

    while True:
        try:
            params = {"timeout": 30, "allowed_updates": ["message"]}
            if offset:
                params["offset"] = offset
            r = requests.get(url, params=params, timeout=40)
            if r.status_code == 200:
                for update in r.json().get("result", []):
                    offset = update["update_id"] + 1
                    msg    = update.get("message", {})
                    text   = msg.get("text")
                    chat   = msg.get("chat", {})
                    cid    = chat.get("id")
                    fname  = chat.get("first_name", "Agent")
                    if text and cid:
                        handle_message(text, str(cid), fname)
        except requests.exceptions.ReadTimeout:
            pass   # Normal for long-polling — just loop
        except Exception as e:
            print(f"[BOT] Poll error: {e}")
            time.sleep(5)
        time.sleep(0.5)


def start_listener():
    threading.Thread(target=poll_telegram, daemon=True).start()
    print("[BOT] Interactive listener started (/quiz, /deepdive, /status enabled)")
