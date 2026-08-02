# Contributing Guidelines

Thank you for contributing to JARVIS!

## Contribution Workflow

1. **Keep Code Modular**: Place new modules in appropriate `backend/` subpackages (`api/`, `auth/`, `collectors/`, `ai/`, `scheduler/`, `notifications/`, `reports/`, `database/`, `storage/`, `services/`, `utils/`, `config/`).
2. **Preserve Shims**: Maintain backward-compatible shims for root entry points if public interface signatures change.
3. **Run Verification**: Ensure `npm run build` in `frontend/` and `python -m pytest` pass with 0 errors.
4. **Update Documentation**: Update relevant markdown files under `docs/` and log work in `WORKLOG.md`.
