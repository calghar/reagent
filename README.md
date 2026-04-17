<!--markdownlint-disable MD033 -->
<h1 align="center">AgentGuard</h1>

<p align="center">
  <strong>Behavioral attestation and runtime shield for AI agent configuration assets.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.13+-blue.svg" alt="Python 3.13+"></a>
  <a href="docs/"><img src="https://img.shields.io/badge/docs-available-blue.svg" alt="Docs"></a>
</p>

---

AgentGuard attests the behavior of AI agent configuration assets (agents, skills, hooks, commands, rules), detects runtime divergence from the attested baseline, and enforces trust-tier-gated tool authority at invocation time. Three layers — config-time attestation, runtime divergence, and causal incident lineage — give security teams a signed baseline for every asset and auto-demote trust tiers when behavior diverges.

## Features

### Layer 1 — Config-time Attestation

- **Inventory & Catalog** — Scan and index agents, skills, hooks, commands, and rules into a content-hashed JSONL catalog
- **Static Analysis** — 25 security rules for prompt injection, exfiltration, and unsafe tool grants, each mapped to MITRE ATLAS and OWASP AST10 taxonomies (see `docs/threat-model.md`)
- **Behavioral Sandbox Replay (BSR)** — Drive the real Claude Code CLI in a mediated sandbox, capture a five-dimension `BehavioralFingerprint`, sign it with ed25519 (see `docs/attestation.md`)
- **Counterfactual Replay Gate (CRG)** — `agentguard counterfactual` replays proposed revisions through the sandbox and blocks merges when behavior expands beyond the attested baseline
- **Quality Scoring** — Per-asset quality metrics with configurable thresholds

### Layer 2 — Runtime Divergence & Shield

- **HLOT Telemetry** — `agentguard telemetry hlot` emits `agentguard.asset.*` attributes (content hash, fingerprint hash, trust tier) on every agent-session OTel span
- **Runtime Fingerprint Divergence Detection (RFDD)** — `agentguard diverge` flags new tool calls, new egress hosts, and new hook subprocess trees with MITRE ATLAS tagging
- **BATT Runtime Shield** — `agentguard shield` enforces trust-tier-gated tool authority at invocation time via a Claude Code `PreToolUse` hook (see `docs/shield.md`)
- **Trust Management** — 4-level trust model (UNTRUSTED/NATIVE/REVIEWED/VERIFIED) with auto-demotion on divergence

### Layer 3 — Supply-chain & CI

- **CI Pipeline** — `agentguard ci` exits with structured codes: 0 = pass, 1 = quality fail, 2 = security fail, 3 = behavioral divergence at merge time
- **Drift Detection** — Find stale file references in tracked assets
- **Snapshot & Rollback** — Content-addressed history with rollback to any prior version
- **Import Gates** — Security scanning on imported assets from URLs, gists, or local paths
- **Integrity Verification** — Detect post-merge tampering against the attested hash

## Installation

> **Requires Python 3.13+** and [uv](https://docs.astral.sh/uv/).

### From Source (recommended — package not yet on PyPI)

```bash
git clone https://github.com/calghar/agentguard.git
cd agentguard

# Core CLI only
uv sync

# With dev tools (tests, linters)
uv sync --extra dev
```

Then run:

```bash
uv run agentguard --help
```

### From PyPI (coming soon)

```bash
pip install agentguard
```

## Quick Start

```bash
# Scan a repo and build the asset catalog
agentguard inventory --repo .

# Static security scan
agentguard scan .claude

# Sign a behavioral fingerprint for an asset
agentguard attest sign .claude/agents/reviewer.md

# Check for stale file references
agentguard drift --repo .
```

## CLI Commands

<details>
<summary><strong>Asset Inventory</strong></summary>

| Command | Description |
| --- | --- |
| `inventory` | Scan repos and update the asset catalog |
| `catalog` | List all cataloged assets (filter with `--type`) |
| `show <id>` | Show detailed view of an asset |
| `harnesses` | List supported harness formats |
| `evaluate --repo <path>` | Compute quality scores for all assets |

</details>

<details>
<summary><strong>Security</strong></summary>

| Command | Description |
| --- | --- |
| `scan <path>` | Run security scanner on a file or directory |
| `audit --repo <path>` | Full security audit of a repo's `.claude/` |
| `import <source>` | Import an asset with security gates |
| `trust show <id>` | Show trust level and history |
| `trust promote <id>` | Promote an asset to a higher trust level |
| `integrity check` | Verify all tracked asset hashes |
| `history <id>` | Show snapshot timeline for an asset |
| `rollback <id> <snapshot>` | Restore an asset from a previous snapshot |

</details>

<details>
<summary><strong>Attestation &amp; Runtime Shield</strong></summary>

| Command | Description |
| --- | --- |
| `attest sign <path>` | Run BSR and sign the behavioral fingerprint |
| `attest verify <path>` | Verify an existing attestation |
| `counterfactual <old> <new>` | Replay a revision against the attested baseline |
| `diverge check` | Runtime divergence detection against attested fingerprints |
| `shield run` | BATT PreToolUse hook enforcing trust-tier tool authority |
| `telemetry hlot` | Emit HLOT OTel attributes for agent-session spans |

</details>

<details>
<summary><strong>CI &amp; Drift</strong></summary>

| Command | Description |
| --- | --- |
| `ci` | CI gate with exit codes 0/1/2/3 (pass / quality / security / behavioral) |
| `drift` | Detect stale file references in tracked assets |

</details>

## CI Integration

Run AgentGuard as a quality and security gate in any CI system:

```bash
agentguard ci --threshold 70 --mode check --security
```

**Exit codes:** `0` = pass, `1` = quality failure, `2` = security failure, `3` = behavioral divergence.

See the [CI Integration Guide](docs/ci-integration.md) for detailed setup instructions.

## How It Works

AgentGuard implements a three-layer governance loop:

1. **Config-time attestation** — Static scan (exit 2 on CRITICAL), Behavioral Sandbox Replay in the native harness, signed fingerprint bound to content hash, Counterfactual Replay Gate against recent sessions (exit 3 on divergence)
2. **Runtime divergence** — HLOT attributes on every OTel span, RFDD compares live behavior against the attested fingerprint on five dimensions, BATT Shield narrows tool grants at invocation time and auto-demotes trust tiers on divergence
3. **Causal lineage** — Incidents join across agent and application spans by content hash to identify blast radius and rollback candidates

## Documentation

Full documentation is available in the **[docs/](docs/)** directory.

| Guide | Description |
| --- | --- |
| [Getting Started](docs/getting-started.md) | Installation, setup, and first steps |
| [CLI Reference](docs/cli-reference.md) | Full command documentation with examples |
| [Configuration](docs/configuration.md) | Full configuration reference and environment variables |
| [Security Scanning](docs/security-scanning.md) | Security features, trust model, and scanning |
| [Evaluation](docs/evaluation.md) | Quality measurement and A/B testing |
| [CI Integration](docs/ci-integration.md) | Running AgentGuard in CI pipelines |
| [Comparison](docs/comparison.md) | How AgentGuard compares to related projects |

## Development

```bash
git clone https://github.com/calghar/agentguard.git
cd agentguard
uv sync --extra dev
```

Run the test suite and linters:

```bash
uv run pytest                    # tests
uv run ruff check src/ tests/    # linting
uv run ruff format --check src/  # formatting
uv run mypy src/                 # type checking
```

Pre-commit hooks are available:

```bash
uv run pre-commit install
```

## License

MIT — see [LICENSE](LICENSE).
