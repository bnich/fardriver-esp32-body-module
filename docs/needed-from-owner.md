# What the board set needs from the owner

**Living document — maintained as items resolve.** Anything here blocks work that cannot honestly
proceed without it. Items are ordered by how much they unblock, not by effort.

⬜ open · ◐ partly answered · ✅ resolved · ⏸️ parked

📄 The design: [`board-design-record.md`](board-design-record.md) · the plan:
[`plans/2026-09-15-board-set.md`](plans/2026-09-15-board-set.md)

---

## 1. ⬜ **M18 — the cavity.** Gates every board outline

Every outline is derived from these six numbers, and they are currently an estimate offered from a
menu, not a measurement. ~10 minutes with a tape or calipers.

| | Measure | ⚠️ The trap |
|---|---|---|
| 1 | **Length**, usable end to end | |
| 2 | **Width** | ⚠️ **at the NARROWEST point along the run**, not the widest |
| 3 | **Height**, floor to the underside of the battery tray | ⚠️ **clear height along the WHOLE 200 mm**, not at its best point |
| 4 | **Floor** — metal or plastic? Does it see moving air? | |
| 5 | **Cable exits** — where can wire leave, toward which end (bars / lamps / controller)? | |
| 6 | **Intrusions** — a weld, a bend, a cable run that eats into the box partway along | |

**Why 2 and 3 carry warnings.** Width is the sensitive axis: every 10 mm buys ~25–30 mm of board
length. And the height budget closes at **61.4 mm against 64** — a bulge partway along that the
estimate assumed away is the single likeliest thing to break this design.

**Why 4 matters.** If the floor is alloy and open to air, the TDK brick can cool *downward*, which
frees BD-9's plate and simplifies the whole stack.

**Then:** edit the six numbers at the top of [`../tools/board-fit.py`](../tools/board-fit.py), set
`CAVITY_MEASURED = True`, and run `python3 tools/board-fit.py`. It reprints the record's §1, §3 and §4
tables. Every outline follows from there.

---

## 2. ⬜ Bench measurements — the bike, an ohmmeter, a voltmeter

### 2.1 ⭐ START button polarity — **do this one first**

⛔ **This is a contradiction between two documents, not a gap**, and it decides a circuit.

- `plan.md` §3.2.5a draws the start button fed **from the 5 V rail** into the RC.
- `plan.md` §2.0 says the right pod, as you rewired it 2026-09-12, has **`blue` as ground** — so
  pressing `green` pulls the node **to ground**.

**How:** right pod unplugged, ohmmeter across `green` ↔ `blue`. Press start.
**Report:** does it close to `blue`? If yes, §3.2.5a's diagram is wrong and the `74HC14` front end
inverts.
**Blocks:** the whole D24 start latch, so all of HVIN.

### 2.2 ⬜ M3 — brake lever type

**How:** each lever unpowered. Wire count. NO/NC by ohmmeter, released vs squeezed. One pair per lever
or shared?
⚠️ A three-wire sensor must be a **sinking open-collector output rated ≥15 V** — a push-pull output
does not work in this circuit.
**Blocks:** the D23 brake circuit and `J306`'s pinout. DRV is laid out to accept **both** outcomes by
resistor population, so this does not block layout — but it does block trusting it.

### 2.3 ⬜ M9 — which serial wire is the controller's TX

**How:** voltmeter on brown/blue and red/black with the app connected. The line that **toggles** is the
controller transmitting.
**Blocks:** BRAIN's tap wiring — and the label on the harness is ambiguous, which is why this is a
measurement and not a reading.

### 2.4 ⬜ M10 — KEY node draw

**How:** voltmeter at the FarDriver KEY wire, then current into it.
**Blocks:** sizing Q3 (`IXTP26P20P`) and its soft-start ramp.

### 2.5 ⛔ Meter the boost wire — **a measurement, not a part choice**

