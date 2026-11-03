import copy
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest

from ac_to_rf2 import convert_track as ct
from ac_to_rf2 import fix_textures
from ac_to_rf2.install_location import install_location
from ac_to_rf2.kn5 import KN5
from ac_to_rf2.material_policy import coefficient, opacity_mode, set_blending
from ac_to_rf2.scene_contract import (MaterialNames, index_meshes, model_meshes,
                            surface_prefix, validate_exports)
from ac_to_rf2.terrain import surface_tdf


def u32(n):
    return struct.pack("<I", n)


def string(value):
    b = value.encode()
    return u32(len(b)) + b


def material(name="asphalt", texture="a.dds", shader="ksPerPixel", kd=.3):
    return SimpleNamespace(name=name, shader=shader, blend=0, alpha_tested=0,
                           depth_mode=0, props={"ksDiffuse": kd},
                           textures={"txDiffuse": texture})


def material_bytes(m):
    return (string(m.name) + string(m.shader) + bytes([m.blend, m.alpha_tested])
            + u32(m.depth_mode) + u32(len(m.props))
            + b"".join(string(k) + struct.pack("<10f", v, *([0.] * 9))
                       for k, v in m.props.items())
            + u32(len(m.textures))
            + b"".join(string(k) + u32(i) + string(t)
                       for i, (k, t) in enumerate(m.textures.items())))


def mesh_bytes(name, mat_id=0, skinned=False):
    verts = [(0., 0., 0.), (0., 0., 30.), (30., 0., 0.)]
    node = u32(3 if skinned else 2) + string(name) + u32(0) + bytes([1, 1, 1, 0])
    if skinned:
        node += u32(1) + string("bone") + struct.pack("<16f", *([0.] * 16))
    node += u32(3)
    for i, v in enumerate(verts):
        node += struct.pack("<11f", *v, 0., 1., 0., float(i == 2),
                            float(i == 1), 1., 0., 0.)
        if skinned:
            node += struct.pack("<8f", 1., 0., 0., 0., 0., 0., 0., 0.)
    node += u32(3) + struct.pack("<3H", 0, 1, 2)
    node += u32(mat_id) + u32(0) + struct.pack("<2f", 0., 100.)
    if not skinned:
        node += struct.pack("<4f", 10., 0., 10., 20.) + bytes([1])
    return node


def kn5_file(path, nodes, mats=None, extra=912125):
    mats = mats or [material()]
    identity = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]
    texture = b"DDS " + bytes(124)
    textures = u32(1) + u32(1) + string("a.dds") + u32(len(texture)) + texture
    root = u32(1) + string("root") + u32(len(nodes)) + bytes([1]) + struct.pack("<16f", *identity)
    path.write_bytes(b"sc6969" + u32(6) + u32(extra) + textures
                     + u32(len(mats)) + b"".join(map(material_bytes, mats))
                     + root + b"".join(nodes))
    return path


@pytest.mark.parametrize("extra", [0, 912125, 781233, 673425])
def test_v6_metadata_is_not_a_payload_length(tmp_path, extra):
    path = kn5_file(tmp_path / "model.kn5", [mesh_bytes("road")], extra=extra)
    model = KN5(path, geometry=True)
    assert model.consumed == model.size
    node = list(model.walk())[1]
    assert node.verts[2] == (30., 0., 0.)
    assert ct.texture_alpha_stats([path]) == {"a.dds": None}
    textures = tmp_path / "textures"
    textures.mkdir()
    assert ct.extract_textures([path], textures, {"a.dds": "a.dds"}) == 1
    assert (textures / "a.dds").read_bytes()[:4] == b"DDS "


def test_skinned_flags_bones_and_tail_do_not_consume_sibling(tmp_path):
    path = kn5_file(tmp_path / "skin.kn5", [mesh_bytes("skin", skinned=True),
                                           mesh_bytes("sibling")])
    model = KN5(path, geometry=True)
    nodes = list(model.walk())[1:]
    assert [n.name for n in nodes] == ["skin", "sibling"]
    assert nodes[0].normals[0] == (0., 1., 0.)
    assert model.consumed == model.size


