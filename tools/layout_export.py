"""The body module described to `pcb-layout-tools`: generate its `layout.yaml`.

    python3 -m tools.layout_export PROJECT.eprj2 -o layout.yaml

`pcbl check PROJECT --constraints layout.yaml` then reads the DESIGN from the
file this writes and the LAYOUT (where everything stands, what copper is down)
from the project.  `tools/layout_hooks.py` goes beside the yaml: it answers the
pack-voltage nets' operating points, which are code (`soft_start`), not data.

⛔ ONE FACT, ONE HOME.  Nothing here is typed a second time.  Every figure is
read from where it already lives, and each block says where:

  boards       the project's own outline, holes and layer table; the inner
               layers' nets by `route.pour_plan`'s rule (R1); `place.M3_KEEPOUT`,
               `route.POUR_INSET` and `board_params.PCB_T`
  footprints   the project's FOOTPRINT documents, read the way pcbl reads them
               (`_footprint`), so the design and the layout see one geometry
  netclasses   `route`'s class table, with `place.CHANNEL_REACH` /
               `place.SIGNAL_REACH` as the routability reach of the classes
               check 20 binds, and `class_copper` on `route.heavy_classes`
  nets         every netlist net, in the class `route.net_class` gives it on
               each board it is on; `supply` from `place.Index`'s grounds and
               `rules.rails` (the nets that feed a part's SUPPLY pin); `order`,
               the netlist's own order of the net's pins, wherever it is not
               the parts' order -- which member a tie meets first
  parts        `netlist.checked()`: board, side, kind, height, body, and the
               pin map padmap already made the footprint's own pad names --
               in the netlist's order, which pcbl breaks its ties by
  constraints  the edge groups from `board_fit.edge_budget`; clusters from
               `place.served_contacts`; the HV region from `layout_rules`'
               HV nets; pairs from `board_params.layer_gaps`, the cable from
               `model.is_cabled`; reaches from `place.decoupler_hosts`, the
               ADC filters, the CAN transceiver and the programming land; the
               brake corridor from `place.brake_terminal` / `place.i2c_pullups`;
               the heavy path from `place.v12_output`; the V12 pour from
               `route.v12_line` / `place.v12_bus`; the ground twin from
               `route._return_twin`'s rule; the antenna and service
               keep-outs from `place`'s zones
  stack        `board_params.STACK_ORDER`, `layer_gaps`, `AVAIL_H`

Where the model cannot say what the legacy tools say, the exporter says so on
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

from tools import board_fit, eprj2, layout_rules, netlist, place, route
from tools import board_params as bp
from tools.eprj3.pcb import M3_INSET_MM
from tools.model import is_cabled

#: Mils per millimetre, EXACTLY.  ⚠️ Not `place.MIL_PER_MM` (39.3701, a
#: rounding): pcbl reads the same file at 1000 / 25.4, and a footprint drawn
#: here at the rounded figure would sit 0.3 um off the pads pcbl places --
#: enough to turn an exact-edge comparison the other way.
MIL_PER_MM = 1000 / 25.4

#: The copper layer types of a PCB document's LAYER table (the editor's own
#: vocabulary; `pcblayout.io.easyeda.records.COPPER_LAYER_TYPES`).
COPPER_LAYER_TYPES = ("TOP", "BOTTOM", "SIGNAL", "PLANE")
LAYER_TOP, LAYER_BOTTOM = 1, 2

#: `route`'s class table, strongest first -- the order `route._net_class`
#: tries them in.  A net that is two classes on two boards states the
#: strongest as its `net_class` and the others under `class_by_board`.
CLASSES = (route.HV, route.PWR12, route.PWR5AUX, route.CH12, route.CH5,
           route.DIFF, route.SENSE, route.RAIL, route.DEFAULT)

#: The routability reach of each class check 20 binds (`place.net_limit`):
#: a channel may run `CHANNEL_REACH` behind its terminal, anything else check
#: 20 measures `SIGNAL_REACH`.  HV, PWR12 and RAIL are not bound -- check 20
#: exempts HV nets and does not measure rails.
REACH = {route.CH12.name: place.CHANNEL_REACH, route.CH5.name: place.CHANNEL_REACH,
         route.PWR5AUX.name: place.SIGNAL_REACH, route.DIFF.name: place.SIGNAL_REACH,
         route.SENSE.name: place.SIGNAL_REACH, route.DEFAULT.name: place.SIGNAL_REACH}


def _mm(mil: float) -> float:
    return mil / MIL_PER_MM


def _exact(legacy_mm: float) -> float:
    """A length `place` read at its rounded conversion, re-read at the exact
    one: back to the file's mils, then to mm."""
    return _mm(legacy_mm * place.MIL_PER_MM)


