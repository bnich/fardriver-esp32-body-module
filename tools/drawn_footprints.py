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
from dataclasses import dataclass, field, replace

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
    #: The body, where the part lies beside its holes: silkscreen shapes.  And
    #: any unplated hole the maker's drawing asks for (`Outline.hole`).
    outline: tuple[Outline, ...] = ()
    #: Rectangles (x0, y0, x1, y1) no track or via may cross, from the maker's
    #: drawing.  The project cannot carry them: tools/layout_rules.py lists them
    #: for the owner to draw before routing.
    keepout: tuple[tuple[float, float, float, float], ...] = ()
    #: No other copper within this of any of its pads, from the maker's drawing.
    pad_clearance_mm: float | None = None


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
    return tuple(replace(p, x_mm=round(-p.x_mm, 4) + 0.0) for p in pads)


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


def wurth_cmbnc_type_s():
    """Würth WE-CMBNC Type S, rev 002.000 p.1, 'Recommended Hole Pattern', a
    TOP view (the drawing is first-angle, and the dimension view above the
    front view is the bottom, its mirror): pins 4 · 3 over 1 · 2, 7.7 × 5.0,
    ø1.5 holes.  Windings 1-4 and 2-3.

    ⚠️ ONE land pattern for the whole Type S family, because the family shares
    it: `we7448022010.pdf` p.1 (10 mH, 2 A -- L102) and `we7448023005.pdf` p.1
    (5 mH, 3 A -- L101) give the same 7,7 ± 0,5 × 5,0 ± 0,5 pattern, the same
    ø1,5 holes, the same ø1,0 ref pins, the same 18,0 × 14,0 × 22,0 max body
    and the same 3,5 ± 0,5 pin length.  Type M (`7448030417`, 26,0 mm tall) is
    a DIFFERENT pattern and must never be pointed here."""
    def at(num, x, y, first=False):
        return Pad(num, x, y, 1.5 + 2 * ANNULAR_MM, 1.5 + 2 * ANNULAR_MM, 1.5,
                   "RECT" if first else "ELLIPSE")
    return Drawn("WE_CMBNC_TYPE_S", (at("1", -3.85, -2.5, first=True), at("2", 3.85, -2.5),
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
    """F201 is never on the board: it sits in the holder FH201's two clips,
    which are, and its device says `Convert to PCB: no` so Import Changes
    leaves it off.
    EasyEDA's Allegro netlist export still refuses a part without a footprint,
    so this marks where the fuse's caps sit: on the clip rows, 17.8 mm apart
    (Littelfuse 01110501Z, `fuse_clip_pair`)."""
    return Drawn("FUSE-5X20_IN_CLIPS_NOT_ON_PCB", (Pad("1", -8.9, 0.0, 1.0, 1.0),
                                                   Pad("2", 8.9, 0.0, 1.0, 1.0)))


#: Tag-Connect 'Footprint for TC2030 Plug-of-Nails cable, No-Legs version'
#: (NL-TC2030-Footprint.pdf, rev B, 12/05/19), PCB TOP LAYER view: contact
#: pads ø0.031" ± 0.003 (0.787 mm), NO SOLDER PASTE; non-plated alignment
#: holes ø0.039" ± 0.003 (0.991 mm).
TC2030_PAD_MM = 0.787
TC2030_HOLE_MM = 0.991
TC2030_PITCH_MM = 1.27


def tag_connect_tc2030_nl():
    """J408: the TC2030-NL land, top view, origin at the centre of the pads.
    Pads 1 3 5 run left to right along the lower row and 2 4 6 along the
    upper, 0.050" (1.270 mm) apart both ways.  The alignment holes: one
    0.050" left of the pad array on its centre line, two 0.200" (5.080 mm)
    right of that one and 0.040" (1.016 mm) above and below the centre line
    (the drawing gives the upper one 1.016 mm over the left hole, whose
    centre is 0.025" / 0.635 mm under the upper row).  The pattern is its own
    key: one hole on one side, two on the other.
    Notes 1-2: no track or via in the shaded area between the pads' centres,
    and nothing else within 0.020" (0.51 mm) of a pad.  Note 3: no paste --
    a solder dome under a spring pin makes a bad contact.  Note 4: DNL."""
    p, half = TC2030_PITCH_MM, TC2030_PITCH_MM / 2
    pads = tuple(Pad(str(2 * col + row + 1), (col - 1) * p, (half if row else -half),
                     TC2030_PAD_MM, TC2030_PAD_MM, None, "ELLIPSE", paste=False)
                 for col in range(3) for row in range(2))
    holes = tuple(Outline(("CIRCLE", x, y, TC2030_HOLE_MM / 2), hole=True)
                  for x, y in ((-2 * p, 0.0), (2 * p, 1.016), (2 * p, -1.016)))
    return Drawn("TAG-CONNECT_TC2030-NL", pads, outline=holes,
                 keepout=((-p, -half, p, half),), pad_clearance_mm=0.51)


#: Connectors that are copper only, by `Connector.land`.
LANDS = {"TC2030-NL": tag_connect_tc2030_nl()}


BY_MPN = {
    "CN150B110-12/CO": tdk_cn150b110(),
    "VY2472M49Y5US6": vishay_vy2_flat(),
    "EKXJ221ELL221MM25S": chemicon_kxj_18x25_lying(),
    "PA35V680M10x15": jierr_pa_10x15_lying(),
    "01110501Z": fuse_clip_pair(),
    "EC7BW-110S05": cincon_ec7bw_110(),
    "7448022010": wurth_cmbnc_type_s(),
    "7448023005": wurth_cmbnc_type_s(),
    "NET-TIE": net_tie(),
    "0001.2504": fuse_in_clips(),
}
