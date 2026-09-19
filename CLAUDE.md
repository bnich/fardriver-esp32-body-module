# CLAUDE.md — FarDriver ESP32 body module

Parent guidance: `../CLAUDE.md` — repo map, conventions, public-repo hygiene, safety rules.

## What this is

Design stage — no firmware, no module hardware built. `docs/plan.md` is the architecture and the
decision log (D1–D24); its header carries the critical path. `docs/bom.md` **owns procurement** of
what the owner buys: the breadboard parts, and the parts JLC cannot place, which are hand-soldered.
Change a part there first, then the plan section that line's Notes names. The LCSC part JLC places
for each part lives in `tools/netlist.py`.

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
python3 -m tools.jlc_bom       # the JLC BOM, and what the owner hand-solders
```

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
- **LCSC parts live in `netlist.py` only**: `_R_LCSC`, `_C_LCSC`, `_FAB_BY_MPN`, `_FAB_CONN`. JLC
  Basic first; the part need not match what was bought. Choose with `~/tools/lcsc-search`, and check
  each candidate against the constraints in the part's `source`, never against the keyword.
- ⛔ **A pad map is typed from the datasheet and checked against the library symbol**
  (`tools/padmap.py`, `tests/test_padmap.py`). Never infer one from a footprint's geometry. A
  wrong map wires a FET backwards on a board that passes every other check.
- **Resistors are rated parts.** A resistor's `v_max` is its chosen part's WORKING voltage, never
  the overload figure: 0603 is 75 V, 0805 150 V, 1206 200 V. `VR-UNDER` checks it against the node.

## ⚠️ The traps that matter most

- **The 84 V pack is above most of the market.** Check the voltage line on every part. Converters need
  **160 V** input; TVS is `SMCJ90A`; 160 V DC is the do-not-exceed including transients.
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
- **TVS arrays follow the line's idle voltage:** the 5 V `SMS05T1G` goes only on 3.3 V-class lines;
  12 V lines and the brake-lever nodes (~11.4 V) take `SMS15T1G`. A 5 V array on a 12 V line is a
  short.
- ⛔ **Never enable CAN on this controller** — on non-CAN units the transceiver lands on A11/A12, the
  Hi/Low speed sense lines.

## Safety boundary — do not erode it

**The brake cutoff and brake light are hardware and must stay hardware.** The module only listens. All
lights OFF at key-on, every gate biases OFF, so a hung module drives no lamps. Any derivative should
keep this.

- State the brake-lamp claim precisely: **no firmware state can affect it, but it is fed from the
  module's 12 V rail** — an unpowered module means a dark brake lamp. The motor cut (`BL`) needs
  nothing from the module. Never write "works with the module unpowered" about the lamp.
- **The module never sources or switches the FarDriver KEY (D10).** The key switch feeds KEY directly
  (D24); there is no start latch, and the start button is a spare sensed input.

## Parked work

The CAN dash feed is parked (**D19**). Do not resume it unprompted. Parked is not disproven —
everything in the parked documents stays correct.
