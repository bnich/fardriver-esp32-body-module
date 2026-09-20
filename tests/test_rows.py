"""IO-4..IO-6: every harness connector sits in one of four rows on one face of
the box, one row per board edge, and each dangerous group has a pitch nothing
else uses (design spec §5).

The rows, bottom to top: CTRL on POWER (the pack plug and every FarDriver and
display lead), 12 V on OUTPUTS' top face, 5 V under OUTPUTS (Task 5 adds it),
INPUTS on LOGIC.  A mismate is dangerous in only three ways once the brake is
plain I/O -- a 5 V device in a 12 V header, a FarDriver lead in any other
header, and the pack plug anywhere but its own -- so those three groups own a
pitch, and everything else shares 3.81 mm, where a mismate is harmless.
"""
import pytest

from tools import board_fit as bf, netlist

D = netlist.current()

#: Which board's edge each harness connector's row is.
ROW_BOARD = {
    # CTRL: the pack plug and the controller leads
    "J101": "POWER", "J309": "POWER", "J404": "POWER", "J405": "POWER",
    "J310": "POWER",
    # 12 V: every lamp, horn, fan and buzzer channel
    "J301": "OUTPUTS", "J302": "OUTPUTS", "J303": "OUTPUTS", "J304": "OUTPUTS",
    "J305": "OUTPUTS",
    # INPUTS: the pods, the levers and the general inputs
    "J402": "LOGIC", "J403": "LOGIC", "J306": "LOGIC", "J409": "LOGIC",
    "J410": "LOGIC",
}

#: A pitch owned by ONE group: nothing outside it may use that pitch, because a
#: plug seats in any header of its own pitch that is at least its size.
#:   7.62  the pack plug alone (84 V)
#:   5.08  the FarDriver and display leads alone -- 12 V back-fed into the
#:         controller's 3.3 V logic is the mismate that destroys something
#:   3.50  the 5 V row alone (Task 5): 12 V into a 5 V device
#: 3.81 mm is deliberately NOT exclusive: it carries the 12 V outputs and the
#: inputs, where the worst mismate is an output into its own current limit or
#: 3.3 V through 1 kΩ into a lamp.
EXCLUSIVE_PITCH = {7.62: {"J101"}, 5.08: {"J309", "J404", "J405", "J310"}}
FIVE_VOLT_PITCH = 3.50


def harness(d=D):
    """Every connector whose wires leave the box, PARKED ONES INCLUDED: a
    parked terminal keeps its footprint, so its size and pitch are already
    decided and a plug pushed into a fitted header of that size still seats."""
    return [c for c in d.connectors if c.leaves_box]


def pitch_problems(d):
    """Every use of an exclusive pitch by something that does not own it."""
    out = []
    for pitch, owners in EXCLUSIVE_PITCH.items():
        users = {c.refdes for c in harness(d) if c.pitch_mm == pitch}
        if users - owners:
            out.append(f"{sorted(users - owners)} on the {pitch} mm pitch "
                       f"owned by {sorted(owners)}")
    five_v = {c.refdes for c in harness(d)
              if any(cp.net.startswith("AUX5V") for cp in c.pins)}
    for c in harness(d):
        if c.pitch_mm == FIVE_VOLT_PITCH and c.refdes not in five_v:
            out.append(f"{c.refdes} is on the {FIVE_VOLT_PITCH} mm pitch owned "
                       f"by the 5 V row")
    return out


def test_every_harness_connector_is_on_its_row_board():
    assert {c.refdes for c in harness()} == set(ROW_BOARD), (
        "a harness connector this file does not place in a row")
    for ref, board in ROW_BOARD.items():
        assert D.connector(ref).board == board, ref


def test_the_pitches_follow_the_rows():
    assert pitch_problems(D) == []


def test_a_fardriver_pitch_on_a_lamp_header_is_caught():
    """12 V into the controller's 3.3 V logic: the mismate the 5.08 row exists
    to make impossible."""
    bad = D.replace_connector("J304", pitch_mm=5.08)
    assert any("J304" in p for p in pitch_problems(bad))


def test_the_pack_pitch_on_any_other_header_is_caught():
    bad = D.replace_connector("J301", pitch_mm=7.62)
    assert any("J301" in p for p in pitch_problems(bad))


def test_the_five_volt_pitch_on_an_input_terminal_is_caught():
    """Nothing carries AUX5V yet (Task 5), so the 3.50 mm pitch is owned by a
    row that does not exist: anything using it fires, which is what keeps it
    free until the 5 V outputs arrive."""
    bad = D.replace_connector("J409", pitch_mm=FIVE_VOLT_PITCH)
    assert any("J409" in p and "5 V row" in p for p in pitch_problems(bad))


def test_the_controller_row_is_the_only_one_that_leaves_power():
    """IO-5: the pack plug and every FarDriver and display lead, and nothing
    else, leave the box from the bottom board."""
    assert {c.refdes for c in harness() if c.board == "POWER"} == \
        {r for r, b in ROW_BOARD.items() if b == "POWER"}
    for ref in ("J309", "J404", "J405", "J310"):
        assert D.connector(ref).pitch_mm == 5.08, ref


def test_the_levers_are_a_three_way_input_terminal():
    j = D.connector("J306")
    assert (j.board, j.pitch_mm) == ("LOGIC", 3.81)
    assert [cp.net for cp in j.pins] == ["LEVER_L", "GND", "LEVER_R"]


def test_the_free_inputs_are_two_fitted_harness_terminals():
    """13 free inputs and the boost button, each with a return, over two 8-way
    terminals: the 16-way header has 2 in stock at JLC and these are fitted."""
    a, b = D.connector("J409"), D.connector("J410")
    nets = []
    for j in (a, b):
        assert j.leaves_box and not j.dnp and not j.parked, j.refdes
        assert (j.pitch_mm, len(j.pins)) == (3.81, 8), j.refdes
        nets += [cp.net for cp in j.pins]
    assert nets[0] == nets[-1] == "GND" and nets.count("GND") == 2
    assert nets[1] == "IN07_BOOST_BTN_WIRE"
    assert sum(n.startswith("SPARE_") for n in nets) == 13


def test_each_row_is_one_face_of_one_board():
    """IO-6: the rows stack on ONE face of the box, each row the edge of one
    board -- so the edge budget is grouped by (board, side), and every harness
    connector belongs to exactly one row. Read off the design, not restated:
    Task 5 hangs the 5 V row under OUTPUTS and it becomes a row here by itself."""
    rows = bf.edge_budget(D)
    assert [(e.board, e.side) for e in rows] == [
        ("POWER", "top"), ("OUTPUTS", "top"), ("LOGIC", "top")]
    placed = [r for e in rows for r in e.headers]
    assert sorted(placed) == sorted(ROW_BOARD), "a header in two rows or none"
    for e in rows:
        assert set(e.headers) == {r for r, b in ROW_BOARD.items() if b == e.board}


def test_a_row_is_as_long_as_its_headers_and_the_gaps_between_them():
    """The one figure the fit depends on, by hand for one row: the inputs row is
    J306 (3 × 3.81 + 10.48), J402 (9), J403 (6), J409 and J410 (8 each), with
    HEADER_GAP between neighbours."""
    e = next(x for x in bf.edge_budget(D) if x.board == "LOGIC")
    by_hand = sum(n * 3.81 + 10.48 for n in (3, 9, 6, 8, 8)) + 4 * bf.HEADER_GAP
    assert e.length_mm == pytest.approx(by_hand)
