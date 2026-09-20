# Design-time tooling

Checks the three-board set and generates its EasyEDA Pro project from a checked-in netlist.
**Stdlib only**, no virtualenv, with two exceptions. Without either, everything else still runs and
says what it could not do:

- the `.eprj2` output needs the `cryptography` package;
- library footprints come through `~/tools/lcsc-search`, which caches every answer, so builds run
  offline after one online build. Without it the build binds no library footprint and names every
  item left without one.

Run everything from the repo root.

📄 The design these tools describe: [`../docs/plan.md` §9.2](../docs/plan.md).

## The order to run things in

After any change to the netlist or the model:

```bash
python3 -m tools.integrity        # is the netlist a circuit at all?  must print "0 integrity problem(s)"
python3 -m pytest                 # rules and unit tests              hermetic: no library fetch
python3 -m tools.rules            # every rule, and the warnings      exit 1 on a violation
python3 -m tools.board_fit        # area, height and plug-room budget exit 1 on FAIL, 2 over the estimate
python3 -m tools.gpio_budget      # pin budget                        exit 1 on FAIL
python3 tools/soft_start.py       # D13 soft start                    exit 1 on FAIL
python3 tools/build_project.py    # the EasyEDA project, and build-eprj3/layout-rules.txt
python3 -m tools.jlc_bom          # JLC's BOM, the loose parts, the hand-soldered parts
```

- ⛔ **After changing any LCSC code:** `python3 -m tools.lcsc_fixture`, which refreshes
  `tests/fixtures/lcsc.json` from the library. The tests hold the design to that file on every run,
  and the file to the live library wherever it is reachable, so a stale fixture fails.
