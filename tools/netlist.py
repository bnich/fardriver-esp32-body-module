"""THE DESIGN: every part, net and connector of the four-board set.

Shape lives in `model.py`; this file is nothing but content, transcribed from
the signal-and-net inventory extracted 2026-09-15 from `docs/plan.md` (v0.9),
`docs/board-design-record.md` (BDR, which overrides the plan on partition),
`docs/bom.md`, `docs/inputs-bench-session.md` and
`../Revv1-FS-72v-Conversion/docs/brake-circuit.md` (BRK).

Every entry carries `source=`, naming the inventory section (§n.n) and the BOM
line or decision ID it came from, so a number can always be walked back to the
document that owns it.  ⬜ marks something no document states.

--- conventions, so nothing here has to be guessed at twice ---------------

1. REFDES is board-scoped in hundreds blocks (HVIN 1xx · CONV 2xx · DRV 3xx ·
   BRAIN 4xx) so refdes are unique across the four schematics.  The documents
   assign none.  Their own informal names (`D13`, `Q1`, `Q3`, `C1`, `R3L`, `F1`)
   are cited in `source=` because they are quoted across BRK/PLAN/BDR and must
   stay greppable.

2. PIN NAMES are functional, not pad numbers: the documents carry pin numbering
   for no device at all (inventory §2 preamble).  `gen_eprj3.py` binds
   `U401.IO15`, `U301.OUT2`, `D401.ch3` to real pads from the datasheets.
   Connector pin numbers are a GENERATOR-SIDE INDEX — for the pods the binding
   key is colour+gauge, never the cavity number (§3, verbatim: a map written in
   pin numbers "is wrong on one end of the pair by construction").

3. A SERIES ELEMENT CANNOT HAVE BOTH ENDS ON ONE NET.  Where the inventory
   writes a chain in one row (`U401.IO42 → R310 → Q301.G · R307`) this file
   splits it, and says so:
     · `*_GATE`  stays on the FET gate node, where the bias-OFF part lives
       (D14) — the MCU-side segment of those four is `*_CMD`;
     · `*_WIRE`  is the harness-side segment of a conditioned input/output,
       where the connector, the wire colour and the TVS live;
     · otherwise the segment that lands on the MCU/expander keeps the
       inventory's name, because §4.4's GPIO map is written in those names;
     · `*_MID` / `*_RC` are a divider's or an RC's internal node.

4. DOMAIN: `model.Domain` has no chassis or ground member.  `GND` (the single
   star net at the CONTROLLER's B− stud) and `BASEPLATE` (chassis) are
   therefore `SIGNAL`.  ⚠️ Tagging `GND` "84V" would trip
   `rules.bd2_voltage_domain_containment` for a net that legitimately appears
   on all four boards.  The model wants a CHASSIS/GND domain.

5. INTERFACE is single-valued but four nets cross more than one interface
   (`GND` all three; `V5`, `KEY_SENSE`, `RUN`, `START` two or three).  Rule
   applied: name the LOWEST crossing in stack order (HV-LINK < PWR-UP < STACK)
   and list every crossing in `source=`.

6. HEIGHTS are the datasheet envelopes already collected in the M19 block of
   `tools/board-fit.py` — ⚠️ mirrored, not imported, because that file is a
   script (`board-fit.py` is not an importable module name).  If one moves, move
   both.  `H_TBD` (NaN) is a part no document gives a height for; ⛔ NaN can
   never trip `rules.layer_height_ceilings`, so a TBD height is an unchecked
   height, not a safe one.

7. PLACEHOLDERS are loud: `value="TBD"`, `mpn="TBD-…"`.  Generic passives have
   no MPN because the BOM buys them by value (lines C1, D2, D9, G3, G6, H3), and
   ⬜ Q29 states no footprint is specified for any passive or discrete — 0805 /
   SOD-123 / DO-41 below are `board-fit.py`'s assumptions, flagged per part.

--- where this file DEPARTS from the inventory's own text ------------------

⭐ These four are decided; the inventory's prose may still show the old position.

  1. The four Y2 caps are on **CONV**, at the converter input terminals, not on
     HVIN (inventory §1.1 / §5 Q7; BOM E9 + PLAN §9.5.2 win over BDR §3 L1).
     Renumbered into CONV's series: C101–C104 → **C203–C206**.
  2. DRV gets **6 × `PESD5V0S4UD`** (D308–D313), one per harness connector —
     §5 Q6 flags their absence as a gap with DRV's 23 conductors unprotected.
     ⛔ SEE THE REPORTED DEFECT: `PESD5V0S4UD` is a 5 V (V_RWM) array and every
     DRV conductor except the lever pair is a 12 V net.  The part number is
     wrong for the job even though the protection is right.
  3. `U405`, BRAIN's 5 V→3.3 V regulator, is a real part with `mpn="TBD-3V3-REG"`
     and NO BOM LINE (§5 Q3).
  4. CONV's layer ceiling is **14.0 mm** (the Y2 discs, not the 12.7 mm brick) —
     already the value in `board_params.LAYER_CEILING_MM`.

--- nets the inventory names that are deliberately NOT here ----------------

A net needs two ends.  These have one, because the thing at the other end does
not exist yet; each is a documented gap, not an omission:

  `ACC_PLUS`      ⛔ Q9  the throttle's 5.1 V reaches no connector, so R314's
                        pull-up end has nowhere to land.
  `START_SENSE`   ⬜     conditioning unspecified (PLAN §2.0 "spare (sense)");
                        expander bit GPB3 is held for it.
  `BW5V`          ⬜     J404.3 exists; the module's use of it is never stated.
  `UART2_RX`      ⛔ Q17 no connector pin, and M9 may delete IN-14 entirely.
                        GPIO21 is held for it.
  `AMBIENT`       ⏸️ Q26 IN-16 parked, no connector.  GPIO6 is held for it.
  `DISP_V12`      ⬜ Q20 undecided whether the module lands display pin 2 at all
                        (D11/D19 parked); the cavity is carried, unconnected.
  `USB_VBUS`      ⬜ Q4  whether VBUS feeds anything is unspecified.
  `LGT_SPARE1/2`  §4.3 slack (A), which §4.4 applies: the two spare
                        `TPS4H160B` inputs stay UNCONNECTED and hold OFF on
                        their internal pulldowns.  That is what buys the map its
                        one spare GPIO.
  `MCP_A0/A1/A2`  ⬜ Q16 "different addresses" is all the documents say.
"""
from .model import Board, ConnPin, Connector, Design, Net, Part

#: The four boards, bottom to top (BD-1, BD-2: voltage falls with height).
BOARDS: tuple[Board, ...] = ("HVIN", "CONV", "DRV", "BRAIN")

# ── heights ── mirror of tools/board-fit.py's M19 block ──────────────────────
H_TBD = float("nan")   # ⬜ no document gives this part a height
H_0805 = 1.0           # generic passive, 0805 assumed (Q29)
H_SOT23 = 1.2
H_SOD123 = 1.1
H_SOT457 = 1.1         # PESD5V0S4UD, SOT457/TSOP6
H_DIP = 4.5            # DIP-14 / DIP-28
H_TO220 = 16.0         # IXTP26P20P, upright — floors HVIN's 18 mm ceiling
H_SMC = 2.6            # DO-214AB
H_CHOKE = 18.0         # ⬜ M19 ASSUMPTION: "≤18 mm"; confirming buys 2 mm
H_FILM = 9.0           # 2.2 µF film RC cap
H_FUSEHOLDER = 12.0    # ⬜ M19: Schurter FAC 0031.3803
H_Y2 = 14.0            # 12.5 mm disc + seating; 1.3 mm over the brick, which
                       # is why CONV's ceiling is 14.0 and the brick gets a
                       # spacer up to BD-9's plate
H_CAN = 18.0           # EKXJ221 18 × 25 mm can, lying down, UNDERSIDE (BD-14)

_INV = "NETLIST-INVENTORY 2026-09-15"


def _r(refdes: str, board: Board, value: str, source: str,
       package: str = "0805", height: float = H_0805) -> Part:
    """A resistor.  No MPN: the BOM buys these by value, and ⬜ Q29 specifies
    no footprint for any passive, so `package` is board-fit.py's assumption."""
    return Part(refdes, f"TBD-R-{value}", package, board, height,
                value=value, source=source)


def _c(refdes: str, board: Board, value: str, source: str,
       package: str = "0805", height: float = H_0805) -> Part:
    """A capacitor.  Same provenance caveat as `_r`."""
    return Part(refdes, f"TBD-C-{value}", package, board, height,
                value=value, source=source)


