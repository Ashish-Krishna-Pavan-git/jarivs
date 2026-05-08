"""
notifier.py
Telegram notifications — broadcasts to all subscribers.
Includes smart fuzzy-matching cooldown to prevent duplicate event spam.
Formats the 8-hour digest, daily, and new Sunday Weekly briefing.
"""

import time
import json
import os
import requests
import difflib

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

MAX_MSG  = 4000
COOLDOWN = {}

SEV_EMOJI = {
    "CRITICAL": "🚨",
    "HIGH":     "⚠️",
    "MEDIUM":   "📌",
    "LOW":      "📄",
    "MINIMAL":  "ℹ️",
}


# ─────────────────────────────────────────────────────────────
# CORE SENDER
# ─────────────────────────────────────────────────────────────

def _get_subscribers():
    subs_file = os.path.join("data", "subscribers.json")
    if os.path.exists(subs_file):
        try:
            with open(subs_file, "r") as f:
                return json.load(f)
        except:
            pass
    return [str(TELEGRAM_CHAT_ID)] if TELEGRAM_CHAT_ID else[]


def _split(text):
    if len(text) <= MAX_MSG:
        return [text]
    chunks, current =[], ""
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


def _send(text):
    if not TELEGRAM_TOKEN:
        print("[NOTIFIER] Telegram not configured")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    chunks = _split(str(text))
    success = True
    
    subscribers = set(_get_subscribers())
    if not subscribers:
        print("[NOTIFIER] No subscribers to send to.")
        return False

    # Broadcast to everyone
    for chat_id in subscribers:
        if not chat_id:
            continue
            
        for i, chunk in enumerate(chunks, 1):
            if len(chunks) > 1:
                chunk = f"[{i}/{len(chunks)}]\n{chunk}"
            try:
                r = requests.post(
                    url,
                    json={"chat_id": chat_id, "text": chunk},
                    timeout=20
                )
                if r.status_code != 200:
                    success = False
            except Exception as e:
                success = False
            time.sleep(0.5)

    return success


# ─────────────────────────────────────────────────────────────
# SMART COOLDOWN (DEDUPLICATION ACROSS SOURCES)
# ─────────────────────────────────────────────────────────────

def _is_similar(t1, t2):
    """Check if two titles are talking about the same event."""
    ratio = difflib.SequenceMatcher(None, t1, t2).ratio()
    return ratio > 0.55  # 55% character similarity is usually enough for headlines


def _on_cooldown(item, hours=12):
    title = str(item.get("title", "")).lower()
    cves  = set(item.get("cves",[]))
    now   = time.time()
    
    # 1. Cleanup old cooldowns (older than 'hours')
    keys_to_delete =[k for k, v in COOLDOWN.items() if (now - v['time']) > hours * 3600]
    for k in keys_to_delete:
        del COOLDOWN[k]

    # 2. Check against recent alerts
    for past_id, data in COOLDOWN.items():
        past_title = data['title']
        past_cves  = data['cves']
        
        # Condition A: They share a CVE number
        if cves and past_cves and cves.intersection(past_cves):
            return True
            
        # Condition B: Titles are highly similar (different news site, same story)
        if _is_similar(title, past_title):
            return True
            
    return False


def _set_cooldown(item):
    k = str(item.get("fp", time.time()))
    COOLDOWN[k] = {
        'time':  time.time(),
        'title': str(item.get("title", "")).lower(),
        'cves':  set(item.get("cves",[]))
    }


# ─────────────────────────────────────────────────────────────
# FORMATTERS
# ─────────────────────────────────────────────────────────────

def _safe_str(val):
    if isinstance(val, list):
        return ", ".join(str(x) for x in val if x)
    return str(val) if val else ""


def _format_alert(item):
    sev      = item.get("severity", "LOW")
    emoji    = SEV_EMOJI.get(sev, "")
    category = _safe_str(item.get("category", "tech")).upper()
    cves     = _safe_str(item.get("cves",[]))
    actors   = _safe_str(item.get("actors", []))
    tags     = _safe_str(item.get("tags",[]))

    summary  = item.get("summary",[])
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


def _format_digest(all_items, cycle_num, ai_digest=None):
    now   = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    lines =[]
    lines.append(f"📰 8-HOUR INTELLIGENCE BRIEFING — CYCLE {cycle_num}")
    lines.append(f"🕐 {now}")
    lines.append("━" * 40)

    if not ai_digest:
        lines.append("\n⚠️ AI processing unavailable for this cycle.")
    else:
        if ai_digest.get("headline"):
            lines.append(f"\n🎯 {ai_digest['headline']}\n")

        sections =[
            ("cybersec_updates", "🛡️ CYBERSECURITY"),
            ("ai_updates", "🧠 ARTIFICIAL INTELLIGENCE"),
            ("tech_business_updates", "💼 TECH & BUSINESS"),
            ("hardware_mobile_updates", "📱 HARDWARE & MOBILE")
        ]

        for key, title in sections:
            paras = ai_digest.get(key,[])
            if paras:
                lines.append(f"\n{title}")
                for p in paras:
                    lines.append(f"  • {p}")

        cves = ai_digest.get("key_cves",[])
        if cves:
            lines.append(f"\n🔴 KEY CVEs: {', '.join(cves)}")

        note = ai_digest.get("strategic_note")
        if note:
            lines.append(f"\n🔍 STRATEGIC NOTE:\n{note}")

    lines.append("\n" + "━" * 40)
    lines.append("\n🔗 TOP REFERENCES:")
    crit_high =[i for i in all_items if i.get("severity") in ("CRITICAL", "HIGH")]
    crit_high = sorted(crit_high, key=lambda x: 0 if x.get("severity") == "CRITICAL" else 1)

    for item in crit_high[:7]:
        sev   = item.get("severity", "")
        title = str(item.get("title", ""))[:80] + "..."
        link  = item.get("link", "")
        lines.append(f"{SEV_EMOJI.get(sev, '')} [{sev}] {title}\n  └ {link}")

    if len(crit_high) > 7:
        lines.append(f"\n...and {len(crit_high) - 7} other high-priority alerts suppressed for readability.")

    counts = {"CRITICAL":0,"HIGH":0,"MEDIUM":0,"LOW":0,"MINIMAL":0}
    for item in all_items:
        sev = item.get("severity","LOW")
        counts[sev] = counts.get(sev, 0) + 1

    stats_str = " | ".join(f"{SEV_EMOJI.get(k,'')} {k}:{v}" for k,v in counts.items() if v > 0)
    lines.append(f"\n📊 STATS: {stats_str}")
    lines.append(f"📦 Total processed: {len(all_items)}")

    return "\n".join(lines)


