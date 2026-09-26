"""The body module's layout FACTS: what `layout_export` states in
`layout.yaml` and `layout_hooks` derives for `pcbl`, and nothing else.

These are the build's own figures and derivations -- the reaches a part must
sit within, the HV edge and strip, the keep-outs, the heavy path, the net
classes and the rules that assign them, the decouplers and the hosts they
serve, the HV node voltages -- and the reader that takes a part's envelope
from the project's footprints.  They are project knowledge, so they stay in
the project.  Placing, routing and checking a layout are `pcb-layout-tools`'
(`pcbl`, tag v0.11.0): it reads these facts from the exported yaml and never
imports this module.

⛔ Nothing here places or routes.  A function that grows a placement or a
routing step belongs in `pcbl`, not here.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field, replace

from tools import board_params as bp, eprj2, layout_rules, netlist, rules, soft_start

# --- the project reader, and the placement facts the export states ----------------

MIL_PER_MM = 39.3701

#: Around each M3 hole centre: a 7 mm washer, so a square of this half-side
#: at every corner holds no part.  The hole centres are read from the file.
M3_KEEPOUT = 3.5

#: 84 V copper keeps this from the board edge: the edge is where the
#: enclosure, a standoff or a finger meets the board (IPC-2221B B2 at 160 V is
#: 1.25; the edge gets more because it is uncontrolled).
HV_EDGE = 3.0

#: The target gap between the HV group and every LV part -- wider than
#: the clearance floor so routing has the 1.25 mm class clearance to spend.
#: Also the adjacency under which the HV parts must form ONE group, and
#: (IO-26 4a) the width of the STRIP that divides POWER along its length:
#: 84 V end | HV_STRIP | low-voltage end.  The strip's u is not typed -- it
#: starts where the 84 V parts' own lengths end (`hv_partition`).
HV_STRIP = 3.0

#: The S3's antenna end within this of the back edge (the U.FL pigtail leaves
#: the board there), and nothing in a zone this wide x deep beyond it.
ANTENNA_EDGE = 2.0

ANTENNA_ZONE_W, ANTENNA_ZONE_D = 18.0, 8.0

#: (THE HEAVY PATH) The u-distance from the brick's `V12` output pad
#: to the contact that takes the 12 V bus OFF the board.  What it protects: an
#: **8.47 A** pour that must not thread between 84 V through-hole pins.  POWER
#: is partitioned along its length (4a), so a bus that leaves the brick at one
#: end of the 84 V region and a connector seated wherever the low-voltage end
#: had room put the whole 8.47 A across the chokes, the fuse clip and the bulk
#: cans -- 104.5 mm of it on the placement before this rule (2026-09-22).
#:
#: THE ARITHMETIC, from the library land patterns, in the order the bus is
#: soldered: the brick's `+V` pad stands **4.30** mm inside its output end;
#: the body ends at the partition, so the **3.00** mm `HV_STRIP` is next; then
#: the bulk cap, which stands across the board and takes **10.50** mm of the
#: run; `CLEAR` (**1.60**) between it and the connector; and `J202`'s `V12`
#: contact **4.25** mm inside its body, its pin row lying across the board.
#: 4.30 + 3.00 + 10.50 + 1.60 + 4.25 = **23.65 mm**, which is what a correct
#: placement gives, and 25.0 carries it with ~6 % to spare.  The defects it stands
#: between: the cap turned to lie ALONG the run instead of across it puts its
#: 19.1 mm side in the way and scores 32; the connector left where the
#: low-voltage end had room for it scores ~50; the placement before this rule
#: scored **104.5**.
HEAVY_PATH_MM = 25.0

#: The CAN transceiver within this of the STACK contacts that carry CANH/CANL.
CAN_REACH = 10.0

#: An ADC input's RC filter within this (edge to edge) of the S3.
ADC_REACH = 5.0

#: The I2C pull-ups keep this far from the straight path of the brake nets.
CORRIDOR_CLEAR = 5.0

#: A 100 nF decoupler within this (edge to edge) of the IC on its rail.
DECOUPLE_REACH = 3.0

#: Every other part on a converter's switch node -- its bootstrap capacitor,
#: its inductor -- within this (edge to edge) of the converter.  The switch
#: node is the loop that radiates and the net that carries the output current
#: at the switching edge; a body beside the converter keeps both short.  The
#: decoupler's figure: the same "against its body, one trace between".
SW_REACH = 3.0

#: Nothing within this of the Tag-Connect land along its long axis on either
#: end: the cable plug's body and its exit.  The entry end is not in the
#: drawing, so both ends are kept.
SERVICE_CLEAR = 5.0

# --- ROUTABILITY: how far a net has to run -----------------------------------------
#: A CHANNEL net -- a `TPS4H160B` `OUTx` or a `TPS2553` `OUT` and
#: everything on it, the clamp and the terminal contact it ends at -- may span
#: its terminal's OWN u-extent plus this.  The terminal's body is in the budget
#: because the driver stands BEHIND the row: its channels land on pins spread
#: over the whole header, so even a driver standing at the header's middle is a
#: body-length from the far one.  This is what is left for the placement.
#:
#: DERIVED from this design, the good case and the defects all real and all
#: measured on 2026-09-22, as an EXCESS over the terminal's own width:
#:   the clustered placement needs **36.2** (`HL_HIGH`, 62.1 mm to `J301`'s
#:     26.0 -- `U301` drives the headlight on `J301` at one end of the row AND
#:     `AUX12` on `J304`/`J305` at the other, so it stands at their weighted
#:     centroid and cannot be close to both);
#:   the placement before it ran nine channels long, by **84.1** (`AUX12V_3`),
#:     71.2, 61.5, 60.6, 59.9, 54.7, 46.8, 41.2 and **40.8** (`TAIL_STOP`).
#: So the figure has to live in (36.2, 40.8] and 40.0 is in it: 10.5 % of
#: headroom above what the board needs, and it still fails every one of the
#: nine, the narrowest by 0.8 mm.  ⚠️ That is a NARROW band, and the narrowness
#: IS the finding -- a driver that feeds terminals at both ends of the row
#: cannot be near all of them, and the next part that does it will have to be
#: split across two drivers rather than have this number raised.
CHANNEL_REACH = 40.0

#: A SIGNAL net that ends at a HARNESS TERMINAL -- an IC or the
#: module at one end, a terminal contact at the other -- may span that
#: terminal's own u-extent plus this.  Same budget shape as a channel and the
#: same reason, with a smaller reach because a signal is 0.2 mm of copper and
#: has no current to keep short: it is here so that the part that reads an
#: input stands behind the terminal the input arrives on.
#:
#: DERIVED (2026-09-22) as an excess over the terminal's width: the clustered
#: placement needs **12.0** (`SPARE_B6_WIRE`, 53.2 mm to `J410`'s 41.2), and
#: the placement before it ran seven long, by **62.1** (`SPARE_B4_WIRE`), 52.0,
#: 40.2, 23.1, 22.6, 20.0 and **19.5** (`SPARE_B1_WIRE`).  16.0 sits in the
#: (12.0, 19.5] that leaves, a third of headroom above what the board needs and
#: 3.5 mm inside the narrowest defect.
SIGNAL_REACH = 16.0

#: The programming land stands this far from the module at most,
#: measured pin to pin on the nets they share -- `EN`, `BOOT_IO0` and the two
#: UART0 lines are the S3's OWN pins (D25), so this is four traces from one
#: 18 mm module to one 3 mm land and nothing else needs to be near either.
#:
#: DERIVED (2026-09-22): with `J408` made the module's satellite the worst of
#: the four measures **21.4 mm** (on `EN`); before it, with the land placed by
#: its own adjacency at the far end of the board from the S3, it was
#: **38.4 mm**.  25.0 is the shipped measurement with ~17 % of headroom, and it
#: fails the old placement by 13.4 mm.  ⚠️ Pin to pin on the shared nets, NOT
#: the nets' own spans: `BOOT_IO0` also carries a pull-up and `EN` is every
#: expander's RESET since IO-22, so those spans say where the expanders are,
#: not where the programmer is.
PROG_REACH = 25.0

#: How hard a connector contact pulls its host, by the width of the copper the
#: net needs (the R0 class table in `layout/PROCESS.md`): a `CH12` channel is a
#: 1.0 mm trace at 1.55 A and a `CH5` 0.8 mm at 1.39 A, against 0.2 mm for a
#: signal.  A driver is therefore pulled to the terminals its CHANNELS feed and
#: only nudged by the nine control lines it shares with the `STACK` socket --
#: which is what "cluster by circuit" means in numbers rather than in a list of
#: refdes.  Anything not named here pulls 1.
CLASS_PULL = {"CH12": 5.0, "CH5": 4.0}

#: A 100 nF ceramic on a rail and GND is a decoupler for the IC on that rail.
DECOUPLER_VALUE = "100nF"

#: The S3's ADC1 pins, IO1-IO10: the only analog-capable GPIOs on this board
#: (ADC2 dies with WiFi -- CLAUDE.md), so a net landing here is a SENSE net.
ADC1_PINS = frozenset(f"IO{n}" for n in range(1, 11))

#: Layers a footprint's outline is drawn on: top silk and the component shape.
OUTLINE_LAYERS = (3, 48)

#: The pad names an exposed thermal pad carries (`padmap`'s `_LIB_ALIASES`:
#: the TPS4H160's and LM73605's and TLV767's PAD, the S3 module's EPAD).  Each
#: datasheet takes the die's heat into the ground planes through a via array
#: under that pad, so the export states `vias_in_pad` on these pads and on no
#: other: pcbl lays its stitch vias inside them and accepts a via in a pad
#: nowhere else.  Plain tented vias -- no fab option.
EXPOSED_PADS = frozenset({"PAD", "EPAD"})

#: A micrometre.  The file holds mils to four decimals (2.5 nm), so a
#: coordinate written and read back can move by a few nanometres; every
#: comparison in the checks allows this much, which no fab tolerance notices.
TOL = 1e-3

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

@dataclass(frozen=True)
class Envelope:
    """A footprint's plan in its own frame, mm: the box its pads, silk and
    stated body occupy, and each pad (number, centre x, y, half-width,
    half-height, THROUGH-HOLE).  The last flag is the PAD record's `hole`: that
    pad is copper on both faces of the board and a pin passes through it.  It
    is part of the tuple and not a parallel table on purpose -- every place
    that builds an Envelope has to say, for each pad, whether it crosses the
    board."""
    x0: float
    y0: float
    x1: float
    y1: float
    pads: tuple = ()

    @property
    def centred(self):
        return abs(self.x0 + self.x1) < 0.1 and abs(self.y0 + self.y1) < 0.1

    @property
    def tht(self):
        """True when ANY pad crosses the board: the part is through-hole, and
        its pins exist on the face it does not stand on."""
        return any(pad[5] for pad in self.pads)

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
    drawn geometry; with nothing drawn it is centred on the origin.

    A pad is THROUGH-HOLE when its record carries a `hole` WITH A SIZE --
    plated or not, something passes through the board there. ⚠️ A `hole`
    object of zero width is how a converted SMD land arrives (U404's SOIC-8 in
    the owner's file: eight pads, each `{"holeType":"ROUND","width":0,
    "height":0}`); it drills nothing and crosses nothing."""
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
            drilled = ((hole.get("width") or 0) > 0) or ((hole.get("height") or 0) > 0)
            pads.append((str(o.get("num", "")), cx / MIL_PER_MM, cy / MIL_PER_MM,
                         hw / MIL_PER_MM, hh / MIL_PER_MM, drilled))
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
    """A part or connector of one board, with what the layout facts need of it."""
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
        #: Every MATED pair in the stack, (lower half, upper half), DERIVED
        #: from the gap each one sets -- never a typed table, so a pair added
        #: to the netlist (CTRL-STACK at IO-27) is seated, checked and drawn
        #: without a second edit here.
        self.pairs = tuple((p.lower, p.upper) for g in bp.layer_gaps(d) for p in g.pairs
                           if p.lower in self.items and p.upper in self.items)

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

