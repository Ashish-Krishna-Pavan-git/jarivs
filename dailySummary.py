"""
dailySummary.py
Loads all cycle data, runs AI correlation, generates daily summary, 
creates the Audio podcast, publishes the WordPress newsletter, 
and triggers the Weekly Sunday Digest.
"""

import json
from datetime import datetime

from storage    import load_last_n_hours, load_today_digests, save_daily_report
from ai_router  import ai_daily_summary, ai_weekly_summary
from notifier   import send_daily_summary, send_weekly_summary
from intelligence import (
    trend_analysis, severity_breakdown,
    top_by_severity, source_breakdown
)

# ─────────────────────────────────────────────────────────────
# TESTING TOGGLE
# ─────────────────────────────────────────────────────────────
# ⚠️ Set this to True to force the Sunday "Doom vs Bloom" report right now!
# ⚠️ Set it back to False for normal Sunday-only operation.
FORCE_TEST_WEEKLY = True


def run_daily_summary():
    print("\n[DAILY SUMMARY] Starting morning report...\n")

    # ── Load all items from past 24 hours ──
    all_items = load_last_n_hours(hours=24)
    print(f"[DAILY] Loaded {len(all_items)} items from past 24h")

    if not all_items:
        print("[DAILY] No data to summarize")
        return

    # ── Load today's 3 cycle digests ──
    digests = load_today_digests()
    print(f"[DAILY] Found {len(digests)} cycle digests")

    # ── Run AI correlation across all 3 digests ──
    ai_summary = None
    if digests:
        print("[DAILY] Running AI correlation across all cycles...")
        ai_summary = ai_daily_summary(digests)
    else:
        print("[DAILY] No digests available — AI daily skipped")

    # ── Build stats ──
    breakdown = severity_breakdown(all_items)
    trends    = trend_analysis(all_items)
    criticals = top_by_severity(all_items, "CRITICAL", 5)
    highs     = top_by_severity(all_items, "HIGH", 10)

    # ── Build report text ──
    now  = datetime.utcnow().strftime("%Y-%m-%d")
    lines =[]

    lines.append(f"🗓 DAILY INTELLIGENCE REPORT — {now}")
    lines.append("━" * 45)

    if ai_summary:
        if ai_summary.get("day_headline"):
            lines.append(f"\n🎯 {ai_summary['day_headline']}\n")

        risk = ai_summary.get("risk_level", "?")
        emoji_map = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "📌", "LOW": "📄"}
        lines.append(f"⚡ RISK LEVEL: {emoji_map.get(risk,'')} {risk}")

        if ai_summary.get("day_summary"):
            lines.append(f"\n{ai_summary['day_summary']}")

        lines.append("\n" + "━" * 45)
        lines.append("📋 QUICK REFERENCE / KEY TAKEAWAYS:")

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
            lines.append("\n🔍 OBSERVED PATTERNS:")
            for p in ai_summary["new_patterns"]:
                lines.append(f"  • {p}")

        if ai_summary.get("tech_trends"):
            lines.append("\n💡 TECH TRENDS:")
            for t in ai_summary["tech_trends"]:
                lines.append(f"  • {t}")

        if ai_summary.get("recommendations"):
            lines.append("\n✅ ACTIONABLE RECOMMENDATIONS:")
            for r in ai_summary["recommendations"]:
                lines.append(f"  ▶ {r}")

    lines.append("\n" + "━" * 45)
    lines.append("\n📊 DAY STATISTICS:")
    lines.append(f"  Total articles: {len(all_items)}")
    for sev, count in breakdown.items():
        emoji = {"CRITICAL":"🚨","HIGH":"⚠️","MEDIUM":"📌","LOW":"📄","MINIMAL":"ℹ️"}.get(sev,"")
        lines.append(f"  {emoji} {sev}: {count}")

    report_text = "\n".join(lines)

    # ── Save report ──
    report_data = {
        "date":       now,
        "total":      len(all_items),
        "breakdown":  breakdown,
        "trends":     trends,
        "ai_summary": ai_summary,
        "generated_at": datetime.utcnow().isoformat(),
    }

    save_daily_report(report_data, report_text)
    print("[DAILY] Report saved")

    # ── 1. Send via Telegram ──
    send_daily_summary(all_items, ai_summary)
    print("[DAILY] Report sent to Telegram")

    # ── 2. Generate & Send Audio Podcast ──
    from audio_generator import generate_daily_audio
    from notifier import send_audio
    audio_path = generate_daily_audio(ai_summary)
    if audio_path:
        send_audio(audio_path)

    # ── 3. Publish WordPress Newsletter ──
    from newsletter_publisher import save_and_publish_newsletter
    save_and_publish_newsletter(ai_summary, all_items)
    
    # ─────────────────────────────────────────────────────────
    # PHASE 3: SUNDAY "DOOM VS BLOOM" EDITION
    # ─────────────────────────────────────────────────────────
    current_day = datetime.now().weekday() # Monday is 0, Sunday is 6
    is_sunday = (current_day == 6)
    
    if is_sunday or FORCE_TEST_WEEKLY:
        print("\n[WEEKLY SUMMARY] Triggering Sunday 'Doom vs Bloom' Edition...")
        weekly_items = load_last_n_hours(168) # 7 days * 24 hours
        
        if len(weekly_items) > 0:
            print(f"[WEEKLY] Loaded {len(weekly_items)} items from the past 7 days.")
            print("[WEEKLY] Running AI weekly correlation...")
            weekly_ai = ai_weekly_summary(weekly_items)
            
            send_weekly_summary(weekly_items, weekly_ai)
            print("[WEEKLY] Sunday digest sent to Telegram!")
        else:
            print("[WEEKLY] Not enough data for weekly summary yet.")


if __name__ == "__main__":
    run_daily_summary()