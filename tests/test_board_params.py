"""The stack's geometry is DERIVED from the design, and these tests prove it by
building small designs whose answer can be worked out by hand.

Every expectation below is arithmetic on the fixture's own heights plus the
stated parameters (PCB 1.6, clearance 1.0, trimmed tails 1.5, plate 3.0 with
flush screws, floor liner 0.5, floor boss 3.0). None of them re-implements
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


def four_boards(hvin_top=14.0):
    """HVIN: one tall THT part. CONV: the brick. DRV, BRAIN: a 7.0 connector each."""
    return Design(
        parts=(part("L101", "HVIN", hvin_top, package="THT"),
               part("U201", "CONV", 12.7, package="brick"),
               part("U401", "BRAIN", 3.1, package="module")),
        connectors=(conn("J301", "DRV", 7.0), conn("J401", "BRAIN", 7.0)))


def gap(stack, below, above):
    return next(g for g in stack.gaps if (g.below, g.above) == (below, above))


# --- parameters ----------------------------------------------------------------
def test_the_envelope_the_pcb_outline_is_cut_to():
    # Hand-stated: 50 - 2x3 - 2x1 = 42 wide, 200 - 2x3 - 2x4 = 186 long,
    # 70 - 3 - 3 = 64 tall. The PCB emitter draws BOARD_W x BOARD_L, so a
    # change here is a change to a manufactured outline and must be meant.
    assert (bp.BOARD_W, bp.BOARD_L, bp.AVAIL_H) == (42.0, 186.0, 64.0)
    assert bp.BOARD_AREA == 42.0 * 186.0


def test_both_budgets_say_they_are_provisional():
    assert bp.CAVITY_MEASURED is False, "flip only when M18 lands"
    assert bp.ENCLOSURE_DECIDED is False, "flip only when the enclosure is chosen"
    # ...and that reaches the verdict even when every height is confirmed:
    stack = bp.stack_height(four_boards())
    assert stack.load_bearing == () and stack.provisional


def test_no_ceiling_is_typed_anywhere():
    assert not hasattr(bp, "LAYER_CEILING_MM")
    assert not any("CEILING" in name for name in dir(bp))


# --- the derivation, by hand -------------------------------------------------------
def test_four_board_stack_by_hand():
    stack = bp.stack_height(four_boards())
    # FLOOR->HVIN  max(3.0 boss, 1.5 tails + 1.0)                    =  3.0
    # HVIN->CONV   14.0 + 1.0 + 1.5 tails under CONV                 = 16.5
    # CONV->DRV    12.7 brick + 3.0 plate + 1.0 + 1.5 tails under DRV = 18.2
    # DRV->BRAIN   7.0 + 1.0 + 1.5                                   =  9.5
    # BRAIN->LID   7.0 + 1.0                                         =  8.0
    assert [g.gap_mm for g in stack.gaps] == pytest.approx([3.0, 16.5, 18.2, 9.5, 8.0])
    assert stack.total_mm == pytest.approx(55.2 + 4 * 1.6)           # 61.6
    assert stack.margin_mm == pytest.approx(2.4)
    assert stack.ok


def test_a_height_changed_in_the_design_moves_the_stack_by_that_much():
    low, high = bp.stack_height(four_boards(14.0)), bp.stack_height(four_boards(22.0))
    assert high.total_mm - low.total_mm == pytest.approx(8.0)
    assert gap(high, "HVIN", "CONV").top_ref == "L101"


def test_an_over_height_stack_fails_and_says_by_how_much(binding_envelope):
    stack = bp.stack_height(four_boards(22.0))          # 61.6 + 8.0 = 69.6 of 64
    assert not stack.ok
    assert any("OVER by 5.6" in p for p in stack.problems)
    assert bp.stack_problems(four_boards(22.0)) == list(stack.problems)


def test_connectors_count_as_tall_things():
    # Connector heights carry most of the stack's margin, so they have to count.
    d = four_boards()
    taller = d.replace_connector("J401", height_mm=12.0)
    assert bp.stack_height(taller).total_mm - bp.stack_height(d).total_mm == \
        pytest.approx(5.0)
    assert gap(bp.stack_height(taller), "BRAIN", "LID").top_ref == "J401"


def test_solder_tails_are_charged_only_under_through_hole_boards():
    smd = Design(parts=(part("R1", "HVIN", 1.0), part("R2", "CONV", 1.0)))
    tht = smd.replace_part("R2", package="DIP-14")
    order = ("HVIN", "CONV")
    assert gap(bp.stack_height(smd, order), "HVIN", "CONV").gap_mm == pytest.approx(2.0)
    assert gap(bp.stack_height(tht, order), "HVIN", "CONV").gap_mm == pytest.approx(3.5)
    assert gap(bp.stack_height(tht, order), "HVIN", "CONV").hang_ref == "solder tails"


def test_tails_under_the_upper_board_stand_off_the_plate():
    # Tails budgeted at 0 sit ON the alloy plate: every DRV harness pin shorted to it.
    g = gap(bp.stack_height(four_boards()), "CONV", "DRV")
    assert g.plate_mm == 3.0
    assert g.gap_mm - (12.7 + 3.0) == pytest.approx(1.0 + 1.5)


# --- bottom-side parts (BD-14) -----------------------------------------------------
def test_a_bottom_side_part_shares_the_gap_and_gets_a_keep_out():
    d = four_boards(22.0).with_part(part("C201", "CONV", 18.0, side="bottom"))
    stack = bp.stack_height(d)
    g = gap(stack, "HVIN", "CONV")
    assert g.gap_mm == pytest.approx(24.5)          # still set by L101, not 22 + 18
    note = next(n for n in stack.notes if n.startswith("keep-out: C201"))
    assert "5.5 mm" in note and "L101" in note      # 24.5 - 18.0 - 1.0


def test_a_bottom_side_part_deeper_than_everything_else_sets_the_gap():
    d = four_boards(14.0).with_part(part("C201", "CONV", 18.0, side="bottom"))
    g = gap(bp.stack_height(d), "HVIN", "CONV")
    assert (g.gap_mm, g.hang_ref) == (pytest.approx(19.0), "C201")


def test_a_bottom_side_part_on_the_bottom_board_lifts_it_off_the_floor():
    d = four_boards().with_part(part("C101", "HVIN", 9.0, side="bottom"))
    # 0.5 liner + 9.0 part + 1.0 clearance
    assert gap(bp.stack_height(d), "FLOOR", "HVIN").gap_mm == pytest.approx(10.5)


# --- leads, the floor liner, the plate's screws (MX-7, HV-1) ------------------------
def test_pins_too_stiff_to_trim_are_charged_at_the_drawing_length():
    """The brick's pins are 5 ± 0.5: 5.5 - 1.6 = 3.9 under CONV, not 1.5."""
    d = four_boards(22.0).replace_part("U201", lead_mm=5.5)
    g = gap(bp.stack_height(d), "HVIN", "CONV")
    assert (g.hang_mm, g.hang_ref) == (pytest.approx(3.9), "U201 pins")
    assert g.gap_mm == pytest.approx(22.0 + 1.0 + 3.9)


