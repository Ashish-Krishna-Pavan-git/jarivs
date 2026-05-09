"""
ai_router.py
Task-aware Groq/Gemini routing with persisted quota/cooldown state.

Routing policy:
  - Bulk article analysis: Groq first, Gemini fallback only if needed.
  - Scheduled synthesis (8h digest, daily, weekly): Gemini 2.5 first.
  - Interactive bot tasks: Groq first to preserve Gemini budget.

Provider usage and cooldowns are persisted in provider_state.json so a redeploy
does not immediately forget quota exhaustion or hammer Gemini again.
"""

import copy
import json
import os
import random
import threading
import time

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

try:
    from groq import Groq
except ImportError:
    Groq = None

from config import (
    AI_MAX_CONTENT_CHARS,
    GEMINI_MIN_INTERVAL,
    GROQ_MIN_INTERVAL,
    GEMINI_SYNTHESIS_MODEL,
    GEMINI_FALLBACK_MODEL,
    GROQ_ARTICLE_MODEL,
    GROQ_ARTICLE_FALLBACK_MODEL,
    GROQ_SYNTHESIS_MODEL,
    GROQ_TEXT_MODEL,
    GEMINI_SYNTHESIS_HOURLY_LIMIT,
    GEMINI_SYNTHESIS_DAILY_LIMIT,
    GEMINI_SYNTHESIS_WEEKLY_LIMIT,
    GEMINI_GENERAL_HOURLY_LIMIT,
    GEMINI_GENERAL_DAILY_LIMIT,
    GEMINI_COOLDOWN_429_SECONDS,
    GEMINI_COOLDOWN_DAILY_SECONDS,
    GROQ_HOURLY_LIMIT,
    GROQ_DAILY_LIMIT,
    GROQ_COOLDOWN_429_SECONDS,
    PROVIDER_STATE_FILE,
)


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY and genai else None
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY and Groq else None

_gemini_lock = threading.Lock()
_gemini_last = [0.0]
_groq_lock = threading.Lock()
_groq_last = [0.0]
_state_lock = threading.RLock()
_provider_state_cache = None


def dbg(msg):
    print(f"  [AI] {msg}")


def _uniq(items):
    seen = set()
    ordered = []
    for item in items:
        if item and item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


ARTICLE_GROQ_MODELS = _uniq([GROQ_ARTICLE_MODEL, GROQ_ARTICLE_FALLBACK_MODEL, GROQ_SYNTHESIS_MODEL])
SYNTHESIS_GROQ_MODELS = _uniq([GROQ_SYNTHESIS_MODEL, GROQ_ARTICLE_FALLBACK_MODEL, GROQ_ARTICLE_MODEL])
TEXT_GROQ_MODELS = _uniq([GROQ_TEXT_MODEL, GROQ_SYNTHESIS_MODEL, GROQ_ARTICLE_FALLBACK_MODEL, GROQ_ARTICLE_MODEL])
SYNTHESIS_GEMINI_MODELS = _uniq([GEMINI_SYNTHESIS_MODEL, GEMINI_FALLBACK_MODEL])
GENERAL_GEMINI_MODELS = _uniq([GEMINI_FALLBACK_MODEL, GEMINI_SYNTHESIS_MODEL])


def _default_provider_state():
    return {
        "gemini": {
            "blocked_until": 0.0,
            "last_error": "",
            "usage": {
                "all": [],
                "synthesis": [],
                "general": [],
            },
        },
        "groq": {
            "blocked_until": 0.0,
            "last_error": "",
            "usage": {
                "all": [],
            },
        },
    }


def _prune_usage(items, now):
    week_ago = now - 7 * 24 * 3600
    return [float(ts) for ts in items if isinstance(ts, (int, float)) and float(ts) >= week_ago]


