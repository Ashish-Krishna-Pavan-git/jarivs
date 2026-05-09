"""
storage.py
Article + digest persistence.

CHANGES vs original:
  - Uses /tmp/jarvis/data/ (always writable on HF Spaces)
  - load_last_n_hours() supplements local files with HF bundle
    so daily/weekly summaries survive space restarts
"""

import os
import json
from datetime import datetime, timedelta

from config import PROCESSED_DIR, DAILY_DIR, RAW_DIR


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _today_dir() -> str:
    day  = datetime.utcnow().strftime("%Y-%m-%d")
    path = os.path.join(PROCESSED_DIR, day)
    os.makedirs(path, exist_ok=True)
    return path


def _ts() -> str:
    return datetime.utcnow().strftime("%H-%M-%S-%f")[:-3]


# ─────────────────────────────────────────────────────────────
# ARTICLE SAVE / LOAD
# ─────────────────────────────────────────────────────────────

def save_article(item: dict) -> str:
    """Save a single processed article as JSON + Markdown."""
    folder = _today_dir()
    ts     = _ts()
    slug   = item.get("severity", "UNK")

    json_path = os.path.join(folder, f"{ts}_{slug}.json")
    md_path   = os.path.join(folder, f"{ts}_{slug}.md")

    summary = item.get("summary", [])
    if isinstance(summary, list):
        summary_str = "\n".join(f"• {s}" for s in summary)
    else:
        summary_str = str(summary)

    item["saved_at"] = datetime.utcnow().isoformat()

    # ── JSON ──
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(item, f, indent=2, ensure_ascii=False)

    # ── Markdown ──
    sev   = item.get("severity", "?")
    emoji = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "📌",
             "LOW": "📄", "MINIMAL": "ℹ️"}.get(sev, "")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {emoji} [{sev}] {item.get('title','')}\n\n")
        f.write(f"**Source:** {item.get('source','?')}  \n")
        f.write(f"**Category:** {item.get('category','?')}  \n")
        f.write(f"**Severity:** {sev}  \n")
        f.write(f"**Confidence:** {item.get('confidence','?')}/10  \n")
        f.write(f"**Link:** {item.get('link','')}  \n")
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


def save_items(items: list):
    saved = 0
    for item in items:
        try:
            save_article(item)
            saved += 1
        except Exception as e:
            print(f"[STORAGE] Error saving {item.get('title','?')[:50]}: {e}")
    print(f"[STORAGE] Saved {saved}/{len(items)} articles")


def load_last_n_hours(hours: int = 24) -> list:
    """
    Load articles from the last N hours.
    Checks local files first (current session), then supplements with HF bundle
    (previous sessions — survives restarts).
    """
    results   = []
    local_fps = set()
    cutoff    = datetime.utcnow() - timedelta(hours=hours)

    # ── 1. Local files (fast, current session) ──
    if os.path.exists(PROCESSED_DIR):
        for root, _, files in os.walk(PROCESSED_DIR):
            for fname in files:
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(root, fname)
                try:
                    with open(path, encoding="utf-8") as f:
                        item = json.load(f)
                    ts = item.get("saved_at")
                    if ts and datetime.fromisoformat(ts) >= cutoff:
                        results.append(item)
                        local_fps.add(item.get("fp", item.get("title", "")))
                except Exception:
                    continue

    # ── 2. HF bundle (previous sessions — fills gaps after restarts) ──
    try:
        from storage_backend import load_bundle
        bundle = load_bundle()
        for item in bundle:
            ts = item.get("saved_at")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts)
                fp = item.get("fp", item.get("title", ""))
                if dt >= cutoff and fp not in local_fps:
                    results.append(item)
                    local_fps.add(fp)
            except Exception:
                continue
    except ImportError:
        pass

    print(f"[STORAGE] load_last_{hours}h → {len(results)} articles")
    return results


# ─────────────────────────────────────────────────────────────
# DIGEST SAVE / LOAD
# ─────────────────────────────────────────────────────────────

def save_digest(digest_data: dict, cycle_num: int) -> str:
    day    = datetime.utcnow().strftime("%Y-%m-%d")
    folder = os.path.join(DAILY_DIR, day)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"digest_cycle_{cycle_num}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(digest_data, f, indent=2)
    return path


def load_today_digests() -> list:
    day    = datetime.utcnow().strftime("%Y-%m-%d")
    folder = os.path.join(DAILY_DIR, day)
    digests = []
    if not os.path.exists(folder):
        return digests
    for i in range(1, 5):   # Up to 4 digests per day (flexible)
        path = os.path.join(folder, f"digest_cycle_{i}.json")
        if os.path.exists(path):
            try:
                with open(path) as f:
                    digests.append(json.load(f))
            except Exception:
                pass
    return digests


def save_daily_report(report_data: dict, report_text: str) -> str:
    day    = datetime.utcnow().strftime("%Y-%m-%d")
    folder = os.path.join(DAILY_DIR, day)
    os.makedirs(folder, exist_ok=True)

    json_path = os.path.join(folder, "daily_summary.json")
    txt_path  = os.path.join(folder, "daily_summary.txt")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    return txt_path
