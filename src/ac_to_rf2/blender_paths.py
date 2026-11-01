"""Paths shared by the portable tooling setup and conversion commands."""
import os
from pathlib import Path


from ac_to_rf2.project_paths import WORKSPACE_DIR

BLENDER_VERSION = "5.0.1"
TOOLS_DIR = Path(os.environ.get("AC2RF2_TOOLS_DIR", WORKSPACE_DIR / ".tools"))
PORTABLE_BLENDER = TOOLS_DIR / ("blender-%s-windows-x64" % BLENDER_VERSION) / "blender.exe"
ADDONS_DIR = TOOLS_DIR / "addons"


def default_blender():
    if os.environ.get("AC2RF2_BLENDER"):
        return os.environ["AC2RF2_BLENDER"]
    candidates = [PORTABLE_BLENDER,
                  Path(r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"),
                  Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")]
    return str(next((p for p in candidates if p.is_file()), PORTABLE_BLENDER))
