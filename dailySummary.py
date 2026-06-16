"""
dailySummary.py — Morning report pipeline.
Sends the full daily intelligence report to:
  1. Telegram (text)
  2. Audio podcast (full report, not just a snippet)
  3. WordPress newsletter (full HTML report)
  4. Sunday: Weekly Doom vs Bloom edition

CRITICAL FIX: /tmp/ resets on HF restart — digests lost.
Fix: if no digests found, generate AI summary directly from articles.
This ensures audio and newsletter always have real content.
"""

import json
from datetime import datetime

from storage    import load_last_n_hours, load_today_digests, save_daily_report
from ai_router  import ai_daily_summary, ai_weekly_summary, ai_digest as ai_make_digest
from notifier   import send_daily_summary, send_weekly_summary
from intelligence import trend_analysis, severity_breakdown, source_breakdown

FORCE_TEST_WEEKLY = False


def run_daily_summary():
    print("\n[DAILY] Starting morning report pipeline...\n")

    all_items = load_last_n_hours(hours=24)
    print(f"[DAILY] {len(all_items)} articles from past 24h")

    if not all_items:
        print("[DAILY] No data — skipping")
        return

    # ── Get AI summary ──────────────────────────────────────────────────────
    digests    = load_today_digests()
    ai_summary = None
    print(f"[DAILY] Found {len(digests)} saved digest(s)")

    if digests:
        print("[DAILY] Running cross-cycle AI correlation...")
        ai_summary = ai_daily_summary(digests)

    if not ai_summary:
        # /tmp/ was cleared on restart — rebuild from articles directly
        print("[DAILY] No usable digests — generating AI summary from articles (fallback)...")
        try:
            fallback = ai_make_digest(all_items, "full-day")
            if fallback:
                ai_summary = ai_daily_summary([fallback])
            if not ai_summary and fallback:
                # Degrade gracefully — use single digest as daily summary
                print("[DAILY] Using single-digest fallback (degraded mode)")
                ai_summary = {
                    "day_headline":      fallback.get("headline","Daily Intelligence Report"),
                    "escalating_threats":fallback.get("cybersec_updates",[]),
                    "new_patterns":      [],
                    "actor_activity":    [],
                    "critical_cves":     fallback.get("key_cves",[]),
                    "tech_trends":       fallback.get("ai_updates",[]) + fallback.get("tech_business_updates",[]),
                    "recommendations":   [],
                    "risk_level":        "HIGH",
                    "day_summary":       fallback.get("strategic_note",""),
                }
        except Exception as e:
            print(f"[DAILY] Fallback AI failed: {e}")

    if not ai_summary:
        print("[DAILY] AI completely unavailable — stats-only report")

    # ── Build report ────────────────────────────────────────────────────────
    breakdown = severity_breakdown(all_items)
    trends    = trend_analysis(all_items)
    sources   = source_breakdown(all_items)
    now       = datetime.utcnow().strftime("%Y-%m-%d")

    # ── 1. Send Telegram ────────────────────────────────────────────────────
    send_daily_summary(all_items, ai_summary)
    print("[DAILY] ✓ Telegram report sent")

    # ── 2. Generate and send audio podcast (full report) ───────────────────
    try:
        from audio_generator import generate_daily_audio
        from notifier import send_audio
        audio_path = generate_daily_audio(ai_summary)
        if audio_path:
            send_audio(audio_path)
            print("[DAILY] ✓ Audio podcast sent")
        else:
            print("[DAILY] Audio generation failed — skipping")
    except Exception as e:
        print(f"[DAILY] Audio error: {e}")

    # ── 3. Publish full WordPress newsletter ────────────────────────────────
    try:
        from newsletter_publisher import save_and_publish_newsletter
        save_and_publish_newsletter(ai_summary, all_items)
        print("[DAILY] ✓ Newsletter published")
    except Exception as e:
        print(f"[DAILY] Newsletter error: {e}")

    # ── 4. Save report ──────────────────────────────────────────────────────
    report_data = {
        "date":         now,
        "total":        len(all_items),
        "breakdown":    breakdown,
        "trends":       trends,
        "top_sources":  dict(list(sources.items())[:10]),
        "ai_summary":   ai_summary,
        "generated_at": datetime.utcnow().isoformat(),
    }
    lines = [f"JARVIS DAILY REPORT — {now}"]
    if ai_summary:
        lines.append(f"Headline: {ai_summary.get('day_headline','')}")
        lines.append(f"Risk: {ai_summary.get('risk_level','?')}")
        lines.append(ai_summary.get('day_summary',''))
    lines.append(f"Total articles: {len(all_items)}")
    save_daily_report(report_data, "\n".join(lines))
    print("[DAILY] ✓ Report saved")

    # ── 5. Sunday Weekly Edition ────────────────────────────────────────────
    current_day = datetime.now().weekday()   # 0=Mon … 6=Sun
    if current_day == 6 or FORCE_TEST_WEEKLY:
        print("\n[WEEKLY] Triggering Sunday Doom vs Bloom edition...")
        weekly_items = load_last_n_hours(168)
        if len(weekly_items) >= 10:
            print(f"[WEEKLY] {len(weekly_items)} articles from past 7 days — running AI...")
            weekly_ai = ai_weekly_summary(weekly_items)
            send_weekly_summary(weekly_items, weekly_ai)

            # Weekly audio
            try:
                if weekly_ai:
                    from audio_generator import generate_daily_audio
                    from notifier import send_audio
                    # Build weekly-flavoured summary for audio
                    weekly_audio_summary = {
                        "day_headline":      weekly_ai.get("day_headline",""),
                        "day_summary":       weekly_ai.get("day_summary",""),
                        "risk_level":        weekly_ai.get("risk_level","HIGH"),
                        "escalating_threats":weekly_ai.get("doom",[]),
                        "tech_trends":       weekly_ai.get("bloom",[]),
                        "critical_cves":     weekly_ai.get("key_cves",[]),
                        "recommendations":   [],
                        "new_patterns":      [],
                        "actor_activity":    [],
                    }
                    audio_path = generate_daily_audio(weekly_audio_summary)
                    if audio_path:
                        send_audio(audio_path, caption="🎙️ JARVIS Sunday Weekly Intelligence Podcast")
                        print("[WEEKLY] ✓ Weekly audio sent")
            except Exception as e:
                print(f"[WEEKLY] Audio error: {e}")

            # Weekly newsletter
            try:
                from newsletter_publisher import save_and_publish_newsletter
                save_and_publish_newsletter(weekly_ai, weekly_items)
                print("[WEEKLY] ✓ Newsletter published")
            except Exception as e:
                print(f"[WEEKLY] Newsletter error: {e}")

            print("[WEEKLY] ✓ Sunday digest complete")
        else:
            print(f"[WEEKLY] Not enough data ({len(weekly_items)} items, need 10+)")
    else:
        print(f"[DAILY] Not Sunday (weekday={current_day}) — weekly skipped")

    print("\n[DAILY] Pipeline complete ✓\n")


if __name__ == "__main__":
    run_daily_summary()
