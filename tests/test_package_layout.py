"""Installed commands must work without the checkout's root on sys.path."""
import os
import json
from pathlib import Path
import subprocess
import sys
import shutil

import pytest

from ac_to_rf2 import project_paths
from ac_to_rf2.blender_paths import TOOLS_DIR
from test_verification import fixture


ROOT = Path(__file__).resolve().parents[1]


def test_root_has_no_application_modules_and_existing_workspace_paths_are_preserved(tmp_path, monkeypatch):
    assert not list(ROOT.glob("*.py"))
    monkeypatch.delenv("AC2RF2_WORKSPACE", raising=False)
    monkeypatch.chdir(tmp_path)
    assert project_paths.workspace_dir() == ROOT
    assert TOOLS_DIR == ROOT / ".tools"


def test_workspace_override_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("AC2RF2_WORKSPACE", str(tmp_path))
    assert project_paths.workspace_dir() == tmp_path


def test_wheel_install_defaults_to_working_directory_not_site_packages(tmp_path, monkeypatch):
    monkeypatch.delenv("AC2RF2_WORKSPACE", raising=False)
    monkeypatch.setattr(project_paths, "PACKAGE_DIR", tmp_path / "venv/Lib/site-packages/ac_to_rf2")
    working = tmp_path / "work"
    working.mkdir()
    monkeypatch.chdir(working)
    assert project_paths.workspace_dir() == working


@pytest.mark.parametrize("module", ["ac_to_rf2", "ac_to_rf2.build_track", "ac_to_rf2.drive_track",
                                   "ac_to_rf2.check_setup", "ac_to_rf2.setup_tools"])
def test_module_entry_points_from_unrelated_directory(tmp_path, module):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-m", module, "--help"], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "usage:" in result.stdout.lower()


def test_verifier_module_from_unrelated_directory(tmp_path):
    installed, out = fixture(tmp_path)
    working = tmp_path / "unrelated"
    working.mkdir()
    result = subprocess.run([sys.executable, "-m", "ac_to_rf2.verify_install", str(installed), str(out)],
                            cwd=working, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "all checks passed" in result.stdout


def test_blender_wheel_entry_does_not_load_virtualenv_numpy(tmp_path, monkeypatch):
    from ac_to_rf2.blender_paths import PORTABLE_BLENDER
    from ac_to_rf2.build_track import write_solid_texture
    from ac_to_rf2 import convert_track
    from test_regressions import kn5_file, mesh_bytes, terrain_template
    if not PORTABLE_BLENDER.is_file():
        pytest.skip("Portable Blender/exporter not installed")
    track = tmp_path / "source"
    track.mkdir()
    kn5_file(track / "source.kn5", [mesh_bytes("1ROAD")])
    out = tmp_path / "build"
    monkeypatch.setattr("sys.argv", ["convert", str(track), "--out", str(out), "--textures",
        "--ac-root", str(tmp_path), "--tdf-template", str(terrain_template(tmp_path))])
    convert_track.main()
    write_solid_texture(out / "textures/a.dds", (255, 255, 255))
    site = tmp_path / "site-packages"
    package = site / "ac_to_rf2"
    shutil.copytree(project_paths.PACKAGE_DIR, package, ignore=shutil.ignore_patterns("__pycache__"))
    (site / "numpy").mkdir()
    (site / "numpy/__init__.py").write_text("raise AssertionError('foreign virtualenv NumPy was loaded')")
    env = dict(os.environ, AC2RF2_TOOLS_DIR=str(TOOLS_DIR.resolve()), AC2RF2_WORKSPACE=str(tmp_path))
    exported = tmp_path / "gmt"
    result = subprocess.run([str(PORTABLE_BLENDER), "--background", "--factory-startup",
        "--python-exit-code", "1", "--python", str(package / "blender_entry.py"), "--",
        str(out / "material_map.json"), str(exported), "--limit", "1"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    records = json.loads((exported / "exported.json").read_text())
    assert len(records) == 1 and (exported / records[0]["gmt"]).stat().st_size >= 264
