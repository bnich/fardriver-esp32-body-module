"""The HV net class the owner sets up before routing (review MX-5).

The generated PCB carries one board-wide 0.2 mm clearance. Pack-voltage copper
needs 1.25 mm, and the class that gets it is derived from the netlist, so a net
added at 84 V joins it without anyone remembering to.
"""
from tools import layout_rules, netlist


def test_every_pack_voltage_net_is_in_the_hv_class_and_nothing_else_is():
    d = netlist.current()
    hv = set(layout_rules.hv_nets(d, "POWER"))
    typed = {n.name for n in d.nets if n.domain == "84V"
             and any(d.board_of(r) == "POWER" for r, _ in n.pins)}
    assert typed <= hv, sorted(typed - hv)
    assert "KEY_SENSE" not in hv and "GND" not in hv
    assert layout_rules.hv_nets(d, "OUTPUTS") == layout_rules.hv_nets(d, "LOGIC") == []


def test_a_net_joined_to_pack_voltage_joins_the_class_whatever_its_label():
    """A 12V-typed net behind a 0 R link from 84 V is still pack voltage."""
    from tools.model import Net, Part
    d = netlist.current()
    link = Part("R299", "NET-TIE", "copper", "POWER", "R", ("1", "2"), 0.04, value="0R")
    d = d.with_part(link).replace_net("HV_C1_P", pins=d.net("HV_C1_P").pins + (("R299", "1"),))
    d = d.with_net(Net("ODD", (("R299", "2"),), "12V"))
    assert "ODD" in layout_rules.hv_nets(d, "POWER")


def test_the_clearance_is_the_160_v_band():
    assert layout_rules.HV_CLEARANCE_MM == 1.25


def test_the_tag_connect_keep_out_reaches_the_owner():
    """Tag-Connect notes 1-2: no track or via between the pads' centres, and
    nothing within 0.020 in of a pad.  The project cannot carry either."""
    text = layout_rules.text()
    line = next(l for l in text.splitlines() if "J408" in l)
    assert "LOGIC" in line and "x -1.27 to 1.27, y -0.635 to 0.635" in line
    assert "0.51 mm" in line


def test_a_mistyped_divider_node_keeps_its_place_in_the_class():
    """H15: KEY_SENSE_MID (held at 84 V through R107) retyped 12V left every
    gate green and layout-rules.txt one net short. The class is drawn from the
    SOLVED voltage as well as the label and the BD-2 walk, so it stays at 14 --
    and VR-DOMAIN names the mistype."""
    from tools import rules
    d = netlist.current()
    before = layout_rules.hv_nets(d, "POWER")
    assert len(before) == 14 and "KEY_SENSE_MID" in before
    for name in ("KEY_SENSE_MID", "D13_EN_MID", "D13_PD", "D13_PD_MID", "KSW"):
        bad = d.replace_net(name, domain="12V")
        assert layout_rules.hv_nets(bad, "POWER") == before, name
        line = next(l for l in layout_rules.text(bad).splitlines() if l.startswith("  POWER:"))
        assert line.count(",") == 13 and name in line
        errs = [e for e in rules.check_all(bad) if e.startswith("VR-DOMAIN: net")]
        assert len(errs) == 1 and f"net {name!r} is typed 12V (12 V) but its copper solves to 84 V" in errs[0]
    assert [e for e in rules.check_all(d) if e.startswith("VR-DOMAIN: net")] == []


def test_the_class_is_drawn_from_solved_voltage_not_only_from_the_walk():
    """Take the solved term away and the retype shrinks the class: the walk
    alone does not reach through resistors (that is what H15 was)."""
    from tools import rules
    d = netlist.current().replace_net("KEY_SENSE_MID", domain="12V")
    ix = rules._index(d)
    solved = rules.hv_nets_solved(ix)
    assert "KEY_SENSE_MID" in solved and "held at 'KSW' = 84 V" in solved["KEY_SENSE_MID"]
    assert set(solved) == {"D13_EN_MID", "D13_GATE", "D13_PD", "D13_PD_MID", "HV_BPLUS",
                           "HV_C1_N", "HV_C1_P", "HV_C2_HOLD", "HV_C2_HOLD_IN", "HV_C2_N",
                           "HV_C2_P", "HV_SW", "KEY_SENSE_MID", "KSW"}
    walked, _ = rules._hv_nets(rules._index(netlist.current()))
    assert set(layout_rules.hv_nets(d, "POWER")) == set(walked)
    # ⚠️ Two returns are in the class by LABEL alone: HV_C1_N and HV_C2_N are
    # the converters' isolated -Vin, reached by no walk and solved by no
    # resistor. Retyped, nothing here would notice; recorded, not closed.
    for name in ("HV_C1_N", "HV_C2_N"):
        bad = netlist.current().replace_net(name, domain="12V")
        assert name not in layout_rules.hv_nets(bad, "POWER")
