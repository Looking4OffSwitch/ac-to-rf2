"""Batch ordering, fail-stop behavior, process identity, and real file locking."""
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import drive_track as workflow
import game_runtime as game


@pytest.fixture
def environment(tmp_path, monkeypatch):
    rf2, ac, out = tmp_path / "rFactor 2", tmp_path / "AC", tmp_path / "out"
    (rf2 / "Bin64").mkdir(parents=True)
    (rf2 / "Bin64" / game.MOD_EXE).write_bytes(b"fixture")
    (rf2 / "ModDev/Locations").mkdir(parents=True)
    (ac / "content/tracks").mkdir(parents=True)
    calls = []
    monkeypatch.setattr(workflow, "ensure_stopped", lambda *a, **k: calls.append(("stop", a)))
    monkeypatch.setattr(workflow, "launch_developer", lambda *a: calls.append(("launch", a)) or
                        SimpleNamespace(wait=lambda: calls.append(("wait", ()))))
    monkeypatch.setattr(workflow.subprocess, "run", lambda command, **kw: calls.append(("run", command, kw)))
    options = ["--rf2", str(rf2), "--ac", str(ac), "--out-root", str(out)]
    return rf2, ac, out, calls, options


def source(ac, name, layouts=()):
    folder = ac / "content/tracks" / name
    folder.mkdir()
    (folder / "source.kn5").write_bytes(b"fixture")
    for suffix in layouts or (None,):
        ini = "models_%s.ini" % suffix if suffix else "models.ini"
        (folder / ini).write_text("[MODEL_0]\nFILE=source.kn5")
    return folder


def test_batch_converts_installs_then_launches_once_with_explicit_paths(environment):
    rf2, ac, out, calls, options = environment
    source(ac, "first track & scenery")
    source(ac, "silverstone", ("gp",))
    assert workflow.main(options + ["first track & scenery", "silverstone::gp", "--jobs", "2", "--hour", "18:30"]) == 0
    runs = [c for c in calls if c[0] == "run"]
    assert len(runs) == 2 and calls[-1][0] == "launch"
    assert sum(c[0] == "launch" for c in calls) == 1
    for _, command, kwargs in runs:
        assert isinstance(command, list) and "shell" not in kwargs
        assert command[command.index("--install") + 1] == str(rf2 / "ModDev/Locations")
        assert command[command.index("--out-root") + 1] == str(out)
        assert command[command.index("--hour") + 1] == "18:30"
        assert kwargs["env"]["AC2RF2_RF2_DIR"] == str(rf2)
    assert runs[1][1][runs[1][1].index("--layout") + 1] == "gp"


def test_batch_failure_stops_later_builds_and_does_not_launch(environment, monkeypatch):
    _rf2, ac, _out, calls, options = environment
    source(ac, "a"); source(ac, "b")
    def fail(command, **kwargs):
        calls.append(("failed", command))
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(workflow.subprocess, "run", fail)
    assert workflow.main(options + ["a", "b"]) == 1
    assert sum(c[0] == "failed" for c in calls) == 1
    assert not any(c[0] == "launch" for c in calls)


def test_all_targets_are_preflighted_before_closing_or_building(environment):
    _rf2, ac, _out, calls, options = environment
    source(ac, "valid")
    assert workflow.main(options + ["valid", "missing"]) == 1
    assert calls == []


def test_install_only_does_not_need_source_game_or_blender(environment):
    rf2, _ac, out, calls, options = environment
    build = out / "laguna"
    (build / "gmt").mkdir(parents=True)
    (build / "material_map.json").write_text("{}")
    (build / "gmt/exported.json").write_text("[]")
    assert workflow.main(options + ["laguna", "--install-only", "--no-launch"]) == 0
    runs = [c for c in calls if c[0] == "run"]
    assert len(runs) == 1
    command = runs[0][1]
    assert Path(command[1]).name == "finalize_track.py" and command[2] == str(build)
    assert command[command.index("--install") + 1] == str(rf2 / "ModDev/Locations")
    assert not any(c[0] == "launch" for c in calls)


