# Environment Variables

## Security

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=
JWT_SECRET=<random-secret>
FLASK_SECRET_KEY=<random-secret>
JARVIS_ENCRYPTION_KEY=<fernet-key-or-long-secret>
```

Empty `ADMIN_PASSWORD` creates `admin / admin123!ChangeMe` and forces password change.

## Data

```env
JARVIS_DATA_DIR=/data
JARVIS_DB_PATH=/data/jarvis.db
JARVIS_LEGACY_DATA_DIR=/legacy/jarvis-data
```

## AI

```env
GEMINI_API_KEY=
GROQ_API_KEY=
OPENAI_API_KEY=
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=phi4-mini
```

## Notifications

```env
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=
SLACK_WEBHOOK_URL=
HF_SPACE_URL=
```

Notification channels can also be configured in the UI.
