"""
ai_router.py
Smart dual-API routing:

  PER-ARTICLE ANALYSIS  → Groq PRIMARY  → Gemini fallback
  DIGEST / DAILY / WEEKLY → Gemini PRIMARY → Groq-70b fallback
  DEEPDIVE / QUIZ (text)  → Gemini PRIMARY → Groq-70b fallback

Why this split:
  - Groq llama-3.1-8b: 30 RPM free, ~2s latency → perfect for bulk article analysis
  - Gemini 2.5 Flash: 15 RPM free, better reasoning → saved for low-volume synthesis
  - Result: 440 articles processed in ~25 min instead of 53 hours
"""

import json
import time
import os
import random
import threading

from google import genai
from google.genai import types
from groq import Groq

from config import (
    AI_MAX_CONTENT_CHARS,
    GEMINI_MIN_INTERVAL,
    GROQ_MIN_INTERVAL,
)

# ─────────────────────────────────────────────────────────────
# CLIENT SETUP
# ─────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
groq_client   = Groq(api_key=GROQ_API_KEY)           if GROQ_API_KEY   else None


# ─────────────────────────────────────────────────────────────
# THREAD-SAFE PER-API RATE LIMITERS
# (Bot listener thread uses Gemini/Groq too — separate locks prevent deadlock)
# ─────────────────────────────────────────────────────────────

_gemini_lock = threading.Lock()
_gemini_last = [0.0]   # mutable list so inner fn can update

_groq_lock   = threading.Lock()
_groq_last   = [0.0]


def _wait_for_slot(lock, last_ref, interval, name):
    with lock:
        now     = time.time()
        elapsed = now - last_ref[0]
        if elapsed < interval:
            wait = interval - elapsed
            print(f"  [AI] {name} rate slot: sleeping {wait:.1f}s")
            time.sleep(wait)
        last_ref[0] = time.time()


def dbg(msg):
    print(f"  [AI] {msg}")


# ─────────────────────────────────────────────────────────────
# SAFETY SETTINGS (allow cybersec content)
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# PROMPT BUILDERS  (unchanged from original)
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# ENGINE CALLS  (JSON mode — for structured analysis)
# ─────────────────────────────────────────────────────────────




# ─────────────────────────────────────────────────────────────
# JSON PARSER
# ─────────────────────────────────────────────────────────────

def extract_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(text[start:end])
    except Exception as e:
        dbg(f"JSON parse error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# KEYWORD SEVERITY  (backup classifier + pre-screen)
# ─────────────────────────────────────────────────────────────

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
    text  = (title + " " + content).lower()
    score = 0
    for k in _CRITICAL_KW:
        if k in text: score += 4
    for k in _HIGH_KW:
        if k in text: score += 2
    for k in _MEDIUM_KW:
        if k in text: score += 1

    if score >= 12: return "CRITICAL"
    if score >= 7:  return "HIGH"
    if score >= 3:  return "MEDIUM"
    if score >= 1:  return "LOW"
    return "MINIMAL"


# ─────────────────────────────────────────────────────────────
# PUBLIC ANALYSIS FUNCTIONS  (ALL articles get full AI — per user request)
# ─────────────────────────────────────────────────────────────

def ai_analyze(title: str, content: str) -> dict:
    """
    Full AI analysis of a single article.
    Uses Groq (fast, 30 RPM) as primary — saves Gemini quota for synthesis.
    """
    prompt = build_analysis_prompt(title, content)
    raw    = local_call_article(prompt)   # ← Groq-primary route
    data   = extract_json(raw)

    kw_sev    = keyword_severity(title, content)
    sev_order = ["MINIMAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"]

    if data:
        ai_sev = data.get("severity", "LOW")
        ai_idx = sev_order.index(ai_sev) if ai_sev in sev_order else 2
        kw_idx = sev_order.index(kw_sev) if kw_sev in sev_order else 1
        # Take the higher of AI vs keyword (never downgrade)
        data["severity"] = sev_order[max(ai_idx, kw_idx)]
        return data

    dbg("AI failed — using keyword fallback for this article")
    return {
        "severity":          kw_sev,
        "category":          "tech",
        "confidence":        1,
        "summary":           ["AI analysis unavailable — keyword classification used"],
        "tags":              [],
        "cves":              [],
        "actors":            [],
        "affected_products": [],
    }


def ai_digest(items: list, cycle_label: str = "8-hour cycle") -> dict | None:
    sev_map = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "MINIMAL": 1}
    sorted_items = sorted(
        items, key=lambda x: sev_map.get(x.get("severity", "LOW"), 0), reverse=True
    )

    items_text = ""
    for item in sorted_items:
        summary = item.get("summary", "")
        if isinstance(summary, list):
            summary = " | ".join(summary)
        items_text += (
            f"[{item.get('severity','?')}][{item.get('category','tech')}] "
            f"{item.get('title','')}\n  {summary[:250]}\n\n"
        )
        if len(items_text) > 8000:
            break

    raw = local_call(build_digest_prompt(items_text, cycle_label))
    return extract_json(raw)


