# PCB layout — the process: placement (Part 1) and routing (Part 2)

Owner, 2026-09-22: *"devise a process for PCB placement. It should take all boards into
consideration, use logic and process to decide on placement, make revisions when needed, and then
save so that i can view your work. This process should be repeatable."*

This is that process. It is a **tool** (`tools/place.py`), not a session's judgement: the same
netlist gives the same placement, every constraint it obeys is one the repo already encodes or this
document states with its reason, and every run ends with the `.eprj2` the owner opens. The owner
reviews; the tool re-places.

## Why the stack is one problem

Three facts make the boards inseparable, and the process is built around them:

1. **Two connector pairs must sit at the same X,Y on two boards.** `J307`↔`J407` (PWR-LOGIC) and
   `J308`↔`J406` (STACK) mate straight down between OUTPUTS and LOGIC. Place one, and the other's
   position is fixed — the stack is only as aligned as those two footprints.
2. **Two keep-outs cross boards.** `J311` and `J312` hang 10.9 / 8.6 mm under OUTPUTS into the
   30 mm gap, so nothing on POWER taller than 18.1 / 20.4 mm may sit beneath them — which is where
   POWER's 22 mm chokes and 18.5 mm bulk caps want to be.
3. **The connector face is one edge of the box** (IO-6). Every board's harness row sits on the
   same edge, in the order `edge_budget` fixes, and the cable halves (`J202`↔`J311`,
   `J105`↔`J312`) should be near each other along the board so the looms run straight.

So the order is **OUTPUTS → LOGIC → POWER**: OUTPUTS holds both mated pairs' lower halves and both
hanging connectors, so it fixes the most; LOGIC then inherits two positions; POWER then inherits
two keep-outs and two loom targets.

## The frame

The tool reasons in a **board frame**: `u` along the 242 mm length, `v` across the 41.84 mm width,
**v = 0 is the connector face**, +v toward the back edge. Every table it writes gives `u`, `v` and
the board angle, beside the file's own X, Y.

⚠️ **The file's outline is portrait.** The build draws the board 41.84 mm along X and 242 mm along
Y (M3 holes at (3.5, 3.5) and (38.34, 238.5) mm; 1 mm = 39.3701 mil), so the board frame and the
file frame differ by a rotation, which `place.Frame` reads from the outline at run time:
`(u, v) → (x, y) = (v, 242 − u)`, and a footprint at board angle 0 stands at file angle 270. The
connector face is the file's **left edge** (X = 0), and u runs from the top of the sheet down. A
landscape outline would map with the identity; nothing in the tool assumes either. The imported
parts sit at negative Y (dumped below the outline by the editor); the tool moves every one of them
onto the board.

**The editor's conventions**, read off tracks landing on pads in its own example projects: a
component's `angle` is degrees counter-clockwise, and a component on layer 2 is rotated in its own
frame and then mirrored about X. A footprint's plan is read from its FOOTPRINT document — pads,
top silk, component shape — and widened to the body `netlist.py` states, so a courtyard is never
smaller than either. **Pads are named by pin** (`padmap.py` renamed them before embedding), which
is what lets the tool weight pin positions, check a mated pair pin for pin, and know which pads of
a brick carry pack voltage.

## The placement logic — bands, derived from the copper

Every board is a **filter**: signals enter at the face on screw terminals, pass through their
protection, reach their driver or reader, and leave DOWN or UP through an inter-board connector.
The tool lays each board out as bands from the face backward and fills each by **net adjacency**:
a part goes next to the pins it shares nets with, nearest the terminal its signals enter on.

