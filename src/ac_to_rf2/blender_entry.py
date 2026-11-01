"""Blender --python entry point; its bundled Python does not see our venv."""
from pathlib import Path
import sys


# A wheel's import root is site-packages. Keep Blender's own NumPy first:
# the venv's NumPy extensions may target a completely different Python ABI.
sys.path.append(str(Path(__file__).resolve().parent.parent))

import ac_to_rf2  # noqa: E402

if Path(ac_to_rf2.__file__).resolve().parent != Path(__file__).resolve().parent:
    raise RuntimeError("Another ac_to_rf2 package shadows this Blender entry point")

from ac_to_rf2.blender_stage import main  # noqa: E402


if __name__ == "__main__":
    main()
