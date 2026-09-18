# Design-time tooling

Checks the four-board set and generates its EasyEDA Pro project from a checked-in netlist.
**Stdlib only**, no virtualenv, with one exception: the `.eprj2` output needs the `cryptography`
package. Without it, everything else still runs and the build says the `.eprj2` was not written.
Run everything from the repo root.

📄 The design these tools describe: [`../docs/plan.md` §9.2](../docs/plan.md).

## The order to run things in

```bash
python3 -m tools.integrity        # is the netlist a circuit at all?  must print "0 integrity problem(s)"
python3 -m pytest                 # rules and unit tests
python3 -m tools.board_fit        # area + height budget            exit 1 on FAIL
python3 -m tools.gpio_budget      # pin budget                      exit 1 on FAIL
python3 tools/soft_start.py       # D13 soft start                  exit 1 on FAIL
```

Green rules on a netlist that fails integrity mean nothing: a TVS with one leg landed passes every rule.

## What each file is

| File | What it owns |
|---|---|
| `model.py` | The shape of a design: `Part`, `Net`, `Connector`, `Design` |
| `netlist.py` | **The design** — every part, net and connector, per board. The one source every tool below reads |
| `integrity.py` | Structural gate: every pin lands, every inter-board net has real contacts |
| `rules.py` | Safety and pin rules, each named for the decision it protects |
| `board_params.py` | The cavity, the enclosure allowances and the stack parameters — and the **derived** stack height |
| `board_fit.py` | Area and height budget (`board-fit.py` is a two-line shim for it) |
| `gpio_budget.py` | ESP32-S3-WROOM-1 pin facts, and the design's demand on the pool |
| `soft_start.py` | The D13 main-switch gate network, simulated |
| `eprj3/` | The `.eprj3` emitter: `records.py` (record grammar), `units.py` (mm ↔ file units), `pcb.py`, `project.py`, `symbols.py` (schematic symbols), `footprints.py` (footprint documents), `v2footprint.py` (EasyEDA library footprints, V2 → V3), `placement.py` (sheet layout), `schematic.py` (sheets, devices and nets) |
| `build_project.py` | Generates the EasyEDA Pro project for the four boards. Gated on integrity, rules and a read-back of its own output |
| `eprj2.py` | Reads and writes EasyEDA Pro's native `.eprj2`, and wraps the generated folder as one: the file the editor opens |
| `padmap.py` | Which footprint pad each netlist pin lands on, typed from the datasheets |
| `footprint_lib.py` | Library footprints through `~/tools/lcsc-search`, fitted to our pins; generated patterns |
| `jlc_bom.py` | The BOM JLC's assembly service reads, one line per LCSC part, plus the list of parts you solder by hand |
| `gauge.py` | Generates the one-sheet gauge project that proved EasyEDA Pro joins the generated nets |

### `board_params.py` — parameters typed, geometry derived

Holds the M18 cavity (`CAVITY_MEASURED = False` until it is measured), the wall / floor / lid
**allowances** (`ENCLOSURE_DECIDED = False` — no enclosure material is assumed), PCB thickness, the
mechanical clearance, the solder-tail allowance and the BD-9 plate. `STACK_ORDER` is bottom to top.

⛔ No layer ceiling is typed anywhere. `layer_gaps(design)` and `stack_height(design)` work the stack
out from the netlist's own heights:

- a gap is the larger of *tallest top-side body below + clearance + solder tails above* and
  *deepest bottom-side part above + clearance*, with the plate stacked in where there is one;
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
does not). Then the derived stack, gap by gap, against the height available, every unconfirmed
height, and one verdict. A body with no footprint that is a connector, or 2 mm tall or more, fails
the run: the budget cannot see it. The first line says PROVISIONAL for as long as M18 is unmeasured
or the enclosure unchosen.

### `gpio_budget.py`

```bash
python3 -m tools.gpio_budget
```

