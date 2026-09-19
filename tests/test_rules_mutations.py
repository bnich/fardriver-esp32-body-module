"""The checks review's mutations (2026-09-19), each an electrically wrong change
to the REAL netlist that once passed every gate.  Each must now be caught by
the rule named, and the real design must stay clean (test_design_clean.py).
"""
from tools import netlist, rules
from tools.model import Net, Part

D = netlist.current()


def fired(d, rule_id):
    return [e for e in rules.check_all(d) if e.startswith(rule_id + ":")]


def add(d, part, landing):
    """`part`, each pin landed on the net named in `landing` (a new net when
    it does not exist yet: (name, domain))."""
    d = d.with_part(part)
    for pin, net in landing.items():
        if isinstance(net, tuple):
            name, domain = net
            d = d.with_net(Net(name, ((part.refdes, pin),), domain))
        else:
            d = d.replace_net(net, pins=d.net(net).pins + ((part.refdes, pin),))
    return d


def move(d, ref, pin, to):
    lifted = d.without_pin(ref, pin)
    return lifted.replace_net(to, pins=lifted.net(to).pins + ((ref, pin),))


def _r(ref, board, value, pkg="0805"):
    return Part(ref, f"R-{value}", pkg, board, "R", ("1", "2"), 0.6, value=value,
                v_max=150.0)


def _fet(ref, board):
    return Part(ref, "AO3400A", "SOT-23", board, "NFET", ("G", "D", "S"), 1.2, v_max=30.0)


# ── CK-1: current through TVS / zener / 0 Ω link / MECH ──────────────────────
def test_m06_a_tvs_from_the_switched_rail_onto_the_key_wire_latches_it():
    tvs = Part("D107", "SMCJ90A", "SMC", "POWER", "TVS", ("A", "K"), 2.6, v_max=90.0)
    assert fired(add(D, tvs, {"A": "HV_SW", "K": "KSW"}), "D10")


def test_m21_a_0_ohm_link_from_84_v_onto_the_12_v_rail():
    tie = Part("R212", "NET-TIE", "copper", "POWER", "R", ("1", "2"), 0.04, value="0R")
    assert fired(add(D, tie, {"1": "HV_C1_P", "2": "V12"}), "BD-2")


def test_m20_a_mech_jumper_from_84_v_onto_the_5_v_rail():
    jumper = Part("M201", "JUMPER", "wire", "POWER", "MECH", ("1", "2"), 1.0)
    assert fired(add(D, jumper, {"1": "HV_C2_HOLD", "2": "V5"}), "BD-2")


def test_m18_a_tvs_puts_the_strapping_pin_on_a_harness_wire():
    tvs = Part("D499", "SMBJ18A", "SMB", "LOGIC", "TVS", ("A", "K"), 2.4, v_max=18.0)
    assert fired(add(D, tvs, {"A": "BOOT_IO0", "K": "IN08A_RUNNING_WIRE"}), "GPIO-STRAP")


# ── CK-2: a resistor to ground no longer hides a divider's real voltage ──────
def test_m01_a_wrong_divider_puts_8_v_on_an_adc_pin():
    assert any("V12_SENSE" in e for e in fired(D.replace_part("R338", value="100k"), "LV-LOGIC"))


def test_m02_a_wrong_divider_overdrives_an_expander_pin():
    assert any("ACC_SENSE" in e for e in fired(D.replace_part("R343", value="10k"), "LV-LOGIC"))


def test_m36_a_resistor_from_the_horn_gate_to_the_stop_lamp_gate():
    bad = add(D, _r("R399", "OUTPUTS", "1k"), {"1": "HORN_GATE", "2": "Q1_GATE"})
    assert any("HORN" in e for e in fired(bad, "LV-LOGIC")), "IO42 sees ~5.7 V"
    assert fired(bad, "LISTEN"), "firmware now drives the stop lamp's gate"


# ── CK-3: the module only listens to the brake and kill hardware ─────────────
def test_m04_a_firmware_fet_that_holds_the_kill_off():
    bad = add(D, _fet("Q306", "OUTPUTS"), {"G": "BUZZ_GATE", "D": "Q2_GATE", "S": "GND"})
    assert any("Q2_GATE" in e for e in fired(bad, "LISTEN"))


def test_m04b_boost_that_defeats_the_run_off_switch():
    bad = add(D, _fet("Q402", "LOGIC"), {"G": "BOOST_GATE", "D": "RUN", "S": "GND"})
    assert any("RUN" in e for e in fired(bad, "LISTEN"))


# ── CK-4 / HV-3: a clamp must be under what it protects ──────────────────────
def test_m35_an_input_tvs_that_clamps_above_the_converters_rating():
    bad = D.replace_part("D101", mpn="SMCJ130A", v_max=130.0, v_clamp=209.0)
    assert any("D101" in e for e in fired(bad, "VR-CLAMP"))


def test_m34_a_15_v_array_on_3_3_v_inputs():
    d401 = D.part("D401")
    bad = D.replace_part("D401", mpn="SMS15T1G", v_max=15.0, v_clamp=29.0)
    assert any("D401" in e for e in fired(bad, "VR-CLAMP"))
    assert d401.v_clamp is not None and d401.v_clamp < 29.0


# ── CK-6: an array's pins by role, so a swap is a polarity error ─────────────
def test_m03_an_array_with_its_ground_and_a_line_swapped():
    a = D.net_of("D401", "A2").name
    b = D.net_of("D401", "K1").name
    bad = move(move(D, "D401", "A2", b), "D401", "K1", a)
    assert any("D401" in e for e in fired(bad, "POL"))


# ── CK-7: labels do not switch protection off ────────────────────────────────
def test_m29_parking_the_brake_kill_terminal_does_not_excuse_its_tvs():
    bad = D.replace_connector("J309", parked=True).replace_part("D316", dnp=True)
    assert any("J309" in e or "BL" in e for e in fired(bad, "PROT"))


def test_m19_a_clamp_returned_through_10k_is_not_grounded():
    bad = D.without_pin("D101", "A")
    bad = bad.with_net(Net("TVS_RTN", (("D101", "A"),), "GND"))
    bad = add(bad, _r("R199", "POWER", "10k", "1206"), {"1": "TVS_RTN", "2": "GND"})
    assert fired(bad, "PROT") or fired(bad, "GND-ISLAND")


# ── CK-8: resistor power ─────────────────────────────────────────────────────
def test_m27_a_100_ohm_lever_pull_up_burns_an_0805():
    assert any("R313" in e for e in fired(D.replace_part("R313", value="100R"), "VR-POWER"))


# ── CK-10: a switch to ground needs a pull-UP ────────────────────────────────
def test_m17_a_pull_down_where_the_boost_button_needs_a_pull_up():
    assert any("IN07" in e for e in fired(move(D, "R409", "2", "GND"), "PULL-DIR"))


def test_m33_a_gate_tied_to_its_own_source():
    assert any("Q301" in e for e in fired(move(D, "Q301", "G", D.net_of("Q301", "S").name),
                                          "TURN-ON"))


def test_the_real_design_passes_every_new_rule():
    for rule_id in ("LISTEN", "VR-CLAMP", "VR-POWER", "PULL-DIR"):
        assert fired(D, rule_id) == [], rule_id
