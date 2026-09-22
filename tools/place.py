#!/usr/bin/env python3
"""PCB placement for the three-board stack -- the process in `layout/PROCESS.md`.

    python3 -m tools.place --stack [--anchor centre] [--keep REF ...] [--file PATH] [--out PATH]
    python3 -m tools.place --check [--file PATH]

`--stack` reads the owner's saved `.eprj2`, places every part of OUTPUTS, then
LOGIC, then POWER that is not in `--keep`, runs every check below, and writes
the file back through the same round trip the build uses (`eprj2.read` ->
edit records -> `eprj2.join` -> `eprj2.write` -> `eprj2.read`, refused if the
re-read differs).  `--check` re-reads a saved file and reports; it never writes.

THE FRAME.  The tool reasons in the BOARD frame of PROCESS.md: `u` along the
242 mm length, `v` across the 41.84 mm width, v = 0 the connector face, +v
toward the back edge.  The file holds the outline the build drew, which is
PORTRAIT -- 41.84 mm along X and 242 mm along Y (the M3 holes sit at (3.5, 3.5)
and (38.34, 238.5) mm) -- so the two frames differ by a rotation, read from the
outline at run time (`Frame`).  Positions in the placement tables are given in
both frames.  A footprint at board angle 0 has its pad row along u and its
local +Y toward the back edge.

THE EDITOR'S CONVENTIONS, verified against its own example projects (a track
lands on a pad only under one reading): a COMPONENT's `angle` is degrees
COUNTER-CLOCKWISE; a component on layer 2 is rotated in its own frame and then
MIRRORED ABOUT X.  `x`, `y` are mils.  A part's plan envelope is read from its
FOOTPRINT document (pads, top silk, component shape) and widened to the body
`netlist.py` states for it, so a courtyard is never smaller than either.

HV IS COPPER.  On POWER the 84 V rule binds a part's HV PADS where the
footprint names them (the bricks, the chokes, J101), and its whole body where
it does not (a D-PAK's pads are 1-2-3): the brick under the board puts pack
voltage on the top layer only at its input pins, and its output end is 12 V.

Stdlib only (plus what `eprj2` needs to decrypt the file).
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import board_fit, board_params as bp, build_project, eprj2, layout_rules  # noqa: E402
from tools import netlist, rules  # noqa: E402
from tools.eprj3.pcb import M3_INSET_MM  # noqa: E402

MIL_PER_MM = 39.3701
PROJECT_FILE = "revv1-module.eprj2"
#: One step of undo: the file as it was before this tool last wrote it.
PREV_SUFFIX = ".prev"

# --- clearances: every number says what it protects ------------------------------
#: Per side of every body, as `board_fit` budgets it (IPC-7351 generous).
COURTYARD = board_fit.COURTYARD
#: Between two courtyards on one face: one 0.2 mm trace with 0.2 mm of
#: clearance each side (JLC's 4-layer capability), so a trace can pass between
#: any two neighbours.  Body to body that is 2 x COURTYARD + TRACE_ROOM = 1.6.
TRACE_ROOM = 0.6
CLEAR = 2 * COURTYARD + TRACE_ROOM
#: Clear strips between the bands of PROCESS.md where one band's part stands
#: directly behind another's (their u-ranges overlap): the signals of a band
#: fan out through the strip in front of it.  Band 4 holds the S3, whose 25
#: STACK signals fan out there, so any strip that borders Band 4 is wider.
CHANNEL = 2.0
CHANNEL_BAND4 = 3.0
#: Around each M3 hole centre: a 7 mm washer, so a square of this half-side
#: at every corner holds no part.  The hole centres are read from the file.
M3_KEEPOUT = 3.5
#: 84 V copper keeps this from the board edge: the edge is where the
#: enclosure, a standoff or a finger meets the board (IPC-2221B B2 at 160 V is
#: 1.25; the edge gets more because it is uncontrolled).
HV_EDGE = 3.0
#: Courtyard to courtyard between 84 V copper and a low-voltage part: the HV
#: class clearance the owner sets up in the editor, as a placement proxy.
HV_CLEARANCE = layout_rules.HV_CLEARANCE_MM
#: The engine's target gap between the HV group and every LV part -- wider than
#: the check's floor so routing has the 1.25 mm class clearance to spend.
#: Also the adjacency under which the HV parts must form ONE group.
HV_STRIP = 3.0
HV_GAP = 2 * COURTYARD + HV_STRIP
#: The S3's antenna end within this of the back edge (the U.FL pigtail leaves
#: the board there), and nothing in a zone this wide x deep beyond it.
ANTENNA_EDGE = 2.0
ANTENNA_ZONE_W, ANTENNA_ZONE_D = 18.0, 8.0
#: The V12 bus on OUTPUTS: the centroid of the V12-fed ICs within this of the
#: contact that feeds them (J311), so 8.47 A is one short wide bus, not a tree.
BUS_REACH = 15.0
#: A through-hole connector longer than this, laid across the board's short
#: axis, cuts the ground plane in two.
PLANE_CUT = 40.0
#: The CAN transceiver within this of the STACK contacts that carry CANH/CANL.
CAN_REACH = 10.0
#: An ADC input's RC filter within this (edge to edge) of the S3.
ADC_REACH = 5.0
#: The I2C pull-ups keep this far from the straight path of the brake nets.
CORRIDOR_CLEAR = 5.0
#: A 100 nF decoupler within this (edge to edge) of the IC on its rail.
DECOUPLE_REACH = 3.0
#: Nothing within this of the Tag-Connect land along its long axis on either
#: end: the cable plug's body and its exit.  The entry end is not in the
#: drawing, so both ends are kept.
SERVICE_CLEAR = 5.0
#: Every board's Band 2 starts one channel behind its face row; Band 3 and 4
#: START where PROCESS.md's table puts them.  These are the fronts the packer
#: pulls toward, not walls: a part goes where it fits and is charged for the
#: distance (`Placer._slot`).
BAND_FRONT = {3: 19.0, 4: 30.0}
#: The packer scans v in this step; a courtyard is 0.5, so a finer step buys
#: nothing.
V_STEP = 0.5
#: What a millimetre of v costs against a millimetre of u in the packer.  A
#: band is SHALLOW: its parts spread along the terminal they serve, and only
#: start a second shelf when the first is full for 10 mm either side -- so
#: falling behind the band's front costs three times a sideways step, and
#: standing ahead of it (in the band in front) four times.
BEHIND_COST = 3.0
AHEAD_COST = 4.0
#: Two footprints coincide when every pad lands within this of its mate.
MATE_TOL = 0.01
#: A 100 nF ceramic on a rail and GND is a decoupler for the IC on that rail.
DECOUPLER_VALUE = "100nF"
#: The S3's ADC1 pins, IO1-IO10: the only analog-capable GPIOs on this board
#: (ADC2 dies with WiFi -- CLAUDE.md), so a net landing here is a SENSE net.
ADC1_PINS = frozenset(f"IO{n}" for n in range(1, 11))
#: Layers a footprint's outline is drawn on: top silk and the component shape.
OUTLINE_LAYERS = (3, 48)
#: A micrometre.  The file holds mils to four decimals (2.5 nm), so a
#: coordinate written and read back can move by a few nanometres; every
#: comparison in the checks allows this much, which no fab tolerance notices.
TOL = 1e-3

EXIT_PROBLEMS = 1
EXIT_REFUSED = 2


# --- geometry -----------------------------------------------------------------------
@dataclass(frozen=True)
class Box:
    """An axis-aligned rectangle in the board frame, mm."""
    u0: float
    v0: float
    u1: float
    v1: float

    @property
    def w(self):
        return self.u1 - self.u0

    @property
    def d(self):
        return self.v1 - self.v0

    @property
    def cu(self):
        return (self.u0 + self.u1) / 2

    @property
    def cv(self):
        return (self.v0 + self.v1) / 2

    def grow(self, m):
        return Box(self.u0 - m, self.v0 - m, self.u1 + m, self.v1 + m)

    def shift(self, du, dv):
        return Box(self.u0 + du, self.v0 + dv, self.u1 + du, self.v1 + dv)

    def gaps(self, o):
        """(gap along u, gap along v): positive = clear by that much on that
        axis, negative = overlapping by that much."""
        return (max(self.u0 - o.u1, o.u0 - self.u1), max(self.v0 - o.v1, o.v0 - self.v1))

    def overlaps(self, o, tol=TOL):
        gu, gv = self.gaps(o)
        return gu < -tol and gv < -tol

    def separation(self, o):
        """Body-to-body distance; 0 if they overlap."""
        gu, gv = self.gaps(o)
        if gu < 0 and gv < 0:
            return 0.0
        return math.hypot(max(gu, 0), max(gv, 0))

    def u_overlaps(self, o):
        return self.u0 < o.u1 and o.u0 < self.u1

    def v_overlaps(self, o):
        return self.v0 < o.v1 and o.v0 < self.v1


@dataclass(frozen=True)
class Frame:
    """The board frame (u along the length, v across, v = 0 the face) against
    the file's outline.  `portrait`: the file's long axis is Y, and the two
    frames differ by the rotation (u, v) -> (x, y) = (v, L - u) -- a proper
    rotation (determinant +1), so a footprint's angle carries over with a fixed
    offset and its handedness (which pin is where) is untouched."""
    length: float
    width: float
    portrait: bool
    holes: tuple = ()      # M3 centres, board frame

    def to_file(self, u, v):
        return (v, self.length - u) if self.portrait else (u, v)

    def to_board(self, x, y):
        return (self.length - y, x) if self.portrait else (x, y)

    def dir_to_board(self, dx, dy):
        return (-dy, dx) if self.portrait else (dx, dy)

    def file_angle(self, board_angle):
        return (board_angle - 90) % 360 if self.portrait else board_angle % 360

    def board_angle(self, file_angle):
        return (file_angle + 90) % 360 if self.portrait else file_angle % 360

    @property
    def corners(self):
        """The M3 washer keep-outs, as boxes."""
        return tuple(Box(u - M3_KEEPOUT, v - M3_KEEPOUT, u + M3_KEEPOUT, v + M3_KEEPOUT)
                     for u, v in self.holes)


def _rot(x, y, deg):
    c, s = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[deg % 360]
    return x * c - y * s, x * s + y * c


@dataclass(frozen=True)
class Envelope:
    """A footprint's plan in its own frame, mm: the box its pads, silk and
    stated body occupy, and each pad (number, centre x, y, half-width,
    half-height)."""
    x0: float
    y0: float
    x1: float
    y1: float
    pads: tuple = ()

    @property
    def centred(self):
        return abs(self.x0 + self.x1) < 0.1 and abs(self.y0 + self.y1) < 0.1


def _path_points(path, out):
    """Every (x, y) a V3 path visits, file units."""
    i = 0
    while i < len(path):
        t = path[i]
        if isinstance(t, list):
            _path_points(t, out)
            i += 1
        elif isinstance(t, str):
            if t == "CIRCLE" and i + 3 < len(path):
                cx, cy, r = path[i + 1:i + 4]
                out += [(cx - r, cy - r), (cx + r, cy + r)]
                i += 4
            elif t in ("ARC", "CARC"):
                i += 2                      # the keyword and its sweep; the end point follows
            elif t == "R" and i + 4 < len(path):
                x, y, w, h = path[i + 1:i + 5]
                out += [(x, y), (x + w, y - h)]
                i += 7
            else:
                i += 1
        elif isinstance(t, (int, float)) and i + 1 < len(path) \
                and isinstance(path[i + 1], (int, float)):
            out.append((t, path[i + 1]))
            i += 2
        else:
            i += 1


def envelope(records, body_mm):
    """The `Envelope` of a FOOTPRINT document's records, widened to `body_mm`
    (w, l) from the netlist.  The body is laid along the footprint's own long
    axis when the two disagree (a brick drawn upright), and centred on the
    drawn geometry; with nothing drawn it is centred on the origin."""
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
            pads.append((str(o.get("num", "")), cx / MIL_PER_MM, cy / MIL_PER_MM,
                         hw / MIL_PER_MM, hh / MIL_PER_MM))
        elif h["type"] in ("POLY", "FILL", "LINE"):
            o = json.loads(p)
            if o.get("layerId") in OUTLINE_LAYERS:
                if "path" in o:
                    _path_points(o["path"], pts)
                elif "startX" in o:
                    pts += [(o["startX"], o["startY"]), (o["endX"], o["endY"])]
    w, l = body_mm
    if pts:
        xs, ys = [x / MIL_PER_MM for x, _ in pts], [y / MIL_PER_MM for _, y in pts]
        gx0, gx1, gy0, gy1 = min(xs), max(xs), min(ys), max(ys)
        gw, gl = gx1 - gx0, gy1 - gy0
        if w and l and ((gw > 1.2 * gl and l > 1.2 * w) or (gl > 1.2 * gw and w > 1.2 * l)):
            w, l = l, w
        cx, cy = (gx0 + gx1) / 2, (gy0 + gy1) / 2
        return Envelope(min(gx0, cx - w / 2), min(gy0, cy - l / 2),
                        max(gx1, cx + w / 2), max(gy1, cy + l / 2), tuple(pads))
    return Envelope(-w / 2, -l / 2, w / 2, l / 2, tuple(pads))


def _place_point(frame, lx, ly, u, v, board_angle, bottom):
    rx, ry = _rot(lx, ly, frame.file_angle(board_angle))
    if bottom:
        rx = -rx
    du, dv = frame.dir_to_board(rx, ry)
    return u + du, v + dv


def _place_box(frame, x0, y0, x1, y1, u, v, board_angle, bottom):
    pts = [_place_point(frame, lx, ly, u, v, board_angle, bottom)
           for lx, ly in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    return Box(min(p[0] for p in pts), min(p[1] for p in pts),
               max(p[0] for p in pts), max(p[1] for p in pts))


def placed_box(env, frame, u, v, board_angle, bottom):
    """The board-frame box of `env` with its origin at (u, v)."""
    return _place_box(frame, env.x0, env.y0, env.x1, env.y1, u, v, board_angle, bottom)


def placed_pads(env, frame, u, v, board_angle, bottom):
    """[(pad number, u, v)] of `env` with its origin at (u, v).  Pads are
    named by the pin they carry (padmap.py renamed them before embedding),
    and one pin can own several pads."""
    return [(num,) + _place_point(frame, lx, ly, u, v, board_angle, bottom)
            for num, lx, ly, _, _ in env.pads]


def placed_pad_boxes(env, frame, u, v, board_angle, bottom):
    """[(pad number, Box)] of `env` with its origin at (u, v)."""
    return [(num, _place_box(frame, lx - hw, ly - hh, lx + hw, ly + hh, u, v, board_angle, bottom))
            for num, lx, ly, hw, hh in env.pads]


# --- the file ----------------------------------------------------------------------
@dataclass
class Component:
    """One COMPONENT record of a PCB document and what hangs off it."""
    refdes: str
    record: int                 # index into the stream's records
    footprint: str              # FOOTPRINT uuid
    x: float                    # mils, as saved
    y: float
    angle: int
    layer: int
    labels: tuple = ()          # ATTR records with a position (Designator ...)


@dataclass
class PcbDoc:
    title: str
    uuid: str
    frame: Frame
    components: dict            # refdes -> Component


@dataclass
class Project:
    """The owner's project, as read: the records, the boards, the footprints."""
    snap: dict
    records: list
    pcbs: dict                  # board title -> PcbDoc
    footprints: dict            # footprint uuid -> records
    envelopes: dict = field(default_factory=dict)

    def envelope(self, comp, body_mm):
        key = (comp.footprint, tuple(body_mm))
        if key not in self.envelopes:
            self.envelopes[key] = envelope(self.footprints.get(comp.footprint, []), body_mm)
        return self.envelopes[key]


