"""Collect offline load evidence or two snapshots of an EXISTING ModDev process.

Never launches, closes, or changes the configuration of the game.
"""
import argparse
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
