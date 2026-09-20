"""The stack's geometry is DERIVED from the design, and these tests prove it by
building small designs whose answer can be worked out by hand.

Every expectation below is arithmetic on the fixture's own heights plus the
stated parameters (PCB 1.6, clearance 1.0, trimmed tails 1.5, floor liner 0.5,
thermal pad 0.5 under the brick, floor boss 3.0). None of them re-implements
`layer_gaps`; each states the number a person would get.
"""
import math
from dataclasses import replace

import pytest

from tools import board_params as bp
from tools.model import ConnPin, Connector, Design, Part


def part(ref, board, height, *, side="top", confirmed=True, package="0805",
         mpn="X", dnp=False):
    return Part(ref, mpn, package, board, "R", ("1", "2"), height, confirmed,
                (2.0, 1.25), side=side, dnp=dnp)


def conn(ref, board, height, *, confirmed=True, interface=None):
    return Connector(ref, board, ref, (ConnPin("1", ""),), height, confirmed,
                     (10.0, 5.0), leaves_box=interface is None,
                     interface=interface)


def three_boards(power_top=14.0):
    """POWER: one tall THT part on top, the brick UNDER the board on its floor
    seat. OUTPUTS, LOGIC: a 7.0 connector each."""
    return Design(
        parts=(part("L101", "POWER", power_top, package="THT"),
               part("U201", "POWER", 12.7, package="brick", side="bottom"),
               part("U401", "LOGIC", 3.1, package="module")),
        connectors=(conn("J301", "OUTPUTS", 7.0), conn("J401", "LOGIC", 7.0)))


def gap(stack, below, above):
    return next(g for g in stack.gaps if (g.below, g.above) == (below, above))


# --- parameters ----------------------------------------------------------------
def test_the_envelope_the_pcb_outline_is_cut_to():
    # IO-14: the board is the DESIGN's requirement, not a slice of the cavity,
    # so these two are typed. 39 x 239 = 9321 mm². The PCB emitter draws
    # BOARD_W x BOARD_L, so a change here is a change to a manufactured outline
    # and must be meant -- and it must come from re-running the search in the
    # file's comment, never from nudging a budget closed.
    assert (bp.BOARD_W, bp.BOARD_L) == (39.0, 239.0)
    assert bp.BOARD_AREA == 39.0 * 239.0 == 9321.0
    # Height is cut from the MEASURED cavity: 100 - 3 floor - 3 lid = 94.
    assert bp.AVAIL_H == 100.0 - 3.0 - 3.0 == 94.0


# --- the 10 % the envelope search bought ------------------------------------
# ⚠️ These three are DESIGN-MARGIN tests and they are not board_fit's gates.
# board_fit asks whether the board can be built at all -- a row or a pack over
# 100 % of BOARD_L, a face over DENSITY_LIMIT. These ask the different question
# IO-14 answered: is the 10 % of headroom the envelope search paid for still
# there? Every one of them would pass at 100 %, which is exactly why they exist:
# without them the margin can erode to zero with every gate green and the
# envelope quietly stops being the one IO-14 chose.
# ⛔ Do not "simplify" one of these into board_fit's limit. A tripwire set at the
# limit it is guarding is not a tripwire.
def test_the_board_length_holds_the_longest_row_with_room_to_spare():
    """The row is arithmetic, not a heuristic, so it is one of the two things
    BOARD_L answers to. POWER top's five headers are 55.88 + 25.4 + 35.56 +
    20.32 + 55.88 = 193.04 of body and four 1 mm gaps = 197.04 mm. Against the
    239.0 mm board that is 82.4 %, so the row clears 0.90 x 239.0 = 215.10 by
    18.06 mm and clears the board itself by 41.96 mm -- 14.0 mm of which the
    four M3 corners take: at each END of the row two corners take 2 x 3.5 mm of
    length between them, so 2 x 2 x 3.5 = 14.0 mm in all.

    ⚠️ The row is no longer what sets the length. It wanted 197.04 / 0.90 =
    218.93; the PACK wanted 238.72 and won. Protects: that the row keeps its
    margin while the length is being set by something else."""
    from tools import board_fit as bf, netlist
    longest = max(e.length_mm for e in bf.edge_budget(netlist.current()))
    assert longest == pytest.approx(197.04)
    assert longest <= 0.90 * bp.BOARD_L
    assert bp.BOARD_L - longest > 4 * bf.M3_INSET_MM


