"""tools/place.py: every check proven to fire on a placement that breaks it,
the engine proven to leave a clean one, and the writer proven to round-trip.

The project under test is SYNTHETIC -- no file of the owner's is committed.
`synthetic_project` writes an .eprj2 with the build's portrait outline, the
four M3 holes, one COMPONENT per netlist item dumped below the outline (as the
editor's import leaves them), and one FOOTPRINT per body shape whose pads are
named by pin, the way padmap.py names the real ones.  Set
REVV1_PLACE_PROJECT to a saved project to run the same tests on it.
"""
import json
import os
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("cryptography")

from tests.test_eprj2 import OWNER, TEMPLATE_DDL  # noqa: E402
from tools import board_params as bp, build_project, eprj2, netlist, place  # noqa: E402
from tools.model import Net, is_cabled  # noqa: E402

MIL = place.MIL_PER_MM
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
        for i, it in enumerate(sorted(on_board, key=lambda x: place._ref_key(x.refdes))):
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
    return place.Index(design)


@pytest.fixture(scope="module")
def synthetic_project(tmp_path_factory, template, design, ix):
    """Path of the synthetic .eprj2 (or the saved one REVV1_PLACE_PROJECT names)."""
    env = os.environ.get("REVV1_PLACE_PROJECT")
    if env:
        return Path(env)
    path = tmp_path_factory.mktemp("proj") / "revv1-module.eprj2"
    eprj2.write(template, path, _stream(design, ix), {"boards": {}}, "revv1-module", owner=OWNER)
    return path


@pytest.fixture(scope="module")
def placed(synthetic_project, ix):
    """(project, the engine's placement of it) -- computed once."""
    project = place.load(synthetic_project)
    return project, place.stack(project, ix)


#: The three the engine cannot seat on the real design, and why each one has
#: nowhere to go.  `NO_ROOM` is not a list of awkward parts: it is this run's
#: finding, proven by `test_the_engine_leaves_what_has_no_room_unplaced`.
NO_ROOM = {
    "J314": "OUTPUTS' face row is ONE strip for both faces -- a terminal's pins cross "
            "the board -- and it is 259.7 mm of a 228 mm edge",
    "U201": "the 37.2 mm brick cannot stand behind a 9.5 mm row on a 41.84 mm board, and "
            "its 10 pins may not come up inside the row's bodies",
    "J311": "its four pins come up through the top face, so the feed may not sit under "
            "the driver line: with the two above gone the packer seats it 15.4 mm from "
            "the drivers' centroid, over BUS_REACH (check 11), and on the owner's own "
            "footprints 17.5 mm",
    "J202": "the other half of the PWR-OUT loom: with no J311 there is no loom",
}


@pytest.fixture(scope="module")
def placeable_project(tmp_path_factory, template, design, ix):
    """The same synthetic project WITHOUT the three parts of `NO_ROOM`: a
    board may carry fewer parts than the netlist, and the tool places what the
    PCB has.

    ⛔ A FIXTURE, and the omission is the finding: no complete placement of
    this design exists today. It is here because "the engine leaves a CLEAN
    placement" and "the engine refuses HONESTLY" are two different claims and
    both have to be proven -- a suite with only the second would pass on an
    engine that had stopped placing anything at all."""
    path = tmp_path_factory.mktemp("fits") / "revv1-module.eprj2"
    eprj2.write(template, path, _stream(design, ix, omit=tuple(NO_ROOM)), {"boards": {}},
                "revv1-module", owner=OWNER)
    return path


@pytest.fixture(scope="module")
def placeable_placed(placeable_project, ix):
    project = place.load(placeable_project)
    return project, place.stack(project, ix)


def clone(pl):
    out = place.Placement(pl.project, pl.ix)
    out.boards = {b: dict(items) for b, items in pl.boards.items()}
    return out


def moved(pl, ref, du=0.0, dv=0.0, layer=None, angle=None, height=None):
    """`pl` with `ref` shifted, re-layered or turned; its box follows."""
    out = clone(pl)
    p = out.get(ref)
    frame = out.frame(p.board)
    u, v = p.u + du, p.v + dv
    layer = p.layer if layer is None else layer
    angle = p.angle if angle is None else angle
    box = place.placed_box(p.env, frame, u, v, angle, layer == 2)
    out.boards[p.board][ref] = replace(p, u=u, v=v, layer=layer, angle=angle, box=box,
                                       height=p.height if height is None else height)
    return out


def as_tht(pl, ref):
    """`pl` with every pad of `ref` through-hole -- the flag `envelope()` reads
    from a PAD record's `hole`.  It changes no box: the synthetic hole is
    smaller than the pad around it."""
    out = clone(pl)
    p = out.get(ref)
    env = replace(p.env, pads=tuple(pad[:5] + (True,) for pad in p.env.pads))
    out.boards[p.board][ref] = replace(p, env=env)
    return out


def numbers(problems):
    return {int(p.split()[0]) for p in problems}


def lines(problems, n):
    return [p for p in problems if p.startswith(f"{n} ")]


# --- the frame ----------------------------------------------------------------------
def test_portrait_frame_is_a_rotation_and_round_trips():
    f = place.Frame(242.0, 41.84, True)
    assert f.to_file(0, 0) == (0, 242.0)                 # u = 0 is the file's top
    assert f.to_file(242.0, 41.84) == (41.84, 0)
    assert f.to_board(*f.to_file(12.5, 7.25)) == pytest.approx((12.5, 7.25))
    assert f.file_angle(0) == 270 and f.board_angle(270) == 0
    # a proper rotation: the direction of +u in the file is -Y, of +v is +X
    assert f.dir_to_board(1, 0) == (0, 1) and f.dir_to_board(0, -1) == (1, 0)
    g = place.Frame(242.0, 41.84, False)
    assert g.to_file(3, 4) == (3, 4) and g.file_angle(90) == 90


