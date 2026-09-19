"""Every rule: quiet on a real circuit, and FIRING on each defect that once
walked past it.

The fixture is a small but real three-board circuit -- a soft-started 84 V
P-FET with its level shifter, a converter behind a common-mode choke, a
low-side horn, the hardware brake lamp, a high-side driver with current sense,
a pod input, USB, an expander and the service header. Every part declares its
real pins, so the fixture passes tools/integrity.py as well as tools/rules.py.
A rule that is only ever shown a toy cannot be trusted on the real netlist.

The failing cases are the 2026-09-18 audit's evasion table (audit F), one test
per evasion, plus the historical defects by name. Each asserts on the RULE ID,
never on prose.
"""
import re
from collections import defaultdict
from dataclasses import replace

import pytest

from tools import board_params as bp
from tools import integrity, rules
from tools.model import ConnPin, Connector, Design, Net, Part

IO_PINS = tuple(f"IO{n}" for n in sorted(rules.MODULE_GPIOS))
MCP_PORT = tuple(f"GP{b}{i}" for b in "AB" for i in range(8))
TPS_PINS = ("VS", "GND", "IN1", "IN2", "IN3", "IN4", "OUT1", "OUT2", "OUT3",
            "OUT4", "CS", "CL", "DIAG_EN", "SEL", "SEH", "FAULT", "THER")


# ── fixture construction ─────────────────────────────────────────────────────
def _r(ref, board, value, v_max=150.0):
    """A chip resistor with its working-voltage rating (0805 thick film: 150 V).
    A 0 R link is a conductor and carries none."""
    return Part(ref, f"R-{value}", "0805", board, "R", ("1", "2"), 0.6,
                value=value, v_max=None if value == "0R" else v_max,
                source="fixture")


def _c(ref, board, value, volts, **kw):
    return Part(ref, f"C-{value}", "0805", board, "C", ("1", "2"), 0.9,
                v_max=volts, value=value, source="fixture", **kw)


#: Each fixture TVS's clamping voltage at its rated pulse, as its datasheet
#: states it (VR-CLAMP needs one on every TVS).
CLAMPS = {"SMCJ90A": 146.0, "SMBJ15A": 24.4, "SMS15T1G": 29.0, "PESD5V0S4UD": 9.8}


def _d(ref, board, mpn, kind, volts, **kw):
    if kind == "TVS":
        kw.setdefault("v_clamp", CLAMPS.get(mpn))
    return Part(ref, mpn, "SMD", board, kind, ("A", "K"), 1.1, v_max=volts,
                source="fixture", **kw)


def _fet(ref, board, mpn, kind, volts, height=1.2):
    return Part(ref, mpn, "SOT-23", board, kind, ("G", "S", "D"), height,
                v_max=volts, source="fixture")


def _array(ref, board, mpn, volts):
    """SC-74 quad array, pins by role as the netlist names them: K1/K3/K4/K6
    are the cathodes, A2/A5 the common anode."""
    return Part(ref, mpn, "SC-74", board, "TVS",
                ("K1", "A2", "K3", "K4", "A5", "K6"), 1.1, v_max=volts,
                v_clamp=CLAMPS[mpn], source="fixture")


def _ic(ref, mpn, package, board, kind, all_pins, unused, height, **kw):
    """A multi-pin part, declared honestly: every pin the package has is
    either landed (`pins`) or accounted for (`nc`) -- never simply left out."""
    return Part(ref, mpn, package, board, kind,
                tuple(p for p in all_pins if p not in unused), height,
                nc=tuple(p for p in all_pins if p in unused), source="fixture", **kw)


def _conn(ref, board, name, nets, **kw):
    kw.setdefault("height_mm", 3.0)
    return Connector(ref, board, name,
                     tuple(ConnPin(str(i + 1), n) for i, n in enumerate(nets)),
                     source="fixture", **kw)


DOMAINS = {
    "GND": "GND", "BASEPLATE": "GND",
    "HV_BPLUS": "84V", "HV_SW": "84V", "KSW": "84V", "D13_GATE": "84V",
    "D13_PD": "84V", "HV_C1_P": "84V", "HV_C1_N": "84V",
    "D13_EN": "12V", "V12": "12V", "V5": "5V", "HORN_OUT": "12V", "LEVER_L": "12V",
    "Q1_GATE": "12V", "STOP_OUT": "12V", "HL_LOW": "12V", "DISP_LINE": "12V",
    "V3P3": "3V3", "KEY_SENSE": "3V3", "HORN_CMD": "3V3",
    "IN05_BRAKE_L": "3V3", "EN": "3V3", "SW_WIRE": "3V3", "SW_IN": "3V3",
    "POD2_WIRE": "3V3", "POD2_IN": "3V3", "USB_DM": "3V3", "USB_DP": "3V3",
    "CS1": "3V3",
    # TI SLVSCV8E: the CS pin sits at 4.5-6.5 V in any fault, which is why it
    # meets the ADC pin only through R323
    "U301_CS": "5V",
    # Resistors are rated parts, so every net one touches carries its level,
    # as in the real netlist: 3.3 V logic, and the TPS4H160B's IN and CL pins.
    "HORN_GATE": "3V3", "SDA": "3V3", "SCL": "3V3", "MCP_RESET": "3V3",
    "LGT_LOW": "3V3", "U301_IN1": "3V3", "U301_CL": "3V3",
    # no rated part and no stated level: honestly SIGNAL.
    "BOOT": "SIGNAL", "U0TXD": "SIGNAL", "U0RXD": "SIGNAL",
}
INTERFACES = {
    "GND": "PWR-OUT", "KEY_SENSE": "PWR-OUT",
    "V12": "PWR-OUT", "V5": "PWR-OUT", "V3P3": "STACK",
    "HORN_CMD": "STACK", "IN05_BRAKE_L": "STACK", "CS1": "STACK",
    "LGT_LOW": "STACK",
}
GPIOS = {
    "BOOT": 0, "KEY_SENSE": 1, "CS1": 4, "IN05_BRAKE_L": 7, "SDA": 8, "SCL": 9,
    "SW_IN": 15, "USB_DM": 19, "USB_DP": 20, "LGT_LOW": 38, "HORN_CMD": 42,
    "U0TXD": 43, "U0RXD": 44,
}


