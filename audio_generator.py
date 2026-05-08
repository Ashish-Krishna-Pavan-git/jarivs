"""
audio_generator.py
Generates a 3-minute podcast of the daily summary using edge-tts.
"""

import os
import re

def strip_emojis_and_markdown(text):
    """Removes emojis and markdown asterisks for clean text-to-speech."""
    # Remove markdown
    text = text.replace("*", "").replace("#", "")
    # Keep only basic ASCII and common punctuation (removes emojis)
    return text.encode('ascii', 'ignore').decode('ascii').replace('"', "'")

def generate_daily_audio(ai_summary):
    if not ai_summary:
        return None
        
    print("[AUDIO] Generating morning podcast...")
    
    # Write the script for the AI Voice Anchor
    script = "Good morning. Here is your JARVIS Daily Intelligence Briefing. "
    script += f"Today's headline: {ai_summary.get('day_headline', '')}. "
    script += f"{ai_summary.get('day_summary', '')} "
    
    threats = ai_summary.get("escalating_threats",[])
    if threats:
        script += "Here are the escalating threats you need to know about. "
        for t in threats:
            script += f"{t}. "
            
    actions = ai_summary.get("recommendations",[])
    if actions:
        script += "Finally, here are today's actionable recommendations. "
        for a in actions:
            script += f"{a}. "
            
    script += "That concludes today's briefing. Stay secure."

    clean_script = strip_emojis_and_markdown(script)
    
    os.makedirs("data/audio", exist_ok=True)
    filepath = "data/audio/daily_podcast.mp3"
    
    # Call edge-tts via command line (Safe for Termux & Windows)
    # en-US-ChristopherNeural is a great, professional news anchor voice
    cmd = f'edge-tts --voice "en-US-ChristopherNeural" --text "{clean_script}" --write-media "{filepath}"'
    os.system(cmd)
    
    if os.path.exists(filepath):
        print(f"[AUDIO] Podcast saved: {filepath}")
        return filepath
    return None