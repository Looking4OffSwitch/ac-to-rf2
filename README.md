# AC to rF2

Convert Assetto Corsa tracks into rFactor 2 Developer Mode locations: geometry,
materials, textures, surfaces, AI lines, cameras, lighting, and shadows.
Custom Shaders Patch settings are read where supported.

## Requirements

- Windows 10/11, Python 3.10+, and both games installed through Steam.
- 16 GB RAM recommended.
- Portable Blender 5.0.1 with the matching community GMT exporter, installed by
  `ac2rf2-tools`. Your system Blender can remain installed separately.

## Setup

In Command Prompt at the repository root:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -e ".[dev]"
ac2rf2-tools
ac2rf2-check
```

Activate `.venv` in each new terminal. Dependencies and project commands are
installed by pip; Python source code lives in `src/ac_to_rf2`.

## Convert and test

```bat
ac2rf2-test ks_laguna_seca --jobs 4 --no-launch
```

This converts, verifies, and installs the track for manual testing in Developer
Mode. Omit `--no-launch` to start Developer Mode automatically. Use
`--restart-game` to close an existing session before updating.

```bat
ac2rf2-test ks_laguna_seca spa ks_silverstone::gp --no-launch
ac2rf2-test ks_laguna_seca --install-only --no-launch
ac2rf2-test --launch-only
```

Builds stay in ignored `out/`; installs go into rFactor 2's `ModDev/Locations`.
The root `convert.bat` remains available for drag-and-drop conversion.

## Documentation

- [Workflow options and batch/layout examples](docs/TESTING.md)
- [Complete usage, requirements, packaging, and limitations](docs/USAGE.md)
- [Visual and file validation](docs/VALIDATION.md)
- [Source format compatibility](docs/FORMATS.md)
- [Development, package layout, and tests](docs/DEVELOPMENT.md)
- [Measured findings](docs/NOTES.md) and [work items](docs/WORK_ITEMS.md)

## Limitations and content rights

The near-car road band still needs in-game validation; CSP GrassFX and some
material behavior are approximated. Normal rFactor 2 requires a separate
packaging step. See the full usage guide for details and protected-track guidance.

Converted tracks contain the source models and textures. Do not redistribute
converted content unless you have the required rights.