# ════════════════════════════════════════════════════════════════════════════
# PARTS — §1.  HVIN (L1): 84 V entry, protection, start latch.  Ceiling 18 mm.
# ════════════════════════════════════════════════════════════════════════════
_HVIN_PARTS = (
    Part("D101", "SMCJ90A", "DO-214AB (SMC)", "HVIN", H_SMC, vds_max=90.0,
         value="90 V standoff",
         source=f"{_INV} §1.1 BOM E12, PLAN §3.2.1. ⛔ not SMBJ90A/SMBJ100A/5KP90A"),
    Part("L101", "7448022010", "THT CM choke 10 mH/2 A/300 V", "HVIN", H_CHOKE,
         source=f"{_INV} §1.1 BOM E7, BDR §3 L1 'one per converter input, "
                f"before the bulk cap'. ⬜ M19: height assumed ≤18 mm"),
    Part("L102", "7448022010", "THT CM choke 10 mH/2 A/300 V", "HVIN", H_CHOKE,
         source=f"{_INV} §1.1 BOM E7. ⬜ M19 height assumed"),
    Part("Q101", "IXTP26P20P", "TO-220AB", "HVIN", H_TO220, vds_max=200.0,
         source=f"{_INV} §1.1 BOM E13, doc name 'D13' switch. PLAN §3.2.5, "
                f"selected on SOA (363 W @ 5 ms). ⭐ ramp is to be ~50 ms, not 10 ms"),
    Part("D102", "TBD-ZENER", "TBD", "HVIN", H_TBD, value="TBD",
         source=f"{_INV} §1.1 BOM E13 '+ zener' — gate zener for Q101. "
                f"⬜ Q11: value and package unspecified"),
    _r("R101", "HVIN", "TBD",
       f"{_INV} §1.1 BOM E13/H3 — D13 ramp RC with C105. ⬜ Q11: value "
       f"unspecified; ramp target ~50 ms, 'still unactioned' in both documents",
       package="TBD"),
    _c("C105", "HVIN", "TBD",
       f"{_INV} §1.1 BOM H3 — D13 ramp RC with R101. ⬜ Q11 value unspecified",
       package="TBD"),
    Part("U101", "74HC14", "DIP-14", "HVIN", H_DIP,
         source=f"{_INV} §1.1 BOM H1, BDR §3 L1. Runs off the 5 V logic rail "
                f"returned DOWN HV-LINK. ⚠️ DIP-14 on a 42 mm board (BDR §9)"),
    _r("R102", "HVIN", "1M",
       f"{_INV} §1.1 BOM H3 — latch RC with C106, the ~2 s start gesture "
       f"(PLAN §3.2.5a). ⬜ final values set on the bench"),
    _c("C106", "HVIN", "2.2uF film",
       f"{_INV} §1.1 BOM H3 '1 MΩ/2.2 µF film RC'. ⬜ final values on the bench",
       package="film THT", height=H_FILM),
    Part("Q102", "BSS126", "SOT-23", "HVIN", H_SOT23, vds_max=600.0,
         source=f"{_INV} §1.1 BOM H2 — 'pulls Q3's gate down from the latch'"),
    Part("Q103", "BSS126", "SOT-23", "HVIN", H_SOT23, vds_max=600.0, dnp=True,
         source=f"{_INV} §1.1 ⚠️ Q12 UNRESOLVED: BOM H2 reads 2 bought = 1 "
                f"fitted + 1 spare; BDR §3 L1 lists '2 × BSS126' fitted. Carried "
                f"as a footprint in parallel with Q102 and marked DNP until Q12 closes"),
    Part("Q104", "IXTP26P20P", "TO-220AB", "HVIN", H_TO220, vds_max=200.0,
         source=f"{_INV} §1.1 BOM E13, doc name 'Q3' — the start latch's KEY "
                f"switch (PLAN §3.2.5a). ⬜ M10 sizes it"),
    Part("D103", "TBD-15V-ZENER", "TBD", "HVIN", H_TBD, value="15V",
         source=f"{_INV} §1.1 BOM H3, BDR §3 L1 'Q3 IXTP26P20P + zener' — "
                f"15 V zener on Q104's gate. ⬜ MPN/package unspecified"),
    _r("R103", "HVIN", "100k",
       f"{_INV} §1.1 BOM H3 latch passive. ⬜ topology not stated — deliberately "
       f"assigned to NO net rather than guessing the latch arrangement (Q14 also "
       f"disputes the polarity that would decide it)"),
    _r("R104", "HVIN", "100k", f"{_INV} §1.1 BOM H3 latch passive. ⬜ topology not stated"),
    _r("R105", "HVIN", "10k", f"{_INV} §1.1 BOM H3 latch passive. ⬜ topology not stated"),
    _r("R106", "HVIN", "10k", f"{_INV} §1.1 BOM H3 latch passive. ⬜ topology not stated"),
    _r("R107", "HVIN", "TBD",
       f"{_INV} §1.1 BOM E14 — IN-12 divider TOP, 330 kΩ realised as a ¼ W "
       f"SERIES PAIR for voltage rating (PLAN §4 class B), so 2 parts not 1. "
       f"⬜ the split is not stated; only the pair's 330 kΩ total is",
       package="TBD (¼ W)"),
    _r("R108", "HVIN", "TBD",
       f"{_INV} §1.1 BOM E14 — second half of the 330 kΩ series pair. ⬜ split not stated",
       package="TBD (¼ W)"),
    _r("R109", "HVIN", "10k",
       f"{_INV} §1.1 BOM E14 — IN-12 divider BOTTOM. 84 V → 2.47 V (PLAN §3.1.3)"),
)

# ════════════════════════════════════════════════════════════════════════════
# PARTS — §1.2  CONV (L2): both converters.  Ceiling 14.0 mm, 66 % area — the
# only board without slack.  ⭐ CORRECTION 1: the four Y2 caps live HERE.
# ════════════════════════════════════════════════════════════════════════════
_CONV_PARTS = (
    Part("U201", "CN150B110-12/CO", "quarter brick 58.3 × 37.2 × 12.7 mm", "CONV",
         12.7, vds_max=160.0, value="43-160 V → 12 V / 12.5 A / 150 W",
         source=f"{_INV} §1.2 BOM E1, DC-DC #1. /CO = factory conformal coat. "
                f"⚠️ 160 V is a hard do-not-exceed, transients included"),
    Part("U202", "EC7BW-110S05", "50.8 × 25.4 × 10.2 mm", "CONV", 10.2,
         vds_max=160.0, value="43-160 V → 5 V / 4 A / 20 W, 3 kV iso",
         source=f"{_INV} §1.2 BOM E2, DC-DC #2. UVLO 40 V up / 38 V down"),
    Part("C201", "EKXJ221ELL221MM25S", "radial can 18 × 25 mm", "CONV", H_CAN,
         side="bottom", value="220uF/220V",
         source=f"{_INV} §1.2 BOM E8, doc name 'C1' — TDK's EMC bulk AT DC-DC #1's "
                f"input terminals. BD-14: mounts on L2's UNDERSIDE, lying down and "
                f"bonded, so it does not count against the 14 mm top-side ceiling"),
    Part("C202", "EKXJ221ELL221MM25S", "radial can 18 × 25 mm", "CONV", H_CAN,
         side="bottom", value="220uF/220V",
         source=f"{_INV} §1.2 BOM E8, doc name 'C2' — hold-up, BEHIND the diode on "
                f"DC-DC #2 alone. ⚠️ C1 and C2 are NOT interchangeable: a common "
                f"node collapses ride-out 237 ms → ~20 ms (PLAN §3.2.2). BD-14 underside"),
    Part("C203", "VY2472M49Y5US6", "radial disc, 12.5 mm body", "CONV", H_Y2,
         value="4700pF Y2",
         source=f"{_INV} §1.2 ⭐ Q7 RESOLVED TO CONV (was C101 on HVIN): BOM E9 + "
                f"PLAN §9.5.2 require it from +Vin to the BASEPLATE, close to the "
                f"terminals. DC-DC #1 +Vin. IEC 60384-14 safety cap"),
    Part("C204", "VY2472M49Y5US6", "radial disc, 12.5 mm body", "CONV", H_Y2,
         value="4700pF Y2",
         source=f"{_INV} §1.2 Q7 (was C102). DC-DC #1 −Vin → baseplate"),
    Part("C205", "VY2472M49Y5US6", "radial disc, 12.5 mm body", "CONV", H_Y2,
         value="4700pF Y2",
         source=f"{_INV} §1.2 Q7 (was C103). DC-DC #2 +Vin → baseplate. ⬜ §2.1 "
                f"only states C101.1 on HV_CONV1; splitting the four as ±Vin per "
                f"converter is this file's reading of BOM E9's '+Vin AND −Vin'"),
    Part("C206", "VY2472M49Y5US6", "radial disc, 12.5 mm body", "CONV", H_Y2,
         value="4700pF Y2",
         source=f"{_INV} §1.2 Q7 (was C104). DC-DC #2 −Vin → baseplate"),
    Part("D201", "1N4007", "DO-41 (assumed, Q29)", "CONV", 3.0, vds_max=1000.0,
         source=f"{_INV} §1.2 BOM E10 — hold-up blocking diode. PLAN §3.2.6a: "
                f"≥150 V reverse, ~1 A, surge ≥3 A, PLAIN SILICON. ⬜ package not stated"),
    Part("FH201", "FAC 0031.3803", "PCB THT holder, 5×20, 600 V UL", "CONV",
         H_FUSEHOLDER,
         source=f"{_INV} §1.2 BOM E6 (1 used on DC-DC #2, 2nd is a spare). ⬜ M19 height"),
    Part("F201", "0001.2504", "5×20 ceramic, 1 A T-lag, 300 VDC", "CONV",
         H_FUSEHOLDER, value="1A T-lag",
         source=f"{_INV} §1.2 BOM E11 — ⛔ order by PN: FST/SP/FSF have NO DC "
                f"rating. Height is the holder's, it sits in FH201"),
)

# ════════════════════════════════════════════════════════════════════════════
# PARTS — §1.3  DRV (L3): 12 V drivers + the D23 brake circuit.  Ceiling 6 mm.
# ⚠️ 40 V parts — the 12 V rail only, NEVER the 84 V node.
# ════════════════════════════════════════════════════════════════════════════
_DRV_PARTS = (
    Part("U301", "TPS4H160BQPWPRQ1", "28-HTSSOP, 0.65 mm, exposed pad", "DRV",
         H_SOT23, vds_max=40.0,
         source=f"{_INV} §1.3 BOM D1 — 4 ch high-side. ⚠️ the pad must reach real "
                f"copper or per-channel current limit and thermal shutdown misbehave"),
    Part("U302", "TPS4H160BQPWPRQ1", "28-HTSSOP, 0.65 mm, exposed pad", "DRV",
         H_SOT23, vds_max=40.0, source=f"{_INV} §1.3 BOM D1 — 4 ch high-side"),
    *[_r(f"R30{n}", "DRV", "20k",
         f"{_INV} §1.3 BOM D2 — OUT→VBAT, one per lighting channel, REQUIRED for "
         f"OFF-state open-load detect (PLAN §6.2.2a)") for n in range(1, 7)],
    Part("Q301", "AO3400A", "SOT-23", "DRV", H_SOT23, vds_max=30.0,
         source=f"{_INV} §1.3 BOM D3 — horn low-side. 48 mΩ max @ V_GS 2.5 V"),
    Part("Q302", "AO3400A", "SOT-23", "DRV", H_SOT23, vds_max=30.0,
         source=f"{_INV} §1.3 BOM D3 — fan low-side, LEDC PWM"),
    Part("Q303", "AO3400A", "SOT-23", "DRV", H_SOT23, vds_max=30.0,
         source=f"{_INV} §1.3 BOM D3 — buzzer low-side, LEDC PWM"),
    _r("R307", "DRV", "10k",
       f"{_INV} §1.3 BOM D9 — horn gate pull-down. D14: EVERY gate biased OFF "
       f"(PLAN §3.1.2, §6.2.3), so a hung module drives no load"),
    _r("R308", "DRV", "10k", f"{_INV} §1.3 BOM D9 — fan gate pull-down (D14)"),
    _r("R309", "DRV", "10k", f"{_INV} §1.3 BOM D9 — buzzer gate pull-down (D14)"),
    _r("R310", "DRV", "100R",
       f"{_INV} §1.3 BOM D9 — horn gate series, 'driven from the S3 through "
       f"~100 Ω' (PLAN §6.2.3)"),
    _r("R311", "DRV", "100R", f"{_INV} §1.3 BOM D9 — fan gate series"),
    _r("R312", "DRV", "100R", f"{_INV} §1.3 BOM D9 — buzzer gate series"),
    Part("D307", "TBD-FLYBACK", "TBD", "DRV", H_TBD, value="TBD",
         source=f"{_INV} §1.3 BOM D3 note 'fan channel needs a flyback diode'. "
                f"⬜ Q28: no part number. ⛔ the horn needs none — electronic, M7"),
    *[Part(f"D30{n}", "1N4148", "SOD-123 (assumed, Q29)", "DRV", H_SOD123,
           vds_max=100.0,
           source=f"{_INV} §1.3 BOM G1, BRK §3, doc name "
                  f"{('D1L','D1R','D2L','D2R','D3L','D3R')[n-1]}. ⚠️ SILICON, not "
                  f"Schottky — a Schottky's hot reverse leakage reaches the 3.3 V "
                  f"inputs. ⚠️ BRK §2's '|◄' = cathode on the LEVER node")
      for n in range(1, 7)],
    Part("Q304", "AO3407A", "SOT-23", "DRV", H_SOT23, vds_max=30.0,
         source=f"{_INV} §1.3 BOM G2, doc name 'Q1' — the HARDWARE stop-lamp "
                f"switch (D23). P-ch, −30 V, ±20 V gate. ⚠️ a ±12 V-gate part "
                f"would be marginal on 12 V"),
    _r("R313", "DRV", "10k",
       f"{_INV} §1.3 BOM G3, doc name 'R1' — Q1 gate pull-up to +12 V AND the "
       f"lever's wetting current (~1.2 mA)"),
    Part("Q305", "AO3400A", "SOT-23", "DRV", H_SOT23, vds_max=30.0,
         source=f"{_INV} §1.3 BOM D3/G6, doc name 'Q2' — run/off toggle inverter "
                f"(BRK §2.1). Its drain sits on BL"),
    _r("R314", "DRV", "10k",
       f"{_INV} §1.3 BOM G3, doc name 'R4' — toggle pull-up from the THROTTLE's "
       f"ACC+ 5.1 V, ⚠️ NOT from the module, so the toggle works with no module "
       f"fitted (BRK §2.1). ⛔ Q9: no connector carries ACC+, so R314.1 is unlanded"),
    _r("R315", "DRV", "100R", f"{_INV} §1.3 BOM G6, doc name 'R5' — Q2 gate series"),
    _r("R316", "DRV", "100k",
       f"{_INV} §1.3 BOM G6, doc name 'R6' — Q2 gate-to-ground, biases OFF (D14)"),
    _r("R317", "DRV", "10k",
       f"{_INV} §1.3 BOM G3, doc name 'R3L' — IN-05 pull-up to 3.3 V. ⚠️ 10 kΩ, "
       f"NOT the bar switches' 1 kΩ: R1 already wets the contact and 10 kΩ keeps "
       f"the low level ~0.55 V through a 1N4148. ⛔ Q8: needs 3V3 on DRV"),
    _r("R318", "DRV", "10k",
       f"{_INV} §1.3 BOM G3, doc name 'R3R' — IN-06 pull-up to 3.3 V. ⛔ Q8"),
    # ── TVS at every DRV connector — TWO part types, by rail voltage ────────
    # DRV's 23 conductors were unprotected while PLAN §4/§6.2.4 and BDR §7.2
    # both assert "every net leaving the box has a TVS at its connector".
    #
    # ⛔ The part is NOT one type. `PESD5V0S4UD` is V_RWM 5 V; J301-J305 carry
    # 12 V lamp/horn/fan feeds, where a 5 V standoff conducts continuously --
    # a dead short across the channel it is meant to protect, and nothing in
    # the schematic looks different. J306 is the brake levers, which reach the
    # board through the D23 circuit's 1N4148s at logic level, so the OWNED
    # part is correct there.
    *[Part(f"D{n}", "TBD-TVS-24V", "TBD (quad array)", "DRV",
           H_SOT457, vds_max=24.0,
           value="⬜ ≥24 V standoff, clamp < 40 V (the TPS4H160B's limit)",
           source=f"gap-fix — 12 V harness protection at "
                  f"{('J301','J302','J303','J304','J305')[n-308]}. ⬜ NEW BOM "
                  f"LINE: no owned part stands off 12 V. BOM C2's "
                  f"PESD5V0S4UD stays fully used on BRAIN's logic lines, so "
                  f"nothing ordered is superseded. Requirement: 4 channels, "
                  f"≥24 V V_RWM, clamping below the TPS4H160B's 40 V")
      for n in range(308, 313)],
    Part("D313", "PESD5V0S4UD", "SOT-457/TSOP6 (⛔ not SOIC-8)", "DRV",
         H_SOT457, vds_max=5.0, value="V_RWM 5 V, V_CL 8 V @1 A",
         source="gap-fix — J306, the brake levers. These reach the board "
                "through the D23 circuit's 1N4148s at logic level, not at "
                "12 V, so the OWNED BOM C2 part is correct here"),
)

