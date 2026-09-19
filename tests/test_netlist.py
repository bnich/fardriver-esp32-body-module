"""Requirements on THE DESIGN, asked of the netlist by walking its copper.

`tools/integrity.py` answers "does every leg of every part go somewhere?".
These tests ask the next question: does the circuit those legs form do the
job? Each one states a requirement from `docs/plan.md`, `brake-circuit.md` or
a manufacturer's datasheet and then WALKS the nets to see whether it holds --
gate -> resistor -> FET -> ground -- instead of reading a label.

Nothing here counts parts or pastes a value back at the file that holds it.
Where a number appears, it is the requirement's own: a datasheet limit, a
rail voltage, a pin list printed by the manufacturer.
"""
import inspect
import re
from collections import deque
from dataclasses import replace

import pytest

from tools import integrity, netlist
from tools.model import DOMAIN_VOLTS
from tools.netlist import BOARDS

#: Supply and return nets. A walk may ARRIVE at one but never passes THROUGH:
#: everything is "connected" through ground, and that proves nothing.
RAILS = {"GND", "BASEPLATE", "V12", "V5", "V3P3"}
FETS = {"NFET", "PFET"}
DC_PATH = {"R", "L", "CMCHOKE", "FUSE", "FUSECLIP"}   # conducts DC, both ways


class Walker:
    """The netlist as a graph: nets are nodes, parts join the nets they touch."""

    def __init__(self, design):
        self.d = design
        self.pin_net = {(r, p): n.name for n in design.nets for r, p in n.pins}
        self.parts = {p.refdes: p for p in design.parts}
        self.conns = {c.refdes: c for c in design.connectors}

    def net(self, refdes, pin):
        assert (refdes, pin) in self.pin_net, f"{refdes}.{pin} is on no net"
        return self.pin_net[(refdes, pin)]

    def nets_of(self, part):
        return {self.pin_net[(part.refdes, q)] for q in part.pins}

    def parts_on(self, net, kinds=None, board=None):
        out = []
        for ref, _pin in self.d.net(net).pins:
            p = self.parts.get(ref)
            if p is None or p in out:
                continue
            if (kinds is None or p.kind in kinds) and board in (None, p.board):
                out.append(p)
        return out

    def connectors_on(self, net):
        return [self.conns[r] for r, _ in self.d.net(net).pins if r in self.conns]

    def between(self, net_a, net_b, kinds):
        return [p for p in self.parts_on(net_a, kinds)
                if net_b in self.nets_of(p) and net_a != net_b]

    def walk(self, start, kinds, board=None):
        """Every net reachable from `start` through parts of `kinds`."""
        seen, todo = {start}, deque([start])
        while todo:
            here = todo.popleft()
            if here in RAILS and here != start:
                continue
            for part in self.parts_on(here, kinds, board):
                for nxt in self.nets_of(part) - seen:
                    seen.add(nxt)
                    todo.append(nxt)
        return seen


def ohms(part):
    """'4k7' -> 4700, '100R' -> 100, '1k00 1%' -> 1000, '0R' -> 0."""
    m = re.match(r"^(\d+)([kRM])(\d*)", part.value)
    assert m, f"{part.refdes}: cannot read a resistance from {part.value!r}"
    whole, unit, frac = m.groups()
    return float(f"{whole}.{frac or 0}") * {"R": 1, "k": 1e3, "M": 1e6}[unit]


def series_to(w, start, target):
    """Total resistance of THE resistor chain from `start` to `target`.

    Depth-first through resistors only, never through a rail; more than one
    chain, or none, is a failure -- the requirement is a single series string.
    """
    chains = []

    def explore(here, used, total):
        if here == target:
            chains.append(total)
            return
        if here in RAILS and here != start:
            return
        for r in w.parts_on(here, {"R"}):
            if r.refdes not in used:
                (nxt,) = w.nets_of(r) - {here}
                explore(nxt, used | {r.refdes}, total + ohms(r))

    explore(start, frozenset(), 0.0)
    assert len(chains) == 1, (
        f"expected one resistor chain {start} -> {target}, found {len(chains)}")
    return chains[0]


@pytest.fixture(scope="module")
def d():
    return netlist.current()


@pytest.fixture(scope="module")
def w(d):
    return Walker(d)


# ─── the design is a circuit, and every entry can be walked back to a source ──

def test_the_structural_gate_is_clean(d):
    assert integrity.check(d) == []


def test_every_entry_cites_a_source(d):
    assert [p.refdes for p in d.parts if not p.source.strip()] == []
    assert [n.name for n in d.nets if not n.source.strip()] == []
    assert [c.refdes for c in d.connectors if not c.source.strip()] == []


def test_every_part_is_fully_described(d):
    rated = {"C", "D", "ZENER", "TVS", "NFET", "PFET"}
    for p in d.parts:
        assert p.board in BOARDS, p.refdes
        assert p.pins, f"{p.refdes} declares no pins"
        assert p.height_mm > 0, f"{p.refdes} has no height"
        assert min(p.footprint_mm) > 0, f"{p.refdes} has no footprint"
        if p.kind in rated:
            assert p.v_max, f"{p.refdes} ({p.kind}) states no voltage rating"


def test_a_confirmed_height_names_the_pdf_and_the_page(d):
    for x in list(d.parts) + list(d.connectors):
        if x.height_confirmed:
            assert ".pdf" in x.source and re.search(r"p\.\d+", x.source), (
                f"{x.refdes} claims a confirmed height without citing a "
                f"manufacturer PDF and page")


def test_every_no_connect_is_argued_in_the_source(d):
    for p in d.parts:
        if p.nc:
            assert "nc " in p.source, f"{p.refdes} leaves {p.nc} open unargued"


#: Pin lists as the manufacturers print them. `pins` + `nc` must be exactly
#: this. A part that declares fewer pins than it has hides exactly the pins
#: that matter: an enable that must be strapped, a current-limit pin, an
#: address strap that 'must be externally biased'.
DATASHEET_PINS = {
    # Espressif WROOM-1 datasheet v1.8 Table 3-1. TXD0 = GPIO43, RXD0 = GPIO44.
    "U401": {"GND", "3V3", "EN", "EPAD"} | {f"IO{n}" for n in (
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19,
        20, 21, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48)},
    # TI SLVSCV8E Table 5-1, version B.
    "U301": {"GND", "IN1", "IN2", "IN3", "IN4", "SEH", "SEL", "FAULT", "CS",
             "CL", "THER", "DIAG_EN", "OUT1", "OUT2", "OUT3", "OUT4", "VS",
             "NC", "PAD"},
    # Microchip DS20001952D Table 2-1, SPDIP.
    "U402": {f"GP{port}{bit}" for port in "AB" for bit in range(8)} | {
        "VDD", "VSS", "NC11", "SCK", "SDA", "NC14", "A0", "A1", "A2",
        "RESET", "INTA", "INTB"},
    # TI SLOS346O pin functions.
    "U404": {"D", "GND", "VCC", "R", "Vref", "CANL", "CANH", "RS"},
    # TI SLVSE84D Table 5-1, DGN fixed.
    "U405": {"OUT", "SNS", "NC", "GND", "EN", "IN", "PAD"},
    # TDK CN50-150B110 instruction manual p.5, plus the baseplate M3 holes.
    "U201": {"-Vin", "CNT", "+Vin", "-V", "-S", "TRM", "+S", "+V", "BASEPLATE"},
    # Cincon EC7BW-110 datasheet p.7.
    "U202": {"+Vin", "-Vin", "+Vout", "Trim", "-Vout", "Remote"},
}
DATASHEET_PINS["U302"] = DATASHEET_PINS["U301"]
DATASHEET_PINS["U403"] = DATASHEET_PINS["U402"]


