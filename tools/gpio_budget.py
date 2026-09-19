"""ESP32-S3-WROOM-1 pin pool, and the design's demand on it.

Two halves, kept apart:

  SILICON AND MODULE FACTS live here and nowhere else (tools/rules.py reads
  them from this file). They come from Espressif's datasheets, not from the
  design.

  DEMAND is never typed. `demand(design)` reads every `Net.gpio` tag in the
  netlist and works out from the copper what each net is: what it drives,
  whether it is analog, where it leaves. A hand-kept demand table is a second
  source of truth, and it drifts.

⛔ The `ESP32-S3-WROOM-1` / `-1U` module has NO pad for GPIO33 or GPIO34 --
they exist on the silicon only. The pool on the custom board is 30.

    python3 -m tools.gpio_budget        # the budget for netlist.current()
"""
import re
import sys
from dataclasses import dataclass

from .model import Design

# --- silicon (ESP32-S3 datasheet) ----------------------------------------------
EXISTS = frozenset(range(0, 22)) | frozenset(range(26, 49))   # GPIO22-25 do not exist
FLASH = frozenset(range(26, 33))       # in-package SPI flash
USB = frozenset({19, 20})              # native USB D-/D+: the recovery path
STRAPPING = frozenset({0, 3, 45, 46})  # sampled at reset to choose the boot mode
BOOT_LOG = 43                          # U0TXD: the ROM prints on it at every reset
ADC1 = frozenset(range(1, 11))         # ADC2 is dead while WiFi is on
#: Pins that come out of reset with a weak pull (datasheet v2.2 Table 2-1,
#: "After Reset"): pull-ups on GPIO0, GPIO20 (USB_PU), GPIO39 (MTCK: note 7,
#: while EFUSE_DIS_PAD_JTAG = 0) and U0TXD/U0RXD (43/44); pull-downs on GPIO45
#: and GPIO46.  Until firmware reconfigures the pin, that pull drives whatever
#: the pin is wired to -- a ~45 kΩ pull-up beats a TPS4H160's 100-250 kΩ input
#: pull-down through a 4.7 kΩ series resistor.
RESET_PULL_UP = frozenset({0, 20, 39, 43, 44})
RESET_PULL_DOWN = frozenset({45, 46})

# --- module (ESP32-S3-WROOM-1 datasheet, pin table) ------------------------------
NOT_BROUGHT_OUT = frozenset({33, 34})  # no pad on the WROOM-1 / -1U

#: What a signal may be given.
POOL = EXISTS - FLASH - NOT_BROUGHT_OUT - USB - STRAPPING
#: Of the pool, the pins that may drive something. GPIO43 chatters at reset,
#: so whatever it drove would chatter with it.
DRIVER_POOL = POOL - {BOOT_LOG}
#: Of the pool, the pins the ADC can use with WiFi running.
ADC1_POOL = ADC1 & POOL

#: Nets the firmware samples with the ADC. That is a firmware fact the copper
#: cannot show, so it is stated -- once, here. A net that reaches a driver
#: IC's `CS` (current-sense) pin is analog whatever it is called.
ANALOG_NETS = frozenset({"CS1", "CS2", "KEY_SENSE", "V12_SENSE", "AMBIENT"})

_SERIES_KINDS = ("R", "L", "FUSE")
_FET_KINDS = ("NFET", "PFET")


@dataclass(frozen=True)
class Signal:
    """One GPIO-tagged net and what the copper says about it."""
    net: str
    gpio: int
    #: FET gates and IC pins it reaches, directly or through series parts.
    loads: tuple[str, ...]
    #: Connectors it reaches: (refdes, name, leaves_box, interface).
    connectors: tuple[tuple[str, str, bool, str | None], ...]
    analog: str          # why it is analog; "" if it is not
    #: Every net in its reach, itself included.
    nets: tuple[str, ...]

    @property
    def leaves_box(self) -> bool:
        return any(leaves for _, _, leaves, _ in self.connectors)


def _is_mcu(part) -> bool:
    return "ESP32" in part.mpn.upper()


def _stiff(parts: dict, net) -> bool:
    """A supply or a return. A walk never passes through one -- otherwise a
    pull-up would connect every signal to every IC's supply pin."""
    if net.domain == "GND":
        return True
    kinds = [parts[ref].kind for ref, _ in net.pins if ref in parts]
    # A converter's terminal, or bulk + bypass. A signal has one filter cap.
    return "CONVERTER" in kinds or kinds.count("C") >= 2


def _reach(d: Design, parts: dict, start) -> list:
    """`start` plus every net joined to it through series parts (R, L, fuse),
    fitted or DNP, stopping at supplies."""
    seen, queue = {start.name: start}, [start]
    while queue:
        net = queue.pop()
        for ref, _ in net.pins:
            part = parts.get(ref)
            if part is None or part.kind not in _SERIES_KINDS or len(part.pins) != 2:
                continue
            for other in d.nets_of(ref):
                if other.name not in seen and not _stiff(parts, other):
                    seen[other.name] = other
                    queue.append(other)
    return list(seen.values())


