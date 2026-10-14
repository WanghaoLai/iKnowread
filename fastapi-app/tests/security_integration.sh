#!/usr/bin/env bash
set -euo pipefail

base_url="${IKNOWREAD_TEST_URL:-http://127.0.0.1:9090}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${IKNOWREAD_TEST_USER:?请设置 IKNOWREAD_TEST_USER}"
: "${IKNOWREAD_TEST_USER_PASSWORD:?请设置 IKNOWREAD_TEST_USER_PASSWORD}"
: "${IKNOWREAD_TEST_ADMIN:?请设置 IKNOWREAD_TEST_ADMIN}"
: "${IKNOWREAD_TEST_ADMIN_PASSWORD:?请设置 IKNOWREAD_TEST_ADMIN_PASSWORD}"
user_cookie="$(mktemp)"
admin_cookie="$(mktemp)"
trap 'rm -f "$user_cookie" "$admin_cookie"' EXIT

status="$(curl -sS -o /dev/null -w '%{http_code}' "$base_url/document/selectPage")"
test "$status" = "401"

read -r user_captcha_id user_captcha_code < <(
  curl -sS "$base_url/captcha" | python3 "$script_dir/captcha_solver.py"
)
user_login="$(curl -sS -c "$user_cookie" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$IKNOWREAD_TEST_USER\",\"password\":\"$IKNOWREAD_TEST_USER_PASSWORD\",\"role\":\"user\",\"captcha_id\":\"$user_captcha_id\",\"captcha_code\":\"$user_captcha_code\"}" "$base_url/login")"
grep -q '"code":"200"' <<<"$user_login"
if grep -q '"password"' <<<"$user_login"; then
  echo "login response leaked password" >&2
  exit 1
fi

user_docs="$(curl -sS -b "$user_cookie" "$base_url/document/selectPage?pageNum=1&pageSize=10")"
grep -q '"code":"200"' <<<"$user_docs"
doc_id="$(sed -n 's/.*"id":\([0-9][0-9]*\).*/\1/p' <<<"$user_docs" | head -1)"
test -n "$doc_id"

status="$(curl -sS -b "$user_cookie" -o /dev/null -w '%{http_code}' "$base_url/document/download/$doc_id")"
test "$status" = "200"
status="$(curl -sS -b "$user_cookie" -o /dev/null -w '%{http_code}' "$base_url/accounts?role=user")"
test "$status" = "403"
status="$(curl -sS -b "$user_cookie" -o /dev/null -w '%{http_code}' "$base_url/files/download/admin/1/1.png")"
test "$status" = "403"

read -r admin_captcha_id admin_captcha_code < <(
  curl -sS "$base_url/captcha" | python3 "$script_dir/captcha_solver.py"
)
admin_login="$(curl -sS -c "$admin_cookie" -H 'Content-Type: application/json' \
  -d "{\"username\":\"$IKNOWREAD_TEST_ADMIN\",\"password\":\"$IKNOWREAD_TEST_ADMIN_PASSWORD\",\"role\":\"admin\",\"captcha_id\":\"$admin_captcha_id\",\"captcha_code\":\"$admin_captcha_code\"}" "$base_url/login")"
grep -q '"code":"200"' <<<"$admin_login"
if grep -q '"password"' <<<"$admin_login"; then
  echo "admin login response leaked password" >&2
  exit 1
fi

admin_users="$(curl -sS -b "$admin_cookie" "$base_url/accounts?role=user&pageNum=1&pageSize=10")"
grep -q '"code":"200"' <<<"$admin_users"
if grep -q '"password"' <<<"$admin_users"; then
  echo "account list leaked password" >&2
  exit 1
fi

status="$(curl -sS -b "$user_cookie" -o /dev/null -w '%{http_code}' \
  -H 'Content-Type: application/json' \
  -X PUT -d '{"name":"123","role":"admin"}' "$base_url/accounts/3")"
test "$status" = "422"

curl -sS -b "$user_cookie" -c "$user_cookie" -X POST "$base_url/logout" >/dev/null
status="$(curl -sS -b "$user_cookie" -o /dev/null -w '%{http_code}' "$base_url/document/selectPage")"
test "$status" = "401"

echo "security-integration: PASS"
