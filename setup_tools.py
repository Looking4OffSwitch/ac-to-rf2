"""Install the tested portable Blender/exporter pair without changing system Blender."""
import argparse
import hashlib
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

from blender_paths import ADDONS_DIR, BLENDER_VERSION, PORTABLE_BLENDER, TOOLS_DIR


BLENDER_ARCHIVE = "blender-%s-windows-x64.zip" % BLENDER_VERSION
BLENDER_URL = "https://download.blender.org/release/Blender5.0/" + BLENDER_ARCHIVE
BLENDER_SHA256 = "921d77f6c505a35b2c2f6e67d4ad1c10b72418338ba0e0d3ea7f582a5e5fe46e"
# rFactor2 IO Group R25.11.27, linked by its author in the Studio 397 forum.
EXPORTER_URL = ("https://drive.usercontent.google.com/download?export=download&"
                "id=1pD3vO3rArMjuaImPBmjLlLeVakNmgchm")
EXPORTER_SHA256 = "295b676408c607b4c6cfc7f0fa8b5ce573c0a6fcdfc3151bc1c2ac6afa2877d7"


def checksum(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url, path, expected):
    path = Path(path)
    if path.is_file() and checksum(path) == expected:
        return
    temporary = path.with_suffix(".download")
    try:
        print("Downloading " + path.name, flush=True)
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        if checksum(temporary) != expected:
            raise ValueError("SHA256 mismatch: " + path.name)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def extract(archive, destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for name in source.namelist():
            if not (destination / name).resolve().is_relative_to(destination):
                raise ValueError("unsafe archive member: " + name)
        source.extractall(destination)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    blender_zip = TOOLS_DIR / BLENDER_ARCHIVE
    exporter_zip = TOOLS_DIR / "rf2-exporter-R25.11.27.zip"
    download(BLENDER_URL, blender_zip, BLENDER_SHA256)
    download(EXPORTER_URL, exporter_zip, EXPORTER_SHA256)
    if not PORTABLE_BLENDER.is_file():
        with tempfile.TemporaryDirectory(prefix="extract-", dir=TOOLS_DIR) as work:
            extract(blender_zip, work)
            shutil.move(str(Path(work) / PORTABLE_BLENDER.parent.name), PORTABLE_BLENDER.parent)
    extract(exporter_zip, ADDONS_DIR)
    print("Ready: " + str(PORTABLE_BLENDER))
    print("Community GMT exporter: " + str(ADDONS_DIR / "io_rfactor2_gmt"))
    print("Next: ac2rf2-check")


if __name__ == "__main__":
    main()