def _outline_frame(recs):
    """The `Frame` of a PCB document: its BOARD_OUTLINE rectangle and M3 holes."""
    rect, holes = None, []
    for h, p in recs:
        if h["type"] == "POLY":
            o = json.loads(p)
            if o.get("polyType") == "BOARD_OUTLINE" and o["path"][0] == "R":
                _, x, y, w, hh = o["path"][:5]
                rect = (x / MIL_PER_MM, (y - hh) / MIL_PER_MM, (x + w) / MIL_PER_MM, y / MIL_PER_MM)
        elif h["type"] == "PAD":
            o = json.loads(p)
            if not o.get("plated", True) and o.get("hole"):
                holes.append((o["centerX"] / MIL_PER_MM, o["centerY"] / MIL_PER_MM))
    if rect is None:
        raise ValueError("PCB has no rectangular BOARD_OUTLINE")
    x0, y0, x1, y1 = rect
    if abs(x0) > TOL or abs(y0) > TOL:
        raise ValueError(f"the outline's corner is at ({x0:.3f}, {y0:.3f}) mm, not the origin")
    portrait = (y1 - y0) > (x1 - x0)
    frame = Frame((y1 - y0) if portrait else (x1 - x0), (x1 - x0) if portrait else (y1 - y0),
                  portrait)
    return replace(frame, holes=tuple(sorted(frame.to_board(x, y) for x, y in holes)))


def load(path):
    """Read `path` into a `Project`."""
    snap = eprj2.read(path)
    records = eprj2.split_records(snap["text"])
    lead, docs = eprj2.documents(records)
    footprints, pcbs = {}, {}
    pos = len(lead)
    for doc_type, uuid, recs in docs:
        start = pos
        pos += len(recs)
        if doc_type == "FOOTPRINT":
            footprints[uuid] = recs
        elif doc_type == "PCB":
            title = next(json.loads(p)["title"] for h, p in recs if h["type"] == "META")
            comps, labels, fps = {}, {}, {}
            for i, (h, p) in enumerate(recs):
                if h["type"] == "ATTR":
                    a = json.loads(p)
                    if a.get("key") == "Footprint":
                        fps[a["parentId"]] = a["value"]
                    elif a.get("key") == "Designator":
                        comps[a["parentId"]] = a["value"]
                    if a.get("x") is not None and a.get("parentId"):
                        labels.setdefault(a["parentId"], []).append(start + i)
            found = {}
            for i, (h, p) in enumerate(recs):
                if h["type"] == "COMPONENT" and h["id"] in comps:
                    c = json.loads(p)
                    ref = comps[h["id"]]
                    found[ref] = Component(ref, start + i, fps.get(h["id"], ""), c["x"], c["y"],
                                           int(round(c.get("angle") or 0)) % 360,
                                           int(c.get("layerId") or 1),
                                           tuple(labels.get(h["id"], ())))
            pcbs[title] = PcbDoc(title, uuid, _outline_frame(recs), found)
    return Project(snap, records, pcbs, footprints)


# --- the design, indexed for placement ---------------------------------------------
PASSIVE_KINDS = frozenset({"R", "C", "D", "ZENER", "TVS", "FUSE"})


@dataclass
class Item:
    """A part or connector of one board, with what the engine needs of it."""
    refdes: str
    board: str
    side: str
    kind: str                   # Part.kind, or "CONN"
    height: float
    body: tuple                 # netlist footprint_mm
    nets: dict                  # net name -> pin count on this item
    harness: bool = False
    interface: str | None = None
    mpn: str = ""
    value: str = ""
    dnp: bool = False
    land: str = ""
    pin_net: dict = field(default_factory=dict)   # pin -> net


class Index:
    """`netlist.checked()` from the placer's point of view."""

    def __init__(self, d):
        self.d = d
        self.items = {}
        for p in d.parts:
            self.items[p.refdes] = Item(p.refdes, p.board, p.side, p.kind, p.height_mm,
                                        tuple(p.footprint_mm), {}, mpn=p.mpn, value=p.value,
                                        dnp=p.dnp)
        for c in d.connectors:
            self.items[c.refdes] = Item(c.refdes, c.board, c.side, "CONN", c.height_mm,
                                        tuple(c.footprint_mm), {}, harness=c.leaves_box,
                                        interface=c.interface, dnp=c.dnp, land=c.land,
                                        pin_net={cp.pin: cp.net for cp in c.pins})
        self.net = {n.name: n for n in d.nets}
        self.members = {}                       # net -> [(refdes, pin)]
        for n in d.nets:
            self.members[n.name] = list(n.pins)
            for r, pin in n.pins:
                it = self.items.get(r)
                if it is not None:
                    it.nets[n.name] = it.nets.get(n.name, 0) + 1
                    it.pin_net.setdefault(pin, n.name)
        self.gnd = {n.name for n in d.nets if n.domain == "GND"}
        self.rails = set(rules.rails(d))
        self.hv = {b: set(layout_rules.hv_nets(d, b)) for b in bp.STACK_ORDER}
        self.classes = power_classes(d)
        self.gaps = {(g.below, g.above): g for g in bp.layer_gaps(d)}

    def on(self, board, side=None):
        return [i for i in self.items.values()
                if i.board == board and (side is None or i.side == side)]

    def signal(self, net):
        return net not in self.gnd and net not in self.rails

    def is_hv(self, ref):
        it = self.items[ref]
        return any(n in self.hv.get(it.board, ()) for n in it.nets)

    def weight(self, board, net):
        """Pin weight of `net` for the adjacency centroid: GND is a plane and
        pulls nothing; pack-voltage nets and the 12 V bus are wide copper that
        must stay short; other rails are everywhere and barely count; a signal
        counts once per pin."""
        if net in self.gnd:
            return 0.0
        if net in self.hv.get(board, ()) or net in self.classes["PWR12"]:
            return 10.0
        if net in self.rails:
            return 0.2
        return 1.0


