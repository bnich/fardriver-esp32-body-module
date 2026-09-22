"""THE DESIGN: every part, net and connector of the three-board set.

Shape lives in `model.py`; this file is content only. `integrity.py` is the
structural gate: every declared pin of every part lands on exactly one net.

Conventions
  REFDES    the hundred a part was FIRST numbered in: POWER 1xx and 2xx ·
            OUTPUTS 3xx · LOGIC 4xx. ⛔ A refdes never changes, not even when
            its part moves board, so the hundreds do NOT partition the boards
            and nothing may read one as if they did. Since the rows were laid
            out, a good many parts sit outside their own hundred -- the
            controller row on POWER is the largest block of them, and it is
            numbered 3xx and 4xx throughout. **Read a part's board off
            `board`**, never off its number. The documents' informal names
            (`D13`, `C1`) are quoted in `source` so they stay greppable.
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
  INTERFACE names the lowest crossing (PWR-OUT and CTRL, below PWR-LOGIC and
            STACK) when a net crosses more than one.
  HEIGHTS   `height_confirmed=True` only where `source` cites the manufacturer
            PDF and the page the figure was read from.
  CONNECTOR pin numbers are a generator-side index -- EXCEPT where the maker
            numbers its own circuits and leaves one out: `PWR-OUT` is a
            five-wide JST wafer carrying 1, 2, 4 and 5, and the hole in that
            numbering is the key, in the netlist and in the copper. For the
            pods the binding key is wire colour + gauge, never the cavity
            number.
  PITCH     the four harness rows (IO-4..IO-6), one row per board face. A screw
            plug seats in ANY header of its own pitch that is at least its
            size, offset if the header is larger, so each group whose mismate
            would DESTROY something owns a pitch nothing else uses:
              7.62  the pack plug (`J101`) alone -- 84 V
              5.08  every FarDriver and display lead alone -- 12 V back-fed
                    into the controller's 3.3 V logic
              3.50  the 5 V outputs alone -- 12 V into a 5 V device
            3.81 is deliberately SHARED by the 12 V outputs and the inputs,
            where the worst mismate is an output into its own current limit, or
            3.3 V through 1 kΩ into a lamp. Beyond that, a terminal carrying a
            safety-relevant wire also keeps a (pitch, positions) SIZE no other
            fitted terminal has, so its plug is left in the hand rather than
            seated offset. `tests/test_rows.py` holds each exclusive pitch to
            its owners; `tests/test_interconnect.py` holds the sizes.
"""
from dataclasses import replace

from .model import Board, ConnPin, Connector, Design, Net, Part, Standoff

#: The three boards, bottom to top: voltage falls with height (BD-1, BD-2).
BOARDS: tuple[Board, ...] = ("POWER", "OUTPUTS", "LOGIC")

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
_DS_WE_3A = "Würth 7448023005 datasheet rev 002.000 (we7448023005.pdf)"
_DS_TDK_OUT = "TDK-Lambda CN50/100/150B110 outline CA952-02-01A (tdk_cn50-150b110_out.pdf)"
_DS_IXYS = "IXYS DS99913D (01/13), IXTA/IXTP26P20P (ixys_ds99913d.pdf)"
_DS_BSS127 = "Infineon BSS127 rev 2.1 (bss127.pdf)"
_DS_SMS = "onsemi SMS05T1/D rev 10 (tvs_onsemi_sms05t1-d.pdf)"
_DS_SMCJ = "Littelfuse SMCJ series datasheet (littelfuse_smcj_series_2025_wayback.pdf)"
_DS_SMF = "SMF series rev 2.2, Zhuhai Hongjiacheng (smf_series_C19077499.pdf)"
_DS_LM736 = "TI SNVSAH5A (ti_lm73605.pdf), LM73605/LM73606"
_DS_TPS2553 = "TI SLVS841F (ti_tps2553.pdf), TPS2552/TPS2553"
_DS_IHLP = "Vishay IHLP-2525CZ-01, rev. 09-Dec-2019 (vishay_ihlp2525cz01.pdf)"
_DS_VY2 = "Vishay doc 28535 (vishay_vy2_series_doc28535.pdf)"
_DS_KXJ = "Chemi-Con KXJ series (kxj.pdf)"
_DS_SPT = "Schurter SPT 5x20 (spt.pdf)"
_DS_KX381 = ("Kangnex WJ15EDGRM-3.81 and WJ15EDGKM-3.81 drawings rev A "
             "(kangnex_15EDGRM-3.81.pdf, kangnex_15EDGKM-3.81.pdf)")
_DS_KX508 = ("Kangnex WJ2EDGRM-5.08 and WJ2EDGKM-5.08 drawings rev A "
             "(kangnex_2EDGRM-5.08.pdf, kangnex_2EDGKM-5.08.pdf)")
_DS_KF762 = ("Cixi Kefa KF2EDGRM-7.62 and KF2EDGKM-7.62 drawings rev A "
             "(kefa_C441304.pdf, kefa_C441154.pdf)")
_DS_KF350 = ("Cixi Kefa KF2EDGRM-3.5 and KF2EDGKM-3.5 drawings rev A "
             "(kefa_C441263.pdf, kefa_C441113.pdf)")
_DS_VH = "JST VH connector series drawing (jst_vh_C594237.pdf)"
_DS_DC3 = ("Zhouri DC3-2.54-*PAS drawing ZR20171018-178 rev A/0 "
           "(zhouri_dc3_C5144580.pdf)")
_DS_HC_PM = ("Hong Cheng HC-PM254-8.5H drawings rev A, 1 of 1 "
             "(hongcheng_pm254_C22373895.pdf, hongcheng_pm254_C42163143.pdf)")
_DS_HC_PZ = ("Hong Cheng HC-PZ254-11.5L-1x9PZ drawing rev A, 1 of 1 "
             "(hongcheng_pz254_C27985193.pdf)")
_DS_BOOM = "BOOMELE PZ2.54-2xNA-11.4MM drawing (boomele_pz254_C2333.pdf)"
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
    ("1k5 1%", "0805"): ("C4310", "UNI-ROYAL 0805W8F1501T5E", 150.0, "Basic"),
    ("3k", "0805"): ("C17661", "UNI-ROYAL 0805W8F3001T5E", 150.0, "Basic"),
    ("12k", "0805"): ("C17444", "UNI-ROYAL 0805W8F1202T5E", 150.0, "Basic"),
    ("470R", "0805"): ("C17710", "UNI-ROYAL 0805W8F4700T5E", 150.0, "Basic"),
    ("2k0 1%", "0805"): ("C17604", "UNI-ROYAL 0805W8F2001T5E", 150.0, "Basic"),
    ("2k2", "0805"): ("C17520", "UNI-ROYAL 0805W8F2201T5E", 150.0, "Basic"),
    ("4k7", "0805"): ("C17673", "UNI-ROYAL 0805W8F4701T5E", 150.0, "Basic"),
    ("10k", "0805"): ("C17414", "UNI-ROYAL 0805W8F1002T5E", 150.0, "Basic"),
    ("20k", "0805"): ("C4328", "UNI-ROYAL 0805W8F2002T5E", 150.0, "Basic"),
    ("27k", "0805"): ("C17593", "UNI-ROYAL 0805W8F2702T5E", 150.0, "Basic"),
    ("47k", "0805"): ("C17713", "UNI-ROYAL 0805W8F4702T5E", 150.0, "Basic"),
    ("100k", "0805"): ("C149504", "UNI-ROYAL 0805W8F1003T5E", 150.0, "Basic"),
    ("180k", "0805"): ("C17501", "UNI-ROYAL 0805W8F1803T5E", 150.0, "preferred Extended"),
    ("240k", "0603"): ("C4197", "UNI-ROYAL 0603WAF2403T5E", 75.0, "preferred Extended"),
    # The 84 V string: 1206, 200 V. No Basic part exists at these values.
    ("1k", "1206"): ("C4410", "UNI-ROYAL 1206W4F1001T5E", 200.0, "Basic"),
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
    ("22nF", 50.0, "0805"): ("C1729", "Samsung CL21B223KBANNNC, X7R", 50.0, "Basic"),
    ("470nF", 16.0, "0805"): ("C13967", "Samsung CL21B474KBFNNNE, X7R", 50.0, "Basic"),
    ("470nF", 35.0, "0805"): ("C13967", "Samsung CL21B474KBFNNNE, X7R", 50.0, "Basic"),
    ("10uF", 16.0, "1206"): ("C13585", "Samsung CL31A106KBHNNNE, X5R", 50.0, "Basic"),
    ("10uF", 25.0, "1206"): ("C13585", "Samsung CL31A106KBHNNNE, X5R", 50.0, "Basic"),
    ("10uF", 35.0, "1206"): ("C13585", "Samsung CL31A106KBHNNNE, X5R", 50.0, "Basic"),
    ("22uF", 16.0, "1206"): ("C12891", "Samsung CL31A226KAHNNNE, X5R", 25.0, "Basic"),
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
       pkg: str = "0805", dnp: bool = False) -> Part:
    """A ceramic chip capacitor, bought by value. `v_max` is the voltage it
    must be rated for; the chosen part's rating (from _C_LCSC) replaces it."""
    fp, h = _C_PKG[pkg]
    lcsc, maker, volts, cls = _C_LCSC.get((value, v_max, pkg), ("", "", v_max, ""))
    return Part(refdes, f"C-{value}", pkg, board, "C", ("1", "2"), h,
                footprint_mm=fp, v_max=volts, lcsc=lcsc, dnp=dnp,
                assembly="jlc" if lcsc else "",
                value=f"{value} {volts:g}V",
                source=source + (_lcsc_note(lcsc, maker, volts, cls) if lcsc else ""))


def _sot23(refdes: str, mpn: str, board: Board, kind: str, v_max: float,
           source: str, height: float = 1.25, confirmed: bool = False) -> Part:
    """A three-lead SOT-23 FET. 1.25 mm is the generic SOT-23 envelope."""
    return Part(refdes, mpn, "SOT-23", board, kind, ("G", "D", "S"), height,
                height_confirmed=confirmed, footprint_mm=(2.9, 2.6),
                v_max=v_max, source=source)


def _tvs15(refdes: str, board: Board, where: str, dnp: bool = False) -> Part:
    """onsemi SMS15T1G, the 15 V quad array for every 12 V-class wire."""
    return Part(refdes, "SMS15T1G", "SC-74", board, "TVS", TVS_ARRAY_PINS, 1.10,
                height_confirmed=True, footprint_mm=(3.1, 3.0), v_max=15.0,
                v_clamp=29.0, dnp=dnp, value="V_RWM 15 V · 24.0 V @ 5 A · 29.0 V @ 12 A",
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
                footprint_mm=(3.9, 1.9), v_max=18.0, v_clamp=29.2,
                value="V_RWM 18 V · V_BR 20.0-22.1 V · V_C 29.2 V",
                source=f"{where}. SMF18A family table: V_RWM 18 V, V_BR 20.0-"
                       f"22.1 V, V_C 29.2 V at 6.8 A, 200 W 10/1000 µs. ⬜ SOD-123FL "
                       f"envelope, not read off a drawing")


def _tvs6(refdes: str, board: Board, where: str) -> Part:
    """SMF6.0A, the single-line clamp for a 5 V AUX output wire (BD-16: the
    stand-off follows the line's idle voltage).  6.0 V clears the buck's
    5.17 V maximum output, where the 5.0 V grade would conduct on it.

    ⚠️ What this clamp does NOT protect is IO-12, the owner's accepted risk,
    and it is stated ONCE -- in the `source` below.  Everything else that
    touches it points here rather than restating it."""
    return Part(refdes, "SMF6.0A", "SOD-123FL", board, "TVS", ("A", "K"), 1.10,
                height_confirmed=True, footprint_mm=(3.9, 1.9), v_max=6.0,
                v_clamp=10.3, value="V_RWM 6.0 V · V_BR 6.67-7.37 V · V_C 10.3 V",
                source=f"{where}. {_DS_SMF} p.2: V_RWM 6.0 V, V_BR 6.67-7.37 V "
                       f"at 10 mA, V_C 10.3 V at 19.4 A (200 W, 10/1000 µs), "
                       f"I_R 400 µA; p.2 outline A = 0.90-1.10 mm high, D = "
                       f"3.60-3.90 over the leads, C = 1.60-1.90 wide, cathode "
                       f"band on the unidirectional part. "
                       f"⚠️⚠️ IO-12, THE ACCEPTED RISK, STATED HERE ONCE: this "
                       f"clamp lets through 10.3 V, and the parts behind it "
                       f"are rated 7 V. No TVS that stands off the buck's "
                       f"5.17 V clamps lower -- silicon clamps at roughly 1.5x "
                       f"its stand-off, and even this family's 5.0 V grade "
                       f"clamps at 9.2 V -- so the owner took the risk rather "
                       f"than the eFuse and six more parts per channel that "
                       f"would close it. ⛔ The exposure is NOT one switch's "
                       f"output: on an ENABLED channel the pass FET is "
                       f"conducting, and {_DS_TPS2553} §9.3.2 p.14 turns it "
                       f"off only after the reverse-voltage comparator's "
                       f"deglitch -- 3-7 ms (p.7) -- with '(V_OUT - V_IN) / "
                       f"r_DS(on)' of reverse current flowing meanwhile. For "
                       f"those milliseconds the surge is on V5AUX, and so on "
                       f"the other three switches' IN pins and the buck's "
                       f"output, every one of them a 7 V part. What the clamp "
                       f"still buys is the size of that surge: without it the "
                       f"wire's full transient arrives instead of 10.3 V. ⛔ "
                       f"Do not 'fix' this by adding OUT to rules.SUPPLY_PINS "
                       f"-- the risk is recorded in the design record, not "
                       f"checked, and the rule would fail a design the owner "
                       f"has already decided")


def _tvs5(refdes: str, board: Board, where: str) -> Part:
    """onsemi SMS05T1G, the 5 V quad array for lines that stay <= 5 V."""
    return Part(refdes, "SMS05T1G", "SC-74", board, "TVS",
                TVS_ARRAY_PINS, 1.10, height_confirmed=True,
                footprint_mm=(3.1, 3.0), v_max=5.0, v_clamp=9.8,
                value="V_RWM 5 V · V_BR 6.0 V min · 9.8 V @ 5 A",
                source=f"{where}. {_DS_SMS}: the SMS05/SMS15 family sheet -- "
                       f"p.1 pads 1/3/4/6 cathode, 2/5 anode, the SMS15T1G's "
                       f"own pinout; p.4 SC-74 A max 1.10 mm. I_R up to 20 uA "
                       f"and ~300 pF per line: harmless on the pod inputs, "
                       f"within the CC spec, 20 mV on a class-A 1 kΩ pull-up, too "
                       f"heavy for CAN (J405 is parked). BOM C2. Spare "
                       f"cathodes tie to GND")


#: Every class-A network built here, as (pull-up, series, cap, net). The board
#: below is a DEFAULT, and `class_a_problems()` is what makes it true: it holds
#: each network to the board of the terminal its own contact arrives on.
_CLASS_A: list[tuple[str, str, str, str]] = []


def _class_a_parts(pull: str, series: str, cap: str, net: str,
                   note: str = "") -> tuple[Part, ...]:
    """plan §4 class A: 1 kΩ pull-up · 1 kΩ series · 100 nF at the pin.

    All of it on LOGIC, because the INPUTS row is LOGIC's edge (IO-4, IO-6):
    every contact from the harness arrives on the board that reads it, so the
    pull-up, the series resistor and the 100 nF at the pin sit together and no
    unconditioned contact crosses an interface.

    ⚠️ That is a default, and `class_a_problems()` checks it against the
    terminal each contact actually lands on -- the guard is in this shared
    function's own class, not at a call site, so an input terminal put on
    another board tomorrow cannot silently get its conditioning an interface
    away. That defect is not hypothetical: the levers had it until IO-6 moved
    J306 into the inputs row.
    """
    board: Board = "LOGIC"
    _CLASS_A.append((pull, series, cap, net))
    tail = f" {note}" if note else ""
    return (
        _r(pull, board, "1k",
           f"Class-A PULL-UP to V3P3 for {net}, on the CONTACT side of the "
           f"series resistor. 1 kΩ, not 4.7 kΩ: 3.3 mA of wetting current "
           f"through a bought switch (plan §4). BOM C1{tail}"),
        _r(series, board, "1k",
           f"Class-A SERIES into the pin for {net} (plan §4). BOM C1{tail}"),
        _c(cap, board, "100nF", 50.0,
           f"Class-A 100 nF to GND at the pin for {net} (plan §4). BOM C1{tail}"),
    )


# ════════════════════════════════════════════════════════════════════════════
# PARTS — POWER (L1): 84 V entry, protection, the D13 module power switch.
# ════════════════════════════════════════════════════════════════════════════
_POWER_ENTRY_PARTS = (
    Part("D101", "SMCJ90A", "DO-214AB (SMC)", "POWER", "TVS", ("A", "K"), 2.62,
         height_confirmed=True, footprint_mm=(8.13, 6.22), v_max=90.0, v_clamp=146.0,
         value="V_R 90 V · V_BR 100-111 V · 146 V @ 10.3 A",
         source=f"B+ to GND at J101. plan §3.2.1, BOM E12 — never SMBJ90A, "
                f"SMBJ100A or 5KP90A. {_DS_SMCJ} p.5: DO-214AB D max 2.62 mm"),
    Part("Q101", "IXTA26P20P-TRL", "TO-263AA (D2PAK)", "POWER", "PFET",
         ("G", "D", "S"), 4.83, height_confirmed=True,
         footprint_mm=(10.41, 15.88), v_max=200.0,
         value="P-ch -200 V, V_GS ±20 V, V_GS(th) -2…-4 V",
         source=f"'D13', the module's high-side power switch: S = HV_BPLUS, "
                f"D = HV_SW. plan §3.2.5, BOM E13; chosen on SOA. At the tap "
                f"current the aux block put on it, the ~50 ms ramp peaks at "
                f"about 195 W, inside DS99913D Fig. 14 at its equal-energy "
                f"pulse width but ABOVE the 70 °C DC line (≈191 W at 84 V): "
                f"the choice now rests on the ramp being a pulse. ⚠️ FIRMWARE "
                f"CONTRACT (IO-16, 2026-09-20): on KEY_SENSE going inactive "
                f"the firmware RELEASES EVERY AUX OUTPUT, within Q101's "
                f"key-off hold (~0.8 s, C107 through R110). This part's SOA "
                f"margin on the key-off decay DEPENDS ON THAT: shed, the tap "
                f"is ~0.63 A and Q101 carries ~53 W against the 138 W derated "
                f"DC line; held on through the decay it is ~162 W, over it. "
                f"tools/soft_start.py has every figure and gates on the shed "
                f"case. "
                f"{_DS_IXYS}: one sheet for the IXTA "
                f"(TO-263) and IXTP (TO-220) -- one die, one SOA, so "
                f"tools/soft_start.py holds for either. p.3 TO-263 outline: A "
                f"max 4.83 mm, E 10.41, L 15.88. The IXTA because JLC can "
                f"reflow it (LCSC C3291074, the IXTP has none in stock); "
                f"fallback: the IXTP26P20P, hand-soldered. ⚠️ The tab is the "
                f"drain (HV_SW, 84 V): board copper at 84 V -- keep "
                f"clearance to every other net, and no metal under it"),
    _r("R110", "POWER", "100k",
       "Q101 gate to SOURCE — the D14 bias-OFF: V_GS = 0 with the key off. "
       "With R101A/B (540 kΩ) it sets V_GS = -13.1 V at 84 V, -9.4 V at 60 V, "
       "-6.7 V at 43 V. BOM D9"),
    Part("D102", "BZT52B15", "SOD-123", "POWER", "ZENER",
         ("A", "K"), 1.35, footprint_mm=(3.7, 1.6), v_max=15.0, value="15V",
         source="Q101 gate clamp inside the ±20 V V_GS rating: anode = gate, "
                "cathode = source. Never conducts in normal running (-13.1 V). "
                "BOM E13 '+ zener'. The 2 % B grade: a C grade can clamp at "
                "13.8 V. ⬜ SOD-123 height not read off a drawing"),
    Part("C105", "CGA9N1C0G2J683JT0Y0S", "2220 C0G", "POWER",
         "C", ("1", "2"), 2.3, footprint_mm=(5.7, 5.0), v_max=630.0,
         value="68nF C0G 630V",
         source="Q101 gate to DRAIN: the Miller cap that sets the output slew, "
                "≈55 ms at 84 V: I = (84 - V_pl)/540 k - V_pl/100 k ≈ 0.105 mA at a "
                "4.3 V plateau, t = 84 V × 68 nF / I (plan §3.2.5). It holds "
                "the full pack with the switch off and 146 V at D101's clamp, "
                "hence ≥250 V; C0G or film because X7R loses half its value at "
                "that bias, exactly where SOA stress peaks. ⚠️ LAYOUT: a 2220 "
                "cracks under board flex, and shorted it holds Q101 on with the "
                "key off -- keep it away from the mounting holes and the board "
                "edges (firmware also flags 'powered with KEY_SENSE low')"),
    _c("C107", "POWER", "4.7uF 50V X7R", 50.0,
       "Q101 gate to SOURCE. Divides the dV/dt that C105 couples into the gate "
       "when the XT90-S is plugged in with the key OFF: 84 V × 68n/(68n+4.7µ) "
       "≈ 1.2 V nominal, under V_GS(th) min 2.0 V. ⚠️ The margin is thin at the "
       "corners (−1.64 … −1.98 V across tolerance, temperature and OVP), and a "
       "Y5V/25 V part loses most of its capacitance under bias and cold -- so "
       "X7R, 50 V: it sees ≤15 V (D102) and keeps its value", pkg="1206"),
    _r("R101A", "POWER", "270k",
       "Upper half of the 540 kΩ gate pull-down string (Q101 gate → Q105). "
       "A series pair for voltage rating: ~35 V each running, 73 V each at "
       "D101's 146 V clamp", pkg="1206"),
    _r("R101B", "POWER", "270k",
       "Lower half of the 540 kΩ gate pull-down string, into Q105's drain",
       pkg="1206"),
    _sot23("Q105", "BSS127", "POWER", "NFET", 600.0,
           f"The level shifter that turns Q101 ON: D = D13_PD, S = GND, "
           f"G = D13_EN. Key on ⇒ D13_EN ≈ 7.6 V ⇒ Q105 pulls the 540 kΩ "
           f"string to GND. Key off ⇒ D13_EN = 0 ⇒ no DC path off Q101's gate "
           f"and zero quiescent drain. {_DS_BSS127}: p.1 600 V, ENHANCEMENT "
           f"mode, logic level (V_GS(th) 1.4-2.6 V); p.8 SOT-23 1.1 mm max",
           height=1.1, confirmed=True),
    _r("R112A", "POWER", "499k",
       "Upper half of the 1 MΩ feed from KSW to Q105's gate. A series pair for "
       "voltage rating", pkg="1206"),
    _r("R112B", "POWER", "499k",
       "Lower half of the 1 MΩ feed from KSW to Q105's gate. With R113: "
       "84 V → 7.6 V, 60 V → 5.5 V, 43 V → 3.9 V, all over V_GS(th) 2.6 V max",
       pkg="1206"),
    _r("R113", "POWER", "100k",
       "Q105 gate to GND — the D14 bias-OFF: key off or J101 unplugged ⇒ "
       "Q105 off ⇒ Q101 off"),
    Part("D106", "BZT52B10", "SOD-123", "POWER", "ZENER",
         ("A", "K"), 1.35, footprint_mm=(3.7, 1.6), v_max=10.0, value="10V",
         source="Q105 gate clamp, D13_EN to GND, inside the BSS127's ±20 V "
                "V_GS. The node runs at 7.6 V, so it conducts only on a "
                "transient. The 2 % B grade. ⬜ SOD-123 height not read off a "
                "drawing"),
    _c("C108", "POWER", "100nF", 50.0,
       "D13_EN to GND: key-contact bounce filter, τ ≈ 9 ms with R112A/B ‖ R113"),
    _r("R107", "POWER", "165k",
       "IN-12 divider top, upper half, fed from KSW. 330 kΩ / 10 kΩ gives "
       "84 V → 2.47 V (plan §3.1.3); 2 × 165 k because plan §4 class B wants a "
       "series pair for voltage rating (40.8 V and 10 mW each). BOM E14",
       pkg="1206"),
    _r("R108", "POWER", "165k",
       "IN-12 divider top, lower half — series partner of R107", pkg="1206"),
    _r("R109", "POWER", "10k", "IN-12 divider bottom. 84 V → 2.47 V. BOM E14"),
    _c("C109", "POWER", "100nF", 50.0,
       "At the divider: holds the KEY_SENSE node low-impedance at its source "
       "before it crosses three boards. τ ≈ 1 ms with R109. The HDG's 0.1 µF "
       "at the ESP pin is C437"),
    Part("L101", "7448023005", "THT common-mode choke, vertical", "POWER",
         "CMCHOKE", ("1", "2", "3", "4"), 22.0, height_confirmed=True,
         footprint_mm=(18.0, 14.0), value="5 mH · 3 A @ 70 °C · 300 V AC",
         source=f"DC-DC #1's input filter, ahead of its bulk cap. FOUR "
                f"terminals, windings 1-4 and 2-3: HV_SW → 1→4 → HV_C1_P, "
                f"HV_C1_N → 3→2 → GND, so the DC currents cancel in the core. "
                f"⚠️ RATED FOR THE AUX LOAD, not for inductance (IO-13): with "
                f"all eight aux outputs at 1 A this winding carries 1.88 A at "
                f"the 60 V LVC (tools/power_budget.py), which the 2 A Type S "
                f"on L102 would meet at 94 % of its rating. {_DS_WE_3A} p.1: "
                f"3 A at 70 °C, 40 mΩ max, 300 V AC, 2100 V AC test; 22,0 max "
                f"tall, 18,0 max wide, 14,0 max deep; pins 3,5 ± 0,5 below the "
                f"body — every dimension the footprint and the envelope depend "
                f"on is identical to {_DS_WE} p.1's, so it is a drop-in and "
                f"shares its land pattern. ⚠️ ONE callout on the two front "
                f"views differs: the 3,2 core-gap dimension is '3,2 max.' on "
                f"the 2 A 7448022010 and '3,2 min.' on this 3 A 7448023005. It "
                f"sits inside the 18,0 max width and touches neither the pads "
                f"nor the height, so the shared land pattern stands. "
                f"⚠️ 5 mH (+50/−30 % at 10 kHz) is HALF the inductance of the "
                f"part on L102: TDK's manual "
                f"({_DS_TDK} p.6-8) asks for a choke on each supply input and "
                f"states NO inductance figure, so 10 mH was this project's own "
                f"choice and neither value is tested for interference — the "
                f"owner accepted that (IO-13), and no Type S part carries "
                f"≥ 3 A with ≥ 10 mH. ⬜ Confirm at the EMI measurement",
         lead_mm=4.0),
    Part("L102", "7448022010", "THT common-mode choke, vertical", "POWER",
         "CMCHOKE", ("1", "2", "3", "4"), 22.0, height_confirmed=True,
         footprint_mm=(18.0, 14.0), value="10 mH · 2 A @ 70 °C · 300 V AC",
         source=f"DC-DC #2's input filter: HV_SW → 1→4 → HV_C2_P, "
                f"HV_C2_N → 3→2 → GND. Still the 10 mH / 2 A Type S where "
                f"L101 is the 3 A part: this one feeds the Cincon alone, whose "
                f"3 W draws 0.05 A at the 60 V LVC — 2.5 % of the rating, "
                f"against L101's 94 % (IO-13). {_DS_WE} p.1: 22,0 max tall, "
                f"pins 3,5 ± 0,5. BOM E7", lead_mm=4.0),
)

