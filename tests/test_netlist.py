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
DC_PATH = {"R", "L", "CMCHOKE", "FUSE"}   # conducts DC, both ways


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
    for name in ("LEVER_L", "LEVER_R", "IN11_RUN_WIRE"):
        assert d.net(name).domain == "3V3", (
            f"{name} is a dry contact pulled up to 3.3 V (IO-8); a higher class "
            f"asks for a clamp that would let 12 V onto an S3 pin")
    assert d.net("AUX12").domain == "12V"
    assert d.net("GND").domain == d.net("BASEPLATE").domain == "GND"
    assert d.net("V5").domain == "5V"


def test_84_volts_never_reaches_the_logic_boards(d):
    for net in d.nets:
        if net.domain == "84V":
            boards = {d.board_of(r) for r, _ in net.pins}
            assert boards <= {"POWER"}, (net.name, boards)


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
            f"(>= 8 V) .. the IXTA26P20P's +/-20 V gate rating")
    clamp = [z for z in w.between(gate, source, {"ZENER"})]
    assert clamp and clamp[0].v_max < 20.0, "no zener holds V_GS under 20 V"
    assert w.net(clamp[0].refdes, "K") == source, "gate zener is backwards"


def test_q105_is_driven_by_the_key_and_biases_off_without_it(d, w):
    en = w.net("Q105", "G")
    key_tap = [cp.net for cp in d.connector("J101").pins
               if cp.net and d.net(cp.net).domain == "84V" and cp.net != "HV_BPLUS"]
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
    ksw = d.net_of("R112A", "1").name
    assert not w.parts_on(ksw, FETS), "a FET sits on the key line"
    assert [c.refdes for c in w.connectors_on(ksw)] == ["J101"], (
        "the key tap enters on the pack connector and goes nowhere else")


def test_key_sense_reads_the_key_switch_output(d, w):
    ksw = d.net_of("R112A", "1").name
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
    bulk = [c for c in out_caps if c.board == "POWER" and set(c.pins) == {"+", "-"}]
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


# ─── OUTPUTS: the smart switches ─────────────────────────────────────────────────

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


def _firmware_commands(d, reach):
    """Firmware can command this input: the walk back from it reaches a native
    GPIO, or a bit of an I²C expander the S3 writes.  ⚠️ Both count since
    IO-1 -- the twelve 12 V channels are more than the native pins left, so the
    aux four and AUX12 are commanded on expander #3."""
    parts = {p.refdes for p in d.parts}
    for x in reach:
        if d.net(x).gpio:
            return True
        if any(d.part(r).mpn.startswith("MCP23017")
               for r, _ in d.net(x).pins if r in parts):
            return True
    return False


def test_every_used_tps_input_is_reachable_from_the_mcu_and_unused_ones_are_off(d, w):
    """Every channel that leaves the box is commanded, and every channel that
    does not is held off.  ⛔ No TPS4H160B input is a HARDWARE input any more:
    AUX12 (U301 IN1) was held high from V3P3 until IO-1 made it an ordinary
    output on expander #3, so horn, fan and buzzer now have no + until
    firmware asks for it."""
    for u in _tps(d):
        for n in "1234":
            out, inp = w.net(u.refdes, f"OUT{n}"), w.net(u.refdes, f"IN{n}")
            reach = w.walk(inp, {"R"})
            if w.connectors_on(out):
                assert _firmware_commands(d, reach), (
                    f"{u.refdes}.IN{n} drives a wire out of the box but "
                    f"nothing the firmware writes reaches it")
                assert "V3P3" not in reach and "V12" not in reach, (
                    f"{u.refdes}.IN{n} is held on by a rail, not commanded")
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
        if {cp.net for cp in c.pins} & lamp_nets and c.board == "OUTPUTS" \
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
        lines = {w.net(a.refdes, p) for p in a.pins}
        assert not lines & {"V12", "V5", "V3P3"}, (
            f"{a.refdes}: the TDK's OVP window overlaps the array's V_BR")
    single = [t for t in w.between("V12", "GND", {"TVS"}) if len(t.pins) == 2]
    assert len(single) == 1 and single[0].board == "OUTPUTS"
    assert w.net(single[0].refdes, "K") == "V12"


