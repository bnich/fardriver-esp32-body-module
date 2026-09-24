# CLAUDE.md — FarDriver ESP32 body module

Parent guidance: `../CLAUDE.md` — repo map, conventions, public-repo hygiene, safety rules.

## What this is

Design stage — no firmware, no module hardware built. `docs/plan.md` is the architecture and the
decision log (D1–D27, with D27's sub-decisions IO-1…IO-27); its header carries the critical path. `docs/bom.md` **owns procurement** of
what the owner buys: the breadboard parts, the parts JLC cannot place (hand-soldered), and the parts
ordered loose with the boards and fitted by the owner. Change a part there first, then the plan
section that line's Notes names. The LCSC part JLC places for each part lives in `tools/netlist.py`.

The custom build is **four stacked boards — POWER · OUTPUTS · LOGIC · CTRL** (plan §9.2,
`board_params.STACK_ORDER`, bottom to top), each carrying one
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

Stdlib Python, no virtualenv, with four exceptions: `pytest` runs the tests, `cryptography` writes
the `.eprj2` (`tools/eprj2.py`), `~/tools/lcsc-search` serves the library footprints, and
pcb-layout-tools v0.5.0 (`pcbl`, installed on its own) lays the boards out. The gate checks all
four by name before running anything, and stops at the one that is missing. After any
change to the netlist or the model, run the gate from the repo root:

```bash
tools/gate.sh   # every check, in order, each run bare; stops at the first non-zero exit and names the tool
```

The individual commands are inside it, in the order they run — integrity, pytest, rules,
gpio_budget, power_budget, soft_start, board_fit, then the build (refused while EasyEDA Pro is
open; there is no override; the owner's saved layout is left untouched), jlc_bom, and the layout
constraints read by `pcbl stack` (pcb-layout-tools v0.5.0, which the gate requires by version) — and `tools/README.md` has one line per tool. Its step 0
removes every `__pycache__`: a same-second, same-size edit is otherwise read as the OLD constant,
and `-B` / `PYTHONDONTWRITEBYTECODE` do not prevent that. ⛔ **Never judge a tool through
`| tail -1`** — the pipeline returns `tail`'s 0, not the tool's exit code. Run it bare.
`build_project.py` exits 1 REFUSED (and renames the previous build `.stale`) or 2 INCOMPLETE (an
item without a footprint, or no `.eprj2`); only 0 is a project to lay out.

- ⛔ **After changing any LCSC code, run `python3 -m tools.lcsc_fixture`.** It refreshes
  `tests/fixtures/lcsc.json` — what LCSC says each ordered code is (part number, maker, package,
  symbol pins, footprint title). The tests hold the design to it offline and hold it to the live
  library where reachable, so a code pointing at the wrong part, or a stale fixture, fails.
- **The generated PCBs carry only the board-wide 0.2 mm** (JLC's capability template), and
  `build-eprj3/layout-rules.txt` states the HV net class (1.25 mm, IPC-2221B B2) over POWER's
  pack-voltage nets. ⭐ **`pcbl route rules` writes every class INTO the project** — a named `RULE`
  per category plus one `RULE_SELECTOR` per member net. Placement, routing and the layout checks are
  **pcb-layout-tools** (`pcbl`, tag v0.5.0); this repo describes the design to it through
  `tools/layout_export.py` and `tools/layout_hooks.py`. 📄 `layout/PROCESS.md`.
  ⭐ **The 1.25 mm is what pack voltage keeps from LOW-VOLTAGE copper; between two 84 V nets the
  clearance is their own voltage difference** on the same IPC-2221B B2 table (IO-29). The editor
  binds a clearance to a net and not to a pair, so `pcbl` is the authority: it routes and checks
  pairwise, its rule to the editor stays 1.25 mm to everything, and `pcbl route exceptions` writes
  the joins the editor's DRC will flag and the decision accepts to `layout/POWER-drc-exceptions.md`.
  ⛔ **A DRC hit that is not on that list is a defect.** The node voltages are derived by
  `tools/soft_start.py` from the netlist, never typed.
- After the owner exports a board's netlist from EasyEDA (to `~/Downloads`), prove it:
  `python3 -m tools.tel_check BOARD ~/Downloads/Netlist_BOARD_<date>.tel`. It must print
  "identical", and exits 1 on any pin on the wrong net or any wrong footprint. ⚠️ A proof holds only
  for the netlist it was taken from: after a netlist change, every board it touches is re-exported
  and re-proven. ⛔ **No board is proven against the current netlist.** IO-26 and IO-27 (2026-09-22)
  re-partitioned the design: CTRL is a fourth board, the CTRL ribbon is deleted, the 5 V aux block
  and `J314` are on CTRL, expander #3 is on LOGIC, `STACK` is 2 × 27, `PWR-LOGIC` 1 × 14 and the new
  `CTRL-STACK` 2 × 22. **All four boards need one `tel_check` export before the boards are ordered.**
  ⛔ **A proof dies the
  moment `netlist.py` changes.** Never carry a ✅ forward; state the commit it was taken against.

- `tools.integrity` asks whether the netlist is a circuit at all — every pin of every part lands on a
  net, every inter-board net has real connector contacts. `tools/rules.py` asks whether it obeys the
  safety and pin rules. **Green rules on a netlist that fails integrity mean nothing**: a TVS with one
  leg landed passes every rule.
- ⛔ **Never close a gap on paper only.** A part counts as protection when both its pins are on nets,
  not when a comment says so.
- ⛔ **A through-hole part occupies BOTH faces of its board.** Its pads are copper on both sides and
  its pins stand proud of the far face, so a bottom-face terminal or brick takes the same plan area
  as a top-face one — the two faces are NOT independent. `board_fit` measures ONE strip per board
  edge (`edge_budget`, 228 mm between the M3 corners) and counts an underside through-hole body too
  deep to sit behind the row; `pcbl`'s `tht_both_faces` check forbids a through-hole pad under any
  body on the other face. ✅ **Look at `pcbl place --draw`'s picture after every placement** — a
  number proves parts do not collide on the axis it measured; a picture proves they are where you
  think.
- A height or rating is "confirmed" only if it was read in a manufacturer PDF — say which.
- The generated folder under `build-eprj3/` is a build artefact: never hand-edit it, never commit it.
  **The `.eprj2` lives in ONE place: `~/Documents/EasyEDA-Pro/projects/revv1-module.eprj2`** (owner,
  2026-09-22). The build writes it there — and **refuses to overwrite one the editor has saved**,
  because that is the owner's layout. 📄 `layout/README.md` has the netlist-change procedure that
  keeps placement.
- ⛔ **EasyEDA Pro 3.2.149 opens `.eprj2`, not `.eprj3`.** Open
  `~/Documents/EasyEDA-Pro/projects/revv1-module.eprj2`.
  The editor refuses a netlist export while any part lacks a footprint. The file to open is
  `~/Documents/EasyEDA-Pro/projects/revv1-module.eprj2`, not anything under `build-eprj3/`. 📄 The
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
  protects to that figure (an `MCP23017` pin to its 20 mA I<sub>IK</sub>). A TVS without one fails —
  and the figure itself is held to `DATASHEET_V_CLAMP` (`rules.py`, one `(mpn prefix, volts, page)`
  row per TVS) by `VR-DATASHEET`, the way `v_max` is held to `DATASHEET_V_MAX`: a flattering clamp
  typed against the sheet fails, and a TVS with no row in the table fails.
- **`VR-CLAMP`**, **`VR-POWER`**, **`PULL-DIR`** (a contact to ground needs a pull-up) and
  **`BUS-ORDER`** (a power bus reads the same from both ends and never puts two rails side by side)
  are each proven to fire on a mutation of the real netlist: `tests/test_rules_mutations.py`, and
  `tests/test_rules.py` for `BUS-ORDER`. A new rule is not a rule until a test shows it firing on
  the defect it names.
- **Board-to-board: four interfaces on three junctions — three MATED PAIRS and one CABLE (D27/IO-20,
  IO-27).** POWER ↔ OUTPUTS is the cable, because **no stocked connector spans that gap**:
  **`PWR-OUT`**, **five conductors** in a keyed JST VH loom (`V12` on 16 AWG, **two** `GND` on
  16 AWG, `V5` + `KEY_SENSE` on 22 AWG) on the plain five-circuit `B5P-VH` wafer, every cavity
  loaded. Its two halves are ORDINARY, un-mirrored footprints — `J202` on POWER's top face, `J311`
  hanging under OUTPUTS into the 30.0 mm gap; the loom carries the orientation. The other two
  junctions are rigid, stamped Hong Cheng / BOOMELE halves mating insulator-to-insulator at
  **11.0 mm** (the 2.54 mm strip's 11.04 is the hard stop in both): OUTPUTS ↔ LOGIC carries
  **`PWR-LOGIC`** (1 × 14 — the rails' palindrome `V12 G V5 G V3P3 G KEY_SENSE KEY_SENSE G V3P3 G V5
  G V12`, its centre doubled because the family has no 1 × 13) and **`STACK`** (2 × 27, every signal
  beside a ground); LOGIC ↔ CTRL carries **`CTRL-STACK`** (2 × 22 — the eleven controller-row
  signals, the four 5 V channels' enable and fault lines, and `V12` at each end for the aux buck,
  a ground beside every one). In each pair the lower half stands on the lower board's top face and
  the upper half hangs **under** the upper board, its footprint generated PRE-MIRRORED (`…-UNDER`),
  placed on the bottom layer. A same-numbered dual-row footprint cannot be aligned by any turn —
  STACK's signals would land on ground. **Keying replaces the
  palindrome** for the cable: `BUS-ORDER` still demands that a mated pair read the same from both
  ends, and demands of a cable a positively keyed shell instead. ⚠️ The VH's keying is the wafer's
  **lock ramp**, not a post omission — a symmetric omission polarises nothing — ⬜ confirm on the
  first sample that a reversed housing will not seat. ⛔ **"VH" clones are rated 3 A**: CAX
  `VH-4A-HT` (C5453989) lists identically and is a 2.8× overload at 8.47 A — genuine JST only, the
  Blue Sea failure shape. ⚠️ **The brass M3×30 standoffs (C775781) SET the 30.0 mm POWER → OUTPUTS
  gap** — bonded to GND at the OUTPUTS end only (IO-21), on a copper-free pad at POWER, so a brass
  post never becomes a *third*, unrated return. ⭐ **`PWR-OUT` is the SOLE 12 V return (IO-27
  restating IO-23):** every load is on OUTPUTS and returns to `U201` on POWER, and until the CTRL
  ribbon was deleted its 13 grounds carried ~79 % of the 8.47 A in parallel with the loom. They are
  gone, so the loom carries all of it — **on TWO 16 AWG conductors in the VH's fifth cavity and its
  neighbour**, ~4.24 A each in service, and with ONE crimp open the whole 8.47 A on the survivor and
  its 10 A contact, which is inside the rating. ⛔ Never thin either conductor to one, and never
  write that some other path shares the return. The nylon TP-11 stands beside **both** rigid
  junctions — four at PWR-LOGIC / STACK and four more at CTRL-STACK, one part number and one
  selection window — deliberately short of the 11.04 mm stop and fitted **by measured length
  (10.94–11.04 mm), with no shim**, so the connectors keep setting those gaps. `integrity`
  checks each kind against what is true of it: a pair's halves face each other, mirrored; a cable's
  halves match contact for contact, unmirrored. ⛔ **HV-LINK is gone** — POWER is one board, so no
  84 V crosses an interface. ⛔ **Every pair's pinout is derived from its signal tuple**
  (`_STACK_SIGNALS`, `_CTRL_STACK_SIGNALS`, `_PWRLOGIC_NETS`) and all three have been renumbered:
  regenerate a pinout from the netlist, never hand-patch a document's copy.
- **Harness terminals come in families by job, and the families are the rows** (plan §9.2): **7.62 mm
  Kefa** for pack voltage (`J101` only, alone on POWER's edge) · **5.08 mm Kangnex** for the
  FarDriver leads and nothing else (`J309`, `J404`, and the parked `J310` / `J405` — the controller
  row, on CTRL since IO-26) · **3.50 mm Kefa** for
  the 5 V outputs and nothing else (`J314`, on CTRL's **top** face in line with the controller row
  since IO-26 2a) · **3.81 mm Kangnex** for the
  12 V row on OUTPUTS and the INPUTS row on LOGIC. **Each dangerous group owns its pitch**, because the three dangerous
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

- **Every expander's `RESET` rides the S3's `EN` net (IO-22, 2026-09-21)**, and since IO-26 2a moved
  expander #3 to LOGIC **that net crosses no interface at all** — all three expanders sit on the
  board the S3 is on. Whatever holds the S3 in reset **through `EN`** — the power-up RC, the programmer's
  pulse at `J408`, the supervisor `U406` if it is ever fitted — holds all three expanders with it, and
  they leave reset after the S3 does: no expander can come up driving, and every bit returns to an
  input with the drivers' own pull-downs taking over (D14). ⛔ Before IO-22 the resets were pull-ups
  to `V3P3` and nothing else, and `V3P3` is the last rail to fall at key-off.
  ⛔ **`EN` is an INPUT the S3 cannot drive** (ESP32-S3 datasheet Table 2-10; the netlist's `EN`
  source says so), so **a watchdog or software restart resets NOTHING on this net** — the expanders
  keep driving what they last drove through the reboot, and boot-to-first-write (~0.5 s, unmeasured)
  cannot beat the **shortest** hold, ~300 ms at the LVC with a slow FET (774 ms is the fast-FET
  figure). **The exposure is therefore a hang OR a watchdog / software reboot inside the hold** —
  162 W against the 138 W line for the rest of the decay. ⬜ **Closing the reboot case needs a reset
  the S3 itself drives** (a GPIO — all 32 are spent — or a supervisor that pulls `EN`): an owner
  decision, open. Never write that "any restart sheds the load".
- `tools/soft_start.py` gates on the shed case and prints the un-shed bound beside it as the residual
  risk it is. ⬜ **M17** scopes a deliberate key-off under load.

## Parked work

The CAN dash feed is parked (**D19**). Do not resume it unprompted. Parked is not disproven —
everything in the parked documents stays correct.
