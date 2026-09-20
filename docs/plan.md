# REVV1 ESP32 body module — planning document

**Status:** v0.11, 2026-09-20 — design; first parts ordered 2026-09-10, most received 2026-09-18.
The left bar pod is wired and tested; no module hardware is built.

⏸️ **The Chaojie CAN dash feed (§7.2 / D8) is parked by owner decision D19, 2026-09-10** — *"the
display we have now will either not work, or take too long to setup … we will come back to the
display later, and either figure it out or replace it."* **The rest of the module carries on.**
Parked is neither solved nor abandoned: the CAN findings stay correct, the CAN hardware stays fitted,
and the work resumes unchanged when the display question re-opens. Also parked with it: **D11** and
**block F** (`bom.md`).

⭐ **Construction path (owner, 2026-09-08): breadboard → generic perfboard prototype (§9.6) → custom
PCB (§9.8).** The DevKitC-1 is the prototype board only, and most of §3.1.3's pin constraints are
DevKit artifacts. The custom build is **three stacked boards — POWER · OUTPUTS · LOGIC (§9.2)** —
around a bare WROOM-1, with **D16 full native**, which takes I2C out of the lighting path. Carry the
*rules* across, not the GPIO numbers.

✅ **M13 is closed:** the module is an `ESP32-S3-WROOM-1-N8` (8 MB quad flash, no PSRAM,
−40…+85 °C) on a DevKitC-1 **v1.0** (RGB LED on GPIO48). GPIO35/36/37 and GPIO38 are usable: clean
pool **28**, **21 native used, 7 spare** (§3.1.3). D18: use an `N8` on the custom board too.

**Where the design stands:**
- ✅ **Power block (board E) sourced and ordered** — TDK `CN150B110-12/CO` + Cincon `EC7BW-110S05`
  (§9.5.1), bulk cap `EKXJ221ELL221MM25S`, hold-up diode `1N4007`, fast-blow `KLKD003` (§9.5.2).
- ✅ **12 V rail budget: 8.47 A / 101.7 W** — the 2.62 A of lamps, fan and display (1.62 A of it
  measured, M4–M7) plus the eight aux outputs at the 1 A each **D27**/IO-2 asks for (§3.2.3).
  `tools/power_budget.py` derives it and says which case it models.
- ✅ **TVS: `SMCJ90A`** — clamps at 146 V at its rated 10.3 A (~7.4 A at 60 °C), under TDK's 160 V
  ceiling (§3.2.1). ⬜ **M17** confirms it on the bike.
- ✅ **D13 soft-start FET: `IXTA26P20P`** (TO-263, placed by JLC), selected on SOA and ramped over
  **~50 ms** (§3.2.5). Low-side FET: `AO3400A` (§6.2.3).
- ✅ **D16 decided: full native on the custom board** — every firmware-driven lighting channel on its
  own S3 pin, the I2C expanders carrying inputs only: the bar controls and slow sense lines (§9.8.2).
  The pin map drawn in §3.1.3 is the **DevKit prototype's**, which keeps low beam and boost native and
  puts the slow outputs on expander #2.
- ✅ **Starting (D24, owner 2026-09-18):** the key switch feeds the FarDriver KEY wire directly
  (§3.2.5). There is no start latch; the right pod's start button is a spare sensed input.
- ✅ **The brake cut, the brake lamp and the run/off kill are firmware functions (D23, 2026-09-19)** —
  there is no dedicated brake circuit on the module. The levers are plain fast inputs, `BL` is an
  open-drain output and the STOP lamp is an ordinary `TPS4H160B` channel (§6.2.2a, §7). With the
  firmware not running the cut is **released** and the lamp is **off**; the key switch is the one
  hardware kill (D24).
- ✅ **D17: the module has no screen** — the Chaojie is the only display; with D8 parked the **WiFi
  page is the primary readout** for motor temp, controller temp, bus current, boost mode and lamp-out.
- ✅ **Controls (D20–D22):** both original bar pods are replaced by bought switch sets — plain class-A dry
  contacts, a 3-position lighting slider, a 3-position turn switch (§2.0).

**⬜ Open:**
- **Watchdog period (§7)** — a safety figure, ≤300 ms; measure the real reset-to-lamp-on time. With
  the brake cut in firmware (D23) it is also what bounds a lost cut.
- **M3** — the brake-lever switch type gates `J306`, the lever terminal, and its wire count.
- **M18** — the enclosure cavity. Gates the enclosure model (§9.7) and confirms the cavity the board
  envelope requires.
- ⚠️ **The boards are 48 × 219 mm, and the cavity they require is bigger than M18's estimate**
  (§9.2). `tools/board_params.py` sizes the boards to the design (D27/IO-14) and states the cavity
  that implies: **233.0 mm along × 74.65 across × 68.4 tall**, against the working estimate of
  200 × 50 × 70 — **33.0 mm longer and 24.7 mm wider**, with 1.6 mm of height to spare. That is a
  finding for M18, which confirms it or forces a rethink; it is not argued away.
- **DC-DC #1's dissipation at the real 101.7 W load** — unverified, ~10 W derived; measure it before
  any thermal budget is trusted (§3.2.3, owner item 4, at 8.5 A).
- Measurements: **M2 · M3 · M8 · M9 · M10** (bench session), M14 current at exactly 12 V, M15, M17,
  M18, M19.

**⭐ CRITICAL PATH (every step is display-independent, D19):**

| | Step | Why here |
|---|---|---|
| **1** | ✅ **Sourcing and first order** — orders placed 2026-09-10; most lines received 2026-09-18. Remaining lines are estimates — **`bom.md`** owns parts, prices and order state | Longest lead time. ⚠️ A 25% tariff appeared on the Mouser line (BOM). ⛔ Block F is not in this order — it parks with D11 |
| **2** | ◐ **Bench session M2 · M3 · M8 · M9 · M10**, plus ohming out the new switch sets — ✅ **left pod done 2026-09-11** (identified, harnessed, 9-pin connector fitted, all controls tested working); ✅ **right pod in hand 2026-09-12 — its lighting slider measured `OFF / A / A+B`, which is what D21's decode needs (§2.0)** — procedure: **`inputs-bench-session.md`** | Gates the input conditioning (**block C**) and the firmware's input map. Needs the *bike*, not the parts. ⚠️ **M3** (unpowered lever-type check) gates `J306`: a three-wire Hall lever adds a supply pin to the terminal |
| **3** | ⬜ **Firmware** — lighting lookup (§7), read-the-slider-at-boot, the **≤300 ms** watchdog, the brake function (cut, lamp, kill), the **key-off aux shed** (D27/IO-16), boost HOLD/TOGGLE, the **WiFi status page** | The brake cut and the brake lamp are firmware (D23), and `Q101`'s key-off SOA margin depends on the shed (§3.2.5). The WiFi page is the only readout for temps, bus current, boost mode and lamp-out |
| **4** | ⬜ Breadboard → perfboard prototype (§9.6) → the three-board custom set (§9.2, §9.8) | Needs 1–3. ⬜ **M18** (the cavity) confirms the enclosure the 48 × 219 mm boards require |

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
    **§6.2.2a** `TPS4H160B` · **§6.2.2b** the aux block · **§6.2.3** low-side · **§6.2.4** protection
- **§7** Behaviour rules — turn signals, lighting, brake light, boost, startup, watchdog
  - **§7.1** Boost path
  - **§7.2** CAN (⏸️ parked) — **§7.2.1** what the vendor documents give · **§7.2.2** active probing ·
    **§7.2.3** community evidence · **§7.2.4** M16
- **§8** Decisions
- **§9** Component breakdown and build plan
  - **§9.1** Breadboard rules · **§9.2** Functional blocks and the three-board set · **§9.3** Breadboard allocation ·
    **§9.4** Bench supply · **§9.5** Converters and support parts · **§9.6** Perfboard prototype ·
    **§9.7** Housing · **§9.8** Custom PCB and module variant (D18)
- **§10** BOM → `bom.md`
- **§11** Sources
- **§12** Appendix — sourcing evidence for the selected parts

📄 **Documents cited by file name:** `bom.md` and `inputs-bench-session.md` sit beside this file;
the work order, checklist, build sheet and issues log are in the build repository
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
   turn signals, dash telltales, the boost button, **the brake lamp and the motor cut** (D23), and
   **four 12 V and four 5 V aux outputs** for whatever the owner wires to them (D27).
   ⚠️ **The brake cut, the brake lamp and the run/off kill are firmware functions.** With the
   firmware not running the cut is released and the lamp is off; the key switch is the one hardware
   kill (D24).

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
| **Run/off toggle** | ✅ latching — **right pod**, `red` + `blue` common | 1 | IN-11 | **The secondary kill, in firmware.** A plain class-A contact (closed in RUN); the firmware treats it as a kill slot and asserts `BL` when it opens. No hardware depends on it, so with the firmware stopped the bike drives. ⛔ Not the 84 V KEY line — no DC rating on a bar switch |
| **Start button** | ✅ momentary — **right pod**, `green` + `blue` common | 1 | spare (sense) | **Spare.** A class-A contact sensed on expander #1 with no function assigned — the key switch alone starts the controller (D24, §3.2.5a). Wired now, assigned in firmware later |
| **Boost** | momentary | 1 | IN-07 | On the FarDriver throttle, not a pod: its 2-pin lead lands on the serial connector with its own return (§9.2) and is read over I²C on expander #1. HOLD/TOGGLE, D4 |
| **Brakes** | lever switches (type per **M3**) | 2 | IN-05/06 | **Plain fast inputs** on native pins (D23): each lever wire is a class-A contact to ground with a 1 kΩ pull-up at the module, read on an interrupt. Firmware asserts `BL` and the STOP lamp from them |

**The bar controls take 12 of expander #1's 14 input-capable bits** (GPA7/GPB7 are output-only,
§3.1.3) — the left pod's 7 (the selector takes two), the right pod's 4 (running, headlight, run/off,
start), and the throttle's boost button. A thirteenth carries the `BL` readback and the fourteenth is
spare. The **13 free inputs** are expander #2's remaining bits, each class-A conditioned on the board
and brought out on two fitted 8-way terminals in the INPUTS row, `J409` and `J410` (§9.2).
Rule for the spares: **wire them now, assign them in firmware later** — the bar-to-box cable is the
irreversible part; the function is one line of code.
⬜ **Still to ohm out:** ⭐ **that the left pod's push-push latch really breaks contact on unlatch**
(latched = closed, unlatched = open).
⚠️ **The two pods share colours for different jobs:** on the right pod (rewired 2026-09-12) **`blue` is
the ground** for all three controls, `black`/`yellow` are the slider bits, `red` the toggle and `green`
the start button; on the **left** pod `blue` is the HIGH-beam signal and `black` carries hazard.

**Other controls and interfaces on the bike:**

| Item | Where | What it is | Source |
|---|---|---|---|
| Brake levers | both | One switch or sensor each. Type, NO/NC and wiring **to be measured (M3)** — it sets `J306`'s size | `inputs-bench-session.md` §6 |
| Throttle red button | FarDriver throttle (installed, D2) | One momentary button on a **2-pin lead** — a dry contact | checklist Phase 5; FarDriver pinout doc |
| Chaojie dash keys | 3" display housing | Five keys, `M` / `+` / `−` functional, two reserved, all internal to the display — the 9-pin plug has no key-output position | `CJ-V3-01` manual; M11 |
| PAS cadence sensor | cranks / bottom bracket | **3-pin connector — +5 V, GND, Hall pulse.** Orphaned: it belonged to the retired stock controller, and **the FarDriver has no PAS input**. Using it for assist would mean the module synthesising a throttle signal, putting firmware in the motor-*control* path — which D10 and the open-drain, default-off boost output exist to avoid. (The firmware may *cut* the motor, D23; it may not command it.) ⬜ **Cap it, or wire it as telemetry only** (the expanders have free input bits; nothing would act on it). ⬜ Confirm it is cadence: ~5 V across two pins, third pulses several times per crank revolution | seen on the bike, 2026-09-11 |
| Key switch | frame | 2-wire switch feeding the FarDriver KEY wire; it also gates the module's power switch (§3.2.5) | work order §2 |
| FarDriver serial | controller harness | TXD / RXD / BW5V / GND, 3.3V TTL, 16-byte CRC frames | `harness-pinout.md` §4 |
| Chaojie dash | bars | telltale inputs L / R / headlight (0–15V), one-line in, CAN | `pinout-3in-cj-v3-01.md` |

### 2.1 Harness — where the lever and lamp wires run

The **brake-lever wires run in the handlebar loom to connector "1T3 10"**; the **lamp feeds run in the
"2T4 18" loom**. The lever wires land on `J306` in the INPUTS row (§9.2) and the lamps on the §6
outputs; the handlebar pods are replaced (D20). **M2** identifies the lever wires in the loom,
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
| IN-05 | Brake, left lever | lever switch or sensor (**M3**), on `J306` | momentary | normally-open dry contact, or a sinking open-collector output (M3) | **A** — a plain contact, 1 kΩ pull-up to 3.3 V | **The motor cut and the brake lamp** (D23, §7), on an interrupt; boost safety-release; telemetry | **M3.** A **native** pin: the cut must leave on an interrupt, not a bus poll. ⚠️ A broken normally-open lever wire reads as "not braking" and nothing can tell |
| IN-06 | Brake, right lever | lever switch or sensor (M3), on `J306` | momentary | as IN-05 | **A** | as IN-05 | M3. Native, on GPIO20 (§9.8) |
| IN-07 | Red button | FarDriver throttle 2-pin lead | momentary | dry contact | A | **boost request → module → controller** (D4): hold or toggle mode, long-press switches mode | M8 |
| IN-08 | Lighting slider — 3 position | right pod — **`black`** (IN-08a) + **`yellow`** (IN-08b), common **`blue`** | latching, 3-position | dry contact — **two bits** | **A** | **D21: 1 = OFF · 2 = running · 3 = headlight.** ✅ **`OFF / A / A+B` confirmed 2026-09-12:** `black` closes in 2 and 3, `yellow` only in 3 — so "headlight implies running" is in the hardware. ⭐ Decode **`headlight = yellow`, `running = black OR yellow`**, so a broken `black` still lights the bike. Full table: §7 | ✅ measured. Read at boot |
| IN-09 | Flash-to-pass | left pod — **`red-gold`**, the rear headlight-marked button | momentary | dry contact | **A** | Holds HIGH while pressed, any lighting state. **Break-before-make** against LOW; ≤10 ms debounce; no-op if already HIGH | ✅ **Built and tested.** Needed two cuts in the pod: `red-white` off the shared feed and the `red-gold`–`blue` tie opened |
| IN-10 | Hazard | left pod — **`green-black`** (hazard trio) | latching | dry contact | **A** | Both signals together; works with every other light off. ⭐ **Its own input rather than "LEFT+RIGHT both asserted" because a turn signal must auto-cancel and hazard must never** — and two independent push-push latches make that inference ambiguous | ✅ **Built and tested** |
| IN-11 | Run/off toggle | right pod — **`red`**, common **`blue`** | latching, **closed in RUN** (confirmed 2026-09-12) | dry contact | **A** — 1 kΩ pull-up to 3.3 V, on expander #1's GPB2, like every other bar contact | **The secondary kill, in firmware** (D23): open = OFF, and the firmware asserts `BL`. ⛔ **Never the FarDriver KEY line** — it sits at 72–84 V and a 12 V-market bar switch has no DC rating; it would also take the lights down with the motor | wire it now |
| IN-12 | KEY state | the key-switch output node `KSW`, **upstream of the hold-up diode** (§3.2.2) — the same node that feeds the FarDriver KEY wire (§3.2.5) | level | 72–84V | B (divider) | orderly shutdown, wake logic, and key state for the WiFi page | M10 |
| IN-13 | FarDriver telemetry | serial TXD/RXD | UART 3.3V | 16-byte frames | E | gear, faults, brake/throttle state as cross-checks, temps and currents for the WiFi page (and the parked CAN feed, §7.2) | M9 — direction must be measured, the label is ambiguous |
| IN-14 | Dongle activity | BT dongle's TX to the controller | UART 3.3V | | E | "polite listener": module sends keepalive only when the dongle is silent | M9 |
| IN-15 | 12V rail sense | DC-DC output | analog | 0–15V | D | diagnostics, lamp-out detection later | |
| IN-16 | Ambient light | photodiode/LDR | analog | | D | auto headlight (optional) | parked |
| IN-17 | Kickstand | none stock | — | — | — | not fitted; one of the 13 free inputs takes it | |
| — | **13 free inputs** | `J409` + `J410`, the INPUTS row's general terminals | anything | dry contact to ground, or 3.3 V logic — ⛔ nothing above 5 V | **A**, conditioned on the board | unassigned (D27/IO-4). Each already has its 1 kΩ pull-up, `SMS05T1G` line, 1 kΩ series and 100 nF, so a new control needs a wire, not a board change | expander #2 |
| — | Chaojie housing keys | 3" display | — | internal | — | not module inputs — five keys, all internal to the display (M11) | pin 6 (red, "reserved") is the only candidate output |

**Input count:** 25 class-A contacts (12 bar and throttle, the 13 free), 2 native fast contacts (the
levers), 4 sense lines (key, 12 V rail, `ACC+`, the `BL` readback), 2 UART RX (+1 TX).

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
   C6's two HP UARTs would both be consumed, leaving none for the console; the S3 has 3.
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
- **Brake inputs IN-05/06 stay native** — the motor cut leaves on their interrupt (D23), and the
  boost safety-release (§7) wants them in under 10 ms.
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
- **GPIO19/20 are USB D−/D+.** On the DevKit they are its native USB port, and reserved. The custom
  board has no USB port — flashing and the console run over UART0 (§9.8.1) — so there they are
  ordinary pins; GPIO20 comes out of reset pulled up.
- **GPIO43 = U0TXD** emits the ROM boot log at 115200 baud on every reset → **never a load driver.**
- ⚠️ **Strapping pins GPIO0, 3, 45, 46** (S3 datasheet; bench-confirm before committing the map).
  **No wire that leaves the box may land on these.** GPIO0 is the boot-mode pin — a rider holding a
  brake lever at key-on that grounds GPIO0 puts the module into download mode and it never runs: no
  lights, no dash, on the road.