def _ref_key(ref: str):
    return place._ref_key(ref)


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


def _footprint(uuid: str, records) -> dict:
    """A FOOTPRINT document as `layout.yaml` states one: every pad at
    `max(defaultPad, hole)`, and the body the union of the pads and what is
    drawn on the outline layers (`place.envelope`'s rule, at the exact mm).

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
            cx, cy = o["centerX"], o["centerY"]
            pts += [(cx - hw, cy - hh), (cx + hw, cy + hh)]
            number = str(o.get("num", "")).strip() or f"#{h.get('id')}"
            pad = {"number": number, "x": _mm(cx), "y": _mm(cy), "hw": _mm(hw), "hh": _mm(hh)}
            if (hole.get("width") or 0) > 0 or (hole.get("height") or 0) > 0:
                pad["crosses_board"] = True
            pad["shape"] = _pad_shape(dp)
            pads.append(pad)
        elif h["type"] in ("POLY", "FILL", "LINE"):
            o = json.loads(p)
            if o.get("layerId") in place.OUTLINE_LAYERS:
                if "path" in o:
                    place._path_points(o["path"], pts)
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
    footprint's X, l along its Y), turned the way `place.envelope` turns it:
    laid along the drawing's own long axis when the two disagree.  None where
    the netlist states no body."""
    w, l = body_mm
    if not (w and l):
        return None
    drawn = place.envelope(records, (0.0, 0.0))
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
def _net_classes(ix) -> dict:
    """{net: {board: class name}} for every board the net is on, by
    `route.net_class` -- the class differs by board where the copper does
    (`V12` is PWR12 where it carries the loads, RAIL where it is one trace to
    a converter).  A net on no placed part is {}."""
    out = {}
    for n in ix.members:                    # the netlist's order: it is stated order
        boards = sorted({ix.items[r].board for r, _ in ix.members[n] if r in ix.items})
        out[n] = {b: route.net_class(ix, b, n).name for b in boards}
    return out


def _net_rows(ix, classes, part_order) -> list:
    """The `nets` block.  `net_class` is the strongest of the net's classes;
    a board where it is another class is named under `class_by_board`.
    `supply` is the circuit's statement of a supply or a return: a ground
    (`ix.gnd`) or a net feeding a part's SUPPLY pin (`ix.rails`) -- what
    check 20 does not measure (`place.routed_nets`).  `order` is the
    netlist's order of the net's members (`ix.members`), stated wherever it
    differs from `part_order`: a band is lent by the first rail member met
    with the most pins (`place.bands`), and the netlist lists a net's pins in
    its own order, not its parts'."""
    rank = {c.name: i for i, c in enumerate(CLASSES)}
    at = {r: i for i, r in enumerate(part_order)}
    rows = []
    for n in classes:                       # the netlist's order, as `_net_classes` keeps it
        per = classes[n]
        base = min(per.values(), key=rank.__getitem__) if per else route.DEFAULT.name
        row = {"name": n, "net_class": base}
        other = {b: c for b, c in per.items() if c != base}
        if other:
            row["class_by_board"] = other
        if n in ix.gnd or n in ix.rails:
            row["supply"] = True
        met = list(dict.fromkeys(r for r, _ in ix.members[n] if r in at))
        if met != sorted(met, key=at.__getitem__):
            row["order"] = met
        rows.append(row)
    return rows


