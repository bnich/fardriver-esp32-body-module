# REVV1 ESP32 body module — planning document

**Status:** v0.10, 2026-09-18 — design; first parts ordered 2026-09-10, most received 2026-09-18.
The left bar pod is wired and tested; no module hardware is built.

⏸️ **The Chaojie CAN dash feed (§7.2 / D8) is parked by owner decision D19, 2026-09-10** — *"the
display we have now will either not work, or take too long to setup … we will come back to the
display later, and either figure it out or replace it."* **The rest of the module carries on.**
Parked is neither solved nor abandoned: the CAN findings stay correct, the CAN hardware stays fitted,
and the work resumes unchanged when the display question re-opens. Also parked with it: **D11** and
**block F** (`bom.md`).

⭐ **Construction path (owner, 2026-09-08): breadboard → generic perfboard prototype (§9.6) → custom
PCB (§9.8).** The DevKitC-1 is the prototype board only, and most of §3.1.3's pin constraints are
DevKit artifacts. The custom build is **four stacked boards — HVIN · CONV · DRV · BRAIN (§9.2)** —
around a bare WROOM-1, with **D16 full native**, which takes I2C out of the lighting path. Carry the
*rules* across, not the GPIO numbers.

✅ **M13 is closed:** the module is an `ESP32-S3-WROOM-1-N8` (8 MB quad flash, no PSRAM,
−40…+85 °C) on a DevKitC-1 **v1.0** (RGB LED on GPIO48). GPIO35/36/37 and GPIO38 are usable: clean
pool **28**, **21 native used, 7 spare** (§3.1.3). D18: use an `N8` on the custom board too.

**Where the design stands:**
- ✅ **Power block (board E) sourced and ordered** — TDK `CN150B110-12/CO` + Cincon `EC7BW-110S05`
  (§9.5.1), bulk cap `EKXJ221ELL221MM25S`, hold-up diode `1N4007`, fast-blow `KLKD002` (§9.5.2).
- ✅ **12 V rail measured: 2.62 A / 31 W worst case** (§3.2.3).
- ✅ **TVS: `SMCJ90A`** — holds the rail under TDK's 160 V ceiling to 13.4 A of surge (§3.2.1).
  ⬜ **M17** confirms it on the bike.
- ✅ **D13 soft-start FET: `IXTP26P20P`**, selected on SOA and ramped over **~50 ms** (§3.2.5).
  Low-side FET: `AO3400A` (§6.2.3).
- ✅ **D16 decided: full native on the custom board** — every lighting channel on its own S3 pin, the
  I2C expanders carrying bar inputs only (§9.8.2). The pin map drawn in §3.1.3 is the **DevKit
  prototype's**, which keeps low beam and boost native and puts the slow outputs on expander #2.
- ✅ **Starting (D24, owner 2026-09-18):** the key switch feeds the FarDriver KEY wire directly
  (§3.2.5). There is no start latch; the right pod's start button is a spare sensed input.
- ✅ **Brake circuit (D23, 2026-09-11)** — each lever cuts the motor (FarDriver `BL`), lights the brake
  lamp through P-FET Q1 and signals IN-05/06, all through 1N4148 steering diodes with no firmware in
  the path (`brake-circuit.md`; the hardware sits on DRV, §9.2). The brake lamp is not a module
  output, but it is fed from the module's 12 V rail; the motor cut needs nothing from the module.
- ✅ **D17: the module has no screen** — the Chaojie is the only display; with D8 parked the **WiFi
  page is the primary readout** for motor temp, controller temp, bus current, boost mode and lamp-out.
- ✅ **Controls (D20–D22):** both original bar pods are replaced by bought switch sets — plain class-A dry
  contacts, a 3-position lighting slider, a 3-position turn switch (§2.0).

**⬜ Open:**
- **Watchdog period (§7)** — a safety figure, ≤300 ms; measure the real reset-to-lamp-on time.
- **M3** — the brake-lever switch type gates the brake circuit build (`brake-circuit.md` §4).
- **M18** — the enclosure cavity. Gates every board outline, and the enclosure material is decided
  after it (§9.7).
- **The custom stack's height does not yet close:** 71.1 mm derived from the netlist's part heights
  against 64.0 mm available at the *estimated* cavity — provisional until M18 and the enclosure land,
  binding after. The inter-board connector family (M19) sets two of the gaps (§9.2).
- **DC-DC #1's dissipation at the real 31 W load** — unverified; measure it before any thermal
  budget is trusted (§3.2.3).
- Measurements: **M2 · M3 · M8 · M9 · M10** (bench session), M14 current at exactly 12 V, M15, M17,
  M18, M19.

**⭐ CRITICAL PATH (every step is display-independent, D19):**

| | Step | Why here |
|---|---|---|
| **1** | ✅ **Sourcing and first order** — orders placed 2026-09-10; most lines received 2026-09-18. Remaining lines are estimates — **`bom.md`** owns parts, prices and order state | Longest lead time. ⚠️ A 25% tariff appeared on the Mouser line (BOM). ⛔ Block F is not in this order — it parks with D11 |
| **2** | ◐ **Bench session M2 · M3 · M8 · M9 · M10**, plus ohming out the new switch sets — ✅ **left pod done 2026-09-11** (identified, harnessed, 9-pin connector fitted, all controls tested working); ✅ **right pod in hand 2026-09-12 — its lighting slider measured `OFF / A / A+B`, which is what D21's decode needs (§2.0)** — procedure: **`inputs-bench-session.md`** | Gates the input conditioning (**block C**) and the firmware's input map. Needs the *bike*, not the parts. ⚠️ **M3** (unpowered lever-type check, `brake-circuit.md` §4) gates the brake circuit; its step 1 — levers → FarDriver `BL` — goes on as soon as M3 passes |
| **3** | ⬜ **Firmware** — lighting lookup (§7), read-the-slider-at-boot, the **≤300 ms** watchdog, boost HOLD/TOGGLE, the **WiFi status page** | The WiFi page is the only readout for temps, bus current, boost mode and lamp-out |
| **4** | ⬜ Breadboard → perfboard prototype (§9.6) → the four-board custom set (§9.2, §9.8) | Needs 1–3. ⬜ **M18** (the cavity) gates the board outlines |

## Contents

- **§1** Purpose and scope
- **§2** What exists on the bike
  - **§2.0** The control map (D20/D21/D22)
  - **§2.1** Harness — where the lever and lamp wires run
- **§3** Inputs plan
  - **§3.1** Board — ESP32-S3 DevKitC-1 (D6)
    - **§3.1.1** Signal budget · **§3.1.2** S3 pin constraints · **§3.1.3** ⭐ Pin map
  - **§3.2** Power architecture (D9, D10)
    - **§3.2.1** Two converters, the 160 V rule, the TVS · **§3.2.2** Orderly shutdown ·
      **§3.2.3** Current budget and input fusing · **§3.2.4** Grounding · **§3.2.5** Module power
      switching (D13) · **§3.2.5a** How the bike starts (D24) · **§3.2.6** Fuse and diode sizing
  - **§3.3** Display power and reset
- **§4** Electrical interface classes
- **§5** Bench discovery — the measurements this plan depends on
- **§6** Outputs
  - **§6.0** Common-ground lamps → high-side switching · **§6.0.1** Colour trap · **§6.0.2** Where
    the lamp commons land
  - **§6.1** MOSFETs, not relays
  - **§6.2** Driver circuits — **§6.2.1** channel inventory · **§6.2.2** discrete fallback ·
    **§6.2.2a** `TPS4H160B` · **§6.2.3** low-side · **§6.2.4** protection
- **§7** Behaviour rules — turn signals, lighting, brake light, boost, startup, watchdog
  - **§7.1** Boost path
  - **§7.2** CAN (⏸️ parked) — **§7.2.1** what the vendor documents give · **§7.2.2** active probing ·
    **§7.2.3** community evidence · **§7.2.4** M16
- **§8** Decisions
- **§9** Component breakdown and build plan
  - **§9.1** Breadboard rules · **§9.2** Functional blocks and the four-board set · **§9.3** Breadboard allocation ·
    **§9.4** Bench supply · **§9.5** Converters and support parts · **§9.6** Perfboard prototype ·
    **§9.7** Housing · **§9.8** Custom PCB and module variant (D18)
- **§10** BOM → `bom.md`
- **§11** Sources
- **§12** Appendix — sourcing evidence for the selected parts

📄 **Documents cited by file name:** `bom.md` and `inputs-bench-session.md` sit beside this file;
`brake-circuit.md`, the work order, checklist, build sheet and issues log are in the build repository
(`Revv1-FS-72v-Conversion/docs/`); `can18-investigation.md` and `pinout-3in-cj-v3-01.md` belong to
`chaojie-display-protocol`, and `harness-pinout.md` and `heb_decode.py` to
`fardriver-nd72450-reference` — two repositories that are not yet published (§11).

---

## 1. Purpose and scope

An ESP32 box on the **72V side** that:
1. **Listens** to the FarDriver's serial stream (every field the app sees: volts, line/phase amps,
   watts, rpm, gear, MOS temp, motor temp, faults, throttle, brake state).
2. **Serves that data on a WiFi status page** — while the CAN feed is parked, the primary readout for
   motor temp, controller temp, bus current, boost mode and lamp-out — and **feeds the Chaojie dash
   over CAN** once that work resumes (⏸️ D19).
3. **Owns the body electronics:** headlight (LOW / HIGH / DRL), horn, tail running light, front + rear
   turn signals, dash telltales, and the boost button. **The brake light is not a module output** —
   the brake circuit switches it in hardware (D23, `brake-circuit.md`); the module senses the
   levers.

⚠️ **The module has no screen of its own (D17): the Chaojie is the only display.**

**Build phases:** P0 bench sniff → P1 listener + WiFi page → **P2 body electronics** → P3 CAN feed to
the Chaojie (§7.2). ⏸️ **P3 is parked (D19)** and runs last and optionally; the bike is complete and
rideable without it.

**The module is built and brought up incrementally (D1).** The bike runs today with no lights; each
lighting function goes live as its output is built and tested. Everything on the bike shares the 72 V
pack's negative (B−). The original handlebar pods are replaced by the new switch sets whenever those
are wired (D20).

## 2. What exists on the bike

### 2.0 The control map — ⭐ BOTH PODS IN HAND (left 2026-09-11, right 2026-09-12) (D20 · D21 · D22)

Both original pods go; two bought bar-mount switch sets carry every control. **Every one is a plain
class A dry contact to the module** (D20).

| Control | Type | Bits | Input | Function |
|---|---|---|---|---|
| **Turn** | **Push-push latch, self-centring button** — left pod | **2** | IN-01/02 | Push left → latched left and the button springs back; press again to unlatch. The latch is electrical and hidden, so **there is no visible state** — the dash telltale is the only indicator. **Edge-driven:** `open→closed` starts, `closed→open` stops. **Auto-cancel: 20 s above 15 km/h, or 60 s regardless**, stopping the lamp and marking that latch cycle spent so the still-closed contact cannot restart it. Both sides latch independently, so **press opposite = switch sides** is a firmware case. 85 ± 10 cpm. ⚠️ Auto-cancel needs speed from IN-13 — with no serial link, fall back to the 60 s timeout alone |
| **Lighting** | 3-position slider — **right pod**, `black` + `yellow`, common `blue` | **2** | IN-08 | **1 OFF · 2 RUNNING** (DRL + tail) **· 3 HEADLIGHT** (DRL + tail + a beam). ✅ `OFF / A / A+B` measured 2026-09-12 — `black` in 2 and 3, `yellow` in 3. §7 truth table |
| **High/Low** | ✅ **2-position** — confirmed on the pod | 1 | IN-04 | Only has a consumer when the slider says headlight, so **the interlock holds in hardware**. HIGH replaces LOW |
| **Horn** | ✅ **momentary** — confirmed | 1 | IN-03 | Sounds while held; no latch, no timeout |
| **Hazard** | ✅ **latching** — confirmed | 1 | IN-10 | Both signals together; works with every other light off. **Required** — a push-push latch gives no "both" gesture either |
| **Flash-to-pass** | ⭐ **the REAR momentary on the left pod** (headlight symbol) | 1 | IN-09 | Rear-facing, index-finger, headlight-marked: the conventional position. ⚠️ **Break-before-make** against LOW; ≤10 ms debounce; no-op if already HIGH |
| **Run/off toggle** | ✅ latching — **right pod**, `red` + `blue` common | 1 | IN-11 (sense) | **The secondary kill.** It holds `BL` low through the brake circuit's Q2 inverter (`brake-circuit.md` §2.1) — hardware, not firmware; the module only senses it. ⛔ Not the 84 V KEY line — no DC rating on a bar switch |
| **Start button** | ✅ momentary — **right pod**, `green` + `blue` common | 1 | spare (sense) | **Spare.** A class-A contact sensed on expander #1 with no function assigned — the key switch alone starts the controller (D24, §3.2.5a). Wired now, assigned in firmware later |
| **Boost** | momentary | 1 | IN-07 | On the FarDriver throttle, not a pod. HOLD/TOGGLE, D4 |
| **Brakes** | lever switches (type per **M3**) | 2 | IN-05/06 | The lever itself cuts the motor and lights the brake lamp in hardware (D23); the module reads it through the brake circuit's D3L/D3R with 10 kΩ pull-ups (`brake-circuit.md` §2) |

**12 of expander #1's 14 input-capable bits** (GPA7/GPB7 are output-only, §3.1.3) — the left pod's 7
(the selector takes two), the right pod's 4, and the throttle's boost button. Rule for the spares:
**wire them now, assign them in firmware later** — the bar-to-box cable is the irreversible part; the
function is one line of code.
⬜ **Still to ohm out:** ⭐ **that the left pod's push-push latch really breaks contact on unlatch**
(latched = closed, unlatched = open).
⚠️ **The two pods share colours for different jobs:** on the right pod (rewired 2026-09-12) **`blue` is
the ground** for all three controls, `black`/`yellow` are the slider bits, `red` the toggle and `green`
the start button; on the **left** pod `blue` is the HIGH-beam signal and `black` carries hazard.

**Other controls and interfaces on the bike:**

| Item | Where | What it is | Source |
|---|---|---|---|
| Brake levers | both | One switch or sensor each. Type, NO/NC and wiring **to be measured (M3)** — the brake circuit's gate | `brake-circuit.md` §4; `inputs-bench-session.md` §6 |
| Throttle red button | FarDriver throttle (installed, D2) | One momentary button on a **2-pin lead** — a dry contact | checklist Phase 5; FarDriver pinout doc |
| Chaojie dash keys | 3" display housing | Five keys, `M` / `+` / `−` functional, two reserved, all internal to the display — the 9-pin plug has no key-output position | `CJ-V3-01` manual; M11 |
| PAS cadence sensor | cranks / bottom bracket | **3-pin connector — +5 V, GND, Hall pulse.** Orphaned: it belonged to the retired stock controller, and **the FarDriver has no PAS input**. Using it for assist would mean the module synthesising a throttle signal, putting firmware in the motor-control path — which D10, the open-drain boost output and the D23 brake circuit all exist to avoid. ⬜ **Cap it, or wire it as telemetry only** (the expanders have free input bits; nothing would act on it). ⬜ Confirm it is cadence: ~5 V across two pins, third pulses several times per crank revolution | seen on the bike, 2026-09-11 |
| Key switch | frame | 2-wire switch feeding the FarDriver KEY wire; it also gates the module's power switch (§3.2.5) | work order §2 |
| FarDriver serial | controller harness | TXD / RXD / BW5V / GND, 3.3V TTL, 16-byte CRC frames | `harness-pinout.md` §4 |
| Chaojie dash | bars | telltale inputs L / R / headlight (0–15V), one-line in, CAN | `pinout-3in-cj-v3-01.md` |

### 2.1 Harness — where the lever and lamp wires run

The **brake-lever wires run in the handlebar loom to connector "1T3 10"**; the **lamp feeds run in the
"2T4 18" loom**. The lever wires go to the brake circuit (`brake-circuit.md`) and the lamps to
the §6 outputs; the handlebar pods are replaced (D20). **M2** identifies the lever wires in the loom,
**M3** the lever type.

There is no PAS on this build; the power, key and speed functions sit with the key switch (KEY), the
FarDriver and the Chaojie dash. Speed, battery % and faults show on the Chaojie over the one-line
feed; the module parses everything from IN-13 and shows the rest on the **WiFi page**.

## 3. Inputs plan

Interface classes are defined in §4. "Measure" = a row in the §5 bench table.

| ID | Input | From | Type | Expected electrical | Class | Function(s) | Notes |
|---|---|---|---|---|---|---|---|
| IN-01 | Turn LEFT | left pod — **`green-black`** (turn trio) | push-push latch, self-centring button | dry contact to the ground bundle | **A** | **Edge-driven:** `open→closed` starts, `closed→open` stops. Auto-cancel 20 s >15 km/h or 60 s, marking the latch cycle spent | ✅ **Built and tested 2026-09-11** |
| IN-02 | Turn RIGHT | left pod — **`green-white`** (turn trio) | push-push latch | dry contact | **A** | As IN-01. Both sides latch independently, so **press opposite = switch sides** is a firmware case | ✅ **Built and tested** |
| IN-03 | Horn | left pod — **`brown`** | momentary | dry contact | **A** | horn while held; no latch, no timeout | ✅ **Built and tested** |
| IN-04 | High/low selector — **2 bits** | left pod — **`light blue`** (LOW) + **`blue`** (HIGH) | 2-position changeover | dry contact | **A** | `highbeam = slider in pos 3 AND selector HIGH`. ⭐ **Both legs are read:** exactly one must be asserted, so **both or neither = broken wire or dirty contact** — reading only `light blue` would make an open circuit look like a valid HIGH | ✅ **Built and tested** |
| IN-05 | Brake, left lever | lever switch or sensor (**M3**) | momentary | normally-open dry contact, or a sinking open-collector output (M3) | **A**, through the brake circuit | boost safety-release (§7); telemetry. The lever itself cuts the motor and lights the brake lamp in hardware (D23) | **M3.** Read through the brake circuit's D3L with a **10 kΩ** pull-up — not the 1 kΩ bar value: the circuit's R1 already wets the contact (`brake-circuit.md` §2) |
| IN-06 | Brake, right lever | lever switch or sensor (M3) | momentary | as IN-05 | **A**, through the brake circuit | as IN-05 | M3. Through D3R |
| IN-07 | Red button | FarDriver throttle 2-pin lead | momentary | dry contact | A | **boost request → module → controller** (D4): hold or toggle mode, long-press switches mode | M8 |
| IN-08 | Lighting slider — 3 position | right pod — **`black`** (IN-08a) + **`yellow`** (IN-08b), common **`blue`** | latching, 3-position | dry contact — **two bits** | **A** | **D21: 1 = OFF · 2 = running · 3 = headlight.** ✅ **`OFF / A / A+B` confirmed 2026-09-12:** `black` closes in 2 and 3, `yellow` only in 3 — so "headlight implies running" is in the hardware. ⭐ Decode **`headlight = yellow`, `running = black OR yellow`**, so a broken `black` still lights the bike. Full table: §7 | ✅ measured. Read at boot |
| IN-09 | Flash-to-pass | left pod — **`red-gold`**, the rear headlight-marked button | momentary | dry contact | **A** | Holds HIGH while pressed, any lighting state. **Break-before-make** against LOW; ≤10 ms debounce; no-op if already HIGH | ✅ **Built and tested.** Needed two cuts in the pod: `red-white` off the shared feed and the `red-gold`–`blue` tie opened |
| IN-10 | Hazard | left pod — **`green-black`** (hazard trio) | latching | dry contact | **A** | Both signals together; works with every other light off. ⭐ **Its own input rather than "LEFT+RIGHT both asserted" because a turn signal must auto-cancel and hazard must never** — and two independent push-push latches make that inference ambiguous | ✅ **Built and tested** |
| IN-11 | Run/off toggle | right pod — **`red`**, common **`blue`** | latching, **closed in RUN** (confirmed 2026-09-12) | 0–5 V node (R4 pulls it to `ACC+`) | **B** — 100 k / 240 k divider into expander #1 (sense only): **3.19 V at the pin** with `ACC+` at 5.1 V. R4's 10 kΩ is loaded by Q2's gate network (100 Ω + 100 kΩ) and by this divider, which puts the node at 4.52 V; 3.19 V is 0.55 V above the `MCP23017`'s 2.64 V V<sub>IH</sub> and 0.11 V under its V<sub>DD</sub>. ⬜ Meter it | The cut itself is hardware: the toggle drives the brake circuit's **Q2** inverter, which holds `BL` low in OFF (`brake-circuit.md` §2.1). The module reads the same node for the WiFi page and telltales. ⛔ **Never the FarDriver KEY line** — it sits at 72–84 V and a 12 V-market bar switch has no DC rating; it would also take the lights down with the motor | wire it now |
| IN-12 | KEY state | the key-switch output node `KSW`, **upstream of the hold-up diode** (§3.2.2) — the same node that feeds the FarDriver KEY wire (§3.2.5) | level | 72–84V | B (divider) | orderly shutdown, wake logic, and key state for the WiFi page | M10 |
| IN-13 | FarDriver telemetry | serial TXD/RXD | UART 3.3V | 16-byte frames | E | gear, faults, brake/throttle state as cross-checks, temps and currents for the WiFi page (and the parked CAN feed, §7.2) | M9 — direction must be measured, the label is ambiguous |
| IN-14 | Dongle activity | BT dongle's TX to the controller | UART 3.3V | | E | "polite listener": module sends keepalive only when the dongle is silent | M9 |
| IN-15 | 12V rail sense | DC-DC output | analog | 0–15V | D | diagnostics, lamp-out detection later | |
| IN-16 | Ambient light | photodiode/LDR | analog | | D | auto headlight (optional) | parked |
| IN-17 | Kickstand | none stock | — | — | — | not fitted; leave a spare class-A input | |
| — | Chaojie housing keys | 3" display | — | internal | — | not module inputs — five keys, all internal to the display (M11) | pin 6 (red, "reserved") is the only candidate output |

