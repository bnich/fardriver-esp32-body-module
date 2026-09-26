# Design-time tooling

Checks the three-board set and generates its EasyEDA Pro project from a checked-in netlist.
**Stdlib only**, no virtualenv, with three exceptions, each checked by name before the gate runs
anything:

- the tests need `pytest`;
- the `.eprj2` output needs the `cryptography` package;
- library footprints come through `~/tools/lcsc-search` (`LCSC_SEARCH_HOME` to relocate it), which
  caches every answer, so builds run offline after one online build. Without it the build binds no
  library footprint, names every item left without one, and exits 2, INCOMPLETE.

Run everything from the repo root.

📄 The design these tools describe: [`../docs/plan.md` §9.2](../docs/plan.md).

## The order to run things in

After any change to the netlist or the model, run the gate:

```bash
tools/gate.sh
```

It removes every `__pycache__` first — CPython validates a `.pyc` by second and size, so a
same-second, same-size edit (`1.25` → `9.25`) is otherwise read as the OLD constant, and `-B` /
`PYTHONDONTWRITEBYTECODE` stop writing one, not reading it — checks that `pytest`, `cryptography`,
`~/tools/lcsc-search`, an editor-saved `.eprj2` template and **pcb-layout-tools v0.11.0** (`pcbl` on
`PATH`, or `PCBL` set to it; the gate names the version it needs and the one it found) are present,
then runs these, in this
order, each **bare**, and exits at the first non-zero exit code naming the tool:

```bash
python3 -m tools.integrity        # is the netlist a circuit at all?  exit 1 on any problem
python3 -m pytest -q              # rules and unit tests              hermetic: no library fetch
python3 -m tools.rules            # every rule, and the warnings      exit 1 on a violation
python3 -m tools.gpio_budget      # pin budget                        exit 1 on FAIL
python3 -m tools.power_budget     # the 12 V load, choke and tap fuse exit 1 on FAIL
python3 -m tools.soft_start       # D13 soft start                    exit 1 on FAIL
python3 -m tools.board_fit        # area, height and connector rows   exit 1 on FAIL (2: see below)
python3 tools/build_project.py --keep-saved-layout
                                  # the EasyEDA project and build-eprj3/layout-rules.txt — refused while EasyEDA Pro is open
                                  #   exit 1 REFUSED (previous build renamed .stale) · 2 INCOMPLETE (an item without a footprint, or no .eprj2)
                                  #   the owner's saved layout is left untouched and counts as the project (0, not 2)
python3 -m tools.jlc_bom          # JLC's BOM, the loose parts, the hand-soldered parts
python3 -m tools.layout_export PROJECT -o layout.yaml   # the design described to pcbl, in a temporary directory
pcbl stack --constraints layout.yaml                    # the stack's height budget, as pcbl reads the constraints
```

`pcbl check` is not in the gate: it is the layout's own bar (📄 `layout/PROCESS.md`), and a layout
still being routed fails it by design.