def test_the_worst_pack_keeps_the_10_percent_the_envelope_was_chosen_for():
    """The pack is what BOARD_L was set by, at the narrowest width M18 allows.
    POWER top binds: 214.85 mm against 0.90 x 239.0 = 215.10, so 0.25 mm of
    slack -- and that is by construction, because 239.0 is the next whole
    millimetre above 214.85 / 0.90 = 238.72.

    ⚠️ It is the tightest tripwire here and it is meant to be: length is the
    abundant axis (7.00 mm of cavity spare), so a body that grows is answered by
    a millimetre or two of board, not by widening into the 4.35 mm the cavity
    has left across. ⛔ What it must NOT be answered by is a wider board:
    BOARD_W is 39.0 because 38.9 packs into 239.25 mm, which no length inside
    the 246.0 mm cavity cap can carry.

    Protects: that margin. board_fit only fails a pack at 239 mm, so without
    this a body could grow 24 mm and nothing would say the envelope had stopped
    being the one the search chose."""
    from tools import board_fit as bf, netlist
    worst = max(bf.area_budget(netlist.current()),
                key=lambda s: -1.0 if s.pack_mm is None else s.pack_mm)
    assert (worst.board, worst.side) == ("POWER", "top")
    assert worst.pack_mm <= 0.90 * bp.BOARD_L          # the tripwire
    assert worst.pack_mm == pytest.approx(214.85, abs=0.01)     # where it stands


def test_the_worst_density_keeps_the_10_percent_the_envelope_was_chosen_for():
    """The same search held every face to 0.90 x DENSITY_LIMIT = 0.675. POWER
    top binds again: 6045.84 mm² of bodies in 39.0 x 239.0 - 196 = 9125 mm² of
    usable side = 0.6626, which clears 0.675 by 0.0124 -- 11.7 % of headroom
    against the 0.75 board_fit fails at.

    Protects: the headroom routing, courtyards and creepage come out of. Density
    is not what set the envelope (at 239.0 mm it wanted only W >= 38.3), so it
    has more slack than the pack -- but board_fit does not fail a face until
    0.75, and a face drifting from 0.663 to 0.749 is a board nobody can lay
    out, silently."""
    from tools import board_fit as bf, netlist
    worst = max(bf.area_budget(netlist.current()), key=lambda s: s.density)
    assert (worst.board, worst.side) == ("POWER", "top")
    assert worst.density <= 0.90 * bf.DENSITY_LIMIT    # the tripwire
    assert worst.density == pytest.approx(0.6626, abs=0.0005)   # where it stands


def test_the_cavity_the_envelope_requires_is_stated_against_m18():
    """A requirement on the enclosure, not a measurement of the bike.
    Across: 39 board + 2 x 3 wall + 1 drop-in on the far side + 19.65 in front
    of the connector face = 65.65. Along: 239 + 2 x 3 + 2 x 4 = 253.0. Tall: the
    DERIVED stack + 3 floor + 3 lid."""
    assert bp.CAVITY_REQUIRED_W == pytest.approx(65.65)
    assert bp.CAVITY_REQUIRED_L == pytest.approx(253.0)
    d = three_boards()                                   # 52.0 mm of stack
    assert bp.cavity_required(d) == pytest.approx((253.0, 65.65, 52.0 + 6.0))
    # ...and it goes inside the cavity M18 measured, with the spare stated:
    # 260.0 - 253.0 = 7.00 mm along, 70.0 - 65.65 = 4.35 mm across.
    assert bp.CAVITY_L - bp.CAVITY_REQUIRED_L == pytest.approx(7.00)
    assert bp.CAVITY_W - bp.CAVITY_REQUIRED_W == pytest.approx(4.35)


def test_the_required_cavity_cannot_grow_without_someone_typing_the_new_number():
    """⚠️ A DRIFT TRIPWIRE on the real netlist, not a derivation.

    CAVITY_REQUIRED_* is an OUTPUT and nothing bounds it from below. Since M18
    `cavity_problems` does bound it from above -- a requirement past 260.0 or
    70.0 now FAILS -- but the whole distance to that bound is only 7.00 mm along
    and 4.35 mm across, and every millimetre of it can be spent with every gate
    green. A body or a terminal that walks the width from 65.65 to 69.9 leaves
    the design fitting by 0.1 mm and nobody told. The per-wall plug-room verdict
    that used to push back was removed with IO-6's connector face.

    Protects: the spare the envelope search bought against the measured cavity.
    These are today's figures on today's netlist; a terminal, a body height, the
    wall or a clearance that moves one of them fails here, so whoever moved it
    has to look at the new number and type it in.

    ⚠️ The TALL figure is asserted beside the plan axes because it must NOT have
    moved with them: the stack is derived from heights alone. 68.39 at 48 x 219,
    68.39 at 39 x 239."""
    from tools import netlist
    along, across, tall = bp.cavity_required(netlist.current())
    assert (along, across) == pytest.approx((253.0, 65.65))
    assert tall == pytest.approx(68.39, abs=0.01)
    # ...and the measurement they are judged against, so a drift in EITHER bites.
    assert (bp.CAVITY_L, bp.CAVITY_W, bp.CAVITY_H) == (260.0, 70.0, 100.0)
    assert bp.cavity_overruns(netlist.current()) == ()      # it fits, on all three