**Input count:** 11 digital class-A/B, 2–3 analog, 2 UART RX (+1 TX).

### 3.1 Board — **ESP32-S3 DevKitC-1 (DECIDED 2026-09-07, D6)**

Capabilities read from ESP-IDF v5.5's own `components/soc/<target>/include/soc/soc_caps.h`:

| | **ESP32-S3** ✅ | ESP32-C6 | ESP32-H2 |
|---|---|---|---|
| Cores | **2 × Xtensa @ 240 MHz** | 1 × RISC-V @ 160 | 1 × RISC-V @ 96 |
| **WiFi** | yes | yes (WiFi 6) | **NO** |
| BLE | yes | yes | yes |
| **TWAI (CAN)** | 1 | **2** | 1 |
| UART | **3** | 2 HP + 1 LP | 2 |
| GPIO (silicon) | **49** (0–48, less 22–25) | 31 | 28 |
| ADC | 2 units / 10 ch | 1 / 7 ch | 1 / 5 ch |
| LEDC (PWM) ch | **8** | 6 | 6 |

**Why the S3:**
1. **Pin count.** The S3-DevKitC-1 breaks out 36 GPIOs; the C6-DevKitC-1 ~23, the H2 fewer.
2. **UART headroom.** Two independent RX taps (IN-13 controller TX, IN-14 dongle TX) plus one TX. The
   C6's two HP UARTs would both be consumed; the S3 has 3, with the console on native USB.
3. **Two cores.** Bus work (two serial streams, and the fixed-cadence CAN transmit when §7.2 resumes)
   pinned to one core, WiFi to the other, so a WiFi callback cannot jitter the bus.

**Not the H2** — no WiFi, and the WiFi page and OTA are required. **Not the C6** — its one advantage is
a second TWAI controller; an `MCP2515`/`TCAN330` on SPI recovers that for a few dollars if ever needed.

**Toolchain:** ESP-IDF **v5.5** at `/root/esp/esp-idf` (tools in `/root/.espressif`), all three
targets present.

#### 3.1.1 Signal budget

Everything native would exceed the clean pool of 28 (5 analog, 2 brake inputs, the bar inputs,
3 serial, 2 CAN, 6 `TPS4H160B` lighting inputs, 3 diagnostic control, low-side gates, boost, display
switch). It is closed in §3.1.3 by putting the slow signals on two I2C `MCP23017` expanders at zero
pin cost: **21 native, 7 spare.**

⚠️ **Analog constraint:** the two `TPS4H160B` current-sense pins (`CS1`/`CS2`) must land on **ADC1 =
GPIO1–10** (ADC2 dies with WiFi), alongside IN-12, IN-15 and IN-16 — 5 of ADC1's channels.

**Rules that govern the map:**
- **PWM loads stay on native LEDC pins** — cooling fan and buzzer. An expander cannot PWM.
- **Boost is a dedicated native GPIO with a hard external pull-down.** §7 requires it open-drain and
  default-off; behind a bus, a garbled frame could assert boost.
- **Brake inputs IN-05/06 stay native** — the boost safety-release (§7) wants them in under 10 ms.
- The other class-A inputs go behind an `MCP23017`.

💡 **Pins to buy back if ever needed:** skip ON-state open-load diagnostics — tie `DIAG_EN` low and
the budget drops by **5 pins**, 2 of them ADC1 (`DIAG_EN`, `SEL`/`SEH` and both `CS` pins exist only
for lamp-out detection, §6.2.2a).

#### 3.1.2 S3 pin constraints — read before changing the pin map

Verified against IDF v5.5 headers unless noted:
- **ADC1 = GPIO1–10 · ADC2 = GPIO11–20.** ADC2 is unusable while WiFi is on, so **IN-12, IN-15 and
  IN-16 must land on GPIO1–10.**
- **GPIO26–32 are the SPI flash (MSPI)** — never available. On octal-PSRAM parts (`R8`/`R16V`)
  GPIO33–37 are also gone; ours is an `N8`, so GPIO35–37 are free.
- ⛔ **GPIO33 and GPIO34 exist on the silicon but not on the module.** The `ESP32-S3-WROOM-1` /
  `-WROOM-1U` has no pads for them (module datasheet, pin table), so nothing can ever land there.
- **GPIO22–25 do not exist on the S3.** Every existing pin can drive an output.
- **GPIO19/20 are USB D−/D+** — reserved; the console/flash path is native USB, which frees a UART.
- **GPIO43 = U0TXD** emits the ROM boot log at 115200 baud on every reset → **never a load driver.**
- ⚠️ **Strapping pins GPIO0, 3, 45, 46** (S3 datasheet; bench-confirm before committing the map).
  **No wire that leaves the box may land on these.** GPIO0 is the boot-mode pin — a rider holding a
  brake lever at key-on that grounds GPIO0 puts the module into download mode and it never runs: no
  lights, no dash, on the road.
- **Boot state — one rule (D14): every output gate is biased OFF.** GPIOs are inputs for the ~200 ms
  of boot, so each output's default is whatever its bias says:
  - **Lighting (high-side):** the `TPS4H160B`'s internal input pulldowns hold every channel OFF while
    the S3 pin is high-Z (§6.2.2a). The discrete fallback (§6.2.2) pulls its P-FET gate up to +12 V.
  - **Low-side** channels (horn, buzzer, fan, boost): ~10k gate **pull-down**.
  - With no hardware default-ON, **the watchdog is the only protection** against a firmware hang
    leaving the bike dark (§7).
  - ⚠️ **One exception, and it is not a lamp: the display power switch (§3.3) is default-ON** — a hung
    module then leaves the dash powered and still showing the one-line feed's speed/volts/faults.
- The module sits on the **72V ground, the same ground as the FarDriver**, so the class-E serial taps
  are direct 3.3V with no isolation.

#### 3.1.3 ⭐ PIN MAP (⚠️ the PROTOTYPE map — see §9.8)

Most of the constraints below are DevKitC-1 artifacts, not silicon; a custom board with a bare
WROOM-1 gets pins back (§9.8). Carry the *rules* to the custom board, not the GPIO numbers.

Verified against ESP-IDF v5.5's headers (`soc/esp32s3/include/soc/adc_channel.h`: ADC1 = GPIO1–10,
ADC2 = GPIO11–20; `soc_caps.h`: GPIO22–25 excluded, 3 UARTs, 1 TWAI, 8 LEDC) and Espressif's
DevKitC-1 user guide for what the headers break out.

##### The pin pool — 36 broken out, **28 clean**

| Class | GPIOs | Verdict |
|---|---|---|
| Broken out on J1 + J3 | 36 of the 45 that exist | — |
| ⚠️ **Strapping — GPIO0, 3, 45, 46** | 4 | internal-only signals. No wire that leaves the box |
| ⚠️ **USB D− / D+ — GPIO19, 20** | 2 | reserved (native USB console/flash) |
| ⚠️ **GPIO43 = U0TXD** | 1 | ROM boot log on every reset → never a driver |
| ⚠️ **GPIO48 — onboard RGB LED** | 1 | this board is a **v1.0** (LED on GPIO48, read off the board 2026-09-09). ⚠️ On a v1.1 the LED is on GPIO38 instead — read it off the board, never assume. A custom board has no onboard LED (§9.8) |
| ✅ **Clean pool** | **28** — 1, 2, 4–18, 21, 35, 36, 37, 38, 39, 40, 41, 42, 44, 47 | of which **9 are ADC1** (1, 2, 4–10) |

⚠️ **GPIO44 (U0RXD) is driven by the onboard CP2102N** whenever the USB-UART bridge is enumerated.
Usable, but the last spare.

##### Slow signals ride I2C; fast, analog and safety-critical stay native

The `TPS4H160B` inputs are ordinary logic inputs, so the slow half can move onto I2C expanders at
**zero extra pins** (they share the bus). This is safe for the D14 boot-state rule: `MCP23017` pins
power up as **high-Z inputs**, and every `TPS4H160B` input has a specified **100/175/250 kΩ internal
pulldown** — a high-Z drive is a hard OFF.

✅ **The prototype runs D16 (b)** (owner, 2026-09-08); the custom board runs **(a) full native**
(§9.8.2). An I2C bus failure takes out everything on the bus at once, and this
box sits beside a controller chopping 80 A on a protocol whose only error check is an ACK bit.
Mitigations — short traces inside one sealed box, strong pull-ups, the §3.2.4 star ground, a firmware
bus-recovery routine (clock SCL nine times to free a slave holding SDA) — are mitigations. **So the
channels that matter when things go wrong stay native, in hardware:**

| Stays NATIVE, and why | Rides the expander |
|---|---|
| **Headlight LOW** — the one lamp whose loss at night is dangerous | headlight HIGH · headlight DRL · tail running · turn L · turn R |
| **Boost** — a garbled bus frame must never assert boost (§7.1) | the bar inputs |
| **Brake inputs IN-05/06** — the boost safety-release wants < 10 ms | `DIAG_EN` · `SEL` · `SEH` |
| **Fan and buzzer** — need LEDC PWM | |
| **All analog** — ADC1 only | |

The brake lamp is not on this list at all: the brake circuit switches it in hardware (D23).

##### The map

| GPIO | Signal | Notes |
|---|---|---|
| **1** | IN-12 — KEY sense | ADC1_CH0; 330 k/10 k divider (§4 class B). 84 V → 2.47 V |
| **2** | IN-15 — 12 V rail sense | ADC1_CH1 |
| **4** | `CS1` — TPS4H160B #1 current sense | ADC1_CH3 (GPIO3 skipped — strapping) |
| **5** | `CS2` — TPS4H160B #2 current sense | ADC1_CH4 |
| **6** | IN-16 — ambient light (optional) | ADC1_CH5 |
| **7** | **Display power switch** (§3.3) | ⚠️ the only default-ON output — pull-up on the gate |
| **8** | Horn — low-side FET gate | 10 k gate pull-down |
| **9** | `MCP23017` INT | |
| **11** | TWAI TX → `SN65HVD230` | |
| **12** | TWAI RX ← `SN65HVD230` | |
| **13** | I2C **SDA** | the two `MCP23017` expanders |
| **14** | I2C **SCL** | |
| **15** | IN-05 — left brake lever, via the brake circuit's D3L | wire leaves the box → clean pin, TVS at the connector; 10 kΩ pull-up |
| **16** | IN-06 — right brake lever, via D3R | as GPIO15 |
| **17** | UART1 **TX** → controller | 1 k series; tri-state whenever not sending (§4 class E) |
| **18** | UART1 **RX** ← controller TX (IN-13) | listen-only tap |
| **21** | UART2 **RX** ← dongle TX (IN-14) | listen-only tap |
| **39** | **Cooling fan** — LEDC PWM | JTAG MTCK — JTAG is given up; debug over native USB |
| **40** | **Buzzer** — LEDC PWM (tones + the turn-signal click, §6.1) | JTAG MTDO |
| **42** | **Headlight LOW** → TPS4H160B #1 `IN2` | native by design (D16) |
| **47** | **Boost** → controller | dedicated pin, open-drain, hard external pull-down; never on a bus |
| — | **Spare: GPIO10, 35, 36, 37, 38, 41**, plus GPIO44 as a last resort — **7 spare** | plus the 4 strapping pins for internal-only signals in a pinch. ⚠️ This margin is the prototype's; the custom board has none to give (§9.8.2) |

💡 **Full-native lighting is reachable on the prototype** — moving expander #2's six `TPS4H160B` inputs
native costs 6 of the 7 spare pins and drops the second `MCP23017`, leaving 1 spare. **Don't** — the
custom board (§9.8) is where full native lives; keep the prototype's margin.

**Expander #1 — inputs (12 of its 14 input-capable bits):** IN-01 turn L · IN-02 turn R · IN-03 horn ·
**IN-04 high/low (two bits)** · IN-07 red button · **IN-08 lighting slider (two bits)** · IN-09
flash-to-pass · IN-10 hazard · IN-11 run/off sense · the spare start button. IN-05/06 (brakes) are
**not** here — native for §7's <10 ms. 2 input bits spare, so a bar control added later needs only a
wire.
⛔ **`MCP23017` pins GPA7 and GPB7 are OUTPUT-ONLY** (Microchip DS20001952 rev D) — never land an
input on them, and have firmware set `IODIR` bit 7 to output on both ports. That is why a 16-bit
expander offers 14 inputs.
**Expander #2 — outputs (8 of 16):** TPS4H160B #1 `IN3`/`IN4` and #2 `IN1`–`IN4` for headlight HIGH,
DRL, tail running, turn L, turn R (5 channels + 1 spare) · `DIAG_EN` · `SEL` · `SEH`.
TPS4H160B #1 `IN1` is tied to ground on the custom board (on the prototype it is left to its internal pulldown). **Six of the eight channels
are used; two are spare.**
*(Two devices, same bus, different addresses — 2 GPIO total.)*

##### ⬜ To confirm before committing the map

- ✔ **Bench-confirm the strapping pins:** boot with each of GPIO0, 3, 45, 46 grounded and confirm
  only GPIO0 blocks a normal boot.
- ✔ Confirm the `TPS4H160B` reads a high-Z `MCP23017` output as OFF, on the bench, before trusting
  the boot-state argument on the bike.

### 3.2 Power architecture — **DECIDED 2026-09-07 (D9, D10)**

**Nothing is live with the key off (D9)** and **the module never drives the FarDriver KEY (D10)** —
it only senses it on IN-12. The key switch stays a purely mechanical thing, so a hung or confused
module can never cut motor power or switch the bike on. **The topology is the §3.2.5 diagram.**

#### 3.2.1 Two converters, the 160 V rule, and the TVS

DC-DC #2 exists so that **a lamp or horn fault cannot brown out the brain** (the S3 browns out around
4.4 V at its 5 V pin). It costs **~$57 net** over deriving 5 V from the 12 V rail with a $5 buck — a
real trade, still recommended.

| | Input | Output | Feeds |
|---|---|---|---|
| **DC-DC #1** | **43–160 V** | **12 V** — load **2.62 A / 31 W** (§3.2.3) | headlight, tail, signals, horn, fan, display switch |
| **DC-DC #2** | **43–160 V** | **5 V** | the logic. Prototype: the DevKit's `5V` pin and its onboard 3.3 V regulator. BRAIN: a bare module has no regulator, so a `TLV76733` (5 V → 3.3 V, 1 A) feeds it |

⚠️ **The input rating is 160 V — and that is architectural, not margin.** A 100 V-rated die **cannot be
protected at all**: the TVS must not conduct below the controller's **90.7 V** OV-protect, and every
TVS with a standoff that high clamps far above 100 V under surge. TDK publishes **no absolute maximum**
and states **160 VDC is a hard instantaneous ceiling** — input ripple *peaks* must stay inside it,
ripple capped at 10 V p-p. **Treat 160 VDC as do-not-exceed including transients.** At 84.0 V the pack
sits at ~53% of it; a 90.7 V excursion is 57%.

✅ **TVS: `SMCJ90A`.** Clamp voltage is a function of surge current, not a constant, so the criterion
is the surge current each part holds below TDK's 160 V:

| | Package | V<sub>C</sub> | at I<sub>PP</sub> | R<sub>dyn</sub> | **Surge held below 160 V** | Price |
|---|---|---|---|---|---|---|
| ✅ **`SMCJ90A`** (1500 W) | DO-214AB | **146.0 V** | **10.3 A** | **4.47 Ω** | **13.4 A** | **$0.47** |
| `SMBJ90A` (600 W) | DO-214AA | 146 V | 4.1 A | 11.2 Ω | 5.4 A | $0.58 |

*(Both: V<sub>RWM</sub> 90.0 V · V<sub>BR</sub> 100.00–111.00 V at 1 mA · I<sub>D</sub> 1 µA · 10/1000 µs,
from the Littelfuse tables.)* Same standoff and clamp; the SMC die reaches it at 2.5× the current,
for less money.

- **Not `SMBJ100A`** — its 162 V clamp exceeds TDK's 160 V ceiling.
- **Not `5KP90A`** — axial leads are a lead-fatigue geometry on a vibrating machine; DO-214AB is
  surface-mount.
- **13.4 A is ample:** this is a battery node, not an automotive one — **no load dump**, no alternator,
  regen OFF. The transient sources are cable inductance × di/dt (a short branch off B+, ~1–2 µH;
  interrupting even 125 A stores ½LI² ≈ **16 mJ**, against the SMCJ's ~1.5 J — ~100×) and converter
  switching, which TDK bounds with the 10 V p-p ripple cap.
- **Standoff margin:** 90 V against 84.0 V full charge is 7%, thinner than the usual 10–20%. Acceptable
  because V<sub>BR</sub> min is **100 V** — real conduction starts above the 90.7 V OV trip. ⬜ Read
  I<sub>R</sub> vs temperature at 84 V if the box will sit hot.
- Cincon names `P6KE180A` for EN 50121-3-2 railway surge testing — a 180 V standoff for a different
  design point; it would never conduct here.
- ⬜ **M17** — scope the module's B+ tap to confirm (§5). Does not block ordering.

⚠️ **Bench hazard:** do **not** feed the DevKit's `5V` pin from the bike while USB is also plugged in —
two sources fighting. Unplug the 84 V feed while flashing, or put a Schottky in the 5 V feed.

#### 3.2.2 Orderly shutdown — the ride-out cap, no latch circuit

D9 means the module dies with the key, so it needs stored energy to park its outputs on the way down:
- DC-DC #2 is fed through a **blocking diode** — plain silicon (`1N4007`, §3.2.6(a)) — with **≥220 µF /
  200 V** on its input.
- **IN-12 senses KSW *upstream* of that diode.** Key off → IN-12 collapses immediately while the diode
  strands the cap's charge on the converter.
- The D13 switch itself releases late — up to ~0.8 s after key-off (§3.2.5) — which only lengthens the
  ride-out. Design against what C2 alone guarantees.

**Sizing.** The floor is the converter's **UVLO (38 V** on the Cincon `EC7BW-110S05`), and a DevKitC-1
idles at ~**1 W**. ⚠️ **Size from the LVC, not full charge:** key-off from a sagging pack starts at
**60.0 V**, giving ½C(60² − 38²) = **237 mJ ≈ 237 ms at 1 W** for 220 µF. **Design against 237 ms.**

⚠️ **TWO capacitors, not one** — the two duties sit on **opposite sides of the diode**:
- **C1 — TDK's "100 µF or more"** at **DC-DC #1's input terminals**, as close as possible — its primary
  EMI-and-stability measure. DC-DC #1 is **upstream** of the diode.
- **C2 — the hold-up cap**, **behind the diode on DC-DC #2's input**.
Both are Chemi-Con `EKXJ221ELL221MM25S` (220 µF / 220 V, BOM E8; §9.5.2). TDK asks for two in parallel below −20 °C to cut ESR;
at this build's −10 °C floor one per node is enough.

⚠️ **The ride-out figure is load-dependent.** Cincon's own hold-up table (at 72 Vdc: **180 µF buys
10 ms**, 560 µF 30 ms) is measured at the module's **full 20 W**. The 237 ms assumes the module sheds to
~1 W within milliseconds of key-off; if shedding lags, ride-out collapses toward tens of ms, and buying
it back with capacitance would take 5,600–11,200 µF.
✅ **So do not depend on ride-out for anything that matters: write NVS on change, not at shutdown.**
Key-off then only has to park the outputs (microseconds). Firmware still **drops WiFi first** on
key-off detect — it is by far the largest sheddable load.

#### 3.2.3 Current budget — ✅ M4–M7 measured 2026-09-08: **2.62 A / 31 W**

| Load on the 12 V rail | Current | Gate |
|---|---|---|
| **Headlight LOW (8.5 W)** | **0.71 A** | ✅ M4 |
| **Headlight HIGH (8.5 W)** — *replaces LOW, not additive* | **(0.71 A, exclusive with LOW)** | ✅ M4 · D14 |
| **DRL (6.5 W)** | **0.54 A** | ✅ M4 |
| **Tail running** | **0.05 A** | ✅ M5 |
| **Tail STOP** — switched by the brake circuit's Q1, not a module channel | **0.12 A** | ✅ M5 |
| **Turn signals, one side (front + rear)** | **0.10 A** | ✅ M6 (front assumed = rear) |
| **Measured subtotal** | **1.62 A** | one beam only (D14) |
| Still estimated: fan 0.50 · display (if on 12 V) 0.40 · telltales 0.10 | 1.00 A | ⬜ M14 for the display |
| **WORST CASE TOTAL** | **≈ 2.62 A = 31 W** | night · one beam · DRL · braking · signalling · fan |
| Horn — electronic | **0.10 A** | ✅ M7 |

