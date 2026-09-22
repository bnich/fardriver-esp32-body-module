"""Layout rules the generated project cannot carry, derived from the netlist.

    python3 -m tools.layout_rules          # print them; build_project writes them too

A generated PCB document carries one board-wide clearance (0.2 mm, JLC's
capability). Copper at pack voltage needs more, so the class is derived here.
`tools/route.py --rules` writes it into the project (PROCESS.md Part 2 R0), and
this text is what the owner enters by hand instead: PCB -> Design -> Net Class,
a class named HV with the nets below; Design Rules -> Safe Spacing, a rule at
HV_CLEARANCE_MM, applied to that class.

The same holds for a drawn land's keep-out (the Tag-Connect pads): the maker's
drawing asks for an area no track or via crosses, which the owner draws as a
keep-out region before routing.
"""
import sys

from . import board_params as bp, drawn_footprints, netlist, rules

#: IPC-2221B Table 6-1, B2 (external, uncoated, sea level), 151-300 V: the
#: band the 160 V do-not-exceed falls in (84 V is 0.6 mm; the transient sets it).
HV_CLEARANCE_MM = 1.25
HV_CLASS = "HV"


def hv_nets(d, board: str) -> list[str]:
    """Every net on `board` that can sit at pack voltage: typed 84V, joined to
    one through copper, a switch, a choke or a diode (rules BD-2's walk), or
    SOLVED above the 12 V rail by its resistors (rules.hv_nets_solved) -- so a
    mistyped divider mid-node keeps its 1.25 mm (H15)."""
    ix = rules._index(d)
    hv, _errs = rules._hv_nets(ix)
    on_board = {n.name for n in d.nets
                if any(d.has(r) and d.board_of(r) == board for r, _ in n.pins)}
    return sorted(n for n in hv if n in on_board)


def keepouts(d) -> list[str]:
    """One line per connector whose land carries a keep-out or a pad
    clearance, in the land's own frame (top view, mm, origin at its centre)."""
    out = []
    for c in d.connectors:
        land = drawn_footprints.LANDS.get(c.land) if c.land else None
        if land is None or not (land.keepout or land.pad_clearance_mm):
            continue
        rects = "; ".join(f"x {x0:g} to {x1:g}, y {y0:g} to {y1:g}"
                          for x0, y0, x1, y1 in land.keepout)
        line = f"  {c.board} {c.refdes} ({land.title}):"
        if rects:
            line += f" no track or via inside {rects}"
        if land.pad_clearance_mm:
            line += (f"{';' if rects else ''} nothing else within "
                     f"{land.pad_clearance_mm:g} mm of any of its pads")
        out.append(line + ".")
    return out


def text(d=None) -> str:
    d = d or netlist.current()
    out = [f"Before routing POWER: `tools/route.py --rules` writes this class into "
           f"the project. By hand in the editor instead: PCB -> Design -> Net "
           f"Class, a class named {HV_CLASS} holding the nets below; then Design "
           f"Rules -> Safe Spacing, a rule of {HV_CLEARANCE_MM} mm applied to "
           f"{HV_CLASS}. The generated boards carry only the board-wide 0.2 mm.",
           "",
           f"Net class {HV_CLASS}: {HV_CLEARANCE_MM} mm to every other net "
           f"(IPC-2221B B2, 151-300 V: the 160 V do-not-exceed)."]
    for board in bp.STACK_ORDER:
        nets = hv_nets(d, board)
        out.append(f"  {board}: " + (", ".join(nets) if nets else "none"))
    lands = keepouts(d)
    if lands:
        out += ["", "Keep-outs from a land's drawing: draw each as a keep-out region "
                    "(no tracks, no vias) over the part before routing, and hold "
                    "the clearance by hand.", *lands]
    return "\n".join(out)


def main(argv=None) -> int:
    try:
        design = netlist.checked()
    except netlist.NotACircuit as e:
        print(f"⛔ REFUSED -- {e}", file=sys.stderr)
        return 1
    print(text(design))
    return 0


if __name__ == "__main__":
    sys.exit(main())
