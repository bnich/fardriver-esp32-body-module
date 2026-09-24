"""board_fit against small designs whose answer is known before it runs.

The tool's job is to say FAIL out loud and exit non-zero. So every test here
either drives `main()` and reads the exit code and the text a person would
see, or checks a figure that can be worked out on paper (41.84 x 242 mm board,
0.5 mm courtyard).
"""
import runpy
from dataclasses import replace
from pathlib import Path

import pytest

from tools import board_fit as bf
from tools.model import ConnPin, Connector, Design, Part, Standoff


def part(ref, board, height, footprint=(2.0, 1.25), *, side="top", confirmed=True,
         package="0805", mpn="X", lead=None):
    """A BODY with a height and a footprint: kind MECH, because the fit model
    reads neither kind nor value, and a resistor with no value is what the
    model refuses (M11). `lead` marks it through-hole (pins cross the board)."""
    return Part(ref, mpn, package, board, "MECH", ("1", "2"), height, confirmed,
                footprint, side=side, lead_mm=lead)


def conn(ref, board, height, footprint=(20.0, 9.0), *, confirmed=True, interface=None,
         leaves_box=None, overhang=0.0):
    return Connector(ref, board, f"{ref} harness", (ConnPin("1", ""),), height,
                     confirmed, footprint,
                     leaves_box=interface is None if leaves_box is None else leaves_box,
                     interface=interface, overhang_mm=overhang)


def with_connectors(design, *more):
    return replace(design, connectors=design.connectors + more)


def good() -> Design:
    """Closes on every budget: 52.0 mm of 94, sparse boards. The brick is under
    POWER on its floor seat, as in the design. Its two 7.0 mm connectors are
    internal, so it has no rows; the ROWS tests add harness headers to it."""
    return Design(
        parts=(part("L101", "POWER", 14.0, (22.0, 14.0), package="THT"),
               part("U201", "POWER", 12.7, (58.3, 37.2), package="brick",
                    side="bottom", lead=5.5),
               part("U401", "LOGIC", 3.1, (25.5, 18.0), package="module")),
        connectors=(conn("J301", "OUTPUTS", 7.0, leaves_box=False),
                    conn("J401", "LOGIC", 7.0, leaves_box=False)))


def run(capsys, design):
    code = bf.main([], design)
    return code, capsys.readouterr().out


# --- the clean design ------------------------------------------------------------
def test_a_design_that_closes_passes_and_says_the_requirement_is_not_final(capsys):
    """M18 is measured, so nothing here is provisional in the old sense. What is
    still open is the enclosure, and the first line has to say that it moves the
    REQUIREMENT and not the verdict."""
    code, out = run(capsys, good())
    assert code == 0
    assert "✅ PASS" in out and "⛔" not in out
    assert "THE REQUIREMENT IS NOT FINAL" in out
    assert "enclosure not chosen" in out and "M18 is measured" in out
    assert "NOT MEASURED" not in out
    assert bf.problems(good()) == []


# --- height ------------------------------------------------------------------------
def test_an_over_height_stack_fails(capsys):
    tall = good().replace_part("L101", height_mm=60.0)      # 52.0 + 46.0 = 98.0
    code, out = run(capsys, tall)
    assert code == 1
    assert "⛔ FAIL" in out and "OVER by 4.0 mm" in out
    assert "L101 60.0 up" in out                            # and says what did it


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


def test_the_height_block_names_the_standoff_that_sets_a_gap(capsys):
    """⭐ The gap POWER -> OUTPUTS has no connector across it since IO-20, so a
    person reading the report has to be told what does hold the boards apart --
    exactly as the FLOOR gap already says "U201 seats on the floor at 13.2,
    which sets it". A 20.0 mm pillar over parts that need 16.5 mm."""
    d = replace(good(), standoffs=(
        Standoff("M3X30", "C0", 4, 20.0, ("POWER", "OUTPUTS"), "sets", "fixture"),))
    code, out = run(capsys, d)
    assert code == 0
    line = next(ln for ln in out.splitlines() if "gap POWER -> OUTPUTS" in ln)
    assert "the M3X30 standoff stands 20.0, which sets it" in line
    assert " 20.0   " in line                        # ...and it IS the gap


