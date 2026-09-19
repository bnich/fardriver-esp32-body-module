"""J409: expander #2's spare inputs on an unfitted header (owner, 2026-09-18).

U403 uses GPA0 for ACC+; its other thirteen input-capable bits are brought out
so they can be used later without a new board.  The footprint is on LOGIC and
the part is not fitted: JLC skips it, and the owner solders a header when a
spare is wanted.
"""
from tools import jlc_bom, netlist
from tools.eprj3.schematic import landed_pins

SPARES = [f"GPA{i}" for i in range(1, 7)] + [f"GPB{i}" for i in range(7)]


def _nets(d):
    return {n.name: set(n.pins) for n in d.nets}


def _net_of(d, ref, pin):
    return landed_pins(d)[(ref, pin)]


def test_every_spare_input_reaches_the_header_through_a_class_a_network():
    """plan §4 class A, as on the bar inputs: 1 kΩ pull-up to 3V3 and a TVS on
    the wire side, 1 kΩ series into the pin, 100 nF at the pin.  A header
    fitted later is ready to wire."""
    d = netlist.current()
    j = d.connector("J409")
    assert (j.board, j.dnp, j.leaves_box, len(j.pins)) == ("LOGIC", True, False, 16)
    parts = {p.refdes: p for p in d.parts}
    nets = _nets(d)
    header = {cp.net: cp.pin for cp in j.pins}
    for bit in SPARES:
        pin_net = nets[_net_of(d, "U403", bit)]
        (series, s_pin), = [(r, p) for r, p in pin_net if parts.get(r) and parts[r].kind == "R"]
        (cap, c_pin), = [(r, p) for r, p in pin_net if parts.get(r) and parts[r].kind == "C"]
        assert len(pin_net) == 3, bit
        wire = _net_of(d, series, "1" if s_pin == "2" else "2")
        wire_pins = nets[wire]
        assert ("J409", header[wire]) in wire_pins, bit
        pull = [r for r, p in wire_pins if parts.get(r) and parts[r].kind == "R" and r != series]
        tvs = [r for r, p in wire_pins if parts.get(r) and parts[r].kind == "TVS"]
        assert len(pull) == 1 and len(tvs) == 1 and len(wire_pins) == 4, bit
        other = lambda ref, pin: _net_of(d, ref, "1" if pin == "2" else "2")
        assert other(*next(x for x in wire_pins if x[0] == pull[0])) == "V3P3", bit
        assert other(cap, c_pin) == "GND", bit
        # The very parts the bar inputs' class-A networks use (R402/R413/C401).
        assert (parts[pull[0]].lcsc, parts[series].lcsc, parts[cap].lcsc) == \
            (parts["R402"].lcsc, parts["R413"].lcsc, parts["C401"].lcsc), bit
        assert parts[pull[0]].value == parts[series].value == "1k", bit
        assert parts[cap].value.startswith("100nF"), bit
        assert parts[tvs[0]].mpn == "SMS05T1G", bit
        assert not any(parts[r].dnp for r in (pull[0], series, cap, tvs[0])), bit


def test_every_line_of_the_spare_arrays_is_used_or_grounded():
    d = netlist.current()
    for ref in ("D410", "D411", "D412", "D413"):
        tvs = d.part(ref)
        assert _net_of(d, ref, "A2") == _net_of(d, ref, "A5") == "GND"
        assert all(_net_of(d, ref, k) for k in ("K1", "K3", "K4", "K6"))


def test_the_output_only_bits_stay_off_the_header():
    """DS20001952D: GPA7 and GPB7 are output only on the MCP23017."""
    u = netlist.current().part("U403")
    assert {"GPA7", "GPB7"} <= set(u.nc)


def test_the_header_carries_3v3_and_ground():
    nets = [cp.net for cp in netlist.current().connector("J409").pins]
    assert nets[0] == "V3P3" and nets.count("GND") == 2


def test_jlc_places_the_protection_but_not_the_header():
    d = netlist.current()
    bom = jlc_bom.bom_csv(d)
    assert "J409" not in bom and "J409" not in jlc_bom.hand_list(d)
    for ref in ("R446", "R471", "C423", "C435", "D410", "D413"):
        assert ref in bom, ref


def test_easyeda_marks_it_dnp():
    from tools.eprj3 import schematic
    d = netlist.current()
    j = d.connector("J409")
    item = next(i for i in schematic.board_items(d, "LOGIC") if i.ref == "J409")
    attrs = dict((a[0], a[1]) for a in schematic._part_attrs(item, 0, 0, "u", connector=j))
    assert attrs.get("DNP") == "yes" and "(DNP)" in schematic.connector_name(j)
