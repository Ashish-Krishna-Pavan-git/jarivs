# Admin Guide

## Daily operations

The Admin dashboard shows scheduler state, processing counts, configured sources, models, users, and legacy-data detection. Use Run Cycle only when you need an immediate collection; the scheduler remains responsible for normal recurring runs.

## Users and access

Admin -> Users creates `admin` and `user` accounts. New accounts receive a temporary password and must change it at first login. Passwords are stored with PBKDF2 hashing. Disable an account instead of deleting it when you need to retain audit context.

The first administrator is documented in [Installation](INSTALLATION.md). Change it before giving the service network access.

## Sources

Admin -> Sources controls the collector's RSS/web sources. Each enabled source has a name, URL, and category. The collector uses the database list when it is available, and falls back to the original curated source list if the database cannot be read.

## AI models and routing

Admin -> Models stores provider definitions for Gemini, Groq, Ollama, and OpenAI-compatible APIs. Set the key name, not the secret itself, in `API Key Env`; for example, `OPENAI_API_KEY`. Add the real key to `.env` or your deployment secret manager.

The router uses enabled providers configured for the requested task and preserves the original hard-coded provider fallbacks if no database route is usable. Rate-limit or quota failures are logged and temporarily blocked to prevent repeated failed calls.

## Integrations

Admin -> Integrations and Admin -> Telegram / Slack Integrations show notification configuration. Multiple Telegram IDs and Slack webhooks are supported. Secret fields are encrypted in SQLite using `JARVIS_ENCRYPTION_KEY`; do not change that key after creating channels unless you have migrated the encrypted values.

## MCP servers

Admin -> MCP adds HTTP JSON-RPC or STDIN/STDOUT servers. Test every server before enabling it in a user workflow. STDIO commands run inside the backend container, so package the executable in the image or use a command already present there.

## Storage, logs, and backups

Admin -> Storage shows the SQLite control-plane path, active data folders, legacy scan result, and sizes. Admin -> Logs supports level and text filtering. Admin -> Health exposes scheduler, queue, telemetry, Hugging Face persistence, and Telegram configuration state.

Back up both pieces of persistent data before upgrading:

1. The Docker `jarvis_data` volume (`/data` in the container).
2. The original host `jarvis-data/` directory, which JARVIS only reads.

See [Docker Deployment](DOCKER_DEPLOYMENT.md) and [Migration](MIGRATION.md) for commands and restoration guidance.
