"""EasyEDA Pro V2 footprint documents -> V3 `FOOTPRINT` records.

WHY THIS EXISTS.  Real land patterns come from EasyEDA's LCSC library, which
serves footprints only as V2 documents: one positional JSON array per line,
first line `["DOCTYPE","FOOTPRINT","1.3"]`.  The project this repository
generates is a V3 record stream (`records.py`), and a V2 line inside a V3
stream is dropped by the editor WITHOUT A WORD.  So a library footprint has to
be converted before it can be bound to a device.

WHERE THE RULES COME FROM.  Every mapping below was read off the editor's own
conversion: 19 example footprints stored as V2, and the same 19 as EasyEDA Pro
3.2 converted them to V3 when it upgraded the project.  `tests/test_v2footprint`
replays all 19 and demands record-for-record equality whenever those files are
present locally.  (They are EasyEDA example material and are never committed.)
Field NAMES follow the public format documentation; the VALUES follow the
editor, which disagrees with the V2 documentation in at least one place (text
alignment, see `_ORIGIN`).

⛔ Anything the 19 examples do not exercise RAISES `V2FootprintError` rather
than being guessed: an unknown record type, an unexpected field count, an enum
value that was never seen converted, a non-empty special-pad stack.  A guess
here is invisible -- the footprint opens and one pad is the wrong shape -- so
the converter stops and names the line instead.  Extending it means finding an
editor-converted example of the new case first.

WHAT THE CONVERSION DOES, beyond renaming positional fields:

  * Units and axes are UNCHANGED.  Footprint V2 and V3 are both mil with +Y up:
    every coordinate of all 19 examples is identical on both sides.  (Unlike
    the schematic, where V3 y = -V2 y.  Do not carry that rule over.)
  * `CONNECT` records vanish; what they held moves into the master's `refs`.
  * `SUBSTRATE` layers are renumbered 101.. -> 361.. .
  * `ELE_PLACEHOLDER` records are inserted and the primitives regrouped by
    type (`_primitive_records`).
  * `zIndex`, `padLen`, `polyType` and friends -- V3 fields V2 has no column
    for -- get the values the editor writes.
"""
import json
import re

from .pcb import EDIT_VERSION, SUBSTRATE_LAYER
from .records import HEADER_SEPARATOR, RECORD_SEPARATOR, serialize_record


class V2FootprintError(ValueError):
    """The V2 text holds something this converter has not seen converted."""


#: V2 substrate layers are numbered from here; V3 numbers them from
#: `SUBSTRATE_LAYER` (361).  All 570 substrate layers in the examples moved by
#: exactly this offset and no other layer moved.
V2_FIRST_SUBSTRATE = 101
V2_LAST_SUBSTRATE = 130

#: V2 text alignment code -> V3 `origin`.  ⚠️ The V2 documentation numbers
#: alignment 0..8 row by row from the top-left, which would make 3 LEFT_MIDDLE.
#: The editor converts 3 to LEFT_BOTTOM (every ATTR in the examples).  With the
#: documentation shown wrong once, no other code is inferred from it.
_ORIGIN = {3: "LEFT_BOTTOM"}

#: V2 FILL mode -> V3 `fillStyle`.  Only solid fills occur in the examples.
_FILL_STYLE = {0: "SOLID"}

#: V2 pad function -> V3 `padType`.  Only ordinary pads occur in the examples.
_PAD_FUNCTION = {0: "NORMAL"}

#: V2 hole and pad shapes that appear converted in the examples.  The name
#: passes through unchanged; width and height become named fields.
_HOLE_SHAPES = frozenset({"ROUND", "SLOT"})
_PAD_SHAPES = frozenset({"ELLIPSE", "OVAL", "RECT"})

#: V2 CANVAS grid type -> V3 `gridType`/`multiGridType` (V2 doc: 0 none,
#: 1 grid, 2 dots).  0 and 2 were seen converted (a V2 PCB canvas).
_GRID_TYPE = {0: "NONE", 2: "OUTLETS"}

#: Tokens that may appear inside a numeric V2 polygon path.
_PATH_TOKENS = frozenset({"L", "ARC", "CARC", "C"})

