# Architecture

dtguard is a single Go binary. This page covers the package layout, the dtctl modules dtguard imports, the lifecycle state machine, the resource model, and configuration.

## Repository layout

```
cmd/dtguard/main.go             # Cobra root, delegates to internal/cli
internal/
  attestation/                  # canonical-json payload, signing, verification
  auth/                         # wraps dtctl/pkg/auth + pkg/config
  cli/                          # Cobra command tree
    cmd/                        # top-level domain verbs (scan, sign, revoke, ci, ...)
  dt/                           # DT Documents/Settings API client (net/http)
  hlot/                         # span-attribute schema and emission
  output/                       # wraps dtctl/pkg/output, agent-envelope formatter
  resources/                    # registry + per-kind handlers
    asset/, attestation/, proposal/, provenance/, revocation/, finding/, floor/
  scanner/                      # 25 static rules, MITRE ATLAS + OWASP AST10 tags
  shield/                       # opt-in PreToolUse enforcer
  signing/                      # ed25519 helpers (crypto/ed25519 stdlib)
  storage/                      # SQLite (modernc.org/sqlite, pure-Go)
    migrations/v1.sql           # the only schema; embedded via go:embed
  version/                      # version string injected via -ldflags
data/                           # go:embed-able static assets
  universal_floor.json
  dql/                          # 5 DQL templates (text/template format)
  davis/                        # Davis detector starter configs
  redteam/                      # corpus
.github/
  action/                       # GitHub Action source (wraps internal/cli/cmd/ci)
  workflows/ci.yml              # CI for the dtguard repo itself
go.mod                          # dependencies pinned, dtctl module range
LICENSE                         # Apache-2.0
README.md, CLAUDE.md, Makefile
```

## dtctl alignment

dtguard's CLI is verb-noun, kubectl/dtctl-aligned. Same muscle memory,
same resource model (`apiVersion: dtguard.io/v1`, `kind`, `metadata`,
`spec`), same `-o table|json|yaml|csv` and `--agent` envelope, same
named contexts under `~/.config/dtguard/`.

dtguard imports these dtctl Go packages directly. Treat them as "use
at your own risk" — pinned in `go.mod`, surfaced through narrow
internal wrappers so a breakage is contained to one file.

| dtctl package | Where dtguard uses it |
|---|---|
| `pkg/auth`     | `internal/auth/auth.go` — login, token refresh, active context |
| `pkg/config`   | `internal/auth/auth.go` — reading the dtctl config file |
| `pkg/output`   | `internal/output/render.go` — table/json/yaml/csv |
| `pkg/safety`   | `internal/cli/safety.go` — readonly / readwrite-mine / ... |
| `pkg/aidetect` | `internal/output/agent.go` — `--agent` envelope schema |

Where dtguard diverges:

- **Signing is first-class.** dtctl signs nothing. `dtguard apply` on
  an `Attestation` requires a private key and produces an ed25519
  signature in the resource body.
- **Domain verbs.** `scan`, `sign`, `revoke` exist alongside CRUD.
- **Local cache** (only when enforcement is opted in). The
  enforcement hook reads from a local SQLite synchronously; that
  cache is fed by `dtguard sync`. In observe mode there is no cache.

dtctl does NOT support arbitrary `apiVersion`s. dtguard talks
directly to the DT Documents/Settings API and embeds resource bodies
as JSON inside DT documents.

## Resource model

Every kind: `apiVersion: dtguard.io/v1`, `kind`, `metadata`, `spec`.
**Crypto fields under `spec`, never `metadata`.** Signing payload is
`canonical_json(spec_without_signature)`.

Kinds: `asset`, `attestation`, `proposal`, `provenance`, `revocation`,
`finding`, `floor`.

```yaml
apiVersion: dtguard.io/v1
kind: Attestation
metadata:
  name: docs-helper
  signedAt: 2026-04-28T10:00:00Z
spec:
  subject:
    contentHash: sha256:abc123...
    declarationHash: sha256:def456...
  observedShape:
    tools:         [Read, Edit]
    egressHosts:   [api.openai.com]
    bashPrefixes:  [git, npm]
    writeGlobs:    [docs/**]
  provenanceRef: sha256:abc123:commit:1f2e3d
  supersedes: sha256:prev...           # null for the first record
  davisProposalId: dav-9871
  signature:
    value: ed25519:0x...
    keyId: ed25519:fp...
    signerKind: human                  # human | davis | policy
    signerId: alice@example.com
```

Per-kind packages register in `init()` against the
`internal/resources/registry.go` Resource interface; `dtguard
get/describe/apply/delete <kind>` dispatches through the registry.

## Lifecycle (state machine)

States are keyed by `content_hash`. They describe the asset's
**attestation status** in Dynatrace, not whether tool calls are
blocked.

```
   [new content_hash]
          |
          v
    [ OBSERVED ] ----- proposal signed -----> [ ATTESTED ]
          |                                        |
          | revoked                                | amendment revoked
          v                                        v
    [ REVOKED ]    <-- CRITICAL floor / TI -- [ ATTESTED ]
          |
          | replace asset (new bytes) -> new content_hash, new OBSERVED
          v
    (gone; new hash starts over)
```

