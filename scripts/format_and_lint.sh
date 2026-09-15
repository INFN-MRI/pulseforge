#!/usr/bin/env bash
# One entry point for formatting and linting, run by pre-commit, by CI (with
# --check) and by hand. Keeping the rules here means a commit cannot pass
# locally and fail in CI on style.
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
check=0
[[ "${1:-}" == "--check" ]] && check=1

if [[ $check -eq 1 ]]; then
    "$PYTHON_BIN" -m ruff format --check .
    "$PYTHON_BIN" -m ruff check .
    bash scripts/sync_agent_docs.sh --check
else
    "$PYTHON_BIN" -m ruff format .
    "$PYTHON_BIN" -m ruff check --fix .
    bash scripts/sync_agent_docs.sh
fi
