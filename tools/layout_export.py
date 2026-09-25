"""The body module described to `pcb-layout-tools`: generate its `layout.yaml`.

    python3 -m tools.layout_export PROJECT.eprj2 -o layout.yaml

`pcbl check PROJECT --constraints layout.yaml` then reads the DESIGN from the
file this writes and the LAYOUT (where everything stands, what copper is down)
from the project.  `tools/layout_hooks.py` goes beside the yaml: it answers the
pack-voltage nets' operating points, which are code (`soft_start`), not data.

⛔ ONE FACT, ONE HOME.  Nothing here is typed a second time.  Every figure is
read from where it already lives, and each block says where:

  boards       the project's own outline, holes and layer table; the inner
               layers' nets by R1's rule (`_third_layer_net`); `facts.M3_KEEPOUT`,
               `facts.POUR_INSET` and `board_params.PCB_T`
  footprints   the project's FOOTPRINT documents, read the way pcbl reads them
               (`_footprint`), so the design and the layout see one geometry
  netclasses   `layout_facts`' class table, with `facts.CHANNEL_REACH` /
               `facts.SIGNAL_REACH` as the routability reach of the classes
               `routability_span` binds, and `class_copper` on `facts.heavy_classes`;
               each current class's ONE current from `power_budget` (its
               width and via count are pcbl's to derive), and the boards'
               copper, `COPPER_UM` / `VIA_PLATING_UM`
  nets         every netlist net, in the class `facts.net_class` gives it on
               each board it is on, HV split by the current the circuit puts
               through it (`_hv_power_nets`); `supply` from `facts.Index`'s grounds and
               `rules.rails` (the nets that feed a part's SUPPLY pin); `order`,
               the netlist's own order of the net's pins, wherever it is not
               the parts' order -- which member a tie meets first; `sources`
               and `sinks`, where each current class's amps enter and leave,
               walked from the brick's +V (`_current_roles`)
  parts        `netlist.checked()`: board, side, kind, height, body, and the
               pin map padmap already made the footprint's own pad names --
               in the netlist's order, which pcbl breaks its ties by
  constraints  the edge groups from `board_fit.edge_budget`; clusters from
               `facts.served_contacts`; the HV region from `layout_rules`'
               HV nets; pairs from `board_params.layer_gaps`, the cable from
               `model.is_cabled`; reaches from `facts.decoupler_hosts`, the
               ADC filters, the CAN transceiver and the programming land; the
               brake corridor from `facts.brake_terminal` / `facts.i2c_pullups`;
               the heavy path from `facts.v12_output`; the V12 pour from
               `facts.v12_line` / `facts.v12_bus`; the ground twin from
               `_twins`; the antenna and service keep-outs from
               `layout_facts`' zones
  stack        `board_params.STACK_ORDER`, `layer_gaps`, `AVAIL_H`

Where the model cannot say what the project's facts say, the exporter says so on
stderr (`Export.notes`) rather than choosing silently: those lines are the
adapter's findings.

⚠️ This module imports nothing from `pcblayout`: the body module does not
depend on the tool.  `tests/test_layout_export.py` loads the result through
pcblayout's own loader where it is installed.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field

import yaml

from tools import board_fit, eprj2, layout_rules, netlist, rules, soft_start
from tools import layout_facts as facts
from tools import board_params as bp
from tools.eprj3.pcb import M3_INSET_MM
from tools.model import is_cabled

#: Mils per millimetre, EXACTLY.  ⚠️ Not `facts.MIL_PER_MM` (39.3701, a
#: rounding): pcbl reads the same file at 1000 / 25.4, and a footprint drawn
#: here at the rounded figure would sit 0.3 um off the pads pcbl places --
#: enough to turn an exact-edge comparison the other way.
MIL_PER_MM = 1000 / 25.4

#: The copper layer types of a PCB document's LAYER table (the editor's own
#: vocabulary; `pcblayout.io.easyeda.records.COPPER_LAYER_TYPES`).
COPPER_LAYER_TYPES = ("TOP", "BOTTOM", "SIGNAL", "PLANE")
LAYER_TOP, LAYER_BOTTOM = 1, 2

#: The LOW-CURRENT pack-voltage class: a pack-voltage net the load and
#: pre-charge current do not flow through (the switch's gate drive, the key
#: sense, the level shifter's string -- `_hv_power_nets` says which).
#: Spacing and width are different facts: it keeps `facts.HV`'s clearance and
#: its pairwise-by-voltage rule, and its stated width is `facts.HV`'s 0.5 mm,
#: which no current widens.  Both figures are `facts.HV`'s, never typed here.
HV_SIGNAL = facts.NetClass("HVSIG", facts.HV.width_mm, facts.HV.clearance_mm,
                           "facts.HV's clearance and stated width, carrying no load current")

#: The pack-voltage classes: pairwise by voltage with each other and within
#: each, laid by rule, and the classes POWER's HV partition holds.
HV_CLASSES = (facts.HV, HV_SIGNAL)

#: `layout_facts`' class table, strongest first -- the order `facts._net_class`
#: tries them in, with HV split by current (`HV_SIGNAL`).  A net that is two
#: classes on two boards states the strongest as its `net_class` and the
#: others under `class_by_board`.
CLASSES = (facts.HV, HV_SIGNAL, facts.PWR12, facts.PWR5AUX, facts.CH12, facts.CH5,
           facts.DIFF, facts.SENSE, facts.RAIL, facts.DEFAULT)

#: The routability reach of each class `routability_span` binds:
#: a channel may run `CHANNEL_REACH` behind its terminal, anything else it
#: measures `SIGNAL_REACH`.  HV, PWR12 and RAIL are not bound -- the check
#: exempts HV nets and does not measure rails.
REACH = {facts.CH12.name: facts.CHANNEL_REACH, facts.CH5.name: facts.CHANNEL_REACH,
         facts.PWR5AUX.name: facts.SIGNAL_REACH, facts.DIFF.name: facts.SIGNAL_REACH,
         facts.SENSE.name: facts.SIGNAL_REACH, facts.DEFAULT.name: facts.SIGNAL_REACH}


def _mm(mil: float) -> float:
    return mil / MIL_PER_MM


def _exact(facts_mm: float) -> float:
    """A length `layout_facts` reads at its rounded conversion, re-read at the exact
    one: back to the file's mils, then to mm."""
    return _mm(facts_mm * facts.MIL_PER_MM)


def _ref_key(ref: str):
    return facts._ref_key(ref)


@dataclass
class Export:
    """The generated document and the findings made while building it."""
    doc: dict
    notes: list = field(default_factory=list)

    def text(self) -> str:
        return yaml.safe_dump(self.doc, sort_keys=False, default_flow_style=None,
                              width=100, allow_unicode=True)


