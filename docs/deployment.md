# Deployment & Production Setup

This guide covers deployment procedures for running JARVIS in Docker or standalone Python environments.

## Docker Compose Deployment (Recommended)

JARVIS includes a production `docker-compose.yml` and `Dockerfile` preconfigured with health checks, persistent data volumes, and legacy data read-only mounts.

### 1. Configure Environment

Copy `.env.example` to `.env` and set your credentials:

```bash
cp .env.example .env
```

Key environment settings to verify in `.env`:
- `ADMIN_USERNAME` and `ADMIN_PASSWORD`
- `JWT_SECRET` and `JARVIS_ENCRYPTION_KEY`
- `GEMINI_API_KEY` or `GROQ_API_KEY`
- `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` (optional)

### 2. Launch Container Stack

```bash
docker compose up --build -d
```

### 3. Verify Container Status

```bash
docker compose ps
docker compose logs -f
```

Access the UI at `http://localhost:7860`.

---

## Docker Volume Storage Layout

The `docker-compose.yml` mounts a persistent volume `jarvis_data` at `/data`:

```yaml
volumes:
  - jarvis_data:/data
  - ./jarvis-data:/legacy/jarvis-data:ro
```

- `/data`: Active database, logs, processed articles, digests, and deduplication cache.
- `/legacy/jarvis-data`: Mounted read-only to preserve existing historical data without rewriting it.

---

## Standalone Python Deployment

### Requirements
- Python 3.10+
- Node.js 18+ (for building frontend)

### Installation Steps

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Build React frontend:
   ```bash
   cd frontend
   npm install
   npm run build
   cd ..
   ```

3. Launch application server & background scheduler:
   ```bash
   python app.py
   ```

The application runs on port `7860`.
