#!/usr/bin/env bash
# Reagent: log Stop events (session end) to telemetry store.
# Installed as an async hook — must exit 0 always.
set -o pipefail

TELEMETRY_DIR="$HOME/.reagent/telemetry/$(date -u +%Y-%m)"
mkdir -p "$TELEMETRY_DIR"

SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

printf '{"event":"session_end","session_id":"%s","ts":"%s"}\n' \
  "$SESSION_ID" "$TIMESTAMP" \
  >> "$TELEMETRY_DIR/sessions.jsonl"

exit 0
