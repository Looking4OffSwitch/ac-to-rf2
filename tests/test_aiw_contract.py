import re

import pytest

from ac_to_rf2.aiw_contract import validate_aiw
from ac_to_rf2.make_aiw import render_aiw


def example():
    # Both grid slots and both boxes share anchors: no branch may be overwritten.
    main = [(0, 0, 0, 6), (20, 0, 0, 6), (20, 0, 20, 6), (0, 0, 20, 6)]
    lane = [(4, 0, 1, 0), (10, 0, 1, 0), (16, 0, 1, 0)]
    boxes = [(10, 0, 3, 0), (10, 0, 4, 0)]
    starts = [((0, 0, 1), 0, "a"), ((0, 0, 2), 0, "b")]
    return render_aiw(main, 80, starts, boxes, boxes,
                      dict(entry=0, exit=1, lane=lane, boxes=boxes, side=1))


def test_connected_grid_pits_and_lane_have_native_types():
    text = example()
    assert validate_aiw(text) == []
    types = [int(m[1]) for m in re.finditer(r"wp_branchID=\((\d+)\)", text)]
    assert types == [0]*4 + [1]*3 + [2]*2 + [3]*2 + [106]*2 + [107]*2
    assert "number_waypoints=15" in text


@pytest.mark.parametrize("mutate,diagnostic", [
    (lambda s: s.replace("number_waypoints=15", "number_waypoints=16"), "number_waypoints"),
    (lambda s: s.replace("wp_branchID=(106)", "wp_branchID=(0)"), "inconsistent type"),
    (lambda s: s.replace("WP_PTRS=(3,1,", "WP_PTRS=(999,1,", 1), "out-of-range"),
    (lambda s: re.sub(r"WP_PTRS=\((\d+),(\d+),-?\d+,", r"WP_PTRS=(\1,\2,-1,", s), "disconnected"),
    (lambda s: s.replace("PitPos=(10.000,0.000,3.000)", "PitPos=(99.000,0.000,3.000)"), "at PitPos"),
    (lambda s: s.replace("wp_pos=(", "wp_pos=(nan,", 1), "invalid wp_pos"),
])
def test_rejects_regressions(mutate, diagnostic):
    assert diagnostic in ";".join(validate_aiw(mutate(example())))


def test_rejects_old_missing_pit_types():
    text = example()
    text = text.replace("wp_branchID=(106)", "wp_branchID=(4)").replace(
        ",106)", ",4)")
    assert "pit box 0" in ";".join(validate_aiw(text))


def test_nonempty_placeholder_is_not_a_valid_aiw():
    assert validate_aiw("fixture")


def test_pit_driving_cycle_is_rejected_even_with_other_branch_connections():
    text = example()
    blocks = re.split(r"(?im)^wp_pos=", text)
    blocks[5] = re.sub(r"WP_PTRS=\((\d+),\d+,", r"WP_PTRS=(\1,4,", blocks[5])
    assert "closed cycle" in ";".join(validate_aiw("wp_pos=".join(blocks)))


def test_backward_pit_exit_branch_reproduces_native_scoring_infinite_loop():
    # Main exit 1 branches back to pit end 6, whose NEXT is main exit 1.
    # All pointers are in range and all nodes remain graph-reachable, yet
    # the native scoring walk from 6.NEXT can never return to 6.
    text = example().replace("WP_PTRS=(0,2,-1,0)", "WP_PTRS=(0,2,6,0)")
    assert "branch scoring walk loops forever" in ";".join(validate_aiw(text))


def test_missing_pit_lane_stops_generation():
    with pytest.raises(ValueError, match="connected pit lane"):
        render_aiw([], 0, [], [], [], None)