def _format_daily(all_items, ai_summary):
    now   = time.strftime("%Y-%m-%d", time.gmtime())
    lines =[]
    lines.append(f"🗓 DAILY REPORT — {now}")
    lines.append("━" * 45)

    if ai_summary:
        if ai_summary.get("day_headline"):
            lines.append(f"\n🎯 {ai_summary['day_headline']}\n")
        rl = ai_summary.get("risk_level","?")
        lines.append(f"⚡ RISK: {SEV_EMOJI.get(rl,'')} {rl}")
        if ai_summary.get("day_summary"):
            lines.append(f"\n{ai_summary['day_summary']}")
        lines.append("\n" + "━" * 45)
        for key, label in[
            ("escalating_threats","🔺 ESCALATING"),
            ("new_patterns",      "🔍 PATTERNS"),
            ("actor_activity",    "🎭 ACTORS"),
            ("tech_trends",       "💡 TECH TRENDS"),
            ("recommendations",   "✅ ACTIONS"),
        ]:
            items = ai_summary.get(key,[])
            if items:
                lines.append(f"\n{label}:")
                for x in items:
                    lines.append(f"  • {x}")
        cves = ai_summary.get("critical_cves",[])
        if cves:
            lines.append(f"\n🔴 KEY CVEs: {', '.join(cves)}")

    lines.append(f"\n📦 Total today: {len(all_items)} articles")
    lines.append("━" * 45)
    return "\n".join(lines)


def _format_weekly(all_items, ai_summary):
    now   = time.strftime("%Y-%m-%d", time.gmtime())
    lines =[]
    lines.append(f"🗓️ SUNDAY WEEKLY DIGEST — {now}")
    lines.append("━" * 45)

    if ai_summary:
        if ai_summary.get("day_headline"):
            lines.append(f"\n🎯 {ai_summary['day_headline']}\n")
            
        rl = ai_summary.get("risk_level", "?")
        lines.append(f"⚡ WEEKLY RISK: {SEV_EMOJI.get(rl, '')} {rl}")
        
        doom = ai_summary.get("doom",[])
        if doom:
            lines.append("\n🌋 DOOM (Threats & Breaches):")
            for d in doom:
                lines.append(f"  • {d}")
                
        bloom = ai_summary.get("bloom",[])
        if bloom:
            lines.append("\n🌸 BLOOM (Tech & Breakthroughs):")
            for b in bloom:
                lines.append(f"  • {b}")
        
        if ai_summary.get("day_summary"):
            lines.append(f"\n📝 CONCLUDING SUMMARY:\n{ai_summary['day_summary']}")
            
    lines.append("\n" + "━" * 45)
    lines.append(f"📦 Total articles analyzed this week: {len(all_items)}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def notify_immediate(item):
    sev = item.get("severity","LOW")
    if sev not in ("CRITICAL","HIGH"):
        return
    if _on_cooldown(item):
        print(f"  [NOTIFIER] Duplicate/Similar Event Suppressed: {str(item.get('title',''))[:50]}")
        return
    print(f"  [NOTIFIER] Sending {sev} alert")
    _send(_format_alert(item))
    _set_cooldown(item)


def send_digest(all_items, cycle_num, ai_digest=None):
    text = _format_digest(all_items, cycle_num, ai_digest)
    print(f"[NOTIFIER] Sending 8hr digest — cycle {cycle_num}")
    _send(text)


def send_daily_summary(all_items, ai_summary):
    text = _format_daily(all_items, ai_summary)
    print(f"[NOTIFIER] Sending daily summary")
    _send(text)


def send_weekly_summary(all_items, ai_summary):
    text = _format_weekly(all_items, ai_summary)
    print("[NOTIFIER] Sending Sunday Weekly summary")
    _send(text)


def telegram_send(text):
    _send(str(text))


def send_audio(filepath, caption="🎙️ JARVIS Daily Audio Briefing"):
    """Sends an MP3 file to all subscribers."""
    if not TELEGRAM_TOKEN or not os.path.exists(filepath):
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendAudio"
    subscribers = set(_get_subscribers())
    
    print("[NOTIFIER] Broadcasting audio podcast...")
    for chat_id in subscribers:
        if not chat_id: continue
        try:
            with open(filepath, 'rb') as audio:
                requests.post(url, data={'chat_id': chat_id, 'caption': caption}, files={'audio': audio})
        except Exception as e:
            print(f"[NOTIFIER] Failed to send audio to {chat_id}: {e}")
            
    return True