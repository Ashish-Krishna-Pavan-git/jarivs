# Local Development Guide

This guide covers setting up JARVIS for local development on Windows, Linux, or macOS.

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ | Earlier versions not supported |
| Node.js | 18+ | For building the frontend |
| npm | 9+ | Bundled with Node.js |
| Git | any | For cloning |
| ffmpeg | any | For audio report generation (optional) |

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-org/jarvis-agent.git
cd jarvis-agent
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Build the frontend

The backend serves the React frontend as static files from `frontend/dist/`. You must build it at least once before running locally.

```bash
cd frontend
npm install
npm run build
cd ..
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

```env
JWT_SECRET=change-this-random-48-char-secret
FLASK_SECRET_KEY=change-this-too
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
```

See [Configuration](configuration.md) for all available options.

### 5. Run the backend

```bash
python app.py
```

This starts:
- The Flask API server on `http://localhost:7860`
- The scheduler as a subprocess (background, starts after 90 seconds)

Open `http://localhost:7860` and log in.

---

## Default Login

| Field | Value |
|---|---|
| Username | `admin` |
| Password | `admin` (or the value of `ADMIN_PASSWORD` in `.env`) |

If `ADMIN_PASSWORD` is empty in `.env`, JARVIS generates a temporary password and forces a change on first login.

---

## Data Directory

By default on local runs, data is stored in `/tmp/jarvis/data/` (Linux/macOS) or `C:\Users\<User>\AppData\Local\Temp\jarvis\data\` (Windows).

Override with the `JARVIS_DATA_DIR` environment variable:

```env
JARVIS_DATA_DIR=./local-data
```

---

## Frontend Development (Hot Reload)

If you are making changes to the React frontend, run the Vite dev server instead of building the static bundle:

```bash
cd frontend
npm run dev
```

The Vite dev server starts on `http://localhost:5173` and proxies API calls to the backend at `http://localhost:7860`.

After frontend changes are final, rebuild the static bundle:

```bash
npm run build
```

The backend always serves from `frontend/dist/` — make sure the bundle is rebuilt before testing the production path.

---

## Running Tests

```bash
# Run the full backend test suite
python -m pytest -v

# Run a specific test file
python -m pytest tests/test_backend_api.py -v

# Run with coverage report
python -m pytest --cov=backend tests/ -v
```

All 8 tests should pass with no warnings. See [Testing Guide](testing.md) for details.

---

## Running the Health Check

```bash
python tools/health_check.py
```

Verifies:
- Database schema version and migration count
- Runtime state (phase, queue stats)

---

## Troubleshooting Local Setup

### `ModuleNotFoundError: No module named 'jarvis_db'`

You are running a script from the wrong directory. Always run from the repository root:

```bash
cd /path/to/jarvis-agent
python app.py
```

The root shims (`jarvis_db.py`, `config.py`, etc.) are in the root directory and must be on `sys.path`.

### `Address already in use` on port 7860

Another process is using port 7860. Either stop it or change the port:

```bash
# Linux/macOS
lsof -i :7860
kill <PID>
```

Or set a different port in the `app.run()` call at the bottom of `backend/app.py`.

### Database is locked

Two processes are writing to `jarvis.db` simultaneously. Stop all running JARVIS processes and restart:

```bash
# On Linux/macOS
pkill -f "python app.py"
pkill -f "python scheduler.py"
python app.py
```

### Scheduler not starting

The scheduler subprocess is launched by `main()` in `backend/app.py` via `subprocess.Popen(["python", "scheduler.py"])`. This requires `scheduler.py` to be findable in the current working directory (root shim) and the Python environment to have all dependencies installed.

Check if the scheduler is running:

```bash
# Linux/macOS
ps aux | grep scheduler
```

### Frontend shows blank white page

The `frontend/dist/` directory is missing or empty. Rebuild the frontend:

```bash
cd frontend
npm run build
```

### Audio not working (ffmpeg missing)

Install ffmpeg:
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS with Homebrew
brew install ffmpeg

# Windows (chocolatey)
choco install ffmpeg
```

Or skip audio by leaving Telegram token unset — audio is only sent to Telegram.

---

## Useful Development Commands

```bash
# Check backend + database health
python tools/health_check.py

# Run only collector to test feed sources
python -c "from collector import collect_all; print(collect_all(limit_per_source=3))"

# Test AI router connectivity
python -c "from ai_router import ai_analyze; print(ai_analyze({'title':'test','content':'test security news'}))"

# Check scheduled cycle times (IST)
python -c "from backend.scheduler.scheduler import CYCLE_SLOTS, _DAILY_HOUR; print('Cycles:', CYCLE_SLOTS); print('Daily hour:', _DAILY_HOUR)"

# Clear all test data (from Python)
python -c "
import requests, json
resp = requests.post('http://localhost:7860/api/admin/testing/clear',
    headers={'X-CSRF-Token': 'skipped'},
    json={'target': 'all'},
    cookies={'jwt': '<your_jwt_cookie>'})
print(resp.json())
"
```

---

## VS Code Workspace Tips

Recommended extensions:
- **Python** (Microsoft)
- **Pylance** for IntelliSense
- **ESLint** for JSX linting
- **Prettier** for formatting
- **REST Client** for testing API endpoints (`.http` files)

Recommended `settings.json`:

```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "editor.formatOnSave": true,
  "python.analysis.extraPaths": ["."]
}
```

The `"python.analysis.extraPaths": ["."]` setting ensures Pylance finds the root-level shim modules (`jarvis_db.py`, `config.py`, etc.).
