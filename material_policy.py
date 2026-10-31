"""Rendering decisions shared by the bake, exporter, and regression tests."""


def coefficient(props, name, default):
    value = props.get(name)
    return default if value is None else float(value)


def opacity_mode(row, data):
    name = row["rf2_material"]
    if name in data.get("alpha_ref", {}):
        return "cutout"
    if name in data.get("gradients", []):
        return "blend"
    if row.get("needs_blend") and not row.get("alpha_test"):
        return "blend"
    return "opaque"


def _blend_identifier(material, property_name, labels):
    try:
        items = material.bl_rna.properties[property_name].enum_items
    except (AttributeError, KeyError) as exc:
        raise RuntimeError("rF2 exporter lacks enum metadata for " + property_name) from exc
    for item in items:
        label = "".join(c for c in item.name.lower() if c.isalnum())
        if label in labels:
            return item.identifier
    raise RuntimeError("rF2 exporter lacks blend option for " + property_name)


def set_blending(material, mode):
    """Use RNA labels: vendor enums are D3D's 1-based values, not 0-based."""
    if not hasattr(material, "Blend"):
        raise RuntimeError("rF2 exporter lacks material property Blend")
    material.Blend = mode == "blend"
    choices = (({"srcalpha", "sourcealpha"}, {"invsrcalpha", "inversesourcealpha"})
               if mode == "blend" else ({"one"}, {"zero"}))
    for name, labels in zip(("Blend_Source_List", "Blend_Destination_List"), choices):
        value = _blend_identifier(material, name, labels)
        setattr(material, name, value)
        if str(getattr(material, name)) != value:
            raise RuntimeError("rF2 exporter rejected material property " + name)
