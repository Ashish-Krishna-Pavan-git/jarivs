# Testing Suite & Verification

JARVIS includes automated unit testing, integration tests, frontend verification, and an interactive administrative Testing & Command Center.

## Automated Backend Unit Tests

Automated backend unit tests are written with `pytest`.

### Running Tests Locally

```bash
python -m pytest -v
```

### Test Suite Structure ([`tests/test_backend_api.py`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/tests/test_backend_api.py))

- `setup_clean_db` (Autouse Fixture): Sets up a completely isolated, temporary SQLite database and environment per test function.
- `test_login_forces_password_change_then_allows_admin`: Verifies authentication flow, password change enforcement, and report loading.
- `test_sources_models_channels_and_encryption`: Verifies creation of sources, model providers, Fernet credential encryption, and notification channels.
- `test_mcp_stdio_mock`: Verifies STDIO transport handshake with a mock python process.
- `test_mcp_http_mock`: Verifies HTTP JSON-RPC transport handling with a mocked endpoint.
- `test_legacy_summary_endpoint_available`: Tests legacy data bridge endpoint compatibility.
- `test_startup_migrates_legacy_database_and_preserves_auth_data`: Verifies transactional SQLite migration path from v1 schema to current v4 schema.
- `test_testing_center_endpoints`: Tests live state telemetry, pipeline pause/resume toggle, provider testing, collector testing, AI analysis, and scheduler reset endpoints.

---

## Frontend Build Verification

To verify that the React/Vite single-page application builds without warnings or syntax errors:

```bash
cd frontend
npm run build
```

This transforms modules and outputs static files to `frontend/dist/`.
