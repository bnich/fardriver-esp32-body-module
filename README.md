# FarDriver ESP32 body module

An **ESP32-S3 body control module** for an electric vehicle running a FarDriver controller on a 72 V
(84 V full) pack. It takes over lighting, turn signals, horn and boost, listens to the controller's
serial link, and serves a status page over WiFi.

Built for a Ride1Up REVV1 FS converted to a 5 kW hub motor
([`Revv1-FS-72v-Conversion`](https://github.com/bnich/Revv1-FS-72v-Conversion)), but the power design
and the FarDriver interfacing are not specific to that bike.

> 🚧 **Design and BOM stage — no firmware yet.** The plan, the bill of materials and the bench
> measurements are here; the module is being built up incrementally on a breadboard. Bench firmware
> for the display protocol lives in a separate repository (see below).

---

## What it does

| | |
|---|---|
| **Lighting** | 3-position slider + high/low toggle, both plain dry contacts |
| **Turn signals** | 3-position switch, **no auto-cancel**, with a dedicated hazard control |
| **Horn** | 12 V electronic horn, 0.10 A |
| **Boost** | The throttle's red button → module → FarDriver boost input, hold or toggle |
| **Readout** | **A WiFi status page** — motor and controller temperature, bus current, boost mode, lamp-out. The module has **no screen of its own** |

The module takes each function over **one at a time**, as each is built and wired.

⚠️ **The brake light and motor cutoff do not depend on this module.** Each lever pulls the FarDriver
`BL` low and switches the brake lamp through hardware
([brake circuit](https://github.com/bnich/Revv1-FS-72v-Conversion/blob/main/docs/brake-circuit.md)).
The module only listens. All lights are OFF at key-on and every gate biases OFF, so a hung module
drives no lamps.

---

## ⚠️ The 84 V problem

This is the thing that catches people, and it runs through the whole BOM.

**The pack is above nearly everything the 12/24/48 V market sells.** Check the voltage line on every
single part.

| | |
|---|---|
| **Converters need a 160 V input rating** | TDK `CN150B110-12`, Cincon `EC7BW-110S05` |
| **TVS** | `SMCJ90A` |
| **Do-not-exceed** | **160 V DC including transients** |
| **Size input protection at the 60.0 V LVC, not at full charge** | Converters are constant-power loads, so current is highest when the pack is lowest. Measured module draw: **~0.62 A at LVC** |
| **`TPS4H160B` smart switches are 40 V parts** | 12 V rail only — **never** the 84 V node |
| **Fuses** | Schurter **`FST`** (glass) and **`SP`** (ceramic fast-acting) 5×20 have **no DC rating**. Only time-lag **`SPT`** does. Order by part number. A fuse holder has no breaking capacity |

**Module ground stars at the controller's B− stud**, not the battery's.

---

## ⚠️ ESP32-S3 specifics

- **`R8`/`R16V` modules are rated only to 65 °C.** Use **`-N8`** (85 °C) or `-H4` (105 °C). An
  under-seat cavity on a dark vehicle exceeds 65 °C.
- **No wire leaves the box on strapping pins 0/3/45/46.**
- **Analog only on GPIO1–10** — ADC2 dies when WiFi is on.
- Prototype is an ESP32-S3 DevKitC-1 **v1.0** (RGB LED on GPIO48) with an `ESP32-S3-WROOM-1-N8`.
- ESP-IDF **v5.5**.

Construction path: breadboard → FR4 plated perfboard → custom PCB. **Carry the pin *rules* to the
custom board, not the GPIO numbers.**

---

## ⚠️ Never enable CAN on a non-CAN FarDriver

On non-CAN units the CAN transceiver lands on **A11/A12 — the Hi/Low speed sense lines.** The module
impersonates a CAN FarDriver toward the display; the controller itself stays on one-line with
`CANConfig` = `None`.

---

## Documents

| | |
|---|---|
| [**docs/plan.md**](docs/plan.md) | The module plan — architecture, decisions (D1–D24), pin map, power design, per-function takeover. The critical path is in its header |
| [**docs/bom.md**](docs/bom.md) | Bill of materials and order tracker. **This owns procurement** — change a part here first, then the plan section its Notes names |
| [**docs/inputs-bench-session.md**](docs/inputs-bench-session.md) | Bench procedure and results for the switch sets, brake-lever wires, lever switch type, red button, serial direction and KEY tap |

## Related

| | |
|---|---|
| [**chaojie-display-protocol**](https://github.com/bnich/chaojie-display-protocol) | Talking to the Chaojie panels — pinouts, the one-line protocol, CAN 18, and the ESP32 bench firmware |
| [**fardriver-nd72450-reference**](https://github.com/bnich/fardriver-nd72450-reference) | `.heb` parameter decoder and the controller's harness pinout |

## Licence

[MIT](LICENSE).

## Disclaimer

This controls the lighting of a 5 kW vehicle from a microcontroller on an 84 V pack. Nothing here has
been tested to any standard. The safety-critical functions — brake cutoff and brake light — are
deliberately **not** in firmware, and should stay that way in any derivative.
