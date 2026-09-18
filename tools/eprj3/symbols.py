"""Schematic symbols: one `SYMBOL` + `DEVICE` document pair per shape.

A sheet file embeds its own library.  Every `COMPONENT` on a page names a
`SYMBOL` document and a `DEVICE` document that must both be present in the same
`.esch2` file, before the `SCH_PAGE` document.  This module draws the symbols
and writes those two documents; `schematic.py` places them.

⛔ EVERY BYTE HERE IS GENERATED.  The glyphs are drawn from the geometry below,
not harvested from any vendor library, because this repository is public.

What the format fixes, and this module relies on (writer spec, `.esch2`):

  * Units are 0.01 inch and ⛔ +Y POINTS DOWN (§4).  "Up" on screen is -y.
  * A pin's `x`,`y` is its ELECTRICAL anchor -- the free end, away from the
    body.  That is the point a wire must touch, exactly (§5.4, §8.2).
  * ⛔ `PIN.rotation` in the file is the direction the pin's drawn line runs
    FROM its anchor TOWARD the body (§5.5).  So a pin on the body's LEFT edge
    has rotation 0 and a pin on the RIGHT edge has rotation 180.  This is 180°
    off the V2 convention; a V2-minded writer detaches every pin by 2 x length.
  * Every drawn primitive carries the `partId` of the symbol's one `PART`
    record; `POLY.points` is a list of `{x, y}` objects, never a flat array.
  * Pin identity lives in `ATTR`s `"Pin Name"`, `"Pin Number"`, `"Pin Type"`.
    `"Pin Number"` is what the netlist keys on, so it carries the netlist's own
    pin id verbatim (`"1"`, `"K"`, `"VS"`, `"+Vin"`).  Pad numbers are not
    known here -- they live in each part's `source` -- and no footprint is
    bound: the owner links LCSC devices in EasyEDA Pro.

⭐ EVERY PIN FACES LEFT OR RIGHT.  No symbol here has a pin on its top or bottom
edge.  That is deliberate: components are then placed at rotation 0 and net
flags at 0 or 180, and those are the two rotations whose transform does not
depend on the handedness question the spec could not settle from the example
(§9: 90/270 is read from the code but not independently confirmed).

A symbol is a pure function of its key: the same key gives the same drawing
every time.  Its uuid is assigned by the page that embeds it (`schematic.Page`)
and is namespaced by that sheet, so no two sheet files in a project share a
library uuid -- the example shares them only between sheets of ONE schematic,
and each board here is its own schematic.
"""
import hashlib
import json
import math
import re
from dataclasses import dataclass

from .pcb import EDIT_VERSION
from .records import serialize_record

#: The schematic snap grid: 0.1 inch.  Every pin anchor sits on it, so every
#: anchor is an exact integer and coincidence is exact (§8.2's tolerance is
#: 0.01 unit -- a float creeping in is a silently open connection).
GRID = 10
#: Pin rows 0.1 inch apart: the classic schematic pitch.
PIN_PITCH = GRID
#: Pin length of a box symbol's pins: one grid step, as in the verified
#: two-resistor example.  The body's half-width is a whole number of grid
#: steps, so body edge + one step keeps every anchor on the grid.
BOX_PIN_LEN = GRID

#: Estimated width of one character of theme-default text, in schematic units.
#: ⚠️ An ESTIMATE, deliberately generous: the default font size is not stated
#: anywhere in the format.  It only sizes boxes and spaces the layout; nothing
#: electrical depends on it.  Too small makes labels overlap; too large only
#: spreads the sheet.
CHAR_W = 6
#: Estimated height of one line of theme-default text.  Same caveat.
TEXT_H = 10

#: `SYMBOL` `META.docType` (§5.2, complete enum read from the application).
DOC_PART = 2
DOC_NETFLAG = 18

#: `PIN.rotation` values used here (§5.5).
FACES_LEFT = 0      # line runs +X from the anchor: the wire arrives from the left
FACES_RIGHT = 180   # line runs -X from the anchor: the wire arrives from the right

#: Pin electrical type.  The netlist states no directions, and inventing IN/OUT
#: would be typing a fact the design does not hold -- so every pin is Passive.
PIN_TYPE = "Passive"

#: Nets drawn with a ground glyph, and nets drawn with a rail glyph (bar and
#: name).  Presentation only: every other net gets a label tag, and all three
#: are the same net-flag mechanism underneath.
GROUND_NETS = frozenset({"GND"})
RAIL_NETS = frozenset({"V12", "V5", "V3P3", "HV_BPLUS"})