def test_outline_frame_reads_the_builds_portrait_outline(placed):
    project, _ = placed
    frame = project.pcbs["LOGIC"].frame
    assert frame.portrait and frame.length == pytest.approx(242.0) and frame.width == pytest.approx(41.84)
    assert len(frame.holes) == 4
    assert frame.holes[0] == pytest.approx((3.5, 3.5), abs=0.01)


def test_rotation_convention_matches_the_editor():
    """CCW angle; a bottom part is rotated then mirrored about X -- read off
    the editor's own example (a track lands on Q1's pads only under CCW, and
    on CARD1's only when the mirror follows the turn)."""
    env = place.Envelope(-1, -1, 1, 1, (("1", 1.0, 0.0, 0.1, 0.1, False),))
    f = place.Frame(10.0, 10.0, False)
    assert place.placed_pads(env, f, 0, 0, 90, False)[0][1:] == pytest.approx((0.0, 1.0))
    assert place.placed_pads(env, f, 0, 0, 90, True)[0][1:] == pytest.approx((0.0, 1.0))
    assert place.placed_pads(env, f, 0, 0, 0, True)[0][1:] == pytest.approx((-1.0, 0.0))


def test_envelope_unions_pads_outline_and_the_stated_body():
    recs = [({"type": "PAD"}, json.dumps({"num": "1", "centerX": -39.37, "centerY": 0,
                                         "defaultPad": {"width": 55.5, "height": 53.15}})),
            ({"type": "PAD"}, json.dumps({"num": "2", "centerX": 39.37, "centerY": 0,
                                         "defaultPad": {"width": 55.5, "height": 53.15}})),
            ({"type": "POLY"}, json.dumps({"layerId": 3, "path": [71.3, -35.6, "ARC", 90, 77.3, -29.6]}))]
    e = place.envelope(recs, (2.0, 1.25))
    assert e.x1 == pytest.approx(77.3 / MIL, abs=0.01)         # the silk, wider than the body
    assert e.y0 == pytest.approx(-35.6 / MIL, abs=0.01)        # the arc's start, below the pads
    assert e.y1 == pytest.approx(53.15 / 2 / MIL, abs=0.01)    # the pads, above the body's 0.625
    assert len(e.pads) == 2 and e.pads[0][0] == "1"
    # no `hole` record: surface mount, and nothing of it reaches the far face
    assert e.pads[0][5] is False and not e.tht
    holed = [(h, json.dumps({**json.loads(p), "hole": {"width": 30, "height": 30}}))
             for h, p in recs if h["type"] == "PAD"]
    assert place.envelope(holed, (2.0, 1.25)).tht
    # a brick drawn upright: the stated body is laid along the drawn long axis
    tall = [({"type": "PAD"}, json.dumps({"num": "a", "centerX": 0, "centerY": -900,
                                         "defaultPad": {"width": 60, "height": 60}})),
            ({"type": "PAD"}, json.dumps({"num": "b", "centerX": 0, "centerY": 900,
                                         "defaultPad": {"width": 60, "height": 60}}))]
    e = place.envelope(tall, (50.8, 25.4))
    assert e.x1 - e.x0 == pytest.approx(25.4) and e.y1 - e.y0 == pytest.approx(50.8)


# --- the design, read for placement ------------------------------------------------
def test_bands_follow_the_copper(ix):
    b = place.bands(ix, "LOGIC")
    assert b["J402"] == 1 and b["J406"] == 4 and b["U401"] == 4
    assert b["D401"] == 2 and b["R402"] == 2          # TVS and series R on J402's nets
    assert b["U402"] == 3 and b["U403"] == 3          # the expanders, the second by part number
    assert b["U404"] == 4 and b["U405"] == 4          # the CAN transceiver and the LDO, with the S3
    o = place.bands(ix, "OUTPUTS")
    assert o["J314"] == 1 and o["J311"] == 4 and o["U301"] == 3 and o["D307"] == 2
    p = place.bands(ix, "POWER")
    assert p["J101"] == 1 and p["U201"] == 3 and p["J202"] == 4 and p["D101"] == 2


def test_power_classes_come_from_driver_pins_not_names(design):
    cls = place.power_classes(design)
    assert cls["PWR12"] == {"V12"}
    assert "AUX5V_1" in cls["CH5"] and "TAIL_STOP" in cls["CH12"]
    assert "KEY_SENSE_PIN" in cls["SENSE"] and "TWAI_TX" not in cls["SENSE"]
    # a net NAMED like a 5 V channel, with no TPS2553 OUT pin on it, is not one
    fake = design.with_net(Net("AUX5V_9", (("R401", "1"), ("U402", "GPA0")), "3V3"))
    assert "AUX5V_9" not in place.power_classes(fake)["CH5"]
    real_faults = [n.name for n in design.nets if n.name.startswith("AUX5V_") and "FAULT" in n.name]
    assert real_faults and not (set(real_faults) & cls["CH5"])


def test_decouplers_are_100nF_on_a_rail_and_ground(ix):
    dec = place.decouplers(ix, "LOGIC")
    assert dec["C414"] == "V3P3"
    assert "C412" not in dec                          # 100 nF on EN + GND: not a rail
    assert "C437" not in dec                          # the ADC filter


# --- the engine ---------------------------------------------------------------------
def test_the_engine_places_every_part_and_the_checks_pass(placeable_placed, ix):
    """A COMPLETE placement is still reachable: on a project without the four
    of `NO_ROOM`, every part is seated and every check passes."""
    project, pl = placeable_placed
    for board in bp.STACK_ORDER:
        assert set(pl.boards[board]) == set(project.pcbs[board].components)
        assert not any(p.unplaced for p in pl.boards[board].values())
    assert place.check(pl, ix) == []


