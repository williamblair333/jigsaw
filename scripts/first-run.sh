#!/bin/sh
# PRODUCT.md's verify block, step for step: a stranger's first run in a clean container.
# Run from the repo root. Exits non-zero, naming the failed check, if any expectation fails.
set -eu

uv sync
out="$(uv run examples/quickstart.py /tmp/jigsaw/decisions.db)"
printf '%s\n' "$out"

fail=0
for want in \
    "Final: farm, decided at rung 2" \
    "#2 turn 2 recruit: archers at rung 7 (close call" \
    "1 of 2 decisions needed a model"
do
    case "$out" in
        *"$want"*) echo "first-run: ok: output contains \"$want\"" ;;
        *) echo "first-run: FAIL: output lacks \"$want\"" >&2; fail=1 ;;
    esac
done
if [ -f /tmp/jigsaw/decisions.db ]; then
    echo "first-run: ok: /tmp/jigsaw/decisions.db exists"
else
    echo "first-run: FAIL: /tmp/jigsaw/decisions.db was not written" >&2; fail=1
fi
exit "$fail"