# --- the project's own geometry ---------------------------------------------------
def _pad_shape(dp) -> str:
    """As pcbl reads it: an equal-axis ELLIPSE is ROUND, an OVAL is OVAL, and
    anything else its circumscribed box."""
    kind = dp.get("padType")
    w, h = dp.get("width") or 0, dp.get("height") or 0
    if kind == "ELLIPSE":
        return "ROUND" if abs(w - h) < 1e-9 else "OVAL"
    return "OVAL" if kind == "OVAL" else "RECT"


def _turned(hw: float, hh: float, angle) -> tuple[float, float]:
    """A pad's half-extents once `padAngle` has turned it -- pcbl's reading
    (`pcblayout.io.easyeda.read._turned`), so the design and the layout see
    one pad.

    ⚠️ `padAngle` turns the PAD; `relativeAngle` and `padOffsetX/Y` turn and
    move the drill inside it and are not read.  Unturned,
    `U305`'s exposed pad (1.8 x 4.5 mm at 270) lies across both pin rows and
    covers `CBOOT`, `VCC` and the `SW` and `PVIN` pins with ground copper, so no
    track can leave them.  A turn off the quarter is read as the box that holds
    the turned pad -- the safe direction."""
    turn = float(angle or 0) % 180
    if turn < 1e-6 or 180 - turn < 1e-6:
        return hw, hh
    if abs(turn - 90) < 1e-6:
        return hh, hw
    c, s = abs(math.cos(math.radians(turn))), abs(math.sin(math.radians(turn)))
    return c * hw + s * hh, s * hw + c * hh


def _footprint(uuid: str, records) -> dict:
    """A FOOTPRINT document as `layout.yaml` states one: every pad at
    `max(defaultPad, hole)` turned by its `padAngle` (`_turned`), and the body the union of the pads and what is
    drawn on the outline layers (`facts.envelope`'s rule, at the exact mm).

    A pad with no number carries no pin -- a mounting or thermal land -- and is
    named `#<record id>`, which is how pcbl names it when it reads the file."""
    pts, pads = [], []
    for h, p in records:
        if h["type"] == "PAD":
            o = json.loads(p)
            dp = o.get("defaultPad") or {}
            hole = o.get("hole") or {}
            hw = max((dp.get("width") or 0), (hole.get("width") or 0)) / 2
            hh = max((dp.get("height") or 0), (hole.get("height") or 0)) / 2
            hw, hh = _turned(hw, hh, o.get("padAngle"))
            cx, cy = o["centerX"], o["centerY"]
            pts += [(cx - hw, cy - hh), (cx + hw, cy + hh)]
            number = str(o.get("num", "")).strip() or f"#{h.get('id')}"
            pad = {"number": number, "x": _mm(cx), "y": _mm(cy), "hw": _mm(hw), "hh": _mm(hh)}
            if (hole.get("width") or 0) > 0 or (hole.get("height") or 0) > 0:
                pad["crosses_board"] = True
            pad["shape"] = _pad_shape(dp)
            if number in facts.EXPOSED_PADS:
                pad["vias_in_pad"] = True
            pads.append(pad)
        elif h["type"] in ("POLY", "FILL", "LINE"):
            o = json.loads(p)
            if o.get("layerId") in facts.OUTLINE_LAYERS:
                if "path" in o:
                    facts._path_points(o["path"], pts)
                elif "startX" in o:
                    pts += [(o["startX"], o["startY"]), (o["endX"], o["endY"])]
    if pts:
        body = [_mm(min(x for x, _ in pts)), _mm(min(y for _, y in pts)),
                _mm(max(x for x, _ in pts)), _mm(max(y for _, y in pts))]
    else:
        body = [0.0, 0.0, 0.0, 0.0]
    return {"name": uuid, "body": body, "pads": pads}


def _stated_body(records, body_mm):
    """The netlist's `footprint_mm` as pcbl's `body_mm` (w along the
    footprint's X, l along its Y), turned the way `facts.envelope` turns it:
    laid along the drawing's own long axis when the two disagree.  None where
    the netlist states no body."""
    w, l = body_mm
    if not (w and l):
        return None
    drawn = facts.envelope(records, (0.0, 0.0))
    gw, gl = drawn.x1 - drawn.x0, drawn.y1 - drawn.y0
    if (gw > 1.2 * gl and l > 1.2 * w) or (gl > 1.2 * gw and w > 1.2 * l):
        w, l = l, w
    return [float(w), float(l)]


def _layer_names(project) -> dict:
    """{PCB title: [copper layer names, top to bottom]} from each document's
    LAYER table, ordered by LAYER_PHYS's zIndex where the file states one
    (⛔ never by `layerId`: the file's 2 is the BOTTOM)."""
    _, docs = eprj2.documents(project.records)
    out = {}
    for doc_type, _uuid, recs in docs:
        if doc_type != "PCB":
            continue
        title = next(json.loads(p)["title"] for h, p in recs if h["type"] == "META")
        used, types, phys = {}, {}, {}
        for h, p in recs:
            if h["type"] not in ("LAYER", "LAYER_PHYS"):
                continue
            try:
                lid = json.loads(h["id"])[1]
            except (TypeError, ValueError, IndexError, KeyError):
                continue
            o = json.loads(p)
            if h["type"] == "LAYER":
                types[lid] = o.get("layerType")
                if o.get("use"):
                    used[lid] = o.get("layerName") or f"Layer {lid}"
            else:
                phys[lid] = o.get("zIndex")

        def rank(lid):
            if phys.get(lid) is not None:
                return (0, phys[lid])
            return (1, -1 if lid == LAYER_TOP else (1 << 30) if lid == LAYER_BOTTOM else lid)
        out[title] = [used[i] for i in sorted(
            (i for i in used if types.get(i) in COPPER_LAYER_TYPES), key=rank)]
    return out


