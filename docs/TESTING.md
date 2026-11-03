# Convert, install, and drive

Use `run.bat` from Command Prompt; no environment activation is needed.
It creates `.venv`, installs dependencies on first use and after metadata changes,
and always activates this checkout's environment, even if another one is active.
Run `run.bat setup` to download portable Blender/exporter and check both games.

## One-click Developer Mode

Double-click `run.bat` in the repository root. It activates the
project's `.venv` and runs the launch-only workflow with automatic diagnostics. No conversion or
installation is performed. Startup failures stay visible in the console.

Optional CLI arguments are forwarded, for example:

```bat
run.bat --restart-game
run.bat --dry-run
```

## Normal iteration

```bat
run.bat drive ks_laguna_seca --restart-game --jobs 4
```

This preflights the targets, closes this installation's game/launcher when
requested, converts the track, verifies the staged location, installs it into
`ModDev\Locations`, then launches `Bin64\rFactor2 Mod Mode.exe` with the game
root as its working directory. It checks that the actual Mod Mode process stays
running for at least two seconds. A regular-game process or a launch timeout is
an error. Process confirmation does not prove that the selected track/vehicle loads or renders correctly.

The implementation is `src/ac_to_rf2/drive_track.py`. The lower-level equivalent module
command is `python -m ac_to_rf2.drive_track ...`; installed commands are unchanged.

Select `ks_laguna_seca` in the game's track list. First-time Developer Mode
graphics/controller setup belongs to its separate profile. Steam should be
running and logged in. The command does not change your track selection or
controller settings and does not automatically enter a driving session.

## Several tracks or layouts

Run `run.bat convert --list-tracks` to print every usable track/layout identifier.
Track names are resolved under the detected Assetto Corsa `content\tracks`
folder. Full or relative source-folder paths also work; quote paths with spaces.
Use `::` for a layout belonging to a particular track:

```bat
run.bat drive ks_laguna_seca spa ks_silverstone::gp --restart-game
run.bat drive "D:\AC mods\my track" --layout short --restart-game
run.bat drive ks_silverstone --all-layouts --restart-game
run.bat convert --all-tracks
run.bat convert --all-tracks --dry-run
```

`--all-tracks` finds source folders containing KN5 models under the selected
AC installation's `content/tracks` and selects each default and declared layout.
Use `--ac <folder>` to select another installation. It cannot be combined with
individual track arguments or `--layout`. Preview the complete list with
`run.bat convert --all-tracks --dry-run`. Like explicit batches, it stops on the
first error and retains earlier successful installs.

Targets run sequentially; each conversion can use several Blender workers.
Developer Mode launches once after every target succeeds. Identical targets are
deduplicated; different sources with the same output name are rejected. A failed
target stops the batch and prevents launch; earlier successful installs remain.

## Reuse work or run individual steps

```bat
run.bat drive ks_laguna_seca --skip-geometry --restart-game
run.bat drive ks_laguna_seca --install-only --restart-game
run.bat drive ks_laguna_seca --no-launch
run.bat game --restart-game
run.bat drive ks_silverstone::gp --dry-run
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
| `--trace 5` | Game trace level, 0–5; logs under `ModDev\UserData\Log` |
| `--wait-for-exit` | Accepted for compatibility; diagnostics already wait until game exit |
| `--rf2 <folder>` / `--ac <folder>` | Override Steam game discovery |
| `--out-root <folder>` | Parent directory for build artifacts |
| `--hour HH:MM` | Session time (default noon), also applied by install-only |
| `--jobs`, `--bake-size`, `--blender`, etc. | Shared conversion options; see `--help` |

Without `--restart-game`, an existing game or launcher stops the workflow before
conversion or installation. No processes are force-killed implicitly. The script
locks this game's test workflow to prevent competing scripts from installing or
launching simultaneously, and rechecks that the game is stopped before install.
`--dry-run` prints commands without changing track files or game processes.
The batch launcher still prepares Python dependencies if setup is needed.

No PowerShell scripts are used. Converted assets stay in ignored output folders.
For visual checks, follow [VALIDATION.md](VALIDATION.md). Launch working-directory
requirements are documented by [Studio 397](https://docs.studio-397.com/display/DG/Developer%2BMode).

## Loading warnings and crashes

The launcher confirms a running Developer Mode process, not a completed driving
session. If a warning appears, preserve the latest `ModDev\UserData\Log\trace_*.txt`.
Start with zero AI opponents. Compare the same vehicle on bundled Joesville and
the converted track to separate vehicle/SDK warnings from track defects.

The converter rejects AIW files with missing pit types, disconnected locations,
invalid waypoint links or nonterminating native branch walks before installation.
It also rejects terrain files missing the native global effects in `[LOOSE]`. Existing builds made before this
check need AIW regeneration; `--install-only` reuses their AIW and will reject an
invalid old one. A full conversion regenerates it automatically.

The 2026-11-01 Skip Barber warnings reference four samples absent from the mounted
bundled vehicle archive. This is separate from converted track content. If those
warnings persist on Joesville, use Steam's installed-file verification and check
for an SDK update. See measured evidence and remaining manual checks in NOTES.md.


A reversible loose-sample workaround for the measured Skip Barber mismatch is
available: see [SDK audio diagnosis and aliases](AUDIO.md). It uses existing
game recordings and leaves SDK configuration/archive files unchanged. It is
separate from track conversion, is never applied automatically by the launcher,
and does not establish that a native crash is resolved.


## Automatic loading-hang diagnostics

Run `.\run.bat` from the repository root, or double-click it.
It activates the project's `.venv`, starts Developer Mode with trace level 5,
and monitors that process automatically. No second command or environment
activation is needed. Leave the launcher console open while testing.

When Windows reports a game window unresponsive continuously for 10 seconds,
the monitor captures two native snapshots, thread CPU times, raw logs and
track inputs under ignored `out/diagnostics/<timestamp>`. It prints that path.
A transient stall that recovers does not trigger dumps. Monitoring continues
after every capture until the game exits or is killed. Sustained hangs can
produce another pair every 30 seconds in separate hang folders. A one-second
timeline records CPU, memory and Windows responsiveness. On process exit,
final logs and track inputs are preserved in the exit folder.

The monitor does not terminate/restart the game, modify settings, or claim that
an unresponsive window identifies the cause. Capture errors are printed in the
launcher console. Keep diagnostic dumps local for analysis. An explicit
`--dry-run` only prints the launch command; it starts no game or monitor.

## Conversion without launching

```bat
run.bat convert ks_laguna_seca --jobs 4
run.bat convert ks_silverstone::gp spa
run.bat verify "<rF2>\ModDev\Locations\ks_laguna_seca" out\ks_laguna_seca
run.bat test -q
```

`convert` uses the same conversion, verification and install workflow as `drive`,
with launch disabled. Missing portable Blender/exporter tools are installed before
full conversions. `--dry-run`, `--install-only` and `--skip-geometry` do not download
them. `drive` uses the same automatic diagnostics as `game` after launching.
When dragging one track onto `convert.bat`, available layouts are prompted for
in an interactive console. All batch files activate the same local environment.
Relative paths are resolved from the caller's directory, including when the batch
file is invoked by its full path from another folder. Dependency installation
requires internet on first use; subsequent launches reuse the environment.
