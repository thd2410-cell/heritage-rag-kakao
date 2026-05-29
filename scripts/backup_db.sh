#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env.production ]; then
  echo "Missing .env.production." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env.production
set +a

mkdir -p data/backups
stamp="$(date +%Y%m%d-%H%M%S)"
out="data/backups/heritage_rag-${stamp}.dump"

docker compose -f docker-compose.prod.yml --env-file .env.production exec -T db \
  pg_dump -U "${POSTGRES_USER:-heritage}" -d "${POSTGRES_DB:-heritage_rag}" -Fc > "$out"

echo "backup written: $out"