# --- the design ---------------------------------------------------------------------
def _hv_power_nets(d, hv) -> set:
    """The pack-voltage nets of `hv` the LOAD and PRE-CHARGE current flows
    through: the power HV class.  Every other net of `hv` is `HV_SIGNAL`.

    ⭐ THE RULE, from the circuit and never from a list of names: start at
    every pack-voltage net that feeds a part's SUPPLY pin (`rules.rails` --
    the converters' `+Vin`), and walk, inside `hv`, across what the current
    flows through on its way there --
      * a FET's channel, drain to source (`rules._Ix.adj` has only that pair);
      * a choke, fuse or link (`soft_start._DC_SHORT`), and for a common-mode
        choke BOTH windings: the second carries the converter's return, so
        its pack-voltage net carries the same current back;
      * a rectifier (kind `D`), either way: the pre-charge current comes in
        through it and the ride-out holds on the far side.
    It does NOT cross a zener or a TVS (they stand off), a resistor (a bias
    or a divider: a load path through one would dissipate the load, and the
    circuit has none) or a capacitor (no DC path).  So the gate drive, the
    key sense and the level shifter's pull-down string are reached by no
    walk: they carry micro- to milliamps, not the tap current."""
    rix = rules._index(d)
    seeds = sorted(set(rules.rails(d)) & hv)
    power, queue = set(seeds), list(seeds)
    while queue:
        net = queue.pop()
        for other, part, _flow, _a, _b in rix.adj.get(net, ()):
            if part.dnp:
                continue
            carries = (rules._kind(part) in soft_start._DC_SHORT
                       or part.kind in rules.FETS or part.kind == "D")
            if not carries:
                continue
            reach = {other}
            if part.kind == "CMCHOKE":          # the return winding carries it back
                reach |= {n for pin in part.pins for n in rix.nets_of_pin(part.refdes, pin)}
            for n in sorted(reach & hv - power):
                power.add(n)
                queue.append(n)
    return power


def _net_classes(ix) -> dict:
    """{net: {board: class name}} for every board the net is on, by
    `facts.net_class` -- the class differs by board where the copper does
    (`V12` is PWR12 where it carries the loads, RAIL where it is one trace to
    a converter).  A pack-voltage net the load current does not flow through
    (`_hv_power_nets`) is `HV_SIGNAL` where `facts.net_class` says HV.  A net on no
    placed part is {}.

    ⛔ A board with pack-voltage nets and not ONE on the load's path is
    refused: every HV net would be laid at the low-current width, and the
    tap current would run through copper nobody sized for it."""
    power = {}
    for b, hv in ix.hv.items():
        if hv:
            power[b] = _hv_power_nets(ix.d, hv)
            if not power[b]:
                raise SystemExit(f"layout_export: {b} has pack-voltage nets {sorted(hv)} and "
                                 f"none feeds a SUPPLY pin through what the load current "
                                 f"flows through: the power HV class would be empty")
    out = {}
    for n in ix.members:                    # the netlist's order: it is stated order
        boards = sorted({ix.items[r].board for r, _ in ix.members[n] if r in ix.items})
        per = {}
        for b in boards:
            c = facts.net_class(ix, b, n)
            if c is facts.HV and n not in power.get(b, ()):
                c = HV_SIGNAL
            per[b] = c.name
        out[n] = per
    return out


#: The classes a stitch sizes by the pin's share: those that carry current AND
#: take a via.  HV carries current too but never changes layer, and HVSIG
#: states no current (its bounded via is one barrel a change), so no pin of
#: theirs is ever asked what it carries.
ROLE_CLASSES = ("PWR12", "PWR5AUX", "CH12", "CH5")


def _current_roles(ix, classes, currents) -> dict:
    """{net: (sources, sinks, {sink: own amps})} for every net in a `ROLE_CLASSES` class on some
    board -- where its current ENTERS and LEAVES each board, from the COPPER.

    A part is a SOURCE of the net its current-output pin is on
    (`facts.current_outputs`: the brick's `+V`, a switch's `OUTx`, the buck's
    `SW`, the inductor's far end).  The nets are ranked by how far the current
    has come from the brick -- `V12` first, then what a part on it feeds, and
    so on -- and a part that sources a net FURTHER from the brick is a SINK of
    each nearer current net it has a pin on: a TPS4H160B of `V12`, the buck
    of `V12`, the inductor of the switch node, a TPS2553 of `V5AUX`.  (The
    buck's `BIAS` pin is on `V5AUX`, which is further from the brick than
    the switch node the buck sources, so the buck is not a sink of it.)  A
    connector whose mate stands on a board nearer the brick (over the stack's
    mated pairs and cable, `interface`) brings the current in, and is a
    source; any other interface connector, and a harness terminal, carries
    it away, and is a sink.  Everything else on the net -- a decoupler, a
    divider, an open-load pull-up, a TVS -- carries only its own current.

    A sink that sources further nets is stated at what THEY carry: the sum of
    their classes' currents on its board (`currents`, `_class_current_a`) --
    a TPS4H160B at its four channels' limiters, not an equal part of the bus,
    which would be a fuse under the one whose channels are all at their
    ceiling.  pcbl caps it at the net's own class current.  A connector
    takes the equal share."""
    cur = {n for n, per in classes.items() if set(per.values()) & set(ROLE_CLASSES)}
    outs = facts.current_outputs(ix.d)
    sourced: dict = {}                       # refdes -> the current nets it sources
    for n in cur:
        for r, pin in ix.members[n]:
            if (r, pin) in outs:
                sourced.setdefault(r, []).append(n)
    depth: dict = {}
    queue = [n for n in ix.members if n in cur and any(
        r == bp.FLOOR_SEAT and (r, pin) in outs for r, pin in ix.members[n])]
    for n in queue:
        depth[n] = 0
    while queue:
        n = queue.pop(0)
        for r in dict.fromkeys(r for r, _ in ix.members[n]):
            for m in sourced.get(r, ()):
                if m not in depth:
                    depth[m] = depth[n] + 1
                    queue.append(m)
    origin = ix.items[bp.FLOOR_SEAT].board
    links: dict = {}
    for it in ix.items.values():
        for o in ix.items.values():
            if it.interface and o.interface == it.interface and o.board != it.board:
                links.setdefault(it.board, set()).add(o.board)
    dist, bq = {origin: 0}, [origin]
    while bq:
        b = bq.pop(0)
        for o in sorted(links.get(b, ())):
            if o not in dist:
                dist[o] = dist[b] + 1
                bq.append(o)
    roles = {}
    for n in [n for n in ix.members if n in cur]:
        src, snk, own = [], [], {}
        for r in dict.fromkeys(r for r, _ in ix.members[n]):
            it = ix.items.get(r)
            if it is None:
                continue
            if n in sourced.get(r, ()):
                src.append(r)
            elif it.kind == "CONN":
                mates = [o for o in ix.items.values()
                         if it.interface and o.interface == it.interface and o.board != it.board]
                if any(dist.get(o.board, math.inf) < dist.get(it.board, math.inf) for o in mates):
                    src.append(r)
                elif mates or it.harness:
                    snk.append(r)
            elif n in depth and any(depth.get(m, -1) > depth[n] for m in sourced.get(r, ())):
                snk.append(r)
                amps = sum(currents.get(classes[m].get(it.board), 0.0)
                           for m in sourced[r] if depth.get(m, -1) > depth[n])
                if amps:
                    own[r] = round(amps, 3)
        roles[n] = (src, snk, own)
    return roles


