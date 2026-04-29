# CLI Reference

`dtguard` follows verb-noun syntax aligned with
[dtctl](https://github.com/dynatrace-oss/dtctl). Every command accepts
`-v/--verbose`, `--log-file PATH`, `-o table|json|yaml|csv`, and
`--agent` (structured envelope for AI agents).

## Auth and config

| Command | Purpose |
|---|---|
| `dtguard auth login` | Browser SSO to the configured DT tenant (delegates to `dtctl/pkg/auth`). |
| `dtguard auth logout` | Clear stored credentials. |
| `dtguard auth whoami` | Show authenticated identity. |
| `dtguard auth status` | Report token validity and scopes. |
| `dtguard config set-context NAME --environment URL [--token-ref REF]` | Add or update a context. |
| `dtguard config use-context NAME` | Switch active context. |
| `dtguard config view` | Print effective config. |
| `dtguard config get-contexts` | List configured contexts. |

## Resources (CRUD)

Kinds: `asset`, `attestation`, `proposal`, `provenance`, `revocation`,
`finding`, `floor`.

| Command | Purpose |
|---|---|
| `dtguard get <kind> [name]` | List or fetch. |
| `dtguard describe <kind> <name>` | Detailed view. Supports `--include shape\|chain\|provenance`. |
| `dtguard apply -f <file>` | Create or update from YAML. `--dry-run` previews. |
| `dtguard delete <kind> <name>` | Remove. |
| `dtguard edit <kind> <name>` | Open in `$EDITOR`. |

## Domain verbs

| Command | Purpose |
|---|---|
| `dtguard scan PATH` | Run the 25-rule static scanner. Returns `Finding` records. |
| `dtguard sign <proposal-id> [--key PATH]` | Sign a Davis proposal -> `Attestation`. Requires at least `readwrite-mine`. |
| `dtguard revoke <content-hash> --reason TEXT` | Explicit move to REVOKED. |
| `dtguard ci` | PR-time scanner + state checks. Exits 0/1/2 — see [security.md](security.md#ci-integration). |
| `dtguard bundle export` | Produce a signed offline bundle (air-gapped envs). |
| `dtguard bundle verify` | Recheck bundle signatures. |
| `dtguard sync [threat-intel]` | Refresh local cache or threat-intel feed. |

## Enforcement (opt-in)

| Command | Purpose |
|---|---|
| `dtguard shield install [--repo PATH]` | Install the PreToolUse hook + `.claude/settings.json` entry. |
| `dtguard shield check ASSET --tool NAME --args-json JSON` | Dry-run a shield decision. |
| `dtguard shield status [ASSET]` | Print current state and shape. |
| `dtguard shield sync [--for-repo PATH]` | Refresh the local cache. |

## Diagnostics

| Command | Purpose |
|---|---|
| `dtguard doctor` | Validate auth, DT reachability, schema, hook installation, OTel exporter. |
| `dtguard version` | Print version and build info. Asserts the dtctl module range. |

## Output modes

`-o table` is the default. `-o json` and `-o yaml` produce parseable
output. `--agent` wraps results in the `{ok, result, context, error}`
envelope shared with dtctl (validated against `dtctl/pkg/aidetect`).

```
$ dtguard get attestation docs-helper --agent
{
  "ok": true,
  "result": {"apiVersion": "dtguard.io/v1", "kind": "Attestation", ...},
  "context": {"verb": "get", "kind": "attestation", "name": "docs-helper"},
  "error": null
}
```
