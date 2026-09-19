"""BRAIN's own interfaces: USB, the service header, the reset line, CAN and
the boost button.  Each test states the behaviour the review asked for."""
from tools import netlist
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


def test_the_usb_esd_array_rides_3v3_so_d_plus_cannot_back_drive_vbus():
    """USBLC6-2SC6 pin 5 is the top of its steering diodes.  On VBUS, D+'s
    pull-up (GPIO20 comes out of reset pulled up) forward-biases I/O1 → VBUS
    and holds the unplugged VBUS near 2.7 V: 1.7 V at GPB6, neither high nor
    low.  On V3P3 the diodes clamp to the rail the pins live on."""
    d = _d()
    assert _net(d, "D409", "VBUS") == "V3P3"
    assert _pins(d, "USB_VBUS") == {("J401", "1"), ("R444", "1")}


def test_the_service_header_offers_no_supply():
    """J408 is for a USB-serial adapter, which brings its own power.  A 3V3 pin
    there would back-feed the LDO from the adapter's rail."""
    j = _d().connector("J408")
    assert all(cp.net not in ("V3P3", "V5", "V12") for cp in j.pins)
    assert [cp.net for cp in j.pins][:4] == ["EN", "BOOT_IO0", "U0TXD_HDR", "UART2_RX"]
    assert {cp.pin: cp.net for cp in j.pins}["6"] == "GND"


def test_native_usb_passes_22_ohms_at_the_module():
    """Espressif HDG, USB: 'reserve series resistors (initial value can be
    22/33 Ω) … close to the chip'."""
    d = _d()
    for pin, wire, conn_pin in (("IO20", "USB_DP", "3"), ("IO19", "USB_DM", "4")):
        mcu_net, r, beyond = _series(d, pin, "22R")
        assert beyond == wire and ("J401", conn_pin) in _pins(d, wire)
        assert next(n for n in d.nets if n.name == mcu_net).gpio == f"GPIO{pin[2:]}"
        assert len(_pins(d, mcu_net)) == 2            # the pin and its resistor


def test_u0txd_passes_a_series_resistor_to_the_header():
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
