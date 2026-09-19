"""Every branch of tools/integrity.py, proven to fire.

integrity.py is the gate underneath the rules: does every leg of every part
go somewhere. On 2026-09-18 two TVS diodes had one terminal each, a kill FET
had no source, and three nets "crossed" a connector with no contact -- with
every rule green. Each test here breaks a small, clean, two-board design in
exactly one way and asserts on the category of the report AND on who it names,
so a check that fires for the wrong reason does not pass.
"""
from dataclasses import replace

import pytest

from tools import integrity
from tools.model import ConnPin, Connector, Design, Net, Part


def _r(ref, board):
    return Part(ref, "R-10k", "0805", board, "R", ("1", "2"), 0.6, value="10k")


def _conn(ref, board, name, nets, **kw):
    return Connector(ref, board, name,
                     tuple(ConnPin(str(i + 1), n) for i, n in enumerate(nets)),
                     height_mm=3.0, **kw)


STACK = ("SIG", "GND", "V3P3")
OK = Design(
    parts=(
        Part("U401", "ESP32-S3-WROOM-1-N8", "MODULE", "BRAIN", "MODULE",
             ("3V3", "GND", "IO5"), 3.1, nc=("IO6",)),
        _r("R1", "BRAIN"),                       # pull-up
        _r("R2", "DRV"),                         # series, lever side
        Part("C1", "C-100n", "0805", "BRAIN", "C", ("1", "2"), 0.9, v_max=16.0),
        Part("D1", "SMBJ15A", "SMB", "DRV", "TVS", ("A", "K"), 2.5, v_max=15.0,
             dnp=True),
    ),
    nets=(
        Net("SIG", (("U401", "IO5"), ("R1", "1"), ("J406", "1"), ("J308", "1"),
                    ("R2", "1")), domain="3V3", interface="STACK", gpio="GPIO5"),
        Net("V3P3", (("U401", "3V3"), ("R1", "2"), ("C1", "1"), ("J406", "3"),
                     ("J308", "3")), domain="3V3", interface="STACK"),
        Net("GND", (("U401", "GND"), ("C1", "2"), ("J406", "2"), ("J308", "2"),
                    ("J306", "2"), ("D1", "A")), domain="GND", interface="STACK"),
        Net("LEVER", (("R2", "2"), ("J306", "1"), ("D1", "K")), domain="12V"),
    ),
    connectors=(
        _conn("J406", "BRAIN", "STACK", STACK, leaves_box=False, interface="STACK",
              side="bottom"),
        _conn("J308", "DRV", "STACK", STACK, leaves_box=False, interface="STACK"),
        _conn("J306", "DRV", "Lever", ("LEVER", "GND", "")),
    ),
)


def problems(d: Design, category: str) -> list[str]:
    return [e for e in integrity.check(d) if e.startswith(category + ":")]


def add_pin(d: Design, net: str, ref: str, pin: str) -> Design:
    return d.replace_net(net, pins=d.net(net).pins + ((ref, pin),))


def test_the_clean_design_is_clean():
    assert integrity.check(OK) == []


# ── identity ─────────────────────────────────────────────────────────────────
def test_duplicate_part_refdes():
    errs = problems(OK.with_part(_r("R1", "DRV")), "identity")
    assert errs and "R1" in errs[0] and "2 times" in errs[0]


def test_a_connector_may_not_share_a_refdes_with_a_part():
    bad = replace(OK, connectors=OK.connectors + (_conn("R2", "DRV", "clash", ()),))
    assert any("R2" in e for e in problems(bad, "identity"))


def test_duplicate_net_name():
    bad = OK.with_net(Net("LEVER", (), domain="12V"))
    assert any("'LEVER'" in e for e in problems(bad, "identity"))


# ── every (refdes, pin) lands once, on something that exists ─────────────────
def test_dangling_refdes():
    errs = problems(add_pin(OK, "LEVER", "Q999", "D"), "dangling")
    assert errs and "Q999" in errs[0] and "'LEVER'" in errs[0]


def test_a_pin_on_two_nets_is_a_short():
    """Audit N10: the brick's -Vout on V12 AND GND passed every test."""
    errs = problems(add_pin(OK, "GND", "R1", "2"), "shorted")
    assert errs and "R1.2" in errs[0] and "V3P3" in errs[0] and "GND" in errs[0]


# ── declared pins land; nothing undeclared lands ─────────────────────────────
def test_a_floating_pin():
    """Audit F-6 / F-2: the one-legged TVS, the FET with no source."""
    errs = problems(OK.without_pin("R2", "2"), "floating")
    assert errs == [e for e in errs if "R2.2" in e] != []


def test_a_floating_pin_on_a_dnp_part_is_still_floating():
    errs = problems(OK.without_pin("D1", "A"), "floating")
    assert errs and "D1.A" in errs[0] and "DNP" in errs[0]