@pytest.mark.parametrize("refdes", sorted(DATASHEET_PINS))
def test_ic_pin_lists_are_the_datasheets_not_a_convenient_subset(d, refdes):
    part = d.part(refdes)
    declared = set(part.pins) | set(part.nc)
    assert declared == DATASHEET_PINS[refdes], (
        f"{refdes}: missing {sorted(DATASHEET_PINS[refdes] - declared)}, "
        f"invented {sorted(declared - DATASHEET_PINS[refdes])}")


# ─── voltage classes and ratings ─────────────────────────────────────────────

def test_every_net_states_a_voltage_nobody_has_to_guess(d):
    assert [n.name for n in d.nets if n.domain not in DOMAIN_VOLTS] == []
    for name in ("LEVER_L", "LEVER_R", "Q1_GATE"):
        assert d.net(name).domain == "12V", (
            f"{name} idles at ~11.4 V (brake-circuit.md §3); a lower class "
            f"lets a 5 V clamp hold the stop lamp on")
    assert d.net("GND").domain == d.net("BASEPLATE").domain == "GND"
    assert d.net("V5").domain == "5V"


def test_84_volts_never_reaches_the_logic_boards(d):
    for net in d.nets:
        if net.domain == "84V":
            boards = {d.board_of(r) for r, _ in net.pins}
            assert boards <= {"HVIN", "CONV"}, (net.name, boards)


def test_a_part_tied_to_ground_is_rated_for_the_node_it_sits_on(d, w):
    """Capacitors, diodes, zener-free clamps: one leg on GND, the other on a
    node -- the part sees that node's whole working voltage."""
    for p in d.parts:
        if p.kind not in {"C", "D", "TVS"} or len(p.pins) != 2:
            continue
        nets = [d.net(n) for n in w.nets_of(p)]
        if len(nets) == 2 and any(n.domain == "GND" for n in nets):
            live = max(DOMAIN_VOLTS[n.domain] for n in nets)
            assert p.v_max >= live, (
                f"{p.refdes} is rated {p.v_max} V on a {live} V node")


def test_a_tvs_never_conducts_at_its_nets_working_voltage(d, w):
    """The 5 V-array-on-an-11.4 V-node class, closed for every TVS channel."""
    for p in d.parts:
        if p.kind != "TVS":
            continue
        for net_name in w.nets_of(p):
            volts = DOMAIN_VOLTS[d.net(net_name).domain]
            assert p.v_max >= volts, (
                f"{p.refdes} (V_RWM {p.v_max} V) sits on {net_name}, a "
                f"{volts} V node: it would conduct continuously")


# ─── D13: the module's 84 V power switch ─────────────────────────────────────

def test_q101_is_turned_on_by_a_dc_path_from_its_gate_to_ground_through_q105(w):
    gate = w.net("Q101", "G")
    through_resistors = w.walk(gate, {"R"})
    assert w.net("Q105", "D") in through_resistors, (
        "no resistor chain joins Q101's gate to Q105's drain: nothing can "
        "pull a high-side P-FET's gate below its source, so it never turns on")
    assert w.net("Q105", "S") == "GND"
    assert w.parts["Q105"].kind == "NFET" and w.parts["Q101"].kind == "PFET"
    assert "GND" not in through_resistors, (
        "a resistor path reaches GND without passing Q105: the module would "
        "draw from the pack with the key off (D9)")


def test_q101_biases_off_with_a_gate_to_source_resistor(w):
    assert w.between(w.net("Q101", "G"), w.net("Q101", "S"), {"R"}), (
        "D14: a P-channel high-side switch biases OFF to its own SOURCE")


def test_q101_gate_drive_stays_inside_the_part_at_every_pack_voltage(w):
    gate, source = w.net("Q101", "G"), w.net("Q101", "S")
    r_gs = ohms(w.between(gate, source, {"R"})[0])
    r_pd = series_to(w, gate, w.net("Q105", "D"))
    for pack in (60.0, 84.0, 90.7):          # LVC · full charge · charger OVP
        v_gs = pack * r_gs / (r_gs + r_pd)
        assert 8.0 <= v_gs <= 20.0, (
            f"V_GS = -{v_gs:.1f} V at {pack} V: outside full enhancement "
            f"(>= 8 V) .. the IXTP26P20P's +/-20 V gate rating")
    clamp = [z for z in w.between(gate, source, {"ZENER"})]
    assert clamp and clamp[0].v_max < 20.0, "no zener holds V_GS under 20 V"
    assert w.net(clamp[0].refdes, "K") == source, "gate zener is backwards"


def test_q105_is_driven_by_the_key_and_biases_off_without_it(d, w):
    en = w.net("Q105", "G")
    key_tap = [cp.net for cp in d.connector("J102").pins if cp.net != "GND"]
    assert len(key_tap) == 1
    assert key_tap[0] in w.walk(en, {"R"}), "Q105's gate is not fed from the key"
    assert w.between(en, "GND", {"R"}), "D14: nothing pulls Q105's gate to GND"
    r_top = series_to(w, en, key_tap[0])
    r_bot = ohms(w.between(en, "GND", {"R"})[0])
    clamp = w.between(en, "GND", {"ZENER"})
    assert clamp and clamp[0].v_max <= 20.0, "BSS127 V_GS is +/-20 V"
    for pack, need in ((43.0, 2.6), (84.0, 2.6)):   # converter UVLO · full
        v = pack * r_bot / (r_top + r_bot)
        assert need < v < clamp[0].v_max, (
            f"D13_EN = {v:.2f} V at {pack} V: must clear V_GS(th) max 2.6 V "
            f"and stay under its own clamp")


def test_the_miller_cap_survives_the_input_tvs_clamp(w):
    caps = w.between(w.net("Q101", "G"), w.net("Q101", "D"), {"C"})
    assert caps, "no gate-to-drain capacitor sets D13's output slew"
    assert caps[0].v_max >= 146.0, (
        "with the switch off it holds the pack, and 146 V at the SMCJ90A's "
        "clamp (Littelfuse: V_C 146 V @ 10.3 A)")


def test_a_gate_to_source_cap_tames_the_plug_in_dvdt(w):
    assert w.between(w.net("Q101", "G"), w.net("Q101", "S"), {"C"}), (
        "without it the Miller cap drags the gate down as the XT90-S is "
        "plugged in, and the module turns on with the key OFF")


