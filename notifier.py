"""
notifier.py — Telegram broadcaster with story-driven report formatting.
- SSL-aware retry with longer backoffs (HF → Telegram SSL EOF errors)
- MAX_RETRIES = 5 for reliability
- All formats: engaging, narrative, informative — not just bullet lists
- send_audio: reopens file on each retry
"""

import time, os, threading, requests, difflib
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from subscriber_store import load_subscribers

MAX_MSG      = 4000
SEND_TIMEOUT = 60
MAX_RETRIES  = 5
COOLDOWN: dict = {}
SEV_EMOJI = {"CRITICAL":"🚨","HIGH":"⚠️","MEDIUM":"📌","LOW":"📄","MINIMAL":"ℹ️"}


def _get_subs():
    try:
        s = load_subscribers()
        return list(s) if s else ([str(TELEGRAM_CHAT_ID)] if TELEGRAM_CHAT_ID else [])
    except:
        return [str(TELEGRAM_CHAT_ID)] if TELEGRAM_CHAT_ID else []


def _split(text):
    if len(text)<=MAX_MSG: return [text]
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur)+len(line)+1>MAX_MSG:
            if cur: chunks.append(cur.strip())
            cur = line+"\n"
        else: cur += line+"\n"
    if cur.strip(): chunks.append(cur.strip())
    return chunks