The whole lighting system is LED; the horn is an **electronic 12 V horn drawing 0.10 A**.
⚠️ **Use 2.62 A / 31 W everywhere.** Never count both headlight beams — D14 forbids it (worst case one
beam + DRL = **1.25 A**).

**Thermal — ⬜ DC-DC #1's dissipation at this load is unverified.** TDK's **91.5 %** is the
*full-load* efficiency (150 W). The measured 31 W is **~21 % of rating**, where a brick's fixed
losses dominate and efficiency is lower. Applying 91.5 % anyway gives **~2.9 W** — a floor, not an
estimate. ⬜ **Measure it; the converter, the bench supply and a load are in hand:** draw 2.6 A from
the 12 V output and read the input power, at the bench supply's 64 V ceiling (§9.4) and again at pack
voltage. No baseplate temperature is final until that number exists.
- **Limits:** baseplate −40…+100 °C, over-temperature trip at 105–120 °C, so target T<sub>b</sub>
  ≤ 85–90 °C. ⚠️ The 60 °C ambient used for that target is an assumption — re-check it once the box
  has a mounting position.
- **The brick is conduction-cooled, so it bolts to a thermal interface** — metal that carries its heat
  out of the enclosure — whichever enclosure is built. The enclosure material is decided after
  **M18** (owner, 2026-09-18), and the boards assume neither answer; §9.7 states the requirement.
- **Not the `HAQ-10T`** (7.5 °C/W, a free-air figure; BOM E5): a finned sink sealed inside a box only
  heats the trapped air, and 25.4 mm of fin on a 12.7 mm brick does not fit the stack (§9.2).
- ⚠️ **An over-temperature trip takes the whole 12 V rail down** — every lamp, the horn, and the brake
  lamp with them (§7). The thermal path is a lighting-safety item.

✅ **Converter: keep the TDK `CN150B110-12`** — ~4.8× oversized, but smaller parts in this series cost
*more* (§9.5.1).

**Input fusing.** TDK-Lambda's instruction manual **mandates a FAST-BLOW fuse** of 10 A or lower,
sized with I²t headroom for turn-on inrush, on the **+Vin leg** when −Vin is ground. Cincon asks for a
**1 A time-delay** on the logic rail. D13(b)'s soft-start is what makes a fast-blow viable, by removing
the inrush that would otherwise nuisance-blow it. **Value: 2 A** (§3.2.6(b)).

**Input current is computed at the 60.0 V LVC, not at 84.0 V.** A converter is a **constant-power**
load: as the pack sags, input current rises, so a full-charge figure under-sizes by ~40% exactly when
the pack is weakest.

| Rail | Power in | @ 84.0 V (full) | @ 72 V (nom) | **@ 60.0 V (LVC)** ← size here |
|---|---|---|---|---|
| **12 V load** — measured, 31 W out | **34 W** | **0.41 A** | 0.47 A | **0.57 A** |
| **5 V logic** — realistic ~2.5 W out | **3 W** | 0.04 A | 0.04 A | **0.05 A** |
| **Module total** | **37 W** | **0.44 A** | 0.51 A | **0.62 A** |

⚠️ **Two sizing rules:**
1. **Size every fuse, choke and input conductor at the LVC current, never at full charge.**
2. **Size at the MEASURED load, never at the converter's nameplate** (150 W nameplate at the LVC gives
   3.13 A — five times the real 0.62 A).

✅ **The module's B+ tap fuse is 2 A** (3.2× the 0.62 A LVC draw): Littelfuse `KLKD002` — §3.2.5, §9.5.2.

#### 3.2.4 ⚠️ Grounding — the rule that quietly corrupts the serial taps if skipped

**Reference the module's ground to the CONTROLLER's B− stud, not the battery's B−.**

80 A of chopped motor current through the B− cable drops real volts across it, and the module reads
the FarDriver's **3.3 V TTL** serial *referenced to controller ground*. Ground the module at the
battery and that IR drop, plus PWM switching spikes, arrives as common-mode noise on IN-13/IN-14. One
star point, at the controller B−.

**Non-isolated converters are correct:** common ground is what the serial taps and the CAN transceiver
want; correct star grounding buys what isolation would.

#### 3.2.5 Module power switching — the key switch stays a logic switch (D13)

**The problem is inrush, not steady current.** Closing a mechanical contact onto the module's bulk
capacitance at 84 V produces a spike limited only by wiring resistance — **tens of amps for a few
hundred microseconds, every key-on** — which pits and welds contacts. The steady draw (**~0.62 A at
the LVC**, §3.2.3) is no problem for the key branch's 2 A fuse.

**Adopted: D13 (b) — the key switch gates a soft-started P-MOSFET high-side switch.**

⚠️ **The diode sits DOWNSTREAM of the P-MOSFET, with the hold-up cap behind it on DC-DC #2 ALONE.** Put
the cap on the common node instead and it has to ride out DC-DC #1's 31 W as well — hold-up collapses
from ~237 ms to **~20 ms**.

```
XT90-S out ─┬──────────────────────────────────────────── Controller B+
            │
            ├─[2A fuse]─● KEY SWITCH ●─┬─────────────────  FarDriver KEY wire
            │                           └───────────────── D13 enable + IN-12 sense, ~0.32 mA
            │                                                      │
            │                                                      ▼
            └─[2A FAST]── P-MOSFET high-side switch ──┬──[C1 ≥100µF/200V]──┐
              KLKD002     (soft-start ~50 ms, §3.2.6a) │   TDK's EMC bulk,  │
              600VDC                                   │   at #1's terminals│
                                                       ├────────────────────┴── DC-DC #1  84V→12V
                                                       │                          LOAD rail
                                                       │
                                                       └──▶│──┬── DC-DC #2  84V→5V
                                                        1N4007 │   LOGIC rail
                                                       [1A slow]│
                                                       0001.2504│
                                                                └─[C2 220µF/200V]
                                                                   hold-up, §3.2.2
```
⚠️ **IN-12 senses KSW *upstream* of the diode** (§3.2.2), so key-off collapses the sense line
immediately while C2 keeps the logic alive.

Why this is the right answer:
1. **The key switch carries only the FarDriver KEY wire plus two resistor dividers — ~0.32 mA at
   84 V** (the D13 enable divider, 0.08 mA, and the IN-12 sense divider, 0.25 mA). An ordinary 72 V
   e-bike key switch is correct (~$10–15, already in the build sheet); its documented 12–96 V spec
   governs and no current rating is needed.
2. **Soft-starting the gate eliminates the inrush** rather than making a contact survive it. The
   ~50 ms ramp also keeps input dv/dt far inside TDK's ≤10 V/µs limit.
3. **The §3.3 display switch is the same idea at a far smaller C** — a soft-started high-side P-FET
   (parked with D11).
4. **The work order, checklist and build sheet keep their wiring** — the key switch still feeds the
   FarDriver KEY wire through its ~2 A inline fuse, low-current logic only, and golden rule #2 is
   untouched. The module adds one tap on the key-switch output.

**The gate network** (on HVIN, §9.2). Q101 is the `IXTP26P20P`, source on the fused B+ tap, drain to
the converters:

| Part | Value | What it protects |
|---|---|---|
| `R110`, gate → source | 100 kΩ | D14's bias-OFF: V<sub>GS</sub> = 0 with the key off |
| `D102`, gate → source | 15 V zener | the FET's ±20 V gate rating |
| `C105`, gate → **drain** | 68 nF, C0G or film, **≥250 V** | the Miller capacitor: it sets the output slew, and so the ramp. With the switch off it sees the full pack — check its voltage line |
| `C107`, gate → source | 4.7 µF, ≥25 V | divides down the dV/dt that `C105` couples into the gate when the XT90-S is mated with the key OFF: 84 V × 68 n / (68 n + 4.7 µ) ≈ 1.2 V, under V<sub>GS(th)</sub>, so the FET stays off |
| `R101`, gate → pull-down switch | **540 kΩ — 2 × 270 kΩ in series** | the turn-on current, and with `R110` the on-state V<sub>GS</sub>; two parts share the voltage |
| `Q105`, the pull-down switch | **`BSS127`** — 600 V **enhancement-mode** N-FET, SOT-23, V<sub>GS(th)</sub> 1.4–2.6 V | the only path that turns Q101 on. ⛔ **Not `BSS126`**, its depletion-mode sibling, which conducts at V<sub>GS</sub> = 0 and would hold the module on with the key off |
| `Q105`'s gate drive | key-switch output → 2 × 499 kΩ → gate → 100 kΩ to ground, with a 10 V zener and 100 nF at the gate | 84 V → 7.6 V · 60 V → 5.5 V · 43 V → 3.9 V, all above the `BSS127`'s threshold. Key off → 0 V → Q105 off → Q101 off, with zero quiescent drain |

This gives V<sub>GS</sub>(Q101) = −13.1 V at 84 V and −9.4 V at the 60 V LVC, and a simulated ramp of
≈ 51 ms at 84 V with a mid-threshold FET — 47–61 ms across the part's V<sub>GS(th)</sub> spread, 52–78 ms
at 60 V (`python3 tools/soft_start.py`, which reads the network off the netlist). Mating the XT90-S with
the key off lifts V<sub>GS</sub> to 1.2 V, under the 2.0 V minimum threshold. ⬜ All of it is computed,
not measured: scope the switched node and the B+ tap at the first key-on, and again while mating the
XT90-S with the key off — a plug-in that rings the tap up to the `SMCJ90A`'s clamp is the case to look
for.

⚠️ **Key-off is not instant.** With the key off `Q105` opens, and `C107` then discharges through `R110`
alone: Q101 stays on for up to **~0.8 s** at 84 V (~0.7 s at 60 V) before it pinches off, carrying at
most 52 W on the way down — under its DC SOA line. For that long the converters are still fed. D9's
*"nothing is live with the key off"* therefore holds from about a second after the key opens; the
zero-quiescent-drain property is untouched. IN-12 taps the key-switch output itself, so firmware sees
key-off at once, whatever Q101 is doing.

**The tap fuse is `KLKD002`, 2 A FAST-blow** (600 VDC, 50 kA DC) in an inline holder (§9.5.2) — 3.2×
the 0.62 A LVC draw. Sitting upstream in series, it also satisfies **TDK's fast-blow mandate for
DC-DC #1**, so the module has two series fuses, not three (this tap + the 1 A time-delay on DC-DC #2).
⚠️ **Deviation to log:** TDK wants the fuse on its own +Vin leg; upstream-in-series still protects it,
recorded as a deliberate choice.

Residual risk: a MOSFET failing **open** leaves the module dead — the same outcome as a blown fuse,
inconvenient, not dangerous.

⚠️ **The MOSFET is selected on SOA, not Vds/Id.** The soft-start moves the inrush energy out of the
key-switch contacts and **into the MOSFET**, which absorbs it:
- **Capacitance downstream of D13: 440 µF** — both `EKXJ221ELL221MM25S` caps (C1 and C2, BOM E8).
- **Energy:** ½CV² = **1.55 J**, **2.85 J** with the 0.62 A load during the 50 ms ramp.
- **Current at the 50 ms ramp:** C·dV/dt = **0.74 A**, **1.36 A** with the load.
- **Stress to check: 114 W @ 25 ms.** TI's conversion for V<sub>DS</sub> falling linearly at constant
  I<sub>DS</sub> over t₁ (exactly a soft-start): the equal-energy square pulse is **P<sub>MAX</sub> at
  t₁/2** — so read an SOA line at or beyond **25 ms** at full V<sub>DS</sub>, not a line at the average.
- **Simulated on the real gate network** (`python3 tools/soft_start.py`, across the FET's threshold
  spread at 84 V): peak **80–94 W**, **3.2–4.0 J** in the FET — the ramp's slow tail keeps the load on
  it longer than the ideal ramp's 2.85 J assumes — against an SOA of **219–241 W** at the equal-energy
  pulse width. The 114 W ideal-ramp figure stays the number the part is selected against.

✅ **Selected: IXYS `IXTP26P20P`** (TO-220AB, laid flat and bolted; BOM E13). Its datasheet
**DS99913D** draws forward-bias SOA at both T<sub>C</sub> = 25 °C and **70 °C**, each with 25 µs,
100 µs, 1 ms, **10 ms, 100 ms and DC** lines, and guarantees 160 W at −200 V / 5 s / 70 °C. Read off the
70 °C plot at 84 V (±10 %): **≈460 W on the 10 ms line · ≈254 W on the 100 ms line · ≈191 W DC.**
**The 114 W demand clears even the DC line at T<sub>C</sub> 70 °C, by 1.7×.** At key-on the FET's
case sits at ambient, which this plan puts at 60 °C — under the plot's 70 °C, so no further derating
applies.
⚠️ **Use DS99913D.** The 2007 "Preliminary" sheet some distributors still serve states a different
T<sub>JM</sub> and draws constant-power lines that stop at 80–100 V.
`IRF9640PbF` is an alternate, checked only on its 10 ms line (~335 W at 84 V, ~241 W derated for
60 °C). Not `FQP12P20` — it publishes no SOA plot at all.

⭐ **The ramp time is the cheapest margin available.** Nothing pushes it down: even at 10 ms the input
dv/dt is **0.0084 V/µs, 1190× inside TDK's ≤10 V/µs limit**, and a slower ramp helps the diode too.

| Gate ramp | Charge current | Total | **P<sub>peak</sub>** | Equivalent square pulse |
|---|---|---|---|---|
| 10 ms | 3.70 A | 4.32 A | **363 W** | 363 W @ 5 ms |
| 25 ms | 1.48 A | 2.10 A | **176 W** | 176 W @ 12.5 ms |
| ✅ **50 ms — the spec** | 0.74 A | 1.36 A | **114 W** | 114 W @ 25 ms |
| 100 ms | 0.37 A | 0.99 A | 83 W | 83 W @ 50 ms |

✅ **The D13 gate ramp is ~50 ms (owner, 2026-09-18)** — 3.2× less peak SOA demand than a 10 ms ramp,
for an imperceptible key-on delay. It matters most in the high-V<sub>DS</sub> / low-I<sub>D</sub>
**Spirito (thermal-instability) corner**, where the limit is local current density, so less current at
high V<sub>DS</sub> is strictly better. Past ~50 ms the gain flattens (the 0.62 A load dominates).

⚠️ **Why headline ratings cannot substitute for the curve:** SOA has five limits — R<sub>DS(on)</sub>,
current, maximum power, **thermal instability**, BV<sub>DSS</sub> — and Vds/Id cover two. Two 100 V
parts with near-identical R<sub>DS(on)</sub> and I<sub>D</sub> can differ 4× in SOA at 50 V / 10 ms. The
Spirito inflexion moves to *lower* V<sub>DS</sub> as the pulse lengthens, so a short-pulse curve cannot
be scaled to a long one — a line at or beyond the real pulse length must be published. Where a plot is
drawn only at T<sub>C</sub> = 25 °C, derate it for T<sub>Jmax</sub> 150 °C and a 60 °C ambient by
(150−60)/(150−25) = **0.72**; the `IXTP26P20P`'s 70 °C plot needs none. ⛔ **No SOT-23 part as the main
switch on the strength of its Vds and Id.**

ℹ️ The same arithmetic applies to the §3.3 display switch at a much smaller C — parked with D11.

#### 3.2.5a How the bike starts — the key switch feeds KEY directly (D24)

**The key switch starts the controller, and nothing else does** (owner, 2026-09-18). Its output feeds
the FarDriver KEY wire directly, exactly as the §3.2.5 diagram draws it; the module takes one tap off
that node, for the D13 enable and the IN-12 sense.

- **The module never sources or switches KEY (D10).** No module part is in series with the KEY wire,
  so a hung, reflashing, unpowered or absent module cannot switch the controller on or off.
- **There is no start latch and no start gesture.** The right pod's start button is a **spare sensed
  input** on expander #1 (§2.0).
- **The secondary kill is the run/off toggle**, which holds `BL` low through the brake circuit's Q2
  (`brake-circuit.md` §2.1) — hardware, sensed by the module on IN-11. It stops drive; it does
  not remove KEY.
- ⬜ **M10** still measures the KEY node — its voltage, and where the module's tap lands.

#### 3.2.6 Fuse and diode sizing

**(a) The hold-up diode is sized by SURGE, not leakage.** Leakage is irrelevant — the cap holds up for
milliseconds, so even 100 µA costs 0.32% of its charge. What governs is the **surge charging 220 µF at
key-on**, set by the D13 soft-start rate:

| D13 soft-start ramp | Peak diode current (I = C·dV/dt) |
|---|---|
| 1 ms | 18.5 A |
| 10 ms | 1.85 A |
| **50 ms** ✅ | **0.4 A** |

**Spec:** ≥150 V reverse, ~1 A continuous, surge ≥3 A, plain silicon — **`1N4007`** (§9.5.2). Its 1 ms
rating (45 A) covers even the 1 ms case, and at the 50 ms ramp the key-on surge (0.4 A) is inside the
part's continuous rating. A Schottky's low V<sub>f</sub> buys nothing at 0.1 A; fast recovery buys nothing on
a diode that switches once per key cycle.

**(b) DC-DC #1's input draws 0.41 A at 84 V, 0.58 A at the LVC.** A **2 A fast-blow** gives 3.4× — ample
above the steady draw once the soft-start has bounded inrush, and tight enough to protect the wiring.
TDK's "10 A or lower" is a ceiling, not a target. The `KLKD002` at the tap provides it (§3.2.5).

### 3.3 Display power and reset — **the module owns pin 2 (decided 2026-09-07)**

The module switches the Chaojie's supply so it can **power-cycle the dash**: the display took eight
trials to talk at all (issue #7), and a desynced CAN impersonation (§7.2) is exactly the failure a
reset clears.

- ⚠️ **HIGH-SIDE ONLY. Never switch pin 3 / B−.** The display's ground is the shared system ground and
  its signal pins reference it — **pin 9** goes to the FarDriver brown lead and **pins 7/8** carry the
  module's CAN. Float that ground and current back-feeds through the signal wires.
- **Default state = ON.** If the S3 hangs, the display stays powered and its one-line feed still shows
  speed, volts and faults — a dead module degrades to a dumb dash, not a black one. **"Reset" is a
  deliberate momentary pull-off of ~2 s.**
- **Soft-start the gate** (~1 ms) — the display's input is an internal buck, a capacitive load. (The
  module's own D13 switch ramps over ~50 ms with a gate-to-drain Miller capacitor, §3.2.5; this load
  is far smaller. Size the network the same way when D11 re-opens.)
- **Pin 2 keeps its own ~2 A fuse** (work order §3.1); the module's switch goes in series with it.
- ⚠️ **Fit a ~1k series resistor in pin 9.** While the module holds the display dark, the FarDriver
  still drives its one-line output (0–15 V on the brown lead) into an unpowered input — current flows
  through the input's ESD clamp, and can hold the panel partly alive so it never cleanly resets. 1k
  limits it and does not trouble a slow single-ended signal.
- ⚠️ **Pins 7/8 (CAN) and the telltale feeds see the same reset window.** For CAN the fix is firmware:
  **halt TWAI transmission before asserting the display reset, and resume only after the panel has
  booted** (ISO 11898-2 transceivers present a high-impedance interface when unpowered, so the hardware
  risk is low). The telltale feeds (pins 1/4/5) are live 12 V lamp feeds (§6.2.1); their ~1 k series
  resistors handle it, as for pin 9.
- **No display is on the bike as of 2026-09-11** (it runs on a temporary throttle and key switch).
  When a display is fitted it feeds from switched B+ (work order §3.1), installed at checklist
  Phase 7.
- **Switch class = D11 (parked, D19):**
  - **12 V feed** → a 60 V P-MOSFET off the 12 V load rail, or a load-switch IC.
  - **Pack-voltage feed** → a 150 V P-MOSFET with a zener-clamped gate, or preferably a
    **photovoltaic-coupled MOSFET SSR** (a photovoltaic gate driver on back-to-back 150 V N-FETs):
    arc-free, with its control side isolated from the 84 V node.

**Interim (D19):** with D11 and board F parked, the dash feeds from switched B+ exactly as work order
§3.1 has it, and the module takes pin 2 over at P2 at the earliest. **Keep the design; defer the
part** — a dash that can be power-cycled from the module is worth having whichever panel ends up fitted.

## 4. Electrical interface classes

