"""
ai_router.py
Cloud API Version — Google Gemini 2.5 Flash (Primary) + Groq (Fallback)
Includes strict Thread-Safe Rate Limiting and Cyber-Security Safety Filter Bypasses.
"""

import json
import time
import os
import threading

# Use the NEW Google GenAI SDK
from google import genai
from google.genai import types
from groq import Groq

from config import AI_MAX_CONTENT_CHARS

# ─────────────────────────────────────────────────────────────
# CONFIGURATION & API SETUP
# ─────────────────────────────────────────────────────────────

# Load API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")

# Initialize Clients
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# ─────────────────────────────────────────────────────────────
# THREAD-SAFE RATE LIMITER
# ─────────────────────────────────────────────────────────────

API_LOCK = threading.Lock()
LAST_CALL_TIME = 0.0

def enforce_rate_limit(min_interval=4.1):
    """Ensures at least `min_interval` seconds pass between API calls."""
    global LAST_CALL_TIME
    with API_LOCK:
        now = time.time()
        elapsed = now - LAST_CALL_TIME
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            print(f"  [AI] Rate limiter active: Sleeping for {sleep_time:.2f}s...")
            time.sleep(sleep_time)
        LAST_CALL_TIME = time.time()

def dbg(msg):
    print(f"  [AI] {msg}")

# ─────────────────────────────────────────────────────────────
# PROMPT BUILDERS
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

Fill all fields. If not applicable, use an empty list[].
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
# API ENGINE CALLS
# ─────────────────────────────────────────────────────────────

def gemini_call(prompt):
    if not gemini_client: 
        return None
    try:
        dbg("Calling Google Gemini 2.5 Flash...")
        
        # New syntax for disabling safety filters so it doesn't block cybersec articles
        safety_settings =[
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
        
        # New syntax for generating content
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                safety_settings=safety_settings
            )
        )
        return response.text
    except Exception as e:
        dbg(f"Gemini error: {e}")
        return None

def groq_call(prompt):
    if not groq_client: 
        return None
    try:
        dbg("Calling Groq (Llama-3.1-8B)...")
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            response_format={"type": "json_object"} # Forces valid JSON
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        dbg(f"Groq error: {e}")
        return None

def local_call(prompt):
    """
    Main routing function. Named 'local_call' to maintain compatibility.
    """
    enforce_rate_limit(4.1)
    result = gemini_call(prompt)
    
    if not result:
        dbg("Gemini failed or rate-limited. Falling back to Groq...")
        enforce_rate_limit(2.5)
        result = groq_call(prompt)
        
    return result

# ─────────────────────────────────────────────────────────────
# PARSERS & FALLBACKS
# ─────────────────────────────────────────────────────────────

def extract_json(text):
    """Safely extracts and parses JSON from the AI's response."""
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

def keyword_severity(title, content):
    """Backup keyword-based severity analyzer in case ALL APIs fail."""
    text  = (title + " " + content).lower()
    score = 0
    
    critical =["rce", "remote code execution", "zero-day", "0-day",
                "actively exploited", "supply chain", "authentication bypass",
                "unauthenticated", "critical", "mass exploitation"]
    high     =["privilege escalation", "malware", "apt", "ransomware",
                "breach", "data leak", "backdoor", "trojan", "phishing campaign"]
    medium   =["cve", "patch", "vulnerability", "advisory", "update",
                "security fix", "exploit"]
                
    for k in critical:
        if k in text: score += 4
    for k in high:
        if k in text: score += 2
    for k in medium:
        if k in text: score += 1

    if score >= 12: return "CRITICAL"
    if score >= 7:  return "HIGH"
    if score >= 3:  return "MEDIUM"
    if score >= 1:  return "LOW"
    return "MINIMAL"

# ─────────────────────────────────────────────────────────────
# PUBLIC API (EXPOSED FUNCTIONS)
# ─────────────────────────────────────────────────────────────

def ai_analyze(title, content):
    """Analyzes a single article."""
    prompt = build_analysis_prompt(title, content)
    raw    = local_call(prompt)
    data   = extract_json(raw)

    if data:
        kw_sev = keyword_severity(title, content)
        ai_sev = data.get("severity", "LOW")
        sev_order =["MINIMAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
        ai_idx    = sev_order.index(ai_sev) if ai_sev in sev_order else 2
        kw_idx    = sev_order.index(kw_sev)
        data["severity"] = sev_order[max(ai_idx, kw_idx)]
        return data

    dbg("AI completely failed — using keyword fallback")
    return {
        "severity": keyword_severity(title, content),
        "category": "tech",
        "confidence": 1,
        "summary":["API Analysis unavailable due to cloud error — keyword classification used"],
        "tags": [], "cves":[], "actors": [], "affected_products":[]
    }

def ai_digest(items, cycle_label="8-hour cycle"):
    sev_map = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "MINIMAL": 1}
    sorted_items = sorted(items, key=lambda x: sev_map.get(x.get("severity", "LOW"), 0), reverse=True)
    
    items_text = ""
    for i, item in enumerate(sorted_items, 1):
        summary = item.get("summary", "")
        if isinstance(summary, list): 
            summary = " | ".join(summary)
            
        items_text += f"[{item.get('severity','?')}][Cat: {item.get('category','tech')}] {item.get('title','')}\n  {summary[:250]}\n\n"
        
        if len(items_text) > 8000:
            break

    raw = local_call(build_digest_prompt(items_text, cycle_label))
    return extract_json(raw)

def ai_daily_summary(digests):
    digests_text = ""
    for i, d in enumerate(digests, 1):
        digests_text += f"\n--- DIGEST {i} ---\n{json.dumps(d, indent=2)}\n"
        
    raw = local_call(build_daily_prompt(digests_text[:12000]))
    return extract_json(raw)

def ai_weekly_summary(items):
    sev_map = {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "MINIMAL": 1}
    sorted_items = sorted(items, key=lambda x: sev_map.get(x.get("severity", "LOW"), 0), reverse=True)
    
    items_text = ""
    for i, item in enumerate(sorted_items[:40], 1):
        summary = item.get("summary_text", "")
        items_text += f"[{item.get('severity','?')}] {item.get('title','')}\n  {summary[:200]}\n\n"

    raw = local_call(build_weekly_prompt(items_text[:12000]))
    return extract_json(raw)