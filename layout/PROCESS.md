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

1. **Three connector pairs must sit at the same X,Y on two boards.** `J307`↔`J407` (PWR-LOGIC) and
   `J308`↔`J406` (STACK) mate straight down between OUTPUTS and LOGIC, and `J411`↔`J501`
   (CTRL-STACK) between LOGIC and CTRL. Place one half, and the other's position is fixed — the
   stack is only as aligned as those footprints. The tool takes the list from the gap each pair
   sets (`board_params.layer_gaps`), never from a table of refdes.
2. **A keep-out crosses boards.** `J311` hangs 10.9 mm under OUTPUTS into the 30 mm gap, so nothing
   on POWER taller than 18.1 mm may sit beneath it — which is where POWER's 22 mm chokes and
   18.5 mm bulk caps want to be.
3. **The connector face is one edge of the box** (IO-6). Every board's harness row sits on the
   same edge, in the order `edge_budget` fixes, and the loom's two halves (`J202`↔`J311`) should be
   near each other along the board so it runs straight.

So the order is **OUTPUTS → LOGIC → CTRL → POWER** (`place.PLACE_ORDER`): OUTPUTS holds two lower
halves and the hanging loom connector, so it fixes the most; LOGIC then inherits two positions and
chooses the third pair's; CTRL inherits that one; POWER inherits the keep-out and the loom target.

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
| **4 · brain / power** | 30 | the S3, its LDO and supervisor, the CAN transceiver, every inter-board connector footprint | the S3's antenna end at the back edge — a FLOOR on where it may stand, not a preference; every pair's LOWER half flush to the back edge; every UPPER half at its mate's X,Y |
| **under** | — | the 6 bottom parts, by the netlist's `side` | `U201`/`U202` with the HV group, turned so their low-voltage pins face the low-voltage end; `J311` in the slot the V12 driver line leaves for it — its pins may not come up inside a driver's body (check 17); `J406`/`J407`/`J501` at the mates' X,Y |

**CTRL's bands are the same four**, with no module and no bus on it: band 1 is the face row
`J309 J404 J310 J405 J314` in `edge_budget` order (the FarDriver leads on 5.08 mm Kangnex, then the
5 V terminal on 3.50 mm Kefa); band 2 each terminal's TVS, series resistor and clamp directly
behind its own terminal, including the four `SMF6.0A` behind `J314`; band 3 the 5 V block — the
buck `U305` with `L301` and its input and output caps, and the four `TPS2553` — behind `J314`'s end
of the row; band 4 the `CTRL-STACK` pair's upper half `J501`, hanging **under** the board at the
back edge, exactly over `J411` on LOGIC's top face. The pair's position is chosen ONCE, on LOGIC,
and CTRL inherits it.

⚠️ **`J411` and the S3 share LOGIC's back edge side by side.** The socket is 56.28 mm of a 242 mm
edge and **the module is seated first** (the clustering objective, above): `U401`'s antenna rule is
a floor on its position rather than a cost, so the adjacency cannot buy the module out of the back
edge to shorten a trace, and the half that is free to choose is the one that yields.

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
follow it**, because a host that drops into a hole exactly its own size pushes its satellite across
the board — that is how `U406`, walled in by `U405`, the channel in front of it and `J406`'s
through-hole pads behind, left its 100 nF 8.6 mm away and failed check 15 while every other check
passed. The engine offers the host **only** positions with room beside them while any such
position exists on the board, and falls back to charging `SATELLITE_ROOM` (10 mm of its own travel)
when none does, so the check still reports rather than the part going unplaced. ⛔ The room it
looks for is the satellite's **real plan at each quarter turn**, and any of them fitting is room:
it used to be `min(w)` and `min(d)` taken across the turns independently — for a 2.0 × 1.25 mm chip
a 1.25 × 1.25 mm rectangle the part has at no angle — so a pocket 1 mm too narrow in every
orientation read as free and the host paid nothing (`C436` beside `U406`, 2026-09-22).

**Each rule in turn, strongest first.** A position has to satisfy every binding rule the part
carries — the antenna floor, the room its satellite needs, the 84 V group it must touch — and the
engine drops them one at a time only when nothing on the board satisfies them. It never trades one
away for a shorter trace while a legal position exists, and whatever it did have to drop, the
checks then report.

**Adjacency scoring:** the candidate `u` is the pin-weighted centroid of the already-placed pins
the part connects to — GND weighs 0 (it is a plane), pack-voltage nets and the 12 V bus weigh 10
(wide copper, kept short), other rails 0.2, a signal 1 per pin — then the nearest free slot by a
shelf scan with the clearances below. Among the four quarter turns, the one whose pins land nearest
their partners wins (that is what tells 0 from 180 on a symmetric body). It is a greedy first-fit
— good enough to be *reviewed*, and honest about being a proposal, not an optimum.

### ⭐ Cluster by circuit — the objective above adjacency (`place.Placer.circuit_u`)

Owner, 2026-09-22, looking at the four placed boards: *routing all four will be extremely
difficult.* Congestion was not the reason — the worst 1 mm cut filled 24 % of two signal layers on
LOGIC and less everywhere else — **the net LENGTHS were**. Bands put a part in the right strip;
plain adjacency did not put it near the parts it belongs with, because it counts every partner on
every net and **the rails win**: `V12` weighs 10 a pin and lands on every driver, so the three
`TPS4H160B` were pulled onto the contact that feeds them and stood in one line in the middle of
OUTPUTS while the terminals they drive were at the ends of the row. `AUX12V_3` ran **121 mm**;
`R362`, whose whole job is to sit on `J313`'s channel, stood **119 mm** from it.

So a part's u is decided by **what it serves**, with the rails DROPPED rather than discounted —
where a part's power comes from says nothing about which circuit it belongs to. Two halves:

- **A HOST** — an IC, the module, a converter — stands at the u-centroid of the **connectors it
  serves**: the connectors on its own signal nets, and where a signal net reaches none, the ones one
  hop away through a **series** passive (a part with exactly two nets), which is how an expander
  reaches the input terminals it reads. Each contact is weighted by the width of the copper its net
  needs (the R0 class table below): a `CH12` channel counts 5 and a `CH5` 4 against a signal's 1, so
  a driver is pulled by the four channels it drives and only nudged by the nine control lines it
  shares with the `STACK` socket. That is "each `TPS4H160B` behind the terminals its channels feed",
  "each `TPS2553` behind `J314`", "each expander behind the input terminals it reads" and "the S3 at
  the centroid of what it talks to" — one rule, not four.
