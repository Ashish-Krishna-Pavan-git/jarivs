# Database Schema & Persistence

JARVIS uses SQLite for its control plane database and a structured file directory for high-volume content storage.

## Database Location & Connection

- **Environment Variable**: `JARVIS_DB_PATH`
- **Default Path**: `/tmp/jarvis/data/jarvis.db` (Local) or `/data/jarvis.db` (Docker)
- **Engine**: SQLite 3 with Write-Ahead Logging (`PRAGMA journal_mode=WAL`) and foreign keys enforced (`PRAGMA foreign_keys=ON`).
- **Schema Management**: Managed via transactional migrations tracked in `schema_migrations` and `PRAGMA user_version` (Current Version: 4).

## Schema Tables

### `users`
User account definitions and credentials.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `username` (TEXT UNIQUE NOT NULL)
- `password_hash` (TEXT NOT NULL) — PBKDF2/SHA256 hash
- `role` (TEXT NOT NULL DEFAULT 'admin') — 'admin' or 'user'
- `display_name` (TEXT NOT NULL DEFAULT '')
- `must_change_password` (INTEGER NOT NULL DEFAULT 0)
- `active` (INTEGER NOT NULL DEFAULT 1)
- `created_at` (TEXT NOT NULL)

### `sources`
Curated RSS feed sources.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `name` (TEXT NOT NULL)
- `url` (TEXT UNIQUE NOT NULL)
- `category` (TEXT NOT NULL DEFAULT 'tech') — 'cybersec', 'ai', 'tech', 'mobile', 'hardware', 'newsletter', 'business'
- `enabled` (INTEGER NOT NULL DEFAULT 1)
- `created_at` (TEXT NOT NULL)
- `updated_at` (TEXT NOT NULL)

### `model_providers`
AI model provider configurations.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `name` (TEXT UNIQUE NOT NULL)
- `provider_type` (TEXT NOT NULL) — 'gemini', 'groq', 'ollama', 'openai_compatible', 'custom'
- `model` (TEXT NOT NULL)
- `base_url` (TEXT NOT NULL DEFAULT '')
- `api_key_env` (TEXT NOT NULL DEFAULT '')
- `enabled` (INTEGER NOT NULL DEFAULT 1)
- `min_interval` (REAL NOT NULL DEFAULT 0) — rate slot minimum delay in seconds
- `blocked_until` (TEXT) — dynamic rate-limit block timestamp
- `created_at` (TEXT NOT NULL)
- `updated_at` (TEXT NOT NULL)

### `model_routes`
Maps task tiers to prioritized model providers.
- `task` (TEXT NOT NULL) — 'article', 'digest', 'premium', 'text'
- `provider_name` (TEXT NOT NULL)
- `priority` (INTEGER NOT NULL)
- `enabled` (INTEGER NOT NULL DEFAULT 1)
- `PRIMARY KEY (task, provider_name)`

### `notification_channels`
Encrypted user/admin notification channels (Telegram & Slack).
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `user_id` (INTEGER REFERENCES users(id) ON DELETE SET NULL)
- `kind` (TEXT NOT NULL) — 'telegram' or 'slack'
- `label` (TEXT NOT NULL DEFAULT '')
- `target` (TEXT NOT NULL DEFAULT '')
- `secret_json` (TEXT NOT NULL DEFAULT '{}') — Fernet encrypted JSON storing sensitive tokens/webhooks
- `enabled` (INTEGER NOT NULL DEFAULT 1)
- `verified_at` (TEXT)
- `created_at` (TEXT NOT NULL)
- `updated_at` (TEXT NOT NULL)

### `mcp_servers`
Model Context Protocol server definitions.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `name` (TEXT UNIQUE NOT NULL)
- `transport` (TEXT NOT NULL DEFAULT 'http') — 'http' or 'stdio'
- `endpoint` (TEXT NOT NULL DEFAULT '')
- `enabled` (INTEGER NOT NULL DEFAULT 1)
- `config_json` (TEXT NOT NULL DEFAULT '{}')
- `created_at` (TEXT NOT NULL)
- `updated_at` (TEXT NOT NULL)

### `event_logs`
System activity and error audit trail.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `level` (TEXT NOT NULL) — 'INFO', 'WARN', 'ERROR'
- `component` (TEXT NOT NULL)
- `message` (TEXT NOT NULL)
- `details_json` (TEXT NOT NULL DEFAULT '{}')
- `created_at` (TEXT NOT NULL)

### `app_settings`
Key-value store for application runtime settings (e.g. `pipeline:paused`).
- `key` (TEXT PRIMARY KEY)
- `value` (TEXT NOT NULL)
- `updated_at` (TEXT NOT NULL)

### `schema_migrations`
Tracks applied database migrations.
- `version` (INTEGER PRIMARY KEY)
- `name` (TEXT NOT NULL)
- `applied_at` (TEXT NOT NULL)

---

## File System Persistence Directory Layout

Docker persistent data is stored under `JARVIS_DATA_DIR` (default `/data`):

```text
/data/
├── jarvis.db        # Control plane SQLite database
├── processed/       # Processed intelligence JSON files (per-article)
├── raw_articles/    # Scraped raw HTML/RSS content JSON files
├── daily/           # Executive daily and cycle digest JSON reports
├── archive/         # Archived historical digests (>3 days)
├── audio/           # Generated daily podcast MP3 files
└── seen.json        # Deduplication fingerprint cache file
```
