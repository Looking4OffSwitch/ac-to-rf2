"""Collect offline load evidence or two snapshots of an EXISTING ModDev process.

Direct collection never launches/closes the game. The root launcher uses explicit
--launch mode to start Developer Mode and automatically monitor it.
"""
import argparse
import sys
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time

import psutil

from ac_to_rf2.game_runtime import game_processes, is_developer
from ac_to_rf2.project_paths import WORKSPACE_DIR


def summarize_trace(text):
    lines = text.splitlines()
    scenes = [line for line in lines if "Loading Scene File:" in line]
    return dict(scene=scenes[-1] if scenes else None, tail=lines[-60:],
                markers=[line for line in lines if any(word in line for word in
                         ("::Restart()", "Entering DYN", "onFatalError", "RF2 Warning", "AIW PATH"))])


def write_dump(pid, destination):
    """External DbgHelp capture: stacks, contexts, thread times and memory map."""
    if os.name != "nt" or ctypes.sizeof(ctypes.c_void_p) != 8:
        raise RuntimeError("Capture requires 64-bit Windows Python")
    import msvcrt
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    dbg = ctypes.WinDLL("dbghelp", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    dbg.MiniDumpWriteDump.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.HANDLE,
                                     wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    dbg.MiniDumpWriteDump.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x410, False, pid)  # query information + VM read
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        with Path(destination).open("xb") as stream:
            # Normal stacks + unloaded modules + indirect memory + memory map + thread info.
            if not dbg.MiniDumpWriteDump(handle, pid, msvcrt.get_osfhandle(stream.fileno()),
                                         0x1860, None, None, None):
                raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)


def window_unresponsive(pid):
    """Read Windows' own hung-window state for this process's top-level windows."""
    user = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.IsHungAppWindow.argtypes = [wintypes.HWND]
    user.IsHungAppWindow.restype = wintypes.BOOL
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    found = []

    @callback_type
    def inspect(hwnd, _):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user.IsHungAppWindow(hwnd):
            found.append(True)
        return True

    if not user.EnumWindows(inspect, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return bool(found)


def monitor(process, rf2, destination, hung=window_unresponsive,
            clock=time.monotonic, sleep=time.sleep):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    created, since, next_capture, number = process.create_time(), None, 0, 0
    print("Automatic diagnostics active until the game exits.\n"
          "Evidence directory: " + str(destination), flush=True)
    with (destination / "timeline.jsonl").open("w", encoding="utf-8", buffering=1) as timeline:
        while True:
            try:
                if not process.is_running() or process.create_time() != created:
                    break
                unresponsive = hung(process.pid)
                timeline.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),
                    unresponsive=unresponsive, cpu=process.cpu_times()._asdict(),
                    memory=process.memory_info()._asdict())) + "\n")
                if unresponsive:
                    since = clock() if since is None else since
                    if clock() - since >= 10 and clock() >= next_capture:
                        number += 1
                        target = destination / ("hang-%04d" % number)
                        print("Capturing unresponsive state: " + str(target), flush=True)
                        try:
                            collect(rf2, target, pid=process.pid)
                        except (OSError, ValueError, RuntimeError, psutil.Error) as exc:
                            timeline.write(json.dumps(dict(capture_error=str(exc))) + "\n")
                            print("Capture error; monitoring continues: " + str(exc), flush=True)
                        next_capture = clock() + 30
                else:
                    since, next_capture = None, 0
                sleep(1)
            except psutil.NoSuchProcess:
                break
    print("Game exited; preserving final logs.", flush=True)
    return collect(rf2, destination / "exit")


