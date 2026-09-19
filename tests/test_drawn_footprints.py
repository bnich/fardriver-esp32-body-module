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


def test_the_tdk_brick_holes_fit_its_pins_and_the_m3_screws():
    """Note C: output pins ø1.5; note D: input and signal pins ø1.0.  The M3
    holes take the screw of TDK's standard mounting (manual Fig. 8-1a), and
    the pad seats its plain washer: that contact is what puts BASEPLATE on
    the net."""
    fp = drawn.BY_MPN["CN150B110-12/CO"]
    for p in fp.pads:
        lead = {"-V": 1.5, "+V": 1.5, "BASEPLATE": 3.0}.get(p.num, 1.0)
        assert p.hole_mm is not None and p.hole_mm >= lead + 0.3, p
        assert p.w_mm - p.hole_mm >= 1.0, p           # 0.5 mm annular ring
    for p in (p for p in fp.pads if p.num == "BASEPLATE"):
        assert 3.2 <= p.hole_mm <= 3.4 and p.w_mm >= 7.0


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
    apart (FH201A's source)."""
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
    top of FH201A/B's."""
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


@pytest.mark.parametrize("mpn", sorted(set(drawn.BY_MPN) - {"NET-TIE"}))
def test_no_two_pads_touch(mpn):
    pads = drawn.BY_MPN[mpn].pads
    for i, a in enumerate(pads):
        for b in pads[i + 1:]:
            assert edge_gap(a, b) >= 1.0, (mpn, a.num, b.num, edge_gap(a, b))


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
