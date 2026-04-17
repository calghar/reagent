# Behavioral Attestation

AgentGuard attests every AI-agent configuration asset by running it through a sandbox replay inside its native harness, producing a signed behavioral fingerprint bound to the asset's content hash. Runtime telemetry and runtime enforcement both key off the attestation record.

## Fingerprint dimensions

A `BehavioralFingerprint` is a deterministic summary of what an asset does, captured across five shape-level dimensions:

| Dimension | What it captures |
|---|---|
| `tool_calls` | Sorted distinct `tool:arg_shape` signatures (e.g., `Read:path`, `Bash:command`) |
| `egress_hosts` | Hostnames the asset caused the agent to contact |
| `file_writes` | Glob patterns of filesystem writes |
| `hook_subprocess` | Sorted exec-family argv signatures |
| `token_profile` | Aggregate statistics: input/output mean, std, count |

Each dimension is deliberately shape-level, not value-level — no prompt text, no file contents. The five fields are Merkle-hashed into a single `fingerprint_hash` (sha256 hex) after canonical JSON serialization.

## Content-hash identity

Every asset is identified by `sha256(asset_file_bytes)`. Renaming or moving a file does not change the hash; any byte-level change produces a new hash. The hash is the primary key across the catalog, attestation store, runtime spans, and trust ledger.

## CLI

```bash
# Produce a signed attestation (runs the sandbox driver end-to-end).
agentguard attest run ./my-skill.md

# Verify a stored attestation by re-checking its signature.
agentguard attest verify ./my-skill.md
```

`agentguard attest run` drives the real Claude Code CLI in a mediated subprocess. The runner requires `claude` on `PATH` and `ANTHROPIC_API_KEY` in the environment; set `--claude-binary` to point at a non-default install.

## Signing

Attestations are signed with a local ed25519 key at `~/.agentguard/keys/attestation.key` (mode 0o600). Missing keys are generated on first use. The public-key fingerprint (first 16 hex chars of sha256 over raw public-key bytes) becomes the `signer_key_id` recorded on every attestation.

A rotation strategy is a future extension; the attestation record schema already tracks `signer_key_id` so downstream systems can pin policies to key cohorts.

## Storage

Attestations live in SQLite at `~/.agentguard/agentguard.db` under the `attestations` table (migration v5). Keyed by `(asset_content_hash, fingerprint_hash)`; the latest record per asset hash is what CLI verification and runtime enforcement consult.

## Prompt corpus

The bundled universal corpus at `src/agentguard/data/corpus/universal.yaml` contains probes designed to elicit divergent behavior from malicious skills (sensitive-file reads, external egress attempts, system-service modifications, etc.). A well-behaved skill produces a benign fingerprint across these probes; a hijacked skill reveals itself through the tool calls, egress hosts, or file writes it generates.

Per-asset probe generation (using the asset's declared `description`) is a planned extension.

## Trust levels

Attestations carry a `TrustLevel` from `agentguard.security.trust`:

| Level | Meaning |
|---|---|
| `UNTRUSTED` | Default for new/imported assets |
| `REVIEWED` | Human-approved, sandbox-attested |
| `VERIFIED` | REVIEWED plus observed runtime stability |
| `NATIVE` | Created locally within the repository |

Promotion is explicit (`agentguard trust promote`); the shield reads the current tier at invocation time.

## Integration with the rest of AgentGuard

- Runtime divergence checks (`agentguard diverge check`) compare a live fingerprint to the attested baseline.
- Counterfactual merge gates (`agentguard counterfactual`) replay a proposed revision and block the merge if the fingerprint expands into new egress, new tool calls, or new hook subprocess trees.
- HLOT span attributes (`agentguard telemetry hlot`) emit the asset content hash, fingerprint hash, and trust tier for every agent-session OTel span.
- The BATT shield (`agentguard shield`) enforces tool-grant authority based on the attested trust tier.