- **Boot state — one rule (D14): every output gate is biased OFF.** GPIOs are inputs for the ~200 ms
  of boot, so each output's default is whatever its bias says:
  - **Lighting (high-side):** the `TPS4H160B`'s internal input pulldowns hold every channel OFF while
    the S3 pin is high-Z (§6.2.2a). The discrete fallback (§6.2.2) pulls its P-FET gate up to +12 V.
    On the custom board `AUX12` is an ordinary firmware-driven channel on expander #3, and the
    expander's own pins come out of reset as inputs, so it too starts off (§6.2.2a).
  - **Low-side** channels (horn, buzzer, fan, boost): ~10k gate **pull-down**.
  - ⚠️ **Not every pin is high-Z at reset:** GPIO0, 20, 39, 43 and 44 come out of reset pulled UP.
    **None of them may drive an active-high enable** — through a `TPS4H160B` input, GPIO39's pull-up
    would light a lamp from reset until firmware runs, and keep it lit through a hang.
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
| **Brake inputs IN-05/06** — the motor cut leaves on their interrupt, and the boost safety-release wants < 10 ms | `DIAG_EN` · `SEL` · `SEH` |
| **Fan and buzzer** — need LEDC PWM | |
| **All analog** — ADC1 only | |

On the custom board the **STOP lamp command and `BL`** join this list: both are firmware outputs on
native pins, chosen so that neither is asserted through boot (§9.8).

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
| **15** | IN-05 — left brake lever | wire leaves the box → clean pin, TVS at the connector; 1 kΩ pull-up |
| **16** | IN-06 — right brake lever | as GPIO15. ⚠️ On the custom board the right lever moves to GPIO20 and GPIO16 carries `BL` (§9.8) |
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
wire. (On the custom board one carries the `BL` copy, the other stays spare, and the wired spares move
to expander #2, §9.8.2.)
⛔ **`MCP23017` pins GPA7 and GPB7 are OUTPUT-ONLY** (Microchip DS20001952 rev D) — never land an
input on them, and have firmware set `IODIR` bit 7 to output on both ports. That is why a 16-bit
expander offers 14 inputs.
**Expander #2 — outputs (8 of 16):** TPS4H160B #1 `IN3`/`IN4` and #2 `IN1`–`IN4` for headlight HIGH,
DRL, tail running, turn L, turn R (5 channels + 1 spare) · `DIAG_EN` · `SEL` · `SEH`.
On the prototype TPS4H160B #1 `IN1` is left to its internal pulldown: **six of the eight channels are
used; two are spare.** The custom board uses all eight — #1 `IN1` is `AUX12` and #2 `IN4` is the STOP
lamp, both ordinary firmware-driven channels — and adds a third package for the four 12 V aux outputs
(§6.2.2a).
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
| **DC-DC #1** | **43–160 V** | **12 V** — load **8.47 A / 101.7 W** (§3.2.3) | headlight, tail, signals, horn, fan, display switch, the four 12 V aux outputs and the 5 V aux buck |
| **DC-DC #2** | **43–160 V** | **5 V** | the logic. Prototype: the DevKit's `5V` pin and its onboard 3.3 V regulator. LOGIC: a bare module has no regulator, so a `TLV76733` (5 V → 3.3 V, 1 A) feeds it. ⛔ **Not** the 5 V aux rail, which is its own buck off V12 (§6.2.2b) |

⚠️ **The input rating is 160 V — and that is architectural, not margin.** A 100 V-rated die **cannot be
protected at all**: the TVS must not conduct below the controller's **90.7 V** OV-protect, and every
TVS with a standoff that high clamps far above 100 V under surge. TDK publishes **no absolute maximum**
and states **160 VDC is a hard instantaneous ceiling** — input ripple *peaks* must stay inside it,
ripple capped at 10 V p-p. **Treat 160 VDC as do-not-exceed including transients.** At 84.0 V the pack
sits at ~53% of it; a 90.7 V excursion is 57%.

✅ **TVS: `SMCJ90A`.** Clamp voltage is a function of surge current, not a constant, so the criterion
is the current each part is rated to clamp at under TDK's 160 V:

| | Package | V<sub>C</sub> | at I<sub>PP</sub> | Price |
|---|---|---|---|---|
| ✅ **`SMCJ90A`** (1500 W) | DO-214AB | **146.0 V** | **10.3 A** | **$0.47** |
| `SMBJ90A` (600 W) | DO-214AA | 146 V | 4.1 A | $0.58 |

*(Both: V<sub>RWM</sub> 90.0 V · V<sub>BR</sub> 100.00–111.00 V at 1 mA · I<sub>D</sub> 1 µA · 10/1000 µs,
from the Littelfuse tables.)* Same standoff and clamp; the SMC die reaches it at 2.5× the current,
for less money. ⚠️ **I<sub>PP</sub> is a 25 °C rating** — Vishay's SMCJ90A derates to ~7.4 A at
60 °C — and above I<sub>PP</sub> the clamp voltage is unspecified: never extrapolate a clamp past it.

- **Not `SMBJ100A`** — its 162 V clamp exceeds TDK's 160 V ceiling.
- **Not `5KP90A`** — axial leads are a lead-fatigue geometry on a vibrating machine; DO-214AB is
  surface-mount.
- **10.3 A (~7.4 A hot) is ample:** this is a battery node, not an automotive one — **no load dump**,
  no alternator, regen OFF. The transient sources are cable inductance × di/dt (a short branch off
  B+, ~1–2 µH; interrupting even 125 A stores ½LI² ≈ **16 mJ**, against the SMCJ's ~1.5 J — ~100×)
  and converter switching, which TDK bounds with the 10 V p-p ripple cap.
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

#### 3.2.3 Current budget — **8.47 A / 101.7 W** (✅ M4–M7 measured 2026-09-08; the aux block derived)

⭐ **`tools/power_budget.py` is the home of every figure in this section.** It reads the aux channels
and their limiters off the netlist, sizes at the LVC, and **states which case it models.** Run it
rather than copying a number out of here.

| Load on the 12 V rail | Current | Gate |
|---|---|---|
| **Headlight LOW (8.5 W)** | **0.71 A** | ✅ M4 |
| **Headlight HIGH (8.5 W)** — *replaces LOW, not additive* | **(0.71 A, exclusive with LOW)** | ✅ M4 · D14 |
| **DRL (6.5 W)** | **0.54 A** | ✅ M4 |
| **Tail running** | **0.05 A** | ✅ M5 |
| **Tail STOP** — an ordinary `TPS4H160B` channel the firmware drives (§6.2.2a) | **0.12 A** | ✅ M5 |
| **Turn signals, one side (front + rear)** | **0.10 A** | ✅ M6 (front assumed = rear) |
| **Measured subtotal** | **1.62 A** | one beam only (D14) |
| Still estimated: fan 0.50 · display (if on 12 V) 0.40 · telltales 0.10 | 1.00 A | ⬜ M14 for the display |
| **Base — lamps, fan, display, telltales** | **2.62 A = 31 W** | night · one beam · DRL · braking · signalling · fan |
| **4 × 12 V aux at 1 A** (D27/IO-2) | **4.00 A** | derived from the netlist |
| **4 × 5 V aux at 1 A**, 20 W through a ~90 % buck | **1.85 A** | derived |
| The 5 V buck's own standing draw — ⚠️ **not sheddable** (`U305`'s `EN` is tied to its `PVIN`) | 0.25 mA | derived |
| **NOMINAL TOTAL** | **8.47 A = 101.7 W** | **68 % of the brick's 12.5 A** |
| Horn — electronic | **0.10 A** | ✅ M7 |

The whole lighting system is LED; the horn is an **electronic 12 V horn drawing 0.10 A**.
⚠️ **Use 8.47 A / 101.7 W everywhere.** Never count both headlight beams — D14 forbids it (one beam
+ DRL = **1.25 A**).

⚠️ **8.47 A is the NOMINAL case, not a ceiling.** It is the 1 A per channel D27/IO-2 asks for. Held
at their **current limits** instead — 1.55 A per 12 V channel, 1.39 A per 5 V channel — the eight
draw **11.39 A**: still inside the brick, but **2.53 A into the choke (84 %)** and **2.58 A through
the tap fuse (86 %)**, over both derates. That case is eight simultaneous output faults, and a
fast-blow fuse opening on it is the fuse working. `power_budget` prints it on its `LIMITED` line
beside the case the input path is sized against.

⚠️ **And the firmware sheds all eight at key-off** (D27/IO-16, §3.2.5). `power_budget`'s `SHED` line
is what is left: **2.62 A at 12 V, 0.63 A at the tap** — the load `tools/soft_start.py` holds
`Q101`'s key-off decay to.

**Thermal — ⬜ DC-DC #1's dissipation at this load is unverified, and it is now ~10 W, not ~3 W.**
TDK's **91.5 %** is the *full-load* efficiency (150 W); 101.7 W out is **68 % of rating**, where that
figure is closest to honest. It puts the loss at ~9 W, and the 90 % `power_budget` sizes with puts it
at ~11 W. ⬜ **Measure it; the converter, the bench supply and a load are in hand:** draw **8.5 A**
from the 12 V output and read the input power and the baseplate temperature, at the bench supply's
64 V ceiling (§9.4) and again at pack voltage — **owner item 4, and the aux outputs are not trusted
all-on until it exists.** No baseplate temperature is final until that number exists.
- **Limits:** baseplate −40…+100 °C, over-temperature trip at 105–120 °C, so target T<sub>b</sub>
  ≤ 85–90 °C. ⚠️ The 60 °C ambient used for that target is an assumption — re-check it once the box
  has a mounting position.
- **The brick is conduction-cooled, so it bolts to a thermal interface** — metal that carries its heat
  out of the enclosure. It sits on POWER's underside and **bolts its baseplate to the box floor
  through a 0.5 mm thermal pad: the floor is the heatsink** (D27/IO-11, §9.7). The floor liner is cut
  away there.
- **Not the `HAQ-10T`** (7.5 °C/W, a free-air figure; BOM E5): a finned sink sealed inside a box only
  heats the trapped air, and 25.4 mm of fin on a 12.7 mm brick does not fit the stack (§9.2).
- ⚠️ **An over-temperature trip takes the whole 12 V rail down** — every lamp, the horn, and the brake
  lamp with them (§7). The thermal path is a lighting-safety item.

✅ **Converter: keep the TDK `CN150B110-12`** — it was ~4.8× oversized against the base load and now
runs at 68 % of its rating, and smaller parts in this series cost *more* (§9.5.1).

**Input fusing.** TDK-Lambda's instruction manual **mandates a FAST-BLOW fuse** of 10 A or lower,
sized with I²t headroom for turn-on inrush, on the **+Vin leg** when −Vin is ground. Cincon asks for a
**1 A time-delay** on the logic rail. D13(b)'s soft-start is what makes a fast-blow viable, by removing
the inrush that would otherwise nuisance-blow it. **Value: 3 A** (§3.2.6(b)).

**Input current is computed at the 60.0 V LVC, not at 84.0 V.** A converter is a **constant-power**
load: as the pack sags, input current rises, so a full-charge figure under-sizes by ~40% exactly when
the pack is weakest.

| Rail | Power in | @ 84.0 V (full) | @ 72 V (nom) | **@ 60.0 V (LVC)** ← size here |
|---|---|---|---|---|
| **12 V load** — 101.7 W out (the budget above), at 90 % | **113 W** | **1.35 A** | 1.57 A | **1.88 A** |
| **5 V logic** — realistic ~2.5 W out | **3 W** | 0.04 A | 0.04 A | **0.05 A** |
| **Module total, at the B+ tap** | **116 W** | **1.38 A** | 1.61 A | **1.93 A** |

⚠️ **Two sizing rules:**
1. **Size every fuse, choke and input conductor at the LVC current, never at full charge.**
2. **Size at the load budget, never at the converter's nameplate** (150 W nameplate at the LVC gives
   3.13 A — 1.6× the budgeted 1.93 A).

✅ **The module's B+ tap fuse is 3 A** (1.55× the 1.93 A LVC draw; 64 % of the fuse, against a 75 %
continuous-duty derate): Littelfuse `KLKD003` — §3.2.5, §9.5.2. ✅ **And `L101`, the 12 V converter's
input choke, is the ≥ 3 A `7448023005`** — 1.88 A is 63 % of it, against an 80 % derate (§3.2.6).

#### 3.2.4 ⚠️ Grounding — the rule that quietly corrupts the serial taps if skipped

**Reference the module's ground to the CONTROLLER's B− stud, not the battery's B−.**

80 A of chopped motor current through the B− cable drops real volts across it, and the module reads
the FarDriver's **3.3 V TTL** serial *referenced to controller ground*. Ground the module at the
battery and that IR drop, plus PWM switching spikes, arrives as common-mode noise on IN-13/IN-14. One
star point, at the controller B−.

**Non-isolated converters are correct:** common ground is what the serial taps and the CAN transceiver
want; correct star grounding buys what isolation would.

- ⚠️ **Residual:** the FarDriver's own grounds still close a loop with the module ground. The star
  point keeps it small; it is not designed out.
- ⚠️ **A laptop on LOGIC's service pads (`J408`) bonds its ground to the bike's.** Use an isolated USB
  adapter, or a laptop on battery, whenever the pack is connected.

#### 3.2.5 Module power switching — the key switch stays a logic switch (D13)

**The problem is inrush, not steady current.** Closing a mechanical contact onto the module's bulk
capacitance at 84 V produces a spike limited only by wiring resistance — **tens of amps for a few
hundred microseconds, every key-on** — which pits and welds contacts. The steady draw (**~1.93 A at
the LVC**, §3.2.3) rides the module's own 3 A tap fuse, not the key branch's.

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
            └─[3A FAST]── P-MOSFET high-side switch ──┬──[C1 ≥100µF/200V]──┐
              KLKD003     (soft-start ~50 ms, §3.2.6a) │   TDK's EMC bulk,  │
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

⚠️ **Two fuses, two branches, two values — and only one of them changed.** Both hang off the XT90-S
and both are harness parts, not board parts:
- **the key branch keeps its 2 A fuse.** It carries the FarDriver KEY wire plus the module's two
  resistive taps — **~0.32 mA**. ⛔ Never uprate it: a 3 A link there protects nothing it needs to.
- **the module's B+ tap is the 3 A `KLKD003`**, because the aux block put 1.93 A through it (§3.2.3).

Both taps — the fused B+ and the key switch's output, `KSW` — enter the module on one plug, J101
(§9.2).
⛔ **No TVS on `KSW`.** The wire reaches only two ≥330 kΩ resistive strings, whose far ends D106 and
C109 hold; a TVS there would be the one part that fails short, blowing the key fuse and cutting the
FarDriver KEY.

Why this is the right answer:
1. **The key switch carries only the FarDriver KEY wire plus two resistor dividers — ~0.32 mA at
   84 V** (the D13 enable divider, 0.08 mA, and the IN-12 sense divider, 0.25 mA). An ordinary 72 V
   e-bike key switch is correct (~$10–15, already in the build sheet); its documented 12–96 V spec
   governs and no current rating is needed.
2. **Soft-starting the gate eliminates the inrush** rather than making a contact survive it. The
   ~50 ms ramp also keeps input dv/dt far inside TDK's ≤10 V/µs limit.
3. **The §3.3 display switch is the same idea at a far smaller C** — a soft-started high-side P-FET
   (parked with D11).
4. **The key switch's own wiring is unchanged** — it feeds the FarDriver KEY wire directly through
   its ~2 A inline fuse, low-current logic only, and golden rule #2 is untouched. ⬜ **The work order,
   checklist and build sheet still need the module's two taps drawn in:** a ~0.3 mA tap on the
   key-switch output, and the module's own 3 A fused B+ tap (`KLKD003`).

**The gate network** (on POWER, §9.2). Q101 is the `IXTA26P20P` (TO-263), source on the fused B+ tap,
drain to the converters. ⚠️ Its tab is the drain, soldered to board copper at 84 V: keep clearance to
every other net, and no metal under it.

| Part | Value | What it protects |
|---|---|---|
| `R110`, gate → source | 100 kΩ | D14's bias-OFF: V<sub>GS</sub> = 0 with the key off |
| `D102`, gate → source | 15 V zener, `BZT52B15` (2 % B grade) | the FET's ±20 V gate rating. A C grade can clamp at 13.8 V, too near the −13.1 V running V<sub>GS</sub> |
| `C105`, gate → **drain** | 68 nF C0G, 630 V, 2220 (TDK `CGA9N1C0G2J683JT0Y0S`) | the Miller capacitor: it sets the output slew, and so the ramp. With the switch off it sees the full pack, and 146 V at D101's clamp — hence ≥250 V, and C0G because X7R loses half its value at that bias. ⚠️ **Layout: keep it away from mounting holes and board edges** — a 2220 cracks under board flex, and shorted it holds Q101 on with the key off |
| `C107`, gate → source | 4.7 µF **X7R, 50 V**, 1206 | divides down the dV/dt that `C105` couples into the gate when the XT90-S is mated with the key OFF: 84 V × 68 n / (68 n + 4.7 µ) ≈ 1.2 V, under V<sub>GS(th)</sub>, so the FET stays off. The margin is thin at the corners — 1.64–1.98 V against the 2.0 V minimum threshold, across tolerance, temperature and OVP — so the part must keep its value under bias and cold: X7R, where a Y5V or 25 V part loses most of it |
| `R101`, gate → pull-down switch | **540 kΩ — 2 × 270 kΩ in series** | the turn-on current, and with `R110` the on-state V<sub>GS</sub>; two parts share the voltage |
| `Q105`, the pull-down switch | **`BSS127`** — 600 V **enhancement-mode** N-FET, SOT-23, V<sub>GS(th)</sub> 1.4–2.6 V | the only path that turns Q101 on. ⛔ **Not `BSS126`**, its depletion-mode sibling, which conducts at V<sub>GS</sub> = 0 and would hold the module on with the key off |
| `Q105`'s gate drive | key-switch output → 2 × 499 kΩ → gate → 100 kΩ to ground, with a 10 V zener (`BZT52B10`, B grade) and 100 nF at the gate | 84 V → 7.6 V · 60 V → 5.5 V · 43 V → 3.9 V, all above the `BSS127`'s threshold. Key off → 0 V → Q105 off → Q101 off, with zero quiescent drain |

