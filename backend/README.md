# JARVIS Backend

The JARVIS backend is a Flask-based application providing control plane APIs, authentication, user/admin routes, security middleware, and background intelligence pipeline orchestration.

## Features

- **Authentication & Security**: JWT-based session tokens with HTTP-only cookies, password hashing with PBKDF2/SHA256, CSRF tokens (`X-CSRF-Token`), role-based authorization (`admin` vs `user`), and forced initial password changes.
- **REST Control APIs**: Complete JSON endpoints for Overview, Testing, Sources, Models, Users, MCP, Logs, Storage, Telemetry, Reports, and Feed.
- **Model Routing**: Multi-tier AI routing system supporting Gemini, Groq, Ollama, and OpenAI-compatible providers with automatic rate backoff and fallback tiers.
- **Background Scheduler**: IST-aligned background schedule trigger for cycle collection (08:00, 15:00, 21:00 IST) and executive daily summaries (07:00 IST).
- **Single-page App Serving**: Serves the compiled React production bundle from `frontend/dist`.

## Architecture & Entry Points

```text
backend/
├── app.py          # Main Flask application, API routes, middleware, and entry point
└── Logs/           # Backend runtime logs
```

Compatibility entry points in root directory:
- [`app.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/app.py): Imports `app, main` from `backend.app` for launcher compatibility.
- [`jarvis_db.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/jarvis_db.py): SQLite control plane persistence with schema versioning & migrations.
- [`security_utils.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/security_utils.py): Cryptographic Fernet encryption, password hashing, JWT, CSRF, security headers.
- [`ai_router.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/ai_router.py): Multi-tier LLM routing, story-driven prompts, latency/call tracking.
- [`scheduler.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/scheduler.py): Main orchestrator thread loop, IST slot timing, keep-alive worker.
- [`collector.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/collector.py): RSS feed collector with URL scheme validation.
- [`worker_processor.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/worker_processor.py): Scrapes content, executes AI analysis, enqueues/processes articles.
- [`notifier.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/notifier.py) & [`slack_notifier.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/slack_notifier.py): Telegram & Slack delivery channels.

## Startup & Execution

Run backend server directly:

```bash
python app.py
```

Runs Flask on `http://0.0.0.0:7860` with scheduler and background workers initialized automatically.

## API Authentication

- Public endpoints: `/`, `/user`, `/admin`, `/ping`, `/health`, `/api/auth/login`
- Authenticated endpoints require a Bearer token in header:
  `Authorization: Bearer <token>`
- State-modifying requests (`POST`, `PUT`, `DELETE`) require a CSRF token header:
  `X-CSRF-Token: <csrf_token>`