def _load_provider_state_unlocked():
    if not os.path.exists(PROVIDER_STATE_FILE):
        return _default_provider_state()

    try:
        with open(PROVIDER_STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = _default_provider_state()

    defaults = _default_provider_state()
    now = time.time()

    for provider, provider_defaults in defaults.items():
        data.setdefault(provider, {})
        data[provider].setdefault("blocked_until", provider_defaults["blocked_until"])
        data[provider].setdefault("last_error", provider_defaults["last_error"])
        usage = data[provider].setdefault("usage", {})
        for bucket, timestamps in provider_defaults["usage"].items():
            usage[bucket] = _prune_usage(usage.get(bucket, timestamps), now)

    return data


def _get_provider_state():
    global _provider_state_cache
    with _state_lock:
        if _provider_state_cache is None:
            _provider_state_cache = _load_provider_state_unlocked()
        return _provider_state_cache


def _save_provider_state():
    with _state_lock:
        state = _provider_state_cache or _default_provider_state()
        with open(PROVIDER_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)


def _count_recent(timestamps, now, window_seconds):
    cutoff = now - window_seconds
    return sum(1 for ts in timestamps if ts >= cutoff)


def _format_ts(ts):
    if not ts:
        return None
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))


def _set_provider_error(provider, message):
    state = _get_provider_state()
    with _state_lock:
        state[provider]["last_error"] = message[:300]
    _save_provider_state()


def _sync_provider_state_to_hf():
    try:
        from storage_backend import is_configured, push_state

        if is_configured():
            push_state(new_articles=[])
    except Exception:
        pass


def _set_provider_cooldown(provider, seconds, message):
    state = _get_provider_state()
    with _state_lock:
        until = time.time() + max(1, seconds)
        state[provider]["blocked_until"] = max(state[provider].get("blocked_until", 0.0), until)
        state[provider]["last_error"] = message[:300]
    _save_provider_state()
    _sync_provider_state_to_hf()


def _clear_provider_cooldown(provider):
    state = _get_provider_state()
    with _state_lock:
        if state[provider].get("blocked_until", 0.0) < time.time():
            state[provider]["blocked_until"] = 0.0
            if "429" in state[provider].get("last_error", ""):
                state[provider]["last_error"] = ""
    _save_provider_state()


def _record_provider_usage(provider, bucket):
    state = _get_provider_state()
    now = time.time()
    with _state_lock:
        usage = state[provider]["usage"]
        usage["all"] = _prune_usage(usage.get("all", []), now)
        usage["all"].append(now)
        if bucket not in usage:
            usage[bucket] = []
        usage[bucket] = _prune_usage(usage.get(bucket, []), now)
        if bucket != "all":
            usage[bucket].append(now)
    _save_provider_state()


def _bucket_counts(provider, bucket):
    state = _get_provider_state()
    now = time.time()
    usage = state[provider]["usage"]
    bucket_usage = _prune_usage(usage.get(bucket, []), now)
    with _state_lock:
        usage[bucket] = bucket_usage
        usage["all"] = _prune_usage(usage.get("all", []), now)
    return {
        "hour": _count_recent(bucket_usage, now, 3600),
        "day": _count_recent(bucket_usage, now, 86400),
        "week": _count_recent(bucket_usage, now, 7 * 86400),
        "all_hour": _count_recent(usage.get("all", []), now, 3600),
        "all_day": _count_recent(usage.get("all", []), now, 86400),
    }


def _quota_reason(provider, bucket):
    state = _get_provider_state()
    now = time.time()
    blocked_until = float(state[provider].get("blocked_until", 0.0) or 0.0)
    if blocked_until > now:
        return False, f"cooldown until {_format_ts(blocked_until)}"

    counts = _bucket_counts(provider, bucket)

    if provider == "gemini" and bucket == "synthesis":
        if counts["hour"] >= GEMINI_SYNTHESIS_HOURLY_LIMIT:
            return False, "synthesis hourly budget exhausted"
        if counts["day"] >= GEMINI_SYNTHESIS_DAILY_LIMIT:
            return False, "synthesis daily budget exhausted"
        if counts["week"] >= GEMINI_SYNTHESIS_WEEKLY_LIMIT:
            return False, "synthesis weekly budget exhausted"

    if provider == "gemini" and bucket == "general":
        if counts["hour"] >= GEMINI_GENERAL_HOURLY_LIMIT:
            return False, "general hourly budget exhausted"
        if counts["day"] >= GEMINI_GENERAL_DAILY_LIMIT:
            return False, "general daily budget exhausted"

    if provider == "groq":
        if counts["all_hour"] >= GROQ_HOURLY_LIMIT:
            return False, "hourly budget exhausted"
        if counts["all_day"] >= GROQ_DAILY_LIMIT:
            return False, "daily budget exhausted"

    return True, ""


