"""THE DESIGN: every part, net and connector of the four-board set.

Shape lives in `model.py`; this file is content only. `integrity.py` is the
structural gate: every declared pin of every part lands on exactly one net.

Conventions
  REFDES    board-scoped hundreds: HVIN 1xx · CONV 2xx · DRV 3xx · BRAIN 4xx.
            The display block (J405, D405, D406, R426-R429) carries 4xx numbers
            and sits on DRV. The documents' informal names (`D13`, `Q1`, `R4`,
            `C1`) are quoted in `source` so they stay greppable.
  PINS      functional names from the datasheet; where several pads share one
            name (`VS`, `GND`, `OUT1`) the pad numbers are in `source`.
            Passives 1/2 · polarised caps +/- · diodes A/K · FETs G/D/S ·
            quad TVS arrays `TVS_ARRAY_PINS`. `pins` + `nc` is the part's whole
            pin list, and every `nc` quotes the datasheet line that allows it.
            U401's IO43 / IO44 are the pads its datasheet labels TXD0 / RXD0.
  NETS      a series element splits a net: `*_WIRE` is the harness side,
            `*_GATE` the FET gate node, `*_IN` the device side of a series
            resistor, `*_MID` the join of a series pair, `*_RAW` a sense node
            ahead of its series resistor.
  DOMAIN    the voltage CLASS of the node. `v_max` is the rating ACROSS a part,
            so a 25 V capacitor between two 84 V-class nodes can be correct.
  INTERFACE names the lowest crossing (HV-LINK < PWR-UP < STACK) when a net
            crosses more than one.
  HEIGHTS   `height_confirmed=True` only where `source` cites the manufacturer
            PDF and the page the figure was read from.
  CONNECTOR pin numbers are a generator-side index. For the pods the binding
            key is wire colour + gauge, never the cavity number.
"""
from dataclasses import replace

from .model import Board, ConnPin, Connector, Design, Net, Part

#: The four boards, bottom to top: voltage falls with height (BD-1, BD-2).
BOARDS: tuple[Board, ...] = ("HVIN", "CONV", "DRV", "BRAIN")

#: Pin names of both quad TVS arrays (SC-74 / SOT457, identical pinout).
#: Letter = function, digit = pad number: pads 1/3/4/6 cathodes, 2/5 anodes.
TVS_ARRAY_PINS = ("K1", "A2", "K3", "K4", "A5", "K6")

# ── manufacturer documents cited below (local copies are never committed) ────
_DS_WROOM = "Espressif ESP32-S3-WROOM-1/1U datasheet v1.8 (esp32s3_wroom1.pdf)"
_DS_HDG = "Espressif ESP32-S3 Hardware Design Guidelines (esp32s3_hdg.pdf)"
_DS_TPS = "TI SLVSCV8E (tps4h160.pdf)"
_DS_MCP = "Microchip DS20001952D (mcp23017.pdf)"
_DS_HVD = "TI SLOS346O (sn65hvd230.pdf)"
_DS_TLV = "TI SLVSE84D (mine_tlv767.pdf)"
_DS_TDK = "TDK-Lambda CN50/100/150B110 instruction manual (tdk_cn50-150b110_apl.pdf)"
_DS_TDK_CAT = "TDK-Lambda CN-B110 datasheet (tdk_cn-b_e.pdf)"
_DS_CINCON = "Cincon EC7BW-110 datasheet V15 (cincon_Datasheet-EC7BW-110-series.pdf)"
_DS_WE = "Würth 7448022010 datasheet rev 002.000 (we7448022010.pdf)"
_DS_IXYS = "IXYS DS99913D (01/13), IXTA/IXTP26P20P (ixys_ds99913d.pdf)"
_DS_BSS127 = "Infineon BSS127 rev 2.1 (bss127.pdf)"
_DS_SMS = "onsemi SMS05T1/D rev 10 (tvs_onsemi_sms05t1-d.pdf)"
_DS_SMCJ = "Littelfuse SMCJ series datasheet (littelfuse_smcj_series_2025_wayback.pdf)"
_DS_VY2 = "Vishay doc 28535 (vishay_vy2_series_doc28535.pdf)"
_DS_KXJ = "Chemi-Con KXJ series (kxj.pdf)"
_DS_1N4007 = "Vishay 1N4001-1N4007 (1n4007.pdf)"
_DS_1N4148 = "Vishay 1N4148 (1n4148.pdf)"
_DS_SPT = "Schurter SPT 5x20 (spt.pdf)"
_DS_KX381 = ("Kangnex WJ15EDGRM-3.81 and WJ15EDGKM-3.81 drawings rev A "
             "(kangnex_15EDGRM-3.81.pdf, kangnex_15EDGKM-3.81.pdf)")
_DS_KX508 = ("Kangnex WJ2EDGRM-5.08 and WJ2EDGKM-5.08 drawings rev A "
             "(kangnex_2EDGRM-5.08.pdf, kangnex_2EDGKM-5.08.pdf)")
_BRK = "brake-circuit.md"

# ── generic chip packages: (footprint w × l, height). Heights are envelopes
# ── for the size class, not read from any one manufacturer: unconfirmed.
_R_PKG = {"0603": ((1.6, 0.8), 0.45), "0805": ((2.0, 1.25), 0.6), "1206": ((3.2, 1.6), 0.6)}
_C_PKG = {"0805": ((2.0, 1.25), 1.25), "1206": ((3.2, 1.6), 1.8)}

# ── The LCSC parts JLC places for parts bought by value ──────────────────────
# Chosen with ~/tools/lcsc-search, JLC Basic first (owner, 2026-09-18). A
# candidate counts only when its PARAMETERS meet the need: value, package,
# 1 % tolerance, and a WORKING voltage (never the overload figure) above the
# worst net it touches. The rating is the chosen part's, and it IS the part's
# v_max: `rules.voltage_ratings` checks it against the circuit. A value with
# no entry has no rating, and VR-RATED fails the design until one is chosen.
#   (value, package) -> (LCSC, maker part, working V, JLC class)
_R_LCSC = {
    ("100R", "0805"): ("C17408", "UNI-ROYAL 0805W8F1000T5E", 150.0, "Basic"),
    ("120R", "0805"): ("C17437", "UNI-ROYAL 0805W8F1200T5E", 150.0, "Basic"),
    ("1k", "0805"): ("C17513", "UNI-ROYAL 0805W8F1001T5E", 150.0, "Basic"),
    ("1k00 1%", "0805"): ("C17513", "UNI-ROYAL 0805W8F1001T5E", 150.0, "Basic"),
    ("2k0 1%", "0805"): ("C17604", "UNI-ROYAL 0805W8F2001T5E", 150.0, "Basic"),
    ("2k2", "0805"): ("C17520", "UNI-ROYAL 0805W8F2201T5E", 150.0, "Basic"),
    ("4k7", "0805"): ("C17673", "UNI-ROYAL 0805W8F4701T5E", 150.0, "Basic"),
    ("5k1", "0805"): ("C27834", "UNI-ROYAL 0805W8F5101T5E", 150.0, "Basic"),
    ("10k", "0805"): ("C17414", "UNI-ROYAL 0805W8F1002T5E", 150.0, "Basic"),
    ("20k", "0805"): ("C4328", "UNI-ROYAL 0805W8F2002T5E", 150.0, "Basic"),
    ("27k", "0805"): ("C17593", "UNI-ROYAL 0805W8F2702T5E", 150.0, "Basic"),
    ("47k", "0805"): ("C17713", "UNI-ROYAL 0805W8F4702T5E", 150.0, "Basic"),
    ("100k", "0805"): ("C149504", "UNI-ROYAL 0805W8F1003T5E", 150.0, "Basic"),
    ("180k", "0805"): ("C17501", "UNI-ROYAL 0805W8F1803T5E", 150.0, "preferred Extended"),
    ("240k", "0603"): ("C4197", "UNI-ROYAL 0603WAF2403T5E", 75.0, "preferred Extended"),
    # The 84 V string: 1206, 200 V. No Basic part exists at these values.
    ("165k", "1206"): ("C2999515", "FOJAN FRC1206F1653TS", 200.0, "Extended"),
    ("270k", "1206"): ("C17940", "UNI-ROYAL 1206W4F2703T5E", 200.0, "Extended"),
    ("499k", "1206"): ("C55020396", "FOJAN FRQ1206F4993TS", 200.0, "Extended"),
}
#   (value, needed V, package) -> (LCSC, maker part, rated V, JLC class). The
#   rated V can exceed the need: a better-rated Basic part beats an exact-rated
#   Extended one.
_C_LCSC = {
    ("100nF", 50.0, "0805"): ("C49678", "YAGEO CC0805KRX7R9BB104", 50.0, "Basic"),
    ("1uF", 16.0, "0805"): ("C28323", "Samsung CL21B105KBFNNNE, X7R", 50.0, "Basic"),
    ("10uF", 16.0, "1206"): ("C13585", "Samsung CL31A106KBHNNNE, X5R", 50.0, "Basic"),
    ("10uF", 25.0, "1206"): ("C13585", "Samsung CL31A106KBHNNNE, X5R", 50.0, "Basic"),
    ("2.2uF", 25.0, "1206"): ("C50254", "Samsung CL31B225KBHNNNE, X7R", 50.0, "Basic"),
    ("4.7uF 50V X7R", 50.0, "1206"): ("C29823", "FH 1206B475K500NT, X7R", 50.0, "Basic"),
    ("22nF", 250.0, "1206"): ("C3862155", "Murata GCM31C5C2E223JX03L, C0G", 250.0, "Extended"),
}


def _lcsc_note(lcsc: str, maker: str, volts: float, cls: str) -> str:
    return f" LCSC {lcsc}: {maker}, {volts:g} V working, JLC {cls}."


def _r(refdes: str, board: Board, value: str, source: str,
       pkg: str = "0805", dnp: bool = False) -> Part:
    """A chip resistor, bought by value; its part and rating come from _R_LCSC."""
    fp, h = _R_PKG[pkg]
    lcsc, maker, volts, cls = _R_LCSC.get((value, pkg), ("", "", None, ""))
    return Part(refdes, f"R-{value}", pkg, board, "R", ("1", "2"), h,
                footprint_mm=fp, value=value, dnp=dnp, v_max=volts,
                lcsc=lcsc, assembly="jlc" if lcsc else "",
                source=source + (_lcsc_note(lcsc, maker, volts, cls) if lcsc else ""))


def _c(refdes: str, board: Board, value: str, v_max: float, source: str,
       pkg: str = "0805") -> Part:
    """A ceramic chip capacitor, bought by value. `v_max` is the voltage it
    must be rated for; the chosen part's rating (from _C_LCSC) replaces it."""
    fp, h = _C_PKG[pkg]
    lcsc, maker, volts, cls = _C_LCSC.get((value, v_max, pkg), ("", "", v_max, ""))
    return Part(refdes, f"C-{value}", pkg, board, "C", ("1", "2"), h,
                footprint_mm=fp, v_max=volts, lcsc=lcsc,
                assembly="jlc" if lcsc else "",
                value=f"{value} {volts:g}V",
                source=source + (_lcsc_note(lcsc, maker, volts, cls) if lcsc else ""))


def _sot23(refdes: str, mpn: str, board: Board, kind: str, v_max: float,
           source: str, height: float = 1.25, confirmed: bool = False) -> Part:
    """A three-lead SOT-23 FET. 1.25 mm is the generic SOT-23 envelope."""
    return Part(refdes, mpn, "SOT-23", board, kind, ("G", "D", "S"), height,
                height_confirmed=confirmed, footprint_mm=(2.9, 2.6),
                v_max=v_max, source=source)


def _1n4148(refdes: str, name: str, role: str) -> Part:
    """One of the six D23 steering diodes, all on DRV."""
    return Part(refdes, "1N4148W", "SOD-123", "DRV", "D", ("A", "K"), 1.35,
                footprint_mm=(3.7, 1.6), v_max=75.0,
                source=f"{_BRK} §2/§3 '{name}' — {role}. Cathode on the lever "
                       f"node. SILICON, never Schottky: a Schottky's hot "
                       f"reverse leakage reaches the 3.3 V inputs. V_R 75 V: "
                       f"{_DS_1N4148} p.1. BOM G1. 1N4148W: the SOD-123 1N4148, same "
                       f"75 V / 150 mA die. ⬜ SOD-123 envelope, not read off a drawing")


def _tvs15(refdes: str, board: Board, where: str, dnp: bool = False) -> Part:
    """onsemi SMS15T1G, the 15 V quad array for every 12 V-class wire."""
    return Part(refdes, "SMS15T1G", "SC-74", board, "TVS", TVS_ARRAY_PINS, 1.10,
                height_confirmed=True, footprint_mm=(3.1, 3.0), v_max=15.0,
                dnp=dnp, value="V_RWM 15 V · 24.0 V @ 5 A · 29.0 V @ 12 A",
                source=f"{where}. {_DS_SMS}: p.1 pads 1/3/4/6 cathode, 2/5 "
                       f"anode; p.2 V_RWM 15 V, V_BR 16.7-18.5 V, clamp under "
                       f"the AO3400A's 30 V; p.4 SC-74 A max 1.10 mm. Spare "
                       f"cathodes tie to GND. BOM C4")


def _tvs18(refdes: str, board: Board, where: str) -> Part:
    """SMF18A, the single-line clamp for a line that sits at V12 while its
    channel is on (or its low-side switch is off).  Its breakdown starts at
    20.0 V, clear of TDK's 15.0-17.4 V over-voltage window: a 15 V part breaks
    down at 16.7 V INSIDE that window and would carry a channel's whole
    current-limit current until it failed short.  29.2 V clamp: under the
    AO3400A's 30 V and the TPS4H160B's 40 V."""
    return Part(refdes, "SMF18A", "SOD-123FL", board, "TVS", ("A", "K"), 1.1,
                footprint_mm=(3.9, 1.9), v_max=18.0,
                value="V_RWM 18 V · V_BR 20.0-22.1 V · V_C 29.2 V",
                source=f"{where}. SMF18A family table: V_RWM 18 V, V_BR 20.0-"
                       f"22.1 V, V_C 29.2 V at 6.8 A, 200 W 10/1000 µs. ⬜ SOD-123FL "
                       f"envelope, not read off a drawing")


def _tvs5(refdes: str, board: Board, where: str) -> Part:
    """onsemi SMS05T1G, the 5 V quad array for lines that stay <= 5 V."""
    return Part(refdes, "SMS05T1G", "SC-74", board, "TVS",
                TVS_ARRAY_PINS, 1.10, height_confirmed=True,
                footprint_mm=(3.1, 3.0), v_max=5.0,
                value="V_RWM 5 V · V_BR 6.0 V min · 9.8 V @ 5 A",
                source=f"{where}. {_DS_SMS}: the SMS05/SMS15 family sheet -- "
                       f"p.1 pads 1/3/4/6 cathode, 2/5 anode, the SMS15T1G's "
                       f"own pinout; p.4 SC-74 A max 1.10 mm. I_R up to 20 uA "
                       f"and ~300 pF per line: harmless on the pod inputs, "
                       f"within the CC spec, ~0.2 V on RUN's 10 k pull-up, too "
                       f"heavy for CAN (J405 is parked). Replaces the Nexperia "
                       f"PESD5V0S4UD (BOM C2), which LCSC has none of. Spare "
                       f"cathodes tie to GND")