⛔ **`python3 -m tools.X | tail -1` returns `tail`'s exit code, not the tool's.** Every tool exits
non-zero on failure; a pipeline hides it. When the exit code matters, run the tool bare or run the
gate. ⛔ The gate has no flag to build while EasyEDA Pro is open — the editor holds the project the
build replaces, and refusing is the safety property. Close it and run again.

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
| `integrity.py` | Structural gate: every pin lands, every inter-board net has real contacts, every interface is two identical halves on neighbouring boards — a **mated pair's** halves facing each other, mirrored; a **cabled** interface's halves matching contact for contact, unmirrored (`model.CROSSING` says which is which) |
| `rules.py` | Safety and pin rules, each named for the decision it protects (`python3 -m tools.rules` prints them) |
| `board_params.py` | The board envelope the design requires, the enclosure allowances, the cavity that envelope implies — and the **derived** stack height |
| `board_fit.py` | Area, height and connector-row budget, and the cavity the design requires (`board-fit.py` is a two-line shim for it) |
| `gpio_budget.py` | ESP32-S3-WROOM-1 pin facts, and the design's demand on the pool |
| `power_budget.py` | The 12 V load against the parts that carry it: the converter, its input choke and the B+ tap fuse, at the LVC. It states which case it models |
| `soft_start.py` | The D13 main-switch gate network, simulated — key-on, the key-off decay, and the plug-in — and the DC voltage of every 84 V node, walked from the netlist for the pairwise clearances `pcbl` routes and checks to |
| `layout_rules.py` | The HV net class and the land keep-outs the generated PCBs cannot carry |
| `build_project.py` | Generates the EasyEDA Pro project for the four boards. Gated on integrity, rules and a read-back of its own output |
| `eprj2.py` | Reads and writes EasyEDA Pro's native `.eprj2`, and wraps the generated folder as one: the file the editor opens |
| `eprj3/` | The `.eprj3` emitter: `records.py` (record grammar), `units.py` (mm ↔ file units), `project.py` (the folder and its index), `pcb.py` (outline, 4-layer stackup, holes, rules), `symbols.py` (schematic symbols), `footprints.py` (footprint documents), `v2footprint.py` (EasyEDA library footprints, V2 → V3), `placement.py` (sheet layout), `schematic.py` (sheets, devices and nets), `reader.py` (reads a sheet back and derives its nets) |
| `padmap.py` | Which footprint pad each netlist pin lands on, typed from the datasheets |
| `footprint_lib.py` | Library footprints through `~/tools/lcsc-search`, fitted to our pins; the generated inter-board header patterns |
| `drawn_footprints.py` | Land patterns drawn from the makers' drawings: the parts with no library device, and the Tag-Connect service pads |
| `lcsc_fixture.py` | Refreshes `tests/fixtures/lcsc.json`: what LCSC says each ordered code is |
| `jlc_bom.py` | The BOM JLC's assembly service reads, one line per LCSC part, plus what is ordered loose and what is hand-soldered |
| `tel_check.py` | Proves EasyEDA's netlist export (`.tel`) against the netlist, pin by pin and footprint by footprint |
| `layout_export.py` | Describes the design to **pcb-layout-tools** (`pcbl`, tag v0.11.0), which places, routes and checks the boards: `python3 -m tools.layout_export PROJECT.eprj2 -o layout.yaml`. Every figure is read from where it already lives in this repo (📄 `layout/PROCESS.md`) |
| `layout_hooks.py` | Goes beside `layout.yaml`: the pack-voltage nets' operating points, from `soft_start.py` — code, not data |
| `layout_facts.py` | The layout facts the two above read: the board frame, the net classes and the rules that assign them, the decoupler hosts, the heavy path, the ground twin |
| `gauge.py` | Generates the one-sheet gauge project that proved EasyEDA Pro joins the generated nets |

### `board_params.py` — parameters typed, geometry derived

