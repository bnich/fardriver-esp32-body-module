"""How the boards join each other, and how the harness joins the boards.

Two halves of an inter-board connector can be mated reversed or one contact
off; on a MATED PAIR the upper half is mounted upside down on the underside of
its board, and on a CABLE both halves stand on a top face and the loom is
offered to each header by hand.  A harness plug can be pushed into the wrong
header, and a smaller plug seats, offset, in a larger header of the same pitch.
Each test below states what must still hold when that happens.

⭐ The two kinds are held to DIFFERENT things, and which one applies is read off
`model.CROSSING`, never typed: a pair earns its safety by ORDER (a palindrome,
and no two rails side by side) and a cable by KEYING plus a conductor sized for
the current it carries, because no order makes four different nets safe to
reverse.
"""
from collections import Counter
from dataclasses import replace
from unittest import mock

import pytest

from tools import board_params, footprint_lib, netlist, power_budget
from tools.model import CROSSING, is_cabled

#: The power interfaces that are MATED PAIRS, derived: a pair is what an
#: ordering rule protects. ⛔ Never type this list — PWR-OUT was in it until
#: IO-20 made it a cable, and a typed list would have kept asking a loom for a
#: palindrome it cannot have.
POWER_BUSES = tuple(i for i in ("PWR-OUT", "PWR-LOGIC") if not is_cabled(i))
#: Read off model.CROSSING, never typed here: a crossing that changes kind must
#: change which test applies to it, not silently keep passing the old one.
MATED_PAIRS = tuple(i for i, k in CROSSING.items() if k == "pair")
CABLES = tuple(i for i, k in CROSSING.items() if k == "cable")


@pytest.fixture(scope="module")
def d():
    return netlist.current()


def _halves(d, iface):
    order = board_params.STACK_ORDER
    return sorted((c for c in d.connectors if c.interface == iface),
                  key=lambda c: order.index(c.board))


def _crossings(d):
    """The interfaces the DESIGN actually carries halves for. ⚠️ Not every name
    in `model.CROSSING`: the table is the shape, and a crossing with no
    connectors is a crossing this design does not have."""
    return {c.interface for c in d.connectors if c.interface}


def _nets(c):
    return [cp.net for cp in c.pins]


# ── board to board ───────────────────────────────────────────────────────────
def test_every_interface_is_one_crossing_between_neighbours_with_matching_halves(d):
    """Every crossing has a part on each side.  PWR-OUT once ran POWER → OUTPUTS →
    LOGIC on one tabled bus with nothing between POWER and OUTPUTS.

    ⭐ EVERY half looks INTO the gap its crossing spans — lower half standing on
    top of the lower board, upper half hanging under the upper one — whichever
    kind it is.  That is geometry, not a choice: the far side of a board is a
    different gap, and a body put there has to fit THAT one.  ⛔ PWR-OUT and
    CTRL sat on OUTPUTS' TOP face until Task 4 of IO-20: the STACK pair stops
    OUTPUTS → LOGIC at 11.04 mm, J311's posts stand 10.9, and the loom would
    have had to come back round a board edge with 1.0 mm of clearance beside it.

    What the two kinds differ in is ALIGNMENT, and that is
    `test_only_a_mated_pair_is_pre_mirrored` and integrity's facing check: a
    mated pair has to face its own other half across the gap and is
    pre-mirrored for it; a cable is not asked to, because the loom carries the
    orientation."""
    order = board_params.STACK_ORDER
    for iface in {c.interface for c in d.connectors if c.interface}:
        halves = _halves(d, iface)
        assert len(halves) == 2, (iface, [c.refdes for c in halves])
        lo, up = halves
        assert order.index(up.board) == order.index(lo.board) + 1, iface
        assert (lo.side, up.side) == ("top", "bottom"), iface
        assert [(cp.pin, cp.net) for cp in lo.pins] == [(cp.pin, cp.net) for cp in up.pins], iface


