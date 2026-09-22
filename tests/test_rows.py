"""IO-4..IO-6: every harness connector sits in one of four rows on one face of
the box, one row per board edge, and each dangerous group has a pitch nothing
else uses (design spec §5).

The rows, bottom to top: the PACK plug alone on POWER, 12 V on OUTPUTS' top
face, INPUTS on LOGIC, and on CTRL both the CONTROLLER row -- every FarDriver
and display lead, on a board of its own since IO-26 -- and the 5 V row, which
followed its block up there at IO-26 2a.
A mismate is dangerous in only three ways once the brake is
plain I/O -- a 5 V device in a 12 V header, a FarDriver lead in any other
header, and the pack plug anywhere but its own -- so those three groups own a
pitch, and everything else shares 3.81 mm, where a mismate is harmless.
"""
import pytest

from tools import board_fit as bf, netlist
from tools.model import ConnPin

D = netlist.current()

#: Which FACE each harness connector's row is: (board, side).  It is a FACE and
#: not a board because the 5 V row spent IO-7 on the underside of OUTPUTS; it
#: stands on CTRL's top face now (IO-26 2a), and the face is still what the
#: pitch rule and the edge budget are read against.
ROW_FACE = {
    # PACK: the 84 V plug, alone on POWER since the controller row left (IO-26)
    "J101": ("POWER", "top"),
    # 12 V: every lamp, horn, fan and buzzer channel, and the four 12 V aux
    "J301": ("OUTPUTS", "top"), "J302": ("OUTPUTS", "top"),
    "J303": ("OUTPUTS", "top"), "J304": ("OUTPUTS", "top"),
    "J305": ("OUTPUTS", "top"), "J313": ("OUTPUTS", "top"),
    # INPUTS: the pods, the levers and the general inputs
    "J402": ("LOGIC", "top"), "J403": ("LOGIC", "top"),
    "J306": ("LOGIC", "top"), "J409": ("LOGIC", "top"),
    "J410": ("LOGIC", "top"),
    # CONTROLLER: every FarDriver and display lead, on the fourth board (IO-26)
    "J309": ("CTRL", "top"), "J404": ("CTRL", "top"),
    "J310": ("CTRL", "top"), "J405": ("CTRL", "top"),
    # 5 V: the four 5 V aux outputs, in line with the controller row on CTRL's
    # top face since the block moved there (IO-26 2a)
    "J314": ("CTRL", "top"),
}
#: The 3.81 mm pitch is shared by two rows on purpose, so the SIZES must not
#: be: a plug of one row seats in any header of its pitch at least its size.
#: Which headers those rows hold is READ OFF `board_fit.edge_budget`, never
#: typed here: the 12 V row is the face on top of OUTPUTS and the INPUTS row
#: the face on top of LOGIC (IO-6), so a terminal added to either face is in
#: the size check the moment it is in the row.
TWELVE_VOLT_FACE = ("OUTPUTS", "top")
INPUT_FACE = ("LOGIC", "top")

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


def test_the_pack_plug_is_the_only_wire_that_leaves_power():
    """⭐ IO-26: the controller row was the rest of POWER's edge and it is a
    board of its own now, so ONE terminal leaves the box from the bottom
    board -- and it is the 84 V one, which is the only wire that could not
    have moved with it (BD-2: pack voltage stays on POWER)."""
    assert {c.refdes for c in harness() if c.board == "POWER"} == {"J101"}
    assert {c.refdes for c in harness() if c.board == "CTRL"} == \
        {r for r, (b, _) in ROW_FACE.items() if b == "CTRL"} == \
        {"J309", "J404", "J405", "J310", "J314"}
    for ref in ("J309", "J404", "J405", "J310"):
        assert D.connector(ref).pitch_mm == 5.08, ref
    # ⚠️ J314 shares the board and not the pitch: two rows, two hazard
    # classes, one edge.
    assert D.connector("J314").pitch_mm == FIVE_VOLT_PITCH
    # ...and nothing on the controller board touches pack voltage.
    for n in D.nets:
        if n.domain == "84V":
            assert "CTRL" not in {D.board_of(r) for r, _ in n.pins}, n.name


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


def test_each_row_is_one_edge_of_one_board():
    """IO-6: the rows stack on ONE face of the box, each row the edge of one
    board -- so the edge budget is grouped by board, and every harness
    connector belongs to exactly one edge. Read off the design, not restated.
    ⭐ A ROW IS NOT A BOARD, and CTRL is where that shows: it carries TWO rows
    on one edge, the controller row at 5.08 mm and the 5 V row at 3.50 mm,
    because a row is a hazard class and an edge is a piece of board. The 5 V
    row spent IO-7 under OUTPUTS and IO-26 2a on top of CTRL, and neither
    move changed a word of the pitch rule."""
    rows = bf.edge_budget(D)
    assert [e.board for e in rows] == ["POWER", "OUTPUTS", "LOGIC", "CTRL"]
    placed = [r for e in rows for r in e.headers]
    assert sorted(placed) == sorted(ROW_FACE), "a header in two edges or none"
    for e in rows:
        assert set(e.headers) == {r for r, (b, _) in ROW_FACE.items() if b == e.board}
    assert D.connector("J314").side == "top" and "J314" in rows[3].headers
    assert {D.connector(r).pitch_mm for r in rows[3].headers} == {5.08, 3.50}


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


def row_sizes(d, face):
    """{refdes: (pitch, positions)} of every harness header in the row on
    `face`, read off `edge_budget` -- the same grouping board_fit measures."""
    board, side = face
    edge = next((e for e in bf.edge_budget(d) if e.board == board), None)
    if edge is None:
        return {}
    return {r: (d.connector(r).pitch_mm, len(d.connector(r).pins))
            for r in edge.headers if d.connector(r).side == side}


