"""Run with Blender --background --factory-startup --python (no GMT add-on)."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
from mathutils import Matrix
import blender_stage

assert bpy.app.version >= (5, 2, 0), bpy.app.version_string
# Supply only the add-on's object tag; all geometry/normals/UV operations below
# use Blender's real API. This smoke test does not claim to export a GMT.
bpy.types.Object.rFactor = bpy.props.StringProperty()
bpy.types.Object.File_Name = bpy.props.StringProperty()
bpy.types.Mesh.Normals = bpy.props.EnumProperty(items=[("0", "Smooth", "")])
bpy.ops.mesh.primitive_cube_add()
template = bpy.context.object
material = bpy.data.materials.new("smoke")
empty = bpy.data.objects.new("template", None)
bpy.context.collection.objects.link(empty)
geom = ([(0., 0., 0.), (1., 0., 0.), (0., 1., 0.)],
        [(0., 0.), (1., 0.), (0., 1.)], [(0, 1, 2)], [(0., 0., 1.)] * 3)
_, ob = blender_stage.build_mesh(geom, Matrix.Identity(4), "smoke", material,
                                empty, template, bpy.context.collection,
                                uv_b=(2., 3.), uv_d=(4., 5.))
ob.data.update()
assert len(ob.data.vertices) == 3
assert len(ob.data.uv_layers) == 4
assert ob.data.has_custom_normals
assert all(abs(n.vector.z - 1.) < 1e-5 for n in ob.data.corner_normals)
assert tuple(ob.data.uv_layers["UV_B"].data[0].uv) == (0., 3.)
assert ob.LOD_Out > 13000 if hasattr(ob, "LOD_Out") else ob["LOD_Out"] > 13000
print("AC2RF2 BLENDER SMOKE " + json.dumps({"blender": bpy.app.version_string,
                                          "vertices": len(ob.data.vertices),
                                          "custom_normals": True}))
