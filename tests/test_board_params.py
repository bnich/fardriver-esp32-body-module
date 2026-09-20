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
    # IO-14: the board is the DESIGN's requirement, not a slice of the cavity
    # estimate, so these two are typed. 48 x 219 = 10512 mm². The PCB emitter
    # draws BOARD_W x BOARD_L, so a change here is a change to a manufactured
    # outline and must be meant -- and it must come from re-running the search
    # in the file's comment, never from nudging a budget closed.
    assert (bp.BOARD_W, bp.BOARD_L) == (48.0, 219.0)
    assert bp.BOARD_AREA == 48.0 * 219.0 == 10512.0
    # Height is still cut from the estimate: 70 - 3 floor - 3 lid = 64.
    assert bp.AVAIL_H == 70.0 - 3.0 - 3.0 == 64.0


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
    """The row is arithmetic, not a heuristic, so it is what BOARD_L answers to.
    POWER top's five headers are 55.88 + 25.4 + 35.56 + 20.32 + 55.88 = 193.04
    of body and four 1 mm gaps = 197.04 mm. 197.04 / 219.0 = 90.0 % of the
    board, so the row clears it by 21.96 mm -- 14.0 mm of which the four M3
    corners take: at each END of the row two corners take 2 x 3.5 mm of length
    between them, so 2 x 2 x 3.5 = 14.0 mm in all.

    ⚠️ 0.06 mm of slack. Protects: the length IO-14 sized to this row."""
    from tools import board_fit as bf, netlist
    longest = max(e.length_mm for e in bf.edge_budget(netlist.current()))
    assert longest == pytest.approx(197.04)
    assert longest <= 0.90 * bp.BOARD_L
    assert bp.BOARD_L - longest > 4 * bf.M3_INSET_MM


def test_the_worst_pack_keeps_the_10_percent_the_width_was_chosen_for():
    """BOARD_W is the smallest width at which every face's shelf pack fits
    0.90 x BOARD_L (47.8, stepped to 48.0). POWER top is the face that binds:
    195.45 mm of 197.1, which is 1.65 mm of slack and the whole reason the
    width is 48 and not 45.

    Protects: that margin. board_fit only fails a pack at 219 mm, so without
    this a body could grow 23 mm and nothing would say the width had stopped
    being the one the search chose."""
    from tools import board_fit as bf, netlist
    worst = max(bf.area_budget(netlist.current()),
                key=lambda s: -1.0 if s.pack_mm is None else s.pack_mm)
    assert (worst.board, worst.side) == ("POWER", "top")
    assert worst.pack_mm <= 0.90 * bp.BOARD_L          # the tripwire
    assert worst.pack_mm == pytest.approx(195.45, abs=0.01)     # where it stands


def test_the_worst_density_keeps_the_10_percent_the_width_was_chosen_for():
    """The same search held every face to 0.90 x DENSITY_LIMIT = 0.675. POWER
    top binds again at 0.586 -- 6046 mm² of bodies in 10316 mm² of usable side.

    Protects: the headroom routing, courtyards and creepage come out of. Density
    is not what set the width (it wanted only 41.8 mm), so it has more slack
    than the pack -- but board_fit does not fail a face until 0.75, and a face
    drifting from 0.586 to 0.674 is a board nobody can lay out, silently."""
    from tools import board_fit as bf, netlist
    worst = max(bf.area_budget(netlist.current()), key=lambda s: s.density)
    assert (worst.board, worst.side) == ("POWER", "top")
    assert worst.density <= 0.90 * bf.DENSITY_LIMIT    # the tripwire
    assert worst.density == pytest.approx(0.5861, abs=0.0005)   # where it stands


def test_the_cavity_the_envelope_requires_is_stated_for_m18():
    """⬜ A requirement on the enclosure, not a measurement of the bike.
    Across: 48 board + 2 x 3 wall + 1 drop-in on the far side + 19.65 in front
    of the connector face = 74.65. Along: 219 + 2 x 3 + 2 x 4 = 233.0. Tall: the
    DERIVED stack + 3 floor + 3 lid."""
    assert bp.CAVITY_REQUIRED_W == pytest.approx(74.65)
    assert bp.CAVITY_REQUIRED_L == pytest.approx(233.0)
    d = three_boards()                                   # 52.0 mm of stack
    assert bp.cavity_required(d) == pytest.approx((233.0, 74.65, 52.0 + 6.0))
    # ...and it is honest about exceeding the estimate rather than matching it.
    assert bp.CAVITY_REQUIRED_W > bp.CAVITY_W and bp.CAVITY_REQUIRED_L > bp.CAVITY_L


def test_the_required_cavity_cannot_grow_without_someone_typing_the_new_number():
    """⚠️ A DRIFT TRIPWIRE on the real netlist, not a derivation.

    Nothing bounds what this design may ask of the enclosure. CAVITY_REQUIRED_*
    is an OUTPUT, the cavity it is compared against is unmeasured, and
    `cavity_problems` is therefore empty -- so the requirement can grow and
    every gate stays green. The per-wall plug-room verdict that used to push
    back was removed with IO-6's connector face. A terminal family whose plug
    stands 40 mm proud walks FACE_ROOM to 50.0 (the plug, then the 10 mm bend)
    and the required width with it, to 105.0 mm, with `board_fit` still
    exiting 0 -- measured, not argued.

    Protects: the requirement M18 will be measured against. These are today's
    figures on today's netlist; a terminal, a body height, the wall or a
    clearance that moves one of them fails here, so whoever moved it has to
    look at the new number and type it in -- against a cavity estimate the
    design is already 33.0 mm and 24.65 mm outside."""
    from tools import netlist
    along, across, tall = bp.cavity_required(netlist.current())
    assert (along, across) == pytest.approx((233.0, 74.65))
    assert tall == pytest.approx(68.39, abs=0.01)
    # ...and the estimate they are reported against, so a drift in EITHER bites.
    assert (bp.CAVITY_L, bp.CAVITY_W, bp.CAVITY_H) == (200.0, 50.0, 70.0)
    assert [(axis, round(need - have, 2))
            for axis, need, have in bp.cavity_overruns(netlist.current())] \
        == [("along", 33.0), ("across", 24.65)]