def test_duplicate_names_have_stable_distinct_ids(tmp_path):
    model = KN5(kn5_file(tmp_path / "m.kn5", [mesh_bytes("D"), mesh_bytes("D")]))
    rows = [{"mesh_id": key, "mesh": node.name}
            for key, node in model_meshes(model, 0)]
    assert len(index_meshes(rows)) == 2
    assert rows[0]["mesh_id"] != rows[1]["mesh_id"]
    assert list(model_meshes(model, 1))[0][0] != rows[0]["mesh_id"]
    with pytest.raises(ValueError, match="ambiguous"):
        index_meshes([{"mesh": "D"}, {"mesh": "D"}])


def test_material_names_preserve_punctuation_textures_and_coefficients():
    names = MaterialNames()
    a = material("asph-pitlane-old")
    variants = [a, material("asph_pitlane_old"), material(a.name, "b.dds"),
                material(a.name, kd=.7), material(a.name, shader="ksTree")]
    assert len({names.get(m) for m in variants}) == 5
    assert names.get(copy.deepcopy(a)) == names.get(a)
    long_name = names.get(material("x" * 100), surface_prefix("ROAD"))
    assert len(long_name + "_detail_nm.dds") < 64
    assert names.get(a, surface_prefix("ROAD")) != names.get(a, surface_prefix("ASPHNEW"))


def terrain_template(tmp_path):
    p = tmp_path / "terrain.tdf"
    p.write_text("[TRACKVARS]\nRoadDryGrip=1.0\n[FEEDBACK]\n"
                 "Dry=RoadDryGrip Legal=true Resistance=0\nMaterials=road\n"
                 "[FEEDBACK]\nDry=.6 Legal=false Resistance=600\nMaterials=gras\n"
                 "[FEEDBACK]\nLegal=false CollFrict=.13\nMaterials=wall,cem\n")
    return p


def test_surface_grip_and_legality_are_not_merged(tmp_path):
    surfaces = {"ROAD": {"friction": .97, "valid": True},
                "ASPHNEW": {"friction": .99, "valid": True},
                "GRASS": {"friction": .6, "valid": False},
                "CONCRETE": {"friction": .965, "valid": True}}
    rows = [{"surface": key, "surface_prefix": surface_prefix(key),
             "surface_kind": {"GRASS": "gras", "CONCRETE": "cem"}.get(key, "road")}
            for key in surfaces]
    text, applied = surface_tdf(terrain_template(tmp_path), rows + rows, surfaces)
    assert len(applied) == len(surfaces)
    assert "Dry=0.970" in text and "Dry=0.990" in text and "Dry=0.965" in text
    grass = next(c for c in text.split("[FEEDBACK]") if "Materials=" + surface_prefix("GRASS") in c)
    assert "Legal=false" in grass and "Resistance=600" in grass
    assert "Materials=road\n" not in text
    assert len(set(applied)) == 4


def export_fixture(tmp_path):
    mapping = {"meshes": [{"mesh": "D", "mesh_id": "0:1", "rf2_material": "mat",
                            "render": True, "physical": True, "tris": 3}]}
    record = {"mesh": "D", "mesh_id": "0:1", "material": "mat",
              "gmt": "D.gmt", "part": 0, "parts": 1}
    (tmp_path / "D.gmt").write_bytes(bytes(264))
    return mapping, record


def test_export_manifest_rejects_missing_mesh_and_chunks(tmp_path):
    mapping, record = export_fixture(tmp_path)
    validate_exports(mapping, [record], tmp_path)
    with pytest.raises(ValueError, match="missing export"):
        validate_exports(mapping, [], tmp_path)
    with pytest.raises(ValueError, match="incomplete"):
        validate_exports(mapping, [dict(record, parts=2)], tmp_path)
    with pytest.raises(ValueError, match="duplicate GMT"):
        validate_exports(mapping, [record, record], tmp_path)
    with pytest.raises(ValueError, match="stale geometry"):
        validate_exports(mapping, [dict(record, material="wrong")], tmp_path)
    (tmp_path / "D.gmt").write_bytes(bytes(10))
    with pytest.raises(ValueError, match="truncated"):
        validate_exports(mapping, [record], tmp_path)


