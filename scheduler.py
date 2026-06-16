"""
scheduler.py — JARVIS main orchestrator.
Schedule (IST = UTC+5:30):
  07:00 → Daily Summary + Audio + Newsletter
  08:00 → Cycle 1  |  15:00 → Cycle 2  |  21:00 → Cycle 3

Keep-alive thread pings Space every 4 min — prevents HF sleep after 48h.
Slot window = 6 min to survive restarts at the edge of the window.
"""

import os, sys, time, threading, traceback
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
def now_ist(): return datetime.now(IST)
def fmt_ist(dt=None): return (dt or now_ist()).strftime("%Y-%m-%d %H:%M IST")

CYCLE_SLOTS       = [(8,0,"08:00 IST"),(15,0,"15:00 IST"),(21,0,"21:00 IST")]
_DAILY_HOUR       = int(os.getenv("DAILY_SUMMARY_HOUR","7"))
_SLOT_WINDOW_MINS = 6


def _state(**kw):
    try:
        from runtime_state import update_runtime_state
        update_runtime_state(**kw)
    except Exception as e:
        print(f"[SCHED] state err: {e}")


def _next_cycle():
    now = now_ist()
    for h,m,_ in CYCLE_SLOTS:
        c = now.replace(hour=h,minute=m,second=0,microsecond=0)
        if c > now: return c
    t = now+timedelta(days=1); h,m,_=CYCLE_SLOTS[0]
    return t.replace(hour=h,minute=m,second=0,microsecond=0)


# ─── Keep-alive ───────────────────────────────────────────────────────────────
def _keep_alive():
    """Ping every 4 minutes so HF Space never sleeps."""
    import requests as req
    hf  = os.getenv("HF_SPACE_URL","").rstrip("/")
    urls = [u for u in [f"{hf}/ping" if hf else None, "http://localhost:7860/ping"] if u]
    time.sleep(90)
    print("[KEEPALIVE] Started — pinging every 4 minutes")
    while True:
        for url in urls:
            try: req.get(url, timeout=8)
            except: pass
        time.sleep(240)


# ─── Cycle ────────────────────────────────────────────────────────────────────
_counter = 0
_clock   = threading.Lock()

def run_cycle(slot_label, boot_cycle=False):
    global _counter
    with _clock: _counter+=1; n=_counter
    prefix = "[BOOT]" if boot_cycle else f"[CYCLE {n}]"
    started = fmt_ist()
    print(f"\n{'='*60}\n{prefix} {slot_label} — {started}\n{'='*60}\n")
    _state(phase="collecting",current_cycle_number=n,current_cycle_slot=slot_label,
           last_cycle_started_at=started,current_item_title="",
           queue_total=0,queue_done=0,queue_failed=0)
    processed=[]
    try:
        from internet_monitor import wait_for_internet; wait_for_internet()
        try:
            from storage_backend import is_configured,pull_state
            if is_configured(): pull_state()
        except Exception as e: print(f"{prefix} HF pull: {e}")

        from telemetry import update as tu; tu("cycle_start")
        from dedupe import reset_cache; reset_cache()
        from queue_manager import clear_all,add_batch,reset_stuck
        clear_all()

        _state(phase="collecting")
        from collector import collect_all
        raw = collect_all(limit_per_source=40)
        print(f"{prefix} Collected {len(raw)} articles")

        from dedupe import get_new_articles
        new = get_new_articles(raw)
        print(f"{prefix} {len(new)} new after dedup")

        if not new:
            print(f"{prefix} Nothing new — skipping"); _state(phase="idle"); return

        add_batch(new); reset_stuck()
        _state(phase="processing",queue_total=len(new),queue_done=0,queue_failed=0)

        from worker_processor import run_worker
        processed,failed = run_worker()
        print(f"{prefix} Processed:{len(processed)} Failed:{len(failed)}")

        _state(phase="digesting")
        digest_data = None
        if processed:
            try:
                from ai_router import ai_digest
                digest_data = ai_digest(processed, slot_label)
            except Exception as e: print(f"{prefix} Digest AI error: {e}")

        if digest_data:
            try:
                from storage import save_digest; save_digest(digest_data, n)
            except Exception as e: print(f"{prefix} Digest save: {e}")

        try:
            from notifier import send_digest; send_digest(processed, n, digest_data)
        except Exception as e: print(f"{prefix} Telegram: {e}")

        try:
            from archive_manager import archive_old_data; archive_old_data(days=3)
        except Exception as e: print(f"{prefix} Archive: {e}")

        _state(phase="syncing")
        try:
            from storage_backend import is_configured,push_state
            if is_configured(): push_state(new_articles=processed, cycle_num=n)
        except Exception as e: print(f"{prefix} HF push: {e}")

    except Exception as e:
        print(f"{prefix} ⚠️ Cycle error: {e}"); traceback.print_exc()
    finally:
        fin = fmt_ist()
        _state(phase="idle",next_cycle_at_ist=fmt_ist(_next_cycle()),
               last_cycle_finished_at=fin)
        print(f"\n{prefix} Done {fin} — next: {fmt_ist(_next_cycle())}\n")


