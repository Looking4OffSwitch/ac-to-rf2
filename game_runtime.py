"""Launch and identify the actual Developer Mode process, without a shell."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import time

import psutil


MOD_EXE = "rFactor2 Mod Mode.exe"
GAME_NAMES = {MOD_EXE.lower(), "rfactor2.exe", "launch rfactor.exe"}


def game_processes(rf2):
    """Only processes from this installation; include the launcher's singleton."""
    root = Path(rf2).resolve()
    result = []
    for process in psutil.process_iter(["name", "exe", "cmdline"]):
        if (process.info.get("name") or "").lower() not in GAME_NAMES:
            continue
        executable = process.info.get("exe")
        if not executable:
            if process.is_running():
                raise RuntimeError("Cannot inspect rFactor process %d; close it before continuing" % process.pid)
            continue
        if Path(executable).resolve().is_relative_to(root):
            result.append(process)
    return result


def is_developer(process, rf2):
    executable = process.info.get("exe")
    command = process.info.get("cmdline") or []
    # A CEF renderer child can carry the same name; it is not proof of a game.
    return (executable is not None and
            Path(executable).resolve() == (Path(rf2) / "Bin64" / MOD_EXE).resolve()
            and not any(arg.startswith("--type=") for arg in command))


def close_windows(processes):
    """Request normal GUI shutdown. TerminateProcess is never used implicitly."""
    if os.name != "nt":
        raise RuntimeError("rFactor 2 testing is supported on Windows")
    pids = {p.pid for p in processes if p.is_running()}
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]

    @callback_type
    def close(hwnd, _param):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        return True

    if not user32.EnumWindows(close, 0):
        raise ctypes.WinError(ctypes.get_last_error())


def ensure_stopped(rf2, restart=False, force=False, timeout=30):
    processes = game_processes(rf2)
    if not processes:
        return
    if not restart:
        raise RuntimeError("rFactor 2 or its launcher is running. Close it, or use --restart-game.")
    print("Closing rFactor 2 and its launcher...", flush=True)
    close_windows(processes)
    _gone, alive = psutil.wait_procs(processes, timeout=timeout)
    if alive and force:
        for process in alive:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(alive, timeout=5)
    if game_processes(rf2):
        raise RuntimeError("rFactor 2 did not close. Exit it manually or add --force-close with --restart-game.")


def launch_developer(rf2, timeout=90, trace=2):
    """Use Studio 397's executable + Start In, then verify sustained identity."""
    root = Path(rf2).resolve()
    executable = root / "Bin64" / MOD_EXE
    if not executable.is_file():
        raise RuntimeError("Developer Mode executable is missing: " + str(executable))
    if game_processes(root):
        raise RuntimeError("rFactor 2 started during the workflow. Close it before launching Developer Mode.")
    print("Starting Developer Mode from " + str(root), flush=True)
    # Interactive game: deliberately visible and detached from this console.
    child = subprocess.Popen([str(executable), "+trace=%d" % trace], cwd=root)
    deadline, found_at, found_pid = time.monotonic() + timeout, None, None
    while time.monotonic() < deadline:
        processes = game_processes(root)
        developer = next((p for p in processes if is_developer(p, root)), None)
        if developer is not None:
            if found_at is None or found_pid != developer.pid:
                found_at = time.monotonic()
                found_pid = developer.pid
            elif time.monotonic() - found_at >= 2:
                print("Developer Mode confirmed (PID %d)." % developer.pid, flush=True)
                return developer
        else:
            found_at = None
            if any(Path(p.info["exe"]).name.lower() == "rfactor2.exe" for p in processes):
                raise RuntimeError("Launch opened regular rFactor 2, not Developer Mode. "
                                   "Exit it and check Steam is running and logged in.")
            if child.poll() not in (None, 0):
                raise RuntimeError("Developer Mode exited with code %s; see ModDev/UserData/Log." % child.returncode)
        time.sleep(.5)
    raise RuntimeError("Developer Mode did not stay running within %s seconds. "
                       "Check Steam/dialogs and ModDev/UserData/Log; launch was not confirmed." % timeout)
