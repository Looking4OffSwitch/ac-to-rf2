"""Generated sources: format drift and corruption must fail before conversion."""
import struct

import pytest

import convert_track as ct
from kn5 import KN5, MAX_NODE_DEPTH, iter_textures
from make_aiw import read_fast_lane
from make_cam import read_cameras
from source_formats import SourceFormatError, read_fast_lane_file, read_ini
from test_regressions import kn5_file, material, mesh_bytes, string, u32


def model(tmp_path):
    return kn5_file(tmp_path / "source.kn5", [mesh_bytes("mesh_probe")])


def replace_value(path, offset, fmt, value):
    data = bytearray(path.read_bytes())
    struct.pack_into(fmt, data, offset, value)
    path.write_bytes(data)


@pytest.mark.parametrize("version", [0, 4, 7, 0xffffffff])
@pytest.mark.parametrize("consumer", ["model", "alpha", "extract"])
def test_unknown_kn5_versions_fail_in_every_reader(tmp_path, version, consumer):
    path = model(tmp_path)
    replace_value(path, 6, "<I", version)
    out = tmp_path / "textures"
    out.mkdir()
    with pytest.raises(SourceFormatError, match=r"source.kn5: KN5 v.*byte 6: unsupported version"):
        if consumer == "model":
            KN5(path)
        elif consumer == "alpha":
            ct.texture_alpha_stats([path])
        else:
            ct.extract_textures([path], out, {})
    assert not list(out.iterdir())


@pytest.mark.parametrize("version", [5, 6])
def test_known_versions_preserve_geometry_and_texture_bytes(tmp_path, version):
    path = model(tmp_path)
    if version == 5:
        data = path.read_bytes()
        path.write_bytes(data[:6] + u32(5) + data[14:])
    result = KN5(path, geometry=True)
    assert result.version == version and result.consumed == result.size
    assert list(result.walk())[1].verts[2] == (30., 0., 0.)
    assert list(iter_textures(path)) == [("a.dds", 1, b"DDS " + bytes(124))]


def test_every_truncation_of_model_fails_with_source_location(tmp_path):
    path = model(tmp_path)
    complete = path.read_bytes()
    for length in range(len(complete)):
        path.write_bytes(complete[:length])
        with pytest.raises(SourceFormatError, match=r"source.kn5: KN5.*byte"):
            KN5(path)


@pytest.mark.parametrize("corruption", ["signature", "string_size", "texture_size", "texture_count", "active_flag"])
def test_texture_prefix_is_checked_consistently_before_extraction(tmp_path, corruption):
    path = model(tmp_path)
    if corruption == "signature":
        replace_value(path, 0, "<B", 0)
    elif corruption == "string_size":
        replace_value(path, 22, "<I", 0xffffffff)
    elif corruption == "texture_size":
        replace_value(path, 31, "<I", 0xffffffff)
    elif corruption == "texture_count":
        replace_value(path, 14, "<I", 0xffffffff)
    else:
        replace_value(path, 18, "<I", 99)
    out = tmp_path / "textures"
    out.mkdir()
    for reader in (lambda: KN5(path), lambda: ct.texture_alpha_stats([path]),
                   lambda: ct.extract_textures([path], out, {})):
        with pytest.raises(SourceFormatError):
            reader()
    assert not list(out.iterdir())


def test_kn5_rejects_unrecognized_trailing_extension(tmp_path):
    path = model(tmp_path)
    path.write_bytes(path.read_bytes() + b"UNRECOGNIZED_EXTENSION")
    with pytest.raises(SourceFormatError, match="22 unexpected trailing bytes"):
        KN5(path)


@pytest.mark.parametrize("duplicate", ["texture", "property", "sampler"])
def test_duplicate_definitions_cannot_be_silently_overwritten(tmp_path, duplicate):
    source = material()
    if duplicate == "property":
        source.props["duplicate"] = .7
    elif duplicate == "sampler":
        source.textures["duplicate"] = "b.dds"
    path = kn5_file(tmp_path / "duplicate.kn5", [mesh_bytes("mesh_probe")], [source])
    data = path.read_bytes()
    if duplicate == "texture":
        end = 14 + 4 + 4 + len(string("a.dds")) + 4 + 128
        entry = data[18:end]
        data = data[:14] + u32(2) + entry + entry + data[end:]
    else:
        data = data.replace(string("duplicate"), string("ksDiffuse" if duplicate == "property" else "txDiffuse"))
    path.write_bytes(data)
    with pytest.raises(SourceFormatError, match="duplicate"):
        KN5(path)


