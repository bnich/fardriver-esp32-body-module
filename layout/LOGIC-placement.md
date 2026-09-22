# LOGIC — placement proposal

Derived from `tools/netlist.py` on 2026-09-22, not from intuition: every zone below is where the
copper says the parts want to be. **Coordinates are in mm from the board's bottom-left corner**,
X along the 242 mm length, Y across the 41.84 mm width. The connector face is the **Y = 0 edge**
(IO-6: every harness plug on one long side of the box). Place, save, and the coordinator reads the
`.eprj2` back to check it.

## The shape the copper dictates

LOGIC is a **filter board**. Every signal enters at the face on a screw terminal, passes through
its own class-A network (series R → TVS → pull-up), and lands on an expander or the S3. The
expanders talk to the S3 over I²C; the S3 talks DOWN through `STACK` on the board's underside.
So the flow is **front → middle → back → down**, and the layout is four bands across the width:

```
Y = 41.84  ┌──────────────────────────────────────────────────────────────┐  back edge
           │  BAND 4  U401 (S3) · antenna end · J408 · U404 CAN · U405/6  │  (STACK J406 UNDER here)
           │  BAND 3  U402 · U403 · I²C pull-ups · their 100 nF           │  (PWR-LOGIC J407 UNDER)
           │  BAND 2  class-A networks: TVS arrays, series R, pull-ups    │  one cluster per terminal
           │  BAND 1  J402      J403     J306      J409       J410        │  the INPUTS row
Y = 0      └──────────────────────────────────────────────────────────────┘  connector face
           X=0                                                          X=242
```

## Band 1 — the INPUTS row (Y = 0 edge), fixed order

The row order is the netlist's (`edge_budget`): **J402 · J403 · J306 · J409 · J410**, bodies end to
end with 1 mm gaps, 185.9 mm total, so **28 mm spare on the 242**. Centre the row, or bias it toward
the end the harness enters from. The header bodies are 9.20 mm deep; their plugs stand out past
the board edge (that is the 19.65 mm `FACE_ROOM` in the cavity budget).

| Terminal | X (body left → right) | Carries |
|---|---|---|
| `J402` 9-way | 28.0 → 72.8 | left bar pod: 7 signals |
| `J403` 6-way | 73.8 → 107.1 | right bar pod: 4 signals + START |
| `J306` 3-way | 108.1 → 130.0 | ⚠️ the two brake levers — to the S3 DIRECTLY |
| `J409` 8-way | 131.0 → 172.0 | general inputs 1: boost button + 6 spares |
| `J410` 8-way | 173.0 → 214.0 | general inputs 2: 7 spares |

## Band 2 — one class-A cluster per terminal, directly behind it (Y ≈ 10–20)

Each terminal's protection sits **behind its own header**, so every input wire is short before it
meets its TVS — the whole point of the network. Behind each terminal, in this order from the face:
the **TVS array** (`SMS05T1G`, cathodes toward the terminal), then the **series 1 kΩ resistors**,
then the **pull-ups**. The netlist names them:

| Behind | TVS | Series R and pull-ups |
|---|---|---|
| `J402` | `D401`, `D402` | `R402`–`R408`, `R413`–`R419` |
| `J403` | `D403` | `R410`–`R412`, `R421`–`R423`, `R477`, `R478` |
| `J306` | `D313` | `R317`, `R318`, `R341`, `R342` |
| `J409` | `D410`, `D411`, `D413` | `R409`, `R420`, `R446`–`R451`, `R459`–`R464` |
| `J410` | `D411`, `D412`, `D413` | `R452`–`R458`, `R465`–`R471` |

`D411` and `D413` serve both general-input terminals — sit them **between** `J409` and `J410`.

⚠️ **`J306`'s two lever signals do not go to an expander.** `IN05_BRAKE_L` → `U401.IO15` and
`IN06_BRAKE_R` → `U401.IO20` — the brake is on the S3's own interrupt pins (IO-8). Route those two
straight back from `J306`'s cluster to the S3; keep them away from the I²C bus and the CAN pair.

## Band 3 — the expanders (Y ≈ 22–30), each over the inputs it reads

- **`U402` reads 11 input bits** — all of `J402`'s and `J403`'s, plus some of `J409`'s. Put it at
  **X ≈ 60–90**, behind the pod terminals it serves.
- **`U403` reads no inputs**; it drives `ACC_SENSE` and 13 spares. It has no terminal to be near, so
  it goes where the I²C bus is shortest: **beside `U402`, X ≈ 95–110**, sharing the bus pull-ups.
- The I²C pull-ups (2.2 kΩ, `R434`/`R435` per the STACK trace) between the two expanders and the S3.
- Each expander's 100 nF decoupler within 3 mm of its VDD pin.
- ⚠️ The bus **also crosses STACK to `U304` on OUTPUTS** — so `SDA`/`SCL` want to reach `J406`
  (under the board) by a short path. Put the expanders **directly above `J406`'s footprint**.

## Band 4 — the S3 and everything that talks to it (Y ≈ 30–41, back edge)

- **`U401` at X ≈ 150–175, against the back edge** — the antenna end of the WROOM-1U must point
  **off the board** (Y = 41.84 edge), and the U.FL pigtail runs from there to the box's SMA
  bulkhead. Nothing metal, no ground copper under the antenna end. Its 25 I/O lines go DOWN
  through `J406`; put `U401` **over `J406`'s far end**.
- **`J408` Tag-Connect** within 15 mm of `U401` — it carries `EN`, `IO0`, `TXD0`, `RXD0`. Leave a
  keep-out for the cable's three alignment pins (`layout-rules.txt` has it). Reachable with the
  lid off, not under another part.
- **`U404` CAN transceiver** next to `U401`; `CANH`/`CANL` go down through `J406` as a flanked pair.
- **`U405` 3.3 V LDO** and **`U406` supervisor** (unfitted) near `J407`, which brings `V5` up —
  the LDO's input cap on the `J407` side, output cap toward `U401`.
- **`R438` / `C412`** — the `EN` RC — beside `U401.EN`. ⚠️ **`EN` is now the reset for all three
  expanders (IO-22)** and crosses STACK on contact 57; keep the node short and clean.

## The two connectors UNDER the board (already flipped? — check)

- **`J406` STACK 2×29, 73.66 × 5.00 mm** — under Bands 3–4, running along X. Its footprint is
  pre-mirrored; when flipped to the bottom it lands pin-1-correct against `J308` on OUTPUTS.
  Everything it carries (25 S3 lines, I²C, `EN`, CAN, the telltales) originates in Bands 3–4, so
  the vias are short.
- **`J407` PWR-LOGIC 1×9, 22.86 × 2.50 mm** — under Band 3/4 near `U405`: it brings `V5`, `V3P3`,
  `KEY_SENSE` up. ⚠️ **Both must land exactly over their mates on OUTPUTS** (`J308`, `J307`) — the
  stack is only as aligned as these two footprints. Fix their X first, then place OUTPUTS to match.

## What to check after placing (I read the save back for these)

1. `J406` and `J407` on the **bottom** layer — today they are still on top.
2. `U401`'s antenna end at the Y = 41.84 edge with no copper under it.
3. Every TVS within ~8 mm of the terminal it protects.
4. The row's five headers at Y = 0, bodies not overlapping the M3 corner holes (3.5 mm inset).
5. Nothing taller than **the LOGIC→LID gap allows**: 8.2 mm available, the tallest LOGIC part is `J410` at 7.2 — every part fits; only a plug stands taller, and that is budgeted.
