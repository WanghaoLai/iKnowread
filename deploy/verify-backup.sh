#!/usr/bin/env bash
# Restore a backup into an isolated, disposable MySQL instance and validate it.
set -Eeuo pipefail
umask 077

BACKUP_DIR="${1:-}"
MODE="${2:-}"
if [[ -z "$BACKUP_DIR" || ( -n "$MODE" && "$MODE" != "--archive-only" ) ]]; then
    echo "用法: bash deploy/verify-backup.sh BACKUP_DIR [--archive-only]" >&2
    exit 64
fi
BACKUP_DIR="$(cd "$BACKUP_DIR" && pwd)"

for file in database.sql.gz app-data.tar.gz deployment.tar.gz source.tar.gz SHA256SUMS; do
    test -f "$BACKUP_DIR/$file" || { echo "备份缺少 $file" >&2; exit 1; }
done

# Validate against the source saved with this backup, not the current checkout.
EXPECTED_MIGRATION_COUNT="$(tar -tzf "$BACKUP_DIR/source.tar.gz" | grep -Ec '^fastapi-app/app/migrations/v[0-9]{3}_[^/]+\.py$')"
test "$EXPECTED_MIGRATION_COUNT" -gt 0
(
    cd "$BACKUP_DIR"
    sha256sum -c SHA256SUMS
)
gzip -t "$BACKUP_DIR/database.sql.gz"
for archive in app-data.tar.gz deployment.tar.gz source.tar.gz; do
    tar -tzf "$BACKUP_DIR/$archive" >/dev/null
done

EXTRACT_DIR="$(mktemp -d)"
CONTAINER="iknowread-restore-check-$$"
cleanup() {
    if [[ "$MODE" != "--archive-only" ]]; then
        docker rm -fv "$CONTAINER" >/dev/null 2>&1 || true
    fi
    rm -rf "$EXTRACT_DIR"
}
trap cleanup EXIT
tar -xzf "$BACKUP_DIR/app-data.tar.gz" -C "$EXTRACT_DIR"
test -d "$EXTRACT_DIR/app-data"

if [[ "$MODE" == "--archive-only" ]]; then
    echo "backup-archive-check: PASS"
    exit 0
fi

command -v docker >/dev/null
docker info >/dev/null
IMAGE="$(docker compose config --images db)"
if [[ -z "$IMAGE" || "$IMAGE" == *$'\n'* ]]; then
    echo "无法确定当前数据库镜像。" >&2
    exit 1
fi
docker image inspect "$IMAGE" >/dev/null
docker run --rm -d --name "$CONTAINER" \
    --memory 600m \
    --memory-swap 900m \
    -e MYSQL_ROOT_PASSWORD=restore-check-password \
    "$IMAGE" >/dev/null
for _attempt in $(seq 1 60); do
    if docker exec "$CONTAINER" sh -c \
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -h127.0.0.1 -uroot -e "SELECT 1" >/dev/null 2>&1'; then
        break
    fi
    if [[ "$_attempt" == 60 ]]; then
        echo "临时 MySQL 未能在 120 秒内就绪" >&2
        exit 1
    fi
    sleep 2
done
gunzip -c "$BACKUP_DIR/database.sql.gz" | docker exec -i "$CONTAINER" sh -c \
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot'
docker exec "$CONTAINER" sh -c \
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -uroot iknowread -e \
    "SELECT COUNT(*) FROM schema_migration"' | grep -qx "$EXPECTED_MIGRATION_COUNT"
docker exec "$CONTAINER" sh -c \
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -N -uroot iknowread -e \
    "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN (\"account\",\"document\")"' \
    | grep -qx 2
echo "backup-restore-check: PASS"
