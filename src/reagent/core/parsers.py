import enum
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AssetType(enum.StrEnum):
    AGENT = "agent"
    SKILL = "skill"
    HOOK = "hook"
    COMMAND = "command"
    RULE = "rule"
    CLAUDE_MD = "claude_md"
    SETTINGS = "settings"
    AGENT_MEMORY = "agent_memory"


class AssetScope(enum.StrEnum):
    GLOBAL = "global"
    PROJECT = "project"
    LOCAL = "local"


class ParsedAsset(BaseModel):
    """Base model for all parsed assets."""

    asset_type: AssetType
    name: str
    file_path: Path
    content_hash: str
    raw_content: str


class AgentAsset(ParsedAsset):
    asset_type: AssetType = AssetType.AGENT
    description: str = ""
    model: str = ""
    tools: list[str] = Field(default_factory=list)
    disallowed_tools: list[str] = Field(default_factory=list)
    permission_mode: str = ""
    max_turns: int | None = None
    skills: list[str] = Field(default_factory=list)
    hooks: dict[str, Any] = Field(default_factory=dict)
    memory: list[str] = Field(default_factory=list)
    isolation: str = ""
    effort: str = ""
    background: bool = False
    initial_prompt: str = ""
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    body: str = ""


class SkillAsset(ParsedAsset):
    asset_type: AssetType = AssetType.SKILL
    description: str = ""
    argument_hint: str = ""
    disable_model_invocation: bool = False
    user_invocable: bool = True
    allowed_tools: list[str] = Field(default_factory=list)
    model: str = ""
    effort: str = ""
    context: str = ""
    agent: str = ""
    paths: list[str] = Field(default_factory=list)
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    body: str = ""


class HookEntry(BaseModel):
    hook_type: str  # command, http, prompt, agent
    command: str = ""
    url: str = ""
    prompt: str = ""
    timeout: int | None = None
    is_async: bool = False
    condition: str = ""


class HookEventConfig(BaseModel):
    matcher: str = "*"
    hooks: list[HookEntry] = Field(default_factory=list)


class HookAsset(ParsedAsset):
    asset_type: AssetType = AssetType.HOOK
    events: dict[str, list[HookEventConfig]] = Field(default_factory=dict)


class CommandAsset(ParsedAsset):
    asset_type: AssetType = AssetType.COMMAND
    description: str = ""
    body: str = ""


class RuleAsset(ParsedAsset):
    asset_type: AssetType = AssetType.RULE
    description: str = ""
    apply_to: str = ""
    paths: list[str] = Field(default_factory=list)
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    body: str = ""


class SettingsPermissions(BaseModel):
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    ask: list[str] = Field(default_factory=list)


class SettingsAsset(ParsedAsset):
    asset_type: AssetType = AssetType.SETTINGS
    permissions: SettingsPermissions = Field(default_factory=SettingsPermissions)
    has_hooks: bool = False
    raw_data: dict[str, Any] = Field(default_factory=dict)


class ClaudeMdAsset(ParsedAsset):
    asset_type: AssetType = AssetType.CLAUDE_MD
    body: str = ""
    line_count: int = 0
    has_imports: bool = False


class AgentMemoryAsset(ParsedAsset):
    asset_type: AssetType = AssetType.AGENT_MEMORY
    memory_files: list[str] = Field(default_factory=list)


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content.

    Args:
        content: The text content to hash.

    Returns:
        Hex-encoded SHA-256 digest.
    """
    return hashlib.sha256(content.encode()).hexdigest()


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter from markdown body.

    Args:
        text: Full markdown text possibly starting with ``---`` delimiters.

    Returns:
        Tuple of (frontmatter_dict, body_text). Returns empty dict
        if no valid frontmatter is found.
    """
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return {}, text

    # Find closing ---
    rest = stripped[3:]
    newline_idx = rest.find("\n")
    if newline_idx == -1:
        return {}, text

    # Check if there's content on the same line as opening ---
    first_line = rest[:newline_idx].strip()
    if first_line:
        return {}, text

    rest = rest[newline_idx + 1 :]

    # Handle closing --- at very start (empty frontmatter)
    if rest.startswith("---\n") or rest.rstrip("\n") == "---":
        yaml_text = ""
        body = rest[3:].lstrip("\n")
    else:
        end_idx = rest.find("\n---")
        if end_idx == -1:
            return {}, text
        yaml_text = rest[:end_idx]
        body = rest[end_idx + 4 :].lstrip("\n")

    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return {}, text

    if data is None:
        data = {}
    elif not isinstance(data, dict):
        return {}, text

    return data, body


