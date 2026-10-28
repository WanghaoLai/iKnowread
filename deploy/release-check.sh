#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ $# -gt 0 ]]; then
    echo "用法: bash deploy/release-check.sh" >&2
    exit 64
fi

command -v docker >/dev/null 2>&1 || {
    echo "错误：未找到 docker。" >&2
    exit 1
}
docker info >/dev/null
docker compose version >/dev/null
docker scout version >/dev/null

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
export MYSQL_IMAGE_TAG=local
export DB_PASSWORD='release-check-db-password-not-for-production'
export MYSQL_ROOT_PASSWORD='release-check-root-password-not-for-production'
export AUTH_SECRET='release-check-auth-secret-not-for-production-0123456789'
export CRAWL4AI_API_TOKEN='release-check-crawler-token-not-for-production-0123456789'
export CRAWLER_ENABLED=true
export DOMAIN='localhost'
export ACME_EMAIL='release-check@example.invalid'
export VERIFY_ADMIN_PASSWORD='release-check-admin-password-not-for-production'

echo '[1/7] 校验 Compose 配置'
python3 fastapi-app/scripts/verify_delivery_manifest.py
bash deploy/test-release-safety.sh
docker compose --env-file /dev/null --profile web-import \
    -f compose.yaml -f deploy/compose.verify.yaml config --quiet
docker compose --env-file /dev/null --profile web-import -f compose.yaml config --format json \
    | python3 -c 'import json, sys; config = json.load(sys.stdin); app_tag, mysql_tag = sys.argv[1:]; services = config["services"]; assert services["db"]["image"] == f"iknowread-mysql:{mysql_tag}"; assert services["backend"]["image"] == f"iknowread-backend:{app_tag}"; assert services["web"]["image"] == f"iknowread-web:{app_tag}"; assert services["crawler"]["image"] == f"iknowread-crawler:{app_tag}"' \
        "$APP_TAG" "$MYSQL_IMAGE_TAG"
docker compose --env-file /dev/null --profile web-import \
    -f compose.yaml -f deploy/compose.verify.yaml config --format json \
    | python3 fastapi-app/scripts/verify_crawler_isolation.py

echo '[2/7] 构建四个生产镜像'
for service in db backend web crawler; do
    docker compose --env-file /dev/null --profile web-import build "$service"
done
for image in \
    "iknowread-mysql:${MYSQL_IMAGE_TAG}" \
    "iknowread-backend:${APP_TAG}" \
    "iknowread-web:${APP_TAG}" \
    "iknowread-crawler:${APP_TAG}"; do
    docker image inspect "$image" >/dev/null || {
        echo "构建后缺少本地镜像：${image}" >&2
        exit 1
    }
done

echo '[3/7] 在生产后端镜像中运行静态检查和回归测试'
docker run --rm \
    -e "AUTH_SECRET=${AUTH_SECRET}" \
    -e IKNOWREAD_ENV_FILE=/dev/null \
    -e DEBUG=false \
    -e ALLOW_REGISTRATION=false \
    -e DB_AUTO_CREATE=false \
    -e PIP_DISABLE_PIP_VERSION_CHECK=1 \
    -e PIP_CACHE_DIR=/tmp/pip-cache \
    -e XDG_CACHE_HOME=/tmp/check-cache \
    --mount "type=bind,src=${ROOT_DIR}/fastapi-app/app,dst=/source/app,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/fastapi-app/tests,dst=/source/tests,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/fastapi-app/scripts,dst=/source/scripts,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/fastapi-app/main.py,dst=/source/main.py,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/fastapi-app/pyproject.toml,dst=/source/pyproject.toml,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/fastapi-app/requirements.lock,dst=/source/requirements.lock,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/fastapi-app/requirements-dev.lock,dst=/source/requirements-dev.lock,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/src/api/apiContract.json,dst=/vue/src/api/apiContract.json,readonly" \
    "iknowread-backend:${APP_TAG}" \
    sh -eu -c 'test ! -e /source/.env && install -d /tmp/check-cache && python -m pip install --require-hashes --target /tmp/check-tools -r /source/requirements-dev.lock >/dev/null && export PYTHONPATH="/tmp/check-tools" COVERAGE_FILE="/tmp/iknowread.coverage" && cd /source && python scripts/document_contract.py --check && python -m ruff check --no-cache app tests scripts && python -m mypy --no-incremental && python -m pip_audit --cache-dir /tmp/check-cache/pip-audit --require-hashes --disable-pip -r requirements.lock && python -m coverage erase && python -m coverage run -m unittest discover -s tests -p "test_*.py" && python -m coverage report'

