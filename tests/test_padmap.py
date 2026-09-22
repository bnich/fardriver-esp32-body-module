"""Which footprint pad each netlist pin lands on.

The symbol's pins carry the netlist's names (A/K, G/D/S, VS, GPA0); a footprint's
pads carry numbers.  EasyEDA joins them by matching the two, so each footprint's
pads are renamed to the pins they carry.  A wrong entry here wires a transistor
backwards on a board that passes every other check, so the tables are typed
from the datasheets and checked two ways: they must cover every pin of every
fitted item, and -- where this machine can reach EasyEDA's library -- they must
agree with the library symbol's own pin numbers and names.
"""
import json

import pytest

from tools import netlist, padmap
from tools.model import ConnPin, Connector, Part


@pytest.fixture(scope="module")
def d():
    return netlist.current()


def _fitted(d):
    return [p for p in d.parts if not p.dnp] + list(d.connectors)


def test_every_fitted_item_with_a_footprint_has_a_map_covering_every_pin(d):
    for x in _fitted(d):
        m = padmap.pad_map(x)
        pins = set(padmap.pins_of(x))
        landed = {pin for pin in m.values() if pin is not None}
        assert pins <= landed, f"{x.refdes}: pins with no pad: {sorted(pins - landed)}"
        extra = landed - pins - set(getattr(x, "nc", ()))
        assert not extra, f"{x.refdes}: pads name pins it does not have: {sorted(extra)}"


@pytest.mark.parametrize("mpn,pad,pin", [
    ("AO3400A", "1", "G"), ("AO3400A", "2", "S"), ("AO3400A", "3", "D"),
    ("BSS127", "3", "D"), ("IXTA26P20P-TRL", "2", "D"), ("IXTA26P20P-TRL", "3", "S"),
    ("SS14", "1", "K"), ("SMCJ90A", "2", "A"),
    # R+O SMF18A rev 2.2 p.4: the band is at pad 2, so pad 1 is the ANODE --
    # deliberately opposite the generic diode rule. Reversed, the clamp shorts
    # its lamp output to ground through the driver.
    ("SMF18A", "1", "A"), ("SMF18A", "2", "K"),
    # TI SLVSCV8E, HTSSOP-28: VS on 20-23, OUT4 on 15-16, OUT1 on 27-28. VS and
    # OUT swapped puts the 12 V rail on a lamp channel and its load on the
    # driver's supply pins.
    ("TPS4H160BQPWPRQ1", "20", "VS"), ("TPS4H160BQPWPRQ1", "23", "VS"),
    ("TPS4H160BQPWPRQ1", "15", "OUT4"), ("TPS4H160BQPWPRQ1", "16", "OUT4"),
    ("TPS4H160BQPWPRQ1", "27", "OUT1"), ("TPS4H160BQPWPRQ1", "28", "OUT1"),
    ("TPS4H160BQPWPRQ1", "3", "IN1"), ("TPS4H160BQPWPRQ1", "1", "GND"),
])
def test_the_pins_a_reversal_would_hurt(d, mpn, pad, pin):
    part = next(p for p in d.parts if p.mpn == mpn)
    assert padmap.pad_map(part)[pad] == pin


def test_the_wroom_matches_the_pads_its_source_cites(d):
    """netlist.py U401: GND = pads 1 and 40, EPAD = 41, IO43 = 37, IO44 = 36."""
    m = padmap.pad_map(d.part("U401"))
    assert (m["1"], m["40"], m["41"], m["37"], m["36"]) == ("GND", "GND", "EPAD", "IO43", "IO44")


def test_every_exposed_pad_is_on_ground(d):
    """The library check accepts a library 'GND' for our EPAD/PAD; that is
    only sound while every exposed pad really is on GND."""
    for p in d.parts:
        for pin in ("EPAD", "PAD"):
            if pin in p.pins:
                net = d.net_of(p.refdes, pin)
                assert net is not None and net.name == "GND", f"{p.refdes}.{pin} is on {net}"


