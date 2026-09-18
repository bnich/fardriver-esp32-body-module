"""The `SCH_PAGE` document: every part of a board placed, every net connected.

HOW A NET IS MADE HERE -- stubs, not routing.  Every connected pin of every
placed component gets:

  1. a STUB: one `WIRE` group holding one `LINE`, two grid steps long, running
     outward from the pin.  Its inner end is EXACTLY the pin's absolute anchor
     (the §9 placement transform, in integers on the 10-unit grid), so the pin
     is on the wire by coordinate coincidence -- the only way a pin and a wire
     connect (§8.2);
  2. a NET FLAG at the stub's outer end: a component whose symbol has
     `META.docType` 18, whose device carries `"Global Net Name"`, and whose pin
     anchor sits exactly on that end (§8.4b).  It names the net;
  3. the stub `WIRE`'s own `NET` attribute set to the same name (§8.4a).

Two pins are on one net because their stubs carry the same name.  `NAMING`
chooses which naming records are written, so the gauge project can test each
mechanism alone:

    "flag"   flags only; every stub's NET value is ""   (§8.4b alone)
    "wire"   NET names only; no flags                   (§8.4a alone)
    "both"   flags AND NET names -- the default

⚠️ WHAT IS VERIFIED AND WHAT IS INFERRED.  Read this before trusting a build.

  VERIFIED against the writer spec and the official example:
    * the record grammar and the document order (library first, page last);
    * pin-to-wire connectivity is exact coincidence of a `LINE` endpoint with
      the transformed pin anchor (§8.2) -- and every anchor here is an integer
      on the grid, so coincidence is exact;
    * the placement transform at rotation 0 and 180 (§9) -- the only two used;
    * the net-flag component's record shape: `docType` 18 symbol, device with
      `Global Net Name`, component ATTRs `Symbol`/`Device`/`Relevance`/`Name`/
      `Global Net Name` (§8.4b, exemplified by the example's VCC and GND);
    * the ordinary component's ATTR set (§7.2).

  VERIFIED in EasyEDA Pro 3.2.149 by the gauge (`tools/gauge.py`, 2026-09-18):
  its exported netlist joined each pair on one net under its own name --
    * a flag names a net when it touches only a STUB;
    * a non-empty `NET` value names a net;
    * two separate wire groups with the same name are one net;
    * and flag + `NET` together, which is what every pin here gets.

  STILL INFERRED:
    * that extra component ATTRs (`Manufacturer Part`, `Value`,
      `Description`, `DNP`) are harmless -- the gauge's `Value` reached the
      netlist, which is evidence, not proof; that a locally authored symbol
      takes `source: ""`; that a symbol-level ATTR's `parentId` is "" (§5.8 says
      so; the example's flag symbols use the PART id instead);
    * that no sheet frame is needed.  None is emitted: the frame symbol's
      title-block records are not specified.  Content sits in the sheet-body
      quadrant (x > 0, y < 0) regardless.

Net names are validated against the application's rules (§8.4a) and a bad one
is REFUSED, never rewritten: a silently renamed net is a different net.
"""
import hashlib
import json
import re
from dataclasses import dataclass

from . import placement
from . import symbols as sym
from .pcb import EDIT_VERSION
from .placement import LABEL_GAP, STUB, refdes_key
from .records import serialize_record

#: Which naming records a stub carries: "flag", "wire" or "both".  Read at
#: call time, so a test (or the owner, after the gauge) can switch it.
NAMING = "both"
NAMINGS = ("flag", "wire", "both")


def naming_mode(naming=None):
    mode = NAMING if naming is None else naming
    if mode not in NAMINGS:
        raise ValueError(f"NAMING must be one of {NAMINGS}, not {mode!r}")
    return mode


# --- net names --------------------------------------------------------------
#: The application's own validator (§8.4a): printable ASCII 0x21-0x7E, which
#: excludes spaces, and no `$`.
_PARSE_BAD = re.compile(r"[^\x21-\x7e]")
#: The writer rule the spec derives from the DRC net-name rule: UPPERCASE,
#: digits and `_ - + ~ . / #` only.  Lowercase parses but raises DRC warnings.
_WRITER_OK = re.compile(r"^[A-Z0-9_\-+~./#]+$")


