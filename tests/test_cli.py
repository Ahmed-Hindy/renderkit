"""Tests for the RenderKit command line interface."""

from click.testing import CliRunner

from renderkit.cli import main as cli_main


def test_help_lists_ui_command(monkeypatch) -> None:
    """Verify the public launcher appears in CLI help."""
    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)

    result = CliRunner().invoke(cli_main.main, ["--help"])

    assert result.exit_code == 0
    assert "ui" in result.output
    assert "Launch the RenderKit desktop UI." in result.output
    assert "gui" not in result.output


def test_ui_command_launches_gui(monkeypatch) -> None:
    """Verify the ui command dispatches to the Qt launcher."""
    launched = False

    def fake_launch_ui() -> None:
        nonlocal launched
        launched = True

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "_launch_ui", fake_launch_ui)

    result = CliRunner().invoke(cli_main.main, ["ui"])

    assert result.exit_code == 0
    assert launched


def test_gui_alias_launches_gui(monkeypatch) -> None:
    """Verify the gui alias dispatches to the Qt launcher."""
    launched = False

    def fake_launch_ui() -> None:
        nonlocal launched
        launched = True

    monkeypatch.setattr(cli_main, "ensure_ffmpeg_env", lambda: None)
    monkeypatch.setattr(cli_main, "setup_logging", lambda: None)
    monkeypatch.setattr(cli_main, "_launch_ui", fake_launch_ui)

    result = CliRunner().invoke(cli_main.main, ["gui"])

    assert result.exit_code == 0
    assert launched