def _claim_provider_slot(provider, bucket, interval, lock, last_ref, label):
    allowed, reason = _quota_reason(provider, bucket)
    if not allowed:
        dbg(f"{label} skipped: {reason}")
        return False

    with lock:
        now = time.time()
        elapsed = now - last_ref[0]
        if elapsed < interval:
            wait = interval - elapsed
            dbg(f"{label} rate slot: sleeping {wait:.1f}s")
            time.sleep(wait)
        last_ref[0] = time.time()
        _record_provider_usage(provider, bucket)
    return True


def _gemini_cooldown_seconds(message):
    text = message.lower()
    if "per day" in text or "daily" in text or "quota" in text:
        return GEMINI_COOLDOWN_DAILY_SECONDS
    return GEMINI_COOLDOWN_429_SECONDS


def _groq_cooldown_seconds(message):
    return GROQ_COOLDOWN_429_SECONDS


if types:
    _SAFETY = [
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
    ]
else:
    _SAFETY = []


SYSTEM_PROMPT = """You are an elite intelligence analyst covering cybersecurity, AI, technology, hardware, and mobile.
Your job is to deeply analyze articles and extract structured intelligence.
You MUST return ONLY valid JSON. If you need to use quotes inside a string, you MUST escape them like this: \\" """


def build_analysis_prompt(title, content):
    safe_content = content[:AI_MAX_CONTENT_CHARS]
    return f"""{SYSTEM_PROMPT}

Analyze this article completely.

Title: {title}
Content:
{safe_content}

Return this exact JSON:
{{
  "severity": "CRITICAL|HIGH|MEDIUM|LOW|MINIMAL",
  "category": "cybersec|ai|tech|mobile|hardware|newsletter|business",
  "confidence": 1-10,
  "summary":[
    "Key finding or vulnerability detail",
    "Attack method or mechanism",
    "Real-world effect",
    "Fix, patch, or mitigation"
  ],
  "tags":["tag1", "tag2"],
  "cves":["CVE-YYYY-NNNNN"],
  "actors": ["threat actor if any"],
  "affected_products":["product names if any"]
}}

SEVERITY GUIDE:
- CRITICAL: Active exploit, zero-day, mass impact
- HIGH: Serious vulnerability, targeted attack
- MEDIUM: Patched CVE, phishing campaign
- LOW: General tech news
- MINIMAL: Marketing fluff

Fill all fields. If not applicable, use empty list [].
Return ONLY the JSON object."""


def build_digest_prompt(items_text, cycle_label):
    return f"""{SYSTEM_PROMPT}
You are the Editor-in-Chief of an elite tech and threat intelligence magazine.
Write a comprehensive briefing combining these stories. Do NOT just list titles.

Items:
{items_text}

Return this exact JSON:
{{
  "headline": "One punchy, engaging sentence capturing the cycle's most important news",
  "cybersec_updates":[
    "Detailed paragraph about a major cybersec event, including threat actors and impact",
    "Detailed paragraph about another cybersec trend or vulnerability"
  ],
  "ai_updates":[
    "Detailed paragraph summarizing AI models, features, or regulations"
  ],
  "tech_business_updates":[
    "Detailed paragraph about general tech, acquisitions, or software"
  ],
  "hardware_mobile_updates":[
    "Detailed paragraph about chips, phones, or hardware vulnerabilities"
  ],
  "key_cves":["CVE-YYYY-NNNNN: Brief explanation of what this CVE affects"],
  "strategic_note": "A final concluding paragraph on what this cycle means strategically."
}}
Return ONLY the JSON object."""