def power_classes(d):
    """Routing classes derived from the COPPER, never from a net's name:
    PWR12 is the net U201's +V is on; CH12 a net with a TPS4H160B OUTx pin;
    CH5 a net with a TPS2553 OUT pin; PWR5AUX the buck's SW net and the nets of
    the inductor on it; SENSE a net on a TPS4H160B CS pin, or a net landing on
    an S3 ADC1 pin that a capacitor filters (the coordinator's rule was every
    ADC1 net, which would class TWAI_TX and FAN_CMD -- digital lines that
    happen to use IO6-IO10 -- as analog).  A net named AUX5V_n_FAULT carries a
    logic level; it has no driver pin, and that is why it is not CH5."""
    out = {"PWR12": set(), "CH12": set(), "CH5": set(), "PWR5AUX": set(), "SENSE": set()}
    by = {p.refdes: p for p in d.parts}
    sw, adc = set(), set()
    for n in d.nets:
        for ref, pin in n.pins:
            p = by.get(ref)
            if p is None:
                continue
            mpn = p.mpn.upper()
            if ref == bp.FLOOR_SEAT and pin == "+V":
                out["PWR12"].add(n.name)
            if "TPS4H160" in mpn and pin.startswith("OUT"):
                out["CH12"].add(n.name)
            if "TPS4H160" in mpn and pin.startswith("CS"):
                out["SENSE"].add(n.name)
            if "TPS2553" in mpn and pin == "OUT":
                out["CH5"].add(n.name)
            if p.kind == "IC" and pin == "SW":
                sw.add(n.name)
            if "ESP32" in mpn and pin in ADC1_PINS:
                adc.add(n.name)
    # PWR5AUX: the buck's switch node and the inductor's far end, both carrying
    # the 1.39 A output current.
    for n in d.nets:
        if n.name in sw:
            out["PWR5AUX"].add(n.name)
            for ref, _ in n.pins:
                if ref in by and by[ref].kind == "L":
                    out["PWR5AUX"] |= {m.name for m in d.nets_of(ref)}
    # SENSE: an ADC1 net is analog when a capacitor filters it; IO6-IO10
    # drive the CAN transceiver and the drivers' SEL/SEH/DIAG digitally.
    for n in d.nets:
        if n.name in adc and any(ref in by and by[ref].kind == "C" for ref, _ in n.pins):
            out["SENSE"].add(n.name)
    return out


def bands(ix, board):
    """refdes -> band (1..4) for every item on `board`, from the copper:

      1  a harness terminal (the face row);
      4  the S3 module, every inter-board connector, an IC that shares a
         signal net with the S3 and none with a terminal, and an IC with no
         signal nets that shares a rail with the S3 (its LDO, its supervisor);
      2  a passive on a net that reaches a harness terminal, or one hop from
         one through a signal net (the class-A cap behind its series R);
      3  every other IC, FET, choke, clip or converter -- and an IC of the same
         part number as a Band 3 IC (the second and third drivers, the second
         expander);
      a passive not in Band 2 takes the band of the function part it shares a
      signal net with, else of the rail partner with the most pins, else 4.
    """
    items = ix.on(board)
    band = {}
    terminal_nets = set()
    for it in items:
        if it.kind == "CONN":
            band[it.refdes] = 1 if it.harness else 4
            if it.harness:
                terminal_nets |= {n for n in it.nets if ix.signal(n)}
    for it in items:
        if it.kind == "MODULE":
            band[it.refdes] = 4
    passives = [it for it in items if it.kind in PASSIVE_KINDS]
    for it in passives:
        if any(n in terminal_nets for n in it.nets):
            band[it.refdes] = 2
    hop = set()
    for it in passives:
        if it.refdes in band:
            continue
        for n in it.nets:
            if ix.signal(n) and any(
                    band.get(r) == 2 and ix.items[r].kind in PASSIVE_KINDS
                    for r, _ in ix.members[n] if r != it.refdes and r in ix.items):
                hop.add(it.refdes)
    for r in hop:
        band[r] = 2
    module = next((it for it in items if it.kind == "MODULE"), None)
    functions = [it for it in items if it.kind not in PASSIVE_KINDS and it.refdes not in band]

    def touches_terminal(it):
        for n in it.nets:
            if not ix.signal(n):
                continue
            if n in terminal_nets:
                return True
            if any(band.get(r) == 2 for r, _ in ix.members[n] if r != it.refdes):
                return True
        return False

    for it in functions:
        if touches_terminal(it):
            band[it.refdes] = 3
    for it in functions:
        if it.refdes not in band and any(
                band.get(o.refdes) == 3 and o.mpn == it.mpn for o in functions if o is not it):
            band[it.refdes] = 3
    for it in functions:
        if it.refdes in band:
            continue
        signals = {n for n in it.nets if ix.signal(n)}
        with_module = module is not None and any(
            module.refdes in {r for r, _ in ix.members[n]} for n in signals)
        shares_rail = module is not None and any(
            n in ix.rails and n in module.nets for n in it.nets)
        band[it.refdes] = 4 if with_module or (not signals and shares_rail) else 3
    for it in passives:
        if it.refdes in band:
            continue
        # the function part it serves: an IC or FET before the module, and a
        # connector only when nothing else is on the net
        rank = {"CONN": 2, "MODULE": 1}
        partner, best = None, 9
        for n in it.nets:
            if not ix.signal(n):
                continue
            for r, _ in ix.members[n]:
                if r != it.refdes and r in band and ix.items[r].kind not in PASSIVE_KINDS:
                    score = rank.get(ix.items[r].kind, 0)
                    if score < best:
                        partner, best = r, score
        if partner is None:
            best = 0
            for n in it.nets:
                if n in ix.rails:
                    for r, _ in ix.members[n]:
                        if r != it.refdes and r in band:
                            w = ix.items[r].nets.get(n, 0)
                            if w > best:
                                best, partner = w, r
        band[it.refdes] = band[partner] if partner else 4
    return band


def decouplers(ix, board):
    """{cap refdes: rail net} for every 100 nF on `board` whose two nets are a
    rail and ground: the ICs on that rail are the ones it decouples."""
    out = {}
    for it in ix.on(board):
        if it.kind == "C" and it.value.startswith(DECOUPLER_VALUE):
            nets = set(it.nets)
            rail = [n for n in nets if n in ix.rails]
            if len(rail) == 1 and (nets - {rail[0]}) <= ix.gnd:
                out[it.refdes] = rail[0]
    return out


def ics_on(ix, board, net):
    return [it for it in ix.on(board)
            if it.kind in ("IC", "MODULE", "CONVERTER") and net in it.nets]


# --- a placement ------------------------------------------------------------------
@dataclass
class Placed:
    refdes: str
    board: str
    u: float                    # origin, board frame mm
    v: float
    angle: int                  # board angle
    layer: int
    band: int
    reason: str
    box: Box                    # body + drawn envelope, board frame
    env: Envelope
    height: float
    kept: bool = False

    @property
    def bottom(self):
        return self.layer == 2

    @property
    def unplaced(self):
        return self.reason.startswith("UNPLACED")

    def pads(self, frame):
        return placed_pads(self.env, frame, self.u, self.v, self.angle, self.bottom)

    def pad_boxes(self, frame):
        return placed_pad_boxes(self.env, frame, self.u, self.v, self.angle, self.bottom)

    def pin_point(self, frame, pin):
        """Where `pin` is, board frame: the mean of its pads, else the body centre."""
        pts = [(u, v) for num, u, v in self.pads(frame) if num == pin]
        if not pts:
            return self.box.cu, self.box.cv
        return sum(u for u, _ in pts) / len(pts), sum(v for _, v in pts) / len(pts)

    def hv_zones(self, ix, frame):
        """The boxes of this part that carry pack voltage: its HV pads where
        the footprint names them, else -- for an HV part -- its whole body."""
        return hv_zones(ix, self.refdes, self.pad_boxes(frame), self.box)


def hv_zones(ix, ref, pad_boxes, body):
    it = ix.items[ref]
    hv = ix.hv.get(it.board, ())
    zones = [b for num, b in pad_boxes if it.pin_net.get(num) in hv]
    if not zones and any(n in hv for n in it.nets):
        zones = [body]
    return zones


class Placement:
    """Every placed item of every board, in the board frame."""

    def __init__(self, project, ix):
        self.project = project
        self.ix = ix
        self.boards = {b: {} for b in bp.STACK_ORDER}
        self.notes = []

    def frame(self, board):
        return self.project.pcbs[board].frame

    def add(self, p):
        self.boards[p.board][p.refdes] = p

    def get(self, ref):
        for b in self.boards.values():
            if ref in b:
                return b[ref]
        return None

    def face(self, board, layer):
        return [p for p in self.boards[board].values() if p.layer == layer]

    @classmethod
    def from_file(cls, project, ix):
        """The placement the file holds, item by item."""
        pl = cls(project, ix)
        for board, doc in project.pcbs.items():
            if board not in pl.boards:
                continue
            band = bands(ix, board)
            for ref, comp in doc.components.items():
                it = ix.items.get(ref)
                if it is None or it.board != board:
                    continue
                env = project.envelope(comp, it.body)
                u, v = doc.frame.to_board(comp.x / MIL_PER_MM, comp.y / MIL_PER_MM)
                ang = doc.frame.board_angle(comp.angle)
                box = placed_box(env, doc.frame, u, v, ang, comp.layer == 2)
                pl.add(Placed(ref, board, u, v, ang, comp.layer, band.get(ref, 0),
                              "as saved", box, env, it.height, kept=True))
        return pl


