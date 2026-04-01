#!/usr/bin/env bash
# Reagent: check for quality regressions after session stops.
# Calls reagent check-regression with session context.
# Installed as an async hook — must exit 0 always.
set -o pipefail

SESSION_ID="${CLAUDE_SESSION_ID:-unknown}"
CWD="${CLAUDE_CWD:-.}"

# Only check if reagent is available
if ! command -v reagent &>/dev/null; then
  exit 0
fi

reagent check-regression "$SESSION_ID" --repo "$CWD" 2>/dev/null || true

exit 0