# ════════════════════════════════════════════════════════════════════════════
# PARTS — HVIN (L1): 84 V entry, protection, the D13 module power switch.
# ════════════════════════════════════════════════════════════════════════════
_HVIN_PARTS = (
    Part("D101", "SMCJ90A", "DO-214AB (SMC)", "HVIN", "TVS", ("A", "K"), 2.62,
         height_confirmed=True, footprint_mm=(8.13, 6.22), v_max=90.0,
         value="V_R 90 V · V_BR 100-111 V · 146 V @ 10.3 A",
         source=f"B+ to GND at J101. plan §3.2.1, BOM E12 — never SMBJ90A, "
                f"SMBJ100A or 5KP90A. {_DS_SMCJ} p.5: DO-214AB D max 2.62 mm"),
    Part("D104", "SMCJ90A", "DO-214AB (SMC)", "HVIN", "TVS", ("A", "K"), 2.62,
         height_confirmed=True, footprint_mm=(8.13, 6.22), v_max=90.0,
         value="V_R 90 V · V_BR 100-111 V · 146 V @ 10.3 A",
         source=f"KSW to GND at J102: the key-switch wire is an 84 V conductor "
                f"leaving the box. BOM E12. {_DS_SMCJ} p.5: D max 2.62 mm"),
    Part("Q101", "IXTA26P20P-TRL", "TO-263AA (D2PAK)", "HVIN", "PFET",
         ("G", "D", "S"), 4.83, height_confirmed=True,
         footprint_mm=(10.41, 15.88), v_max=200.0,
         value="P-ch -200 V, V_GS ±20 V, V_GS(th) -2…-4 V",
         source=f"'D13', the module's high-side power switch: S = HV_BPLUS, "
                f"D = HV_SW. plan §3.2.5, BOM E13; chosen on SOA — 114 W at a "
                f"~50 ms ramp clears the 70 °C DC line (≈191 W at 84 V, "
                f"DS99913D Fig. 14). {_DS_IXYS}: one sheet for the IXTA "
                f"(TO-263) and IXTP (TO-220) -- one die, one SOA, so "
                f"tools/soft_start.py holds for either. p.3 TO-263 outline: A "
                f"max 4.83 mm, E 10.41, L 15.88. The IXTA because JLC can "
                f"reflow it (LCSC C3291074, the IXTP has none in stock); "
                f"fallback: the IXTP26P20P, hand-soldered. ⚠️ The tab is the "
                f"drain (HV_SW, 84 V): board copper at 84 V -- keep "
                f"clearance to every other net, and no metal under it"),
    _r("R110", "HVIN", "100k",
       "Q101 gate to SOURCE — the D14 bias-OFF: V_GS = 0 with the key off. "
       "With R101A/B (540 kΩ) it sets V_GS = -13.1 V at 84 V, -9.4 V at 60 V, "
       "-6.7 V at 43 V. BOM D9"),
    Part("D102", "BZT52B15", "SOD-123", "HVIN", "ZENER",
         ("A", "K"), 1.35, footprint_mm=(3.7, 1.6), v_max=15.0, value="15V",
         source="Q101 gate clamp inside the ±20 V V_GS rating: anode = gate, "
                "cathode = source. Never conducts in normal running (-13.1 V). "
                "BOM E13 '+ zener'. ⬜ MPN and package unchosen"),
    Part("C105", "CGA9N1C0G2J683JT0Y0S", "2220 C0G", "HVIN",
         "C", ("1", "2"), 2.3, footprint_mm=(5.7, 5.0), v_max=630.0,
         value="68nF C0G 630V",
         source="Q101 gate to DRAIN: the Miller cap that sets the output slew, "
                "≈55 ms at 84 V: I = (84 - V_pl)/540 k - V_pl/100 k ≈ 0.105 mA at a "
                "4.3 V plateau, t = 84 V × 68 nF / I (plan §3.2.5). It holds "
                "the full pack with the switch off and 146 V at D101's clamp, "
                "hence ≥250 V; C0G or film because X7R loses half its value at "
                "that bias, exactly where SOA stress peaks. ⬜ part unchosen"),
    _c("C107", "HVIN", "4.7uF 50V X7R", 50.0,
       "Q101 gate to SOURCE. Divides the dV/dt that C105 couples into the gate "
       "when the XT90-S is plugged in with the key OFF: 84 V × 68n/(68n+4.7µ) "
       "≈ 1.2 V nominal, under V_GS(th) min 2.0 V. ⚠️ The margin is thin at the "
       "corners (−1.64 … −1.98 V across tolerance, temperature and OVP), and a "
       "Y5V/25 V part loses most of its capacitance under bias and cold -- so "
       "X7R, 50 V: it sees ≤15 V (D102) and keeps its value", pkg="1206"),
    _r("R101A", "HVIN", "270k",
       "Upper half of the 540 kΩ gate pull-down string (Q101 gate → Q105). "
       "A series pair for voltage rating: ~35 V each running, 73 V each at "
       "D101's 146 V clamp", pkg="1206"),
    _r("R101B", "HVIN", "270k",
       "Lower half of the 540 kΩ gate pull-down string, into Q105's drain",
       pkg="1206"),
    _sot23("Q105", "BSS127", "HVIN", "NFET", 600.0,
           f"The level shifter that turns Q101 ON: D = D13_PD, S = GND, "
           f"G = D13_EN. Key on ⇒ D13_EN ≈ 7.6 V ⇒ Q105 pulls the 540 kΩ "
           f"string to GND. Key off ⇒ D13_EN = 0 ⇒ no DC path off Q101's gate "
           f"and zero quiescent drain. {_DS_BSS127}: p.1 600 V, ENHANCEMENT "
           f"mode, logic level (V_GS(th) 1.4-2.6 V); p.8 SOT-23 1.1 mm max",
           height=1.1, confirmed=True),
    _r("R112A", "HVIN", "499k",
       "Upper half of the 1 MΩ feed from KSW to Q105's gate. A series pair for "
       "voltage rating", pkg="1206"),
    _r("R112B", "HVIN", "499k",
       "Lower half of the 1 MΩ feed from KSW to Q105's gate. With R113: "
       "84 V → 7.6 V, 60 V → 5.5 V, 43 V → 3.9 V, all over V_GS(th) 2.6 V max",
       pkg="1206"),
    _r("R113", "HVIN", "100k",
       "Q105 gate to GND — the D14 bias-OFF: key off or J102 unplugged ⇒ "
       "Q105 off ⇒ Q101 off"),
    Part("D106", "BZT52B10", "SOD-123", "HVIN", "ZENER",
         ("A", "K"), 1.35, footprint_mm=(3.7, 1.6), v_max=10.0, value="10V",
         source="Q105 gate clamp, D13_EN to GND, inside the BSS127's ±20 V "
                "V_GS. The node runs at 7.6 V, so it conducts only on a "
                "transient. ⬜ MPN and package unchosen"),
    _c("C108", "HVIN", "100nF", 50.0,
       "D13_EN to GND: key-contact bounce filter, τ ≈ 9 ms with R112A/B ‖ R113"),
    _r("R107", "HVIN", "165k",
       "IN-12 divider top, upper half, fed from KSW. 330 kΩ / 10 kΩ gives "
       "84 V → 2.47 V (plan §3.1.3); 2 × 165 k because plan §4 class B wants a "
       "series pair for voltage rating (40.8 V and 10 mW each). BOM E14",
       pkg="1206"),
    _r("R108", "HVIN", "165k",
       "IN-12 divider top, lower half — series partner of R107", pkg="1206"),
    _r("R109", "HVIN", "10k", "IN-12 divider bottom. 84 V → 2.47 V. BOM E14"),
    _c("C109", "HVIN", "100nF", 50.0,
       f"At the KEY_SENSE node. {_DS_HDG} p.21: 'add a 0.1 μF filter "
       f"capacitor between ESP pins and ground when using the ADC function'"),
    Part("L101", "7448022010", "THT common-mode choke, vertical", "HVIN",
         "CMCHOKE", ("1", "2", "3", "4"), 22.0, height_confirmed=True,
         footprint_mm=(18.0, 14.0), value="10 mH · 2 A @ 70 °C · 300 V AC",
         source=f"DC-DC #1's input filter, ahead of its bulk cap. FOUR "
                f"terminals, windings 1-4 and 2-3: HV_SW → 1→4 → HV_C1_P, "
                f"HV_C1_N → 3→2 → GND, so the DC currents cancel in the core. "
                f"{_DS_WE} p.1: 22,0 max tall, 18,0 max wide, 14,0 max deep. "
                f"BOM E7"),
    Part("L102", "7448022010", "THT common-mode choke, vertical", "HVIN",
         "CMCHOKE", ("1", "2", "3", "4"), 22.0, height_confirmed=True,
         footprint_mm=(18.0, 14.0), value="10 mH · 2 A @ 70 °C · 300 V AC",
         source=f"DC-DC #2's input filter: HV_SW → 1→4 → HV_C2_P, "
                f"HV_C2_N → 3→2 → GND. {_DS_WE} p.1: 22,0 max tall. BOM E7"),
)

# ════════════════════════════════════════════════════════════════════════════
# PARTS — CONV (L2): both converters. Each converter's −Vin is its own net and
# reaches GND only through its choke winding; −Vout IS GND (isolated bricks).
# ════════════════════════════════════════════════════════════════════════════
_CONV_PARTS = (
    Part("U201", "CN150B110-12/CO", "quarter brick 58.3 × 37.2 × 12.7 mm",
         "CONV", "CONVERTER",
         ("-Vin", "CNT", "+Vin", "-V", "-S", "+S", "+V", "BASEPLATE"), 12.7,
         height_confirmed=True, footprint_mm=(58.3, 37.2), nc=("TRM",),
         v_max=160.0, value="43-160 V → 12 V / 12.5 A, isolated",
         source=f"DC-DC #1, the load rail. BOM E1. {_DS_TDK} p.5 pins: 1 -Vin, "
                f"2 CNT, 3 +Vin, 4 -V, 5 -S, 6 TRM, 7 +S, 8 +V; 'Base-plate can "
                f"be connected to FG by M3 threaded holes' = pin BASEPLATE. "
                f"p.18 CNT is negative logic, 'H Level or Open → OFF'; 'When "
                f"ON/OFF control function is not used, CNT terminal should be "
                f"shorted to -Vin terminal'. p.17 'short +S terminal to +V "
                f"terminal and -S terminal to -V terminal'. nc TRM: p.6 "
                f"Fig.6-1 draws it open and p.10 §7-2 adjusts only 'by "
                f"external resistor'. {_DS_TDK_CAT} p.3: 58.3 × 37.2 × 12.7 mm. "
                f"⚠️ 160 V is a hard ceiling, transients included"),
    Part("U202", "EC7BW-110S05", "2 × 1 in. module", "CONV", "CONVERTER",
         ("+Vin", "-Vin", "+Vout", "-Vout"), 10.7, height_confirmed=True,
         footprint_mm=(50.8, 25.4), nc=("Trim", "Remote"), v_max=160.0,
         value="43-160 V → 5 V / 4 A, 3 kV isolation",
         source=f"DC-DC #2, the logic rail. BOM E2. {_DS_CINCON} p.7 pins: "
                f"1 +V Input, 2 -V Input, 3 +V Output, 4 Trim, 5 -V Output, "
                f"6 Remote On/Off; 50.8 × 25.4 × 10.2 mm ±0.5, booked at the "
                f"10.7 mm maximum. nc Remote: p.3 positive logic, 'Pin open=On'. "
                f"nc Trim: p.2 'Output Voltage Trim Range' ±10 % is an "
                f"optional external-resistor adjustment; open = nominal 5 V"),
    Part("C201", "EKXJ221ELL221MM25S", "radial can 18 × 25 mm, lying down",
         "CONV", "C", ("+", "-"), 18.5, height_confirmed=True,
         footprint_mm=(18.5, 26.5), v_max=220.0, side="bottom",
         value="220uF 220V",
         source=f"'C1': TDK's input bulk across HV_C1_P / HV_C1_N at U201's "
                f"terminals ({_DS_TDK} p.7: ≥100 µF, KXJ class). UNDERSIDE, "
                f"lying down and bonded (BD-14). {_DS_KXJ} p.1: φD' = φD + 0.5 "
                f"max = 18.5 mm, L' = L + 1.5 max = 26.5 mm. BOM E8"),
    Part("C202", "EKXJ221ELL221MM25S", "radial can 18 × 25 mm, lying down",
         "CONV", "C", ("+", "-"), 18.5, height_confirmed=True,
         footprint_mm=(18.5, 26.5), v_max=220.0, side="bottom",
         value="220uF 220V",
         source=f"'C2': hold-up across U202's ±Vin, BEHIND D201 and F201. "
                f"⚠️ Not interchangeable with C1: on the common node ride-out "
                f"collapses from ~237 ms to ~20 ms (plan §3.2.2). UNDERSIDE "
                f"(BD-14). {_DS_KXJ} p.1: 18.5 mm. BOM E8"),
    Part("C203", "VY2472M49Y5US6", "radial disc, lying FLAT", "CONV", "C",
         ("1", "2"), 5.0, height_confirmed=True, footprint_mm=(12.5, 16.5),
         v_max=1000.0, value="4700pF Y2 1000VDC",
         source=f"HV_C1_P to BASEPLATE at U201's terminals ({_DS_TDK} p.8 "
                f"C2/C3: 4700 pF). {_DS_VY2} p.2: D max 12.5, T max 5.0 mm — "
                f"FLAT it is 5.0 mm where upright it is 15.5-16.5; p.1 "
                f"1000 VDC, IEC 60384-14 Y2. BOM E9"),
    Part("C204", "VY2472M49Y5US6", "radial disc, lying FLAT", "CONV", "C",
         ("1", "2"), 5.0, height_confirmed=True, footprint_mm=(12.5, 16.5),
         v_max=1000.0, value="4700pF Y2 1000VDC",
         source=f"HV_C1_N to BASEPLATE. {_DS_VY2} p.2: T max 5.0 mm. BOM E9"),
    Part("C205", "VY2472M49Y5US6", "radial disc, lying FLAT", "CONV", "C",
         ("1", "2"), 5.0, height_confirmed=True, footprint_mm=(12.5, 16.5),
         v_max=1000.0, value="4700pF Y2 1000VDC",
         source=f"U202 +Vin (HV_C2_HOLD) to BASEPLATE. {_DS_VY2} p.2: T max "
                f"5.0 mm. BOM E9"),
    Part("C206", "VY2472M49Y5US6", "radial disc, lying FLAT", "CONV", "C",
         ("1", "2"), 5.0, height_confirmed=True, footprint_mm=(12.5, 16.5),
         v_max=1000.0, value="4700pF Y2 1000VDC",
         source=f"HV_C2_N to BASEPLATE. {_DS_VY2} p.2: T max 5.0 mm. BOM E9"),
    Part("C207", "PA25V680M8x12", "radial polymer 8 × 12.5 mm, lying down",
         "CONV", "C", ("+", "-"), 8.5, footprint_mm=(8.5, 15.0), v_max=25.0,
         value="680uF 25V polymer, 20 mΩ",
         source=f"U201 +V to -V. {_DS_TDK} p.9 Table 6-1: '12,15V: 25V 680μF "
                f"(Solid Cap.)', 'For stable operation' (Chemi-Con PSG class). "
                f"JIERR PA25V680M8x12: solid polymer, 20 mΩ, 4.1 A ripple, "
                f"-55…105 °C. ⬜ 8 mm can lying down is ~8.5 mm, not read "
                f"off a drawing; under the 12.7 mm brick either way"),
    _c("C208", "CONV", "2.2uF", 25.0,
       f"U201 +V to -V. {_DS_TDK} p.8 C6: 2.2 µF ceramic against output spike "
       f"noise", pkg="1206"),
    _c("C209", "CONV", "22nF", 250.0,
       f"U201 +V to BASEPLATE, close to the terminal. {_DS_TDK} p.8 C4/C5: "
       f"0.022 µF. 250 V so it survives BASEPLATE lifted to the 84 V rail by a "
       f"shorted Y2 with R211 open", pkg="1206"),
    _c("C210", "CONV", "22nF", 250.0,
       f"U201 -V to BASEPLATE. {_DS_TDK} p.8 C4/C5: 0.022 µF. Rated as C209",
       pkg="1206"),
    _c("C211", "CONV", "10uF", 16.0, "U202 output bulk, V5 to GND", pkg="1206"),
    _c("C212", "CONV", "100nF", 50.0, "U202 output HF decoupling, V5 to GND"),
    Part("D201", "M7", "DO-214AC (SMA)", "CONV", "D", ("A", "K"), 2.44,
         footprint_mm=(5.3, 2.9), v_max=1000.0,
         source=f"Hold-up blocking diode, HV_C2_P → HV_C2_HOLD_IN. Plain "
                f"silicon (plan §3.2.6): the SMA 1N4007, 1000 V / 1 A, 30 A "
                f"surge; it carries <= 0.62 A (the whole module at 60 V) "
                f"behind F201. The DO-41 1N4007 (BOM E10) is the breadboard's. "
                f"⬜ SMA envelope 2.44 mm, not read off a drawing"),
    Part("FH201A", "01110501Z", "PCB fuse clip, 5 × 20", "CONV",
         "FUSECLIP", ("1",), 7.1, footprint_mm=(4.8, 3.8),
         source="F201's input-end clip. ⛔ Not the in-hand Schurter FAC "
                "0031.3803: that is a 47.5 mm VERTICAL holder. The DC "
                "interrupting duty is the fuse's, not the clip's. Littelfuse "
                "01110501Z (111 501): 5 mm clip with fuse stop, 10 A; catalogue "
                "body 7.1 mm tall, 4.8 × 3.8 mm, rows 17.8 mm apart for 5 × 20. "
                "⬜ seated height to confirm on a real part"),
    Part("FH201B", "01110501Z", "PCB fuse clip, 5 × 20", "CONV",
         "FUSECLIP", ("1",), 7.1, footprint_mm=(4.8, 3.8),
         source="F201's output-end clip, as FH201A"),
    Part("F201", "0001.2504", "5 × 20 ceramic, in clips FH201A/B", "CONV",
         "FUSE", ("1", "2"), 8.0, footprint_mm=(5.2, 20.0), v_max=300.0,
         value="1A T-lag 300VDC",
         source=f"DC-DC #2's input fuse (Cincon: 1 A time-delay). ⛔ Order by "
                f"part number: FST and SP have NO DC rating. {_DS_SPT} p.2: "
                f"ø 5.2 × 20 mm; 8.0 mm assumes a ≤2.8 mm clip seat. BOM E11"),
    Part("R211", "NET-TIE", "copper net-tie, ≥2 mm wide", "CONV", "R", ("1", "2"),
         0.04, footprint_mm=(4.0, 2.0), value="0R",
         source="Single-point tie BASEPLATE → GND, so a shorted Y2 blows the "
                "KLKD002 instead of floating a plate at 84 V. COPPER, not a "
                "chip jumper: the prospective current is ~200 A, and a 1206 "
                "0 Ω would race the 2 A fuse and could open first -- leaving "
                "the plate floating at 84 V, the exact fault this tie prevents"),
)

