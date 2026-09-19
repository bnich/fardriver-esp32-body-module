"""The BOM JLC's assembly service reads, written from the netlist.

    python3 -m tools.jlc_bom                  # print the BOM and the hand-solder list
    python3 -m tools.jlc_bom --out bom.csv    # write the CSV to upload

One line per LCSC part, with every designator that uses it. Parts marked
`assembly="hand"` are left off: the owner buys and solders them, and they are
listed separately. DNP parts are left off. The LCSC numbers themselves live in
`netlist.py` (_R_LCSC, _C_LCSC, _FAB_BY_MPN, _FAB_CONN), and nowhere else.
"""
import argparse
import csv
import io
import sys
from collections import defaultdict

from . import netlist
from .model import Connector, Design

HEADER = ("Comment", "Designator", "Footprint", "LCSC Part #")


def _items(d: Design):
    return [x for x in list(d.parts) + list(d.connectors)
            if not getattr(x, "dnp", False)]


def _refkey(ref: str):
    head = ref.rstrip("0123456789AB")
    tail = ref[len(head):]
    digits = "".join(ch for ch in tail if ch.isdigit())
    return head, int(digits or 0), tail


def _describe(x):
    """(Comment, Footprint) for one BOM line: the value for parts bought by
    value, the part number for the rest; a connector by pins and pitch."""
    if isinstance(x, Connector):
        return f"{len(x.pins)}-pin {x.pitch_mm:g} mm connector", f"{x.pitch_mm:g} mm"
    comment = x.value if x.kind in ("R", "C") else x.mpn
    return comment, x.package


def _label(x) -> str:
    return x.name if isinstance(x, Connector) else x.mpn


def bom_csv(d: Design) -> str:
    groups = defaultdict(list)
    for x in _items(d):
        if x.assembly == "jlc" and x.lcsc:
            groups[x.lcsc].append(x)
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(HEADER)
    for code, xs in sorted(groups.items(), key=lambda kv: _refkey(min(r.refdes for r in kv[1]))):
        xs.sort(key=lambda x: _refkey(x.refdes))
        comment, package = _describe(xs[0])
        w.writerow((comment, ",".join(x.refdes for x in xs), package, code))
    return out.getvalue()


def hand_list(d: Design) -> str:
    lines = []
    for x in sorted(_items(d), key=lambda x: _refkey(x.refdes)):
        if x.assembly == "hand":
            why = x.source.split("HAND-SOLDERED:", 1)[-1].strip()
            lines.append(f"{x.refdes:7} {_label(x)[:24]:24} {why}")
    return "\n".join(lines)


def plug_list(d: Design) -> str:
    """The loose screw plugs: ordered with the boards, not placed, wired by
    the owner.  One line per plug part."""
    by_plug = {}
    for c in d.connectors:
        if c.plug:
            by_plug.setdefault(c.plug, []).append(c)
    lines = []
    for plug, cs in sorted(by_plug.items(), key=lambda kv: _refkey(kv[1][0].refdes)):
        refs = " ".join(c.refdes for c in sorted(cs, key=lambda c: _refkey(c.refdes)))
        lines.append(f"{plug:8} x{len(cs)} {len(cs[0].pins)}-position "
                     f"{cs[0].pitch_mm} mm screw plug, for {refs}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", help="write the BOM CSV here")
    a = ap.parse_args(argv)
    d = netlist.current()
    text = bom_csv(d)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print(f"wrote {a.out}: {len(text.splitlines()) - 1} LCSC parts")
    else:
        print(text, end="")
    pending = [x.refdes for x in _items(d) if not x.lcsc and x.assembly != "hand"
               and getattr(x, "mpn", "") != "NET-TIE"]
    print("\nLOOSE, order with the boards (not placed; you wire them):\n" + plug_list(d))
    print("\nHAND-SOLDERED by the owner:\n" + hand_list(d))
    if pending:
        print(f"\n⚠️ NOT YET CHOSEN (no LCSC part, not hand-soldered): {' '.join(pending)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
