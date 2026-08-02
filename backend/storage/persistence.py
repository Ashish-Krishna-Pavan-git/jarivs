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
from datetime import datetime, timedelta, timezone

import config


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _today_dir() -> str:
    day  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(config.PROCESSED_DIR, day)
    os.makedirs(path, exist_ok=True)
    return path


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H-%M-%S-%f")[:-3]


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

    item["saved_at"] = datetime.now(timezone.utc).isoformat()

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
    cutoff    = datetime.now(timezone.utc) - timedelta(hours=hours)

    # ── 1. Local files (fast, current session) ──
    if os.path.exists(config.PROCESSED_DIR):
        for root, _, files in os.walk(config.PROCESSED_DIR):
            for fname in files:
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(root, fname)
                try:
                    with open(path, encoding="utf-8") as f:
                        item = json.load(f)
                    ts = item.get("saved_at")
                    if ts:
                        dt = datetime.fromisoformat(ts)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if dt >= cutoff:
                            results.append(item)
                            local_fps.add(item.get("fp", item.get("title", "")))
                    else:
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
    day    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    folder = os.path.join(config.DAILY_DIR, day)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"digest_cycle_{cycle_num}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(digest_data, f, indent=2)
    return path


def load_today_digests() -> list:
    day    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    folder = os.path.join(config.DAILY_DIR, day)
    digests = []
    if not os.path.exists(folder):
        return digests
    for i in range(1, 5):   # Up to 4 digests per day (flexible)
        path = os.path.join(folder, f"digest_cycle_{i}.json")
        if os.path.exists(path):
            try:
                with open(path) as f:
                    item = json.load(f)
                    saved_at = item.get("saved_at")
                    if saved_at:
                        dt = datetime.fromisoformat(saved_at)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        # No hard cutoff here, returning all today's
                        digests.append(item)
                    else:
                        digests.append(item)
            except Exception:
                pass
    return digests


def load_digests(days: int = 30) -> list:
    """Load current-runtime cycle digests and daily summaries for the Reports view."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    results = []
    if not os.path.exists(config.DAILY_DIR):
        return results

    for day_name in sorted(os.listdir(config.DAILY_DIR), reverse=True):
        folder = os.path.join(config.DAILY_DIR, day_name)
        if not os.path.isdir(folder):
            continue
        try:
            dt = datetime.fromisoformat(day_name)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < cutoff:
                continue
        except ValueError:
            continue
        for filename in sorted(os.listdir(folder), reverse=True):
            is_cycle = filename.startswith("digest_cycle_") and filename.endswith(".json")
            if filename != "daily_summary.json" and not is_cycle:
                continue
            path = os.path.join(folder, filename)
            try:
                with open(path, encoding="utf-8") as f:
                    item = json.load(f)
                if isinstance(item, dict):
                    item["_runtime_path"] = path
                    item.setdefault("report_date", day_name)
                    results.append(item)
            except (OSError, json.JSONDecodeError):
                continue
    return results


def save_daily_report(report_data: dict, report_text: str) -> str:
    day    = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    folder = os.path.join(config.DAILY_DIR, day)
    os.makedirs(folder, exist_ok=True)

    json_path = os.path.join(folder, "daily_summary.json")
    txt_path  = os.path.join(folder, "daily_summary.txt")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    return txt_path