def test_a_shimmed_standoff_is_reported_as_what_it_is_not_as_the_gap(capsys):
    """The other seating, and the report must not blur them: a standoff
    specified SHORT under a connector stop is named beside the gap, and the
    sentence says which of the two is in charge."""
    d = replace(
        with_connectors(good(),
                        conn("J308", "OUTPUTS", 8.5, (63.5, 5.0), interface="STACK"),
                        conn("J406", "LOGIC", 2.54, (63.5, 5.0), interface="STACK")),
        standoffs=(Standoff("TP-11", "C1", 4, 11.0, ("OUTPUTS", "LOGIC"),
                            "shimmed", "fixture"),))
    code, out = run(capsys, d)
    assert code == 0
    line = next(ln for ln in out.splitlines() if "gap OUTPUTS -> LOGIC" in ln)
    assert "the TP-11 standoff stands 11.0, shimmed short so the connectors set it" \
        in line
    assert "J308+J406 mates at 11.0" in line


def test_a_fourth_board_adds_two_gaps_and_an_empty_one_adds_none(capsys):
    """IO-26/IO-27: CTRL sits on top of LOGIC, so the report gains
    `gap LOGIC -> CTRL` -- set by the CTRL-STACK pair, 8.5 + 2.54 = 11.04 --
    and `gap CTRL -> LID`, set by CTRL's tallest top-side body.

    ⛔ AND THE OTHER HALF OF IT, which is why both directions are in one test:
    `good()` puts NOTHING on CTRL, and a board nothing is on is not a deck. Its
    report must be exactly what it was before CTRL joined STACK_ORDER --
    `LOGIC -> LID`, three boards in the AREA table, no CTRL row anywhere. Two
    clearances and a 1.6 mm PCB round an empty board is a stack nobody built."""
    code, out = run(capsys, good())
    assert code == 0 and "gap LOGIC -> LID" in out
    assert "CTRL" not in out, "an empty board is not a deck"
    assert [ln.split()[:2] for ln in out.splitlines() if ln.startswith("  POWER ")] \
        == [["POWER", "top"], ["POWER", "bottom"]]
    four = with_connectors(
        good(),
        conn("J411", "LOGIC", 8.5, (27.94, 5.0), interface="CTRL-STACK"),
        replace(conn("J501", "CTRL", 2.54, (27.94, 5.0), interface="CTRL-STACK"),
                side="bottom"),
        conn("J404", "CTRL", 8.3, (35.56, 12.2), leaves_box=True, overhang=8.8))
    code, out = run(capsys, four)
    assert code == 0, out
    assert "gap LOGIC -> LID" not in out
    up = next(ln for ln in out.splitlines() if "gap LOGIC -> CTRL" in ln)
    assert "J411+J501 mates at 11.0" in up
    lid = next(ln for ln in out.splitlines() if "CTRL -> LID" in ln)
    assert "J404 8.3 up" in lid and lid.split()[-4] == "9.3"
    # ...and the fourth board is budgeted like any other: its own AREA faces
    # and its own strip of connector edge.
    assert "  CTRL   top" in out and "  CTRL   bottom" in out
    assert next(ln for ln in out.splitlines()
                if ln.startswith("  CTRL ") and "of edge" in ln).split()[1] == "35.6"


def test_the_real_report_says_which_standoff_sets_the_power_to_outputs_gap(capsys):
    """The same thing on the real netlist, which is where it has to be true.
    The HEIGHT budget is what this reads; the exit code is the whole report's
    and is not asserted here -- the ROWS budget owns its own verdict."""
    from tools import netlist
    code, out = run(capsys, netlist.current())
    line = next(ln for ln in out.splitlines() if "gap POWER -> OUTPUTS" in ln)
    assert "the Shuntian M3X30 standoff stands 30.0, which sets it" in line
    assert "L102 22.0 up" in line                    # ...and what it has to clear


