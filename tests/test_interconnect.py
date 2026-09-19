"""How the boards join each other, and how the harness joins the boards.

Two halves of an inter-board connector can be mated reversed or one contact
off, and the upper half is mounted upside down on the underside of its board.
A harness plug can be pushed into the wrong header, and a smaller plug seats,
offset, in a larger header of the same pitch.  Each test below states what
must still hold when that happens.
"""
from collections import Counter

import pytest

from tools import board_params, footprint_lib, netlist

POWER_BUSES = ("PWR-OUT", "PWR-LOGIC")


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
    LOGIC on one tabled bus with nothing between POWER and OUTPUTS."""
    order = board_params.STACK_ORDER
    for iface in {c.interface for c in d.connectors if c.interface}:
        halves = _halves(d, iface)
        assert len(halves) == 2, (iface, [c.refdes for c in halves])
        lo, up = halves
        assert order.index(up.board) == order.index(lo.board) + 1, iface
        assert (lo.side, up.side) == ("top", "bottom"), iface
        assert [(cp.pin, cp.net) for cp in lo.pins] == [(cp.pin, cp.net) for cp in up.pins], iface


def test_a_power_bus_mated_reversed_or_mirrored_lands_every_net_on_itself(d):
    for iface in POWER_BUSES:
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


def test_each_crossing_carries_what_the_boards_above_it_use(d):
    up = Counter(_nets(_halves(d, "PWR-OUT")[0]))
    assert up["V12"] >= 3, "2.62 A: one fretted contact of two is 100 %"
    assert up["GND"] >= 4 and up["V5"] and up["KEY_SENSE"]
    assert set(up) == {"V12", "V5", "KEY_SENSE", "GND"}
    brain = Counter(_nets(_halves(d, "PWR-LOGIC")[0]))
    assert set(brain) == {"V5", "KEY_SENSE", "GND"}, "LOGIC uses no V12"


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


def test_a_bottom_side_half_lands_pad_for_pad_over_its_mate(d):
    """The upper half is placed on the underside, which the editor mirrors.
    Its footprint is generated pre-mirrored, so after the flip (and at most a
    180° turn) every pad sits over its mate's.  A same-numbered dual-row
    footprint cannot be aligned by any turn: its rows swap, and STACK's
    signals would land on ground."""
    for iface in {c.interface for c in d.connectors if c.interface}:
        lo, up = _halves(d, iface)
        lo_pads = {p.num: (p.x_mm, p.y_mm) for p in footprint_lib.generated(lo)[1]}
        up_pads = {p.num: (-p.x_mm, p.y_mm) for p in footprint_lib.generated(up)[1]}
        assert up_pads == lo_pads, iface
        assert footprint_lib.generated(lo)[0] != footprint_lib.generated(up)[0]


# ── the harness ──────────────────────────────────────────────────────────────
#: Wires whose plug, in the wrong header, silently changes what the brake,
#: the kill or the motor does, or puts pack voltage where it does not belong.
SENSITIVE_NETS = {"HV_BPLUS", "KSW", "LEVER_L", "LEVER_R", "BL", "ACC_PLUS",
                  "RUN", "BOOST_OUT"}


def _fitted_harness(d):
    return [c for c in d.connectors if c.leaves_box and not c.dnp]


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
