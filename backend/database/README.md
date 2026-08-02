# Backend Database Module

## Purpose
Manages the SQLite control plane database, connection pooling, table schemas, Fernet secret encryption, and transactional schema version migrations (v1 to v4).

## Contained Modules
- `jarvis_db.py`: Complete SQLite CRUD helpers, table definitions, and migration sequences.

## Dependencies
- `sqlite3`, `threading`, `backend.auth.security_utils`.

## Entry Points
- `init_db()`: Initializes tables and applies pending migrations.
- `ensure_admin_user()`: Guarantees active administrator user exists.
- `schema_status()`: Returns database schema version details.

## Important Files
- [`jarvis_db.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/backend/database/jarvis_db.py)