def _normalize_tool_list(value: Any) -> list[str]:
    """Normalize tools from YAML (can be list or comma-separated string).

    Args:
        value: Raw YAML value (list, string, or other).

    Returns:
        List of trimmed tool name strings.
    """
    if isinstance(value, list):
        return [str(t).strip() for t in value]
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    return []


def parse_agent(path: Path) -> AgentAsset:
    """Parse an agent .md file from .claude/agents/.

    Args:
        path: Path to the agent markdown file.

    Returns:
        Populated AgentAsset with frontmatter and body extracted.
    """
    content = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(content)

    return AgentAsset(
        name=frontmatter.get("name", path.stem),
        file_path=path,
        content_hash=compute_content_hash(content),
        raw_content=content,
        description=frontmatter.get("description", ""),
        model=str(frontmatter.get("model", "")),
        tools=_normalize_tool_list(frontmatter.get("tools", [])),
        disallowed_tools=_normalize_tool_list(frontmatter.get("disallowedTools", [])),
        permission_mode=str(frontmatter.get("permissionMode", "")),
        max_turns=frontmatter.get("maxTurns"),
        skills=_normalize_tool_list(frontmatter.get("skills", [])),
        hooks=frontmatter.get("hooks", {}),
        memory=_normalize_tool_list(frontmatter.get("memory", [])),
        isolation=str(frontmatter.get("isolation", "")),
        effort=str(frontmatter.get("effort", "")),
        background=bool(frontmatter.get("background", False)),
        initial_prompt=str(frontmatter.get("initialPrompt", "")),
        frontmatter=frontmatter,
        body=body,
    )


def parse_skill(path: Path) -> SkillAsset:
    """Parse a SKILL.md file from .claude/skills/<name>/.

    Args:
        path: Path to the SKILL.md file.

    Returns:
        Populated SkillAsset with frontmatter and body extracted.
    """
    content = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(content)

    return SkillAsset(
        name=frontmatter.get("name", path.parent.name),
        file_path=path,
        content_hash=compute_content_hash(content),
        raw_content=content,
        description=frontmatter.get("description", ""),
        argument_hint=str(frontmatter.get("argument-hint", "")),
        disable_model_invocation=bool(
            frontmatter.get("disable-model-invocation", False)
        ),
        user_invocable=bool(frontmatter.get("user-invocable", True)),
        allowed_tools=_normalize_tool_list(frontmatter.get("allowed-tools", [])),
        model=str(frontmatter.get("model", "")),
        effort=str(frontmatter.get("effort", "")),
        context=str(frontmatter.get("context", "")),
        agent=str(frontmatter.get("agent", "")),
        paths=_normalize_tool_list(frontmatter.get("paths", [])),
        frontmatter=frontmatter,
        body=body,
    )


def _parse_hook_entries(raw_hooks: list[dict[str, Any]]) -> list[HookEntry]:
    """Parse a list of raw hook dicts into HookEntry models.

    Args:
        raw_hooks: List of hook configuration dicts from JSON.

    Returns:
        List of validated HookEntry models.
    """
    entries: list[HookEntry] = []
    for h in raw_hooks:
        entries.append(
            HookEntry(
                hook_type=h.get("type", "command"),
                command=str(h.get("command", "")),
                url=str(h.get("url", "")),
                prompt=str(h.get("prompt", "")),
                timeout=h.get("timeout"),
                is_async=bool(h.get("async", False)),
                condition=str(h.get("if", "")),
            )
        )
    return entries


