"""board_fit against small designs whose answer is known before it runs.

The tool's job is to say FAIL out loud and exit non-zero. So every test here
either drives `main()` and reads the exit code and the text a person would
see, or checks a figure that can be worked out on paper (48 x 219 mm board,
0.5 mm courtyard).
"""
import runpy
from dataclasses import replace
from pathlib import Path

import pytest

from tools import board_fit as bf
from tools.model import ConnPin, Connector, Design, Part


def part(ref, board, height, footprint=(2.0, 1.25), *, side="top", confirmed=True,
         package="0805", mpn="X"):
    return Part(ref, mpn, package, board, "R", ("1", "2"), height, confirmed,
                footprint, side=side)


def conn(ref, board, height, footprint=(20.0, 9.0), *, confirmed=True, interface=None,
         leaves_box=None, overhang=0.0):
    return Connector(ref, board, f"{ref} harness", (ConnPin("1", ""),), height,
                     confirmed, footprint,
                     leaves_box=interface is None if leaves_box is None else leaves_box,
                     interface=interface, overhang_mm=overhang)


def with_connectors(design, *more):
    return replace(design, connectors=design.connectors + more)


def good() -> Design:
    """Closes on every budget: 52.0 mm of 64, sparse boards. The brick is under
    POWER on its floor seat, as in the design. Its two 7.0 mm connectors are
    internal, so it has no rows; the ROWS tests add harness headers to it."""
    return Design(
        parts=(part("L101", "POWER", 14.0, (22.0, 14.0), package="THT"),
               part("U201", "POWER", 12.7, (58.3, 37.2), package="brick",
                    side="bottom"),
               part("U401", "LOGIC", 3.1, (25.5, 18.0), package="module")),
        connectors=(conn("J301", "OUTPUTS", 7.0, leaves_box=False),
                    conn("J401", "LOGIC", 7.0, leaves_box=False)))


def run(capsys, design):
    code = bf.main([], design)
    return code, capsys.readouterr().out


# --- the clean design ------------------------------------------------------------
def test_a_design_that_closes_passes_and_still_says_it_is_provisional(capsys):
    code, out = run(capsys, good())
    assert code == 0
    assert "✅ PASS" in out and "⛔" not in out
    assert "PROVISIONAL" in out and "M18 NOT MEASURED" in out
    assert "enclosure not chosen" in out
    assert bf.problems(good()) == []


# --- height ------------------------------------------------------------------------
def test_an_over_height_stack_fails(capsys, binding_envelope):
    tall = good().replace_part("L101", height_mm=30.0)      # 52.0 + 16.0 = 68.0
    code, out = run(capsys, tall)
    assert code == 1
    assert "⛔ FAIL" in out and "OVER by 4.0 mm" in out
    assert "L101 30.0 up" in out                            # and says what did it


def test_an_unconfirmed_height_is_reported_and_starred_when_it_sets_a_gap(capsys):
    d = good().replace_part("L101", height_confirmed=False) \
        .with_part(part("R101", "POWER", 0.6, confirmed=False))
    code, out = run(capsys, d)
    assert code == 0                                        # reported, not failed
    assert "UNCONFIRMED HEIGHTS   2 not read" in out
    listing = out[out.index("UNCONFIRMED HEIGHTS"):].splitlines()
    l101 = next(ln for ln in listing if ln.endswith(": L101"))
    r101 = next(ln for ln in listing if ln.endswith(": R101"))
    assert "⭐" in l101 and "14.0 mm" in l101
    assert "⭐" not in r101 and "0.6 mm" in r101
    assert "1 unconfirmed height(s) set gaps" in out


def test_identical_unconfirmed_parts_share_a_line_but_every_refdes_is_named(capsys):
    d = good()
    for ref in ("R1", "R2", "R3"):
        d = d.with_part(part(ref, "OUTPUTS", 0.6, confirmed=False, mpn="R-1k"))
    out = run(capsys, d)[1]
    assert "UNCONFIRMED HEIGHTS   3 not read" in out
    assert any(ln.endswith("R-1k: R1 R2 R3") for ln in out.splitlines())


def test_no_unconfirmed_section_when_every_height_is_confirmed(capsys):
    assert "UNCONFIRMED" not in run(capsys, good())[1]


