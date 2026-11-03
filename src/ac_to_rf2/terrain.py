"""Clone native terrain behavior without merging AC's distinct surfaces."""
import re
from pathlib import Path


def surface_tdf(template, rows, surfaces):
    text = Path(template).read_text(encoding="utf-8", errors="replace")
    # Split every section: LOOSE is independent of the final material block.
    chunks = re.split(r"(?m)^(?=\[[^]\r\n]+\])", text)
    native = {}
    for chunk in chunks[1:]:
        if not chunk.startswith("[FEEDBACK]"):
            continue
        match = re.search(r"(?m)^Materials=(.+)$", chunk)
        if match:
            for name in match.group(1).split(","):
                native.setdefault(name.strip().lower(), chunk)
    first_feedback = next((i for i, chunk in enumerate(chunks)
                           if chunk.startswith("[FEEDBACK]")), len(chunks))
    out, applied, seen = chunks[:first_feedback], {}, {}
    for row in rows:
        prefix, key = row["surface_prefix"], row["surface"]
        if prefix in seen:
            if seen[prefix] != key:
                raise ValueError("surface identifier collision")
            continue
        seen[prefix] = key
        info = surfaces.get(key, {"friction": 1.0, "valid": False})
        kind = row["surface_kind"]
        block = native.get(kind)
        if block is None:
            raise ValueError("terrain template has no behavior for " + kind)
        if info["valid"] and not re.search(r"\bDry=", block):
            block = native["road"]
        dry = info["friction"]
        block = re.sub(r"\bDry=\S+", "Dry=%.3f" % dry, block)
        if re.search(r"\bDry=", block):
            if re.search(r"\bWet=", block):
                block = re.sub(r"\bWet=\S+", "Wet=%.3f" % (dry * 0.85), block)
            else:
                block = re.sub(r"\bDry=\S+", "Dry=%.3f Wet=%.3f" %
                               (dry, dry * 0.85), block)
        block = re.sub(r"\bLegal=\w+", "Legal=" + str(info["valid"]).lower(), block)
        block = re.sub(r"(?m)^Materials=.+$", "Materials=" + prefix, block)
        out.append("\n// AC surface %s\n%s" % (key, block))
        applied[prefix] = dry
    # Native global effects are required even when no surface uses them.
    out.extend(chunk for chunk in chunks[first_feedback:] if not chunk.startswith("[FEEDBACK]"))
    return "".join(out), applied


def validate_terrain(text):
    """Reject the missing native global effects that crash session startup."""
    match = re.search(r"(?ims)^\[LOOSE\]\s*\n(.*?)(?=^\[|\Z)", text)
    if not match:
        return ["TDF: missing [LOOSE] global effects"]
    reactions = set(re.findall(r"(?im)^\s*Reaction=(\w+)", match[1]))
    missing = {"spark", "whitesmoke", "blacksmoke", "flames", "groove", "wallskid"} - reactions
    return ["TDF: missing global effects: " + ", ".join(sorted(missing))] if missing else []