def test_a_power_bus_mated_reversed_or_mirrored_lands_every_net_on_itself(d):
    """⚠️ MATED PAIRS only, and the set is read off model.CROSSING, not typed:
    a palindrome is what a bus whose halves can be mated reversed needs, and
    PWR-OUT stopped being one when it became a keyed cable (IO-20). The cable's
    own contract is two tests below."""
    for iface in POWER_BUSES:
        assert not is_cabled(iface), f"{iface} is a cable: keying, not order"
        nets = _nets(_halves(d, iface)[0])
        assert nets == nets[::-1], (iface, nets)


#: Nets at ground potential: each converter's -Vin reaches GND through its
#: choke's second winding and nothing else.
RETURNS = {"GND", "HV_C1_N", "HV_C2_N"}


def test_a_power_bus_mated_one_contact_off_puts_no_rail_on_another(d):
    """Shifted by one, each contact meets its neighbour's net.  Two different
    nets side by side must include a return, so the worst a shift does is
    short a rail, never feed 84 V or 12 V into a logic input."""
    for iface in POWER_BUSES:
        nets = _nets(_halves(d, iface)[0])
        for a, b in zip(nets, nets[1:]):
            assert a == b or RETURNS & {a, b}, (iface, a, b)
    for name in RETURNS - {"GND"}:
        joins = {n.name for p in d.parts if p.kind == "CMCHOKE"
                 for n in d.nets_of(p.refdes)}
        assert name in joins, f"{name} is not a choke-winding return"


# ── what carries PWR-OUT's 8.47 A, now that it is a CABLE ───────────────────
# ⭐ `CONTACT_A` and its arithmetic retired with IO-20, and what replaced them
# is not a weaker check, it is the right one. A 1.0 A per-contact floor was a
# STAND-IN for a rating nobody had: no candidate in the 2026-09-20 survey
# published one, so the bus was widened to 23 contacts to stay inside a figure
# that was invented. A cable does not divide its current over contacts at all
# -- it sizes the CONDUCTOR, and both the conductor and the one contact it
# lands on are now figures off JST's own drawing.
#: PWR-OUT's nets that carry the whole 12 V load, out and back.
HEAVY = ("V12", "GND")
#: How many conductors each of them takes. ⭐ ONE out and TWO back (IO-27): the
#: CTRL ribbon's 13 grounds carried ~79 % of the return and are gone, so a
#: single GND crimp would be the one silent failure that puts the whole 8.47 A
#: nowhere. The feed keeps one conductor because an open V12 crimp is a dead
#: module, which is loud.
RETURN_CONDUCTORS = {"V12": 1, "GND": 2}


def test_the_cables_conductors_and_contacts_carry_every_amp_the_budget_derives(d):
    """⚠️ The crossing and the budget must not drift apart — the aux block took
    it from 2.62 A to 8.47 A in one commit (IO-10), and this is what says so
    now that no contact count does.

    Protects: the conductor and the contact TOGETHER, which is how JST states
    it — 10 A AC/DC **with AWG #16**, one figure for the pair. The current is
    whatever tools/power_budget.py derives, never a typed one.

    ⚠️ Derating: JST's VH drawing p.1 gives ONE current figure and no table
    against the number of circuits energised, so 10 A is the figure held to
    here; its −25…+85 °C range is stated to include the rise the current
    causes, which is where a loaded connector is really bounded. Three of the
    five circuits carry it, and the other two carry ~0.6 A and ~0 A.

    ⭐ TWO GND CONDUCTORS SINCE IO-27, and the figure each is held to is the
    WHOLE load, not half of it. They share by conductance in service (~4.24 A
    each), but the case that sizes them is ONE CRIMP OPEN: the survivor then
    carries all 8.47 A, and an open crimp is silent. So the assertion below is
    deliberately the same for one return conductor or two -- what the second
    one buys is that the loom no longer has a single point of failure, now
    that the CTRL ribbon's 13 grounds are gone.
    """
    load = power_budget.budget(d).load_12v_a
    assert load > 8, f"a load of {load:.2f} A would not test anything"
    for c in _halves(d, "PWR-OUT"):
        assert c.contact_a, f"{c.refdes} states no per-contact rating"
        for net in HEAVY:
            carrying = [cp for cp in c.pins if cp.net == net]
            assert len(carrying) == RETURN_CONDUCTORS[net], (c.refdes, net)
            assert load <= c.contact_a, (
                f"{c.refdes}: {load:.2f} A on one contact rated "
                f"{c.contact_a} A")
            awg, crimp, _ = netlist.PWROUT_LOOM[net]
            thinnest, thickest = netlist.VH_CONTACTS[crimp]
            assert thickest <= awg <= thinnest, (
                f"{net} is {awg} AWG and {crimp} takes {thinnest}-{thickest}: "
                f"the wire does not crimp into the contact")
            assert awg <= RATED_AWG, (
                f"{net} carries {load:.2f} A on {awg} AWG, and the 10 A the "
                f"connector is rated at is stated at AWG #{RATED_AWG}")