def validate_net_name(name):
    """Return `name` unchanged, or raise ValueError saying why it is refused.

    ⛔ Never rewrites.  A net quietly renamed on the way out is a different net
    from the one the netlist means, and nothing downstream would notice.
    """
    if not isinstance(name, str) or not name:
        raise ValueError(f"net name {name!r} is empty")
    if _PARSE_BAD.search(name):
        raise ValueError(
            f"net name {name!r} has a space or a character outside printable "
            f"ASCII; EasyEDA Pro rejects it")
    if "$" in name:
        raise ValueError(f"net name {name!r} contains '$'; EasyEDA Pro "
                         f"rejects it")
    if not _WRITER_OK.match(name):
        raise ValueError(
            f"net name {name!r} must be UPPERCASE letters, digits and "
            f"_ - + ~ . / # only; anything else fails the DRC net-name rule")
    return name


# --- the placement transform (§9) --------------------------------------------
def place_point(px, py, cx, cy, rotation=0, mirror=False):
    """Symbol-local (px, py) -> absolute sheet coordinates.  Exact integers.

    From the application's `multiplyPoint`, in stored (Y-down) coordinates:
    rotate, then mirror about the Y axis, then translate.  Only 0 and 180 are
    used by this emitter -- the two rotations whose result does not depend on
    the handedness the spec could not confirm from the example.
    """
    table = {0: (px, py), 90: (py, -px), 180: (-px, -py), 270: (-py, px)}
    if rotation not in table:
        raise ValueError(f"rotation {rotation} is not a right angle")
    x, y = table[rotation]
    if mirror:
        x = -x
    return cx + x, cy + y


# --- one page -----------------------------------------------------------------
@dataclass
class Placed:
    id: str
    symbol: object
    x: int
    y: int
    rotation: int
    #: pin number -> absolute anchor
    anchors: dict


def _uid(*parts):
    key = ":".join(str(p) for p in parts).encode("utf-8")
    return hashlib.sha1(key).hexdigest()[:16]