# --- plugs at the walls (MX-3) ------------------------------------------------------
def test_the_edge_a_board_s_headers_take_by_hand():
    """Two 20 mm headers 1 mm apart; room = the 9.6 mm plug + the 10 mm bend."""
    d = with_connectors(good(), conn("J302", "OUTPUTS", 7.0, overhang=9.6),
                        conn("J303", "OUTPUTS", 7.0, overhang=0.0))
    (e,) = bf.edge_budget(d)
    assert (e.board, e.headers, e.blockers) == ("OUTPUTS", ("J302", "J303"), ())
    assert (e.length_mm, e.room_mm) == (pytest.approx(41.0), pytest.approx(19.6))


def test_a_terminal_under_a_board_takes_the_edge_like_one_on_top(capsys):
    """A harness terminal is through-hole: its pins cross the board and stand
    proud of the other face, so the 5 V row under OUTPUTS cannot share a length
    of the edge with the 12 V row on top -- each one's pins would land in the
    other's body. Two 20 mm terminals, one per face, are ONE 41 mm strip. (The
    first placement, 2026-09-22, put J314 under J303-J305 and passed 16 checks;
    the picture showed it.)"""
    d = with_connectors(good(), conn("J302", "OUTPUTS", 7.0, overhang=9.6),
                        replace(conn("J314", "OUTPUTS", 7.0, overhang=8.9),
                                side="bottom"))
    (e,) = bf.edge_budget(d)
    assert e.headers == ("J302", "J314")
    assert e.length_mm == pytest.approx(41.0)
    assert e.room_mm == pytest.approx(19.6)      # the deeper plug of the two
    rows = run(capsys, d)[1].split("\nROWS")[1]
    assert "OUTPUTS   41.0 mm of edge" in rows and "J302 J314" in rows
    assert rows.count("OUTPUTS") == 1            # one strip, not a row per face


def test_an_underside_brick_too_deep_to_sit_behind_the_row_takes_the_edge():
    """`good()` puts the 58.3 x 37.2 quarter brick under POWER with through-hole
    pins. Behind a 9 mm row there are 41.84 - 9 = 32.84 mm; the brick is 37.2
    deep, so the row's pins would land in its case: it takes 58.3 mm of the
    edge, plus a gap. A 25.4 mm brick sits behind the row and takes nothing."""
    d = with_connectors(good(), conn("J101", "POWER", 7.0, (56.1, 9.0)))
    (e,) = bf.edge_budget(d)
    assert e.blockers == ("U201",)
    assert e.length_mm == pytest.approx(56.1 + 1.0 + 58.3)
    shallow = replace(d, parts=tuple(
        replace(x, footprint_mm=(50.8, 25.4)) if x.refdes == "U201" else x for x in d.parts))
    (e2,) = bf.edge_budget(shallow)
    assert e2.blockers == () and e2.length_mm == pytest.approx(56.1)


def test_a_brick_without_through_hole_pins_is_not_a_row_blocker():
    """The rule is about pins crossing the board: a body with no `lead_mm`
    (nothing typed as through-hole) is not counted, whatever its depth."""
    d = with_connectors(good(), conn("J101", "POWER", 7.0, (56.1, 9.0)))
    smd = replace(d, parts=tuple(
        replace(x, lead_mm=None) if x.refdes == "U201" else x for x in d.parts))
    (e,) = bf.edge_budget(smd)
    assert e.blockers == ()


def test_a_row_longer_than_its_board_fails():
    from tools import netlist
    d = netlist.current()
    long = d.replace_connector("J409", footprint_mm=(bf.bp.BOARD_L + 1.0, 9.2))
    assert any("row" in p and "LOGIC" in p for p in bf.face_verdicts(long))


