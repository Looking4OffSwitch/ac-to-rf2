"""Replace a location only after its complete replacement has been copied."""
import os
from pathlib import Path
import shutil
import tempfile
import uuid


def install_location(stage, destination):
    destination = Path(destination).absolute()
    pending = Path(tempfile.mkdtemp(prefix="." + destination.name + "-new-",
                                    dir=destination.parent))
    backup = destination.with_name("." + destination.name + "-backup-" + uuid.uuid4().hex)
    try:
        shutil.copytree(stage, pending, dirs_exist_ok=True)
        had_previous = destination.exists()
        if had_previous:
            os.replace(destination, backup)
        try:
            os.replace(pending, destination)
        except OSError:
            if had_previous:
                os.replace(backup, destination)
            raise
        if had_previous:
            # A cleanup failure must not undo a successfully installed venue.
            try:
                shutil.rmtree(backup)
            except OSError as exc:
                print("WARNING installed successfully; old backup retained at %s: %s"
                      % (backup, exc))
    finally:
        if pending.exists():
            shutil.rmtree(pending)