# ════════════════════════════════════════════════════════════════════════════
# PARTS — §1.4  BRAIN (L4): logic.  Ceiling 6 mm.  Respin cost cheap.
# ════════════════════════════════════════════════════════════════════════════
#: §1.4 BOM C1 + §4.5's bit budget.  (pull-up, series, cap, net, expander bit,
#: connector pin, TVS channel).  ⚠️ The expander BIT allocation is
#: generator-side: the documents say only '12 of 16 bits' and §4.5's rule is
#: "wire them now, assign them in firmware later".
_CLASS_A = (
    ("R402", "R413", "C401", "IN01_TURN_L",      "GPA0", ("J402", "6"), ("D401", "ch4")),
    ("R403", "R414", "C402", "IN02_TURN_R",      "GPA1", ("J402", "8"), ("D402", "ch2")),
    ("R404", "R415", "C403", "IN03_HORN",        "GPA2", ("J402", "5"), ("D401", "ch3")),
    ("R405", "R416", "C404", "IN04A_LOW",        "GPA3", ("J402", "3"), ("D401", "ch1")),
    ("R406", "R417", "C405", "IN04B_HIGH",       "GPA4", ("J402", "4"), ("D401", "ch2")),
    ("R407", "R418", "C406", "IN09_FLASH",       "GPA5", ("J402", "7"), ("D402", "ch1")),
    ("R408", "R419", "C407", "IN10_HAZARD",      "GPA6", ("J402", "9"), ("D402", "ch3")),
    ("R409", "R420", "C408", "IN07_BOOST_BTN",   "GPA7", None,          None),
    ("R410", "R421", "C409", "IN08A_RUNNING",    "GPB0", ("J403", "2"), ("D402", "ch4")),
    ("R411", "R422", "C410", "IN08B_HEADLIGHT",  "GPB1", ("J403", "3"), ("D403", "ch1")),
)

_BRAIN_PARTS = (
    Part("U401", "ESP32-S3-WROOM-1-N8", "WROOM-1 SMD module", "BRAIN", 3.1,
         source=f"{_INV} §1.4 BOM A1 / D18 — 8 MB quad flash, no PSRAM, −40…+85 °C. "
                f"⛔ never R8/R16V (65 °C only, and they take GPIO33-37). BOM A1 is "
                f"the DevKitC-1 PROTOTYPE; the bare module is the custom-board part"),
    Part("U402", "MCP23017-E/SP", "DIP-28", "BRAIN", H_DIP,
         source=f"{_INV} §1.4 BOM C3 — expander #1, bar inputs, 12 of 16 bits. "
                f"⬜ Q24: BDR §9 prefers SOIC-28 on a 44 mm board but 'change the "
                f"BOM first' — the BOM owns procurement, so DIP-28 stands here"),
    Part("U403", "MCP23017-E/SP", "DIP-28", "BRAIN", H_DIP, source=f"{_INV} §1.4 ⚠️ Q2 UNRESOLVED: BDR §3 L4 says '2 × MCP23017', but "
                f"BD-5 removed I²C from the lighting path and the 12 bar bits fit "
                f"ONE device. Carried as a DNP footprint for spare bits"),
    Part("U404", "SN65HVD230DR", "SOIC-8", "BRAIN", 1.8,
         source=f"{_INV} §1.4 BOM B1 — the BARE IC is the custom-PCB part; the 3 "
                f"characterised breakouts in hand are the prototype part"),
    _r("R401", "BRAIN", "120R",
       f"{_INV} §1.4 BOM B2 — CAN termination at the module end. 68 Ω joined with "
       f"the panel's own 132.4 Ω = the CAN pre-flight gate"),
    Part("U405", "TBD-3V3-REG", "TBD", "BRAIN", H_TBD, value="5 V → 3.3 V",
         source=f"{_INV} §1.4 ⛔ Q3 GAP, ⭐ CORRECTION 3: a real part with NO BOM "
                f"LINE. PLAN §3.2.1 leans on the DevKit's onboard LDO; BDR §5 sends "
                f"PWR-UP's +5 V 'to BRAIN's regulator'; a bare WROOM-1 has none. "
                f"⬜ no MPN, no package, no current figure"),
    *[_r(pu, "BRAIN", "1k",
         f"{_INV} §1.4 BOM C1 — class-A PULL-UP to 3V3 for {net}. ⚠️ 1 kΩ, not "
         f"4.7 kΩ: wetting current 3.3 mA (PLAN §4), which is why it sits on the "
         f"CONTACT side of the series resistor")
      for pu, _s, _cap, net, _bit, _cn, _tv in _CLASS_A],
    *[_r(se, "BRAIN", "1k",
         f"{_INV} §1.4 BOM C1 — class-A SERIES into the pin for {net} (PLAN §4)")
      for _pu, se, _cap, net, _bit, _cn, _tv in _CLASS_A],
    *[_c(cp, "BRAIN", "100nF",
         f"{_INV} §1.4 BOM C1 — class-A 100 nF to GND at the pin for {net}")
      for _pu, _s, cp, net, _bit, _cn, _tv in _CLASS_A],
    # ⚠️ Q23: BDR §3 L4 says 11 class-A networks, BOM C1 bought 10 sets, and only
    # 10 dry contacts are identifiable. The 11th set is carried, unassigned.
    _r("R412", "BRAIN", "1k",
       f"{_INV} §1.4 / §5 Q23 — the 11th class-A pull-up. ⬜ WHICH INPUT IT SERVES "
       f"IS NOT STATED (IN-11 is class B with its own divider, IN-05/06 take G3's "
       f"10 kΩ, IN-17 is 'a spare class-A input'). On no net"),
    _r("R423", "BRAIN", "1k", f"{_INV} §1.4 / §5 Q23 — 11th class-A series. On no net"),
    _c("C411", "BRAIN", "100nF", f"{_INV} §1.4 / §5 Q23 — 11th class-A cap. On no net"),
    *[Part(f"D40{n}", "PESD5V0S4UD", "SOT-457/TSOP6 (⛔ not SOIC-8)", "BRAIN",
           H_SOT457, vds_max=5.0, value="V_RWM 5 V, V_CL 8 V @1 A",
           source=f"{_INV} §1.4 BOM C2 — quad UNIDIRECTIONAL, common anode. "
                  f"4 packages = 16 lines for the 15 needed")
      for n in range(1, 5)],
    Part("Q401", "AO3400A", "SOT-23", "BRAIN", H_SOT23, vds_max=30.0,
         source=f"{_INV} §1.4 BOM D3 — boost open-drain output. ⚠️ METER THE BOOST "
                f"WIRE FIRST: the same 30-pin harness carries pink 60VC at 72-84 V. "
                f">25 V means a PC817 opto instead of this 30 V FET"),
    _r("R424", "BRAIN", "100R", f"{_INV} §1.4 BOM D9 — boost gate series (PLAN §6.2.3)"),
    _r("R425", "BRAIN", "10k",
       f"{_INV} §1.4 BOM D9 — boost HARD external pull-down (BDR §3 L4, PLAN §3.1.1). "
       f"D14: the gate must bias OFF through a boot that is ~200 ms of high-Z"),
    _r("R426", "DRV", "1k",
       f"{_INV} §1.4 BOM B3 — LEFT telltale series to display pin 1, fed FROM THE "
       f"LAMP FEED, not a driver channel (PLAN §6.2.1)"),
    _r("R427", "DRV", "1k", f"{_INV} §1.4 BOM B3 — RIGHT telltale series, display pin 4"),
    _r("R428", "DRV", "1k",
       f"{_INV} §1.4 BOM B3 — headlight telltale series, display pin 5. ⬜ Q22: "
       f"'channel 1 or 2' is undecided; wired to HL_HIGH here because PLAN §7 says "
       f"the high-beam telltale follows the lamp feed so a flash lights it with no "
       f"firmware — ⚠️ which means LOW beam does NOT light it"),
    _r("R429", "DRV", "1k",
       f"{_INV} §1.4 BOM B3 — series in display PIN 9. ⚠️ back-feed protection: the "
       f"FarDriver drives 0-15 V into an unpowered input during a display reset "
       f"(PLAN §3.3). ⛔ Q19: the FarDriver's brown one-line lead reaches no module "
       f"connector, so R429.1 is unlanded"),
    _r("R430", "BRAIN", "10k",
       f"{_INV} §1.4 BRK §2.1 — IN-11 divider TOP (10 k/15 k, 3.0 V at 5 V in). "
       f"SENSE ONLY: it never drives the cut"),
    _r("R431", "BRAIN", "15k",
       f"{_INV} §1.4 BRK §2.1 — IN-11 divider BOTTOM. ⛔ Q13: NO 15 kΩ LINE EXISTS "
       f"IN THE BOM (G3 has 10 kΩ ×4 only)"),
    _r("R432", "BRAIN", "TBD",
       f"{_INV} §1.4 PLAN §6.2.2a — FAULT1 pull-up to 3V3 ('STx/FAULT are "
       f"open-drain and need their own 3.3 V pullups'). ⬜ value unstated"),
    _r("R433", "BRAIN", "TBD", f"{_INV} §1.4 PLAN §6.2.2a — FAULT2 pull-up. ⬜ value unstated"),
    _r("R434", "BRAIN", "TBD",
       f"{_INV} §1.4 D16 mitigation list: 'strong pull-ups' on I²C SDA. ⬜ value unstated"),
    _r("R435", "BRAIN", "TBD", f"{_INV} §1.4 D16 — I²C SCL pull-up. ⬜ value unstated"),
    _r("R436", "BRAIN", "1k",
       f"{_INV} §2.6 UART1_TX 'class E: 1 k series, pin tri-stated whenever not "
       f"sending'. ⚠️ §1.4's parts table assigns NO REFDES for this resistor; §0 "
       f"states the documents assign no refdes at all and the generator owns the "
       f"scheme, so it is numbered here"),
)


