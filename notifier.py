"""
notifier.py — Telegram broadcaster.
FIXES:
- SSL EOF errors now get longer backoff (was treating them same as generic connection errors)
- MAX_RETRIES increased to 5 for digests/daily (HF → Telegram can be flaky)
- send_audio reopens file fresh on each attempt
- All formatting updated to professional, structured style
- Uses subscriber_store consistently
"""

import time, json, os, threading, requests, difflib
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from subscriber_store import load_subscribers

MAX_MSG      = 4000
SEND_TIMEOUT = 60
MAX_RETRIES  = 5       # Increased from 3 — HF→Telegram can need more attempts
COOLDOWN: dict = {}

SEV_EMOJI = {"CRITICAL":"🚨","HIGH":"⚠️","MEDIUM":"📌","LOW":"📄","MINIMAL":"ℹ️"}


def _get_subscribers():
    try:
        subs = load_subscribers()
        return list(subs) if subs else ([str(TELEGRAM_CHAT_ID)] if TELEGRAM_CHAT_ID else [])
    except Exception:
        return [str(TELEGRAM_CHAT_ID)] if TELEGRAM_CHAT_ID else []


def _split(text):
    if len(text) <= MAX_MSG: return [text]
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur)+len(line)+1 > MAX_MSG:
            if cur: chunks.append(cur.strip())
            cur = line+"\n"
        else:
            cur += line+"\n"
    if cur.strip(): chunks.append(cur.strip())
    return chunks