def test_the_engine_leaves_what_has_no_room_unplaced(placed, ix):
    """The whole design. Both faces share one strip of the connector edge, so
    OUTPUTS' row is 259.7 mm of the 228 mm between the M3 corners, and the
    37.2 mm brick cannot stand behind a 9.5 mm row on a 41.84 mm board.
    Neither is squeezed into somewhere illegal: each keeps the reason it
    could not be placed, every part is still accounted for, and everything
    the engine DID place passes every check."""
    project, pl = placed
    for board in bp.STACK_ORDER:
        assert set(pl.boards[board]) == set(project.pcbs[board].components)
    assert not any(p.unplaced for p in pl.boards["LOGIC"].values())
    assert {r for r, p in pl.boards["OUTPUTS"].items() if p.unplaced} == {"J314"}
    assert {r for r, p in pl.boards["POWER"].items() if p.unplaced} == {"U201"}
    assert "228.0 mm" in pl.get("J314").reason and "both faces" in pl.get("J314").reason
    assert pl.get("U201").reason == "UNPLACED: no free slot"
    assert place.check(pl, ix) == []


def test_an_unplaced_part_is_reported_not_measured(placed, ix):
    """A part with no position is named once, with its reason. Measuring it
    where the file happened to leave it would report the import's coordinates
    as if they were this run's proposal -- `J314` sits below the outline."""
    _, pl = placed
    assert pl.get("J314").box.v1 > 41.84                      # where the import left it
    assert not any("J314" in s for s in place.check(pl, ix))
    assert "J314" not in pl.placed("OUTPUTS")


def test_bottom_parts_come_from_the_netlists_side(placed, ix):
    _, pl = placed
    for board in bp.STACK_ORDER:
        under = {it.refdes for it in ix.on(board) if it.side == "bottom"}
        assert {r for r, p in pl.boards[board].items() if p.layer == 2} == under
    assert {r for b in pl.boards.values() for r, p in b.items() if p.layer == 2} == \
        {"U201", "U202", "J314", "J311", "J312", "J406", "J407"}


def test_the_row_is_at_the_face_in_edge_budget_order(placed):
    _, pl = placed
    row = [pl.boards["LOGIC"][r] for r in ("J402", "J403", "J306", "J409", "J410")]
    assert all(abs(p.box.v0) < 0.05 for p in row)
    assert all(a.box.u1 + place.board_fit.HEADER_GAP == pytest.approx(b.box.u0, abs=0.01)
               for a, b in zip(row, row[1:]))
    total = row[-1].box.u1 - row[0].box.u0
    assert row[0].box.u0 == pytest.approx((242.0 - total) / 2, abs=0.01)     # centred


def test_anchor_left_and_right_move_the_row(synthetic_project, ix):
    project = place.load(synthetic_project)
    left = place.stack(project, ix, anchor="left").boards["LOGIC"]["J402"].box.u0
    right = place.stack(project, ix, anchor="right").boards["LOGIC"]["J410"].box.u1
    assert left == pytest.approx(2 * place.M3_KEEPOUT, abs=0.01)
    assert right == pytest.approx(242.0 - 2 * place.M3_KEEPOUT, abs=0.01)


def test_mates_take_their_lower_halfs_position_pin_for_pin(placed):
    _, pl = placed
    for lower, upper in (("J307", "J407"), ("J308", "J406")):
        lo, up = pl.get(lower), pl.get(upper)
        assert (up.u, up.v) == pytest.approx((lo.u, lo.v), abs=1e-9)
        assert up.layer == 2 and lo.layer == 1


def test_keep_holds_a_part_where_the_file_has_it(synthetic_project, ix):
    project = place.load(synthetic_project)
    pl = place.stack(project, ix, keep=["R402"])
    comp = project.pcbs["LOGIC"].components["R402"]
    u, v = project.pcbs["LOGIC"].frame.to_board(comp.x / MIL, comp.y / MIL)
    p = pl.boards["LOGIC"]["R402"]
    assert (p.u, p.v) == pytest.approx((u, v)) and p.kept


def test_from_file_reads_the_saved_positions(synthetic_project, ix):
    project = place.load(synthetic_project)
    pl = place.Placement.from_file(project, ix)
    p = pl.boards["POWER"]["J101"]
    assert p.reason == "as saved" and p.band == 1
    # the import dumps parts below the outline: the raw save fails the checks
    assert 1 in numbers(place.check(pl, ix))


# --- the checks: each proven to fire ---------------------------------------------------
def test_1_outline_and_corners(placed, ix):
    _, pl = placed
    p = pl.get("R402")
    off = moved(pl, "R402", du=-(p.box.u0 + 5))
    assert numbers(place.check(off, ix)) >= {1}
    assert any(s.startswith("1 outline: LOGIC R402") for s in place.check(off, ix))
    corner = moved(pl, "R402", du=3.5 - p.box.cu, dv=3.5 - p.box.cv)
    assert any(s.startswith("1 corner: LOGIC R402") for s in place.check(corner, ix))


def test_2_same_face_clearance(placed, ix):
    _, pl = placed
    a, b = pl.get("R402"), pl.get("R403")           # both Band 2, both on top
    tight = moved(pl, "R403", du=(a.box.u1 + 1.0 - b.box.u0), dv=(a.box.v0 - b.box.v0))
    got = place.check(tight, ix)
    assert any(s.startswith("2 clearance: LOGIC") and "R402" in s and "R403" in s for s in got)


def test_3_layers_follow_the_netlist(placed, ix):
    _, pl = placed
    flipped = moved(pl, "J311", layer=1)
    assert any(s.startswith("3 layer: OUTPUTS J311") and "under" in s for s in place.check(flipped, ix))
    flipped = moved(pl, "R402", layer=2)
    assert any(s.startswith("3 layer: LOGIC R402") for s in place.check(flipped, ix))