# ── Gaps closed 2026-09-15 ───────────────────────────────────────────────────
# Found by running rules.check_all() against the real netlist; each uses a part
# type already on the BOM so nothing ordered is superseded.
_GAP_PARTS = (
    # D14 requires every gate to bias OFF. For a P-channel HIGH-SIDE switch
    # that means Vgs = 0, i.e. the gate tied to its own SOURCE -- not to
    # ground. Without these two resistors nothing holds the 84 V switches off
    # through power-up, which is the one place D14 matters most.
    Part("R110", "TBD-R-100k", "TBD (0805)", "HVIN", 1.0, value="100k",
         source="gap-fix — Q101 (D13) gate-to-SOURCE pull-up. Same topology as "
                "PLAN 6.2.2's R1 on the discrete high-side, at 84 V. BOM D9 "
                "('every gate biased OFF') covers the part"),
    Part("R111", "TBD-R-100k", "TBD (0805)", "HVIN", 1.0, value="100k",
         source="gap-fix — Q104 (Q3, the FarDriver KEY switch) gate-to-SOURCE "
                "pull-up. BOM D9"),
    # 84 V wires leaving the box. SMCJ90A is BOM E12 -- the part already chosen
    # for this exact node, so this is a QUANTITY change, not a new line.
    Part("D104", "SMCJ90A", "DO-214AB", "HVIN", 2.6, vds_max=90.0,
         source="gap-fix — KEY_SW_OUT leaves the box unprotected; HVIN's only "
                "TVS was D101 on B+. Same part as E12"),
    Part("D105", "SMCJ90A", "DO-214AB", "HVIN", 2.6, vds_max=90.0,
         source="gap-fix — FD_KEY (the FarDriver KEY wire) leaves the box "
                "unprotected. Same part as E12"),
    # CAN is a 3.3 V differential pair, so the OWNED PESD5V0S4UD is correct
    # here. BOM C2 bought 20 arrays for 15 lines -- this uses stock.
    # The display connector J405 is parked with D19 but its FOOTPRINT is
    # fitted (BDR §3 L4). Its protection footprint is fitted on the same terms:
    # placed, routed, NOT POPULATED -- so un-parking the display is a
    # populate-and-go, not a respin. The three telltales are 12 V lamp feeds
    # and DISP_ONELINE is the FarDriver's 0-15 V output, so 5 V is wrong here
    # for the same reason it is wrong on DRV.
    Part("D406", "TBD-TVS-24V", "TBD (quad array)", "DRV", 1.1, vds_max=24.0,
         dnp=True, value="⬜ ≥24 V standoff — DNP until D19 un-parks",
         source="gap-fix — TT_L/TT_R/TT_HL/DISP_ONELINE leave the box on J405 "
                "unprotected. ⏸️ Fitted but not populated, matching the park"),
    Part("D405", "PESD5V0S4UD", "SOT-457", "BRAIN", 1.1, vds_max=5.0,
         source="gap-fix — CANH/CANL leave the box on J405. 5 V standoff is "
                "correct on a 3.3 V differential pair. Uses BOM C2 stock"),
)

_PARTS = (_HVIN_PARTS + _CONV_PARTS + _DRV_PARTS + _BRAIN_PARTS
          + _GAP_PARTS)

# ════════════════════════════════════════════════════════════════════════════
# INTERFACE PIN MAPS — the three inter-board spines (BDR §5, BD-3, BD-4)
# Contact indices are generator-side; no document numbers these pins.
# ════════════════════════════════════════════════════════════════════════════

#: ⬜ Q1: HV-LINK's PIN COUNT IS NEVER STATED. This is the minimum implied
#: content — 2 × protected 84 V up, 1 return, 1 × +5 V down, plus the three
#: nets Q10 shows must also cross it — at BD-4's 5.08 mm effective spacing.
_HVLINK_NETS = ("HV_CONV1", "HV_CONV2_PRE", "GND", "V5", "KEY_SENSE", "RUN", "START")

#: BDR §5, verbatim: 2 × +12 V, 3 × GND, 1 × +5 V, KEY_SENSE, RUN, START = 9.
#: ⬜ The documents do not say how "L2 → L3/L4" branches, so all three headers
#: carry the same 9-pin bus here.
_PWRUP_NETS = ("V12", "V12", "GND", "GND", "GND", "V5", "KEY_SENSE", "RUN", "START")

#: STACK, 2 × 25 with ALTERNATING GROUNDS = 25 signal contacts, odd pins, each
#: ground-flanked by construction (which CS1/CS2 require).
#:
#: ⭐ RESIZED 2026-09-18 from 2 × 20. BDR §5's 2 × 20 gave 20 signal contacts
#: against a real demand of 23, counted from this netlist rather than from the
#: documented list -- the three telltale feeds carried pins on both boards and
#: had no contact at all.
#:
#: Owner decision 2026-09-18: the display block (J405, its TVS, and the R426-
#: R429 series resistors) moves to DRV, putting the connector on the board
#: whose 12 V the telltales already are. ⚠️ Moving the CONNECTOR ALONE makes
#: it worse (30 crossings -> 36): the telltale nets keep their BRAIN pins
#: unless the resistors go too. With the whole block moved it is 29, and the
#: cost of the move is that CANH/CANL now cross instead, since the
#: SN65HVD230 stays on BRAIN.
#:
#: `RUN`, `START` and `KEY_SENSE` are NOT here: they are routed on PWR-UP and
#: HV-LINK, whose documented pin lists name them, and they must stay copper
#: end to end (BD-7).
_STACK_SIGNALS = (
    "LGT_LOW", "LGT_HIGH", "LGT_DRL", "LGT_TAIL", "LGT_TURN_L", "LGT_TURN_R",
    "DIAG_EN", "SEL1", "SEL2", "CS1", "CS2", "FAULT1", "FAULT2",
    "HORN_CMD", "FAN_CMD", "BUZZ_CMD", "V12_SENSE", "BL",
    "IN05_BRAKE_L", "IN06_BRAKE_R",
    # added with the 2 x 25 resize:
    "CANH", "CANL",   # the display move sends these across; transceiver stays on BRAIN
    "V3P3",           # R317/R318 are 3.3 V pull-ups sitting on the 12 V board (Q8)
)


def _hvlink(net: str) -> tuple[tuple[str, str], ...]:
    i = _HVLINK_NETS.index(net) + 1
    return (("J104", str(i)), ("J201", str(i)))


def _pwrup(net: str) -> tuple[tuple[str, str], ...]:
    return tuple((c, str(i + 1))
                 for i, n in enumerate(_PWRUP_NETS) if n == net
                 for c in ("J202", "J307", "J407"))


def _stack(net: str) -> tuple[tuple[str, str], ...]:
    i = _STACK_SIGNALS.index(net)
    return (("J308", str(2 * i + 1)), ("J406", str(2 * i + 1)))


_S = f"{_INV} §2"

