"""Which footprint pad each netlist pin lands on.

A symbol pin carries the netlist's name for it (A/K, G/D/S, VS, GPA0); a
footprint pad carries a number.  EasyEDA joins a symbol to a footprint by
matching those two, so every footprint's pads are renamed to the pins they
carry before the footprint is embedded.  The schematic, the read-back and the
gauge are untouched by this: they never see a pad number.

⛔ A wrong entry wires a transistor backwards on a board that passes every other
check.  The tables are TYPED FROM THE DATASHEETS the parts' own `source` cites,
and tests/test_padmap.py checks them against EasyEDA's library symbols, which
are an independent reading of the same datasheets.

`pad_map(item)` returns {pad number: pin name}.  A pad mapped to None is left
unconnected on purpose (a contact the design does not use).
"""
import json
import re
from collections import defaultdict

from .model import Connector, Part

# ── Parts JLC places from EasyEDA's library, by the footprint they use ───────
#: Where a part's footprint comes from when it is not its own LCSC part:
#: hand-soldered parts, and LCSC parts EasyEDA's library has no device for.
#: None means the footprint is generated here, from the part's datasheet.
FOOTPRINT_FROM_MPN = {
    "VY2472M49Y5US6": None,         # drawn FLAT: 7.5 mm leads (C1620119's library land is 10 mm)
    "EKXJ221ELL221MM25S": None,     # drawn LYING, with its body outline
    "PA35V680M10x15": None,         # drawn LYING, with its body outline
    "01110501Z": None,              # both clips in one drawn footprint, 17.8 mm apart
    "CN150B110-12/CO": None,        # no library device: generated from TDK's drawing
    "EC7BW-110S05": None,           # no library device: generated from Cincon's drawing
    "7448022010": None,             # no library device: generated from Würth's drawing
    "NET-TIE": None,                # copper, generated
    "0001.2504": None,              # the fuse: never on the PCB, a stand-in (drawn_footprints)
}

# ── Explicit tables, pad -> pin, typed from each datasheet ────────────────────
_TPS4H160 = {  # TI SLVSCV8E, PWP (HTSSOP-28) pin table
    "1": "GND", "2": "NC", "3": "IN1", "4": "IN2", "5": "IN3", "6": "IN4",
    "7": "SEH", "8": "SEL", "9": "FAULT", "10": "CS", "11": "CL", "12": "GND",
    "13": "THER", "14": "DIAG_EN", "15": "OUT4", "16": "OUT4", "17": "OUT3",
    "18": "OUT3", "19": "NC", "20": "VS", "21": "VS", "22": "VS", "23": "VS",
    "24": "NC", "25": "OUT2", "26": "OUT2", "27": "OUT1", "28": "OUT1", "29": "PAD",
}
_MCP23017_SS = {  # Microchip DS20001952D Table 2-1: SSOP / SOIC / SPDIP pins 1-28
    **{str(i + 1): f"GPB{i}" for i in range(8)},
    "9": "VDD", "10": "VSS", "11": "NC11", "12": "SCK", "13": "SDA", "14": "NC14",
    "15": "A0", "16": "A1", "17": "A2", "18": "RESET", "19": "INTB", "20": "INTA",
    **{str(21 + i): f"GPA{i}" for i in range(8)},
}
_WROOM1 = {  # Espressif ESP32-S3-WROOM-1/1U datasheet v1.8, Table 3-1
    "1": "GND", "2": "3V3", "3": "EN", "4": "IO4", "5": "IO5", "6": "IO6", "7": "IO7",
    "8": "IO15", "9": "IO16", "10": "IO17", "11": "IO18", "12": "IO8", "13": "IO19",
    "14": "IO20", "15": "IO3", "16": "IO46", "17": "IO9", "18": "IO10", "19": "IO11",
    "20": "IO12", "21": "IO13", "22": "IO14", "23": "IO21", "24": "IO47", "25": "IO48",
    "26": "IO45", "27": "IO0", "28": "IO35", "29": "IO36", "30": "IO37", "31": "IO38",
    "32": "IO39", "33": "IO40", "34": "IO41", "35": "IO42", "36": "IO44", "37": "IO43",
    "38": "IO2", "39": "IO1", "40": "GND", "41": "EPAD",
}
_BY_MPN = {
    "TPS4H160BQPWPRQ1": _TPS4H160,
    "MCP23017T-E/SS": _MCP23017_SS,
    "ESP32-S3-WROOM-1U-N8": _WROOM1,
    # R+O SMF18A datasheet rev 2.2 p.4: "Cathode Band: unidirectional only".
    # EasyEDA's footprint for C19077512 draws that band at pad 2, and its
    # symbol numbers K = 2: pad 1 is the ANODE here, unlike the generic
    # diode rule below -- a reversed clamp would short its lamp output.
    "SMF18A": {"1": "A", "2": "K"},
    # TI SBVS157E p.4, TLV803 DBZ (SOT-23): GND 1, RESET 2, VDD 3
    "TLV803SDBZR": {"1": "GND", "2": "RESET", "3": "VDD"},
    # TI SLOS346O, D (SOIC-8)
    "SN65HVD230DR": {"1": "D", "2": "GND", "3": "VCC", "4": "R", "5": "Vref",
                     "6": "CANL", "7": "CANH", "8": "RS"},
    # TI SLVSE84D p.3-4, DGN fixed: OUT 1, SNS 2, NC 3/7, GND 4/6, EN 5, IN 8, pad
    "TLV76733DGNR": {"1": "OUT", "2": "SNS", "3": "NC", "4": "GND", "5": "EN",
                     "6": "GND", "7": "NC", "8": "IN", "9": "PAD"},
    # IXYS DS99913D p.3, TO-263: 1 gate, 2 drain (and the tab), 3 source
    "IXTA26P20P-TRL": {"1": "G", "2": "D", "3": "S"},
}
def pins_of(x):
    """The pins that must land on a pad."""
    if isinstance(x, Connector):
        return tuple(cp.pin for cp in x.pins)
    return tuple(x.pins)


