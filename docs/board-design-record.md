# REVV1 ESP32 body module — board design record

**Adopted 2026-09-15 (owner).** The module becomes **four stacked PCBs** in a custom enclosure in the
old-controller cavity under the battery compartment, delivered as a **native EasyEDA Pro `.eprj3`
project** generated from a checked-in netlist source.

This record owns **the board partition, the inter-board interfaces, the physical stack and the
toolchain.** It owns nothing else.

📄 **Architecture, the pin rules and decisions D1–D24 stay in
[`docs/plan.md`](plan.md).**
📄 **Parts, prices and order state stay in
[`docs/bom.md`](bom.md).**
📄 **The brake circuit stays in
[`brake-circuit.md`](https://github.com/bnich/Revv1-FS-72v-Conversion/blob/main/docs/brake-circuit.md).**

⚠️ **This record supersedes the plan's §9.2 "seven blocks" (A–G) as the board partition.** The A–G
grouping was functional, drawn before **D23** (brake circuit) and **D24** (start latch) existed, and
before the enclosure had a location. The plan's §9.2 table should be updated to point here. Blocks A–G
remain useful as *functional* names; they are no longer board names.

---

## 0. The envelope

| | mm | Provenance |
|---|---|---|
| Cavity length | **200** | ⚠️ owner estimate 2026-09-15 — **not measured** (**M18**) |
| Cavity width | **50** | ⚠️ estimate — **the sensitive axis** |
| Cavity height | **70** | ⚠️ estimate |
| Enclosure wall | 3 | assumed printed ASA |
| **Board envelope** | **42 × 186** | = 7,812 mm² per layer, derived from the four rows above |
| Internal stack height | **64** | 70 − 3 floor − 3 lid |

⛔ **Every board outline in the generated project is parametric on these four numbers.** They are an
estimate from a menu, not a measurement. **M18 must land before layout begins** — width is worth about
25–30 mm of length per 10 mm gained, so a 10 mm error rewrites the partition.

**Location:** the cavity under the battery compartment, where the stock controller lived. It is **not**
the under-seat bay — that is occupied by the FarDriver (120 × 180 × 55) and its shroud, whose belly
must stay open for convection.

---

## 1. What forced four boards

The partition is not a matter of taste. It falls out of one computation.

```
HV section raw part footprint            7,537 mm²
one 42 × 186 board                       7,812 mm²
                                    ---------------
raw part density if kept on one board        96%      unroutable

  of which, two converter modules        3,459 mm²  = 44% of the board
      TDK CN150B110-12/CO   58.3 × 37.2
      Cincon EC7BW-110S05   50.8 × 25.4  (2"×1"×0.4")
```

⭐ **No individual part is large — the board is small.** 42 × 186 mm is a small board, and the 84 V
section has 18 distinct part types plus five connectors. Split across two layers the problem vanishes
entirely; the four boards run at **34 / 66 / 24 / 29 %** raw density, against 96 % for the single board.

⚠️ **These are shelf-packed real datasheet footprints, not a part count times a routing multiplier.**
A density multiplier is a guess wearing a number's clothes; it answered this question wrongly once
already. Where one is unavoidable it is stated in the open, never folded into a total.

---

## 2. Decisions

| ID | Decision | Why |
|---|---|---|
| **BD-1** | **Four boards, stacked vertically** — HVIN · CONV · DRV · BRAIN | §1. The 84 V section cannot fit one 42 × 186 board. The cavity is a tower (50 wide × 70 tall), so layers are cheap and length is not |
| **BD-2** | **Power flows bottom to top, voltage decreasing.** 84 V at the floor, 3.3 V at the lid | Maximum physical separation between the 84 V node and the 3.3 V serial taps — the §3.2.4 concern, solved by geometry instead of by routing |
| **BD-3** | **Every inter-board interface is 2.54 mm pitch** | Owner, 2026-09-15: *"both. i want full options for pcb and breadboard."* Any one board can be replaced by a breadboard or perfboard section during bring-up, so §9.8's "don't skip the prototype" survives into the PCB era instead of being traded away |
| **BD-4** | **The HV-LINK header skips alternate pins → 5.08 mm** | Plain 2.54 mm leaves ~0.7 mm pad-edge to pad-edge against IPC-2221's 0.6 mm at this voltage (plan §9.6.2) — passing but marginal. Skipping pins retires the issue for the cost of a longer connector |
| **BD-5** | **`D16` resolves to (a) — FULL NATIVE lighting.** I²C leaves the lighting path; the `MCP23017`s serve bar inputs only | DRV and BRAIN are *stacked*, so the connector between them is short and rigid and 21 signals cost nothing. This is the end state plan §9.8.2 predicted and told us to revisit at layout |
| **BD-6** | **The start latch (D24) is on HVIN. The brake circuit (D23) is NOT — it is on DRV** | The latch switches 84 V and cannot leave that domain. The brake circuit is gated on **M3, still unmeasured** — ⛔ an unmeasured circuit does not go on a board we intend to spin once. DRV carries it with resistor-population options for both M3 outcomes |
| **BD-7** | **`RUN` and `START` are copper, not firmware.** Both pods land on BRAIN for conditioning; the two contacts pass straight through to the spine as bare traces, tapped for sensing | D23 and D24 both require function with a hung or unflashed module. A trace through an unpowered board is still a trace; a firmware-mediated signal is not |
| **BD-8** | **All harness connectors are right-angle, edge-facing, and low-profile (≤ 6 mm) wherever the current allows** | The lid lifts without disturbing the harness, and strain relief lands at the wall where the gland is. ⚠️ Connector height is **one of the two measures §4's budget depends on**, and the one carrying its whole 3.9 mm margin |
| **BD-9** | **An alloy plate between CONV and DRV** — brick heatsink, EMC barrier between the 84 V and logic sections, and structural deck, bolted to the enclosure walls | One part solving three problems. ~79 cm² plus conduction into the walls is ample for the brick's 2.9 W |
| **BD-10** | ⛔ **The `HAQ-10T` heatsink is NOT used** (BOM E5 becomes a spare) | 25.4 mm of fins on top of a 12.7 mm brick does not fit a stacked assembly. BD-9's plate is both a shorter and a better thermal path. ⚠️ E5 was specified against a free-standing metal box, a configuration this design no longer has |
| **BD-11** | **Deliverable is a native `.eprj3` project**, generated from `netlist.py`, committed as text | EasyEDA publish `.eprj3` themselves as a git-friendly JSON format explicitly *"for users and AI tools."* No importer, no KiCad-version gamble, and `COMPONENT` binds a Device by UUID so real LCSC parts stay linked for ordering |
| **BD-12** | ⛔ **Not the KiCad import route** | EasyEDA Pro's importer documents **KiCad 5.1 / 5.9**; the only available KiCad is **10.0.6**, five majors past it, across the KiCad-6 schematic format break. EasyEDA also warn *"copper area will be different, please check carefully."* Writing a 2019 format to feed a lossy importer is more work than writing the native one |
| **BD-13** | **Keep both converters** — the isolated 5 V rail stays | Dropping the Cincon would free ~2,900 mm² and one tall part, but plan §3.2.1 bought it deliberately so *"a lamp or horn fault cannot brown out the brain"* at ~$57. §4 closes without spending that property, so it is not spent. ⚠️ **This is the reserve.** If M18 comes back smaller than the estimate, this is the first thing to re-open |
| **BD-14** | **Tall parts may mount on a board's UNDERSIDE**, hanging into the free area of the layer below | L1 runs at 34 % density, so CONV's two 18 mm electrolytics hang down into it instead of adding 18 mm to the stack. Worth **5.3 mm**, and §4 does not close without it. ⚠️ Requires a keep-out on L1 directly beneath them, and the generator must carry a per-part side |

---

## 3. The four boards

| Layer | Board | Domain | Raw area | Density | Respin cost |
|---|---|---|---|---|---|
| **L1** ↓floor | **HVIN** | 84 V | 2,632 mm² | 34 % | **once** |
| **L2** | **CONV** | 84 V → 12 V / 5 V | 5,141 mm² | **66 %** ⚠️ | **once** |
| ⎯ | *alloy plate (BD-9)* | — | — | — | — |
| **L3** | **DRV** | 12 V | 1,876 mm² | 24 % | medium |
| **L4** ↑lid | **BRAIN** | 3.3 V | 2,274 mm² | 29 % | **cheap** |

Total raw part area **11,922 mm²** across **31,248 mm²** of board — **38 %**.

⚠️ **CONV is the tight board and the only one that is.** A naive shelf-pack puts it at 202 mm against
186 mm available — it only fits because its two dominant parts are modules with **no routing beneath
them**, which shelf-packing cannot model. Real layout will close it; a smaller cavity will not.
**If M18 comes back under the estimate, CONV is the first casualty**, and BD-13 is the answer.

### L1 — HVIN (84 V entry, protection, start latch)

`SMCJ90A` TVS · 2 × Würth `7448022010` CM choke (one per converter input, before the bulk cap) ·
4 × Vishay `VY2472M49Y5US6` Y2 to the plate · **D13** soft-start high-side switch `IXTP26P20P` +
gate zener + ramp RC · **start latch (D24)** — `74HC14` · 1 MΩ/2.2 µF film RC · 2 × `BSS126` ·
**Q3** `IXTP26P20P` + zener → FarDriver KEY · IN-12 divider 330 k / 10 k.

⭐ **Set the D13 ramp at ~50 ms, not 10 ms** — plan §3.2.5's own recommendation, still unactioned.
114 W peak SOA instead of 363 W, for one capacitor value and an imperceptible key-on delay.

### L2 — CONV (both converters)

TDK `CN150B110-12/CO` · Cincon `EC7BW-110S05` · **C1** `EKXJ221ELL221MM25S` at DC-DC #1's input
terminals · `1N4007` hold-up blocking diode · Schurter `FAC 0031.3803` + `0001.2504` 1 A T-lag ·
**C2** `EKXJ221ELL221MM25S` behind the diode on DC-DC #2 alone.

⚠️ **C1 and C2 sit on opposite sides of the diode and are not interchangeable** (plan §3.2.2). Putting
the hold-up cap on the common node collapses ride-out from ~237 ms to ~20 ms.
⚠️ **Both cans lie down and are bonded.** 18 × 25 mm radial cans on long leads are a lead-fatigue
geometry on a motorcycle (BOM §9.5.2); lying down is the shorter cantilever.

### L3 — DRV (12 V drivers + brake circuit)

2 × TI `TPS4H160BQPWPRQ1` — 6 lighting channels, 2 spare · 6 × 20 kΩ `OUT`→VBAT for off-state open-load ·
3 × `AO3400A` low-side (horn, fan, buzzer) · **brake circuit (D23)** — 6 × `1N4148` steering,
**Q1** `AO3407A` for the STOP lamp, **Q2** `AO3400A` run/off inverter, pull-ups.

⚠️ **The HTSSOP thermal pads must reach real copper**, or per-channel current limiting and thermal
shutdown do not behave as specified. This is the hardest mount on the BOM.
⚠️ **40 V parts — the 12 V rail only.** Never the 84 V node.

### L4 — BRAIN (logic)

`ESP32-S3-WROOM-1-N8` (or `-H4`; ⛔ never `R8`/`R16V`, 65 °C) · 2 × `MCP23017` · `SN65HVD230` + 120 Ω ·
USB-C for native USB console/flash · 11 × class-A conditioning networks (1 kΩ pull-up — **wetting
current**, not 4.7 kΩ) · 4 × `PESD5V0S4UD` at the connectors · boost open-drain FET with a hard
external pull-down.

⚠️ **Carry the plan's pin *rules*, not its GPIO numbers** (§9.8): analog on ADC1 only (GPIO1–10),
brake inputs native, boost on a dedicated pin and never on a bus, **no wire leaving the box on a
strapping pin (0/3/45/46)**, GPIO43 never a driver.
⚠️ **The CAN hardware is fitted though D19 parks the feed.** Transceiver in hand, 2 GPIO, and a
replacement panel is likelier to need CAN than not.

---

## 4. The stack and the height budget

⛔ **Height is the binding constraint of this design, and it does not close by default.** Area is
solved — 38 % across four boards. Height is not, and it is where this design fails if it fails.

Available internal height **64.0 mm** (70 − 3 floor − 3 lid). Four layers, each contributing 1.6 mm of
PCB, its tallest part, and 1 mm of clearance, plus a 3 mm plate:

| Cumulative measure | Stack height | |
|---|---|---|
| Nothing done — 18 mm caps upright, 12 mm connectors throughout | **77.4** | ⛔ over by 13.4 |
| **+ BD-14** — the two electrolytics on L2's underside | 72.1 | ⛔ over by 8.1 |
| **+ BD-8** — low-profile connectors on **both** logic layers | **60.1** | ✅ **under by 3.9** |
| *+ M19 confirms the choke at 12 mm* | *58.1* | *under by 5.9* |
| *+ TO-220s laid flat rather than upright* | *56.1* | *under by 7.9* |

✅ **The budget closes on BD-14 and BD-8 alone** — two design decisions, neither waiting on a
measurement. The two italic rows are margin, not requirements.

⚠️ **3.9 mm is thin**, and it is spent by any one of: a taller connector family than assumed, a thicker
plate, or a fourth standoff. The two italic rows are where more comes from; **BD-13 is the reserve**
beyond that.

**Per-layer ceilings that layout must hold:**

| Layer | Ceiling above its own board | Set by |
|---|---|---|
| **L1 HVIN** | **18 mm** | ⭐ **the `IXTP26P20P` TO-220 floors this at 16 mm standing up**, so the CM choke is free up to 18 — confirming it (M19) buys only 2 mm |
| **L2 CONV** | **12.7 mm** | the TDK brick. ⚠️ Nothing on the **top** side may exceed it — the electrolytics go underneath (BD-14) |
| **L3 DRV** | **6 mm** | right-angle low-profile connectors |
| **L4 BRAIN** | **6 mm** | right-angle low-profile connectors |

⚠️ **Height is a design rule here, not an outcome.** One tall substitution breaks the enclosure, so
each ceiling is an assertion in §7.2, not a note.

📄 **Re-runnable:** [`tools/board-fit.py`](../tools/board-fit.py) holds the cavity and the part heights as
parameters at the top and prints both tables. **Re-run it when M18 or M19 land** and update §1, §3 and
§4 from its output.

---

## 5. The three interfaces

All 2.54 mm (**BD-3**), so any board can be a breadboard section.

### HV-LINK — L1 ↔ L2, **84 V**, alternate pins skipped → 5.08 mm (**BD-4**)

Protected 84 V up to the converters; 5 V back down for the start latch's `74HC14`.

### PWR-UP — L2 → L3/L4

| Pins | Net | Note |
|---|---|---|
| 2 | **+12 V** | 2 pins for the measured 2.62 A |
| 3 | **GND** | return + reference |
| 1 | +5 V | to BRAIN's regulator |
| 1 | `KEY_SENSE` | IN-12, 330 k/10 k divider output, 0–2.47 V |
| 1 | `RUN` | **hardware net** (BD-7) → Q2 on DRV, latch reset on HVIN |
| 1 | `START` | **hardware net** (BD-7) → latch SET on HVIN |

### STACK — L3 ↔ L4, 2 × 20

6 lighting channel inputs (+2 spare) · `DIAG_EN` · `SEL1` · `SEL2` · `CS1` · `CS2` (analog,
ground-flanked) · `FAULT1` · `FAULT2` · horn / fan / buzzer gates · `IN-05` / `IN-06` brake sense
(native, < 10 ms) · `IN-15` 12 V rail sense · `BL` · alternating grounds.

⚠️ **`CS1`/`CS2` must land on ADC1 (GPIO1–10)** — ADC2 dies with WiFi.

---

## 6. Connector allocation

**One keyed connector per harness bundle**, not per-wire terminals — which is what BOM **X1** already
anticipates. Three reasons, none of them edge length: a 42 × 186 board has **372 mm of long edge**, so
DRV's 23 conductors (115 mm at 5 mm pitch) and BRAIN's 28 (140 mm) would fit terminals comfortably.

1. ⛔ **Height.** A screw terminal is 10–12 mm. §4 gives the logic layers a **6 mm** ceiling.
2. ⛔ **Keying.** Colour is never evidence on this bike — `blue` is LOW beam on the headlight, LEFT
   turn on the tail, and `+` on the horn. A keyed shell makes a mis-plug physically impossible where
   colour cannot.
3. **Field service and strain relief** — a lamp assembly unplugs, and the relief lands at the gland.

| Board | Connector | Cond. | Carries |
|---|---|---|---|
| **HVIN** | B+/B− | 2 | 84 V tap, fused upstream in the harness (`KLKD002` in the Mersen `FEB-11-11` inline holder — **not a board part**) |
| **HVIN** | KEY switch | 2 | the mechanical key |
| **HVIN** | KEY out | 1 | Q3 → FarDriver KEY wire |
| **DRV** | Headlight | 4 | black common · green HIGH · blue LOW · yellow DRL |
| **DRV** | Tail + rear signals | 5 | black common · yellow running · **red STOP** (Q1) · blue L · green R |
| **DRV** | Front turn L/R | 4 | isolated 2-wire pairs |
| **DRV** | Horn | 2 | ⛔ blue `+`, black `−` — **red is not positive** |
| **DRV** | Fan + buzzer | 4 | |
| **DRV** | Brake levers | 4 | gated on **M3** |
| **BRAIN** | Left pod | 8 | turn L/R, horn, high/low ×2, flash-to-pass, hazard, common |
| **BRAIN** | Right pod | 5 | slider ×2, run, start, common — run/start pass through (BD-7) |
| **BRAIN** | FarDriver signal | 6 | TXD, RXD, BW5V, GND, boost, `BL` |
| **BRAIN** | Display 9-pin | 9 | ⏸️ footprint fitted, parked with D19 |

⛔ **Colour is never evidence on this bike** — the same colour means different things on every
assembly (plan §6.0.1). Identify by function, every time.
⚠️ **Every lamp common lands on the module's 12 V return**, which stars at the **controller B− stud** —
never a frame point.

---

## 7. Toolchain

### 7.1 Source of truth

`netlist.py` holds parts, nets, connector pinouts and the constraint assertions. `gen_eprj3.py` emits
the project. **The generated project is an artefact; the Python is the design.**

```
netlist.py  ──►  gen_eprj3.py  ──►  revv1-module.eprj3/
                                     ├── revv1-module.eprj3     project index
                                     ├── sch/HVIN/HVIN.esch2
                                     ├── sch/CONV/CONV.esch2
                                     ├── sch/DRV/DRV.esch2
                                     ├── sch/BRAIN/BRAIN.esch2
                                     └── pcb/*.epcb2            outline + keepouts
```

### 7.2 Assertions — the constraints are executable, not comments

Following the project's rule that a constraint belongs in `assert()`, not prose, and that **an
assertion that never fires is not a test** — each must be proven against deliberately broken input:

| Assertion | Protects |
|---|---|
| no net above 12 V appears on L3 or L4 | BD-2, the `TPS4H160B`'s 40 V limit |
| every HV-LINK pin has ≥ 5.08 mm to its neighbour | BD-4 |
| no connector pin on BRAIN maps to GPIO 0/3/45/46 | strapping — a rider holding a lever at key-on |
| `CS1`,`CS2`,`IN-12`,`IN-15`,`IN-16` are on GPIO1–10 | ADC2 dies with WiFi |
| every output gate has a bias-OFF part | D14 |
| every net leaving the box has a TVS at its connector | §4 |
| board outline ⊆ envelope; every part height ≤ layer ceiling | §0, §4 |

### 7.3 ⚠️ Gauge first

⛔ **The `.eprj3` encoding cannot be verified from this machine** — EasyEDA Pro is a browser
application. The published example uses JSON objects with a `type` field; the v2 spec shows JSON
arrays. **Which one the current editor accepts is unknown.**

✅ **So build a gauge: a 5-part, 3-net project, opened in EasyEDA Pro, before generating anything
real.** This is the project's own gauge-first rule applied to the toolchain, and it is cheap: a wrong
encoding discovered on a 4-board project costs the whole generator.

Reference material: `easyeda/easyeda-pro-eprj3-format` (project layout, worked example) and
`easyeda/easyeda-pro-file-format-v2` (85 documents, per-record).

---

## 8. What must be measured before layout

| # | Measure | Gates | State |
|---|---|---|---|
| **M18** | ⭐ **The cavity** — length, width **at the narrowest point**, clear height along the *whole* run, cable exits, what the floor is made of and whether it sees moving air | **Every board outline.** Width is the sensitive axis | ⬜ **owner estimate only** |
| **M19** | Part heights — **the right-angle connector family first**, then the CM choke, then the fuse holder | §4's per-layer ceilings. ⚠️ **The connector is the one that matters**: §4 assumes 6 mm on both logic layers and the whole 3.9 mm margin rests on it. The choke is worth 2 mm | ⬜ |
| **M3** | Brake lever type, NO/NC, wire count | The brake circuit on DRV (BD-6) | ⬜ from the plan |
| **M9** | FarDriver serial direction | BRAIN's tap wiring | ⬜ from the plan |
| **M10** | KEY node draw | Q3 and its ramp | ⬜ from the plan |
| — | ⚠️ **Meter the boost wire** before connecting a 30 V FET | BRAIN's boost channel | ⬜ — the same harness carries pink `60VC` at 84 V |

---

## 9. Open items

- ⛔ **M18 is the gate on everything.** The envelope is an estimate offered from a menu, and both
  budgets are computed from it. Width is the sensitive axis.
- ⚠️ **Height closes at 60.1 mm against 64 — a 3.9 mm margin that rests on one unread number**, the
  right-angle connector height assumed at 6 mm (**M19**). Pick the connector family early; it is a
  cheap decision that is carrying more of this design than its price suggests.
- ⚠️ **CONV at 66 % is the only board without slack.** §3.
- ⬜ **BD-9's plate** — material, thickness, how it bolts, and whether it needs a cutout for the
  electrolytics or an alloy spacer block down to the brick baseplate.
- ⬜ **Does the enclosure see moving air?** If the floor is alloy and open, the brick could cool
  downward and BD-9 simplifies. Part of M18.
- ⬜ **`MCP23017` package** — the BOM bought **DIP-28** (4 paid). On a 44 mm board SOIC-28 is the
  better part. ⚠️ **Change the BOM first, then this record** — the BOM owns procurement.
- ⬜ **Enclosure design has not started** and is not in this record's scope.
- ⏸️ **Board F (display power switch)** stays parked with D11/D19. BRAIN carries the 9-pin footprint
  and nothing else.
- ⚠️ **No part in the power group carries a vibration qualification**, and the conformal-coat / stake /
  bond specification is still undefined (plan §9.5.2). Unchanged by this record — but four stacked
  boards make it more pressing, not less.

---

## 10. Build order

1. **M18** — measure the cavity, re-run `tools/board-fit.py`, update §1/§3/§4.
   ⛔ Nothing below starts first; every outline is derived from it.
   Choose the right-angle connector family at the same time (**M19**) — §4's margin rests on it.
2. **Gauge project** (§7.3) — 5 parts, 3 nets, opened in EasyEDA Pro.
3. `netlist.py` + assertions (§7.2), each assertion proven to fire.
4. **BRAIN** and **DRV** schematics — cheapest to respin, and firmware needs them.
5. **HVIN** and **CONV** schematics — spun once, so they go last, with the most review.
6. Board outlines, placement and keepouts.
7. Order. ⚠️ **One board at a time is affordable here** — that is what the partition bought.
