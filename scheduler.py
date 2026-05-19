"""
scheduler.py — JARVIS main orchestrator.

Schedule (IST = UTC+5:30):
  07:00 → Daily Summary + Audio + Newsletter
  08:00 → Cycle 1
  15:00 → Cycle 2
  21:00 → Cycle 3

FIX: Keep-alive thread pings Space URL every 4 minutes — prevents HF sleep after 48h.
FIX: Slot window = 6 minutes (was 4, too tight on restart).
FIX: last_cycle_started_at / last_cycle_finished_at tracked in runtime state.
"""

import os, sys, time, threading, traceback
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

def now_ist(): return datetime.now(IST)
def fmt_ist(dt=None): return (dt or now_ist()).strftime("%Y-%m-%d %H:%M IST")


# ─── Schedule ─────────────────────────────────────────────────────────────────
CYCLE_SLOTS = [
    (8,  0, "08:00 IST"),
    (15, 0, "15:00 IST"),
    (21, 0, "21:00 IST"),
]
_DAILY_HOUR      = int(os.getenv("DAILY_SUMMARY_HOUR","7"))
_SLOT_WINDOW_MINS = 6


# ─── Runtime state helper ─────────────────────────────────────────────────────
def _update_state(**kwargs):
    try:
        from runtime_state import update_runtime_state
        update_runtime_state(**kwargs)
    except Exception as e:
        print(f"[SCHED] state error: {e}")


# ─── Next slot ────────────────────────────────────────────────────────────────
def _next_cycle_dt():
    now = now_ist()
    for h,m,_ in CYCLE_SLOTS:
        c = now.replace(hour=h,minute=m,second=0,microsecond=0)
        if c > now: return c
    tomorrow = now+timedelta(days=1)
    h,m,_ = CYCLE_SLOTS[0]
    return tomorrow.replace(hour=h,minute=m,second=0,microsecond=0)


# ─── Keep-alive (prevents HF Space sleeping after 48h) ───────────────────────
def _keep_alive_thread():
    """
    Pings the HF Space URL every 4 minutes.
    HF Spaces sleep after ~48h of no external traffic.
    With UptimeRobot pinging /ping every 5 min this thread acts as a local backup.
    """
    import requests as req
    hf_url = os.getenv("HF_SPACE_URL","").rstrip("/")
    # Always try localhost — works whether webhook mode is on or not
    local_url = "http://localhost:7860/ping"
    urls = [local_url]
    if hf_url:
        urls.insert(0, f"{hf_url}/ping")

    time.sleep(60)  # Let everything start first
    print(f"[KEEPALIVE] Thread started — pinging every 4 minutes")
    while True:
        for url in urls:
            try:
                req.get(url, timeout=8)
            except Exception:
                pass
        time.sleep(240)   # 4 minutes


# ─── Intelligence Cycle ───────────────────────────────────────────────────────
_cycle_counter = 0
_cycle_lock    = threading.Lock()


def run_cycle(slot_label, boot_cycle=False):
    global _cycle_counter
    with _cycle_lock:
        _cycle_counter += 1
        cycle_num = _cycle_counter

    prefix     = "[BOOT-CYCLE]" if boot_cycle else f"[CYCLE {cycle_num}]"
    started_at = fmt_ist()

    print(f"\n{'='*60}\n{prefix} Starting — {slot_label}\n{prefix} IST: {started_at}\n{'='*60}\n")
    _update_state(phase="collecting", current_cycle_number=cycle_num,
                  current_cycle_slot=slot_label, last_cycle_started_at=started_at,
                  current_item_title="", queue_total=0, queue_done=0, queue_failed=0)

    processed_items = []
    try:
        from internet_monitor import wait_for_internet
        wait_for_internet()

        try:
            from storage_backend import is_configured, pull_state
            if is_configured(): pull_state()
        except Exception as e:
            print(f"{prefix} HF pull warning: {e}")

        from telemetry import update as tele_update
        tele_update("cycle_start")

        from dedupe import reset_cache
        reset_cache()

        from queue_manager import clear_all, add_batch, reset_stuck
        clear_all()

        _update_state(phase="collecting")
        from collector import collect_all
        raw = collect_all(limit_per_source=40)
        print(f"{prefix} Collected {len(raw)} articles")

        from dedupe import get_new_articles
        new_articles = get_new_articles(raw)
        print(f"{prefix} {len(new_articles)} new after dedup")

        if not new_articles:
            print(f"{prefix} No new articles — skipping")
            _update_state(phase="idle")
            return

        add_batch(new_articles)
        reset_stuck()

        _update_state(phase="processing", queue_total=len(new_articles), queue_done=0, queue_failed=0)
        from worker_processor import run_worker
        processed_items, failed_items = run_worker()
        print(f"{prefix} Processed: {len(processed_items)} | Failed: {len(failed_items)}")

        _update_state(phase="digesting")
        ai_digest_data = None
        if processed_items:
            try:
                from ai_router import ai_digest
                ai_digest_data = ai_digest(processed_items, slot_label)
            except Exception as e:
                print(f"{prefix} AI digest error: {e}")

        if ai_digest_data:
            try:
                from storage import save_digest
                save_digest(ai_digest_data, cycle_num)
            except Exception as e:
                print(f"{prefix} Digest save error: {e}")

        try:
            from notifier import send_digest
            send_digest(processed_items, cycle_num, ai_digest_data)
        except Exception as e:
            print(f"{prefix} Telegram send error: {e}")

        try:
            from archive_manager import archive_old_data
            archive_old_data(days=3)
        except Exception as e:
            print(f"{prefix} Archive error: {e}")

        _update_state(phase="syncing")
        try:
            from storage_backend import is_configured, push_state
            if is_configured():
                push_state(new_articles=processed_items, cycle_num=cycle_num)
                print(f"{prefix} HF state synced")
        except Exception as e:
            print(f"{prefix} HF push error: {e}")

    except Exception as e:
        print(f"{prefix} ⚠️ Cycle error: {e}")
        traceback.print_exc()
    finally:
        finished = fmt_ist()
        _update_state(phase="idle", next_cycle_at_ist=fmt_ist(_next_cycle_dt()),
                      last_cycle_finished_at=finished)
        print(f"\n{prefix} Done at {finished} — next cycle at {fmt_ist(_next_cycle_dt())}\n")