# ════════════════════════════════════════════════════════════════════════════
# PARTS — POWER (L1), continued: both converters. Each converter's −Vin is its own net and
# reaches GND only through its choke winding; −Vout IS GND (isolated bricks).
# ════════════════════════════════════════════════════════════════════════════
_POWER_CONVERTER_PARTS = (
    Part("U201", "CN150B110-12/CO", "quarter brick 58.3 × 37.2 × 12.7 mm",
         "POWER", "CONVERTER",
         ("-Vin", "CNT", "+Vin", "-V", "-S", "+S", "+V", "BASEPLATE"), 12.7,
         height_confirmed=True, footprint_mm=(58.3, 37.2), nc=("TRM",),
         v_max=160.0, value="43-160 V → 12 V / 12.5 A, isolated", side="bottom",
         source=f"DC-DC #1, the load rail. BOM E1. ⚠️ UNDERSIDE: the brick is "
                f"conduction-cooled and its baseplate bolts to the box floor "
                f"through a thermal pad, which is the heatsink. The board's "
                f"height above the floor is measured from this seat "
                f"(`board_params.FLOOR_SEAT`), so nothing else on this face may "
                f"hang deeper than it does. {_DS_TDK} p.5 pins: 1 -Vin, "
                f"2 CNT, 3 +Vin, 4 -V, 5 -S, 6 TRM, 7 +S, 8 +V; 'Base-plate can "
                f"be connected to FG by M3 threaded holes' = pin BASEPLATE, "
                f"which reaches board copper at the two ø7.0 FG lands (p.24 "
                f"§(3) 'Mounting Holes on Printed Circuit Board'): the screw's "
                f"washer on the land IS the contact -- the brick has no "
                f"baseplate pin of its own. {_DS_TDK_OUT} note B: the /CO model carries 2 × M3 "
                f"THREADED holes 'for customer chassis mounting (FG)'. They "
                f"were BD-9's plate screws; under BD-27 they are the floor "
                f"bolts. ⬜ UNCONFIRMED, and needed before the floor is "
                f"drilled: the drawing gives no thread DEPTH and does not say "
                f"whether the holes pass through the case, so whether one "
                f"screw can both seat the FG land's washer at the board and "
                f"reach the floor -- or whether the two jobs take two screws "
                f"into one thread from opposite ends -- is open. Ask TDK for "
                f"the thread depth, or measure the brick. ⬜ And the bolt "
                f"heads: outside the floor, or in a counterbore in the 3.0 mm "
                f"floor allowance -- an enclosure decision, with the model. "
                f"p.18 CNT is negative logic, 'H Level or Open → OFF'; 'When "
                f"ON/OFF control function is not used, CNT terminal should be "
                f"shorted to -Vin terminal'. p.17 'short +S terminal to +V "
                f"terminal and -S terminal to -V terminal' -- ⚠️ LAYOUT: strap "
                f"them AT the brick's pins, never through J202 or another board, "
                f"so a connector cannot open the sense loop. nc TRM: p.6 "
                f"Fig.6-1 draws it open and p.10 §7-2 adjusts only 'by "
                f"external resistor'. {_DS_TDK_CAT} p.3: 58.3 × 37.2 × 12.7 mm. "
                f"{_DS_TDK_OUT} p.1 note F: pins 5 ± 0.5 below the case, ø1.0 "
                f"and ø1.5 -- too stiff to trim after soldering. "
                f"⚠️ 160 V is a hard ceiling, transients included", lead_mm=5.5),
    Part("U202", "EC7BW-110S05", "2 × 1 in. THT module", "POWER", "CONVERTER",
         ("+Vin", "-Vin", "+Vout", "-Vout"), 10.7, height_confirmed=True,
         footprint_mm=(50.8, 25.4), nc=("Trim", "Remote"), v_max=160.0,
         value="43-160 V → 5 V / 4 A, 3 kV isolation", side="bottom",
         source=f"DC-DC #2, the logic rail. BOM E2. UNDERSIDE, beside U201: at "
                f"10.7 mm it stands clear under the brick's 12.7 mm seat, so it "
                f"rides the same face without lifting the board off the floor. "
                f"{_DS_CINCON} p.7 pins: "
                f"1 +V Input, 2 -V Input, 3 +V Output, 4 Trim, 5 -V Output, "
                f"6 Remote On/Off; 50.8 × 25.4 × 10.2 mm ±0.5, booked at the "
                f"10.7 mm maximum. nc Remote: p.3 positive logic, 'Pin open=On'. "
                f"nc Trim: p.2 'Output Voltage Trim Range' ±10 % is an "
                f"optional external-resistor adjustment; open = nominal 5 V. "
                f"p.7: pins '0.22 min. [5.6]', no maximum: TRIM them to leave "
                f"≤ 1.5 mm through POWER before soldering"),
    Part("C201", "EKXJ221ELL221MM25S", "radial can 18 × 25 mm, lying down",
         "POWER", "C", ("+", "-"), 18.5, height_confirmed=True,
         footprint_mm=(18.5, 29.6), v_max=220.0, side="top",
         value="220uF 220V",
         source=f"'C1': TDK's input bulk across HV_C1_P / HV_C1_N at U201's "
                f"terminals ({_DS_TDK} p.7: ≥100 µF, KXJ class). TOP FACE, "
                f"lying down and bonded (BD-14): the underside is the brick's "
                f"seat and nothing there may hang deeper than it, while on top "
                f"an 18.5 mm can lies well under the chokes' 22 mm. "
                f"{_DS_KXJ} p.1: φD' = φD + 0.5 "
                f"max = 18.5 mm, L' = L + 1.5 max = 26.5 mm. BOM E8"),
    Part("C202", "EKXJ221ELL221MM25S", "radial can 18 × 25 mm, lying down",
         "POWER", "C", ("+", "-"), 18.5, height_confirmed=True,
         footprint_mm=(18.5, 29.6), v_max=220.0, side="top",
         value="220uF 220V",
         source=f"'C2': hold-up across U202's ±Vin, BEHIND D201 and F201. "
                f"⚠️ Not interchangeable with C1: on the common node ride-out "
                f"collapses from ~237 ms to ~20 ms (plan §3.2.2). TOP FACE, "
                f"lying down and bonded, as C1 (BD-14). {_DS_KXJ} p.1: 18.5 mm. "
                f"BOM E8"),
    Part("C203", "VY2472M49Y5US6", "radial disc, lying FLAT", "POWER", "C",
         ("1", "2"), 5.0, height_confirmed=True, footprint_mm=(12.5, 18.5),
         v_max=1000.0, value="4700pF Y2 1000VDC",
         source=f"HV_C1_P to BASEPLATE at U201's terminals ({_DS_TDK} p.8 "
                f"C2/C3: 4700 pF). {_DS_VY2} p.2: D max 12.5, T max 5.0 mm — "
                f"FLAT it is 5.0 mm where upright it is 15.5-16.5; p.1 "
                f"1000 VDC, IEC 60384-14 Y2; leads ø0.6, 7.5 mm apart (the "
                f"'…TV7' reel). BOM E9"),
    Part("C204", "VY2472M49Y5US6", "radial disc, lying FLAT", "POWER", "C",
         ("1", "2"), 5.0, height_confirmed=True, footprint_mm=(12.5, 18.5),
         v_max=1000.0, value="4700pF Y2 1000VDC",
         source=f"HV_C1_N to BASEPLATE. {_DS_VY2} p.2: T max 5.0 mm. BOM E9"),
    Part("C205", "VY2472M49Y5US6", "radial disc, lying FLAT", "POWER", "C",
         ("1", "2"), 5.0, height_confirmed=True, footprint_mm=(12.5, 18.5),
         v_max=1000.0, value="4700pF Y2 1000VDC",
         source=f"U202 +Vin (HV_C2_HOLD) to BASEPLATE. {_DS_VY2} p.2: T max "
                f"5.0 mm. BOM E9"),
    Part("C206", "VY2472M49Y5US6", "radial disc, lying FLAT", "POWER", "C",
         ("1", "2"), 5.0, height_confirmed=True, footprint_mm=(12.5, 18.5),
         v_max=1000.0, value="4700pF Y2 1000VDC",
         source=f"HV_C2_N to BASEPLATE. {_DS_VY2} p.2: T max 5.0 mm. BOM E9"),
    Part("C207", "PA35V680M10x15", "radial polymer 10 × 15 mm, lying down",
         "POWER", "C", ("+", "-"), 10.5, height_confirmed=True,
         footprint_mm=(10.5, 19.1), v_max=35.0,
         value="680uF 35V polymer, 16 mΩ",
         source=f"U201 +V to -V. {_DS_TDK} p.9 Table 6-1: '12,15V: 25V 680μF "
                f"(Solid Cap.)', 'For stable operation' (Chemi-Con PSG class). "
                f"35 V, not 25: D315 clamps V12 at up to 29.2 V, over a 25 V "
                f"part's rating (rules VR-CLAMP). JIERR PA series "
                f"(jierr_pa25v680m8x12.pdf) p.7: PA35V680M10X15, 680 µF, 16 mΩ, "
                f"4.1 A ripple, -55…105 °C; p.2: φD + 0.5 max = 10.5 mm, "
                f"L + α = 16 mm, F 5.0, ø0.6 leads. LYING DOWN: 10.5 mm "
                f"against the 16 mm it stands at upright. ⚠️ With BD-9's plate "
                f"withdrawn nothing on POWER's top face holds it to 10.5 any "
                f"more -- the 22 mm chokes set that gap -- so this is headroom, "
                f"not a ceiling. It stays lying and bonded like the bulk cans "
                f"(BD-14): a 16 mm can standing on its leads is the shock path "
                f"the lying ones were chosen to avoid"),
    _c("C208", "POWER", "2.2uF", 25.0,
       f"U201 +V to -V. {_DS_TDK} p.8 C6: 2.2 µF ceramic against output spike "
       f"noise", pkg="1206"),
    _c("C209", "POWER", "22nF", 250.0,
       f"U201 +V to BASEPLATE, close to the terminal. {_DS_TDK} p.8 C4/C5: "
       f"0.022 µF. 250 V so it survives BASEPLATE lifted to the 84 V rail by a "
       f"shorted Y2 with R211 open", pkg="1206"),
    _c("C210", "POWER", "22nF", 250.0,
       f"U201 -V to BASEPLATE. {_DS_TDK} p.8 C4/C5: 0.022 µF. Rated as C209",
       pkg="1206"),
    _c("C211", "POWER", "10uF", 16.0, "U202 output bulk, V5 to GND", pkg="1206"),
    _c("C212", "POWER", "100nF", 50.0, "U202 output HF decoupling, V5 to GND"),
    Part("D201", "M7", "DO-214AC (SMA)", "POWER", "D", ("A", "K"), 2.44,
         footprint_mm=(5.3, 2.9), v_max=1000.0,
         source=f"Hold-up blocking diode, HV_C2_P → HV_C2_HOLD_IN. Plain "
                f"silicon (plan §3.2.6): the SMA 1N4007, 1000 V / 1 A, 30 A "
                f"surge; it is in series with the LOGIC rail ALONE, so it "
                f"carries U202's input current and not the module's tap -- "
                f"3 W at its 43 V input floor is 0.07 A, a 14x margin on the "
                f"1 A. The DO-41 1N4007 (BOM E10) is the breadboard's. "
                f"⬜ SMA envelope 2.44 mm, not read off a drawing"),
    Part("FH201", "01110501Z", "5 × 20 fuse holder: two PCB clips", "POWER",
         "FUSECLIP", ("1", "2"), 7.1, footprint_mm=(22.6, 5.2),
         value="2 × Littelfuse 01110501Z",
         source="F201's holder: BOTH clips in one footprint, their 17.8 mm "
                "fixed in copper. Pin 1 is the input-end clip, pin 2 the "
                "output-end; the clips do not conduct to each other, the fuse "
                "does. ⛔ Not the in-hand Schurter FAC 0031.3803: that is a "
                "47.5 mm VERTICAL holder. The DC interrupting duty is the "
                "fuse's, not the clip's. Littelfuse 01110501Z (111 501): 5 mm "
                "clip with fuse stop, 10 A; catalogue body 7.1 mm tall, 4.8 × "
                "3.8 mm, rows 17.8 mm apart for 5 × 20. ⬜ seated height to "
                "confirm on a real part"),
    Part("F201", "0001.2504", "5 × 20 ceramic, in the holder FH201", "POWER",
         "FUSE", ("1", "2"), 8.0, footprint_mm=(5.2, 20.0), v_max=300.0,
         value="1A T-lag 300VDC",
         source=f"DC-DC #2's input fuse (Cincon: 1 A time-delay). ⛔ Order by "
                f"part number: FST and SP have NO DC rating. {_DS_SPT} p.2: "
                f"ø 5.2 × 20 mm; 8.0 mm assumes a ≤2.8 mm clip seat. BOM E11"),
    Part("R211", "NET-TIE", "copper net-tie, ≥2 mm wide", "POWER", "R", ("1", "2"),
         0.04, footprint_mm=(4.0, 2.0), value="0R",
         source="Tie BASEPLATE → GND. A shorted Y2 puts the pack on U201's "
                "BASEPLATE, and BD-27 bolts that baseplate to the box floor, "
                "so the metal of the box goes with it: the fault has to blow "
                "the harness KLKD003, never leave touchable metal sitting at "
                "84 V. COPPER, not a chip jumper: the prospective current is "
                "~200 A, and this tie carries every amp of it until the tap "
                "fuse clears. The KLKD003 melts at 7.8 A²s "
                "(littelfuse_klkd.pdf p.2, Average Melting I²t) -- about "
                "200 µs at 200 A. A 1206 0 Ω link publishes no fusing I²t at "
                "all, only a continuous rating in the low amps: nothing says "
                "it lasts those 200 µs, and a tie that opens before the fuse "
                "leaves the baseplate floating at 84 V, the exact fault it "
                "exists to prevent. A 2 mm strip of board copper is the one "
                "conductor here whose survival is not in question. "
                "⚠️ NOT a proven single-point tie any "
                "more: bolted to a floor the box bonds to ground, BASEPLATE "
                "reaches GND through the chassis as well as through R211, so "
                "the fault splits between them and the two paths enclose a "
                "loop. ⬜ OPEN with the enclosure: bring the box's bond and "
                "this tie to the SAME point, or state which one carries the "
                "fault. The old wording called R211 the single point; with a "
                "bonded box bolted to the baseplate that is no longer true"),
)

# ════════════════════════════════════════════════════════════════════════════
# PARTS — POWER (L1), continued: the CONTROLLER ROW (IO-5, IO-6). Every wire to
# the FarDriver and the parked display leaves from POWER's edge, and each one's
# driver, divider, series resistor and clamp sits here with its connector, so
# nothing unconditioned crosses an interface: commands and sense nodes cross
# CTRL, and nothing else --
#   ⚠️ except the three TELLTALES, deliberately. TT_L, TT_R and TT_HL are fed
#   from the lamp channels themselves (plan §6.2.1: a flash lights the headlight
#   telltale with no firmware running), so their 1 kΩ series resistors have to
#   stay on OUTPUTS with those feeds. What crosses CTRL is the far side of a
#   1206 that limits a shorted display wire to 144 mW (VR-POWER), clamped at the
#   connector by D406. Moving the resistors here instead would put the raw lamp
#   feed on the crossing, which is the thing this row exists to prevent.
# The refdes hundreds are the boards these parts came from (see REFDES above)
# -- a refdes never changes when a part moves board.
# ════════════════════════════════════════════════════════════════════════════
_POWER_CTRL_PARTS = (
    # ── the motor cut: an open-drain output at J309 (IO-8, IO-9) ─────────────
    _sot23("Q106", "AO3400A", "POWER", "NFET", 30.0,
           "BL, the FarDriver's low-brake input, pulled low = motor cut. "
           "Firmware-driven (IO-8) from GPIO16; the hard gate pull-down R115 "
           "keeps it RELEASED from reset until firmware drives it (IO-9). On "
           "POWER with J309, where BL leaves the box"),
    _r("R114", "POWER", "100R",
       "BL gate series (plan §6.2.3), as R310-R312 and R424. With R115 it is "
       "also the gate DIVIDER, and that is what has to switch the cut: "
       "3.3 V × 10k / (100R + 10k) = 3.27 V, over the AO3400A's specified "
       "V_GS of 2.5 V (rule GATE-VGS). BOM D9"),
    _r("R115", "POWER", "10k",
       "BL gate HARD pull-down: released at reset, through boot and whenever "
       "the firmware is not running (IO-9, D14). 10 kΩ against R114's 100 Ω "
       "leaves 3.27 V of gate drive (GATE-VGS). ⛔ It stays on this board with "
       "Q106: a pull-down behind a connector is a guarantee a bad contact can "
       "take away, and this one is what keeps the bike driving"),
    _r("R336", "POWER", "100k",
       "BL → BL_SENSE: the copy firmware reads back, so a cut that did not take "
       "and one that will not release both show up. ⚠️ The cut itself is a "
       "firmware output now (IO-8), so this is a readback, not an isolation "
       "barrier. ⚠️ AND ITS RISK HAS INVERTED: under D23 a spurious pull here "
       "moved BL toward a cut, which was the safe direction; under IO-9 the "
       "bike is meant to drive whenever the firmware is not running, so this "
       "is the ONE copper path on the module that can work against IO-9. A "
       "fitted but unpowered LOGIC, or an expander pin left as an output, "
       "clamps BL_SENSE near 0.5 V and puts 100 kΩ from BL to ground. That only "
       "cuts if the FarDriver's own BL pull-up is 47 kΩ or weaker, which is "
       "⬜ UNMEASURED — the 100 kΩ is the whole margin, so it may only ever go "
       "up, never down"),
    _r("R343", "POWER", "100k",
       "ACC+ sense divider, top. The throttle's 5.1 V supply is a sensor only "
       "(IO-8): nothing on the module is powered from it, and firmware reads it "
       "to tell a live FarDriver from a dead one. 5.1 V × 180/280 = 3.28 V at "
       "the expander pin (V_IH 2.64 V)"),
    _r("R344", "POWER", "180k", "ACC+ sense divider, bottom (with R343)"),
    # ── the FarDriver serial pair and the boost output at J404 ───────────────
    _r("R436", "POWER", "1k",
       "UART1 TX series (plan §4 class E); the pin is tri-stated whenever the "
       "module is not sending. On POWER with J404: the harness wire meets a "
       "resistor on the board it arrives on, and only the 3.3 V logic node "
       "crosses CTRL"),
    _r("R443", "POWER", "1k",
       "UART1 RX series (plan §4 class E): the FarDriver's TX level is "
       "unmeasured (⬜ M9), so the harness wire never meets GPIO18 directly. On "
       "POWER with J404, as R436"),
    _sot23("Q401", "AO3400A", "POWER", "NFET", 30.0,
           "Boost open-drain output to the controller's CruisePin. ⛔ METER THE "
           "WIRE FIRST: the same 30-pin harness carries pink 60VC at 72-84 V; "
           "above 15 V (D407's stand-off) the module needs a PC817 opto "
           "instead of this FET. BOM D3"),
    _r("R424", "POWER", "100R", "Boost gate series (plan §6.2.3). BOM D9"),
    _r("R425", "POWER", "10k",
       "Boost HARD external pull-down (plan §3.1.1). D14: the gate biases OFF "
       "through the ~200 ms of high-Z at boot, and on POWER with Q401, so no "
       "contact of CTRL stands between the gate and its pull-down. BOM D9"),
    _r("R429", "POWER", "1k",
       "Series in the one-line feed to display pin 9: back-feed protection "
       "while the FarDriver drives 0-15 V into an unpowered display "
       "(plan §3.3). Between J310 and J405, both on this board, so the "
       "controller's 0-15 V one-line never crosses an interface. 1206 as R426. "
       "BOM B3", pkg="1206"),
    # ── one clamp per connector of the row, on the row's own board (PROT) ────
    _tvs15("D316", "POWER", "At J309: BL and ACC+"),
    _tvs15("D317", "POWER", "At J310: FD_ONELINE, 0-15 V. ⏸️ DNP with the "
           "parked display (D19)", dnp=True),
    _tvs5("D404", "POWER", "At J404: the two FarDriver serial wires (K1, K3)"),
    _tvs15("D407", "POWER",
           "At J404: BOOST_OUT, whose controller-side pull-up must meter "
           "≤ 15 V before the wire is connected (plan §7.1): the 15 V array"),
    _tvs15("D406", "POWER", "At J405: TT_L, TT_R, TT_HL, DISP_ONELINE. ⏸️ DNP "
           "with the parked display (D19); populate-and-go", dnp=True),
    _tvs5("D405", "POWER", "At J405: CANH, CANL"),
)

# ════════════════════════════════════════════════════════════════════════════
# PARTS — OUTPUTS (L2): the 12 V drivers, whose channels are the 12 V row
# (IO-4). ⚠️ 40 V parts: the 12 V rail only, never the 84 V node.
# There is no brake or kill circuit here: every channel is plain I/O (IO-8).
# The motor cut, the FarDriver links and the display block sit on POWER with
# the connectors they serve (IO-5); only R426-R428 stay, because the telltale
# feeds they tap are the lamp channels here.
#   U301: IN1 AUX12 · IN2 HL_LOW · IN3 HL_HIGH · IN4 HL_DRL
#   U302: IN1 TAIL_RUN · IN2 TURN_L · IN3 TURN_R · IN4 TAIL_STOP
#   U303: IN1-4 the four 12 V aux outputs (IO-1), on expander #3
# The 5 V row is here too, under the board: a buck of its own and four
# current-limited load switches (IO-1, IO-2).
# ════════════════════════════════════════════════════════════════════════════
_MCP_SOURCE = (
    f"{_DS_MCP} p.11 Table 2-1 (one column for SSOP, SOIC and SPDIP): GPB0-7 1-8 · VDD 9 · VSS 10 · NC 11 · "
    f"SCK 12 · SDA 13 · NC 14 · A0-A2 15-17 · RESET 18 · INTB 19 · INTA 20 · "
    f"GPA0-7 21-28. A0-A2 and RESET 'Must be externally biased'. ⛔ GPA7 and "
    f"GPB7 are 'Output only (MCP23017)' and carry nothing. nc NC11/NC14: 'NC "
    f"(MCP23017)'. nc INTB: p.20 'When MIRROR = 1, the INTn pins are "
    f"functionally OR'ed', so INTA alone reports both ports. Firmware drives "
    f"GPA7/GPB7 as outputs (p.18), so neither floats; every input bit has an "
    f"external pull. p.35 (drawing C04-073): SSOP-28 A 2.00 mm max, D 10.50, "
    f"E 8.20. 400 kHz at 3.3 V. BOM C3")


_TPS_PINS = ("GND", "IN1", "IN2", "IN3", "IN4", "SEH", "SEL", "FAULT", "CS",
             "CL", "THER", "DIAG_EN", "OUT1", "OUT2", "OUT3", "OUT4", "VS",
             "PAD")


