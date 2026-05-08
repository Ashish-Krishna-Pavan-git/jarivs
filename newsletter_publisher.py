"""
newsletter_publisher.py
Converts the Daily AI Summary into HTML and publishes it directly to WordPress.
Styled specifically for akpghub.live dark/tech theme.
"""

import os
import json
from datetime import datetime
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

# Responsive, dark-themed CSS matching your site's aesthetic
CSS_STYLE = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=Inter:wght@400;600&display=swap');

    .jarvis-wrapper {
        font-family: 'Inter', sans-serif;
        color: #e0e6ed;
        line-height: 1.8;
        background-color: transparent;
        max-width: 100%;
        box-sizing: border-box;
    }
    .jarvis-wrapper h1, .jarvis-wrapper h2 {
        font-family: 'Orbitron', sans-serif;
        color: #ffffff;
        margin-top: 1.5em;
        margin-bottom: 0.8em;
        border-bottom: 1px solid rgba(255,255,255,0.1);
        padding-bottom: 8px;
        letter-spacing: 1px;
    }
    .jarvis-wrapper h1 { font-size: clamp(1.5rem, 4vw, 2.2rem); color: #38bdf8; border: none; }
    .jarvis-wrapper h2 { font-size: clamp(1.2rem, 3vw, 1.6rem); }
    
    .jarvis-summary {
        background-color: rgba(15, 23, 42, 0.4);
        border-left: 4px solid #38bdf8;
        padding: 20px;
        border-radius: 0 8px 8px 0;
        margin: 25px 0;
        font-size: clamp(1rem, 2vw, 1.1rem);
    }
    
    .jarvis-risk-CRITICAL { color: #fca5a5; font-weight: bold; background: rgba(248, 113, 113, 0.15); padding: 4px 10px; border-radius: 4px; border: 1px solid rgba(248, 113, 113, 0.3); }
    .jarvis-risk-HIGH { color: #fcd34d; font-weight: bold; background: rgba(251, 191, 36, 0.15); padding: 4px 10px; border-radius: 4px; border: 1px solid rgba(251, 191, 36, 0.3); }
    .jarvis-risk-MEDIUM { color: #cbd5e1; font-weight: bold; background: rgba(203, 213, 225, 0.15); padding: 4px 10px; border-radius: 4px; }
    
    .jarvis-wrapper ul { padding-left: 20px; }
    .jarvis-wrapper li { margin-bottom: 12px; }
    
    .jarvis-cve { 
        background-color: rgba(56, 189, 248, 0.1); 
        color: #38bdf8; 
        padding: 4px 8px; 
        border-radius: 4px; 
        font-family: monospace; 
        font-size: 0.9em; 
        border: 1px solid rgba(56, 189, 248, 0.2);
        display: inline-block;
        margin: 2px 4px 2px 0;
    }
    
    @media (max-width: 768px) {
        .jarvis-summary { padding: 15px; }
    }
</style>
"""

def generate_html(ai_summary):
    now = datetime.now()
    date_str = now.strftime("%B %d, %Y")
    
    headline = ai_summary.get("day_headline", "Daily Intelligence Briefing")
    risk = ai_summary.get("risk_level", "LOW")
    day_summary = ai_summary.get("day_summary", "No summary available.")
    
    html = f"""
    <div class="jarvis-wrapper">
        <p><strong>Date:</strong> {date_str} | <strong>Overall Risk:</strong> <span class="jarvis-risk-{risk}">{risk}</span></p>
        
        <div class="jarvis-summary">
            <strong>🎯 Executive Summary:</strong><br><br>
            {day_summary}
        </div>
    """

    threats = ai_summary.get("escalating_threats",[])
    if threats:
        html += "<h2>🔺 Escalating Threats</h2><ul>"
        for t in threats: html += f"<li>{t}</li>"
        html += "</ul>"

    cves = ai_summary.get("critical_cves",[])
    if cves:
        html += "<h2>🔴 Key Vulnerabilities (CVEs)</h2><p>"
        for cve in cves: html += f'<span class="jarvis-cve">{cve}</span>'
        html += "</p>"

    trends = ai_summary.get("tech_trends",[])
    if trends:
        html += "<h2>💡 Tech & AI Trends</h2><ul>"
        for t in trends: html += f"<li>{t}</li>"
        html += "</ul>"

    actions = ai_summary.get("recommendations",[])
    if actions:
        html += "<h2>✅ Actionable Recommendations</h2><ul>"
        for a in actions: html += f"<li><strong>Action:</strong> {a}</li>"
        html += "</ul>"
        
    html += "</div>"
    return html

def save_and_publish_newsletter(ai_summary, all_items):
    if not ai_summary:
        return
        
    html_content = generate_html(ai_summary)
    title = f"JARVIS Threat Intel: {datetime.now().strftime('%B %d, %Y')}"
    
    wp_url = os.getenv("WP_URL")
    wp_user = os.getenv("WP_USER")
    wp_pass = os.getenv("WP_APP_PASSWORD")
    
    if not wp_url or not wp_user or not wp_pass:
        print("[NEWSLETTER] WordPress credentials missing in .env. Skipping publish.")
        return
        
    print("[NEWSLETTER] Publishing to WordPress (Bypassing Cloudflare)...")
    api_url = f"{wp_url.rstrip('/')}/wp-json/wp/v2/posts"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    data = {
        "title": title,
        "content": CSS_STYLE + html_content,
        "status": "publish", 
        "categories":[46]  # Auto-routes to your Newsletter category!
    }
    
    try:
        response = requests.post(api_url, auth=HTTPBasicAuth(wp_user, wp_pass), json=data, headers=headers, timeout=30)
        if response.status_code in[200, 201]:
            link = response.json().get('link')
            print(f"[NEWSLETTER] Success! Published at: {link}")
        else:
            print(f"[NEWSLETTER] Failed. HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"[NEWSLETTER] Error connecting to WordPress: {e}")