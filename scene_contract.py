"""Stable source identities and checked geometry-stage contracts (no Blender)."""
import hashlib
import json
import os
import re
from collections import Counter


SCHEMA_VERSION = 2


def model_meshes(model, model_index):
    """Names can repeat even within one KN5; traversal ordinals cannot."""
    for ordinal, node in enumerate(model.walk()):
        if node.type in (2, 3):
            yield "%d:%d" % (model_index, ordinal), node


def mesh_key(row):
    return row.get("mesh_id", row.get("mesh"))


def index_meshes(rows):
    result = {}
    for row in rows:
        key = mesh_key(row)
        if not key or key in result:
            raise ValueError("ambiguous mesh identity %r; rebuild geometry" % key)
        result[key] = row
    return result


def material_signature(material):
    """Include the original name: punctuation is significant before sanitizing."""
    facts = [material.name, material.shader, material.blend,
             material.alpha_tested, material.depth_mode,
             material.props, material.textures]
    return hashlib.sha256(json.dumps(facts, sort_keys=True,
                                    allow_nan=False).encode()).hexdigest()


class MaterialNames:
    def __init__(self):
        self.definitions = {}
        self.names = {}

    def get(self, material, prefix=None):
        signature = material_signature(material)
        key = (signature, prefix)
        if key not in self.definitions:
            stem = re.sub(r"[^A-Za-z0-9_]", "_", material.name) or "material"
            # Leave space for the prefix and the fixed-size GMT name field.
            stem = stem[:20]
            name = "%s_%s" % (stem, signature[:12])
            if prefix:
                name = prefix + name
            previous = self.names.setdefault(name.lower(), key)
            if previous != key:
                raise ValueError("material identifier collision: " + name)
            self.definitions[key] = name
        return self.definitions[key]


def surface_prefix(key):
    """A prefix that matches neither another surface nor generic template road."""
    digest = hashlib.sha256(str(key).encode()).hexdigest()[:12]
    return "ac%s_" % digest


def validate_exports(mapping, exported, gmt_dir):
    """Reject missing, duplicate, empty, or stale geometry before staging it."""
    rows = index_meshes(mapping["meshes"])
    counts = Counter()
    parts = {}
    names = set()
    for record in exported:
        filename = record["gmt"]
        if os.path.basename(filename) != filename or not filename.lower().endswith(".gmt"):
            raise ValueError("invalid GMT filename: " + filename)
        if filename.lower() in names:
            raise ValueError("duplicate GMT export: " + filename)
        names.add(filename.lower())
        path = os.path.join(gmt_dir, filename)
        if not os.path.isfile(path) or os.path.getsize(path) < 264:
            raise ValueError("missing or truncated GMT: " + filename)
        if record.get("timing"):
            continue
        key = mesh_key(record)
        if key not in rows or (record.get("material") != rows[key]["rf2_material"]
                               or record.get("mesh") != rows[key]["mesh"]):
            raise ValueError("stale geometry mapping for %r; rebuild geometry" % key)
        counts[key] += 1
        part, total = record.get("part"), record.get("parts")
        if not isinstance(part, int) or not isinstance(total, int) or not 0 <= part < total:
            raise ValueError("missing geometry chunk manifest; rebuild geometry")
        seen, expected = parts.setdefault(key, (set(), total))
        if total != expected or part in seen:
            raise ValueError("duplicate or inconsistent chunks for " + key)
        seen.add(part)
    for key, row in rows.items():
        required = row.get("tris", 0) > 0 and (row.get("render", True) or row.get("physical"))
        if required and not counts[key]:
            raise ValueError("missing export for %s (%s)" % (row["mesh"], key))
        if key in parts:
            seen, total = parts[key]
            if len(seen) != total:
                raise ValueError("incomplete geometry chunks for " + key)
