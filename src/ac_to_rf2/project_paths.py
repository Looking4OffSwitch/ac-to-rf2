"""Separate installed package files from writable build/tool directories."""
import os
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
IMPORT_ROOT = PACKAGE_DIR.parent


def workspace_dir():
    override = os.environ.get("AC2RF2_WORKSPACE")
    if override:
        return Path(override).expanduser().resolve()
    # Editable checkout: keep the existing project out/ and .tools/ locations.
    candidate = PACKAGE_DIR.parent.parent
    if ((candidate / "pyproject.toml").is_file()
            and (candidate / "src" / "ac_to_rf2").resolve() == PACKAGE_DIR):
        return candidate
    # Wheel installs must never write into site-packages.
    return Path.cwd().resolve()


WORKSPACE_DIR = workspace_dir()
