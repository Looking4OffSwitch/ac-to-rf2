"""Load a current rF2 exporter in Blender; never accept an incompatible import."""
import sys
from ac_to_rf2.blender_paths import ADDONS_DIR


MIN_BLENDER = (5, 0, 0)
EXPORTER_MODULES = ("io_rfactor2_gmt", "io_rf2_gmt_release")


def enable_exporter():
    import bpy
    import addon_utils

    if bpy.app.version < MIN_BLENDER:
        raise RuntimeError("Blender 5.0 or newer is required")
    if ADDONS_DIR.is_dir() and str(ADDONS_DIR) not in sys.path:
        sys.path.insert(0, str(ADDONS_DIR))
    for name in EXPORTER_MODULES:
        module = addon_utils.enable(name, default_set=False, persistent=True)
        if module is not None:
            return name, module
    raise RuntimeError(
        "No compatible rF2 GMT exporter could be loaded in Blender %s (Python %d.%d). "
        "Install exporter source or a build compiled for this Python version. "
        "The community add-on's Blender 5.0 archive contains Python 3.11 bytecode and cannot "
        "load in Blender 5.2's Python 3.13. Run ac2rf2-tools for the tested portable 5.0 pair."
        % (bpy.app.version_string, *sys.version_info[:2]))