def test_4_mates_coincide_in_position_and_by_net(placed, ix):
    _, pl = placed
    shifted = moved(pl, "J406", du=1.0)
    assert any(s.startswith("4 mate: J406") and "not over J308" in s for s in place.check(shifted, ix))
    turned = moved(pl, "J406", angle=(pl.get("J406").angle + 90) % 360)
    assert any(s.startswith("4 mate: J406 over J308") and "different net" in s
               for s in place.check(turned, ix))


def test_5_cross_board_keepout_under_j311(placed, ix):
    _, pl = placed
    j311, l101 = pl.get("J311"), pl.get("L101")
    under = moved(pl, "L101", du=j311.box.cu - l101.box.cu, dv=j311.box.cv - l101.box.cv)
    got = place.check(under, ix)
    assert any(s.startswith("5 keep-out: POWER L101") and "J311" in s for s in got)
    limit = bp.layer_gaps(ix.d)[1].gap_mm - ix.items["J311"].height - bp.CLEARANCE
    assert f"limit there is {limit:.1f}" in " ".join(got)


def test_6_row_at_the_face_in_order_inside_the_ends(placed, ix):
    _, pl = placed
    lifted = moved(pl, "J301", dv=3.0)
    assert any(s.startswith("6 row: OUTPUTS J301") and "v = 0" in s for s in place.check(lifted, ix))
    a, b = pl.get("J301"), pl.get("J302")
    swapped = moved(moved(pl, "J301", du=b.box.u0 - a.box.u0), "J302", du=a.box.u0 - b.box.u0)
    assert any(s.startswith("6 row: OUTPUTS") and "is not after" in s for s in place.check(swapped, ix))
    past = moved(pl, "J313", du=242.0 - pl.get("J313").box.u1)
    assert any(s.startswith("6 row: OUTPUTS J313") and "past the board end" in s
               for s in place.check(past, ix))


def test_7_hv_copper_off_the_edge_and_clear_of_lv(placed, ix):
    _, pl = placed
    c201 = pl.get("C201")
    frame = pl.frame("POWER")
    zone = c201.hv_zones(ix, frame)[0]
    to_edge = moved(pl, "C201", dv=(41.84 - 1.0) - zone.v1)
    got = place.check(to_edge, ix)
    assert any(s.startswith("7 HV edge: POWER C201") for s in got)
    r336 = pl.get("R336")
    close = moved(pl, "R336", du=zone.u1 + 0.5 - r336.box.u0, dv=zone.cv - r336.box.cv)
    got = place.check(close, ix)
    assert any(s.startswith("7 HV clearance: POWER R336") and "C201" in s for s in got)


def test_8_antenna_end_at_the_back_edge_zone_clear(placed, ix):
    _, pl = placed
    turned = moved(pl, "U401", angle=180)
    assert any(s.startswith("8 antenna") and "connector-face" in s for s in place.check(turned, ix))
    u401 = pl.get("U401")
    back = moved(pl, "U401", dv=-6.0)
    got = place.check(back, ix)
    assert any(s.startswith("8 antenna: LOGIC U401") and "back edge" in s for s in got)
    r = pl.get("R402")
    inzone = moved(back, "R402", du=u401.box.cu - r.box.cu, dv=(u401.box.v1 - 6.0 + 2.0) - r.box.v0)
    assert any(s.startswith("8 antenna: LOGIC R402 stands in") for s in place.check(inzone, ix))


def test_9_no_part_taller_than_its_faces_gap(placed, ix):
    _, pl = placed
    tall = moved(pl, "R402", height=50.0)
    assert any(s.startswith("9 height: LOGIC R402") for s in place.check(tall, ix))


def test_10_channel_between_bands(placed, ix):
    _, pl = placed
    j402, r = pl.get("J402"), pl.get("R402")
    behind = moved(pl, "R402", du=j402.box.cu - r.box.cu, dv=(j402.box.v1 + 1.0) - r.box.v0)
    got = place.check(behind, ix)
    assert any(s.startswith("10 channel: LOGIC") and "R402" in s and "J402" in s for s in got)
    u401 = pl.get("U401")
    front = moved(pl, "R402", du=u401.box.cu - r.box.cu, dv=(u401.box.v0 - 2.5 - r.box.d) - r.box.v0)
    got = place.check(front, ix)
    assert any(s.startswith("10 channel: LOGIC") and "U401" in s and "3 mm" in s for s in got)


def test_11_v12_bus_line_and_feed(placed, ix):
    _, pl = placed
    j311 = pl.get("J311")
    far = pl
    for r in ("U301", "U302", "U303", "U305"):
        far = moved(far, r, du=(j311.box.cu + 40.0) - pl.get(r).box.cu)
    assert any(s.startswith("11 V12 bus") and "over 15" in s for s in place.check(far, ix))
    turned = moved(pl, "U302", angle=(pl.get("U302").angle + 90) % 360)
    assert any(s.startswith("11 V12 bus") and "2 ways" in s for s in place.check(turned, ix))


def test_12_a_long_through_hole_row_across_the_board_cuts_the_plane(placed, ix):
    _, pl = placed
    across = moved(pl, "J308", angle=90, du=0, dv=20.0 - pl.get("J308").box.cv)
    assert any(s.startswith("12 plane: OUTPUTS J308") for s in place.check(across, ix))


def test_13_hv_region_one_group_no_lv_enclosed(placed, ix):
    _, pl = placed
    c201 = pl.get("C201")
    apart = moved(pl, "C201", du=(238.0 - c201.box.u1))
    got = place.check(apart, ix)
    assert any(s.startswith("13 HV region: POWER's 84 V parts form") for s in got)
    # an LV part with 84 V copper on all four sides: four two-pin HV
    # resistors round it, left and right along u, front and back turned 90
    r336 = pl.get("R336")
    boxed = clone(pl)
    walls = [it.refdes for it in ix.on("POWER") if it.kind == "R"
             and all(n in ix.hv["POWER"] for n in it.nets)][:4]
    assert len(walls) == 4
    for ref, (du, dv, ang) in zip(walls, ((-5, 0, 0), (5, 0, 0), (0, -5, 90), (0, 5, 90))):
        q = pl.get(ref)
        boxed = moved(boxed, ref, du=122 + du - q.box.cu, dv=20 + dv - q.box.cv, angle=ang)
    boxed = moved(boxed, "R336", du=122 - r336.box.cu, dv=20 - r336.box.cv, angle=0)
    got = place.check(boxed, ix)
    assert any(s.startswith("13 HV region: POWER R336") and "inside" in s for s in got), got


