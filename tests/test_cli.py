"""Tests for CLI commands."""

from __future__ import annotations

from typer.testing import CliRunner

from forge_armory.cli import app

runner = CliRunner()


class TestVersionOption:
    """Tests for the version option."""

    def test_version_shows_version(self) -> None:
        """--version option should display version."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "forge-armory v" in result.output

    def test_short_version_shows_version(self) -> None:
        """-V option should display version."""
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert "forge-armory v" in result.output


class TestInfoCommand:
    """Tests for the info command."""

    def test_info_shows_info(self) -> None:
        """Info command should display gateway info."""
        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        assert "Forge Armory" in result.output
        assert "MCP protocol gateway" in result.output
