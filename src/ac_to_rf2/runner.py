"""Convert Assetto Corsa tracks and run rFactor 2 Developer Mode."""
import argparse
from pathlib import Path
import subprocess
import sys

from ac_to_rf2.project_paths import WORKSPACE_DIR


COMMANDS = {
    "setup": "download Blender/exporter and check the game installations",
    "check": "check Python, games, Blender and exporter",
    "convert": "convert, verify and install tracks without launching the game",
    "drive": "convert, verify and install tracks, then launch and monitor the game",
    "game": "launch Developer Mode with automatic hang diagnostics (default)",
    "verify": "verify an installed track against its build folder",
    "diagnose": "save logs or capture an already running game's hang",
    "test": "run the project's regression tests",
}


def run_module(module, args):
    return subprocess.call([sys.executable, "-m", module, *args])


def ensure_tools():
    from ac_to_rf2.blender_paths import PORTABLE_BLENDER, ADDONS_DIR
    from ac_to_rf2.exporter_support import EXPORTER_MODULES
    if not PORTABLE_BLENDER.is_file() or not any((ADDONS_DIR / name).is_dir() for name in EXPORTER_MODULES):
        print("Preparing portable Blender and the GMT exporter (first conversion)...", flush=True)
        return run_module("ac_to_rf2.setup_tools", [])
    return 0


def choose_layout(args):
    """Retain the drag-and-drop layout prompt when running interactively."""
    from ac_to_rf2 import drive_track, steam_paths
    import os
    options = drive_track.parser().parse_args(args)
    if (not sys.stdin.isatty() or len(options.tracks) != 1 or options.layout
            or options.all_layouts or options.all_tracks or options.list_tracks or "::" in options.tracks[0]):
        return args
    ac = Path(options.ac or os.environ.get("AC2RF2_AC_DIR") or steam_paths.game_dir("assettocorsa"))
    source = drive_track.targets_for(options, ac)[0].source
    layouts = sorted(p.stem[len("models_"):] for p in source.glob("models_*.ini"))
    if layouts:
        print("Available layouts: " + ", ".join(layouts))
        layout = input("Layout (Enter for default): ").strip()
        if layout:
            return [*args, "--layout", layout]
    return args


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="run.bat", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Commands:\n" + "\n".join("  %-9s %s" % item for item in COMMANDS.items())
               + "\n\nUse run.bat COMMAND --help for options. Quote paths containing spaces.")
    ap.add_argument("command", nargs="?", choices=COMMANDS, default="game")
    if not argv:
        argv = ["game"]
    elif argv[0].startswith("-") and argv[0] not in ("--help", "-h"):
        argv.insert(0, "game")
    command = ap.parse_args(argv[:1]).command
    args = argv[1:]
    try:
        if command in ("convert", "drive"):
            from ac_to_rf2 import drive_track, load_diagnostics
            # Parse help before downloading large conversion tools.
            if "--help" in args or "-h" in args:
                parser = drive_track.parser()
                parser.prog = "run.bat " + command
                if command == "convert":
                    parser.description = "Convert, verify and install AC tracks without launching the game."
                parser.print_help()
                return 0
            args = choose_layout(args)
            options = drive_track.parser().parse_args(args)
            if options.list_tracks:
                return drive_track.main(args)
            if not options.tracks and not options.launch_only and not options.all_tracks:
                drive_track.parser().error("provide at least one track, or use --all-tracks")
            if not (options.dry_run or options.install_only or options.skip_geometry or options.launch_only):
                result = ensure_tools()
                if result:
                    return result
            if command == "convert":
                return drive_track.main([*args, "--no-launch"])
            return load_diagnostics.launch_and_monitor(args, launch_only=False)
        if command == "game":
            from ac_to_rf2 import load_diagnostics
            return load_diagnostics.main(["--launch", *args])
        if command == "setup":
            if "--help" in args or "-h" in args:
                print("run.bat setup [--rf2 FOLDER] [--ac FOLDER] [--blender FILE]\n"
                      "Download portable conversion tools, then check the installation.")
                return 0
            # Validate before downloading.
            parser = argparse.ArgumentParser(prog="run.bat setup")
            for flag in ("--rf2", "--ac", "--blender"):
                parser.add_argument(flag)
            parser.parse_args(args)
            result = run_module("ac_to_rf2.setup_tools", [])
            return result or run_module("ac_to_rf2.check_setup", args)
        modules = {"check": "ac_to_rf2.check_setup", "verify": "ac_to_rf2.verify_install",
                   "diagnose": "ac_to_rf2.load_diagnostics"}
        if command == "test":
            return subprocess.call([sys.executable, "-m", "pytest", *args], cwd=WORKSPACE_DIR)
        return run_module(modules[command], args)
    except (OSError, ValueError, RuntimeError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
