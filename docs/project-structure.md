# Project Structure

Complete breakdown of directory layouts, root files, and sub-packages in the JARVIS repository.

```text
Jarvis-Agent/
├── .env.example                # Template for environment variables and credentials
├── Dockerfile                  # Container build instructions for Flask + Python environment
├── README.md                   # Root project documentation
├── PROJECT_STATUS.md           # Maintenance status and handoff notes
├── WORKLOG.md                  # Development trajectory log
├── docker-compose.yml          # Docker deployment configuration with volumes
├── requirements.txt            # Python package dependencies
├── runtime_state.json          # Runtime phase state file (persisted)
├── seen.json                   # Deduplication fingerprint cache file (persisted)
│
├── backend/                    # Flask backend application package
│   ├── README.md               # Backend module documentation
│   └── app.py                  # API endpoints, authentication, security middleware
│
├── frontend/                   # Single Page React application (Vite)
│   ├── README.md               # Frontend structure & dev instructions
│   ├── index.html              # React entry HTML
│   ├── package.json            # Node.js dependencies
│   ├── vite.config.js          # Vite build config
│   ├── dist/                   # Compiled static bundle (served by Flask)
│   └── src/                    # JSX source components and styles
│       ├── main.jsx            # Entry point
│       ├── App.jsx             # Router and theme container
│       ├── api.js              # Centralized API fetch wrapper
│       ├── components/         # Shell, Auth, Button, Field, Table components
│       ├── pages/              # Admin and User page views
│       └── styles/             # Global CSS and design tokens
│
├── core/                       # Compatibility package wrapper
│
├── storage/                    # Storage package
│   ├── persistence.py          # Articles and digests file I/O
│   └── legacy_data.py          # Read-only legacy data bridge
│
├── docs/                       # Project documentation suite
│   ├── README.md               # Documentation sitemap
│   ├── architecture.md         # System architecture diagram & design
│   ├── api.md                  # Complete REST API reference
│   ├── database.md             # SQLite database schema & migrations
│   ├── deployment.md           # Docker & manual deployment guides
│   ├── configuration.md        # Environment variable reference
│   ├── troubleshooting.md      # Diagnostic checklist & error solutions
│   ├── testing.md              # Pytest backend test suite documentation
│   ├── notifications.md        # Telegram & Slack alert configuration
│   ├── ai-routing.md           # Multi-tier LLM router & fallbacks
│   ├── scheduler.md            # IST cycle schedule & pipeline flow
│   ├── project-structure.md    # Repository layout
│   └── command-center.md       # Administrative Command Center guide
│
├── tests/                      # Automated pytest suite
│   └── test_backend_api.py     # End-to-end API & integration tests
│
# Root-Level Core Modules (Compatibility Entrypoints):
├── ai_router.py                # LLM router, prompts, call tracking
├── collector.py                # RSS collector with URL validation
├── dedupe.py                   # Fingerprint deduplication engine
├── jarvis_db.py                # SQLite database management & migrations
├── queue_manager.py            # In-memory item processing queue
├── runtime_state.py            # Phase & telemetry state tracking
├── scheduler.py                # Background scheduler & orchestrator
├── scraper.py                  # Full-text HTML web scraper
├── security_utils.py           # Cryptographic security, JWT, CSRF, passwords
├── notifier.py                 # Telegram notification engine
├── slack_notifier.py           # Slack webhook delivery engine
├── audio_generator.py          # Edge-TTS podcast audio generator
├── dailySummary.py             # Executive daily synthesis runner
└── worker_processor.py         # Queue item worker pipeline processor
```
