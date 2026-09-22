"""Structural integrity of the netlist -- is it a CIRCUIT at all?

rules.py asks whether the design obeys its safety and pin rules. This module
asks the question underneath that one, which the 2026-09-18 audit showed nobody
was asking: does every leg of every part actually go somewhere?

At the time, all of these were true and every rule was green:
  * two TVS diodes "protecting" 84 V wires had one terminal each
  * the run/off kill FET had no source
  * a zener that clamps a +/-20 V gate had no cathode
  * the 3.3 V rail and the CAN pair "crossed" a connector with no contact
  * nothing joined the lamp returns to ground

None of these needs electrical judgement to find. They need counting.

Deliberately dumb, deliberately independent of rules.py: nothing here trusts a
label. Run it first; a design that fails here is not worth rule-checking.
"""
from collections import Counter, defaultdict
from typing import get_args

from .model import CROSSING, Crossing, Design, is_cabled

#: Pins a part may legitimately leave unconnected, by MPN prefix, each because
#: its DATASHEET says so. A must-tie pin dropped into `nc` makes the "every
#: declared pin lands" check vacuous -- a converter's output return, an enable,
#: a thermal pad -- so `nc` is policed against this list, not trusted.
#: "IO*"/"GP*" are prefixes: any unused GPIO of that part may be left open.
NC_ALLOWED = {
    "CN150B110": {"TRM"},            # TDK: trim open = nominal output
    "EC7BW": {"Trim", "Remote"},     # Cincon: remote is positive logic, open = ON
    "TPS4H160": {"NC"},              # package no-connect pads
    "TLV767": {"NC"},
    # TI SNVSAH5A p.3: RT open IS a setting -- "If floating, the default
    # switching frequency is 500 kHz", which is the frequency the design is
    # sized at, and "Do not short to ground". Its NC pads are not here: they
    # land on GND, because the same page says to connect them to ground copper.
    "LM73605": {"RT"},
    "SN65HVD230": {"Vref"},          # V_CC/2 reference output, unused
    "ESP32-S3-WROOM-1": {"IO*"},     # unused GPIO pads -- never EN, 3V3, GND, EPAD
    "MCP23017": {"GP*", "INTA", "INTB", "NC11", "NC14"},
}


def _nc_ok(mpn: str, pin: str) -> bool:
    for prefix, allowed in NC_ALLOWED.items():
        if mpn.startswith(prefix):
            return pin in allowed or any(
                a.endswith("*") and pin.startswith(a[:-1]) for a in allowed)
    return False


#: The two neighbouring boards each inter-board interface joins, lower first.
#: One interface is ONE crossing: a bus that must reach a third board does so
#: on a second interface, with parts of its own.
INTERFACE_BOARDS = {
    "PWR-OUT": ("POWER", "OUTPUTS"),
    "CTRL": ("POWER", "OUTPUTS"),
    "PWR-LOGIC": ("OUTPUTS", "LOGIC"),
    "STACK": ("OUTPUTS", "LOGIC"),
    "CTRL-STACK": ("LOGIC", "CTRL"),
}