def test_every_pin_of_a_removed_net_floats():
    bad = replace(OK, nets=tuple(n for n in OK.nets if n.name != "V3P3"))
    named = " ".join(problems(bad, "floating"))
    assert "U401.3V3" in named and "R1.2" in named and "C1.1" in named


def test_an_undeclared_pin():
    errs = problems(add_pin(OK, "LEVER", "R2", "3"), "undeclared")
    assert errs and "R2.3" in errs[0]


def test_a_part_with_no_pins():
    bad = OK.with_part(Part("X1", "MYSTERY", "?", "DRV", "MECH", (), 1.0))
    assert any("X1" in e and "declares no pins" in e for e in problems(bad, "pins"))


def test_a_pin_both_declared_and_no_connect():
    bad = OK.replace_part("U401", nc=("IO6", "IO5"))
    assert any("IO5" in e and "both" in e for e in problems(bad, "pins"))


def test_a_no_connect_pin_that_is_netted():
    bad = add_pin(OK, "LEVER", "U401", "IO6")
    assert any("U401.IO6" in e and "no-connect" in e for e in problems(bad, "pins"))


# ── connector tables and nets tell the same story ────────────────────────────
def test_connector_lists_a_pin_twice():
    j = OK.connector("J306")
    bad = OK.replace_connector("J306", pins=j.pins + (ConnPin("3", ""),))
    assert any("J306" in e and "twice" in e for e in problems(bad, "connector"))


def test_connector_cavity_tabled_unused_but_netted():
    errs = problems(add_pin(OK, "LEVER", "J306", "3"), "connector")
    assert errs and "J306.3" in errs[0] and "unused" in errs[0]


def test_connector_names_a_net_that_does_not_exist():
    j = OK.connector("J306")
    bad = OK.replace_connector(
        "J306", pins=j.pins[:2] + (ConnPin("3", "NO_SUCH_NET"),))
    assert any("NO_SUCH_NET" in e for e in problems(bad, "connector"))


def test_connector_table_says_a_net_the_net_does_not_carry():
    """Audit M5: V3P3 / CANH / CANL were tabled on STACK with no contact in
    the net -- the signal never actually reached the connector."""
    errs = problems(OK.without_pin("J308", "3"), "connector")
    assert errs and "J308.3" in errs[0] and "'V3P3'" in errs[0]


def test_net_lands_on_a_contact_the_connector_does_not_have():
    """Audit F-8: GND landed on J308.48 and .50 of a table that stopped at 46."""
    errs = problems(add_pin(OK, "GND", "J308", "48"), "connector")
    assert errs and "J308.48" in errs[0] and "does not have" in errs[0]


def test_net_and_table_disagree_about_which_net_is_on_a_contact():
    """Both directions at once: LEVER moved to J306.2 in the net, not the table."""
    bad = add_pin(OK.without_pin("J306", "1"), "LEVER", "J306", "2")
    errs = " ".join(integrity.check(bad))
    assert "J306.1 is tabled as 'LEVER'" in errs          # table -> net
    assert "shorted: J306.2" in errs                      # net -> table


# ── a net that spans boards needs copper across the gap ──────────────────────
def test_cross_board_net_with_no_contact_on_one_board():
    bad = OK.without_pin("J308", "1")
    errs = problems(bad, "interface")
    assert any("'SIG'" in e and "no inter-board contact on DRV" in e for e in errs)


def test_cross_board_net_with_no_contact_at_all():
    bad = OK.without_pin("J308", "1").without_pin("J406", "1")
    errs = " ".join(problems(bad, "interface"))
    assert "contact on BRAIN" in errs and "contact on DRV" in errs


def test_a_connector_of_the_wrong_interface_bridges_nothing():
    """HV-LINK joins HVIN and CONV; labelled onto a DRV header it carries no
    net across DRV<->BRAIN."""
    bad = OK.replace_connector("J308", interface="HV-LINK")
    errs = problems(bad, "interface")
    assert any("'SIG'" in e and "DRV" in e for e in errs)


# ── an interface is two halves that mate ─────────────────────────────────────
def test_a_crossing_with_a_half_missing():
    """PWR-UP once ran CONV -> DRV -> BRAIN with no part between CONV and DRV."""
    bad = replace(OK, connectors=tuple(c for c in OK.connectors if c.refdes != "J406"))
    errs = " ".join(problems(bad, "interface"))
    assert "STACK needs one half on DRV and one on BRAIN" in errs


def test_a_half_whose_contact_disagrees_with_its_mate():
    """J407.1 set to GND against J307.1's V12 once passed every check."""
    j = OK.connector("J406")
    bad = OK.replace_connector("J406", pins=(ConnPin("1", "GND"),) + j.pins[1:])
    errs = problems(bad, "interface")
    assert any("J308.1 carries 'SIG' but its mate J406.1 carries 'GND'" in e for e in errs)


