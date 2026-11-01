# Convert, install, and drive

Activate the standard virtual environment in Command Prompt, then install the
project commands (repeat pip installation after pulling command/dependency changes):

```bat
cd /d D:\dev\ac-to-rf2
.venv\Scripts\activate.bat
python -m pip install -e ".[dev]"
```

## Normal iteration

```bat
ac2rf2-test ks_laguna_seca --restart-game --jobs 4
```

This preflights the targets, closes this installation's game/launcher when
requested, converts the track, verifies the staged location, installs it into
`ModDev\Locations`, then launches `Bin64\rFactor2 Mod Mode.exe` with the game
root as its working directory. It checks that the actual Mod Mode process stays
running for at least two seconds. A regular-game process or a launch timeout is
an error. Process confirmation does not prove that the track renders correctly.

The Python script is `drive_track.py`; `python drive_track.py ...` accepts the
same arguments as the installed `ac2rf2-test` command.

Select `ks_laguna_seca` in the game's track list. First-time Developer Mode
graphics/controller setup belongs to its separate profile. Steam should be
running and logged in. The command does not change your track selection or
controller settings and does not automatically enter a driving session.

## Several tracks or layouts

Track names are resolved under the detected Assetto Corsa `content\tracks`
folder. Full or relative source-folder paths also work; quote paths with spaces.
Use `::` for a layout belonging to a particular track:

```bat
ac2rf2-test ks_laguna_seca spa ks_silverstone::gp --restart-game
ac2rf2-test "D:\AC mods\my track" --layout short --restart-game
ac2rf2-test ks_silverstone --all-layouts --restart-game
```

Targets run sequentially; each conversion can use several Blender workers.
Developer Mode launches once after every target succeeds. Identical targets are
deduplicated; different sources with the same output name are rejected. A failed
target stops the batch and prevents launch; earlier successful installs remain.

## Reuse work or run individual steps

```bat
ac2rf2-test ks_laguna_seca --skip-geometry --restart-game
ac2rf2-test ks_laguna_seca --install-only --restart-game
ac2rf2-test ks_laguna_seca --no-launch
ac2rf2-test --launch-only --restart-game
ac2rf2-test ks_silverstone::gp --dry-run
```

`--skip-geometry` reruns the pipeline except Blender and retains its existing
stale/incomplete-export checks. Use a full build after geometry/exporter changes.
`--install-only` needs a completed build, not the source game or Blender; it
regenerates the scene/database and verifies before replacing the location.
Use `--out-root <directory>` to select the parent containing existing builds or
choose where new builds are written. The default is this project's `out`.
The output directory must be outside both game installations. Within this
checkout, keep generated builds under ignored `out/`.

| Option | Purpose |
|---|---|
| `--restart-game` | Request normal GUI shutdown before updating files |
| `--force-close` | With restart, kill only this game's detected processes if graceful close times out; unsaved session changes can be lost |
| `--close-timeout 30` | Time allowed for normal shutdown, in seconds |
| `--launch-timeout 90` | Time allowed to confirm the actual Mod Mode process |
| `--trace 2` | Game trace level, 0–5; logs under `ModDev\UserData\Log` |
| `--wait-for-exit` | Keep the command running until the launched game exits |
| `--rf2 <folder>` / `--ac <folder>` | Override Steam game discovery |
| `--out-root <folder>` | Parent directory for build artifacts |
| `--hour HH:MM` | Session time (default noon), also applied by install-only |
| `--jobs`, `--bake-size`, `--blender`, etc. | Shared conversion options; see `--help` |

Without `--restart-game`, an existing game or launcher stops the workflow before
conversion or installation. No processes are force-killed implicitly. The script
locks this game's test workflow to prevent competing scripts from installing or
launching simultaneously, and rechecks that the game is stopped before install.
`--dry-run` prints commands without changing files or game processes.

No PowerShell scripts are used. Converted assets stay in ignored output folders.
For visual checks, follow [VALIDATION.md](VALIDATION.md). Launch working-directory
requirements are documented by [Studio 397](https://docs.studio-397.com/display/DG/Developer%2BMode).
