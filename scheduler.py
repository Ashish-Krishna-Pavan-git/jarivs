"""
scheduler.py
Main orchestrator. Runs every 8 hours.
Tracks cycle count and triggers daily summary at 7 AM IST.

CHANGES vs original:
  - Pulls HF state at boot, pushes after each cycle (persistence across restarts)
  - _should_run_daily() is more robust (handles midnight edge case)
  - TEST_MODE flags are both False by default
  - queue cleared at start of each cycle (in-memory queue)
  - better error messages
"""

import time
import json
import os
from datetime import datetime, timezone, timedelta

from internet_monitor import wait_for_internet
from collector        import collect_all
from dedupe           import get_new_articles, mark_as_seen
from queue_manager    import add_batch, reset_stuck, clear_done, clear_all, stats as queue_stats
from worker_processor import run_worker
from ai_router        import ai_digest
from notifier         import send_digest
from storage          import save_digest, load_last_n_hours
from archive_manager  import archive_old_data
import dailySummary
from telemetry        import update as tele_update, print_stats
from config           import CYCLE_INTERVAL, DIGEST_STATE_FILE
from bot_listener     import start_listener
from storage_backend  import pull_state, push_state, is_configured


# ─────────────────────────────────────────────────────────────
# TESTING TOGGLES  (both False for production)
# ─────────────────────────────────────────────────────────────
TEST_MODE_DAILY  = False   # True → trigger 7 AM daily summary right after next cycle
TEST_MODE_WEEKLY = False   # True → trigger Sunday Doom vs Bloom right after next cycle

# Indian Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))


# ─────────────────────────────────────────────────────────────
# CYCLE STATE  (persisted to HF Dataset via storage_backend)
# ─────────────────────────────────────────────────────────────

def _load_state() -> dict:
    if not os.path.exists(DIGEST_STATE_FILE):
        return {"cycle_num": 0, "last_daily_date": "", "last_cycle_at": ""}
    try:
        with open(DIGEST_STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"cycle_num": 0, "last_daily_date": "", "last_cycle_at": ""}


