"""EasyEDA library footprints for the parts, and fitting them to our pins.

The footprints come from EasyEDA's LCSC library through ~/tools/lcsc-search,
which caches every answer: after one online build, builds run offline.  The
library serves footprints only as V2; `eprj3/v2footprint.py` converts them,
and `fit()` renames each pad to the netlist pin it carries (tools/padmap.py).

No library data is kept in this repository: a build without lcsc-search, or
with REVV1_NO_LIBRARY set (the test suite does), binds no library footprint
and says so.
"""
import json
import os
import re
import sys
from dataclasses import replace
from pathlib import Path

from . import padmap
from .eprj3.records import serialize_record

TOOL = Path(os.environ.get("LCSC_SEARCH_HOME", Path.home() / "tools" / "lcsc-search"))

#: Interfaces whose land pattern is TWO rows: a signal bus that puts a ground
#: beside every signal carries twice its signal count, numbered across the rows
#: (pin 1 signal, pin 2 its ground).  A power bus is one row.
DUAL_ROW_INTERFACES = frozenset({"STACK", "CTRL"})


def allegro_safe(title):
    """A footprint name an Allegro netlist accepts.  EasyEDA's netlist export
    (.tel) is Allegro's format, which rejects '; ! .' and spaces -- the editor
    warns and names the parts -- and library names also carry non-ASCII text.
    Everything outside letters, digits and `_ - ( ) + = , #` becomes '_'."""
    safe = re.sub(r"[^A-Za-z0-9_\-()+=,#]", "_", title or "")
    return re.sub(r"_+", "_", safe).strip("_") or "FOOTPRINT"


class Library:
    """code -> (footprint title, V2 text), or None when the library has none."""

    def __init__(self, service):
        self._svc = service

    def footprint(self, code):
        dev = self._svc.footprint(code)
        if dev is None or not dev.get("footprint_uuid"):
            return None
        doc = self._svc.document(dev["footprint_uuid"])
        if doc is None or doc.get("format") != "v2":
            return None
        # The document's own name (ASCII, e.g. sot-23-3_l2.9-w1.3-p1.90) over
        # LCSC's category label, which can be Chinese ('弯插,P=2mm').
        return doc.get("title") or dev["footprint_name"] or dev["title"], doc["data"]


class FakeLibrary(Library):
    """For tests: {code: (title, V2 text)}."""

    def __init__(self, table):
        self._table = dict(table)

    def footprint(self, code):
        return self._table.get(code)


def open_library():
    """The library, or None when it cannot be reached from here."""
    if os.environ.get("REVV1_NO_LIBRARY"):
        return None
    if not (TOOL / "lcsc_search").is_dir():
        return None
    sys.path.insert(0, str(TOOL))
    try:
        from lcsc_search import Service
    except ImportError:
        return None
    return Library(Service())


def _missing(nums, cols):
    """The positions a keyed body leaves empty, as JST writes them: '3' for a
    five-wide body carrying contacts 1, 2, 4 and 5."""
    have = {int(n) for n in nums}
    return "-".join(str(i) for i in range(1, cols + 1) if i not in have)


def generated(thing):
    """(title, pads, shared pad numbers, outline) for a footprint generated
    here rather than taken from the library, or None when there is no
    generator for `thing` yet.

    - The parts with no library device, drawn from their datasheets
      (`drawn_footprints`), and the connectors that are copper only (a
      Tag-Connect land).
    - The inter-board connectors, EVERY one of them, whether or not an LCSC
      part is chosen for it: the upper half of a mated pair has to be
      pre-mirrored (`...-UNDER`) and no library footprint is, and the one
      cabled power connector is a 5-wide body with its third post left out as
      a key, which a 1x4 library land would quietly fill in."""
    from . import drawn_footprints
    from .eprj3 import footprints
    from .model import Connector, Part, is_cabled
    if isinstance(thing, Part) and thing.mpn in drawn_footprints.BY_MPN:
        d = drawn_footprints.BY_MPN[thing.mpn]
        return d.title, d.pads, d.shared, d.outline
    if isinstance(thing, Connector) and thing.land:
        d = drawn_footprints.LANDS[thing.land]
        return d.title, d.pads, d.shared, d.outline
    if isinstance(thing, Connector) and thing.interface is not None:
        n = len(thing.pins)
        rows = 2 if thing.interface in DUAL_ROW_INTERFACES else 1
        nums = tuple(cp.pin for cp in thing.pins)
        keyed = rows == 1 and nums != tuple(str(i + 1) for i in range(n))
        cols = max(int(x) for x in nums) if keyed else n // rows
        title = (f"HDR-TH_{rows}X{cols}({cols}-{_missing(nums, cols)})"
                 f"-P{thing.pitch_mm:g}MM" if keyed else
                 f"HDR-TH_{rows}X{cols}-P{thing.pitch_mm:g}MM").replace(".", "_")
        pads = footprints.header(n, thing.pitch_mm, rows=rows,
                                 nums=nums if keyed else None,
                                 hole_mm=thing.hole_mm)
        if thing.side == "bottom" and not is_cabled(thing.interface):
            # MATED PAIRS ONLY.  The upper half of a pair hangs under its board,
            # and the editor mirrors a part placed there.  Drawn mirrored here,
            # the flip puts every pad back over its MATE's (a 180° turn after
            # the flip covers an editor that mirrors the other axis).  Drawn as
            # the lower half is, no turn can align a dual row: its rows swap,
            # and STACK's signals land on the ground row.
            # A cabled crossing has no mate to line up with -- the loom carries
            # the orientation -- so pre-mirroring it would only move its pads
            # away from where the netlist says they are.
            pads = tuple(replace(p, x_mm=-p.x_mm) for p in pads)
            title += "-UNDER"
        return title, pads, frozenset(), ()
    return None


def _parse(rec):
    head, _, payload = rec.partition("||")
    return json.loads(head), (json.loads(payload) if payload else None)


def fit(records, item):
    """Library footprint records -> the same footprint with its pads renamed
    to `item`'s pins.  Refuses a pad the map does not account for: an unmapped
    pad is how a wrong footprint gets through."""
    mapping = padmap.pad_map(item)
    out = []
    for head, payload in (_parse(r) for r in records):
        if head["type"] == "PAD":
            num = str(payload["num"])
            if num not in mapping:
                raise ValueError(f"{item.refdes}: library pad {num!r} is in no pad "
                                 f"map (the map covers {sorted(mapping)})")
            if mapping[num] is not None:
                payload = {**payload, "num": mapping[num]}
        out.append(serialize_record(head, payload))
    return out


def pads_of(records):
    """The pad numbers a footprint's records carry."""
    return [str(json.loads(r.partition("||")[2])["num"])
            for r in records if json.loads(r.partition("||")[0])["type"] == "PAD"]