**How:** meter `CruisePin` (PIN 17) against B− with the controller powered.
⛔ **The same 30-pin harness carries pink `60VC` at 72–84 V.** Landing a 30 V FET on that destroys it
instantly. If the boost line reads high, the fallback is the `PC817` opto (plan §6).

---

## 3. ⬜ One test only you can run — **the gauge**

⭐ **EasyEDA Pro 2.2.45.4 is installed on this machine** (`/opt/easyeda-pro`), and the file format is
verified against the editor's own parser. What is **not** verified is whether the application opens a
hand-written project — the installed client wants your JLC account.

When the gauge project exists, open it and report three things:

```
1. Does it open at all?
2. Are both resistors present?
3. ⭐ Does the NETLIST PANEL show ONE net, or two?
```

⛔ **Question 3 is the one that matters.** Connectivity in this format is purely geometric — a pin
joins a net *iff* a `LINE` endpoint lands on its anchor within 0.01 unit. **A file can open looking
perfect with every wire cosmetic and zero connectivity.** "It looks right" cannot catch that.

---

## 4. ⬜ Decisions with no measurement behind them

| | Decision | Recommendation |
|---|---|---|
| **4.1** | ⬜ **Licence.** This is now unambiguously a hardware repo under **MIT**, against **CC BY-SA 4.0** in the workspace conventions | Move the hardware docs to CC BY-SA 4.0 and keep MIT for firmware, or state the exception deliberately |
| **4.2** | ⬜ **The `C4` TVS part** (≥24 V quad array, clamp < 40 V) and the **`U405` 3.3 V regulator** | I will research and propose both unless told otherwise — they need sourcing, not a decision |

⭐ **Every 09-10 order was received 09-18**, so "don't replace parts we've ordered" is now "don't
replace parts in hand". The board set honours that: **`C4` is the only new line**, and it exists
because no owned part stands off 12 V — physics, not preference. `C2`'s 20 `PESD5V0S4UD` stay fully
used (6 arrays, 14 spare) on the logic lines where 5 V standoff is correct.

---

## 5. ⬜ Values the documents leave undefined

None of these block layout; all block a *correct* schematic. I can compute the first three.

| | What | State |
|---|---|---|
| 5.1 | **D13 ramp RC** — target ~50 ms (plan §3.2.5's own recommendation, still unactioned) | computable |
| 5.2 | **Gate zeners** on Q101 and Q104 | computable |
| 5.3 | **`FAULT` and I²C pull-ups** — "strong pull-ups", value never stated | computable |
| 5.4 | **Fan flyback diode** — BOM D3 notes it is needed, no part given | ⬜ needs a part |
| 5.5 | **Latch passives R103–R106** topology — BOM H3 lists values, no circuit | ⬜ needs the bench |

---

## 6. ✅ Resolved — kept so the reasoning is not re-litigated

| Date | Question | Answer |
|---|---|---|
| 09-15 | Build path | **Both** PCB and breadboard → every inter-board interface on 2.54 mm (BD-3) |
| 09-15 | Enclosure | Custom, in the old-controller cavity under the battery |
| 09-15 | Board partition | **Four**, stacked (BD-1) — forced by area, not preference |
| 09-15 | Deliverable | Native `.eprj3`, not KiCad import (BD-11 / BD-12) |
| 09-15 | Where the work lives | `fardriver-esp32-body-module/` |
| 09-18 | `MCP23017` #2 | **Keep both.** Bought, one I²C address, 16 spare bits for later |
| 09-18 | STACK over-subscription | **Move the display block to DRV** — ⚠️ see the note below |

⚠️ **On the display move:** moving the **connector alone** makes it *worse* (30 crossings → 36),
because the telltale nets keep their BRAIN pins. Moving the whole block — `J405`, its TVS and the
`R426`–`R429` series resistors — gives **29**. The move is still right (it puts the connector on the
board whose 12 V the telltales already are), but it **did not solve the spine**: the real demand was
23 signals against 20 contacts, so **STACK was resized to 2 × 25**. The cost of the move is that
`CANH`/`CANL` now cross, since the `SN65HVD230` stays on BRAIN.
