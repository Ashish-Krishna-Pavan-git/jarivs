"""
ai_router.py — Multi-tier AI routing with story-driven prompts.

Model tiers:
  PREMIUM  daily/weekly    → gemini-2.5-pro   → flash → groq-70b
  STANDARD cycle digest    → gemini-2.5-flash → groq-70b
  FAST     per-article     → groq-8b          → gemini-2.5-flash
  TEXT     chat/deepdive   → gemini-2.5-flash → groq-70b
"""

import json, time, os, random, threading, requests
from google import genai
from google.genai import types
from groq import Groq
from config import AI_MAX_CONTENT_CHARS, GEMINI_MIN_INTERVAL, GROQ_MIN_INTERVAL

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY","")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY","")
gemini_client  = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
groq_client    = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

_gemini_lock = threading.Lock(); _gemini_last = [0.0]
_groq_lock   = threading.Lock(); _groq_last   = [0.0]
_GEMINI_PRO_INTERVAL = 13.0

# ─── AI call tracking (for UI visibility) ─────────────────────────────────────
_ai_status_lock = threading.Lock()
_ai_status: dict = {
    "last_task": None,
    "last_provider": None,
    "last_model": None,
    "last_latency_ms": None,
    "last_fallback_used": False,
    "last_success": False,
    "last_error": None,
    "last_called_at": None,
    "total_calls": 0,
    "total_fallbacks": 0,
    "total_failures": 0,
}

def _record_ai_call(task, provider, model, latency_ms, success, fallback_used=False, error=None):
    """Record metadata about the most recent AI call for UI visibility."""
    with _ai_status_lock:
        _ai_status.update({
            "last_task": task,
            "last_provider": provider,
            "last_model": model,
            "last_latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
            "last_fallback_used": fallback_used,
            "last_success": success,
            "last_error": str(error)[:300] if error else None,
            "last_called_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_calls": _ai_status["total_calls"] + 1,
            "total_fallbacks": _ai_status["total_fallbacks"] + (1 if fallback_used else 0),
            "total_failures": _ai_status["total_failures"] + (0 if success else 1),
        })

def get_ai_status() -> dict:
    """Return a snapshot of AI call metadata for the UI."""
    with _ai_status_lock:
        return dict(_ai_status)

def _wait(lock, last_ref, interval, name):
    with lock:
        elapsed = time.time()-last_ref[0]
        if elapsed < interval:
            w = interval-elapsed
            print(f"  [AI] {name} rate slot: sleeping {w:.1f}s")
            time.sleep(w)
        last_ref[0] = time.time()

def dbg(msg): print(f"  [AI] {msg}")


def _api_key(provider):
    env_name = str(provider.get("api_key_env") or "").strip()
    return os.getenv(env_name, "") if env_name else ""


