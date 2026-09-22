# PCB layout — the process: placement (Part 1) and routing (Part 2)

Owner, 2026-09-22: *"devise a process for PCB placement. It should take all boards into
consideration, use logic and process to decide on placement, make revisions when needed, and then
save so that i can view your work. This process should be repeatable."*

This is that process. It is a **tool** (`tools/place.py`), not a session's judgement: the same
netlist gives the same placement, every constraint it obeys is one the repo already encodes, and
every run ends with the `.eprj2` the owner opens. The owner reviews; the tool re-places.

## Why the stack is one problem

Three facts make the boards inseparable, and the process is built around them:

1. **Two connector pairs must sit at the same X,Y on two boards.** `J307`↔`J407` (PWR-LOGIC) and
   `J308`↔`J406` (STACK) mate straight down between OUTPUTS and LOGIC. Place one, and the other's
   position is fixed — the stack is only as aligned as those two footprints.
2. **Two keep-outs cross boards.** `J311` and `J312` hang 10.9 / 8.6 mm under OUTPUTS into the
   30 mm gap, so nothing on POWER taller than 18.1 / 20.4 mm may sit beneath them — which is where
   POWER's 22 mm chokes and 18.5 mm bulk caps want to be.
3. **The connector face is one edge of the box** (IO-6). Every board's harness row sits on the
   same Y = 0 edge, in the order `edge_budget` fixes, and the cable halves (`J202`↔`J311`,
   `J105`↔`J312`) should be near each other in X so the looms run straight.

So the order is **OUTPUTS → LOGIC → POWER**: OUTPUTS holds both mated pairs' lower halves and both
hanging connectors, so it fixes the most; LOGIC then inherits two positions; POWER then inherits
two keep-outs and two loom targets.

## The frame

Board coordinates in **mm from the bottom-left corner**: X along the 242 mm length, Y across the
41.84 mm width, **Y = 0 is the connector face**, +Y toward the back edge. The `.epcb2` stores mils
(1 mm = 39.3701 mil) with the outline at (0,0)–(9527.56, 1647.24) — so the same frame, scaled. The
imported parts sit at negative Y (dumped below the outline by the editor); the tool moves every one
of them onto the board.

## The placement logic — five bands, derived from the copper

Every board is a **filter**: signals enter at the face on screw terminals, pass through their
protection, reach their driver or reader, and leave DOWN or UP through an inter-board connector.
The tool lays each board out as bands across its width, front to back, and fills each band by
**net adjacency** — a part goes next to the part it shares the most nets with, nearest the
terminal its signals enter on.