def test_unidirectional_clamps_point_the_right_way(d, w):
    for t in (p for p in d.parts if p.kind in {"TVS", "ZENER"} and len(p.pins) == 2):
        a, k = d.net(w.net(t.refdes, "A")), d.net(w.net(t.refdes, "K"))
        assert DOMAIN_VOLTS[k.domain] >= DOMAIN_VOLTS[a.domain], (
            f"{t.refdes}: cathode on {k.name}, anode on {a.name}")


# ─── IO-8: the brake, the brake lamp and the kill are plain firmware I/O ──────
# There is no dedicated circuit left.  What still has to hold is the WIRING:
# BL's own copper never crosses an interface, the lever contacts are conditioned
# on the board that owns the connector, and the FarDriver's 5.1 V is a sensor.
# tests/test_plain_io.py holds the FUNCTION (released at reset, off at reset).
#
# ⚠️ Not one of these names a board.  Each DERIVES it from the harness terminal
# the wire arrives on -- which is how they survived the move of J309 (with
# Q106/R114/R115) to POWER and J306 (with the lever networks) to LOGIC, and how
# they will survive the next one.  A typed board name would have had to be
# edited in seven places, and the invariant is what gets lost in that edit.


def _terminal_board(w, net):
    """The board whose harness terminal `net` arrives on -- one board, or the
    wire is landed in two places at once."""
    boards = {c.board for c in w.connectors_on(net) if c.leaves_box}
    assert len(boards) == 1, f"{net} leaves the box from {sorted(boards)}"
    return boards.pop()


def test_bl_leaves_the_box_on_its_own_board_and_only_signals_cross(d, w):
    """The command and the readback cross STACK; BL's own copper does not. One
    walked-out inter-board contact must not be able to open the cut's return
    path or short it. The cut FET and its bias live on the board BL leaves from."""
    board = _terminal_board(w, "BL")
    assert not [c for c in w.connectors_on("BL") if c.interface], (
        "BL itself crosses an inter-board connector: one walked-out contact "
        "and the motor cut fails, silently")
    cut = [q for q in w.parts_on("BL", {"NFET"}, board=board)
           if w.net(q.refdes, "D") == "BL"]
    assert cut, f"nothing on {board}, where BL leaves, can pull BL low"
    gate = w.net(cut[0].refdes, "G")
    assert w.net(cut[0].refdes, "S") == "GND", "the cut FET has no source"
    assert [r for r in w.between(gate, "GND", {"R"}) if r.board == board], (
        f"the cut FET's bias-OFF is not on {board} with it: an interface "
        f"between a gate and its pull-down is a cut waiting for a bad contact")
    copy = w.between("BL", "BL_SENSE", {"R"})
    assert copy and ohms(copy[0]) >= 100e3
    assert w.parts_on("BL_SENSE") and not w.between("BL", "BL_SENSE", FETS | {"D"})


def test_the_throttle_supply_is_sensed_and_never_used_as_a_rail(d, w):
    """ACC+ comes in beside BL and feeds the sense divider alone (IO-8): nothing
    on the module is powered or pulled up from the controller's 5.1 V."""
    assert _terminal_board(w, "ACC_PLUS") == _terminal_board(w, "BL"), (
        "ACC+ and BL share one FarDriver terminal")
    top = w.between("ACC_PLUS", "ACC_SENSE", {"R"})
    assert len(top) == 1 and ohms(top[0]) >= 100e3
    others = {r.refdes for r in w.parts_on("ACC_PLUS", {"R"})} - {top[0].refdes}
    assert others == set(), f"ACC+ still feeds {sorted(others)}"


@pytest.mark.parametrize("wire,node", [("IN05_BRAKE_L", "LEVER_L"),
                                       ("IN06_BRAKE_R", "LEVER_R")])
def test_each_lever_is_a_class_a_contact_conditioned_on_its_own_board(d, w, wire, node):
    """plan §4 class A, and the lever WIRE is the node: the 1 kΩ pull-up and the
    1 kΩ series sit on the board the lever terminal is on, beside its array, and
    the 100 nF sits at the S3's pin on the S3's board. Only the conditioned
    signal travels."""
    board = _terminal_board(w, node)
    mcu = d.part("U401").board
    pull = w.between(node, "V3P3", {"R"})
    assert pull and pull[0].board == board and pull[0].value == "1k", (
        f"{node}'s pull-up must be on {board}, at its terminal")
    series = w.between(node, wire, {"R"})
    assert series and series[0].board == board, f"{wire} has no series resistor"
    assert series[0].value == "1k"
    assert not w.between(node, wire, {"D"}), (
        "no steering diode stands between the lever and its input any more")
    assert any(p.kind == "C" and p.board == mcu for p in w.parts_on(wire, {"C"})), \
        f"{wire} has no capacitor at the MCU pin on {mcu} (plan §4 class A)"
    assert [t for t in w.parts_on(node, {"TVS"}) if t.board == board], (
        f"{node} has no clamp on {board}, the board its terminal is on")
    rail_reaches = ([c for c in w.connectors_on("V3P3")
                     if c.board == board and c.interface]
                    + [p for p in w.parts_on("V3P3", {"IC"}) if p.board == board])
    assert rail_reaches, f"V3P3 does not reach {board}, where the pull-up is"


