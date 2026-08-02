# JARVIS System Status & Handoff Document

**Last Updated**: 2026-08-02
**System Status**: Production-Ready / Hugging Face Spaces Verified
**Test Pass Rate**: 100% (8/8 backend test cases passing)
**Frontend Build**: 0 Errors / 0 Warnings (Vite 6.4.3 production bundle)
**Authentication & CSRF**: First Login Password Change Verified / Cross-Site Iframe Cookie & JWT Claim Supported
**Telegram Delivery**: Operational / IPv4 Socket Resolution Enforced / Connect (3s) & Read (20s) Timeouts

---

## Executive Overview

JARVIS is a fully functional, self-hosted security intelligence aggregator, LLM-powered threat analyst, and automated report publisher. All components across ingestion, deduplication, worker processing, multi-tier AI routing, reporting, multi-channel notification delivery, storage, WordPress publishing, Hugging Face Docker Space hosting, robust CSRF protection, and administrative control are operational, tested, and documented.

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
