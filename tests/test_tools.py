import io
from pathlib import Path
import subprocess
import zipfile

import pytest

from ac_to_rf2.blender_paths import PORTABLE_BLENDER
from ac_to_rf2.setup_tools import download, extract


def test_download_rejects_bad_checksum_without_replacing_existing_file(tmp_path, monkeypatch):
    archive = tmp_path / "archive.zip"
    archive.write_bytes(b"existing")
    monkeypatch.setattr("ac_to_rf2.setup_tools.urllib.request.urlopen", lambda *a, **k: io.BytesIO(b"wrong"))
    with pytest.raises(ValueError, match="SHA256"):
        download("https://example.test/archive.zip", archive, "0" * 64)
    assert archive.read_bytes() == b"existing"
    assert not archive.with_suffix(".download").exists()


def test_extract_rejects_archive_path_escape(tmp_path):
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as source:
        source.writestr("../outside.txt", "bad")
    with pytest.raises(ValueError, match="unsafe archive"):
        extract(archive, tmp_path / "target")
    assert not (tmp_path / "outside.txt").exists()


def test_real_community_exporter_serialization(tmp_path):
    if not PORTABLE_BLENDER.is_file():
        pytest.skip("Run ac2rf2-tools to enable the real GMT exporter regression test")
    result = subprocess.run([str(PORTABLE_BLENDER), "--background", "--factory-startup",
                             "--python-exit-code", "1", "--python",
                             str(Path(__file__).with_name("exporter_smoke.py")), "--", str(tmp_path)],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "AC2RF2 EXPORTER SMOKE" in result.stdout
