"""Land patterns drawn from the manufacturers' drawings.

Each drawing is typed here AS THE VENDOR DRAWS IT -- its own view, its own
origin -- and the footprint must be the top view of it.  A drawing of the pin
face or a BOTTOM VIEW mirrors into the top view; getting that wrong swaps a
module's pins left for right on a board that passes every other check.
"""
import json
import math

import pytest

from tools import drawn_footprints as drawn
from tools import footprint_lib, netlist
from tools.eprj3 import footprints
from tools.eprj3 import symbols as sym
from tools.eprj3.project import Project
from tools.eprj3.schematic import emit_board
from tools.eprj3.units import pcb_to_mm

IN = 25.4


def part(mpn):
    return next(p for p in netlist.current().parts if p.mpn == mpn)


def centres(fp):
    """{num: [(x, y), ...]} rounded to 0.001 mm."""
    out = {}
    for p in fp.pads:
        out.setdefault(p.num, []).append((round(p.x_mm, 3), round(p.y_mm, 3)))
    return {k: sorted(v) for k, v in out.items()}


def mirrored(view):
    """A pin-face or bottom view -> the top view: X changes sign."""
    return {k: sorted((round(-x, 3), round(y, 3)) for x, y in v) for k, v in view.items()}


def edge_gap(a, b):
    """Copper-to-copper distance between two pads (exact for circles and
    axis-aligned rectangles)."""
    def box(p):
        return (p.x_mm - p.w_mm / 2, p.y_mm - p.h_mm / 2,
                p.x_mm + p.w_mm / 2, p.y_mm + p.h_mm / 2)
    if a.shape == "ELLIPSE" and b.shape == "ELLIPSE":
        return math.dist((a.x_mm, a.y_mm), (b.x_mm, b.y_mm)) - a.w_mm / 2 - b.w_mm / 2
    if a.shape == "ELLIPSE":
        a, b = b, a
    ax0, ay0, ax1, ay1 = box(a)
    if b.shape == "ELLIPSE":
        dx = max(ax0 - b.x_mm, 0, b.x_mm - ax1)
        dy = max(ay0 - b.y_mm, 0, b.y_mm - ay1)
        return math.hypot(dx, dy) - b.w_mm / 2
    bx0, by0, bx1, by1 = box(b)
    return math.hypot(max(bx0 - ax1, 0, ax0 - bx1), max(by0 - ay1, 0, ay0 - by1))


# --- TDK CN150B110: outline CA952-02-01A, a view of the PIN FACE -----------------------
# Origin at the drawing's two centre lines, X right, Y up, as drawn.  Input column at
# -49.7/2, output column at +49.7/2; the M3 holes sit in the pin columns, 28 apart.
TDK_PIN_FACE = {
    "-Vin": [(-24.85, 10.16)], "CNT": [(-24.85, 6.35)], "+Vin": [(-24.85, -3.175)],
    "-V": [(24.85, 7.62)], "-S": [(24.85, 3.81)], "TRM": [(24.85, 0.0)],
    "+S": [(24.85, -3.81)], "+V": [(24.85, -7.62)],
    "BASEPLATE": [(-24.85, -14.0), (24.85, 14.0)],
}


def test_the_tdk_brick_is_the_mirror_of_its_pin_face_drawing():
    assert centres(drawn.BY_MPN["CN150B110-12/CO"]) == mirrored(TDK_PIN_FACE)


def test_the_tdk_brick_takes_tdks_own_holes_and_lands():
    """Manual p.24: input / signal pins (ø1.0) hole 1.5, land 2.5; output pins
    (ø1.5) hole 2.0, land 3.5; the M3 mounting holes (FG) hole 3.5, land 7.0,
    which seats the washer that puts BASEPLATE on the net."""
    want = {"-V": (2.0, 3.5), "+V": (2.0, 3.5), "BASEPLATE": (3.5, 7.0)}
    for p in drawn.BY_MPN["CN150B110-12/CO"].pads:
        assert (p.hole_mm, p.w_mm, p.h_mm) == (*want.get(p.num, (1.5, 2.5)),
                                               want.get(p.num, (1.5, 2.5))[1]), p