def test_a_third_half_on_a_board_the_interface_does_not_join():
    extra = _conn("J999", "HVIN", "STACK", STACK, leaves_box=False, interface="STACK")
    bad = replace(OK, connectors=OK.connectors + (extra,))
    assert any("J999 sits elsewhere" in e for e in problems(bad, "interface"))


def test_the_upper_half_must_hang_under_its_board():
    bad = OK.replace_connector("J406", side="top")
    assert any("J406 hang under BRAIN" in e for e in problems(bad, "interface"))


def test_an_interface_nobody_defined():
    bad = OK.replace_connector("J306", interface="PWR-SIDEWAYS")
    assert any("J306 names 'PWR-SIDEWAYS'" in e for e in problems(bad, "interface"))


def test_cross_board_net_that_names_no_interface():
    errs = problems(OK.replace_net("SIG", interface=None), "interface")
    assert errs and "'SIG'" in errs[0] and "names no interface" in errs[0]


def test_single_board_net_that_claims_an_interface():
    errs = problems(OK.replace_net("LEVER", interface="STACK"), "interface")
    assert errs and "'LEVER'" in errs[0] and "one board" in errs[0]


# ── the gpio tag and the MCU pin must agree ──────────────────────────────────
def test_gpio_tag_disagrees_with_the_pin():
    errs = problems(OK.replace_net("SIG", gpio="GPIO7"), "gpio")
    assert errs and "GPIO7" in errs[0] and "IO5" in errs[0]


def test_gpio_tag_on_a_net_with_no_mcu_pin():
    errs = problems(OK.replace_net("LEVER", gpio="GPIO9"), "gpio")
    assert errs and "'LEVER'" in errs[0] and "NONE" in errs[0]


def test_mcu_pin_with_no_gpio_tag():
    errs = problems(OK.replace_net("SIG", gpio=None), "gpio")
    assert errs and "U401.IO5" in errs[0] and "no gpio tag" in errs[0]


def test_duplicate_gpio():
    bad = OK.replace_part("U401", pins=("3V3", "GND", "IO5", "IO9"))
    bad = bad.with_net(Net("OTHER", (("U401", "IO9"),), domain="3V3", gpio="GPIO5"))
    assert any("GPIO5 is assigned to 2 nets" in e for e in problems(bad, "gpio"))


# ── heights must be numbers ──────────────────────────────────────────────────
def test_nan_height():
    errs = problems(OK.replace_part("C1", height_mm=float("nan")), "height")
    assert errs and "C1" in errs[0]


# ── each break is reported as what it is, and nothing else ───────────────────
@pytest.mark.parametrize("category, broken", [
    ("identity", lambda: OK.with_net(Net("LEVER", (), domain="12V"))),
    ("dangling", lambda: add_pin(OK, "LEVER", "Q999", "D")),
    ("shorted", lambda: add_pin(OK, "GND", "R1", "2")),
    ("floating", lambda: OK.without_pin("R2", "2")),
    ("undeclared", lambda: add_pin(OK, "LEVER", "R2", "3")),
    ("gpio", lambda: OK.replace_net("SIG", gpio="GPIO7")),
    ("height", lambda: OK.replace_part("C1", height_mm=float("nan"))),
])
def test_one_break_gives_one_category(category, broken):
    found = {e.split(":", 1)[0] for e in integrity.check(broken())}
    assert found == {category}


# --- a net is a connection; a no-connect needs a datasheet's permission --------
def _real():
    from tools import netlist
    return netlist.current()


def test_a_net_with_one_pin_is_floating():
    d = _real()
    victim = next(n for n in d.nets if len(n.pins) == 2)
    broken = d.replace_net(victim.name, pins=victim.pins[:1])
    errs = integrity.check(broken)
    assert any(e.startswith("floating: net") and victim.name in e for e in errs), errs


@pytest.mark.parametrize("refdes,pin", [
    ("U202", "-Vout"),    # the 5 V rail would have no return
    ("U401", "EN"),       # the module would never leave reset
    ("U201", "CNT"),      # TDK: open = OFF, the 12 V rail never starts
    ("U404", "GND"),
])
def test_a_must_tie_pin_cannot_hide_in_nc(refdes, pin):
    d = _real()
    part = d.part(refdes)
    assert pin in part.pins, f"fixture assumes {refdes}.{pin} is a declared pin"
    hidden = d.without_pin(refdes, pin).replace_part(
        refdes, pins=tuple(q for q in part.pins if q != pin), nc=part.nc + (pin,))
    errs = integrity.check(hidden)
    assert any(e.startswith("nc:") and f"{refdes}.{pin}" in e for e in errs), errs


def test_the_datasheet_sanctioned_no_connects_pass():
    assert [e for e in integrity.check(_real()) if e.startswith("nc:")] == []
