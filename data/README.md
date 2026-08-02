# Data Directory

## Purpose
Root directory for runtime-generated operational data, raw scraped articles, processed threat intelligence JSON files, daily digests, historical archives, deduplication cache, event logs, and SQLite database storage.

## Contained Subdirectories
- `raw/`: Raw scraped HTML and RSS feed payloads (`/data/raw_articles`).
- `processed/`: Formatted Threat Intelligence JSON files (`/data/processed`).
- `reports/` / `daily/`: Generated executive digests (`/data/daily`).
- `archive/`: Historical report archives older than 3 days (`/data/archive`).
- `cache/`: Deduplication fingerprint cache (`seen.json`).
- `logs/`: Runtime event logs (`/data/logs`).
- `database/`: SQLite control plane database file (`jarvis.db`).

## Dependencies
- Managed dynamically by `backend.storage.persistence` and `backend.database.jarvis_db`.