# ════════════════════════════════════════════════════════════════════════════
# PARTS — DRV (L3): 12 V drivers, the complete D23 brake/kill hardware, and the
# parked display block. ⚠️ 40 V parts: the 12 V rail only, never the 84 V node.
#   U301: IN1 spare · IN2 HL_LOW · IN3 HL_HIGH · IN4 HL_DRL
#   U302: IN1 TAIL_RUN · IN2 TURN_L · IN3 TURN_R · IN4 spare
# ════════════════════════════════════════════════════════════════════════════
_TPS_PINS = ("GND", "IN1", "IN2", "IN3", "IN4", "SEH", "SEL", "FAULT", "CS",
             "CL", "THER", "DIAG_EN", "OUT1", "OUT2", "OUT3", "OUT4", "VS",
             "PAD")


def _tps4h160(refdes: str, role: str) -> Part:
    return Part(refdes, "TPS4H160BQPWPRQ1", "28-HTSSOP PowerPAD, 0.65 mm",
                "DRV", "IC", _TPS_PINS, 1.2, height_confirmed=True,
                footprint_mm=(9.8, 6.6), nc=("NC",), v_max=40.0,
                value="4-ch high-side, version B (CS + SEH/SEL + FAULT)",
                source=f"{role}. BOM D1. {_DS_TPS} p.4-5 Table 5-1, version B: "
                       f"GND 1,12 · IN1-4 3-6 · SEH 7 · SEL 8 · FAULT 9 · CS 10 "
                       f"· CL 11 · THER 13 · DIAG_EN 14 · OUT4 15,16 · OUT3 "
                       f"17,18 · VS 20-23 · OUT2 25,26 · OUT1 27,28 · thermal "
                       f"pad. nc NC (pads 2, 19, 24): 'No internal connection'. "
                       f"PAD lands on GND: p.31 'tie the thermal pad directly "
                       f"to the board GND copper'. THER lands on GND: p.24 "
                       f"'When the THER pin is low, thermal shutdown operates "
                       f"in the auto-retry mode'. p.38: 1.2 mm max, 9.8 × 6.6")


def _tps_series(refdes: str, signal: str) -> Part:
    return _r(refdes, "DRV", "4k7",
              f"Series protection in {signal}, MCU side of the TPS4H160B pin. "
              f"{_DS_TPS} p.26: 'TI recommends serial resistors to protect the "
              f"microcontroller, for example, 4.7-kΩ when using a 3.3-V "
              f"microcontroller'; plan §6.2.2a's 3.15 V drive figure assumes it")


def _open_load_pullup(refdes: str, channel: str) -> Part:
    return _r(refdes, "DRV", "20k",
              f"{channel} OUT → V12, for OFF-state open-load detect. "
              f"{_DS_TPS} p.23: 'The recommended pullup resistance is 20 kΩ'. "
              f"BOM D2")


_DRV_PARTS = (
    _tps4h160("U301", "Headlight: LOW, HIGH, DRL. OUT1 is AUX12, the "
              "current-limited feed to horn +, fan + and buzzer +"),
    _tps4h160("U302", "Tail running + turn L/R. OUT4 is the STOP lamp, its IN4 "
              "driven by the hardware brake circuit and never by firmware"),
    _open_load_pullup("R301", "HL_LOW"),
    _open_load_pullup("R302", "HL_HIGH"),
    _open_load_pullup("R303", "HL_DRL"),
    _open_load_pullup("R304", "TAIL_RUN"),
    _open_load_pullup("R305", "TURN_L"),
    _open_load_pullup("R306", "TURN_R"),
    _open_load_pullup("R345", "TAIL_STOP"),
    _r("R346", "DRV", "10k",
       "AUX12 enable: U301 IN1 → V3P3. The channel is on whenever BRAIN's "
       "3.3 V is up and off when it is not; 3.3 V × 100-250k / (10k + 100-250k) "
       "= 3.0-3.2 V against V_IH 2 V. What it feeds is switched low-side "
       "(Q301-Q303), each gate biased OFF (D14), so no load runs at key-on. "
       "The channel is a FEED: it current-limits horn +, fan + and buzzer + at "
       "2 A, where raw V12 would put the 12.75-18.75 A brick into the harness "
       "and hiccup the rail the stop lamp shares"),
    _r("R347", "DRV", "27k",
       f"STOP_CMD → U302 IN4, the top of a 27k / 10k divider from Q1's drain. "
       f"{_DS_TPS} p.7: INx is 0-5 V recommended, 7 V absolute, V_IH 2 V, "
       f"100-250 kΩ pull-down. 12 V → 3.02-3.15 V; TDK's 17.4 V OVP → 4.4-4.6 V; "
       f"on above 7.9 V. D318 clamps a V12 transient (D315 lets 29.2 V through) "
       f"at 5.1 V. Also the pin's series resistor (p.26)"),
    _r("R348", "DRV", "10k", "STOP_CMD divider bottom, U302 IN4 → GND (with R347)"),
    Part("D318", "BZT52B5V1", "SOD-123", "DRV", "ZENER", ("A", "K"), 1.35,
         footprint_mm=(3.7, 1.6), v_max=5.1, value="5.1 V B grade, 5.0-5.2 V",
         source=f"U302 IN4 clamp: a V12 transient up to D315's 29.2 V puts "
                f"(29.2 - 5.1) / 27k = 0.9 mA through it and holds IN4 under "
                f"{_DS_TPS}'s 7 V absolute. At TDK's 17.4 V OVP IN4 sits at "
                f"4.6 V, below the 5.0 V knee. ⬜ SOD-123 envelope"),
    _r("R319", "DRV", "1k00 1%",
       f"U301 CL → GND: 0.8 V × 2500 / 1.00 kΩ = 2.0 A per channel, over the "
       f"0.71 A / 0.54 A loads. {_DS_TPS} p.29 eq. 10. This is the lamp-scale "
       f"limit D15 chose the part for"),
    _r("R320", "DRV", "2k0 1%",
       f"U302 CL → GND: 0.8 V × 2500 / 2.0 kΩ = 1.0 A per channel, over the "
       f"0.05-0.10 A loads. {_DS_TPS} p.29 eq. 10"),
    _r("R321", "DRV", "1k00 1%",
       f"U301 CS → GND, the sense resistor: I_OUT / 300 × 1.00 kΩ = 3.33 V/A, "
       f"so 0.71 A reads 2.37 V. {_DS_TPS} p.29 eq. 9; ≥300 Ω keeps the "
       f"15 mA fault current in range"),
    _r("R322", "DRV", "1k00 1%", f"U302 CS → GND, the sense resistor, as R321"),
    _r("R323", "DRV", "10k",
       f"Series from U301's CS node to CS1 -- the TOP of a 10 k / 10 k divider "
       f"with R339. In any fault the CS pin pulls up to V_CS(H) 4.5-6.5 V "
       f"({_DS_TPS} p.29); TI's 10 kΩ series advice is written for a 5 V MCU, "
       f"and alone it leaves ~3.8 V on a 3.3 V pin. Halved, a fault reads "
       f"2.25-3.25 V: above every real load, below VDD"),
    _r("R324", "DRV", "10k", "Series from U302's CS node to CS2, as R323 (with R340)"),
    _r("R343", "DRV", "100k",
       "ACC+ sense divider, top. The run/off kill's pull-up (R314) is fed from "
       "the throttle's ACC+; if that wire never arrives the kill cannot cut "
       "the motor and NOTHING shows it. This divider lets firmware see ACC+: "
       "5.1 V × 180/280 = 3.28 V at the expander pin (V_IH 2.64 V)"),
    _r("R344", "DRV", "180k", "ACC+ sense divider, bottom (with R343)"),
    _r("R341", "DRV", "1k",
       "IN-05 series resistor, between the D23 sense node and the wire to the "
       "MCU (plan §4 class A). Without it a negative surge on the lever wire "
       "runs D313 → D305 → straight into the S3's input clamp"),
    _r("R342", "DRV", "1k", "IN-06 series resistor, as R341"),
    _r("R339", "DRV", "10k",
       "CS1 to GND on the ADC side of R323: the bottom of the divider. Scale is "
       "1.67 V/A at the pin (0.71 A reads 1.19 V; the 0.05 A tail lamp 83 mV)"),
    _r("R340", "DRV", "10k", "CS2 to GND on the ADC side of R324, as R339"),
    _c("C301", "DRV", "100nF", 50.0,
       f"CS1 to GND on the ADC side of R323. {_DS_HDG} p.21: 0.1 µF at an ADC "
       f"input. With the 10 k / 10 k divider τ ≈ 0.55 ms: firmware waits ≥3 ms after moving SEH/SEL"),
    _c("C302", "DRV", "100nF", 50.0, "CS2 to GND on the ADC side of R324"),
    _c("C303", "DRV", "100nF", 50.0, "U301 VS decoupling, at the pins"),
    _c("C304", "DRV", "10uF", 25.0, "U301 VS bulk decoupling", pkg="1206"),
    _c("C305", "DRV", "100nF", 50.0, "U302 VS decoupling, at the pins"),
    _c("C306", "DRV", "10uF", 25.0, "U302 VS bulk decoupling", pkg="1206"),
    _tps_series("R327", "LGT_LOW → U301 IN2"),
    _tps_series("R328", "LGT_HIGH → U301 IN3"),
    _tps_series("R329", "LGT_DRL → U301 IN4"),
    _tps_series("R330", "LGT_TAIL → U302 IN1"),
    _tps_series("R331", "LGT_TURN_L → U302 IN2"),
    _tps_series("R332", "LGT_TURN_R → U302 IN3"),
    _tps_series("R333", "DIAG_EN, bussed to both devices"),
    _tps_series("R334", "SEL, bussed to both devices"),
    _tps_series("R335", "SEH, bussed to both devices"),
    # ── low-side channels (plan §6.2.3) ─────────────────────────────────────
    _sot23("Q301", "AO3400A", "DRV", "NFET", 30.0,
           "Horn low-side. 48 mΩ max at V_GS 2.5 V. BOM D3"),
    _sot23("Q302", "AO3400A", "DRV", "NFET", 30.0,
           "Fan low-side, LEDC PWM. BOM D3"),
    _sot23("Q303", "AO3400A", "DRV", "NFET", 30.0,
           "Buzzer low-side, LEDC PWM. BOM D3"),
    _r("R307", "DRV", "10k",
       "Horn gate pull-down. D14: every gate biases OFF, so a hung module "
       "drives no load (plan §3.1.2). BOM D9"),
    _r("R308", "DRV", "10k", "Fan gate pull-down (D14). BOM D9"),
    _r("R309", "DRV", "10k", "Buzzer gate pull-down (D14). BOM D9"),
    _r("R310", "DRV", "100R", "Horn gate series (plan §6.2.3). BOM D9"),
    _r("R311", "DRV", "100R", "Fan gate series. BOM D9"),
    _r("R312", "DRV", "100R", "Buzzer gate series. BOM D9"),
    Part("D307", "SS14", "DO-214AC (SMA)", "DRV", "D", ("A", "K"), 2.4,
         footprint_mm=(5.3, 2.8), v_max=40.0, value="1 A / 40 V Schottky",
         source="Fan flyback across J305.1-2: anode FAN_RTN, cathode AUX12, "
                "the fan's own + feed. "
                "Schottky is right here: BOM G1's leakage objection concerns "
                "3.3 V inputs, and this diode sits across a 12 V load. SMA "
                "outline assumed"),
    Part("D314", "SS14", "DO-214AC (SMA)", "DRV", "D", ("A", "K"), 2.4,
         footprint_mm=(5.3, 2.8), v_max=40.0, value="1 A / 40 V Schottky",
         source="Buzzer flyback across J305.3-4: anode BUZZ_RTN, cathode AUX12. "
                "The AO3400A has no avalanche rating and a magnetic buzzer is "
                "a coil; harmless if the buzzer is piezo. SMA outline assumed"),
    Part("D315", "SMBJ18A", "DO-214AA (SMB)", "DRV", "TVS", ("A", "K"), 2.5,
         footprint_mm=(5.6, 3.95), v_max=18.0,
         value="V_RWM 18 V · V_BR 20.0-22.1 V · V_C 29.2 V",
         source="The clamp on the V12 rail itself, at the TPS4H160B's VS. "
                "No raw V12 leaves the box: horn +, fan + and buzzer + ride "
                "AUX12, U301's current-limited channel. The 18 V grade, not "
                "15 V: TDK's over-voltage window is 15.0-17.4 V and a 15 V "
                "part breaks down at 16.70-18.50 V, INSIDE it -- so a converter "
                "fault would cook the clamp, which then fails short and takes "
                "the 12 V rail (and the brake lamp) with it. The 18 V grade "
                "starts at 20.00 V, clear of that window, and still clamps at "
                "29.2 V: under the AO3400A's 30 V and the TPS4H160B's 40 V. "
                "Littelfuse SMCJ/SMBJ series table (the two series share the "
                "V_R/V_BR/V_C grid). SMB outline assumed"),
    # ── D23: brake cutoff, brake lamp, run/off kill — all hardware, all here ─
    _1n4148("D301", "D1L", "left lever → BL"),
    _1n4148("D302", "D1R", "right lever → BL"),
    _1n4148("D303", "D2L", "left lever → Q1 gate"),
    _1n4148("D304", "D2R", "right lever → Q1 gate"),
    _1n4148("D305", "D3L", "left lever → IN-05"),
    _1n4148("D306", "D3R", "right lever → IN-06"),
    _sot23("Q304", "AO3407A", "DRV", "PFET", 30.0,
           f"'Q1', the HARDWARE stop-lamp command: S = V12, D = STOP_CMD, which "
           f"drives U302's IN4 through R347/R348. The lamp itself hangs on U302 "
           f"OUT4, so it gets a 1 A current limit, open-load detection and "
           f"FAULT2 -- with no firmware anywhere in the switching path: a "
           f"TPS4H160B channel follows its IN pin whatever DIAG_EN, SEL and "
           f"SEH do. P-ch, -30 V, ±20 V gate. {_BRK} §2/§3, BOM G2"),
    _r("R313", "DRV", "10k",
       f"'R1': Q1 gate pull-up to V12, and the levers' wetting current "
       f"(~1.2 mA). {_BRK} §3, BOM G3"),
    _sot23("Q305", "AO3400A", "DRV", "NFET", 30.0,
           f"'Q2', the run/off kill inverter: D = BL, S = GND. Node high "
           f"(toggle OFF, or the bar wire open) ⇒ BL held low ⇒ motor cut. "
           f"{_BRK} §2.1, BOM D3"),
    _r("R314", "DRV", "10k",
       f"'R4': pulls the RUN node up FROM ACC+ (the throttle's 5.1 V, in on "
       f"J309). On DRV so an open pod, STACK or BRAIN contact leaves the node "
       f"pulled up = OFF = motor cut: those opens fail SAFE. ⚠️ An open ACC+ "
       f"does NOT: with no pull-up the node never rises and the kill goes dead "
       f"silently -- which is what ACC_SENSE (R343/R344) exists to report. "
       f"{_BRK} §2.1, BOM G3"),
    _r("R315", "DRV", "100R", f"'R5': Q2 gate series. {_BRK} §2.1, BOM G6"),
    _r("R316", "DRV", "100k",
       f"'R6': Q2 gate to GND, the D14 bias-OFF. {_BRK} §2.1, BOM G6"),
    _r("R317", "DRV", "10k",
       f"'R3L': IN-05 pull-up to V3P3, which crosses STACK. 10 kΩ, not the "
       f"bar switches' 1 kΩ: R1 already wets the contact and 10 kΩ keeps the "
       f"low level ~0.55 V through a 1N4148. {_BRK} §3, BOM G3"),
    _r("R318", "DRV", "10k", f"'R3R': IN-06 pull-up to V3P3. {_BRK} §3, BOM G3"),
    _r("R336", "DRV", "100k",
       "BL → BL_SENSE: the 100 kΩ-isolated copy firmware reads. The real BL "
       "never leaves DRV, so a dead or absent BRAIN cannot load or open it"),
    # ── IN-15: 12 V rail sense (plan §4 class D) ────────────────────────────
    _r("R337", "DRV", "47k",
       "IN-15 divider top, from V12. 47 k / 10 k: 12 V → 2.11 V, and TDK's "
       "17.4 V over-voltage ceiling → 3.05 V, inside the 3.3 V pin. On DRV so "
       "12 V never crosses to BRAIN"),
    _r("R338", "DRV", "10k", "IN-15 divider bottom"),
    _c("C307", "DRV", "100nF", 50.0,
       f"At the V12_SENSE node (plan §4 class D). {_DS_HDG} p.21"),
    # ── protection: one array per harness connector, same board ─────────────
    _tvs18("D308", "DRV", "At J301: HL_LOW"),
    _tvs18("D309", "DRV", "At J301: HL_HIGH"),
    _tvs18("D310", "DRV", "At J301: HL_DRL"),
    _tvs18("D311", "DRV", "At J304: HORN_N"),
    _tvs18("D312", "DRV", "At J305: FAN_RTN"),
    _tvs18("D319", "DRV", "At J305: BUZZ_RTN"),
    _tvs18("D320", "DRV", "At J302: TAIL_RUN"),
    _tvs18("D321", "DRV", "At J302: rear TURN_L"),
    _tvs18("D322", "DRV", "At J302: rear TURN_R"),
    _tvs18("D323", "DRV", "At J302: TAIL_STOP"),
    _tvs18("D324", "DRV", "At J303: front TURN_L"),
    _tvs18("D325", "DRV", "At J303: front TURN_R"),
    _tvs18("D326", "DRV", "At J304/J305: AUX12, the horn/fan/buzzer + feed"),
    _tvs15("D313", "DRV",
           f"At J306: LEVER_L, LEVER_R. The lever nodes idle at ~11.4 V "
           f"({_BRK} §3), so a 5 V array here would hold the stop lamp on"),
    _tvs15("D316", "DRV", "At J309: BL and ACC+"),
    _tvs15("D317", "DRV", "At J310: FD_ONELINE, 0-15 V. ⏸️ DNP with the "
           "parked display (D19)", dnp=True),
    # ── display block, parked with D19: footprints fitted ───────────────────
    _tvs15("D406", "DRV", "At J405: TT_L, TT_R, TT_HL, DISP_ONELINE. ⏸️ DNP "
           "with the parked display (D19); populate-and-go", dnp=True),
    _tvs5("D405", "DRV", "At J405: CANH, CANL"),
    _r("R426", "DRV", "1k",
       "LEFT telltale series to display pin 1, fed from the TURN_L lamp feed, "
       "not a driver channel (plan §6.2.1). BOM B3"),
    _r("R427", "DRV", "1k", "RIGHT telltale series to display pin 4. BOM B3"),
    _r("R428", "DRV", "1k",
       "Headlight telltale series to display pin 5, fed from HL_HIGH so a "
       "flash lights it with no firmware (plan §7); LOW beam does not. BOM B3"),
    _r("R429", "DRV", "1k",
       "Series in the one-line feed to display pin 9: back-feed protection "
       "while the FarDriver drives 0-15 V into an unpowered display "
       "(plan §3.3). BOM B3"),
)