# ─── LOGIC ───────────────────────────────────────────────────────────────────

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
    assert service, "no internal service pads bring out EN and IO0 for recovery"
    nets = {cp.net for cp in service[0].pins}
    tx = w.net("U401", "IO43")
    assert tx not in nets and any(w.between(tx, n, {"R"}) for n in nets), (
        "U0TXD reaches the service pads through its HDG series resistor")
    assert {w.net("U401", "IO44"), "GND"} <= nets
    assert "V3P3" not in nets, "the adapter powers itself: no rail on the pads"


def test_the_pin_map_obeys_the_silicon(d, w):
    by_gpio = {n.gpio: n for n in d.nets if n.gpio}
    adc1 = {f"GPIO{n}" for n in range(1, 11)}
    for analog in ("KEY_SENSE_PIN", "V12_SENSE", "CS1", "CS2"):
        assert d.net(analog).gpio in adc1, f"{analog}: ADC2 dies with WiFi"
    for strap in ("GPIO0", "GPIO3", "GPIO45", "GPIO46", "GPIO43"):
        if strap in by_gpio:
            wires = [c.refdes for c in w.connectors_on(by_gpio[strap].name) if c.leaves_box]
            assert not wires, f"{strap} reaches the harness on {wires}"
    assert d.net("TWAI_TX").gpio == "GPIO10" and d.net("TWAI_RX").gpio == "GPIO21"
    assert d.net("FAN_CMD").gpio == "GPIO6", "GPIO44's boot pull-up sits at V_th"
    assert d.net("U0RXD").gpio == "GPIO44"
    assert not [c.refdes for c in w.connectors_on("U0RXD") if c.leaves_box], (
        "the programmer's TX drives GPIO44 while flashing: no harness wire there")
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


def test_can_transceiver_mode_pin_is_terminated(d, w):
    assert "GND" in w.walk(w.net("U404", "RS"), {"R"}), "RS open = undefined mode"


# ─── interfaces and connectors ───────────────────────────────────────────────

#: The contract between OUTPUTS and LOGIC: these nets cross STACK, and no others.
STACK_CONTRACT = {
    # the seven lamp commands, the stop lamp among them since IO-8
    "LGT_LOW", "LGT_HIGH", "LGT_DRL", "LGT_TAIL", "LGT_TURN_L", "LGT_TURN_R",
    "LGT_STOP",
    "DIAG_EN", "SEL", "SEH", "CS1", "CS2", "FAULT1", "FAULT2", "HORN_CMD",
    "FAN_CMD", "BUZZ_CMD", "V12_SENSE",
    # the motor cut: the command out, the 100 kΩ-isolated copy back (IO-8)
    "BL_CMD", "BL_SENSE",
    # relayed on to CTRL and the controller row on POWER (IO-5): the serial
    # pair, the boost command, ACC+ divided down (LOW with the key on means the
    # controller is not alive) and the parked display's CAN pair
    "UART1_TX", "UART1_RX", "BOOST_CMD", "ACC_SENSE", "CANH", "CANL",
    # the I²C bus, DOWN to expander #3, which commands the aux block on
    # OUTPUTS (IO-1). One bus for all three expanders: no native pin is free
    # for a second.
    "SDA", "SCL",
    # ⛔ NOT the brake levers: J306 is in the INPUTS row on LOGIC (IO-6), so
    # IN05_BRAKE_L and IN06_BRAKE_R reach their pins without a crossing.
    # ⛔ And NOT V3P3, or any other rail: a rail lands on itself when a half is
    # mated reversed, which only a palindrome gives it, so it rides PWR-LOGIC
    # (rule BUS-ORDER). The spine carries signals and grounds.
}