def shared_sizes(d):
    """(pitch, positions) that a 12 V terminal and an input terminal both use.

    ⚠️ What this checks is EXACT-SIZE equality, and that is all it claims. A
    smaller plug does seat, offset, in a larger header of its pitch -- a
    seven-way 12 V plug still fits an eight-way input header, and the row's
    4-ways fit several of them -- so this is not a proof that no plug of one
    row enters a header of the other. The argument that makes exact size worth
    checking is `tests/test_interconnect.py`'s: with EVERY plug seated, each
    one is forced into a header of its own size, so a connector whose size
    nothing shares cannot be swapped without leaving a plug in the hand.
    What makes the weaker guarantee acceptable here is that 3.81 mm is a
    SHARED pitch on purpose (see EXCLUSIVE_PITCH above): a 12 V plug in an
    input header drives an output into its own current limit, which reports
    the fault, and an input plug in a 12 V header meets 3.3 V through 1 kΩ.
    Neither hurts, which is exactly why the dangerous groups got pitches of
    their own instead.
    """
    return (set(row_sizes(d, TWELVE_VOLT_FACE).values())
            & set(row_sizes(d, INPUT_FACE).values()))


def repeated_sizes(d):
    """{(pitch, positions): (refdes, ...)} for every size more than one 12 V
    terminal uses. Two 12 V terminals of one size swap freely, and the row's
    polarity conventions differ -- [G,+,+,+], [+,G,+,G], [+,-,+,-] -- so the
    swap is not an output into its own current limit, it is a load driven
    REVERSED, or a lamp common held at +12 V (IO-24)."""
    by_size = {}
    for r, size in row_sizes(d, TWELVE_VOLT_FACE).items():
        by_size.setdefault(size, []).append(r)
    return {size: tuple(refs) for size, refs in by_size.items() if len(refs) > 1}


def test_no_size_is_shared_between_the_12_v_row_and_the_inputs_row():
    assert shared_sizes(D) == set()


def test_a_12_v_terminal_the_size_of_an_input_terminal_is_caught():
    """J313 is SEVEN-way for this reason: 3.81 × 8 is what J409 and J410 are,
    and an eight-way 12 V plug would seat in either of them squarely, not
    offset -- 12 V onto contacts wired for dry contacts to ground."""
    j = D.connector("J313")
    bad = D.replace_connector("J313", pins=j.pins + (ConnPin("8", "GND"),))
    assert shared_sizes(bad) == {(3.81, 8)}


def test_a_terminal_is_in_the_size_check_the_moment_it_is_in_the_row():
    """The rows are read off `edge_budget`, so there is no list a new 12 V
    terminal can be left out of. J314 is the 5 V terminal, on CTRL: moved to
    OUTPUTS' top face at the 3.81 mm pitch and eight ways, it is in the 12 V
    row and shares J409's and J410's size, and this file did not have to be
    told about it."""
    j = D.connector("J314")
    bad = D.replace_connector("J314", board="OUTPUTS", side="top",
                              pitch_mm=3.81)
    assert "J314" in row_sizes(bad, TWELVE_VOLT_FACE)
    assert shared_sizes(bad) == {(3.81, len(j.pins))} == {(3.81, 8)}


def test_no_two_12_v_terminals_share_a_size():
    """IO-24 (M7): J301, J303 and J305 were all 3.81 × 4 with three polarity
    conventions. J303 carries ten ways and J305 twelve for its four conductors
    each -- every size 2-9 at 3.81 mm is taken and the 11-way header (C3030059)
    is stock 0 -- so the 12 V row's sizes are 2, 4, 5, 7, 10, 12, each used
    once."""
    assert repeated_sizes(D) == {}
    assert sorted(n for _, n in row_sizes(D, TWELVE_VOLT_FACE).values()) == \
        [2, 4, 5, 7, 10, 12]
    for ref, n in (("J303", 10), ("J305", 12)):
        j = D.connector(ref)
        assert len(j.pins) == n and all(cp.net == "" for cp in j.pins[4:]), ref


def test_two_12_v_terminals_of_one_size_are_caught():
    """⚠️ THE MUTATIONS for the check above. Take J305's eight empty ways off
    and it is a 4-way again, the check names it beside J301; take J303's six
    off as well and it names all three, the pre-IO-24 netlist."""
    four = {r: D.connector(r).pins[:4] for r in ("J303", "J305")}
    assert all(cp.net for pins in four.values() for cp in pins), "the conductors"
    one_back = D.replace_connector("J305", pins=four["J305"])
    assert repeated_sizes(one_back) == {(3.81, 4): ("J301", "J305")}
    pre_fix = one_back.replace_connector("J303", pins=four["J303"])
    assert repeated_sizes(pre_fix) == {(3.81, 4): ("J301", "J303", "J305")}
    # ...and neither mutation puts a 12 V size on the inputs row: the check
    # above is the one that catches this defect, not shared_sizes.
    assert shared_sizes(pre_fix) == set()


def test_a_row_is_as_long_as_its_headers_and_the_gaps_between_them():
    """The one figure the fit depends on, by hand for one row: the inputs row is
    J306 (3 × 3.81 + 10.48), J402 (9), J403 (6), J409 and J410 (8 each), with
    HEADER_GAP between neighbours."""
    e = next(x for x in bf.edge_budget(D) if x.board == "LOGIC")
    by_hand = sum(n * 3.81 + 10.48 for n in (3, 9, 6, 8, 8)) + 4 * bf.HEADER_GAP
    assert e.length_mm == pytest.approx(by_hand)