# --- Cincon EC7BW-110: datasheet V15 p.7, BOTTOM VIEW, inches ---------------------------
# From the case's top-left corner as drawn, Y down: 1.00 wide, 2.00 tall.
CINCON_BOTTOM_IN = {
    "+Vout": (0.10, 0.10), "-Vout": (0.50, 0.10), "Trim": (0.90, 0.10),
    "+Vin": (0.20, 1.90), "-Vin": (0.40, 1.90), "Remote": (0.80, 1.90),
}


def test_the_cincon_module_is_the_mirror_of_its_bottom_view():
    view = {k: [((x - 0.50) * IN, -(y - 1.00) * IN)] for k, (x, y) in CINCON_BOTTOM_IN.items()}
    assert centres(drawn.BY_MPN["EC7BW-110S05"]) == mirrored(view)


def test_the_cincon_holes_fit_its_largest_pin():
    """p.7 note: pin size 1.0 ± 0.1 mm."""
    for p in drawn.BY_MPN["EC7BW-110S05"].pads:
        assert p.hole_mm >= 1.1 + 0.25 and p.w_mm - p.hole_mm >= 1.0


# --- Würth 7448022010: 'Recommended Hole Pattern', a TOP view --------------------------
WURTH_TOP = {"4": [(-3.85, 2.5)], "3": [(3.85, 2.5)], "1": [(-3.85, -2.5)], "2": [(3.85, -2.5)]}


def test_the_choke_follows_wurths_recommended_hole_pattern():
    fp = drawn.BY_MPN["7448022010"]
    assert centres(fp) == {k: sorted(v) for k, v in WURTH_TOP.items()}
    assert all(p.hole_mm == 1.5 for p in fp.pads)       # the pattern's ø1.5


# --- The net-tie ------------------------------------------------------------------------
def test_the_net_tie_is_one_unbroken_strip_of_copper_2_mm_wide():
    """R211 carries a shorted Y2's fault current until the fuse opens: copper,
    at least 2 mm wide, with no gap for the current to jump."""
    a, b = sorted(drawn.BY_MPN["NET-TIE"].pads, key=lambda p: p.x_mm)
    assert (a.num, b.num) == ("1", "2")
    assert a.hole_mm is None and b.hole_mm is None
    assert a.x_mm + a.w_mm / 2 == pytest.approx(b.x_mm - b.w_mm / 2)   # abutting
    assert a.y_mm == b.y_mm and min(a.h_mm, b.h_mm) >= 2.0


# --- The fuse: a footprint for the netlist export, never converted to PCB ---------------
def test_the_fuse_footprint_sits_on_its_clip_rows():
    """EasyEDA's Allegro netlist export refuses a part without a footprint even
    when it is not converted to PCB.  F201 is never on the board -- its clips
    are -- so its pads mark where the caps sit: on the clip rows, 17.8 mm
    apart (FH201's source)."""
    a, b = sorted(drawn.BY_MPN["0001.2504"].pads, key=lambda p: p.x_mm)
    assert (a.num, b.num) == ("1", "2")
    assert b.x_mm - a.x_mm == pytest.approx(17.8) and a.y_mm == b.y_mm == 0


def _devices(board):
    project = Project("t")
    project.add_board(board)
    sheet = project.boards[0].schematic.sheets[0]
    emit_board(netlist.current(), board, sheet)
    out, cur = [], None
    for rec in sheet.library_records:
        head, _, payload = rec.partition("||")
        h, p = json.loads(head), json.loads(payload)
        if h["type"] == "DOCHEAD":
            cur = p["docType"]
        elif cur == "DEVICE" and h["type"] == "META":
            out.append(p)
    return out


def test_only_the_fuse_is_left_off_the_pcb():
    """Import Changes honours `Convert to PCB`: the fuse's pads must not land on
    top of FH201's."""
    off = [d["title"] for d in _devices("CONV")
           if "Global Net Name" not in d["attributes"]      # net flags are not parts
           and d["attributes"].get("Convert to PCB") != "yes"]
    assert off == ["0001.2504_C1665055"]
    assert all(d["attributes"].get("Convert to PCB") == "yes"
               for b in ("HVIN", "DRV", "BRAIN") for d in _devices(b)
               if "Global Net Name" not in d["attributes"])


# --- Every drawn footprint --------------------------------------------------------------
@pytest.mark.parametrize("mpn", sorted(drawn.BY_MPN))
def test_every_symbol_pin_has_a_pad_and_no_pad_is_extra(mpn):
    p = part(mpn)
    fp = drawn.BY_MPN[mpn]
    assert {pad.num for pad in fp.pads} == {pin.number for pin in sym.for_part(p).pins}
    repeated = {n for n in (pad.num for pad in fp.pads)
                if sum(q.num == n for q in fp.pads) > 1}
    assert repeated == set(fp.shared)