- **Class A — dry contact to module ground** (the bar switch sets, red button, and the brake levers
  through the brake circuit's steering diodes): GPIO input, pull-up to
  3.3V, 1k series into the pin, 100 nF to ground at the pin, a TVS/ESD array on any wire that leaves
  the box — `PESD5V0S4UD` (BOM C2) on these ≤3.3 V lines; the brake-lever nodes idle near 11.4 V and
  take the 15 V array instead (§6.2.4). The two native brake inputs carry the same network split across
  the stack: the pull-up and the 1 k series resistor on DRV, the 100 nF at the MCU pin on BRAIN
  (τ = 100 µs, well inside their <10 ms budget). Firmware debounce 20 ms (≤10 ms for flash-to-pass, §7).
  ⚠️ **Wetting current sets the pull-up.** 4.7 kΩ to 3.3 V puts only **0.70 mA** through the contacts —
  fine for gold-plated domes, marginal for a cheap automotive switch: tin and silver contacts commonly
  specify a **1–10 mA minimum**, below which oxide and sulfide films make contact resistance erratic,
  and these switches live on a handlebar in the weather. **Use 1 kΩ → 3.3 mA on every channel driven by
  a bought switch** (11 mW; the RC with 100 nF stays ~100 µs). Firmware debounce does not help:
  intermittent contact resistance reads as a non-press, not as chatter.
  All bar controls are class A (D20). Gesture decoding (short/long press) is needed only on the boost
  button, IN-07.
  **The brake inputs IN-05/06 take a 10 kΩ pull-up, not 1 kΩ:** the brake circuit's R1 already puts
  ~1.2 mA through the lever contact, and 10 kΩ keeps the low level, seen through a 1N4148, near
  0.55 V — inside the S3's input-low limit of 0.25 × VDD ≈ 0.8 V (`brake-circuit.md` §3).
- **Class B — 12V or 72V level sense:** resistor divider to < 3.3V (72V: 330k / 10k, the top resistor
  as a series pair of 2 × 165 k for voltage rating) and 100 nF. No separate clamp: the 330 k top
  resistor holds the injected current to microamps even at the input TVS's 146 V clamp level.
- **Class D — analog:** ADC pin with divider and 100 nF; average in firmware.
- **Class E — FarDriver serial:** direct 3.3V, 1k series on the module's TX, TX pin tri-stated (input
  mode) whenever the module isn't sending; both RX lines are listen-only taps.

## 5. Bench discovery — the measurements this plan depends on

📄 **M2 · M3 · M8 · M9 · M10 have a written bench procedure: `inputs-bench-session.md`** —
unpowered sittings (sitting B is the brake levers, M3) and a 72 V bench-supply sitting. The procedure
carries four traps: **the ohmmeter cannot see through an LED assembly**, **colour is never evidence on
this bike**, **a floating reference lies**, and **"it fits so it must be right"**. ⚠️ **M3 gates the
brake circuit build** (`brake-circuit.md` §4).

| # | Measure | How | Result |
|---|---|---|---|
| M1 | **The new switch sets (D20)**, unplugged: each switch's contact pair, momentary or latching, and ⚠️ **how the 3-position slider is wired** (OFF/A/B or OFF/A/A+B — the D21 decode depends on it). Bench session A2 | ohmmeter, new parts on the bench | ⬜ on arrival |
| M2 | Handlebar loom ("1T3 10"): which wires are the **brake-lever wires** — the only wires in that loom the build re-uses | ohmmeter unplugged | ⬜ |
| M3 | **Brake levers, unpowered** (`brake-circuit.md` §4): wire count per lever; NO/NC by ohmmeter, released vs squeezed; a three-wire sensor must have a **sinking open-collector output rated ≥15 V** (push-pull does not work); one pair per lever or shared. **Gates the brake circuit build** | ohmmeter unplugged (bench session sitting B) | ⬜ |
| M4 | ✅ **Headlight (2026-09-08):** stamped on the housing (PN `25012001WX`): **LOW 12 V / 8.5 W = 0.71 A · HIGH 12 V / 8.5 W = 0.71 A · DRL 12 V / 6.5 W = 0.54 A.** Wire map: **BLACK = common ground · GREEN = HIGH · BLUE = LOW · YELLOW = DRL · RED = unused.** ⚠️ **Identify LED assemblies by powered sweep, never by ohmmeter** — all 10 pairs read O.L, because a 12 V LED driver + string cannot be forward-biased by a meter | housing + DP2031 | ✅ |
| M5 | ✅ **Tail (2026-09-08):** shares a 5-wire connector with the rear signals. **BLACK common · YELLOW running 0.05 A · RED STOP 0.12 A**, 12 V. Running and stop are **separate feeds**, not PWM | DP2031 | ✅ |
| M6 | ✅ **Rear signals (2026-09-08):** in the tail connector, **BLUE = left · GREEN = right**, 12 V, **0.05 A each**. Front pair: isolated 2-wire each. ⬜ Front currents assumed equal to rear; ⬜ confirm the front pair's return can share the tail common before paralleling | DP2031 | ✅ |
| M7 | ✅ **Horn (2026-09-08):** **electronic, 12.0 V, 0.10 A** (1.2 W), loud; 3-wire, internal driver PCB `LB001`. ⛔ **Colour trap: `+` = BLUE, `−` = BLACK — red is NOT the positive** (role unconfirmed) | DP2031 | ✅ |
| M8 | Red button: 2-pin continuity pressed / released; confirm momentary | ohmmeter | ⬜ |
| M9 | FarDriver serial: idle level on brown/blue and red/black, which toggles with the app connected (= controller transmit line); dongle on the 4-pin plug or integrated? | voltmeter / scope | ⬜ |
| M10 | KEY node voltage and where the module's fused tap lands | voltmeter | ⬜ |
| M11 | ◐ **Chaojie keys:** the `CJ-V3-01` manual gives **five keys, `M`/`+`/`−` functional, two reserved**, all internal; backend entry is **hold `+` and `−` together within 15 s of power-on**. Software version read: `CJ-YQ25-250418`. ⏸️ Remainder (meter pins 1, 4–9 to pin 3 while pressing each key, to confirm no key drives a wire) parked with the display (D19) | voltmeter | ◐ |
| M12 | ✅ **Closed — impossible by design.** `CANConfig` 60 saved and exported: the `.heb` CAN block is empty, because `CAN` is an *instruction number* selecting a firmware-internal protocol, not a table (§7.2.1). Do not retry with other values | app + decoder | ✅ negative |
| M13 | ✅ **Closed.** Module `ESP32-S3-WROOM-1-N8` (8 MB quad flash, no PSRAM, −40…+85 °C) — GPIO35/36/37 usable, 25 °C clear of the 60 °C ambient. Board **DevKitC-1 v1.0** (RGB LED on GPIO48) — GPIO48 excluded, GPIO38 usable. Pool **28**, spare **7** (§3.1.3). Does not carry to the custom PCB (§9.8) | off the board | ✅ |
| M14 | ◐ **Display supply.** ✅ Boots at 12 V — and at 7 V. The `CJ-V3-01` manual rates **DC 12–120 V** and **70 mA ± 20 mA at 12 V**; the bench read **~0.22 A** at an unconfirmed supply voltage. ⬜ **Re-measure at exactly 12 V**, noting backlight level (`pinout-3in-cj-v3-01.md` §1.1); ⬜ sweep 12/24/48/64 V to confirm constant-power behaviour. ⚠️ **Set the bench current limit to 500 mA** — at 100 mA the supply goes into CC and the panel brown-out loops, which reads exactly like "won't boot". The dash's V field reads pin 2, not the link (D11) | bench PSU + ammeter | ◐ |
| M15 | Proto-board geometry, on arrival: (a) DevKit header rows centre-to-centre — expect **0.9" (22.86 mm)**; (c) **copper weight** (1 vs 2 oz — sets the ~2.4 A vs ~3.6 A trace limit, §9.6.2); (d) meter top-to-bottom continuity to see whether plated through-holes join the layers | calipers + ohmmeter | ⬜ |
| M16 | ⏸️ **Answered, then parked (D19).** The Chaojie never ACKs: 17 bitrates (10K–1M), standard and extended IDs, TEC pinned at 128, 0 ACKs, panel silent — with the bus proven one node at **68 Ω** at the breakout, grounds bonded, the display's transceiver proven live, and the rig validated (loopback 8/8 correct · 0/8 disconnected · 0/8 reversed). The vendor says the panel speaks **FarDriver CAN 18** by default, so it reads as a **receive-only node** (confidence MEDIUM): the module transmits in `TWAI_MODE_NO_ACK` and the remaining gap is the **CAN 18 byte map (D8)**. 📄 `can18-investigation.md` — ⛔ its §4.1 pre-flight gate is mandatory before any CAN bench work | MSO5074 + ohmmeter + a CAN node | ⏸️ parked |
| M17 | **Transients on the 84 V node.** MSO5074 on the module's B+ tap, referenced to controller B−. Capture (i) hard acceleration at the 80 A cap, (ii) a deliberate key-off under load, (iii) XT90-S mate/unmate with the key OFF. Record worst peak voltage, current into the clamp, duration. Expectation (§3.2.1): nothing near the `SMCJ90A`'s 13.4 A / 160 V limit. Does not block ordering | MSO5074 + current probe | ⬜ |
| M18 | **The enclosure cavity** — the old-controller cavity under the battery compartment, where the four-board stack lives (§9.2). Usable length; width **at the narrowest point along the run**; clear height **along the whole run**, floor to the underside of the battery tray; what the floor is made of and whether it sees moving air; where cables can exit; any intrusion partway along. Working figure until measured: **200 × 50 × 70 mm — an estimate.** Gates every board outline and the enclosure-material decision (§9.7) | tape + calipers | ⬜ |
| M19 | **Part heights that set each gap in the stack** (§9.2) — **the inter-board connector family first: its mated height sets two of the gaps**; then every part not yet read from a manufacturer drawing. Read so far: CM choke `7448022010` **22.0 mm** tall (18.0 × 14.0 mm footprint); `IXTP26P20P` upright 17.5–21.8 mm and the Y2 discs upright 15.5–16.5 mm, so both lie **flat**; JST PA right-angle (latched, 3 A) 7.0 mm; the Schurter `FAC 0031.3803` holder is a **47.5 mm vertical** part and cannot go in the stack (§9.5.2) | datasheets + calipers | ◐ |

## 6. Outputs

| Output | Load | Driver | Notes |
|---|---|---|---|
| Headlight **LOW** (blue) | 12 V / 8.5 W = **0.71 A** | **high-side** smart switch (D15), default-OFF | M4. Lamp is common-ground (black), so low-side is impossible |
| Headlight **DRL / running** (yellow) | 12 V / 6.5 W = **0.54 A** | high-side, default-OFF | M4 |
| Headlight **HIGH** (green) | 12 V / 8.5 W = **0.71 A** | high-side, default-OFF | From IN-04 / IN-09. **HIGH replaces LOW** (D14), enforced in firmware |
| Tail **running** (yellow) | 0.05 A, 5-wire assembly, common = black | high-side, default-OFF | M5 |
| Tail **STOP / brake** (red) | 0.12 A, separate feed | **not a module output** — the brake circuit's P-FET Q1 switches it from the levers, in hardware, off the module's 12 V rail (D23, `brake-circuit.md`) | M5 |
| Turn **LEFT** (front + rear) | rear = **blue** in the tail plug; front = its own 2-wire pair | high-side (rear shares the tail common) | M6. 85 flashes/min — no relay (§6.1). ⬜ Confirm the front pair's return can sit on the same common before paralleling |
| Turn **RIGHT** (front + rear) | rear = **green**; front = own pair | high-side | M6 |
| Horn | electronic, 12 V / 0.10 A | **low-side** N-MOSFET on a native pin (its own pair: blue `+`, black `−`); TVS on the wire leaving the box, **no flyback needed** | M7. **D12 = MOSFET** |
| Dash telltales L / R / headlight | Chaojie pins 1 / 4 / 5, **0–15 V inputs** | **from the corresponding lamp feed through ~1 k** — not a driver channel (§6.2.1) | costs zero channels; mirrors the feed actually energised |
| **Boost to controller** | FarDriver boost input (an unused pull-down input re-assigned to `BoostPin`, §7.1) | open-drain N-MOSFET (100 Ω series) or PC817 opto; **off = no boost** by default | **D4: through the module** |
| **CAN to the Chaojie** | display pins 8 (H) / 7 (L) | ESP32 TWAI + `SN65HVD230`, 120 Ω | ⏸️ **Deferred (D19).** Build the hardware anyway — transceiver in hand, 2 GPIO, and a replacement panel is likelier to need CAN than not. Transmit in `TWAI_MODE_NO_ACK` |
| Buzzer | small 12V buzzer | low-side MOSFET, LEDC PWM | boost chirps (§7), turn-signal click (§6.1) |
| **Display power (pin 2)** | Chaojie supply | high-side switch, **default-ON**, soft-started | **§3.3.** ⏸️ D11 parked. ⚠️ Never switch pin 3 / B− |
| **Cooling fan** | 12V fan on the controller heatsink | low-side MOSFET, PWM | thermostatic from the MOS/motor temps the module already reads — this is what makes an enclosed controller bay viable (checklist Phase 3) |

Power for all of this is **§3.2** (12 V for the loads — measured worst case **2.62 A / 31 W** — and 5 V
for the logic).

⚠️ **Gate bias — one rule: every output biases OFF.** The `TPS4H160B`'s internal input pulldowns (D15)
deliver this by device design. **The display power switch (§3.3) is the sole default-ON output.**
There is **no hardware fail-safe** keeping any lamp alive through a firmware hang — D14 dropped it.
**The ≤300 ms watchdog (§7) and reading the lighting slider at boot are the only mitigation** for the
lighting. The brake light needs none: the brake circuit switches it in hardware (D23).

### 6.0 ⚠️ The lamps are COMMON-GROUND — lighting needs HIGH-SIDE switching

The headlight is **BLACK = common ground · GREEN = HIGH · BLUE = LOW · YELLOW = DRL**, and the tail is
also common (black). All functions share one ground wire, so **the only way to control them
independently is to switch each feed between +12 V and the lamp — high-side.** **All six module
lighting channels are high-side**: headlight LOW / HIGH / DRL, tail running, turn L, turn R — and so is
the brake circuit's STOP switch (Q1). Only the **horn** (its own `+`/`−` pair) is low-side, and the
telltales are fed from the lamp feeds.
**The driver board (block D, DRV) is a high-side board** with a few low-side channels.

- Every lighting feed gets a **high-side switch** — the `TPS4H160B` smart switch (D15, §6.2.2a). An
  open-drain low-side sink (e.g. the `TPIC6B595`) cannot drive a shared-ground lamp at all.
- **Gate bias is uniform: every channel OFF** (D14). No inverted special case, so no lamp can twitch at
  key-on.

#### 6.0.1 ⛔ COLOUR TRAP — the same colour means different things on every connector

| Colour | Headlight assembly | **Tail assembly** | Horn |
|---|---|---|---|
| **BLACK** | common **ground** | **common** | **−** |
| **BLUE** | **LOW beam** | **LEFT turn** | **+** |
| **GREEN** | **HIGH beam** | **RIGHT turn** | — |
| **YELLOW** | DRL / running | running | — |
| **RED** | **unused** | **STOP / brake** | **unused** |

Only `black = common` and `yellow = running` hold across assemblies. Red is unused on the horn and
headlight but is **STOP** on the tail. **Identify by function, never by colour, every time.**

#### 6.0.2 ⚠️ Where the lamp COMMONS land

- **Every lamp common (the black wires) lands on the MODULE's 12 V return**, which stars at the
  **controller B− stud** (§3.2.4) — never on a convenient frame point or an unused harness ground.
- Lamps come up one at a time as the module is built. **Unplug each lamp assembly from its original
  harness before feeding it from the module**, so its common lands only on the module's return.

### 6.1 MOSFETs, not relays — **decided 2026-09-07**

| Load | Driver | Why |
|---|---|---|
| **Turn signals** | MOSFET, mandatory | 85 cpm ≈ **1.4 Hz** — ten minutes of signalling ≈ **850 operations**; a 100k–1M-cycle relay wears out in tens of hours. For the click, **firmware clicks the buzzer** |
| **Tail running** | MOSFET (smart high-side, D15) | a plain feed (M5); the STOP feed is the brake circuit's Q1 (D23) |
| **Headlight LOW / HIGH / DRL** | MOSFET (smart high-side, D15) | modest currents, per-channel current limit |
| **Horn** | MOSFET (**D12**) | electronic 0.10 A horn — no coil, no inductive kick |
| Fan · buzzer | MOSFET | PWM |

The one place a relay-class part could earn its keep is the **display supply on pack voltage** (§3.3,
D11 parked) — and there the better answer is a **photovoltaic-coupled MOSFET SSR**: arc-free on a DC
rail no small signal relay is rated to break.

### 6.2 Driver circuits

#### 6.2.1 Channel inventory — 6 high-side, 3 low-side, 2 special

| # | Channel | Side | Current | Default |
|---|---|---|---|---|
| 1 | Headlight **LOW** (blue) | HIGH | 0.71 A | OFF |
| 2 | Headlight **HIGH** (green) | HIGH | 0.71 A | OFF · *exclusive with #1* |
| 3 | Headlight **DRL** (yellow) | HIGH | 0.54 A | OFF |
| 4 | Tail **running** (yellow) | HIGH | 0.05 A | OFF |
| 5 | Tail **STOP** (red) | — | 0.12 A | **not a module channel** — the brake circuit's Q1 switches it (D23) |
| 6 | Turn **LEFT** (rear blue ∥ front pair) | HIGH | 0.10 A | OFF |
| 7 | Turn **RIGHT** (rear green ∥ front pair) | HIGH | 0.10 A | OFF |
| 8 | Horn (own `+`/`−` pair) | low | 0.10 A | OFF |
| 9 | Cooling fan (**PWM**) | low | ~0.5 A ⬜ | OFF |
| 10 | Buzzer (**PWM**) | low | small | OFF |
| S1 | **Boost to controller** | open-drain | — | **OFF (hard pull-down)** |
| S2 | **Display power** (§3.3) | HIGH, soft-start | ⬜ M14 | ⚠️ **ON — the only one** |

**Peak simultaneous ≈ 2.62 A** (§3.2.3). **No channel exceeds 0.71 A.**

⚠️ **The dash telltales are not driver channels — drive them from the lamp feeds they mirror.** Chaojie
pins 1 / 4 / 5 are **0–15 V inputs**: a telltale lights when the lamp voltage is *applied* to it.
A low-side FET pulling such a pin to ground does nothing, and making them high-side would take the count
from 6 to 9 — past the 8 channels two `TPS4H160B` packages provide.

| Telltale | Fed from | Via |
|---|---|---|
| Turn L | channel 6 (turn LEFT feed) | ~1 k series resistor |
| Turn R | channel 7 (turn RIGHT feed) | ~1 k series resistor |
| Headlight | channel 1 or 2 (LOW / HIGH feed) | ~1 k series resistor |

Zero extra channels, and the telltale reflects **the feed actually energised** rather than firmware's
belief about it. ⚠️ **The series resistor is required** (as for pin 9, §3.3): during a display
power-cycle these feeds may be live into an unpowered input's ESD clamp.

#### 6.2.2 Discrete high-side channel — the FALLBACK only

```
        +12V ──┬──────────────┬─── source
               │             ┌┴┐  P-MOSFET
              R1 100k        │ │
               │             └┬┘
   gate ───────┴──[R2 10k]─┐  └─── drain ──► LAMP FEED ──► lamp ──► common (black)
                           │
                      ┌────┴────┐  2N7002 (small N-FET)
   S3 GPIO ──[1k]─────┤ G     D │
                      │    S    │
                      └────┬────┘
                          GND
```

- **2N7002 OFF → gate at +12 V = source → V<sub>GS</sub> = 0 → lamp OFF** — the power-up and in-reset
  state, D14's default.
- **2N7002 ON → gate divides to 12 × 10/110 ≈ 1.1 V → V<sub>GS</sub> ≈ −10.9 V → hard ON**, inside a
  ±20 V gate rating.
- **P-MOSFET:** V<sub>DS</sub> ≥ 30 V, I<sub>D</sub> ≥ 2 A, V<sub>GS</sub> ±20 V. At 0.71 A even
  100 mΩ dissipates 50 mW — choose on package and availability.

**Why D15 uses a smart switch instead: fault containment.** A lighting wire chafing to frame ground is a
dead short on the 12 V rail; a discrete P-FET passes it, and the TDK's OCP is **non-latching** — the
whole rail hiccups and **one shorted turn-signal wire takes out the headlight too.** A smart switch
current-limits *per channel*, keeping the fault local.

#### 6.2.2a ✅ Part selected — TI `TPS4H160BQPWPRQ1` (2026-09-08)

Quad-channel, 160 mΩ, 4–40 V, **2.5 A nominal per channel**, AEC-Q100 Grade 1 (−40…+125 °C),
28-HTSSOP (DigiKey `296-44711-1-ND`). **Two packages = 8 channels for the 6 needed — 2 spare.**

**It clears both hard gates by device design — no level shifter, no external pulldown:**
- ✅ **3.3 V drive, no level shifter.** V<sub>IH</sub> min **2 V** / V<sub>IL</sub> max 0.8 V across
  −40…+150 °C. TI recommends a **4.7 kΩ series protection resistor** on every logic line from a 3.3 V
  MCU — fitted on the six used `INx` and on `DIAG_EN`, `SEL` and `SEH`; through it the divider still
  delivers 3.15 V.
