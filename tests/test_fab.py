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
AWAITING_OWNER = {"J104", "J201", "J202", "J311", "J307", "J407", "J308", "J406"}


def test_every_fitted_item_has_a_way_onto_the_board(d):
    missing = {x.refdes for x in _fitted(d) if not (x.lcsc or x.assembly == "hand")}
    assert missing == AWAITING_OWNER, (
        f"no LCSC part and not hand-soldered: {sorted(missing - AWAITING_OWNER)}; "
        f"chosen since, so drop from AWAITING_OWNER: {sorted(AWAITING_OWNER - missing)}")


def test_lcsc_numbers_are_well_formed_and_say_who_fits_them(d):
    """An LCSC part is JLC's to place, or 'loose': ordered with the boards and
    fitted by the owner."""
    for x in _fitted(d):
        if x.lcsc:
            assert LCSC.match(x.lcsc), f"{x.refdes}: {x.lcsc!r}"
            assert x.assembly in ("jlc", "loose"), (
                f"{x.refdes} has {x.lcsc} but assembly {x.assembly!r}")
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


# --- every wire into the box lands on a pluggable screw terminal ---------------------
#: LOCKING pluggable terminal blocks, Kangnex at 3.81 and 5.08 mm and Kefa at
#: 7.62 mm (the RM header's flanges carry the nuts the KM plug's two screws draw into), (pitch mm, positions) -> (the right-angle
#: header JLC places, the loose screw plug the owner wires).  Typed from LCSC.
TERMINALS = {
    (3.81, 2): ("C133147", "C62113"), (3.81, 3): ("C160129", "C106871"),
    (3.81, 4): ("C160127", "C157472"), (3.81, 5): ("C50223", "C50222"),
    (3.81, 6): ("C160126", "C157470"),
    (3.81, 7): ("C489994", "C489981"), (3.81, 9): ("C489995", "C384932"),
    (5.08, 3): ("C49238", "C49239"), (5.08, 4): ("C122715", "C122716"),
    (7.62, 6): ("C441304", "C441154"),
}


def test_every_wire_into_the_box_lands_on_a_pluggable_screw_terminal(d):
    """Owner, 2026-09-18: screw terminals for every connection onto the boards,
    so nothing is crimped and no mating housing has to be matched.  The plug is
    wired outside the box and pushed in from the board edge, where the stack
    cannot block a screwdriver.  The plug screws to the header's flanges:
    retention under vibration, as the plan's vibration rule asks."""
    harness = [c for c in d.connectors if c.leaves_box]
    assert len(harness) == 13
    for c in harness:
        assert TERMINALS.get((c.pitch_mm, len(c.pins))) == (c.lcsc, c.plug), c.refdes
        assert c.assembly == "jlc" and c.height_confirmed, c.refdes


#: A pitch per job, so a plug of one job cannot seat in a header of another:
#: pack voltage alone at 7.62 mm (400 V IEC); the brake and kill exits alone at
#: 5.08 mm; lamps, pods and serial at 3.81 mm (160 V IEC).
FAMILY = {"J101": 7.62, "J306": 5.08, "J309": 5.08}


def test_each_job_has_its_own_terminal_pitch(d):
    for c in d.connectors:
        if c.leaves_box:
            assert c.pitch_mm == FAMILY.get(c.refdes, 3.81), c.refdes


def test_nothing_but_a_harness_terminal_has_a_plug(d):
    assert all(not c.plug for c in d.connectors if not c.leaves_box)
