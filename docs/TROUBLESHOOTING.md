# Troubleshooting & FAQ

This guide addresses common error scenarios, diagnostic steps, and resolutions.

## Quick Diagnostic Checklist

1. Check **Command Center / Testing page** (`/admin/#testing`) for provider, collector, or MCP connectivity issues.
2. Check **Admin → Event Logs** (`/admin/#logs`) filtered by level `ERROR` or `WARN`.
3. Check system runtime status at `/health` and `/api/admin/system/health`.

---

## Common Issues & Solutions

### 1. Telegram Notifications Not Arriving / AI Degrading to Keyword Mode

**Symptom**:
Telegram messages fail to send or AI analysis falls back to basic keyword classification.

**Cause**:
Duplicate keys in `.env`. If a key is defined at the top with a real value and again at the bottom as `KEY=""`, `python-dotenv` overwrites the real credential with an empty string.

**Fix**:
Inspect `.env` and remove any duplicate empty re-declarations at the bottom. Ensure keys load as `SET`.

---

### 2. Reports Page Shows No Reports

**Symptom**:
The User Reports page (`/user/#reports`) is empty.

**Cause**:
No collection cycle has run yet, or AI synthesis failed without degraded mode fallback.

**Fix**:
1. Go to Admin → Testing Center (`/admin/#testing`).
2. Click **Run One Collection Cycle** or **Run Report Generation**.
3. Verify that digests appear under Reports. (JARVIS saves degraded mode reports if AI synthesis fails so reports are never missing).

---

### 3. Rate Limit Errors (HTTP 429 / Quota Exhausted)

**Symptom**:
Log shows `Groq 429 backoff` or `Gemini 429 backoff`.

**Cause**:
API rate limit thresholds hit on free or shared tier API keys.

**Fix**:
JARVIS automatically handles 429 backoffs with exponential retry logic and temporary provider blocking (`block_model_provider`). Configure secondary model providers (e.g. Groq or Ollama) under **Admin → Models** to allow automatic failover.

---

### 4. Database Schema or Integrity Errors

**Symptom**:
Error log mentions missing table columns or SQLite integrity error.

**Cause**:
Outdated database schema version.

**Fix**:
Restart the backend (`python app.py`). JARVIS automatically runs schema migrations up to version 4 on startup via `jarvis_db.init_db()`.
