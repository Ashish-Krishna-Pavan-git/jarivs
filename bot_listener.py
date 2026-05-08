"""
bot_listener.py
Background thread that listens to Telegram commands (/start, /stop, /status, /deepdive, /quiz)
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
from ai_router import local_call, extract_json

SUBS_FILE = os.path.join("data", "subscribers.json")

def _load_subs():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(SUBS_FILE):
        default = [str(TELEGRAM_CHAT_ID)] if TELEGRAM_CHAT_ID else[]
        _save_subs(default)
        return set(default)
    try:
        with open(SUBS_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def _save_subs(subs):
    os.makedirs("data", exist_ok=True)
    with open(SUBS_FILE, "w") as f:
        json.dump(list(subs), f)

def send_reply(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

# ─────────────────────────────────────────────────────────────
# PHASE 2: NEW INTERACTIVE COMMANDS
# ─────────────────────────────────────────────────────────────

def execute_deepdive(chat_id, keyword):
    """Searches the database and writes a custom intelligence dossier."""
    send_reply(chat_id, f"🔍 *Initiating Deep Dive on '{keyword}'*...\nMining local database...")
    
    # Load last 7 days of articles
    items = load_last_n_hours(168)
    
    # Filter for the keyword
    relevant = [i for i in items if keyword.lower() in str(i).lower()]
    
    if not relevant:
        send_reply(chat_id, f"⚠️ Not enough recent intelligence found on '{keyword}'. Try a broader term (e.g., 'Apple', 'Ransomware', 'China').")
        return
        
    send_reply(chat_id, f"📚 Found {len(relevant)} related articles. Generating AI Dossier...")
    
    # Combine summaries for the AI
    context = ""
    for i in relevant[:25]: # Limit to top 25 so we don't overload prompt
        context += f"- {i.get('title')}: {i.get('summary_text', '')}\n"
        
    prompt = f"""You are an elite cyber intelligence analyst. 
Write a highly detailed, professional Intelligence Dossier on "{keyword}" based ONLY on these recent reports:
{context}

Format your response using Markdown:
- Use ## Headers for sections (e.g., Overview, Key Threats, Impact).
- Use bullet points.
- Keep it under 400 words. Be sharp, factual, and analytical."""

    report = local_call(prompt)
    
    if report:
        send_reply(chat_id, f"📊 *DEEP DIVE DOSSIER: {keyword.upper()}*\n\n{report}")
    else:
        send_reply(chat_id, "⚠️ AI Engine failed to generate the dossier.")


def execute_quiz(chat_id):
    """Generates a native Telegram Quiz based on today's news."""
    send_reply(chat_id, "🧠 *Generating your daily intel quiz...*")
    
    # Get high priority news from the last 24 hours
    items = load_last_n_hours(24)
    crit_high =[i for i in items if i.get("severity") in ("CRITICAL", "HIGH")]
    
    if not crit_high:
        send_reply(chat_id, "Not enough critical news today to generate a quiz! Check back later.")
        return
        
    context = ""
    for i in crit_high[:5]: # Take top 5 news items
        context += f"- {i.get('title')}: {i.get('summary_text', '')}\n"

    prompt = f"""Based on the following recent news, create ONE multiple-choice trivia question.
News:
{context}

Return exactly this JSON format:
{{
  "question": "The trivia question (under 200 chars)",
  "options":["Option A", "Option B", "Option C", "Option D"],
  "correct_index": 0, 
  "explanation": "A short sentence explaining the correct answer (under 150 chars)"
}}
NOTE: correct_index must be an integer between 0 and 3."""

    raw = local_call(prompt)
    data = extract_json(raw)
    
    if data and "question" in data and len(data.get("options",[])) >= 2:
        # Use Telegram's native sendPoll API
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPoll"
        payload = {
            "chat_id": chat_id,
            "question": data["question"][:300],
            "options": json.dumps(data["options"][:10]),
            "type": "quiz",
            "correct_option_id": data["correct_index"],
            "explanation": data["explanation"][:200],
            "is_anonymous": False
        }
        requests.post(url, data=payload)
    else:
        send_reply(chat_id, "⚠️ AI failed to format the quiz correctly.")

# ─────────────────────────────────────────────────────────────
# ROUTER
# ─────────────────────────────────────────────────────────────

def handle_message(text, chat_id, first_name):
    text = text.lower().strip()
    subs = _load_subs()

    if text == "/start":
        subs.add(str(chat_id))
        _save_subs(subs)
        welcome = (
            f"👋 *Welcome to JARVIS, {first_name}!*\n\n"
            "🟢 *You are now SUBSCRIBED to alerts.*\n\n"
            "📋 *Commands:*\n"
            "• `/status` - Check system health\n"
            "• `/quiz` - Test your knowledge on today's intel\n"
            "• `/deepdive <topic>` - Ask JARVIS to write a custom research report (e.g. `/deepdive Microsoft`)\n"
            "• `/stop` - Unsubscribe"
        )
        send_reply(chat_id, welcome)

    elif text == "/stop":
        if str(chat_id) in subs:
            subs.remove(str(chat_id))
            _save_subs(subs)
        send_reply(chat_id, "🛑 Unsubscribed.")

    elif text == "/status":
        qs = queue_stats()
        ts = tele_stats()
        msg = (
            "📊 *JARVIS System Status*\n"
            f"👥 *Subscribers:* {len(subs)}\n"
            f"📥 *Queue:* {qs.get('pending', 0)}\n"
            f"✅ *Processed:* {ts.get('total_processed', 0)}"
        )
        send_reply(chat_id, msg)
        
    elif text == "/quiz":
        threading.Thread(target=execute_quiz, args=(chat_id,)).start()

    elif text.startswith("/deepdive"):
        parts = text.split(" ", 1)
        if len(parts) > 1:
            keyword = parts[1].strip()
            # Run in a separate thread so it doesn't block the listener loop
            threading.Thread(target=execute_deepdive, args=(chat_id, keyword)).start()
        else:
            send_reply(chat_id, "⚠️ Please provide a topic. Example: `/deepdive Apple`")

def poll_telegram():
    if not TELEGRAM_TOKEN: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    offset = None
    while True:
        try:
            params = {"timeout": 30}
            if offset: params["offset"] = offset
            r = requests.get(url, params=params, timeout=40)
            if r.status_code == 200:
                for update in r.json().get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    text = msg.get("text")
                    chat_id = msg.get("chat", {}).get("id")
                    if text and chat_id:
                        handle_message(text, str(chat_id), msg.get("chat", {}).get("first_name", "Agent"))
        except Exception:
            time.sleep(5)
        time.sleep(1)

def start_listener():
    threading.Thread(target=poll_telegram, daemon=True).start()
    print("[BOT] Interactive listener started (/quiz, /deepdive enabled)")