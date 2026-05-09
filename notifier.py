"""
notifier.py
Telegram broadcaster — sends to all subscribers.

FIXES vs original:
  - Timeout raised 20s → 60s  (HF Spaces has slow egress to Telegram)
  - 3 retries with exponential backoff per chunk
  - Immediate alerts sent in a daemon thread (never blocks AI processing)
  - Smart duplicate cooldown (CVE + title fuzzy match)
  - All formatters preserved and improved
"""

import time
import os
import threading
import requests
import difflib

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from subscriber_store import load_subscribers, save_subscribers

MAX_MSG       = 4000
SEND_TIMEOUT  = 60        # seconds — was 20, too short for HF egress
MAX_RETRIES   = 3
COOLDOWN: dict = {}

SEV_EMOJI = {
    "CRITICAL": "🚨",
    "HIGH":     "⚠️",
    "MEDIUM":   "📌",
    "LOW":      "📄",
    "MINIMAL":  "ℹ️",
}


# ─────────────────────────────────────────────────────────────
# SUBSCRIBER MANAGEMENT
# ─────────────────────────────────────────────────────────────

def _get_subscribers():
    try:
        subs = load_subscribers()
        return sorted(subs)
    except Exception:
        return [str(TELEGRAM_CHAT_ID)] if TELEGRAM_CHAT_ID else []


# ─────────────────────────────────────────────────────────────
# CORE SENDER  (with retry + backoff)
# ─────────────────────────────────────────────────────────────

