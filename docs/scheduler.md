# Scheduler & Intelligence Pipeline

JARVIS orchestrates intelligence collection and synthesis using an IST-aligned background schedule ([`scheduler.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/scheduler.py)).

## Schedule Alignment (IST = UTC+5:30)

| Time (IST) | Event | Target Function | Description |
|---|---|---|---|
| **07:00 IST** | Executive Daily Briefing | `run_daily()` | Cross-cycle synthesis, audio podcast generation, newsletter publishing |
| **08:00 IST** | Cycle 1 | `run_cycle("08:00 IST")` | RSS collection, deduplication, worker processing, cycle digest |
| **15:00 IST** | Cycle 2 | `run_cycle("15:00 IST")` | RSS collection, deduplication, worker processing, cycle digest |
| **21:00 IST** | Cycle 3 | `run_cycle("21:00 IST")` | RSS collection, deduplication, worker processing, cycle digest |

---

## Execution Pipeline Flow

1. **Internet Check**: `wait_for_internet()` verifies network reachability before commencing cycle.
2. **State Pull**: `pull_state()` pulls remote Hugging Face state (if configured).
3. **Queue Initialization**: `clear_all()` wipes previous queue state; `reset_cache()` reloads seen fingerprints.
4. **Collection**: `collect_all()` fetches entries from enabled sources in database.
5. **Deduplication**: `get_new_articles()` checks MD5 fingerprints against `seen.json` cache.
6. **Queue Population**: `add_batch(new_items)` enqueues new items for processing.
7. **Worker Processing**: `run_worker()` scrapes full text, executes AI analysis, saves articles to `/data/processed`, and triggers immediate alerts for critical threats.
8. **Digest Generation**: `ai_digest()` synthesizes cycle findings; falls back to degraded mode if AI synthesis is unavailable.
9. **Notification Delivery**: `send_digest()` broadcasts report to Telegram and Slack channels.
10. **State Synchronization**: `push_state()` syncs processed articles to remote storage backend.

---

## Keep-Alive Worker

The background scheduler includes a daemon thread (`_keep_alive()`) that pings `/ping` every 4 minutes. This prevents cloud hosting environments (such as Hugging Face Spaces) from entering idle sleep mode after 48 hours.
