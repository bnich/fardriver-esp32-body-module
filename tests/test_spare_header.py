"""J409 and J410: expander #2's spare inputs in the INPUTS row (IO-1, IO-4).

U403 uses GPA0 for ACC+; its other thirteen input-capable bits are brought out
so they can be used later without a new board.  Since IO-4 they are FITTED
harness terminals in the inputs row on LOGIC -- 13 free inputs and the boost
button over two 8-way terminals, because the 16-way header JLC would need is
out of stock -- so a wire is pushed into a screw plug, not soldered to a header.
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
    the wire side, 1 kΩ series into the pin, 100 nF at the pin.  Every one is
    fitted, so a wire needs only a plug."""
    d = netlist.current()
    terminals = [d.connector(r) for r in ("J409", "J410")]
    for j in terminals:
        assert (j.board, j.dnp, j.leaves_box) == ("LOGIC", False, True), j.refdes
        assert (j.pitch_mm, len(j.pins)) == (3.81, 8), j.refdes
    parts = {p.refdes: p for p in d.parts}
    nets = _nets(d)
    header = {cp.net: (j.refdes, cp.pin) for j in terminals for cp in j.pins}
    for bit in SPARES:
        pin_net = nets[_net_of(d, "U403", bit)]
        (series, s_pin), = [(r, p) for r, p in pin_net if parts.get(r) and parts[r].kind == "R"]
        (cap, c_pin), = [(r, p) for r, p in pin_net if parts.get(r) and parts[r].kind == "C"]
        assert len(pin_net) == 3, bit
        wire = _net_of(d, series, "1" if s_pin == "2" else "2")
        wire_pins = nets[wire]
        assert header[wire] in wire_pins, bit
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


def test_each_terminal_carries_a_return_and_no_rail():
    """A class-A contact closes to GROUND, so each terminal carries one return
    of its own -- and ⛔ no rail leaves the box on it: the 3.3 V pin the old
    internal header offered is gone with it (nothing outside the box may be fed
    from the logic rail)."""
    d = netlist.current()
    for ref in ("J409", "J410"):
        nets = [cp.net for cp in d.connector(ref).pins]
        assert nets.count("GND") == 1, ref
        assert not {"V3P3", "V5", "V12"} & set(nets), ref
    assert [cp.net for cp in d.connector("J409").pins][0] == "GND"
    assert [cp.net for cp in d.connector("J410").pins][-1] == "GND"


def test_jlc_places_the_protection_and_both_headers():
    """Fitted terminals: JLC places the headers too, and the owner wires the
    screw plugs. It is the plug, not the header, that is ordered loose."""
    d = netlist.current()
    bom = jlc_bom.bom_csv(d)
    for ref in ("J409", "J410", "R446", "R471", "C423", "C435", "D410", "D413"):
        assert ref in bom, ref
    for ref in ("J409", "J410"):
        assert ref not in jlc_bom.hand_list(d), ref
        assert d.connector(ref).plug


def test_easyeda_is_not_told_to_skip_them_any_more():
    from tools.eprj3 import schematic
    d = netlist.current()
    for ref in ("J409", "J410"):
        j = d.connector(ref)
        item = next(i for i in schematic.board_items(d, "LOGIC") if i.ref == ref)
        attrs = dict((a[0], a[1]) for a in
                     schematic._part_attrs(item, 0, 0, "u", connector=j))
        assert "DNP" not in attrs and "Add into BOM" not in attrs, ref
        assert "(DNP)" not in schematic.connector_name(j), ref
