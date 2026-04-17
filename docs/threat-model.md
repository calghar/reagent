# AgentGuard Threat Model

> Owner: Michael Krieger (Principal Security Researcher, CNS). Last reviewed: 2026-04.

This document describes the threat model AgentGuard defends against and maps every built-in scanner rule to a standard taxonomy.

## Scope

AgentGuard protects the **authoring → PR → review → merge → install → runtime invocation → tool call → filesystem / network egress** path for AI-agent configuration assets (skills, sub-agents, slash-commands, hooks, rules, CLAUDE.md / AGENTS.md / `.cursor/rules` / `.codex` / `.opencode`). It does not protect the underlying LLM weights or the application code the agent writes.

## Assets

1. **Authored agent configuration** — skills, agents, hooks, rules, CLAUDE.md, MCP tool descriptors.
2. **Agent runtime identity** — tool grants, trust tier, permission mode.
3. **Developer credentials** — API keys, SSH keys, tokens accessible to the agent process.
4. **Downstream artifacts** — source code, commits, PRs, application deployments produced by the agent.

## Trust boundaries

| Boundary | Enforced by |
|---|---|
| Author → repository | Git permissions, PR review, AgentGuard CI static scan + behavioral sandbox attestation |
| Repository → developer workstation | AgentGuard `shield` runtime interceptor, trust-tier policy |
| Developer workstation → external network | AgentGuard egress mediation, HLOT-linked audit trail |
| Developer workstation → application deployment | Existing CI/CD + AgentGuard causal lineage on post-incident analysis |

## STRIDE per boundary

| Threat | Author→Repo | Repo→Dev | Dev→Net | Dev→Deploy |
|---|---|---|---|---|
| **S**poofing (impersonation) | Malicious PR author | Unsigned asset rug-pull | Attacker-controlled host | Forged attestation |
| **T**ampering | Payload in skill body | Post-merge mutation | In-flight prompt injection | Malicious tool call |
| **R**epudiation | No audit trail of instruction authorship | No span-to-asset linkage | No egress log | No incident attribution |
| **I**nformation disclosure | Secret in skill | Cred access via sensitive-file rule | Exfiltration via tool | Exfil via deployed code |
| **D**enial of service | Token-burn via looping skill | Resource exhaustion hook | Rate-limit exhaustion | — |
| **E**levation of privilege | `bypassPermissions` mode | Tool-grant expansion at runtime | — | Writes to `.claude/` to re-arm |

## Six canonical attack classes

| # | Class | Concrete example | MITRE ATLAS | AST10 |
|---|-------|------------------|-------------|-------|
| T1 | Direct prompt injection | `"Ignore all previous instructions and..."` in a skill body | AML.T0051.000 | AST01 |
| T2 | Indirect prompt injection | Hidden instructions embedded in tool output, rendered as trusted | AML.T0051.001 | AST01, AST10 |
| T3 | Unsafe tool-grant breadth | Skill asks for `Bash(*)` when it only needs `Read` | AML.T0011 | AST03 |
| T4 | Hook shell injection | `echo ${ARG}` in a pre-commit hook → RCE | AML.T0050 | AST06 |
| T5 | Supply-chain rug-pull | Approved skill mutated post-merge to add exfil | AML.T0010 | AST05 |
| T6 | Homoglyph / bidi Unicode | Invisible instructions in rules file | AML.T0051.001, AML.T0054 | AST07 |

## Rule → taxonomy mapping

Every scanner rule declares its `mitre_atlas` and `owasp_ast10` fields. The test `tests/test_security_taxonomy.py::test_every_critical_rule_has_atlas_tag` enforces that every CRITICAL-severity rule carries at least one ATLAS technique ID; no rule of any severity may ship without an AST10 ID.

Summary of built-in coverage (see `src/reagent/security/scanner.py` for authoritative definitions):

