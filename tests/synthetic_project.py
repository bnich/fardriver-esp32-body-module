"""A SYNTHETIC project of the design, for the tests that need an .eprj2 --
no file of the owner's is committed.

`_stream` writes the record stream of a project with the build's portrait
outline, the four M3 holes, one COMPONENT per netlist item dumped below the
outline (as the editor's import leaves them), and one FOOTPRINT per body
shape whose pads are named by pin, the way padmap.py names the real ones.
`template` is the empty project database it is written into.  Import the
fixtures by name (`from tests.synthetic_project import template, ...`).
"""
import sqlite3

import pytest

pytest.importorskip("cryptography")

from tests.test_eprj2 import OWNER, TEMPLATE_DDL  # noqa: E402,F401  (OWNER is re-exported)
from tools import board_params as bp, eprj2, layout_facts, netlist  # noqa: E402
from tools.model import is_cabled  # noqa: E402

MIL = layout_facts.MIL_PER_MM
#: The synthetic hole, mm: smaller than the smallest pad the fixture draws
#: (0.6 mm), so marking a footprint through-hole moves no pad box and only the
#: `hole` flag changes.
HOLE_MM = 0.6


# --- a synthetic project -----------------------------------------------------------
def _is_tht(it, d):
    """Does `it`'s synthetic footprint cross the board?  A connector does
    unless it is a bare land (`J408`, a Tag-Connect pad set); a part does when
    the netlist states its `lead_mm`.

    ⚠️ A MODEL of the real thing, and deliberately a conservative one: on the
    owner's saved project this predicate is right for every connector, and it
    misses the radial cans, the disc caps, the fuse clip and the 2 x 1 in.
    brick, whose library footprints have holes the netlist does not describe.
    (`U404`'s SOIC-8 carries a `hole` object of ZERO size on every pad -- a
    converted SMD land, not a drill; `envelope()` does not count it.)  Fewer
    pins cross here than really do, so a placement the
    fixture calls legal can still be illegal on the owner's footprints -- the
    check reads the FILE's pads (`envelope`), never this."""
    if it.kind == "CONN":
        return not d.connector(it.refdes).land
    return d.part(it.refdes).lead_mm is not None


