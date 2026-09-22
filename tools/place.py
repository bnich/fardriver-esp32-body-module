#!/usr/bin/env python3
"""PCB placement for the four-board stack -- the process in `layout/PROCESS.md`.

    python3 -m tools.place --stack [--anchor centre] [--keep REF ...] [--file PATH] [--out PATH]
    python3 -m tools.place --check [--file PATH]
    python3 -m tools.place --draw DIR [--file PATH]        # and with either mode

`--stack` reads the owner's saved `.eprj2`, places every part of OUTPUTS, then
LOGIC, then CTRL, then POWER that is not in `--keep`, runs every check below, and writes
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

A THROUGH-HOLE PART CROSSES THE BOARD.  The two faces are not two independent
planes: a THT pad is copper on BOTH of them, and the pin tip and its solder
fillet stand proud of the far face, so a part on the other layer may not stand
on one (check 17, `PIN_PROTRUSION`).  Only the pads cross -- an SMD part over
a THT part's BODY on the other side is fine, which is how a 0603 sits over the
brick's case.  The harness row obeys the same fact through `edge_budget`: both
faces share ONE strip of the connector edge.

Stdlib only (plus what `eprj2` needs to decrypt the file, and Pillow for
`--draw`, which is imported only when that flag is used).
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
#: A through-hole pin's tip and its solder fillet stand ~3 mm proud of the FAR
#: face of the board, and the fillet spreads around the pad there.  This is the
#: room they need on that face: no body on the opposite layer may come closer
#: than this to a through-hole pad, or the pin is inside it.  It is the CHECK's
#: floor; the engine keeps `CLEAR` from a pad on the other face instead, which
#: is wider, because the pad is also COPPER there and a trace has to be able to
#: pass between the pin and its neighbour.
PIN_PROTRUSION = 1.0
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
#: Also the adjacency under which the HV parts must form ONE group, and
#: (IO-26 4a) the width of the STRIP that divides POWER along its length:
#: 84 V end | HV_STRIP | low-voltage end.  The strip's u is not typed -- it
#: starts where the 84 V parts' own lengths end (`hv_partition`).
HV_STRIP = 3.0
HV_GAP = 2 * COURTYARD + HV_STRIP
#: The S3's antenna end within this of the back edge (the U.FL pigtail leaves
#: the board there), and nothing in a zone this wide x deep beyond it.
ANTENNA_EDGE = 2.0
ANTENNA_ZONE_W, ANTENNA_ZONE_D = 18.0, 8.0
#: The V12 bus on OUTPUTS: the centroid of the V12-fed ICs within this of the
#: contact that feeds them (J311), so 8.47 A is one short wide bus, not a tree.
BUS_REACH = 15.0
#: (IO-26 3a) The driver line leaves a SLOT for the 12 V loom's four pins: the
#: feed's own through-hole pad row plus this much at each end, and a driver may
#: then stand right up to it.  The slot is `pad row + 2 x DRIVER_SLOT_MARGIN`,
#: derived from the footprint's pads and never typed.
#: What it protects: an **11.39 A** feed entering the layer-3 `V12` pour WHERE
#: THE LOAD IS.  Fed from the END of the line instead, the whole bus current
#: runs the length of every driver before it reaches the last one -- and the
#: pins may not simply come up under a driver, because a through-hole pad is
#: copper on both faces and the pin stands proud of the far one (check 17).
#: `CLEAR`, because that is exactly the room one 0.2 mm trace with its
#: clearances needs to pass between the pin and the driver beside it.
DRIVER_SLOT_MARGIN = CLEAR
#: (check 19, THE HEAVY PATH) The u-distance from the brick's `V12` output pad
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
#: 4.30 + 3.00 + 10.50 + 1.60 + 4.25 = **23.65 mm**, which is what the engine
#: places, and 25.0 carries it with ~6 % to spare.  The defects it stands
#: between: the cap turned to lie ALONG the run instead of across it puts its
#: 19.1 mm side in the way and scores 32; the connector left where the
#: low-voltage end had room for it scores ~50; the placement before this rule
#: scored **104.5**.
HEAVY_PATH_MM = 25.0
#: (check 19) A brick's INPUT bulk cap stands at its pack-voltage pins: the
#: u-distance from the cap's pads to the brick's `+Vin`/`-Vin` pads, LESS the
#: brick's own body where that lies between them -- board the cap may not
#: stand on, because two bodies on one face keep `CLEAR` and a through-hole
#: pad may not come up inside a body on the other face (check 17).  So the
#: figure is how far the cap is from the nearest place it could stand, and one
#: constant holds both bricks: `C201`, whose pins `U201` offers it, and
#: `C202`, whose 50.8 mm brick lies under the face row with its input pins at
#: the far side of its own case.
#:
#: THE ARITHMETIC, the two bricks in turn: `C201` stands at `U201`'s own pins
#: -- `CLEAR` (1.60, one 0.2 mm trace with its clearances between two
#: courtyards) + the can's leads 1.10 mm inside its end = **2.70**.  `C202`
#: has to round `U202`, and what it clears is not the brick but the FACE ROW
#: over it: `J101`'s body runs 5.30 mm past the brick's case, so 5.30 + 1.60 +
#: 1.10 = **8.03** as placed.  The 9.0 carries the worse of the two with ~12 %
#: to spare.  The defects it stands between: a can turned leads-away from its
#: brick scores 27, and one parked in the bulk pack instead of at its brick's
#: pins ~50.  What it protects: the 84 V input loop -- the cap IS the brick's
#: input source impedance, and a metre of loop is not a bulk cap.
BULK_REACH = 9.0
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
#: What a host pays in the packer for standing where its SATELLITE cannot
#: follow it.  A decoupler, an ADC filter's RC and the CAN transceiver are
#: placed against their host, so a host that lands in a hole exactly its own
#: size pushes its satellite across the board: `U406` was boxed in by `U405`,
#: the band-3 channel in front of it and `J406`'s through-hole pads behind,
#: and its 100 nF ended up 8.6 mm away, failing check 15 (2026-09-22).  It is
#: a COST, not a bar -- when no position on the board has room the host is
#: still placed and the check says so -- and it is worth this many millimetres
#: of the host's own travel, which is `DECOUPLE_REACH` three times over: past
#: that the host itself is in the wrong place.
SATELLITE_ROOM = 10.0
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


def _conflicts(box, other, gu, gv):
    """Does `box` come within (gu, gv) of `other`?  The packer's own test,
    written once so a keep-out and a slot scan cannot disagree."""
    return (box.u0 < other.u1 + gu - 1e-9 and other.u0 < box.u1 + gu - 1e-9
            and box.v0 < other.v1 + gv - 1e-9 and other.v0 < box.v1 + gv - 1e-9)


def _room_beside(box, reserve, length, width):
    """Is there room against `box` -- left, right, in front or behind, `CLEAR`
    away and on the board -- for the satellite that must follow this part?

    ⚠️ `reserve` carries the satellite's REAL plan at each quarter turn, one
    `(w, d)` per shape, and ANY of them fitting is room.  It used to carry
    `min(w)` and `min(d)` taken across the turns INDEPENDENTLY, which is a
    rectangle the part never has: a 2.0 x 1.25 chip reserved 1.25 x 1.25, so a
    pocket 1 mm too narrow for it in every orientation read as free and the
    host paid nothing (`C436` beside `U406`, found 2026-09-22)."""
    shapes, obs = reserve
    for w, d in shapes:
        spots = (Box(box.u0 - CLEAR - w, box.cv - d / 2, box.u0 - CLEAR, box.cv + d / 2),
                 Box(box.u1 + CLEAR, box.cv - d / 2, box.u1 + CLEAR + w, box.cv + d / 2),
                 Box(box.cu - w / 2, box.v0 - CLEAR - d, box.cu + w / 2, box.v0 - CLEAR),
                 Box(box.cu - w / 2, box.v1 + CLEAR, box.cu + w / 2, box.v1 + CLEAR + d))
        for s in spots:
            if s.u0 < -1e-9 or s.v0 < -1e-9 or s.u1 > length + 1e-9 or s.v1 > width + 1e-9:
                continue
            if not any(_conflicts(s, o, gu, gv) for o, gu, gv in obs):
                return True
    return False


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
            for num, lx, ly, _, _, _ in env.pads]


def placed_pad_boxes(env, frame, u, v, board_angle, bottom):
    """[(pad number, Box)] of `env` with its origin at (u, v)."""
    return [(num, _place_box(frame, lx - hw, ly - hh, lx + hw, ly + hh, u, v, board_angle, bottom))
            for num, lx, ly, hw, hh, _ in env.pads]


def placed_tht_boxes(env, frame, u, v, board_angle, bottom):
    """[Box] of the THROUGH-HOLE pads alone, with the origin at (u, v).  These
    are the boxes that exist on BOTH faces of the board, whichever face the
    part stands on."""
    return [_place_box(frame, lx - hw, ly - hh, lx + hw, ly + hh, u, v, board_angle, bottom)
            for _, lx, ly, hw, hh, tht in env.pads if tht]


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


def decoupler_hosts(ix, board):
    """{cap refdes: the IC it sits beside}.  The ICs on a rail take its 100 nFs
    in turn, so every IC on the rail gets one before any gets two.  The engine
    places a cap against this IC, and check 15 then asks only that it be near
    the NEAREST IC on the rail -- so a host that leaves its own cap no room is
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


def row_blocking_brick(ix, board):
    """The underside through-hole body too deep to sit behind the face row
    (`board_fit.row_blockers`): its pins would land in the row's plastic, so
    it takes a length of the connector edge itself.  On POWER that is `U201`,
    58.3 x 37.2 mm on a 41.84 mm board -- nothing can share its u, so where it
    stands decides the ORDER of the whole 84 V end, and (check 19) it stands
    against the partition with its 12 V end at the low-voltage end.  The
    largest where a board has several; None where it has none."""
    refs = [r for e in board_fit.edge_budget(ix.d) if e.board == board
            for r in e.blockers if r in ix.items]
    return max(refs, key=lambda r: (ix.items[r].body[0] * ix.items[r].body[1], r), default=None)


