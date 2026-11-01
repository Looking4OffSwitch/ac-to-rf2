import json
import os
from pathlib import Path
import struct
import subprocess
import sys

import pytest

from ac_to_rf2.verify_install import verify


def fixture(tmp_path):
    installed, out = tmp_path / "venue", tmp_path / "out"
    gmts, maps, layout = installed / "Assets/GMTs", installed / "Assets/MAPs", installed / "venue"
    for p in (gmts, maps, layout, out / "gmt"):
        p.mkdir(parents=True)
    rows, records = [], []
    for name in ("a", "b"):
        rows.append({"mesh": name, "mesh_id": "0:" + name, "rf2_material": name,
                     "textures": {"txDiffuse": name + ".dds"}, "alpha_test": True,
                     "render": True, "tris": 1})
        records.append({"mesh": name, "mesh_id": "0:" + name, "material": name,
                        "gmt": name + ".gmt", "part": 0, "parts": 1})
        b = bytearray(600)
        shader = b"L2BUMPSPECMAPT0"
        b[128:128 + len(shader)] = shader
        struct.pack_into("<f", b, 48, .5)
        struct.pack_into("<f", b, 64, .5)
        struct.pack_into("<f", b, 260, 14000.)
        tex = (name + ".dds").encode()
        b[320:320 + len(tex)] = tex
        struct.pack_into("<I", b, 384, 0x80)
        b[420] = 191
        (gmts / (name + ".gmt")).write_bytes(b)
        dds = bytearray(128)
        dds[:4] = b"DDS "
        struct.pack_into("<II", dds, 12, 4, 4)
        (maps / (name + ".dds")).write_bytes(dds)
    for name in ("xfinish", "xsector1", "xsector2"):
        (gmts / (name + ".gmt")).write_bytes((gmts / "a.gmt").read_bytes())
        records.append({"mesh": name, "gmt": name + ".gmt", "timing": True})
    (out / "material_map.json").write_text(json.dumps({"meshes": rows, "alpha_ref": {"a": 191, "b": 191}}))
    (out / "gmt/exported.json").write_text(json.dumps(records))
    (layout / "venue.scn").write_text("\n".join(
        "Instance=%s\n{\nMeshFile=%s ShadowCaster=(Static,Texture)\n}" %
        (r["mesh"], r["gmt"]) for r in records))
    for p in (layout / "venue.gdb", layout / "venue.AIW", installed / "venue.tdf"):
        p.write_text("fixture")
    return installed, out


def test_verifier_accepts_complete_manifest(tmp_path):
    installed, out = fixture(tmp_path)
    assert verify(installed, out) == 0


def test_missing_cutout_is_not_skipped_when_another_passes(tmp_path, capsys):
    installed, out = fixture(tmp_path)
    p = installed / "Assets/GMTs/b.gmt"
    p.write_bytes(p.read_bytes().replace(b"b.dds", b"a.dds"))
    assert verify(installed, out) == 1
    assert "expected cut-out texture b.dds missing" in capsys.readouterr().out


def test_missing_scene_gmt_and_database_fail(tmp_path, capsys):
    installed, out = fixture(tmp_path)
    (installed / "Assets/GMTs/b.gmt").unlink()
    (installed / "venue/venue.gdb").unlink()
    assert verify(installed, out) == 1
    text = capsys.readouterr().out
    assert "scene references missing GMT" in text
    assert "missing required location file" in text


def test_real_blender_52_geometry_api():
    binary = Path(os.environ.get("BLENDER_EXE", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"))
    if not binary.is_file():
        pytest.skip("Blender 5.2 not installed; set BLENDER_EXE to run the API smoke test")
    result = subprocess.run([str(binary), "--background", "--factory-startup",
                             "--python-exit-code", "1", "--python",
                             str(Path(__file__).with_name("blender_smoke.py"))],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "AC2RF2 BLENDER SMOKE" in result.stdout