# ─── Daily ────────────────────────────────────────────────────────────────────
def run_daily():
    print(f"\n{'='*60}\n[DAILY] {fmt_ist()}\n{'='*60}\n")
    _state(phase="daily_summary")
    try:
        from dailySummary import run_daily_summary; run_daily_summary()
        _state(last_daily_run_ist=fmt_ist()); print("[DAILY] ✓ Complete")
    except Exception as e:
        print(f"[DAILY] Error: {e}"); traceback.print_exc()
    finally: _state(phase="idle")


# ─── Boot ─────────────────────────────────────────────────────────────────────
def _boot():
    time.sleep(90); now=now_ist()
    for h,m,_ in CYCLE_SLOTS:
        s=now.replace(hour=h,minute=m,second=0,microsecond=0)
        if abs((s-now).total_seconds())<600:
            print("[SCHED] Boot skipped — slot imminent"); return
    ds=now.replace(hour=_DAILY_HOUR,minute=0,second=0,microsecond=0)
    if abs((ds-now).total_seconds())<600:
        print("[SCHED] Boot skipped — daily imminent"); return
    run_cycle("Boot", boot_cycle=True)


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print(f"\n[SCHED] ====== JARVIS Scheduler ======\n[SCHED] {fmt_ist()}")

    try:
        from bot_listener import start_listener; start_listener()
    except Exception as e:
        print(f"[SCHED] Bot failed: {e}"); traceback.print_exc()

    _state(phase="idle",current_cycle_number=0,current_cycle_slot=None,
           next_cycle_at_ist=fmt_ist(_next_cycle()),
           last_cycle_started_at="",last_cycle_finished_at="")

    threading.Thread(target=_keep_alive, daemon=True).start()
    threading.Thread(target=_boot, daemon=True).start()

    print(f"[SCHED] Slots: {[s[2] for s in CYCLE_SLOTS]}")
    print(f"[SCHED] Daily: {_DAILY_HOUR:02d}:00 IST  |  Window: {_SLOT_WINDOW_MINS}min")
    print(f"[SCHED] Next cycle: {fmt_ist(_next_cycle())}\n")

    ran: set[str] = set()
    while True:
        try:
            now=now_ist(); ds=now.strftime("%Y-%m-%d"); h,m=now.hour,now.minute

            dk = f"{ds}-daily"
            if h==_DAILY_HOUR and 0<=m<_SLOT_WINDOW_MINS and dk not in ran:
                ran.add(dk); threading.Thread(target=run_daily,daemon=False).start()

            for sh,sm,sl in CYCLE_SLOTS:
                sk=f"{ds}-{sh:02d}"
                if h==sh and 0<=m<_SLOT_WINDOW_MINS and sk not in ran:
                    ran.add(sk)
                    threading.Thread(target=run_cycle,args=(sl,),kwargs={"boot_cycle":False},daemon=False).start()
                    break

            yd=(now-timedelta(days=1)).strftime("%Y-%m-%d")
            ran={k for k in ran if k.startswith(ds) or k.startswith(yd)}
        except Exception as e: print(f"[SCHED] Loop error: {e}")
        time.sleep(30)


if __name__ == "__main__":
    main()
