from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from agentguard.cli import cli


class TestCLI:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "AgentGuard" in result.output

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

    def test_inventory_single_repo(
        self, sample_claude_dir: Path, tmp_path: Path
    ) -> None:
        runner = CliRunner()
        catalog_path = tmp_path / "catalog.jsonl"

        with patch("agentguard.cli.commands.assets._load_config") as mock_config:
            from agentguard.config import AgentGuardConfig, CatalogConfig

            mock_config.return_value = AgentGuardConfig(
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

        with patch("agentguard.cli.commands.assets._load_config") as mock_config:
            from agentguard.config import AgentGuardConfig, CatalogConfig

            mock_config.return_value = AgentGuardConfig(
                catalog=CatalogConfig(path=catalog_path)
            )
            result = runner.invoke(cli, ["catalog"])

        assert result.exit_code == 0
        assert "No assets" in result.output

    def test_show_not_found(self, tmp_path: Path) -> None:
        runner = CliRunner()
        catalog_path = tmp_path / "catalog.jsonl"
        catalog_path.write_text("")

        with patch("agentguard.cli.commands.assets._load_config") as mock_config:
            from agentguard.config import AgentGuardConfig, CatalogConfig

            mock_config.return_value = AgentGuardConfig(
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

        with patch("agentguard.cli.commands.assets._load_config") as mock_config:
            from agentguard.config import AgentGuardConfig, CatalogConfig

            mock_config.return_value = AgentGuardConfig(
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

        with patch("agentguard.cli.commands.assets._load_config") as mock_config:
            from agentguard.config import AgentGuardConfig, CatalogConfig

            mock_config.return_value = AgentGuardConfig(
                catalog=CatalogConfig(path=catalog_path)
            )

            # Scan
            runner.invoke(cli, ["inventory", "--repo", str(sample_claude_dir)])

            # Show a specific asset
            result = runner.invoke(cli, ["show", "project:agent:review"])
            assert result.exit_code == 0
            assert "review" in result.output
