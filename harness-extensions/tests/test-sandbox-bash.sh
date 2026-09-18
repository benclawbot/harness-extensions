#!/usr/bin/env bash
# test-sandbox-bash.sh — exercise the sandbox-bash acceptance criteria.
# Note: NOT using `set -e`; each assertion calls pass/fail explicitly so
# that expected-failure assertions don't kill the script.
set -uo pipefail

EXT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SB="$EXT_DIR/sandbox-bash/sandbox_bash.py"
WORK="$(mktemp -d -t sb-test-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

pass() { printf "  \033[32m✓\033[0m %s\n" "$1"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$1"; exit 1; }

echo "[sandbox-bash]"

# Acceptance #1: basic echo works.
out="$("$SB" --cwd "$WORK" echo hello)"
[ "$out" = "hello" ] && pass "echo hello → hello" || fail "echo hello → $out"

# Acceptance #2: / is read-only, can't write to /etc.
if "$SB" --cwd "$WORK" sh -c 'echo hi > /etc/test' 2>/dev/null; then
    fail "wrote to /etc/test under read-only / (sandbox is leaky)"
fi
pass "/etc/test write blocked under strict profile"

# Acceptance #3: /tmp is writable private.
"$SB" --cwd "$WORK" sh -c 'echo ok > /tmp/x && cat /tmp/x' >/dev/null
pass "/tmp writable inside sandbox"

# Acceptance #4: network off by default.
if "$SB" --cwd "$WORK" sh -c 'curl -sS --max-time 1 https://example.invalid' 2>/dev/null; then
    fail "curl reached example.invalid under strict profile"
fi
pass "curl blocked under strict profile (no network)"

# Acceptance #5: --allow-net lifts the network block.
code=0
"$SB" --cwd "$WORK" --allow-net sh -c 'curl -sS --max-time 3 -o /dev/null -w "%{http_code}\n" https://example.com' > "$WORK/curl.out" || code=$?
[ "$code" = "0" ] || fail "--allow-net curl failed (exit $code)"
[ "$(cat "$WORK/curl.out")" = "200" ] && pass "--allow-net: example.com → 200" || fail "got $(cat "$WORK/curl.out")"

# Acceptance #6: audit log JSON line.
LOG="$WORK/audit.jsonl"
"$SB" --cwd "$WORK" --log "$LOG" sh -c 'exit 7' >/dev/null 2>&1 || true
[ -f "$LOG" ] || fail "audit log not created"
[ "$(jq -r '.exit' "$LOG")" = "7" ] && pass "audit log records exit=7" || fail "audit log exit wrong"
[ "$(jq -r '.tool' "$LOG")" = "sandbox-bash" ] && pass "audit log records tool=sandbox-bash" || fail "audit log tool wrong"

# Extra: cwd under /home (not /tmp) works too.
"$SB" --cwd "$HOME" sh -c 'pwd; touch /tmp/y && echo ok' >/dev/null
pass "cwd under /home works (no /tmp remap needed)"

echo "[sandbox-bash] all passed"