def _tps4h160(refdes: str, role: str) -> Part:
    return Part(refdes, "TPS4H160BQPWPRQ1", "28-HTSSOP PowerPAD, 0.65 mm",
                "OUTPUTS", "IC", _TPS_PINS, 1.2, height_confirmed=True,
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
    return _r(refdes, "OUTPUTS", "4k7",
              f"Series protection in {signal}, MCU side of the TPS4H160B pin. "
              f"{_DS_TPS} p.26: 'TI recommends serial resistors to protect the "
              f"microcontroller, for example, 4.7-kΩ when using a 3.3-V "
              f"microcontroller'; plan §6.2.2a's 3.15 V drive figure assumes it")


def _open_load_pullup(refdes: str, channel: str) -> Part:
    return _r(refdes, "OUTPUTS", "20k",
              f"{channel} OUT → V12, for OFF-state open-load detect. "
              f"{_DS_TPS} p.23: 'The recommended pullup resistance is 20 kΩ'. "
              f"BOM D2")


def _aux5v_parts(n: int) -> tuple[Part, ...]:
    """One 5 V aux channel (IO-1, IO-2): a current-limited load switch, the
    pull-down that holds its enable OFF, the pull-up on its open-drain fault
    flag, the resistor that sets its limit, its input capacitor and the clamp
    on the wire.  Typed once for all four, so no channel can quietly differ
    from its neighbours."""
    return (
        Part(f"U{305 + n}", "TPS2553DBVR", "SOT-23-6", "OUTPUTS", "IC",
             ("IN", "GND", "EN", "FAULT", "ILIM", "OUT"), 1.45,
             height_confirmed=True, footprint_mm=(3.05, 3.0), v_max=6.5,
             value=f"5 V aux {n}: 1.19-1.39 A limit, active-high EN",
             source=f"5 V aux {n} (IO-1), switching V5AUX onto AUX5V_{n}. "
                    f"{_DS_TPS2553} p.5 pin table, DBV: IN 1 · GND 2 · EN 3 · "
                    f"FAULT 4 · ILIM 5 · OUT 6, and it is the TPS2553, whose "
                    f"'EN: logic high turns on' -- ⛔ never the TPS2552, whose "
                    f"enable is inverted, and never the '-1' latch-off part: "
                    f"this one limits current and keeps reporting. p.6-7: IN "
                    f"2.5-6.5 V (7 V absolute, p.5), I_OUT 1.2 A continuous to "
                    f"T_J 125 °C, over the 1 A of IO-2; FAULT is an active-low "
                    f"open drain for over-current, over-temperature and "
                    f"reverse voltage, V_OL ≤ 180 mV at 1 mA; EN thresholds "
                    f"0.66/1.1 V with I_EN ≤ ±0.5 µA. In a hard short it "
                    f"thermal-cycles in current limit with FAULT low (p.15) "
                    f"and the firmware drops EN. p.41 DBV0006A: SOT-23-6, "
                    f"1.45 mm max, 2.6-3.0 mm over the leads"),
        _r(f"R{364 + n}", "OUTPUTS", "100k",
           f"AUX5V_{n} enable pull-down: the switch is OFF from reset and "
           f"whenever firmware is not driving expander #3's bit (D14). "
           f"{_DS_TPS2553} p.7: I_EN is ±0.5 µA, so 100 kΩ holds the pin "
           f"under 50 mV against a 0.66 V V_IL"),
        _r(f"R{368 + n}", "OUTPUTS", "10k",
           f"AUX5V_{n} FAULT pull-up to V3P3, at the pin. {_DS_TPS2553} p.5: "
           f"the flag is an open drain; p.7 gives V_OL ≤ 180 mV at 1 mA and "
           f"≤ 1 µA of leakage, so 0.33 mA reads a clean 0/1 on an expander "
           f"bit. ⚠️ V3P3, never V5AUX: the bit belongs to a 3.3 V expander"),
        _r(f"R{372 + n}", "OUTPUTS", "20k",
           f"AUX5V_{n} ILIM to GND, which sets the limit. {_DS_TPS2553} p.7: "
           f"20 kΩ gives 1200/1295/1375 mA over -40…125 °C, and 1190-1388 mA "
           f"once the resistor's own 1 % goes through eq. 1 (p.15, which "
           f"excludes it). Over the 1 A of IO-2 at every corner and under the "
           f"1.6 A a 1 A wire is sized for; p.6 allows 15-232 kΩ"),
        _c(f"C{325 + n}", "OUTPUTS", "100nF", 50.0,
           f"AUX5V_{n} switch input decoupling, at the pin. {_DS_TPS2553} p.5: "
           f"'connect a 0.1 µF or greater ceramic capacitor from IN to GND as "
           f"close to the IC as possible'"),
        _tvs6(f"D{330 + n}", "OUTPUTS", f"At J314: AUX5V_{n}"),
    )


_OUTPUTS_PARTS = (
    _tps4h160("U301", "Headlight: LOW, HIGH, DRL. OUT1 is AUX12, the "
              "current-limited feed to horn +, fan + and buzzer +, commanded "
              "by expander #3 (IO-1) like any other channel"),
    _tps4h160("U302", "Tail running + turn L/R. OUT4 is the STOP lamp, "
              "firmware-driven from GPIO19 (IO-8)"),
    _open_load_pullup("R301", "HL_LOW"),
    _open_load_pullup("R302", "HL_HIGH"),
    _open_load_pullup("R303", "HL_DRL"),
    _open_load_pullup("R304", "TAIL_RUN"),
    _open_load_pullup("R305", "TURN_L"),
    _open_load_pullup("R306", "TURN_R"),
    _open_load_pullup("R345", "TAIL_STOP"),
    _tps_series("R346", "AUX12_CMD → U301 IN1"),
    _r("R319", "OUTPUTS", "1k00 1%",
       f"U301 CL → GND: 0.8 V × 2500 / 1.00 kΩ = 2.0 A per channel, over the "
       f"0.71 A / 0.54 A loads. {_DS_TPS} p.29 eq. 10. This is the lamp-scale "
       f"limit D15 chose the part for"),
    _r("R320", "OUTPUTS", "2k0 1%",
       f"U302 CL → GND: 0.8 V × 2500 / 2.0 kΩ = 1.0 A per channel, over the "
       f"0.05-0.10 A loads. {_DS_TPS} p.29 eq. 10"),
    _r("R321", "OUTPUTS", "1k00 1%",
       f"U301 CS → GND, the sense resistor: I_OUT / 300 × 1.00 kΩ = 3.33 V/A, "
       f"so 0.71 A reads 2.37 V. {_DS_TPS} p.29 eq. 9; ≥300 Ω keeps the "
       f"15 mA fault current in range"),
    _r("R322", "OUTPUTS", "1k00 1%", f"U302 CS → GND, the sense resistor, as R321"),
    _r("R323", "OUTPUTS", "10k",
       f"Series from U301's CS node to CS1 -- the TOP of a 10 k / 10 k divider "
       f"with R339. In any fault the CS pin pulls up to V_CS(H) 4.5-6.5 V "
       f"({_DS_TPS} p.29); TI's 10 kΩ series advice is written for a 5 V MCU, "
       f"and alone it leaves ~3.8 V on a 3.3 V pin. Halved, a fault reads "
       f"2.25-3.25 V: above every real load, below VDD"),
    _r("R324", "OUTPUTS", "10k", "Series from U302's CS node to CS2, as R323 (with R340)"),
    _r("R339", "OUTPUTS", "10k",
       "CS1 to GND on the ADC side of R323: the bottom of the divider. The CS "
       "node is R321 ∥ (R323 + R339) = 952 Ω: 3.17 V/A there, 1.59 V/A at the "
       "pin (0.71 A reads 1.13 V; the 0.05 A tail lamp 79 mV). ⚠️ 79 mV is "
       "inside ATTEN3's ±50 mV error: firmware reads CS2's open-load at ATTEN0 "
       "(0-850 mV, ±5 mV; Espressif ESP32-S3 datasheet v2.2 p.66 Table 5-6)"),
    _r("R340", "OUTPUTS", "10k", "CS2 to GND on the ADC side of R324, as R339"),
    _c("C301", "OUTPUTS", "100nF", 50.0,
       f"CS1 to GND on the ADC side of R323. {_DS_HDG} p.21: 0.1 µF at an ADC "
       f"input. With the 10 k / 10 k divider τ ≈ 0.55 ms: firmware waits ≥3 ms after moving SEH/SEL"),
    _c("C302", "OUTPUTS", "100nF", 50.0, "CS2 to GND on the ADC side of R324"),
    _c("C303", "OUTPUTS", "100nF", 50.0, "U301 VS decoupling, at the pins"),
    _c("C304", "OUTPUTS", "10uF", 25.0, "U301 VS bulk decoupling", pkg="1206"),
    _c("C305", "OUTPUTS", "100nF", 50.0, "U302 VS decoupling, at the pins"),
    _c("C306", "OUTPUTS", "10uF", 25.0, "U302 VS bulk decoupling", pkg="1206"),
    _tps_series("R327", "LGT_LOW → U301 IN2"),
    _tps_series("R328", "LGT_HIGH → U301 IN3"),
    _tps_series("R329", "LGT_DRL → U301 IN4"),
    _tps_series("R330", "LGT_TAIL → U302 IN1"),
    _tps_series("R331", "LGT_TURN_L → U302 IN2"),
    _tps_series("R332", "LGT_TURN_R → U302 IN3"),
    _tps_series("R353", "LGT_STOP → U302 IN4"),
    _tps_series("R333", "DIAG_EN, bussed to both devices"),
    _tps_series("R334", "SEL, bussed to both devices"),
    _tps_series("R335", "SEH, bussed to both devices"),
    _r("R349", "OUTPUTS", "10k",
       f"FAULT1 pull-up to V3P3 at U301's pin: FAULT is open-drain, "
       f"{_DS_TPS} p.29 'R(pu) = 10 kΩ'. On the DEVICE side of R350, so the "
       f"series resistor carries no DC and a fault still reads ~0 V at the MCU"),
    _tps_series("R350", "FAULT1, U301 → GPIO39"),
    _r("R351", "OUTPUTS", "10k", "FAULT2 pull-up to V3P3 at U302's pin, as R349"),
    _tps_series("R352", "FAULT2, U302 → GPIO12"),
    # ── low-side channels (plan §6.2.3) ─────────────────────────────────────
    _sot23("Q301", "AO3400A", "OUTPUTS", "NFET", 30.0,
           "Horn low-side. 48 mΩ max at V_GS 2.5 V. BOM D3"),
    _sot23("Q302", "AO3400A", "OUTPUTS", "NFET", 30.0,
           "Fan low-side, LEDC PWM. BOM D3"),
    _sot23("Q303", "AO3400A", "OUTPUTS", "NFET", 30.0,
           "Buzzer low-side, LEDC PWM. BOM D3"),
    _r("R307", "OUTPUTS", "10k",
       "Horn gate pull-down. D14: every gate biases OFF, so a hung module "
       "drives no load (plan §3.1.2). BOM D9"),
    _r("R308", "OUTPUTS", "10k", "Fan gate pull-down (D14). BOM D9"),
    _r("R309", "OUTPUTS", "10k", "Buzzer gate pull-down (D14). BOM D9"),
    _r("R310", "OUTPUTS", "100R", "Horn gate series (plan §6.2.3). BOM D9"),
    _r("R311", "OUTPUTS", "100R", "Fan gate series. BOM D9"),
    _r("R312", "OUTPUTS", "100R", "Buzzer gate series. BOM D9"),
    Part("D307", "SS14", "DO-214AC (SMA)", "OUTPUTS", "D", ("A", "K"), 2.4,
         footprint_mm=(5.3, 2.8), v_max=40.0, value="1 A / 40 V Schottky",
         source="Fan flyback across J305.1-2: anode FAN_RTN, cathode AUX12, "
                "the fan's own + feed. "
                "Schottky is right here: BOM G1's leakage objection concerns "
                "3.3 V inputs, and this diode sits across a 12 V load. SMA "
                "outline assumed"),
    Part("D314", "SS14", "DO-214AC (SMA)", "OUTPUTS", "D", ("A", "K"), 2.4,
         footprint_mm=(5.3, 2.8), v_max=40.0, value="1 A / 40 V Schottky",
         source="Buzzer flyback across J305.3-4: anode BUZZ_RTN, cathode AUX12. "
                "The AO3400A has no avalanche rating and a magnetic buzzer is "
                "a coil; harmless if the buzzer is piezo. SMA outline assumed"),
    Part("D315", "SMBJ18A", "DO-214AA (SMB)", "OUTPUTS", "TVS", ("A", "K"), 2.5,
         footprint_mm=(5.6, 3.95), v_max=18.0, v_clamp=29.2,
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
    # ── IN-15: 12 V rail sense (plan §4 class D) ────────────────────────────
    _r("R337", "OUTPUTS", "47k",
       "IN-15 divider top, from V12. 47 k / 10 k: 12 V → 2.11 V, and TDK's "
       "17.4 V over-voltage ceiling → 3.05 V, inside the 3.3 V pin. On OUTPUTS so "
       "12 V never crosses to LOGIC"),
    _r("R338", "OUTPUTS", "10k", "IN-15 divider bottom"),
    _c("C307", "OUTPUTS", "100nF", 50.0,
       f"At the V12_SENSE node (plan §4 class D). {_DS_HDG} p.21"),
    # ── protection: one array per harness connector, same board ─────────────
    _tvs18("D308", "OUTPUTS", "At J301: HL_LOW"),
    _tvs18("D309", "OUTPUTS", "At J301: HL_HIGH"),
    _tvs18("D310", "OUTPUTS", "At J301: HL_DRL"),
    _tvs18("D311", "OUTPUTS", "At J304: HORN_N"),
    _tvs18("D312", "OUTPUTS", "At J305: FAN_RTN"),
    _tvs18("D319", "OUTPUTS", "At J305: BUZZ_RTN"),
    _tvs18("D320", "OUTPUTS", "At J302: TAIL_RUN"),
    _tvs18("D321", "OUTPUTS", "At J302: rear TURN_L"),
    _tvs18("D322", "OUTPUTS", "At J302: rear TURN_R"),
    _tvs18("D323", "OUTPUTS", "At J302: TAIL_STOP"),
    _tvs18("D324", "OUTPUTS", "At J303: front TURN_L"),
    _tvs18("D325", "OUTPUTS", "At J303: front TURN_R"),
    _tvs18("D326", "OUTPUTS", "At J304/J305: AUX12, the horn/fan/buzzer + feed"),
    # ── the telltale feeds: the display's own block is on POWER (IO-5), but
    # ── these three resistors tap the LAMP FEEDS, which are here ────────────
    _r("R426", "OUTPUTS", "1k",
       "LEFT telltale series to display pin 1, fed from the TURN_L lamp feed, "
       "not a driver channel (plan §6.2.1). 1206: a display wire shorted to "
       "ground puts the 12 V feed across it, 144 mW (rules VR-POWER). BOM B3",
       pkg="1206"),
    _r("R427", "OUTPUTS", "1k", "RIGHT telltale series to display pin 4, 1206 as "
       "R426. BOM B3", pkg="1206"),
    _r("R428", "OUTPUTS", "1k",
       "Headlight telltale series to display pin 5, fed from HL_HIGH so a "
       "flash lights it with no firmware (plan §7); LOW beam does not. 1206 "
       "as R426. BOM B3", pkg="1206"),
    # ── the aux block (IO-1, IO-2): four 12 V and four 5 V outputs at 1 A ────
    # A third TPS4H160B gives the 12 V four, identical in hardware to the lamp
    # channels; a buck and four load switches give the 5 V four; expander #3
    # commands all of it, and both terminals are in the rows on OUTPUTS' two
    # faces (12 V on top, 5 V underneath).
    _tps4h160("U303", "12 V aux 1-4 (IO-1). Commanded by expander #3, and its "
              "CS and FAULT pins share U302's nodes: with DIAG_EN low a "
              "TPS4H160B's CS and FAULT are high-impedance while the current "
              "limit stays live, so the firmware reads one device at a time "
              "and no second ADC pin is needed (SLVSCV8E Table 7-1). ⚠️ The "
              "sharing is only safe while ONE DIAG_EN is up: its own comes off "
              "U304.GPA4, so it is high only when the firmware has written it. "
              "A reset that takes EN low resets U304 with the S3 (IO-22) and "
              "GPA4 returns to an input, so a restart from that reset cannot "
              "raise GPIO7 over a GPA4 left high. ⛔ A watchdog or software "
              "restart does not touch EN: after one GPA4 keeps its last state, "
              "and until the firmware's first write to U304 a raised GPIO7 "
              "sums both devices into CS2_RAW and ORs both FAULTs -- so the "
              "firmware writes U304 OFF before it raises DIAG_EN"),
    _tps_series("R354", "AUX12_1_CMD → U303 IN1"),
    _tps_series("R355", "AUX12_2_CMD → U303 IN2"),
    _tps_series("R356", "AUX12_3_CMD → U303 IN3"),
    _tps_series("R357", "AUX12_4_CMD → U303 IN4"),
    _tps_series("R358", "DIAG3_CMD → U303 DIAG_EN, this device's own"),
    _r("R359", "OUTPUTS", "1k5 1%",
       f"U303 CL → GND: 0.8 V × 2500 / 1.5 kΩ = 1.33 A per channel, and "
       f"1.12-1.55 A with the ±15 % accuracy {_DS_TPS} p.8 gives for 0.5-7 A "
       f"and the resistor's 1 %. Over the 1 A each aux output delivers (IO-2) "
       f"at every corner, and under the 2 A the lamps get. {_DS_TPS} p.29 "
       f"eq. 10. ⚠️ 1.5 kΩ, not the 1.6 kΩ first asked for: no 1.6 kΩ 1 % part "
       f"is JLC Basic in 0805 or 0603 and this one is, and the next Basic "
       f"value up (2.0 kΩ) limits at 1.0 A nominal and 0.85 A at -15 %, "
       f"which is under the load"),
    _open_load_pullup("R360", "AUX12V_1"),
    _open_load_pullup("R361", "AUX12V_2"),
    _open_load_pullup("R362", "AUX12V_3"),
    _open_load_pullup("R363", "AUX12V_4"),
    _c("C309", "OUTPUTS", "100nF", 50.0, "U303 VS decoupling, at the pins"),
    _c("C310", "OUTPUTS", "10uF", 25.0, "U303 VS bulk decoupling", pkg="1206"),
    _tvs18("D327", "OUTPUTS", "At J313: AUX12V_1"),
    _tvs18("D328", "OUTPUTS", "At J313: AUX12V_2"),
    _tvs18("D329", "OUTPUTS", "At J313: AUX12V_3"),
    _tvs18("D330", "OUTPUTS", "At J313: AUX12V_4"),
    # ── expander #3: everything the aux block is commanded by ───────────────
    Part("U304", "MCP23017T-E/SS", "SSOP-28", "OUTPUTS", "IC",
         ("VDD", "VSS", "SCK", "SDA", "A0", "A1", "A2", "RESET")
         + tuple(f"GPA{i}" for i in range(7)) + tuple(f"GPB{i}" for i in range(7)),
         2.0, height_confirmed=True, footprint_mm=(10.5, 8.2),
         nc=("GPA7", "GPB7", "INTA", "INTB", "NC11", "NC14"),
         value="I²C address 0x22 (A2..A0 = 010)",
         source=f"Expander #3, on OUTPUTS with what it drives: the third "
                f"TPS4H160B's four inputs and its own DIAG_EN, the AUX12 "
                f"enable, the four 5 V switch enables and the four 5 V fault "
                f"flags (IO-1). 14 of 16 bits. It shares the input expanders' "
                f"I²C bus -- no native pin is free for a second -- so the "
                f"module's two bus wires cross STACK to reach it. ⚠️ Its "
                f"RESET is the S3's EN, down a third STACK contact (IO-22): "
                f"out of reset every bit is an input ({_DS_MCP} register map, "
                f"IODIR POR/RST = FFh) and every enable it drives has its own "
                f"pull-down (the TPS4H160B's are internal), so every aux "
                f"output is OFF whenever the S3 is held in reset -- at "
                f"power-up behind the EN RC, with the programmer on J408, "
                f"and under a fitted U406. ⛔ A watchdog or software restart "
                f"does NOT reset it: EN is an input the chip cannot drive "
                f"(ESP32-S3 datasheet v2.2 p.28), so after one it keeps "
                f"driving what it last drove until the firmware's first "
                f"write. nc INTA and INTB: it is polled every tick, and "
                f"nothing here needs an interrupt. {_MCP_SOURCE}"),
    _c("C308", "OUTPUTS", "100nF", 50.0, "U304 VDD decoupling"),
    # ── the 5 V aux supply: its OWN buck off V12 (spec §8.4) ────────────────
    # Separate from the logic's 5 V, which comes from the Cincon on POWER, so
    # a 5 V aux fault cannot brown out the S3.
    Part("U305", "LM73605RNPR", "WQFN-30 (RNP), 0.5 mm", "OUTPUTS", "IC",
         ("SW", "CBOOT", "VCC", "BIAS", "SS/TRK", "FB", "NC", "PGOOD",
          "SYNC/MODE", "EN", "AGND", "PVIN", "PGND", "PAD"),
         0.8, height_confirmed=True, footprint_mm=(6.1, 4.1), nc=("RT",),
         v_max=36.0, value="V12 → V5AUX, 5 A synchronous buck at 500 kHz",
         source=f"The 5 V aux rail: 4 × 1 A (IO-2) plus margin, off V12. "
                f"{_DS_LM736} p.3-4 pin table: SW 1-5 · CBOOT 6 · VCC 7 · "
                f"BIAS 8 · RT 9 · SS/TRK 10 · FB 11 · NC 12-15 and 27-30 · "
                f"PGOOD 16 · SYNC/MODE 17 · EN 18 · AGND 19 · PVIN 20-22 · "
                f"PGND 23-26 · DAP. NC lands on GND, not left open: p.4 'No "
                f"internal connection. Connect to ground net and copper to "
                f"improve heat sinking'; PAD is the DAP, p.4 'Must be used "
                f"for heat sinking by soldering to ground copper'. nc RT: "
                f"p.3 'If floating, the default switching frequency is "
                f"500 kHz', which is the frequency this design is sized at, "
                f"and ⛔ 'Do not short to ground'. EN straight to V12: p.4 "
                f"'Do not float. High = ON… Can be tied to PVIN' -- the rail "
                f"is on whenever the 12 V rail is, and no expander bit is "
                f"spent on it. SYNC/MODE to GND: p.4 'Tie to ground if not "
                f"used' = auto mode. Ratings: PVIN 3.5-36 V operating and "
                f"42 V absolute (p.5-6), over D315's 29.2 V clamp on V12; "
                f"I_OUT 0-5 A (p.5). p.51 RNP0030A: WQFN 0.8 mm max height, "
                f"3.9-4.1 × 5.9-6.1 mm"),
    Part("L301", "IHLP2525CZER4R7M01", "SMD, 6.9 × 6.5 mm", "OUTPUTS", "L",
         ("1", "2"), 3.0, height_confirmed=True, footprint_mm=(8.26, 6.9),
         v_max=75.0, value="4.7 µH ±20 % · 5.5 A at ΔT 40 °C · I_sat 10 A",
         source=f"U305's output inductor. {_DS_LM736} Table 3 p.27 asks 4.7 µH "
                f"at 500 kHz and 5 V, and p.30 wants I_sat above the 8.35 A "
                f"worst-case high-side limit. {_DS_IHLP} p.1: 4.7 µH ±20 %, "
                f"DCR 37 mΩ typ / 40 max, 5.5 A for ΔT 40 °C, I_sat 10 A at a "
                f"20 % drop, 75 V across the winding, shielded composite "
                f"construction; body 6.47 × 6.86 mm, 3.0 mm max, pads 3.43 mm "
                f"square over an 8.26 mm layout -- booked at the pad layout, "
                f"not the body. The 4 A this rail can draw peaks at ~4.8 A "
                f"with 25 % ripple, well inside both current figures"),
    _c("C311", "OUTPUTS", "10uF", 35.0,
       f"U305 PVIN bulk, one of two. {_DS_LM736} p.29 asks 2 × 10 µF 50 V "
       f"X7R (X5R accepted) at PVIN; 50 V is well over the 29.2 V D315 lets "
       f"onto V12, and TI's own rule is 'a voltage rating of twice the "
       f"maximum input voltage' to cover DC-bias derating (p.29)", pkg="1206"),
    _c("C312", "OUTPUTS", "10uF", 35.0, "U305 PVIN bulk, the second", pkg="1206"),
    _c("C313", "OUTPUTS", "470nF", 35.0,
       f"U305 PVIN high-frequency bypass, right at the PVIN/PGND pins. "
       f"{_DS_LM736} p.29"),
    _c("C314", "OUTPUTS", "470nF", 16.0,
       f"U305 CBOOT to SW, the high-side driver's bootstrap. {_DS_LM736} p.3: "
       f"'Connect a high-quality 470-nF capacitor from this pin to the SW "
       f"pin'"),
    _c("C315", "OUTPUTS", "2.2uF", 25.0,
       f"U305 VCC to GND, the internal bias LDO's output. {_DS_LM736} p.31 "
       f"asks 2.2 µF X5R/X7R; ⛔ nothing else may load this pin (p.3)",
       pkg="1206"),
    _c("C316", "OUTPUTS", "22nF", 50.0,
       f"U305 SS/TRK to GND: 22 nF gives ~11 ms of soft start off the pin's "
       f"2 µA ({_DS_LM736} p.31), so the rail ramps rather than inrushing "
       f"into four load switches and their cables"),
    _c("C317", "OUTPUTS", "470nF", 16.0,
       f"V5AUX high-frequency bypass beside the bulk. {_DS_LM736} p.30"),
    *(_c(f"C{317 + i}", "OUTPUTS", "22uF", 16.0,
         f"V5AUX bulk, {i} of 8. ⚠️ Sized on TI's TABLE, not TI's example: "
         f"{_DS_LM736} Table 3 p.27 asks 88 µF at 5 V and 500 kHz and its "
         f"footnote says 'All the COUT values are after derating. Add more "
         f"when using ceramics', while the worked example on p.30 fits four "
         f"22 µF parts -- 88 µF NOMINAL, which is under the table's figure "
         f"the moment DC bias is counted. Eight parts are 176 µF nominal and "
         f"hold ≥ 88 µF even at a 50 % loss to DC bias, tolerance and ageing, "
         f"which is the pessimistic end for a 25 V X5R 1206 biased at 5 V "
         f"(a fifth of its rating). ⬜ The derating is a class figure, not "
         f"this part's measured curve: Samsung publishes no DC-bias data in "
         f"the catalogue on file, so confirm it on the part's own curve or "
         f"on the bench before the boards are ordered", pkg="1206")
      for i in range(1, 9)),
    _r("R377", "OUTPUTS", "12k",
       f"U305 feedback divider, top (FB to V5AUX). With R378 and V_FB "
       f"0.987/1.006/1.017 V ({_DS_LM736} p.6), V_OUT is 4.86/5.03/5.17 V -- "
       f"under the 5.25 V the 5 V clamp is chosen against and over the "
       f"TPS2553's 2.5 V floor. TI's own 100 k/24.9 k pair (p.28) has no JLC "
       f"Basic 24.9 kΩ; 12 k/3 k does, and p.31 needs no C_FF while R_FBT is "
       f"under 100 kΩ"),
    _r("R378", "OUTPUTS", "3k", "U305 feedback divider, bottom (FB to GND), with R377"),
    _r("R379", "OUTPUTS", "100k",
       f"U305 PGOOD pull-up to V5AUX. {_DS_LM736} p.31: the flag is an open "
       f"drain and wants 'a suitable voltage supply through a current "
       f"limiting resistor'. ⚠️ Nothing reads it -- expander #3 has no input "
       f"bit left and no native pin is free -- so it is a test point and a "
       f"defined level, not a signal"),
    # ── the four 5 V channels ───────────────────────────────────────────────
    *(part for n in range(1, 5) for part in _aux5v_parts(n)),
)

# ════════════════════════════════════════════════════════════════════════════
# PARTS — LOGIC (L3): logic, and the INPUTS row (IO-4, IO-6). Every contact
# from the harness arrives here, on the board that reads it, so each class-A
# network sits with its own pin. The module footprint serves -WROOM-1 and -1U.
# ════════════════════════════════════════════════════════════════════════════
_U401_PINS = (
    "3V3", "EN", "GND", "EPAD",
    "IO0", "IO1", "IO2", "IO4", "IO5", "IO6", "IO7", "IO8", "IO9", "IO10",
    "IO11", "IO12", "IO13", "IO14", "IO15", "IO16", "IO17", "IO18",
    "IO19", "IO20", "IO21", "IO35", "IO36", "IO37", "IO38", "IO39", "IO40", "IO41",
    "IO42", "IO43", "IO44", "IO47", "IO48",
)

#: Expander #2's spare input-capable bits: the 13 free inputs of the INPUTS row
#: (IO-1), on J409 and J410.  GPA7/GPB7 are output-only and stay nc.
_U403_SPARES = tuple(f"GPA{i}" for i in range(1, 7)) + tuple(f"GPB{i}" for i in range(7))
#: The general-inputs terminals, in row order: A carries a ground, the boost
#: button and the six GPA spares; B carries the seven GPB spares and a ground.
#: ⛔ Two 8-way terminals, not one 16-way: the Kangnex 3.81 × 16 header has 2 in
#: stock at JLC, and this row's headers are FITTED.
_INPUTS_A, _INPUTS_B = "J409", "J410"
#: Where each spare bit's wire lands: the six GPA spares behind A's ground and
#: boost button (pins 3-8), the seven GPB spares on B's pins 1-7.
_SPARE_PINS = tuple(f"{_INPUTS_A}.{i + 3}" for i in range(6)) \
    + tuple(f"{_INPUTS_B}.{i + 1}" for i in range(7))
#: Each spare is class A (plan §4), as the bar inputs are, and the network is
#: fitted, so a wire pushed into the plug later needs no board change.
#: (bit, terminal contact, pull-up, series, cap, TVS line); four SMS05T1G
#: quads, the last two lines of D413 grounded as on the other arrays.
_SPARE_TVS = ("D410", "D411", "D412", "D413")
_SPARE_LINES = tuple(
    (bit, _SPARE_PINS[i], f"R{446 + i}", f"R{459 + i}", f"C{423 + i}",
     f"{_SPARE_TVS[i // 4]}.{('K1', 'K3', 'K4', 'K6')[i % 4]}")
    for i, bit in enumerate(_U403_SPARES))


#: The throttle's boost button is an input too (IO-4), so it sits in the row
#: beside the spares and takes a line of the same arrays. Typed once, read by
#: the array's own `source` and by the net that lands it.
_BOOST_BTN_AT, _BOOST_BTN_LINE = f"{_INPUTS_A}.2", "D413.K3"


def _array_where(ref: str) -> str:
    """What one input array clamps, DERIVED from the lines it carries: the
    arrays span the two terminals (D412 sits entirely at J410, D411 and D413
    straddle both), and a typed connector name went on saying J409 after the
    row was split in two."""
    at, lines = set(), []
    for bit, where, *_x, tvs in _SPARE_LINES:
        if tvs.startswith(f"{ref}."):
            at.add(where.split(".")[0])
            lines.append(f"U403.{bit}")
    if _BOOST_BTN_LINE.startswith(f"{ref}."):
        at.add(_BOOST_BTN_AT.split(".")[0])
        lines.append("the boost button")
    return (f"At {' and '.join(sorted(at))}: {', '.join(lines)} — class-A "
            f"contacts of the INPUTS row (plan §4)")


def _spare_cps(terminal: str) -> tuple[ConnPin, ...]:
    """One terminal's spare contacts, DERIVED from `_SPARE_LINES`, so the
    connector table and the nets cannot disagree about a pin number."""
    return tuple(_cp(where.split(".")[1], f"SPARE_{bit[2:]}_WIRE",
                     f"U403.{bit}, class A")
                 for bit, where, *_ in _SPARE_LINES
                 if where.startswith(f"{terminal}."))


#: What the class-A network at J306 protects, said once for both levers.
_LEVER_NOTE = (
    "{side} brake lever, IN-{n}: since IO-8 the lever WIRE is the node, so the "
    "pull-up, the series resistor and the array (D313) all sit on LOGIC with "
    "J306 in the INPUTS row (IO-6) and with the S3 pin itself, so the lever "
    "signal crosses no interface at all. The series resistor is what keeps a "
    "negative surge on the lever wire out of the S3's input clamp through D313; "
    "with the 100 nF at the pin "
    "τ = 100 µs, well inside the <10 ms the boost safety-release wants."
)


_LOGIC_PARTS = (
    Part("U401", "ESP32-S3-WROOM-1U-N8", "WROOM-1 / WROOM-1U SMD module",
         "LOGIC", "MODULE", _U401_PINS, 3.35, height_confirmed=True,
         footprint_mm=(18.0, 25.5), nc=("IO3", "IO45", "IO46"),
         value="U.FL antenna: the enclosure is metal. The footprint also takes the -1-N8",
         source=f"BOM A4 / D18: 8 MB quad flash, no PSRAM, -40…+85 °C; never "
                f"R8/R16V (65 °C). {_DS_WROOM} p.11-12 Table 3-1, 41 pads: "
                f"GND = pads 1 and 40, EPAD = 41, 3V3 = 2, EN = 3 ('Do not "
                f"leave the EN pin floating'), IO43 = pad 37 'TXD0', IO44 = "
                f"pad 36 'RXD0'. ⛔ There is NO IO33 / IO34 pad. nc IO3, IO45, "
                f"IO46: the unused strapping pins, which no wire may reach "
                f"(plan §3.1.2). IO19 and IO20 are the native USB pins and "
                f"ordinary GPIOs here — the board has no USB port; flashing and "
                f"the console are on UART0 at J408 — and both are in service: "
                f"IO19 is the STOP lamp, IO20 the right brake lever (IO-8). "
                f"{_DS_HDG} p.18: 'For unused pins … enable the "
                f"internal pull during software initialization'. p.42: 18 × 25.5 × 3.1±0.15 (-1), "
                f"18 × 19.2 × 3.2±0.15 (-1U) — booked at the -1U's 3.35 max. "
                f"Keep the antenna keep-out either way"),
    Part("U402", "MCP23017T-E/SS", "SSOP-28", "LOGIC", "IC",
         ("GPA0", "GPA1", "GPA2", "GPA3", "GPA4", "GPA5", "GPA6",
          "GPB0", "GPB1", "GPB2", "GPB3", "GPB4", "GPB5",
          "VDD", "VSS", "SCK", "SDA", "A0", "A1", "A2", "RESET", "INTA"),
         2.0, height_confirmed=True, footprint_mm=(10.5, 8.2),
         nc=("GPA7", "GPB6", "GPB7", "INTB", "NC11", "NC14"),
         value="I²C address 0x20 (A2..A0 = 000)",
         source=f"Expander #1: every bar input. nc GPB6: a spare bit, "
                f"driven as an output by firmware as GPA7/GPB7 are. {_MCP_SOURCE}"),
    Part("U403", "MCP23017T-E/SS", "SSOP-28", "LOGIC", "IC",
         ("VDD", "VSS", "SCK", "SDA", "A0", "A1", "A2", "RESET", "GPA0")
         + _U403_SPARES,
         2.0, height_confirmed=True, footprint_mm=(10.5, 8.2),
         nc=("GPA7", "GPB7", "INTA", "INTB", "NC11", "NC14"),
         value="I²C address 0x21 (A2..A0 = 001)",
         source=f"Expander #2: GPA0 senses ACC+; the other 13 input-capable "
                f"bits are the INPUTS row's free inputs (IO-1), brought out to "
                f"the fitted terminals {_INPUTS_A} and {_INPUTS_B}, each "
                f"class-A conditioned on this board. "
                f"nc INTA: nothing on #2 needs an interrupt; ACC_SENSE is "
                f"polled. {_MCP_SOURCE}"),
    *(part for bit, _, pull, series, cap, _ in _SPARE_LINES
      for part in _class_a_parts(pull, series, cap, f"SPARE_{bit[2:]}")),
    *(_tvs5(ref, "LOGIC", _array_where(ref)) for ref in _SPARE_TVS),
    Part("U404", "SN65HVD230DR", "SOIC-8", "LOGIC", "IC",
         ("D", "GND", "VCC", "R", "CANL", "CANH", "RS"), 1.75,
         height_confirmed=True, footprint_mm=(5.0, 6.2), nc=("Vref",),
         source=f"CAN transceiver; hardware fitted, feed parked (D19). BOM B1. "
                f"{_DS_HVD} p.5: D 1 · GND 2 · VCC 3 · R 4 · Vref 5 · CANL 6 · "
                f"CANH 7 · RS 8. nc Vref: p.20 'If the Vref pin is not used it "
                f"may be left floating'. p.40: SOIC 1.75 mm max"),
    Part("U405", "TLV76733DGNR", "8-HVSSOP PowerPAD", "LOGIC", "IC",
         ("IN", "OUT", "SNS", "EN", "GND", "PAD"), 1.1, height_confirmed=True,
         footprint_mm=(3.1, 5.05), nc=("NC",), v_max=16.0,
         value="5 V → 3.3 V, 1 A, 1 %",
         source=f"LOGIC's regulator: the S3 wants ≥500 mA ({_DS_HDG} p.8) and "
                f"16 V of input rating rides the Cincon's 6.2 V output clamp. "
                f"{_DS_TLV} p.3-4 (DGN, fixed): OUT 1 · SNS 2 · NC 3,7 · GND "
                f"4,6 · EN 5 · IN 8 · pad. SNS: 'Connect the SNS pin to the OUT "
                f"pin … Do not float'. EN ties to IN ('can be connected to the "
                f"input pin'). PAD to GND. nc NC: Figure 5-4 names pads 3 and "
                f"7 NC and Table 5-1 gives them no function. p.41: 1.1 mm max"),
    Part("U406", "TLV803SDBZR", "SOT-23", "LOGIC", "IC", ("GND", "RESET", "VDD"),
         1.12, height_confirmed=True, footprint_mm=(2.9, 2.6), v_max=6.0, dnp=True,
         value="2.93 V threshold, 200 ms, open drain",
         source="EN supervisor, NOT FITTED: the footprint is there if a slow "
                "or bouncing 3V3 ramp ever shows up. Espressif HDG, 'Chip "
                "Power-up and Reset Timing': CHIP_PU must rise after the 3.3 V "
                "rails settle; the 10 kΩ / 1 µF RC (R438, C412) does that for "
                "the TLV767's fast start, and fitted this holds EN low until "
                "3V3 is over 2.93 V and 200 ms more -- and, since the three "
                "MCP23017 RESETs ride EN (IO-22), holds every expander in "
                "reset for the same brown-out. TI SBVS157E (tlv803.pdf) p.4: "
                "TLV803 DBZ GND 1 · RESET 2 · VDD 3; RESET open drain, 'Use a 10-kΩ "
                "to 1-MΩ pullup' = R438. VIT- 2.87-2.99 V (p.6). p.22: DBZ "
                "1.12 mm max"),
    _c("C436", "LOGIC", "100nF", 50.0,
       "U406 VDD decoupling, not fitted with it. TI SBVS157E p.4: 'place a "
       "0.1-µF ceramic capacitor close to this pin'", dnp=True),
    _r("R401", "LOGIC", "120R",
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
    _tvs5("D401", "LOGIC", "At J402: IN04A, IN04B, IN03, IN01"),
    _tvs5("D402", "LOGIC", "At J402: IN09, IN02, IN10"),
    _tvs5("D403", "LOGIC",
          "At J403: IN08A, IN08B, IN11 (the run/off toggle, a plain contact "
          "since IO-8) and START — four 3.3 V class-A lines"),
    *_class_a_parts("R477", "R478", "C438", "IN11_RUN"),
    # ── the brake levers: two plain contacts in the INPUTS row (IO-8) ────────
    *_class_a_parts("R317", "R341", "C421", "IN05_BRAKE_L",
                    note=_LEVER_NOTE.format(side="Left", n="05")),
    *_class_a_parts("R318", "R342", "C422", "IN06_BRAKE_R",
                    note=_LEVER_NOTE.format(side="Right", n="06")),
    _tvs5("D313", "LOGIC",
          "At J306: LEVER_L, LEVER_R — 3.3 V class-A lines (IO-8)"),

    _r("R434", "LOGIC", "2k2",
       "I²C SDA pull-up. I²C at 3.3 V / 400 kHz allows 967 Ω-3.5 kΩ at "
       "100 pF; D16 wants the STRONG end beside 80 A of chopped phase current"),
    _r("R435", "LOGIC", "2k2", "I²C SCL pull-up, as R434"),
    _r("R438", "LOGIC", "10k",
       f"U401 EN pull-up to V3P3, the R of the reset RC, and the ONE external "
       f"bias of all three MCP23017 RESETs, which share the EN net (IO-22). "
       f"{_DS_HDG} p.11: 'CHIP_PU must not be left floating … R = 10 kΩ and "
       f"C = 1 μF'; {_DS_MCP} p.11: RESET 'Must be externally biased' -- it "
       f"has no internal pull-up. ⛔ No second pull-up on EN: two 10 kΩ in "
       f"parallel halve the RC's 10 ms. The three RESET inputs leak ±1 µA "
       f"each ({_DS_MCP} p.4 D060), 30 mV across this resistor at worst, "
       f"against an EN that must sit above 0.8 × VDD = 2.64 V"),
    _r("R439", "LOGIC", "10k",
       f"U401 IO0 pull-up to V3P3, so an unprobed J408 pad cannot select "
       f"download mode at key-on. {_DS_HDG} p.18: 'It is recommended to place "
       f"a pull-up resistor at the GPIO0 pin'"),
    _r("R442", "LOGIC", "10k",
       f"U404 RS → GND, NOT FITTED while CAN is parked (D19). {_DS_HVD} p.5: "
       f"'10kΩ to 100kΩ pull down to GND = slope control mode' — 10 kΩ is "
       f"the fastest slope, ample at 250 kbit/s. To un-park: fit R442, "
       f"remove R472", dnp=True),
    _r("R472", "LOGIC", "10k",
       f"U404 RS → V3P3: standby while CAN is parked (D19). {_DS_HVD} p.6: "
       f"V(Rs) ≥ 0.75 VCC is standby — driver off, receiver listening, 370 µA "
       f"typ (p.7) where slope mode drew 10-17 mA. The transceiver cannot "
       f"drive the bus"),
    _r("R476", "LOGIC", "1k",
       "KEY_SENSE series, at U401.IO1. The line crosses three boards and runs "
       "past 84 V copper on POWER; 1 kΩ limits what a fault or ESD event can "
       "push into the pin's clamp diodes, and what the divider can back-feed "
       "into an unpowered module (<0.3 mA before it)"),
    _c("C437", "LOGIC", "100nF", 50.0,
       f"KEY_SENSE at U401.IO1. {_DS_HDG} p.21: 'add a 0.1 μF filter "
       f"capacitor between ESP pins and ground when using the ADC function'. "
       f"With R476: τ = 0.1 ms"),
    _r("R475", "LOGIC", "470R",
       f"U0TXD series, at U401, on its way to J408 pad 3. {_DS_HDG}, UART: 'a "
       f"499 Ω series resistor to the U0TXD line to suppress harmonics'. "
       f"470 Ω is the nearest JLC Basic value"),
    _c("C412", "LOGIC", "1uF", 16.0,
       f"U401 EN to GND, the C of the reset RC. {_DS_HDG} p.11"),
    _c("C413", "LOGIC", "10uF", 16.0,
       f"U401 3V3 bulk, at pad 2. {_DS_HDG} p.8", pkg="1206"),
    _c("C414", "LOGIC", "100nF", 50.0, f"U401 3V3 HF decoupling. {_DS_HDG} p.8"),
    _c("C415", "LOGIC", "10uF", 16.0, "U405 input, V5 to GND", pkg="1206"),
    _c("C416", "LOGIC", "10uF", 16.0,
       f"U405 output, V3P3 to GND. {_DS_TLV} p.5: C_OUT 1-220 µF, ESR "
       f"2-500 mΩ — ceramic-stable", pkg="1206"),
    _c("C417", "LOGIC", "100nF", 50.0, "U405 output HF decoupling"),
    _c("C418", "LOGIC", "100nF", 50.0, "U402 VDD decoupling"),
    _c("C419", "LOGIC", "100nF", 50.0, "U403 VDD decoupling"),
    _c("C420", "LOGIC", "100nF", 50.0, "U404 VCC decoupling"),
)

_PARTS = (_POWER_ENTRY_PARTS + _POWER_CONVERTER_PARTS + _POWER_CTRL_PARTS
          + _OUTPUTS_PARTS + _LOGIC_PARTS)

# ════════════════════════════════════════════════════════════════════════════
# INTERFACE PIN MAPS — the four inter-board crossings (BD-3, BD-4): two power
# paths (PWR-OUT, a four-conductor keyed loom; PWR-LOGIC, a nine-contact mated
# bus) and two signal spines (CTRL on ribbon, STACK mated).
# ════════════════════════════════════════════════════════════════════════════
# PWR-LOGIC and STACK are MATED PAIRS: the upper half hangs under its board,
# mirrored, facing the lower one. PWR-OUT and CTRL are CABLES (IO-20), so both
# their halves stand on a top face and the loom carries the orientation.
# `model.CROSSING` is where that lives; `integrity` reads it.
# A mated PAIR reads the same from either end, so a half mated reversed, or an
# upper half mirrored by being mounted under its board, lands every net on
# itself; two different nets never sit side by side unless one is a return, so
# a half mated one contact off shorts a rail at worst. A CABLE buys the same
# safety the other way, with a KEYED shell that cannot be offered either way
# round -- rule BUS-ORDER asks each kind for its own. Each is ONE crossing
# between two neighbouring boards.

# ── Connector body sizes: the RULES each maker's drawing states ─────────────
# ⭐ A family's drawing gives its body length as a FORMULA in the contact
# count, and the netlist used to type one figure for both halves of a pair --
# which was 0.4 mm short on every socket and 5.08 wide where every dual-row
# body is 5.0. Encoding the rule closes the class; a corrected constant closes
# one instance, and the same families are used again on the next board.
HDR_PITCH = 2.54


def hc_body(per_row: int, *, rows: int, socket: bool,
            cut: bool = False) -> tuple[float, float]:
    """(length, width) of one 2.54 mm header or socket body, in mm.

    B = contacts per row × 2.54 in both makers' tables (Hong Cheng calls the
    pin span A and the body B; BOOMELE swaps the letters, which is exactly how
    a typed figure goes wrong). The bodies are then:

      socket              B + 0.4   (HC-PM254-8.5H drawings, "(B+0.4)±0.3")
      header, single row  B         (HC-PZ254-11.5L-1x9PZ, "B±0.3")
      header, dual row    B − 0.2   (Hong Cheng's moulded dual-row bodies)
      header, cut to      B         (BOOMELE PZ2.54-2xNA-11.4MM, "A±0.5" =
        length from a strip          N × 2.54: the cut falls on the grid, so
                                     the body ends on it)

    Width is per half, not per family: 2.50 a single-row header, 2.4 a
    single-row socket, 5.0 every dual-row body -- ⛔ never 5.08, which is the
    figure a reader supplies from the pitch when the drawing is not open.
    """
    b = per_row * HDR_PITCH
    if socket:
        return round(b + 0.4, 2), 5.0 if rows == 2 else 2.4
    if rows == 2:
        return round(b if cut else b - 0.2, 2), 5.0
    return round(b, 2), 2.50


def vh_body(ways: int) -> tuple[float, float]:
    """(length, width) of a JST VH wafer, from the series drawing's own table:
    B = ways × 3.96 − 0.06 at every size from 2 to 10 circuits, and the wafer
    is 8.5 mm deep. ⚠️ `ways` is the size of the ORIGINAL body, so a four-way
    header with its third post omitted is a five-way body: 19.74 mm."""
    return round(ways * 3.96 - 0.06, 2), 8.5


def dc3_body(per_row: int) -> tuple[float, float]:
    """(length, width) of a DIN 41651 shrouded box header. The Zhouri drawing
    prints the rule on the part: 2.54 × N/2 + 7.6 ± 0.2 over the shroud, by
    8.4 ± 0.15 across it, where N is the contact count."""
    return round(per_row * HDR_PITCH + 7.6, 2), 8.4


#: PWR-OUT, J202 ↔ J311, POWER to OUTPUTS: FOUR conductors in a keyed shell.
#: Every 12 V load in the module hangs off OUTPUTS, so the whole 8.47 A of
#: IO-10 (tools/power_budget.py) crosses here -- on ONE 16 AWG conductor out
#: and one back, into contacts JST rates at 10 A with that gauge. ⛔ The ten
#: contacts each of V12 and GND this carried until IO-20 were paying a 1 A
#: per-contact floor that a stamped 2.54 mm header imposes and a crimped
#: conductor does not; a cable does not share a current out over contacts, it
#: sizes the wire. V5 and KEY_SENSE only pass THROUGH OUTPUTS, on up to J307.
#: ⚠️ The CONTACT NUMBERS ARE JST'S: the body is five circuits wide with the
#: third post omitted, and the omission is the gap in this tuple. Reading it as
#: 1-2-3-4 would put four evenly spaced holes on the board.
#: ⛔ NOT a palindrome, and it does not need to be: what stops this being mated
#: the wrong way round is the wafer's own lock, which only closes one way
#: (`Connector.keyed`, rule BUS-ORDER). The heavy pair sits together so the
#: 8.47 A goes out and comes back through adjacent contacts, the smallest loop
#: the connector allows; the two light conductors sit on the far side of the
#: key gap.
_PWROUT_CONTACTS = (("1", "V12"), ("2", "GND"), ("4", "V5"), ("5", "KEY_SENSE"))
#: The original body the omitted post is counted out of (JST's "(5-3)").
_PWROUT_WAYS = 5
#: PWR-OUT's HOUSING -- the loom's other half -- as (maker part, circuits, the
#: cavities left EMPTY). ⚠️ The wafer is a FIVE-circuit body with its third
#: post omitted, so the housing is the five-circuit VHR-5N with cavity 3 left
#: empty: JST's housing table (VH drawing p.2) gives it B = 19.74, the wafer's
#: own length. ⛔ The VHR-4N mates the 15.78 mm B4P-VH: cavities 1-4 only, so
#: it cannot carry contact 5, and its lock does not meet this wafer.
#: tests/test_interconnect.py holds the circuit count to `_PWROUT_WAYS` and the
#: empty cavities to the posts `_PWROUT_CONTACTS` omits.
PWROUT_HOUSING = ("VHR-5N", 5, ("3",))

#: PWR-LOGIC, J307 ↔ J407, OUTPUTS to LOGIC: the rails between those two
#: boards, in both directions -- V5 and KEY_SENSE up, and 3.3 V back DOWN for
#: the three pull-ups on OUTPUTS (R346, R349, R351). Its ground return is also
#: every even STACK contact.
#: ⚠️ V3P3 rides HERE, not on STACK, and it takes two contacts: a rail must land
#: on ITSELF when a half is mated reversed or mirrored, which only a palindrome
#: gives it (rule BUS-ORDER). On the spine it faced a ground, and reversed that
#: is the 3.3 V rail shorted to ground. A power bus is where a rail belongs.
_PWRLOGIC_NETS = ("V5", "GND", "V3P3", "GND", "KEY_SENSE", "GND", "V3P3",
                  "GND", "V5")

#: CTRL, J105 ↔ J312, POWER to OUTPUTS: the controller row's signals, each one
#: with a GROUND ON BOTH SIDES OF IT along the ribbon. Nothing here is a rail:
#: the row's own connectors are on POWER (IO-5), so only commands and sense
#: nodes cross. The conductors that matter are the ribbon's, so "beside" means
#: the next CONTACT NUMBER -- a 2.54 mm IDC header numbers across its two rows,
#: so conductor n lands on contact n, and 150 mm of parallel ribbon is what
#: couples, not the 8 mm of header.
#: ⚠️ A PAIR given as a tuple stays ADJACENT and is flanked as one block: CANH
#: and CANL are a differential pair and must see the same neighbours, ground on
#: each outer side. ⛔ Never put a switched 12 V-class line (BOOST_CMD, TT_*)
#: straight outboard of the pair -- an unbalanced aggressor against one half of
#: a pair injects DIFFERENTIALLY, the one coupling a pair cannot reject. The
#: order below keeps a ground between the pair and both of them, and
#: tests/test_interconnect.py holds it there.
_CTRL_SIGNALS = ("BL_CMD", "BL_SENSE", "ACC_SENSE", "UART1_TX", "UART1_RX",
                 ("CANH", "CANL"), "BOOST_CMD", "TT_L", "TT_R", "TT_HL")
#: 2 × 12 = 24 ways, because the DC3-2.54 family (DIN 41651) has no 22-way
#: member: it goes 8, 10, 14, 16, 20, 24. Going UP a size rather than losing
#: the shroud's key is the better half of that trade -- 22 ways force
#: G S G S … G S, and the last signal then has ground on ONE side. 24 give 11
#: signals, each flanked, and 13 grounds. ⭐ The two ways past the 22 the order
#: needs are grounds at the far end: a twelfth signal takes contact 23 and is
#: still flanked, by 22 and 24.
_CTRL_WAYS = 24


def _flanked(signals: tuple, ways: int) -> tuple[str, ...]:
    """`signals` laid out over `ways` contacts with a ground on both sides of
    every one; a tuple of names stays adjacent and is flanked as a block.
    Spare contacts are grounds, at the end. ⚠️ Raises rather than truncating:
    a signal list that outgrows its connector must not lose its last member."""
    out: list[str] = ["GND"]
    for s in signals:
        out += list(s) if isinstance(s, tuple) else [s]
        out.append("GND")
    if len(out) > ways:
        raise ValueError(f"{signals} need {len(out)} contacts, not {ways}")
    return tuple(out + ["GND"] * (ways - len(out)))


_CTRL_NETS = _flanked(_CTRL_SIGNALS, _CTRL_WAYS)
_CTRL_SIGNAL_NAMES = tuple(n for n in _CTRL_NETS if n != "GND")
_CTRL_FP = dc3_body(_CTRL_WAYS // 2)

#: STACK, J308 ↔ J406, 2 × len(_STACK_SIGNALS): odd contacts carry these in
#: order, every even contact is GND, so each signal (CS1/CS2 above all) faces a
#: ground.  The connector's size is DERIVED from this tuple, never typed.
#: Eight of these are RELAYED from CTRL: they start or end on POWER, cross to
#: OUTPUTS on CTRL and carry on to LOGIC here (the lower crossing names them).
_STACK_SIGNALS = (
    "LGT_LOW", "LGT_HIGH", "LGT_DRL", "LGT_TAIL", "LGT_TURN_L", "LGT_TURN_R",
    "LGT_STOP",
    "DIAG_EN", "SEL", "SEH", "CS1", "CS2", "FAULT1", "FAULT2",
    "HORN_CMD", "FAN_CMD", "BUZZ_CMD", "V12_SENSE", "BL_SENSE", "BL_CMD",
    "UART1_TX", "UART1_RX", "BOOST_CMD", "CANH", "CANL",
    "ACC_SENSE",
    # The I²C bus comes DOWN to expander #3, which commands the aux block on
    # OUTPUTS (IO-1). It is the input expanders' own bus: no native pin is
    # free for a second one, and a fault that holds it stalls input reading
    # until the driver's nine-clock recovery frees it (spec §6).
    "SDA", "SCL",
    # The S3's EN comes DOWN to expander #3's RESET (IO-22, owner 2026-09-21),
    # so whatever holds the S3 in reset -- the RC at power-up, the programmer
    # at J408, a fitted U406 -- holds every expander in reset with it and
    # releases the aux outputs. ⚠️ EN is an INPUT the chip cannot drive
    # (ESP32-S3 datasheet v2.2 p.28), so a watchdog or software restart never
    # touches this line. It rides a stack contact beside a ground like every
    # other signal; C412's 1 µF sits at the S3 end.
    "EN",
)
#: Contacts per row, and each half's own body from its maker's drawing: the
#: socket on OUTPUTS is 0.4 mm longer than the header that plugs into it.
_STACK_ROWS = len(_STACK_SIGNALS)
_STACK_SOCKET_FP = hc_body(_STACK_ROWS, rows=2, socket=True)
_STACK_HEADER_FP = hc_body(_STACK_ROWS, rows=2, socket=False, cut=True)


def _p(spec: str) -> tuple[tuple[str, str], ...]:
    """'Q106.S R115.2' → (("Q106", "S"), ("R115", "2")). Keeps REF.PIN greppable."""
    return tuple((ref, pin) for ref, pin in
                 (tok.split(".", 1) for tok in spec.split()))


def _pwrout(net: str) -> tuple[tuple[str, str], ...]:
    return tuple((c, pin) for pin, n in _PWROUT_CONTACTS
                 if n == net for c in ("J202", "J311"))


def _pwrlogic(net: str) -> tuple[tuple[str, str], ...]:
    return tuple((c, str(i + 1)) for i, n in enumerate(_PWRLOGIC_NETS)
                 if n == net for c in ("J307", "J407"))


def _ctrl(net: str) -> tuple[tuple[str, str], ...]:
    i = _CTRL_NETS.index(net)
    return (("J105", str(i + 1)), ("J312", str(i + 1)))


def _stack(net: str) -> tuple[tuple[str, str], ...]:
    i = _STACK_SIGNALS.index(net)
    return (("J308", str(2 * i + 1)), ("J406", str(2 * i + 1)))


_CTRL_GND = tuple((c, str(i + 1)) for c in ("J105", "J312")
                  for i, n in enumerate(_CTRL_NETS) if n == "GND")

_STACK_GND = tuple((c, str(n)) for c in ("J308", "J406")
                   for n in range(2, 2 * _STACK_ROWS + 1, 2))

# ════════════════════════════════════════════════════════════════════════════
# NETS — the 84 V section. POWER only (BD-2).
# ⚠️ Order on each branch: HV_SW → choke → bulk cap → converter. D201 + F201 sit
# between the choke and C2 ONLY, so the hold-up cap serves DC-DC #2 alone.
# ════════════════════════════════════════════════════════════════════════════
_NETS_84V = (
    Net("HV_BPLUS", _p("J101.1 D101.K Q101.S R110.2 D102.K C107.2"),
        domain="84V",
        source="B+ from the tap downstream of the XT90-S; fused UPSTREAM IN THE "
               "HARNESS by the 3 A KLKD003 (plan §3.2.5), never on the board"),
    Net("KSW", _p("J101.6 R112A.1 R107.1"), domain="84V",
        source="The key switch's OUTPUT: 84 V with the key on. The switch, its "
               "own 2 A inline fuse and the FarDriver KEY wire are harness "
               "(plan §3.2.5) -- ⚠️ a DIFFERENT fuse from the module's 3 A "
               "B+ tap (KLKD003): two branches off the XT90-S, one fuse each; "
               "the module only taps it, for D13's gate drive and for IN-12, "
               "and never sources or switches KEY (D10). ⛔ NO clamp here: the "
               "wire reaches only two 400 V strings of ≥ 330 kΩ, whose far ends "
               "D106 and C109 hold; a TVS would add the one part that fails "
               "SHORT and blows the key fuse -- cutting the controller's KEY "
               "mid-ride, the one thing D10 says the module never does"),
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
    Net("HV_C1_P", _p("L101.4 C201.+ U201.+Vin C203.1"),
        domain="84V",
        source="DC-DC #1 +Vin: choke → C1 → converter, in that order"),
    Net("HV_C1_N", _p("L101.3 C201.- U201.-Vin U201.CNT C204.1"),
        domain="84V",
        source="DC-DC #1 -Vin, its OWN net: it joins GND only through L101's "
               "3-2 winding. ~0 V DC, but it is 84 V-section copper. U201.CNT "
               "is strapped here: negative logic, open = OFF"),
    Net("HV_C2_P", _p("L102.4 D201.A"),
        domain="84V",
        source="DC-DC #2's branch after its choke, ahead of the hold-up diode"),
    Net("HV_C2_N", _p("L102.3 C202.- U202.-Vin C206.1"),
        domain="84V",
        source="DC-DC #2 -Vin, its OWN net: it joins GND only through L102's "
               "3-2 winding"),
    Net("HV_C2_HOLD_IN", _p("D201.K FH201.1 F201.1"), domain="84V",
        source="Between the hold-up diode and the fuse"),
    Net("HV_C2_HOLD", _p("FH201.2 F201.2 C202.+ U202.+Vin C205.1"),
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
        # POWER: entry
        _p("J101.3 J101.4 D101.A Q105.S R113.2 D106.A C108.2 "
           "R109.2 C109.2 L101.2 L102.2")
        # POWER: converters
        + _p("U201.-V U201.-S C207.- C208.2 C210.1 U202.-Vout C211.2 C212.2 "
             "R211.2")
        # POWER: the controller row
        + _p("Q106.S R115.2 R344.2 Q401.S R425.2 "
             "J309.2 J310.2 J404.4 J405.3 "
             "D316.A2 D316.A5 D316.K4 D316.K6 "
             "D317.A2 D317.A5 D317.K3 D317.K4 D317.K6 "
             "D404.A2 D404.A5 D404.K4 D404.K6 "
             "D405.A2 D405.A5 D405.K4 D405.K6 D406.A2 D406.A5 "
             "D407.A2 D407.A5 D407.K3 D407.K4 D407.K6")
        # OUTPUTS
        + _p("U301.GND U301.PAD U301.THER U302.GND U302.PAD U302.THER "
             "R319.2 R320.2 R321.2 R322.2 "
             "C301.2 C302.2 C303.2 C304.2 C305.2 C306.2 C307.2 R338.2 R339.2 R340.2 "
             "Q301.S Q302.S Q303.S R307.2 R308.2 R309.2 D315.A "
             "J301.1 J302.1 J303.2 J303.4 "
             "D308.A D309.A D310.A D311.A D312.A D319.A D320.A D321.A D322.A "
             "D323.A D324.A D325.A D326.A")
        # OUTPUTS: the aux block (IO-1)
        + _p("U303.GND U303.PAD U303.THER R359.2 C309.2 C310.2 "
             "D327.A D328.A D329.A D330.A "
             "U304.VSS U304.A0 U304.A2 C308.2 "
             "U305.AGND U305.PGND U305.PAD U305.NC U305.SYNC/MODE "
             "C311.2 C312.2 C313.2 C315.2 C316.2 C317.2 R378.2 "
             "J313.2 J313.4 J313.6 J314.2 J314.4 J314.6 J314.8")
        + _p(" ".join(f"C{317 + i}.2" for i in range(1, 9)))
        + _p(" ".join(f"U{305 + n}.GND R{364 + n}.2 R{372 + n}.2 "
                      f"C{325 + n}.2 D{330 + n}.A" for n in range(1, 5)))
        # LOGIC
        + _p("U401.GND U401.EPAD C412.2 C413.2 C414.2 "
             "U402.VSS U402.A0 U402.A1 U402.A2 C418.2 "
             "U403.VSS U403.A1 U403.A2 C419.2 "
             "U404.GND R442.2 C420.2 U405.GND U405.PAD C415.2 C416.2 C417.2 "
             "C401.2 C402.2 C403.2 C404.2 C405.2 C406.2 C407.2 C408.2 C409.2 "
             "C410.2 C411.2 C421.2 C422.2 C438.2 "
             "D401.A2 D401.A5 D402.A2 D402.A5 D402.K6 D403.A2 D403.A5 "
             "D313.A2 D313.A5 D313.K4 D313.K6 "
             "U406.GND C436.2 C437.2 "
             "J306.2 J402.1 J403.1 J408.4 J409.1 J410.8")
        + _p(" ".join(f"{cap}.2" for *_, cap, _ in _SPARE_LINES))
        + _p(" ".join(f"{d}.A2 {d}.A5" for d in _SPARE_TVS))
        + _p("D413.K4 D413.K6") + _pwrout("GND") + _CTRL_GND + _pwrlogic("GND")
        + _STACK_GND,
        domain="GND", interface="PWR-OUT",
        source="The star net, on all three boards and across all four "
               "interfaces (one 16 AWG conductor of PWR-OUT, 13 of CTRL's 24 "
               "contacts, PWR-LOGIC × 4, every even STACK contact); "
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
        _p("U201.+V U201.+S C207.+ C208.1 C209.1") + _pwrout("V12")
        + _p("U301.VS U302.VS C303.1 C304.1 C305.1 C306.1 "
             "R301.2 R302.2 R303.2 R304.2 R305.2 R306.2 R345.2 "
             "D315.K R337.1")
        + _p("U303.VS C309.1 C310.1 R360.2 R361.2 R362.2 R363.2 "
             "U305.PVIN U305.EN C311.1 C312.1 C313.1"),
        domain="12V", interface="PWR-OUT",
        source="DC-DC #1's output, +S strapped to +V at the brick. 2.62 A "
               "measured (plan §3.2.3), and 8.47 A nominal now the aux block "
               "hangs off it — every channel at its 1 A design load, not at "
               "its limiter's ceiling (spec §8, tools/power_budget.py). It "
               "never leaves the box: every 12 V wire out is a TPS4H160B "
               "channel, aux 1-4 included, and "
               "the 5 V aux rail is a buck off it. D315 is its clamp, and "
               "U305's 42 V absolute input rating clears that clamp's 29.2 V"),
    Net("V5",
        _p("U202.+Vout C211.1 C212.1") + _pwrout("V5") + _pwrlogic("V5")
        + _p("U405.IN U405.EN C415.1"),
        domain="5V", interface="PWR-OUT",
        source="DC-DC #2's isolated output, referenced to the star. Feeds "
               "LOGIC's regulator and nothing else"),
    Net("V3P3",
        _p("U405.OUT U405.SNS C416.1 C417.1 U401.3V3 C413.1 C414.1 "
           "U402.VDD C418.1 U403.VDD U403.A0 C419.1 U404.VCC C420.1 "
           "R402.2 R403.2 R404.2 R405.2 R406.2 R407.2 R408.2 R409.2 R410.2 "
           "R411.2 R412.2 R434.2 R435.2 R438.2 R439.2 R477.2 "
           "R317.2 R318.2 "
           "R472.2 U406.VDD C436.1") + _p(" ".join(f"{pull}.2" for _, _, pull, *_ in _SPARE_LINES))
        + _pwrlogic("V3P3") + _p("R349.2 R351.2 U304.VDD U304.A1 C308.1")
        + _p(" ".join(f"R{368 + n}.2" for n in range(1, 5))),
        domain="3V3", interface="PWR-LOGIC",
        source="LOGIC's 3.3 V rail. It goes DOWN to OUTPUTS for the two "
               "TPS4H160B FAULT pull-ups (R349, R351), expander #3 and its "
               "RESET pull-up, and the four 5 V FAULT pull-ups -- every "
               "class-A pull-up, the levers' included, is on LOGIC with its own "
               "terminal now -- and it goes on the POWER BUS, two contacts of "
               "it, never on the signal spine: a rail has to land on itself "
               "when a half is mated reversed (BUS-ORDER). U403.A0 is strapped "
               "here (address 001) and U304.A1 is (address 010)"),
)

#: Said once for every channel expander #3 commands: what holds it off, and
#: for HOW LONG. ⛔ Not `_LGT`'s sentence, which is written for a native GPIO
#: and bounds the window at the ~200 ms it spends high-Z at boot. An expander
#: bit is high-Z until firmware writes the chip -- on an unflashed, dead or
#: hung module, for ever -- so what holds these channels off has to hold
#: indefinitely, and the silicon's own pull-down does.
_AUX_OFF = ("The TPS4H160B's internal 100-250 kΩ input pull-down holds the "
            "channel OFF for as long as nothing drives the bit: expander #3's "
            "pins come out of reset as inputs and stay inputs until firmware "
            "writes them, so an unflashed or hung module never lights this "
            "output (D14, plan §6.2.2a)")

# ════════════════════════════════════════════════════════════════════════════
# NETS — the OUTPUTS board's outputs. Every lamp common is GND; there is no separate return.
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
    Net("AUX12_CMD", _p("U304.GPA5 R346.1"), domain="3V3",
        source="The AUX12 feed's command, expander #3's GPA5 (IO-1). ⚠️ An "
               "ordinary output: nothing holds the channel on, so horn, fan "
               "and buzzer have no + until firmware asks for it"),
    Net("AUX12_EN", _p("R346.2 U301.IN1"), domain="3V3",
        source=f"U301 IN1, behind R346. {_AUX_OFF}"),
    Net("TAIL_RUN", _p("U302.OUT1 R304.1 J302.2 D320.K"), domain="12V",
        source="J302.2 YELLOW, 0.05 A, a separate feed and not PWM"),
    Net("TURN_L", _p("U302.OUT2 R305.1 J302.4 J303.1 R426.1 D321.K D324.K"),
        domain="12V",
        source="Rear LEFT is J302.4 BLUE (M6); the front pair is on J303"),
    Net("TURN_R", _p("U302.OUT3 R306.1 J302.5 J303.3 R427.1 D322.K D325.K"),
        domain="12V", source="Rear RIGHT is J302.5 GREEN (M6)"),
    Net("TAIL_STOP", _p("U302.OUT4 R345.1 J302.3 D323.K"), domain="12V",
        source="J302.3 RED, 0.12 A, on U302 OUT4 -- an ordinary firmware-"
               "commanded channel since IO-8, identical in hardware to the turn "
               "lamps: the 1 A limit, OFF-state open-load detection through R345 "
               "and FAULT2. ⚠️ The lamp is DARK whenever the firmware is not "
               "running (IO-9). Firmware reads its current on CS2 (SEL/SEH = "
               "channel 4) and cross-checks it against IN-05/06"),
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
    Net("CS2_RAW", _p("U302.CS R322.1 R324.1 U303.CS"), domain="5V",
        source=f"U302's current-sense node, as CS1_RAW -- and U303's too. Two "
               f"devices share it because a TPS4H160B's CS pin is "
               f"high-impedance while its own DIAG_EN is low ({_DS_TPS} "
               f"Table 7-1, 'Diagnostics disabled, full protection': the "
               f"current LIMIT stays live either way). The firmware raises one "
               f"DIAG_EN at a time, so this node carries one device's sense "
               f"current and the scale R339 states still means what it says. "
               f"⚠️ Raise both and the two sense currents add: the reading is "
               f"then the sum of two channels, not either one"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — the brake and the motor cut, as plain firmware I/O (IO-8). There is no
# dedicated circuit: the levers are contacts the S3 reads, the stop lamp is a
# TPS4H160B channel the S3 commands, and BL is an open-drain output the S3
# drives. ⚠️ Nothing here works while the firmware is not running: BL is
# RELEASED and the stop lamp is OFF at key-on, through boot, and after a hang or
# a restart (IO-9). The key switch remains the one hardware kill (D24).
# ════════════════════════════════════════════════════════════════════════════
_NETS_BRAKE = (
    Net("LEVER_L", _p("J306.1 R317.1 R341.1 D313.K1"), domain="3V3",
        source="Left lever wire: a dry contact to ground, pulled up to 3.3 V by "
               "R317 at the module end (plan §4 class A). The wire IS the node "
               "now — no steering diode stands between it and the input. ⬜ M3 "
               "gates J306: lever type, NO/NC and wire count. ⚠️ A broken "
               "normally-open lever wire reads as 'not braking' and nothing "
               "detects it"),
    Net("LEVER_R", _p("J306.3 R318.1 R342.1 D313.K3"), domain="3V3",
        source="Right lever wire, as LEVER_L"),
    Net("BL", _p("Q106.D R336.1 J309.1 D316.K1"), domain="3V3",
        source=f"FarDriver BL, YELLOW/GREEN — never grey BH, which stays "
               f"capped. Rests on the controller's own ~3.3 V pull-up "
               f"({_BRK} §7.1), so it is RELEASED unless Q106 pulls it low = "
               f"motor cut. ⚠️ With the firmware stopped Q106's gate is held "
               f"down by R115 and the bike drives (IO-9). It leaves the box from "
               f"POWER on J309, in the controller row (IO-5), and its FET, gate "
               f"divider and clamp are all on that board with it. The 100 nF "
               f"brake C1 belongs at the controller, not here"),
    Net("BL_CMD", _p("U401.IO16") + _stack("BL_CMD") + _ctrl("BL_CMD")
        + _p("R114.1"), domain="3V3", gpio="GPIO16", interface="CTRL",
        source="The motor-cut command (IO-8). GPIO16 comes out of reset with no "
               "pull and only a low glitch at power-up (S3 datasheet v2.2 "
               "Table 2-2), so BL stays released through boot (IO-9). From the "
               "S3 on LOGIC it crosses STACK and then CTRL to reach Q106's gate "
               "resistor on POWER; `interface` names the lower crossing. ⚠️ Both "
               "crossings are open-circuit failures, and an open here RELEASES "
               "the cut -- the direction IO-9 chose"),
    Net("BL_GATE", _p("R114.2 Q106.G R115.1"), domain="3V3",
        source="Q106's gate, behind its 100 Ω series resistor and over R115's "
               "hard 10 kΩ pull-down: the gate is biased OFF (D14), so the cut "
               "is released whenever nothing drives it"),
    Net("BL_SENSE", _p("R336.2") + _ctrl("BL_SENSE") + _stack("BL_SENSE")
        + _p("U402.GPB5"), domain="3V3", interface="CTRL",
        source="BL read back through R336's 100 kΩ, so a stuck cut or a missing "
               "one can be reported. A readback, NOT an isolation barrier: "
               "firmware commands the cut directly on BL_CMD (IO-8), and R336 "
               "is sized to keep this node from loading BL (see R336)"),
    Net("ACC_SENSE", _p("R343.2 R344.1") + _ctrl("ACC_SENSE")
        + _stack("ACC_SENSE") + _p("U403.GPA0"), domain="3V3", interface="CTRL",
        source="ACC+ divided to 3.28 V for expander #2: LOW with the key on "
               "means the throttle's 5.1 V is not arriving. ⚠️ What that costs "
               "is the MOTOR CUT and nothing else — BL only means something to a "
               "live controller. Every 12 V output runs off this module's own "
               "converters and is unaffected, so ⛔ firmware must NOT gate the "
               "lamps or the horn on this sensor. ⚠️ It also cannot tell a dead "
               "controller from a broken ACC+ sense wire: both read LOW, and a "
               "lamp policy built on it would be lost to one chafed wire"),
    Net("ACC_PLUS", _p("J309.3 R343.1 D316.K3"), domain="5V",
        source="The throttle's 5.1 V supply, in from the FarDriver harness on "
               "POWER. It feeds the R343/R344 sense divider, on that board with "
               "it, and nothing else: a sensor, not a rail, and only the divided "
               "node crosses CTRL"),
    Net("IN05_BRAKE_L", _p("R341.2 U401.IO15 C421.1"),
        domain="3V3", gpio="GPIO15",
        source="Stays NATIVE: the brake must cut the motor from an interrupt, "
               "and the boost safety-release wants it in <10 ms (plan §3.1.1). "
               "The lever wire's TVS is D313 at J306, and since J306 joined the "
               "INPUTS row on LOGIC (IO-6) this signal crosses no interface at "
               "all: no contact of the stack stands between a lever and its pin"),
    Net("IN06_BRAKE_R", _p("R342.2 U401.IO20 C422.1"),
        domain="3V3", gpio="GPIO20",
        source="As IN05_BRAKE_L, for the right lever. GPIO20 comes out of reset "
               "with USB_PU, the USB D+ pull-up (S3 datasheet v2.2 Table 2-1): "
               "harmless on an input already pulled up to 3.3 V, and ⛔ nothing "
               "with a pull-down bias may ever be moved onto this pin"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — STACK control and diagnostics (OUTPUTS ↔ LOGIC). Lighting is FULL NATIVE
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
    Net("LGT_STOP", _p("U401.IO19") + _stack("LGT_STOP") + _p("R353.1"),
        domain="3V3", interface="STACK", gpio="GPIO19",
        source=f"The brake lamp, firmware-driven (IO-8); lighting stays native "
               f"(D16). GPIO19's two ~60 µs high glitches at power-up (S3 "
               f"datasheet v2.2 Table 2-2) DO reach the channel: {_DS_TPS} §6.6 "
               f"gives t_d(on) 20 µs MIN and a 0.55 V/µs MAX turn-on slew, so "
               f"the fastest part puts current in the lamp for well under "
               f"100 µs. On a 0.12 A lamp that is below anything a rider or a "
               f"following driver can see, and orders of magnitude under the "
               f"lamp's own thermal time constant. What actually keeps the lamp "
               f"dark is IN4's internal pull-down (below) and, for the pin "
               f"choice, rule GPIO-RESET-PULL: GPIO19 comes out of reset with "
               f"NO pull, and the rule refuses any pin that does. {_LGT}"),
    Net("LGT_STOP_IN", _p("R353.2 U302.IN4"), domain="3V3",
        source="U302 IN4: the STOP channel. Its 100-250 kΩ internal pull-down "
               "holds it OFF from reset, so the lamp is dark whenever the "
               "firmware is not running (IO-9)"),
    Net("DIAG_EN", _p("U401.IO7") + _stack("DIAG_EN") + _p("R333.1"),
        domain="3V3", interface="STACK", gpio="GPIO7",
        source="Diagnostics enable, bussed to both devices behind R333"),
    Net("DIAG_EN_IN", _p("R333.2 U301.DIAG_EN U302.DIAG_EN"), domain="3V3",
        source="Device side of R333"),
    Net("SEL", _p("U401.IO8") + _stack("SEL") + _p("R334.1"),
        domain="3V3", interface="STACK", gpio="GPIO8",
        source="CS channel-select LOW bit (TI's SEL, pad 8), bussed"),
    Net("SEL_IN", _p("R334.2 U301.SEL U302.SEL U303.SEL"), domain="3V3",
        source="Device side of R334, all three devices"),
    Net("SEH", _p("U401.IO9") + _stack("SEH") + _p("R335.1"),
        domain="3V3", interface="STACK", gpio="GPIO9",
        source="CS channel-select HIGH bit (TI's SEH, pad 7), bussed"),
    Net("SEH_IN", _p("R335.2 U301.SEH U302.SEH U303.SEH"), domain="3V3",
        source="Device side of R335, all three devices"),
    Net("CS1", _p("R323.2 R339.1 C301.1") + _stack("CS1") + _p("U401.IO4"),
        domain="3V3", interface="STACK", gpio="GPIO4",
        source="U301's current sense behind R323. ⚠️ ADC1 ONLY (ADC2 dies with "
               "WiFi), and it faces a ground contact across STACK"),
    Net("CS2", _p("R324.2 R340.1 C302.1") + _stack("CS2") + _p("U401.IO5"),
        domain="3V3", interface="STACK", gpio="GPIO5",
        source="U302's current sense behind R324. ⚠️ ADC1 only"),
    Net("FAULT1_DEV", _p("U301.FAULT R349.1 R350.1"), domain="3V3",
        source="U301's open-drain FAULT, pulled up at the pin by R349"),
    Net("FAULT1", _p("R350.2") + _stack("FAULT1") + _p("U401.IO39"),
        domain="3V3", interface="STACK", gpio="GPIO39",
        source="U301's global fault behind R350. Digital only. GPIO39's reset "
               "pull-up only adds to R349's"),
    Net("FAULT2_DEV", _p("U302.FAULT R351.1 R352.1 U303.FAULT"), domain="3V3",
        source="U302's open-drain FAULT, pulled up at the pin by R351 -- and "
               "U303's, which shares it the way they share CS2_RAW: the pin is "
               "high-impedance while that device's DIAG_EN is low. ⚠️ Low here "
               "means 'whichever of the two has diagnostics enabled has a "
               "fault', so firmware reads it against the DIAG_EN it raised"),
    Net("FAULT2", _p("R352.2") + _stack("FAULT2") + _p("U401.IO12"),
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
        source="IN-15, ADC1_CH1: V12 through 47 k / 10 k on OUTPUTS"),
    Net("CANH", _p("U404.CANH R401.1") + _stack("CANH") + _ctrl("CANH")
        + _p("J405.8 D405.K1"), domain="3V3", interface="CTRL",
        source="Display pin 8, RED-BLACK. The panel terminates its own end "
               "(132.4 Ω). A 3.3 V transceiver's pair; even a 5 V part at the "
               "panel end drives CANH to 4.5 V at most, under D405's 5 V "
               "V_RWM. The transceiver is on LOGIC and J405 on POWER, so the "
               "pair crosses STACK and then CTRL. ⚠️ Two more contacts in a "
               "differential pair: it is parked (D19), and if it is ever "
               "un-parked the pair's two crossings are the first thing to "
               "measure"),
    Net("CANL", _p("U404.CANL R401.2") + _stack("CANL") + _ctrl("CANL")
        + _p("J405.7 D405.K3"), domain="3V3", interface="CTRL",
        source="Display pin 7, GREEN-BLACK. As CANH"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — the parked display block, on POWER with J405 in the controller row
# (IO-5, D19). Only the three telltales cross an interface: their 1 kΩ series
# resistors stay on OUTPUTS with the lamp feeds that drive them.
# ════════════════════════════════════════════════════════════════════════════
_NETS_DISPLAY = (
    Net("TT_L", _p("R426.2") + _ctrl("TT_L") + _p("J405.1 D406.K1"),
        domain="12V", interface="CTRL",
        source="Display pin 1, telltale LEFT: a 0-15 V input fed from the "
               "TURN_L lamp feed through R426. The feed is a lamp channel on "
               "OUTPUTS and the display plug is on POWER, so the three telltales "
               "cross CTRL behind their 1 kΩ resistors -- the resistor stays with "
               "the channel, so a shorted display wire is 12 V across a 1206 on "
               "OUTPUTS and not into a contact"),
    Net("TT_R", _p("R427.2") + _ctrl("TT_R") + _p("J405.4 D406.K3"),
        domain="12V", interface="CTRL",
        source="Display pin 4, telltale RIGHT. As TT_L"),
    Net("TT_HL", _p("R428.2") + _ctrl("TT_HL") + _p("J405.5 D406.K4"),
        domain="12V", interface="CTRL",
        source="Display pin 5, telltale HEADLIGHT, fed from HL_HIGH. As TT_L"),
    Net("DISP_ONELINE", _p("R429.2 J405.9 D406.K6"), domain="12V",
        source="Display pin 9, the one-line feed behind R429. 0-15 V"),
    Net("FD_ONELINE", _p("J310.1 R429.1 D317.K1"), domain="12V",
        source="The FarDriver's BROWN one-line lead, 0-15 V, in on J310"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — LOGIC: the module's support pins, buses, serial, CAN, boost.
# ════════════════════════════════════════════════════════════════════════════
_NETS_LOGIC = (
    Net("KEY_SENSE",
        _p("R108.2 R109.1 C109.1") + _pwrout("KEY_SENSE")
        + _pwrlogic("KEY_SENSE") + _p("R476.1"),
        domain="3V3", interface="PWR-OUT",
        source="IN-12, ADC1_CH0: KSW through 330 k / 10 k, 84 V → 2.47 V. "
               "Tapped UPSTREAM of the hold-up diode, so key-off shows at once "
               "while C2 keeps the logic alive (plan §3.2.2). Divider on POWER, "
               "pin on LOGIC behind R476: crosses PWR-OUT on its own 22 AWG "
               "conductor and PWR-LOGIC with a ground either side of it. Key "
               "state only — never a battery gauge"),
    Net("KEY_SENSE_PIN", _p("R476.2 C437.1 U401.IO1"), domain="3V3", gpio="GPIO1",
        source="KEY_SENSE at the ADC pin, behind its 1 kΩ, with the HDG's "
               "0.1 µF at the pin"),
    Net("EN", _p("U401.EN R438.1 C412.1 J408.1 U406.RESET "
                 "U402.RESET U403.RESET U304.RESET") + _stack("EN"), domain="3V3",
        interface="STACK",
        source=f"Module enable AND every expander's RESET (IO-22): the 10 kΩ / "
               f"1 µF reset RC, the unfitted supervisor's open drain, the "
               f"service pad the programmer pulses to reset the module, the two "
               f"input expanders' RESET on this board and expander #3's down a "
               f"STACK contact. Whatever holds the S3 in reset holds all three "
               f"in reset with it, and they leave it AFTER the S3 does: the "
               f"MCP23017's RESET releases at 0.8 × VDD ({_DS_MCP} p.4 D041, "
               f"Schmitt) and the S3 at 0.75 × VDD (ESP32-S3 datasheet v2.2 "
               f"p.65 Table 5-4, VIH_nRST), 16.1 ms against 13.9 ms up the "
               f"10 ms RC -- so no expander is ever awake while the S3 is "
               f"held, and none is still held when the firmware first writes "
               f"it, tens of ms later. Any pull that resets the S3 (≥ 50 µs "
               f"below 0.25 × VDD, p.30 Table 2-13) is far past the MCP's "
               f"1 µs TRSTL ({_DS_MCP} p.5) and its 0.2 × VDD VIL. ⛔ EN is an "
               f"input the S3 cannot drive (p.28 Table 2-10), so a watchdog or "
               f"software restart resets nothing on this net"),
    Net("BOOT_IO0", _p("U401.IO0 R439.1 J408.6"), domain="3V3", gpio="GPIO0",
        source="Boot-mode strap, pulled up. ⛔ It reaches the INTERNAL service "
               "pads only — no wire that leaves the box lands on a "
               "strapping pin (plan §3.1.2)"),
    Net("U0TXD", _p("U401.IO43 R475.1"), domain="3V3", gpio="GPIO43",
        source="ROM boot log, the console and download-mode TX, to the "
               "service pads only. ⛔ Never a load driver: it chatters at "
               "every reset"),
    Net("U0TXD_HDR", _p("R475.2 J408.3"), domain="3V3",
        source="U0TXD beyond its 470 Ω, at the service pads"),
    Net("U0RXD", _p("U401.IO44 J408.5"), domain="3V3", gpio="GPIO44",
        source="GPIO44 = U0RXD: the console and download-mode RX, on the "
               "service pads only, so no harness wire ever meets the "
               "programmer's TX here. ⬜ M9 decides whether IN-14, the dongle-TX "
               "listen-only tap, exists; every native pin is now in service, so "
               "it costs a pin move (the horn command to an expander) and no "
               "harness connector carries it"),
    Net("SDA", _p("U401.IO13 U402.SDA U403.SDA R434.1") + _stack("SDA")
        + _p("U304.SDA"), domain="3V3", gpio="GPIO13", interface="STACK",
        source="I²C data. The two input expanders are on LOGIC and expander "
               "#3 is on OUTPUTS with the aux block it drives (IO-1), so the "
               "bus crosses STACK, a ground beside it. ⚠️ ONE bus for all "
               "three: no native pin is free for a second, so a device that "
               "holds SDA down stalls input reading as well as the aux "
               "outputs until the driver's nine-clock recovery frees it. "
               "⛔ Still no lamp on it: lighting stays native (BD-5)"),
    Net("SCL", _p("U401.IO14 U402.SCK U403.SCK R435.1") + _stack("SCL")
        + _p("U304.SCK"), domain="3V3", gpio="GPIO14", interface="STACK",
        source="I²C clock, onto the MCP23017's pin 12 'SCK'. Crosses STACK to "
               "expander #3, as SDA does"),
    Net("MCP_INT", _p("U402.INTA U401.IO35"), domain="3V3", gpio="GPIO35",
        source="Interrupt from expander #1, IOCON.MIRROR = 1. GPIO35 is free "
               "because the module is an -N8 (no octal PSRAM)"),
    Net("TWAI_TX", _p("U401.IO10 U404.D"), domain="3V3", gpio="GPIO10",
        source="To the transceiver's D. CAN hardware is fitted; D19 parks the "
               "feed"),
    Net("TWAI_RX", _p("U404.R U401.IO21"), domain="3V3", gpio="GPIO21",
        source="From the transceiver's R"),
    Net("CAN_RS", _p("U404.RS R442.1 R472.1"), domain="3V3",
        source="Mode pin, held high by R472: standby, the driver off, while "
               "CAN is parked (D19). R442 to GND is slope control, unfitted"),
    Net("UART1_TX", _p("U401.IO17") + _stack("UART1_TX") + _ctrl("UART1_TX")
        + _p("R436.1"), domain="3V3", gpio="GPIO17", interface="CTRL",
        source="Class E: tri-stated whenever the module is not sending. The pin "
               "is on LOGIC and R436 on POWER with J404, so the 3.3 V logic node "
               "crosses STACK and then CTRL and the harness wire crosses "
               "nothing"),
    Net("UART1_TX_WIRE", _p("R436.2 J404.2 D404.K3"), domain="3V3",
        source="J404.2, RED/BLACK, labelled 'RXD'. Class E: direct 3.3 V on "
               "the shared ground (plan §4). ⬜ M9: direction and level are "
               "MEASURED, not read off the label"),
    Net("UART1_RX_WIRE", _p("J404.1 D404.K1 R443.1"), domain="3V3",
        source="J404.1, BROWN/BLUE, labelled 'TXD'. IN-13, a listen-only tap "
               "on the shared ground. ⬜ M9 as UART1_TX_WIRE"),
    Net("UART1_RX", _p("R443.2") + _ctrl("UART1_RX") + _stack("UART1_RX")
        + _p("U401.IO18"), domain="3V3", gpio="GPIO18", interface="CTRL",
        source="IN-13 behind its 1 kΩ, which sits on POWER with J404: the "
               "controller's unmeasured TX level (⬜ M9) never reaches a contact "
               "of the stack, let alone the pin"),
    Net("BOOST_CMD", _p("U401.IO48") + _stack("BOOST_CMD") + _ctrl("BOOST_CMD")
        + _p("R424.1"), domain="3V3", gpio="GPIO48", interface="CTRL",
        source="A DEDICATED native pin, never on a bus: a garbled bus frame "
               "must not be able to assert boost (plan §3.1.1). It crosses STACK "
               "and CTRL to Q401's gate resistor on POWER; an open contact leaves "
               "the gate on R425's pull-down, which is boost OFF (D14)"),
    Net("BOOST_GATE", _p("R424.2 Q401.G R425.1"), domain="3V3",
        source="R425 is the hard pull-down: boost defaults OFF through the "
               "boot's high-Z window (D14)"),
    Net("BOOST_OUT", _p("Q401.D J404.5 D407.K1"), domain="12V",
        source="Open-drain to the controller's CruisePin (PIN17). 12 V class "
               "until the wire is metered; its pull-up must meter ≤ 15 V "
               "(plan §7.1)"),
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
    *_class_a_nets("R409", "R420", "C408", "IN07_BOOST_BTN", "GPB3",
                   f"{_BOOST_BTN_AT} {_BOOST_BTN_LINE}",
                   f"The throttle's red button, a 2-pin dry-contact lead: it is "
                   f"an INPUT, so it joins the inputs row on {_INPUTS_A}.2 with "
                   f"the row's return on {_INPUTS_A}.1 -- not the serial "
                   f"terminal, whose other four wires go to the controller. ⬜ M8 "
                   f"confirms the lead. GPB3, never GPA7: that bit is "
                   f"output-only"),
    *_class_a_nets("R410", "R421", "C409", "IN08A_RUNNING", "GPB0",
                   "J403.2 D403.K1", "Right pod 'black', slider 2 and 3"),
    *_class_a_nets("R411", "R422", "C410", "IN08B_HEADLIGHT", "GPB1",
                   "J403.3 D403.K3", "Right pod 'yellow', slider 3 only"),
    *_class_a_nets("R477", "R478", "C438", "IN11_RUN", "GPB2",
                   "J403.4 D403.K4",
                   "Right pod 'red': the run/off toggle, a plain contact "
                   "(IO-8). Firmware treats it as a kill slot; no hardware "
                   "depends on it"),
    Net("START", _p("R412.1 R423.1 J403.5 D403.K6"), domain="3V3",
        source="Right pod GREEN, the start button: a spare sensed input that "
               "closes to the pod's shared ground. Class A, like every other "
               "bar contact"),
    Net("START_SENSE", _p("R423.2 C411.1 U402.GPB4"), domain="3V3",
        source="The conditioned start-button node at expander #1's GPB4"),
    *(net for bit, where, pull, series, cap, tvs in _SPARE_LINES
      for net in _class_a_nets(pull, series, cap, f"SPARE_{bit[2:]}", bit,
                               f"{where} {tvs}",
                               f"{where.split('.')[0]}, a free input of the "
                               f"INPUTS row: one of expander #2's spare bits, "
                               f"conditioned and ready to wire (IO-1)",
                               expander="U403")),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — the aux block on OUTPUTS (IO-1, IO-2): four 12 V outputs on a third
# TPS4H160B, four 5 V outputs on a buck and four load switches, all commanded
# by expander #3.  ⚠️ Every one of them is OFF until firmware drives the
# expander: its bits come out of reset as inputs, each TPS4H160B channel input
# has its own 100-250 kΩ pull-down, and each load switch's enable has R365-R368
# to ground (D14).  Nothing here is a hardware function.
# ════════════════════════════════════════════════════════════════════════════
#: Which bit of expander #3 carries each 5 V channel's enable and fault, in
#: channel order. GPA6 then GPB0-2 for the enables, GPB3-6 for the flags: the
#: bits left once the third TPS4H160B's five and the AUX12 enable have theirs,
#: and ⛔ never GPA7 or GPB7, which are output-only and could not read a flag.
_AUX5V_EN_BITS = ("GPA6", "GPB0", "GPB1", "GPB2")
_AUX5V_FAULT_BITS = ("GPB3", "GPB4", "GPB5", "GPB6")

def _aux12_nets(n: int) -> tuple[Net, ...]:
    """One 12 V aux channel: the command from expander #3, the device side of
    its series resistor, and the output on its way to the terminal."""
    return (
        Net(f"AUX12_{n}_CMD", _p(f"U304.GPA{n - 1} R{353 + n}.1"), domain="3V3",
            source=f"12 V aux {n}, commanded on expander #3's GPA{n - 1} "
                   f"(IO-1). {_AUX_OFF}"),
        Net(f"AUX12_{n}_IN", _p(f"R{353 + n}.2 U303.IN{n}"), domain="3V3",
            source=f"Device side of R{353 + n}"),
        Net(f"AUX12V_{n}", _p(f"U303.OUT{n} R{359 + n}.1 J313.{2 * n - 1} "
                              f"D{326 + n}.K"), domain="12V",
            source=f"12 V aux output {n}: 1 A (IO-2) out of a TPS4H160B "
                   f"channel identical to the lamp channels -- current limit "
                   f"at 1.12-1.55 A (R359), current sense on CS2_RAW, "
                   f"OFF-state open-load detect through R{359 + n}, and a "
                   f"clamp at the terminal. Its return is the GND contact "
                   f"beside it on J313"),
    )


def _aux5v_nets(n: int) -> tuple[Net, ...]:
    """One 5 V aux channel: the switched output, its enable, its fault flag
    and the node that sets its current limit."""
    return (
        Net(f"AUX5V_{n}", _p(f"U{305 + n}.OUT J314.{2 * n - 1} D{330 + n}.K"),
            domain="5V",
            source=f"5 V aux output {n}: 1 A (IO-2) through U{305 + n}, "
                   f"limited at 1.19-1.39 A, with its return on the GND "
                   f"contact beside it on J314. ⚠️ What D{330 + n} does and "
                   f"does not protect is IO-12, stated once in that part's "
                   f"own source"),
        Net(f"AUX5V_{n}_EN", _p(f"U304.{_AUX5V_EN_BITS[n - 1]} "
                                f"U{305 + n}.EN R{364 + n}.1"), domain="3V3",
            source=f"5 V aux {n} enable, expander #3's "
                   f"{_AUX5V_EN_BITS[n - 1]}. Active high, and R{364 + n} "
                   f"holds it down: the switch is OFF from reset and stays "
                   f"off through any window where nothing drives the "
                   f"expander (D14)"),
        Net(f"AUX5V_{n}_FAULT", _p(f"U304.{_AUX5V_FAULT_BITS[n - 1]} "
                                   f"U{305 + n}.FAULT R{368 + n}.1"),
            domain="3V3",
            source=f"5 V aux {n} fault flag, read on expander #3's "
                   f"{_AUX5V_FAULT_BITS[n - 1]}: LOW means over-current, "
                   f"over-temperature or reverse voltage on that channel, "
                   f"after the part's 5-10 ms deglitch. Pulled up by "
                   f"R{368 + n}"),
        Net(f"AUX5V_{n}_ILIM", _p(f"U{305 + n}.ILIM R{372 + n}.1"),
            domain="3V3",
            source=f"5 V aux {n}: the node R{372 + n} sets the current limit "
                   f"on. ⛔ Never shorted or left open -- open is the part's "
                   f"minimum limit and a short is its maximum"),
    )


_NETS_AUX = (
    *(net for n in range(1, 5) for net in _aux12_nets(n)),
    Net("DIAG3_CMD", _p("U304.GPA4 R358.1"), domain="3V3",
        source="Expander #3's GPA4: U303's own diagnostics enable. It is "
               "separate from U301/U302's DIAG_EN precisely so the three "
               "devices can share CS2_RAW and FAULT2_DEV -- the firmware "
               "raises one at a time"),
    Net("DIAG3_EN_IN", _p("R358.2 U303.DIAG_EN"), domain="3V3",
        source="Device side of R358"),
    Net("CL3", _p("U303.CL R359.1"), domain="3V3",
        source="U303's current-limit programming node, 0.8 V across R359"),
    # ── the 5 V aux supply ──────────────────────────────────────────────────
    Net("V5AUX",
        _p("L301.2 U305.BIAS R377.1 R379.2 C317.1")
        + _p(" ".join(f"C{317 + i}.1" for i in range(1, 9)))
        + _p(" ".join(f"U{305 + n}.IN C{325 + n}.1" for n in range(1, 5))),
        domain="5V",
        source="The 5 V AUX rail: U305's output, 4.86-5.17 V, feeding the "
               "four load switches and nothing else. ⛔ Not the logic's 5 V "
               "(V5, the Cincon's isolated output on POWER): a shorted aux "
               "wire must not be able to brown out the S3, which is the whole "
               f"reason this buck exists (spec §8.4). U305's BIAS pin is tied "
               f"here -- {_DS_LM736} p.31, 'TI recommends tying to VOUT when "
               f"3.3 V ≤ VOUT ≤ 18 V… to improve efficiency'"),
    Net("V5AUX_SW", _p("U305.SW L301.1 C314.2"), domain="12V",
        source="U305's switch node, between the half-bridge and the inductor: "
               "it swings the full 0-12 V at 500 kHz and carries the "
               "bootstrap capacitor's return leg. ⚠️ The loop U305, L301 and "
               "the input capacitors make is the noisiest copper on OUTPUTS; "
               "keep it small and away from CS2_RAW"),
    Net("V5AUX_BOOT", _p("U305.CBOOT C314.1"), domain="12V",
        source="The bootstrap node above V5AUX_SW: C314 supplies the "
               "high-side gate driver. 5 V above SW at most, and SW reaches "
               "V12, so it is 12 V-class copper"),
    Net("V5AUX_VCC", _p("U305.VCC C315.1"), domain="5V",
        source=f"U305's internal bias LDO output, decoupled by C315. "
               f"{_DS_LM736} p.3: 'TI does not recommend loading this pin by "
               f"external circuitry'; its absolute maximum is 5 V (p.5)"),
    Net("V5AUX_SS", _p("U305.SS/TRK C316.1"), domain="3V3",
        source="U305's soft-start node: C316 charges off the pin's 2 µA and "
               "sets the ramp. ⛔ Never shorted to ground (p.3)"),
    Net("V5AUX_FB", _p("U305.FB R377.2 R378.1"), domain="3V3",
        source="U305's feedback node, the midpoint of R377/R378 at 1.006 V "
               "typical. ⛔ 'Never short this pin to ground during operation' "
               "(p.3)"),
    Net("V5AUX_PG", _p("U305.PGOOD R379.1"), domain="5V",
        source="U305's power-good flag behind its pull-up: HIGH when V5AUX is "
               "in regulation. ⚠️ Nothing reads it -- it is a test point"),
    *(net for n in range(1, 5) for net in _aux5v_nets(n)),
)

_NETS = (_NETS_84V + _NETS_RAILS + _NETS_12V + _NETS_BRAKE + _NETS_STACK
         + _NETS_DISPLAY + _NETS_LOGIC + _NETS_CLASS_A + _NETS_AUX)

# ════════════════════════════════════════════════════════════════════════════
# CONNECTORS. One keyed, latched shell per harness bundle: ⛔ "colour is never
# evidence on this bike", and a keyed shell makes a mis-plug impossible where
# colour cannot. All right-angle and edge-facing (BD-8).
# ════════════════════════════════════════════════════════════════════════════
def _cp(pin: str, net: str, note: str = "") -> ConnPin:
    return ConnPin(pin, net, note)


def _empty_ways(first: int, last: int, why: str) -> tuple[ConnPin, ...]:
    """Positions `first`..`last` of a terminal with nothing landed on them, as
    J403 carries its sixth: the terminal is bought larger than its conductors
    need so that its SIZE is one no other terminal of its pitch has. A plug
    seats in any header of its pitch at least its size, so with every plug
    seated each one is forced into the header of exactly its own size, and a
    unique size cannot be swapped without leaving a plug in the hand
    (tests/test_interconnect.py). `why` is said once, on the first empty way."""
    return tuple(_cp(str(n), "", f"empty way: {why}" if n == first else "empty way")
                 for n in range(first, last + 1))


#: Every wire into the box lands on a pluggable screw terminal (owner,
#: 2026-09-18): nothing to crimp, no housing to match.  (pitch mm, positions) ->
#: (the right-angle header JLC places, the loose screw plug the owner wires).
#: One maker's pair, so they mate by construction; the LOCKING version, whose
#: plug screws to the header's flanges, because a bike vibrates.
#: ⛔ No 16-way 3.81: the Kangnex header (C508942) has 2 in stock at JLC, so the
#: inputs row is two 8-way terminals instead (J409, J410).
#: A size no connector uses is REMOVED, so every code here is a code the design
#: orders and the LCSC fixture records: 5.08 × 4 went with J306's move to the
#: 3.81 row. (3.81, 7) is BACK, for the 12 V aux terminal J313: an eight-way
#: there would seat in J409 and J410, the two general-input terminals, which
#: are 3.81 × 8 -- so the 12 V row and the inputs row share a pitch and never a
#: size (tests/test_rows.py).
#: (3.81, 10) and (3.81, 12) are J303 and J305 (IO-24): no two 12 V terminals
#: may share a size either, every size 2-9 at 3.81 mm is taken, and the 11-way
#: header (C3030059) is stock 0, so the two that grow take the smallest stocked
#: sizes nothing else uses. Their extra ways are EMPTY -- no net, no pin on any
#: part -- and the 12 V row they lengthen to 220.28 mm is the one stated
#: exception to the 90 % design margin (tests/test_board_params.py).
_TERMINALS = {
    (3.50, 8): ("C441263", "C441113"),
    (3.81, 2): ("C133147", "C62113"), (3.81, 3): ("C160129", "C106871"),
    (3.81, 4): ("C160127", "C157472"), (3.81, 5): ("C50223", "C50222"),
    (3.81, 6): ("C160126", "C157470"), (3.81, 7): ("C489994", "C489981"),
    (3.81, 8): ("C189319", "C62102"),
    (3.81, 9): ("C489995", "C384932"),
    (3.81, 10): ("C160125", "C157469"),
    (3.81, 12): ("C508940", "C193771"),
    (5.08, 2): ("C63299", "C63303"), (5.08, 3): ("C49238", "C49239"),
    (5.08, 5): ("C49240", "C49241"), (5.08, 9): ("C508920", "C508910"),
    (7.62, 6): ("C441304", "C441154"),
}
#: Per family, from its drawings: header height and depth, the length N x pitch +
#: `extra` over both locking flanges, the hole, the pins below the body (nominal
#: plus the drawing's tolerance), how far the mated plug stands past the
#: header's face (its length less the part inside the header), and what the
#: plug takes.
_TB_FAMILY = {
    3.50: dict(maker="Kefa", ds=_DS_KF350, h=7.00, deep=9.20, extra=10.40, hole=1.40,
               lead=3.70 + 0.30, overhang=15.60 - 6.70,
               plug="28-16 AWG (1.5 mm²), strip 7-8 mm, 0.2 N·m",
               rating="300 V / 8 A UL, 160 V / 7 A IEC"),
    3.81: dict(maker="Kangnex", ds=_DS_KX381, h=7.25, deep=9.20, extra=0.88 + 2 * 4.80, hole=1.40,
               lead=3.50 + 0.20, overhang=16.30 - 6.70,
               plug="28-16 AWG (1.5 mm²), strip 6-7 mm, 0.2 N·m",
               rating="300 V / 8 A UL, 160 V / 7 A IEC"),
    5.08: dict(maker="Kangnex", ds=_DS_KX508, h=8.30, deep=12.20, extra=10.16, hole=1.60,
               lead=4.00 + 0.20, overhang=17.60 - 8.80,
               plug="24-12 AWG (2.5 mm²), strip 7-8 mm, 0.4 N·m",
               rating="300 V / 10 A UL, 320 V / 15 A IEC"),
    7.62: dict(maker="Kefa", ds=_DS_KF762, h=8.60, deep=12.15, extra=10.16, hole=1.60,
               lead=4.00 + 0.30, overhang=18.10 - 8.45,
               plug="24-12 AWG (2.5 mm²), strip 7-8 mm, 0.4 N·m",
               rating="300 V / 10 A UL, 630 V / 15 A IEC"),
}


def _tb(refdes: str, board: Board, name: str, pins: tuple[ConnPin, ...],
        parked: bool = False, pitch: float = 3.81, note: str = "") -> Connector:
    """A pluggable screw terminal: a right-angle header at the board edge and a
    screw plug, wired outside the box and pushed in from the side, where the
    stack cannot block a screwdriver.  A parked one keeps its footprint but not
    its header: with no header there is nothing for a stray plug to seat in."""
    f = _TB_FAMILY[pitch]
    n = len(pins)
    length = round(n * pitch + f["extra"], 2)
    return Connector(refdes, board, name, pins, f["h"], height_confirmed=True,
                     footprint_mm=(length, f["deep"]), pitch_mm=pitch, parked=parked,
                     dnp=parked, lead_mm=f["lead"], overhang_mm=f["overhang"],
                     source=f"{f['ds']} p.1: locking pluggable screw terminal, "
                            f"right-angle header {f['h']:.2f} mm above the board "
                            f"and {f['deep']:.2f} deep, N × {pitch} + {f['extra']:g} = "
                            f"{length:g} mm long over its flanges, ø{f['hole']:.2f} "
                            f"holes, pins {f['lead']:.2f} mm max below the body. The "
                            f"mated plug stands {f['overhang']:.1f} mm past the "
                            f"header's face. The plug screws to the flanges and takes "
                            f"{f['plug']}. {f['rating']}" + (f". {note}" if note else ""))


def _bus(nets: tuple[str, ...]) -> tuple[ConnPin, ...]:
    return tuple(ConnPin(str(i + 1), n) for i, n in enumerate(nets))


def _keyed_bus(contacts: tuple[tuple[str, str], ...]) -> tuple[ConnPin, ...]:
    """A bus whose contact numbers are the MAKER'S: a body with a post omitted
    as a key numbers its circuits over the whole body, so the key is a hole in
    the numbering here and a hole in the land pattern there."""
    return tuple(ConnPin(pin, net) for pin, net in contacts)


#: The two JST VH crimp contacts and the wire each one takes (VH series
#: drawing p.2, "Contact"). ⛔ SVH-21T-P1.1 STOPS AT AWG #18: the conductors
#: that carry 8.47 A are 16 AWG and take the SVH-41T-P1.1. A survey that wrote
#: "SVH-21T-P1.1 class, 22-16 AWG" had read across the two rows of that table,
#: and a 16 AWG wire does not crimp into a 22-18 barrel.
VH_CONTACTS = {"SVH-21T-P1.1": (22, 18), "SVH-41T-P1.1": (20, 16)}

#: PWR-OUT's loom, conductor by conductor: net -> (AWG, crimp contact, why).
#: ⭐ The gauge is the whole current story now: a cable does not spread a load
#: over contacts, it sizes the wire, and JST states this header's 10 A rating
#: AT AWG #16 -- so the conductor and the rating come off the same line of the
#: same drawing, and the check cannot be satisfied by one without the other.
#: The housings and crimps are owner-buys: JLC places board parts only.
PWROUT_LOOM = {
    "V12": (16, "SVH-41T-P1.1", "the whole 8.47 A of IO-10, out"),
    "GND": (16, "SVH-41T-P1.1", "the same 8.47 A back: ⛔ the ONLY sized "
                                "return between the boards, since the brass "
                                "standoffs are bonded at the OUTPUTS end only "
                                "(IO-21)"),
    "V5": (22, "SVH-21T-P1.1", "~0.6 A to LOGIC's regulator, passing through "
                               "OUTPUTS to J307"),
    "KEY_SENSE": (22, "SVH-21T-P1.1", "a divided sense node, ~0 A"),
}


def pwrout_loom_ends() -> tuple[tuple[str, int, str], ...]:
    """What the owner buys to make PWR-OUT's loom, as (maker part, qty, why):
    the housing at each end and a crimp contact on each end of each conductor,
    COUNTED from `PWROUT_LOOM`, so a conductor cannot be added without the
    contacts that terminate it. ⛔ None of it is on LCSC, and it is genuine JST
    (Digi-Key / Mouser) for the same reason the header is: a clone housing's
    lock and contact plating are the parts of the 10 A figure nobody can see."""
    housing, circuits, empty = PWROUT_HOUSING
    ends = [(f"JST {housing}", 2,
             f"the {circuits}-circuit housing with cavity {'/'.join(empty)} "
             f"left EMPTY, one per end of the loom")]
    by_crimp: dict[str, list[tuple[str, int]]] = {}
    for net, (awg, crimp, _) in PWROUT_LOOM.items():
        by_crimp.setdefault(crimp, []).append((net, awg))
    for crimp, nets in by_crimp.items():
        thinnest, thickest = VH_CONTACTS[crimp]
        ends.append((f"JST {crimp}", 2 * len(nets),
                     f"the AWG #{thinnest}-#{thickest} crimp, both ends of "
                     + " and ".join(f"{n} ({awg} AWG)" for n, awg in nets)))
    return tuple(ends)


def _signal_gnd_pins(signals: tuple[str, ...]) -> tuple[ConnPin, ...]:
    """2 × len(signals): odd = signal, even = GND. One column per signal, so a
    signal spine cannot silently run out of contacts or carry an empty one.
    Both signal spines are built from it, so neither can drift from its list."""
    pins = []
    for i, net in enumerate(signals):
        pins.append(ConnPin(str(2 * i + 1), net))
        pins.append(ConnPin(str(2 * i + 2), "GND"))
    return tuple(pins)


#: Said once for both general-input terminals: the INPUTS row's spare capacity.
_INPUTS_NOTE = (
    "The INPUTS row's general terminals (IO-4): 13 free class-A inputs and the "
    "boost button, on TWO 8-way headers rather than one 16-way, because the "
    "Kangnex 3.81 × 16 header has 2 in stock at JLC and these are FITTED. Every "
    "contact is conditioned on this board (1 kΩ pull-up to 3V3, an SMS05T1G "
    "line, 1 kΩ series and 100 nF at the pin), so a wire needs no board change: "
    "for a dry contact to ground or 3.3 V logic, ⛔ nothing above 5 V. The two "
    "are the same size ON PURPOSE -- they carry the same class of contact, and a "
    "plug swapped between them misreads spares and the boost button, which the "
    "firmware's own input health catches"
)

#: The MATED PAIR that spans OUTPUTS ↔ LOGIC, said once for all four halves.
#: The two bodies butt insulator to insulator and that IS the board spacing:
#: 2.5 (header insulator) + 8.5 (socket body) = 11.00 mm on PWR-LOGIC, 2.54 +
#: 8.5 = 11.04 on STACK. ⚠️ STACK is therefore the hard stop and PWR-LOGIC's
#: insulators sit 0.04 mm apart -- far inside tolerance, and worth saying which
#: is which. A 6.0 mm pin in an 8.5 mm bore leaves 2.5 mm of headroom, so it is
#: the PLASTIC that stops, not the pin.
_INTERBOARD = ("Hong Cheng 2.54 mm, gold flash over brass, 3 A, 1000 V AC "
               "withstanding, 20 mΩ, -40…+105 °C, PA6T (HC-PZ254-11.5L-1x9PZ "
               "and HC-PM254-8.5H-*PZ drawings, 1 of 1 each; the BOOMELE strip "
               "PZ2.54-2xNA-11.4MM). Body sizes come from `hc_body`, each "
               "half's own rule. The two bodies BUTT, and their sum is the "
               "board spacing")

#: The two POWER ↔ OUTPUTS crossings (IO-20, 2026-09-20). No stocked connector
#: spans that gap, so a LOOM carries it, and the loom takes the orientation:
#: neither half faces the other and neither is mirrored, and neither land
#: pattern is pre-mirrored.
#:
#: ⭐ BOTH HALVES LOOK INTO THE GAP THE CABLE CROSSES — the POWER half standing
#: on POWER's top, the OUTPUTS half hanging under OUTPUTS — and that is the
#: freedom a loom buys, NOT a licence to put a body anywhere. Two facts fix it,
#: and both were found when the stack model stopped counting a cabled half as a
#: mated pair (which had hidden every body in this paragraph):
#:   * ⛔ ON OUTPUTS' TOP FACE THE BODY DOES NOT FIT AND THE LOOM CANNOT REACH
#:     IT. The STACK pair stops OUTPUTS → LOGIC at 11.04 mm and J311's posts
#:     stand 10.9 mm: 0.14 mm of air under LOGIC, no room for the VHR housing,
#:     and 8.6 mm of box header beside it. The loom would also have to leave
#:     the inter-board gap and come back round the board's edge, where the
#:     envelope gives it 1.0 mm on the far side (SIDE_CLEARANCE) and the
#:     connector face on the near one.
#:   * ✅ UNDER OUTPUTS IT IS FREE. The M3×30 standoffs set POWER → OUTPUTS at
#:     30.0 mm, so a 10.9 mm body hanging into it clears by 18.1 mm and the
#:     loom runs straight between the two headers. The keep-out it costs is
#:     stated by `board_params` exactly as J314's is: nothing on POWER taller
#:     than 18.1 mm beneath it, which L101/L102 at 22.0 are.
#: ⚠️ The 22 mm figure that once argued for a top face was a facing pair of
#: SHROUDS, 22 mm per end, against a 25.1 mm gap. A cable has no facing pair
#: and the standoffs made the gap 30.0: neither half of that argument survives.
_CABLED = ("A CABLE crossing (IO-20): no stocked connector spans the "
           "POWER→OUTPUTS gap, so a loom carries it and the M3×30 standoffs "
           "set that gap at 30.0 mm. The cable takes the orientation, so this "
           "half neither faces its mate nor is mirrored; both halves look into "
           "the 30.0 mm gap the loom crosses, the POWER half standing on top "
           "and the OUTPUTS half hanging under, because OUTPUTS' top face has "
           "11.04 mm under LOGIC and this body needs more")

#: PWR-OUT's connector: JST's VH locking header, top entry, five circuits wide
#: with the third post omitted. ⛔ THE TRAP, and it is the Blue Sea failure
#: again: "VH" CLONES ARE RATED 3 A. CAX's VH-4A-HT (C5453989) lists
#: identically — same series name, same 3.96 mm pitch, same 4P, cheaper, in
#: stock — and at 8.47 A that is a 2.8× overload. This part is GENUINE JST or
#: it is the wrong part.
_VH = (f"LCSC C594237: JST B4P(5-3)-VH(LF)(SN), a VH locking header, top entry, "
       "PA 66 UL94V-0 with brass tin-plated posts. ⛔ GENUINE JST, never a "
       "'VH' clone (CAX VH-4A-HT C5453989 lists the same series, pitch and 4P "
       "at 3 A — a 2.8× overload here). 10 A AC/DC per contact with AWG #16 "
       f"and 250 V, from {_DS_VH} p.1, which states ONE current "
       "figure and no derating for the number of circuits loaded; its "
       "-25…+85 °C range is stated to INCLUDE the rise the current causes, "
       "which is where a fully loaded connector is really held. Wafer 3.2 "
       "thick and 8.5 deep, posts □1.14 standing 7.7 above it and 3.7 below "
       "the board, body ways × 3.96 - 0.06 = 19.74 long; JST's PCB layout "
       "calls for ø1.65 +0.1 holes, not the 1.0 mm a 0.64 mm post takes, "
       "and the land is drilled ø1.73 so that JLC's -0.08 finishes on JST's "
       "1.65 minimum, clear of the post's 1.612 diagonal")
#: The loom's OTHER half, said beside the header so both ends of PWR-OUT are
#: specified from one place and neither can be ordered without the other.
_VHR = ("The loom mates a JST " + PWROUT_HOUSING[0] + " housing with cavity "
        + "/".join(PWROUT_HOUSING[2]) + " left EMPTY -- the five-circuit housing "
        f"of this five-circuit body, B = 19.74 in JST's housing table ({_DS_VH} "
        "p.2). ⛔ Never the VHR-4N: it mates the 15.78 mm B4P-VH, has cavities "
        "1-4 only and cannot carry contact 5. OWNER-BUY, genuine JST, none of it "
        "on LCSC: " + "; ".join(f"{qty} × {mpn}, {why}"
                                for mpn, qty, why in pwrout_loom_ends()))
#: The post tips, 3.2 mm of wafer plus 7.7 mm of post above the board.
_VH_H = 10.9
_VH_LEAD = 3.7
#: The post is □1.14 (_DS_VH p.1), so its diagonal, 1.14 × √2 = 1.612 mm, is
#: what the finished hole must clear.
_VH_POST = 1.14
#: JLC drills a plated hole +0.13/-0.08 on the figure it is given.
_JLC_HOLE_UNDER = 0.08
#: The drill both VH lands use. JST's PCB layout says ø1.65 +0.1/0 -- a
#: guideline, its note 4 says -- and 1.65 is the LOW end of that band: drilled
#: at 1.65, a low batch finishes at 1.57, under the post's 1.612 diagonal, and
#: the header does not go in. 1.73 puts JLC's low side ON JST's 1.65 minimum
#: (1.73 - 0.08 = 1.65 > 1.612 by 0.038) and its high side at 1.86, 0.11 over
#: JST's 1.75. `footprints.header()` keeps a 0.35 mm ring around whatever it
#: drills, so the pad is 2.43 mm (tests/test_footprint_binding.py).
_VH_HOLE = 1.73
assert _VH_HOLE - _JLC_HOLE_UNDER > _VH_POST * 2 ** 0.5, (
    "a low-tolerance batch of VH lands will not take the header's post")
_VH_KEY = ("the wafer's lock ramp stands proud on ONE wall, and the "
           + PWROUT_HOUSING[0] + " housing (cavity " + "/".join(PWROUT_HOUSING[2])
           + " empty) has its cutout on one side, so a housing offered the other "
           "way round meets the ramp and cannot seat; the omitted third post "
           "keys it against a plug of any other size. ⚠️ The OMISSION is not "
           "what polarises it: JST's post-omitted page gives polarity to an "
           "omission at the 2nd or (N-1)th circuit and says a symmetric one "
           "gives none, and the third post of five is symmetric — the ramp "
           "does that work. ⬜ Confirm on the first sample that a reversed "
           "housing will not go down; if it will, the loom needs the shrouded "
           "VH (B5P-VH-FB-B) instead")

#: CTRL's connector: a DIN 41651 shrouded box header at each end of a 24-way
#: ribbon. Its POLARISING NOTCH is the whole reason 24 ways were taken over 22
#: (the family has no 22-way member): the alternative was a bare header the
#: socket could be pushed onto either way round.
_DC3 = (f"LCSC C5144580: ZHOURI DC3-2.54-24PAS, a 2×12 shrouded box header, "
        "glass-filled PBT UL94V-0, brass contacts gold over nickel. 1.5 A per "
        "contact, 500 V AC for one minute, 20 mΩ, -40…+105 °C; pins □0.64 on "
        "2.54, shroud 8.6 ±0.15 above the board, tails 3.1 ±0.1, body "
        "2.54 × N/2 + 7.6 = 38.08 by 8.4 ±0.15 — the drawing prints that rule "
        f"on the part ({_DS_DC3} p.1). Its cable end "
        "is the FC-2.54-24P IDC socket, ordered from LCSC with the boards "
        "(`_LOOSE_BY_MPN`, one per header), on 3M 3365/24 ribbon, which LCSC "
        "does not carry")
_DC3_H = 8.6
_DC3_LEAD = 3.1
_DC3_KEY = ("a 4.5 ±0.15 mm polarising notch in the shroud with the pin-1 "
            "triangle beside it: the IDC socket's key enters it one way round "
            "only, and nothing else enters at all")

#: ⬜ What neither drawing dimensions: how deep the plug goes in, and so how
#: tall the MATED assembly stands. Said once, on every cabled half, because it
#: is the same gap in both drawings — and because the figure that would settle
#: it must be measured, never typed from a bound.
_MATED_UNKNOWN = ("⬜ height_mm is the BARE header off the drawing; the mated "
                  "height is undimensioned there, so it is not confirmed — "
                  "measure it on the first sample. Nothing rests on it: the "
                  "standoffs set this gap, not these two halves")

_CONNECTORS = (
    # ── POWER ───────────────────────────────────────────────────────────────
    _tb("J101", "POWER", "Pack entry: B+, two B− returns and the key tap on one "
        "plug. The KLKD003 in its FEB-11-11 holder is UPSTREAM IN THE HARNESS, "
        "not a board part", (
            _cp("1", "HV_BPLUS", "84 V tap, downstream of the XT90-S"),
            _cp("2", "", "empty: a pitch of air between B+ and the returns"),
            _cp("3", "GND", "B− to the controller's stud"),
            _cp("4", "GND", "B−, second conductor: one open return cannot push "
                            "the input current through a signal ground"),
            _cp("5", "", "empty: a pitch of air between the key tap and the "
                         "returns, so no strand can pull KEY down"),
            _cp("6", "KSW", "the key switch's OUTPUT, 84 V with the key on; "
                            "~0.3 mA of gate drive and sense. The switch, its "
                            "own 2 A inline fuse and the FarDriver KEY wire "
                            "are harness -- not the 3 A KLKD003 on pin 1's "
                            "branch"),
        ), pitch=7.62, note="The only 7.62 mm terminal, so no other plug seats "
                            "in it and its plug seats in no other header. 84 V "
                            "sits 7.62 mm from its return (BD-4)"),
    Connector("J202", "POWER", "PWR-OUT, POWER side, on top of the board: "
              "V12 and GND at 8.47 A, V5, KEY_SENSE", _keyed_bus(_PWROUT_CONTACTS),
              _VH_H, footprint_mm=vh_body(_PWROUT_WAYS), pitch_mm=3.96,
              hole_mm=_VH_HOLE, contact_a=10.0, keyed=_VH_KEY,
              leaves_box=False, interface="PWR-OUT", lead_mm=_VH_LEAD,
              source=f"{_CABLED}. {_VH}. {_VHR}. {_MATED_UNKNOWN}"),
    Connector("J105", "POWER",
              f"CTRL, POWER side, on top of the board: 2 × {_CTRL_WAYS // 2}, "
              f"the controller row's signals with a ground on both sides of "
              f"each", _bus(_CTRL_NETS),
              _DC3_H, footprint_mm=_CTRL_FP, leaves_box=False, interface="CTRL",
              hole_mm=1.0, contact_a=1.5, keyed=_DC3_KEY, lead_mm=_DC3_LEAD,
              source=f"{_CABLED}. {_DC3}. {_MATED_UNKNOWN}"),
    _tb("J309", "POWER", "FarDriver motor cut and throttle supply sense: BL "
        "out, ACC+ in", (
            _cp("1", "BL", "yellow/green, OUT. ⛔ Not grey BH — High Brake "
                           "stays capped"),
            _cp("2", "GND", "BL's only neighbour: a strand bridging them "
                            "grounds BL, which CUTS the motor -- fail-safe. Land "
                            "it at the controller's B− stud (brake-circuit §9), "
                            "not a signal ground: it parallels J101's returns"),
            _cp("3", "ACC_PLUS", "the throttle's 5.1 V, IN — the ACC_SENSE "
                                 "divider's source, a sensor only"),
        ), pitch=5.08, note="5.08 mm is the FarDriver row's pitch and nothing "
                            "else's (IO-6): a 12 V plug cannot seat here, which "
                            "is what keeps 12 V out of the controller's 3.3 V "
                            "logic. The only 3-way at this pitch"),
    _tb("J404", "POWER", "FarDriver serial + boost (5 conductors)", (
        _cp("1", "UART1_RX_WIRE", "brown/blue, labelled 'TXD' — ⬜ M9, measure"),
        _cp("2", "UART1_TX_WIRE", "red/black, labelled 'RXD' — ⬜ M9"),
        _cp("3", "", "brown/green = BW5V, 5 V OUT of the controller; unused. "
                     "⚠️ Never feed a 3.3 V-only adapter from it"),
        _cp("4", "GND", "black — serial ground, the reference for every "
                        "measurement"),
        _cp("5", "BOOST_OUT", "CruisePin PIN17, colour unknown. ⛔ METER FIRST"),
    ), pitch=5.08, note="The FarDriver row's pitch (IO-6); the only 5-way in it"),
    _tb("J310", "POWER", "FarDriver one-line in. ⏸️ Footprint fitted, parked "
        "with the display (D19)", (
            _cp("1", "FD_ONELINE", "brown, 0-15 V"),
            _cp("2", "GND"),
        ), parked=True, pitch=5.08,
        note="The FarDriver row's pitch (IO-6): its lead comes off the same "
             "controller harness as J404's and J309's"),
    _tb("J405", "POWER", "Display, 9-pin. ⏸️ Footprint fitted, parked with D19", (
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
    ), parked=True, pitch=5.08,
        note="In the controller row with the rest of the dash wiring (IO-5), at "
             "the FarDriver pitch: the panel's CAN pair and its one-line share "
             "the controller's grounds"),
    # ── OUTPUTS ─────────────────────────────────────────────────────────────
    _tb("J301", "OUTPUTS", "Headlight (M4). ⛔ The assembly's RED lead is unused: "
        "do not land it", (
            _cp("1", "GND", "black — lamp common (M4)"),
            _cp("2", "HL_HIGH", "green — HIGH beam"),
            _cp("3", "HL_LOW", "blue — LOW beam"),
            _cp("4", "HL_DRL", "yellow — DRL"),
        )),
    _tb("J302", "OUTPUTS", "Tail + rear signals (M5/M6)", (
        _cp("1", "GND", "black — lamp common (M5)"),
        _cp("2", "TAIL_RUN", "yellow — running, 0.05 A"),
        _cp("3", "TAIL_STOP", "red — STOP, 0.12 A, on U302 OUT4, commanded by "
                              "firmware from GPIO19 (IO-8)"),
        _cp("4", "TURN_L", "blue — rear LEFT (M6)"),
        _cp("5", "TURN_R", "green — rear RIGHT (M6)"),
    )),
    _tb("J303", "OUTPUTS", "Front turn L/R, two isolated 2-wire pairs, on a "
        "TEN-way terminal (IO-24)", (
            _cp("1", "TURN_L", "front LEFT feed"),
            _cp("2", "GND", "front LEFT return. ⬜ M6: confirm the front pair may "
                            "share the tail common"),
            _cp("3", "TURN_R", "front RIGHT feed"),
            _cp("4", "GND", "front RIGHT return"),
            *_empty_ways(5, 10, "ten ways for four conductors, so this plug has "
                                "a size no other 12 V terminal has (IO-24). As a "
                                "4-way it swapped with J301 [G,+,+,+] and J305 "
                                "[+,-,+,-] -- a lamp common held at +12 V, or a "
                                "load driven reversed. Every size 2-9 at 3.81 mm "
                                "is taken and the 11-way header is stock 0, so 10 "
                                "and 12 are the sizes left. The front lamps are a "
                                "fixed pair that will not gain conductors, so this "
                                "terminal takes the smaller, 10; the fan + buzzer "
                                "terminal, where a third accessory pair is the "
                                "likely addition, takes 12"),
        )),
    _tb("J304", "OUTPUTS", "Horn (M7)", (
        _cp("1", "AUX12", "⛔ BLUE IS THE POSITIVE"),
        _cp("2", "HORN_N", "black = '-'. ⛔ Red is not the positive"),
    )),
    _tb("J305", "OUTPUTS", "Fan + buzzer, on a TWELVE-way terminal (IO-24)", (
        _cp("1", "AUX12", "fan +"),
        _cp("2", "FAN_RTN", "fan -, flyback D307"),
        _cp("3", "AUX12", "buzzer +"),
        _cp("4", "BUZZ_RTN", "buzzer -, flyback D314"),
        *_empty_ways(5, 12, "twelve ways for four conductors, so this plug has "
                            "a size no other 12 V terminal has (IO-24). As a "
                            "4-way it swapped with J301 [G,+,+,+] and J303 "
                            "[+,G,+,G]: the headlight's plug here puts AUX12 "
                            "on the lamp common and its beams on the fan and "
                            "buzzer returns, loads driven REVERSED. J303 took "
                            "10, the smaller of the two "
                            "sizes left; this terminal takes 12 because a third "
                            "accessory pair (a second fan, a relay coil) is the "
                            "likely addition to it, and the eight empty ways "
                            "carry the 12 V row to 220.28 mm, 91.0 % of the "
                            "board -- accepted by the owner 2026-09-21 as the one "
                            "exception to the 90 % design margin"),
    )),
    _tb("J313", "OUTPUTS", "12 V aux 1-4 (IO-1): four feeds alternating with "
        "three shared returns, in the 12 V row", tuple(
            cp for n in range(1, 5)
            for cp in ((_cp(str(2 * n - 1), f"AUX12V_{n}",
                            f"aux {n} +, 1 A, current-limited at 1.12-1.55 A"),)
                       + ((_cp(str(2 * n), "GND",
                               f"return for aux {n} and aux {n + 1}, whichever "
                               f"of the two is wired to it"),)
                          if n < 4 else ()))),
        note="SEVEN ways, not eight: 3.81 × 8 is what the two general-input "
             "terminals are (J409, J410), and a plug of this row must not be "
             "able to seat in one of theirs. So the four feeds alternate with "
             "THREE grounds rather than four: each load's return goes to a "
             "ground contact beside its own feed, and since every ground is "
             "between two feeds no contact can carry more than two loads -- "
             "2 A against this family's 8 A rating"),
    replace(
        _tb("J314", "OUTPUTS", "5 V aux 1-4 (IO-1): each output with its own "
            "return, in the 5 V row UNDER the board", tuple(
                cp for n in range(1, 5)
                for cp in (_cp(str(2 * n - 1), f"AUX5V_{n}",
                               f"aux {n} +, 1 A, limited at 1.19-1.39 A"),
                           _cp(str(2 * n), "GND", f"aux {n} return"))),
            pitch=3.50,
            note="3.50 mm is the 5 V row's pitch and nothing else's (IO-6): "
                 "no 12 V plug can seat here, which is what keeps 12 V out of "
                 "a 5 V device. It hangs under OUTPUTS because the 5 V row is "
                 "the underside of that board (IO-7), so its plugs come off "
                 "the same face of the box as every other row's, one row "
                 "below the 12 V terminals"),
        side="bottom"),
    Connector("J311", "OUTPUTS", "PWR-OUT, OUTPUTS side, under the board: "
              "V12 for the drivers and the 5 V buck, GND back, V5 and "
              "KEY_SENSE on up to J307", _keyed_bus(_PWROUT_CONTACTS), _VH_H,
              footprint_mm=vh_body(_PWROUT_WAYS), pitch_mm=3.96, hole_mm=_VH_HOLE,
              contact_a=10.0, keyed=_VH_KEY, leaves_box=False,
              interface="PWR-OUT", lead_mm=_VH_LEAD, side="bottom",
              source=f"{_CABLED}. {_VH}. {_VHR}. {_MATED_UNKNOWN}"),
    Connector("J307", "OUTPUTS", "PWR-LOGIC, OUTPUTS side: V5 and KEY_SENSE up "
              "to LOGIC, 3.3 V back down, ground on every other contact",
              _bus(_PWRLOGIC_NETS), 8.5, height_confirmed=True,
              footprint_mm=hc_body(len(_PWRLOGIC_NETS), rows=1, socket=True),
              leaves_box=False, contact_a=3.0, lead_mm=3.0,
              interface="PWR-LOGIC",
              source=f"The SOCKET, LCSC C22373895: HC-PM254-8.5H-1x9PZ, body "
                     f"8.5 ±0.15 tall over the board and (B+0.4)±0.3 long, "
                     f"2.4 ±0.15 wide, tails 3.0 ±0.2, ø1.02 holes ({_DS_HC_PM} p.1). "
                     f"{_INTERBOARD}"),
    Connector("J308", "OUTPUTS",
              f"STACK, OUTPUTS side: 2 × {_STACK_ROWS}, alternating grounds",
              _signal_gnd_pins(_STACK_SIGNALS), 8.5, height_confirmed=True,
              footprint_mm=_STACK_SOCKET_FP, contact_a=3.0, lead_mm=3.0,
              leaves_box=False, interface="STACK",
              source=f"The SOCKET, LCSC C41376169: HC-PM254-8.5H-2x{_STACK_ROWS}PZ, body "
                     f"8.5 ±0.15 tall and (B+0.4)±0.3 long by 5.0 ±0.15 — ⛔ "
                     f"5.0, not the 5.08 the pitch suggests. Tails 3.0 ±0.2, "
                     f"ø1.02 holes ({_DS_HC_PM} p.1). This is the pair that STOPS: 8.5 + 2.54 = "
                     f"11.04 mm, 0.04 mm more than PWR-LOGIC's 11.00, so "
                     f"J307's insulators sit that far apart. {_INTERBOARD}"),
    Connector("J312", "OUTPUTS",
              f"CTRL, OUTPUTS side, under the board: 2 × {_CTRL_WAYS // 2}, "
              f"a ground on both sides of every signal", _bus(_CTRL_NETS),
              _DC3_H, footprint_mm=_CTRL_FP, leaves_box=False, interface="CTRL",
              hole_mm=1.0, contact_a=1.5, keyed=_DC3_KEY, lead_mm=_DC3_LEAD,
              side="bottom",
              source=f"{_CABLED}. {_DC3}. {_MATED_UNKNOWN}"),
    # ── LOGIC ───────────────────────────────────────────────────────────────
    _tb("J402", "LOGIC", "Left pod: 9-way shell, 8 conductors. The module "
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
    _tb("J403", "LOGIC", "Right pod, 5 conductors on 6 ways. The slider is OFF / A / "
        "A+B, so headlight implies running IN HARDWARE", (
            _cp("1", "GND", "blue — ⛔ GROUND FOR ALL THREE CONTROLS"),
            _cp("2", "IN08A_RUNNING_WIRE", "black — running (IN-08a), closed "
                                           "in slider positions 2 and 3"),
            _cp("3", "IN08B_HEADLIGHT_WIRE", "yellow — headlight (IN-08b), "
                                             "closed in position 3 only"),
            _cp("4", "IN11_RUN_WIRE", "red — run/off toggle, a class-A "
                                      "contact read by firmware (IO-8)"),
            _cp("5", "START", "green — start button, a spare sensed input"),
            _cp("6", "", "empty: six ways, a size no other terminal has, so a "
                         "swap with the tail's 5-way plug (which would hold "
                         "IN11_RUN_WIRE to ground through a lamp) always leaves "
                         "a plug in the hand"),
        )),
    _tb("J306", "LOGIC", "Brake levers — plain inputs (IO-8), in the INPUTS "
        "row. ⬜ GATED ON M3", (
            _cp("1", "LEVER_L", "⬜ M2 identifies the wires in loom '1T3 10'"),
            _cp("2", "GND", "the levers' shared return, between the two "
                            "contacts: a strand off either lever wire meets "
                            "ground, which READS AS BRAKING -- the safe way for "
                            "an input to fail"),
            _cp("3", "LEVER_R", "⬜ M3: a 3-wire Hall lever adds a supply "
                                "contact and changes this terminal's size"),
        ), note="3.81 mm with the rest of the INPUTS row (IO-6): a mismated "
                "input plug puts 3.3 V through 1 kΩ somewhere harmless, and the "
                "only 3-way at this pitch, so the plug seats nowhere else"),
    Connector("J406", "LOGIC",
              f"STACK, LOGIC side, under the board: 2 × {_STACK_ROWS}, "
              f"alternating grounds", _signal_gnd_pins(_STACK_SIGNALS), 2.54,
              height_confirmed=True, footprint_mm=_STACK_HEADER_FP,
              contact_a=3.0, lead_mm=3.0,
              leaves_box=False, interface="STACK", side="bottom",
              source=f"The HEADER, LCSC C2333: a BOOMELE 2.54-2*40P strip CUT "
                     f"TO 2×{_STACK_ROWS}, insulator 2.54 (⚠️ not Hong Cheng's 2.5 — the "
                     f"0.04 mm that makes this pair the stop), pins 6.00 +0.2 "
                     f"above it and 3.0 ±0.2 below the board, body N × 2.54 "
                     f"long because the cut falls on the grid, 5.0 ±0.1 wide, "
                     f"ø1.0 holes ({_DS_BOOM} p.1). 3 A, 550 V AC, 20 mΩ, -55…+105 °C, PBT. "
                     f"{_INTERBOARD}"),
    Connector("J407", "LOGIC", "PWR-LOGIC, LOGIC side, under the board",
              _bus(_PWRLOGIC_NETS), 2.5, height_confirmed=True,
              footprint_mm=hc_body(len(_PWRLOGIC_NETS), rows=1, socket=False),
              contact_a=3.0, lead_mm=3.0,
              leaves_box=False, interface="PWR-LOGIC", side="bottom",
              source=f"The HEADER, LCSC C27985193: HC-PZ254-11.5L-1x9PZ, "
                     f"insulator 2.5 (its H) with 6.0 mm of pin into the "
                     f"socket and 3.0 ±0.2 below the board, body B ±0.3 long "
                     f"by 2.50 wide, ø1.02 holes ({_DS_HC_PZ} p.1). 2.5 + 8.5 = 11.00 mm, "
                     f"insulator to insulator: a 6.0 mm pin in an 8.5 mm bore "
                     f"has 2.5 mm to spare, so the PLASTIC is the stop. "
                     f"{_INTERBOARD}"),
    Connector("J408", "LOGIC", "Service pads, INTERNAL: a Tag-Connect TC2030-NL "
              "land on UART0 — first flash, the console, and recovery when OTA "
              "fails (hold IO0 low, pulse EN, flash over UART0)", (
        _cp("1", "EN", "ESP-Prog ESP_EN"),
        _cp("2", "", "VDD — not connected: the board powers itself, and the "
                     "ESP-Prog's VDD is jumpered 3.3 V or 5 V, so 5 V here "
                     "would reach the S3's rail"),
        _cp("3", "U0TXD_HDR", "GPIO43 through R475: ESP-Prog ESP_TXD0"),
        _cp("4", "GND"),
        _cp("5", "U0RXD", "GPIO44: ESP-Prog ESP_RXD0"),
        _cp("6", "BOOT_IO0", "ESP-Prog ESP_IO0"),
    ), 0.0, height_confirmed=True, footprint_mm=(6.07, 3.02), leaves_box=False,
        pitch_mm=1.27, dnp=True, land="TC2030-NL",
        source="Bare copper, nothing fitted: the cable's spring pins press on "
               "the pads while it is held there. Tag-Connect 'Footprint for "
               "TC2030 (No-Legs)' rev B (NL-TC2030-Footprint.pdf p.1, note 4: "
               "DNL in the BOM; drawn_footprints.tag_connect_tc2030_nl). "
               "Pads numbered as the ESP-Prog's 2 × 3 PROG header (Espressif "
               "SCH_ESP32-PROG_V2.1: 1 ESP_EN · 2 VDD · 3 ESP_TXD0 · 4 GND · "
               "5 ESP_RXD0 · 6 ESP_IO0, TXD0/RXD0 the target's own pins — "
               "FT_RXD ← ESP_TXD0), and the TC2030-IDC-NL cable takes pad n "
               "to IDC pin n, so the cable plugs straight into an ESP-Prog, "
               "whose DTR/RTS drive EN and IO0 for an automatic download. "
               "Any USB-serial adapter at 3.3 V does as well, wired to the "
               "IDC end. 0 mm: nothing stands above the board"),
    _tb(_INPUTS_A, "LOGIC", "General inputs A: the boost button and expander "
        "#2's GPA spares, class-A contacts to ground (IO-1)", (
            _cp("1", "GND", "the row's return: every contact on this terminal "
                            "and on J410 closes to it"),
            _cp("2", "IN07_BOOST_BTN_WIRE", "the throttle's red button (IN-07), "
                                            "beside its own return. ⬜ M8 "
                                            "confirms the 2-pin lead"),
            *_spare_cps(_INPUTS_A),
        ), note=_INPUTS_NOTE),
    _tb(_INPUTS_B, "LOGIC", "General inputs B: expander #2's GPB spares, "
        "class-A contacts to ground (IO-1)", (
            *_spare_cps(_INPUTS_B),
            _cp("8", "GND", "this terminal's return"),
        ), note=_INPUTS_NOTE),
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
    "SMS05T1G": ("C233428", "onsemi SMS05T1G", "Extended", "the part itself"),
    "SMF6.0A": ("C19077499", "SMF6.0A (R+O)", "preferred Extended",
                "200 W, V_RWM 6.0 V, V_BR 6.67-7.37 V, V_C 10.3 V @ 19.4 A; "
                "the unidirectional 'A' grade, never the bidirectional 'CA'"),
    "SS14": ("C2480", "MDD SS14", "Basic", "40 V / 1 A Schottky"),
    "M7": ("C95872", "MDD M7", "Basic", "1000 V / 1 A, 30 A surge"),
    "BZT52B10": ("C22395568", "BZT52B10 (R+O)", "preferred Extended",
                 "V_Z 9.8-10.2 V"),
    "BZT52B15": ("C22395570", "BZT52B15 (R+O)", "preferred Extended",
                 "V_Z 14.7-15.3 V; the 5 % C grade reaches 13.8 V, too near "
                 "the -13.1 V running V_GS"),
    "AO3400A": ("C20917", "AOS AO3400A", "Basic", "the part itself"),
    "BSS127": ("C152611", "Infineon BSS127H6327XTSA2", "Extended",
               "enhancement mode, V_GS(th) 2.6 V max; not the Diodes "
               "BSS127S-7, whose 4.5 V max is above D13_EN at 43 V"),
    "IXTA26P20P-TRL": ("C3291074", "IXYS IXTA26P20P-TRL", "Extended",
                       "DS99913D, the IXTP's die in TO-263"),
    "MCP23017T-E/SS": ("C558584", "Microchip MCP23017T-E/SS", "Extended",
                       "DS20001952D Table 2-1: SSOP, SOIC and SPDIP share pins 1-28"),
    "SN65HVD230DR": ("C12084", "TI SN65HVD230DR", "preferred Extended", "the part itself"),
    "TLV803SDBZR": ("C132016", "TI TLV803SDBZR", "Extended",
                    "the part itself, unfitted; no Basic supervisor exists"),
    "TLV76733DGNR": ("C2873382", "TI TLV76733DGNR", "Extended",
                     "the part itself; stock is thin (34). Pin-compatible fallback "
                     "TLV76701DGNR C3752401 needs an FB divider"),
    "TPS4H160BQPWPRQ1": ("C471053", "TI TPS4H160BQPWPRQ1", "Extended",
                         "version B; never the A version, C485918"),
    "LM73605RNPR": ("C473342", "TI LM73605RNPR", "Extended",
                    "the two Basic bucks carry 3 A (TPS5430, and "
                    "non-synchronous) and 2 A (XL1509), both under the 5 A "
                    "this rail is sized for; LM73606 C544826 is the 6 A "
                    "pin-to-pin part if more headroom is ever wanted"),
    "TPS2553DBVR": ("C55266", "TI TPS2553DBVR", "Extended",
                    "no Basic power-distribution switch exists. The DBVR of "
                    "the TPS2553 -- active-high EN, constant-current limit; "
                    "⛔ never the TPS2552 (inverted enable) or a '-1' "
                    "(latch-off) part"),
    "IHLP2525CZER4R7M01": ("C553961", "Vishay IHLP2525CZER4R7M01", "Extended",
                           "4.7 µH, I_sat 10 A, shielded; no Basic inductor "
                           "meets TI's saturation figure at this size"),
    "ESP32-S3-WROOM-1U-N8": ("C2980297", "Espressif ESP32-S3-WROOM-1U-N8", "Extended",
                             "-40…+85 °C; never the 65 °C N8R8 / N16R8"),
    "CGA9N1C0G2J683JT0Y0S": ("C2175506", "TDK CGA9N1C0G2J683JT0Y0S", "Extended",
                             "C0G, 630 V, ±5 %"),
}

#: Parts ordered from LCSC with the boards but fitted by the owner, because
#: JLC would fit them wrong: through-hole parts that must LIE on the board
#: (the height budget counts them flat; JLC inserts upright), the fuse, which
#: clips into its holder, and a cable end that plugs onto a header (named by
#: `_MATE_BY_REFDES`). mpn -> (LCSC, maker part, per refdes, why).
_LOOSE_BY_MPN = {
    "EKXJ221ELL221MM25S": ("C1600234", "Chemi-Con EKXJ221ELL221MM25S", 1,
                           "bent over and bonded LYING on POWER's underside"),
    "VY2472M49Y5US6": ("C2251831", "Vishay VY2472M49Y5US6TV7", 1,
                       "X1/Y2, kinked 7.5 mm leads on reel: bent FLAT"),
    "PA35V680M10x15": ("C46550429", "JIERR PA35V680M10x15", 1,
                       "680 µF 35 V polymer, 16 mΩ: bent over LYING"),
    "0001.2504": ("C1665055", "Schurter 0001.2504", 1, "clipped into FH201"),
    "01110501Z": ("C151075", "Littelfuse 01110501Z", 2,
                  "two clips, soldered into FH201's footprint"),
    "FC-2.54-24P": ("C5274612", "ZHOURI FC-2.54-24P", 1,
                    "the 2×12 IDC socket pressed onto each end of the CTRL "
                    "ribbon (3M 3365/24): one per header, 1.5 A per contact, "
                    "-45…+105 °C, the same Zhouri family as the header"),
}

#: The cable end that plugs onto each half of a CABLED crossing (IO-20), by
#: refdes, so a loom's two ends are bought with its two headers and neither
#: half can be ordered without what mates it. The mpn is an `_LOOSE_BY_MPN`
#: entry (ordered from LCSC with the boards) or the PWR-OUT housing, which is
#: owner-buy off LCSC (`pwrout_loom_ends`). ⛔ Every cabled half is here or
#: `tests/test_interconnect.py` fails: a header with no mate is a loom that
#: cannot be built.
_MATE_BY_REFDES = {
    "J105": "FC-2.54-24P", "J312": "FC-2.54-24P",
    "J202": PWROUT_HOUSING[0], "J311": PWROUT_HOUSING[0],
}


def loose_per(mpn: str) -> int:
    """How many of a loose part each refdes takes (FH201: two clips)."""
    return _LOOSE_BY_MPN[mpn][2]


def mates() -> dict[str, tuple[str, ...]]:
    """mpn -> the cabled halves it plugs onto, from `_MATE_BY_REFDES`."""
    out: dict[str, list[str]] = {}
    for ref, mpn in _MATE_BY_REFDES.items():
        out.setdefault(mpn, []).append(ref)
    return {mpn: tuple(refs) for mpn, refs in out.items()}


#: Parts LCSC cannot supply to their constraints: the owner buys them and
#: solders them by hand (owner, 2026-09-18). mpn -> why.
_HAND_BY_MPN = {
    "CN150B110-12/CO": "nothing on LCSC takes 43-160 V in and gives 12 V at "
                       ">= 8.47 A with stock: the TDK brick, in hand",
    "EC7BW-110S05": "the Cincon is in hand; LCSC's nearest 43-160 V 5 V module "
                    "(YLPTEC URB1D05LD-20WR3, C19724292) numbers its pins "
                    "differently and states its isolation two ways",
    "7448022010": "LCSC has none of the Würth choke; its nearest (YDFW1212T, "
                  "C16197255) has 2.4x the DCR and no voltage rating. Two in "
                  "hand, of which L102 now takes one",
    "7448023005": "the 3 A Type S the aux load needs (IO-13): LCSC lists it as "
                  "C1534621 with NO STOCK, and no common-mode choke on LCSC is "
                  "Basic. To buy -- Digi-Key product 9863721, or Mouser",
}


#: The board-to-board STANDOFFS, and the gap each one holds (IO-20, IO-21).
#:
#: ⭐ THEY ARE IN THE DESIGN (`Design.standoffs`) and `board_params.layer_gaps`
#: derives a gap from them, which is what closed the last hole in the height
#: model: it knew a thing that STANDS IN a gap, and a connector PAIR whose
#: mated bodies ARE the gap, and had no term for a pillar that DEFINES one.
#: They are not `Part`s and must not become ones -- an ordinary part is cleared
#: by CLEARANCE, which would derive a gap 1.0 mm taller than the standoff and
#: fail the 11.04 mm connector stop the nylon one is deliberately specified
#: short under. The mounting holes themselves are already board geometry
#: (`board_params` subtracts the four M3 corners); this table is what goes
#: through them, and it is ordered from LCSC with the boards.
#: ⭐ IO-21, owner 2026-09-21: the brass posts are bonded to GND at the OUTPUTS
#: END ONLY, landing on a copper-free pad at POWER. Defined potential beside
#: POWER's 84 V pins, and NO second path between the boards -- ⛔ bonding both
#: ends would put the return on two paths, the 16 AWG conductor the budget
#: sizes and an unrated one through brass threads and screw torque that nothing
#: checks and that changes as fasteners age.
STANDOFFS = (
    Standoff(
        "Shuntian M3X30", "C775781", 4, 30.0, ("POWER", "OUTPUTS"), "sets",
        "POWER → OUTPUTS: brass, female-female, 30.0 ±0.2 (inspected 29.96-29.98), "
        "hex 4.7 AF. ⭐ This is what sets that gap: no connector spans it any more. "
        "BRASS, not nylon -- rigidity is the standoffs' whole job now, nylon creeps "
        "under preload so the screws back off, LCSC's nylon M3 range stops at 20 mm, "
        "and 94V-2 is the weakest flame class to put on the 84 V board. ⚠️ The cost "
        "is a post at chassis potential beside POWER's 84 V pins: pay it in layout "
        "with a copper keep-out annulus (≈3.5 mm radius, both layers, mask over, no "
        "HV net inside it) around every POWER mounting hole. ⭐ BONDED TO GND AT THE "
        "OUTPUTS END ONLY (IO-21), on a copper-free pad at POWER: PWR-OUT's 16 AWG "
        "GND conductor stays the SOLE sized return for the 8.47 A, and bonding both "
        "ends would put that return on a second, unrated path through brass threads "
        "and screw torque that nothing checks and that changes as fasteners age"),
    Standoff(
        "HIWA TP-11", "C118174", 20, 11.0, ("OUTPUTS", "LOGIC"), "shimmed",
        "OUTPUTS → LOGIC: nylon 66 94V-2, M3×11+6 male-female, hex 5.5 AF, 11.0 "
        "±0.5 (HIWA drawing QR-JZ-34-TP-11: one-decimal dimensions ±0.5). ⚠️ That "
        "±0.5 mm is the whole problem: against the 11.04 mm CONNECTOR stop, a piece "
        "at 11.5 holds the boards apart and un-seats both pairs by 0.46 mm of their "
        "6.0 mm engagement -- 8 % of the wipe, on the stamped contacts -- while one "
        "at 10.5 is a pillar the screws pull LOGIC's corner 0.54 mm down onto. ✅ So "
        "it is specified DELIBERATELY SHORT and fitted by MEASURED LENGTH, with NO "
        "shim: the CONNECTORS set this gap and the standoff only stops the boards "
        "flexing apart. TWENTY are ordered for the FOUR fitted: measure every piece "
        "and fit the four that measure between 10.94 and 11.04 mm (`board_params` "
        "prints the window from the gap), rejecting anything over 11.04 outright; "
        "if fewer than four make the window, the remedy is another twenty, never "
        "a longer piece. ⛔ No shim, because no ~0.5 mm nylon M3 washer is stocked "
        "on LCSC -- the only 0.5 mm M3 washer listed (Tong Ming 290059, C5199342) "
        "is 304 stainless at zero stock, the XHHD 3M SUS (C24867) is stainless "
        "with no stated thickness, and a steel washer is a loose conductor at a "
        "mounting hole -- and because a 0.5 mm shim under a nominal 11.0 piece is "
        "0.46 mm OVER the stop: the shortfall it would take up is 0.04 mm. ⛔ The "
        "HIWA PN-3 (C115937) is a 2.4 mm-thick M3 NUT (drawing QR-JZ-74: B = 2.4; "
        "0.5 is its thread pitch): fitted as a shim it holds the boards 2.36 mm "
        "apart, off both pairs"),
)


def standoffs() -> tuple[Standoff, ...]:
    """The board-to-board standoffs. ⚠️ `STANDOFFS` is the one home for them,
    and `current()` hands them to the Design so `board_params` derives the
    POWER → OUTPUTS gap from the 30.0 mm brass post rather than from whatever
    the obstructions happen to need."""
    return STANDOFFS


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
        elif p.mpn in _LOOSE_BY_MPN:
            used.add(p.mpn)
            lcsc, maker, per, why = _LOOSE_BY_MPN[p.mpn]
            p = replace(p, lcsc=lcsc, assembly="loose",
                        source=f"{p.source}. LOOSE, LCSC {lcsc} × {per}: {maker}, "
                               f"ordered with the boards and fitted by the owner; {why}")
        elif p.mpn in _HAND_BY_MPN:
            used.add(p.mpn)
            p = replace(p, assembly="hand",
                        source=f"{p.source}. HAND-SOLDERED: {_HAND_BY_MPN[p.mpn]}")
        out.append(p)
    # A loose cable end is used by the header it plugs onto, not by a part.
    used |= set(_MATE_BY_REFDES.values())
    stale = (set(_FAB_BY_MPN) | set(_LOOSE_BY_MPN) | set(_HAND_BY_MPN)) - used
    if stale:
        raise ValueError(f"_FAB_BY_MPN entries no part uses: {sorted(stale)}")
    return tuple(out)


#: Connectors by refdes, for everything that is not a harness terminal: (LCSC,
#: maker part, who fits it, note), or ("hand", why). A harness terminal takes
#: its codes from `_TERMINALS` instead, by pitch and size.
#: ⚠️ `loose` here means the same as it does for a part: ordered from LCSC with
#: the boards and fitted by the owner, and JLC is told not to place it.
_FAB_CONN: dict[str, tuple[str, ...]] = {
    "J202": ("C594237", "JST B4P(5-3)-VH(LF)(SN)", "loose",
             "the keyed 10 A power header at each end of the loom"),
    "J311": ("C594237", "JST B4P(5-3)-VH(LF)(SN)", "loose",
             "the keyed 10 A power header at each end of the loom"),
    "J105": ("C5144580", "ZHOURI DC3-2.54-24PAS", "loose",
             "the shrouded box header the ribbon plugs into. ⚠️ 180 in stock "
             "and nothing behind it: buy spares with the first order"),
    "J312": ("C5144580", "ZHOURI DC3-2.54-24PAS", "loose",
             "the shrouded box header the ribbon plugs into"),
    "J307": ("C22373895", "Hong Cheng HC-PM254-8.5H-1x9PZ", "jlc",
             "the 8.5 mm socket half of the 11.00 mm pair"),
    "J407": ("C27985193", "Hong Cheng HC-PZ254-11.5L-1x9PZ", "jlc",
             "the 2.5 mm header half, under LOGIC"),
    "J308": ("C41376169", f"Hong Cheng HC-PM254-8.5H-2x{_STACK_ROWS}PZ", "jlc",
             "the 8.5 mm socket half of the 11.04 mm pair"),
    "J406": ("C2333", "BOOMELE(Boom Precision Elec) 2.54-2*40P", "loose",
             f"a 2×40 strip CUT TO 2×{_STACK_ROWS} and soldered into LOGIC's underside: "
             "the cutting is why JLC cannot place it"),
}


def _with_fab_conn(connectors: tuple[Connector, ...]) -> tuple[Connector, ...]:
    out = []
    for c in connectors:
        fab = _FAB_CONN.get(c.refdes)
        if c.leaves_box:
            header, plug = _TERMINALS[(c.pitch_mm, len(c.pins))]
            maker = _TB_FAMILY[c.pitch_mm]["maker"]
            c = replace(c, lcsc=header, plug=plug, assembly="jlc",
                        source=f"{c.source}. LCSC {header}: the {maker} header, JLC "
                               f"Extended; plug LCSC {plug}"
                               + (", not ordered while parked" if c.dnp else ", ordered loose"))
        elif fab and fab[0] == "hand":
            c = replace(c, assembly="hand", source=f"{c.source}. HAND-SOLDERED: {fab[1]}")
        elif fab:
            lcsc, maker, how, note = fab
            fits = ("ordered loose and fitted by the owner" if how == "loose"
                    else "placed by JLC")
            c = replace(c, lcsc=lcsc, assembly=how,
                        source=f"{c.source}. LCSC {lcsc}: {maker}, JLC "
                               f"Extended, {fits}; {note}")
        out.append(c)
    stale = set(_FAB_CONN) - {c.refdes for c in connectors}
    if stale:
        raise ValueError(f"_FAB_CONN entries for no connector: {sorted(stale)}")
    return tuple(out)


def lcsc_catalogue() -> dict[str, str]:
    """Every LCSC code the design orders, with the maker part number its table
    says it is. An LCSC record for the code must name that part: a changed
    code that points at a different part (the 65 °C ESP32, the BSS127S-7)
    otherwise passes every rule, which read the netlist MPN (review CK-5)."""
    out = {}
    for lcsc, maker, *_ in (*_R_LCSC.values(), *_C_LCSC.values(),
                            *_FAB_BY_MPN.values(), *_LOOSE_BY_MPN.values()):
        out[lcsc] = maker
    for fab in _FAB_CONN.values():
        if fab[0] != "hand":
            out[fab[0]] = fab[1]
    for so in STANDOFFS:
        out[so.lcsc] = so.name
    return out


def terminal_catalogue() -> dict[str, str]:
    """Each harness terminal's header and plug codes, with the pattern their
    maker part numbers follow: the header (RM) and plug (KM) of the family at
    that pitch and size."""
    out = {}
    for (pitch, n), (header, plug) in _TERMINALS.items():
        for code, half in ((header, "RM"), (plug, "KM")):
            out[code] = rf"EDG{half}-{pitch:g}-0?{n}P"
    return out


def class_a_problems(d: Design) -> list[str]:
    """Every class-A network sitting apart from the terminal it conditions.

    The pull-up's wire-side leg is on the contact's own net, and that net names
    the harness terminal, so the board is DERIVED both ways round and neither
    is typed. Empty on the design; `current()` refuses to hand out a design
    that is not."""
    out = []
    for pull, series, cap, net in _CLASS_A:
        wire = next((n for n in d.nets if (pull, "1") in n.pins), None)
        if wire is None:
            out.append(f"class A: {pull}.1 ({net}) is on no net, so nothing can "
                       f"say which terminal it conditions")
            continue
        refs = {r for r, _ in wire.pins}
        boards = {c.board for c in d.connectors if c.leaves_box and c.refdes in refs}
        if not boards:
            continue                    # an internal node: no terminal to be beside
        for ref in (pull, series, cap):
            if d.board_of(ref) not in boards:
                out.append(
                    f"class A: {ref} ({net}) is on {d.board_of(ref)}, but "
                    f"{wire.name} arrives on {'/'.join(sorted(boards))} -- the "
                    f"pull-up, the series resistor and the 100 nF belong on the "
                    f"board the contact lands on, or an unconditioned wire "
                    f"crosses an interface (plan §4, IO-6)")
    return out


def current() -> Design:
    """The design as it stands. The ONE API: `.parts`, `.nets`, `.connectors`
    and the lookups on `Design`. Nothing else builds a Design.

    ⚠️ UNGATED: this is the design as typed, whether or not it is a circuit.
    A tool's `main()` reads it through `checked()` below. `current()` is for
    the tests and fixtures that must construct a broken design on purpose."""
    design = Design(parts=_with_fab(_PARTS), nets=_NETS,
                    connectors=_with_fab_conn(_CONNECTORS), standoffs=STANDOFFS)
    problems = class_a_problems(design)
    if problems:
        raise ValueError("; ".join(problems))
    return design


class NotACircuit(ValueError):
    """`checked()` refused the design: `integrity.check` found problems. The
    message lists every one, so a tool that lets it through prints them."""


def checked() -> Design:
    """`current()`, gated on `tools.integrity`: the design only if it is a
    circuit, else `NotACircuit` listing every problem.

    ⛔ Every tool's `main()` reads the design through this and nothing else.
    Until 2026-09-21 only `build_project.py` ran integrity first, so a design
    integrity REJECTED -- a TVS with one leg in the air and a STACK pair that
    could not mate -- got `✅ PASS` from board_fit, gpio_budget, power_budget,
    soft_start, a full BOM from jlc_bom, a net class from layout_rules and
    "identical" from tel_check (H10). The documented run order was the only
    thing holding that together.

    `integrity` is imported here, not at module level: it imports `model`
    only today, and a lazy import keeps that graph acyclic if it ever needs
    the netlist."""
    from . import integrity
    design = current()
    problems = integrity.check(design)
    if problems:
        raise NotACircuit(
            f"{len(problems)} integrity problem(s) -- nothing is computed on a "
            f"design that is not a circuit. Run `python3 -m tools.integrity`.\n"
            + "\n".join(f"  {p}" for p in problems))
    return design
