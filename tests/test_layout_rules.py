"""The HV net class the owner sets up before routing (review MX-5).

The generated PCB carries one board-wide 0.2 mm clearance. Pack-voltage copper
needs 1.25 mm, and the class that gets it is derived from the netlist, so a net
added at 84 V joins it without anyone remembering to.
"""
from tools import layout_rules, netlist


def test_every_pack_voltage_net_is_in_the_hv_class_and_nothing_else_is():
    d = netlist.current()
    for board in ("HVIN", "CONV"):
        hv = set(layout_rules.hv_nets(d, board))
        typed = {n.name for n in d.nets if n.domain == "84V"
                 and any(d.board_of(r) == board for r, _ in n.pins)}
        assert typed <= hv, sorted(typed - hv)
        assert "KEY_SENSE" not in hv and "GND" not in hv
    assert layout_rules.hv_nets(d, "DRV") == layout_rules.hv_nets(d, "BRAIN") == []


def test_a_net_joined_to_pack_voltage_joins_the_class_whatever_its_label():
    """A 12V-typed net behind a 0 R link from 84 V is still pack voltage."""
    from tools.model import Net, Part
    d = netlist.current()
    link = Part("R299", "NET-TIE", "copper", "CONV", "R", ("1", "2"), 0.04, value="0R")
    d = d.with_part(link).replace_net("HV_C1_P", pins=d.net("HV_C1_P").pins + (("R299", "1"),))
    d = d.with_net(Net("ODD", (("R299", "2"),), "12V"))
    assert "ODD" in layout_rules.hv_nets(d, "CONV")


def test_the_clearance_is_the_160_v_band():
    assert layout_rules.HV_CLEARANCE_MM == 1.25