#: The gauge JST's 10 A figure is stated at. Anything thinner is outside the
#: rating even though the CONTACT is unchanged — the two come as a pair.
RATED_AWG = 16


def test_the_conductor_check_fires_on_the_clone_and_on_a_thin_wire(d):
    """A check nothing can fail is not a check. Both defects are real ones:

    ⛔ THE CLONE. CAX's `VH-4A-HT` (C5453989) lists identically to the JST part
    — same series name, same 3.96 mm pitch, same 4P, cheaper, in stock — at
    **3 A**. That is a 2.8× overload at 8.47 A, and it is the Blue Sea failure
    again: right family, right pitch, wrong rating line.
    ⛔ THE WIRE. 22 AWG is what the other two conductors use and it crimps into
    the same housing.
    """
    load = power_budget.budget(d).load_12v_a
    clone = d.replace_connector("J202", contact_a=3.0)
    with pytest.raises(AssertionError, match="rated 3.0 A"):
        test_the_cables_conductors_and_contacts_carry_every_amp_the_budget_derives(clone)
    assert load / 3.0 > 2.5, "the clone would be a 2.8x overload"

    thin = dict(netlist.PWROUT_LOOM, V12=(22, "SVH-21T-P1.1", "too thin"))
    with mock.patch.object(netlist, "PWROUT_LOOM", thin):
        with pytest.raises(AssertionError, match="stated at AWG"):
            test_the_cables_conductors_and_contacts_carry_every_amp_the_budget_derives(d)

    wrong_crimp = dict(netlist.PWROUT_LOOM, V12=(16, "SVH-21T-P1.1", "22-18"))
    with mock.patch.object(netlist, "PWROUT_LOOM", wrong_crimp):
        with pytest.raises(AssertionError, match="does not crimp"):
            test_the_cables_conductors_and_contacts_carry_every_amp_the_budget_derives(d)