def build_daily_prompt(digests_text):
    return f"""{SYSTEM_PROMPT}
Perform deep correlation and pattern analysis across these daily digests to write an Executive Daily Briefing.

Digests:
{digests_text}

Return this exact JSON:
{{
  "day_headline": "Most critical finding or theme of the entire day",
  "escalating_threats": ["Threats that appeared multiple times and are growing"],
  "new_patterns":["New patterns not obvious in individual digests"],
  "actor_activity":["Notable threat actor activity"],
  "critical_cves":["CVE-YYYY-NNNNN: Brief explanation of what this CVE affects"],
  "tech_trends": ["Major tech/AI/hardware trends"],
  "recommendations":[
    "Action to take based on today's intelligence"
  ],
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
  "day_summary": "3-4 sentence paragraph summarizing the entire day"
}}
Return ONLY the JSON object."""


def build_weekly_prompt(digests_text):
    return f"""{SYSTEM_PROMPT}
You are generating the special 'Doom vs. Bloom' Sunday Weekly Intelligence Digest.
Analyze the top items from the past 7 days.

Items:
{digests_text}

Return this exact JSON:
{{
  "day_headline": "One catchy, engaging headline summarizing the entire week",
  "doom":[
    "Paragraph detailing the worst hacks, APT activity, and critical vulnerabilities of the week",
    "Paragraph detailing ransomware, supply chain attacks, or escalating threats"
  ],
  "bloom":[
    "Paragraph detailing the most exciting AI breakthroughs, tech innovations, or hardware releases",
    "Paragraph detailing positive security defenses, patches, or law enforcement wins"
  ],
  "key_cves":["CVE-YYYY-NNNNN: Brief explanation of the week's most critical CVE"],
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
  "day_summary": "A high-level concluding summary of the entire week."
}}
Return ONLY the JSON object."""


def extract_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(text[start:end])
    except Exception as e:
        dbg(f"JSON parse error: {e}")
        return None


_CRITICAL_KW = [
    "rce", "remote code execution", "zero-day", "0-day", "actively exploited",
    "supply chain attack", "authentication bypass", "unauthenticated rce",
    "mass exploitation", "emergency patch", "in the wild",
]
_HIGH_KW = [
    "privilege escalation", "malware", "apt", "ransomware", "breach",
    "data leak", "backdoor", "trojan", "phishing campaign", "critical vulnerability",
]
_MEDIUM_KW = [
    "cve", "patch", "vulnerability", "advisory", "security fix",
    "exploit", "attack", "compromised", "injection",
]


def keyword_severity(title: str, content: str = "") -> str:
    text = (title + " " + content).lower()
    score = 0
    for kw in _CRITICAL_KW:
        if kw in text:
            score += 4
    for kw in _HIGH_KW:
        if kw in text:
            score += 2
    for kw in _MEDIUM_KW:
        if kw in text:
            score += 1

    if score >= 12:
        return "CRITICAL"
    if score >= 7:
        return "HIGH"
    if score >= 3:
        return "MEDIUM"
    if score >= 1:
        return "LOW"
    return "MINIMAL"


def _groq_json_call(prompt: str, models: list[str], retries: int = 2) -> str | None:
    if not groq_client:
        return None

    for model in models:
        for attempt in range(1, retries + 1):
            if not _claim_provider_slot("groq", "all", GROQ_MIN_INTERVAL, _groq_lock, _groq_last, f"Groq({model[:18]})"):
                return None
            try:
                dbg(f"Groq JSON call [{model}] attempt {attempt}/{retries}")
                chat = groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    response_format={"type": "json_object"},
                    timeout=45,
                )
                _clear_provider_cooldown("groq")
                return chat.choices[0].message.content
            except Exception as e:
                message = str(e)
                lower = message.lower()
                if "429" in lower or "rate" in lower or "too_many" in lower:
                    cooldown = _groq_cooldown_seconds(message)
                    _set_provider_cooldown("groq", cooldown, message)
                    dbg(f"Groq 429 on {model}; cooling down for {cooldown}s")
                    break
                if "model" in lower and "not found" in lower:
                    _set_provider_error("groq", message)
                    dbg(f"Groq model unavailable: {model}")
                    break
                _set_provider_error("groq", message)
                dbg(f"Groq error on {model}: {e}")
                if attempt < retries:
                    time.sleep(min(5, attempt * 2))
    return None


