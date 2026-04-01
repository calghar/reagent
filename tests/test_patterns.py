from pathlib import Path

import pytest

from reagent.core.catalog import Catalog, CatalogEntry
from reagent.core.parsers import AssetScope, AssetType
from reagent.intelligence.patterns import (
    PatternStage,
    PatternTemplate,
    extract_all_patterns,
    extract_patterns_from_catalog,
    extract_pipeline_patterns,
    get_archetype_template,
    list_patterns,
)


@pytest.fixture()
def pattern_dir(tmp_path: Path) -> Path:
    """Create a temporary patterns directory."""
    d = tmp_path / "patterns"
    d.mkdir()
    return d


@pytest.fixture()
def sample_catalog(tmp_path: Path) -> Catalog:
    """Create a catalog with sample assets for pattern extraction."""
    catalog_path = tmp_path / "catalog.jsonl"
    catalog = Catalog(catalog_path)

    # Create sample agent files
    agents_dir = tmp_path / "repo-a" / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "review.md").write_text(
        "---\nname: review\ndescription: Code review agent\n"
        "tools:\n  - Read\n  - Glob\n---\nReview code for quality.\n"
    )
    agents_dir_b = tmp_path / "repo-b" / ".claude" / "agents"
    agents_dir_b.mkdir(parents=True)
    (agents_dir_b / "review.md").write_text(
        "---\nname: review\ndescription: Code review agent\n"
        "tools:\n  - Read\n  - Grep\n---\nReview code for correctness.\n"
    )

    # Create sample skill files
    skill_dir_a = tmp_path / "repo-a" / ".claude" / "skills" / "test"
    skill_dir_a.mkdir(parents=True)
    (skill_dir_a / "SKILL.md").write_text(
        "---\nname: test\ndescription: Run tests\n---\nRun pytest.\n"
    )
    skill_dir_b = tmp_path / "repo-a" / ".claude" / "skills" / "review"
    skill_dir_b.mkdir(parents=True)
    (skill_dir_b / "SKILL.md").write_text(
        "---\nname: review\ndescription: Review code\n---\nReview.\n"
    )

    from datetime import UTC, datetime

    now = datetime.now(UTC)

    # Add entries
    for name, file_path, repo_name, asset_type in [
        ("review", agents_dir / "review.md", "repo-a", AssetType.AGENT),
        ("review", agents_dir_b / "review.md", "repo-b", AssetType.AGENT),
        ("test", skill_dir_a / "SKILL.md", "repo-a", AssetType.SKILL),
        ("review", skill_dir_b / "SKILL.md", "repo-a", AssetType.SKILL),
    ]:
        repo_path = tmp_path / repo_name
        entry = CatalogEntry(
            asset_id=f"{repo_name}:{asset_type.value}:{name}",
            asset_type=asset_type,
            name=name,
            scope=AssetScope.PROJECT,
            repo_path=repo_path,
            file_path=file_path,
            content_hash="abc123",
            first_seen=now,
            last_seen=now,
            last_modified=now,
        )
        catalog.add(entry)

    return catalog


class TestPatternTemplate:
    def test_save_and_load(self, pattern_dir: Path) -> None:
        pattern = PatternTemplate(
            name="test-pattern",
            description="A test pattern",
            pattern_type="agent-archetype",
            parameters={},
        )
        path = pattern.save(pattern_dir)
        assert path.exists()

        loaded = PatternTemplate.load_pattern(
            "test-pattern",
            pattern_dir,
        )
        assert loaded is not None
        assert loaded.name == "test-pattern"
        assert loaded.description == "A test pattern"

    def test_load_nonexistent(self, pattern_dir: Path) -> None:
        loaded = PatternTemplate.load_pattern(
            "nonexistent",
            pattern_dir,
        )
        assert loaded is None

    def test_render(self) -> None:
        pattern = PatternTemplate(
            name="test",
            stages=[
                PatternStage(skill="build", template="Build {{language}} project"),
                PatternStage(skill="test", template="Run {{test_command}}"),
            ],
        )
        rendered = pattern.render(
            {
                "language": "python",
                "test_command": "pytest",
            }
        )
        assert len(rendered) == 2
        assert "python" in rendered[0]["content"]
        assert "pytest" in rendered[1]["content"]

    def test_list_patterns(self, pattern_dir: Path) -> None:
        PatternTemplate(
            name="p1",
            description="First",
        ).save(pattern_dir)
        PatternTemplate(
            name="p2",
            description="Second",
        ).save(pattern_dir)

        patterns = list_patterns(pattern_dir)
        assert len(patterns) == 2
        names = [p.name for p in patterns]
        assert "p1" in names
        assert "p2" in names


class TestPatternExtraction:
    def test_extract_from_catalog(self, sample_catalog: Catalog) -> None:
        patterns = extract_patterns_from_catalog(sample_catalog, threshold=0.5)
        # Should find at least the review agent archetype (2 similar agents)
        assert len(patterns) >= 1
        agent_patterns = [p for p in patterns if "agent" in p.pattern_type]
        assert len(agent_patterns) >= 1

    def test_extract_pipeline(self, sample_catalog: Catalog) -> None:
        # repo-a has test + review skills, might detect pipeline
        patterns = extract_pipeline_patterns(sample_catalog)
        # This may or may not find patterns depending on keyword matching
        assert isinstance(patterns, list)

    def test_extract_all(
        self,
        sample_catalog: Catalog,
        pattern_dir: Path,
    ) -> None:
        patterns = extract_all_patterns(
            sample_catalog,
            output_dir=pattern_dir,
        )
        assert isinstance(patterns, list)
        # Check patterns were saved
        yaml_files = list(pattern_dir.glob("*.yaml"))
        assert len(yaml_files) == len(patterns)


class TestArchetypes:
    def test_agent_archetype(self) -> None:
        template = get_archetype_template("agent")
        assert "name:" in template or "{name}" in template

    def test_skill_archetype(self) -> None:
        template = get_archetype_template("skill")
        assert "{name}" in template or "name:" in template

    def test_unknown_type(self) -> None:
        template = get_archetype_template("unknown")
        assert template == ""
