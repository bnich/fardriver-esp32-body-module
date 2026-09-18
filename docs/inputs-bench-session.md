# Inputs bench session — M2 · M3 · M8 · M9 · M10, plus the new switch sets

**Created 2026-09-10 · budget ~2 hours across three sittings · owner runs this, at the bike**

Companion to `revv1-m16-can-bench-test.md`, which is its template. This session closes the **input**
side of the ESP32 module — the measurements `revv1-esp32-module-plan.md` §5 still lists as ⬜ and that
every remaining design step waits on.

---

## 0. Why this is the job now — read first

The Chaojie CAN dash feed is **parked** (plan **D19**, build issue **#13**), so the module's critical
path is linear:

> **① sourcing → ② order → ③ THIS SESSION → ④ firmware → ⑤ boards**

The module parts are on order (`revv1-module-bom.md`). These measurements need **the bike**, not the
parts — run them while the order ships.

⚠️ **These are not survey measurements — each one gates a decision, and M3 gates the brake circuit,
which has to be *built*:**

| # | What it decides | What is blocked until it lands |
|---|---|---|
| **A2** | The new bar-mount switch sets: contact pairs, momentary vs latching, and how the 3-position lighting slider is wired | IN-01…04 and IN-08…11; the **D21** slider decode depends on OFF/A/B vs OFF/A/A+B |
| **M2** | Which wires in the handlebar loom (connector "1T3 10") are the **brake-lever** wires | The brake circuit's lever inputs (`revv1-brake-circuit.md` §2). Nothing in the loom is cut until they are known; the lever pairs are the only part of it that is re-used |
| **M3** | Brake lever type: two-wire switch (NO or NC) or three-wire sensor (output type), one pair per lever | ⚠️ **The brake circuit build** (`revv1-brake-circuit.md` §4, step 1 in §6) — nothing is wired to the levers until it lands. Also **IN-05/06** |
| **M8** | Red button is a true momentary dry contact | **IN-07** and therefore **D4**, the whole boost scheme |
| **M9** | Which serial line is the controller's **transmit** — the label is ambiguous | ⚠️ **IN-13/IN-14.** Tapping the wrong one gives a listener that hears nothing. Also settles whether the Bluetooth is a dongle or integrated |
| **M10** | KEY node voltage, and where the module's fused B+ tap physically lands | **IN-12** and the D13 power tap — plan §3.2.5 |

ℹ️ **There is no M1.** D20 replaces both original pods with two bar-mount switch sets (BOM **A3**), so there
is nothing to reverse-engineer; **A2** ohms out the new sets instead, unpowered.
**M11's remainder is parked with the display**; the software version it wanted is **`CJ-YQ25-250418`**.

---

## 1. ⚠️ THE ORGANIZING RULE: ONE SITTING PER POWER STATE

The sittings separate **unpowered** work (A and B) from **powered** work (C). Do A and B first —
they carry no risk, and they tell you which connectors you will probe in C.

| Sitting | Domain | What is live | Measurements |
|---|---|---|---|
| **A** | **NOTHING** — everything unplugged | ohmmeter only | **A2** switch sets, **M8**, M15(a) |
| **B** | **NOTHING** — the brake levers | ohmmeter only | **M2**, **M3** |
| **C** | **72 V FarDriver only, on the bench supply** | DP2031 at 64 V, pack out of circuit | **M9**, boost wire (C1.5), **M10(a)** |

⚠️ **The USB cable is a ground path.** In sitting C a laptop plugged into the ESP32 or a serial
adapter bonds that adapter's ground to the FarDriver's B−. Keep that in mind for anything else on the
bench.

---

## 2. Safety rules

- ⚠️ **Sitting C runs off the DP2031, not the pack** (§7 explains the voltage). The bike is on its
  temporary running setup, so take the pack out of circuit first: **key OFF → unplug the XT90-S**.
- ⚠️ **Wheel off the ground or motor phases disconnected** for anything powered. Nothing in this
  session should turn the wheel, but nothing here is worth a surprise either.
- ⚠️ **Unplug the throttle for sitting C** — none of these measurements need it, and a connected
  throttle makes an accidental spin possible.
- ⚠️ **Ohmmeter measurements happen with the circuit DEAD and at least one end UNPLUGGED.** An
  in-circuit resistance reading is a parallel-path reading and is worth nothing.
- ⚠️ **Photograph every connector before unplugging it**, cavity side, with the latch oriented.
- 🔑 **Label as you go.** A bagged, unlabelled connector is a second measurement session.

---

## 3. Kit

- DMM (the usual one) — needs continuity beep, DC volts, ohms
- **Rigol DP2031** bench supply — sitting C, CH1+CH2 in series
- **MSO5074** scope — optional but wanted for **M9** (see §7: a DMM can identify the transmit line,
  a scope confirms the bitrate and frame shape)
- Jumper leads with fine probes / IC hooks, a set of insulated clips
- **Paper and a pen at the bike**, or this file open on a phone. ⚠️ Do not plan to remember which of
  five identical black wires read 4.7 kΩ.
- Camera
- Small heat-shrink or tape flags for labelling

---

## 4. ⛔ TRAPS — read before probing anything

Each of these produced a confident wrong answer on this bike.

**(1) ⛔ The ohmmeter is USELESS on any LED assembly.** A 12 V LED module's driver plus a 9–11 V string
forward voltage cannot be forward-biased by a meter's <1 V (ohms) or ~2–3 V (diode) test — M4 read
all 10 pairs of the headlight's 5 wires as O.L. ⭐ **Identify LED assemblies by POWERED SWEEP, never by
ohmmeter.** ✅ This does **not** affect A2/M2/M8 — switch sets, brake switches and the red button are
**dry contacts**, where the ohmmeter is exactly right. ⚠️ But if any switch turns out to be
**illuminated**, that leg falls under this trap; sweep it powered instead. A **three-wire** brake lever
is a powered sensor, not a contact — M3 records it and stops (§6).

**(2) ⛔ THE COLOUR TRAP, and it is worse on this bike than on most.** Plan §6.0.1: **the same colour
means different things on different connectors.** BLUE is low beam *and* left turn *and* horn-positive
across three connectors; RED is unused on the horn and headlight but is **STOP** on the tail; on the
horn, **`+` is BLUE and `−` is BLACK — red is not the positive.** And on the display side, all nine
wires have a same-colour FarDriver counterpart and **none is the correct match**.
⭐ **Identify every wire by FUNCTION, measured. Colour is a label, never evidence.**

**(3) ⚠️ A meter referenced to a floating node lies.** The DP2031 **opens its output relay on BOTH
rails** when the output is disabled, so anything referenced to a rail with the output off is garbage.
⭐ **Reference to a ground you can prove is a ground**, and if the supply is off, reference to the
chassis/B− you are actually clipped to.

**(4) ⚠️ "It fits, so it must be right" — issues #3/#4/#5.** Physical fit and vendor defaults prove
nothing on this bike, because its non-stock wiring breaks assumptions that hold everywhere else.
**Verify by function before connecting.**

---

## 5. SITTING A — everything unpowered (ohmmeter only)

> Nothing is live. This is a zero-risk sitting; do it first because it also tells you which
> connectors you will be probing in C.

### ✔ A2 — the new bar-mount switch sets (D20)

**LEFT POD: DONE 2026-09-11 — identified, harnessed and tested working.** **RIGHT POD: measured
2026-09-12** — its map is below.

#### Left pod — the map as built

The pod is wired as a **power-distribution block**, not as dry contacts: `red-white` was its +12 V
feed, shared by the horn and flash buttons, and `red-gold` was tied internally to `blue` so the flash
button injected power straight onto the high-beam output. **Two cuts turn it into independent
contacts:** `red-white` severed from the shared feed, and the `red-gold`–`blue` tie opened.

**Ground bundle — 6 wires, bundled at the pod into 1 conductor.** All are switch commons:

| Wire | Was |
|---|---|
| `yellow-orange` | hi/lo changeover common |
| `red-white` | flash common |
| `red-white` | horn common |
| `orange` | turn common |
| `orange` | hazard |
| `green-white` | hazard |

**Signals — 7 conductors:**

| Wire | Function | Input |
|---|---|---|
| `light blue` | selector in **LOW** | IN-04a |
| `blue` | selector in **HIGH** | IN-04b |
| `red-gold` | flash-to-pass | IN-09 |
| `brown` | horn | IN-03 |
| `green-black` (turn) | **LEFT** | IN-01 |
| `green-white` (turn) | **RIGHT** | IN-02 |
| `green-black` (hazard) | **HAZARD** | IN-10 |

**12 wires → 8 conductors → 7 input bits.**

⭐ **Both selector legs are read, not one.** It is a changeover, so exactly one must be asserted at any
moment — **both or neither means a broken wire or a dirty contact**, which on a headlight selector is
worth the conductor. Reading only `light blue` would make an open circuit look like a valid "HIGH".

⭐ **Hazard has its own input because of auto-cancel.** Inferring it from "LEFT and RIGHT both
asserted" is ambiguous — the push-push latches can both be set independently — and the two cases need
opposite treatment: a turn signal must auto-cancel, **hazard must never**. The hazard switch shorts all
three of its wires together, so with two of them in the ground bundle the third reads as a clean
signal.

⚠️ **Same-colour trap — sleeve these before the trios leave the housing.** `green-white` appears twice
(hazard = ground, turn = RIGHT signal) and `green-black` twice (hazard = HAZARD signal, turn = LEFT
signal). Both `orange` wires are in the ground bundle, so those two are interchangeable and safe.

#### Left pod — connector and pin map

**9-pin e-bike connector. The pod carries the FEMALE half; the MALE half goes to the ESP32 module.**
8 conductors needed, 9 pins available.

| Connector pigtail | Pod wire | Function | Input |
|---|---|---|---|
| **thick green** | ground bundle | **GND** | — |
| **thin green** | — | **not connected as built** (was to double GND; spare pin) | — |
| thick blue | `light blue` | selector **LOW** | IN-04a |
| thick yellow | `blue` | selector **HIGH** | IN-04b |
| thin blue | `brown` | horn | IN-03 |
| thin yellow | `green-black` (turn) | **LEFT** | IN-01 |
| thin red | `red-gold` | flash-to-pass | IN-09 |
| thin white | `green-white` (turn) | **RIGHT** | IN-02 |
| thin black | `green-black` (hazard) | **HAZARD** | IN-10 |

⚠️⚠️ **Read this table by PIGTAIL COLOUR AND GAUGE, never by cavity number.** Numbering on these
connectors is usually unmarked, and counting pins from one edge gives **mirrored order between the two
halves** — a map written in pin numbers is wrong on one end of the pair by construction.

⭐ **Gauge is irrelevant electrically** — every conductor carries a dry contact at **3.3 mA** (1 kΩ
pull-up to 3.3 V), and the ground bundle sees at most ~**17 mA** with everything asserted. The thick
wires are chosen for mechanical reasons only.

**As built 2026-09-11: GND is on `thick green` only; `thin green` is unused.** GND is the one conductor
whose failure kills **every** control at once, silently, at the only joint in the harness that flexes.
⬜ Tying `thin green` to the same junction doubles it for one extra solder joint — the spare pin is
there, and nothing else on the left pod needs it.

⚠️ **The cost: `thin black` is a SIGNAL, against the convention that black is ground.** It is assigned
to **HAZARD on purpose** — if it is ever mistaken for a ground and tied down, hazard reads permanently
asserted and **both indicators flash continuously.** That is a loud, immediate failure rather than a
silent dead control, which is the right outcome for the wire most likely to be misread.
⚠️ Blue and yellow also duplicate across gauges, but **both of their uses are signals** — a mix-up there
mis-maps a function instead of shorting one to ground. Less dangerous, still label it.

⭐ The two selector legs take the remaining thick wires: they are the pair where an open circuit is a
*detectable* fault (exactly one must be asserted), so they get the sturdier conductors.

⚠️ **Match wire to terminal, not to function.** A thin pod wire in a barrel sized for the thick
conductor goes intermittent or pulls out. The connector is pre-wired, so these are pigtail-to-pod-wire
splices — solder plus adhesive-lined heatshrink.

⚠️⚠️ **Colour identifies nothing on the POD side.** It duplicates `green-white` and `green-black` across
two trios **with opposite roles**. **Label both ends before soldering.**

ℹ️ The class A network (1 kΩ pull-up · 1 kΩ series · 100 nF) and the ESD array sit at the **module**
end, not the bar end — plan §4.


#### Right pod — the map as measured 2026-09-12

Three controls, **rewired by the owner onto a new connector 2026-09-12** — five conductors, one
shared ground. Nothing inside needed cutting (unlike the left pod).

| Wire | Function | Goes to |
|---|---|---|
| `blue` | **ground** — common for all three controls | module GND |
| `black` | slider — **running light**: closed in positions 2 **and** 3 | IN-08a |
| `yellow` | slider — **headlight**: closed in position 3 only | IN-08b |
| `red` | **run/off toggle** | `brake-circuit.md` §2.1 — R4 pull-up + Q2 gate; sensed on IN-11 |
| `green` | **start button** (momentary) | a spare sensed input on expander #1. The key switch alone starts the controller (plan D24), so this button drives nothing |

⭐ **The slider is the `OFF / A / A+B` pattern** — position 1 nothing, position 2 `black`, position 3
`black` **and** `yellow`. ✅ Confirmed on the rewired harness (owner, 2026-09-12): *"with the switch on
the headlight position, both black and yellow are live; with the switch in the running lights
position, only black is live."* So **"headlight implies running" is in the hardware**, exactly as D21
assumed, and the module reads it as two plain bits.

⭐ **Decode it as `headlight = yellow`, `running = black OR yellow`.** Taking running from `black`
alone would leave a broken `black` wire showing a headlight with no tail light; this way a single
open circuit still lights the bike.

⚠️ **Same-colour traps across the two pods — label both ends.** `blue` is **ground** here but the
**HIGH-beam signal** on the left pod. `black` is a **signal** here (running light) and a signal on the
left pod too (hazard), against the convention that black is ground. `yellow` is a signal here and a
signal there (selector HIGH, via `blue`), and `green`/`red` differ from the left pod's `green-*` and
`red-*` trios only by the suffix.

✅ **The toggle closes `red`–`blue` in RUN** (owner, 2026-09-12), which is the sense the brake
circuit's Q2 inverter expects — and it means a broken bar wire reads as OFF.

### ✔ A3 — M8: the red button on the FarDriver throttle

The one input the whole boost scheme hangs on (**IN-07 → D4**).

1. Find its **2-pin lead** on the FarDriver throttle.
2. Ohm across the two pins: **released ______ Ω · pressed ______ Ω**
3. ⭐ **Confirm MOMENTARY** — it must return to the released reading when let go. If it latches, D4's
   HOLD mode is meaningless and the mode scheme needs revisiting.
4. Confirm it is a **clean dry contact**: neither pin should show continuity to the throttle's ground,
   supply or signal wires. **Record: ______**

### ✔ A4 — M15(a): DevKitC-1 header spacing (2 minutes, do it while the meter is out)

Measure the two header rows **centre-to-centre** with calipers. **Expect 0.9" (22.86 mm).**
**Measured: ______ mm.** ⚠️ Anything else changes the perfboard layout, so it is worth knowing before
the board is bought, not after.

---

## 6. SITTING B — the brake levers (nothing live)

> Nothing is live — ohmmeter only. The levers feed the **brake circuit** (`revv1-brake-circuit.md`),
> which cuts the motor, lights the brake lamp and signals the module. Nothing is wired to the levers
> until B1 and B2 are recorded.

### ✔ B1 — M2: find the brake-lever wires in the handlebar loom ("1T3 10")

The lever wires **travel in the handlebar loom** (connector "1T3 10"), not the throttle harness. Only
the lever pairs are re-used — they become the brake circuit's inputs (§2 there) and IN-05/06; the
rest of the loom is unused.

1. Unplug the loom at both ends. **Photograph both connector faces.**
2. Count and record the wires: colour, gauge, and which cavity.
3. With the **brake levers released**, ohm every wire against every other wire. Record the matrix.
4. **Pull each lever in turn** and repeat. ⭐ **The pair (or the wire-plus-common) that changes state
   is that lever's switch** — this is the whole measurement.
5. Note whether the change is **open→short** (normally-open) or **short→open** (normally-closed).

⚠️ **A normally-CLOSED lever switch inverts the brake circuit** (motor cut and lamp on at rest). Record
what you see, not what you expect.

| Wire (colour / cavity) | Ω, levers released | Ω, LEFT pulled | Ω, RIGHT pulled | Verdict |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |

**Record:** total wire count ______ · lever wires identified: ______ · **NO or NC** ______ ·
**one pair per lever, or a shared common** ______

### ✔ B2 — M3: the lever type (`revv1-brake-circuit.md` §4)

The brake circuit works as drawn for a **normally-open dry contact** or a **sinking open-collector
sensor output**. Only a few milliamps flow through the lever, so a reed or microswitch rating is not a
concern.

1. **At each lever, count the wires.** Two = a switch. Three = a powered sensor (supply, ground,
   signal).
2. **Two wires:** ohmmeter across the pair, released vs squeezed.
   - Open → ~0 Ω: **normally open** ✅ — works as drawn.
   - ~0 Ω → open: **normally closed** ⚠️ — don't wire it as drawn; it needs a different arrangement.
3. **Three wires:** don't power it here. Record the colours and any marking. The signal must be an
   **open-collector / open-drain output that sinks, rated ≥15 V**; ⚠️ a **push-pull 5 V output does
   not work** — it holds the brake lamp half-on. ⬜ Settle the output type from a datasheet or a
   separate bench test before connecting it.
4. If you can, open a lever housing or read the part: **reed or microswitch?**

| Lever | Wires | Colours | Ω released | Ω squeezed | Type · NO / NC |
|---|---|---|---|---|---|
| Left | | | | | |
| Right | | | | | |

→ **Results feed the brake circuit build** (step 1, `revv1-brake-circuit.md` §6) **and IN-05/06.**

---

## 7. SITTING C — FarDriver only, on the bench supply

> ⚠️ **Pack out of circuit (key OFF → XT90-S unplugged).** Power the controller from the **DP2031**.

### ⚡ Supply setup — and the one number that matters

**DP2031 CH1 + CH2 in series = 64 V max.** That is enough, but only just, and for a specific reason:

- The FarDriver's **LVC is 60.0 V** (with a +2 V derate).
- **64 V clears it; 60 V does not.** Set the supply to its **full 64 V**, not to a round 60.
- ⚠️ **Current limit: set ≥ 1 A** for the controller. At 100 mA the supply drops into constant-current
  and the load brown-out loops, which reads exactly like "won't boot".

**Recorded supply voltage for this sitting: ______ V · current limit: ______ A**

### ✔ C1 — M9: which serial wire is the controller's TRANSMIT

⚠️ **The labels are ambiguous and this is the point of the measurement.** The pinout doc gives
**brown/blue = TXD** and **red/black = RXD** — but those names are from the *controller's* point of
view in one document and the *dongle's* in another, and plan §5 M9 says outright: *"direction must be
measured, label is ambiguous."* **Tapping the wrong one gives a listener that hears nothing.**

1. Locate the 4-pin serial plug: **brown/green `BW5V` (5 V out) · brown/blue `TXD` · red/black `RXD` ·
   black GND**. ⚠️ **Never feed a 3.3 V-only adapter from `BW5V`** — it is 5 V.
2. Power the controller. **Reference the meter to the serial GND (black), not to anything else.**
3. Read the **idle level** on brown/blue and on red/black. A UART idles **HIGH** (~3.3 V).
   - brown/blue idle: ______ V · red/black idle: ______ V
4. ⭐ **The discriminating step: connect the FarDriver app over Bluetooth and watch both lines again.**
   The line that **drops away from idle / toggles** while the app is talking is carrying traffic.
   - brown/blue with app connected: ______ · red/black with app connected: ______
5. ⭐ **A DMM sees a toggling line as a sagging average — that is enough to identify it.** For the
   bitrate and frame shape, put the **MSO5074** on it with UART decode: expect **3.3 V TTL, 16-byte
   CRC frames**. Record bitrate: ______
6. **The dongle question, answered in the same sitting:** is the Bluetooth an **integrated** part of
   the controller, or a **dongle sitting on this 4-pin plug**? Look. **Record: ______**
   ⚠️ This is not cosmetic — **IN-14 is the "polite listener" tap on the dongle's transmit line**, and
   if the Bluetooth is integrated there is **no dongle TX to tap**, so IN-14 does not exist and the
   module's keepalive logic simplifies. **One UART tap instead of two.**

**Conclusion to record:** controller transmit = ______ (colour) → **IN-13** ·
dongle transmit = ______ or **N/A, integrated** → IN-14

### ⚠️ C1.5 — METER THE BOOST WIRE (10 seconds, gates a connection)

⛔ **Do this before any FET is connected to the FarDriver's boost input.** §7.1 asserts a
*"3.3–12 V pull-up inside the controller"* — **that figure is unsourced**, and the chosen wire
(`CruisePin` **PIN17**) has never been metered. The module's boost FET is an **`AO3400A`, 30 V abs max**.

⛔ **The same 30-pin harness carries pink `60VC` — a B+ OUTPUT at 72–84 V.** Landing on that instead
destroys a 30 V FET instantly, and a higher-rated one too. **This is a measurement, not a part choice.**

With the controller powered (sitting C, 64 V), meter referenced to **serial GND**:

| Wire | Idle V | Verdict |
|---|---|---|
| `CruisePin` PIN17 (boost candidate) | ______ | ✅ ≤ 15 V → the `AO3400A` is fine · ⚠️ 15–25 V → usable but thin · ⛔ > 25 V → **use the PC817 output instead** (plan §6's alternative for the boost line) |
| *(if PIN17 is unsuitable)* `ReversePin` PIN8 | ______ | Frees up when issue #6 closes |

✔ **Then the functional check §7.1 already asks for:** ground the wire → **the app shows gear `Bst`.**
⚠️ **Do not ground any wire you have not metered first.**

### ✔ C2 — M10(a): the KEY node and where the module's tap lands

Two halves. **Only (a) can be done now.**

**(a) Routing — do it now, it is a decision not a reading.** Confirm physically where the module's
fused B+ tap lands: plan §3.2.5 puts it **downstream of the XT90-S, alongside the key-switch tap**,
on its own **2 A fast-blow `KLKD002`** in an inline holder. Walk the intended path and confirm there
is room for the holder and that the tap point is reachable with the pack in place.
**Route confirmed / problem found: ______**

**(b) The 84 V reading — this WAITS for checklist Phase 7.** On the bench you will read the supply
voltage (64 V), not the pack, so the number means nothing yet. ⚠️ **What matters for IN-12 is the
divider ratio**, and that is already fixed by design: **330 k / 10 k, 84 V → 2.47 V** (plan §3.1.3).
**Nothing here blocks; confirm the real node voltage at Phase 7 and log it then.**

---

## 8. Results sheet — fill this in, it is the deliverable

| # | Measurement | Result | Date | Feeds |
|---|---|---|---|---|
| **A2** | Switch sets: wire count, contacts per position, momentary/latching, slider wiring (`OFF/A/B` or `OFF/A/A+B`) | | | IN-01…04, IN-08…11, D21 decode, board C |
| **M2** | Handlebar loom ("1T3 10"): lever wires identified, NO/NC, one pair per lever or shared | | | brake circuit inputs, IN-05/06 |
| **M3** | Lever type: wire count, NO/NC, output type if three-wire, reed or micro | | | ⚠️ **brake circuit build** (`revv1-brake-circuit.md` §4, §6), IN-05/06 |
| **M8** | Red button: released/pressed Ω, momentary confirmed, clean dry contact | | | IN-07, D4 |
| **M9** | Controller TX line identified; bitrate; dongle vs integrated | | | IN-13/14 |
| C1.5 | Boost wire (PIN17) idle voltage | | | boost FET vs PC817 |
| **M10(a)** | KEY tap route confirmed | | | D13 |
| M15(a) | DevKit header spacing (mm) | | | perfboard layout |

---

## 9. What each result changes — do these before the notes go cold

- **A2 → plan §2.0, §3.1.3 and §5.** Fill in IN-01…04 and IN-08…11 with the measured facts; the slider
  wiring sets the D21 decode. ⚠️ **If high/low is momentary, D21's interlock needs re-specifying.**
- **M2 → checklist Phase 5 and work order §3.** Mark which wires in "1T3 10" are the lever pairs; the
  rest of the loom is unused. ⚠️ **If the lever switches are normally-CLOSED**, say so loudly — it
  inverts the brake circuit and the firmware.
- **M3 → `revv1-brake-circuit.md` §4** (record the type there), then **build step 1** (§6) and run the
  **§7.1–§7.2 tests — issue #8's gate before riding**. Also checklist PHASE 5B and work order §5.3.
- **M8 → plan D4.** If it is not a clean momentary dry contact, the boost mode scheme changes.
- **M9 → plan §3.1.3.** Assign IN-13 to the measured transmit line. ⭐ **If the Bluetooth is integrated,
  delete IN-14** and note that the module needs only one RX tap — that also frees a UART.
- **C1.5 → plan §6 / D4.** Keep the `AO3400A` or move the boost output to the PC817.
- **M10(a) → plan §3.2.5.** Confirm or correct the tap position.
- **All of them → plan §5**, changing each ⬜ to ✅ with the result inline, the same way M4–M7 were
  recorded. ⚠️ **Record the actual numbers, not "as expected."**

---

## 10. If it goes wrong

- **Everything reads O.L on a connector you expected to be a switch** → check trap (1) in §4. If the
  switch is illuminated, the ohmmeter cannot see through the LED. Sweep it powered.
- **Two wires you expected to be a pair are not** → check trap (2). Stop matching by colour.
- **A live reading makes no sense** → check trap (3). Confirm your reference is a real ground, and that
  the supply's output is actually enabled.
- **The controller will not power up on the bench** → check the supply is at **64 V**, not 60, and that
  the current limit is not throttling it (§7).
- **You cannot tell the two serial lines apart even with the app connected** → put the scope on them.
  A DMM's averaging can hide a low-duty-cycle line; a scope cannot.