TWO_PIN_KINDS = frozenset({"R", "C", "D", "ZENER", "TVS", "FUSE", "FUSECLIP",
                           "L"})
FET_KINDS = frozenset({"NFET", "PFET"})

#: Designator template of a device, by kind.  A template only -- the placed
#: component's `Designator` ATTR carries the real refdes.
_DESIGNATOR = {
    "R": "R?", "C": "C?", "D": "D?", "ZENER": "D?", "TVS": "D?",
    "FUSE": "F?", "FUSECLIP": "FH?", "L": "L?", "CMCHOKE": "L?",
    "NFET": "Q?", "PFET": "Q?", "IC": "U?", "MODULE": "U?",
    "CONVERTER": "U?", "MECH": "M?", "CONN": "J?",
}


# --- geometry records -----------------------------------------------------
@dataclass(frozen=True)
class Pin:
    """One pin, in symbol-local coordinates."""
    number: str          # "Pin Number": the netlist's pin id, verbatim
    name: str            # "Pin Name": shown inside box symbols
    x: int               # ELECTRICAL anchor -- the end a wire touches
    y: int
    rotation: int        # FACES_LEFT or FACES_RIGHT
    length: int
    #: (x, y, align) where the pin name is shown, or None when it is hidden.
    label: tuple | None = None

    @property
    def outward(self):
        """-1 when the pin faces left (its wire leaves toward -X), +1 right."""
        if self.rotation == FACES_LEFT:
            return -1
        if self.rotation == FACES_RIGHT:
            return 1
        raise ValueError(f"pin {self.number} faces neither left nor right")


@dataclass(frozen=True)
class Graphic:
    type: str            # RECT / POLY / ARC
    geometry: dict       # the payload's geometry fields


@dataclass(frozen=True)
class Symbol:
    key: tuple
    title: str
    doc_type: int
    designator: str
    pins: tuple
    graphics: tuple
    #: The drawn body (x1, y1, x2, y2): part labels are placed from it.
    body: tuple
    #: Net flags only: the net this flag names.
    global_net_name: str | None = None
    #: Net flags only: how far the glyph reaches from the anchor along +X.
    reach: int = 0

    def pin(self, number):
        for p in self.pins:
            if p.number == number:
                return p
        raise KeyError(f"symbol {self.title} has no pin {number!r}")

    @property
    def bbox(self):
        """[minX, minY, maxX, maxY] over graphics and pin anchors.

        Advisory only: the format's own BBOX values are inconsistent and the
        V2 docs say not to rely on it (§5.3).
        """
        xs, ys = [], []
        for g in self.graphics:
            for x, y in _points_of(g):
                xs.append(x)
                ys.append(y)
        for p in self.pins:
            xs.append(p.x)
            ys.append(p.y)
        return [min(xs), min(ys), max(xs), max(ys)]


def _points_of(graphic):
    g = graphic.geometry
    if graphic.type == "RECT":
        return [(g["dotX1"], g["dotY1"]), (g["dotX2"], g["dotY2"])]
    if graphic.type == "POLY":
        return [(p["x"], p["y"]) for p in g["points"]]
    if graphic.type == "ARC":
        return [(g["startX"], g["startY"]), (g["referX"], g["referY"]),
                (g["endX"], g["endY"])]
    raise ValueError(graphic.type)


def _rect(x1, y1, x2, y2):
    return Graphic("RECT", {"dotX1": x1, "dotY1": y1, "dotX2": x2,
                            "dotY2": y2})


def _poly(*points, closed=False):
    return Graphic("POLY", {"points": [{"x": x, "y": y} for x, y in points],
                            "closed": closed})


def _arc(start, refer, end):
    """An arc through three points: start, one point ON the arc, end."""
    return Graphic("ARC", {"startX": start[0], "startY": start[1],
                           "referX": refer[0], "referY": refer[1],
                           "endX": end[0], "endY": end[1]})


def _snap_up(value, step=2 * GRID):
    return int(math.ceil(value / step) * step)


