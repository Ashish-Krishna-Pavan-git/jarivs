"""
dailySummary.py
Morning report: AI correlation across daily digests, audio podcast, WordPress publish,
and Sunday Weekly "Doom vs Bloom" edition.

CRITICAL FIX: Digest files live in /tmp/ which resets on Space restart.
When the 7AM daily summary runs, digests from earlier cycles are often gone.
Fix: if no digests found, fall back to generating AI summary DIRECTLY from articles.
This ensures the daily report, newsletter, and audio always have content.
"""

import json
from datetime import datetime

from storage   import load_last_n_hours, load_today_digests, save_daily_report
from ai_router import ai_daily_summary, ai_weekly_summary, ai_digest as ai_make_digest
from notifier  import send_daily_summary, send_weekly_summary
from intelligence import trend_analysis, severity_breakdown, top_by_severity, source_breakdown

FORCE_TEST_WEEKLY = False   # Only set True manually for testing


def run_daily_summary():
    print("\n[DAILY SUMMARY] Starting morning report...\n")

    # ── Load all items from past 24 hours ──
    all_items = load_last_n_hours(hours=24)
    print(f"[DAILY] {len(all_items)} articles from past 24h")

    if not all_items:
        print("[DAILY] No data to summarize — skipping")
        return

    # ── Load today's cycle digests ──
    digests = load_today_digests()
    print(f"[DAILY] Found {len(digests)} cycle digest(s)")

    # ── AI correlation ──
    # CRITICAL FIX: /tmp/ resets on Space restart, so digests are often missing.
    # Fallback: generate a fresh digest from the raw articles, then run daily summary on it.
    ai_summary = None

    if digests:
        print("[DAILY] Running AI cross-cycle correlation from saved digests...")
        ai_summary = ai_daily_summary(digests)

    if not ai_summary:
        # Digests missing (Space restarted) OR ai_daily_summary failed — generate from articles
        print("[DAILY] No usable digests — generating AI summary directly from articles (fallback)...")
        try:
            fallback_digest = ai_make_digest(all_items, "full-day-fallback")
            if fallback_digest:
                # Wrap in a list so ai_daily_summary can correlate it
                ai_summary = ai_daily_summary([fallback_digest])
            # If ai_daily_summary still fails, use the single digest itself as the summary
            if not ai_summary and fallback_digest:
                print("[DAILY] Using single-digest as daily summary (degraded mode)")
                ai_summary = {
                    "day_headline":       fallback_digest.get("headline", "Daily Intelligence Report"),
                    "escalating_threats": fallback_digest.get("cybersec_updates", []),
                    "new_patterns":       [],
                    "actor_activity":     [],
                    "critical_cves":      fallback_digest.get("key_cves", []),
                    "tech_trends":        fallback_digest.get("ai_updates", []) + fallback_digest.get("tech_business_updates", []),
                    "recommendations":    [],
                    "risk_level":         "HIGH",
                    "day_summary":        fallback_digest.get("strategic_note", ""),
                }
        except Exception as e:
            print(f"[DAILY] Fallback AI generation failed: {e}")

    if not ai_summary:
        print("[DAILY] AI summary completely unavailable — sending stats-only report")

    # ── Build stats ──
    breakdown = severity_breakdown(all_items)
    trends    = trend_analysis(all_items)

    # ── Build report text ──
    now   = datetime.utcnow().strftime("%Y-%m-%d")
    lines = []

    lines.append(f"🗓 DAILY INTELLIGENCE REPORT — {now}")
    lines.append("━" * 45)

    if ai_summary:
        if ai_summary.get("day_headline"):
            lines.append(f"\n🎯 {ai_summary['day_headline']}\n")

        risk      = ai_summary.get("risk_level", "?")
        emoji_map = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "📌", "LOW": "📄"}
        lines.append(f"⚡ RISK LEVEL: {emoji_map.get(risk, '')} {risk}")

        if ai_summary.get("day_summary"):
            lines.append(f"\n{ai_summary['day_summary']}")

        lines.append("\n" + "━" * 45)
        lines.append("📋 KEY TAKEAWAYS:")

        if ai_summary.get("critical_cves"):
            lines.append(f"\n🔴 KEY CVEs: {', '.join(ai_summary['critical_cves'])}")

        if ai_summary.get("escalating_threats"):
            lines.append("\n🔺 ESCALATING THREATS:")
            for t in ai_summary["escalating_threats"]:
                lines.append(f"  • {t}")

        if ai_summary.get("actor_activity"):
            lines.append("\n🎭 THREAT ACTORS:")
            for a in ai_summary["actor_activity"]:
                lines.append(f"  • {a}")

        if ai_summary.get("new_patterns"):
            lines.append("\n🔍 PATTERNS OBSERVED:")
            for p in ai_summary["new_patterns"]:
                lines.append(f"  • {p}")

        if ai_summary.get("tech_trends"):
            lines.append("\n💡 TECH TRENDS:")
            for t in ai_summary["tech_trends"]:
                lines.append(f"  • {t}")

        if ai_summary.get("recommendations"):
            lines.append("\n✅ RECOMMENDATIONS:")
            for r in ai_summary["recommendations"]:
                lines.append(f"  ▶ {r}")
    else:
        lines.append("\n⚠️ AI analysis unavailable for this report.")

    lines.append("\n" + "━" * 45)
    lines.append("\n📊 DAY STATISTICS:")
    lines.append(f"  Total articles: {len(all_items)}")
    for sev, count in breakdown.items():
        emoji = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "📌",
                 "LOW": "📄", "MINIMAL": "ℹ️"}.get(sev, "")
        if count > 0:
            lines.append(f"  {emoji} {sev}: {count}")

    # Top sources
    sources = source_breakdown(all_items)
    top_sources = list(sources.items())[:5]
    if top_sources:
        lines.append(f"\n📡 TOP SOURCES: " + " | ".join(f"{s}:{c}" for s, c in top_sources))

    report_text = "\n".join(lines)

    # ── Save report ──
    report_data = {
        "date":         now,
        "total":        len(all_items),
        "breakdown":    breakdown,
        "trends":       trends,
        "ai_summary":   ai_summary,
        "generated_at": datetime.utcnow().isoformat(),
    }
    save_daily_report(report_data, report_text)
    print("[DAILY] Report saved to disk")

    # ── 1. Send via Telegram ──
    send_daily_summary(all_items, ai_summary)
    print("[DAILY] Report sent to Telegram")

    # ── 2. Generate & send audio podcast ──
    try:
        from audio_generator import generate_daily_audio
        from notifier import send_audio
        audio_path = generate_daily_audio(ai_summary)
        if audio_path:
            send_audio(audio_path)
            print("[DAILY] Audio podcast sent")
        else:
            print("[DAILY] Audio generation skipped")
    except Exception as e:
        print(f"[DAILY] Audio error: {e}")

    # ── 3. Publish WordPress newsletter ──
    try:
        from newsletter_publisher import save_and_publish_newsletter
        save_and_publish_newsletter(ai_summary, all_items)
    except Exception as e:
        print(f"[DAILY] Newsletter error: {e}")

    # ─────────────────────────────────────────────────────────
    # PHASE 3: SUNDAY "DOOM VS BLOOM" WEEKLY EDITION
    # ─────────────────────────────────────────────────────────
    current_day = datetime.now().weekday()   # 0=Monday … 6=Sunday
    is_sunday   = (current_day == 6)

    if is_sunday or FORCE_TEST_WEEKLY:
        print("\n[WEEKLY] Triggering Sunday 'Doom vs Bloom' edition...")
        weekly_items = load_last_n_hours(168)   # 7 days

        if len(weekly_items) >= 10:
            print(f"[WEEKLY] {len(weekly_items)} articles from past 7 days")
            print("[WEEKLY] Running AI weekly correlation...")
            weekly_ai = ai_weekly_summary(weekly_items)
            if not weekly_ai:
                print("[WEEKLY] AI weekly failed — sending stats-only weekly")
            send_weekly_summary(weekly_items, weekly_ai)
            print("[WEEKLY] Sunday digest sent!")
        else:
            print(f"[WEEKLY] Not enough data yet ({len(weekly_items)} items). Need 10+.")
    else:
        print(f"[DAILY] Weekly summary skipped (today is not Sunday, weekday={current_day})")


if __name__ == "__main__":
    run_daily_summary()