def _json(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _attr(parent, key, value, z, shown=None, key_visible=None,
          value_visible=None):
    """A page ATTR in the shape the editor writes (§7.2).

    `shown` is (x, y, align) for a displayed attribute; None leaves x/y null,
    which marks an attribute that has never been displayed.
    """
    if shown is None:
        x = y = rotation = align = None
    else:
        x, y, align = shown
        rotation = 0
    return {"x": x, "y": y, "rotation": rotation, "color": None,
            "fontFamily": None, "fontSize": None, "fontWeight": None,
            "italic": None, "underline": None, "strikeout": None,
            "align": align, "value": value, "keyVisible": key_visible,
            "valueVisible": value_visible, "key": key, "fillColor": None,
            "parentId": parent, "zIndex": z}


class Page:
    """Builds one sheet's library documents and page records.

    Record ids are derived (SHA-1 of the sheet uuid and a role key), so a
    rebuilt sheet is byte-identical, and a duplicate role key is an error here
    rather than a silently merged record in the editor.
    """

    def __init__(self, sheet_uuid, *, client, epoch_ms,
                 edit_version=EDIT_VERSION):
        self.sheet_uuid = sheet_uuid
        self.client = client
        self.epoch_ms = epoch_ms
        self.edit_version = edit_version
        self._library = {}      # symbol key -> (symbol, symbol uuid, device uuid)
        self._footprints = {}   # symbol key -> (footprint uuid, FOOTPRINT records)
        self._records = []      # (type, id, payload)
        self._ids = set()
        self._z = 0
        self.placed = []        # every Placed, flags included

    def _id(self, *role):
        oid = _uid(self.sheet_uuid, *role)
        if oid in self._ids:
            raise ValueError(f"two page records share the role {role!r}")
        self._ids.add(oid)
        return oid

    def _next_z(self):
        self._z += 1
        return self._z

    def use(self, symbol):
        """Embed `symbol` in this sheet's library; return (symbol, device)
        uuids.  Namespaced by the sheet, so no two sheets share a uuid."""
        entry = self._library.get(symbol.key)
        if entry is None:
            problems = sym.check_symbol(symbol)
            if problems:
                raise ValueError("bad symbol: " + "; ".join(problems))
            key = _json(list(symbol.key))
            entry = (symbol, _uid("symbol", self.sheet_uuid, key),
                     _uid("device", self.sheet_uuid, key))
            self._library[symbol.key] = entry
        elif entry[0] != symbol:
            raise ValueError(f"two different symbols share the key "
                             f"{symbol.key!r}")
        return entry[1], entry[2]

    def place(self, symbol, x, y, rotation=0, *, role, attrs):
        """A COMPONENT and its ATTRs.  `attrs` is a list of
        (key, value, shown, key_visible, value_visible)."""
        sym_uuid, dev_uuid = self.use(symbol)
        cid = self._id("component", *role)
        is_flag = symbol.doc_type == sym.DOC_NETFLAG
        if is_flag:
            # The shape §8.4b shows for a net-flag placement.
            inline = {"Footprints": "[]", "Devices": "[]",
                      "DeviceName": None, "FootprintName": None}
        else:
            inline = {"Footprints": "[]", "Devices": "[]",
                      "DeviceName": _json({"uuid": dev_uuid,
                                           "name": symbol.title,
                                           "source": ""}),
                      "FootprintName": None, "pinClass": {},
                      "differentialPairClass": {}, "Symbols": "[]"}
        self._records.append(("COMPONENT", cid, {
            "partId": sym.part_id(symbol), "x": x, "y": y,
            "rotation": rotation, "isMirror": False, "attrs": inline,
            "zIndex": self._next_z()}))
        full = [("Symbol", sym_uuid, None, None, None),
                ("Device", dev_uuid, None, None, None)] + list(attrs)
        for key, value, shown, kv, vv in full:
            self._records.append(("ATTR", self._id("attr", key, *role),
                                  _attr(cid, key, value, self._next_z(),
                                        shown, kv, vv)))
        anchors = {p.number: place_point(p.x, p.y, x, y, rotation)
                   for p in symbol.pins}
        placed = Placed(cid, symbol, x, y, rotation, anchors)
        self.placed.append(placed)
        return placed

    def wire(self, segments, *, role, net, label, show):
        """One WIRE group: its LINEs, a `Relevance` ATTR, and its `NET` ATTR.

        `net` is the NET value ("" = unnamed).  `label` is (x, y, align) for
        the NET text; `show` whether it is displayed.
        """
        wid = self._id("wire", *role)
        self._records.append(("WIRE", wid, {"zIndex": self._next_z()}))
        for i, (x1, y1, x2, y2) in enumerate(segments):
            for v in (x1, y1, x2, y2):
                if not isinstance(v, int):
                    raise TypeError(f"wire {role} endpoint {v!r} is not an "
                                    f"integer; coincidence would be lost")
            self._records.append(("LINE", self._id("line", i, *role), {
                "fillColor": None, "fillStyle": None, "strokeColor": None,
                "strokeStyle": None, "strokeWidth": None,
                "startX": x1, "startY": y1, "endX": x2, "endY": y2,
                "lineGroup": wid}))
        self._records.append(("ATTR", self._id("attr", "Relevance", *role),
                              _attr(wid, "Relevance", "[]", self._next_z())))
        self._records.append(("ATTR", self._id("attr", "NET", *role),
                              _attr(wid, "NET", net, self._next_z(), label,
                                    False, show)))
        return wid

    def flag(self, net, at, outward, *, role):
        """A net flag whose pin anchor is exactly `at`, glyph pointing away
        from the stub (rotation 0 for +X, 180 for -X)."""
        validate_net_name(net)
        symbol = sym.net_flag(net)
        x, y = at
        rotation = 0 if outward > 0 else 180
        text = (x + outward * (symbol.reach + LABEL_GAP), y,
                "LEFT_MIDDLE" if outward > 0 else "RIGHT_MIDDLE")
        placed = self.place(symbol, x, y, rotation, role=role, attrs=[
            ("Relevance", "[]", None, None, None),
            ("Name", net, text, None, True),
            ("Global Net Name", net, text, False, False),
        ])
        assert placed.anchors["1"] == (x, y)
        return placed

    # -- output ----------------------------------------------------------
    def bind_footprint(self, symbol, title, pads):
        """Give `symbol`'s device a FOOTPRINT document built from `pads`.

        Every pad number must be one of the symbol's pin numbers and every pin
        must have a pad, or the netlist would map a pin to nothing."""
        from . import footprints
        pins = {p.number for p in symbol.pins}
        nums = {p.num for p in pads}
        if pins != nums:
            raise ValueError(f"{symbol.title}: pads {sorted(nums)} do not match "
                             f"pins {sorted(pins)}")
        uuid = _uid("footprint", self.sheet_uuid, _json(list(symbol.key)))
        self._footprints[symbol.key] = (uuid, footprints.footprint_records(
            uuid, title, pads, client=self.client, epoch_ms=self.epoch_ms,
            edit_version=self.edit_version))

    def library_records(self):
        """FOOTPRINT, SYMBOL, then DEVICE documents: the order the editor
        writes a project's library in."""
        unused = set(self._footprints) - set(self._library)
        if unused:
            raise ValueError(f"footprints bound to symbols never placed: {sorted(unused)}")
        out = []
        for _, records in self._footprints.values():
            out += records
        for symbol, sym_uuid, dev_uuid in self._library.values():
            out += sym.symbol_records(symbol, sym_uuid, client=self.client,
                                      epoch_ms=self.epoch_ms,
                                      edit_version=self.edit_version)
        for key, (symbol, sym_uuid, dev_uuid) in self._library.items():
            fp = self._footprints.get(key)
            out += sym.device_records(symbol, dev_uuid, sym_uuid,
                                      client=self.client,
                                      epoch_ms=self.epoch_ms,
                                      edit_version=self.edit_version,
                                      footprint_uuid=fp[0] if fp else "")
        return out

    def page_records(self, first_ticket=2):
        """Serialised records after the page's META (ticket 1)."""
        return [serialize_record({"type": t, "ticket": n, "id": i},
                                 payload=p)
                for n, (t, i, p) in enumerate(self._records,
                                              start=first_ticket)]


def connect(page, anchor, outward, net, *, role, naming=None):
    """The production connection of one pin: a stub, and per `NAMING` a flag
    at its end and/or the net's name on the stub.

    ⭐ This is the one function that connects a pin, for the build and for the
    gauge's production-style experiment alike.
    """
    mode = naming_mode(naming)
    validate_net_name(net)
    ax, ay = anchor
    ex = ax + outward * STUB
    named_wire = mode in ("wire", "both")
    if mode == "wire":
        # No flag: the NET text is the only label, so it is shown where a
        # flag's name would be.
        label = (ex + outward * LABEL_GAP, ay,
                 "LEFT_MIDDLE" if outward > 0 else "RIGHT_MIDDLE")
    else:
        # A flag shows the name; the wire's own copy stays hidden so the net
        # is not labelled twice.
        label = ((ax + ex) // 2, ay, None)
    wid = page.wire([(ax, ay, ex, ay)], role=("stub",) + tuple(role),
                    net=net if named_wire else "", label=label,
                    show=mode == "wire")
    flag = None
    if mode in ("flag", "both"):
        flag = page.flag(net, (ex, ay), outward, role=("flag",) + tuple(role))
    return wid, flag


# --- a board ----------------------------------------------------------------
def part_name(part):
    """The displayed `Name`: the MPN, plus the value when it adds something
    short, plus "(DNP)" for a part that is not fitted."""
    name = part.mpn
    value = part.value.strip()
    if value and value not in part.mpn and len(value) <= 12:
        name = f"{part.mpn} {value}"
    if part.dnp:
        name += " (DNP)"
    return name


def connector_name(connector):
    """A short displayed name: the connector description's first clause."""
    text = connector.name
    for stop in (": ", ". "):
        cut = text.find(stop)
        if cut > 0:
            text = text[:cut]
    text = text.strip()
    return text if len(text) <= 32 else text[:31] + "…"


def board_refs(design, board):
    return ({p.refdes for p in design.parts if p.board == board}
            | {c.refdes for c in design.connectors if c.board == board})


def landed_pins(design):
    """(refdes, pin) -> net name, from the nets: the netlist's own truth."""
    return {(ref, pin): net.name for net in design.nets
            for ref, pin in net.pins}


def board_items(design, board):
    """Every part and connector of `board` as a placement `Item`, with the
    net of each pin that gets a wire.  `nc` pins and unused connector cavities
    get none."""
    landed = landed_pins(design)
    items = []
    for p in sorted((p for p in design.parts if p.board == board),
                    key=lambda p: refdes_key(p.refdes)):
        nets = {pin: landed[(p.refdes, pin)] for pin in p.pins
                if (p.refdes, pin) in landed}
        items.append(placement.Item(p.refdes, sym.for_part(p), nets,
                                    p.refdes, part_name(p)))
    for c in sorted((c for c in design.connectors if c.board == board),
                    key=lambda c: refdes_key(c.refdes)):
        nets = {cp.pin: landed[(c.refdes, cp.pin)] for cp in c.pins
                if (c.refdes, cp.pin) in landed}
        items.append(placement.Item(c.refdes, sym.for_connector(c), nets,
                                    c.refdes, connector_name(c),
                                    is_connector=True))
    return items


def project_unique_ids(design, boards):
    """refdes -> `Unique ID` ("gge1", ...), unique across the WHOLE project
    (§7.2: it is the schematic <-> PCB identity)."""
    order = {b: i for i, b in enumerate(boards)}
    things = list(design.parts) + list(design.connectors)
    refs = sorted((order[t.board], refdes_key(t.refdes), t.refdes)
                  for t in things if t.board in order)
    return {ref: f"gge{i}" for i, (_, _, ref) in enumerate(refs, start=1)}


@dataclass
class BoardSheet:
    board: str
    items: list
    layout: object
    page: Page
    naming: str

    @property
    def part_count(self):
        return sum(1 for i in self.items if not i.is_connector)

    @property
    def connector_count(self):
        return sum(1 for i in self.items if i.is_connector)

    @property
    def net_names(self):
        return sorted({n for i in self.items for n in i.nets.values()})


def _part_attrs(item, x, y, unique_id, *, part=None, connector=None):
    """The ATTRs of an ordinary component (§7.2), plus the part's catalogue
    data.  `Name` and `Designator` are shown; the rest are hidden."""
    bx1, by1, bx2, by2 = item.symbol.body
    cx = x + (bx1 + bx2) // 2
    attrs = [
        ("Unique ID", unique_id, None, None, None),
        # No `Footprint` ATTR: the component inherits its device's footprint.
        # An editor-saved sheet carries one only as a per-part override.
        ("Name", item.name, (cx, y + by2 + 5, "CENTER_TOP"), None, True),
        ("Designator", item.designator, (cx, y + by1 - 5, "CENTER_BOTTOM"),
         None, True),
    ]
    if part is not None:
        attrs += [("Manufacturer Part", part.mpn, None, None, None),
                  ("Value", part.value, None, None, None),
                  ("Description", part.package, None, None, None)]
        if part.dnp:
            attrs.append(("DNP", "yes", None, None, None))
    if connector is not None:
        attrs.append(("Description",
                      f"{connector.pitch_mm:g} mm pitch · {connector.name}",
                      None, None, None))
    attrs += [("Reuse Block", None, None, None, None),
              ("Group ID", None, None, None, None),
              ("Channel ID", None, None, None, None)]
    return attrs


def place_part(page, item, x, y, unique_id, *, part=None, connector=None):
    """Place one part or connector at rotation 0 with its full ATTR set."""
    return page.place(item.symbol, x, y, 0, role=("part", item.ref),
                      attrs=_part_attrs(item, x, y, unique_id, part=part,
                                        connector=connector))


def emit_board(design, board, sheet, *, naming=None, unique_ids=None):
    """Fill `sheet` (a `project.Sheet`) with every part, connector and net of
    `board`.  Returns the `BoardSheet` describing what was placed."""
    mode = naming_mode(naming)
    items = board_items(design, board)
    for net in sorted({n for i in items for n in i.nets.values()}):
        validate_net_name(net)      # refuse before emitting anything
    lay = placement.layout(items)
    clash = placement.overlaps(lay)
    if clash:
        raise ValueError(f"{board}: placement overlaps {clash[:5]}")
    if unique_ids is None:
        unique_ids = project_unique_ids(design, (board,))

    parts = {p.refdes: p for p in design.parts}
    connectors = {c.refdes: c for c in design.connectors}
    page = Page(sheet.uuid, client=sheet.client, epoch_ms=sheet.epoch_ms,
                edit_version=sheet.edit_version)
    for item in items:
        x, y = lay.origins[item.ref]
        placed = place_part(page, item, x, y, unique_ids[item.ref],
                            part=parts.get(item.ref),
                            connector=connectors.get(item.ref))
        for pin in item.symbol.pins:
            net = item.nets.get(pin.number)
            if net is None:
                continue
            connect(page, placed.anchors[pin.number], pin.outward, net,
                    role=(item.ref, pin.number), naming=mode)

    sheet.library_records = page.library_records()
    sheet.page_records = page.page_records(first_ticket=2)
    return BoardSheet(board, items, lay, page, mode)
