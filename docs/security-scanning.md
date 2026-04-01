# Security Scanning

Reagent includes a security pipeline for auditing Claude Code assets. This covers static analysis, import security, trust management, and integrity monitoring.

## How `reagent scan` Works

The scanner reads asset files (agents, skills, hooks, commands, rules, settings) and applies 20+ static analysis rules to detect security issues.

```bash
reagent scan ./path/to/file          # Scan a single file
reagent scan ./my-project/.claude    # Scan an entire directory
reagent audit --repo ./my-project    # Audit a repo's .claude/ directory
```

Each finding includes:

- **Rule ID** — unique identifier (e.g., `SEC-001`)
- **Severity** — critical, high, or medium
- **File and line number** — where the issue was found
- **Description** — what the rule detected

The scanner produces a risk score and a pass/fail verdict.

## Rule Categories

### Critical

Rules that detect dangerous patterns requiring immediate attention:

- Unrestricted tool access (e.g., `tools: ["*"]` or no tool restrictions)
- `bypassPermissions` or `dontAsk` permission modes
- Shell injection patterns in hook commands
- Secrets or credentials in asset content

### High

Rules that detect significant security concerns:

- Overly broad file write permissions
- External URL references in prompts
- Unsafe environment variable expansion
- Missing tool restrictions on imported assets

### Medium

Rules that detect potential issues worth reviewing:

- Large prompt sizes that may hide injected content
- Unused or stale assets with elevated trust
- Missing description fields (reduces auditability)

## Import Pipeline

When importing assets from external sources, Reagent enforces a multi-stage security pipeline:

```text
Fetch → Isolate → Scan → Review → Install
```

1. **Fetch** — Download from local path, git URL, or gist into a staging directory
2. **Isolate** — Staged files are quarantined, not yet accessible to Claude Code
3. **Scan** — Full static analysis runs on staged content
4. **Review** — Human review gate: scan results are displayed, and explicit approval is required
5. **Install** — Approved assets are copied to the target repo's `.claude/` directory with trust level set to UNTRUSTED

```bash
reagent import https://gist.github.com/user/abc123
reagent import ./shared-agent.md --target-repo ./my-project
```

## Trust Model

Reagent uses a 4-level trust model for assets:

| Level | Name | Description |
| --- | --- | --- |
| 3 | VERIFIED | Cryptographically verified or promoted after extended use |
| 2 | REVIEWED | Manually reviewed and promoted by a human |
| 1 | NATIVE | Created locally within the repository |
| 0 | UNTRUSTED | Imported from external source, not yet reviewed |

### Managing Trust

```bash
reagent trust show <asset-id>                          # View trust level
reagent trust promote <asset-id> --level 2 --reason "Reviewed"  # Promote
```

Trust transitions are logged with timestamps and reasons for audit trails.

### Trust Rules

- Imported assets always start at UNTRUSTED (level 0)
- Promotion requires an explicit reason
- Trust cannot skip levels (0 → 1 → 2 → 3)
- Modifications reset trust to the lower of current level and NATIVE

## Integrity Monitoring

Reagent tracks content hashes for all cataloged assets. The integrity checker detects unauthorized modifications:

```bash
reagent integrity check     # Verify all asset hashes
reagent integrity report    # Show modified/missing assets
```

The checker compares current file hashes against the catalog and reports:

- **Modified** — file content has changed since last scan
- **Missing** — file has been deleted but is still in the catalog

Integrity events are logged to `~/.reagent/security/integrity-log.jsonl` for audit trails.

## Snapshots and Rollback

All asset versions are stored in a content-addressed snapshot store:

```bash
reagent history <asset-id>              # View version timeline
reagent rollback <asset-id> --snapshot 3  # Restore a previous version
reagent rollback-best <asset-id>        # Restore best-quality version
```

Snapshots are triggered on catalog updates, imports, and manual changes.