- **After the owner exports a board's netlist from EasyEDA:** `python3 -m tools.tel_check BOARD
  FILE.tel` (below).

Green rules on a netlist that fails integrity mean nothing: a TVS with one leg landed passes every rule.

## What each file is

| File | What it owns |
|---|---|
| `model.py` | The shape of a design: `Part`, `Net`, `Connector`, `Design` |
| `netlist.py` | **The design** — every part, net and connector, per board, and every LCSC code. The one source every tool below reads |
| `integrity.py` | Structural gate: every pin lands, every inter-board net has real contacts, every interface is two identical halves on neighbouring boards, facing each other |
| `rules.py` | Safety and pin rules, each named for the decision it protects (`python3 -m tools.rules` prints them) |
| `board_params.py` | The cavity, the enclosure allowances and the stack parameters — and the **derived** stack height |
| `board_fit.py` | Area, height and plug-room budget (`board-fit.py` is a two-line shim for it) |
| `gpio_budget.py` | ESP32-S3-WROOM-1 pin facts, and the design's demand on the pool |
| `soft_start.py` | The D13 main-switch gate network, simulated |
| `layout_rules.py` | The HV net class and the land keep-outs the generated PCBs cannot carry |
| `build_project.py` | Generates the EasyEDA Pro project for the three boards. Gated on integrity, rules and a read-back of its own output |
| `eprj2.py` | Reads and writes EasyEDA Pro's native `.eprj2`, and wraps the generated folder as one: the file the editor opens |
| `eprj3/` | The `.eprj3` emitter: `records.py` (record grammar), `units.py` (mm ↔ file units), `project.py` (the folder and its index), `pcb.py` (outline, 4-layer stackup, holes, rules), `symbols.py` (schematic symbols), `footprints.py` (footprint documents), `v2footprint.py` (EasyEDA library footprints, V2 → V3), `placement.py` (sheet layout), `schematic.py` (sheets, devices and nets), `reader.py` (reads a sheet back and derives its nets) |
| `padmap.py` | Which footprint pad each netlist pin lands on, typed from the datasheets |
| `footprint_lib.py` | Library footprints through `~/tools/lcsc-search`, fitted to our pins; the generated inter-board header patterns |
| `drawn_footprints.py` | Land patterns drawn from the makers' drawings: the parts with no library device, and the Tag-Connect service pads |
| `lcsc_fixture.py` | Refreshes `tests/fixtures/lcsc.json`: what LCSC says each ordered code is |
| `jlc_bom.py` | The BOM JLC's assembly service reads, one line per LCSC part, plus what is ordered loose and what is hand-soldered |
| `tel_check.py` | Proves EasyEDA's netlist export (`.tel`) against the netlist, pin by pin and footprint by footprint |
| `gauge.py` | Generates the one-sheet gauge project that proved EasyEDA Pro joins the generated nets |

### `board_params.py` — parameters typed, geometry derived

Holds the M18 cavity (`CAVITY_MEASURED = False` until it is measured); the wall / floor / lid
**allowances** (`ENCLOSURE_DECIDED = False` until the enclosure's model sets them — the box is
all-metal, its thicknesses are not yet known); PCB thickness; the mechanical clearance; the 1.5 mm a
trimmed through-hole lead stands out of its board (IPC); the 0.5 mm insulating liner on the metal
floor under POWER, whose underside carries 84 V pins; the floor seat — `U201` bolts its baseplate
to the box floor through a 0.5 mm thermal pad, which is the only heatsink (BD-27), and the liner is
cut away there; and the wire-bend room behind a harness plug. `STACK_ORDER` is bottom to top, three
boards. ⛔ BD-9's alloy plate is withdrawn: there is none in the stack, and nothing here models one.

⛔ No layer ceiling is typed anywhere. `layer_gaps(design)` and `stack_height(design)` work the stack
out from the netlist's own heights:

- a gap is the larger of *tallest top-side body below + clearance + solder tails above* and
  *deepest bottom-side part above + clearance*. The FLOOR gap instead takes the larger of *pad +
  the floor seat's height* and *liner + the deepest other underside item + clearance*, and fails
  the design when anything beside the seat hangs deeper than it, or when the seat is not on the
  bottom board's underside at all;
- solder tails are per part: a through-hole part whose pins are too short or stiff to trim states
  its drawing's maximum (`lead_mm`) and is charged that, less the board; every other lead is
  trimmed to 1.5 mm;
- an inter-board connector pair mates at the sum of its two halves' `height_mm`. While either
  height is unconfirmed the pair can only widen the gap; once both are confirmed the pair **is**
  the gap, and a part that needs more room fails the design;
- a height that is `NaN`, negative or missing is a **failure**, never a short part;
- every unconfirmed height is listed, and the ones that set a gap are named (`load_bearing`);
- a bottom-side part and a tall part beneath it share a gap only by standing side by side, so each
  one produces a **keep-out** note naming what may not sit under it.

`stack_problems(design)` returns the failures in the shape a rule returns.

### `board_fit.py`

```bash
python3 -m tools.board_fit
```

Prints, per board and side, the raw body area and density (**FAIL above 75 %** of the usable
side) and a naive shelf-pack length against the board's length (**FAIL when it does not fit** —
the tool then has not shown the board can be built; a placed outline overrules it, an argument
does not). Then the derived stack, gap by gap, against the height available; every unconfirmed
height; and each board's harness headers end to end against the envelope's edges, with the room a
mated plug and the bend of its wire need to the wall. One verdict: exit 1 when a budget fails, 2 when
the stack is over the estimated envelope. A body with no footprint that is a connector, or 2 mm tall
or more, fails the run: the budget cannot see it. The first line says PROVISIONAL for as long as M18
is unmeasured or the enclosure unmodelled.

### `gpio_budget.py`

```bash
python3 -m tools.gpio_budget
```

Silicon and module facts live here and nowhere else: GPIO22–25 do not exist, 26–32 are the flash,
⛔ **33/34 have no pad on the WROOM-1**, 0/3/45/46 are strapping pins — a pool of **32**, GPIO19/20
included: the board has no USB port — GPIO43 prints the ROM boot log and is never a driver, and
analog is ADC1 (GPIO1–10) only.

Demand is **derived**: `demand(design)` reads every `Net.gpio` tag and follows the copper through
series parts (stopping at supplies) to find what the net drives, whether it is analog, and where it
leaves. `report(design)` fires on a GPIO outside the pool, a GPIO given to two nets, anything driven
from GPIO43, an analog net off ADC1, and an ADC net that reaches no GPIO. A strapping pin may carry
its bias parts and the internal service pads only.

### `soft_start.py`

```bash
python3 tools/soft_start.py
```

A fixed-step simulation of Q101's gate network (R110, R101A+B, C105, C107, D102) charging 440 µF
with the converters' load, at 84 V and 60 V across the FET's threshold spread. **The load is the
LVC tap current `power_budget` derives** (`tap_current_a()`), not a typed figure: Q101 sits upstream
of both converters, so a new aux output moves the ramp and the SOA verdict with nothing retyped.
Key-on, the ramp and the plug-in use that whole tap; **key-off uses the shed tap**
(`shed_tap_current_a()`) — see below. The network is
**read off the netlist** by following the copper round Q101 (`circuit_from(design)`), so a changed
resistor is the one simulated and a pull-down path that reaches no ground is reported as a switch
that never turns on; the run prints where the netlist differs from the specified values. Reports turn-on
delay, ramp, peak FET power and energy, and compares the peak — as an equal-energy pulse — with
Q101's SOA (DS99913D Fig. 14, T_C 70 °C; the `IXTA26P20P` and `IXTP26P20P` share the die and the
sheet) × 0.72. Also: the V_GS excursion when the pack is plugged in with the key off (must stay under
the 2.0 V minimum threshold), and `solve_r_pd(target_ramp_s)` for choosing the pull-down. Prints
PASS or FAIL.

**Key-off is a gated criterion, not a printed remark** (`key_off()`, in `assess()`): Q101 holds on
for ~0.8 s after the key opens while C107 bleeds through R110, and what it dissipates during the
decay is held to the **derated DC SOA line**. ⚠️ The gated power figure is an upper **bound** —
`I_LOAD_SHED × V_pack`, the **shed** LVC tap current across the whole pack. ⚠️ **FIRMWARE
CONTRACT (IO-16):** the firmware releases every aux output when `KEY_SENSE` goes inactive, inside
that hold, so the decay carries the base load plus the 5 V buck's standing draw — which its
`EN`-to-`PVIN` tie makes unsheddable — and **this part's SOA margin depends on that firmware
behaviour**. The un-shed case is printed beside the gate as the **residual risk** it is: hold the
outputs on through the decay and the bound is over the line again. A reset is not that exposure —
every driver enable comes out of reset pulled down, so a restart sheds the load by itself; a hang
that holds the outputs on without tripping the watchdog is what is left. `key_off_decay()`
integrates the decay beside the bound, which lands a little under it and puts the equal-energy pulse
**past the SOA table's 100 ms row**, so the DC line is the right row and not a stand-in for a
missing one. The `KeyOff` docstring says what a further refinement would take: a converter
under-voltage shutdown threshold, which TDK does not publish for the CN-B110.

### `layout_rules.py` — the HV net class and the land keep-outs

```bash
python3 -m tools.layout_rules
```

The generated PCBs carry one board-wide clearance, 0.2 mm: the record form of an editor-made net
class is not known from any file here, and a guessed record can corrupt the project. Copper at pack
voltage needs **1.25 mm** (IPC-2221B B2, 151–300 V: the 160 V do-not-exceed). This lists, per board,
every net that can sit at pack voltage — typed 84 V, or joined to one through copper, a switch, a
choke or a diode — as the net class **HV**. `build_project.py` writes the same text to
`build-eprj3/layout-rules.txt`. ⚠️ **Set the class up in the editor before routing POWER:**
PCB → Design → Net Class, a class `HV` holding those nets; Design Rules → Safe Spacing, a 1.25 mm
rule applied to `HV`.

It also lists each drawn land's keep-out: `J408`, the Tag-Connect TC2030-NL service pads, wants no
track or via between its pad centres and nothing within 0.51 mm of a pad (Tag-Connect's drawing,
notes 1–2). Draw it as a keep-out region before routing LOGIC.

### `jlc_bom.py`

```bash
python3 -m tools.jlc_bom                  # the BOM, then the loose, hand-soldered and unchosen lists
python3 -m tools.jlc_bom --out bom.csv    # the CSV JLC's order takes
```

One line per LCSC part, with every designator that uses it. Left off the CSV: DNP parts, parts marked
`assembly="hand"` (the owner buys and solders them) and parts marked `assembly="loose"` (ordered
from LCSC with the boards and fitted by the owner). The printout then lists what is ordered loose —
every fitted harness header's plug, and the parts that must lie flat or clip in — with each LCSC code
and count, the hand-soldered parts with the reason LCSC cannot supply them, and the connectors with no
part chosen yet.

### `lcsc_fixture.py` — what LCSC says each code is

```bash
python3 -m tools.lcsc_fixture        # refresh tests/fixtures/lcsc.json
```

For every LCSC code the design orders — each part's, each harness terminal's header and plug — the
fixture records the part number, maker and package LCSC gives it, the library symbol's pin numbers
and names, and the library footprint's title. `tests/test_lcsc_records.py` holds the design to it
offline on every run, so a changed code that points at a different part (a 65 °C ESP32, the wrong
BSS127) fails although the rules, which read the netlist's MPN, pass. Where the library is
reachable, the same test holds the fixture to the live library, so a stale fixture fails too.
⛔ **Refresh it after changing any LCSC code.**

### `tel_check.py` — proving the editor's netlist

```bash
python3 -m tools.tel_check BOARD ~/Downloads/Netlist_BOARD_<date>.tel
```

The export is EasyEDA's own reading of the generated project, so every pin it puts on a net is a pin
the layout will route. `tel_check` compares it with the netlist for that board, net by net and pin by
pin, and each part's footprint with the one the build binds. The fuse is not converted to PCB (it
sits in its clips), so it is absent from the export, as it should be. It prints "identical to the
generator's netlist" and exits 0 when they agree; it exits 1 on any difference. ⚠️ **A proof holds
only for the netlist it was taken from:** after any netlist change, re-export and re-prove every board
the change touches.

### `eprj3/records.py` — the record grammar

```
file   := record ( "|" LF record )*        no trailing separator, no trailing newline
record := header_json "||" payload_json    payload may be empty
```

`serialize_record(header, payload)` returns one record with no separator; `join_records(records)`
is the only place the separator exists. The editor drops a record it cannot parse **without an
error**, so a header with no `type`, a `||` inside a header, and NaN/Infinity are all refused here.

## Generating the EasyEDA Pro project

```bash
python3 tools/gauge.py             # gauge-revv1/ + .eprj2 + .zip + GAUGE-INSTRUCTIONS.md   the naming test (passed)
python3 tools/build_project.py     # revv1-module/ + revv1-module.eprj2 + .zip + layout-rules.txt   exit 1 if any gate fails
```

Both write to `build-eprj3/` by default (`--out DIR` to change it). That folder is gitignored: the
project is a build artefact. Never hand-edit it; change the netlist and regenerate.

⭐ **Open `revv1-module.eprj2` in EasyEDA Pro**, by its path. The editor lists a project only after
it has been opened once. EasyEDA Pro 3.2.149 does not open the `.eprj3` folder or the zip; its
native project is `.eprj2`. `tools/eprj2.py` wraps the folder as one:

- The `.eprj2` is an SQLite file whose design is one snapshot made of the same records.
- It copies the schema, db version and account uuid from a **template**: any `.eprj2` the installed
  editor saved. By default the tool finds one in `~/Documents/EasyEDA-Pro/`; pass `--template` or
  set `EASYEDA_EPRJ2_TEMPLATE` to choose. No file of the editor's is kept in this repo.
- It is deterministic. The same design gives the same file, and a changed design gets a new project
  id, so the editor never mistakes it for an older build.
- `python3 tools/eprj2.py info|decode|roundtrip FILE.eprj2` reads any `.eprj2`.

`build_project.py` runs three gates, and writes nothing unless all three are empty: `integrity.check`,
`rules.check_all`, and a **read-back** — `eprj3/reader.py` parses every sheet about to be written,
derives its nets from the bytes, and compares them pin by pin with the netlist. A failure exits 1,
naming every problem. Otherwise it writes one board per
`board_params.STACK_ORDER` layer. Each board gets:

- a schematic sheet with every part and connector of that board;
- a PCB with the outline, the 4-layer stackup, mounting holes and rules from `eprj3/pcb.py`.

It also writes a zip of the folder, the `.eprj2`, and `layout-rules.txt`. Two runs are
byte-identical.

### How a net is drawn

Parts are not routed. Every connected pin gets a **stub**: one wire, two grid steps long, starting
exactly on the pin's anchor. The stub is then named in up to two ways, set by `NAMING` in
`eprj3/schematic.py`:

| `NAMING` | The stub carries |
|---|---|
| `"both"` (default) | a net flag at its end **and** the net name on the wire |
| `"flag"` | a net flag only; the wire's name is empty |
| `"wire"` | the net name on the wire only; no flag |

`GND` gets a ground glyph. `V12`, `V5`, `V3P3` and `HV_BPLUS` get a rail bar. Every other net gets
a label tag. Pins in a part's `nc`, and connector cavities with no net, get nothing. Every symbol's
pins face left or right, so components sit at rotation 0 and flags at 0 or 180. The spec cannot
confirm the handedness of 90/270, and those two rotations do not depend on it.

A net name that EasyEDA Pro would reject is **refused, never rewritten**. Allowed characters are
uppercase letters, digits and `_ - + ~ . / #`.

