"""Checked source reads. Unknown layouts must never masquerade as missing data."""
import configparser
import math
from pathlib import Path
import struct
import warnings


class SourceFormatError(ValueError):
    """An unsupported or malformed source, with its location in the file."""


class Reader:
    def __init__(self, data, path="<memory>", format_name="binary"):
        self.d, self.p = data, 0
        self.path, self.format_name = str(path), format_name
        self.context = "header"

    def fail(self, message, offset=None):
        raise SourceFormatError("%s: %s, %s at byte %d: %s" % (
            self.path, self.format_name, self.context,
            self.p if offset is None else offset, message))

    def require(self, size):
        if size < 0 or size > len(self.d) - self.p:
            self.fail("need %d bytes, only %d remain" % (size, len(self.d) - self.p))

    def take(self, size):
        self.require(size)
        start = self.p
        self.p += size
        return self.d[start:self.p]

    def skip(self, size):
        self.require(size)
        self.p += size

    def unpack(self, fmt):
        size = struct.calcsize(fmt)
        self.require(size)
        values = struct.unpack_from(fmt, self.d, self.p)
        self.p += size
        return values

    def u8(self):
        return self.unpack("<B")[0]

    def u16(self):
        return self.unpack("<H")[0]

    def u32(self):
        return self.unpack("<I")[0]

    def i32(self):
        return self.unpack("<i")[0]

    def vec(self, count):
        start = self.p
        values = self.unpack("<%df" % count)
        if not all(math.isfinite(v) for v in values):
            self.fail("non-finite floating-point value", start)
        return values

    def f32(self):
        return self.vec(1)[0]

    def boolean(self):
        start = self.p
        value = self.u8()
        if value not in (0, 1):
            self.fail("invalid boolean %d" % value, start)
        return value

    def count(self, minimum_size, signed=False):
        start = self.p
        value = self.i32() if signed else self.u32()
        if value < 0 or value > (len(self.d) - self.p) // minimum_size:
            self.fail("count %d cannot fit remaining bytes (minimum record %d)" %
                      (value, minimum_size), start)
        return value

    def string(self):
        size = self.u32()
        start = self.p
        raw = self.take(size)
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            self.fail("invalid UTF-8 string", start + exc.start)
        if "\0" in value:
            self.fail("embedded NUL in string", start)
        return value

    def finish(self):
        if self.p != len(self.d):
            self.fail("%d unexpected trailing bytes" % (len(self.d) - self.p))


def read_fast_lane_file(path):
    """Read v7 points and validate its 72-byte extras and optional spatial grid.

    Missing files and the measured stock 12-byte v3 empty stub mean no AI.
    A complete empty v7 file is also allowed. Other present files must validate.
    """
    path = Path(path)
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return []
    if data == struct.pack("<3i", 3, 0, 0):
        warnings.warn("%s: empty AC v3 AI stub; using generated racing line" % path,
                      stacklevel=2)
        return []
    r = Reader(data, path, "AC racing line")
    version = r.i32()
    r.format_name += " v%d" % version
    if version != 7:
        r.fail("unsupported version; supported: 7 (plus the empty v3 stub)", 0)
    count = r.count(20, signed=True)
    r.i32()  # lap time and sample count do not change the record layout
    r.i32()
    points = []
    r.context = "points"
    for i in range(count):
        start = r.p
        point = r.vec(3)
        r.f32()  # cumulative distance
        index = r.i32()
        if not 0 <= index < count:
            r.fail("point id %d outside 0..%d" % (index, count - 1), start + 16)
        points.append(point)
    r.context = "point extras"
    extra = r.count(72, signed=True)
    if extra != count:
        r.fail("extra point count %d differs from point count %d" % (extra, count), r.p - 4)
    r.skip(extra * 72)  # speed/width/etc. are not used by this converter
    r.context = "spatial grid"
    start = r.p
    has_grid = r.i32()
    if has_grid not in (0, 1):
        r.fail("invalid grid flag %d" % has_grid, start)
    if has_grid:
        r.vec(6)  # maximum and minimum bounds
        neighbors = r.i32()
        density = r.f32()
        if neighbors < 0 or density <= 0:
            r.fail("invalid grid neighbors or sampling density")
        for _ in range(r.count(4, signed=True)):
            for _ in range(r.count(4, signed=True)):
                r.skip(r.count(4, signed=True) * 4)  # unused grid references
    r.finish()
    if not points:
        warnings.warn("%s: empty v7 AI; using generated racing line" % path, stacklevel=2)
    return points


def read_ini(path):
    """Unknown sections/keys are compatible; malformed syntax/encoding is not."""
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    try:
        with open(path, encoding="utf-8-sig") as stream:
            cp.read_file(stream)
    except FileNotFoundError:
        pass
    except (UnicodeError, configparser.Error) as exc:
        raise SourceFormatError("%s: invalid INI: %s" % (path, exc)) from exc
    return cp


def ini_required(path, section, key):
    value = section.get(key, "").strip()
    if not value:
        raise SourceFormatError("%s: [%s] missing required %s" % (path, section.name, key))
    return value


def ini_number(path, section, key, default=None):
    raw = section.get(key, default)
    try:
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError("not finite")
        return value
    except (TypeError, ValueError) as exc:
        raise SourceFormatError("%s: [%s] invalid %s=%r; expected finite number" %
                                (path, section.name, key, raw)) from exc


def ini_vector(path, section, key, default=None, allow_short=False):
    raw = section.get(key, default)
    try:
        parts = raw.split(",") if "," in raw else raw.split()
        values = [float(v) for v in parts]
        if not (1 <= len(values) <= 3 if allow_short else len(values) == 3):
            raise ValueError("wrong vector size")
        if not all(math.isfinite(v) for v in values):
            raise ValueError("not finite")
        return values + [0.] * (3 - len(values))
    except (AttributeError, TypeError, ValueError) as exc:
        raise SourceFormatError("%s: [%s] invalid %s=%r; expected %s finite components" %
                                (path, section.name, key, raw,
                                 "1 to 3" if allow_short else "3")) from exc