def _net_rows(ix, classes, part_order, currents) -> list:
    """The `nets` block.  `net_class` is the strongest of the net's classes;
    a board where it is another class is named under `class_by_board`.
    `supply` is the circuit's statement of a supply or a return: a ground
    (`ix.gnd`) or a net feeding a part's SUPPLY pin (`ix.rails`) -- what
    `routability_span` does not measure.  `order` is the
    netlist's order of the net's members (`ix.members`), stated wherever it
    differs from `part_order`: a band is lent by the first rail member met
    with the most pins, and the netlist lists a net's pins in
    its own order, not its parts'."""
    rank = {c.name: i for i, c in enumerate(CLASSES)}
    at = {r: i for i, r in enumerate(part_order)}
    roles = _current_roles(ix, classes, currents)
    rows = []
    for n in classes:                       # the netlist's order, as `_net_classes` keeps it
        per = classes[n]
        base = min(per.values(), key=rank.__getitem__) if per else facts.DEFAULT.name
        row = {"name": n, "net_class": base}
        other = {b: c for b, c in per.items() if c != base}
        if other:
            row["class_by_board"] = other
        if n in ix.gnd or n in ix.rails:
            row["supply"] = True
        met = list(dict.fromkeys(r for r, _ in ix.members[n] if r in at))
        if met != sorted(met, key=at.__getitem__):
            row["order"] = met
        if n in roles:
            for key, got in zip(("sources", "sinks"), roles[n][:2]):
                got = [r for r in got if r in at]
                if got:
                    row[key] = got
            own = {r: a for r, a in roles[n][2].items() if r in at}
            if own:
                row["part_current_a"] = own
        rows.append(row)
    return rows


def _used_classes(classes) -> set:
    """Every class a net row names: a net on no placed part is DEFAULT."""
    used = {c for per in classes.values() for c in per.values()}
    if any(not per for per in classes.values()):
        used.add(facts.DEFAULT.name)
    return used


#: The via the routers may use on the classes of `VIA_CLASSES`:
#: 0.6 mm pad, 0.3 mm finished hole -- JLCPCB's standard via, no extra charge.
VIA_MM = (0.6, 0.3)
#: The fab stack's copper, stated once for every board (JLCPCB's
#: JLC04161H-7628 four-layer stack): 1 oz -- 35 um -- on the faces, where every
#: laid class runs, and the 18 um the fab states as its AVERAGE via plating,
#: the barrel's whole current-carrying wall.  pcbl derives every current
#: class's width and every via's current from these two and the class's own
#: current and rise (IPC-2221; its `model.ampacity`), so they are the only
#: copper figures the design states.
COPPER_UM = 35.0
VIA_PLATING_UM = 18.0

#: The temperature rise each current class's copper may take carrying its
#: current -- `layout_facts`' own derivations (`facts.HV`, `PWR12`, `PWR5AUX`,
#: `CH12`, `CH5`): the buses at 20 degC, which run once and are never shorted
#: at a terminal; the channels and the pack tap at 10 degC, the margin a run
#: that may be shorted at its far end needs.  A via takes the class's rise,
#: so a layer change runs no hotter than its tracks.
RISE_C = {facts.HV.name: 10.0, facts.PWR12.name: 20.0, facts.PWR5AUX.name: 20.0,
          facts.CH12.name: 10.0, facts.CH5.name: 10.0}

#: ⭐ Every class states `layout_facts`' width as its `min_width_mm`: that width is
#: a design decision (CH12 1.00, CH5 0.80, PWR5AUX 2.00, PWR12 5.00, HV 0.50),
#: and a standard may WIDEN it, never narrow it.  pcbl takes the larger of it
#: and the width the class's current derives (its `Design.width_mm`), so
#: IPC-2221 stands where it is wider -- PWR12 5.66, PWR5AUX 2.10, HV 1.12 --
#: and the stated width stands where it is not -- CH12, CH5.
#:
#: The current is the CONTINUOUS design current at the limited case
#: (`_class_current_a`).  Whether a run must also carry its protection's trip
#: current (the OCP ceiling, `limit_case().ocp_*`) is the owner's hardware
#: review, not a default here.


#: The classes that state a via.  ⛔ No HV via: HV is the load path, and a
#: pack-voltage barrel through the inner GND planes needs a 1.25 mm antipad in
#: each; HV stays on the faces (`facts.HV`).  HVSIG takes one only where that
#: reason does not hold (`BOUNDED_VIA_CLASSES`).  CH5 has room on its face.  PWR12 and RAIL are carried
#: by an inner sheet where the board has one (the 12 V pour, the 3.3 V
#: plane), and a surface pad reaches an inner sheet only through a via -- so
#: they state one, sized by pcbl from the class current like every other.
#: The signal classes -- DIFF, SENSE and default, which pcbl's signal router
#: lays -- take the same standard via: a board with parts on both faces
#: cannot join a top pad to a bottom one without it.
VIA_CLASSES = ("PWR12", "RAIL", "PWR5AUX", "CH12", "DIFF", "SENSE", "default")

#: The classes whose via is BOUNDED to the HV regions (pcbl's `via_regions`):
#: the standard via, but only inside a board's HV region and only where no
#: plane or pour of another net comes within the class's clearance, on any
#: layer.  HVSIG carries no load current, and POWER's HV region carries no
#: inner plane (the GND planes are cut back past its strip), so there the
#: antipad reason for "no HV via" does not hold: a divider's run may change
#: face to cross the region.  Every such via keeps the class clearance on
#: every layer, judged pairwise by voltage as the class is.  pcbl's
#: `via_region` check fires on one anywhere else.  HV (the load path) stays
#: via-free.
BOUNDED_VIA_CLASSES = ("HVSIG",)