def _good() -> Design:
    # Power buses read the same from both ends, a return beside every rail.
    pwr = ("V12", "GND", "V5", "GND", "KEY_SENSE", "GND", "V5", "GND", "V12")
    stack = ("HORN_CMD", "GND", "IN05_BRAKE_L", "GND", "V3P3", "GND", "CS1",
             "GND", "LGT_LOW")
    connectors = (
        # POWER
        _conn("J101", "POWER", "Battery B+/B-", ("HV_BPLUS", "GND", "GND"), pitch_mm=7.62),
        _conn("J102", "POWER", "Key tap", ("KSW", "GND"), pitch_mm=5.08),
        _conn("J202", "POWER", "PWR-OUT", pwr, leaves_box=False, interface="PWR-OUT"),
        # OUTPUTS
        _conn("J311", "OUTPUTS", "PWR-OUT", pwr, leaves_box=False, interface="PWR-OUT",
              side="bottom"),
        _conn("J307", "OUTPUTS", "PWR-LOGIC", pwr, leaves_box=False,
              interface="PWR-LOGIC"),
        _conn("J308", "OUTPUTS", "STACK", stack, leaves_box=False, interface="STACK"),
        _conn("J301", "OUTPUTS", "Headlight", ("HL_LOW", "GND")),
        _conn("J302", "OUTPUTS", "Stop lamp", ("STOP_OUT", "GND")),
        _conn("J303", "OUTPUTS", "Horn", ("V12", "HORN_OUT")),
        _conn("J306", "OUTPUTS", "Brake lever", ("LEVER_L", "GND")),
        _conn("J305", "OUTPUTS", "Display (parked, D19)", ("DISP_LINE", "GND"), parked=True,
              dnp=True),
        # LOGIC
        _conn("J406", "LOGIC", "STACK", stack, leaves_box=False, interface="STACK",
              side="bottom"),
        _conn("J407", "LOGIC", "PWR-LOGIC", pwr, leaves_box=False,
              interface="PWR-LOGIC", side="bottom"),
        _conn("J401", "LOGIC", "USB-C", ("USB_DM", "USB_DP", "GND")),
        _conn("J402", "LOGIC", "Left pod", ("SW_WIRE", "POD2_WIRE", "GND")),
        _conn("J408", "LOGIC", "Service header",
              ("EN", "BOOT", "U0TXD", "U0RXD", "V3P3", "GND"), leaves_box=False),
    )

    used_io = {f"IO{g}" for g in GPIOS.values()}
    parts = (
        # ── POWER: entry, clamps, the D13 switch and its level shifter ──
        _d("D101", "POWER", "SMCJ90A", "TVS", 90.0),
        _d("D104", "POWER", "SMCJ90A", "TVS", 90.0),
        _fet("Q101", "POWER", "IXTP26P20P", "PFET", 200.0, height=4.7),
        _r("R110", "POWER", "100k"),
        _d("D102", "POWER", "BZT52C15", "ZENER", 15.0),
        _c("C105", "POWER", "68n", 250.0),
        _c("C107", "POWER", "4.7u", 25.0),
        _r("R101", "POWER", "560k"),
        _fet("Q105", "POWER", "BSS127", "NFET", 600.0),
        _r("R112", "POWER", "1M"),
        _r("R113", "POWER", "100k"),
        _d("D106", "POWER", "BZT52C10", "ZENER", 10.0),
        _c("C108", "POWER", "100n", 50.0),
        _r("R107", "POWER", "330k"),
        _r("R109", "POWER", "10k"),
        _c("C109", "POWER", "100n", 50.0),
        Part("L101", "CM-CHOKE", "THT", "POWER", "CMCHOKE", ("1", "2", "3", "4"),
             5.0, source="fixture"),
        # ── POWER ──
        _ic("U201", "CN150B110-12/CO", "BRICK", "POWER", "CONVERTER",
            ("-Vin", "CNT", "+Vin", "-V", "-S", "TRM", "+S", "+V", "BASEPLATE"),
            {"TRM"}, 5.0),
        _c("C201", "POWER", "220u", 160.0, side="bottom"),
        # The logic rail's own converter, so LOGIC's regulator is not on the
        # clamped 12 V rail (no TVS holds 12 V under its 16 V).
        _ic("U202", "EC7BW-110S05", "MODULE", "POWER", "CONVERTER",
            ("+Vin", "-Vin", "+Vout", "-Vout"), set(), 3.0),
        _c("C203", "POWER", "4.7n Y2", 1000.0),
        _r("R211", "POWER", "0R"),
        _c("C207", "POWER", "680u", 25.0),
        _c("C208", "POWER", "2.2u", 25.0),
        # ── OUTPUTS ──
        _fet("Q301", "OUTPUTS", "AO3400A", "NFET", 30.0),
        _r("R307", "OUTPUTS", "10k"),
        _r("R310", "OUTPUTS", "100R"),
        _d("D315", "OUTPUTS", "SMBJ15A", "TVS", 15.0),
        _array("D310", "OUTPUTS", "SMS15T1G", 15.0),
        _d("D303", "OUTPUTS", "1N4148", "D", 100.0),
        _d("D305", "OUTPUTS", "1N4148", "D", 100.0),
        _r("R313", "OUTPUTS", "10k"),
        _fet("Q304", "OUTPUTS", "AO3407A", "PFET", 30.0),
        _r("R317", "OUTPUTS", "10k"),
        _d("D406", "OUTPUTS", "SMBJ15A", "TVS", 15.0, dnp=True),
        _ic("U301", "TPS4H160BQPWPRQ1", "HTSSOP-28", "OUTPUTS", "IC", TPS_PINS,
            {"IN2", "IN3", "IN4", "OUT2", "OUT3", "OUT4", "FAULT", "THER"}, 1.2,
            v_max=40.0),
        _r("R330", "OUTPUTS", "4.7k"),
        _r("R319", "OUTPUTS", "1.00k"),
        _r("R321", "OUTPUTS", "1.00k"),
        _r("R323", "OUTPUTS", "10k"),
        _c("C303", "OUTPUTS", "100n", 25.0),
        _c("C304", "OUTPUTS", "10u", 25.0),
        # ── LOGIC ──
        _ic("U401", "ESP32-S3-WROOM-1-N8", "MODULE", "LOGIC", "MODULE",
            ("3V3", "GND", "EN") + IO_PINS, set(IO_PINS) - used_io, 3.1),
        Part("U405", "TLV76733DGNR", "HVSSOP-8", "LOGIC", "IC",
             ("IN", "OUT", "GND", "EN"), 1.1, v_max=16.0, source="fixture"),
        _c("C404", "LOGIC", "10u", 25.0),
        _c("C402", "LOGIC", "10u", 10.0),
        _c("C403", "LOGIC", "100n", 16.0),
        _c("C405", "LOGIC", "100n", 16.0),
        _r("R401", "LOGIC", "10k"),
        _c("C401", "LOGIC", "1u", 10.0),
        _array("D401", "LOGIC", "PESD5V0S4UD", 5.0),
        _r("R410", "LOGIC", "1k"),
        _r("R411", "LOGIC", "4.7k"),
        _c("C410", "LOGIC", "100n", 16.0),
        _r("R412", "LOGIC", "1k"),
        _r("R413", "LOGIC", "4.7k"),
        _r("R414", "LOGIC", "10k"),
        _r("R415", "LOGIC", "4.7k"),
        _r("R416", "LOGIC", "4.7k"),
        _c("C301", "LOGIC", "100n", 16.0),
        _ic("U402", "MCP23017-E/SO", "SOIC-28", "LOGIC", "IC",
            ("VDD", "VSS", "SCL", "SDA", "RESET", "A0", "A1", "A2", "INTA",
             "INTB") + MCP_PORT, {"INTA", "INTB"} | set(MCP_PORT) - {"GPB3"}, 2.65),
    )

    land = defaultdict(list)
    for c in connectors:
        for cp in c.pins:
            land[cp.net].append((c.refdes, cp.pin))

    def wire(net, *pins):
        land[net].extend(pins)

    wire("HV_BPLUS", ("D101", "K"), ("Q101", "S"), ("R110", "1"), ("D102", "K"), ("C107", "1"))
    wire("KSW", ("D104", "K"), ("R112", "1"), ("R107", "1"))
    wire("D13_GATE", ("Q101", "G"), ("R110", "2"), ("D102", "A"), ("C105", "1"),
         ("C107", "2"), ("R101", "1"))
    wire("HV_SW", ("Q101", "D"), ("C105", "2"), ("L101", "1"))
    wire("D13_PD", ("R101", "2"), ("Q105", "D"))
    wire("D13_EN", ("R112", "2"), ("Q105", "G"), ("R113", "1"), ("D106", "K"), ("C108", "1"))
    wire("KEY_SENSE", ("R107", "2"), ("R109", "1"), ("C109", "1"), ("U401", "IO1"))
    wire("HV_C1_P", ("L101", "4"), ("U201", "+Vin"), ("C201", "1"), ("C203", "1"),
         ("U202", "+Vin"))
    wire("HV_C1_N", ("L101", "3"), ("U201", "-Vin"), ("U201", "CNT"), ("C201", "2"),
         ("U202", "-Vin"))
    wire("BASEPLATE", ("U201", "BASEPLATE"), ("C203", "2"), ("R211", "1"))
    wire("V12", ("U201", "+V"), ("U201", "+S"), ("C207", "1"), ("C208", "1"),
         ("D315", "K"), ("R313", "2"), ("Q304", "S"), ("U301", "VS"),
         ("C303", "1"), ("C304", "1"))
    wire("V5", ("U202", "+Vout"), ("U405", "IN"), ("U405", "EN"), ("C404", "1"))
    wire("HORN_CMD", ("U401", "IO42"), ("R310", "1"))
    wire("HORN_GATE", ("R310", "2"), ("Q301", "G"), ("R307", "1"))
    wire("HORN_OUT", ("Q301", "D"), ("D310", "K1"))
    wire("LEVER_L", ("D303", "K"), ("D305", "K"), ("D310", "K3"))
    wire("Q1_GATE", ("D303", "A"), ("R313", "1"), ("Q304", "G"))
    wire("STOP_OUT", ("Q304", "D"), ("D310", "K4"))
    wire("HL_LOW", ("U301", "OUT1"), ("D310", "K6"))
    wire("IN05_BRAKE_L", ("D305", "A"), ("R317", "1"), ("U401", "IO7"))
    wire("DISP_LINE", ("D406", "K"))
    wire("LGT_LOW", ("U401", "IO38"), ("R330", "1"))
    wire("U301_IN1", ("R330", "2"), ("U301", "IN1"))
    wire("U301_CL", ("U301", "CL"), ("R319", "1"))
    wire("U301_CS", ("U301", "CS"), ("R321", "1"), ("R323", "1"))
    wire("CS1", ("R323", "2"), ("C301", "1"), ("U401", "IO4"))
    wire("V3P3", ("U405", "OUT"), ("C402", "1"), ("C403", "1"), ("C405", "1"),
         ("U401", "3V3"), ("R401", "1"), ("R317", "2"), ("R411", "1"),
         ("R413", "1"), ("R414", "1"), ("R415", "1"), ("R416", "1"), ("U402", "VDD"))
    wire("EN", ("U401", "EN"), ("R401", "2"), ("C401", "1"))
    wire("BOOT", ("U401", "IO0"))
    wire("U0TXD", ("U401", "IO43"))
    wire("U0RXD", ("U401", "IO44"))
    wire("USB_DM", ("U401", "IO19"), ("D401", "K1"))
    wire("USB_DP", ("U401", "IO20"), ("D401", "K3"))
    wire("SW_WIRE", ("R410", "1"), ("D401", "K4"))
    wire("SW_IN", ("R410", "2"), ("R411", "2"), ("C410", "1"), ("U401", "IO15"))
    wire("POD2_WIRE", ("R412", "1"), ("D401", "K6"))
    wire("POD2_IN", ("R412", "2"), ("R413", "2"), ("U402", "GPB3"))
    wire("MCP_RESET", ("U402", "RESET"), ("R414", "2"))
    wire("SDA", ("U401", "IO8"), ("U402", "SDA"), ("R415", "2"))
    wire("SCL", ("U401", "IO9"), ("U402", "SCL"), ("R416", "2"))
    wire("GND",
         ("D101", "A"), ("D104", "A"), ("Q105", "S"), ("R113", "2"), ("D106", "A"),
         ("C108", "2"), ("R109", "2"), ("C109", "2"), ("L101", "2"),
         ("U201", "-V"), ("U201", "-S"), ("R211", "2"), ("C207", "2"), ("C208", "2"),
         ("Q301", "S"), ("R307", "2"), ("D315", "A"), ("D310", "A2"), ("D310", "A5"),
         ("D406", "A"), ("U301", "GND"), ("U301", "DIAG_EN"), ("U301", "SEL"),
         ("U301", "SEH"), ("R319", "2"), ("R321", "2"), ("C303", "2"), ("C304", "2"),
         ("U401", "GND"), ("U405", "GND"), ("C404", "2"), ("C402", "2"), ("U202", "-Vout"),
         ("C403", "2"), ("C405", "2"), ("C401", "2"), ("D401", "A2"), ("D401", "A5"),
         ("C410", "2"), ("C301", "2"), ("U402", "VSS"), ("U402", "A0"),
         ("U402", "A1"), ("U402", "A2"))

    nets = tuple(
        Net(name, tuple(pins), domain=DOMAINS[name],
            interface=INTERFACES.get(name),
            gpio=f"GPIO{GPIOS[name]}" if name in GPIOS else None,
            source="fixture")
        for name, pins in land.items())
    return Design(parts=parts, nets=nets, connectors=connectors)


