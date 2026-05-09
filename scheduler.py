"""
scheduler.py
Main orchestrator with fixed IST schedule:
  - Daily summary + newsletter: 7:00 AM IST
  - Cycle 1: 8:00 AM IST
  - Cycle 2: 3:00 PM IST
  - Cycle 3: 9:00 PM IST
"""

import json
import os
import threading
import time
from datetime import datetime, timezone, timedelta

import dailySummary
from ai_router import ai_digest
from archive_manager import archive_old_data
from bot_listener import start_listener
from collector import collect_all
from config import DIGEST_STATE_FILE
from dedupe import get_new_articles
from internet_monitor import wait_for_internet
from notifier import send_digest
from queue_manager import (
    add_batch,
    clear_all,
    clear_done,
    reset_stuck,
    stats as queue_stats,
)
from runtime_state import reset_processing_state, update_runtime_state
from storage import save_digest
from storage_backend import is_configured, pull_state, push_state
from telemetry import print_stats, update as tele_update
from worker_processor import run_worker


TEST_MODE_DAILY = False
TEST_MODE_WEEKLY = False

IST = timezone(timedelta(hours=5, minutes=30))
DAILY_SUMMARY_TIME = (7, 0)
CYCLE_SLOTS = [
    ("cycle_1", 8, 0),
    ("cycle_2", 15, 0),
    ("cycle_3", 21, 0),
]

_daily_summary_lock = threading.Lock()
_last_test_daily_run = [0.0]


