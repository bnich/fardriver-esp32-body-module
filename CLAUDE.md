# CLAUDE.md — FarDriver ESP32 body module

Parent guidance: `../CLAUDE.md` — repo map, conventions, public-repo hygiene, safety rules.

## What this is

Design stage — no firmware, no module hardware built. `docs/plan.md` is the architecture and the
decision log (D1–D24); its header carries the critical path. `docs/bom.md` **owns procurement** of
what the owner buys: the breadboard parts, the parts JLC cannot place (hand-soldered), and the parts
ordered loose with the boards and fitted by the owner. Change a part there first, then the plan
section that line's Notes names. The LCSC part JLC places for each part lives in `tools/netlist.py`.

The custom build is **four stacked boards — HVIN · CONV · DRV · BRAIN** (plan §9.2). `tools/netlist.py`
**is** that design: parts, nets, connectors, board assignment. The DevKitC-1 pin map in plan §3.1.3 is
the **prototype's**; the custom board carries the pin *rules*, not those GPIO numbers.

**This repo is public and holds reader-facing facts only.** The working material lives in the
workspace, unpublished: `../docs/esp32-board-design-record.md` (decisions BD-1…),
`../docs/esp32-needed-from-owner.md`, `../docs/plans/2026-09-15-esp32-board-set.md`. Do not move it
back, and do not write working notes into `docs/` here.

**Licence: MIT for everything in this repo**, documentation and hardware included — a deliberate
owner decision (2026-09-18), and an exception to the workspace's CC BY-SA default.

## The `tools/` workflow

Stdlib Python, no virtualenv. The exceptions are `cryptography`, needed for the `.eprj2` output
(`tools/eprj2.py`), and `~/tools/lcsc-search` for library footprints. Without either, the build
still runs and says what it could not do. Run from the repo root, in this order, after any change
to the netlist or the model:

```bash
python3 -m tools.integrity     # structural gate — must print "0 integrity problem(s)"
python3 -m pytest              # rules and unit tests (hermetic: no library fetch)
python3 tools/build_project.py # the project, footprints bound; names every item still without one
python3 -m tools.jlc_bom       # the JLC BOM, what is ordered loose, what the owner hand-solders
```

`tools/README.md` has the full order (`board_fit`, `gpio_budget`, `soft_start`) and one line per tool.

- ⛔ **After changing any LCSC code, run `python3 -m tools.lcsc_fixture`.** It refreshes
  `tests/fixtures/lcsc.json` — what LCSC says each ordered code is (part number, maker, package,
  symbol pins, footprint title). The tests hold the design to it offline and hold it to the live
  library where reachable, so a code pointing at the wrong part, or a stale fixture, fails.
- **The build writes `build-eprj3/layout-rules.txt`:** the HV net class (1.25 mm, IPC-2221B B2) over
  HVIN's and CONV's pack-voltage nets. The generated PCBs carry only the board-wide 0.2 mm, so the
  owner sets the class up in the editor before routing. Never try to emit it into the project.
- After the owner exports a board's netlist from EasyEDA (to `~/Downloads`), prove it:
  `python3 -m tools.tel_check BOARD ~/Downloads/Netlist_BOARD_<date>.tel`. It must print
  "identical", and exits 1 on any pin on the wrong net or any wrong footprint. ⚠️ A proof holds only
  for the netlist it was taken from: after a netlist change, every board it touches is re-exported
  and re-proven. No board of the current netlist has been proven yet.

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
- **`LISTEN`** (firmware reaches a brake/kill net only through ≥ 100 kΩ), **`VR-CLAMP`**,
  **`VR-POWER`**, **`PULL-DIR`** (a contact to ground needs a pull-up) and **`BUS-ORDER`** (a power
  bus reads the same from both ends and never puts two rails side by side) are each proven to fire
  on a mutation of the real netlist: `tests/test_rules_mutations.py`, and
  `tests/test_rules.py` for `BUS-ORDER`. A new rule is not a rule until a test shows it firing on
  the defect it names.
