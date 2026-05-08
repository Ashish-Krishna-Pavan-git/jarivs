"""
storage.py
Saves processed articles as JSON + Markdown.
All severities saved. Directory structure: data/processed/YYYY-MM-DD/
"""

import os
import json
from datetime import datetime

from config import PROCESSED_DIR, RAW_DIR


def _today_dir():
    day  = datetime.utcnow().strftime("%Y-%m-%d")
    path = os.path.join(PROCESSED_DIR, day)
    os.makedirs(path, exist_ok=True)
    return path


def _ts():
    return datetime.utcnow().strftime("%H-%M-%S-%f")[:-3]  # ms precision


def save_article(item):
    """Save a single processed article to JSON + Markdown."""
    folder = _today_dir()
    ts     = _ts()
    slug   = item.get("severity", "UNK")

    json_path = os.path.join(folder, f"{ts}_{slug}.json")
    md_path   = os.path.join(folder, f"{ts}_{slug}.md")

    # Ensure summary is a string for storage
    summary = item.get("summary", [])
    if isinstance(summary, list):
        summary_str = "\n".join(f"• {s}" for s in summary)
    else:
        summary_str = summary

    item["saved_at"] = datetime.utcnow().isoformat()

    # ── JSON ──
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(item, f, indent=2, ensure_ascii=False)

    # ── MARKDOWN ──
    with open(md_path, "w", encoding="utf-8") as f:
        sev   = item.get("severity", "?")
        emoji = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "📌",
                 "LOW": "📄", "MINIMAL": "ℹ️"}.get(sev, "")
        f.write(f"# {emoji} [{sev}] {item['title']}\n\n")
        f.write(f"**Source:** {item.get('source', '?')}  \n")
        f.write(f"**Category:** {item.get('category', '?')}  \n")
        f.write(f"**Severity:** {sev}  \n")
        f.write(f"**Confidence:** {item.get('confidence', '?')}/10  \n")
        f.write(f"**Link:** {item.get('link', '')}  \n")
        f.write(f"**Saved:** {item['saved_at']}  \n\n")
        f.write("## Summary\n\n")
        f.write(summary_str + "\n\n")
        if item.get("cves"):
            f.write(f"**CVEs:** {', '.join(item['cves'])}  \n")
        if item.get("actors"):
            f.write(f"**Threat Actors:** {', '.join(item['actors'])}  \n")
        if item.get("affected_products"):
            f.write(f"**Affected Products:** {', '.join(item['affected_products'])}  \n")
        if item.get("tags"):
            f.write(f"**Tags:** {', '.join(item['tags'])}  \n")
        f.write("\n---\n")

    return json_path


def save_items(items):
    """Save a list of processed articles."""
    saved = 0
    for item in items:
        try:
            save_article(item)
            saved += 1
        except Exception as e:
            print(f"[STORAGE] Error saving {item.get('title','?')[:50]}: {e}")
    print(f"[STORAGE] Saved {saved}/{len(items)} articles")


def load_last_n_hours(hours=24):
    """Load all saved articles from the last N hours."""
    from datetime import timedelta
    results = []
    cutoff  = datetime.utcnow() - timedelta(hours=hours)

    if not os.path.exists(PROCESSED_DIR):
        return results

    for root, _, files in os.walk(PROCESSED_DIR):
        for fname in files:
            if not fname.endswith(".json"):
                continue
            path = os.path.join(root, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    item = json.load(f)
                ts = item.get("saved_at")
                if not ts:
                    continue
                dt = datetime.fromisoformat(ts)
                if dt >= cutoff:
                    results.append(item)
            except:
                continue

    return results


def save_digest(digest_data, cycle_num):
    """Save 8hr digest JSON."""
    day    = datetime.utcnow().strftime("%Y-%m-%d")
    folder = os.path.join("data", "daily", day)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"digest_cycle_{cycle_num}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(digest_data, f, indent=2)
    return path


def save_daily_report(report_data, report_text):
    """Save daily summary JSON + txt."""
    day    = datetime.utcnow().strftime("%Y-%m-%d")
    folder = os.path.join("data", "daily", day)
    os.makedirs(folder, exist_ok=True)

    json_path = os.path.join(folder, "daily_summary.json")
    txt_path  = os.path.join(folder, "daily_summary.txt")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    return txt_path


def load_today_digests():
    """Load today's saved digest files."""
    day    = datetime.utcnow().strftime("%Y-%m-%d")
    folder = os.path.join("data", "daily", day)
    digests = []

    if not os.path.exists(folder):
        return digests

    for i in range(1, 4):
        path = os.path.join(folder, f"digest_cycle_{i}.json")
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    digests.append(json.load(f))
            except:
                pass

    return digests
