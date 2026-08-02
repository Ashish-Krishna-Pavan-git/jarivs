# API Reference

Write APIs require `Authorization: Bearer <token>` and `X-CSRF-Token: <csrf>`.

## Auth

- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/change-password`

## Admin

- `GET /api/admin/overview`
- `GET /api/admin/system/storage`
- `GET /api/admin/system/health`
- `GET /api/admin/migrations` - legacy scan, migration history, SQLite schema version, columns, indexes, and foreign keys
- `GET /api/admin/logs`
- `GET|POST /api/admin/sources`
- `DELETE /api/admin/sources/<id>`
- `GET|POST /api/admin/models`
- `GET|POST /api/admin/users`
- `PUT /api/admin/users/<id>`
- `GET|POST /api/admin/notification-channels`
- `DELETE /api/admin/notification-channels/<id>`
- `GET|POST /api/admin/mcp`
- `POST /api/admin/mcp/<id>/test`
- `POST /api/admin/run/cycle`
- `POST /api/admin/run/daily`

## User

- `GET /api/user/status`
- `GET /api/user/feed`
- `GET /api/user/reports`
- `POST /api/user/assistant`
- `GET|POST /api/user/preferences`
- `GET|POST /api/user/notification-channels`

## MCP

`POST /api/mcp/http`

```json
{"server_id":1,"method":"initialize","params":{}}
```
