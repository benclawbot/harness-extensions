#!/usr/bin/env bash
# run-all.sh — run every test in tests/ and report pass/fail.
set -uo pipefail

EXT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

fail=0
for t in "$EXT_DIR"/tests/test-*.sh; do
    if bash "$t"; then
        :
    else
        fail=$((fail + 1))
    fi
    echo
done

if [ "$fail" -gt 0 ]; then
    echo "FAIL: $fail test(s) failed"
    exit 1
fi
echo "PASS: all suites green"
