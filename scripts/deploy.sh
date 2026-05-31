#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI is not installed." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not running or not reachable." >&2
  exit 1
fi

# Avoid local Docker credential-helper hangs on public image pulls/build metadata.
export DOCKER_CONFIG="${DOCKER_CONFIG:-/tmp/openclaw-docker-config}"
mkdir -p "$DOCKER_CONFIG/cli-plugins"
if [ -d "$HOME/.docker/cli-plugins" ]; then
  for plugin in "$HOME"/.docker/cli-plugins/*; do
    [ -e "$plugin" ] || continue
    ln -sfn "$plugin" "$DOCKER_CONFIG/cli-plugins/$(basename "$plugin")"
  done
fi

if [ ! -f .env.production ]; then
  echo "Missing .env.production. Copy .env.production.example and fill required secrets first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env.production
set +a

echo "[deploy] validating compose config"
docker compose -f docker-compose.prod.yml --env-file .env.production config >/dev/null

echo "[deploy] pulling base images"
docker pull pgvector/pgvector:pg16 || true
docker pull python:3.11-slim || true
docker pull node:22-alpine || true
docker pull nginx:1.27-alpine || true

echo "[deploy] building images"
DOCKER_BUILDKIT=0 docker build ./backend -t heritage-rag-kakao-api:local
DOCKER_BUILDKIT=0 docker build ./frontend -t heritage-rag-kakao-frontend:local

echo "[deploy] starting services"
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --no-build --remove-orphans

echo "[deploy] waiting for api health"
for i in {1..30}; do
  if curl -fsS "http://${API_BIND_HOST:-127.0.0.1}:${API_PORT:-8000}/health" >/dev/null 2>&1; then
    echo "[deploy] api is healthy"
    break
  fi
  sleep 2
done

if ! curl -fsS "http://${API_BIND_HOST:-127.0.0.1}:${API_PORT:-8000}/health" >/dev/null 2>&1; then
  echo "[deploy] api health check failed" >&2
  docker compose -f docker-compose.prod.yml --env-file .env.production logs --tail=120 api >&2
  exit 1
fi

echo "[deploy] waiting for frontend health"
for i in {1..30}; do
  if curl -fsS "http://${FRONTEND_BIND_HOST:-127.0.0.1}:${FRONTEND_PORT:-3001}/" >/dev/null 2>&1; then
    echo "[deploy] frontend is healthy"
    docker compose -f docker-compose.prod.yml --env-file .env.production ps
    exit 0
  fi
  sleep 2
done

echo "[deploy] frontend health check failed" >&2
docker compose -f docker-compose.prod.yml --env-file .env.production logs --tail=120 frontend >&2
exit 1
