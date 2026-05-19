"""
ai_router.py — Smart multi-tier AI routing.

Model tiers:
  PREMIUM  (daily/weekly synthesis) → gemini-2.5-pro  → gemini-2.5-flash fallback
  STANDARD (cycle digest / quiz)    → gemini-2.5-flash → groq-70b fallback
  FAST     (per-article analysis)   → groq-8b          → gemini-2.5-flash fallback
  TEXT     (deepdive dossiers)      → gemini-2.5-flash → groq-70b fallback

gemini-2.5-pro free tier: 5 RPM / 25 RPD — used only for daily & weekly (2-3 calls/day).
gemini-2.5-flash free tier: 15 RPM — used for cycle digests & fallback.
groq llama-3.1-8b: 30 RPM — bulk per-article analysis.
"""

import json, time, os, random, threading
from google import genai
from google.genai import types
from groq import Groq
from config import AI_MAX_CONTENT_CHARS, GEMINI_MIN_INTERVAL, GROQ_MIN_INTERVAL

# ─── Clients ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY","")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY","")
gemini_client  = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
groq_client    = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ─── Rate limiters (per-API, thread-safe) ─────────────────────────────────────
_gemini_lock = threading.Lock(); _gemini_last = [0.0]
_groq_lock   = threading.Lock(); _groq_last   = [0.0]
# Pro has stricter 5 RPM limit → 12s minimum
_GEMINI_PRO_INTERVAL = 13.0

def _wait(lock, last_ref, interval, name):
    with lock:
        elapsed = time.time()-last_ref[0]
        if elapsed < interval:
            w = interval-elapsed
            print(f"  [AI] {name} rate slot: sleeping {w:.1f}s")
            time.sleep(w)
        last_ref[0] = time.time()

def dbg(msg): print(f"  [AI] {msg}")

# ─── Safety (allow cybersec content) ─────────────────────────────────────────
_SAFETY = [
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,        threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,         threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,  threshold=types.HarmBlockThreshold.BLOCK_NONE),
    types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,  threshold=types.HarmBlockThreshold.BLOCK_NONE),
]

# ─── System Prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are JARVIS — a senior intelligence analyst specialising in cybersecurity, artificial intelligence, enterprise technology, hardware, and mobile platforms.
Produce concise, factual, professional-grade intelligence assessments.
Avoid marketing language and speculation. Use precise technical terminology.
You MUST return ONLY valid JSON as specified. Escape internal quotes with \\\"."""

# ─── Prompts ──────────────────────────────────────────────────────────────────
def build_analysis_prompt(title, content):
    return f"""{SYSTEM_PROMPT}

Analyse the following article and extract structured intelligence.

Title: {title}
Content:
{content[:AI_MAX_CONTENT_CHARS]}

Return this exact JSON structure:
{{
  "severity": "CRITICAL|HIGH|MEDIUM|LOW|MINIMAL",
  "category": "cybersec|ai|tech|mobile|hardware|newsletter|business",
  "confidence": 1-10,
  "summary": [
    "Primary threat, vulnerability, or key finding",
    "Attack vector, mechanism, or technical detail",
    "Real-world impact or affected systems",
    "Mitigation, patch, or recommended action"
  ],
  "tags": ["tag1","tag2"],
  "cves": ["CVE-YYYY-NNNNN"],
  "actors": ["threat actor name"],
  "affected_products": ["product or platform name"]
}}

SEVERITY CRITERIA:
- CRITICAL: Active exploitation, zero-day, mass impact, unauthenticated RCE
- HIGH: Serious unpatched vulnerability, confirmed targeted attack, significant breach
- MEDIUM: Patched CVE, contained phishing campaign, notable security advisory
- LOW: General technology news, product announcement, industry development
- MINIMAL: Marketing content, opinion pieces, non-technical articles

IMPORTANT: "category" must be a SINGLE value from the list above. Never use pipe-separated values.
Return ONLY the JSON object. No preamble, no explanation."""


