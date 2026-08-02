# Backend Scheduler Module

## Purpose
Background thread scheduler, IST cycle execution (08:00, 15:00, 21:00 IST), daily summary trigger (07:00 IST), in-memory queue management, and keep-alive ping worker.

## Contained Modules
- `scheduler.py`: Main thread loop and cycle orchestrator.
- `queue_manager.py`: Ephemeral thread-safe article processing queue.

## Dependencies
- `threading`, `time`, `backend.collectors.collector`, `backend.services.worker_processor`.

## Entry Points
- `start_scheduler()`: Launches background scheduling thread.
- `run_cycle(slot_name)`: Triggers single collection cycle.

## Important Files
- [`scheduler.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/scheduler/scheduler.py)
- [`queue_manager.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/scheduler/queue_manager.py)
