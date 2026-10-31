"""Standalone reader for Assetto Corsa .kn5 files.

Format (version 5-6):
  "sc6969", u32 version, [u32 extra if version > 5]
  u32 texture_count, then per texture: u32 type, str name, u32 size, bytes
  u32 material_count, then per material: see read_material
  node tree, depth first
"""
import struct, sys, os, math

import numpy as np

from source_formats import Reader

SUPPORTED_VERSIONS = (5, 6)
MAX_NODE_DEPTH = 256


def _header(r):
    if r.take(6) != b'sc6969':
        r.fail("not a KN5 file (expected sc6969)", 0)
    version = r.u32()
    r.format_name = "KN5 v%d" % version
    if version not in SUPPORTED_VERSIONS:
        r.fail("unsupported version; supported: 5, 6", 6)
    return version, r.u32() if version == 6 else 0


def _texture_table(r):
    r.context = "textures"
    entries = []
    names = set()
    for _ in range(r.count(12)):
        texture_type = r.u32()
        if texture_type not in (0, 1):
            r.fail("unsupported texture active flag %d" % texture_type, r.p - 4)
        name = r.string()
        if not name or name.casefold() in names:
            r.fail("empty or duplicate texture name %r" % name)
        names.add(name.casefold())
        size = r.u32()
        offset = r.p
        r.skip(size)
        entries.append((name, texture_type, offset, size))
    return entries


def iter_textures(path):
    """Read the checked texture prefix using exactly the model reader's layout."""
    with open(path, 'rb') as stream:
        r = Reader(stream.read(), path, "KN5")
    _header(r)
    entries = _texture_table(r)
    for name, texture_type, offset, size in entries:
        yield name, texture_type, r.d[offset:offset + size]


class Material:
    __slots__ = ('name', 'shader', 'blend', 'alpha_tested', 'depth_mode', 'props', 'textures')

class Node:
    __slots__ = ('type', 'name', 'active', 'matrix', 'children', 'parent',
                 'material_id', 'vertex_count', 'index_count', 'layer',
                 'lod_in', 'lod_out', 'center', 'radius', 'cast_shadows',
                 'visible', 'transparent', 'renderable',
                 '_verts', '_uvs', '_normals', '_indices', 'raw')
    def __init__(self):
        self.children = []
        self.parent = None
        self.matrix = None
        self.material_id = None
        self.vertex_count = 0
        self.index_count = 0
        self.raw = None
        self.verts = None
        self.uvs = None
        self.normals = None
        self.indices = None


# Geometry is decoded from the file the first time it is asked for, not on
# load. As Python tuples it takes about 12 times its size on disk, and the
# split geometry stage has every Blender load every model but export only its
# own share: decoding it all put each of six Blenders at 3.8 GB on Laguna.
# The values are unpacked from the same bytes in the same way either way.
def _lazy(slot, unpack):
    def get(self):
        v = getattr(self, slot)
        if v is None and self.raw is not None:
            v = unpack(*self.raw)
            setattr(self, slot, v)
            if all(getattr(self, s) is not None for s in _GEOMETRY_SLOTS):
                self.raw = None         # all decoded: let go of the file
        return v

    def put(self, v):
        setattr(self, slot, v)
    return property(get, put)


def _vecs(fmt, at):
    def unpack(d, vp, count, stride, ip, icount):
        return [struct.unpack_from(fmt, d, vp + i * stride + at) for i in range(count)]
    return unpack


_GEOMETRY_SLOTS = ('_verts', '_uvs', '_normals', '_indices')
# position 3f, normal 3f, uv 2f, tangent 3f
Node.verts = _lazy('_verts', _vecs('<3f', 0))
Node.normals = _lazy('_normals', _vecs('<3f', 12))
Node.uvs = _lazy('_uvs', _vecs('<2f', 24))
Node.indices = _lazy('_indices', lambda d, vp, count, stride, ip, icount:
                     struct.unpack_from('<%dH' % icount, d, ip))


def placement_matrix(position, rotation):
    """models.ini POSITION/ROTATION as a kn5 row-vector matrix.

    ROTATION's first number is a turn about the vertical axis, in degrees.
    Measured on Highlands' drift layout, the one stock model placed this way:
    its start light gantry (100.kn5, ROTATION=-17) hangs 3.8 m over a flat
    road heading 20.3 degrees off the model's own axis. Read as this turn the
    lights end up 3.3 degrees off the road; with the opposite sign, 37. The
    other two numbers have no stock example to measure, so they are refused
    rather than guessed (see convert_track.layout_files).
    """
    yaw = math.radians(rotation[0])
    c, s = math.cos(yaw), math.sin(yaw)
    return [c, 0.0, s, 0.0,
            0.0, 1.0, 0.0, 0.0,
            -s, 0.0, c, 0.0,
            position[0], position[1], position[2], 1.0]