def build_digest_prompt(items_text, cycle_label):
    return f"""{SYSTEM_PROMPT}

Compose a structured intelligence briefing for the {cycle_label} cycle.
Synthesise the following items into a coherent analytical report — do not merely list headlines.

Items:
{items_text}

Return this exact JSON:
{{
  "headline": "Single authoritative sentence capturing the most significant development of this cycle",
  "cybersec_updates": [
    "Detailed analytical paragraph on a major cybersecurity event, including threat actors, CVEs, and operational impact",
    "Analytical paragraph on additional cybersecurity developments or emerging trends"
  ],
  "ai_updates": [
    "Analytical paragraph on AI model releases, regulatory developments, or security implications of AI systems"
  ],
  "tech_business_updates": [
    "Analytical paragraph on enterprise technology, acquisitions, policy changes, or platform developments"
  ],
  "hardware_mobile_updates": [
    "Analytical paragraph on hardware vulnerabilities, chip developments, or mobile security issues"
  ],
  "key_cves": ["CVE-YYYY-NNNNN: Precise description of what this vulnerability affects and its severity"],
  "strategic_note": "Concluding analytical paragraph on the strategic significance of this cycle's intelligence."
}}
Return ONLY the JSON object."""


def build_daily_prompt(digests_text):
    return f"""{SYSTEM_PROMPT}

Perform cross-cycle correlation and pattern analysis across the following intelligence digests.
Produce an Executive Daily Intelligence Briefing suitable for a CISO or senior security leader.

Digests:
{digests_text}

Return this exact JSON:
{{
  "day_headline": "Single authoritative sentence capturing the most critical finding of the day",
  "escalating_threats": [
    "Threat that appeared across multiple cycles, indicating sustained or growing activity",
    "Secondary escalating threat with evidence of persistence"
  ],
  "new_patterns": [
    "Cross-cycle pattern not visible in any single digest",
    "Correlation between seemingly unrelated events"
  ],
  "actor_activity": [
    "Named threat actor activity with attribution confidence and observed TTPs"
  ],
  "critical_cves": ["CVE-YYYY-NNNNN: Concise technical description and affected systems"],
  "tech_trends": [
    "Significant technology or AI development with strategic implications",
    "Hardware or mobile development worth monitoring"
  ],
  "recommendations": [
    "Specific, actionable security recommendation based on today's intelligence",
    "Strategic recommendation for risk reduction"
  ],
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
  "day_summary": "Three to four sentence executive summary of the day's most significant intelligence findings and their collective strategic implications."
}}
Return ONLY the JSON object."""


def build_weekly_prompt(items_text):
    return f"""{SYSTEM_PROMPT}

Produce the Sunday 'Doom vs. Bloom' Weekly Intelligence Digest — a premium analytical report
covering the most significant developments of the past seven days.

Source intelligence (top items by severity):
{items_text}

Return this exact JSON:
{{
  "day_headline": "Compelling, authoritative headline capturing the defining narrative of the week",
  "doom": [
    "Analytical paragraph on the week's most serious threat activity: major breaches, APT campaigns, critical vulnerabilities, ransomware operations",
    "Analytical paragraph on escalating threat trends, supply chain risks, or law enforcement/regulatory failures"
  ],
  "bloom": [
    "Analytical paragraph on significant AI breakthroughs, positive security innovations, or major product advances",
    "Analytical paragraph on law enforcement wins, successful defences, or technology milestones"
  ],
  "key_cves": ["CVE-YYYY-NNNNN: Technical summary of the week's most critical vulnerability"],
  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW",
  "day_summary": "Executive summary paragraph synthesising the week's overall threat posture, key trends, and strategic outlook for the coming week."
}}
Return ONLY the JSON object."""


# ─── JSON Parser ──────────────────────────────────────────────────────────────
def extract_json(text: str) -> dict | None:
    if not text: return None
    try:
        text  = text.replace("```json","").replace("```","").strip()
        start = text.find("{"); end = text.rfind("}")+1
        if start==-1 or end==0: return None
        return json.loads(text[start:end])
    except Exception as e:
        dbg(f"JSON parse error: {e}")
        return None


# ─── Keyword Severity Fallback ────────────────────────────────────────────────
_CRITICAL_KW = ["rce","remote code execution","zero-day","0-day","actively exploited",
                "supply chain attack","authentication bypass","unauthenticated rce",
                "mass exploitation","emergency patch","in the wild"]
_HIGH_KW     = ["privilege escalation","malware","apt","ransomware","breach",
                "data leak","backdoor","trojan","phishing campaign","critical vulnerability"]
_MEDIUM_KW   = ["cve","patch","vulnerability","advisory","security fix",
                "exploit","attack","compromised","injection"]