def _used_classes(classes) -> set:
    """Every class a net row names: a net on no placed part is DEFAULT."""
    used = {c for per in classes.values() for c in per.values()}
    if any(not per for per in classes.values()):
        used.add(route.DEFAULT.name)
    return used


#: The via the class-copper router may use on the classes of `VIA_CLASSES`:
#: 0.6 mm pad, 0.3 mm finished hole -- JLCPCB's standard via, no extra charge.
VIA_MM = (0.6, 0.3)
#: Via plating the fab states as its average (18 um), in mils -- the wall of
#: the barrel, and the whole of its current-carrying copper.
VIA_PLATING_MIL = 18e-3 / 25.4e-3
#: The temperature rise a via may take: the 10 degC the channel classes are
#: sized to (`route.CH12`), so a layer change runs no hotter than its tracks.
VIA_RISE_C = 10.0


def via_current_a(hole_mm: float = VIA_MM[1], plating_mil: float = VIA_PLATING_MIL,
                  rise_c: float = VIA_RISE_C) -> float:
    """What ONE via may carry: IPC-2221 for an INTERNAL conductor,
    `I = 0.024 * dT^0.44 * A^0.725` (A in mil^2), with the barrel's cross-
    section `A = pi * hole * plating` -- 26.3 mil^2 for a 0.3 mm hole in 18 um,
    0.707 A at 10 degC, taken DOWN to 0.70 A.  Conservative three ways: the
    internal constant is half the external one though a barrel reaches both
    faces; the finished hole, not the plating's mean diameter, sets the
    circumference; and the barrel's copper is taken at the fab's average
    plating, not its typical."""
    area = math.pi * (hole_mm / 25.4e-3) * plating_mil
    return math.floor(0.024 * rise_c ** 0.44 * area ** 0.725 * 100) / 100


#: The classes that state a via, and what sizes the cluster: the most any ONE
#: net of the class can carry.  ⛔ No HV via: a pack-voltage barrel through the
#: inner GND planes needs a 1.25 mm antipad in each, and HV stays on the faces
#: (`route.HV`).  PWR12 is a bus carried by a pour, CH5 has room on its face.
VIA_CLASSES = ("PWR5AUX", "CH12")


def _class_current_a(d, ix) -> dict:
    """{class: amps} for `VIA_CLASSES`, read off the circuit, never typed.

    CH12: the highest current limit any of its channels has -- each channel's
    own limiter at its ceiling (`power_budget._channel_limit_a`); a via sized
    for the typical channel would be a fuse on the strongest.  PWR5AUX: the four
    5 V channels' limiters at their ceiling together, `n5 x per_5v_a`
    (`power_budget.limit_case`), which is what the 5 V bus feeds.  A figure the
    circuit cannot give is a refusal, not a guess."""
    from tools import power_budget as pb
    out = {}
    amps = []
    for net in sorted(ix.classes.get("CH12", ())):
        a, why = pb._channel_limit_a(d, net)
        if why:
            raise SystemExit(f"layout_export: CH12 via current: {why}")
        amps.append(a)
    if amps:
        out["CH12"] = round(max(amps), 3)
    lim = pb.limit_case(d)
    if lim.per_5v_a is None or not lim.n5:
        raise SystemExit(f"layout_export: PWR5AUX via current: the 5 V channels' limit is "
                         f"not derivable ({'; '.join(lim.problems) or 'no 5 V channel'})")
    out["PWR5AUX"] = round(lim.n5 * lim.per_5v_a, 3)
    return out


