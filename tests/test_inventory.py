from pathlib import Path

from reagent.config import CatalogConfig, ReagentConfig, ScanConfig
from reagent.core.catalog import Catalog
from reagent.core.inventory import scan_all, scan_claude_dir, scan_repo
from reagent.core.parsers import AssetScope, AssetType


class TestScanRepo:
    def test_scan_sample_project(self, sample_claude_dir: Path) -> None:
        entries = scan_repo(sample_claude_dir)
        asset_types = {e.asset_type for e in entries}

        assert AssetType.AGENT in asset_types
        assert AssetType.SKILL in asset_types
        assert AssetType.COMMAND in asset_types
        assert AssetType.HOOK in asset_types
        assert AssetType.SETTINGS in asset_types
        assert AssetType.RULE in asset_types
        assert AssetType.CLAUDE_MD in asset_types

    def test_scan_finds_agents(self, sample_claude_dir: Path) -> None:
        entries = scan_repo(sample_claude_dir)
        agents = [e for e in entries if e.asset_type == AssetType.AGENT]

        assert len(agents) == 1
        assert agents[0].name == "review"

    def test_scan_finds_skills(self, sample_claude_dir: Path) -> None:
        entries = scan_repo(sample_claude_dir)
        skills = [e for e in entries if e.asset_type == AssetType.SKILL]

        assert len(skills) == 1
        assert skills[0].name == "deploy"

    def test_scan_finds_commands(self, sample_claude_dir: Path) -> None:
        entries = scan_repo(sample_claude_dir)
        commands = [e for e in entries if e.asset_type == AssetType.COMMAND]

        assert len(commands) == 1
        assert commands[0].name == "test"

    def test_scan_finds_settings(self, sample_claude_dir: Path) -> None:
        entries = scan_repo(sample_claude_dir)
        settings = [e for e in entries if e.asset_type == AssetType.SETTINGS]

        # settings.json + settings.local.json
        assert len(settings) == 2

    def test_scan_finds_rules(self, sample_claude_dir: Path) -> None:
        entries = scan_repo(sample_claude_dir)
        rules = [e for e in entries if e.asset_type == AssetType.RULE]

        assert len(rules) == 1
        assert rules[0].name == "style"

    def test_scan_finds_claude_md(self, sample_claude_dir: Path) -> None:
        entries = scan_repo(sample_claude_dir)
        claude_mds = [e for e in entries if e.asset_type == AssetType.CLAUDE_MD]

        assert len(claude_mds) == 1
        assert claude_mds[0].name == "CLAUDE.md"

    def test_scan_nonexistent_dir(self, tmp_path: Path) -> None:
        entries = scan_repo(tmp_path / "nonexistent")
        assert entries == []

    def test_scan_empty_claude_dir(self, tmp_path: Path) -> None:
        project = tmp_path / "project"
        (project / ".claude").mkdir(parents=True)
        entries = scan_repo(project)

        assert entries == []

    def test_asset_ids_format(self, sample_claude_dir: Path) -> None:
        entries = scan_repo(sample_claude_dir)
        for entry in entries:
            parts = entry.asset_id.split(":")
            assert len(parts) == 3
            assert parts[0] == "project"  # repo name
            assert parts[1] in [t.value for t in AssetType]


class TestScanClaudeDir:
    def test_scan_from_fixture(self, fixtures_dir: Path) -> None:
        entries = scan_claude_dir(
            fixtures_dir / ".claude", fixtures_dir, AssetScope.PROJECT
        )
        types_found = {e.asset_type for e in entries}

        assert AssetType.AGENT in types_found
        assert AssetType.SKILL in types_found
        assert AssetType.COMMAND in types_found

    def test_scan_nonexistent_dir(self, tmp_path: Path) -> None:
        entries = scan_claude_dir(tmp_path / ".claude", tmp_path, AssetScope.PROJECT)
        assert entries == []

    def test_agent_memory_detection(self, tmp_path: Path) -> None:
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        memory_dir = claude_dir / "agent-memory"
        memory_dir.mkdir()
        (memory_dir / "notes.md").write_text("Some memory notes")

        entries = scan_claude_dir(claude_dir, tmp_path, AssetScope.PROJECT)
        memory_entries = [e for e in entries if e.asset_type == AssetType.AGENT_MEMORY]

        assert len(memory_entries) == 1