def test_14_can_brake_and_adc_adjacency(placed, ix):
    _, pl = placed
    far = moved(pl, "U404", du=25.0)
    assert any(s.startswith("14 CAN: LOGIC U404") for s in place.check(far, ix))
    j306, u401, r434 = pl.get("J306"), pl.get("U401"), pl.get("R434")
    mid_u, mid_v = (j306.box.cu + u401.box.cu) / 2, (j306.box.cv + u401.box.cv) / 2
    on_path = moved(pl, "R434", du=mid_u - r434.box.cu, dv=mid_v - r434.box.cv)
    assert any(s.startswith("14 brake: LOGIC R434") for s in place.check(on_path, ix))
    away = moved(pl, "R476", du=-30.0)
    assert any(s.startswith("14 ADC: LOGIC R476") and "KEY_SENSE_PIN" in s for s in place.check(away, ix))


def test_15_decouplers_on_their_ic(placed, ix):
    _, pl = placed
    away = moved(pl, "C414", dv=-12.0)
    got = place.check(away, ix)
    assert any(s.startswith("15 decoupling: LOGIC C414") and "V3P3" in s for s in got)


def test_16_programming_land_on_top_with_clear_ends(placed, ix):
    _, pl = placed
    j408, r = pl.get("J408"), pl.get("R402")
    zone = place.service_zones(j408.box)[1]
    at_end = moved(pl, "R402", du=zone.cu - r.box.cu, dv=zone.cv - r.box.cv)
    got = place.check(at_end, ix)
    assert any(s.startswith("16 service: LOGIC R402") and "J408" in s for s in got)
    under = moved(pl, "J408", layer=2)
    assert any(s.startswith("16 service: LOGIC J408") and "layer 2" in s for s in place.check(under, ix))


def test_17_two_through_hole_parts_on_opposite_faces(placed, ix):
    """The first placement's OUTPUTS: `J312`'s 24 pins inside `J308`'s 58.
    Both are through-hole, so each one's pads are inside the other's body and
    the message says so, naming both parts and the layer each is on."""
    _, pl = placed
    j308, j312 = pl.get("J308"), pl.get("J312")
    assert j308.tht and j312.tht and j308.layer == 1 and j312.layer == 2
    inside = moved(pl, "J312", du=j308.box.cu - j312.box.cu, dv=j308.box.cv - j312.box.cv)
    got = lines(place.check(inside, ix), 17)
    assert any("J308 (layer 1)" in s and "J312 (layer 2)" in s
               and "both through-hole" in s for s in got), got


def test_17_a_through_hole_pad_under_a_surface_mount_body(placed, ix):
    """The first placement's `J311`: a VH wafer under the board, its pins
    coming up through the top face inside `U302`'s body. `U302` is surface
    mount, so only one direction fires, and it names the pins' owner."""
    _, pl = placed
    u302, j311 = pl.get("U302"), pl.get("J311")
    assert j311.tht and not u302.tht
    under = moved(pl, "J311", du=u302.box.cu - j311.box.cu, dv=u302.box.cv - j311.box.cv)
    got = lines(place.check(under, ix), 17)
    assert any(s.startswith("17 through-hole: OUTPUTS J311's pins (layer 2, through-hole)")
               and "U302's body (layer 1)" in s for s in got), got


def test_17_a_header_under_the_row_on_the_other_face(placed, ix):
    """A through-hole header hanging under the board, under a through-hole
    terminal standing on top of it: pins into the other one's plastic body.
    That is the shape of `J314` under `J303`-`J305` in the first placement,
    and it is why both faces now share ONE strip of the connector edge."""
    _, pl = placed
    j303, j311 = pl.get("J303"), pl.get("J311")
    assert j303.tht and j311.tht and (j303.layer, j311.layer) == (1, 2)
    under = moved(pl, "J311", du=j303.box.cu - j311.box.cu, dv=j303.box.cv - j311.box.cv)
    got = lines(place.check(under, ix), 17)
    assert any("J303 (layer 1)" in s and "J311 (layer 2)" in s for s in got), got


def test_17_allows_a_body_over_a_through_hole_body_clear_of_its_pads(placed, ix):
    """⭐ The allowance the rule turns on: only the PADS cross the board. A
    part on the far face may stand over a through-hole part's BODY -- a 0603
    over the brick's case -- as long as it keeps `PIN_PROTRUSION` from every
    pad. Here `R301` overlaps `J311`'s body in plan and is 1.0 mm clear of its
    pad row, and nothing fires."""
    _, pl = placed
    j311 = pl.get("J311")
    frame = pl.frame("OUTPUTS")
    pads = j311.tht_boxes(frame)
    assert pads and j311.layer == 2
    r = pl.get("R301")
    assert not r.tht and r.layer == 1
    # just past the back of J311's pad row, inside its body
    v0 = max(b.v1 for b in pads) + place.PIN_PROTRUSION
    over = moved(pl, "R301", du=j311.box.cu - r.box.cu, dv=v0 - r.box.v0)
    q = over.get("R301")
    assert q.box.overlaps(j311.box)                     # it IS over the body
    assert min(max(*b.gaps(q.box)) for b in pads) == pytest.approx(place.PIN_PROTRUSION)
    assert not any("J311" in s and "R301" in s for s in lines(place.check(over, ix), 17))
    # and half a millimetre closer, it is on the pins
    on = moved(over, "R301", dv=-0.5)
    assert any("J311" in s and "R301" in s for s in lines(place.check(on, ix), 17))


