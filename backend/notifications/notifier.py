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


def _log(level, message, **details):
    """Log notification events to the database so they appear in the Logs page."""
    try:
        from jarvis_db import log_event
        log_event(level, "notifier", message, details or {})
    except Exception:
        pass


def _get_subs():
    try:
        s = load_subscribers()
        subs = set(str(item) for item in s)
        try:
            from jarvis_db import list_notification_channels
            for channel in list_notification_channels():
                if channel.get("kind") == "telegram" and channel.get("enabled") and channel.get("target"):
                    subs.add(str(channel["target"]))
        except Exception:
            pass
        return list(subs) if subs else ([str(TELEGRAM_CHAT_ID)] if TELEGRAM_CHAT_ID else [])
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


from backend.utils.telegram_client import telegram_post


def _send_one(chat_id, text):
    res = telegram_post("sendMessage", TELEGRAM_TOKEN, payload={"chat_id": chat_id, "text": text}, timeout=(3.0, 20.0), max_retries=3)
    if res.get("ok"):
        return True
    _log("ERROR", f"Telegram delivery failed for {chat_id}", chat_id=chat_id, error=str(res.get("error"))[:300])
    return False


def _send(text):
    if not TELEGRAM_TOKEN:
        _log("WARN", "Telegram send skipped: TELEGRAM_TOKEN not configured")
        return False
    subs = set(_get_subs())
    if not subs:
        _log("WARN", "Telegram send skipped: no subscribers or channels configured")
        return False
    chunks = _split(str(text)); ok = False
    for cid in subs:
        if not cid: continue
        for i,chunk in enumerate(chunks,1):
            payload = f"[{i}/{len(chunks)}]\n{chunk}" if len(chunks)>1 else chunk
            if _send_one(cid, payload): ok=True
            time.sleep(0.3)
    if ok:
        _log("INFO", "Telegram digest delivered", recipients=len(subs), chunks=len(chunks))
    return ok

def _send_async(text):
    threading.Thread(target=_send, args=(text,), daemon=True).start()


def _send_multichannel(text):
    tg_ok = False
    slack_ok = False

    # 1. Telegram delivery
    try:
        tg_ok = _send(text)
    except Exception as exc:
        print(f"[NOTIFIER] Telegram error: {exc}")
        _log("ERROR", f"Telegram error in multichannel send: {exc}")

    # 2. Slack delivery
    try:
        from slack_notifier import send_slack_message
        slack_ok = send_slack_message(text)
    except Exception as exc:
        print(f"[NOTIFIER] Slack error: {exc}")
        _log("ERROR", f"Slack error in multichannel send: {exc}")

    return tg_ok or slack_ok


def _send_multichannel_async(text):
    threading.Thread(target=_send_multichannel, args=(text,), daemon=True).start()


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
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%A, %B %d %Y")
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
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%B %d, %Y")
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
    sev = item.get("severity", "LOW")
    if sev not in ("CRITICAL", "HIGH"):
        return False
    if _on_cooldown(item):
        print(f"  [NOTIFIER] Dupe suppressed: {str(item.get('title',''))[:50]}")
        _log("INFO", f"Immediate alert suppressed (cooldown)", title=str(item.get('title',''))[:100], severity=sev)
        return False
    print(f"  [NOTIFIER] 🚨 Sending {sev} alert")
    _log("INFO", f"Triggering immediate {sev} alert", title=str(item.get('title',''))[:100], severity=sev)
    ok = _send_multichannel(_format_alert(item))
    _set_cooldown(item)
    return ok

def send_digest(all_items, cycle_num, ai_digest=None):
    print(f"[NOTIFIER] Sending cycle {cycle_num} digest")
    ok = _send_multichannel(_format_digest(all_items, cycle_num, ai_digest))
    if ok:
        _log("INFO", f"Cycle {cycle_num} digest delivered", articles=len(all_items))
    else:
        _log("WARN", f"Cycle {cycle_num} digest delivery failed or no channels", articles=len(all_items))
    return ok

def send_daily_summary(all_items, ai_summary):
    print("[NOTIFIER] Sending daily report")
    ok = _send_multichannel(_format_daily(all_items, ai_summary))
    if ok:
        _log("INFO", "Daily summary delivered", articles=len(all_items))
    else:
        _log("WARN", "Daily summary delivery failed or no channels", articles=len(all_items))
    return ok

def send_weekly_summary(all_items, ai_summary):
    print("[NOTIFIER] Sending weekly digest")
    ok = _send_multichannel(_format_weekly(all_items, ai_summary))
    if ok:
        _log("INFO", "Weekly summary delivered", articles=len(all_items))
    else:
        _log("WARN", "Weekly summary delivery failed or no channels", articles=len(all_items))
    return ok

def telegram_send(text): _send(str(text))


def test_channel(kind, target, secret=None):
    """Send a test message to a specific channel and return a result dict.

    Used by the admin/user UI "Test" button so delivery failures are visible.
    """
    kind = str(kind or "").lower().strip()
    target = str(target or "").strip()
    secret = secret or {}
    if kind == "telegram":
        if not TELEGRAM_TOKEN:
            return {"ok": False, "error": "TELEGRAM_TOKEN is not configured in .env"}
        if not target:
            return {"ok": False, "error": "Telegram chat ID is required"}
        res = telegram_post("sendMessage", TELEGRAM_TOKEN, payload={"chat_id": target, "text": "✅ JARVIS test message — your Telegram channel is working."}, timeout=(3.0, 15.0), max_retries=2)
        if res.get("ok"):
            _log("INFO", "Telegram test message sent", chat_id=target)
            return {"ok": True, "message": "Test message sent successfully"}
        err = str(res.get("error", "Unknown error"))
        _log("ERROR", "Telegram test failed", chat_id=target, error=err[:300])
        return {"ok": False, "error": err[:300]}
    if kind == "slack":
        webhook = str(secret.get("webhook_url") or target or "").strip()
        if not webhook:
            return {"ok": False, "error": "Slack webhook URL is required"}
        try:
            r = requests.post(webhook, json={"text": "✅ JARVIS test message — your Slack channel is working."}, timeout=20)
            if 200 <= r.status_code < 300:
                _log("INFO", "Slack test message sent")
                return {"ok": True, "message": "Test message sent successfully"}
            body = r.text[:300]
            _log("ERROR", "Slack test failed", status=r.status_code, error=body)
            return {"ok": False, "error": f"Slack webhook returned HTTP {r.status_code}: {body}"}
        except Exception as exc:
            _log("ERROR", "Slack test error", error=str(exc)[:300])
            return {"ok": False, "error": str(exc)[:300]}
    return {"ok": False, "error": f"Unknown channel kind: {kind}"}

def send_audio(filepath, caption="🎙️ JARVIS Daily Audio Briefing"):
    if not TELEGRAM_TOKEN or not os.path.exists(filepath):
        return False
    ok = False
    for cid in set(_get_subs()):
        if not cid:
            continue
        try:
            with open(filepath, "rb") as audio:
                res = telegram_post("sendAudio", TELEGRAM_TOKEN, payload={"chat_id": cid, "caption": caption}, files={"audio": audio}, timeout=(5.0, 60.0), max_retries=3)
                if res.get("ok"):
                    ok = True
        except Exception as e:
            print(f"[NOTIFIER] Audio error: {e}")
    return ok
