# CLAUDE.md — FarDriver ESP32 body module

Parent guidance: `../CLAUDE.md` — repo map, conventions, public-repo hygiene, safety rules.

## What this is

Design and BOM stage. `docs/plan.md` is the architecture and the decision log (D1–D24); its header
carries the critical path. `docs/bom.md` **owns procurement** — change a part there first, then the
plan section that line's Notes names.

## ⚠️ The traps that matter most

- **The 84 V pack is above most of the market.** Check the voltage line on every part. Converters need
  **160 V** input; TVS is `SMCJ90A`; 160 V DC is the do-not-exceed including transients.
- **Size input protection at the 60.0 V LVC, not full charge** — converters are constant-power loads.
- **`TPS4H160B` are 40 V parts — 12 V rail only**, never the 84 V node.
- **ESP32-S3 `R8`/`R16V` are rated to 65 °C only.** Use `-N8` (85 °C) or `-H4` (105 °C).
- **No wire leaves the box on strapping pins 0/3/45/46**; analog only on GPIO1–10 (ADC2 dies with WiFi).
- ⛔ **Never enable CAN on this controller** — on non-CAN units the transceiver lands on A11/A12, the
  Hi/Low speed sense lines.

## Safety boundary — do not erode it

**The brake cutoff and brake light are hardware and must stay hardware.** The module only listens. All
lights OFF at key-on, every gate biases OFF, so a hung module drives no lamps. Any derivative should
keep this.

## Parked work

The CAN dash feed is parked (**D19**). Do not resume it unprompted. Parked is not disproven —
everything in the parked documents stays correct.
