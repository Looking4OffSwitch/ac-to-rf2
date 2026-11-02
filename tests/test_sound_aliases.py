import io
import json
from pathlib import Path
import wave

import pytest

from ac_to_rf2 import sound_aliases as aliases


def wav(width=2):
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setparams((1, width, 44100, 0, "NONE", "not compressed"))
        stream.writeframes(bytes(100 * width))
    return output.getvalue()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "rf2"
    vehicle = root / "ModDev/Vehicles/car"
    vehicle.mkdir(parents=True)
    config = vehicle / "sound.json"
    config.write_text(json.dumps({"events": [{"sample": "sounds\\a.wav"},
                                             {"sample": "sounds\\b.wav"}]}))
    source = tmp_path / "source.wav"
    source.write_bytes(wav())
    spec = dict(rf2=str(root), vehicle="car", sound_config="sound.json",
                aliases={"sounds/a.wav": str(source), "sounds/b.wav": str(source)})
    monkeypatch.setattr(aliases, "ensure_stopped", lambda root: None)
    return spec, vehicle, tmp_path / "receipt.json"


def test_install_and_undo_preserve_configuration_and_preexisting_files(setup):
    spec, vehicle, receipt = setup
    config = (vehicle / "sound.json").read_bytes()
    (vehicle / "sounds").mkdir()
    original = vehicle / "sounds/a.wav"
    original.write_bytes(wav())
    record = aliases.apply(spec, receipt)
    assert [r["created"] for r in record["aliases"]] == [False, True]
    assert (vehicle / "sounds/b.wav").read_bytes() == wav()
    assert (vehicle / "sound.json").read_bytes() == config
    aliases.undo(receipt)
    assert original.read_bytes() == wav()
    assert not (vehicle / "sounds/b.wav").exists()
    aliases.undo(receipt)


def test_preflight_refuses_conflict_before_creating_any_files(setup):
    spec, vehicle, receipt = setup
    (vehicle / "sounds").mkdir()
    (vehicle / "sounds/b.wav").write_bytes(b"user content")
    with pytest.raises(ValueError, match="overwrite"):
        aliases.apply(spec, receipt)
    assert not (vehicle / "sounds/a.wav").exists()
    assert (vehicle / "sounds/b.wav").read_bytes() == b"user content"


@pytest.mark.parametrize("payload,diagnostic", [(wav(1), "16-bit"), (wav()[:-2], "Truncated")])
def test_bad_wav_rejected(setup, payload, diagnostic):
    spec, vehicle, receipt = setup
    Path(next(iter(spec["aliases"].values()))).write_bytes(payload)
    with pytest.raises(ValueError, match=diagnostic):
        aliases.apply(spec, receipt)
    assert not (vehicle / "sounds").exists()


def test_undeclared_sample_rejected(setup):
    spec, _vehicle, receipt = setup
    spec["aliases"]["sounds/unknown.wav"] = next(iter(spec["aliases"].values()))
    with pytest.raises(ValueError, match="undeclared"):
        aliases.apply(spec, receipt)


@pytest.mark.parametrize("path", ["../escape.wav", "sounds/../../escape.wav",
                                   "C:\\escape.wav", "sounds\\..\\escape.wav"])
def test_paths_cannot_escape_vehicle(tmp_path, path):
    with pytest.raises(ValueError):
        aliases.child(tmp_path, path, sounds=True)


def test_undo_checks_all_hashes_before_removing_any_files(setup):
    spec, vehicle, receipt = setup
    aliases.apply(spec, receipt)
    (vehicle / "sounds/b.wav").write_bytes(b"later user edit")
    with pytest.raises(ValueError, match="nothing removed"):
        aliases.undo(receipt)
    assert (vehicle / "sounds/a.wav").exists()
    assert (vehicle / "sounds/b.wav").read_bytes() == b"later user edit"


def test_running_game_prevents_install(setup, monkeypatch):
    spec, vehicle, receipt = setup

    def running(root):
        raise RuntimeError("game running")

    monkeypatch.setattr(aliases, "ensure_stopped", running)
    with pytest.raises(RuntimeError, match="game running"):
        aliases.apply(spec, receipt)
    assert not (vehicle / "sounds").exists()


def test_failed_receipt_creation_rolls_back_new_aliases(setup):
    spec, vehicle, receipt = setup
    blocker = receipt.parent / "not-a-directory"
    blocker.write_bytes(b"existing user file")
    with pytest.raises(OSError):
        aliases.apply(spec, blocker / "receipt.json")
    assert not (vehicle / "sounds/a.wav").exists()
    assert not (vehicle / "sounds/b.wav").exists()
    assert blocker.read_bytes() == b"existing user file"


def test_default_cli_only_checks(setup, tmp_path):
    spec, vehicle, _receipt = setup
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(spec))
    assert aliases.main(["--plan", str(plan)]) == 0
    assert not (vehicle / "sounds").exists()