| Band | Front (v, mm) | Holds | Rule |
|---|---|---|---|
| **1 · face** | 0 | the harness row | `edge_budget` order, 1 mm gaps (4 mm where the row changes voltage class), centred in the 242 less the two 7 mm M3 corners, or `--anchor left`/`right`; the plug side of each body faces the edge. ⚠️ **ONE strip for BOTH faces**: a terminal is through-hole, so `J314` under OUTPUTS takes the same length of edge as one on top — its pins would otherwise land in the 12 V terminals' bodies. A header that does not fit the strip is left UNPLACED |
| **2 · protection** | row depth + 2 | each terminal's TVS, series R, pull-ups, clamps, and the class-A cap one hop behind them | directly behind ITS terminal |
| **3 · function** | 19 | drivers, switches, expanders, the buck, the chokes and bricks, and every IC of the same part number as one of them | over the terminals they serve; their passives follow them |
| **4 · brain / power** | 30 | the S3, its LDO and supervisor, the CAN transceiver, every inter-board connector footprint | the S3's antenna end at the back edge; `J307`/`J308` flush to the back edge; `J406`/`J407` at the mates' X,Y |
| **under** | — | the 7 bottom parts, by the netlist's `side` | `U201`/`U202` with the HV group; `J314` in the face strip; `J311` as near the middle of the V12 drivers as its pins allow — they may not come up inside their bodies (check 17) — `J312` where its signals are; `J406`/`J407` at the mates' X,Y |

**Bands are fronts, not walls.** A part is pulled toward its band's front and charged for the
distance it ends up from it — three times a sideways step behind the front, four times ahead of
it — so a band stays shallow and spreads along the terminal it serves, and a deep part (the S3 at
25.5 mm, a lying can at 30 mm) reaches into the next band's range in its own column rather than
failing. What holds between bands is the **channel**, wherever one band's part stands directly
behind another's. Strips straight across the board are not possible: the S3 alone is 25.5 mm deep
on a 41.84 mm board, and POWER's bulk fills the depth behind its row.

**A part's band is derived** (`place.bands`) from kind and nets: a harness terminal is 1; a passive
on a net that reaches a terminal, or one hop from one through a signal net, is 2; an IC that shares
a signal with a Band 2 part or a terminal is 3, and so is any IC of the same part number; the
module, the interface connectors, an IC that talks to the module and no terminal, and an IC with
no signals on the module's rail are 4; any other passive takes its function partner's band.

**Order within a band:** parts with a fixed target first (the S3, the flush connectors, the loom
mates), then the function parts by area, then the passives by area. A **satellite** — a 100 nF
decoupler, an ADC input's RC filter, the CAN transceiver — is placed the moment its host is,
against the host's body, whichever side is free. ⚠️ **And the host stands where its satellite can
follow it**: a position with no room beside it for the satellite costs the host `SATELLITE_ROOM`
(10 mm of its own travel), because a host that drops into a hole exactly its own size pushes its
satellite across the board. That is how `U406` — walled in by `U405`, the channel in front of it
and `J406`'s through-hole pads behind — left its 100 nF 8.6 mm away and failed check 15 while
every other check passed.

**Adjacency scoring:** the candidate `u` is the pin-weighted centroid of the already-placed pins
the part connects to — GND weighs 0 (it is a plane), pack-voltage nets and the 12 V bus weigh 10
(wide copper, kept short), other rails 0.2, a signal 1 per pin — then the nearest free slot by a
shelf scan with the clearances below. Among the four quarter turns, the one whose pins land nearest
their partners wins (that is what tells 0 from 180 on a symmetric body). It is a greedy first-fit
— good enough to be *reviewed*, and honest about being a proposal, not an optimum.

**POWER places its 84 V parts first**, as one group: the bulk (bricks under the board, chokes,
cans, the fuse clip) packs against the end `J101` stands at, straight behind the row, and the HV
passives fill the gaps; the low-voltage parts then take the rest of the board and keep the strip.
If a board cannot seat every part at the engine's 3 mm HV strip, it is placed again with the strip
at the check's 1.25 mm floor and says so — the built-in revision.

## What the tool checks after placing — and refuses on

A placement the tool writes has passed every one of these **and has every part placed**, or it does
not write: a part with nowhere to go is reported by refdes with the reason it had none, and is never
squeezed somewhere illegal. Each check is numbered in the tool's output, every constant in
`place.py` says what it protects, and `tests/test_place.py` proves each check fires on a placement
that breaks it. The first nine are the placement's own; **checks 10–16 exist because the board must
be routed afterwards (owner, 2026-09-22) — placement decides whether routing is possible**; check 17
is the board itself, which has two faces and one set of holes.

1. **Inside the outline**, clear of the four M3 corners: a 7 × 7 mm washer square at each hole
   centre, read from the file.