def test_the_tlv767_matches_its_source(d):
    """netlist.py U405: OUT 1, SNS 2, NC 3 and 7, GND 4 and 6, EN 5, IN 8, pad."""
    m = padmap.pad_map(d.part("U405"))
    assert [m[str(n)] for n in range(1, 10)] == ["OUT", "SNS", "NC", "GND", "EN", "GND", "NC", "IN", "PAD"]


def test_the_buck_matches_its_source(d):
    """netlist.py U305 and TI SNVSAH5A p.3-4: SW 1-5, CBOOT 6, VCC 7, BIAS 8,
    RT 9, SS/TRK 10, FB 11, NC 12-15 and 27-30, PGOOD 16, SYNC/MODE 17, EN 18,
    AGND 19, PVIN 20-22, PGND 23-26, DAP.  A swapped PVIN and SW would put the
    12 V rail on the inductor and the switch node on the input capacitors."""
    m = padmap.pad_map(d.part("U305"))
    assert [m[str(n)] for n in range(1, 12)] == \
        ["SW"] * 5 + ["CBOOT", "VCC", "BIAS", "RT", "SS/TRK", "FB"]
    assert [m[str(n)] for n in (16, 17, 18, 19)] == \
        ["PGOOD", "SYNC/MODE", "EN", "AGND"]
    assert [m[str(n)] for n in (20, 21, 22)] == ["PVIN"] * 3
    assert [m[str(n)] for n in (23, 24, 25, 26)] == ["PGND"] * 4
    assert {m[str(n)] for n in (12, 13, 14, 15, 27, 28, 29, 30)} == {"NC"}
    assert m["31"] == "PAD"


def test_the_load_switch_matches_its_source(d):
    """netlist.py U306-U309 and TI SLVS841F p.5, DBV: IN 1, GND 2, EN 3,
    FAULT 4, ILIM 5, OUT 6.  IN and OUT reversed would back-feed the buck
    through the switch's body diode with its enable low."""
    for n in range(6, 10):
        m = padmap.pad_map(d.part(f"U30{n}"))
        assert [m[str(i)] for i in range(1, 7)] == \
            ["IN", "GND", "EN", "FAULT", "ILIM", "OUT"], f"U30{n}"


# --- the independent check: EasyEDA's library symbol --------------------------------
# From tests/fixtures/lcsc.json (tools/lcsc_fixture.py), so the check runs
# offline and cannot skip: offline it once did, and a reversed brake-lamp FET
# passed (review CK-9). tests/test_lcsc_records.py holds the fixture to the
# live library.
def _library_pins():
    from tools import lcsc_fixture
    return {code: rec["symbol_pins"] for code, rec in lcsc_fixture.load().items()}


def _part(kind="IC", package="SOIC-8", pins=("1", "2")):
    return Part("X1", "x", package, "LOGIC", kind, tuple(pins), 1.0)


_CONN = Connector("J1", "LOGIC", "j", (ConnPin("1", "GND"), ConnPin("2", "V5")), 5.0)


