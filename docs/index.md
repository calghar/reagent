# dtguard

A Dynatrace-aligned attestation and observability layer for AI-agent
configuration assets (skills, sub-agents, hooks, rules). Single Go
binary, distributed via Homebrew. Imports
[dtctl](https://github.com/dynatrace-oss/dtctl) packages directly so
auth, output, and the agent envelope are inherited rather than
reimplemented.

## What it does

dtguard fingerprints every asset by `content_hash =
sha256(asset_file_bytes)`, signs the fingerprint once Davis says its
behavior has stabilized, and surfaces drift through Dynatrace as DT
problems. The same `content_hash` is the join key at PR scan time, in
runtime spans, and on the signed record.

The product surface is **observability and attestation**.
Synchronous gating at the agent harness is opt-in.

## States

- **OBSERVED** — default. Spans flow into Dynatrace; Davis is
  learning the shape.
- **ATTESTED** — a signer (`human`, `davis`, or `policy`) produced a
  signed `Attestation`; Davis raises a problem on any drift.
- **REVOKED** — the asset is marked untrusted; Davis raises CRITICAL
  on any usage.

## Modes

| Mode | What runs at the agent | Use when |
|---|---|---|
| `observe` *(default)* | Nothing local. Spans -> Davis -> workflows. | Most of the time. |
| `alert` | Hook annotates "would-deny" on drift; tool still runs. | Richer DT signal without committing to gating. |
| `enforce` | PreToolUse hook denies tool calls outside the signed shape. | Regulated production. |

## Where to go next

- [Getting started](getting-started.md) — install, login, first scan.
- [Architecture](architecture.md) — Go package layout, lifecycle,
  dtctl alignment.
- [CLI reference](cli-reference.md) — full command surface.
- [Dynatrace integration](dt-integration.md) — DQL templates, Davis
  detectors, span attributes, distribution model.
- [Security](security.md) — threat model, scanner, attestation,
  shield (opt-in).
