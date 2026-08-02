# Tests Directory

## Purpose
Contains automated unit and integration test suites executed with `pytest`.

## Contained Files
- `test_backend_api.py`: Automated backend REST API test suite, authentication tests, MCP mocks, SQLite migration tests, and Command Center maintenance data cleanup verification.

## Dependencies
- `pytest`, `requests`, `unittest.mock`.

## Entry Points
Run all tests:
```bash
python -m pytest -v
```