| Rule | Severity | MITRE ATLAS | AST10 |
|---|---|---|---|
| PROMPT_INJECTION_OVERRIDE | CRITICAL | T0051.000 | AST01 |
| PERMISSION_ESCALATION | CRITICAL | T0011 | AST03, AST08 |
| HIDDEN_UNICODE | CRITICAL | T0051.001, T0054 | AST07 |
| EXTERNAL_HOOK_URL | CRITICAL | T0024, T0025 | AST02 |
| TOOL_POISONING_TAGS | CRITICAL | T0051.001, T0011 | AST01, AST10 |
| ROLE_HIJACKING | CRITICAL | T0051.000, T0054 | AST01 |
| SEC-010 (bypassPermissions) | CRITICAL | T0011 | AST03, AST08 |
| SEC-014 (strong secret) | CRITICAL | T0025 | AST09 |
| UNRESTRICTED_BASH | HIGH | T0011, T0050 | AST03 |
| SHELL_PIPE_EXEC | HIGH | T0010, T0050 | AST05 |
| SENSITIVE_FILE_ACCESS | HIGH | T0025 | AST02, AST09 |
| SECRET_EXFILTRATION | HIGH | T0024, T0025 | AST02 |
| HARDCODED_SECRET | HIGH | T0025 | AST09 |
| SHELL_INJECTION | HIGH | T0050 | AST06 |
| FILESYSTEM_ESCAPE | HIGH | T0025 | AST03 |
| SUSPICIOUS_URL | HIGH | T0010 | AST05, AST07 |
| RUNTIME_CODE_FETCH | HIGH | T0010, T0050 | AST05 |
| CREDENTIAL_IN_URL | HIGH | T0025 | AST09 |
| SEC-011 (YAML bare Bash) | HIGH | T0011, T0050 | AST03 |
| SEC-013 (hook shell injection) | HIGH | T0050 | AST06 |
| ENCODED_CONTENT | MEDIUM | T0051.001 | AST07 |
| WRITE_TO_CLAUDE_DIR | MEDIUM | T0010 | AST05 |
| GIT_FORCE_PUSH | MEDIUM | T0049 | AST03 |
| SYSTEM_SERVICE_MOD | MEDIUM | T0050 | AST03 |
| SEC-012 (>10 tools) | MEDIUM | T0011 | AST03 |

## MITRE ATLAS techniques referenced

- **AML.T0010** — ML Supply Chain Compromise
- **AML.T0011** — LLM Plugin Compromise
- **AML.T0024** — Exfiltration via ML Inference API
- **AML.T0025** — Exfiltration via Cyber Means
- **AML.T0049** — Exploit Public-Facing Application
- **AML.T0050** — Command and Scripting Interpreter
- **AML.T0051.000 / .001** — LLM Prompt Injection (Direct / Indirect)
- **AML.T0054** — LLM Jailbreak

Canonical reference: https://atlas.mitre.org/matrices/ATLAS

## OWASP Agentic Skills Top-10 (provisional)

Labels below are the working mapping used by AgentGuard; the authoritative text is maintained at https://owasp.org/www-project-agentic-skills-top-10/. Michael owns re-validation before any external publication.

| ID | Risk |
|---|---|
| AST01 | Prompt Injection |
| AST02 | Sensitive Information Disclosure |
| AST03 | Excessive Agency / Over-privileged Skills |
| AST04 | Insecure Output Handling |
| AST05 | Supply Chain Vulnerabilities |
| AST06 | Insecure Tool Invocation |
| AST07 | Hidden / Obfuscated Instructions |
| AST08 | Insecure Permission Modes |
| AST09 | Credential Exposure in Skills |
| AST10 | Indirect Prompt Injection via Tool Outputs |

## Defence layers

1. **Layer 1 — Config-time**: static scan with taxonomy-tagged findings + Behavioral Sandbox Replay + Counterfactual Replay Gate.
2. **Layer 2 — Runtime**: HLOT-extended OTel spans, Runtime Fingerprint Divergence Detection, BATT Shield runtime tool-grant narrowing.
3. **Layer 3 — Post-incident**: Bidirectional Causal Incident Lineage joins app-layer incidents to asset content hashes.

Each layer maps back to the six attack classes so no class is covered by a single control.

## Out of scope

- Attacks on the underlying model weights or hosted LLM provider.
- Exploitation of the developer's OS / IDE outside the agent process tree.
- Compromise of the OTel collector or Grail ingestion pipeline (assumed trusted infrastructure).