2. **Same-face clearance**: 1.6 mm body to body — 0.5 mm courtyard each (`board_fit.COURTYARD`)
   plus 0.6 mm for one 0.2 mm trace with 0.2 mm each side, JLC's 4-layer capability, so a trace
   can pass between any two neighbours. Two harness headers in the row keep `edge_budget`'s 1 mm:
   no trace passes between flanges.
3. **Every bottom-side part on layer 2** and every other on layer 1 — the set comes from the
   netlist's `side`, not from a list: `U201 U202 J314 J311 J312 J406 J407` today.
4. **The mated pairs coincide**: `J407` over `J307`, `J406` over `J308`, X,Y within 0.01 mm — and
   **pin for pin by net**: every contact of the lower half has the upper half's contact at the same
   place carrying the same net. The upper half's angle is found the same way: the quarter turn at
   which its pre-mirrored footprint lands its nets on its mate's (180 from `J308`'s, in the file).
5. **The cross-board keep-outs hold**: nothing on POWER's top taller than the limit stands under
   `J311`'s or `J312`'s footprint as placed on OUTPUTS; the limit is the gap less the connector's
   height less `CLEARANCE`, from `board_params`.
6. **The row is at the face**, bodies from v = 0, in `edge_budget` order, no header past the board
   end less the M3 inset.
7. **HV on POWER is copper.** The 84 V rule binds a part's HV **pads** where the footprint names
   them (the bricks, the chokes, `J101`) and its whole body where it does not (a D-PAK's pads are
   1-2-3): the brick under the board puts pack voltage on the top layer only at its input pins, and
   its output end is 12 V. That copper keeps ≥ 3 mm from the board edge (the edge is where the
   enclosure, a standoff or a finger meets the board) and ≥ 1.25 mm courtyard to courtyard from
   every LV part (`layout_rules.HV_CLEARANCE_MM`, IPC-2221B B2 at the 160 V do-not-exceed) — a
   *placement* proxy for the routing rule the owner sets up in the editor.
8. **The S3's antenna end** (`U401`'s local +Y, the padless end) within 2 mm of the back edge,
   nothing in the 8 × 18 mm zone beyond it on either face.
9. **Nothing on a face taller than that face's gap** (`layer_gaps`).
10. **Channels**: 2 mm between bands, 3 mm to or from Band 4 (the S3's 25 STACK signals fan out
    there), wherever one band's part stands directly behind another's.
11. **The 12 V bus on OUTPUTS is a line**: the centroid of the V12-fed ICs (`U301 U302 U303 U305`)
    within 15 mm of the contact that feeds them (`J311`), and all of them facing one way, so `V12`
    is one straight pour, not a tree. Which ICs and which contact come from the copper: the net
    `U201`'s `+V` is on. ⚠️ **This now pulls against check 17**: `J311`'s four pins come up through
    the top face, so the feed may not sit under the driver line, and the engine gets it only to
    17.5 mm on the owner's footprints. Either the drivers leave a gap for those pins or the bus is
    fed from the end of the line — an owner's decision. ⛔ The 15 mm is not relaxed to hide it: it
    is the length of an 11.39 A pour.
12. **The ground plane** (152 pins on OUTPUTS, 108 LOGIC, 58 POWER — never traces): no through-hole
    connector longer than 40 mm laid across the board's short axis. `J308`/`J406` (2 × 29, 73.66 mm)
    lie along the board, flush to the back edge, where a row of holes cuts a plane least.
13. **The HV region on POWER**: the 84 V parts form **one group** (each within 3 mm of another),
    and **no LV part is enclosed** by 84 V copper on all four sides. The region's bounding box
    cannot be made LV-free on this board — the HV bulk (3500 mm² of chokes, cans and Y-caps) has to
    stand behind the LV headers of the same row — so "inside" means the part's traces could not
    leave without crossing pack voltage; copper on three sides is a bay with a way out.
14. **Pairs and sense lines are short**: `U404` within 10 mm of `J406`'s CANH/CANL contacts; the
    I²C pull-ups ≥ 5 mm off the straight path from the brake terminal (`J306`) to the S3; an ADC
    input's RC filter within 5 mm of the S3 (`R476`/`C437` on `KEY_SENSE_PIN`). A SENSE net is a
    TPS4H160B `CS` net, or a net on an S3 ADC1 pin that a capacitor filters — `TWAI_TX` and
    `FAN_CMD` use IO6–IO10 digitally and are not.
