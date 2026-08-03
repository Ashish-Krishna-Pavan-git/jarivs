# JARVIS System Status & Handoff Document

**Last Updated**: 2026-08-02
**System Status**: Production-Ready / Hugging Face Spaces Verified
**Test Pass Rate**: 100% (8/8 backend test cases passing)
**Frontend Build**: 0 Errors / 0 Warnings (Vite 6.4.3 production bundle)
**Authentication & CSRF**: First Login Password Change Verified / Cross-Site Iframe Cookie & JWT Claim Supported
**Telegram & Slack Delivery**: Operational / Non-Blocking Startup Architecture / Decoupled Dual-Channel / Critical Alerts & Reports Verified

---

## 1. Executive Summary
JARVIS is a fully functional, containerized, multi-channel intelligence aggregation system. It collects articles from multiple RSS and web sources, evaluates them using local and cloud-based AI providers (Gemini, Groq, Ollama), persists data using JSON and Hugging Face Datasets, and delivers notifications via Telegram and Slack.

**Latest Milestone (2026-08-03):**
- ✅ **Migrated to Slack Upload V2**: Replaced deprecated `files.upload` endpoint with Slack's modern 3-step upload API (`files.getUploadURLExternal` -> POST binary `upload_url` -> `files.completeUploadExternal`). Resolves `Slack API error: method_deprecated` while preserving retries, timing metrics, and channel delivery.
- ✅ **Fixed "Slack is not defined"**: Added missing `Slack` icon import from `lucide-react` in `Testing.jsx` and added graceful component rendering when Slack is disabled.
- ✅ **Live Configuration Reload**: Implemented `reload_config()` in `config.py`, registered `POST /api/admin/config/reload`, and updated the "Reload Configuration" button in `Testing.jsx` to update in-memory settings (`NOTIFICATION_PROVIDER`, `IS_SLACK_ENABLED`, `IS_TELEGRAM_ENABLED`, tokens, timeouts) at runtime without requiring a full application redeploy.
- ✅ **True Factory Reset & HF Storage Sync**: Enhanced `/api/admin/factory-reset` to wipe all runtime data (`raw_articles/`, `processed/`, `daily/`, `archive/`, `data/audio/`, `data/images/`, `data/podcasts/`, `data/drafts/`, `seen.json`, `digest_state.json`, `telemetry.json`, `runtime_state.json`, `wordpress_posts.jsonl`, in-memory queue, dedupe cache, `event_logs`) and sync clean state to Hugging Face Datasets. Displays `Processed=0, Scraped=0, Cycles=0, Queue=0, Reports=0, Audio=0, Phase=Idle, Last Cycle=Never` while preserving users, sources, models, and channels.
- ✅ **Complete Telegram Isolation**: Gated all low-level HTTP clients (`telegram_post`/`telegram_get`), listener threads, polling loops, audio senders, and internet checks behind `IS_TELEGRAM_ENABLED`. Verified zero executable network requests to `api.telegram.org` when Telegram is disabled.
- ✅ **Slack Audio Support**: Added `send_slack_audio()` with file upload support via Slack Bot Token (`SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`) and graceful fallback for Webhook-only deployments. Integrated `Test Slack Audio` button in Admin UI.
- ✅ **WordPress REST API Diagnostic System**: Added `POST /api/admin/wordpress/test` performing step-by-step authentication (`/users/me`), capability evaluation, temporary draft creation, and automatic draft deletion without modifying production posts or logging credentials.
- ✅ **Admin → Factory Reset Feature**: Implemented `POST /api/admin/factory-reset` and Admin UI buttons on the Dashboard and Maintenance pages. Resets telemetry to zero, clears queue, seen history, digest state, reports, and logs while preserving user accounts, passwords, settings, sources, models, and channels. Restarts the scheduler subprocess and automatically refreshes the dashboard.
- ✅ **Decoupled Provider-Agnostic Notification Architecture**: Made Slack the primary notification provider for Hugging Face deployments and made Telegram fully optional via `NOTIFICATION_PROVIDER=slack|telegram|both|none`.
- ✅ **Complete Telegram Isolation**: When Telegram is disabled, no polling loops, webhooks, or background threads are initialized. Startup cleanly outputs `[CLOUD] Notification Provider: Slack` and `[TELEGRAM] Disabled by configuration`.
- ✅ **Admin UI Integration**: Added dynamic Provider Selector dropdown in `Channels.jsx` and backend API endpoints `GET/POST /api/admin/notification-provider`.
- ✅ Decoupled Telegram and Slack Notification Engine (Robust multi-channel delivery)
- ✅ Implemented low-level non-blocking network diagnostics (`tools/network_diagnostics.py`)
- ✅ **Redesigned Telegram Startup Architecture**: Completely eradicated automatic webhook setup hooks from the application boot sequence to prevent 409 Webhook Conflicts and IPv6 DNS timeouts on Hugging Face Spaces. Introduced explicit polling/webhook modes and an admin API (`/api/admin/telegram/setup`) for manual configuration.
- ✅ Fixed startup `ImportError` related to `HF_SPACE_URL` in the Telegram notification module.
- ✅ **Refactored Telegram Network Policies**: Separated `connect_timeout` and `read_timeout` to fix `ReadTimeout(3.0)` on TLS handshakes in cloud edge proxies. Prevented duplicate alert notifications by catching `ReadTimeout` exceptions dynamically and halting the internal retry loop.

---

## Component Status Matrix