GOOD = _good()


# ── fixture surgery ──────────────────────────────────────────────────────────
def move_pin(d: Design, ref: str, pin: str, to_net: str) -> Design:
    """Re-land one leg of a part on a different net."""
    d = d.without_pin(ref, pin)
    return d.replace_net(to_net, pins=d.net(to_net).pins + ((ref, pin),))


def add_pin(d: Design, net: str, ref: str, pin: str) -> Design:
    return d.replace_net(net, pins=d.net(net).pins + ((ref, pin),))


def rename_net(d: Design, old: str, new: str) -> Design:
    d = replace(d, nets=tuple(replace(n, name=new) if n.name == old else n
                              for n in d.nets))
    return replace(d, connectors=tuple(
        replace(c, pins=tuple(replace(cp, net=new) if cp.net == old else cp
                              for cp in c.pins)) for c in d.connectors))


def on_gpio(d: Design, net: str, n: int) -> Design:
    """Move a net's MCU pin (and its tag) to GPIOn, honestly: the pin moves,
    the tag follows, and the module's `nc` list is kept true."""
    old = [p for r, p in d.net(net).pins if r == "U401" and p.startswith("IO")]
    for p in old:
        d = d.without_pin("U401", p)
    d = add_pin(d, net, "U401", f"IO{n}")
    d = d.replace_net(net, gpio=f"GPIO{n}")
    u = d.part("U401")
    pins = tuple(p for p in u.pins if p not in old) + (f"IO{n}",)
    nc = tuple(sorted((set(u.nc) | set(old)) - {f"IO{n}"}))
    return d.replace_part("U401", pins=pins, nc=nc)


def fired(d: Design, rule_id: str) -> list[str]:
    return [e for e in rules.check_all(d) if e.startswith(rule_id + ":")]


RULE_IDS = {
    "BD-2", "BD-4", "GPIO-TAG", "GPIO-DUP", "GPIO-PAD", "GPIO-43",
    "GPIO-ADC1", "GPIO-STRAP", "D14", "TURN-ON", "VR-RATED", "VR-DOMAIN",
    "VR-UNDER", "VR-STANDOFF", "VR-DATASHEET", "LV-LOGIC", "PROT",
    "GND-ISLAND", "MCP-OUT7", "POL", "HT-NUM", "HT-STACK", "HT-GEOM",
    "D10", "SUPPLY", "BUS-ORDER", "LISTEN", "VR-CLAMP", "VR-POWER", "PULL-DIR",
}


# ── the fixture itself ───────────────────────────────────────────────────────
def test_the_fixture_is_a_circuit():
    """Every leg of every fixture part goes somewhere, by the structural
    gate's own count -- so a rule that passes it is not passing a sketch.

    One category is set aside: GOOD is a REDUCED circuit that uses one channel
    of a quad switch and parks the rest in `nc`, which a real board may not do.
    The real design gets no such allowance -- tests/test_design_clean.py holds
    it to the whole gate, no-connect policing included."""
    assert [e for e in integrity.check(GOOD) if not e.startswith("nc:")] == []


def test_the_good_design_passes_every_rule():
    assert rules.check_all(GOOD) == []


def test_every_error_starts_with_a_stable_rule_id():
    wreck = GOOD.without_part("R307").without_part("D310").without_part("Q105")
    wreck = wreck.replace_part("U405", height_mm=float("nan"))
    wreck = on_gpio(wreck, "SW_IN", 33)
    errs = rules.check_all(wreck)
    assert len(errs) >= 5
    for e in errs:
        m = re.match(r"([A-Z0-9-]+): \S", e)
        assert m and m.group(1) in RULE_IDS, e


def test_rules_never_raise_on_a_structurally_broken_design():
    """integrity.py owns these defects; rules.py must still return a list."""
    broken = GOOD.with_net(Net("GHOST", (("X999", "1"), ("J999", "2")), domain="84V"))
    broken = broken.with_net(GOOD.net("V12"))                 # duplicate net
    broken = broken.with_part(GOOD.part("R307"))              # duplicate refdes
    assert isinstance(rules.check_all(broken), list)
    assert isinstance(rules.warnings(broken), list)


def test_leaves_box_cannot_be_typed_on_a_net():
    """The old evasion -- flip Net.leaves_box and the TVS and strapping rules
    go blind -- is closed in the model: the field does not exist."""
    with pytest.raises(TypeError):
        Net("X", (), domain="12V", leaves_box=False)


# ── BD-2: 84 V containment ───────────────────────────────────────────────────
def test_bd2_fires_when_an_84v_net_lands_on_a_brain_part():
    bad = add_pin(GOOD, "HV_SW", "U401", "IO10")
    assert fired(bad, "BD-2")


def test_bd2_fires_on_drv_too_not_only_brain():
    bad = add_pin(GOOD, "HV_SW", "R307", "9")
    assert any("OUTPUTS" in e for e in fired(bad, "BD-2"))


def test_bd2_fires_on_a_connector_pin():
    """The old rule swallowed the KeyError for a connector refdes."""
    bad = add_pin(GOOD, "HV_BPLUS", "J408", "7")
    assert any("J408" in e for e in fired(bad, "BD-2"))


def test_bd2_fires_when_only_the_connector_table_carries_the_net():
    j = GOOD.connector("J408")
    bad = GOOD.replace_connector("J408", pins=j.pins + (ConnPin("7", "HV_BPLUS"),))
    assert any("J408" in e for e in fired(bad, "BD-2"))


def test_bd2_is_not_fooled_by_relabelling_the_net():
    """HV_SW typed SIGNAL is still the drain of the 84 V switch."""
    bad = add_pin(GOOD.replace_net("HV_SW", domain="SIGNAL"), "HV_SW", "U401", "IO10")
    errs = fired(bad, "BD-2")
    assert any("typed SIGNAL" in e for e in errs)
    assert any("U401" in e for e in errs)


