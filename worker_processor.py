"""
worker_processor.py
Core processing engine.
Handles AI response normalization (category/summary type safety).
Includes strict crash-prevention for bad AI formatting.
"""

import time

from queue_manager  import get_next_item, mark_done, mark_failed, get_pending_count
from ai_router      import ai_analyze
from scraper        import scrape_article
from storage        import save_article
from notifier       import notify_immediate
from telemetry      import update as tele_update
from dedupe         import mark_as_seen
from config         import IMMEDIATE_ALERT_LEVELS


# ─────────────────────────────────────────────────────────────
# DATA NORMALIZERS (CRASH-PROOFED)
# ─────────────────────────────────────────────────────────────

def normalize_category(cat):
    """Ensure category is always a plain string."""
    try:
        if isinstance(cat, list):
            return str(cat[0]).lower().strip() if cat else "tech"
        if isinstance(cat, str):
            return cat.lower().strip()
        return "tech"
    except:
        return "tech"


def normalize_summary(summary):
    """
    Ensure summary is always a list of plain strings.
    AI sometimes returns list of dicts, a raw string, or broken JSON.
    """
    try:
        if isinstance(summary, str):
            return [summary] if summary.strip() else ["No summary available"]

        if isinstance(summary, list):
            clean =[]
            for item in summary:
                if isinstance(item, str) and item.strip():
                    clean.append(item.strip())
                elif isinstance(item, dict):
                    # Extract any string value from the dict
                    for v in item.values():
                        if isinstance(v, str) and v.strip():
                            clean.append(v.strip())
                            break
            return clean if clean else ["No summary available"]

        return ["No summary available"]
    except:
        return ["AI summary parsing failed — raw text used."]


def normalize_list_field(val):
    """Normalize tags/cves/actors — always return list of strings."""
    try:
        if not val:
            return[]
        if isinstance(val, str):
            return [val] if val.strip() else[]
        if isinstance(val, list):
            return [str(x).strip() for x in val if x and str(x).strip()]
        return[]
    except:
        return[]


def is_dead_serious(item):
    """Smart filter to prevent alert spam. Only triggers on drop-everything events."""
    try:
        severity = item.get("severity", "LOW")
        if severity not in ("CRITICAL", "HIGH"):
            return False
            
        try:
            confidence = int(item.get("confidence", 5))
        except:
            confidence = 5
            
        # Ignore low-confidence AI classifications to prevent false alarms
        if confidence < 7:
            return False
            
        text = (str(item.get("title", "")) + " " + str(item.get("summary_text", ""))).lower()

        # Ignore retrospective or historical articles
        ignore_keywords =[
            "retrospective", "history of", "years ago", "look back", 
            "news events that shaped", "decade", "evolution of"
        ]
        if any(ik in text for ik in ignore_keywords):
            return False
        
        # Keywords that imply immediate real-world danger
        urgent_keywords =[
            "zero-day", "0-day", "actively exploited", "in the wild",
            "mass exploitation", "unauthenticated rce", "emergency patch"
        ]
        
        has_urgent = any(kw in text for kw in urgent_keywords)
        
        # Condition 1: It's CRITICAL, and either mentions active exploits OR has CVEs with high confidence
        if severity == "CRITICAL" and (has_urgent or (item.get("cves") and confidence >= 8)):
            return True
            
        # Condition 2: It's HIGH, but explicitly mentions active exploitation and AI is confident
        if severity == "HIGH" and has_urgent and confidence >= 8:
            return True
            
        return False
    except Exception as e:
        print(f"  [PROC] Error in dead_serious filter: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# PROCESS ONE ITEM
# ─────────────────────────────────────────────────────────────

def process_item(item):
    article = item.get("article", {})
    title   = str(article.get("title", "Unknown Title"))

    print(f"\n  [PROC] {title[:70]}")
    print(f"  [PROC] Source: {article.get('source','?')}")

    # ── 1. Scrape full content ──
    article = scrape_article(article)
    content = str(article.get("content", ""))

    if article.get("scraped"):
        tele_update("scraped")
        print(f"  [PROC] Full scrape: {len(content)} chars")
    else:
        print(f"  [PROC] RSS fallback: {len(content)} chars")

    # ── 2. AI analysis ──
    print(f"  [PROC] Running AI analysis...")
    ai_data = ai_analyze(title, content)
    
    # Failsafe if AI returns nothing at all
    if not ai_data or not isinstance(ai_data, dict):
        ai_data = {
            "severity": "LOW",
            "category": "tech",
            "summary":["AI analysis completely failed."],
        }

    # ── 3. Normalize AI output (type safety) ──
    severity = str(ai_data.get("severity", "LOW")).upper()
    category = normalize_category(ai_data.get("category", "tech"))
    summary  = normalize_summary(ai_data.get("summary", []))
    tags     = normalize_list_field(ai_data.get("tags",[]))
    cves     = normalize_list_field(ai_data.get("cves",[]))
    actors   = normalize_list_field(ai_data.get("actors",[]))
    affected = normalize_list_field(ai_data.get("affected_products",[]))
    
    try:
        confidence = int(ai_data.get("confidence", 1))
    except:
        confidence = 1

    # Summary as plain text for Telegram
    summary_text = "\n".join(f"• {s}" for s in summary)

    # ── 4. Build processed record ──
    processed = {
        "title":             title,
        "link":              str(article.get("link", "")),
        "source":            str(article.get("source", "")),
        "severity":          severity,
        "category":          category,
        "confidence":        confidence,
        "summary":           summary,           # list of strings
        "summary_text":      summary_text,      # plain text for Telegram
        "tags":              tags,
        "cves":              cves,
        "actors":            actors,
        "affected_products": affected,
        "scraped":           bool(article.get("scraped", False)),
        "paywall":           bool(article.get("paywall", False)),
        "fp":                str(article.get("fp", "")),
        "timestamp":         int(time.time()),
    }

    print(f"  [PROC] Severity: {severity} | Category: {category}")

    # ── 5. Save (ALL severities) ──
    save_article(processed)
    tele_update("processed", severity=severity)

    # ── 6. Immediate alert ONLY for DEAD SERIOUS items ──
    if is_dead_serious(processed):
        print(f"  [PROC] 🚨 DEAD SERIOUS EVENT DETECTED — Sending Immediate Alert")
        notify_immediate(processed)
    elif severity in IMMEDIATE_ALERT_LEVELS:
        print(f"  [PROC] Alert suppressed to prevent spam (will appear in 8hr digest).")

    return processed


# ─────────────────────────────────────────────────────────────
# DRAIN QUEUE
# ─────────────────────────────────────────────────────────────

def run_worker():
    print("\n[WORKER] Starting...\n")

    processed_all = []
    failed_all    =[]
    total         = get_pending_count()
    done          = 0

    while True:
        item = get_next_item()
        if not item:
            print("\n[WORKER] Queue empty — done")
            break

        done += 1
        article = item.get("article", {})
        print(f"\n[WORKER] {done}/{total}")

        try:
            result = process_item(item)
            processed_all.append(result)
            mark_done(item["id"])
            mark_as_seen([article])

        except Exception as e:
            print(f"[WORKER] FATAL ERROR on item: {e}")
            import traceback
            traceback.print_exc()
            tele_update("failed")
            mark_failed(item["id"])
            failed_all.append(item)

        time.sleep(1)

    print(f"\n[WORKER] Complete: {len(processed_all)} processed, {len(failed_all)} failed")
    return processed_all, failed_all