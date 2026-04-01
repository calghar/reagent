#!/usr/bin/env bash
# Reagent: log SubagentStart/SubagentStop events to telemetry store.
# Installed as an async hook — must exit 0 always.
set -o pipefail

TELEMETRY_DIR="$HOME/.reagent/telemetry/$(date -u +%Y-%m)"
mkdir -p "$TELEMETRY_DIR"

SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Read hook payload from stdin
INPUT=""
if ! [ -t 0 ]; then
  INPUT="$(cat)"
fi

EVENT_TYPE="${1:-agent_event}"

printf '{"event":"%s","session_id":"%s","ts":"%s"}\n' \
  "$EVENT_TYPE" "$SESSION_ID" "$TIMESTAMP" \
  >> "$TELEMETRY_DIR/agents.jsonl"

exit 0