def test_the_brass_posts_are_bonded_at_one_end_only_so_one_return_is_sized(d):
    """⭐ IO-21 (owner, 2026-09-21), recorded where the fact lives rather than
    in a document. It is a CURRENT question, not a mechanical one.

    The four brass M3×30 posts that set POWER → OUTPUTS are conductive and they
    are bolted through a mounting pad on each board. Bond both ends and the
    8.47 A return has TWO paths: PWR-OUT's 16 AWG GND conductor, which the
    power budget sizes, and an unrated one through brass threads and screw
    torque that nothing checks and that changes as fasteners age. ⛔ So they are
    bonded to GND at the OUTPUTS END ONLY, landing on a copper-free pad at
    POWER — a defined potential beside POWER's 84 V pins, and no second return.

    Protects: that the single-ended bond and the sized conductor stay written
    down together. Either one alone reads as arbitrary, and the reason the
    brass may not be a second return is the whole of it."""
    (brass,) = [s for s in netlist.standoffs()
                if tuple(s.between) == ("POWER", "OUTPUTS")]
    assert brass.seating == "sets" and "brass" in brass.source.lower()
    assert "OUTPUTS END ONLY (IO-21)" in brass.source
    assert "copper-free pad at POWER" in brass.source
    assert "16 AWG" in brass.source and "SOLE sized return" in brass.source
    # ...and the conductor that IS the return says the same, from its own end.
    awg, _crimp, why = netlist.PWROUT_LOOM["GND"]
    assert awg == 16 and "ONLY sized return" in why and "IO-21" in why
    # ⭐ TWO GND conductors on the cable since IO-27, and they are the whole
    # return: the ribbon that used to carry ~79 % of it is gone, which is why
    # the brass must still not become a third path.
    for c in _halves(d, "PWR-OUT"):
        assert len([cp for cp in c.pins if cp.net == "GND"]) == \
            RETURN_CONDUCTORS["GND"], c.refdes
    assert "IO-27" in brass.source and "no third path" in brass.source


def test_the_pwrout_housing_is_the_body_s_size_with_the_omitted_posts_empty(d):
    """⛔ Audit C2: the BOM named a VHR-4N for a wafer that is a FIVE-circuit
    body with its third post omitted. JST's housing table (VH drawing p.2)
    gives the 4-circuit housing B = 15.78 against the wafer's 19.74: cavities
    1-4 only, so it cannot carry contact 5, and its lock does not meet the
    wafer. The loom as listed could not be built, and nothing read the housing.

    Protects: the housing's circuit count IS the body's (`vh_body`'s `ways`),
    and the cavities left empty ARE the posts the contact table omits -- both
    derived from the header's own tables, so neither can be typed apart from
    them again. And the two ends come from one place: the keyed string and
    both halves' sources name the housing, and `jlc_bom` orders it.
    ⚠️ Since IO-27 the contact table omits NOTHING: cavity 3 carries the second
    GND, so the set of empty cavities is empty and the assertion is that it
    matches, not that it is non-empty."""
    housing, circuits, empty = netlist.PWROUT_HOUSING
    halves = _halves(d, "PWR-OUT")
    assert halves, "no PWR-OUT half to hold the housing to"
    for c in halves:
        assert c.footprint_mm == netlist.vh_body(circuits), (
            f"{c.refdes}: a {circuits}-circuit housing on a body that is not "
            f"{circuits} circuits long")
        numbered = {cp.pin for cp in c.pins}
        omitted = {str(i) for i in range(1, circuits + 1)} - numbered
        assert set(empty) == omitted, (
            f"{c.refdes}: the housing leaves {set(empty)} empty but the wafer "
            f"omits {omitted}")
        assert housing in c.keyed and housing in c.source, c.refdes
        assert netlist._MATE_BY_REFDES[c.refdes] == housing, c.refdes
    ends = dict((mpn, qty) for mpn, qty, _ in netlist.pwrout_loom_ends())
    assert ends[f"JST {housing}"] == 2                      # one per end
    # ⭐ ...and a crimp on both ends of every CONDUCTOR, counted off the
    # CONTACT table and not off the loom table's keys: two contacts carry GND
    # since IO-27, and counting nets would have ordered four heavy crimps for
    # three heavy conductors -- the second return arriving uncrimpable.
    per_crimp = Counter(netlist.PWROUT_LOOM[net][1]
                        for _pin, net in netlist._PWROUT_CONTACTS)
    for crimp, n in per_crimp.items():
        assert ends[f"JST {crimp}"] == 2 * n, crimp
    assert ends == {"JST VHR-5N": 2, "JST SVH-41T-P1.1": 6, "JST SVH-21T-P1.1": 4}