# ─── Daily Summary ────────────────────────────────────────────────────────────
def run_daily():
    print(f"\n{'='*60}\n[DAILY] Starting Daily Summary\n[DAILY] IST: {fmt_ist()}\n{'='*60}\n")
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


# ─── Boot Cycle ───────────────────────────────────────────────────────────────
def _boot_cycle_thread():
    delay = 90
    print(f"[SCHED] Boot cycle in {delay}s")
    time.sleep(delay)
    now = now_ist()
    for h,m,_ in CYCLE_SLOTS:
        slot = now.replace(hour=h,minute=m,second=0,microsecond=0)
        if abs((slot-now).total_seconds()) < 600:
            print("[SCHED] Boot cycle skipped — scheduled slot imminent")
            return
    daily_slot = now.replace(hour=_DAILY_HOUR,minute=0,second=0,microsecond=0)
    if abs((daily_slot-now).total_seconds()) < 600:
        print("[SCHED] Boot cycle skipped — daily summary imminent")
        return
    run_cycle("Boot", boot_cycle=True)


# ─── Main Loop ────────────────────────────────────────────────────────────────
def main():
    print(f"\n[SCHED] ====== JARVIS Scheduler Starting ======\n[SCHED] IST: {fmt_ist()}")

    try:
        from bot_listener import start_listener
        start_listener()
    except Exception as e:
        print(f"[SCHED] Bot listener failed: {e}")
        traceback.print_exc()

    _update_state(phase="idle", current_cycle_number=0, current_cycle_slot=None,
                  next_cycle_at_ist=fmt_ist(_next_cycle_dt()),
                  last_cycle_started_at="", last_cycle_finished_at="")

    # Start keep-alive thread (prevents HF Space sleeping)
    threading.Thread(target=_keep_alive_thread, daemon=True).start()

    threading.Thread(target=_boot_cycle_thread, daemon=True).start()

    print(f"[SCHED] Cycle slots (IST): {[s[2] for s in CYCLE_SLOTS]}")
    print(f"[SCHED] Daily summary hour: {_DAILY_HOUR:02d}:00 IST")
    print(f"[SCHED] Slot window: {_SLOT_WINDOW_MINS} minutes")
    print(f"[SCHED] Next cycle: {fmt_ist(_next_cycle_dt())}")
    print("[SCHED] Scheduling loop active\n")

    ran_slots: set[str] = set()
    while True:
        try:
            now      = now_ist()
            date_str = now.strftime("%Y-%m-%d")
            h, m     = now.hour, now.minute

            daily_key = f"{date_str}-daily"
            if h==_DAILY_HOUR and 0<=m<_SLOT_WINDOW_MINS and daily_key not in ran_slots:
                ran_slots.add(daily_key)
                threading.Thread(target=run_daily, daemon=False).start()

            for slot_h,slot_m,slot_label in CYCLE_SLOTS:
                slot_key = f"{date_str}-{slot_h:02d}"
                if h==slot_h and 0<=m<_SLOT_WINDOW_MINS and slot_key not in ran_slots:
                    ran_slots.add(slot_key)
                    threading.Thread(target=run_cycle, args=(slot_label,),
                                     kwargs={"boot_cycle":False}, daemon=False).start()
                    break

            yesterday = (now-timedelta(days=1)).strftime("%Y-%m-%d")
            ran_slots = {k for k in ran_slots if k.startswith(date_str) or k.startswith(yesterday)}
        except Exception as e:
            print(f"[SCHED] Loop error: {e}")
        time.sleep(30)


if __name__ == "__main__":
    main()