"""The shape of the design. Content lives in netlist.py.

Every field here exists because its absence let a real defect through the
2026-09-18 audit:

  * `Part.pins` is MANDATORY and lists every pin the part electrically has.
    Without it nothing could tell that two TVS diodes had one leg in the air,
    that a kill-switch FET had no source, or that a converter's enable pin was
    never tied -- and the rules passed all three.
  * `Net.domain` has NO default. A defaulted "SIGNAL" is how a 5 V clamp ended
    up across an 11.4 V node unnoticed: the voltage rule skipped the net.
  * "Leaves the box" is DERIVED from the connectors, never typed by hand. A
    hand-typed flag is a second source of truth, and it drifted.
  * `Connector` carries a height. The stack's whole margin lived in connector
    heights that no rule could see.
  * `height_confirmed` separates a number read off a datasheet from a number
    somebody hoped for. Three "assumed" heights were wrong while the
    datasheets sat on disk.
  * ⛔ EVERY `Literal` FIELD IS CHECKED AT CONSTRUCTION (`__post_init__`),
    against `typing.get_args()` of its own literal so the check and the type
    cannot drift. Three auditors independently found the class this closes
    (2026-09-21, H8): every `== "top"` / `== "sets"` / `== "cable"` comparison
    downstream falls through on `"Top"` / `"Sets"` / `"Cable"`, and the part,
    standoff or interface VANISHES from the model with every gate green -- a
    15 mm body at `side="Top"` in an 11.04 mm gap passed 1479 tests. Heights
    are held to the same standard: `nan` printed `⛔ OVER by nan mm` and
    `✅ PASS` on one run (H11), and `0.0` removed the tallest connector under
    OUTPUTS from the stack (M13). A resistor whose `value` no rule can parse
    is refused for the same reason: `"10K"` skipped D14, GATE-VGS and VR-POWER
    silently (M11). The message names the field, the value and the allowed set.
"""
import math
from dataclasses import dataclass, replace
from typing import Literal, get_args

#: Bottom to top, and `board_params.STACK_ORDER` is the ORDER. ⚠️ CTRL is the
#: fourth board (IO-26/IO-27, 2026-09-22): the controller row outgrew POWER's
#: edge, so it sits on top of LOGIC and mates straight down onto it.
Board = Literal["POWER", "OUTPUTS", "LOGIC", "CTRL"]
Domain = Literal["84V", "12V", "5V", "3V3", "SIGNAL", "GND"]
#: ⚠️ `CTRL-STACK` is the LOGIC ↔ CTRL pair, and it is NOT the `CTRL` ribbon:
#: that is a POWER → OUTPUTS cable. The name is a pair's name on purpose -- the
#: pair is built like STACK, out of the same family, and a reader who sees
#: "CTRL" must not be able to reach for the ribbon's rules.
Interface = Literal["PWR-OUT", "CTRL", "CTRL-STACK", "PWR-LOGIC", "STACK"]
#: How an inter-board interface gets from one board to the other.
Crossing = Literal["pair", "cable"]
#: How a pillar in the stack meets the gap it stands in. ⚠️ The three are NOT
#: degrees of the same thing -- each one is a different claim about what sets
#: the board spacing, and `board_params` checks a different thing for each:
#:   "sets"     its own height IS the spacing. Nothing between the boards may
#:              be taller than it, or the screws crush that thing.
#:   "shimmed"  it is specified deliberately SHORT of a spacing something else
#:              sets (a mated connector pair), with washers taking up the
#:              shortfall, so it only stops the boards flexing apart. Longer
#:              than the gap it un-seats the connectors it was supposed to
#:              leave in charge.
#:   "shim"     the washer itself. It stands between no two decks.
Seating = Literal["sets", "shimmed", "shim"]
Side = Literal["top", "bottom"]
Assembly = Literal["", "jlc", "hand", "loose"]
Kind = Literal[
    "R", "C", "L", "CMCHOKE", "D", "ZENER", "TVS", "FUSE", "FUSECLIP",
    "NFET", "PFET", "IC", "MODULE", "CONVERTER", "MECH",
]