def ai_daily_summary(digests: list) -> dict | None:
    digests_text = ""
    for i, d in enumerate(digests, 1):
        digests_text += f"\n--- DIGEST {i} ---\n{json.dumps(d, indent=2)}\n"

    raw = local_call(build_daily_prompt(digests_text[:12000]))
    return extract_json(raw)


def ai_weekly_summary(items: list) -> dict | None:
    sev_map = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "MINIMAL": 1}
    sorted_items = sorted(
        items, key=lambda x: sev_map.get(x.get("severity", "LOW"), 0), reverse=True
    )

    items_text = ""
    for item in sorted_items[:40]:
        summary = item.get("summary_text", "")
        items_text += f"[{item.get('severity','?')}] {item.get('title','')}\n  {summary[:200]}\n\n"

    raw = local_call(build_weekly_prompt(items_text[:12000]))
    return extract_json(raw)

# ─────────────────────────────────────────────────────────────
# ENGINE CALLS
# ─────────────────────────────────────────────────────────────

# ── GROQ ── (Primary for bulk article analysis — 30 RPM, fast)

def groq_call(prompt: str, model: str = "llama-3.1-8b-instant", retries: int = 3) -> str | None:
    """
    JSON-mode Groq call.
    Default model: llama-3.1-8b-instant (30 RPM, fastest for bulk).
    Pass model="llama-3.3-70b-versatile" for synthesis fallback.
    """
    if not groq_client:
        return None

    for attempt in range(1, retries + 1):
        _wait_for_slot(_groq_lock, _groq_last, GROQ_MIN_INTERVAL, f"Groq({model[:12]})")
        try:
            dbg(f"Groq JSON call [{model[:20]}] attempt {attempt}/{retries}")
            chat = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                response_format={"type": "json_object"},
                timeout=45,
            )
            return chat.choices[0].message.content
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err or "too_many" in err:
                # Groq 429 is usually just RPM — wait retry_after or short backoff
                retry_after = 5 * attempt   # 5s, 10s, 15s — NOT 30s/60s
                dbg(f"Groq 429 — backing off {retry_after}s (attempt {attempt}/{retries})")
                time.sleep(retry_after)
            elif "model" in err and "not found" in err:
                dbg(f"Groq model not found: {model} — aborting")
                return None
            else:
                dbg(f"Groq error: {e}")
                if attempt < retries:
                    time.sleep(3)
                else:
                    return None

    dbg("Groq: all retries exhausted")
    return None


def groq_call_text(prompt: str, model: str = "llama-3.3-70b-versatile", retries: int = 3) -> str | None:
    """Plain-text Groq call for deepdive dossiers (no JSON forced)."""
    if not groq_client:
        return None

    for attempt in range(1, retries + 1):
        _wait_for_slot(_groq_lock, _groq_last, GROQ_MIN_INTERVAL, f"Groq-text({model[:12]})")
        try:
            dbg(f"Groq TEXT call [{model[:20]}] attempt {attempt}/{retries}")
            chat = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                timeout=60,
            )
            return chat.choices[0].message.content
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err:
                retry_after = 5 * attempt
                dbg(f"Groq-text 429 — backing off {retry_after}s")
                time.sleep(retry_after)
            else:
                dbg(f"Groq-text error: {e}")
                if attempt < retries:
                    time.sleep(3)
                else:
                    return None

    return None


