# AC to rF2

Convert Assetto Corsa tracks for personal use in rFactor 2 Developer Mode.
Requires Windows 10/11, Steam installations of both games, and
[Python 3.10+](https://www.python.org/downloads/windows/) with **Add Python to PATH** enabled.

Open Command Prompt in this folder. `run.bat` handles environment setup automatically.
Run setup, list tracks, then choose an individual or all-track conversion:

```bat
run.bat setup
run.bat convert --list-tracks
run.bat convert ks_laguna_seca
run.bat convert --all-tracks
run.bat
```

Copy track identifiers from `--list-tracks`; quoted folder paths also work.
Setup downloads Blender/exporter. Conversions take roughly 5-15 minutes per track.
Double-click `run.bat` to play; keep its console open for automatic diagnostics.

| Command | Action |
|---|---|
| `setup` | Install tools; check requirements. |
| `check` | Check requirements. |
| `convert TRACK ...` | Convert, verify and install. |
| `drive TRACK ...` | Convert, install and play. |
| `game` (or no arguments) | Launch Developer Mode with diagnostics. |
| `verify "INSTALL" "BUILD"` | Verify a converted installation. |
| `diagnose` | Save existing game logs. |
| `test` | Run regression tests. |

Use `run.bat COMMAND --help` for details.

| Argument | Action |
|---|---|
| `--list-tracks` | List exact track/layout identifiers. |
| `--all-tracks` | Convert every installed track/layout. |
| `--layout NAME` / `TRACK::NAME` | Select a layout, e.g. `ks_silverstone::gp`. |
| `--all-layouts` | Convert all layouts of specified tracks. |
| `--hour HH:MM` | Session time; default noon. |
| `--jobs N` | Parallel workers; `1` minimizes memory. |
| `--skip-geometry` | Reuse previous geometry. |
| `--install-only` | Reinstall completed builds. |
| `--no-launch` | Leave game stopped after `drive`. |
| `--restart-game` | Close existing game before proceeding. |
| `--force-close` | Force shutdown if restart times out. |
| `--dry-run` | Preview without converting or launching. |
| `--ac DIR` / `--rf2 DIR` | Override game folders. |
| `--out-root DIR` | Build storage; default `out`. |
| `--blender FILE` | Override Blender executable. |
| `--close-timeout N` / `--launch-timeout N` | Shutdown/startup timeouts in seconds. |
| `--trace 0..5` | Game logging; default `5`. |
| `--launch-only` / `--wait-for-exit` | Compatibility options for launching/waiting. |
| `--bake-size N`, `--grain N`, `--detail-metres N`, `--gain N` | Texture baking controls. |
| `--diffuse N`, `--ambient N`, `--scene-ambient N` | Material/scene lighting controls. |
| `diagnose --capture [--pid N]` | Capture running game; optionally select PID. |
| `diagnose --out DIR` | Diagnostic storage. |
| `--help` | Show command help. |

A failed track stops the batch. Builds stay in ignored `out/`; installs go into
rF2's `ModDev/Locations`. `convert.bat` supports dragging a track folder onto it.
Do not redistribute converted content without its owners' permission.

[Usage](docs/USAGE.md) | [Testing](docs/TESTING.md) | [Development](docs/DEVELOPMENT.md) |
[Findings](docs/NOTES.md) | [Work items](docs/WORK_ITEMS.md)