- **OBSERVED**: any new `content_hash` lands here. HLOT-tagged spans
  flow to DT; Davis accumulates a shape.
- **ATTESTED**: a signer produced an `Attestation` containing a
  stable `observedShape`. Davis raises a problem on any span whose
  `(tool, egressHost, bashPrefix, writeGlob)` falls outside the shape.
  If Davis later sees new-but-stable behavior, it files an
  **amendment proposal** with `supersedes` pointing at the current
  record.
- **REVOKED**: marked untrusted via `dtguard revoke <hash> --reason`
  or a Davis workflow on a CRITICAL universal-floor or threat-intel
  hit. Exiting REVOKED requires either replacing the asset bytes
  (-> new hash, fresh OBSERVED) or an explicit reinstate.

Mutating the asset on disk changes its `content_hash` and creates a
fresh OBSERVED state. Old records are never rewritten in place;
history is append-only via `supersedes`.

## Signers

`signer.kind` discriminates *how* an Attestation came to exist; the
shield treats all kinds identically — the trust anchor is the public
key registered for that signer ID.

- **`human`** — reviewer signs personally. Separation of duties:
  must not equal `provenance.author`.
- **`davis`** — DT anomaly-detection holds a service key, auto-signs
  after configurable stability + zero-anomaly windows.
- **`policy`** — deterministic rule engine signs when its predicates
  pass.

Mixed-mode signing is supported via `supersedes`: a `policy` pre-sign
chained with a `human` countersign produces two records in the chain.
Each record carries `signedAt` + `keyId`; the trust set tracks per-key
validity windows so rotating a signer out doesn't void records they
signed within their valid window.

## Request flows

**`dtguard get attestations -o yaml`**:

```
cmd/dtguard/main.go -> internal/cli (Cobra)
  -> get -> kind="attestation"
       -> internal/resources/registry: Attestation handler
            -> internal/auth: dtctl context (tenant + token)
            -> internal/dt: GET /platform/documents/...
            -> internal/resources/attestation: decode + verify signature
            -> internal/output: render YAML via dtctl/pkg/output -> stdout
```

**`dtguard sign <proposal-id>`**:

```
internal/cli/cmd/sign.go
  -> internal/auth: resolve context
  -> internal/dt: fetch Proposal by ID
  -> internal/signing: load ~/.config/dtguard/keys/sign.key
  -> internal/attestation: build canonical_json(spec) and sign
  -> internal/dt: PUT new Attestation document
  -> internal/output: render confirmation
```

**PreToolUse hook (enforcement opt-in)**:

```
Claude Code -> stdin JSON -> dtguard shield invoke
  -> internal/shield/enforcer.go
       -> internal/storage: read state + attestation by content_hash
       -> internal/shield: universal-floor + four-dimension shape match
       -> stdout JSON: {"allow": bool, "reason": "...", "state": "..."}
       -> internal/hlot: emit span via go.opentelemetry.io/otel
```

The hook never makes a network call. Local SQLite is the source of
truth at the call path; refresh happens via `dtguard sync` on
SessionStart.

## Where state lives

| State | Source of truth |
|---|---|
| Active dtctl context (tenant URL, token) | `~/.config/dtctl/` (read-only) |
| dtguard signing key | `~/.config/dtguard/keys/sign.key` (mode 0600) |
| Attestations, Proposals, Provenance, Revocations, Findings | DT Documents/Settings API |
| Local cache (enforcement opt-in only) | `~/.dtguard/dtguard.db` |
| Span attributes | DT trace store, via OTel exporter |

## Configuration

dtguard reads, in precedence order: CLI flags > env vars > active
context in `~/.config/dtguard/config.yaml` > built-in defaults.

| Variable | Purpose |
|---|---|
| `DT_TENANT_URL` | Override active context's tenant URL. |
| `DT_API_TOKEN` | Token-based auth (alternative to dtctl SSO). |
| `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_EXPORTER_OTLP_HEADERS` | Standard OTel OTLP config when OneAgent is not present. |
| `DTGUARD_UNIVERSAL_FLOOR` | Path to a custom `floor.yaml`. |
| `DTGUARD_SIGNING_KEY` | Path to the ed25519 signing key. Default: `~/.config/dtguard/keys/sign.key`. |
| `DTGUARD_DB` | Local SQLite path (enforcement only). Default: `~/.dtguard/dtguard.db`. |

Safety levels (apply to `apply`, `delete`, `sign`, `revoke`):

| Level | Allows |
|---|---|
| `readonly` | `get`, `describe`, `scan`, `doctor`. |
| `readwrite-mine` | + sign/apply/delete records you authored. **Default.** |
| `readwrite-all` | + sign on others' behalf, cross-org writes. |
| `dangerously-unrestricted` | + bypass server-side validation. CI only. |

## Build and test

`make build` produces `bin/dtguard`. `make test` runs `go test ./...`.
`make lint` runs `golangci-lint`. `make install` does
`go install ./cmd/dtguard`.

Convergence with dtctl stays open: dtguard could ship as an
agentskills.io skill pack, or — long-term — contribute its kinds as
dtctl resource providers so `dtctl get attestations` works natively.
