#!/usr/bin/env python3
"""PCB routing for the four-board stack -- Part 2 of `layout/PROCESS.md`.

    python3 -m tools.route --check-routing [--board BOARD ...] [--file PATH]
    python3 -m tools.route --rules   [--board BOARD ...] [--file PATH] [--out PATH]
    python3 -m tools.route --pours   [--board BOARD ...] [--file PATH] [--out PATH]
    python3 -m tools.route --heavy   [--board BOARD ...] [--file PATH] [--out PATH]
    python3 -m tools.route --strip-routing BOARD [BOARD ...] [--file PATH] [--out PATH]
    python3 -m tools.route --draw DIR [--file PATH]          # and with any mode

A SIBLING of `tools/place.py`, not a second copy of it.  Every fact about the
design, the file and the board frame is read through `place` -- `place.load`,
`place.Index`, `place.Placement.from_file`, `place.Frame`, `place.power_classes`,
`place.hv_partition`, `place.v12_bus`, `place.v12_output` -- and every write goes
out through `place.write`, the round trip the build uses.  What lives here is
the COPPER: the class table, the design rules, the planes, the rule-driven
runs, and the check that reads a saved route back and refuses it.

⛔ THE TOOL DOES NOT ROUTE THE SIGNALS.  It writes the rules, the planes and the
copper whose width and path the rules DETERMINE -- an 8.47 A bus has one
shape -- and the editor's autorouter does the ~250 signal nets afterwards,
inside those rules.  `--check-routing` then gates the result.

THE FRAME.  `place.Frame` maps the file's portrait outline to the board frame
(u along the 242 mm length, v across, v = 0 the connector face).  Everything
here reasons in the BOARD frame and converts at the record boundary, so a
partition measured by `place` and a pour written by this tool cannot disagree
about which end of the board is which.

THE LAYERS.  `layout/PROCESS.md` counts layers by the STACKUP (1 top, 2 and 3
inner, 4 bottom); the file numbers them 1 top, 15 Inner1, 16 Inner2, 2 bottom
(`LAYER_PHYS` zIndex order).  `STACK_LAYER` is the one place the two meet.

Stdlib only (plus what `eprj2` needs to decrypt the file, and Pillow for
`--draw`, which is imported only when that flag is used).
"""
import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import board_params as bp, eprj2, layout_rules, netlist, place  # noqa: E402

MIL_PER_MM = place.MIL_PER_MM
TOL = place.TOL

EXIT_PROBLEMS = place.EXIT_PROBLEMS
EXIT_REFUSED = place.EXIT_REFUSED

# --- the stackup ------------------------------------------------------------------
#: PROCESS.md's stackup number -> the file's `layerId`.  A 4-layer JLC board is
#: Top / Inner1 / Inner2 / Bottom, and the editor numbers the inner pair 15 and
#: 16 while the outer pair keeps 1 and 2 -- read from `LAYER_PHYS`, whose
#: `zIndex` puts 1 (1000), 15 (1002), 16 (1004), 2 (9000) in that physical
#: order.  ⛔ Never write "layer 2" into a record meaning the second layer of
#: the stack: layerId 2 is the BOTTOM.
STACK_LAYER = {1: 1, 2: 15, 3: 16, 4: 2}
#: The two outer layers, where the parts and the hand routing are.
OUTER = (1, 2)

# --- R0: the class table ----------------------------------------------------------
#: The class a net is in is derived from the COPPER (`place.power_classes`,
#: `layout_rules.hv_nets`, the transceiver's own pin names), never from the
#: net's name, so a renamed or added net cannot end up in the wrong class.
#: Each width is for **1 oz outer copper**; `--copper-oz` re-derives them.


@dataclass(frozen=True)
class NetClass:
    name: str
    width_mm: float
    clearance_mm: float
    why: str
    #: A class whose copper may be a POUR instead of a trace: the width is then
    #: met by the plane, and `--check-routing` accepts the pour in its place.
    pour_ok: bool = False


#: IPC-2221B Table 6-1 B2 (external, uncoated) for the 151-300 V band, which is
#: where the 160 V do-not-exceed falls.  The clearance is `layout_rules`'
#: figure -- the same one check 7 uses as a placement proxy -- so the routing
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
#: partition and gets the 5 mm trace `--heavy` writes.
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

#: Strongest first.  ⚠️ The order is load-bearing: `HV_C1_P` and `HV_C2_HOLD`
#: are in `rules.rails(d)` as well as in the HV set, and a net that reaches the
#: RAIL row first would be routed at 0.6 mm and 0.25 mm clearance at 84 V.
CLASS_ORDER = (HV, PWR12, PWR5AUX, CH12, CH5, DIFF, SENSE, RAIL)

#: A `SENSE` segment keeps this from any `PWR12`, `PWR5AUX` or `CH12` segment
#: on the same layer (PROCESS.md R3).  1.0 mm is four times the 0.25 mm the
#: class table gives a signal pair and is what an 11 A edge couples across at
#: the ~10 kHz the limiters switch at; it is a KEEP, not a clearance -- the
#: clearance is met at 0.3 mm and this is the extra the analog reading needs.
SENSE_KEEP = 1.0
#: Every pour is inset this far from the board edge: the edge is where the
#: enclosure, a standoff or a finger meets the board, and a plane that reaches
#: it is a plane a mill can smear.  Half of `place.HV_EDGE`, which is what
#: pack-voltage COPPER keeps from the same edge -- a ground plane is not at
#: 84 V and does not need the full figure.
POUR_INSET = place.HV_EDGE / 2
#: A pour's own outline stroke, mm, as the editor writes it (`POUR.width`).
POUR_STROKE = 0.2
#: The editor's fill resolution for a SOLID pour, as it writes it.
POUR_FINENESS = 8
#: How far `--heavy` may miss a straight line and still call a leg straight:
#: one pad pitch of the finest footprint on these boards is 0.5 mm, so a
#: tenth of that is a dog-leg nobody drew on purpose.
STRAIGHT_TOL = 0.05


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
    those two get the RAIL class and its 0.6 mm, and `--heavy` leaves them to
    the autorouter.  Calling them PWR12 asks for a 5 mm trace between two
    sockets at the back edge, which does not fit across a 41.84 mm board: the
    first run of this tool refused three LOGIC legs for leaving the outline,
    and the class was what was wrong, not the placement."""
    def make():
        if v12_line(ix, board):
            return True
        src, _, _ = place.v12_output(ix, board)
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


def classed_nets(ix, board):
    """{net: NetClass} for every net of `board` that is NOT in the default
    class -- the ones `--rules` has to write a selector for."""
    nets = {n for it in ix.on(board) for n in it.nets if n}
    out = {}
    for n in sorted(nets):
        cls = net_class(ix, board, n)
        if cls is not DEFAULT:
            out[n] = cls
    return out


def heavy_classes():
    """The classes whose copper is RULE-DRIVEN: their width and their path are
    determined by the current they carry and the pads they join, so a tool can
    write them.  Everything else is the autorouter's."""
    return (HV, PWR12, PWR5AUX, CH12, CH5)


# --- the copper, read back --------------------------------------------------------
@dataclass(frozen=True)
class Seg:
    """One `LINE` record, board frame, mm."""
    net: str
    layer: int
    u0: float
    v0: float
    u1: float
    v1: float
    width: float
    record: int = -1

    @property
    def box(self):
        return place.Box(min(self.u0, self.u1) - self.width / 2,
                         min(self.v0, self.v1) - self.width / 2,
                         max(self.u0, self.u1) + self.width / 2,
                         max(self.v0, self.v1) + self.width / 2)

    @property
    def length(self):
        return ((self.u1 - self.u0) ** 2 + (self.v1 - self.v0) ** 2) ** 0.5


@dataclass(frozen=True)
class Via:
    """One `VIA` record, board frame, mm.  A NORMAL via's barrel crosses every
    layer, which is why it is checked against copper on all of them."""
    net: str
    u: float
    v: float
    diameter: float
    hole: float
    record: int = -1

    @property
    def box(self):
        r = self.diameter / 2
        return place.Box(self.u - r, self.v - r, self.u + r, self.v + r)


@dataclass(frozen=True)
class Pour:
    """One `POUR` record, board frame, mm.  `box` is the bounding box of its
    path, which is the whole of it for the rectangles this tool writes and a
    bound for a polygon the owner drew."""
    net: str
    layer: int
    box: object
    name: str
    record: int = -1


@dataclass(frozen=True)
class Pad:
    """A placed pad: copper at a fixed place, on one face or on both.

    ⚠️ `radius` is set only for a pad the FOOTPRINT draws as a circle (an
    `ELLIPSE` whose two axes are equal -- which is every through-hole pad in
    this project's libraries).  Anything else is measured as its bounding box,
    which OVER-reports for an oval or a rounded rectangle: the error is on the
    side of reporting a clearance tighter than it is, never looser."""
    ref: str
    pin: str
    net: str
    box: object
    layers: tuple
    tht: bool
    radius: float = 0.0

    @property
    def u(self):
        return self.box.cu

    @property
    def v(self):
        return self.box.cv