def current_outputs(d):
    """{(refdes, pin)} a power class's current LEAVES a part by, by the same
    pins `power_classes` names the classes by: the brick's `+V` (not `+S`,
    its sense lead), a TPS4H160B's `OUTx`, a TPS2553's `OUT`, an IC's `SW`,
    and the far pin of the inductor on a switch node.  `layout_export`
    walks the current from these (`_current_roles`)."""
    by = {p.refdes: p for p in d.parts}
    out, sw = set(), set()
    for n in d.nets:
        for ref, pin in n.pins:
            p = by.get(ref)
            if p is None:
                continue
            mpn = p.mpn.upper()
            if ((ref == bp.FLOOR_SEAT and pin == "+V")
                    or ("TPS4H160" in mpn and pin.startswith("OUT"))
                    or ("TPS2553" in mpn and pin == "OUT")
                    or (p.kind == "IC" and pin == "SW")):
                out.add((ref, pin))
            if p.kind == "IC" and pin == "SW":
                sw.add(n.name)
    for n in d.nets:
        if n.name in sw:
            for ref, pin in n.pins:
                if ref in by and by[ref].kind == "L":
                    out |= {(ref, q) for q in by[ref].pins if q != pin}
    return out

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

def decoupler_hosts(ix, board):
    """{cap refdes: the IC it sits beside}.  The ICs on a rail take its 100 nFs
    in turn, so every IC on the rail gets one before any gets two.  A cap is
    placed against this IC, and the decoupling reach then asks only that it be
    near the NEAREST IC on the rail -- so a host that leaves its own cap no room is
    the earlier failure."""
    out = {}
    dec = decouplers(ix, board)
    for rail in sorted(set(dec.values())):
        caps = sorted((c for c, r in dec.items() if r == rail), key=_ref_key)
        hosts = sorted((i.refdes for i in ics_on(ix, board, rail)), key=_ref_key)
        for i, cap in enumerate(caps):
            if hosts:
                out[cap] = hosts[i % len(hosts)]
    return out