This gives V<sub>GS</sub>(Q101) = −13.1 V at 84 V and −9.4 V at the 60 V LVC, and a simulated ramp of
≈ 51 ms at 84 V with a mid-threshold FET — 47–61 ms across the part's V<sub>GS(th)</sub> spread, 52–78 ms
at 60 V (`python3 tools/soft_start.py`, which reads the network off the netlist). Mating the XT90-S with
the key off lifts V<sub>GS</sub> to 1.2 V, under the 2.0 V minimum threshold. ⬜ All of it is computed,
not measured: scope the switched node and the B+ tap at the first key-on, and again while mating the
XT90-S with the key off — a plug-in that rings the tap up to the `SMCJ90A`'s clamp is the case to look
for.

⚠️ **Key-off is not instant, and it is now the case that binds `Q101`.** With the key off `Q105`
opens and `C107` discharges through `R110` alone, so Q101 stays on for **~0.8 s** before it pinches
off, carrying the load across the whole pack while it does. IN-12 taps the key-switch output itself,
so firmware sees key-off at once, whatever Q101 is doing; D9's *"nothing is live with the key off"*
holds from about a second after the key opens, and the zero-quiescent-drain property is untouched.

⛔ **HARDWARE CONTRACT — the key-off aux shed (D27/IO-16, 2026-09-20).** On `KEY_SENSE` going
inactive the firmware **releases all eight aux outputs**, well inside `Q101`'s **~774 ms** hold.
**`Q101`'s SOA margin depends on that firmware behaviour**, and this is the only place in the design
where it is so — ⛔ do not write it as a feature:

| The decay carries | Bound | Against the derated DC line (138 W) |
|---|---|---|
| **shed** — the base load and the buck's standing draw, 0.63 A at the tap | **~53 W** at 84 V, 38 W at 60 V | ✅ **×2.6** (×3.6 at 60 V) |
| **not shed** — all eight held on, 1.93 A at the tap | **162 W**; integrating the decay gives 147 W over 21.3 J, a 145 ms equal-energy pulse, past the SOA table's 100 ms row | ⛔ **over it** |

- ✅ **A watchdog reset, or any restart, sheds the load by itself:** expander #3's pins come out of
  reset as inputs, the `TPS4H160B` `INx` pull-downs are internal, and the `TPS2553` enables are
  pulled to GND (D14). **The exposure is narrowly a hang that holds the outputs on and does not trip
  the watchdog**, through the whole decay.
- ⚠️ The 53 W is itself a **bound** — 0.63 A across the whole pack. The converters are constant power,
  so the real figure is ~36 W if they quit at their 43 V input floor; ⬜ TDK publishes no
  under-voltage shutdown for the CN-B110, so that floor is an assumption, and a brick still
  converting below it draws **more**, not less. ⬜ **M17** scopes a deliberate key-off under load.
- `tools/soft_start.py` derives its load from `tools/power_budget.py`, **gates on the shed case**,
  and prints the un-shed bound beside it as the residual risk. Run it; do not copy these numbers.

⚠️ **Firmware must flag "powered with KEY_SENSE low for > 2 s"** and drop to minimum load. A
failed-short `Q105` or `C105` leaves the module live with the key off, and nothing else notices.

**The tap fuse is `KLKD003`, 3 A FAST-blow** (600 VDC, 50 kA DC) in an inline holder (§9.5.2) —
**1.55×** the 1.93 A LVC draw, 64 % of the fuse. Sitting upstream in series, it also satisfies
**TDK's fast-blow mandate for DC-DC #1**, so the module has two series fuses, not three (this tap +
the 1 A time-delay on DC-DC #2). ⚠️ **Deviation to log:** TDK wants the fuse on its own +Vin leg;
upstream-in-series still protects it, recorded as a deliberate choice.

Residual risks — documented, not designed out:
- A MOSFET failing **open** leaves the module dead — the same outcome as a blown fuse, inconvenient,
  not dangerous.
- **A short downstream of Q101 at key-on can destroy Q101:** it ramps through its linear region while
  the harness fuse needs amps to open. The KEY_SENSE check above detects the stuck-on switch that
  results.
- **`Q105` has no hysteresis:** a `KSW` parked mid-range (~15–28 V) could hold Q101 partly on. A
  narrow window.
- At key-on `KSW` is live ~150–350 ms before the 3.3 V rail, and the IN-12 divider back-feeds GPIO1's
  clamp at ≤ 0.19 mA, behind its 1 kΩ series resistor (§4) — harmless.

⚠️ **The MOSFET is selected on SOA, not Vds/Id.** The soft-start moves the inrush energy out of the
key-switch contacts and **into the MOSFET**, which absorbs it. **`tools/soft_start.py` owns every
figure below**: it reads the gate network off the netlist, takes its load from
`tools/power_budget.py`, and simulates both directions across the FET's threshold spread.
- **Capacitance downstream of D13: 440 µF** — both `EKXJ221ELL221MM25S` caps (C1 and C2, BOM E8) —
  with the **1.93 A** LVC tap on it as well (§3.2.3). ½CV² at 84 V is 1.55 J; Q101 absorbs that plus
  the load's share, **7.0–10.0 J** over the ramp.
- **Key-on, simulated at 84 V:** a **45.7–59.8 ms** ramp peaking at **184–198 W**, against an SOA of
  **214–239 W** read at the equal-energy pulse width. ✅ Every corner clears, at 84 V and at 60 V.
- ⚠️ **The peak is above the DC line.** The derated 70 °C DC line is
  **138 W**, and the load alone puts 1.93 A × 84 V = **162 W** on the part at the instant
  V<sub>DS</sub> is still full. **The part choice rests on the ramp being a pulse** — Fig. 14's line
  at the equal-energy pulse width, not the DC line. ⛔ Nothing may lengthen the key-off decay or
  raise the tap current without re-running the tool.

✅ **Selected: IXYS `IXTA26P20P`** (TO-263 / D2PAK), placed by JLC with its tab — the drain —
soldered to 84 V copper. The `IXTP26P20P` (TO-220, BOM E13) is the same die on the same datasheet,
and only a hand-solder fallback. That datasheet, **DS99913D**, draws forward-bias SOA at both
T<sub>C</sub> = 25 °C and **70 °C**, each with 25 µs, 100 µs, 1 ms, **10 ms, 100 ms and DC** lines, and
guarantees 160 W at −200 V / 5 s / 70 °C. Read off the 70 °C plot at 84 V (±10 %): **≈460 W on the
10 ms line · ≈254 W on the 100 ms line · ≈191 W DC.** `soft_start` derates Fig. 14 by **0.72** for a
60 °C ambient against T<sub>Jmax</sub> 150 °C and quotes the derated line throughout, which is why
the DC figure it gates the key-off decay against is 138 W.
⚠️ **Use DS99913D.** The 2007 "Preliminary" sheet some distributors still serve states a different
T<sub>JM</sub> and draws constant-power lines that stop at 80–100 V.
`IRF9640PbF` is an alternate, checked only on its 10 ms line (~335 W at 84 V, ~241 W derated for
60 °C). Not `FQP12P20` — it publishes no SOA plot at all.

⭐ **The ramp time still buys margin, but far less of it than it did.** Even at 10 ms the input
dv/dt is **0.0084 V/µs, 1190× inside TDK's ≤10 V/µs limit**, so nothing pushes the ramp down; and a
slower ramp helps the diode too. What changed is the floor: **the 1.93 A load is 162 W of the peak
whatever the ramp does**, so only the 440 µF's charging current — 0.74 A at 50 ms — is still on the
table. `soft_start`'s `R_PD FOR A TARGET RAMP` block solves the pull-down for a wanted ramp.

✅ **The D13 gate ramp is ~50 ms (owner, 2026-09-18)**, an imperceptible key-on delay. It matters most
in the high-V<sub>DS</sub> / low-I<sub>D</sub> **Spirito (thermal-instability) corner**, where the
limit is local current density, so less current at high V<sub>DS</sub> is strictly better.

⚠️ **Why headline ratings cannot substitute for the curve:** SOA has five limits — R<sub>DS(on)</sub>,
current, maximum power, **thermal instability**, BV<sub>DSS</sub> — and Vds/Id cover two. Two 100 V
parts with near-identical R<sub>DS(on)</sub> and I<sub>D</sub> can differ 4× in SOA at 50 V / 10 ms. The
Spirito inflexion moves to *lower* V<sub>DS</sub> as the pulse lengthens, so a short-pulse curve cannot
be scaled to a long one — a line at or beyond the real pulse length must be published. Where a plot is
drawn only at T<sub>C</sub> = 25 °C, derate it for T<sub>Jmax</sub> 150 °C and a 60 °C ambient by
(150−60)/(150−25) = **0.72**; DS99913D's 70 °C plot needs none. ⛔ **No SOT-23 part as the main
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
- **The secondary kill is the run/off toggle**, read on IN-11 and acted on by the firmware, which
  asserts `BL` when it opens (D23). It stops drive; it does not remove KEY, and it does nothing with
  the firmware stopped.
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

**(b) DC-DC #1's input draws 1.35 A at 84 V, 1.88 A at the LVC** (§3.2.3), and the whole tap 1.93 A.
A **3 A fast-blow** gives **1.55×** — 64 % of the link against a 75 % continuous-duty derate, still
above the steady draw once the soft-start has bounded inrush, and tight enough to protect the wiring.
TDK's "10 A or lower" is a ceiling, not a target. The `KLKD003` at the tap provides it (§3.2.5).
⛔ **Size at the LVC, never at full charge**, and ⛔ never at the eight limiters' 2.58 A — that is
eight simultaneous faults, and opening on it is the fuse working (§3.2.3).

**(c) The 12 V converter's input choke is a ≥ 3 A part.** `L101` is the Würth **`7448023005`**
(5 mH, **3 A at 70 °C**, 300 V AC) — 1.88 A is 63 % of it, against an 80 % derate that allows for the
choke sitting in a sealed box with the brick, not in 70 °C air. ⚠️ It is half the inductance of the
2 A `7448022010` on `L102`; TDK states no inductance figure, so neither value is tested for
interference. `L102`, the Cincon's, is the 2 A part — the logic rail draws 0.05 A at the LVC.

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
  risk is low). The telltale feeds (pins 1/4/5) are live 12 V lamp feeds (§6.2.1); their 1 kΩ series
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

- **Class A — dry contact to module ground** (the bar switch sets, the red button, the brake levers
  and the 13 free inputs): GPIO input, **1 kΩ** pull-up to
  3.3V, 1k series into the pin, 100 nF to ground at the pin, a TVS/ESD array on any wire that leaves
  the box — the 5 V `SMS05T1G` (BOM C2), which is correct on **every** one of them, the levers
  included: a lever wire is a 3.3 V node now (§6.2.4). **Every class-A network sits complete on the
  board its terminal is on**, so no input crosses an interface as an unconditioned wire
  (τ = 100 µs, well inside the levers' <10 ms budget). Firmware debounce 20 ms (≤10 ms for
  flash-to-pass, §7).
  ⚠️ **Wetting current sets the pull-up.** 4.7 kΩ to 3.3 V puts only **0.70 mA** through the contacts —
  fine for gold-plated domes, marginal for a cheap automotive switch: tin and silver contacts commonly
  specify a **1–10 mA minimum**, below which oxide and sulfide films make contact resistance erratic,
  and these switches live on a handlebar in the weather. **Use 1 kΩ → 3.3 mA on every channel driven by
  a bought switch** (11 mW; the RC with 100 nF stays ~100 µs). Firmware debounce does not help:
  intermittent contact resistance reads as a non-press, not as chatter.
  All bar controls are class A (D20). Gesture decoding (short/long press) is needed only on the boost
  button, IN-07.
  **The brake inputs IN-05/06 take the same 1 kΩ pull-up as every other contact** and land directly
  on the S3: no steering diode, no divider, nothing between the lever wire and the pin but its 1 kΩ
  series resistor, so the low level is the contact's own.
- **Class B — 12V or 72V level sense:** resistor divider to < 3.3V (72V: 330k / 10k, the top resistor
  as a series pair of 2 × 165 k for voltage rating) and 100 nF. No separate clamp: the 330 k top
  resistor holds the injected current to microamps even at 146 V. On the custom board IN-12 keeps its
  100 nF at the divider on POWER, crosses PWR-OUT and PWR-LOGIC with a ground on each side
  (§9.2), and meets GPIO1 through **1 kΩ with 100 nF at the pin** — the resistor limits what a fault,
  an ESD event or the divider itself can push into the pin's clamp diodes.
- **Class D — analog:** ADC pin with divider and 100 nF; average in firmware.
- **Class E — FarDriver serial:** direct 3.3V, 1k series on the module's TX, TX pin tri-stated (input
  mode) whenever the module isn't sending; both RX lines are listen-only taps. On the custom board
  the controller-TX tap takes 1 k too, because the FarDriver's TX level is unmeasured (⬜ M9).
  ⚠️ With the module unpowered, the FarDriver's TX can feed ~mA into GPIO18 through that 1 k — M9's
  reading of the TX level sets how much.

## 5. Bench discovery — the measurements this plan depends on

📄 **M2 · M3 · M8 · M9 · M10 have a written bench procedure: `inputs-bench-session.md`** —
unpowered sittings (sitting B is the brake levers, M3) and a 72 V bench-supply sitting. The procedure
carries four traps: **the ohmmeter cannot see through an LED assembly**, **colour is never evidence on
this bike**, **a floating reference lies**, and **"it fits so it must be right"**. ⚠️ **M3 gates
`J306`**, the lever terminal.

| # | Measure | How | Result |
|---|---|---|---|
| M1 | **The new switch sets (D20)**, unplugged: each switch's contact pair, momentary or latching, and ⚠️ **how the 3-position slider is wired** (OFF/A/B or OFF/A/A+B — the D21 decode depends on it). Bench session A2 | ohmmeter, new parts on the bench | ⬜ on arrival |
| M2 | Handlebar loom ("1T3 10"): which wires are the **brake-lever wires** — the only wires in that loom the build re-uses | ohmmeter unplugged | ⬜ |
| M3 | **Brake levers, unpowered:** wire count per lever; NO/NC by ohmmeter, released vs squeezed; one pair per lever or shared. **Gates `J306`**, the lever terminal — a three-wire Hall lever adds a supply pin and changes its size (§9.2) | ohmmeter unplugged (bench session sitting B) | ⬜ |
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
| M17 | **Transients on the 84 V node.** MSO5074 on the module's B+ tap, referenced to controller B−. Capture (i) hard acceleration at the 80 A cap, (ii) **a deliberate key-off under load** — the case `Q101`'s SOA turns on (§3.2.5) — (iii) XT90-S mate/unmate with the key OFF. Record worst peak voltage, current into the clamp, duration, and the decay's shape. Expectation (§3.2.1): nothing near the `SMCJ90A`'s rated 10.3 A (~7.4 A at 60 °C) at its 146 V clamp. Does not block ordering | MSO5074 + current probe | ⬜ |
| M18 | **The enclosure cavity** — the old-controller cavity under the battery compartment, where the three-board stack lives (§9.2). Usable length; width **at the narrowest point along the run**; clear height **along the whole run**, floor to the underside of the battery tray; what the floor is made of and whether it sees moving air; where cables can exit; any intrusion partway along. Working estimate: **200 × 50 × 70 mm.** ⚠️ **The design requires 233.0 × 74.65 × 68.4 mm** (§9.2) — 33.0 mm longer and 24.7 mm wider than that estimate. M18 confirms the requirement or forces a rethink; it no longer sizes the boards | tape + calipers | ⬜ |
| M19 | **Part heights that set each gap in the stack** (§9.2) — **the inter-board connector family first: its mated pairs sit in three of the four gaps and, once chosen, set them**; then every part not yet read from a manufacturer drawing. Read so far: CM chokes `7448023005` and `7448022010` **22.0 mm** tall (18.0 × 14.0 mm footprint); `IXTA26P20P` 4.83 mm (TO-263); the Y2 discs upright 15.5–16.5 mm, so they lie **flat** (5.0 mm); the harness headers **7.00 mm** (Kefa 3.50 mm), **7.25 mm** (Kangnex 3.81 mm), **8.30 mm** (Kangnex 5.08 mm) and **8.60 mm** (Kefa 7.62 mm) tall; the Schurter `FAC 0031.3803` holder is a **47.5 mm vertical** part and cannot go in the stack (§9.5.2) | datasheets + calipers | ◐ |

## 6. Outputs

