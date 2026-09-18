# REVV1 ESP32 module — BOM

**✅ $382.75 committed** (14 lines) · ~ **$212.15 estimated** (29 lines) · **≈$595 all-in, EX-DUTY** · ⚠️ **tariffs are counted in no total here:** $31.97 on the Mouser line (E1, 25%) and $26.09 on DigiKey order 101547984 (with $8.49 shipping and $14.68 tax, total $232.22).
📦 in hand · ⏳ ordered, not yet received · ✅ price verified · ~ approximate · ⬜ no price · ◐ candidate, **unverified** · ⏸️ parked

| # | Qty | Part | St | $ | Notes |
|---|---|---|---|---|---|
| **A1** | 1 | **ESP32-S3-DevKitC-1** `WROOM-1-N8` | 📦 | — | v1.0 board → GPIO48 excluded, GPIO38 free. Never an `R8` (65 °C) |
| **A2** | 2 | Turned-pin socket strips, 2.54 mm | ⬜ | ~3 | ⚠️ Never dual-wipe — they walk out under vibration |
| **A3** | 2 | **Bar-mount switch sets**, L + R | ◐  | ~30–50 | ◐ **LEFT POD RECEIVED, HARNESSED AND TESTED WORKING 2026-09-11** — 12 wires → 8 conductors → 7 bits; map in `revv1-inputs-bench-session.md`. It arrived wired as a **power-distribution block** (a shared +12 V feed, flash injecting onto the high-beam output), so two cuts were needed to make the switches independent contacts. ⏳ **Right pod still in transit** — it carries the **lighting slider**, flameout and e-start. ⚠️ Expect it to be a power-distribution block too; ground any shared feed rather than feeding it |
| **B1** | 3 | **`SN65HVD230`** breakouts | 📦 | — | In hand ×3 — **do not order.** Characterised: 120 Ω fitted, no `Rs` exposed, 8/8 loopback at 1 Mbit — a generic replacement may be neither. The bare `SN65HVD230DR` SOIC-8 is a custom-PCB-stage part |
| **B2** | 1 | 120 Ω termination | 📦 | — | On the breakout. **68 Ω joined** = the CAN pre-flight gate |
| **B3** | 4 | 1 kΩ series | ⬜ | — | One is display pin-9 back-feed protection |
| **C1** | 10 | **1 kΩ** pull-up + 1 kΩ + 100 nF | ⬜ | ~5 | ⚠️ **1 kΩ, not 4.7 kΩ** — wetting current. The brake inputs IN-05/06 take G3's 10 kΩ instead |
| **C2** | 20 | **`PESD5V0S4UD`** quad TVS | 📦 | **8.54** | ✅ Paid 09-10, **received 09-18** (20 @ $0.427, `PESD5V0S4UD,115`, DK 1727-3928-1-ND). Need **6 pkgs**: 4 on BRAIN's class-A lines + `D405` (CAN, where 5 V standoff is *correct* on a 3.3 V pair) + `D313` (brake levers, logic level through the D23 diodes). **14 spare.** ⛔ **Not usable on 12 V lines — see C4.** Datasheet: V_RWM 5 V · V_CL 8 V@1 A / 13 V@20 A · **unidirectional ×4 lines** · common anode. ⛔ **SOT457/TSOP6, 6-pin 0.95 mm — not SOIC-8** (adapter: X6) |
| **C3** | 4 | **`MCP23017-E/SP`** DIP-28 | 📦 | **6.76** | ✅ Paid 09-10, **received 09-18** (4 @ $1.69, DK MCP23017-E/SP-ND). Need 2: #1 = 10 bar inputs, #2 = 5 lighting + diagnostics. DIP-28 through-hole — no adapter. I²C part, not the SPI `MCP23S17` |
| **C4** | 6 | ⬜ **Quad TVS array, ≥24 V standoff** | ⬜ | ~6 | ⭐ **NEW 2026-09-15 — the only new part the board-set gaps required.** ⛔ **`C2`'s `PESD5V0S4UD` cannot do this job: it is V_RWM 5 V and DRV's harness lines are 12 V feeds**, so it would conduct continuously — a dead short across the channel it protects, with nothing in the schematic looking different. **Requirement:** 4 channels, **V_RWM ≥ 24 V**, clamping **below 40 V** (the `TPS4H160B`'s limit). 5 fitted on DRV (`D308`–`D312`, one per harness connector J301–J305) + 1 on BRAIN (`D406`, **DNP** until D19 un-parks the display). ⚠️ C2 is **not** superseded — it stays fully used on BRAIN's logic lines and on `D313` (the brake levers arrive at logic level through the D23 `1N4148`s) |
| **D1** | 4 | TI **`TPS4H160BQPWPRQ1`** | 📦 | **15.04** | ✅ Paid 09-10, **received 09-18** (4 @ $3.76, DK 296-44711-1-ND). **2 fitted** = 8 ch for 6 (the brake lamp is switched by the brake circuit's Q1, G2); 2 spare. 28-HTSSOP 0.65 mm with thermal pad — the hardest mount on the BOM (Notes; adapter: X7). ⚠️ **40 V — 12 V rail ONLY** |
| **D2** | 6 | 20 kΩ pullup, OUT→VBAT | ⬜ | ~1 | Required for open-load detect — one per lighting channel |
| **D3** | 10 | **`AO3400A`** (Alpha & Omega, genuine) | 📦 | **3.22** | ✅ Paid 09-10, **received 09-18** (10 @ $0.322, DK 785-1000-1-ND — `785-` = Alpha & Omega). Covers 5 channels: fan · buzzer · horn · boost · spare. Chosen for **48 mΩ guaranteed max at V_GS 2.5 V** — clones lack that guaranteed figure. SOT-23 (adapter: X6). Fan channel needs a flyback diode |
| **D5** | 1 | **Buzzer, 12 V** | ⬜ | ~2 | Only boost-mode feedback since D17. PWM transducer, not self-drive |
| **D6** | 1 | **Cooling fan, 12 V** | ⬜ | ~8 | Thermostatic off serial temps |
| **D7** | ~15 | Screw terminals, 5 mm | ⬜ | ~8 | Consumes a whole board edge |
| **D8** | — | 20 AWG bare copper | ⬜ | ~3 | 12 V bus reinforcement, sized for the measured 2.62 A |
| **D9** | — | Gate pull-downs, resistors, TVS | ⬜ | ~5 | Every gate biased OFF. ⚠️ **Includes `R110`/`R111`, 100 kΩ gate-to-SOURCE pull-ups on `Q101` (D13) and `Q104` (Q3)** — added 2026-09-15. For a P-channel **high-side** switch, biasing OFF means V_GS = 0, so the gate ties to its own **source**, not to ground. Without them nothing held the pack off the converters through power-up |
| **E1** | 1 | TDK-Lambda **`CN150B110-12/CO`** | 📦 | **127.88** | ✅ Paid 09-10, **received 09-18** (Mouser 967-CN150B110-12/CO) **+ $31.97 tariff = $159.85.** `/CO` = factory conformal coating (EN 50155) on the internal board — cannot be retrofitted; +$14.78 over the uncoated $113.10, taken because the bike condensation-cycles. ⚠️ **160 V is a hard ceiling, transients included.** ⬜ **Now in hand, so check:** the baseplate mounting face is **bare metal** (thermal path to E5, baseplate ~82 °C) and that E5 fits (see E5) |
| **E2** | 1 | Cincon **`EC7BW-110S05`** | 📦 | **61.66** | ✅ Ordered 09-10, **received 09-18**. 43–160 VDC → 5 V/4 A, 3 kV iso — the logic rail, kept separate so a lamp or horn fault cannot brown out the brain. ⚠️ Meets its EN 50155 EMC rating only *"WITH EXTERNAL FILTER"* — that filter is E7. ⬜ Likely potted, so no coating option as on E1 — confirm by inspection |
| **E3** | 1 | Littelfuse **`KLKD002.T`** 2 A fast | 📦 | **26.44** | ✅ Paid 09-10, **received 09-18** (DK 5666-KLKD002.T-ND; `.T` = packaging only). 2 A fast, 600 VAC/**600 VDC**, 50 kA DC. Fits at the module's B+ tap, in E4. ⬜ **Order 2–3 spares** — no substitute exists (Notes) |
| **E4** | 1+2 | Mersen **`FEB-11-11`** + 2× **`FSB1`** boots | 📦 | **58.49** | ✅ Paid 09-10 (DK 2378-FEB-11-11-ND) + 2× `FSB1` boots, ⬜ price. **Holder and both boots received 09-18.** Verified **600 VAC/DC**, 10×38, free-hanging inline, crimp, UL Recognized, 100 kA SCCR, 3 captive O-rings, 155 °C, tulip clips. ⚠️ **Boots are required** — the non-breakaway holder ships without them (*"non-breakaway units do not include insulator boots"*); the O-rings seal the fuse compartment, the boots seal the terminations. ⬜ **Also tape-wrap** — Mersen: *"due to varying wire insulation sizes it is suggested that tape wrap be utilized for best results."* On 12 AWG, tape or a light adhesive-shrink over the boot. ⚠️ **Terminal `11` = Cu crimp #8–#12 → 12 AWG minimum on a 0.62 A tap** — buy wire and crimp tool to match. Not `FEB-11-11-BA` ($128.19, utility breakaway, *"pole knockdown"*) |
| **E5** | 1 | TDK **`HAQ-10T`** heatsink | 📦 | **25.66** | ✅ Paid 09-10, **received 09-18** (DK 285-HAQ-10T-ND). ◐ **Fit ~85% confident, not primary-sourced:** DigiKey's *"HEAT SINK FOR CNA30-100"* is a tagline, not an exclusivity claim; TDK lists HAQ-10T as related for the **CN-B110** series incl. **CN150B110**, and its **57.9 × 36.8 mm** is the standard quarter-brick footprint. 7.5 °C/W, 25 mm transverse fins, screw mount. TDK's sites 403 from this machine. ⬜ **E1 and E5 are both in hand: offer the heatsink to the baseplate.** The hole pattern and footprint settle the fit directly. `cn-b_e.pdf` (in Downloads) still settles the `/CO` derating |
| **E6** | 2 | Schurter **`FAC 0031.3803`** holders | 📦 | **9.78** | ✅ Paid 09-10, **received 09-18** (2 @ $4.89, DK 486-1257-ND). DigiKey lists **400 V/16 A** vs the 600 VAC/VDC UL figure — IEC/VDE vs UL ratings; 400 V is ample for 84 V. 1 used (DC-DC #2, with E11); the `KLKD002` upstream covers DC-DC #1, so the 2nd is a spare |
| **E7** | 2 | Würth **`7448022010`** choke | 📦 | **17.84** | ✅ Paid 09-10, **received 09-18** (2 @ $8.92, DK 732-13589-ND). ⚠️ **Two, not one:** TDK requires a choke per supply input, before the bulk cap; Cincon's EC7BW meets EN 50155 *"WITH EXTERNAL FILTER"* only. 10 mH, 2 A @ 70 °C, AEC-Q200, at 29% of rating |
| **E8** | 2 | Chemi-Con **`EKXJ221ELL221MM25S`** (KXJ, 220 µF / **220 V**) | 📦 | **8.02** | ✅ Paid 09-10, **received 09-18** (2 @ $4.01, DK 565-EKXJ221ELL221MM25S-ND — *"CAP ALUM 220UF 20% 220V RADIAL"*). Meets the plan's ≥220 µF / 200 V requirement with margin; same `MM25S` 18 × 25 mm size as the 200 V `EKXJ201…`. ⚠️ **Two are needed, different nodes** — TDK's EMC bulk at DC-DC #1's input, hold-up behind the diode at #2; **440 µF total downstream of D13, which is what the SOA figure turns on** |
| **E9** | 4 | **Vishay `VY2472M49Y5US6`** Y2 4700 pF | ✅ | ~2 | Verified from Vishay's datasheet: 4700 pF ±20% (M), **12.5 mm body**, Y5U. *"Class X1, 440 VAC, Class Y2, 300 VAC"*, **IEC 60384-14**, and an explicit **`1000 VDC`** rating — ours is a DC application (84 V rail → baseplate), ~12× margin. Test 2600 VAC/2 s. IEC/UL/DIN-VDE/CSA/CQC, UL 94 V-0, IR ≥ 10 000 MΩ. **−40…+125 °C — needed: they sit at DC-DC #1's input terminals beside a ~82 °C baseplate.** Why Y-class (not the voltage): they bridge +Vin/−Vin to the **baseplate** → heatsink → enclosure, and the module grounds at the controller's B− stud, so **a short-failure would put the 84 V rail on the enclosure**; IEC 60384-14 certifies a safety cap against exactly that. A plain 2 kV ceramic is the wrong part. ⚠️ The trailing `###` selects packaging (DK `…TV0`, Mouser `…TV7`). ⬜ **4 × 12.5 mm discs is real carrier-board area** — note before layout |
| **E10** | 1 | **`1N4007`** | ~ | ~0.15 | Hold-up blocking diode |
| **E11** | 1 | **Schurter `0001.2504`** 1 A T-lag | 📦 | **4.93** | ✅ Paid 09-10, **received 09-18** (5 @ $0.986, DK 486-1782-ND). Listing: *"1A 250VAC 300VDC 5X20"*. 1 fitted on DC-DC #2 per Cincon's datasheet, **4 spare** — bring-up will blow one. ⚠️ **Order SPT by part number** — the glass `FST` and ceramic `SP` are the same size with **no DC rating at all** |
| **E12** | **3** | **`SMCJ90A`** TVS | ✅ | ~1.41 | ⚠️ Not `SMBJ90A` / `SMBJ100A` / `5KP90A`. ⭐ **Qty 1 → 3 (2026-09-15):** the input TVS, plus **`D104` on `KEY_SW_OUT` and `D105` on `FD_KEY`** — both 84 V wires leaving the box, previously unprotected (HVIN's only TVS was on B+). Same part, already proven for this node |
| **E13** | 2 | IXYS **`IXTP26P20P`** TO-220AB + zener | ⬜ | ~6 | Chosen on **SOA: 363 W @ 5 ms**. Not `FQP12P20` (no SOA plot). **Two: D13's module switch and Q3, the start latch's KEY switch (plan §3.2.5a)** |
| **E14** | 1 | 330 k / 10 k divider | ⬜ | — | KEY sense, 84 V → 2.47 V |
| **E16** | 1 | Carrier PCB + **metal** enclosure | ⬜ | ~30 | ⚠️ Metal, never proto board — conduction-cooled bricks. ⬜ No part chosen |
| **F** | — | Display power switch | ⏸️ | — | **Parked with D11/D19 — not in this order** |
| **G1** | 10 | **1N4148** small-signal diode | ⬜ | ~1 | Brake circuit steering diodes D1L/R · D2L/R · D3L/R + 4 spare (`revv1-brake-circuit.md` §3; plan board G). ⚠️ Silicon, **not Schottky** — a Schottky's reverse leakage reaches the 3.3 V inputs when hot |
| **G2** | 2 | **`AO3407A`** P-channel MOSFET, −30 V, **±20 V gate** | ⬜ | ~1 | Q1, the hardware brake-lamp switch (plan D23), + 1 spare. SOT-23 — same adapter as D3 (X6). A ±12 V-gate part is marginal on the 12 V rail |
| **G3** | 4 | 10 kΩ ¼ W | ⬜ | ~0.5 | R1 — Q1's gate pull-up to +12 V, which is also the lever's wetting current · R3L / R3R — the IN-05/06 pull-ups to 3.3 V · R4 — the run/off toggle's pull-up from `ACC+` (§2.1) |
| **G6** | 2 | 100 Ω · 100 kΩ ¼ W | ⬜ | ~0.5 | R5 / R6 — gate series and gate-to-ground for **Q2**, the run/off toggle's inverter (§2.1). Q2 itself is an `AO3400A` from **D3** |
| **G4** | 1 | 100 nF ceramic | ⬜ | ~0.5 | C1 — `BL` ↔ B− at the controller (EMI) |
| **G5** | 1 | 1 A automotive mini-blade (ATM) fuse + inline holder | ⬜ | ~2 | F1 — the brake-lamp feed; the STOP lamp draws 0.12 A (M5) |
| **H1** | 1 | **`74HC14`** Schmitt inverter, DIP-14 | ⬜ | ~1 | Start latch (plan §3.2.5a): clean threshold for the ~2 s RC, and spare gates for the latch itself. Runs off the 5 V logic rail |
| **H2** | 2 | **`BSS126`** N-channel, 600 V, SOT-23 | ⬜ | ~1.5 | Pulls Q3's gate down from the latch; 1 spare. SOT-23 (adapter: X6). ⚠️ A 30 V part (`AO3400A`) will not stand off the 84 V node |
| **H3** | — | RC + latch passives: 1 MΩ, 2.2 µF film, 100 kΩ ×2, 10 kΩ ×2, 15 V zener | ⬜ | ~2 | ⬜ Final RC values set on the bench to land on ~2 s at the Schmitt's threshold |
| **X6** | 20 | Cermant **SOT23-6 / SC70-6 → DIP** breakout boards | 📦 | **8.49** | ✅ Paid 09-10, received (Amazon). **The breadboard adapter for every SOT-23 part on the BOM.** Use the **SOT23-6 side (0.95 mm)**, never the SC70-6 side (0.65 mm). **C2** fits it directly — Nexperia: *"SOT457 (also referred to as SOT23-6)"*. A **3-lead SOT-23** (D3 `AO3400A`, G2 `AO3407A`, H2 `BSS126`) sits on **pads 1, 3 and 5**: lead 1 → pad 1, lead 2 → pad 3, lead 3 → pad 5. Fitted: C2 ×6 · D3 ×6 · G2 ×1 · H2 ×1 = **14 of 20** |
| **X7** | 4 | **HTSSOP-28 exposed-pad → DIP-28 adapters** for D1 | ⬜ | ~30 | Chip Quik / Proto Advantage **`2200235`** (*"TSSOP-28-Exp-Pad to DIP-28, 0.65 mm"* — the **Exp-Pad** variant is the one that matters); ⬜ **confirm it routes the pad to a pin or via array, or the thermal path is lost** (their site 403s from here). **Buy 4** — a failed mount can take the adapter. Also on Amazon (`B00JU3IXLQ`). ⬜ **Price unverified** — ~$7.50 each assumed; the vendor sites 403 from here. The SOT-23 parts go on X6 |
| **X1** | 2 | **Bar-to-box cable + connectors** | ⬜ | ~15 | ~10 lines per side. ⚠️ Not the same as X5's enclosure glands |
| **X2** | — | FR4 **plated** proto board + stripboard | ⬜ | ~15 | ⚠️ Not phenolic/FR2 — pads lift under vibration |
| **X3** | 10 | M3 brass heat-set inserts | ⬜ | ~8 | ⚠️ Not screws self-tapped into plastic |
| **X4** | — | 3D-printed housing | ⬜ | ~5 | ⚠️ PETG min, ASA preferred — **never PLA** |
| **X5** | — | Glands, strain relief, coating | ⬜ | ~20 | Printed walls wick water along layer lines |

**Not on this BOM:** `BSS138` for the boost line — an `AO3400A` from D3 covers it (30 V is ~2.5× the 3.3–12 V pull-up plan §7.1 states; 48 mΩ vs 6 Ω max, 5.7 A vs 220 mA; one FET type across all low-side channels — ⚠️ but meter the wire first, Notes) · status screen (plan D17) · 4 momentary buttons (plan D3) · `TPIC6B595` · a brake-sense divider — the brake circuit feeds IN-05/06 through G1's diodes with G3's 10 kΩ pull-ups.

---

## Order history

| Date | Order | Lines | Paid | State |
|---|---|---|---|---|
| pre-09 | **Owned stock** | **A1** DevKitC-1 `WROOM-1-N8` (v1.0) · **B1** `SN65HVD230` breakouts ×3 · **B2** 120 Ω (on breakout) | — | 📦 In hand. ⚠️ B1's vendor/PN never recorded — 120 Ω fitted, no `Rs` pin |
| pre-09 | ElectroCookie `B07ZYNWJ1S` / `B082KYCJXJ` proto boards | — | — | 📦 Spares — generic FR4 (**X2**) is used instead |
| **09-10** | **Amazon** | **X6** Cermant SOT23-6 / SC70-6 → DIP ×20 | **$8.49** <br>+ $0.57 tax = **$9.06** | 📦 Received |
| **09-10** | **DigiKey — 10 lines** (SO 101547984) | **C2** ×20 · **C3** ×4 · **D1** ×4 · **D3** ×10 · **E2** · **E3** · **E5** · **E6** ×2 · **E7** ×2 · **E8** ×2 | **$182.96** <br>+ $8.49 ship · $14.68 tax · **$26.09 tariff** = **$232.22** | 📦 **Received 09-18** |
| **09-10** | **Mouser** | **E1** TDK `CN150B110-12/CO` | **$127.88** <br>+ **$31.97 tariff** | 📦 **Received 09-18**. 25% tariff |
| **09-10** | **DigiKey — fuse pair** | **E11** `0001.2504` ×5 · **E4** `FEB-11-11` | **$63.42** | 📦 **Received 09-18** |
| **09-10** | **Boots** | **E4** `FSB1` ×2 | ⬜ | 📦 **Received 09-18**. ⚠️ Utility channel, not DigiKey |
| **09-11** | — | **A3** bar-mount switch sets ×2 | ⬜ | ◐ **LEFT received, harnessed, working.** ⏳ Right pod in transit — it has the lighting slider |

**Committed: $382.75** (+$31.97 tariff on the Mouser line). ⬜ Prices still to log: **E4**'s boots, **A3**.

## Notes

- **Reasoning lives in `revv1-esp32-module-plan.md`**, not here — §3.2 power/D13 · §4 interface classes
  and the wetting-current rule · §6 outputs · §9.5 sourcing · §8 the decision table.
  ⚠️ **Change a part here first**, then the plan section that carries its reasoning.
- ⬜ **Not yet checked against what is already on the shelf** — the BOM was built from what the docs
  specify. Likely candidates: A2 socket strips · D7 screw terminals · D3 FETs · the passives (B3, C1, D2,
  D9, E14, G1, G3, G4). A shelf pass cuts both cost and price-hunting.
- ⚠️ **D1 is the hardest mount on the BOM.** `TPS4H160BQPWPRQ1` is **28-HTSSOP, 0.65 mm pitch, with an
  exposed thermal pad** carrying the heat of 7 current-limited channels, and **the pad must reach real
  copper or the per-channel current limiting and thermal shutdown will not behave as specified.**
  ⬜ Decide how D1 is mounted before the boards are laid out; solder a spare to an X7 adapter first and
  prove the technique before committing the two that go in the build. *(Plan §9.1 covers what may and
  may not sit on a breadboard.)*
- **Specs come from the manufacturer PDF (`pdftotext`), never a web-fetch summary** — the summary got C2's
  polarity and pitch wrong (plan §12).
- ⚠️ **Meter the boost wire before connecting a 30 V FET to it.** §7.1's *"3.3–12 V pull-up inside the
  controller"* is unsourced, and the candidate wire (`CruisePin` PIN17) has never been metered.
  ⛔ **The same 30-pin harness carries pink `60VC` at 72–84 V** — landing on it destroys any low-voltage
  FET, so this is a measurement, not a part choice. Fallback if it reads high: the **PC817** output
  plan §6 offers for the boost line. Procedure: `revv1-inputs-bench-session.md` §7, C1.5.
- ⛔ **Fuse and holder part numbers look interchangeable and are not.** For anything fuse-related, read
  the datasheet's **fuse-type line and the ordering-table footnotes** before the price. Three that looked
  right: Schurter **`FST`** (same 5×20 size, glass, **no DC rating**) · Schurter **`SP`** (ceramic,
  fast-acting, high-breaking — **no DC rating anywhere**) · Littelfuse **`01500330HXU`** (looked like
  E3's holder; actually **6.3×32 mm 3AG**, **IP40**, *"certifications do not apply"*).
- ⚠️ **Tariffs are in no figure here.** Mouser added **$31.97 (25%)** on E1's $127.88, and DigiKey order
  101547984 added **$26.09**. Treat every all-in number as **ex-duty**.
- **Holders and elements are one purchase:** E3 + E4 (inline, B+ tap) and E6 + E11 (PCB, DC-DC #2).
  Neither works half-bought — including when reordering spares.
- ⚠️ **E3 has no spares and no substitute.** A 2 A fast-blow at **600 VDC / 50 kA DC** is a narrow part —
  Schurter has **no** fast-acting 5×20 with any DC rating. A bring-up wiring error will pop it, and a
  hardware-store fuse is not a stand-in on an 84 V pack. ⬜ **Order 2–3 spares.**
- ⬜ **Save the TDK CN-B datasheet into `fardriver/reference/`** — source
  `sg.lambda.tdk.com/wp-content/uploads/cn-b_e.pdf` (TDK's sites 403 from this machine; a copy is in
  Downloads). While it is open, check whether TDK publishes the **same derating curve for `/CO`** as for
  the uncoated part — coating adds a little internal thermal resistance, and E1's baseplate runs ~82 °C.
- **Not in this BOM:** the bike's own parts — wheel, tyres, controller, battery, Class T fuse and block,
  torque arms. Those are in the build sheet's order tracker.
- **Totals are summed from the rows:** committed = the 14 paid rows; estimated = the 29 `~` rows, with A3
  at the low end of its range. E12's verified price (now ~$1.41 for qty 3) is in neither.
- **D23 — the brake light is hardware (decided 2026-09-11).** The STOP lamp is switched by the brake
  circuit's Q1 (group G), not a `TPS4H160B` channel, so D1 serves 6 lighting channels, D2 is 6, C1 is
  10, and IN-05/06 take G3's 10 kΩ pull-ups. Only milliamps flow through the lever switch, so any lever
  type that passes **M3** works (`revv1-brake-circuit.md` §4).