#: Working voltage of each domain. "SIGNAL" is deliberately absent: a net whose
#: voltage nobody can state must not carry a voltage-rated protection part, and
#: rules.py enforces that instead of skipping it.
DOMAIN_VOLTS = {"84V": 84.0, "12V": 12.0, "5V": 5.0, "3V3": 3.3, "GND": 0.0}

#: How each inter-board interface crosses its gap (IO-20, 2026-09-20). The two
#: kinds are held to DIFFERENT truths, and integrity.py reads this table to
#: know which:
#:
#:   "pair"  -- one connector in two halves, body on body. The lower half
#:              stands on top of the lower board and the upper half hangs UNDER
#:              the upper board, so the two FACE each other, and the upper
#:              half's land pattern is generated pre-mirrored ("...-UNDER"):
#:              a same-numbered dual row cannot be aligned by any turn, and
#:              STACK's signals would land on ground.
#:   "cable" -- a loom between two headers. The CABLE carries the orientation,
#:              so the halves need not face each other and neither is mirrored;
#:              what must hold is that both ends have the same contact count
#:              and the same net on the same contact index. That freedom is the
#:              point: no stocked connector spans the POWER -> OUTPUTS gap, so
#:              a loom carries it and the M3x30 standoffs set the gap instead.
#:              ⛔ The freedom is over ALIGNMENT, not over WHICH FACE. Both
#:              halves still look into the gap their cable crosses -- lower on
#:              top, upper hanging under -- because the far side of a board is
#:              a different gap with its own budget, and J311's 10.9 mm posts
#:              on OUTPUTS' top face had 11.04 mm of STACK-pair gap over them.
CROSSING: dict[Interface, Crossing] = {
    "PWR-OUT": "cable",
    "CTRL": "cable",
    "PWR-LOGIC": "pair",
    "STACK": "pair",
    "CTRL-STACK": "pair",
}


def is_cabled(interface: Interface | None) -> bool:
    """True when a cable crosses this interface, False for a mated pair.

    An interface with no entry in CROSSING is NOT silently treated as a cable:
    it falls to the stricter mated-pair checks, and integrity.py reports the
    missing declaration rather than letting a crossing pick its own rules.
    ⛔ Nor is a value outside `Crossing`: "Cable" reads as a pair here, so
    integrity.py holds every value of the table to the literal.
    """
    return CROSSING.get(interface) == "cable"


# --- construction-time validation ---------------------------------------------
def _literal(owner: str, field: str, value, literal, *, optional: bool = False) -> None:
    """`value` is one of `literal`'s members (or None, when `optional`)."""
    if optional and value is None:
        return
    allowed = get_args(literal)
    if value not in allowed:
        raise ValueError(f"{owner}: {field}={value!r} is not one of {allowed}"
                         + (" or None" if optional else "")
                         + " -- every comparison downstream would fall through "
                           "and the thing would vanish from the model")


def _height(owner: str, h, *, zero_ok: bool) -> None:
    """A height is a finite number >= 0, and 0.0 only for a bare land."""
    if isinstance(h, bool) or not isinstance(h, (int, float)) or not math.isfinite(h) \
            or h < 0.0:
        raise ValueError(f"{owner}: height_mm={h!r} must be a finite number >= 0 -- "
                         f"an unknown height is an UNCHECKED height, and nan passes "
                         f"every `total > avail` comparison as False")
    if h == 0.0 and not zero_ok:
        raise ValueError(f"{owner}: height_mm=0.0 removes the body from the stack "
                         f"-- only a connector that is copper only (`land` set) "
                         f"has no height")