def test_bd2_fires_when_an_84v_part_pin_is_tied_onto_a_logic_net():
    """Audit 3a: the switch's drain tied onto a net that lands on LOGIC."""
    bad = add_pin(GOOD, "SW_IN", "Q101", "D")
    errs = fired(bad, "BD-2")
    assert any("'SW_IN'" in e and "typed 3V3" in e for e in errs)
    assert any("LOGIC" in e for e in errs)


def test_bd2_lets_a_divided_sense_net_cross_to_brain():
    """KEY_SENSE reaches KSW only through 330 k: not an 84 V net."""
    assert not [e for e in rules.check_all(GOOD) if "KEY_SENSE" in e]


def test_bd2_reports_an_84v_net_on_a_refdes_that_does_not_exist():
    bad = add_pin(GOOD, "HV_SW", "U999", "1")
    assert any("U999" in e for e in fired(bad, "BD-2"))


# ── BD-4: creepage on every connector that carries pack voltage ──────────────
def test_bd4_boundary_is_508_not_anything_above_254():
    assert fired(GOOD.replace_connector("J102", pitch_mm=5.0), "BD-4")
    assert not fired(GOOD.replace_connector("J102", pitch_mm=5.08), "BD-4")


def test_bd4_fires_on_a_harness_connector_carrying_84v():
    """Audit 9b: the key tap leaves the box at pack voltage."""
    bad = GOOD.replace_connector("J102", pitch_mm=1.0)
    assert any("J102" in e for e in fired(bad, "BD-4"))


def test_bd4_nan_pitch_is_not_a_pass():
    assert fired(GOOD.replace_connector("J102", pitch_mm=float("nan")), "BD-4")


# ── GPIO ─────────────────────────────────────────────────────────────────────
def test_silicon_facts_are_pinned():
    assert rules.GPIO_STRAPPING == {0, 3, 45, 46}
    assert rules.GPIO_ADC1 == set(range(1, 11))
    assert rules.GPIO_BOOT_LOG == 43
    assert rules.GPIO_FLASH == set(range(26, 33))
    assert not rules.MODULE_GPIOS & {22, 23, 24, 25, 33, 34}
    assert len(rules.MODULE_GPIOS) == 36          # the WROOM-1's GPIO pads
    assert rules.ANALOG_NETS == {"CS1", "CS2", "KEY_SENSE", "V12_SENSE", "AMBIENT"}


def test_gpio_dup_fires_on_two_nets_sharing_a_gpio():
    bad = on_gpio(GOOD, "SW_IN", 42)                       # HORN_CMD's pin
    assert any("GPIO42" in e for e in fired(bad, "GPIO-DUP"))


def test_gpio_dup_sees_a_duplicate_made_only_of_tags():
    bad = GOOD.replace_net("SW_IN", gpio="GPIO42")
    assert fired(bad, "GPIO-DUP")


@pytest.mark.parametrize("n, why", [
    (33, "no pad on the WROOM-1"), (34, "no pad on the WROOM-1"),
    (24, "does not exist"), (27, "in-package flash"), (99, "does not exist"),
])
def test_gpio_pad_fires_on_a_gpio_the_module_does_not_have(n, why):
    errs = fired(on_gpio(GOOD, "SW_IN", n), "GPIO-PAD")
    assert errs and why in errs[0]


def test_gpio_tag_fires_when_label_and_pin_disagree():
    """Audit 5g: tagged GPIO48, landed on IO21."""
    bad = on_gpio(GOOD, "SW_IN", 21).replace_net("SW_IN", gpio="GPIO48")
    assert fired(bad, "GPIO-TAG")


def test_gpio_tag_fires_on_an_mcu_pin_with_no_tag():
    assert fired(GOOD.replace_net("SW_IN", gpio=None), "GPIO-TAG")


def test_gpio_tag_fires_on_a_tag_with_no_mcu_pin():
    assert fired(GOOD.replace_net("SW_WIRE", gpio="GPIO16"), "GPIO-TAG")


def test_gpio_tag_fires_on_a_malformed_tag():
    assert fired(GOOD.replace_net("SW_IN", gpio="IO15"), "GPIO-TAG")


def test_gpio43_is_allowed_on_the_service_header():
    assert not fired(GOOD, "GPIO-43")


def _free_gpio43(d: Design) -> Design:
    """Take U0TXD off the module so another net can have the pin."""
    return d.without_pin("U401", "IO43").replace_net("U0TXD", gpio=None)


def test_gpio43_fires_when_it_reaches_a_fet_gate():
    bad = on_gpio(_free_gpio43(GOOD), "HORN_CMD", 43)
    assert any("Q301.G" in e and "R310" in e for e in fired(bad, "GPIO-43"))
    assert not fired(bad, "GPIO-DUP")


def test_gpio43_fires_on_the_pin_even_with_the_tag_omitted():
    """Audit 7a: physically on IO43, gpio= left off."""
    bad = on_gpio(_free_gpio43(GOOD), "HORN_CMD", 43).replace_net("HORN_CMD", gpio=None)
    assert fired(bad, "GPIO-43")


def test_gpio43_fires_when_it_reaches_a_driver_ic_input():
    bad = on_gpio(_free_gpio43(GOOD), "LGT_LOW", 43)
    assert any("U301.IN1" in e for e in fired(bad, "GPIO-43"))


def test_gpio43_sees_the_wroom_pad_name_too():
    """The module's own pad name for GPIO43 is TXD0; a net landed on it under
    that name is still on the boot-log pin."""
    bad = GOOD.replace_part("U401", pins=GOOD.part("U401").pins + ("TXD0",))
    bad = add_pin(bad.without_pin("U401", "IO42"), "HORN_CMD", "U401", "TXD0")
    assert fired(bad, "GPIO-43")


def test_adc1_fires_when_a_named_analog_net_is_on_adc2():
    assert any("GPIO11" in e for e in fired(on_gpio(GOOD, "KEY_SENSE", 11), "GPIO-ADC1"))


def test_adc1_fires_when_an_analog_net_is_on_no_mcu_pin():
    """Audit 6b."""
    bad = GOOD.without_pin("U401", "IO1").replace_net("KEY_SENSE", gpio=None)
    assert any("KEY_SENSE" in e for e in fired(bad, "GPIO-ADC1"))


def _behind_resistors(d, n):
    """KEY_SENSE meets IO1 through `n` series resistors, the pin net last."""
    d = d.without_pin("U401", "IO1").replace_net("KEY_SENSE", gpio=None)
    prev = "KEY_SENSE"
    for i in range(n):
        ref, net = f"R49{i}", f"KS_{i}"
        d = d.with_part(_r(ref, "LOGIC", "1k"))
        d = add_pin(d, prev, ref, "1")
        pins = ((ref, "2"),) + ((("U401", "IO1"),) if i == n - 1 else ())
        d = replace(d, nets=d.nets + (Net(net, pins, "3V3",
                                          gpio="GPIO1" if i == n - 1 else None),))
        prev = net
    return d


def test_adc1_follows_an_analog_net_through_its_series_resistor():
    """KEY_SENSE meets the ADC pin through R476: still read by the ADC, so
    still held to ADC1 -- and a move to ADC2 behind the resistor still fires."""
    ok = _behind_resistors(GOOD, 1)
    assert not fired(ok, "GPIO-ADC1")
    moved = ok.without_pin("U401", "IO1")
    moved = add_pin(moved.replace_net("KS_0", gpio="GPIO11"), "KS_0", "U401", "IO11")
    assert any("GPIO11" in e for e in fired(moved, "GPIO-ADC1"))


def test_adc1_does_not_look_further_than_one_resistor():
    bad = _behind_resistors(GOOD, 2)
    assert any("KEY_SENSE" in e and "no MCU pin" in e for e in fired(bad, "GPIO-ADC1"))


def test_adc1_is_not_fooled_by_renaming_the_current_sense_net():
    """Audit 6a: CS1 -> ISENSE1 on ADC2. It still reads U301.CS."""
    bad = on_gpio(rename_net(GOOD, "CS1", "ISENSE1"), "ISENSE1", 11)
    assert any("U301.CS" in e for e in fired(bad, "GPIO-ADC1"))


def test_adc1_is_quiet_when_analog_is_on_gpio1_to_10():
    for n in (2, 3 + 2, 10):
        assert not fired(on_gpio(GOOD, "KEY_SENSE", n), "GPIO-ADC1")


def test_strapping_pin_may_serve_the_internal_service_header():
    assert not fired(GOOD, "GPIO-STRAP")                  # BOOT = GPIO0 -> J408


def test_strap_fires_on_a_net_that_lands_on_a_harness_connector():
    bad = on_gpio(GOOD, "SW_WIRE", 3)
    assert any("J402" in e and "leaves the box" in e for e in fired(bad, "GPIO-STRAP"))