def _class_current_a(d, ix) -> dict:
    """{class: amps} for every class in `RISE_C`, read off the circuit, never
    typed.  ONE current per class: its track width and its via count both
    derive from it.

    CH12 / CH5: the highest current limit any of the class's channels has --
    each channel's own limiter at its ceiling (`power_budget._channel_limit_a`);
    copper sized for the typical channel would be a fuse on the strongest.
    PWR5AUX: the four 5 V channels' limiters at their ceiling together,
    `n5 x per_5v_a`, which is what the 5 V bus feeds.  PWR12: the 12 V load in
    the LIMITED case, every limiter at its ceiling at once
    (`limit_case().load_12v_a`).  HV: the pack tap in that same case at the
    low-voltage cut-off (`limit_case().tap_a`).  A figure the circuit cannot
    give is a refusal, not a guess."""
    from tools import power_budget as pb
    out = {}
    for cls in (facts.CH12.name, facts.CH5.name):
        amps = []
        for net in sorted(ix.classes.get(cls, ())):
            a, why = pb._channel_limit_a(d, net)
            if why:
                raise SystemExit(f"layout_export: {cls} current: {why}")
            amps.append(a)
        if amps:
            out[cls] = round(max(amps), 3)
    lim = pb.limit_case(d)
    if lim.per_5v_a is None or not lim.n5:
        raise SystemExit(f"layout_export: PWR5AUX current: the 5 V channels' limit is "
                         f"not derivable ({'; '.join(lim.problems) or 'no 5 V channel'})")
    out[facts.PWR5AUX.name] = round(lim.n5 * lim.per_5v_a, 3)
    if lim.load_12v_a is None or lim.tap_a is None:
        raise SystemExit(f"layout_export: PWR12 / HV current: the limited case is not "
                         f"derivable ({'; '.join(lim.problems) or 'no 12 V load'})")
    out[facts.PWR12.name] = round(lim.load_12v_a, 3)
    out[facts.HV.name] = round(lim.tap_a, 3)
    return out


def _netclasses(used, currents, regions=()) -> list:
    out = []
    for c in CLASSES:
        if c.name not in used:
            continue
        row = {"name": c.name}
        if c.name in RISE_C:
            # one current per class: pcbl derives the width AND the via count
            # from it, the class's rise and the board's copper
            row["current_a"] = currents[c.name]
            row["rise_c"] = RISE_C[c.name]
        row["min_width_mm"] = c.width_mm          # stated: widened, never narrowed
        row["clearance_mm"] = {"default": c.clearance_mm}
        if c.pour_ok:
            row["pour"] = True
        if c in HV_CLASSES:
            # pairwise within each HV class and across the two: IPC-2221B B2
            # at the two nets' own difference over the operating points
            # `layout_hooks` answers (IO-29) -- 1.25 mm stands wherever
            # either has none
            row["pairwise_by_voltage"] = True
        if c.name in REACH:
            row["reach_mm"] = REACH[c.name]
        if c in facts.heavy_classes() or c is HV_SIGNAL:
            # the classes `pcbl route copper` lays by rule;
            # HV_SIGNAL is HV's own nets, laid with HV
            row["class_copper"] = True
        if c.name in VIA_CLASSES:
            row["via_mm"] = list(VIA_MM)
        hv_regions = [r["name"] for r in regions if c.name in r["classes"]]
        if c.name in BOUNDED_VIA_CLASSES and hv_regions:
            row["via_mm"] = list(VIA_MM)
            row["via_regions"] = hv_regions
        out.append(row)
    return out


def _third_layer_net(ix, board) -> tuple[str, str]:
    """(net, kind) of `board`'s second inner layer, by R1's rule: the 12 V
    pour where a driver line takes the bus, else the rail with `RAIL_POUR_PINS`, else a second ground.  A rail poured
    over the whole board is a plane; the 12 V pour covers only the bus."""
    if facts.v12_line(ix, board):
        return sorted(ix.classes["PWR12"])[0], "pour"
    rail = facts._rail_pour_net(ix, board)
    if rail is not None:
        return rail, "plane"
    return _ground(ix, board), "plane"


def _ground(ix, board):
    gnd = sorted(ix.gnd & {n for it in ix.on(board) for n in it.nets})
    return "GND" if "GND" in gnd else gnd[0]


def _boards(project, ix, notes) -> list:
    names = _layer_names(project)
    out = []
    for b in bp.STACK_ORDER:
        pcb = project.pcbs.get(b)
        if pcb is None:
            notes.append(f"board: the project has no {b} document; it is not exported")
            continue
        layers = names[b]
        if len(layers) != 4:
            raise SystemExit(f"layout_export: {b} has {len(layers)} copper layers "
                             f"({layers}); R1 plans four")
        third, kind = _third_layer_net(ix, b)
        f = pcb.frame
        # The outline's width is the design's (`board_params.board_width`:
        # POWER_W for POWER, BOARD_W otherwise), not the project's: the holes
        # stay where the project has them, on the common pattern, and
        # `pcbl board` moves the drawn outline to this width.
        width = bp.board_width(b)
        if abs(f.width - width) > facts.TOL:
            notes.append(f"board: {b} is drawn {f.width:.2f} mm wide in the project; "
                         f"the design's width is {width:g} mm -- `pcbl board` redraws it")
        else:
            width = _exact(f.width)
        out.append({
            "name": b, "length_mm": _exact(f.length), "width_mm": width,
            "filled_vias_in_pad": True,
            "portrait": bool(f.portrait), "thickness_mm": bp.PCB_T,
            "layers": [{"name": layers[0], "kind": "signal"},
                       {"name": layers[1], "kind": "plane", "net": _ground(ix, b)},
                       {"name": layers[2], "kind": kind, "net": third},
                       {"name": layers[3], "kind": "signal"}],
            "holes": sorted([_exact(u), _exact(v)] for u, v in f.holes),
            "hole_keepout_mm": facts.M3_KEEPOUT,
            "pour_inset_mm": facts.POUR_INSET,
            "copper_um": COPPER_UM, "via_plating_um": VIA_PLATING_UM})
    return out


def _parts(d, ix, project, footprints, notes) -> list:
    """The `parts` block, in the NETLIST's order -- `facts.Index.items`, the
    parts then the connectors, each pin in the order the netlist lands it.
    ⚠️ The order is a fact of the design: pcbl breaks a tie by stated order,
    so a sorted list would place tied parts differently from the netlist's
    own statement of the order."""
    leads = {x.refdes: x.lead_mm for x in (*d.parts, *d.connectors)
             if getattr(x, "lead_mm", None) is not None}
    out = []
    for it in ix.items.values():
        board = it.board
        pcb = project.pcbs.get(board)
        if pcb is None:
            continue
        comp = pcb.components.get(it.refdes)
        if comp is None:
            notes.append(f"part: {board} {it.refdes} is not in the project; not exported")
            continue
        fp = footprints[comp.footprint]
        pads = {p["number"] for p in fp["pads"]}
        pins = {}
        for pin, net in it.pin_net.items():
            if pin in pads:
                pins[pin] = net
            elif net:
                notes.append(f"part: {board} {it.refdes} pin {pin} ({net}) has no pad of "
                             f"that name on footprint {comp.footprint}; dropped")
        row = {"refdes": it.refdes, "footprint": comp.footprint, "board": board,
               "kind": "CONNECTOR" if it.kind == "CONN" else it.kind}
        if it.side == "bottom":
            row["side"] = "bottom"
        row["pins"] = pins
        body = _stated_body(project.footprints[comp.footprint], it.body)
        if body is not None:
            row["body_mm"] = body
        if it.height is not None:
            row["height_mm"] = float(it.height)
        lead = leads.get(it.refdes)
        if lead is not None:
            # pcbl gives a part tails only where its footprint has a pad that
            # crosses the board; a lead on any other footprint is refused.
            if any(p.get("crosses_board") for p in fp["pads"]):
                row["lead_mm"] = float(lead)
            else:
                notes.append(f"part: {board} {it.refdes} states lead_mm {lead:g} but footprint "
                             f"{comp.footprint} has no through-hole pad; lead not exported")
        if it.harness:
            row["attrs"] = {"harness": True}
        out.append(row)
    return out


