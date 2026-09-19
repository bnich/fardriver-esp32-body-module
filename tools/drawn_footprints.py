"""Land patterns drawn from the manufacturers' drawings, for the parts EasyEDA's
library has no device for (padmap.FOOTPRINT_FROM_MPN maps them to None).

Every footprint is the TOP view: the side the part sits on, looking down, X
right and Y up, which is the frame EasyEDA's library footprints use (a SOIC-8
and a SOT-23 there number counter-clockwise in +Y-up coordinates).  A vendor
drawing of the PIN FACE or a BOTTOM VIEW is mirrored into it by `_mirror`:
getting that wrong swaps a module's pins left for right on a board that passes
every other check.  tests/test_drawn_footprints.py types each drawing as the
vendor draws it and checks the mirror.

Pad numbers are the netlist's pin names (the symbol's pin numbers), so no pad
map is needed.  Pin 1 is square: these parts are hand-soldered and the
footprints carry no silkscreen.
"""
from dataclasses import dataclass, field

from .eprj3.footprints import Pad

IN = 25.4
#: Drill over a pin's nominal diameter.  Leaves 0.3 mm over Cincon's largest
#: pin (1.0 ± 0.1 mm), above JLC's ±0.08 mm plated-hole tolerance.
LEAD_CLEARANCE_MM = 0.4
#: Copper ring around each drill, per side.
ANNULAR_MM = 0.5
#: M3 clearance: TDK's own non-threaded mounting hole is ø3.3 (manual p.4, /T).
M3_DRILL_MM = 3.3
#: The OD of an ISO 7089 M3 plain washer, the one TDK's Fig. 8-1a puts under
#: the screw head.  The washer must seat on copper: that contact is what puts
#: BASEPLATE on the board's net.
M3_WASHER_MM = 7.0


@dataclass(frozen=True)
class Drawn:
    title: str
    pads: tuple[Pad, ...]
    #: Pad numbers more than one pad carries (a module's two mounting holes).
    shared: frozenset[str] = field(default_factory=frozenset)


def _pin(num, x, y, lead_mm, first=False):
    drill = round(lead_mm + LEAD_CLEARANCE_MM, 3)
    size = round(drill + 2 * ANNULAR_MM, 3)
    return Pad(num, x, y, size, size, drill, "RECT" if first else "ELLIPSE")


def _mirror(pads):
    """A pin-face or bottom view -> the top view."""
    return tuple(Pad(p.num, round(-p.x_mm, 4) + 0.0, p.y_mm, p.w_mm, p.h_mm, p.hole_mm, p.shape)
                 for p in pads)


def tdk_cn150b110():
    """TDK-Lambda outline CA952-02-01A (cn50-150b110_out.pdf), which draws the
    PIN FACE: the name plate and pins face the reader, as in the manual's p.5
    figure.  Origin at the drawing's centre lines.  Input column at -49.7/2:
    -Vin 3.81 above CNT, CNT 6.35 above the centre line, +Vin 3.175 below it.
    Output column at +49.7/2: -V, -S, TRM, +S, +V on 3.81 steps, TRM on the
    centre line.  M3 threaded holes in the pin columns, 28 apart.  Note C:
    output pins ø1.5.  Note D: input and signal pins ø1.0."""
    xi, xo = -49.7 / 2, 49.7 / 2
    face = (
        _pin("-Vin", xi, 6.35 + 3.81, 1.0, first=True),
        _pin("CNT", xi, 6.35, 1.0),
        _pin("+Vin", xi, -3.175, 1.0),
        _pin("-V", xo, 2 * 3.81, 1.5),
        _pin("-S", xo, 3.81, 1.0),
        _pin("TRM", xo, 0.0, 1.0),
        _pin("+S", xo, -3.81, 1.0),
        _pin("+V", xo, -2 * 3.81, 1.5),
        Pad("BASEPLATE", xi, -14.0, M3_WASHER_MM, M3_WASHER_MM, M3_DRILL_MM, "ELLIPSE"),
        Pad("BASEPLATE", xo, 14.0, M3_WASHER_MM, M3_WASHER_MM, M3_DRILL_MM, "ELLIPSE"),
    )
    return Drawn("TDK_CN50-150B110_QUARTER_BRICK", _mirror(face), frozenset({"BASEPLATE"}))


def cincon_ec7bw_110():
    """Cincon EC7BW-110 datasheet V15 p.7, a BOTTOM VIEW in inches, from the
    case's top-left corner (Y down): top row 0.10 in, pins 3 · 5 · 4 at 0.10 ·
    0.50 · 0.90; bottom row 1.800 lower, pins 1 · 2 · 6 at 0.20 · 0.40 · 0.80.
    Case 1.00 × 2.00.  Pin 1.0 ± 0.1 mm."""
    def at(num, x, y, first=False):
        return _pin(num, round((x - 0.50) * IN, 4), round(-(y - 1.00) * IN, 4), 1.0, first)
    bottom = (at("+Vin", 0.20, 1.90, first=True), at("-Vin", 0.40, 1.90),
              at("+Vout", 0.10, 0.10), at("Trim", 0.90, 0.10),
              at("-Vout", 0.50, 0.10), at("Remote", 0.80, 1.90))
    return Drawn("CINCON_EC7BW_2X1IN", _mirror(bottom))


def wurth_7448022010():
    """Würth 7448022010 rev 002.000 p.1, 'Recommended Hole Pattern', a TOP
    view (the drawing is first-angle, and the dimension view above the front
    view is the bottom, its mirror): pins 4 · 3 over 1 · 2, 7.7 × 5.0, ø1.5
    holes.  Windings 1-4 and 2-3."""
    def at(num, x, y, first=False):
        return Pad(num, x, y, 1.5 + 2 * ANNULAR_MM, 1.5 + 2 * ANNULAR_MM, 1.5,
                   "RECT" if first else "ELLIPSE")
    return Drawn("WE_7448022010", (at("1", -3.85, -2.5, first=True), at("2", 3.85, -2.5),
                                   at("3", 3.85, 2.5), at("4", -3.85, 2.5)))


def net_tie():
    """R211: two 2 × 2 mm pads that abut, one unbroken 4 × 2 mm strip of top
    copper.  The part's `source` says why it is copper, not a 0 Ω chip.
    Expect EasyEDA's DRC to report the two nets touching here (not yet run);
    that contact is the part's whole purpose."""
    return Drawn("NET-TIE_4X2MM", (Pad("1", -1.0, 0.0, 2.0, 2.0),
                                   Pad("2", 1.0, 0.0, 2.0, 2.0)))


BY_MPN = {
    "CN150B110-12/CO": tdk_cn150b110(),
    "EC7BW-110S05": cincon_ec7bw_110(),
    "7448022010": wurth_7448022010(),
    "NET-TIE": net_tie(),
}
