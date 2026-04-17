# BATT Runtime Shield

The Behavior-Attested Trust Tier (BATT) shield enforces tool-grant authority at invocation time, based on the asset's current trust tier. It narrows or denies tool calls that would exceed what the tier permits — turning trust from paperwork into runtime policy.

## How it works

1. Before every tool invocation, a Claude Code `PreToolUse` hook calls `reagent shield check`.
2. The shield hashes the asset-in-scope, looks up its current trust tier from the attestation store, and consults the `TrustPolicy` for that tier.
3. The shield returns an allow/deny JSON decision back to Claude Code, which either proceeds or rejects the call.

Typical latency: one SQLite point lookup, under one millisecond on SSD.

## Trust tiers → runtime authority

| Tier | Allowed tools | Bash | External egress | File writes |
|---|---|---|---|---|
| `UNTRUSTED` | `Read`, `Grep`, `Glob` | ✗ | ✗ | ✗ |
| `REVIEWED` | declared tools | allowlist (`git`, `npm`, `python`, …) | ✓ | ✓ |
| `VERIFIED` | declared tools | allowlist | ✓ | ✓ |
| `NATIVE` | editor + Bash | ✓ (no prefix allowlist) | ✗ | ✓ |

`UNTRUSTED` is the default for any asset without a matching attestation record.

## CLI

```bash
# Check whether a proposed tool call would be allowed.
reagent shield check ./my-skill.md --tool Bash --args-json '{"command":"git status"}'

# Install the PreToolUse hook into .claude/hooks/ for the current repo.
reagent shield install --repo .

# Inspect the runtime authority granted by an asset's current tier.
reagent shield status ./my-skill.md
```

## Claude Code hook settings

After `reagent shield install`, add this snippet to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": {
      "command": ".claude/hooks/agentguard_shield_pretool.py"
    }
  }
}
```

The hook reads the PreToolUse event from stdin (Claude Code's standard hook protocol) and writes a one-line JSON decision to stdout.

## Relationship to the divergence detector

When runtime divergence detection (`reagent diverge check`) fires on a `VERIFIED` asset, the trust store demotes the asset before the next tool call. The shield reads the new tier at the next invocation, immediately narrowing the asset's authority. That closes the loop from runtime anomaly to runtime containment without a human in the loop — review happens after containment.

## Future extensions

- MCP middleware that wraps MCP tool discovery / invocation with the same policy check.
- Cursor extension and Codex/OpenCode integrations.
- Remote policy source backed by a DT-hosted endpoint so trust demotions propagate organization-wide within seconds.
