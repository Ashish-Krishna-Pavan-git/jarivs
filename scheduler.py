"""
scheduler.py
Main orchestrator. Runs every 8 hours.
Tracks cycle count and triggers daily summary at 7 AM IST.
"""

import time
import json
import os
from datetime import datetime, timezone, timedelta

from internet_monitor  import wait_for_internet
from collector         import collect_all
from dedupe            import get_new_articles
from queue_manager     import add_batch, reset_stuck, clear_done, stats as queue_stats
from worker_processor  import run_worker
from ai_router         import ai_digest
from notifier          import send_digest
from storage           import save_digest, load_last_n_hours
from archive_manager   import archive_old_data
import dailySummary    # Imported as a module so we can override its test flags
from telemetry         import update as tele_update, print_stats
from config            import CYCLE_INTERVAL
from bot_listener      import start_listener

# ─────────────────────────────────────────────────────────────
# TESTING TOGGLES
# ─────────────────────────────────────────────────────────────
# Set to True to test immediately. Set to False for normal operation.
TEST_MODE_DAILY  = False  # Trigger 7 AM Daily Summary after the next cycle
TEST_MODE_WEEKLY = False  # Trigger Sunday "Doom vs Bloom" report after the next cycle

DIGEST_STATE_FILE = "digest_state.json"

# Define Indian Standard Time (UTC + 5:30)
IST = timezone(timedelta(hours=5, minutes=30))


# ─────────────────────────────────────────────────────────────
# DIGEST STATE (tracks cycle numbers + daily summary flag)
# ─────────────────────────────────────────────────────────────

def _load_state():
    if not os.path.exists(DIGEST_STATE_FILE):
        return {"cycle_num": 0, "last_daily_date": "", "last_cycle_at": ""}
    try:
        with open(DIGEST_STATE_FILE) as f:
            return json.load(f)
    except:
        return {"cycle_num": 0, "last_daily_date": "", "last_cycle_at": ""}


def _save_state(state):
    with open(DIGEST_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _should_run_daily():
    """Check if we should send daily summary today (7 AM IST, once per day)."""
    if TEST_MODE_DAILY or TEST_MODE_WEEKLY:
        print("[SCHEDULER] TEST MODE: Triggering Daily/Weekly Summary immediately.")
        return True

    state = _load_state()
    now_ist = datetime.now(IST)
    today_ist = now_ist.strftime("%Y-%m-%d")

    # If we already sent it today (in IST), do not send again
    if state.get("last_daily_date") == today_ist:
        return False

    # Fire if the current hour in India is 7 AM or later
    if now_ist.hour >= 7:
        return True

    return False


# ─────────────────────────────────────────────────────────────
# SINGLE CYCLE
# ─────────────────────────────────────────────────────────────

def run_cycle():
    state     = _load_state()
    cycle_num = state["cycle_num"] + 1

    print(f"\n{'='*50}")
    print(f"[SCHEDULER] CYCLE {cycle_num} — {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*50}\n")

    tele_update("cycle_start")

    # ── 1. Wait for internet ──
    wait_for_internet()

    # ── 2. Reset any stuck queue items ──
    reset_stuck()

    # ── 3. Collect articles ──
    print("[CYCLE] Collecting from all sources...")
    raw_articles = collect_all()
    print(f"[CYCLE] Collected: {len(raw_articles)}")

    # ── 4. Deduplicate ──
    new_articles = get_new_articles(raw_articles)
    print(f"[CYCLE] New articles after dedupe: {len(new_articles)}")

    if not new_articles:
        print("[CYCLE] Nothing new — skipping processing")
        return

    # ── 5. Queue ──
    add_batch(new_articles)
    print(f"[CYCLE] Queue stats: {queue_stats()}")

    # ── 6. Process (AI analyze + save + instant alerts) ──
    processed_items, failed_items = run_worker()

    # ── 7. Build 8hr AI digest ──
    digest_data = None
    if processed_items:
        print("\n[CYCLE] Building AI digest...")
        digest_data = ai_digest(processed_items, f"Cycle {cycle_num}")
        if digest_data:
            save_digest(digest_data, cycle_num)
            print("[CYCLE] Digest saved")

    # ── 8. Send 8hr Telegram digest ──
    send_digest(processed_items, cycle_num, digest_data)

    # ── 9. Clean up done items ──
    clear_done()

    # ── 10. Archive old data ──
    archive_old_data(days=3)

    # ── 11. Print stats ──
    print_stats()

    # ── 12. Update state ──
    state["cycle_num"]     = cycle_num
    state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    print(f"\n[CYCLE {cycle_num}] Complete ✓\n")


# ─────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────

def start_scheduler():
    print("\n[JARVIS] Intelligence System Started")
    print(f"[JARVIS] Cycle interval: every 8 hours")
    print(f"[JARVIS] Daily summary: 7:00 AM IST\n")
    
    # Start the Telegram background listener
    start_listener()

    while True:
        cycle_start = time.time()

        try:
            # Run main cycle
            run_cycle()

            # Check if daily summary should fire
            if _should_run_daily():
                print("\n[JARVIS] Running daily morning summary...")
                
                # Pass the weekly test toggle directly to the dailySummary module
                dailySummary.FORCE_TEST_WEEKLY = TEST_MODE_WEEKLY
                dailySummary.run_daily_summary()

                # Mark today's summary as done (using IST date)
                if not TEST_MODE_DAILY and not TEST_MODE_WEEKLY:
                    state = _load_state()
                    now_ist = datetime.now(IST)
                    state["last_daily_date"] = now_ist.strftime("%Y-%m-%d")
                    _save_state(state)

        except KeyboardInterrupt:
            print("\n[JARVIS] Stopped by user")
            break

        except Exception as e:
            print(f"\n[JARVIS] FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()

        # ── Sleep until next cycle ──
        elapsed  = time.time() - cycle_start
        sleep_for = max(0, CYCLE_INTERVAL - elapsed)

        hours   = int(sleep_for // 3600)
        minutes = int((sleep_for % 3600) // 60)
        print(f"\n[JARVIS] Next cycle in {hours}h {minutes}m")
        time.sleep(sleep_for)


if __name__ == "__main__":
    start_scheduler()