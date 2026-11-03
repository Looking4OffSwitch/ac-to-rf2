"""Convert/install one or more tracks, then launch verified rF2 Developer Mode."""
import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import os
import math
from datetime import datetime
from pathlib import Path
import subprocess
import sys

import psutil

from ac_to_rf2.build_track import HERE, add_build_options
from ac_to_rf2.game_runtime import ensure_stopped, launch_developer


@dataclass(frozen=True)
class Target:
    source: Path
    layout: str | None = None

    @property
    def venue(self):
        return self.source.name + ("_" + self.layout if self.layout else "")


def parser():
    ap = argparse.ArgumentParser(prog="ac2rf2-test", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=(
        "Choosing tracks:\n"
        "  Use --list-tracks to print the exact installed track/layout identifiers.\n"
        "  A track name is its folder name inside Assetto Corsa's content/tracks,\n"
        "  not its display name in the game. Steam finds that folder automatically.\n"
        "  Append ::LAYOUT for a listed layout, or pass --layout LAYOUT.\n"
        "  A full track folder path also works; quote paths containing spaces.\n\n"
        "Examples:\n"
        "  %(prog)s --list-tracks\n"
        "  %(prog)s ks_laguna_seca\n"
        "  %(prog)s ks_silverstone::gp\n"
        '  %(prog)s "D:\\AC mods\\my_track"\n'
        "  %(prog)s --all-tracks\n"
        "  %(prog)s --all-tracks --dry-run"))
    ap.add_argument("tracks", nargs="*", metavar="TRACK[::LAYOUT]",
                    help="identifier printed by --list-tracks, or a quoted AC track folder path")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--list-tracks", action="store_true",
                      help="list exact installed track/layout identifiers without converting or launching")
    mode.add_argument("--install-only", action="store_true", help="reuse completed builds beneath --out-root")
    mode.add_argument("--launch-only", action="store_true", help="launch Developer Mode without converting/installing")
    ap.add_argument("--layout", help="layout for targets without an inline ::LAYOUT")
    ap.add_argument("--all-tracks", action="store_true",
                    help="convert every installed AC track and all its declared layouts")
    ap.add_argument("--all-layouts", action="store_true", help="convert every declared layout for each track")
    ap.add_argument("--no-launch", action="store_true", help="convert/install and leave the game stopped")
    ap.add_argument("--restart-game", action="store_true", help="request game/launcher shutdown before updating")
    ap.add_argument("--force-close", action="store_true", help="with --restart-game, kill game processes if normal close times out")
    ap.add_argument("--close-timeout", type=float, default=30, help="seconds allowed for normal game shutdown")
    ap.add_argument("--launch-timeout", type=float, default=90, help="seconds to confirm a sustained Mod Mode process")
    ap.add_argument("--trace", type=int, choices=range(6), default=2, help="Developer Mode trace level (0-5)")
    ap.add_argument("--wait-for-exit", action="store_true", help="keep this command open until the game exits")
    ap.add_argument("--dry-run", action="store_true", help="print the plan without converting, installing or touching game processes")
    add_build_options(ap)
    return ap


def targets_for(args, ac):
    targets = {}
    specs = args.tracks
    if args.all_tracks or args.list_tracks:
        directory = ac / "content" / "tracks"
        specs = [str(folder) for folder in sorted(directory.iterdir(), key=lambda p: p.name.casefold())
                 if folder.is_dir() and any(folder.glob("*.kn5"))]
        if not specs:
            raise ValueError("No AC tracks with .kn5 models found in " + str(directory))
    for spec in specs:
        parts = spec.split("::")
        if len(parts) > 2 or not parts[0] or (len(parts) == 2 and not parts[1]):
            raise ValueError("Invalid target: " + spec)
        raw = Path(parts[0]).expanduser()
        source = (raw if raw.is_dir() or raw.is_absolute() or len(raw.parts) > 1
                  else ac / "content" / "tracks" / raw).resolve()
        inline = parts[1] if len(parts) == 2 else None
        if args.all_layouts or args.all_tracks or args.list_tracks:
            if inline or args.layout:
                raise ValueError("--all-layouts cannot be combined with a specific layout")
            layouts = sorted(p.stem[len("models_"):] for p in source.glob("models_*.ini"))
            if (source / "models.ini").is_file() or not layouts or (source / "ai").is_dir():
                layouts.insert(0, None)
        else:
            layouts = [inline or args.layout]
        for layout in layouts:
            if layout and (layout in (".", "..") or any(c in layout for c in '/\\:')):
                raise ValueError("Invalid layout: " + layout)
            target = Target(source, layout)
            if not source.name:
                raise ValueError("A filesystem root cannot identify a track")
            previous = targets.setdefault(target.venue.casefold(), target)
            if previous != target:
                raise ValueError("Targets have the same output name: " + target.venue)
    return list(targets.values())


def build_command(args, target, rf2, ac, out_root):
    command = [sys.executable, "-m", "ac_to_rf2.build_track", str(target.source),
               "--install", str(rf2 / "ModDev" / "Locations"),
               "--rf2", str(rf2), "--ac", str(ac), "--out-root", str(out_root)]
    if target.layout:
        command += ["--layout", target.layout]
    for name in ("hour", "bake_size", "grain", "detail_metres", "gain", "diffuse",
                 "ambient", "scene_ambient", "blender", "jobs"):
        command += ["--" + name.replace("_", "-"), str(getattr(args, name))]
    if args.skip_geometry:
        command.append("--skip-geometry")
    return command