@dataclass
class Copper:
    """Everything on one board that is copper: what the file holds and what the
    placement puts there."""
    board: str
    frame: object
    segs: list = field(default_factory=list)
    vias: list = field(default_factory=list)
    pours: list = field(default_factory=list)
    pads: list = field(default_factory=list)

    #: `on_layer`, its bucket index and the pin lands, each built once.
    #: Rebuilding the layer list inside the router's inner loop cost 45 s of a
    #: 47 s run.
    _by_layer: dict = field(default_factory=dict)
    _index: dict = field(default_factory=dict)
    _lands: dict = field(default_factory=dict)

    def on_layer(self, layer):
        """Every piece of copper that exists on `layer`: the segments and pours
        drawn there, every via (the barrel crosses the board) and every pad
        that is either surface-mount on this face or through-hole."""
        if layer not in self._by_layer:
            self._by_layer[layer] = ([s for s in self.segs if s.layer == layer]
                                     + list(self.vias)
                                     + [p for p in self.pads if layer in p.layers])
        return self._by_layer[layer]

    def pin_lands(self):
        """{(refdes, pin): the box its pads together occupy} -- a PIN's land,
        which is what a run lands on.  ⚠️ One pin can own several pads
        (`U303.OUT1` owns two), and the point `nodes_of` aims a run at is their
        mean, which falls BETWEEN them and inside neither.  Both the router and
        `is_neck` have to agree on what "on the pad" means, or the tool writes
        a neck its own check calls a thin bus -- which is what happened on
        OUTPUTS' `AUX12V_1` the first time the clustered placement was routed."""
        if not self._lands:
            for p in self.pads:
                key = (p.ref, p.pin)
                b = self._lands.get(key)
                self._lands[key] = p.box if b is None else place.Box(
                    min(b.u0, p.box.u0), min(b.v0, p.box.v0),
                    max(b.u1, p.box.u1), max(b.v1, p.box.v1))
        return self._lands

    def near(self, layer, box, margin):
        """The copper of `layer` whose own u-range comes within `margin` of
        `box` -- the same set `on_layer` gives, narrowed by a bucket index so
        the router does not measure the whole board against every leg."""
        if layer not in self._index:
            self._index[layer] = _buckets(self.on_layer(layer), 0.0)
        idx = self._index[layer]
        out, seen = [], set()
        for i in range(int((box.u0 - margin) // BUCKET), int((box.u1 + margin) // BUCKET) + 1):
            for it in idx.get(i, ()):
                if id(it) not in seen:
                    seen.add(id(it))
                    out.append(it)
        return out


def documents(project):
    """{PCB title: (first record index, [records])} of `project`, recomputed
    from its record list so an edit made here lands in the right document.
    `place.load` keeps only the COMPONENT records' indices; the copper needs
    the whole document."""
    lead, docs = eprj2.documents(project.records)
    out, pos = {}, len(lead)
    for doc_type, uuid, recs in docs:
        start, pos = pos, pos + len(recs)
        if doc_type != "PCB":
            continue
        title = next(json.loads(p)["title"] for h, p in recs if h["type"] == "META")
        out[title] = (start, recs)
    return out


def pad_shapes(project):
    """{footprint uuid: ((cx, cy, hw, hh, round) per PAD record, mm, in the
    order the records appear)} -- the pad's COPPER in the footprint's own frame.

    ⚠️ Not the same thing as `place.Envelope.pads`, on purpose.  The envelope
    carries a pad's EXTENT for a courtyard: it takes `max(defaultPad, hole)`,
    ignores the pad's own `relativeAngle` and its offset, and never says what
    shape the copper is.  All three are the right simplifications for a
    courtyard -- each one makes the box bigger, never smaller.  A CLEARANCE
    needs the copper itself, so this reads it:

    - the pad's COPPER is `defaultPad` alone.  The envelope takes
      `max(defaultPad, hole)` so a bare mounting hole still has an extent;
      for copper the hole is INSIDE the pad and taking the larger of the two
      only ever makes the pad look bigger than it is.
    - an `ELLIPSE` with equal axes is a CIRCLE, and measuring a round
      through-hole pad by its circumscribed square over-reports a diagonal
      trace's clearance to it by up to 0.41 x its radius -- which on this
      project's 2.4 mm through-hole pads is half a millimetre of phantom
      violation.
    - `padAngle` turns the pad.  ⛔ `relativeAngle` and `padOffsetX/Y` do NOT:
      the editor's own encoder writes them from `holeRotation` and
      `holeOffset`, so they turn and move the DRILL inside the pad.  Reading
      them as the pad's own turn swaps a chip pad's width and height and puts
      a D-PAK's tab 2 mm off its body -- checked against `Q101`'s land, whose
      330.709 x 417.638 mil tab sits on a 10.41 x 15.88 mm body only one way
      round.

    A shape this cannot resolve (an oval, a polygon, a pad turned off the
    quarter) falls back to the circumscribed box, which is the safe direction:
    it reports a clearance tighter than it is, never looser."""
    out = {}
    for uuid, recs in project.footprints.items():
        pads = []
        for h, p in recs:
            if h["type"] != "PAD":
                continue
            o = json.loads(p)
            dp = o.get("defaultPad") or {}
            hole = o.get("hole") or {}
            w = dp.get("width") or hole.get("width") or 0.0
            hgt = dp.get("height") or hole.get("height") or 0.0
            turn = float(o.get("padAngle") or 0) % 360
            if abs(turn - 90) < 1 or abs(turn - 270) < 1:
                w, hgt = hgt, w
            elif turn % 180 > 1:                # not on a quarter: circumscribe it
                w = hgt = max(w, hgt)
            pads.append((o["centerX"] / MIL_PER_MM, o["centerY"] / MIL_PER_MM,
                         w / 2 / MIL_PER_MM, hgt / 2 / MIL_PER_MM,
                         (dp.get("padType") == "ELLIPSE" and abs(w - hgt) < 1e-6)))
        out[uuid] = tuple(pads)
    return out


def copper(project, pl, ix, board):
    """The `Copper` of `board`: the file's LINE, VIA and POUR records in the
    board frame, and every placed pad with the net its pin carries."""
    frame = pl.frame(board)
    c = Copper(board, frame)
    start, recs = documents(project).get(board, (0, []))
    shapes = pad_shapes(project)
    doc = project.pcbs.get(board)
    for i, (h, p) in enumerate(recs):
        if h["type"] not in ("LINE", "VIA", "POUR"):
            continue
        o = json.loads(p)
        if h["type"] == "LINE":
            u0, v0 = frame.to_board(o["startX"] / MIL_PER_MM, o["startY"] / MIL_PER_MM)
            u1, v1 = frame.to_board(o["endX"] / MIL_PER_MM, o["endY"] / MIL_PER_MM)
            c.segs.append(Seg(o.get("netName", ""), int(o["layerId"]), u0, v0, u1, v1,
                              o["width"] / MIL_PER_MM, start + i))
        elif h["type"] == "VIA":
            u, v = frame.to_board(o["centerX"] / MIL_PER_MM, o["centerY"] / MIL_PER_MM)
            c.vias.append(Via(o.get("netName", ""), u, v,
                              o["viaDiameter"] / MIL_PER_MM, o["holeDiameter"] / MIL_PER_MM,
                              start + i))
        else:
            pts = []
            place._path_points(o["path"], pts)
            if not pts:
                continue
            board_pts = [frame.to_board(x / MIL_PER_MM, y / MIL_PER_MM) for x, y in pts]
            box = place.Box(min(u for u, _ in board_pts), min(v for _, v in board_pts),
                            max(u for u, _ in board_pts), max(v for _, v in board_pts))
            c.pours.append(Pour(o.get("netName", ""), int(o["layerId"]), box,
                                o.get("name", ""), start + i))
    for ref, pd in pl.boards.get(board, {}).items():
        if pd.unplaced or ref not in ix.items:
            continue
        item = ix.items[ref]
        comp = doc.components.get(ref) if doc else None
        copper_pads = shapes.get(comp.footprint, ()) if comp else ()
        for i, ((num, box), pad) in enumerate(zip(pd.pad_boxes(frame), pd.env.pads)):
            tht = bool(pad[5])
            radius = 0.0
            if i < len(copper_pads):
                cx, cy, hw, hh, round_ = copper_pads[i]
                box = place._place_box(frame, cx - hw, cy - hh, cx + hw, cy + hh,
                                       pd.u, pd.v, pd.angle, pd.bottom)
                radius = hw if round_ else 0.0
            c.pads.append(Pad(ref, num, item.pin_net.get(num, ""), box,
                              OUTER if tht else (pd.layer,), tht, radius))
    return c


# --- geometry ----------------------------------------------------------------------
def _seg_point_gap(s, pu, pv):
    return place._point_segment(pu, pv, (s.u0, s.v0), (s.u1, s.v1))


def _seg_seg_centreline(a, b):
    """Distance between two segments' centrelines."""
    if _crosses(a, b):
        return 0.0
    return min(_seg_point_gap(a, b.u0, b.v0), _seg_point_gap(a, b.u1, b.v1),
               _seg_point_gap(b, a.u0, a.v0), _seg_point_gap(b, a.u1, a.v1))


def _crosses(a, b):
    def side(x0, y0, x1, y1, px, py):
        return (x1 - x0) * (py - y0) - (y1 - y0) * (px - x0)
    d1 = side(a.u0, a.v0, a.u1, a.v1, b.u0, b.v0)
    d2 = side(a.u0, a.v0, a.u1, a.v1, b.u1, b.v1)
    d3 = side(b.u0, b.v0, b.u1, b.v1, a.u0, a.v0)
    d4 = side(b.u0, b.v0, b.u1, b.v1, a.u1, a.v1)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _seg_box_gap(s, box):
    """Edge-to-edge gap between a segment's copper and a box (a pad).  The
    segment is a rectangle of its own width; the box is the pad's own extent."""
    grown = place.Box(box.u0 - s.width / 2, box.v0 - s.width / 2,
                      box.u1 + s.width / 2, box.v1 + s.width / 2)
    return _centreline_box_gap(s, grown)


def _centreline_box_gap(s, box):
    """How far the segment's CENTRELINE stays outside `box` -- 0 if it enters."""
    if _point_in(box, s.u0, s.v0) or _point_in(box, s.u1, s.v1):
        return 0.0
    edges = ((box.u0, box.v0, box.u1, box.v0), (box.u1, box.v0, box.u1, box.v1),
             (box.u1, box.v1, box.u0, box.v1), (box.u0, box.v1, box.u0, box.v0))
    best = min(_seg_seg_centreline(s, Seg("", s.layer, *e, 0.0)) for e in edges)
    return best


def _point_in(box, u, v):
    return box.u0 - TOL <= u <= box.u1 + TOL and box.v0 - TOL <= v <= box.v1 + TOL


def _circle(x):
    """(centre u, centre v, radius) where the piece of copper is round, else
    None.  A via always is; a pad is where its footprint draws it as one."""
    if isinstance(x, Via):
        return (x.u, x.v, x.diameter / 2)
    if isinstance(x, Pad) and x.radius:
        return (x.u, x.v, x.radius)
    return None


def gap(a, b):
    """Edge-to-edge clearance, mm, between two pieces of copper -- a `Seg`, a
    `Via` or a `Pad` in any combination.  Negative is never returned: two
    pieces that touch are at 0."""
    if isinstance(a, Seg) and isinstance(b, Seg):
        return max(0.0, _seg_seg_centreline(a, b) - a.width / 2 - b.width / 2)
    if isinstance(a, Seg):
        return _seg_other_gap(a, b)
    if isinstance(b, Seg):
        return _seg_other_gap(b, a)
    ca, cb = _circle(a), _circle(b)
    if ca and cb:
        d = ((ca[0] - cb[0]) ** 2 + (ca[1] - cb[1]) ** 2) ** 0.5
        return max(0.0, d - ca[2] - cb[2])
    if ca or cb:
        circ, box = (ca, b.box) if ca else (cb, a.box)
        du = max(box.u0 - circ[0], 0.0, circ[0] - box.u1)
        dv = max(box.v0 - circ[1], 0.0, circ[1] - box.v1)
        return max(0.0, (du * du + dv * dv) ** 0.5 - circ[2])
    return max(0.0, a.box.separation(b.box))


def _seg_other_gap(s, other):
    circ = _circle(other)
    if circ:
        return max(0.0, _seg_point_gap(s, circ[0], circ[1]) - s.width / 2 - circ[2])
    return max(0.0, _seg_box_gap(s, other.box))


def _layers_of(x):
    if isinstance(x, Seg):
        return (x.layer,)
    if isinstance(x, Via):
        return None                 # every layer
    return tuple(x.layers)


def _meets(a, b):
    la, lb = _layers_of(a), _layers_of(b)
    if la is None or lb is None:
        return True
    return bool(set(la) & set(lb))


def _net_of(x):
    return x.net


# --- R3: the check ------------------------------------------------------------------
#: The u-bucket the clearance sweep sorts copper into, mm.  A bucket has to be
#: wider than the widest clearance any class asks for (1.25 mm) plus the
#: longest piece of copper it may hold; 20 mm is comfortably both and keeps the
#: pair count down by ~an order of magnitude on a fully routed board.
BUCKET = 20.0


def _buckets(items, extra):
    """{bucket index: [item]}, an item in every bucket its grown box touches."""
    out = {}
    for it in items:
        box = it.box
        for i in range(int((box.u0 - extra) // BUCKET), int((box.u1 + extra) // BUCKET) + 1):
            out.setdefault(i, []).append(it)
    return out


def clearance_problems(c, ix, board):
    """Every pair of copper on `board` that is closer than the stronger of the
    two nets' class clearances, one entry per class: the worst offender.

    ⛔ PAD TO PAD IS NOT CHECKED, and that is deliberate.  Two pads of a
    manufacturer's land pattern sit where the manufacturer put them; a class
    rule is about what ROUTING may do, and the editor's own rules keep pad
    spacing out of it too (`OTHER.deviceClearance`, 0 in the JLC template).
    What is checked is what the router chose: segment to segment, segment to
    pad, and a via to anything -- a via's barrel crosses every layer, so it is
    the one object compared against copper on all of them."""
    need = {}

    def cls_of(net):
        return net_class(ix, board, net) if net else DEFAULT

    worst = {}
    layers = sorted({s.layer for s in c.segs} | set(OUTER))
    for layer in layers:
        items = c.on_layer(layer)
        for it in items:
            need.setdefault(_net_of(it), cls_of(_net_of(it)))
        widest = max((need[_net_of(it)].clearance_mm for it in items), default=0.0)
        bk = _buckets(items, widest)
        seen = set()
        for _, group in sorted(bk.items()):
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    if _net_of(a) == _net_of(b) or not _meets(a, b):
                        continue
                    if isinstance(a, Pad) and isinstance(b, Pad):
                        continue
                    key = (id(a), id(b)) if id(a) < id(b) else (id(b), id(a))
                    if key in seen:
                        continue
                    seen.add(key)
                    ca, cb = need[_net_of(a)], need[_net_of(b)]
                    want = max(ca.clearance_mm, cb.clearance_mm)
                    g = gap(a, b)
                    if g >= want - TOL:
                        continue
                    strong = ca if ca.clearance_mm >= cb.clearance_mm else cb
                    slack = want - g
                    n = worst[strong.name][6] + 1 if strong.name in worst else 1
                    if strong.name not in worst or slack > worst[strong.name][0]:
                        worst[strong.name] = (slack, want, g, a, b, layer, n)
                    else:
                        worst[strong.name] = worst[strong.name][:6] + (n,)
    return worst


def _describe(x):
    if isinstance(x, Seg):
        return f"{x.net or '<no net>'} segment"
    if isinstance(x, Via):
        return f"{x.net or '<no net>'} via"
    return f"{x.ref}.{x.pin} ({x.net or 'no net'})"


def check_routing(project, pl, ix, boards=None):
    """PROCESS.md R3, on a saved file: every problem as a line, worst offender
    per class.  Never writes and never guesses -- a board with no copper on it
    has nothing to fail."""
    problems = []
    for board in (boards or bp.STACK_ORDER):
        if board not in pl.project.pcbs:
            continue
        c = copper(project, pl, ix, board)
        problems += _check_widths(c, ix, board)
        problems += _check_clearances(c, ix, board)
        problems += _check_hv_over_plane(c, ix, board, pl)
        problems += _check_pour_extent(c, ix, board, pl)
        problems += _check_v12_carrier(c, ix, board)
        problems += _check_sense_beside_power(c, ix, board)
    return problems


def is_neck(c, s):
    """Is `s` a NECK -- the short piece of narrower copper where a run enters
    the pad it lands on?  Two conditions, and both are needed: it is at most
    `NECK_MM` long, and one of its ends is ON a pad of its own net.  Drop the
    second and a whole thin bus reads as a chain of necks; drop the first and
    a thin run that happens to start at a pad reads as one."""
    if s.length > NECK_MM + TOL:
        return False
    lands = c.pin_lands()
    return any(p.net == s.net and s.layer in p.layers
               and (_point_in(lands[(p.ref, p.pin)], s.u0, s.v0)
                    or _point_in(lands[(p.ref, p.pin)], s.u1, s.v1))
               for p in c.pads)


def _check_widths(c, ix, board):
    """R0: every segment at least its class's width.  Two exemptions, both
    stated in R0 itself: a class whose copper may be a POUR (`pour_ok`) is
    exempt where the pour exists -- the plane IS the conductor there, and a
    stitch from a pad onto it is not a bus -- and a NECK at a pad is exempt,
    because a run wider than its pad has to enter it somehow."""
    out, worst = [], {}
    poured = {(p.net, p.layer) for p in c.pours}
    for s in c.segs:
        cls = net_class(ix, board, s.net)
        if cls is DEFAULT or s.width >= cls.width_mm - TOL:
            continue
        if cls.pour_ok and any(n == s.net for n, _ in poured):
            continue
        if is_neck(c, s):
            continue
        key = cls.name
        if key not in worst or s.width < worst[key].width:
            worst[key] = s
    for name, s in sorted(worst.items()):
        cls = next(k for k in CLASS_ORDER if k.name == name)
        out.append(f"{board}: class {name} width -- {s.net} is {s.width:.3f} mm over "
                   f"{s.length:.1f} mm on layer {s.layer} at u {s.box.cu:.1f}, v "
                   f"{s.box.cv:.1f}, and is not a neck at a pad; the class needs "
                   f"{cls.width_mm:.2f} mm ({cls.why})")
    return out


def _check_clearances(c, ix, board):
    out = []
    for name, (slack, want, got, a, b, layer, n) in sorted(
            clearance_problems(c, ix, board).items()):
        out.append(f"{board}: class {name} clearance -- {n} pair(s) short of {want:.2f} mm; "
                   f"the worst is {_describe(a)} to {_describe(b)} at {got:.3f} mm on layer "
                   f"{layer} (short by {slack:.3f})")
    return out


def hv_plane_layers(c, ix, board, pl):
    """The layers that carry a GND pour reaching under the 84 V end of `board`:
    84 V to a plane across one 0.2 mm prepreg is the thing the 1.25 mm rule
    forbids, and a plane is not something you can keep 1.25 mm from in Z.
    Empty on a board with no partition (no pack voltage on it)."""
    part = place.hv_partition(pl, ix, board)
    if part is None:
        return (), None
    low, far, line = part
    hv_end = place.Box(0.0, -1e6, far, 1e6) if low else place.Box(far, -1e6, 1e9, 1e6)
    layers = tuple(sorted({p.layer for p in c.pours
                           if p.net in ix.gnd and p.box.overlaps(hv_end)}))
    return layers, (low, far, line)


def _check_hv_over_plane(c, ix, board, pl):
    """R1: no HV copper on a layer whose GND plane reaches the 84 V end, and no
    HV via at all while such a plane exists -- a NORMAL via's barrel crosses
    every layer, so it meets the plane whatever layer the trace is on."""
    layers, part = hv_plane_layers(c, ix, board, pl)
    if not layers:
        return []
    hv = ix.hv.get(board, ())
    out = []
    bad = [s for s in c.segs if s.net in hv and s.layer in layers]
    if bad:
        worst = min(bad, key=lambda s: s.box.cu)
        out.append(f"{board}: R1 -- {len(bad)} pack-voltage segment(s) on layer(s) "
                   f"{', '.join(str(x) for x in layers)}, which carry a GND pour reaching the "
                   f"84 V end (u < {part[1]:.1f} mm); first is {worst.net} at u "
                   f"{worst.box.cu:.1f}. 84 V to a plane across one 0.2 mm prepreg is what the "
                   f"{layout_rules.HV_CLEARANCE_MM} mm rule forbids")
    vias = [v for v in c.vias if v.net in hv]
    if vias:
        out.append(f"{board}: R1 -- {len(vias)} pack-voltage via(s) through the GND pour on "
                   f"layer(s) {', '.join(str(x) for x in layers)}; a NORMAL via's barrel crosses "
                   f"every layer, first at u {vias[0].u:.1f}")
    return out


def _check_pour_extent(c, ix, board, pl):
    """R1: on the board that carries pack voltage, no pour may reach past the
    partition.  The FLOOR is the far edge of the 84 V parts (`hv_partition`'s
    middle term, which is the line less `HV_STRIP`); `--pours` writes the pour
    at the line itself, so the 3 mm of cut-back R1 asks for is margin the check
    does not spend."""
    part = place.hv_partition(pl, ix, board)
    if part is None:
        return []
    low, far, line = part
    out = []
    for p in sorted(c.pours, key=lambda q: (q.layer, q.name)):
        over = (p.box.u0 < far - TOL) if low else (p.box.u1 > far + TOL)
        if not over:
            continue
        edge = p.box.u0 if low else p.box.u1
        out.append(f"{board}: R1 pour extent -- {p.net} pour {p.name or '?'} on layer {p.layer} "
                   f"reaches u {edge:.1f} mm, past the partition at {far:.1f} mm "
                   f"(the 84 V end is u {'below' if low else 'above'} it); "
                   f"--pours writes it at {line:.1f}")
    return out


def _check_v12_carrier(c, ix, board):
    """R0/R1: the 12 V bus is a pour or it is >= 5 mm of trace.  `V12` is a
    rail on four boards; what this asks about is the board where the 11.39 A
    IS -- one that carries a `PWR12` part that is not just a decoupler, i.e.
    the board the bus is made on or the board it feeds."""
    pwr12 = ix.classes.get("PWR12", ())
    nets = sorted(n for n in pwr12 if any(ix.items[r].board == board
                                          for r, _ in ix.members.get(n, ())))
    if not nets:
        return []
    out = []
    for net in nets:
        if any(p.net == net for p in c.pours):
            continue
        segs = [s for s in c.segs if s.net == net]
        if not segs:
            continue
        body = [s for s in segs if not is_neck(c, s)] or segs
        thin = min(body, key=lambda s: s.width)
        if thin.width < PWR12.width_mm - TOL:
            out.append(f"{board}: {net} is carried by neither a pour nor "
                       f"{PWR12.width_mm:.1f} mm of copper -- the thinnest of {len(segs)} "
                       f"segment(s) that is not a neck at a pad is {thin.width:.3f} mm on "
                       f"layer {thin.layer} at u {thin.box.cu:.1f} ({PWR12.why})")
    return out


def _check_sense_beside_power(c, ix, board):
    """R3: an analog input may not run beside the bus it is measuring."""
    sense = [s for s in c.segs if net_class(ix, board, s.net) is SENSE]
    if not sense:
        return []
    loud = [s for s in c.segs
            if net_class(ix, board, s.net) in (PWR12, PWR5AUX, CH12)]
    worst = None
    for a in sense:
        for b in loud:
            if a.layer != b.layer or a.net == b.net:
                continue
            g = gap(a, b)
            if g < SENSE_KEEP - TOL and (worst is None or g < worst[0]):
                worst = (g, a, b)
    if worst is None:
        return []
    g, a, b = worst
    return [f"{board}: SENSE beside power -- {a.net} is {g:.2f} mm from {b.net} on layer "
            f"{a.layer} at u {a.box.cu:.1f}; a SENSE net keeps {SENSE_KEEP:.1f} mm from a "
            f"PWR or CH12 segment on its own layer"]


# --- writing records ---------------------------------------------------------------
def _rid(*parts):
    """A 16-hex-character record id, the shape the editor uses, derived from
    what the record IS.  Deterministic: the same design writes the same file,
    which is what lets a re-read be compared record for record."""
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _mil(mm):
    return place._mil(mm)


class DocEdit:
    """One PCB document's records, being edited in place inside a `Project`."""

    def __init__(self, project, board):
        self.project = project
        self.board = board
        self.start, self.recs = documents(project)[board]
        self.end = self.start + len(self.recs)
        self.max_ticket = max((h.get("ticket", 0) for h, _ in self.recs), default=0)

    def find(self, type_, id_=None):
        for i, (h, p) in enumerate(self.recs):
            if h["type"] == type_ and (id_ is None or h.get("id") == id_):
                return self.start + i, h, p
        return None

    def replace(self, index, payload):
        h, _ = self.project.records[index]
        self.project.records[index] = (h, eprj2._compact(payload))

    def append(self, type_, id_, payload):
        self.max_ticket += 1
        head = {"type": type_, "ticket": self.max_ticket, "id": id_}
        self.project.records.insert(self.end, (head, eprj2._compact(payload)))
        self.end += 1

    def drop(self, indices):
        for i in sorted(indices, reverse=True):
            del self.project.records[i]
        self.end -= len(indices)


# --- R0 written into the project (`--rules`) ---------------------------------------
#: The rule categories a net class needs: the clearance matrix and the track
#: width.  Discovered from the editor's own example project
#: (`example-projects/Example_3D Shell Design.eprj2`, which THIS editor
#: converted from `.eprj`): a `RULE` named other than the default, plus a
#: `RULE_SELECTOR` per net whose `ruleKeyValue` names it by category.  There
#: the category was `TRACK` and the rule a 20 mil power trace; the owner's own
#: POWER document carries the same shape for `COPPER` on `GND`.  The category
#: KEYS are the editor's own numeric rule ids by name -- 1 SAFE, 3 TRACK,
#: 6 PLANE, 7 COPPER -- read out of the bundle's numeric-to-name map.
#: ⛔ There is no persisted NET_CLASS record: a class is a set of per-net
#: selectors pointing at one named rule, which is why `--rules` writes one
#: selector per member net.
RULE_CATEGORIES = ("SAFE", "TRACK")
#: `ruleState` on a rule that is NOT the category's board-wide default, as the
#: editor writes a user-added rule beside its `DEFAULT` one.
RULE_STATE = "NORMAL"
#: `ruleOrder` 4 is the NET / NET_CLASS scope -- the only order at which the
#: editor reads `ruleKeyValue` as a per-net override.
NET_RULE_ORDER = 4


def _safe_rule(default_payload, clearance_mm):
    """A SAFE rule at `clearance_mm`, built from the board's own DEFAULT one so
    the matrix keeps its shape and its layer set.  Every cell is RAISED to the
    class figure and none is lowered: the matrix's rows are element-type pairs
    (track, pad, via, copper, hole, outline, text ...) and raising all of them
    is the conservative reading of "this net keeps 1.25 mm from everything"."""
    payload = json.loads(json.dumps(default_payload))
    want = clearance_mm * MIL_PER_MM
    for layer in payload["ruleContext"].get("safeSpacing", []):
        layer["content"] = [[round(max(v, want), 4) for v in row] for row in layer["content"]]
    payload["ruleState"] = RULE_STATE
    return payload


def _track_rule(default_payload, width_mm):
    """A TRACK rule whose minimum and default are the class width.  The maximum
    is the template's own, so the owner can still draw wider by hand."""
    payload = json.loads(json.dumps(default_payload))
    w = round(width_mm * MIL_PER_MM, 4)
    for row in payload["ruleContext"]["track"]["content"]:
        row["stroMin"] = w
        row["stroDef"] = w
        row["stroMax"] = max(row.get("stroMax", w), w)
    payload["ruleState"] = RULE_STATE
    return payload


def write_rules(project, pl, ix, boards=None):
    """R0 into every named board's PCB document: one named `RULE` per class per
    category, and one `RULE_SELECTOR` per classed net.  The JLCPCB capability
    template and its ALL-nets rules are left exactly as they are -- they stay
    the default for the ~250 signal nets, which is what they are right for.

    Returns {board: [what was written]}."""
    written = {}
    for board in (boards or bp.STACK_ORDER):
        if board not in project.pcbs:
            continue
        doc = DocEdit(project, board)
        defaults = {}
        for cat in RULE_CATEGORIES:
            found = None
            for i, (h, p) in enumerate(doc.recs):
                if h["type"] != "RULE":
                    continue
                rid = json.loads(h["id"])
                if rid[1] == cat and json.loads(p).get("ruleState") == "DEFAULT":
                    found = json.loads(p)
                    break
            if found is None:
                raise RuntimeError(f"{board}: the PCB has no DEFAULT {cat} rule to build on")
            defaults[cat] = found
        nets = classed_nets(ix, board)
        used = sorted({cls.name: cls for cls in nets.values()}.items())
        lines = []
        for name, cls in used:
            for cat in RULE_CATEGORIES:
                payload = (_safe_rule(defaults[cat], cls.clearance_mm) if cat == "SAFE"
                           else _track_rule(defaults[cat], cls.width_mm))
                rid = json.dumps(["RULE", cat, name], separators=(",", ":"))
                hit = doc.find("RULE", rid)
                if hit:
                    doc.replace(hit[0], payload)
                else:
                    doc.append("RULE", rid, payload)
            lines.append(f"{name}: {cls.width_mm:.2f} mm wide, {cls.clearance_mm:.2f} mm clear "
                         f"-- {cls.why}")
        for net, cls in sorted(nets.items()):
            rid = json.dumps(["RULE_SELECTOR", ["NET", net]], separators=(",", ":"))
            hit = doc.find("RULE_SELECTOR", rid)
            payload = json.loads(hit[2]) if hit else {"ruleOrder": NET_RULE_ORDER,
                                                      "ruleKeyValue": {}, "copperValue": {},
                                                      "innerPlaneValue": {}}
            payload["ruleOrder"] = NET_RULE_ORDER
            payload.setdefault("ruleKeyValue", {})
            payload.setdefault("copperValue", {})
            payload.setdefault("innerPlaneValue", {})
            for cat in RULE_CATEGORIES:
                payload["ruleKeyValue"][cat] = cls.name
            if hit:
                doc.replace(hit[0], payload)
            else:
                doc.append("RULE_SELECTOR", rid, payload)
        written[board] = lines + [f"{len(nets)} net selector(s)"]
    return written


def rules_text(ix, d=None):
    """The class table as the owner reads it -- what `--rules` wrote, and what
    to enter by hand if a rule record ever has to be typed into the editor
    instead.  `build-eprj3/layout-rules.txt` already carries the HV class;
    this is every class, per board."""
    out = ["# Net classes and design rules — what `tools/route.py --rules` writes", "",
           "Each class is one named `RULE` per category (`SAFE`, `TRACK`) plus one",
           "`RULE_SELECTOR` per member net. In the editor by hand that is:",
           "**PCB → Design Rules → Safe Spacing / Track**, a rule per row below, then",
           "**Design → Net Class** with the nets listed and the rule applied to it.", "",
           "| Class | Width | Clearance | Why |", "|---|---|---|---|"]
    for cls in CLASS_ORDER + (DEFAULT,):
        out.append(f"| {cls.name} | {cls.width_mm:.2f} mm | {cls.clearance_mm:.2f} mm | "
                   f"{cls.why} |")
    for board in bp.STACK_ORDER:
        nets = classed_nets(ix, board)
        out += ["", f"## {board}", ""]
        if not nets:
            out.append("Every net is in the default class.")
            continue
        by = {}
        for net, cls in sorted(nets.items()):
            by.setdefault(cls.name, []).append(net)
        for name, members in sorted(by.items()):
            out.append(f"- **{name}** ({len(members)}): {', '.join(members)}")
    return "\n".join(out) + "\n"


# --- R1 written into the project (`--pours`) ---------------------------------------
def pour_plan(project, pl, ix, board):
    """The pours R1 asks of `board`: [(stack layer, net, Box, why)].  Every
    rectangle is DERIVED -- the outline from the file, the cut-back from
    `place.hv_partition`, the `V12` pour's span from the bus's own pads."""
    frame = pl.frame(board)
    full = place.Box(POUR_INSET, POUR_INSET, frame.length - POUR_INSET,
                     frame.width - POUR_INSET)
    part = place.hv_partition(pl, ix, board)
    gnd = sorted(ix.gnd & {n for it in ix.on(board) for n in it.nets})
    gnd_net = "GND" if "GND" in gnd else (gnd[0] if gnd else None)
    if gnd_net is None:
        return []
    if part is None:
        plane, why = full, "the whole board: no pack voltage reaches it"
    else:
        low, far, line = part
        plane = (place.Box(line, full.v0, full.u1, full.v1) if low
                 else place.Box(full.u0, full.v0, line, full.v1))
        why = (f"cut back at the partition: the 84 V end is u "
               f"{'0 to' if low else 'above'} {far:.1f} mm and the plane starts at the line, "
               f"{line:.1f} mm, which is {place.HV_STRIP:.1f} mm of clearance to pack voltage")
    out = [(2, gnd_net, plane, why)]
    third = _third_layer(project, pl, ix, board, full, plane, why)
    if third is not None:
        out.append(third)
    return out


def _third_layer(project, pl, ix, board, full, plane, plane_why):
    """R1's second inner layer, decided by what the board CARRIES: the 12 V
    pour where the bus is, the 3.3 V pour where the pin count is, a second
    ground where neither earns a rail."""
    drivers = v12_line(ix, board)
    box = v12_pour_box(pl, ix, board) if drivers else None
    if box is not None:
        net = sorted(ix.classes["PWR12"])[0]
        return (3, net, box, f"the bus IS the pour: {' '.join(drivers)} take 12 V in and hand "
                             f"out limited channels, and it spans their bus pads and the feed's "
                             f"own contacts (check 11, amended)")
    rail = _rail_pour_net(ix, board)
    if rail is not None:
        pins = sum(it.nets.get(rail, 0) for it in ix.on(board))
        return (3, rail, full, f"{pins} pins on {rail}: a pour for droop, not for current")
    gnd = sorted(ix.gnd & {n for it in ix.on(board) for n in it.nets})
    return (3, "GND" if "GND" in gnd else gnd[0], plane,
            "a second ground: this board's returns outnumber anything a rail would earn"
            + ("; " + plane_why if plane is not full else ""))


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
                            key=place._ref_key))
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


def v12_pour_box(pl, ix, board):
    """The layer-3 `V12` pour of `board` (R1), or None where the board has no
    12 V bus to pour.

    ⛔ ONE FACT, ONE HOME: the rectangle is `place.v12_pour`'s, because that is
    what the amended check 11 MEASURES.  A pour written from a second
    derivation would let the placement check pass on a span the pour does not
    have."""
    got = place.v12_pour(pl, ix, board)
    return None if got is None else got[0]


def _pour_record(frame, net, layer, box, name, order):
    """A `POUR` payload, file frame, mil.  ⭐ No `POURED` record is written:
    the editor's own example project (`Example_3D Shell Design.eprj2`) carries
    POUR records with NO POURED beside them, so the filled result is
    regenerated rather than stored -- and a POURED written by hand would be a
    fill this tool computed, not the editor's, which is worse than none."""
    x0, y0 = frame.to_file(box.u0, box.v0)
    x1, y1 = frame.to_file(box.u1, box.v1)
    fx0, fx1 = min(x0, x1), max(x0, x1)
    fy0, fy1 = min(y0, y1), max(y0, y1)
    return {"partitionId": "", "groupId": 0, "netName": net, "layerId": layer,
            "width": POUR_STROKE, "name": name, "order": order,
            "path": [["R", _mil(fx0), _mil(fy1), _mil(fx1 - fx0), _mil(fy1 - fy0), 0, 0]],
            "pourType": {"pourType": "SOLID", "fineness": POUR_FINENESS},
            "keepIsland": False, "locked": False, "zIndex": -1}


def write_pours(project, pl, ix, boards=None):
    """R1 into every named board: the planes and the one power pour each board
    earns, replacing any pour already there (an autoroute's plane over the
    whole board is exactly what this is here to correct)."""
    written = {}
    for board in (boards or bp.STACK_ORDER):
        if board not in project.pcbs:
            continue
        plan = pour_plan(project, pl, ix, board)
        doc = DocEdit(project, board)
        doc.drop([doc.start + i for i, (h, _) in enumerate(doc.recs)
                  if h["type"] in ("POUR", "POURED")])
        doc = DocEdit(project, board)
        frame = pl.frame(board)
        lines = []
        for order, (stack, net, box, why) in enumerate(plan):
            layer = STACK_LAYER[stack]
            name = f"POUR{order + 1}"
            payload = _pour_record(frame, net, layer, box, name, order)
            doc.append("POUR", _rid(board, "POUR", net, layer, name), payload)
            lines.append(f"layer {stack} (layerId {layer}): {net} over "
                         f"u {box.u0:.1f}..{box.u1:.1f}, v {box.v0:.1f}..{box.v1:.1f} mm "
                         f"-- {why}")
        written[board] = lines
    return written


# --- R2 written into the project (`--heavy`) ---------------------------------------
@dataclass(frozen=True)
class Node:
    """One pin of one part, as a routing endpoint: the pin's own pads."""
    ref: str
    pin: str
    net: str
    u: float
    v: float
    layers: tuple
    box: object


@dataclass
class Leg:
    net: str
    cls: str
    layer: int
    width: float            # the class width the BODY is drawn at
    segs: tuple             # the `Seg`s that go into the file, necks included
    a: str
    b: str

    @property
    def necked(self):
        return any(s.width < self.width - TOL for s in self.segs)


@dataclass
class Refusal:
    net: str
    a: str
    b: str
    why: str

    def __str__(self):
        return f"{self.net}: {self.a} to {self.b} -- {self.why}"


def nodes_of(c, net):
    """The endpoints of `net` on this board: one per (part, pin), at the mean
    of that pin's pads, on the layers that pin's copper exists on."""
    by = {}
    for pad in c.pads:
        if pad.net != net:
            continue
        by.setdefault((pad.ref, pad.pin), []).append(pad)
    out = []
    for (ref, pin), pads in sorted(by.items(), key=lambda kv: place._ref_key(kv[0][0])):
        u = sum(p.u for p in pads) / len(pads)
        v = sum(p.v for p in pads) / len(pads)
        layers = tuple(sorted(set.intersection(*[set(p.layers) for p in pads])))
        box = place.Box(min(p.box.u0 for p in pads), min(p.box.v0 for p in pads),
                        max(p.box.u1 for p in pads), max(p.box.v1 for p in pads))
        out.append(Node(ref, pin, net, u, v, layers, box))
    return out


def _tree(nodes, draw):
    """The net's spanning tree, grown Prim-style by MANHATTAN distance -- the
    metric the runs are actually drawn in -- with `draw(a, b)` deciding whether
    each candidate leg can be drawn at all.

    ⭐ THE TREE IS BUILT OUT OF LEGS THAT EXIST.  A plain minimum spanning tree
    joins a node by its nearest neighbour and stops; when that one leg is
    blocked the node is simply not connected, even though a slightly longer
    legal leg was available.  That is what happened to POWER's bus on the first
    run: the tree hung `J202` off `C208` because that was 2 mm shorter, the
    5 mm run hit `C211`, and `U201 -> C207 -> J202` -- the chain check 19
    measures, and the one the 8.47 A actually takes -- went unrouted while the
    stubs between the chip caps were drawn.  So each node is offered every leg
    to the tree in turn, shortest first, and only a node that NO legal leg
    reaches is refused.  Returns ([(a, b, leg)], [(a, b, why)])."""
    if len(nodes) < 2:
        return [], []
    inside, outside = [nodes[0]], list(nodes[1:])
    drawn, refused = [], []
    while outside:
        cands = sorted(((abs(a.u - b.u) + abs(a.v - b.v), i, j)
                        for i, a in enumerate(inside) for j, b in enumerate(outside)),
                       key=lambda t: (round(t[0], 4), t[1], t[2]))
        taken = None
        first_why = ""
        for _, i, j in cands:
            leg, why = draw(inside[i], outside[j])
            if leg is not None:
                taken = (i, j, leg)
                break
            first_why = first_why or why
        if taken is None:
            _, i, j = cands[0]
            refused.append((inside[i], outside[j], first_why))
            inside.append(outside.pop(j))
            continue
        i, j, leg = taken
        a, b = inside[i], outside.pop(j)
        drawn.append((a, b, leg))
        inside.append(b)
    return drawn, refused


def _candidates(a, b):
    """The Manhattan routes between two nodes, best first: the straight run
    when they line up, then the two single-corner L's.  ⛔ Nothing else --
    `--heavy` refuses rather than routing round an obstacle, because a bus that
    wanders is a bus whose length nobody derived."""
    out = []
    if abs(a.u - b.u) < STRAIGHT_TOL or abs(a.v - b.v) < STRAIGHT_TOL:
        out.append(((a.u, a.v), (b.u, b.v)))
    out.append(((a.u, a.v), (b.u, a.v), (b.u, b.v)))
    out.append(((a.u, a.v), (a.u, b.v), (b.u, b.v)))
    return [p for p in out if len({tuple(q) for q in p}) > 1]


def _leg_segs(net, layer, width, points):
    """The polyline as `Seg`s, all at one width."""
    return [Seg(net, layer, points[i][0], points[i][1], points[i + 1][0], points[i + 1][1], width)
            for i in range(len(points) - 1)
            if abs(points[i][0] - points[i + 1][0]) > TOL
            or abs(points[i][1] - points[i + 1][1]) > TOL]


#: How long a NECK may be: the short piece of narrower copper where a run
#: enters the pad it lands on.  ⭐ A neck is not a compromise, it is how a run
#: wider than its pad is drawn -- a 5 mm bus cannot land on `J202`'s 3.96 mm
#: pitch contact, and a 2 mm `V5AUX` run cannot leave a 1.5 mm chip pad,
#: without one.  Refusing instead was tried first and cost the headline run:
#: `C207.+ -> J202.V12`, the leg check 19 exists to keep short, is exactly the
#: one a full-width rectangle cannot land.
#:
#: THE ARITHMETIC, from the worst case this project has: a 1.5 mm neck in
#: 35 um (1 oz) copper is 1.724e-8 / (0.0015 x 35e-6) = 0.328 ohm per metre, so
#: 3 mm of it is 0.985 mOhm and the LIMITED 11.39 A drops **11.2 mV** across
#: it.  The bus's whole budget is 50 mV (`place.V12_POUR_MM` derives it: 0.42 %
#: of the 12 V rail, so the farthest channel sees its limiter's ceiling and not
#: a sagged rail), and TWO necks spend under half of it.  Longer than this and
#: the neck stops being an entry and starts being the run.
NECK_MM = 3.0
#: The widths a neck is tried at, as fractions of what the pad itself can
#: carry: the pad's own narrower side first, then a little under two thirds of
#: it, then the board default.  Three tries, because a neck that has to be
#: thinner than 0.2 mm is not a neck -- it is a pad in the wrong place.
NECK_STEPS = (1.0, 0.6)


def _neck_widths(node, width):
    """The widths to try for the run entering `node`, widest first.  A run is
    never usefully wider than the pad it lands on, and a neck is never thinner
    than the board default."""
    cap = min(width, node.box.w, node.box.d)
    out = []
    for f in NECK_STEPS:
        w = round(min(width, cap * f), 4)
        if w > DEFAULT.width_mm and w not in out:
            out.append(w)
    out.append(DEFAULT.width_mm)
    return [w for w in out if w <= width + TOL]


def _necked_segs(net, layer, width, points, wa, wb):
    """The polyline drawn as a run: a neck of `wa` entering the first point, a
    neck of `wb` entering the last, the class `width` between them.

    Each neck is cut inside the polyline's FIRST (or last) straight, never
    across its corner, and is at most a third of the run -- so a neck segment
    always has the pad at one end, which is what lets `--check-routing` tell a
    neck from a thin bus."""
    full = _leg_segs(net, layer, width, points)
    if not full:
        return []
    total = sum(s.length for s in full)
    out = list(full)
    for at_end, w in ((False, wa), (True, wb)):
        if w >= width - TOL:
            continue
        s = out[-1] if at_end else out[0]
        cut = min(NECK_MM, s.length / 2, total / 3)
        if cut <= TOL:
            continue
        fx = (s.u1 - s.u0) / s.length, (s.v1 - s.v0) / s.length
        if at_end:
            mu, mv = s.u1 - fx[0] * cut, s.v1 - fx[1] * cut
            out[-1:] = [Seg(net, layer, s.u0, s.v0, mu, mv, width),
                        Seg(net, layer, mu, mv, s.u1, s.v1, w)]
        else:
            mu, mv = s.u0 + fx[0] * cut, s.v0 + fx[1] * cut
            out[0:1] = [Seg(net, layer, s.u0, s.v0, mu, mv, w),
                        Seg(net, layer, mu, mv, s.u1, s.v1, width)]
    return [s for s in out if s.length > TOL]


#: ⛔ THERE IS NO TAPER EXEMPTION, and that is a decision, not an omission.
#: A run that leaves a 1.5 mm chip pad at 2.0 mm has to neck down, and a hand
#: router draws that neck.  `--heavy` writes `LINE` records, which have ONE
#: width each, so a leg it "drew" with the neck excused would be a full-width
#: rectangle lying across the pad next door -- a SHORT in the saved file, not
#: a taper.  Excusing it also split the tool in two: `--heavy` would write
#: copper that its own `--check-routing` then refused.  So a leg that cannot
#: be drawn at the class width with the class clearance is REFUSED and named,
#: and the owner necks it by hand or moves the part.
#: What that costs, measured on this placement (2026-09-22): 8 of CTRL's
#: `V5AUX` legs and 5 of POWER's 84 V legs, every one of them a run leaving a
#: 0603 whose other pad is 0.0-0.3 mm away.

#: The widest clearance any class asks for: what the router's obstacle search
#: has to reach, because the figure that binds a leg is the STRONGER of the two
#: nets' classes and the other net may be the strong one.
WIDEST_CLEARANCE = max(cls.clearance_mm for cls in CLASS_ORDER + (DEFAULT,))


def _blocker(c, ix, board, segs, net, clearance, frame, extra, ends=()):
    """What stops this run, or None.  A blocker is other-net copper that the
    swept trace comes within `clearance` of, the board edge, or an M3 washer
    square -- a hole with a washer on it is not board a trace may cross.

    `ends` is ((refdes, u, v), ...) for the pins the run lands on -- used only
    to word the refusal, never to excuse copper."""
    for s in segs:
        box = s.box
        if box.u0 < -TOL or box.v0 < -TOL or box.u1 > frame.length + TOL \
                or box.v1 > frame.width + TOL:
            return "it leaves the board outline"
        for corner in frame.corners:
            if box.overlaps(corner):
                return (f"it crosses the M3 washer square at u {corner.cu:.1f}, "
                        f"v {corner.cv:.1f}")
        for other in c.near(s.layer, box, WIDEST_CLEARANCE) + list(extra):
            if other.net == net:
                continue
            if isinstance(other, Seg) and other.layer != s.layer:
                continue
            # ⚠️ the STRONGER of the two classes, which is what
            # `clearance_problems` measures.  Using the run's own figure alone
            # wrote a 1.0 mm CH12 channel 0.25 mm from a `V12` pad, and the
            # tool's own check then refused it: a router and a DRC that
            # disagree are worse than either alone.
            need = max(clearance, net_class(ix, board, other.net).clearance_mm
                       if other.net else DEFAULT.clearance_mm)
            g = gap(s, other)
            if g < need - TOL:
                near = any(other.ref == ref for ref, _, _ in ends) \
                    if isinstance(other, Pad) else False
                return (f"{_describe(other)} is {g:.2f} mm away and the class needs "
                        f"{need:.2f}"
                        + (" -- the run would have to neck down out of its own pad, and a "
                           "LINE record has one width" if near else ""))
    return None


def heavy_runs(project, pl, ix, board, c=None):
    """The rule-driven copper of `board`: ([Leg], [Refusal]).

    Every heavy class, every net in it, every leg of the net's Manhattan
    spanning tree, at the class width.  A net whose copper R1 gives to a POUR
    is skipped -- the plane carries it, and a trace beside a plane is a second
    conductor nobody sized."""
    c = c or copper(project, pl, ix, board)
    frame = pl.frame(board)
    poured = {p.net for p in c.pours}
    legs, refusals, extra = [], [], []
    for cls in heavy_classes():
        nets = sorted(n for n in _class_nets(ix, board, cls)
                      if any(p.net == n for p in c.pads))
        for net in nets:
            if net in poured:
                continue
            legs_here, refs_here = _route_net(c, ix, board, net, cls, frame, extra)
            legs += legs_here
            refusals += refs_here
            for leg in legs_here:
                extra += list(leg.segs)
    twin_legs, twin_refs = _return_twin(c, ix, board, frame, extra)
    legs += twin_legs
    refusals += twin_refs
    return legs, refusals


def _class_nets(ix, board, cls):
    """The nets of `board` in `cls`, judged by `net_class` -- so a net that is
    PWR12 where the bus is and RAIL where it is only passing through lands in
    one class on one board and the other on the next."""
    nets = {n for it in ix.on(board) for n in it.nets if n}
    return {n for n in nets if net_class(ix, board, n) is cls}


def _draw_leg(c, ix, board, net, name, width, clearance, frame, extra):
    """`draw(a, b) -> (Leg or None, why)` for `_tree`: the straight run if the
    two line up, else the two single-corner L's, on the outer layer they
    share."""
    def draw(a, b):
        shared = sorted(set(a.layers) & set(b.layers) & set(OUTER))
        if not shared:
            return None, (f"no shared outer layer: {a.ref} is on {a.layers}, {b.ref} on "
                          f"{b.layers} -- the run needs a via, which --heavy does not place")
        why = ""
        for layer in shared:
            for points in _candidates(a, b):
                ends = ((a.ref, a.u, a.v), (b.ref, b.u, b.v))
                # the BODY first: the necks only change the two ends, so a run
                # whose middle is blocked cannot be saved by any neck, and
                # trying every pair of them there was 45 s of a 47 s run.
                thinnest = _necked_segs(net, layer, width, points,
                                        DEFAULT.width_mm, DEFAULT.width_mm)
                body = [x for x in thinnest if x.width >= width - TOL]
                blocked = _blocker(c, ix, board, body, net, clearance, frame, extra, ends=ends)
                if blocked is not None:
                    why = why or blocked
                    continue
                for wa in _neck_widths(a, width):
                    for wb in _neck_widths(b, width):
                        segs = _necked_segs(net, layer, width, points, wa, wb)
                        blocked = _blocker(c, ix, board, segs, net, clearance, frame, extra,
                                           ends=ends)
                        if blocked is None:
                            return Leg(net, name, layer, width, tuple(segs),
                                       f"{a.ref}.{a.pin}", f"{b.ref}.{b.pin}"), ""
                        why = why or blocked
        return None, why
    return draw


def _route_net(c, ix, board, net, cls, frame, extra):
    draw = _draw_leg(c, ix, board, net, cls.name, cls.width_mm, cls.clearance_mm, frame, extra)
    drawn, refused = _tree(nodes_of(c, net), draw)
    return ([leg for _, _, leg in drawn],
            [Refusal(net, f"{a.ref}.{a.pin}", f"{b.ref}.{b.pin}", why)
             for a, b, why in refused])


def _return_twin(c, ix, board, frame, extra):
    """The 12 V run's GROUND TWIN.  The 8.47 A that leaves on `V12` comes back
    on `GND`, and on POWER it cannot come back on the plane: R1 cuts both inner
    planes off at the partition and the brick's output pins stand AT the
    partition, so the return would have to cross the cut to reach copper.  So
    it is a trace of the same class as the bus, over the same parts -- the
    converter that makes the bus, the bulk cap on it and the contact that takes
    it off the board (`place.v12_output`), which is exactly the chain check 19
    measures the 12 V side of."""
    src, away, parts = place.v12_output(ix, board)
    if src is None or away is None or not carries_bus(ix, board):
        return [], []
    poured = {p.net for p in c.pours}
    # the RETURN is the ground net that reaches BOTH ends of the bus.  ⚠️ Not
    # every net in the ground domain: `BASEPLATE` is on `U201` too (the brick's
    # Y-caps go to it) and is not a return -- it never reaches the connector
    # the 8.47 A leaves by, and routing it at 5 mm would put a wide plane-like
    # trace on a net that carries leakage.
    gnd = sorted(n for n in ix.gnd
                 if any(r == src for r, _ in ix.members.get(n, ()))
                 and any(r == away for r, _ in ix.members.get(n, ())))
    legs, refusals = [], []
    for net in gnd:
        if net in poured and not _plane_is_cut(c, net):
            continue
        refs = {src, away} | {r for r in parts if net in ix.items[r].nets}
        nodes = [n for n in nodes_of(c, net) if n.ref in refs]
        draw = _draw_leg(c, ix, board, net, "PWR12 return", PWR12.width_mm,
                         PWR12.clearance_mm, frame, extra)
        drawn, refused = _tree(nodes, draw)
        for _, _, leg in drawn:
            legs.append(leg)
            extra += list(leg.segs)
        refusals += [Refusal(net, f"{a.ref}.{a.pin}", f"{b.ref}.{b.pin}", why)
                     for a, b, why in refused]
    return legs, refusals


def _plane_is_cut(c, net):
    """Is this board's plane for `net` cut back, so it cannot be the return
    everywhere?  True where a pour on that net is shorter than the board by at
    least the strip R1 cuts -- which is POWER, and only POWER."""
    return any(p.net == net and p.box.w < c.frame.length - place.HV_STRIP
               for p in c.pours)


def _line_record(frame, seg):
    x0, y0 = frame.to_file(seg.u0, seg.v0)
    x1, y1 = frame.to_file(seg.u1, seg.v1)
    return {"partitionId": "", "groupId": 0, "netName": seg.net, "layerId": seg.layer,
            "startX": _mil(x0), "startY": _mil(y0), "endX": _mil(x1), "endY": _mil(y1),
            "width": _mil(seg.width), "locked": False, "zIndex": -1}


def write_heavy(project, pl, ix, boards=None):
    """R2's rule-driven copper into every named board.  Returns
    {board: ([Leg], [Refusal])}."""
    out = {}
    for board in (boards or bp.STACK_ORDER):
        if board not in project.pcbs:
            continue
        c = copper(project, pl, ix, board)
        legs, refusals = heavy_runs(project, pl, ix, board, c)
        doc = DocEdit(project, board)
        frame = pl.frame(board)
        n = 0
        for leg in legs:
            for seg in leg.segs:
                doc.append("LINE", _rid(board, "LINE", seg.net, seg.layer, seg.u0, seg.v0,
                                        seg.u1, seg.v1, seg.width), _line_record(frame, seg))
                n += 1
        out[board] = (legs, refusals)
    return out


# --- stripping a route (`--strip-routing`) -----------------------------------------
STRIP_TYPES = ("LINE", "VIA", "POUR", "POURED")


def strip_routing(project, boards):
    """Remove every LINE, VIA, POUR and POURED record of `boards` -- a bad
    autoroute, taken off so it can be redone.  ⛔ Nothing else is touched: the
    rules, the selectors, the components, the pad nets and every other board
    come through byte for byte, which is what the round-trip comparison then
    proves."""
    out = {}
    for board in boards:
        doc = DocEdit(project, board)
        idx = [doc.start + i for i, (h, _) in enumerate(doc.recs) if h["type"] in STRIP_TYPES]
        counts = {}
        for i, (h, _) in enumerate(doc.recs):
            if h["type"] in STRIP_TYPES:
                counts[h["type"]] = counts.get(h["type"], 0) + 1
        doc.drop(idx)
        out[board] = counts
    return out


# --- the picture ---------------------------------------------------------------------
#: Pixels per mm.  `place.DRAW_SCALE`, so a routing picture and a placement
#: picture of the same board are the same size and can be flipped between.
DRAW_SCALE = place.DRAW_SCALE
DRAW_MARGIN = place.DRAW_MARGIN
#: Pour fills, by what they are.  A plane is drawn as a light wash so the
#: copper on top of it stays readable; the point of the picture is the pour's
#: EXTENT, which is an edge, not a colour.
DRAW_POUR = {"GND": (210, 235, 210), "V12": (250, 225, 190), "V3P3": (225, 225, 250)}
DRAW_POUR_OTHER = (232, 232, 232)
#: Trace colours by layer: the file's own layer colours, dulled.
DRAW_LAYER = {1: (200, 30, 30), 2: (30, 30, 200), 15: (200, 90, 90), 16: (200, 130, 90)}
#: The partition, and the edge a cut-back plane must not pass.
DRAW_PARTITION = (150, 0, 150)


def draw(project, pl, ix, out_dir, prefix="routing"):
    """One PNG per board of the COPPER: the pours as washes with their edges
    drawn, every trace at its real width in its layer's colour, every via as a
    ring, the parts' bodies as thin grey boxes for context, and on the board
    with a partition a line at it.

    ✔ A STEP OF THE PROCESS.  The numbers say a pour stops at 167.7 mm; the
    picture says whether that is the end you meant."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as e:                    # pragma: no cover - Pillow is installed
        raise RuntimeError("--draw needs Pillow (PIL); the rest of the tool is stdlib") from e
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default()
    written = []
    for board in bp.STACK_ORDER:
        if board not in pl.project.pcbs:
            continue
        c = copper(project, pl, ix, board)
        fr = c.frame
        W = int(fr.length * DRAW_SCALE) + 2 * DRAW_MARGIN
        H = int(fr.width * DRAW_SCALE) + 2 * DRAW_MARGIN
        im = Image.new("RGB", (W, H), "white")
        dr = ImageDraw.Draw(im)

        def P(u, v):
            return (DRAW_MARGIN + u * DRAW_SCALE, H - DRAW_MARGIN - v * DRAW_SCALE)

        def R(a, b):
            (x0, y0), (x1, y1) = P(*a), P(*b)
            return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]

        for p in sorted(c.pours, key=lambda q: q.layer):
            fill = DRAW_POUR.get(p.net, DRAW_POUR_OTHER)
            dr.rectangle(R((p.box.u0, p.box.v0), (p.box.u1, p.box.v1)), fill=fill,
                         outline=tuple(max(0, v - 60) for v in fill), width=2)
            dr.text(P(p.box.u0 + 1, p.box.v1 - 2), f"{p.net} L{p.layer}",
                    fill=(90, 90, 90), font=font)
        dr.rectangle(R((0, 0), (fr.length, fr.width)), outline="black", width=3)
        for ref, pd in sorted(pl.boards[board].items(), key=lambda kv: place._ref_key(kv[0])):
            if pd.unplaced:
                continue
            dr.rectangle(R((pd.box.u0, pd.box.v0), (pd.box.u1, pd.box.v1)),
                         outline=(185, 185, 185), width=1)
        for s in c.segs:
            colour = DRAW_LAYER.get(s.layer, (120, 120, 120))
            dr.line([P(s.u0, s.v0), P(s.u1, s.v1)], fill=colour,
                    width=max(1, int(round(s.width * DRAW_SCALE))))
        for v in c.vias:
            r = v.diameter / 2
            dr.ellipse(R((v.u - r, v.v - r), (v.u + r, v.v + r)), outline=(0, 0, 0), width=2)
        part = place.hv_partition(pl, ix, board)
        if part is not None:
            low, far, line = part
            # the two lines are HV_STRIP (3 mm = 24 px) apart, and two labels
            # at the same height overprint each other into mush
            for n, (u, label) in enumerate(((far, "84 V ends"), (line, "the plane starts"))):
                dr.line([P(u, 0), P(u, fr.width)], fill=DRAW_PARTITION, width=2)
                dr.text((P(u, fr.width)[0] + 3, P(u, fr.width)[1] + 4 + 13 * n), label,
                        fill=DRAW_PARTITION, font=font)
        widths = sorted({round(s.width, 3) for s in c.segs})
        dr.text((DRAW_MARGIN, 10),
                f"{board}  {fr.length:.2f} x {fr.width:.2f} mm  face at the bottom (v = 0)  "
                f"{len(c.segs)} segment(s), {len(c.vias)} via(s), {len(c.pours)} pour(s)",
                fill="black", font=font)
        dr.text((DRAW_MARGIN, 26),
                "widths (mm): " + (", ".join(f"{w:g}" for w in widths) if widths else "none"),
                fill=(110, 110, 110), font=font)
        path = out_dir / f"{prefix}-{board}.png"
        im.save(path)
        written.append(path)
    return written


# --- command line ---------------------------------------------------------------------
def _load(src, ix):
    project = place.load(src)
    for board in bp.STACK_ORDER:
        if board not in project.pcbs:
            raise RuntimeError(f"{src} has no PCB titled {board}")
    return project, place.Placement.from_file(project, ix)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check-routing", action="store_true",
                      help="R3: read the saved route back and report every class rule it "
                           "breaks; never writes")
    mode.add_argument("--rules", action="store_true",
                      help="R0: write the net classes and design rules into every PCB document")
    mode.add_argument("--pours", action="store_true",
                      help="R1: write the planes and the one power pour each board earns")
    mode.add_argument("--heavy", action="store_true",
                      help="R2: write the rule-driven copper -- the 12 V bus, the 84 V chain, "
                           "the output channels. Refuses a run rather than routing round an "
                           "obstacle, and says which pair")
    mode.add_argument("--strip-routing", nargs="+", default=None, metavar="BOARD",
                      choices=bp.STACK_ORDER,
                      help="remove these boards' LINE, VIA, POUR and POURED records")
    ap.add_argument("--draw", default=None, metavar="DIR",
                    help="draw one PNG per board of the copper into DIR. LOOK AT IT")
    ap.add_argument("--board", nargs="+", default=None, metavar="BOARD", choices=bp.STACK_ORDER,
                    help="act on these boards only; every other board's records are left "
                         "exactly as saved")
    ap.add_argument("--file", default=None,
                    help=f"the .eprj2 to read (default: the editor's {place.PROJECT_FILE})")
    ap.add_argument("--out", default=None, help="where to write (default: --file, keeping .prev)")
    ap.add_argument("--rules-doc", default=None, metavar="PATH",
                    help="also write the whole class table, and each class's nets per board, as "
                         "text for hand entry in the editor. Not written unless asked: the rules "
                         "themselves go into the project, and a second copy of a table is a "
                         "second thing to keep true")
    a = ap.parse_args(argv)
    writing = a.rules or a.pours or a.heavy or a.strip_routing
    if not (a.check_routing or writing or a.draw):
        ap.error("one of --check-routing, --rules, --pours, --heavy, --strip-routing or "
                 "--draw is needed")
    src = Path(a.file) if a.file else place.default_file()
    if not src.is_file():
        print(f"REFUSED: {src} is not a file", file=sys.stderr)
        return EXIT_REFUSED
    try:
        d = netlist.checked()
    except netlist.NotACircuit as e:
        print(f"REFUSED -- {e}", file=sys.stderr)
        return EXIT_REFUSED
    ix = place.Index(d)
    try:
        project, pl = _load(src, ix)
    except RuntimeError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return EXIT_REFUSED
    picked = list(a.board) if a.board else None
    if a.rules_doc:
        Path(a.rules_doc).write_text(rules_text(ix, d), encoding="utf-8")
        print(f"written: {a.rules_doc}")
    problems = []
    if a.check_routing:
        problems = check_routing(project, pl, ix, boards=picked)
        print(f"{len(problems)} problem(s)"
              + ("" if problems else " -- the route passes every class rule"))
        for p in problems:
            print(f"  - {p}")
    if writing:
        if place.editor_running():
            print("REFUSED: EasyEDA Pro is running; close it first", file=sys.stderr)
            return EXIT_REFUSED
        out = Path(a.out) if a.out else src
        if a.rules:
            for board, lines in sorted(write_rules(project, pl, ix, boards=picked).items()):
                print(f"{board}:")
                for ln in lines:
                    print(f"  {ln}")
        elif a.pours:
            for board, lines in sorted(write_pours(project, pl, ix, boards=picked).items()):
                print(f"{board}:")
                for ln in lines:
                    print(f"  {ln}")
        elif a.heavy:
            for board, (legs, refusals) in sorted(write_heavy(project, pl, ix,
                                                              boards=picked).items()):
                total = sum(len(l.segs) for l in legs)
                print(f"{board}: {len(legs)} run(s), {total} segment(s), "
                      f"{len(refusals)} refused")
                for leg in legs:
                    necks = sorted({f"{s.width:.2f}" for s in leg.segs
                                    if s.width < leg.width - TOL})
                    print(f"  {leg.net} ({leg.cls}) {leg.a} -> {leg.b}: {leg.width:.2f} mm "
                          f"on layer {leg.layer}"
                          + (f", necked to {' and '.join(necks)} mm at the pad(s)"
                             if necks else ""))
                for r in refusals:
                    print(f"  REFUSED {r}")
        else:
            for board, counts in sorted(strip_routing(project, list(a.strip_routing)).items()):
                what = ", ".join(f"{n} {t}" for t, n in sorted(counts.items())) or "nothing"
                print(f"{board}: removed {what}")
        try:
            path = _write(project, pl, src, out)
        except RuntimeError as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return EXIT_REFUSED
        print(f"written: {path}")
        project, pl = _load(path, ix)
    if a.draw:
        for path in draw(project, pl, ix, a.draw, prefix=Path(a.out or src).stem + "-routing"):
            print(f"drawn: {path}")
    return EXIT_PROBLEMS if problems and a.check_routing else 0


def _write(project, pl, src, out):
    """Serialise `project` back through the build's round trip.  Unlike
    `place.write` this one has no placement to verify coordinate by
    coordinate -- what it verifies is that the stream re-reads, record for
    record, as what was meant."""
    if place.editor_running():
        raise RuntimeError("EasyEDA Pro is running -- close it before writing the project")
    import os
    out, src = Path(out), Path(src)
    text = eprj2.join(project.records)
    want = eprj2.split_records(text)
    tmp = out.with_name(out.name + ".routing")
    if tmp.exists():
        tmp.unlink()
    snap = project.snap
    eprj2.write(src, tmp, text, snap["structure"], snap["name"], owner=snap["owner"])
    if out.exists():
        prev = out.with_name(out.name + place.PREV_SUFFIX)
        if prev.exists():
            prev.unlink()
        os.replace(out, prev)
    os.replace(tmp, out)
    got = eprj2.split_records(eprj2.read(out)["text"])
    if len(got) != len(want):
        raise RuntimeError(f"{out}: re-reads as {len(got)} records, not {len(want)}")
    for i, ((ha, pa), (hb, pb)) in enumerate(zip(want, got)):
        if ha != hb or pa != pb:
            raise RuntimeError(f"{out}: record {i} ({ha.get('type')}) re-reads differently")
    return out


if __name__ == "__main__":
    sys.exit(main())
