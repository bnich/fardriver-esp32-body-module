"""Footprint documents: the minimum a `DEVICE` needs to name a footprint.

EasyEDA Pro refuses to export a netlist while any placed part has no
`Footprint` -- its schematic DRC calls that a fatal error.  A `DEVICE` names its
footprint by the uuid of a `FOOTPRINT` document in the same project, so a
schematic cannot be netlist-checked until every device names one.

A footprint here is DOCHEAD, META, CANVAS and one PAD per pin, the record set of
an editor-saved SMD footprint minus its silkscreen and layer table.  The pads
are a land pattern for layout, NOT a checked one: `two_pad` is a generic chip
outline so the netlist can be read.  Real land patterns come from the parts'
LCSC footprints, bound in EasyEDA Pro.

Geometry is millimetres here; conversion happens once, in `units`.
"""
from dataclasses import dataclass

from .pcb import EDIT_VERSION
from .records import serialize_record
from .units import mm_to_pcb

#: The PCB top copper layer id.
TOP_LAYER = 1


@dataclass(frozen=True)
class Pad:
    num: str            # must equal the symbol's pin number: that is the pin-to-pad map
    x_mm: float
    y_mm: float
    w_mm: float
    h_mm: float


def two_pad(pitch_mm, pad_w_mm, pad_h_mm, nums=("1", "2")):
    """Two rectangular SMD pads, centred on the origin, `pitch_mm` apart."""
    half = pitch_mm / 2
    return (Pad(nums[0], -half, 0.0, pad_w_mm, pad_h_mm),
            Pad(nums[1], half, 0.0, pad_w_mm, pad_h_mm))


def _pad_payload(pad, z):
    return {"groupId": 0, "netName": "", "layerId": TOP_LAYER, "num": pad.num,
            "centerX": round(mm_to_pcb(pad.x_mm), 4),
            "centerY": round(mm_to_pcb(pad.y_mm), 4), "padAngle": 0,
            "hole": None,
            "defaultPad": {"padType": "RECT",
                           "width": round(mm_to_pcb(pad.w_mm), 4),
                           "height": round(mm_to_pcb(pad.h_mm), 4)},
            "specialPad": [], "padOffsetX": 0, "padOffsetY": 0,
            "relativeAngle": 0, "plated": True, "padType": "NORMAL",
            "topSolderExpansion": None, "bottomSolderExpansion": None,
            "topPasteExpansion": None, "bottomPasteExpansion": None,
            "locked": False, "zIndex": z, "connectMode": None,
            "spokeSpace": None, "spokeWidth": None, "spokeAngle": None,
            "padLen": 0}


def footprint_records(uuid, title, pads, *, client, epoch_ms,
                      edit_version=EDIT_VERSION):
    """The `FOOTPRINT` document for `pads`.  Pad numbers must be unique."""
    nums = [p.num for p in pads]
    if len(set(nums)) != len(nums):
        raise ValueError(f"{title}: pad numbers repeat: {nums}")
    head = serialize_record(
        {"type": "DOCHEAD"},
        payload={"docType": "FOOTPRINT", "client": client, "uuid": uuid,
                 "updateTime": epoch_ms, "version": str(epoch_ms),
                 "editVersion": edit_version, "user": {}})
    body = [("META", "META", {"title": title, "description": "", "tags": [],
                              "source": ""}),
            ("CANVAS", "CANVAS", {"originX": 0, "originY": 0, "unit": "mm",
                                  "gridXSize": 0.1, "gridYSize": 0.1,
                                  "gridType": "NONE", "multiGridType": "NONE",
                                  "highlightValue": 0.5})]
    body += [("PAD", f"e{n}", _pad_payload(p, n))
             for n, p in enumerate(pads, start=1)]
    return [head] + [serialize_record({"type": t, "ticket": n, "id": i},
                                      payload=pl)
                     for n, (t, i, pl) in enumerate(body, start=1)]
