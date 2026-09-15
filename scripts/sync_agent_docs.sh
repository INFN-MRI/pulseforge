#!/usr/bin/env bash
# Generate CLAUDE.md and GEMINI.md from AGENTS.md so the three cannot drift.
#
# With --check, verify they are current and fail if they are not; this is what
# CI runs. Without it, write them.
set -euo pipefail

cd "$(dirname "$0")/.."

SOURCE=AGENTS.md
TARGETS=(CLAUDE.md GEMINI.md)
BANNER="<!-- Generated from AGENTS.md by scripts/sync_agent_docs.sh. Do not edit. -->"

check=0
[[ "${1:-}" == "--check" ]] && check=1

status=0
for target in "${TARGETS[@]}"; do
    rendered="$(printf '%s\n\n' "$BANNER"; cat "$SOURCE")"
    if [[ $check -eq 1 ]]; then
        if [[ ! -f "$target" ]] || ! diff -q <(printf '%s' "$rendered") "$target" >/dev/null; then
            echo "$target is out of date; run scripts/sync_agent_docs.sh" >&2
            status=1
        fi
    else
        printf '%s' "$rendered" > "$target"
    fi
done
exit $status
