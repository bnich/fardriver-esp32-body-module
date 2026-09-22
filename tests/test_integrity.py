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
from tools.model import CROSSING, ConnPin, Connector, Design, Net, Part


def _r(ref, board):
    return Part(ref, "R-10k", "0805", board, "R", ("1", "2"), 0.6, value="10k")


def _conn(ref, board, name, nets, **kw):
    return Connector(ref, board, name,
                     tuple(ConnPin(str(i + 1), n) for i, n in enumerate(nets)),
                     height_mm=3.0, **kw)


STACK = ("SIG", "GND", "V3P3")
OK = Design(
    parts=(
        Part("U401", "ESP32-S3-WROOM-1-N8", "MODULE", "LOGIC", "MODULE",
             ("3V3", "GND", "IO5"), 3.1, nc=("IO6",)),
        _r("R1", "LOGIC"),                       # pull-up
        _r("R2", "OUTPUTS"),                         # series, lever side
        Part("C1", "C-100n", "0805", "LOGIC", "C", ("1", "2"), 0.9, v_max=16.0),
        Part("D1", "SMBJ15A", "SMB", "OUTPUTS", "TVS", ("A", "K"), 2.5, v_max=15.0,
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
        _conn("J406", "LOGIC", "STACK", STACK, leaves_box=False, interface="STACK",
              side="bottom"),
        _conn("J308", "OUTPUTS", "STACK", STACK, leaves_box=False, interface="STACK"),
        _conn("J306", "OUTPUTS", "Lever", ("LEVER", "GND", "")),
    ),
)


#: The same idea for a CABLED crossing: two ordinary headers joined by a loom
#: (PWR-OUT, POWER → OUTPUTS, IO-20). Both halves stand on their boards' TOP
#: faces -- `_conn` defaults to "top" -- so neither faces the other and neither
#: is mirrored. Under the mated-pair rules this design is a defect; it must be
#: clean, because a cable is not a pair pretending.
CABLED = Design(
    parts=(_r("R10", "POWER"), _r("R11", "OUTPUTS")),
    nets=(
        Net("V12", (("R10", "1"), ("J202", "1"), ("J311", "1"), ("R11", "1")),
            domain="12V", interface="PWR-OUT"),
        Net("GND", (("R10", "2"), ("J202", "2"), ("J311", "2"), ("R11", "2")),
            domain="GND", interface="PWR-OUT"),
    ),
    connectors=(
        _conn("J202", "POWER", "PWR-OUT", ("V12", "GND"),
              leaves_box=False, interface="PWR-OUT"),
        _conn("J311", "OUTPUTS", "PWR-OUT", ("V12", "GND"),
              leaves_box=False, interface="PWR-OUT"),
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
    errs = problems(OK.with_part(_r("R1", "OUTPUTS")), "identity")
    assert errs and "R1" in errs[0] and "2 times" in errs[0]


def test_a_connector_may_not_share_a_refdes_with_a_part():
    bad = replace(OK, connectors=OK.connectors + (_conn("R2", "OUTPUTS", "clash", ()),))
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
    bad = OK.with_part(Part("X1", "MYSTERY", "?", "OUTPUTS", "MECH", (), 1.0))
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
    assert any("'SIG'" in e and "no inter-board contact on OUTPUTS" in e for e in errs)


def test_cross_board_net_with_no_contact_at_all():
    bad = OK.without_pin("J308", "1").without_pin("J406", "1")
    errs = " ".join(problems(bad, "interface"))
    assert "contact on LOGIC" in errs and "contact on OUTPUTS" in errs


def test_a_connector_of_the_wrong_interface_bridges_nothing():
    """PWR-OUT joins POWER and OUTPUTS; labelled onto a LOGIC header it carries
    no net across OUTPUTS<->LOGIC."""
    bad = OK.replace_connector("J406", interface="PWR-OUT")
    errs = problems(bad, "interface")
    assert any("'SIG'" in e and "LOGIC" in e for e in errs)


# ── an interface is two halves that mate ─────────────────────────────────────
def test_a_crossing_with_a_half_missing():
    """PWR-OUT once ran POWER -> OUTPUTS -> LOGIC with no part between POWER and OUTPUTS."""
    bad = replace(OK, connectors=tuple(c for c in OK.connectors if c.refdes != "J406"))
    errs = " ".join(problems(bad, "interface"))
    assert "STACK needs one half on OUTPUTS and one on LOGIC" in errs


def test_a_half_whose_contact_disagrees_with_its_mate():
    """J407.1 set to GND against J307.1's V12 once passed every check."""
    j = OK.connector("J406")
    bad = OK.replace_connector("J406", pins=(ConnPin("1", "GND"),) + j.pins[1:])
    errs = problems(bad, "interface")
    assert any("J308.1 carries 'SIG' but its mate J406.1 carries 'GND'" in e for e in errs)


def test_a_third_half_on_a_board_the_interface_does_not_join():
    extra = _conn("J999", "POWER", "STACK", STACK, leaves_box=False, interface="STACK")
    bad = replace(OK, connectors=OK.connectors + (extra,))
    assert any("J999 sits elsewhere" in e for e in problems(bad, "interface"))


def test_the_upper_half_of_a_mated_pair_must_hang_under_its_board():
    """⚠️ The old, stricter rule, and it did NOT relax when cables arrived.
    STACK is a mated pair: unmirrored, its rows swap and every signal lands on
    the ground row."""
    assert CROSSING["STACK"] == "pair"
    bad = OK.replace_connector("J406", side="top")
    assert any("J406 hang under LOGIC" in e for e in problems(bad, "interface"))


# ── a cable is not a pair, and is not checked as one ─────────────────────────
def test_a_cabled_crossing_with_both_halves_on_top_is_clean():
    """The freedom is the point: a loom carries the orientation, so nothing
    here may ask a cable's halves to face each other, to be mirrored, or to be
    on opposite faces.  That is what lets both headers sit on a top face rather
    than hanging a 22 mm body into a 25.1 mm gap (IO-20)."""
    assert CROSSING["PWR-OUT"] == "cable"
    assert [c.side for c in CABLED.connectors] == ["top", "top"]
    assert integrity.check(CABLED) == []


def test_a_cable_whose_ends_have_different_contacts():
    """A loom terminates in two housings. One end wider than the other is a
    conductor with nowhere to go, or a contact fed by nothing. The two ends
    are compared as SETS OF CONTACT NUMBERS, so the same count on different
    numbers is a mismatch too."""
    j = CABLED.connector("J202")
    bad = CABLED.replace_connector("J202", pins=j.pins + (ConnPin("3", ""),))
    errs = problems(bad, "interface")
    assert any("PWR-OUT is a cable" in e and "same contacts" in e
               and "J202 has ['1', '2', '3'] and J311 has ['1', '2']" in e
               for e in errs), errs
    # Same count, different numbers: J311 on contacts 1 and 3 against J202's 1 and 2.
    j = CABLED.connector("J311")
    bad = CABLED.replace_connector("J311", pins=(j.pins[0], ConnPin("3", "GND")))
    bad = bad.replace_net("GND", pins=tuple(
        (r, "3" if r == "J311" else p) for r, p in bad.net("GND").pins))
    errs = problems(bad, "interface")
    assert any("J202 has ['1', '2'] and J311 has ['1', '3']" in e for e in errs), errs


def test_a_cable_wired_to_the_wrong_contact_at_one_end():
    """Both ends agree with their own tables and both carry the same nets --
    only the ORDER differs, which is a loom crimped into the wrong cavities.
    A check that compared the two SETS of nets would see nothing here."""
    swap = {"1": "2", "2": "1"}
    bad = CABLED.replace_connector(
        "J311", pins=(ConnPin("1", "GND"), ConnPin("2", "V12")))
    for name in ("V12", "GND"):
        bad = bad.replace_net(name, pins=tuple(
            (r, swap[p] if r == "J311" else p) for r, p in bad.net(name).pins))
    errs = problems(bad, "interface")
    assert any("contact 1 of PWR-OUT carries 'V12' on J202.1 but 'GND' on "
               "J311.1" in e for e in errs), errs
    assert any("contact 2 of PWR-OUT" in e for e in errs), errs


def _retabled(d, refdes, moves: dict):
    """`refdes`'s table AND its nets with each contact renumbered per `moves`
    -- the copper really is wired that way, and integrity's table-vs-net
    check has nothing to say. Only the cable check can see it."""
    j = d.connector(refdes)
    by = {p.pin: p for p in j.pins}
    pins = tuple(ConnPin(moves.get(p, p), by[p].net, by[p].note) for p in by)
    out = d.replace_connector(refdes, pins=pins)
    for n in d.nets:
        if any(r == refdes for r, _ in n.pins):
            out = out.replace_net(n.name, pins=tuple(
                (r, moves.get(p, p) if r == refdes else p) for r, p in n.pins))
    return out


def test_a_cable_end_retabled_onto_other_contacts_is_caught_on_the_real_netlist():
    """⚠️ H9 (2026-09-21): J311 re-tabled 5:V12 4:GND 2:V5 1:KEY_SENSE -- a
    straight loom then puts 12 V on KEY_SENSE -- passed integrity, rules and
    the build gate, because the cable branch zipped the two tuples by POSITION
    and called position i "contact i". It compares by contact number now."""
    from tools import netlist
    d = netlist.current()
    assert [(p.pin, p.net) for p in d.connector("J311").pins] == \
        [("1", "V12"), ("2", "GND"), ("4", "V5"), ("5", "KEY_SENSE")]
    bad = _retabled(d, "J311", {"1": "5", "2": "4", "4": "2", "5": "1"})
    assert [(p.pin, p.net) for p in bad.connector("J311").pins] == \
        [("5", "V12"), ("4", "GND"), ("2", "V5"), ("1", "KEY_SENSE")]
    errs = problems(bad, "interface")
    assert "interface: contact 1 of PWR-OUT carries 'V12' on J202.1 but 'KEY_SENSE' " \
        "on J311.1 -- a cable is wired contact for contact" in errs, errs
    assert len([e for e in errs if "of PWR-OUT carries" in e]) == 4


def test_a_cable_table_written_in_another_order_is_the_same_copper():
    """The other half of H9: J202's tuple in the order 5, 4, 2, 1 -- nothing
    moved, only the lines of the table -- gave four FALSE problems. A table
    is a set of (contact, net) pairs, and its order means nothing."""
    from tools import netlist
    d = netlist.current()
    j = d.connector("J202")
    by = {p.pin: p for p in j.pins}
    same = d.replace_connector("J202", pins=tuple(by[k] for k in ("5", "4", "2", "1")))
    assert integrity.check(same) == []


def test_a_crossing_with_no_declared_kind_is_named(monkeypatch):
    """Guarding the TABLE, not each crossing: with no entry, an interface would
    quietly inherit the pair rules and a cable would be reported for a defect
    it does not have."""
    monkeypatch.setattr(integrity, "CROSSING",
                        {k: v for k, v in CROSSING.items() if k != "STACK"})
    assert any("STACK has no entry in model.CROSSING" in e
               for e in problems(OK, "interface"))


def test_an_interface_the_board_table_does_not_know(monkeypatch):
    """`Interface` is checked at construction (tests/test_model.py), so what is
    left to guard is the TABLE: an interface added to the literal but not to
    INTERFACE_BOARDS joins no pair of boards, and every half naming it says so.
    A test below holds the literal, INTERFACE_BOARDS and CROSSING to one set."""
    monkeypatch.setattr(integrity, "INTERFACE_BOARDS",
                        {k: v for k, v in integrity.INTERFACE_BOARDS.items()
                         if k != "STACK"})
    errs = problems(OK, "interface")
    assert any("J406 names 'STACK', which joins no known pair of boards" in e
               for e in errs), errs
    assert any("J308 names 'STACK'" in e for e in errs)


def test_a_crossing_declared_outside_the_literal_is_named(monkeypatch):
    """L4: `is_cabled` reads anything that is not exactly "cable" as a pair, so
    "Cable" makes a loom answer to the mated-pair rules. The VALUE is held to
    the literal, as the key is held to the table. `integrity.CROSSING` and
    `model.CROSSING` are one dict, so `setitem` reaches both."""
    monkeypatch.setitem(CROSSING, "PWR-OUT", "Cable")
    errs = problems(CABLED, "interface")
    assert any("model.CROSSING['PWR-OUT'] is 'Cable', not one of ('pair', 'cable')"
               in e for e in errs), errs


def test_the_interface_literal_the_board_table_and_the_crossing_table_agree():
    """Three homes for the set of interfaces; a name in one and not another is
    a crossing that would pick its own rules."""
    from typing import get_args

    from tools.model import Interface
    assert set(get_args(Interface)) == set(integrity.INTERFACE_BOARDS) == set(CROSSING)


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


# ── each break is reported as what it is, and nothing else ───────────────────
@pytest.mark.parametrize("category, broken", [
    ("identity", lambda: OK.with_net(Net("LEVER", (), domain="12V"))),
    ("dangling", lambda: add_pin(OK, "LEVER", "Q999", "D")),
    ("shorted", lambda: add_pin(OK, "GND", "R1", "2")),
    ("floating", lambda: OK.without_pin("R2", "2")),
    ("undeclared", lambda: add_pin(OK, "LEVER", "R2", "3")),
    ("gpio", lambda: OK.replace_net("SIG", gpio="GPIO7")),
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