# Some ripped tracks (ek_nagao) store every UV as 0.5 + d with the sign of d
# scrambled per vertex, and flip vertex normals at random. AC with CSP draws
# them correctly; read as they stand, every face samples across half the
# atlas and the road turns to streaks. Measured on ek_nagao, the true value
# is 0.5 - |d|: rendered from the kn5 alone it gives clean asphalt with its
# edge lines and clean grass, where the stored values give a patchwork.
#
# Detected per file, never per mesh: folding about 0.5 shrinks a face's UV
# span 37x on the median ek_nagao mesh and 1.00x on Silverstone, Laguna,
# Highlands and Wuhu Town -- though 169 single Silverstone meshes pass a
# per-mesh test of 3x.
FOLD_RATIO = 8.0


def _uv_span_ratio(n):
    import statistics
    U, I = n.uvs, n.indices
    raw, fold = [], []
    for i in range(0, len(I) - 2, 3):
        tri = (U[I[i]], U[I[i + 1]], U[I[i + 2]])
        raw.append(sum(max(t[k] for t in tri) - min(t[k] for t in tri) for k in (0, 1)))
        f = [tuple(0.5 - abs(c - 0.5) for c in t) for t in tri]
        fold.append(sum(max(t[k] for t in f) - min(t[k] for t in f) for k in (0, 1)))
    return statistics.median(raw) / max(statistics.median(fold), 1e-6)


def unfold_vertex_data(kn5):
    """Undo the scrambled UV and normal signs described above, if present."""
    import statistics
    # From the counts, which say the same as the lists without decoding them.
    meshes = [n for n in kn5.walk()
              if n.type in (2, 3) and n.vertex_count and n.index_count >= 30]
    if not meshes:
        return False
    sample = meshes[:: max(1, len(meshes) // 200)]
    if statistics.median(_uv_span_ratio(n) for n in sample) < FOLD_RATIO:
        return False
    for n in meshes:
        n.uvs = [(0.5 - abs(u - 0.5), 0.5 - abs(v - 0.5)) for u, v in n.uvs]
        if not n.normals:
            continue
        # A vertex normal facing away from the faces around it is a flipped
        # one: turn it round. Normals at right angles to them (grass cards
        # lit as the ground) are left as they are.
        acc = [[0.0, 0.0, 0.0] for _ in n.verts]
        V, I = n.verts, n.indices
        for i in range(0, len(I) - 2, 3):
            a, b, c = V[I[i]], V[I[i + 1]], V[I[i + 2]]
            e1 = [b[k] - a[k] for k in range(3)]
            e2 = [c[k] - a[k] for k in range(3)]
            fn = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2],
                  e1[0] * e2[1] - e1[1] * e2[0])
            for j in I[i:i + 3]:
                for k in range(3):
                    acc[j][k] += fn[k]
        out = []
        for nv, f in zip(n.normals, acc):
            fl = sum(x * x for x in f) ** 0.5
            dot = sum(nv[k] * f[k] for k in range(3)) / fl if fl > 0 else 0.0
            out.append(tuple(-x for x in nv) if dot < -0.2 else nv)
        n.normals = out
    return True


