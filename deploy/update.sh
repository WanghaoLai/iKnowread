#!/usr/bin/env bash
# Update an existing Docker deployment with a backup, immutable application
# image tags, health-gated activation and schema-aware container rollback.
set -Eeuo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/deploy/release-safety.sh"

INCLUDE_DB=false
RELEASE_TAG_ARG=""
for argument in "$@"; do
    case "$argument" in
        --include-db)
            INCLUDE_DB=true
            ;;
        -*)
            echo "未知选项：${argument}" >&2
            echo "用法: bash deploy/update.sh [--include-db] [唯一版本标签]" >&2
            exit 64
            ;;
        *)
            if [[ -n "$RELEASE_TAG_ARG" ]]; then
                echo "只能指定一个版本标签。" >&2
                exit 64
            fi
            RELEASE_TAG_ARG="$argument"
            ;;
    esac
done

ENV_FILE="$ROOT_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "缺少 .env；已有服务器应保留原部署配置，不要重新生成密钥。" >&2
    exit 1
fi
command -v docker >/dev/null 2>&1 || { echo "未找到 docker。" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "未找到 python3。" >&2; exit 1; }
command -v flock >/dev/null 2>&1 || { echo "未找到 flock（Ubuntu 的 util-linux 包提供该命令）。" >&2; exit 1; }
docker info >/dev/null
docker compose version >/dev/null

mkdir -p runtime
exec 9>runtime/.update.lock
if ! flock -n 9; then
    echo "已有更新任务正在运行，本次未执行。" >&2
    exit 1
fi

read_env_value() {
    python3 - "$ENV_FILE" "$1" <<'PY'
from pathlib import Path
import sys

path, key = Path(sys.argv[1]), sys.argv[2]
value = ""
for raw in path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    current_key, current_value = line.split("=", 1)
    if current_key.strip() == key:
        value = current_value.strip()
print(value)
PY
}