def ics_on(ix, board, net):
    return [it for it in ix.on(board)
            if it.kind in ("IC", "MODULE", "CONVERTER") and net in it.nets]

def v12_bus(ix, board):
    """(the ICs the 12 V bus feeds on `board`, the contact that feeds them),
    both from the COPPER: PWR12 is the net `U201`'s `+V` is on
    (`power_classes`), never a name.

    ⚠️ Several interface connectors carry `V12` since IO-26 -- `PWR-LOGIC`
    takes it up to LOGIC and on to CTRL's buck -- so the FEED is the one whose
    other half stands on the board the 12 V comes FROM.  The rest carry it
    away, and pulling the bus toward one of those would measure the wrong
    thing."""
    pwr12 = ix.classes["PWR12"]
    ics = sorted((it.refdes for it in ix.on(board, "top")
                  if it.kind == "IC" and any(n in pwr12 for n in it.nets)), key=_ref_key)
    source = ix.items[bp.FLOOR_SEAT].board if bp.FLOOR_SEAT in ix.items else None
    feeds = [it for it in ix.on(board)
             if it.kind == "CONN" and it.interface and any(n in pwr12 for n in it.nets)]
    incoming = [it.refdes for it in feeds
                if any(o.interface == it.interface and o.board == source
                       for o in ix.items.values() if o.refdes != it.refdes)]
    chosen = sorted(incoming or [it.refdes for it in feeds], key=_ref_key)
    return ics, (chosen[0] if chosen else None)