class TestScanAll:
    def test_scan_all_finds_repos(self, tmp_path: Path) -> None:
        # Create two repos under a root
        for name in ("repo1", "repo2"):
            repo = tmp_path / "root" / name
            claude = repo / ".claude"
            claude.mkdir(parents=True)
            agents = claude / "agents"
            agents.mkdir()
            (agents / "test.md").write_text(
                f"---\nname: test\ndescription: test in {name}\n---\nBody.\n"
            )

        config = ReagentConfig(
            scan=ScanConfig(roots=[tmp_path / "root"], exclude_patterns=[]),
            catalog=CatalogConfig(path=tmp_path / "catalog.jsonl"),
        )

        entries = scan_all(config)
        repos = {e.repo_path.name for e in entries}

        assert "repo1" in repos
        assert "repo2" in repos

    def test_scan_all_excludes_patterns(self, tmp_path: Path) -> None:
        # Create repo in excluded dir
        repo = tmp_path / "root" / "node_modules" / "pkg"
        claude = repo / ".claude"
        claude.mkdir(parents=True)
        agents = claude / "agents"
        agents.mkdir()
        (agents / "test.md").write_text("---\nname: test\n---\nBody.\n")

        config = ReagentConfig(
            scan=ScanConfig(
                roots=[tmp_path / "root"],
                exclude_patterns=["node_modules"],
            ),
            catalog=CatalogConfig(path=tmp_path / "catalog.jsonl"),
        )

        entries = scan_all(config)
        assert len(entries) == 0

    def test_scan_all_deduplicates(self, tmp_path: Path) -> None:
        # Same repo reachable from two roots
        repo = tmp_path / "shared" / "myrepo"
        claude = repo / ".claude"
        claude.mkdir(parents=True)
        agents = claude / "agents"
        agents.mkdir()
        (agents / "test.md").write_text("---\nname: test\n---\nBody.\n")

        config = ReagentConfig(
            scan=ScanConfig(
                roots=[tmp_path / "shared", tmp_path / "shared"],
                exclude_patterns=[],
            ),
            catalog=CatalogConfig(path=tmp_path / "catalog.jsonl"),
        )

        entries = scan_all(config)
        agent_entries = [e for e in entries if e.asset_type == AssetType.AGENT]
        assert len(agent_entries) == 1

    def test_scan_nonexistent_root(self, tmp_path: Path) -> None:
        config = ReagentConfig(
            scan=ScanConfig(roots=[tmp_path / "nonexistent"], exclude_patterns=[]),
            catalog=CatalogConfig(path=tmp_path / "catalog.jsonl"),
        )

        entries = scan_all(config)
        assert entries == []


class TestInventoryIntegration:
    def test_full_scan_and_catalog_update(self, tmp_path: Path) -> None:
        # Create a repo
        repo = tmp_path / "root" / "myrepo"
        claude = repo / ".claude"
        claude.mkdir(parents=True)
        agents = claude / "agents"
        agents.mkdir()
        (agents / "review.md").write_text(
            "---\nname: review\ndescription: Review code\n---\nReview.\n"
        )

        catalog_path = tmp_path / "catalog.jsonl"
        config = ReagentConfig(
            scan=ScanConfig(roots=[tmp_path / "root"], exclude_patterns=[]),
            catalog=CatalogConfig(path=catalog_path),
        )

        # First scan
        from reagent.core.inventory import run_inventory

        catalog = Catalog(catalog_path)
        catalog.load()
        added, modified, removed = run_inventory(config, catalog)

        assert added >= 1
        assert modified == 0
        assert removed == 0

        # Second scan (no changes)
        catalog2 = Catalog(catalog_path)
        catalog2.load()
        added2, modified2, removed2 = run_inventory(config, catalog2)

        assert added2 == 0
        assert modified2 == 0
        assert removed2 == 0

    def test_detect_modification(self, tmp_path: Path) -> None:
        repo = tmp_path / "root" / "myrepo"
        claude = repo / ".claude"
        claude.mkdir(parents=True)
        agents = claude / "agents"
        agents.mkdir()
        agent_file = agents / "review.md"
        agent_file.write_text("---\nname: review\n---\nOriginal.\n")

        catalog_path = tmp_path / "catalog.jsonl"
        config = ReagentConfig(
            scan=ScanConfig(roots=[tmp_path / "root"], exclude_patterns=[]),
            catalog=CatalogConfig(path=catalog_path),
        )

        from reagent.core.inventory import run_inventory

        catalog = Catalog(catalog_path)
        catalog.load()
        run_inventory(config, catalog)

        # Modify the agent file
        agent_file.write_text("---\nname: review\n---\nUpdated body.\n")

        catalog2 = Catalog(catalog_path)
        catalog2.load()
        _, modified, _ = run_inventory(config, catalog2)

        assert modified >= 1
