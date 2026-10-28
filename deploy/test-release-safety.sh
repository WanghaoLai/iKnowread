#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT_DIR/deploy/release-safety.sh"

before="$(printf '%s\n' 'CREATE TABLE t (id INT) AUTO_INCREMENT=4;' '20:a' | canonical_schema_fingerprint)"
same_schema="$(printf '%s\n' 'CREATE TABLE t (id INT) AUTO_INCREMENT=99;' '20:a' | canonical_schema_fingerprint)"
changed_schema="$(printf '%s\n' 'CREATE TABLE t (id BIGINT) AUTO_INCREMENT=99;' '20:a' | canonical_schema_fingerprint)"
advanced_ledger="$(printf '%s\n' 'CREATE TABLE t (id INT) AUTO_INCREMENT=99;' '20:a' '21:b' | canonical_schema_fingerprint)"

schema_state_allows_container_rollback "$before" "$same_schema"
if schema_state_allows_container_rollback "$before" "$changed_schema"; then
    echo '数据库结构改变后不应允许容器回滚。' >&2
    exit 1
fi
if schema_state_allows_container_rollback "$before" "$advanced_ledger"; then
    echo '数据库迁移推进后不应允许容器回滚。' >&2
    exit 1
fi
if schema_state_allows_container_rollback "$before" ''; then
    echo '数据库状态不可读取时不应允许容器回滚。' >&2
    exit 1
fi
if schema_state_allows_container_rollback '' "$same_schema"; then
    echo '缺少发布前指纹时不应允许容器回滚。' >&2
    exit 1
fi

echo 'release rollback safety check: PASS'