def test_17_allows_two_surface_mount_parts_on_opposite_faces(placed, ix):
    """Nothing crosses the board between two surface-mount parts: they may
    overlap in plan freely, which is the whole point of a second face."""
    _, pl = placed
    u202, r110 = pl.get("U202"), pl.get("R110")
    assert not u202.tht and not r110.tht and (u202.layer, r110.layer) == (2, 1)
    over = moved(pl, "R110", du=u202.box.cu - r110.box.cu, dv=u202.box.cv - r110.box.cv)
    assert over.get("R110").box.overlaps(u202.box)
    assert not any("U202" in s and "R110" in s for s in lines(place.check(over, ix), 17))


def test_the_engine_never_lands_a_pin_in_a_body_on_the_other_face(placed, placeable_placed, ix):
    """The rule in the ENGINE, not only in the check -- on both fixtures, and
    on a fixture that really does have pins crossing: the face row, `J308`,
    `J311` and `J312` are all through-hole here."""
    for _, pl in (placed, placeable_placed):
        tht = {p.refdes for b in bp.STACK_ORDER for p in pl.placed(b).values() if p.tht}
        assert {"J308", "J312", "J303", "J406"} <= tht
        assert lines(place.check(pl, ix), 17) == []


# --- a host stands where its satellite can follow ------------------------------------
def test_every_decoupler_sits_on_the_ic_it_decouples(placed, ix):
    """Stronger than check 15, which asks only for the NEAREST IC on the rail:
    every 100 nF is within `DECOUPLE_REACH` of the IC it was given."""
    _, pl = placed
    for board in bp.STACK_ORDER:
        for cap, host in place.decoupler_hosts(ix, board).items():
            p, h = pl.get(cap), pl.get(host)
            if p is None or h is None or p.unplaced or h.unplaced:
                continue
            sep = p.box.separation(h.box)
            assert sep <= place.DECOUPLE_REACH + place.TOL, (board, cap, host, sep)


def test_room_beside_finds_a_free_side_and_refuses_a_pocket():
    """The mechanism: a satellite needs a `w x d` rectangle against its host,
    CLEAR away and on the board."""
    host = place.Box(100.0, 20.0, 103.0, 23.0)
    sat = (3.9, 1.8, [])
    assert place._room_beside(host, sat, 242.0, 41.84)
    c = place.CLEAR
    walls = [(place.Box(90.0, 10.0, 100.0 - c, 33.0), 0.0, 0.0),
             (place.Box(103.0 + c, 10.0, 113.0, 33.0), 0.0, 0.0),
             (place.Box(90.0, 10.0, 113.0, 20.0 - c), 0.0, 0.0),
             (place.Box(90.0, 23.0 + c, 113.0, 33.0), 0.0, 0.0)]
    assert not place._room_beside(host, (3.9, 1.8, walls), 242.0, 41.84)
    # the same pocket with the left wall pulled back leaves room on that side
    walls[0] = (place.Box(90.0, 10.0, 100.0 - c - 3.9, 33.0), 0.0, 0.0)
    assert place._room_beside(host, (3.9, 1.8, walls), 242.0, 41.84)
    # and a side that runs off the board is not room
    edge = place.Box(0.0, 0.0, 3.0, 3.0)
    assert not place._room_beside(edge, (3.9, 1.8, []), 3.0, 3.0)


def test_a_host_is_steered_to_a_position_its_satellite_can_follow(placed, ix):
    """⭐ The cause of the defect this fixed: `U406` was placed into a hole
    exactly its own size -- `U405` beside it, the band-3 channel in front and
    `J406`'s through-hole pads behind -- so its 100 nF had nowhere nearer than
    8.6 mm and check 15 failed while every other check passed. A host now pays
    `SATELLITE_ROOM` for a position its satellite cannot follow, and the slot
    scan walks past a pocket that is exactly big enough."""
    project, _ = placed
    pr = place.Placer(place.Placement(project, ix), "LOGIC")
    host, sat = "U406", "C436"
    assert pr.host(sat) == host
    hbox = place.placed_box(pr.env(host), pr.frame, 0.0, 0.0, 0, False)
    # a pocket walled on all four sides, the host's own size plus SLACK: it
    # seats the host and nothing else
    slack, thick = 0.5, 3.0
    pu, pv = 100.0, 20.0
    u0, u1 = pu - slack - thick, pu + hbox.w + slack + thick
    v0, v1 = pv - slack - thick, pv + hbox.d + slack + thick
    walls = [place.Box(u0, v0, pu - slack, v1),
             place.Box(pu + hbox.w + slack, v0, u1, v1),
             place.Box(u0, v0, u1, pv - slack),
             place.Box(u0, pv + hbox.d + slack, u1, v1)]
    pr.extra[host] = walls
    pr.extra[sat] = walls
    reserve = pr._reserve(host, 4)
    assert reserve is not None and reserve[0] > 0 and reserve[1] > 0
    # ... because a satellite needs CLEAR plus its own size beyond the host,
    # and the pocket gives at most twice the slack on any side
    assert min(reserve[0], reserve[1]) + place.CLEAR > 2 * slack

    def body(got):
        return place.placed_box(pr.env(host), pr.frame, got[0], got[1], 0, False)

    loose = body(pr._slot(host, 4, 0, pu + hbox.w / 2, pv))
    assert loose.u0 == pytest.approx(pu, abs=0.01)         # it takes the pocket
    assert not place._room_beside(loose, reserve, pr.frame.length, pr.frame.width)
    tight = body(pr._slot(host, 4, 0, pu + hbox.w / 2, pv, reserve=reserve))
    assert abs(tight.u0 - pu) > hbox.w                     # it walks past it
    assert place._room_beside(tight, reserve, pr.frame.length, pr.frame.width)