def _save_state(state: dict):
    with open(DIGEST_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _should_run_daily() -> bool:
    """
    Returns True if daily summary should run NOW.
    Rules:
      - TEST_MODE_DAILY or TEST_MODE_WEEKLY → always True
      - Otherwise: only once per IST calendar day, and only after 7 AM IST
    """
    if TEST_MODE_DAILY or TEST_MODE_WEEKLY:
        print("[SCHEDULER] TEST MODE: Triggering Daily/Weekly Summary")
        return True

    state      = _load_state()
    now_ist    = datetime.now(IST)
    today_ist  = now_ist.strftime("%Y-%m-%d")

    if state.get("last_daily_date") == today_ist:
        return False   # Already ran today

    if now_ist.hour >= 7:
        return True

    return False


# ─────────────────────────────────────────────────────────────
# SINGLE CYCLE
# ─────────────────────────────────────────────────────────────

def run_cycle():
    state     = _load_state()
    cycle_num = state["cycle_num"] + 1

    print(f"\n{'='*55}")
    print(f"[SCHEDULER] CYCLE {cycle_num} — {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*55}\n")

    tele_update("cycle_start")

    # ── 1. Internet check ──
    wait_for_internet()

    # ── 2. Clear in-memory queue from previous cycle ──
    clear_all()
    reset_stuck()
    # Reset dedupe cache so it reloads from disk (picks up HF-pulled seen.json)
    from dedupe import reset_cache
    reset_cache()

    # ── 3. Collect articles ──
    print("[CYCLE] Collecting from all RSS sources...")
    raw_articles = collect_all()
    print(f"[CYCLE] Collected: {len(raw_articles)} total")

    # ── 4. Deduplicate ──
    new_articles = get_new_articles(raw_articles)
    print(f"[CYCLE] New after dedup: {len(new_articles)}")

    if not new_articles:
        print("[CYCLE] Nothing new — skipping processing")
        # Still update state and push
        state["cycle_num"]     = cycle_num
        state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
        _save_state(state)
        push_state(new_articles=[])
        return

    # ── 5. Add to queue ──
    add_batch(new_articles)
    print(f"[CYCLE] Queue: {queue_stats()}")

    # ── 6. Process (AI analyze + save + instant alerts) ──
    processed_items, failed_items = run_worker()

    # ── 7. Build 8hr AI digest ──
    digest_data = None
    if processed_items:
        print("\n[CYCLE] Generating AI digest...")
        digest_data = ai_digest(processed_items, f"Cycle {cycle_num}")
        if digest_data:
            save_digest(digest_data, cycle_num)
            print("[CYCLE] Digest saved")
        else:
            print("[CYCLE] ⚠️ AI digest generation failed")

    # ── 8. Send Telegram digest ──
    send_digest(processed_items, cycle_num, digest_data)

    # ── 9. Cleanup ──
    clear_done()
    archive_old_data(days=3)
    print_stats()

    # ── 10. Update + persist state ──
    state["cycle_num"]     = cycle_num
    state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    # ── 11. Push everything to HF Dataset ──
    if is_configured():
        print("[CYCLE] Syncing state to HF Dataset...")
        push_state(new_articles=processed_items)
    else:
        print("[CYCLE] ⚠️ HF_STORAGE_REPO not set — state will not persist across restarts")
        print("         Set HF_TOKEN and HF_STORAGE_REPO in Space secrets to enable persistence")

    print(f"\n[CYCLE {cycle_num}] ✓ Complete — processed {len(processed_items)}, failed {len(failed_items)}\n")


# ─────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────

def start_scheduler():
    print("\n" + "="*55)
    print(" JARVIS Intelligence System — Starting")
    print(f" Cycle interval : every 8 hours")
    print(f" Daily summary  : 7:00 AM IST")
    print(f" HF Persistence : {'✓ Enabled' if is_configured() else '✗ Not configured (add HF_TOKEN + HF_STORAGE_REPO)'}")
    print("="*55 + "\n")

    # ── Pull persisted state from HF Dataset before first cycle ──
    if is_configured():
        print("[JARVIS] Restoring state from HF Dataset...")
        pull_state()
    
    # ── Start Telegram bot listener (background thread) ──
    start_listener()

    while True:
        cycle_start = time.time()

        try:
            run_cycle()

            # ── Check if daily summary should fire ──
            if _should_run_daily():
                print("\n[JARVIS] Running 7 AM daily morning summary...")

                # Pass weekly test toggle to dailySummary module
                dailySummary.FORCE_TEST_WEEKLY = TEST_MODE_WEEKLY
                dailySummary.run_daily_summary()

                # Mark daily as done for today (skip test modes from marking)
                if not TEST_MODE_DAILY and not TEST_MODE_WEEKLY:
                    state = _load_state()
                    now_ist = datetime.now(IST)
                    state["last_daily_date"] = now_ist.strftime("%Y-%m-%d")
                    _save_state(state)
                    # Push updated state immediately after daily summary
                    if is_configured():
                        push_state(new_articles=[])

        except KeyboardInterrupt:
            print("\n[JARVIS] Stopped by user. Goodbye.")
            break

        except Exception as e:
            print(f"\n[JARVIS] ⚠️ Cycle error: {e}")
            import traceback
            traceback.print_exc()
            print("[JARVIS] Continuing to next cycle...")

        # ── Sleep until next cycle ──
        elapsed   = time.time() - cycle_start
        sleep_for = max(60, CYCLE_INTERVAL - elapsed)   # Min 60s gap
        hours     = int(sleep_for // 3600)
        minutes   = int((sleep_for % 3600) // 60)
        print(f"\n[JARVIS] 💤 Next cycle in {hours}h {minutes}m")
        time.sleep(sleep_for)


if __name__ == "__main__":
    start_scheduler()