Holds the **board envelope, 41.84 × 242 mm** (and `POWER_W`, POWER's 42.3 mm depth) — typed, and re-derived by the search written out beside
it (the width stands **3.64 mm above the nearest packing discontinuity, which since IO-26 is a WALL
at 38.20 mm** and not a step: the quarter brick `U201` is 37.2 mm deep and with a courtyard either
side needs that much board, below which POWER's underside cannot be placed in any orientation —
which
`tests/test_board_params.py` derives from the packer and guards); the M18 cavity, **260 × 70 × 100 mm, measured by the owner 2026-09-20** (`CAVITY_MEASURED =
True`); the wall / floor / lid **allowances** (`ENCLOSURE_DECIDED = False` until the enclosure's
model sets them — the box is all-metal, its thicknesses are not yet known); PCB thickness; the mechanical clearance; the 1.5 mm a
trimmed through-hole lead stands out of its board (IPC); the 0.5 mm insulating liner on the metal
floor under POWER, whose underside carries 84 V pins; the floor seat — `U201` bolts its baseplate
to the box floor through a 0.5 mm thermal pad, which is the only heatsink (BD-27), and the liner is
cut away there; and the wire-bend room behind a harness plug. `STACK_ORDER` is bottom to top, four
boards — POWER · OUTPUTS · LOGIC · CTRL. ⛔ BD-9's alloy plate is withdrawn: there is none in the
stack, and nothing here models one.

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
  the gap, and a part that needs more room fails the design. A **cabled** interface's halves are
  ordinary bodies — they set no gap;
- a **`Standoff` is a pillar that DEFINES a gap** (`netlist.standoffs()` is their one home) — the
  third kind of thing in the height model, deliberately not a `Part`: `stack_height` names which
  pillar sets each gap and **fails a pillar shorter than the tallest part between its decks** — it
  would crush that part when the screws pull up (`L102` at 22.0 mm is the tall one today) — and
  fails a "sets" pillar that disagrees with a chosen connector pair's mated height.
  `standoff_problems` holds the table's structure: neighbouring decks only, one pillar per gap. A
  standoff whose `seating` is `"shimmed"` is deliberately short so a connector pair keeps setting
  its gap, and is reported, not failed — the TP-11 is fitted **by measured length, with no shim**
  (10.94–11.04 mm against the 11.04 mm stop), and a shim in the table is bounded by
  `gap − standoff` so a 2.4 mm nut booked as a 0.5 mm washer fails;
- a height that is `NaN`, negative or missing is a **failure**, never a short part;
- every unconfirmed height is listed, and the ones that set a gap are named (`load_bearing`);
- a bottom-side part and a tall part beneath it share a gap only by standing side by side, so each
  one produces a **keep-out** note naming what may not sit under it.

`stack_problems(design)` returns the failures in the shape a rule returns.

`cavity_required(design)` states the cavity the envelope asks the enclosure for — along, across
and the derived height — and `cavity_overruns(design)` names every axis the cavity does not hold.
`cavity_problems(design)` turns the two **plan** axes into failures once `envelope_is_binding()` —
which since M18 means **the cavity is measured**, and nothing else. ⚠️ `ENCLOSURE_DECIDED` is
deliberately *not* in that gate (owner's measurement, 2026-09-20): the cavity is the fact the design
cannot change, while the wall, floor and lid are the design's **own** allowances, so a design that
does not fit **with** them fails today rather than after the box is drawn. What the undecided
enclosure still does is keep the requirement from being final, which the report's first line says
and the failure text names as a lever. Today the design requires **256.0 × 68.95 × 87.0 mm** and
fits, with 4.00 mm along and 1.05 mm across to spare. The height is not in that list: `stack_height`
already fails on it through the same gate. Both `board_fit` and `rules` (`HT-CAVITY`) relay it, so
the two gates cannot give different answers.

### `board_fit.py`

```bash
python3 -m tools.board_fit
```

Prints, per board and side, the raw body area and density (**FAIL above 75 %** of the usable
side) and a naive shelf-pack length against the board's length (**FAIL when it does not fit** —
the tool then has not shown the board can be built; a placed outline overrules it, an argument
does not). Then the derived stack, gap by gap, against the height available, with every unconfirmed
height and every **keep-out** a bottom-side part imposes on the board below it.

⚠️ **ROWS replaced the per-wall plug verdict** when the connectors were grouped by kind (IO-6). There
is no longer a budget of "every header's plug against the nearest wall": every harness plug is on
**one face**, so the check is **one strip per board edge, both faces of the board in it** — its
harness headers end to end, 1 mm apart, against the **228 mm** between the M3 corners of the board
they stand on. ⚠️ A harness terminal is through-hole, so one hanging under the board takes the edge
exactly as one on top does (its pins come up inside the other's body), and an underside through-hole
body too deep to sit behind the row — the quarter brick, 37.2 mm of 41.84 — takes its length of the
strip too (`row_blockers`). The room a mated plug and its wire's bend need is no longer a
budget either: it is a **term of the cavity this design requires**, which the report states on its
second line against the cavity M18 measured. ⚠️ **That requirement is checked, not just printed:** a
plan axis the measured box cannot hold is a **FAIL** (`board_params.cavity_problems`).

One verdict: exit 1 when a budget fails, 2 when the stack is over an *estimated* envelope — a path
M18 closed, kept for the day a cavity figure goes back to being a guess. A body with no footprint
that is a connector, or 2 mm tall or more, fails the run: the budget cannot see it. The first line
says **THE REQUIREMENT IS NOT FINAL** while the enclosure is unmodelled: wall, floor and lid are
allowances, so the cavity figures move when its model lands — but every **verdict** binds
regardless, because the cavity is measured.

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

### `power_budget.py`

```bash
python3 -m tools.power_budget
```

The 12 V load against the parts that carry it, sized at the 60.0 V LVC because a converter is a
constant-power load. The base is plan §3.2.3's measured-and-estimated budget; **the aux load is
derived from the netlist** — every 12 V and 5 V aux channel at the design's per-output current, plus
the 5 V buck's own standing draw — and the 12 V converter and its choke are found **through the
copper**, never by refdes. It prints three cases and says which one the gates use:

- **NOMINAL** — IO-2's eight channels at 1 A each, **8.47 A**, and the converter, choke and tap fuse
  against their derates. ⛔ Never call this "worst case": it is not the ceiling.
- **LIMITED** — every limiter at its upper threshold, ~11.4 A, over the choke's and the fuse's
  derates by design: eight simultaneous output faults. ⚠️ **The fuse does not bound this case** —
  the `KLKD003` holds 100 % indefinitely and opens 135 %+ only within an hour. What bounds a
  sustained 12 V-side overload is the brick's own **OCP CEILING**, 12.75–18.75 A out (102–150 % of
  rating), which the tool derives as 2.83–4.17 A at the choke — **94–139 % of its 3 A** — with the
  time at that current stated (indefinite at the low end, until the brick's over-temperature trip;
  up to 60 min at the high end). The tap fuse is a short-circuit device for the 84 V side (~200 A
  prospective), and the tool says so.
- **SHED** — every aux channel released, which the firmware does at key-off (IO-16). This is the load
  `soft_start` charges `Q101`'s key-off decay with. ⚠️ The buck's standing draw stays in it: `U305`'s
  `EN` is tied to its own `PVIN`, so no firmware can release the 5 V rail.

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
outputs on through the decay and the bound is over the line again. Every expander's `RESET`
rides the S3's `EN` net (IO-22), so a reset that arrives **through `EN`** — power-up, the programmer,
a fitted supervisor — resets the chip that commands the aux outputs and the drivers' pull-downs take
over; but `EN` is an input the S3 cannot drive, so a watchdog or software restart does not reach it,
and the exposure is a hang **or a reboot** inside the hold, through the shortest hold (~300 ms at the
LVC, slow FET). `key_off_decay()`
integrates the decay beside the bound, which lands a little under it and puts the equal-energy pulse
**past the SOA table's 100 ms row**, so the DC line is the right row and not a stand-in for a
missing one. The `KeyOff` docstring says what a further refinement would take: a converter
under-voltage shutdown threshold, which TDK does not publish for the CN-B110.

**It also owns the 84 V section's node voltages** (`hv_node_ranges()`, IO-29), because the gate
network is already here and a second walk elsewhere would be a second thing to keep true.
`hv_node_voltages()` gives every node in the section one DC voltage per operating point, walked
from the netlist: the switch's source is the B+ tap, its drain follows the key, its gate is the
source less `static_v_sg`, the shifter's drain and gate come off the same circuit, and everything
else is reached across a choke winding, a fuse or the hold-up rectifier — the divider mids read
off their own resistor values. The points are pack 43 · 60 · 84 · 160 V (`pack_ceiling_v()`, the
lowest input rating among the fitted converters, not a typed 160) × key on · key off · the
hold-up's **ride-out**, at both ends of the rectifier's drop. ⛔ One value per node per point, not
a band: a band would make the two ends of F201 — the same copper — read a diode drop apart.
`pcbl` takes the differences (through `tools/layout_hooks.py`); nothing here knows which pairs exist on the board.

### `layout_rules.py` — the HV net class and the land keep-outs

```bash
python3 -m tools.layout_rules
```

The generated PCBs carry one board-wide clearance, 0.2 mm: the record form of an editor-made net
class is not known from any file here, and a guessed record can corrupt the project. Copper at pack
voltage needs **1.25 mm** (IPC-2221B B2, 151–300 V: the 160 V do-not-exceed). This lists, per board,
every net that can sit at pack voltage — typed 84 V, DC-joined to one through copper, a switch, a
choke or a diode, **or SOLVED above the 12 V rail by its resistors** (`rules.hv_nets_solved`, the
same divider solver the rules use) — as the net class **HV**. A net typed `12V` that the copper holds
at 84 V is a rule violation, not a silent drop from the class: the class is derived from the solved
voltage, never from the label alone. Today: 14 nets on POWER, none elsewhere. `build_project.py` writes the same text to
`build-eprj3/layout-rules.txt`. ⚠️ **Set the class up in the editor before routing POWER:**
PCB → Design → Net Class, a class `HV` holding those nets; Design Rules → Safe Spacing, a 1.25 mm
rule applied to `HV`.

⭐ **1.25 mm is the figure against LOW-VOLTAGE copper.** IPC-2221B sets clearance by the voltage
*between* two conductors, so between two of these nets it is their own difference (IO-29), which
`pcbl` routes and checks to. The editor's rule deliberately stays at 1.25 mm to everything —
it is what keeps the autorouter's low-voltage copper away from pack voltage — and the joins it
will flag as a result are listed in `layout/POWER-drc-exceptions.md`.

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
offline on every run: `lcsc_fixture.check` compares the **maker** word of the netlist's table string
to the record's manufacturer, the netlist **package** to the record's package, the MPN by
**equality** after a stated suffix strip — never by substring, so `BSS127` does not accept
`BSS127S-7` and `SMS05T1G` does not accept `TPSMS05T1G` — and each inter-board connector's contact
count to the record's symbol-pin count. So a changed code that points at a different part (a 65 °C
ESP32, a Diodes `BSS127S-7`, a clone TVS, a 1×12 socket ordered for a 14-contact table) fails
although the rules, which read the netlist's MPN, pass. Where the library is
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
generator's netlist" and exits 0 **only when every net and every placed part's footprint was
compared**; it exits 1 on any difference — and a placed part whose footprint could not be compared
(no footprint in the fixture record, or none in the export) is a **problem**, never a silent skip, so
"identical" is never printed over an uncompared part. ⚠️ **A proof holds
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

