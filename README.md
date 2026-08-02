---
license: mit
title: Jarvis
sdk: docker
emoji: 🏃
colorFrom: red
colorTo: indigo
---
# JARVIS Intelligence System

> Self-hosted AI-powered threat intelligence aggregator, analyst, and publisher.

JARVIS collects security and technology articles from RSS feeds, analyzes them with configurable LLMs (Gemini, Groq, Ollama, custom OpenAI-compatible providers), generates daily digests and executive reports, delivers alerts via Telegram and Slack, and publishes formatted reports to WordPress — automatically on a schedule.

---

## Quick Start (Docker)

```bash
# 1. Clone the repository
[git clone https://github.com/your-org/jarvis-agent.git](https://github.com/Ashish-Krishna-Pavan-git/jarivs)
cd jarvis

# 2. Create your environment file
cp .env.example .env
# Edit .env and set at least: JWT_SECRET, FLASK_SECRET_KEY
# Optional: add GEMINI_API_KEY, TELEGRAM_TOKEN, WP_URL, etc.

# 3. Start
docker compose up --build -d

# 4. Open the dashboard
open http://localhost:7860
```

**Default admin login (first run):**
- Username: `admin`
- Password: `admin123!ChangeMe` or `admin`

JARVIS forces a password change after the first login.

---

## Quick Start (Local Development)

```bash
# Python 3.11+ required
pip install -r requirements.txt

# Build the frontend
cd frontend && npm install && npm run build && cd ..

# Copy and configure environment
cp .env.example .env

# Run the backend
python app.py
```

The backend starts at `http://localhost:7860`.  
The scheduler runs as a subprocess and starts automatically.

---

## What JARVIS Does

| Feature | Description |
|---|---|
| **Feed Collection** | Parses RSS/Atom feeds on a configurable schedule (08:00, 15:00, 21:00 IST) |
| **Deduplication** | MD5 fingerprint cache prevents processing the same article twice |
| **AI Analysis** | Routes each article through a priority-ordered LLM chain for categorization, severity scoring, CVE extraction, and summary |
| **Cycle Digests** | After each collection cycle, generates a structured threat digest |
| **Daily Report** | Every morning at 07:00 IST, synthesizes all cycle digests into an executive daily report |
| **Telegram Alerts** | Sends CRITICAL/HIGH alerts immediately; digest summaries after each cycle |
| **Slack Alerts** | Mirrors Telegram alerts to a Slack webhook |
| **Audio Podcast** | Text-to-speech daily report sent to Telegram as an audio file |
| **WordPress Publishing** | Publishes the daily report as a formatted HTML post via WordPress REST API |
| **Admin Dashboard** | Manage feeds, AI models, users, notifications, MCP, and logs through a React UI |
| **User Feed** | Browse processed intelligence articles with severity and category filters |

---

## Repository Structure

```text
jarvis-agent/
├── app.py                  # Entry point — starts Flask + scheduler subprocess
├── scheduler.py            # Compatibility shim → backend/scheduler/scheduler.py
├── config.py               # Compatibility shim → backend/config/config.py
├── jarvis_db.py            # Compatibility shim → backend/database/jarvis_db.py
├── ...                     # Other root shims for backward compatibility
│
├── backend/                # All Python implementation lives here
│   ├── app.py              # Flask application, REST API routes, auth middleware
│   ├── api/                # API route groupings (future)
│   ├── ai/                 # AI router — multi-provider LLM dispatch
│   ├── archive/            # Historical data archiver
│   ├── auth/               # JWT, CSRF, password hashing, encryption
│   ├── collectors/         # RSS feed collector and HTML scraper
│   ├── config/             # Centralized config (paths, keys, constants)
│   ├── database/           # SQLite ORM, migrations, CRUD helpers
│   ├── notifications/      # Telegram + Slack notification engines
│   ├── reports/            # Daily summary + WordPress newsletter publisher
│   ├── scheduler/          # Scheduler orchestrator and queue manager
│   ├── services/           # Worker processor, MCP client, audio, runtime state
│   ├── storage/            # Article persistence, dedup, legacy data bridge
│   └── utils/              # Internet connectivity monitor
│
├── core/                   # Legacy compat package — delegates to backend/
├── storage/                # Legacy compat package — delegates to backend/storage/
│
├── frontend/               # React 18 + Vite single-page application
│   └── src/
│       ├── pages/admin/    # Dashboard, Sources, Models, Users, Logs, Testing, MCP
│       └── pages/user/     # Feed, Reports, Assistant, Preferences
│
├── docs/                   # Documentation
├── data/                   # Runtime data (git-ignored — populated at runtime)
│   ├── database/           # jarvis.db
│   ├── processed/          # Analyzed article JSON files
│   ├── reports/daily/      # Cycle digest and daily summary JSON+TXT
│   ├── archive/            # Reports older than 3 days
│   ├── cache/              # seen.json deduplication fingerprints
│   └── logs/               # Event logs
│
├── scripts/                # Helper scripts
├── tools/                  # Diagnostic tools (health_check.py)
├── docker/                 # Docker artifacts
├── config/                 # Config templates
├── tests/                  # pytest test suite
│
├── Dockerfile              # Production Docker image
├── docker-compose.yml      # Local/production Docker Compose
├── requirements.txt        # Python dependencies
└── .env.example            # Environment variable template
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values you need.

### Required for production

| Variable | Description |
|---|---|
| `JWT_SECRET` | Random 48+ character secret for JWT signing |
| `FLASK_SECRET_KEY` | Random secret for Flask session signing |

### AI Providers (at least one recommended)

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key |
| `GROQ_API_KEY` | Groq API key |
| `OPENAI_API_KEY` | OpenAI-compatible API key |
| `OLLAMA_URL` | Ollama base URL (default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Ollama model name (default: `phi4-mini`) |

### Notifications (optional)

| Variable | Description |
|---|---|
| `TELEGRAM_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat/channel ID |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL |

### WordPress Publishing (optional)

| Variable | Description |
|---|---|
| `WP_URL` | WordPress site URL, e.g. `https://mysite.com` |
| `WP_USER` | WordPress username |
| `WP_APP_PASSWORD` | WordPress **Application Password** (not your login password) |
| `WP_CATEGORY_ID` | Category ID to assign the post (default: `1`) |
| `WP_POST_STATUS` | `publish` or `draft` (default: `publish`) |
| `WP_TAGS` | Comma-separated tag IDs (default: empty) |

### Data Storage

| Variable | Default | Description |
|---|---|---|
| `JARVIS_DATA_DIR` | `/data` (Docker) / `/tmp/jarvis/data` (local) | Root data directory |
| `JARVIS_DB_PATH` | `$JARVIS_DATA_DIR/jarvis.db` | SQLite database path |

### Admin User

| Variable | Default | Description |
|---|---|---|
| `ADMIN_USERNAME` | `admin` | Admin username created on first start |
| `ADMIN_PASSWORD` | `admin` | Admin password (JARVIS forces change on first login) |

---

## WordPress Setup

JARVIS publishes the daily report to WordPress via the REST API using **Application Passwords** — a secure alternative to using your login password.

### Step-by-step

1. **Enable Application Passwords** (WordPress 5.6+)  
   In your WordPress admin: *Users → Profile → Application Passwords*.  
   Generate a new password named "JARVIS".

2. **Set environment variables** in your `.env`:
   ```env
   WP_URL=https://your-wordpress-site.com
   WP_USER=your_wp_username
   WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
   WP_CATEGORY_ID=1
   WP_POST_STATUS=publish
   ```

3. **Verify** by watching the JARVIS logs during the 07:00 IST daily summary.  
   Look for lines starting with `[WP]`.

4. **Audit log** is written to `$JARVIS_DATA_DIR/wordpress_posts.jsonl` — every publish attempt is recorded with timestamp, post ID, URL, and any error.

JARVIS checks for an existing post with the same slug before publishing — if one exists for today's date, it updates the post instead of creating a duplicate.

---

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | System design, component interactions, data flow |
| [API Reference](docs/API.md) | REST endpoint reference |
| [Database](docs/database.md) | SQLite schema and migrations |
| [Configuration](docs/configuration.md) | All environment variables explained |
| [Deployment](docs/deployment.md) | Docker and bare-metal deployment |
| [Docker](docs/docker.md) | Docker-specific configuration |
| [Local Development](docs/local-development.md) | Local dev setup and workflow |
| [Scheduler](docs/scheduler.md) | Schedule logic and cycle orchestration |
| [AI Routing](docs/ai-routing.md) | LLM provider priority, rate limits, fallbacks |
| [Notifications](docs/notifications.md) | Telegram and Slack setup |
| [Reports](docs/reports.md) | Daily digests and WordPress publishing |
| [Storage](docs/storage.md) | Data directories and file layout |
| [Testing](docs/testing.md) | Running the test suite |
| [Command Center](docs/command-center.md) | Admin testing dashboard |
| [Folder Structure](docs/folder-structure.md) | Full directory reference |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and fixes |
| [Developer Guide](docs/developer-guide.md) | How to contribute |

---

## License

MIT — see [LICENSE](LICENSE) if included.