def parse_hooks(path: Path) -> HookAsset:
    """Parse hooks from a settings.json or hooks.json file.

    Args:
        path: Path to the JSON file containing hook definitions.

    Returns:
        HookAsset with events mapped to their hook configurations.
    """
    content = path.read_text(encoding="utf-8")
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return HookAsset(
            name=path.name,
            file_path=path,
            content_hash=compute_content_hash(content),
            raw_content=content,
        )

    hooks_data = data.get("hooks", {})
    events: dict[str, list[HookEventConfig]] = {}

    for event_name, event_configs in hooks_data.items():
        if not isinstance(event_configs, list):
            continue
        configs: list[HookEventConfig] = []
        for cfg in event_configs:
            matcher = cfg.get("matcher", "*")
            hook_entries = _parse_hook_entries(cfg.get("hooks", []))
            configs.append(HookEventConfig(matcher=matcher, hooks=hook_entries))
        events[event_name] = configs

    return HookAsset(
        name=path.name,
        file_path=path,
        content_hash=compute_content_hash(content),
        raw_content=content,
        events=events,
    )


def parse_command(path: Path) -> CommandAsset:
    """Parse a command .md file from .claude/commands/.

    Args:
        path: Path to the command markdown file.

    Returns:
        Populated CommandAsset with description and body.
    """
    content = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(content)

    # Commands may or may not have frontmatter
    description = frontmatter.get("description", "")
    if not body:
        body = content

    return CommandAsset(
        name=path.stem,
        file_path=path,
        content_hash=compute_content_hash(content),
        raw_content=content,
        description=description,
        body=body,
    )


def parse_rule(path: Path) -> RuleAsset:
    """Parse a rule .md file from .claude/rules/.

    Args:
        path: Path to the rule markdown file.

    Returns:
        Populated RuleAsset with frontmatter and body.
    """
    content = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(content)

    return RuleAsset(
        name=path.stem,
        file_path=path,
        content_hash=compute_content_hash(content),
        raw_content=content,
        description=frontmatter.get("description", ""),
        apply_to=str(frontmatter.get("applyTo", "")),
        paths=_normalize_tool_list(frontmatter.get("paths", [])),
        frontmatter=frontmatter,
        body=body,
    )


def parse_settings(path: Path) -> SettingsAsset:
    """Parse a settings.json or settings.local.json file.

    Args:
        path: Path to the settings JSON file.

    Returns:
        SettingsAsset with extracted permissions and raw data.
    """
    content = path.read_text(encoding="utf-8")
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return SettingsAsset(
            name=path.name,
            file_path=path,
            content_hash=compute_content_hash(content),
            raw_content=content,
        )

    perms = data.get("permissions", {})
    permissions = SettingsPermissions(
        allow=perms.get("allow", []),
        deny=perms.get("deny", []),
        ask=perms.get("ask", []),
    )

    return SettingsAsset(
        name=path.name,
        file_path=path,
        content_hash=compute_content_hash(content),
        raw_content=content,
        permissions=permissions,
        has_hooks="hooks" in data,
        raw_data=data,
    )


def parse_claude_md(path: Path) -> ClaudeMdAsset:
    """Parse a CLAUDE.md file.

    Args:
        path: Path to the CLAUDE.md file.

    Returns:
        ClaudeMdAsset with body content and metadata.
    """
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Detect @import or similar inclusion patterns
    has_imports = any(
        line.strip().startswith("@import") or line.strip().startswith("!include")
        for line in lines
    )

    return ClaudeMdAsset(
        name="CLAUDE.md",
        file_path=path,
        content_hash=compute_content_hash(content),
        raw_content=content,
        body=content,
        line_count=len(lines),
        has_imports=has_imports,
    )


def parse_agent_memory(path: Path) -> AgentMemoryAsset:
    """Parse agent-memory directory contents.

    Args:
        path: Path to the agent-memory directory.

    Returns:
        AgentMemoryAsset listing all memory files found.
    """
    memory_files: list[str] = []
    if path.is_dir():
        for f in sorted(path.iterdir()):
            if f.is_file():
                memory_files.append(f.name)

    # Use directory listing as "content" for hashing
    content = "\n".join(memory_files) if memory_files else ""

    return AgentMemoryAsset(
        name="agent-memory",
        file_path=path,
        content_hash=compute_content_hash(content),
        raw_content=content,
        memory_files=memory_files,
    )
