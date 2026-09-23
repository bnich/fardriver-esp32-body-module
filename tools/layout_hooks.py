"""The body module's hooks for `pcb-layout-tools`.

`pcbl` imports this file from beside the `layout.yaml` that
`tools/layout_export.py` writes, so SYMLINK it there (`ln -s`): the hook finds
the netlist through its own resolved path, and a copy does not know where the
repo is (it refuses rather than guess).  It answers
what the yaml cannot hold as data because it is DERIVED: the voltage every
pack-voltage net stands at in each operating point.

⛔ Nothing here is typed.  `soft_start.operating_points` names the worlds a
clearance is judged in (pack volts x key state x diode drop) and
`route.hv_node_voltages` walks the netlist for each node's voltage in each of
them -- the same figures `tools/route.py` judges its pairwise HV clearance by
(IO-29), so the tool and the legacy check cannot disagree about a voltage.
"""
from __future__ import annotations

import sys
from pathlib import Path

#: The repo this hook belongs to: `tools/layout_hooks.py`'s grandparent,
#: through any symlink it was reached by.
REPO = Path(__file__).resolve().parents[1]


def _tools():
    if not (REPO / "tools" / "netlist.py").is_file():
        raise ImportError(f"layout_hooks: {Path(__file__)} does not resolve into the body "
                          f"module's tools/ -- symlink it beside layout.yaml, do not copy it")
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from tools import netlist, route, soft_start
    return netlist, route, soft_start


def _name(point) -> str:
    v_pack, key_on, held, vf = point
    state = "on" if key_on else ("held" if held else "off")
    return f"{v_pack:g}V-{state}-vf{vf:g}"


def operating_points() -> dict:
    """{operating point name: {net: volts}}, one entry per world
    `soft_start.operating_points` walks, in its order."""
    netlist, route, soft_start = _tools()
    d = netlist.checked()
    points = soft_start.operating_points(d)
    volts = route.hv_node_voltages(d)
    for net, v in volts.items():
        if len(v) != len(points):
            raise ValueError(f"layout_hooks: {net} has {len(v)} voltages for "
                             f"{len(points)} operating points")
    out = {}
    for i, point in enumerate(points):
        name = _name(point)
        if name in out:
            raise ValueError(f"layout_hooks: operating point {point} names {name!r} twice")
        out[name] = {net: float(v[i]) for net, v in sorted(volts.items())}
    return out