def test_the_module_only_taps_the_key_line_it_never_switches_it(d, w):
    """D10: the key switch feeds the FarDriver KEY wire in
    the harness. No FET of ours is in that path and no latch exists."""
    deleted = {"U101", "Q102", "Q103", "Q104", "D103", "D105", "R102", "C106",
               "R103", "R104", "R105", "R106", "R111", "J103"}
    assert [r for r in deleted if d.has(r)] == [], "a start-latch part is back"
    mpns = " ".join(p.mpn for p in d.parts)
    assert "74HC14" not in mpns, "the latch's Schmitt inverter is back"
    assert "BSS126" not in mpns, "BSS126 is DEPLETION mode: on at V_GS = 0"
    assert [p.refdes for p in d.parts
            if p.kind == "PFET" and (p.v_max or 0) >= DOMAIN_VOLTS["84V"]] == ["Q101"], (
        "one 84 V P-FET: the module's own power switch")
    ksw = [cp.net for cp in d.connector("J102").pins if cp.net != "GND"][0]
    assert not w.parts_on(ksw, FETS), "a FET sits on the key line"
    assert {cp.net for cp in d.connector("J102").pins} == {ksw, "GND"}


def test_key_sense_reads_the_key_switch_output(d, w):
    ksw = [cp.net for cp in d.connector("J102").pins if cp.net != "GND"][0]
    assert ksw in w.walk("KEY_SENSE", {"R"})
    top = series_to(w, "KEY_SENSE", ksw)
    bottom = ohms(w.between("KEY_SENSE", "GND", {"R"})[0])
    assert 84.0 * bottom / (top + bottom) < 3.1, "over the S3's ADC range"


# ─── the converters ──────────────────────────────────────────────────────────

def test_cm_chokes_are_four_terminal_with_both_windings_in_circuit(d, w):
    chokes = [p for p in d.parts if p.kind == "CMCHOKE"]
    converters = [p for p in d.parts if p.kind == "CONVERTER"]
    assert len(chokes) == len(converters) > 0, "one choke per converter input"
    switched = w.net("Q101", "D")
    for choke in chokes:
        nets = [w.net(choke.refdes, q) for q in choke.pins]
        assert len(choke.pins) == 4 and len(set(nets)) == 4
        assert switched in nets and "GND" in nets, (
            f"{choke.refdes}: one winding carries the feed, the other the "
            f"return -- a single winding saturates on DC")


def test_each_converter_return_meets_ground_only_through_its_choke(d, w):
    for conv in (p for p in d.parts if p.kind == "CONVERTER"):
        ret = w.net(conv.refdes, "-Vin")
        assert ret != "GND", f"{conv.refdes} -Vin is tied straight to GND"
        dc = w.parts_on(ret, DC_PATH)
        assert [p.kind for p in dc] == ["CMCHOKE"], (
            f"{conv.refdes}: -Vin's DC paths are {[p.refdes for p in dc]}")


def test_the_tdk_brick_is_enabled_and_locally_sensed(w):
    """TDK manual p.18: CNT open = OFF. p.17: unused sense pins strap to the
    output. Unlanded, the 12 V rail -- and the brake lamp -- never come up."""
    assert w.net("U201", "CNT") == w.net("U201", "-Vin")
    assert w.net("U201", "+S") == w.net("U201", "+V") == "V12"
    assert w.net("U201", "-S") == w.net("U201", "-V") == "GND"


def test_the_tdk_brick_has_the_output_network_its_manual_requires(w):
    out_caps = w.between("V12", "GND", {"C"})
    bulk = [c for c in out_caps if c.board == "CONV" and set(c.pins) == {"+", "-"}]
    assert bulk and bulk[0].v_max >= 25.0, "TDK Table 6-1: 25 V 680 uF solid"
    plate = w.net("U201", "BASEPLATE")
    assert w.between("V12", plate, {"C"}) and w.between("GND", plate, {"C"})


def test_the_baseplate_is_tied_to_ground_not_left_to_float(w):
    plate = w.net("U201", "BASEPLATE")
    assert w.between(plate, "GND", {"R"}), (
        "a shorted Y2 must blow the fuse, not float a plate at 84 V")


def test_the_hold_up_cap_serves_the_logic_converter_alone(d, w):
    hold = w.net("U202", "+Vin")
    assert hold != w.net("U201", "+Vin")
    assert w.between(hold, w.net("U202", "-Vin"), {"C"}), "C2 is missing"
    assert not w.parts_on(hold, {"CMCHOKE"}), "C2 must sit BEHIND the diode"
    upstream = w.walk(hold, {"FUSE", "D"})
    assert any(w.parts_on(n, {"CMCHOKE"}) for n in upstream)
    kinds = {p.kind for n in upstream for p in w.parts_on(n, {"FUSE", "D"})}
    assert kinds == {"FUSE", "D"}, "both the 1 A fuse and the diode are needed"


def test_the_fuse_sits_in_clips_not_the_47mm_holder(d, w):
    assert not [p.refdes for p in d.parts if "0031.3803" in p.mpn]
    for fuse in (p for p in d.parts if p.kind == "FUSE"):
        for pin in fuse.pins:
            assert w.parts_on(w.net(fuse.refdes, pin), {"FUSECLIP"}), (
                f"{fuse.refdes}.{pin} has no clip")


# ─── DRV: the smart switches ─────────────────────────────────────────────────

def _tps(d):
    return [p for p in d.parts if p.mpn.startswith("TPS4H160B")]


def test_tps4h160b_has_a_current_limit_and_a_sense_resistor(d, w):
    assert _tps(d)
    for u in _tps(d):
        assert w.between(w.net(u.refdes, "CL"), "GND", {"R"}), (
            f"{u.refdes}: CL open or grounded is an 8-14 A 'limit' (D15)")
        assert w.between(w.net(u.refdes, "CS"), "GND", {"R"}), (
            f"{u.refdes}: CS is a current output and needs R(CS)")


def test_nothing_but_the_open_drain_fault_joins_a_tps_pin_to_the_mcu(d, w):
    """CS pulls to 4.5-6.5 V in any fault; TI wants series resistors on every
    logic line. Only FAULT (open-drain, pulls LOW) may share a net."""
    for u in _tps(d):
        for pin in u.pins:
            net = d.net(w.net(u.refdes, pin))
            if net.name not in RAILS and any(r == "U401" for r, _ in net.pins):
                assert pin == "FAULT", f"{u.refdes}.{pin} meets U401 directly"


#: The two TPS4H160B channels no firmware commands: U301 OUT1 is AUX12, a
#: current-limited FEED held on from V3P3, and U302 OUT4 is the STOP lamp, whose
#: IN4 the hardware brake circuit drives (D23).  (device, input) -> source net.
HARDWARE_INPUTS = {("U301", "IN1"): "V3P3", ("U302", "IN4"): "STOP_CMD"}


