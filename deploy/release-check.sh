#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SCAN_IMAGES=false
if [[ $# -eq 1 && "${1:-}" == "--scan" ]]; then
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
if [[ -n "$TARGET_PLATFORM" ]]; then
    case "$TARGET_PLATFORM" in
        linux/amd64|linux/arm64) ;;
        *)
            echo "错误：TARGET_PLATFORM 只支持 linux/amd64 或 linux/arm64。" >&2
            exit 64
            ;;
    esac
    export DOCKER_DEFAULT_PLATFORM="$TARGET_PLATFORM"
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

echo '[1/7] 校验 Compose 配置'
docker compose --env-file /dev/null \
    -f compose.yaml -f deploy/compose.verify.yaml config --quiet

echo '[2/7] 构建三个生产镜像'
for service in db backend web; do
    docker compose --env-file /dev/null build "$service"
done

echo '[3/7] 在生产后端镜像中运行静态检查和回归测试'
docker run --rm \
    -e "AUTH_SECRET=${AUTH_SECRET}" \
    -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
    --mount "type=bind,src=${ROOT_DIR}/fastapi-app/tests,dst=/app/tests,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/fastapi-app,dst=/source,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/src/api/documentContract.json,dst=/vue/src/api/documentContract.json,readonly" \
    "iknowread-backend:${APP_TAG}" \
    sh -eu -c 'python -m pip install --target /tmp/check-tools -r /source/requirements-dev.lock >/dev/null && export PATH="/tmp/check-tools/bin:$PATH" && cd /source && ruff check --no-cache app tests scripts && cd /app && python -m unittest discover -s tests -p "test_*.py"'

echo '[4/7] 使用锁文件执行前端静态检查、测试、生产依赖审计和构建'
docker run --rm \
    -e NO_UPDATE_NOTIFIER=1 \
    --workdir /workspace \
    --mount "type=bind,src=${ROOT_DIR}/vue/package.json,dst=/workspace/package.json,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/package-lock.json,dst=/workspace/package-lock.json,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/eslint.config.js,dst=/workspace/eslint.config.js,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/vite.config.mjs,dst=/workspace/vite.config.mjs,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/index.html,dst=/workspace/index.html,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/.env.production,dst=/workspace/.env.production,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/public,dst=/workspace/public,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/src,dst=/workspace/src,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/tests,dst=/workspace/tests,readonly" \
    node:24-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 \
    sh -eu -c 'npm ci && npm run check && npm audit --omit=dev'

echo '[5/7] 校验运行镜像中的关键二进制、真实 OCR 与 Caddy 配置'
docker run --rm \
    -e DOMAIN=localhost -e ACME_EMAIL=release-check@example.invalid \
    --entrypoint caddy "iknowread-web:${APP_TAG}" \
    validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker run --rm --entrypoint /bin/sh "iknowread-mysql:${APP_TAG}" \
    -c 'test ! -e /usr/bin/mysqlsh && mysqld --version && mysql --version && mysqldump --version'
docker run --rm --entrypoint /usr/local/bin/gosu "iknowread-mysql:${APP_TAG}" --version
docker run --rm --read-only \
    --tmpfs /tmp:size=256m,mode=1777 \
    -e PYTHONPATH=/app -e OCR_ENABLED=true -e OCR_LANGUAGES=chi_sim+eng \
    --mount "type=bind,src=${ROOT_DIR}/fastapi-app/scripts,dst=/checks,readonly" \
    --entrypoint python "iknowread-backend:${APP_TAG}" \
    /checks/ocr_runtime_check.py

echo '[6/7] 启动隔离栈并验证重启持久化、网关和数据库约束'
VERIFY_PROJECT="iknowread-release-check-$$"
COMPOSE_VERIFY=(
    docker compose --env-file /dev/null -p "$VERIFY_PROJECT"
    -f compose.yaml -f deploy/compose.verify.yaml
)
cleanup_verify_stack() {
    "${COMPOSE_VERIFY[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup_verify_stack EXIT
"${COMPOSE_VERIFY[@]}" up -d --wait --wait-timeout 240
WEB_CONTAINER="$("${COMPOSE_VERIFY[@]}" ps -q web)"
test -n "$WEB_CONTAINER"
run_smoke() {
    docker run --rm \
        --network "container:${WEB_CONTAINER}" \
        -e "IKNOWREAD_TEST_ADMIN=admin" \
        -e "IKNOWREAD_TEST_ADMIN_PASSWORD=${VERIFY_ADMIN_PASSWORD}" \
        --mount "type=bind,src=${ROOT_DIR}/fastapi-app/scripts,dst=/app/scripts,readonly" \
        --mount "type=bind,src=${ROOT_DIR}/vue/src/api/documentContract.json,dst=/vue/src/api/documentContract.json,readonly" \
        "iknowread-backend:${APP_TAG}" \
        python /app/scripts/docker_smoke_check.py "$1" \
            --base-url https://localhost --insecure
}
run_smoke seed
"${COMPOSE_VERIFY[@]}" restart backend
"${COMPOSE_VERIFY[@]}" up -d --wait --wait-timeout 240
run_smoke verify
docker run --rm \
    --network "${VERIFY_PROJECT}_data" \
    -e "AUTH_SECRET=${AUTH_SECRET}" \
    -e DB_HOST=db -e DB_PORT=3306 -e DB_USER=iknowread \
    -e "DB_PASSWORD=${DB_PASSWORD}" -e DB_DATABASE=iknowread \
    --mount "type=bind,src=${ROOT_DIR}/fastapi-app/scripts,dst=/app/scripts,readonly" \
    "iknowread-backend:${APP_TAG}" \
    python /app/scripts/database_security_check.py
cleanup_verify_stack
trap - EXIT

echo '[7/7] 镜像漏洞门禁'
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