def test_a_row_longer_than_its_board_is_a_plain_failure_not_a_caveat(capsys):
    """IO-14 made the board the design's own requirement, so a row that does not
    fit it is a failure whatever the cavity turns out to be. Two 130 mm headers
    1 mm apart take 261 mm of the 228 mm between a 242 mm board's M3 corners:
    33 mm over."""
    d = with_connectors(good(),
                        conn("J302", "OUTPUTS", 7.0, (130.0, 9.2), overhang=9.6),
                        conn("J303", "OUTPUTS", 7.0, (130.0, 9.2), overhang=9.6))
    (e,) = bf.edge_budget(d)
    assert e.length_mm == pytest.approx(261.0)
    code, out = run(capsys, d)
    assert code == 1 and "✅ PASS" not in out
    assert "row: OUTPUTS's 2 harness headers take 261 mm of the edge" in out
    assert "the edge is 228 mm between the M3 corners of a 242 mm board" in out
    assert "⛔ DOES NOT FIT (33 mm over)" in out


def test_a_row_that_fits_its_board_is_no_verdict_at_all(capsys):
    d = with_connectors(good(), conn("J302", "OUTPUTS", 7.0, (120.0, 9.2), overhang=9.6))
    assert bf.face_verdicts(d) == [] and run(capsys, d)[0] == 0


def test_an_unknown_height_fails_instead_of_vanishing():
    """A nan height is refused by the model at construction (H11: the report
    once printed `⛔ OVER by nan mm` and `✅ PASS` on one run), so no design
    the tool can be handed carries one."""
    with pytest.raises(ValueError, match="L101: height_mm=nan"):
        good().replace_part("L101", height_mm=float("nan"))


# --- the cavity the design REQUIRES (IO-14, M18) ---------------------------------------
# ⚠️ M18 is MEASURED: 260 x 70 x 100, and the design's 256.0 x 68.95 goes inside
# it. So the tests that need a FAILURE drive `measured_cavity` to supply a box
# that cannot hold the design; the real flags are left alone in the two that
# prove the pass and the gate.
def test_the_cavity_m18_measured_holds_the_design_and_the_tool_passes(capsys):
    """The real flags. The design requires 256.0 along x 68.95 across of the
    260 x 70 x 100 that was measured, so the report states the measurement and
    the tool passes -- on the arithmetic, not on a missing gate."""
    code, out = run(capsys, good())
    assert code == 0 and "✅ PASS" in out and "⛔" not in out
    assert "MEASURED (M18) -- the cavity is 260 x 70 x 100 mm" in out
    assert "the requirement fits inside it" in out
    assert "NOT MEASURED" not in out and "finding for M18" not in out
    assert bf.problems(good()) == []


def test_a_board_too_wide_for_the_measured_cavity_fails_the_tool(capsys, wider_board):
    """⚠️ THE MUTATION, at the tool's own exit code: the same design on a 45.0 mm
    board asks 71.65 mm of a 70.0 mm cavity and `board_fit` must exit 1. The
    enclosure is still undecided -- the real flag -- and that no longer buys a
    reprieve. ⚠️ 45.0 is only 3.16 mm past the 41.84 the envelope search chose,
    and 1.65 mm past what the box holds: that is how little width is left."""
    assert bf.main([], good()) == 0                  # 41.84 mm: it fits
    capsys.readouterr()
    wider_board(45.0)
    code, out = run(capsys, good())
    assert code == 1 and "⛔ FAIL" in out and "✅ PASS" not in out
    assert "board 45 x 242" in out
    assert "DOES NOT FIT the cavity that was measured" in out
    (problem,) = [p for p in bf.problems(good()) if p.startswith("cavity ")]
    assert "cavity across:" in problem and "OVER by 1.65 mm" in problem


def test_a_measured_cavity_too_short_for_the_design_fails(capsys, measured_cavity):
    """256.0 mm of board, wall and end clearance into a 250 mm box: 6 mm over."""
    measured_cavity(250.0, 80.0)
    code, out = run(capsys, good())
    assert code == 1 and "⛔ FAIL" in out and "✅ PASS" not in out
    (problem,) = [p for p in bf.problems(good()) if p.startswith("cavity ")]
    assert problem.startswith("cavity along:")                   # names the axis
    assert "requires 256.00 mm" in problem and "gives 250.00 mm" in problem
    assert "OVER by 6.00 mm" in problem                          # ...and by how much
    assert "the requirement EXCEEDS it along by 6.0 mm" in out
    assert "DOES NOT FIT the cavity that was measured" in out