_ELEMENT_ID = re.compile(r"^e([1-9][0-9]*)$")

#: Primitive types carried across.  Everything else except the ones handled
#: explicitly in `convert` raises.
_PRIMITIVES = ("PAD", "FILL", "POLY", "ATTR", "STRING")
#: The keys a V2 1.8 HEAD carries: metadata only.
_HEAD_KEYS = frozenset({"editorVersion", "importFlag", "uuid", "title", "source"})


def parse_v2(v2_text):
    """V2 text -> list of (line_number, record) with the record a list.

    A blank line carries nothing and is skipped.  So is `[]`: a V2 line is
    dispatched on its first element, the type string, and an empty array has
    none -- it is an empty slot, not a record (LCSC serves footprints with one
    between the header section and the primitives).  Any NON-empty array
    without a string type, and any line that is not a JSON array, raises.
    """
    out = []
    for n, line in enumerate(v2_text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as exc:
            raise V2FootprintError(f"line {n}: not JSON ({exc})") from None
        if not isinstance(rec, list):
            raise V2FootprintError(f"line {n}: not a JSON array: {line[:60]!r}")
        if not rec:
            continue
        if not isinstance(rec[0], str):
            raise V2FootprintError(f"line {n}: no type string: {line[:60]!r}")
        out.append((n, rec))
    return out


# --- field helpers -----------------------------------------------------------

def _where(n, rec):
    return f"line {n} ({rec[0]} {rec[1] if len(rec) > 1 else ''})"


def _arity(n, rec, *allowed):
    if len(rec) not in allowed:
        raise V2FootprintError(
            f"{_where(n, rec)}: {len(rec)} fields, only {allowed} seen converted")


def _bool(n, rec, i):
    """V2 encodes a yes/no as 1/0; newer editors (V2 1.8) sometimes write a
    JSON false/true instead, which is just as unambiguous."""
    v = rec[i]
    if v is True or v is False:
        return v
    if v not in (0, 1):
        raise V2FootprintError(
            f"{_where(n, rec)}: field {i} = {v!r}, expected 0, 1, false or true")
    return v == 1


def _enum(n, rec, i, table, what):
    v = rec[i]
    if isinstance(v, bool) or v not in table:
        raise V2FootprintError(
            f"{_where(n, rec)}: {what} {v!r} was never seen converted "
            f"(known: {sorted(table)})")
    return table[v]


def _element_number(n, rec):
    m = _ELEMENT_ID.match(rec[1]) if isinstance(rec[1], str) else None
    if not m:
        raise V2FootprintError(
            f"{_where(n, rec)}: primitive id {rec[1]!r} is not of the form "
            f"e<N>; zIndex and ELE_PLACEHOLDER are derived from N")
    return int(m.group(1))


def _layer(n, rec, layer_id, substrates):
    if layer_id in substrates:
        raise V2FootprintError(
            f"{_where(n, rec)}: primitive on substrate layer {layer_id}, "
            f"which V3 renumbers; never seen converted")
    return layer_id


def _single_path(n, rec, path):
    """One V2 single polygon -> its V3 form.

    `R` is the only form that changes: V2 writes `R x y w h 0`, V3 appends a
    sixth number, and the editor writes it 0.  A non-zero fifth number was
    never seen, and the V2 documentation disagrees with its own example about
    what it is, so it raises.  `CIRCLE cx cy r` and the numeric `L`/`ARC`
    forms are identical on both sides.
    """
    if not isinstance(path, list) or not path:
        raise V2FootprintError(f"{_where(n, rec)}: empty or malformed path")
    head = path[0]
    if head == "R":
        if len(path) != 6 or path[5] != 0:
            raise V2FootprintError(
                f"{_where(n, rec)}: rectangle path {path!r}; only "
                f"['R', x, y, w, h, 0] was seen converted")
        return path + [0]
    if head == "CIRCLE":
        if len(path) != 4:
            raise V2FootprintError(
                f"{_where(n, rec)}: circle path {path!r}; only "
                f"['CIRCLE', cx, cy, r] was seen converted")
        return list(path)
    for tok in path:
        if isinstance(tok, str):
            if tok not in _PATH_TOKENS:
                raise V2FootprintError(
                    f"{_where(n, rec)}: path token {tok!r} never seen converted")
        elif isinstance(tok, bool) or not isinstance(tok, (int, float)):
            raise V2FootprintError(f"{_where(n, rec)}: path element {tok!r}")
    return list(path)


def _complex_path(n, rec, path):
    """A FILL path: one single polygon, or a list of them.  Shape is kept."""
    if isinstance(path, list) and path and isinstance(path[0], list):
        return [_single_path(n, rec, p) for p in path]
    return _single_path(n, rec, path)


# --- per-type conversion -----------------------------------------------------

def _layer_record(n, rec):
    """LAYER: [id, type, name, state, activeColor, activeT, inactiveColor,
    inactiveT].  `state` is a bit set: 1 used, 2 shown, 4 locked."""
    _arity(n, rec, 9)
    _, lid, ltype, name, state, acol, atr, icol, _itr = rec
    if isinstance(state, bool) or state not in range(8):
        raise V2FootprintError(f"{_where(n, rec)}: layer state {state!r}")
    if ltype == "SUBSTRATE":
        last_v3 = SUBSTRATE_LAYER + (V2_LAST_SUBSTRATE - V2_FIRST_SUBSTRATE)
        if V2_FIRST_SUBSTRATE <= lid <= V2_LAST_SUBSTRATE:
            lid = lid - V2_FIRST_SUBSTRATE + SUBSTRATE_LAYER
        elif not SUBSTRATE_LAYER <= lid <= last_v3:
            # A document written by a newer editor (V2 1.8, "2.2.C") already
            # numbers its substrates in V3's range: those pass through.
            raise V2FootprintError(
                f"{_where(n, rec)}: substrate layer {lid} outside both "
                f"{V2_FIRST_SUBSTRATE}..{V2_LAST_SUBSTRATE} and "
                f"{SUBSTRATE_LAYER}..{last_v3}")
    return ("LAYER", json.dumps(["LAYER", lid], separators=(",", ":")), {
        "layerType": ltype, "layerName": name,
        "use": bool(state & 1), "show": bool(state & 2),
        "locked": bool(state & 4),
        "activeColor": acol, "activateTransparency": atr,
        # The editor writes 0.5 here whatever V2 said: every one of the 2204
        # example layers says 1 in V2 and 0.5 in V3 (a V2 PCB saying 0.5
        # converts to 0.5 as well).
        "inactiveColor": icol, "inactiveTransparency": 0.5,
    })


def _canvas_record(n, rec):
    """CANVAS: [originX, originY, unit, gridX, gridY, snapX, snapY, altSnapX,
    altSnapY, gridType, multiGridType, multiGridRatio]; V2 stops early and
    V3 omits whatever V2 did not write.

    The 6-field form is what the 19 examples hold.  The longer positions were
    seen converted on a V2 PCB canvas and use the same record grammar; LCSC
    footprints carry the 8-field form (snap sizes).  `unit` is a display hint
    only -- footprint numbers are mil whatever it says.
    """
    _arity(n, rec, 6, 8, 10, 11, 12, 13)
    out = {"originX": rec[1], "originY": rec[2], "unit": rec[3],
           "gridXSize": rec[4], "gridYSize": rec[5]}
    for i, key in ((6, "snapXSize"), (7, "snapYSize"),
                   (8, "altSnapXSize"), (9, "altSnapYSize")):
        if len(rec) > i:
            out[key] = rec[i]
    out["gridType"] = (_enum(n, rec, 10, _GRID_TYPE, "grid type")
                       if len(rec) > 10 else "NONE")
    out["multiGridType"] = (_enum(n, rec, 11, _GRID_TYPE, "grid type")
                            if len(rec) > 11 else "NONE")
    if len(rec) > 12:
        out["multiGridRatio"] = rec[12]
    out["highlightValue"] = 0.5
    return ("CANVAS", "CANVAS", out)


def _pad_shape(n, rec, shape):
    """`["ELLIPSE"|"OVAL"|"RECT", w, h]` -> {padType, width, height}.

    LCSC writes rectangles with a fourth element, the corner radius, which V3
    names `radius`.  Only radius 0 is accepted: whether V2 means mil or a
    percentage was never seen, and a wrong guess changes copper.
    """
    if (not isinstance(shape, list) or not shape
            or shape[0] not in _PAD_SHAPES):
        raise V2FootprintError(
            f"{_where(n, rec)}: pad shape {shape!r} never seen converted")
    if len(shape) == 3:
        return {"padType": shape[0], "width": shape[1], "height": shape[2]}
    if shape[0] == "RECT" and len(shape) == 4 and shape[3] == 0:
        return {"padType": "RECT", "width": shape[1], "height": shape[2],
                "radius": 0}
    raise V2FootprintError(
        f"{_where(n, rec)}: pad shape {shape!r} never seen converted")


def _hole(n, rec, hole):
    if hole is None:
        return None
    if (not isinstance(hole, list) or len(hole) != 3
            or hole[0] not in _HOLE_SHAPES):
        raise V2FootprintError(
            f"{_where(n, rec)}: hole {hole!r} never seen converted")
    return {"holeType": hole[0], "width": hole[1], "height": hole[2]}


def _pad_record(n, rec, substrates):
    """PAD, 22 fields (footprint 1.3), or 27 with the thermal-relief tail.

    The tail -- connect mode, spoke space/width/angle, unused inner layers --
    is absent from every example footprint.  It was seen converted once, on
    a V2 PCB pad: all four thermal fields null, and V3 then carries the
    layer list as `unusedInnerLayers` before `padLen`.  Only that form is
    accepted.
    """
    _arity(n, rec, 22, 27)
    if rec[11] != []:
        raise V2FootprintError(
            f"{_where(n, rec)}: special (per-layer) pad stack {rec[11]!r} "
            f"never seen converted")
    out = {"groupId": rec[2], "netName": rec[3],
           "layerId": _layer(n, rec, rec[4], substrates), "num": rec[5],
           "centerX": rec[6], "centerY": rec[7], "padAngle": rec[8],
           "hole": _hole(n, rec, rec[9]),
           "defaultPad": _pad_shape(n, rec, rec[10]), "specialPad": [],
           "padOffsetX": rec[12], "padOffsetY": rec[13],
           "relativeAngle": rec[14], "plated": _bool(n, rec, 15),
           "padType": _enum(n, rec, 16, _PAD_FUNCTION, "pad function"),
           "topSolderExpansion": rec[17], "bottomSolderExpansion": rec[18],
           "topPasteExpansion": rec[19], "bottomPasteExpansion": rec[20],
           "locked": _bool(n, rec, 21), "zIndex": _element_number(n, rec),
           "connectMode": None, "spokeSpace": None, "spokeWidth": None,
           "spokeAngle": None}
    if len(rec) == 27:
        if rec[22:26] != [None] * 4 or not isinstance(rec[26], list):
            raise V2FootprintError(
                f"{_where(n, rec)}: thermal relief {rec[22:]!r}; only the "
                f"all-null form was seen converted")
        out["unusedInnerLayers"] = list(rec[26])
    out["padLen"] = 0
    return ("PAD", rec[1], out)


def _fill_record(n, rec, substrates, refs):
    _arity(n, rec, 9)
    return ("FILL", rec[1], {
        "groupId": rec[2], "netName": rec[3],
        "layerId": _layer(n, rec, rec[4], substrates), "width": rec[5],
        "fillStyle": _enum(n, rec, 6, _FILL_STYLE, "fill mode"),
        "path": _complex_path(n, rec, rec[7]), "locked": _bool(n, rec, 8),
        "zIndex": _element_number(n, rec), "isBridgingCopper": False,
        "networkList": [], "refs": refs.pop(rec[1], [])})


def _poly_record(n, rec, substrates):
    _arity(n, rec, 8)
    return ("POLY", rec[1], {
        "groupId": rec[2], "netName": rec[3],
        "layerId": _layer(n, rec, rec[4], substrates), "width": rec[5],
        "path": _single_path(n, rec, rec[6]), "locked": _bool(n, rec, 7),
        "zIndex": _element_number(n, rec), "polyType": "NORMAL"})


def _attr_record(n, rec, substrates):
    _arity(n, rec, 22)
    return ("ATTR", rec[1], {
        "groupId": rec[2], "parentId": rec[3],
        "layerId": _layer(n, rec, rec[4], substrates),
        "x": rec[5], "y": rec[6], "key": rec[7], "value": rec[8],
        "keyVisible": _bool(n, rec, 9), "valueVisible": _bool(n, rec, 10),
        "fontFamily": rec[11], "fontSize": rec[12], "strokeWidth": rec[13],
        "bold": _bool(n, rec, 14), "italic": _bool(n, rec, 15),
        "origin": _enum(n, rec, 16, _ORIGIN, "text alignment"),
        "angle": rec[17], "reverse": _bool(n, rec, 18), "expansion": rec[19],
        "mirror": _bool(n, rec, 20), "locked": _bool(n, rec, 21),
        "zIndex": _element_number(n, rec)})


def _string_record(n, rec, substrates):
    """STRING, silkscreen text: [id, groupId, layer, x, y, text, font, size,
    stroke, bold, italic, origin, angle, reverse, expansion, mirror, locked].
    Field for field the example PCB's 19 strings (whose V3 form adds a
    PCB-only specialColor); the footprint form is EasyEDA's documented one."""
    _arity(n, rec, 18)
    return ("STRING", rec[1], {
        "partitionId": "", "groupId": rec[2],
        "layerId": _layer(n, rec, rec[3], substrates),
        "x": rec[4], "y": rec[5], "text": rec[6], "fontFamily": rec[7],
        "fontSize": rec[8], "strokeWidth": rec[9],
        "bold": _bool(n, rec, 10), "italic": _bool(n, rec, 11),
        "origin": _enum(n, rec, 12, _ORIGIN, "text alignment"),
        "angle": rec[13], "reverse": _bool(n, rec, 14), "expansion": rec[15],
        "mirror": _bool(n, rec, 16), "locked": _bool(n, rec, 17),
        "zIndex": _element_number(n, rec)})


def _primitive_records(prims):
    """Primitives regrouped by type, each run behind an ELE_PLACEHOLDER.

    `prims` is [(type, id_number, (type, id, payload))] in V2 order.  The
    editor writes all primitives of one type together, types in the order
    they first appear in V2, V2 order kept within a type.  Every run of
    consecutive element numbers within a type is preceded by

        {"type":"ELE_PLACEHOLDER","id":"placeholder<k>"}||
            {"dataType":<type>,"max":m}

    with k counting placeholders from 1 in file order, and m the run's first
    element number for a type's FIRST run, or the count of element numbers
    skipped since the previous run of that type for any later one:

        POLY e1..e13, PAD e14..e16, FILL e17..e21, POLY e22, ATTR e23..e24
        -> <POLY 1> e1..e13 <POLY 8> e22 <PAD 14> e14..e16
           <FILL 17> e17..e21 <ATTR 23> e23 e24

    All 111 placeholders in the examples obey this.  In the examples a run of
    consecutive numbers is also a run of adjacent V2 lines, so the two
    readings cannot be told apart there; numbers going backwards within a
    type would separate them and raise instead.
    """
    by_type = {}
    for t, num, rec3 in prims:
        by_type.setdefault(t, []).append((num, rec3))
    out, k = [], 0
    for t, members in by_type.items():
        prev = None
        for num, rec3 in members:
            if prev is not None and num <= prev:
                raise V2FootprintError(
                    f"{t} e{num} follows e{prev}: element numbers go "
                    f"backwards within a type, never seen converted")
            if prev is None or num != prev + 1:
                k += 1
                out.append(("ELE_PLACEHOLDER", f"placeholder{k}",
                            {"dataType": t,
                             "max": num if prev is None else num - prev - 1}))
            out.append(rec3)
            prev = num
    return out


def convert(v2_text, *, uuid, title, client, epoch_ms,
            edit_version=EDIT_VERSION, description="", source=""):
    """A V2 footprint document -> serialised V3 records, DOCHEAD first.

    `title`, `description` and `source` fill META; in a V2 project they are
    the library row's `display_title`, `description` and `source` columns,
    not anything in the V2 text.  Order: DOCHEAD, META, the LAYER table in V2
    order, ACTIVE_LAYER, CANVAS, then the primitives (`_primitive_records`).
    Tickets run 1..N from META in file order and DOCHEAD carries none, as
    everywhere else in this package.

    Two things LCSC documents do that the examples never do, kept as they
    are for want of evidence: the LAYER table out of id order (kept in V2
    order, not sorted) and upper-case colours (copied, not lower-cased).
    Both are display configuration; neither touches copper.
    """
    lines = parse_v2(v2_text)
    if not lines or lines[0][1][:2] != ["DOCTYPE", "FOOTPRINT"]:
        raise V2FootprintError(
            "not a V2 footprint: the first record must be "
            "['DOCTYPE', 'FOOTPRINT', version]")
    _arity(*lines[0], 3)

    layers, active, canvas, prims = [], None, None, []
    substrates = set()
    refs = {}
    for n, rec in lines[1:]:
        if rec[0] == "LAYER":
            layers.append(_layer_record(n, rec))
            if rec[2] == "SUBSTRATE":
                substrates.add(rec[1])
        elif rec[0] == "CONNECT":
            # CONNECT [master, [ids]] ties primitives into one logical group.
            # In the examples all 64 tie one pin-area FILL -- PIN_SOLDERING
            # (layer 50) or PIN_FLOATING (51) -- to the single PAD it belongs
            # to: ["CONNECT","e4",["e1"]].  V3 has no CONNECT record type; the
            # editor keeps the list on the master itself, as the FILL's
            # `refs` ["e1"], and writes the CONNECT nowhere.  Only FILL
            # masters were seen, so any other master raises below.
            _arity(n, rec, 3)
            if (rec[1] in refs or not isinstance(rec[2], list)
                    or not all(isinstance(i, str) for i in rec[2])):
                raise V2FootprintError(f"{_where(n, rec)}: malformed CONNECT")
            refs[rec[1]] = list(rec[2])
        elif rec[0] in _PRIMITIVES:
            prims.append((n, rec))
        elif rec[0] == "ACTIVE_LAYER":
            _arity(n, rec, 2)
            # The editor's selected layer: UI state, no copper.  LCSC serves
            # footprints with this line twice, in V2 1.8 with DIFFERENT values
            # (49, then 1).  A V2 document is a sequence, so the last one is
            # the document's state; V3 keeps one record.
            active = ("ACTIVE_LAYER", "ACTIVE_LAYER", {"layerId": rec[1]})
        elif rec[0] == "LAYER_PHYS":
            # Per-layer stackup (material, thickness, permittivity), written
            # by newer editors into footprints too.  The PCB owns the stackup;
            # the editor's own conversions of all 19 example footprints carry
            # none, so leaving it out gives a form the editor itself writes.
            _arity(n, rec, 7)
            continue
        elif rec[0] == "PREFERENCE":
            # The editor's routing settings (track width, via size, corner
            # style, optimisation), written by newer editors into footprints:
            # UI state, not footprint content.  The editor's own conversions of
            # all 19 example footprints carry none.
            continue
        elif rec[0] == "FONT":
            # Glyph outlines cached for STRING text.  The example PCB's V2 form
            # carries none and the editor's V3 form of it carries 51: the
            # editor builds the cache itself, so dropping it loses nothing.
            continue
        elif rec[0] == "HEAD":
            # V2 1.8 opens with HEAD {editorVersion, importFlag, uuid, title,
            # source}: who wrote the document and what it is called.  META
            # takes title and source from convert()'s arguments, and the
            # document gets its own uuid.  Anything else in it could be
            # content, so it raises rather than being dropped.
            _arity(n, rec, 2)
            extra = set(rec[1]) - _HEAD_KEYS if isinstance(rec[1], dict) else {"?"}
            if extra:
                raise V2FootprintError(
                    f"{_where(n, rec)}: HEAD carries {sorted(extra)}, which is not "
                    f"document metadata -- dropping it could lose content")
        elif rec[0] == "CANVAS":
            if canvas is not None:
                raise V2FootprintError(f"{_where(n, rec)}: second CANVAS")
            canvas = _canvas_record(n, rec)
        else:
            raise V2FootprintError(
                f"line {n}: V2 record type {rec[0]!r} is not converted -- "
                f"dropping it would lose it silently")
    if active is None or canvas is None:
        raise V2FootprintError("a V2 footprint needs ACTIVE_LAYER and CANVAS")

    ids = [rec[1] for _, rec in prims]
    if len(set(ids)) != len(ids):
        raise V2FootprintError(f"primitive ids repeat: {ids}")
    converted = []
    for n, rec in prims:
        t = rec[0]
        if t == "PAD":
            rec3 = _pad_record(n, rec, substrates)
        elif t == "FILL":
            rec3 = _fill_record(n, rec, substrates, refs)
        elif t == "POLY":
            rec3 = _poly_record(n, rec, substrates)
        elif t == "STRING":
            rec3 = _string_record(n, rec, substrates)
        else:
            rec3 = _attr_record(n, rec, substrates)
        converted.append((t, _element_number(n, rec), rec3))
    if refs:
        raise V2FootprintError(
            f"CONNECT masters that are not FILLs in this document: "
            f"{sorted(refs)}; only FILL masters were seen converted")

    body = [("META", "META", {"title": title, "description": description,
                              "tags": [], "source": source}),
            *layers, active, canvas, *_primitive_records(converted)]
    head = serialize_record(
        {"type": "DOCHEAD"},
        payload={"docType": "FOOTPRINT", "client": client, "uuid": uuid,
                 "updateTime": epoch_ms, "version": str(epoch_ms),
                 "editVersion": edit_version, "user": {}})
    return [head] + [serialize_record({"type": t, "ticket": i, "id": rid},
                                      payload=pl)
                     for i, (t, rid, pl) in enumerate(body, start=1)]


# --- comparison --------------------------------------------------------------

#: DOCHEAD fields that identify a copy (who saved it, when, which editor)
#: rather than describe the footprint.
DOCHEAD_IDENTITY = ("client", "uuid", "updateTime", "version", "editVersion",
                    "user")


def parse_records(records):
    """Serialised records (a list, or joined text) -> [(header, payload)]."""
    if isinstance(records, str):
        records = records.split(RECORD_SEPARATOR)
    out = []
    for r in records:
        head, sep, payload = r.partition(HEADER_SEPARATOR)
        if not sep:
            raise ValueError(f"not a record: {r[:60]!r}")
        out.append((json.loads(head), json.loads(payload) if payload else None))
    return out


def canonical(records):
    """Records as comparable (header, payload) pairs.

    Drops what does not describe the footprint: the header `ticket` (list
    position carries order instead) and DOCHEAD's identity fields.
    """
    out = []
    for head, payload in parse_records(records):
        head = {k: v for k, v in head.items() if k != "ticket"}
        if head.get("type") == "DOCHEAD" and payload is not None:
            payload = {k: v for k, v in payload.items()
                       if k not in DOCHEAD_IDENTITY}
        out.append((head, payload))
    return out


def same_value(a, b):
    """JSON equality as the editor sees it: key order ignored, 1 == 1.0, but
    a boolean is never equal to a number (Python's True == 1 is not JSON's)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_value(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(map(same_value, a, b))
    return type(a) is type(b) and a == b


def record_diff(ours, theirs):
    """Differences between two record lists, compared `canonical`ly and in
    order.  Empty when they describe the same footprint."""
    a, b = canonical(ours), canonical(theirs)
    diffs = []
    if len(a) != len(b):
        diffs.append(f"record count {len(a)} != {len(b)}")
    for i, (x, y) in enumerate(zip(a, b)):
        if not (same_value(x[0], y[0]) and same_value(x[1], y[1])):
            diffs.append(f"record {i}: {x} != {y}")
    return diffs