def test_a_connector_under_its_board_sends_its_pins_up_through_it():
    """An upper inter-board half's pins come out on top of its board."""
    d = four_boards()
    d = replace(d, connectors=d.connectors + (replace(
        conn("J311", "DRV", 2.5), side="bottom", lead_mm=6.1, leaves_box=False),))
    g = gap(bp.stack_height(d), "DRV", "BRAIN")
    assert (g.top_mm, g.top_ref) == (pytest.approx(7.0), "J301")   # 4.5 pins < 7.0
    tall = d.replace_connector("J311", lead_mm=10.6)                 # 9.0 up
    assert gap(bp.stack_height(tall), "DRV", "BRAIN").top_ref == "J311 pins"


def test_84v_pins_stand_off_an_insulated_floor():
    """HVIN's pins face the grounded metal floor through the liner."""
    d = four_boards().replace_part("L101", lead_mm=6.0)              # 4.4 down
    assert gap(bp.stack_height(d), "FLOOR", "HVIN").gap_mm == pytest.approx(
        bp.FLOOR_LINER_T + 4.4 + 1.0)
    assert bp.FLOOR_LINER_T > 0


def test_the_plate_screws_sit_flush():
    """ISO 10642 countersunk heads sink into the 3.0 mm plate: nothing over it."""
    assert bp.PLATE_SCREW_HEAD <= bp.PLATE_T and bp.PLATE_HARDWARE_ABOVE == 0.0