@dataclass(frozen=True)
class Part:
    refdes: str
    mpn: str
    package: str
    board: Board
    kind: Kind
    #: EVERY pin that must land on a net. integrity.py fails if any is missing,
    #: landed twice, or landed without being declared.
    pins: tuple[str, ...]
    height_mm: float
    #: True ONLY when height_mm was read off the manufacturer's drawing, and
    #: `source` says which. An unconfirmed height is reported, never trusted.
    height_confirmed: bool = False
    #: Body envelope (w, l) in mm, for the area budget. (0, 0) = negligible.
    footprint_mm: tuple[float, float] = (0.0, 0.0)
    #: Pins deliberately left unconnected. Must be justified in `source`.
    nc: tuple[str, ...] = ()
    #: Maximum continuous working voltage ACROSS the part: V_DS for a FET,
    #: V_RWM for a TVS, rated voltage for a capacitor, V_R for a diode, the
    #: working voltage for a resistor (a 0 R link or net-tie carries none).
    #: REQUIRED for kinds C, D, ZENER, TVS, NFET, PFET, R (rules.py enforces).
    v_max: float | None = None
    #: A TVS's clamping voltage at its rated peak pulse current, from its
    #: datasheet: what the parts behind it must survive. REQUIRED for a TVS.
    v_clamp: float | None = None
    side: Side = "top"
    value: str = ""
    dnp: bool = False
    source: str = ""
    #: The LCSC part JLC places (`C` + digits), or "" when none is chosen.
    lcsc: str = ""
    #: "jlc" when JLC assembles it from `lcsc`; "hand" when the owner buys it
    #: and solders it, because LCSC has nothing that meets its constraints;
    #: "loose" when it is ordered from LCSC with the boards but fitted by the
    #: owner (a part formed to lie flat, a fuse that clips in).
    assembly: Assembly = ""
    #: A through-hole part's leads below its seating plane, the drawing's
    #: maximum, when they are too short or stiff to trim (a brick's pins, a
    #: choke's). None: long leads, trimmed to board_params.TAIL when soldered.
    lead_mm: float | None = None

    def __post_init__(self):
        who = f"Part {self.refdes}"
        _literal(who, "board", self.board, Board)
        _literal(who, "kind", self.kind, Kind)
        _literal(who, "side", self.side, Side)
        _literal(who, "assembly", self.assembly, Assembly)
        _height(who, self.height_mm, zero_ok=False)
        if self.kind == "R" and resistance(self.value) is None:
            raise ValueError(f"{who}: value={self.value!r} states no resistance "
                             f"`resistance()` can read ('4k7', '100R', '1M', "
                             f"'0R') -- D14, GATE-VGS and VR-POWER would skip "
                             f"it silently")


@dataclass(frozen=True)
class Net:
    name: str
    pins: tuple[tuple[str, str], ...]
    domain: Domain                      # no default, on purpose
    #: Required iff the net's pins span more than one board.
    interface: Interface | None = None
    #: The GPIO it lands on, for MCU nets, e.g. "GPIO7". Must match the
    #: U401 pin name ("IO7") -- integrity.py checks the two agree.
    gpio: str | None = None
    source: str = ""

    def __post_init__(self):
        who = f"Net {self.name}"
        _literal(who, "domain", self.domain, Domain)
        _literal(who, "interface", self.interface, Interface, optional=True)


@dataclass(frozen=True)
class ConnPin:
    pin: str
    net: str            # "" = cavity deliberately unused; say why in `note`
    note: str = ""