#: The parts the CLUSTERING objective steers as HOSTS: an active part a
#: circuit is built around, which is what "a host stands at the u-centroid of
#: the connectors it serves" is about.  A passive is steered too, but by a
#: narrower rule -- the terminal it is directly on, Band 2's own rule -- and a
#: connector is what both are steered TOWARD.
HOST_KINDS = frozenset({"IC", "MODULE", "CONVERTER"})

def net_pull(ix, net):
    """How hard a contact on `net` pulls its host: `CLASS_PULL` by the routing
    class the copper puts it in, 1 for anything else."""
    for name, pull in CLASS_PULL.items():
        if net in ix.classes[name]:
            return pull
    return 1.0

def served_contacts(ix, board, ref):
    """[(net, connector, pin, pull)] -- the connector contacts `ref` SERVES on
    its own board.  The clustering objective's input, and all of it from the
    copper.  Two parts read it, and they read it differently:

    * a HOST -- an IC, the module, a converter -- serves the connectors on its
      own SIGNAL nets (a `TPS4H160B`'s `OUTx` lands on the terminal its channel
      feeds; the S3's lamp commands on the `STACK` socket's contacts), and
      where a signal net reaches no connector, the ones ONE hop away through a
      SERIES passive: a part with exactly two nets, one in and one out.  That
      is how an expander reaches the input terminals it reads, through each
      input's series resistor.  ⚠️ The hop is taken only when the net itself
      has no connector, so a channel that already ends at its terminal is never
      also credited to whatever else hangs off it, and never more than one
      hop: two hops reach the whole board and say nothing about which circuit
      a part belongs to.
    ⚠️ A PASSIVE is NOT steered this way -- `Placer.circuit_u` has the other
    half of the objective for it.  A passive is a link in a chain and belongs
    BETWEEN the two things it links; pinned to the connector on its net it
    drags the other end instead, which is what the `AUX5V_n_EN` series
    resistors did when they were (`R368` on `J501`'s contact, `U309` 82 mm
    away, 2026-09-22).
    """
    it = ix.items.get(ref)
    if it is None or it.kind not in HOST_KINDS:
        return []
    host = True

    def here(r):
        o = ix.items.get(r)
        return o is not None and o.kind == "CONN" and o.board == board

    out, seen = [], set()

    def take(net, r, pin):
        if (r, pin) not in seen:
            seen.add((r, pin))
            out.append((net, r, pin, net_pull(ix, net)))
    for net in sorted(it.nets):
        if not ix.signal(net):
            continue
        direct = sorted((r, pin) for r, pin in ix.members[net] if r != ref and here(r))
        if direct:
            for r, pin in direct:
                take(net, r, pin)
            continue
        if not host:
            continue
        for r, _ in sorted(ix.members[net]):
            o = ix.items.get(r)
            if r == ref or o is None or o.kind not in PASSIVE_KINDS or o.board != board:
                continue
            if len(o.nets) != 2:
                continue            # a series element: one net in, one out
            for m in sorted(o.nets):
                if m == net or not ix.signal(m):
                    continue
                for rr, pin in sorted(ix.members[m]):
                    if here(rr):
                        take(m, rr, pin)
    return out

