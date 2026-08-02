# Backend Archive Module

## Purpose
Manages historical intelligence report archiving, moving daily digests older than 3 days into `/data/archive`.

## Contained Modules
- `archive_manager.py`: File archiving utility.

## Dependencies
- `shutil`, `os`, `datetime`, `backend.config.config`.

## Entry Points
- `archive_old_reports(days)`: Archives reports older than threshold.

## Important Files
- [`archive_manager.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/archive/archive_manager.py)