# --- the constraints ------------------------------------------------------------------
def _edge_groups(d, boards) -> list:
    length = {b["name"]: b["length_mm"] for b in boards}
    out = []
    for e in board_fit.edge_budget(d):
        if e.board not in length:
            continue
        out.append({"kind": "edge_group", "name": f"{e.board}-ROW", "board": e.board,
                    "edge": "v0", "parts": list(e.headers),
                    # `edge_strip`: inside the board end less the M3 inset
                    "span_mm": [M3_INSET_MM, length[e.board] - M3_INSET_MM],
                    # between two headers in the row (`body_clearance`)
                    "gap_mm": board_fit.HEADER_GAP})
    return out


def _clusters(ix, classes) -> list:
    out = []
    for board in bp.STACK_ORDER:
        for it in sorted(ix.on(board), key=lambda i: _ref_key(i.refdes)):
            served = facts.served_contacts(ix, board, it.refdes)
            if not served:
                continue
            pull = {}
            for net, _conn, _pin, weight in served:
                if weight != 1.0:
                    pull[classes[net][board]] = weight
            row = {"kind": "cluster", "name": f"{it.refdes}-SERVES", "host": it.refdes,
                   "serves": sorted({conn for _, conn, _, _ in served}, key=_ref_key)}
            if pull:
                row["pull"] = dict(sorted(pull.items()))
            out.append(row)
    return out


def _regions(d, ix, boards) -> list:
    """POWER's HV/LV partition (the `region_*` checks).  Its neutral nets are every
    GND-domain net (ground is on both sides by definition)
    that is not already the board's plane -- `BASEPLATE`, which `C203`/`C204`
    tie to the pack-voltage input, is ground and no plane carries it."""
    out = []
    for b in boards:
        if layout_rules.hv_nets(d, b["name"]):
            planes = {l["net"] for l in b["layers"] if l["kind"] == "plane"}
            on_board = {n for it in ix.on(b["name"]) for n in it.nets}
            row = {"kind": "region", "name": f"{b['name']}-HV", "board": b["name"],
                   "classes": [c.name for c in HV_CLASSES], "strip_mm": facts.HV_STRIP,
                   "straddler": "member_pins_in", "edge_mm": facts.HV_EDGE}
            neutral = sorted((ix.gnd & on_board) - planes)
            if neutral:
                row["neutral_nets"] = neutral
            out.append(row)
    return out


def _interfaces(d, ix) -> list:
    out = []
    gaps = bp.layer_gaps(d)
    for g in gaps:
        for p in g.pairs:
            iface = ix.items[p.lower].interface or f"{p.lower}-{p.upper}"
            out.append({"kind": "pair", "name": iface, "lower": p.lower, "upper": p.upper,
                        "mated_height_mm": p.mated_mm})
    by_iface = {}
    for c in d.connectors:
        if c.interface and is_cabled(c.interface):
            by_iface.setdefault(c.interface, []).append(c)
    order = {b: i for i, b in enumerate(bp.STACK_ORDER)}
    for iface, ends in sorted(by_iface.items()):
        ends = sorted(ends, key=lambda c: order[c.board])
        if len(ends) != 2:
            raise SystemExit(f"layout_export: cabled interface {iface} has {len(ends)} ends")
        # ⛔ no gap: pcbl derives the height the loom spans from the stack
        # (`stack.cable_gap`), so a gap stated here would be a second home
        out.append({"kind": "cable", "name": iface, "ends": [ends[0].refdes, ends[1].refdes]})
    return out


def _reaches(ix, notes) -> list:
    out = []
    for board in bp.STACK_ORDER:
        for cap, host in sorted(facts.decoupler_hosts(ix, board).items(),
                                key=lambda kv: _ref_key(kv[0])):
            out.append({"kind": "reach", "name": f"{cap}-DECOUPLE", "host": host,
                        "satellite": cap, "within_mm": facts.DECOUPLE_REACH,
                        "reason": "a 100 nF decoupler beside the IC on its rail"})
        # `reach`: a converter's switch-node parts -- bootstrap cap, inductor --
        # beside it (the IC's `SW` pin, as `current_outputs` names it)
        for it in sorted(ix.on(board), key=lambda i: _ref_key(i.refdes)):
            sw = it.pin_net.get("SW") if it.kind == "IC" else None
            if not sw:
                continue
            for r in sorted({r for r, _ in ix.members[sw]}, key=_ref_key):
                other = ix.items.get(r)
                if r == it.refdes or other is None or other.board != board:
                    continue
                out.append({"kind": "reach", "name": f"{r}-SW", "host": it.refdes,
                            "satellite": r, "within_mm": facts.SW_REACH,
                            "reason": f"on {it.refdes}'s switch node {sw}: the loop that "
                                      f"radiates, and the output current at the edge"})
        module = next((it for it in ix.on(board) if it.kind == "MODULE"), None)
        if module is None:
            continue
        # `reach`: an ADC input's RC beside the module
        seen = set()
        for n in sorted(ix.classes["SENSE"]):
            if not any(r == module.refdes for r, _ in ix.members[n]):
                continue
            for r, _ in ix.members[n]:
                it = ix.items.get(r)
                if it is None or it.board != board or it.kind not in ("R", "C") or r in seen:
                    continue
                seen.add(r)
                out.append({"kind": "reach", "name": f"{r}-ADC", "host": module.refdes,
                            "satellite": r, "within_mm": facts.ADC_REACH,
                            "reason": f"the filter on {n}, an ADC1 input, sits at the pin"})
        # `reach`: the CAN transceiver by the stack contacts its pair leaves on
        for it in sorted(ix.on(board), key=lambda i: _ref_key(i.refdes)):
            if it.kind != "IC" or not any(n.startswith("CAN") for n in it.nets):
                continue
            for conn in sorted(ix.on(board), key=lambda i: _ref_key(i.refdes)):
                if conn.kind != "CONN" or not conn.interface:
                    continue
                if not any(net in it.nets and net.startswith("CAN")
                           for net in conn.pin_net.values()):
                    continue
                out.append({"kind": "reach", "name": f"{it.refdes}-{conn.refdes}-CAN",
                            "host": it.refdes, "satellite": conn.refdes,
                            "within_mm": facts.CAN_REACH, "measure": "shared_pins",
                            "reason": "the CAN pair stays short to the stack contacts"})
                notes.append(f"reach: {it.refdes}-{conn.refdes}-CAN is measured pin to pin "
                             f"(worst shared pin), not from the transceiver's box centre to "
                             f"the centroid of the connector's CAN contacts")
        # `reach`: the programming land by the module whose pins it carries
        land = next((it for it in ix.on(board) if it.kind == "CONN" and it.land), None)
        if land is not None:
            out.append({"kind": "reach", "name": f"{land.refdes}-PROG", "host": module.refdes,
                        "satellite": land.refdes, "within_mm": facts.PROG_REACH,
                        "measure": "shared_pins",
                        "reason": "the land carries the module's own EN, IO0 and UART0 pins "
                                  "(D25)"})
    return out


