# CLAUDE.md — FarDriver ESP32 body module

Parent guidance: `../CLAUDE.md` — repo map, conventions, public-repo hygiene, safety rules.

## What this is

Design stage — no firmware, no module hardware built. `docs/plan.md` is the architecture and the
decision log (D1–D27); its header carries the critical path. `docs/bom.md` **owns procurement** of
what the owner buys: the breadboard parts, the parts JLC cannot place (hand-soldered), and the parts
ordered loose with the boards and fitted by the owner. Change a part there first, then the plan
section that line's Notes names. The LCSC part JLC places for each part lives in `tools/netlist.py`.

The custom build is **three stacked boards — POWER · OUTPUTS · LOGIC** (plan §9.2), each carrying one
row of harness connectors on one face of the box. `tools/netlist.py`
**is** that design: parts, nets, connectors, board assignment. The DevKitC-1 pin map in plan §3.1.3 is
the **prototype's**; the custom board carries the pin *rules*, not those GPIO numbers.

**This repo is public and holds reader-facing facts only.** The working material lives in the
workspace, unpublished: `../docs/esp32-board-design-record.md` (decisions BD-1…),
`../docs/esp32-needed-from-owner.md`, `../docs/plans/2026-09-15-esp32-board-set.md`. Do not move it
back, and do not write working notes into `docs/` here.

**Licence: MIT for everything in this repo**, documentation and hardware included — a deliberate
owner decision (2026-09-18), and an exception to the workspace's CC BY-SA default.

## The `tools/` workflow

Stdlib Python, no virtualenv, with three exceptions: `pytest` runs the tests, `cryptography` writes
the `.eprj2` (`tools/eprj2.py`), and `~/tools/lcsc-search` serves the library footprints. The gate
checks all three by name before running anything, and stops at the one that is missing. After any
change to the netlist or the model, run the gate from the repo root:

```bash
tools/gate.sh   # every check, in order, each run bare; stops at the first non-zero exit and names the tool
```

The individual commands are inside it, in the order they run — integrity, pytest, rules,
gpio_budget, power_budget, soft_start, board_fit, then the build (refused while EasyEDA Pro is
open; there is no override) and jlc_bom — and `tools/README.md` has one line per tool. Its step 0
removes every `__pycache__`: a same-second, same-size edit is otherwise read as the OLD constant,
and `-B` / `PYTHONDONTWRITEBYTECODE` do not prevent that. ⛔ **Never judge a tool through
`| tail -1`** — the pipeline returns `tail`'s 0, not the tool's exit code. Run it bare.
`build_project.py` exits 1 REFUSED (and renames the previous build `.stale`) or 2 INCOMPLETE (an
item without a footprint, or no `.eprj2`); only 0 is a project to lay out.

- ⛔ **After changing any LCSC code, run `python3 -m tools.lcsc_fixture`.** It refreshes
  `tests/fixtures/lcsc.json` — what LCSC says each ordered code is (part number, maker, package,
  symbol pins, footprint title). The tests hold the design to it offline and hold it to the live
  library where reachable, so a code pointing at the wrong part, or a stale fixture, fails.
- **The build writes `build-eprj3/layout-rules.txt`:** the HV net class (1.25 mm, IPC-2221B B2) over
  POWER's pack-voltage nets. The generated PCBs carry only the board-wide 0.2 mm, so the
  owner sets the class up in the editor before routing. Never try to emit it into the project.
- After the owner exports a board's netlist from EasyEDA (to `~/Downloads`), prove it:
  `python3 -m tools.tel_check BOARD ~/Downloads/Netlist_BOARD_<date>.tel`. It must print
  "identical", and exits 1 on any pin on the wrong net or any wrong footprint. ⚠️ A proof holds only
  for the netlist it was taken from: after a netlist change, every board it touches is re-exported
  and re-proven. ⛔ **No board is proven against the current netlist.** The audit fixes of 2026-09-21
  changed the netlist on all three boards — STACK is 2 × 29 (LOGIC, OUTPUTS), the VH land drills 1.73
  (POWER, OUTPUTS), `J303`/`J305` are 10- and 12-way (OUTPUTS), and the expanders' RESETs ride `EN`.
  Every board must be re-exported and re-proven before its layout is trusted. ⛔ **A proof dies the
  moment `netlist.py` changes.** Never carry a ✅ forward; state the commit it was taken against.

