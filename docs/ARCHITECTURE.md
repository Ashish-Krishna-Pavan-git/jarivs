# Architecture

JARVIS runs a Flask backend, React frontend, SQLite control plane, and scheduler subprocess.

Flow:

1. Scheduler triggers cycles.
2. Collector reads sources from SQLite.
3. Dedupe removes seen articles.
4. Worker scrapes content.
5. AI router uses enabled model routes.
6. Storage writes JSON/Markdown reports.
7. Notifier sends Telegram and Slack alerts.
8. Frontend reads status, feeds, reports, logs, health, storage, and settings over API.

Security:

- PBKDF2 password hashing.
- JWT sessions.
- CSRF on writes.
- Encrypted secrets.
- URL validation for external calls.
- Read-only legacy data mount.
