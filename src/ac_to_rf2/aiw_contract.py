"""Validate the waypoint types and connections emitted by our AIW writer.

Type IDs measured in bundled Joesville and both Loch Drummond AIWs:
main=0, pit lane=1, grid=2+i, pit box=106+i. Pointer D is a type,
not another waypoint index. A/B/C are waypoint references (-1 for no branch).
"""
import collections
import math
import re


def validate_aiw(text):
    """Return diagnostics; never accept a nonempty file as proof of usable AI."""
    def values(block, key, count, cast=int):
        match = re.search(r"(?im)^\s*" + key + r"\s*=\s*\(([^)]*)\)", block)
        if not match:
            raise ValueError("missing " + key)
        result = tuple(cast(x.strip()) for x in match[1].split(","))
        if len(result) != count or any(not math.isfinite(x) for x in result):
            raise ValueError("invalid " + key)
        return result

    try:
        header, *blocks = re.split(r"(?im)^\s*wp_pos\s*=", text)
        number = re.search(r"(?im)^number_waypoints\s*=\s*(\d+)", header)
        if not blocks or not number or int(number[1]) != len(blocks):
            raise ValueError("number_waypoints does not match waypoint records")
        records = []
        for i, block in enumerate(blocks):
            pos = values("wp_pos=" + block, "wp_pos", 3, float)
            ptrs = values(block, "WP_PTRS", 4)
            branch, = values(block, "wp_branchID", 1)
            flags, = values(block, "wp_bitfields", 1)
            pit, = values(block, "wp_pitlane", 1)
            if any(p < 0 or p >= len(blocks) for p in ptrs[:2]) or not -1 <= ptrs[2] < len(blocks):
                raise ValueError("waypoint %d has an out-of-range pointer" % i)
            if branch != ptrs[3] or bool(flags & 1) != (ptrs[3] >= 2):
                raise ValueError("waypoint %d has inconsistent type/branch/nonpath flags" % i)
            if ptrs[3] >= 106 and pit != 1:
                raise ValueError("pit-box waypoint %d is outside the pit lane" % i)
            records.append((pos, ptrs))
        kinds = collections.Counter(r[1][3] for r in records)
        if kinds[0] < 3 or kinds[1] < 2:
            raise ValueError("main loop or typed pit lane is missing")
        # Check the main path really is one reciprocal loop, not two islands.
        main = {i for i, r in enumerate(records) if r[1][3] == 0}
        seen, cur = set(), min(main)
        while cur not in seen:
            if cur not in main:
                raise ValueError("main loop leaves the main path")
            seen.add(cur)
            nxt = records[cur][1][1]
            if records[nxt][1][0] != cur:
                raise ValueError("main loop has nonreciprocal links")
            cur = nxt
        if seen != main:
            raise ValueError("main path contains disconnected loops")
        # Branch reachability alone can accept a pit NEXT loop: C may still
        # point to the main track while the actual driving route never exits.
        for start, record in enumerate(records):
            if record[1][3] != 1:
                continue
            lane_seen, cur = set(), start
            while records[cur][1][3] == 1:
                if cur in lane_seen:
                    raise ValueError("pit lane NEXT links contain a closed cycle")
                lane_seen.add(cur)
                cur = records[cur][1][1]
            if records[cur][1][3] != 0:
                raise ValueError("pit lane NEXT links do not rejoin the main path")
        reached, pending = set(), [min(main)]
        while pending:
            cur = pending.pop()
            if cur in reached:
                continue
            reached.add(cur)
            pending.extend(p for p in records[cur][1][:3] if p >= 0 and p not in reached)
        if len(reached) != len(records):
            raise ValueError("waypoints are disconnected from the main path")
        sections = {m[1].upper(): m[2] for m in re.finditer(
            r"(?ims)^\[([^]\n]+)\]\s*\n(.*?)(?=^\[|\Z)", header)}
        pits = re.findall(r"(?im)^PitPos\s*=\s*\(([^)]*)\)", sections.get("PITS", ""))
        if not pits:
            raise ValueError("no pit positions declared")
        for i, raw in enumerate(pits):
            pos = tuple(map(float, raw.split(",")))
            if len(pos) != 3 or any(not math.isfinite(x) for x in pos):
                raise ValueError("invalid PitPos")
            kind = 106 + i
            if kinds[kind] != 2:
                raise ValueError("pit box %d needs two typed waypoints (%d)" % (i, kind))
            if not any(math.dist(pos, r[0]) < .15 for r in records if r[1][3] == kind):
                raise ValueError("pit box %d has no waypoint at PitPos" % i)
        grids = re.findall(r"(?im)^GridIndex\s*=", sections.get("GRID", ""))
        for i in range(len(grids)):
            if kinds[2 + i] != 2:
                raise ValueError("grid slot %d needs two typed waypoints" % i)
    except (ValueError, IndexError, OverflowError) as exc:
        return ["AIW: " + str(exc)]
    return []
