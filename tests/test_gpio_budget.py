"""The pin budget: silicon facts, and demand DERIVED from a design.

Every branch of `report()` is driven by a fixture that contains the defect it
names, beside a clean design that must stay quiet. The clean design is not
decoration: each broken fixture is one `replace_net` away from it, so a branch
that fired on the clean design would make every test below meaningless.
"""
import pytest

from tools import gpio_budget as g
from tools.model import ConnPin, Connector, Design, Net, Part


def _r(ref):
    return Part(ref, "RC0805", "0805", "BRAIN", "R", ("1", "2"), 0.6)


def _c(ref):
    return Part(ref, "CC0805", "0805", "BRAIN", "C", ("1", "2"), 0.9, v_max=16.0)


def clean() -> Design:
    parts = (
        Part("U401", "ESP32-S3-WROOM-1-N8", "module", "BRAIN", "MODULE",
             ("3V3", "GND", "IO0", "IO1", "IO4", "IO7", "IO17", "IO19", "IO43"), 3.1),
        Part("Q401", "AO3400A", "SOT-23", "BRAIN", "NFET", ("G", "S", "D"), 1.1,
             v_max=30.0),
        Part("U301", "TPS4H160B", "HTSSOP-28", "DRV", "IC", ("CS", "VS", "GND"), 1.2),
        _r("R1"), _r("R2"), _r("R3"), _r("R4"), _r("R5"), _c("C1"), _c("C2"),
    )
    connectors = (
        Connector("J408", "BRAIN", "service header",
                  (ConnPin("1", "BOOT"), ConnPin("2", "U0TXD")), 8.5,
                  leaves_box=False),
        Connector("J404", "BRAIN", "USB-C", (ConnPin("A7", "USB_DM"),), 3.2),
        Connector("J402", "BRAIN", "FarDriver serial",
                  (ConnPin("1", "UART1_TX_WIRE"),), 7.0),
    )
    nets = (
        Net("GND", (("U401", "GND"), ("Q401", "S"), ("U301", "GND"),
                    ("C1", "2"), ("C2", "2"), ("R5", "2")), "GND"),
        Net("V3P3", (("U401", "3V3"), ("C1", "1"), ("C2", "1"), ("R3", "1")), "3V3"),
        Net("V12", (("U301", "VS"), ("Q401", "D")), "12V"),
        # a driver, through its series resistor
        Net("HORN_CMD", (("U401", "IO7"), ("R1", "1")), "3V3", gpio="GPIO7"),
        Net("HORN_GATE", (("R1", "2"), ("Q401", "G")), "3V3"),
        # analog by what it reaches, not by its name
        Net("ISENSE_ADC", (("U401", "IO4"), ("R2", "2")), "3V3", gpio="GPIO4"),
        Net("U301_CS", (("R2", "1"), ("U301", "CS")), "3V3"),
        # analog by name
        Net("KEY_SENSE", (("U401", "IO1"), ("R5", "1")), "3V3", gpio="GPIO1"),
        # reserved pins doing only their reserved job
        Net("U0TXD", (("U401", "IO43"), ("J408", "2")), "3V3", gpio="GPIO43"),
        Net("BOOT", (("U401", "IO0"), ("J408", "1"), ("R3", "2")), "3V3", gpio="GPIO0"),
        Net("USB_DM", (("U401", "IO19"), ("J404", "A7")), "3V3", gpio="GPIO19"),
        # an ordinary signal that leaves the box
        Net("UART1_TX", (("U401", "IO17"), ("R4", "1")), "3V3", gpio="GPIO17"),
        Net("UART1_TX_WIRE", (("R4", "2"), ("J402", "1")), "3V3"),
    )
    return Design(parts, nets, connectors)


def only(errs, *needles):
    """Exactly one problem, and it says every needle."""
    assert len(errs) == 1, errs
    assert all(n in errs[0] for n in needles), errs[0]


# --- silicon and module facts -----------------------------------------------------
def test_the_pool_is_thirty_and_here_is_why():
    assert len(g.EXISTS) == 45                       # GPIO0-21 and 26-48
    assert len(g.POOL) == 45 - 7 - 2 - 2 - 4 == 30
    for pin in (22, 23, 24, 25):
        assert pin not in g.EXISTS
    for pin in (*range(26, 33), 33, 34, 19, 20, 0, 3, 45, 46):
        assert pin not in g.POOL, f"GPIO{pin}"


def test_the_wroom_1_has_no_pad_for_33_or_34():
    assert g.NOT_BROUGHT_OUT == {33, 34}
    assert {33, 34} <= g.EXISTS                      # on the silicon...
    assert not {33, 34} & g.POOL                     # ...but not on the module


def test_gpio43_is_in_the_pool_but_can_never_drive():
    assert g.BOOT_LOG == 43
    assert 43 in g.POOL and 43 not in g.DRIVER_POOL
    assert len(g.DRIVER_POOL) == 29


def test_adc1_is_gpio_1_to_10_less_the_strapping_pin():
    assert g.ADC1 == set(range(1, 11))
    assert g.ADC1_POOL == g.ADC1 - {3}


