"""Prepare the checkout's standard virtual environment using only the stdlib."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parents[1]


def prepare(root=ROOT):
    if sys.version_info < (3, 10):
        raise RuntimeError("Install Python 3.10 or newer from python.org, then run run.bat again.")
    environment = root / ".venv"
    scripts = environment / ("Scripts" if os.name == "nt" else "bin")
    python = scripts / ("python.exe" if os.name == "nt" else "python")
    if not python.is_file():
        print("Creating .venv (first run)...", flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    # Reinstall after project metadata changes or a moved/replaced environment.
    digest = hashlib.sha256((root / "pyproject.toml").read_bytes()
                            + str(root.resolve()).encode()).hexdigest()
    stamp = environment / ".ac2rf2-setup"
    probe = subprocess.run([str(python), "-c",
        "import sys; assert sys.version_info >= (3, 10); "
        "import numpy, psutil, pytest, build, ac_to_rf2; "
        "from pathlib import Path; "
        "assert Path(ac_to_rf2.__file__).resolve().parent == Path(sys.argv[1]).resolve()",
        str(root / "src/ac_to_rf2")], capture_output=True)
    if probe.returncode or not stamp.is_file() or stamp.read_text() != digest:
        print("Installing project dependencies...", flush=True)
        subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                        "-e", str(root) + "[dev]"], check=True)
        stamp.write_text(digest)


def main():
    try:
        prepare()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print("Setup failed: %s\nCheck Python and your internet connection, then retry run.bat." % exc,
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