def test_strap_fires_through_a_series_resistor():
    """Audit 5b: the MCU-side segment of a conditioned input."""
    errs = fired(on_gpio(GOOD, "SW_IN", 46), "GPIO-STRAP")
    assert any("J402" in e and "R410" in e for e in errs)


def test_strap_fires_on_the_brake_lever_through_its_steering_diode():
    """Audit 5c -- the rule's own headline: a rider holding a lever at key-on.
    IN05_BRAKE_L is one diode away from J306."""
    errs = fired(on_gpio(GOOD, "IN05_BRAKE_L", 3), "GPIO-STRAP")
    assert any("J306" in e and "D305" in e for e in errs)


@pytest.mark.parametrize("n", sorted(rules.GPIO_STRAPPING - {0}))
def test_strap_covers_every_strapping_pin(n):
    assert fired(on_gpio(GOOD, "SW_IN", n), "GPIO-STRAP")


def test_strap_fires_on_gpio0_as_well():
    bad = on_gpio(GOOD.without_pin("U401", "IO0").replace_net("BOOT", gpio=None),
                  "SW_IN", 0)
    assert fired(bad, "GPIO-STRAP")


def test_strap_fires_when_a_strapping_pin_drives_a_gate():
    """Audit 5d: a gate's pull-down on a strapping pin sets the boot strap."""
    errs = fired(on_gpio(GOOD, "HORN_CMD", 45), "GPIO-STRAP")
    assert any("Q301.G" in e for e in errs)


def test_strap_fires_when_a_strapping_pin_crosses_to_another_board():
    """A strapping pin may serve its bias parts and the internal service
    header. Across STACK it meets another board's contacts at key-on."""
    ext = lambda c: c.pins + (ConnPin("10", "SPARE_X"),)
    bad = GOOD.replace_connector("J406", pins=ext(GOOD.connector("J406")))
    bad = bad.replace_connector("J308", pins=ext(GOOD.connector("J308")))
    bad = bad.with_net(Net("SPARE_X", (("J406", "10"), ("J308", "10")),
                           domain="SIGNAL", interface="STACK"))
    errs = fired(on_gpio(bad, "SPARE_X", 46), "GPIO-STRAP")
    assert any("crosses STACK" in e for e in errs)


def test_strap_does_not_walk_through_the_3v3_rail():
    """Every pull-up meets at V3P3. A walk that crossed a supply would
    connect every input to every connector."""
    d = on_gpio(GOOD, "MCP_RESET", 46)    # its only series part is its pull-up
    assert not [e for e in fired(d, "GPIO-STRAP") if "J4" in e or "J3" in e]


# ── D14: gate bias, by polarity ──────────────────────────────────────────────
def test_d14_fires_when_the_pulldown_is_deleted():
    assert any("Q301" in e for e in fired(GOOD.without_part("R307"), "D14"))


def test_d14_fires_when_the_bias_resistor_goes_to_the_wrong_rail():
    """Audit 2a: the horn's 10 k rewired gate -> V12. N-FET biased ON."""
    assert any("Q301" in e for e in fired(move_pin(GOOD, "R307", "2", "V12"), "D14"))


def test_d14_fires_on_a_pulldown_to_ground_on_a_high_side_pfet():
    """Audit 2b: gate -> GND on the 84 V P-FET is V_GS = -84 V. ON, not OFF."""
    assert any("Q101" in e for e in fired(move_pin(GOOD, "R110", "1", "GND"), "D14"))


def test_d14_fires_when_the_bias_resistors_far_end_floats():
    """Audit 2c."""
    assert any("Q301" in e for e in fired(GOOD.without_pin("R307", "2"), "D14"))


def test_d14_fires_when_the_bias_resistor_is_dnp():
    """Audit 2h."""
    assert any("Q301" in e for e in fired(GOOD.replace_part("R307", dnp=True), "D14"))


def test_d14_is_not_satisfied_by_a_series_resistor_with_a_bias_value():
    """Audit 2e: pull-down gone, the 100 R series part retyped '10k'."""
    bad = GOOD.without_part("R307").replace_part("R310", value="10k")
    assert any("Q301" in e for e in fired(bad, "D14"))


def test_d14_does_not_care_what_the_gate_net_is_called():
    """Audit 2d: renamed away from *_GATE, pull-down deleted."""
    assert not fired(rename_net(GOOD, "HORN_GATE", "HORN_G"), "D14")
    bad = rename_net(GOOD.without_part("R307"), "HORN_GATE", "HORN_G")
    assert any("Q301" in e for e in fired(bad, "D14"))


def test_d14_fires_when_the_fet_has_no_source_connection():
    """Audit F-2: the run/off kill FET with S on no net."""
    assert any("Q301" in e and "source" in e
               for e in fired(GOOD.without_pin("Q301", "S"), "D14"))


def test_d14_fires_when_fet_pins_are_not_named_g_s_d():
    bad = GOOD.replace_part("Q301", pins=("1", "2", "3"))
    assert any("Q301" in e for e in fired(bad, "D14"))


def test_d14_accepts_the_pfet_whose_pullup_is_its_bias():
    """Q304: R313 gate -> V12 IS gate -> source."""
    assert not [e for e in fired(GOOD, "D14") if "Q304" in e]


# ── TURN-ON: can the switch be commanded on at all? ──────────────────────────
def test_turn_on_fires_on_a_pfet_with_no_path_to_ground():
    """Audit F-4: gate tied to the source through R110, nothing to ground."""
    assert any("Q101" in e for e in fired(GOOD.without_part("Q105"), "TURN-ON"))


def test_turn_on_fires_on_the_historical_topology():
    """As netlisted on 2026-09-18: the pull-down resistor went to the key
    switch's output, which sits at the SOURCE's own potential with the key on.
    A contact that leaves the box is not a ground."""
    bad = move_pin(GOOD, "R101", "2", "KSW")
    assert any("Q101" in e for e in fired(bad, "TURN-ON"))


def test_turn_on_fires_when_the_pulldown_is_dnp():
    assert any("Q101" in e for e in fired(GOOD.replace_part("R101", dnp=True), "TURN-ON"))


def test_turn_on_allows_one_nfet_in_the_path_not_two():
    """Two stacked N-FETs need two commands to be true at once; nothing here
    checks the second. One level shifter is the topology that was verified."""
    bad = GOOD.with_part(_fet("Q199", "POWER", "BSS127", "NFET", 600.0))
    bad = bad.with_part(_r("R198", "POWER", "100k"))
    bad = bad.with_net(Net("D13_PD2", (("Q105", "S"), ("Q199", "D")), domain="84V"))
    bad = replace(bad, nets=tuple(
        replace(n, pins=tuple(p for p in n.pins if p != ("Q105", "S")))
        if n.name == "GND" else n for n in bad.nets))
    for ref, pin, net in (("Q199", "S", "GND"), ("Q199", "G", "D13_EN"),
                          ("R198", "1", "D13_EN"), ("R198", "2", "GND")):
        bad = add_pin(bad, net, ref, pin)
    assert any("Q101" in e for e in fired(bad, "TURN-ON"))


def test_sensed_node_typed_at_its_fault_ceiling_does_not_condemn_the_adc_pin():
    """U301_CS is typed 5V for what the CS pin does in a fault. It is loaded by
    its sense resistor, so its label rates parts; it does not hold CS1 at 5 V."""
    assert GOOD.net("U301_CS").domain == "5V"
    assert not [e for e in rules.check_all(GOOD) if "CS1" in e]


def test_turn_on_does_not_count_a_path_through_the_source():
    """gate -> R110 -> source -> anything -> ground turns nothing on."""
    bad = GOOD.without_part("Q105").with_part(_r("R199", "POWER", "1M"))
    bad = add_pin(add_pin(bad, "HV_BPLUS", "R199", "1"), "GND", "R199", "2")
    assert any("Q101" in e for e in fired(bad, "TURN-ON"))


def test_turn_on_accepts_a_steering_diode_to_a_contact_that_sinks():
    """Q304's gate is pulled low by the brake lever, outside the box, through
    D303 -- a diode that can only ever pull the gate DOWN."""
    assert not [e for e in fired(GOOD, "TURN-ON") if "Q304" in e]


def test_turn_on_fires_when_that_steering_diode_is_reversed():
    bad = move_pin(move_pin(GOOD, "D303", "A", "LEVER_L"), "D303", "K", "Q1_GATE")
    assert any("Q304" in e for e in fired(bad, "TURN-ON"))


def test_turn_on_fires_on_an_nfet_gate_commanded_by_nothing():
    bad = GOOD.without_pin("R310", "1")
    assert any("Q301" in e for e in fired(bad, "TURN-ON"))


