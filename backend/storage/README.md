# Backend Storage Module

## Purpose
Handles filesystem JSON persistence for raw articles, processed articles, daily digests, archive reports, deduplication fingerprint cache (`seen.json`), and read-only legacy data mounts.

## Contained Modules
- `persistence.py`: File I/O for processed articles and digests.
- `legacy_data.py`: Read-only bridge for legacy `jarvis-data` directory.
- `dedupe.py`: MD5 fingerprint generation and seen cache management.
- `storage_backend.py`: Hugging Face dataset remote sync.

## Dependencies
- `json`, `os`, `pathlib`, `hashlib`, `huggingface_hub`.

## Entry Points
- `save_processed_articles(items)`: Persists processed items to disk.
- `load_recent_processed_articles(hours)`: Reads recent articles.
- `seen_count()`: Returns dedupe fingerprint count.

## Important Files
- [`persistence.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/storage/persistence.py)
- [`dedupe.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/storage/dedupe.py)
- [`legacy_data.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/storage/legacy_data.py)