def test_a_bottom_side_part_taller_than_the_gap_below_it_fails(capsys):
    # A chosen (confirmed) STACK pair sets OUTPUTS->LOGIC at 8.5 + 2.54 = 11.04 mm.
    d = with_connectors(
        good(),
        conn("J308", "OUTPUTS", 8.5, (63.5, 5.0), interface="STACK"),
        conn("J406", "LOGIC", 2.54, (63.5, 5.0), interface="STACK"))
    assert bf.main([], d) == 0
    d = d.with_part(part("C450", "LOGIC", 12.0, (10.0, 10.0), side="bottom"))
    code, out = run(capsys, d)
    assert code == 1
    assert "C450 hangs 12.0 mm under LOGIC" in out
    assert "J308+J406" in out and "11.0" in out


# --- plugs at the walls (MX-3) ------------------------------------------------------
def test_the_edge_a_board_s_headers_take_by_hand():
    """Two 20 mm headers 1 mm apart; room = the 9.6 mm plug + the 10 mm bend."""
    d = with_connectors(good(), conn("J302", "OUTPUTS", 7.0, overhang=9.6),
                        conn("J303", "OUTPUTS", 7.0, overhang=0.0))
    (e,) = bf.edge_budget(d)
    assert (e.board, e.side, e.headers) == ("OUTPUTS", "top", ("J302", "J303"))
    assert (e.length_mm, e.room_mm) == (pytest.approx(41.0), pytest.approx(19.6))


def test_a_terminal_under_a_board_is_a_row_of_its_own(capsys):
    """IO-6: one row per FACE. The 5 V row hangs under OUTPUTS, under the 12 V
    row on top of it; summed as one board they would report 41 mm of edge where
    neither row is longer than 20, and OUTPUTS would fail a length no row needs."""
    d = with_connectors(good(), conn("J302", "OUTPUTS", 7.0, overhang=9.6),
                        replace(conn("J314", "OUTPUTS", 7.0, overhang=8.9),
                                side="bottom"))
    rows = {(e.board, e.side): e for e in bf.edge_budget(d)}
    assert set(rows) == {("OUTPUTS", "top"), ("OUTPUTS", "bottom")}
    assert rows[("OUTPUTS", "top")].length_mm == pytest.approx(20.0)
    assert rows[("OUTPUTS", "bottom")].length_mm == pytest.approx(20.0)
    assert rows[("OUTPUTS", "bottom")].room_mm == pytest.approx(18.9)
    out = run(capsys, d)[1]
    assert "OUTPUTS top " in out and "OUTPUTS bottom " in out


def test_a_row_longer_than_its_board_fails():
    from tools import netlist
    d = netlist.current()
    long = d.replace_connector("J409", footprint_mm=(bf.bp.BOARD_L + 1.0, 9.2))
    assert any("row" in p and "LOGIC" in p for p in bf.face_verdicts(long))


def test_a_row_longer_than_its_board_is_a_plain_failure_not_a_caveat(capsys):
    """IO-14 made the board the design's own requirement, so a row that does not
    fit it is a failure whatever M18 turns out to say. Two 120 mm headers 1 mm
    apart take 241 mm of a 219 mm board: 22 mm over."""
    d = with_connectors(good(),
                        conn("J302", "OUTPUTS", 7.0, (120.0, 9.2), overhang=9.6),
                        conn("J303", "OUTPUTS", 7.0, (120.0, 9.2), overhang=9.6))
    (e,) = bf.edge_budget(d)
    assert e.length_mm == pytest.approx(241.0)
    code, out = run(capsys, d)
    assert code == 1 and "✅ PASS" not in out
    assert "row: OUTPUTS's 2 harness headers take 241 mm of the face" in out
    assert "the board is 219 mm long" in out
    assert "⛔ DOES NOT FIT (22 mm over)" in out


def test_a_row_that_fits_its_board_is_no_verdict_at_all(capsys):
    d = with_connectors(good(), conn("J302", "OUTPUTS", 7.0, (120.0, 9.2), overhang=9.6))
    assert bf.face_verdicts(d) == [] and run(capsys, d)[0] == 0


def test_an_unknown_height_fails_instead_of_vanishing(capsys):
    code, out = run(capsys, good().replace_part("L101", height_mm=float("nan")))
    assert code == 1 and "height: L101" in out