def test_the_tall_requirement_does_not_answer_to_the_board_s_width_or_length(
        monkeypatch):
    """Shown, not assumed. Reshaping the board from 48 x 219 to 39 x 239 moved
    both plan axes and must have moved the height by nothing at all: the stack
    is a sum of part heights, clearances and PCB, and no term of it is a plan
    dimension. Put the old envelope back and the tall figure is the same."""
    from tools import netlist
    d = netlist.current()
    tall_now = bp.cavity_required(d)[2]
    monkeypatch.setattr(bp, "BOARD_W", 48.0)
    monkeypatch.setattr(bp, "BOARD_L", 219.0)
    monkeypatch.setattr(bp, "BOARD_AREA", 48.0 * 219.0)
    assert bp.cavity_required(d)[2] == pytest.approx(tall_now)
    assert bp.stack_height(d).total_mm == pytest.approx(tall_now - bp.FLOOR - bp.LID)


# --- the cavity requirement is CHECKED, now that the cavity is a fact --------
def test_the_measured_cavity_holds_the_design_and_the_gate_is_armed():
    """The real flags. M18 measured 260 x 70 x 100 and the design asks for
    253.0 x 65.65 x 68.4, so there is no verdict to give -- and, unlike before
    M18, the empty list means it FITS and not that nothing was gating it."""
    from tools import netlist
    assert bp.envelope_is_binding()
    assert bp.cavity_overruns(netlist.current()) == ()
    assert bp.cavity_problems(netlist.current()) == []


def test_the_gate_answers_to_the_measurement_not_to_the_enclosure():
    """⚠️ THE DECISION of 2026-09-20, asserted and not merely commented: a
    MEASURED cavity binds while the enclosure is still undecided. Both flags are
    read as they really are, and `envelope_is_binding` must follow only the
    first. ⛔ If someone re-adds ENCLOSURE_DECIDED to that gate, this fails and
    the reasoning is in `board_params.envelope_is_binding`."""
    assert (bp.CAVITY_MEASURED, bp.ENCLOSURE_DECIDED) == (True, False)
    assert bp.envelope_is_binding()


def test_a_board_too_wide_for_the_measured_cavity_fails(wider_board):
    """⚠️ THE MUTATION that makes the gate a check rather than a claim. Today's
    39.0 mm board asks 65.65 mm of the 70.0 M18 measured and passes; a 45.0 mm
    board asks 71.65 mm and does not go in the box. The flags are the real ones
    -- the enclosure is STILL UNDECIDED -- so this is exactly the case the
    decision is about, and the failure names the wall allowance as the lever
    that has not been spent yet."""
    from tools import netlist
    d = netlist.current()
    assert bp.cavity_problems(d) == []                   # 39.0 mm: it fits
    wider_board(45.0)
    (across,) = bp.cavity_problems(d)
    assert across.startswith("cavity across:")
    assert "requires 71.65 mm" in across and "gives 70.00 mm" in across
    assert "OVER by 1.65 mm" in across
    assert "thinner wall allowance" in across            # the lever still open


def test_a_measured_cavity_that_cannot_hold_the_design_is_a_failure(measured_cavity):
    """253.0 x 65.65 required; a 250 x 61 box holds neither axis, and each
    problem names its axis and the overrun."""
    d = three_boards()
    measured_cavity(250.0, 61.0)
    along, across = bp.cavity_problems(d)
    assert along.startswith("cavity along:") and "OVER by 3.00 mm" in along
    assert across.startswith("cavity across:") and "OVER by 4.65 mm" in across
    assert "measured cavity gives 250.00 mm" in along


def test_a_measured_cavity_that_holds_the_design_is_no_verdict_at_all(measured_cavity):
    measured_cavity(270.0, 80.0)
    assert bp.cavity_problems(three_boards()) == []
    assert bp.cavity_overruns(three_boards()) == ()