- ✅ **Floating input = output OFF.** Every `INx` has a specified **100/175/250 kΩ internal pulldown**,
  so the S3's ~200 ms high-Z boot window is safe **by device design** — D14's requirement.

⚠️ **Current limit and current sense DO need external parts — `CL` and `CS` each take a resistor:**
- **`CL` sets the per-channel current limit:** R<sub>CL</sub> = 0.8 V × 2500 / I<sub>limit</sub>, to
  ground. **1.00 kΩ → ≈2 A** on package #1 (the 0.71 A and 0.54 A headlight loads); **2.0 kΩ → ≈1 A**
  on package #2 (the 0.05–0.10 A tail and turn loads). With `CL` strapped to ground the part falls back
  to its internal **8–14 A** limit — on a 12.5 A converter that is no per-channel limit at all, and
  D15's fault containment is gone.
- **`CS` is a current SOURCE (I<sub>OUT</sub> / 300), not a voltage:** **1.00 kΩ 1 %** to ground turns
  it into 3.33 V/A (0.71 A reads 2.37 V). In any fault — an unplugged lamp included — the pin drives
  **4.5–6.5 V**, so it reaches the S3 only through a **10 kΩ / 10 kΩ divider** with 100 nF at the
  ADC side: a fault reads 2.25–3.25 V — above any real load, below VDD — and the working scale at the
  pin is **1.67 V/A** (0.71 A reads 1.19 V). ⚠️ TI's "10 kΩ series" advice is written for a 5 V MCU;
  on its own it leaves ~3.8 V on a 3.3 V pin.
- **TI's pin names are `VS` (supply), `SEL` and `SEH` (sense-channel select, low and high bit)** — not
  VBAT / SEL1 / SEL2. Decouple each `VS` with 100 nF + 10 µF / 25 V. `THER` tied to ground selects auto-retry
  after a thermal shutdown. Unused `INx` tie to ground, and each unused `OUTx` takes 10 kΩ to ground so
  an idle channel is not reported as an open load on the shared `FAULT` line.

⚠️ **Diagnostics cost firmware.**
- **OFF-state open-load needs an external 20 kΩ pullup from each `OUTx` to `VS` — 6 resistors.**
- **ON-state open-load is not reported on `FAULT`/`STx`.** The MCU must multiplex `SEL`/`SEH` and
  **ADC the current-sense pin**, and only **Version B** can do it. ⚠️ The divider and its 100 nF
  settle in τ ≈ 0.55 ms — firmware waits **≥ 3 ms** after moving `SEL`/`SEH`, not TI's 50 µs.
- `STx` / `FAULT` are open-drain and need their own 3.3 V pullups.
- ⚠️ The HTSSOP thermal pad must reach real copper or the current limiting and thermal shutdown will not
  behave as specified (BOM D1).

⚠️ **Domain constraint: 40 V-class part — ONLY on the regulated 12 V rail. Never the 84 V pack node.**
40 V recommended / 48 V transient abs-max against an 84 V node with a 90.7 V OVP = permanent damage. So
the §3.3 display switch can use it only on a 12 V feed (D11).

⬜ **Board decision: omit the reverse-battery GND-network diode.** With it fitted the required drive
rises to V<sub>IH</sub> + V<sub>F</sub> ≈ **2.7 V**, while an ESP32-S3 guarantees only ~2.64 V V<sub>OH</sub>
under load. Omitting it is defensible because these switches sit on a regulated DC-DC output, not a
reversible battery.

💡 **Two channels are spare** — their `INx` pins tie to ground. One could drive the §3.3 display switch on a 12 V feed.

**Not Infineon `BTS7008-2EPA`** — the only candidate that detects open load in the ON state (8/21/35 mA
thresholds), but it has **no internal input pulldown** (an external 10 kΩ per channel) and **no lamp-scale
current limit** — its overcurrent trip is ~88 A, ~124× the 0.71 A load, which defeats the reason D15
chose smart switches.
**Not TI `TPS2HB50-Q1`** (resistor-programmed per-channel limit, 1.325 A min trip at R<sub>ILIM</sub> =
25 kΩ) — ~1.9× the load may be too thin for LED-driver inrush, which has never been measured.

#### 6.2.3 Low-side channels

N-MOSFET, source to ground, drain to the load's return, **10k gate pull-down** (default OFF), gate
driven from the S3 through ~100 Ω. Part: **`AO3400A`** — genuinely logic-level (48 mΩ guaranteed max at
V<sub>GS</sub> 2.5 V); SOT-23, 30 V, with open caveats in `bom.md` (D3).
- **Horn**, **buzzer** (LEDC) and **fan** (LEDC) are each a discrete FET on a native pin — GPIO8, 40
  and 39 on the prototype map — because the fan and buzzer need PWM, which only native LEDC pins
  provide. ⚠️ Never put a FET gate on GPIO44 (U0RXD): its boot-time pull-up sits at the FET's
  threshold.
- ⚠️ **Boost (S1) is on its own dedicated native pin with a hard external pull-down** (§3.1.1).
  ⚠️ Meter the boost wire before connecting a 30 V FET to it — the controller-side pull-up voltage is
  unmeasured, and the same harness carries pink `60VC` at pack voltage (§7.1).

#### 6.2.4 Protection on every wire that leaves the box