- **A PASSIVE** stands at the weighted centroid of everything already placed on its **signal** nets.
  It is a link in a chain and belongs BETWEEN the two things it links. ⚠️ Pinning it to the
  connector instead drags the other end: the `AUX5V_n_EN` series resistors sat on `J501`'s contacts
  with their switch 82 mm away.

**The programming land is the module's satellite** — `EN`, `BOOT_IO0` and the two UART0 lines are
the S3's own pins (D25), so `J408` follows the module wherever the clustering puts it (check 20b).

⛔ **The objective does NOT steer POWER's 84 V parts.** They are placed as a REGION and checks 13,
18 and 19 already answer "where does this part belong"; a second objective pulled them out of the
blob toward the signal partners they link and split the region in two.

⚠️ **The module is seated between a pair's inherited UPPER halves and its free LOWER ones.** An
upper half's position comes from the board below and cannot move; a lower half chooses its own u;
the module is the host every signal on LOGIC clusters around. Seated after the lowers it found the
back edge full — `J406` u 21.9…90.5, `J411` 91.7…148, `J407` 103…139 — and its antenna floor makes
it 25.5 mm deep on a 41.84 mm board, so the only position left was u 149.6, and every `LGT_*`
command ran 127–145 mm. The thing everything clusters around chooses **before** the things that
cluster around it.

**POWER places its 84 V parts first**, as one group: the bulk (bricks under the board, chokes,
cans, the fuse clip) packs against the end `J101` stands at, and the HV passives fill the gaps; the
low-voltage parts then take the rest of the board. Three of them have a u of their own instead,
and check 19 below says why: the row-blocking brick, seated against the partition before the pack,
and each brick's input bulk cap, aimed at its own brick's pack-voltage pins. ⚠️ The bulk's front is the **board's own edge**,
not the row's depth: it is a REGION, not a band, and `J101` is only 56 mm of the 242, so charging
the bulk for standing in front of the row leaves the strip beside `J101` empty and pushes the
region 15 mm further along the board — length the low-voltage end needs. And each 84 V part lands
within `HV_STRIP` of one already down, so the region is contiguous by construction rather than by
luck in the packing order (check 13).

If a board cannot seat every part at the engine's 3 mm HV strip, it is placed again with the strip
at the check's 1.25 mm floor and says so — the built-in revision. POWER has a second: the
partition below is **measured on a first pass and used on a second**, and the second pass can find
that measure wrong in either direction. If holding the low-voltage parts out costs the 84 V parts
room they used to borrow, the 84 V end is grown by the length those parts pack into; if instead
they pack short of the end reserved for them — leaving the row-blocking brick standing off its own
bulk, which is a hole in the region and length the low-voltage end could have had — the line is
pulled in by the slack. Either way the board is placed again, up to `PARTITION_GROWTHS` times
between them, and the note says which happened.

## The two rules IO-26 decided (3a and 4a)

**(3a) The driver line leaves a slot for the loom's pins.** `J311` hangs under OUTPUTS and its four
through-hole pins come up through the top face, where the `V12` drivers are. So the loom's contact
is seated FIRST, in the middle of the driver line — at the mean of the u's the drivers' own signals
ask for, which is the middle of the terminals they serve — and the drivers then pack around it. The
slot is the feed's own pad row plus `DRIVER_SLOT_MARGIN` (= `CLEAR`) at each end, derived from the
footprint and never typed, and the drivers keep off it through the ordinary rule that a
through-hole pad is copper on **both** faces (check 17): nothing else has to be told about it.
What it protects is an **11.39 A** feed entering the layer-3 pour **where the load is**; fed from
the end of the line instead, the whole bus current runs the length of every driver before it
reaches the last one. Check 11 says so.

⭐ **Amended 2026-09-22 by the clustering objective: the gap is now "inside the POUR's span".**
3a was written when the drivers stood in one line and the gap was a hole in that line. Clustering
spreads them behind the terminals they feed — they span 122 mm of OUTPUTS — and what carries the
bus between them is the **layer-3 `V12` pour** (R1 below), which the amended check 11 makes
**mandatory**: the pour's u-extent covers every driver's `VS` pads, and `J311`'s pin row comes up
INSIDE that span with a driver on each side of the slot. 3a's intent is unchanged and its wording
is the only thing that moved — the feed enters the pour **where the load is**, not off its end.
⚠️ The feed's u is still the mean of the drivers' own SIGNAL centroids, deliberately and not the
clustering objective's targets: the two answers sit 20 mm apart (u 119.3 against 99.9) with no
electrical difference — the feed's pads barely move a pour whose length the drivers set — but
`J311` hangs into the 30 mm gap and nothing on POWER's top taller than 18.1 mm may stand under it
(check 5), so the feed's u decides where POWER's 22 mm chokes and 18.5 mm cans pack.

**(4a) POWER is partitioned along its length:** 84 V end · `HV_STRIP` (3 mm) · low-voltage end.

- **The line is derived, not typed.** It is where the 84 V parts' own lengths end — the far edge of
  every part that carries pack voltage and nothing else, and the far edge of the pack-voltage
  **pads** of a part that straddles, since a brick's output end is 12 or 5 V and belongs on the
  other side. `place.hv_partition` computes it from the placement, so `--check` on a saved file
  derives the same line the engine built to. It is capped by what the low-voltage parts need: their
  own shelf pack plus the M3 washer square at the far corner, or they are the ones with nowhere to
  go.
- **`J101` sits at the face of the 84 V end**, so POWER's row is anchored to one end rather than
  centred; `--anchor right` puts the 84 V end at the far end instead.
- **No low-voltage body enters the 84 V end, and no 84 V body enters the low-voltage end**, so a
  low-voltage part cannot be enclosed by pack voltage — it is never among it. The one exception is
  a straddler's own satellite (a brick's 100 nF), which belongs against that brick's low-voltage
  pads; check 13 still asks that it not be walled in.
- **A straddler is turned with its low-voltage pins toward the low-voltage end** — which fixes both
  bricks' orientation as a constraint, not a choice. The quarter turns that face it the other way
  are refused, not outbid.

⚠️ **What 4a asks for and the board cannot give:** "a straddling part has its 84 V pads in the 84 V
end and its low-voltage pads in the low-voltage end" holds for **one** brick at a time, not both.
`U201` is 58.3 × 37.2 mm and `U202` 50.8 × 25.4 on a 41.84 mm board, so they cannot share u
(37.2 + 25.4 = 62.6 mm of depth) and stand end to end; a single line can pass through only one of
the two intervals. The part of the rule that binds both is therefore the ORIENTATION, which is
what decision 4a itself names, and the consequence to watch in routing is that the brick further in
feeds its output caps across the partition.