def test_the_housing_check_fires_on_the_vhr_4n(d):
    """A check nothing can fail is not a check: the housing the BOM DID name.
    Four circuits on a five-circuit body, and its cavity-3 omission would be
    the wrong post anyway."""
    with mock.patch.object(netlist, "PWROUT_HOUSING", ("VHR-4N", 4, ("3",))):
        with pytest.raises(AssertionError, match="not 4 circuits long"):
            test_the_pwrout_housing_is_the_body_s_size_with_the_omitted_posts_empty(d)
    # ...and the right size with a cavity wrongly left empty is the other half.
    # ⚠️ Cavity 3 is the one IO-27 filled, so leaving it empty in the housing is
    # a housing that cannot take the second return.
    with mock.patch.object(netlist, "PWROUT_HOUSING", ("VHR-5N", 5, ("3",))):
        with pytest.raises(AssertionError, match="but the wafer omits"):
            test_the_pwrout_housing_is_the_body_s_size_with_the_omitted_posts_empty(d)


def test_every_cabled_half_has_a_cable_end_bought_with_it(d):
    """⛔ Audit M31: the CTRL ribbon's IDC socket was named in a prose string
    and ordered nowhere. A loom is two headers AND two cable ends; a header
    with nothing booked to plug onto it is a loom that cannot be built.

    Protects: every cabled half names its mate, the mate is either an LCSC
    part ordered loose (`_LOOSE_BY_MPN`, so the fixture and `jlc_bom` carry
    it) or the PWR-OUT housing (owner-buy, `pwrout_loom_ends`), and nothing
    names a mate for a half that is not cabled.
    ⚠️ ONE cable is left since IO-27 deleted the ribbon, and its mate is the
    owner-buy housing rather than an LCSC part -- which is why both branches
    of the `or` below stay."""
    cabled = {c.refdes for c in d.connectors if is_cabled(c.interface)}
    assert cabled == set(netlist._MATE_BY_REFDES) == {"J202", "J311"}, (
        f"mates for {set(netlist._MATE_BY_REFDES) ^ cabled}")
    off_lcsc = {mpn.removeprefix("JST ") for mpn, _, _ in netlist.pwrout_loom_ends()}
    for ref, mpn in netlist._MATE_BY_REFDES.items():
        assert mpn in netlist._LOOSE_BY_MPN or mpn in off_lcsc, (ref, mpn)
    # ⛔ And the ribbon's own cable end is GONE from the order, not merely
    # unreferenced: an IDC socket still booked for a loom that no longer
    # exists is a part the owner buys for nothing.
    assert "FC-2.54-24P" not in netlist._LOOSE_BY_MPN
    from tools import jlc_bom
    assert "FC-2.54-24P" not in jlc_bom.loose_list(d)
    assert "VHR-5N" in jlc_bom.loom_list()


def test_every_cabled_half_is_positively_keyed(d):
    """⛔ What a cable has INSTEAD of a palindrome, and the reason it may not
    simply be exempted: a loom is offered to its header by hand at every
    service, and PWR-OUT's four different nets on four contacts admit no order
    that makes a reversed mate harmless. Rule BUS-ORDER says the same thing on
    the real design; this holds the FEATURE to being named from a drawing,
    which is the only form of it anybody can check on the bench."""
    assert set(CABLES) & _crossings(d), "no cabled crossing left to check"
    for iface in set(CABLES) & _crossings(d):
        for c in _halves(d, iface):
            assert c.keyed, f"{c.refdes} ({iface}) names no keying"
            assert any(w in c.keyed for w in ("notch", "lock", "key")), c.refdes