def launch_and_monitor(argv):
    # The root batch activates .venv and delegates the entire workflow here.
    from ac_to_rf2 import drive_track, steam_paths
    args = [a for a in argv if a != "--wait-for-exit"]
    result = drive_track.main(["--launch-only", "--trace", "5", *args])
    if result or "--dry-run" in args:
        return result
    # Reuse the exact installation resolution used by the launch command.
    options = drive_track.parser().parse_args(["--launch-only", *args])
    rf2 = Path(options.rf2 or os.environ.get("AC2RF2_RF2_DIR") or steam_paths.game_dir("rFactor 2")).resolve()
    destination = WORKSPACE_DIR / "out/diagnostics" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    processes = [p for p in game_processes(rf2) if is_developer(p, rf2)]
    if len(processes) != 1:
        collect(rf2, destination)
        raise RuntimeError("Game exited before monitoring; traces preserved in " + str(destination))
    monitor(processes[0], rf2, destination)
    print("Evidence saved: " + str(destination), flush=True)
    return 0


def collect(rf2, destination, pid=None, interval=3):
    rf2, destination = Path(rf2).resolve(), Path(destination).resolve()
    if destination.is_relative_to(rf2):
        raise ValueError("Diagnostics must be outside the game installation")
    process = None
    if pid is not None:
        candidates = [p for p in game_processes(rf2) if is_developer(p, rf2)
                      and (pid == 0 or p.pid == pid)]
        if len(candidates) != 1:
            raise ValueError("Expected one running ModDev process; leave the hung game open")
        process = candidates[0]
    destination.mkdir(parents=True, exist_ok=False)
    report = dict(utc=datetime.now(timezone.utc).isoformat(), rf2=str(rf2), traces={}, files={}, snapshots=[])

    def save(path, relative):
        data = path.read_bytes()
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        report["files"][relative] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        return data

    try:
        logs = rf2 / "ModDev/UserData/Log"
        for path in sorted(logs.glob("trace_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:8]:
            data = save(path, "logs/" + path.name)
            report["traces"][path.name] = summarize_trace(data.decode(errors="replace"))
        # Keep the actual track inputs and hashes needed to reproduce the comparison.
        locations = rf2 / "ModDev/Locations"
        for path in locations.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".aiw", ".scn", ".gdb", ".tdf"}:
                save(path, "locations/" + path.relative_to(locations).as_posix())
        if process:
            report["pid"] = process.pid
            report["process_created"] = process.create_time()
            for number in range(2):
                if not process.is_running() or process.create_time() != report["process_created"]:
                    raise RuntimeError("Game exited during capture")
                snapshot = dict(utc=datetime.now(timezone.utc).isoformat(),
                                cpu=process.cpu_times()._asdict(), memory=process.memory_info()._asdict(),
                                threads=[t._asdict() for t in process.threads()])
                report["snapshots"].append(snapshot)
                dump = destination / ("snapshot-%d.dmp" % number)
                print("Capturing " + str(dump), flush=True)
                write_dump(process.pid, dump)
                snapshot["dump_bytes"] = dump.stat().st_size
                if not number:
                    time.sleep(interval)
            # Capture log progress during the same sampling interval.
            for path in sorted(logs.glob("trace_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:1]:
                save(path, "after/" + path.name)
    finally:
        (destination / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--launch":
        try:
            return launch_and_monitor(argv[1:])
        except KeyboardInterrupt:
            print("Diagnostic monitoring stopped; game was not closed.")
            return 130
        except (OSError, ValueError, RuntimeError, psutil.Error) as exc:
            print("ERROR: " + str(exc))
            return 1
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rf2", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--capture", action="store_true", help="capture two dumps of the already running game")
    ap.add_argument("--pid", type=int, help="specific ModDev PID (otherwise find the only running one)")
    args = ap.parse_args(argv)
    if args.pid and not args.capture:
        ap.error("--pid requires --capture")
    try:
        from ac_to_rf2.steam_paths import game_dir
        rf2 = args.rf2 or Path(game_dir("rFactor 2"))
        out = args.out or WORKSPACE_DIR / "out/diagnostics" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        collect(rf2, out, (args.pid or 0) if args.capture else None)
        print("Evidence saved: " + str(out))
    except (OSError, ValueError, RuntimeError, psutil.Error) as exc:
        print("ERROR: " + str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