# --- the engine -------------------------------------------------------------------
class Placer:
    """Places one board's items in the board frame: the face row, then Bands
    2, 3, 4 by net adjacency, greedy first-fit.  See `layout/PROCESS.md`."""

    def __init__(self, placement, board, anchor="centre", keep=(), relaxed=False):
        self.pl = placement
        self.ix = placement.ix
        self.project = placement.project
        self.board = board
        self.doc = self.project.pcbs[board]
        self.frame = self.doc.frame
        self.anchor = anchor
        self.keep = set(keep)
        #: A second pass for a board that could not seat every part at the
        #: engine's target strip: the HV gap falls back to the check's floor.
        self.relaxed = relaxed
        self.hv_gap = (2 * COURTYARD + HV_CLEARANCE) if relaxed else HV_GAP
        self.target_pt = {}         # refdes -> (u, v_front, why): a point to sit at
        self.near = {}              # refdes -> host refdes: sit against its body
        self.near_why = {}
        self.band = bands(self.ix, board)
        self.decouple = decouplers(self.ix, board)
        # cap -> the IC it sits beside: the ICs on a rail take its 100 nFs in
        # turn, so every IC on the rail gets one before any gets two
        self.host_of = {}
        for rail in sorted(set(self.decouple.values())):
            caps = sorted((c for c, r in self.decouple.items() if r == rail), key=_ref_key)
            hosts = sorted((i.refdes for i in ics_on(self.ix, board, rail)), key=_ref_key)
            for i, cap in enumerate(caps):
                if hosts:
                    self.host_of[cap] = hosts[i % len(hosts)]
        self.hv_board = board == "POWER"
        self.extra = {}             # refdes -> [Box] keep-outs that bind it alone
        self.target_u = {}          # refdes -> (u, why) the engine must aim at
        self.target_v = {}          # refdes -> (box front v, why)

    # -- helpers ------------------------------------------------------------------
    def item(self, ref):
        return self.ix.items[ref]

    def env(self, ref):
        return self.project.envelope(self.doc.components[ref], self.item(ref).body)

    def is_hv(self, ref):
        return self.hv_board and self.ix.is_hv(ref)

    def layer_of(self, ref):
        return 2 if self.item(ref).side == "bottom" else 1

    def make(self, ref, u, v, angle, band, reason, kept=False):
        env = self.env(ref)
        layer = self.layer_of(ref)
        box = placed_box(env, self.frame, u, v, angle, layer == 2)
        return Placed(ref, self.board, u, v, angle, layer, band, reason, box, env,
                      self.item(ref).height, kept)

    def _channel(self, band_a, band_b):
        if band_a == band_b or 0 in (band_a, band_b):
            return CLEAR
        return CHANNEL_BAND4 if 4 in (band_a, band_b) else CHANNEL

    def _obstacles(self, ref, band, layer):
        """([(box, gap u, gap v)] the BODY must clear, [(box, gap u, gap v)]
        each of the part's own HV ZONES must clear).  HV copper and an LV body
        keep the strip on either face; two bodies on one face keep CLEAR, or
        the channel between their bands."""
        hv = self.is_hv(ref)
        body, zones = [], []
        for p in self.pl.boards[self.board].values():
            if p.unplaced:
                continue
            if p.layer == layer:
                body.append((p.box, CLEAR, self._channel(band, p.band)))
            if self.hv_board and self.ix.is_hv(p.refdes) != hv:
                if hv:
                    zones.append((p.box, self.hv_gap, self.hv_gap))
                else:
                    body += [(z, self.hv_gap, self.hv_gap) for z in p.hv_zones(self.ix, self.frame)]
        body += [(c, 0.0, 0.0) for c in self.frame.corners]
        body += [(k, 0.0, 0.0) for k in self.extra.get(ref, ())]
        for p in self.pl.boards[self.board].values():
            if p.unplaced:
                continue
            if self.item(p.refdes).land and layer == 1:
                # the programming land's cable ends stay clear (check 16)
                body += [(z, 0.0, 0.0) for z in service_zones(p.box)]
            if self.item(p.refdes).kind == "MODULE":
                # the antenna zone beyond the S3 stays clear on both faces (check 8)
                body.append((Box(p.box.u0, p.box.v1, p.box.u1, p.box.v1 + ANTENNA_ZONE_D), 0.0, 0.0))
        return body, zones

    def _margins(self, ref, off, zones):
        """How close each body edge may come to the board edge: an HV part's
        copper keeps HV_EDGE, and its body may reach the edge only by the
        inset of that copper inside the body."""
        if not zones:
            return 0.0, 0.0, 0.0, 0.0
        z0u = min(z.u0 for z in zones) - off.u0
        z0v = min(z.v0 for z in zones) - off.v0
        z1u = off.u1 - max(z.u1 for z in zones)
        z1v = off.v1 - max(z.v1 for z in zones)
        return (max(0.0, HV_EDGE - z0u), max(0.0, HV_EDGE - z0v),
                max(0.0, HV_EDGE - z1u), max(0.0, HV_EDGE - z1v))

    def _slot(self, ref, band, angle, target_u, v_front, back_flush=False, near=None):
        """The cheapest free origin for `ref` at `angle`: nearest `target_u`,
        then nearest `v_front` (ahead of it costs more).  With `near`, a Box,
        the cost is the body's distance from that box instead: a satellite
        sits against its host whichever side is free.  None if it fits nowhere
        on its face."""
        env = self.env(ref)
        layer = self.layer_of(ref)
        bottom = layer == 2
        off = placed_box(env, self.frame, 0.0, 0.0, angle, bottom)
        a, b = off.w, off.d
        L, W = self.frame.length, self.frame.width
        zones = []
        if self.is_hv(ref):
            zones = hv_zones(self.ix, ref, placed_pad_boxes(env, self.frame, 0.0, 0.0, angle, bottom),
                             placed_box(env, self.frame, 0.0, 0.0, angle, bottom))
        mu0, mv0, mu1, mv1 = self._margins(ref, off, zones)
        body_obs, zone_obs = self._obstacles(ref, band, layer)
        # each HV zone as an offset from the body's corner; the attached zones
        # (antenna, cable ends) likewise, against every placed body
        zone_off = [(z.u0 - off.u0, z.v0 - off.v0, z.u1 - off.u0, z.v1 - off.v0) for z in zones]
        attached = self.attached(ref, angle)
        if attached:
            zone_off += attached
            zone_obs = list(zone_obs) + [(p.box, 0.0, 0.0) for p in self.pl.boards[self.board].values()
                                          if not p.unplaced]
        best = None
        v0 = mv0
        while v0 + b <= W - mv1 + 1e-9:
            forbidden = []
            for box, gu, gv in body_obs:
                if v0 >= box.v1 + gv - 1e-9 or v0 + b <= box.v0 - gv + 1e-9:
                    continue
                forbidden.append((box.u0 - gu - a, box.u1 + gu))
            for zu0, zv0, zu1, zv1 in zone_off:
                for box, gu, gv in zone_obs:
                    if v0 + zv0 >= box.v1 + gv - 1e-9 or v0 + zv1 <= box.v0 - gv + 1e-9:
                        continue
                    forbidden.append((box.u0 - gu - zu1, box.u1 + gu - zu0))
            forbidden.sort()
            free, lo = [], mu0
            hi_lim = L - mu1 - a
            for f0, f1 in forbidden:
                if f0 > lo:
                    free.append((lo, min(f0, hi_lim)))
                lo = max(lo, f1)
            if lo <= hi_lim:
                free.append((lo, hi_lim))
            want = target_u - a / 2
            for f0, f1 in free:
                if f1 < f0 - 1e-9:
                    continue
                u0 = min(max(want, f0), f1)
                dv = v0 - v_front
                if near is not None:
                    cost = Box(u0, v0, u0 + a, v0 + b).separation(near) + 0.1 * abs(u0 - want)
                else:
                    cost = abs(u0 - want) + (AHEAD_COST * -dv if dv < 0 else
                                             (AHEAD_COST if back_flush else BEHIND_COST) * dv)
                if best is None or cost < best[0]:
                    best = (cost, u0 - off.u0, v0 - off.v0)
            v0 += V_STEP
        return None if best is None else (best[1], best[2], best[0])

    def centroid_u(self, ref):
        """Pin-weighted centroid (u) of the placed items sharing `ref`'s nets;
        None when nothing it touches is placed yet."""
        it = self.item(ref)
        num = den = 0.0
        partners = set()
        for net in it.nets:
            w = self.ix.weight(self.board, net)
            if w <= 0:
                continue
            for r, pin in self.ix.members[net]:
                if r == ref:
                    continue
                p = self.pl.boards[self.board].get(r)
                if p is None or p.unplaced:
                    continue
                num += w * p.pin_point(self.frame, pin)[0]
                den += w
                partners.add(r)
        if den <= 0:
            return None, []
        return num / den, sorted(partners, key=_ref_key)

    # -- the row ------------------------------------------------------------------
    def row(self, side):
        edge = next((e for e in board_fit.edge_budget(self.ix.d)
                     if e.board == self.board and e.side == side), None)
        if edge is None:
            return
        headers = [r for r in edge.headers if r in self.doc.components and r not in self.keep]
        if not headers:
            return
        bottom = side == "bottom"
        boxes = {}
        for ref in headers:
            env = self.env(ref)
            # The body extends farther from the pad row on its plug side, and
            # that side faces the edge: board angle 0 or 180.
            best = None
            for ang in (0, 180):
                box = placed_box(env, self.frame, 0.0, 0.0, ang, bottom)
                pv = placed_pads(env, self.frame, 0.0, 0.0, ang, bottom)
                pad_v = (sum(v for _, _, v in pv) / len(pv)) if pv else 0.0
                toward_face = pad_v - box.cv
                if best is None or toward_face > best[0] + 1e-9:
                    best = (toward_face, ang, box)
            boxes[ref] = best[1:]
        gaps = []
        for a, b in zip(headers, headers[1:]):
            g = board_fit.HEADER_GAP
            if self.is_hv(a) != self.is_hv(b):
                g = max(g, self.hv_gap)      # the HV strip, where the row changes class
            gaps.append(g)
        total = sum(boxes[r][1].w for r in headers) + sum(gaps)
        L = self.frame.length
        corner = 2 * M3_KEEPOUT if self.frame.holes else 2 * M3_INSET_MM
        start = {"left": corner, "right": L - corner - total}.get(self.anchor, (L - total) / 2)
        u = start
        for i, ref in enumerate(headers):
            ang, box = boxes[ref]
            reason = (f"face row ({edge.side}), position {i + 1} of {len(headers)} in "
                      f"edge_budget order, body v 0-{box.d:.1f}")
            self.pl.add(self.make(ref, u - box.u0, -box.v0, ang, 1, reason))
            u += box.w + (gaps[i] if i < len(gaps) else 0)

    # -- the bands ----------------------------------------------------------------
    def pending(self, band=None):
        return [r for r, b in self.band.items()
                if (band is None or b == band) and r in self.doc.components
                and r not in self.pl.boards[self.board]]

    def place_band(self, band, only=None):
        refs = [r for r in self.pending(band) if only is None or r in only]
        area = {r: (self.env(r).x1 - self.env(r).x0) * (self.env(r).y1 - self.env(r).y0) for r in refs}
        # fixed-position items first, so the rest gather round them; then the
        # function parts (an IC anchors its passives), then passives; each by
        # area; a decoupler waits for its host and follows it at once
        def order(r):
            fixed = 0 if r in self.target_u or r in self.target_v else 1
            passive = 1 if self.item(r).kind in PASSIVE_KINDS | {"L"} else 0
            return (fixed, passive, -area[r], _ref_key(r))
        refs.sort(key=order)
        for ref in refs:
            if ref in self.pl.boards[self.board]:
                continue                      # placed already, as a satellite
            if self.host(ref) is not None and self.host(ref) not in self.pl.boards[self.board]:
                continue
            self.place_with_satellites(ref, band, only)

    def host(self, ref):
        return self.host_of.get(ref) or self.near.get(ref)

    def place_with_satellites(self, ref, band, only=None):
        """Place `ref`, then at once everything that must sit against it."""
        self.place_one(ref, band)
        # a satellite follows its host whatever pass the host is placed in
        sats = [r for r in self.doc.components if self.host(r) == ref
                and r not in self.pl.boards[self.board]]
        for sat in sorted(sats, key=_ref_key):
            self.place_one(sat, self.band.get(sat, band))

    def place_one(self, ref, band):
        cu, partners = self.centroid_u(ref)
        if ref in self.target_u:
            target, why = self.target_u[ref]
        elif cu is not None:
            target = cu
            why = "centroid of " + ", ".join(partners[:6]) + (", …" if len(partners) > 6 else "")
        elif self.terminal_u(ref) is not None:
            target, term = self.terminal_u(ref)
            why = f"behind {term} (reached through one passive)"
        else:
            target, why = self.frame.length / 2, "board centre (nothing it touches is placed)"
        layer = self.layer_of(ref)
        row_depth = max((p.box.v1 for p in self.pl.face(self.board, layer) if p.band == 1),
                        default=0.0)
        if ref in self.target_v:
            v_front, why_v = self.target_v[ref]
            why = f"{why_v}; u: {why}"
        else:
            v_front = BAND_FRONT.get(band, row_depth + CHANNEL)
        back_flush = ref in self.target_v
        if self.is_hv(ref) and band != 2 and ref not in self.target_u and ref not in self.target_v:
            # the 84 V bulk -- chokes, bricks, cans, the fuse -- packs against
            # the end J101 stands at, straight behind the row, so the HV group
            # is one compact blob and the low-voltage parts have the rest
            hv_row = [p for p in self.pl.face(self.board, 1) if p.band == 1 and self.ix.is_hv(p.refdes)]
            end = 0.0 if not hv_row or hv_row[0].box.cu < self.frame.length / 2 else self.frame.length
            target, why = end, f"HV bulk, packed toward the {'left' if end == 0 else 'right'} end"
            v_front = row_depth + CHANNEL
        near = None
        if ref in self.target_pt:
            target, v_front, why = self.target_pt[ref]
            back_flush = True
        if ref in self.host_of and self.host_of[ref] in self.pl.boards[self.board]:
            host = self.pl.boards[self.board][self.host_of[ref]]
            near, target, v_front = host.box, host.box.cu, host.box.v0
            why = f"decouples {host.refdes} on {self.decouple[ref]}"
        elif ref in self.near and self.near[ref] in self.pl.boards[self.board]:
            host = self.pl.boards[self.board][self.near[ref]]
            near, target, v_front = host.box, host.box.cu, host.box.v0
            why = f"beside {host.refdes}: {self.near_why.get(ref, '')}"
        env = self.env(ref)
        angles = (0, 90, 180, 270)
        if self.item(ref).kind == "MODULE":
            angles = (0,)                 # local +Y (the antenna end) toward the back edge
        if self.item(ref).kind == "IC" and any(n in self.ix.classes["PWR12"] for n in self.item(ref).nets):
            # the V12 bus: every IC on it faces the way the first one did
            first = next((p for p in self.pl.boards[self.board].values()
                          if self.item(p.refdes).kind == "IC"
                          and any(n in self.ix.classes["PWR12"] for n in self.item(p.refdes).nets)), None)
            if first is not None:
                angles = (first.angle,)
                v_front, back_flush = first.box.v0, True
                why += f"; in line with {first.refdes}"
        best = None
        for ang in angles:
            got = self._slot(ref, band, ang, target, v_front, back_flush=back_flush, near=near)
            if got is None:
                continue
            u, v, cost = got
            cost += 0.5 if ang else 0.0
            cost += self.misalignment(ref, u, v, ang)
            if best is None or cost < best[0]:
                best = (cost, u, v, ang)
        if best is None:
            self.pl.notes.append(f"{self.board}: {ref} fits nowhere on its face; left as saved")
            comp = self.doc.components[ref]
            u, v = self.frame.to_board(comp.x / MIL_PER_MM, comp.y / MIL_PER_MM)
            self.pl.add(self.make(ref, u, v, self.frame.board_angle(comp.angle), band,
                                  "UNPLACED: no free slot"))
            return
        _, u, v, ang = best
        self.pl.add(self.make(ref, u, v, ang, band, why))

    def terminal_u(self, ref):
        """(u, refdes) of the placed harness terminal `ref` reaches through one
        passive on a signal net -- the class-A cap behind its series R -- or
        None.  The pin's u, not the header's centre."""
        placed = self.pl.boards[self.board]
        for net in self.item(ref).nets:
            if not self.ix.signal(net):
                continue
            for r, _ in self.ix.members[net]:
                it = self.ix.items.get(r)
                if r == ref or it is None or it.kind not in PASSIVE_KINDS:
                    continue
                for m in it.nets:
                    if not self.ix.signal(m):
                        continue
                    for rr, pin in self.ix.members[m]:
                        p = placed.get(rr)
                        if p is not None and self.ix.items[rr].harness and not p.unplaced:
                            return p.pin_point(self.frame, pin)[0], rr
        return None

    def misalignment(self, ref, u, v, angle):
        """Weighted mean distance (u) from this part's pins to the placed pins
        they connect to: what tells 0 from 180 on a symmetric body."""
        probe = self.make(ref, u, v, angle, 0, "")
        num = den = 0.0
        for net, _ in self.item(ref).nets.items():
            w = self.ix.weight(self.board, net)
            if w <= 0:
                continue
            mine = [pin for pin, n in self.item(ref).pin_net.items() if n == net]
            for r, pin in self.ix.members[net]:
                p = self.pl.boards[self.board].get(r)
                if r == ref or p is None or p.unplaced:
                    continue
                pu = p.pin_point(self.frame, pin)[0]
                for m in mine:
                    num += w * abs(probe.pin_point(self.frame, m)[0] - pu)
                    den += w
        return num / den if den else 0.0

    def attached(self, ref, angle):
        """Boxes that travel with `ref` and must land on nothing, on any face:
        the S3's antenna zone, a programming land's cable ends.  Offsets from
        the body's (u0, v0) corner."""
        env = self.env(ref)
        off = placed_box(env, self.frame, 0.0, 0.0, angle, self.layer_of(ref) == 2)
        it = self.item(ref)
        if it.kind == "MODULE":
            z = Box(off.u0, off.v1, off.u1, off.v1 + ANTENNA_ZONE_D)
            return [(z.u0 - off.u0, z.v0 - off.v0, z.u1 - off.u0, z.v1 - off.v0)]
        if it.land:
            return [(z.u0 - off.u0, z.v0 - off.v0, z.u1 - off.u0, z.v1 - off.v0)
                    for z in service_zones(off)]
        return []

    # -- fixed items --------------------------------------------------------------
    def place_fixed(self, ref, u, v, angle, band, reason):
        self.pl.add(self.make(ref, u, v, angle, band, reason))

    def keep_saved(self):
        for ref in sorted(self.keep):
            comp = self.doc.components.get(ref)
            if comp is None:
                continue
            u, v = self.frame.to_board(comp.x / MIL_PER_MM, comp.y / MIL_PER_MM)
            self.pl.add(self.make(ref, u, v, self.frame.board_angle(comp.angle),
                                  self.band.get(ref, 0), "kept where the owner put it", kept=True))


