"""
newsletter_publisher.py
Converts the Daily AI Summary into HTML and publishes it directly to WordPress.
Styled specifically for akpghub.live dark/tech theme.
"""

import os
import html
import time
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
    
    content_html = f"""
    <div class="jarvis-wrapper">
        <h1>{html.escape(headline)}</h1>
        <p><strong>Date:</strong> {date_str} | <strong>Overall Risk:</strong> <span class="jarvis-risk-{risk}">{risk}</span></p>
        
        <div class="jarvis-summary">
            <strong>🎯 Executive Summary:</strong><br><br>
            {html.escape(day_summary)}
        </div>
    """

    threats = ai_summary.get("escalating_threats",[])
    if threats:
        content_html += "<h2>🔺 Escalating Threats</h2><ul>"
        for t in threats:
            content_html += f"<li>{html.escape(str(t))}</li>"
        content_html += "</ul>"

    cves = ai_summary.get("critical_cves",[])
    if cves:
        content_html += "<h2>🔴 Key Vulnerabilities (CVEs)</h2><p>"
        for cve in cves:
            content_html += f'<span class="jarvis-cve">{html.escape(str(cve))}</span>'
        content_html += "</p>"

    trends = ai_summary.get("tech_trends",[])
    if trends:
        content_html += "<h2>💡 Tech & AI Trends</h2><ul>"
        for t in trends:
            content_html += f"<li>{html.escape(str(t))}</li>"
        content_html += "</ul>"

    actions = ai_summary.get("recommendations",[])
    if actions:
        content_html += "<h2>✅ Actionable Recommendations</h2><ul>"
        for a in actions:
            content_html += f"<li><strong>Action:</strong> {html.escape(str(a))}</li>"
        content_html += "</ul>"
        
    content_html += "</div>"
    return content_html


def _build_reference_section(all_items):
    items = sorted(
        all_items,
        key=lambda item: {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(item.get("severity", "LOW"), 0),
        reverse=True,
    )
    refs = []
    for item in items[:10]:
        title = html.escape(str(item.get("title", "")))
        link = html.escape(str(item.get("link", "")))
        severity = html.escape(str(item.get("severity", "LOW")))
        if title and link:
            refs.append(f'<li><strong>[{severity}]</strong> <a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a></li>')
    if not refs:
        return ""
    return "<h2>🔗 Key Source Articles</h2><ul>" + "".join(refs) + "</ul>"


def _request_with_retry(method, url, auth, headers=None, params=None, json_data=None):
    last_error = None
    for attempt in range(1, 4):
        try:
            response = requests.request(
                method,
                url,
                auth=auth,
                headers=headers,
                params=params,
                json=json_data,
                timeout=30,
            )
            if response.status_code in (200, 201):
                return response
            last_error = f"HTTP {response.status_code}: {response.text[:300]}"
        except Exception as e:
            last_error = str(e)
        time.sleep(attempt * 2)
    raise RuntimeError(last_error or "Unknown WordPress error")


def _find_existing_post(api_root, auth, headers, slug):
    response = _request_with_retry(
        "GET",
        f"{api_root}/posts",
        auth=auth,
        headers=headers,
        params={"slug": slug, "per_page": 1},
    )
    data = response.json()
    if data:
        return data[0]
    return None


def save_and_publish_newsletter(ai_summary, all_items):
    if not ai_summary:
        return
        
    html_content = generate_html(ai_summary) + _build_reference_section(all_items)
    date_now = datetime.now()
    title = f"JARVIS Threat Intel: {date_now.strftime('%B %d, %Y')}"
    slug = f"jarvis-threat-intel-{date_now.strftime('%Y-%m-%d')}"
    
    wp_url = os.getenv("WP_URL")
    wp_user = os.getenv("WP_USER")
    wp_pass = os.getenv("WP_APP_PASSWORD")
    wp_category_id = os.getenv("WP_CATEGORY_ID", "46")
    wp_post_status = os.getenv("WP_POST_STATUS", "publish")
    
    if not wp_url or not wp_user or not wp_pass:
        print("[NEWSLETTER] WordPress credentials missing in .env. Skipping publish.")
        return
        
    print("[NEWSLETTER] Publishing to WordPress (Bypassing Cloudflare)...")
    api_root = f"{wp_url.rstrip('/')}/wp-json/wp/v2"
    api_url = f"{api_root}/posts"
    auth = HTTPBasicAuth(wp_user, wp_pass)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    data = {
        "title": title,
        "content": CSS_STYLE + html_content,
        "status": wp_post_status,
        "slug": slug,
        "excerpt": ai_summary.get("day_summary", "")[:250],
        "categories": [int(wp_category_id)],
    }
    
    try:
        existing = _find_existing_post(api_root, auth, headers, slug)
        if existing:
            response = _request_with_retry(
                "POST",
                f"{api_url}/{existing['id']}",
                auth=auth,
                headers=headers,
                json_data=data,
            )
            link = response.json().get("link")
            print(f"[NEWSLETTER] Updated existing post: {link}")
        else:
            response = _request_with_retry(
                "POST",
                api_url,
                auth=auth,
                headers=headers,
                json_data=data,
            )
            link = response.json().get("link")
            print(f"[NEWSLETTER] Success! Published at: {link}")
    except Exception as e:
        print(f"[NEWSLETTER] Error connecting to WordPress: {e}")
