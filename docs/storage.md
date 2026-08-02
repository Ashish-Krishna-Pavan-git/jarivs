# Storage Architecture & Persistence Layout

JARVIS manages data across SQLite control plane tables and dedicated file directories under `/data/`.

## Directory Hierarchy

- `/data/database/`: SQLite `jarvis.db` file.
- `/data/raw/`: Raw scraped HTML and RSS feed payloads (`/data/raw_articles`).
- `/data/processed/`: Formatted Threat Intelligence JSON files (`/data/processed`).
- `/data/reports/`: Executive digests (`/data/daily`).
- `/data/archive/`: Historical report archives older than 3 days (`/data/archive`).
- `/data/cache/`: Deduplication fingerprint cache (`seen.json`).
- `/data/logs/`: System log files (`/data/logs`).