@pytest.mark.parametrize("corruption", ["node_type", "child_count", "boolean", "vertex_count",
                                       "index_count", "index", "material", "position", "normal", "uv"])
def test_invalid_mesh_references_counts_and_numbers_fail_without_decoding(tmp_path, corruption):
    path = model(tmp_path)
    start = path.read_bytes().index(string("mesh_probe")) - 4
    count_at = start + 4 + len(string("mesh_probe")) + 4 + 4
    vertex_at = count_at + 4
    indices_at = vertex_at + 3 * 44 + 4
    offsets = {
        "node_type": (start, "<I", 99),
        "child_count": (start + 4 + len(string("mesh_probe")), "<I", 0xffffffff),
        "boolean": (count_at - 4, "<B", 2),
        "vertex_count": (count_at, "<I", 0xffffffff),
        "index_count": (indices_at - 4, "<I", 4),
        "index": (indices_at, "<H", 3),
        "material": (indices_at + 6, "<I", 1),
        "position": (vertex_at, "<f", float("nan")),
        "normal": (vertex_at + 12, "<f", float("inf")),
        "uv": (vertex_at + 24, "<f", float("-inf")),
    }
    replace_value(path, *offsets[corruption])
    with pytest.raises(SourceFormatError, match=r"source.kn5: KN5 v6, node .*byte"):
        KN5(path, geometry=False)


@pytest.mark.parametrize("field", ["blend", "depth", "property", "encoding"])
def test_invalid_material_metadata_is_not_defaulted(tmp_path, field):
    path = model(tmp_path)
    data = path.read_bytes()
    start = data.index(string("asphalt"))
    flags = start + len(string("asphalt")) + len(string("ksPerPixel"))
    if field == "blend":
        replace_value(path, flags, "<B", 99)
    elif field == "depth":
        replace_value(path, flags + 2, "<I", 99)
    elif field == "property":
        replace_value(path, data.index(string("ksDiffuse")) + len(string("ksDiffuse")), "<f", float("nan"))
    else:
        replace_value(path, start + 4, "<B", 255)
    with pytest.raises(SourceFormatError):
        KN5(path)


def test_excessive_tree_depth_is_a_format_error_not_recursion_error(tmp_path):
    path = tmp_path / "deep.kn5"
    transform = struct.pack("<16f", *([0.] * 16))
    branch = u32(1) + string("branch") + u32(1) + b"\1" + transform
    leaf = u32(1) + string("leaf") + u32(0) + b"\1" + transform
    path.write_bytes(b"sc6969" + u32(6) + u32(0) + u32(0) + u32(0)
                     + branch * (MAX_NODE_DEPTH + 1) + leaf)
    with pytest.raises(SourceFormatError, match="nesting exceeds supported depth"):
        KN5(path)


def test_texture_extraction_rejects_path_escape(tmp_path):
    path = model(tmp_path)
    out = tmp_path / "textures"
    out.mkdir()
    with pytest.raises(SourceFormatError, match="unsafe extracted texture filename"):
        ct.extract_textures([path], out, {"a.dds": "../outside.dds"})
    assert not (tmp_path / "outside.dds").exists()


def ai_bytes(grid=False):
    points = b"".join(struct.pack("<4fi", float(i), 2., 3., float(i), i) for i in range(3))
    data = struct.pack("<4i", 7, 3, 0, 0) + points + u32(3) + bytes(3 * 72) + u32(int(grid))
    if grid:
        data += struct.pack("<6fif", *([0.] * 6), 1, 1.) + u32(1) + u32(1) + u32(2) + u32(0) + u32(2)
    return data


def ai_path(tmp_path, data):
    path = tmp_path / "ai/fast_lane.ai"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("grid", [False, True])
