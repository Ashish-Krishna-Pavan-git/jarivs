"""
audio_generator.py
Generates a full daily intelligence podcast using edge-tts Python API.
Voice: en-US-GuyNeural (smooth, natural male — primary)
       en-US-ChristopherNeural (authoritative news anchor — fallback)
"""

import os, re, asyncio


def _clean(text: str) -> str:
    text = text.replace("*","").replace("#","").replace("_","").replace("`","")
    text = text.replace("•","").replace("━","").replace("─","").replace("▶","")
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\[.*?\]", "", text)
    text = text.encode("ascii","ignore").decode("ascii")
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


async def _tts(script: str, voice: str, filepath: str) -> bool:
    try:
        import edge_tts
        comm = edge_tts.Communicate(script, voice)
        await comm.save(filepath)
        return os.path.exists(filepath) and os.path.getsize(filepath) > 1024
    except Exception as e:
        print(f"[AUDIO] TTS error ({voice}): {e}")
        return False


def _run_tts(script, voice, filepath):
    """Run async TTS, handles both fresh and existing event loops."""
    try:
        return asyncio.run(_tts(script, voice, filepath))
    except RuntimeError:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(_tts(script, voice, filepath))
            loop.close()
            return result
        except Exception as e:
            print(f"[AUDIO] Event loop error: {e}")
            return False


def generate_daily_audio(ai_summary: dict) -> str | None:
    if not ai_summary:
        return None

    print("[AUDIO] Generating daily intelligence podcast...")

    risk     = ai_summary.get("risk_level", "MEDIUM")
    headline = ai_summary.get("day_headline", "")
    summary  = ai_summary.get("day_summary", "")
    threats  = ai_summary.get("escalating_threats", [])
    patterns = ai_summary.get("new_patterns", [])
    actors   = ai_summary.get("actor_activity", [])
    trends   = ai_summary.get("tech_trends", [])
    recs     = ai_summary.get("recommendations", [])
    cves     = ai_summary.get("critical_cves", [])

    from datetime import datetime
    today = datetime.utcnow().strftime("%B %d, %Y")

    parts = []

    # ── Opening ───────────────────────────────────────────────
    parts.append(
        f"Good morning. Welcome to the JARVIS Daily Intelligence Briefing for {today}. "
        f"I am your AI analyst, and today's overall threat level is rated {risk}. "
        f"Let's get into what matters."
    )

    # ── Headline ──────────────────────────────────────────────
    if headline:
        parts.append(f"Today's headline: {headline}.")

    # ── Executive Summary ─────────────────────────────────────
    if summary:
        parts.append(f"Here is the executive summary. {summary}")

    # ── Escalating Threats ────────────────────────────────────
    if threats:
        parts.append(
            f"Now, the threats that are escalating and demand your immediate attention. "
            f"We identified {len(threats)} developing situations."
        )
        for i, t in enumerate(threats[:4], 1):
            parts.append(f"Threat number {i}: {t}.")

    # ── Patterns ──────────────────────────────────────────────
    if patterns:
        parts.append(
            "Our cross-cycle analysis has surfaced some important patterns "
            "that are not visible when looking at individual incidents."
        )
        for p in patterns[:3]:
            parts.append(f"{p}.")

    # ── Threat Actors ─────────────────────────────────────────
    if actors:
        parts.append("On the threat actor front:")
        for a in actors[:3]:
            parts.append(f"{a}.")

    # ── CVEs ──────────────────────────────────────────────────
    if cves:
        cve_list = ", ".join(cves[:5])
        parts.append(
            f"The critical vulnerabilities you need to patch today are: {cve_list}. "
            f"Do not leave these open. Attackers are actively scanning for them."
        )

    # ── Tech Trends ───────────────────────────────────────────
    if trends:
        parts.append("Shifting to technology and AI developments worth tracking:")
        for t in trends[:3]:
            parts.append(f"{t}.")

    # ── Recommendations ───────────────────────────────────────
    if recs:
        parts.append(
            f"Finally, here are your {len(recs[:4])} recommended actions for today. "
            "These are prioritised by urgency."
        )
        for i, r in enumerate(recs[:4], 1):
            parts.append(f"Action {i}: {r}.")

    # ── Closing ───────────────────────────────────────────────
    parts.append(
        "That is your JARVIS Daily Intelligence Briefing. "
        "Stay ahead of the threats. Stay secure. "
        "The next briefing will be delivered at your scheduled cycle time. "
        "JARVIS out."
    )

    raw_script   = "  ".join(parts)
    clean_script = _clean(raw_script)

    if len(clean_script) < 100:
        print("[AUDIO] Script too short — skipping")
        return None

    print(f"[AUDIO] Script length: {len(clean_script)} chars (~{len(clean_script)//15} seconds)")

    os.makedirs("data/audio", exist_ok=True)
    filepath = "data/audio/daily_podcast.mp3"

    # Male voices — smooth and professional
    voices = [
        "en-US-GuyNeural",          # Natural, conversational male (PRIMARY)
        "en-US-ChristopherNeural",  # Authoritative news anchor (FALLBACK)
        "en-US-EricNeural",         # Warm, engaging (LAST RESORT)
    ]

    for voice in voices:
        print(f"[AUDIO] Trying voice: {voice}")
        if _run_tts(clean_script, voice, filepath):
            kb = os.path.getsize(filepath) // 1024
            print(f"[AUDIO] ✓ {voice} — {kb}KB → {filepath}")
            return filepath

    print("[AUDIO] ✗ All voices failed — check edge-tts installation: pip install edge-tts")
    return None