def keyword_severity(title, content=""):
    text  = (title+" "+content).lower()
    score = sum(4 for k in _CRITICAL_KW if k in text) + \
            sum(2 for k in _HIGH_KW     if k in text) + \
            sum(1 for k in _MEDIUM_KW   if k in text)
    if score>=12: return "CRITICAL"
    if score>=7:  return "HIGH"
    if score>=3:  return "MEDIUM"
    if score>=1:  return "LOW"
    return "MINIMAL"


# ─── Engine: Groq ─────────────────────────────────────────────────────────────
def groq_call(prompt, model="llama-3.1-8b-instant", retries=3):
    if not groq_client: return None
    for attempt in range(1, retries+1):
        _wait(_groq_lock, _groq_last, GROQ_MIN_INTERVAL, f"Groq({model[:12]})")
        try:
            dbg(f"Groq JSON call [{model[:20]}] attempt {attempt}/{retries}")
            chat = groq_client.chat.completions.create(
                messages=[{"role":"user","content":prompt}],
                model=model, response_format={"type":"json_object"}, timeout=45)
            return chat.choices[0].message.content
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err:
                t = 5*attempt; dbg(f"Groq 429 — backoff {t}s"); time.sleep(t)
            elif "model" in err and "not found" in err:
                dbg(f"Groq model not found: {model}"); return None
            else:
                dbg(f"Groq error: {e}")
                if attempt<retries: time.sleep(3)
                else: return None
    dbg("Groq: all retries exhausted"); return None


def groq_call_text(prompt, model="llama-3.3-70b-versatile", retries=3):
    if not groq_client: return None
    for attempt in range(1, retries+1):
        _wait(_groq_lock, _groq_last, GROQ_MIN_INTERVAL, f"Groq-text({model[:12]})")
        try:
            dbg(f"Groq TEXT call [{model[:20]}] attempt {attempt}/{retries}")
            chat = groq_client.chat.completions.create(
                messages=[{"role":"user","content":prompt}],
                model=model, timeout=60)
            return chat.choices[0].message.content
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err:
                t = 5*attempt; dbg(f"Groq-text 429 — backoff {t}s"); time.sleep(t)
            else:
                dbg(f"Groq-text error: {e}")
                if attempt<retries: time.sleep(3)
                else: return None
    return None


# ─── Engine: Gemini Flash ─────────────────────────────────────────────────────
def gemini_call(prompt, retries=3, model="gemini-2.5-flash"):
    if not gemini_client: return None
    for attempt in range(1, retries+1):
        _wait(_gemini_lock, _gemini_last, GEMINI_MIN_INTERVAL, f"Gemini({model[-5:]})")
        try:
            dbg(f"Gemini JSON call [{model}] attempt {attempt}/{retries}")
            response = gemini_client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", safety_settings=_SAFETY))
            return response.text
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "quota" in err or "resource_exhausted" in err:
                w = (2**attempt)*20 + random.uniform(0,10)
                dbg(f"Gemini 429 — backoff {w:.0f}s"); time.sleep(w)
            elif "503" in err or "unavailable" in err:
                time.sleep(15+random.uniform(0,5))
            else:
                dbg(f"Gemini error: {e}"); return None
    dbg("Gemini: all retries exhausted"); return None


def gemini_call_text(prompt, retries=3, model="gemini-2.5-flash"):
    if not gemini_client: return None
    for attempt in range(1, retries+1):
        _wait(_gemini_lock, _gemini_last, GEMINI_MIN_INTERVAL, f"Gemini-text({model[-5:]})")
        try:
            dbg(f"Gemini TEXT call [{model}] attempt {attempt}/{retries}")
            response = gemini_client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(safety_settings=_SAFETY))
            return response.text
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "quota" in err or "resource_exhausted" in err:
                w = (2**attempt)*20 + random.uniform(0,10)
                dbg(f"Gemini-text 429 — backoff {w:.0f}s"); time.sleep(w)
            elif "503" in err or "unavailable" in err:
                time.sleep(15)
            else:
                dbg(f"Gemini-text error: {e}"); return None
    return None


