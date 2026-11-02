"""Check/install reversible loose WAV aliases for a ModDev vehicle.

Does not launch rFactor, edit sound configurations, or unpack/modify MAS files.
Run ``python -m ac_to_rf2.sound_aliases --help`` for the plan/receipt interface.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PureWindowsPath
import wave

from ac_to_rf2.game_runtime import ensure_stopped


def digest(data):
    return hashlib.sha256(data).hexdigest()


def child(base, relative, sounds=False):
    name = PureWindowsPath(relative)
    if (name.is_absolute() or name.drive or ".." in name.parts or not name.parts
            or (sounds and (name.parts[0].lower() != "sounds" or len(name.parts) < 2))):
        raise ValueError("Expected a relative vehicle sound path: " + relative)
    target = base.joinpath(*name.parts).resolve()
    if not target.is_relative_to(base.resolve()):
        raise ValueError("Path escapes the vehicle directory: " + relative)
    return target


def vehicle_folder(rf2, vehicle):
    if not vehicle or len(PureWindowsPath(vehicle).parts) != 1:
        raise ValueError("vehicle must be one folder name")
    folder = child(rf2 / "ModDev" / "Vehicles", vehicle)
    if not folder.is_dir():
        raise ValueError("Missing ModDev vehicle: " + str(folder))
    return folder


def samples(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "sample" and isinstance(item, str):
                yield item.replace("\\", "/").casefold()
            else:
                yield from samples(item)
    elif isinstance(value, list):
        for item in value:
            yield from samples(item)


def wav_info(data):
    with wave.open(io.BytesIO(data), "rb") as sound:
        channels, width, rate, frames = (sound.getnchannels(), sound.getsampwidth(),
                                          sound.getframerate(), sound.getnframes())
        if sound.getcomptype() != "NONE" or width != 2 or not frames:
            raise ValueError("Aliases require nonempty 16-bit PCM WAV files")
        if len(sound.readframes(frames)) != frames * channels * width:
            raise ValueError("Truncated WAV data")
    return dict(channels=channels, bits=16, rate=rate, frames=frames)


def prepare(spec):
    rf2 = Path(spec["rf2"]).resolve()
    vehicle = vehicle_folder(rf2, spec["vehicle"])
    config = child(vehicle, spec["sound_config"])
    config_data = config.read_bytes()
    declared = set(samples(json.loads(config_data)))
    aliases = spec["aliases"]
    if not isinstance(aliases, dict) or not aliases:
        raise ValueError("aliases must be a nonempty target-to-source mapping")
    rows, seen = [], set()
    for relative, source in aliases.items():
        key = relative.replace("\\", "/").casefold()
        if key in seen or key not in declared:
            raise ValueError("Duplicate or undeclared sound alias: " + relative)
        seen.add(key)
        target = child(vehicle, relative, sounds=True)
        data = Path(source).read_bytes()
        info = wav_info(data)
        if target.exists() and target.read_bytes() != data:
            raise ValueError("Refusing to overwrite existing sound: " + str(target))
        rows.append(dict(target=relative, source=str(Path(source).resolve()),
                         sha256=digest(data), bytes=len(data), audio=info,
                         created=not target.exists(), payload=data))
    return rf2, vehicle, config, digest(config_data), rows


def apply(spec, receipt):
    rf2, vehicle, config, config_sha, rows = prepare(spec)
    receipt = Path(receipt).resolve()
    if receipt.is_relative_to(rf2) or receipt.exists():
        raise ValueError("Use a new receipt path outside the game installation")
    ensure_stopped(rf2)
    created = []
    try:
        for row in rows:
            target = child(vehicle, row["target"], sounds=True)
            if not row["created"]:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation also protects files added after preflight.
            with target.open("xb") as stream:
                created.append(target)
                stream.write(row["payload"])
        record = dict(version=1, state="applied", rf2=str(rf2), vehicle=spec["vehicle"],
                      config=str(config.relative_to(vehicle)), config_sha256=config_sha,
                      aliases=[{k: v for k, v in row.items() if k != "payload"} for row in rows])
        receipt.parent.mkdir(parents=True, exist_ok=True)
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2)
    except BaseException:
        for target in reversed(created):
            target.unlink()
        raise
    return record


def undo(receipt):
    receipt = Path(receipt)
    record = json.loads(receipt.read_text(encoding="utf-8"))
    if record.get("version") != 1 or record.get("state") not in {"applied", "undone"}:
        raise ValueError("Unsupported alias receipt")
    rf2 = Path(record["rf2"]).resolve()
    vehicle = vehicle_folder(rf2, record["vehicle"])
    targets = []
    for row in record["aliases"]:
        target = child(vehicle, row["target"], sounds=True)
        if row["created"] and target.exists():
            if digest(target.read_bytes()) != row["sha256"]:
                raise ValueError("Sound changed since installation; nothing removed: " + str(target))
            targets.append(target)
    if record["state"] == "undone":
        return
    ensure_stopped(rf2)
    for target in targets:
        target.unlink()
    record["state"] = "undone"
    receipt.write_text(json.dumps(record, indent=2), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", type=Path, help="JSON: rf2, vehicle, sound_config, aliases {target: source}")
    mode.add_argument("--undo", type=Path, help="remove only unchanged aliases created by this receipt")
    ap.add_argument("--apply", action="store_true", help="install the checked aliases; default only checks")
    ap.add_argument("--receipt", type=Path, help="new receipt outside the game; required with --apply")
    args = ap.parse_args(argv)
    if args.apply and (not args.plan or not args.receipt):
        ap.error("--apply requires --plan and --receipt")
    try:
        if args.undo:
            undo(args.undo)
            print("Owned audio aliases removed; original SDK files were not edited.")
        else:
            spec = json.loads(args.plan.read_text(encoding="utf-8-sig"))
            _rf2, _vehicle, _config, _sha, rows = prepare(spec)
            for row in rows:
                print("%s: %d bytes, %d-bit PCM, %d Hz (%s)" % (
                    row["target"], row["bytes"], row["audio"]["bits"], row["audio"]["rate"],
                    "create" if row["created"] else "already matches"))
            if args.apply:
                apply(spec, args.receipt)
                print("Installed; receipt: " + str(args.receipt))
            else:
                print("Check only; no game files changed.")
    except (OSError, ValueError, KeyError, TypeError, EOFError, RuntimeError, wave.Error) as exc:
        print("ERROR: " + str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