| Subsystem | Status | Details | Primary Responsible Files |
|---|---|---|---|
| **Control Plane API** | ✅ Operational | REST endpoints with JWT cookies, CSRF protection, PBKDF2 password hashing, and role authorization. | [`backend/app.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/app.py) |
| **Frontend UI** | ✅ Operational | React 18 / Vite single-page dashboard with zero-reload mode switching and instant hash routing. | [`frontend/src/App.jsx`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/frontend/src/App.jsx) |
| **Command Center** | ✅ Operational | Live diagnostics, component test runners, pipeline pause/resume, and one-click maintenance data cleanup. | [`frontend/src/pages/admin/Testing.jsx`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/frontend/src/pages/admin/Testing.jsx) |
| **Database & Migrations** | ✅ Operational | Transactional SQLite schema migrations (v1 to v4) with foreign keys and WAL mode. | [`backend/database/jarvis_db.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/database/jarvis_db.py) |
| **Collector & Scraper** | ✅ Operational | RSS parser with URL scheme validation, HTML body scraper, and source configuration controls. | [`backend/collectors/collector.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/collectors/collector.py) |
| **Deduplication & Queue** | ✅ Operational | Single-load memory cache per cycle (MD5 title+link fingerprint) + in-memory queue. | [`backend/storage/dedupe.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/storage/dedupe.py) |
| **AI Router** | ✅ Operational | Multi-tier LLM routing (Gemini 2.5 Pro/Flash → Groq Llama3 8b/70b → Ollama → Custom OpenAI) with rate slot locks and dynamic fallbacks. | [`backend/ai/ai_router.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/ai/ai_router.py) |
| **Scheduler** | ✅ Operational | IST-aligned background schedule: 07:00 Daily Summary, 08:00/15:00/21:00 intelligence cycles + keep-alive thread. | [`backend/scheduler/scheduler.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/scheduler/scheduler.py) |
| **Notifications** | ✅ Operational | Telegram bot broadcaster & Slack webhook integration with message splitting, SSL retry backoffs, and inline testing. | [`backend/notifications/notifier.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/notifications/notifier.py) |
| **Report Generation** | ✅ Operational | Automated cycle digests and daily executive summaries with Markdown & JSON exports, degraded mode fallback. | [`backend/reports/daily_summary.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/reports/daily_summary.py) |
| **WordPress Publishing** | ✅ Operational | Daily report published to WordPress via REST API + Application Passwords. Duplicate-safe, retries, audit log. | [`backend/reports/newsletter_publisher.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/reports/newsletter_publisher.py) |

---

## Documentation Index

All documentation is under `docs/`. See [`docs/README.md`](docs/README.md) for the full categorized sitemap.

**Key documents:**

| Document | Purpose |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | System design, pipeline flow, component interactions |
| [API Reference](docs/API.md) | REST endpoint reference |
| [WordPress Integration](docs/wordpress.md) | Publishing daily reports to WordPress |
| [Reports](docs/reports.md) | Cycle digests, daily summaries, file layout |
| [Local Development](docs/local-development.md) | Setup, hot reload, testing, troubleshooting |
| [Configuration](docs/configuration.md) | All environment variables |
| [Integrations](docs/INTEGRATIONS.md) | Telegram, Slack, WordPress, Ollama, MCP |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common errors and fixes |

---

## Handoff Directives for Future Developers

### Environment Variables

- Declare each key **once** in `.env`. `python-dotenv` resolves duplicates using the **last** declaration.
- The three WordPress env vars (`WP_URL`, `WP_USER`, `WP_APP_PASSWORD`) must all be set for publishing to activate. Missing any one silently skips the publish step.
- Always commit `.env.example` — never `.env`.

### Database Migrations

- Schema versioning uses `PRAGMA user_version` + `schema_migrations` table.
- Add new migrations in `backend/database/jarvis_db.py` under the version sequence (current: v4).
- **Never** modify `_bootstrap_tables` for migrations — that function runs only on fresh installs.

### Frontend Builds

- After any JSX/CSS change: `cd frontend && npm run build`
- The backend serves static files from `frontend/dist/`. The dist bundle must be rebuilt before production use.
- For active frontend development: `npm run dev` (starts Vite dev server on port 5173 with proxy to backend at 7860).

### WordPress Publisher

- `publish_to_wordpress(ai_summary, all_items)` returns a result dict — **always check `result["success"]`** in callers.
- The audit log at `$JARVIS_DATA_DIR/wordpress_posts.jsonl` contains one JSON line per attempt.
- `save_and_publish_newsletter()` is a backward-compatible alias — use `publish_to_wordpress()` in new code.

### Root-Level Shims

- Root `.py` files (e.g. `jarvis_db.py`, `config.py`, `scheduler.py`) are tiny shims — they delegate to `backend/` subpackages.
- Do **not** add new logic to root shims. Add logic to the appropriate `backend/` subpackage, then update the shim if needed.
- The `core/` package is a secondary compat layer — also delegates to `backend/`. No real logic lives there either.

### Maintenance Cleanup

- Use **Clear All Test Data** in `Admin → Testing` (or `POST /api/admin/testing/clear` with `{"target": "clear_all_test_data"}`) to reset test artifacts while preserving configuration, users, sources, and model providers.

---

## Known Limitations / Future Work

| Item | Priority | Notes |
|---|---|---|
| `backend/api/` stub | Low | Currently empty — Flask routes all live in `backend/app.py`. A future refactor could split into Blueprint files. |
| `backend/models/` stub | Low | Placeholder subpackage — no data models defined yet. |
| `docker/` duplicates root | Low | `docker/Dockerfile` and `docker/docker-compose.yml` are copies of root files. Can be removed if `docker/` directory adds no value. |
| Weekly Edition WordPress | Medium | Sunday Doom vs Bloom edition published to WordPress — works but uses same category as daily. Consider separate `WP_WEEKLY_CATEGORY_ID`. |
| Audio on non-HF deployments | Low | `edge-tts` works anywhere, but audio is only useful if Telegram is configured. |
