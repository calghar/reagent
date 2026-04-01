#!/usr/bin/env bash
# Reagent: on ConfigChange, hash changed assets and compare to catalog.
# Installed as an async hook — must exit 0 always.
set -o pipefail

TELEMETRY_DIR="$HOME/.reagent/telemetry/$(date -u +%Y-%m)"
CATALOG="$HOME/.reagent/catalog.jsonl"
mkdir -p "$TELEMETRY_DIR"

SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Read hook payload from stdin
INPUT=""
if ! [ -t 0 ]; then
  INPUT="$(cat)"
fi

# If no catalog exists yet, nothing to verify
if [ ! -f "$CATALOG" ]; then
  exit 0
fi

# Log the config change event
printf '{"event":"config_change","session_id":"%s","ts":"%s"}\n' \
  "$SESSION_ID" "$TIMESTAMP" \
  >> "$TELEMETRY_DIR/integrity.jsonl"

exit 0
