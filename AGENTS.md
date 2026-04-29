# CLAUDE.md

## Commands

```bash
make build                              # -> bin/dtguard
make test                               # go test ./...
make lint                               # golangci-lint run
go test ./... -race -count=1            # full quick test
go vet ./...                            # vet
./bin/dtguard --help                    # CLI help
```

## What This Is

dtguard is a Dynatrace-aligned attestation and observability layer for
AI-agent configuration assets (skills, sub-agents, hooks, rules). It
fingerprints every asset by `content_hash`, signs the fingerprint
once behavior stabilizes, and surfaces drift through Davis as DT
problems. Single Go binary, distributed via Homebrew.

The product surface is observability and attestation. Synchronous
gating at the agent harness is opt-in.

## Architecture

Go 1.23+ CLI (`cmd/dtguard/main.go`) backed by these packages:

- **internal/cli/** — Cobra command tree (verb-noun, kubectl/dtctl-aligned)
- **internal/resources/** — registry + per-kind handlers (`asset`,
  `attestation`, `proposal`, `provenance`, `revocation`, `finding`,
  `floor`); resources are YAML with `apiVersion: dtguard.io/v1`
- **internal/auth/** — wraps `dtctl/pkg/auth` and `dtctl/pkg/config`
- **internal/dt/** — DT Documents/Settings API client (net/http)
- **internal/attestation/** — canonical-json payload, signing,
  verification
- **internal/signing/** — ed25519 via `crypto/ed25519` stdlib
- **internal/scanner/** — 25 static rules with MITRE ATLAS / OWASP
  AST10 metadata
- **internal/shield/** — opt-in PreToolUse enforcer (the only thing
  that touches local SQLite)
- **internal/storage/** — `modernc.org/sqlite` (pure-Go), single v1
  migration via `go:embed`
- **internal/hlot/** — OTel span attributes (`dtguard.asset.*`,
  `dtguard.tool.*`)
- **internal/output/** — wraps `dtctl/pkg/output` for
  `-o table|json|yaml|csv`; agent envelope via `dtctl/pkg/aidetect`
- **internal/version/** — version string injected via `-ldflags`
- **data/** — `go:embed`-ed universal floor, DQL templates, Davis
  configs, redteam corpus

## Key Patterns

- **dtctl as substrate, not runtime dep.** Imports happen at compile
  time; never shell out to dtctl.
- **Crypto fields under `spec`, never `metadata`.** Signing payload
  is `canonical_json(spec_without_signature)`.
- **States**: `OBSERVED` / `ATTESTED` / `REVOKED`. No `QUARANTINED`.
- **Modes**: `observe` (default) / `alert` / `enforce`. Enforcement
  is opt-in.
- **Signers**: `human` / `davis` / `policy`. Trust anchor is the
  public key, not the resource location.
- **No daemon, no local state in observe mode.** Local SQLite at
  `~/.dtguard/dtguard.db` exists ONLY when `dtguard shield install`
  has been run.
- **PreToolUse hook is hot-path code.** No network calls. Budget
  <1 ms per invocation.

## Things That Will Bite You

- DT Documents/Settings API does NOT support arbitrary `apiVersion`
  — dtguard talks directly to the API and embeds resource bodies
  inside DT documents.
- `dtctl/pkg/*` is not documented as a stable SDK. Pinned in
  `go.mod` with a minimum module version. Wrappers in
  `internal/auth` and `internal/output` are the only callers.
- Use `modernc.org/sqlite` (pure-Go). Don't accidentally pull in
  `github.com/mattn/go-sqlite3` (cgo).
- `--agent` envelope must validate against `dtctl/pkg/aidetect`. If
  you're tempted to define your own envelope shape, you're wrong.

## Code Conventions

- Go 1.23+, `gofmt -s` + `goimports`, `golangci-lint run` clean.
- Errors: wrap with `fmt.Errorf("...: %w", err)`. Never silently
  swallow.
- Logging: `log/slog` with stable keys.
- No module-level docstrings. Public symbols get one-line comments
  starting with the symbol name (Go convention).
- Embed static assets via `//go:embed`, never read from disk at
  runtime.
- `init()` is reserved for resource registry registration.
- Default to standard library. Add a dep only when it earns its keep.
- Tests: table-driven, `t.Run(name, ...)` per case. Use `t.TempDir()`
  for filesystem isolation. Use `httptest.NewServer` for HTTP.

## Reference

- Plan: [tmp/plan.md](../tmp/plan.md) (current implementation brief)
- Architecture: [docs/architecture.md](../docs/architecture.md)
- CLI design: [docs/cli-design.md](../docs/cli-design.md)
- Mental model: [tmp/mental-model.html](../tmp/mental-model.html)