def _netclasses(used, currents=None) -> list:
    currents = currents or {}
    out = []
    for c in CLASSES:
        if c.name not in used:
            continue
        row = {"name": c.name, "min_width_mm": c.width_mm,
               "clearance_mm": {"default": c.clearance_mm}}
        if c.pour_ok:
            row["pour"] = True
        if c is route.HV:
            # the pairwise figure is IPC-2221B B2 at the two nets' own
            # difference over the operating points `layout_hooks` answers
            # (IO-29) -- 1.25 mm stands wherever either has none
            row["pairwise_by_voltage"] = True
        if c.name in REACH:
            row["reach_mm"] = REACH[c.name]
        if c in route.heavy_classes():
            # the classes `route.py --heavy` lays by rule -- `pcbl route copper`
            row["class_copper"] = True
        if c.name in VIA_CLASSES and c.name in currents:
            # a layer change of ceil(current / per-via) vias (`pcbl`'s
            # `copper_via_current`): CH12 4, PWR5AUX 8
            row["current_a"] = currents[c.name]
            row["via_mm"] = list(VIA_MM)
            row["via_current_a"] = via_current_a()
        out.append(row)
    return out


def _third_layer_net(ix, board) -> tuple[str, str]:
    """(net, kind) of `board`'s second inner layer, by R1's rule
    (`route._third_layer`): the 12 V pour where a driver line takes the bus,
    else the rail with `RAIL_POUR_PINS`, else a second ground.  A rail poured
    over the whole board is a plane; the 12 V pour covers only the bus."""
    if route.v12_line(ix, board):
        return sorted(ix.classes["PWR12"])[0], "pour"
    rail = route._rail_pour_net(ix, board)
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
        out.append({
            "name": b, "length_mm": _exact(f.length), "width_mm": _exact(f.width),
            "portrait": bool(f.portrait), "thickness_mm": bp.PCB_T,
            "layers": [{"name": layers[0], "kind": "signal"},
                       {"name": layers[1], "kind": "plane", "net": _ground(ix, b)},
                       {"name": layers[2], "kind": kind, "net": third},
                       {"name": layers[3], "kind": "signal"}],
            "holes": sorted([_exact(u), _exact(v)] for u, v in f.holes),
            "hole_keepout_mm": place.M3_KEEPOUT,
            "pour_inset_mm": route.POUR_INSET})
    return out


def _parts(d, ix, project, footprints, notes) -> list:
    """The `parts` block, in the NETLIST's order -- `place.Index.items`, the
    parts then the connectors, each pin in the order the netlist lands it.
    ⚠️ The order is a fact of the design: pcbl breaks a tie by stated order,
    and legacy meets the parts in this one, so a sorted list would place tied
    parts differently from the placer it is held to."""
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
                    # check 6: inside the board end less the M3 inset
                    "span_mm": [M3_INSET_MM, length[e.board] - M3_INSET_MM],
                    # between two headers in the row (check 2)
                    "gap_mm": board_fit.HEADER_GAP})
    return out