def footprint_source(x):
    """The LCSC part whose library footprint `x` uses, or None when its
    footprint is generated here (or, for an inter-board connector, not yet
    chosen)."""
    mpn = getattr(x, "mpn", "")
    if mpn in FOOTPRINT_FROM_MPN:
        return FOOTPRINT_FROM_MPN[mpn]
    return x.lcsc or None


def pad_map(x):
    """{pad: pin} for `x`.  Raises for a part with no rule: a guess is how a
    transistor ends up backwards."""
    if isinstance(x, Connector):
        return {p: p for p in pins_of(x)}
    pins = tuple(x.pins)
    if x.mpn in _BY_MPN:
        return dict(_BY_MPN[x.mpn])
    if x.kind in ("R", "C") and set(pins) == {"1", "2"}:
        return {"1": "1", "2": "2"}
    if x.kind == "C" and set(pins) == {"+", "-"}:
        return {"1": "+", "2": "-"}          # pad 1 is the positive lead
    if x.kind in ("D", "ZENER", "TVS") and set(pins) == {"A", "K"}:
        return {"1": "K", "2": "A"}          # pad 1 is the cathode (band)
    if x.kind in ("NFET", "PFET") and x.package == "SOT-23":
        return {"1": "G", "2": "S", "3": "D"}
    if x.kind == "TVS" and all(re.fullmatch(r"[AK]\d", p) for p in pins):
        return {p[1:]: p for p in pins}      # SMS05/15: pads 1/3/4/6 K, 2/5 A
    if footprint_source(x) is None:
        return {p: p for p in pins + tuple(x.nc)}   # generated: pads ARE the pins
    if pins == tuple(str(i + 1) for i in range(len(pins))):
        return {p: p for p in pins}
    raise KeyError(f"{x.refdes} ({x.mpn}): no pad map -- add one from its datasheet")


# ── the independent check ──────────────────────────────────────────────────────
def library_pins(v2_symbol_text):
    """[(NUMBER, NAME)] from an EasyEDA V2 symbol document."""
    recs = [r for r in (json.loads(line) for line in v2_symbol_text.splitlines()
                        if line.strip()) if r]
    attrs = defaultdict(dict)
    for r in recs:
        if r[0] == "ATTR":
            attrs[r[2]][r[3]] = r[4]
    return [(str(attrs[r[1]].get("NUMBER")), str(attrs[r[1]].get("NAME")))
            for r in recs if r[0] == "PIN"]


#: Library names for a pin we name otherwise.  GND -> EPAD/PAD holds only
#: because the netlist lands every exposed pad on GND (tests check that).
_LIB_ALIASES = {"EP": {"PAD", "EPAD"}, "GND": {"PAD", "EPAD"}, "C": {"K"},
                "RXD0": {"IO44"}, "TXD0": {"IO43"}}


def names_agree(ours, lib_name, x):
    """Does the library's NAME for a pad agree with the pin we put there?  A
    purely numeric library name carries no information and agrees."""
    lib = (lib_name or "").strip().upper().rstrip("#")
    if not lib or lib.isdigit() or lib == "NONE":
        return True
    if isinstance(x, Connector):
        net = next((cp.net for cp in x.pins if cp.pin == ours), None)
        return lib == net
    mine = ours.upper()
    if x.kind == "TVS" and re.fullmatch(r"[AK]\d", mine):
        mine = mine[0]                 # an array pin's role, not its index
    if mine == lib or mine in _LIB_ALIASES.get(lib, ()):
        return True
    return lib == "NC" and mine.startswith("NC")