# --- the picture ----------------------------------------------------------------------
def test_draw_writes_one_picture_per_board(placed, ix, tmp_path):
    Image = pytest.importorskip("PIL.Image")
    _, pl = placed
    paths = place.draw(pl, ix, tmp_path / "pics", prefix="stack")
    assert [p.name for p in paths] == [f"stack-{b}.png" for b in bp.STACK_ORDER]
    for p in paths:
        with Image.open(p) as im:
            # the board at DRAW_SCALE px/mm, plus a margin each side
            assert im.size[0] == pytest.approx(242.0 * place.DRAW_SCALE + 2 * place.DRAW_MARGIN,
                                               abs=1)
            assert im.size[1] == pytest.approx(41.84 * place.DRAW_SCALE + 2 * place.DRAW_MARGIN,
                                               abs=1)


# --- the writer ---------------------------------------------------------------------
def test_write_round_trips_every_placed_coordinate_and_keeps_prev(placeable_project, ix,
                                                                  tmp_path, monkeypatch):
    synthetic_project = placeable_project
    monkeypatch.setattr(place, "editor_running", lambda: False)
    fresh = place.load(synthetic_project)
    pl2 = place.stack(fresh, ix)
    place.apply(fresh, pl2)
    out = tmp_path / "out.eprj2"
    out.write_bytes(b"old")
    place.write(fresh, pl2, synthetic_project, out)
    assert (tmp_path / "out.eprj2.prev").read_bytes() == b"old"
    back = place.load(out)
    for board, items in pl2.boards.items():
        frame = fresh.pcbs[board].frame
        for ref, p in items.items():
            c = back.pcbs[board].components[ref]
            x, y = frame.to_file(p.u, p.v)
            assert (c.x, c.y, c.angle, c.layer) == (place._mil(x), place._mil(y),
                                                   frame.file_angle(p.angle), p.layer)
    # nothing but COMPONENT and label ATTR records changed
    a = eprj2.split_records(eprj2.read(synthetic_project)["text"])
    b = eprj2.split_records(eprj2.read(out)["text"])
    assert len(a) == len(b)
    changed = {h["type"] for (h, p), (h2, p2) in zip(a, b) if (h, p) != (h2, p2)}
    assert changed == {"COMPONENT", "ATTR"}
    assert place.check(place.Placement.from_file(back, ix), ix) == []


def test_write_refuses_while_the_editor_is_open(placed, synthetic_project, tmp_path, monkeypatch):
    project, pl = placed
    monkeypatch.setattr(place, "editor_running", lambda: True)
    with pytest.raises(RuntimeError, match="EasyEDA Pro is running"):
        place.write(project, pl, synthetic_project, tmp_path / "x.eprj2")
    assert not (tmp_path / "x.eprj2").exists()


def test_the_default_file_is_the_editor_folder_and_tests_never_touch_the_real_one():
    """conftest redirects build_project.EDITOR_PROJECTS for the whole session;
    place.py reads the attribute at call time, so the redirect covers it."""
    assert place.default_file().parent == Path(build_project.EDITOR_PROJECTS)
    assert not str(place.default_file()).startswith(str(Path.home() / "Documents"))


