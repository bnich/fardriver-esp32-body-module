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


def _nets(c):
    return [cp.net for cp in c.pins]


# ── board to board ───────────────────────────────────────────────────────────
def test_every_interface_is_one_crossing_between_neighbours_with_matching_halves(d):
    """Every crossing has a part on each side.  PWR-OUT once ran POWER → OUTPUTS →
    LOGIC on one tabled bus with nothing between POWER and OUTPUTS.

    The FACES depend on the kind.  A mated pair faces itself across the gap —
    lower half on top, upper half hanging under.  A cable does not: the loom
    carries the orientation, so both halves stand on a top face (IO-20), which
    is what keeps a 22 mm connector assembly out of the gap L102 already stands
    22.0 mm in."""
    order = board_params.STACK_ORDER
    for iface in {c.interface for c in d.connectors if c.interface}:
        halves = _halves(d, iface)
        assert len(halves) == 2, (iface, [c.refdes for c in halves])
        lo, up = halves
        assert order.index(up.board) == order.index(lo.board) + 1, iface
        want = ("top", "top") if is_cabled(iface) else ("top", "bottom")
        assert (lo.side, up.side) == want, iface
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
    causes, which is where a loaded connector is really bounded. Only two of
    the four circuits carry it, and the other two carry ~0.6 A and ~0 A.
    """
    load = power_budget.budget(d).load_12v_a
    assert load > 8, f"a load of {load:.2f} A would not test anything"
    for c in _halves(d, "PWR-OUT"):
        assert c.contact_a, f"{c.refdes} states no per-contact rating"
        for net in HEAVY:
            carrying = [cp for cp in c.pins if cp.net == net]
            assert len(carrying) == 1, (c.refdes, net)
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


def test_every_cabled_half_is_positively_keyed(d):
    """⛔ What a cable has INSTEAD of a palindrome, and the reason it may not
    simply be exempted: a loom is offered to its header by hand at every
    service, and PWR-OUT's four different nets on four contacts admit no order
    that makes a reversed mate harmless. Rule BUS-ORDER says the same thing on
    the real design; this holds the FEATURE to being named from a drawing,
    which is the only form of it anybody can check on the bench."""
    assert CABLES, "no cabled crossing left to check"
    for iface in CABLES:
        for c in _halves(d, iface):
            assert c.keyed, f"{c.refdes} ({iface}) names no keying"
            assert any(w in c.keyed for w in ("notch", "lock", "key")), c.refdes


def test_each_crossing_carries_what_the_boards_above_it_use(d):
    up = Counter(_nets(_halves(d, "PWR-OUT")[0]))
    assert up["V12"] and up["V5"] and up["KEY_SENSE"]
    assert set(up) == {"V12", "V5", "KEY_SENSE", "GND"}
    brain = Counter(_nets(_halves(d, "PWR-LOGIC")[0]))
    assert set(brain) == {"V5", "V3P3", "KEY_SENSE", "GND"}, "LOGIC uses no V12"
    assert brain["V3P3"] == 2, (
        "the 3.3 V rail goes back DOWN to OUTPUTS on this bus, not on the "
        "signal spine, and a rail needs two contacts to stay a palindrome")


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
    assert CABLES, "no cabled crossing left to check"
    for iface in CABLES:
        lo, up = _halves(d, iface)
        lo_fp, up_fp = footprint_lib.generated(lo), footprint_lib.generated(up)
        assert "-UNDER" not in lo_fp[0] and "-UNDER" not in up_fp[0], iface
        assert lo_fp[0] == up_fp[0], iface
        assert {p.num: (p.x_mm, p.y_mm) for p in lo_fp[1]} == \
            {p.num: (p.x_mm, p.y_mm) for p in up_fp[1]}, iface


def test_the_under_gate_is_the_crossing_kind_not_the_face(d):
    """⚠️ Proven by mutation, or the rule above passes only because no cabled
    half happens to sit on a bottom face.  Put one there: it is STILL not
    pre-mirrored, because what earns the mirror is having a mate to line up
    with, and a mated pair on the same face still earns it."""
    cabled = replace(_halves(d, CABLES[0])[1], side="bottom")
    assert "-UNDER" not in footprint_lib.generated(cabled)[0]
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
