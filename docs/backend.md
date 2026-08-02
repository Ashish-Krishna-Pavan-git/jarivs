# Backend System Architecture & Modules

The JARVIS backend is organized into modular Python subpackages under `backend/`.

## Modular Architecture

```text
backend/
├── app.py                  # REST API controller & Flask entry point
├── api/                    # API definitions & request wrappers
├── auth/                   # Security, JWT, CSRF, & Fernet encryption (security_utils.py)
├── collectors/             # RSS collectors & HTML text scrapers (collector.py, scraper.py)
├── ai/                     # Multi-tier LLM router & rate locks (ai_router.py)
├── scheduler/              # IST schedule loop & queue manager (scheduler.py, queue_manager.py)
├── notifications/          # Telegram & Slack notification engines (notifier.py, slack_notifier.py)
├── reports/                # Daily summary & newsletter publishers (daily_summary.py)
├── database/               # SQLite migrations & CRUD persistence (jarvis_db.py)
├── storage/                # File persistence & dedupe cache (persistence.py, dedupe.py)
├── archive/                # Historical report archiver (archive_manager.py)
├── services/               # Item workers, audio generator, MCP client (worker_processor.py)
├── config/                 # Environment variables & constants (config.py)
└── utils/                  # Network & system utilities (internet_monitor.py)
```
