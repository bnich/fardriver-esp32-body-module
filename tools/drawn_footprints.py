"""Land patterns drawn from the manufacturers' drawings, for the parts EasyEDA's
library has no device for (padmap.FOOTPRINT_FROM_MPN maps them to None), and the
fuse's stand-in (`fuse_in_clips`).

Every footprint is the TOP view: the side the part sits on, looking down, X
right and Y up, which is the frame EasyEDA's library footprints use (a SOIC-8
and a SOT-23 there number counter-clockwise in +Y-up coordinates).  A vendor
drawing of the PIN FACE or a BOTTOM VIEW is mirrored into it by `_mirror`:
getting that wrong swaps a module's pins left for right on a board that passes
every other check.  tests/test_drawn_footprints.py types each drawing as the
vendor draws it and checks the mirror.

Pad numbers are the netlist's pin names (the symbol's pin numbers), so no pad
map is needed.  Pin 1 is square.  These parts are fitted by hand; a part that
LIES on the board beside its holes carries its body as a silkscreen outline,
so layout sees what it covers.
"""
from dataclasses import dataclass, field

from .eprj3.footprints import Outline, Pad

IN = 25.4
#: Drill over a pin's nominal diameter.  Leaves 0.3 mm over Cincon's largest
#: pin (1.0 ± 0.1 mm), above JLC's ±0.08 mm plated-hole tolerance.
LEAD_CLEARANCE_MM = 0.4
#: Copper ring around each drill, per side.
ANNULAR_MM = 0.5
#: TDK manual p.24 '(3) Mounting Holes on Printed Circuit Board': hole and
#: land diameters for the brick's pins and its M3 mounting holes (FG).  The
#: FG land seats the screw's washer: that contact puts BASEPLATE on the net.
TDK_SIGNAL = (1.5, 2.5)       # input / signal pins, ø1.0
TDK_OUTPUT = (2.0, 3.5)       # output pins, ø1.5
TDK_FG = (3.5, 7.0)           # M3 mounting holes
#: Where a lying part's leads turn down into the board: this far from the body,
#: measured from the hole's centre, so the body clears its own lands (≤ ø2.2)
#: and the bend stays off the can's seal.
LEAD_BEND_MM = 2.0


@dataclass(frozen=True)
class Drawn:
    title: str
    pads: tuple[Pad, ...]
    #: Pad numbers more than one pad carries (a module's two mounting holes).
    shared: frozenset[str] = field(default_factory=frozenset)
    #: The body, where the part lies beside its holes: silkscreen shapes.
    outline: tuple[Outline, ...] = ()


def _pin(num, x, y, lead_mm, first=False):
    drill = round(lead_mm + LEAD_CLEARANCE_MM, 3)
    size = round(drill + 2 * ANNULAR_MM, 3)
    return Pad(num, x, y, size, size, drill, "RECT" if first else "ELLIPSE")


def _land(num, x, y, hole_land, first=False):
    drill, size = hole_land
    return Pad(num, x, y, size, size, drill, "RECT" if first else "ELLIPSE")