def _groq_text_call(prompt: str, models: list[str], retries: int = 2) -> str | None:
    if not groq_client:
        return None

    for model in models:
        for attempt in range(1, retries + 1):
            if not _claim_provider_slot("groq", "all", GROQ_MIN_INTERVAL, _groq_lock, _groq_last, f"Groq-text({model[:18]})"):
                return None
            try:
                dbg(f"Groq TEXT call [{model}] attempt {attempt}/{retries}")
                chat = groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    timeout=60,
                )
                _clear_provider_cooldown("groq")
                return chat.choices[0].message.content
            except Exception as e:
                message = str(e)
                lower = message.lower()
                if "429" in lower or "rate" in lower or "too_many" in lower:
                    cooldown = _groq_cooldown_seconds(message)
                    _set_provider_cooldown("groq", cooldown, message)
                    dbg(f"Groq TEXT 429 on {model}; cooling down for {cooldown}s")
                    break
                if "model" in lower and "not found" in lower:
                    _set_provider_error("groq", message)
                    dbg(f"Groq text model unavailable: {model}")
                    break
                _set_provider_error("groq", message)
                dbg(f"Groq text error on {model}: {e}")
                if attempt < retries:
                    time.sleep(min(5, attempt * 2))
    return None


def _gemini_call(prompt: str, models: list[str], bucket: str, json_mode: bool, retries: int = 2) -> str | None:
    if not gemini_client:
        return None

    for model in models:
        for attempt in range(1, retries + 1):
            if not _claim_provider_slot("gemini", bucket, GEMINI_MIN_INTERVAL, _gemini_lock, _gemini_last, f"Gemini({model})"):
                return None
            try:
                dbg(f"Gemini call [{model}] bucket={bucket} attempt {attempt}/{retries}")
                config = types.GenerateContentConfig(safety_settings=_SAFETY) if types else None
                if json_mode and config is not None:
                    config.response_mime_type = "application/json"

                kwargs = {"model": model, "contents": prompt}
                if config is not None:
                    kwargs["config"] = config
                response = gemini_client.models.generate_content(**kwargs)
                _clear_provider_cooldown("gemini")
                return response.text
            except Exception as e:
                message = str(e)
                lower = message.lower()
                if "429" in lower or "quota" in lower or "resource_exhausted" in lower:
                    cooldown = _gemini_cooldown_seconds(message)
                    _set_provider_cooldown("gemini", cooldown, message)
                    dbg(f"Gemini 429 on {model}; cooling down for {cooldown}s")
                    break
                if "503" in lower or "unavailable" in lower:
                    _set_provider_error("gemini", message)
                    time.sleep(10 + random.uniform(0, 3))
                    continue
                if "model" in lower and "not found" in lower:
                    _set_provider_error("gemini", message)
                    dbg(f"Gemini model unavailable: {model}")
                    break
                _set_provider_error("gemini", message)
                dbg(f"Gemini error on {model}: {e}")
                if attempt < retries:
                    time.sleep(5)
    return None


def ai_analyze(title: str, content: str) -> dict:
    prompt = build_analysis_prompt(title, content)
    raw = local_call_article(prompt)
    data = extract_json(raw)

    kw_sev = keyword_severity(title, content)
    sev_order = ["MINIMAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"]

    if data:
        ai_sev = data.get("severity", "LOW")
        ai_idx = sev_order.index(ai_sev) if ai_sev in sev_order else 2
        kw_idx = sev_order.index(kw_sev) if kw_sev in sev_order else 1
        data["severity"] = sev_order[max(ai_idx, kw_idx)]
        return data

    dbg("AI failed — using keyword fallback for this article")
    return {
        "severity": kw_sev,
        "category": "tech",
        "confidence": 1,
        "summary": ["AI analysis unavailable — keyword classification used"],
        "tags": [],
        "cves": [],
        "actors": [],
        "affected_products": [],
    }


def ai_digest(items: list, cycle_label: str = "8-hour cycle") -> dict | None:
    sev_map = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "MINIMAL": 1}
    sorted_items = sorted(items, key=lambda x: sev_map.get(x.get("severity", "LOW"), 0), reverse=True)

    items_text = ""
    for item in sorted_items:
        summary = item.get("summary", "")
        if isinstance(summary, list):
            summary = " | ".join(summary)
        items_text += (
            f"[{item.get('severity', '?')}][{item.get('category', 'tech')}] "
            f"{item.get('title', '')}\n  {summary[:250]}\n\n"
        )
        if len(items_text) > 8000:
            break

    raw = local_call(build_digest_prompt(items_text, cycle_label))
    return extract_json(raw)