def test_valid_ai_extensions_are_checked_and_both_consumers_agree(tmp_path, grid):
    path = ai_path(tmp_path, ai_bytes(grid))
    expected = [(float(i), 2., 3.) for i in range(3)]
    assert read_fast_lane_file(path) == read_fast_lane(tmp_path) == ct.racing_line(tmp_path) == expected


def test_every_ai_truncation_fails_instead_of_generating_another_line(tmp_path):
    complete = ai_bytes(grid=True)
    path = ai_path(tmp_path, complete)
    for length in range(len(complete)):
        path.write_bytes(complete[:length])
        with pytest.raises(SourceFormatError, match=r"fast_lane.ai: AC racing line.*byte"):
            read_fast_lane_file(path)


@pytest.mark.parametrize("corruption", ["version", "count", "extra_count", "point", "point_id",
                                       "grid_flag", "grid_count", "grid_subcount", "tail"])
def test_bad_ai_is_never_treated_as_missing(tmp_path, corruption):
    path = ai_path(tmp_path, ai_bytes(grid=True))
    grid_at = 16 + 3 * 20 + 4 + 3 * 72
    offsets = {"version": (0, "<i", 8), "count": (4, "<i", -1),
               "extra_count": (76, "<i", 2), "point": (16, "<f", float("inf")),
               "point_id": (32, "<i", -1), "grid_flag": (grid_at, "<i", 9),
               "grid_count": (grid_at + 36, "<i", 0x7fffffff),
               "grid_subcount": (grid_at + 40, "<i", -1)}
    if corruption == "tail":
        path.write_bytes(path.read_bytes() + b"new extension")
    else:
        replace_value(path, *offsets[corruption])
    for reader in (read_fast_lane, ct.racing_line):
        with pytest.raises(SourceFormatError):
            reader(tmp_path)


def test_only_missing_and_explicitly_empty_ai_can_fall_back(tmp_path):
    assert read_fast_lane(tmp_path) == ct.racing_line(tmp_path) == []
    path = ai_path(tmp_path, struct.pack("<3i", 3, 0, 0))
    with pytest.warns(UserWarning, match="empty AC v3 AI stub"):
        assert read_fast_lane_file(path) == []
    path.write_bytes(struct.pack("<6i", 7, 0, 0, 0, 0, 0))
    with pytest.warns(UserWarning, match="empty v7 AI"):
        assert read_fast_lane_file(path) == []
    path.write_bytes(b"")
    with pytest.raises(SourceFormatError):
        read_fast_lane_file(path)


@pytest.mark.parametrize("content", ["[SURFACE_0]\nFRICTION=1", "[SURFACE_0]\nKEY=ROAD\nFRICTION=nan",
                                     "[SURFACE_0]\nKEY=ROAD\nFRICTION=-1",
                                     "[SURFACE_0]\nKEY=ROAD\nIS_VALID_TRACK=yes"])
def test_surface_errors_include_file_and_section(tmp_path, content):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/surfaces.ini").write_text(content)
    with pytest.raises(SourceFormatError, match=r"surfaces.ini: \[SURFACE_0\]"):
        ct.load_surfaces(tmp_path, tmp_path)


@pytest.mark.parametrize("content", ["[MODEL_0]\nPOSITION=0,0,0", "[MODEL_0]\nFILE=absent.kn5",
                                     "[MODEL_0]\nFILE=source.kn5\nPOSITION=nan,0,0",
                                     "[MODEL_0]\nFILE=source.kn5\nPOSITION=1,,3",
                                     "[MODEL_0]\nFILE=source.kn5\nROTATION=0,0,0,90",
                                     "[FUTURE_MODEL_LIST]\nFILE=source.kn5"])
def test_declared_model_errors_cannot_silently_drop_geometry(tmp_path, content):
    model(tmp_path)
    (tmp_path / "models.ini").write_text(content)
    with pytest.raises(SourceFormatError, match="models.ini"):
        ct.layout_models(tmp_path)