| Output | Load | Driver | Notes |
|---|---|---|---|
| Headlight **LOW** (blue) | 12 V / 8.5 W = **0.71 A** | **high-side** smart switch (D15), default-OFF | M4. Lamp is common-ground (black), so low-side is impossible |
| Headlight **DRL / running** (yellow) | 12 V / 6.5 W = **0.54 A** | high-side, default-OFF | M4 |
| Headlight **HIGH** (green) | 12 V / 8.5 W = **0.71 A** | high-side, default-OFF | From IN-04 / IN-09. **HIGH replaces LOW** (D14), enforced in firmware |
| Tail **running** (yellow) | 0.05 A, 5-wire assembly, common = black | high-side, default-OFF | M5 |
| Tail **STOP / brake** (red) | 0.12 A, separate feed | **high-side, firmware-driven** — an ordinary `TPS4H160B` channel on a native pin, asserted from the lever interrupt (D23, §6.2.2a) | M5. The channel adds a current limit, lamp-out detection and `FAULT`. ⚠️ Off whenever the firmware is not running |
| Turn **LEFT** (front + rear) | rear = **blue** in the tail plug; front = its own 2-wire pair | high-side (rear shares the tail common) | M6. 85 flashes/min — no relay (§6.1). ⬜ Confirm the front pair's return can sit on the same common before paralleling |
| Turn **RIGHT** (front + rear) | rear = **green**; front = own pair | high-side | M6 |
| Horn | electronic, 12 V / 0.10 A | **low-side** N-MOSFET on a native pin, `+` fed from `AUX12` (its own pair: blue `+`, black `−`); TVS on the wire leaving the box, **no flyback needed** | M7. **D12 = MOSFET** |
| **Motor cut (`BL`)** | the FarDriver `BL` wire, on its own controller pull-up | **open-drain** N-MOSFET on a native pin, 100 Ω series, hard 10 kΩ gate pull-down | **D23.** Released whenever the firmware is not running (§7) |
| **4 × 12 V aux** | 1 A each | high-side, a third `TPS4H160B`, default-OFF | **D27/IO-1.** Identical in hardware to the lamp channels — "aux" is only their use |
| **4 × 5 V aux** | 1 A each | `TPS2553` current-limited load switches off their own 12 → 5 V buck | **D27/IO-1.** Fault flag per channel; enables pulled down, so off at boot |
| Dash telltales L / R / headlight | Chaojie pins 1 / 4 / 5, **0–15 V inputs** | **from the corresponding lamp feed through 1 kΩ** — not a driver channel (§6.2.1) | costs zero channels; mirrors the feed actually energised |
| **Boost to controller** | FarDriver boost input (an unused pull-down input re-assigned to `BoostPin`, §7.1) | open-drain N-MOSFET (100 Ω series) or PC817 opto; **off = no boost** by default | **D4: through the module** |
| **CAN to the Chaojie** | display pins 8 (H) / 7 (L) | ESP32 TWAI + `SN65HVD230`, 120 Ω | ⏸️ **Deferred (D19).** Build the hardware anyway — transceiver in hand, 2 GPIO, and a replacement panel is likelier to need CAN than not. Transmit in `TWAI_MODE_NO_ACK` |
| Buzzer | small 12V buzzer | low-side MOSFET, LEDC PWM | boost chirps (§7), turn-signal click (§6.1) |
| **Display power (pin 2)** | Chaojie supply | high-side switch, **default-ON**, soft-started | **§3.3.** ⏸️ D11 parked. ⚠️ Never switch pin 3 / B− |
| **Cooling fan** | 12V fan on the controller heatsink | low-side MOSFET, PWM | thermostatic from the MOS/motor temps the module already reads — this is what makes an enclosed controller bay viable (checklist Phase 3) |

Power for all of this is **§3.2** (12 V for the loads — **8.47 A / 101.7 W** nominal — and 5 V
for the logic).

⚠️ **Gate bias — one rule: every output biases OFF.** The `TPS4H160B`'s internal input pulldowns (D15)
deliver this by device design, and the `TPS2553` enables and the `BL` gate have hard pull-downs.
**The display power switch (§3.3) is the sole default-ON output.** `AUX12` is an ordinary channel
too: the horn, fan and buzzer have no `+` until the firmware asks for it.
There is **no hardware fail-safe** keeping any lamp alive through a firmware hang (D14).
**The ≤300 ms watchdog (§7) and reading the lighting slider at boot are the only mitigation** for the
lighting, **and the brake lamp is inside that risk now, not outside it** (D23, §7).

### 6.0 ⚠️ The lamps are COMMON-GROUND — lighting needs HIGH-SIDE switching

The headlight is **BLACK = common ground · GREEN = HIGH · BLUE = LOW · YELLOW = DRL**, and the tail is
also common (black). All functions share one ground wire, so **the only way to control them
independently is to switch each feed between +12 V and the lamp — high-side.** **All seven lamp
channels are high-side**: headlight LOW / HIGH / DRL, tail running, turn L, turn R and the STOP lamp,
and so are `AUX12` and the four 12 V aux outputs. The **horn** (its own `+`/`−` pair), fan and buzzer
are switched low-side under their `AUX12` feed, and the telltales are fed from the lamp feeds.
**The driver board (block D, OUTPUTS) is a high-side board** with a few low-side channels.

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
| **Tail running · STOP** | MOSFET (smart high-side, D15) | plain feeds (M5); the STOP channel is firmware-driven like the rest (D23) |
| **Headlight LOW / HIGH / DRL** | MOSFET (smart high-side, D15) | modest currents, per-channel current limit |
| **Horn** | MOSFET (**D12**) | electronic 0.10 A horn — no coil, no inductive kick |
| Fan · buzzer | MOSFET | PWM |

The one place a relay-class part could earn its keep is the **display supply on pack voltage** (§3.3,
D11 parked) — and there the better answer is a **photovoltaic-coupled MOSFET SSR**: arc-free on a DC
rail no small signal relay is rated to break.

### 6.2 Driver circuits

#### 6.2.1 Channel inventory — 12 high-side 12 V, 4 × 5 V aux, 3 low-side, 2 open-drain, 1 special

| # | Channel | Side | Current | Default |
|---|---|---|---|---|
| 1 | Headlight **LOW** (blue) | HIGH | 0.71 A | OFF |
| 2 | Headlight **HIGH** (green) | HIGH | 0.71 A | OFF · *exclusive with #1* |
| 3 | Headlight **DRL** (yellow) | HIGH | 0.54 A | OFF |
| 4 | Tail **running** (yellow) | HIGH | 0.05 A | OFF |
| 5 | Tail **STOP** (red) | HIGH | 0.12 A | OFF — **firmware follows the levers** (D23) |
| 6 | Turn **LEFT** (rear blue ∥ front pair) | HIGH | 0.10 A | OFF |
| 7 | Turn **RIGHT** (rear green ∥ front pair) | HIGH | 0.10 A | OFF |
| 8 | Horn (own `+`/`−` pair) | low | 0.10 A | OFF |
| 9 | Cooling fan (**PWM**) | low | ~0.5 A ⬜ | OFF |
| 10 | Buzzer (**PWM**) | low | small | OFF |
| A | **`AUX12`** — the `+` feed for #8–#10 | HIGH | their sum | OFF. An ordinary channel on expander #3 that the REVV1 preset turns on at its first tick; each load it feeds biases OFF as well |
| 11–14 | **12 V aux 1–4** | HIGH | 1 A each | OFF |
| 15–18 | **5 V aux 1–4** | HIGH, `TPS2553` | 1 A each | OFF (enable pulled down) |
| S1 | **Boost to controller** | open-drain | — | **OFF (hard pull-down)** |
| S2 | **`BL` — the motor cut** | open-drain | — | **RELEASED (hard pull-down)** — the bike drives (D23) |
| S3 | **Display power** (§3.3) | HIGH, soft-start | ⬜ M14 | ⚠️ **ON — the only one** |

**Nominal simultaneous 8.47 A** (§3.2.3). **No lamp channel exceeds 0.71 A**; each aux channel is
1 A nominal and its limiter passes at most 1.55 A (12 V) or 1.39 A (5 V).

⚠️ **The dash telltales are not driver channels — drive them from the lamp feeds they mirror.** Chaojie
pins 1 / 4 / 5 are **0–15 V inputs**: a telltale lights when the lamp voltage is *applied* to it.
A low-side FET pulling such a pin to ground does nothing, and making them high-side would need three
more channels — all twelve that three `TPS4H160B` packages provide are in use (§6.2.2a).

| Telltale | Fed from | Via |
|---|---|---|
| Turn L | channel 6 (turn LEFT feed) | 1 kΩ series resistor, 1206 |
| Turn R | channel 7 (turn RIGHT feed) | 1 kΩ series resistor, 1206 |
| Headlight | channel 2 (HIGH feed) **only** — a flash lights it; LOW beam does not | 1 kΩ series resistor, 1206 |

Zero extra channels, and the telltale reflects **the feed actually energised** rather than firmware's
belief about it. ⚠️ **The series resistor is required** (as for pin 9, §3.3): during a display
power-cycle these feeds may be live into an unpowered input's ESD clamp. It is a 1206 because a
display wire shorted to ground puts the whole 12 V feed across it: 144 mW.

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
28-HTSSOP (DigiKey `296-44711-1-ND`). **Three packages = 12 channels, all used and all
firmware-driven:** `U301` — `AUX12`, headlight LOW / HIGH / DRL · `U302` — tail running, turn L,
turn R, **the STOP lamp** · `U303` — the **four 12 V aux outputs** (D27/IO-1).

**It clears both hard gates by device design — no level shifter, no external pulldown:**
- ✅ **3.3 V drive, no level shifter.** V<sub>IH</sub> min **2 V** / V<sub>IL</sub> max 0.8 V across
  −40…+150 °C. TI recommends a **4.7 kΩ series protection resistor** on every logic line from a 3.3 V
  MCU — fitted on every `INx` and on `DIAG_EN`, `SEL`, `SEH`, `FAULT1` and `FAULT2`; through it the
  divider still delivers 3.15 V.
- ✅ **Floating input = output OFF.** Every `INx` has a specified **100/175/250 kΩ internal pulldown**,
  so the S3's ~200 ms high-Z boot window is safe **by device design** — D14's requirement.

⚠️ **Current limit and current sense DO need external parts — `CL` and `CS` each take a resistor:**
- **`CL` sets the per-channel current limit:** R<sub>CL</sub> = 0.8 V × 2500 / I<sub>limit</sub>, to
  ground. **1.00 kΩ → ≈2 A** on `U301` (the 0.71 A and 0.54 A headlight loads); **2.0 kΩ → ≈1 A**
  on `U302` (the 0.05–0.12 A tail, turn and STOP loads); **1.5 kΩ → 1.12–1.55 A** on `U303`, the
  1 A aux channels (1.5 kΩ is JLC Basic where 1.6 kΩ is not, and it never dips under the 1.06 A
  floor). With `CL` strapped to ground the part falls back
  to its internal **8–14 A** limit — on a 12.5 A converter that is no per-channel limit at all, and
  D15's fault containment is gone.
- **`CS` is a current SOURCE (I<sub>OUT</sub> / 300), not a voltage:** **1.00 kΩ 1 %** to ground turns
  it into a voltage. In any fault — an unplugged lamp included — the pin drives **4.5–6.5 V**, so it
  reaches the S3 only through a **10 kΩ / 10 kΩ divider** with 100 nF at the ADC side: a fault reads
  2.25–3.25 V — above any real load, below VDD. The divider loads the node, so it is 1.00 kΩ ∥ 20 kΩ =
  952 Ω: **3.17 V/A at the node, 1.59 V/A at the pin** (0.71 A reads 1.13 V). ⚠️ TI's "10 kΩ series"
  advice is written for a 5 V MCU; on its own it leaves ~3.8 V on a 3.3 V pin.
- ⚠️ **Firmware reads `U302`'s open-load at `ATTEN0`.** The 0.05 A tail lamp is **79 mV** at the
  pin: inside `ATTEN3`'s ±50 mV total error, readable at `ATTEN0` (0–850 mV, ±5 mV; ESP32-S3
  datasheet v2.2, Table 5-6).
- ⭐ **The third package needs no new ADC pin.** SLVSCV8E Table 7-1: with `DIAG_EN` low a
  `TPS4H160B`'s `CS` and `FAULT` pins go high-impedance while its current limit stays active
  (*"Diagnostics disabled, full protection"*). `U303` therefore shares **`CS2`** and **`FAULT2`**
  with `U302` through its own `DIAG_EN`, and firmware holds the other device's `DIAG_EN` low while it
  reads one.
- **TI's pin names are `VS` (supply), `SEL` and `SEH` (sense-channel select, low and high bit)** — not
  VBAT / SEL1 / SEL2. Decouple each `VS` with 100 nF + 10 µF / 50 V. `THER` tied to ground selects auto-retry
  after a thermal shutdown. Unused `INx` tie to ground, and each unused `OUTx` takes 10 kΩ to ground so
  an idle channel is not reported as an open load on the shared `FAULT` line.

⚠️ **Diagnostics cost firmware.**
- **OFF-state open-load needs an external 20 kΩ pullup from each `OUTx` to `VS` — 11 resistors,** one
  per lamp channel, the STOP lamp's included, and one per 12 V aux channel; `AUX12` has none.
- **ON-state open-load is not reported on `FAULT`/`STx`.** The MCU must multiplex `SEL`/`SEH` and
  **ADC the current-sense pin**, and only **Version B** can do it. ⚠️ The divider and its 100 nF
  settle in τ ≈ 0.55 ms — firmware waits **≥ 3 ms** after moving `SEL`/`SEH`, not TI's 50 µs.
