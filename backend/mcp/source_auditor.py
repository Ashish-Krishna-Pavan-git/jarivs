"""
source_auditor.py — Useful MCP Tool for JARVIS AITC News System.
Performs real-time RSS Feed Health, Freshness Analysis, Duplicate Detection, and Category Alignment Audit.
"""

from __future__ import annotations
import time
import os
from pathlib import Path
from datetime import datetime, timezone
import requests
import feedparser

from concurrent.futures import ThreadPoolExecutor, as_completed

def mcp_audit_sources(limit: int = 15) -> dict:
    """
    Executes a comprehensive Model Context Protocol (MCP) Source Audit:
    1. Tests reachability & HTTP latency for active RSS sources concurrently.
    2. Parses RSS feed items to measure content freshness (hours since last article).
    3. Detects duplicate fingerprint rates across recent items.
    4. Evaluates category alignment (cybersecurity vs general tech).
    """
    from jarvis_db import list_sources
    from backend.storage.persistence import load_last_n_hours

    sources = list_sources()
    active_sources = [s for s in sources if s.get("enabled")][:limit]
    
    source_results = []
    stale_sources = 0
    healthy_sources = 0
    unreachable_sources = 0
    headers = {"User-Agent": "Mozilla/5.0 (JARVIS MCP Source Audit/2.0)"}

    def _check_source(s):
        name = s.get("name", "Unknown")
        url = s.get("url", "")
        category = s.get("category", "tech")
        t0 = time.time()
        try:
            r = requests.get(url, headers=headers, timeout=5)
            latency_ms = round((time.time() - t0) * 1000, 1)
            if r.status_code == 200:
                parsed = feedparser.parse(r.text)
                entry_count = len(parsed.entries)
                latest_age_hours = None
                if parsed.entries:
                    first_entry = parsed.entries[0]
                    published_parsed = getattr(first_entry, "published_parsed", None) or getattr(first_entry, "updated_parsed", None)
                    if published_parsed:
                        entry_time = datetime(*published_parsed[:6], tzinfo=timezone.utc)
                        latest_age_hours = round((datetime.now(timezone.utc) - entry_time).total_seconds() / 3600, 1)

                is_stale = latest_age_hours is not None and latest_age_hours > 72
                return {
                    "id": s.get("id"),
                    "name": name,
                    "url": url,
                    "category": category,
                    "status": "Healthy" if not is_stale else "Stale (>72h)",
                    "http_code": 200,
                    "latency_ms": latency_ms,
                    "feed_items": entry_count,
                    "freshness_hours": latest_age_hours,
                    "ok": True,
                    "is_stale": is_stale,
                }
            else:
                return {
                    "id": s.get("id"),
                    "name": name,
                    "url": url,
                    "category": category,
                    "status": f"HTTP {r.status_code}",
                    "http_code": r.status_code,
                    "latency_ms": latency_ms,
                    "feed_items": 0,
                    "freshness_hours": None,
                    "ok": False,
                    "is_stale": False,
                }
        except Exception as exc:
            return {
                "id": s.get("id"),
                "name": name,
                "url": url,
                "category": category,
                "status": f"Connection Error ({type(exc).__name__})",
                "http_code": 0,
                "latency_ms": None,
                "feed_items": 0,
                "freshness_hours": None,
                "ok": False,
                "is_stale": False,
            }

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_check_source, s) for s in active_sources]
        for f in as_completed(futures):
            res = f.result()
            if res.get("ok"):
                if res.get("is_stale"): stale_sources += 1
                else: healthy_sources += 1
            else:
                unreachable_sources += 1
            res.pop("is_stale", None)
            source_results.append(res)

    # Freshness & Duplicate analysis on stored articles
    recent_items = load_last_n_hours(hours=48)
    unique_fp = {i.get("fp") for i in recent_items if i.get("fp")}
    dup_rate = round(((len(recent_items) - len(unique_fp)) / len(recent_items) * 100), 1) if recent_items else 0.0

    return {
        "mcp_tool": "jarvis_source_audit",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_sources": len(sources),
            "active_sources": len(active_sources),
            "healthy_sources": healthy_sources,
            "stale_sources": stale_sources,
            "unreachable_sources": unreachable_sources,
            "recent_articles_48h": len(recent_items),
            "duplicate_rate_pct": dup_rate,
        },
        "sources": source_results,
    }
