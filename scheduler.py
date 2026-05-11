"""
scheduler.py
JARVIS main orchestrator — runs intelligence cycles and daily summary on schedule.

Schedule (IST = UTC+5:30):
  07:00 IST → Daily Summary + Newsletter
  08:00 IST → Cycle 1
  15:00 IST → Cycle 2
  21:00 IST → Cycle 3

All 3 cycles complete well before 23:00 IST (each takes ~25–30 min).

FIX: _SLOT_WINDOW_MINS raised to 6 (was 4 — too tight if scheduler restarts
     at minute 4 or 5 of the hour, causing the slot to be silently skipped).
FIX: update_runtime_state now includes last_cycle_started_at and last_cycle_finished_at.
"""

import os
import sys
import time
import threading
import traceback
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


def fmt_ist(dt: datetime = None) -> str:
    if dt is None:
        dt = now_ist()
    return dt.strftime("%Y-%m-%d %H:%M IST")


# ─────────────────────────────────────────────────────────────
# SCHEDULE CONFIGURATION
# ─────────────────────────────────────────────────────────────

# (hour_IST, minute_IST, display_label)
CYCLE_SLOTS = [
    (8,  0, "08:00 IST"),
    (15, 0, "15:00 IST"),
    (21, 0, "21:00 IST"),
]

_DAILY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", "7"))

# FIX: raised from 4 to 6 minutes — prevents missed slots on restart
_SLOT_WINDOW_MINS = 6


# ─────────────────────────────────────────────────────────────
# RUNTIME STATE HELPERS
# ─────────────────────────────────────────────────────────────

def _update_state(**kwargs):
    try:
        from runtime_state import update_runtime_state
        update_runtime_state(**kwargs)
    except Exception as e:
        print(f"[SCHED] runtime_state update error: {e}")


# ─────────────────────────────────────────────────────────────
# NEXT-SLOT CALCULATOR
# ─────────────────────────────────────────────────────────────

def _next_cycle_dt() -> datetime:
    """Return the datetime of the very next scheduled cycle slot."""
    now = now_ist()
    for h, m, _ in CYCLE_SLOTS:
        candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if candidate > now:
            return candidate
    # All slots passed today — first slot tomorrow
    tomorrow = now + timedelta(days=1)
    h, m, _ = CYCLE_SLOTS[0]
    return tomorrow.replace(hour=h, minute=m, second=0, microsecond=0)


# ─────────────────────────────────────────────────────────────
# INTELLIGENCE CYCLE
# ─────────────────────────────────────────────────────────────

_cycle_counter = 0
_cycle_lock    = threading.Lock()


def run_cycle(slot_label: str, boot_cycle: bool = False):
    """
    Full intelligence cycle:
      collect → dedupe → queue → worker (AI + save) → digest → push HF.
    """
    global _cycle_counter

    with _cycle_lock:
        _cycle_counter += 1
        cycle_num = _cycle_counter

    prefix = "[BOOT-CYCLE]" if boot_cycle else f"[CYCLE {cycle_num}]"
    started_at = fmt_ist()

    print(f"\n{'='*60}")
    print(f"{prefix} Starting — {slot_label}")
    print(f"{prefix} IST: {started_at}")
    print(f"{'='*60}\n")

    _update_state(
        phase="collecting",
        current_cycle_number=cycle_num,
        current_cycle_slot=slot_label,
        last_cycle_started_at=started_at,
        current_item_title="",
        queue_total=0,
        queue_done=0,
        queue_failed=0,
    )

    processed_items = []

    try:
        # 1. Wait for internet
        from internet_monitor import wait_for_internet
        wait_for_internet()

        # 2. Pull HF state
        try:
            from storage_backend import is_configured, pull_state
            if is_configured():
                pull_state()
        except Exception as e:
            print(f"{prefix} HF pull warning: {e}")

        # 3. Telemetry
        from telemetry import update as tele_update
        tele_update("cycle_start")

        # 4. Reset dedupe cache
        from dedupe import reset_cache
        reset_cache()

        # 5. Clear in-memory queue
        from queue_manager import clear_all, add_batch, reset_stuck
        clear_all()

        # 6. Collect RSS
        _update_state(phase="collecting")
        from collector import collect_all
        raw = collect_all(limit_per_source=40)
        print(f"{prefix} Collected {len(raw)} articles from RSS")

        # 7. Deduplicate
        from dedupe import get_new_articles
        new_articles = get_new_articles(raw)
        print(f"{prefix} {len(new_articles)} new after dedup")

        if not new_articles:
            print(f"{prefix} No new articles — skipping processing")
            _update_state(phase="idle")
            return

        # 8. Enqueue
        add_batch(new_articles)
        reset_stuck()

        # 9. Worker: AI analysis + save
        _update_state(phase="processing", queue_total=len(new_articles), queue_done=0, queue_failed=0)
        from worker_processor import run_worker
        processed_items, failed_items = run_worker()
        print(f"{prefix} Processed: {len(processed_items)} | Failed: {len(failed_items)}")

        # 10. AI digest
        _update_state(phase="digesting")
        ai_digest_data = None
        if processed_items:
            try:
                from ai_router import ai_digest
                ai_digest_data = ai_digest(processed_items, slot_label)
            except Exception as e:
                print(f"{prefix} AI digest error: {e}")

        # 11. Save digest for morning daily-summary
        if ai_digest_data:
            try:
                from storage import save_digest
                save_digest(ai_digest_data, cycle_num)
            except Exception as e:
                print(f"{prefix} Digest save error: {e}")

        # 12. Send Telegram digest
        try:
            from notifier import send_digest
            send_digest(processed_items, cycle_num, ai_digest_data)
        except Exception as e:
            print(f"{prefix} Telegram send error: {e}")

        # 13. Archive old data
        try:
            from archive_manager import archive_old_data
            archive_old_data(days=3)
        except Exception as e:
            print(f"{prefix} Archive error: {e}")

        # 14. Push to HF Dataset
        _update_state(phase="syncing")
        try:
            from storage_backend import is_configured, push_state
            if is_configured():
                push_state(new_articles=processed_items)
                print(f"{prefix} HF state synced")
        except Exception as e:
            print(f"{prefix} HF push error: {e}")

    except Exception as e:
        print(f"{prefix} ⚠️ Cycle error: {e}")
        traceback.print_exc()

    finally:
        finished_at = fmt_ist()
        next_dt     = _next_cycle_dt()
        _update_state(
            phase="idle",
            next_cycle_at_ist=fmt_ist(next_dt),
            last_cycle_finished_at=finished_at,
        )
        print(f"\n{prefix} Done at {finished_at} — next cycle at {fmt_ist(next_dt)}\n")


