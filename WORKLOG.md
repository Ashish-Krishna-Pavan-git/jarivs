# JARVIS Worklog

## 2026-08-03 - Telegram Network Timeout Policies and Duplicate Fixes

Primary Issue Resolved: 
Telegram requests on Hugging Face Spaces were intermittently throwing `requests.exceptions.ReadTimeout (read timeout=3.0)`. This occurred because the `(3.0, 20.0)` tuple was occasionally mapping badly in requests, or 3.0s connect timeout was too aggressive for TLS handshakes through cloud edge proxies. Furthermore, when `ReadTimeout` did occur on `sendMessage`, the retries were causing duplicate notifications to be sent because Telegram actually processed the message despite the delay.

Key Changes:
1. **Separated Timeout Policies**: Refactored `telegram_client.py` to explicitly require `connect_timeout` (default 10.0s) and `read_timeout` (default 30.0s) separately, instead of relying on a shared timeout tuple. 
2. **Detailed Exception Logging**: Upgraded the exception handlers to log the exact `connect_timeout` and `read_timeout` alongside the `elapsed` time.
3. **No-Duplicate Retry Logic**: Added a `retry_on_read_timeout` boolean flag to `telegram_post()` (default `False`). If a `requests.exceptions.ReadTimeout` is raised (meaning the TCP connection succeeded and the request was sent, but the response was delayed), the client intentionally breaks the retry loop to avoid sending duplicate alerts to users.
4. **Targeted Method Limits**:
   - `sendMessage`: connect=10.0s, read=30.0s, no retry on read timeout.
   - `getUpdates` (Polling): connect=10.0s, read=35.0s (to safely exceed Telegram's 15s long-poll).
   - Setup Webhook / Admin APIs: connect=10.0s, read=20.0s.
5. **Diagnostic Endpoint**: Created `GET /api/admin/telegram/timeouts` that dynamically reflects the signature defaults and active policies for debugging in the cloud.

Verification: All components initialized successfully and tests passed without regressions. Telegram polling accurately obeys the 35s read boundary, and sendMessage avoids duplicate delays.

## 2026-08-02 - Fixed HF_SPACE_URL ImportError in Telegram Module

Primary Issue Resolved: 
After the Telegram startup redesign, the application crashed with an `ImportError` because `HF_SPACE_URL` was removed from `backend.config.config` but was still being imported by `backend.notifications.bot_listener`.

Key Changes:
1. **Removed Broken Import**: Removed `HF_SPACE_URL` from the `backend.config.config` import statement in `bot_listener.py`. 
2. **Global Variable Usage**: `bot_listener.py` already dynamically loads `HF_SPACE_URL = os.getenv("HF_SPACE_URL", "").rstrip("/")` at the module level. The local scope in `start_listener` now implicitly correctly uses the module-level variable without attempting to import it from `config.py`.
3. **Verification**: Executed `python -m compileall backend` and `pytest tests/test_backend_api.py` to ensure no other cyclic or missing imports exist. All tests pass and the application boots successfully in both Webhook and Polling modes.

## 2026-08-02 - Telegram Webhook and Startup Architecture Redesign

Primary Issue Resolved: 
The application was executing bot-management HTTP calls (setWebhook, deleteWebhook, setMyCommands) automatically during startup. Even though non-blocking threads were used, this still resulted in Hugging Face network timeouts (due to IPv6 dead drops) and 409 Webhook Conflict errors when polling and webhooks were mixed.

Key Changes:
1. **Removed Automatic Bot Management**: `register_webhook()`, `delete_webhook()`, and `send_startup_message()` are completely eliminated from the backend initialization sequence.
2. **Added Dedicated Admin Endpoint**: Moved bot setup capabilities to `POST /api/admin/telegram/setup`. Now `setWebhook`, `deleteWebhook`, and `setMyCommands` only execute when manually triggered by an admin.
3. **Decoupled Polling and Webhook Modes**: The configuration variable `TELEGRAM_MODE` (default "polling") strictly dictates behavior. 
   - Polling mode: Starts `_poll_loop` immediately. No webhook operations are performed.
   - Webhook mode: Simply waits for incoming requests at `/telegram/<TOKEN>`.
4. **Resilient Polling Loop**: The `_poll_loop` no longer tries to automatically delete an existing webhook if it encounters a 409 Conflict. Instead, it waits and prints instructions to use the admin API, avoiding race conditions and unexpected deletions.
5. **Robust Testing**: Refactored logic to strictly abide by `@require_admin` (fixing a missing `@require_auth` reference) and validated against the backend test suite (8/8 tests passing).

This architecture is completely production-safe. Startup never depends on Telegram availability. If Telegram APIs are completely offline, JARVIS still boots instantly.

---

## 2026-08-02 - Non-Blocking Telegram Startup & Hugging Face Webhook Resolution

Root Cause of HF Spaces Telegram Startup Hang & Failures:
1. **Synchronous Pre-Startup Webhook Network Calls**: `register_webhook()` and `delete_webhook()` were called synchronously inside `main()` in `backend/app.py` BEFORE Flask bound port 7860 (`app.run()`).
2. **Hugging Face Container Startup Race Condition**: Calling Telegram's `setWebhook` API with `https://akp-07-jarvis-agent.hf.space/telegram/<TOKEN>` caused Telegram's servers to attempt an HTTP validation probe to `https://akp-07-jarvis-agent.hf.space`. Because Flask was not yet listening on port 7860 and Hugging Face edge proxies drop incoming webhooks until containers pass health checks, `setWebhook` hung for 25+ seconds, timed out, and triggered synchronous `delete_webhook()` calls.
3. **Startup Blocking & 409 Conflict Loops**: The synchronous network calls blocked application container initialization for 37+ seconds, and caused `409 Conflict` errors when `getUpdates` long-polling started while a webhook registration attempt was pending on Telegram servers.

Files Created / Changed:
- `backend/app.py` — Made Telegram initialization completely non-blocking:
  - `main()` launches Flask (`app.run(host="0.0.0.0", port=7860)`) immediately so HF health checks pass without delay.
  - Webhook registration (`register_webhook()`), fallback deletion (`delete_webhook()`), and startup messages run asynchronously in a daemon thread after Flask binds port 7860.
- `backend/notifications/bot_listener.py` — Made `start_listener()` non-blocking:
  - Removed synchronous `_delete_webhook()` call from `start_listener()`. Polling starts immediately in a daemon thread and self-heals asynchronously if 409 Conflict occurs.

Verification Performed:
- **Direct API Timings**: `getMe` (0.70s), `sendMessage` (0.42s), `deleteWebhook` (0.26s).
- **Notifier Pipeline**: `notify_immediate` (True), `send_digest` (True).
- **Backend Test Suite**: `pytest tests/test_backend_api.py` (8/8 test cases passing, 100% pass rate).

Status: Non-Blocking Non-Hanging Telegram Architecture Verified.

---

Root Cause of Notification Non-Delivery for Critical Alerts & Cycle Reports:
1. **Strict Keyword Filtering in Alert Processor**: `is_dead_serious()` in `worker_processor.py` required `confidence >= 7` or `confidence >= 8` AND explicit string matching for zero-day keywords. When `is_dead_serious()` returned `False`, articles classified as `CRITICAL` or `HIGH` by the AI were logged as `"queued for 8hr digest"` and `notify_immediate()` was never called.
2. **Coupled Channel Execution**: `_send_multichannel()` checked Telegram first and returned `False` if `TELEGRAM_TOKEN` was missing or failed before attempting Slack delivery.
3. **Missing Slack Webhook Field Extraction**: Slack webhook URLs stored in `list_notification_channels()` were skipped if `channel.secret` was empty.
4. **Lack of Delivery Diagnostics**: Notification events were executed in daemon threads without returning delivery booleans or recording diagnostic metrics.

Files Created / Changed:
- `backend/notifications/slack_notifier.py` — Overhauled Slack delivery engine:
  - Supports `SLACK_WEBHOOK_URL` in `.env`, DB integrations, and DB notification channels.
  - Sanitized logging (masks webhook URLs in logs).
  - Connect (3.0s) & Read (15.0s) timeouts with exponential retry logic.
- `backend/notifications/notifier.py` — Decoupled multichannel dispatch:
  - Telegram and Slack run independently; failure of one channel does not prevent the other from delivering.
  - Updated `notify_immediate()`, `send_digest()`, `send_daily_summary()`, `send_weekly_summary()` with detailed event logging.
- `backend/services/worker_processor.py` — Fixed alert trigger logic:
  - Automatically triggers `notify_immediate()` for all `CRITICAL` articles and `HIGH` severity articles with `confidence >= 5` or `is_dead_serious`.
- `backend/database/jarvis_db.py` — Implemented `get_notification_diagnostics()`:
  - Returns Telegram & Slack last success/error timestamps, error messages, and notification counts.
- `backend/app.py` — Added `/api/admin/notification-diagnostics` and `/api/admin/testing/trigger-test-alert`.

Verification Performed:
- **End-to-End Delivery Verification**:
  - `notify_immediate` (Critical Alert): Telegram HTTP 200 (1.43s, msg #2134) & Slack HTTP 200 (0.64s, `ok`).
  - `send_digest` (Cycle Digest): Telegram HTTP 200 (0.45s, msg #2135) & Slack HTTP 200 (0.56s, `ok`).
  - `send_daily_summary` (Daily Brief): Telegram HTTP 200 (0.45s, msg #2136) & Slack HTTP 200 (0.61s, `ok`).
  - `get_notification_diagnostics()`: Tracked success timestamps and metrics for both channels.
- **Backend Test Suite**: `pytest tests/test_backend_api.py` (8/8 test cases passing, 100% pass rate).

Status: Dual Telegram & Slack Pipeline Operational.

---

Root Cause of `HTTPSConnectionPool(host='api.telegram.org', port=443): Read timed out. (read timeout=20)`:
1. **IPv6 Socket Hanging on Cloud/Container Networks**: `api.telegram.org` returns dual-stack IPv6 (`2001:67c:4e8:f004::9`) and IPv4 (`149.154.166.110`) DNS records. Python's `socket.getaddrinfo()` returns IPv6 first. On cloud containers (Hugging Face Spaces / AWS EC2) lacking active outbound IPv6 routing, TCP connection attempts to the IPv6 address hang silently until the HTTP timeout (20-60s) expires, resulting in `Read timed out` or `Connect timed out`.
2. **Scalar Timeout Overhead**: Requests set single scalar timeouts (`timeout=20` or `timeout=60`). When TCP connection attempts hung on IPv6, each attempt blocked the execution thread for up to 60 seconds before failing.
3. **Edge Proxy Throttling**: Default `python-requests` User-Agent header triggered connection drops or rate-limits on cloud edge proxies.

Files Created / Changed:
- `backend/utils/telegram_client.py` (Created) — Centralized Telegram API client:
  - Enforces IPv4 socket resolution (`urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET`).
  - Implements automatic bot token masking (`bot***`) in logs.
  - Uses separate connect (3.0s) and read (20.0s) timeouts with custom User-Agent (`JARVIS-Intelligence-Bot/2.0`).
  - Detailed diagnostic logging (request start/finish, HTTP status, elapsed time in seconds, response snippet, stack trace on failure).
- `backend/notifications/notifier.py` — Refactored `_send_one()`, `test_channel()`, and `send_audio()` to use `telegram_client`.
- `backend/notifications/bot_listener.py` — Refactored `send_reply()`, `_delete_webhook()`, `_poll_loop()`, and `_set_commands()` to use `telegram_client`.
- `backend/app.py` — Refactored `register_webhook()`, `delete_webhook()`, and `send_startup_message()` to use `telegram_client`.
- `backend/utils/internet_monitor.py` — Added IPv4 socket family enforcement.

Verification Performed:
- **Telegram Verification Suite**:
  - `getMe`: Succeeded in 0.63s (`@JarvisAkpBot`).
  - `getUpdates`: Completed in 0.18s.
  - `sendMessage` (direct API): Succeeded in 0.40s.
  - `test_channel` (UI button logic): Succeeded in 0.40s.
  - `_send_one` & `_send` notifier pipeline: Succeeded in 0.39s & 0.43s.
- **Backend Test Suite**: `pytest tests/test_backend_api.py` (8/8 tests passing, 100% pass rate).

Status: Production-Ready & Telegram Delivery Verified.

---

Root Cause of `csrf_failed` on First Login Password Change:
1. **Cross-Site Iframe Cookie Restrictions**: When running embedded inside a Hugging Face Space iframe (`https://huggingface.co/spaces/akp-07/jarvis-agent` embedding `https://akp-07-jarvis-agent.hf.space`), browsers treat `huggingface.co` and `hf.space` as cross-site. Cookies set with `SameSite=Strict` are omitted by browsers on iframe requests, causing `request.cookies.get("csrf_token")` to return empty.
2. **Reverse Proxy Scheme Detection**: Hugging Face's edge proxy terminates SSL and forwards requests over HTTP with `X-Forwarded-Proto: https`. Flask's `request.scheme` evaluates to `"http"`, setting `secure=False`. Browsers reject `SameSite=None` cookies on non-secure responses.
3. **Fetch API Options**: `frontend/src/api.js` omitted `credentials: "include"`, causing `fetch()` to drop cookies on cross-origin requests.

Files Changed:
- `backend/auth/security_utils.py` — Updated `issue_jwt` to accept optional `csrf` parameter and include `"csrf": csrf` in the cryptographically signed JWT payload.
- `backend/app.py` —
  - Implemented `_is_secure_request()` (checks `request.scheme == "https"` and `X-Forwarded-Proto == "https"`).
  - Updated `_login_response()` to pass `csrf` to `issue_jwt()` and set `SameSite=None; Secure` when secure / on HF, `SameSite=Lax` on local HTTP.
  - Updated `require_csrf()` decorator to validate `X-CSRF-Token` header against `request.cookies.get("csrf_token")` OR `g.user.get("csrf")` from verified JWT.
  - Added `POST /api/auth/logout` endpoint clearing `jarvis_token` and `csrf_token` cookies.
- `frontend/src/api.js` — Added `credentials: "include"` to `fetch()` options.

Verification Performed:
- **Frontend Build**: `cd frontend && npm run build` (0 errors, `dist/index.html` and assets built).
- **Comprehensive Auth & CSRF Test Suite**:
  - First login with `must_change_password=True` verified.
  - Protected endpoint access before password change blocked (`password_change_required`, 403).
  - Password change without `X-CSRF-Token` header blocked (`csrf_failed`, 403).
  - Password change WITH `X-CSRF-Token` header & JWT claim succeeded (`must_change_password=False`, 200 OK).
  - Admin endpoint access after password change succeeded (200 OK).
  - Hugging Face HTTPS proxy detection verified (`SameSite=None; Secure` set-cookie headers).
  - Logout endpoint verified (`POST /api/auth/logout` 200 OK).
- **Backend Test Suite**: `pytest tests/test_backend_api.py` (8/8 tests passing, 100% pass rate).

Status: Production-Ready & First-Login Password Change Verified.

---

Root Cause of `akp-07-jarvis-agent.hf.space refused to connect`:
1. **Missing Hugging Face Spaces YAML Frontmatter**: `README.md` lacked `sdk: docker` and `app_port: 7860` metadata header. Without this, Hugging Face's ingress proxy failed to route port 7860 to `*.hf.space`, causing connection refusal.
2. **Browser Iframe Blocking (`X-Frame-Options: DENY`)**: `backend/auth/security_utils.py` enforced `X-Frame-Options: DENY`. Hugging Face embeds Spaces inside an `<iframe>` on `huggingface.co`. Modern browsers block iframe content when `X-Frame-Options: DENY` is returned, resulting in a "refused to connect" browser error.
3. **Incomplete SPA Catch-All Routes**: `backend/app.py` lacked explicit SPA fallback routes for `/login` and deep paths like `/user/*`, leading to 404 errors on deep navigation or direct page reloads.

Files Changed:
- `README.md` — Added Hugging Face Spaces YAML frontmatter (`sdk: docker`, `app_port: 7860`, `title`, `emoji`).
- `backend/auth/security_utils.py` — Replaced `X-Frame-Options: DENY` with `Content-Security-Policy: frame-ancestors 'self' https://huggingface.co https://*.huggingface.co https://*.hf.space;`, updated `Referrer-Policy` to `strict-origin-when-cross-origin`, and updated CORS origin matching to allow Hugging Face domains.
- `backend/app.py` — Added `@app.route("/login")`, `@app.route("/user/<path:_path>")`, `@app.errorhandler(404)` SPA catch-all handler for non-API routes, and `PORT` env var support (`int(os.getenv("PORT", 7860))`).

Verification Performed:
- **Frontend Build**: `cd frontend && npm run build` (0 errors, `dist/index.html` and assets generated).
- **Backend Tests**: `pytest tests/test_backend_api.py` (8/8 tests passing, 100% pass rate).
- **Security Headers & Routing Verification**: End-to-end Python test script verified `/`, `/login`, `/user/*`, `/admin/*`, `/health`, `/ping`, and CSP `frame-ancestors` headers.

Status: Production-Ready & Hugging Face Spaces Ready.

---

Completed:

- **WordPress Publisher (`backend/reports/newsletter_publisher.py`)** — Full rewrite:
  - New public entry point: `publish_to_wordpress(ai_summary, all_items)` (returns structured result dict, never raises)
  - `save_and_publish_newsletter()` kept as backward-compatible alias for `daily_summary.py` callers
  - Retry-aware HTTP requests with exponential back-off (3 attempts, 3s × attempt)
  - Duplicate-safe: queries existing post by slug before creating (updates if found, creates if new)
  - `WP_TAGS` env var support for attaching tag IDs (comma-separated integers)
  - Structured audit log written to `$JARVIS_DATA_DIR/wordpress_posts.jsonl` (slug, timestamp, post_id, post_url, action, error)
  - Full HTML builder with `escalating_threats`, `new_patterns`, `actor_activity`, `critical_cves`, `tech_trends`, `recommendations`, and top-10 source articles by severity
  - Dark-tech CSS (Orbitron + Inter fonts, sky-blue #38bdf8 accent) matching JARVIS aesthetic
  - Graceful credential validation — logs skip message without crashing when WP env vars absent

- **New Documentation Files** (`docs/`):
  - `docs/wordpress.md` — Step-by-step WordPress Application Password setup, environment variables, duplicate prevention, audit log reference, troubleshooting (HTTP 401/403/503, Cloudflare, CSS stripping)
  - `docs/reports.md` — Report types (cycle digests, daily summary, Sunday weekly), dashboard viewing, degraded mode fallback, file layout, scheduler config
  - `docs/local-development.md` — Prerequisites, setup steps, hot-reload frontend dev, testing commands, troubleshooting (port conflicts, database locked, blank page, missing ffmpeg), VS Code workspace tips

- **Updated Documentation**:
  - `docs/INTEGRATIONS.md` — Expanded from 20 lines to full guide covering Telegram, Slack, WordPress, HuggingFace, Ollama, and MCP
  - `docs/README.md` — Updated sitemap with new guides properly categorized (Getting Started, User, Admin, Integration, Technical, Development)
  - Root `README.md` — Rewritten as comprehensive GitHub-ready README: Quick Start (Docker + local), feature table, directory structure, all environment variables, WordPress setup summary, full docs index

- **Repository Cleanup**:
  - Removed `runtime_state.json` and `telemetry.json` from git tracking (both gitignored but were committed — contains live runtime data)
  - Improved `.gitignore` with organized sections, added: `seen.json`, `queue.json`, `digest_state.json`, `wordpress_posts.jsonl`, `venv/`, `*.egg-info/`, `frontend/npm/`

- **Verification**: All 8/8 pytest tests pass (100% pass rate)

---

## 2026-08-02 - Repository Reorganization & Enterprise Folder Structure

Completed:

- **Reorganized Repository into Professional Subpackages (`backend/`, `scripts/`, `docker/`, `data/`, `config/`, `tools/`)**:
  - Moved scattered root python modules into specialized backend subpackages:
    - `backend/config/config.py`: Central configuration and environment loader.
    - `backend/database/jarvis_db.py`: SQLite database control plane and transactional schema migrations.
    - `backend/auth/security_utils.py`: JWT, CSRF, Fernet encryption, and password hashing.
    - `backend/collectors/collector.py` & `scraper.py`: RSS collectors and HTML text scrapers.
    - `backend/ai/ai_router.py`: Multi-tier LLM router, rate slot locks, and provider fallbacks.
    - `backend/scheduler/scheduler.py` & `queue_manager.py`: IST cycle scheduler and in-memory queue manager.
    - `backend/notifications/notifier.py`, `slack_notifier.py`, `bot_listener.py`: Telegram & Slack delivery engines.
    - `backend/reports/daily_summary.py` & `newsletter_publisher.py`: Executive summary and newsletter generators.
    - `backend/storage/persistence.py`, `dedupe.py`, `legacy_data.py`, `storage_backend.py`: Storage persistence, dedupe fingerprints, and legacy data bridge.
    - `backend/services/worker_processor.py`, `audio_generator.py`, `mcp_client.py`, `runtime_state.py`, `subscriber_store.py`, `telemetry.py`, `intelligence.py`: Core background services.
    - `backend/archive/archive_manager.py`: Report archiver.
    - `backend/utils/internet_monitor.py`: Network reachability monitor.
  - Created root-level python shims with dynamic `__getattr__` delegation to maintain 100% backward compatibility for all external callers, scripts, and processes.
  - Created `scripts/start_backend.py` and `tools/health_check.py` diagnostic utilities.
  - Created `docker/Dockerfile` and `docker/docker-compose.yml`.

- **Added Folder README Files**:
  - Created folder `README.md` files for every major directory (`backend/api`, `backend/auth`, `backend/collectors`, `backend/ai`, `backend/scheduler`, `backend/notifications`, `backend/reports`, `backend/database`, `backend/storage`, `backend/archive`, `backend/services`, `backend/utils`, `backend/config`, `backend/models`, `scripts`, `docker`, `data`, `config`, `tests`, `tools`).

- **Created & Updated Comprehensive Documentation Suite (`docs/`)**:
  - Added `docs/backend.md`, `docs/frontend.md`, `docs/docker.md`, `docs/storage.md`, `docs/folder-structure.md`, `docs/developer-guide.md`, `docs/contributing.md`, and updated `docs/README.md` sitemap.

- **Verification**:
  - `tools/health_check.py` executed successfully.
  - `npm run build` in `frontend/` succeeded with 0 errors and 0 warnings.
  - `python -m pytest -v` executed with 8/8 backend test cases passing (`100%` pass rate).

## 2026-08-02 - Documentation Suite, Single Clear-All Maintenance Action, and Project Handoff

Completed:

- **Enhanced Command Center Clear-All Maintenance Action (`backend/app.py` & `Testing.jsx`)**:
  - Implemented `clear_all_test_data` target in `testing_clear()` API endpoint.
  - Deletes all non-production test data artifacts: daily & archive reports (`/data/daily`, `/data/archive`), event logs and alert history (`event_logs` table), in-memory queue entries, scraped/processed/raw article JSON files (`/data/processed`, `/data/raw_articles`), dedupe cache (`seen.json`), and audio files (`/data/audio`).
  - Preserves working configurations, database schema migrations, user accounts, source feed targets, model providers, and notification channel credentials.
  - Generates detailed post-cleanup verification reporting (`verified_clean`, file counts, and uncleared errors list) and logs action in admin logs as the new baseline entry.
  - Added a designated **Clear All Test Data** maintenance section card in `Testing.jsx` requiring explicit user confirmation.

- **Created Comprehensive Documentation Suite (`docs/`)**:
  - Root [`README.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/README.md) — updated quick start, directory structure, data storage paths, and sitemap.
  - [`frontend/README.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/frontend/README.md) — Vite/React architecture, component tree, and development scripts.
  - [`backend/README.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/README.md) — Flask control plane, JWT auth, security headers, and execution flow.
  - [`docs/README.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/docs/README.md) — complete sitemap and index.
  - [`docs/architecture.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/docs/architecture.md) — architecture diagrams, subsystem descriptions, and pipeline flow.
  - [`docs/api.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/docs/api.md) — REST API reference for auth, user feed, admin, and testing endpoints.
  - [`docs/database.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/docs/database.md) — SQLite schema tables, Fernet encryption, and filesystem layout.
  - [`docs/deployment.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/docs/deployment.md) — Docker Compose configuration and standalone python setup.
  - [`docs/configuration.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/docs/configuration.md) — Environment variable reference and `.env` duplicate key warnings.
  - [`docs/troubleshooting.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/docs/troubleshooting.md) — Troubleshooting checklist, error scenarios, and solutions.
  - [`docs/testing.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/docs/testing.md) — Pytest suite structure and frontend build verification.
  - [`docs/notifications.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/docs/notifications.md) — Telegram & Slack channel configuration and testing.
  - [`docs/ai-routing.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/docs/ai-routing.md) — Multi-tier LLM routing, rate slots, and LLM fallbacks.
  - [`docs/scheduler.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/docs/scheduler.md) — IST schedule alignment and execution pipeline sequence.
  - [`docs/project-structure.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/docs/project-structure.md) — Full repository layout tree.
  - [`docs/command-center.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/docs/command-center.md) — Interactive testing dashboard & maintenance cleanup guide.

- **Created Handoff Document (`PROJECT_STATUS.md`)**:
  - Created [`PROJECT_STATUS.md`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/PROJECT_STATUS.md) as the handoff document for future development sessions.

- **Verification**:
  - Added `test_clear_all_test_data_maintenance_action` to `tests/test_backend_api.py`.
  - Ran `npm run build` — 1595 modules transformed, 0 warnings, 0 errors.
  - Ran `python -m pytest` — 8/8 backend test cases passing.

## 2026-08-02 - Testing & Command Center, Source Validation, Report Export, and Production Readiness

Completed:

- **Implemented Testing / Command Center page (`frontend/src/pages/admin/Testing.jsx`)**:
  - Full-featured system diagnostics & control plane page added to Admin navigation (`Shell.jsx`) and application router (`App.jsx`).
  - Added pipeline pause/resume toggle (`pipeline-toggle`), single-step collection runner, AI analysis runner, notification channel tester, and report generation runner.
  - Added individual diagnostic testers for AI Model Providers (`test-providers`), Feed Collectors (`test-collectors`), and MCP Servers (`test-mcp`).
  - Added maintenance tools for selective data clearing (reports, event logs, articles/queue, dedupe cache), scheduler reset, and config reloading.
  - Added live telemetry views: pipeline phase banner, queue breakdown, current item processed, active AI model & latency, storage sizes, and real-time error log stream.

- **Added Backend Testing API Endpoints (`backend/app.py`)**:
  - `GET /api/admin/testing/live-state` — returns runtime phase, queue metrics, AI status, storage path sizes, active component counts, and recent error log entries.
  - `POST /api/admin/testing/pipeline-toggle` — toggles global pipeline execution pause/resume setting.
  - `POST /api/admin/testing/run-collection` — runs immediate source collection cycle.
  - `POST /api/admin/testing/run-ai-analysis` — tests multi-tier AI analysis on demand.
  - `POST /api/admin/testing/run-notification` — tests all configured Telegram and Slack notification channels.
  - `POST /api/admin/testing/run-report` — generates intelligence report on demand.
  - `POST /api/admin/testing/test-providers` — tests all enabled AI providers in DB and reports latency and success.
  - `POST /api/admin/testing/test-collectors` — tests all enabled feed sources in DB for HTTP accessibility and article yield.
  - `POST /api/admin/testing/test-mcp` — tests MCP server transport connections.
  - `POST /api/admin/testing/clear` — clears target storage (reports, logs, articles, cache).
  - `POST /api/admin/testing/reset-scheduler` — resets queue and stuck items.
  - `POST /api/admin/testing/reload-config` — re-reads environment variables and database config.
  - `GET /api/user/reports/<report_id>/export` — allows downloading reports directly as Markdown (`.md`) or JSON files.

- **Hardened Source Management (`collector.py`)**:
  - Added `is_valid_source_url()` helper to validate HTTP/HTTPS schemes before fetching feeds.
  - Ensured deleted and disabled sources in DB are strictly ignored during collection cycles.

- **Enhanced Reports User UI (`Reports.jsx`)**:
  - Added "Export Markdown" and "Export JSON" buttons to all report cards for instant downloading.

- **Test Suite Extended (`tests/test_backend_api.py`)**:
  - Added `test_testing_center_endpoints` covering live state, pipeline toggle, provider testing, collector testing, AI analysis, and scheduler reset.
  - All unit tests pass cleanly.

- **Build Verification**:
  - `npm run build` executed under `frontend/` — 1595 modules transformed, 0 warnings, 0 errors.

## 2026-08-02 - End-to-end visibility fixes: AI status, reports, notifications, and .env critical bug

Completed:

- **CRITICAL FIX: `.env` duplicate keys wiped all API credentials.**
  - Root cause: `TELEGRAM_TOKEN`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`, `TELEGRAM_CHAT_ID`, `WP_URL`, `WP_USER`, `WP_APP_PASSWORD` were declared twice in `.env` — once with real values at the top, and again as empty strings at the bottom. `python-dotenv` uses the LAST occurrence of a duplicate key, so every credential was silently overwritten with an empty string.
  - This was the root cause of: Telegram notifications not arriving, AI analysis degrading to keyword-only fallback, and Slack delivery having no webhook.
  - Fix: Removed the duplicate empty declarations at the bottom of `.env`. Verified all keys now load as `SET`.

- **AI analysis visibility added (`ai_router.py`).**
  - Added `_ai_status` tracking dict with: `last_task`, `last_provider`, `last_model`, `last_latency_ms`, `last_fallback_used`, `last_success`, `last_error`, `last_called_at`, `total_calls`, `total_fallbacks`, `total_failures`.
  - `_configured_route_call()` and all fallback router functions (`local_call_premium`, `local_call`, `local_call_article`, `local_call_text`) now record every AI call with provider name, model, latency, success/failure, and whether a fallback was used.
  - `get_ai_status()` returns a snapshot for the UI.
  - New endpoint: `GET /api/admin/ai-status`.
  - `GET /api/admin/overview` now includes `ai_status` in its response.

- **Notification delivery logging added (`notifier.py`).**
  - `_log()` helper writes to `event_logs` so delivery results appear in the Logs page.
  - `_send_one()` logs permanent errors (400/403) and retry-exhaustion failures with chat ID and error details.
  - `_send()` logs when Telegram is skipped (no token / no subscribers) and when delivery succeeds.
  - `send_digest()`, `send_daily_summary()`, `send_weekly_summary()` now log success/failure with article counts.
  - New `test_channel(kind, target, secret)` function sends a test message to a specific Telegram chat or Slack webhook and returns a result dict with `ok`/`error`/`message`.
  - New endpoints: `POST /api/admin/notification-channels/test` and `POST /api/user/notification-channels/test`.

- **Scheduler saves digests even when AI fails (`scheduler.py`).**
  - Root cause: `scheduler.py` only saved digests when `digest_data` was truthy. If AI synthesis failed (empty API keys), no digest was saved, so the Reports page was always empty.
  - Fix: When AI synthesis returns `None`, a degraded-mode digest is built from processed items (top titles by category, CVEs) and saved with a `_degraded: True` flag. The Reports page now always shows real content after a cycle.
  - Runtime state now includes `ai_status` for UI visibility.

- **Frontend Dashboard completely rebuilt (`Dashboard.jsx`).**
  - Phase banner with color-coded status (idle/collecting/processing/digesting/syncing/daily_summary).
  - Queue progress with pending/processing/done/failed metrics and a progress bar.
  - AI Analysis Status panel: provider, model, task, latency, success/failure, fallback used, last call time, total calls, total fallbacks, total failures, and last error.
  - Telemetry panel with cycles, scraped, failed, last cycle time, and severity breakdown badges.
  - Cycle timing panel: last started, last finished, last daily, next cycle.
  - Auto-refresh every 5 seconds (toggleable) so background work is visible without manual refresh.

- **Frontend Reports page rebuilt (`Reports.jsx`).**
  - Loading state, empty state with icon and guidance, and error state.
  - Day-range selector (7/30/90 days).
  - Expandable report cards showing: headline, strategic note, risk level, cybersecurity updates, AI updates, tech & business updates, hardware & mobile updates, escalating threats, patterns, actor activity, tech trends, recommendations, doom/bloom, CVEs.
  - Degraded-mode reports are flagged with a warning banner.

- **Frontend Feed page rebuilt (`Feed.jsx`).**
  - Loading state, empty state with icon and guidance.
  - Severity filter dropdown added.
  - Each feed item shows: severity badge, category, confidence score, title (link), source, timestamp.
  - Expandable detail view showing: AI analysis summary, CVEs, actors, affected products, tags, scrape status, paywall status.
  - Color-coded left border by severity.

- **Frontend Channels page rebuilt (`Channels.jsx`).**
  - Test button for both new (unsaved) and existing channels.
  - Test results shown inline with success/failure/loading indicators.
  - Loading state for channel list.
  - Improved setup guide with Telegram and Slack instructions.

- **Frontend Logs page rebuilt (`Logs.jsx`).**
  - Auto-refresh toggle (5s interval).
  - Loading state and empty state.
  - Color-coded log levels (ERROR=red, WARN=amber, INFO=green).
  - Details column showing `details_json` content (truncated).

- **Frontend Sources page updated (`Sources.jsx`).**
  - Loading state added.
  - Category field changed to a dropdown with valid categories.
  - Empty state message.

- **Frontend Models page updated (`Models.jsx`).**
  - Loading state added.
  - Status column showing Active/Blocked/Disabled with icons.
  - Empty state message.

- **CSS styles added (`app.css`).**
  - Phase banner, progress bar, AI status grid, severity badges, empty state, report styles, feed styles, test result indicators, log level colors, spinner animation.

- **Backend API additions (`backend/app.py`).**
  - `GET /api/admin/ai-status` — returns AI call metadata.
  - `POST /api/admin/notification-channels/test` — tests a notification channel.
  - `POST /api/user/notification-channels/test` — tests a user notification channel.
  - `GET /api/admin/overview` now includes `ai_status`.
  - Total routes: 39 (was 36).

Verified:

- `python -m pytest -q`: 6 tests passed (20 deprecation warnings, all `datetime.utcnow()`).
- `npm run build`: frontend rebuilt successfully, `frontend/dist/index.html` and `assets/` present.
- Backend smoke test: 39 routes registered, new endpoints confirmed (`/api/admin/notification-channels/test`, `/api/admin/ai-status`, `/api/user/notification-channels/test`).
- `.env` verification: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` all load as `SET` (previously `EMPTY`).
- Backend started on port 7860: `/health` returns `{"db":true,"frontend":true,"status":"ok"}`, `/ping` returns `pong`, SPA serves `<title>JARVIS</title>`.

Bugs found and fixed:

1. **`.env` duplicate keys** — all API credentials silently wiped by empty re-declarations at the bottom of the file. Root cause of Telegram/Slack failures and AI degradation.
2. **No AI visibility** — `ai_router.py` had no tracking; UI couldn't show provider/model/status/fallback. Fixed with `_ai_status` tracking and `get_ai_status()`.
3. **No notification delivery logging** — `notifier.py` only printed to console; failures invisible in Logs page. Fixed with `_log()` helper writing to `event_logs`.
4. **Digests not saved on AI failure** — `scheduler.py` skipped `save_digest()` when AI returned `None`. Fixed with degraded-mode digest fallback.
5. **Dashboard showed raw JSON** — replaced with structured panels for phase, queue, AI status, telemetry, and cycle timing.
6. **No auto-refresh** — Dashboard and Logs now auto-refresh every 5 seconds.
7. **Feed lacked AI details** — added expandable detail view with summary, CVEs, actors, affected products, tags.
8. **No channel test button** — added test endpoints and UI test buttons with inline results.
9. **No loading/empty/error states** — added to all pages (Dashboard, Reports, Feed, Channels, Logs, Sources, Models).

Files modified:

- `.env` — removed duplicate empty key declarations
- `ai_router.py` — added AI call tracking (`_ai_status`, `_record_ai_call`, `get_ai_status`, `_tracked_call`)
- `notifier.py` — added `_log()`, delivery logging in `_send_one`/`_send`, `test_channel()` function
- `scheduler.py` — degraded-mode digest fallback, AI status in runtime state
- `backend/app.py` — new endpoints (`ai-status`, `notification-channels/test`), `ai_status` in overview
- `frontend/src/pages/admin/Dashboard.jsx` — complete rebuild with AI status, queue, telemetry, auto-refresh
- `frontend/src/pages/user/Reports.jsx` — complete rebuild with expandable cards, loading/empty states
- `frontend/src/pages/user/Feed.jsx` — complete rebuild with AI details, severity filter, expandable items
- `frontend/src/pages/Channels.jsx` — test buttons, loading state, inline test results
- `frontend/src/pages/admin/Logs.jsx` — auto-refresh, loading/empty states, color-coded levels, details column
- `frontend/src/pages/admin/Sources.jsx` — loading state, category dropdown
- `frontend/src/pages/admin/Models.jsx` — loading state, status column with Active/Blocked/Disabled
- `frontend/src/styles/app.css` — new styles for all new UI components

Remaining limitations:

- Docker is not installed in this workstation session, so Compose could not be launched here.
- Live browser smoke test (login, navigate, run cycle) should be completed on a Docker-enabled machine.
- The `datetime.utcnow()` deprecation warnings are cosmetic and do not affect functionality.
- Telegram/Slack delivery requires valid chat IDs and webhook URLs configured by the user via the UI.

## 2026-08-02 - Frontend refactored into clean component structure with full stability fixes

Completed:

- **Split the single-file `frontend/src/main.jsx` into a proper component hierarchy**:
  - `frontend/src/api.js` — centralized API helper with robust JSON/error handling, token/CSRF store, and auth setters.
  - `frontend/src/App.jsx` — app root with `ErrorBoundary`, hash-based routing, mode switching (`/admin` ↔ `/user`) via `history.pushState` (zero full-page reloads), `popstate`/`hashchange` listeners, theme handling, and auth bootstrap.
  - `frontend/src/components/` — `Button`, `ui` (Field/Metric/Header/Table), `Auth` (Login/PasswordChange), `Shell` (sidebar navigation).
  - `frontend/src/pages/admin/` — `Dashboard`, `Sources`, `Models`, `Users`, `Channels` (shared), `Mcp`, `Logs`, plus `JsonPage` for storage/health/migrations read-only views.
  - `frontend/src/pages/user/` — `Feed`, `Reports`, `Assistant`, `Preferences`, `Channels` (shared user mode).
  - `frontend/src/main.jsx` — slim entry point rendering `<Root />`.

- **Fixed all runtime error sources**:
  - `api()` now safely parses non-JSON responses instead of throwing on `JSON.parse`.
  - All page components catch API errors and render inline error banners instead of crashing.
  - `Login` and `PasswordChange` now handle failures gracefully and disable submit while busy.
  - Added a global `ErrorBoundary` with a "Try again" recovery UI so no page can white-screen the app.
  - MCP test result now renders a readable message instead of `undefined`.
  - Reports page renders an empty state message instead of a blank list.

- **Navigation is now instant**:
  - Hash changes update React state immediately (`setRoute`) without waiting for the `hashchange` event.
  - Admin ↔ User console switching uses `history.pushState` — no full page reload, no Ctrl+R needed.
  - Browser back/forward buttons are handled via both `popstate` and `hashchange` listeners.

- **Verified**:
  - `npm.cmd run build` succeeds and regenerates `frontend/dist` with the new component bundle.
  - `python -m pytest -q` — all 6 backend tests pass.
  - Backend import smoke test — 36 routes registered, `/`, `/admin`, `/user` each return the SPA `200` with the `dist` bundle, `/health` returns `{"status":"ok","db":true,"frontend":true}`.

Known environment limits:

- Docker is not installed in this workstation session, so Compose could not be launched here.
- The local Node setup is available in `frontend/node_modules`; production Docker builds install and build it independently.
- Live-database login could not be re-verified because the local admin password was changed in a prior session (expected behavior — pytest covers the full auth flow against an isolated test database).

Next safe milestones:

1. Run `docker compose up --build` on a Docker-enabled machine and complete the documented browser smoke flow.
2. Add real browser smoke tests (Playwright) once the project environment includes a browser runner.
3. Extend report search/export and the visual log time-range filter after the core deployment check passes.

## 2026-08-02 - Core production flow verified

Completed:

- Added the separated `backend/`, `core/`, `storage/`, `frontend/`, and `docs/` structure while retaining root-level Python compatibility entry points.
- Added Flask authentication, first-login password change enforcement, role checks, encrypted integration storage, admin/user APIs, MCP HTTP and STDIO transports, and model-provider routing.
- Added a React/Vite dashboard build for admin and user workflows.
- Added Docker Compose with persistent `/data` storage and a read-only legacy `jarvis-data/` mount.
- Added a read-only legacy scanner for bundles, digests, telemetry, runtime state, seen IDs, and subscribers.
- Fixed Reports to combine current runtime reports with legacy reports. Password changes now always require the current password.

Verification completed:

- `python -m pytest -q`: 5 tests passed. Coverage includes login/password change, current and legacy reports, role authorization, encrypted notification persistence, MCP HTTP/STDIO behavior, and the legacy migration endpoint.
- `python -m py_compile` passed for the backend, scheduler, routing, notification, and storage modules.
- `npm.cmd run build` passed and regenerated the React production bundle under `frontend/dist`.

Known environment limits:

- Docker is not installed in this workstation session, so Compose could not be launched here.
- The local Node setup is available in `frontend/node_modules`; production Docker builds install and build it independently.

Next safe milestones:

1. Run `docker compose up --build` on a Docker-enabled machine and complete the documented browser smoke flow.
2. Add real browser smoke tests (Playwright) once the project environment includes a browser runner.
3. Extend report search/export and the visual log time-range filter after the core deployment check passes.

## 2026-08-02 - Versioned SQLite upgrade path completed

Completed:

- Replaced one-time `CREATE TABLE IF NOT EXISTS` setup with transactional schema migrations, recorded in `schema_migrations` and `PRAGMA user_version`.
- Added migrations through schema version 4 for authentication fields, all control-plane columns, unique guarantees, query indexes, and the notification-channel user foreign key.
- Fixed local `.env` load order so `JARVIS_DB_PATH`, administrator settings, and security configuration apply before database initialization.
- Added an admin schema inventory to `GET /api/admin/migrations`.
- Added a regression test that launches the backend against an old database, then verifies preserved rows, roles, login, forced password change, permissions, indexes, and foreign keys.

Live verification:

- Backed up the runtime SQLite file to `C:\data\jarvis.db.pre-schema-v4-20260802-101632.bak` before migration.
- Runtime database migrated to v4 automatically on backend import.
- SQLite integrity check passed; foreign-key check returned no violations.
- Live login, `/api/auth/me`, and `/api/admin/overview` each returned `200` for the configured administrator.