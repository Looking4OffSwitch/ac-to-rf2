"""Exercise the public launcher routing and Windows batch environment boundary."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ac_to_rf2 import drive_track, load_diagnostics, runner


ROOT = Path(__file__).resolve().parents[1]


def test_convert_reuses_workflow_without_launch(monkeypatch):
    commands = []
    monkeypatch.setattr(runner, "choose_layout", lambda args: args)
    monkeypatch.setattr(runner, "ensure_tools", lambda: 0)
    monkeypatch.setattr(drive_track, "main", lambda args: commands.append(args) or 7)
    assert runner.main(["convert", "track with spaces", "--jobs", "2"]) == 7
    assert commands == [["track with spaces", "--jobs", "2", "--no-launch"]]


@pytest.mark.parametrize("args", [[], ["game"], ["--restart-game"]])
def test_default_and_game_keep_diagnostics(monkeypatch, args):
    commands = []
    monkeypatch.setattr(load_diagnostics, "main", lambda args: commands.append(args) or 0)
    assert runner.main(args) == 0
    assert commands == [["--launch", *(["--restart-game"] if args == ["--restart-game"] else [])]]


def test_drive_monitors_after_conversion(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "choose_layout", lambda args: args)
    monkeypatch.setattr(runner, "ensure_tools", lambda: 0)
    monkeypatch.setattr(load_diagnostics, "launch_and_monitor",
                        lambda args, **kw: calls.append((args, kw)) or 0)
    assert runner.main(["drive", "ks_silverstone::gp"]) == 0
    assert calls == [(["ks_silverstone::gp"], {"launch_only": False})]


@pytest.mark.parametrize("flag", ["--dry-run", "--install-only", "--skip-geometry"])
def test_reuse_or_dry_run_does_not_download(monkeypatch, flag):
    monkeypatch.setattr(runner, "choose_layout", lambda args: args)
    monkeypatch.setattr(runner, "ensure_tools", lambda: pytest.fail("download requested"))
    monkeypatch.setattr(drive_track, "main", lambda args: 0)
    assert runner.main(["convert", "track", flag]) == 0


def test_failed_tool_setup_stops_before_conversion(monkeypatch):
    monkeypatch.setattr(runner, "choose_layout", lambda args: args)
    monkeypatch.setattr(runner, "ensure_tools", lambda: 9)
    monkeypatch.setattr(drive_track, "main", lambda args: pytest.fail("conversion after setup failure"))
    assert runner.main(["convert", "track"]) == 9


def test_conversion_failure_does_not_monitor(monkeypatch):
    monkeypatch.setattr(drive_track, "main", lambda args: 12)
    monkeypatch.setattr(load_diagnostics, "game_processes", lambda root: pytest.fail("monitored failed conversion"))
    assert load_diagnostics.launch_and_monitor(["track"], launch_only=False) == 12


@pytest.mark.parametrize("flag", ["--dry-run", "--no-launch"])
def test_drive_without_launch_does_not_monitor(monkeypatch, flag):
    commands = []
    monkeypatch.setattr(drive_track, "main", lambda args: commands.append(args) or 0)
    monkeypatch.setattr(load_diagnostics, "game_processes", lambda root: pytest.fail("unexpected monitor"))
    assert load_diagnostics.launch_and_monitor(["track", flag], launch_only=False) == 0
    assert commands == [["--trace", "5", "track", flag]]


@pytest.mark.parametrize("command", ["convert", "drive"])
def test_conversion_help_does_not_download(monkeypatch, command, capsys):
    monkeypatch.setattr(runner, "ensure_tools", lambda: pytest.fail("help downloaded tools"))
    assert runner.main([command, "--help"]) == 0
    assert "run.bat " + command in capsys.readouterr().out


@pytest.mark.skipif(os.name != "nt", reason="Windows batch entry point")
def test_batch_uses_checkout_environment_from_other_directory(tmp_path):
    # Run with an intentionally foreign active environment and no activation.
    environment = dict(os.environ, VIRTUAL_ENV=str(tmp_path / "foreign venv"))
    environment.pop("PYTHONPATH", None)
    environment.pop("AC2RF2_WORKSPACE", None)
    result = subprocess.run(["cmd", "/d", "/c", str(ROOT / "run.bat"), "test",
        str(Path(__file__).with_name("test_package_layout.py")), "-q", "-k",
        "root_has_no_application_modules"], cwd=tmp_path, env=environment,
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="Windows batch entry point")
def test_batch_preserves_failure_exit_code(tmp_path):
    result = subprocess.run(["cmd", "/d", "/c", str(ROOT / "run.bat"), "unknown-command"],
        cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "invalid choice" in result.stderr


def test_all_tracks_is_forwarded_without_layout_prompt_or_download_on_dry_run(monkeypatch):
    commands = []
    monkeypatch.setattr(runner, "ensure_tools", lambda: pytest.fail("dry run downloaded tools"))
    monkeypatch.setattr(drive_track, "main", lambda args: commands.append(args) or 0)
    assert runner.main(["convert", "--all-tracks", "--dry-run"]) == 0
    assert commands == [["--all-tracks", "--dry-run", "--no-launch"]]


def test_track_list_does_not_download_or_launch(monkeypatch):
    commands = []
    monkeypatch.setattr(runner, "ensure_tools", lambda: pytest.fail("listing downloaded tools"))
    monkeypatch.setattr(load_diagnostics, "launch_and_monitor", lambda *a, **k: pytest.fail("listing launched game"))
    monkeypatch.setattr(drive_track, "main", lambda args: commands.append(args) or 0)
    assert runner.main(["convert", "--list-tracks"]) == 0
    assert runner.main(["drive", "--list-tracks"]) == 0
    assert commands == [["--list-tracks"], ["--list-tracks"]]


def test_convert_help_explains_how_to_find_and_select_tracks(capsys):
    assert runner.main(["convert", "--help"]) == 0
    output = capsys.readouterr().out
    assert "without launching" in output
    assert "folder name inside Assetto Corsa's content/tracks" in output
    assert "run.bat convert --list-tracks" in output
    assert "run.bat convert ks_laguna_seca" in output
    assert "run.bat convert ks_silverstone::gp" in output
    assert "run.bat convert --all-tracks" in output
