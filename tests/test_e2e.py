from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from reagent.cli import cli
from reagent.config import CatalogConfig, ReagentConfig, ScanConfig
from reagent.core.catalog import Catalog
from reagent.core.parsers import AssetType


def _make_sample_project(tmp_path: Path) -> Path:
    """Create a minimal project with Claude assets for testing."""
    project = tmp_path / "test_project"
    project.mkdir()
    claude_dir = project / ".claude"
    claude_dir.mkdir()

    (claude_dir / "settings.json").write_text('{"permissions": {"allow": ["Read"]}}')

    agents_dir = claude_dir / "agents"
    agents_dir.mkdir()
    (agents_dir / "review.md").write_text(
        "---\n"
        "name: review\n"
        "description: Code review agent\n"
        "model: sonnet\n"
        "---\n"
        "Review code for correctness.\n"
    )

    skill_dir = claude_dir / "skills" / "deploy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: deploy\ndescription: Deploy to production\n---\n"
        "Run deployment pipeline.\n"
    )

    (project / "CLAUDE.md").write_text("# Test Project\n\nA test project.\n")

    return project


def _make_config(tmp_path: Path, project_path: Path) -> ReagentConfig:
    """Create a Reagent config pointing to temp directories."""
    reagent_home = tmp_path / ".reagent"
    reagent_home.mkdir()
    catalog_path = reagent_home / "catalog.jsonl"
    catalog_path.write_text("")

    return ReagentConfig(
        scan=ScanConfig(roots=[project_path.parent]),
        catalog=CatalogConfig(path=catalog_path),
    )


class TestE2EPipeline:
    def test_inventory_to_evaluate(self, tmp_path: Path) -> None:
        project = _make_sample_project(tmp_path)
        config = _make_config(tmp_path, project)

        # Step 1: Inventory
        from reagent.core.inventory import scan_repo

        entries = scan_repo(project)
        assert len(entries) > 0

        catalog = Catalog(config.catalog.path)
        catalog.load()
        added, modified, removed_ids = catalog.diff(entries)
        catalog.apply_diff(added, modified, removed_ids)
        catalog.save()

        assert catalog.count > 0

        # Step 2: Evaluate (without sessions, should still produce scores)
        from reagent.evaluation.evaluator import evaluate_repo

        with patch("reagent.evaluation.evaluator.persist_report"):
            report = evaluate_repo(project, config, catalog)
        assert report.evaluated > 0
        for m in report.asset_metrics:
            assert 0 <= m.quality_score <= 100

    def test_scan_security(self, tmp_path: Path) -> None:
        project = _make_sample_project(tmp_path)
        from reagent.security.scanner import scan_directory

        report = scan_directory(project / ".claude")
        assert report.files_scanned > 0

    def test_variant_workflow(self, tmp_path: Path) -> None:
        project = _make_sample_project(tmp_path)
        config = _make_config(tmp_path, project)

        # Set up catalog
        from reagent.core.inventory import scan_repo

        entries = scan_repo(project)
        catalog = Catalog(config.catalog.path)
        catalog.load()
        added, modified, removed_ids = catalog.diff(entries)
        catalog.apply_diff(added, modified, removed_ids)
        catalog.save()

        # Create a variant
        from reagent.evaluation.evaluator import ABTestStore, create_variant

        ab_path = config.catalog.path.parent / "ab-tests.jsonl"
        ab_store = ABTestStore(ab_path)

        agent_entries = catalog.query(asset_type=AssetType.AGENT)
        assert len(agent_entries) > 0
        entry = agent_entries[0]

        test = create_variant(
            entry.asset_id, "v2", "testing variant", catalog, ab_store
        )
        ab_store.save()

        # Verify variant routing
        results = {ab_store.route_session(test.test_id, f"s{i}") for i in range(20)}
        assert len(results) == 2

    def test_cli_evaluate_command(self, tmp_path: Path) -> None:
        project = _make_sample_project(tmp_path)
        config = _make_config(tmp_path, project)

        # Populate catalog first
        from reagent.core.inventory import scan_repo

        entries = scan_repo(project)
        catalog = Catalog(config.catalog.path)
        catalog.load()
        added, modified, removed_ids = catalog.diff(entries)
        catalog.apply_diff(added, modified, removed_ids)
        catalog.save()

        runner = CliRunner()
        with patch("reagent.cli._load_config", return_value=config):
            result = runner.invoke(cli, ["evaluate", "--repo", str(project)])
        assert result.exit_code == 0 or "No assets" in (result.output or "")