## What the tool checks after placing — and refuses on

A placement the tool writes has passed every one of these **and has every part placed**, or it does
not write: a part with nowhere to go is reported by refdes with the reason it had none, and is never
squeezed somewhere illegal. Each check is numbered in the tool's output, every constant in
`place.py` says what it protects, and `tests/test_place.py` proves each check fires on a placement
that breaks it. The first nine are the placement's own; **checks 10–16 exist because the board must
be routed afterwards (owner, 2026-09-22) — placement decides whether routing is possible**; check 17
is the board itself, which has two faces and one set of holes; check 18 is IO-26's partition,
check 19 the order inside it, and check 20 asks of the NETS what 10–16 ask of the board.

📄 **Where the two rules IO-26 decided live:** (3a), the slot the driver line leaves for the loom's
pins, is **folded into check 11** — the bus is a line AND the feed enters it from inside, which is
the same sentence about the same 11.39 A pour, and a separate number would have let one pass while
the other failed. (4a), POWER's partition, is **check 18**, a new one: check 13 says something
else and stays as the backstop — 18 is about the CONSTRUCTION, 13 about whether any part ended up
walled in by pack voltage whatever the construction believed.

1. **Inside the outline**, clear of the four M3 corners: a 7 × 7 mm washer square at each hole
   centre, read from the file.
2. **Same-face clearance**: 1.6 mm body to body — 0.5 mm courtyard each (`board_fit.COURTYARD`)
   plus 0.6 mm for one 0.2 mm trace with 0.2 mm each side, JLC's 4-layer capability, so a trace
   can pass between any two neighbours. Two harness headers in the row keep `edge_budget`'s 1 mm:
   no trace passes between flanges.
3. **Every bottom-side part on layer 2** and every other on layer 1 — the set comes from the
   netlist's `side`, not from a list: `U201 U202 J311 J406 J407 J501` today.
4. **The mated pairs coincide**: `J407` over `J307`, `J406` over `J308`, `J501` over `J411`, X,Y
   within 0.01 mm — and **pin for pin by net**: every contact of the lower half has the upper
   half's contact at the same place carrying the same net. The upper half's angle is found the same
   way: the quarter turn at which its pre-mirrored footprint lands its nets on its mate's (180 from
   `J308`'s, in the file). The list of pairs is derived from the gap each one sets, so a pair added
   to the netlist is checked without a line being written here.
5. **The cross-board keep-outs hold**: nothing on POWER's top taller than the limit stands under
   what hangs beneath OUTPUTS as placed there (`J311` today); the limit is the gap less the
   connector's height less `CLEARANCE`, from `board_params`.
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
   nothing in the 8 × 18 mm zone beyond it on either face. ⚠️ The engine treats this as a FLOOR on
   where the module may stand rather than a cost: `J411` is 56.28 mm of the same back edge, and a
   preference the adjacency could outbid left the antenna 7.3 mm short of it (2026-09-22).
9. **Nothing on a face taller than that face's gap** (`layer_gaps`).
10. **Channels**: 2 mm between bands, 3 mm to or from Band 4 (the S3's 25 STACK signals fan out
    there), wherever one band's part stands directly behind another's.
11. **The 12 V POUR on OUTPUTS** (amended 2026-09-22 for the clustering objective). Until the
    drivers were clustered this asked that their centroid stand within **15 mm** of the contact
    that feeds them — a trace-era figure, and the one that FORCED the single mid-board driver line
    the owner could not route out of. Clustering spreads the drivers along the board and the
    layer-3 pour IS the bus (R1), so the pour is what is measured. It is **mandatory**: a placement
    with no pour under the line has no bus. Four clauses —
    - **every V12 IC faces one way**: one pour, one orientation, so every `VS` pad row presents to
      the same edge of it;
    - **every driver's `VS` pads are ON the pour.** The pour is a strip under the line: its
      u-extent runs from the first driver's `VS` pads to the last with the feed's own contacts in
      it, and its v-band is the strip the driver **nearest the feed** stands in. A driver pushed
      off the line needs a neck to the pour instead of vias into it;
    - **the feed's pin row stands INSIDE the pour's span, with a driver on each side of the slot**
      it leaves (IO-26 3a, unchanged in substance): the 11.39 A enters where the load is, not off
      the end. The slot is the pad row plus `DRIVER_SLOT_MARGIN` each side, and it is what settles
      the pull against check 17;
    - **the pour is no longer than `V12_POUR_MM` (178 mm)** — the drop the copper allows, and what
      replaces the 15 mm. 11.39 A (the LIMITED case) through a 20 mm × 35 µm pour is 0.493 mΩ per
      20 mm, so 5.61 mV per 20 mm, and a 50 mV budget — 0.42 % of the 12 V rail — buys 178 mm. The
      clustered placement measures **122.5 mm**; a driver at each end of the board scores 221.

    Which ICs and which contact come from the copper: the net `U201`'s `+V` is on, and the FEED is
    the connector whose other half stands on the board the 12 V comes from (several carry `V12`
    away since IO-26). Which pads are `VS` is read off the copper too, never off TI's pin name.
    ⛔ The 178 mm is the DROP, not the channel lengths: check 20(a) is what keeps a channel short.
12. **The ground plane** (139 ground pins on LOGIC, 100 CTRL, 92 OUTPUTS, 30 POWER — never traces): no through-hole
    connector longer than 40 mm laid across the board's short axis. `J308`/`J406` (2 × 29, 73.66 mm)
    lie along the board, flush to the back edge, where a row of holes cuts a plane least.
13. **The HV region on POWER — the BACKSTOP**: the 84 V parts form **one group** (each within 3 mm
    of another), and **no LV part is enclosed** by 84 V copper on all four sides. "Inside" means
    the part's traces could not leave without crossing pack voltage; copper on three sides is a bay
    with a way out. Since IO-26 4a the partition should make both impossible, and this is what says
    so if it did not: ⛔ it must never fire on POWER again.
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
    passing all 16 of the checks above (2026-09-22): a 24-way ribbon header's pins inside `J308`'s
    58, `J311`'s inside `U301`/`U302`, `J314`'s inside `J303`, `J406`'s inside the S3, and both
    bricks' inside the through-hole parts on POWER's top face.