# --- the cavity the design REQUIRES (IO-14, M18) ---------------------------------------
# ⚠️ Every one of these drives the fixture `measured_cavity`. The real
# CAVITY_MEASURED is False and is not touched: what is proven here is that the
# comparison exists and is gated, not what the bike measures.
def test_a_measured_cavity_that_holds_the_design_passes(capsys, measured_cavity):
    """The design requires 233.0 along x 74.65 across; a 240 x 80 box holds it,
    so the report states the measurement and the tool passes."""
    measured_cavity(240.0, 80.0)
    code, out = run(capsys, good())
    assert code == 0 and "✅ PASS" in out and "⛔" not in out
    assert "MEASURED (M18) -- the cavity is 240 x 80 x 70 mm" in out
    assert "the requirement fits inside it" in out
    assert "NOT MEASURED" not in out and "finding for M18" not in out
    assert bf.problems(good()) == []


def test_a_measured_cavity_too_short_for_the_design_fails(capsys, measured_cavity):
    """233.0 mm of board, wall and end clearance into a 230 mm box: 3 mm over."""
    measured_cavity(230.0, 80.0)
    code, out = run(capsys, good())
    assert code == 1 and "⛔ FAIL" in out and "✅ PASS" not in out
    (problem,) = [p for p in bf.problems(good()) if p.startswith("cavity ")]
    assert problem.startswith("cavity along:")                   # names the axis
    assert "requires 233.00 mm" in problem and "gives 230.00 mm" in problem
    assert "OVER by 3.00 mm" in problem                          # ...and by how much
    assert "the requirement EXCEEDS it along by 3.0 mm" in out
    assert "DOES NOT FIT the cavity that was measured" in out


def test_a_measured_cavity_too_narrow_for_the_design_fails(capsys, measured_cavity):
    """74.65 mm of board, walls, drop-in and plug room into a 70 mm box."""
    measured_cavity(240.0, 70.0)
    code, out = run(capsys, good())
    assert code == 1 and "⛔ FAIL" in out and "✅ PASS" not in out
    (problem,) = [p for p in bf.problems(good()) if p.startswith("cavity ")]
    assert problem.startswith("cavity across:")
    assert "requires 74.65 mm" in problem and "gives 70.00 mm" in problem
    assert "OVER by 4.65 mm" in problem
    assert "the requirement EXCEEDS it across by 4.7 mm" in out


def test_a_measured_cavity_short_on_both_axes_names_both(capsys, measured_cavity):
    measured_cavity(230.0, 70.0)
    axes = [p.split(":")[0] for p in bf.problems(good()) if p.startswith("cavity ")]
    assert axes == ["cavity along", "cavity across"]
    assert "EXCEEDS it along by 3.0 mm, across by 4.7 mm" in run(capsys, good())[1]


def test_the_same_overrun_is_a_finding_while_the_cavity_is_an_estimate(capsys):
    """The real flags, untouched: the requirement exceeds M18's estimate by
    33.0 mm and 24.7 mm and the design still PASSES. This is the other half of
    the three tests above -- what the flag changes is the gate, not the
    arithmetic, and a tool that reported the same paragraph either way was the
    defect."""
    code, out = run(capsys, good())
    assert code == 0 and "✅ PASS" in out
    assert "⬜ NOT MEASURED -- M18's estimate is 200 x 50 x 70 mm" in out
    assert "the requirement EXCEEDS it along by 33.0 mm, across by 24.7 mm" in out
    assert "finding for M18, not a failure of the design" in out
    assert not any(p.startswith("cavity ") for p in bf.problems(good()))


# --- area: density -------------------------------------------------------------------
def test_density_is_bodies_over_the_side_less_its_mounting_corners():
    rows = {(s.board, s.side): s for s in bf.area_budget(good())}
    brick = rows[("POWER", "bottom")]                       # the brick's own face
    assert brick.raw_mm2 == pytest.approx(58.3 * 37.2)
    assert bf.MOUNT_AREA == pytest.approx(4 * 7.0 * 7.0)     # 3.5 mm inset, both ways
    assert brick.density == pytest.approx(58.3 * 37.2 / (48 * 219 - 196))


