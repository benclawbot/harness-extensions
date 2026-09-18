#!/usr/bin/env bash
# test-agents-md.sh — exercise the agents-md acceptance criteria.
set -uo pipefail

EXT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AG="$EXT_DIR/agents-md/agents_md.py"
WORK="$(mktemp -d -t am-test-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

pass() { printf "  \033[32m✓\033[0m %s\n" "$1"; }
fail() { printf "  \033[31m✗\033[0m %s\n" "$1"; exit 1; }

echo "[agents-md]"

# Acceptance #1: nested files, deepest first.
mkdir -p "$WORK/repo/sub"
printf 'ROOT\n' > "$WORK/repo/AGENTS.md"
printf 'SUB OVERRIDE\n' > "$WORK/repo/sub/AGENTS.md"
out="$("$AG" --cwd "$WORK/repo/sub" collect)"
echo "$out" | grep -q "SUB OVERRIDE" \
    && echo "$out" | grep -q "ROOT" \
    || fail "collect missing one of the files"
sub_pos="$(echo "$out" | grep -n 'SUB OVERRIDE' | head -1 | cut -d: -f1)"
root_pos="$(echo "$out" | grep -n 'ROOT' | head -1 | cut -d: -f1)"
[ "$sub_pos" -lt "$root_pos" ] \
    && pass "deepest file appears first (sub=$sub_pos < root=$root_pos)" \
    || fail "ordering wrong: sub=$sub_pos root=$root_pos"

# Acceptance #2: CLAUDE.md with @AGENTS.md bridge expands.
printf 'ROOT FROM AGENTS\n' > "$WORK/repo/AGENTS.md"
printf 'CLAUDE imports: @AGENTS.md\n\nUse prettier.\n' > "$WORK/repo/CLAUDE.md"
out="$("$AG" --cwd "$WORK/repo" collect)"
echo "$out" | grep -q "ROOT FROM AGENTS" || fail "bridge did not expand"
echo "$out" | grep -q "Use prettier" || fail "bridge lost surrounding CLAUDE.md content"
card="$(cd "$WORK/repo" && "$AG" card)"
echo "$card" | jq -e '.bridge_expansions | length > 0' >/dev/null \
    && pass "card reports bridge expansion" \
    || fail "card did not record bridge expansion"

# Acceptance #3: empty directory returns next_steps.
mkdir -p "$WORK/empty"
card="$(cd "$WORK/empty" && "$AG" card)"
echo "$card" | jq -e '.loaded | length == 0' >/dev/null \
    && pass "empty dir: loaded=[]" \
    || fail "empty dir should report loaded=[]"
echo "$card" | jq -e '.next_steps | length > 0' >/dev/null \
    && pass "empty dir: next_steps present" \
    || fail "empty dir should include next_steps"

# Acceptance #4: card is stable JSON on the same tree.
mkdir -p "$WORK/stable"
printf 'X\n' > "$WORK/stable/AGENTS.md"
c1="$(cd "$WORK/stable" && "$AG" card)"
c2="$(cd "$WORK/stable" && "$AG" card)"
[ "$c1" = "$c2" ] && pass "card is byte-identical on repeat runs" || fail "card drifted"

# Extra: init scaffold.
rm -f "$WORK/init-target/AGENTS.md" 2>/dev/null || true
mkdir -p "$WORK/init-target"
"$AG" --cwd "$WORK/init-target" init
[ -f "$WORK/init-target/AGENTS.md" ] && pass "init writes AGENTS.md" || fail "init did not write file"

echo "[agents-md] all passed"
