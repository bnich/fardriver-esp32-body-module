"""The model refuses what the rules cannot see.

Eight `Literal` types and not one runtime check (audit 2026-09-21, H8, found
by three auditors independently): every `== "top"` / `== "sets"` / `== "cable"`
downstream fell through on `"Top"` / `"Sets"` / `"Cable"` and the part,
standoff or interface VANISHED from the model with every gate green -- a 15 mm
body at `side="Top"` in an 11.04 mm gap passed 1479 tests. The same for a
height that is not a number (H11: `⛔ OVER by nan mm` and `✅ PASS` on one run),
a height of 0.0 (M13: the tallest connector under OUTPUTS, gone from the
stack) and a resistor value no rule can parse (M11: "10K" skipped D14,
GATE-VGS and VR-POWER).

Every test here is one mutation of a field the model now validates at
construction, and the control is the real netlist constructing clean.
"""
import math
from typing import get_args

import pytest

from tools import board_params as bp, integrity, netlist
from tools.model import (CROSSING, Assembly, Board, ConnPin, Connector, Crossing,
                         Domain, Interface, Kind, Net, Part, Seating, Side, Standoff)


def part(**kw):
    base = dict(refdes="R1", mpn="R-10k", package="0805", board="LOGIC", kind="R",
                pins=("1", "2"), height_mm=0.6, value="10k")
    return Part(**{**base, **kw})


def connector(**kw):
    base = dict(refdes="J1", board="OUTPUTS", name="fixture",
                pins=(ConnPin("1", "V12"),), height_mm=8.5)
    return Connector(**{**base, **kw})


def standoff(**kw):
    base = dict(name="M3X30", lcsc="C0", qty=4, height_mm=30.0,
                between=("POWER", "OUTPUTS"))
    return Standoff(**{**base, **kw})


# --- the control: everything the design actually constructs is accepted -------
def test_the_real_netlist_constructs_clean():
    d = netlist.current()
    assert len(d.parts) > 100 and len(d.connectors) > 10 and d.standoffs


def test_the_board_literal_and_the_stack_order_are_one_set():
    """`board` is checked against the literal because `model` cannot import
    `board_params`; this holds the two homes together."""
    assert set(get_args(Board)) == set(bp.STACK_ORDER)


def test_the_crossing_table_is_clean_today():
    assert all(v in get_args(Crossing) for v in CROSSING.values())


# --- one mutation per literal, each raising at construction -------------------
@pytest.mark.parametrize("field, bad, literal", [
    ("board", "Logic", Board),
    ("kind", "Resistor", Kind),
    ("side", "Top", Side),
    ("assembly", "JLC", Assembly),
])
def test_a_part_field_outside_its_literal_is_refused(field, bad, literal):
    with pytest.raises(ValueError) as e:
        part(**{field: bad})
    msg = str(e.value)
    assert msg.startswith("Part R1: ") and f"{field}={bad!r}" in msg
    assert str(get_args(literal)) in msg


@pytest.mark.parametrize("field, bad, literal", [
    ("board", "Outputs", Board),
    ("side", "Bottom", Side),
    ("assembly", "Loose", Assembly),
    ("interface", "PWR-SIDEWAYS", Interface),
    ("interface", "stack", Interface),
])
def test_a_connector_field_outside_its_literal_is_refused(field, bad, literal):
    with pytest.raises(ValueError) as e:
        connector(**{field: bad})
    msg = str(e.value)
    assert msg.startswith("Connector J1: ") and f"{field}={bad!r}" in msg
    assert str(get_args(literal)) in msg


@pytest.mark.parametrize("field, bad, literal", [
    ("domain", "12v", Domain),
    ("domain", "SIG", Domain),
    ("interface", "Stack", Interface),
])
def test_a_net_field_outside_its_literal_is_refused(field, bad, literal):
    kw = dict(name="X", pins=(("R1", "1"), ("R2", "1")), domain="12V")
    kw[field] = bad
    with pytest.raises(ValueError) as e:
        Net(**kw)
    msg = str(e.value)
    assert msg.startswith("Net X: ") and f"{field}={bad!r}" in msg
    assert str(get_args(literal)) in msg


def test_a_standoff_seating_outside_its_literal_is_refused():
    """L3: `seating="Sets"` was silently neither kind -- the 30 mm pillar was
    inert and the report said "shimmed short" on a gap with no connectors."""
    with pytest.raises(ValueError, match=r"Standoff M3X30: seating='Sets' is not one of "
                                         r"\('sets', 'shimmed', 'shim'\)"):
        standoff(seating="Sets")
    assert str(get_args(Seating)) == "('sets', 'shimmed', 'shim')"