def _load_state() -> dict:
    if not os.path.exists(DIGEST_STATE_FILE):
        return {
            "cycle_num": 0,
            "last_daily_date": "",
            "last_cycle_at": "",
            "last_cycle_slot": "",
        }
    try:
        with open(DIGEST_STATE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if "last_cycle_slot" not in data:
            data["last_cycle_slot"] = ""
        if not data.get("last_cycle_slot") and data.get("last_cycle_at"):
            inferred = _infer_slot_from_last_cycle_at(data.get("last_cycle_at", ""))
            if inferred:
                data["last_cycle_slot"] = inferred
        return data
    except Exception:
        return {
            "cycle_num": 0,
            "last_daily_date": "",
            "last_cycle_at": "",
            "last_cycle_slot": "",
        }


def _infer_slot_from_last_cycle_at(last_cycle_at: str) -> str:
    try:
        dt_utc = datetime.fromisoformat(last_cycle_at)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        dt_ist = dt_utc.astimezone(IST)
        chosen = None
        for slot_name, hour, minute in CYCLE_SLOTS:
            slot_dt = _slot_datetime(dt_ist.date(), hour, minute)
            if dt_ist >= slot_dt:
                chosen = _slot_id(dt_ist, slot_name)
        return chosen or ""
    except Exception:
        return ""


def _save_state(state: dict):
    with open(DIGEST_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _slot_id(now_ist: datetime, slot_name: str) -> str:
    return f"{now_ist.strftime('%Y-%m-%d')}::{slot_name}"


def _slot_datetime(base_date, hour, minute):
    return datetime(
        year=base_date.year,
        month=base_date.month,
        day=base_date.day,
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
        tzinfo=IST,
    )


def _next_cycle_info(now_ist: datetime | None = None):
    now_ist = now_ist or datetime.now(IST)
    today = now_ist.date()
    candidates = []

    for slot_name, hour, minute in CYCLE_SLOTS:
        slot_dt = _slot_datetime(today, hour, minute)
        candidates.append((slot_name, slot_dt))

    tomorrow = today + timedelta(days=1)
    for slot_name, hour, minute in CYCLE_SLOTS:
        slot_dt = _slot_datetime(tomorrow, hour, minute)
        candidates.append((slot_name, slot_dt))

    for slot_name, slot_dt in candidates:
        if slot_dt > now_ist:
            return slot_name, slot_dt
    return candidates[-1]


def _due_cycle_slot(now_ist: datetime | None = None):
    now_ist = now_ist or datetime.now(IST)
    state = _load_state()
    today = now_ist.date()

    for slot_name, hour, minute in reversed(CYCLE_SLOTS):
        slot_dt = _slot_datetime(today, hour, minute)
        if now_ist >= slot_dt:
            current_slot_id = _slot_id(now_ist, slot_name)
            if state.get("last_cycle_slot") != current_slot_id:
                return slot_name, slot_dt, current_slot_id
            return None
    return None


def _should_run_daily(now_ist: datetime | None = None) -> bool:
    now_ist = now_ist or datetime.now(IST)

    if TEST_MODE_DAILY or TEST_MODE_WEEKLY:
        now = time.time()
        if now - _last_test_daily_run[0] < 1800:
            return False
        print("[SCHEDULER] TEST MODE: Triggering Daily/Weekly Summary")
        _last_test_daily_run[0] = now
        return True

    state = _load_state()
    today_ist = now_ist.strftime("%Y-%m-%d")
    if state.get("last_daily_date") == today_ist:
        return False

    target = _slot_datetime(now_ist.date(), DAILY_SUMMARY_TIME[0], DAILY_SUMMARY_TIME[1])
    return now_ist >= target


def _run_daily_summary_if_due():
    now_ist = datetime.now(IST)
    if not _should_run_daily(now_ist):
        return
    if not _daily_summary_lock.acquire(blocking=False):
        return

    try:
        print("\n[JARVIS] Running 7:00 AM IST daily summary + newsletter pipeline...")
        update_runtime_state(
            phase="daily_summary",
            last_daily_run_ist=now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        )
        dailySummary.FORCE_TEST_WEEKLY = TEST_MODE_WEEKLY
        dailySummary.run_daily_summary()

        if not TEST_MODE_DAILY and not TEST_MODE_WEEKLY:
            state = _load_state()
            state["last_daily_date"] = now_ist.strftime("%Y-%m-%d")
            _save_state(state)
            if is_configured():
                push_state(new_articles=[])
    finally:
        reset_processing_state()
        _daily_summary_lock.release()


def _daily_timer_loop():
    print("[SCHEDULER] Daily timer thread active; checking every 30s for 7:00 AM IST")
    while True:
        try:
            _run_daily_summary_if_due()
        except Exception as e:
            print(f"[SCHEDULER] Daily timer error: {e}")
        time.sleep(30)


def _update_next_cycle_runtime():
    slot_name, slot_dt = _next_cycle_info()
    update_runtime_state(
        next_cycle_at_ist=slot_dt.strftime("%Y-%m-%d %H:%M:%S IST"),
        phase=update_runtime_phase(),
    )
    return slot_name, slot_dt


def update_runtime_phase():
    try:
        from runtime_state import load_runtime_state
        current = load_runtime_state()
        return current.get("phase", "idle")
    except Exception:
        return "idle"


def run_cycle(slot_name: str, slot_dt: datetime, slot_id: str):
    state = _load_state()
    cycle_num = state["cycle_num"] + 1
    now_utc = datetime.now(timezone.utc).isoformat()
    slot_label = slot_name.replace("_", " ").title()

    print(f"\n{'=' * 60}")
    print(f"[SCHEDULER] {slot_label} starting at scheduled IST slot {slot_dt.strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"[SCHEDULER] Global cycle number: {cycle_num} | UTC start: {now_utc}")
    print(f"{'=' * 60}\n")

    update_runtime_state(
        phase="cycle_starting",
        current_cycle_number=cycle_num,
        current_cycle_slot=slot_name,
        current_cycle_date_ist=slot_dt.strftime("%Y-%m-%d"),
        last_cycle_started_at=now_utc,
        queue_total=0,
        queue_done=0,
        queue_failed=0,
        current_item_title="",
    )

    tele_update("cycle_start")
    wait_for_internet()

    clear_all()
    reset_stuck()
    from dedupe import reset_cache

    reset_cache()

    update_runtime_state(phase="collecting")
    print("[CYCLE] Collecting RSS sources...")
    raw_articles = collect_all()
    print(f"[CYCLE] Collected: {len(raw_articles)} total")

    update_runtime_state(phase="deduplicating")
    new_articles = get_new_articles(raw_articles)
    print(f"[CYCLE] New after dedup: {len(new_articles)}")

    if not new_articles:
        print("[CYCLE] No new articles in this slot")
        state["cycle_num"] = cycle_num
        state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
        state["last_cycle_slot"] = slot_id
        _save_state(state)
        update_runtime_state(
            phase="idle",
            last_cycle_finished_at=state["last_cycle_at"],
            queue_total=0,
            queue_done=0,
            queue_failed=0,
        )
        if is_configured():
            push_state(new_articles=[])
        return

    update_runtime_state(phase="queueing", queue_total=len(new_articles), queue_done=0, queue_failed=0)
    add_batch(new_articles)
    print(f"[CYCLE] Queue stats: {queue_stats()}")

    update_runtime_state(phase="processing")
    processed_items, failed_items = run_worker()

    digest_data = None
    if processed_items:
        update_runtime_state(phase="digest_generation")
        print(f"[CYCLE] Generating AI 8-hour summary for {slot_name}...")
        digest_data = ai_digest(processed_items, f"{slot_label} ({slot_dt.strftime('%d %b %Y')})")
        if digest_data:
            save_digest(digest_data, cycle_num)
            print("[CYCLE] Digest saved")
        else:
            print("[CYCLE] AI digest failed; continuing with raw digest send")

    update_runtime_state(phase="telegram_digest")
    send_digest(processed_items, cycle_num, digest_data)

    clear_done()
    archive_old_data(days=3)
    print_stats()

    state["cycle_num"] = cycle_num
    state["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
    state["last_cycle_slot"] = slot_id
    _save_state(state)

    update_runtime_state(
        phase="syncing",
        last_cycle_finished_at=state["last_cycle_at"],
        queue_total=len(processed_items) + len(failed_items),
        queue_done=len(processed_items),
        queue_failed=len(failed_items),
    )

    if is_configured():
        print("[CYCLE] Syncing state to HF Dataset...")
        push_state(new_articles=processed_items)
    else:
        print("[CYCLE] HF persistence not configured")

    print(f"\n[CYCLE] {slot_name} complete: processed={len(processed_items)} failed={len(failed_items)}")
    next_slot_name, next_slot_dt = _next_cycle_info()
    print(f"[SCHEDULER] Next cycle scheduled: {next_slot_name} at {next_slot_dt.strftime('%Y-%m-%d %H:%M:%S IST')}")
    update_runtime_state(
        phase="idle",
        next_cycle_at_ist=next_slot_dt.strftime("%Y-%m-%d %H:%M:%S IST"),
        current_item_title="",
    )


def start_scheduler():
    print("\n" + "=" * 60)
    print(" JARVIS Intelligence System — Fixed IST Schedule")
    print(" Daily summary/newsletter : 07:00 AM IST")
    print(" Cycle 1                 : 08:00 AM IST")
    print(" Cycle 2                 : 03:00 PM IST")
    print(" Cycle 3                 : 09:00 PM IST")
    print(f" HF Persistence          : {'Enabled' if is_configured() else 'Disabled'}")
    print("=" * 60 + "\n")

    if is_configured():
        print("[JARVIS] Restoring state from HF Dataset...")
        pull_state()

    reset_processing_state()
    _, next_slot_dt = _next_cycle_info()
    update_runtime_state(next_cycle_at_ist=next_slot_dt.strftime("%Y-%m-%d %H:%M:%S IST"))

    start_listener()
    threading.Thread(target=_daily_timer_loop, daemon=True).start()

    while True:
        try:
            due = _due_cycle_slot()
            if due:
                slot_name, slot_dt, slot_id = due
                run_cycle(slot_name, slot_dt, slot_id)
            else:
                next_slot_name, next_slot_dt = _next_cycle_info()
                update_runtime_state(next_cycle_at_ist=next_slot_dt.strftime("%Y-%m-%d %H:%M:%S IST"))
                now_ist = datetime.now(IST)
                seconds = max(15, int((next_slot_dt - now_ist).total_seconds()))
                minutes = seconds // 60
                print(f"[SCHEDULER] Idle. Next cycle: {next_slot_name} at {next_slot_dt.strftime('%Y-%m-%d %H:%M:%S IST')} ({minutes}m away)")
                time.sleep(min(300, seconds))

        except KeyboardInterrupt:
            print("\n[JARVIS] Stopped by user.")
            break
        except Exception as e:
            print(f"\n[JARVIS] Scheduler error: {e}")
            import traceback

            traceback.print_exc()
            time.sleep(30)


if __name__ == "__main__":
    start_scheduler()