def _heavy_paths(ix) -> list:
    """`heavy_path`: the converter's 12 V output pins to the contact the bus
    leaves by.  One chain per (output pin, contact) pair, so the WORST of
    them binds; pcbl measures each as a straight line between the pins."""
    out = []
    pwr12 = ix.classes["PWR12"]
    for board in bp.STACK_ORDER:
        src, away, _ = facts.v12_output(ix, board)
        if src is None or away is None:
            continue
        mine = sorted({p for p, n in ix.items[src].pin_net.items() if n in pwr12}, key=_ref_key)
        theirs = sorted({p for p, n in ix.items[away].pin_net.items() if n in pwr12},
                        key=_ref_key)
        for a in mine:
            for b in theirs:
                out.append({"kind": "heavy_path", "name": f"{src}.{a}-{away}.{b}",
                            "chain": [[src, a], [away, b]], "max_mm": facts.HEAVY_PATH_MM})
    return out


def _twins(ix) -> list:
    """The 12 V run's ground twin: on a board that
    carries the bus, each ground that reaches both the converter and the
    contact the bus leaves by, over those two and the bus's other parts on
    that ground, laid beside the run at `PWR12`'s width."""
    out = []
    for board in bp.STACK_ORDER:
        src, away, parts = facts.v12_output(ix, board)
        if src is None or away is None or not facts.carries_bus(ix, board):
            continue
        for net in sorted(n for n in ix.gnd
                          if any(r == src for r, _ in ix.members.get(n, ()))
                          and any(r == away for r, _ in ix.members.get(n, ()))):
            refs = [src, away] + [r for r in parts
                                   if r != away and net in ix.items[r].nets]
            out.append({"kind": "twin", "name": f"{board}-{net}-RETURN", "board": board,
                        "net": net, "beside": facts.PWR12.name, "parts": refs})
    return out


def _region_returns(ix, classes, regions, reaches, boards) -> list:
    """The pack-voltage end's ground, laid as copper. There is no ground pour at that end.
    The board's ground plane is cut back at the region and its strip (no
    ground sheet a prepreg from pack voltage), so the ground pins that stand
    in the region -- the pack's negative contacts, the common-mode chokes'
    return legs, the clamp's and the pull-down's, the isolated converters'
    output returns -- have no sheet in a stitch via's reach.  A twin joins
    them at the region's power class width, under the pairwise clearance
    `pcbl route copper` keeps: every ground-carrying MEMBER of the region
    (a part with a pin on one of its classes' nets, a straddler included --
    whose ground pins stand on the plane side, which is where the twin meets
    the sheet) and every reach satellite of one that is on the ground (a
    converter's decoupler)."""
    out = []
    by_board = {b["name"]: b for b in boards}
    for r in regions:
        board = r["board"]
        b = by_board.get(board)
        if b is None:
            continue
        planes = {l["net"] for l in b["layers"] if l["kind"] == "plane" and l.get("net")}
        wanted = set(r["classes"])
        members = [it.refdes for it in ix.on(board)
                   if any(classes.get(n, {}).get(board) in wanted for n in it.nets)]
        heavy = r["classes"][0]
        for net in sorted(planes & ix.gnd):
            refs = [m for m in members if net in ix.items[m].nets]
            host = set(refs)
            refs += [c["satellite"] for c in reaches
                     if c["host"] in host and ix.items[c["satellite"]].board == board
                     and net in ix.items[c["satellite"]].nets and c["satellite"] not in host]
            refs = sorted(dict.fromkeys(refs), key=_ref_key)
            if len(refs) < 2:
                continue
            out.append({"kind": "twin", "name": f"{r['name']}-{net}-RETURN", "board": board,
                        "net": net, "beside": heavy, "parts": refs})
    return out


def _corridors(ix) -> list:
    """`corridor`, the brake clause: the I2C pull-ups keep `CORRIDOR_CLEAR` off
    the straight path the brake nets take from their harness terminal to the
    module -- the path `facts.brake_terminal` finds and `facts.i2c_pullups`'
    resistors keep clear of."""
    out = []
    for board in bp.STACK_ORDER:
        module = next((it for it in ix.on(board) if it.kind == "MODULE"), None)
        if module is None:
            continue
        term = facts.brake_terminal(ix, board, module.refdes)
        pullups = facts.i2c_pullups(ix, board)
        if term is None or not pullups:
            continue
        out.append({"kind": "corridor", "name": f"{term}-{module.refdes}-BRAKE",
                    "ends": [term, module.refdes], "parts": list(pullups),
                    "clear_mm": facts.CORRIDOR_CLEAR,
                    "reason": "the brake nets' way to the module; the I2C bus's edges "
                              "stay off it"})
    return out