- `FAULT` is open-drain: a **10 kΩ pull-up to 3.3 V at each device** (TI's R<sub>pu</sub>) and a
  **4.7 kΩ series resistor** on to the MCU, TI's recommendation. The pull-up sits on the device side,
  so the series resistor carries no DC and a fault still reads ~0 V at the pin.
- ⚠️ The HTSSOP thermal pad must reach real copper or the current limiting and thermal shutdown will not
  behave as specified (BOM D1).

⚠️ **Domain constraint: 40 V-class part — ONLY on the regulated 12 V rail. Never the 84 V pack node.**
40 V recommended / 48 V transient abs-max against an 84 V node with a 90.7 V OVP = permanent damage. So
the §3.3 display switch can use it only on a 12 V feed (D11).

⬜ **Board decision: omit the reverse-battery GND-network diode.** With it fitted the required drive
rises to V<sub>IH</sub> + V<sub>F</sub> ≈ **2.7 V**, while an ESP32-S3 guarantees only ~2.64 V V<sub>OH</sub>
under load. Omitting it is defensible because these switches sit on a regulated DC-DC output, not a
reversible battery.

**Every channel is firmware's** (D23) — there is no hardware-driven input on any of the three
packages. Two are worth naming:
- **`U301` `OUT1` is `AUX12`**, the `+` feed for horn, fan and buzzer, commanded on expander #3's
  GPA5 through a 4.7 kΩ. It is an ordinary output that the REVV1 preset keeps on, so the horn, fan
  and buzzer have no `+` until the first firmware tick; each is also switched low-side with its gate
  biased OFF (D14). **No raw 12 V leaves the box:** a horn, fan or buzzer wire chafed to ground meets
  the channel's 2 A limit, not the brick's 12.75–18.75 A.
- **`U302` `OUT4` is the STOP lamp**, on **GPIO19** direct from the S3 (§9.8). The pin has no reset
  pull, and what holds the lamp off through boot is `IN4`'s own 100–250 kΩ internal pull-down; the
  two ~60 µs power-up glitches the S3 datasheet lists can put at most a ~20 µs pulse on the channel,
  below visibility on a 0.12 A lamp. The lamp keeps the channel's 1 A limit, open-load detection and
  `FAULT2`.

**Not Infineon `BTS7008-2EPA`** — the only candidate that detects open load in the ON state (8/21/35 mA
thresholds), but it has **no internal input pulldown** (an external 10 kΩ per channel) and **no lamp-scale
current limit** — its overcurrent trip is ~88 A, ~124× the 0.71 A load, which defeats the reason D15
chose smart switches.
**Not TI `TPS2HB50-Q1`** (resistor-programmed per-channel limit, 1.325 A min trip at R<sub>ILIM</sub> =
25 kΩ) — ~1.9× the load may be too thin for LED-driver inrush, which has never been measured.

#### 6.2.2b The aux block — 4 × 12 V, 4 × 5 V, and the expander that commands them

**D27/IO-1.** Eight outputs with no assigned function, for whatever the owner wires to them. The
12 V four are `U303`'s channels, described above. The 5 V four have their own supply:

- **The buck: TI `LM73605`**, V12 → 5 V, 5 A. **42 V absolute maximum in**, which matters because
  `D315` lets a V12 transient through at 29.2 V. The two JLC Basic candidates carry only 3 A and
  2 A, under the 4 A this rail can draw. ⚠️ **It is a second 5 V rail, not the logic's**: the Cincon's isolated
  5 V is on POWER and feeds the S3, so **a shorted aux wire cannot brown out the brain** — which is
  the whole reason the part exists.
- ⚠️ **The 5 V rail is live whenever the 12 V rail is.** The buck's `EN` is tied to its own `PVIN`
  (datasheet-sanctioned), so `V5AUX` comes up with no firmware, and its standing draw sits on the
  12 V budget permanently and cannot be shed (§3.2.3). The four switches still hold every wire off.
- **Each output: TI `TPS2553`**, a current-limited load switch limiting at **1.19–1.39 A** with a
  20 kΩ on `ILIM`, with an open-drain fault flag. Its **enable is pulled to GND**, so the channel is
  off at boot and through any window where nothing drives the expander (D14).
- **The clamp is an `SMF6.0A`** at each terminal — 6.0 V standoff clears the buck's 5.17 V maximum
  (§6.2.4). ⚠️ **It does not protect the switch's own output** (D27/IO-12): it clamps at 10.3 V where
  `TPS2553`'s `OUT` is rated 7 V, and no TVS with a high enough standoff clamps lower. Worse while a
  channel is **on**: the switch's reverse-voltage comparator takes 3–7 ms to open, so a surge on an
  enabled wire couples onto `V5AUX` and thus onto the other three switches and the buck's output.
  **Recorded as a residual risk, not checked by a rule** — `VR-CLAMP` reads supply pins, and widening
  it to output pins would fail the design by design. With the channel off, the clamp does hold.

**Expander #3 — `U304`, an `MCP23017` at 0x22 on OUTPUTS**, 14 of 16 bits: four `U303` inputs, that
device's `DIAG_EN`, the four 5 V enables, the four 5 V fault flags, and `AUX12`. GPA7 / GPB7 are
output-only and spare.
- At power-up its bits are **inputs**, and every enable it drives has a pull-down of its own, so
  every aux output starts off.
- ⚠️ **Nothing resets the expander when the S3 restarts:** it keeps driving what it last drove until
  firmware writes it. That is not the key-off exposure — key-off drops the 3.3 V rail with
  everything else — but it is why the firmware writes it all-off at boot.
- ⚠️ **It shares the input expanders' I²C bus**, because no native pin is free for a second. A fault
  that holds the bus stalls input reading until the driver's nine-clock recovery frees it.

#### 6.2.3 Low-side channels

N-MOSFET, source to ground, drain to the load's return, **10k gate pull-down** (default OFF), gate
driven from the S3 through ~100 Ω. Part: **`AO3400A`** — genuinely logic-level (48 mΩ guaranteed max at
V<sub>GS</sub> 2.5 V); SOT-23, 30 V, with open caveats in `bom.md` (D3).
- **Horn**, **buzzer** (LEDC) and **fan** (LEDC) are each a discrete FET on a native pin — GPIO8, 40
  and 39 on the prototype map — because the fan and buzzer need PWM, which only native LEDC pins
  provide. ⚠️ Never put a FET gate on GPIO44 (U0RXD): its boot-time pull-up sits at the FET's
  threshold. On the custom board their `+` side is AUX12, a current-limited channel (§6.2.2a), and
  each flyback diode returns to it.
- **`BL`, the motor cut (S2)**, is the same arrangement on its own native pin: `Q106`, an `AO3400A`,
  open-drain onto the FarDriver's `BL` wire, 100 Ω gate series and a **fitted 10 kΩ gate pull-down**.
  ⚠️ That pull-down is what makes "no firmware, no cut" true (D23, §7) — it is not a default, it is
  the specification. `BL` is read back through a 100 kΩ (`R336`) so firmware can report a stuck or
  missing cut; that resistor is a **readback, not an isolation barrier**.
- ⚠️ **Boost (S1) is on its own dedicated native pin with a hard external pull-down** (§3.1.1).
  ⚠️ Meter the boost wire before connecting a 30 V FET to it — the controller-side pull-up voltage is
  unmeasured, and the same harness carries pink `60VC` at pack voltage (§7.1). The module's
  `SMS15T1G` on the boost output sets the acceptance band: **≤ 15 V** keeps this FET; above that, the
  PC817 opto (`inputs-bench-session.md` C1.5).

#### 6.2.4 Protection on every wire that leaves the box

- **A TVS at the connector, on the same board as the connector, on every line that leaves the box —
  chosen by the line's idle voltage:**
  - **`SMF18A`** single-line clamp (V<sub>RWM</sub> 18 V, V<sub>BR</sub> 20.0–22.1 V, V<sub>C</sub>
    29.2 V) on **every 12 V lamp and load output** — the six lamp feeds, the STOP lamp, `AUX12`, the
    horn, fan and buzzer returns, and each of the **four 12 V aux outputs**. The 18 V grade for the
    same reason as the rail clamp below.
  - **`SMF6.0A`** single-line clamp on each of the **four 5 V aux outputs** — the standoff follows
    the line's idle voltage, and 6.0 V clears the buck's 5.17 V maximum. ⚠️ Its 10.3 V clamp is above
    the `TPS2553`'s 7 V `OUT` rating: a recorded residual risk (§6.2.2b), not a checked constraint.
  - **onsemi `SMS15T1G`** (SC-74 quad, V<sub>RWM</sub> 15 V, V<sub>BR</sub> 16.7–18.5 V; clamps 24.0 V at
    5 A and 29.0 V at 12 A, under the `AO3400A`'s 30 V) on `BL` and `ACC+`, on the boost output (its
    pull-up voltage is unmeasured, §7.1), and on the parked display and one-line lines (not fitted).
  - **onsemi `SMS05T1G`** (the same family sheet and SC-74 pinout; V<sub>RWM</sub> 5 V, V<sub>BR</sub>
    6.0 V min, 9.8 V at 5 A, ~300 pF per line) **only** on lines at 5 V or below — the pod inputs,
    **the brake levers** (a lever wire is a 3.3 V node now that nothing pulls it toward 12 V), `RUN`,
    the boost button, UART and the 13 free inputs. It also sits on CAN at the parked display
    connector, where ~300 pF per
    line is too heavy for the bus. ⛔ A 5 V array on a 12 V line conducts continuously: a dead short
    across the channel it was meant to protect.
- ⚠️ **No raw 12 V leaves the box.** Horn `+`, fan `+` and buzzer `+` ride `AUX12` (§6.2.2a). One
  **`SMBJ18A`** clamps the 12 V rail itself, at the `TPS4H160B`s' `VS` — the 18 V grade, because its
  20.0 V minimum breakdown clears the TDK's 15.0–17.4 V over-voltage window where a 15 V part's 16.7 V
  sits inside it (a converter fault would cook it until it failed short, taking the rail and the brake
  lamp with it). It still clamps at 29.2 V, under the `AO3400A`'s 30 V and the `TPS4H160B`'s 40 V, and
  `tools/rules.py` holds every part on the rail to that 29.2 V.
- **Flyback:** the horn needs none — it is electronic (M7). The fan and the buzzer are inductive, and
  each gets an `SS14`-class Schottky (1 A / 40 V) across its load connector, returning to `AUX12`.
- **Transients** are bounded by that `SMBJ18A` on the rail and by each output's `SMF18A` on its wire.
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
- **The brake light** lights whenever a lever is pulled, the module's 12 V rail is up **and the
  firmware is running** (D23).
- **Turn signals and hazard** follow their own inputs **always**.

**Restore-on-boot: read the slider.** At boot the module reads the switch position and re-asserts
lighting **within the first few milliseconds — before WiFi, before anything else.** No NVS write path,
no stale value, no disagreement between firmware and where the rider set the control. NVS is still used
for the **boost mode** (D4), which has no physical position.

⚠️ **What this does not fix:** a **hung** module drives no lamps whatever the slider says. The accepted
D14 risk — a firmware hang at night means darkness — stands, **and since D23 the brake light is
inside it.** **The watchdog is a safety figure: ≤300 ms** (below), and ⬜ the real reset-to-lamp-on
time must be measured.

### ⚠️ The brake cut, the brake lamp and the run/off kill are FIRMWARE (D23)

The levers are plain inputs, `BL` is an open-drain output and the STOP lamp is an ordinary
`TPS4H160B` channel. **State it exactly, because the failure directions are not symmetrical:**

| With the firmware… | The motor cut (`BL`) | The brake lamp |
|---|---|---|
| running | asserted from the **lever interrupt**, not the 10 ms tick | on with it |
| hung, restarting after a watchdog, rebooting after OTA | **released — the bike drives** | **off** |
| never flashed, or the module dead or absent | **released** | **off** |
| powered but its 12 V rail down | released | off (the lamp rides that rail) |

- **Released is the owner's choice** (D27/IO-9): *the bike always drives*. `Q106`'s gate is held down
  by a fitted 10 kΩ and nothing else is in the path, so this is a property of the copper, not of a
  default value somewhere.
- **The accepted consequence, recorded:** a hang or restart while braking loses the cut and the lamp
  for up to **~0.8 s** (a ≤300 ms watchdog plus ~0.5 s of restart), and a dead or unflashed module
  loses them entirely, **with nothing to warn the rider.**
- **A lever cuts the motor and lights the lamp as a fixed guarantee**, not a rule the configuration
  UI can unbind.
- **The run/off toggle is the same mechanism:** the firmware reads IN-11 and asserts `BL` when it
  opens. It does nothing with the firmware stopped.
- ⛔ **The one hardware kill is the key switch** (D24, D10). It feeds the FarDriver KEY wire directly
  and the module never sources or switches it, so turning the key off stops the motor whatever the
  firmware is doing.
- ⚠️ **Residual: `R336`, the `BL` readback resistor** — 100 kΩ from `BL` to a sense node that an
  unpowered or output-driven LOGIC board holds near 0.5 V. It is the one copper path that could pull
  the cut toward "cut" with no firmware running, and it bites only if the FarDriver's own `BL`
  pull-up is 47 kΩ or weaker, which is ⬜ unmeasured.
- ⚠️ **A broken normally-open lever wire reads as "not braking"** and nothing can detect it.
- There is no hard-brake flash: the lamp is on whenever a lever is pulled.

- **Brake inputs (IN-05/06):** on an interrupt — they drive the cut and the lamp (above), clear boost
  (below) and feed the WiFi page.
- **Boost (IN-07) — module in the middle (D4).** Two rider-selectable modes:
  - **HOLD:** boost output asserted while the button is held (release = off within 50 ms).
  - **TOGGLE:** short press = on, short press = off. Safety clears: any brake input, key-off, a
    configurable timeout (default 60 s), and a watchdog/brown-out reset → off.
  - **Mode switch:** long-press ≥ 1.5 s toggles HOLD ↔ TOGGLE; mode remembered in NVS.
  - **Indication (no screen, D17):** the **buzzer** — a single chirp on boost assert, a double chirp on
    a mode change. The WiFi page shows the mode when parked; a CAN dash could show `BST` (§7.2).
  - Output is **open-drain, default off**, so any module failure = no boost. The FarDriver's own boost
    timer (`BstTime` 45 s, `BstRelease` 90 s in the export) still bounds every assertion.
  - **The button is read over I²C** (expander #1), not on a dedicated pin: accept the bus latency.
    Only the boost *output* needs its own pin (§3.1.1).
- **Startup:** all outputs off until self-test passes, then assert lighting from the slider position.
- ⚠️ **Watchdog: task watchdog ≤ 300 ms, with the lighting re-assert as the first action in
  `app_main`.** A 2 s watchdog plus S3 boot (~200 ms ROM + app init) is **≥2.2 s dark ≈ 37 m at
  60 km/h**; ≤300 ms gives ~0.5 s total. ✔ **Measure the real reset-to-lamp-on time on the bench** and
  record it here.
- **Safety:** the module's firmware **is** the brake-cutoff and brake-light path (D23), so both are
  inside the watchdog's budget; the module still never writes controller parameters, and it still
  never touches KEY (D10, D24).

**Firmware duties the hardware relies on** — each is specified where its hardware is:
- ⛔ **Release every aux output when `KEY_SENSE` goes inactive** — a **hardware contract**, not a
  nicety: `Q101`'s key-off SOA margin depends on it (§3.2.5, D27/IO-16).
- Read `U302`'s current sense at `ATTEN0` for open-load, and wait ≥ 3 ms after moving
  `SEL`/`SEH`; hold one device's `DIAG_EN` low while reading the other's (§6.2.2a).
- Write expander #3 all-off at boot (§6.2.2b).
- Flag "powered with KEY_SENSE low for > 2 s" and drop to minimum load (§3.2.5).
- Alarm when `ACC+` reads low with the key on — the throttle's 5.1 V is not arriving (§9.2).
- Report a `BL` readback that disagrees with the command (§6.2.3).
- Read the boost button over I²C and accept its latency (above).
- Recover a hung I²C bus by clocking SCL; the expanders share one RESET pull-up and no GPIO drives it,
  so a power cycle is the last resort (§9.8.2).

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
   before fitting a 30 V FET** (the harness also carries pink `60VC` at pack voltage). The boost output
   carries an `SMS15T1G` (V<sub>RWM</sub> 15 V, V<sub>BR</sub> 16.7 V min), so **≤ 15 V** keeps the
   `AO3400A`; above that the array would conduct, and the output becomes the PC817 opto (§6).
   ⛔ **Keep `60VC` capped and taped back on its own**, and pull its pin from the plug if possible: it
   runs in the same 30-pin loom as the serial wires, and shorted onto one it burns that line's 1 kΩ
   series resistor.
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
  its own end (**132.4 Ω** measured, M16 step 1; the two in parallel measured 68 Ω). On the custom
  board the transceiver idles in **standby** while the feed is parked — `RS` pulled to 3.3 V
  (`R472`), so it cannot drive the bus, and the slope-control resistor (`R442`) not fitted. To un-park:
  fit `R442`, remove `R472`.
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
| **D6** | Board | **ESP32-S3 DevKitC-1** | **DECIDED 2026-09-07 (§3.1).** Pins (21 native used, 7 spare of a 28-pin clean pool, §3.1.3; a pool of 32 on the custom board, §9.8), 3 UARTs for the two RX taps, two cores to keep bus timing off the WiFi core. Not the H2 (no WiFi); the C6's second TWAI is the only thing given up — on the prototype an `MCP2515`/`TCAN330` on SPI recovers it from the spare pins. The module *variant* is a thermal choice (D18) |
| **D7** | Use a spare latching bar input as **FarDriver gear select** (Low / Mid / High via `LowSpeedPin` PIN2 / `HighSpeedPin` PIN3)? | **(b) no for first ride** — stay `HighOnly`; (a) is cheap to add later | Options: (a) module grounds SDL/SDH through an open-drain MOSFET with `SPModeConfig` set to a 3-speed mode (currently `HighOnly`) · (b) stay `HighOnly`, gear changes in the app · (c) a hardware 3-speed switch. It is a **power limiter, not a ratio**: **Low** = 25% line / 50% phase (**20 A / 100 A**), **Mid** = 50% / 75% (**40 A / 150 A**), `MidSpeed_rpm` 4500, **High** = full 80 A / 200 A. ⚠️ **`LowSpeed_rpm` = 0 is vendor-shipped and ambiguous** (0 rpm cap, or no cap?) — resolve on the bench before enabling. ⚠️ Costs 2 module outputs and competes with boost for PIN2 (§7.1 — boost uses PIN17). Mid ≈ the "everyday 60 A" of §7.1. Its real value is a **persistent** low-power mode (lending the bike, wet roads) — a latching switch fits it |
| ⏸️ **D8** | How to obtain the CAN table the Chaojie parses (§7.2) | ⏸️ **PARKED (D19)** — do not work this row | **Known:** protocol **`CAN` = 18** (Chaojie, 2026-09-10); **`CANBaud` = 0 = 250K** (reseller text — "0-250 kbps" is an enum index, `fardriver-nd72450-reference/tools/heb_decode.py:24`); the panel is a receive-only node, so the module transmits in `TWAI_MODE_NO_ACK` (MEDIUM); the goal is demonstrated on this display model (NRGZ28: motor temp, controller temp, bus current populate; **phase current stays blank**); **M12 is closed** — the map is firmware-internal (§7.2.1). **Missing:** the byte map. Routes when it re-opens: `can18-investigation.md` §8. ⛔ Do not enable CAN on our controller (§7.2) |
| **D9** | What stays live at key-off? | **(a) nothing** — module + 12V rail off the key-switched path | **DECIDED 2026-09-07.** Zero parasitic drain; the §3.2.2 ride-out cap still gives a clean shutdown. **Hazards die with the key** — accepted. The D13 switch releases up to ~0.8 s after the key opens, while its gate capacitor discharges (§3.2.5); nothing is live after that. ⚠️ **The firmware sheds the aux outputs inside that window** and `Q101`'s SOA depends on it (D27/IO-16) |
| **D10** | May the module drive the FarDriver **KEY** line? | **(b) no — sense only via IN-12** | **DECIDED 2026-09-07.** The module never holds the KEY line, so a hung module can neither remove motor power nor switch the bike on. Starting is the key switch alone, feeding KEY directly (**D24**). ⚠️ Unchanged by D23: the firmware may *cut* drive on `BL`, an input to the controller, and a released `BL` is the no-firmware state |
| ⭐ **D24** | **How the bike starts** (§3.2.5a) | **(a) the key switch feeds the FarDriver KEY wire directly** — no start latch, no start gesture | ✅ **DECIDED 2026-09-18 (owner).** The topology is the §3.2.5 diagram: XT90-S out → 2 A fuse → key switch → FarDriver KEY wire, with one tap into the module for the D13 enable and the IN-12 sense. The module never sources or switches KEY (**D10**), so no module state — hung, reflashing, unpowered, absent — can start or stop the controller; a firmware-held KEY would mean a watchdog reset cuts motor power under way. The right pod's start button is a **spare sensed input** (§2.0). The run/off toggle remains the secondary kill, now in firmware (D23) |
| ⏸️ **D11** | Display supply: 12 V or pack voltage, and so which high-side switch? | ⏸️ **PARKED with the display (D19)** | Options: (a) 12 V + a 60 V P-MOSFET off the load rail · (b) pack V + a 150 V P-MOSFET or a photovoltaic MOSFET SSR. The right answer depends on which panel ends up fitted, so **board F leaves the first order** and the dash feeds from switched B+ (work order §3.1) meanwhile. **The gate when it re-opens:** M14 shows the panel boots at 12 V, but its **V field reads pin 2, not the link** — under (a) the dash reads **12 V / 0 %** unless a transmitted voltage overrides the internal ADC. `SpecialFrame` 21 (16 + DATA9 *power* + DATA10 *current %*) sends **no voltage byte**; frames **25 / 24 / 16**, or **31 with ByteOption 2**, do (`pinout-3in-cj-v3-01.md` §4). Under (b), V and battery % stay a direct measurement, truthful through a module hang |
| **D12** | Horn driver | **(a) MOSFET** | **DECIDED 2026-09-08.** M7: an electronic 12 V horn at 0.10 A — no coil, no inductive kick, no flyback diode needed (keep a TVS on the wire leaving the box) |
| **D13** | Inrush into the module's bulk capacitance must not land on the key-switch contacts (§3.2.5) | **(b) key switch gates a soft-started P-MOSFET high-side switch; module on its own fused B+ tap** | **DECIDED 2026-09-07.** Closing a contact onto the module's bulk capacitance at 84 V is tens of amps every key-on; (b) removes it instead of making a contact absorb it. Key switch carries the KEY wire plus **~0.32 mA** of dividers — an ordinary 72 V e-bike key switch, 12–96 V. Tap fuse **3 A fast (`KLKD003`)** — ⛔ **a different fuse from the key branch's, which stays 2 A** (§3.2.5). FET **`IXTA26P20P`**, selected on SOA. **Gate ramp ~50 ms (owner, 2026-09-18):** simulated at **184–198 W** against **214–239 W** at the equal-energy pulse width, which is **above the derated DC line** — the choice rests on the ramp being a pulse (§3.2.5). The gate's pull-down switch is a **`BSS127`** — enhancement-mode; its sibling `BSS126` is depletion-mode, on at V<sub>GS</sub> = 0. ⬜ The work order, checklist and build sheet still need the key tap and the B+ tap drawn in (§3.2.5) |
| **D14** | Lighting defaults | **All lights OFF at key-on · HIGH replaces LOW · no hardware default-ON fail-safe** | **DECIDED 2026-09-08 (owner).** ⚠️ **Accepted risk: a firmware hang at night leaves the bike dark**; mitigation is the ≤300 ms watchdog and reading the slider at boot (§7). Gate bias is uniform default-OFF (§3.1.2). The control mapping is D21; flash-to-pass is IN-09 (§7). ⚠️ **The brake light is inside this risk** since D23 made it firmware |
| **D15** | High-side driver type | **(a) smart high-side switch on every 12 V channel** — TI `TPS4H160BQPWPRQ1` (§6.2.2a): three packages, twelve channels — the six lamps, the STOP lamp, `AUX12` and the four 12 V aux outputs | **DECIDED 2026-09-08**, extended to twelve channels by **D27/IO-1**. Per-channel current limiting stops a shorted lamp wire hiccuping the whole rail and killing the headlight; thermal shutdown and lamp-out detection come with it. 3.3 V input compatible, floating input = OFF |
| **D16** | Which channels are native GPIO, which ride the I2C expander? | **(a) FULL NATIVE on the custom board** — all six lighting channels, their diagnostics, boost, the brake inputs, PWM and analog on S3 pins; the expanders carry inputs only — the bar controls and slow sense lines (§9.8.2). **The DevKit prototype runs (b):** low beam + boost native, the other 5 lighting channels on expander #2 (§3.1.3) | **(a) DECIDED 2026-09-18 (owner)** for the custom board; **(b) DECIDED 2026-09-08 (owner)** for the prototype, where all-native does not fit the DevKit's pins. Putting every lamp and bar switch behind one bus means a single I2C fault at night costs the headlight and signals in one event. (a) takes the bus out of the lighting path entirely; (b) keeps the headlight LOW on a private wire, and boost on its own pin (§7.1), with 7 pins spare. ⚠️ **The STOP lamp and `BL` are native too** (D23, §9.8), and the aux block's twelve slow bits sit on expander #3, off the lighting path |
| **D17** | Status screen on the module | **(c) no screen** | **DECIDED 2026-09-08 (owner).** The Chaojie 3" is the only display; simplifies board A, the housing and the firmware. With D8 parked the dash shows only the one-line fields and the **WiFi page is the primary readout**. ⚠️ **Re-open trigger (D19): if the panel is replaced rather than fixed**, revisit what the module must display itself |
| **D18** | Module variant for the custom PCB (§9.8.3) | **(a) the `-N8` variant (8 MB, no PSRAM, −40…+85 °C): `ESP32-S3-WROOM-1U-N8`**, the external-antenna twin of the prototype's `-1-N8` on the same footprint, because the enclosure is metal (§9.7, §9.8.1) | Same part as the prototype (M13), so firmware, pin availability and thermal envelope carry across unchanged. Keep **(b) `-H4`** (4 MB, −40…+105 °C) in reserve only if a thermal survey of the finished box shows it above ~75 °C — ⬜ confirm two OTA app partitions fit 4 MB first. ⛔ **Never an `R8` / `R16V`** — −40…+65 °C against a 60 °C ambient |
| ⏸️ **D19** | Keep spending time on the Chaojie CAN dash feed? | **(b) PARK it** — finish the rest of the module, re-open the display later | **DECIDED 2026-09-10 (owner):** *"the display we have now will either not work, or take too long to setup … we will come back to the display later, and either figure it out or replace it."* Parking costs almost nothing to hold open (the CAN hardware is in hand and spends 2 GPIO), and every remaining step is display-independent. **Consequences:** ① D8 parked (the vendor thread with Peri stays open passively) · ② the CAN hardware stays fitted · ③ D11 parks and block F leaves the first order · ④ the WiFi page becomes the primary readout — a firmware deliverable · ⑤ the dash keeps its one-line feed (issue #7) · ⑥ D17 gains its re-open trigger. **Cost:** temperatures on the glass are deferred — the rider sees them on a phone, not while riding. Telltales are unaffected (pins 1/4/5 off the lamp feeds) and port to any 0–15 V sense-input dash |
| **D20** | Handlebar pods | **(c) replace BOTH with bought switch sets** — every bar control is a new dry contact | **DECIDED 2026-09-10 (owner):** *"we are going to replace the right pod as well. this will be all of our buttons."* IN-01…IN-04 are plain **class A** dry contacts. The original pods come off whenever the switch sets are wired. **M1** is the unpowered ohm-out of the new sets. The bar controls and the boost button take **12 input bits on expander #1** (§2.0); 1 kΩ pull-ups on every bar input (§4); ⬜ check right-bar space; ⬜ measure bar Ø |
| **D21** | Lighting control | **(b) a 3-position slider + a high/low toggle**, as the bought set provides | **DECIDED 2026-09-10 (owner):** *"for the lighting, there is a high/low toggle, and a 3 position slider."* The slider's positions **are** D14's three states in order, with "low beam implies running" built into the hardware; the state is visible; and at boot the module reads the actual switch, not a remembered value. It improves **recovery**, not **immunity** — a hung module still drives no lamps. Lighting becomes a combinational lookup (§7). ⬜ Ohm the slider out before wiring (OFF/A/B vs OFF/A/A+B) |
| **D22** | Turn-signal control | **A push-push latch whose button self-centres, with auto-cancel** — a fact of the bought left pod, in hand 2026-09-11 | ⭐ **It is a PUSH-PUSH (alternate-action) latch whose BUTTON SELF-CENTRES:** push left → latched left, the button springs back; press again to unlatch. **The latch is electrical and hidden, so the switch has NO visible state** — the dash telltale is the only indicator, and that is what auto-cancel exists to compensate for. ✅ **Auto-cancel: 20 s above 15 km/h, or 60 s regardless.** ⭐ **Implement on EDGES, not levels:** `open→closed` starts · `closed→open` stops · **auto-cancel stops the lamp and marks that latch cycle spent** so the still-closed contact cannot restart it · the next `open→closed` is a fresh signal. ⛔ **A latch state machine is required** — press = on · same side = off · **press opposite = switch sides**, a real firmware case since both sides latch independently. ⚠️ **Auto-cancel depends on speed from the serial link** — degrade to the 60 s timeout alone when speed is unavailable. ✅ Also confirmed on this pod: **horn momentary · hazard latching · high/low 2-position.** ⭐ **The rear headlight-marked momentary is the natural flash-to-pass** — IN-09 |
| ⭐ **D23** | Does the brake light depend on firmware? | **Yes — firmware.** The module has **no dedicated circuits**: the brake cut, the brake lamp and the run/off kill are ordinary I/O like everything else | ✅ **DECIDED 2026-09-19 (owner):** *"Which systems have dedicated circuits like brakes? I'm thinking we get rid of those and just use simple input/output like everything else."* Chosen over moving the circuit into an external brake box and over keeping it on the module. **The design:** the levers are class-A contacts on **native** pins, read on an interrupt (IN-05/06) · `BL` is an **open-drain** output, `Q106` with a fitted 10 kΩ gate pull-down · the STOP lamp is an ordinary `TPS4H160B` channel on GPIO19 · the run/off toggle is a plain contact the firmware treats as a kill slot (IN-11). ⚠️ **With the firmware not running the cut is RELEASED and the lamp is OFF** — the owner's choice, *the bike always drives* (D27/IO-9). **Accepted consequence:** a hang or restart while braking loses both for up to ~0.8 s, and a dead or unflashed module loses them entirely, with nothing to warn the rider. **The one hardware kill is the key switch** (D24, D10). **Consequences:** the steering diodes, Q1, Q2 and their networks are **deleted, not moved** · the lever arrays drop from the 15 V `SMS15T1G` to the 5 V `SMS05T1G` (§6.2.4) · a lever cuts the motor as a **fixed guarantee** the configuration UI cannot unbind · rule `LISTEN` is deleted with the circuit. **Gate:** **M3** still sets `J306`'s size (§5) |
| **D25** | How is the custom board flashed and serviced? | **A Tag-Connect TC2030-NL land on UART0 (`J408`) — no USB port** | **DECIDED 2026-09-19 (owner):** *"is the usb port for initial load of the firmware? if so, lets change that to a TC2030-MCP-NL."* The USB-C carried first load, the console and recovery when OTA fails. The `TC2030-MCP-NL` itself is Microchip's ICSP cable (MCLR / VDD / GND / PGD / PGC to an RJ-12), which cannot program an ESP32, so the land is the same TC2030-NL footprint wired for UART0 in the ESP-Prog's order, reached with a `TC2030-IDC-NL` cable (bom A8). It replaces both the USB-C and the pin header, and with them the CC resistors, the VBUS sense divider, both USB ESD parts and the 22 Ω pair; GPIO19/20 join the pool (§9.8.1). Later updates go over WiFi OTA |
| ⭐ **D27** | **I/O by rows, aux outputs, three boards** — the shape of the module's I/O and of the board set | **Plain channels only, grouped by kind in rows on one face, on three boards** | ✅ **DECIDED 2026-09-19 (owner), with IO-16 added 2026-09-20.** Sixteen numbered sub-decisions, **IO-1…IO-16**, which the tools cite by number. **IO-1** 4 × 12 V + 4 × 5 V aux outputs (*"buying more TPS4H160B is fine"*) · **IO-2** 1 A each, all eight on together · **IO-3** they leave on pluggable screw terminals like the rest of the harness · **IO-4** grouped **by kind, in rows** (*"I want all 12v and 5v outputs to be together … And Inputs row, a 12v row, a 5v row"*) · **IO-5** a fourth row, **CTRL**: the pack plug, the FarDriver links, the parked display · **IO-6** the rows stack on **one face**, each row the edge of one board · **IO-7** **three boards — POWER · OUTPUTS · LOGIC** (§9.2) · **IO-8** **no dedicated circuits** — this is **D23** · **IO-9** `BL` **released** when the firmware is not running · **IO-10** a ≥ 3 A input choke and a 3 A tap fuse, and the converter's heat measured at the new load, rather than a firmware cap on the aux total (§3.2.3) · **IO-11** the 12 V brick moves to POWER's underside and **bolts to the box floor through a thermal pad — the floor is the heatsink**; BD-9's alloy plate is removed (§9.7) · **IO-12** the 5 V outputs keep `TPS2553` switches with an `SMF6.0A` and a **recorded residual risk**, rather than eFuses at ~4× the area (§6.2.2b) · **IO-13** the choke is Würth **`7448023005`**, hand-soldered (§3.2.6) · **IO-14** **the boards are sized to the design, not to the cavity estimate** (*"we have the ability to increase the board size if we need to"*); `tools/board_params.py` states the cavity that implies and M18 confirms it (§9.2) · **IO-15** the parked display and one-line connectors **stay** · **IO-16** (2026-09-20) **the firmware releases every aux output at key-off**, and `Q101`'s SOA margin depends on it (§3.2.5) |

## 9. Component breakdown and build plan

### 9.1 What may and may not sit on a breadboard

| | Allowed? | Why |
|---|---|---|
| Logic, buses, input conditioning (3.3 / 5 V) | ✅ **yes** | most of the work |
| The **84 V divider / IN-12 sense**, fed from a **current-limited bench supply** | ✅ **yes, carefully** | a 100 mA-limited supply makes a slip a non-event |
| **Any switching converter**, at any voltage | ❌ **never** | physics: breadboard contact inductance wrecks a buck's switching loop — it oscillates or destroys itself |
| **The 12 V load rail with real lamps** | ❌ **never** | breadboard tie points are good for ~1 A |
| ⚠️ **Anything fed from the pack** | ❌ **never** | 34 Ah of Molicel P42A ≈ **8P** ≈ **~360 A continuous** and far more into a short. A jumper working loose on B+ is an arc-welding event next to a lithium pack. **The bench supply is the safety device** |

### 9.2 Functional blocks and the three-board set

**Blocks A–F are functional names.** This plan and the BOM use them throughout ("board E" is block
E); on the prototype each is its own breadboard or perfboard (§9.3, §9.6).

| | Block | Domain | Prototype on | Phase |
|---|---|---|---|---|
| **A** | **Brain** — S3 + the two input `MCP23017` expanders (no screen, D17) | 3.3 / 5 V | breadboard → proto board | P0 · P1 · P3 |
| **B** | **Bus interface** — 2 × serial tap, CAN transceiver + 120 Ω, one-line | 3.3 V signals | breadboard → proto board | P0 · P1 · P3 |
| **C** | **Input conditioning** — the class-A networks (§4), the levers among them | 3.3 V, wires leave the box | breadboard → proto board | P2 |
| **D** | **Output drivers** — 12 high-side 12 V channels on three `TPS4H160B` (six lamps, the STOP lamp, `AUX12`, four 12 V aux), the 5 V aux buck and its four load switches, expander #3, horn, fan, buzzer; **8.47 A nominal** | 12 V / 5 V | breadboard **with LED stand-ins only** → stripboard with a reinforced bus (§9.6) | P2 |
| **E** | **Power supply** — 84 V → 12 V + 5 V (§3.2) | **84 V** | — (bench supply direct). Bought modules on a carrier PCB — never proto board | P2 |
| **F** | **Display high-side switch** (§3.3) | 12 V or 84 V per D11 | breadboard (12 V case) | ⏸️ parked (D11) |

There is **no brake-circuit block**: D23 made the cut, the lamp and the kill firmware I/O, so the
levers are block C, `BL` and the STOP lamp are block D, and the parts are deleted rather than moved.

**A + B are all that P0, P1 and P3 need, and both are breadboard-safe on USB power.** The power block
(E) gates only P2.

**The custom build is three stacked boards in one enclosure**, in the old-controller cavity under the
battery compartment (**M18**). Power flows from the floor up with the voltage falling, which puts the
most distance between the 84 V node and the 3.3 V serial taps (§3.2.4). **Each board owns one row of
harness connectors on one long face of the box** (D27/IO-4…IO-7), so every plug is reachable from one
side.

| Layer | Board | Domain | Holds | Blocks | Face row |
|---|---|---|---|---|---|
| 1 — floor | **POWER** | 84 V → 12 V / 5 V, and the controller links | B+ / B− entry and the key tap on one plug, `J101`; an `SMCJ90A` on B+ and no clamp on the key tap; the D13 soft-start switch and its gate network (§3.2.5); one CM choke per converter and the bulk caps on top; **both converters underneath — the 12 V brick bolts its baseplate to the box floor through a thermal pad (D27/IO-11), the Cincon beside it**; the hold-up diode and its 1 A fuse in PCB clips (§3.2.2); the Y2 capacitors; the baseplate-to-ground tie; the IN-12 divider. **And every controller connector, each with its driver and clamps beside it:** the `BL` open-drain FET `Q106` with its hard gate pull-down and the `R336` readback, the `ACC+` sense divider, the serial series resistors, the boost FET, and the parked display and one-line with their telltale and pin-9 resistors | E | **CTRL** |
| 2 | **OUTPUTS** | 12 V / 5 V | three `TPS4H160B` with their `CL` / `CS` resistors — six lamps, the STOP lamp, `AUX12`, the four 12 V aux (§6.2.2a) — the three low-side FETs, **the 12 → 5 V aux buck, its four `TPS2553` load switches and expander #3** (§6.2.2b), the rail's `SMBJ18A`, an `SMF18A` on every 12 V output and an `SMF6.0A` on every 5 V output (§6.2.4) | D · F | **12 V** on top · **5 V** underneath |
| 3 — lid | **LOGIC** | 3.3 V | the `ESP32-S3-WROOM-1` / `-1U` (§9.8.1), its 3.3 V regulator, both input `MCP23017`, the CAN transceiver (in standby while CAN is parked), the Tag-Connect service pads on UART0, and **every input terminal with its class-A network complete on this board** — both pods, the levers, and the two general-input terminals | A · B · C | **INPUTS** |

**Four inter-board interfaces on two junctions, all on 2.54 mm headers**, so that any one board can be
stood in for by a breadboard or perfboard section during bring-up (owner, 2026-09-15: *"both. i want
full options for pcb and breadboard."*). Each is **one crossing between neighbouring boards**: the
lower half stands on top of the lower board, the upper half hangs under the upper board. Power and
signals ride separate pairs, so each power bus stays a palindrome and every signal sits beside a
ground.

- **`PWR-OUT`**, POWER `J202` ↔ OUTPUTS `J311` — 23 contacts: 12 V on **10** and ground on **10**
  (8.47 A at ≤ 1 A a channel), the logic 5 V on 2, and `KEY_SENSE` on the centre contact between two
  grounds.
- **`CTRL`**, POWER `J105` ↔ OUTPUTS `J312` — 2 × 11, every signal facing a ground: the `BL` command
  and its readback, the `ACC+` sense, serial TX / RX, the boost command, and the parked display's
  CAN pair and three telltales.
- **`PWR-LOGIC`**, OUTPUTS `J307` ↔ LOGIC `J407` — 9 contacts: the logic 5 V, 3.3 V back down for the
  expander bus, `KEY_SENSE`, and a ground between each. LOGIC takes no 12 V.
- **`STACK`**, OUTPUTS `J308` ↔ LOGIC `J406` — **2 × 28**, odd contacts signals and even contacts
  ground. ⛔ **Its pinout is derived from `_STACK_SIGNALS` in `tools/netlist.py` and nowhere else** —
  never hand-patch it, and never quote a row count from this document:

| Pin | Signal | Pin | Signal | Pin | Signal | Pin | Signal |
|---|---|---|---|---|---|---|---|
| 1 | `LGT_LOW` | 15 | `DIAG_EN` | 29 | `HORN_CMD` | 43 | `UART1_RX` |
| 3 | `LGT_HIGH` | 17 | `SEL` | 31 | `FAN_CMD` | 45 | `BOOST_CMD` |
| 5 | `LGT_DRL` | 19 | `SEH` | 33 | `BUZZ_CMD` | 47 | `CANH` |
| 7 | `LGT_TAIL` | 21 | `CS1` | 35 | `V12_SENSE` | 49 | `CANL` |
| 9 | `LGT_TURN_L` | 23 | `CS2` | 37 | `BL_SENSE` | 51 | `ACC_SENSE` |
| 11 | `LGT_TURN_R` | 25 | `FAULT1` | 39 | `BL_CMD` | 53 | `SDA` |
| 13 | `LGT_STOP` | 27 | `FAULT2` | 41 | `UART1_TX` | 55 | `SCL` |

Every even contact is `GND`. Eight of these signals are **relayed** — they start or end on POWER,
cross `CTRL` to OUTPUTS and carry on here. The I²C pair comes *down* to expander #3 on OUTPUTS: it is
the input expanders' own bus, because no native pin is free for a second one (§6.2.2b).

- **The power buses read the same from either end**, so a reversed or mirrored mate is harmless, and
  never put two different rails side by side, so a mate one contact off is a short to ground — never
  84 V or 12 V onto logic.
- **The upper halves' footprints are generated pre-mirrored** ("…-UNDER"): place them on the bottom
  layer, and after the flip — plus at most a 180° turn — every pad sits over its mate's. A
  same-numbered dual-row footprint cannot be aligned by any turn: STACK's signals would land on ground.
- ⬜ **The inter-board connector family is the owner's open choice (M19)**, now for two junctions.
- **`RUN` and the lever lines cross no interface at all** — they land on LOGIC, beside the S3.

**Harness connectors — four rows on one face.** Every wire into the box lands on a **locking
pluggable screw terminal**: a right-angle header at the board edge, its plug screwed to the header's
flanges, the wire leaving straight out of the plug's back. The plugs are ordered loose with the
boards and wired by the owner.

⚠️ **A mismate is dangerous in exactly three ways**, so those three groups each own a pitch nothing
else uses, and everything else keeps the 3.81 mm family: a **5 V device in a 12 V header** (12 V into
the device), a **FarDriver lead in any other header** (12 V back-fed into the controller's 3.3 V
logic), and **the pack plug** anywhere but its own. An input harness in a 12 V header only shorts an
output into its own current limit, which reports the fault; a lamp in an input header sees 3.3 V
through 1 kΩ.

| Row | Pitch | Headers |
|---|---|---|
| **CTRL** | **7.62 mm** (Kefa) — pack only | `J101`, 6-way: 1 B+ · 2 empty · 3 B− · 4 B− · 5 empty · 6 `KSW`. Each empty position puts a pitch of air around B+ and around the key tap |
| | **5.08 mm** (Kangnex) — FarDriver only | `J309` brake/kill, 3-way: 1 `BL` · 2 GND · 3 `ACC+` · `J404` serial + boost, 5-way: TXD · RXD · `BW5V` (unused) · GND · boost · ⏸️ `J405` display 9-way and `J310` one-line 2-way, parked |
| **12 V** | 3.81 mm (Kangnex) | `J301` headlight 4 · `J302` tail 5 · `J303` front turn 4 · `J304` horn 2 · `J305` fan + buzzer 4 · `J313` **12 V aux 7** — four feeds alternating with three shared returns |
| **5 V** | **3.50 mm** (Kefa) — 5 V only | `J314` **8-way**, four outputs each with its own return, under OUTPUTS |
| **INPUTS** | 3.81 mm | `J402` left pod 9 · `J403` right pod 6 · `J306` levers 3 · `J409` and `J410`, **the general inputs, 8 each** |

- A plug seats in any header of its own pitch at least its size, so **within 3.81 mm no 12 V terminal
  may share a size with an input terminal**: inputs use **3, 6, 8, 8 and 9**; the 12 V row uses
  **2, 4, 4, 4, 5 and 7**. With every plug seated, a unique size leaves the wrong plug in the hand
  instead of in a header. `J403` is 6-way for exactly this — five conductors, but the tail's 5-way
  plug seated there would hold `RUN` to ground through a lamp.
- ⚠️ **Residual:** the three 4-way 12 V headers — `J301`, `J303`, `J305` — still take each other's
  plugs. Label them, and check every lamp after any service.
- `J101`'s plug wired mirror-image swaps only B+ and `KSW` — benign, the module is simply always on —
  and both B− stay B−.
- ⏸️ `J310` and `J405` are parked with D19 but **stay in the design** (D27/IO-15): footprint only,
  header not fitted, no plug ordered.
- ⬜ **M3 still gates `J306`:** a three-wire Hall lever adds a supply pin to the terminal.
- Headers stand **7.00 mm** (3.50), **7.25 mm** (3.81), **8.30 mm** (5.08) and **8.60 mm** (7.62)
  above the board, and a mated plug reaches 8.8–9.7 mm past the header's face. Each pinout, with its
  wire colours, is in `tools/netlist.py`.

**What JLC does not place.** JLC places every surface-mount part and the harness headers.
The owner **hand-solders** the TDK brick, the Cincon module and both Würth chokes (LCSC has no fit for
any of them — the 3 A `7448023005` is listed with no stock; trim the Cincon's pins before soldering —
5.6 mm minimum, no maximum), and fits the **loose parts** ordered with the boards: C1 and C2, bent
over and bonded lying on POWER's top face; the four Y2 discs, bent flat; the TDK's 680 µF output
capacitor, lying; and the DC-DC #2 fuse in its two clips (§9.5.2). JLC inserts through-hole parts
upright, and the height budget needs these lying down. `python3 -m tools.jlc_bom` prints both lists.

#### The envelope, and the cavity it requires

⚠️ **The boards are sized to the design, not cut out of a cavity estimate** (D27/IO-14). Every
number below comes from `python3 -m tools.board_fit` and `tools/board_params.py`; nothing here is
typed twice.

**The boards are 48 × 219 mm**, 4-layer. Length is set by the longest row — POWER's face packs
197.0 mm of headers end to end — and width by the tightest shelf-pack, with about 10 % of margin on
each. The other rows: LOGIC 185.9 mm, OUTPUTS' 12 V row 166.9 mm, its 5 V row 38.4 mm. Body density
runs 59 % on POWER's top face and under 30 % everywhere else, against a 75 % ceiling.

⚠️ **The cavity that envelope requires is bigger than M18's working estimate, and this is a finding
for M18, not a failure of the design:**

| | Required | M18's estimate | Excess |
|---|---|---|---|
| along the bike | **233.0 mm** | 200 | **+33.0 mm** |
| across (the sensitive axis) | **74.65 mm** | 50 | **+24.7 mm** |
| tall | **68.4 mm** | 70 | 1.6 mm to spare |

Across is the board, 3 mm of wall each side, 1 mm to drop it in past the far side, and **19.65 mm in
front of the connector face** — the deepest mated plug's 9.65 mm past its header, then a 10 mm bend
in the wire. Along is the board plus wall and 4 mm of drop-in room at each end. ⬜ M18 confirms these
or forces a rethink.

**The stack's height is derived, never typed**, from the netlist's own part and connector heights.
With 1.6 mm boards and 1.0 mm of clearance, solder tails are per part: long leads are trimmed to
1.5 mm (IPC-A-610), and pins too short or stiff to trim are charged at their drawing's maximum.

| Gap | mm | What sets it |
|---|---|---|
| floor → POWER | 13.2 | `U201`, the 12 V brick, **seats on the box floor** through a 0.5 mm thermal pad; the Cincon hangs 10.7 mm. The 0.5 mm liner covers the rest of the floor and is cut away under the brick |
| POWER → OUTPUTS | 25.1 | the 22.0 mm chokes standing on POWER, and `J314`'s 7.0 mm hanging under OUTPUTS |
| OUTPUTS → LOGIC | 11.0 | `J313` 7.2 mm up, and LOGIC's header pins 2.1 mm down |
| LOGIC → lid | 8.2 | `J410` at 7.2 mm |
| **used** | **62.4 of 64.0** | 1.6 mm spare — ⚠️ provisional until M18 and the enclosure model |

⚠️ **`J314` is a placement constraint, not just a height.** The 5 V terminal hangs **7.0 mm under
OUTPUTS**, so **nothing on POWER taller than 17.1 mm may sit beneath it** — which rules out `L101`,
`L102`, `C201` and `C202`, both 22 mm chokes and both bulk cans. Place POWER's tall parts first,
clear of the 5 V row's footprint, and the rest around them.

⬜ **Once the inter-board family is chosen, each pair's mated height *is* its gap** — so it is picked
before layout (M19). The pairs are booked at 11.0 mm (`PWR-OUT`, `CTRL`, `PWR-LOGIC`) and 6.6 mm
(`STACK`), all unconfirmed, and each must be a type that mates at its gap.

⚠️ **A short does not fail safe: `RUN` to ground.** The toggle is closed in RUN against a pull-up, so
a failed TVS or a chafed pod wire reads as RUN and silently defeats the secondary kill. The key
switch is the primary kill, and it is hardware (D24).

⚠️ **`ACC+` is a sensor, not a rail.** It feeds the `R343` / `R344` divider (100 k / 180 k → 3.28 V)
on expander #2 and nothing else, and **firmware must raise an alarm when it reads low with the key
on** — the throttle's 5.1 V is not arriving, which means a `BL` cut would mean nothing anyway.
⛔ **Firmware must not gate the lamps or the horn on it:** every 12 V output runs off the module's own
converters, and this sensor cannot tell a dead controller from one chafed sense wire.

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
| Full-load test of DC-DC #1 | CH1+CH2 series | ⚠️ **The load is 8.47 A / 101.7 W now** ≈ 113 W in ≈ **1.77 A at 64 V** — inside the 3 A limit, but the 12 V side needs a load bank that can sink 8.5 A, which the DP2031 is not. Owner item 4 |

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
conduction-cooled quarter brick, **58.3 × 37.2 × 12.7 mm**, aluminium baseplate. It runs at **68 % of
its rating** against the 8.47 A load, and **in this EN 50155 railway market the 160 V input rating
sets the price, not the wattage** — smaller parts cost more, and none of them could carry this load:

| Part | Output | Price (uncoated) |
|---|---|---|
| **TDK `CN150B110-12`** ✅ | 12 V / **12.5 A** / 150 W | **$113.10** |
| TDK `CN100B110-12` | 12 V / 8.4 A / 100 W | **$146.03** |
| TDK `CN50B110-12` | 12 V / 4.2 A / 50 W | ~$170 (RS, regional listing); TME 0 in stock |
| RECOM `RP40-11012SFR/P` | 12 V / 3.33 A / 40 W | **$126.52** |

⚠️ **All three of those alternatives are under-rated for this load** — 8.4 A, 4.2 A and 3.33 A
against 8.47 A — so downsizing is no longer even arguable. What the TDK dissipates at 101.7 W is
still ⬜ unmeasured (§3.2.3).

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
| **Input fuse, DC-DC #1 — FAST-blow**, ≤10 A, on the **+Vin leg** (−Vin grounded), with I²t headroom for turn-on inrush | TDK-Lambda instruction manual | **Littelfuse `KLKD003`** — **3 A**, **600 VAC / 600 VDC**, 100 kA AC / **50 kA DC**, 10.3 × 38.1 mm midget, fitted at the **module's B+ tap** so it serves the tap and DC-DC #1 together (§3.2.5). ⛔ Not the 2 A `KLKD002`: the aux block puts 1.93 A through this link (§3.2.3). Holder: **Mersen `FEB-11-11`** inline + **`FSB1`** boots (BOM E4) |
| **Input fuse, DC-DC #2 — 1 A TIME-DELAY** | Cincon datasheet | **Schurter `0001.2504`** (SPT 5×20 ceramic) — 250 VAC / **300 VDC**, UL 1500 A breaking at 300 VDC |
| Fuse holder for that link, on POWER | — | **`FH201`: two Littelfuse `01110501Z` PCB clips** (5 mm, with fuse stop, 10 A) **in one footprint**, their 17.8 mm spacing fixed in copper; the owner fits them loose. The clips do not conduct to each other — the fuse does — and the DC interrupting duty is the fuse's, not the clips'. ⬜ Seated height to confirm on a real part. ⛔ **Not the Schurter `FAC 0031.3803`** (PCB THT, 600 VAC/VDC UL, 10 A VDE / 16 A UL, −40…+85 °C, IP40) in the stack: it is a **47.5 mm-tall vertical** holder. It suits a free-standing carrier only |
| **Bulk input electrolytic ≥100 µF**, low-impedance, Chemi-Con KXJ class, at the terminals; two in parallel below −20 °C | TDK | **Chemi-Con `EKXJ221ELL221MM25S`** — 220 µF / 220 V (the requirement is ≥200 V), −40…+105 °C, 18 × 25 mm. ⚠️ **×2** (§3.2.2), bent over and bonded lying on POWER's top face, beside the chokes — the underside belongs to the two converters (D27/IO-11) |
| **4700 pF from +Vin AND from −Vin to the module BASEPLATE**, close to the terminals, HV rated | TDK — its *primary* EMI-and-stability measure | **Vishay `VY2472M49Y5US6`** Y2 (BOM E9), lying flat. The baseplate is tied to ground at **one** point, so a shorted Y2 blows the tap fuse instead of floating the baseplate at 84 V |
| **`CNT` strapped to −Vin; +S strapped to +V and −S to −V.** `CNT` is negative logic — *open = OFF* — and an open sense pin leaves the output undefined | TDK-Lambda instruction manual | Three straps at the brick on POWER. ⚠️ Left open, the 12 V rail never comes up — and every lamp with it |
| **Output capacitor *"for stable operation"*: 680 µF / 25 V solid**, plus 2.2 µF ceramic across the output and 22 nF from +V and from −V to the baseplate | TDK-Lambda instruction manual, Table 6-1 | **JIERR `PA35V680M10x15`**: 680 µF / **35 V** polymer, 16 mΩ, 10 × 15 mm, **lying down** under the brick's height at 10.5 mm (BOM E20) — 35 V, not 25, because the rail's `SMBJ18A` lets it reach 29.2 V · 2.2 µF / 25 V · 2 × 22 nF / **250 V** — rated to survive the baseplate lifted to the 84 V rail (BOM E21) |
| **Input dv/dt ≤ 10 V/µs** | TDK | delivered by D13(b)'s soft-start |
| **Common-mode choke — one PER CONVERTER**, **before** the bulk capacitor. The Cincon meets its EN 50155 EMC rating only *"WITH EXTERNAL FILTER"*; TDK: *"when using multiple power supplies, add choke to each power supply input"* | Cincon + TDK | **Two different WE-CMBNC parts, one per converter.** `L101`, the TDK's: **Würth `7448023005`** — 5 mH, **3 A @ 70 °C**, 300 V AC, at **63 % of rating** on 1.88 A (§3.2.6c), ⬜ no stock at LCSC, so hand-soldered. `L102`, the Cincon's: **`7448022010`** — 10 mH, 2 A @ 70 °C, 85 mΩ, 2100 V hipot, −55…+125 °C, AEC-Q200 Grade 1, unchanged. Both are **four-terminal parts** (windings 1–4 and 2–3), so each converter's −Vin is its own net, joined to ground only through its own winding, and both are **22.0 mm tall** × 18.0 × 14.0 mm |
| **Input TVS** | Cincon (names `P6KE180A` for railway surge) | **`SMCJ90A`** (1500 W, DO-214AB) — §3.2.1 |
| Hold-up blocking diode | §3.2.6(a) | **`1N4007`** — 1000 V, I<sub>FSM</sub> 30 A @ 8.3 ms / 45 A @ 1 ms. On POWER the SMA-packaged equivalent (`M7`, 1000 V / 1 A, 30 A surge); the DO-41 part is the breadboard's |
| Cooling path for the conduction-cooled quarter brick | TDK | **Bolt the baseplate to the box floor through a thermal pad — the floor is the heatsink** (D27/IO-11, §3.2.3, §9.7). Baseplate −40…+100 °C, OTP trips 105–120 °C, so **target Tb ≤ 85–90 °C**; the dissipation that sets it is ⬜ unmeasured. TDK's **`HAQ-10T`** finned sink (7.5 °C/W in free air, 57.9 × 25.4 × 36.8 mm, BOM E5) is a free-air part and does not fit the stacked build |

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
- ○ Value alternative to the `KLKD003`: **`KLKR003`** — 3 A, 600 VAC / **300 VDC**, 200 kA AC / 20 kA DC,
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
  The custom boards use locking pluggable screw terminals instead — right-angle headers 7.25–8.60 mm
  tall with the plug screwed to the header; their heights and pins set several of the stack's gaps
  (§9.2).
- **Boards A / B / C** are small; one board per block.
- The **S3-DevKitC-1 is ~63 × 25.5 mm**. Its header rows are a whole multiple of 0.1", so it spans any
  0.1" grid; with plated through-holes every pin is reachable from the underside. ⬜ **M15** confirms the
  header spacing (expect 0.9" / 22.86 mm), copper weight and plating on whichever board is bought.

#### 9.6.2 Current capacity, creepage, and what prototype board does *not* fix

1. **Current capacity.** By IPC-2221 (1 oz copper, 10 °C rise) a **1 mm trace carries ≈ 2.4 A**; typical
   proto-board rails are 1–2 mm, so **3–4 A is the ceiling**. ⚠️ **The custom board's 8.47 A bus cannot be
   prototyped on perfboard at all** — prototype the lighting with LED stand-ins and leave the aux
   outputs to the PCB. **Reinforce the 12 V rail and its return with soldered 20 AWG bare copper**,
   tacked to every pad.
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

### 9.7 Housing — an all-metal CNC box

- ✅ **The custom stack's enclosure is an all-metal box, CNC-machined by JLCCNC from this project's
  models** (owner, 2026-09-18). It follows the custom boards' outline (§9.2) and M18. ⭐ **The brick's
  baseplate bolts to the box FLOOR through a thermal pad, so the floor is the heatsink** (D27/IO-11):
  **there is no interface plate in the stack** — the 22 mm chokes could not have stood under one
  bolted to the 12.7 mm brick. Wall, floor and lid thicknesses come from the model, and until then
  the height budget uses 3 mm allowances and says it is provisional.
- ⚠️ **The box kills a PCB antenna**, so LOGIC fits the external-antenna `-WROOM-1U` (§9.8.1). Its
  antenna sits outside the box, and M18 finds where a lead can leave. ⚠️ **Insulate the antenna's
  SMA bulkhead from the box** — bonded, it is a second connection between the module ground and the
  box.
- ⚠️ **The box is insulated from the frame** (gap pad, nylon hardware), or the frame becomes a second
  B− return (§3.2.4).
- ⚠️ **Floor liner:** a 0.5 mm insulating sheet (Formex GK-17 class) on the metal floor under POWER.
  POWER's underside carries 84 V pins and the box is bonded to ground, so without it one bent tail, a
  stray strand or a flexed board is a pack short. ⚠️ **It is cut away under the brick's baseplate** —
  that is the thermal path — so the pad there is what keeps POWER's underside pads, `+Vin` among
  them, off the brick's case. ⬜ What sets that standoff is not on any drawing: settle it before the
  floor is cut.
- ⬜ **The brick's two M3 threads now have two jobs** — the FG land's screw and washer at the board,
  and the floor bolt below. The outline drawing gives no thread depth and does not say whether the
  holes pass through; ask TDK or measure before the floor is drilled.
- ⚠️ **Ingress:** a gasket and cable glands, or a sheltered mounting position.
- **Recovery access:** LOGIC, the top of the stack, carries a Tag-Connect TC2030-NL land on UART0
  (`J408`, §9.8.1), so with the lid off the module can be flashed and its console read without
  dismantling anything: a `TC2030-IDC-NL` cable into an ESP-Prog (bom A8), held on by hand for the
  flash. ⚠️ With the pack connected, use an isolated USB adapter (§3.2.4).
- Strain relief at every wire entry (§9.6.2).

**At the prototype stage:**
- **Keep the DevKit's USB port reachable**, or the prototype commits to OTA-only reflashing.
- **Block E goes in a METAL enclosure of its own:** the module is a **conduction-cooled pinned brick**
  whose baseplate wants to bolt to metal, a metal box is the right EMC answer next to 3.3 V serial taps
  and 80 A of chopped phase current, and it is the only sane home for the 84 V node. Whether it also
  needs moving air waits on the §3.2.3 measurement.
- Internal envelope: follows the boards — plan for **4 positions, A, B, C and one D**. Allow **≥20 mm per
  layer** if stacking (DevKit plus headers ~13 mm).
- ⚠️ **Mounting:** generic proto board may have **no mounting holes** — buy boards with them or drill
  before populating.

### 9.8 ⭐ Custom PCB — the likely final form (owner's intent, 2026-09-08)

**Breadboard → generic perfboard prototype (§9.6) → custom PCB.** Build the prototype so it transfers,
and don't constrain the custom boards with DevKit artifacts. The custom build is the three-board set of
§9.2.

#### 9.8.1 Most of the pin-map constraints are DevKit artifacts, not silicon

| Constraint in §3.1.3 | On a custom PCB with a bare WROOM-1 |
|---|---|
| Only **36 of 45** GPIOs reach the headers | ✅ **Gone** — route all of them |
| **GPIO33, 34** not broken out | ⛔ **Unchanged — the module, not the DevKit.** The `ESP32-S3-WROOM-1` / `-1U` has no IO33 or IO34 pad; both exist only inside the module |
| **GPIO38 / 48** and the onboard RGB LED (the v1.0-vs-v1.1 trap) | ✅ **Gone** — no LED, or fit one where you like |
| **GPIO44** driven by the onboard CP2102N | ✅ **Recovered** — no UART bridge. It is U0RXD, the console and download RX on the service pads, and nothing else: a harness wire there would fight the programmer's TX, so the IN-14 tap is held for GPIO19. ⚠️ Its boot-time pull-up sits at a FET's threshold, so never a gate |
| **GPIO35, 36, 37** and octal PSRAM | ✅ **Yours by purchase order** — specify the module variant (§9.8.3) |
| ⛔ **Strapping GPIO0, 3, 45, 46** | ⚠️ **Unchanged — silicon.** No wire that leaves the box |
| **GPIO19, 20 = USB** | ✅ **Gone** — the custom board has no USB port; flashing, the console and the fallback when OTA fails run over UART0 at the service pads. Both are ordinary pins and both are now used: GPIO19 is the STOP lamp, GPIO20 the right brake lever (§9.8.2). ⚠️ GPIO20 comes out of reset carrying `USB_PU` (`GPIO-RESET-PULL` watches what it drives) |
| ⛔ **GPIO43 emits the ROM boot log** | ⚠️ **Unchanged — silicon.** Never a load driver |
| ⛔ **GPIO26–32 = in-package flash · GPIO22–25 do not exist** | ⚠️ **Unchanged** |

**Net: a clean pool of 32** (the DevKit prototype has 28) — the 45 GPIOs that exist, less the 7 flash
pins (26–32), IO33/34 (no pads) and the 4 strapping pins. GPIO43 counts in the 32 but only ever carries
U0TXD (the ROM boot log).

**One footprint, two modules.** The `ESP32-S3-WROOM-1` (PCB antenna, 18 × 25.5 mm) and the
`ESP32-S3-WROOM-1U` (U.FL connector for an external antenna, 18 × 19.2 mm) share pads and pinout, and
both come as `-N8` (85 °C) and `-H4` (105 °C), so D18 applies to either. LOGIC's footprint accepts
both and keeps the PCB antenna's keep-out. **The `-1U` matters because a metal enclosure — or a metal
cavity with the battery tray for a lid — kills a PCB antenna**, and Espressif asks for at least 15 mm
of clearance around one in every direction. The enclosure is metal (§9.7), so the custom board fits
the `-1U`.

**Around the module**, per Espressif's hardware design guidelines:
- **470 Ω in series in U0TXD** — the guideline asks for 499 Ω against harmonics, and 470 Ω is the
  nearest JLC Basic value.
- **EN:** a 10 kΩ / 1 µF RC. A `TLV803S` supervisor footprint sits on EN, **not fitted** — fit it if
  a slow or bouncing 3.3 V ramp ever shows up.
- **IO0:** 10 kΩ pull-up, so an unprobed service pad cannot select download mode at key-on.
- **UART0 is the service port, on a Tag-Connect TC2030-NL land (`J408`, D25)** — six bare pads and
  three unplated alignment holes, nothing fitted, no paste. The pads follow the ESP-Prog's PROG header:
  1 `EN` · 2 VDD, **not connected** (the board powers itself; the ESP-Prog can be jumpered to 5 V) ·
  3 U0TXD, through the 470 Ω · 4 ground · 5 U0RXD · 6 `IO0`. The `TC2030-IDC-NL` cable takes pad *n* to
  IDC pin *n*, so it plugs straight into an ESP-Prog, whose DTR / RTS drive `EN` and `IO0` for an
  automatic download (bom A8). Tag-Connect's drawing asks for no track or via between the pads and
  0.51 mm around them; the project cannot carry that, so the build writes it to `layout-rules.txt`.
  ⬜ Before ordering, check the stencil (paste) layer has no aperture over the six pads — a solder dome
  under a spring pin is a bad contact.

#### 9.8.2 What gets easier, and what may reverse

- ✅ **D16 is FULL NATIVE on the custom board (owner, 2026-09-18).** The S3 drives the seven lamp
  inputs and `DIAG_EN` / `SEL` / `SEH` directly, over the STACK connector
  (§9.2) — **the I2C bus is out of the lighting path entirely.** Three `MCP23017`s are fitted: #1
  uses 13 of its 14 input-capable bits — the bar inputs, where a bus glitch is a missed press, the
  boost button, the run/off toggle and the `BL` readback (GPB6 is spare); #2 senses `ACC+` on GPA0
  and carries the **13 free inputs** on `J409` and `J410`, each class-A conditioned on the board;
  #3 is on OUTPUTS and commands the aux block (§6.2.2b). GPA7 / GPB7 are output-only (§3.1.3).

##### ⭐ Three pin choices the design turns on

| Signal | Pin | Why that pin |
|---|---|---|
| **STOP lamp** (`U302` `IN4`, through 4.7 kΩ) | **GPIO19** | No reset pull, and lighting stays native (D16). The two ~60 µs high glitches the S3 datasheet lists at power-up (v2.2 Table 2-2) can put at most a **~20 µs** pulse on the channel — `TPS4H160B` turns on in 20 µs minimum — which is below visibility on a 0.12 A lamp. What actually holds it off is `IN4`'s own 100–250 kΩ internal pull-down |
| **`BL`** (the open-drain FET's gate, 100 Ω series, 10 kΩ pull-down) | **GPIO16** | No reset pull, and **only a low glitch** at power-up (Table 2-2), so the motor cut stays **released** through boot — which is D23's whole requirement |
| **Right brake lever** (IN-06) | **GPIO20** | ⛔ **GPIO20 comes out of reset with `USB_PU`, the USB D+ pull-up** (Table 2-1) — far stronger than the 45 kΩ weak pull-up, so **no pull-down could hold a gate off there**. On an input that is already pulled up to 3.3 V it is harmless, so the lever takes the pin and nothing with a pull-down bias may ever be moved onto it. `GPIO-RESET-PULL` refuses any reset-pulled-up pin driving an enable, whatever pull-down it has |
- ⚠️ **The expanders share one RESET pull-up, and no GPIO drives it.** Firmware recovers a hung bus by
  clocking SCL; past that, only a power cycle resets them.
- ⚠️ **Spare pins are scarce.** Full native moves eight signals off expander #2 and onto the S3, into a
  pool only four pins larger than the prototype's, and **the pool is now full: 32 of 32, none spare**
  (`python3 -m tools.gpio_budget`). The pin assignment, and the count of what is left, live in
  `tools/netlist.py` and are checked by `tools/rules.py` — this plan carries the rules, not the
  numbers.
- ⚠️ **What does not change: the functional rules.** Carry these over verbatim — analog only on ADC1
  (GPIO1–10), brake inputs native for < 10 ms, boost on a dedicated pin with a hard external pull-down
  and never on a bus, nothing that leaves the box on a strapping pin, no pin that comes out of reset
  pulled up on an active-high enable (§3.1.2), TVS at every connector, every gate biased OFF.

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
  The build writes a net class **HV, 1.25 mm to every other net** (IPC-2221B B2, the 151–300 V band,
  for the 160 V do-not-exceed) over POWER's pack-voltage nets to
  `build-eprj3/layout-rules.txt`. ⚠️ **Set it up in the editor before routing** — the generated PCB
  carries only a board-wide 0.2 mm.
- ✅ **A ground plane** — the big one: §3.2.4's concern is 3.3 V TTL serial taps beside 80 A of chopped
  phase current.
- ✅ **Trace widths sized to real current** — the 20 AWG reinforcement disappears.
- ✅ **Decoupling placed properly**, mounting holes, strain relief and conformal coat designed in.
- ✅ **Partition by voltage** — three stacked boards with 84 V at the floor and 3.3 V at the lid (§9.2),
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
§9.8 the custom PCB · §12 sourcing evidence.

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
| Littelfuse **`KLKD003`** | **3 A** fast-acting · **600 VAC / 600 VDC** · 10.3 × 38.1 mm midget · 100 kA AC / **50 kA DC** interrupting — the DC figure is a measured PV-approval rating (UL 2579 / IEC 60269-6), not an extrapolated AC one | Littelfuse KLKD datasheet |
| Schurter **`0001.2504`** (`SPT`) | 250 VAC / **300 VDC**, UL 1500 A breaking at 300 VDC — the DC rating comes **only from the UL/CSA listing** (the IEC/VDE line is AC-only); DC rating derates with current (§9.5.2) | Schurter SPT datasheet |
| Schurter **`FAC 0031.3803`** | PCB THT, **vertical, 47.5 mm tall**, 600 VAC/VDC UL, 10 A VDE / 16 A UL, −40…+85 °C, IP40. Power acceptance 3.2 W at 23 °C, ~1.2 W by 60 °C — fine for a 1 A link, **could not carry a 10 A link at 60 °C**. Too tall for the stacked build (§9.5.2) | Schurter FAC datasheet |
| Würth **`7448023005`** (`L101`) and **`7448022010`** (`L102`), both WE-CMBNC | `7448023005`: 5 mH · **3 A @ 70 °C** · 300 V AC · 22.0 mm tall × 18.0 × 14.0 mm — a mechanical drop-in for the 2 A part, and the one the 1.88 A converter input needs (§3.2.6c). `7448022010`: 10 mH · 2 A @ 70 °C · 85 mΩ · 300 V AC · 2100 V AC hipot · −55…+125 °C · AEC-Q200 Grade 1 · same body. Both are four-terminal (windings 1–4 and 2–3). An AC-only rating is the documentation convention for CM chokes (IEC 60938-2 is an AC standard) — a CM choke sees near-zero differential voltage. Only `WE-SL5` states a DC limit (80 V DC) and is out. ⚠️ Halving the inductance halves the common-mode filtering, and ⬜ neither value is tested for interference: TDK states no inductance figure, so 10 mH was this project's own choice | Würth datasheets |
| TDK **`HAQ-10T`** | 7.5 °C/W natural convection, a free-air figure · 57.9 × 25.4 × 36.8 mm · for the CN-B110 series (fit ~85% confident, BOM E5). Not used in the stacked build (§3.2.3) | TDK |
| IXYS **`IXTA26P20P`** (TO-263; the `IXTP26P20P` is the same die in TO-220) | V<sub>DSS</sub> −200 V · V<sub>GSS</sub> ±20 V continuous, ±30 V transient · V<sub>GS(th)</sub> −2.0…−4.0 V · T<sub>JM</sub> 150 °C · guaranteed SOA 160 W at −200 V / 5 s / T<sub>C</sub> 70 °C · forward-bias SOA plots at T<sub>C</sub> 25 °C **and 70 °C**, each with 25 µs, 100 µs, 1 ms, **10 ms, 100 ms and DC** lines. Read at 84 V on the 70 °C plot (±10 %): ≈460 W (10 ms) · ≈254 W (100 ms) · ≈191 W (DC). TO-263 outline: 4.83 mm max tall. ⚠️ `tools/soft_start.py` derates Fig. 14 by 0.72 for a 60 °C ambient, which is why the DC line it gates the key-off decay against is 138 W. `IRF9640PbF`: ~335 W on its 10 ms line at 84 V (~241 W derated for 60 °C). `FQP12P20`: no SOA plot at all | IXYS / Littelfuse **DS99913D** (not the 2007 "Preliminary" sheet) · Infineon / onsemi datasheets |
| Infineon **`BSS127`** | N-channel **enhancement mode**, logic level · V<sub>DS</sub> 600 V · V<sub>GS(th)</sub> 1.4 / 2.0 / 2.6 V · R<sub>DS(on)</sub> ≤ 600 Ω at 4.5 V · P<sub>tot</sub> 0.5 W · SOT-23. ⛔ The same-family `BSS126` is **depletion mode** (V<sub>GS(th)</sub> −2.7…−1.6 V, conducting at V<sub>GS</sub> = 0) | Infineon BSS127 / BSS126 datasheets, Rev 2.1 |
| onsemi **`SMS15T1G`** and **`SMS05T1G`** | One family sheet, one SC-74 quad pinout: pads 1/3/4/6 cathodes, 2/5 anodes · `SMS15T1G`: V<sub>RWM</sub> 15 V · V<sub>BR</sub> 16.7–18.5 V · clamps 24.0 V at 5 A, 29.0 V at 12 A · `SMS05T1G`: V<sub>RWM</sub> 5 V · V<sub>BR</sub> 6.0 V min · 9.8 V at 5 A · I<sub>R</sub> ≤ 20 µA · ~300 pF per line | onsemi SMS05T1/D, Rev 10 |
| Microchip **`MCP23017`** | **GPA7 and GPB7 are output-only** · `RESET` and A0–A2 must be externally biased · 1.8–5.5 V · V<sub>IH</sub> 0.8 × V<sub>DD</sub> = 2.64 V at 3.3 V | Microchip DS20001952, rev D |
| Espressif **`ESP32-S3-WROOM-1` / `-1U`** | 41 pads, **no IO33 or IO34** · `-1` 18 × 25.5 mm with PCB antenna, `-1U` 18 × 19.2 mm with U.FL, same pinout · `-N8` −40…+85 °C, `-H4` −40…+105 °C, `R8` / `R16V` −40…+65 °C · the ambient rating is the air immediately outside the module | ESP32-S3-WROOM-1 / -1U datasheet v1.8; Espressif hardware design guidelines (15 mm antenna clearance) |
| Alpha & Omega **`AO3400A`** | Logic-level: **48 mΩ guaranteed max at V<sub>GS</sub> 2.5 V**; SOT-23, 30 V (caveats in the BOM) | AOS datasheet |
| TI **`TPS4H160BQPWPRQ1`** | See §6.2.2a. `CL` unused must be tied to ground, giving the internal 8–14 A limit; R<sub>CL</sub> = 0.8 V × 2500 / I; `CS` sources I<sub>OUT</sub> / 300 and drives 4.5–6.5 V in a fault | TI datasheet SLVSCV8 |
| TI **`LM73605`** | 3.5–36 V in, **42 V absolute maximum**, 5 A out, 500 kHz; `EN` may be tied to `PVIN`, so the rail is live whenever V12 is; `VCC` must not be loaded externally; `FB` and `SS/TRK` must never be shorted to ground in operation | TI SNVSAH5A |
| TI **`TPS2553`** | Current-limited load switch, 5 V class; **`OUT` rated 7 V** · limit **1.19–1.39 A** with a 20 kΩ on `ILIM` (never open, never shorted) · open-drain `FAULT` after a 5–10 ms deglitch · reverse-voltage comparator takes **3–7 ms** to open the pass transistor (§9.3.2) | TI SLVS841F |
| onsemi **`SMF6.0A`** | Single-line TVS, V<sub>RWM</sub> 6.0 V · clamps **10.3 V** at its rated pulse — above the `TPS2553`'s 7 V `OUT`, which is the recorded residual risk of D27/IO-12 (§6.2.2b) | onsemi SMF series datasheet |