def test_each_crossing_carries_what_the_boards_above_it_use(d):
    """⭐ V12 CLIMBS THE WHOLE STACK SINCE IO-26 2a. It used to stop at
    OUTPUTS, where every 12 V load was; the 5 V aux buck is on CTRL now, so
    V12 rides PWR-LOGIC up to LOGIC and CTRL-STACK up to CTRL. Nothing ON
    LOGIC draws from it -- it passes over that board on copper, the way the
    telltales pass the other way."""
    up = Counter(_nets(_halves(d, "PWR-OUT")[0]))
    assert up["V12"] and up["V5"] and up["KEY_SENSE"]
    assert set(up) == {"V12", "V5", "KEY_SENSE", "GND"}
    brain = Counter(_nets(_halves(d, "PWR-LOGIC")[0]))
    assert set(brain) == {"V12", "V5", "V3P3", "KEY_SENSE", "GND"}
    assert brain["V3P3"] == 2, (
        "the 3.3 V rail goes back DOWN to OUTPUTS on this bus, not on the "
        "signal spine, and a rail needs two contacts to stay a palindrome")
    assert brain["V12"] == 2, (
        "the buck's input is ~2.6 A against a 3 A contact: two contacts, "
        "sized in tools/power_budget.py")
    top = Counter(_nets(_halves(d, "CTRL-STACK")[0]))
    assert top["V12"] == 2 and "V5" not in top and "V3P3" not in top, (
        "the only rail CTRL needs is the buck's input; a rail nobody draws "
        "on costs two contacts and a palindrome constraint for nothing")
    # ...and no part on LOGIC is on V12: it only passes through.
    assert "LOGIC" not in {d.board_of(r) for r, _ in d.net("V12").pins
                           if not r.startswith("J")}


def test_key_sense_meets_its_adc_pin_through_1k_with_100nf_at_the_pin(d):
    """It crosses three boards and passes 84 V copper on the way."""
    parts = {p.refdes: p for p in d.parts}
    pin_net = d.net_of("U401", "IO1")
    others = [(r, p) for r, p in pin_net.pins if r != "U401"]
    rs = [r for r, _ in others if parts[r].kind == "R"]
    cs = [r for r, _ in others if parts[r].kind == "C"]
    assert len(rs) == 1 and parts[rs[0]].value == "1k"
    assert {n.name for n in d.nets_of(rs[0])} == {pin_net.name, "KEY_SENSE"}
    assert len(cs) == 1 and parts[cs[0]].value.startswith("100nF")
    assert {n.name for n in d.nets_of(cs[0])} == {pin_net.name, "GND"}
    assert pin_net.gpio == "GPIO1"


def test_the_spines_pinouts_are_derived_from_their_signal_lists(d):
    """⛔ THE PINOUT IS NEVER TYPED, on either spine. STACK is built by
    `_signal_gnd_pins` from a list of signals -- contact 2i+1 the signal, 2i+2
    the ground across the row from it -- and CTRL-STACK by `_rail_pair_pins`,
    which is the same thing with the V12 rail wrapped round it. The contact a
    net lands on, the contact count, the body length and the LCSC size all
    follow the list.

    THE MUTATION, and it is the whole test: reverse the signal list and rebuild
    the pinout. Every signal moves to a different contact, the grounds stay
    where they are, and the body is unchanged -- which is what "derived" means
    and what a typed table could not do. ⚠️ It is run on CTRL-STACK AND on
    STACK, because a builder shared by two spines has to be proven on both,
    and because this is the check that would catch a hand-patched pin table.
    """
    def build(iface, signals):
        if iface == "CTRL-STACK":
            return [cp.net for cp in netlist._rail_pair_pins(
                signals, netlist._CTRL_STACK_RAIL, netlist._CTRL_STACK_ROWS)]
        return [cp.net for cp in netlist._signal_gnd_pins(signals)]

    for iface, signals, pad in (
            ("CTRL-STACK", netlist._flat(netlist._CTRL_STACK_SIGNALS), 3),
            ("STACK", netlist._STACK_SIGNALS, 0)):
        live = [cp.net for cp in _halves(d, iface)[0].pins]
        built = build(iface, signals)
        assert live == built, iface
        body = built[pad:len(built) - pad] if pad else built
        assert body[0::2] == list(signals) and set(body[1::2]) == {"GND"}
        turned = build(iface, signals[::-1])
        t_body = turned[pad:len(turned) - pad] if pad else turned
        assert turned != built and t_body[0::2] == list(signals)[::-1]
        assert t_body[1::2] == body[1::2], "the grounds do not move"
        assert turned[:pad] == built[:pad], "nor does the rail's end block"
        assert len(turned) == len(built) == 2 * len(signals) + 2 * pad