#: CTRL, POWER ↔ OUTPUTS: the controller row's signals, every one beside a
#: ground. Eight of them carry on to LOGIC across STACK; the three telltales
#: stop here, because the lamp feeds that drive them are on OUTPUTS.
CTRL_CONTRACT = {
    "BL_CMD", "BL_SENSE", "ACC_SENSE", "UART1_TX", "UART1_RX", "BOOST_CMD",
    "CANH", "CANL", "TT_L", "TT_R", "TT_HL",
}


def _interface(d, name):
    return [c for c in d.connectors if c.interface == name]


def test_stack_is_one_row_per_signal_and_carries_exactly_the_contracted_nets(d):
    """2 × N, N derived from the contract itself: every odd contact a signal,
    every even one a ground, and no empty contact to grow a signal into by
    accident."""
    ends = _interface(d, "STACK")
    assert {c.board for c in ends} == {"OUTPUTS", "LOGIC"}
    for c in ends:
        assert len(c.pins) == 2 * len(STACK_CONTRACT)
        assert {cp.net for cp in c.pins} - {"GND"} == STACK_CONTRACT
        grounds = [cp for cp in c.pins if cp.net == "GND"]
        assert len(grounds) == len(STACK_CONTRACT), "alternating grounds"
        assert c.footprint_mm[0] == pytest.approx(2.54 * len(STACK_CONTRACT))
    assert ends[0].pins == ends[1].pins, "the two halves must mate pin for pin"


def test_ctrl_carries_the_controller_row_with_a_ground_beside_every_signal(d):
    """2 × N like STACK, N derived from the contract: the controller row's
    connectors are on POWER (IO-5) and everything that commands or reads them
    is above, so each of these signals faces a ground of its own."""
    ends = _interface(d, "CTRL")
    assert {c.board for c in ends} == {"POWER", "OUTPUTS"}
    for c in ends:
        assert len(c.pins) == 2 * len(CTRL_CONTRACT)
        assert {cp.net for cp in c.pins} - {"GND"} == CTRL_CONTRACT
        assert len([cp for cp in c.pins if cp.net == "GND"]) == len(CTRL_CONTRACT)
        assert c.footprint_mm[0] == pytest.approx(2.54 * len(CTRL_CONTRACT))
    assert ends[0].pins == ends[1].pins, "the two halves must mate pin for pin"


def test_what_crosses_ctrl_and_stack_both_is_relayed_not_duplicated(d):
    """A net that starts on LOGIC and ends on POWER crosses both interfaces. It
    is ONE net with two crossings, and `interface` names the lower one, so a
    reader looking for the crossing finds the whole path."""
    relayed = CTRL_CONTRACT & STACK_CONTRACT
    assert relayed == {"BL_CMD", "BL_SENSE", "ACC_SENSE", "UART1_TX",
                       "UART1_RX", "BOOST_CMD", "CANH", "CANL"}
    for name in sorted(relayed):
        n = d.net(name)
        assert n.interface == "CTRL", name
        assert {d.board_of(r) for r, _ in n.pins} >= {"POWER", "LOGIC"}, name


def test_no_rail_rides_a_signal_spine(d):
    """Derived from the design's own statement of what a rail is (rules.rails,
    which reads SUPPLY_PINS): reversed or mirrored, a spine lands every contact
    on a ground, so a rail on one is a short across the interface."""
    from tools import rules
    spines = {"STACK", "CTRL"}
    for c in d.connectors:
        if c.interface in spines:
            assert not (rules.rails(d) & {cp.net for cp in c.pins}), c.refdes


def test_pwr_up_shares_the_load_current_over_three_contacts(d):
    ends = _interface(d, "PWR-OUT")
    assert {c.board for c in ends} == {"POWER", "OUTPUTS"}
    for c in ends:
        nets = [cp.net for cp in c.pins]
        assert nets.count("V12") >= 3, "2.62 A: one fretted contact of two is 100 %"
        assert nets.count("GND") >= 4
        assert set(nets) == {"V12", "GND", "V5", "KEY_SENSE"}
    assert ends[0].pins == ends[1].pins


def test_84v_harness_connectors_keep_their_distance(d):
    for c in d.connectors:
        if c.leaves_box and any(cp.net and d.net(cp.net).domain == "84V" for cp in c.pins):
            assert c.pitch_mm >= 5.08, f"{c.refdes}: 84 V at {c.pitch_mm} mm"


