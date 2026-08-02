# Docker & Container Orchestration

JARVIS provides containerization files under `docker/` and root configuration wrappers.

## Files
- `docker/Dockerfile`: Multi-stage container build specification.
- `docker/docker-compose.yml`: Multi-container stack configuration.

## Commands

Building and running via Docker Compose:

```bash
docker compose up --build -d
```

Viewing logs:

```bash
docker compose logs -f
```