def test_a_side_over_the_density_limit_fails(capsys):
    # Three 46 x 56 slabs beside J301's 20 x 9: 3 x 2576 + 180 = 7908 mm² of the
    # 48 x 219 - 196 = 10316 usable = 77 % > 75 %. Two of them is 5332 = 52 %.
    d = good()
    for i in range(3):
        d = d.with_part(part(f"X{i}", "OUTPUTS", 1.0, (46.0, 56.0)))
    code, out = run(capsys, d)
    assert code == 1
    assert any(p.startswith("density: OUTPUTS top is 77%") for p in bf.problems(d))
    two = good().with_part(part("X0", "OUTPUTS", 1.0, (46.0, 56.0))) \
        .with_part(part("X1", "OUTPUTS", 1.0, (46.0, 56.0)))
    assert not any(p.startswith("density") for p in bf.problems(two))   # 52 %


# --- area: the naive pack --------------------------------------------------------------
def test_the_pack_by_hand():
    # Two 20 x 10 bodies -> 21 x 11 with courtyards. 21 + 21 = 42 of the 48 mm
    # board: one shelf, 11 mm deep. A third needs 63 and starts a second: 22 mm.
    two = [("A", 20.0, 10.0), ("B", 10.0, 20.0)]
    assert bf.shelf_pack(two) == (pytest.approx(11.0), "")
    assert bf.shelf_pack(two + [("C", 20.0, 10.0)])[0] == pytest.approx(22.0)
    assert bf.shelf_pack([]) == (0.0, "")


def test_a_body_longer_than_the_board_is_wide_opens_its_shelf_first():
    """Two 50 x 5 terminals, a 30 x 10 and a 25 x 12 on a 40 mm board. With the
    courtyard they are 51 x 6, 51 x 6, 31 x 11 and 26 x 13; 51 does not go
    across a 40 mm board, so the terminals lie lengthwise -- 6 across, 51 deep.

    Deepest shelf first: the two terminals share one 51 mm shelf (6 + 6 = 12 of
    40), the 26 goes beside them (12 + 26 = 38), and the 31 opens an 11 mm shelf
    of its own. 51 + 11 = 62 mm.

    ⛔ Ordering on each body's SHORT side instead, which is what this did until
    2026-09-20, orders them 26, 31, 6, 6: the 26 opens a 13 mm shelf, the 31 an
    11 mm shelf, the first terminal lands on THAT shelf and deepens it to 51,
    and the second opens another 51. 13 + 51 + 51 = 115 mm, 53 mm of it pure
    fragmentation -- and on POWER top, whose three biggest bodies are the
    55.88 mm terminals J101 and J405 and J202's 58.42 mm inter-board PWR-OUT
    connector, that mechanism reported 254.93 mm on the 48 mm board for a
    195.45 mm pack (319.32 at the 42 mm width the board used to be)."""
    rects = [("J1", 50.0, 5.0), ("J2", 50.0, 5.0),
             ("X1", 30.0, 10.0), ("X2", 25.0, 12.0)]
    assert bf.shelf_pack(rects, 40.0) == (pytest.approx(62.0), "")


def test_a_pack_that_does_not_fit_is_a_plain_failure(capsys):
    # Eight 30 x 28 bodies -> 31 x 29. Two will not go side by side on a 48 mm
    # board (31 + 31 = 62), so each takes a 29 mm shelf: 232 mm. J301's 21 mm
    # will not fit beside any of them either (31 + 21 = 52), so it opens a 10 mm
    # shelf: 242 mm of a 219 mm board. Density is only (8 x 840 + 180) / 10316 =
    # 67 %, so it is the PACK that fails, and density must not excuse it.
    d = good()
    for i in range(8):
        d = d.with_part(part(f"X{i}", "OUTPUTS", 1.0, (30.0, 28.0)))
    drv = next(s for s in bf.area_budget(d) if (s.board, s.side) == ("OUTPUTS", "top"))
    assert drv.density == pytest.approx(6900 / 10316) and drv.density_ok
    assert drv.pack_mm == pytest.approx(242.0) and not drv.pack_ok
    code, out = run(capsys, d)
    assert code == 1
    assert "⛔ DOES NOT FIT (23 mm over)" in out
    assert any(p.startswith("pack: OUTPUTS top DOES NOT FIT") and "23 mm over" in p
               for p in bf.problems(d))