def _split(text: str) -> list:
    if len(text) <= MAX_MSG:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_MSG:
            if current:
                chunks.append(current.strip())
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _send_one(chat_id: str, text: str) -> bool:
    """Send one message chunk to one chat_id. Retries up to MAX_RETRIES times."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.post(
                url,
                json={"chat_id": chat_id, "text": text},
                timeout=SEND_TIMEOUT,
            )
            if r.status_code == 200:
                return True
            elif r.status_code == 429:
                retry_after = r.json().get("parameters", {}).get("retry_after", 30)
                print(f"[NOTIFIER] Rate limited — waiting {retry_after}s")
                time.sleep(retry_after)
            elif r.status_code in (400, 403):
                # Bad chat_id or bot blocked — don't retry
                print(f"[NOTIFIER] Permanent error {r.status_code} for {chat_id}")
                subscribers = load_subscribers()
                if str(chat_id) in subscribers:
                    subscribers.discard(str(chat_id))
                    save_subscribers(subscribers)
                return False
            else:
                wait = 2 ** attempt
                print(f"[NOTIFIER] HTTP {r.status_code}, retry {attempt}/{MAX_RETRIES} in {wait}s")
                time.sleep(wait)
        except requests.exceptions.ReadTimeout:
            wait = 2 ** attempt * 5   # 10s, 20s, 40s
            print(f"[NOTIFIER] ⚠️ Read timeout (attempt {attempt}/{MAX_RETRIES}), retry in {wait}s")
            time.sleep(wait)
        except requests.exceptions.ConnectionError as e:
            wait = 2 ** attempt * 5
            print(f"[NOTIFIER] ⚠️ Connection error: {e}, retry in {wait}s")
            time.sleep(wait)
        except Exception as e:
            print(f"[NOTIFIER] ⚠️ Unexpected error: {e}")
            return False

    print(f"[NOTIFIER] ✗ All {MAX_RETRIES} retries failed for chat {chat_id}")
    return False


def _send(text: str) -> bool:
    """Broadcast to all subscribers. Returns True if at least one succeeded."""
    if not TELEGRAM_TOKEN:
        print("[NOTIFIER] Telegram not configured")
        return False

    subscribers = set(_get_subscribers())
    if not subscribers:
        print("[NOTIFIER] No subscribers")
        return False

    chunks = _split(str(text))
    any_success = False

    for chat_id in subscribers:
        if not chat_id:
            continue
        for i, chunk in enumerate(chunks, 1):
            payload = f"[{i}/{len(chunks)}]\n{chunk}" if len(chunks) > 1 else chunk
            if _send_one(chat_id, payload):
                any_success = True
            time.sleep(0.3)   # small gap between chunks

    return any_success


def _send_async(text: str):
    """Fire-and-forget: send in daemon thread so it never blocks processing."""
    threading.Thread(target=_send, args=(text,), daemon=True).start()


# ─────────────────────────────────────────────────────────────
# DUPLICATE COOLDOWN
# ─────────────────────────────────────────────────────────────

def _is_similar(t1: str, t2: str) -> bool:
    return difflib.SequenceMatcher(None, t1, t2).ratio() > 0.55


def _on_cooldown(item: dict, hours: int = 12) -> bool:
    title = str(item.get("title", "")).lower()
    cves  = set(item.get("cves", []))
    now   = time.time()

    # Clean expired entries
    stale = [k for k, v in COOLDOWN.items() if now - v["time"] > hours * 3600]
    for k in stale:
        del COOLDOWN[k]

    for data in COOLDOWN.values():
        if cves and data["cves"] and cves.intersection(data["cves"]):
            return True
        if _is_similar(title, data["title"]):
            return True

    return False


def _set_cooldown(item: dict):
    k = str(item.get("fp", time.time()))
    COOLDOWN[k] = {
        "time":  time.time(),
        "title": str(item.get("title", "")).lower(),
        "cves":  set(item.get("cves", [])),
    }


# ─────────────────────────────────────────────────────────────
# FORMATTERS
# ─────────────────────────────────────────────────────────────

def _safe_str(val) -> str:
    if isinstance(val, list):
        return ", ".join(str(x) for x in val if x)
    return str(val) if val else ""


def _format_alert(item: dict) -> str:
    sev      = item.get("severity", "LOW")
    emoji    = SEV_EMOJI.get(sev, "")
    category = _safe_str(item.get("category", "tech")).upper()
    cves     = _safe_str(item.get("cves", []))
    actors   = _safe_str(item.get("actors", []))
    tags     = _safe_str(item.get("tags", []))

    summary = item.get("summary", [])
    if isinstance(summary, list):
        summary_str = "\n".join(f"  • {s}" for s in summary if isinstance(s, str))
    else:
        summary_str = f"  • {summary}"

    msg  = f"{emoji} {sev} ALERT\n"
    msg += "━" * 35 + "\n"
    msg += f"📰 {item.get('title', '')}\n\n"
    msg += f"📡 Source   : {item.get('source', '?')}\n"
    msg += f"🏷 Category : {category}\n"
    if cves:
        msg += f"🔴 CVEs     : {cves}\n"
    if actors:
        msg += f"🎭 Actors   : {actors}\n"
    if tags:
        msg += f"🔖 Tags     : {tags}\n"
    msg += "\n📋 Analysis:\n" + summary_str + "\n\n"
    msg += f"🔗 {item.get('link', '')}"
    return msg


def _format_digest(all_items: list, cycle_num: int, ai_digest: dict = None) -> str:
    now   = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    lines = []
    lines.append(f"📰 8-HOUR INTELLIGENCE BRIEFING — CYCLE {cycle_num}")
    lines.append(f"🕐 {now}")
    lines.append("━" * 40)

    if not ai_digest:
        lines.append("\n⚠️ AI digest unavailable for this cycle.")
    else:
        if ai_digest.get("headline"):
            lines.append(f"\n🎯 {ai_digest['headline']}\n")

        sections = [
            ("cybersec_updates",       "🛡️ CYBERSECURITY"),
            ("ai_updates",             "🧠 ARTIFICIAL INTELLIGENCE"),
            ("tech_business_updates",  "💼 TECH & BUSINESS"),
            ("hardware_mobile_updates","📱 HARDWARE & MOBILE"),
        ]
        for key, title in sections:
            paras = ai_digest.get(key, [])
            if paras:
                lines.append(f"\n{title}")
                for p in paras:
                    lines.append(f"  • {p}")

        cves = ai_digest.get("key_cves", [])
        if cves:
            lines.append(f"\n🔴 KEY CVEs: {', '.join(cves)}")

        note = ai_digest.get("strategic_note")
        if note:
            lines.append(f"\n🔍 STRATEGIC NOTE:\n{note}")

    lines.append("\n" + "━" * 40)
    lines.append("\n🔗 TOP REFERENCES:")

    crit_high = sorted(
        [i for i in all_items if i.get("severity") in ("CRITICAL", "HIGH")],
        key=lambda x: 0 if x.get("severity") == "CRITICAL" else 1,
    )
    for item in crit_high[:7]:
        sev   = item.get("severity", "")
        title = str(item.get("title", ""))[:80] + "…"
        link  = item.get("link", "")
        lines.append(f"{SEV_EMOJI.get(sev,'')} [{sev}] {title}\n  └ {link}")

    if len(crit_high) > 7:
        lines.append(f"\n…and {len(crit_high) - 7} more high-priority alerts in the digest.")

    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "MINIMAL": 0}
    for item in all_items:
        counts[item.get("severity", "LOW")] = counts.get(item.get("severity", "LOW"), 0) + 1

    stats_str = " | ".join(
        f"{SEV_EMOJI.get(k,'')} {k}:{v}" for k, v in counts.items() if v > 0
    )
    lines.append(f"\n📊 STATS: {stats_str}")
    lines.append(f"📦 Total processed this cycle: {len(all_items)}")
    return "\n".join(lines)


def _format_daily(all_items: list, ai_summary: dict) -> str:
    now   = time.strftime("%Y-%m-%d", time.gmtime())
    lines = []
    lines.append(f"🗓 DAILY REPORT — {now}")
    lines.append("━" * 45)

    if ai_summary:
        if ai_summary.get("day_headline"):
            lines.append(f"\n🎯 {ai_summary['day_headline']}\n")
        rl = ai_summary.get("risk_level", "?")
        lines.append(f"⚡ RISK: {SEV_EMOJI.get(rl, '')} {rl}")
        if ai_summary.get("day_summary"):
            lines.append(f"\n{ai_summary['day_summary']}")
        lines.append("\n" + "━" * 45)

        for key, label in [
            ("escalating_threats", "🔺 ESCALATING THREATS"),
            ("new_patterns",       "🔍 OBSERVED PATTERNS"),
            ("actor_activity",     "🎭 THREAT ACTORS"),
            ("tech_trends",        "💡 TECH TRENDS"),
            ("recommendations",    "✅ RECOMMENDATIONS"),
        ]:
            items = ai_summary.get(key, [])
            if items:
                lines.append(f"\n{label}:")
                for x in items:
                    lines.append(f"  • {x}")

        cves = ai_summary.get("critical_cves", [])
        if cves:
            lines.append(f"\n🔴 KEY CVEs: {', '.join(cves)}")

    lines.append(f"\n📦 Total articles today: {len(all_items)}")
    lines.append("━" * 45)
    return "\n".join(lines)


def _format_weekly(all_items: list, ai_summary: dict) -> str:
    now   = time.strftime("%Y-%m-%d", time.gmtime())
    lines = []
    lines.append(f"🗓️ SUNDAY WEEKLY DIGEST — {now}")
    lines.append("━" * 45)

    if ai_summary:
        if ai_summary.get("day_headline"):
            lines.append(f"\n🎯 {ai_summary['day_headline']}\n")
        rl = ai_summary.get("risk_level", "?")
        lines.append(f"⚡ WEEKLY RISK: {SEV_EMOJI.get(rl, '')} {rl}")

        doom = ai_summary.get("doom", [])
        if doom:
            lines.append("\n🌋 DOOM (Threats & Breaches):")
            for d in doom:
                lines.append(f"  • {d}")

        bloom = ai_summary.get("bloom", [])
        if bloom:
            lines.append("\n🌸 BLOOM (Tech & Breakthroughs):")
            for b in bloom:
                lines.append(f"  • {b}")

        if ai_summary.get("day_summary"):
            lines.append(f"\n📝 WEEK SUMMARY:\n{ai_summary['day_summary']}")

    lines.append("\n" + "━" * 45)
    lines.append(f"📦 Total articles this week: {len(all_items)}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def notify_immediate(item: dict):
    """Send an immediate CRITICAL/HIGH alert. Non-blocking — runs in background thread."""
    sev = item.get("severity", "LOW")
    if sev not in ("CRITICAL", "HIGH"):
        return
    if _on_cooldown(item):
        print(f"  [NOTIFIER] Duplicate suppressed: {str(item.get('title',''))[:50]}")
        return

    print(f"  [NOTIFIER] 🚨 Sending {sev} alert (async)")
    _send_async(_format_alert(item))
    _set_cooldown(item)


def send_digest(all_items: list, cycle_num: int, ai_digest: dict = None):
    text = _format_digest(all_items, cycle_num, ai_digest)
    print(f"[NOTIFIER] Sending 8hr digest — cycle {cycle_num}")
    _send(text)   # Blocking is fine here — we're between cycles


def send_daily_summary(all_items: list, ai_summary: dict):
    text = _format_daily(all_items, ai_summary)
    print("[NOTIFIER] Sending daily summary")
    _send(text)


def send_weekly_summary(all_items: list, ai_summary: dict):
    text = _format_weekly(all_items, ai_summary)
    print("[NOTIFIER] Sending Sunday Weekly summary")
    _send(text)


def telegram_send(text: str):
    """Generic send for bot commands etc."""
    _send(str(text))


def send_audio(filepath: str, caption: str = "🎙️ JARVIS Daily Audio Briefing"):
    """Send an MP3 file to all subscribers."""
    if not TELEGRAM_TOKEN or not os.path.exists(filepath):
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendAudio"
    subscribers = set(_get_subscribers())

    for chat_id in subscribers:
        if not chat_id:
            continue
        for attempt in range(MAX_RETRIES):
            try:
                with open(filepath, "rb") as audio:
                    r = requests.post(
                        url,
                        data={"chat_id": chat_id, "caption": caption},
                        files={"audio": audio},
                        timeout=SEND_TIMEOUT,
                    )
                if r.status_code == 200:
                    break
                time.sleep(2 ** attempt * 3)
            except Exception as e:
                print(f"[NOTIFIER] Audio send error: {e}")
                time.sleep(2 ** attempt * 3)

    return True