def _send_one(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for attempt in range(1, MAX_RETRIES+1):
        try:
            r = requests.post(url, json={"chat_id":chat_id,"text":text}, timeout=SEND_TIMEOUT)
            if r.status_code==200: return True
            if r.status_code==429:
                ra=r.json().get("parameters",{}).get("retry_after",30)
                print(f"[NOTIFIER] Rate limited — wait {ra}s"); time.sleep(ra)
            elif r.status_code in (400,403):
                print(f"[NOTIFIER] Permanent error {r.status_code} for {chat_id}"); return False
            else: time.sleep(2**attempt)
        except requests.exceptions.SSLError as e:
            w=2**attempt*8
            print(f"[NOTIFIER] SSL error attempt {attempt}/{MAX_RETRIES}, retry {w}s"); time.sleep(w)
        except requests.exceptions.ReadTimeout:
            w=2**attempt*5
            print(f"[NOTIFIER] Timeout attempt {attempt}/{MAX_RETRIES}, retry {w}s"); time.sleep(w)
        except requests.exceptions.ConnectionError as e:
            w=2**attempt*5
            print(f"[NOTIFIER] Conn error attempt {attempt}/{MAX_RETRIES}, retry {w}s"); time.sleep(w)
        except Exception as e:
            print(f"[NOTIFIER] Error: {e}"); return False
    print(f"[NOTIFIER] ✗ All {MAX_RETRIES} retries failed for {chat_id}"); return False


def _send(text):
    if not TELEGRAM_TOKEN: return False
    subs = set(_get_subs())
    if not subs: return False
    chunks = _split(str(text)); ok = False
    for cid in subs:
        if not cid: continue
        for i,chunk in enumerate(chunks,1):
            payload = f"[{i}/{len(chunks)}]\n{chunk}" if len(chunks)>1 else chunk
            if _send_one(cid, payload): ok=True
            time.sleep(0.3)
    return ok

def _send_async(text):
    threading.Thread(target=_send, args=(text,), daemon=True).start()


# ─── Cooldown ─────────────────────────────────────────────────────────────────
def _similar(t1,t2): return difflib.SequenceMatcher(None,t1,t2).ratio()>0.55

def _on_cooldown(item, hours=12):
    title=str(item.get("title","")).lower(); cves=set(item.get("cves",[])); now=time.time()
    stale=[k for k,v in COOLDOWN.items() if now-v["time"]>hours*3600]
    for k in stale: del COOLDOWN[k]
    for d in COOLDOWN.values():
        if cves and d["cves"] and cves.intersection(d["cves"]): return True
        if _similar(title,d["title"]): return True
    return False

def _set_cooldown(item):
    COOLDOWN[str(item.get("fp",time.time()))] = {
        "time":time.time(),"title":str(item.get("title","")).lower(),"cves":set(item.get("cves",[]))}


# ─── Formatters ───────────────────────────────────────────────────────────────
def _s(val):
    if isinstance(val,list): return ", ".join(str(x) for x in val if x)
    return str(val) if val else ""


def _format_alert(item):
    sev=item.get("severity","LOW"); em=SEV_EMOJI.get(sev,"")
    summary=item.get("summary",[]); 
    ss="\n".join(f"  • {s}" for s in summary if isinstance(s,str)) if isinstance(summary,list) else f"  • {summary}"
    cves=_s(item.get("cves",[])); actors=_s(item.get("actors",[]))
    m  = f"{em} {sev} ALERT — {item.get('source','?')}\n{'━'*35}\n"
    m += f"📰 {item.get('title','')}\n\n"
    m += f"🏷 Category: {_s(item.get('category','tech')).upper()}\n"
    if cves:   m += f"🔴 CVEs: {cves}\n"
    if actors: m += f"🎭 Actors: {actors}\n"
    m += f"\n📋 Analysis:\n{ss}\n\n🔗 {item.get('link','')}"
    return m


def _format_digest(all_items, cycle_num, ai_digest=None):
    now   = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    lines = [f"📡 JARVIS CYCLE {cycle_num} BRIEFING", f"🕐 {now}", "━"*40]

    if ai_digest:
        if ai_digest.get("headline"):
            lines.append(f"\n🎯 {ai_digest['headline']}\n")

        for key, icon, title in [
            ("cybersec_updates",        "🛡️","CYBERSECURITY"),
            ("ai_updates",              "🧠","ARTIFICIAL INTELLIGENCE"),
            ("tech_business_updates",   "💼","TECH & BUSINESS"),
            ("hardware_mobile_updates", "📱","HARDWARE & MOBILE"),
        ]:
            paras = ai_digest.get(key,[])
            if paras:
                lines.append(f"\n{icon} {title}")
                for p in paras: lines.append(f"{p}")

        cves = ai_digest.get("key_cves",[])
        if cves: lines.append(f"\n🔴 CVEs THIS CYCLE:\n" + "\n".join(f"  • {c}" for c in cves))

        note = ai_digest.get("strategic_note","")
        if note: lines.append(f"\n🔍 ANALYST NOTE:\n{note}")
    else:
        lines.append("\n⚠️ AI synthesis unavailable for this cycle.")

    # Top references
    crit = sorted([i for i in all_items if i.get("severity") in ("CRITICAL","HIGH")],
                  key=lambda x: 0 if x.get("severity")=="CRITICAL" else 1)
    if crit:
        lines.append("\n" + "━"*40 + "\n🔗 TOP REFERENCES:")
        for item in crit[:6]:
            lines.append(f"{SEV_EMOJI.get(item.get('severity',''),'')} {str(item.get('title',''))[:75]}…\n  └ {item.get('link','')}")

    counts={}
    for item in all_items: s=item.get("severity","LOW"); counts[s]=counts.get(s,0)+1
    stats=" | ".join(f"{SEV_EMOJI.get(k,'')}{k}:{v}" for k,v in counts.items() if v>0)
    lines.append(f"\n📊 {stats} — {len(all_items)} articles processed")
    return "\n".join(lines)


def _format_daily(all_items, ai_summary):
    from datetime import datetime
    now = datetime.utcnow().strftime("%A, %B %d %Y")
    lines = [f"🗓 JARVIS DAILY BRIEF — {now}", "━"*45]

    if ai_summary:
        if ai_summary.get("day_headline"):
            lines.append(f"\n🎯 {ai_summary['day_headline']}")
        rl=ai_summary.get("risk_level","?")
        lines.append(f"⚡ Risk Level: {SEV_EMOJI.get(rl,'')} {rl}\n")

        if ai_summary.get("day_summary"):
            lines.append(ai_summary["day_summary"])

        lines.append("\n" + "━"*45)

        threats = ai_summary.get("escalating_threats",[])
        if threats:
            lines.append("\n🔺 ESCALATING THREATS")
            for t in threats: lines.append(f"  • {t}")

        patterns = ai_summary.get("new_patterns",[])
        if patterns:
            lines.append("\n🔍 ANALYST PATTERNS OBSERVED")
            for p in patterns: lines.append(f"  • {p}")

        actors = ai_summary.get("actor_activity",[])
        if actors:
            lines.append("\n🎭 THREAT ACTOR ACTIVITY")
            for a in actors: lines.append(f"  • {a}")

        cves = ai_summary.get("critical_cves",[])
        if cves: lines.append(f"\n🔴 PATCH NOW — {', '.join(cves)}")

        trends = ai_summary.get("tech_trends",[])
        if trends:
            lines.append("\n💡 TECH & AI DEVELOPMENTS")
            for t in trends: lines.append(f"  • {t}")

        recs = ai_summary.get("recommendations",[])
        if recs:
            lines.append("\n✅ RECOMMENDED ACTIONS")
            for i,r in enumerate(recs,1): lines.append(f"  {i}. {r}")
    else:
        lines.append("\n⚠️ AI synthesis unavailable — statistics only.")

    # Stats
    counts={}
    for item in all_items: s=item.get("severity","LOW"); counts[s]=counts.get(s,0)+1
    stats=" | ".join(f"{SEV_EMOJI.get(k,'')}{k}:{v}" for k,v in counts.items() if v>0)
    lines.append(f"\n{'━'*45}\n📊 Today: {len(all_items)} articles — {stats}")
    return "\n".join(lines)


def _format_weekly(all_items, ai_summary):
    from datetime import datetime
    now = datetime.utcnow().strftime("%B %d, %Y")
    lines = [f"🌍 JARVIS WEEKLY DIGEST — {now}", f"{'━'*45}"]

    if ai_summary:
        if ai_summary.get("day_headline"):
            lines.append(f"\n🎯 {ai_summary['day_headline']}")
        rl=ai_summary.get("risk_level","?")
        lines.append(f"⚡ Weekly Risk: {SEV_EMOJI.get(rl,'')} {rl}\n")

        doom=ai_summary.get("doom",[])
        if doom:
            lines.append("🌋 DOOM — Threats & Breaches")
            for d in doom: lines.append(f"\n{d}")

        bloom=ai_summary.get("bloom",[])
        if bloom:
            lines.append("\n🌸 BLOOM — Innovations & Wins")
            for b in bloom: lines.append(f"\n{b}")

        cves=ai_summary.get("key_cves",[])
        if cves: lines.append(f"\n🔴 WEEK'S CRITICAL CVEs:\n" + "\n".join(f"  • {c}" for c in cves))

        if ai_summary.get("day_summary"):
            lines.append(f"\n📝 STRATEGIC OUTLOOK\n{ai_summary['day_summary']}")
    else:
        lines.append("\n⚠️ AI synthesis unavailable.")

    lines.append(f"\n{'━'*45}\n📦 {len(all_items)} articles analysed this week")
    return "\n".join(lines)


# ─── Public API ───────────────────────────────────────────────────────────────
def notify_immediate(item):
    sev=item.get("severity","LOW")
    if sev not in ("CRITICAL","HIGH"): return
    if _on_cooldown(item):
        print(f"  [NOTIFIER] Dupe suppressed: {str(item.get('title',''))[:50]}"); return
    print(f"  [NOTIFIER] 🚨 Sending {sev} alert (async)")
    _send_async(_format_alert(item)); _set_cooldown(item)

def send_digest(all_items, cycle_num, ai_digest=None):
    print(f"[NOTIFIER] Sending cycle {cycle_num} digest")
    _send(_format_digest(all_items, cycle_num, ai_digest))

def send_daily_summary(all_items, ai_summary):
    print("[NOTIFIER] Sending daily report")
    _send(_format_daily(all_items, ai_summary))

def send_weekly_summary(all_items, ai_summary):
    print("[NOTIFIER] Sending weekly digest")
    _send(_format_weekly(all_items, ai_summary))

def telegram_send(text): _send(str(text))

def send_audio(filepath, caption="🎙️ JARVIS Daily Audio Briefing"):
    if not TELEGRAM_TOKEN or not os.path.exists(filepath): return False
    url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendAudio"
    for cid in set(_get_subs()):
        if not cid: continue
        for attempt in range(MAX_RETRIES):
            try:
                with open(filepath,"rb") as audio:
                    r=requests.post(url,data={"chat_id":cid,"caption":caption},
                                    files={"audio":audio},timeout=SEND_TIMEOUT)
                if r.status_code==200: break
                time.sleep(2**attempt*3)
            except requests.exceptions.SSLError: time.sleep(2**attempt*8)
            except Exception as e:
                print(f"[NOTIFIER] Audio error: {e}"); time.sleep(2**attempt*3)
    return True
