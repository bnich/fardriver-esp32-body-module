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
([brake circuit](https://github.com/bnich/Revv1-FS-72v-Conversion/blob/main/docs/brake-circuit.md)):
the stop lamp rides a current-limited smart-switch channel whose input only that hardware drives.
The run/off toggle is the secondary kill (the key switch is the primary), also hardware: it pulls
`BL` low through its own FET. The module only listens, and no firmware state — hung, crashed,
unflashed — can stop either. One dependence remains: **the brake lamp is fed from the module's 12 V
rail**, so an unpowered module means a dark brake lamp. The motor cut needs nothing from the module.
All lights are OFF at key-on and every gate biases OFF, so a hung module drives no lamps.

⚠️ **Starting the bike is not the module's job.** The key switch feeds the FarDriver KEY wire directly;
the module takes one tap off it, on the same plug as the pack, to switch its own supply and to sense
key state. It never sources or switches KEY, and there is no start latch.

---

## ⚠️ The 84 V problem

This is the thing that catches people, and it runs through the whole BOM.

**The pack is above nearly everything the 12/24/48 V market sells.** Check the voltage line on every
single part.

| | |
|---|---|
| **Converters need a 160 V input rating** | TDK `CN150B110-12`, Cincon `EC7BW-110S05` |
| **TVS** | `SMCJ90A` on B+. None on the key tap: it is a high-impedance input, and a TVS there that failed short would cut the FarDriver KEY |
| **Do-not-exceed** | **160 V DC including transients** |
| **Size input protection at the 60.0 V LVC, not at full charge** | Converters are constant-power loads, so current is highest when the pack is lowest. Module draw: **~0.62 A at LVC**, worked out from the 12 V budget — 2.62 A worst case, 1.62 A of it measured ([plan §3.2.3](docs/plan.md)) |
| **`TPS4H160B` smart switches are 40 V parts** | 12 V rail only — **never** the 84 V node. Their `CL` and `CS` pins each need a resistor; TI's pin names are `VS` / `SEL` / `SEH` |
| **Small-signal FET on the 84 V node** | **`BSS127`** (600 V, enhancement-mode). ⛔ Not its sibling `BSS126` — that one is **depletion-mode**, conducting at V<sub>GS</sub> = 0 |
| **Low-voltage TVS parts follow the line's idle voltage** | The 5 V array `SMS05T1G` only on 3.3 V-class lines · the 15 V array `SMS15T1G` on the brake-lever nodes, `BL` / `ACC+` and the boost output · a single-line `SMF18A` on every 12 V lamp and load output, and an `SMBJ18A` on the 12 V rail itself. A 5 V array on a 12 V line is a dead short |
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
4-layer boards** — **HVIN** (84 V entry and soft-start) · **CONV** (both converters) · **DRV** (12 V
drivers and the whole brake circuit) · **BRAIN** (the S3 and the bar inputs) — with every inter-board
interface on the 2.54 mm grid, so a breadboard section can stand in for any one board
([plan §9.2](docs/plan.md)). **Carry the pin *rules* to the custom board, not the GPIO numbers.**

---

## Where the design stands

The board set exists as a checked netlist ([`tools/netlist.py`](tools/netlist.py)) and a generated
EasyEDA Pro project. No board is laid out yet.

- **Power.** Two isolated converters behind the soft-start switch: a TDK brick for the 12 V loads
  (2.62 A worst case) and a Cincon module for the 5 V logic, kept apart so a lamp or horn fault cannot
  brown out the brain. **No raw 12 V leaves the box:** every lamp is a `TPS4H160B` channel
  (current-limited, with open-load and fault reporting), and horn, fan and buzzer share one more such
  channel and are switched on their return. BRAIN takes no 12 V; USB VBUS is sensed, never a supply.
- **Harness.** Every wire enters on a locking pluggable screw terminal, in three families by job —
  7.62 mm for pack voltage (one connector), 5.08 mm for the brake levers and the FarDriver brake/kill,
  3.81 mm for the rest — so a plug of one job cannot seat in a header of another, and every
  safety-relevant terminal has a size nothing else in its family shares
  ([BOM](docs/bom.md) X8, X9, X11).
- **Assembly.** JLC places everything but the two converters and the two input chokes, which are
  hand-soldered, and the parts that must lie flat or clip in, which are ordered loose with the boards
  ([BOM](docs/bom.md#jlc-assembly--the-custom-boards)).
- ⚠️ **The fit does not close.** `python3 -m tools.board_fit` derives the stack at **77.7 mm against
  64.0 mm available** — above even the raw 70 mm cavity estimate, so no enclosure choice can absorb
  it; only a taller measured cavity (M18) or a shorter stack can. DRV's top side does not fit its
  board (the naive pack needs 212 mm of its 186 mm), and the harness plugs need more room to the wall
  than the estimated envelope leaves. All three verdicts are provisional until M18 is measured and the
  all-metal enclosure is modelled, and none of them is a pass.
- ⬜ **The EasyEDA project must be re-proven.** Each board has to be re-imported, its netlist
  re-exported from the editor and proven identical with `python3 -m tools.tel_check`; no board of
  the current netlist has been proven yet.
- ⬜ **The inter-board connector family is open**, and the mated pair sets each board gap.

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
| [**docs/bom.md**](docs/bom.md) | Bill of materials and order tracker. **This owns procurement** — change a part here first, then the plan section its Notes names. It also says what JLC places, what is ordered loose and what you hand-solder |
| [**docs/inputs-bench-session.md**](docs/inputs-bench-session.md) | Bench procedure and results for the switch sets, brake-lever wires, lever switch type, red button, serial direction and KEY tap |
| [**tools/**](tools/README.md) | Design-time tooling, stdlib Python. `tools/netlist.py` **is** the board set — parts, nets, connectors, board assignment — and the checks below gate every change to it |

```bash
python3 -m tools.integrity     # structural gate: every pin of every part lands somewhere
python3 -m pytest              # the rule and unit tests
python3 -m tools.board_fit     # area, height and plug-room budget: currently FAILS (see above)
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
