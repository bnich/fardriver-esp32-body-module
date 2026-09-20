"""IO-1 / IO-2: four 12 V and four 5 V aux outputs, 1 A each, on expander #3.

The 12 V four are a third TPS4H160B, identical in hardware to the lamp
channels; the 5 V four are a buck of their own and four current-limited load
switches.  ⚠️ Nothing here is a hardware function: every one of the eight is
OFF until firmware drives expander #3, and the expander's bits come out of
reset as inputs.
"""
from tools import netlist, rules
from tools.eprj3.schematic import landed_pins

D = netlist.current()
BITS = {  # expander #3 (U304, 0x22)
    "GPA0": "AUX12_1_CMD", "GPA1": "AUX12_2_CMD", "GPA2": "AUX12_3_CMD",
    "GPA3": "AUX12_4_CMD",
    "GPA4": "DIAG3_CMD", "GPA5": "AUX12_CMD", "GPA6": "AUX5V_1_EN",
    "GPB0": "AUX5V_2_EN", "GPB1": "AUX5V_3_EN", "GPB2": "AUX5V_4_EN",
    "GPB3": "AUX5V_1_FAULT", "GPB4": "AUX5V_2_FAULT", "GPB5": "AUX5V_3_FAULT",
    "GPB6": "AUX5V_4_FAULT",
}


def _net(ref, pin):
    return landed_pins(D)[(ref, pin)]


def _other_end(ref, pin):
    return _net(ref, "2" if pin == "1" else "1")


def test_expander_3_bit_map():
    assert {b: _net("U304", b) for b in BITS} == BITS
    assert set(D.part("U304").nc) >= {"GPA7", "GPB7"}
    assert (_net("U304", "A0"), _net("U304", "A1"), _net("U304", "A2")) == \
        ("GND", "V3P3", "GND")


def test_expander_3_is_on_the_board_it_drives_and_shares_the_one_i2c_bus():
    """It sits on OUTPUTS with the aux block (IO-7), so what crosses STACK is
    two bus wires rather than fourteen commands."""
    assert D.part("U304").board == "OUTPUTS"
    for bus, pin in (("SDA", "SDA"), ("SCL", "SCK")):
        assert _net("U304", pin) == bus
        assert D.net(bus).interface == "STACK"
        assert {r for r, _ in D.net(bus).pins if r.startswith("U")} == \
            {"U401", "U402", "U403", "U304"}


def test_the_third_tps4h160b_shares_cs2_and_fault2_through_its_own_diag_en():
    assert _net("U303", "CS") == _net("U302", "CS") == "CS2_RAW"
    assert _net("U303", "FAULT") == _net("U302", "FAULT") == "FAULT2_DEV"
    assert _net("U303", "DIAG_EN") != _net("U302", "DIAG_EN")
    cl = [r for r, _ in D.net(_net("U303", "CL")).pins if r.startswith("R")]
    assert [D.part(r).value for r in cl] == ["1k5 1%"]


def test_every_aux_output_reaches_its_terminal_with_a_clamp():
    for n in range(1, 5):
        v12 = {r for r, _ in D.net(f"AUX12V_{n}").pins}
        assert "J313" in v12 and any(D.part(r).mpn == "SMF18A"
                                     for r in v12 if r.startswith("D"))
        v5 = {r for r, _ in D.net(f"AUX5V_{n}").pins}
        assert "J314" in v5 and any(D.part(r).kind == "TVS"
                                    for r in v5 if r.startswith("D"))
    assert D.connector("J314").side == "bottom"
    assert D.connector("J314").pitch_mm == 3.50


def test_the_12_v_terminal_shares_returns_so_it_can_be_seven_way():
    """⚠️ SEVEN contacts, because 3.81 × 8 is what the two general-input
    terminals are and a plug must not cross rows (tests/test_rows.py).  Each
    ground contact carries at most two outputs: 2 A against the family's 8 A.
    """
    nets = [cp.net for cp in D.connector("J313").pins]
    assert nets == ["AUX12V_1", "GND", "AUX12V_2", "GND", "AUX12V_3", "GND",
                    "AUX12V_4"]
    assert nets.count("GND") == 3 and len(nets) - nets.count("GND") == 4


def test_the_5_v_outputs_come_off_their_own_buck_never_the_logic_rail():
    """A shorted aux wire must not brown out the S3 (spec §8.4): the logic's
    5 V is the Cincon's isolated output on POWER and nothing here touches it.
    """
    assert _net("U305", "PVIN") == "V12"
    for n in range(1, 5):
        assert _net(f"U{305 + n}", "IN") == "V5AUX"
        assert _net(f"U{305 + n}", "OUT") == f"AUX5V_{n}"
    assert "V5" not in {n.name for n in D.nets_of("U305")}
    assert {r for r, _ in D.net("V5").pins if r.startswith("U")} == \
        {"U202", "U405"}


def test_every_5_v_channel_has_its_limit_set_its_enable_down_and_its_flag_up():
    for n in range(1, 5):
        u = f"U{305 + n}"
        ilim = [r for r, _ in D.net(_net(u, "ILIM")).pins if r.startswith("R")]
        assert [D.part(r).value for r in ilim] == ["20k"], u
        down = [r for r, p in D.net(_net(u, "EN")).pins
                if r.startswith("R") and _other_end(r, p) == "GND"]
        assert [D.part(r).value for r in down] == ["100k"], u
        up = [r for r, p in D.net(_net(u, "FAULT")).pins
              if r.startswith("R") and _other_end(r, p) == "V3P3"]
        assert [D.part(r).value for r in up] == ["10k"], u


def test_aux12_is_a_firmware_output_now():
    assert _net("U301", "IN1") == "AUX12_EN"
    assert "V3P3" not in {_net("R346", "1"), _net("R346", "2")}


def test_an_aux_enable_left_floating_is_caught():
    """D14: every enable biases OFF. Lifting a 5 V switch's EN pull-down must
    fire -- and it is an IC's EN, not a FET gate, which is the case D14 did
    not cover until the aux block arrived."""
    en = "AUX5V_1_EN"
    down = next(r for r, p in D.net(en).pins if r.startswith("R"))
    bad = D.without_pin(down, "1").without_pin(down, "2").without_part(down)
    assert any(e.startswith(("D14:", "TURN-ON:")) for e in rules.check_all(bad))


def test_the_real_design_passes_the_enable_rule_it_adds():
    """An assertion that never fires is not a test -- and a rule that fires on
    the real design is not a rule. Both halves, in one file."""
    assert [e for e in rules.d14_gate_bias(D)] == []
