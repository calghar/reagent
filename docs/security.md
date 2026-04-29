# Security

dtguard's security surface has three layers: a **PR-time scanner**
that blocks merges on CRITICAL findings, **runtime observation**
that lets Davis raise drift problems, and an **opt-in shield** that
gates tool calls at the agent harness. Each layer is independent;
observation is the headline.

## Threat model

dtguard protects the path from authoring -> PR -> merge -> install
-> runtime invocation -> tool call -> filesystem / network egress
for AI-agent configuration assets. It does not protect the model
weights, the hosted LLM provider, or the application code the agent
writes.

| # | Class | Example | Where dtguard catches it |
|---|---|---|---|
| T1 | Direct prompt injection | `"Ignore all previous instructions"` in a skill body | PR scanner (CRITICAL). |
| T2 | Indirect injection via tool output | Malicious instructions in a fetched page | Davis raises drift when the call falls outside the attested shape. *Honest limit: if injection steers the agent into an already-attested call, only volume/context anomalies catch it.* |
| T3 | Unsafe tool-grant breadth | Skill requests `Bash(*)` when it only needs `Read` | PR scanner; ATTESTED shape never grows beyond observed calls. |
| T4 | Hook shell injection | `echo ${ARG}` in a hook -> RCE | PR scanner (CRITICAL). |
| T5 | Supply-chain rug-pull | Attested skill overwritten on disk post-merge | `content_hash` changes -> state resets to OBSERVED. Davis re-proposes. |
| T6 | Homoglyph / bidi Unicode | Invisible instructions in a rules file | PR scanner (CRITICAL). |

## What dtguard explicitly does not do

- No automated semantic judgement of prompt text at runtime.
- No sandbox pre-flight. Attested shapes come from real traffic only.
- No cross-tenant fleet consensus. Each tenant's observation window
  is its own.

## 1. PR-time: the scanner

`dtguard scan PATH` runs 25 static rules with MITRE ATLAS technique
IDs and OWASP Agentic Skills Top-10 (AST10) categories. Each finding
is a `Finding` resource with rule ID, severity, file/line,
description, and taxonomy tags.

| Severity | Examples |
|---|---|
| **CRITICAL** | unrestricted tool access (`tools: ["*"]`); `bypassPermissions` / `dontAsk` modes; shell injection in hooks; secrets in asset content; prompt-injection-override phrasing, role hijacking, tool-poisoning; bidi / homoglyph payloads; URL fetched and executed by a hook. |
| **HIGH** | broad file-write permissions; unsafe env-var expansion; sensitive-file access patterns; suspicious URLs / credentials in URLs; runtime code fetch; shell-pipe exec; filesystem escape. |
| **MEDIUM** | large prompt sizes; encoded content (base64, ...); writes to `.claude/`; git force-push patterns; system-service modifications; excessive tool count. |

Authoritative rule definitions live in `internal/scanner/`. References:

- MITRE ATLAS: <https://atlas.mitre.org/matrices/ATLAS>
- OWASP AST10: <https://owasp.org/www-project-agentic-skills-top-10/>

## 2. Runtime: attestation and Davis

dtguard attestation is **observation-grounded**. Davis proposes a
stable behavioral shape from HLOT-tagged runtime spans; a signer
produces a signed `Attestation`. There is no pre-runtime claim, no
sandbox replay, no author-authored declaration. The signature
asserts: "this shape has been observed to be stable in production,
and I approve it as the policy for this content hash."

The signed blob is the shape plus its provenance — not the asset
file contents, not the prompt text. The asset's `content_hash` binds
the record to exactly the bytes observed.

Lifecycle, signer kinds, amendment chain via `supersedes`, and key
rotation: see [architecture.md](architecture.md#lifecycle-state-machine).

Revocation is a REVOKED-state transition, written as a new record
with an empty `observedShape` and a `reason`. Davis reads the latest
state per `content_hash` and raises CRITICAL on any usage. There is
no CRL; the DT document store is the source of truth.

## 3. Optional: the shield

The shield is an **opt-in** PreToolUse hook that gates tool calls at
the agent harness. Install it only when synchronous blocking is a
hard requirement: regulated production where laptop-root must not
silently widen policy, air-gapped or partially-offline environments
where Davis-side alerts cannot reach a paging system in time, or
shops that explicitly want a deny at the tool call rather than a
problem in DT.

| State | Shield decision |
|---|---|
| `OBSERVED` | Allow, unless universal floor denies. |
| `ATTESTED` | Allow iff `(tool, egressHost, bashPrefix, writeGlob)` is in the signed shape. Otherwise deny `drift: <dim>`. |
| `REVOKED` | Deny all. |

Decision flow:

```
state = local_cache.state_for(content_hash)
if UniversalFloor.blocks(tool, args):   return DENY "universal floor: ..."
if state == REVOKED:                    return DENY "revoked"
if state == OBSERVED:                   return ALLOW
if state == ATTESTED:
    if (tool, host, prefix, glob) in observed_shape:  return ALLOW
    return DENY "drift: <dimension>"
```

Latency: one local SQLite point lookup, sub-millisecond on SSD. The
hook never makes a network call. Cache distribution and refresh:
[dt-integration.md](dt-integration.md#6-distribution-enforcement-opt-in-only).

### Universal floor

A bundled deny-list that applies in **every** state:

- destructive shell prefixes (`rm -rf /`, `mkfs`, `dd of=/dev/`, ...)
- writes outside configured workspace roots
- egress to DT threat-intel-flagged IPs / domains

Override via `DTGUARD_UNIVERSAL_FLOOR` pointing at a custom YAML.
Universal-floor denies emit `deny_reason="universal floor: ..."`.

### Install

```bash
dtguard shield install --repo .
```

Adds a `PreToolUse` hook plus a `SessionStart` cache-sync hook to
`.claude/settings.json`. The hook reads the PreToolUse event from
stdin and writes a one-line JSON decision to stdout per the Claude
Code hook protocol.

Whether the shield is installed or not, every tool call emits the
same HLOT span attributes. With the shield installed, the span
additionally carries `dtguard.tool.shield_decision` and
`dtguard.tool.deny_reason`.

## CI integration

dtguard ships a GitHub Action that runs on PR (informational) and on
merge (records provenance).

```yaml
# .github/workflows/dtguard.yml
name: dtguard
on:
  pull_request:
  push:
    branches: [main]

jobs:
  dtguard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: dtguard/action@v1
        with:
          assets-path: .claude
          dt-tenant: ${{ secrets.DT_TENANT_URL }}
          dt-token: ${{ secrets.DT_API_TOKEN }}
```

| Exit code | Meaning |
|---|---|
| 0 | Pass. PR: informational comment. Merge: provenance written. |
| 1 | Scanner reported a CRITICAL finding. |
| 2 | One or more changed hashes are REVOKED. Do not merge. |

PR comment shape — one line per changed asset:

```
dtguard
- .claude/skills/docs-helper/SKILL.md  new -> OBSERVED on merge
- .claude/agents/reviewer.md           already ATTESTED (unchanged shape)
- .claude/skills/legacy-exporter.md    REVOKED -- block merge
```

The `Provenance` resource (one per merge: `content_hash`, commit sha,
author, repo, branch, timestamp) is a Dynatrace document, queryable
via `dtguard get provenance --content-hash <hash>` or directly in DT.
The GitHub runner's filesystem is ephemeral and not relied upon.