#: Pads a part's own datasheet joins: TDK p.17 straps +S to +V and -S to -V
#: at the brick, so TDK's p.24 lands may sit 0.81 mm apart there.
STRAPPED = {"CN150B110-12/CO": {frozenset({"+V", "+S"}), frozenset({"-V", "-S"})}}


@pytest.mark.parametrize("mpn", sorted(set(drawn.BY_MPN) - {"NET-TIE"}))
def test_no_two_pads_touch(mpn):
    pads = drawn.BY_MPN[mpn].pads
    for i, a in enumerate(pads):
        for b in pads[i + 1:]:
            if a.num == b.num or frozenset({a.num, b.num}) in STRAPPED.get(mpn, ()):
                assert edge_gap(a, b) > 0, (mpn, a.num, b.num)
                continue
            assert edge_gap(a, b) >= 1.0, (mpn, a.num, b.num, edge_gap(a, b))


def test_the_strapped_pads_really_share_a_net():
    d = netlist.current()
    for pair in STRAPPED["CN150B110-12/CO"]:
        assert len({d.net_of("U201", pin).name for pin in pair}) == 1, pair


@pytest.mark.parametrize("mpn", ["CN150B110-12/CO", "EC7BW-110S05"])
def test_the_160_v_input_clears_every_other_pad(mpn):
    """+Vin sees up to 160 V (the do-not-exceed): IPC-2221B B2, external and
    uncoated, asks 1.25 mm for 151-300 V."""
    pads = drawn.BY_MPN[mpn].pads
    vin = next(p for p in pads if p.num == "+Vin")
    for p in pads:
        if p is not vin:
            assert edge_gap(vin, p) >= 1.25, (mpn, p.num)


def test_pin_one_is_the_square_pad():
    """These are hand-soldered and carry no silkscreen: the square pad is how
    the part goes in the right way round."""
    for mpn, first in (("CN150B110-12/CO", "-Vin"), ("EC7BW-110S05", "+Vin"),
                       ("7448022010", "1")):
        square = [p.num for p in drawn.BY_MPN[mpn].pads if p.shape == "RECT"]
        assert square == [first], mpn


# --- Binding --------------------------------------------------------------------------
def test_repeated_pad_numbers_need_declaring():
    pads = (footprints.Pad("M", 0, 0, 7, 7, 3.3, "ELLIPSE"),
            footprints.Pad("M", 20, 0, 7, 7, 3.3, "ELLIPSE"))
    with pytest.raises(ValueError, match="repeat"):
        footprints.footprint_records("fp", "T", pads, client="c", epoch_ms=1)
    recs = footprints.footprint_records("fp", "T", pads, client="c", epoch_ms=1,
                                        shared={"M"})
    assert sum('"num": "M"' in r or '"num":"M"' in r for r in recs) == 2


@pytest.mark.parametrize("board, refs", [("HVIN", {"L101", "L102"}),
                                         ("CONV", {"U201", "U202", "R211", "F201"})])
def test_the_drawn_parts_are_bound_without_the_library(board, refs):
    project = Project("t")
    project.add_board(board)
    sheet = project.boards[0].schematic.sheets[0]
    bs = emit_board(netlist.current(), board, sheet)
    assert refs <= set(bs.footprints_bound)
    assert not refs & set(bs.footprints_unbound)


# --- Parts that lie on the board, and the fuse holder ------------------------------------
def _outline_bounds(fp):
    xs, ys = [], []
    for o in fp.outline:
        if o.shape[0] == "CIRCLE":
            _, cx, cy, r = o.shape
            xs += [cx - r, cx + r]
            ys += [cy - r, cy + r]
        else:
            xs += [x for x, _ in o.shape]
            ys += [y for _, y in o.shape]
    return min(xs), min(ys), max(xs), max(ys)