def test_incomplete_existing_build_fails_before_shutdown_or_install(environment):
    _rf2, _ac, _out, calls, options = environment
    assert workflow.main(options + ["laguna", "--install-only"]) == 1
    assert calls == []


def test_launch_only_restart_and_wait_options(environment):
    _rf2, _ac, _out, calls, options = environment
    assert workflow.main(options + ["--launch-only", "--restart-game", "--force-close", "--wait-for-exit"]) == 0
    assert [c[0] for c in calls] == ["stop", "launch", "wait"]
    assert calls[0][1][1:3] == (True, True)


def test_dry_run_has_no_process_or_file_side_effects(environment):
    rf2, ac, _out, calls, options = environment
    source(ac, "laguna")
    assert workflow.main(options + ["laguna", "--restart-game", "--dry-run"]) == 0
    assert calls == [] and not (rf2 / "ModDev/.ac2rf2-test.lock").exists()


def test_all_layouts_and_duplicate_specs_produce_one_build_each(environment):
    _rf2, ac, _out, calls, options = environment
    source(ac, "silverstone", ("gp", "national"))
    assert workflow.main(options + ["silverstone", "silverstone", "--all-layouts", "--no-launch"]) == 0
    commands = [c[1] for c in calls if c[0] == "run"]
    assert [c[c.index("--layout") + 1] for c in commands] == ["gp", "national"]


def test_distinct_sources_cannot_overwrite_same_venue(environment, tmp_path):
    _rf2, ac, _out, calls, options = environment
    a = source(ac, "same")
    b = tmp_path / "other/same"
    b.mkdir(parents=True)
    assert workflow.main(options + [str(a), str(b)]) == 1
    assert calls == []


@pytest.mark.parametrize("flags", [[], ["--force-close"], ["--launch-only", "track"],
    ["--launch-only", "--no-launch"], ["track", "--jobs", "0"],
    ["track", "--hour", "99:99"], ["track", "--launch-timeout", "nan"],
    ["track", "--close-timeout", "inf"], ["track", "--no-launch", "--wait-for-exit"],
    ["track", "--install-only", "--skip-geometry"]])
def test_invalid_combinations_fail_at_argument_parsing(flags):
    with pytest.raises(SystemExit) as exc:
        workflow.main(flags)
    assert exc.value.code == 2


def test_output_directory_cannot_be_inside_game_installation(environment):
    rf2, ac, _out, calls, options = environment
    source(ac, "laguna")
    assert workflow.main(options + ["laguna", "--out-root", str(rf2 / "ModDev")]) == 1
    assert calls == []


def test_workflow_file_lock_excludes_other_workspace_and_releases(environment):
    rf2, *_ = environment
    with workflow.workflow_lock(rf2):
        with pytest.raises(RuntimeError, match="Another test workflow"):
            with workflow.workflow_lock(rf2):
                pytest.fail("must not acquire the same game lock twice")
    with workflow.workflow_lock(rf2):
        pass


def process(executable, pid=1, args=()):
    path = Path(executable)
    return SimpleNamespace(pid=pid, info=dict(name=path.name, exe=str(path), cmdline=list(args)),
                           is_running=lambda: True)


def test_process_detection_ignores_other_installations_and_checks_actual_mod_binary(tmp_path, monkeypatch):
    root = tmp_path / "game"
    dev = process(root / "Bin64" / game.MOD_EXE)
    normal = process(root / "Bin64/rFactor2.exe", 2)
    other = process(tmp_path / "other/Bin64" / game.MOD_EXE, 3)
    renderer = process(root / "Bin64" / game.MOD_EXE, 4, ["--type=renderer"])
    monkeypatch.setattr(game.psutil, "process_iter", lambda *a, **k: [dev, normal, other, renderer])
    assert game.game_processes(root) == [dev, normal, renderer]
    assert game.is_developer(dev, root) and not game.is_developer(normal, root)
    assert not game.is_developer(renderer, root) and not game.is_developer(other, root)


def test_running_game_requires_explicit_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(game, "game_processes", lambda *a: [process(tmp_path / "rfactor2.exe")])
    monkeypatch.setattr(game, "close_windows", lambda *a: pytest.fail("must not close implicitly"))
    with pytest.raises(RuntimeError, match="--restart-game"):
        game.ensure_stopped(tmp_path)


