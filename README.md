# JARVIS Intelligence System

JARVIS is a self-hosted intelligence platform. It collects RSS and web sources, analyzes articles with configurable AI models, stores reports, and delivers alerts through Telegram and Slack.

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:7860`.

Fresh install login:

- Username: `admin`
- Password: `admin123!ChangeMe`

If `ADMIN_PASSWORD` is empty, JARVIS forces a password change after the first login.

## Production Layout

```text
backend/        Flask API, auth, admin/user routes, MCP APIs
core/           Intelligence pipeline compatibility package
frontend/       React/Vite dashboard with dark/light themes
storage/        Runtime persistence and read-only legacy data bridge
docs/           Beginner-friendly user, admin, Docker, API, MCP, and migration guides
```

Root-level Python files remain as compatibility entrypoints so older scripts still work.

## Data Storage

Docker runtime data is written to `/data` in the `jarvis_data` volume:

- `/data/jarvis.db`
- `/data/processed`
- `/data/daily`
- `/data/archive`
- `/data/logs`
- `/data/raw_articles`

Old production data in `jarvis-data/` is mounted read-only at `/legacy/jarvis-data` and surfaced in the Storage, Reports, and Migration views. JARVIS does not delete or rewrite it.

## Documentation

- [Installation](docs/INSTALLATION.md)
- [Docker Deployment](docs/DOCKER_DEPLOYMENT.md)
- [User Guide](docs/USER_GUIDE.md)
- [Admin Guide](docs/ADMIN_GUIDE.md)
- [API Reference](docs/API.md)
- [Environment Variables](docs/ENVIRONMENT.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Architecture](docs/ARCHITECTURE.md)
- [MCP](docs/MCP.md)
- [Migration](docs/MIGRATION.md)
- [Integrations](docs/INTEGRATIONS.md)