18. **POWER's HV/LV partition** (IO-26 4a): the board is 84 V end, `HV_STRIP`, low-voltage end
    along its length. **No low-voltage part stands in the 84 V end**, and **a part that straddles
    is turned with its low-voltage pins toward the low-voltage end**, measured at each pin group's
    centroid so a part whose pins interleave is still judged by which way it faces. The line is
    derived from the 84 V parts' own lengths (`place.hv_partition`), so `--check` on a saved file
    derives the line the board was built to. The one part allowed in the 84 V end is a straddler's
    own satellite — a brick's 100 nF, which belongs against that brick's low-voltage pads; check 13
    still asks that it not be walled in.
19. **The heavy path on POWER** — the ORDER inside the 84 V end, which 18 says nothing about. Two
    placements can both pass 18 and put the brick's 12 V output 24 mm from the connector the
    **8.47 A** leaves by or 104 mm from it, threaded past the chokes, the fuse clip and both bulk
    cans; the one this repo shipped on 2026-09-22 was the second. So: **the row-blocking brick**
    (`board_fit.row_blockers` — the underside body too deep to sit behind the face row, `U201`) is
    **the last body in the 84 V end**, its 12 V pins at the strip, which is the one arrangement
    where 4a's own sentence holds literally — its 84 V pads in the 84 V end, its low-voltage pads
    in the low-voltage end. **The 12 V output's own parts are the low-voltage end's first
    tenants** (`place.v12_output`, from the PWR12 net, largest body first: `C207` then `J202`),
    so the brick's `+V` → the bulk cap → the contact is one short run, measured at
    `HEAVY_PATH_MM` (25 mm; 23.65 as placed, and the arithmetic is in the constant). ⛔ **This
    overrides the loom's own target for `J202`**: the cable is five flying conductors in a 30 mm
    gap and can run at an angle, an 8.47 A pour cannot. And **each brick's input bulk cap stands
    at its pack-voltage pins** — `BULK_REACH` (9 mm), the brick's own body discounted because a
    through-hole pad may not come up inside a case on the other face (check 17), which is what
    lets one figure hold `C201` at `U201`'s pins (2.70 mm) and `C202` round `U202`'s 50.8 mm case
    (8.03 mm). Which cap belongs to which brick is read off the nets (`HV_C1_*` against
    `HV_C2_*`), never off a name. The engine seats them in that order — brick, its bulk, the 84 V
    pack, then the 12 V output — and the 84 V end is measured **without** the brick and its own
    length added, so the line is where the rest of the region packs to. ⚠️ A greedy packer
    re-flows when the brick moves, so when the region ends up short of the end reserved for it the
    board is placed again with the line pulled in (`PARTITION_GROWTHS`, the mirror of the growth
    revision) — and check 13 stays the backstop that reports a region still in two pieces.
