"""The shape of the design. Content lives in netlist.py.

Split from netlist.py deliberately: the SHAPE is fixed by the plan and can be
tested against synthetic fixtures, while the CONTENT is transcribed from
plan.md and board-design-record.md and changes as measurements land.
"""
from dataclasses import dataclass, field, replace
from typing import Literal

Board = Literal["HVIN", "CONV", "DRV", "BRAIN"]
Domain = Literal["84V", "12V", "5V", "3V3", "SIGNAL"]
Interface = Literal["HV-LINK", "PWR-UP", "STACK"]
Side = Literal["top", "bottom"]


@dataclass(frozen=True)
class Part:
    refdes: str
    mpn: str
    package: str
    board: Board
    height_mm: float
    #: Absolute max Vds for actives; None for passives and modules.
    vds_max: float | None = None
    side: Side = "top"
    value: str = ""
    dnp: bool = False
    #: Free-text: which document section this part came from.
    source: str = ""


@dataclass(frozen=True)
class Net:
    name: str
    pins: tuple[tuple[str, str], ...]
    domain: Domain = "SIGNAL"
    #: Required iff the net's pins span more than one board.
    interface: Interface | None = None
    #: True if this net reaches a connector that leaves the enclosure.
    leaves_box: bool = False
    #: The GPIO it lands on, for MCU nets. e.g. "GPIO7".
    gpio: str | None = None
    source: str = ""


@dataclass(frozen=True)
class ConnPin:
    pin: int
    net: str
    colour: str = ""


@dataclass(frozen=True)
class Connector:
    refdes: str
    board: Board
    name: str
    pins: tuple[ConnPin, ...]
    leaves_box: bool = True
    #: Contact pitch. BD-3 puts inter-board interfaces on 2.54; BD-4 requires
    #: the 84 V HV-LINK to skip alternate pins for 5.08.
    pitch_mm: float = 2.54
    #: Set for the three inter-board interfaces; None for harness connectors.
    interface: Interface | None = None


@dataclass(frozen=True)
class Design:
    parts: tuple[Part, ...] = ()
    nets: tuple[Net, ...] = ()
    connectors: tuple[Connector, ...] = ()

    def board_of(self, refdes: str) -> Board:
        for p in self.parts:
            if p.refdes == refdes:
                return p.board
        raise KeyError(f"no part {refdes!r}")

    def part(self, refdes: str) -> Part:
        for p in self.parts:
            if p.refdes == refdes:
                return p
        raise KeyError(f"no part {refdes!r}")

    def net(self, name: str) -> Net:
        for n in self.nets:
            if n.name == name:
                return n
        raise KeyError(f"no net {name!r}")

    # -- mutators used by the rule tests to build deliberately-broken fixtures
    def with_net(self, net: Net) -> "Design":
        return replace(self, nets=self.nets + (net,))

    def with_part_height(self, refdes: str, height_mm: float) -> "Design":
        return replace(self, parts=tuple(
            replace(p, height_mm=height_mm) if p.refdes == refdes else p
            for p in self.parts))

    def with_gpio(self, net_name: str, gpio: str) -> "Design":
        return replace(self, nets=tuple(
            replace(n, gpio=gpio) if n.name == net_name else n
            for n in self.nets))

    def without_part(self, refdes: str) -> "Design":
        return replace(self, parts=tuple(
            p for p in self.parts if p.refdes != refdes))