def test_the_two_spines_take_the_same_family_across_the_same_stop(d):
    """⭐ CTRL-STACK is STACK one deck up (IO-27): the same Hong Cheng socket
    series on the lower board's TOP face, the same BOOMELE strip cut to length
    under the upper board, and the same 8.5 + 2.54 = 11.04 mm insulator-to-
    insulator stop. That is why one HIWA TP-11 part number and one 10.94-11.04
    selection window serve both gaps -- a second mated height would need a
    second pillar and a second window to measure into."""
    stack, ctrl = _halves(d, "STACK"), _halves(d, "CTRL-STACK")
    for lower, upper in (stack, ctrl):
        assert (lower.side, upper.side) == ("top", "bottom")
        assert (lower.height_mm, upper.height_mm) == (8.5, 2.54)
        assert lower.height_confirmed and upper.height_confirmed
    assert stack[0].lcsc != ctrl[0].lcsc, "different sizes, different sockets"
    assert stack[1].lcsc == ctrl[1].lcsc == "C2333", "one strip, two lengths"
    gaps = {(g.below, g.above): g for g in board_params.layer_gaps(d)}
    for key in (("OUTPUTS", "LOGIC"), ("LOGIC", "CTRL")):
        assert gaps[key].gap_mm == pytest.approx(11.04), key
        assert gaps[key].standoff.name == "HIWA TP-11"
        assert gaps[key].standoff.seating == "shimmed"


def test_a_mated_pairs_upper_half_lands_pad_for_pad_over_its_mate(d):
    """A PAIR's upper half is placed on the underside, which the editor mirrors.
    Its footprint is generated pre-mirrored, so after the flip (and at most a
    180° turn) every pad sits over its mate's.  A same-numbered dual-row
    footprint cannot be aligned by any turn: its rows swap, and STACK's
    signals would land on ground."""
    assert MATED_PAIRS, "no mated pair left to check"
    for iface in MATED_PAIRS:
        lo, up = _halves(d, iface)
        lo_pads = {p.num: (p.x_mm, p.y_mm) for p in footprint_lib.generated(lo)[1]}
        up_pads = {p.num: (-p.x_mm, p.y_mm) for p in footprint_lib.generated(up)[1]}
        assert up_pads == lo_pads, iface
        assert "-UNDER" in footprint_lib.generated(up)[0]
        assert footprint_lib.generated(lo)[0] != footprint_lib.generated(up)[0]


def test_a_cabled_crossing_gets_two_ordinary_unmirrored_footprints(d):
    """Pre-mirroring exists to line a half up with the MATE under it.  A cable
    has no such mate, so mirroring it would only move its pads off where the
    netlist puts them: both halves get the same plain land pattern."""
    assert set(CABLES) & _crossings(d), "no cabled crossing left to check"
    for iface in set(CABLES) & _crossings(d):
        lo, up = _halves(d, iface)
        lo_fp, up_fp = footprint_lib.generated(lo), footprint_lib.generated(up)
        assert "-UNDER" not in lo_fp[0] and "-UNDER" not in up_fp[0], iface
        assert lo_fp[0] == up_fp[0], iface
        assert {p.num: (p.x_mm, p.y_mm) for p in lo_fp[1]} == \
            {p.num: (p.x_mm, p.y_mm) for p in up_fp[1]}, iface


