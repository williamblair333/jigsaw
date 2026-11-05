#!/usr/bin/env bash
# Run a consumer's test suite against this Jigsaw checkout, before tagging a release.
# Usage: scripts/contract-test.sh [CONSUMER_REPO]   (default: the Parley checkout)
#
# Works in a throwaway worktree of the consumer's origin/main: installs its locked
# dependencies, swaps in this checkout of Jigsaw, and runs its tests. The consumer's own
# checkout, branch and venv are never touched. Exit status is the consumer's pytest status.
set -euo pipefail

consumer="${1:-/opt/proj/games/mtw2}"
jigsaw="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -d "$consumer/.git" ] && [ ! -f "$consumer/.git" ]; then
    echo "contract-test: no git checkout at $consumer (pass the consumer repo as the first argument)" >&2
    exit 2
fi

work="$(mktemp -d)"
cleanup() {
    git -C "$consumer" worktree remove --force "$work/consumer" >/dev/null 2>&1 || true
    rm -rf "$work"
}
trap cleanup EXIT

git -C "$consumer" fetch -q origin main
git -C "$consumer" worktree add -q --detach "$work/consumer" origin/main
cd "$work/consumer"

echo "contract-test: $(basename "$consumer") @ $(git rev-parse --short HEAD) against jigsaw @ $(git -C "$jigsaw" rev-parse --short HEAD)"
uv sync -q --locked
uv pip install -q --python .venv/bin/python --reinstall-package jigsaw "$jigsaw"
# Proof of which jigsaw is installed: a local install records a file:// URL, a pinned one a git URL.
uv run --no-sync python -c "from importlib.metadata import distribution as d; print('contract-test: jigsaw installed from', d('jigsaw').read_text('direct_url.json'))"
uv run --no-sync pytest -q