def _pour_spans(ix, boards) -> list:
    """`pour_span`: the V12 pour reaches EVERY pad of its net on the board -- the
    driver line's bus pins, the feed's own contacts, and every other part on
    the net (the pull-ups, the terminals, the decouplers), because a surface
    pad reaches a pour only by a stitch via beside it, and a pad with no sheet
    in reach is left with no copper at all.  Fed from inside."""
    out = []
    for b in boards:
        board = b["name"]
        drivers = facts.v12_line(ix, board)
        if not drivers:
            continue
        _, feed = facts.v12_bus(ix, board)
        layer = next(l for l in b["layers"] if l["kind"] == "pour")
        net = layer["net"]
        refs = sorted({it.refdes for it in ix.on(board) if net in it.nets}, key=_ref_key)
        pads = [[r, p] for r in refs
                for p in sorted({p for p, n in ix.items[r].pin_net.items() if n == net},
                                key=_ref_key)]
        row = {"kind": "pour_span", "name": f"{board}-{layer['net']}-POUR", "board": board,
               "net": layer["net"], "layer": layer["name"], "pads": pads}
        if feed:
            row["feed"] = feed
        out.append(row)
    return out


def _keep_outs(ix, project) -> list:
    out = []
    for board in bp.STACK_ORDER:
        pcb = project.pcbs.get(board)
        if pcb is None:
            continue
        for it in sorted(ix.on(board), key=lambda i: _ref_key(i.refdes)):
            comp = pcb.components.get(it.refdes)
            if comp is None:
                continue
            env = facts.envelope(project.footprints[comp.footprint], it.body)
            if it.kind == "MODULE":
                # `keep_out`: the zone beyond the antenna end -- the module's
                # padless end, its footprint's +Y
                out.append({"kind": "keep_out", "name": f"{it.refdes}-ANTENNA", "board": board,
                            "box": [env.x0, env.y1, env.x1, env.y1 + facts.ANTENNA_ZONE_D],
                            "reason": "the antenna end: nothing in the zone beyond it",
                            "side": "both", "part": it.refdes,
                            "at_edge_mm": facts.ANTENNA_EDGE})
            if it.kind == "CONN" and it.land:
                # `keep_out`: the programming cable's plug at each end of the land
                w, dd, c = env.x1 - env.x0, env.y1 - env.y0, facts.SERVICE_CLEAR
                zones = ([[env.x0 - c, env.y0, env.x0, env.y1], [env.x1, env.y0, env.x1 + c, env.y1]]
                         if w >= dd else
                         [[env.x0, env.y0 - c, env.x1, env.y0], [env.x0, env.y1, env.x1, env.y1 + c]])
                for tag, box in zip(("LO", "HI"), zones):
                    out.append({"kind": "keep_out", "name": f"{it.refdes}-SERVICE-{tag}",
                                "board": board, "box": box,
                                "reason": "the programming cable's plug at the land's end",
                                "side": "top", "part": it.refdes})
    return out


#: The body module's standoff seatings, in pcbl's words: "shimmed" is a pillar
#: specified SHORT of the pair's stop, which pcbl calls "short"; a "shim" is
#: not a pillar at all and goes to `shims`.
_SEATING = {"sets": "sets", "shimmed": "short"}


def _stack(d, boards, notes) -> dict:
    """What SETS each gap, never a gap: pcbl derives the gaps, the total and the
    keep-outs from these and the parts' heights, as `board_params.layer_gaps`
    does (📄 pcb-layout-tools docs/model.md, "Stack")."""
    names = {b["name"] for b in boards}
    order = [b for b in bp.STACK_ORDER if b in names]
    decks = {bp.FLOOR_NAME, bp.LID_NAME, *order}
    standoffs, shims = [], []
    for s in d.standoffs:
        if s.seating == "shim":
            shims.append({"name": s.name, "mm": float(s.height_mm)})
            continue
        below, above = s.between
        if below not in decks or above not in decks:
            notes.append(f"stack: the {s.name} standoff stands {below} -> {above}, a board "
                         f"the project does not place; not exported")
            continue
        standoffs.append({"name": s.name, "below": below, "above": above,
                          "mm": float(s.height_mm), "seating": _SEATING[s.seating]})
    out = {"order": order, "available_mm": bp.AVAIL_H, "clearance_mm": bp.CLEARANCE,
           "tail_mm": bp.TAIL,
           "floor": {"liner_mm": bp.FLOOR_LINER_T, "min_mm": bp.FLOOR_STANDOFF_MIN,
                     "seat": bp.FLOOR_SEAT, "seat_pad_mm": bp.THERMAL_PAD_T},
           "lid": True, "standoffs": standoffs}
    if shims:
        out["shims"] = shims
    return out


def export(project, d=None) -> Export:
    """The `layout.yaml` document for `project`, a `facts.load` result."""
    d = d or netlist.checked()
    ix = facts.Index(d)
    notes: list[str] = []
    used = set()
    for board in bp.STACK_ORDER:
        pcb = project.pcbs.get(board)
        if pcb is not None:
            used |= {c.footprint for c in pcb.components.values()}
    footprints = {u: _footprint(u, project.footprints[u]) for u in sorted(used)}
    classes = _net_classes(ix)
    boards = _boards(project, ix, notes)
    parts = _parts(d, ix, project, footprints, notes)
    exported = {p["refdes"] for p in parts}
    regions = _regions(d, ix, boards)
    reaches = _reaches(ix, notes)
    constraints = (_edge_groups(d, boards) + _clusters(ix, classes) + regions
                   + _keep_outs(ix, project) + _interfaces(d, ix) + reaches
                   + _corridors(ix) + _heavy_paths(ix) + _pour_spans(ix, boards)
                   + _twins(ix) + _region_returns(ix, classes, regions, reaches, boards))
    for c in constraints:
        refs = ([c.get("host"), c.get("satellite"), c.get("part"), c.get("lower"),
                 c.get("upper")] + list(c.get("parts", ())) + list(c.get("serves", ()))
                + list(c.get("ends", ())) + [r for r, _ in c.get("chain", ())]
                + [r for r, _ in c.get("pads", ())])
        missing = sorted({r for r in refs if r and r not in exported})
        if missing:
            raise SystemExit(f"layout_export: {c['kind']} {c['name']} names {missing}, "
                             f"which the project does not place")
    currents = _class_current_a(d, ix)
    doc = {
        "version": 1,
        "boards": boards,
        "footprints": list(footprints.values()),
        "netclasses": _netclasses(_used_classes(classes), currents, regions),
        "nets": _net_rows(ix, classes, [p["refdes"] for p in parts], currents),
        "parts": parts,
        "constraints": constraints,
        "stack": _stack(d, boards, notes),
    }
    return Export(doc, notes)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m tools.layout_export", description=__doc__.split(
        "\n\n")[0])
    ap.add_argument("project", help="the .eprj2 whose parts and footprints to describe")
    ap.add_argument("-o", "--output", help="where to write layout.yaml (default stdout)")
    args = ap.parse_args(argv)
    got = export(facts.load(args.project))
    text = got.text()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    for n in got.notes:
        print(f"layout_export: {n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
