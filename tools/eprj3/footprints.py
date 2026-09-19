"""Footprint documents: the minimum a `DEVICE` needs to name a footprint.

EasyEDA Pro refuses to export a netlist while any placed part has no
`Footprint` -- its schematic DRC calls that a fatal error.  A `DEVICE` names its
footprint by the uuid of a `FOOTPRINT` document in the same project, so a
schematic cannot be netlist-checked until every device names one.

A footprint here is DOCHEAD, META, CANVAS and one PAD per pin, the record set of
an editor-saved SMD footprint minus its silkscreen and layer table.  One with a
body `outline` (a part that lies on the board beside its holes) also carries
the layer table rows it draws on, ACTIVE_LAYER, and one silkscreen POLY per
shape, in the order and form `v2footprint.convert` writes a library footprint.  The pads
are a land pattern for layout, NOT a checked one: `two_pad` is a generic chip
outline so the netlist can be read.  Real land patterns come from the parts'
LCSC footprints, bound in EasyEDA Pro.

Geometry is millimetres here; conversion happens once, in `units`.
"""
from dataclasses import dataclass

from .pcb import EDIT_VERSION
from .records import serialize_record
from .units import mm_to_pcb

#: The PCB top copper layer id, and the all-copper-layers id a drilled pad
#: sits on (the id the library's through-hole footprints use).
TOP_LAYER = 1
TOP_SILK = 3
MULTI_LAYER = 12
#: Silkscreen stroke for a body outline: JLC's minimum line width is 0.15 mm.
OUTLINE_STROKE_MM = 0.2
#: The stroke field of an unplated-hole FILL, as LCSC C165948's pegs carry it
#: (V2 FILL e55/e56: width 0.1, solid, a CIRCLE path, on layer 12).
HOLE_FILL_WIDTH = 0.1
#: The layer-table rows a footprint with an outline declares, exactly as
#: `v2footprint.convert` writes them from an LCSC footprint.
_LAYER_ROWS = (
    (TOP_LAYER, "TOP", "Top Layer", "#FF0000", "#7F0000"),
    (TOP_SILK, "TOP_SILK", "Top Silkscreen Layer", "#FFCC00", "#7F6600"),
    (MULTI_LAYER, "MULTI", "Multi-Layer", "#C0C0C0", "#606060"),
)
#: A 2.54 mm pin header's land: 1.0 mm drill, 1.7 mm pad -- the common
#: pattern for 0.64 mm square posts, whatever the header family.
HEADER_HOLE_MM = 1.0
HEADER_PAD_MM = 1.7


@dataclass(frozen=True)
class Outline:
    """One shape, in mm: ("CIRCLE", cx, cy, r) or a closed polygon [(x, y),
    ...].  On the silkscreen, or `hole=True`: an unplated hole, a solid FILL
    on the Multi-Layer -- the form EasyEDA's own library footprints give a
    connector's locating pegs (LCSC C165948, its two pegs)."""
    shape: tuple
    hole: bool = False

    def path(self):
        if self.shape and self.shape[0] == "CIRCLE":
            _, cx, cy, r = self.shape
            return ["CIRCLE", _u(cx), _u(cy), _u(r)]
        pts = list(self.shape) + [self.shape[0]]
        out = [_u(pts[0][0]), _u(pts[0][1]), "L"]
        for x, y in pts[1:]:
            out += [_u(x), _u(y)]
        return out


def _u(mm):
    return round(mm_to_pcb(mm), 4)


@dataclass(frozen=True)
class Pad:
    num: str            # must equal the symbol's pin number: that is the pin-to-pad map
    x_mm: float
    y_mm: float
    w_mm: float
    h_mm: float
    hole_mm: float | None = None    # None: surface mount; else a round drill
    shape: str = "RECT"             # RECT or ELLIPSE
    #: False: no stencil aperture over it (a pad a probe presses on).
    paste: bool = True


def two_pad(pitch_mm, pad_w_mm, pad_h_mm, nums=("1", "2")):
    """Two rectangular SMD pads, centred on the origin, `pitch_mm` apart."""
    half = pitch_mm / 2
    return (Pad(nums[0], -half, 0.0, pad_w_mm, pad_h_mm),
            Pad(nums[1], half, 0.0, pad_w_mm, pad_h_mm))