# ════════════════════════════════════════════════════════════════════════════
# PARTS — BRAIN (L4): logic. The module footprint serves -WROOM-1 and -1U.
# ════════════════════════════════════════════════════════════════════════════
_U401_PINS = (
    "3V3", "EN", "GND", "EPAD",
    "IO0", "IO1", "IO2", "IO4", "IO5", "IO6", "IO7", "IO8", "IO9", "IO10",
    "IO11", "IO12", "IO13", "IO14", "IO15", "IO16", "IO17", "IO18", "IO19",
    "IO20", "IO21", "IO35", "IO36", "IO37", "IO38", "IO39", "IO40", "IO41",
    "IO42", "IO43", "IO44", "IO47", "IO48",
)

#: Expander #2's spare input-capable bits: on J409, unfitted.  GPA7/GPB7 are
#: output-only and stay nc.
_U403_SPARES = tuple(f"GPA{i}" for i in range(1, 7)) + tuple(f"GPB{i}" for i in range(7))
#: Each spare is class A (plan §4), as the bar inputs are, and the network is
#: fitted: a header soldered into J409 later is ready to wire.  (bit, J409 pin,
#: pull-up, series, cap, TVS line); four SMS05T1G quads, the last three lines
#: of D413 grounded as on the other arrays.
_SPARE_TVS = ("D410", "D411", "D412", "D413")
_SPARE_LINES = tuple(
    (bit, n, f"R{446 + i}", f"R{459 + i}", f"C{423 + i}",
     f"{_SPARE_TVS[i // 4]}.{('K1', 'K3', 'K4', 'K6')[i % 4]}")
    for i, (n, bit) in enumerate(enumerate(_U403_SPARES, start=3)))


_MCP_SOURCE = (
    f"{_DS_MCP} p.11 Table 2-1 (SPDIP): GPB0-7 1-8 · VDD 9 · VSS 10 · NC 11 · "
    f"SCK 12 · SDA 13 · NC 14 · A0-A2 15-17 · RESET 18 · INTB 19 · INTA 20 · "
    f"GPA0-7 21-28. A0-A2 and RESET 'Must be externally biased'. ⛔ GPA7 and "
    f"GPB7 are 'Output only (MCP23017)' and carry nothing. nc NC11/NC14: 'NC "
    f"(MCP23017)'. nc INTB: p.20 'When MIRROR = 1, the INTn pins are "
    f"functionally OR'ed', so INTA alone reports both ports. nc spare GPx: "
    f"'Can be enabled for … internal weak pull-up resistor' — firmware sets "
    f"GPPU on every spare input bit and drives GPA7/GPB7 as outputs (p.18). "
    f"p.33: SPDIP top-to-seating-plane 0.200 in = 5.08 mm max, soldered "
    f"direct with no socket. 400 kHz at 3.3 V. BOM C3")


def _class_a_parts(pull: str, series: str, cap: str, net: str) -> tuple[Part, ...]:
    """plan §4 class A: 1 kΩ pull-up · 1 kΩ series · 100 nF at the pin."""
    return (
        _r(pull, "BRAIN", "1k",
           f"Class-A PULL-UP to V3P3 for {net}, on the CONTACT side of the "
           f"series resistor. 1 kΩ, not 4.7 kΩ: 3.3 mA of wetting current "
           f"through a bought switch (plan §4). BOM C1"),
        _r(series, "BRAIN", "1k",
           f"Class-A SERIES into the pin for {net} (plan §4). BOM C1"),
        _c(cap, "BRAIN", "100nF", 50.0,
           f"Class-A 100 nF to GND at the pin for {net} (plan §4). BOM C1"),
    )


_BRAIN_PARTS = (
    Part("U401", "ESP32-S3-WROOM-1U-N8", "WROOM-1 / WROOM-1U SMD module",
         "BRAIN", "MODULE", _U401_PINS, 3.35, height_confirmed=True,
         footprint_mm=(18.0, 25.5), nc=("IO3", "IO45", "IO46"),
         value="U.FL antenna: the enclosure is metal (BD-19). The footprint also takes the -1-N8",
         source=f"BOM A4 / D18: 8 MB quad flash, no PSRAM, -40…+85 °C; never "
                f"R8/R16V (65 °C). {_DS_WROOM} p.11-12 Table 3-1, 41 pads: "
                f"GND = pads 1 and 40, EPAD = 41, 3V3 = 2, EN = 3 ('Do not "
                f"leave the EN pin floating'), IO43 = pad 37 'TXD0', IO44 = "
                f"pad 36 'RXD0'. ⛔ There is NO IO33 / IO34 pad. nc IO3, IO45, "
                f"IO46: the unused strapping pins, which no wire may reach "
                f"(plan §3.1.2). {_DS_HDG} p.18: 'For unused pins … enable the "
                f"internal pull during software initialization'. p.42: 18 × 25.5 × 3.1±0.15 (-1), "
                f"18 × 19.2 × 3.2±0.15 (-1U) — booked at the -1U's 3.35 max. "
                f"Keep the antenna keep-out either way"),
    Part("U402", "MCP23017T-E/SS", "SSOP-28", "BRAIN", "IC",
         ("GPA0", "GPA1", "GPA2", "GPA3", "GPA4", "GPA5", "GPA6",
          "GPB0", "GPB1", "GPB2", "GPB3", "GPB4", "GPB5", "GPB6",
          "VDD", "VSS", "SCK", "SDA", "A0", "A1", "A2", "RESET", "INTA"),
         2.0, footprint_mm=(10.5, 8.2),
         nc=("GPA7", "GPB7", "INTB", "NC11", "NC14"),
         value="I²C address 0x20 (A2..A0 = 000)",
         source=f"Expander #1: every bar input. {_MCP_SOURCE}"),
    Part("U403", "MCP23017T-E/SS", "SSOP-28", "BRAIN", "IC",
         ("VDD", "VSS", "SCK", "SDA", "A0", "A1", "A2", "RESET", "GPA0")
         + _U403_SPARES,
         2.0, footprint_mm=(10.5, 8.2),
         nc=("GPA7", "GPB7", "INTA", "INTB", "NC11", "NC14"),
         value="I²C address 0x21 (A2..A0 = 001)",
         source=f"Expander #2: GPA0 senses ACC+; the other 13 input-capable "
                f"bits are spare, brought out to the unfitted header J409. "
                f"nc INTA: nothing on #2 needs an interrupt; ACC_SENSE is "
                f"polled. {_MCP_SOURCE}"),
    *(part for bit, _, pull, series, cap, _ in _SPARE_LINES
      for part in _class_a_parts(pull, series, cap, f"SPARE_{bit[2:]}")),
    *(_tvs5(ref, "BRAIN", "J409, expander #2's spare inputs: class A (plan §4)")
      for ref in _SPARE_TVS),
    Part("U404", "SN65HVD230DR", "SOIC-8", "BRAIN", "IC",
         ("D", "GND", "VCC", "R", "CANL", "CANH", "RS"), 1.75,
         height_confirmed=True, footprint_mm=(5.0, 6.2), nc=("Vref",),
         source=f"CAN transceiver; hardware fitted, feed parked (D19). BOM B1. "
                f"{_DS_HVD} p.5: D 1 · GND 2 · VCC 3 · R 4 · Vref 5 · CANL 6 · "
                f"CANH 7 · RS 8. nc Vref: p.20 'If the Vref pin is not used it "
                f"may be left floating'. p.40: SOIC 1.75 mm max"),
    Part("U405", "TLV76733DGNR", "8-HVSSOP PowerPAD", "BRAIN", "IC",
         ("IN", "OUT", "SNS", "EN", "GND", "PAD"), 1.1, height_confirmed=True,
         footprint_mm=(3.1, 5.05), nc=("NC",), v_max=16.0,
         value="5 V → 3.3 V, 1 A, 1 %",
         source=f"BRAIN's regulator: the S3 wants ≥500 mA ({_DS_HDG} p.8) and "
                f"16 V of input rating rides the Cincon's 6.2 V output clamp. "
                f"{_DS_TLV} p.3-4 (DGN, fixed): OUT 1 · SNS 2 · NC 3,7 · GND "
                f"4,6 · EN 5 · IN 8 · pad. SNS: 'Connect the SNS pin to the OUT "
                f"pin … Do not float'. EN ties to IN ('can be connected to the "
                f"input pin'). PAD to GND. nc NC: Figure 5-4 names pads 3 and "
                f"7 NC and Table 5-1 gives them no function. p.41: 1.1 mm max"),
    _r("R401", "BRAIN", "120R",
       "CAN termination at the module end. 68 Ω joined with the panel's own "
       "132.4 Ω is the CAN pre-flight gate. BOM B2"),
    *_class_a_parts("R402", "R413", "C401", "IN01_TURN_L"),
    *_class_a_parts("R403", "R414", "C402", "IN02_TURN_R"),
    *_class_a_parts("R404", "R415", "C403", "IN03_HORN"),
    *_class_a_parts("R405", "R416", "C404", "IN04A_LOW"),
    *_class_a_parts("R406", "R417", "C405", "IN04B_HIGH"),
    *_class_a_parts("R407", "R418", "C406", "IN09_FLASH"),
    *_class_a_parts("R408", "R419", "C407", "IN10_HAZARD"),
    *_class_a_parts("R409", "R420", "C408", "IN07_BOOST_BTN"),
    *_class_a_parts("R410", "R421", "C409", "IN08A_RUNNING"),
    *_class_a_parts("R411", "R422", "C410", "IN08B_HEADLIGHT"),
    *_class_a_parts("R412", "R423", "C411", "START_SENSE"),
    _tvs5("D401", "BRAIN", "At J402: IN04A, IN04B, IN03, IN01"),
    _tvs5("D402", "BRAIN", "At J402: IN09, IN02, IN10"),
    _tvs5("D403", "BRAIN",
          "At J403: IN08A, IN08B, RUN, START. RUN's 5.1 V sits 0.1 V over "
          "V_RWM and 1.3 V under V_BR min"),
    _tvs5("D404", "BRAIN", "At J404: the two FarDriver serial wires"),
    _tvs15("D407", "BRAIN",
           "At J404: BOOST_OUT, whose controller-side pull-up is unmeasured "
           "('3.3-12 V', plan §7.1), so it takes the 15 V array"),
    _tvs5("D408", "BRAIN", "At J401: USB-C CC1 and CC2 only. ⛔ NOT the data "
          "pair: this array is 165-220 pF per line, and D409 carries D+/D-"),
    Part("D409", "USBLC6-2SC6", "SOT23-6L", "BRAIN", "TVS",
         ("1", "2", "3", "4", "5", "6"), 1.45,
         footprint_mm=(3.0, 3.0), v_max=5.25,
         value="V_RM 5.25 V · 3.5 pF max per line",
         source="USB D+/D- ESD at J401. ST USBLC6-2SC6: pins 1 and 6 are I/O1 "
                "(flow-through), 3 and 4 are I/O2, 2 is GND, 5 is VBUS. A "
                "general-purpose array is tens of times too capacitive for a "
                "USB pair; this one is 3.5 pF max. SOT23-6 height assumed"),
    _sot23("Q401", "AO3400A", "BRAIN", "NFET", 30.0,
           "Boost open-drain output to the controller's CruisePin. ⛔ METER THE "
           "WIRE FIRST: the same 30-pin harness carries pink 60VC at 72-84 V; "
           ">25 V means a PC817 opto instead of this 30 V FET. BOM D3"),
    _r("R424", "BRAIN", "100R", "Boost gate series (plan §6.2.3). BOM D9"),
    _r("R425", "BRAIN", "10k",
       "Boost HARD external pull-down (plan §3.1.1). D14: the gate biases OFF "
       "through the ~200 ms of high-Z at boot. BOM D9"),
    _r("R430", "BRAIN", "100k",
       "IN-11 divider top, from the RUN node. SENSE ONLY: it never drives the "
       "cut. RUN is pulled to ACC+ 5.1 V by R314 10 k and loaded by Q2's gate "
       "network (R315 100 Ω + R316 100 k) in parallel with this 340 k divider: "
       "5.1 V × 77.3 k / 87.3 k = 4.52 V at the node"),
    _r("R431", "BRAIN", "240k",
       "IN-11 divider bottom: 4.52 V × 240 / 340 = 3.19 V at U402.GPB2 — "
       "0.55 V over the MCP23017's V_IH (0.8 × V_DD = 2.64 V) and 0.11 V "
       "under V_DD. 0603: the 240k LCSC stocks is an 0603", pkg="0603"),
    _r("R432", "BRAIN", "10k",
       f"FAULT1 pull-up to V3P3: FAULT is open-drain. {_DS_TPS} p.29: "
       f"'R(pu) = 10 kΩ'"),
    _r("R433", "BRAIN", "10k", "FAULT2 pull-up to V3P3, as R432"),
    _r("R434", "BRAIN", "2k2",
       "I²C SDA pull-up. I²C at 3.3 V / 400 kHz allows 967 Ω-3.5 kΩ at "
       "100 pF; D16 wants the STRONG end beside 80 A of chopped phase current"),
    _r("R435", "BRAIN", "2k2", "I²C SCL pull-up, as R434"),
    _r("R436", "BRAIN", "1k",
       "UART1 TX series (plan §4 class E); the pin is tri-stated whenever the "
       "module is not sending"),
    _r("R437", "BRAIN", "10k",
       f"MCP23017 RESET (both devices) pull-up to V3P3. {_DS_MCP} p.11: RESET "
       f"'Must be externally biased'"),
    _r("R438", "BRAIN", "10k",
       f"U401 EN pull-up to V3P3, the R of the reset RC. {_DS_HDG} p.11: "
       f"'CHIP_PU must not be left floating … R = 10 kΩ and C = 1 μF'"),
    _r("R439", "BRAIN", "10k",
       f"U401 IO0 pull-up to V3P3, so a floating J408 pin cannot select "
       f"download mode at key-on. {_DS_HDG} p.18: 'It is recommended to place "
       f"a pull-up resistor at the GPIO0 pin'"),
    _r("R440", "BRAIN", "5k1",
       "USB-C CC1 → GND: Rd 5.1 kΩ marks the port a device (USB Type-C)"),
    _r("R441", "BRAIN", "5k1", "USB-C CC2 → GND: Rd 5.1 kΩ, as R440"),
    _r("R442", "BRAIN", "10k",
       f"U404 RS → GND. {_DS_HVD} p.5: '10kΩ to 100kΩ pull down to GND = "
       f"slope control mode' — 10 kΩ is the fastest slope, ample at "
       f"250 kbit/s and quieter than high-speed mode"),
    _r("R443", "BRAIN", "1k",
       "UART1 RX series (plan §4 class E): the FarDriver's TX level is "
       "unmeasured (⬜ M9), so the harness wire never meets GPIO18 directly"),
    _r("R444", "BRAIN", "100k",
       "USB VBUS sense divider top. VBUS is SENSED ONLY — it powers nothing, "
       "so the bike's 5 V rail and a USB host never meet"),
    _r("R445", "BRAIN", "180k",
       "USB VBUS sense divider bottom: 5.0 V × 180 / 280 = 3.21 V at "
       "U402.GPB6, over V_IH 2.64 V"),
    _c("C412", "BRAIN", "1uF", 16.0,
       f"U401 EN to GND, the C of the reset RC. {_DS_HDG} p.11"),
    _c("C413", "BRAIN", "10uF", 16.0,
       f"U401 3V3 bulk, at pad 2. {_DS_HDG} p.8", pkg="1206"),
    _c("C414", "BRAIN", "100nF", 50.0, f"U401 3V3 HF decoupling. {_DS_HDG} p.8"),
    _c("C415", "BRAIN", "10uF", 16.0, "U405 input, V5 to GND", pkg="1206"),
    _c("C416", "BRAIN", "10uF", 16.0,
       f"U405 output, V3P3 to GND. {_DS_TLV} p.5: C_OUT 1-220 µF, ESR "
       f"2-500 mΩ — ceramic-stable", pkg="1206"),
    _c("C417", "BRAIN", "100nF", 50.0, "U405 output HF decoupling"),
    _c("C418", "BRAIN", "100nF", 50.0, "U402 VDD decoupling"),
    _c("C419", "BRAIN", "100nF", 50.0, "U403 VDD decoupling"),
    _c("C420", "BRAIN", "100nF", 50.0, "U404 VCC decoupling"),
    _c("C421", "BRAIN", "100nF", 50.0,
       "IN-05 to GND at the MCU pin (plan §4 class A). With R341: τ = 100 µs, "
       "well inside the <10 ms the boost safety-release wants"),
    _c("C422", "BRAIN", "100nF", 50.0, "IN-06 to GND at the MCU pin, as C421"),
)