def test_none_is_accepted_only_where_the_field_is_optional():
    assert connector(interface=None).interface is None
    assert Net("X", (("R1", "1"), ("R2", "1")), "GND", interface=None).interface is None
    with pytest.raises(ValueError, match="board=None"):
        part(board=None)
    with pytest.raises(ValueError, match="side=None"):
        connector(side=None)


# --- L4: the CROSSING table's VALUES, checked by integrity ---------------------
def test_a_crossing_value_outside_the_literal_is_an_integrity_problem(monkeypatch):
    """`is_cabled` reads anything that is not exactly "cable" as a pair, so
    "Cable" makes a loom answer to the mated-pair rules; the value is held to
    the literal as the key is held to the table."""
    d = netlist.current()
    assert integrity.check(d) == []
    monkeypatch.setitem(CROSSING, "PWR-OUT", "Cable")
    errs = integrity.check(d)
    assert any("model.CROSSING['PWR-OUT'] is 'Cable', not one of ('pair', 'cable')"
               in e for e in errs), errs


# --- H11 / M13: heights are finite numbers, and 0.0 is a bare land only --------
@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, -0.01, None, True, "8.5"])
def test_a_part_height_that_is_not_a_finite_number_is_refused(bad):
    with pytest.raises(ValueError, match=r"Part R1: height_mm=.* must be a finite number"):
        part(height_mm=bad)


@pytest.mark.parametrize("bad", [math.nan, -1.0, None])
def test_a_connector_height_that_is_not_a_finite_number_is_refused(bad):
    with pytest.raises(ValueError, match=r"Connector J1: height_mm=.* must be a finite"):
        connector(height_mm=bad)


@pytest.mark.parametrize("bad", [math.nan, -1.0, None])
def test_a_standoff_height_that_is_not_a_finite_number_is_refused(bad):
    """H11: a nan standoff printed `⛔ OVER by nan mm` and `✅ PASS` on one run,
    because `total > avail` is False for nan."""
    with pytest.raises(ValueError, match=r"Standoff M3X30: height_mm=.* must be a finite"):
        standoff(height_mm=bad)


def test_a_zero_height_removes_the_body_from_the_stack_and_is_refused():
    """M13: J311 -- 10.9 mm, the tallest thing under OUTPUTS -- at 0.0, and no
    HT fired. On the real netlist, and on a part and a standoff too."""
    d = netlist.current()
    assert d.connector("J311").height_mm == 10.9 and not d.connector("J311").land
    with pytest.raises(ValueError, match="Connector J311: height_mm=0.0 removes the body"):
        d.replace_connector("J311", height_mm=0.0)
    with pytest.raises(ValueError, match="Part R1: height_mm=0.0 removes the body"):
        part(height_mm=0.0)
    with pytest.raises(ValueError, match="Standoff M3X30: height_mm=0.0 removes the body"):
        standoff(height_mm=0.0)


def test_a_bare_land_is_the_one_connector_with_no_height():
    """J408 is a Tag-Connect TC2030-NL: copper only, so 0.0 is its height. The
    exemption is `land`, not the refdes."""
    d = netlist.current()
    j408 = d.connector("J408")
    assert j408.land and j408.height_mm == 0.0
    assert connector(height_mm=0.0, land="TC2030-NL").height_mm == 0.0
    with pytest.raises(ValueError, match="height_mm=0.0 removes the body"):
        connector(height_mm=0.0, land="")


# --- M11: a resistor states a resistance the rules can read --------------------
@pytest.mark.parametrize("bad", ["10K", "4.7k", "", "as marked", "10 k"])
def test_a_resistor_value_no_rule_can_parse_is_refused(bad):
    """`"10K"` gave D14 0, GATE-VGS 0, VR-POWER 0: every resistor rule skipped
    it silently. The spellings the netlist uses are '4k7', '100R', '1k00 1%',
    '0R' -- the ones `resistance()` reads."""
    with pytest.raises(ValueError, match=rf"Part R1: value={bad!r} states no resistance"):
        part(value=bad)


@pytest.mark.parametrize("good", ["10k", "4k7", "100R", "1k00 1%", "0R", "1M", "2k0 1%"])
def test_every_spelling_the_netlist_uses_is_accepted(good):
    assert part(value=good).value == good


def test_only_a_resistor_is_held_to_a_resistance():
    assert part(kind="C", value="", v_max=16.0).value == ""
    assert part(kind="MECH", value="").value == ""


def test_the_real_netlist_mutated_at_a_resistor_value_is_refused():
    d = netlist.current()
    with pytest.raises(ValueError, match="Part R110: value='10K' states no resistance"):
        d.replace_part("R110", value="10K")
