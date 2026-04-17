from datetime import UTC, datetime
from pathlib import Path

from agentguard.core.catalog import (
    Catalog,
    CatalogEntry,
    entry_from_parsed,
    make_asset_id,
)
from agentguard.core.parsers import AssetScope, AssetType, parse_agent


class TestMakeAssetId:
    def test_basic(self) -> None:
        asset_id = make_asset_id(Path("/repos/myproject"), AssetType.AGENT, "review")
        assert asset_id == "myproject:agent:review"

    def test_skill(self) -> None:
        asset_id = make_asset_id(Path("/repos/app"), AssetType.SKILL, "deploy")
        assert asset_id == "app:skill:deploy"


class TestEntryFromParsed:
    def test_creates_entry(self, sample_claude_dir: Path) -> None:
        agent_path = sample_claude_dir / ".claude" / "agents" / "review.md"
        asset = parse_agent(agent_path)
        entry = entry_from_parsed(asset, sample_claude_dir)

        assert entry.asset_id == "project:agent:review"
        assert entry.asset_type == AssetType.AGENT
        assert entry.name == "review"
        assert entry.scope == AssetScope.PROJECT
        assert entry.content_hash == asset.content_hash
        assert "description" in entry.metadata

    def test_global_scope(self, sample_claude_dir: Path) -> None:
        agent_path = sample_claude_dir / ".claude" / "agents" / "review.md"
        asset = parse_agent(agent_path)
        entry = entry_from_parsed(asset, sample_claude_dir, AssetScope.GLOBAL)

        assert entry.scope == AssetScope.GLOBAL