def _pads_for(it, d):
    """[(pin, x mm, y mm, half w, half h)] in the footprint frame."""
    w, l = it.body
    if it.kind == "CONN":
        c = d.connector(it.refdes)
        pins = [cp.pin for cp in c.pins]
        pitch = c.pitch_mm
        rows = 2 if w < (len(pins) - 1) * pitch * 0.75 and len(pins) > 2 else 1
        cols = -(-len(pins) // rows)
        out = []
        for i, pin in enumerate(pins):
            col, row = (i // rows, i % rows) if rows == 2 else (i, 0)
            x = (col - (cols - 1) / 2) * pitch
            y = (row - (rows - 1) / 2) * pitch
            if c.side == "bottom" and c.interface and not is_cabled(c.interface):
                x = -x                    # a pair's upper half is generated pre-mirrored
            out.append((pin, x, y, 0.5, 0.5))
        return out
    p = d.part(it.refdes)
    pins = list(p.pins)
    if len(pins) <= 2:
        xs = [-(w / 2 - 0.6), (w / 2 - 0.6)][:len(pins)]
        return [(pin, x, 0.0, 0.45, min(0.6, l / 2)) for pin, x in zip(pins, xs)]
    out = []
    if it.kind == "MODULE":
        # a WROOM: pads down both sides and along the bottom, none at +Y
        n = len(pins)
        side = n // 3
        for i in range(side):
            out.append((pins[i], -w / 2 + 0.4, -l / 2 + 2 + i * (l - 6) / max(side - 1, 1), 0.4, 0.4))
        for i in range(side):
            out.append((pins[side + i], w / 2 - 0.4, -l / 2 + 2 + i * (l - 6) / max(side - 1, 1), 0.4, 0.4))
        rest = pins[2 * side:]
        for i, pin in enumerate(rest):
            out.append((pin, -w / 2 + 1 + i * (w - 2) / max(len(rest) - 1, 1), -l / 2 + 0.4, 0.4, 0.4))
        return out
    half = -(-len(pins) // 2)
    for i, pin in enumerate(pins):
        col = -1 if i < half else 1
        j = i if i < half else i - half
        n = half if col < 0 else len(pins) - half
        y = -l / 2 + 0.5 + j * (l - 1) / max(n - 1, 1)
        out.append((pin, col * (w / 2 - 0.3), y, 0.3, 0.3))
    return out


def _stream(d, ix, omit=()):
    """The V3 record stream of a synthetic project of the design.  `omit` is
    the refdes the PCB documents leave out -- a board is allowed to carry
    fewer parts than the netlist (the tool places what the PCB has), and that
    is how a project that CAN be fully placed is built out of a design that
    cannot."""
    recs = [({"type": "EDIT_HEAD"}, eprj2._compact({"uuid": OWNER}))]
    fps, fp_of = {}, {}
    for it in ix.items.values():
        key = (it.kind, it.body, tuple(sorted(it.pin_net)), _is_tht(it, d),
               it.refdes if it.kind == "CONN" else "")
        if key not in fps:
            fps[key] = f"fp{len(fps):04d}"
        fp_of[it.refdes] = fps[key]
    footprints = []
    for it in ix.items.values():
        uuid = fp_of[it.refdes]
        if any(u == uuid for u, _ in footprints):
            continue
        w, l = it.body
        body = [({"type": "DOCHEAD"}, eprj2._compact({"docType": "FOOTPRINT", "uuid": uuid})),
                ({"type": "META", "id": "META"}, eprj2._compact({"title": uuid}))]
        hole = ({"holeType": "ROUND", "width": round(HOLE_MM * MIL, 4),
                 "height": round(HOLE_MM * MIL, 4)} if _is_tht(it, d) else None)
        for i, (pin, x, y, hw, hh) in enumerate(_pads_for(it, d)):
            body.append(({"type": "PAD", "id": f"p{i}"}, eprj2._compact({
                "layerId": 1, "num": pin, "centerX": round(x * MIL, 4), "centerY": round(y * MIL, 4),
                "hole": hole, "defaultPad": {"padType": "RECT", "width": round(2 * hw * MIL, 4),
                                             "height": round(2 * hh * MIL, 4)}, "plated": True})))
        if w and l:
            x0, y0, x1, y1 = -w / 2 * MIL, -l / 2 * MIL, w / 2 * MIL, l / 2 * MIL
            body.append(({"type": "POLY", "id": "o"}, eprj2._compact({
                "layerId": 48, "width": 2, "polyType": "NORMAL",
                "path": [x0, y0, "L", x1, y0, x1, y1, x0, y1, x0, y0]})))
        footprints.append((uuid, body))
    for _, body in footprints:
        recs += body
    for bi, board in enumerate(bp.STACK_ORDER):
        recs.append(({"type": "DOCHEAD"}, eprj2._compact({"docType": "PCB", "uuid": f"pcb{bi}"})))
        recs.append(({"type": "META", "id": "META"}, eprj2._compact({"title": board})))
        recs.append(({"type": "POLY", "id": "outline"}, eprj2._compact({
            "layerId": 11, "width": 10, "polyType": "BOARD_OUTLINE",
            "path": ["R", 0, 9527.5591, 1647.2441, 9527.5591, 0, 0]})))
        for hi, (x, y) in enumerate(((3.5, 3.5), (38.34, 3.5), (3.5, 238.5), (38.34, 238.5))):
            recs.append(({"type": "PAD", "id": f"hole{hi}"}, eprj2._compact({
                "layerId": 12, "num": "", "centerX": round(x * MIL, 4), "centerY": round(y * MIL, 4),
                "hole": {"holeType": "ROUND", "width": 125.9843, "height": 125.9843},
                "defaultPad": {"padType": "ELLIPSE", "width": 125.9843, "height": 125.9843},
                "plated": False})))
        on_board = [x for x in ix.on(board) if x.refdes not in omit]
        for i, it in enumerate(sorted(on_board, key=lambda x: layout_facts._ref_key(x.refdes))):
            cid = f"c{bi}_{i}"
            recs.append(({"type": "COMPONENT", "id": cid}, eprj2._compact({
                "layerId": 1, "x": round((5 + (i % 8) * 4.5) * MIL, 4),
                "y": round(-(10 + (i // 8) * 6) * MIL, 4), "angle": 0, "attrs": {}, "locked": False})))
            recs.append(({"type": "ATTR", "id": cid + "d"}, eprj2._compact({
                "parentId": cid, "key": "Designator", "value": it.refdes, "layerId": 3,
                "x": round((5 + (i % 8) * 4.5) * MIL, 4), "y": round(-(8 + (i // 8) * 6) * MIL, 4)})))
            recs.append(({"type": "ATTR", "id": cid + "f"}, eprj2._compact({
                "parentId": cid, "key": "Footprint", "value": fp_of[it.refdes], "layerId": 3,
                "x": None, "y": None})))
    return eprj2.join(recs)


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    path = tmp_path_factory.mktemp("tpl") / "template.eprj2"
    db = sqlite3.connect(path)
    for sql in TEMPLATE_DDL:
        db.execute(sql)
    db.execute("insert into projects (uuid, archive, name, content, thumb, ticket, owner_uuid) "
               "values ('p', 0, 'T', '', '', 1, ?)", (OWNER,))
    db.execute("insert into db_versions values ('sqlite', 'test')")
    db.execute("insert into users values ('u', 'LCSC', 'LCSC')")
    db.commit()
    db.close()
    return path


@pytest.fixture(scope="module")
def design():
    return netlist.checked()


@pytest.fixture(scope="module")
def ix(design):
    return layout_facts.Index(design)
