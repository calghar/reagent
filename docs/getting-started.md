# Getting Started

Install dtguard, authenticate to your Dynatrace tenant, and walk one
asset through the **observe -> propose -> sign** lifecycle.

## Install

```bash
brew install dynatrace-oss/tap/dtguard            # preferred
go install github.com/dynatrace-oss/dtguard@latest # alternative
dtguard --help
```

Requirements:

- A Dynatrace tenant (URL + SSO or API token).
- An OTel path from where the agent runs to your tenant (OneAgent or
  OTLP exporter).
- [dtctl](https://github.com/dynatrace-oss/dtctl) installed and
  logged in. dtguard inherits dtctl's active context.

## One-time setup

```bash
dtctl auth login                                    # via dtctl
dtguard config use-context default
dtguard doctor                                      # auth + tenant + OTel reachable
```

Configuration lives at `~/.config/dtguard/` (Linux) or
`~/Library/Application Support/dtguard/` (macOS), matching dtctl's
layout. Safety levels and env vars: see
[architecture.md](architecture.md#configuration).

## Walk one asset through the lifecycle

```bash
# 1. Index assets in the repo. Each asset enters OBSERVED state.
dtguard get assets --refresh

# 2. Use the agent normally. Every tool call emits HLOT-tagged spans.
#    See dt-integration.md for the DQL templates and Davis detectors.

# 3. Wait for Davis. Once the stability detector sees enough calls
#    with a stable shape, Davis emits a Proposal.
dtguard get proposals

# 4. Sign. The signer's ed25519 key produces an Attestation.
#    State moves to ATTESTED; Davis now raises on any drift.
dtguard sign <proposal-id>

# 5. Inspect.
dtguard describe attestation docs-helper --include shape
```

## Optional: enforcement

For a synchronous gate at the agent harness (deny tool calls that
don't match the signed shape):

```bash
dtguard shield install
```

This adds a PreToolUse hook and a SessionStart sync hook to
`.claude/settings.json`. The hook reads from a local SQLite cache at
`~/.dtguard/dtguard.db`, refreshed by `dtguard sync`. Most
deployments stop at observe + Davis; see [security.md](security.md)
for when enforcement is worth the operational cost.