# --- demand is read off the design -------------------------------------------------
def test_demand_is_every_tagged_net_and_nothing_typed():
    assert [(s.net, s.gpio) for s in g.demand(clean())] == [
        ("BOOT", 0), ("KEY_SENSE", 1), ("ISENSE_ADC", 4), ("HORN_CMD", 7),
        ("UART1_TX", 17), ("USB_DM", 19), ("U0TXD", 43)]
    assert not hasattr(g, "DEMAND") and not hasattr(g, "TOTAL")


def test_demand_sees_through_a_series_resistor_but_not_through_a_rail():
    by_net = {s.net: s for s in g.demand(clean())}
    assert by_net["HORN_CMD"].loads == ("Q401.G",)
    assert by_net["UART1_TX"].leaves_box and not by_net["HORN_CMD"].leaves_box
    assert "U301.CS" in by_net["ISENSE_ADC"].analog
    # BOOT's pull-up ends on V3P3 and KEY_SENSE's divider on GND; both also
    # reach U301. The walk stops at a supply, so neither "drives" the IC.
    assert by_net["BOOT"].loads == () and "V3P3" not in by_net["BOOT"].nets
    assert by_net["KEY_SENSE"].loads == () and "GND" not in by_net["KEY_SENSE"].nets


def test_adding_a_signal_takes_a_pin_out_of_the_spare_list():
    d = clean()
    assert 5 in g.spare(d) and 7 not in g.spare(d)
    assert len(g.spare(d)) == 30 - 5                 # 5 of the 7 nets are pool pins
    more = d.with_net(Net("FAN_CMD", (("U401", "IO5"),), "3V3", gpio="GPIO5"))
    assert 5 not in g.spare(more)


def test_the_clean_design_closes():
    assert g.report(clean()) == []


# --- every failure branch, fired ----------------------------------------------------
@pytest.mark.parametrize("gpio, why", [
    ("GPIO22", "does not exist"),
    ("GPIO27", "in-package flash"),
    ("GPIO33", "no pad on the WROOM-1"),
    ("GPIO34", "no pad on the WROOM-1"),
    ("GPIO20", "native USB"),
    ("GPIO45", "strapping pin"),
])
def test_a_signal_outside_the_pool_is_reported(gpio, why):
    only(g.report(clean().replace_net("HORN_CMD", gpio=gpio)),
         "'HORN_CMD'", "outside the pool", why)


def test_a_strapping_pin_may_not_leave_the_box_either():
    only(g.report(clean().replace_net("UART1_TX", gpio="GPIO46")),
         "'UART1_TX'", "strapping pin")


def test_a_usb_pin_may_not_pick_up_a_second_job():
    d = clean().replace_net(
        "USB_DM", pins=(("U401", "IO19"), ("J404", "A7"), ("Q401", "G")))
    d = d.replace_net("HORN_GATE", pins=(("R1", "2"),))
    only(g.report(d), "'USB_DM'", "native USB")


def test_one_gpio_given_to_two_nets_is_reported():
    only(g.report(clean().replace_net("UART1_TX", gpio="GPIO7")),
         "GPIO7", "HORN_CMD", "UART1_TX", "2 nets")


def test_a_driver_on_gpio43_is_reported_through_its_series_resistor():
    d = clean().replace_net("U0TXD", gpio="GPIO9").replace_net("HORN_CMD", gpio="GPIO43")
    only(g.report(d), "'HORN_CMD'", "Q401.G", "never a driver")


def test_gpio43_on_a_wire_that_leaves_the_box_is_a_driver_too():
    d = clean().replace_net("U0TXD", gpio="GPIO9").replace_net("UART1_TX", gpio="GPIO43")
    only(g.report(d), "'UART1_TX'", "J402", "never a driver")


def test_an_analog_net_off_adc1_is_reported_by_name():
    only(g.report(clean().replace_net("KEY_SENSE", gpio="GPIO11")),
         "'KEY_SENSE'", "GPIO11", "ADC1")


def test_an_analog_net_off_adc1_is_reported_whatever_it_is_called():
    # ISENSE_ADC is in no list. It is analog because it reaches U301.CS.
    assert "ISENSE_ADC" not in g.ANALOG_NETS
    only(g.report(clean().replace_net("ISENSE_ADC", gpio="GPIO12")),
         "'ISENSE_ADC'", "U301.CS", "ADC1")


def test_an_analog_net_that_reaches_no_gpio_is_reported():
    d = clean().with_net(Net("V12_SENSE", (("R4", "1"),), "3V3"))
    d = d.replace_net("UART1_TX", pins=(("U401", "IO17"),))
    only(g.report(d), "'V12_SENSE'", "reaches no GPIO")


def test_a_malformed_tag_is_refused_not_skipped():
    with pytest.raises(ValueError, match="IO7"):
        g.report(clean().replace_net("HORN_CMD", gpio="IO7"))


def test_the_command_line_says_pass_or_fail_and_exits_to_match(capsys):
    assert g.main([], clean()) == 0
    assert "PASS" in capsys.readouterr().out
    assert g.main([], clean().replace_net("HORN_CMD", gpio="GPIO43")
                  .replace_net("U0TXD", gpio="GPIO9")) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "never a driver" in out


# --- the real design ---------------------------------------------------------------
def test_the_real_netlist_closes():
    try:
        from tools import netlist
        design = netlist.current()
    except Exception as exc:                          # the netlist is its own test's job
        pytest.skip(f"tools.netlist does not build a Design: {type(exc).__name__}: {exc}")
    assert g.report(design) == []
    assert g.report() == []                           # the default IS the real design
