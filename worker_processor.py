"""
worker_processor.py
Core processing engine.
Handles AI analysis, normalization, saving, and immediate alerts.
"""

import time
import traceback

from queue_manager  import get_next_item, mark_done, mark_failed, get_pending_count
from ai_router      import ai_analyze
from scraper        import scrape_article
from storage        import save_article
from notifier       import notify_immediate
from telemetry      import update as tele_update
from dedupe         import mark_as_seen
from config         import IMMEDIATE_ALERT_LEVELS


# ─────────────────────────────────────────────────────────────
# NORMALIZERS
# ─────────────────────────────────────────────────────────────

def normalize_category(cat) -> str:
    try:
        if isinstance(cat, list):
            return str(cat[0]).lower().strip() if cat else "tech"
        if isinstance(cat, str):
            return cat.lower().strip()
        return "tech"
    except Exception:
        return "tech"


def normalize_summary(summary) -> list:
    try:
        if isinstance(summary, str):
            return [summary] if summary.strip() else ["No summary available"]
        if isinstance(summary, list):
            clean = []
            for item in summary:
                if isinstance(item, str) and item.strip():
                    clean.append(item.strip())
                elif isinstance(item, dict):
                    for v in item.values():
                        if isinstance(v, str) and v.strip():
                            clean.append(v.strip())
                            break
            return clean if clean else ["No summary available"]
        return ["No summary available"]
    except Exception:
        return ["Summary parsing failed"]


def normalize_list_field(val) -> list:
    try:
        if not val:
            return []
        if isinstance(val, str):
            return [val] if val.strip() else []
        if isinstance(val, list):
            return [str(x).strip() for x in val if x and str(x).strip()]
        return []
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────
# SMART ALERT FILTER
# ─────────────────────────────────────────────────────────────

def is_dead_serious(item: dict) -> bool:
    """
    Returns True only for drop-everything events that warrant immediate alert.
    Prevents alert spam from borderline articles.
    """
    try:
        severity = item.get("severity", "LOW")
        if severity not in ("CRITICAL", "HIGH"):
            return False

        try:
            confidence = int(item.get("confidence", 5))
        except Exception:
            confidence = 5

        if confidence < 7:
            return False

        text = (str(item.get("title", "")) + " " + str(item.get("summary_text", ""))).lower()

        # Ignore historical/retrospective articles
        ignore_kw = [
            "retrospective", "history of", "years ago", "look back",
            "news events that shaped", "decade", "evolution of",
            "a timeline of", "how it happened",
        ]
        if any(k in text for k in ignore_kw):
            return False

        # Keywords that indicate real-time danger
        urgent_kw = [
            "zero-day", "0-day", "actively exploited", "in the wild",
            "mass exploitation", "unauthenticated rce", "emergency patch",
            "immediate", "critical patch tuesday",
        ]
        has_urgent = any(k in text for k in urgent_kw)

        if severity == "CRITICAL" and (has_urgent or (item.get("cves") and confidence >= 8)):
            return True
        if severity == "HIGH" and has_urgent and confidence >= 8:
            return True

        return False
    except Exception as e:
        print(f"  [PROC] Alert filter error: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# PROCESS ONE ITEM
# ─────────────────────────────────────────────────────────────

def process_item(item: dict) -> dict:
    article = item.get("article", {})
    title   = str(article.get("title", "Unknown Title"))

    print(f"\n  [PROC] {title[:70]}")
    print(f"  [PROC] Source: {article.get('source', '?')}")

    # ── 1. Scrape full content ──
    article = scrape_article(article)
    content = str(article.get("content", ""))

    if article.get("scraped"):
        tele_update("scraped")
        print(f"  [PROC] Full scrape: {len(content)} chars")
    else:
        print(f"  [PROC] RSS fallback: {len(content)} chars")

    # ── 2. AI analysis (all articles) ──
    print(f"  [PROC] Running AI analysis...")
    ai_data = ai_analyze(title, content)

    if not ai_data or not isinstance(ai_data, dict):
        ai_data = {
            "severity":  "LOW",
            "category":  "tech",
            "summary":   ["AI analysis completely failed."],
            "confidence": 1,
        }

    # ── 3. Normalize AI output ──
    severity = str(ai_data.get("severity", "LOW")).upper()
    category = normalize_category(ai_data.get("category", "tech"))
    summary  = normalize_summary(ai_data.get("summary", []))
    tags     = normalize_list_field(ai_data.get("tags", []))
    cves     = normalize_list_field(ai_data.get("cves", []))
    actors   = normalize_list_field(ai_data.get("actors", []))
    affected = normalize_list_field(ai_data.get("affected_products", []))

    try:
        confidence = int(ai_data.get("confidence", 1))
    except Exception:
        confidence = 1

    summary_text = "\n".join(f"• {s}" for s in summary)

    # ── 4. Build processed record ──
    processed = {
        "title":             title,
        "link":              str(article.get("link", "")),
        "source":            str(article.get("source", "")),
        "severity":          severity,
        "category":          category,
        "confidence":        confidence,
        "summary":           summary,
        "summary_text":      summary_text,
        "tags":              tags,
        "cves":              cves,
        "actors":            actors,
        "affected_products": affected,
        "scraped":           bool(article.get("scraped", False)),
        "paywall":           bool(article.get("paywall", False)),
        "fp":                str(article.get("fp", "")),
        "timestamp":         int(time.time()),
    }

    print(f"  [PROC] ✓ {severity} | {category} | confidence={confidence}")

    # ── 5. Save to disk ──
    save_article(processed)
    tele_update("processed", severity=severity)

    # ── 6. Immediate alert for genuinely critical events ──
    if is_dead_serious(processed):
        print(f"  [PROC] 🚨 DEAD SERIOUS — sending immediate alert")
        notify_immediate(processed)   # Non-blocking (background thread)
    elif severity in IMMEDIATE_ALERT_LEVELS:
        print(f"  [PROC] {severity} — will appear in 8hr digest (cooldown active or not urgent enough)")

    return processed


# ─────────────────────────────────────────────────────────────
# DRAIN QUEUE
# ─────────────────────────────────────────────────────────────

def run_worker():
    print("\n[WORKER] Starting queue drain...\n")

    processed_all = []
    failed_all    = []
    total         = get_pending_count()
    done          = 0

    while True:
        item = get_next_item()
        if not item:
            print(f"\n[WORKER] Queue empty — done")
            break

        done += 1
        article = item.get("article", {})
        print(f"\n[WORKER] {done}/{total}")

        try:
            result = process_item(item)
            processed_all.append(result)
            mark_done(item["id"])
            mark_as_seen([article])   # In-memory only — no disk write per article

        except Exception as e:
            print(f"[WORKER] ⚠️ Error on item: {e}")
            traceback.print_exc()
            tele_update("failed")
            mark_failed(item["id"])
            failed_all.append(item)

        time.sleep(0.5)   # Small gap between articles (rate limiter handles AI waits)

    print(f"\n[WORKER] ✓ Complete: {len(processed_all)} processed, {len(failed_all)} failed")
    # Flush seen fingerprints to disk ONCE (not per-article — huge speed improvement)
    from dedupe import flush_seen
    flush_seen()
    return processed_all, failed_all
