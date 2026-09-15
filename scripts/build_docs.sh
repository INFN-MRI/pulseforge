#!/usr/bin/env bash
# Render the figures, then build the HTML documentation. Any Sphinx warning
# fails the build.
set -euo pipefail
shopt -s nullglob

cd "$(dirname "$0")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"

for script in docs/_figures/*.py; do
    "$PYTHON_BIN" "$script"
done

"$PYTHON_BIN" -m sphinx -W --keep-going -b html docs docs/build/html