# ════════════════════════════════════════════════════════════════════════════
# NETS — §2.1  the 84 V domain.  HVIN and CONV only (BD-2).
# ⚠️ Ordering PLAN §3.2.5 forbids scrambling: HV_SW → choke → bulk cap →
# converter on each branch, and the 1N4007 + 1 A T-lag sit between HV_SW and C2
# ONLY. Putting the hold-up cap on the common node collapses ride-out from
# ~237 ms to ~20 ms.
# ════════════════════════════════════════════════════════════════════════════
_NETS_84V = (
    Net("HV_BPLUS", (("R110", "2"), ("J101", "1"), ("D101", "K"), ("Q101", "S"), ("J102", "1")),
        domain="84V", leaves_box=True,
        source=f"{_S}.1 — fused UPSTREAM IN THE HARNESS (KLKD002 in a FEB-11-11), "
               f"never on the board (BDR §6)"),
    Net("KEY_SW_OUT", (("R111", "2"), ("D104", "1"), ("J102", "2"), ("R101", "1"), ("Q104", "S")),
        domain="84V", leaves_box=True,
        source=f"{_S}.1 — back from the mechanical key switch, which carries "
               f"~0.25 mA of gate drive only (PLAN §3.2.5)"),
    Net("HV_SW", (("Q101", "D"), ("L101", "1"), ("L102", "1")),
        domain="84V", source=f"{_S}.1 — D13's output, ahead of both chokes"),
    Net("D13_GATE", (("R110", "1"), ("Q101", "G"), ("R101", "2"), ("C105", "1"), ("D102", "A")),
        domain="84V",
        source=f"{_S}.1 / §1.1 — ⬜ Q11: the ramp RC's and the zener's REFERENCE "
               f"NODE (source vs GND) is nowhere stated, so C105.2 and D102.K are "
               f"deliberately unassigned rather than guessed. Ramp target ~50 ms"),
    Net("KEY_GATE", (("R111", "1"), ("Q104", "G"), ("D103", "A"), ("Q102", "D"), ("Q103", "D")),
        domain="84V",
        source=f"{_S}.1 / §1.1 BDR §3 L1 'pulls Q3's gate down from the latch'. "
               f"⬜ the latch passives R103-R106 have no stated topology and "
               f"D103.K's reference is not stated either; both left unassigned"),
    Net("LATCH_OUT", (("U101", "LATCH_OUT"), ("Q102", "G"), ("Q103", "G")),
        domain="5V",
        source=f"{_S}.1 / §1.1 — the 74HC14 latch output. ⚠️ Q14 disputes START's "
               f"polarity, which is what decides U101's gate arrangement"),
    Net("HV_CONV1",
        (("L101", "2"),) + _hvlink("HV_CONV1") +
        (("C201", "+"), ("U201", "+Vin"), ("C203", "1")),
        domain="84V", interface="HV-LINK",
        source=f"{_S}.1 — choke → bulk cap → converter, in that order"),
    Net("HV_CONV2_PRE",
        (("L102", "2"),) + _hvlink("HV_CONV2_PRE") + (("D201", "A"),),
        domain="84V", interface="HV-LINK",
        source=f"{_S}.1 — ⬜ Q1: the documents do not say whether D201 precedes or "
               f"follows L102; both readings keep 'choke before the bulk cap' true"),
    Net("HV_CONV2_FUSE_IN", (("D201", "K"), ("FH201", "1"), ("F201", "1")),
        domain="84V",
        source=f"{_S}.1 — ⚠️ NAME NOT IN THE INVENTORY: §2.1 writes HV_CONV2_HOLD "
               f"as one row across the fuse, but a two-terminal fuse needs two "
               f"nodes. The post-fuse node keeps the inventory's name"),
    Net("HV_CONV2_HOLD",
        (("FH201", "2"), ("F201", "2"), ("C202", "+"), ("U202", "+Vin"),
         ("C205", "1")),
        domain="84V",
        source=f"{_S}.1 — ⚠️ THE HOLD-UP NODE: C2 lives here and C1 does not "
               f"(PLAN §3.2.2). 237 ms of ride-out depends on it"),
    Net("FD_KEY", (("D105", "1"), ("Q104", "D"), ("J103", "1"), ("R107", "1")),
        domain="84V", leaves_box=True,
        source=f"{_S}.1 — Q3 → the FarDriver KEY wire; 1 conductor, the return is "
               f"the shared B−. ⚠️ Q5 DISPUTED: PLAN §3 puts the IN-12 divider tap "
               f"DOWNSTREAM of the latch (here), PLAN §3.2.2/§3.2.5 UPSTREAM of the "
               f"diode so key-off collapses the sense line while C2 holds the logic up"),
    Net("KEY_SENSE_MID", (("R107", "2"), ("R108", "1")),
        domain="84V",
        source=f"{_S}.1 / §1.1 — the join in the 330 kΩ ¼ W series pair; it exists "
               f"only because one resistor cannot take the voltage (PLAN §4 class B)"),
    Net("BASEPLATE",
        (("C203", "2"), ("C204", "2"), ("C205", "2"), ("C206", "2"),
         ("U201", "BASEPLATE")),
        domain="GND",
        source=f"{_S}.1 — chassis: the Y2 caps bridge ±Vin to it, BD-9's alloy plate "
               f"and the enclosure share it. ⚠️ 'A short-failure would put the 84 V "
               f"rail on the enclosure' (BOM E9) — hence IEC 60384-14 safety caps. "
               f"Domain is GND: a chassis return, 0 V by definition"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — §2.2/§2.3  the rails.
# ⛔ GND is a SINGLE STAR NET referenced to the CONTROLLER's B− stud — never the
# battery's B− and never a frame point (PLAN §3.2.4, §6.0.2, BDR §6).
# ════════════════════════════════════════════════════════════════════════════
_GND_PINS = (
    # HVIN
    ("J101", "2"), ("D101", "A"), ("U101", "GND"), ("Q102", "S"), ("Q103", "S"),
    ("R109", "2"), ("C106", "2"),
    # CONV
    ("C201", "-"), ("C202", "-"), ("U201", "-Vin"), ("U201", "-Vout"),
    ("U202", "-Vin"), ("U202", "-Vout"), ("C204", "1"), ("C206", "1"),
    # DRV
    ("U301", "GND"), ("U302", "GND"), ("Q301", "S"), ("Q302", "S"), ("Q303", "S"),
    ("R307", "2"), ("R308", "2"), ("R309", "2"), ("R316", "2"),
    ("D311", "A"), ("D312", "A"), ("D313", "A"), ("J306", "2"), ("J306", "4"),
    # BRAIN
    ("U401", "GND"), ("U402", "VSS"), ("U403", "VSS"), ("U404", "GND"),
    ("U405", "GND"), ("Q401", "S"), ("R425", "2"), ("R431", "2"),
    ("D401", "A"), ("D402", "A"), ("D403", "A"), ("D404", "A"),
    ("J402", "1"), ("J403", "1"), ("J404", "4"), ("J405", "3"), ("J401", "4"),
) + tuple((cp, "2") for _pu, _s, cp, _n, _b, _c, _t in _CLASS_A) \
  + _hvlink("GND") + _pwrup("GND") \
  + tuple(("J308", str(n)) for n in range(2, 51, 2)) \
  + tuple(("J406", str(n)) for n in range(2, 51, 2))

_NETS_RAILS = (
    Net("GND", _GND_PINS, domain="GND", interface="HV-LINK", leaves_box=True,
        source=f"{_S}.1/§2.2 — the star net, on all four boards and across ALL "
               f"THREE interfaces (HV-LINK · PWR-UP ×3 · STACK alternating "
               f"grounds). `interface` can name only one, so it names the lowest "
               f"in stack order. Domain is GND -- model.Domain now has "
               f"ground member and '84V' would trip BD-2 on a net that belongs on "
               f"every board. Display pin 3 (J405.3) is here and ⛔ IS NEVER SWITCHED"),
    Net("V5",
        (("U202", "+Vout"),) + _hvlink("V5") + (("U101", "VCC"),) +
        _pwrup("V5") + (("U405", "IN"),),
        domain="GND", interface="HV-LINK",
        source=f"{_S}.2 — BDR §5: '+5 V to BRAIN's regulator' on PWR-UP, and '5 V "
               f"back DOWN for the start latch's 74HC14' on HV-LINK. Two crossings; "
               f"the lower is named. ⚠️ U202's output is isolated (3 kV) but is "
               f"referenced to the star here — BD-13 is the reserve that drops it"),
    Net("V3P3",
        (("U405", "OUT"), ("U401", "3V3"), ("U402", "VDD"), ("U403", "VDD"),
         ("U404", "VCC"), ("R432", "2"), ("R433", "2"), ("R434", "2"),
         ("R435", "2"), ("R317", "2"), ("R318", "2")) +
        tuple((pu, "2") for pu, _s, _c, _n, _b, _cn, _t in _CLASS_A),
        domain="3V3", interface="STACK",
        source=f"{_S}.2 — ⛔ Q8: R317/R318 (R3L/R3R) are on DRV and pull IN-05/06 up "
               f"TO 3.3 V, but PWR-UP carries +12 V/GND/+5 V only and BD-2 puts 3V3 "
               f"at the lid. So 3V3 must cross STACK downward — UNDOCUMENTED, and "
               f"STACK has no contact left for it. The alternative is moving those "
               f"two resistors to BRAIN"),
    Net("V12",
        (("U201", "+Vout"),) + _pwrup("V12") +
        (("U301", "VBAT"), ("U302", "VBAT"), ("Q304", "S"), ("R313", "2"),
         ("D307", "K"), ("J304", "1"), ("J305", "1"), ("J305", "3"),
         ("D311", "ch1"), ("D312", "ch1")) +
        tuple((f"R30{n}", "2") for n in range(1, 7)),
        domain="12V", interface="PWR-UP", leaves_box=True,
        source=f"{_S}.3 — PWR-UP carries it on TWO pins for the measured 2.62 A "
               f"(BDR §5). ⛔ J304.1 is BLUE and it is the POSITIVE — red is not"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — §2.3  the six high-side lighting channels and the low-side outputs.
# Channel allocation is PLAN §3.1.3's, carried verbatim; BD-5 changed only which
# pin DRIVES it (native GPIO, not an expander).
#   U301: IN1 spare/unconnected · IN2 HL_LOW · IN3 HL_HIGH · IN4 HL_DRL
#   U302: IN1 TAIL_RUN · IN2 TURN_L · IN3 TURN_R · IN4 spare
# ════════════════════════════════════════════════════════════════════════════
_NETS_12V = (
    Net("HL_LOW", (("U301", "OUT2"), ("R301", "1"), ("J301", "3"), ("D308", "ch1")),
        domain="12V", leaves_box=True,
        source=f"{_S}.3 — J301.3 is BLUE on the headlight. 12 V / 8.5 W = 0.71 A"),
    Net("HL_HIGH",
        (("U301", "OUT3"), ("R302", "1"), ("J301", "2"), ("D308", "ch2"),
         ("R428", "1")),
        domain="12V", leaves_box=True,
        source=f"{_S}.3/§2.6 — J301.2 is GREEN. ⚠️ firmware must break-before-make "
               f"against LOW (never both: 1.96 A). ⬜ Q18/Q22: R428 is on BRAIN, so "
               f"this 12 V feed has to cross STACK to reach the display connector — "
               f"a crossing STACK's documented pin list does not carry"),
    Net("HL_DRL", (("U301", "OUT4"), ("R303", "1"), ("J301", "4"), ("D308", "ch3")),
        domain="12V", leaves_box=True,
        source=f"{_S}.3 — J301.4 is YELLOW. 12 V / 6.5 W = 0.54 A"),
    Net("TAIL_RUN", (("U302", "OUT1"), ("R304", "1"), ("J302", "2"), ("D309", "ch1")),
        domain="12V", leaves_box=True,
        source=f"{_S}.3 — J302.2 YELLOW, 0.05 A, a SEPARATE FEED and not PWM"),
    Net("TURN_L",
        (("U302", "OUT2"), ("R305", "1"), ("J302", "4"), ("J303", "1"),
         ("R426", "1"), ("D309", "ch2"), ("D310", "ch1")),
        domain="12V", leaves_box=True,
        source=f"{_S}.3/§2.6 — rear LEFT is J302.4 BLUE (M6), front pair on J303. "
               f"⬜ Q18: R426 is on BRAIN, so this crosses STACK with no contact"),
    Net("TURN_R",
        (("U302", "OUT3"), ("R306", "1"), ("J302", "5"), ("J303", "3"),
         ("R427", "1"), ("D309", "ch3"), ("D310", "ch2")),
        domain="12V", leaves_box=True,
        source=f"{_S}.3/§2.6 — rear RIGHT is J302.5 GREEN (M6). ⬜ Q18 as TURN_L"),
    Net("TAIL_STOP", (("Q304", "D"), ("J302", "3"), ("D309", "ch4")),
        domain="12V", leaves_box=True,
        source=f"{_S}.3 — J302.3 RED, 0.12 A. ⛔ NOT A MODULE CHANNEL: Q1 switches "
               f"it in hardware (D23). F1, the 1 A ATM fuse in this feed, is a "
               f"HARNESS part (Q32) and is deliberately absent from this netlist"),
    Net("LAMP_COMMON",
        (("J301", "1"), ("J302", "1"), ("J303", "2"), ("J303", "4"),
         ("D308", "A"), ("D309", "A"), ("D310", "A")),
        domain="GND", leaves_box=True,
        source=f"{_S}.3 — every lamp common lands on the module's 12 V return, "
               f"which stars at the controller B− stud, so this IS GND copper and "
               f"needs a net-tie to it at the star. Kept as its own net because the "
               f"inventory names it and the three lamp connectors carry it; it is "
               f"also the reference the three lamp-connector TVS arrays clamp to. "
               f"⬜ M6: confirm the front pair's return may share the tail common"),
    Net("HORN_N", (("J304", "2"), ("Q301", "D"), ("D311", "ch2")),
        domain="12V", leaves_box=True,
        source=f"{_S}.3 — J304.2 BLACK = '−'. ⛔ red is NOT the positive on the horn "
               f"and its role is unconfirmed. Electronic horn, 12.0 V / 0.10 A"),
    Net("FAN_RTN",
        (("J305", "2"), ("Q302", "D"), ("D307", "A"), ("D312", "ch2")),
        domain="12V", leaves_box=True,
        source=f"{_S}.3 — fan '−', LEDC PWM. D307 is the flyback across the motor "
               f"(cathode to V12); ⬜ Q28 gives it no part number"),
    Net("BUZZ_RTN", (("J305", "4"), ("Q303", "D"), ("D312", "ch3")),
        domain="12V", leaves_box=True,
        source=f"{_S}.3 — buzzer '−', LEDC PWM. ⬜ Q27: whether the buzzer is inside "
               f"the box or on the harness is unstated; it shares J305 with the fan"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — §2.4  the D23 brake circuit, on DRV (BD-6).
# ⚠️ BRK §2's '|◄' means CATHODE ON THE LEVER-NODE SIDE: each diode's anode
# faces the line it pulls, its cathode faces the lever.
# ⭐ RUN fails safe — a broken or unplugged bar wire leaves the node pulled up,
# which reads as OFF and stops drive. Nothing here may defeat that.
# ════════════════════════════════════════════════════════════════════════════
_NETS_BRAKE = (
    Net("LEVER_L",
        (("J306", "1"), ("D301", "K"), ("D303", "K"), ("D305", "K"),
         ("D313", "ch1")),
        leaves_box=True,
        source=f"{_S}.4 — ⬜ M3 gates J306 entirely: lever type/NO-NC/wire count "
               f"decide whether the circuit works as drawn. M2 identifies the wires "
               f"in loom '1T3 10'"),
    Net("LEVER_R",
        (("J306", "3"), ("D302", "K"), ("D304", "K"), ("D306", "K"),
         ("D313", "ch2")),
        leaves_box=True,
        source=f"{_S}.4 — ⬜ M3, and ⬜ M3 also decides whether the two levers share "
               f"one return (J306.2/J306.4) or need their own pairs"),
    Net("BL",
        (("D301", "A"), ("D302", "A"), ("Q305", "D")) + _stack("BL") +
        (("J404", "6"), ("D404", "ch3")),
        interface="STACK", leaves_box=True,
        source=f"{_S}.4 — FarDriver YELLOW/GREEN. ⛔ not grey BH, which stays capped. "
               f"⚠️ the 100 nF brake C1 belongs AT THE CONTROLLER (BRK §8, Q32) and "
               f"is deliberately not a board part"),
    Net("Q1_GATE", (("D303", "A"), ("D304", "A"), ("R313", "1"), ("Q304", "G")),
        source=f"{_S}.4 — either lever pulls Q1's gate down and the stop lamp lights "
               f"WITHOUT FIRMWARE. R313 is both the pull-up and the contact's "
               f"wetting current"),
    Net("IN05_BRAKE_L",
        (("D305", "A"), ("R317", "1")) + _stack("IN05_BRAKE_L") +
        (("U401", "IO15"),),
        interface="STACK", gpio="GPIO15",
        source=f"{_S}.4 — R8: stays NATIVE because the boost safety-release wants it "
               f"in <10 ms. The lever wire's TVS is D313 at J306, where it leaves"),
    Net("IN06_BRAKE_R",
        (("D306", "A"), ("R318", "1")) + _stack("IN06_BRAKE_R") +
        (("U401", "IO16"),),
        interface="STACK", gpio="GPIO16", source=f"{_S}.4 — R8, as IN05"),
    Net("RUN",
        (("J403", "4"), ("R314", "2"), ("R315", "1"), ("R430", "1"),
         ("U101", "RESET_IN"), ("D403", "ch2")) + _pwrup("RUN") + _hvlink("RUN"),
        interface="HV-LINK", leaves_box=True,
        source=f"{_S}.4 — BD-7 HARDWARE NET: a bare trace from the right pod's RED "
               f"wire to the spine, tapped for sensing. ⛔ Q10: BDR §5 lists it on "
               f"PWR-UP only; it must also cross STACK (no contact allocated) and "
               f"HV-LINK. ⭐ fails safe pulled up = OFF"),
    Net("START",
        (("J403", "5"), ("R102", "1"), ("D403", "ch3")) +
        _pwrup("START") + _hvlink("START"),
        interface="HV-LINK", leaves_box=True,
        source=f"{_S}.4 — BD-7 hardware net, right pod GREEN. ⛔ Q14: POLARITY IS "
               f"INVERTED BETWEEN DOCUMENTS — PLAN §3.2.5a has the button DELIVER "
               f"5 V, while the pod as rewired (BENCH 2026-09-12) makes blue the "
               f"ground common so the button PULLS TO GROUND. One of the two must "
               f"change. ⛔ Q10 as RUN"),
    Net("START_RC", (("R102", "2"), ("C106", "1"), ("U101", "SET_IN")),
        source=f"{_S}.4 / §1.1 — the 1 MΩ/2.2 µF film RC that makes the ~2 s start "
               f"gesture, into the Schmitt. ⚠️ its sense is undecided until Q14 closes"),
    Net("Q2_GATE", (("R315", "2"), ("Q305", "G"), ("R316", "1")),
        source=f"{_S}.4 — the run/off toggle inverter's gate (BRK §2.1)"),
    Net("IN11_SENSE", (("R430", "2"), ("R431", "1"), ("U402", "GPB2")),
        source=f"{_S}.4 — 10 k/15 k, 3.0 V at 5 V in. ⚠️ SENSE ONLY: it never drives "
               f"the cut (BRK §2.1). Expander bit is generator-side (§4.5)"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — §2.5  STACK control and diagnostics (L3 ↔ L4).
# BD-5: lighting is FULL NATIVE — I²C left the lighting path entirely.
# ════════════════════════════════════════════════════════════════════════════
_LIGHTING = (
    ("LGT_LOW",    "GPIO36", "U301", "IN2", "headlight LOW"),
    ("LGT_HIGH",   "GPIO37", "U301", "IN3", "headlight HIGH"),
    ("LGT_DRL",    "GPIO38", "U301", "IN4", "headlight DRL"),
    ("LGT_TAIL",   "GPIO39", "U302", "IN1", "tail running"),
    ("LGT_TURN_L", "GPIO40", "U302", "IN2", "turn LEFT"),
    ("LGT_TURN_R", "GPIO41", "U302", "IN3", "turn RIGHT"),
)

_NETS_STACK = tuple(
    Net(name, (("U401", gpio.replace("GPIO", "IO")),) + _stack(name) + ((dev, pin),),
        interface="STACK", gpio=gpio,
        source=f"{_S}.5 / §4.4 — {what} → {dev}.{pin}. R12: the TPS4H160B's internal "
               f"input pulldown holds the channel OFF through the ~200 ms the GPIO "
               f"spends high-Z at boot (D14)")
    for name, gpio, dev, pin, what in _LIGHTING
) + (
    Net("DIAG_EN",
        (("U301", "DIAG_EN"), ("U302", "DIAG_EN")) + _stack("DIAG_EN") +
        (("U401", "IO7"),),
        interface="STACK", gpio="GPIO7",
        source=f"{_S}.5 — BUSSED to both devices (PLAN §3.1.1 counts it once). An "
               f"ADC1 pin spent on a digital signal deliberately, so slack (D) can "
               f"free GPIO4/5/7/8/9 as one block if the budget needs it"),
    Net("SEL1", (("U301", "SEL1"), ("U302", "SEL1")) + _stack("SEL1") +
        (("U401", "IO8"),), interface="STACK", gpio="GPIO8",
        source=f"{_S}.5 — bussed to both devices"),
    Net("SEL2", (("U301", "SEL2"), ("U302", "SEL2")) + _stack("SEL2") +
        (("U401", "IO9"),), interface="STACK", gpio="GPIO9",
        source=f"{_S}.5 — bussed to both devices"),
    Net("CS1", (("U301", "CS"),) + _stack("CS1") + (("U401", "IO4"),),
        interface="STACK", gpio="GPIO4",
        source=f"{_S}.5 — ⚠️ ADC1 ONLY (ADC2 dies with WiFi) and GROUND-FLANKED "
               f"across STACK (BDR §5), which the alternating-ground map gives it"),
    Net("CS2", (("U302", "CS"),) + _stack("CS2") + (("U401", "IO5"),),
        interface="STACK", gpio="GPIO5", source=f"{_S}.5 — ⚠️ ADC1 only, ground-flanked"),
    Net("FAULT1",
        (("U301", "FAULT"), ("R432", "1")) + _stack("FAULT1") + (("U401", "IO11"),),
        interface="STACK", gpio="GPIO11",
        source=f"{_S}.5 — open-drain, needs its own 3V3 pull-up (PLAN §6.2.2a). "
               f"Digital only: GPIO11 is ADC2, which is unusable (R1)"),
    Net("FAULT2",
        (("U302", "FAULT"), ("R433", "1")) + _stack("FAULT2") + (("U401", "IO12"),),
        interface="STACK", gpio="GPIO12", source=f"{_S}.5 — as FAULT1"),
    Net("HORN_CMD", (("U401", "IO42"),) + _stack("HORN_CMD") + (("R310", "1"),),
        interface="STACK", gpio="GPIO42",
        source=f"{_S}.5 — the MCU-side segment of §2.5's HORN_GATE row; the name "
               f"HORN_GATE stays on the FET gate node, where the bias-OFF part is"),
    Net("FAN_CMD", (("U401", "IO44"),) + _stack("FAN_CMD") + (("R311", "1"),),
        interface="STACK", gpio="GPIO44",
        source=f"{_S}.5 — LEDC PWM. ⚠️ GPIO44 is U0RXD: driving it as an output is "
               f"legal but must be noted on the schematic"),
    Net("BUZZ_CMD", (("U401", "IO47"),) + _stack("BUZZ_CMD") + (("R312", "1"),),
        interface="STACK", gpio="GPIO47", source=f"{_S}.5 — LEDC PWM"),
    Net("HORN_GATE", (("R310", "2"), ("Q301", "G"), ("R307", "1")),
        source=f"{_S}.5 — D14: the 10 kΩ pull-down is what biases the gate OFF"),
    Net("FAN_GATE", (("R311", "2"), ("Q302", "G"), ("R308", "1")),
        source=f"{_S}.5 — D14 bias-OFF pull-down"),
    Net("BUZZ_GATE", (("R312", "2"), ("Q303", "G"), ("R309", "1")),
        source=f"{_S}.5 — D14 bias-OFF pull-down"),
    Net("V12_SENSE", _stack("V12_SENSE") + (("U401", "IO2"),),
        interface="STACK", gpio="GPIO2",
        source=f"{_S}.5 — IN-15, ADC1_CH1. ⬜ Q15: THE DIVIDER HAS NO PARTS AND NO "
               f"BOARD. PLAN §3 calls it class D (divider + 100 nF, 0-15 V); BDR §5 "
               f"puts the net on STACK. Nothing is invented here, so the net runs "
               f"from the spine to the pin and the divider is missing"),
)

# ════════════════════════════════════════════════════════════════════════════
# NETS — §2.6  BRAIN-local: buses, serial, CAN, boost, USB, telltales.
# ════════════════════════════════════════════════════════════════════════════
_NETS_BRAIN = (
    Net("KEY_SENSE",
        (("R108", "2"), ("R109", "1")) + _hvlink("KEY_SENSE") +
        _pwrup("KEY_SENSE") + (("U401", "IO1"),),
        interface="HV-LINK", gpio="GPIO1",
        source=f"{_S}.7 / §4.4 — IN-12, ADC1_CH0, 330 k/10 k gives 84 V → 2.47 V. "
               f"⛔ Q10: the divider is on HVIN and the pin on BRAIN, so it crosses "
               f"HV-LINK (whose documented content is only '84 V up, 5 V down') AND "
               f"PWR-UP. ⚠️ rules.ANALOG_NETS calls this net 'IN-12', so the ADC1 "
               f"check does not currently see it under its net-table name"),
    Net("SDA",
        (("U401", "IO13"), ("U402", "SDA"), ("U403", "SDA"), ("R434", "1")),
        gpio="GPIO13",
        source=f"{_S}.6 — bar inputs only now (BD-5). D16 asks for 'strong "
               f"pull-ups'; ⬜ the value is never stated"),
    Net("SCL",
        (("U401", "IO14"), ("U402", "SCL"), ("U403", "SCL"), ("R435", "1")),
        gpio="GPIO14", source=f"{_S}.6 — ⬜ pull-up value unstated"),
    Net("MCP_INT", (("U402", "INTA"), ("U401", "IO35")), gpio="GPIO35",
        source=f"{_S}.6 — GPIO35 is free only because the part is an -N8 (R7)"),
    Net("MCP_RESET", (("U402", "RESET"), ("U403", "RESET")),
        source=f"{_S}.6 — ⬜ Q16: NOT DOCUMENTED. The part has a RESET pin that must "
               f"be HELD HIGH or it stays in reset, and no document says what drives "
               f"or pulls it. Nothing is invented: the two pins are tied and the net "
               f"has no source"),
    Net("TWAI_TX", (("U401", "IO33"), ("U404", "D")), gpio="GPIO33",
        source=f"{_S}.6 / §4.4 — R7/R14: recovered on a custom board. CAN hardware "
               f"is fitted though D19 parks the feed"),
    Net("TWAI_RX", (("U404", "R"), ("U401", "IO34")), gpio="GPIO34",
        source=f"{_S}.6 / §4.4 — R7/R14 recovered"),
    Net("CANH", (("D405", "ch1"), ("U404", "CANH"), ("R401", "1"), ("J405", "8")),
        leaves_box=True, interface="STACK",
        source=f"{_S}.6 — display pin 8, RED-BLACK. The panel terminates its own end "
               f"(132.4 Ω); the pair reading 68 Ω is the CAN pre-flight gate. "
               f"⚠️ Crosses STACK since the 2026-09-18 display move: J405 is on DRV, "
               f"the SN65HVD230 stays on BRAIN. This is the cost of the move"),
    Net("CANL", (("D405", "ch2"), ("U404", "CANL"), ("R401", "2"), ("J405", "7")),
        leaves_box=True, interface="STACK",
        source=f"{_S}.6 — display pin 7, GREEN-BLACK. Crosses STACK, as CANH"),
    Net("UART1_TX", (("U401", "IO17"), ("R436", "1")), gpio="GPIO17",
        source=f"{_S}.6 — class E: 1 kΩ series and the PIN IS TRI-STATED WHENEVER "
               f"NOT SENDING"),
    Net("UART1_TX_WIRE", (("R436", "2"), ("J404", "2"), ("D404", "ch1")),
        leaves_box=True,
        source=f"{_S}.6/§3.3 — J404.2, RED/BLACK, labelled 'RXD'. ⬜ M9: the label is "
               f"ambiguous and the direction must be MEASURED — tapping the wrong "
               f"one gives a listener that hears nothing"),
    Net("UART1_RX", (("J404", "1"), ("U401", "IO18"), ("D403", "ch4")),
        gpio="GPIO18", leaves_box=True,
        source=f"{_S}.6 — IN-13, a LISTEN-ONLY tap, direct 3.3 V, no isolation "
               f"(common ground). J404.1 is BROWN/BLUE, labelled 'TXD'. ⬜ M9"),
    Net("BOOST_CMD", (("U401", "IO48"), ("R424", "1")), gpio="GPIO48",
        source=f"{_S}.6 / §4.4 — R9: a DEDICATED native pin, NEVER on a bus. A "
               f"garbled bus frame must not be able to assert boost"),
    Net("BOOST_GATE", (("R424", "2"), ("Q401", "G"), ("R425", "1")),
        source=f"{_S}.6 — R425 is the HARD external pull-down (BDR §3 L4): boost "
               f"defaults OFF through the boot's high-Z window (D14)"),
    Net("BOOST_OUT", (("Q401", "D"), ("J404", "5"), ("D404", "ch2")),
        leaves_box=True,
        source=f"{_S}.6 — open-drain to the controller's CruisePin (PIN17), default "
               f"OFF. ⛔ METER THE WIRE BEFORE FITTING A 30 V FET: the same 30-pin "
               f"harness carries pink 60VC at 72-84 V. Fallback is a PC817 opto"),
    Net("TT_L", (("D406", "ch1"), ("R426", "2"), ("J405", "1")), domain="12V", leaves_box=True,
        source=f"{_S}.6 — display pin 1, telltale LEFT, 0-15 V input fed from the "
               f"TURN_L LAMP FEED through ~1 kΩ. ⚠️ Q18: a 12 V net on the 3V3 board"),
    Net("TT_R", (("D406", "ch2"), ("R427", "2"), ("J405", "4")), domain="12V", leaves_box=True,
        source=f"{_S}.6 — display pin 4, telltale RIGHT. ⚠️ Q18"),
    Net("TT_HL", (("D406", "ch3"), ("R428", "2"), ("J405", "5")), domain="12V", leaves_box=True,
        source=f"{_S}.6 — display pin 5, telltale HEADLIGHT. ⬜ Q22: fed from HIGH "
               f"here (PLAN §7's flash-with-no-firmware argument), so LOW beam does "
               f"NOT light it. One resistor, two, or a diode-OR is undecided"),
    Net("DISP_ONELINE", (("D406", "ch4"), ("R429", "2"), ("J405", "9")), leaves_box=True,
        source=f"{_S}.6 — display pin 9 through 1 kΩ. ⛔ Q19: the FarDriver's BROWN "
               f"one-line lead is on NO MODULE CONNECTOR — J404's six conductors are "
               f"full — so R429.1 has no source and this net is only half a path"),
    Net("USB_DM", (("J401", "1"), ("U401", "IO19")), gpio="GPIO19",
        source=f"{_S}.6 / §4.4 R3 — reserved in silicon for native USB console/flash, "
               f"which frees a UART and is the OTA fallback. ⚠️ rules.strapping_pins "
               f"flags ANY net on GPIO19/20, so it fires here on the one net that is "
               f"entitled to the pin — a rule gap, not a design fault"),
    Net("USB_DP", (("J401", "2"), ("U401", "IO20")), gpio="GPIO20",
        source=f"{_S}.6 / §4.4 R3 — as USB_DM"),
)

# ── the class-A conditioned inputs (PLAN §4): 1 kΩ pull-up · 1 kΩ series ·
# ── 100 nF at the pin, plus the ESD array, all at the MODULE end (BENCH).
# The pull-up sits on the CONTACT side of the series resistor: the stated
# 3.3 mA of wetting current is 3.3 V / 1 kΩ through the contact itself.
_NETS_CLASS_A: tuple[Net, ...] = ()
for _pu, _se, _cp, _net, _bit, _cn, _tv in _CLASS_A:
    _wire_pins = ((_pu, "1"), (_se, "1"))
    if _cn:
        _wire_pins = (_cn,) + _wire_pins
    if _tv:
        _wire_pins = _wire_pins + (_tv,)
    _NETS_CLASS_A += (
        Net(f"{_net}_WIRE", _wire_pins, leaves_box=bool(_cn),
            source=f"{_S}.6/§3.3 — the harness side of {_net}: pull-up, series and "
                   f"TVS all at the module end. "
                   + (f"Lands on {_cn[0]}.{_cn[1]}."
                      if _cn else
                      "⛔ Q21: the throttle's red button is a 2-pin dry-contact lead "
                      "with NO CONNECTOR ALLOCATED, so this node reaches nothing.")),
        Net(_net, ((_se, "2"), (_cp, "1"), ("U402", _bit)),
            source=f"{_S}.6 — the conditioned node at expander #1's {_bit}. The BIT "
                   f"is a generator-side allocation: the documents say only '12 of "
                   f"16 bits', and §4.5's rule is wire them now, assign them in "
                   f"firmware later"),
    )

del _pu, _se, _cp, _net, _bit, _cn, _tv, _wire_pins   # loop temporaries

_NETS = (_NETS_84V + _NETS_RAILS + _NETS_12V + _NETS_BRAKE + _NETS_STACK
         + _NETS_BRAIN + _NETS_CLASS_A)

# ════════════════════════════════════════════════════════════════════════════
# CONNECTORS — §3.  One keyed shell per harness bundle (BDR §6), never
# per-wire terminals: a screw terminal is 10-12 mm against the logic layers'
# 6 mm ceiling, and ⛔ "colour is never evidence on this bike" — a keyed shell
# makes a mis-plug physically impossible where colour cannot.
# BD-8: right-angle, edge-facing, low-profile (≤6 mm) wherever current allows.
# ⬜ M19: the connector FAMILY IS UNCHOSEN and §4's entire 3.9 mm height margin
# rests on it. `model.Connector` carries no height, so `rules` cannot check it.
#
# ⛔⛔ PIN NUMBERS ARE A GENERATOR-SIDE INDEX. For the pods the binding key is
# the pigtail COLOUR + GAUGE: cavity numbering is unmarked and counting from one
# edge gives mirrored order between the two halves, so a map written in pin
# numbers is wrong on one end of the pair by construction (§3, BENCH).
# ════════════════════════════════════════════════════════════════════════════
_SRC3 = f"{_INV} §3"


def _bus_pins(nets: tuple[str, ...]) -> tuple[ConnPin, ...]:
    return tuple(ConnPin(i + 1, n) for i, n in enumerate(nets))


def _stack_conn_pins() -> tuple[ConnPin, ...]:
    """2 × 25 with alternating grounds: odd = signal, even = GND."""
    pins = []
    for i, sig in enumerate(_STACK_SIGNALS):
        pins.append(ConnPin(2 * i + 1, sig))
        pins.append(ConnPin(2 * i + 2, "GND"))
    return tuple(pins)


_STACK_NOTE = (
    "2 × 25, alternating grounds, CS1/CS2 ground-flanked by construction. "
    "⭐ Resized from BDR §5's 2 × 20, which gave 20 signal contacts against a "
    "real demand of 23 counted from this netlist. 2 contacts spare. "
    "⚠️ RUN/START/KEY_SENSE are deliberately NOT here — they route on PWR-UP "
    "and HV-LINK and stay copper end to end (BD-7)."
)

_CONNECTORS = (
    # ── HVIN ────────────────────────────────────────────────────────────────
    Connector("J101", "HVIN", "B+/B− harness (§3.1, BDR §6) — ⚠️ the KLKD002 fuse "
              "in its FEB-11-11 holder is UPSTREAM IN THE HARNESS, not a board part",
              (ConnPin(1, "HV_BPLUS", "⬜ not stated — 84 V tap"),
               ConnPin(2, "GND", "⬜ — B− to the controller stud"))),
    Connector("J102", "HVIN", "KEY switch (§3.1, BDR §6) — the mechanical key; carries ~0.25 mA",
              (ConnPin(1, "HV_BPLUS"), ConnPin(2, "KEY_SW_OUT"))),
    Connector("J103", "HVIN", "KEY out → FarDriver (§3.1) — 1 conductor, the return is the shared B−", (ConnPin(1, "FD_KEY"),)),
    Connector("J104", "HVIN", "HV-LINK, L1 side (§1.1, BD-3/BD-4) — 2.54 mm header with alternate pins SKIPPED for 5.08 mm effective. ⬜ Q1: pin count never stated", _bus_pins(_HVLINK_NETS),
              leaves_box=False, pitch_mm=5.08, interface="HV-LINK"),
    # ── CONV ────────────────────────────────────────────────────────────────
    Connector("J201", "CONV", "HV-LINK, L2 side (§1.2, BD-4) — ⬜ Q1 as J104", _bus_pins(_HVLINK_NETS),
              leaves_box=False, pitch_mm=5.08, interface="HV-LINK"),
    Connector("J202", "CONV", "PWR-UP, L2 side (§1.2, BDR §5) — 2 × +12 V, 3 × GND, +5 V, KEY_SENSE, RUN, START", _bus_pins(_PWRUP_NETS),
              leaves_box=False, interface="PWR-UP"),
    # ── DRV ─────────────────────────────────────────────────────────────────
    Connector("J301", "DRV", "Headlight (§3.2, M4) — 4-pin keyed, right-angle ≤6 mm", (
        ConnPin(1, "LAMP_COMMON", "black — common GROUND (M4)"),
        ConnPin(2, "HL_HIGH", "green — HIGH beam"),
        ConnPin(3, "HL_LOW", "blue — LOW beam"),
        ConnPin(4, "HL_DRL", "yellow — DRL"),
        # ⛔ the assembly's RED lead is UNUSED (M4): do not land it.
    )),
    Connector("J302", "DRV", "Tail + rear signals (§3.2, M5/M6) — 5-pin", (
        ConnPin(1, "LAMP_COMMON", "black — common (M5)"),
        ConnPin(2, "TAIL_RUN", "yellow — running, 0.05 A"),
        ConnPin(3, "TAIL_STOP", "red — STOP, 0.12 A, switched by Q1 in hardware"),
        ConnPin(4, "TURN_L", "blue — rear LEFT (M6)"),
        ConnPin(5, "TURN_R", "green — rear RIGHT (M6)"),
    )),
    Connector("J303", "DRV", "Front turn L/R (§3.2) — 4-pin, isolated 2-wire pairs", (
        ConnPin(1, "TURN_L", "⬜ not stated — front LEFT feed"),
        ConnPin(2, "LAMP_COMMON", "⬜ — ⬜ M6: confirm the front pair's return may "
                                  "share the tail common before paralleling"),
        ConnPin(3, "TURN_R", "⬜ — front RIGHT feed"),
        ConnPin(4, "LAMP_COMMON", "⬜ — as pin 2"),
    )),
    Connector("J304", "DRV", "Horn (§3.2, M7) — 2-pin", (
        ConnPin(1, "V12", "⛔ BLUE IS THE POSITIVE"),
        ConnPin(2, "HORN_N", "black = '−'. ⛔ red is NOT positive; role unconfirmed"),
    )),
    Connector("J305", "DRV", "Fan + buzzer (§3.2) — 4-pin", (
        ConnPin(1, "V12", "⬜ — fan +"),
        ConnPin(2, "FAN_RTN", "⬜ — fan −, flyback diode required"),
        ConnPin(3, "V12", "⬜ — buzzer +"),
        ConnPin(4, "BUZZ_RTN", "⬜ — buzzer −, LEDC PWM"),
    )),
    Connector("J306", "DRV", "Brake levers (§3.2) — 4-pin, ⬜ GATED ON M3", (
        ConnPin(1, "LEVER_L", "⬜ M2 identifies them in loom '1T3 10'"),
        ConnPin(2, "GND", "⬜ — left lever return"),
        ConnPin(3, "LEVER_R", "⬜"),
        ConnPin(4, "GND", "⬜ — right lever return. ⬜ M3: one pair per lever or "
                          "shared? A 3-wire sensor changes this connector's width"),
    )),
    Connector("J307", "DRV", "PWR-UP, L3 side (§1.3, BDR §5)", _bus_pins(_PWRUP_NETS),
              leaves_box=False, interface="PWR-UP"),
    Connector("J308", "DRV", "STACK, L3 side (§1.3, BDR §5) — " + _STACK_NOTE, _stack_conn_pins(),
              leaves_box=False, interface="STACK"),
    # ── BRAIN ───────────────────────────────────────────────────────────────
    Connector("J401", "BRAIN", "USB-C, native console/flash (§3.3) — ⬜ Q4: no part number, no CC resistors, no D± ESD specified", (
        ConnPin(1, "USB_DM", "D− ⛔ reserved in silicon"),
        ConnPin(2, "USB_DP", "D+ ⛔ reserved"),
        ConnPin(3, "", "VBUS — ⬜ Q4: whether it feeds anything is unspecified. "
                       "⚠️ never feed the 5 V rail from the bike with USB plugged in"),
        ConnPin(4, "GND", "GND + shield — ⬜ Q4: shield-vs-GND strategy unstated"),
    ), leaves_box=False),
    Connector("J402", "BRAIN", "Left pod, 9-pin shell / 8 conductors (§3.3, BENCH) — module carries the MALE half", (
        ConnPin(1, "GND", "thick green ← pod ground bundle (6 wires)"),
        ConnPin(2, "", "thin green — SPARE, not connected as built. ⬜ tying it to "
                       "the same junction doubles GND for one solder joint"),
        ConnPin(3, "IN04A_LOW_WIRE", "thick blue ← pod 'light blue' (IN-04a)"),
        ConnPin(4, "IN04B_HIGH_WIRE", "thick yellow ← pod 'blue' (IN-04b)"),
        ConnPin(5, "IN03_HORN_WIRE", "thin blue ← pod 'brown' (IN-03)"),
        ConnPin(6, "IN01_TURN_L_WIRE", "thin yellow ← pod 'green-black' (turn, IN-01)"),
        ConnPin(7, "IN09_FLASH_WIRE", "thin red ← pod 'red-gold' (IN-09)"),
        ConnPin(8, "IN02_TURN_R_WIRE", "thin white ← pod 'green-white' (turn, IN-02)"),
        ConnPin(9, "IN10_HAZARD_WIRE", "thin black ← pod 'green-black' (hazard, IN-10). "
                                       "⚠️⚠️ A SIGNAL ON BLACK, ON PURPOSE: mistaken "
                                       "for ground and tied down, both indicators "
                                       "flash continuously — a loud failure instead "
                                       "of a silent dead control"),
    )),
    Connector("J403", "BRAIN", "Right pod, 5 conductors (§3.3, BENCH, rewired 2026-09-12) — slider is OFF / A / A+B, so headlight implies running IN HARDWARE", (
        ConnPin(1, "GND", "blue — ⛔ GROUND FOR ALL THREE CONTROLS"),
        ConnPin(2, "IN08A_RUNNING_WIRE", "black — running-light SIGNAL (IN-08a), "
                                         "closed in slider positions 2 and 3"),
        ConnPin(3, "IN08B_HEADLIGHT_WIRE", "yellow — headlight SIGNAL (IN-08b), "
                                           "closed in position 3 only"),
        ConnPin(4, "RUN", "red — run/off toggle, BD-7 hardware net"),
        ConnPin(5, "START", "green — start button, BD-7 hardware net"),
    )),
    Connector("J404", "BRAIN", "FarDriver signal, 6 conductors (§3.3, BDR §6)", (
        ConnPin(1, "UART1_RX", "brown/blue, labelled 'TXD' — ⬜ M9, measure it"),
        ConnPin(2, "UART1_TX_WIRE", "red/black, labelled 'RXD' — ⬜ M9"),
        ConnPin(3, "", "brown/green = BW5V, 5 V OUT of the controller. ⬜ the "
                       "module's use of it is never stated. ⚠️ never feed a "
                       "3.3 V-only adapter from it"),
        ConnPin(4, "GND", "black — serial ground, the reference for every measurement"),
        ConnPin(5, "BOOST_OUT", "⬜ colour unknown (CruisePin PIN17). ⛔ METER FIRST"),
        ConnPin(6, "BL", "yellow/green. ⛔ not grey BH — High Brake stays capped"),
    )),
    Connector("J405", "DRV", "Display, 9-pin (§3.3) — ⏸️ footprint fitted, parked with D19", (
        ConnPin(1, "TT_L", "⬜ — telltale LEFT, 0-15 V in"),
        ConnPin(2, "", "⬜ Q20 — display supply. ⏸️ D11 parked; under D19 the dash "
                       "feeds from switched B+ externally. Carried unconnected"),
        ConnPin(3, "GND", "⬜ — ⛔ NEVER SWITCH PIN 3 / B−: float it and current "
                          "back-feeds through the signal wires"),
        ConnPin(4, "TT_R", "⬜ — telltale RIGHT"),
        ConnPin(5, "TT_HL", "⬜ — telltale HEADLIGHT, ⬜ Q22 which feed"),
        ConnPin(6, "", "red — reserved: 'the only candidate output' on the panel; "
                       "its five keys are all internal (M11)"),
        ConnPin(7, "CANL", "green-black"),
        ConnPin(8, "CANH", "red-black — the panel terminates its own end"),
        ConnPin(9, "DISP_ONELINE", "brown (FarDriver lead) — ⚠️ 1 kΩ series required"),
    )),
    Connector("J406", "BRAIN", "STACK, L4 side (§1.4, BDR §5) — " + _STACK_NOTE, _stack_conn_pins(),
              leaves_box=False, interface="STACK"),
    Connector("J407", "BRAIN", "PWR-UP, L4 side (§1.4) — BDR §5: PWR-UP is L2 → L3/L4", _bus_pins(_PWRUP_NETS),
              leaves_box=False, interface="PWR-UP"),
)


def current() -> Design:
    """The design as it stands today. The ONE API — `.parts`, `.nets`,
    `.connectors`, plus `board_of` / `part` / `net`. Nothing else in the tool
    chain builds a Design from anything but this."""
    return Design(parts=_PARTS, nets=_NETS, connectors=_CONNECTORS)