def test_every_used_tps_input_is_reachable_from_the_mcu_and_unused_ones_are_off(d, w):
    for u in _tps(d):
        for n in "1234":
            out, inp = w.net(u.refdes, f"OUT{n}"), w.net(u.refdes, f"IN{n}")
            src = HARDWARE_INPUTS.get((u.refdes, f"IN{n}"))
            reach = w.walk(inp, {"R"})
            if src:
                assert src in reach, f"{u.refdes}.IN{n} is not driven from {src}"
                assert not any(d.net(x).gpio for x in reach), (
                    f"{u.refdes}.IN{n} is a hardware input, yet a GPIO reaches it")
            elif w.connectors_on(out):
                assert any(d.net(x).gpio for x in reach), (
                    f"{u.refdes}.IN{n} drives a lamp but no GPIO reaches it")
            else:
                assert inp == "GND", f"{u.refdes}.IN{n} is unused yet not held off"


def test_every_ic_is_decoupled_on_every_rail_it_touches(d, w):
    for u in (p for p in d.parts if p.kind in {"IC", "MODULE"}):
        for rail in w.nets_of(u) & {"V12", "V5", "V3P3"}:
            caps = [c for c in w.between(rail, "GND", {"C"}) if c.board == u.board]
            assert caps, f"{u.refdes} has no capacitor on {rail} on {u.board}"


def test_inductive_loads_have_a_flyback_path(d, w):
    """Across the load: from its switched return to its OWN + feed, AUX12."""
    for net in ("FAN_RTN", "BUZZ_RTN"):
        diodes = [x for x in w.between(net, "AUX12", {"D"})
                  if w.net(x.refdes, "A") == net and w.net(x.refdes, "K") == "AUX12"]
        assert diodes, f"{net}: the AO3400A has no avalanche rating"


def test_every_low_side_gate_biases_off(d, w):
    """D14: a hung or booting module drives no load."""
    for q in (p for p in d.parts if p.kind == "NFET" and w.net(p.refdes, "S") == "GND"):
        gate = w.net(q.refdes, "G")
        assert w.between(gate, "GND", {"R"}), f"{q.refdes}'s gate floats"


def test_lamp_commons_are_ground(d, w):
    assert not [n.name for n in d.nets if "COMMON" in n.name.upper()]
    # AUX12 is a FEED: its loads return through their own low-side switch in
    # the same connector (test_every_aux12_load_returns_through_its_switch).
    lamp_nets = {w.net(u.refdes, f"OUT{n}") for u in _tps(d) for n in "1234"} - {"AUX12"}
    for c in d.connectors:
        if {cp.net for cp in c.pins} & lamp_nets and c.board == "DRV" \
                and not c.parked:
            assert "GND" in {cp.net for cp in c.pins}, (
                f"{c.refdes} feeds a lamp and offers it no return")


def test_every_aux12_load_returns_through_its_switch(d, w):
    for c in w.connectors_on("AUX12"):
        rets = [cp.net for cp in c.pins if cp.net not in ("AUX12", "")]
        assert rets, f"{c.refdes} feeds AUX12 with no return"
        for net in rets:
            assert [q for q in w.parts_on(net, {"NFET"}) if w.net(q.refdes, "D") == net
                    and w.net(q.refdes, "S") == "GND"], (
                f"{c.refdes}: {net} is no low-side switch's drain")


# ─── protection ──────────────────────────────────────────────────────────────

def _arrays(d):
    return [p for p in d.parts if p.kind == "TVS" and len(p.pins) > 2]


def test_every_tvs_array_returns_to_ground_beside_a_connector_it_protects(d, w):
    """The requirement, whatever the package: a multi-line protection part has
    a real return to ground and sits on the board of a connector it serves.

    SC-74 quad arrays (pads K1 A2 K3 K4 A5 K6) must have BOTH anodes on GND --
    one floating anode halves the clamp and passes every label-based check.
    """
    from tools.netlist import TVS_ARRAY_PINS
    assert _arrays(d)
    for a in _arrays(d):
        landed = {q: w.net(a.refdes, q) for q in a.pins}
        if tuple(a.pins) == tuple(TVS_ARRAY_PINS):
            anodes = [q for q in a.pins if q.startswith("A")]
            assert len(anodes) == 2, f"{a.refdes}: SC-74 arrays have two anode pads"
            for q in anodes:
                assert landed[q] == "GND", f"{a.refdes}.{q} is not on GND"
        assert "GND" in landed.values(), f"{a.refdes} has no pin on GND"
        protected = set(landed.values()) - {"GND"}
        assert protected, f"{a.refdes} protects nothing"
        mates = [c for n in protected for c in w.connectors_on(n)
                 if c.board == a.board and not c.interface]
        assert mates, f"{a.refdes} is on {a.board}, away from any connector it serves"


def _resistive_input(d, w, net):
    """Every on-board part the wire reaches is a fitted resistor of ≥ 100 kΩ:
    it can push only microamps in, and a clamp would add a part that fails
    short (KSW: that blows the key fuse)."""
    parts = w.parts_on(net)
    return bool(parts) and all(p.kind == "R" and not p.dnp and ohms(p) >= 100e3
                               for p in parts)


def test_every_wire_that_leaves_the_box_has_a_tvs_on_its_own_board(d, w):
    for c in d.connectors:
        if not c.leaves_box:
            continue
        for cp in c.pins:
            if cp.net in ("", "GND") or _resistive_input(d, w, cp.net):
                continue
            tvs = [t for t in w.parts_on(cp.net, {"TVS"}, board=c.board)
                   if c.parked or not t.dnp]
            assert tvs, f"{c.refdes}.{cp.pin} ({cp.net}) leaves {c.board} unprotected"


def test_no_quad_array_touches_a_raw_rail_and_v12_has_its_own_clamp(d, w):
    for a in _arrays(d):
        assert not w.nets_of(a) & {"V12", "V5", "V3P3"}, (
            f"{a.refdes}: the TDK's OVP window overlaps the array's V_BR")
    single = [t for t in w.between("V12", "GND", {"TVS"}) if len(t.pins) == 2]
    assert len(single) == 1 and single[0].board == "DRV"
    assert w.net(single[0].refdes, "K") == "V12"


def test_unidirectional_clamps_point_the_right_way(d, w):
    for t in (p for p in d.parts if p.kind in {"TVS", "ZENER"} and len(p.pins) == 2):
        a, k = d.net(w.net(t.refdes, "A")), d.net(w.net(t.refdes, "K"))
        assert DOMAIN_VOLTS[k.domain] >= DOMAIN_VOLTS[a.domain], (
            f"{t.refdes}: cathode on {k.name}, anode on {a.name}")


# ─── D23: brake cutoff, brake lamp and run/off kill are hardware, on DRV ──────

D23_NETS = ("LEVER_L", "LEVER_R", "Q1_GATE", "BL", "Q2_GATE", "ACC_PLUS",
            "TAIL_STOP")


def test_d23_hardware_touches_no_board_but_drv(d):
    for name in D23_NETS:
        boards = {d.board_of(r) for r, _ in d.net(name).pins}
        assert boards == {"DRV"}, f"{name} depends on {sorted(boards - {'DRV'})}"