def v12_output(ix, board):
    """The 12 V output on `board`, all of it from the COPPER: `(the converter
    that makes the bus, the connector that takes it off the board, its other
    low-voltage parts -- largest body first)`.  PWR12 is the net the seated
    brick's own `+V` pin is on (`power_classes`), never a net's name, and the
    connector is the one whose other half stands on another board: `V12`
    leaves POWER on the loom and nowhere else.

    Largest first because (the heavy path) these are the low-voltage end's FIRST
    tenants and the big two -- the bulk cap and the connector -- are the ones
    that have to reach the strip; the bus's chip caps follow their adjacency
    to whichever of them is down."""
    pwr12 = ix.classes["PWR12"]
    here = [it for it in ix.on(board) if any(n in pwr12 for n in it.nets)]
    src = next((it.refdes for it in sorted(here, key=lambda i: _ref_key(i.refdes))
                if it.kind == "CONVERTER"), None)
    away = [it.refdes for it in here if it.kind == "CONN" and it.interface
            and any(o.interface == it.interface and o.board != board
                    for o in ix.items.values() if o.refdes != it.refdes)]
    parts = sorted((it.refdes for it in here
                    if it.refdes != src and not ix.is_hv(it.refdes)),
                   key=lambda r: (-ix.items[r].body[0] * ix.items[r].body[1], _ref_key(r)))
    return src, (sorted(away, key=_ref_key)[0] if away else None), parts

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