class KN5:
    def __init__(self, path, geometry=False, placement=None):
        self.geometry = geometry
        with open(path, 'rb') as f:
            data = f.read()
        self.size = len(data)
        r = Reader(data, path, "KN5")
        self.version, self.extra = _header(r)
        self.textures = [(name, kind, size) for name, kind, _at, size in _texture_table(r)]
        r.context = "materials"
        self.materials = [self.read_material(r) for _ in range(r.count(22))]
        self.root = self.read_node(r, None)
        self.consumed = r.p
        r.context = "end of node tree"
        r.finish()
        self.folded_uvs = geometry and unfold_vertex_data(self)
        if placement:
            # Where the track's models.ini puts this whole file. A parent
            # above the root, so every world transform walking up the parents
            # picks it up and walk() still starts at the file's own root.
            top = Node()
            top.type = 1
            top.name = "__placement__"
            top.matrix = placement_matrix(*placement)
            top.children = [self.root]
            self.root.parent = top

    def read_material(self, r):
        m = Material()
        m.name = r.string()
        r.context = "material %r" % m.name
        m.shader = r.string()
        m.blend = r.u8()
        m.alpha_tested = r.boolean()
        m.depth_mode = r.u32() if self.version > 4 else 0
        if m.blend not in (0, 1, 2) or m.depth_mode not in (0, 1, 2):
            r.fail("unsupported material blend/depth mode %d/%d" % (m.blend, m.depth_mode))
        if not m.shader:
            r.fail("empty material shader")
        m.props = {}
        for _ in range(r.count(44)):
            pname = r.string()
            if pname in m.props:
                r.fail("duplicate material property %r" % pname)
            value = r.f32()
            r.skip(36)  # unused vec2/vec3/vec4 slots; only bounds are relevant
            m.props[pname] = value
        m.textures = {}
        for _ in range(r.count(12)):
            sample = r.string()
            if sample in m.textures:
                r.fail("duplicate texture sampler %r" % sample)
            slot = r.u32()
            tex = r.string()
            m.textures[sample] = tex
        return m

    def read_node(self, r, parent, depth=0):
        r.context = "node at depth %d" % depth
        if depth > MAX_NODE_DEPTH:
            r.fail("node nesting exceeds supported depth %d" % MAX_NODE_DEPTH)
        n = Node()
        n.type = r.u32()
        n.name = r.string()
        r.context = "node %r" % n.name
        child_count = r.count(13)
        n.active = r.boolean()
        n.parent = parent
        if n.type == 1:
            n.matrix = r.vec(16)
        elif n.type in (2, 3):
            n.cast_shadows = r.boolean()
            n.visible = r.boolean()
            n.transparent = r.boolean()
            if n.type == 3:
                # Skinned flags precede the bone table.
                bones = r.count(68)
                for _ in range(bones):
                    r.string()
                    r.vec(16)
            # position 3f, normal 3f, uv 2f, tangent 3f (+ skin data)
            stride = 44 if n.type == 2 else 76
            n.vertex_count = r.count(stride)
            vp = r.p
            r.skip(n.vertex_count * stride)
            # Check the geometry even when lazy decoding/geometry=False is used.
            view = memoryview(r.d)
            values = np.ndarray((n.vertex_count, 8), dtype='<f4', buffer=r.d,
                                offset=vp, strides=(stride, 4))
            valid = np.isfinite(values).all(axis=1)
            if not valid.all():
                r.fail("non-finite position, normal or UV", vp + int(np.flatnonzero(~valid)[0]) * stride)
            n.index_count = r.count(2)
            if n.index_count % 3:
                r.fail("index count %d is not a triangle list" % n.index_count, r.p - 4)
            ip = r.p
            r.require(n.index_count * 2)
            indices = np.frombuffer(view, dtype='<u2', count=n.index_count, offset=ip)
            bad = indices >= n.vertex_count
            if bad.any():
                i = int(np.flatnonzero(bad)[0])
                r.fail("vertex index %d outside vertex count %d" % (indices[i], n.vertex_count), ip + i * 2)
            if self.geometry:
                # Where to decode from when asked (see _lazy).
                n.raw = (r.d, vp, n.vertex_count, stride, r.p, n.index_count)
            r.skip(n.index_count * 2)
            n.material_id = r.u32()
            if n.material_id >= len(self.materials):
                r.fail("material index %d outside material count %d" %
                       (n.material_id, len(self.materials)), r.p - 4)
            n.layer = r.u32()
            n.lod_in = r.f32()
            n.lod_out = r.f32()
            if n.type == 2:
                n.center = r.vec(3)
                n.radius = r.f32()
                n.renderable = r.boolean()
            else:
                n.center, n.radius, n.renderable = (0.0, 0.0, 0.0), 0.0, True
        else:
            r.fail('unknown node type %d' % n.type)
        for _ in range(child_count):
            n.children.append(self.read_node(r, n, depth + 1))
        return n

    def walk(self, node=None):
        node = self.root if node is None else node
        yield node
        for c in node.children:
            yield from self.walk(c)


if __name__ == '__main__':
    k = KN5(sys.argv[1])
    nodes = list(k.walk())
    meshes = [n for n in nodes if n.type in (2, 3)]
    print('version      %d' % k.version)
    print('bytes read   %d of %d  (%s)' % (
        k.consumed, k.size, 'exact' if k.consumed == k.size else 'MISMATCH'))
    print('textures     %d' % len(k.textures))
    print('materials    %d' % len(k.materials))
    print('nodes        %d  (%d meshes)' % (len(nodes), len(meshes)))
    print('triangles    %d' % (sum(n.index_count for n in meshes) // 3))