def _clusters(ix, classes) -> list:
    out = []
    for board in bp.STACK_ORDER:
        for it in sorted(ix.on(board), key=lambda i: _ref_key(i.refdes)):
            served = place.served_contacts(ix, board, it.refdes)
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
    """POWER's HV/LV partition (check 18).  Its neutral nets are every
    GND-domain net (`place.hv_pins`: ground is on both sides by definition)
    that is not already the board's plane -- `BASEPLATE`, which `C203`/`C204`
    tie to the pack-voltage input, is ground and no plane carries it."""
    out = []
    for b in boards:
        if layout_rules.hv_nets(d, b["name"]):
            planes = {l["net"] for l in b["layers"] if l["kind"] == "plane"}
            on_board = {n for it in ix.on(b["name"]) for n in it.nets}
            row = {"kind": "region", "name": f"{b['name']}-HV", "board": b["name"],
                   "classes": [route.HV.name], "strip_mm": place.HV_STRIP,
                   "straddler": "member_pins_in", "edge_mm": place.HV_EDGE}
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
        for cap, host in sorted(place.decoupler_hosts(ix, board).items(),
                                key=lambda kv: _ref_key(kv[0])):
            out.append({"kind": "reach", "name": f"{cap}-DECOUPLE", "host": host,
                        "satellite": cap, "within_mm": place.DECOUPLE_REACH,
                        "reason": "a 100 nF decoupler beside the IC on its rail (check 15)"})
        module = next((it for it in ix.on(board) if it.kind == "MODULE"), None)
        if module is None:
            continue
        # check 14: an ADC input's RC beside the module
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
                            "satellite": r, "within_mm": place.ADC_REACH,
                            "reason": f"the filter on {n}, an ADC1 input, sits at the pin "
                                      f"(check 14)"})
        # check 14: the CAN transceiver by the stack contacts its pair leaves on
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
                            "within_mm": place.CAN_REACH, "measure": "shared_pins",
                            "reason": "the CAN pair stays short to the stack contacts "
                                      "(check 14)"})
                notes.append(f"reach: {it.refdes}-{conn.refdes}-CAN is measured pin to pin "
                             f"(worst shared pin); check 14 measures the transceiver's box "
                             f"centre to the centroid of the connector's CAN contacts")
        # check 20(b): the programming land by the module whose pins it carries
        land = next((it for it in ix.on(board) if it.kind == "CONN" and it.land), None)
        if land is not None:
            out.append({"kind": "reach", "name": f"{land.refdes}-PROG", "host": module.refdes,
                        "satellite": land.refdes, "within_mm": place.PROG_REACH,
                        "measure": "shared_pins",
                        "reason": "the land carries the module's own EN, IO0 and UART0 pins "
                                  "(D25)"})
    return out


def _heavy_paths(ix) -> list:
    """Check 19(a): the converter's 12 V output pins to the contact the bus
    leaves by.  One chain per (output pin, contact) pair, because check 19
    takes the WORST of them; pcbl measures each as a straight line between
    the pins, where check 19 measures u only."""
    out = []
    pwr12 = ix.classes["PWR12"]
    for board in bp.STACK_ORDER:
        src, away, _ = place.v12_output(ix, board)
        if src is None or away is None:
            continue
        mine = sorted({p for p, n in ix.items[src].pin_net.items() if n in pwr12}, key=_ref_key)
        theirs = sorted({p for p, n in ix.items[away].pin_net.items() if n in pwr12},
                        key=_ref_key)
        for a in mine:
            for b in theirs:
                out.append({"kind": "heavy_path", "name": f"{src}.{a}-{away}.{b}",
                            "chain": [[src, a], [away, b]], "max_mm": place.HEAVY_PATH_MM})
    return out


def _twins(ix) -> list:
    """The 12 V run's ground twin (`route._return_twin`): on a board that
    carries the bus, each ground that reaches both the converter and the
    contact the bus leaves by, over those two and the bus's other parts on
    that ground, laid beside the run at `PWR12`'s width."""
    out = []
    for board in bp.STACK_ORDER:
        src, away, parts = place.v12_output(ix, board)
        if src is None or away is None or not route.carries_bus(ix, board):
            continue
        for net in sorted(n for n in ix.gnd
                          if any(r == src for r, _ in ix.members.get(n, ()))
                          and any(r == away for r, _ in ix.members.get(n, ()))):
            refs = [src, away] + [r for r in parts
                                   if r != away and net in ix.items[r].nets]
            out.append({"kind": "twin", "name": f"{board}-{net}-RETURN", "board": board,
                        "net": net, "beside": route.PWR12.name, "parts": refs})
    return out


