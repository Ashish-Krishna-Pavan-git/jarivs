# Docker Deployment Guide

`docker compose up --build` builds the React frontend, copies it into the Flask backend image, starts the scheduler, and exposes the full app at `http://localhost:7860`.

Compose mounts:

- `jarvis_data:/data`
- `./jarvis-data:/legacy/jarvis-data:ro`

Health check:

```bash
curl http://localhost:7860/health
```

Logs:

```bash
docker logs -f jarvis-backend
```

Back up the volume before upgrades:

```bash
docker run --rm -v jarvis-agent_jarvis_data:/data -v "%cd%":/backup alpine tar czf /backup/jarvis-data-backup.tgz /data
```