def test_graceful_shutdown_cannot_fall_through_to_install_when_game_remains(tmp_path, monkeypatch):
    running = process(tmp_path / "rfactor2.exe")
    monkeypatch.setattr(game, "game_processes", lambda *a: [running])
    monkeypatch.setattr(game, "close_windows", lambda *a: None)
    monkeypatch.setattr(game.psutil, "wait_procs", lambda *a, **k: ([], [running]))
    with pytest.raises(RuntimeError, match="did not close"):
        game.ensure_stopped(tmp_path, restart=True, timeout=.01)


def test_force_shutdown_is_explicit_and_scoped_to_detected_processes(tmp_path, monkeypatch):
    events = []
    running = process(tmp_path / "rfactor2.exe")
    running.kill = lambda: events.append("kill")
    monkeypatch.setattr(game, "game_processes", lambda *a: [] if events else [running])
    monkeypatch.setattr(game, "close_windows", lambda *a: None)
    monkeypatch.setattr(game.psutil, "wait_procs", lambda *a, **k: ([], [running]))
    game.ensure_stopped(tmp_path, restart=True, force=True, timeout=.01)
    assert events == ["kill"]


def fake_clock(monkeypatch):
    now = [0.]
    monkeypatch.setattr(game.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(game.time, "sleep", lambda value: now.__setitem__(0, now[0] + value))


def test_launch_uses_root_working_directory_and_confirms_actual_process(tmp_path, monkeypatch):
    executable = tmp_path / "Bin64" / game.MOD_EXE
    executable.parent.mkdir()
    executable.write_bytes(b"fixture")
    dev = process(executable, 12)
    events = []
    monkeypatch.setattr(game, "game_processes", lambda *a: [dev] if events else [])
    monkeypatch.setattr(game.subprocess, "Popen", lambda command, **kwargs:
        events.append((command, kwargs)) or SimpleNamespace(poll=lambda: None))
    fake_clock(monkeypatch)
    assert game.launch_developer(tmp_path, timeout=3, trace=4) is dev
    assert events == [([str(executable), "+trace=4"], {"cwd": tmp_path})]


def test_launch_detects_steam_redirect_to_regular_game(tmp_path, monkeypatch):
    executable = tmp_path / "Bin64" / game.MOD_EXE
    executable.parent.mkdir()
    executable.touch()
    events = []
    monkeypatch.setattr(game, "game_processes", lambda *a:
        [process(tmp_path / "Bin64/rFactor2.exe")] if events else [])
    monkeypatch.setattr(game.subprocess, "Popen", lambda *a, **k:
        events.append("launch") or SimpleNamespace(poll=lambda: 0))
    fake_clock(monkeypatch)
    with pytest.raises(RuntimeError, match="regular rFactor 2, not Developer Mode"):
        game.launch_developer(tmp_path, timeout=3)


def test_launch_never_reports_success_for_a_quick_exit(tmp_path, monkeypatch):
    executable = tmp_path / "Bin64" / game.MOD_EXE
    executable.parent.mkdir()
    executable.touch()
    monkeypatch.setattr(game, "game_processes", lambda *a: [])
    monkeypatch.setattr(game.subprocess, "Popen", lambda *a, **k: SimpleNamespace(poll=lambda: 0))
    fake_clock(monkeypatch)
    with pytest.raises(RuntimeError, match="did not stay running"):
        game.launch_developer(tmp_path, timeout=3)


def test_output_root_is_forwarded_to_source_conversion(tmp_path, monkeypatch):
    import build_track
    import check_setup
    commands = []
    class StopAfterSource(Exception):
        pass
    def capture(command, **kw):
        commands.append(command)
        raise StopAfterSource
    monkeypatch.setattr(check_setup, "check", lambda *a, **k: True)
    monkeypatch.setattr(build_track, "run", capture)
    out = tmp_path / "builds"
    with pytest.raises(StopAfterSource):
        build_track.main([str(tmp_path / "source"), "--out-root", str(out)])
    assert commands[0][commands[0].index("--out") + 1] == str(out / "source")