| Band | Y (mm) | Holds | Rule |
|---|---|---|---|
| **1 · face** | 0 – 9.2 | the harness row | fixed order from `edge_budget`, 1 mm gaps, centred in the 242 less 2 × 3.5 M3 inset; the 3.50 mm row (`J314`) on the underside of OUTPUTS shares the face |
| **2 · protection** | 9.2 – 19 | each terminal's TVS, series R, pull-ups, clamps | directly behind ITS terminal — the TVS first, cathode toward the face |
| **3 · function** | 19 – 30 | drivers, switches, expanders, the buck | over the terminals they serve; a chip with no terminal (expander #2, the CAN transceiver) goes where its bus is shortest |
| **4 · brain / power** | 30 – 41.84 | the S3, the converters' control, the inter-board connector footprints | the S3's antenna end at the back edge; `STACK`/`PWR-LOGIC` under Bands 3–4 where their signals originate |
| **under** | bottom layer | the 7 bottom parts | `U201`/`U202` seated per `FLOOR_SEAT`; `J314` at the face; `J311`/`J312` under OUTPUTS where the looms land; `J406`/`J407` at the mates' X,Y |

**Adjacency scoring** (`tools/place.py`): for each unplaced part, the candidate position is the
centroid of the already-placed parts it shares nets with, weighted by pin count, pushed to the
nearest free courtyard in its band. Ties break toward the face. It is a greedy first-fit — good
enough to be *reviewed*, and honest about being a proposal, not an optimum.

## What the tool checks after placing — and refuses on

A placement the tool writes has passed every one of these, or it does not write:

- **Inside the outline**, clear of the four M3 corners (3.5 mm inset) by its courtyard.
- **No two courtyards overlap** on the same face.
- **Every bottom-side part is on layer 2** and every other on layer 1 — the seven, by name.
- **The mated pairs coincide**: `J407`'s X,Y on LOGIC equals `J307`'s on OUTPUTS; `J406` equals
  `J308`. (Mirroring is in the footprint; the position is the same.)
- **The cross-board keep-outs hold**: nothing on POWER's top taller than the limit stands under
  `J311`'s or `J312`'s footprint as placed on OUTPUTS.
- **The row is at the face**, in order, no header past the board end.
- **HV on POWER**: every part on an 84 V net (the HV class) sits ≥ 3 mm from the board edge and
  ≥ 1.25 mm courtyard-to-courtyard from any part on a low-voltage net — a *placement* proxy for the
  routing rule the owner sets up in the editor.
- **The S3's antenna end** (`U401`, the `-1U`) is within 2 mm of the back edge with no part in the
  8 mm × 18 mm zone beyond it.
- **Nothing on a face stands taller than that face's gap** (`layer_gaps`) — the height model, applied
  per part where it stands.

**And because the board must be routed afterwards (owner, 2026-09-22), seven more — placement
decides whether routing is possible:**

- **Routing channels, not just courtyards.** 2.0 mm clear between Bands 1–2 and 2–3, 3.0 mm between
  3–4 (the S3's 25 signals fan out there); within a band, part-to-part clearance is courtyard
  + 0.6 mm — one 0.2 mm trace with its clearance each side. Named constants; each says what it holds.
- **The 12 V bus is a LINE.** `V12` fans from `J311`'s one contact to 28 pins carrying **11.39 A at
  the limiters**. The three `TPS4H160B`s and `U305` sit in a line along X with `VS` pins facing the
  same way and `J311` under its middle, so `V12` is one straight pour, not a tree. Check: the
  V12-bearing ICs' centroid within 15 mm of `J311`'s X.
- **Ground is a plane** (152 pins on OUTPUTS, 108 LOGIC, 58 POWER — never traces; inner layer 2).
  Placement must not split it: no THT connector over 40 mm long with its axis across the board's
  short dimension. `J308`/`J406` (2×29, 73.66 mm) go at an edge region, along X.
- **HV on POWER is a REGION.** All 14 HV-net parts in one contiguous blob at `J101`'s end, a 3 mm
  clear strip between it and every low-voltage part; no LV part inside it. Check: the region's box
  overlaps no LV courtyard + 1.25 mm.
- **Pairs and sense lines are SHORT.** `U404` within 10 mm of `J406`'s CAN contacts; the brake-lever
  nets `J306` → `U401` straight and away from the I²C pull-ups; `R476`/`C437` (the `KEY_SENSE` ADC
  filter) within 5 mm of `U401`.
- **Every decoupler on its IC.** A 100 nF whose non-GND net is a rail sits within 3 mm of the
  nearest IC power pin on that rail — pairing derived from the netlist, checked.
- **`J408` reachable**: on top, no part within 5 mm on the cable's entry side.

The adjacency scoring weights rail nets by what they carry — `V12` pins ×10, HV nets ×10, GND ×0 (it
is a plane and pulls nothing) — so the bus line, the HV region and the decoupler proximity fall out
of the flow rather than being bolted on.

## The loop — repeatable

```
tools/place.py --stack                 # place OUTPUTS, LOGIC, POWER in that order; check; write
                                       #   → ~/Documents/EasyEDA-Pro/projects/revv1-module.eprj2
owner opens it, looks, closes the editor
tools/place.py --check                 # re-read the SAVED file; report every rule above
tools/place.py --stack --keep J302 J305 # re-place, holding the owner's hand-moved parts fixed
```

- `--stack` reads the saved `.eprj2` (the owner's file — so hand-moved parts are known), places
  every part **not in `--keep`**, checks, and writes back. ⛔ It refuses if the editor is open.
- `--check` never writes. It is the review step and the regression test: after the owner moves
  things by hand, `--check` says what broke.
- `--keep` is how revision works: the owner fixes a part where they want it; the tool re-flows
  everything else around it. Repeat until the owner is satisfied.
- **Every write goes through the same round trip the build uses** (`eprj2.read` → edit →
  `eprj2.write` → re-read identical), and the tool refuses to write if the re-read differs.
- The write is to the owner's file **only** — it is placement, not generation, so the no-clobber
  guard (`_is_generated`) is bypassed deliberately and the tool says so; it keeps the previous
  file as `.eprj2.prev` for one step of undo.

## What the tool does NOT do

Route — **Part 2 says what it does instead**: derive the rules, write them into the project, check
the result. Judge aesthetics. See silkscreen. Know where the harness enters the box (that biases which
end the row sits toward — an `--anchor left|right` flag, default centred). Those are the owner's,
and the loop above is how the owner's judgement re-enters the process without losing what the
tool derived.

## Files

- `tools/place.py` — the tool. Stdlib only.
- `tests/test_place.py` — every check above proven to fire on a placement that breaks it, and the
  round trip proven lossless on a real saved project.
- `layout/PROCESS.md` — this document. `layout/<BOARD>-placement.md` — the per-board rationale
  the tool prints, regenerated each run (the LOGIC one written by hand on 2026-09-22 is the seed).

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
