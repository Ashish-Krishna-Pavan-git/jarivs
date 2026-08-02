# Backend API Module

## Purpose
Provides control plane REST API routes, request validation, authentication middleware, and administrative testing endpoints.

## Contained Modules
- `app.py`: Central Flask application instance, endpoint definitions, security headers, and static bundle server.

## Dependencies
- `Flask`, `PyJWT`, `cryptography`, `jarvis_db`, `security_utils`, `ai_router`.

## Entry Points
- `GET /api/admin/overview`: System telemetry.
- `GET /api/admin/testing/live-state`: Real-time diagnostic state.
- `POST /api/admin/testing/clear`: Maintenance data cleanup.

## Important Files
- [`app.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/app.py): Complete REST controller.
