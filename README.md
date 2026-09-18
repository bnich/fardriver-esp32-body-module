# FarDriver ESP32 body module

An **ESP32-S3 body control module** for an electric vehicle running a FarDriver controller on a 72 V
(84 V full) pack. It takes over lighting, turn signals, horn and boost, listens to the controller's
serial link, and serves a status page over WiFi.

Built for a Ride1Up REVV1 FS converted to a 5 kW hub motor
([`Revv1-FS-72v-Conversion`](https://github.com/bnich/Revv1-FS-72v-Conversion)), but the power design
and the FarDriver interfacing are not specific to that bike.

> 🚧 **Design stage — no firmware yet, no module hardware built.** Here: the plan, the bill of
> materials, the bench measurements, and the design-time tooling that holds the custom board set as a
> checked netlist ([`tools/`](tools/README.md)). The left bar pod is wired and tested. Bench firmware
> for the display protocol belongs to a companion repository that is not yet published (see below).

---

## What it does

| | |
|---|---|
| **Lighting** | 3-position slider + high/low toggle, both plain dry contacts. A rear momentary button is flash-to-pass |
| **Turn signals** | Push-push latching buttons that self-centre, so the switch shows no state — the module **auto-cancels** (20 s above 15 km/h, or 60 s regardless). A dedicated hazard control |
| **Horn** | 12 V electronic horn, 0.10 A |
| **Boost** | The throttle's red button → module → FarDriver boost input, hold or toggle |
| **Readout** | **A WiFi status page** — motor and controller temperature, bus current, boost mode, lamp-out. The module has **no screen of its own** |

The module takes each function over **one at a time**, as each is built and wired.

⚠️ **The brake light and motor cutoff do not depend on firmware.** Each lever pulls the FarDriver
`BL` low and switches the brake lamp through hardware
([brake circuit](https://github.com/bnich/Revv1-FS-72v-Conversion/blob/main/docs/brake-circuit.md)).
The module only listens, and no firmware state — hung, crashed, unflashed — can stop either. One
dependence remains: **the brake lamp is fed from the module's 12 V rail**, so an unpowered module means
a dark brake lamp. The motor cut needs nothing from the module. All lights are OFF at key-on and every
gate biases OFF, so a hung module drives no lamps.

⚠️ **Starting the bike is not the module's job.** The key switch feeds the FarDriver KEY wire directly;
the module takes one tap off it to switch its own supply and to sense key state. It never sources or
switches KEY, and there is no start latch.

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
| **`TPS4H160B` smart switches are 40 V parts** | 12 V rail only — **never** the 84 V node. Their `CL` and `CS` pins each need a resistor; TI's pin names are `VS` / `SEL` / `SEH` |
| **Small-signal FET on the 84 V node** | **`BSS127`** (600 V, enhancement-mode). ⛔ Not its sibling `BSS126` — that one is **depletion-mode**, conducting at V<sub>GS</sub> = 0 |
| **TVS arrays follow the line's voltage** | `PESD5V0S4UD` (5 V) only on 3.3 V-class lines; 12 V-class lines and the brake-lever nodes take a 15 V array (`SMS15T1G`). A 5 V array on a 12 V line is a dead short |
| **Fuses** | Schurter **`FST`** (glass) and **`SP`** (ceramic fast-acting) 5×20 have **no DC rating**. Only time-lag **`SPT`** does. Order by part number. A fuse holder has no breaking capacity |

**Module ground stars at the controller's B− stud**, not the battery's.

---

## ⚠️ ESP32-S3 specifics

- **`R8`/`R16V` modules are rated only to 65 °C.** Use **`-N8`** (85 °C) or `-H4` (105 °C). An
  under-seat cavity on a dark vehicle exceeds 65 °C.
- **No wire leaves the box on strapping pins 0/3/45/46.**
- **Analog only on GPIO1–10** — ADC2 dies when WiFi is on.
- **The `ESP32-S3-WROOM-1` module has no IO33 or IO34 pads.** On a custom board the clean GPIO pool
  is **30**, not 32.
- **`ESP32-S3-WROOM-1` and `-WROOM-1U` share one footprint.** The `-1U` takes an external antenna, which
  matters because a metal enclosure — or a metal cavity — kills a PCB antenna.
- **`MCP23017` pins GPA7 and GPB7 are output-only** — a 16-bit expander offers 14 inputs.
- Prototype is an ESP32-S3 DevKitC-1 **v1.0** (RGB LED on GPIO48) with an `ESP32-S3-WROOM-1-N8`.
- ESP-IDF **v5.5**.

Construction path: breadboard → FR4 plated perfboard → custom PCB. The custom build is **four stacked
boards** — **HVIN** (84 V entry and soft-start) · **CONV** (both converters) · **DRV** (12 V drivers
and the whole brake circuit) · **BRAIN** (the S3 and the bar inputs) — with every inter-board interface
on 2.54 mm pitch, so a breadboard section can stand in for any one board
([plan §9.2](docs/plan.md)). **Carry the pin *rules* to the custom board, not the GPIO numbers.**

---

## ⚠️ Never enable CAN on a non-CAN FarDriver

On non-CAN units the CAN transceiver lands on **A11/A12 — the Hi/Low speed sense lines.** The module
impersonates a CAN FarDriver toward the display; the controller itself stays on one-line with
`CANConfig` = `None`.

---

## Documents

| | |
|---|---|
| [**docs/plan.md**](docs/plan.md) | The module plan — architecture, decisions (D1–D24), pin map, power design, the four-board partition (§9.2), per-function takeover. The critical path is in its header |
| [**docs/bom.md**](docs/bom.md) | Bill of materials and order tracker. **This owns procurement** — change a part here first, then the plan section its Notes names |
| [**docs/inputs-bench-session.md**](docs/inputs-bench-session.md) | Bench procedure and results for the switch sets, brake-lever wires, lever switch type, red button, serial direction and KEY tap |
| [**tools/**](tools/README.md) | Design-time tooling, stdlib Python. `tools/netlist.py` **is** the board set — parts, nets, connectors, board assignment — and the checks below gate every change to it |

```bash
python3 -m tools.integrity     # structural gate: every pin of every part lands somewhere
python3 -m pytest              # the rule and unit tests
```

## Related

Two companion repositories are **not yet published**; the plan cites documents that belong to them.

| | |
|---|---|
| **chaojie-display-protocol** | Talking to the Chaojie panels — pinouts, the one-line protocol, CAN 18, and the ESP32 bench firmware |
| **fardriver-nd72450-reference** | `.heb` parameter decoder and the controller's harness pinout |

## Licence

**[MIT](LICENSE) — for everything in this repository:** firmware, tooling, the netlist, the hardware
design and the documentation. That is a deliberate choice by the owner. The sibling hardware and
documentation repositories of this build are CC BY-SA 4.0; this one is MIT throughout.

## Disclaimer

This controls the lighting of a 5 kW vehicle from a microcontroller on an 84 V pack. Nothing here has
been tested to any standard. The safety-critical functions — brake cutoff and brake light — are
deliberately **not** in firmware, and should stay that way in any derivative.
