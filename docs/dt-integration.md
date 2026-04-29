# Dynatrace Integration

Dynatrace is the system of record for dtguard. The CLI emits
HLOT-tagged OTel spans, ships DQL templates, expects two Davis
custom anomaly detectors on the tenant side, and stores resources as
DT documents. This page covers all four plus the optional local-cache
distribution model used in enforcement mode.

## 1. Span attributes

Every tool call emits attributes whether or not enforcement is
installed. With enforcement on, the span additionally carries the
shield decision.

**Asset attributes** (per-span, stable for the life of the asset):

| Attribute | Meaning |
|---|---|
| `dtguard.asset.content_hash` | `sha256(asset_file_bytes)`. Primary join key. |
| `dtguard.asset.declaration_hash` | Hash of the currently attested shape (or null when OBSERVED). |
| `dtguard.asset.state` | `OBSERVED` / `ATTESTED` / `REVOKED`. |
| `dtguard.asset.signer_id` | Who produced the current attestation (null when OBSERVED). |
| `dtguard.asset.signer_kind` | `human` / `davis` / `policy` (null when OBSERVED). |
| `dtguard.asset.name` | Human-readable identifier for dashboards. |

**Tool attributes** (per-call):

| Attribute | Meaning |
|---|---|
| `dtguard.tool.name` | Tool invoked (`Bash`, `Read`, `Write`, ...). |
| `dtguard.tool.arg_shape` | Shape-level summary of args; never contents. |
| `dtguard.tool.egress_host` | Host contacted if the call did network I/O. |
| `dtguard.tool.bash_prefix` | First argv token, for Bash calls. |
| `dtguard.tool.write_glob` | Normalized glob of a filesystem write. |
| `dtguard.tool.shield_decision` | `allow` / `deny` (only when enforcement is installed). |
| `dtguard.tool.deny_reason` | Free text when denied (`universal floor: ...`, `drift: egress_host`, `revoked`). |

In DQL these are flat dotted columns: `dtguard.asset.content_hash`,
not `attributes["dtguard.asset.content_hash"]`.

## 2. DQL templates

Bundled at `data/dql/` and embedded into the binary via `go:embed`.
They are Go `text/template` placeholders; substitute
`{{.content_hash}}` and `{{.window_hours}}` before running.

| File | Purpose |
|---|---|
| `asset_shape.dql` | Collect the observed shape (tools, hosts, bash prefixes, write globs) for a content hash over a window. Body of the stability detector. |
| `drift.dql` | List spans whose call falls outside the attested shape. |
| `deny_rate.dql` | Denies per asset per hour (enforcement mode only). |
| `new_host_emergence.dql` | Egress hosts in the last window but not in the prior. |
| `threat_intel_hits.dql` | Universal-floor hits whose reason matches threat-intel. |

## 3. Davis detectors

Davis custom anomaly detectors are configured in the **Anomaly
Detection app UI**. Dynatrace does not publish a JSON schema for this
configuration, so dtguard does not ship a Davis config file — only
starter thresholds at `data/davis/README.md`.

Walkthrough:
<https://docs.dynatrace.com/docs/dynatrace-intelligence/anomaly-detection/anomaly-detection-app/configure-a-simple-ad>

### Detector 1 — Stability proposal

Promotes an OBSERVED asset to a `Proposal` once its shape has
stabilized.

- **Query**: `asset_shape.dql`.
- **Threshold (starting point)**: ≥50 calls, ≥3 distinct hosts,
  ≤10% shape variance over 7 days. Adapt per tenant.
- **Event**: `dtguard stability proposal: {dtguard.asset.name}`,
  severity INFO, payload carries `content_hash`, observed sets,
  call/host counts.

### Detector 2 — Drift alert

Flags spans outside an ATTESTED shape and universal-floor hits.

- **Query**: `drift.dql` for drift; `threat_intel_hits.dql` for
  universal-floor TI hits.
- **Threshold (starting point)**: any `universal floor:` hit in 5 min
  -> CRITICAL; any `drift:` event in 15 min -> HIGH.
- **Event**: `dtguard drift: {dtguard.asset.name} ({reason})`,
  severity CRITICAL or HIGH, payload carries `content_hash`,
  `tool.name`, `tool.egress_host`, `tool.bash_prefix`.

Alert routing to Slack / PagerDuty / approval queues is done through
DT Workflows.

## 4. Resources as DT documents

The state-bearing kinds (`Attestation`, `Proposal`, `Provenance`,
`Revocation`, `Finding`) are stored as Dynatrace documents and are
queryable via the Documents API. `dtguard get / describe / apply`
are thin wrappers over that surface; the same data is accessible from
DT Notebooks and from a future `dtctl get attestations`.

DT does NOT support arbitrary `apiVersion`s — dtguard encodes its
kinds inside document bodies, not URL paths.

## 5. Threat-intel sync (optional)

`dtguard sync threat-intel` periodically pulls the DT threat-intel
feed into the universal-floor IP/domain list. Schedule via DT
Workflows alongside other tenant-side maintenance jobs.

## 6. Distribution (enforcement opt-in only)

A signed `Attestation` is a DT document. In **observe mode** there is
no local cache and no daemon — dtguard fetches resources on demand
through the dtctl auth context.

Enforcement opts into a synchronous local gate at the agent harness,
so records must be on the laptop or runner before the call happens.
The PreToolUse hook reads from a local SQLite at
`~/.dtguard/dtguard.db` (<1 ms point lookup). Four layers feed it:

| Layer | Mechanism | Refresh |
|---|---|---|
| **L1 — primary cache** | `dtguard sync --for-repo .` writes verified records into local SQLite. | Per session |
| **L2 — one-line install** | L1 command goes into `.claude/settings.json` as a SessionStart hook. | Automatic at session start |
| **L3 — revocation feed** | Conditional GET (ETag) for the org's revocation list. Hook owns the heartbeat. | ≤5 min |
| **L4 — offline bundle** | `dtguard bundle export` produces a signed gzipped bundle. Hook reads bundle when no DT-backed cache is present. | Per `git pull` |

L1 + L2 + L3 covers 95% of enforcement users. L4 is the escape hatch
for air-gapped envs and open-source maintainers without a tenant.

The hook is **always local-first**: it reads the local SQLite
synchronously. Network is for refresh, never for the tool-call
critical path. The **signature** is what is trusted, not the storage
— tampering with the cache fails verification at hook time.

SessionStart hook (one-line install):

```json
{
  "hooks": {
    "SessionStart": [
      {"command": "dtguard sync --for-repo $CLAUDE_CWD --quiet"}
    ]
  }
}
```
