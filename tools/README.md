# Tools Directory

## Purpose
Diagnostic scripts and operational verification tools for developer and administrator maintenance.

## Contained Files
- `health_check.py`: System diagnostic tool checking database migration status, schema version, and runtime state.

## Dependencies
- `backend.database.jarvis_db`, `backend.services.runtime_state`.

## Entry Points
```bash
python tools/health_check.py
```