@pytest.mark.parametrize("lever", ["LEVER_L", "LEVER_R"])
def test_a_lever_cuts_the_motor_and_lights_the_lamp_through_drv_parts_alone(d, w, lever):
    assert [c.refdes for c in w.connectors_on(lever) if c.leaves_box and c.board == "DRV"]
    reached = w.walk(lever, {"D"}, board="DRV")
    assert "BL" in reached, f"{lever} has no diode path to BL on DRV"
    for line in ("BL", "Q1_GATE"):
        steer = w.between(lever, line, {"D"})
        assert steer and all(w.net(x.refdes, "K") == lever for x in steer), (
            f"{lever} -> {line}: the cathode faces the lever node")
    lamp_switch = [q for q in w.parts_on("Q1_GATE", {"PFET"}, board="DRV")
                   if w.net(q.refdes, "G") == "Q1_GATE"]
    assert lamp_switch, "nothing on DRV switches the stop lamp"
    q1 = lamp_switch[0]
    assert w.net(q1.refdes, "S") == "V12"
    assert w.between("Q1_GATE", "V12", {"R"}), "Q1's gate has no pull-up: lamp stuck on"
    # Q1's drain commands exactly one TPS4H160B input, and that channel's
    # output is the lamp wire leaving DRV -- with no GPIO anywhere on the way.
    cmd = w.net(q1.refdes, "D")
    path = w.walk(cmd, {"R"})
    ins = [(u, n) for u in _tps(d) for n in "1234" if w.net(u.refdes, f"IN{n}") in path]
    assert len(ins) == 1, f"Q1's drain reaches TPS inputs {ins}"
    u, n = ins[0]
    assert u.board == "DRV" and not any(d.net(x).gpio for x in path | {cmd})
    stop = w.net(u.refdes, f"OUT{n}")
    assert [c for c in w.connectors_on(stop) if c.leaves_box and c.board == "DRV"]


def test_bl_leaves_the_box_from_drv_and_only_a_copy_goes_to_brain(d, w):
    exits = [c for c in w.connectors_on("BL") if c.leaves_box]
    assert exits and all(c.board == "DRV" for c in exits)
    assert not [c for c in w.connectors_on("BL") if c.interface], (
        "BL itself crosses an inter-board connector: one walked-out contact "
        "and the motor cut fails open, silently")
    copy = w.between("BL", "BL_SENSE", {"R"})
    assert copy and ohms(copy[0]) >= 100e3
    assert w.parts_on("BL_SENSE") and not w.between("BL", "BL_SENSE", FETS | {"D"})


def test_the_run_switch_kills_through_drv_parts_and_fails_safe(d, w):
    kill = [q for q in w.parts_on("BL", {"NFET"}, board="DRV")
            if w.net(q.refdes, "D") == "BL"]
    assert kill, "no FET on DRV can hold BL low"
    q2 = kill[0]
    assert w.net(q2.refdes, "S") == "GND", "Q2 has no source: it cannot pull BL"
    gate = w.net(q2.refdes, "G")
    assert "RUN" in w.walk(gate, {"R"}, board="DRV"), "RUN never reaches Q2's gate"
    assert w.between(gate, "GND", {"R"}), "D14: Q2's gate has no bias-OFF"
    pullups = [r for r in w.parts_on("RUN", {"R"}, board="DRV")
               if w.nets_of(r) - {"RUN"} <= {"ACC_PLUS"}]
    assert pullups, ("RUN's pull-up must be ON DRV: then an open pod, STACK "
                     "or BRAIN leaves the node high = OFF = motor cut")
    feed = w.connectors_on("ACC_PLUS")
    assert feed and all(c.board == "DRV" and c.leaves_box for c in feed)


def test_the_run_node_reads_as_a_valid_high_everywhere_it_is_read(w):
    """RUN open = pulled to ACC+ (5.1 V), loaded by Q2's gate network AND the
    IN-11 divider. It must turn Q2 hard on and clear the MCP23017's V_IH."""
    r_pu = ohms(w.between("RUN", "ACC_PLUS", {"R"})[0])
    gate = w.net(w.between("RUN", "Q2_GATE", {"R"})[0].refdes, "2")
    r_gate = series_to(w, "RUN", "Q2_GATE") + ohms(w.between(gate, "GND", {"R"})[0])
    r_top = ohms(w.between("RUN", "IN11_SENSE", {"R"})[0])
    r_bot = ohms(w.between("IN11_SENSE", "GND", {"R"})[0])
    load = 1 / (1 / r_gate + 1 / (r_top + r_bot))
    node = 5.1 * load / (r_pu + load)
    sense = node * r_bot / (r_top + r_bot)
    assert node >= 2.5, f"RUN = {node:.2f} V: AO3400A is specified at V_GS 2.5 V"
    assert 0.8 * 3.3 + 0.3 <= sense <= 3.3, (
        f"IN-11 = {sense:.2f} V: needs >= 0.3 V over V_IH (0.8 x VDD = 2.64 V) "
        f"and must not exceed VDD")


def test_brake_inputs_are_pulled_up_on_drv_from_a_3v3_that_really_arrives(d, w):
    # The pull-up sits on the D23 sense node, AHEAD of the class-A series
    # resistor -- so the lever, its diode and its pull-up are all on DRV, and
    # only the conditioned signal crosses to the MCU.
    for node, wire in (("IN05_NODE", "IN05_BRAKE_L"), ("IN06_NODE", "IN06_BRAKE_R")):
        pull = w.between(node, "V3P3", {"R"})
        assert pull and pull[0].board == "DRV"
        series = w.between(node, wire, {"R"})
        assert series and series[0].board == "DRV", f"{wire} has no series resistor"
        assert series[0].value == "1k"
        assert any(p.kind == "C" and p.board == "BRAIN" for p in w.parts_on(wire, {"C"})), \
            f"{wire} has no capacitor at the MCU pin (plan §4 class A)"
    on_drv = [c for c in w.connectors_on("V3P3") if c.board == "DRV" and c.interface]
    assert on_drv, "V3P3 has no contact onto DRV"


# ─── BRAIN ───────────────────────────────────────────────────────────────────

def test_no_net_lands_on_a_pad_the_module_does_not_have(d):
    u401 = d.part("U401")
    for ghost in ("IO33", "IO34"):
        assert ghost not in u401.pins + u401.nc, f"the WROOM-1 has no {ghost} pad"
        assert d.net_of("U401", ghost) is None, f"a net lands on U401.{ghost}"


def test_the_mcp23017_output_only_bits_carry_nothing(d):
    for u in ("U402", "U403"):
        for bit in ("GPA7", "GPB7"):
            assert d.net_of(u, bit) is None, f"{u}.{bit} is OUTPUT-ONLY (DS20001952D)"
            assert bit in d.part(u).nc