def test_the_tall_axis_is_left_to_the_stack_so_one_overrun_is_not_two_faults():
    """`three_boards(60.0)` is 98.0 mm of stack, 104.0 mm of cavity against the
    100 mm M18 measured: `cavity_overruns` sees it on the tall axis, and it is
    `stack_height` that fails on it. `cavity_problems` must not say it again.
    The plan axes are the real ones here and they fit, so the tall axis is the
    only thing that can speak."""
    d = three_boards(60.0)
    assert [axis for axis, *_ in bp.cavity_overruns(d)] == ["tall"]
    assert bp.cavity_problems(d) == []
    assert any("OVER by 4.0" in p for p in bp.stack_height(d).problems)


def test_rules_fails_on_a_cavity_the_measured_box_cannot_hold(measured_cavity):
    from tools import rules
    d = three_boards()
    assert not any(e.startswith("HT-CAVITY") for e in rules.check_all(d))
    measured_cavity(250.0, 61.0)
    cavity = [e for e in rules.check_all(d) if e.startswith("HT-CAVITY: ")]
    assert len(cavity) == 2 and "cavity along" in cavity[0]


def test_the_cavity_is_measured_and_the_enclosure_is_not():
    assert bp.CAVITY_MEASURED is True, "M18: measured by the owner, 2026-09-20"
    assert bp.ENCLOSURE_DECIDED is False, "flip only when the enclosure is chosen"
    # The stack still calls itself provisional -- on the ALLOWANCES now, not on
    # the cavity -- even when every height is confirmed:
    stack = bp.stack_height(three_boards())
    assert stack.load_bearing == () and stack.provisional


def test_no_ceiling_is_typed_anywhere():
    assert not hasattr(bp, "LAYER_CEILING_MM")
    assert not any("CEILING" in name for name in dir(bp))


# --- the derivation, by hand -------------------------------------------------------
def test_three_board_stack_by_hand():
    stack = bp.stack_height(three_boards())
    # FLOOR->POWER    the brick's seat, 0.5 pad + 12.7, over both the
    #                 0.5 liner + 1.5 tails + 1.0 path and the 3.0 boss = 13.2
    # POWER->OUTPUTS  14.0 + 1.0 + 1.5 tails under OUTPUTS             = 16.5
    # OUTPUTS->LOGIC   7.0 + 1.0 + 1.5                                 =  9.5
    # LOGIC->LID       7.0 + 1.0                                       =  8.0
    assert [g.gap_mm for g in stack.gaps] == pytest.approx([13.2, 16.5, 9.5, 8.0])
    assert stack.total_mm == pytest.approx(47.2 + 3 * 1.6)           # 52.0
    assert stack.margin_mm == pytest.approx(42.0)                    # 94.0 - 52.0
    assert stack.ok


def test_a_height_changed_in_the_design_moves_the_stack_by_that_much():
    low, high = bp.stack_height(three_boards(14.0)), bp.stack_height(three_boards(22.0))
    assert high.total_mm - low.total_mm == pytest.approx(8.0)
    assert gap(high, "POWER", "OUTPUTS").top_ref == "L101"


def test_an_over_height_stack_fails_and_says_by_how_much():
    stack = bp.stack_height(three_boards(60.0))         # 52.0 + 46.0 = 98.0 of 94
    assert not stack.ok
    assert any("OVER by 4.0" in p for p in stack.problems)
    assert bp.stack_problems(three_boards(60.0)) == list(stack.problems)


def test_connectors_count_as_tall_things():
    # Connector heights carry most of the stack's margin, so they have to count.
    d = three_boards()
    taller = d.replace_connector("J401", height_mm=12.0)
    assert bp.stack_height(taller).total_mm - bp.stack_height(d).total_mm == \
        pytest.approx(5.0)
    assert gap(bp.stack_height(taller), "LOGIC", "LID").top_ref == "J401"


def test_solder_tails_are_charged_only_under_through_hole_boards():
    smd = Design(parts=(part("R1", "POWER", 1.0), part("R2", "OUTPUTS", 1.0)))
    tht = smd.replace_part("R2", package="DIP-14")
    order = ("POWER", "OUTPUTS")
    assert gap(bp.stack_height(smd, order), "POWER", "OUTPUTS").gap_mm == pytest.approx(2.0)
    assert gap(bp.stack_height(tht, order), "POWER", "OUTPUTS").gap_mm == pytest.approx(3.5)
    assert gap(bp.stack_height(tht, order), "POWER", "OUTPUTS").hang_ref == "solder tails"


def test_tails_under_the_upper_board_are_charged_to_the_gap():
    # Tails budgeted at 0 land on whatever stands below: every OUTPUTS harness
    # pin on the choke under it. 16.5 - 14.0 = the clearance plus the tails.
    g = gap(bp.stack_height(three_boards()), "POWER", "OUTPUTS")
    assert g.gap_mm - 14.0 == pytest.approx(1.0 + 1.5)


