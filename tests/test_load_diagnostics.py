import os
from pathlib import Path
import struct
import subprocess
import sys

import pytest

from ac_to_rf2.load_diagnostics import collect, summarize_trace, write_dump
from ac_to_rf2.make_aiw import lap_score


def test_pit_scoring_uses_main_lap_distance_not_branch_distance():
    square = [(0, 0, 0, 5), (10, 0, 0, 5), (10, 0, 10, 5), (0, 0, 10, 5)]
    assert lap_score((8, 0, -2), square, 40) == (0, 8)
    assert lap_score((12, 0, 8), square, 40) == (1, 18)
    assert lap_score((-2, 0, 2), square, 40) == (2, 38)


def test_trace_summary_keeps_observations_without_declaring_a_cause():
    text = "1 Loading Scene File: track.scn\n2 Entered Sound::Restart()\n3 AIW PATH warning"
    result = summarize_trace(text)
    assert result["scene"] == text.splitlines()[0]
    assert len(result["markers"]) == 2
    assert "cause" not in result


def test_offline_collection_preserves_evidence(tmp_path):
    root = tmp_path / "rf2"
    logs = root / "ModDev/UserData/Log"
    logs.mkdir(parents=True)
    (logs / "trace_1.txt").write_bytes(b"Entered Game::Restart()\n")
    location = root / "ModDev/Locations/test"
    location.mkdir(parents=True)
    (location / "test.AIW").write_bytes(b"exact input")
    out = tmp_path / "report"
    report = collect(root, out)
    assert (out / "locations/test/test.AIW").read_bytes() == b"exact input"
    assert report["snapshots"] == []
    assert report["files"]["locations/test/test.AIW"]["bytes"] == 11
    assert (out / "report.json").is_file()


def test_cannot_write_evidence_into_game(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        collect(tmp_path, tmp_path / "report")


@pytest.mark.skipif(os.name != "nt", reason="Windows DbgHelp API")
def test_real_external_dump_has_threads_modules_and_thread_times(tmp_path):
    # Exercise the actual capture API against a disposable Python helper, never a game.
    child = subprocess.Popen([sys.executable, "-c",
                              "import time; print('ready', flush=True); time.sleep(30)"],
                             stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "ready"
        path = tmp_path / "helper.dmp"
        write_dump(child.pid, path)
        data = path.read_bytes()
        signature, _version, count, directory = struct.unpack_from("<IIII", data)
        assert signature == 0x504D444D
        types = {struct.unpack_from("<III", data, directory + 12*i)[0] for i in range(count)}
        assert {3, 4, 16, 17} <= types
    finally:
        child.terminate()
        child.wait(timeout=10)