def test_turn_on_accepts_a_gate_commanded_only_from_a_harness_contact():
    """Q105 is driven by the key switch, which is outside the box. With the
    KEY_SENSE divider gone, J102 is the only thing its gate reaches."""
    assert not fired(GOOD.without_part("R107"), "TURN-ON")


def test_turn_on_fires_when_the_level_shifter_has_no_drive():
    """The P-FET's path exists, but the N-FET in it can never turn on."""
    assert any("Q105" in e for e in fired(GOOD.without_part("R112"), "TURN-ON"))


# ── VR: the voltage line on every part ───────────────────────────────────────
def test_vr_standoff_fires_on_a_5v_tvs_on_the_11v4_lever_node():
    """Audit F-1 / C-H2: PESD5V0S4UD breaks down at 6.4 V; the lever node
    idles at 11.4 V; the stop lamp is lit for ever."""
    bad = GOOD.replace_part("D310", mpn="PESD5V0S4UD", v_max=5.0)
    assert any("D310" in e and "LEVER_L" in e for e in fired(bad, "VR-STANDOFF"))


def test_vr_domain_fires_when_the_lever_node_is_left_signal():
    """The defect was invisible because the net's domain defaulted to SIGNAL
    and the rule skipped it. No silent skip."""
    bad = GOOD.replace_net("LEVER_L", domain="SIGNAL")
    assert any("D310" in e and "LEVER_L" in e for e in fired(bad, "VR-DOMAIN"))


def test_vr_standoff_is_not_fooled_by_typing_the_lever_node_3v3():
    """DERIVED: R313 and D303 hold it at V12 with no path to ground."""
    bad = GOOD.replace_part("D310", mpn="PESD5V0S4UD", v_max=5.0)
    bad = bad.replace_net("LEVER_L", domain="3V3").replace_net("Q1_GATE", domain="3V3")
    errs = fired(bad, "VR-STANDOFF")
    assert any("LEVER_L" in e and "typed 3V3" in e and "12 V" in e for e in errs)


def test_vr_standoff_covers_the_84v_bus():
    bad = GOOD.replace_part("D101", mpn="SMCJ58A", v_max=58.0)
    assert any("D101" in e for e in fired(bad, "VR-STANDOFF"))


def test_vr_rated_fires_on_a_tvs_with_no_rating():
    """Audit 8a."""
    assert any("D310" in e for e in fired(GOOD.replace_part("D310", v_max=None), "VR-RATED"))


@pytest.mark.parametrize("ref", ["C105", "D303", "D102", "D101", "Q301", "Q101"])
def test_vr_rated_fires_for_every_kind_that_must_carry_a_rating(ref):
    assert any(ref in e for e in fired(GOOD.replace_part(ref, v_max=None), "VR-RATED"))


def test_vr_rated_fires_on_a_resistor_with_no_rating():
    """A resistor on the 84 V string is chosen by its working voltage: an
    unrated one is an unchecked one."""
    assert any("R110" in e for e in fired(GOOD.replace_part("R110", v_max=None), "VR-RATED"))


def test_a_zero_ohm_link_needs_no_rating():
    assert not [e for e in fired(GOOD, "VR-RATED") if "R211" in e]


def test_vr_under_fires_on_a_75v_resistor_on_the_84v_bus():
    """0603 thick film is rated 75 V.  R112 runs from KSW (84 V) with no clamp
    across it: under-rated.  R110 is across Q101's gate-source, which D102
    clamps to 15 V, so the same rating is enough there."""
    assert any("R112" in e for e in fired(GOOD.replace_part("R112", v_max=75.0), "VR-UNDER"))
    assert not [e for e in fired(GOOD.replace_part("R110", v_max=75.0), "VR-UNDER") if "R110" in e]


def test_vr_rated_rejects_a_rating_that_is_not_a_number():
    assert fired(GOOD.replace_part("C105", v_max=float("nan")), "VR-RATED")
    assert fired(GOOD.replace_part("C105", v_max=0.0), "VR-RATED")


def test_vr_datasheet_fires_on_a_rating_typed_above_the_datasheet():
    """Audit 8c: v_max=999 typed onto the array."""
    assert any("D310" in e for e in fired(GOOD.replace_part("D310", v_max=999.0), "VR-DATASHEET"))
    bad = GOOD.replace_part("D401", v_max=50.0)               # mutation N8
    assert any("D401" in e for e in fired(bad, "VR-DATASHEET"))


def test_vr_under_fires_on_a_30v_fet_on_an_84v_node():
    """Audit N14."""
    bad = GOOD.replace_part("Q105", mpn="AO3400A", v_max=30.0)
    assert any("Q105" in e for e in fired(bad, "VR-UNDER"))


def test_vr_under_fires_on_an_under_rated_capacitor():
    assert any("C105" in e for e in fired(GOOD.replace_part("C105", v_max=50.0), "VR-UNDER"))


def test_vr_under_fires_on_a_rated_ic():
    assert any("U405" in e for e in fired(GOOD.replace_part("U405", v_max=4.5), "VR-UNDER"))


def test_vr_lets_a_25v_cap_sit_across_a_zener_clamped_gate():
    """C107 is between two 84 V nets and sees 15 V, because D102 is across it."""
    assert not [e for e in rules.check_all(GOOD) if "C107" in e]
    assert any("C107" in e for e in fired(GOOD.without_part("D102"), "VR-UNDER"))
    assert any("C107" in e for e in fired(GOOD.replace_part("D102", dnp=True), "VR-UNDER"))


def test_vr_treats_a_zener_as_a_clamp_only_across_a_gate():
    assert not [e for e in rules.check_all(GOOD) if "D102" in e or "D106" in e]
    bad = GOOD.with_part(_d("D199", "OUTPUTS", "BZT52C5V1", "ZENER", 5.1))
    bad = add_pin(add_pin(bad, "LEVER_L", "D199", "K"), "GND", "D199", "A")
    assert any("D199" in e for e in fired(bad, "VR-UNDER"))


def test_vr_checks_dnp_parts_too():
    """A wrong part that is not fitted today is wrong the day it is."""
    bad = GOOD.replace_part("D406", mpn="PESD5V0S4UD", v_max=5.0)
    assert any("D406" in e for e in fired(bad, "VR-STANDOFF"))


# ── LV-LOGIC: nothing above 3.3 V on a 3.3 V pin ─────────────────────────────
def test_lv_logic_fires_on_12v_wired_to_an_mcu_pin():
    assert any("U401.IO10" in e for e in fired(add_pin(GOOD, "V12", "U401", "IO10"), "LV-LOGIC"))


def test_lv_logic_fires_on_a_lamp_feed_wired_to_the_expander():
    assert any("U402.GPB5" in e for e in fired(add_pin(GOOD, "HL_LOW", "U402", "GPB5"), "LV-LOGIC"))


def test_lv_logic_fires_on_a_pullup_to_12v_with_no_divider():
    bad = move_pin(GOOD, "R411", "1", "V12")
    assert any("SW_IN" in e and "R411" in e for e in fired(bad, "LV-LOGIC"))


def test_lv_logic_accepts_a_divider():
    assert not [e for e in fired(GOOD, "LV-LOGIC")]
    # KEY_SENSE hangs off 84 V through R107 -- and R109 holds it down
    assert fired(GOOD.without_part("R109"), "LV-LOGIC")


# ── PROT: fitted, at the connector, and returned to ground ───────────────────
def test_prot_fires_when_the_tvs_is_removed_from_the_net():
    assert any("HL_LOW" in e for e in fired(GOOD.without_pin("D310", "K6"), "PROT"))


def test_prot_fires_on_a_tvs_with_one_leg_floating():
    """Audit F-6: D104 / D105 had one terminal landed and counted as cover."""
    assert any("KSW" in e and "D104" in e for e in fired(GOOD.without_pin("D104", "A"), "PROT"))


def test_prot_fires_when_every_array_anode_is_lifted():
    """Audit 1b."""
    bad = GOOD.without_pin("D310", "A2").without_pin("D310", "A5")
    assert {"HL_LOW", "HORN_OUT", "LEVER_L", "STOP_OUT"} <= {
        m.group(1) for e in fired(bad, "PROT") if (m := re.search(r"net '(\w+)'", e))}


def test_prot_fires_on_a_dnp_tvs():
    """Audit 1c."""
    assert any("LEVER_L" in e and "DNP" in e
               for e in fired(GOOD.replace_part("D310", dnp=True), "PROT"))


def test_prot_fires_on_a_tvs_on_another_board():
    """Audit F-6: D405 sat on LOGIC while its connector moved to OUTPUTS."""
    assert any("is on LOGIC, not OUTPUTS" in e
               for e in fired(GOOD.replace_part("D310", board="LOGIC"), "PROT"))


