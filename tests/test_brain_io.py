"""BRAIN's own interfaces: the service pads, the reset line, CAN and the boost
button.  Each test states the behaviour the review asked for."""
from tools import drawn_footprints, gpio_budget, netlist
from tools.eprj3.schematic import landed_pins


def _d():
    return netlist.current()


def _net(d, ref, pin):
    return landed_pins(d)[(ref, pin)]


def _pins(d, name):
    return set(next(n for n in d.nets if n.name == name).pins)


def _other(d, ref, pin):
    return _net(d, ref, "1" if pin == "2" else "2")


def _series(d, mcu_pin, value):
    """The one resistor on the module pin's net, and the net beyond it."""
    d_parts = {p.refdes: p for p in d.parts}
    net = _net(d, "U401", mcu_pin)
    rs = [(r, p) for r, p in _pins(d, net) if r in d_parts and d_parts[r].kind == "R"]
    assert len(rs) == 1, (mcu_pin, rs)
    (r, p), = rs
    assert d_parts[r].value == value and not d_parts[r].dnp, (mcu_pin, r)
    return net, r, _other(d, r, p)


def test_the_service_pads_are_an_esp_prog_header_with_no_supply():
    """J408 is a Tag-Connect TC2030-NL land.  The TC2030-IDC-NL cable takes pad n
    to IDC pin n, and the pads follow the ESP-Prog's PROG header (Espressif
    SCH_ESP32-PROG_V2.1): 1 ESP_EN, 2 VDD, 3 ESP_TXD0, 4 GND, 5 ESP_RXD0,
    6 ESP_IO0, where TXD0 is the target's own TX.  VDD is left open: the
    ESP-Prog jumpers it to 5 V as readily as 3.3 V, and the board powers
    itself."""
    j = _d().connector("J408")
    assert [(cp.pin, cp.net) for cp in j.pins] == [
        ("1", "EN"), ("2", ""), ("3", "U0TXD_HDR"), ("4", "GND"),
        ("5", "U0RXD"), ("6", "BOOT_IO0")]
    assert j.land == "TC2030-NL" and j.dnp and not j.lcsc and j.height_mm == 0.0
    land = drawn_footprints.LANDS[j.land]
    assert {p.num for p in land.pads} == {cp.pin for cp in j.pins}
    assert not any(p.paste for p in land.pads), "Tag-Connect note 3: no paste"


def test_the_board_has_no_usb_port_and_its_usb_pins_are_spare():
    """Flashing and the console are on UART0 at J408; the S3's native USB pins
    are ordinary spares in the pool."""
    d = _d()
    assert not [c.refdes for c in d.connectors if "USB" in c.name.upper()
                and "USB-SERIAL" not in c.name.upper()]
    assert {"IO19", "IO20"} <= set(d.part("U401").nc)
    assert {19, 20} <= set(gpio_budget.POOL) and {19, 20} <= set(gpio_budget.spare(d))


def test_u0txd_passes_a_series_resistor_to_the_service_pads():
    """HDG, UART: 'a 499 Ω series resistor to the U0TXD line to suppress
    harmonics'.  470 Ω is the nearest JLC Basic value."""
    d = _d()
    mcu_net, r, beyond = _series(d, "IO43", "470R")
    assert mcu_net == "U0TXD" and ("J408", "3") in _pins(d, beyond)


def test_a_supervisor_footprint_can_hold_en_low_until_3v3_is_good():
    """Unfitted by default: the 10 k / 1 µF RC is what the HDG asks for.  Fit
    U406 if a slow or bouncing 3V3 ramp ever shows up."""
    d = _d()
    u = d.part("U406")
    assert (u.mpn, u.dnp, u.board) == ("TLV803SDBZR", True, "BRAIN")
    assert _net(d, "U406", "RESET") == "EN"
    assert _net(d, "U406", "VDD") == "V3P3" and _net(d, "U406", "GND") == "GND"


def test_the_parked_can_transceiver_idles_in_standby():
    """SLOS346O: RS ≥ 0.75 VCC is standby, 370 µA and the driver off.  A fitted
    pull-up holds it there; the slope-control pull-down stays as a footprint."""
    d = _d()
    rs = _net(d, "U404", "RS")
    parts = {p.refdes: p for p in d.parts}
    fitted = [r for r, p in _pins(d, rs) if r in parts and parts[r].kind == "R" and not parts[r].dnp]
    assert len(fitted) == 1 and _other(d, fitted[0], next(
        p for r, p in _pins(d, rs) if r == fitted[0])) == "V3P3"
    assert parts["R442"].dnp


def test_the_boost_button_reaches_a_terminal_with_its_own_return():
    """The throttle's red button (IN-07) is a 2-pin dry contact.  It lands on
    J404 beside a ground of its own, with a TVS on the wire."""
    d = _d()
    wire = _pins(d, "IN07_BOOST_BTN_WIRE")
    (j404_pin,) = [p for r, p in wire if r == "J404"]
    assert ("D404", "K4") in wire
    j = d.connector("J404")
    nets = [cp.net for cp in j.pins]
    assert nets[int(j404_pin)] == "GND"          # the contact beside it
    assert j.lcsc and j.plug