# ─── Routers ──────────────────────────────────────────────────────────────────
def local_call_premium(prompt: str) -> str | None:
    """
    PREMIUM router — daily summary & weekly digest.
    gemini-2.5-pro PRIMARY (best reasoning, 25 RPD free)
    → gemini-2.5-flash fallback → groq-70b last resort
    """
    result = gemini_call(prompt, model="gemini-2.5-pro")
    if not result:
        dbg("Gemini-Pro failed — trying Flash fallback")
        result = gemini_call(prompt, model="gemini-2.5-flash")
    if not result:
        dbg("Gemini failed — trying Groq-70b fallback")
        result = groq_call(prompt, model="llama-3.3-70b-versatile")
    return result


def local_call(prompt: str) -> str | None:
    """
    STANDARD router — cycle digest, quiz, deepdive JSON.
    gemini-2.5-flash PRIMARY → groq-70b fallback
    """
    result = gemini_call(prompt, model="gemini-2.5-flash")
    if not result:
        dbg("Gemini Flash failed — trying Groq-70b fallback")
        result = groq_call(prompt, model="llama-3.3-70b-versatile")
    return result


def local_call_article(prompt: str) -> str | None:
    """
    FAST router — per-article bulk analysis.
    groq-8b PRIMARY (30 RPM, fast) → gemini-2.5-flash fallback
    """
    result = groq_call(prompt, model="llama-3.1-8b-instant")
    if not result:
        dbg("Groq failed — trying Gemini Flash fallback for article")
        result = gemini_call(prompt, model="gemini-2.5-flash")
    return result


def local_call_text(prompt: str) -> str | None:
    """
    TEXT router — deepdive dossiers, AI chat (plain prose).
    gemini-2.5-flash PRIMARY → groq-70b fallback
    """
    result = gemini_call_text(prompt, model="gemini-2.5-flash")
    if not result:
        dbg("Gemini-text failed — trying Groq-70b text fallback")
        result = groq_call_text(prompt, model="llama-3.3-70b-versatile")
    return result


# ─── Public Analysis Functions ────────────────────────────────────────────────
def ai_analyze(title: str, content: str) -> dict:
    raw  = local_call_article(build_analysis_prompt(title, content))
    data = extract_json(raw)
    sev_order = ["MINIMAL","LOW","MEDIUM","HIGH","CRITICAL"]
    kw_sev    = keyword_severity(title, content)
    if data:
        ai_sev = data.get("severity","LOW")
        ai_idx = sev_order.index(ai_sev) if ai_sev in sev_order else 2
        kw_idx = sev_order.index(kw_sev)
        data["severity"] = sev_order[max(ai_idx, kw_idx)]
        return data
    dbg("AI failed — keyword fallback")
    return {"severity":kw_sev,"category":"tech","confidence":1,
            "summary":["AI analysis unavailable — keyword classification applied"],
            "tags":[],"cves":[],"actors":[],"affected_products":[]}


def ai_digest(items: list, cycle_label="8-hour cycle") -> dict | None:
    sev_map = {"CRITICAL":5,"HIGH":4,"MEDIUM":3,"LOW":2,"MINIMAL":1}
    sorted_items = sorted(items, key=lambda x: sev_map.get(x.get("severity","LOW"),0), reverse=True)
    items_text = ""
    for item in sorted_items:
        summary = item.get("summary","")
        if isinstance(summary, list): summary = " | ".join(summary)
        items_text += f"[{item.get('severity','?')}][{item.get('category','tech')}] {item.get('title','')}\n  {summary[:250]}\n\n"
        if len(items_text) > 8000: break
    raw = local_call(build_digest_prompt(items_text, cycle_label))
    return extract_json(raw)


def ai_daily_summary(digests: list) -> dict | None:
    digests_text = "".join(f"\n--- DIGEST {i} ---\n{json.dumps(d,indent=2)}\n" for i,d in enumerate(digests,1))
    raw = local_call_premium(build_daily_prompt(digests_text[:12000]))
    return extract_json(raw)


def ai_weekly_summary(items: list) -> dict | None:
    sev_map = {"CRITICAL":5,"HIGH":4,"MEDIUM":3,"LOW":2,"MINIMAL":1}
    sorted_items = sorted(items, key=lambda x: sev_map.get(x.get("severity","LOW"),0), reverse=True)
    items_text = ""
    for item in sorted_items[:40]:
        summary = item.get("summary_text","")
        items_text += f"[{item.get('severity','?')}] {item.get('title','')}\n  {summary[:200]}\n\n"
    raw = local_call_premium(build_weekly_prompt(items_text[:12000]))
    return extract_json(raw)