def test_zero_is_not_missing_and_gradients_blend():
    assert coefficient({"ksDiffuse": 0.}, "ksDiffuse", .42) == 0.
    assert coefficient({}, "ksDiffuse", .42) == .42
    row = {"rf2_material": "gravel", "alpha_test": True, "needs_blend": True}
    assert opacity_mode(row, {"gradients": ["gravel"]}) == "blend"
    assert opacity_mode(row, {"alpha_ref": {"gravel": 191}}) == "cutout"
    assert opacity_mode(row, {"no_alpha_test": ["gravel"]}) == "opaque"


def test_blend_adapter_uses_attributes_and_rejects_unsupported_exporter():
    items = [SimpleNamespace(name=label, identifier=str(i)) for i, label in
             [(1, "Zero"), (2, "One"), (5, "Src Alpha"), (6, "Inv Src Alpha")]]
    prop = SimpleNamespace(enum_items=items)
    m = SimpleNamespace(Blend=False, Blend_Source_List="2", Blend_Destination_List="1",
                        bl_rna=SimpleNamespace(properties={"Blend_Source_List": prop,
                                                          "Blend_Destination_List": prop}))
    set_blending(m, "blend")
    assert (m.Blend_Source_List, m.Blend_Destination_List) == ("5", "6")
    assert m.Blend is True
    set_blending(m, "cutout")
    assert (m.Blend_Source_List, m.Blend_Destination_List) == ("2", "1")
    assert m.Blend is False
    with pytest.raises(RuntimeError, match="lacks"):
        set_blending({}, "blend")


def test_csp_specular_overrides_and_global_multiplier(tmp_path):
    config = tmp_path / "extension"
    config.mkdir()
    (config / "ext_config.ini").write_text("[LIGHTING]\nSPECULAR_MULT=0.15\n"
        "[MATERIAL_ADJUSTMENT_0]\nMATERIALS=grass?\nKEY_0=ksSpecular\nVALUE_0=0\n")
    assert ct.csp_specular_mult(str(tmp_path), str(tmp_path)) == .15
    adjustments = ct.csp_adjustments(str(tmp_path), str(tmp_path))
    assert adjustments[0][0][0].match("grass-side")
    assert adjustments[0][1]["ksSpecular"] == 0.


def test_texture_failure_returns_nonzero(tmp_path, monkeypatch):
    tex = tmp_path / "textures"
    tex.mkdir()
    b = bytearray(176)
    b[:4] = b"DDS "
    struct.pack_into("<II", b, 12, 4, 4)
    struct.pack_into("<I", b, 88, 24)
    (tex / "sample.dds").write_bytes(b)
    monkeypatch.setattr("sys.argv", ["fix_textures.py", str(tex), "--jobs", "1"])
    monkeypatch.setattr(fix_textures.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=1, stdout="failed", stderr=""))
    with pytest.raises(SystemExit, match="conversion failed"):
        fix_textures.main()


def test_failed_copy_keeps_existing_install(tmp_path, monkeypatch):
    stage, dest = tmp_path / "stage", tmp_path / "venue"
    stage.mkdir(); dest.mkdir()
    (dest / "old").write_text("working")
    def denied(*a, **k):
        raise PermissionError("fixture denied")
    monkeypatch.setattr("ac_to_rf2.install_location.shutil.copytree", denied)
    with pytest.raises(PermissionError):
        install_location(stage, dest)
    assert (dest / "old").read_text() == "working"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["stage", "venue"]


def test_failed_publish_rolls_back_and_success_replaces(tmp_path, monkeypatch):
    from ac_to_rf2 import install_location as module
    stage, dest = tmp_path / "stage", tmp_path / "venue"
    stage.mkdir(); dest.mkdir()
    (stage / "new").write_text("replacement")
    (dest / "old").write_text("working")
    real_replace = module.os.replace
    def fail_new(src, dst):
        if "-new-" in Path(src).name:
            raise PermissionError("cannot publish")
        return real_replace(src, dst)
    with monkeypatch.context() as ctx:
        ctx.setattr(module.os, "replace", fail_new)
        with pytest.raises(PermissionError):
            install_location(stage, dest)
    assert (dest / "old").exists()
    install_location(stage, dest)
    assert (dest / "new").read_text() == "replacement"
    assert not (dest / "old").exists()