def test_connectors_state_what_they_are(d):
    for c in d.connectors:
        # A copper-only land (the Tag-Connect pads) stands 0 mm tall.
        assert (c.height_mm > 0 or c.land) and min(c.footprint_mm) > 0, c.refdes
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

def without_parts(design, *refdes):
    for ref in refdes:
        design = design.without_part(ref)
    return design


def move_pin(design, refdes, pin, to_net):
    lifted = design.without_pin(refdes, pin)
    return lifted.replace_net(to_net, pins=lifted.net(to_net).pins + ((refdes, pin),))


def swap_pins(design, refdes, a, b):
    net_a, net_b = design.net_of(refdes, a).name, design.net_of(refdes, b).name
    return move_pin(move_pin(design, refdes, a, net_b), refdes, b, net_a)


def fewer_v12_contacts(design):
    """Every V12 contact of PWR-OUT but two becomes a ground."""
    out = design
    for c in _interface(design, "PWR-OUT"):
        extra = [cp for cp in c.pins if cp.net == "V12"][2:]
        out = out.replace_connector(c.refdes, pins=tuple(
            replace(cp, net="GND") if cp in extra else cp for cp in c.pins))
    return out


DEFECTS = [
    ("the cut FET has no source",
     lambda d: d.without_pin("Q106", "S"),
     test_bl_leaves_the_box_on_its_own_board_and_only_signals_cross, {}),
    ("the lever pull-up sits on OUTPUTS, an interface away from its terminal",
     lambda d: d.replace_part("R317", board="OUTPUTS"),
     test_each_lever_is_a_class_a_contact_conditioned_on_its_own_board,
     {"wire": "IN05_BRAKE_L", "node": "LEVER_L"}),
    ("the lever array left behind on OUTPUTS",
     lambda d: d.replace_part("D313", board="OUTPUTS"),
     test_each_lever_is_a_class_a_contact_conditioned_on_its_own_board,
     {"wire": "IN05_BRAKE_L", "node": "LEVER_L"}),
    ("the cut FET's bias-OFF an interface away from its gate",
     lambda d: d.replace_part("R115", board="LOGIC"),
     test_bl_leaves_the_box_on_its_own_board_and_only_signals_cross, {}),
    ("the throttle's 5.1 V pressed into service as a pull-up",
     lambda d: move_pin(d, "R346", "2", "ACC_PLUS"),
     test_the_throttle_supply_is_sensed_and_never_used_as_a_rail, {}),
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
    ("a 5 V array on a 12 V output line",
     lambda d: d.replace_part("D326", v_max=5.0),
     test_a_tvs_never_conducts_at_its_nets_working_voltage, {}),
    ("the lever wire mislabelled as a 12 V line",
     lambda d: d.replace_net("LEVER_L", domain="12V"),
     test_every_net_states_a_voltage_nobody_has_to_guess, {}),
    ("a TVS array with an anode in the air",
     lambda d: d.without_pin("D313", "A5"),
     test_every_tvs_array_returns_to_ground_beside_a_connector_it_protects, {}),
    ("a TVS array on the wrong board",
     lambda d: d.replace_part("D405", board="LOGIC"),
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
    # DERIVED, not typed: every capacitor OUTPUTS holds between V12 and
    # ground. A typed list went stale the moment the aux block added more
    # (a third driver's pair and the 5 V buck's input caps), and the mutation
    # passed while the requirement it exists to prove sat unexercised.
    ("a driver chip with no decoupling",
     lambda d: without_parts(d, *(c.refdes for c in
                                  Walker(d).between("V12", "GND", {"C"})
                                  if c.board == "OUTPUTS")),
     test_every_ic_is_decoupled_on_every_rail_it_touches, {}),
    ("a flyback diode fitted backwards",
     lambda d: swap_pins(d, "D314", "A", "K"),
     test_inductive_loads_have_a_flyback_path, {}),
    ("BL taken to LOGIC across STACK",
     lambda d: d.replace_net("BL", pins=d.net("BL").pins + (("J308", "49"),)),
     test_bl_leaves_the_box_on_its_own_board_and_only_signals_cross, {}),
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
    ("R115", "10k", "BL's HARD gate pull-down: released at reset (IO-9)"),
    ("R317", "1k", "the left lever's class-A pull-up: 3.3 mA of wetting current"),
    ("R353", "4k7", "the STOP command's series resistor into U302 IN4"),
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