@pytest.mark.parametrize("mpn,pitch,lead,body", [
    # Vishay doc 28535 p.2: the '…TV7' reel's leads are 7.5 mm apart, ø0.6 ± 0.05,
    # disc D 12.5 max. C1620119's library land put them 10 mm apart.
    ("VY2472M49Y5US6", 7.5, 0.65, (12.5, 12.5)),
    # Chemi-Con KXJ p.1, φ18: F 7.5, φd 0.8; φD' 18.5 × L' 26.5 lying down.
    ("EKXJ221ELL221MM25S", 7.5, 0.8, (18.5, 26.5)),
    # JIERR PA p.2, 10 × 15: F 5.0, φd 0.6 ± 0.05; φD + 0.5 = 10.5 × L + α = 16.
    ("PA35V680M10x15", 5.0, 0.65, (10.5, 16.0)),
])
def test_a_part_lying_beside_its_holes_has_its_leads_pitch_and_its_body_drawn(mpn, pitch, lead, body):
    fp = drawn.BY_MPN[mpn]
    a, b = sorted(fp.pads, key=lambda p: p.x_mm)
    assert b.x_mm - a.x_mm == pytest.approx(pitch) and a.y_mm == b.y_mm == 0
    assert all(p.hole_mm >= lead + 0.3 for p in fp.pads)
    x0, y0, x1, y1 = _outline_bounds(fp)
    assert (x1 - x0, y1 - y0) == (pytest.approx(body[0]), pytest.approx(body[1]))
    assert y0 >= max(p.h_mm / 2 for p in fp.pads), "the body sits clear of its holes"


def test_the_fuse_holder_fixes_its_clips_17_8_mm_apart():
    """Littelfuse 01110501Z: two pins 5.0 mm apart per clip; rows 17.8 mm
    apart hold a 5 × 20 fuse. One footprint, so layout cannot move them."""
    fp = drawn.BY_MPN["01110501Z"]
    assert fp.shared == {"1", "2"}
    rows = {n: sorted(p.x_mm for p in fp.pads if p.num == n) for n in ("1", "2")}
    assert rows["2"][0] - rows["1"][0] == pytest.approx(17.8)
    for n in ("1", "2"):
        ys = sorted(p.y_mm for p in fp.pads if p.num == n)
        assert ys[1] - ys[0] == pytest.approx(5.0)
    x0, _, x1, _ = _outline_bounds(fp)
    assert x1 - x0 == pytest.approx(20.0), "the fuse body is drawn between them"


def test_an_outline_is_written_as_the_library_writes_silkscreen():
    """The layer rows, ACTIVE_LAYER and a POLY per shape on layer 3, as
    v2footprint.convert writes an LCSC footprint's body."""
    fp = drawn.BY_MPN["EKXJ221ELL221MM25S"]
    recs = [(json.loads(h), json.loads(p)) for h, _, p in
            (r.partition("||") for r in footprints.footprint_records(
                "fp", fp.title, fp.pads, client="c", epoch_ms=1, outline=fp.outline))]
    types = [h["type"] for h, _ in recs]
    assert types[:2] == ["DOCHEAD", "META"] and types.index("ACTIVE_LAYER") < types.index("CANVAS")
    layers = {h["id"]: p["layerType"] for h, p in recs if h["type"] == "LAYER"}
    assert layers == {'["LAYER",1]': "TOP", '["LAYER",3]': "TOP_SILK", '["LAYER",12]': "MULTI"}
    polys = [p for h, p in recs if h["type"] == "POLY"]
    assert len(polys) == 1 and polys[0]["layerId"] == 3 and polys[0]["path"][2] == "L"
    bare = footprints.footprint_records("fp", "T", fp.pads, client="c", epoch_ms=1)
    assert not any('"LAYER"' in r or '"POLY"' in r for r in bare)


# --- The Tag-Connect TC2030-NL land (J408) ------------------------------------------
#: NL-TC2030-Footprint.pdf rev B, 'PCB TOP LAYER', typed as drawn: inches from
#: the lone left alignment hole's centre.  Pads 1 3 5 run along the lower row
#: and 2 4 6 along the upper, 0.050" apart both ways; the rows sit 0.025"
#: above and below the left hole; the two right holes are 0.200" right of it
#: and 0.040" above and below.
TC2030_PADS_IN = {"1": (0.050, -0.025), "2": (0.050, 0.025), "3": (0.100, -0.025),
                  "4": (0.100, 0.025), "5": (0.150, -0.025), "6": (0.150, 0.025)}
TC2030_HOLES_IN = ((0.0, 0.0), (0.200, 0.040), (0.200, -0.040))
#: The footprint's origin is the centre of the pads.
TC2030_ORIGIN_IN = (0.100, 0.0)


