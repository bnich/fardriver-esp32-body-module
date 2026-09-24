# FarDriver ESP32 body module

An **ESP32-S3 body control module** for an electric vehicle running a FarDriver controller on a 72 V
(84 V full) pack. It takes over lighting, turn signals, horn, boost, the brake lamp and the motor
cut, offers four 12 V and four 5 V spare outputs, reads the controller's serial link, and serves a
status page over WiFi.

Built for a Ride1Up REVV1 FS converted to a 5 kW hub motor
([`Revv1-FS-72v-Conversion`](https://github.com/bnich/Revv1-FS-72v-Conversion)), but the power design
and the FarDriver interfacing are not specific to that bike.

> 🚧 **Design stage — no firmware yet, no module hardware built.** Here: the plan, the bill of
> materials, the bench measurements, and the design-time tooling that holds the custom board set as a
> checked netlist ([`tools/`](tools/README.md)). The left bar pod is wired and tested. Bench firmware
> for the display protocol belongs to a companion repository that is not yet published (see below).

---

## What it does

| | |
|---|---|
| **Lighting** | 3-position slider + high/low toggle, both plain dry contacts. A rear momentary button is flash-to-pass |
| **Turn signals** | Push-push latching buttons that self-centre, so the switch shows no state — the module **auto-cancels** (20 s above 15 km/h, or 60 s regardless). A dedicated hazard control |
| **Horn** | 12 V electronic horn, 0.10 A |
| **Boost** | The throttle's red button → module → FarDriver boost input, hold or toggle |
| **Brakes** | Each lever is a plain input on an interrupt; the module cuts the motor on the FarDriver `BL` and lights the brake lamp |
| **Spare outputs** | **4 × 12 V and 4 × 5 V**, 1 A each, current-limited, on their own connector rows — unassigned, for whatever gets added |
| **Readout** | **A WiFi status page** — motor and controller temperature, bus current, boost mode, lamp-out. The module has **no screen of its own** |

The module takes each function over **one at a time**, as each is built and wired.

⚠️ **The brake cut, the brake lamp and the run/off kill are FIRMWARE functions.** The module has no
dedicated brake circuit: the levers are plain inputs on native pins, `BL` is an open-drain output,
and the stop lamp is an ordinary current-limited smart-switch channel. **With the firmware not
running — key-on before boot, a watchdog restart, an OTA reboot, a dead or unflashed module — the
motor cut is RELEASED and the brake lamp is OFF.** That is the owner's decision: the bike always
drives. The accepted consequence, stated plainly: a hang or restart while braking loses the cut and
the lamp for up to ~0.8 s, and a dead module loses them entirely, with nothing to warn the rider.
**The one hardware kill is the key switch**, which feeds the FarDriver KEY wire directly and never
passes through the module. All lights are OFF at key-on and every gate biases OFF, so a hung module
drives no lamps.

⚠️ **Starting the bike is not the module's job.** The key switch feeds the FarDriver KEY wire directly;
the module takes one tap off it, on the same plug as the pack, to switch its own supply and to sense
key state. It never sources or switches KEY, and there is no start latch.

---

## ⚠️ The 84 V problem

This is the thing that catches people, and it runs through the whole BOM.

**The pack is above nearly everything the 12/24/48 V market sells.** Check the voltage line on every
single part.

| | |
|---|---|
| **Converters need a 160 V input rating** | TDK `CN150B110-12`, Cincon `EC7BW-110S05` |
| **TVS** | `SMCJ90A` on B+. None on the key tap: it is a high-impedance input, and a TVS there that failed short would cut the FarDriver KEY |
| **Do-not-exceed** | **160 V DC including transients** |
| **Size input protection at the 60.0 V LVC, not at full charge** | Converters are constant-power loads, so current is highest when the pack is lowest. Module draw: **1.93 A at LVC**, derived from the 12 V budget — 8.47 A nominal, of which 2.62 A is lamps and loads (1.62 A measured) and 5.85 A the eight aux outputs ([plan §3.2.3](docs/plan.md); `tools/power_budget.py` owns it) |
| **`TPS4H160B` smart switches are 40 V parts** | 12 V rail only — **never** the 84 V node. Their `CL` and `CS` pins each need a resistor; TI's pin names are `VS` / `SEL` / `SEH` |
| **Small-signal FET on the 84 V node** | **`BSS127`** (600 V, enhancement-mode). ⛔ Not its sibling `BSS126` — that one is **depletion-mode**, conducting at V<sub>GS</sub> = 0 |
| **Low-voltage TVS parts follow the line's idle voltage** | The 5 V array `SMS05T1G` on every 3.3 V-class line, the brake levers included · the 15 V array `SMS15T1G` on `BL` / `ACC+` and the boost output · a single-line `SMF18A` on every 12 V lamp, load and aux output, an `SMF6.0A` on every 5 V aux output, and an `SMBJ18A` on the 12 V rail itself. A 5 V array on a 12 V line is a dead short |
| **Fuses** | Schurter **`FST`** (glass) and **`SP`** (ceramic fast-acting) 5×20 have **no DC rating**. Only time-lag **`SPT`** does. Order by part number. A fuse holder has no breaking capacity |

**Module ground stars at the controller's B− stud**, not the battery's.

---

## ⚠️ ESP32-S3 specifics

- **`R8`/`R16V` modules are rated only to 65 °C.** Use **`-N8`** (85 °C) or `-H4` (105 °C). An
  under-seat cavity on a dark vehicle exceeds 65 °C.
- **No wire leaves the box on strapping pins 0/3/45/46.**
- **Analog only on GPIO1–10** — ADC2 dies when WiFi is on.
- **The `ESP32-S3-WROOM-1` module has no IO33 or IO34 pads.** On a custom board with no USB port the
  clean GPIO pool is **32** — and this design uses all 32, with none spare.
- **`ESP32-S3-WROOM-1` and `-WROOM-1U` share one footprint.** The `-1U` takes an external antenna, which
  matters because a metal enclosure — or a metal cavity — kills a PCB antenna.
- **`MCP23017` pins GPA7 and GPB7 are output-only** — a 16-bit expander offers 14 inputs.
- Prototype is an ESP32-S3 DevKitC-1 **v1.0** (RGB LED on GPIO48) with an `ESP32-S3-WROOM-1-N8`.
- ESP-IDF **v5.5**.

Construction path: breadboard → FR4 plated perfboard → custom PCB. The custom build is **four
stacked 4-layer boards, 41.84 × 242 mm, POWER 42.3 × 242** — **POWER** (84 V entry, the soft-start, both converters
and the pack plug) · **OUTPUTS** (the 12 V drivers) · **LOGIC** (the S3, every input and all three
expanders) · **CTRL** (every FarDriver connector, the 5 V aux supply and its switches) — joined at
three junctions: POWER ↔ OUTPUTS by one cable, OUTPUTS ↔ LOGIC and LOGIC ↔ CTRL by mated 2.54 mm
header pairs, so a breadboard section can stand in for any one
board. **Each board owns one row of harness connectors on
one face of the box**, grouped by kind ([plan §9.2](docs/plan.md)).
**Carry the pin *rules* to the custom board, not the GPIO numbers.**

---

## Where the design stands

The board set exists as a checked netlist ([`tools/netlist.py`](tools/netlist.py)) and a generated
EasyEDA Pro project. No board is laid out yet.

- **Power.** Two isolated converters behind the soft-start switch: a TDK brick for the 12 V loads
  (**8.47 A nominal**, 68 % of its rating) and a Cincon module for the 5 V logic, kept apart so a lamp
  or horn fault cannot brown out the brain. A third supply, a buck off the 12 V rail, feeds the 5 V
  aux outputs, so a shorted aux wire cannot brown out the brain either. **No raw 12 V leaves the
  box:** every 12 V output is a `TPS4H160B` channel (current-limited, with open-load and fault
  reporting), and horn, fan and buzzer share one more such channel and are switched on their return.
  Nothing on LOGIC draws 12 V — the rail crosses that board on copper only, on its way to the aux
  buck on CTRL.
- ⛔ **One firmware behaviour holds a part inside its rating, and it is the only one.** `Q101`, the
  soft-start switch, stays on for ~0.8 s after key-off; with all eight aux outputs still on it would
  carry a 162 W bound against a 138 W derated DC SOA line. **The firmware releases every aux output
  when key sense goes inactive**, which brings it to ~53 W. **Every expander's `RESET` rides the
  S3's `EN` net**, so a reset that arrives through `EN` — power-up, the programmer, a fitted
  supervisor — resets the chip that commands every aux output and the drivers' own pull-downs take
  over. `EN` is an input the S3 cannot drive, so a watchdog or software restart does not reach it:
  the exposure is a hang **or a reboot** inside the hold, through the shortest hold (~300 ms at the
  cutoff voltage with a slow FET), and closing the reboot case needs a reset the S3 itself drives —
  an open owner decision. `tools/soft_start.py` gates on the shed case.
- **Service.** No USB port: first flash, the console and recovery when OTA fails run over UART0, on a
  Tag-Connect TC2030-NL land on LOGIC — bare pads in the ESP-Prog's order, reached with a
  `TC2030-IDC-NL` cable ([BOM](docs/bom.md) A8). Later updates go over WiFi.
- **Harness.** Every wire enters on a locking pluggable screw terminal, and the terminals stand in
  rows on one face of the box, **each row the edge of one board** — the pack plug alone on POWER,
  the 12 V row on OUTPUTS, the inputs on LOGIC, and the controller leads with the 5 V outputs beside
  them on CTRL. **Each dangerous group owns a pitch nothing else uses:** 7.62 mm for pack voltage (one
  connector), 5.08 mm for the FarDriver leads, 3.50 mm for the 5 V outputs; everything else shares
  3.81 mm, where no 12 V terminal has the same size as an input terminal
  ([BOM](docs/bom.md) X8, X9, X11, X12).
- **Assembly.** JLC places everything but the two converters and the two input chokes, which are
  hand-soldered, and the parts that must lie flat or clip in, which are ordered loose with the boards
  ([BOM](docs/bom.md#jlc-assembly--the-custom-boards)).
- **Board-to-board.** Three junctions, **one cable and three mated pairs**. POWER ↔ OUTPUTS is the
  **cabled** one, because no stocked connector spans the gap the 22 mm chokes force: the whole 12 V
  load crosses on **five conductors into a keyed JST VH connector** — `V12` out on 16 AWG and the
  return on **two** 16 AWG conductors, into contacts JST rates at 10 A with that gauge (⛔ genuine
  JST only: "VH" clones list identically and are rated 3 A) — with `V5` and `KEY_SENSE` on 22 AWG
  beside them. A keyed shell that cannot seat reversed replaces the mated pairs'
  read-the-same-from-both-ends contact order, and **brass M3×30 standoffs set that gap at 30.0 mm**
  — bonded to ground at the OUTPUTS end only, so a brass post is never an unrated third return.
  **That loom is the sole 12 V return** (D27/IO-27 restating IO-23): the CTRL ribbon whose 13
  grounds used to carry ~79 % of it is deleted, which is why the return runs on two conductors —
  ~4.24 A each in service, and one open crimp leaves 8.47 A on the survivor, inside its 10 A
  contact. The other two junctions are rigid, mated 2.54 mm pairs whose butting insulators set each
  gap at 11.0 mm: OUTPUTS ↔ LOGIC takes `PWR-LOGIC` (1 × 14) and `STACK` (2 × 27), LOGIC ↔ CTRL
  takes `CTRL-STACK` (2 × 22) — every signal beside a ground in both spines.
- ✅ **The cavity is measured, and the boards are shaped to it.** M18 came back **260 mm along × 70
  across × 100 tall** (owner, 2026-09-20). The 48 × 219 mm boards did not go in it — they needed
  74.65 mm across — so **IO-17** re-shapes them to the measurement. That inverts IO-14's search
  order, which took least length first because length was the axis further over the *estimate*: the
  measured cavity allows a board **246.0 mm long but only 43.35 mm wide**, so the rule is now to take
  the narrowest board that still clears every budget by 10 % and spend the abundant length. **IO-18**
  then stands the width clear of a packing discontinuity. The result is **41.84 × 242.0 mm** (POWER alone 42.3 mm deep, for its pack-voltage routing):
  `python3 -m tools.board_fit` closes every area, pack and row budget on it (pack 32 % and density
  44 % of margin; every row is inside the 90 % line except OUTPUTS' 12 V row, which stands at
  **96.6 %** of the 228 mm edge — the one stated exception, D27/IO-24, bought to give every 12 V
  terminal its own size) and derives
  the stack at **81.0 mm of 94.0 available** across four boards. The cavity that
  implies is **256.0 mm along × 68.95 across × 87.0 tall**, inside the measurement by **4.00, 1.05
  and 13.0 mm**. ⚠️ **Width is the axis with least room** — 1.05 mm, and 19.65 mm of the 68.95 is the
  plug-and-bend room in front of the connector face, so anything that deepens a harness plug spends
  it. ⭐ **The gate is live**: `board_fit` and the rules gate now compare a real measurement, so an
  envelope that outgrows the cavity **FAILS**. The requirement itself is not final — the wall, floor
  and lid are allowances until the all-metal enclosure is modelled, **which happens after the boards
  are laid out, not before** — the pack and density budgets predict that a board can be routed;
  layout proves it, and proves the size the box has to hold. Layout has room to grow the boards to
  **43.35 × 246 mm** before the cavity gate fails. ⚠️ The wall is the exception to that order: it is
  an input to the board width, and today's 42.3 mm POWER board tolerates a wall up to **3.52 mm**.
- ⛔ **The EasyEDA project is NOT proven against this netlist.** IO-26 and IO-27 re-partitioned the
  design on 2026-09-22 — CTRL is a fourth board, the CTRL ribbon is gone, the 5 V aux block and
  expander #3 moved, and all three mated pairs changed size — which voids every proof taken before
  it. **All four boards** must be re-imported, their netlists
  exported and checked identical with `python3 -m tools.tel_check` before the boards are ordered.
  **No board is laid out yet** — layout is the next step, and the enclosure is drawn after it
  (D27/IO-19).

---

## ⚠️ Never enable CAN on a non-CAN FarDriver

On non-CAN units the CAN transceiver lands on **A11/A12 — the Hi/Low speed sense lines.** The module
impersonates a CAN FarDriver toward the display; the controller itself stays on one-line with
`CANConfig` = `None`.

---

## Documents

| | |
|---|---|
| [**docs/plan.md**](docs/plan.md) | The module plan — architecture, decisions (D1–D27), pin map, power design, the four-board partition and the connector rows (§9.2), per-function takeover. The critical path is in its header |
| [**docs/bom.md**](docs/bom.md) | Bill of materials and order tracker. **This owns procurement** — change a part here first, then the plan section its Notes names. It also says what JLC places, what is ordered loose and what you hand-solder |
| [**docs/inputs-bench-session.md**](docs/inputs-bench-session.md) | Bench procedure and results for the switch sets, brake-lever wires, lever switch type, red button, serial direction and KEY tap |
| [**tools/**](tools/README.md) | Design-time tooling, stdlib Python. `tools/netlist.py` **is** the board set — parts, nets, connectors, board assignment — and the checks below gate every change to it |

```bash
python3 -m tools.integrity     # structural gate: every pin of every part lands somewhere
python3 -m pytest              # the rule and unit tests
python3 -m tools.board_fit     # area, height and connector-row budget, and the cavity it requires
```

## Related

Two companion repositories are **not yet published**; the plan cites documents that belong to them.

| | |
|---|---|
| **chaojie-display-protocol** | Talking to the Chaojie panels — pinouts, the one-line protocol, CAN 18, and the ESP32 bench firmware |
| **fardriver-nd72450-reference** | `.heb` parameter decoder and the controller's harness pinout |

## Licence

**[MIT](LICENSE) — for everything in this repository:** firmware, tooling, the netlist, the hardware
design and the documentation. That is a deliberate choice by the owner. The sibling hardware and
documentation repositories of this build are CC BY-SA 4.0; this one is MIT throughout.

## Disclaimer

This controls the lighting, the brake lamp and the motor cut of a 5 kW vehicle from a microcontroller
on an 84 V pack. Nothing here has been tested to any standard. ⚠️ **The brake cutoff and the brake
light are firmware functions**, by a deliberate owner decision, and they are released and off
whenever the firmware is not running. The only hardware kill is the key switch. Anyone deriving from
this should decide that question for themselves rather than inherit it.
