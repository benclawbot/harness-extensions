#!/usr/bin/env bash
# test-agent-hooks.sh — exercise the agent-hooks acceptance criteria.
# Note: NOT using `set -e`; each assertion calls pass/fail explicitly so
# that expected-failure assertions (verdict=block, exit=2) don't kill
# the script.
set -uo pipefail

EXT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AH="$EXT_DIR/agent-hooks/agent_hooks.py"
WORK="$(mktemp -d -t ah-test-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

pass() { printf "  \033[32m✓\033[0m %s\n" "$1"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$1"; exit 1; }

# Helper: run agent-hooks and capture verdict JSON. By default we
# suppress stderr (events JSON) since most assertions only need the
# verdict on stdout. Tests that want to inspect hook events should
# call `$AH` directly with `2>&1` instead.
run_ah() {
    local cwd="$1"; shift
    ( cd "$cwd" && "$AH" "$@" 2>/dev/null )
}

# Helper for tests that need to see hook events on stderr too.
run_ah_full() {
    local cwd="$1"; shift
    ( cd "$cwd" && "$AH" "$@" 2>&1 )
}

echo "[agent-hooks]"

# Acceptance #1: no hooks → no-op, verdict=allow.
verdict="$(run_ah "$WORK" run pre-tool bash)"
echo "$verdict" | jq -e '.verdict == "allow"' >/dev/null \
    && pass "no hooks → verdict=allow" \
    || fail "no hooks: expected allow, got $verdict"

# Acceptance #2: blocking pre-tool hook in cwd.
mkdir -p "$WORK/.mcode-hooks"
cat > "$WORK/.mcode-hooks/pre-tool.bash" <<'EOF'
#!/bin/bash
read -r payload
tool=$(echo "$payload" | python3 -c 'import sys,json; print(json.load(sys.stdin)["tool"])')
if [ "$tool" = "bash" ]; then
  echo "blocking bash calls" >&2
  exit 2
fi
exit 0
EOF
chmod +x "$WORK/.mcode-hooks/pre-tool.bash"
out="$(run_ah "$WORK" run pre-tool bash --arg 'rm -rf /')"
echo "$out" | jq -e '.verdict == "block"' >/dev/null \
    && pass "blocking hook → verdict=block" \
    || fail "blocking hook: expected block, got $out"

# Acceptance #3: HOOK_FAIL_OPEN turns errors into warnings.
cat > "$WORK/.mcode-hooks/pre-tool.read" <<'EOF'
#!/bin/bash
echo "flaky" >&2
exit 99
EOF
chmod +x "$WORK/.mcode-hooks/pre-tool.read"
out="$(HOOK_FAIL_OPEN=1 run_ah "$WORK" run pre-tool read)"
echo "$out" | jq -e '.verdict == "allow"' >/dev/null \
    && pass "HOOK_FAIL_OPEN=1 → flaky hook warned, not blocked" \
    || fail "HOOK_FAIL_OPEN=1: expected allow, got $out"

# Same setup without HOOK_FAIL_OPEN should block.
unset HOOK_FAIL_OPEN
out="$(run_ah "$WORK" run pre-tool read)"
echo "$out" | jq -e '.verdict == "block"' >/dev/null \
    && pass "default fail-closed → verdict=block on hook error" \
    || fail "default should block; got $out"

# Acceptance #4: post-tool hooks fire with the result payload.
cat > "$WORK/.mcode-hooks/post-tool.bash" <<'EOF'
#!/bin/bash
read -r payload
result=$(echo "$payload" | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"])')
echo "[post-tool.bash] result=$result"
exit 0
EOF
chmod +x "$WORK/.mcode-hooks/post-tool.bash"
out="$(run_ah "$WORK" run post-tool bash --result '{"exit":0,"stdout":"hi"}')"
echo "$out" | jq -e '.verdict == "allow"' >/dev/null \
    && pass "post-tool hook fires and allows" \
    || fail "post-tool hook: expected allow, got $out"
run_ah_full "$WORK" run post-tool bash --result '{"exit":0,"stdout":"hi"}' | grep -q "result={'exit': 0, 'stdout': 'hi'}" \
    && pass "post-tool hook sees the result payload" \
    || fail "post-tool hook did not see result"

# Extra: --log records structured events.
LOG="$WORK/hooks.jsonl"
"$AH" --log "$LOG" run pre-tool bash --arg 'rm' >/dev/null 2>&1 || true
[ -f "$LOG" ] && pass "--log wrote audit file" || fail "--log did not write file"

echo "[agent-hooks] all passed"