def _mate_angle(pl, lower, upper):
    """The board angle at which `upper` (under its board) lands pin for pin on
    `lower` by NET, or None if no quarter turn does."""
    ix = pl.ix
    lo = pl.get(lower)
    board = ix.items[upper].board
    frame = pl.frame(board)
    env = pl.project.envelope(pl.project.pcbs[board].components[upper], ix.items[upper].body)
    pads_lo = lo.pads(pl.frame(lo.board))
    net_lo, net_up = ix.items[lower].pin_net, ix.items[upper].pin_net
    for ang in (lo.angle, (lo.angle + 180) % 360, (lo.angle + 90) % 360, (lo.angle + 270) % 360):
        pads_up = placed_pads(env, frame, lo.u, lo.v, ang, True)
        if _mismatched(pads_lo, net_lo, pads_up, net_up) == 0:
            return ang
    return None


def _mismatched(pads_a, net_a, pads_b, net_b):
    """How many of `pads_a` have no pad of `pads_b` at the same place carrying
    the same net."""
    wrong = 0
    for num, u, v in pads_a:
        hit = next((n for n, uu, vv in pads_b
                    if abs(uu - u) <= MATE_TOL and abs(vv - v) <= MATE_TOL), None)
        if hit is None or net_b.get(hit, "") != net_a.get(num, ""):
            wrong += 1
    return wrong


def stack(project, ix, anchor="centre", keep=()):
    """Place OUTPUTS, then LOGIC, then POWER.  Returns the `Placement`."""
    pl = Placement(project, ix)
    keep = set(keep)
    for board in ("OUTPUTS", "LOGIC", "POWER"):
        if board not in project.pcbs:
            pl.notes.append(f"{board}: no PCB document in the file")
            continue
        _place_board(pl, board, anchor, keep)
    return pl