def check(d: Design) -> list[str]:
    errs: list[str] = []
    part_refs = [p.refdes for p in d.parts]
    conn_refs = [c.refdes for c in d.connectors]

    # -- identity -------------------------------------------------------------
    for ref, n in Counter(part_refs + conn_refs).items():
        if n > 1:
            errs.append(f"identity: refdes {ref} is defined {n} times")
    for name, n in Counter(x.name for x in d.nets).items():
        if n > 1:
            errs.append(f"identity: net {name!r} is defined {n} times")

    # -- every (refdes, pin) lands at most once, on a thing that exists --------
    landed: dict[tuple[str, str], list[str]] = defaultdict(list)
    for net in d.nets:
        for ref, pin in net.pins:
            landed[(ref, pin)].append(net.name)
            if ref not in part_refs and ref not in conn_refs:
                errs.append(f"dangling: net {net.name!r} references {ref}, "
                            f"which is neither a part nor a connector")
    for (ref, pin), nets in landed.items():
        if len(nets) > 1:
            errs.append(f"shorted: {ref}.{pin} is on {len(nets)} nets {nets}")

    # -- every declared pin of every part lands; nothing undeclared lands ------
    for p in d.parts:
        if not p.pins:
            errs.append(f"pins: {p.refdes} ({p.mpn}) declares no pins")
        declared, nc = set(p.pins), set(p.nc)
        if declared & nc:
            errs.append(f"pins: {p.refdes} lists {sorted(declared & nc)} as both "
                        f"a pin and a no-connect")
        on = {pin for (ref, pin) in landed if ref == p.refdes}
        for pin in sorted(declared - on):
            errs.append(f"floating: {p.refdes}.{pin} ({p.mpn}) is on no net"
                        + ("  [part is DNP -- its footprint still needs both "
                           "ends]" if p.dnp else ""))
        for pin in sorted(on - declared):
            errs.append(f"undeclared: {p.refdes}.{pin} is netted but "
                        f"{p.refdes} does not declare that pin")
        for pin in sorted(on & nc):
            errs.append(f"pins: {p.refdes}.{pin} is declared no-connect but "
                        f"is on a net")
        for pin in sorted(nc):
            if not _nc_ok(p.mpn, pin):
                errs.append(f"nc: {p.refdes}.{pin} ({p.mpn}) is left unconnected, "
                            f"and no datasheet entry in NC_ALLOWED says that pin "
                            f"may be. A must-tie pin hidden in `nc` floats silently")

    # -- a net is a CONNECTION: one pin alone connects to nothing ---------------
    for net in d.nets:
        if len(net.pins) == 1:
            ref, pin = net.pins[0]
            errs.append(f"floating: net {net.name!r} has one pin ({ref}.{pin}) "
                        f"-- that leg is 'on a net' and still goes nowhere")

    # -- connector tables and nets must tell the same story --------------------
    net_names = {n.name for n in d.nets}
    for c in d.connectors:
        table = {cp.pin: cp.net for cp in c.pins}
        if len(table) != len(c.pins):
            errs.append(f"connector: {c.refdes} lists a pin twice")
        for pin, net_name in table.items():
            if not net_name:
                if (c.refdes, pin) in landed:
                    errs.append(f"connector: {c.refdes}.{pin} is tabled unused "
                                f"but is on net {landed[(c.refdes, pin)]}")
                continue
            if net_name not in net_names:
                errs.append(f"connector: {c.refdes}.{pin} names net "
                            f"{net_name!r}, which does not exist")
            elif (c.refdes, pin) not in d.net(net_name).pins:
                errs.append(f"connector: {c.refdes}.{pin} is tabled as "
                            f"{net_name!r} but that net has no such pin -- "
                            f"the signal does not actually reach the connector")
        for (ref, pin), nets in landed.items():
            if ref == c.refdes and pin not in table:
                errs.append(f"connector: {nets[0]!r} lands on {c.refdes}.{pin}, "
                            f"a contact the connector does not have")

    # -- a net that spans boards must have copper across the gap ---------------
    for net in d.nets:
        boards = {d.board_of(r) for r, _ in net.pins if d.has(r)}
        if len(boards) < 2:
            if net.interface:
                errs.append(f"interface: {net.name!r} claims {net.interface} "
                            f"but sits on one board {sorted(boards)}")
            continue
        refs = {r for r, _ in net.pins}
        bridged: set[str] = set()
        for c in d.connectors:
            if c.interface and c.refdes in refs:
                bridged |= set(INTERFACE_BOARDS.get(c.interface, ())) & {c.board}
        for b in sorted(boards - bridged):
            errs.append(f"interface: {net.name!r} has pins on {b} but no "
                        f"inter-board contact on {b} carries it -- the net "
                        f"spans {sorted(boards)} with a gap in the copper")
        if not net.interface:
            errs.append(f"interface: {net.name!r} spans {sorted(boards)} and "
                        f"names no interface")

    # -- MCU pin label and gpio tag must agree; no GPIO used twice --------------
    gpios = Counter()
    for net in d.nets:
        mcu_pins = [pin for ref, pin in net.pins
                    if ref == "U401" and pin.startswith("IO")]
        if net.gpio:
            gpios[net.gpio] += 1
            want = "IO" + net.gpio.removeprefix("GPIO")
            if want not in mcu_pins:
                errs.append(f"gpio: {net.name!r} is tagged {net.gpio} but lands "
                            f"on U401 pins {mcu_pins or 'NONE'}")
        elif mcu_pins:
            errs.append(f"gpio: {net.name!r} lands on U401.{mcu_pins[0]} with "
                        f"no gpio tag, so no pin rule can see it")
    for g, n in gpios.items():
        if n > 1:
            errs.append(f"gpio: {g} is assigned to {n} nets")

    # -- every interface: two halves, one on each of two neighbouring boards ---
    # The pin tables alone cannot show a missing half: PWR-OUT once ran from
    # POWER to OUTPUTS with no part between them, and J407.1 could be set to GND
    # against J307.1's V12 without a complaint.
    #
    # What is asked of the two halves depends on model.CROSSING. A MATED PAIR
    # must face each other -- lower half on top of the lower board, upper half
    # hanging under the upper one, its land pattern pre-mirrored. A CABLE must
    # not be asked for any of that: the loom carries the orientation (IO-20).
    # ⛔ That is about ALIGNMENT and mirroring, not about which face a half
    # sits on: every half still looks into the gap its crossing spans, which is
    # `board_params`' business and `tests/test_interconnect.py`'s to hold.
    for c in d.connectors:
        if c.interface and c.interface not in INTERFACE_BOARDS:
            errs.append(f"interface: {c.refdes} names {c.interface!r}, which "
                        f"joins no known pair of boards")
    # Guard the TABLE, not each crossing: an interface with no declared kind
    # would quietly inherit the pair rules, and a cable that inherits them is
    # reported for a defect it does not have. The VALUE is held to the literal
    # too: `is_cabled` reads anything that is not exactly "cable" as a pair, so
    # "Cable" would inherit the pair rules the same way (L4).
    for iface in INTERFACE_BOARDS:
        if iface not in CROSSING:
            errs.append(f"interface: {iface} has no entry in model.CROSSING, so "
                        f"nothing says whether it is a mated pair or a cable")
    for iface, kind in CROSSING.items():
        if kind not in get_args(Crossing):
            errs.append(f"interface: model.CROSSING[{iface!r}] is {kind!r}, not one "
                        f"of {get_args(Crossing)} -- is_cabled() reads it as a "
                        f"pair and asks a loom to face and mirror")
    for iface, (lower, upper) in INTERFACE_BOARDS.items():
        halves = [c for c in d.connectors if c.interface == iface]
        lo = [c for c in halves if c.board == lower]
        up = [c for c in halves if c.board == upper]
        stray = [c.refdes for c in halves if c.board not in (lower, upper)]
        if stray:
            errs.append(f"interface: {iface} joins {lower} and {upper}, but "
                        f"{', '.join(stray)} sits elsewhere")
        if not halves:
            continue
        if len(lo) != 1 or len(up) != 1:
            errs.append(f"interface: {iface} needs one half on {lower} and one "
                        f"on {upper}; found {[c.refdes for c in lo]} and "
                        f"{[c.refdes for c in up]}")
            continue
        a, b = lo[0], up[0]
        # Both kinds compare the halves CONTACT BY CONTACT NUMBER -- `cp.pin`,
        # never the position in the table's tuple. ⛔ The cable branch once
        # zipped the two tuples and called position i "contact i": J311
        # re-tabled 5:V12 4:GND 2:V5 1:KEY_SENSE -- a straight loom putting
        # 12 V on KEY_SENSE -- passed, and the same copper with a tuple merely
        # written in another order was reported four times (H9).
        ta = {cp.pin: cp.net for cp in a.pins}
        tb = {cp.pin: cp.net for cp in b.pins}
        contacts = sorted(set(ta) | set(tb), key=lambda x: (len(x), x))
        if is_cabled(iface):
            # Deliberately says NOTHING about sides, facing or mirroring. What
            # a loom cannot survive is ends with different contact numbers, or
            # a conductor that leaves one contact and arrives on another.
            if set(ta) != set(tb):
                errs.append(f"interface: {iface} is a cable, so its two ends "
                            f"must have the same contacts; {a.refdes} has "
                            f"{sorted(ta, key=lambda x: (len(x), x))} and "
                            f"{b.refdes} has {sorted(tb, key=lambda x: (len(x), x))}")
            for pin in contacts:
                if pin in ta and pin in tb and ta[pin] != tb[pin]:
                    errs.append(f"interface: contact {pin} of {iface} carries "
                                f"{ta[pin]!r} on {a.refdes}.{pin} but "
                                f"{tb[pin]!r} on {b.refdes}.{pin} -- a cable "
                                f"is wired contact for contact")
        else:
            if (a.side, b.side) != ("top", "bottom"):
                errs.append(f"interface: {a.refdes} must stand on top of {lower} "
                            f"and {b.refdes} hang under {upper} to face each "
                            f"other; they are {a.side} and {b.side}")
            for pin in contacts:
                if ta.get(pin) != tb.get(pin):
                    errs.append(f"interface: {a.refdes}.{pin} carries "
                                f"{ta.get(pin)!r} but its mate {b.refdes}.{pin} "
                                f"carries {tb.get(pin)!r}")
    return errs


if __name__ == "__main__":
    import sys
    from . import netlist
    problems = check(netlist.current())
    for e in problems:
        print(e)
    print(f"\n{len(problems)} integrity problem(s)")
    sys.exit(1 if problems else 0)