def test_mapping_joins_duplicate_nodes_and_surface_variants_end_to_end(tmp_path, monkeypatch):
    track = tmp_path / "track"
    (track / "data").mkdir(parents=True)
    (track / "data/surfaces.ini").write_text("[SURFACE_0]\nKEY=ROAD\nFRICTION=.97\nIS_VALID_TRACK=1\n"
        "[SURFACE_1]\nKEY=ASPHNEW\nFRICTION=.99\nIS_VALID_TRACK=1\n")
    kn5_file(track / "track.kn5", [mesh_bytes("D"), mesh_bytes("D", 1),
                                  mesh_bytes("1ROAD"), mesh_bytes("2ASPHNEW")],
             [material(), material("asphalt", "b.dds")])
    out = tmp_path / "output"
    monkeypatch.setattr("sys.argv", ["convert_track.py", str(track), "--out", str(out),
        "--ac-root", str(tmp_path), "--tdf-template", str(terrain_template(tmp_path))])
    ct.main()
    data = json.loads((out / "material_map.json").read_text())
    rows = data["meshes"]
    assert len(index_meshes(rows)) == 4
    assert rows[0]["rf2_material"] != rows[1]["rf2_material"]
    assert rows[2]["surface_prefix"] != rows[3]["surface_prefix"]
    assert "Dry=0.970" in (out / "track.tdf").read_text()
    assert "Dry=0.990" in (out / "track.tdf").read_text()


def test_exporter_loader_rejects_older_blender_and_missing_addon(monkeypatch):
    import sys
    from ac_to_rf2 import exporter_support
    app = SimpleNamespace(version=(4, 5, 0), version_string="4.5.0")
    monkeypatch.setitem(sys.modules, "bpy", SimpleNamespace(app=app))
    monkeypatch.setitem(sys.modules, "addon_utils", SimpleNamespace(enable=lambda *a, **k: None))
    with pytest.raises(RuntimeError, match="5.0 or newer"):
        exporter_support.enable_exporter()
    app.version, app.version_string = (5, 2, 3), "5.2.3"
    with pytest.raises(RuntimeError, match="No compatible rF2 GMT exporter"):
        exporter_support.enable_exporter()


def test_blend_adapter_does_not_assume_enum_indices():
    items = [SimpleNamespace(name=label, identifier=identifier) for identifier, label in
             [("zero-id", "Zero"), ("one-id", "One"),
              ("source-id", "Source Alpha"), ("inverse-id", "Inverse Source Alpha")]]
    prop = SimpleNamespace(enum_items=items)
    m = SimpleNamespace(Blend=False, Blend_Source_List="", Blend_Destination_List="",
                        bl_rna=SimpleNamespace(properties={"Blend_Source_List": prop,
                                                          "Blend_Destination_List": prop}))
    set_blending(m, "blend")
    assert (m.Blend_Source_List, m.Blend_Destination_List) == ("source-id", "inverse-id")


def test_terrain_preserves_global_loose_effects_after_unused_surface(tmp_path):
    template = terrain_template(tmp_path)
    loose = "[LOOSE]\nReaction=whitesmoke Tex=smokewhite.tga Max=256\nReaction=blacksmoke Tex=smokeblack.tga Max=1024\n"
    with template.open("a") as stream:
        stream.write("\n[FEEDBACK]\nMaterials=unused\n" + loose)
    text, _ = surface_tdf(template, [dict(surface_prefix="ac_road_", surface="ROAD", surface_kind="road")],
                          {"ROAD": dict(friction=1.0, valid=True)})
    assert text.index("[TRACKVARS]") < text.index("[FEEDBACK]")
    assert text.count("[LOOSE]") == 1
    assert text.endswith(loose)
    assert "Materials=unused" not in text


def test_terrain_global_effect_validation():
    from ac_to_rf2.terrain import validate_terrain
    assert "missing [LOOSE]" in validate_terrain("[FEEDBACK]\nMaterials=road")[0]
    assert "whitesmoke" in validate_terrain("[LOOSE]\n//Reaction=whitesmoke")[0]
    text = "[LOOSE]\n" + "".join("Reaction=" + name + " Tex=x.tga\n" for name in
        ("spark", "whitesmoke", "blacksmoke", "flames", "groove", "wallskid"))
    assert validate_terrain(text) == []