# --- ordinary component symbols ---------------------------------------------
def _two_pin(kind, pins):
    """A horizontal body, pin anchors at x = -20 and x = +20 on y = 0.

    D, ZENER and TVS put A on the left and K on the right whatever order the
    part declares them in -- the glyph's triangle and bar are the polarity
    mark, so the pin order has to follow the glyph, not the tuple.
    """
    names = set(pins)
    if kind in ("D", "ZENER", "TVS") and names == {"A", "K"}:
        left, right = "A", "K"
    elif kind == "C" and names == {"+", "-"}:
        left, right = "+", "-"
    elif len(pins) == 2:
        left, right = pins
    elif len(pins) == 1:
        left, right = pins[0], None
    else:
        raise ValueError(f"{kind} with pins {pins} is not a two-pin shape")

    polar_diode = kind in ("D", "ZENER", "TVS") and names == {"A", "K"}
    polar_cap = kind == "C" and names == {"+", "-"}
    if kind == "R":
        body_x, graphics = 10, [_rect(-10, -4, 10, 4)]
        body = (-10, -4, 10, 4)
    elif kind == "C":
        body_x = 2
        graphics = [_poly((-2, -6), (-2, 6)), _poly((2, -6), (2, 6))]
        if polar_cap:
            graphics += [_poly((-8, -7), (-4, -7)), _poly((-6, -9), (-6, -5))]
        body = (-2, -6, 2, 6)
    elif kind in ("D", "ZENER", "TVS"):
        body_x = 5
        graphics = [_poly((-5, -5), (-5, 5), (5, 0), closed=True),
                    _poly((5, -5), (5, 5))]
        if kind in ("ZENER", "TVS"):
            graphics += [_poly((5, -5), (3, -7)), _poly((5, 5), (7, 7))]
        if not polar_diode:
            # A diode whose pins are not A/K has no polarity to show.
            graphics = [_rect(-5, -5, 5, 5)]
        body = (-5, -5, 5, 5)
    elif kind == "FUSE":
        body_x = 10
        graphics = [_rect(-10, -3, 10, 3), _poly((-10, 0), (10, 0))]
        body = (-10, -3, 10, 3)
    elif kind == "FUSECLIP":
        # One end of a fuse holder: a clip open toward the fuse it holds.
        body_x = 10
        graphics = [_poly((4, -4), (-10, -4), (-10, 4), (4, 4))]
        body = (-10, -4, 4, 4)
    elif kind == "L":
        body_x = 10
        graphics = [_arc((-10, 0), (-5, -5), (0, 0)),
                    _arc((0, 0), (5, -5), (10, 0))]
        body = (-10, -5, 10, 0)
    else:
        raise ValueError(f"not a two-pin kind: {kind}")

    length = 2 * GRID - body_x
    out = [Pin(left, left, -2 * GRID, 0, FACES_LEFT, length)]
    if right is not None:
        out.append(Pin(right, right, 2 * GRID, 0, FACES_RIGHT, length))
    return tuple(out), tuple(graphics), body


def _fet(kind):
    """G on the left; D upper-right and S lower-right.

    Pins stay on the left and right edges (module docstring).  The arrow on
    the body tie points IN for an N-channel part and OUT for a P-channel one.
    """
    pins = (
        Pin("G", "G", -2 * GRID, 0, FACES_LEFT, 14, (-14, -2, "CENTER_BOTTOM")),
        Pin("D", "D", 2 * GRID, -GRID, FACES_RIGHT, GRID,
            (16, -12, "CENTER_BOTTOM")),
        Pin("S", "S", 2 * GRID, GRID, FACES_RIGHT, GRID,
            (16, 12, "CENTER_TOP")),
    )
    arrow = (_poly((-3, 0), (1, -2), (1, 2), closed=True) if kind == "NFET"
             else _poly((2, 0), (-2, -2), (-2, 2), closed=True))
    graphics = (
        _poly((-6, -7), (-6, 7)),                          # gate plate
        _poly((-3, -8), (-3, 8)),                          # channel
        _poly((-3, -6), (6, -6), (6, -10), (10, -10)),     # drain lead
        _poly((-3, 6), (6, 6), (6, 10), (10, 10)),         # source lead
        _poly((-3, 0), (6, 0), (6, 6)),                    # body tie
        arrow,
    )
    return pins, graphics, (-6, -10, 10, 10)


