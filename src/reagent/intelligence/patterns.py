import logging
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from reagent.core.catalog import Catalog, CatalogEntry
from reagent.core.parsers import AssetType, _split_frontmatter

logger = logging.getLogger(__name__)


class PatternParameter(BaseModel):
    """A parameter slot in a pattern template."""

    type: str = "string"
    example: str = ""
    inferred_from: str = ""
    optional: bool = False
    default: str = ""


class PatternStage(BaseModel):
    """A single stage in a pipeline pattern."""

    skill: str = ""
    asset_type: str = "skill"
    name: str = ""
    template: str = ""


class PatternTemplate(BaseModel):
    """A reusable pattern template with parameter slots."""

    name: str
    description: str = ""
    pattern_type: str = ""  # feature-pipeline, agent-archetype, hook-pattern, etc.
    parameters: dict[str, PatternParameter] = Field(default_factory=dict)
    stages: list[PatternStage] = Field(default_factory=list)
    assets: list[dict[str, Any]] = Field(default_factory=list)
    instances: list[dict[str, Any]] = Field(default_factory=list)

    def save(self, output_dir: Path | None = None) -> Path:
        """Save the pattern template to YAML.

        Args:
            output_dir: Override directory. Defaults to ~/.reagent/patterns/.

        Returns:
            Path to the saved pattern file.
        """
        dest = output_dir or (Path.home() / ".reagent" / "patterns")
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{self.name}.yaml"
        path.write_text(
            yaml.dump(
                self.model_dump(exclude_defaults=True),
                default_flow_style=False,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load_pattern(
        cls,
        name: str,
        patterns_dir: Path | None = None,
    ) -> "PatternTemplate | None":
        """Load a saved pattern template.

        Args:
            name: Pattern name (filename stem).
            patterns_dir: Override patterns directory.

        Returns:
            Loaded PatternTemplate, or None if not found.
        """
        directory = patterns_dir or (Path.home() / ".reagent" / "patterns")
        path = directory / f"{name}.yaml"
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return cls.model_validate(data)

    def render(self, params: dict[str, str]) -> list[dict[str, str]]:
        """Render the pattern template with concrete parameter values.

        Args:
            params: Parameter name to value mapping.

        Returns:
            List of dicts with 'name', 'type', and 'content' keys.
        """
        rendered: list[dict[str, str]] = []
        for stage in self.stages:
            content = stage.template
            for key, value in params.items():
                content = content.replace(f"{{{{{key}}}}}", value)
            rendered.append(
                {
                    "name": stage.skill or stage.name,
                    "type": stage.asset_type,
                    "content": content,
                }
            )
        for asset in self.assets:
            template = asset.get("template", "")
            content = template
            for key, value in params.items():
                content = content.replace(f"{{{{{key}}}}}", value)
            rendered.append(
                {
                    "name": asset.get("name", ""),
                    "type": asset.get("type", "skill"),
                    "content": content,
                }
            )
        return rendered


def list_patterns(patterns_dir: Path | None = None) -> list[PatternTemplate]:
    """List all saved pattern templates.

    Args:
        patterns_dir: Override patterns directory.

    Returns:
        List of loaded PatternTemplate objects.
    """
    directory = patterns_dir or (Path.home() / ".reagent" / "patterns")
    if not directory.exists():
        return []

    patterns: list[PatternTemplate] = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "name" in data:
            patterns.append(PatternTemplate.model_validate(data))
    return patterns


# --- Pattern Extraction ---


def _similarity(a: str, b: str) -> float:
    """Compute text similarity ratio between two strings."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _cluster_by_description(
    entries: list[tuple[CatalogEntry, dict[str, Any], str]],
    threshold: float = 0.5,
) -> list[list[tuple[CatalogEntry, dict[str, Any], str]]]:
    """Group assets by description similarity.

    Args:
        entries: List of (CatalogEntry, frontmatter, body) tuples.
        threshold: Minimum similarity to place in same cluster.

    Returns:
        List of clusters, each a list of entries.
    """
    clusters: list[list[tuple[CatalogEntry, dict[str, Any], str]]] = []
    assigned = set()

    for i, (entry_a, fm_a, body_a) in enumerate(entries):
        if i in assigned:
            continue
        cluster = [(entry_a, fm_a, body_a)]
        assigned.add(i)
        desc_a = fm_a.get("description", "")

        for j, (entry_b, fm_b, body_b) in enumerate(entries):
            if j in assigned:
                continue
            desc_b = fm_b.get("description", "")
            if _similarity(desc_a, desc_b) >= threshold:
                cluster.append((entry_b, fm_b, body_b))
                assigned.add(j)

        if len(cluster) >= 2:
            clusters.append(cluster)

    return clusters


def _extract_variable_parts(
    cluster: list[tuple[CatalogEntry, dict[str, Any], str]],
) -> dict[str, set[str]]:
    """Find frontmatter fields that vary across a cluster.

    Args:
        cluster: List of similar assets.

    Returns:
        Dict of field_name -> set of distinct values.
    """
    field_values: dict[str, set[str]] = defaultdict(set)

    for _, fm, _ in cluster:
        for key, value in fm.items():
            field_values[key].add(str(value))

    # Only return fields that actually vary
    return {k: v for k, v in field_values.items() if len(v) > 1}


def _parameterize_body(bodies: list[str]) -> tuple[str, dict[str, str]]:
    """Find common structure in bodies and identify variable sections.

    Args:
        bodies: List of body texts from similar assets.

    Returns:
        Tuple of (template_body, detected_parameters).
    """
    if not bodies:
        return "", {}
    if len(bodies) == 1:
        return bodies[0], {}

    # Use the first body as the template base
    base = bodies[0]
    params: dict[str, str] = {}

    # Find lines that differ between bodies and mark them as parameters
    base_lines = base.splitlines()
    other_lines_set = [b.splitlines() for b in bodies[1:]]

    template_lines: list[str] = []
    param_counter = 0

    for i, line in enumerate(base_lines):
        differs = False
        for other_lines in other_lines_set:
            if i < len(other_lines) and other_lines[i] != line:
                differs = True
                break
        if differs and line.strip():
            param_counter += 1
            param_name = f"param_{param_counter}"
            template_lines.append(f"{{{{{param_name}}}}}")
            params[param_name] = line.strip()
        else:
            template_lines.append(line)

    return "\n".join(template_lines), params


def extract_patterns_from_catalog(
    catalog: Catalog,
    threshold: float = 0.5,
) -> list[PatternTemplate]:
    """Extract reusable patterns from the asset catalog.

    Groups similar assets by description, identifies variable parts,
    and generates parameterized templates.

    Args:
        catalog: The asset catalog to analyze.
        threshold: Similarity threshold for clustering.

    Returns:
        List of discovered PatternTemplate objects.
    """
    patterns: list[PatternTemplate] = []

    # Collect assets by type
    by_type: dict[AssetType, list[tuple[CatalogEntry, dict[str, Any], str]]] = (
        defaultdict(list)
    )

    for entry in catalog.all_entries():
        if entry.asset_type not in (AssetType.AGENT, AssetType.SKILL):
            continue
        if not entry.file_path.exists():
            continue
        try:
            content = entry.file_path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm, body = _split_frontmatter(content)
        by_type[entry.asset_type].append((entry, fm, body))

    # Cluster and extract patterns for each type
    for asset_type, entries in by_type.items():
        clusters = _cluster_by_description(entries, threshold)

        for cluster in clusters:
            first_entry, first_fm, _ = cluster[0]
            variable_fields = _extract_variable_parts(cluster)
            bodies = [body for _, _, body in cluster]
            template_body, body_params = _parameterize_body(bodies)

            # Build parameters from variable fields
            parameters: dict[str, PatternParameter] = {}
            for field_name, values in variable_fields.items():
                parameters[field_name] = PatternParameter(
                    type="string",
                    example=sorted(values)[0],
                )
            for param_name, example in body_params.items():
                parameters[param_name] = PatternParameter(
                    type="string",
                    example=example,
                )

            # Build pattern name from cluster
            base_name = first_fm.get("name", first_entry.name)
            pattern_name = f"{asset_type.value}-{base_name}"

            pattern = PatternTemplate(
                name=pattern_name,
                description=first_fm.get("description", ""),
                pattern_type=f"{asset_type.value}-archetype",
                parameters=parameters,
                assets=[
                    {
                        "type": asset_type.value,
                        "name": base_name,
                        "template": template_body,
                    }
                ],
                instances=[
                    {
                        "repo": e.repo_path.name,
                        "source": str(e.file_path),
                    }
                    for e, _, _ in cluster
                ],
            )
            patterns.append(pattern)

    return patterns


def extract_pipeline_patterns(
    catalog: Catalog,
) -> list[PatternTemplate]:
    """Extract pipeline patterns from skill sequences in repos.

    Finds repos with multiple skills that follow a common workflow
    sequence (scaffold, implement, test, review, ship).

    Args:
        catalog: The asset catalog to analyze.

    Returns:
        List of pipeline PatternTemplate objects.
    """
    pipeline_keywords = [
        "scaffold",
        "implement",
        "test",
        "review",
        "ship",
        "deploy",
        "release",
        "lint",
        "format",
        "build",
    ]

    # Group skills by repo
    skills_by_repo: dict[str, list[CatalogEntry]] = defaultdict(list)
    for entry in catalog.all_entries():
        if entry.asset_type == AssetType.SKILL:
            skills_by_repo[str(entry.repo_path)].append(entry)

    patterns: list[PatternTemplate] = []

    for repo_path, skills in skills_by_repo.items():
        if len(skills) < 2:
            continue

        # Check if skills match pipeline keywords
        pipeline_skills: list[tuple[str, CatalogEntry]] = []
        for skill in skills:
            for keyword in pipeline_keywords:
                if keyword in skill.name.lower():
                    pipeline_skills.append((keyword, skill))
                    break

        if len(pipeline_skills) < 2:
            continue

        repo_name = Path(repo_path).name
        stages: list[PatternStage] = []
        for keyword, skill in pipeline_skills:
            body = ""
            if skill.file_path.exists():
                try:
                    content = skill.file_path.read_text(encoding="utf-8")
                    _, body = _split_frontmatter(content)
                except OSError:
                    pass
            stages.append(
                PatternStage(
                    skill=keyword,
                    asset_type="skill",
                    name=skill.name,
                    template=body,
                )
            )

        pattern = PatternTemplate(
            name=f"pipeline-{repo_name}",
            description=f"Skill pipeline from {repo_name}",
            pattern_type="feature-pipeline",
            stages=stages,
            instances=[{"repo": repo_name}],
        )
        patterns.append(pattern)

    return patterns


def extract_hook_patterns(
    catalog: Catalog,
) -> list[PatternTemplate]:
    """Extract hook configuration patterns from settings.

    Groups similar hook configurations across repos.

    Args:
        catalog: The asset catalog to analyze.

    Returns:
        List of hook PatternTemplate objects.
    """
    import json

    hook_configs: list[tuple[CatalogEntry, dict[str, Any]]] = []

    for entry in catalog.all_entries():
        if entry.asset_type != AssetType.HOOK:
            continue
        if not entry.file_path.exists():
            continue
        try:
            content = entry.file_path.read_text(encoding="utf-8")
            data = json.loads(content)
            hooks = data.get("hooks", {})
            if hooks:
                hook_configs.append((entry, hooks))
        except (OSError, json.JSONDecodeError):
            continue

    if not hook_configs:
        return []

    # Group by event types
    patterns: list[PatternTemplate] = []
    events_seen: dict[str, list[tuple[CatalogEntry, dict[str, Any]]]] = defaultdict(
        list
    )

    for entry, hooks in hook_configs:
        event_key = "|".join(sorted(hooks.keys()))
        events_seen[event_key].append((entry, hooks))

    for event_key, configs in events_seen.items():
        if len(configs) < 2:
            continue

        events = event_key.split("|")
        pattern = PatternTemplate(
            name=f"hook-{'-'.join(events[:3])}",
            description=f"Hook pattern for {', '.join(events)}",
            pattern_type="hook-pattern",
            instances=[{"repo": e.repo_path.name} for e, _ in configs],
        )
        patterns.append(pattern)

    return patterns


def extract_all_patterns(
    catalog: Catalog,
    threshold: float = 0.5,
    output_dir: Path | None = None,
) -> list[PatternTemplate]:
    """Run all pattern extraction methods and save results.

    Args:
        catalog: The asset catalog to analyze.
        threshold: Similarity threshold for clustering.
        output_dir: Override output directory.

    Returns:
        All extracted patterns.
    """
    all_patterns: list[PatternTemplate] = []

    all_patterns.extend(extract_patterns_from_catalog(catalog, threshold))
    all_patterns.extend(extract_pipeline_patterns(catalog))
    all_patterns.extend(extract_hook_patterns(catalog))

    for pattern in all_patterns:
        pattern.save(output_dir)

    return all_patterns


# --- Built-in Archetypes ---

MINIMAL_AGENT_TEMPLATE = """---
name: {name}
description: {description}
tools:
  - Read
  - Glob
  - Grep
---
# {title}

{body}
"""

MINIMAL_SKILL_TEMPLATE = """---
name: {name}
description: {description}
allowed-tools: [{tools}]
---
# {title}

{body}
"""

MINIMAL_HOOK_TEMPLATE = """{{"hooks": {{{event}: [{{"matcher": "{matcher}", \
"hooks": [{{"type": "command", "command": "{command}"}}]}}]}}}}"""

MINIMAL_COMMAND_TEMPLATE = """# {title}

{body}
"""

MINIMAL_RULE_TEMPLATE = """---
description: {description}
applyTo: '{apply_to}'
---
# {title}

{body}
"""


def get_archetype_template(asset_type: str) -> str:
    """Return the minimal archetype template for an asset type.

    Args:
        asset_type: One of "agent", "skill", "hook", "command", "rule".

    Returns:
        Template string with placeholder variables.
    """
    templates = {
        "agent": MINIMAL_AGENT_TEMPLATE,
        "skill": MINIMAL_SKILL_TEMPLATE,
        "hook": MINIMAL_HOOK_TEMPLATE,
        "command": MINIMAL_COMMAND_TEMPLATE,
        "rule": MINIMAL_RULE_TEMPLATE,
    }
    return templates.get(asset_type, "")