# ── GEMINI ── (Primary for synthesis — better reasoning, saved for important tasks)

def gemini_call(prompt: str, retries: int = 3) -> str | None:
    """JSON-mode Gemini 2.5 Flash call. Used for digests, daily, weekly summaries."""
    if not gemini_client:
        return None

    for attempt in range(1, retries + 1):
        _wait_for_slot(_gemini_lock, _gemini_last, GEMINI_MIN_INTERVAL, "Gemini")
        try:
            dbg(f"Gemini JSON call (attempt {attempt}/{retries})")
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    safety_settings=_SAFETY,
                ),
            )
            return response.text
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "quota" in err or "resource_exhausted" in err:
                # Gemini 429 needs longer backoff (TPM + RPM limits)
                wait = (2 ** attempt) * 20 + random.uniform(0, 10)  # 40s, 80s, 160s
                dbg(f"Gemini 429 — backing off {wait:.0f}s (attempt {attempt}/{retries})")
                time.sleep(wait)
            elif "503" in err or "unavailable" in err:
                time.sleep(15 + random.uniform(0, 5))
            else:
                dbg(f"Gemini error: {e}")
                return None

    dbg("Gemini: all retries exhausted")
    return None


def gemini_call_text(prompt: str, retries: int = 3) -> str | None:
    """Plain-text Gemini call for deepdive (no JSON mode). Better formatting."""
    if not gemini_client:
        return None

    for attempt in range(1, retries + 1):
        _wait_for_slot(_gemini_lock, _gemini_last, GEMINI_MIN_INTERVAL, "Gemini-text")
        try:
            dbg(f"Gemini TEXT call (attempt {attempt}/{retries})")
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(safety_settings=_SAFETY),
            )
            return response.text
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "quota" in err or "resource_exhausted" in err:
                wait = (2 ** attempt) * 20 + random.uniform(0, 10)
                dbg(f"Gemini-text 429 — backing off {wait:.0f}s")
                time.sleep(wait)
            elif "503" in err or "unavailable" in err:
                time.sleep(15)
            else:
                dbg(f"Gemini-text error: {e}")
                return None

    return None


# ─────────────────────────────────────────────────────────────
# ROUTERS — smart model selection by task type
# ─────────────────────────────────────────────────────────────

def local_call(prompt: str) -> str | None:
    """
    SYNTHESIS router (digest / daily / weekly / quiz).
    Gemini 2.5 Flash PRIMARY → Groq 70b fallback.
    High quality needed, low volume.
    """
    result = gemini_call(prompt)
    if not result:
        dbg("Gemini failed — trying Groq-70b fallback for synthesis")
        result = groq_call(prompt, model="llama-3.3-70b-versatile")
    return result


def local_call_article(prompt: str) -> str | None:
    """
    ARTICLE ANALYSIS router (bulk, per-article).
    Groq 8b PRIMARY → Gemini fallback.
    Speed matters — Groq handles 30 RPM vs Gemini's 15 RPM.
    """
    result = groq_call(prompt, model="llama-3.1-8b-instant")
    if not result:
        dbg("Groq failed — trying Gemini fallback for article")
        result = gemini_call(prompt)
    return result


def local_call_text(prompt: str) -> str | None:
    """
    TEXT router for deepdive dossiers (plain markdown, not JSON).
    Gemini PRIMARY (better prose) → Groq-70b fallback.
    """
    result = gemini_call_text(prompt)
    if not result:
        dbg("Gemini-text failed — trying Groq-70b text fallback")
        result = groq_call_text(prompt, model="llama-3.3-70b-versatile")
    return result