def _box(left, right, extra=()):
    """A rectangle with pins on its left and right edges, names shown inside.

    The body is sized so the longest left name and the longest right name fit
    side by side with a gap, and its half-width is a whole number of grid
    steps so every anchor lands on the grid.
    """
    rows = max(len(left), len(right), 1)
    top = -((rows - 1) // 2) * PIN_PITCH
    inset = 3
    name_w = (max((len(n) for n in left), default=0)
              + max((len(n) for n in right), default=0)) * CHAR_W
    width = max(4 * GRID, _snap_up(name_w + 2 * inset + 2 * GRID))
    half = width // 2
    body = (-half, top - GRID, half, top + (rows - 1) * PIN_PITCH + GRID)

    pins = []
    for i, name in enumerate(left):
        y = top + i * PIN_PITCH
        pins.append(Pin(name, name, -half - BOX_PIN_LEN, y, FACES_LEFT,
                        BOX_PIN_LEN, (-half + inset, y, "LEFT_MIDDLE")))
    for i, name in enumerate(right):
        y = top + i * PIN_PITCH
        pins.append(Pin(name, name, half + BOX_PIN_LEN, y, FACES_RIGHT,
                        BOX_PIN_LEN, (half - inset, y, "RIGHT_MIDDLE")))
    graphics = (_rect(*body),) + tuple(g(body) for g in extra)
    return tuple(pins), graphics, body


def _choke_core(body):
    """Two vertical bars through the middle: the common-mode choke's core.

    ⚠️ No windings are drawn.  Which pins pair into a winding is a fact about
    the part, and the symbol is shared by shape, so it must not assert one.
    """
    x1, y1, x2, y2 = body
    return _poly((-2, y1 + 3), (-2, y2 - 3))


def _choke_core2(body):
    x1, y1, x2, y2 = body
    return _poly((2, y1 + 3), (2, y2 - 3))


def _shape_hash(pins):
    return hashlib.sha1("\x1f".join(pins).encode("utf-8")).hexdigest()[:6]


def all_pins(part):
    """Every pin the part physically has: the netted ones, then the `nc` ones.

    `nc` pins are drawn -- the footprint will have them -- but get no wire.
    """
    return tuple(part.pins) + tuple(part.nc)


def part_key(part):
    return ("part", part.kind, all_pins(part))


def for_part(part):
    """The symbol for a `model.Part`.  A pure function of `part_key(part)`."""
    return _part_symbol(part.kind, all_pins(part))


def _part_symbol(kind, pins):
    key = ("part", kind, pins)
    if kind in TWO_PIN_KINDS and len(pins) <= 2:
        spins, graphics, body = _two_pin(kind, pins)
        title = {"C": "C_POL" if set(pins) == {"+", "-"} else "C"}.get(
            kind, kind)
    elif kind in FET_KINDS and set(pins) == {"G", "D", "S"} and len(pins) == 3:
        spins, graphics, body = _fet(kind)
        title = kind
    else:
        half = (len(pins) + 1) // 2
        extra = (_choke_core, _choke_core2) if kind == "CMCHOKE" else ()
        spins, graphics, body = _box(pins[:half], pins[half:], extra)
        title = f"{kind}_{len(pins)}P_{_shape_hash(pins)}"
    return Symbol(key=key, title=title, doc_type=DOC_PART,
                  designator=_DESIGNATOR.get(kind, "U?"), pins=spins,
                  graphics=graphics, body=body)


def connector_key(connector):
    return ("conn", tuple(cp.pin for cp in connector.pins))


def for_connector(connector):
    """The symbol for a `model.Connector`.  Pins alternate left and right in
    table order, which draws a 2-row header the way it is numbered and keeps
    a single-row harness connector compact."""
    pins = tuple(cp.pin for cp in connector.pins)
    spins, graphics, body = _box(pins[0::2], pins[1::2])
    return Symbol(key=("conn", pins),
                  title=f"CONN_{len(pins)}P_{_shape_hash(pins)}",
                  doc_type=DOC_PART, designator=_DESIGNATOR["CONN"],
                  pins=spins, graphics=graphics, body=body)


# --- net flags --------------------------------------------------------------
#: Length of a flag's own pin: the stem from its anchor to its glyph.
FLAG_PIN_LEN = 5


def flag_style(net_name):
    if net_name in GROUND_NETS:
        return "ground"
    if net_name in RAIL_NETS:
        return "rail"
    return "tag"


def net_flag(net_name):
    """A net flag (`docType` 18): one pin at (0, 0), glyph extending +X.

    Placed at rotation 0 it names a right-facing stub; at rotation 180 a
    left-facing one.  The glyphs are symmetric about y = 0, so 180 draws the
    exact mirror image and no mirroring (untested in the format) is needed.
    The net name is NOT part of the glyph: it is the placed component's
    `Name` ATTR, positioned in sheet coordinates, so it stays upright.
    """
    style = flag_style(net_name)
    pin = Pin("1", "1", 0, 0, FACES_LEFT, FLAG_PIN_LEN)
    s = FLAG_PIN_LEN
    if style == "ground":
        graphics = (_poly((s, -4), (s, 4)), _poly((s + 2, -3), (s + 2, 3)),
                    _poly((s + 4, -2), (s + 4, 2)),
                    _poly((s + 6, -1), (s + 6, 1)))
        reach = s + 6
    elif style == "rail":
        graphics = (_poly((s, -4), (s, 4)),)
        reach = s
    else:
        graphics = (_poly((s, 0), (s + 4, -4), (s + 20, -4), (s + 20, 4),
                          (s + 4, 4), closed=True),)
        reach = s + 20
    return Symbol(key=("flag", net_name), title=f"Flag-{net_name}",
                  doc_type=DOC_NETFLAG, designator="", pins=(pin,),
                  graphics=graphics, body=(0, -4, reach, 4),
                  global_net_name=net_name, reach=reach)


# --- documents --------------------------------------------------------------
def _json(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _dochead(doc_type, uuid, client, epoch_ms, edit_version):
    return serialize_record(
        {"type": "DOCHEAD"},
        payload={"docType": doc_type, "client": client, "uuid": uuid,
                 "updateTime": epoch_ms, "version": str(epoch_ms),
                 "editVersion": edit_version, "user": {}})


def part_id(symbol):
    """The id of the symbol's one `PART` record: document-scoped, derived."""
    digest = hashlib.sha1(_json(list(symbol.key)).encode("utf-8")).hexdigest()
    return "pid" + digest[:13]


def _symbol_attr(part_id, z, parent, key, value, *, shown_at=None):
    """A symbol-document ATTR, in the shape §10 writes."""
    x, y, align = shown_at if shown_at else (None, None, "LEFT_BOTTOM")
    return {"partId": part_id, "groupId": "", "locked": False, "zIndex": z,
            "parentId": parent, "key": key, "value": value,
            "keyVisible": False, "valueVisible": shown_at is not None,
            "x": x, "y": y, "rotation": 0, "color": None, "fillColor": None,
            "fontFamily": None, "fontSize": None, "strikeout": False,
            "underline": False, "italic": False, "fontWeight": False,
            "align": align, "version": "2.0"}


_STROKE_SOLID = {"strokeColor": None, "strokeStyle": "SOLID",
                 "fillColor": None, "strokeWidth": 1, "fillStyle": "NONE"}
_STROKE_THEME = {"strokeColor": None, "strokeStyle": None, "fillColor": None,
                 "strokeWidth": None, "fillStyle": None}


def symbol_records(symbol, uuid, *, client, epoch_ms,
                   edit_version=EDIT_VERSION):
    """The `SYMBOL` document, serialised, DOCHEAD first."""
    pid = part_id(symbol)
    body = []   # (type, id, payload)
    body.append(("META", "META", {"title": symbol.title, "description": "",
                                  "tags": [], "docType": symbol.doc_type,
                                  "source": ""}))
    body.append(("CANVAS", "CANVAS", {"originX": 0, "originY": 0}))
    body.append(("PART", pid, {"BBOX": symbol.bbox, "title": ""}))
    n = 0

    def eid():
        nonlocal n
        n += 1
        return f"e{n - 1}"

    for g in symbol.graphics:
        payload = {"partId": pid, "groupId": "", "locked": False,
                   "zIndex": len(body)}
        if g.type == "RECT":
            payload.update(g.geometry)
            payload.update({"radiusX": 0, "radiusY": 0, "rotation": 0})
            payload.update(_STROKE_SOLID)
        elif g.type == "ARC":
            payload.update(g.geometry)
            payload.update(_STROKE_SOLID)
        else:
            payload.update(g.geometry)
            payload.update(_STROKE_THEME)
        body.append((g.type, eid(), payload))

    for p in symbol.pins:
        pin_id = eid()
        body.append(("PIN", pin_id, {
            "partId": pid, "groupId": "", "locked": False,
            "zIndex": len(body), "display": True, "x": p.x, "y": p.y,
            "length": p.length, "rotation": p.rotation, "color": None,
            "pinShape": "NONE"}))
        body.append(("ATTR", eid(), _symbol_attr(
            pid, len(body), pin_id, "Pin Name", p.name, shown_at=p.label)))
        body.append(("ATTR", eid(), _symbol_attr(
            pid, len(body), pin_id, "Pin Number", p.number)))
        body.append(("ATTR", eid(), _symbol_attr(
            pid, len(body), pin_id, "Pin Type", PIN_TYPE)))

    body.append(("ATTR", eid(), _symbol_attr(pid, len(body), "", "Name",
                                             symbol.global_net_name
                                             or symbol.title)))
    if symbol.global_net_name is not None:
        body.append(("ATTR", eid(), _symbol_attr(
            pid, len(body), "", "Global Net Name", symbol.global_net_name)))
    else:
        body.append(("ATTR", eid(), _symbol_attr(
            pid, len(body), "", "Designator", symbol.designator)))

    out = [_dochead("SYMBOL", uuid, client, epoch_ms, edit_version)]
    for ticket, (type_, id_, payload) in enumerate(body, start=1):
        out.append(serialize_record(
            {"type": type_, "ticket": ticket, "id": id_}, payload=payload))
    return out


def device_records(symbol, uuid, symbol_uuid, *, client, epoch_ms,
                   edit_version=EDIT_VERSION, footprint_uuid="", title=None,
                   extra=()):
    """The `DEVICE` document: DOCHEAD + META, nothing else (§6).

    `Footprint` is the uuid of a FOOTPRINT document in the project, or empty
    when none is bound (EasyEDA Pro then refuses to export a netlist).  A net
    flag's device carries `Global Net Name`, which is what makes it a net flag
    (§8.4b), and never a footprint.
    """
    if footprint_uuid and symbol.global_net_name is not None:
        raise ValueError(f"{symbol.title}: a net flag has no footprint")
    title = title or symbol.title
    symbol_name = _json({"name": symbol.title, "uuid": symbol_uuid,
                         "source": ""})
    if symbol.global_net_name is not None:
        attributes = {"Global Net Name": symbol.global_net_name,
                      "Name": symbol.global_net_name, "Description": "",
                      "Symbol": symbol_uuid, "SymbolName": symbol_name}
    else:
        attributes = {"Symbol": symbol_uuid, "Footprint": footprint_uuid,
                      "Designator": symbol.designator, "Name": title,
                      "Value": "", "Description": "", "Add into BOM": "yes",
                      "Convert to PCB": "yes", "SymbolName": symbol_name}
        attributes.update(dict(extra))
    return [
        _dochead("DEVICE", uuid, client, epoch_ms, edit_version),
        serialize_record({"type": "META", "ticket": 1, "id": "META"},
                         payload={"title": title, "tags": [],
                                  "source": "", "images": [],
                                  "attributes": attributes}),
    ]


_TITLE_OK = re.compile(r"^[\x21-\x7e]+$")


def check_symbol(symbol):
    """Every invariant a placed symbol relies on.  Returns problems as text.

    Pins on the grid (so anchors stay integers after placement), each pin's
    line reaching toward the body (rotation and side agree), pin numbers
    unique (they are the netlist identity), and a title the editor can show.
    """
    problems = []
    seen = set()
    for p in symbol.pins:
        if p.number in seen:
            problems.append(f"{symbol.title}: pin number {p.number} twice")
        seen.add(p.number)
        if p.x % GRID or p.y % GRID:
            problems.append(f"{symbol.title}.{p.number}: anchor ({p.x},{p.y})"
                            f" is off the {GRID}-unit grid")
        if p.rotation not in (FACES_LEFT, FACES_RIGHT):
            problems.append(f"{symbol.title}.{p.number}: rotation "
                            f"{p.rotation} faces up or down")
        # The line runs from the anchor toward the body: a left pin must sit
        # left of the body, a right pin right of it.
        bx1, _, bx2, _ = symbol.body
        inner = p.x + (p.length if p.rotation == FACES_LEFT else -p.length)
        if p.rotation == FACES_LEFT and not (p.x < bx1 or symbol.doc_type ==
                                             DOC_NETFLAG):
            problems.append(f"{symbol.title}.{p.number}: left pin not left "
                            f"of the body")
        if p.rotation == FACES_RIGHT and not p.x > bx2:
            problems.append(f"{symbol.title}.{p.number}: right pin not right "
                            f"of the body")
        if symbol.doc_type != DOC_NETFLAG and not bx1 <= inner <= bx2:
            problems.append(f"{symbol.title}.{p.number}: pin line ends at "
                            f"x={inner}, outside the body [{bx1}, {bx2}]")
    if not _TITLE_OK.match(symbol.title):
        problems.append(f"title {symbol.title!r} is not printable ASCII")
    return problems