Both write their folder, zip and `layout-rules.txt` to `build-eprj3/` (`--out DIR` to change it) — a
gitignored build artefact; never hand-edit it. **The `.eprj2` goes to
`~/Documents/EasyEDA-Pro/projects/`**, the editor's own folder and the ONE place it lives (owner,
2026-09-22) — ⚠️ **unless the file there has been SAVED by the editor**, in which case it is the owner's
layout and the build refuses to overwrite it (exit `INCOMPLETE`, reason printed). A generated project
carries the build's fixed `updateTime` on every document; a saved one does not. 📄 `layout/README.md`
for the netlist-change procedure that keeps placement.

⭐ **Open `~/Documents/EasyEDA-Pro/projects/revv1-module.eprj2` in EasyEDA Pro**, by its path. The editor lists a project only after
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
- **The generated project carries no layer for any part — SIX sit on a bottom face and every one
  is flipped by hand in the editor**, against `side` in `netlist.py`: `U201` and `U202` under
  POWER (the brick's underside seat is what `FLOOR_SEAT` and the whole thermal design rest on) ·
  `J311` under OUTPUTS · `J406` and `J407` under LOGIC · `J501` under CTRL. Each `…-UNDER` footprint
  (`J406`, `J407`, `J501`) is the upper half of a **mated** inter-board pair and is generated
  mirrored: after
  the flip, plus at most a 180° turn, every pad sits over its mate's. A same-numbered dual-row
  footprint cannot be aligned by any turn — STACK's signals would land on its ground row. The
  **cabled** half `J311` and both converters are ordinary,
  un-mirrored footprints — a cable has no mate to line up with; the loom carries the orientation.
  ⚠️ The 5 V terminal `J314` is no longer one of them: since IO-26 2a it stands on CTRL's top face.
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
  design does not use), and refuses a pad no map accounts for. The inter-board connectors get a
  generated header pattern on their own pitch — the keyed VH halves keep JST's contact numbers, with
  the omitted position a real gap in the pattern; only a **mated pair's** upper half is mirrored
  (`-UNDER`), never a cabled half.
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
- **Rows and pitches are held by the tests, not by `rules.py`:** `tests/test_rows.py` puts every
  harness connector on its row's face, gives 3.50 mm, 5.08 mm and 7.62 mm to one group each, refuses
  a 12 V terminal that shares a size with an input terminal, and requires every class-A network to
  sit on the board its terminal is on. Each check is proven to fire on a deliberate mistake.