### Verified

The tests re-derive every board's nets from the emitted bytes. They follow wire endpoints, then
flag names, then wire names, and compare the result pin by pin with `netlist.current()`. They do
this in all three `NAMING` modes. The same reader reproduces the official example's nets.

EasyEDA Pro itself joins the nets. The gauge was opened in EasyEDA Pro 3.2.149 and its exported
netlist put each of the four pairs on one net under its own name: drawn wire, wire name alone, net
flag alone, and flag with wire name, which is what the build emits. `NAMING = "both"` stays.

### What the owner does in EasyEDA Pro

- **Every placed item carries a footprint.** The build summary names any that does not, and the
  editor refuses a netlist export while one is missing (its DRC calls a missing footprint fatal).
- **Place each `…-UNDER` footprint on the bottom layer.** It is the upper half of an inter-board
  pair, which hangs under its board, and it is generated mirrored: after the flip, plus at most a
  180° turn, every pad sits over its mate's. A same-numbered dual-row footprint cannot be aligned by
  any turn — STACK's signals would land on its ground row.
- **Set up the HV net class before routing POWER, and J408's keep-out before routing LOGIC**
  (`layout_rules.py`, above).
- ⬜ **Check the paste layer has no aperture over `J408`'s six pads** (Gerber viewer, top paste). The
  pads carry a paste expansion past their own radius, which should close the aperture; this has not
  been seen in the editor yet. A solder dome under a spring pin is a bad contact.
