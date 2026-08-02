# Configuration & Environment Variables

JARVIS is configured using environment variables specified in `.env` or passed via system process environment variables.

> **CRITICAL REPEAT-KEY WARNING**:
> `python-dotenv` uses the *LAST* occurrence of a key in `.env`. Ensure keys are declared ONCE. Duplicate empty declarations at the bottom of `.env` will overwrite valid top-level credentials with empty strings!

## Complete Environment Variable Reference

### Security & Authentication

| Variable | Description | Default | Required |
|---|---|---|---|
| `ADMIN_USERNAME` | Administrator username created on first run | `admin` | Yes |
| `ADMIN_PASSWORD` | Administrator initial password. If empty or default, password change is forced on first login | `admin123!ChangeMe` | Yes |
| `JWT_SECRET` | Secret key used to sign JWT session tokens | `jarvis-dev-secret` | Yes (in prod) |
| `FLASK_SECRET_KEY` | Flask session cookie secret | `jarvis-dev-secret` | Yes (in prod) |
| `JARVIS_ENCRYPTION_KEY` | Key used for Fernet encryption of integration credentials in database | `jarvis-dev-secret` | Yes (in prod) |

### Path & Database Configuration

| Variable | Description | Default |
|---|---|---|
| `JARVIS_DATA_DIR` | Root directory for file-system storage | `/tmp/jarvis/data` (Local) / `/data` (Docker) |
| `JARVIS_DB_PATH` | Full absolute file path to control plane SQLite database | `$JARVIS_DATA_DIR/jarvis.db` |
| `JARVIS_LEGACY_DATA_DIR` | Directory path for legacy historical data mount | `/legacy/jarvis-data` |

### AI Model Provider API Keys

| Variable | Description | Default |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini API Key | `""` |
| `GROQ_API_KEY` | Groq LLM Cloud API Key | `""` |
| `OPENAI_API_KEY` | OpenAI API Key (or OpenAI-compatible providers) | `""` |
| `OLLAMA_URL` | Ollama local endpoint base URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama default model name | `phi4-mini` |

### Notification Settings

| Variable | Description | Default |
|---|---|---|
| `TELEGRAM_TOKEN` | Telegram Bot API Token from @BotFather | `""` |
| `TELEGRAM_CHAT_ID` | Default Telegram Chat / Channel ID for notifications | `""` |
| `SLACK_WEBHOOK_URL` | Incoming Slack Webhook URL | `""` |

### Scheduler Configuration

| Variable | Description | Default |
|---|---|---|
| `DAILY_SUMMARY_HOUR` | IST Hour (0-23) for daily summary report execution | `7` (07:00 IST) |
| `HF_SPACE_URL` | Base URL of HuggingFace Space or hosting server (used for keep-alive pings) | `""` |
