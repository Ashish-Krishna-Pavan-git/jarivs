"""
audio_generator.py
Generates a daily audio briefing using edge-tts Python API.

FIX: replaces os.system() shell call which silently fails on HF Spaces.
Uses async Python API directly — reliable across all platforms.
Voice: en-US-AriaNeural (natural female news anchor tone).
Fallback: en-US-JennyNeural → en-US-ChristopherNeural (male).
"""

import os
import re
import asyncio


def _clean(text: str) -> str:
    """Strip emojis, markdown, and problematic punctuation for clean TTS output."""
    text = text.replace("*","").replace("#","").replace("_","").replace("`","")
    text = text.replace("•","").replace("━","").replace("─","")
    text = re.sub(r"https?://\S+", "", text)           # remove URLs
    text = re.sub(r"\[.*?\]", "", text)                # remove brackets
    text = text.encode("ascii","ignore").decode("ascii")  # strip non-ASCII (emojis)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


async def _tts_generate(script: str, voice: str, filepath: str) -> bool:
    """Run edge-tts async generation. Returns True on success."""
    try:
        import edge_tts
        communicate = edge_tts.Communicate(script, voice)
        await communicate.save(filepath)
        return os.path.exists(filepath) and os.path.getsize(filepath) > 1024
    except Exception as e:
        print(f"[AUDIO] TTS error with voice {voice}: {e}")
        return False


def generate_daily_audio(ai_summary: dict) -> str | None:
    if not ai_summary:
        return None

    print("[AUDIO] Generating daily intelligence podcast...")

    # ── Build natural-sounding script ──────────────────────────────────────────
    headline  = ai_summary.get("day_headline", "")
    summary   = ai_summary.get("day_summary", "")
    risk      = ai_summary.get("risk_level", "MEDIUM")
    threats   = ai_summary.get("escalating_threats", [])
    patterns  = ai_summary.get("new_patterns", [])
    actors    = ai_summary.get("actor_activity", [])
    trends    = ai_summary.get("tech_trends", [])
    recs      = ai_summary.get("recommendations", [])
    cves      = ai_summary.get("critical_cves", [])

    script_parts = []
    script_parts.append(
        "Good morning. This is JARVIS — your daily intelligence briefing. "
        f"Today's overall risk level is {risk}. "
    )

    if headline:
        script_parts.append(f"Today's headline: {headline}. ")

    if summary:
        script_parts.append(f"{summary} ")

    if threats:
        script_parts.append("Here are the escalating threats requiring your attention. ")
        for t in threats[:3]:
            script_parts.append(f"{t}. ")

    if patterns:
        script_parts.append("Our cross-cycle analysis has identified the following patterns. ")
        for p in patterns[:2]:
            script_parts.append(f"{p}. ")

    if actors:
        script_parts.append("Regarding threat actor activity. ")
        for a in actors[:2]:
            script_parts.append(f"{a}. ")

    if cves:
        script_parts.append(f"Critical vulnerabilities to prioritise: {', '.join(cves[:3])}. ")

    if trends:
        script_parts.append("On the technology front. ")
        for t in trends[:2]:
            script_parts.append(f"{t}. ")

    if recs:
        script_parts.append("Finally, today's recommended actions. ")
        for i, r in enumerate(recs[:3], 1):
            script_parts.append(f"Action {i}: {r}. ")

    script_parts.append(
        "That concludes today's JARVIS intelligence briefing. "
        "Stay vigilant, stay informed, and stay secure."
    )

    raw_script  = " ".join(script_parts)
    clean_script = _clean(raw_script)

    if len(clean_script) < 50:
        print("[AUDIO] Script too short after cleaning — skipping audio")
        return None

    print(f"[AUDIO] Script: {len(clean_script)} characters")

    os.makedirs("data/audio", exist_ok=True)
    filepath = "data/audio/daily_podcast.mp3"

    # ── Try voices in order ────────────────────────────────────────────────────
    voices = [
        "en-US-AriaNeural",        # Natural female, news anchor style
        "en-US-JennyNeural",       # Clear female, professional
        "en-US-ChristopherNeural", # Male fallback
    ]

    for voice in voices:
        print(f"[AUDIO] Trying voice: {voice}")
        try:
            success = asyncio.run(_tts_generate(clean_script, voice, filepath))
            if success:
                size_kb = os.path.getsize(filepath) // 1024
                print(f"[AUDIO] ✓ Generated with {voice} — {size_kb}KB saved to {filepath}")
                return filepath
        except RuntimeError:
            # asyncio.run() fails if there's already a running event loop (some environments)
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                success = loop.run_until_complete(_tts_generate(clean_script, voice, filepath))
                loop.close()
                if success:
                    size_kb = os.path.getsize(filepath) // 1024
                    print(f"[AUDIO] ✓ Generated with {voice} (new loop) — {size_kb}KB")
                    return filepath
            except Exception as e:
                print(f"[AUDIO] Loop error with {voice}: {e}")
        except Exception as e:
            print(f"[AUDIO] Failed with {voice}: {e}")

    print("[AUDIO] ✗ All TTS voices failed — check edge-tts installation")
    return None