def test_the_mcp23017s_are_biased_addressed_apart_and_held_out_of_reset(d, w):
    addresses = []
    for u in ("U402", "U403"):
        straps = tuple(w.net(u, a) for a in ("A2", "A1", "A0"))
        assert set(straps) <= {"GND", "V3P3"}, f"{u}: 'Must be externally biased'"
        addresses.append(straps)
        assert w.between(w.net(u, "RESET"), "V3P3", {"R"}), f"{u} RESET floats"
    assert addresses[0] != addresses[1], "both expanders answer at one address"


def test_the_module_has_its_reset_rc_and_a_recovery_path(d, w):
    en = w.net("U401", "EN")
    assert w.between(en, "V3P3", {"R"}) and w.between(en, "GND", {"C"}), (
        "Espressif: CHIP_PU must not float; RC = 10 k / 1 uF")
    service = [c for c in d.connectors if not c.leaves_box and not c.interface
               and {en, w.net("U401", "IO0")} <= {cp.net for cp in c.pins}]
    assert service, "no internal header brings out EN and IO0 for recovery"
    nets = {cp.net for cp in service[0].pins}
    assert {w.net("U401", "IO43"), w.net("U401", "IO44"), "V3P3", "GND"} <= nets


def test_the_pin_map_obeys_the_silicon(d, w):
    by_gpio = {n.gpio: n for n in d.nets if n.gpio}
    adc1 = {f"GPIO{n}" for n in range(1, 11)}
    for analog in ("KEY_SENSE", "V12_SENSE", "CS1", "CS2"):
        assert d.net(analog).gpio in adc1, f"{analog}: ADC2 dies with WiFi"
    for strap in ("GPIO0", "GPIO3", "GPIO45", "GPIO46", "GPIO43"):
        if strap in by_gpio:
            wires = [c.refdes for c in w.connectors_on(by_gpio[strap].name) if c.leaves_box]
            assert not wires, f"{strap} reaches the harness on {wires}"
    assert d.net("TWAI_TX").gpio == "GPIO10" and d.net("TWAI_RX").gpio == "GPIO21"
    assert d.net("FAN_CMD").gpio == "GPIO6", "GPIO44's boot pull-up sits at V_th"
    assert d.net("UART2_RX").gpio == "GPIO44"
    drivers = {n.gpio for n in d.nets if n.gpio and w.parts_on(n.name, FETS)}
    assert "GPIO43" not in drivers and "GPIO44" not in drivers


def test_no_harness_wire_meets_the_mcu_or_an_expander_without_a_series_element(d, w):
    for net in (n for n in d.nets if n.name not in RAILS):
        logic = {r for r, _ in net.pins} & {"U401", "U402", "U403"}
        wires = [c.refdes for c in w.connectors_on(net.name) if c.leaves_box]
        assert not (logic and wires), f"{net.name}: {wires} lands straight on {logic}"


def test_boost_is_a_dedicated_pin_that_defaults_off(d, w):
    gate = w.net("Q401", "G")
    assert w.between(gate, "GND", {"R"})
    cmd = [n for n in w.walk(gate, {"R"}) if d.net(n).gpio]
    assert len(cmd) == 1
    assert {r for r, _ in d.net(cmd[0]).pins if r.startswith("U")} == {"U401"}


def test_can_transceiver_mode_pin_and_usb_cc_are_terminated(d, w):
    assert "GND" in w.walk(w.net("U404", "RS"), {"R"}), "RS open = undefined mode"
    usb = [c for c in d.connectors if "USB" in c.name.upper()]
    assert usb
    cc = [cp.net for cp in usb[0].pins if "CC" in cp.net]
    assert len(cc) == 2 and all(w.between(n, "GND", {"R"}) for n in cc)
    assert all(abs(ohms(w.between(n, "GND", {"R"})[0]) - 5100) < 1 for n in cc), (
        "USB Type-C: Rd = 5.1 k marks a device")


# ─── interfaces and connectors ───────────────────────────────────────────────

#: The contract between DRV and BRAIN: these nets cross STACK, and no others.
STACK_CONTRACT = {
    "LGT_LOW", "LGT_HIGH", "LGT_DRL", "LGT_TAIL", "LGT_TURN_L", "LGT_TURN_R",
    "DIAG_EN", "SEL", "SEH", "CS1", "CS2", "FAULT1", "FAULT2", "HORN_CMD",
    "FAN_CMD", "BUZZ_CMD", "IN05_BRAKE_L", "IN06_BRAKE_R", "V12_SENSE", "RUN",
    "CANH", "CANL", "V3P3", "BL_SENSE",
    # ACC+ divided down for firmware: without it, a missing ACC+ wire leaves the
    # run/off kill dead and nothing shows it
    "ACC_SENSE",
}


def _interface(d, name):
    return [c for c in d.connectors if c.interface == name]


def test_stack_is_2x25_and_carries_exactly_the_contracted_nets(d):
    ends = _interface(d, "STACK")
    assert {c.board for c in ends} == {"DRV", "BRAIN"}
    for c in ends:
        assert len(c.pins) == 50
        assert {cp.net for cp in c.pins} - {"", "GND"} == STACK_CONTRACT
        grounds = [cp for cp in c.pins if cp.net == "GND"]
        assert len(grounds) >= 25, "alternating grounds"
    assert ends[0].pins == ends[1].pins, "the two halves must mate pin for pin"


def test_pwr_up_shares_the_load_current_over_three_contacts(d):
    ends = _interface(d, "PWR-UP")
    assert {c.board for c in ends} == {"CONV", "DRV", "BRAIN"}
    for c in ends:
        nets = [cp.net for cp in c.pins]
        assert nets.count("V12") >= 3, "2.62 A: one fretted contact of two is 100 %"
        assert nets.count("GND") >= 4
        assert set(nets) == {"V12", "GND", "V5", "KEY_SENSE"}
    assert ends[0].pins == ends[1].pins == ends[2].pins


def test_hv_link_carries_both_converter_pairs_two_grounds_and_no_5v(d, w):
    ends = _interface(d, "HV-LINK")
    assert {c.board for c in ends} == {"HVIN", "CONV"}
    need = {w.net(u, pin) for u in ("U201",) for pin in ("+Vin", "-Vin")}
    need |= {w.net("U202", "-Vin")}
    for c in ends:
        nets = [cp.net for cp in c.pins]
        assert need <= set(nets)
        assert nets.count("GND") >= 2, "one open contact must not reroute the return"
        assert "V5" not in nets and "KEY_SENSE" in nets
        assert c.pitch_mm >= 5.08, "BD-4: 84 V on a 2.54 mm header skips pins"
    assert ends[0].pins == ends[1].pins


def test_84v_harness_connectors_keep_their_distance(d):
    for c in d.connectors:
        if c.leaves_box and any(cp.net and d.net(cp.net).domain == "84V" for cp in c.pins):
            assert c.pitch_mm >= 5.08, f"{c.refdes}: 84 V at {c.pitch_mm} mm"