def test_a_measured_cavity_too_narrow_for_the_design_fails(capsys, measured_cavity):
    """68.95 mm of board, walls, drop-in and plug room into a 61 mm box."""
    measured_cavity(270.0, 61.0)
    code, out = run(capsys, good())
    assert code == 1 and "⛔ FAIL" in out and "✅ PASS" not in out
    (problem,) = [p for p in bf.problems(good()) if p.startswith("cavity ")]
    assert problem.startswith("cavity across:")
    assert "requires 68.95 mm" in problem and "gives 61.00 mm" in problem
    assert "OVER by 7.95 mm" in problem
    assert "the requirement EXCEEDS it across by 7.9 mm" in out


def test_a_measured_cavity_short_on_both_axes_names_both(capsys, measured_cavity):
    measured_cavity(250.0, 61.0)
    axes = [p.split(":")[0] for p in bf.problems(good()) if p.startswith("cavity ")]
    assert axes == ["cavity along", "cavity across"]
    assert "EXCEEDS it along by 6.0 mm, across by 7.9 mm" in run(capsys, good())[1]


def test_the_same_overrun_would_be_a_finding_against_a_cavity_nobody_measured(
        capsys, measured_cavity, monkeypatch):
    """The pre-M18 world, which monkeypatching is the only way back into: the
    same 250 x 61 box, the same 6.0 and 7.9 mm of overrun, and the design still
    PASSES because nothing may fail against a guess. What the flag changes is
    the gate, not the arithmetic -- a tool that reported the same paragraph
    either way was the defect that put this pair of tests here."""
    measured_cavity(250.0, 61.0)
    monkeypatch.setattr(bf.bp, "CAVITY_MEASURED", False)    # back before M18
    code, out = run(capsys, good())
    assert code == 0 and "✅ PASS" in out
    assert "⬜ NOT MEASURED -- M18's estimate is 250 x 61 x 100 mm" in out
    assert "the requirement EXCEEDS it along by 6.0 mm, across by 7.9 mm" in out
    assert "finding for M18, not a failure of the design" in out
    assert not any(p.startswith("cavity ") for p in bf.problems(good()))


# --- area: density -------------------------------------------------------------------
def test_density_is_bodies_over_the_side_less_its_mounting_corners():
    rows = {(s.board, s.side): s for s in bf.area_budget(good())}
    brick = rows[("POWER", "bottom")]                       # the brick's own face
    assert brick.raw_mm2 == pytest.approx(58.3 * 37.2)
    assert bf.MOUNT_AREA == pytest.approx(4 * 7.0 * 7.0)     # 3.5 mm inset, both ways
    assert brick.density == pytest.approx(58.3 * 37.2 / (41.84 * 242 - 196))


def test_a_side_over_the_density_limit_fails(capsys):
    # Three 40 x 64 slabs beside J301's 20 x 9: 3 x 2560 + 180 = 7860 mm² of the
    # 41.84 x 242 - 196 = 9929.28 usable = 79 % > 75 %. Two of them is 5300 = 53 %.
    # Each slab lies lengthwise (41 across with its courtyard, 65 deep), so the
    # pack is 3 x 65 + J301's own 10 mm shelf = 205 mm and closes: it is DENSITY
    # that fails here, and the pack must not be what does it.
    d = good()
    for i in range(3):
        d = d.with_part(part(f"X{i}", "OUTPUTS", 1.0, (40.0, 64.0)))
    code, out = run(capsys, d)
    assert code == 1
    assert any(p.startswith("density: OUTPUTS top is 79%") for p in bf.problems(d))
    assert not any(p.startswith("pack") for p in bf.problems(d))
    two = good().with_part(part("X0", "OUTPUTS", 1.0, (40.0, 64.0))) \
        .with_part(part("X1", "OUTPUTS", 1.0, (40.0, 64.0)))
    assert not any(p.startswith("density") for p in bf.problems(two))   # 53 %