- `tools.integrity` asks whether the netlist is a circuit at all — every pin of every part lands on a
  net, every inter-board net has real connector contacts. `tools/rules.py` asks whether it obeys the
  safety and pin rules. **Green rules on a netlist that fails integrity mean nothing**: a TVS with one
  leg landed passes every rule.
- ⛔ **Never close a gap on paper only.** A part counts as protection when both its pins are on nets,
  not when a comment says so.
- A height or rating is "confirmed" only if it was read in a manufacturer PDF — say which.
- The generated EasyEDA project is a build artefact: never hand-edit it, never commit it.
- ⛔ **EasyEDA Pro 3.2.149 opens `.eprj2`, not `.eprj3`.** Open `build-eprj3/revv1-module.eprj2`.
  The editor refuses a netlist export while any part lacks a footprint. 📄 The
  `working-with-easyeda-pro` skill has the formats and the proof method.
- **LCSC parts live in `netlist.py` only**: `_R_LCSC`, `_C_LCSC`, `_FAB_BY_MPN`, `_LOOSE_BY_MPN`,
  `_FAB_CONN`, and the harness terminals' `_TERMINALS`. Never in a document. JLC Basic first; the
  part need not match what was bought. Choose with `~/tools/lcsc-search`, and check each candidate
  against the constraints in the part's `source`, never against the keyword.
- **Every part has an `assembly` class:** `jlc` (JLC places it), `hand` (LCSC has nothing that meets
  its constraints; the owner buys and solders it, reason in `_HAND_BY_MPN`) or `loose` (ordered from
  LCSC with the boards, fitted by the owner — JLC inserts through-hole parts upright, and these must
  lie flat, or clip in). Anything JLC must not fit gets `Add into BOM: no`; EasyEDA ignores DNP.
- ⛔ **A pad map is typed from the datasheet and checked against the library symbol**
  (`tools/padmap.py`, `tests/test_padmap.py`). Never infer one from a footprint's geometry. A
  wrong map wires a FET backwards on a board that passes every other check.
- **A part with no library device gets a land pattern drawn from its manufacturer's drawing**
  (`tools/drawn_footprints.py`). A footprint is the **top view, Y up**. ⛔ A drawing of the pin face
  or a **bottom view** must be mirrored, or the module's pins land left for right. The tests type
  each drawing as the vendor draws it and check the mirror (`tests/test_drawn_footprints.py`).