def bulk_caps(ix, board):
    """{input bulk cap: the brick it belongs to} on `board`, from the NETS and
    never from a name: a capacitor whose nets are exactly a converter's own
    pack-voltage input nets is that converter's input bulk.  `C201` sits on
    `HV_C1_P`/`HV_C1_N` and `C202` on `HV_C2_HOLD`/`HV_C2_N`, so each one
    names its brick by the copper it is on; the Y2 caps, which go from one of
    those nets to `BASEPLATE`, do not match and are not bulk."""
    out = {}
    for brick in ix.on(board):
        if brick.kind != "CONVERTER":
            continue
        high, _ = hv_pins(ix, brick.refdes)
        nets = {brick.pin_net[p] for p in high}
        if len(nets) < 2:
            continue
        for it in ix.on(board):
            if it.kind == "C" and set(it.nets) == nets:
                out[it.refdes] = brick.refdes
    return out


def v12_output(ix, board):
    """The 12 V output on `board`, all of it from the COPPER: `(the converter
    that makes the bus, the connector that takes it off the board, its other
    low-voltage parts -- largest body first)`.  PWR12 is the net the seated
    brick's own `+V` pin is on (`power_classes`), never a net's name, and the
    connector is the one whose other half stands on another board: `V12`
    leaves POWER on the loom and nowhere else.

    Largest first because (check 19) these are the low-voltage end's FIRST
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


def driver_slot(pads):
    """(u0, u1) of the gap a driver line leaves for a feed whose through-hole
    pad boxes are `pads`: the pad row plus `DRIVER_SLOT_MARGIN` at each end
    (IO-26 3a).  Derived from the footprint, never typed."""
    return (min(b.u0 for b in pads) - DRIVER_SLOT_MARGIN,
            max(b.u1 for b in pads) + DRIVER_SLOT_MARGIN)


def hv_partition(pl, ix, board="POWER"):
    """POWER's partition (IO-26 4a): `(the 84 V end is the low-u end, its far
    edge, where the low-voltage end starts)`, or None on a board that carries
    no pack voltage.

    ⭐ The line is DERIVED and nothing here is typed but `HV_STRIP`: the 84 V
    end reaches exactly as far as the 84 V parts' OWN LENGTHS take it -- the
    far edge of every part that carries pack voltage and nothing else, and the
    far edge of the pack-voltage PADS of a part that straddles, since a brick's
    output end is 12 or 5 V and belongs on the other side.  `HV_STRIP` beyond
    that, the low-voltage end begins.

    Which end is the 84 V end is read from the placement too: it is the end
    the pack-voltage harness terminal stands at (`J101` sits at the face of the
    HV end)."""
    hv = [p for p in pl.placed(board).values() if ix.is_hv(p.refdes)]
    if not hv:
        return None
    frame = pl.frame(board)
    term = next((p for p in sorted(hv, key=lambda q: _ref_key(q.refdes))
                 if ix.items[p.refdes].harness), None)
    here = term.box.cu if term is not None else sum(p.box.cu for p in hv) / len(hv)
    low = here < frame.length / 2
    edges = []
    for p in hv:
        if straddles(ix, p.refdes):
            edges += [(z.u1 if low else z.u0) for z in p.hv_zones(ix, frame)]
        else:
            edges.append(p.box.u1 if low else p.box.u0)
    far = max(edges) if low else min(edges)
    return low, far, (far + HV_STRIP if low else far - HV_STRIP)


def lv_end_needs(ix, board, width):
    """How much of the board's LENGTH the low-voltage end needs: the shelf
    pack of the low-voltage bodies (the measure `board_fit` budgets a face
    with) plus the M3 washer square at the far corner, which no body may
    stand on.  ⚠️ `C207` is a 10.5 x 19.1 mm polymer bulk cap, so the end
    cannot be narrower than 10.5 mm however few parts are in it."""
    rects = [(it.refdes, *it.body) for it in ix.on(board)
             if not ix.is_hv(it.refdes) and all(it.body)]
    if not rects:
        return 0.0
    span, _ = board_fit.shelf_pack(rects, width)
    return (span or 0.0) + 2 * M3_KEEPOUT


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

    @property
    def tht(self):
        """A through-hole part: at least one pad crosses the board."""
        return self.env.tht

    def tht_boxes(self, frame):
        """Its through-hole pads, board frame -- copper on both faces, with a
        pin tip and a fillet standing proud of the one it does not sit on."""
        return placed_tht_boxes(self.env, frame, self.u, self.v, self.angle, self.bottom)

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


def hv_pins(ix, ref):
    """(the pins of `ref` that carry pack voltage, the pins that carry low
    voltage).  A pin on the GROUND PLANE is in neither list -- ground is on
    both sides of the partition by definition, and counting it would make a
    choke with a shield pin "straddle" -- and neither is a pin with no net at
    all, which is how `J101`'s empty positions arrive."""
    it = ix.items[ref]
    hv = ix.hv.get(it.board, ())
    high = sorted(pin for pin, n in it.pin_net.items() if n in hv)
    low = sorted(pin for pin, n in it.pin_net.items()
                 if n and n not in hv and n not in ix.gnd)
    return high, low


def straddler_satellite(ix, board, ref):
    """Is `ref` a low-voltage part that has to sit against a STRADDLER -- a
    brick's own 100 nF?  It belongs on that straddler's low-voltage side, which
    is the one place inside the 84 V end where low voltage has business being,
    and the partition lets it stand there (check 13 still asks that it not be
    walled in).  ⚠️ `U202` is 50.8 mm long and `U201` 58.3, and at 25.4 and
    37.2 mm deep they cannot share u on a 41.84 mm board -- so they stand end
    to end and at most one of them can reach the strip.  The other's decoupler
    has to follow it inward, or there is no decoupler."""
    host = decoupler_hosts(ix, board).get(ref)
    return host is not None and straddles(ix, host)


def straddles(ix, ref):
    """Does `ref` cross POWER's partition?  A part with pack-voltage pins AND
    low-voltage pins is the thing that converts one into the other -- both
    bricks, the key-sense divider's upper leg, the gate network's pull-down --
    and it is placed with its 84 V pins toward the 84 V end (IO-26 4a)."""
    high, low = hv_pins(ix, ref)
    return bool(high and low)


def heavy_path(pl, ix, board):
    """(the brick, the contact that takes the 12 V bus off `board`, the worst
    u-distance from one of the brick's bus pads to one of that contact's), or
    None where the board carries no 12 V output.  The WORST of them, not the
    mean: every one of those pads carries the 8.47 A or senses it."""
    src, away, _ = v12_output(ix, board)
    if src is None or away is None:
        return None
    a, b = pl.get(src), pl.get(away)
    if a is None or b is None or a.unplaced or b.unplaced:
        return None
    frame, pwr12 = pl.frame(board), ix.classes["PWR12"]
    us = [u for num, u, _ in a.pads(frame) if ix.items[src].pin_net.get(num) in pwr12]
    them = [u for num, u, _ in b.pads(frame) if ix.items[away].pin_net.get(num) in pwr12]
    if not us or not them:
        return None
    return src, away, max(abs(x - y) for x in us for y in them)


def bulk_reach(pl, ix, cap, brick):
    """How far `cap` stands from the nearest place it could stand at `brick`'s
    pack-voltage pins: the worst u-distance from one of its pads to the
    nearest of those pins, LESS the brick's own body where that lies between
    them.  The brick's body is board the cap cannot use -- two bodies on one
    face keep `CLEAR`, and a through-hole pad may not come up inside a body on
    the other one (check 17) -- so discounting it is what lets ONE constant
    hold a cap at a brick's pins and a cap that has to stand round a 50.8 mm
    case to reach them."""
    a, b = pl.get(cap), pl.get(brick)
    if a is None or b is None or a.unplaced or b.unplaced:
        return None
    frame = pl.frame(ix.items[cap].board)
    high, _ = hv_pins(ix, brick)
    pins = [u for num, u, _ in b.pads(frame) if num in high]
    if not pins:
        return None
    worst = 0.0
    for _, u, _ in a.pads(frame):
        near = min(pins, key=lambda p: abs(p - u))
        lo, hi = min(u, near), max(u, near)
        blocked = max(0.0, min(hi, b.box.u1) - max(lo, b.box.u0))
        worst = max(worst, (hi - lo) - blocked)
    return worst


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

    def placed(self, board):
        """The items of `board` that HAVE a position.  An UNPLACED part is
        reported by refdes and reason and the write is refused; measuring it
        where the file happened to leave it would report its old coordinates
        as if they were this run's proposal."""
        return {r: p for r, p in self.boards[board].items() if not p.unplaced}

    def face(self, board, layer):
        return [p for p in self.placed(board).values() if p.layer == layer]

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
        self.host_of = decoupler_hosts(self.ix, board)
        self.hv_board = board == "POWER"
        self.extra = {}             # refdes -> [Box] keep-outs that bind it alone
        self.target_u = {}          # refdes -> (u, why) the engine must aim at
        #: refdes -> (u, why): aim the body's FAR EDGE at this u rather than
        #: its centre.  (check 19) The row-blocking brick stands against the
        #: partition, and what has to land there is the end its 12 V output
        #: leaves by -- a centre target would put half its 58.3 mm past the
        #: line and the other half short of it, whichever way it is turned.
        self.target_end = {}
        self.target_v = {}          # refdes -> (box front v, why)
        self.floor_v = {}           # refdes -> (v, why): a FLOOR, not a target
        self._tht_cache = {}        # refdes -> [Box] of its through-hole pads
        #: Which end of this board is the 84 V end (IO-26 4a), set once the
        #: face row is down -- None on every board but POWER.
        self.hv_low = None

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

    def _tht(self, p):
        """`p`'s through-hole pad boxes; a placed part never moves again
        within one `Placer`, so they are computed once."""
        if p.refdes not in self._tht_cache:
            self._tht_cache[p.refdes] = p.tht_boxes(self.frame)
        return self._tht_cache[p.refdes]

    def _obstacles(self, ref, band, layer):
        """([(box, gap u, gap v)] the BODY must clear, [(box, gap u, gap v)]
        each of the part's own HV ZONES must clear, [(box, gap u, gap v)] each
        of its own THROUGH-HOLE PADS must clear).  HV copper and an LV body
        keep the strip on either face; two bodies on one face keep CLEAR, or
        the channel between their bands.

        A through-hole pad crosses the board, so it binds the OTHER face too:
        the pads of a part on the opposite layer are obstacles to this body,
        and this part's own pads are obstacles against every body over there.
        Both at CLEAR -- the pad is copper on that face, and a trace must be
        able to pass between it and whatever stands beside it.  A body over a
        through-hole part's BODY is not an obstacle: only its pads cross."""
        hv = self.is_hv(ref)
        tht = self.env(ref).tht
        body, zones, cross = [], [], []
        for p in self.pl.boards[self.board].values():
            if p.unplaced:
                continue
            if p.layer == layer:
                body.append((p.box, CLEAR, self._channel(band, p.band)))
            else:
                body += [(b, CLEAR, CLEAR) for b in self._tht(p)]
                if tht:
                    cross.append((p.box, CLEAR, CLEAR))
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
        return body, zones, cross

    def satellites_of(self, ref):
        """The parts that must sit against `ref` and are not placed yet -- a
        decoupler, an ADC input's RC, the CAN transceiver."""
        return sorted((r for r in self.doc.components if self.host(r) == ref
                       and r not in self.pl.boards[self.board]), key=_ref_key)

    def _reserve(self, ref, band):
        """`([(w, d), ...], obstacles)` for the satellite that will follow
        `ref`, or None when nothing must sit against it: one plan per quarter
        turn it may take, since any of them fitting is room.  It must clear
        what IT must clear, not what its host must."""
        sats = self.satellites_of(ref)
        if not sats:
            return None
        sat = sats[0]
        layer = self.layer_of(sat)
        shapes = {(round(b.w, 6), round(b.d, 6)) for b in
                  (placed_box(self.env(sat), self.frame, 0.0, 0.0, ang, layer == 2)
                   for ang in (0, 90))}
        obs, _, _ = self._obstacles(sat, self.band.get(sat, band), layer)
        return (sorted(shapes), obs)

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

    def _slot(self, ref, band, angle, target_u, v_front, back_flush=False, near=None,
              reserve=None, v_min=None, require_room=False, touch=None, align_end=False):
        """The cheapest free origin for `ref` at `angle`: nearest `target_u`,
        then nearest `v_front` (ahead of it costs more).  With `near`, a Box,
        the cost is the body's distance from that box instead: a satellite
        sits against its host whichever side is free.  With `reserve`, a
        `(shapes, obstacles)` from `_reserve`, a position with no room beside
        it for the satellite that must follow costs `SATELLITE_ROOM` more --
        or is refused outright with `require_room`.  `v_min` is a FLOOR on the
        body's front, not a preference: a rule that binds where a part stands
        (the S3's antenna end at the back edge, check 8) is not something the
        adjacency may outbid.  `touch`, a list of boxes, requires the body to
        come within `HV_STRIP` of at least one of them -- how the 84 V parts
        are kept ONE group by construction (check 13).  With `align_end` the
        body's FAR EDGE is aimed at `target_u` instead of its centre (check
        19's brick against the partition).  None if it fits nowhere on its
        face."""
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
        body_obs, zone_obs, cross_obs = self._obstacles(ref, band, layer)
        # each HV zone as an offset from the body's corner; the attached zones
        # (antenna, cable ends) likewise, against every placed body
        zone_off = [(z.u0 - off.u0, z.v0 - off.v0, z.u1 - off.u0, z.v1 - off.v0) for z in zones]
        attached = self.attached(ref, angle)
        if attached:
            zone_off += attached
            zone_obs = list(zone_obs) + [(p.box, 0.0, 0.0) for p in self.pl.boards[self.board].values()
                                          if not p.unplaced]
        # (boxes that travel with the body, as offsets from its (u0, v0)
        # corner; what each of them must clear).  The second group is this
        # part's own through-hole pads against the bodies on the other face.
        groups = [(zone_off, zone_obs)] if zone_off and zone_obs else []
        if cross_obs:
            groups.append(([(z.u0 - off.u0, z.v0 - off.v0, z.u1 - off.u0, z.v1 - off.v0)
                            for z in placed_tht_boxes(env, self.frame, 0.0, 0.0, angle, bottom)],
                           cross_obs))
        best = None
        v0 = mv0 if v_min is None else max(mv0, v_min)
        while v0 + b <= W - mv1 + 1e-9:
            forbidden = []
            for box, gu, gv in body_obs:
                if v0 >= box.v1 + gv - 1e-9 or v0 + b <= box.v0 - gv + 1e-9:
                    continue
                forbidden.append((box.u0 - gu - a, box.u1 + gu))
            for offs, obs in groups:
                for zu0, zv0, zu1, zv1 in offs:
                    for box, gu, gv in obs:
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
            want = target_u - (a if align_end else a / 2)
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
                if best is not None and cost >= best[0]:
                    continue        # the room penalty only adds, so this cannot win
                if touch is not None and not any(
                        t.separation(Box(u0, v0, u0 + a, v0 + b)) <= HV_STRIP + 1e-9
                        for t in touch):
                    continue
                if reserve is not None and not _room_beside(Box(u0, v0, u0 + a, v0 + b),
                                                            reserve, L, W):
                    if require_room:
                        continue
                    cost += SATELLITE_ROOM
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
    def row(self):
        """The harness row: ONE strip of the connector edge for BOTH faces, in
        `edge_budget` order.  A harness terminal is through-hole -- its pins
        cross the board and stand proud of the other face -- so a terminal
        hanging under the board takes the same length of the edge as one
        standing on top, and `board_fit.edge_budget` returns one `Edge` per
        board holding both faces' headers.  A header that does not fit the
        strip between the M3 corners is left UNPLACED, and so is every header
        after it: the row is an ordered strip, never squeezed."""
        headers = [r for e in board_fit.edge_budget(self.ix.d) if e.board == self.board
                   for r in e.headers if r in self.doc.components and r not in self.keep]
        if not headers:
            return
        boxes = {}
        for ref in headers:
            env = self.env(ref)
            bottom = self.layer_of(ref) == 2
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
        strip = L - 2 * corner
        anchor = self.anchor
        if self.hv_board and any(self.is_hv(r) for r in headers) and anchor == "centre":
            # (IO-26 4a) POWER is partitioned along its length and `J101` sits
            # at the FACE OF THE HV END, so the pack-voltage row is anchored to
            # one end rather than centred; `--anchor right` puts the 84 V end
            # at the far end instead.
            anchor = "left"
        start = {"left": corner, "right": L - corner - total}.get(anchor, (L - total) / 2)
        start = max(corner, min(start, L - corner - total))
        u = start
        over = False
        for i, ref in enumerate(headers):
            ang, box = boxes[ref]
            if over or u + box.w > L - corner + TOL:
                over = True
                self.keep_one(ref, 1, f"UNPLACED: the row needs {total:.1f} mm of the connector "
                                      f"edge and the strip between the M3 corners is {strip:.1f} mm "
                                      f"-- one strip for both faces, because a terminal's pins "
                                      f"cross the board")
                continue
            reason = (f"face row (layer {self.layer_of(ref)}), position {i + 1} of {len(headers)} "
                      f"in edge_budget order, body v 0-{box.d:.1f}")
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
            fixed = 0 if r in self.target_u or r in self.target_v or r in self.target_end else 1
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
        """Place `ref`, then at once everything that must sit against it.
        ⚠️ A satellite outside `only` waits for its own pass: POWER places its
        84 V parts first and then partitions the board (4a), and a low-voltage
        decoupler dragged along behind an 84 V host would be seated in the 84 V
        end before the partition that forbids it exists."""
        self.place_one(ref, band)
        # a satellite follows its host whatever pass the host is placed in
        for sat in self.satellites_of(ref):
            if only is not None and sat not in only:
                continue
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
        if self.is_hv(ref) and band != 2 and ref not in self.target_v:
            # ⚠️ The bulk's front is the board's own edge, NOT the row's depth.
            # The 84 V bulk is a REGION, not a band: it fills one end of the
            # board to both edges, and the row it stands behind is only 56 mm
            # of the 242.  Charging it for standing in front of the row's depth
            # left the whole strip beside `J101` empty and pushed the region
            # 15 mm further along the board (measured on the owner's
            # footprints, 2026-09-22) -- length the low-voltage end needs.
            # ⚠️ The REGION binds every 84 V part, including one the heavy
            # path aims at a u of its own (check 19): a bulk cap given a
            # target and left in band 3's front stood at v 19 with the strip
            # at the face empty in front of it, which cost the region 20 mm
            # of its length and turned the can's leads away from the brick.
            v_front = 0.0
            if ref not in self.target_u and ref not in self.target_end:
                # the 84 V bulk -- chokes, bricks, cans, the fuse -- packs
                # against the end J101 stands at, straight behind the row, so
                # the HV group is one compact blob and the low-voltage parts
                # have the rest
                hv_row = [p for p in self.pl.face(self.board, 1)
                          if p.band == 1 and self.ix.is_hv(p.refdes)]
                end = 0.0 if not hv_row or hv_row[0].box.cu < self.frame.length / 2 \
                    else self.frame.length
                target, why = end, f"HV bulk, packed toward the {'left' if end == 0 else 'right'} end"
        align_end = ref in self.target_end
        if align_end:
            # (check 19) the row-blocking brick against the partition: the u
            # given is where its BODY ENDS, and the region it stands at the
            # end of is still the board's own edge in v.
            target, why = self.target_end[ref]
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
        v_min = None
        if ref in self.floor_v:
            v_min, why_floor = self.floor_v[ref]
            why = f"{why_floor}; {why}"
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
        if self.hv_low is not None and straddles(self.ix, ref):
            # (IO-26 4a) a part that converts pack voltage into low voltage is
            # turned with its low-voltage pins toward the low-voltage end --
            # which is what fixes both bricks' orientation
            turned = tuple(a for a in angles if self.lv_pins_outward(ref, a))
            if turned:
                angles = turned
                why += "; low-voltage pins toward the low-voltage end (4a)"
        # a host stands where its satellite can follow it (check 14, check 15)
        reserve = self._reserve(ref, band)
        # the 84 V parts are ONE group (check 13): each one lands within
        # HV_STRIP of one already down, so the region is contiguous by
        # construction rather than by luck in the packing order
        touch = None
        if self.hv_board and self.is_hv(ref) and not align_end:
            group = [p.box for p in self.pl.boards[self.board].values()
                     if not p.unplaced and self.ix.is_hv(p.refdes)]
            touch = group or None
        # ⚠️ The brick seated against the partition is the region's OTHER
        # anchor and is exempt: it goes down first, at the far end, and the
        # 84 V parts then pack from the row toward it, each touching the one
        # before.  Requiring IT to touch the group would put it back against
        # `J101`, which is the placement check 19 exists to undo -- and if
        # the pack does not close up to it, check 13 says so.
        best = None
        # Each rule in turn, strongest first: the group, the satellite's room
        # and the floor are dropped only when nothing on the board satisfies
        # them, so the engine never trades one away for a shorter trace while
        # a legal position exists.  What is dropped, the checks then report.
        room = reserve is not None
        ladder = [(v_min, room, touch), (v_min, room, None), (v_min, False, None),
                  (None, False, None)]
        seen = set()
        for floor, require, group in ladder:
            key = (floor, require, group is not None)
            if key in seen:
                continue
            seen.add(key)
            for ang in angles:
                got = self._slot(ref, band, ang, target, v_front, back_flush=back_flush,
                                 near=near, reserve=reserve, v_min=floor,
                                 require_room=require, touch=group, align_end=align_end)
                if got is None:
                    continue
                u, v, cost = got
                cost += 0.5 if ang else 0.0
                cost += self.misalignment(ref, u, v, ang)
                if best is None or cost < best[0]:
                    best = (cost, u, v, ang)
            if best is not None:
                break
        if best is None:
            self.pl.notes.append(f"{self.board}: {ref} fits nowhere on its face; left as saved")
            self.keep_one(ref, band, "UNPLACED: no free slot")
            return
        _, u, v, ang = best
        self.pl.add(self.make(ref, u, v, ang, band, why))

    def lv_pins_outward(self, ref, angle):
        """At `angle`, do this part's low-voltage pins face the low-voltage end
        of POWER?  Measured at each group's CENTROID, so a part whose pins
        interleave is still judged by which way it faces.  True when it has
        only one kind of pin -- the rule is about turning a straddler round,
        not about where a part sits."""
        high, low = hv_pins(self.ix, ref)
        pads = placed_pads(self.env(ref), self.frame, 0.0, 0.0, angle,
                           self.layer_of(ref) == 2)
        hu = [u for num, u, _ in pads if num in high]
        lu = [u for num, u, _ in pads if num in low]
        if not hu or not lu:
            return True
        return (sum(hu) / len(hu) < sum(lu) / len(lu)) if self.hv_low else \
               (sum(hu) / len(hu) > sum(lu) / len(lu))

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

    def keep_one(self, ref, band, reason):
        """Leave `ref` exactly where the file has it, with `reason` -- how an
        UNPLACED part is recorded.  It is reported and refused, never squeezed
        into a place it does not fit."""
        comp = self.doc.components[ref]
        u, v = self.frame.to_board(comp.x / MIL_PER_MM, comp.y / MIL_PER_MM)
        self.pl.add(self.make(ref, u, v, self.frame.board_angle(comp.angle), band, reason))

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


#: The order the boards are placed in, which is NOT the stack order: a board
#: goes after every board whose positions it inherits.  OUTPUTS holds both
#: lower halves of the OUTPUTS↔LOGIC junction and both hanging connectors, so
#: it fixes the most; LOGIC then inherits those two positions and chooses the
#: CTRL-STACK pair's; CTRL inherits that one; POWER inherits the loom's u and
#: the two cross-board keep-outs.  Every board of `STACK_ORDER` is placed --
#: this only says in which order -- and a board missing from here would never
#: be placed at all, so it is derived from the stack and then reordered.
PLACE_ORDER = ("OUTPUTS", "LOGIC", "CTRL", "POWER")


def _place_order():
    """`PLACE_ORDER`, with any board of the stack it does not name appended:
    a fifth board added to `STACK_ORDER` is still placed, after the rest."""
    return tuple(b for b in PLACE_ORDER if b in bp.STACK_ORDER) + \
        tuple(b for b in bp.STACK_ORDER if b not in PLACE_ORDER)


def stack(project, ix, anchor="centre", keep=()):
    """Place every board of the stack, in `PLACE_ORDER`.  Returns the
    `Placement`."""
    pl = Placement(project, ix)
    keep = set(keep)
    for board in _place_order():
        if board not in project.pcbs:
            pl.notes.append(f"{board}: no PCB document in the file")
            continue
        _place_board(pl, board, anchor, keep)
    return pl


def _seat_pairs(pl, pr, board, keep):
    """The mated pairs' halves, before anything else on this board.

    An UPPER half is fixed at its mate's X, Y -- the pair mates straight down
    (check 4) -- and a LOWER half goes flush to the back edge, where a long
    through-hole row cuts an inner plane least (check 12).  ⚠️ Uppers first,
    then lowers: a lower half chooses its own u, and it has to choose one that
    clears the halves this board already inherited.  ⚠️ And the whole group
    before the bands, because what follows is placed AGAINST it -- the CAN
    transceiver stands over the contacts that carry its bus (check 14), and it
    can only look for a connector that is already down.
    """
    ix, W = pl.ix, pr.frame.width
    for lower, upper in ix.pairs:
        if ix.items[upper].board != board or upper not in pr.doc.components or upper in keep:
            continue
        lo = pl.get(lower)
        if lo is None or lo.unplaced:
            continue
        ang = _mate_angle(pl, lower, upper)
        if ang is None:
            ang = lo.angle
            pl.notes.append(f"{board}: {upper} lands pin for pin on {lower} at no quarter "
                            f"turn; placed at {lower}'s angle")
        pr.place_fixed(upper, lo.u, lo.v, ang, 4, f"fixed: mate of {lower}")
    for lower, _ in ix.pairs:
        if ix.items[lower].board != board or lower not in pr.doc.components or lower in keep:
            continue
        box = placed_box(pr.env(lower), pr.frame, 0, 0, 0, pr.layer_of(lower) == 2)
        pr.target_v[lower] = (W - box.d - COURTYARD, "flush to the back edge")
        if lower in pr.pending():
            pr.place_with_satellites(lower, pr.band.get(lower, 4))


def _signal_centroid(pr, ref):
    """Where the parts `ref` SIGNALS to already stand: the mean u over its
    signal nets alone, one vote per pin.  The rails are left out on purpose --
    a driver's 12 V pins would pull every driver onto whichever contact happens
    to be down and say nothing about which terminals that driver serves."""
    num = den = 0.0
    for net in pr.item(ref).nets:
        if not pr.ix.signal(net):
            continue
        for r, pin in pr.ix.members[net]:
            if r == ref:
                continue
            p = pr.pl.boards[pr.board].get(r)
            if p is None or p.unplaced:
                continue
            num += p.pin_point(pr.frame, pin)[0]
            den += 1
    return num / den if den else None


def _reserve_driver_slot(pl, pr, keep):
    """(IO-26 3a) The 12 V loom's contact is seated in the MIDDLE of the driver
    line, before the drivers themselves, so the line closes round it and its
    four pins come up in the slot rather than under a driver.

    The slot is the feed's own pad row plus `DRIVER_SLOT_MARGIN` each side, and
    the drivers keep off it through the ordinary rule that a through-hole pad is
    copper on BOTH faces (check 17): nothing else has to be told about it.  The
    u is the mean of the u's the drivers' own signals ask for -- the middle of
    the terminals they serve -- so the 11.39 A feed enters the layer-3 pour
    where the load is, instead of at one end of the line (check 11)."""
    ix = pr.ix
    ics, feed = v12_bus(ix, pr.board)
    ics = [r for r in ics if r in pr.doc.components]
    if feed is None or feed not in pr.doc.components or feed in keep or len(ics) < 2:
        return
    wants = [u for u in (_signal_centroid(pr, r) for r in ics) if u is not None]
    if not wants:
        return
    u = sum(wants) / len(wants)
    env = pr.env(feed)
    pads = placed_tht_boxes(env, pr.frame, 0.0, 0.0, 0, pr.layer_of(feed) == 2)
    width = (driver_slot(pads)[1] - driver_slot(pads)[0]) if pads else 0.0
    pr.target_u[feed] = (u, f"the middle of the {' '.join(ics)} line (u {u:.1f}): its pin row "
                            f"and {DRIVER_SLOT_MARGIN:g} mm each side, {width:.1f} mm, is the slot "
                            f"the line leaves for it (3a)")
    pr.target_v[feed] = (BAND_FRONT[3], "in the driver line, not behind it")


def _apply_partition(pl, pr, partition):
    """(IO-26 4a) Divide POWER along its length -- 84 V end, `HV_STRIP`,
    low-voltage end -- BEFORE anything of it is placed.

    Every low-voltage part is barred from the 84 V end, and every part that
    carries pack voltage and nothing else from the low-voltage end.  A
    low-voltage part therefore cannot be enclosed by 84 V copper, because it
    is never among it, which is what 4a is for; the only thing that crosses is
    a straddler's body, the part that converts one into the other.

    ⭐ Barring the 84 V parts is also what makes the line STABLE: `far` is what
    a first pass of this board measured (capped by what the low-voltage parts
    need), and because nothing that is 84 V and nothing else may now reach past
    it, `hv_partition` measuring the finished board can only come out the same
    or shorter -- so every low-voltage part barred from `[0, line]` is still
    clear of the line the checks derive.

    The one part exempt from the low-voltage bar is a straddler's own
    satellite: a brick's 100 nF belongs against the brick's low-voltage pads
    (`straddler_satellite`), and check 13 still asks that it not be walled
    in."""
    low, far, line = partition
    fr = pr.frame
    pr.hv_low = low
    lv_end = (Box(far, -1.0, fr.length + 1.0, fr.width + 1.0) if low
              else Box(-1.0, -1.0, far, fr.width + 1.0))
    bar = (Box(-1.0, -1.0, line, fr.width + 1.0) if low
           else Box(line, -1.0, fr.length + 1.0, fr.width + 1.0))
    for ref in pr.doc.components:
        if ref in pr.keep:
            continue
        if pr.is_hv(ref):
            if not straddles(pr.ix, ref):
                pr.extra.setdefault(ref, []).append(lv_end)
        elif not straddler_satellite(pr.ix, pr.board, ref):
            pr.extra.setdefault(ref, []).append(bar)
    pl.notes.append(f"{pr.board}: the 84 V end runs to u {far:.1f} and the low-voltage end starts "
                    f"at u {line:.1f}, a {HV_STRIP:g} mm strip apart (4a)")


def _seat_heavy_path(pl, pr, only):
    """(check 19, the 84 V half) The converters, then each one's input bulk
    cap aimed at its pack-voltage pins -- before the rest of the 84 V region.

    ⚠️ THE BRICKS BEFORE THE CAPS, and not only because they are the biggest
    bodies: a cap's target is READ OFF its brick's placed pads, so the brick
    has to be down before there is a target to give.  The blocker among them
    carries `target_end` and lands against the partition; the other takes the
    ordinary bulk rule and ends up under the face row's back.

    The cap is given a `target_u` and not a place against the body, because
    what it has to be near is the PINS: `U201` offers its own, while `U202`
    puts 50.8 mm of case between its input pins and the nearest board a
    through-hole can may stand on, and a u-target lets the packer take the
    first legal position on that line instead of hugging a corner of the case
    and standing across the width the input path needs."""
    ix = pr.ix
    bricks = [it.refdes for it in ix.on(pr.board) if it.kind == "CONVERTER"
              and it.refdes in only and it.refdes in pr.pending()]
    bricks.sort(key=lambda r: (0 if r in pr.target_end else 1,
                               -ix.items[r].body[0] * ix.items[r].body[1], _ref_key(r)))
    for ref in bricks:
        pr.place_with_satellites(ref, pr.band.get(ref, 3), only=only)
    for cap, brick in sorted(bulk_caps(ix, pr.board).items()):
        p = pl.get(brick)
        if cap not in only or cap in pr.keep or p is None or p.unplaced:
            continue
        high, _ = hv_pins(ix, brick)
        us = [u for num, u, _ in p.pads(pr.frame) if num in high]
        if us:
            pr.target_u[cap] = (sum(us) / len(us),
                                f"at {brick}'s {' '.join(high)} pads (u {sum(us) / len(us):.1f}): "
                                f"a brick's input bulk stands at its pack-voltage pins (check 19)")


def _seat_v12_output(pl, pr, partition, keep):
    """(check 19, the low-voltage half) The 12 V output's own parts are the
    low-voltage end's FIRST tenants, seated at the strip in that order, so the
    brick's `+V`/`-V` pins -> the bulk cap -> the contact that takes 8.47 A
    off the board is one short run instead of the length of the 84 V end.

    ⚠️ This OVERRIDES the loom's own target for that contact.  The loom wants
    its two halves near each other so the cable runs straight (`J202` under
    `J311`), but the cable is five flying conductors in a 30 mm gap and can
    run at an angle; the 8.47 A pour on the board cannot, and `J202` is barred
    from the 84 V end anyway.  The pour wins, and says so in the table."""
    line = partition[2]
    _, _, parts = v12_output(pr.ix, pr.board)
    for ref in parts:
        if ref not in pr.doc.components or ref in keep:
            continue
        pr.target_u[ref] = (line, f"at the strip (u {line:.1f}), a first tenant of the "
                                  f"low-voltage end: the 12 V output's own parts stand at the "
                                  f"brick's output end (check 19)")
        if ref in pr.pending():
            pr.place_with_satellites(ref, pr.band.get(ref, 4))


def _blocker_slack(pl, pr, blocker, partition):
    """How far the row-blocking brick stands off the region it closes: the gap
    between the group it is in and the nearest other 84 V group, less the
    `CLEAR` it keeps from it.  0 while the region is ONE group, which is the
    state check 13 asks for.

    ⚠️ Measured between GROUPS, with the same adjacency check 13 uses, not
    between the brick and the far edge of everything else: the brick's own
    input bulk cap stands at its pins and is therefore the far edge of
    "everything else", which would read every hole as zero."""
    if blocker is None:
        return 0.0
    b = pl.get(blocker)
    if b is None or b.unplaced:
        return 0.0
    hv = [p for p in pl.placed(pr.board).values() if pr.ix.is_hv(p.refdes)]
    groups = hv_groups(hv)
    mine = next((g for g in groups if blocker in g), None)
    if mine is None or len(groups) < 2:
        return 0.0
    here = [p for p in hv if p.refdes in mine]
    gap = min(p.box.separation(q.box) for p in here for q in hv if q.refdes not in mine)
    return gap - CLEAR


#: How many times the 84 V end may be re-measured: GROWN when it cannot seat
#: its own parts, or pulled IN when they pack short of it.  Every millimetre
#: it takes is one the low-voltage end does not have, so the revision moves in
#: small steps -- the shelf pack of what it could not seat, or the slack the
#: brick was left standing in -- and stops: a board that still cannot place
#: everything after three is a board to look at, not one to keep stretching.
#: One counter for both directions, so a board cannot be walked back and forth
#: between them.
PARTITION_GROWTHS = 3


def _place_board(pl, board, anchor, keep, relaxed=False, partition=None, grown=0):
    ix = pl.ix
    W = pl.frame(board).width
    if True:
        pr = Placer(pl, board, anchor, keep, relaxed=relaxed)
        if pr.hv_board:
            pr.hv_low = anchor != "right"
        pr.keep_saved()
        pr.row()
        _seat_pairs(pl, pr, board, keep)
        if board == "OUTPUTS":
            _reserve_driver_slot(pl, pr, keep)
        if board == "LOGIC":
            if "U401" in pr.doc.components and "U401" not in keep:
                box = placed_box(pr.env("U401"), pr.frame, 0, 0, 0, False)
                pr.target_v["U401"] = (W - ANTENNA_EDGE / 2 - box.d,
                                       "antenna end (local +Y, the padless end) at the back edge")
                # check 8 is a RULE, not a preference: the module may only be
                # offered positions that keep its antenna end at the back edge,
                # so a 56 mm socket on the same edge is something it stands
                # BESIDE rather than something that outbids it.
                pr.floor_v["U401"] = (W - ANTENNA_EDGE - box.d,
                                      "the antenna end within "
                                      f"{ANTENNA_EDGE:g} mm of the back edge")
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
                # the CAN transceiver over the pair contacts that carry its bus
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
            # the loom's two halves near each other, so it runs straight, and
            # nothing tall under what hangs into the gap.  Both lists are the
            # netlist's: the CTRL ribbon's `J105`/`J312` were the second pair
            # of each until IO-27 deleted it.
            hanging = sorted((it.refdes for it in ix.on("OUTPUTS", "bottom") if it.kind == "CONN"),
                             key=_ref_key)
            for upper in hanging:
                lower = next((it.refdes for it in ix.on(board)
                              if it.interface and it.interface == ix.items[upper].interface), None)
                up = pl.get(upper)
                if lower and up is not None and lower in pr.doc.components:
                    pr.target_u[lower] = (up.box.cu, f"under {upper}'s loom (u {up.box.cu:.1f})")
            gap = ix.gaps[("POWER", "OUTPUTS")].gap_mm
            for hang in hanging:
                up = pl.get(hang)
                if up is None:
                    continue
                limit = gap - ix.items[hang].height - bp.CLEARANCE
                for it in ix.on("POWER", "top"):
                    if it.height > limit:
                        pr.extra.setdefault(it.refdes, []).append(up.box.grow(COURTYARD))
            # the 84 V parts go down first, as one group behind J101, so the
            # low-voltage parts then keep the strip from copper that exists
            hv_refs = {r for r in pr.doc.components if pr.is_hv(r)}
            # (check 19) The row-blocking brick stands against the partition,
            # so the 84 V end is measured WITHOUT it and its own length added:
            # what decides the line is where the rest of the 84 V parts pack
            # to, and the brick then fills the end of the region with its 12 V
            # pins at the strip.  Measured on a pass that has it in the middle,
            # the line lands wherever the packing order happened to leave it.
            blocker = row_blocking_brick(ix, board)
            if blocker not in pr.doc.components or blocker in keep:
                blocker = None
            measuring = partition is None and blocker is not None
            first = hv_refs - {blocker} if measuring else hv_refs
            if partition is not None:
                _apply_partition(pl, pr, partition)
                if blocker is not None:
                    pr.target_end[blocker] = (
                        partition[1], f"seated against the partition at u {partition[1]:.1f}, its "
                                      f"12 V end at the low-voltage end: the row-blocking brick is "
                                      f"the last body in the 84 V end (check 19)")
            # the bricks are the biggest bodies on the board and go down first
            # of all, before the bands: placed after the bulk, a through-hole
            # part 58.3 x 37.2 mm has nowhere on the far face to bring its pins
            # up that is not inside a body.  Their input bulk caps follow them
            # at once, because what those caps aim at is read off the placed
            # brick's own pads (check 19).
            _seat_heavy_path(pl, pr, first)
            for band in (3, 4, 2):           # the bulk first, its passives into the gaps
                pr.place_band(band, only=first)
            if partition is None:
                # ⭐ THE FIRST PASS MEASURES THE PARTITION (IO-26 4a).  Where
                # the 84 V end ends is the 84 V parts' own lengths, and the
                # only honest way to have that number before placing is to
                # place them once and read it off.  The board is then thrown
                # away and placed again with the line known -- the same
                # revision the HV strip already does below.
                part = hv_partition(pl, ix, board)
                if part is not None:
                    low, far, _ = part
                    L, W = pl.frame(board).length, pl.frame(board).width
                    if blocker is not None:
                        # ...plus the brick that was held out of the measure:
                        # it stands beyond everything else, one `CLEAR` gap on
                        # from the pack, and the 84 V end reaches its far edge.
                        span = CLEAR + placed_box(pr.env(blocker), pr.frame, 0, 0, 0,
                                                  pr.layer_of(blocker) == 2).w
                        far = far + span if low else far - span
                    # ...and it may not take more than it leaves: the
                    # low-voltage end has to be at least as long as the
                    # low-voltage parts' own shelf pack, or they are the ones
                    # with nowhere to go.  Whichever of the two is shorter.
                    room = lv_end_needs(ix, board, W) + HV_STRIP
                    cap = L - room if low else room
                    far = min(far, cap) if low else max(far, cap)
                    part = (low, far, far + HV_STRIP if low else far - HV_STRIP)
                    pl.boards[board] = {}
                    pl.notes = [n for n in pl.notes if not n.startswith(f"{board}:")]
                    return _place_board(pl, board, anchor, keep, relaxed, partition=part)
            else:
                # ⭐ A REVISION, and the MIRROR of the growth below: the 84 V
                # end was measured on a pass with the brick held out, and the
                # region has packed SHORTER than the end that measure reserved
                # -- so the brick stands away from its own bulk, with a hole
                # where the 84 V group should be continuous (check 13) and a
                # gap the low-voltage end could have had (check 19's whole
                # point).  Pull the line in by the slack and place again.
                slack = _blocker_slack(pl, pr, blocker, partition)
                if slack > TOL and grown < PARTITION_GROWTHS:
                    low, far, _ = partition
                    far = far - slack if low else far + slack
                    pl.boards[board] = {}
                    pl.notes = [n for n in pl.notes if not n.startswith(f"{board}:")]
                    pl.notes.append(
                        f"{board}: the 84 V parts packed {slack:.1f} mm short of the end measured "
                        f"for them, leaving {blocker} standing off its own bulk; the line is pulled "
                        f"in to u {far:.1f} and the board placed again")
                    return _place_board(pl, board, anchor, keep, relaxed,
                                        (low, far, far + HV_STRIP if low else far - HV_STRIP),
                                        grown + 1)
                _seat_v12_output(pl, pr, partition, keep)
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
        left = [p for p in pl.boards[board].values() if p.unplaced]
        stuck = [p for p in left if ix.is_hv(p.refdes)]
        if stuck and partition is not None and grown < PARTITION_GROWTHS:
            # a revision: the 84 V end was measured on a pass with no partition
            # in it, and holding the low-voltage parts out has cost the 84 V
            # parts room they used to borrow.  Grow it by the length those
            # parts need -- their own shelf pack, the measure `board_fit`
            # budgets a face with -- and place the board again.
            low, far, _ = partition
            need, _ = board_fit.shelf_pack(
                [(p.refdes, *ix.items[p.refdes].body) for p in stuck], pl.frame(board).width)
            if need:
                far = far + need if low else far - need
                line = far + HV_STRIP if low else far - HV_STRIP
                pl.notes = [n for n in pl.notes if not n.startswith(f"{board}:")]
                pl.notes.append(
                    f"{board}: {' '.join(sorted((p.refdes for p in stuck), key=_ref_key))} found no "
                    f"room in an 84 V end measured on a pass with no partition in it; the end is "
                    f"grown by the {need:.1f} mm those parts pack into, to u {far:.1f}")
                pl.boards[board] = {}
                return _place_board(pl, board, anchor, keep, relaxed, (low, far, line), grown + 1)
        if left and not pr.relaxed:
            # a revision: the same board again with the HV strip at the check's
            # floor, so the parts the strip crowded out have room
            pl.notes = [n for n in pl.notes if not n.startswith(f"{board}:")]
            pl.notes.append(f"{board}: {' '.join(sorted((p.refdes for p in left), key=_ref_key))} "
                            f"found no room at the {HV_STRIP:g} mm HV strip; re-placed with the "
                            f"strip at the check's {HV_CLEARANCE:g} mm floor")
            pl.boards[board] = {}
            return _place_board(pl, board, anchor, keep, True, partition, grown)
    return pl


# --- the checks -------------------------------------------------------------------
def check(pl, ix=None, boards=None):
    """Every problem with `pl`, as readable lines.  Empty means the placement
    may be written.  Each check is proven to fire in tests/test_place.py.

    `boards` narrows it to the boards being written (`--board`): a check that
    names parts on one board only is skipped for the others, and a check that
    spans two -- the mated pairs, the cross-board keep-outs -- is kept when
    either end is selected."""
    ix = ix or pl.ix
    out = []
    for board in bp.STACK_ORDER:
        if board not in pl.project.pcbs or (boards is not None and board not in boards):
            continue
        frame = pl.frame(board)
        items = pl.placed(board)
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
        # 6 -- the face row: at the face, in order, inside the ends.  ONE strip
        # per board for both faces (edge_budget): a terminal is through-hole,
        # so one under the board takes the edge like one on top.
        for edge in [e for e in board_fit.edge_budget(ix.d) if e.board == board]:
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
    out += _check_cross_board(pl, ix, boards)
    out += _check_pairs(pl, ix, boards)
    out += _check_keepouts(pl, ix, boards)
    out += _check_hv(pl, ix, boards)
    out += _check_antenna(pl, ix, boards)
    out += _check_bus(pl, ix, boards)
    out += _check_partition(pl, ix, boards)
    out += _check_heavy_path(pl, ix, boards)
    out += _check_sensitive(pl, ix, boards)
    return out


def _check_cross_board(pl, ix, boards=None):
    """17 -- a through-hole part crosses the board.  Its pads are copper on
    BOTH faces and its pin tips and solder fillets stand proud of the far one,
    so no body on the other layer may come within `PIN_PROTRUSION` of one.

    Only the PADS cross: an SMD part over a through-hole part's BODY on the
    other side is legal, which is how a 0603 sits over the brick's case, and
    two SMD parts on opposite faces may overlap freely.  Two through-hole
    parts on opposite faces may never overlap in plan at all -- each one's
    pads are inside the other's body, so both directions fire.  Pad against
    pad needs no separate test: a body's box contains its own pads."""
    out = []
    for board in bp.STACK_ORDER:
        if board not in pl.project.pcbs or (boards is not None and board not in boards):
            continue
        frame = pl.frame(board)
        items = sorted((p for p in pl.boards[board].values() if not p.unplaced),
                       key=lambda p: _ref_key(p.refdes))
        pads = {p.refdes: (p.tht_boxes(frame) if p.tht else []) for p in items}
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if a.layer == b.layer or not (pads[a.refdes] or pads[b.refdes]):
                    continue
                gu, gv = a.box.gaps(b.box)
                if max(gu, gv) >= PIN_PROTRUSION - TOL:
                    continue            # the bodies are apart, so the pads are too
                ga = _pad_gap(pads[a.refdes], b.box)
                gb = _pad_gap(pads[b.refdes], a.box)
                hit = [g for g in (ga, gb) if g is not None and g < PIN_PROTRUSION - TOL]
                if not hit:
                    continue
                if len(hit) == 2:
                    out.append(f"17 through-hole: {board} {a.refdes} (layer {a.layer}) and "
                               f"{b.refdes} (layer {b.layer}) are both through-hole and overlap "
                               f"in plan; each one's pins land inside the other's body")
                    continue
                pin, host, gap = ((a, b, ga) if ga is not None and ga < PIN_PROTRUSION - TOL
                                  else (b, a, gb))
                out.append(f"17 through-hole: {board} {pin.refdes}'s pins (layer {pin.layer}, "
                           f"through-hole) are {max(gap, 0):.2f} mm from {host.refdes}'s body "
                           f"(layer {host.layer}) on the other face; a pin tip and its solder "
                           f"fillet need {PIN_PROTRUSION:g} mm there")
    return out


def _pad_gap(boxes, body):
    """The smallest gap between any of `boxes` and `body` -- negative where
    they overlap, None with no boxes at all."""
    gaps = [max(*b.gaps(body)) for b in boxes]
    return min(gaps) if gaps else None


def _check_pairs(pl, ix, boards=None):
    """4 -- the mated pairs coincide, in X, Y and pin for pin by net.  A
    pair spans two boards, so it is checked when EITHER end is selected.
    The list is `ix.pairs`, derived from the gap each pair sets."""
    out = []
    for lower, upper in ix.pairs:
        lo, up = pl.get(lower), pl.get(upper)
        if lo is None or up is None or lo.unplaced or up.unplaced:
            continue
        if boards is not None and not {lo.board, up.board} & set(boards):
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


def _check_keepouts(pl, ix, boards=None):
    """5 -- nothing tall on POWER's top under what hangs beneath OUTPUTS as
    placed there.  It names POWER's parts, so it is POWER's check.  `J312`
    was the second one until IO-27 deleted the CTRL ribbon; the list is read
    from the netlist's own `side` so a third would be found."""
    out = []
    gap = ix.gaps.get(("POWER", "OUTPUTS"))
    if gap is None or "POWER" not in pl.boards or (boards is not None
                                                   and "POWER" not in boards):
        return out
    for hang in sorted((it.refdes for it in ix.on("OUTPUTS", "bottom") if it.kind == "CONN"),
                       key=_ref_key):
        up = pl.get(hang)
        if up is None or up.unplaced:
            continue
        limit = gap.gap_mm - ix.items[hang].height - bp.CLEARANCE
        for p in pl.face("POWER", 1):
            if p.box.overlaps(up.box) and p.height > limit + TOL:
                out.append(f"5 keep-out: POWER {p.refdes} ({p.height:.1f} mm) stands under {hang}, "
                           f"which hangs {ix.items[hang].height:.1f} mm into the {gap.gap_mm:.1f} mm "
                           f"gap; the limit there is {limit:.1f} mm")
    return out


def _check_hv(pl, ix, boards=None):
    """7 -- HV copper off the edge and clear of LV courtyards; 13 -- the HV
    parts are one group and no LV part is sandwiched between HV copper."""
    out = []
    board = "POWER"
    if not pl.boards.get(board) or (boards is not None and board not in boards):
        return out
    frame = pl.frame(board)
    hv = [p for p in pl.placed(board).values() if ix.is_hv(p.refdes)]
    lv = [p for p in pl.placed(board).values() if not ix.is_hv(p.refdes)]
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
    groups = hv_groups(hv)
    if len(groups) > 1:
        out.append(f"13 HV region: POWER's 84 V parts form {len(groups)} groups, not one: "
                   + " | ".join(" ".join(sorted(g, key=_ref_key)) for g in groups)
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


def hv_groups(hv):
    """The 84 V parts of `hv` (placed items) as groups, each part within
    `HV_STRIP` of another in its own: one group is what check 13 asks for, and
    the same grouping is what tells the engine's revision how far the
    row-blocking brick is standing off its own region (`_blocker_slack`).
    Written once so the check and the revision cannot disagree about what a
    region is."""
    if not hv:
        return []
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
    out = {}
    for p in hv:
        out.setdefault(root(p.refdes), []).append(p.refdes)
    return [sorted(g, key=_ref_key) for g in out.values()]


def _check_antenna(pl, ix, boards=None):
    """8 -- the S3's antenna end at the back edge, the zone beyond it empty."""
    out = []
    p = pl.get("U401")
    if p is None or (boards is not None and p.board not in boards):
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
    for q in pl.placed(p.board).values():
        if q is not p and q.box.overlaps(zone):
            out.append(f"8 antenna: {p.board} {q.refdes} stands in the {ANTENNA_ZONE_W:g} x "
                       f"{ANTENNA_ZONE_D:g} mm zone beyond U401's antenna end")
    return out


def _check_bus(pl, ix, boards=None):
    """11 -- the V12 bus on OUTPUTS: its ICs one way, the loom's contact under
    their middle, and (IO-26 3a) the feed INSIDE the line rather than off its
    end -- a driver each side of the slot its pin row stands in."""
    out = []
    board = "OUTPUTS"
    if not pl.boards.get(board) or (boards is not None and board not in boards):
        return out
    items = pl.placed(board)
    names, feed_ref = v12_bus(ix, board)
    ics = [items[r] for r in names if r in items]
    feed = items.get(feed_ref)
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
    pads = feed.tht_boxes(pl.frame(board))
    if pads and len(ics) > 1:
        s0, s1 = driver_slot(pads)
        before = [p.refdes for p in ics if p.box.u1 <= s0 + TOL]
        after = [p.refdes for p in ics if p.box.u0 >= s1 - TOL]
        if not (before and after):
            out.append(f"11 V12 bus: OUTPUTS {feed.refdes}'s pin row stands at u {s0:.1f}..{s1:.1f} "
                       f"with {' '.join(sorted(before + after)) or 'no driver'} beside it, all on "
                       f"{'one side' if before or after else 'neither side'}; the line leaves a "
                       f"{s1 - s0:.1f} mm slot for those pins and the feed enters the pour from "
                       f"INSIDE it, not off the end (3a)")
    return out


def _check_partition(pl, ix, boards=None):
    """18 -- POWER's HV/LV partition (IO-26 4a): the board is 84 V end,
    `HV_STRIP`, low-voltage end along its length.  No low-voltage part stands
    in the 84 V end, and a part that straddles is turned with its low-voltage
    pins toward the low-voltage end -- which is what fixes both bricks'
    orientation.  ⚠️ Check 13 is still the backstop and says something else:
    18 is about the CONSTRUCTION, 13 about whether any part ended up walled in
    by pack voltage whatever the construction believed."""
    out = []
    board = "POWER"
    if not pl.boards.get(board) or (boards is not None and board not in boards):
        return out
    part = hv_partition(pl, ix, board)
    if part is None:
        return out
    low, far, line = part
    frame = pl.frame(board)
    end = "low-u" if low else "high-u"
    for q in sorted(pl.placed(board).values(), key=lambda p: _ref_key(p.refdes)):
        if ix.is_hv(q.refdes) or straddler_satellite(ix, board, q.refdes):
            continue
        near = q.box.u0 if low else q.box.u1
        if (near < line - TOL) if low else (near > line + TOL):
            out.append(f"18 partition: POWER {q.refdes} (low voltage) reaches u {near:.1f}, inside "
                       f"the 84 V end: that end is the {end} end and runs to u {far:.1f}, and the "
                       f"low-voltage end starts at u {line:.1f} across a {HV_STRIP:g} mm strip")
    for p in sorted(pl.placed(board).values(), key=lambda q: _ref_key(q.refdes)):
        if not straddles(ix, p.refdes):
            continue
        high, lows = hv_pins(ix, p.refdes)
        pads = p.pads(frame)
        hu = [u for num, u, _ in pads if num in high]
        lu = [u for num, u, _ in pads if num in lows]
        if not hu or not lu:
            continue
        hm, lm = sum(hu) / len(hu), sum(lu) / len(lu)
        if (lm < hm) if low else (lm > hm):
            out.append(f"18 partition: POWER {p.refdes} is turned with its low-voltage pins "
                       f"({' '.join(lows)}, centred on u {lm:.1f}) toward the 84 V end and its "
                       f"pack-voltage pins ({' '.join(high)}, u {hm:.1f}) toward the low-voltage "
                       f"end; a straddling part faces the other way")
    return out


def _check_heavy_path(pl, ix, boards=None):
    """19 -- THE HEAVY PATH on POWER: the order the 84 V end is built in,
    measured on the copper that carries the current.

    The partition (check 18) says which end of the board a part belongs in and
    says nothing about where in it; two placements that both pass it can put
    the brick's 12 V output 104 mm from the connector the 8.47 A leaves by or
    10 mm from it.  This is the one that asks:

    (a) the brick's `V12` output pad to that contact, within `HEAVY_PATH_MM`
        of u.  It is where the ORDER shows up: the row-blocking brick stands
        against the partition with its output end at the strip, and the 12 V
        output's own parts are the low-voltage end's first tenants, so the run
        is the strip, the bulk cap and a gap.  A brick packed against `J101`
        instead runs the pour past the chokes, the fuse clip and both bulk
        cans, and no other check notices.
    (b) each brick's INPUT bulk cap within `BULK_REACH` of its pack-voltage
        pins, the brick's own body discounted (`bulk_reach`): the cap IS the
        brick's input source impedance.  Which cap belongs to which brick
        comes from the nets (`bulk_caps`), never from a name."""
    out = []
    board = "POWER"
    if not pl.boards.get(board) or (boards is not None and board not in boards):
        return out
    got = heavy_path(pl, ix, board)
    if got is not None:
        src, away, mm = got
        if mm > HEAVY_PATH_MM + TOL:
            out.append(f"19 heavy path: POWER {src}'s 12 V output pins stand {mm:.1f} mm of u from "
                       f"{away}'s contact, over {HEAVY_PATH_MM:g}: {src} seats against the "
                       f"partition and {away} is a first tenant of the low-voltage end, so the "
                       f"8.47 A crosses the strip and nothing else")
    for cap, brick in sorted(bulk_caps(ix, board).items()):
        reach = bulk_reach(pl, ix, cap, brick)
        if reach is not None and reach > BULK_REACH + TOL:
            high, _ = hv_pins(ix, brick)
            out.append(f"19 bulk: POWER {cap} stands {reach:.1f} mm of u from {brick}'s "
                       f"{' '.join(high)} pads with {brick}'s own body discounted, over "
                       f"{BULK_REACH:g}; a brick's input bulk belongs at its pack-voltage pins")
    return out


def _check_sensitive(pl, ix, boards=None):
    """14 -- CAN transceiver by its STACK contacts; the brake nets' corridor
    clear of the I2C pull-ups; an ADC input's RC beside the S3."""
    out = []
    board = "LOGIC"
    if not pl.boards.get(board) or (boards is not None and board not in boards):
        return out
    items = pl.placed(board)
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


def apply(project, pl, boards=None):
    """Edit the COMPONENT records (and their labels, which follow the part) to
    `pl`.  Returns {board: {refdes: (x mil, y mil, angle, layer)}}.

    `boards` restricts it to the boards being written (`--board`): every
    record of a board left out is untouched, so it serialises back exactly
    as it was saved."""
    written = {}
    for board, items in pl.boards.items():
        doc = project.pcbs.get(board)
        if doc is None or (boards is not None and board not in boards):
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


def write(project, pl, src, out, boards=None):
    """Write `project` (already `apply`d) to `out` through the build's round
    trip, keeping the previous `out` as `.prev`.  Refuses while the editor is
    open, and refuses to leave a file whose re-read differs from what was
    meant.  `boards` is the same selection `apply` was given -- a board left
    out was not edited, so its coordinates are not what `pl` proposes and are
    not what is verified.  Returns the written path."""
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
        if boards is not None and board not in boards:
            continue
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
        if p.unplaced:
            # no position to give: where the file happens to hold it is not a
            # proposal, and a reader must not copy it as one
            lines.append(f"| {ref} | — | — | — | — | — | {p.layer} | {p.band} | {p.reason} |")
            continue
        x, y = frame.to_file(p.u, p.v)
        lines.append(f"| {ref} | {p.u:.2f} | {p.v:.2f} | {p.angle} | {x:.2f} | {y:.2f} | {p.layer} | "
                     f"{p.band} | {p.reason} |")
    return "\n".join(lines) + "\n"


def summary(pl):
    lines = []
    for board in _place_order():
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


# --- the picture --------------------------------------------------------------------
#: Pixels per mm.  At 8 a 0603 (1.6 x 0.8 mm) is 13 x 6 px -- a box you can
#: see -- and a 242 mm board is 1936 px, which fits on a screen.
DRAW_SCALE = 8
#: White margin round the outline, px: room for the title line above the board
#: and for the label of a part sitting at the very edge.
DRAW_MARGIN = 60
#: A pad dot's radius, mm.  Half of the 0.7 mm that is the smallest pad on the
#: boards, so two pads of one part never merge into one blob.
DRAW_PAD_R = 0.35
#: A through-hole pad is drawn as a RING: the hole is what makes it cross the
#: board, and a ring is the one mark that reads at a glance as "this pin comes
#: out the other side".  Ring, not colour: colour already says the net.
DRAW_HOLE_R = 0.55
#: Body colours, and what each one says.
DRAW_TOP = (0, 0, 0)            # layer 1: on top of the board
DRAW_BOTTOM = (60, 60, 200)     # layer 2: under it
DRAW_HV = (200, 0, 0)           # pack voltage anywhere on the part
DRAW_UNPLACED = (230, 120, 0)   # no room for it: it is where the file had it


def draw(pl, ix, out_dir, prefix="placement"):
    """One PNG per board of the placement `pl` holds, board frame, face (v = 0)
    at the bottom: the outline and the M3 washer squares, a line at each band's
    front, every body as a box (top black, bottom blue, pack voltage red, an
    UNPLACED part orange), every pad as a dot (GND green, HV red) with a ring
    where it is through-hole, and every refdes labelled.

    ⚠️ This is a STEP OF THE PROCESS, not a decoration: the picture is what
    showed the first placement's two faces standing inside each other while all
    16 checks said `0 problem(s)`.  Returns the paths written, in board order.
    """
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
        fr = pl.frame(board)
        items = pl.boards[board]
        W = int(fr.length * DRAW_SCALE) + 2 * DRAW_MARGIN
        H = int(fr.width * DRAW_SCALE) + 2 * DRAW_MARGIN
        im = Image.new("RGB", (W, H), "white")
        dr = ImageDraw.Draw(im)

        def P(u, v):                            # board mm -> px, v upward
            return (DRAW_MARGIN + u * DRAW_SCALE, H - DRAW_MARGIN - v * DRAW_SCALE)

        def R(a, b):                            # a rectangle from two board points
            (x0, y0), (x1, y1) = P(*a), P(*b)
            return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]

        dr.rectangle(R((0, 0), (fr.length, fr.width)), outline="black", width=3)
        row_depth = max((p.box.v1 for p in items.values() if p.band == 1 and not p.unplaced),
                        default=0.0)
        fronts = [(2, row_depth + CHANNEL)] + sorted(BAND_FRONT.items())
        for band, v in fronts:
            if 0 < v < fr.width:
                dr.line([P(0, v), P(fr.length, v)], fill=(200, 200, 200), width=1)
                dr.text((P(0, v)[0] + 2, P(0, v)[1] - 11), f"band {band}", fill=(170, 170, 170),
                        font=font)
        for u, v in fr.holes:
            dr.ellipse(R((u - 1.6, v - 1.6), (u + 1.6, v + 1.6)), outline="gray", width=2)
            dr.rectangle(R((u - M3_KEEPOUT, v - M3_KEEPOUT), (u + M3_KEEPOUT, v + M3_KEEPOUT)),
                         outline=(230, 200, 200))
        hv = ix.hv.get(board, ())
        n_bottom = 0
        for ref in sorted(items, key=_ref_key):
            p = items[ref]
            b = p.box
            colour = DRAW_BOTTOM if p.bottom else DRAW_TOP
            if ix.is_hv(ref):
                colour = DRAW_HV
            if p.unplaced:
                colour = DRAW_UNPLACED
            n_bottom += 1 if p.bottom else 0
            dr.rectangle(R((b.u0, b.v0), (b.u1, b.v1)), outline=colour, width=1 if p.bottom else 2)
            for (num, pu, pv), pad in zip(p.pads(fr), p.env.pads):
                net = ix.items[ref].pin_net.get(num) if ref in ix.items else None
                fill = (220, 0, 0) if net in hv else ((0, 140, 0) if net in ix.gnd else (90, 90, 90))
                dr.ellipse(R((pu - DRAW_PAD_R, pv - DRAW_PAD_R), (pu + DRAW_PAD_R, pv + DRAW_PAD_R)),
                           fill=fill)
                if pad[5]:                      # through-hole: it comes out the other side
                    dr.ellipse(R((pu - DRAW_HOLE_R, pv - DRAW_HOLE_R),
                                 (pu + DRAW_HOLE_R, pv + DRAW_HOLE_R)), outline=fill)
            cx, cy = P(b.cu, b.cv)
            dr.text((cx - dr.textlength(ref, font=font) / 2, cy - 5), ref, fill=colour, font=font)
        unplaced = sorted((r for r, p in items.items() if p.unplaced), key=_ref_key)
        dr.text((DRAW_MARGIN, 10),
                f"{board}  {fr.length:.2f} x {fr.width:.2f} mm  face at the bottom (v = 0)  "
                f"{len(items)} parts, {n_bottom} under the board (blue), pack voltage red, "
                f"GND pads green, a ring = a pin through the board", fill="black", font=font)
        dr.text((DRAW_MARGIN, 26),
                (f"UNPLACED (orange, drawn where the file had them): {' '.join(unplaced)}"
                 if unplaced else "every part placed"),
                fill=DRAW_UNPLACED if unplaced else (120, 120, 120), font=font)
        path = out_dir / f"{prefix}-{board}.png"
        im.save(path)
        written.append(path)
    return written


# --- command line -----------------------------------------------------------------
def default_file():
    return Path(build_project.EDITOR_PROJECTS) / PROJECT_FILE


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--stack", action="store_true", help="place every board, check, write")
    mode.add_argument("--check", action="store_true", help="report on the saved file; never writes")
    ap.add_argument("--draw", default=None, metavar="DIR",
                    help="draw one PNG per board into DIR -- the placement proposed by --stack, "
                         "or the one the file holds; on its own it draws the file. LOOK AT IT: "
                         "the picture is a step of the process, not a decoration")
    ap.add_argument("--board", nargs="+", default=None, metavar="BOARD", choices=bp.STACK_ORDER,
                    help="write ONLY these boards' PCB documents; every other board's records are "
                         "left exactly as saved. All three are still placed in memory, because the "
                         "stack is one problem -- LOGIC's mates sit at OUTPUTS' J307/J308 -- and "
                         "only the named boards' checks and unplaced parts gate the write")
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
    if not (a.stack or a.check or a.draw):
        ap.error("one of --stack, --check or --draw is needed")
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
    if not a.stack:
        pl = Placement.from_file(project, ix)
        picked = list(a.board) if a.board else None
        problems = check(pl, ix, boards=picked)
        if a.check:
            print(summary(pl) if not picked else
                  "\n".join(ln for ln in summary(pl).split("\n") if ln.split(":")[0] in picked))
            if picked:
                print(f"checking {' '.join(picked)} only")
            print(f"{len(problems)} problem(s)"
                  + ("" if problems else " -- the placement passes every check"))
            for p in problems:
                print(f"  - {p}")
        if a.draw:
            for path in draw(pl, ix, a.draw, prefix=src.stem):
                print(f"drawn: {path}")
        return EXIT_PROBLEMS if problems and a.check else 0
    out = Path(a.out) if a.out else src
    if editor_running():
        print("REFUSED: EasyEDA Pro is running; close it first", file=sys.stderr)
        return EXIT_REFUSED
    picked = list(a.board) if a.board else None
    pl = stack(project, ix, anchor=a.anchor, keep=a.keep)
    print(summary(pl))
    problems = check(pl, ix)
    docs = Path(a.docs)
    docs.mkdir(parents=True, exist_ok=True)
    for board in (picked or bp.STACK_ORDER):
        # the table is the record of what went INTO the file, so a board that
        # is not being written does not get one
        (docs / f"{board}-placement.md").write_text(placement_table(pl, board), encoding="utf-8")
    unplaced = sorted((p for items in pl.boards.values() for p in items.values() if p.unplaced),
                      key=lambda p: (bp.STACK_ORDER.index(p.board), _ref_key(p.refdes)))
    print(f"{len(problems)} problem(s)" + ("" if problems else " -- the placement passes every check"))
    for p in problems:
        print(f"  - {p}")
    for p in unplaced:
        print(f"  - {p.board} {p.refdes}: {p.reason}")
    if a.draw:
        for path in draw(pl, ix, a.draw, prefix=out.stem):
            print(f"drawn: {path}")
    # only the boards being written gate the write; the rest are reported
    gate_problems = problems if picked is None else check(pl, ix, boards=picked)
    gate_unplaced = [p for p in unplaced if picked is None or p.board in picked]
    if picked is not None:
        print(f"writing {' '.join(picked)} only: {len(gate_problems)} failed check(s) and "
              f"{len(gate_unplaced)} unplaced part(s) there; every other board's records are "
              f"left exactly as saved")
    if gate_problems or gate_unplaced:
        print(f"REFUSED: not written; {len(gate_unplaced)} part(s) had nowhere to go and "
              f"{len(gate_problems)} check(s) failed. The tables in {docs} show the proposal"
              + (f" and the pictures in {a.draw} show it" if a.draw else ""), file=sys.stderr)
        return EXIT_PROBLEMS
    apply(project, pl, boards=picked)
    try:
        path = write(project, pl, src, out, boards=picked)
    except RuntimeError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return EXIT_REFUSED
    prev = path.with_name(path.name + PREV_SUFFIX)
    print(f"written: {path}" + (f" (previous kept as {prev.name})" if prev.exists() else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