# --- area: the naive pack --------------------------------------------------------------
def test_the_pack_by_hand():
    # Two 17 x 10 bodies -> 18 x 11 with courtyards. 18 + 18 = 36 of the 40 mm
    # board: one shelf, 11 mm deep. A third needs 54 and starts a second: 22 mm.
    two = [("A", 17.0, 10.0), ("B", 10.0, 17.0)]
    assert bf.shelf_pack(two) == (pytest.approx(11.0), "")
    assert bf.shelf_pack(two + [("C", 17.0, 10.0)])[0] == pytest.approx(22.0)
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
    fragmentation -- and on the POWER top of 2026-09-20, whose three biggest
    bodies were the 55.88 mm terminals J101 and J405 and the 58.42 mm PWR-OUT
    bus J202 then was, that mechanism reported 321.57 mm against a 214.85 mm
    pack on the 39 mm board (254.93 against 195.45 on the 48 mm one before it).
    ⚠️ J202 is a 19.74 mm keyed header since IO-20; the mechanism is unchanged
    and these are the figures of the run that exposed it."""
    rects = [("J1", 50.0, 5.0), ("J2", 50.0, 5.0),
             ("X1", 30.0, 10.0), ("X2", 25.0, 12.0)]
    assert bf.shelf_pack(rects, 40.0) == (pytest.approx(62.0), "")


def test_a_pack_that_does_not_fit_is_a_plain_failure(capsys):
    # Twelve 21 x 21 bodies -> 22 x 22. Two will not go side by side on a
    # 41.84 mm board (22 + 22 = 44), so each takes a 22 mm shelf: 264 mm.
    # J301's 21 mm will not fit beside any of them either (22 + 21 = 43), so
    # it opens a 10 mm shelf: 274 mm of a 242 mm board. Density is only
    # (12 x 441 + 180) / 9929.28 = 55 %, so it is the PACK that fails, and
    # density must not excuse it.
    d = good()
    for i in range(12):
        d = d.with_part(part(f"X{i}", "OUTPUTS", 1.0, (21.0, 21.0)))
    drv = next(s for s in bf.area_budget(d) if (s.board, s.side) == ("OUTPUTS", "top"))
    assert drv.density == pytest.approx(5472 / 9929.28) and drv.density_ok
    assert drv.pack_mm == pytest.approx(274.0) and not drv.pack_ok
    code, out = run(capsys, d)
    assert code == 1
    assert "⛔ DOES NOT FIT (32 mm over)" in out
    assert any(p.startswith("pack: OUTPUTS top DOES NOT FIT") and "32 mm over" in p
               for p in bf.problems(d))


def test_a_body_wider_than_the_board_both_ways_cannot_be_placed(capsys):
    # 50 x 42 -> 51 x 43 with the courtyard: neither side goes across 41.84 mm.
    code, out = run(capsys, good().with_part(part("X1", "OUTPUTS", 1.0, (50.0, 42.0))))
    assert code == 1 and "X1 fits a 41.84 mm board in neither orientation" in out


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


def test_an_overrun_of_an_estimated_envelope_is_never_printed_as_a_pass(
        capsys, unmeasured_cavity):
    """The tool once printed 'OVER by 7.1 mm' and then '✅ PASS', exit 0. Exit 2
    is now reachable only through the fixture, M18 having been measured -- the
    regression is still worth a test, and so is the branch."""
    tall = good().replace_part("L101", height_mm=60.0)      # 98.0 mm of 94
    code, out = run(capsys, tall)
    assert code == 2
    assert "✅ PASS" not in out and "NOT A PASS" in out and "OVER by 4.0 mm" in out


def test_an_overrun_past_the_raw_cavity_says_no_enclosure_can_absorb_it(
        capsys, unmeasured_cavity):
    taller = good().replace_part("L101", height_mm=64.0)    # 102.0 mm > the 100 mm cavity
    out = run(capsys, taller)[1]
    assert "exceeds even the RAW cavity estimate" in out


# --- M18: the verdict TEXT agrees with the exit code, both ways -----------------------
def test_over_in_the_text_means_exit_1_and_exit_1_means_over_in_the_text(capsys):
    """`⛔ OVER` is the stack verdict word; `✅ PASS` / `⛔ FAIL` the tool's. The
    good design prints neither OVER nor FAIL and exits 0; a stack 4 mm over
    prints both and exits 1. Force either line and this fails."""
    code, out = run(capsys, good())
    assert ("⛔ OVER" in out) == (code == 1) == False
    assert "✅ PASS" in out and "⛔ FAIL" not in out
    code, out = run(capsys, good().replace_part("L101", height_mm=60.0))
    assert ("⛔ OVER" in out) == (code == 1) == True
    assert "⛔ FAIL" in out and "✅ PASS" not in out
    assert "OVER by 4.0 mm" in out


def _area_line(out: str, board: str, side: str) -> str:
    """The AREA table's row for one face: `board side bodies raw density verdict pack`."""
    table = out[out.index("AREA   density"):]
    return next(l for l in table.splitlines() if l.split()[:2] == [board, side])