# --- bottom-side parts (BD-14) -----------------------------------------------------
def test_a_bottom_side_part_shares_the_gap_and_gets_a_keep_out():
    d = three_boards(22.0).with_part(part("C201", "OUTPUTS", 18.0, side="bottom"))
    stack = bp.stack_height(d)
    g = gap(stack, "POWER", "OUTPUTS")
    assert g.gap_mm == pytest.approx(24.5)          # still set by L101, not 22 + 18
    note = next(n for n in stack.notes if n.startswith("keep-out: C201"))
    assert "5.5 mm" in note and "L101" in note      # 24.5 - 18.0 - 1.0


def test_a_bottom_side_part_deeper_than_everything_else_sets_the_gap():
    d = three_boards(14.0).with_part(part("C201", "OUTPUTS", 18.0, side="bottom"))
    g = gap(bp.stack_height(d), "POWER", "OUTPUTS")
    assert (g.gap_mm, g.hang_ref) == (pytest.approx(19.0), "C201")   # 18.0 + 1.0


def test_a_bottom_side_part_on_the_bottom_board_lifts_it_off_the_floor():
    # With no brick to seat on, the liner path sets it: 0.5 + 9.0 + 1.0 = 10.5.
    d = three_boards().without_part("U201") \
        .with_part(part("C101", "POWER", 9.0, side="bottom"))
    assert gap(bp.stack_height(d), "FLOOR", "POWER").gap_mm == pytest.approx(10.5)
    # With the brick there, 10.5 hides under its 13.2 seat and changes nothing.
    seated = three_boards().with_part(part("C101", "POWER", 9.0, side="bottom"))
    assert gap(bp.stack_height(seated), "FLOOR", "POWER").gap_mm == pytest.approx(13.2)
    assert bp.stack_height(seated).ok


# --- leads and the floor liner (MX-7, HV-1) ----------------------------------------
def test_pins_too_stiff_to_trim_are_charged_at_the_drawing_length():
    """The brick's pins are 5 ± 0.5: 5.5 - 1.6 = 3.9 mm of pin standing THROUGH
    POWER, where a trimmed lead would leave 1.5. With a 2.0 mm choke over it the
    pins are the tallest thing in the gap: 3.9 + 1.0 + 1.5 tails = 6.4."""
    d = three_boards(2.0).replace_part("U201", lead_mm=5.5)
    g = gap(bp.stack_height(d), "POWER", "OUTPUTS")
    assert (g.top_mm, g.top_ref) == (pytest.approx(3.9), "U201 pins")
    assert g.gap_mm == pytest.approx(3.9 + 1.0 + 1.5)


def test_a_connector_under_its_board_sends_its_pins_up_through_it():
    """An upper inter-board half's pins come out on top of its board."""
    d = three_boards()
    d = replace(d, connectors=d.connectors + (replace(
        conn("J311", "OUTPUTS", 2.5), side="bottom", lead_mm=6.1, leaves_box=False),))
    g = gap(bp.stack_height(d), "OUTPUTS", "LOGIC")
    assert (g.top_mm, g.top_ref) == (pytest.approx(7.0), "J301")   # 4.5 pins < 7.0
    tall = d.replace_connector("J311", lead_mm=10.6)                 # 9.0 up
    assert gap(bp.stack_height(tall), "OUTPUTS", "LOGIC").top_ref == "J311 pins"


def test_84v_pins_stand_off_an_insulated_floor():
    """POWER's pins face the grounded metal floor through the liner. Taken with
    no brick on the board, so the liner path is what sets the gap."""
    d = three_boards().without_part("U201").replace_part("L101", lead_mm=6.0)  # 4.4 down
    assert gap(bp.stack_height(d), "FLOOR", "POWER").gap_mm == pytest.approx(
        bp.FLOOR_LINER_T + 4.4 + 1.0)
    assert bp.FLOOR_LINER_T > 0


# --- the brick's floor seat --------------------------------------------------------
def test_the_floor_seat_sets_the_bottom_board_and_says_so():
    """0.5 pad + 12.7 brick = 13.2, against 0.5 liner + 1.5 tails + 1.0 = 3.0."""
    g = gap(bp.stack_height(three_boards()), "FLOOR", "POWER")
    assert (g.seat_mm, g.seat_ref) == (pytest.approx(13.2), "U201")
    assert g.seat_sets_gap and g.gap_mm == pytest.approx(13.2)
    assert "U201" in bp.stack_height(three_boards()).gaps[0].set_by