- **Resistors are rated parts.** A resistor's `v_max` is its chosen part's WORKING voltage, never
  the overload figure: 0603 is 75 V, 0805 150 V, 1206 200 V. `VR-UNDER` checks it against the node,
  and `VR-POWER` its V²/R against its package (a logic pin's drive capped at 40 mA ESP32, 25 mA MCP).
- **A TVS states `v_clamp`**, its datasheet clamping voltage: `VR-CLAMP` holds every part it
  protects to that figure (an `MCP23017` pin to its 20 mA I<sub>IK</sub>). A TVS without one fails.
- **`VR-CLAMP`**, **`VR-POWER`**, **`PULL-DIR`** (a contact to ground needs a pull-up) and
  **`BUS-ORDER`** (a power bus reads the same from both ends and never puts two rails side by side)
  are each proven to fire on a mutation of the real netlist: `tests/test_rules_mutations.py`, and
  `tests/test_rules.py` for `BUS-ORDER`. A new rule is not a rule until a test shows it firing on
  the defect it names.
- **Board-to-board: four interfaces on two junctions — two MATED PAIRS and two CABLES (D27/IO-20).**
  OUTPUTS ↔ LOGIC carries the pairs, **`PWR-LOGIC`** (1 × 9) and **`STACK`** (2 × 29, every signal beside a ground, `EN` the 29th
  beside a ground), stamped Hong Cheng / BOOMELE halves mating insulator-to-insulator at **11.0 mm**
  (STACK's 11.04 is the hard stop): the lower half stands on OUTPUTS, the upper half hangs **under**
  LOGIC, its footprint generated PRE-MIRRORED (`…-UNDER`), placed on the bottom layer. A
  same-numbered dual-row footprint cannot be aligned by any turn — STACK's signals would land on
  ground. POWER ↔ OUTPUTS carries the cables, because **no stocked connector spans that gap**:
  **`PWR-OUT`**, four conductors in a keyed JST VH loom (`V12` + `GND` on 16 AWG at 8.47 A each,
  `V5` + `KEY_SENSE` on 22 AWG), and **`CTRL`**, a 2 × 12 (24-way) shrouded IDC ribbon — 13 grounds,
  11 signals each flanked on both sides, the CAN pair adjacent as `G CANH CANL G`. The cable halves
  are ORDINARY, un-mirrored footprints — the POWER halves on POWER's top face, the OUTPUTS halves
  hanging under OUTPUTS into the gap; the loom carries the orientation. **Keying replaces the
  palindrome**: `BUS-ORDER` still demands that a mated pair read the same from both ends, and
  demands of a cable a positively keyed shell instead. ⚠️ The VH's keying is the wafer's **lock
  ramp**, not the omitted third post — a symmetric omission polarises nothing — ⬜ confirm on the
  first sample that a reversed housing will not seat. ⛔ **"VH" clones are rated 3 A**: CAX
  `VH-4A-HT` (C5453989) lists identically and is a 2.8× overload at 8.47 A — genuine JST only, the
  Blue Sea failure shape. ⚠️ **The brass M3×30 standoffs (C775781) SET the 30.0 mm POWER → OUTPUTS
  gap** — bonded to GND at the OUTPUTS end only (IO-21), on a copper-free pad at POWER, so
  `PWR-OUT`'s 16 AWG GND stays the sole sized return; the nylon TP-11 beside PWR-LOGIC / STACK is
  deliberately short and shimmed so the connectors keep setting that 11.04 mm gap. `integrity`
  checks each kind against what is true of it: a pair's halves face each other, mirrored; a cable's
  halves match contact for contact, unmirrored. ⛔ **HV-LINK is gone** — POWER is one board, so no
  84 V crosses an interface. ⛔ **STACK's pinout is derived from `_STACK_SIGNALS`** and has been
  renumbered twice: regenerate it from the netlist, never hand-patch a document's copy.
- **Harness terminals come in families by job, and the families are the rows** (plan §9.2): **7.62 mm
  Kefa** for pack voltage (`J101` only, the CTRL row) · **5.08 mm Kangnex** for the FarDriver leads
  and nothing else (`J309`, `J404`, and the parked `J310` / `J405`, also CTRL) · **3.50 mm Kefa** for
  the 5 V outputs and nothing else (`J314`, the 5 V row under OUTPUTS) · **3.81 mm Kangnex** for the
  12 V row and the INPUTS row. **Each dangerous group owns its pitch**, because the three dangerous
  mismates are a 5 V device in a 12 V header, a FarDriver lead anywhere else, and the pack plug
  anywhere else. Within the shared 3.81 mm family a smaller plug seats offset in a larger header, so
  **no 12 V terminal may share a size with an input terminal** — and no two 12 V terminals may share a size either (IO-24): 2, 4, 5, 7, 10, 12 against 3, 6, 8, 8,
  9 (`tests/test_interconnect.py`, `tests/test_rows.py`). A parked terminal keeps its footprint, not
  its header.

## ⚠️ The traps that matter most

- **The 84 V pack is above most of the market.** Check the voltage line on every part. Converters need
  **160 V** input; TVS is `SMCJ90A`, on B+ only — ⛔ never on the key tap `KSW`, where a failed-short
  TVS cuts the FarDriver KEY; 160 V DC is the do-not-exceed including transients.
- **Pack voltage enters on `J101` alone**, 7.62 mm pitch with an empty position around B+ and around
  `KSW`, and **never leaves POWER** — no inter-board interface carries it.
- **Size input protection at the 60.0 V LVC, not full charge** — converters are constant-power loads.
  The tap draws **1.93 A** there and the 12 V converter's input **1.88 A**, so the tap fuse is the
  3 A `KLKD003` and `L101` the 3 A `7448023005`. ⛔ **The key branch's own fuse stays 2 A** — it
  carries ~0.32 mA. `tools/power_budget.py` derives all of it.
- **`TPS4H160B` are 40 V parts — 12 V rail only**, never the 84 V node. `CL` and `CS` each need a
  resistor; TI's pin names are `VS` / `SEL` / `SEH`.
- ⛔ **`BSS126` is DEPLETION-mode — on at V<sub>GS</sub> = 0.** Wherever a 600 V small-signal N-FET is
  called for, the part is **`BSS127`** (enhancement-mode, same family, same SOT-23 pinout). A
  depletion FET as a pull-down switch holds the thing it controls ON with the key off. ⛔ And the
  **Infineon** BSS127 (V<sub>GS(th)</sub> 2.6 V max), not Diodes' `BSS127S-7` (4.5 V max, above
  D13_EN at a 43 V pack).
- **Zeners are the 2 % `B` grade.** `BZT52C15` can clamp as low as 13.8 V, only 0.7 V above Q101's
  −13.1 V running V<sub>GS</sub>.
- ⛔ **`MCP23017` GPA7 and GPB7 are OUTPUT-ONLY** (DS20001952 rev D). Never land an input on them; a
  16-bit expander offers 14 inputs.
- ⛔ **The `ESP32-S3-WROOM-1` / `-1U` module has no IO33 or IO34 pads.** They exist on the silicon
  only. The clean GPIO pool on the custom board is **32**: it has no USB port, so GPIO19/20 are
  ordinary pins there.
- **The board is flashed over UART0 at `J408`, a Tag-Connect TC2030-NL land** (D25): bare copper,
  no paste, pads in the ESP-Prog's PROG order (1 EN · 2 VDD, not connected · 3 TXD0 · 4 GND · 5 RXD0
  · 6 IO0 — TXD0 is the S3's own TX). ⛔ `TC2030-MCP-NL` is Microchip's ICSP cable; it cannot program
  an ESP32. **GPIO44 carries U0RXD and nothing else** — a harness wire there fights the programmer.
- **ESP32-S3 `R8`/`R16V` are rated to 65 °C only.** Use `-N8` (85 °C) or `-H4` (105 °C).
- **No wire leaves the box on strapping pins 0/3/45/46**; analog only on GPIO1–10 (ADC2 dies with WiFi).
- **TVS parts follow the line's idle voltage:** the 5 V `SMS05T1G` goes on every 3.3 V-class line,
  **the brake levers included** — they are plain contacts now; `BL` / `ACC+` and the boost output
  take the 15 V `SMS15T1G`; each 12 V lamp, load or aux output takes a single-line `SMF18A`, each
  5 V aux output an `SMF6.0A`, and the 12 V rail an `SMBJ18A` — never a
  15 V part there (the TDK's over-voltage window is 15.0–17.4 V). A 5 V array on a 12 V line is a
  short. ⚠️ **The `SMF6.0A` clamps at 10.3 V against the `TPS2553`'s 7 V `OUT`** — a recorded
  residual risk (plan D27/IO-12), deliberately not a rule.
- **No GPIO that comes out of reset pulled up drives an active-high enable** (`GPIO-RESET-PULL`):
  GPIO39 would light the tail at boot.
- ⛔ **Never enable CAN on this controller** — on non-CAN units the transceiver lands on A11/A12, the
  Hi/Low speed sense lines.

## Safety boundary — state it exactly

⚠️ **The brake cut, the brake lamp and the run/off kill are FIRMWARE functions** — owner decision
2026-09-19 (plan D23, design record BD-27). The module's dedicated brake/kill circuit is deleted, and
rule `LISTEN` with it. ⛔ Do not "restore" that hardware, and do not write that the module only
senses the levers: the netlist is the current state, and it says the firmware decides.

- **With the firmware not running — key-on before boot, a watchdog restart, an OTA reboot, a dead or
  unflashed module — the motor cut is RELEASED and the brake lamp is OFF** (the owner's choice; the
  bike always drives). `Q106`'s gate is held down by a fitted 10 kΩ, and `U302` IN4 by the driver's
  own internal pull-down. The accepted consequence: a hang or restart while braking loses the cut for
  up to ~0.8 s, and a dead module loses it entirely, with nothing to warn the rider.
- **The one hardware kill left is the key switch** (D24, D10): it feeds the FarDriver KEY wire
  directly, and the module never sources or switches it.
- All lights OFF at key-on, every gate biases OFF, so a hung module drives no lamps.
- **The brake lamp is fed from the module's 12 V rail**, so an unpowered module means a dark lamp.
  Never write "works with the module unpowered" about it.
- ⚠️ **`R336`, the 100 kΩ `BL` readback, is the one copper path that can work against this.** An
  unpowered or output-driven LOGIC board holds `BL_SENSE` near 0.5 V and puts 100 kΩ from `BL` to
  ground, which cuts only if the FarDriver's own `BL` pull-up is 47 kΩ or weaker — ⬜ unmeasured. That
  100 kΩ may only ever go up.
- **No raw 12 V leaves the box.** Horn, fan and buzzer ride `AUX12` (`U301` OUT1, current-limited).
  ⚠️ `AUX12` is an **ordinary firmware-driven channel** on expander #3 — nothing holds it on, so those
  three have no `+` until the firmware's first tick.
- **The module never sources or switches the FarDriver KEY (D10).** The key switch feeds KEY directly
  (D24); there is no start latch, and the start button is a spare sensed input.

### ⛔ The key-off aux shed is a HARDWARE CONTRACT (plan D27/IO-16, 2026-09-20)

**On `KEY_SENSE` going inactive the firmware releases all eight aux outputs**, inside `Q101`'s
**~774 ms** key-off hold (`C107` bleeding through `R110`). **`Q101`'s SOA margin depends on it:**
un-shed, the part carries a **162 W** bound against a **138 W** derated DC line; shed, about **53 W**,
a 2.6× margin. ⛔ **This is the only place in the design where a firmware behaviour holds a part
inside its rating — never write it as a feature, and never let a change lengthen the decay or raise
the tap current without re-running `tools/soft_start.py`.**

- ✅ **A watchdog reset, or any restart, sheds the load — because every expander's `RESET` rides the
  S3's `EN` net (IO-22, 2026-09-21).** An S3 reset resets the chip that commands every aux output;
  every bit returns to an input and the drivers' own pull-downs take over (D14). ⛔ Before IO-22 the
  expanders' resets were pull-ups to `V3P3` and nothing else — an S3 restart left them driving what
  they last drove, and `V3P3` is the last rail to fall at key-off, so nothing else reset them either.
  `EN` reaches expander #3 down a 29th STACK signal. **The exposure is narrowly a hang that holds
  the outputs on and does not trip the watchdog**, through the **shortest** hold — ~300 ms at the
  LVC with a slow FET, not the 774 ms fast-FET figure.
- `tools/soft_start.py` gates on the shed case and prints the un-shed bound beside it as the residual
  risk it is. ⬜ **M17** scopes a deliberate key-off under load.

## Parked work

The CAN dash feed is parked (**D19**). Do not resume it unprompted. Parked is not disproven —
everything in the parked documents stays correct.