# --- reports ----------------------------------------------------------------------
def _ref_key(ref):
    m = re.match(r"^([A-Z]+)(\d+)(.*)$", ref)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (ref, 0, "")



# --- the net classes, and the facts that assign them ----------------------------

@dataclass(frozen=True)
class NetClass:
    name: str
    width_mm: float
    clearance_mm: float
    why: str
    #: A class whose copper may be a POUR instead of a trace: the width is then
    #: met by the plane, and the class's copper check accepts the pour in its place.
    pour_ok: bool = False

#: IPC-2221B Table 6-1 B2 (external, uncoated) for the 151-300 V band, which is
#: where the 160 V do-not-exceed falls.  The clearance is `layout_rules`'
#: figure -- the same one the HV placement gap is judged by -- so the routing
#: rule and the placement rule cannot drift apart.  The 0.5 mm width is not a
#: current figure: the HV nets carry 1.93 A at the 60 V LVC
#: (`power_budget`), which 0.5 mm of 1 oz copper takes at a ~10 degC rise; it is a
#: MINIMUM so that a pack-voltage trace is never a hair that a nick opens.
HV = NetClass("HV", 0.5, layout_rules.HV_CLEARANCE_MM,
              f"IPC-2221B B2 at the 160 V do-not-exceed ({layout_rules.HV_CLEARANCE_MM} mm); "
              f"0.5 mm is a floor on pack-voltage copper, not the 1.93 A it carries")

#: 11.39 A -- the LIMITED case (`power_budget.limit_case`), not the 8.47 A
#: nominal: the copper has to survive every TPS4H160B limiter at its ceiling at
#: once.  IPC-2152, external 1 oz, 20 degC rise: 5 mm carries ~11 A.  A POUR is
#: better and is what R1 gives OUTPUTS; POWER has no room for one across the
#: partition and gets a 5 mm trace (class copper).
PWR12 = NetClass("PWR12", 5.0, 0.3,
                 "11.39 A limited case over 1 oz external copper (IPC-2152, 20 degC rise)",
                 pour_ok=True)

#: 4 x 1.39 A = 5.6 A at the four TPS2553 limiters, all of which can be at
#: their ceiling together.  IPC-2152 external 1 oz at a 20 degC rise: 2.0 mm.
PWR5AUX = NetClass("PWR5AUX", 2.0, 0.3, "5.6 A -- four 1.39 A limiters at their ceiling")

#: 1.55 A per 12 V channel at its own limiter (`R359` = 1k5 sets the
#: TPS4H160B's current limit).  1.0 mm of 1 oz external copper carries it at a
#: ~10 degC rise, which is the margin a channel that may be shorted needs.
CH12 = NetClass("CH12", 1.0, 0.25, "1.55 A per channel at the TPS4H160B limiter")

#: 1.39 A per 5 V channel at the TPS2553's limit.  0.8 mm, same derivation.
CH5 = NetClass("CH5", 0.8, 0.25, "1.39 A per channel at the TPS2553 limiter")

#: `V5` and `V3P3`: under an amp but on many pins.  The width is for DROOP, not
#: heat -- 0.6 mm keeps a 300 mA rail inside a few millivolts over the length of
#: a board -- and LOGIC's `V3P3` gets a pour instead (R1).
RAIL = NetClass("RAIL", 0.6, 0.25, "the logic supplies: width for droop, not for heat",
                pour_ok=True)

#: The CAN pair.  120 ohm is not achievable at 0.25 mm over 0.2 mm prepreg and is
#: not the constraint: the run is electrically short (< 150 mm), so what matters
#: is that the two stay PAIRED and skew-matched, and that nothing else comes
#: inside 0.4 mm of them.
DIFF = NetClass("DIFF", 0.25, 0.4, "a short, paired CAN run: pairing and skew, not impedance")

