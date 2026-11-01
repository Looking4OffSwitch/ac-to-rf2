"""Validate wheel + sdist in a fresh venv, away from checkout imports."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import venv
import zipfile


def run(command, **kwargs):
    result = subprocess.run([str(a) for a in command], capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dist_dir", type=Path)
    args = ap.parse_args()
    dist = args.dist_dir.resolve()
    wheels, sources = list(dist.glob("*.whl")), list(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        ap.error("dist_dir must contain exactly one wheel and one source distribution")
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        assert "ac_to_rf2/blender_entry.py" in names
        assert not any(n.endswith(".py") and "/" not in n for n in names), "stale flat modules in wheel"
    with tarfile.open(sources[0]) as archive:
        names = [n.partition("/")[2] for n in archive.getnames()]
        for required in ["src/ac_to_rf2/blender_entry.py", "docs/NOTES.md", "tests/test_package_layout.py",
                         "tools/probes/probe_normals.py", "convert.bat", "launch_dev_mode.bat"]:
            assert required in names, required
        assert not any(n.startswith(("out/", ".tools/", ".venv/")) for n in names)
    with tempfile.TemporaryDirectory(prefix="distribution-", dir=dist.parent) as temporary:
        work = Path(temporary)
        environment = work / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        env = dict(os.environ)
        for key in ("PYTHONPATH", "PYTHONHOME", "AC2RF2_WORKSPACE", "AC2RF2_TOOLS_DIR"):
            env.pop(key, None)
        run([python, "-m", "pip", "install", "--disable-pip-version-check", wheels[0]], cwd=work, env=env)
        code = '''
from importlib.metadata import distribution
from pathlib import Path
import json
from ac_to_rf2.project_paths import WORKSPACE_DIR, PACKAGE_DIR
from ac_to_rf2.blender_paths import TOOLS_DIR
assert WORKSPACE_DIR == Path.cwd()
assert TOOLS_DIR == Path.cwd() / '.tools'
assert not WORKSPACE_DIR.is_relative_to(PACKAGE_DIR)
entries = distribution('ac-to-rf2').entry_points
expected = {'ac2rf2', 'ac2rf2-test', 'ac2rf2-check', 'ac2rf2-tools', 'ac2rf2-verify'}
assert {e.name for e in entries} == expected
for entry in entries:
    assert callable(entry.load()), entry.name
print(json.dumps({'package': str(PACKAGE_DIR), 'workspace': str(WORKSPACE_DIR)}))
'''
        print(run([python, "-c", code], cwd=work, env=env).strip())
        for command in ("ac2rf2", "ac2rf2-test", "ac2rf2-check", "ac2rf2-tools"):
            executable = scripts / (command + (".exe" if os.name == "nt" else ""))
            assert "usage:" in run([executable, "--help"], cwd=work, env=env).lower()
        assert "usage:" in run([python, "-m", "ac_to_rf2", "--help"], cwd=work, env=env).lower()
        run([python, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", work / "rebuilt", sources[0]],
            cwd=work, env=env)
    print("Wheel commands, isolated imports/workspace, and wheel rebuild from sdist passed.")


if __name__ == "__main__":
    main()
