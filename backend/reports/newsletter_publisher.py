"""
wordpress_publisher.py
Publishes the JARVIS daily intelligence report to a WordPress site
via the WordPress REST API using Application Passwords.

Required environment variables:
    WP_URL             - Base URL of your WordPress site, e.g. https://mysite.com
    WP_USER            - WordPress username (not email)
    WP_APP_PASSWORD    - WordPress Application Password (spaces or no-spaces both work)

Optional environment variables:
    WP_CATEGORY_ID     - WordPress category ID to assign the post (default: 1)
    WP_POST_STATUS     - "publish" or "draft" (default: publish)
    WP_TAGS            - Comma-separated tag IDs to attach (default: "")
"""

from __future__ import annotations

import html
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

# ─── Dark-tech CSS matching JARVIS aesthetic ──────────────────────────────────
CSS_STYLE = """\
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
.jarvis-risk-CRITICAL { color: #fca5a5; font-weight: bold; background: rgba(248,113,113,0.15); padding: 4px 10px; border-radius: 4px; }
.jarvis-risk-HIGH     { color: #fcd34d; font-weight: bold; background: rgba(251,191,36,0.15);  padding: 4px 10px; border-radius: 4px; }
.jarvis-risk-MEDIUM   { color: #cbd5e1; font-weight: bold; background: rgba(203,213,225,0.15); padding: 4px 10px; border-radius: 4px; }

.jarvis-wrapper ul { padding-left: 20px; }
.jarvis-wrapper li { margin-bottom: 12px; }

.jarvis-cve {
    background-color: rgba(56,189,248,0.1);
    color: #38bdf8;
    padding: 4px 8px;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.9em;
    border: 1px solid rgba(56,189,248,0.2);
    display: inline-block;
    margin: 2px 4px 2px 0;
}

.jarvis-footer {
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid rgba(255,255,255,0.1);
    font-size: 0.85em;
    color: #94a3b8;
}

@media (max-width: 768px) {
    .jarvis-summary { padding: 15px; }
}
</style>
"""


# ─── HTML builder ─────────────────────────────────────────────────────────────

def _build_html(ai_summary: dict, all_items: list) -> str:
    now = datetime.now()
    date_str = now.strftime("%B %d, %Y")

    headline    = ai_summary.get("day_headline", "Daily Intelligence Briefing")
    risk        = ai_summary.get("risk_level", "LOW")
    day_summary = ai_summary.get("day_summary", "No summary available.")

    content = f"""
<div class="jarvis-wrapper">
    <h1>{html.escape(headline)}</h1>
    <p><strong>Date:</strong> {date_str} &nbsp;|&nbsp;
       <strong>Overall Risk:</strong>
       <span class="jarvis-risk-{html.escape(risk)}">{html.escape(risk)}</span>
    </p>

    <div class="jarvis-summary">
        <strong>🎯 Executive Summary:</strong><br><br>
        {html.escape(day_summary)}
    </div>
"""

    threats = ai_summary.get("escalating_threats", [])
    if threats:
        content += "<h2>🔺 Escalating Threats</h2><ul>"
        for t in threats:
            content += f"<li>{html.escape(str(t))}</li>"
        content += "</ul>"

    patterns = ai_summary.get("new_patterns", [])
    if patterns:
        content += "<h2>📊 Emerging Patterns</h2><ul>"
        for p in patterns:
            content += f"<li>{html.escape(str(p))}</li>"
        content += "</ul>"

    actors = ai_summary.get("actor_activity", [])
    if actors:
        content += "<h2>🕵️ Threat Actor Activity</h2><ul>"
        for a in actors:
            content += f"<li>{html.escape(str(a))}</li>"
        content += "</ul>"

    cves = ai_summary.get("critical_cves", [])
    if cves:
        content += "<h2>🔴 Key Vulnerabilities (CVEs)</h2><p>"
        for cve in cves:
            content += f'<span class="jarvis-cve">{html.escape(str(cve))}</span>'
        content += "</p>"

    trends = ai_summary.get("tech_trends", [])
    if trends:
        content += "<h2>💡 Tech & AI Trends</h2><ul>"
        for t in trends:
            content += f"<li>{html.escape(str(t))}</li>"
        content += "</ul>"

    actions = ai_summary.get("recommendations", [])
    if actions:
        content += "<h2>✅ Actionable Recommendations</h2><ul>"
        for a in actions:
            content += f"<li><strong>Action:</strong> {html.escape(str(a))}</li>"
        content += "</ul>"

    # Top reference articles
    if all_items:
        top_items = sorted(
            all_items,
            key=lambda x: {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(x.get("severity", "LOW"), 0),
            reverse=True,
        )[:10]
        refs = []
        for item in top_items:
            title    = html.escape(str(item.get("title", "")))
            link     = html.escape(str(item.get("link", "")))
            severity = html.escape(str(item.get("severity", "LOW")))
            if title and link:
                refs.append(f'<li><strong>[{severity}]</strong> <a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a></li>')
        if refs:
            content += "<h2>🔗 Source Articles</h2><ul>" + "".join(refs) + "</ul>"

    content += f"""
    <div class="jarvis-footer">
        Generated by JARVIS Intelligence System &mdash; {date_str}
    </div>
</div>
"""
    return content


# ─── WordPress REST API helpers ───────────────────────────────────────────────

def _auth() -> tuple[HTTPBasicAuth, dict]:
    """Return (auth, headers) for WordPress REST API requests."""
    wp_user = os.getenv("WP_USER", "")
    wp_pass = os.getenv("WP_APP_PASSWORD", "")
    # Application Passwords may contain spaces — that's fine for HTTPBasicAuth
    auth    = HTTPBasicAuth(wp_user, wp_pass)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":       "application/json",
        "Content-Type": "application/json",
    }
    return auth, headers