_PARTS = _HVIN_PARTS + _CONV_PARTS + _DRV_PARTS + _BRAIN_PARTS

# ════════════════════════════════════════════════════════════════════════════
# INTERFACE PIN MAPS — the three inter-board spines (BD-3, BD-4).
# ════════════════════════════════════════════════════════════════════════════
#: HV-LINK, J104 ↔ J201. Two GND contacts, so one open contact cannot push the
#: input return through a signal ground. No 5 V: nothing on HVIN uses it.
_HVLINK_NETS = ("HV_C1_P", "HV_C1_N", "HV_C2_P", "HV_C2_N", "GND", "GND",
                "KEY_SENSE")

#: PWR-UP, J202 → J307, J407. Three V12 contacts: 2.62 A is 0.87 A each, and
#: 1.31 A each with one contact open.
_PWRUP_NETS = ("V12", "V12", "V12", "GND", "GND", "GND", "GND", "V5",
               "KEY_SENSE")

#: STACK, J308 ↔ J406, 2 × 25: odd contacts carry these in order, every even
#: contact is GND, so each signal (CS1/CS2 above all) faces a ground.
_STACK_SIGNALS = (
    "LGT_LOW", "LGT_HIGH", "LGT_DRL", "LGT_TAIL", "LGT_TURN_L", "LGT_TURN_R",
    "DIAG_EN", "SEL", "SEH", "CS1", "CS2", "FAULT1", "FAULT2",
    "HORN_CMD", "FAN_CMD", "BUZZ_CMD", "V12_SENSE", "BL_SENSE",
    "IN05_BRAKE_L", "IN06_BRAKE_R", "CANH", "CANL", "V3P3", "RUN",
    "ACC_SENSE",
)


def _p(spec: str) -> tuple[tuple[str, str], ...]:
    """'Q305.S R316.2' → (("Q305", "S"), ("R316", "2")). Keeps REF.PIN greppable."""
    return tuple((ref, pin) for ref, pin in
                 (tok.split(".", 1) for tok in spec.split()))


def _hvlink(net: str) -> tuple[tuple[str, str], ...]:
    return tuple((c, str(i + 1)) for i, n in enumerate(_HVLINK_NETS)
                 if n == net for c in ("J104", "J201"))


def _pwrup(net: str) -> tuple[tuple[str, str], ...]:
    return tuple((c, str(i + 1)) for i, n in enumerate(_PWRUP_NETS)
                 if n == net for c in ("J202", "J307", "J407"))


def _stack(net: str) -> tuple[tuple[str, str], ...]:
    i = _STACK_SIGNALS.index(net)
    return (("J308", str(2 * i + 1)), ("J406", str(2 * i + 1)))


_STACK_GND = tuple((c, str(n)) for c in ("J308", "J406") for n in range(2, 51, 2))

