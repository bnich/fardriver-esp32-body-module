"""board_fit against small designs whose answer is known before it runs.

The tool's job is to say FAIL out loud and exit non-zero. So every test here
either drives `main()` and reads the exit code and the text a person would
see, or checks a figure that can be worked out on paper (42 x 186 mm board,
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
    """Closes on every budget: 61.6 mm of 64, sparse boards. Its two 7.0 mm
    connectors are internal: no harness plug fits the envelope's walls as
    estimated (see the PLUGS tests)."""
    return Design(
        parts=(part("L101", "HVIN", 14.0, (22.0, 14.0), package="THT"),
               part("U201", "CONV", 12.7, (58.3, 37.2), package="brick"),
               part("U401", "BRAIN", 3.1, (25.5, 18.0), package="module")),
        connectors=(conn("J301", "DRV", 7.0, leaves_box=False),
                    conn("J401", "BRAIN", 7.0, leaves_box=False)))


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
    tall = good().replace_part("L101", height_mm=22.0)      # 61.6 + 8.0 = 69.6
    code, out = run(capsys, tall)
    assert code == 1
    assert "⛔ FAIL" in out and "OVER by 5.6 mm" in out
    assert "L101 22.0 up" in out                            # and says what did it


def test_an_unconfirmed_height_is_reported_and_starred_when_it_sets_a_gap(capsys):
    d = good().replace_part("L101", height_confirmed=False) \
        .with_part(part("R101", "HVIN", 0.6, confirmed=False))
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
        d = d.with_part(part(ref, "DRV", 0.6, confirmed=False, mpn="R-1k"))
    out = run(capsys, d)[1]
    assert "UNCONFIRMED HEIGHTS   3 not read" in out
    assert any(ln.endswith("R-1k: R1 R2 R3") for ln in out.splitlines())


def test_no_unconfirmed_section_when_every_height_is_confirmed(capsys):
    assert "UNCONFIRMED" not in run(capsys, good())[1]


def test_a_bottom_side_part_taller_than_the_gap_below_it_fails(capsys):
    # A chosen (confirmed) STACK pair sets DRV->BRAIN at 8.5 + 2.54 = 11.04 mm.
    d = with_connectors(
        good(),
        conn("J308", "DRV", 8.5, (63.5, 5.0), interface="STACK"),
        conn("J406", "BRAIN", 2.54, (63.5, 5.0), interface="STACK"))
    assert bf.main([], d) == 0
    d = d.with_part(part("C450", "BRAIN", 12.0, (10.0, 10.0), side="bottom"))
    code, out = run(capsys, d)
    assert code == 1
    assert "C450 hangs 12.0 mm under BRAIN" in out
    assert "J308+J406" in out and "11.0" in out


# --- plugs at the walls (MX-3) ------------------------------------------------------
def test_the_edge_a_board_s_headers_take_by_hand():
    """Two 20 mm headers 1 mm apart; room = the 9.6 mm plug + the 10 mm bend."""
    d = with_connectors(good(), conn("J302", "DRV", 7.0, overhang=9.6),
                        conn("J303", "DRV", 7.0, overhang=0.0))
    (e,) = bf.edge_budget(d)
    assert (e.board, e.headers) == ("DRV", ("J302", "J303"))
    assert (e.length_mm, e.room_mm) == (pytest.approx(41.0), pytest.approx(19.6))


def test_a_plug_no_wall_has_room_for_is_never_printed_as_a_pass(capsys):
    """The walls leave 4 mm at each end and 1 mm at each side: a mated plug
    stands 9.6 mm proud and its wire must bend after it."""
    d = with_connectors(good(), conn("J302", "DRV", 7.0, overhang=9.6))
    code, out = run(capsys, d)
    assert code == 2 and "NOT A PASS" in out and "✅ PASS" not in out
    assert "DRV's 1 harness headers take 20 mm of edge and need 19.6 mm" in out


def test_a_plug_no_wall_has_room_for_fails_once_the_envelope_is_a_fact(capsys, binding_envelope):
    d = with_connectors(good(), conn("J302", "DRV", 7.0, overhang=9.6))
    code, out = run(capsys, d)
    assert code == 1 and "plugs: DRV" in out


def test_walls_with_room_let_the_plugs_through(capsys, monkeypatch):
    from tools import board_params as bp
    monkeypatch.setattr(bp, "END_ALLOWANCE", 20.0)
    d = with_connectors(good(), conn("J302", "DRV", 7.0, overhang=9.6))
    assert bf.edge_verdicts(d) == [] and run(capsys, d)[0] == 0


def test_an_unknown_height_fails_instead_of_vanishing(capsys):
    code, out = run(capsys, good().replace_part("L101", height_mm=float("nan")))
    assert code == 1 and "height: L101" in out


# --- area: density -------------------------------------------------------------------
def test_density_is_bodies_over_the_side_less_its_mounting_corners():
    rows = {(s.board, s.side): s for s in bf.area_budget(good())}
    conv = rows[("CONV", "top")]
    assert conv.raw_mm2 == pytest.approx(58.3 * 37.2)
    assert bf.MOUNT_AREA == pytest.approx(4 * 7.0 * 7.0)     # 3.5 mm inset, both ways
    assert conv.density == pytest.approx(58.3 * 37.2 / (42 * 186 - 196))


def test_a_side_over_the_density_limit_fails(capsys):
    # Three 40 x 50 slabs: 6000 mm2 of 7616 usable = 79 % > 75 %.
    d = good()
    for i in range(3):
        d = d.with_part(part(f"X{i}", "DRV", 1.0, (40.0, 50.0)))
    code, out = run(capsys, d)
    assert code == 1
    assert any(p.startswith("density: DRV top is 8") for p in bf.problems(d))
    two = good().with_part(part("X0", "DRV", 1.0, (40.0, 50.0))) \
        .with_part(part("X1", "DRV", 1.0, (40.0, 50.0)))
    assert not any(p.startswith("density") for p in bf.problems(two))   # 55 %


# --- area: the naive pack --------------------------------------------------------------
def test_the_pack_by_hand():
    # Two 20 x 10 bodies -> 21 x 11 with courtyards. 21 + 21 = 42 fills one row
    # of a 42 mm board exactly: 11 mm long. A third starts a second row: 22 mm.
    two = [("A", 20.0, 10.0), ("B", 10.0, 20.0)]
    assert bf.shelf_pack(two) == (pytest.approx(11.0), "")
    assert bf.shelf_pack(two + [("C", 20.0, 10.0)])[0] == pytest.approx(22.0)
    assert bf.shelf_pack([]) == (0.0, "")


def test_a_pack_that_does_not_fit_is_a_plain_failure(capsys):
    # Eight 25 x 24 bodies. Two will not go side by side on a 42 mm board
    # (26 + 26), so each takes a 25 mm row: 200 mm, plus J301's 10 mm row, of a
    # 186 mm board. Density is only (8 x 600 + 180) / 7616 = 65 %, so it is the
    # PACK that fails, and the density figure must not be allowed to excuse it.
    d = good()
    for i in range(8):
        d = d.with_part(part(f"X{i}", "DRV", 1.0, (25.0, 24.0)))
    drv = next(s for s in bf.area_budget(d) if (s.board, s.side) == ("DRV", "top"))
    assert drv.density == pytest.approx(4980 / 7616) and drv.density_ok
    assert drv.pack_mm == pytest.approx(210.0) and not drv.pack_ok
    code, out = run(capsys, d)
    assert code == 1
    assert "⛔ DOES NOT FIT (24 mm over)" in out
    assert any(p.startswith("pack: DRV top DOES NOT FIT") and "24 mm over" in p
               for p in bf.problems(d))


def test_a_body_wider_than_the_board_both_ways_cannot_be_placed(capsys):
    code, out = run(capsys, good().with_part(part("X1", "DRV", 1.0, (45.0, 50.0))))
    assert code == 1 and "X1 fits a 42 mm board in neither orientation" in out


def test_bottom_side_parts_are_packed_on_the_underside():
    top = good().with_part(part("C201", "CONV", 5.0, (25.0, 18.0)))
    under = good().with_part(part("C201", "CONV", 5.0, (25.0, 18.0), side="bottom"))
    rows_top = {(s.board, s.side): s for s in bf.area_budget(top)}
    rows_under = {(s.board, s.side): s for s in bf.area_budget(under)}
    assert ("CONV", "bottom") not in rows_top
    assert rows_under[("CONV", "bottom")].raw_mm2 == pytest.approx(25.0 * 18.0)
    assert rows_under[("CONV", "top")].raw_mm2 == \
        rows_top[("CONV", "top")].raw_mm2 - 25.0 * 18.0


def test_a_body_with_no_footprint_is_a_hole_in_the_budget_not_a_free_part(capsys):
    blind = good().replace_connector("J301", footprint_mm=(0.0, 0.0))
    code, out = run(capsys, blind)
    assert code == 1 and "J301" in out and "cannot see it" in out
    tall = good().with_part(part("Q101", "HVIN", 4.5, (0.0, 0.0)))
    assert any("Q101" in p and "no footprint" in p for p in bf.problems(tall))
    passive = good().with_part(part("R1", "HVIN", 0.6, (0.0, 0.0)))
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
    tall = good().replace_part("L101", height_mm=22.0)      # 69.6 mm of 64
    code, out = run(capsys, tall)
    assert code == 2
    assert "✅ PASS" not in out and "NOT A PASS" in out and "OVER by 5.6 mm" in out


def test_an_overrun_past_the_raw_cavity_says_no_enclosure_can_absorb_it(capsys, monkeypatch):
    from tools import board_params as bp
    monkeypatch.setattr(bp, "CAVITY_MEASURED", False)
    taller = good().replace_part("L101", height_mm=24.0)    # 71.6 mm > the 70 mm cavity
    out = run(capsys, taller)[1]
    assert "exceeds even the RAW cavity estimate" in out
