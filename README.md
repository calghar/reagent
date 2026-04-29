<!--markdownlint-disable MD033 -->
<h1 align="center">dtguard</h1>

<p align="center">
  <strong>Dynatrace-aligned attestation and observability for AI-agent configuration assets.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License: Apache 2.0"></a>
  <a href="https://go.dev/dl/"><img src="https://img.shields.io/badge/go-1.23+-00ADD8.svg" alt="Go 1.23+"></a>
  <a href="docs/"><img src="https://img.shields.io/badge/docs-available-blue.svg" alt="Docs"></a>
</p>

---

dtguard fingerprints AI-agent configuration assets (skills, sub-agents,
hooks, rules) by `content_hash`, signs the fingerprint once behavior
has stabilized, and surfaces drift through Dynatrace Davis as DT
problems. The asset's `content_hash` is the identity that survives
from PR scan through runtime span through signed record.

The product surface is **observability and attestation**. Synchronous
gating at the agent harness is opt-in.

## Why this exists

Static scanners read the file at PR time. LLM-observability platforms
collect spans at runtime. Nothing joins the two and makes the asset's
behavior an attested, DT-queryable resource keyed by a stable identity.
dtguard is that join.

## How it works

Three states, keyed by `content_hash`:

- **OBSERVED** *(default)* — spans flow into Dynatrace, Davis is
  learning the shape.
- **ATTESTED** — a signer (`human`, `davis`, or `policy`) has
  produced a signed `Attestation`; Davis raises a problem on any
  span outside the signed shape.
- **REVOKED** — asset is marked untrusted; Davis raises CRITICAL on
  any usage.

Three opt-in modes:

| Mode | What runs at the agent | Use when |
|---|---|---|
| `observe` *(default)* | Nothing local. Spans -> Davis -> workflows. | Most of the time. |
| `alert` | Hook annotates "would-deny" on drift; tool still runs. | Richer DT signal without committing to gating. |
| `enforce` | PreToolUse hook denies tool calls outside the signed shape. | Regulated production. |

## Install

```bash
brew install dynatrace-oss/tap/dtguard          # preferred
go install github.com/dynatrace-oss/dtguard@latest   # alternative
```

dtguard relies on [dtctl](https://github.com/dynatrace-oss/dtctl) for
authentication. Install it once and `dtctl auth login`; dtguard
inherits the active context.

## Quick start

```bash
dtctl auth login                      # authenticate via dtctl
dtguard doctor                        # verify auth, DT reachability, OTel
dtguard scan ./.claude/skills         # static scan (25 rules)
dtguard get attestations              # list attested assets
dtguard apply -f attestation.yaml     # sign and apply
```

See [docs/getting-started.md](docs/getting-started.md) for the full
walkthrough.

## Architecture

Single Go binary. dtguard imports
[dtctl](https://github.com/dynatrace-oss/dtctl) Go packages
(`pkg/auth`, `pkg/config`, `pkg/output`, `pkg/safety`, `pkg/aidetect`)
directly so authentication, output rendering, safety levels, and the
`--agent` envelope are inherited rather than reimplemented.

| Surface | Where it lands in DT |
|---|---|
| HLOT-tagged spans | DT trace store |
| 5 DQL templates | Bundled, paste into Notebooks |
| 2 Davis detector configs | Anomaly Detection app |
| Resources (Attestation, Proposal, ...) | DT Documents API |

See [docs/architecture.md](docs/architecture.md) for the package
layout.

## License

Apache 2.0. See [LICENSE](LICENSE).