def test_cli_check_reports_and_stack_writes(placeable_project, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(place, "editor_running", lambda: False)
    assert place.main(["--check", "--file", str(placeable_project)]) == place.EXIT_PROBLEMS
    out = tmp_path / "stack.eprj2"
    docs = tmp_path / "docs"
    pics = tmp_path / "pics"
    assert place.main(["--stack", "--file", str(placeable_project), "--out", str(out),
                       "--docs", str(docs), "--draw", str(pics)]) == 0
    text = capsys.readouterr().out
    assert "0 problem(s)" in text and "written:" in text and "drawn:" in text
    for board in bp.STACK_ORDER:
        table = (docs / f"{board}-placement.md").read_text()
        assert "| Refdes |" in table and "reason" in table
        assert (pics / f"stack-{board}.png").is_file()
    assert place.main(["--check", "--file", str(out)]) == 0
    assert "J406" in (docs / "LOGIC-placement.md").read_text()
    assert "fixed: mate of J308" in (docs / "LOGIC-placement.md").read_text()


def test_cli_stack_refuses_and_names_what_had_nowhere_to_go(synthetic_project, tmp_path, capsys,
                                                            monkeypatch):
    """The real design: `--stack` writes the tables and the pictures, names
    every unplaced part with its reason, and does NOT write the project."""
    monkeypatch.setattr(place, "editor_running", lambda: False)
    out = tmp_path / "stack.eprj2"
    pics = tmp_path / "pics"
    assert place.main(["--stack", "--file", str(synthetic_project), "--out", str(out),
                       "--docs", str(tmp_path / "docs"), "--draw", str(pics)]) \
        == place.EXIT_PROBLEMS
    text = capsys.readouterr().out
    assert "OUTPUTS J314: UNPLACED" in text and "POWER U201: UNPLACED" in text
    assert not out.exists()
    assert (pics / "stack-OUTPUTS.png").is_file()
    # the table gives an unplaced part no coordinates: where the file happens
    # to hold it is not a proposal
    row = next(ln for ln in (tmp_path / "docs" / "OUTPUTS-placement.md").read_text().splitlines()
               if ln.startswith("| J314 "))
    assert row.count("| — ") == 5 and "UNPLACED" in row


def _doc_span(records, title):
    """(first, last + 1) of the PCB document titled `title` in `records` --
    the same walk `place.load` does."""
    lead, docs = eprj2.documents(records)
    pos = len(lead)
    for doc_type, _uuid, recs in docs:
        if doc_type == "PCB" and any(h["type"] == "META" and json.loads(p).get("title") == title
                                     for h, p in recs):
            return pos, pos + len(recs)
        pos += len(recs)
    raise AssertionError(f"no PCB titled {title}")


def test_board_writes_only_that_boards_records(synthetic_project, tmp_path, monkeypatch, capsys):
    """`--board LOGIC`: LOGIC is placeable today while OUTPUTS and POWER wait
    on the row decision, so it is written on its own and every other record in
    the file is left exactly as it was saved."""
    monkeypatch.setattr(place, "editor_running", lambda: False)
    out = tmp_path / "one.eprj2"
    docs = tmp_path / "docs"
    assert place.main(["--stack", "--board", "LOGIC", "--file", str(synthetic_project),
                       "--out", str(out), "--docs", str(docs)]) == 0
    text = capsys.readouterr().out
    assert "writing LOGIC only: 0 failed check(s) and 0 unplaced part(s)" in text
    before = eprj2.split_records(eprj2.read(synthetic_project)["text"])
    after = eprj2.split_records(eprj2.read(out)["text"])
    assert len(before) == len(after)
    changed = [i for i, (x, y) in enumerate(zip(before, after)) if x != y]
    lo, hi = _doc_span(after, "LOGIC")
    assert changed and all(lo <= i < hi for i in changed)
    assert {before[i][0]["type"] for i in changed} == {"COMPONENT", "ATTR"}
    for title in ("OUTPUTS", "POWER"):
        a0, a1 = _doc_span(before, title)
        assert (a0, a1) == _doc_span(after, title) and before[a0:a1] == after[a0:a1]
    # LOGIC's parts really did move, and only LOGIC got a table
    fresh = place.load(out)
    assert fresh.pcbs["LOGIC"].components["U401"].y > 0      # the import left it below the outline
    assert {p.name for p in docs.iterdir()} == {"LOGIC-placement.md"}


def test_board_refuses_when_the_board_it_names_cannot_be_placed(synthetic_project, tmp_path,
                                                                monkeypatch, capsys):
    """The gate is per selected board: POWER cannot seat the brick, so
    `--board POWER` refuses and writes nothing -- while the same run reports
    LOGIC as clean."""
    monkeypatch.setattr(place, "editor_running", lambda: False)
    out = tmp_path / "p.eprj2"
    assert place.main(["--stack", "--board", "POWER", "--file", str(synthetic_project),
                       "--out", str(out), "--docs", str(tmp_path / "docs")]) == place.EXIT_PROBLEMS
    text = capsys.readouterr().out
    assert "POWER U201: UNPLACED" in text
    assert "writing POWER only: 0 failed check(s) and 1 unplaced part(s)" in text
    assert not out.exists()


def test_board_gates_on_the_named_board_alone(placed, ix):
    """`check(boards=...)` is what the gate reads: a problem on a board that
    is not being written does not block the one that is."""
    _, pl = placed
    j402, r = pl.get("J402"), pl.get("R402")
    broken = moved(pl, "R402", du=j402.box.cu - r.box.cu, dv=(j402.box.v1 + 1.0) - r.box.v0)
    assert any(" LOGIC " in s for s in place.check(broken, ix))
    assert place.check(broken, ix, boards=["POWER"]) == []
    assert place.check(broken, ix, boards=["LOGIC"]) != []


def test_cli_draw_alone_draws_the_file_and_judges_nothing(synthetic_project, tmp_path, capsys):
    pytest.importorskip("PIL.Image")
    pics = tmp_path / "pics"
    assert place.main(["--draw", str(pics), "--file", str(synthetic_project)]) == 0
    text = capsys.readouterr().out
    assert "problem(s)" not in text
    assert {p.name for p in pics.iterdir()} == {f"{synthetic_project.stem}-{b}.png"
                                                for b in bp.STACK_ORDER}


def test_cli_refuses_a_part_the_netlist_does_not_know(synthetic_project, tmp_path, capsys):
    project = place.load(synthetic_project)
    recs = project.records
    # rename one designator to a refdes the netlist has never heard of
    doc = project.pcbs["LOGIC"]
    comp = doc.components["R402"]
    for i in comp.labels:
        h, p = recs[i]
        a = json.loads(p)
        if a.get("key") == "Designator":
            a["value"] = "R999"
            recs[i] = (h, eprj2._compact(a))
    bad = tmp_path / "bad.eprj2"
    eprj2.write(synthetic_project, bad, eprj2.join(recs), project.snap["structure"],
                project.snap["name"], owner=project.snap["owner"])
    assert place.main(["--check", "--file", str(bad)]) == place.EXIT_REFUSED
    assert "R999" in capsys.readouterr().err


def test_a_zero_size_hole_is_an_smd_pad_not_a_pin_through_the_board():
    """`U404`'s SOIC-8 in the owner's file: eight pads, each with
    `"hole":{"holeType":"ROUND","width":0,"height":0}` -- the converter's way
    of writing an SMD land. Counting it as through-hole made an SOIC a THT part
    (2026-09-22) and would forbid every part on the other face under it. A
    hole crosses the board only if it has a size; the same pad with a 0.6 mm
    hole does."""
    def pad(hole):
        return [({"type": "PAD", "id": "p"}, eprj2._compact({
            "layerId": 1, "num": "1", "centerX": 0, "centerY": 0, "hole": hole, "plated": True,
            "defaultPad": {"padType": "RECT", "width": 60.0, "height": 60.0}}))]
    smd = place.envelope(pad({"holeType": "ROUND", "width": 0, "height": 0}), (2.0, 2.0))
    assert smd.pads[0][5] is False and not smd.tht
    none = place.envelope(pad(None), (2.0, 2.0))
    assert none.pads[0][5] is False and not none.tht
    drilled = place.envelope(pad({"holeType": "ROUND", "width": 23.622, "height": 23.622}), (2.0, 2.0))
    assert drilled.pads[0][5] is True and drilled.tht