def test_connectors_state_what_they_are(d):
    for c in d.connectors:
        assert c.height_mm > 0 and min(c.footprint_mm) > 0, c.refdes
        if c.interface:
            assert not c.leaves_box, f"{c.refdes}: an inter-board header is inside"
    display = [c for c in d.connectors if "DISPLAY" in c.name.upper()]
    assert display and all(c.parked for c in display), "D19: the display is parked"
    harness = [c for c in d.connectors if c.leaves_box]
    assert harness and all(c.height_confirmed for c in harness), (
        "every harness connector's height comes off a manufacturer drawing")


def test_the_telltales_follow_the_lamp_feeds_with_no_firmware(d, w):
    lamp_nets = {w.net(u.refdes, f"OUT{n}") for u in _tps(d) for n in "1234"}
    for tt in ("TT_L", "TT_R", "TT_HL"):
        assert w.walk(tt, {"R"}) & lamp_nets, f"{tt} is not fed from a lamp output"


# ─── an assertion that never fires is not a test ─────────────────────────────
# Each requirement above is run against the real design with ONE defect put
# back -- each of a kind that every label-reading check passes -- and must
# fail. Fixtures are built with model.Design's own mutators.

def move_pin(design, refdes, pin, to_net):
    lifted = design.without_pin(refdes, pin)
    return lifted.replace_net(to_net, pins=lifted.net(to_net).pins + ((refdes, pin),))


def swap_pins(design, refdes, a, b):
    net_a, net_b = design.net_of(refdes, a).name, design.net_of(refdes, b).name
    return move_pin(move_pin(design, refdes, a, net_b), refdes, b, net_a)


def fewer_v12_contacts(design):
    out = design
    for c in _interface(design, "PWR-UP"):
        first = next(cp for cp in c.pins if cp.net == "V12")
        out = out.replace_connector(c.refdes, pins=tuple(
            replace(cp, net="GND") if cp is first else cp for cp in c.pins))
    return out


DEFECTS = [
    ("the kill FET has no source",
     lambda d: d.without_pin("Q305", "S"),
     test_the_run_switch_kills_through_drv_parts_and_fails_safe, {}),
    ("the RUN pull-up sits on BRAIN",
     lambda d: d.replace_part("R314", board="BRAIN"),
     test_the_run_switch_kills_through_drv_parts_and_fails_safe, {}),
    ("the gate pull-down goes to the key line, not to a FET to ground",
     lambda d: move_pin(d, "R101B", "2", "KSW"),
     test_q101_is_turned_on_by_a_dc_path_from_its_gate_to_ground_through_q105, {}),
    ("a second pull-down bypasses Q105: on with the key off",
     lambda d: d.with_part(replace(d.part("R113"), refdes="R199"))
     .replace_net("D13_GATE", pins=d.net("D13_GATE").pins + (("R199", "1"),))
     .replace_net("GND", pins=d.net("GND").pins + (("R199", "2"),)),
     test_q101_is_turned_on_by_a_dc_path_from_its_gate_to_ground_through_q105, {}),
    ("no gate-to-source resistor",
     lambda d: d.without_part("R110"),
     test_q101_biases_off_with_a_gate_to_source_resistor, {}),
    ("a 100 k pull-down drives the gate to -42 V",
     lambda d: d.replace_part("R101A", value="0R").replace_part("R101B", value="100k"),
     test_q101_gate_drive_stays_inside_the_part_at_every_pack_voltage, {}),
    ("a 100 V Miller cap",
     lambda d: d.replace_part("C105", v_max=100.0),
     test_the_miller_cap_survives_the_input_tvs_clamp, {}),
    ("a second P-FET switches the KEY line",
     lambda d: d.with_part(replace(d.part("Q101"), refdes="Q104")),
     test_the_module_only_taps_the_key_line_it_never_switches_it, {}),
    ("the 5 V array on the lever nodes",
     lambda d: d.replace_part("D313", v_max=5.0),
     test_a_tvs_never_conducts_at_its_nets_working_voltage, {}),
    ("the lever node mislabelled as logic level",
     lambda d: d.replace_net("LEVER_L", domain="3V3"),
     test_every_net_states_a_voltage_nobody_has_to_guess, {}),
    ("a TVS array with an anode in the air",
     lambda d: d.without_pin("D313", "A5"),
     test_every_tvs_array_returns_to_ground_beside_a_connector_it_protects, {}),
    ("a TVS array on the wrong board",
     lambda d: d.replace_part("D405", board="BRAIN"),
     test_every_tvs_array_returns_to_ground_beside_a_connector_it_protects, {}),
    ("a lamp wire with a DNP array",
     lambda d: d.replace_part("D309", dnp=True),
     test_every_wire_that_leaves_the_box_has_a_tvs_on_its_own_board, {}),
    ("an array channel on raw V12",
     lambda d: move_pin(d, "D311", "K3", "V12"),
     test_no_quad_array_touches_a_raw_rail_and_v12_has_its_own_clamp, {}),
    ("the brick's enable pin left open",
     lambda d: d.without_pin("U201", "CNT"),
     test_the_tdk_brick_is_enabled_and_locally_sensed, {}),
    ("a choke with one winding in circuit",
     lambda d: d.without_pin("L101", "3"),
     test_cm_chokes_are_four_terminal_with_both_windings_in_circuit, {}),
    ("a converter return strapped to ground past its choke",
     lambda d: d.with_part(replace(d.part("R211"), refdes="R299")).with_net(
         netlist.Net("X1", (("R299", "1"),), domain="GND", source="x"))
     .replace_net("HV_C1_N", pins=d.net("HV_C1_N").pins + (("R299", "2"),)),
     test_each_converter_return_meets_ground_only_through_its_choke, {}),
    ("the hold-up cap on the common node",
     lambda d: move_pin(d, "L102", "4", "HV_C2_HOLD"),
     test_the_hold_up_cap_serves_the_logic_converter_alone, {}),
    ("a floating baseplate",
     lambda d: d.without_part("R211"),
     test_the_baseplate_is_tied_to_ground_not_left_to_float, {}),
    ("no current-limit resistor",
     lambda d: d.without_part("R319"),
     test_tps4h160b_has_a_current_limit_and_a_sense_resistor, {}),
    ("CS wired straight to the ADC pin",
     lambda d: move_pin(d, "U401", "IO4", "CS1_RAW"),
     test_nothing_but_the_open_drain_fault_joins_a_tps_pin_to_the_mcu, {}),
    ("a driver chip with no decoupling",
     lambda d: d.without_part("C303").without_part("C304")
     .without_part("C305").without_part("C306"),
     test_every_ic_is_decoupled_on_every_rail_it_touches, {}),
    ("a flyback diode fitted backwards",
     lambda d: swap_pins(d, "D314", "A", "K"),
     test_inductive_loads_have_a_flyback_path, {}),
    ("BL taken to BRAIN across STACK",
     lambda d: d.replace_net("BL", pins=d.net("BL").pins + (("J308", "49"),)),
     test_bl_leaves_the_box_from_drv_and_only_a_copy_goes_to_brain, {}),
    ("a D23 node that depends on BRAIN",
     lambda d: d.replace_part("R313", board="BRAIN"),
     test_d23_hardware_touches_no_board_but_drv, {}),
    ("a steering diode fitted backwards",
     lambda d: swap_pins(d, "D301", "A", "K"),
     test_a_lever_cuts_the_motor_and_lights_the_lamp_through_drv_parts_alone,
     {"lever": "LEVER_L"}),
    ("the IN-11 divider that reads 2.52 V",
     lambda d: d.replace_part("R431", value="100k"),
     test_the_run_node_reads_as_a_valid_high_everywhere_it_is_read, {}),
    ("CAN on pads the module does not have",
     lambda d: d.replace_net("TWAI_TX", pins=(("U401", "IO33"), ("U404", "D"))),
     test_no_net_lands_on_a_pad_the_module_does_not_have, {}),
    ("an input on an output-only expander bit",
     lambda d: move_pin(d, "U402", "GPA7", "IN07_BOOST_BTN"),
     test_the_mcp23017_output_only_bits_carry_nothing, {}),
    ("both expanders at one address",
     lambda d: move_pin(d, "U403", "A0", "GND"),
     test_the_mcp23017s_are_biased_addressed_apart_and_held_out_of_reset, {}),
    ("EN with no reset capacitor",
     lambda d: d.without_part("C412"),
     test_the_module_has_its_reset_rc_and_a_recovery_path, {}),
    ("the fan back on GPIO44",
     lambda d: d.replace_net("FAN_CMD", gpio="GPIO44"),
     test_the_pin_map_obeys_the_silicon, {}),
    ("a harness wire straight onto a GPIO",
     lambda d: move_pin(d, "U401", "IO18", "UART1_RX_WIRE"),
     test_no_harness_wire_meets_the_mcu_or_an_expander_without_a_series_element, {}),
    ("12 V over two contacts",
     fewer_v12_contacts,
     test_pwr_up_shares_the_load_current_over_three_contacts, {}),
    ("a confirmed height with nothing behind it",
     lambda d: d.replace_part("R110", height_confirmed=True),
     test_a_confirmed_height_names_the_pdf_and_the_page, {}),
    ("a part declaring fewer pins than it has",
     lambda d: d.replace_part("U301", pins=tuple(
         q for q in d.part("U301").pins if q != "CL")),
     test_ic_pin_lists_are_the_datasheets_not_a_convenient_subset,
     {"refdes": "U301"}),
]


