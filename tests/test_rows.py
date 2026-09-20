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
from tools.model import ConnPin

D = netlist.current()

#: Which FACE each harness connector's row is: (board, side).  The 5 V row is
#: the underside of OUTPUTS (IO-7), which is why this is a face and not a board.
ROW_FACE = {
    # CTRL: the pack plug and the controller leads
    "J101": ("POWER", "top"), "J309": ("POWER", "top"),
    "J404": ("POWER", "top"), "J405": ("POWER", "top"),
    "J310": ("POWER", "top"),
    # 12 V: every lamp, horn, fan and buzzer channel, and the four 12 V aux
    "J301": ("OUTPUTS", "top"), "J302": ("OUTPUTS", "top"),
    "J303": ("OUTPUTS", "top"), "J304": ("OUTPUTS", "top"),
    "J305": ("OUTPUTS", "top"), "J313": ("OUTPUTS", "top"),
    # 5 V: the four 5 V aux outputs, under OUTPUTS
    "J314": ("OUTPUTS", "bottom"),
    # INPUTS: the pods, the levers and the general inputs
    "J402": ("LOGIC", "top"), "J403": ("LOGIC", "top"),
    "J306": ("LOGIC", "top"), "J409": ("LOGIC", "top"),
    "J410": ("LOGIC", "top"),
}
#: The 3.81 mm pitch is shared by two rows on purpose, so the SIZES must not
#: be: a plug of one row seats in any header of its pitch at least its size.
TWELVE_VOLT_ROW = {"J301", "J302", "J303", "J304", "J305", "J313"}
INPUT_ROW = {"J306", "J402", "J403", "J409", "J410"}

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
    assert {c.refdes for c in harness()} == set(ROW_FACE), (
        "a harness connector this file does not place in a row")
    for ref, (board, side) in ROW_FACE.items():
        assert (D.connector(ref).board, D.connector(ref).side) == (board, side), ref


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
    """The 3.50 mm pitch belongs to whatever carries AUX5V -- J314 and nothing
    else -- so an input terminal that took it would let a 12 V or an input
    plug seat where a 5 V device belongs."""
    bad = D.replace_connector("J409", pitch_mm=FIVE_VOLT_PITCH)
    assert any("J409" in p and "5 V row" in p for p in pitch_problems(bad))


def test_the_controller_row_is_the_only_one_that_leaves_power():
    """IO-5: the pack plug and every FarDriver and display lead, and nothing
    else, leave the box from the bottom board."""
    assert {c.refdes for c in harness() if c.board == "POWER"} == \
        {r for r, (b, _) in ROW_FACE.items() if b == "POWER"}
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
        ("POWER", "top"), ("OUTPUTS", "top"), ("OUTPUTS", "bottom"),
        ("LOGIC", "top")]
    placed = [r for e in rows for r in e.headers]
    assert sorted(placed) == sorted(ROW_FACE), "a header in two rows or none"
    for e in rows:
        assert set(e.headers) == {r for r, f in ROW_FACE.items()
                                  if f == (e.board, e.side)}


def test_every_class_a_network_sits_at_its_own_terminal():
    """The conditioning belongs on the board the contact lands on, so only the
    conditioned signal crosses an interface (plan §4). `netlist.current()`
    refuses a design where it does not."""
    assert netlist.class_a_problems(D) == []


def test_a_class_a_network_left_on_another_board_is_refused():
    """The guard is inside `_class_a_parts`' own class, not at a call site: it
    is the default board that is checked, so an input terminal put on another
    board cannot silently take its conditioning an interface away."""
    bad = D.replace_part("R409", board="OUTPUTS")
    problems = netlist.class_a_problems(bad)
    assert any("R409" in p and "OUTPUTS" in p and "IN07_BOOST_BTN_WIRE" in p
               for p in problems), problems
    # ...and every other network is still clean, so the message names the one.
    assert len(problems) == 1


def shared_sizes(d):
    """(pitch, positions) that a 12 V terminal and an input terminal both use.

    They share the 3.81 mm pitch deliberately -- a mismate there is an output
    into its own current limit, or 3.3 V through 1 kΩ into a lamp, and neither
    hurts -- so what keeps the two rows apart is SIZE. A plug seats in any
    header of its pitch at least its own size, so an eight-way 12 V terminal
    would seat in either general-input header and put 12 V on contacts wired
    for dry contacts to ground.
    """
    sizes = {name: {(d.connector(r).pitch_mm, len(d.connector(r).pins))
                    for r in row}
             for name, row in (("12 V", TWELVE_VOLT_ROW), ("inputs", INPUT_ROW))}
    return sizes["12 V"] & sizes["inputs"]


def test_no_size_is_shared_between_the_12_v_row_and_the_inputs_row():
    assert shared_sizes(D) == set()


def test_a_12_v_terminal_the_size_of_an_input_terminal_is_caught():
    """J313 is SEVEN-way for this reason: 3.81 × 8 is what J409 and J410 are."""
    j = D.connector("J313")
    bad = D.replace_connector("J313", pins=j.pins + (ConnPin("8", "GND"),))
    assert shared_sizes(bad) == {(3.81, 8)}


def test_a_row_is_as_long_as_its_headers_and_the_gaps_between_them():
    """The one figure the fit depends on, by hand for one row: the inputs row is
    J306 (3 × 3.81 + 10.48), J402 (9), J403 (6), J409 and J410 (8 each), with
    HEADER_GAP between neighbours."""
    e = next(x for x in bf.edge_budget(D) if x.board == "LOGIC")
    by_hand = sum(n * 3.81 + 10.48 for n in (3, 9, 6, 8, 8)) + 4 * bf.HEADER_GAP
    assert e.length_mm == pytest.approx(by_hand)