- **Export each board's netlist and prove it** with `tel_check.py` (above).
- Parts JLC must not fit — DNP, hand-soldered and loose — carry `Add into BOM: no`, because
  EasyEDA's BOM ignores its own DNP flag. The fuse carries `Convert to PCB: no`: its clips are the
  PCB part.
- Each symbol pin's `Pin Number` is the netlist's own pin id (`1`, `K`, `VS`, `+Vin`), not a pad
  number. Pad numbers are in each part's `source`.
- There is no sheet frame. Its title-block records are not specified, so none is generated. All
  content sits in the sheet-body quadrant.
- Text widths used for spacing are generous estimates, because the default font size is not stated
  anywhere. If the real font is wider still, labels can overlap. Connectivity is unaffected, because
  text carries none.

### Parts, devices and LCSC numbers

- Each **real part** is one EasyEDA device: one value in one package with one LCSC number. Devices
  share symbols. Two 10k 0805 resistors share a device; a 10k and a 100k do not.
- A device with an LCSC number carries `Supplier: LCSC` and `Supplier Part`, which is what a JLC BOM
  reads.
- The numbers come from `netlist.py`.
  - `current()` applies `_FAB_BY_MPN`, `_LOOSE_BY_MPN`, `_HAND_BY_MPN` and `_FAB_CONN`, and refuses
    an entry no part uses. Each harness terminal takes its header and plug from `_TERMINALS`, by
    pitch and size.
  - Each part carries an `assembly` class: `jlc` (JLC places it), `hand` (the owner buys and
    solders it, because LCSC has nothing that meets its constraints — the reason is in its
    `source`) or `loose` (ordered from LCSC with the boards and fitted by the owner: a part that
    must lie flat, or the fuse and its clips).

