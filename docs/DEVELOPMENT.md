# Development

The project uses a standard `src` package layout:

```text
src/ac_to_rf2/       application modules and Blender entry point
tests/              generated fixtures and regression/smoke tests
tools/probes/       standalone Blender format diagnostics
tools/              Python distribution-validation automation
docs/               guides, measured notes, screenshots, and work items
pyproject.toml      dependencies, packaging, commands, and pytest settings
convert.bat         retained drag-and-drop launcher (CRLF)
launch_dev_mode.bat  one-click .venv / Developer Mode launcher (CRLF)
```

Use an activated `.venv` and reinstall after changing entry points or layout:

```bat
python -m pip install -e ".[dev]"
pytest -q
python -m build --outdir out\dist
python tools\check_distribution.py out\dist
```

The distribution check installs the wheel in a fresh temporary environment,
runs commands outside the checkout, checks writable workspace defaults, and
rebuilds a wheel from the source archive. CI runs this on Windows/Python 3.10
and 3.14. Real Blender tests are optional when Blender/exporter tools are absent.

## Commands and imports

Installed commands retain their names: `ac2rf2`, `ac2rf2-test`, `ac2rf2-check`,
`ac2rf2-tools`, and `ac2rf2-verify`. `python -m ac_to_rf2` is an alternative to
`ac2rf2`. Individual stages can be invoked as modules, for example:

```bat
python -m ac_to_rf2.convert_track "<AC track>" --textures
python -m ac_to_rf2.finalize_track out\ks_laguna_seca --install "<rF2>\ModDev\Locations"
python -m ac_to_rf2.steam_paths
```

Former `python build_track.py`, `python drive_track.py`, and similar root-file
invocations become `ac2rf2`, `ac2rf2-test`, or `python -m ac_to_rf2.<module>`.
Imports use `ac_to_rf2.<module>`; there are no root-level Python compatibility
modules that could shadow an installed package. The batch launcher activates
the local `.venv` when needed and invokes the package module.

Blender has its own Python. The build passes the installed package's
`blender_entry.py` to `--python`; that small entry point adds the package's import
root after Blender's bundled libraries before loading `ac_to_rf2.blender_stage`.
This keeps incompatible virtual-environment NumPy extensions out of Blender. It works from both editable and
wheel installs without copying project dependencies into Blender. Probes remain
standalone scripts under `tools/probes`; their exporter requirements are unchanged.

## Writable paths

In an editable checkout, defaults remain `<checkout>/out` and `<checkout>/.tools`,
even when a command is run from another directory. A wheel install defaults to
the caller's working directory, never `site-packages`. Set `AC2RF2_WORKSPACE` to
an explicit workspace when needed. `--out-root` and `AC2RF2_TOOLS_DIR` retain
their more specific overrides; `AC2RF2_BLENDER` can select a Blender executable.

Do not edit converter code while a build is running from it. Keep converted
content and generated packages under ignored `out/`. Read [NOTES.md](NOTES.md)
before changing rendering/material behavior, and add measurements there.