def test_a_body_wider_than_the_board_both_ways_cannot_be_placed(capsys):
    # 50 x 48 -> 51 x 49 with the courtyard: neither side goes across 48 mm.
    code, out = run(capsys, good().with_part(part("X1", "OUTPUTS", 1.0, (50.0, 48.0))))
    assert code == 1 and "X1 fits a 48 mm board in neither orientation" in out


def test_bottom_side_parts_are_packed_on_the_underside():
    top = good().with_part(part("C201", "POWER", 5.0, (25.0, 18.0)))
    under = good().with_part(part("C201", "POWER", 5.0, (25.0, 18.0), side="bottom"))
    rows_top = {(s.board, s.side): s for s in bf.area_budget(top)}
    rows_under = {(s.board, s.side): s for s in bf.area_budget(under)}
    assert ("OUTPUTS", "bottom") not in rows_top      # an empty side gets no row
    # POWER already has the brick underneath, so read the two arrangements
    # against each other: the 450 mm² body moves from the top row to the bottom.
    assert rows_under[("POWER", "bottom")].raw_mm2 \
        - rows_top[("POWER", "bottom")].raw_mm2 == pytest.approx(25.0 * 18.0)
    assert rows_top[("POWER", "top")].raw_mm2 \
        - rows_under[("POWER", "top")].raw_mm2 == pytest.approx(25.0 * 18.0)


def test_a_body_with_no_footprint_is_a_hole_in_the_budget_not_a_free_part(capsys):
    blind = good().replace_connector("J301", footprint_mm=(0.0, 0.0))
    code, out = run(capsys, blind)
    assert code == 1 and "J301" in out and "cannot see it" in out
    tall = good().with_part(part("Q101", "POWER", 4.5, (0.0, 0.0)))
    assert any("Q101" in p and "no footprint" in p for p in bf.problems(tall))
    passive = good().with_part(part("R1", "POWER", 0.6, (0.0, 0.0)))
    assert bf.problems(passive) == []                       # negligible, and counted:
    assert "1 part(s) carry no footprint" in bf.report(passive)


# --- plumbing --------------------------------------------------------------------------
def test_nothing_about_the_design_is_typed_in_the_tool():
    import inspect
    source = inspect.getsource(bf)
    for leaked in ("TPS4H160", "IXTP26P20P", "7448022010", "H_CHOKE", "MCP23017"):
        assert leaked not in source


def test_the_hyphenated_script_is_only_a_shim(monkeypatch):
    shim = Path(bf.__file__).with_name("board-fit.py")
    code = [ln for ln in shim.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]
    assert len(code) == 2
    monkeypatch.setattr(bf, "main", lambda: 7)
    with pytest.raises(SystemExit) as exit_:
        runpy.run_path(str(shim), run_name="__main__")
    assert exit_.value.code == 7


def test_the_real_netlist_runs_through_it(capsys):
    try:
        from tools import netlist
        design = netlist.current()
    except Exception as exc:                  # the netlist is its own test's job
        pytest.skip(f"tools.netlist does not build a Design: {type(exc).__name__}: {exc}")
    code = bf.main([], design)
    out = capsys.readouterr().out
    # 0 pass · 1 a budget fails · 2 over the ESTIMATED envelope (never a pass)
    assert code in (0, 1, 2)
    assert ("✅ PASS" in out) == (code == 0)
    assert ("⛔ FAIL" in out) == (code == 1)
    assert ("NOT A PASS" in out) == (code == 2)


def test_an_overrun_of_an_estimated_envelope_is_never_printed_as_a_pass(capsys, monkeypatch):
    """The tool once printed 'OVER by 7.1 mm' and then '✅ PASS', exit 0."""
    from tools import board_params as bp
    monkeypatch.setattr(bp, "CAVITY_MEASURED", False)
    tall = good().replace_part("L101", height_mm=30.0)      # 68.0 mm of 64
    code, out = run(capsys, tall)
    assert code == 2
    assert "✅ PASS" not in out and "NOT A PASS" in out and "OVER by 4.0 mm" in out


def test_an_overrun_past_the_raw_cavity_says_no_enclosure_can_absorb_it(capsys, monkeypatch):
    from tools import board_params as bp
    monkeypatch.setattr(bp, "CAVITY_MEASURED", False)
    taller = good().replace_part("L101", height_mm=34.0)    # 72.0 mm > the 70 mm cavity
    out = run(capsys, taller)[1]
    assert "exceeds even the RAW cavity estimate" in out