# --- the plate ---------------------------------------------------------------------
def test_the_plate_cannot_seat_over_a_part_that_outgrows_the_brick():
    ok = four_boards().with_part(part("C203", "CONV", 11.7))       # 11.7 + 1.0 = 12.7
    bad = four_boards().with_part(part("C203", "CONV", 12.0))
    assert bp.stack_height(ok).ok
    problems = bp.stack_height(bad).problems
    assert any("cannot seat on U201" in p and "C203" in p for p in problems)


# --- inter-board connectors --------------------------------------------------------
def with_connectors(design, *more):
    return replace(design, connectors=design.connectors + more)


def linked(lower_h, upper_h, confirmed):
    """`four_boards` with a 5.0 mm DRV connector and a STACK pair DRV<->BRAIN."""
    return with_connectors(
        four_boards().replace_connector("J301", height_mm=5.0),
        conn("J308", "DRV", lower_h, confirmed=confirmed, interface="STACK"),
        conn("J406", "BRAIN", upper_h, confirmed=confirmed, interface="STACK"))


def test_an_unconfirmed_connector_pair_only_widens_the_gap():
    # DRV->BRAIN parts need 5.0 + 1.0 + 1.5 = 7.5
    short = bp.stack_height(linked(3.0, 2.5, confirmed=False))     # mates at 5.5
    tall = bp.stack_height(linked(8.5, 2.54, confirmed=False))     # mates at 11.04
    assert gap(short, "DRV", "BRAIN").gap_mm == pytest.approx(7.5)
    assert gap(tall, "DRV", "BRAIN").gap_mm == pytest.approx(11.04)
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
        conn("J307", "DRV", 8.5, confirmed=False, interface="PWR-UP"),
        conn("J407", "BRAIN", 2.5, confirmed=False, interface="PWR-UP"))  # 11.0
    stack = bp.stack_height(d)
    assert gap(stack, "DRV", "BRAIN").gap_mm == pytest.approx(11.0)
    assert any("J308+J406 mates at 5.5 mm" in n and "gap is 11.0 mm" in n
               for n in stack.notes)
    assert set(stack.load_bearing) == {"J307", "J407"}


def test_a_confirmed_connector_pair_is_the_gap_and_the_parts_must_fit_it():
    fits = bp.stack_height(linked(8.5, 2.54, confirmed=True))
    assert gap(fits, "DRV", "BRAIN").gap_mm == pytest.approx(11.04) and fits.ok
    tight = bp.stack_height(linked(3.0, 2.5, confirmed=True))      # 5.5 < 7.5
    assert any("J301 stands 5.0 mm on DRV" in p for p in tight.problems)


def test_a_bottom_side_part_taller_than_the_gap_below_it_fails():
    d = linked(8.5, 2.54, confirmed=True).with_part(
        part("C450", "BRAIN", 12.0, side="bottom"))                # 12 + 1 > 11.04
    problems = bp.stack_height(d).problems
    assert any("C450 hangs 12.0 mm under BRAIN" in p for p in problems)