def header(pins, pitch_mm, rows=1):
    """A through-hole pin-header land pattern, centred on the origin: `pins`
    posts at `pitch_mm`, in one row, or in two rows numbered across (pin 1 and
    pin 2 share a column, odd pins in one row) as headers are.  Pin 1 is square."""
    cols = pins // rows
    if cols * rows != pins:
        raise ValueError(f"{pins} pins do not fill {rows} rows")
    out = []
    for i in range(pins):
        col, row = (i // rows, i % rows) if rows == 2 else (i, 0)
        x = (col - (cols - 1) / 2) * pitch_mm
        y = (row - (rows - 1) / 2) * pitch_mm
        out.append(Pad(str(i + 1), round(x, 4), round(y, 4), HEADER_PAD_MM,
                       HEADER_PAD_MM, HEADER_HOLE_MM, "RECT" if i == 0 else "ELLIPSE"))
    return tuple(out)


#: How far past a pad's own edge a paste aperture is pulled in when the pad
#: takes no paste: the aperture shrinks to nothing.  EasyEDA's library puts
#: -3937 mil (-100 mm) on EVERY pasted pad, so that figure means "the rule
#: default", not "none"; a pad's own custom value is used instead.
NO_PASTE_MARGIN_MM = 0.1


def _pad_payload(pad, z):
    hole = None if pad.hole_mm is None else {
        "holeType": "ROUND", "width": round(mm_to_pcb(pad.hole_mm), 4),
        "height": round(mm_to_pcb(pad.hole_mm), 4)}
    paste = None if pad.paste else round(
        mm_to_pcb(-(max(pad.w_mm, pad.h_mm) / 2 + NO_PASTE_MARGIN_MM)), 4)
    return {"groupId": 0, "netName": "",
            "layerId": TOP_LAYER if pad.hole_mm is None else MULTI_LAYER,
            "num": pad.num,
            "centerX": round(mm_to_pcb(pad.x_mm), 4),
            "centerY": round(mm_to_pcb(pad.y_mm), 4), "padAngle": 0,
            "hole": hole,
            "defaultPad": {"padType": pad.shape,
                           "width": round(mm_to_pcb(pad.w_mm), 4),
                           "height": round(mm_to_pcb(pad.h_mm), 4)},
            "specialPad": [], "padOffsetX": 0, "padOffsetY": 0,
            "relativeAngle": 0, "plated": True, "padType": "NORMAL",
            "topSolderExpansion": None, "bottomSolderExpansion": None,
            "topPasteExpansion": paste, "bottomPasteExpansion": paste,
            "locked": False, "zIndex": z, "connectMode": None,
            "spokeSpace": None, "spokeWidth": None, "spokeAngle": None,
            "padLen": 0}


def footprint_records(uuid, title, pads, *, client, epoch_ms,
                      edit_version=EDIT_VERSION, shared=frozenset(), outline=()):
    """The `FOOTPRINT` document for `pads`.  Pad numbers must be unique,
    except those in `shared`: several pads for one pin, which EasyEDA joins by
    number (a module's two mounting holes).  `outline`: silkscreen shapes."""
    nums = [p.num for p in pads]
    repeated = {n for n in nums if nums.count(n) > 1} - set(shared)
    if repeated:
        raise ValueError(f"{title}: pad numbers repeat: {sorted(repeated)}")
    head = serialize_record(
        {"type": "DOCHEAD"},
        payload={"docType": "FOOTPRINT", "client": client, "uuid": uuid,
                 "updateTime": epoch_ms, "version": str(epoch_ms),
                 "editVersion": edit_version, "user": {}})
    body = [("META", "META", {"title": title, "description": "", "tags": [],
                              "source": ""})]
    if outline:
        body += [("LAYER", f'["LAYER",{lid}]', {
            "layerType": ltype, "layerName": name, "use": True, "show": True,
            "locked": False, "activeColor": active, "activateTransparency": 1,
            "inactiveColor": inactive, "inactiveTransparency": 0.5})
            for lid, ltype, name, active, inactive in _LAYER_ROWS]
        body += [("ACTIVE_LAYER", "ACTIVE_LAYER", {"layerId": TOP_LAYER})]
    body += [("CANVAS", "CANVAS", {"originX": 0, "originY": 0, "unit": "mm",
                                   "gridXSize": 0.1, "gridYSize": 0.1,
                                   "gridType": "NONE", "multiGridType": "NONE",
                                   "highlightValue": 0.5})]
    body += [("PAD", f"e{n}", _pad_payload(p, n))
             for n, p in enumerate(pads, start=1)]
    body += [("FILL", f"e{n}", {
        "groupId": 0, "netName": "", "layerId": MULTI_LAYER, "width": HOLE_FILL_WIDTH,
        "fillStyle": "SOLID", "path": [o.path()], "locked": False, "zIndex": n,
        "isBridgingCopper": False, "networkList": [], "refs": []})
        if o.hole else ("POLY", f"e{n}", {
        "groupId": 0, "netName": "", "layerId": TOP_SILK,
        "width": _u(OUTLINE_STROKE_MM), "path": o.path(), "locked": False,
        "zIndex": n, "polyType": "NORMAL"})
        for n, o in enumerate(outline, start=len(pads) + 1)]
    return [head] + [serialize_record({"type": t, "ticket": n, "id": i},
                                      payload=pl)
                     for n, (t, i, pl) in enumerate(body, start=1)]