@dataclass(frozen=True)
class Connector:
    refdes: str
    board: Board
    name: str
    pins: tuple[ConnPin, ...]
    height_mm: float
    height_confirmed: bool = False
    footprint_mm: tuple[float, float] = (0.0, 0.0)
    #: True for harness connectors (wires leave the enclosure). False for the
    #: board-to-board interfaces and the internal service pads.
    leaves_box: bool = True
    pitch_mm: float = 2.54
    #: Set for the inter-board interfaces; None for harness connectors.
    interface: Interface | None = None
    #: Footprint fitted, function parked (e.g. the display under D19). Its
    #: protection parts may be DNP without that counting as a gap.
    parked: bool = False
    source: str = ""
    #: As on Part: the LCSC part, and who fits it.
    lcsc: str = ""
    assembly: Assembly = ""
    #: The LCSC part of the loose mating half the owner wires and plugs in (a
    #: screw plug), or "" when there is none.  Ordered with the boards, not placed.
    plug: str = ""
    #: Footprint laid out, part not fitted: JLC skips it, and the owner fits it
    #: when it is wanted.
    dnp: bool = False
    #: The face of its board it stands on.  The upper half of an inter-board
    #: pair hangs under its board, facing the half below.
    side: Side = "top"
    #: As on Part: its pins below the seating plane, the drawing's maximum.
    lead_mm: float | None = None
    #: How far its mated plug stands out past the board edge, from the plug's
    #: drawing; the wire leaves straight out of the back of it.
    overhang_mm: float = 0.0
    #: A land drawn from its maker's drawing (`drawn_footprints.LANDS`), for a
    #: connector that is copper only: a Tag-Connect pad set.
    land: str = ""
    #: The POSITIVE keying that makes a wrong mate mechanically impossible,
    #: named from the maker's drawing (a polarising notch, an omitted circuit,
    #: a latch that only closes one way). "" says nothing prevents it.
    #: ⛔ A CABLED crossing has no other defence: a mated pair is soldered down
    #: facing its own half at a fixed spacing and survives being mated reversed
    #: by being a palindrome, while a loom is presented by hand every time it
    #: is serviced and can be offered to its header either way round. Rule
    #: BUS-ORDER asks a pair for the palindrome and a cable for this.
    keyed: str = ""
    #: Continuous current ONE contact may carry, from the maker's drawing, with
    #: `source` saying whether that figure is derated when every circuit is
    #: loaded. None: the drawing states none, so nothing may be assumed.
    contact_a: float | None = None
    #: The drill its maker's PCB layout calls for, when the generic 1.0 mm of a
    #: 0.64 mm square post does not take its post (a 1.14 mm VH post needs
    #: 1.65). None: the generic land pattern.
    hole_mm: float | None = None

    def __post_init__(self):
        who = f"Connector {self.refdes}"
        _literal(who, "board", self.board, Board)
        _literal(who, "side", self.side, Side)
        _literal(who, "assembly", self.assembly, Assembly)
        _literal(who, "interface", self.interface, Interface, optional=True)
        _height(who, self.height_mm, zero_ok=bool(self.land))


@dataclass(frozen=True)
class Standoff:
    """A pillar screwed between two decks of the stack.

    ⭐ It is the third kind of thing in the height model, and the reason it is
    not a `Part`: a part STANDS IN a gap and `board_params` clears it by
    CLEARANCE, and a connector pair's mated bodies ARE the gap. A standoff
    DEFINES a gap -- the boards sit exactly where it puts them -- so counting
    it as a part would derive a gap 1.0 mm taller than the standoff and fail
    the connector stop the nylon one is deliberately shimmed under.

    It carries no refdes because nothing is placed on a board for it: the four
    M3 corners are already board geometry, and this is what goes through them.
    """
    #: The maker's part, e.g. "Shuntian M3X30". Named in every verdict, so it
    #: has to read as a part number and not as a description.
    name: str
    lcsc: str
    qty: int
    #: Its own length, in mm. For "sets" that IS the board spacing.
    height_mm: float
    #: The two decks it stands between, bottom first, e.g. ("POWER",
    #: "OUTPUTS"). ⛔ () for a "shim", which stands between nothing.
    between: tuple[str, ...] = ()
    seating: Seating = "sets"
    source: str = ""

    def __post_init__(self):
        who = f"Standoff {self.name}"
        _literal(who, "seating", self.seating, Seating)
        _height(who, self.height_mm, zero_ok=False)