15. **Every decoupler on its IC**: a 100 nF whose two nets are a rail and ground within 3 mm (edge
    to edge) of the nearest IC on that rail; the engine hands the ICs on a rail its 100 nFs in turn.
16. **`J408` reachable**: on top, nothing within 5 mm of either end along its long axis — the cable
    plug's body and its exit; the drawing does not say which end, so both are kept.
17. **A through-hole part crosses the board**: no body on either face may come within
    `PIN_PROTRUSION` (1 mm) of a through-hole pad on the other one, because that pad is copper on
    both faces and the pin tip and its solder fillet stand ~3 mm proud of the far one. It protects
    the pin: a terminal's pins may not end up inside another terminal's plastic, a brick's case or
    an IC's body. **Only the pads cross** — a part may stand over a through-hole part's *body* on
    the other side (a 0603 over the brick's case is fine), and two surface-mount parts may overlap
    in plan freely. Two through-hole parts on opposite faces therefore may never overlap at all.
    The engine keeps the wider `CLEAR` (1.6 mm) from a pad on the other face, so a trace can still
    pass between the pin and its neighbour. ⛔ This is the rule the first placement broke while
    passing all 16 of the checks above: `J312`'s 24 pins inside `J308`'s 58, `J311`'s inside
    `U301`/`U302`, `J314`'s inside `J303`, `J406`'s inside the S3, and both bricks' inside the
    through-hole parts on POWER's top face.

Every comparison allows a micrometre: the file holds mils to four decimals, and a coordinate
written and read back may move by nanometres.

**Power classes are derived from driver pins, never from a net's name** (`place.power_classes`):
PWR12 is the net on `U201`'s `+V`; CH12 a net with a TPS4H160B `OUTx`; CH5 a net with a TPS2553
`OUT`; PWR5AUX the buck's `SW` net and its inductor's nets; SENSE as above. `AUX5V_n_FAULT` is a
logic level and is in no class. The adjacency weights use them: `V12` pins ×10, HV nets ×10, GND ×0
(a plane pulls nothing), so the bus line, the HV group and the decoupler proximity fall out of the
flow rather than being bolted on.

## The loop — repeatable

```
tools/place.py --stack --draw pics/    # place OUTPUTS, LOGIC, POWER in that order; check; write
                                       #   → ~/Documents/EasyEDA-Pro/projects/revv1-module.eprj2
owner opens it, looks, closes the editor
tools/place.py --check --draw pics/    # re-read the SAVED file; report every rule above
LOOK AT pics/*.png                     # ✔ a required step, not a decoration
tools/place.py --stack --keep J302 J305 # re-place, holding the owner's hand-moved parts fixed
```

- `--stack` reads the saved `.eprj2` (the owner's file — so hand-moved parts are known), places
  every part **not in `--keep`**, checks, writes back, and writes `layout/<BOARD>-placement.md`.
  ⛔ It refuses if the editor is open, if any check fails, **or if any part had nowhere to go** —
  and then names each one and why. `--file` and `--out` point it elsewhere; `--docs` says where
  the tables go.
- **`--board LOGIC [BOARD …]` writes only the named boards' PCB documents** — every other board's
  records are left exactly as saved, and only the named boards' failed checks and unplaced parts
  refuse the write — while all three are still placed in memory, because LOGIC's mates sit at
  OUTPUTS' `J307`/`J308`.
- `--check` never writes. It is the review step and the regression test: after the owner moves
  things by hand, `--check` says what broke.
- ✔ **`--draw DIR` writes one PNG per board, and looking at it is a step of the process** — the
  proposal for `--stack`, the file's own placement for `--check`, and on its own it just draws the
  file and judges nothing. Outline, M3 washer squares, band fronts, every body as a box (top black,
  under-board blue, pack voltage red, UNPLACED orange), every pad as a dot (GND green, HV red) with
  a **ring where the pin goes through the board**, every refdes labelled. ⛔ **It caught what the
  16 checks did not**: the first placement stood two faces inside each other and reported
  `0 problem(s)`; the picture showed it at a glance. Numbers prove parts do not collide on the axis
  they measured; a picture proves they are where you think. It is the one part of the tool that
  needs Pillow, imported only when the flag is used.
- `--keep` is how revision works: the owner fixes a part where they want it; the tool re-flows
  everything else around it. Repeat until the owner is satisfied.
- **Every write goes through the same round trip the build uses** (`eprj2.read` → edit the
  COMPONENT records and the labels that follow them → `eprj2.join` → `eprj2.write` → re-read), and
  the tool refuses to leave a file whose re-read differs from what it meant to write, coordinate by
  coordinate.
- The write is to the owner's file **only** — it is placement, not generation, so the build's
  no-clobber guard (`_is_generated`) does not apply; the tool keeps the previous file as
  `.eprj2.prev` for one step of undo.
- A PCB that carries a part the netlist does not put on that board is refused: re-import the
  schematic first.

## What the tool does NOT do

Route — **Part 2 says what it does instead**: derive the rules, write them into the project, check
the result. Judge aesthetics. See silkscreen. Know where the harness enters the box (that biases which
end the row sits toward — an `--anchor left|right` flag, default centred). Those are the owner's,
and the loop above is how the owner's judgement re-enters the process without losing what the
tool derived.

## Files

- `tools/place.py` — the tool. Stdlib only (plus what `eprj2` needs to decrypt the file, and
  Pillow for `--draw`).
- `tests/test_place.py` — every check above proven to fire on a placement that breaks it, the
  engine proven to leave a clean one, and the writer proven to round-trip. The project under test
  is **synthetic** (the build's outline, pin-named pads from the netlist), so no file of the
  owner's is committed; `REVV1_PLACE_PROJECT=/path/to/saved.eprj2 pytest tests/test_place.py`
  runs the same tests on a real save.
- `layout/PROCESS.md` — this document. `layout/<BOARD>-placement.md` — the per-board tables
  (`u`, `v`, angle, file X, Y, layer, band, and the reason: "face row, position 3 of 5" /
  "centroid of U402, R413, …" / "fixed: mate of J308"), regenerated on every `--stack`.

---

# Part 2 — Routing

Owner, 2026-09-22: *"after placement, we will need to route the traces"* and *"the routing process
should be included in our layout process."* Placement decides whether routing is possible; routing
decides whether the board works. The two are one process, and the placement rules in Part 1 (the
channels, the bus line, the HV region, the ground plane) exist **for** this part.

## What a tool can do, and what it cannot — stated first

A tool **can derive** every number routing needs from the netlist: which nets carry current and how
much (`power_budget`), which need clearance (`layout_rules.hv_nets`), which are pairs, which are
planes, which pins must be short. It **can write** those as **net classes and design rules** into
the project so the editor enforces them while you route. And it **can check** a routed board read
back from the save: every net connected, every rule met, every width and clearance as derived.

A tool **cannot** route this board well. Autorouters exist (the editor has one) and are acceptable
for the signal fan-out on LOGIC; they are **not** acceptable for the 8.47 A bus, the 84 V region, or
the CAN pair. Those are routed by hand, by the owner, against rules the tool set up. **The process
puts the derivation and the checking in the tool, and the routing in the editor.**

## Step R0 — the rules go in before the first trace (`tools/place.py --rules`)

Derived from the netlist, written into the project's PCB documents as net classes and rules, and
printed as `build-eprj3/layout-rules.txt` (already exists; extended). ⛔ The editor's board-wide
default is 0.2 mm / 0.2 mm — good for logic, fatal for power. These override it per class:

| Class | Nets (derived) | Width | Clearance | Why — the number it protects |
|---|---|---|---|---|
| **HV** | the 14 `hv_nets(d,"POWER")` | 0.5 mm | **1.25 mm** | IPC-2221B B2 for the 160 V do-not-exceed. Already in `layout-rules.txt`; unchanged |
| **PWR12** | `V12` and its return on OUTPUTS and POWER | **≥ 5.0 mm** on 1 oz outer copper, or a **pour** | 0.3 mm | **11.39 A** — the LIMITED case, not the 8.47 A nominal (`power_budget.limit_case`): the copper must survive every limiter at its ceiling. 5 mm / 1 oz ≈ 11 A at 20 °C rise (IPC-2152 external). A pour is better; the placement's bus line exists so a pour works |
| **PWR5AUX** | `V5AUX` and its switches' inputs | **2.0 mm** | 0.3 mm | 4 × 1.39 A = 5.6 A at the limiters |
| **CH12** | each `AUX12V_n`, each lamp `OUTx` | **1.0 mm** | 0.25 mm | 1.55 A per channel at its limiter (`R359` = 1k5) |
| **CH5** | each `AUX5V_n` | **0.8 mm** | 0.25 mm | 1.39 A |
| **RAIL** | `V5`, `V3P3` on every board | 0.6 mm | 0.25 mm | the logic supplies; < 1 A but many pins — width is for droop, not heat |
| **DIFF** | `CANH`/`CANL` | 0.25 mm, **paired**, 0.25 mm gap | 0.4 mm to everything else | a differential pair on a 4-layer board; 120 Ω is not achievable in 0.25 mm over 0.2 mm prepreg — **the run is electrically short (< 150 mm) so impedance is not the constraint; pairing and skew are** (audit A10 / parts doc §2) |
| **SENSE** | `KEY_SENSE_PIN`, `V12_SENSE`, `CS1`, `CS2` (the four ADC nets), `BL_SENSE` | 0.25 mm | 0.3 mm, **not adjacent to any CH12 or PWR** | an ADC input beside an 11 A pour reads the pour, not the sense |
| **default** | everything else | 0.2 mm | 0.2 mm | signals; the editor's default is right for these |

⚠️ **Widths are for 1 oz outer copper on a 4-layer board, inner layers reserved for planes.** If
the fab's stackup differs, `--rules` takes `--copper-oz` and re-derives. The tool writes the class
membership from the netlist every run, so a renamed or added net is never in the wrong class.

## Step R1 — planes, before any trace (owner asked 2026-09-22: "we have 4 layers, should we fill one ground and/or power?" — yes, and a different one per board)

Decided from the pin counts, not the textbook. **Layer 2 is GND on every board** (152 pins on
OUTPUTS, 108 on LOGIC, 58 on POWER — never traces; a solid plane under the top-layer parts gives
every signal its return and every decoupler a short loop). **Layer 3 differs by what each board
carries:**

| Board | Layer 3 | Because |
|---|---|---|
| **OUTPUTS** | **`V12` pour** under the driver line and the buck | 28 pins at **11.39 A** at the limiters. The pour IS the bus: `J311`'s two power contacts onto it by vias-in-pad or a ≥ 5 mm neck; each `TPS4H160B`'s `VS` pins down to it by **four** vias, not two — the pour is also the drivers' heat spreader, and a via is a thermal path only if there are enough |
| **LOGIC** | **`V3P3` pour** | 48 pins — the S3, two expanders, every pull-up: a pour for **droop**, not current |
| **POWER** | **second GND** — no power pour (6 `V12` pins earn none) — **and BOTH inner planes cut back 3 mm from the HV region** | the 14 HV nets sit at up to 160 V; a plane under them is 84 V-to-GND across one 0.2 mm prepreg, which is what the 1.25 mm rule forbids. The 84 V section returns on `HV_C1_N` / `HV_C2_N` — **not GND** |

**Layers 1 and 4 (outer): traces and the parts.** The bottom layer carries the seven bottom parts'
pads and the face rows' returns.

⛔ **What the planes demand of placement** (and why Part 1 checks it): no long THT connector across
the short axis — `J308`/`J406` at 73.66 mm would split every inner plane, so they run along X at an
edge; `J311` under the driver line, or the `V12` pour is fed through a bottleneck; the HV region one
contiguous blob, or the plane cut-back has holes in it.

`tools/place.py --rules` writes the two pour outlines per board (the `V12` pour's rectangle over the
driver line; the HV cut-back polygon on POWER) as copper regions into the project, so the owner
fills them rather than draws them.

## Step R2 — route by class, in this order (owner, by hand, in the editor)

Power first, because it needs the room; signals last, because they can go around anything.

1. **HV region on POWER** (class HV). `J101` → `Q101` → `L101` → `C201` → `U201.+Vin`, and the Cincon
   branch. Short, wide, on one layer, inside the region the placement drew. ✔ **Before leaving it:
   run the editor's DRC with the HV rule on** — the one check the tool cannot do until you save.
2. **The 12 V bus on OUTPUTS** (PWR12). Pour on layer 3 under the driver line; `J311`'s two power
   contacts onto it with the widest neck the pad allows. Then each driver's `VS` pins down to the
   pour with two vias each. **Then the return**: `J311`'s GND contact to the layer-2 plane the same
   way. This is the 8.47 A path — nothing else on the board matters if this is thin.
3. **The 5 V aux supply** (PWR5AUX): `U305`'s input from the pour, its inductor `L301` and output
   caps in a tight loop (the switching node `V5AUX_SW` is the noisiest thing on the board — shortest
   trace, no via, no signal within 3 mm), then `V5AUX` to the four switches.
4. **Each output channel** (CH12 / CH5): driver `OUTx` → clamp diode → terminal, in that order and
   that geometry — the TVS sits *between* driver and terminal so a surge meets the clamp first.
5. **The face rows' returns**: every terminal's GND to the plane by its own via, beside the pad.
6. **The differential pair** (DIFF): `U404` → `J406` on LOGIC; `J308` → `J312` on OUTPUTS. Paired,
   same layer, no via if it can be avoided, one via each if not — together.
7. **Sense lines** (SENSE): `KEY_SENSE_PIN`, `V12_SENSE`, `CS1`, `CS2` from their dividers to the S3 or
   the `CS` pins, routed *away* from every CH12 and PWR trace; on the layer opposite the pour.
8. **Everything else** — the autorouter is acceptable here, **after** 1–7 are done and locked.
   Lock every trace of classes HV, PWR12, PWR5AUX and DIFF first, or the autorouter moves them.

## Step R3 — the routed board is checked, not admired (`tools/place.py --check-routing`)

Read back from the saved `.eprj2`, every one of these, and the tool says which failed:

- **Every net connected** — the editor's own unrouted count, read from the file, is 0.
- **Every class rule met** — width ≥ the class minimum on every segment; clearance ≥ the class
  minimum to every other net. (The editor's DRC does this too; the tool does it from the netlist's
  own derivation so a class the owner forgot to set up is still caught.)
- **The HV/GND separation**: no GND copper on any layer inside the HV region's outline + 1.25 mm.
- **The pour exists**: `V12` on layer 3 covers ≥ 80 % of the bounding box of the parts on it.
- **Every decoupling cap's loop**: cap pad → IC power pin ≤ 3 mm of trace, cap GND pad → a via ≤ 2 mm.
- **The CAN pair**: `CANH` and `CANL` segment lengths within 5 % of each other, never more than
  0.5 mm apart along the run.
- **No via inside the Tag-Connect keep-out**, and none inside the four M3 annuli.
- **Sense nets**: no `SENSE` segment within 1.0 mm of a `PWR12` or `CH12` segment on the same layer.

## Step R4 — export, prove, DRC

After routing, the same proof as always, plus the editor's: **export each board's netlist →
`tel_check` identical** (routing must not have changed connectivity — an accidental short or a
dragged pad shows up here) **→ editor DRC clean with every class rule on → `--check-routing` clean.**
Three independent checks; a board is routed when all three agree.

## The loop, complete

```
tools/place.py --stack            # placement (Part 1) → the .eprj2
tools/place.py --rules            # net classes + design rules INTO the project, layout-rules.txt out
owner: planes, then route by class R2.1 → R2.8, save often
tools/place.py --check            # placement still legal after the owner moved things
tools/place.py --check-routing    # R3
owner: export ×3 → tel_check ×3 → editor DRC
```
`--check` and `--check-routing` never write; run them after every save. `--stack --keep …` re-flows
placement around what the owner fixed; there is deliberately **no** `--route` — the tool derives and
checks routing, the owner does it.

## What routing may send back to placement

Routing finds what placement could not: a channel that is too narrow for the bus neck, a TVS that
ended up on the far side of its terminal, a decoupler whose IC is across a plane split. **Each is a
`--keep` and a re-place, not a hand-fix that the next `--stack` would undo.** When it is a *rule*
that was wrong (a channel width, a band boundary), fix the constant in `place.py` — every number
there states what it protects, so the fix names what it learned.