def test_two_chosen_pairs_cannot_disagree_about_one_gap():
    d = with_connectors(
        linked(8.5, 2.54, confirmed=True),
        conn("J307", "DRV", 6.0, interface="PWR-UP"),
        conn("J407", "BRAIN", 2.0, interface="PWR-UP"))
    assert any("cannot be two heights" in p for p in bp.stack_height(d).problems)


def test_the_middle_connector_of_a_three_board_bus_is_counted_once():
    # PWR-UP runs CONV -> DRV -> BRAIN. J307 is ONE body on DRV. Summing it into
    # the gap below as well would invent a 17 mm "mated height" out of two
    # sockets that do not mate with each other.
    d = with_connectors(
        four_boards(),
        conn("J202", "CONV", 8.5, confirmed=False, interface="PWR-UP"),
        conn("J307", "DRV", 8.5, confirmed=False, interface="PWR-UP"),
        conn("J407", "BRAIN", 2.5, confirmed=False, interface="PWR-UP"))
    stack = bp.stack_height(d)
    assert gap(stack, "CONV", "DRV").pairs == ()
    assert [p.refs for p in gap(stack, "DRV", "BRAIN").pairs] == ["J307+J407"]
    assert gap(stack, "DRV", "BRAIN").gap_mm == pytest.approx(11.0)
    assert any(n.startswith("J307 (PWR-UP) is the middle") for n in stack.notes)


# --- heights nobody has read --------------------------------------------------------
def test_every_unconfirmed_height_is_listed_and_the_load_bearing_ones_named():
    d = four_boards().replace_part("L101", height_confirmed=False) \
        .with_part(part("R101", "HVIN", 0.6, confirmed=False))
    stack = bp.stack_height(d)
    assert [r[0] for r in stack.unconfirmed] == ["L101", "R101"]
    assert stack.load_bearing == ("L101",)
    assert stack.ok and stack.provisional        # reported, not failed


@pytest.mark.parametrize("bad", [math.nan, -1.0, None])
def test_an_unknown_height_is_a_failure_not_a_short_part(bad):
    d = four_boards().replace_part("L101", height_mm=bad)
    problems = bp.stack_height(d).problems
    assert any(p.startswith("height: L101") for p in problems)


def test_a_dnp_part_still_needs_its_room():
    d = four_boards().with_part(part("D406", "DRV", 9.0, dnp=True))
    assert gap(bp.stack_height(d), "DRV", "BRAIN").top_ref == "D406"


# --- the envelope verdict is provisional until the envelope is a fact --------
def _real():
    from tools import netlist
    return netlist.current()


def test_an_overrun_against_an_estimated_envelope_is_loud_but_not_a_failure(monkeypatch):
    from tools import board_params as bp
    monkeypatch.setattr(bp, "CAVITY_MEASURED", False)
    tall = bp.stack_height(_real())
    if tall.total_mm <= tall.avail_mm:
        pytest.skip("the real stack fits the estimate; nothing to report")
    assert tall.envelope_verdicts, "an overrun must never vanish silently"
    assert "OVER by" in tall.envelope_verdicts[0]
    assert not any("OVER by" in p for p in tall.problems)


def test_the_same_overrun_is_a_failure_once_the_envelope_is_measured(binding_envelope):
    from tools import board_params as bp
    tall = bp.stack_height(_real())
    if tall.total_mm <= tall.avail_mm:
        pytest.skip("the real stack fits; nothing to fail")
    assert any("OVER by" in p for p in tall.problems)
    assert not tall.envelope_verdicts


def test_rules_relay_the_provisional_verdict_as_a_warning(monkeypatch):
    from tools import board_params as bp, rules
    monkeypatch.setattr(bp, "CAVITY_MEASURED", False)
    d = _real()
    if not bp.stack_height(d).envelope_verdicts:
        pytest.skip("no overrun to relay")
    assert any(w.startswith("HT-STACK-PROVISIONAL") for w in rules.warnings(d))
    assert not any(e.startswith("HT-STACK") for e in rules.check_all(d))