class TestCatalog:
    def test_add_and_get(self, agentguard_home: Path) -> None:
        catalog = Catalog(agentguard_home / "catalog.jsonl")
        entry = CatalogEntry(
            asset_id="myrepo:agent:review",
            asset_type=AssetType.AGENT,
            name="review",
            repo_path=Path("/repos/myrepo"),
            file_path=Path("/repos/myrepo/.claude/agents/review.md"),
            content_hash="abc123",
        )
        catalog.add(entry)

        result = catalog.get("myrepo:agent:review")
        assert result is not None
        assert result.name == "review"

    def test_get_nonexistent(self, agentguard_home: Path) -> None:
        catalog = Catalog(agentguard_home / "catalog.jsonl")
        assert catalog.get("nope:agent:missing") is None

    def test_remove(self, agentguard_home: Path) -> None:
        catalog = Catalog(agentguard_home / "catalog.jsonl")
        entry = CatalogEntry(
            asset_id="repo:agent:test",
            asset_type=AssetType.AGENT,
            name="test",
            repo_path=Path("/repos/repo"),
            file_path=Path("/repos/repo/.claude/agents/test.md"),
            content_hash="hash",
        )
        catalog.add(entry)
        assert catalog.remove("repo:agent:test") is True
        assert catalog.get("repo:agent:test") is None
        assert catalog.remove("repo:agent:test") is False

    def test_query_by_type(self, agentguard_home: Path) -> None:
        catalog = Catalog(agentguard_home / "catalog.jsonl")
        catalog.add(
            CatalogEntry(
                asset_id="r:agent:a1",
                asset_type=AssetType.AGENT,
                name="a1",
                repo_path=Path("/r"),
                file_path=Path("/r/.claude/agents/a1.md"),
                content_hash="h1",
            )
        )
        catalog.add(
            CatalogEntry(
                asset_id="r:skill:s1",
                asset_type=AssetType.SKILL,
                name="s1",
                repo_path=Path("/r"),
                file_path=Path("/r/.claude/skills/s1/SKILL.md"),
                content_hash="h2",
            )
        )

        agents = catalog.query(asset_type=AssetType.AGENT)
        assert len(agents) == 1
        assert agents[0].name == "a1"

    def test_query_by_repo(self, agentguard_home: Path) -> None:
        catalog = Catalog(agentguard_home / "catalog.jsonl")
        catalog.add(
            CatalogEntry(
                asset_id="repo1:agent:a",
                asset_type=AssetType.AGENT,
                name="a",
                repo_path=Path("/repos/repo1"),
                file_path=Path("/repos/repo1/.claude/agents/a.md"),
                content_hash="h1",
            )
        )
        catalog.add(
            CatalogEntry(
                asset_id="repo2:agent:b",
                asset_type=AssetType.AGENT,
                name="b",
                repo_path=Path("/repos/repo2"),
                file_path=Path("/repos/repo2/.claude/agents/b.md"),
                content_hash="h2",
            )
        )

        results = catalog.query(repo_name="repo1")
        assert len(results) == 1
        assert results[0].asset_id == "repo1:agent:a"

    def test_save_and_load(self, agentguard_home: Path) -> None:
        catalog_path = agentguard_home / "catalog.jsonl"

        # Save
        catalog = Catalog(catalog_path)
        catalog.add(
            CatalogEntry(
                asset_id="r:agent:a",
                asset_type=AssetType.AGENT,
                name="a",
                repo_path=Path("/r"),
                file_path=Path("/r/.claude/agents/a.md"),
                content_hash="hash1",
            )
        )
        catalog.save()

        # Load in new instance
        catalog2 = Catalog(catalog_path)
        catalog2.load()
        assert catalog2.count == 1
        entry = catalog2.get("r:agent:a")
        assert entry is not None
        assert entry.content_hash == "hash1"

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        catalog_path = tmp_path / "subdir" / "catalog.jsonl"
        catalog = Catalog(catalog_path)
        catalog.add(
            CatalogEntry(
                asset_id="r:agent:a",
                asset_type=AssetType.AGENT,
                name="a",
                repo_path=Path("/r"),
                file_path=Path("/r/a.md"),
                content_hash="h",
            )
        )
        catalog.save()
        assert catalog_path.exists()

    def test_all_entries(self, agentguard_home: Path) -> None:
        catalog = Catalog(agentguard_home / "catalog.jsonl")
        catalog.add(
            CatalogEntry(
                asset_id="r:skill:b",
                asset_type=AssetType.SKILL,
                name="b",
                repo_path=Path("/r"),
                file_path=Path("/r/b"),
                content_hash="h1",
            )
        )
        catalog.add(
            CatalogEntry(
                asset_id="r:agent:a",
                asset_type=AssetType.AGENT,
                name="a",
                repo_path=Path("/r"),
                file_path=Path("/r/a"),
                content_hash="h2",
            )
        )

        entries = catalog.all_entries()
        assert len(entries) == 2
        # Sorted by asset_id
        assert entries[0].asset_id == "r:agent:a"
        assert entries[1].asset_id == "r:skill:b"

    def test_counts_by_type(self, agentguard_home: Path) -> None:
        catalog = Catalog(agentguard_home / "catalog.jsonl")
        for i in range(3):
            catalog.add(
                CatalogEntry(
                    asset_id=f"r:agent:a{i}",
                    asset_type=AssetType.AGENT,
                    name=f"a{i}",
                    repo_path=Path("/r"),
                    file_path=Path(f"/r/a{i}"),
                    content_hash=f"h{i}",
                )
            )
        catalog.add(
            CatalogEntry(
                asset_id="r:skill:s",
                asset_type=AssetType.SKILL,
                name="s",
                repo_path=Path("/r"),
                file_path=Path("/r/s"),
                content_hash="hs",
            )
        )

        counts = catalog.counts_by_type()
        assert counts[AssetType.AGENT] == 3
        assert counts[AssetType.SKILL] == 1

    def test_add_preserves_first_seen(self, agentguard_home: Path) -> None:
        catalog = Catalog(agentguard_home / "catalog.jsonl")
        early = datetime(2025, 1, 1, tzinfo=UTC)

        catalog.add(
            CatalogEntry(
                asset_id="r:agent:a",
                asset_type=AssetType.AGENT,
                name="a",
                repo_path=Path("/r"),
                file_path=Path("/r/a"),
                content_hash="h1",
                first_seen=early,
            )
        )

        # Update same entry
        catalog.add(
            CatalogEntry(
                asset_id="r:agent:a",
                asset_type=AssetType.AGENT,
                name="a",
                repo_path=Path("/r"),
                file_path=Path("/r/a"),
                content_hash="h2",
            )
        )

        entry = catalog.get("r:agent:a")
        assert entry is not None
        assert entry.first_seen == early