def _tc2030_mm(x, y):
    ox, oy = TC2030_ORIGIN_IN
    return round((x - ox) * IN, 3), round((y - oy) * IN, 3)


def test_the_tc2030_pads_are_where_the_drawing_puts_them():
    """A TOP view already: only the origin moves."""
    fp = drawn.LANDS["TC2030-NL"]
    assert centres(fp) == {n: [_tc2030_mm(*xy)] for n, xy in TC2030_PADS_IN.items()}
    for p in fp.pads:
        assert (p.w_mm, p.h_mm, p.hole_mm, p.shape) == (0.787, 0.787, None, "ELLIPSE"), p
        assert not p.paste, "note 3: no paste on a contact pad"


def test_the_tc2030_alignment_holes_are_unplated_and_key_the_cable():
    fp = drawn.LANDS["TC2030-NL"]
    holes = [o for o in fp.outline if o.hole]
    assert len(holes) == len(fp.outline) == 3, "the land carries no silkscreen"
    assert sorted((round(o.shape[1], 3), round(o.shape[2], 3)) for o in holes) == \
        sorted(_tc2030_mm(*xy) for xy in TC2030_HOLES_IN)
    assert all(o.shape[0] == "CIRCLE" and o.shape[3] == pytest.approx(0.991 / 2) for o in holes)
    left = [o for o in holes if o.shape[1] < 0]
    assert len(left) == 1, "one hole on one side, two on the other: one way on"


def test_the_tc2030_keep_out_is_the_area_between_its_pad_centres():
    fp = drawn.LANDS["TC2030-NL"]
    xs, ys = [p.x_mm for p in fp.pads], [p.y_mm for p in fp.pads]
    assert fp.keepout == ((min(xs), min(ys), max(xs), max(ys)),)
    assert fp.pad_clearance_mm == pytest.approx(0.020 * IN, abs=0.01)


def _records(fp):
    return [(json.loads(h), json.loads(p)) for h, _, p in
            (r.partition("||") for r in footprints.footprint_records(
                "fp", fp.title, fp.pads, client="c", epoch_ms=1, outline=fp.outline))]


def test_a_hole_is_written_as_the_library_writes_a_locating_peg():
    """LCSC C165948's pegs, through v2footprint: a solid FILL on layer 12 with
    one CIRCLE path and width 0.1 -- no pad, so no pin number and no copper."""
    fills = [p for h, p in _records(drawn.LANDS["TC2030-NL"]) if h["type"] == "FILL"]
    assert len(fills) == 3
    for f in fills:
        assert {k: f[k] for k in ("layerId", "width", "fillStyle", "netName",
                                  "isBridgingCopper", "networkList", "refs")} == {
            "layerId": 12, "width": 0.1, "fillStyle": "SOLID", "netName": "",
            "isBridgingCopper": False, "networkList": [], "refs": []}
        (circle,) = f["path"]
        assert circle[0] == "CIRCLE" and pcb_to_mm(circle[3]) == pytest.approx(0.991 / 2, abs=1e-3)


def test_a_pad_that_takes_no_paste_shrinks_its_aperture_to_nothing():
    """The library writes -3937 mil on every PASTED pad, so a large negative
    number there means 'the rule', not 'none': a no-paste pad carries its own
    expansion, past its own radius."""
    for h, p in _records(drawn.LANDS["TC2030-NL"]):
        if h["type"] == "PAD":
            size = p["defaultPad"]["width"]
            assert p["topPasteExpansion"] < 0 and size + 2 * p["topPasteExpansion"] < 0, p["num"]
    pasted = footprints.footprint_records("fp", "T", footprints.two_pad(1.9, 1.0, 1.3),
                                          client="c", epoch_ms=1)
    assert all(json.loads(r.partition("||")[2])["topPasteExpansion"] is None
               for r in pasted if json.loads(r.partition("||")[0])["type"] == "PAD")


def test_the_service_pads_take_the_tc2030_land_and_every_pin_has_a_pad():
    j = netlist.current().connector("J408")
    title, pads, shared, outline = footprint_lib.generated(j)
    assert title == "TAG-CONNECT_TC2030-NL" and not shared
    assert {p.num for p in pads} == {pin.number for pin in sym.for_connector(j).pins}
    assert sum(o.hole for o in outline) == 3