def demand(d: Design) -> tuple[Signal, ...]:
    """Every GPIO-tagged net, in GPIO order."""
    parts = {p.refdes: p for p in d.parts}
    conns = {c.refdes: c for c in d.connectors}
    out = []
    for net in d.nets:
        if net.gpio is None:
            continue
        m = re.fullmatch(r"GPIO(\d+)", net.gpio)
        if not m:
            raise ValueError(f"net {net.name!r}: gpio tag {net.gpio!r} is not 'GPIOn'")
        loads, reached, analog = [], [], ""
        reach = _reach(d, parts, net)
        for n in reach:
            if n.name in ANALOG_NETS and not analog:
                analog = f"{n.name} is sampled by the ADC"
            for ref, pin in n.pins:
                part = parts.get(ref)
                if part is not None and not _is_mcu(part):
                    if part.kind == "IC" and pin == "CS" and not analog:
                        analog = f"it reads the current-sense pin {ref}.CS"
                    if (part.kind in _FET_KINDS and pin == "G") or part.kind == "IC":
                        loads.append(f"{ref}.{pin}")
                c = conns.get(ref)
                if c is not None:
                    reached.append((c.refdes, c.name, c.leaves_box, c.interface))
        out.append(Signal(net.name, int(m.group(1)), tuple(sorted(set(loads))),
                          tuple(sorted(set(reached), key=lambda r: r[0])), analog,
                          tuple(sorted(n.name for n in reach))))
    return tuple(sorted(out, key=lambda s: (s.gpio, s.net)))


def spare(d: Design) -> tuple[int, ...]:
    """Pool pins no net has taken."""
    return tuple(sorted(POOL - {s.gpio for s in demand(d)}))


def report(d: Design | None = None) -> list[str]:
    """Problems with the budget. Empty list means it closes."""
    if d is None:
        from . import netlist
        d = netlist.current()
    signals = demand(d)
    errs = []

    by_gpio: dict[int, list[str]] = {}
    for s in signals:
        by_gpio.setdefault(s.gpio, []).append(s.net)
    for g, nets in sorted(by_gpio.items()):
        if len(nets) > 1:
            errs.append(f"GPIO budget: GPIO{g} is given to {len(nets)} nets "
                        f"({', '.join(sorted(nets))}) -- one pin, one signal")

    for s in signals:
        g, tag = s.gpio, f"{s.net!r} on GPIO{s.gpio}"
        if g not in POOL:
            if g not in EXISTS:
                why = "does not exist on the ESP32-S3"
            elif g in FLASH:
                why = "is wired to the in-package flash"
            elif g in NOT_BROUGHT_OUT:
                why = "has no pad on the WROOM-1 module"
            elif g in USB:
                usb_only = s.connectors and not s.loads and all(
                    "USB" in name.upper() for _, name, _, _ in s.connectors)
                why = "" if usb_only else (
                    "is native USB D-/D+, the recovery path; it may go to the "
                    "USB connector and nowhere else")
            else:                          # strapping
                quiet = not s.loads and not any(
                    leaves or iface for _, _, leaves, iface in s.connectors)
                why = "" if quiet else (
                    "is a strapping pin: whatever it reaches sets the boot mode at "
                    "reset. It may carry its bias parts and the internal service "
                    "header, nothing else"
                    + (f" (reaches {', '.join(s.loads)})" if s.loads else ""))
            if why:
                errs.append(f"GPIO budget: {tag} is outside the pool -- GPIO{g} {why}")
        if g == BOOT_LOG and (s.loads or s.leaves_box):
            what = list(s.loads) + [f"{r} ({name})" for r, name, leaves, _ in s.connectors
                                    if leaves]
            errs.append(
                f"GPIO budget: {tag} drives {', '.join(what)}. GPIO43 prints the ROM "
                f"boot log at every reset and is never a driver")
        if s.analog and g not in ADC1:
            errs.append(
                f"GPIO budget: {tag} is analog ({s.analog}) but GPIO{g} is not on "
                f"ADC1 (GPIO1-10). ADC2 is dead while WiFi is on")

    read = {name for s in signals for name in s.nets}
    for name in sorted(ANALOG_NETS & {n.name for n in d.nets} - read):
        errs.append(f"GPIO budget: {name!r} is sampled by the ADC but reaches no "
                    f"GPIO -- nothing can read it")
    return errs


def main(argv=None, d: Design | None = None) -> int:
    if d is None:
        from . import netlist
        d = netlist.current()
    signals = demand(d)
    print(f"POOL {len(POOL)}   (45 GPIOs - 7 flash - 2 with no WROOM-1 pad - 2 USB "
          f"- 4 strapping)\n")
    for s in signals:
        where = ("pool" if s.gpio in POOL else "USB" if s.gpio in USB else
                 "strap" if s.gpio in STRAPPING else "⛔")
        notes = ["analog" if s.analog else "",
                 f"-> {', '.join(s.loads)}" if s.loads else "",
                 "leaves the box" if s.leaves_box else ""]
        print(f"  GPIO{s.gpio:<3} {where:5} {s.net:22} {'  '.join(n for n in notes if n)}")
    free = spare(d)
    used = len({s.gpio for s in signals} & POOL)
    print(f"\n  {used} of {len(POOL)} pool pins used; spare: "
          f"{', '.join(f'GPIO{g}' for g in free) or 'none'}"
          + ("   (GPIO43 can never drive)" if BOOT_LOG in free else ""))
    errs = report(d)
    for e in errs:
        print("  ⛔", e)
    print("\n" + ("⛔ FAIL" if errs else "✅ PASS -- every signal has its own legal pin"))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