echo '[4/7] 使用锁文件执行前端静态检查、测试、生产依赖审计和构建'
docker run --rm \
    -e NO_UPDATE_NOTIFIER=1 \
    --workdir /workspace \
    --mount "type=bind,src=${ROOT_DIR}/vue/package.json,dst=/workspace/package.json,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/package-lock.json,dst=/workspace/package-lock.json,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/jsconfig.json,dst=/workspace/jsconfig.json,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/eslint.config.js,dst=/workspace/eslint.config.js,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/vite.config.mjs,dst=/workspace/vite.config.mjs,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/index.html,dst=/workspace/index.html,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/.env.production,dst=/workspace/.env.production,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/public,dst=/workspace/public,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/src,dst=/workspace/src,readonly" \
    --mount "type=bind,src=${ROOT_DIR}/vue/tests,dst=/workspace/tests,readonly" \
    node:24-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 \
    sh -eu -c 'npm ci && npm run check && test -z "$(find dist -type f -name "*.map" -print -quit)" && ! grep -R "sourceMappingURL=" dist && npm audit --omit=dev --audit-level=moderate && npm audit --audit-level=high'

echo '[5/7] 校验运行镜像中的关键二进制、真实 OCR 与 Caddy 配置'
docker run --rm \
    -e DOMAIN=localhost -e ACME_EMAIL=release-check@example.invalid \
    --entrypoint caddy "iknowread-web:${APP_TAG}" \
    validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker run --rm --entrypoint /bin/sh "iknowread-mysql:${MYSQL_IMAGE_TAG}" \
    -c 'test ! -e /usr/bin/mysqlsh && mysqld --version | grep -F "Ver 8.4.13 " && mysql --version && mysqldump --version'
docker run --rm --entrypoint /usr/local/bin/gosu "iknowread-mysql:${MYSQL_IMAGE_TAG}" --version
docker run --rm --entrypoint /bin/sh "iknowread-backend:${APP_TAG}" \
    -ec 'minimum="3.0.22-1~deb12u2"; for package in openssl libssl3; do version="$(dpkg-query -W "$package" | cut -f2)"; echo "$package $version"; dpkg --compare-versions "$version" ge "$minimum"; done'
docker run --rm --entrypoint python "iknowread-crawler:${APP_TAG}" \
    -c 'import importlib.metadata as metadata; expected = {"Crawl4AI": "0.9.4", "Brotli": "1.2.1", "pypdf": "6.21.2", "filelock": "4.2.1"}; assert all(metadata.version(package) == version for package, version in expected.items()), {package: metadata.version(package) for package in expected}'
docker run --rm --entrypoint /bin/sh "iknowread-crawler:${APP_TAG}" \
    -ec 'minimum="3.0.22-1~deb12u2"; for package in openssl libssl3; do version="$(dpkg-query -W "$package" | cut -f2)"; echo "$package $version"; dpkg --compare-versions "$version" ge "$minimum"; done'
docker run --rm --read-only \
    --tmpfs /tmp:size=256m,mode=1777 \
    -e PYTHONPATH=/app -e OCR_ENABLED=true -e OCR_LANGUAGES=chi_sim+eng \
    --mount "type=bind,src=${ROOT_DIR}/fastapi-app/scripts,dst=/checks,readonly" \
    --entrypoint python "iknowread-backend:${APP_TAG}" \
    /checks/ocr_runtime_check.py

echo '[6/7] 启动隔离栈并验证重启持久化、网关和数据库约束'
VERIFY_PROJECT="iknowread-release-check-$$"
COMPOSE_VERIFY=(
    docker compose --env-file /dev/null --profile web-import -p "$VERIFY_PROJECT"
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

echo '[7/7] 镜像漏洞检查（全部严重项可见；已有修复版本的严重项阻断发布）'
for image in backend web crawler; do
    echo "iknowread-${image}:${APP_TAG}：未修复的 Critical/High（报告，不静默忽略）"
    docker scout cves \
        --only-severity critical,high \
        --only-unfixed \
        --only-vuln-packages \
        --format only-packages \
        "local://iknowread-${image}:${APP_TAG}"
    echo "iknowread-${image}:${APP_TAG}：已有修复版本的 Critical/High（发布门禁）"
    docker scout cves --exit-code \
        --only-severity critical,high \
        --only-fixed \
        --only-vuln-packages \
        --format packages \
        "local://iknowread-${image}:${APP_TAG}"
done
echo "iknowread-mysql:${MYSQL_IMAGE_TAG}：未修复的 Critical/High（报告，不静默忽略）"
docker scout cves \
    --only-severity critical,high \
    --only-unfixed \
    --only-vuln-packages \
    --format only-packages \
    "local://iknowread-mysql:${MYSQL_IMAGE_TAG}"
echo "iknowread-mysql:${MYSQL_IMAGE_TAG}：已有修复版本的 Critical/High（发布门禁）"
docker scout cves --exit-code \
    --only-severity critical,high \
    --only-fixed \
    --only-vuln-packages \
    --format packages \
    "local://iknowread-mysql:${MYSQL_IMAGE_TAG}"

echo '发布前检查全部通过。'
