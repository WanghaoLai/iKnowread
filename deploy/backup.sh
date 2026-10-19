#!/usr/bin/env bash
# Run on the Ubuntu host: sudo bash deploy/backup.sh
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/.."
if ! docker info >/dev/null 2>&1; then
  echo "当前用户无法访问 Docker daemon；请在具有 Docker 权限的账号下运行，或使用 sudo。" >&2
  exit 1
fi
mkdir -p runtime
exec 9>runtime/.backup.lock
if ! flock -n 9; then
  echo "已有备份任务正在运行，本次未执行。" >&2
  exit 1
fi
if [[ -z "$(docker compose ps --status running -q backend)" ]]; then
  echo "backend 未运行。请确认服务状态后再备份。" >&2
  exit 1
fi
backup_dir="backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
# Pause writers/OCR so the SQL dump and file snapshot belong together.
backend_stopped=false
restore_backend() {
  if [[ "$backend_stopped" == true ]]; then
    docker compose start backend >/dev/null || echo "严重：备份后端自动恢复失败，请立即检查服务。" >&2
  fi
}
trap restore_backend EXIT
docker compose stop backend
backend_stopped=true
docker compose exec -T db sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --no-tablespaces --set-gtid-purged=OFF --databases "$MYSQL_DATABASE"' \
  | gzip > "$backup_dir/database.sql.gz"
# Read the Docker-managed volume through the production image. The name inside
# the archive remains app-data/ so existing restore procedures stay compatible.
docker compose run --rm --no-deps -T --entrypoint python backend -c \
  'import sys, tarfile; archive = tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz"); archive.add("/app/data", arcname="app-data"); archive.close()' \
  > "$backup_dir/app-data.tar.gz"
tar -czf "$backup_dir/deployment.tar.gz" .env compose.yaml deploy .dockerignore
# Save matching source; frontend dependencies and build output are intentionally excluded.
tar --exclude='*/node_modules' --exclude='*/dist' --exclude='*/__pycache__' \
    --exclude='*/.venv' --exclude='*/venv' --exclude='fastapi-app/.env' \
    --exclude='fastapi-app/data' \
    -czf "$backup_dir/source.tar.gz" fastapi-app vue
(
  cd "$backup_dir"
  sha256sum *.gz > SHA256SUMS
)
docker compose start backend >/dev/null
for _attempt in $(seq 1 45); do
  health="$(docker inspect "$(docker compose ps -q backend)" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
  if [[ "$health" == "healthy" ]]; then
    backend_stopped=false
    break
  fi
  sleep 2
done
if [[ "$backend_stopped" == true ]]; then
  echo "备份文件已生成，但后端未在 90 秒内恢复健康；未标记为完整备份。" >&2
  exit 1
fi
if ! bash deploy/verify-backup.sh "$backup_dir"; then
  echo "备份归档已生成，但隔离恢复验证失败；未标记为完整备份。" >&2
  exit 1
fi
touch "$backup_dir/COMPLETE"
echo "备份完成：$backup_dir（含数据库、文件、AI 密钥、部署配置和源码；请下载到异地）"
