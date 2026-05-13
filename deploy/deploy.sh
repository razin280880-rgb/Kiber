#!/usr/bin/env bash
# Скрипт обновления igrovan-trial на сервере.
#
# Использование:
#   ssh user@server
#   cd /opt/igrovan-trial
#   ./deploy/deploy.sh
#
# Что делает:
#   1) git pull (если используешь git) ИЛИ напоминает что код надо подтянуть rsync'ом
#   2) docker compose build --no-cache web (новый образ)
#   3) docker compose up -d (web + worker, zero-downtime благодаря restart policy)
#   4) docker image prune -f (чистит старые слои)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.prod.yml"

cd "$PROJECT_DIR"

echo "==> Project: $PROJECT_DIR"

# 1. Подтянуть код
if [ -d ".git" ]; then
    echo "==> git pull"
    git pull --ff-only
else
    echo "WARNING: not a git repo. Sync code manually (rsync/scp) before re-running."
fi

# 2. Проверить .env
if [ ! -f ".env" ]; then
    echo "ERROR: .env not found. Copy from deploy/.env.prod.example and fill in."
    exit 1
fi

# 3. Пересобрать образ
echo "==> docker compose build"
docker compose -f "$COMPOSE_FILE" build

# 4. Перезапустить контейнеры
echo "==> docker compose up -d"
docker compose -f "$COMPOSE_FILE" up -d

# 5. Чистка старых образов
echo "==> docker image prune"
docker image prune -f

echo ""
echo "==> Done. Status:"
docker compose -f "$COMPOSE_FILE" ps
echo ""
echo "==> Tail logs:"
echo "   docker compose -f $COMPOSE_FILE logs -f"
