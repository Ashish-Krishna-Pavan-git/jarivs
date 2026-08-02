# Troubleshooting

## The page does not open

Check the container and the health endpoint:

```bash
docker compose ps
curl http://localhost:7860/health
docker compose logs --tail=150 backend
```

`frontend: true` in `/health` means the React production build is being served. Rebuild after frontend changes with `docker compose up --build`.

## I cannot sign in

On a fresh install with empty `ADMIN_PASSWORD`, use `admin / admin123!ChangeMe`. The default user is created only once, so changing `.env` later does not overwrite an existing administrator. Use the database backup or an existing admin account to recover an established installation.

Keep `JWT_SECRET` stable between container restarts. Changing it signs out existing browser sessions.

## Password change is rejected

Enter the correct current password and a new password with at least 12 characters. This check applies to the first forced password change as well as later password changes.

## A manual cycle does not produce feed items

Open Admin -> Logs and Admin -> Health. Common causes are unreachable feeds, missing AI credentials, an unavailable local Ollama server, or provider quota limits. The original scheduler pipeline still writes items under `/data/processed` and reports under `/data/daily`.

## Telegram or Slack does not send

For Telegram, confirm `TELEGRAM_TOKEN` is set and the bot has received `/start` from the desired chat. A bot can be polled by only one active process. For Slack, confirm the Incoming Webhook URL is correct and the channel is enabled. Inspect Admin -> Logs for notifier errors.

## MCP test fails

HTTP MCP endpoints must accept JSON-RPC over POST. STDIO commands must exist inside the backend container, read one JSON-RPC line from standard input, and return a JSON response line before the configured timeout. Private-network HTTP targets are blocked by default as a security measure.

## Legacy data is not visible

Check that the repository has a `jarvis-data/` folder and that Docker mounted it:

```bash
docker compose exec backend ls -la /legacy/jarvis-data
```

JARVIS scans `articles_bundle.json`, dated digest files, telemetry, runtime state, seen IDs, and subscribers. It does not modify any legacy file. See [Migration](MIGRATION.md).

## Resetting a local test install

Do not delete a production volume to troubleshoot. For a disposable local test only, stop the stack and remove its named volume, then start again. Back up `/data` and `jarvis-data/` first for any real deployment.