def test_nothing_beside_the_brick_may_hang_deeper_than_its_seat():
    """The baseplate reaches the floor only at 13.2 mm. Beside it a part has the
    0.5 liner under it and 1.0 of clearance over it, so 11.7 is the deepest that
    still fits (0.5 + 11.7 + 1.0 = 13.2); a 13.0 mm part is deeper than the
    brick itself and holds it off its heatsink."""
    ok = three_boards().with_part(part("U202", "POWER", 11.7, side="bottom"))
    bad = three_boards().with_part(part("U202", "POWER", 13.0, side="bottom"))
    assert bp.stack_height(ok).ok
    assert gap(bp.stack_height(ok), "FLOOR", "POWER").gap_mm == pytest.approx(13.2)
    problems = bp.stack_height(bad).problems
    assert any("U201" in p and "U202" in p and "bolt to the floor" in p
               for p in problems)
    assert not bp.stack_height(bad).ok


def test_the_seat_has_to_be_on_the_bottom_board_underside():
    """Flipped to POWER's top the stack still derives, and comes out 1.2 mm
    SHORTER (the 13.2 mm seat gap collapses to the 3.0 mm boss, and 12.7 mm of
    brick moves into a gap the 14.0 mm choke already sets) -- an arrangement
    that reads as an improvement while the brick has nothing to cool it."""
    flipped = three_boards().replace_part("U201", side="top")
    assert bp.stack_height(flipped).total_mm < bp.stack_height(three_boards()).total_mm
    assert any(p.startswith("seat: U201 sits on POWER top") and "heatsink" in p
               for p in bp.stack_height(flipped).problems)
    # ...and a design that does not carry the part says nothing either way.
    assert bp.stack_height(three_boards().without_part("U201")).ok


def test_a_stiff_lead_beside_the_brick_lifts_it_off_the_floor_too():
    """A tail stands on the liner like a part does: a 15 mm lead leaves
    15.0 - 1.6 = 13.4 mm through the board, and 0.5 + 13.4 + 1.0 > 13.2."""
    stiff = three_boards().replace_part("L101", lead_mm=15.0)
    assert any("L101 pins" in p and "bolt to the floor" in p
               for p in bp.stack_height(stiff).problems)


# --- inter-board connectors --------------------------------------------------------
def with_connectors(design, *more):
    return replace(design, connectors=design.connectors + more)


def linked(lower_h, upper_h, confirmed):
    """`three_boards` with a 5.0 mm OUTPUTS connector and a STACK pair OUTPUTS<->LOGIC."""
    return with_connectors(
        three_boards().replace_connector("J301", height_mm=5.0),
        conn("J308", "OUTPUTS", lower_h, confirmed=confirmed, interface="STACK"),
        conn("J406", "LOGIC", upper_h, confirmed=confirmed, interface="STACK"))


def test_an_unconfirmed_connector_pair_only_widens_the_gap():
    # OUTPUTS->LOGIC parts need 5.0 + 1.0 + 1.5 = 7.5
    short = bp.stack_height(linked(3.0, 2.5, confirmed=False))     # mates at 5.5
    tall = bp.stack_height(linked(8.5, 2.54, confirmed=False))     # mates at 11.04
    assert gap(short, "OUTPUTS", "LOGIC").gap_mm == pytest.approx(7.5)
    assert gap(tall, "OUTPUTS", "LOGIC").gap_mm == pytest.approx(11.04)
    # Too short to reach: said so, and it is the PARTS that set the gap.
    assert any("J308+J406 mates at 5.5 mm (unconfirmed) and the gap is 7.5 mm" in n
               for n in short.notes)
    assert not {"J308", "J406"} & set(short.load_bearing)
    # Tall enough to push the boards apart: now the guess is load-bearing.
    assert {"J308", "J406"} <= set(tall.load_bearing)
    assert short.ok and tall.ok


def test_two_unconfirmed_pairs_across_one_gap_are_told_to_agree():
    d = with_connectors(
        linked(3.0, 2.5, confirmed=False),                       # STACK at 5.5
        conn("J307", "OUTPUTS", 8.5, confirmed=False, interface="PWR-OUT"),
        conn("J407", "LOGIC", 2.5, confirmed=False, interface="PWR-OUT"))  # 11.0
    stack = bp.stack_height(d)
    assert gap(stack, "OUTPUTS", "LOGIC").gap_mm == pytest.approx(11.0)
    assert any("J308+J406 mates at 5.5 mm" in n and "gap is 11.0 mm" in n
               for n in stack.notes)
    assert set(stack.load_bearing) == {"J307", "J407"}


