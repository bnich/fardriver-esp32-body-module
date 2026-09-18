"""What JLC is asked to place, and what the owner solders by hand.

Every fitted part and connector either names the LCSC part JLC places, or is
marked hand-soldered because LCSC has nothing that meets its constraints
(owner, 2026-09-18: Basic parts first; the LCSC part need not be the part
already bought).  A part with neither is a board that cannot be ordered.
"""
import re

import pytest

from tools import netlist

LCSC = re.compile(r"^C\d+$")


@pytest.fixture(scope="module")
def d():
    return netlist.current()


def _fitted(d):
    return [p for p in d.parts if not p.dnp and p.mpn != "NET-TIE"] + list(d.connectors)


#: The inter-board connectors wait on the owner's choice of family
#: (docs/esp32-needed-from-owner.md item 6). When it is made, empty this set.
AWAITING_OWNER = {"J104", "J201", "J202", "J307", "J407", "J308", "J406"}


def test_every_fitted_item_has_a_way_onto_the_board(d):
    missing = {x.refdes for x in _fitted(d) if not (x.lcsc or x.assembly == "hand")}
    assert missing == AWAITING_OWNER, (
        f"no LCSC part and not hand-soldered: {sorted(missing - AWAITING_OWNER)}; "
        f"chosen since, so drop from AWAITING_OWNER: {sorted(AWAITING_OWNER - missing)}")


def test_lcsc_numbers_are_well_formed_and_say_jlc(d):
    for x in _fitted(d):
        if x.lcsc:
            assert LCSC.match(x.lcsc), f"{x.refdes}: {x.lcsc!r}"
            assert x.assembly == "jlc", f"{x.refdes} has {x.lcsc} but assembly {x.assembly!r}"
        if x.assembly == "hand":
            assert not x.lcsc, f"{x.refdes} is hand-soldered and names {x.lcsc}"
            assert "HAND" in x.source.upper(), f"{x.refdes}: say why it is hand-soldered"


def test_one_value_one_part(d):
    """Parts bought by value (same kind, value and package) share one LCSC part:
    two numbers for one value is two setup fees for nothing."""
    seen = {}
    for p in d.parts:
        if p.lcsc and p.kind in ("R", "C"):
            key = (p.kind, p.value, p.package)
            assert seen.setdefault(key, p.lcsc) == p.lcsc, f"{key}: {seen[key]} and {p.lcsc}"