def test_prot_fires_when_the_return_is_an_island_called_ground():
    """Audit F-3: LAMP_COMMON satisfied the old rule with the TVS anodes."""
    bad = GOOD.with_net(Net("LAMP_COMMON", (), domain="GND"))
    bad = move_pin(move_pin(bad, "D310", "A2", "LAMP_COMMON"), "D310", "A5", "LAMP_COMMON")
    assert fired(bad, "PROT")
    assert any("LAMP_COMMON" in e for e in fired(bad, "GND-ISLAND"))


def test_prot_is_not_satisfied_by_a_part_that_is_not_a_tvs():
    bad = GOOD.replace_part("D104", kind="D")
    assert any("KSW" in e for e in fired(bad, "PROT"))


def test_prot_needs_a_rail_clamp_where_the_rail_leaves_the_box():
    assert any("'V12'" in e and "J303" in e for e in fired(GOOD.without_part("D315"), "PROT"))


def test_prot_lets_a_parked_connector_keep_its_tvs_dnp_but_not_unwired():
    """Parked AND with its header unfitted: nothing can plug in, so its clamp
    may be unfitted too. The label alone excuses nothing (review CK-7)."""
    assert not [e for e in fired(GOOD, "PROT") if "J305" in e]
    assert any("J305" in e for e in fired(GOOD.without_pin("D406", "A"), "PROT"))
    assert any("J305" in e for e in fired(GOOD.replace_connector("J305", parked=False), "PROT"))
    assert any("J305" in e for e in fired(GOOD.replace_connector("J305", dnp=False), "PROT"))


def test_prot_reads_the_connector_table_as_well_as_the_net():
    j = GOOD.connector("J302")
    bad = GOOD.replace_connector("J302", pins=j.pins + (ConnPin("3", "HORN_GATE"),))
    assert any("HORN_GATE" in e and "J302" in e for e in fired(bad, "PROT"))


def test_prot_ignores_internal_connectors_and_ground_pins():
    assert not [e for e in fired(GOOD, "PROT")]


# ── GND-ISLAND ───────────────────────────────────────────────────────────────
def test_ground_island_accepts_a_plate_tied_by_a_fitted_link():
    assert not fired(GOOD, "GND-ISLAND")


def test_ground_island_fires_when_the_tie_is_dnp_or_missing():
    assert any("BASEPLATE" in e for e in fired(GOOD.replace_part("R211", dnp=True), "GND-ISLAND"))
    assert any("BASEPLATE" in e for e in fired(GOOD.without_part("R211"), "GND-ISLAND"))


def test_ground_island_accepts_a_return_behind_a_choke_winding():
    assert not fired(GOOD.replace_net("HV_C1_N", domain="GND"), "GND-ISLAND")


# ── MCP-OUT7 ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("pin", ["GPA7", "GPB7"])
def test_mcp_bit7_is_never_netted(pin):
    assert not fired(GOOD, "MCP-OUT7")
    bad = add_pin(GOOD.without_pin("U402", "GPB3"), "POD2_IN", "U402", pin)
    assert any(pin in e for e in fired(bad, "MCP-OUT7"))


# ── POL ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ref", ["D104", "D303", "D102"])
def test_pol_fires_on_a_diode_with_numbered_pins(ref):
    """Audit C-H6: D104 was netted as pin `1`; polarity undefined."""
    assert any(ref in e for e in fired(GOOD.replace_part(ref, pins=("1", "2")), "POL"))


def test_pol_allows_a_bidirectional_tvs():
    ok = GOOD.replace_part("D315", mpn="SMBJ15CA", pins=("1", "2"))
    assert not fired(ok, "POL")


# ── HT: heights, for every body in the stack ─────────────────────────────────
# The stack is DERIVED by board_params.stack_height() from the design's own
# heights, so these tests state outcomes ("this does not fit") and take every
# number from that module -- never a typed ceiling.
def _tallest_on_top_of(d, board):
    """Tallest top-side body on a board, inter-board connectors aside."""
    return max([p.height_mm for p in d.parts if p.board == board and p.side == "top"]
               + [c.height_mm for c in d.connectors
                  if c.board == board and c.interface is None])


def test_ht_good_design_fits():
    assert not fired(GOOD, "HT-NUM") and not fired(GOOD, "HT-STACK")


def test_ht_fires_on_a_connector_too_tall_for_the_stack(binding_envelope):
    """Audit F-12 / D-4: the stack's margin lived in connector heights that
    no rule could see."""
    for ref in ("J306", "J401", "J101"):
        bad = GOOD.replace_connector(ref, height_mm=bp.AVAIL_H)
        assert fired(bad, "HT-STACK"), ref


def test_ht_polices_every_board_not_just_one(binding_envelope):
    for ref in ("Q101", "U201", "U301", "U405"):
        bad = GOOD.replace_part(ref, height_mm=bp.AVAIL_H)
        assert fired(bad, "HT-STACK"), GOOD.part(ref).board


def test_ht_fires_on_a_nan_height():
    """nan > 6.0 is False: an unknown height was an unchecked height."""
    assert any("U405" in e for e in fired(GOOD.replace_part("U405", height_mm=float("nan")), "HT-NUM"))
    assert any("J306" in e for e in fired(GOOD.replace_connector("J306", height_mm=float("nan")), "HT-NUM"))
    assert fired(GOOD.replace_part("U405", height_mm=float("inf")), "HT-NUM")
    assert fired(GOOD.replace_part("U405", height_mm=-1.0), "HT-NUM")
    assert fired(GOOD.replace_part("U405", height_mm=None), "HT-NUM")


def test_ht_does_not_exempt_a_bottom_side_part(binding_envelope):
    """Audit 4b: a 40 mm part marked side='bottom' passed."""
    bad = GOOD.replace_part("U402", side="bottom", height_mm=bp.AVAIL_H)
    assert fired(bad, "HT-STACK")


def test_ht_checks_a_bottom_side_part_against_the_gap_below_it():
    """With the PWR-LOGIC pair chosen (both heights confirmed) the
    OUTPUTS->LOGIC spacing is fixed at 10.0 + 2.0; a part hanging deeper under
    LOGIC than that does not fit."""
    chosen = GOOD.replace_connector("J307", height_confirmed=True, height_mm=10.0)
    chosen = chosen.replace_connector("J407", height_confirmed=True, height_mm=2.0)
    fits = chosen.replace_part("U402", side="bottom", height_mm=5.0)
    assert not fired(fits, "HT-STACK")
    errs = fired(chosen.replace_part("U402", side="bottom", height_mm=13.0), "HT-STACK")
    assert any("U402" in e for e in errs)


def test_ht_relays_every_stack_problem(monkeypatch):
    monkeypatch.setattr(rules, "_stack_problems", lambda d: ["first", "second"])
    assert fired(GOOD, "HT-STACK") == ["HT-STACK: first", "HT-STACK: second"]


def test_ht_says_so_when_there_is_no_geometry_to_check_against(monkeypatch):
    monkeypatch.setattr(rules, "_stack_problems", None)
    monkeypatch.setattr(rules, "_stack_height", None)
    assert fired(GOOD, "HT-GEOM")
    assert isinstance(rules.warnings(GOOD), list)


# ── warnings: reported, never trusted, never a gate failure ──────────────────
# ── BUS-ORDER ────────────────────────────────────────────────────────────────
def _rebus(d, iface, nets):
    out = d
    for c in d.connectors:
        if c.interface == iface:
            out = out.replace_connector(c.refdes, pins=tuple(
                ConnPin(str(i + 1), n) for i, n in enumerate(nets)))
    return out


def test_bus_order_fires_on_a_bus_that_reads_differently_reversed():
    """A bus that is not palindromic: mated reversed, V12 lands where V5 was."""
    bad = _rebus(GOOD, "PWR-OUT", ("V12", "GND", "KEY_SENSE", "GND", "V5"))
    assert any("PWR-OUT" in e and "both ends" in e for e in fired(bad, "BUS-ORDER"))


def test_bus_order_fires_on_a_rail_beside_a_signal():
    """Palindromic, but one contact off puts V12 on KEY_SENSE."""
    bad = _rebus(GOOD, "PWR-OUT", ("GND", "V12", "KEY_SENSE", "V12", "GND"))
    errs = fired(bad, "BUS-ORDER")
    assert any("V12 beside KEY_SENSE" in e for e in errs)
    assert not any("both ends" in e for e in errs)