def test_a_confirmed_connector_pair_is_the_gap_and_the_parts_must_fit_it():
    fits = bp.stack_height(linked(8.5, 2.54, confirmed=True))
    assert gap(fits, "OUTPUTS", "LOGIC").gap_mm == pytest.approx(11.04) and fits.ok
    tight = bp.stack_height(linked(3.0, 2.5, confirmed=True))      # 5.5 < 7.5
    assert any("J301 stands 5.0 mm on OUTPUTS" in p for p in tight.problems)


def test_a_bottom_side_part_taller_than_the_gap_below_it_fails():
    d = linked(8.5, 2.54, confirmed=True).with_part(
        part("C450", "LOGIC", 12.0, side="bottom"))                # 12 + 1 > 11.04
    problems = bp.stack_height(d).problems
    assert any("C450 hangs 12.0 mm under LOGIC" in p for p in problems)


def test_two_chosen_pairs_cannot_disagree_about_one_gap():
    d = with_connectors(
        linked(8.5, 2.54, confirmed=True),
        conn("J307", "OUTPUTS", 6.0, interface="PWR-OUT"),
        conn("J407", "LOGIC", 2.0, interface="PWR-OUT"))
    assert any("cannot be two heights" in p for p in bp.stack_height(d).problems)


def test_the_middle_connector_of_a_three_board_bus_is_counted_once():
    # PWR-OUT runs POWER -> OUTPUTS -> LOGIC. J307 is ONE body on OUTPUTS. Summing it into
    # the gap below as well would invent a 17 mm "mated height" out of two
    # sockets that do not mate with each other.
    d = with_connectors(
        three_boards(),
        conn("J202", "POWER", 8.5, confirmed=False, interface="PWR-OUT"),
        conn("J307", "OUTPUTS", 8.5, confirmed=False, interface="PWR-OUT"),
        conn("J407", "LOGIC", 2.5, confirmed=False, interface="PWR-OUT"))
    stack = bp.stack_height(d)
    assert gap(stack, "POWER", "OUTPUTS").pairs == ()
    assert [p.refs for p in gap(stack, "OUTPUTS", "LOGIC").pairs] == ["J307+J407"]
    assert gap(stack, "OUTPUTS", "LOGIC").gap_mm == pytest.approx(11.0)
    assert any(n.startswith("J307 (PWR-OUT) is the middle") for n in stack.notes)


# --- heights nobody has read --------------------------------------------------------
def test_every_unconfirmed_height_is_listed_and_the_load_bearing_ones_named():
    d = three_boards().replace_part("L101", height_confirmed=False) \
        .with_part(part("R101", "POWER", 0.6, confirmed=False))
    stack = bp.stack_height(d)
    assert [r[0] for r in stack.unconfirmed] == ["L101", "R101"]
    assert stack.load_bearing == ("L101",)
    assert stack.ok and stack.provisional        # reported, not failed


@pytest.mark.parametrize("bad", [math.nan, -1.0, None])
def test_an_unknown_height_is_a_failure_not_a_short_part(bad):
    d = three_boards().replace_part("L101", height_mm=bad)
    problems = bp.stack_height(d).problems
    assert any(p.startswith("height: L101") for p in problems)


def test_a_dnp_part_still_needs_its_room():
    d = three_boards().with_part(part("D406", "OUTPUTS", 9.0, dnp=True))
    assert gap(bp.stack_height(d), "OUTPUTS", "LOGIC").top_ref == "D406"


# --- the connector face (IO-6) ------------------------------------------------
def test_the_face_room_is_the_deepest_plug_and_its_bend():
    from tools import netlist
    d = netlist.current()
    deepest = max(c.overhang_mm for c in d.connectors if c.leaves_box and not c.dnp)
    assert bp.face_room(d) == pytest.approx(deepest + bp.WIRE_BEND)


def test_the_typed_face_room_matches_the_netlist():
    """FACE_ROOM is typed once so the outline and the budgets can use it as a
    constant; this is what keeps it honest. Today the deepest fitted plug is
    J101's Kefa 7.62, 9.65 mm past its header: 9.65 + 10.0 bend = 19.65."""
    from tools import netlist
    assert bp.FACE_ROOM == pytest.approx(19.65)
    assert bp.FACE_ROOM == pytest.approx(bp.face_room(netlist.current()))