`eprj3/v2footprint.py` converts EasyEDA library footprints, which the library serves only as V2, into
V3 records. It reproduces the editor's own conversion of 19 footprints record for record. The oracle
test needs those example files locally and skips without them.

**Footprints are bound to devices.** EasyEDA joins a symbol pin to a footprint pad by number. Our
symbols number pins by the netlist's names (`A`/`K`, `G`/`D`/`S`, `VS`), so each footprint's pads
are renamed to the pins they carry:

- `padmap.py` holds the pad → pin maps, typed from each part's datasheet. `test_padmap.py`
  checks every map against EasyEDA's library symbol where this machine can reach the library, and
  it fails on a swapped FET or a reversed diode.
- `footprint_lib.py` fetches the library footprints through `~/tools/lcsc-search`. `fit()` renames
  each pad to the pin it carries, leaves a pad mapped to `None` unconnected on purpose (a contact the
  design does not use), and refuses a pad no map accounts for. The inter-board connectors get a generated
  2.54 mm header pattern, because every family on the options list uses that grid; an upper half's
  pattern is mirrored (`-UNDER`).
- `drawn_footprints.py` draws a land pattern from the maker's drawing for each part with no library
  device — the converters, the chokes, the lying capacitors, the fuse clips, the net-tie. A footprint
  is the **top view, Y up**; a drawing of the pin face or a bottom view is mirrored into it, and
  `test_drawn_footprints.py` checks the mirror.
- The build summary names every placed item still without a footprint. `--no-footprints` binds
  none, and the test suite binds only generated footprints.
- No library footprint or symbol is kept in this repository. `tests/fixtures/lcsc.json` holds only
  the facts the tests check: part number, maker, package, pin names and footprint title.

## Rules

- ⛔ **Never hand-edit a generated project.** It is a build artefact. Change the netlist and
  regenerate, or the next build silently reverts your edit.
- ⛔ **Never store native units outside `eprj3/units.py`.** Geometry is millimetres everywhere;
  conversion happens once, at emit.
- ⛔ **Never type a fact about the design into a tool.** Parts, heights, footprints and GPIOs are
  read from `netlist.py`; a second copy drifts.
- **A height is confirmed only if it was read off the manufacturer's drawing** — and `source` says
  which. Everything else is reported as unconfirmed, every run.
- **Every constant states what it protects**, so it cannot be silently re-broken.
