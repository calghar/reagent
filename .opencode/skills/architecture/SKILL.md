---
name: architecture
description: >-
  dtguard architecture reference. Load when making design decisions,
  implementing new packages, or reviewing architectural alignment. Captures
  package boundaries, dtctl alignment constraints, and key conventions.
---
# dtguard Architecture Reference

Quick reference. Full prose in [docs/architecture.md](../../docs/architecture.md).

## What It Is

dtguard is a Dynatrace-aligned attestation and observability layer for
AI-agent configuration assets. Single Go binary, distributed via
Homebrew. Imports dtctl Go packages (`pkg/auth`, `pkg/output`,
`pkg/safety`, `pkg/config`, `pkg/aidetect`) directly so auth, output,
and the agent envelope are inherited rather than reimplemented.

The product surface is **observe + sign + Davis signal**. Enforcement
at the agent harness is opt-in.

## Repository Layout

```
cmd/dtguard/main.go             # 5-line Cobra entry, delegates to internal/cli
internal/
  attestation/                  # signing, verification, canonical-json payload
  auth/                         # wraps dtctl/pkg/auth + pkg/config
  cli/                          # Cobra command tree
    cmd/                        # top-level domain verbs (scan, sign, revoke, ci, ...)
  dt/                           # DT Documents/Settings API client (net/http)
  hlot/                         # span-attribute schema and emission
  output/                       # wraps dtctl/pkg/output, agent envelope formatter
  resources/                    # registry + per-kind handlers
    asset/, attestation/, proposal/, provenance/, revocation/, finding/, floor/
  scanner/                      # 25 static rules, MITRE ATLAS / OWASP AST10 tags
  shield/                       # opt-in PreToolUse enforcer
  signing/                      # ed25519 helpers (crypto/ed25519 stdlib)
  storage/                      # SQLite (modernc.org/sqlite, pure-Go)
    migrations/v1.sql           # the only schema; embedded via go:embed
  version/                      # version string injected via -ldflags
data/                           # go:embed-able static assets
  universal_floor.json
  dql/                          # 5 DQL templates (text/template)
  davis/                        # detector starter configs
  redteam/                      # corpus
.github/
  action/                       # GitHub Action source (wraps internal/cli/cmd/ci)
  workflows/ci.yml              # CI for dtguard itself
go.mod                          # dtctl pinned with module range
Makefile                        # build, test, lint, install
```

## States and Modes

States, keyed by `content_hash = sha256(asset_file_bytes)`:

- `OBSERVED` — default; spans flow, Davis is learning the shape.
- `ATTESTED` — signed `Attestation` exists; Davis raises on drift.
- `REVOKED` — asset is untrusted; Davis raises CRITICAL on use.

Modes (per-asset or per-tenant):

- `observe` *(default)* — nothing local. Spans -> Davis -> workflows.
- `alert` — local hook annotates "would-deny" on drift. Tool still runs.
- `enforce` — PreToolUse hook denies tool calls outside the signed shape.

## Resource Model

Every kind: `apiVersion: dtguard.io/v1`, `kind`, `metadata`, `spec`.
**Crypto fields under `spec`, never `metadata`.** Signing payload is
`canonical_json(spec_without_signature)`.

Kinds: `asset`, `attestation`, `proposal`, `provenance`, `revocation`,
`finding`, `floor`. Each registers itself in `internal/resources/registry.go`
via `init()`.

## Signers

`signer.kind` discriminates *how* an Attestation came to exist. Trust
anchor is the public key registered for that signer ID.

- `human` — reviewer signs with their ed25519 key. Must not equal
  `provenance.author` (separation of duties).
- `davis` — DT anomaly-detection holds a service key, auto-signs after
  configurable stability + zero-anomaly windows.
- `policy` — deterministic rule engine signs when predicates pass.

## dtctl Alignment

Imported (treat as "use at your own risk", pinned in `go.mod`):

| dtctl package | Where dtguard uses it |
|---|---|
| `pkg/auth`     | `internal/auth/auth.go` |
| `pkg/config`   | `internal/auth/auth.go` |
| `pkg/output`   | `internal/output/render.go` |
| `pkg/safety`   | `internal/cli/safety.go` |
| `pkg/aidetect` | `internal/output/agent.go` |

dtctl does NOT support arbitrary `apiVersion`s — dtguard talks
directly to the DT Documents/Settings API and embeds resource bodies
as JSON inside DT documents.

## Where State Lives

| State | Source of truth |
|---|---|
| Active dtctl context (tenant URL, token) | `~/.config/dtctl/` (read-only from dtguard) |
| dtguard signing key | `~/.config/dtguard/keys/sign.key` (mode 0600) |
| Attestations, Proposals, Provenance, Revocations, Findings | DT Documents/Settings API |
| Local cache (enforcement opt-in only) | `~/.dtguard/dtguard.db` |
| Span attributes | DT trace store, via OTel exporter |

Local cache exists ONLY when `dtguard shield install` has been run.

## Module Dependencies (What Can Import What)

```
cli/        -> resources/, auth/, output/, scanner/, shield/, dt/
resources/  -> attestation/, signing/, dt/
shield/     -> storage/, hlot/, attestation/
attestation/-> signing/
dt/         -> auth/
storage/    -> nothing (leaf)
hlot/       -> nothing (leaf, just OTel attribute names)
version/    -> nothing (leaf)
```

No circular imports. If tempted, extract shared types into a leaf
package.

## Key Design Decisions

1. **Single binary, no daemon.** Observe mode has no local state.
2. **dtctl as substrate, not as runtime dep.** Imports happen at
   compile time; dtguard does not shell out to dtctl.
3. **Signature is the trust anchor.** Resource location is not
   trusted; tampering with any cache fails verification.
4. **`content_hash` is the thread.** Same identity at PR scan,
   runtime span, and signed record.
5. **Apache 2.0**, matching dtctl.
6. **Single v1 schema.** No migration history. Past never happened.

## Verification Bar (per Batch 14 of the plan)

- `make build` produces `bin/dtguard` < 30 MB.
- `go test ./...`, `golangci-lint run`, `gosec ./...` all clean.
- `dtguard --help`, `dtguard version`, `dtguard doctor` work.
- Round-trip: `dtguard apply -f x.yaml && dtguard get <kind> <name>
  -o yaml > y.yaml && diff x.yaml y.yaml` for every kind.
- `--agent` envelope validates against `dtctl/pkg/aidetect`.
- `grep -r "agentguard\|QUARANTINED\|AGENTGUARD_\|src/agentguard"`
  returns zero matches outside git history.

## Working Notes

- All packages above are **planned**. Batch 1 ships only the Cobra
  skeleton; subsequent batches flesh out each package per
  [tmp/plan.md](../../tmp/plan.md).
- Update this file when the dependency graph changes.
- Never run `git add` / `git commit` / `git push` — architecture
  analysis belongs in response text, not commits.