def install_command(args, target, rf2, out_root):
    return [sys.executable, "-m", "ac_to_rf2.finalize_track", str(out_root / target.venue),
            "--install", str(rf2 / "ModDev" / "Locations"), "--hour", args.hour,
            "--ambient", args.scene_ambient]


@contextmanager
def workflow_lock(rf2):
    """Serialize scripts from all workspaces that target this game installation."""
    path = rf2 / "ModDev" / ".ac2rf2-test.lock"
    with path.open("a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if not lock.tell():
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        import msvcrt
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("Another test workflow is using this rFactor 2 installation") from exc
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def execute(args, rf2, ac, out_root, targets):
    commands = [install_command(args, target, rf2, out_root) if args.install_only
                else build_command(args, target, rf2, ac, out_root) for target in targets]
    for command in commands:
        print(subprocess.list2cmdline(command), flush=True)
    if not args.no_launch:
        print("Launch: %s (working directory: %s)" %
              (rf2 / "Bin64" / "rFactor2 Mod Mode.exe", rf2), flush=True)
    if args.dry_run:
        return
    with workflow_lock(rf2):
        ensure_stopped(rf2, args.restart_game, args.force_close, args.close_timeout)
        env = dict(os.environ, AC2RF2_RF2_DIR=str(rf2), AC2RF2_AC_DIR=str(ac), PYTHONUNBUFFERED="1")
        for command in commands:
            # Recheck before each target in case the game was opened during a build.
            ensure_stopped(rf2)
            subprocess.run(command, cwd=HERE, env=env, check=True)
        if args.no_launch:
            return
        process = launch_developer(rf2, args.launch_timeout, args.trace)
        if targets:
            print("Select track: " + ", ".join(t.venue for t in targets), flush=True)
    if args.wait_for_exit:
        process.wait()


def main(argv=None):
    ap = parser()
    args = ap.parse_args(argv)
    if args.launch_only and (args.tracks or args.no_launch or args.skip_geometry or args.layout or args.all_layouts or args.all_tracks):
        ap.error("--launch-only cannot be combined with track/build options or --no-launch")
    if args.list_tracks and (args.tracks or args.all_tracks or args.layout or args.all_layouts or args.skip_geometry):
        ap.error("--list-tracks cannot be combined with track/build selection options")
    if args.all_tracks and (args.tracks or args.layout):
        ap.error("--all-tracks cannot be combined with track names or --layout")
    if not args.launch_only and not args.tracks and not args.all_tracks and not args.list_tracks:
        ap.error("provide at least one track, use --all-tracks, or use --launch-only")
    if args.force_close and not args.restart_game:
        ap.error("--force-close requires --restart-game")
    if args.no_launch and args.wait_for_exit:
        ap.error("--wait-for-exit requires launching the game")
    if args.install_only and (args.skip_geometry or args.all_layouts):
        ap.error("--install-only uses explicit existing builds; it cannot use --skip-geometry/--all-layouts")
    if (args.jobs <= 0 or args.bake_size <= 0 or not math.isfinite(args.close_timeout)
            or not math.isfinite(args.launch_timeout) or args.close_timeout <= 0 or args.launch_timeout <= 2):
        ap.error("jobs/bake size/close timeout must be positive; launch timeout must exceed 2 seconds")
    try:
        datetime.strptime(args.hour, "%H:%M")
    except ValueError:
        ap.error("--hour must be a valid HH:MM time")
    from ac_to_rf2 import steam_paths
    rf2 = Path(args.rf2 or os.environ.get("AC2RF2_RF2_DIR") or steam_paths.game_dir("rFactor 2")).resolve()
    ac = Path(args.ac or os.environ.get("AC2RF2_AC_DIR") or steam_paths.game_dir("assettocorsa")).resolve()
    out_root = Path(args.out_root).resolve()
    try:
        targets = targets_for(args, ac)
        if args.list_tracks:
            print("Available track identifiers in %s:" % (ac / "content/tracks"))
            for target in targets:
                print("  " + target.source.name + ("::" + target.layout if target.layout else ""))
            return 0
        if not (rf2 / "ModDev" / "Locations").is_dir():
            raise ValueError("Developer Mode Locations folder is missing: " + str(rf2))
        if not args.no_launch and not (rf2 / "Bin64" / "rFactor2 Mod Mode.exe").is_file():
            raise ValueError("Developer Mode executable is missing: " + str(rf2))
        if out_root.is_relative_to(rf2) or out_root.is_relative_to(ac):
            raise ValueError("--out-root must be outside the game installations")
        for target in targets:
            build = (out_root / target.venue).resolve()
            if build.is_relative_to(rf2) or build.is_relative_to(ac):
                raise ValueError("Build output must be outside the game installations: " + str(build))
            if args.install_only:
                for required in (build / "material_map.json", build / "gmt" / "exported.json"):
                    if not required.is_file():
                        raise ValueError("Incomplete build; missing " + str(required))
            else:
                from ac_to_rf2.convert_track import layout_models
                layout_models(str(target.source), target.layout)
        if args.all_tracks or args.list_tracks:
            print("Selected %d track/layout targets from %s" % (len(targets), ac / "content/tracks"), flush=True)
        execute(args, rf2, ac, out_root, targets)
    except (OSError, ValueError, RuntimeError, psutil.Error, subprocess.CalledProcessError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted; no further workflow steps will run.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
