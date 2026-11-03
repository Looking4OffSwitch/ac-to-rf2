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
        b = bytearray(764)
        struct.pack_into("<II", b, 0, 316, 0)
        struct.pack_into("<I", b, 320, 1)
        shader = b"L2BUMPSPECMAPT0"
        b[472:472 + len(shader)] = shader
        struct.pack_into("<f", b, 392, .5)
        struct.pack_into("<f", b, 408, .5)
        struct.pack_into("<f", b, 260, 14000.)
        tex = (name + ".dds").encode()
        b[584:584 + len(tex)] = tex
        struct.pack_into("<I", b, 580, 1)
        struct.pack_into("<I", b, 656, 1)
        struct.pack_into("<I", b, 648, 0x80)
        b[684] = 191
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
    (installed / "venue.tdf").write_text("[LOOSE]\n" + "".join(
        "Reaction=" + name + " Tex=x.tga\n" for name in
        ("spark", "whitesmoke", "blacksmoke", "flames", "groove", "wallskid")))
    from ac_to_rf2.make_aiw import render_aiw
    boxes = [(4, 0, 1, 0)]
    (layout / "venue.AIW").write_text(render_aiw(
        [(0, 0, 0, 6), (10, 0, 0, 6), (0, 0, 10, 6)], 34,
        [((0, 0, 0), 0, "start")], boxes, boxes,
        dict(entry=0, exit=1, lane=[(3, 0, 0, 0), (6, 0, 0, 0)],
             boxes=boxes, side=1)))
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


def test_verifier_rejects_nonempty_broken_aiw(tmp_path, capsys):
    installed, out = fixture(tmp_path)
    (installed / "venue/venue.AIW").write_text("fixture")
    assert verify(installed, out) == 1
    assert "AIW: number_waypoints" in capsys.readouterr().out


def test_verifier_rejects_terrain_missing_global_effects(tmp_path, capsys):
    installed, out = fixture(tmp_path)
    (installed / "venue.tdf").write_text("[FEEDBACK]\nMaterials=road\n")
    assert verify(installed, out) == 1
    assert "missing [LOOSE] global effects" in capsys.readouterr().out


def test_vertex_bytes_are_not_texture_references(tmp_path):
    from ac_to_rf2.verify_install import read_gmt
    installed, out = fixture(tmp_path)
    p = installed / "Assets/GMTs/a.gmt"
    b = bytearray(p.read_bytes())
    b[100:112] = b"Kr.DdS\0sBase"
    p.write_bytes(b)
    assert read_gmt(p)["textures"] == {b"a.dds"}
    assert verify(installed, out) == 0


def test_real_texture_missing_from_install_is_still_rejected(tmp_path, capsys):
    installed, out = fixture(tmp_path)
    (installed / "Assets/MAPs/a.dds").unlink()
    assert verify(installed, out) == 1
    assert "textures referenced but not installed" in capsys.readouterr().out


def test_truncated_material_table_is_rejected(tmp_path, capsys):
    installed, out = fixture(tmp_path)
    p = installed / "Assets/GMTs/a.gmt"
    p.write_bytes(p.read_bytes()[:-1])
    assert verify(installed, out) == 1
    assert "invalid GMT a.gmt" in capsys.readouterr().out


def test_multiple_material_records_are_read_by_count(tmp_path):
    from ac_to_rf2.verify_install import read_gmt
    installed, _out = fixture(tmp_path)
    p = installed / "Assets/GMTs/a.gmt"
    b = bytearray(p.read_bytes())
    second = bytearray(b[324:])
    second[260:265] = b"z.dds"
    b.extend(second)
    struct.pack_into("<I", b, 320, 2)
    p.write_bytes(b)
    assert read_gmt(p)["textures"] == {b"a.dds", b"z.dds"}