Silicon and module facts live here and nowhere else: GPIO22–25 do not exist, 26–32 are the flash,
⛔ **33/34 have no pad on the WROOM-1**, 19/20 are USB, 0/3/45/46 are strapping pins — a pool of
**30** — GPIO43 prints the ROM boot log and is never a driver, and analog is ADC1 (GPIO1–10) only.

Demand is **derived**: `demand(design)` reads every `Net.gpio` tag and follows the copper through
series parts (stopping at supplies) to find what the net drives, whether it is analog, and where it
leaves. `report(design)` fires on a GPIO outside the pool, a GPIO given to two nets, anything driven
from GPIO43, an analog net off ADC1, and an ADC net that reaches no GPIO. USB pins may go to the USB
connector only; a strapping pin may carry its bias parts and the internal service header only.

### `soft_start.py`

```bash
python3 tools/soft_start.py
```

A fixed-step simulation of Q101's gate network (R110, R101A+B, C105, C107, D102) charging 440 µF
with the converters' load, at 84 V and 60 V across the FET's threshold spread. The network is
**read off the netlist** by following the copper round Q101 (`circuit_from(design)`), so a changed
resistor is the one simulated and a pull-down path that reaches no ground is reported as a switch
that never turns on; the run prints where the netlist differs from the specified values. Reports turn-on
delay, ramp, peak FET power and energy, and compares the peak — as an equal-energy pulse — with the
`IXTP26P20P` SOA (DS99913D Fig. 14, T_C 70 °C) × 0.72. Also: the V_GS excursion when the pack is
plugged in with the key off (must stay under the 2.0 V minimum threshold), the key-off hold time,
and `solve_r_pd(target_ramp_s)` for choosing the pull-down. Prints PASS or FAIL.

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
python3 tools/build_project.py     # revv1-module/ + revv1-module.eprj2 + .zip             exit 1 if any gate fails
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
- a PCB with the outline, mounting holes and rules from `eprj3/pcb.py`.

It also writes a zip of the folder and the `.eprj2`. Two runs are byte-identical.

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

⚠️ **EasyEDA Pro 3.2.149 does not open `.eprj3`.** It opens its own `.eprj2`, an SQLite file whose
design is one snapshot made of the same records, so the folder has to be wrapped as `.eprj2` before
it opens.

### What the owner does in EasyEDA Pro

- **Footprints are not bound.** Until every part has one, the editor refuses to export a netlist
  (its DRC calls a missing footprint fatal). A device links to a footprint by uuid;
  `Page.bind_footprint` does that, and the gauge uses it with a generic 0805.
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
  - `current()` applies `_FAB_BY_MPN` and `_FAB_CONN`, and refuses an entry no part uses.
  - A part that JLC cannot place is marked `assembly="hand"`, with the reason in its `source`.

`eprj3/v2footprint.py` converts EasyEDA library footprints, which the library serves only as V2, into
V3 records. It reproduces the editor's own conversion of 19 footprints record for record. The oracle
test needs those example files locally and skips without them.

**Footprints are bound to devices.** EasyEDA joins a symbol pin to a footprint pad by number. Our
symbols number pins by the netlist's names (`A`/`K`, `G`/`D`/`S`, `VS`), so each footprint's pads
are renamed to the pins they carry:

- `padmap.py` holds the pad → pin maps, typed from each part's datasheet. `test_padmap.py`
  checks every map against EasyEDA's library symbol where this machine can reach the library, and
  it fails on a swapped FET or a reversed diode.
- `footprint_lib.py` fetches the library footprints through `~/tools/lcsc-search` (cached, so it
  works offline after one online build). `fit()` renames their pads and removes the VH post the
  design omits. The inter-board connectors get a generated 2.54 mm header pattern, because every
  family on the options list uses that grid.
- The build summary names every placed item still without a footprint. `--no-footprints` binds
  none, and the test suite binds only generated footprints.
- No library data is kept in this repository.

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