#: An ADC input beside an 11 A pour reads the pour.  0.3 mm of clearance to
#: everything, and check `SENSE beside POWER` below adds the rule that really
#: matters: never within `SENSE_KEEP` of a PWR or CH12 segment on the same layer.
SENSE = NetClass("SENSE", 0.25, 0.3, "an analog input: clearance is the whole point")

#: Signals.  The editor's board-wide default is right for these, and it is what
#: the JLCPCB capability template already holds.
DEFAULT = NetClass("default", 0.2, 0.2, "a signal; JLC's 4-layer capability")

#: Every pour is inset this far from the board edge: the edge is where the
#: enclosure, a standoff or a finger meets the board, and a plane that reaches
#: it is a plane a mill can smear.  Half of `HV_EDGE`, which is what
#: pack-voltage COPPER keeps from the same edge -- a ground plane is not at
#: 84 V and does not need the full figure.
POUR_INSET = HV_EDGE / 2

#: Memo for the derivations the router asks for in its inner loop.  They are
#: pure functions of (`ix`, board) -- the design does not change under a
#: run -- and `net_class` walking every item of every board per obstacle took
#: the suite from 27 s to minutes.
_DERIVED: dict = {}

def _memo(key, make):
    if key not in _DERIVED:
        _DERIVED[key] = make()
    return _DERIVED[key]

def diff_nets(ix, board):
    """The differential pair on `board`, from the transceiver's OWN PIN NAMES
    (`CANH`, `CANL`) and never from a net called CANH: the pair is whatever the
    part with those pins is wired to.  Empty on a board with no transceiver --
    and the pair's nets are in the class on every board they REACH, because
    `CANH` crosses two interfaces (LOGIC's `J411` to CTRL's `J501`)."""
    def make():
        out = set()
        for it in ix.items.values():
            for pin, net in it.pin_net.items():
                if pin.upper() in ("CANH", "CANL") and it.kind == "IC" and net:
                    out.add(net)
        return {n for n in out
                if any(ix.items[r].board == board for r, _ in ix.members.get(n, ()))}
    return _memo((id(ix), board, "diff"), make)

def carries_bus(ix, board):
    """Is the 11.39 A actually ON this board?  The R0 table scopes PWR12 to
    "`V12` and its return **on OUTPUTS and POWER**", and this is that sentence
    derived rather than typed: the board that MAKES the bus (a converter whose
    `+V` is the `PWR12` net) or the board that LOADS it (the driver line).

    ⚠️ `V12` reaches all four boards.  On LOGIC it crosses two connectors and
    on CTRL it feeds one buck -- about 0.7 A between them, not 11.39 -- so
    those two get the RAIL class and its 0.6 mm, and class copper leaves them to
    the autorouter.  Calling them PWR12 asks for a 5 mm trace between two
    sockets at the back edge, which does not fit across a 41.84 mm board: the
    first run of this tool refused three LOGIC legs for leaving the outline,
    and the class was what was wrong, not the placement."""
    def make():
        if v12_line(ix, board):
            return True
        src, _, _ = v12_output(ix, board)
        return src is not None
    return _memo((id(ix), board, "bus"), make)

def net_class(ix, board, net):
    """The `NetClass` of `net` on `board`.  Strongest first: a net that is at
    pack voltage is HV whatever else it also is."""
    key = (id(ix), board, "class", net)
    if key in _DERIVED:
        return _DERIVED[key]
    _DERIVED[key] = cls = _net_class(ix, board, net)
    return cls

def _net_class(ix, board, net):
    if net in ix.hv.get(board, ()):
        return HV
    if net in ix.classes.get("PWR12", ()) and carries_bus(ix, board):
        return PWR12
    for cls in (PWR5AUX, CH12, CH5):
        if net in ix.classes.get(cls.name, ()):
            return cls
    if net in diff_nets(ix, board):
        return DIFF
    if net in ix.classes.get("SENSE", ()):
        return SENSE
    if net in ix.rails:
        return RAIL
    return DEFAULT