def _place_board(pl, board, anchor, keep, relaxed=False):
    ix = pl.ix
    W = pl.frame(board).width
    if True:
        pr = Placer(pl, board, anchor, keep, relaxed=relaxed)
        pr.keep_saved()
        pr.row("top")
        pr.row("bottom")
        if board == "OUTPUTS":
            # the pairs' lower halves flush to the back edge: a long through-
            # hole row cuts a plane least at its edge (check 12)
            for ref in ("J307", "J308"):
                if ref in pr.doc.components and ref not in keep:
                    box = placed_box(pr.env(ref), pr.frame, 0, 0, 0, False)
                    pr.target_v[ref] = (W - box.d - COURTYARD, "flush to the back edge")
        if board == "LOGIC":
            for lower, upper in (("J307", "J407"), ("J308", "J406")):
                lo = pl.get(lower)
                if lo is None or upper not in pr.doc.components or upper in keep:
                    continue
                ang = _mate_angle(pl, lower, upper)
                if ang is None:
                    ang = lo.angle
                    pl.notes.append(f"LOGIC: {upper} lands pin for pin on {lower} at no quarter "
                                    f"turn; placed at {lower}'s angle")
                pr.place_fixed(upper, lo.u, lo.v, ang, 4, f"fixed: mate of {lower}")
            if "U401" in pr.doc.components and "U401" not in keep:
                box = placed_box(pr.env("U401"), pr.frame, 0, 0, 0, False)
                pr.target_v["U401"] = (W - ANTENNA_EDGE / 2 - box.d,
                                       "antenna end (local +Y, the padless end) at the back edge")
            s3 = next((it for it in ix.on(board) if it.kind == "MODULE"), None)
            if s3 is not None:
                # an ADC input's RC filter sits against the S3 (check 14)
                for n in ix.classes["SENSE"]:
                    if not any(r == s3.refdes for r, _ in ix.members[n]):
                        continue
                    for r, _ in ix.members[n]:
                        it = ix.items.get(r)
                        if it and it.board == board and it.kind in ("R", "C") and r in pr.doc.components:
                            pr.near[r], pr.near_why[r] = s3.refdes, f"RC filter on {n}, an ADC1 input"
                # the CAN transceiver over the STACK contacts that carry its bus
                for it in ix.on(board):
                    if it.kind != "IC" or not any(n.startswith("CAN") for n in it.nets):
                        continue
                    for conn in ix.on(board):
                        if conn.kind != "CONN" or not conn.interface or pl.get(conn.refdes) is None:
                            continue
                        shared = [pin for pin, net in conn.pin_net.items()
                                  if net in it.nets and net.startswith("CAN")]
                        pts = [(u, v) for num, u, v in pl.get(conn.refdes).pads(pr.frame) if num in shared]
                        if pts and it.refdes in pr.doc.components:
                            cu = sum(u for u, _ in pts) / len(pts)
                            cv = sum(v for _, v in pts) / len(pts)
                            depth = placed_box(pr.env(it.refdes), pr.frame, 0, 0, 0, False).d
                            pr.target_pt[it.refdes] = (cu, cv - depth / 2,
                                                       f"over {conn.refdes}'s CANH/CANL contacts")
        if board == "POWER":
            for lower, upper in (("J202", "J311"), ("J105", "J312")):
                up = pl.get(upper)
                if up is not None and lower in pr.doc.components:
                    pr.target_u[lower] = (up.box.cu, f"under {upper}'s loom (u {up.box.cu:.1f})")
            gap = ix.gaps[("POWER", "OUTPUTS")].gap_mm
            for hang in ("J311", "J312"):
                up = pl.get(hang)
                if up is None:
                    continue
                limit = gap - ix.items[hang].height - bp.CLEARANCE
                for it in ix.on("POWER", "top"):
                    if it.height > limit:
                        pr.extra.setdefault(it.refdes, []).append(up.box.grow(COURTYARD))
        if board == "POWER":
            # the 84 V parts go down first, as one group behind J101, so the
            # low-voltage parts then keep the strip from copper that exists
            hv_refs = {r for r in pr.doc.components if pr.is_hv(r)}
            for band in (3, 4, 2):           # the bulk first, its passives into the gaps
                pr.place_band(band, only=hv_refs)
        # what has a fixed target goes before the bands, so the bands gather round it
        for ref in sorted(set(pr.target_u) | set(pr.target_v) | set(pr.target_pt), key=_ref_key):
            if ref in pr.pending():
                pr.place_with_satellites(ref, pr.band.get(ref, 4))
        s3 = next((p for p in pl.boards[board].values() if ix.items[p.refdes].kind == "MODULE"), None)
        term = pl.boards[board].get(brake_terminal(ix, board, s3.refdes)) if s3 else None
        if s3 is not None and term is not None:
            # the brake nets' straight path stays clear of the I2C pull-ups (check 14)
            a, b = (term.box.cu, term.box.cv), (s3.box.cu, s3.box.cv)
            corridor = Box(min(a[0], b[0]) - CORRIDOR_CLEAR, min(a[1], b[1]) - CORRIDOR_CLEAR,
                           max(a[0], b[0]) + CORRIDOR_CLEAR, max(a[1], b[1]) + CORRIDOR_CLEAR)
            for r in i2c_pullups(ix, board):
                pr.extra.setdefault(r, []).append(corridor)
        for band in (2, 3, 4):
            pr.place_band(band)
        for ref in pr.pending():
            pr.place_one(ref, pr.band.get(ref, 4))
        if any(p.unplaced for p in pl.boards[board].values()) and not pr.relaxed:
            # a revision: the same board again with the HV strip at the check's
            # floor, so the parts the strip crowded out have room
            left = [p.refdes for p in pl.boards[board].values() if p.unplaced]
            pl.notes = [n for n in pl.notes if not n.startswith(f"{board}:")]
            pl.notes.append(f"{board}: {' '.join(sorted(left, key=_ref_key))} found no room at the "
                            f"{HV_STRIP:g} mm HV strip; re-placed with the strip at the check's "
                            f"{HV_CLEARANCE:g} mm floor")
            pl.boards[board] = {}
            return _place_board(pl, board, anchor, keep, relaxed=True)
    return pl


# --- the checks -------------------------------------------------------------------
def check(pl, ix=None):
    """Every problem with `pl`, as readable lines.  Empty means the placement
    may be written.  Each check is proven to fire in tests/test_place.py."""
    ix = ix or pl.ix
    out = []
    for board in bp.STACK_ORDER:
        if board not in pl.project.pcbs:
            continue
        frame = pl.frame(board)
        items = pl.boards[board]
        L, W = frame.length, frame.width
        # 1 -- inside the outline, clear of the M3 corners
        for p in items.values():
            if p.box.u0 < -TOL or p.box.v0 < -TOL or p.box.u1 > L + TOL or p.box.v1 > W + TOL:
                out.append(f"1 outline: {board} {p.refdes} body spans u {p.box.u0:.1f}..{p.box.u1:.1f}, "
                           f"v {p.box.v0:.1f}..{p.box.v1:.1f} on a {L:g} x {W:g} board")
            for c in frame.corners:
                if p.box.overlaps(c):
                    out.append(f"1 corner: {board} {p.refdes} sits on the M3 washer at "
                               f"({c.cu:.1f}, {c.cv:.1f})")
        # 2 -- clearance between same-face bodies; 10 -- channels between bands
        for layer in (1, 2):
            face = pl.face(board, layer)
            for i, a in enumerate(face):
                for b in face[i + 1:]:
                    gu, gv = a.box.gaps(b.box)
                    if a.band and b.band and a.band != b.band and a.box.u_overlaps(b.box):
                        need = CHANNEL_BAND4 if 4 in (a.band, b.band) else CHANNEL
                        if gv < need - TOL:
                            out.append(f"10 channel: {board} {a.refdes} (band {a.band}) and "
                                       f"{b.refdes} (band {b.band}) stand {max(gv, 0):.2f} mm apart "
                                       f"in v, one behind the other; the strip between bands is "
                                       f"{need:g} mm")
                            continue
                    # two harness headers in the row keep edge_budget's HEADER_GAP:
                    # no trace passes between flanges, the signals leave behind
                    need = board_fit.HEADER_GAP if a.band == b.band == 1 else CLEAR
                    if max(gu, gv) < need - TOL:
                        out.append(f"2 clearance: {board} {a.refdes} and {b.refdes} are "
                                   f"{max(gu, gv, 0):.2f} mm apart on the same face; "
                                   f"{need:g} mm " + ("between headers" if need == board_fit.HEADER_GAP
                                                      else "lets one trace pass"))
        # 3 -- layers per the netlist's side
        bottom = {it.refdes for it in ix.on(board) if it.side == "bottom"}
        for p in items.values():
            want = 2 if p.refdes in bottom else 1
            if p.layer != want:
                out.append(f"3 layer: {board} {p.refdes} is on layer {p.layer}; the netlist puts it "
                           f"{'under' if want == 2 else 'on top of'} the board (layer {want})")
        # 6 -- the face row: at the face, in order, inside the ends
        for side in ("top", "bottom"):
            edge = next((e for e in board_fit.edge_budget(ix.d)
                         if e.board == board and e.side == side), None)
            if edge is None:
                continue
            row = [items[r] for r in edge.headers if r in items]
            for p in row:
                if abs(p.box.v0) > 0.05:
                    out.append(f"6 row: {board} {p.refdes} body starts at v {p.box.v0:.2f}; the "
                               f"harness row stands at the face, v = 0")
                if p.box.u1 > L - M3_INSET_MM + TOL or p.box.u0 < M3_INSET_MM - TOL:
                    out.append(f"6 row: {board} {p.refdes} runs past the board end "
                               f"(u {p.box.u0:.1f}..{p.box.u1:.1f} of {L:g} less the M3 inset)")
            for a, b in zip(row, row[1:]):
                if b.box.u0 < a.box.u1 - TOL:
                    out.append(f"6 row: {board} edge_budget puts {a.refdes} then {b.refdes}, but "
                               f"{b.refdes} (u {b.box.u0:.1f}) is not after {a.refdes} (u {a.box.u1:.1f})")
        # 9 -- heights against the face's gap
        i = bp.STACK_ORDER.index(board)
        above = (board, bp.STACK_ORDER[i + 1] if i + 1 < len(bp.STACK_ORDER) else bp.LID_NAME)
        below = (bp.STACK_ORDER[i - 1] if i else bp.FLOOR_NAME, board)
        for p in items.values():
            key = above if p.layer == 1 else below
            gap = ix.gaps[key]
            if p.height > gap.gap_mm + TOL:
                out.append(f"9 height: {board} {p.refdes} is {p.height:.1f} mm tall on a face whose "
                           f"gap is {gap.gap_mm:.1f} mm ({key[0]} -> {key[1]})")
        # 12 -- a long through-hole connector across the board cuts the plane
        for p in items.values():
            it = ix.items.get(p.refdes)
            if it is None or it.kind != "CONN" or not p.env.pads:
                continue
            if max(it.body) > PLANE_CUT and p.box.d > p.box.w:
                out.append(f"12 plane: {board} {p.refdes} ({max(it.body):.1f} mm of through-hole row) "
                           f"lies across the board (v-extent {p.box.d:.1f} > u-extent {p.box.w:.1f}) "
                           f"and would split the ground plane")
        # 16 -- the programming land: on top, clear along its long axis
        for p in items.values():
            it = ix.items.get(p.refdes)
            if it is None or it.kind != "CONN" or not it.land:
                continue
            if p.layer != 1:
                out.append(f"16 service: {board} {p.refdes} is on layer {p.layer}; the programming "
                           f"land must be on top")
            zones = service_zones(p.box)
            for q in pl.face(board, 1):
                if q is not p and any(q.box.overlaps(z) for z in zones):
                    out.append(f"16 service: {board} {q.refdes} stands within {SERVICE_CLEAR:g} mm of "
                               f"{p.refdes}'s end, where the programming cable enters")
        # 15 -- decouplers on their IC
        for cap, rail in decouplers(ix, board).items():
            p = items.get(cap)
            hosts = [items[i.refdes] for i in ics_on(ix, board, rail) if i.refdes in items]
            if p is None or not hosts:
                continue
            near = min(p.box.separation(h.box) for h in hosts)
            if near > DECOUPLE_REACH + TOL:
                out.append(f"15 decoupling: {board} {cap} (100 nF on {rail}) is {near:.1f} mm from the "
                           f"nearest IC on that rail; {DECOUPLE_REACH:g} mm is a decoupler")
    out += _check_pairs(pl, ix)
    out += _check_keepouts(pl, ix)
    out += _check_hv(pl, ix)
    out += _check_antenna(pl, ix)
    out += _check_bus(pl, ix)
    out += _check_sensitive(pl, ix)
    return out