@pytest.mark.parametrize("label, mutate, requirement, extra", DEFECTS,
                         ids=[x[0] for x in DEFECTS])
def test_each_requirement_fires_on_the_defect_it_exists_for(
        d, label, mutate, requirement, extra):
    broken = mutate(d)
    wanted = inspect.signature(requirement).parameters
    kwargs = {k: v for k, v in
              {"d": broken, "w": Walker(broken), **extra}.items() if k in wanted}
    with pytest.raises(AssertionError):
        requirement(**kwargs)


# ─── polarity and winding sense: a reversed part passes every structural gate ──

@pytest.mark.parametrize("ref,plus,minus", [
    ("C201", "HV_C1_P", "HV_C1_N"),      # TDK's bulk cap, across ITS input
    ("C202", "HV_C2_HOLD", "HV_C2_N"),   # hold-up, BEHIND the diode and fuse
    ("C207", "V12", "GND"),              # the TDK's required output capacitor
])
def test_every_polarised_capacitor_has_its_plus_on_the_higher_node(d, ref, plus, minus):
    assert d.net_of(ref, "+").name == plus, f"{ref} is reversed or on the wrong node"
    assert d.net_of(ref, "-").name == minus


@pytest.mark.parametrize("ref,anode,cathode,why", [
    ("D201", "HV_C2_P", "HV_C2_HOLD_IN", "hold-up diode conducts TOWARD converter 2"),
    ("D102", "D13_GATE", "HV_BPLUS", "gate zener: cathode on the SOURCE of a P-FET"),
    ("D106", "GND", "D13_EN", "level-shifter gate clamp: cathode on the gate"),
    ("D307", "FAN_RTN", "AUX12", "flyback: cathode on the load's feed, across it"),
    ("D314", "BUZZ_RTN", "AUX12", "flyback: cathode on the load's feed, across it"),
])
def test_every_diode_points_the_way_its_job_needs(d, ref, anode, cathode, why):
    assert d.net_of(ref, "A").name == anode, f"{ref}: {why}"
    assert d.net_of(ref, "K").name == cathode, f"{ref}: {why}"


@pytest.mark.parametrize("ref,conv", [("L101", "HV_C1"), ("L102", "HV_C2")])
def test_each_choke_carries_supply_and_return_through_opposite_windings(d, ref, conv):
    """Würth 7448022010: windings are 1-4 and 2-3. Supply in on 1, out on 4;
    return in on 3, out on 2. Cross pins 2 and 3 and the two fluxes ADD instead
    of cancelling: the core saturates on the DC and the choke filters nothing."""
    assert d.net_of(ref, "1").name == "HV_SW"
    assert d.net_of(ref, "4").name == f"{conv}_P"
    assert d.net_of(ref, "3").name == f"{conv}_N"
    assert d.net_of(ref, "2").name == "GND"


# ─── values whose wrong number passes every gate and breaks the job ────────────

@pytest.mark.parametrize("ref,value,why", [
    ("R319", "1k00 1%", "TPS4H160B #1 current limit ≈2 A; 0 Ω falls back to 8-14 A"),
    ("R320", "2k0 1%", "TPS4H160B #2 current limit ≈1 A"),
    ("R321", "1k00 1%", "CS sense resistor: I_OUT/300 × 1 k = 3.33 V/A at the pin"),
    ("R322", "1k00 1%", "CS sense resistor, package #2"),
    ("R110", "100k", "Q101 gate-source: with 540 k below it, V_GS = −13.1 V at 84 V"),
    ("R101A", "270k", "half of the 540 k pull-down that sets the ~51 ms ramp"),
    ("R101B", "270k", "half of the 540 k pull-down"),
    ("R113", "100k", "level-shifter divider bottom: 3.9 V at 43 V vs V_th ≤ 2.6 V"),
    ("R314", "1k", "'R4', the kill's pull-up from ACC+ and the toggle's 5.1 mA wetting"),
    ("R316", "100k", "'R6', Q2 gate to ground"),
    ("R317", "10k", "'R3L': 10 k keeps the low level ~0.55 V through a 1N4148"),
    ("R425", "10k", "boost: the HARD external pull-down (D14)"),
])
def test_a_value_the_circuit_depends_on(d, ref, value, why):
    assert d.part(ref).value == value, f"{ref} should be {value}: {why}"


def test_the_fuse_is_the_one_amp_time_lag_part(d):
    assert d.part("F201").value.startswith("1A T-lag"), \
        "Cincon specifies a 1 A time-delay input fuse; a 10 A link protects nothing"


def test_the_output_capacitor_is_the_size_tdk_requires(d):
    assert d.part("C207").value.startswith("680uF"), "TDK: 680 µF at the output"
    assert d.part("R211").mpn == "NET-TIE", \
        "the baseplate tie is copper -- a chip jumper can open before the fuse does"
