#!/usr/bin/env bash

# Normalize non-structural counters before hashing a schema dump plus its
# migration ledger.  MySQL includes the next AUTO_INCREMENT value in DDL even
# though inserts do not change application/schema compatibility.
canonical_schema_fingerprint() {
    python3 -c 'import hashlib, re, sys
payload = sys.stdin.buffer.read()
payload = re.sub(rb"AUTO_INCREMENT=[0-9]+", b"AUTO_INCREMENT=<ignored>", payload)
print(hashlib.sha256(payload).hexdigest())'
}

# Old application images may be restarted only when the database structure and
# migration ledger are proven identical to the state they were running against.
schema_state_allows_container_rollback() {
    if [[ $# -ne 2 ]]; then
        return 64
    fi
    local previous="$1"
    local current="$2"
    [[ -n "$previous" && -n "$current" && "$previous" == "$current" ]]
}