20. ⭐ **ROUTABILITY, per board** (owner, 2026-09-22: routing all four boards will be extremely
    difficult). Checks 10–16 ask whether the BOARD can be routed; this asks it of the **NETS**, and
    it is the measurement that finding was made with, moved inside the tool. **Its figures are
    reported on every run, passing or failing** — the point is that the number is visible.

    Measured over every net that is copper the placement leaves to be THREADED: the ground plane
    and the rails are out (layer 2 is GND on all four boards and layer 3 a pour or a second ground,
    R1; the rails that get neither are R0's wide traces, laid by hand in R2 before the autorouter
    runs). Three figures per board: the **u-span** of each net, the **star length** — each net's
    pins to their own centroid, summed, the MST proxy — and the **worst 1 mm cut** in each axis.

    - **(a) a net's u-span against its class's reach.** One budget shape: **the connector's own
      u-extent plus a reach**, because which contact of a header a net lands on is the pinout's
      choice, not the placement's. A **CHANNEL** — a `TPS4H160B` `OUTx` or a `TPS2553` `OUT` and
      everything on it — gets `CHANNEL_REACH` (40 mm); a **SIGNAL** that ends at a harness terminal
      gets `SIGNAL_REACH` (16 mm). Both figures are derived from this design: the clustered
      placement needs 36.2 and 12.0 mm of them, and the placement before it ran nine channels and
      seven signals long, the narrowest by 40.8 and 19.5. ⚠️ The channel band is only (36.2, 40.8]
      wide, and the narrowness is the finding: `U301` feeds `J301` at one end of the row and
      `AUX12` on `J304`/`J305` at the other and cannot be near both. The next part that does that
      wants two drivers, not a bigger number.

      Six kinds of net are **reported and not bound**, each because another rule owns it: a
      **RAIL** (not measured at all), a **SENSE** net on the module (check 14), POWER's **pack
      voltage** (checks 7, 13, 18, 19), a net on a **straddler** of POWER's partition (4a puts its
      two ends in two different halves of the board), a **face-row** net that lands on two
      terminals (the row's order is `edge_budget`'s), a **BUS** on two or more hosts (`EN` is every
      expander's RESET since IO-22; its span says where the expanders are), a net on an
      **inter-board half** — that half lies flush to the back edge (check 12) where the module's
      antenna must also be (check 8), and on LOGIC those three halves and the module want 180 mm of
      a 228 mm strip with two of the three fixed on the board below — and a net on the
      **programming land**, which 20(b) owns. ⛔ An exemption is a claim about **who owns the
      net**, not a way to pass.
    - **(b) the programming land within `PROG_REACH` (25 mm) of the module**, pin to pin on the
      nets they share. `EN`, `BOOT_IO0` and the two UART0 lines are the S3's OWN pins (D25). The
      clustered placement measures 21.4 mm; the one before it 38.4.
    - **(c) the worst 1 mm cut under `CUT_LOAD` (50 %)** of what two signal layers hold at
      `TRACK_PITCH` (0.4 mm — a 0.2 mm trace with 0.2 mm of clearance, JLC's 4-layer capability),
      which on a 41.84 mm board is 209 tracks across and 1210 along. It is a **BACKSTOP**: the four
      boards fill 4 % (POWER), 11 % (CTRL), 12 % (OUTPUTS) and 21 % (LOGIC) today, so congestion is
      not what makes this stack hard to route — the lengths are.

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
tools/place.py --stack --draw pics/    # place OUTPUTS, LOGIC, CTRL, POWER in that order; check; write
                                       #   → ~/Documents/EasyEDA-Pro/projects/revv1-module.eprj2
READ THE ROUTABILITY BLOCK             # ✔ a required step: check 20's star length, three longest
                                       #   spans and worst cut, printed under each board
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
- **`--board CTRL [BOARD …]` writes only the named boards' PCB documents** — every other board's
  records are left exactly as saved, and only the named boards' failed checks and unplaced parts
  refuse the write — while all four are still placed in memory, because LOGIC's mates sit at
  OUTPUTS' `J307`/`J308` and CTRL's at LOGIC's `J411`.
- `--check` never writes. It is the review step and the regression test: after the owner moves
  things by hand, `--check` says what broke.
- ✔ **Check 20's figures are printed under every board on every `--stack` and `--check`, and
  written into `layout/<BOARD>-placement.md`** — the star length, the three longest spans with the
  limit each one answers to, and the worst 1 mm cut in each axis. **Reading them is a step of the
  process**, not a decoration: the owner read this stack as hard to route off numbers like these
  while all nineteen checks were green, which is what check 20 exists to stop happening again.
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
  owner's is committed. ⚠️ Its footprints are a MODEL and a generous one: fewer pins cross the
  board there than really do, and the bodies are the netlist's rectangles rather than the library's
  land patterns, so a placement it calls legal can still be tight on the owner's. Run the tool on
  the real project as well, and look at the pictures; `REVV1_PLACE_PROJECT=/path/to/saved.eprj2 pytest tests/test_place.py`
  runs the same tests on a real save.
- `layout/PROCESS.md` — this document. `layout/<BOARD>-placement.md` — check 20's routability
  block and then the per-board table (`u`, `v`, angle, file X, Y, layer, band, and the reason:
  "face row, position 3 of 5" / "behind J313, J308 — the connectors it serves" / "between U303,
  J313 — the signal partners it links" / "fixed: mate of J308"), regenerated on every `--stack`.

---

# Part 2 — Routing

Owner, 2026-09-22: *"after placement, we will need to route the traces"*, *"the routing process
should be included in our layout process"* and, after autorouting POWER, *"can't you also do the
routing?"* Placement decides whether routing is possible; routing decides whether the board works.
The two are one process, and the placement rules in Part 1 (the channels, the bus line, the HV
region, the ground plane) exist **for** this part.

The answer to the third question is: **the rule-driven copper, yes.** An 8.47 A bus, a 1.25 mm
pack-voltage chain and a 1.55 A channel each have one shape, and a tool can derive it, write it and
check it. The ~250 signal nets are the editor's autorouter's job — **once the rules and the planes
exist**, which is what the autoroute of 2026-09-22 did not have.

## The loop, complete

```
tools/place.py  --stack                  # placement (Part 1) → the .eprj2
tools/route.py  --rules                  # R0: the classes into every PCB document
tools/route.py  --pours                  # R1: the planes, cut back at POWER's partition
tools/route.py  --heavy                  # R2: the copper whose shape the rules decide
tools/route.py  --draw pics/             # ✔ LOOK AT IT
owner: in the editor — check the pours fill, lock R2's copper, autoroute the rest, save
tools/place.py  --check                  # placement still legal after the owner moved things
tools/route.py  --check-routing          # R3 — this is the gate
owner: export ×4 → tel_check ×4 → editor DRC with the class rules on
```

`--check-routing` and `--check` never write; run them after every save. Everything that writes
**refuses while EasyEDA Pro is open**, keeps the previous file as `.eprj2.prev`, and re-reads the
result record for record before it says "written". There is deliberately **no `--route`**: the tool
derives, writes what the rules determine, and checks; the threading is the editor's and the
judgement is the owner's.

## What the tool does, and what it does not

It **derives** every number routing needs from the netlist — which nets carry current and how much
(`power_budget`), which sit at pack voltage (`layout_rules.hv_nets`), which are a pair, which are a
plane. It **writes** those as net classes and design rules into the project, as copper regions, and
as the runs whose width and path the rules decide. It **checks** a saved file against the same
derivation, so a class the owner forgot to set up is still caught.

It does **not** thread signals, judge aesthetics, or place a via. ⛔ And it never routes **round**
an obstacle: a run it cannot draw straight is **refused by name**, because a bus that wanders is a
bus whose length nobody derived.

## Step R0 — the rules go in before the first trace (`tools/route.py --rules`)

⛔ The editor's board-wide default is **0.2 mm / 0.2 mm** — good for logic, fatal for power, and it
is what the JLCPCB capability template gives every net. These override it per class. **Membership
is derived from the copper on every run**, never from a net's name, so a renamed or added net is
never in the wrong class.

| Class | Nets — where they come from | Width | Clearance | Why — the number it protects |
|---|---|---|---|---|
| **HV** | `layout_rules.hv_nets(d, board)` — 14 on POWER | 0.5 mm | **1.25 mm** | IPC-2221B B2 for the 160 V do-not-exceed. The clearance is `layout_rules.HV_CLEARANCE_MM` itself, the same figure check 7 uses as a placement proxy — not a second copy. The width is a FLOOR, not a current: the HV nets carry 1.93 A at the 60 V LVC, which 0.5 mm takes easily |
| **PWR12** | `place.power_classes()["PWR12"]` — the net `U201`'s `+V` is on — **and only on a board that carries the bus** | **≥ 5.0 mm**, or a **pour** | 0.3 mm | **11.39 A**, the LIMITED case (`power_budget.limit_case`), not the 8.47 A nominal: the copper survives every limiter at its ceiling at once. IPC-2152, external 1 oz, 20 °C rise |
| **PWR5AUX** | the buck's `SW` net and its inductor's | 2.0 mm | 0.3 mm | 4 × 1.39 A = 5.6 A at the four `TPS2553` limiters |
| **CH12** | a net on a `TPS4H160B` `OUTx` | 1.0 mm | 0.25 mm | 1.55 A per channel at its limiter (`R359` = 1k5) |
| **CH5** | a net on a `TPS2553` `OUT` | 0.8 mm | 0.25 mm | 1.39 A |
| **DIFF** | the nets on a transceiver's own `CANH`/`CANL` **pins** | 0.25 mm | 0.4 mm | the run is electrically short (< 150 mm), so pairing and skew are the constraint and 120 Ω is not |
| **SENSE** | a `TPS4H160B` `CS` net, or an S3 ADC1 net a capacitor filters | 0.25 mm | 0.3 mm | an ADC input beside an 11 A pour reads the pour. R3 adds the rule that bites: never within **1.0 mm** of a PWR or CH12 segment on its own layer. ⚠️ `BL_SENSE` is NOT in this class: it lands on `U402.GPB5`, an expander GPIO, with no filter — it is a logic-level readback, and the copper says so |
| **RAIL** | `V5`, `V3P3` — and `V12` where it is only passing through | 0.6 mm | 0.25 mm | the logic supplies: width for **droop**, not for heat |
| **default** | everything else | 0.2 mm | 0.2 mm | signals; the JLC template is right for these |

⚠️ **Strongest first, and the order is load-bearing.** `HV_C1_P` and `HV_C2_HOLD` are in
`rules.rails(d)` as well as in the HV set; reached by the RAIL row first they would be routed at
0.6 mm and 0.25 mm of clearance **at pack voltage**.

⚠️ **`V12` reaches all four boards; the 11.39 A does not.** `route.carries_bus` derives R0's "on
OUTPUTS and POWER" rather than typing it: a board is on the bus if it MAKES it (a converter whose
`+V` is the PWR12 net) or LOADS it (`route.v12_line` — an IC with a PWR12 pin and a CH12 pin,
which is `U301 U302 U303` and nothing else). On LOGIC `V12` crosses two sockets and on CTRL it
feeds one buck — about 0.7 A between them — so both get RAIL. Calling them PWR12 asks for a 5 mm
trace between two back-edge sockets, which does not fit across a 41.84 mm board.

⚠️ **Widths are for 1 oz outer copper on a 4-layer board with both inner layers spoken for.**

### The record the editor reads — established, not guessed

⭐ A **net-class rule is a named `RULE` per category plus one `RULE_SELECTOR` per member net.**
Proven against a file this editor wrote: `~/Documents/EasyEDA-Pro/example-projects/Example_3D Shell
Design.eprj2`, which 3.2.149 converted from `.eprj` itself, carries `["RULE","TRACK","电源"]` (a
20 mil power track, `ruleState` `NORMAL` beside the category's `DEFAULT` one) bound to net `+5V` by
`["RULE_SELECTOR",["NET","+5V"]]` with `ruleKeyValue {"TRACK":"电源"}`. POWER's own saved document
already carries the same shape — `["RULE_SELECTOR",["NET","GND"]]` with `{"COPPER":"copperRegion"}`
— written when the owner made the pours. `ruleOrder` 4 is the NET / NET_CLASS scope; the
`ruleKeyValue` keys are the editor's rule categories by name (`SAFE`, `TRACK`, `COPPER`, `PLANE`,
`RADIUS`, …).

⛔ **There is no persisted net-class record.** A "class" in the saved file *is* that set of per-net
selectors pointing at one named rule, which is why `--rules` writes one selector per member net and
merges into a selector the owner already set rather than replacing it.

⚠️ **`isForAll` is the LAYER set, not the net set** (`"ALL"` vs `"LAYERED"`). The one rule POWER
carried said `isForAll: "ALL"` and applied to every net only because **no selector named any other
rule** — R0 had never been done.

Each class SAFE rule is built from the document's own `DEFAULT` one, with every cell of the
clearance matrix **raised** to the class figure and none lowered: the matrix's rows are
element-type pairs, and raising all of them is the conservative reading of "this net keeps 1.25 mm
from everything". The JLCPCB capability template and its ALL-nets rules are left exactly as they
are — they stay the default for the ~250 signal nets, which is what they are right for.

`--rules --rules-doc PATH` also writes the whole table as text, for the day a rule has to be
entered by hand: **PCB → Design Rules** for each row, then **Design → Net Class** with the nets
listed.

## Step R1 — planes, before any trace (`tools/route.py --pours`)

Owner, 2026-09-22: *"we have 4 layers, should we fill one ground and/or power?"* — yes, and a
different one per board. Decided from the pin counts, not the textbook.

⚠️ **This document counts layers by the STACKUP; the file numbers them differently.** Physical 1 ·
2 · 3 · 4 is `layerId` **1 · 15 · 16 · 2** (`LAYER_PHYS` zIndex order: Top, Inner1, Inner2,
Bottom). `route.STACK_LAYER` is the one place the two meet. ⛔ Never write "layer 2" into a record
meaning the second layer of the stack — `layerId` 2 is the BOTTOM.

**Layer 2 is GND on every board**: 139 ground-domain pins on LOGIC, 100 on CTRL, 92 on OUTPUTS, 30
on POWER, never traces. A solid plane under the top-layer parts gives every signal its return and
every decoupler a short loop. **Layer 3 differs by what each board carries:**

| Board | Layer 3 | Because |
|---|---|---|
| **OUTPUTS** | **`V12` pour** over the driver line | 25 pins at **11.39 A** at the limiters. The pour IS the bus, and its extent is the amended check 11's: the u-span of the drivers' own bus pads and the feed's contacts, in the v-strip of the driver nearest the feed. `J311`'s two power contacts come onto it inside the line (3a); each `TPS4H160B`'s `VS` pins go down to it by **four** vias, not two — the pour is also the drivers' heat spreader, and a via is a thermal path only if there are enough |
| **LOGIC** | **`V3P3` pour** | 57 pins — the S3, three expanders' worth of pull-ups, every filter: a pour for **droop**, not current. The threshold is derived (`route.RAIL_POUR_PINS`): the next-best rail on any board is CTRL's `V5AUX` at 13 pins, and that is a CURRENT problem, which `PWR5AUX`'s 2.0 mm traces answer |
| **CTRL** | **second GND** | the controller row is signals and the 5 V block's currents are small and short. What CTRL has a lot of is **returns**. ⚠️ No pack voltage reaches CTRL, so neither plane is cut back |
| **POWER** | **second GND** — and **BOTH inner planes cut back at the partition** | the 14 HV nets sit at up to 160 V; a plane under them is 84 V to GND across one 0.2 mm prepreg, which is exactly what the 1.25 mm rule forbids. The 84 V section returns on `HV_C1_N` / `HV_C2_N` — **not GND** |

**The cut-back is derived, not typed.** `place.hv_partition` gives (the 84 V end, its far edge
`far`, the line `far + HV_STRIP`); `--pours` starts POWER's planes **at the line**, so there is
`HV_STRIP` (3 mm) of clear board between the 84 V parts and any plane. On the placement of
2026-09-22 that is u 167.7 mm of 242: the planes hold the low-voltage end and stop dead.

**Layers 1 and 4 (outer): traces and the parts.** The bottom layer carries the six bottom parts'
pads and the face rows' returns.

⭐ **A `POUR` needs no `POURED`.** The same example project carries POUR records with no POURED
beside them — the editor regenerates the filled result — so `--pours` writes the outline only. A
POURED written here would be this tool's idea of a fill standing in for the editor's, which is
worse than none. ⭐ **A copper keep-out, if one is ever needed, is a `REGION`** with
`regionType: "PROHIBIT"` and `prohibitType: ["COPPER"]`, layer-scoped, rectangle or polygon — the
same example carries four. R1 needs none: a cut-back plane is a smaller rectangle.

⛔ **What the planes demand of placement** (and why Part 1 checks it): no long through-hole
connector across the short axis — `J308`/`J406` at 73.66 mm would split every inner plane, so they
run along the board at an edge (check 12); `J311` inside the driver line, or the `V12` pour is fed
through a bottleneck (check 11); the HV region one contiguous blob, or the cut-back has holes in it
(checks 13 and 18).

## Step R2 — the copper whose shape the rules decide (`tools/route.py --heavy`), then the rest by hand

Power first, because it needs the room; signals last, because they can go around anything. **The
tool writes 1–4 where the placement leaves a straight run; the owner draws what it refused and then
locks all of it.**

1. **The 84 V chain on POWER** (HV). `J101.B+ → FH201 → Q101 → HV_SW → L101`/`L102` → `C201`/`C202`
   → `U201`/`U202` `+Vin`, and the negative twin on `HV_C1_N` / `HV_C2_N`. 0.5 mm minimum at
   1.25 mm, inside the region the placement drew, on one layer. ✔ **Before leaving it, run the
   editor's DRC with the HV rule on.**
2. **The 12 V bus on POWER** (PWR12). `U201.+V`/`+S` → `C207.+` → `J202.V12` and its **ground
   twin**, ≥ 5 mm. ⚠️ **A trace, not a pour**: R1 cuts both inner planes off at the partition and
   the brick's output pins stand *at* it, so the return cannot come back on copper that is not
   there. This is the 23.65 mm run check 19 exists to keep short. ⚠️ The twin is `GND` and not
   every net in the ground domain — `BASEPLATE` is on `U201` too and is not a return.
3. **The 12 V bus on OUTPUTS** (PWR12). The **pour** R1 wrote is the bus; `J311`'s two power
   contacts go onto it with the widest neck the pad allows, each driver's `VS` down with two vias,
   then `J311`'s GND contact to the layer-2 plane the same way. Nothing else on the board matters
   if this is thin.
4. **The channels** (CH12 / CH5) and **the 5 V aux supply** (PWR5AUX): driver `OUTx` → clamp diode
   → terminal, in that order and that geometry, so a surge meets the clamp first. On CTRL, `V12`
   reaches the buck through `PWR-LOGIC` and `CTRL-STACK` (two contacts on each — route those pairs'
   `V12` and `GND` together on OUTPUTS, LOGIC and CTRL first), then `U305`'s input, `L301` and the
   output caps in a tight loop — `V5AUX_SW` is the noisiest thing on CTRL: shortest trace, no via,
   no signal within 3 mm — then `V5AUX` to the four switches.
5. **The face rows' returns**: every terminal's GND to the plane by its own via, beside the pad.
6. **The differential pair** (DIFF): `U404` → `J411` on LOGIC and on to `J501` on CTRL. Paired,
   same layer, no via if it can be avoided, one via each if not — together.
7. **Sense lines** (SENSE): from their dividers to the S3 or the `CS` pins, routed *away* from
   every CH12 and PWR trace, on the layer opposite the pour.
8. **Everything else** — the autorouter is acceptable here, **after 1–7 are done and locked.** Lock
   every trace of HV, PWR12, PWR5AUX and DIFF first, or the autorouter moves them.

### How `--heavy` draws a run, and when it refuses

A net's pins are joined by a spanning tree grown in the **Manhattan** metric the runs are drawn in,
and each leg is a straight run where the two pins line up, else a single-corner L. ⭐ **The tree is
built out of legs that EXIST**: every leg to the tree is offered in turn, shortest first, and only
a pin that no legal leg reaches is refused. A plain minimum spanning tree hung `J202` off the
nearest chip cap because that leg was 2 mm shorter, the 5 mm run hit `C211`, and the chain check 19
measures went unrouted while the stubs between the chip caps got drawn.

A run **necks** into the pad it lands on — a 5 mm bus cannot land on `J202`'s 3.96 mm pitch
otherwise, and a 2.0 mm `V5AUX` run cannot leave a 1.5 mm chip pad. The neck is at most
`route.NECK_MM` (3 mm) long: 3 mm of a 1.5 mm neck in 1 oz copper is 0.985 mΩ, so the limited
11.39 A drops 11.2 mV across it, and two necks spend under half the bus's whole 50 mV budget.
⛔ **There is no taper exemption in the obstacle test.** A `LINE` record has one width, so a leg
"drawn" with the neck excused would be a full-width rectangle lying across the pad next door — a
short in the saved file, and copper the tool's own check would then refuse.

A refusal names the pair and what stopped it, and the owner necks it by hand or moves the part with
`--stack --keep`. **On the placement of 2026-09-22** the tool wrote 21 runs on POWER — four
legs of the 12 V bus, four of its ground twin and thirteen of the 84 V chain — 14 on OUTPUTS, 16 on
CTRL and none on LOGIC, and refused 23 · 32 · 14 · 0. Two things the refusals say, and both are findings rather than noise:

- ⚠️ **The HV class's 1.25 mm cannot be met between the 84 V gate network's own parts.** Twenty-one
  of POWER's 23 refusals are one 84 V net's run passing within 1.25 mm of another 84 V net's pad —
  `D13_GATE` beside `HV_SW`, `D13_PD_MID` beside `HV_BPLUS` — on 0603s whose pads are 0.6 mm apart.
  Check 7 only holds pack-voltage copper 1.25 mm from **low-voltage** parts, and IPC-2221B asks for
  clearance by the voltage *between* two conductors, which for a gate node and its source is about
  13 V and not 160. ⬜ **Open, and the owner's call:** either a second rule for pairs inside the
  84 V group, or those parts move.
- **Most of OUTPUTS' 32 refusals are the pre-clustering placement**, where a channel runs 121 mm
  and its straight line crosses three other parts. They should thin out once check 20's clustering
  placement is in the file; re-run and see.

## Step R3 — the routed board is checked, not admired (`tools/route.py --check-routing`)

Read back from the saved `.eprj2`, on any board, derived from the netlist rather than from the
rules in the file — **so a class the owner forgot to set up is still caught.** It reports the worst
offender per class with the count beside it, and exits 1.

- **Width** — every segment at least its class's minimum. Two exemptions, both from R0 itself: a
  class whose copper may be a POUR is exempt where the pour is, and a **neck** is exempt. ⚠️ A neck
  is two conditions together — at most `NECK_MM` long **and** one end on a pad of its own net. Drop
  the second and a whole thin bus reads as a chain of necks.
- **Clearance** — edge to edge, the **stronger** of the two nets' class figures: segment to
  segment, segment to pad, and a via to anything. A via's barrel crosses every layer, so it is the
  one object compared against copper on all of them. ⛔ Pad to pad is not checked: two pads of a
  land pattern sit where the manufacturer put them, and the editor's own `OTHER.deviceClearance` is
  0 for the same reason. ⚠️ A pad is measured by its **copper** — `defaultPad`, with an equal-axis
  `ELLIPSE` treated as a circle — and not by the courtyard box `place.Envelope` carries.
- **R1, HV over a plane** — no pack-voltage segment on a layer whose GND pour reaches the 84 V end,
  and **no pack-voltage via at all** while such a plane exists.
- **R1, pour extent** — no pour past the partition on the board that carries pack voltage.
- **The 12 V bus** — carried by a pour, or by ≥ 5 mm of copper, on every board the bus is on.
- **SENSE beside power** — no SENSE segment within 1.0 mm of a PWR or CH12 segment on its layer.

It is a DRC, not a completion report: a placed, unrouted board has nothing to fail, and the
unrouted count is the editor's own business. Every rule is proven to fire on a mutation of the
route the tool itself wrote (`tests/test_route.py`) — ⛔ **a check is not a check until a test
shows it firing on the defect it names.**

### What the owner's autoroute of 2026-09-22 scored — the example of what the check refuses

The owner autorouted POWER in the editor and saved. `--check-routing` on that file reports **12
problems**, and they are what R0 and R1 exist to prevent:

```
POWER: class HV width -- D13_EN_MID is 0.254 mm over 5.4 mm on layer 1 at u 41.9, v 28.0,
  and is not a neck at a pad; the class needs 0.50 mm
POWER: class PWR12 width -- V12 is 0.254 mm over 8.2 mm on layer 1 at u 217.4, v 14.8,
  and is not a neck at a pad; the class needs 5.00 mm
POWER: class RAIL width -- V5 is 0.254 mm over 9.7 mm ...; the class needs 0.60 mm
POWER: class HV clearance -- 201 pair(s) short of 1.25 mm; the worst is D13_EN segment to
  R112A.2 (D13_EN_MID) at 0.158 mm on layer 1 (short by 1.092)
POWER: class PWR12 clearance -- 4 pair(s) short of 0.30 mm; the worst is GND segment to
  C207.+ (V12) at 0.150 mm
POWER: class RAIL clearance -- 3 pair(s) short of 0.25 mm ...
POWER: class default clearance -- 4 pair(s) short of 0.20 mm; the worst is KEY_SENSE segment
  to U202.-Vout (GND) at 0.000 mm
POWER: R1 -- 30 pack-voltage segment(s) on layer(s) 15, 16, which carry a GND pour reaching
  the 84 V end (u < 164.7 mm); first is HV_C2_HOLD_IN at u 11.9
POWER: R1 -- 7 pack-voltage via(s) through the GND pour on layer(s) 15, 16
POWER: R1 pour extent -- GND pour POUR1 on layer 15 reaches u -1.7 mm, past the partition
  at 164.7 mm; --pours writes it at 167.7
POWER: R1 pour extent -- GND pour POUR2 on layer 16 reaches u -2.0 mm ...
POWER: V12 is carried by neither a pour nor 5.0 mm of copper -- the thinnest of 9 segment(s)
  that is not a neck at a pad is 0.254 mm
```

**Every one of its 271 segments is 0.254 mm** — a 10 mil trace, the editor's default — including
`V12` at 8.47 A, and all fourteen 84 V nets. Two GND pours covered the **whole** board on both
inner layers, 84 V end included, with 30 pack-voltage segments inside them and 7 pack-voltage vias
through them at 0.2 mm. ⭐ **The cause was not the autorouter.** The PCB's RULE records held one
0.2 mm / 0.2 mm rule and no selector named any other: **R0 had never been done**, because the
`--rules` option was planned and not built. The autorouter obeyed the only rule it was given.

⚠️ **It did not finish, either**, which the check does not say because completion is the editor's
own count: 96 of POWER's 100 netted pins have a trace landing on them and the four that do not are
all `U202`'s — the 5 V brick was left entirely unconnected.

⛔ **So a route is redone, not patched:** `--strip-routing BOARD` takes that board's LINE, VIA,
POUR and POURED records off — proven lossless on everything else — and the loop starts again at
`--rules`.

## Step R4 — export, prove, DRC

After routing, the same proof as always, plus the editor's: **export each of the four boards'
netlists → `tel_check` identical** (routing must not have changed connectivity — an accidental
short or a dragged pad shows up here) **→ editor DRC clean with every class rule on →
`--check-routing` clean.** Three independent checks; a board is routed when all three agree.

## What routing may send back to placement

Routing finds what placement could not: a channel too narrow for the bus neck, a TVS on the far
side of its terminal, a decoupler whose IC is across a plane split, a straight run with a part in
it. **Each is a `--keep` and a re-place, not a hand-fix that the next `--stack` would undo.** When
it is a *rule* that was wrong, fix the constant — every number in `place.py` and `route.py` states
what it protects, so the fix names what it learned.

## Files

- `tools/route.py` — the tool. A **sibling** of `place.py`, not more of it: every fact about the
  design, the file and the board frame is read through `place`, and what lives here is the copper.
  Stdlib only (plus what `eprj2` needs to decrypt the file, and Pillow for `--draw`).
- `tests/test_route.py` — every rule of the check proven to fire on a mutation of the route the
  tool wrote, the tool proven to write nothing its own check refuses, and the writer proven to
  re-read record for record. The project under test is the **synthetic** one `test_place.py`
  builds plus the design rules the **build** writes (`eprj3.pcb.DesignRules`), so no file of the
  owner's is committed; `REVV1_PLACE_PROJECT=/path/to/saved.eprj2 pytest tests/test_route.py` runs
  the same tests on a real save.
- ✔ **`--draw DIR` writes one PNG per board of the COPPER** — pours as washes with their edges
  drawn, every trace at its real width in its layer's colour, every via as a ring, the bodies as
  thin grey boxes for context, and a line at the partition on the board that has one. The numbers
  say a pour stops at 167.7 mm; the picture says whether that is the end you meant.