def _corridors(ix) -> list:
    """Check 14's brake clause: the I2C pull-ups keep `CORRIDOR_CLEAR` off
    the straight path the brake nets take from their harness terminal to the
    module -- the path `place.brake_terminal` finds and `place.i2c_pullups`'
    resistors keep clear of."""
    out = []
    for board in bp.STACK_ORDER:
        module = next((it for it in ix.on(board) if it.kind == "MODULE"), None)
        if module is None:
            continue
        term = place.brake_terminal(ix, board, module.refdes)
        pullups = place.i2c_pullups(ix, board)
        if term is None or not pullups:
            continue
        out.append({"kind": "corridor", "name": f"{term}-{module.refdes}-BRAKE",
                    "ends": [term, module.refdes], "parts": list(pullups),
                    "clear_mm": place.CORRIDOR_CLEAR,
                    "reason": "the brake nets' way to the module; the I2C bus's edges "
                              "stay off it (check 14)"})
    return out


def _pour_spans(ix, boards) -> list:
    """Check 11: the V12 pour covers the driver line's bus pins and the feed's
    own contacts, fed from inside."""
    out = []
    pwr12 = ix.classes["PWR12"]
    for b in boards:
        board = b["name"]
        drivers = route.v12_line(ix, board)
        if not drivers:
            continue
        _, feed = place.v12_bus(ix, board)
        layer = next(l for l in b["layers"] if l["kind"] == "pour")
        pads = [[r, p] for r in list(drivers) + ([feed] if feed else [])
                for p in sorted({p for p, n in ix.items[r].pin_net.items() if n in pwr12},
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
            env = place.envelope(project.footprints[comp.footprint], it.body)
            if it.kind == "MODULE":
                # check 8: the zone beyond the antenna end -- the module's
                # padless end, its footprint's +Y
                out.append({"kind": "keep_out", "name": f"{it.refdes}-ANTENNA", "board": board,
                            "box": [env.x0, env.y1, env.x1, env.y1 + place.ANTENNA_ZONE_D],
                            "reason": "the antenna end: nothing in the zone beyond it (check 8)",
                            "side": "both", "part": it.refdes,
                            "at_edge_mm": place.ANTENNA_EDGE})
            if it.kind == "CONN" and it.land:
                # check 16: the programming cable's plug at each end of the land
                w, dd, c = env.x1 - env.x0, env.y1 - env.y0, place.SERVICE_CLEAR
                zones = ([[env.x0 - c, env.y0, env.x0, env.y1], [env.x1, env.y0, env.x1 + c, env.y1]]
                         if w >= dd else
                         [[env.x0, env.y0 - c, env.x1, env.y0], [env.x0, env.y1, env.x1, env.y1 + c]])
                for tag, box in zip(("LO", "HI"), zones):
                    out.append({"kind": "keep_out", "name": f"{it.refdes}-SERVICE-{tag}",
                                "board": board, "box": box,
                                "reason": "the programming cable's plug at the land's end "
                                          "(check 16)",
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
    """The `layout.yaml` document for `project`, a `place.load` result."""
    d = d or netlist.checked()
    ix = place.Index(d)
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
    constraints = (_edge_groups(d, boards) + _clusters(ix, classes) + _regions(d, ix, boards)
                   + _keep_outs(ix, project) + _interfaces(d, ix) + _reaches(ix, notes)
                   + _corridors(ix) + _heavy_paths(ix) + _pour_spans(ix, boards)
                   + _twins(ix))
    for c in constraints:
        refs = ([c.get("host"), c.get("satellite"), c.get("part"), c.get("lower"),
                 c.get("upper")] + list(c.get("parts", ())) + list(c.get("serves", ()))
                + list(c.get("ends", ())) + [r for r, _ in c.get("chain", ())]
                + [r for r, _ in c.get("pads", ())])
        missing = sorted({r for r in refs if r and r not in exported})
        if missing:
            raise SystemExit(f"layout_export: {c['kind']} {c['name']} names {missing}, "
                             f"which the project does not place")
    doc = {
        "version": 1,
        "boards": boards,
        "footprints": list(footprints.values()),
        "netclasses": _netclasses(_used_classes(classes), _class_current_a(d, ix)),
        "nets": _net_rows(ix, classes, [p["refdes"] for p in parts]),
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
    got = export(place.load(args.project))
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
