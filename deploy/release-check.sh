#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SCAN_IMAGES=false
if [[ "${1:-}" == "--scan" ]]; then
    SCAN_IMAGES=true
elif [[ $# -gt 0 ]]; then
    echo "用法: bash deploy/release-check.sh [--scan]" >&2
    exit 64
fi

command -v docker >/dev/null 2>&1 || {
    echo "错误：未找到 docker。" >&2
    exit 1
}
docker info >/dev/null
docker compose version >/dev/null

TARGET_PLATFORM="${TARGET_PLATFORM:-}"
RUN_PLATFORM_ARGS=()
if [[ -n "$TARGET_PLATFORM" ]]; then
    case "$TARGET_PLATFORM" in
        linux/amd64|linux/arm64) ;;
        *)
            echo "错误：TARGET_PLATFORM 只支持 linux/amd64 或 linux/arm64。" >&2
            exit 64
            ;;
    esac
    export DOCKER_DEFAULT_PLATFORM="$TARGET_PLATFORM"
    RUN_PLATFORM_ARGS=(--platform "$TARGET_PLATFORM")
    echo "目标镜像平台：$TARGET_PLATFORM"
fi

# These values exist only to exercise Compose interpolation. They are not used
# to start services and must never be replaced with production credentials.
export APP_TAG=local
export DB_PASSWORD='release-check-db-password-not-for-production'
export MYSQL_ROOT_PASSWORD='release-check-root-password-not-for-production'
export AUTH_SECRET='release-check-auth-secret-not-for-production-0123456789'
export DOMAIN='localhost'
export ACME_EMAIL='release-check@example.invalid'
export VERIFY_ADMIN_PASSWORD='release-check-admin-password-not-for-production'

echo '[1/6] 校验 Compose 配置'
docker compose --env-file /dev/null \
    -f compose.yaml -f deploy/compose.verify.yaml config --quiet

echo '[2/6] 构建三个生产镜像'
for service in db backend web; do
    docker compose --env-file /dev/null build "$service"
done

echo '[3/6] 在生产后端镜像中运行回归测试'
docker run --rm "${RUN_PLATFORM_ARGS[@]}" \
    --mount "type=bind,src=${ROOT_DIR}/fastapi-app/tests,dst=/app/tests,readonly" \
    "iknowread-backend:${APP_TAG}" \
    python -m unittest discover -s tests -p 'test_*.py'

echo '[4/6] 使用锁文件执行前端安装、生产依赖审计和构建'
docker run --rm "${RUN_PLATFORM_ARGS[@]}" \
    --mount "type=bind,src=${ROOT_DIR}/vue,dst=/source,readonly" \
    node:24-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 \
    sh -eu -c 'cp -R /source /tmp/vue && cd /tmp/vue && npm ci && npm audit --omit=dev && npm run build'

echo '[5/6] 校验运行镜像中的关键二进制与 Caddy 配置'
docker run --rm "${RUN_PLATFORM_ARGS[@]}" \
    -e DOMAIN=localhost -e ACME_EMAIL=release-check@example.invalid \
    --entrypoint caddy "iknowread-web:${APP_TAG}" \
    validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker run --rm "${RUN_PLATFORM_ARGS[@]}" --entrypoint /bin/sh "iknowread-mysql:${APP_TAG}" \
    -c 'test ! -e /usr/bin/mysqlsh && mysqld --version && mysql --version && mysqldump --version'
docker run --rm "${RUN_PLATFORM_ARGS[@]}" --entrypoint /usr/local/bin/gosu "iknowread-mysql:${APP_TAG}" --version

echo '[6/6] 镜像漏洞门禁'
if [[ "$SCAN_IMAGES" == true ]]; then
    docker scout version >/dev/null
    for image in backend web mysql; do
        docker scout cves --exit-code \
            --only-severity critical,high \
            --only-fixed \
            --format packages \
            "local://iknowread-${image}:${APP_TAG}"
    done
else
    echo '已跳过 Docker Scout；正式发布前请使用 --scan 再运行一次。'
fi

echo '发布前检查全部通过。'
