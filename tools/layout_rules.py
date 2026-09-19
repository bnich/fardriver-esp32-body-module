"""Layout rules the generated project cannot carry, derived from the netlist.

    python3 -m tools.layout_rules          # print them; build_project writes them too

The PCB documents carry one board-wide clearance (0.2 mm, JLC's capability),
because the editor-saved record form of a net class and its rule is not known
from any file here -- and a guessed record can corrupt the project. Copper at
pack voltage needs more, so the class is derived here and the owner creates it
in the editor before routing: PCB -> Design -> Net Class, a class named HV with
the nets below; Design Rules -> Safe Spacing, a rule at HV_CLEARANCE_MM,
applied to that class.
"""
import sys

from . import netlist, rules

#: IPC-2221B Table 6-1, B2 (external, uncoated, sea level), 151-300 V: the
#: band the 160 V do-not-exceed falls in (84 V is 0.6 mm; the transient sets it).
HV_CLEARANCE_MM = 1.25
HV_CLASS = "HV"


def hv_nets(d, board: str) -> list[str]:
    """Every net on `board` that can sit at pack voltage: typed 84V, or joined
    to one through copper, a switch, a choke or a diode (rules BD-2's walk)."""
    ix = rules._index(d)
    hv, _errs = rules._hv_nets(ix)
    on_board = {n.name for n in d.nets
                if any(d.has(r) and d.board_of(r) == board for r, _ in n.pins)}
    return sorted(n for n in hv if n in on_board)


def text(d=None) -> str:
    d = d or netlist.current()
    out = [f"Before routing HVIN and CONV, in the editor: PCB -> Design -> Net "
           f"Class, a class named {HV_CLASS} holding the nets below; then Design "
           f"Rules -> Safe Spacing, a rule of {HV_CLEARANCE_MM} mm applied to "
           f"{HV_CLASS}. The generated boards carry only the board-wide 0.2 mm.",
           "",
           f"Net class {HV_CLASS}: {HV_CLEARANCE_MM} mm to every other net "
           f"(IPC-2221B B2, 151-300 V: the 160 V do-not-exceed)."]
    for board in ("HVIN", "CONV", "DRV", "BRAIN"):
        nets = hv_nets(d, board)
        out.append(f"  {board}: " + (", ".join(nets) if nets else "none"))
    return "\n".join(out)


if __name__ == "__main__":
    print(text())
    sys.exit(0)