def _check_pairs(pl, ix):
    """4 -- the mated pairs coincide, in X, Y and pin for pin by net."""
    out = []
    for lower, upper in (("J307", "J407"), ("J308", "J406")):
        lo, up = pl.get(lower), pl.get(upper)
        if lo is None or up is None:
            continue
        if abs(lo.u - up.u) > MATE_TOL or abs(lo.v - up.v) > MATE_TOL:
            out.append(f"4 mate: {upper} at ({up.u:.2f}, {up.v:.2f}) is not over {lower} at "
                       f"({lo.u:.2f}, {lo.v:.2f}); the pair mates straight down")
            continue
        wrong = _mismatched(lo.pads(pl.frame(lo.board)), ix.items[lower].pin_net,
                            up.pads(pl.frame(up.board)), ix.items[upper].pin_net)
        if wrong:
            out.append(f"4 mate: {upper} over {lower}: {wrong} of {len(lo.env.pads)} contacts land on a "
                       f"different net (angle {up.angle} against {lo.angle})")
    return out


def _check_keepouts(pl, ix):
    """5 -- nothing tall on POWER's top under J311 / J312 as placed on OUTPUTS."""
    out = []
    gap = ix.gaps.get(("POWER", "OUTPUTS"))
    if gap is None or "POWER" not in pl.boards:
        return out
    for hang in ("J311", "J312"):
        up = pl.get(hang)
        if up is None:
            continue
        limit = gap.gap_mm - ix.items[hang].height - bp.CLEARANCE
        for p in pl.face("POWER", 1):
            if p.box.overlaps(up.box) and p.height > limit + TOL:
                out.append(f"5 keep-out: POWER {p.refdes} ({p.height:.1f} mm) stands under {hang}, "
                           f"which hangs {ix.items[hang].height:.1f} mm into the {gap.gap_mm:.1f} mm "
                           f"gap; the limit there is {limit:.1f} mm")
    return out


def _check_hv(pl, ix):
    """7 -- HV copper off the edge and clear of LV courtyards; 13 -- the HV
    parts are one group and no LV part is sandwiched between HV copper."""
    out = []
    board = "POWER"
    if not pl.boards.get(board):
        return out
    frame = pl.frame(board)
    hv = [p for p in pl.boards[board].values() if ix.is_hv(p.refdes)]
    lv = [p for p in pl.boards[board].values() if not ix.is_hv(p.refdes)]
    L, W = frame.length, frame.width
    zones = [(p, z) for p in hv for z in p.hv_zones(ix, frame)]
    for p, z in zones:
        edge = min(z.u0, z.v0, L - z.u1, W - z.v1)
        if edge < HV_EDGE - TOL:
            out.append(f"7 HV edge: POWER {p.refdes}'s 84 V copper is {max(edge, 0):.2f} mm from the "
                       f"board edge; {HV_EDGE:g} mm keeps pack voltage off the rim")
    for q in lv:
        worst = None
        for p, z in zones:
            sep = z.grow(COURTYARD).separation(q.box.grow(COURTYARD))
            if sep < HV_CLEARANCE - TOL and (worst is None or sep < worst[0]):
                worst = (sep, p.refdes)
        if worst:
            out.append(f"7 HV clearance: POWER {q.refdes}'s courtyard is {worst[0]:.2f} mm from "
                       f"{worst[1]}'s 84 V copper; the HV class needs {HV_CLEARANCE:g} mm")
    # 13a -- one group at HV_STRIP adjacency
    if len(hv) > 1:
        parent = {p.refdes: p.refdes for p in hv}

        def root(r):
            while parent[r] != r:
                parent[r] = parent[parent[r]]
                r = parent[r]
            return r
        for i, a in enumerate(hv):
            for b in hv[i + 1:]:
                if a.box.separation(b.box) <= HV_STRIP + TOL:
                    parent[root(a.refdes)] = root(b.refdes)
        groups = {}
        for p in hv:
            groups.setdefault(root(p.refdes), []).append(p.refdes)
        if len(groups) > 1:
            out.append(f"13 HV region: POWER's 84 V parts form {len(groups)} groups, not one: "
                       + " | ".join(" ".join(sorted(g, key=_ref_key)) for g in groups.values())
                       + f" (grouped at {HV_STRIP:g} mm)")
    # 13b -- no LV part between HV copper
    zone_boxes = [z for _, z in zones]
    for q in lv:
        sides = {
            "left": any(z.v_overlaps(q.box) and z.u1 <= q.box.u0 for z in zone_boxes),
            "right": any(z.v_overlaps(q.box) and z.u0 >= q.box.u1 for z in zone_boxes),
            "front": any(z.u_overlaps(q.box) and z.v1 <= q.box.v0 for z in zone_boxes),
            "back": any(z.u_overlaps(q.box) and z.v0 >= q.box.v1 for z in zone_boxes)}
        # inside the region = 84 V copper on all four sides: its traces cannot
        # leave without crossing pack voltage.  Copper on three sides is a bay,
        # open toward the board edge or the LV side, and its traces leave there.
        if all(sides.values()):
            out.append(f"13 HV region: POWER {q.refdes} (low voltage) is inside the 84 V region "
                       f"(copper {', '.join(k for k, v in sides.items() if v)}); its traces would "
                       f"have to cross it")
    return out


def _check_antenna(pl, ix):
    """8 -- the S3's antenna end at the back edge, the zone beyond it empty."""
    out = []
    p = pl.get("U401")
    if p is None:
        return out
    frame = pl.frame(p.board)
    W, L = frame.width, frame.length
    ex, ey = _rot(0.0, 1.0, frame.file_angle(p.angle))      # local +Y: the padless end
    if p.bottom:
        ex = -ex
    du, dv = frame.dir_to_board(ex, ey)
    if abs(dv) > abs(du):
        gap = (W - p.box.v1) if dv > 0 else p.box.v0
        zone = (Box(p.box.u0, p.box.v1, p.box.u1, p.box.v1 + ANTENNA_ZONE_D) if dv > 0 else
                Box(p.box.u0, p.box.v0 - ANTENNA_ZONE_D, p.box.u1, p.box.v0))
        where = "back" if dv > 0 else "connector-face"
    else:
        gap = (L - p.box.u1) if du > 0 else p.box.u0
        zone = (Box(p.box.u1, p.box.v0, p.box.u1 + ANTENNA_ZONE_D, p.box.v1) if du > 0 else
                Box(p.box.u0 - ANTENNA_ZONE_D, p.box.v0, p.box.u0, p.box.v1))
        where = "board-end"
    if where != "back" or gap > ANTENNA_EDGE + TOL:
        out.append(f"8 antenna: {p.board} U401's antenna end faces the {where} edge, "
                   f"{gap:.1f} mm from it; it must be within {ANTENNA_EDGE:g} mm of the back edge")
    for q in pl.boards[p.board].values():
        if q is not p and q.box.overlaps(zone):
            out.append(f"8 antenna: {p.board} {q.refdes} stands in the {ANTENNA_ZONE_W:g} x "
                       f"{ANTENNA_ZONE_D:g} mm zone beyond U401's antenna end")
    return out


def _check_bus(pl, ix):
    """11 -- the V12 bus on OUTPUTS: its ICs one way, J311 under their middle."""
    out = []
    board = "OUTPUTS"
    if not pl.boards.get(board):
        return out
    items = pl.boards[board]
    pwr12 = ix.classes["PWR12"]
    ics = [items[it.refdes] for it in ix.on(board, "top")
           if it.kind == "IC" and any(n in pwr12 for n in it.nets) and it.refdes in items]
    feed = next((items[it.refdes] for it in ix.on(board)
                 if it.kind == "CONN" and it.interface and any(n in pwr12 for n in it.nets)
                 and it.refdes in items), None)
    if not ics or feed is None:
        return out
    cu = sum(p.box.cu for p in ics) / len(ics)
    if abs(cu - feed.box.cu) > BUS_REACH + TOL:
        out.append(f"11 V12 bus: OUTPUTS {' '.join(sorted(p.refdes for p in ics))} centre on u "
                   f"{cu:.1f} but {feed.refdes} feeds them from u {feed.box.cu:.1f}: "
                   f"{abs(cu - feed.box.cu):.1f} mm apart, over {BUS_REACH:g}")
    if len({p.angle for p in ics}) > 1:
        out.append(f"11 V12 bus: OUTPUTS the V12 ICs face {len({p.angle for p in ics})} ways "
                   f"({', '.join(f'{p.refdes}@{p.angle}' for p in ics)}); one bus wants one way")
    return out


def _check_sensitive(pl, ix):
    """14 -- CAN transceiver by its STACK contacts; the brake nets' corridor
    clear of the I2C pull-ups; an ADC input's RC beside the S3."""
    out = []
    board = "LOGIC"
    if not pl.boards.get(board):
        return out
    items = pl.boards[board]
    frame = pl.frame(board)
    s3 = next((items[it.refdes] for it in ix.on(board) if it.kind == "MODULE" and it.refdes in items),
              None)
    if s3 is None:
        return out
    for it in ix.on(board):
        if it.kind != "IC" or not any(n.startswith("CAN") for n in it.nets) or it.refdes not in items:
            continue
        can = items[it.refdes]
        for conn in ix.on(board):
            if conn.kind != "CONN" or not conn.interface or conn.refdes not in items:
                continue
            shared = [pin for pin, net in conn.pin_net.items()
                      if net in it.nets and net.startswith("CAN")]
            pts = [(u, v) for num, u, v in items[conn.refdes].pads(frame) if num in shared]
            if not pts:
                continue
            cu, cv = sum(u for u, _ in pts) / len(pts), sum(v for _, v in pts) / len(pts)
            dist = math.hypot(can.box.cu - cu, can.box.cv - cv)
            if dist > CAN_REACH + TOL:
                out.append(f"14 CAN: LOGIC {it.refdes} is {dist:.1f} mm from {conn.refdes}'s CANH/CANL "
                           f"contacts ({', '.join(shared)}); the pair stays within {CAN_REACH:g} mm")
    terminal = items.get(brake_terminal(ix, board, s3.refdes))
    pullups = [items[r] for r in i2c_pullups(ix, board) if r in items]
    if terminal is not None:
        a, b = (terminal.box.cu, terminal.box.cv), (s3.box.cu, s3.box.cv)
        for r in pullups:
            dist = _point_segment(r.box.cu, r.box.cv, a, b)
            if dist < CORRIDOR_CLEAR - TOL:
                out.append(f"14 brake: LOGIC {r.refdes} (I2C pull-up) is {dist:.1f} mm from the straight "
                           f"path {terminal.refdes} -> U401 the brake nets take; {CORRIDOR_CLEAR:g} mm "
                           f"keeps the bus off them")
    for n in sorted(ix.classes["SENSE"]):
        if not any(r == s3.refdes for r, _ in ix.members[n]):
            continue
        for r, _ in ix.members[n]:
            it = ix.items.get(r)
            if it is None or it.board != board or it.kind not in ("R", "C") or r not in items:
                continue
            sep = items[r].box.separation(s3.box)
            if sep > ADC_REACH + TOL:
                out.append(f"14 ADC: LOGIC {r} (on {n}, an ADC1 input) is {sep:.1f} mm from U401; "
                           f"the filter sits within {ADC_REACH:g} mm of the pin")
    return out


