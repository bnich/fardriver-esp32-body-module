"""The body module's hooks for `pcb-layout-tools`.

`pcbl` imports this file from beside the `layout.yaml` that
`tools/layout_export.py` writes, so SYMLINK it there (`ln -s`): the hook finds
the netlist through its own resolved path, and a copy does not know where the
repo is (it refuses rather than guess).  It answers
what the yaml cannot hold as data because it is DERIVED: the voltage every
pack-voltage net stands at in each operating point.

The points are `soft_start`'s worlds -- every one a circuit working as drawn --
and one FAULT point per fuse (`fault_points`): the fuse open, with the pack on
one side of it and nothing on the other.

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
    from tools import netlist, route, rules, soft_start
    return netlist, route, soft_start, rules


def _name(point) -> str:
    v_pack, key_on, held, vf = point
    state = "on" if key_on else ("held" if held else "off")
    return f"{v_pack:g}V-{state}-vf{vf:g}"


def operating_points() -> dict:
    """{operating point name: {net: volts}}, one entry per world
    `soft_start.operating_points` walks, in its order."""
    netlist, route, soft_start, rules = _tools()
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
    for name, row in fault_points(d, soft_start, rules, out, points).items():
        if name in out:
            raise ValueError(f"layout_hooks: fault point {name!r} is already a soft-start world")
        out[name] = {net: row[net] for net in sorted(volts)}
    return out


#: Part kinds that carry DC between two nets of the 84 V section: what the
#: pack reaches a node through.  `rules._HV_JOIN` (chokes, fuses, links,
#: diodes, switches) plus resistors -- a divider mid is not isolated from the
#: pack by its resistor, it sits on a string off it.  A capacitor carries none.
DC_KINDS_EXTRA = ("R",)


def fault_points(d, soft_start, rules, worlds: dict, points) -> dict:
    """{name: {net: volts}}: one fault point per fitted FUSE, the fuse OPEN.

    ⚠️ What it protects.  In every working world the two ends of a fuse are
    one conductor, so `soft_start` has them 0 V apart and the pairwise rule
    would let their copper sit 0.1 mm apart.  Blown -- which is the fuse's one
    job -- the pack stands across it: its supply end is still fed, its load
    end is discharged by the load it was protecting.  The copper either side
    of every fuse must hold THAT, so the pack voltage apart is a world of its
    own.

    The world is `soft_start.hv_node_voltages` at the pack's do-not-exceed
    (`soft_start.pack_ceiling_v`, the figure the body module states), key on,
    no diode drop -- the fuse's supply end at the full pack -- with every net
    on the fuse's LOAD side set to 0 V.  The load side is found, not named:
    the nets of the 84 V section the always-at-pack nets no longer reach
    through DC-carrying parts once this fuse is removed (`_load_side`).
    """
    ceiling = soft_start.pack_ceiling_v(d)
    base = soft_start.hv_node_voltages(d, ceiling, True, False, 0.0)
    # always at pack: the nets at the pack voltage in EVERY working world
    # -- the tap the pack feeds, before any switch
    packs = [p[0] for p in points]
    tap = sorted(n for n in next(iter(worlds.values()))
                 if all(abs(row[n] - v) < 1e-9 for row, v in zip(worlds.values(), packs)))
    if not tap:
        raise ValueError("layout_hooks: no net is at the pack voltage in every world -- "
                         "nothing to feed a fuse from")
    ix = rules._index(d)
    domain = {n.name: n.domain for n in d.nets}
    kinds = set(rules._HV_JOIN) | set(DC_KINDS_EXTRA)
    fuses = sorted((p for p in d.parts if p.kind == "FUSE" and not p.dnp),
                   key=lambda p: p.refdes)
    out = {}
    for fuse in fuses:
        ends = [d.net_of(fuse.refdes, pin) for pin in fuse.pins]
        if len(ends) != 2 or None in ends:
            raise ValueError(f"layout_hooks: {fuse.refdes} is not a two-terminal fuse on two nets")
        joins = []
        for net in sorted(n for n, dom in domain.items() if dom == soft_start._HV_DOMAIN):
            for other, part, _flow, _a, _b in ix.adj[net]:
                if not part.dnp and rules._kind(part) in kinds:
                    joins.append((net, other, part.refdes))
        load = _load_side(fuse.refdes, ends[0].name, ends[1].name, joins, tap)
        row = dict(base)
        for net in load:
            row[net] = 0.0
        apart = abs(row[ends[0].name] - row[ends[1].name])
        if abs(apart - ceiling) > 1e-9:
            raise ValueError(f"layout_hooks: {fuse.refdes} open leaves its ends {apart:g} V "
                             f"apart, not the {ceiling:g} V pack")
        out[f"{ceiling:g}V-on-{fuse.refdes}-open"] = row
    return out


def _load_side(fuse: str, a: str, b: str, joins, tap) -> set:
    """The nets on `fuse`'s LOAD side: those the `tap` nets reach through
    `joins` [(net, net, refdes)] with the fuse there, and do not reach
    without it.  Refuses a fuse whose two ends are both fed, or neither --
    open, it would then have no pack across it, and the point would state a
    difference the circuit cannot show."""
    def reach(skip):
        adj: dict = {}
        for x, y, ref in joins:
            if ref != skip:
                adj.setdefault(x, set()).add(y)
                adj.setdefault(y, set()).add(x)
        seen, todo = set(tap), list(tap)
        while todo:
            n = todo.pop()
            for m in adj.get(n, ()):
                if m not in seen:
                    seen.add(m)
                    todo.append(m)
        return seen
    closed, opened = reach(None), reach(fuse)
    fed = [n in opened for n in (a, b)]
    if fed.count(True) != 1:
        where = "both ends" if all(fed) else "neither end"
        raise ValueError(f"layout_hooks: {fuse} open still has {where} fed from "
                         f"{', '.join(tap)} -- no pack stands across it")
    return closed - opened