def ai_daily_summary(digests: list) -> dict | None:
    digests_text = ""
    for idx, digest in enumerate(digests, 1):
        digests_text += f"\n--- DIGEST {idx} ---\n{json.dumps(digest, indent=2)}\n"

    raw = local_call(build_daily_prompt(digests_text[:12000]))
    return extract_json(raw)


def ai_weekly_summary(items: list) -> dict | None:
    sev_map = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "MINIMAL": 1}
    sorted_items = sorted(items, key=lambda x: sev_map.get(x.get("severity", "LOW"), 0), reverse=True)

    items_text = ""
    for item in sorted_items[:40]:
        items_text += f"[{item.get('severity', '?')}] {item.get('title', '')}\n  {item.get('summary_text', '')[:200]}\n\n"

    raw = local_call(build_weekly_prompt(items_text[:12000]))
    return extract_json(raw)


def local_call(prompt: str) -> str | None:
    """
    Scheduled synthesis router.
    Gemini is reserved here for 8h, daily, weekly, and newsletter-quality output.
    """
    result = _gemini_call(prompt, SYNTHESIS_GEMINI_MODELS, bucket="synthesis", json_mode=True)
    if result:
        return result

    dbg("Gemini synthesis unavailable — falling back to Groq synthesis")
    return _groq_json_call(prompt, SYNTHESIS_GROQ_MODELS)


def local_call_general_json(prompt: str) -> str | None:
    """
    Interactive JSON router.
    Groq first so bot features do not spend the reserved Gemini synthesis budget.
    """
    result = _groq_json_call(prompt, ARTICLE_GROQ_MODELS)
    if result:
        return result

    dbg("Groq JSON unavailable — trying Gemini general fallback")
    return _gemini_call(prompt, GENERAL_GEMINI_MODELS, bucket="general", json_mode=True)


def local_call_article(prompt: str) -> str | None:
    result = _groq_json_call(prompt, ARTICLE_GROQ_MODELS)
    if result:
        return result

    dbg("Groq article route unavailable — trying Gemini fallback")
    return _gemini_call(prompt, GENERAL_GEMINI_MODELS, bucket="general", json_mode=True)


def local_call_text(prompt: str) -> str | None:
    result = _groq_text_call(prompt, TEXT_GROQ_MODELS)
    if result:
        return result

    dbg("Groq text route unavailable — trying Gemini general fallback")
    return _gemini_call(prompt, GENERAL_GEMINI_MODELS, bucket="general", json_mode=False)


def get_provider_status() -> dict:
    state = copy.deepcopy(_get_provider_state())
    now = time.time()

    gemini_counts = _bucket_counts("gemini", "general")
    gemini_synth_counts = _bucket_counts("gemini", "synthesis")
    groq_counts = _bucket_counts("groq", "all")

    def provider_state(provider_name, blocked_until, last_error, usage):
        provider_status = "ready"
        if blocked_until and blocked_until > now:
            provider_status = "cooldown"
        elif "exhausted" in last_error.lower():
            provider_status = "budget_guarded"
        elif last_error:
            provider_status = "degraded"
        return {
            "state": provider_status,
            "blocked_until": _format_ts(blocked_until),
            "last_error": last_error,
            "usage": usage,
        }

    return {
        "gemini": provider_state(
            "gemini",
            state["gemini"].get("blocked_until", 0.0),
            state["gemini"].get("last_error", ""),
            {
                "hour": gemini_counts["hour"],
                "day": gemini_counts["day"],
                "week": gemini_counts["week"],
                "synthesis_hour": gemini_synth_counts["hour"],
                "synthesis_day": gemini_synth_counts["day"],
                "synthesis_week": gemini_synth_counts["week"],
            },
        ),
        "groq": provider_state(
            "groq",
            state["groq"].get("blocked_until", 0.0),
            state["groq"].get("last_error", ""),
            {
                "hour": groq_counts["all_hour"],
                "day": groq_counts["all_day"],
                "week": groq_counts["week"],
            },
        ),
    }