@pytest.mark.parametrize("ours, lib, x, agree", [
    # Agreement, one case per alias class in `_LIB_ALIASES` and the rules:
    ("VS", "VS", _part(), True),
    ("vs", "VS", _part(), True),                       # case
    ("GND", "GND#", _part(), True),                    # a trailing '#'
    ("K", "4", _part("TVS"), True),                    # numeric: no information
    ("K", "", _part("TVS"), True),                     # unnamed: no information
    ("K", "None", _part("TVS"), True),
    ("EPAD", "EP", _part(), True), ("PAD", "EP", _part(), True),
    ("PAD", "GND", _part(), True), ("EPAD", "GND", _part(), True),
    ("K", "C", _part("D"), True),                      # cathode as 'C'
    ("IO44", "RXD0", _part("MODULE"), True), ("IO43", "TXD0", _part("MODULE"), True),
    ("FAULT", "/FAULT", _part(), True),
    ("NC11", "NC", _part(), True),                     # our numbered NC pins
    ("K1", "K", _part("TVS"), True),                   # array pin: its role
    ("A2", "A", _part("TVS"), True),
    ("1", "GND", _CONN, True),                         # a connector pad: its net
    # Disagreement -- the reversals a wrong table would make:
    ("D", "S", _part("NFET", "SOT-23", ("G", "D", "S")), False),
    ("S", "D", _part("NFET", "SOT-23", ("G", "D", "S")), False),
    ("G", "D", _part("PFET", "TO-263AA", ("G", "D", "S")), False),
    ("A", "K", _part("TVS", "SOD-123FL", ("A", "K")), False),
    ("K", "A", _part("D", "SMA", ("A", "K")), False),
    ("VS", "OUT4", _part(), False), ("OUT4", "VS", _part(), False),
    ("OUT1", "OUT2", _part(), False),
    ("IN", "OUT", _part(), False),
    ("K1", "A", _part("TVS"), False),                  # array cathode on an anode pad
    ("A2", "K", _part("TVS"), False),
    ("PAD", "VS", _part(), False),                     # an exposed pad on a supply
    ("GND", "VDD", _part(), False),
    ("NC11", "GND", _part(), False),                   # our NC on a real pin
    ("GND", "NC", _part(), False),                     # a real pin on the library's NC
    ("K1", "K", _part("IC"), False),                   # 'K1' is a role only on a TVS
    ("2", "GND", _CONN, False),                        # connector pad 2 is V5
    ("1", "V5", _CONN, False),
])
def test_names_agree_says_yes_to_each_alias_class_and_no_to_a_reversal(ours, lib, x, agree):
    """The library check hangs on this one predicate (H17): until 2026-09-21
    nothing ever handed it a mismatch, and `return True` at its top passed
    every test."""
    assert padmap.names_agree(ours, lib, x) is agree


def test_every_map_agrees_with_the_library_symbol(d):
    """For each LCSC part, the library symbol's NUMBER -> NAME must agree with
    our table wherever the library names a pin (an unnamed or purely numeric
    library pin carries no information to check)."""
    lib_pins = _library_pins()
    checked = 0
    # Unfitted parts too: their footprint is on the board, waiting to be fitted.
    for x in list(d.parts) + list(d.connectors):
        code = padmap.footprint_source(x)
        if not code:
            continue
        assert code in lib_pins, f"{x.refdes}: {code} is not in the fixture"
        lib = lib_pins[code]
        if not lib:
            continue
        m = padmap.pad_map(x)
        for num, name in lib:
            if num not in m or m[num] is None:
                continue
            assert padmap.names_agree(m[num], name, x), (
                f"{x.refdes} ({code}) pad {num}: our {m[num]!r}, library {name!r}")
        checked += 1
    assert checked > 30


#: Pad maps the library cannot check -- its symbol numbers the pins 1..n and
#: names none of them -- typed from the datasheet and pinned here, pad -> pin.
PINNED = {
    # onsemi SMS05T1/D rev 10 p.1: pads 1/3/4/6 cathodes, 2/5 the common anode.
    "SMS05T1G": {"1": "K1", "2": "A2", "3": "K3", "4": "K4", "5": "A5", "6": "K6"},
    "SMS15T1G": {"1": "K1", "2": "A2", "3": "K3", "4": "K4", "5": "A5", "6": "K6"},
    # ST USBLC6-2 p.1: 1 I/O1, 2 GND, 3 I/O2, 4 I/O2, 5 VBUS, 6 I/O1.
    "USBLC6-2SC6": {"1": "IO1A", "2": "GND", "3": "IO2A", "4": "IO2B", "5": "VBUS",
                    "6": "IO1B"},
}


def test_a_map_the_library_cannot_check_is_pinned_from_its_datasheet(d):
    """A numeric-only library symbol agrees with ANY map (review CK-6: a
    wrong SMS05 map clamps every line to ground and passed). Every part whose
    map renames pads the library does not name is pinned here instead."""
    lib_pins = _library_pins()
    for x in d.parts:
        code = padmap.footprint_source(x)
        lib = lib_pins.get(code) if code else None
        if not lib or any(not str(name).strip().rstrip("#").isdigit() for _, name in lib):
            continue
        m = padmap.pad_map(x)
        if all(m.get(num) == num for num, _ in lib):
            continue                             # numbered pins mapped to themselves
        assert x.mpn in PINNED, f"{x.refdes} ({x.mpn}): a map no library checks"
        assert m == PINNED[x.mpn], x.refdes
