"""Invariants of the netlist ITSELF -- not design rules.

tools/rules.py owns the design's constraints (BD-2, BD-4, ADC1, strapping,
D14, TVS, heights) and each of those is proven against a broken fixture there.
What is left over is the smaller, duller question these tests answer: is this
data even a netlist? A refdes that appears in a net but in no parts table, a
net with one end, a board name nobody recognises and a cross-board net that
names no interface are all transcription failures that would sail straight
past every rule in rules.py and land in the emitted schematic.

⚠️ These are the tests a transcription needs. They cannot tell you the netlist
is RIGHT -- only that it is self-consistent. `rules.check_all(netlist.current())`
is the part that has opinions, and it currently fires; see this file's sibling
report and the ⛔/⬜ notes in tools/netlist.py.
"""
import math

import pytest

from tools import netlist
from tools.netlist import BOARDS


@pytest.fixture(scope="module")
def d():
    return netlist.current()


def _refdes_board(design):
    """refdes -> board, over parts AND connectors: a net pin may legitimately
    land on either, and `Design.part` only knows about parts."""
    m = {p.refdes: p.board for p in design.parts}
    m.update({c.refdes: c.board for c in design.connectors})
    return m


# --- the four the plan asks for, plus the converse of the interface rule -----

def test_every_net_pin_refers_to_a_real_part_or_connector(d):
    known = _refdes_board(d)
    dangling = sorted({
        f"{net.name}:{refdes}.{pin}"
        for net in d.nets for refdes, pin in net.pins if refdes not in known
    })
    assert dangling == [], f"net pins on nothing: {dangling}"


def test_every_part_is_on_a_known_board(d):
    assert BOARDS == ("HVIN", "CONV", "DRV", "BRAIN")
    strays = [(p.refdes, p.board) for p in d.parts if p.board not in BOARDS]
    assert strays == []
    strays = [(c.refdes, c.board) for c in d.connectors if c.board not in BOARDS]
    assert strays == []


def test_no_duplicate_refdes(d):
    # parts and connectors share one refdes space -- the schematic does too
    seen = [p.refdes for p in d.parts] + [c.refdes for c in d.connectors]
    dupes = sorted({r for r in seen if seen.count(r) > 1})
    assert dupes == [], f"duplicate refdes: {dupes}"


def test_every_cross_board_net_declares_an_interface(d):
    known = _refdes_board(d)
    undeclared = sorted(
        net.name for net in d.nets
        if len({known[r] for r, _ in net.pins}) > 1 and net.interface is None
    )
    assert undeclared == [], (
        f"nets span two boards with no interface named: {undeclared}")


def test_no_single_board_net_claims_an_interface(d):
    # model.Net: "Required iff the net's pins span more than one board."
    known = _refdes_board(d)
    bogus = sorted(
        net.name for net in d.nets
        if net.interface is not None and len({known[r] for r, _ in net.pins}) == 1
    )
    assert bogus == [], f"interface named on a single-board net: {bogus}"


def test_every_net_has_at_least_two_pins(d):
    stubs = sorted(f"{n.name}({len(n.pins)})" for n in d.nets if len(n.pins) < 2)
    assert stubs == [], (
        f"a net needs two ends; these have fewer: {stubs}. The inventory's "
        f"one-ended nets (ACC_PLUS, BW5V, DISP_V12, UART2_RX, START_SENSE, "
        f"USB_VBUS) are documented gaps and are deliberately NOT here")


# --- guards on the transcription itself -------------------------------------

def test_the_four_corrections_stuck(d):
    # 1. the Y2 caps moved to CONV, at the converter input terminals (Q7)
    y2 = [p for p in d.parts if p.mpn == "VY2472M49Y5US6"]
    assert len(y2) == 4
    assert {p.board for p in y2} == {"CONV"}
    # 2. DRV got its TVS (Q6)
    drv_tvs = [p for p in d.parts
               if p.board == "DRV" and p.mpn == "PESD5V0S4UD"]
    assert len(drv_tvs) == 6, "one quad array per DRV harness connector"
    # 3. BRAIN's regulator exists as a part with no BOM line (Q3)
    assert d.part("U405").mpn == "TBD-3V3-REG"
    # 4. CONV's ceiling is the Y2 discs', not the brick's
    from tools.board_params import LAYER_CEILING_MM
    assert LAYER_CEILING_MM["CONV"] == pytest.approx(14.0)


def test_every_entry_cites_a_source(d):
    assert [p.refdes for p in d.parts if not p.source] == []
    assert [n.name for n in d.nets if not n.source] == []


def test_placeholders_are_visible_not_invented(d):
    """⬜ values are TBD or NaN -- never a plausible-looking number."""
    tbd_values = sorted(p.refdes for p in d.parts if p.value == "TBD")
    assert tbd_values == ["C105", "D102", "D307", "R101", "R107", "R108",
                          "R432", "R433", "R434", "R435"], tbd_values
    unknown_height = sorted(p.refdes for p in d.parts if math.isnan(p.height_mm))
    # ⛔ NaN can never trip rules.layer_height_ceilings: an unknown height is an
    # UNCHECKED height. Keep the list short and keep it honest.
    assert unknown_height == ["D102", "D103", "D307", "U405"], unknown_height


def test_bd14_puts_the_electrolytics_underside(d):
    for ref in ("C201", "C202"):
        assert d.part(ref).side == "bottom", (
            f"{ref} hangs into the layer below (BD-14); topside it would break "
            f"CONV's 14 mm ceiling at 18 mm")


def test_the_gpio_map_matches_the_pin_assignment_table(d):
    """§4.4: 30 signals on 31 usable pins, one spare (GPIO10)."""
    assigned = {n.gpio: n.name for n in d.nets if n.gpio}
    assert len(assigned) == 30, sorted(assigned)
    # R5/R6: the pins that do not exist or belong to the flash are never used
    for n in list(range(22, 33)):
        assert f"GPIO{n}" not in assigned
    # R4: GPIO43 emits the ROM boot log at every reset
    assert "GPIO43" not in assigned
    # R11: the analog signals are on ADC1
    for net in ("KEY_SENSE", "V12_SENSE", "CS1", "CS2"):
        pin = int(d.net(net).gpio.removeprefix("GPIO"))
        assert 1 <= pin <= 10, f"{net} on GPIO{pin}: ADC2 dies with WiFi"


def test_no_84v_net_touches_a_logic_board(d):
    """BD-2 in this file's own terms -- rules.py proves the rule fires."""
    boards = _refdes_board(d)
    for net in d.nets:
        if net.domain == "84V":
            assert {boards[r] for r, _ in net.pins} <= {"HVIN", "CONV"}, net.name
