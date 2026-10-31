"""Exercise the real community exporter on generated geometry and inspect GMT bytes."""
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
import blender_stage as bs
from build_track import write_solid_texture
from exporter_support import enable_exporter
from material_policy import set_blending
from verify_install import read_gmt

output = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
output.mkdir(parents=True, exist_ok=True)
bs.ADDON, addon = enable_exporter()
bs.silence_popups()
empty_t, ob_t, plain, coll = bs.make_template()
bump = bs.make_shader_template(ob_t, bs.BUMP_SHADER, bs.BUMP_SLOTS)
write_solid_texture(output / "white.dds", (255, 255, 255))
images = {}
for filename, rgb in [("white.dds", (255, 255, 255)), ("spec.dds", (0, 0, 0)),
                      ("normal.dds", (128, 128, 255))]:
    write_solid_texture(output / filename, rgb)
    images[filename] = bpy.data.images.load(str(output / filename))
geometry = ([(5., 0., 0.), (5., 0., -1.), (5., 1., -1.)],
            [(0., 0.), (1., 0.), (1., 1.)], [(0, 1, 2)], [(0., 2 ** -.5, 2 ** -.5)] * 3)
results = {}
for mode in ("opaque", "blend", "cutout"):
    material = (bump if mode == "cutout" else plain).copy()
    material.name = mode
    material.Ambient_Color = (.2, .2, .2, 1.)
    material.Diffuse_Color = (.4, .4, .4, 1.)
    set_blending(material, mode)
    for node in material.node_tree.nodes:
        if node.type == "TEX_IMAGE":
            filename = "spec.dds" if node.name == "sSpec" else "normal.dds" if node.name == "sBump" else "white.dds"
            node.image = images[filename]
    if mode == "cutout":
        node = material.node_tree.nodes["sBase"]
        node.Alpha_Reference = 191
        assert bs.set_texture_flag(node, 0x80)
    empty, ob = bs.build_mesh(geometry, bs.AC_TO_RF2, mode, material,
                              empty_t, ob_t, coll)
    for obj in bpy.data.objects:
        obj.select_set(False)
    empty.select_set(True)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = empty
    bpy.ops.export_scene.export_gmt_override(directory=str(output) + "/",
                                            filename=mode + ".gmt", check_existing=False)
    path = output / (mode + ".gmt")
    data = path.read_bytes()
    gmt = read_gmt(path)
    at = data.index(gmt["shader"].encode())
    ambient = struct.unpack_from("<f", data, at - 80)[0]
    diffuse = struct.unpack_from("<f", data, at - 64)[0]
    factors = struct.unpack_from("<II", data, at - 16)
    assert abs(ambient - .2) < 1e-6 and abs(diffuse - .4) < 1e-6
    assert factors == ((5, 6) if mode == "blend" else (2, 1)), factors
    if mode == "cutout":
        assert gmt["alpha_refs"]["white.dds"] == 191
        assert gmt["tex_flags"]["white.dds"] & 0x80
    # The authored diagonal normal differs from both the face and constant up.
    # Check it immediately after a known vertex position in the GMT records.
    hits = []
    position = struct.pack("<3f", -5., 0., 0.)
    start = 0
    while True:
        hit = data.find(position, start)
        if hit < 0:
            break
        if hit + 24 <= len(data):
            normal = struct.unpack_from("<3f", data, hit + 12)
            if abs(sum(v * v for v in normal) - 1.) < 1e-5:
                hits.append(normal)
        start = hit + 4
    # Blender packs custom normals; measured round-trip error is ~4e-5.
    expected_normal = (0., 2 ** -.5, 2 ** -.5)
    assert any(max(abs(a - b) for a, b in zip(n, expected_normal)) < 1e-4
               for n in hits), hits
    results[mode] = {"blend": factors, "ambient": ambient, "diffuse": diffuse,
                     "authored_normal": True}
    mesh = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.objects.remove(empty, do_unlink=True)
    bpy.data.meshes.remove(mesh)
print("AC2RF2 EXPORTER SMOKE " + json.dumps(results))