@dataclass(frozen=True)
class Design:
    parts: tuple[Part, ...] = ()
    nets: tuple[Net, ...] = ()
    connectors: tuple[Connector, ...] = ()
    #: The hardware that holds the decks apart. Not placed, so not in `parts`;
    #: `board_params.layer_gaps` reads it, and a design without any (a test
    #: fixture) simply has no gap defined by one.
    standoffs: tuple[Standoff, ...] = ()

    # -- lookups ------------------------------------------------------------
    def part(self, refdes: str) -> Part:
        for p in self.parts:
            if p.refdes == refdes:
                return p
        raise KeyError(f"no part {refdes!r}")

    def connector(self, refdes: str) -> Connector:
        for c in self.connectors:
            if c.refdes == refdes:
                return c
        raise KeyError(f"no connector {refdes!r}")

    def has(self, refdes: str) -> bool:
        return any(p.refdes == refdes for p in self.parts) or \
            any(c.refdes == refdes for c in self.connectors)

    def board_of(self, refdes: str) -> Board:
        for p in self.parts:
            if p.refdes == refdes:
                return p.board
        for c in self.connectors:
            if c.refdes == refdes:
                return c.board
        raise KeyError(f"no part or connector {refdes!r}")

    def net(self, name: str) -> Net:
        for n in self.nets:
            if n.name == name:
                return n
        raise KeyError(f"no net {name!r}")

    def net_of(self, refdes: str, pin: str) -> Net | None:
        for n in self.nets:
            if (refdes, pin) in n.pins:
                return n
        return None

    def nets_of(self, refdes: str) -> tuple[Net, ...]:
        return tuple(n for n in self.nets if any(r == refdes for r, _ in n.pins))

    def leaves_box(self, net_name: str) -> bool:
        """DERIVED: the net has a pin on a connector whose wires leave the box."""
        net = self.net(net_name)
        refs = {r for r, _ in net.pins}
        return any(c.leaves_box and c.refdes in refs for c in self.connectors)

    # -- mutators: build deliberately-broken fixtures for the rule tests ------
    def with_net(self, net: Net) -> "Design":
        return replace(self, nets=self.nets + (net,))

    def with_part(self, part: Part) -> "Design":
        return replace(self, parts=self.parts + (part,))

    def replace_part(self, refdes: str, **changes) -> "Design":
        assert any(p.refdes == refdes for p in self.parts), refdes
        return replace(self, parts=tuple(
            replace(p, **changes) if p.refdes == refdes else p
            for p in self.parts))

    def replace_net(self, name: str, **changes) -> "Design":
        assert any(n.name == name for n in self.nets), name
        return replace(self, nets=tuple(
            replace(n, **changes) if n.name == name else n for n in self.nets))

    def replace_connector(self, refdes: str, **changes) -> "Design":
        assert any(c.refdes == refdes for c in self.connectors), refdes
        return replace(self, connectors=tuple(
            replace(c, **changes) if c.refdes == refdes else c
            for c in self.connectors))

    def without_part(self, refdes: str) -> "Design":
        """Remove a part AND its pins from every net (an honest deletion)."""
        return replace(
            self,
            parts=tuple(p for p in self.parts if p.refdes != refdes),
            nets=tuple(replace(n, pins=tuple(
                (r, q) for r, q in n.pins if r != refdes)) for n in self.nets))

    def without_pin(self, refdes: str, pin: str) -> "Design":
        """Lift one leg of a part off its net -- the floating-terminal fixture."""
        return replace(self, nets=tuple(replace(n, pins=tuple(
            (r, q) for r, q in n.pins if (r, q) != (refdes, pin)))
            for n in self.nets))


def resistance(value: str) -> float | None:
    """'4k7' -> 4700, '100R' -> 100, '1k00 1%' -> 1000, '0R' -> 0; None if the
    value states no resistance."""
    import re
    m = re.match(r"^(\d+)([kRM])(\d*)", value or "")
    if not m:
        return None
    whole, unit, frac = m.groups()
    return float(f"{whole}.{frac or 0}") * {"R": 1, "k": 1e3, "M": 1e6}[unit]
