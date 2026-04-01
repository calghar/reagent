#!/usr/bin/env bash
# Reagent: log PostToolUse events to telemetry store.
# Reads JSON from stdin (tool_name, tool_input, tool_output).
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

# Extract tool name, sanitize input (shape only, no secrets)
TOOL_NAME=""
if [ -n "$INPUT" ]; then
  TOOL_NAME="$(printf '%s' "$INPUT" | grep -o '"tool_name":"[^"]*"' | head -1 | cut -d'"' -f4)"
fi
TOOL_NAME="${TOOL_NAME:-unknown}"

printf '{"event":"tool_use","session_id":"%s","tool":"%s","ts":"%s"}\n' \
  "$SESSION_ID" "$TOOL_NAME" "$TIMESTAMP" \
  >> "$TELEMETRY_DIR/tool-use.jsonl"

exit 0