def test_the_density_verdict_word_on_the_area_line_agrees_with_the_exit(capsys):
    """The other verdict word the same report prints, per face: `ok` under
    DENSITY_LIMIT, `⛔ FAIL` over it -- and only the second goes with exit 1.
    Force the word either way and this fails; the tool's own `⛔ FAIL -- N
    problem(s)` line is not what is read here."""
    code, out = run(capsys, good())
    assert code == 0
    assert _area_line(out, "OUTPUTS", "top").split()[5] == "ok"
    d = good()
    for i in range(40):
        d = d.with_part(part(f"R{i}", "OUTPUTS", 1.0, (20.0, 20.0)))
    code, out = run(capsys, d)
    line = _area_line(out, "OUTPUTS", "top")
    assert code == 1 and "⛔ FAIL" in line and "✅ PASS" not in out
    assert float(line.split()[4].rstrip("%")) > bf.DENSITY_LIMIT * 100


def test_the_real_design_s_four_rows_all_fit_and_the_report_says_by_how_much(capsys):
    """⭐ 2026-09-22, IO-26 END TO END. Both halves have landed: (1d) the
    controller row is a board of its own, so POWER's strip is J101 plus the
    quarter brick it cannot sit in front of; (2a) the 5 V block and J314 left
    OUTPUTS for CTRL, so the 12 V row has the OUTPUTS edge to itself.

    The four edges, against 228.0 mm between the M3 corners:
      POWER    J101 55.88 + gap 1.0 + U201 58.30 (under it) = 115.18, 50.5 %
      OUTPUTS  the 12 V row alone                           = 220.28, 96.6 %
      LOGIC    the INPUTS row                               = 185.94, 81.6 %
      CTRL     the controller row 140.16 + gap 1.0 + J314 38.40 = 179.56, 78.8 %

    ⛔ It exited 1 on OUTPUTS' 259.68 mm strip from the day IO-26 found that a
    through-hole terminal takes both faces until 2a landed. A 1 here again is a
    real overrun, not a known one.

    Protects: that this tool's verdict on the REAL design is asserted, not just
    its verdict on a fixture -- which is what let 259.68 mm of row sit behind a
    green gate until a picture showed it."""
    from tools import netlist
    over = {e.board: (e.over_mm, e.blockers) for e in bf.edge_budget(netlist.current())}
    assert set(over) == {"POWER", "OUTPUTS", "LOGIC", "CTRL"}
    assert over["POWER"][0] < 0 and over["POWER"][1] == ("U201",)
    assert over["OUTPUTS"][0] < 0 and over["OUTPUTS"][1] == ()
    assert over["LOGIC"][0] < 0 and over["CTRL"][0] < 0
    assert all(b == () for k, (_, b) in over.items() if k != "POWER")
    code, out = run(capsys, netlist.current())
    assert code == 0
    assert "⛔ DOES NOT FIT" not in out and "✅ PASS" in out
    assert bf.problems(netlist.current()) == []
    # ⚠️ Fires: put J314 back under OUTPUTS and the strip overruns again, on
    # the one board that has no room for it.
    bad = netlist.current().replace_connector("J314", board="OUTPUTS",
                                              side="bottom")
    errs = bf.problems(bad)
    assert len(errs) == 1 and errs[0].startswith("row: OUTPUTS"), errs
    assert "260 mm of the edge" in errs[0]