- **Board-to-board: one crossing per interface, between neighbouring boards.** The lower half sits
  on top of the lower board, the upper half **under** the upper board, and its footprint is
  generated PRE-MIRRORED (`…-UNDER`), placed on the bottom layer. A same-numbered dual-row footprint
  cannot be aligned by any turn — STACK's signals would land on ground. `integrity` checks each
  interface is two identical halves on neighbours, facing each other.
- **Harness terminals come in families by job:** 7.62 mm Kefa for pack voltage (`J101` only),
  5.08 mm Kangnex for the levers and the brake/kill (`J306`, `J309`), 3.81 mm Kangnex for the rest.
  A smaller plug seats offset in a larger header of its pitch, so **every safety-relevant terminal
  (84 V, levers, `BL` / `ACC+`, `RUN`, boost) keeps a (pitch, positions) size nothing else in its
  family shares** (`tests/test_interconnect.py`). A parked terminal keeps its footprint, not its
  header.

## ⚠️ The traps that matter most

- **The 84 V pack is above most of the market.** Check the voltage line on every part. Converters need
  **160 V** input; TVS is `SMCJ90A`, on B+ only — ⛔ never on the key tap `KSW`, where a failed-short
  TVS cuts the FarDriver KEY; 160 V DC is the do-not-exceed including transients.
- **Pack voltage enters on `J101` alone**, 7.62 mm pitch with an empty position around B+ and around
  `KSW`; HV-LINK carries it at 5.08 mm effective (a 2.54 mm header, alternate pins skipped).
- **Size input protection at the 60.0 V LVC, not full charge** — converters are constant-power loads.
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
  only. The clean GPIO pool on the custom board is **30**.
- **ESP32-S3 `R8`/`R16V` are rated to 65 °C only.** Use `-N8` (85 °C) or `-H4` (105 °C).
- **No wire leaves the box on strapping pins 0/3/45/46**; analog only on GPIO1–10 (ADC2 dies with WiFi).
- **TVS parts follow the line's idle voltage:** the 5 V `SMS05T1G` goes only on 3.3 V-class lines;
  the brake-lever nodes (~11.4 V), `BL` / `ACC+` and the boost output take the 15 V `SMS15T1G`; each
  12 V lamp or load output takes a single-line `SMF18A`, and the 12 V rail an `SMBJ18A` — never a
  15 V part there (the TDK's over-voltage window is 15.0–17.4 V). A 5 V array on a 12 V line is a
  short.
- **No GPIO that comes out of reset pulled up drives an active-high enable** (`GPIO-RESET-PULL`):
  GPIO39 would light the tail at boot.
- ⛔ **Never enable CAN on this controller** — on non-CAN units the transceiver lands on A11/A12, the
  Hi/Low speed sense lines.

## Safety boundary — do not erode it

**The brake cutoff and brake light are hardware and must stay hardware.** The module only listens. All
lights OFF at key-on, every gate biases OFF, so a hung module drives no lamps. Any derivative should
keep this.

- State the brake-lamp claim precisely: **no firmware state can affect it, but it is fed from the
  module's 12 V rail** — an unpowered module means a dark brake lamp. The motor cut (`BL`) needs
  nothing from the module. Never write "works with the module unpowered" about the lamp.
- The stop lamp is `U302` OUT4, a `TPS4H160B` channel whose input only the lever hardware (Q1)
  drives: current limit and diagnosis, no firmware in the path. `LISTEN` enforces it.
- **No raw 12 V leaves the box.** Horn, fan and buzzer ride `AUX12` (`U301` OUT1, current-limited,
  on while the logic runs) and are switched on their return.
- **The module never sources or switches the FarDriver KEY (D10).** The key switch feeds KEY directly
  (D24); there is no start latch, and the start button is a spare sensed input.

## Parked work

The CAN dash feed is parked (**D19**). Do not resume it unprompted. Parked is not disproven —
everything in the parked documents stays correct.
