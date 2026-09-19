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
"""
from dataclasses import dataclass, replace
from typing import Literal

Board = Literal["HVIN", "CONV", "DRV", "BRAIN"]
Domain = Literal["84V", "12V", "5V", "3V3", "SIGNAL", "GND"]
Interface = Literal["HV-LINK", "PWR-UP", "PWR-BRAIN", "STACK"]
Side = Literal["top", "bottom"]
Assembly = Literal["", "jlc", "hand"]
Kind = Literal[
    "R", "C", "L", "CMCHOKE", "D", "ZENER", "TVS", "FUSE", "FUSECLIP",
    "NFET", "PFET", "IC", "MODULE", "CONVERTER", "MECH",
]

#: Working voltage of each domain. "SIGNAL" is deliberately absent: a net whose
#: voltage nobody can state must not carry a voltage-rated protection part, and
#: rules.py enforces that instead of skipping it.
DOMAIN_VOLTS = {"84V": 84.0, "12V": 12.0, "5V": 5.0, "3V3": 3.3, "GND": 0.0}


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
    side: Side = "top"
    value: str = ""
    dnp: bool = False
    source: str = ""
    #: The LCSC part JLC places (`C` + digits), or "" when none is chosen.
    lcsc: str = ""
    #: "jlc" when JLC assembles it from `lcsc`; "hand" when the owner buys it
    #: and solders it, because LCSC has nothing that meets its constraints.
    assembly: Assembly = ""
    #: A through-hole part's leads below its seating plane, the drawing's
    #: maximum, when they are too short or stiff to trim (a brick's pins, a
    #: choke's). None: long leads, trimmed to board_params.TAIL when soldered.
    lead_mm: float | None = None


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
    #: board-to-board interfaces and the internal service header.
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


@dataclass(frozen=True)
class Design:
    parts: tuple[Part, ...] = ()
    nets: tuple[Net, ...] = ()
    connectors: tuple[Connector, ...] = ()

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