# ════════════════════════════════════════════════════════════════════════════
# NETS — the 84 V section. HVIN and CONV only (BD-2).
# ⚠️ Order on each branch: HV_SW → choke → bulk cap → converter. D201 + F201 sit
# between the choke and C2 ONLY, so the hold-up cap serves DC-DC #2 alone.
# ════════════════════════════════════════════════════════════════════════════
_NETS_84V = (
    Net("HV_BPLUS", _p("J101.1 D101.K Q101.S R110.2 D102.K C107.2"),
        domain="84V",
        source="B+ from the tap downstream of the XT90-S; fused UPSTREAM IN THE "
               "HARNESS by the KLKD002 (plan §3.2.5), never on the board"),
    Net("KSW", _p("J102.1 D104.K R112A.1 R107.1"), domain="84V",
        source="The key switch's OUTPUT: 84 V with the key on. The switch, its "
               "2 A fuse and the FarDriver KEY wire are harness (plan §3.2.5); "
               "the module only taps it, for D13's gate drive and for IN-12, "
               "and never sources or switches KEY (D10)"),
    Net("HV_SW", _p("Q101.D C105.2 L101.1 L102.1"), domain="84V",
        source="D13's output, ahead of both chokes"),
    Net("D13_GATE", _p("Q101.G R110.1 D102.A C105.1 C107.1 R101A.1"),
        domain="84V",
        source="Q101's gate. R110 holds it at the source (OFF); Q105 pulls it "
               "down through 540 kΩ to V_GS = -13.1 V; C105 sets the slew"),
    Net("D13_PD_MID", _p("R101A.2 R101B.1"), domain="84V",
        source="The join of the 2 × 270 kΩ pull-down string"),
    Net("D13_PD", _p("R101B.2 Q105.D"), domain="84V",
        source="Foot of the pull-down string, on Q105's drain: ~84 V with the "
               "key off, ~0 V with it on"),
    Net("D13_EN_MID", _p("R112A.2 R112B.1"), domain="84V",
        source="The join of the 2 × 499 kΩ feed from KSW"),
    Net("D13_EN", _p("R112B.2 R113.1 D106.K C108.1 Q105.G"), domain="12V",
        source="Q105's gate: 7.6 V at 84 V, 5.5 V at 60 V, 3.9 V at 43 V, "
               "clamped at 10 V by D106. Key off ⇒ 0 V ⇒ module off"),
    Net("KEY_SENSE_MID", _p("R107.2 R108.1"), domain="84V",
        source="The join of the 2 × 165 kΩ IN-12 divider top"),
    Net("HV_C1_P", _p("L101.4 C201.+ U201.+Vin C203.1") + _hvlink("HV_C1_P"),
        domain="84V", interface="HV-LINK",
        source="DC-DC #1 +Vin: choke → C1 → converter, in that order"),
    Net("HV_C1_N", _p("L101.3 C201.- U201.-Vin U201.CNT C204.1")
        + _hvlink("HV_C1_N"),
        domain="84V", interface="HV-LINK",
        source="DC-DC #1 -Vin, its OWN net: it joins GND only through L101's "
               "3-2 winding. ~0 V DC, but it is 84 V-section copper. U201.CNT "
               "is strapped here: negative logic, open = OFF"),
    Net("HV_C2_P", _p("L102.4 D201.A") + _hvlink("HV_C2_P"),
        domain="84V", interface="HV-LINK",
        source="DC-DC #2's branch after its choke, ahead of the hold-up diode"),
    Net("HV_C2_N", _p("L102.3 C202.- U202.-Vin C206.1") + _hvlink("HV_C2_N"),
        domain="84V", interface="HV-LINK",
        source="DC-DC #2 -Vin, its OWN net: it joins GND only through L102's "
               "3-2 winding"),
    Net("HV_C2_HOLD_IN", _p("D201.K FH201A.1 F201.1"), domain="84V",
        source="Between the hold-up diode and the fuse"),
    Net("HV_C2_HOLD", _p("FH201B.1 F201.2 C202.+ U202.+Vin C205.1"),
        domain="84V",
        source="⚠️ THE HOLD-UP NODE: C2 lives here and C1 does not "
               "(plan §3.2.2). 237 ms of ride-out depends on it"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — rails and returns.
# ⛔ GND is ONE star net referenced to the CONTROLLER's B− stud — never the
# battery's B− and never a frame point (plan §3.2.4, §6.0.2).
# ════════════════════════════════════════════════════════════════════════════
_NETS_RAILS = (
    Net("GND",
        # HVIN
        _p("J101.2 J101.3 J102.2 D101.A D104.A Q105.S R113.2 D106.A C108.2 "
           "R109.2 C109.2 L101.2 L102.2")
        # CONV
        + _p("U201.-V U201.-S C207.- C208.2 C210.1 U202.-Vout C211.2 C212.2 "
             "R211.2")
        # DRV
        + _p("U301.GND U301.PAD U301.THER U302.GND U302.PAD U302.THER "
             "R319.2 R320.2 R321.2 R322.2 R348.2 D318.A "
             "C301.2 C302.2 C303.2 C304.2 C305.2 C306.2 C307.2 R338.2 R339.2 R340.2 R344.2 "
             "Q301.S Q302.S Q303.S R307.2 R308.2 R309.2 D315.A "
             "Q305.S R316.2 "
             "J301.1 J302.1 J303.2 J303.4 J306.2 J306.4 J309.3 J310.2 J405.3 "
             "D308.A D309.A D310.A D311.A D312.A D319.A D320.A D321.A D322.A "
             "D323.A D324.A D325.A D326.A "
             "D313.A2 D313.A5 D313.K4 D313.K6 "
             "D316.A2 D316.A5 D316.K4 D316.K6 "
             "D317.A2 D317.A5 D317.K3 D317.K4 D317.K6 "
             "D405.A2 D405.A5 D405.K4 D405.K6 D406.A2 D406.A5")
        # BRAIN
        + _p("U401.GND U401.EPAD C412.2 C413.2 C414.2 "
             "U402.VSS U402.A0 U402.A1 U402.A2 C418.2 "
             "U403.VSS U403.A1 U403.A2 C419.2 "
             "U404.GND R442.2 C420.2 U405.GND U405.PAD C415.2 C416.2 C417.2 "
             "Q401.S R425.2 R431.2 R440.2 R441.2 R445.2 "
             "C401.2 C402.2 C403.2 C404.2 C405.2 C406.2 C407.2 C408.2 C409.2 "
             "C410.2 C411.2 C421.2 C422.2 "
             "D401.A2 D401.A5 D402.A2 D402.A5 D402.K6 D403.A2 D403.A5 "
             "D404.A2 D404.A5 D404.K4 D404.K6 "
             "D407.A2 D407.A5 D407.K3 D407.K4 D407.K6 D408.A2 D408.A5 D408.K1 D408.K3 D409.2 "
             "J401.6 J401.7 J402.1 J403.1 J404.4 J408.6 J409.2 J409.16")
        + _p(" ".join(f"{cap}.2" for *_, cap, _ in _SPARE_LINES))
        + _p(" ".join(f"{d}.A2 {d}.A5" for d in _SPARE_TVS))
        + _p("D413.K3 D413.K4 D413.K6")
        + _hvlink("GND") + _pwrup("GND") + _STACK_GND,
        domain="GND", interface="HV-LINK",
        source="The star net, on all four boards and across all three "
               "interfaces (HV-LINK × 2, PWR-UP × 4, every even STACK contact); "
               "`interface` names the lowest. Both converters' -Vout, every "
               "lamp common (plan §6.0.2), both B− conductors of J101, and "
               "both anode pads of every TVS array land here. ⛔ Display pin 3 "
               "(J405.3) is here and is NEVER switched"),
    Net("BASEPLATE",
        _p("U201.BASEPLATE C203.2 C204.2 C205.2 C206.2 C209.2 C210.2 R211.1"),
        domain="GND",
        source="U201's baseplate through its M3 holes, with the thermal "
               "interface it bolts to. The Y2 caps and TDK's C4/C5 return "
               "here; R211 ties it to GND at one point"),
    Net("V12",
        _p("U201.+V U201.+S C207.+ C208.1 C209.1") + _pwrup("V12")
        + _p("U301.VS U302.VS C303.1 C304.1 C305.1 C306.1 "
             "R301.2 R302.2 R303.2 R304.2 R305.2 R306.2 R345.2 "
             "Q304.S R313.2 D315.K R337.1"),
        domain="12V", interface="PWR-UP",
        source="DC-DC #1's output, +S strapped to +V at the brick. 2.62 A "
               "measured (plan §3.2.3). It never leaves the box: every 12 V "
               "wire out is a TPS4H160B channel. D315 is its clamp"),
    Net("V5",
        _p("U202.+Vout C211.1 C212.1") + _pwrup("V5")
        + _p("U405.IN U405.EN C415.1"),
        domain="5V", interface="PWR-UP",
        source="DC-DC #2's isolated output, referenced to the star. Feeds "
               "BRAIN's regulator and nothing else"),
    Net("V3P3",
        _p("U405.OUT U405.SNS C416.1 C417.1 U401.3V3 C413.1 C414.1 "
           "U402.VDD C418.1 U403.VDD U403.A0 C419.1 U404.VCC C420.1 "
           "R402.2 R403.2 R404.2 R405.2 R406.2 R407.2 R408.2 R409.2 R410.2 "
           "R411.2 R412.2 R432.2 R433.2 R434.2 R435.2 R437.2 R438.2 R439.2 "
           "J408.5 J409.1") + _p(" ".join(f"{pull}.2" for _, _, pull, *_ in _SPARE_LINES))
        + _stack("V3P3") + _p("R317.2 R318.2 R346.2"),
        domain="3V3", interface="STACK",
        source="BRAIN's 3.3 V rail. Crosses STACK to DRV for R317/R318, the "
               "IN-05/06 pull-ups. U403.A0 is strapped here (address 001)"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — DRV outputs. Every lamp common is GND; there is no separate return.
# ════════════════════════════════════════════════════════════════════════════
_NETS_12V = (
    Net("HL_LOW", _p("U301.OUT2 R301.1 J301.3 D308.K"), domain="12V",
        source="J301.3 is BLUE on the headlight. 12 V / 8.5 W = 0.71 A"),
    Net("HL_HIGH", _p("U301.OUT3 R302.1 J301.2 D309.K R428.1"), domain="12V",
        source="J301.2 is GREEN. ⚠️ Firmware breaks before make against LOW "
               "(never both: 1.96 A). R428 taps it for the headlight telltale"),
    Net("HL_DRL", _p("U301.OUT4 R303.1 J301.4 D310.K"), domain="12V",
        source="J301.4 is YELLOW. 12 V / 6.5 W = 0.54 A"),
    Net("AUX12", _p("U301.OUT1 J304.1 J305.1 J305.3 D307.K D314.K D326.K"),
        domain="12V",
        source="U301 OUT1, the current-limited feed to horn +, fan + and "
               "buzzer +: 0.10 + ~0.50 A + a few mA against its 2 A limit. ⛔ "
               "J304.1 is BLUE and it is the POSITIVE — red is not"),
    Net("AUX12_EN", _p("U301.IN1 R346.1"), domain="3V3",
        source="U301 IN1, held high from V3P3 by R346"),
    Net("TAIL_RUN", _p("U302.OUT1 R304.1 J302.2 D320.K"), domain="12V",
        source="J302.2 YELLOW, 0.05 A, a separate feed and not PWM"),
    Net("TURN_L", _p("U302.OUT2 R305.1 J302.4 J303.1 R426.1 D321.K D324.K"),
        domain="12V",
        source="Rear LEFT is J302.4 BLUE (M6); the front pair is on J303"),
    Net("TURN_R", _p("U302.OUT3 R306.1 J302.5 J303.3 R427.1 D322.K D325.K"),
        domain="12V", source="Rear RIGHT is J302.5 GREEN (M6)"),
    Net("TAIL_STOP", _p("U302.OUT4 R345.1 J302.3 D323.K"), domain="12V",
        source="J302.3 RED, 0.12 A, on U302 OUT4 -- a hardware-commanded "
               "channel (D23): the levers drive Q1, Q1 drives IN4, and nothing "
               "firmware touches is in that path. The channel adds the 1 A "
               "limit, OFF-state open-load detection through R345 and FAULT2; "
               "firmware reads the lamp current on CS2 (SEL/SEH = channel 4) "
               "and cross-checks it against IN-05/06"),
    Net("STOP_CMD", _p("Q304.D R347.1"), domain="12V",
        source="Q1's drain: V12 while either lever is pulled, else open"),
    Net("STOP_IN4", _p("R347.2 R348.1 D318.K U302.IN4"), domain="3V3",
        source="U302 IN4: 3.0-3.2 V braking at 12 V, 0 V released"),
    Net("HORN_N", _p("J304.2 Q301.D D311.K"), domain="12V",
        source="J304.2 BLACK = '-'. ⛔ Red is not the positive on the horn. "
               "Electronic horn, 0.10 A, so no flyback (M7)"),
    Net("FAN_RTN", _p("J305.2 Q302.D D307.A D312.K"), domain="12V",
        source="Fan '-', LEDC PWM; D307 is the flyback across the motor"),
    Net("BUZZ_RTN", _p("J305.4 Q303.D D314.A D319.K"), domain="12V",
        source="Buzzer '-', LEDC PWM; D314 is the flyback across it"),
    Net("CL1", _p("U301.CL R319.1"), domain="3V3",
        source="U301's current-limit programming node, 0.8 V across R319"),
    Net("CL2", _p("U302.CL R320.1"), domain="3V3",
        source="U302's current-limit programming node, 0.8 V across R320"),
    Net("CS1_RAW", _p("U301.CS R321.1 R323.1"), domain="5V",
        source="U301's current-sense node: 0-4 V linear across R321, and "
               "4.5-6.5 V in any fault — which is why it never meets the ADC "
               "pin without R323"),
    Net("CS2_RAW", _p("U302.CS R322.1 R324.1"), domain="5V",
        source="U302's current-sense node, as CS1_RAW"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — D23, the brake and kill hardware. Complete on DRV: BRAIN only listens.
# ⚠️ brake-circuit.md §2's '|◄' = CATHODE ON THE LEVER-NODE SIDE.
# ⭐ An open bar wire, pod, STACK contact or BRAIN leaves the RUN node pulled up
# by R314 on DRV, which reads as OFF and stops drive. ⚠️ The exception is ACC+
# itself: open, there is nothing to pull the node up with, and the kill is dead
# without a sign -- ACC_SENSE reports it to firmware; the levers still cut.
# ════════════════════════════════════════════════════════════════════════════
_NETS_BRAKE = (
    Net("LEVER_L", _p("J306.1 D301.K D303.K D305.K D313.K1"), domain="12V",
        source=f"Left lever node. Idles at ~11.4 V through D303 and R313 "
               f"({_BRK} §3); a pull takes it to B−. ⬜ M3 gates J306: lever "
               f"type, NO/NC and wire count"),
    Net("LEVER_R", _p("J306.3 D302.K D304.K D306.K D313.K3"), domain="12V",
        source=f"Right lever node, as LEVER_L ({_BRK} §2)"),
    Net("Q1_GATE", _p("D303.A D304.A R313.1 Q304.G"), domain="12V",
        source="Either lever pulls Q1's gate down and the stop lamp lights "
               "WITHOUT FIRMWARE. Rests at 12 V through R313"),
    Net("BL", _p("D301.A D302.A Q305.D R336.1 J309.1 D316.K1"), domain="3V3",
        source=f"FarDriver BL, YELLOW/GREEN — never grey BH, which stays "
               f"capped. Rests on the controller's own ~3.3 V pull-up "
               f"({_BRK} §7.1); a lever or Q2 pulls it low = motor cut. It "
               f"leaves the box from DRV on J309 and touches no other board. "
               f"The 100 nF brake C1 belongs at the controller, not here"),
    Net("BL_SENSE", _p("R336.2") + _stack("BL_SENSE") + _p("U402.GPB5"),
        domain="3V3", interface="STACK",
        source="The 100 kΩ-isolated copy of BL that firmware reads"),
    Net("ACC_SENSE", _p("R343.2 R344.1") + _stack("ACC_SENSE") + _p("U403.GPA0"),
        domain="3V3", interface="STACK",
        source="ACC+ divided to 3.28 V for expander #2. LOW with the key on "
               "means the run/off kill has no pull-up and cannot cut the "
               "motor -- firmware must raise it; hardware cannot know"),
    Net("ACC_PLUS", _p("J309.2 R314.1 R343.1 D316.K3"), domain="5V",
        source=f"The throttle's 5.1 V supply, in from the FarDriver harness. "
               f"It feeds R314 alone, so the kill works with the module's own "
               f"rails dead ({_BRK} §2.1)"),
    Net("RUN",
        _p("J403.4 D403.K4 R430.1") + _stack("RUN") + _p("R314.2 R315.1"),
        domain="5V", interface="STACK",
        source=f"Right pod RED: closed to ground in RUN, open in OFF. Bare "
               f"copper from J403 across STACK to DRV (BD-7), tapped on BRAIN "
               f"for IN-11. 4.52 V when open ({_BRK} §2.1)"),
    Net("Q2_GATE", _p("R315.2 Q305.G R316.1"), domain="5V",
        source="The run/off kill inverter's gate; R316 biases it OFF"),
    Net("IN05_NODE", _p("D305.A R317.1 R341.1"), domain="3V3",
        source="The D23 sense node for the left lever: D3L's anode and its "
               "10 kΩ pull-up (R3L), ahead of the class-A series resistor"),
    Net("IN06_NODE", _p("D306.A R318.1 R342.1"), domain="3V3",
        source="As IN05_NODE, for the right lever"),
    Net("IN05_BRAKE_L",
        _p("R341.2") + _stack("IN05_BRAKE_L") + _p("U401.IO15 C421.1"),
        domain="3V3", interface="STACK", gpio="GPIO15",
        source="Stays NATIVE: the boost safety-release wants it in <10 ms "
               "(plan §3.1.1). The lever wire's TVS is D313 at J306"),
    Net("IN06_BRAKE_R",
        _p("R342.2") + _stack("IN06_BRAKE_R") + _p("U401.IO16 C422.1"),
        domain="3V3", interface="STACK", gpio="GPIO16",
        source="As IN05_BRAKE_L, for the right lever"),
    Net("IN11_SENSE", _p("R430.2 R431.1 U402.GPB2"), domain="3V3",
        source="RUN through 100 k / 240 k: 3.19 V with the toggle OFF. Sense "
               "only — it never drives the cut"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — STACK control and diagnostics (DRV ↔ BRAIN). Lighting is FULL NATIVE
# (BD-5): no bus sits between the S3 and a lamp.
# ════════════════════════════════════════════════════════════════════════════
_LGT = ("The TPS4H160B's internal input pull-down holds the channel OFF "
        "through the ~200 ms the GPIO spends high-Z at boot (D14, plan §6.2.2a)")

_NETS_STACK = (
    Net("LGT_LOW", _p("U401.IO36") + _stack("LGT_LOW") + _p("R327.1"),
        domain="3V3", interface="STACK", gpio="GPIO36",
        source=f"Headlight LOW command. {_LGT}"),
    Net("LGT_LOW_IN", _p("R327.2 U301.IN2"), domain="3V3",
        source="Device side of R327"),
    Net("LGT_HIGH", _p("U401.IO37") + _stack("LGT_HIGH") + _p("R328.1"),
        domain="3V3", interface="STACK", gpio="GPIO37",
        source=f"Headlight HIGH command. {_LGT}"),
    Net("LGT_HIGH_IN", _p("R328.2 U301.IN3"), domain="3V3",
        source="Device side of R328"),
    Net("LGT_DRL", _p("U401.IO38") + _stack("LGT_DRL") + _p("R329.1"),
        domain="3V3", interface="STACK", gpio="GPIO38",
        source=f"Headlight DRL command. {_LGT}"),
    Net("LGT_DRL_IN", _p("R329.2 U301.IN4"), domain="3V3",
        source="Device side of R329"),
    Net("LGT_TAIL", _p("U401.IO11") + _stack("LGT_TAIL") + _p("R330.1"),
        domain="3V3", interface="STACK", gpio="GPIO11",
        source=f"Tail running command. {_LGT} GPIO11, never GPIO39: MTCK comes "
               f"out of reset pulled UP (datasheet v2.2 Table 2-1 note 7), "
               f"which would light the tail before firmware runs"),
    Net("LGT_TAIL_IN", _p("R330.2 U302.IN1"), domain="3V3",
        source="Device side of R330"),
    Net("LGT_TURN_L", _p("U401.IO40") + _stack("LGT_TURN_L") + _p("R331.1"),
        domain="3V3", interface="STACK", gpio="GPIO40",
        source=f"Turn LEFT command. {_LGT}"),
    Net("LGT_TURN_L_IN", _p("R331.2 U302.IN2"), domain="3V3",
        source="Device side of R331"),
    Net("LGT_TURN_R", _p("U401.IO41") + _stack("LGT_TURN_R") + _p("R332.1"),
        domain="3V3", interface="STACK", gpio="GPIO41",
        source=f"Turn RIGHT command. {_LGT}"),
    Net("LGT_TURN_R_IN", _p("R332.2 U302.IN3"), domain="3V3",
        source="Device side of R332"),
    Net("DIAG_EN", _p("U401.IO7") + _stack("DIAG_EN") + _p("R333.1"),
        domain="3V3", interface="STACK", gpio="GPIO7",
        source="Diagnostics enable, bussed to both devices behind R333"),
    Net("DIAG_EN_IN", _p("R333.2 U301.DIAG_EN U302.DIAG_EN"), domain="3V3",
        source="Device side of R333"),
    Net("SEL", _p("U401.IO8") + _stack("SEL") + _p("R334.1"),
        domain="3V3", interface="STACK", gpio="GPIO8",
        source="CS channel-select LOW bit (TI's SEL, pad 8), bussed"),
    Net("SEL_IN", _p("R334.2 U301.SEL U302.SEL"), domain="3V3",
        source="Device side of R334"),
    Net("SEH", _p("U401.IO9") + _stack("SEH") + _p("R335.1"),
        domain="3V3", interface="STACK", gpio="GPIO9",
        source="CS channel-select HIGH bit (TI's SEH, pad 7), bussed"),
    Net("SEH_IN", _p("R335.2 U301.SEH U302.SEH"), domain="3V3",
        source="Device side of R335"),
    Net("CS1", _p("R323.2 R339.1 C301.1") + _stack("CS1") + _p("U401.IO4"),
        domain="3V3", interface="STACK", gpio="GPIO4",
        source="U301's current sense behind R323. ⚠️ ADC1 ONLY (ADC2 dies with "
               "WiFi), and it faces a ground contact across STACK"),
    Net("CS2", _p("R324.2 R340.1 C302.1") + _stack("CS2") + _p("U401.IO5"),
        domain="3V3", interface="STACK", gpio="GPIO5",
        source="U302's current sense behind R324. ⚠️ ADC1 only"),
    Net("FAULT1", _p("U301.FAULT") + _stack("FAULT1") + _p("R432.1 U401.IO39"),
        domain="3V3", interface="STACK", gpio="GPIO39",
        source="U301's open-drain global fault, pulled up on BRAIN. Digital "
               "only. GPIO39's reset pull-up only joins R432's"),
    Net("FAULT2", _p("U302.FAULT") + _stack("FAULT2") + _p("R433.1 U401.IO12"),
        domain="3V3", interface="STACK", gpio="GPIO12", source="As FAULT1"),
    Net("HORN_CMD", _p("U401.IO42") + _stack("HORN_CMD") + _p("R310.1"),
        domain="3V3", interface="STACK", gpio="GPIO42",
        source="MCU side of the horn gate resistor"),
    Net("HORN_GATE", _p("R310.2 Q301.G R307.1"), domain="3V3",
        source="D14: R307 biases the gate OFF"),
    Net("FAN_CMD", _p("U401.IO6") + _stack("FAN_CMD") + _p("R311.1"),
        domain="3V3", interface="STACK", gpio="GPIO6",
        source="LEDC PWM. GPIO6 has no boot-time pull-up, so R308 alone sets "
               "the gate through reset (GPIO44's 45 kΩ pull-up would sit the "
               "gate at the AO3400A's V_th)"),
    Net("FAN_GATE", _p("R311.2 Q302.G R308.1"), domain="3V3",
        source="D14: R308 biases the gate OFF"),
    Net("BUZZ_CMD", _p("U401.IO47") + _stack("BUZZ_CMD") + _p("R312.1"),
        domain="3V3", interface="STACK", gpio="GPIO47", source="LEDC PWM"),
    Net("BUZZ_GATE", _p("R312.2 Q303.G R309.1"), domain="3V3",
        source="D14: R309 biases the gate OFF"),
    Net("V12_SENSE",
        _p("R337.2 R338.1 C307.1") + _stack("V12_SENSE") + _p("U401.IO2"),
        domain="3V3", interface="STACK", gpio="GPIO2",
        source="IN-15, ADC1_CH1: V12 through 47 k / 10 k on DRV"),
    Net("CANH", _p("U404.CANH R401.1") + _stack("CANH") + _p("J405.8 D405.K1"),
        domain="3V3", interface="STACK",
        source="Display pin 8, RED-BLACK. The panel terminates its own end "
               "(132.4 Ω). A 3.3 V transceiver's pair; even a 5 V part at the "
               "panel end drives CANH to 4.5 V at most, under D405's 5 V "
               "V_RWM. The transceiver is on BRAIN and J405 on DRV, so the "
               "pair crosses STACK"),
    Net("CANL", _p("U404.CANL R401.2") + _stack("CANL") + _p("J405.7 D405.K3"),
        domain="3V3", interface="STACK",
        source="Display pin 7, GREEN-BLACK. As CANH"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — the parked display block on DRV (D19).
# ════════════════════════════════════════════════════════════════════════════
_NETS_DISPLAY = (
    Net("TT_L", _p("R426.2 J405.1 D406.K1"), domain="12V",
        source="Display pin 1, telltale LEFT: a 0-15 V input fed from the "
               "TURN_L lamp feed through R426"),
    Net("TT_R", _p("R427.2 J405.4 D406.K3"), domain="12V",
        source="Display pin 4, telltale RIGHT"),
    Net("TT_HL", _p("R428.2 J405.5 D406.K4"), domain="12V",
        source="Display pin 5, telltale HEADLIGHT, fed from HL_HIGH"),
    Net("DISP_ONELINE", _p("R429.2 J405.9 D406.K6"), domain="12V",
        source="Display pin 9, the one-line feed behind R429. 0-15 V"),
    Net("FD_ONELINE", _p("J310.1 R429.1 D317.K1"), domain="12V",
        source="The FarDriver's BROWN one-line lead, 0-15 V, in on J310"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — BRAIN: the module's support pins, buses, serial, CAN, boost, USB.
# ════════════════════════════════════════════════════════════════════════════
_NETS_BRAIN = (
    Net("KEY_SENSE",
        _p("R108.2 R109.1 C109.1") + _hvlink("KEY_SENSE") + _pwrup("KEY_SENSE")
        + _p("U401.IO1"),
        domain="3V3", interface="HV-LINK", gpio="GPIO1",
        source="IN-12, ADC1_CH0: KSW through 330 k / 10 k, 84 V → 2.47 V. "
               "Tapped UPSTREAM of the hold-up diode, so key-off shows at once "
               "while C2 keeps the logic alive (plan §3.2.2). Divider on HVIN, "
               "pin on BRAIN: crosses HV-LINK and PWR-UP. Key state only — "
               "never a battery gauge"),
    Net("EN", _p("U401.EN R438.1 C412.1 J408.1"), domain="3V3",
        source="Module enable: 10 kΩ / 1 µF reset RC, and out to the service "
               "header for a manual reset"),
    Net("BOOT_IO0", _p("U401.IO0 R439.1 J408.2"), domain="3V3", gpio="GPIO0",
        source="Boot-mode strap, pulled up. ⛔ It reaches the INTERNAL service "
               "header only — no wire that leaves the box lands on a "
               "strapping pin (plan §3.1.2)"),
    Net("U0TXD", _p("U401.IO43 J408.3"), domain="3V3", gpio="GPIO43",
        source="ROM boot log and download-mode TX, to the service header "
               "only. ⛔ Never a load driver: it chatters at every reset"),
    Net("UART2_RX", _p("U401.IO44 J408.4"), domain="3V3", gpio="GPIO44",
        source="GPIO44 = U0RXD: download-mode RX on the service header, and "
               "the pin held for IN-14, the dongle-TX listen-only tap. ⬜ M9 "
               "decides whether IN-14 exists; until then no harness connector "
               "carries it"),
    Net("SDA", _p("U401.IO13 U402.SDA U403.SDA R434.1"), domain="3V3",
        gpio="GPIO13", source="I²C data: bar inputs only (BD-5)"),
    Net("SCL", _p("U401.IO14 U402.SCK U403.SCK R435.1"), domain="3V3",
        gpio="GPIO14", source="I²C clock, onto the MCP23017's pin 12 'SCK'"),
    Net("MCP_INT", _p("U402.INTA U401.IO35"), domain="3V3", gpio="GPIO35",
        source="Interrupt from expander #1, IOCON.MIRROR = 1. GPIO35 is free "
               "because the module is an -N8 (no octal PSRAM)"),
    Net("MCP_RESET", _p("U402.RESET U403.RESET R437.1"), domain="3V3",
        source="Both expanders' RESET, held high by R437"),
    Net("TWAI_TX", _p("U401.IO10 U404.D"), domain="3V3", gpio="GPIO10",
        source="To the transceiver's D. CAN hardware is fitted; D19 parks the "
               "feed"),
    Net("TWAI_RX", _p("U404.R U401.IO21"), domain="3V3", gpio="GPIO21",
        source="From the transceiver's R"),
    Net("CAN_RS", _p("U404.RS R442.1"), domain="3V3",
        source="Mode pin, to GND through R442: slope-control mode"),
    Net("UART1_TX", _p("U401.IO17 R436.1"), domain="3V3", gpio="GPIO17",
        source="Class E: tri-stated whenever the module is not sending"),
    Net("UART1_TX_WIRE", _p("R436.2 J404.2 D404.K3"), domain="3V3",
        source="J404.2, RED/BLACK, labelled 'RXD'. Class E: direct 3.3 V on "
               "the shared ground (plan §4). ⬜ M9: direction and level are "
               "MEASURED, not read off the label"),
    Net("UART1_RX_WIRE", _p("J404.1 D404.K1 R443.1"), domain="3V3",
        source="J404.1, BROWN/BLUE, labelled 'TXD'. IN-13, a listen-only tap "
               "on the shared ground. ⬜ M9 as UART1_TX_WIRE"),
    Net("UART1_RX", _p("R443.2 U401.IO18"), domain="3V3", gpio="GPIO18",
        source="IN-13 behind its 1 kΩ"),
    Net("BOOST_CMD", _p("U401.IO48 R424.1"), domain="3V3", gpio="GPIO48",
        source="A DEDICATED native pin, never on a bus: a garbled bus frame "
               "must not be able to assert boost (plan §3.1.1)"),
    Net("BOOST_GATE", _p("R424.2 Q401.G R425.1"), domain="3V3",
        source="R425 is the hard pull-down: boost defaults OFF through the "
               "boot's high-Z window (D14)"),
    Net("BOOST_OUT", _p("Q401.D J404.5 D407.K1"), domain="12V",
        source="Open-drain to the controller's CruisePin (PIN17). 12 V class "
               "until the wire is metered: its pull-up is stated only as "
               "'3.3-12 V' (plan §7.1)"),
    Net("USB_DM", _p("J401.4 U401.IO19 D409.3 D409.4"), domain="3V3", gpio="GPIO19",
        source="Native USB D-: console, flashing and the OTA fallback"),
    Net("USB_DP", _p("J401.3 U401.IO20 D409.1 D409.6"), domain="3V3", gpio="GPIO20",
        source="Native USB D+"),
    Net("USB_CC1", _p("J401.2 R440.1 D408.K4"), domain="3V3",
        source="USB-C CC1, Rd to GND"),
    Net("USB_CC2", _p("J401.5 R441.1 D408.K6"), domain="3V3",
        source="USB-C CC2, Rd to GND"),
    Net("USB_VBUS", _p("J401.1 R444.1 D409.5"), domain="5V",
        source="USB VBUS, sensed only: it reaches a 100 kΩ resistor and "
               "nothing else"),
    Net("USB_VBUS_SENSE", _p("R444.2 R445.1 U402.GPB6"), domain="3V3",
        source="'A host is plugged in', 3.21 V at 5.0 V"),
)


def _class_a_nets(pull: str, series: str, cap: str, net: str, bit: str,
                  wire: str, where: str, expander: str = "U402") -> tuple[Net, Net]:
    """The two nets of one class-A input: harness side, then expander side."""
    which = {"U402": "#1", "U403": "#2"}[expander]
    return (
        Net(f"{net}_WIRE", _p(f"{pull}.1 {series}.1 {wire}"), domain="3V3",
            source=f"Harness side of {net}: pull-up, series resistor and TVS "
                   f"all at the module end. {where}"),
        Net(net, _p(f"{series}.2 {cap}.1 {expander}.{bit}"), domain="3V3",
            source=f"The conditioned node at expander {which}'s {bit}"),
    )


_NETS_CLASS_A = (
    *_class_a_nets("R402", "R413", "C401", "IN01_TURN_L", "GPA0",
                   "J402.6 D401.K6", "Left pod 'green-black' (turn trio)"),
    *_class_a_nets("R403", "R414", "C402", "IN02_TURN_R", "GPA1",
                   "J402.8 D402.K3", "Left pod 'green-white' (turn trio)"),
    *_class_a_nets("R404", "R415", "C403", "IN03_HORN", "GPA2",
                   "J402.5 D401.K4", "Left pod 'brown'"),
    *_class_a_nets("R405", "R416", "C404", "IN04A_LOW", "GPA3",
                   "J402.3 D401.K1", "Left pod 'light blue'"),
    *_class_a_nets("R406", "R417", "C405", "IN04B_HIGH", "GPA4",
                   "J402.4 D401.K3", "Left pod 'blue'"),
    *_class_a_nets("R407", "R418", "C406", "IN09_FLASH", "GPA5",
                   "J402.7 D402.K1", "Left pod 'red-gold'"),
    *_class_a_nets("R408", "R419", "C407", "IN10_HAZARD", "GPA6",
                   "J402.9 D402.K4", "Left pod 'green-black' (hazard trio)"),
    *_class_a_nets("R409", "R420", "C408", "IN07_BOOST_BTN", "GPB3", "",
                   "⬜ M8: the throttle's red button is a 2-pin dry-contact "
                   "lead with no connector allocated, so this node reaches no "
                   "harness yet. GPB3, never GPA7: that bit is output-only"),
    *_class_a_nets("R410", "R421", "C409", "IN08A_RUNNING", "GPB0",
                   "J403.2 D403.K1", "Right pod 'black', slider 2 and 3"),
    *_class_a_nets("R411", "R422", "C410", "IN08B_HEADLIGHT", "GPB1",
                   "J403.3 D403.K3", "Right pod 'yellow', slider 3 only"),
    Net("START", _p("R412.1 R423.1 J403.5 D403.K6"), domain="3V3",
        source="Right pod GREEN, the start button: a spare sensed input that "
               "closes to the pod's shared ground. Class A, like every other "
               "bar contact"),
    Net("START_SENSE", _p("R423.2 C411.1 U402.GPB4"), domain="3V3",
        source="The conditioned start-button node at expander #1's GPB4"),
    *(net for bit, n, pull, series, cap, tvs in _SPARE_LINES
      for net in _class_a_nets(pull, series, cap, f"SPARE_{bit[2:]}", bit,
                               f"J409.{n} {tvs}", "J409, internal: a spare of "
                               "expander #2, header not fitted", expander="U403")),
)

_NETS = (_NETS_84V + _NETS_RAILS + _NETS_12V + _NETS_BRAKE + _NETS_STACK
         + _NETS_DISPLAY + _NETS_BRAIN + _NETS_CLASS_A)

# ════════════════════════════════════════════════════════════════════════════
# CONNECTORS. One keyed, latched shell per harness bundle: ⛔ "colour is never
# evidence on this bike", and a keyed shell makes a mis-plug impossible where
# colour cannot. All right-angle and edge-facing (BD-8).
# ════════════════════════════════════════════════════════════════════════════
def _cp(pin: str, net: str, note: str = "") -> ConnPin:
    return ConnPin(pin, net, note)


#: Every wire into the box lands on a pluggable screw terminal (owner,
#: 2026-09-18): nothing to crimp, no housing to match.  (pitch mm, positions) ->
#: (the right-angle header JLC places, the loose screw plug the owner wires).
#: One maker's pair, so they mate by construction; the LOCKING version, whose
#: plug screws to the header's flanges, because a bike vibrates.
_TERMINALS = {
    (3.81, 2): ("C133147", "C62113"), (3.81, 3): ("C160129", "C106871"),
    (3.81, 4): ("C160127", "C157472"), (3.81, 5): ("C50223", "C50222"),
    (3.81, 9): ("C489995", "C384932"),
    (5.08, 2): ("C63299", "C63303"), (5.08, 3): ("C49238", "C49239"),
}
#: Per family, from its drawings: header height and depth, the length N x pitch +
#: `extra` over both locking flanges, the hole, and what the plug takes.
_TB_FAMILY = {
    3.81: dict(ds=_DS_KX381, h=9.2, deep=7.25, extra=0.88 + 2 * 4.80, hole=1.40,
               plug="28-16 AWG (1.5 mm²), strip 6-7 mm, 0.2 N·m",
               rating="300 V UL / 160 V IEC, 8 A"),
    5.08: dict(ds=_DS_KX508, h=12.2, deep=8.30, extra=10.16, hole=1.60,
               plug="24-12 AWG (2.5 mm²), strip 7-8 mm, 0.4 N·m",
               rating="300 V UL / 320 V IEC, 10 A"),
}


def _tb(refdes: str, board: Board, name: str, pins: tuple[ConnPin, ...],
        parked: bool = False, pitch: float = 3.81, note: str = "") -> Connector:
    """A pluggable screw terminal: a right-angle header at the board edge and a
    screw plug, wired outside the box and pushed in from the side, where the
    stack cannot block a screwdriver."""
    f = _TB_FAMILY[pitch]
    n = len(pins)
    length = round(n * pitch + f["extra"], 2)
    return Connector(refdes, board, name, pins, f["h"], height_confirmed=True,
                     footprint_mm=(length, f["deep"]), pitch_mm=pitch, parked=parked,
                     source=f"{f['ds']} p.1: locking pluggable screw terminal, "
                            f"right-angle header {f['h']:.2f} mm above the board "
                            f"and {f['deep']:.2f} deep, N × {pitch} + {f['extra']:g} = "
                            f"{length:g} mm long over its flanges, ø{f['hole']:.2f} "
                            f"holes. The plug screws to the flanges and takes "
                            f"{f['plug']}. {f['rating']}" + (f". {note}" if note else ""))


def _bus(nets: tuple[str, ...]) -> tuple[ConnPin, ...]:
    return tuple(ConnPin(str(i + 1), n) for i, n in enumerate(nets))


def _stack_pins() -> tuple[ConnPin, ...]:
    """2 × 25: odd = signal, even = GND; the unused odd contacts are spare."""
    pins = []
    for i in range(25):
        sig = _STACK_SIGNALS[i] if i < len(_STACK_SIGNALS) else ""
        pins.append(ConnPin(str(2 * i + 1), sig, "" if sig else "spare"))
        pins.append(ConnPin(str(2 * i + 2), "GND"))
    return tuple(pins)


_INTERBOARD = ("⬜ Connector family unchosen, and the mated pair SETS the board "
               "gap rather than fitting under a ceiling. Samtec ESQ elevated "
               "sockets exist at 11.05 / 13.59 / 16.13 / 18.67 mm bodies only "
               "(esq.pdf); an SLW low-profile socket body is 4.06 mm (slw.pdf). "
               "Height here is a generic 2.54 mm part, unconfirmed")

_CONNECTORS = (
    # ── HVIN ────────────────────────────────────────────────────────────────
    _tb("J101", "HVIN", "B+ / B− harness. The KLKD002 in its FEB-11-11 "
        "holder is UPSTREAM IN THE HARNESS, not a board part", (
            _cp("1", "HV_BPLUS", "84 V tap, downstream of the XT90-S"),
            _cp("2", "GND", "B− to the controller's stud"),
            _cp("3", "GND", "B−, second conductor: one open return cannot push "
                            "the input current through a signal ground"),
        ), pitch=5.08, note="Adjacent positions are rated for the pack, so 84 V "
                            "sits one 5.08 mm pitch from the return (BD-4)"),
    _tb("J102", "HVIN", "Key tap: the key switch's OUTPUT and a return. "
        "The switch, its 2 A fuse and the FarDriver KEY wire are harness", (
            _cp("1", "KSW", "84 V with the key on; ~0.3 mA of gate drive and sense"),
            _cp("2", "GND"),
        ), pitch=5.08, note="As J101: 5.08 mm between KSW and GND (BD-4)"),
    Connector("J104", "HVIN", "HV-LINK, HVIN side: a 2.54 mm header with "
              "alternate pins skipped, 5.08 mm effective (BD-4)",
              _bus(_HVLINK_NETS), 8.5, footprint_mm=(33.0, 2.54),
              leaves_box=False, pitch_mm=5.08, interface="HV-LINK",
              source=_INTERBOARD),
    # ── CONV ────────────────────────────────────────────────────────────────
    Connector("J201", "CONV", "HV-LINK, CONV side (BD-4)", _bus(_HVLINK_NETS),
              2.54, footprint_mm=(33.0, 2.54), leaves_box=False, pitch_mm=5.08,
              interface="HV-LINK", source=_INTERBOARD),
    Connector("J202", "CONV", "PWR-UP, CONV side: 3 × V12, 4 × GND, V5, "
              "KEY_SENSE", _bus(_PWRUP_NETS), 8.5, footprint_mm=(22.86, 2.54),
              leaves_box=False, interface="PWR-UP", source=_INTERBOARD),
    # ── DRV ─────────────────────────────────────────────────────────────────
    _tb("J301", "DRV", "Headlight (M4). ⛔ The assembly's RED lead is unused: "
        "do not land it", (
            _cp("1", "GND", "black — lamp common (M4)"),
            _cp("2", "HL_HIGH", "green — HIGH beam"),
            _cp("3", "HL_LOW", "blue — LOW beam"),
            _cp("4", "HL_DRL", "yellow — DRL"),
        )),
    _tb("J302", "DRV", "Tail + rear signals (M5/M6)", (
        _cp("1", "GND", "black — lamp common (M5)"),
        _cp("2", "TAIL_RUN", "yellow — running, 0.05 A"),
        _cp("3", "TAIL_STOP", "red — STOP, 0.12 A, switched by Q1 in hardware"),
        _cp("4", "TURN_L", "blue — rear LEFT (M6)"),
        _cp("5", "TURN_R", "green — rear RIGHT (M6)"),
    )),
    _tb("J303", "DRV", "Front turn L/R, two isolated 2-wire pairs", (
        _cp("1", "TURN_L", "front LEFT feed"),
        _cp("2", "GND", "front LEFT return. ⬜ M6: confirm the front pair may "
                        "share the tail common"),
        _cp("3", "TURN_R", "front RIGHT feed"),
        _cp("4", "GND", "front RIGHT return"),
    )),
    _tb("J304", "DRV", "Horn (M7)", (
        _cp("1", "AUX12", "⛔ BLUE IS THE POSITIVE"),
        _cp("2", "HORN_N", "black = '-'. ⛔ Red is not the positive"),
    )),
    _tb("J305", "DRV", "Fan + buzzer", (
        _cp("1", "AUX12", "fan +"),
        _cp("2", "FAN_RTN", "fan -, flyback D307"),
        _cp("3", "AUX12", "buzzer +"),
        _cp("4", "BUZZ_RTN", "buzzer -, flyback D314"),
    )),
    _tb("J306", "DRV", "Brake levers. ⬜ GATED ON M3", (
        _cp("1", "LEVER_L", "⬜ M2 identifies the wires in loom '1T3 10'"),
        _cp("2", "GND", "left lever return"),
        _cp("3", "LEVER_R"),
        _cp("4", "GND", "right lever return. ⬜ M3: a 3-wire sensor changes "
                        "this connector's width"),
    )),
    Connector("J307", "DRV", "PWR-UP, DRV side", _bus(_PWRUP_NETS), 8.5,
              footprint_mm=(22.86, 2.54), leaves_box=False,
              interface="PWR-UP", source=_INTERBOARD),
    Connector("J308", "DRV", "STACK, DRV side: 2 × 25, alternating grounds",
              _stack_pins(), 4.06, footprint_mm=(63.5, 5.08),
              leaves_box=False, interface="STACK", source=_INTERBOARD),
    _tb("J309", "DRV", "FarDriver brake/kill: the D23 hardware's own exit, so "
        "BL never passes through BRAIN", (
            _cp("1", "BL", "yellow/green, OUT. ⛔ Not grey BH — High Brake "
                           "stays capped"),
            _cp("2", "ACC_PLUS", "the throttle's 5.1 V, IN — R314's pull-up "
                                 "source"),
            _cp("3", "GND"),
        )),
    _tb("J310", "DRV", "FarDriver one-line in. ⏸️ Footprint fitted, parked "
        "with the display (D19)", (
            _cp("1", "FD_ONELINE", "brown, 0-15 V"),
            _cp("2", "GND"),
        ), parked=True),
    _tb("J405", "DRV", "Display, 9-pin. ⏸️ Footprint fitted, parked with D19", (
        _cp("1", "TT_L", "telltale LEFT, 0-15 V in"),
        _cp("2", "", "display supply. ⏸️ D11 parked: under D19 the dash feeds "
                     "from switched B+ in the harness"),
        _cp("3", "GND", "⛔ NEVER SWITCH PIN 3 / B−: floated, current "
                        "back-feeds through the signal wires"),
        _cp("4", "TT_R", "telltale RIGHT"),
        _cp("5", "TT_HL", "telltale HEADLIGHT"),
        _cp("6", "", "red — 'reserved' on the panel; its five keys are all "
                     "internal (M11)"),
        _cp("7", "CANL", "green-black"),
        _cp("8", "CANH", "red-black — the panel terminates its own end"),
        _cp("9", "DISP_ONELINE", "brown — behind R429's 1 kΩ"),
    ), parked=True),
    # ── BRAIN ───────────────────────────────────────────────────────────────
    Connector("J401", "BRAIN", "USB-C receptacle, USB 2.0: native console and "
              "flashing. Inside the box: a service port", (
        _cp("1", "USB_VBUS", "sensed only — ⚠️ it never feeds the 5 V rail"),
        _cp("2", "USB_CC1"),
        _cp("3", "USB_DP", "D+ (both orientations' pads joined)"),
        _cp("4", "USB_DM", "D− (both orientations' pads joined)"),
        _cp("5", "USB_CC2"),
        _cp("6", "GND"),
        _cp("7", "GND", "shell"),
    ), 3.3, footprint_mm=(9.0, 7.5), leaves_box=False, pitch_mm=0.5,
        source="⬜ Receptacle unchosen: 3.3 mm is the usual 16-pin top-mount "
               "USB-C envelope, unconfirmed. Contacts are listed by function"),
    _tb("J402", "BRAIN", "Left pod: 9-way shell, 8 conductors. The module "
        "carries the MALE half", (
            _cp("1", "GND", "thick green ← the pod's ground bundle (6 wires)"),
            _cp("2", "", "thin green — spare conductor, not connected as built"),
            _cp("3", "IN04A_LOW_WIRE", "thick blue ← pod 'light blue' (IN-04a)"),
            _cp("4", "IN04B_HIGH_WIRE", "thick yellow ← pod 'blue' (IN-04b)"),
            _cp("5", "IN03_HORN_WIRE", "thin blue ← pod 'brown' (IN-03)"),
            _cp("6", "IN01_TURN_L_WIRE", "thin yellow ← pod 'green-black' "
                                         "(turn, IN-01)"),
            _cp("7", "IN09_FLASH_WIRE", "thin red ← pod 'red-gold' (IN-09)"),
            _cp("8", "IN02_TURN_R_WIRE", "thin white ← pod 'green-white' "
                                         "(turn, IN-02)"),
            _cp("9", "IN10_HAZARD_WIRE",
                "thin black ← pod 'green-black' (hazard, IN-10). ⚠️⚠️ A SIGNAL "
                "ON BLACK, ON PURPOSE: mistaken for ground and tied down, both "
                "indicators flash continuously — a loud failure instead of a "
                "silent dead control"),
        )),
    _tb("J403", "BRAIN", "Right pod, 5 conductors. The slider is OFF / A / "
        "A+B, so headlight implies running IN HARDWARE", (
            _cp("1", "GND", "blue — ⛔ GROUND FOR ALL THREE CONTROLS"),
            _cp("2", "IN08A_RUNNING_WIRE", "black — running (IN-08a), closed "
                                           "in slider positions 2 and 3"),
            _cp("3", "IN08B_HEADLIGHT_WIRE", "yellow — headlight (IN-08b), "
                                             "closed in position 3 only"),
            _cp("4", "RUN", "red — run/off toggle; copper straight to STACK "
                            "(BD-7)"),
            _cp("5", "START", "green — start button, a spare sensed input"),
        )),
    _tb("J404", "BRAIN", "FarDriver serial + boost, 5 conductors", (
        _cp("1", "UART1_RX_WIRE", "brown/blue, labelled 'TXD' — ⬜ M9, measure"),
        _cp("2", "UART1_TX_WIRE", "red/black, labelled 'RXD' — ⬜ M9"),
        _cp("3", "", "brown/green = BW5V, 5 V OUT of the controller; unused. "
                     "⚠️ Never feed a 3.3 V-only adapter from it"),
        _cp("4", "GND", "black — serial ground, the reference for every "
                        "measurement"),
        _cp("5", "BOOST_OUT", "CruisePin PIN17, colour unknown. ⛔ METER FIRST"),
    )),
    Connector("J406", "BRAIN", "STACK, BRAIN side: 2 × 25, alternating grounds",
              _stack_pins(), 2.54, footprint_mm=(63.5, 5.08),
              leaves_box=False, interface="STACK", source=_INTERBOARD),
    Connector("J407", "BRAIN", "PWR-UP, BRAIN side", _bus(_PWRUP_NETS), 2.54,
              footprint_mm=(22.86, 2.54), leaves_box=False,
              interface="PWR-UP", source=_INTERBOARD),
    Connector("J408", "BRAIN", "Service header, INTERNAL: recovery without "
              "dismantling the stack (hold IO0 low, pulse EN, flash over UART0)", (
        _cp("1", "EN"),
        _cp("2", "BOOT_IO0"),
        _cp("3", "U0TXD", "GPIO43"),
        _cp("4", "UART2_RX", "U0RXD, GPIO44"),
        _cp("5", "V3P3"),
        _cp("6", "GND"),
    ), 3.0, footprint_mm=(15.24, 2.54), leaves_box=False,
        source="⬜ Part unchosen: a 1 × 6 right-angle 2.54 mm pin header is "
               "~3 mm above the board, unconfirmed"),
    Connector("J409", "BRAIN", "Spare inputs, INTERNAL: expander #2's thirteen "
              "spare bits, each class-A conditioned on the board", (
        _cp("1", "V3P3"),
        _cp("2", "GND"),
        *(_cp(str(n), f"SPARE_{bit[2:]}_WIRE", f"U403.{bit}, class A")
          for bit, n, *_ in _SPARE_LINES),
        _cp("16", "GND"),
    ), 8.5, footprint_mm=(20.32, 5.08), leaves_box=False, dnp=True,
        source="2 × 8 vertical 2.54 mm pin header, the footprint only: fit a "
               "header when a spare is wanted. Every spare is class A (plan §4), "
               "fitted: a 1 kΩ pull-up to 3V3 and an SMS05T1G line on the header "
               "side, 1 kΩ series and 100 nF at the pin. For a dry contact to "
               "ground or 3.3 V logic; nothing above 5 V. LCSC lists it 2.5 mm of body and a "
               "6 mm pin, so 8.5 mm fitted, unconfirmed: below BRAIN's 9.2 mm "
               "terminals"),
)


# ── The LCSC parts JLC places for parts bought by part number ────────────────
# Parts bought by value are in _R_LCSC / _C_LCSC. Chosen with ~/tools/lcsc-search
# on 2026-09-18, JLC Basic first, each checked against the constraints its own
# `source` states (standoff, V_DS, threshold, pinout). mpn -> (LCSC, maker part,
# JLC class, what the check found).
_FAB_BY_MPN = {
    "SMCJ90A": ("C1976063", "Vishay SMCJ90A-E3/57T", "Extended",
                "1.5 kW, V_C 146 V @ 10.3 A; not the 600 W 'SMCJ90A-L'"),
    "SMBJ18A": ("C19077573", "SMBJ18A (R+O)", "preferred Extended",
                "600 W, V_C 29.2 V"),
    "SMS15T1G": ("C894371", "onsemi SMS15T1G", "Extended", "the part itself"),
    "SMF18A": ("C19077512", "SMF18A (hongjiacheng)", "preferred Extended",
               "200 W, V_RWM 18 V, V_BR 20.0-22.1 V, V_C 29.2 V @ 6.8 A"),
    "BZT52B5V1": ("C19077393", "BZT52B5V1 (hongjiacheng)", "preferred Extended",
                  "V_Z 5.0-5.2 V"),
    "SMS05T1G": ("C233428", "onsemi SMS05T1G", "Extended", "the part itself"),
    "USBLC6-2SC6": ("C7519", "ST USBLC6-2SC6", "Extended", "the part itself"),
    "1N4148W": ("C81598", "1N4148W", "Basic", "75 V, silicon"),
    "SS14": ("C2480", "MDD SS14", "Basic", "40 V / 1 A Schottky"),
    "M7": ("C95872", "MDD M7", "Basic", "1000 V / 1 A, 30 A surge"),
    "BZT52B10": ("C22395568", "BZT52B10 (R+O)", "preferred Extended",
                 "V_Z 9.8-10.2 V"),
    "BZT52B15": ("C22395570", "BZT52B15 (R+O)", "preferred Extended",
                 "V_Z 14.7-15.3 V; the 5 % C grade reaches 13.8 V, too near "
                 "the -13.1 V running V_GS"),
    "AO3400A": ("C20917", "AOS AO3400A", "Basic", "the part itself"),
    "AO3407A": ("C15155", "AOS AO3407A", "Extended",
                "±20 V gate; not the Basic AO3401A, whose gate is ±12 V"),
    "BSS127": ("C152611", "Infineon BSS127H6327XTSA2", "Extended",
               "enhancement mode, V_GS(th) 2.6 V max; not the Diodes "
               "BSS127S-7, whose 4.5 V max is above D13_EN at 43 V"),
    "IXTA26P20P-TRL": ("C3291074", "IXYS IXTA26P20P-TRL", "Extended",
                       "DS99913D, the IXTP's die in TO-263"),
    "MCP23017T-E/SS": ("C558584", "Microchip MCP23017T-E/SS", "Extended",
                       "DS20001952D Table 2-1: SSOP, SOIC and SPDIP share pins 1-28"),
    "SN65HVD230DR": ("C12084", "TI SN65HVD230DR", "preferred Extended", "the part itself"),
    "TLV76733DGNR": ("C2873382", "TI TLV76733DGNR", "Extended",
                     "the part itself; stock is thin (34). Pin-compatible fallback "
                     "TLV76701DGNR C3752401 needs an FB divider"),
    "TPS4H160BQPWPRQ1": ("C471053", "TI TPS4H160BQPWPRQ1", "Extended",
                         "version B; never the A version, C485918"),
    "ESP32-S3-WROOM-1U-N8": ("C2980297", "Espressif ESP32-S3-WROOM-1U-N8", "Extended",
                             "-40…+85 °C; never the 65 °C N8R8 / N16R8"),
    "EKXJ221ELL221MM25S": ("C1600234", "Chemi-Con EKXJ221ELL221MM25S", "Extended",
                           "the part itself; through-hole"),
    "PA25V680M8x12": ("C46550437", "JIERR PA25V680M8x12", "Extended",
                      "680 µF 25 V polymer, 20 mΩ; through-hole"),
    "VY2472M49Y5US6": ("C2251831", "Vishay VY2472M49Y5US6TV7", "Extended",
                       "the same series, X1/Y2: reel, kinked 7.5 mm leads"),
    "CGA9N1C0G2J683JT0Y0S": ("C2175506", "TDK CGA9N1C0G2J683JT0Y0S", "Extended",
                             "C0G, 630 V, ±5 %"),
    "0001.2504": ("C1665055", "Schurter 0001.2504", "Extended", "the part itself"),
    "01110501Z": ("C151075", "Littelfuse 01110501Z", "Extended", "5 mm clip with fuse stop"),
}

#: Parts LCSC cannot supply to their constraints: the owner buys them and
#: solders them by hand (owner, 2026-09-18). mpn -> why.
_HAND_BY_MPN = {
    "CN150B110-12/CO": "nothing on LCSC takes 43-160 V in and gives 12 V at "
                       ">= 2.62 A with stock: the TDK brick, in hand",
    "EC7BW-110S05": "the Cincon is in hand; LCSC's nearest 43-160 V 5 V module "
                    "(YLPTEC URB1D05LD-20WR3, C19724292) numbers its pins "
                    "differently and states its isolation two ways",
    "7448022010": "LCSC has none of the Würth choke; its nearest (YDFW1212T, "
                  "C16197255) has 2.4x the DCR and no voltage rating. Two in hand",
}


def _with_fab(parts: tuple[Part, ...]) -> tuple[Part, ...]:
    """Parts with their LCSC part from _FAB_BY_MPN.  An entry no part uses is
    an error: a stale choice would read as a checked one."""
    used = set()
    out = []
    for p in parts:
        fab = None if p.lcsc else _FAB_BY_MPN.get(p.mpn)
        if fab:
            used.add(p.mpn)
            lcsc, maker, cls, check = fab
            p = replace(p, lcsc=lcsc, assembly="jlc",
                        source=f"{p.source}. LCSC {lcsc}: {maker}, JLC {cls}; {check}")
        elif p.mpn in _HAND_BY_MPN:
            used.add(p.mpn)
            p = replace(p, assembly="hand",
                        source=f"{p.source}. HAND-SOLDERED: {_HAND_BY_MPN[p.mpn]}")
        out.append(p)
    stale = (set(_FAB_BY_MPN) | set(_HAND_BY_MPN)) - used
    if stale:
        raise ValueError(f"_FAB_BY_MPN entries no part uses: {sorted(stale)}")
    return tuple(out)


#: Connectors, by refdes: (LCSC, maker part, note), or "hand" and why. The
#: inter-board connectors are absent on purpose: their family is the owner's
#: open decision (docs/esp32-needed-from-owner.md item 6).
_FAB_CONN = {
    "J401": ("C2988369", "G-Switch GT-USB-7010ASV", "USB-C 2.0, 16-pin top mount, "
                                                    "-40…+85 °C"),
    "J408": ("C32713265", "hanxia HX PZ2.54-1x6P WZ", "1 × 6 right-angle, gold"),
    "J409": ("C492425", "XFCN PZ254V-12-16P", "2 × 8 vertical; not fitted, the "
                                             "footprint and the part to fit"),
}


def _with_fab_conn(connectors: tuple[Connector, ...]) -> tuple[Connector, ...]:
    out = []
    for c in connectors:
        fab = _FAB_CONN.get(c.refdes)
        if c.leaves_box:
            header, plug = _TERMINALS[(c.pitch_mm, len(c.pins))]
            c = replace(c, lcsc=header, plug=plug, assembly="jlc",
                        source=f"{c.source}. LCSC {header}: the Kangnex header, JLC "
                               f"Extended; plug LCSC {plug}, ordered loose")
        elif fab and fab[0] == "hand":
            c = replace(c, assembly="hand", source=f"{c.source}. HAND-SOLDERED: {fab[1]}")
        elif fab:
            lcsc, maker, note = fab
            c = replace(c, lcsc=lcsc, assembly="jlc",
                        source=f"{c.source}. LCSC {lcsc}: {maker}, JLC Extended; {note}")
        out.append(c)
    stale = set(_FAB_CONN) - {c.refdes for c in connectors}
    if stale:
        raise ValueError(f"_FAB_CONN entries for no connector: {sorted(stale)}")
    return tuple(out)


def current() -> Design:
    """The design as it stands. The ONE API: `.parts`, `.nets`, `.connectors`
    and the lookups on `Design`. Nothing else builds a Design."""
    return Design(parts=_with_fab(_PARTS), nets=_NETS,
                  connectors=_with_fab_conn(_CONNECTORS))