def test_the_under_gate_is_the_crossing_kind_not_the_face(d):
    """⚠️ Proven by mutation in BOTH directions, or the rule above passes only
    because of where the halves happen to sit.  Every upper half hangs under
    its board today, cabled or mated, so the face cannot be what distinguishes
    them: move a cabled one to the TOP and it is still not pre-mirrored, while
    the mated one on the same face still earns the mirror.  What earns it is
    having a mate to line up with."""
    cabled = _halves(d, sorted(set(CABLES) & _crossings(d))[0])[1]
    assert cabled.side == "bottom"                      # ...as its gap requires
    assert "-UNDER" not in footprint_lib.generated(cabled)[0]
    assert "-UNDER" not in footprint_lib.generated(replace(cabled, side="top"))[0]
    paired = _halves(d, MATED_PAIRS[0])[1]
    assert "-UNDER" in footprint_lib.generated(paired)[0]


# ── the harness ──────────────────────────────────────────────────────────────
#: Wires whose plug, in the wrong header, silently changes what the brake,
#: the kill or the motor does, or puts pack voltage where it does not belong.
SENSITIVE_NETS = {"HV_BPLUS", "KSW", "LEVER_L", "LEVER_R", "BL", "ACC_PLUS",
                  "IN11_RUN_WIRE", "BOOST_OUT"}


def _fitted_harness(d):
    return [c for c in d.connectors if c.leaves_box and not c.dnp]


def _named_nets_exist(d):
    """Every name in SENSITIVE_NETS, against the nets the design really has."""
    return SENSITIVE_NETS - {n.name for n in d.nets}


def test_every_sensitive_net_named_here_is_a_net_the_design_has(d):
    """SENSITIVE_NETS is typed. A renamed net would drop out of it silently and
    the size check below would simply stop looking at that connector."""
    missing = _named_nets_exist(d)
    assert missing == set(), f"no such net: {sorted(missing)}"


def test_the_sensitive_net_guard_fires_when_a_net_it_names_is_renamed(d):
    """The guard is only a check if it fails. Task 2 renamed RUN to
    IN11_RUN_WIRE and the list kept the old name, which cost J403 its unique-size
    check with every test still green. The nets named here move between
    connectors and boards as the rows are laid out; the names must not."""
    renamed = replace(d, nets=tuple(
        replace(n, name="BL_OUT") if n.name == "BL" else n for n in d.nets))
    assert _named_nets_exist(renamed) == {"BL"}


def test_a_sensitive_plug_has_a_size_no_other_header_in_its_family_shares(d):
    """A plug seats in any header of its pitch at least its size, offset if
    larger.  With every plug seated that forces each plug into a header of
    exactly its own size -- so a connector whose (pitch, positions) is unique
    cannot be swapped without leaving a plug in the hand."""
    harness = _fitted_harness(d)
    sizes = Counter((c.pitch_mm, len(c.pins)) for c in harness)
    for c in harness:
        if SENSITIVE_NETS & set(_nets(c)):
            assert sizes[(c.pitch_mm, len(c.pins))] == 1, c.refdes


def test_pack_voltage_has_a_pitch_of_its_own(d):
    """Every 84 V wire enters on one connector, and no other plug shares its
    pitch: nothing else seats in it and it seats in nothing else."""
    harness = _fitted_harness(d)
    hv = [c for c in harness if any(cp.net and d.net(cp.net).domain == "84V" for cp in c.pins)]
    assert [c.refdes for c in hv] == ["J101"]
    assert [c.refdes for c in harness if c.pitch_mm == hv[0].pitch_mm] == ["J101"]


def test_the_key_tap_is_a_pitch_away_from_any_return(d):
    """A strand across KSW and a return pulls the FarDriver KEY line down."""
    nets = _nets(d.connector("J101"))
    k = nets.index("KSW")
    assert all(n == "" for n in nets[max(0, k - 1):k] + nets[k + 1:k + 2])


def test_a_parked_connector_has_no_header_to_seat_a_plug_in(d):
    for c in d.connectors:
        if c.leaves_box and c.parked:
            assert c.dnp, c.refdes