def test_requested_layout_cannot_fall_back_to_a_different_model_list(tmp_path):
    model(tmp_path)
    (tmp_path / "models.ini").write_text("[MODEL_0]\nFILE=source.kn5")
    with pytest.raises(SourceFormatError, match="models_absent.ini: requested layout"):
        ct.layout_models(tmp_path, "absent")


def test_declared_kn5_disappearing_between_passes_is_not_silently_skipped(tmp_path):
    path = tmp_path / "absent.kn5"
    for reader in (lambda: ct.texture_alpha_stats([path]),
                   lambda: ct.extract_textures([path], tmp_path, {})):
        with pytest.raises(FileNotFoundError):
            reader()


def test_unknown_ini_keys_and_sections_and_short_heading_remain_compatible(tmp_path):
    model(tmp_path)
    (tmp_path / "models.ini").write_text("[MODEL_0]\nFILE=source.kn5\nROTATION=-17\nFUTURE_KEY=whatever\n"
                                         "[FUTURE_SECTION]\nKEY=value\n", encoding="utf-8-sig")
    models, _, warnings = ct.layout_models(tmp_path)
    assert len(models) == 1 and models[0][1][1] == [-17., 0., 0.] and not warnings


@pytest.mark.parametrize("content", [b"not INI", b"[SECTION]\nKEY=\xff"])
def test_bad_ini_syntax_or_encoding_has_source_context(tmp_path, content):
    path = tmp_path / "source.ini"
    path.write_bytes(content)
    with pytest.raises(SourceFormatError, match="source.ini: invalid INI"):
        read_ini(path)


@pytest.mark.parametrize("fields", ["FORWARD=1,0,0", "POSITION=1,2,3\nFORWARD=1,0",
                                    "POSITION=nan,2,3\nFORWARD=1,0,0",
                                    "POSITION=1,2,3\nFORWARD=0,0,0"])
def test_malformed_camera_sections_are_not_silently_ignored(tmp_path, fields):
    (tmp_path / "cameras.ini").write_text("[CAMERA_0]\n" + fields)
    with pytest.raises(SourceFormatError, match=r"cameras.ini: \[CAMERA_0\]"):
        read_cameras(tmp_path)


def test_unknown_rendering_shader_warns_without_changing_known_mapping(tmp_path, monkeypatch, capsys):
    from test_regressions import terrain_template
    kn5_file(tmp_path / (tmp_path.name + ".kn5"), [mesh_bytes("1ROAD")],
             [material(shader="future_shader_v2")])
    out = tmp_path / "out"
    monkeypatch.setattr("sys.argv", ["convert_track.py", str(tmp_path), "--out", str(out),
        "--ac-root", str(tmp_path), "--tdf-template", str(terrain_template(tmp_path))])
    ct.main()
    assert "unrecognized source shader 'future_shader_v2'" in capsys.readouterr().out


def test_pipeline_stops_before_export_or_install_on_unsupported_source(tmp_path, monkeypatch):
    import build_track
    import check_setup
    from test_regressions import terrain_template
    track = tmp_path / "track"
    track.mkdir()
    source = kn5_file(track / "track.kn5", [mesh_bytes("1ROAD")])
    replace_value(source, 6, "<I", 7)
    installed = tmp_path / "locations/track"
    installed.mkdir(parents=True)
    sentinel = installed / "working.gdb"
    sentinel.write_bytes(b"existing location")
    commands = []
    def run_source_only(command, **kwargs):
        commands.append(command[1])
        assert command[1] == "convert_track.py", "Later stages must never run"
        monkeypatch.setattr("sys.argv", command[1:] + ["--out", str(tmp_path / "out"),
            "--ac-root", str(tmp_path), "--tdf-template", str(terrain_template(tmp_path))])
        ct.main()
    monkeypatch.setattr(check_setup, "check", lambda *args, **kwargs: True)
    monkeypatch.setattr(build_track, "run", run_source_only)
    monkeypatch.setattr("sys.argv", ["ac2rf2", str(track), "--install", str(installed.parent)])
    with pytest.raises(SourceFormatError, match="unsupported version"):
        build_track.main()
    assert commands == ["convert_track.py"]
    assert sentinel.read_bytes() == b"existing location"
    assert list(installed.iterdir()) == [sentinel]
