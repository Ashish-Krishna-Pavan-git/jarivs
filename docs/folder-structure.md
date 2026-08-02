# Repository Folder Structure

Comprehensive breakdown of the JARVIS repository layout:

```text
Jarvis-Agent/
├── app.py                      # Root launcher shim
├── backend/                    # Core Python Backend Subpackages
│   ├── app.py                  # Central Flask controller
│   ├── api/                    # REST API definitions
│   ├── auth/                   # Security, JWT, CSRF, Fernet encryption
│   ├── collectors/             # RSS collector & web scraper
│   ├── ai/                     # Multi-tier LLM router & rate locks
│   ├── scheduler/              # IST schedule & in-memory queue
│   ├── notifications/          # Telegram & Slack notification engines
│   ├── reports/                # Daily summary digest generators
│   ├── database/               # SQLite database & transactional schema migrations
│   ├── storage/                # JSON persistence, dedupe, legacy bridge
│   ├── archive/                # Historical report archiving
│   ├── services/               # Worker processor, audio generator, MCP client
│   ├── models/                 # Domain schemas & data models
│   ├── utils/                  # Network monitor & utility helpers
│   ├── config/                 # Environment configuration loader
│   └── tests/                  # Backend unit test suites
│
├── frontend/                   # React 18 / Vite Single-Page Application
│   ├── src/                    # Components, pages, and styles
│   └── dist/                   # Production distribution bundle
│
├── docs/                       # Comprehensive documentation suite
├── scripts/                    # Management launch scripts
├── docker/                     # Dockerfile and Docker Compose manifests
├── data/                       # Operational data directories
├── config/                     # Configuration templates
├── tests/                      # Automated pytest test suites
├── tools/                      # System diagnostic utilities
│
├── README.md                   # Root project overview
├── PROJECT_STATUS.md           # Developer handoff document
└── WORKLOG.md                  # Development trajectory log
```
