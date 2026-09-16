"""mm <-> EasyEDA Pro's native unit.

`fmt2 general/conventions.md`, verbatim: "all coordinates, lengths, and sizes
use 0.01 inch as the unit".  So 1 unit = 0.254 mm and 1 inch = 100 units.

Geometry is carried in millimetres as float everywhere else in this project and
converted exactly once, here, at emit time.  Never store native units in the
netlist: a number whose unit you have to remember is a number you will
eventually get wrong.

The board envelope is not a round number of units -- 42 mm is 165.354 -- so
conversion deliberately does NOT round.  Rounding belongs at the point a
specific record needs an integer, where the record format says so, not here
where it would silently accumulate.
"""

MM_PER_UNIT = 0.254
"""One native unit expressed in millimetres (0.01 inch)."""


def mm_to_units(mm: float) -> float:
    """Millimetres -> native units. No rounding; see module docstring."""
    return mm / MM_PER_UNIT


def units_to_mm(units: float) -> float:
    """Native units -> millimetres."""
    return units * MM_PER_UNIT