def brake_terminal(ix, board, s3):
    """The harness terminal the brake nets enter on: walk one passive back
    from the S3's BRAKE pins along SIGNAL nets (ground reaches every header)."""
    for n, members in ix.members.items():
        if "BRAKE" not in n.upper() or not any(r == s3 for r, _ in members):
            continue
        for r, _ in members:
            it = ix.items.get(r)
            if it and it.kind in PASSIVE_KINDS:
                for m in it.nets:
                    if not ix.signal(m):
                        continue
                    for rr, _ in ix.members[m]:
                        c = ix.items.get(rr)
                        if c and c.kind == "CONN" and c.harness and c.board == board:
                            return rr
    return None


def i2c_pullups(ix, board):
    """The resistors on the I2C bus of `board`: those on a net the S3 talks
    SDA/SCL on, by the module's own pin names."""
    s3 = next((it for it in ix.on(board) if it.kind == "MODULE"), None)
    if s3 is None:
        return []
    bus = {ix.items[s3.refdes].pin_net.get(pin) for pin in ("IO13", "IO14")} - {None}
    bus |= {n for n in s3.nets if n in ("SDA", "SCL")}
    return sorted((it.refdes for it in ix.on(board) if it.kind == "R" and any(n in bus for n in it.nets)),
                  key=_ref_key)


def service_zones(box):
    """The two cable-end zones of a programming land, along its long axis."""
    if box.w >= box.d:
        return (Box(box.u0 - SERVICE_CLEAR, box.v0, box.u0, box.v1),
                Box(box.u1, box.v0, box.u1 + SERVICE_CLEAR, box.v1))
    return (Box(box.u0, box.v0 - SERVICE_CLEAR, box.u1, box.v0),
            Box(box.u0, box.v1, box.u1, box.v1 + SERVICE_CLEAR))


def _point_segment(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# --- writing ----------------------------------------------------------------------
def editor_running():
    """True while EasyEDA Pro is open: an edit under an open editor is lost or
    corrupts the file."""
    try:
        ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, check=False).stdout
    except OSError:
        return False
    return any("/opt/apps/easyeda" in line for line in ps.splitlines())


def _mil(mm):
    v = round(mm * MIL_PER_MM, 4)
    return int(v) if v == int(v) else v


def apply(project, pl):
    """Edit the COMPONENT records (and their labels, which follow the part) to
    `pl`.  Returns {board: {refdes: (x mil, y mil, angle, layer)}}."""
    written = {}
    for board, items in pl.boards.items():
        doc = project.pcbs.get(board)
        if doc is None:
            continue
        for ref, p in items.items():
            comp = doc.components.get(ref)
            if comp is None:
                continue
            x, y = doc.frame.to_file(p.u, p.v)
            angle = doc.frame.file_angle(p.angle)
            xm, ym = _mil(x), _mil(y)
            h, payload = project.records[comp.record]
            o = json.loads(payload)
            dth = (angle - int(round(o.get("angle") or 0))) % 360
            o["x"], o["y"], o["angle"], o["layerId"] = xm, ym, angle, p.layer
            project.records[comp.record] = (h, eprj2._compact(o))
            for li in comp.labels:
                lh, lp = project.records[li]
                a = json.loads(lp)
                if a.get("x") is None:
                    continue
                rx, ry = _rot(a["x"] - comp.x, a["y"] - comp.y, dth)
                a["x"], a["y"] = round(xm + rx, 4), round(ym + ry, 4)
                project.records[li] = (lh, eprj2._compact(a))
            written.setdefault(board, {})[ref] = (xm, ym, angle, p.layer)
    return written


def write(project, pl, src, out):
    """Write `project` (already `apply`d) to `out` through the build's round
    trip, keeping the previous `out` as `.prev`.  Refuses while the editor is
    open, and refuses to leave a file whose re-read differs from what was
    meant.  Returns the written path."""
    if editor_running():
        raise RuntimeError("EasyEDA Pro is running -- close it before writing the project")
    out, src = Path(out), Path(src)
    text = eprj2.join(project.records)
    eprj2.split_records(text)
    tmp = out.with_name(out.name + ".placing")
    if tmp.exists():
        tmp.unlink()
    snap = project.snap
    eprj2.write(src, tmp, text, snap["structure"], snap["name"], owner=snap["owner"])
    if out.exists():
        prev = out.with_name(out.name + PREV_SUFFIX)
        if prev.exists():
            prev.unlink()
        os.replace(out, prev)
    os.replace(tmp, out)
    back = load(out)
    for board, items in pl.boards.items():
        doc = back.pcbs.get(board)
        frame = project.pcbs[board].frame
        for ref, p in items.items():
            c = doc.components.get(ref) if doc else None
            x, y = frame.to_file(p.u, p.v)
            want = (_mil(x), _mil(y), frame.file_angle(p.angle), p.layer)
            got = (c.x, c.y, c.angle, c.layer) if c else None
            if got is None or abs(got[0] - want[0]) > TOL or abs(got[1] - want[1]) > TOL \
                    or got[2:] != want[2:]:
                raise RuntimeError(f"{out}: {board} {ref} re-reads as {got}, not {want}")
    return out


# --- reports ----------------------------------------------------------------------
def _ref_key(ref):
    m = re.match(r"^([A-Z]+)(\d+)(.*)$", ref)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (ref, 0, "")


def placement_table(pl, board):
    frame = pl.frame(board)
    lines = [f"# {board} — placement", "",
             f"Generated by `tools/place.py`; regenerated on every `--stack`. Board frame: u along the "
             f"{frame.length:g} mm length, v across the {frame.width:g} mm width, v = 0 the connector "
             f"face, the origin of each footprint. File frame: the editor's X, Y in mm"
             + (" (the outline is drawn portrait: X across, Y along)." if frame.portrait else "."),
             "", "| Refdes | u | v | angle | file X | file Y | layer | band | reason |",
             "|---|---|---|---|---|---|---|---|---|"]
    for ref in sorted(pl.boards[board], key=_ref_key):
        p = pl.boards[board][ref]
        x, y = frame.to_file(p.u, p.v)
        lines.append(f"| {ref} | {p.u:.2f} | {p.v:.2f} | {p.angle} | {x:.2f} | {y:.2f} | {p.layer} | "
                     f"{p.band} | {p.reason} |")
    return "\n".join(lines) + "\n"


def summary(pl):
    lines = []
    for board in ("OUTPUTS", "LOGIC", "POWER"):
        items = pl.boards.get(board, {})
        if not items:
            continue
        pops = {}
        for p in items.values():
            pops[p.band] = pops.get(p.band, 0) + 1
        unplaced = [p.refdes for p in items.values() if p.reason.startswith("UNPLACED")]
        lines.append(f"{board}: {len(items)} placed; bands "
                     + ", ".join(f"{b}: {n}" for b, n in sorted(pops.items()))
                     + (f"; UNPLACED {' '.join(unplaced)}" if unplaced else ""))
    for n in pl.notes:
        lines.append(f"  note: {n}")
    return "\n".join(lines)


# --- command line -----------------------------------------------------------------
def default_file():
    return Path(build_project.EDITOR_PROJECTS) / PROJECT_FILE


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stack", action="store_true", help="place every board, check, write")
    mode.add_argument("--check", action="store_true", help="report on the saved file; never writes")
    ap.add_argument("--anchor", choices=("left", "right", "centre"), default="centre",
                    help="which end of the board the face row sits toward (default centre)")
    ap.add_argument("--keep", nargs="*", default=[], metavar="REF",
                    help="parts that keep the X, Y, layer they have in the saved file")
    ap.add_argument("--file", default=None,
                    help=f"the .eprj2 to read (default: the editor's {PROJECT_FILE})")
    ap.add_argument("--out", default=None, help="where to write (default: --file, keeping .prev)")
    ap.add_argument("--docs", default=str(Path(__file__).resolve().parent.parent / "layout"),
                    help="where the per-board placement tables go (default: layout/)")
    a = ap.parse_args(argv)
    src = Path(a.file) if a.file else default_file()
    if not src.is_file():
        print(f"REFUSED: {src} is not a file", file=sys.stderr)
        return EXIT_REFUSED
    try:
        d = netlist.checked()
    except netlist.NotACircuit as e:
        print(f"REFUSED -- {e}", file=sys.stderr)
        return EXIT_REFUSED
    ix = Index(d)
    project = load(src)
    for board in bp.STACK_ORDER:
        doc = project.pcbs.get(board)
        if doc is None:
            print(f"REFUSED: {src} has no PCB titled {board}", file=sys.stderr)
            return EXIT_REFUSED
        unknown = sorted(r for r in doc.components if r not in ix.items or ix.items[r].board != board)
        if unknown:
            print(f"REFUSED: {board}'s PCB carries {' '.join(unknown)}, which the netlist does not put "
                  f"there -- re-import the schematic before placing", file=sys.stderr)
            return EXIT_REFUSED
    if a.check:
        pl = Placement.from_file(project, ix)
        problems = check(pl, ix)
        print(summary(pl))
        print(f"{len(problems)} problem(s)" + ("" if problems else " -- the placement passes every check"))
        for p in problems:
            print(f"  - {p}")
        return EXIT_PROBLEMS if problems else 0
    out = Path(a.out) if a.out else src
    if editor_running():
        print("REFUSED: EasyEDA Pro is running; close it first", file=sys.stderr)
        return EXIT_REFUSED
    pl = stack(project, ix, anchor=a.anchor, keep=a.keep)
    print(summary(pl))
    problems = check(pl, ix)
    docs = Path(a.docs)
    docs.mkdir(parents=True, exist_ok=True)
    for board in bp.STACK_ORDER:
        (docs / f"{board}-placement.md").write_text(placement_table(pl, board), encoding="utf-8")
    print(f"{len(problems)} problem(s)" + ("" if problems else " -- the placement passes every check"))
    for p in problems:
        print(f"  - {p}")
    if problems:
        print(f"REFUSED: not written; the tables in {docs} show the proposal", file=sys.stderr)
        return EXIT_PROBLEMS
    apply(project, pl)
    try:
        path = write(project, pl, src, out)
    except RuntimeError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return EXIT_REFUSED
    prev = path.with_name(path.name + PREV_SUFFIX)
    print(f"written: {path}" + (f" (previous kept as {prev.name})" if prev.exists() else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