# --- the cavity requirement is CHECKED, once the cavity is a fact ------------
def test_an_unmeasured_cavity_cannot_fail_the_design_it_does_not_hold():
    """The real flags. The requirement exceeds the estimate on both plan axes
    and that is a finding for M18, not a failure -- `cavity_problems` is empty
    because `envelope_is_binding()` is False, not because it fits."""
    from tools import netlist
    assert not bp.envelope_is_binding()
    assert bp.cavity_overruns(netlist.current())        # it does NOT fit
    assert bp.cavity_problems(netlist.current()) == []  # ...and does not fail


def test_a_measured_cavity_that_cannot_hold_the_design_is_a_failure(measured_cavity):
    """The day M18 lands. 233.0 x 74.65 required; a 230 x 70 box holds neither
    axis, and each problem names its axis and the overrun."""
    d = three_boards()
    measured_cavity(230.0, 70.0)
    along, across = bp.cavity_problems(d)
    assert along.startswith("cavity along:") and "OVER by 3.00 mm" in along
    assert across.startswith("cavity across:") and "OVER by 4.65 mm" in across
    assert "measured cavity gives 230.00 mm" in along


def test_a_measured_cavity_that_holds_the_design_is_no_verdict_at_all(measured_cavity):
    measured_cavity(240.0, 80.0)
    assert bp.cavity_problems(three_boards()) == []
    assert bp.cavity_overruns(three_boards()) == ()


def test_the_tall_axis_is_left_to_the_stack_so_one_overrun_is_not_two_faults(
        measured_cavity):
    """`three_boards(30.0)` is 68.0 mm of stack, 74.0 mm of cavity against the
    70 mm estimate: `cavity_overruns` sees it on the tall axis, and it is
    `stack_height` that fails on it. `cavity_problems` must not say it again."""
    measured_cavity(240.0, 80.0)
    d = three_boards(30.0)
    assert [axis for axis, *_ in bp.cavity_overruns(d)] == ["tall"]
    assert bp.cavity_problems(d) == []
    assert any("OVER by 4.0" in p for p in bp.stack_height(d).problems)


def test_rules_fails_on_a_cavity_the_measured_box_cannot_hold(measured_cavity):
    from tools import rules
    d = three_boards()
    assert not any(e.startswith("HT-CAVITY") for e in rules.check_all(d))
    measured_cavity(230.0, 70.0)
    cavity = [e for e in rules.check_all(d) if e.startswith("HT-CAVITY: ")]
    assert len(cavity) == 2 and "cavity along" in cavity[0]


def test_both_budgets_say_they_are_provisional():
    assert bp.CAVITY_MEASURED is False, "flip only when M18 lands"
    assert bp.ENCLOSURE_DECIDED is False, "flip only when the enclosure is chosen"
    # ...and that reaches the verdict even when every height is confirmed:
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
    assert stack.margin_mm == pytest.approx(12.0)                    # 64.0 - 52.0
    assert stack.ok


def test_a_height_changed_in_the_design_moves_the_stack_by_that_much():
    low, high = bp.stack_height(three_boards(14.0)), bp.stack_height(three_boards(22.0))
    assert high.total_mm - low.total_mm == pytest.approx(8.0)
    assert gap(high, "POWER", "OUTPUTS").top_ref == "L101"


def test_an_over_height_stack_fails_and_says_by_how_much(binding_envelope):
    stack = bp.stack_height(three_boards(30.0))         # 52.0 + 16.0 = 68.0 of 64
    assert not stack.ok
    assert any("OVER by 4.0" in p for p in stack.problems)
    assert bp.stack_problems(three_boards(30.0)) == list(stack.problems)


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


# --- the envelope verdict is provisional until the envelope is a fact --------
# ⚠️ Built on `three_boards(30.0)`, NOT on the real netlist. These three used to
# derive their overrun from `netlist.current()` and skip when it fitted, so the
# wording of the verdict went untested exactly when the design was healthy.
def test_an_overrun_against_an_estimated_envelope_is_loud_but_not_a_failure():
    """52.0 mm with the 14.0 mm choke, so 30.0 makes it 68.0 of the 64.0 the
    estimate leaves: OVER by 4.0."""
    assert not bp.envelope_is_binding()
    tall = bp.stack_height(three_boards(30.0))
    assert tall.envelope_verdicts, "an overrun must never vanish silently"
    assert "OVER by 4.0" in tall.envelope_verdicts[0]
    assert "ESTIMATED envelope" in tall.envelope_verdicts[0]
    assert not any("OVER by" in p for p in tall.problems)
    assert tall.ok                       # reported loudly, and not a failure


def test_the_same_overrun_is_a_failure_once_the_envelope_is_measured(binding_envelope):
    tall = bp.stack_height(three_boards(30.0))
    assert any("OVER by 4.0" in p for p in tall.problems)
    assert not tall.envelope_verdicts
    assert not tall.ok


def test_rules_relay_the_provisional_verdict_as_a_warning():
    from tools import rules
    d = three_boards(30.0)
    assert bp.stack_height(d).envelope_verdicts
    assert any(w.startswith("HT-STACK-PROVISIONAL") and "OVER by 4.0" in w
               for w in rules.warnings(d))
    assert not any(e.startswith("HT-STACK") for e in rules.check_all(d))
