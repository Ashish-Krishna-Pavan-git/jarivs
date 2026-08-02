# JARVIS Worklog

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