def heavy_classes():
    """The classes whose copper is RULE-DRIVEN: their width and their path are
    determined by the current they carry and the pads they join, so a tool can
    write them.  Everything else is the autorouter's."""
    return (HV, PWR12, PWR5AUX, CH12, CH5)

# --- IO-29: the clearance between two HV nets is their own difference ---------------
#: {net: ((low, high) volts at each of `soft_start.operating_points`)} for every
#: net in the HV class, built once.
_HV_VOLTS: dict = {}

def hv_node_voltages(d=None):
    """The HV class's nodes and what they sit at, from `soft_start`.

    ⛔ THE VOLTAGES ARE NOT TYPED HERE AND MUST NOT BE.  `soft_start` walks the
    netlist for them -- the switch, the chokes, the blocking diode, the divider
    strings' own resistor values -- so a resistor changed there moves the node,
    the IPC band it falls in and the copper spacing with it.  This function's
    only job is to take the nets the HV class actually holds and REFUSE if one
    of them has no derived voltage: a new 84 V net that nothing derives would
    otherwise fall through `pair_clearance`'s guard and be given a relaxed
    figure by default.  ✔ Proven to fire: `tests/test_layout_facts.py::
    test_an_hv_net_with_no_derived_voltage_is_refused`.
    """
    if not _HV_VOLTS:
        d = d or netlist.current()
        derived = soft_start.hv_node_ranges(d)
        wanted = {n for board in bp.STACK_ORDER for n in layout_rules.hv_nets(d, board)}
        missing = sorted(wanted - set(derived))
        if missing:
            raise RuntimeError(
                f"{', '.join(missing)}: in the HV class with no derived node voltage. "
                f"Derive it in tools/soft_start.py -- IO-29 sets the clearance between "
                f"two 84 V nets from their difference, and a net with no voltage has no "
                f"difference to set it from")
        _HV_VOLTS.update({n: derived[n] for n in sorted(wanted)})
    return _HV_VOLTS

def v12_line(ix, board):
    """The 12 V DRIVER LINE on `board`: every IC that takes the `PWR12` bus in
    on one pin and hands out a `CH12` channel on another.  Empty on a board
    that only carries `V12` past.

    ⭐ This is what decides which board's second inner layer is the `V12` pour
    (R1), and it is decided by the COPPER rather than by a board's name.  ⚠️
    "the board `V12` reaches" is not the test and was the first thing tried:
    `V12` reaches all four boards, and CTRL's `U305` sits on it -- but `U305`
    is a LOAD (its own outputs are the 5 V channels, which `PWR5AUX` carries
    as 2.0 mm traces), so pouring a plane for it would spend CTRL's second
    ground on 1.39 A."""
    def make():
        ch12 = ix.classes.get("CH12", ())
        pwr12 = ix.classes.get("PWR12", ())
        return tuple(sorted((it.refdes for it in ix.on(board)
                             if it.kind == "IC"
                             and any(n in pwr12 for n in it.nets)
                             and any(n in ch12 for n in it.nets)),
                            key=_ref_key))
    return _memo((id(ix), board, "line"), make)

#: A board earns a RAIL pour on its second inner layer when one logic rail has
#: at least this many pins on it.  DERIVED from the four boards as they stand
#: (`netlist.py`, 2026-09-22): LOGIC's `V3P3` has 57, and the next-best rail on
#: any board is CTRL's `V5AUX` at 13 -- which `PWR5AUX` routes as 2.0 mm trace
#: because it is a CURRENT, not a droop problem. 40 sits in that gap with room
#: either side, and what it protects is the choice R1 states: a plane is worth
#: more as a second GND than as a rail nobody has many pins on.
RAIL_POUR_PINS = 40

def _rail_pour_net(ix, board):
    """The logic rail that earns the second inner layer on `board`, or None."""
    best, count = None, 0
    for net in sorted(ix.rails):
        if net_class(ix, board, net) is not RAIL:
            continue
        pins = sum(it.nets.get(net, 0) for it in ix.on(board))
        if pins > count:
            best, count = net, pins
    return best if count >= RAIL_POUR_PINS else None
