"""J409: expander #2's spare inputs on an unfitted header (owner, 2026-09-18).

U403 uses GPA0 for ACC+; its other thirteen input-capable bits are brought out
so they can be used later without a new board.  The footprint is on BRAIN and
the part is not fitted: JLC skips it, and the owner solders a header when a
spare is wanted.
"""
from tools import jlc_bom, netlist
from tools.eprj3.schematic import landed_pins

SPARES = [f"GPA{i}" for i in range(1, 7)] + [f"GPB{i}" for i in range(7)]


def test_every_spare_input_of_expander_two_lands_on_the_header():
    d = netlist.current()
    j = d.connector("J409")
    assert (j.board, j.dnp, j.leaves_box, len(j.pins)) == ("BRAIN", True, False, 16)
    landed = landed_pins(d)
    on_header = {cp.net: cp.pin for cp in j.pins}
    for bit in SPARES:
        net = landed[("U403", bit)]
        pins = next(n.pins for n in d.nets if n.name == net)
        assert set(pins) == {("U403", bit), ("J409", on_header[net])}, bit


def test_the_output_only_bits_stay_off_the_header():
    """DS20001952D: GPA7 and GPB7 are output only on the MCP23017."""
    u = netlist.current().part("U403")
    assert {"GPA7", "GPB7"} <= set(u.nc)


def test_the_header_carries_3v3_and_ground():
    nets = [cp.net for cp in netlist.current().connector("J409").pins]
    assert nets[0] == "V3P3" and nets.count("GND") == 2


def test_jlc_places_nothing_for_it():
    d = netlist.current()
    assert "J409" not in jlc_bom.bom_csv(d)
    assert "J409" not in jlc_bom.hand_list(d)


def test_easyeda_marks_it_dnp():
    from tools.eprj3 import schematic
    d = netlist.current()
    j = d.connector("J409")
    item = next(i for i in schematic.board_items(d, "BRAIN") if i.ref == "J409")
    attrs = dict((a[0], a[1]) for a in schematic._part_attrs(item, 0, 0, "u", connector=j))
    assert attrs.get("DNP") == "yes" and "(DNP)" in schematic.connector_name(j)
