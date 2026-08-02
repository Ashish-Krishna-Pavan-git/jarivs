FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/vite.config.js frontend/index.html ./
COPY frontend/src ./src
RUN npm install && npm run build

FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
RUN mkdir -p /data/processed /data/daily /data/archive /data/logs /data/raw_articles /legacy
ENV JARVIS_DATA_DIR=/data \
    JARVIS_DB_PATH=/data/jarvis.db \
    JARVIS_LEGACY_DATA_DIR=/legacy/jarvis-data \
    PYTHONUNBUFFERED=1
EXPOSE 7860
VOLUME ["/data"]
HEALTHCHECK --interval=60s --timeout=10s --retries=3 CMD curl -fsS http://localhost:7860/health || exit 1
CMD ["python", "app.py"]