set_release_tags() {
    python3 - "$ENV_FILE" "$1" "$2" <<'PY'
from pathlib import Path
import os
import sys
import tempfile

path = Path(sys.argv[1])
values = {"APP_TAG": sys.argv[2], "MYSQL_IMAGE_TAG": sys.argv[3]}
metadata = path.stat()
lines = path.read_text(encoding="utf-8").splitlines()
updated = set()
result = []
for line in lines:
    key = line.split("=", 1)[0].strip() if "=" in line else ""
    if key in values:
        result.append(f"{key}={values[key]}")
        updated.add(key)
    else:
        result.append(line)
for key, value in values.items():
    if key not in updated:
        result.append(f"{key}={value}")
fd, temporary = tempfile.mkstemp(prefix=".env.update-", dir=path.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write("\n".join(result) + "\n")
        output.flush()
        os.fsync(output.fileno())
    os.chmod(temporary, metadata.st_mode & 0o777)
    os.chown(temporary, metadata.st_uid, metadata.st_gid)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY
}

PREVIOUS_TAG="$(read_env_value APP_TAG)"
PREVIOUS_TAG="${PREVIOUS_TAG:-local}"
PREVIOUS_MYSQL_TAG="$(read_env_value MYSQL_IMAGE_TAG)"
PREVIOUS_MYSQL_TAG="${PREVIOUS_MYSQL_TAG:-local}"
GIT_REVISION="$(git rev-parse --short=12 HEAD 2>/dev/null || echo source)"
RELEASE_TAG="${RELEASE_TAG_ARG:-$(date -u +%Y%m%dT%H%M%SZ)-${GIT_REVISION}}"
if [[ ! "$RELEASE_TAG" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$ ]]; then
    echo "版本标签不合法：仅允许字母、数字、点、下划线和连字符。" >&2
    exit 64
fi
if [[ "$RELEASE_TAG" == "$PREVIOUS_TAG" ]]; then
    echo "新版本标签与当前版本相同，请使用唯一标签。" >&2
    exit 64
fi

CRAWLER_ENABLED="$(read_env_value CRAWLER_ENABLED)"
RELEASE_SERVICES=(backend web)
COMPOSE=(docker compose)
if [[ "$CRAWLER_ENABLED" == [Tt][Rr][Uu][Ee] ]]; then
    RELEASE_SERVICES+=(crawler)
    COMPOSE+=(--profile web-import)
fi
if [[ "$INCLUDE_DB" == true ]]; then
    RELEASE_SERVICES=(db "${RELEASE_SERVICES[@]}")
    TARGET_MYSQL_TAG="$RELEASE_TAG"
else
    TARGET_MYSQL_TAG="$PREVIOUS_MYSQL_TAG"
fi

schema_fingerprint() {
    "${COMPOSE[@]}" exec -T db sh -ec '
        MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot \
            --no-data --skip-comments --compact "$MYSQL_DATABASE"
        printf "\n-- migration-ledger --\n"
        MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$MYSQL_DATABASE" -NBe \
            "SELECT CONCAT_WS(CHAR(58), version, name, COALESCE(checksum, CHAR(45))) FROM schema_migration ORDER BY version"
    ' | canonical_schema_fingerprint
}

service_image_name() {
    if [[ "$1" == db ]]; then
        printf 'iknowread-mysql'
    else
        printf 'iknowread-%s' "$1"
    fi
}

for service in "${RELEASE_SERVICES[@]}"; do
    image="$(service_image_name "$service"):${RELEASE_TAG}"
    if docker image inspect "$image" >/dev/null 2>&1; then
        echo "版本标签已存在：${image}。请使用新标签，避免覆盖不可变发布镜像。" >&2
        exit 64
    fi
done

# Preserve the exact images used by the running containers. APP_TAG may be a
# mutable legacy tag (usually "local") that no longer points at those images.
ROLLBACK_TAG="rollback-$(date -u +%Y%m%dT%H%M%SZ)-$$"
web_running_image_id=""
for service in "${RELEASE_SERVICES[@]}"; do
    container_id="$("${COMPOSE[@]}" ps --status running -q "$service")"
    if [[ -z "$container_id" ]]; then
        echo "${service} 当前未运行，无法创建可信回滚点。" >&2
        exit 1
    fi
    running_image_id="$(docker inspect --format '{{.Image}}' "$container_id")"
    if [[ "$service" == web ]]; then
        web_running_image_id="$running_image_id"
    fi
    docker image tag "$running_image_id" "$(service_image_name "$service"):${ROLLBACK_TAG}"
done
if [[ "$CRAWLER_ENABLED" == [Tt][Rr][Uu][Ee] ]]; then
    gateway_container_id="$("${COMPOSE[@]}" ps --status running -q crawler-gateway)"
    if [[ -z "$gateway_container_id" ]]; then
        echo "crawler-gateway 当前未运行，无法创建可信回滚点。" >&2
        exit 1
    fi
    gateway_image_id="$(docker inspect --format '{{.Image}}' "$gateway_container_id")"
    if [[ "$gateway_image_id" != "$web_running_image_id" ]]; then
        echo "web 与 crawler-gateway 未运行同一镜像，拒绝以单一标签覆盖不一致的回滚状态。" >&2
        exit 1
    fi
fi

MYSQL_IMAGE_TAG="$PREVIOUS_MYSQL_TAG"
export MYSQL_IMAGE_TAG
if [[ "$INCLUDE_DB" == false ]]; then
    docker image inspect "iknowread-mysql:${MYSQL_IMAGE_TAG}" >/dev/null || {
        echo "缺少现有数据库镜像 iknowread-mysql:${MYSQL_IMAGE_TAG}；请先确认当前部署完整。" >&2
        exit 1
    }
fi

echo "[1/5] 校验 Compose 配置"
APP_TAG="$RELEASE_TAG" MYSQL_IMAGE_TAG="$TARGET_MYSQL_TAG" "${COMPOSE[@]}" config --quiet

if [[ "$INCLUDE_DB" == true ]]; then
    echo "[2/5] 构建版本化应用和 MySQL 镜像"
else
    echo "[2/5] 构建版本化应用镜像（MySQL 不随普通更新重启）"
fi
APP_TAG="$RELEASE_TAG" MYSQL_IMAGE_TAG="$TARGET_MYSQL_TAG" \
    "${COMPOSE[@]}" build "${RELEASE_SERVICES[@]}"

echo "[3/5] 创建并验证一致性备份"
bash deploy/backup.sh

PREVIOUS_SCHEMA_FINGERPRINT="$(schema_fingerprint)"
if [[ -z "$PREVIOUS_SCHEMA_FINGERPRINT" ]]; then
    echo "无法取得发布前数据库迁移指纹，拒绝激活新版本。" >&2
    exit 1
fi

ENV_UPDATED=false
rollback() {
    status=$?
    trap - ERR INT TERM
    if [[ "$ENV_UPDATED" == true ]]; then
        current_schema_fingerprint="$(schema_fingerprint 2>/dev/null || true)"
        if schema_state_allows_container_rollback \
            "$PREVIOUS_SCHEMA_FINGERPRINT" "$current_schema_fingerprint"; then
            echo "新版未通过健康检查且数据库未迁移，恢复容器快照 ${ROLLBACK_TAG}。" >&2
            if [[ "$INCLUDE_DB" == true ]]; then
                rollback_mysql_tag="$ROLLBACK_TAG"
            else
                rollback_mysql_tag="$PREVIOUS_MYSQL_TAG"
            fi
            set_release_tags "$ROLLBACK_TAG" "$rollback_mysql_tag"
            APP_TAG="$ROLLBACK_TAG" MYSQL_IMAGE_TAG="$rollback_mysql_tag" \
                "${COMPOSE[@]}" up -d --wait --wait-timeout 300 --remove-orphans || \
                echo "严重：自动回滚未恢复健康，请立即检查容器并使用最新 COMPLETE 备份。" >&2
        else
            echo "严重：数据库迁移状态已改变或无法确认，拒绝让旧镜像连接未知结构。" >&2
            echo "新版本标签和 COMPLETE 备份均已保留；请前向修复，或隔离服务后从本次备份恢复。" >&2
        fi
    fi
    exit "$status"
}
trap rollback ERR INT TERM

echo "[4/5] 激活 ${RELEASE_TAG} 并等待全部健康检查"
set_release_tags "$RELEASE_TAG" "$TARGET_MYSQL_TAG"
ENV_UPDATED=true
APP_TAG="$RELEASE_TAG" MYSQL_IMAGE_TAG="$TARGET_MYSQL_TAG" \
    "${COMPOSE[@]}" up -d --wait --wait-timeout 300 --remove-orphans

echo "[5/5] 核对运行容器"
APP_TAG="$RELEASE_TAG" MYSQL_IMAGE_TAG="$TARGET_MYSQL_TAG" "${COMPOSE[@]}" ps
ENV_UPDATED=false
trap - ERR INT TERM

echo "更新完成：${PREVIOUS_TAG} -> ${RELEASE_TAG}"
if [[ "$INCLUDE_DB" == true ]]; then
    echo "MySQL 镜像已更新：${PREVIOUS_MYSQL_TAG} -> ${TARGET_MYSQL_TAG}"
fi
echo "已保留回滚镜像 ${ROLLBACK_TAG} 和本次 COMPLETE 备份；确认稳定后再按运维策略清理旧镜像。"
