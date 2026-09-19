"""IO-8 / IO-9: the brake cut, the brake lamp and the run/off kill are firmware
I/O. The module has no dedicated brake or kill circuit; BL is released and the
STOP lamp is off whenever the firmware is not running."""
from tools import netlist, rules
from tools.eprj3.schematic import landed_pins

D = netlist.current()
GONE_PARTS = {"Q304", "Q305", "D301", "D302", "D303", "D304", "D305", "D306",
              "R313", "R314", "R315", "R316", "R347", "R348", "D318", "R430", "R431"}
GONE_NETS = {"Q1_GATE", "Q2_GATE", "STOP_CMD", "STOP_IN4", "IN05_NODE",
             "IN06_NODE", "IN11_SENSE", "RUN"}


def _net(ref, pin):
    return landed_pins(D)[(ref, pin)]


def _other_end(ref, pin):
    return _net(ref, "2" if pin == "1" else "1")


def test_no_brake_or_kill_hardware_is_left():
    assert not GONE_PARTS & {p.refdes for p in D.parts}
    assert not GONE_NETS & {n.name for n in D.nets}


def test_the_stop_lamp_is_a_firmware_output_on_gpio19():
    assert D.net("LGT_STOP").gpio == "GPIO19"
    assert _net("U302", "IN4") == "LGT_STOP_IN"
    series = [r for r, _ in D.net("LGT_STOP_IN").pins if r.startswith("R")]
    assert len(series) == 1 and D.part(series[0]).value == "4k7"
    assert _other_end(series[0], next(p for r, p in D.net("LGT_STOP_IN").pins if r == series[0])) == "LGT_STOP"


def test_bl_is_an_open_drain_output_on_gpio16_released_by_default():
    assert D.net("BL_CMD").gpio == "GPIO16"
    q = D.part("Q106")
    assert (q.mpn, q.kind) == ("AO3400A", "NFET")
    assert _net("Q106", "D") == "BL" and _net("Q106", "S") == "GND"
    gate = _net("Q106", "G")
    downs = [r for r, p in D.net(gate).pins if r.startswith("R")
             and D.part(r).value == "10k" and _other_end(r, p) == "GND"]
    assert downs, "BL's FET needs a hard gate pull-down: released until firmware drives it"
    assert 16 not in rules.GPIO_RESET_PULL_UP


def test_the_levers_and_run_are_plain_inputs():
    assert D.net("IN05_BRAKE_L").gpio == "GPIO15"
    assert D.net("IN06_BRAKE_R").gpio == "GPIO20"
    assert _net("U402", "GPB2") == "IN11_RUN"
    assert D.part("D313").mpn == "SMS05T1G", "the lever lines are 3.3 V class now (BD-16)"


def test_bl_on_a_pin_pulled_up_at_reset_is_refused():
    """GPIO20 comes out of reset with USB_PU (S3 datasheet v2.2 Table 2-1): a
    gate on it would cut the motor through boot, against IO-9."""
    bad = D.without_pin("U401", "IO16").without_pin("U401", "IO20")
    bad = bad.replace_net("BL_CMD", pins=bad.net("BL_CMD").pins + (("U401", "IO20"),), gpio="GPIO20")
    bad = bad.replace_net("IN06_BRAKE_R", pins=bad.net("IN06_BRAKE_R").pins + (("U401", "IO16"),), gpio="GPIO16")
    assert any(e.startswith("GPIO-RESET-PULL:") and "BL_CMD" in e for e in rules.check_all(bad))


def test_the_listen_rule_is_gone():
    assert "listen_only" not in {f.__name__ for f in rules.ALL_RULES}
