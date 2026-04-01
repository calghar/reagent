import enum
import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from reagent.core.parsers import (
    AgentAsset,
    HookAsset,
    HookEntry,
    ParsedAsset,
    SettingsAsset,
    SkillAsset,
)

logger = logging.getLogger(__name__)


class Severity(enum.StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"


class SecurityFinding(BaseModel):
    """A single security finding from the static analyzer."""

    rule_id: str
    severity: Severity
    line_number: int
    matched_text: str
    description: str
    file_path: Path


class ScanReport(BaseModel):
    """Result of a security scan."""

    findings: list[SecurityFinding] = Field(default_factory=list)
    risk_score: float = 0.0
    verdict: str = "pass"
    files_scanned: int = 0

    def add(self, finding: SecurityFinding) -> None:
        """Add a finding and recalculate risk score."""
        self.findings.append(finding)
        self._recalculate()

    def merge(self, other: "ScanReport") -> None:
        """Merge another report into this one."""
        self.findings.extend(other.findings)
        self.files_scanned += other.files_scanned
        self._recalculate()

    def _recalculate(self) -> None:
        weights = {Severity.CRITICAL: 10.0, Severity.HIGH: 5.0, Severity.MEDIUM: 2.0}
        self.risk_score = sum(weights.get(f.severity, 0) for f in self.findings)
        has_critical = any(f.severity == Severity.CRITICAL for f in self.findings)
        self.verdict = "fail" if has_critical or self.risk_score >= 10 else "pass"


# A checker function takes (content, file_path) and returns findings.
CheckerFn = Callable[[str, Path], list[SecurityFinding]]


@dataclass
class SecurityRule:
    """A single security rule definition.

    Rules can be either pattern-based (using a regex pattern that is checked
    line-by-line) or custom (using a checker function for complex logic).
    """

    rule_id: str
    severity: Severity
    description: str
    pattern: re.Pattern[str] | None = None
    checker: CheckerFn | None = None
    tags: list[str] = field(default_factory=list)
    enabled: bool = True
    references: list[str] = field(default_factory=list)


# Module-level rule registry
_RULE_REGISTRY: list[SecurityRule] = []


def register_rule(rule: SecurityRule) -> None:
    """Register a new security rule."""
    # Replace existing rule with same id
    for i, existing in enumerate(_RULE_REGISTRY):
        if existing.rule_id == rule.rule_id:
            _RULE_REGISTRY[i] = rule
            return
    _RULE_REGISTRY.append(rule)


def unregister_rule(rule_id: str) -> bool:
    """Remove a rule by ID. Returns True if found and removed."""
    for i, rule in enumerate(_RULE_REGISTRY):
        if rule.rule_id == rule_id:
            _RULE_REGISTRY.pop(i)
            return True
    return False


def get_rules() -> list[SecurityRule]:
    """Return a copy of the current rule registry."""
    return list(_RULE_REGISTRY)


def get_rule(rule_id: str) -> SecurityRule | None:
    """Look up a single rule by ID."""
    for rule in _RULE_REGISTRY:
        if rule.rule_id == rule_id:
            return rule
    return None


# Hidden unicode categories: zero-width chars, RTL overrides, etc.
_HIDDEN_UNICODE_CATS = {"Cf", "Mn", "Co"}
_ALLOWED_HIDDEN = {"\n", "\r", "\t", "\u00ad"}  # soft hyphen is common

_PROMPT_INJECTION_RE = re.compile(
    r"(ignore|disregard|forget|override|bypass)\s+"
    r"(all\s+)?(previous|above|prior|earlier|system|original)\s+"
    r"(instructions|rules|guidelines|constraints|prompts|directives)",
    re.IGNORECASE,
)

_PERMISSION_ESCALATION_RE = re.compile(
    r"permissionMode\s*:\s*(bypassPermissions|dontAsk)", re.IGNORECASE
)

_UNRESTRICTED_BASH_RE = re.compile(
    r"allowed[_-]?tools\s*:.*\bBash\b(?!\()", re.IGNORECASE
)

_SHELL_PIPE_RE = re.compile(
    r"(curl|wget)\s+[^\n|]*\|\s*(sh|bash|python|python3|ruby|perl|zsh)", re.IGNORECASE
)

_SENSITIVE_FILE_RE = re.compile(
    r"(\.ssh|\.aws|\.gnupg|\.gpg|\.env\b|\.netrc|id_rsa|id_ed25519|credentials)",
    re.IGNORECASE,
)

_SECRET_EXFIL_RE = re.compile(
    r"(curl|wget|fetch|http)\s+[^\n]*(API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIALS)",
    re.IGNORECASE,
)

_BASE64_RE = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")

_WRITE_CLAUDE_DIR_RE = re.compile(r"Write\s*\(?\s*[\"']?\.claude/", re.IGNORECASE)

_GIT_FORCE_PUSH_RE = re.compile(r"git\s+push\s+--force", re.IGNORECASE)

_EXTERNAL_URL_RE = re.compile(
    r"https?://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])[^\s\"']+", re.IGNORECASE
)

_HARDCODED_SECRETS_RE = re.compile(
    r"(api[_-]?key|password|secret|token)\s*[=:]\s*[\"'][^\s\"']{8,}", re.IGNORECASE
)

_SHELL_INJECTION_RE = re.compile(r"\$\{[^}]+\}|\$\([^)]+\)|`[^`]+`")
# Markdown-safe variant: only match ${ } and $( ), skip backticks
# which are legitimate inline-code formatting in .md files.
_SHELL_INJECTION_MD_RE = re.compile(r"\$\{[^}]+\}|\$\([^)]+\)")

_FILESYSTEM_ESCAPE_RE = re.compile(r"\.\./\.\./|/etc/|/usr/|/root/")

# New patterns from threat research (Snyk Agent Scan, Invariant Labs, OWASP LLM Top 10)

# Snyk E001/E003 + Invariant Labs: Tool poisoning via HTML-like attention tags
_TOOL_POISONING_TAGS_RE = re.compile(
    r"<\s*(IMPORTANT|CRITICAL|SYSTEM|INSTRUCTION|OVERRIDE|NOTE_TO_ASSISTANT|ADMIN|PRIORITY"
    r"|MANDATORY|HIDDEN|SECRET_INSTRUCTION|DO_NOT_DISPLAY)\b[^>]*>",
    re.IGNORECASE,
)

# Snyk E004 + OWASP LLM01: Role/persona hijacking
_ROLE_HIJACKING_RE = re.compile(
    r"(you\s+are\s+now|act\s+as|your\s+new\s+role\s+is|pretend\s+to\s+be"
    r"|assume\s+the\s+role|from\s+now\s+on\s+you\s+are"
    r"|switch\s+to\s+(?:a\s+)?(?:new\s+)?(?:mode|persona|identity))",
    re.IGNORECASE,
)

# Snyk E005: Suspicious download URLs (shorteners, raw IPs, paste sites)
_SUSPICIOUS_URL_RE = re.compile(
    r"https?://(?:"
    r"bit\.ly|tinyurl\.com|t\.co|is\.gd|goo\.gl|rb\.gy|cutt\.ly|shorturl\.at"
    r"|pastebin\.com|ghostbin\.com|hastebin\.com|dpaste\.org|paste\.ee"
    r"|transfer\.sh|file\.io|temp\.sh|0x0\.st"
    r"|(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?"
    r")/[^\s\"']*",
    re.IGNORECASE,
)

# Snyk W012: Runtime code fetching + execution (beyond simple pipe)
_RUNTIME_CODE_FETCH_RE = re.compile(
    r"(?:source\s+<\(curl|eval\s+\"\$\(curl|eval\s+\"\$\(wget"
    r"|python[3]?\s+-c\s+[\"'].*(?:urllib|requests)\.get"
    r"|node\s+-e\s+[\"'].*(?:fetch|https?\.get))",
    re.IGNORECASE,
)

# Snyk W013: System service modification
_SYSTEM_SERVICE_MOD_RE = re.compile(
    r"(?:crontab\s+-[el]|launchctl\s+(?:load|install|bootstrap)"
    r"|systemctl\s+(?:enable|start|daemon-reload)"
    r"|/etc/init\.d/|rc\.local|\.bashrc|\.zshrc|\.profile|\.bash_profile"
    r"|sudoers|visudo)",
    re.IGNORECASE,
)

# Snyk W007: Credential leakage in URLs
_CREDENTIAL_IN_URL_RE = re.compile(
    r"https?://[^:]+:[^@]+@[^\s\"']+",
    re.IGNORECASE,
)

# SEC-010: bypassPermissions in permissionMode with quoted/spaced variants
_BYPASS_PERMISSIONS_RE = re.compile(
    r'permissionMode["\s:]+bypassPermissions',
    re.IGNORECASE,
)

# SEC-013: Shell variable expansion in any context (hook command fields specifically)
_SHELL_INJECTION_HOOK_RE = re.compile(r"\$\{[^}]+\}|\$\([^)]+\)")

# SEC-014: Stronger hardcoded-secret pattern covering bearer tokens etc.
_HARDCODED_SECRET_STRONG_RE = re.compile(
    r"(?i)(api[_-]?key|secret[_-]?key|password|token|bearer)"
    r"\s*[:=]\s*[\"']?[A-Za-z0-9+/]{16,}[\"']?"
)


def _check_lines(
    content: str,
    file_path: Path,
    pattern: re.Pattern[str],
    rule_id: str,
    severity: Severity,
    description: str,
) -> list[SecurityFinding]:
    """Check each line of content against a regex pattern."""
    findings: list[SecurityFinding] = []
    for i, line in enumerate(content.splitlines(), 1):
        match = pattern.search(line)
        if match:
            findings.append(
                SecurityFinding(
                    rule_id=rule_id,
                    severity=severity,
                    line_number=i,
                    matched_text=match.group(0),
                    description=description,
                    file_path=file_path,
                )
            )
    return findings


def _check_shell_injection(content: str, file_path: Path) -> list[SecurityFinding]:
    """Check for shell injection, using a markdown-safe regex for .md files."""
    is_markdown = file_path.suffix.lower() == ".md"
    pattern = _SHELL_INJECTION_MD_RE if is_markdown else _SHELL_INJECTION_RE
    return _check_lines(
        content,
        file_path,
        pattern,
        "SHELL_INJECTION",
        Severity.HIGH,
        "Shell injection via unescaped variable interpolation",
    )


def _check_hidden_unicode(content: str, file_path: Path) -> list[SecurityFinding]:
    """Detect hidden unicode characters (zero-width, RTL override, etc.)."""
    findings: list[SecurityFinding] = []
    for i, line in enumerate(content.splitlines(), 1):
        for ch in line:
            if ch in _ALLOWED_HIDDEN:
                continue
            cat = unicodedata.category(ch)
            if cat in _HIDDEN_UNICODE_CATS:
                findings.append(
                    SecurityFinding(
                        rule_id="HIDDEN_UNICODE",
                        severity=Severity.CRITICAL,
                        line_number=i,
                        matched_text=f"U+{ord(ch):04X}\
                             ({unicodedata.name(ch, 'UNKNOWN')})",
                        description="Hidden Unicode character that could obscure\
                             malicious content",
                        file_path=file_path,
                    )
                )
                break  # One finding per line is enough
    return findings


def _check_external_hook_url(content: str, file_path: Path) -> list[SecurityFinding]:
    """Detect HTTP hooks pointing to external servers."""
    findings: list[SecurityFinding] = []
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        # Look for http hook type near a URL pointing externally
        if "type" in line and "http" in line.lower():
            # Check surrounding lines for external URL
            context_start = max(0, i - 3)
            context_end = min(len(lines), i + 3)
            context = "\n".join(lines[context_start:context_end])
            url_match = _EXTERNAL_URL_RE.search(context)
            if url_match:
                findings.append(
                    SecurityFinding(
                        rule_id="EXTERNAL_HOOK_URL",
                        severity=Severity.CRITICAL,
                        line_number=i,
                        matched_text=url_match.group(0),
                        description="HTTP hook pointing to an external server",
                        file_path=file_path,
                    )
                )
    return findings


def _parse_frontmatter_yaml(content: str) -> dict[str, object] | None:
    """Safely parse the YAML frontmatter from raw file content.

    Handles multi-document YAML (frontmatter + body separated by ``---``).

    Args:
        content: Raw file text potentially starting with ``---``.

    Returns:
        Parsed dict, or ``None`` on any error.
    """
    import yaml  # lazy import — yaml used only in checker paths

    fm_text = _extract_frontmatter_text(content)
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        logger.warning("Failed to parse YAML frontmatter: %s", exc)
        return None
    return data if isinstance(data, dict) else None


def _extract_frontmatter_text(content: str) -> str:
    """Extract just the YAML portion from frontmatter-delimited content.

    Args:
        content: Raw file content.

    Returns:
        The YAML frontmatter text (without ``---`` delimiters) or the
        full content if no frontmatter structure is detected.
    """
    stripped = content.strip()
    if not stripped.startswith("---"):
        return stripped
    # Skip the opening ---
    rest = stripped[3:]
    # Find the closing ---
    end = rest.find("\n---")
    if end != -1:
        return rest[:end].strip()
    return rest.strip()


def _check_unrestricted_bash_yaml(
    content: str, file_path: Path
) -> list[SecurityFinding]:
    """SEC-011: Bare ``Bash`` in YAML tools list (no parenthetical restriction).

    Args:
        content: Raw file content.
        file_path: File path for reporting.

    Returns:
        List of findings (at most one per file).
    """
    data = _parse_frontmatter_yaml(content)
    if data is None:
        return []

    tools = data.get("tools", [])
    if not isinstance(tools, list):
        return []

    for tool in tools:
        if isinstance(tool, str) and tool.strip() == "Bash":
            return [
                SecurityFinding(
                    rule_id="SEC-011",
                    severity=Severity.HIGH,
                    line_number=1,
                    matched_text=f"tools: {tools}",
                    description=(
                        "Bash tool without restrictions allows arbitrary"
                        " command execution"
                    ),
                    file_path=file_path,
                )
            ]
    return []


def _check_missing_tool_restrictions(
    content: str, file_path: Path
) -> list[SecurityFinding]:
    """SEC-012: Agent frontmatter with more than 10 tools.

    Args:
        content: Raw file content.
        file_path: File path for reporting.

    Returns:
        List with one finding if the rule fires, else empty.
    """
    data = _parse_frontmatter_yaml(content)
    if data is None or "agent" not in data:
        return []

    tools = data.get("tools", [])
    if not isinstance(tools, list) or len(tools) <= 10:
        return []

    return [
        SecurityFinding(
            rule_id="SEC-012",
            severity=Severity.MEDIUM,
            line_number=1,
            matched_text=f"{len(tools)} tools",
            description=(
                "Agent has unrestricted tool access (>10 tools)."
                " Consider limiting to required tools."
            ),
            file_path=file_path,
        )
    ]


def _check_shell_injection_in_hooks(
    content: str, file_path: Path
) -> list[SecurityFinding]:
    """SEC-013: Shell variable expansion found in hook command fields.

    Parses YAML to target only the ``command`` field of hook entries,
    reducing false positives compared to a raw line-by-line scan.

    Args:
        content: Raw file content.
        file_path: File path for reporting.

    Returns:
        List of findings (one per affected hook command).
    """
    data = _parse_frontmatter_yaml(content)
    if data is None:
        return []

    hooks = data.get("hooks", {})
    if not isinstance(hooks, dict):
        return []

    findings: list[SecurityFinding] = []
    for hook_list in hooks.values():
        if not isinstance(hook_list, list):
            continue
        for hook in hook_list:
            if not isinstance(hook, dict):
                continue
            cmd = hook.get("command", "")
            if isinstance(cmd, str) and _SHELL_INJECTION_HOOK_RE.search(cmd):
                findings.append(
                    SecurityFinding(
                        rule_id="SEC-013",
                        severity=Severity.HIGH,
                        line_number=1,
                        matched_text=cmd[:80],
                        description=(
                            "Shell variable expansion in hook command"
                            " may allow injection"
                        ),
                        file_path=file_path,
                    )
                )
    return findings


def _register_builtin_rules() -> None:
    """Register all built-in security rules."""
    # -- Critical rules --
    register_rule(
        SecurityRule(
            rule_id="PROMPT_INJECTION_OVERRIDE",
            severity=Severity.CRITICAL,
            description="Prompt injection: attempts to override system instructions",
            pattern=_PROMPT_INJECTION_RE,
            tags=["prompt-injection"],
            references=["OWASP LLM01", "Snyk E001/E004"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="PERMISSION_ESCALATION",
            severity=Severity.CRITICAL,
            description="Permission escalation: unrestricted permission mode",
            pattern=_PERMISSION_ESCALATION_RE,
            tags=["permission"],
            references=["OWASP LLM06"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="HIDDEN_UNICODE",
            severity=Severity.CRITICAL,
            description="Hidden Unicode character that could obscure malicious content",
            checker=_check_hidden_unicode,
            tags=["obfuscation"],
            references=["Snyk E001", "Invariant Labs TPA"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="EXTERNAL_HOOK_URL",
            severity=Severity.CRITICAL,
            description="HTTP hook pointing to an external server",
            checker=_check_external_hook_url,
            tags=["exfiltration", "hook"],
            references=["Snyk TF001"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="TOOL_POISONING_TAGS",
            severity=Severity.CRITICAL,
            description="HTML-like tags used to hijack agent attention",
            pattern=_TOOL_POISONING_TAGS_RE,
            tags=["prompt-injection", "tool-poisoning"],
            references=[
                "Snyk E001/E003",
                "Invariant Labs Tool Poisoning Attacks",
            ],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="ROLE_HIJACKING",
            severity=Severity.CRITICAL,
            description="Persona/role override attempting to hijack agent identity",
            pattern=_ROLE_HIJACKING_RE,
            tags=["prompt-injection"],
            references=["OWASP LLM01", "Snyk E004"],
        )
    )

    # -- High rules --
    register_rule(
        SecurityRule(
            rule_id="UNRESTRICTED_BASH",
            severity=Severity.HIGH,
            description="Unrestricted Bash grants without command restrictions",
            pattern=_UNRESTRICTED_BASH_RE,
            tags=["permission", "excessive-agency"],
            references=["OWASP LLM06"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="SHELL_PIPE_EXEC",
            severity=Severity.HIGH,
            description="Remote code downloaded and piped to shell for execution",
            pattern=_SHELL_PIPE_RE,
            tags=["supply-chain", "rce"],
            references=["OWASP LLM03", "Snyk E006"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="SENSITIVE_FILE_ACCESS",
            severity=Severity.HIGH,
            description="References to sensitive files or directories",
            pattern=_SENSITIVE_FILE_RE,
            tags=["data-leak"],
            references=["OWASP LLM02"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="SECRET_EXFILTRATION",
            severity=Severity.HIGH,
            description="Potential secret exfiltration via network call",
            pattern=_SECRET_EXFIL_RE,
            tags=["exfiltration", "data-leak"],
            references=["OWASP LLM02", "Snyk TF001"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="HARDCODED_SECRET",
            severity=Severity.HIGH,
            description="Potential hardcoded secret or credential",
            pattern=_HARDCODED_SECRETS_RE,
            tags=["credential"],
            references=["Snyk W008"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="SHELL_INJECTION",
            severity=Severity.HIGH,
            description="Shell injection via unescaped variable interpolation",
            checker=_check_shell_injection,
            tags=["injection"],
            references=["OWASP LLM05"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="FILESYSTEM_ESCAPE",
            severity=Severity.HIGH,
            description="Path references outside project scope",
            pattern=_FILESYSTEM_ESCAPE_RE,
            tags=["escape"],
            references=["OWASP LLM06"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="SUSPICIOUS_URL",
            severity=Severity.HIGH,
            description="URL shortener, raw IP,\
                 or paste site that obscures destination",
            pattern=_SUSPICIOUS_URL_RE,
            tags=["supply-chain", "obfuscation"],
            references=["Snyk E005"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="RUNTIME_CODE_FETCH",
            severity=Severity.HIGH,
            description="Dynamic code loading from external URL at runtime",
            pattern=_RUNTIME_CODE_FETCH_RE,
            tags=["supply-chain", "rce"],
            references=["Snyk W012", "Snyk E006"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="CREDENTIAL_IN_URL",
            severity=Severity.HIGH,
            description="Credentials embedded directly in URL",
            pattern=_CREDENTIAL_IN_URL_RE,
            tags=["credential", "data-leak"],
            references=["Snyk W007"],
        )
    )

    # -- Medium rules --
    register_rule(
        SecurityRule(
            rule_id="ENCODED_CONTENT",
            severity=Severity.MEDIUM,
            description="Base64-encoded content that may hide instructions",
            pattern=_BASE64_RE,
            tags=["obfuscation"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="WRITE_TO_CLAUDE_DIR",
            severity=Severity.MEDIUM,
            description="Writes to .claude/ directory which could modify configuration",
            pattern=_WRITE_CLAUDE_DIR_RE,
            tags=["config-modification"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="GIT_FORCE_PUSH",
            severity=Severity.MEDIUM,
            description="Destructive git force push operation",
            pattern=_GIT_FORCE_PUSH_RE,
            tags=["destructive"],
            references=["Snyk TF002"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="SYSTEM_SERVICE_MOD",
            severity=Severity.MEDIUM,
            description="Modification of system services, startup scripts,\
                 or shell profiles",
            pattern=_SYSTEM_SERVICE_MOD_RE,
            tags=["system-modification"],
            references=["Snyk W013"],
        )
    )

    # -- Phase 7 additions: SEC-010 through SEC-014 --
    register_rule(
        SecurityRule(
            rule_id="SEC-010",
            severity=Severity.CRITICAL,
            description=(
                "permissionMode: bypassPermissions disables all safety guardrails"
            ),
            pattern=_BYPASS_PERMISSIONS_RE,
            tags=["permission", "bypass"],
            references=["OWASP LLM06"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="SEC-011",
            severity=Severity.HIGH,
            description=(
                "Bash tool without restrictions allows arbitrary command execution"
            ),
            checker=_check_unrestricted_bash_yaml,
            tags=["permission", "excessive-agency"],
            references=["OWASP LLM06"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="SEC-012",
            severity=Severity.MEDIUM,
            description=(
                "Agent has unrestricted tool access (>10 tools)."
                " Consider limiting to required tools."
            ),
            checker=_check_missing_tool_restrictions,
            tags=["excessive-agency"],
            references=["OWASP LLM06"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="SEC-013",
            severity=Severity.HIGH,
            description="Shell variable expansion in hook command may allow injection",
            checker=_check_shell_injection_in_hooks,
            tags=["injection", "hook"],
            references=["OWASP LLM05"],
        )
    )
    register_rule(
        SecurityRule(
            rule_id="SEC-014",
            severity=Severity.CRITICAL,
            description="Hardcoded secret or credential detected",
            pattern=_HARDCODED_SECRET_STRONG_RE,
            tags=["credential", "secret"],
            references=["Snyk W008", "OWASP LLM02"],
        )
    )


# Populate registry on import
_register_builtin_rules()


def scan_content(content: str, file_path: Path) -> list[SecurityFinding]:
    """Run all registered security rules against raw content.

    Args:
        content: The text content to scan.
        file_path: Path for reporting purposes.

    Returns:
        List of security findings.
    """
    findings: list[SecurityFinding] = []
    for rule in _RULE_REGISTRY:
        if not rule.enabled:
            continue
        if rule.pattern:
            findings.extend(
                _check_lines(
                    content,
                    file_path,
                    rule.pattern,
                    rule.rule_id,
                    rule.severity,
                    rule.description,
                )
            )
        elif rule.checker:
            findings.extend(rule.checker(content, file_path))
    return findings


def scan_file(path: Path) -> ScanReport:
    """Scan a single file and return a security report.

    Args:
        path: Path to the file to scan.

    Returns:
        ScanReport with all findings.
    """
    report = ScanReport(files_scanned=1)
    if not path.exists() or not path.is_file():
        return report

    content = path.read_text(encoding="utf-8")
    findings = scan_content(content, path)
    for f in findings:
        report.add(f)
    return report


def scan_directory(directory: Path) -> ScanReport:
    """Scan all relevant files in a directory tree.

    Args:
        directory: Root directory to scan.

    Returns:
        Aggregated ScanReport from all files.
    """
    report = ScanReport()
    if not directory.exists():
        return report

    extensions = {".md", ".json", ".yaml", ".yml", ".jsonl"}
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix in extensions:
            file_report = scan_file(path)
            report.merge(file_report)

    return report


def scan_asset(asset: ParsedAsset) -> ScanReport:
    """Scan a parsed asset for security issues.

    Args:
        asset: A parsed asset from the parsers module.

    Returns:
        ScanReport with findings.
    """
    report = ScanReport(files_scanned=1)
    findings = scan_content(asset.raw_content, asset.file_path)

    # Type-specific checks
    if isinstance(asset, AgentAsset):
        findings.extend(_check_agent_specific(asset))
    elif isinstance(asset, SkillAsset):
        findings.extend(_check_skill_specific(asset))
    elif isinstance(asset, HookAsset):
        findings.extend(_check_hook_specific(asset))
    elif isinstance(asset, SettingsAsset):
        findings.extend(_check_settings_specific(asset))

    for f in findings:
        report.add(f)
    return report


def _check_agent_specific(agent: AgentAsset) -> list[SecurityFinding]:
    """Check agent-specific security concerns."""
    findings: list[SecurityFinding] = []

    # Check for unrestricted bash in tools list
    for tool in agent.tools:
        if tool.strip() == "Bash":
            findings.append(
                SecurityFinding(
                    rule_id="UNRESTRICTED_BASH",
                    severity=Severity.HIGH,
                    line_number=1,
                    matched_text=f"tools: [{', '.join(agent.tools)}]",
                    description=(
                        "Agent grants unrestricted Bash access without\
                             command restrictions"
                    ),
                    file_path=agent.file_path,
                )
            )
            break

    # Check permission mode
    if agent.permission_mode in ("bypassPermissions", "dontAsk"):
        findings.append(
            SecurityFinding(
                rule_id="PERMISSION_ESCALATION",
                severity=Severity.CRITICAL,
                line_number=1,
                matched_text=f"permissionMode: {agent.permission_mode}",
                description="Agent uses unrestricted permission mode",
                file_path=agent.file_path,
            )
        )

    return findings


def _check_skill_specific(skill: SkillAsset) -> list[SecurityFinding]:
    """Check skill-specific security concerns."""
    findings: list[SecurityFinding] = []

    for tool in skill.allowed_tools:
        if tool.strip() == "Bash":
            findings.append(
                SecurityFinding(
                    rule_id="UNRESTRICTED_BASH",
                    severity=Severity.HIGH,
                    line_number=1,
                    matched_text=f"allowed-tools: [{', '.join(skill.allowed_tools)}]",
                    description="Skill grants unrestricted Bash access",
                    file_path=skill.file_path,
                )
            )
            break

    return findings


def _check_hook_specific(hook_asset: HookAsset) -> list[SecurityFinding]:
    """Check hook-specific security concerns."""
    findings: list[SecurityFinding] = []

    entries = [
        entry
        for configs in hook_asset.events.values()
        for config in configs
        for entry in config.hooks
    ]
    for entry in entries:
        findings.extend(_check_single_hook_entry(entry, hook_asset.file_path))

    return findings


def _check_single_hook_entry(
    entry: HookEntry, file_path: Path
) -> list[SecurityFinding]:
    """Check a single hook entry for security issues."""
    findings: list[SecurityFinding] = []
    if entry.hook_type == "http" and entry.url:
        url_match = _EXTERNAL_URL_RE.match(entry.url)
        if url_match:
            findings.append(
                SecurityFinding(
                    rule_id="EXTERNAL_HOOK_URL",
                    severity=Severity.CRITICAL,
                    line_number=1,
                    matched_text=entry.url,
                    description="HTTP hook pointing to an external server",
                    file_path=file_path,
                )
            )
    if entry.command:
        findings.extend(scan_content(entry.command, file_path))
    return findings


def _check_settings_specific(settings: SettingsAsset) -> list[SecurityFinding]:
    """Check settings-specific security concerns."""
    findings: list[SecurityFinding] = []

    for perm in settings.permissions.allow:
        if perm.strip() == "Bash":
            findings.append(
                SecurityFinding(
                    rule_id="UNRESTRICTED_BASH",
                    severity=Severity.HIGH,
                    line_number=1,
                    matched_text=f"allow: {perm}",
                    description="Settings grants unrestricted Bash permission",
                    file_path=settings.file_path,
                )
            )

    return findings


def score_report(report: ScanReport) -> tuple[float, str]:
    """Convert a ScanReport to a (score, grade) tuple.

    Score is computed as ``max(0, 100 - risk_score)`` where ``risk_score``
    is the weighted sum already stored on the report.

    Args:
        report: A completed ScanReport.

    Returns:
        Tuple of (score 0-100, grade letter A-F).
    """
    score = max(0.0, 100.0 - report.risk_score)
    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"
    return score, grade


_FIX_BYPASS_RE = re.compile(r"[ \t]*permissionMode\s*:\s*bypassPermissions[ \t]*\n?")
_FIX_BARE_BASH_RE = re.compile(r'"Bash"(?!\s*\()')
_BASH_SAFE_REPLACEMENT = '"Bash(git *, npm *, python *)"'


def apply_auto_fixes(content: str) -> tuple[str, list[str]]:
    """Apply auto-fixable security transformations to file content.

    Fixes applied:
    - Remove ``permissionMode: bypassPermissions`` lines.
    - Replace bare ``"Bash"`` with a safe restricted variant.

    Args:
        content: Original file content.

    Returns:
        Tuple of (fixed content, list of human-readable fix descriptions).
    """
    fixes: list[str] = []

    fixed, count = _FIX_BYPASS_RE.subn("", content)
    if count:
        fixes.append(
            f"Removed permissionMode: bypassPermissions ({count} occurrence(s))"
        )
    content = fixed

    fixed, count = _FIX_BARE_BASH_RE.subn(_BASH_SAFE_REPLACEMENT, content)
    if count:
        fixes.append(f"Restricted bare Bash tool ({count} occurrence(s))")
    content = fixed

    return content, fixes