def _ollama_call(provider, prompt, json_mode=True):
    base_url = str(provider.get("base_url") or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
    payload = {"model": provider.get("model") or os.getenv("OLLAMA_MODEL", "phi4-mini"), "prompt": prompt, "stream": False}
    if json_mode:
        payload["format"] = "json"
    response = requests.post(f"{base_url}/api/generate", json=payload, timeout=180)
    response.raise_for_status()
    return response.json().get("response", "")


def _openai_compatible_call(provider, prompt, json_mode=True):
    base_url = str(provider.get("base_url") or "").rstrip("/")
    key = _api_key(provider)
    if not base_url:
        return None
    payload = {
        "model": provider.get("model"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    response = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=180)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _configured_route_call(task, prompt, json_mode=True):
    try:
        from jarvis_db import block_model_provider, get_model_route, init_db, log_event
        init_db()
        route = get_model_route(task)
    except Exception as exc:
        dbg(f"DB route unavailable: {exc}")
        return None
    first_provider = True
    for provider in route:
        kind = str(provider.get("provider_type", "")).lower()
        pname = provider.get("name", kind)
        pmodel = provider.get("model", "")
        t0 = time.time()
        try:
            if float(provider.get("min_interval") or 0) > 0:
                time.sleep(float(provider.get("min_interval") or 0))
            if kind == "gemini":
                result = gemini_call(prompt, model=pmodel) if json_mode else gemini_call_text(prompt, model=pmodel)
            elif kind == "groq":
                result = groq_call(prompt, model=pmodel) if json_mode else groq_call_text(prompt, model=pmodel)
            elif kind == "ollama":
                result = _ollama_call(provider, prompt, json_mode=json_mode)
            elif kind in {"openai", "openai_compatible", "custom"}:
                result = _openai_compatible_call(provider, prompt, json_mode=json_mode)
            else:
                continue
            latency = (time.time() - t0) * 1000
            if result:
                _record_ai_call(task, pname, pmodel, latency, True, fallback_used=not first_provider)
                return result
        except Exception as exc:
            msg = str(exc)
            _record_ai_call(task, pname, pmodel, (time.time() - t0) * 1000, False, fallback_used=not first_provider, error=msg)
            try:
                log_event("WARN", "ai_router", f"Provider failed: {pname}", {"error": msg[:500], "model": pmodel, "task": task})
                if any(token in msg.lower() for token in ["429", "quota", "rate", "resource_exhausted"]):
                    block_model_provider(pname, 180, msg[:300])
            except Exception:
                pass
        first_provider = False
    return None

_SAFETY = [
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,       threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,        threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
]

# ─── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are JARVIS — a senior intelligence analyst and compelling science journalist.
Your reports combine rigorous technical accuracy with engaging narrative storytelling.
Write like the best of The Economist meets a threat intelligence CISO briefing.
Be specific, concrete, and use real names, CVE IDs, and product names.
You MUST return ONLY valid JSON. Escape internal quotes with \\\"."""


def reset_ai_status():
    """Reset AI status counters for Factory Reset."""
    global _ai_status
    _ai_status = {
        "last_task": None,
        "last_provider": None,
        "last_model": None,
        "last_latency_ms": None,
        "last_fallback_used": False,
        "last_success": True,
        "last_error": None,
        "last_called_at": None,
        "total_calls": 0,
        "total_fallbacks": 0,
        "total_failures": 0,
    }


def build_analysis_prompt(title, content):
    return f"""{SYSTEM_PROMPT}

Analyse this article and extract structured intelligence.

Title: {title}
Content:
{content[:AI_MAX_CONTENT_CHARS]}

Return ONLY this JSON:
{{
  "severity": "CRITICAL|HIGH|MEDIUM|LOW|MINIMAL",
  "confidence": 0-100,
  "reason": "Clear 1-sentence justification for the severity assignment",
  "category": "cybersec|ai|tech|mobile|hardware|newsletter|business",
  "summary": [
    "What happened — the core finding in one clear sentence",
    "How it works — the technical mechanism or attack vector",
    "Who is affected — specific products, versions, organisations",
    "What to do — concrete mitigation or patch action"
  ],
  "tags": ["tag1","tag2"],
  "cves": ["CVE-YYYY-NNNNN"],
  "actors": ["threat actor name"],
  "affected_products": ["product name vX.X"]
}}

STRICT SEVERITY DEFINITIONS:
- CRITICAL: Reserved ONLY for active zero-days, active in-the-wild exploitation, emergency CISA KEV advisories, major nation-state/ransomware attacks causing active disruption, or critical supply chain compromises.
- HIGH: Important vulnerabilities (unpatched or vendor advisories), major vendor security releases, cloud security incidents, AI security flaws.
- MEDIUM: Product releases, technical research papers, new attack techniques, security tooling updates, significant tech news.
- LOW: Minor updates, small product announcements, routine advisories without active threat.
- MINIMAL: General news, opinion articles, small feature updates.

category must be ONE value from the list. Return ONLY the JSON."""


def build_digest_prompt(items_text, cycle_label):
    return f"""{SYSTEM_PROMPT}

You are writing the {cycle_label} intelligence briefing — think of it as a tightly edited
breaking-news segment combined with expert analyst commentary.
Do NOT just list headlines. Synthesise, contextualise, find the thread connecting events.

Items from this cycle:
{items_text}

Return ONLY this JSON:
{{
  "headline": "One punchy, specific sentence — the single most important story of this cycle, written like a front-page headline",
  "cybersec_updates": [
    "Story-driven paragraph: what attack/vulnerability emerged, who is behind it, what systems are at risk, and what defenders should do — name specific threat actors and CVEs where present",
    "Second cybersecurity story with similar depth and narrative"
  ],
  "ai_updates": [
    "Engaging paragraph on the AI development — why it matters, what changed, what it means for the industry or security landscape"
  ],
  "tech_business_updates": [
    "Narrative paragraph on the most interesting tech or business development — connect it to broader trends"
  ],
  "hardware_mobile_updates": [
    "Concrete paragraph on hardware or mobile news — specs, vulnerabilities, or market shifts that matter"
  ],
  "key_cves": ["CVE-YYYY-NNNNN: What it affects, severity, and whether it's being exploited"],
  "strategic_note": "One analytical paragraph — step back from the individual stories and tell the reader what the pattern means. What should a CISO or tech leader take away from this cycle?"
}}
Return ONLY the JSON."""


def build_daily_prompt(digests_text):
    return f"""{SYSTEM_PROMPT}

You are writing the Executive Daily Intelligence Briefing — the definitive end-of-day
analysis that a CISO, security researcher, or tech executive reads before signing off.
Cross-correlate the cycle digests below. Find the threads, escalations, and surprises.
Write with the authority of someone who has read everything and synthesised it.

Cycle digests:
{digests_text}

Return ONLY this JSON:
{{
  "day_headline": "The single most important story of the day — specific, vivid, actionable. Not generic.",
  "escalating_threats": [
    "A threat that appeared across multiple cycles, growing in severity or scope — name it specifically",
    "Another escalating threat with evidence of persistence or widening impact"
  ],
  "new_patterns": [
    "A pattern visible only when you look across all three cycles — something a single digest would miss",
    "A second cross-cycle insight or correlation between seemingly unrelated events"
  ],
  "actor_activity": [
    "Named threat actor observed today — their TTPs, targets, and what changed"
  ],
  "critical_cves": ["CVE-YYYY-NNNNN: Affected system, exploit status, and urgency level"],
  "tech_trends": [
    "The most significant AI or technology development today and why it matters strategically",
    "A hardware or platform shift worth tracking"
  ],
  "recommendations": [
    "Specific, implementable action a security team should take today based on this intelligence",
    "A strategic recommendation for the coming week based on today's patterns"
  ],
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
  "day_summary": "Three to four sentences that tell the story of today. What happened, what it means, and what comes next. Write it like the opening paragraph of a great intelligence report — specific, clear, and memorable."
}}
Return ONLY the JSON."""


def build_weekly_prompt(items_text):
    return f"""{SYSTEM_PROMPT}

You are writing the Sunday JARVIS Weekly Digest — our premium weekly intelligence magazine.
This is 'Doom vs Bloom': the week's darkest threats contrasted with its brightest innovations.
Write with depth, narrative drive, and genuine insight. This is the report readers save.

Top items from the past 7 days:
{items_text}

Return ONLY this JSON:
{{
  "day_headline": "A headline that captures the defining narrative of this week — compelling, specific, and memorable",
  "doom": [
    "Deep-dive paragraph on the week's most serious threat: the breach, the APT campaign, the zero-day that defined the threat landscape. Name actors, victims, CVEs. Tell the story.",
    "Second doom paragraph covering escalating ransomware, supply chain risks, or regulatory failures — the slow-burning threat"
  ],
  "bloom": [
    "Genuinely exciting AI or technology breakthrough this week — what changed, why it matters, what it unlocks",
    "A security win, law enforcement takedown, or defensive innovation that gives defenders reason for optimism"
  ],
  "key_cves": ["CVE-YYYY-NNNNN: The week's most critical vulnerability — who found it, what it affects, patch status"],
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
  "day_summary": "The week in four sentences. What was the defining threat? What was the most exciting development? What pattern should we carry into next week? Make it worth reading."
}}
Return ONLY the JSON."""


# ─── JSON Parser ──────────────────────────────────────────────────────────────
def extract_json(text):
    if not text: return None
    try:
        text  = text.replace("```json","").replace("```","").strip()
        start = text.find("{"); end = text.rfind("}")+1
        if start==-1 or end==0: return None
        return json.loads(text[start:end])
    except Exception as e:
        dbg(f"JSON parse error: {e}"); return None


# ─── Keyword Severity ─────────────────────────────────────────────────────────
_CK = ["rce","remote code execution","zero-day","0-day","actively exploited","supply chain attack",
       "authentication bypass","unauthenticated rce","mass exploitation","emergency patch","in the wild"]
_HK = ["privilege escalation","malware","apt","ransomware","breach","data leak",
       "backdoor","trojan","phishing campaign","critical vulnerability"]
_MK = ["cve","patch","vulnerability","advisory","security fix","exploit","attack","compromised","injection"]

def keyword_severity(title, content=""):
    t = (title+" "+content).lower()
    s = sum(4 for k in _CK if k in t)+sum(2 for k in _HK if k in t)+sum(1 for k in _MK if k in t)
    return "CRITICAL" if s>=12 else "HIGH" if s>=7 else "MEDIUM" if s>=3 else "LOW" if s>=1 else "MINIMAL"


# ─── Groq ─────────────────────────────────────────────────────────────────────
def groq_call(prompt, model="llama-3.1-8b-instant", retries=3):
    if not groq_client: return None
    for attempt in range(1, retries+1):
        _wait(_groq_lock, _groq_last, GROQ_MIN_INTERVAL, f"Groq({model[:12]})")
        try:
            dbg(f"Groq JSON [{model[:20]}] attempt {attempt}/{retries}")
            chat = groq_client.chat.completions.create(
                messages=[{"role":"user","content":prompt}],
                model=model, response_format={"type":"json_object"}, timeout=45)
            return chat.choices[0].message.content
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err:
                t=5*attempt; dbg(f"Groq 429 backoff {t}s"); time.sleep(t)
            elif "model" in err and "not found" in err:
                dbg(f"Groq model not found: {model}"); return None
            else:
                dbg(f"Groq error: {e}")
                if attempt<retries: time.sleep(3)
                else: return None
    return None


def groq_call_text(prompt, model="llama-3.3-70b-versatile", retries=3):
    if not groq_client: return None
    for attempt in range(1, retries+1):
        _wait(_groq_lock, _groq_last, GROQ_MIN_INTERVAL, f"Groq-txt({model[:12]})")
        try:
            dbg(f"Groq TEXT [{model[:20]}] attempt {attempt}/{retries}")
            chat = groq_client.chat.completions.create(
                messages=[{"role":"user","content":prompt}],
                model=model, timeout=60)
            return chat.choices[0].message.content
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err:
                t=5*attempt; dbg(f"Groq-txt 429 backoff {t}s"); time.sleep(t)
            else:
                dbg(f"Groq-txt error: {e}")
                if attempt<retries: time.sleep(3)
                else: return None
    return None


# ─── Gemini ───────────────────────────────────────────────────────────────────
def gemini_call(prompt, retries=3, model="gemini-2.5-flash"):
    if not gemini_client: return None
    interval = _GEMINI_PRO_INTERVAL if "pro" in model else GEMINI_MIN_INTERVAL
    for attempt in range(1, retries+1):
        _wait(_gemini_lock, _gemini_last, interval, f"Gemini({model[-8:]})")
        try:
            dbg(f"Gemini JSON [{model}] attempt {attempt}/{retries}")
            r = gemini_client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", safety_settings=_SAFETY))
            return r.text
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "quota" in err or "resource_exhausted" in err:
                w=(2**attempt)*20+random.uniform(0,10); dbg(f"Gemini 429 backoff {w:.0f}s"); time.sleep(w)
            elif "503" in err or "unavailable" in err:
                time.sleep(15+random.uniform(0,5))
            else:
                dbg(f"Gemini error: {e}"); return None
    return None


def gemini_call_text(prompt, retries=3, model="gemini-2.5-flash"):
    if not gemini_client: return None
    interval = _GEMINI_PRO_INTERVAL if "pro" in model else GEMINI_MIN_INTERVAL
    for attempt in range(1, retries+1):
        _wait(_gemini_lock, _gemini_last, interval, f"Gemini-txt({model[-8:]})")
        try:
            dbg(f"Gemini TEXT [{model}] attempt {attempt}/{retries}")
            r = gemini_client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(safety_settings=_SAFETY))
            return r.text
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "quota" in err or "resource_exhausted" in err:
                w=(2**attempt)*20+random.uniform(0,10); dbg(f"Gemini-txt 429 backoff {w:.0f}s"); time.sleep(w)
            elif "503" in err or "unavailable" in err:
                time.sleep(15)
            else:
                dbg(f"Gemini-txt error: {e}"); return None
    return None


# ─── Routers ──────────────────────────────────────────────────────────────────
def _tracked_call(task, provider_name, model, fn, fallback_used):
    """Call an AI function and record metadata for UI visibility."""
    t0 = time.time()
    try:
        result = fn()
        latency = (time.time() - t0) * 1000
        if result:
            _record_ai_call(task, provider_name, model, latency, True, fallback_used=fallback_used)
        return result
    except Exception as exc:
        _record_ai_call(task, provider_name, model, (time.time() - t0) * 1000, False, fallback_used=fallback_used, error=exc)
        raise

def local_call_premium(prompt):
    """Daily/weekly — gemini-2.5-pro → flash → groq-70b"""
    r = _configured_route_call("premium", prompt, json_mode=True)
    if r: return r
    r = _tracked_call("premium", "gemini", "gemini-2.5-pro", lambda: gemini_call(prompt, model="gemini-2.5-pro"), False)
    if not r:
        r = _tracked_call("premium", "gemini", "gemini-2.5-flash", lambda: gemini_call(prompt, model="gemini-2.5-flash"), True)
    if not r:
        r = _tracked_call("premium", "groq", "llama-3.3-70b-versatile", lambda: groq_call(prompt, model="llama-3.3-70b-versatile"), True)
    return r

def local_call(prompt):
    """Cycle digest / quiz — gemini-2.5-flash → groq-70b"""
    r = _configured_route_call("digest", prompt, json_mode=True)
    if r: return r
    r = _tracked_call("digest", "gemini", "gemini-2.5-flash", lambda: gemini_call(prompt, model="gemini-2.5-flash"), False)
    if not r:
        r = _tracked_call("digest", "groq", "llama-3.3-70b-versatile", lambda: groq_call(prompt, model="llama-3.3-70b-versatile"), True)
    return r

def local_call_article(prompt):
    """Per-article bulk — groq-8b → gemini-flash"""
    r = _configured_route_call("article", prompt, json_mode=True)
    if r: return r
    r = _tracked_call("article", "groq", "llama-3.1-8b-instant", lambda: groq_call(prompt, model="llama-3.1-8b-instant"), False)
    if not r:
        r = _tracked_call("article", "gemini", "gemini-2.5-flash", lambda: gemini_call(prompt, model="gemini-2.5-flash"), True)
    return r

def local_call_text(prompt):
    """Plain prose — gemini-flash → groq-70b"""
    r = _configured_route_call("text", prompt, json_mode=False)
    if r: return r
    r = _tracked_call("text", "gemini", "gemini-2.5-flash", lambda: gemini_call_text(prompt, model="gemini-2.5-flash"), False)
    if not r:
        r = _tracked_call("text", "groq", "llama-3.3-70b-versatile", lambda: groq_call_text(prompt, model="llama-3.3-70b-versatile"), True)
    return r


# ─── Redesigned Severity Engine ────────────────────────────────────────────────
_CRIT_TRIGGERS = [
    "zero-day", "0-day", "actively exploited", "in the wild", "active exploitation",
    "cisa kev", "emergency advisory", "unauthenticated rce", "supply chain attack",
    "supply-chain attack", "supply chain compromise", "nation-state attack", "ransomware attack",
    "critical vulnerability", "mass exploitation"
]

_HIGH_TRIGGERS = [
    "vulnerability", "cve-", "privilege escalation", "malware", "apt",
    "ransomware", "breach", "data leak", "backdoor", "trojan", "phishing campaign",
    "security update", "security release", "advisory", "patch tuesday", "remote code execution"
]

_MED_TRIGGERS = [
    "release", "update", "research", "paper", "tooling", "framework", "architecture",
    "analysis", "feature", "model", "benchmarks", "announcement"
]

_HISTORICAL_TRIGGERS = [
    "retrospective", "history of", "years ago", "look back", "evolution of",
    "timeline of", "news events that shaped", "decade of"
]


def evaluate_severity(title: str, content: str, ai_data: dict | None = None) -> dict:
    """
    Redesigned Severity Engine:
    Combines AI reasoning with deterministic validation rules, strict severity capping
    to prevent over-classification into Critical/High, 0-100 confidence scoring,
    and detailed logging.
    """
    text = (title + " " + content).lower()

    ai_sev = str((ai_data or {}).get("severity", "")).upper()
    ai_conf = (ai_data or {}).get("confidence")
    ai_reason = str((ai_data or {}).get("reason", "")).strip()

    try:
        raw_conf = int(ai_conf)
        conf = raw_conf * 10 if 0 < raw_conf <= 10 else min(100, max(0, raw_conf))
    except Exception:
        conf = 70 if ai_sev else 50

    has_crit_trigger = any(kw in text for kw in _CRIT_TRIGGERS)
    has_high_trigger = any(kw in text for kw in _HIGH_TRIGGERS)
    has_med_trigger = any(kw in text for kw in _MED_TRIGGERS)
    is_historical = any(kw in text for kw in _HISTORICAL_TRIGGERS)

    # 1. CRITICAL Validation
    if ai_sev == "CRITICAL":
        if is_historical:
            final_sev = "MEDIUM"
            conf = min(conf, 70)
            reason = "Capped from CRITICAL to MEDIUM: Historical/retrospective content."
        elif has_crit_trigger or (ai_data and ai_data.get("cves") and conf >= 80):
            final_sev = "CRITICAL"
            conf = max(conf, 85)
            reason = ai_reason or "Verified CRITICAL: Active zero-day/exploitation signals present."
        else:
            final_sev = "HIGH"
            conf = min(conf, 75)
            reason = ai_reason or "Capped from CRITICAL to HIGH: Lacks active exploitation or zero-day triggers."

    # 2. HIGH Validation
    elif ai_sev == "HIGH":
        if is_historical:
            final_sev = "LOW"
            conf = min(conf, 65)
            reason = "Capped from HIGH to LOW: Historical content."
        elif has_crit_trigger and not is_historical:
            final_sev = "CRITICAL"
            conf = max(conf, 85)
            reason = "Upgraded to CRITICAL: Strong active exploitation/zero-day signals detected."
        elif has_high_trigger or (ai_data and ai_data.get("cves")):
            final_sev = "HIGH"
            conf = max(conf, 75)
            reason = ai_reason or "Verified HIGH: Important vulnerability or security advisory."
        else:
            final_sev = "MEDIUM"
            conf = min(conf, 70)
            reason = ai_reason or "Capped from HIGH to MEDIUM: Lacks security advisory/vulnerability triggers."

    # 3. MEDIUM / LOW / MINIMAL Validation
    elif ai_sev in ("MEDIUM", "LOW", "MINIMAL"):
        if has_crit_trigger and not is_historical:
            final_sev = "CRITICAL" if conf >= 70 else "HIGH"
            conf = max(conf, 80)
            reason = f"Upgraded to {final_sev}: High-risk zero-day/exploitation signals present."
        elif ai_sev == "MEDIUM":
            final_sev = "MEDIUM"
            reason = ai_reason or "Verified MEDIUM: Standard research, product release, or tech news."
        elif ai_sev == "LOW":
            final_sev = "LOW"
            reason = ai_reason or "Verified LOW: Routine update or minor announcement."
        else:
            final_sev = "MINIMAL"
            reason = ai_reason or "Verified MINIMAL: General news, opinion, or non-technical content."

    # 4. Deterministic Fallback (AI unavailable)
    else:
        if is_historical:
            final_sev = "LOW"
            conf = 50
            reason = "Fallback: Historical content."
        elif has_crit_trigger:
            final_sev = "HIGH"
            conf = 65
            reason = "Fallback: Critical security keywords detected without AI verification."
        elif has_high_trigger:
            final_sev = "MEDIUM"
            conf = 60
            reason = "Fallback: Security keywords detected."
        elif has_med_trigger:
            final_sev = "MEDIUM"
            conf = 55
            reason = "Fallback: Product/tech keywords detected."
        else:
            final_sev = "LOW"
            conf = 50
            reason = "Fallback: General content."

    print(f"[SEVERITY_ENGINE] Title: '{title[:50]}...' -> {final_sev} ({conf}%) | Reason: {reason}")
    try:
        from jarvis_db import log_event
        log_event("INFO", "severity_engine", f"Assigned {final_sev} ({conf}%)", {
            "title": title[:100], "severity": final_sev, "confidence": conf, "reason": reason
        })
    except Exception:
        pass

    return {"severity": final_sev, "confidence": conf, "reason": reason}


# ─── Public Analysis ──────────────────────────────────────────────────────────
def ai_analyze(title, content):
    raw = local_call_article(build_analysis_prompt(title, content))
    data = extract_json(raw) or {}
    
    sev_eval = evaluate_severity(title, content, data)
    
    data["severity"] = sev_eval["severity"]
    data["confidence"] = sev_eval["confidence"]
    data["reason"] = sev_eval["reason"]
    if "category" not in data:
        data["category"] = "tech"
    if "summary" not in data or not data["summary"]:
        data["summary"] = ["Summary unavailable — initial processing completed."]
    if "tags" not in data: data["tags"] = []
    if "cves" not in data: data["cves"] = []
    if "actors" not in data: data["actors"] = []
    if "affected_products" not in data: data["affected_products"] = []
    
    return data


def ai_digest(items, cycle_label="8-hour cycle"):
    sev_map = {"CRITICAL":5,"HIGH":4,"MEDIUM":3,"LOW":2,"MINIMAL":1}
    sorted_items = sorted(items, key=lambda x: sev_map.get(x.get("severity","LOW"),0), reverse=True)
    items_text = ""
    for item in sorted_items:
        s = item.get("summary","")
        if isinstance(s, list): s = " | ".join(s)
        items_text += f"[{item.get('severity','?')}][{item.get('category','tech')}] {item.get('title','')}\n  {s[:250]}\n\n"
        if len(items_text) > 8000: break
    return extract_json(local_call(build_digest_prompt(items_text, cycle_label)))


def ai_daily_summary(digests):
    dt = "".join(f"\n--- DIGEST {i} ---\n{json.dumps(d,indent=2)}\n" for i,d in enumerate(digests,1))
    return extract_json(local_call_premium(build_daily_prompt(dt[:12000])))


def ai_weekly_summary(items):
    sev_map = {"CRITICAL":5,"HIGH":4,"MEDIUM":3,"LOW":2,"MINIMAL":1}
    sorted_items = sorted(items, key=lambda x: sev_map.get(x.get("severity","LOW"),0), reverse=True)
    items_text = ""
    for item in sorted_items[:40]:
        items_text += f"[{item.get('severity','?')}] {item.get('title','')}\n  {item.get('summary_text','')[:200]}\n\n"
    return extract_json(local_call_premium(build_weekly_prompt(items_text[:12000])))


def get_models_summary() -> dict:
    """
    Returns a comprehensive model inventory, free vs paid counts, active models,
    rate-limiting cooldown status, and provider descriptions for Admin UI.
    """
    try:
        from jarvis_db import list_model_providers
        providers = list_model_providers()
    except Exception:
        providers = []

    provider_guides = {
        "groq": {
            "title": "Groq LPU Cloud",
            "tier": "Free Tier Available",
            "best_for": "Ultra-fast, low-latency bulk article classification & extraction",
            "rate_limit_info": "30 RPM free tier limit (2.5s interval between requests)",
        },
        "gemini": {
            "title": "Google Gemini AI",
            "tier": "Free Tier Available",
            "best_for": "Deep analytical reasoning, multi-article synthesis & executive digests",
            "rate_limit_info": "15 RPM free tier limit (4.5s interval between requests)",
        },
        "ollama": {
            "title": "Ollama Local (Future / On-Prem)",
            "tier": "100% Free / Local",
            "best_for": "Zero-cloud-cost private LLM inference running on local hardware",
            "rate_limit_info": "No API rate limits (hardware dependent)",
        },
        "openrouter": {
            "title": "OpenRouter Cloud (Future / Multi-Model)",
            "tier": "Free & Paid Models",
            "best_for": "Multi-provider routing to DeepSeek, Claude, Llama 3.3, & Qwen",
            "rate_limit_info": "Varies by selected model & tier",
        },
    }

    existing_types = {str(p.get("provider_type")).lower() for p in providers}
    formatted_providers = []
    total_models = 0
    free_models = 0
    active_models = 0
    rate_limited_models = 0
    now = time.time()

    for p in providers:
        ptype = str(p.get("provider_type", "")).lower()
        model_name = str(p.get("model", "default"))
        is_enabled = bool(p.get("enabled", True))
        is_free = ptype in ("groq", "gemini", "ollama") or "free" in model_name.lower()
        
        total_models += 1
        if is_free: free_models += 1
        if is_enabled: active_models += 1

        cooldown_rem = 0.0
        if ptype == "gemini" and (now - _gemini_last[0]) < GEMINI_MIN_INTERVAL:
            cooldown_rem = round(GEMINI_MIN_INTERVAL - (now - _gemini_last[0]), 1)
        elif ptype == "groq" and (now - _groq_last[0]) < GROQ_MIN_INTERVAL:
            cooldown_rem = round(GROQ_MIN_INTERVAL - (now - _groq_last[0]), 1)

        if cooldown_rem > 0:
            rate_limited_models += 1

        guide = provider_guides.get(ptype, {
            "title": p.get("name", ptype.upper()),
            "tier": "Free Tier" if is_free else "Paid Tier",
            "best_for": "General LLM inference",
            "rate_limit_info": f"Min interval: {p.get('min_interval', 0)}s",
        })

        formatted_providers.append({
            "id": p.get("id"),
            "name": p.get("name"),
            "provider_type": ptype,
            "model": model_name,
            "enabled": is_enabled,
            "is_free": is_free,
            "base_url": p.get("base_url", ""),
            "api_key_configured": bool(_api_key(p)),
            "min_interval": float(p.get("min_interval") or 0.0),
            "cooldown_remaining_sec": cooldown_rem,
            "guide": guide,
        })

    for ptype in ["ollama", "openrouter"]:
        if ptype not in existing_types:
            formatted_providers.append({
                "id": None,
                "name": f"Future Provider: {ptype.upper()}",
                "provider_type": ptype,
                "model": "phi4-mini" if ptype == "ollama" else "deepseek/deepseek-r1:free",
                "enabled": False,
                "is_free": True,
                "placeholder": True,
                "base_url": "http://localhost:11434" if ptype == "ollama" else "https://openrouter.ai/api/v1",
                "api_key_configured": False,
                "min_interval": 0.0,
                "cooldown_remaining_sec": 0.0,
                "guide": provider_guides[ptype],
            })
            total_models += 1
            free_models += 1

    return {
        "total_models": total_models,
        "free_models": free_models,
        "active_models": active_models,
        "rate_limited_models": rate_limited_models,
        "providers": formatted_providers,
        "ai_status": get_ai_status(),
    }