# ─────────────────────────────────────────────────────────────
# DAILY SUMMARY
# ─────────────────────────────────────────────────────────────

def run_daily():
    print(f"\n{'='*60}")
    print(f"[DAILY] Starting Daily Summary")
    print(f"[DAILY] IST: {fmt_ist()}")
    print(f"{'='*60}\n")

    _update_state(phase="daily_summary")
    try:
        from dailySummary import run_daily_summary
        run_daily_summary()
        _update_state(last_daily_run_ist=fmt_ist())
        print("[DAILY] Complete")
    except Exception as e:
        print(f"[DAILY] Error: {e}")
        traceback.print_exc()
    finally:
        _update_state(phase="idle")


# ─────────────────────────────────────────────────────────────
# BOOT CYCLE — runs once ~90 s after startup
# ─────────────────────────────────────────────────────────────

def _boot_cycle_thread():
    """
    Runs one cycle shortly after startup so we get fresh intelligence
    immediately rather than waiting for the next scheduled slot.
    Skipped if a scheduled slot fires within 10 minutes.
    """
    delay = 90
    print(f"[SCHED] Boot cycle scheduled in {delay}s")
    time.sleep(delay)

    now = now_ist()
    for h, m, _ in CYCLE_SLOTS:
        slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if abs((slot - now).total_seconds()) < 600:
            print("[SCHED] Boot cycle skipped — scheduled slot is imminent")
            return

    daily_slot = now.replace(hour=_DAILY_HOUR, minute=0, second=0, microsecond=0)
    if abs((daily_slot - now).total_seconds()) < 600:
        print("[SCHED] Boot cycle skipped — daily summary is imminent")
        return

    run_cycle("Boot", boot_cycle=True)


# ─────────────────────────────────────────────────────────────
# MAIN SCHEDULING LOOP
# ─────────────────────────────────────────────────────────────

def main():
    print("\n[SCHED] ====== JARVIS Scheduler Starting ======")
    print(f"[SCHED] IST: {fmt_ist()}")

    # Start bot listener (polling or webhook based on env)
    try:
        from bot_listener import start_listener
        start_listener()
    except Exception as e:
        print(f"[SCHED] Bot listener failed to start: {e}")
        traceback.print_exc()

    # Initial runtime state
    _update_state(
        phase="idle",
        current_cycle_number=0,
        current_cycle_slot=None,
        next_cycle_at_ist=fmt_ist(_next_cycle_dt()),
        last_cycle_started_at="",
        last_cycle_finished_at="",
    )

    # Boot cycle (runs once after short delay)
    threading.Thread(target=_boot_cycle_thread, daemon=True).start()

    print(f"[SCHED] Cycle slots (IST): {[s[2] for s in CYCLE_SLOTS]}")
    print(f"[SCHED] Daily summary hour: {_DAILY_HOUR:02d}:00 IST")
    print(f"[SCHED] Slot window: {_SLOT_WINDOW_MINS} minutes")
    print(f"[SCHED] Next cycle: {fmt_ist(_next_cycle_dt())}")
    print("[SCHED] Scheduling loop active\n")

    # Track which slots already ran today (key = "YYYY-MM-DD-HH")
    ran_slots: set[str] = set()

    while True:
        try:
            now      = now_ist()
            date_str = now.strftime("%Y-%m-%d")
            h, m     = now.hour, now.minute

            # Daily summary check
            daily_key = f"{date_str}-daily"
            if h == _DAILY_HOUR and 0 <= m < _SLOT_WINDOW_MINS and daily_key not in ran_slots:
                ran_slots.add(daily_key)
                threading.Thread(target=run_daily, daemon=False).start()

            # Cycle slot checks
            for slot_h, slot_m, slot_label in CYCLE_SLOTS:
                slot_key = f"{date_str}-{slot_h:02d}"
                if h == slot_h and 0 <= m < _SLOT_WINDOW_MINS and slot_key not in ran_slots:
                    ran_slots.add(slot_key)
                    threading.Thread(
                        target=run_cycle,
                        args=(slot_label,),
                        kwargs={"boot_cycle": False},
                        daemon=False,
                    ).start()
                    break

            # Prune old keys — keep today and yesterday
            yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            ran_slots = {k for k in ran_slots if k.startswith(date_str) or k.startswith(yesterday)}

        except Exception as e:
            print(f"[SCHED] Loop error: {e}")

        time.sleep(30)


if __name__ == "__main__":
    main()