def test_bus_order_lets_a_converter_return_sit_beside_its_feed():
    """HV_C1_N joins GND through the choke's winding: a shift that lands the
    feed on it shorts the input, the same as landing it on GND. No bus in this
    design carries a converter pair -- both stay on POWER -- so the exemption is
    shown on a bus built to hold one."""
    assert not fired(GOOD, "BUS-ORDER")
    pair = ("HV_C1_P", "HV_C1_N", "GND", "KEY_SENSE", "GND", "HV_C1_N", "HV_C1_P")
    assert not fired(_rebus(GOOD, "PWR-OUT", pair), "BUS-ORDER")


def test_bus_order_leaves_the_stack_to_its_ground_row():
    stack = GOOD.connector("J308")
    odd = _rebus(GOOD, "STACK", tuple(cp.net for cp in stack.pins)[::-1][:-1] + ("GND",))
    assert not fired(odd, "BUS-ORDER")


def _warned(d, wid, ref=None):
    return [w for w in rules.warnings(d)
            if w.startswith(wid + ":") and (ref is None or f" {ref} " in f" {w}")]


def test_unconfirmed_height_near_what_sets_its_gap_is_a_warning_not_an_error():
    top = _tallest_on_top_of(GOOD, "LOGIC")
    near = GOOD.replace_part("U405", height_mm=top - 1.5)
    assert rules.check_all(near) == []
    assert _warned(near, "HT-W1", "U405")
    assert not _warned(near.replace_part("U405", height_confirmed=True), "HT-W1", "U405")
    far = GOOD.replace_part("U405", height_mm=top - 2.5)
    assert not _warned(far, "HT-W1", "U405")


def test_unconfirmed_connector_height_is_warned_about_too():
    assert _warned(GOOD, "HT-W1", "J306")                     # a harness connector
    assert not _warned(GOOD.replace_connector("J306", height_confirmed=True),
                       "HT-W1", "J306")


def test_unconfirmed_underside_part_is_warned_about():
    deep = GOOD.replace_part("C201", height_mm=9.0)
    assert _warned(deep, "HT-W1", "C201")
    assert not _warned(deep.replace_part("C201", height_confirmed=True), "HT-W1", "C201")


def test_an_unconfirmed_inter_board_connector_is_warned_about():
    assert _warned(GOOD, "HT-W1", "J308")
    chosen = GOOD.replace_connector("J308", height_confirmed=True)
    assert not _warned(chosen, "HT-W1", "J308")


def test_stack_notes_and_load_bearing_heights_are_relayed(monkeypatch):
    class Stack:
        notes = ("keep-out: X under Y",)
        load_bearing = ("R307",)                 # far from tallest on OUTPUTS
    assert not _warned(GOOD, "HT-W1", "R307")
    monkeypatch.setattr(rules, "_stack_height", lambda d: Stack())
    assert _warned(GOOD, "HT-W2") == ["HT-W2: keep-out: X under Y"]
    assert _warned(GOOD, "HT-W1", "R307")


def test_a_connector_declared_internal_with_no_interface_is_warned():
    """Connector.leaves_box is the one hand-typed flag left. It cannot be
    derived, so it is surfaced: flip a harness connector to 'internal' and it
    shows up here by name."""
    assert _warned(GOOD, "BOX-W1") == _warned(GOOD, "BOX-W1", "J408") != []
    flipped = GOOD.replace_connector("J306", leaves_box=False)
    assert _warned(flipped, "BOX-W1", "J306")


# --- D10: the module only listens to the key wire ----------------------------
def _real_design():
    from tools import netlist
    return netlist.current()


def _with_extra_pins(d, net_name, pins):
    return d.replace_net(net_name, pins=d.net(net_name).pins + tuple(pins))


def test_d10_is_quiet_on_the_real_design():
    assert [e for e in rules.check_all(_real_design()) if e.startswith("D10")] == []


def test_d10_fires_on_a_diode_from_the_switched_rail_onto_the_key_wire():
    """The self-latch: HV_SW -> diode -> KSW holds the module AND the
    FarDriver KEY on with the key out. It passed every gate before D10 had a
    rule of its own."""
    d = _real_design().with_part(Part(
        "D999", "1N4007", "DO-41", "POWER", "D", ("A", "K"), 3.0, v_max=1000.0,
        source="fixture"))
    d = _with_extra_pins(d, "HV_SW", [("D999", "A")])
    d = _with_extra_pins(d, "KSW", [("D999", "K")])
    assert any(e.startswith("D10") for e in rules.check_all(d))


def test_d10_fires_on_a_fet_channel_onto_the_key_wire_even_if_dnp():
    d = _real_design().with_part(Part(
        "Q999", "IXTP26P20P", "TO-220", "POWER", "PFET", ("G", "D", "S"), 5.0,
        v_max=200.0, dnp=True, source="fixture"))
    d = _with_extra_pins(d, "HV_BPLUS", [("Q999", "S")])
    d = _with_extra_pins(d, "KSW", [("Q999", "D")])
    d = _with_extra_pins(d, "D13_GATE", [("Q999", "G")])
    assert any(e.startswith("D10") for e in rules.check_all(d))


def test_d10_allows_the_resistive_taps_and_the_tvs():
    ksw = {r for r, _ in _real_design().net("KSW").pins}
    kinds = {_real_design().part(r).kind for r in ksw if not r.startswith("J")}
    assert kinds <= {"R", "TVS"}, kinds


# --- SUPPLY: an IC on a rail it cannot take -----------------------------------
def test_supply_is_quiet_on_the_real_design():
    assert [e for e in rules.check_all(_real_design()) if e.startswith("SUPPLY")] == []


@pytest.mark.parametrize("refdes,pin,wrong_rail", [
    ("U404", "VCC", "V5"),       # a 3.3 V transceiver on 5 V: abs max 4 V
    ("U402", "VDD", "V5"),       # the expander would drive 5 V into ESP32 pins
    ("U301", "VS", "HV_BPLUS"),  # a 40 V switch on the 84 V pack
])
def test_supply_fires_on_an_ic_moved_to_the_wrong_rail(refdes, pin, wrong_rail):
    d = _real_design()
    old = d.net_of(refdes, pin).name
    d = d.without_pin(refdes, pin)
    d = d.replace_net(wrong_rail, pins=d.net(wrong_rail).pins + ((refdes, pin),))
    errs = [e for e in rules.check_all(d) if e.startswith("SUPPLY")]
    assert any(f"{refdes}.{pin}" in e for e in errs), (old, errs)


def test_supply_reports_an_ic_it_knows_nothing_about():
    d = _real_design().with_part(Part(
        "U999", "LM358", "SOIC-8", "LOGIC", "IC", ("V+", "V-"), 1.75, source="fixture"))
    d = d.replace_net("V3P3", pins=d.net("V3P3").pins + (("U999", "V+"),))
    d = d.replace_net("GND", pins=d.net("GND").pins + (("U999", "V-"),))
    assert any("SUPPLY: U999" in e and "no entry" in e for e in rules.check_all(d))


# --- a pin's reset-time pull must not switch a load on --------------------------------
def test_a_driver_on_a_pin_pulled_up_at_reset_fires():
    """ESP32-S3 datasheet v2.2 Table 2-1: GPIO39 (MTCK) comes out of reset with
    its weak pull-up on (note 7, EFUSE_DIS_PAD_JTAG = 0).  Through a 4.7 kΩ
    series resistor that beats the TPS4H160's 100-250 kΩ input pull-down, so a
    lamp on GPIO39 lights before firmware runs -- and stays lit if it hangs."""
    from tools import netlist
    real = netlist.current()
    assert not fired(real, "GPIO-RESET-PULL")
    moved = on_gpio(on_gpio(real, "FAULT1", 18), "LGT_TAIL", 39)
    hits = fired(moved, "GPIO-RESET-PULL")
    assert any("LGT_TAIL" in e and "GPIO39" in e for e in hits), hits


def test_an_input_on_a_pin_pulled_up_at_reset_is_fine():
    """FAULT is an open-drain input to the MCU: a reset pull-up there only
    joins the one it already has."""
    from tools import netlist
    real = netlist.current()
    moved = on_gpio(real, "FAULT1", 39) if real.net("FAULT1").gpio != "GPIO39" else real
    assert not fired(moved, "GPIO-RESET-PULL")


def test_only_a_truly_high_impedance_input_goes_unclamped():
    """KSW reaches only ≥ 330 kΩ strings and carries no TVS (a clamp there is
    the one part that fails short and blows the key fuse).  The exemption
    must not cover a wire that reaches anything of lower impedance."""
    from tools import netlist
    real = netlist.current()
    assert not fired(real, "PROT")
    low = real.replace_part("R107", value="10k")
    assert any("KSW" in e for e in fired(low, "PROT"))