def test_an_unfitted_plug_does_not_set_the_face_room():
    """A DNP terminal is laid out but nothing is plugged into it, so no plug of
    its stands in front of the face. J405 is parked and DNP: a 40 mm overhang on
    it must not move the answer; on a fitted one it would."""
    from tools import netlist
    d = netlist.current()
    assert bp.face_room(d.replace_connector("J405", overhang_mm=40.0)) \
        == pytest.approx(bp.FACE_ROOM)
    assert bp.face_room(d.replace_connector("J101", overhang_mm=40.0)) \
        == pytest.approx(50.0)


def test_a_harness_header_hanging_under_outputs_sets_the_gap_below_it():
    from tools import netlist
    d = netlist.current()
    tall = d.replace_connector("J314", height_mm=20.0, height_confirmed=True)
    gap = next(g for g in bp.layer_gaps(tall) if (g.below, g.above) == ("POWER", "OUTPUTS"))
    assert gap.hang_mm >= 20.0 and gap.gap_mm >= 20.0 + bp.CLEARANCE


def test_a_harness_terminal_under_a_board_gets_a_keep_out_like_a_part():
    """BD-14 on connectors, not just parts. J314 hangs 7.0 mm under OUTPUTS into
    the POWER->OUTPUTS gap, which L102's 22.0 mm choke + 1.0 clearance + the
    2.1 mm of J402's pins through OUTPUTS set to 25.1 mm. So 25.1 - 7.0 - 1.0 =
    17.1 mm is the tallest thing that may stand under it, and the chokes do
    not qualify."""
    from tools import netlist
    stack = bp.stack_height(netlist.current())
    note = next(n for n in stack.notes if n.startswith("keep-out: J314"))
    assert "hangs 7.0 mm under OUTPUTS" in note
    assert "taller than 17.1 mm" in note and "L101" in note and "L102" in note


def test_the_inter_board_halves_get_no_keep_out_of_their_own():
    """Each half of a pair faces its own other half by construction, and their
    mated height IS the gap -- so J311, J312, J406 and J407 hanging under their
    boards are four notes about nothing."""
    from tools import netlist
    stack = bp.stack_height(netlist.current())
    assert not [n for n in stack.notes
                if any(n.startswith(f"keep-out: {r}")
                       for r in ("J311", "J312", "J406", "J407"))]


# --- the envelope verdict is provisional only while the CAVITY is a guess ----
# ⚠️ Built on `three_boards(60.0)`, NOT on the real netlist. These three used to
# derive their overrun from `netlist.current()` and skip when it fitted, so the
# wording of the verdict went untested exactly when the design was healthy.
# 52.0 mm of stack with the 14.0 mm choke, so 60.0 makes it 98.0 against the
# 94.0 the measured cavity leaves: OVER by 4.0 either way.
def test_an_overrun_of_the_measured_envelope_is_a_failure():
    """The real flags. M18 is measured, so this is a verdict and not a note --
    and the enclosure being undecided does not soften it."""
    assert bp.envelope_is_binding()
    tall = bp.stack_height(three_boards(60.0))
    assert any("OVER by 4.0" in p for p in tall.problems)
    assert not tall.envelope_verdicts
    assert not tall.ok


def test_the_same_overrun_could_not_fail_a_cavity_nobody_had_measured(
        unmeasured_cavity):
    """The world before M18, which is the only thing `envelope_verdicts` is for:
    an overrun reported loudly and unable to fail the design."""
    assert not bp.envelope_is_binding()
    tall = bp.stack_height(three_boards(60.0))
    assert tall.envelope_verdicts, "an overrun must never vanish silently"
    assert "OVER by 4.0" in tall.envelope_verdicts[0]
    assert "ESTIMATED envelope" in tall.envelope_verdicts[0]
    assert not any("OVER by" in p for p in tall.problems)
    assert tall.ok                       # reported loudly, and not a failure


def test_rules_relay_the_provisional_verdict_as_a_warning(unmeasured_cavity):
    from tools import rules
    d = three_boards(60.0)
    assert bp.stack_height(d).envelope_verdicts
    assert any(w.startswith("HT-STACK-PROVISIONAL") and "OVER by 4.0" in w
               for w in rules.warnings(d))
    assert not any(e.startswith("HT-STACK") for e in rules.check_all(d))


def test_rules_fail_on_that_same_overrun_now_the_cavity_is_measured():
    """...and the other side of it: with the real flags the warning becomes an
    error, so a stack too tall for the measured box cannot ride out as a note."""
    from tools import rules
    d = three_boards(60.0)
    assert not bp.stack_height(d).envelope_verdicts
    assert not any(w.startswith("HT-STACK-PROVISIONAL") for w in rules.warnings(d))
    assert any(e.startswith("HT-STACK") and "OVER by 4.0" in e
               for e in rules.check_all(d))