class TestCatalogDiff:
    def test_diff_detects_new(self, agentguard_home: Path) -> None:
        catalog = Catalog(agentguard_home / "catalog.jsonl")
        new_entries = [
            CatalogEntry(
                asset_id="r:agent:new",
                asset_type=AssetType.AGENT,
                name="new",
                repo_path=Path("/r"),
                file_path=Path("/r/new"),
                content_hash="h1",
            )
        ]

        added, modified, removed = catalog.diff(new_entries)
        assert len(added) == 1
        assert len(modified) == 0
        assert len(removed) == 0

    def test_diff_detects_modified(self, agentguard_home: Path) -> None:
        catalog = Catalog(agentguard_home / "catalog.jsonl")
        catalog.add(
            CatalogEntry(
                asset_id="r:agent:a",
                asset_type=AssetType.AGENT,
                name="a",
                repo_path=Path("/r"),
                file_path=Path("/r/a"),
                content_hash="old_hash",
            )
        )

        new_entries = [
            CatalogEntry(
                asset_id="r:agent:a",
                asset_type=AssetType.AGENT,
                name="a",
                repo_path=Path("/r"),
                file_path=Path("/r/a"),
                content_hash="new_hash",
            )
        ]

        added, modified, removed = catalog.diff(new_entries)
        assert len(added) == 0
        assert len(modified) == 1
        assert len(removed) == 0

    def test_diff_detects_removed(self, agentguard_home: Path) -> None:
        catalog = Catalog(agentguard_home / "catalog.jsonl")
        catalog.add(
            CatalogEntry(
                asset_id="r:agent:gone",
                asset_type=AssetType.AGENT,
                name="gone",
                repo_path=Path("/r"),
                file_path=Path("/r/gone"),
                content_hash="h",
            )
        )

        added, modified, removed = catalog.diff([])
        assert len(added) == 0
        assert len(modified) == 0
        assert removed == ["r:agent:gone"]

    def test_apply_diff(self, agentguard_home: Path) -> None:
        catalog = Catalog(agentguard_home / "catalog.jsonl")
        catalog.add(
            CatalogEntry(
                asset_id="r:agent:keep",
                asset_type=AssetType.AGENT,
                name="keep",
                repo_path=Path("/r"),
                file_path=Path("/r/keep"),
                content_hash="h1",
            )
        )
        catalog.add(
            CatalogEntry(
                asset_id="r:agent:remove",
                asset_type=AssetType.AGENT,
                name="remove",
                repo_path=Path("/r"),
                file_path=Path("/r/remove"),
                content_hash="h2",
            )
        )

        new_entry = CatalogEntry(
            asset_id="r:skill:added",
            asset_type=AssetType.SKILL,
            name="added",
            repo_path=Path("/r"),
            file_path=Path("/r/added"),
            content_hash="h3",
        )

        catalog.apply_diff([new_entry], [], ["r:agent:remove"])
        assert catalog.count == 2
        assert catalog.get("r:skill:added") is not None
        assert catalog.get("r:agent:remove") is None

    def test_load_skips_invalid_lines(self, agentguard_home: Path) -> None:
        catalog_path = agentguard_home / "catalog.jsonl"
        catalog_path.write_text("not valid json\n\n{also invalid\n")

        catalog = Catalog(catalog_path)
        catalog.load()
        assert catalog.count == 0