def _request(method: str, url: str, auth, headers: dict, **kwargs) -> requests.Response:
    """Retry-aware HTTP request — up to 3 attempts with back-off."""
    last_error: str | None = None
    for attempt in range(1, 4):
        try:
            resp = requests.request(method, url, auth=auth, headers=headers, timeout=30, **kwargs)
            if resp.status_code in (200, 201):
                return resp
            last_error = f"HTTP {resp.status_code}: {resp.text[:400]}"
        except Exception as exc:
            last_error = str(exc)
        if attempt < 3:
            time.sleep(attempt * 3)
    raise RuntimeError(last_error or "Unknown WordPress error")


def _find_existing_post(api_root: str, auth, headers: dict, slug: str) -> dict | None:
    """Return existing post dict if a post with this slug exists, else None."""
    resp = _request("GET", f"{api_root}/posts", auth, headers, params={"slug": slug, "per_page": 1})
    data = resp.json()
    return data[0] if data else None


def _log_result(result: dict) -> None:
    """Append publish result to a JSONL log file for audit trail."""
    try:
        log_dir = os.getenv("JARVIS_DATA_DIR", "/tmp/jarvis/data")
        log_path = os.path.join(log_dir, "wordpress_posts.jsonl")
        os.makedirs(log_dir, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")
    except Exception as e:
        print(f"[WP] Warning: could not write log: {e}")


# ─── Public entry point ───────────────────────────────────────────────────────

def publish_to_wordpress(ai_summary: dict, all_items: list) -> dict | None:
    """
    Publish the daily AI summary to WordPress via REST API.

    Returns a result dict with keys:
        success     bool
        post_id     int | None
        post_url    str | None
        action      "created" | "updated" | "skipped" | "error"
        error       str | None

    Always returns a dict (never raises). Logs result to
    $JARVIS_DATA_DIR/wordpress_posts.jsonl.
    """
    if not ai_summary:
        return {"success": False, "action": "skipped", "error": "No AI summary provided", "post_id": None, "post_url": None}

    wp_url        = os.getenv("WP_URL", "").rstrip("/")
    wp_user       = os.getenv("WP_USER", "")
    wp_app_pass   = os.getenv("WP_APP_PASSWORD", "")
    category_id   = int(os.getenv("WP_CATEGORY_ID", "1"))
    post_status   = os.getenv("WP_POST_STATUS", "publish")

    # Validate — only the three essentials are required
    if not wp_url:
        print("[WP] WP_URL not set — skipping WordPress publish.")
        return {"success": False, "action": "skipped", "error": "WP_URL not configured", "post_id": None, "post_url": None}
    if not wp_user or not wp_app_pass:
        print("[WP] WP_USER / WP_APP_PASSWORD not set — skipping WordPress publish.")
        return {"success": False, "action": "skipped", "error": "WP credentials not configured", "post_id": None, "post_url": None}

    now       = datetime.now()
    title     = f"JARVIS Threat Intel: {now.strftime('%B %d, %Y')}"
    slug      = f"jarvis-threat-intel-{now.strftime('%Y-%m-%d')}"
    excerpt   = ai_summary.get("day_summary", "")[:250]
    content   = CSS_STYLE + _build_html(ai_summary, all_items)

    api_root  = f"{wp_url}/wp-json/wp/v2"
    auth, hdr = _auth()

    post_data = {
        "title":      title,
        "content":    content,
        "status":     post_status,
        "slug":       slug,
        "excerpt":    excerpt,
        "categories": [category_id],
    }

    tag_ids_raw = os.getenv("WP_TAGS", "")
    if tag_ids_raw:
        try:
            post_data["tags"] = [int(t.strip()) for t in tag_ids_raw.split(",") if t.strip()]
        except ValueError:
            print(f"[WP] Warning: WP_TAGS contains non-integer values: {tag_ids_raw}")

    result: dict = {"slug": slug, "published_at": now.isoformat()}

    try:
        existing = _find_existing_post(api_root, auth, hdr, slug)
        if existing:
            post_id  = existing["id"]
            resp     = _request("POST", f"{api_root}/posts/{post_id}", auth, hdr, json=post_data)
            rdata    = resp.json()
            post_url = rdata.get("link", "")
            print(f"[WP] ✓ Updated existing post (ID {post_id}): {post_url}")
            result.update({"success": True, "action": "updated", "post_id": post_id, "post_url": post_url, "error": None})
        else:
            resp     = _request("POST", f"{api_root}/posts", auth, hdr, json=post_data)
            rdata    = resp.json()
            post_id  = rdata.get("id")
            post_url = rdata.get("link", "")
            print(f"[WP] ✓ Published new post (ID {post_id}): {post_url}")
            result.update({"success": True, "action": "created", "post_id": post_id, "post_url": post_url, "error": None})

    except Exception as exc:
        err_msg = str(exc)
        print(f"[WP] ✗ Failed to publish to WordPress: {err_msg}")
        result.update({"success": False, "action": "error", "post_id": None, "post_url": None, "error": err_msg})

    _log_result(result)
    return result


# ─── Keep backwards-compatible alias ─────────────────────────────────────────
def save_and_publish_newsletter(ai_summary: dict, all_items: list) -> None:
    """Legacy alias kept for compatibility with daily_summary.py callers."""
    publish_to_wordpress(ai_summary, all_items)