def _send_one(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for attempt in range(1, MAX_RETRIES+1):
        try:
            r = requests.post(url, json={"chat_id":chat_id,"text":text}, timeout=SEND_TIMEOUT)
            if r.status_code == 200:
                return True
            elif r.status_code == 429:
                ra = r.json().get("parameters",{}).get("retry_after",30)
                print(f"[NOTIFIER] Rate limited — waiting {ra}s")
                time.sleep(ra)
            elif r.status_code in (400,403):
                print(f"[NOTIFIER] Permanent error {r.status_code} for {chat_id}")
                return False
            else:
                time.sleep(2**attempt)
        except requests.exceptions.SSLError as e:
            # SSL EOF on HF Spaces — longer backoff needed
            wait = 2**attempt * 8   # 16s, 32s, 64s, 128s, 256s
            print(f"[NOTIFIER] SSL error (attempt {attempt}/{MAX_RETRIES}), retry in {wait}s: {str(e)[:80]}")
            time.sleep(wait)
        except requests.exceptions.ReadTimeout:
            wait = 2**attempt * 5
            print(f"[NOTIFIER] Read timeout (attempt {attempt}/{MAX_RETRIES}), retry in {wait}s")
            time.sleep(wait)
        except requests.exceptions.ConnectionError as e:
            wait = 2**attempt * 5
            print(f"[NOTIFIER] Connection error (attempt {attempt}/{MAX_RETRIES}), retry in {wait}s")
            time.sleep(wait)
        except Exception as e:
            print(f"[NOTIFIER] Unexpected error: {e}")
            return False
    print(f"[NOTIFIER] ✗ All {MAX_RETRIES} retries failed for {chat_id}")
    return False


def _send(text):
    if not TELEGRAM_TOKEN: return False
    subscribers = set(_get_subscribers())
    if not subscribers: return False
    chunks = _split(str(text))
    success = False
    for cid in subscribers:
        if not cid: continue
        for i, chunk in enumerate(chunks,1):
            payload = f"[{i}/{len(chunks)}]\n{chunk}" if len(chunks)>1 else chunk
            if _send_one(cid, payload): success = True
            time.sleep(0.3)
    return success


def _send_async(text):
    threading.Thread(target=_send, args=(text,), daemon=True).start()


# ── Cooldown ──────────────────────────────────────────────────────────────────
def _similar(t1, t2):
    return difflib.SequenceMatcher(None, t1, t2).ratio() > 0.55

def _on_cooldown(item, hours=12):
    title = str(item.get("title","")).lower()
    cves  = set(item.get("cves",[]))
    now   = time.time()
    stale = [k for k,v in COOLDOWN.items() if now-v["time"]>hours*3600]
    for k in stale: del COOLDOWN[k]
    for data in COOLDOWN.values():
        if cves and data["cves"] and cves.intersection(data["cves"]): return True
        if _similar(title, data["title"]): return True
    return False

def _set_cooldown(item):
    COOLDOWN[str(item.get("fp",time.time()))] = {
        "time":time.time(), "title":str(item.get("title","")).lower(),
        "cves":set(item.get("cves",[]))}


# ── Formatters ────────────────────────────────────────────────────────────────
def _safe_str(val):
    if isinstance(val,list): return ", ".join(str(x) for x in val if x)
    return str(val) if val else ""


def _format_alert(item):
    sev      = item.get("severity","LOW")
    emoji    = SEV_EMOJI.get(sev,"")
    category = _safe_str(item.get("category","tech")).upper()
    cves     = _safe_str(item.get("cves",[]))
    actors   = _safe_str(item.get("actors",[]))
    tags     = _safe_str(item.get("tags",[]))
    summary  = item.get("summary",[])
    summary_str = "\n".join(f"  • {s}" for s in summary if isinstance(s,str)) if isinstance(summary,list) else f"  • {summary}"

    msg  = f"{emoji} {sev} ALERT\n{'━'*35}\n"
    msg += f"📰 {item.get('title','')}\n\n"
    msg += f"📡 Source    : {item.get('source','?')}\n"
    msg += f"🏷 Category  : {category}\n"
    if cves:   msg += f"🔴 CVEs      : {cves}\n"
    if actors: msg += f"🎭 Actors    : {actors}\n"
    if tags:   msg += f"🔖 Tags      : {tags}\n"
    msg += f"\n📋 Intelligence Assessment:\n{summary_str}\n\n"
    msg += f"🔗 {item.get('link','')}"
    return msg


def _format_digest(all_items, cycle_num, ai_digest=None):
    now   = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    lines = [f"📰 JARVIS INTELLIGENCE BRIEFING — CYCLE {cycle_num}", f"🕐 {now}", "━"*40]

    if not ai_digest:
        lines.append("\n⚠️ AI synthesis unavailable for this cycle.")
    else:
        if ai_digest.get("headline"):
            lines.append(f"\n🎯 {ai_digest['headline']}\n")
        for key, title in [
            ("cybersec_updates","🛡️ CYBERSECURITY INTELLIGENCE"),
            ("ai_updates","🧠 ARTIFICIAL INTELLIGENCE"),
            ("tech_business_updates","💼 TECHNOLOGY & BUSINESS"),
            ("hardware_mobile_updates","📱 HARDWARE & MOBILE"),
        ]:
            paras = ai_digest.get(key,[])
            if paras:
                lines.append(f"\n{title}")
                for p in paras: lines.append(f"  • {p}")
        cves = ai_digest.get("key_cves",[])
        if cves: lines.append(f"\n🔴 KEY CVEs: {', '.join(cves)}")
        if ai_digest.get("strategic_note"):
            lines.append(f"\n🔍 STRATEGIC ASSESSMENT:\n{ai_digest['strategic_note']}")

    lines.append("\n"+"━"*40+"\n🔗 HIGH-PRIORITY REFERENCES:")
    crit_high = sorted([i for i in all_items if i.get("severity") in ("CRITICAL","HIGH")],
                       key=lambda x: 0 if x.get("severity")=="CRITICAL" else 1)
    for item in crit_high[:7]:
        sev = item.get("severity","")
        lines.append(f"{SEV_EMOJI.get(sev,'')} [{sev}] {str(item.get('title',''))[:80]}…\n  └ {item.get('link','')}")
    if len(crit_high)>7:
        lines.append(f"\n…and {len(crit_high)-7} additional high-priority items in this cycle.")

    counts = {}
    for item in all_items:
        s = item.get("severity","LOW"); counts[s] = counts.get(s,0)+1
    stats_str = " | ".join(f"{SEV_EMOJI.get(k,'')} {k}:{v}" for k,v in counts.items() if v>0)
    lines.append(f"\n📊 CYCLE STATISTICS: {stats_str}")
    lines.append(f"📦 Articles processed this cycle: {len(all_items)}")
    return "\n".join(lines)


def _format_daily(all_items, ai_summary):
    now   = time.strftime("%Y-%m-%d", time.gmtime())
    lines = [f"🗓 JARVIS DAILY INTELLIGENCE REPORT — {now}", "━"*45]

    if ai_summary:
        if ai_summary.get("day_headline"):
            lines.append(f"\n🎯 {ai_summary['day_headline']}\n")
        rl = ai_summary.get("risk_level","?")
        lines.append(f"⚡ OVERALL RISK LEVEL: {SEV_EMOJI.get(rl,'')} {rl}")
        if ai_summary.get("day_summary"):
            lines.append(f"\n{ai_summary['day_summary']}")
        lines.append("\n"+"━"*45)
        for key, label in [
            ("escalating_threats","🔺 ESCALATING THREATS"),
            ("new_patterns","🔍 OBSERVED PATTERNS"),
            ("actor_activity","🎭 THREAT ACTOR ACTIVITY"),
            ("tech_trends","💡 TECHNOLOGY TRENDS"),
            ("recommendations","✅ RECOMMENDED ACTIONS"),
        ]:
            items = ai_summary.get(key,[])
            if items:
                lines.append(f"\n{label}:")
                for x in items: lines.append(f"  • {x}")
        cves = ai_summary.get("critical_cves",[])
        if cves: lines.append(f"\n🔴 CRITICAL CVEs: {', '.join(cves)}")
    else:
        lines.append("\n⚠️ AI synthesis unavailable — statistics report only.")

    lines.append(f"\n{'━'*45}\n📊 DAY STATISTICS: {len(all_items)} articles processed")
    return "\n".join(lines)


def _format_weekly(all_items, ai_summary):
    now   = time.strftime("%Y-%m-%d", time.gmtime())
    lines = [f"🗓️ JARVIS SUNDAY WEEKLY DIGEST — {now}", "━"*45]
    if ai_summary:
        if ai_summary.get("day_headline"):
            lines.append(f"\n🎯 {ai_summary['day_headline']}\n")
        rl = ai_summary.get("risk_level","?")
        lines.append(f"⚡ WEEKLY RISK POSTURE: {SEV_EMOJI.get(rl,'')} {rl}")
        if ai_summary.get("doom"):
            lines.append("\n🌋 DOOM — Threats, Breaches & Vulnerabilities:")
            for d in ai_summary["doom"]: lines.append(f"  • {d}")
        if ai_summary.get("bloom"):
            lines.append("\n🌸 BLOOM — Innovations, Wins & Breakthroughs:")
            for b in ai_summary["bloom"]: lines.append(f"  • {b}")
        if ai_summary.get("key_cves"):
            lines.append(f"\n🔴 WEEK'S CRITICAL CVEs: {', '.join(ai_summary['key_cves'])}")
        if ai_summary.get("day_summary"):
            lines.append(f"\n📝 STRATEGIC OUTLOOK:\n{ai_summary['day_summary']}")
    lines.append(f"\n{'━'*45}\n📦 Total articles analysed this week: {len(all_items)}")
    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────
def notify_immediate(item):
    sev = item.get("severity","LOW")
    if sev not in ("CRITICAL","HIGH"): return
    if _on_cooldown(item):
        print(f"  [NOTIFIER] Duplicate suppressed: {str(item.get('title',''))[:50]}")
        return
    print(f"  [NOTIFIER] 🚨 Sending {sev} alert (async)")
    _send_async(_format_alert(item))
    _set_cooldown(item)

def send_digest(all_items, cycle_num, ai_digest=None):
    print(f"[NOTIFIER] Sending 8hr digest — cycle {cycle_num}")
    _send(_format_digest(all_items, cycle_num, ai_digest))

def send_daily_summary(all_items, ai_summary):
    print("[NOTIFIER] Sending daily report")
    _send(_format_daily(all_items, ai_summary))

def send_weekly_summary(all_items, ai_summary):
    print("[NOTIFIER] Sending Sunday weekly digest")
    _send(_format_weekly(all_items, ai_summary))

def telegram_send(text):
    _send(str(text))

def send_audio(filepath, caption="🎙️ JARVIS Daily Intelligence Audio Briefing"):
    if not TELEGRAM_TOKEN or not os.path.exists(filepath): return False
    url         = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendAudio"
    subscribers = set(_get_subscribers())
    for cid in subscribers:
        if not cid: continue
        for attempt in range(MAX_RETRIES):
            try:
                with open(filepath,"rb") as audio:   # FIX: reopen on each retry
                    r = requests.post(url, data={"chat_id":cid,"caption":caption},
                                      files={"audio":audio}, timeout=SEND_TIMEOUT)
                if r.status_code == 200: break
                time.sleep(2**attempt*3)
            except requests.exceptions.SSLError as e:
                time.sleep(2**attempt*8)
            except Exception as e:
                print(f"[NOTIFIER] Audio send error: {e}")
                time.sleep(2**attempt*3)
    return True