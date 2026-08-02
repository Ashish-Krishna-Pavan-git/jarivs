# REST API Reference

The JARVIS backend exposes a REST API for authentication, intelligence feeds, report access, and system administration.

## Base URL

By default, the API is available at `http://localhost:7860`.

## Authentication

All protected endpoints require a JWT token passed in the `Authorization` header:

```http
Authorization: Bearer <jwt_token>
```

State-modifying requests (`POST`, `PUT`, `DELETE`) require a CSRF token header matching the `csrf_token` cookie:

```http
X-CSRF-Token: <csrf_token>
```

---

## Authentication Endpoints

### `POST /api/auth/login`
Authenticates user and returns JWT token and CSRF token.

**Request Body**:
```json
{
  "username": "admin",
  "password": "admin123!ChangeMe"
}
```

**Response**:
```json
{
  "token": "<jwt_string>",
  "csrf": "<csrf_string>",
  "user": {
    "id": 1,
    "username": "admin",
    "role": "admin",
    "display_name": "Administrator",
    "must_change_password": false,
    "active": 1
  }
}
```

### `GET /api/auth/me`
Returns current authenticated user details.

### `POST /api/auth/change-password`
Changes current user password. Requires `current_password` and `new_password` (minimum 12 characters).

---

## End-User Endpoints

### `GET /api/user/feed`
Returns recent intelligence articles.

**Query Parameters**:
- `hours` (int): Lookback period in hours (default 72, max 720).
- `severity` (str): Filter by severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
- `q` (str): Search term filter.

### `GET /api/user/reports`
Returns executive intelligence digest reports.

**Query Parameters**:
- `days` (int): Lookback range in days (default 30).

### `GET /api/user/reports/<report_id>/export`
Downloads a specific intelligence digest report.

**Query Parameters**:
- `format` (`markdown` | `json`): Export format (default `markdown`).

### `POST /api/user/assistant`
Queries the built-in AI intelligence assistant.

**Request Body**:
```json
{
  "query": "What critical CVEs were identified today?",
  "hours": 48
}
```

---

## Administration Control Endpoints

### `GET /api/admin/overview`
Returns high-level system metrics, telemetry, queue status, AI status, and source/user counts.

### `GET /api/admin/system/health`
Returns detailed system health, storage setup, and configuration status.

### `GET /api/admin/system/storage`
Returns file counts and byte sizes for all data storage paths.

### `GET /api/admin/logs`
Returns system event logs. Supports `level`, `component`, and `q` search parameters.

### `GET /api/admin/sources` & `POST /api/admin/sources`
List or create/update RSS feed sources.

### `DELETE /api/admin/sources/<source_id>`
Deletes a source feed.

### `GET /api/admin/models` & `POST /api/admin/models`
List or create/update AI model providers.

### `GET /api/admin/mcp` & `POST /api/admin/mcp`
List or create/update MCP server definitions.

### `POST /api/admin/mcp/<server_id>/test`
Tests connection handshake to an MCP server.

---

## Command Center / Testing Endpoints

### `GET /api/admin/testing/live-state`
Returns complete real-time diagnostics: pipeline status, queue, AI model status, telemetry, storage sizes, recent errors, and active component counts.

### `POST /api/admin/testing/pipeline-toggle`
Toggles global pipeline pause/resume state.

### `POST /api/admin/testing/run-collection`
Executes an immediate single collection cycle.

### `POST /api/admin/testing/run-ai-analysis`
Runs an AI analysis test on sample content or pending queue items.

### `POST /api/admin/testing/run-notification`
Tests all active Telegram and Slack notification channels.

### `POST /api/admin/testing/run-report`
Triggers digest report generation on demand.

### `POST /api/admin/testing/test-providers`
Tests connectivity and latency for all configured AI model providers.

### `POST /api/admin/testing/test-collectors`
Tests reachability and article yield for all configured RSS sources.

### `POST /api/admin/testing/test-mcp`
Tests MCP server transport connections.

### `POST /api/admin/testing/clear`
Clears targeted runtime data (`reports`, `logs`, `articles`, `cache`, or `clear_all_test_data`). Returns post-cleanup verification report.

### `POST /api/admin/testing/reset-scheduler`
Resets queue items and resets pipeline runtime state to idle.

### `POST /api/admin/testing/reload-config`
Reloads environment variables and database configurations.
