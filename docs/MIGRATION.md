# Migration Notes

Old production data stays in `jarvis-data/`. Docker mounts it read-only at `/legacy/jarvis-data`.

## SQLite schema upgrades

JARVIS automatically runs transactional, versioned SQLite migrations whenever the backend starts. Migration history is stored in the `schema_migrations` table and mirrored in `PRAGMA user_version`.

The current schema version is `4`. It creates missing control-plane tables, upgrades older `users` tables with authentication fields such as `active`, preserves existing password hashes and roles, adds required indexes, and repairs the notification-channel user foreign key when its data is valid.

Migrations are additive. They do not delete `users`, reports, notification channels, unknown legacy tables, or files in `jarvis-data/`. If an old database has conflicting duplicate values or orphaned notification users that cannot be repaired safely, startup stops with a specific migration error and leaves the database unchanged.

After startup, an administrator can inspect migration history, schema version, columns, indexes, and foreign keys in Admin -> Settings & Migrations or `GET /api/admin/migrations`.

Before upgrading a production installation, make a SQLite-consistent backup of `/data/jarvis.db` and back up the separate `jarvis-data/` folder. The local migration verification created `C:\data\jarvis.db.pre-schema-v4-20260802-101632.bak`; retain it until the deployment has been observed in normal operation.

JARVIS scans:

- `articles_bundle.json`
- `digests/YYYY-MM-DD/digest_cycle_*.json`
- `telemetry.json`
- `runtime_state.json`
- `seen.json`
- `data/subscribers.json`

New runtime data writes to `/data`, not `jarvis-data/`.

Back up both `/data` and `jarvis-data/` before upgrades.