- **A TVS array at the connector, on the same board as the connector, on every line that leaves the
  box — chosen by the line's idle voltage:**
  - **onsemi `SMS15T1G`** (SC-74 quad, V<sub>RWM</sub> 15 V, V<sub>BR</sub> 16.7–18.5 V; clamps 24.0 V at
    5 A and 29.0 V at 12 A, under the `AO3400A`'s 30 V) on every switched 12 V-class line, on the
    brake-lever nodes (they idle near 11.4 V), on `BL`, and on the boost output (its pull-up voltage is
    unmeasured, §7.1).
  - **`PESD5V0S4UD`** (same SC-74 pinout, V<sub>RWM</sub> 5 V) **only** on lines that never exceed
    3.3 V-class levels — pod inputs, UART, CAN, the USB-C CC pins. ⛔ A 5 V array on a 12 V line conducts
    continuously: a dead short across the channel it was meant to protect.
  - **`USBLC6-2SC6`** on the USB D+ / D− pair — 3.5 pF per line, where a general-purpose array's
    165–220 pF is tens of times too much for a USB pair.
  - ⚠️ **No array on the raw 12 V rail pins** that leave the box (horn +, fan +, buzzer +): the TDK's
    over-voltage window (15.0–17.4 V) overlaps the array's minimum breakdown. One **`SMBJ18A`** at
    those connectors covers them instead — the 18 V grade, because its 20.0 V minimum breakdown clears
    that window where a 15 V part's 16.7 V sits inside it, and it still clamps at 29.2 V, under the
    `AO3400A`'s 30 V.
- **Flyback:** the horn needs none — it is electronic (M7). The fan and the buzzer are inductive, and
  each gets an `SS14`-class Schottky (1 A / 40 V) across its load connector.
- **Reverse-polarity and load-dump** are bounded by the 12 V rail's own TVS — that `SMBJ18A` — rather
  than per channel.
- **No per-channel fuses** — the `TPS4H160B`'s per-channel current limit keeps a shorted lamp wire local
  instead of hiccuping the whole rail (D15).

## 7. Behaviour rules for the inputs (draft)

- **Turn signals (D22): a push-push latch whose button self-centres.** Push left → latched left and the
  button springs back to centre; press again to unlatch. The latch is electrical and hidden, so **the
  switch shows no state** — the dash telltale is the only indicator. Telltale mirrors the lamp. Flash
  **85 ± 10 cpm**. **2 input bits.**
  - **Edge-driven, not level-driven:** `open→closed` starts signalling, `closed→open` stops it.
  - **Auto-cancel: after 20 s once speed (IN-13) is above 15 km/h, or 60 s regardless.** It stops the
    lamp **and marks that latch cycle spent**, so the still-closed contact cannot restart the signal;
    the next `open→closed` is a fresh request. A rider's unlatch after an auto-cancel is a no-op.
  - **Both sides latch independently**, so the latch rules are real firmware cases: **press = on ·
    same side = off · press opposite = switch sides.**
  - ⚠️ **Auto-cancel needs speed from the serial link.** With IN-13 unavailable, fall back to the
    **60 s** timeout alone rather than leaving a signal latched indefinitely.
  - **Hazard has its own control (IN-10)** — a single push-push latch per side gives no "both" gesture.
- **Horn:** on while IN-03 is held; no latch, no timeout.

### Lighting — D14 states, set by a slider (D21)

**Everything is OFF at key-on (D14).** Two states — `running` (headlight DRL + tail running) and
`lowbeam` (headlight LOW) — plus a derived `highbeam`, only with the headlight on. The bought switch set
(D20) carries a **3-position slider** whose positions *are* those states, in order, plus a **high/low
toggle**. Lighting is one combinational lookup — no gestures, no timers, no NVS:

| Slider | Hi/Lo toggle | DRL / running (yellow) | Tail running (yellow) | Headlight LOW (blue) | Headlight HIGH (green) |
|---|---|---|---|---|---|
| **1 — OFF** | either | off | off | off | off |
| **2 — RUNNING** | either | **ON** | **ON** | off | off |
| **3 — HEADLIGHT** | LOW | **ON** | **ON** | **ON** | off |
| **3 — HEADLIGHT** | HIGH | **ON** | **ON** | off | **ON** |

What the slider buys:
1. **The illegal state is unreachable in hardware** — "low beam implies running" and the high/low
   interlock hold by construction (with the slider off, the toggle has no consumer).
2. **The state is visible** — the rider can see where the slider sits.
3. **Boot recovery reads the truth** — see restore-on-boot below.

✅ **HIGH REPLACES LOW** stays a firmware rule: position 3 + HIGH drives HIGH and **turns LOW off**, so
the worst-case headlight load is **one beam + DRL = 1.25 A**, never 1.96 A. The assembly can physically
run both; firmware must enforce the exclusion — do not rely on the toggle alone.

**Flash-to-pass (IN-09, owner 2026-09-10).** It costs only the input wire and firmware; the HIGH
channel already exists.

| Slider | Pass button held | Result |
|---|---|---|
| **1 — OFF** | held | **HIGH only** — DRL and tail stay off; a pass is a beam flash, not a lighting mode |
| **2 — RUNNING** | held | **HIGH** + DRL + tail running |
| **3 — HEADLIGHT**, toggle LOW | held | **HIGH replaces LOW**; returns to LOW on release |
| **3 — HEADLIGHT**, toggle HIGH | held | **No-op** — already on HIGH. Must not flicker |

- ⚠️ **Break before make:** de-assert LOW, then assert HIGH, and the reverse on release. The two are
  separate `TPS4H160B` channels with no atomic write; driving both at once would briefly pull 1.96 A.
- ⚠️ **Debounce ≤10 ms on press and release** — a signalling function.
- The high-beam telltale follows the lamp feed (§6.2.1), so it lights during a flash with no firmware.
- **No timeout.** ⬜ Accepted minor failure mode: a stuck pass button holds HIGH (0.71 A, thermally
  harmless). Say so if a timeout is wanted.
- ✅ **The slider is `OFF / A / A+B`** (measured 2026-09-12, §2.0): `black` closes in positions 2 and
  3, `yellow` only in 3. Decode **`headlight = yellow`, `running = black OR yellow`** — a broken
  `black` then still lights the bike instead of leaving a headlight with no tail. The high/low toggle
  is a third bit.

⚠️ **Independent of the lighting state — these work with every light off:**
- **The brake light** lights whenever a lever is pulled and the module's 12 V rail is up — the brake
  circuit switches it in hardware (D23), independent of the lighting state and of firmware.
- **Turn signals and hazard** follow their own inputs **always**.

**Restore-on-boot: read the slider.** At boot the module reads the switch position and re-asserts
lighting **within the first few milliseconds — before WiFi, before anything else.** No NVS write path,
no stale value, no disagreement between firmware and where the rider set the control. NVS is still used
for the **boost mode** (D4), which has no physical position.

⚠️ **What this does not fix:** a **hung** module drives no lamps whatever the slider says. The accepted
D14 risk — a firmware hang at night means darkness — stands, the brake light excepted. **The watchdog
is a safety figure: ≤300 ms** (below), and ⬜ the real reset-to-lamp-on time must be measured.

✅ **The brake light does not depend on firmware (D23).** Each lever, through the brake circuit's
steering diodes, switches the STOP lamp on through P-FET Q1 and cuts the motor through the FarDriver
`BL` — both in hardware (`brake-circuit.md`). The module only senses the levers (IN-05/06).
**Firmware state cannot affect either:** a hung, crashed, reflashing or unflashed module leaves the
brake light and the motor cut working. ⚠️ **Loss of the module's 12 V rail takes the lamp with it —
and not the motor cut.** The STOP lamp is fed from that rail, so a blown tap fuse, an open key tap or
a tripped converter means a dark brake lamp; `BL` is pulled low by the lever itself and needs nothing
from the module. There is no hard-brake flash: the lamp is on whenever a lever is pulled.

- **Brake inputs (IN-05/06):** read within 10 ms — they clear boost (below) and feed the WiFi page.
- **Boost (IN-07) — module in the middle (D4).** Two rider-selectable modes:
  - **HOLD:** boost output asserted while the button is held (release = off within 50 ms).
  - **TOGGLE:** short press = on, short press = off. Safety clears: any brake input, key-off, a
    configurable timeout (default 60 s), and a watchdog/brown-out reset → off.
  - **Mode switch:** long-press ≥ 1.5 s toggles HOLD ↔ TOGGLE; mode remembered in NVS.
  - **Indication (no screen, D17):** the **buzzer** — a single chirp on boost assert, a double chirp on
    a mode change. The WiFi page shows the mode when parked; a CAN dash could show `BST` (§7.2).
  - Output is **open-drain, default off**, so any module failure = no boost. The FarDriver's own boost
    timer (`BstTime` 45 s, `BstRelease` 90 s in the export) still bounds every assertion.
- **Startup:** all outputs off until self-test passes, then assert lighting from the slider position.
- ⚠️ **Watchdog: task watchdog ≤ 300 ms, with the lighting re-assert as the first action in
  `app_main`.** A 2 s watchdog plus S3 boot (~200 ms ROM + app init) is **≥2.2 s dark ≈ 37 m at
  60 km/h**; ≤300 ms gives ~0.5 s total. ✔ **Measure the real reset-to-lamp-on time on the bench** and
  record it here.
- **Safety:** the module's **firmware is never in the brake-cutoff or brake-light path** — both are
  the brake circuit's hardware (D23), and the lamp's only dependence on the module is its 12 V rail —
  and the module never writes controller parameters.

### 7.1 Boost path — controller-side setup and the current-cap catch

1. **Which wire.** On this NS-series unit the brown lead is the one-line *output*, so the boost *input*
   is an unused pull-down input re-assigned in the app: set **`BoostPin`** to the pin value held by an
   unused function, and that wire becomes the boost input. From the export: `CruisePin` **PIN17** ·
   `LowSpeedPin` **PIN2** · `HighSpeedPin` **PIN3(P7)** · `ReversePin` **PIN8** · `AntiTheftPin`
   **PIN14** · `BoostPin` **Invalid(off)**.
   ✅ **Use `CruisePin` PIN17** — genuinely unused, and it leaves PIN2/PIN3 free for D7's gear select
   (D7(a) needs both). Once reverse is disabled (issue #6), `ReversePin` PIN8 is free too.
   **Bench-verify:** ground that wire → the app shows gear `Bst`.
2. **Module output** grounds that wire (a pull-down input with a pull-up inside the controller); nothing
   else on the module touches motor control. ⚠️ **The pull-up voltage is unmeasured — meter the wire
   before fitting a 30 V FET** (the harness also carries pink `60VC` at pack voltage). Fallback if it
   reads high: the PC817 opto (§6).
3. ⚠️ **Boost does nothing unless the normal cap sits below the boost cap.** FarDriver boost runs at the
   *custom* maximum line/phase current; the export has **MaxLineCurr = CustomMaxLineCurr = 80 A** and
   phase 200 A = 200 A, so boost currently changes nothing. To make it real: set the everyday
   `MaxLineCurr` lower (e.g. **60 A**) and leave the custom/boost cap at **80 A** — the **XT90-S (~90 A)
   bounds the ceiling**, so the boost cap must never exceed 80 A.

### 7.2 CAN — ⏸️ PARKED (D19, 2026-09-10)

> ⏸️ **Parked by owner decision D19.** The module ships without dash telemetry; the display question
> re-opens later — solve the CAN 18 map, or replace the panel. What is known stays correct: the vendor
> confirms the protocol is **FarDriver CAN 18**, the bench reads the panel as a **receive-only node**,
> and an owner video shows the goal working on this display model. The single missing item is the
> **byte map (D8)**. **The CAN hardware stays in the design** — `SN65HVD230`, the 120 Ω, display pins
> 7/8, 2 GPIO: the park is on the software, not the copper. Consequences: D11 and board F park too; the
> WiFi page is the primary readout; D17 is the decision to re-open if the panel is *replaced*. Stop-list
> and re-open triggers: `can18-investigation.md` §0.

**Design.** The Chaojie shows temperatures, phase current, amps and the status/alarm flags **only over
CAN** — the one-line frame has no room for them — and our controller has no CAN. So the module
**impersonates a CAN-enabled FarDriver**: serial in from the real controller, CAN out to the display.
- ESP32 TWAI + **`SN65HVD230`** 3.3V transceiver, **120 Ω** at the module end; the display terminates
  its own end (**132.4 Ω** measured, M16 step 1; the two in parallel measured 68 Ω).
- CAN H → display **pin 8 (red-black)**, CAN L → **pin 7 (green-black)**.
- Protocol **FarDriver CAN 18** (Chaojie, 2026-09-10: *"Currently display default only support
  fardriver CAN18 protocol"*); bitrate **250K** (`CANBaud` = 0 — reseller text only).
- **Transmit in `TWAI_MODE_NO_ACK` permanently** — the panel acknowledges nothing (confidence MEDIUM).
  Use `TWAI_MODE_LISTEN_ONLY` to sniff safely. Firmware still detects and recovers from bus-off
  explicitly, and **halts transmission before a display reset** (§3.3).
- The one-line on the brown wire stays connected — it is the working feed.
- ⚠️ **Never enable CAN on our own controller** — on non-CAN units the transceiver sits on **A11/A12, the
  Hi/Low speed sense lines** = `LowSpeedPin` PIN2 / `HighSpeedPin` PIN3, the inputs D7 wants. Nothing
  requires it: the controller stays on one-line/serial with `CANConfig` = `None`.

**What FarDriver's documentation gives — the *app parameter description* §12.3, "CAN Agreement
data".** The controller's CAN output is *table-driven*, and the table format is public:
- **6 transmit IDs** (Send ID0–ID5) with a 10 ms-unit timer each; ID2–ID5 with timer < 4 are
  request-only (on-demand commands 12–15).
- **52 items**: **21 data** (customer code, serial ×2, serial/error code, hardware version, software
  version ×2, **input voltage 0.1V**, **line current 0.1A**, **phase current 0.1A**, throttle opening,
  throttle voltage 0.01V, torque 0.1 Nm, **speed**, **rpm**, total mileage hi/lo 0.1 km, current
  mileage 0.1 km, **controller temp °C bias 40**, **motor temp °C bias 40**, **battery level %**),
  **17 status bits** (gear 2 bits with several SEC3 encodings, 3-speed 3 bits, brake, cruise, seat,
  side-stand, speed-limit, repair, reverse, **boost**, push, park, charge, READY, ECO, ABS, BOOST),
  **14 alarm bits** (hall, throttle, brake, MOS, phase short, phase lost, MOS over-temp, motor
  over-temp, over-current, over-voltage, under-voltage, blocked, anti-theft, controller).
- Each item = **Length (bits), Position (LSB bit 0–63 in the 8-byte frame), Gain, Send-ID (0–5), Valid
  flag, Bias**; byte order **Intel or Motorola**; standard or extended frames.
- The `.heb` file's 0x180-byte CAN section stores exactly this table — **`fardriver-nd72450-reference/tools/heb_decode.py`
  decodes it** (`CAN_block`). Ours is empty (`CAN: None`).
- The controller also *receives* frames: **SOP** (BMS max discharge current), **SOC**, charge,
  side-stand, **3-speed** (0/1/2 gear, **3 = boost**), **gear N/F/R**, **Control** (display-type word),
  OBD 0x7DF. A CAN display may therefore *send* gear / 3-speed / boost commands; the module can honour
  or ignore them.

### 7.2.1 What the vendor documents settle

1. **The map never lives in the parameter file (M12 closed).** App parameter description **§5.1.5**:
   *"CAN: Instruction number, Hxx version default 60…"*. Our firmware is **HA86**, so 60 is the H-series
   default. `CAN` is an **instruction number selecting a protocol built into the firmware**, not a table
   selector — which is why `CAN_block` decodes empty with `CANConfig` = 60. Do not retry with other values.
2. **The full item vocabulary is documented** in the app parameter description **§12.3** (not the
   controller manual): §12.3.1 data format · §12.3.2 CAN Send ID · §12.3.3 rules (ID 0–5, valid flag,
   gain, bias) · **§12.3.4 the 21 data items** · **§12.3.5 the 17 states** (with SEC1/SEC3 gear
   encodings) · **§12.3.6 the 14 alarms**. Bit numbering: `BIT 7..0, 15..8, … 63..56`. Temperatures carry
   **bias 40**. Only the CAN 18 assignment of items to IDs and bit positions is missing.
3. **Pins 7/8 carry controller CAN, not only battery CAN.** The `CJ-V3-01` manual documents both a
   battery/BMS page and a **Controller-information page** (motor temp, controller temp, bus voltage, bus
   current, phase current, throttle in); the vendor confirms CAN 18; and an owner video (**NRGZ28**,
   captions verified 2026-09-09) shows a CAN-SKU FarDriver 72450 populating speed, power, voltage, bus
   current and both temperatures on a Chaojie 3", with **phase current blank**. ⚠️ Our 3"'s build
   `CJ-YQ25-250418` does not show the Controller-information page. Detail:
   `pinout-3in-cj-v3-01.md` §3.2.

#### 7.2.2 Active probing — the D8 route when the park lifts

With the ESP32 + transceiver transmitting candidate frames in `TWAI_MODE_NO_ACK`, **the glass is the
feedback channel.** The search is structured: the vocabulary and encoding are known (app description
§12.3), send-IDs are 0–5, bit positions 0–63. Narrow it by target field — the dash shows **C** and **M**
as 0, so sweep send-IDs with a plausible temperature byte (bias 40) and watch those two fields — anchored
on `SendID0` = `0x100` (§7.2.3). The **Rigol MSO5074** verifies what is actually on the wire.

#### 7.2.3 Community evidence (Endless Sphere, GitHub — leads to verify, not specs)

1. **FarDriver's CAN stalls without an ACK:** *"the controller sends several messages in a row and then
   stops… it is waiting for an incoming transmission before continuing"*; adding a terminated,
   ACKing node restores continuous output. With no ACKing peer it retransmits SendID0 and never
   advances. Our module is the transmitter and the panel never ACKs, hence `TWAI_MODE_NO_ACK`
   (confirmed in ESP-IDF v5.5's `hal/twai_types_deprecated.h`: *"transmission does not require
   acknowledgment"*; `TWAI_MODE_LISTEN_ONLY` *"will not influence the bus… but can receive"*).
2. **A transmit ID:** a modified unit was observed with **`SendID0` = `0x100`, carrying voltage** — the
   first data item in the app description's §12.3.4 (input voltage, 0.1 V). One unit, unverified; a plausible probing anchor.
3. **Receive IDs** (jackhumbert/fardriver-controllers): `0x0CFE55B0` set max line current · `0x0CFE55B1`
   add max current · `0x0CFF55B0` set battery capacity — **29-bit extended, J1939-style**; inbound
   commands, not the outbound map.
4. **Bus parameters:** 250 K / 500 K / 1 M all confirmed working; extended frames operational; running
   cadence ~**1560 frames/s with ~100 µs gaps**.
5. **Other instruction numbers:** `CAN` = 59 = autonomous-driving system; `CAN` = 48 = (H80 only) serial
   port to CAN analyser debugging. Neither applies to our HA86.
6. **Prior art:** an ESP32 + LVGL display decodes FarDriver CAN, with `CurrentRotation` (RPM) working
   and `CurrentSpeed` / `CurrentDistance` not — the opposite direction to ours, but proof the protocol is
   tractable. A working decoder's ID/bit map *is* the answer to D8.
7. **Do not enable CAN on our controller** — A11/A12 = the Hi/Low speed sense lines (§7.2 design).

Routes to the map, in order, for when the park lifts: `can18-investigation.md` §8.

#### 7.2.4 M16 — done, parked

M16 established that the panel does not ACK and reads as a receive-only node (§5 M16 row). The
procedure, firmware, results and the three method traps are in `can18-investigation.md` — ⛔ its
§4.1 pre-flight gate is mandatory reading before any CAN bench work.

With no module screen (D17) and D8 parked (D19), the Chaojie shows only the one-line fields (speed, its
own V/SOC, gear, faults); temperatures, bus current, boost mode and lamp-out are on the **WiFi page**.
During P0/P1 the diagnostic channels are USB serial and the WiFi page.

## 8. Decisions

| # | Decision | Chosen | Rationale and status |
|---|---|---|---|
| **D1** | How does the lighting come up? | **Incrementally** — the module drives each lighting function as its output is built | **DECIDED 2026-09-11 (owner):** *"we will build incrementally."* The bike runs today with no lights; each function goes live as its output is built and tested |
| **D2** | Which throttle is on the bar? | **FarDriver throttle with red button** | **DECIDED 2026-09-06.** Bar controls come from the new switch sets (D20) |
| **D3** | Where do the "dashboard buttons" go? | **(d) a bought handlebar switch set** — extended to both pods by D20 | **DECIDED 2026-09-10 (owner).** A new switch set is plain dry contacts to the module (§4 class A). No printed pad, inserts or sealing job. **Selection criteria:** ⚠️ **wetting current** — prefer gold-plated or sealed contacts and use **1 kΩ pull-ups** (§4) · latching vs momentary per control (D21/D22) · ⛔ **avoid sets with built-in LEDs or a controller/USB module** (they need their own 12 V feed and ground reference) · the pair must cover turn (3-position), horn, high/low, lighting (3-position) and hazard — ⛔ the evaluated `B0CT897DDX` has **no horn button** · ⬜ measure the bar clamp Ø (22.2 mm / ⅞″ expected, some 25.4 mm) and ⬜ check right-bar space (throttle grip, switch set and brake perch compete). Two sets, **~$30–50** |
| **D4** | Boost button routing | **(b) through the module** — HOLD / TOGGLE, long-press mode switch, safety clears | **DECIDED 2026-09-06.** The modes exist only with the module in the middle; mitigations: open-drain default-off output, brake/key/timeout clears, the controller's own boost timer |
| **D5** | Lamp voltage class | **12 V** | **RESOLVED 2026-09-08.** The headlight housing is stamped `LOW BEAM 12V/8.5W`, `HIGH BEAM 12V/8.5W`, `DAYTIME RUNNING 12V/6.5W`; the horn measured 12 V / 0.10 A. The module's 12 V rail drives the bike's lamps directly |
| **D6** | Board | **ESP32-S3 DevKitC-1** | **DECIDED 2026-09-07 (§3.1).** Pins (21 native used, 7 spare of a 28-pin clean pool, §3.1.3; a pool of 30 on the custom board, §9.8), 3 UARTs for the two RX taps, two cores to keep bus timing off the WiFi core. Not the H2 (no WiFi); the C6's second TWAI is the only thing given up — on the prototype an `MCP2515`/`TCAN330` on SPI recovers it from the spare pins. The module *variant* is a thermal choice (D18) |
| **D7** | Use a spare latching bar input as **FarDriver gear select** (Low / Mid / High via `LowSpeedPin` PIN2 / `HighSpeedPin` PIN3)? | **(b) no for first ride** — stay `HighOnly`; (a) is cheap to add later | Options: (a) module grounds SDL/SDH through an open-drain MOSFET with `SPModeConfig` set to a 3-speed mode (currently `HighOnly`) · (b) stay `HighOnly`, gear changes in the app · (c) a hardware 3-speed switch. It is a **power limiter, not a ratio**: **Low** = 25% line / 50% phase (**20 A / 100 A**), **Mid** = 50% / 75% (**40 A / 150 A**), `MidSpeed_rpm` 4500, **High** = full 80 A / 200 A. ⚠️ **`LowSpeed_rpm` = 0 is vendor-shipped and ambiguous** (0 rpm cap, or no cap?) — resolve on the bench before enabling. ⚠️ Costs 2 module outputs and competes with boost for PIN2 (§7.1 — boost uses PIN17). Mid ≈ the "everyday 60 A" of §7.1. Its real value is a **persistent** low-power mode (lending the bike, wet roads) — a latching switch fits it |
| ⏸️ **D8** | How to obtain the CAN table the Chaojie parses (§7.2) | ⏸️ **PARKED (D19)** — do not work this row | **Known:** protocol **`CAN` = 18** (Chaojie, 2026-09-10); **`CANBaud` = 0 = 250K** (reseller text — "0-250 kbps" is an enum index, `fardriver-nd72450-reference/tools/heb_decode.py:24`); the panel is a receive-only node, so the module transmits in `TWAI_MODE_NO_ACK` (MEDIUM); the goal is demonstrated on this display model (NRGZ28: motor temp, controller temp, bus current populate; **phase current stays blank**); **M12 is closed** — the map is firmware-internal (§7.2.1). **Missing:** the byte map. Routes when it re-opens: `can18-investigation.md` §8. ⛔ Do not enable CAN on our controller (§7.2) |
| **D9** | What stays live at key-off? | **(a) nothing** — module + 12V rail off the key-switched path | **DECIDED 2026-09-07.** Zero parasitic drain; the §3.2.2 ride-out cap still gives a clean shutdown. **Hazards die with the key** — accepted. The D13 switch releases up to ~0.8 s after the key opens, while its gate capacitor discharges (§3.2.5); nothing is live after that |
| **D10** | May the module drive the FarDriver **KEY** line? | **(b) no — sense only via IN-12** | **DECIDED 2026-09-07.** The module never holds the KEY line, so a hung module can neither cut motor power nor switch the bike on. Starting is the key switch alone, feeding KEY directly (**D24**) |
| ⭐ **D24** | **How the bike starts** (§3.2.5a) | **(a) the key switch feeds the FarDriver KEY wire directly** — no start latch, no start gesture | ✅ **DECIDED 2026-09-18 (owner).** The topology is the §3.2.5 diagram: XT90-S out → 2 A fuse → key switch → FarDriver KEY wire, with one tap into the module for the D13 enable and the IN-12 sense. The module never sources or switches KEY (**D10**), so no module state — hung, reflashing, unpowered, absent — can start or stop the controller; a firmware-held KEY would mean a watchdog reset cuts motor power under way. The right pod's start button is a **spare sensed input** (§2.0). The run/off toggle remains the secondary kill, through Q2 onto `BL` (D23) |
| ⏸️ **D11** | Display supply: 12 V or pack voltage, and so which high-side switch? | ⏸️ **PARKED with the display (D19)** | Options: (a) 12 V + a 60 V P-MOSFET off the load rail · (b) pack V + a 150 V P-MOSFET or a photovoltaic MOSFET SSR. The right answer depends on which panel ends up fitted, so **board F leaves the first order** and the dash feeds from switched B+ (work order §3.1) meanwhile. **The gate when it re-opens:** M14 shows the panel boots at 12 V, but its **V field reads pin 2, not the link** — under (a) the dash reads **12 V / 0 %** unless a transmitted voltage overrides the internal ADC. `SpecialFrame` 21 (16 + DATA9 *power* + DATA10 *current %*) sends **no voltage byte**; frames **25 / 24 / 16**, or **31 with ByteOption 2**, do (`pinout-3in-cj-v3-01.md` §4). Under (b), V and battery % stay a direct measurement, truthful through a module hang |
| **D12** | Horn driver | **(a) MOSFET** | **DECIDED 2026-09-08.** M7: an electronic 12 V horn at 0.10 A — no coil, no inductive kick, no flyback diode needed (keep a TVS on the wire leaving the box) |
| **D13** | Inrush into the module's bulk capacitance must not land on the key-switch contacts (§3.2.5) | **(b) key switch gates a soft-started P-MOSFET high-side switch; module on its own fused B+ tap** | **DECIDED 2026-09-07.** Closing a contact onto the module's bulk capacitance at 84 V is tens of amps every key-on; (b) removes it instead of making a contact absorb it. Key switch carries the KEY wire plus **~0.32 mA** of dividers — an ordinary 72 V e-bike key switch, 12–96 V. Tap fuse **2 A fast (`KLKD002`)**. FET **`IXTP26P20P`**, selected on SOA. **Gate ramp ~50 ms (owner, 2026-09-18):** 114 W @ 25 ms, under the part's DC SOA line at T<sub>C</sub> 70 °C (§3.2.5). The gate's pull-down switch is a **`BSS127`** — enhancement-mode; its sibling `BSS126` is depletion-mode, on at V<sub>GS</sub> = 0. The work order, checklist and build sheet keep their wiring |
| **D14** | Lighting defaults | **All lights OFF at key-on · HIGH replaces LOW · hardware default-ON fail-safe dropped** | **DECIDED 2026-09-08 (owner).** ⚠️ **Accepted risk: a firmware hang at night leaves the bike dark**; mitigation is the ≤300 ms watchdog and reading the slider at boot (§7). Gate bias is uniform default-OFF (§3.1.2). The control mapping is now D21; flash-to-pass is IN-09 (§7). The brake light is outside this risk — it is hardware (D23) |
| **D15** | High-side driver type | **(a) smart high-side switch on all 6 module lighting channels** — TI `TPS4H160BQPWPRQ1` (§6.2.2a) | **DECIDED 2026-09-08.** Per-channel current limiting stops a shorted lamp wire hiccuping the whole rail and killing the headlight; thermal shutdown and lamp-out detection come with it. 3.3 V input compatible, floating input = OFF |
| **D16** | Which channels are native GPIO, which ride the I2C expander? | **(a) FULL NATIVE on the custom board** — all six lighting channels, their diagnostics, boost, the brake inputs, PWM and analog on S3 pins; the expanders carry bar inputs only (§9.8.2). **The DevKit prototype runs (b):** low beam + boost native, the other 5 lighting channels on expander #2 (§3.1.3) | **(a) DECIDED 2026-09-18 (owner)** for the custom board; **(b) DECIDED 2026-09-08 (owner)** for the prototype, where all-native does not fit the DevKit's pins. Putting every lamp and bar switch behind one bus means a single I2C fault at night costs the headlight and signals in one event. (a) takes the bus out of the lighting path entirely; (b) keeps the headlight LOW on a private wire, and boost on its own pin (§7.1), with 7 pins spare. The brake lamp is not a module output (D23) |
| **D17** | Status screen on the module | **(c) no screen** | **DECIDED 2026-09-08 (owner).** The Chaojie 3" is the only display; simplifies board A, the housing and the firmware. With D8 parked the dash shows only the one-line fields and the **WiFi page is the primary readout**. ⚠️ **Re-open trigger (D19): if the panel is replaced rather than fixed**, revisit what the module must display itself |
| **D18** | Module variant for the custom PCB (§9.8.3) | **(a) `ESP32-S3-WROOM-1-N8`** (8 MB, no PSRAM, −40…+85 °C) — or its external-antenna twin **`-WROOM-1U-N8`** on the same footprint (§9.8.1) | Same part as the prototype (M13), so firmware, pin availability and thermal envelope carry across unchanged. Keep **(b) `-H4`** (4 MB, −40…+105 °C) in reserve only if a thermal survey of the finished box shows it above ~75 °C — ⬜ confirm two OTA app partitions fit 4 MB first. ⛔ **Never an `R8` / `R16V`** — −40…+65 °C against a 60 °C ambient |
| ⏸️ **D19** | Keep spending time on the Chaojie CAN dash feed? | **(b) PARK it** — finish the rest of the module, re-open the display later | **DECIDED 2026-09-10 (owner):** *"the display we have now will either not work, or take too long to setup … we will come back to the display later, and either figure it out or replace it."* Parking costs almost nothing to hold open (the CAN hardware is in hand and spends 2 GPIO), and every remaining step is display-independent. **Consequences:** ① D8 parked (the vendor thread with Peri stays open passively) · ② the CAN hardware stays fitted · ③ D11 parks and block F leaves the first order · ④ the WiFi page becomes the primary readout — a firmware deliverable · ⑤ the dash keeps its one-line feed (issue #7) · ⑥ D17 gains its re-open trigger. **Cost:** temperatures on the glass are deferred — the rider sees them on a phone, not while riding. Telltales are unaffected (pins 1/4/5 off the lamp feeds) and port to any 0–15 V sense-input dash |
| **D20** | Handlebar pods | **(c) replace BOTH with bought switch sets** — every bar control is a new dry contact | **DECIDED 2026-09-10 (owner):** *"we are going to replace the right pod as well. this will be all of our buttons."* IN-01…IN-04 are plain **class A** dry contacts. The original pods come off whenever the switch sets are wired. **M1** is the unpowered ohm-out of the new sets. **12 input bits on expander #1** (§3.1.3); 1 kΩ pull-ups on every bar input (§4); ⬜ check right-bar space; ⬜ measure bar Ø |
| **D21** | Lighting control | **(b) a 3-position slider + a high/low toggle**, as the bought set provides | **DECIDED 2026-09-10 (owner):** *"for the lighting, there is a high/low toggle, and a 3 position slider."* The slider's positions **are** D14's three states in order, with "low beam implies running" built into the hardware; the state is visible; and at boot the module reads the actual switch, not a remembered value. It improves **recovery**, not **immunity** — a hung module still drives no lamps. Lighting becomes a combinational lookup (§7). ⬜ Ohm the slider out before wiring (OFF/A/B vs OFF/A/A+B) |
| **D22** | Turn-signal control | **A push-push latch whose button self-centres, with auto-cancel** — a fact of the bought left pod, in hand 2026-09-11 | ⭐ **It is a PUSH-PUSH (alternate-action) latch whose BUTTON SELF-CENTRES:** push left → latched left, the button springs back; press again to unlatch. **The latch is electrical and hidden, so the switch has NO visible state** — the dash telltale is the only indicator, and that is what auto-cancel exists to compensate for. ✅ **Auto-cancel: 20 s above 15 km/h, or 60 s regardless.** ⭐ **Implement on EDGES, not levels:** `open→closed` starts · `closed→open` stops · **auto-cancel stops the lamp and marks that latch cycle spent** so the still-closed contact cannot restart it · the next `open→closed` is a fresh signal. ⛔ **A latch state machine is required** — press = on · same side = off · **press opposite = switch sides**, a real firmware case since both sides latch independently. ⚠️ **Auto-cancel depends on speed from the serial link** — degrade to the 60 s timeout alone when speed is unavailable. ✅ Also confirmed on this pod: **horn momentary · hazard latching · high/low 2-position.** ⭐ **The rear headlight-marked momentary is the natural flash-to-pass** — IN-09 |
| **D23** | Does the brake light depend on firmware? | **No — the brake circuit switches it in hardware** (`brake-circuit.md`) | **DECIDED 2026-09-11 (owner).** Each lever, through 1N4148 steering diodes, pulls the FarDriver `BL` low (motor cut), pulls P-FET Q1 (`AO3407A`)'s gate low so Q1 switches +12 V to the tail STOP lamp (0.12 A, M5), and signals the module on IN-05/06 (10 kΩ pull-ups). **Firmware state cannot affect either function** — a hung, crashed or unflashed module leaves the brake light and the motor cut working; the module only senses. ⚠️ **The lamp is fed from the module's 12 V rail, so loss of that rail takes the lamp with it — not the motor cut**, which the lever makes by itself. The lever carries only a few mA. **Consequences:** the brake lamp is not a module output — GPIO41 and one `TPS4H160B` channel are free (§3.1.3, §6.2.1; still two packages for 6 channels) · no hard-brake flash — the lamp is on whenever a lever is pulled · IN-05/06 are class A through the circuit's diodes, still native. **Gate:** **M3**, the lever switch type (§5), before the circuit is built. **Build order:** step 1 levers → `BL` now; step 2 the lamp when the 12 V rail is in; step 3 the module inputs. On the custom build the whole circuit sits on **DRV** (block G, §9.2) |

## 9. Component breakdown and build plan

### 9.1 What may and may not sit on a breadboard

| | Allowed? | Why |
|---|---|---|
| Logic, buses, input conditioning (3.3 / 5 V) | ✅ **yes** | most of the work |
| The **84 V divider / IN-12 sense**, fed from a **current-limited bench supply** | ✅ **yes, carefully** | a 100 mA-limited supply makes a slip a non-event |
| **Any switching converter**, at any voltage | ❌ **never** | physics: breadboard contact inductance wrecks a buck's switching loop — it oscillates or destroys itself |
| **The 12 V load rail with real lamps** | ❌ **never** | breadboard tie points are good for ~1 A |
| ⚠️ **Anything fed from the pack** | ❌ **never** | 34 Ah of Molicel P42A ≈ **8P** ≈ **~360 A continuous** and far more into a short. A jumper working loose on B+ is an arc-welding event next to a lithium pack. **The bench supply is the safety device** |

### 9.2 Functional blocks and the four-board set

**Blocks A–G are functional names.** This plan and the BOM use them throughout ("board E" is block
E); on the prototype each is its own breadboard or perfboard (§9.3, §9.6).

| | Block | Domain | Prototype on | Phase |
|---|---|---|---|---|
| **A** | **Brain** — S3 + the two `MCP23017` expanders (no screen, D17) | 3.3 / 5 V | breadboard → proto board | P0 · P1 · P3 |
| **B** | **Bus interface** — 2 × serial tap, CAN transceiver + 120 Ω, one-line | 3.3 V signals | breadboard → proto board | P0 · P1 · P3 |
| **C** | **Input conditioning** — the class-A networks (§4) | 3.3 V, wires leave the box | breadboard → proto board | P2 |
| **D** | **Output drivers** — 6 high-side lighting channels, horn, fan, buzzer; 2.62 A worst case | 12 V | breadboard **with LED stand-ins only** → stripboard with a reinforced bus (§9.6) | P2 |
| **E** | **Power supply** — 84 V → 12 V + 5 V (§3.2) | **84 V** | — (bench supply direct). Bought modules on a carrier PCB — never proto board | P2 |
| **F** | **Display high-side switch** (§3.3) | 12 V or 84 V per D11 | breadboard (12 V case) | ⏸️ parked (D11) |
| **G** | **Brake circuit** — 1N4148 steering diodes, P-FET Q1 for the brake lamp, module pull-ups (`brake-circuit.md`; parts = BOM group G) | 3.3 V / 12 V signals | step 1: in-line in the lever-to-`BL` harness under heat-shrink | step 1 now · steps 2–3 with P2 |

**A + B are all that P0, P1 and P3 need, and both are breadboard-safe on USB power.** The power block
(E) gates only P2.

**The custom build is four stacked boards in one enclosure**, in the old-controller cavity under the
battery compartment (**M18**). Power flows from the floor up with the voltage falling, which puts the
most distance between the 84 V node and the 3.3 V serial taps (§3.2.4).

| Layer | Board | Domain | Holds | Blocks |
|---|---|---|---|---|
| 1 — floor | **HVIN** | 84 V | B+ / B− entry and the key tap, an `SMCJ90A` on each, the D13 soft-start switch and its gate network (§3.2.5), one CM choke per converter, the IN-12 divider | E |
| 2 | **CONV** | 84 V → 12 V / 5 V | both converters, C1 and C2, the hold-up diode and its 1 A fuse (§3.2.2), the Y2 capacitors, the TDK's output capacitors, one single-point tie from the baseplate to ground | E |
| 3 | **DRV** | 12 V | both `TPS4H160B` with their `CL` / `CS` resistors (§6.2.2a), the three low-side FETs, **the whole brake circuit**, the 15 V TVS arrays at its connectors (§6.2.4), the parked display connector block | D · G · F |
| 4 — lid | **BRAIN** | 3.3 V | the `ESP32-S3-WROOM-1` / `-1U` (§9.8.1), its 3.3 V regulator, both `MCP23017`, the CAN transceiver, USB-C and a service header, the pod and serial connectors with their input conditioning | A · B · C |

**Three inter-board interfaces, all on 2.54 mm pitch**, so that any one board can be stood in for by a
breadboard or perfboard section during bring-up (owner, 2026-09-15: *"both. i want full options for
pcb and breadboard."*):
- **HV-LINK**, HVIN → CONV — each converter's filtered +/− input, ground, and the IN-12 sense. It uses
  alternate pins (5.08 mm effective pitch) for 84 V creepage.
- **PWR-UP**, CONV → DRV and BRAIN — 12 V on three contacts, ground on four, 5 V, the IN-12 sense.
- **STACK**, DRV ↔ BRAIN, 2 × 25 with alternating grounds — the six lighting commands, `DIAG_EN` /
  `SEL` / `SEH`, both current-sense lines and fault flags, the horn / fan / buzzer commands, the two
  brake inputs, the 12 V sense, `RUN`, CAN, 3.3 V, and a 100 kΩ-isolated copy of `BL` for firmware.

⚠️ **The stack's height is derived, never typed — and at the estimated cavity it does not yet close.**
`python3 -m tools.board_fit` works it out from the netlist's own part and connector heights: **71.1 mm,
against 64.0 mm available** inside the 70 mm estimate (3 mm allowed for a floor, 3 mm for a lid) — over
by 7.1 mm. ⚠️ **Provisional on both sides** until M18 is measured and the enclosure chosen (§9.7);
binding the moment both are. With 1.6 mm boards, 1.0 mm of clearance and 1.5 mm for solder tails:

| Gap | mm | What sets it |
|---|---|---|
| floor → HVIN | 3.0 | the floor standoff, over HVIN's solder tails |
| HVIN → CONV | 24.5 | the 22.0 mm CM chokes standing on HVIN. C1 and C2 hang 18.5 mm under CONV beside them, so nothing on HVIN taller than 5.0 mm may sit beneath the cans |
| CONV → DRV | 18.2 | the 12.7 mm brick, the 3.0 mm thermal-interface plate bolted to it (§3.2.3), and DRV's solder tails |
| DRV → BRAIN | 11.0 | ⬜ the mated height of a generic 2.54 mm header pair — unconfirmed. The parts need only 9.5 mm (the 7.0 mm JST PA connectors) |
| BRAIN → lid | 8.0 | the 7.0 mm JST PA connectors |

⬜ **The inter-board connector family is unchosen, and once chosen its mated height *is* the gap** — so it
is picked before layout (M19). A family that mates lower returns at most 1.5 mm of the 7.1 mm, because
the parts in that gap need 9.5 mm; the rest waits on the measured cavity and the enclosure. ⬜ Nothing
in the design yet carries PWR-UP down from DRV to CONV across the 18.2 mm gap.

⚠️ **D23's hardware is complete on DRV alone.** The levers, `BL` out and `ACC+` in all land on DRV's
own connectors, and the real `BL` never crosses to BRAIN. The run/off toggle's contact arrives from
BRAIN's right-pod connector over STACK as plain copper; its pull-up is on DRV, so an open contact — a
lifted BRAIN included — reads as OFF and cuts the motor.

⚠️ **One open wire does NOT fail safe: `ACC+`.** The kill's pull-up is fed from the throttle's `ACC+`
(so it works with the module's own rails dead). If that wire never arrives, the node cannot rise, Q2
never turns on, and the run/off toggle silently stops cutting the motor — the levers still do. Hardware
cannot know, so `ACC+` is divided down (100 k / 180 k → 3.28 V) onto expander #2 and **firmware must
raise an alarm when it reads low with the key on.**

📄 The netlist is the design: `tools/netlist.py`, gated by `python3 -m tools.integrity` and the test
suite (repository README).

### 9.3 Breadboard allocation (prototype stage)

- **BB1 — Brain + buses (A + B).** S3 across the centre channel, the two expanders, `SN65HVD230` +
  termination, tap resistors. ⚠️ The DevKitC-1's dual headers leave only **one accessible tie-point row
  per side** on a 5+5 board — butt two boards end-to-end or use a wide one.
- **BB2 — Input conditioning (C).** The class-A networks with **real switches**, so debounce is
  developed against actual contact bounce.
- **BB3 — Output logic, with LED stand-ins (D in miniature).** **Prototype every lighting behaviour
  with LEDs at 12 V and < 100 mA** — flash cadence, hazard, the lighting lookup, flash-to-pass
  break-before-make, the default-OFF gate bias. Firmware cannot tell a 20 mA LED from a headlight, so
  board D becomes a transcription with bigger parts, not a redesign.
- **Rail discipline:** one ground bus, **all grounds tied at a single point** — the bench stand-in for
  the controller-B− star of §3.2.4.

### 9.4 Bench supply — Rigol **DP2031**

**CH1 0–32 V/3 A · CH2 0–32 V/3 A · CH3 0–6 V/5 A**, isolated channels, internal CH1+CH2 series.

| Job | Channel | Note |
|---|---|---|
| Logic rail for BB1–BB3 | **CH3** | 5 V (or 3.3 V) at up to 5 A |
| **HV bring-up of board E** | **CH1+CH2 in series = 0–64 V** | **current-limited — the safety property.** Start at 100 mA and walk it up |
| **M14** display test | CH3 at 12 V, then series up to 64 V | ⚠️ current limit ≥500 mA — the display draws ~0.22 A |
| Full-load test of DC-DC #1 | CH1+CH2 series | 12 V × **2.62 A = 31 W** out ≈ **34 W in** ≈ **0.53 A at 64 V** — well inside the 3 A limit. The supply can drive the converter harder to prove the part; the bike never asks for it |

⚠️ **64 V is not 84 V.** The supply covers the LVC (60.0 V) and upward, so every converter and
protection circuit can be commissioned on the bench — but **the top 20 V of the pack range can only be
validated on the pack.** Do that last, with the Class T main fuse in place, after everything has passed
at 64 V. An 84 V-only fault is exactly what the bench cannot catch — which is why §3.2.1 insists on
**160 V-rated parts**.

### 9.5 Converters and support parts — **buy, do not build** (decided 2026-09-07)

A 100 V-class buck cannot be breadboarded (§9.1), so DIY means straight to a PCB with no prototype step;
and a homebrew high-voltage switcher beside 3.3 V TTL serial taps and 80 A of chopped phase current
invites the hardest class of bug in the build. **There is no cheap commodity part:** scooter-market
"72 V" converters are 45–90 V input, and every verified 160 V candidate is a **pinned brick or DIP
needing a carrier PCB** and a metal thermal path for its baseplate (§3.2.3, §9.7). Real cost: **~$175 for
the two converters, ~$200–260 for the block.**

⚠️ **The spec trap:** many converters sold as "72 V" specify **45–90 V** input. The pack is **84.0 V at
full charge** and OV-protect is **90.7 V** — such a part runs at its ceiling on every charge. **Require
160 V rated input** (§3.2.1 explains why 100 V is unprotectable).

#### 9.5.1 Converters — selected, and why nothing smaller is cheaper

✅ **TDK `CN150B110-12`** — ordered as **`CN150B110-12/CO`**, factory conformal-coated (BOM E1). A
conduction-cooled quarter brick, **58.3 × 37.2 × 12.7 mm**, aluminium baseplate. It is ~4.8× oversized
against the 2.62 A load, but **in this EN 50155 railway market the 160 V input rating sets the price,
not the wattage** — smaller parts cost more:

| Part | Output | Price (uncoated) |
|---|---|---|
| **TDK `CN150B110-12`** ✅ | 12 V / **12.5 A** / 150 W | **$113.10** |
| TDK `CN100B110-12` | 12 V / 8.4 A / 100 W | **$146.03** |
| TDK `CN50B110-12` | 12 V / 4.2 A / 50 W | ~$170 (RS, regional listing); TME 0 in stock |
| RECOM `RP40-11012SFR/P` | 12 V / 3.33 A / 40 W | **$126.52** |

Downsizing has no thermal case either: what any of these bricks dissipates at 31 W is unmeasured
(§3.2.3).

**Converter #1 — 12 V load rail**

| | Part | Input | Output | Verdict |
|---|---|---|---|---|
| ✅ | **TDK-Lambda `CN150B110-12`** (DK 25325134) | **43–160 VDC** | **12 V / 12.5 A / 150 W**, 91.5% | **Selected.** Non-latching OCP/OVP |
| ○ | Cincon `CHB300W-110S12` | 43–160 V (200 V/100 ms surge) | 12 V / 25 A / 300 W | Thermal derating binds: unheatsunk in still air ~50 W at +60 °C. Only viable bolted to metal |
| ❌ | Cincon `CQB100-110S-12-CM` | **66**–160 V | 12 V / 8.4 A / 100 W | **Rejected:** its 66 V minimum with UVLO turn-off at 54–58 V sits inside the pack's own LVC band — lights could drop out at low SoC while the controller still runs |

**Converter #2 — 5 V logic rail**

| | Part | Input | Output | Verdict |
|---|---|---|---|---|
| ✅ | **Cincon `EC7BW-110S05`** (DK 2034-3294-ND) | **43–160 VDC** | **5 V / 4 A / 20 W**, 3 kV iso | **Selected.** 2× the needed current, full 20 W to +73 °C, UVLO 40 V up / **38 V down** (the §3.2.2 hold-up floor) |
| ○ | RECOM `RP10-11005SRAW` | 36–160 V | 5 V / 2 A | alternate |
| ○ | Traco `THN 10-7211UIR` | 14–160 V | 5.1 V / 2 A | best environmentals (encapsulated metal case, EN 50155/61373, MIL-STD-810F vibration). ⚠️ **Suffix trap: `THN 10-7211WIR` is 9–75 V — unusable** |
| ❌ | RECOM `RP03-11005SRAW` | 36–160 V | 5 V / **600 mA** | under-spec — Espressif wants ≥500 mA *before* the DevKit's LDO, CP2102N and LEDs |

**Not a custom LM5164-class board** — TI `LM5164`, ADI `LT8631` and MPS `MP9486A` are all **100 V
absolute-maximum, 1 A** parts, and none can be protected on this rail (§3.2.1).

#### 9.5.2 Support parts — what the datasheets require

**None of these modules is internally fused, and none is complete on its own.**

| Requirement | Source | ✅ Selected part |
|---|---|---|
| **Input fuse, DC-DC #1 — FAST-blow**, ≤10 A, on the **+Vin leg** (−Vin grounded), with I²t headroom for turn-on inrush | TDK-Lambda instruction manual | **Littelfuse `KLKD002`** — 2 A, **600 VAC / 600 VDC**, 100 kA AC / **50 kA DC**, 10.3 × 38.1 mm midget, fitted at the **module's B+ tap** so it serves the tap and DC-DC #1 together (§3.2.5). Holder: **Mersen `FEB-11-11`** inline + **`FSB1`** boots (BOM E4) |
| **Input fuse, DC-DC #2 — 1 A TIME-DELAY** | Cincon datasheet | **Schurter `0001.2504`** (SPT 5×20 ceramic) — 250 VAC / **300 VDC**, UL 1500 A breaking at 300 VDC |
| Fuse holder for that link, on CONV | — | **Two PCB fuse clips for a 5×20 link** — ⬜ part to choose: check its voltage line, and the clip-to-clip creepage at 84 V. ⛔ **Not the Schurter `FAC 0031.3803`** (PCB THT, 600 VAC/VDC UL, 10 A VDE / 16 A UL, −40…+85 °C, IP40) in the stack: it is a **47.5 mm-tall vertical** holder. It suits a free-standing carrier only |
| **Bulk input electrolytic ≥100 µF**, low-impedance, Chemi-Con KXJ class, at the terminals; two in parallel below −20 °C | TDK | **Chemi-Con `EKXJ221ELL221MM25S`** — 220 µF / 220 V (the requirement is ≥200 V), −40…+105 °C, 18 × 25 mm. ⚠️ **×2** (§3.2.2) |
| **4700 pF from +Vin AND from −Vin to the module BASEPLATE**, close to the terminals, HV rated | TDK — its *primary* EMI-and-stability measure | **Vishay `VY2472M49Y5US6`** Y2 (BOM E9), lying flat. The baseplate is tied to ground at **one** point, so a shorted Y2 blows the tap fuse instead of floating the plate at 84 V |
| **`CNT` strapped to −Vin; +S strapped to +V and −S to −V.** `CNT` is negative logic — *open = OFF* — and an open sense pin leaves the output undefined | TDK-Lambda instruction manual | Three straps at the brick on CONV. ⚠️ Left open, the 12 V rail never comes up — and the brake lamp with it |
| **Output capacitor *"for stable operation"*: 680 µF / 25 V solid**, plus 2.2 µF ceramic across the output and 22 nF from +V and from −V to the baseplate | TDK-Lambda instruction manual, Table 6-1 | 680 µF / 25 V low-ESR polymer, lying down beside the brick (BOM E20) · 2.2 µF / 25 V · 2 × 22 nF / **250 V** — rated to survive the baseplate lifted to the 84 V rail (BOM E21) |
| **Input dv/dt ≤ 10 V/µs** | TDK | delivered by D13(b)'s soft-start |
| **Common-mode choke — one PER CONVERTER**, **before** the bulk capacitor. The Cincon meets its EN 50155 EMC rating only *"WITH EXTERNAL FILTER"*; TDK: *"when using multiple power supplies, add choke to each power supply input"* | Cincon + TDK | **Würth `7448022010`** (WE-CMBNC) **×2** — 10 mH, 2 A @ 70 °C, 85 mΩ, 300 V, 2100 V hipot, −55…+125 °C, **AEC-Q200 Grade 1**. Runs at **29% of rating**; I²R ≈ 57 mW. **A four-terminal part** (windings 1–4 and 2–3): each converter's −Vin is its own net, joined to ground only through its choke winding. **22.0 mm tall** × 18.0 × 14.0 mm |
| **Input TVS** | Cincon (names `P6KE180A` for railway surge) | **`SMCJ90A`** (1500 W, DO-214AB) — §3.2.1 |
| Hold-up blocking diode | §3.2.6(a) | **`1N4007`** — 1000 V, I<sub>FSM</sub> 30 A @ 8.3 ms / 45 A @ 1 ms |
| Cooling path for the conduction-cooled quarter brick | TDK | **Bolt the baseplate to a thermal interface** (§3.2.3). Baseplate −40…+100 °C, OTP trips 105–120 °C, so **target Tb ≤ 85–90 °C**; the dissipation that sets it is ⬜ unmeasured. TDK's **`HAQ-10T`** finned sink (7.5 °C/W in free air, 57.9 × 25.4 × 36.8 mm, BOM E5) is a free-air part and does not fit the stacked build |

##### ⛔ Fuse traps — read before substituting anything

⚠️ **Order fuses BY PART NUMBER. Never substitute on form factor.** Three Schurter 5×20 families look
like the selected `SPT` and are unusable on a DC battery rail:

| Family | Tube | Characteristic | Breaking capacity | DC rating |
|---|---|---|---|---|
| ✅ `SPT` 5×20 | Ceramic | **Time-lag T** | 1500 A | ✅ **250 VAC / 300 VDC** (UL/CSA) |
| ⛔ `FST` 5×20 | **Glass** | Time-lag T | low | ⛔ **none** — zero DC hits in the datasheet |
| ⛔ `FSF` 5×20 | **Glass** | Quick-acting F | 35–100 A | ⛔ **none** |
| ⛔ **`SP` 5×20** | Ceramic | **Quick-acting F** | 500–1500 A | ⛔ **none** — exactly the ceramic, fast, high-breaking part this build wanted, with no DC rating at all |

**In Schurter's 5×20 line only the time-lag `SPT` carries a DC rating — there is no fast-acting 5×20
route.** That is why the fast-blow is a 10×38 midget.

- ⚠️ **`SPT`'s DC rating derates with current:** 0.5–3.15 A = **300 VDC** · 4–10 A = **150 VDC** ·
  12.5–16 A = 125 VDC.
- ⚠️ **A fuse *holder* has NO breaking capacity** — its voltage rating covers insulation and spacing
  only; arc interruption rests entirely on the link. DigiKey's default suggested holder for these fuses
  is a Keystone 4628 rated **250 VAC** — the weak-link trap, offered by default.
- ⚠️ **Automotive blade fuses are rated 32 VDC** and cannot interrupt an 84 VDC arc. DC arcs do not
  self-extinguish. Never fit one on this rail.
- ○ Value alternative to the `KLKD002`: **`KLKR002`** — 2 A, 600 VAC / **300 VDC**, 200 kA AC / 20 kA DC,
  Class CC, same body. ⚠️ Class CC has a **rejection cap** and needs a Class CC holder.

##### ⚠️ Two limits that stay open

- **`CN150B110-12` absolute maximum: unverifiable.** The word *"absolute"* appears **zero times**
  across four TDK primary documents. **Treat 160 VDC as the hard do-not-exceed, including transients**
  — the manual requires input ripple *peaks* to stay inside it, with ripple capped at 10 V p-p.
- ⚠️ **No part in this group carries a vibration or automotive qualification.** Schurter offers IATF
  16949 product only under customer-specific agreement; Chemi-Con publishes no vibration spec for KXJ.
  **The conformal-coat / stake / bond specification is still undefined** — a ceramic fuse body on long
  leads and the 18 × 25 mm capacitor cans are lead-fatigue geometries unless the leads are cut short and
  the bodies bonded.

#### 9.5.3 Prices

**`bom.md` owns prices and order state** — it logs what the 2026-09-10 orders actually
cost.

### 9.6 Prototype construction — generic FR4 prototype board (owner's choice, 2026-09-08)

This is the **prototype** unit; the final form is the custom PCB (§9.8), which removes several of the
constraints below. Soldered, not solderless — **solder joints don't work loose under vibration**.

⚠️ **The buying rule:**
- **FR4, double-sided, with PLATED through-holes.** ⛔ **Not brown phenolic/FR2 paper board** — its
  pads lift on rework and it is brittle. Plated holes let you solder from either face, which is how you
  reach pads under the DevKit.
- **2.54 mm (0.1") pitch**, with mounting holes or plan to drill them (§9.7 assumes M3).
- **Stripboard (Veroboard) for board D** — the strips become the +12 V and ground rails. **Plain
  pad-per-hole for boards A/B/C** — point-to-point signals.
- The purchased ElectroCookie boards (`B07ZYNWJ1S`) are spares — fine for small sub-assemblies; the mini
  board suits the display-switch daughter card.

⚠️ **The 84 V creepage limit (§9.6.2) is a property of the 0.1" grid** — keep HV off the grid and
conformal-coat anything above 12 V whatever board you buy.

#### 9.6.1 Board sizes and the DevKit

- **Board D** (the prototype's) wants ~**100 × 100 mm or larger** — ~15 screw terminals at 5 mm pitch
  (~75 mm of edge) plus the drivers, gate resistors, pull-downs and the reinforcement wire. One board.
  The custom DRV uses keyed right-angle harness connectors instead: a screw terminal is 10–12 mm tall,
  and connector height sets the stack's gaps (§9.2, M19).
- **Boards A / B / C** are small; one board per block.
- The **S3-DevKitC-1 is ~63 × 25.5 mm**. Its header rows are a whole multiple of 0.1", so it spans any
  0.1" grid; with plated through-holes every pin is reachable from the underside. ⬜ **M15** confirms the
  header spacing (expect 0.9" / 22.86 mm), copper weight and plating on whichever board is bought.

#### 9.6.2 Current capacity, creepage, and what prototype board does *not* fix

1. **Current capacity.** By IPC-2221 (1 oz copper, 10 °C rise) a **1 mm trace carries ≈ 2.4 A**; typical
   proto-board rails are 1–2 mm, so **3–4 A is the ceiling** against the real 2.62 A bus. **Reinforce the
   12 V rail and its return with soldered 20 AWG bare copper**, tacked to every pad.
2. ⚠️ **Creepage at 84 V is marginal on a 0.1" grid.** 2.54 mm pitch with ~1.8 mm pads leaves **~0.7 mm
   between pad edges**, against IPC-2221's **0.6 mm** for 31–100 V on an uncoated external layer — and
   IPC assumes a clean board. **Keep 84 V off the grid** wherever possible, **conformal-coat** anything
   above 12 V, and for the IN-12 divider skip the intervening pads.
3. **Switching converters still cannot be built on it** (§9.1).

**Rules for a board that lives on a motorcycle:**
- **Conformal-coat after testing passes.**
- **Strain-relieve every wire leaving the board.** Connectors for anything field-serviceable.
- **Standoffs, not a board floating in the box.**
- ⚠️ **The DevKit: machined-pin (turned-pin) sockets, never dual-wipe** — dual-wipe sockets walk out
  under vibration. Add mechanical retention over the module (a nylon standoff or clamp).
- **Every wire that leaves the box gets its TVS/ESD part on-board at the connector** (§4).

### 9.7 3D-printed housing (later pass)

⚠️ **Gated on §9.8:** the housing follows the custom boards' outline (§9.2), not the perfboard
stack's. Material, ingress, inserts and thermal rules below apply either way.

- ⬜ **The custom stack's enclosure material — printed or metal — is decided after M18** (owner,
  2026-09-18). The boards are drawn to suit either, and no thermal or height budget is final until it
  is. Either way the brick's baseplate bolts to a metal thermal interface (§3.2.3), which is the
  "bolt to metal" requirement below in its minimum form.
- ⚠️ **A metal enclosure — or a metal cavity with the battery tray for a lid — kills a PCB antenna.**
  BRAIN's footprint takes the external-antenna `-WROOM-1U` for that case (§9.8.1).

- Internal envelope: follows the boards — plan for **4 positions, A, B, C and one D**. Allow **≥20 mm per
  layer** if stacking (DevKit plus headers ~13 mm).
- ⚠️ **Mounting:** generic proto board may have **no mounting holes** — buy boards with them or drill
  before populating.
- ⚠️ **Brass heat-set inserts, not screws self-tapped into plastic** — printed bosses crack under
  vibration.
- **Keep the DevKit's USB port reachable**, or the design commits to OTA-only reflashing. On the
  custom build BRAIN carries USB-C and an internal service header (EN, IO0, UART0, 3V3, GND) — recovery
  access without dismantling the stack.
- ⚠️ **Material: not PLA** (softens at ~50–60 °C). **PETG (~80 °C) minimum; ASA preferred** for UV
  stability. ABS only if never sun-exposed.
- ⚠️ **Ingress:** printed walls **wick water along the layer lines** — a gasket channel and cable glands,
  or a sheltered mounting position.
- **At the prototype stage, block E goes in a METAL enclosure of its own:** the module is a
  **conduction-cooled pinned brick** whose baseplate wants to bolt to metal, a metal box is the right
  EMC answer next to 3.3 V serial taps and 80 A of chopped phase current, and it is the only sane home
  for the 84 V node. Whether it also needs moving air waits on the §3.2.3 measurement. The printed
  housing is for blocks A–D. The custom stack puts all four boards in one enclosure, whose material is
  the ⬜ item at the top of this section.
- Strain relief at every wire entry (§9.6.2).

### 9.8 ⭐ Custom PCB — the likely final form (owner's intent, 2026-09-08)

**Breadboard → generic perfboard prototype (§9.6) → custom PCB.** Build the prototype so it transfers,
and don't constrain the custom boards with DevKit artifacts. The custom build is the four-board set of
§9.2.

#### 9.8.1 Most of the pin-map constraints are DevKit artifacts, not silicon

| Constraint in §3.1.3 | On a custom PCB with a bare WROOM-1 |
|---|---|
| Only **36 of 45** GPIOs reach the headers | ✅ **Gone** — route all of them |
| **GPIO33, 34** not broken out | ⛔ **Unchanged — the module, not the DevKit.** The `ESP32-S3-WROOM-1` / `-1U` has no IO33 or IO34 pad; both exist only inside the module |
| **GPIO38 / 48** and the onboard RGB LED (the v1.0-vs-v1.1 trap) | ✅ **Gone** — no LED, or fit one where you like |
| **GPIO44** driven by the onboard CP2102N | ✅ **Recovered** with native USB (GPIO19/20) and no UART bridge — as an input (the IN-14 tap lands there). ⚠️ Its boot-time pull-up sits at a FET's threshold, so never a gate |
| **GPIO35, 36, 37** and octal PSRAM | ✅ **Yours by purchase order** — specify the module variant (§9.8.3) |
| ⛔ **Strapping GPIO0, 3, 45, 46** | ⚠️ **Unchanged — silicon.** No wire that leaves the box |
| ⛔ **GPIO19, 20 = USB** | ⚠️ **Unchanged** if you keep native USB — which you should (the OTA fallback) |
| ⛔ **GPIO43 emits the ROM boot log** | ⚠️ **Unchanged — silicon.** Never a load driver |
| ⛔ **GPIO26–32 = in-package flash · GPIO22–25 do not exist** | ⚠️ **Unchanged** |

**Net: a clean pool of 30** (the DevKit prototype has 28) — the 45 GPIOs that exist, less the 7 flash
pins (26–32), IO33/34 (no pads), the 2 USB pins and the 4 strapping pins. GPIO43 is inside the 30 but
stays unused (ROM boot log).

**One footprint, two modules.** The `ESP32-S3-WROOM-1` (PCB antenna, 18 × 25.5 mm) and the
`ESP32-S3-WROOM-1U` (U.FL connector for an external antenna, 18 × 19.2 mm) share pads and pinout, and
both come as `-N8` (85 °C) and `-H4` (105 °C), so D18 applies to either. BRAIN's footprint accepts
both and keeps the PCB antenna's keep-out. **The `-1U` matters because a metal enclosure — or a metal
cavity with the battery tray for a lid — kills a PCB antenna**, and Espressif asks for at least 15 mm
of clearance around one in every direction. Which module is fitted follows the enclosure decision
(§9.7).

#### 9.8.2 What gets easier, and what may reverse

- ✅ **D16 is FULL NATIVE on the custom board (owner, 2026-09-18).** The S3 drives the six used
  `TPS4H160B` inputs and `DIAG_EN` / `SEL` / `SEH` directly, over the STACK connector (§9.2) — **the
  I2C bus is out of the lighting path entirely.** Both `MCP23017`s are still fitted: #1 carries the bar
  inputs, where a bus glitch is a missed press; #2 is sixteen spare bits (GPA7/GPB7 output-only,
  §3.1.3).
- ⚠️ **Spare pins are scarce.** Full native moves eight signals off expander #2 and onto the S3, into a
  pool only two pins larger than the prototype's. The BRAIN pin assignment, and the count of what is
  left, live in `tools/netlist.py` and are checked by `tools/rules.py` — this plan carries the rules,
  not the numbers.
- ⚠️ **What does not change: the functional rules.** Carry these over verbatim — analog only on ADC1
  (GPIO1–10), brake inputs native for < 10 ms, boost on a dedicated pin with a hard external pull-down
  and never on a bus, nothing that leaves the box on a strapping pin, TVS at every connector, every gate
  biased OFF.

#### 9.8.3 ⚠️ Module variant — a THERMAL choice

From the ESP32-S3-WROOM-1 datasheet's ordering table:

| Variant | Flash | PSRAM | **Ambient temp** | Verdict for this build |
|---|---|---|---|---|
| `-H4` | 4 MB Quad | none | **−40 … +105 °C** | ✅ best thermally; 4 MB is enough with no screen (D17) — ⚠️ check OTA fits two app partitions |
| `-N8` / `-N16` | 8 / 16 MB Quad | none | **−40 … +85 °C** | ✅ **the default** — our prototype is an `N8`; 25 °C over the assumed ambient |
| `-N…R2` | Quad | Quad | −40 … +85 °C | ○ fine, but no PSRAM is needed |
| ⛔ **`-N…R8`, `-R16V`** | Quad | **Octal** | ⛔ **−40 … +65 °C** | ⛔ **Never** — only 5 °C over the assumed 60 °C ambient, and it costs GPIO33–37 |

Espressif, verbatim: *"H4 series modules operate at –40 ~ 105 °C ambient temperature, R8 and R16V
series modules operate at –40 ~ 65 °C ambient temperature, and other module variants operate at
–40 ~ 85 °C ambient temperature."* **→ D18.**

#### 9.8.4 What the custom board fixes that perfboard cannot

- ✅ **84 V creepage** — proper clearances and a slotted high-voltage section, instead of §9.6.2's ~0.7 mm.
- ✅ **A ground plane** — the big one: §3.2.4's concern is 3.3 V TTL serial taps beside 80 A of chopped
  phase current.
- ✅ **Trace widths sized to real current** — the 20 AWG reinforcement disappears.
- ✅ **Decoupling placed properly**, mounting holes, strain relief and conformal coat designed in.
- ✅ **Partition by voltage** — four stacked boards with 84 V at the floor and 3.3 V at the lid (§9.2),
  in place of five perfboards and their interconnect.

⚠️ **Do not skip the prototype stage.** A first-spin PCB with untested firmware and untested driver
circuits is how you buy three spins instead of one; the perfboard unit is what de-risks the layout.
The custom set keeps the option open to the end: every inter-board interface is on 2.54 mm pitch, so
a breadboard or perfboard section can stand in for any one board during bring-up (§9.2).

## 10. BOM → `bom.md`

📄 **The bill of materials lives in `bom.md`** — part numbers, quantities, prices, order
history and status. **Change a part there first**, then the plan section that carries its reasoning:
§3.2 power and D13 · §3.2.1 the TVS · §3.2.6 fuse and diode sizing · §4 interface classes and the
wetting-current rule · §6 outputs and drivers · §9.5 converters and support parts · §9.6 construction ·
§9.8 the custom PCB · §12 sourcing evidence. The brake circuit's parts are **group G**; their reasoning
is `brake-circuit.md` §3.

**Totals and order state live in the BOM, not here.** Its header carries the committed and estimated
totals and the tariffs they exclude; its order history shows what has arrived and what is outstanding.
Lines whose part or price is not yet verified are marked ⬜ or ◐ there. **The BOM header is
authoritative.**

- ⏸️ **Block F (display power switch) is not ordered** — it parks with D11 under D19.
- **Prices** are the ones the owner read from the distributor's own page — never a search snippet.
- **Not in this BOM:** the bike's own parts, including the issue #10 Class T fuse and block — they are in
  the build sheet's order tracker.

## 11. Sources

- Ride1Up "Revv 1 motor controller access" (the brake-lever wires run in the handlebar loom, §2.1) — https://support.ride1up.com/support/solutions/articles/65000189986-revv-1-motor-controller-access
- FarDriver *APP parameter description* (2025) — §5.1.5 CAN instruction number, §12.3 CAN agreement data. FarDriver's copyright: cited here, not redistributed
- `brake-circuit.md` — https://github.com/bnich/Revv1-FS-72v-Conversion/blob/main/docs/brake-circuit.md
- `harness-pinout.md` and `tools/heb_decode.py` — repository `fardriver-nd72450-reference` (not yet published)
- `pinout-3in-cj-v3-01.md` and `can18-investigation.md` — repository `chaojie-display-protocol` (not yet published)

---

## 12. Appendix — sourcing evidence for the selected parts

**Method rule:** specs come from the **manufacturer's datasheet PDF**, read with `pdftotext -layout` —
never from a web-fetch summary (a summary has already mis-stated a part's pin pitch and polarity).

| Part | Datasheet figures relied on | Source document |
|---|---|---|
| TDK-Lambda **`CN150B110-12`** | 43–160 VDC in; 12 V / 12.5 A / 150 W, 91.5%; non-latching OCP/OVP. Instruction manual: **FAST-blow** fuse ≤10 A on the +Vin leg; **≥100 µF** low-impedance electrolytic (KXJ class) at the terminals, two in parallel below −20 °C; **4700 pF** from +Vin and −Vin to the baseplate (the primary EMI measure); a choke per supply, before the bulk cap; input dv/dt ≤10 V/µs; **160 VDC hard instantaneous ceiling**, ripple ≤10 V p-p; no absolute maximum published | CN-B catalog + the 28-page CN-B instruction manual (`product.tdk.com` 403s every PDF; the same paths retrieve through `web.archive.org`) |
| Cincon **`EC7BW-110S05`** | 43–160 VDC in; 5 V / 4 A / 20 W; 3 kV iso; full 20 W to +73 °C; UVLO 40 V up / 38 V down; **1 A time-delay** input fuse; EN 50155 EMC only *"WITH EXTERNAL FILTER"*; names `P6KE180A` for EN 50121-3-2 surge; inrush I²t ≤ 0.1 A²s; hold-up table at 72 Vdc full load (180 µF → 10 ms, 560 µF → 30 ms); hold-up diode guidance: a 200 V / 10 A silicon-class part | Cincon datasheet |
| Littelfuse **`SMCJ90A`** | V<sub>RWM</sub> 90.0 V · V<sub>BR</sub> 100.00–111.00 V @ 1 mA · **V<sub>C</sub> 146.0 V @ I<sub>PP</sub> 10.3 A** (10/1000 µs) · I<sub>D</sub> 1 µA · 1500 W · DO-214AB | Littelfuse SMCJ datasheet table |
| Chemi-Con KXJ — bought as **`EKXJ221ELL221MM25S`** (220 V, same series and case code); figures below are the catalogue row for the 200 V **`EKXJ201ELL221MM25S`** | 220 µF / 200 Vdc ±20% · −40…+105 °C · **12,000 h @ 105 °C** · 18 × 25 mm radial, 7.5 mm pitch, φd 0.8 mm · tanδ 0.20 · Z(−40 °C)/Z(+20 °C) = 6 · ripple 1,050 mA<sub>rms</sub> (105 °C, 120 Hz). The 18 × 25 can is the shortest of four cases with equal ripple — the smallest cantilever moment. **No vibration or shock spec** (zero hits) | KXJ catalogue, CAT. No. E1001U |
| **`1N4007`** (Vishay `1N4007-E3/54`, onsemi `1N4007RLG`) | V<sub>RRM</sub> / V<sub>DC</sub> 1000 V · I<sub>F(AV)</sub> 1.0 A · **I<sub>FSM</sub> 30 A @ 8.3 ms half-sine, 45 A @ 1 ms square** · V<sub>F</sub> 1.1 V @ 1 A · I<sub>R</sub> 5.0 µA @ 25 °C · I²t 3.7 A²s · DO-41 · −50…+150 °C | Vishay / onsemi datasheets |
| Littelfuse **`KLKD002`** | 2 A fast-acting · **600 VAC / 600 VDC** · 10.3 × 38.1 mm midget · 100 kA AC / **50 kA DC** interrupting — the DC figure is a measured PV-approval rating (UL 2579 / IEC 60269-6), not an extrapolated AC one | Littelfuse KLKD datasheet |
| Schurter **`0001.2504`** (`SPT`) | 250 VAC / **300 VDC**, UL 1500 A breaking at 300 VDC — the DC rating comes **only from the UL/CSA listing** (the IEC/VDE line is AC-only); DC rating derates with current (§9.5.2) | Schurter SPT datasheet |
| Schurter **`FAC 0031.3803`** | PCB THT, **vertical, 47.5 mm tall**, 600 VAC/VDC UL, 10 A VDE / 16 A UL, −40…+85 °C, IP40. Power acceptance 3.2 W at 23 °C, ~1.2 W by 60 °C — fine for a 1 A link, **could not carry a 10 A link at 60 °C**. Too tall for the stacked build (§9.5.2) | Schurter FAC datasheet |
| Würth **`7448022010`** (WE-CMBNC) | 10 mH · 2 A @ 70 °C · 85 mΩ · 300 V AC · 2100 V AC hipot · −55…+125 °C · AEC-Q200 Grade 1 · four terminals (windings 1–4 and 2–3) · 22.0 mm tall × 18.0 × 14.0 mm max. An AC-only rating is the documentation convention for CM chokes (IEC 60938-2 is an AC standard) — a CM choke sees near-zero differential voltage. Only `WE-SL5` states a DC limit (80 V DC) and is out | Würth datasheets |
| TDK **`HAQ-10T`** | 7.5 °C/W natural convection, a free-air figure · 57.9 × 25.4 × 36.8 mm · for the CN-B110 series (fit ~85% confident, BOM E5). Not used in the stacked build (§3.2.3) | TDK |
| IXYS **`IXTP26P20P`** | V<sub>DSS</sub> −200 V · V<sub>GSS</sub> ±20 V continuous, ±30 V transient · V<sub>GS(th)</sub> −2.0…−4.0 V · T<sub>JM</sub> 150 °C · guaranteed SOA 160 W at −200 V / 5 s / T<sub>C</sub> 70 °C · forward-bias SOA plots at T<sub>C</sub> 25 °C **and 70 °C**, each with 25 µs, 100 µs, 1 ms, **10 ms, 100 ms and DC** lines. Read at 84 V on the 70 °C plot (±10 %): ≈460 W (10 ms) · ≈254 W (100 ms) · ≈191 W (DC). Upright it stands 17.5–21.8 mm, so it lies flat. `IRF9640PbF`: ~335 W on its 10 ms line at 84 V (~241 W derated for 60 °C). `FQP12P20`: no SOA plot at all | IXYS / Littelfuse **DS99913D** (not the 2007 "Preliminary" sheet) · Infineon / onsemi datasheets |
| Infineon **`BSS127`** | N-channel **enhancement mode**, logic level · V<sub>DS</sub> 600 V · V<sub>GS(th)</sub> 1.4 / 2.0 / 2.6 V · R<sub>DS(on)</sub> ≤ 600 Ω at 4.5 V · P<sub>tot</sub> 0.5 W · SOT-23. ⛔ The same-family `BSS126` is **depletion mode** (V<sub>GS(th)</sub> −2.7…−1.6 V, conducting at V<sub>GS</sub> = 0) | Infineon BSS127 / BSS126 datasheets, Rev 2.1 |
| onsemi **`SMS15T1G`** | SC-74 quad array, pins 1/3/4/6 cathodes and 2/5 anodes — the `PESD5V0S4UD`'s pinout · V<sub>RWM</sub> 15 V · V<sub>BR</sub> 16.7–18.5 V · clamps 24.0 V at 5 A, 29.0 V at 12 A | onsemi SMS05T1/D, Rev 10 |
| Microchip **`MCP23017`** | **GPA7 and GPB7 are output-only** · `RESET` and A0–A2 must be externally biased · 1.8–5.5 V · V<sub>IH</sub> 0.8 × V<sub>DD</sub> = 2.64 V at 3.3 V | Microchip DS20001952, rev D |
| Espressif **`ESP32-S3-WROOM-1` / `-1U`** | 41 pads, **no IO33 or IO34** · `-1` 18 × 25.5 mm with PCB antenna, `-1U` 18 × 19.2 mm with U.FL, same pinout · `-N8` −40…+85 °C, `-H4` −40…+105 °C, `R8` / `R16V` −40…+65 °C · the ambient rating is the air immediately outside the module | ESP32-S3-WROOM-1 / -1U datasheet v1.8; Espressif hardware design guidelines (15 mm antenna clearance) |
| Alpha & Omega **`AO3400A`** | Logic-level: **48 mΩ guaranteed max at V<sub>GS</sub> 2.5 V**; SOT-23, 30 V (caveats in the BOM) | AOS datasheet |
| TI **`TPS4H160BQPWPRQ1`** | See §6.2.2a. `CL` unused must be tied to ground, giving the internal 8–14 A limit; R<sub>CL</sub> = 0.8 V × 2500 / I; `CS` sources I<sub>OUT</sub> / 300 and drives 4.5–6.5 V in a fault | TI datasheet SLVSCV8 |