def _box(x0, y0, x1, y1):
    return Outline(((x0, y0), (x1, y0), (x1, y1), (x0, y1)))


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
    output pins ø1.5.  Note D: input and signal pins ø1.0.  Holes and lands:
    TDK's p.24."""
    xi, xo = -49.7 / 2, 49.7 / 2
    face = (
        _land("-Vin", xi, 6.35 + 3.81, TDK_SIGNAL, first=True),
        _land("CNT", xi, 6.35, TDK_SIGNAL),
        _land("+Vin", xi, -3.175, TDK_SIGNAL),
        _land("-V", xo, 2 * 3.81, TDK_OUTPUT),
        _land("-S", xo, 3.81, TDK_SIGNAL),
        _land("TRM", xo, 0.0, TDK_SIGNAL),
        _land("+S", xo, -3.81, TDK_SIGNAL),
        _land("+V", xo, -2 * 3.81, TDK_OUTPUT),
        _land("BASEPLATE", xi, -14.0, TDK_FG),
        _land("BASEPLATE", xo, 14.0, TDK_FG),
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


def vishay_vy2_flat():
    """VY2472M49Y5US6, Vishay doc 28535 p.2, LYING FLAT: lead spacing 7.5 mm
    (ordering code 17th digit 7, C2251831 '…TV7'), leads ø0.6 ± 0.05, disc
    D 12.5 max, coating extension e 3.0 max.  The disc lies beside its holes,
    its edge past e and the lead bend."""
    edge = 3.0 + LEAD_BEND_MM
    return Drawn("VISHAY_VY2_D12_5_LS7_5_FLAT",
                 (_pin("1", -3.75, 0.0, 0.6 + 0.05, first=True), _pin("2", 3.75, 0.0, 0.6 + 0.05)),
                 outline=(Outline(("CIRCLE", 0.0, edge + 12.5 / 2, 12.5 / 2)),))


def chemicon_kxj_18x25_lying():
    """EKXJ221ELL221MM25S, Chemi-Con KXJ p.1, LYING DOWN: φ18 × 25, lead
    spacing 7.5, leads ø0.8; φD' = φD + 0.5 = 18.5 and L' = L + 1.5 = 26.5
    max.  The can's axis runs away from its holes; + is the square pad."""
    return Drawn("CHEMICON_KXJ_D18X25_LS7_5_LYING",
                 (_pin("+", -3.75, 0.0, 0.8, first=True), _pin("-", 3.75, 0.0, 0.8)),
                 outline=(_box(-18.5 / 2, LEAD_BEND_MM, 18.5 / 2, LEAD_BEND_MM + 26.5),))


def jierr_pa_10x15_lying():
    """PA35V680M10x15, JIERR PA series p.2, LYING DOWN: φ10 × 15, F 5.0 ±
    0.5, leads ø0.6 ± 0.05, φD + 0.5 max = 10.5, L + α = 16 max."""
    return Drawn("JIERR_PA_D10X15_LS5_0_LYING",
                 (_pin("+", -2.5, 0.0, 0.6 + 0.05, first=True), _pin("-", 2.5, 0.0, 0.6 + 0.05)),
                 outline=(_box(-10.5 / 2, LEAD_BEND_MM, 10.5 / 2, LEAD_BEND_MM + 16.0),))


#: Littelfuse 01110501Z (111 501), as LCSC C151075's library land: two pins
#: 5.0 mm apart, ø1.5 holes, ø2.2 lands.  Two clips 17.8 mm apart, row to row,
#: hold a 5 × 20 fuse.
CLIP_PIN_PITCH_MM = 5.0
CLIP_ROWS_MM = 17.8


def fuse_clip_pair():
    """FH201: BOTH clips of the 5 × 20 holder in one footprint, so their
    17.8 mm is fixed in copper, not left to placement.  Pin 1 is the input
    clip, pin 2 the output clip; each clip's two pins are one pin.  The fuse
    body is drawn between them."""
    def clip(num, x):
        return tuple(Pad(num, x, y, 2.2, 2.2, 1.5, "RECT" if (num, y) == ("1", 2.5) else "ELLIPSE")
                     for y in (CLIP_PIN_PITCH_MM / 2, -CLIP_PIN_PITCH_MM / 2))
    return Drawn("FUSE-CLIPS_5X20_PAIR_17_8MM",
                 clip("1", -CLIP_ROWS_MM / 2) + clip("2", CLIP_ROWS_MM / 2),
                 frozenset({"1", "2"}),
                 outline=(_box(-10.0, -2.6, 10.0, 2.6),))


def fuse_in_clips():
    """F201 is never on the board: it sits in the clips FH201A/B, which are,
    and its device says `Convert to PCB: no` so Import Changes leaves it off.
    EasyEDA's Allegro netlist export still refuses a part without a footprint,
    so this marks where the fuse's caps sit: on the clip rows, 17.8 mm apart
    (Littelfuse 01110501Z, FH201A's source)."""
    return Drawn("FUSE-5X20_IN_CLIPS_NOT_ON_PCB", (Pad("1", -8.9, 0.0, 1.0, 1.0),
                                                   Pad("2", 8.9, 0.0, 1.0, 1.0)))


BY_MPN = {
    "CN150B110-12/CO": tdk_cn150b110(),
    "VY2472M49Y5US6": vishay_vy2_flat(),
    "EKXJ221ELL221MM25S": chemicon_kxj_18x25_lying(),
    "PA35V680M10x15": jierr_pa_10x15_lying(),
    "01110501Z": fuse_clip_pair(),
    "EC7BW-110S05": cincon_ec7bw_110(),
    "7448022010": wurth_7448022010(),
    "NET-TIE": net_tie(),
    "0001.2504": fuse_in_clips(),
}
