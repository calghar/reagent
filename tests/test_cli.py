from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from reagent.cli import cli


class TestCLI:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "Reagent" in result.output

    def test_inventory_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["inventory", "--help"])

        assert result.exit_code == 0
        assert "--repo" in result.output

    def test_catalog_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["catalog", "--help"])

        assert result.exit_code == 0
        assert "--type" in result.output

    def test_show_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["show", "--help"])

        assert result.exit_code == 0
        assert "ASSET_ID" in result.output

    def test_schema_show_preserves_regex(self) -> None:
        """schema show must not strip bracket chars like [a-z] via Rich markup."""
        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "show", "agent"])
        assert result.exit_code == 0
        # The agent schema has a name pattern with character classes
        assert "[a-z]" in result.output

    def test_inventory_single_repo(
        self, sample_claude_dir: Path, tmp_path: Path
    ) -> None:
        runner = CliRunner()
        catalog_path = tmp_path / "catalog.jsonl"

        with patch("reagent.cli.commands.assets._load_config") as mock_config:
            from reagent.config import CatalogConfig, ReagentConfig

            mock_config.return_value = ReagentConfig(
                catalog=CatalogConfig(path=catalog_path)
            )
            result = runner.invoke(cli, ["inventory", "--repo", str(sample_claude_dir)])

        assert result.exit_code == 0
        assert "assets" in result.output
        assert "new" in result.output

    def test_catalog_empty(self, tmp_path: Path) -> None:
        runner = CliRunner()
        catalog_path = tmp_path / "catalog.jsonl"
        catalog_path.write_text("")

        with patch("reagent.cli.commands.assets._load_config") as mock_config:
            from reagent.config import CatalogConfig, ReagentConfig

            mock_config.return_value = ReagentConfig(
                catalog=CatalogConfig(path=catalog_path)
            )
            result = runner.invoke(cli, ["catalog"])

        assert result.exit_code == 0
        assert "No assets" in result.output

    def test_show_not_found(self, tmp_path: Path) -> None:
        runner = CliRunner()
        catalog_path = tmp_path / "catalog.jsonl"
        catalog_path.write_text("")

        with patch("reagent.cli.commands.assets._load_config") as mock_config:
            from reagent.config import CatalogConfig, ReagentConfig

            mock_config.return_value = ReagentConfig(
                catalog=CatalogConfig(path=catalog_path)
            )
            result = runner.invoke(cli, ["show", "nonexistent:agent:nope"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_inventory_then_catalog(
        self, sample_claude_dir: Path, tmp_path: Path
    ) -> None:
        runner = CliRunner()
        catalog_path = tmp_path / "catalog.jsonl"

        with patch("reagent.cli.commands.assets._load_config") as mock_config:
            from reagent.config import CatalogConfig, ReagentConfig

            mock_config.return_value = ReagentConfig(
                catalog=CatalogConfig(path=catalog_path)
            )

            # Scan
            result = runner.invoke(cli, ["inventory", "--repo", str(sample_claude_dir)])
            assert result.exit_code == 0

            # List
            result = runner.invoke(cli, ["catalog"])
            assert result.exit_code == 0
            assert "agent" in result.output.lower() or "skill" in result.output.lower()

    def test_inventory_then_show(self, sample_claude_dir: Path, tmp_path: Path) -> None:
        runner = CliRunner()
        catalog_path = tmp_path / "catalog.jsonl"

        with patch("reagent.cli.commands.assets._load_config") as mock_config:
            from reagent.config import CatalogConfig, ReagentConfig

            mock_config.return_value = ReagentConfig(
                catalog=CatalogConfig(path=catalog_path)
            )

            # Scan
            runner.invoke(cli, ["inventory", "--repo", str(sample_claude_dir)])

            # Show a specific asset
            result = runner.invoke(cli, ["show", "project:agent:review"])
            assert result.exit_code == 0
            assert "review" in result.output
