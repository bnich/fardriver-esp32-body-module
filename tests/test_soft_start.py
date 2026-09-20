"""D13 soft start: the numbers, and the two wrong circuits that look right.

The model is checked three ways that do not share its arithmetic:

  * against the closed-form KCL ramp, where that form is valid (no C107);
  * against conservation of energy -- a capacitor charged from a stiff source
    through ANY lossy switch leaves ½CV² in the switch;
  * against the capacitive divider for the key-off plug-in.

⛔ Pinned at the bottom, because both are easy to draw and both read as a 50 ms
soft start on paper: a gate with NO pull-down path (it never turns on),
and a 100 k pull-down with the 68 nF Miller capacitor -- which is what sizing
C105 from the current in R110, the resistor that OPPOSES the pull-down, gives.
That one ramps in ~8 ms at ~450 W.
"""
import math
from dataclasses import replace

import pytest

from tools import soft_start as ss

#: The wrong circuit: R110 = R101 = 100 k, C105 = 68 nF, no C107.
WRONG_100K = ss.Circuit(r_gs=100e3, r_pd=100e3, c_gd=68e-9, c_gs=0.0)


@pytest.fixture(scope="module")
def spec_84():
    return ss.simulate_key_on(84.0)


# --- the specified circuit -----------------------------------------------------
def test_the_spec_values_are_the_ones_under_test():
    assert ss.SPEC == ss.Circuit(r_gs=100e3, r_pd=540e3, c_gd=68e-9,
                                 c_gs=4.7e-6, v_zener=15.0)


def test_the_ramp_with_the_spec_values_is_about_50_ms(spec_84):
    assert spec_84.turns_on
    assert 0.040 <= spec_84.ramp_s <= 0.070


def test_every_corner_turns_on_inside_the_soa_target():
    for v in (84.0, 60.0):
        for fet in (ss.FAST, ss.NOMINAL, ss.SLOW):
            r = ss.simulate_key_on(v, ss.SPEC, fet)
            assert r.turns_on, (v, fet, r.why_not)
            assert r.soa_ok, (v, fet, r.p_peak_w, r.soa_limit_w)


def test_the_spec_circuit_fails_on_the_key_off_line_and_nothing_else(capsys):
    # ⛔ The design does NOT pass at the load the aux block put on the tap. The
    # key-off decay is over the derated DC SOA line at 84 V, and that is the
    # whole of the verdict: every KEY ON corner is still inside its own line.
    fails = ss.assess()
    assert [f for f in fails if not f.startswith("key off")] == []
    assert [f for f in fails if f.startswith("key off, 84 V")] != []
    assert ss.main([], ss.SPEC) == 1
    out = capsys.readouterr().out
    assert "⛔ FAIL" in out and "✅ PASS" not in out


def test_settled_gate_drive_is_the_divider_and_inside_the_gate_rating():
    assert ss.static_v_sg(84.0) == pytest.approx(84.0 * 100 / 640)     # 13.1 V
    assert ss.static_v_sg(60.0) == pytest.approx(60.0 * 100 / 640)     # 9.4 V
    assert ss.static_v_sg(200.0) == 15.0          # D102 clamps, under 20 V
    assert ss.static_v_sg(60.0) > ss.VTH_MAX


def test_turn_on_delay_is_the_gate_rc_reaching_threshold(spec_84):
    tau = (100e3 * 540e3 / 640e3) * (4.7e-6 + 68e-9 + ss.C_ISS)
    expected = -tau * math.log(1 - 3.0 / (84.0 * 100 / 640))
    assert spec_84.gate_delay_s == pytest.approx(expected, rel=1e-6)
    assert 0.05 < spec_84.turn_on_delay_s < 0.25


# --- the load is DERIVED, and it moves -------------------------------------------
def one_more_aux_channel(d):
    """The design with a fifth 12 V aux output hung on U303.

    The cheapest thing this netlist could grow. ⚠️ The point of the fixture is
    that NOTHING in soft_start.py mentions aux channels: the tap current it
    charges 440 µF with has to follow the netlist by itself, or it is a typed
    number wearing a derivation.
    """
    from tools.model import Net
    return d.with_net(Net("AUX12V_5", (("U303", "OUT5"),), "12V",
                          source="fixture: one more 1 A aux channel"))


def test_the_load_is_the_tap_current_power_budget_derives():
    from tools import netlist, power_budget
    r = power_budget.budget()
    assert ss.I_LOAD_MAX == pytest.approx(r.tap_a)
    assert ss.I_LOAD_MAX == pytest.approx(ss.tap_current_a(netlist.current()))
    assert ss.P_LOAD == pytest.approx(ss.I_LOAD_MAX * ss.V_LVC)
    # The WHOLE tap, not one converter: Q101 is upstream of both, so the
    # Cincon's 3 W is inside this figure as well as the 12 V brick's input.
    assert ss.I_LOAD_MAX > r.conv_in_a
    assert ss.I_LOAD_MAX == pytest.approx(
        r.conv_in_a + power_budget.LOGIC_IN_W / power_budget.LVC_V)


def test_one_more_aux_channel_moves_the_load_the_soft_start_carries():
    from tools import netlist
    d = netlist.current()
    before, after = ss.tap_current_a(d), ss.tap_current_a(one_more_aux_channel(d))
    # 1 A at 12 V, through the converter's efficiency, at the 60 V LVC.
    assert after - before == pytest.approx(1.0 * 12.0 / 0.90 / 60.0, rel=1e-6)


def test_a_heavier_tap_is_a_hotter_switch(monkeypatch):
    """And the number reaches the simulation, not just the report's header."""
    from tools import netlist
    heavier = ss.tap_current_a(one_more_aux_channel(netlist.current()))
    base_on, base_off = ss.simulate_key_on(84.0), ss.key_off(84.0)
    monkeypatch.setattr(ss, "I_LOAD_MAX", heavier)
    monkeypatch.setattr(ss, "P_LOAD", heavier * ss.V_LVC)
    assert ss.simulate_key_on(84.0).i_peak_a > base_on.i_peak_a
    assert ss.simulate_key_on(84.0).p_peak_w > base_on.p_peak_w
    assert ss.key_off(84.0).p_max_w > base_off.p_max_w


# --- the physics, checked from outside the integrator ---------------------------
@pytest.mark.parametrize("r_pd", [100e3, 330e3, 560e3])
@pytest.mark.parametrize("v_pack", [84.0, 60.0])
def test_the_ode_agrees_with_kcl_where_the_closed_form_holds(r_pd, v_pack):
    c = ss.Circuit(r_pd=r_pd, c_gs=0.0)
    sim = ss.simulate_key_on(v_pack, c).ramp_s
    assert sim == pytest.approx(ss.miller_estimate_s(v_pack, c), rel=0.02)


def test_kcl_by_hand_for_the_spec_pull_down():
    # I(C105) = (V - Vpl)/R_PD - Vpl/R_GS. At mid-ramp the FET carries
    # 440 uF x 84 V / 51 ms = 0.72 A into the caps plus the tap's 1.93 A, so
    # Vpl = 3 + sqrt(2.65 A / 5.558) = 3.69 V.
    # R_PD 540 k: 148.7 uA - 36.9 uA = 111.8 uA -> 68.1 nF x 84 V / 111.8 uA = 51.2 ms
    # ⚠️ The 1.93 A is the DERIVED tap current: this hand figure moves when the
    # netlist's load does, which is the point -- and is why it is written out.
    assert ss.I_LOAD_MAX == pytest.approx(1.93, abs=0.005)
    assert ss.miller_estimate_s(84.0, ss.Circuit(c_gs=0.0)) == \
        pytest.approx(0.0512, rel=0.02)


def test_the_gate_source_resistor_opposes_the_pull_down():
    # The defect in one line: R_GS's current was taken as the current that
    # charges C105. It is SUBTRACTED from it, so a stiffer R_GS slows the ramp.
    base = ss.simulate_key_on(84.0, ss.Circuit(c_gs=0.0)).ramp_s
    stiff = ss.simulate_key_on(84.0, ss.Circuit(r_gs=47e3, c_gs=0.0)).ramp_s
    assert stiff > base * 1.2


def test_the_ramp_scales_with_the_miller_capacitor():
    one = ss.simulate_key_on(84.0, ss.Circuit(c_gs=0.0)).ramp_s
    two = ss.simulate_key_on(84.0, ss.Circuit(c_gd=136e-9, c_gs=0.0)).ramp_s
    assert two / one == pytest.approx(2.0, rel=0.05)


def test_with_no_load_the_fet_absorbs_half_c_v_squared(monkeypatch):
    monkeypatch.setattr(ss, "load_current", lambda v_d: 0.0)
    for c in (ss.SPEC, WRONG_100K):
        r = ss.simulate_key_on(84.0, c)
        assert r.energy_j == pytest.approx(0.5 * 440e-6 * 84.0 ** 2, rel=0.01)


def test_a_slower_ramp_costs_more_energy_not_less(spec_84):
    # Peak power falls with a longer ramp; the energy the FET absorbs RISES,
    # because the load draws through it for longer.
    fast = ss.simulate_key_on(84.0, replace(ss.SPEC, r_pd=270e3))
    assert fast.p_peak_w > spec_84.p_peak_w
    assert fast.energy_j < spec_84.energy_j
    assert spec_84.energy_j > 0.5 * 440e-6 * 84.0 ** 2


def test_the_integration_step_is_fine_enough():
    coarse = ss.simulate_key_on(84.0, WRONG_100K, ss.FAST, dt=10e-6)
    fine = ss.simulate_key_on(84.0, WRONG_100K, ss.FAST, dt=2.5e-6)
    assert coarse.ramp_s == pytest.approx(fine.ramp_s, rel=0.005)
    assert coarse.p_peak_w == pytest.approx(fine.p_peak_w, rel=0.005)


# --- SOA -------------------------------------------------------------------------
def test_soa_figures_are_the_70_degree_lines_with_the_derate():
    assert ss.SOA_DERATE == pytest.approx((150 - 60) / (150 - 25))
    assert ss.soa_limit_w(0.010) == pytest.approx(460 * 0.72)
    assert ss.soa_limit_w(0.100) == pytest.approx(254 * 0.72)
    assert ss.soa_limit_w(5.0) == pytest.approx(191 * 0.72)


def test_soa_is_never_extrapolated_in_the_generous_direction():
    assert ss.soa_limit_w(0.001) == ss.soa_limit_w(0.010)     # no 1 ms credit
    assert ss.soa_limit_w(0.101) == ss.soa_limit_w(10.0)      # DC past 100 ms
    widths = [0.001, 0.01, 0.02, 0.05, 0.1, 0.2, 1.0]
    limits = [ss.soa_limit_w(t) for t in widths]
    assert limits == sorted(limits, reverse=True)
    assert 254 * 0.72 < ss.soa_limit_w(0.0316) < 460 * 0.72


def test_the_equal_energy_pulse_is_energy_over_peak_power(spec_84):
    assert spec_84.pulse_s == pytest.approx(spec_84.energy_j / spec_84.p_peak_w)
    assert spec_84.p_peak_w < spec_84.soa_limit_w


# --- key OFF, pack plugged in ----------------------------------------------------
def test_key_off_plug_in_stays_under_the_minimum_threshold():
    p = ss.plug_in(84.0)
    assert p.v_sg_peak < 1.6
    assert p.ok and p.hv_sw_peak == 0.0


def test_the_plug_in_excursion_is_the_capacitive_divider():
    c_gd, c_gs = 68e-9 + ss.C_RSS, 4.7e-6 + ss.C_ISS - ss.C_RSS
    assert ss.plug_in(84.0).v_sg_peak == pytest.approx(
        84.0 * c_gd / (c_gd + c_gs), rel=1e-3)


def test_without_c107_a_plug_in_turns_the_fet_on_with_the_key_off():
    p = ss.plug_in(84.0, ss.Circuit(c_gs=0.0))
    assert p.v_sg_peak == pytest.approx(15.0)       # straight to the zener
    assert not p.ok
    assert p.hv_sw_peak > 5.0                       # the module charges, key out
    assert any("key-OFF plug-in" in f for f in ss.assess(ss.Circuit(c_gs=0.0)))


def test_key_off_delay_is_c107_through_r110():
    # 13.13 V (84 x 100/640) decaying to the plateau of a minimum-threshold FET
    # at the derived load.
    tau = 100e3 * (4.7e-6 + 68e-9 + ss.C_ISS)
    v_pl = 2.0 + math.sqrt(ss.I_LOAD_MAX / ss.FAST.k)
    assert ss.key_off_delay_s(84.0) == pytest.approx(
        tau * math.log((84.0 * 100 / 640) / v_pl))
    assert ss.key_off_delay_s(84.0, ss.Circuit(c_gs=0.0)) < 0.02


# --- key OFF: the criterion that is IN the verdict ---------------------------------
def test_the_key_off_soa_line_is_in_the_verdict_and_bites_today():
    # ⛔ This is the defect the check was written for, and it is the CURRENT
    # design: the tool used to print this ⛔ inline and exit 0 because assess()
    # never looked at it.
    hot = ss.key_off(84.0)
    assert not hot.ok
    assert hot.p_max_w == pytest.approx(ss.I_LOAD_MAX * 84.0)
    assert hot.soa_limit_w == pytest.approx(ss.SOA_DC_84V_TC70 * ss.SOA_DERATE)
    assert [f for f in ss.assess() if f.startswith("key off, 84 V")] != []
    assert ss.main([], ss.SPEC) == 1


def test_the_key_off_verdict_follows_the_load_it_is_not_always_on(monkeypatch):
    # At the 0.62 A that predated the aux block, the same criterion clears --
    # so what fails is the load, not a check that can only ever say no.
    monkeypatch.setattr(ss, "I_LOAD_MAX", 0.62)
    monkeypatch.setattr(ss, "P_LOAD", 0.62 * ss.V_LVC)
    hot = ss.key_off(84.0)
    assert hot.ok and hot.sim_ok
    assert ss.assess() == []


def test_the_integrated_decay_is_under_the_bound_and_still_over_the_line():
    # Refining the bound into a simulation does NOT rescue the design: it
    # takes 162 W down to ~147 W, and the line is 138 W.
    hot = ss.key_off(84.0)
    assert hot.p_sim_w < hot.p_max_w        # so the bound is the stricter test
    assert not hot.sim_ok
    assert hot.energy_j > 15.0              # ~21 J, mostly after the hold


def test_the_decay_is_not_a_short_pulse_so_the_dc_line_is_the_right_row():
    hot = ss.key_off(84.0)
    assert hot.pulse_s > 0.100                                  # past the last row
    assert hot.soa_at_pulse_w == pytest.approx(hot.soa_limit_w)
    # ⚠️ What makes it slow is the GATE's RC, not the 440 µF: the caps alone
    # would be emptied in ~19 ms at this load.
    assert hot.pulse_s > 5 * (ss.C_LOAD * 84.0 / ss.I_LOAD_MAX)


def test_the_decay_integration_step_is_fine_enough():
    coarse, fine = ss.key_off_decay(84.0, dt=50e-6), ss.key_off_decay(84.0, dt=2e-6)
    assert coarse[0] == pytest.approx(fine[0], rel=1e-3)     # peak
    assert coarse[1] == pytest.approx(fine[1], rel=1e-3)     # energy


def test_the_60_v_corner_is_under_the_line_so_the_check_discriminates():
    assert ss.key_off(60.0).ok
    assert [f for f in ss.assess() if f.startswith("key off, 60 V")] == []


def test_the_key_off_figure_is_stated_as_a_bound_with_its_alternative():
    hot = ss.key_off(84.0)
    # The bound is I_LOAD_MAX x V_pack; the constant-power case held to the
    # converters' stated 43 V input floor is lower, and the verdict text says
    # which is which rather than quietly using the kinder one.
    assert hot.dropout_case_w < hot.p_max_w
    assert hot.dropout_case_w == pytest.approx(
        ss.P_LOAD * (84.0 / ss.V_CONVERTER_MIN - 1.0))
    text = " ".join(ss.assess())
    assert "BOUND" in text and f"{ss.V_CONVERTER_MIN:.0f} V" in text


# --- solving for the resistor ----------------------------------------------------
@pytest.mark.parametrize("target_ms", [40, 50, 70])
def test_solve_r_pd_round_trips_through_the_simulation(target_ms):
    r_pd = ss.solve_r_pd(target_ms / 1e3)
    got = ss.simulate_key_on(84.0, replace(ss.SPEC, r_pd=r_pd)).ramp_s
    assert got == pytest.approx(target_ms / 1e3, rel=0.01)


def test_solve_r_pd_puts_the_spec_resistor_near_its_own_ramp(spec_84):
    assert ss.solve_r_pd(spec_84.ramp_s) == pytest.approx(540e3, rel=0.01)


def test_solve_r_pd_refuses_a_ramp_no_resistor_can_give():
    with pytest.raises(ValueError):
        ss.solve_r_pd(0.0001)
    with pytest.raises(ValueError):
        ss.solve_r_pd(60.0)


# --- the circuit is read off the netlist, not typed twice ---------------------------
def d13_fragment(r101=("270k", "270k"), q105_source="GND"):
    """POWER's D13 block, as a Design."""
    from tools.model import Design, Net, Part

    def two(ref, kind, value, pins=("1", "2")):
        return Part(ref, f"X-{value}", "0805", "POWER", kind, pins, 1.0, value=value,
                    v_max=250.0)
    parts = (
        Part("Q101", "IXTP26P20P", "TO-220", "POWER", "PFET", ("G", "D", "S"), 4.5,
             v_max=200.0),
        Part("Q105", "BSS127", "SOT-23", "POWER", "NFET", ("G", "D", "S"), 1.2,
             v_max=600.0),
        two("R110", "R", "100k"), two("R101A", "R", r101[0]), two("R101B", "R", r101[1]),
        two("C105", "C", "68nF C0G/film ≥250 V"), two("C107", "C", "4.7uF 25V"),
        two("D102", "ZENER", "15V", ("A", "K")),
        two("R113", "R", "100k"),
    )
    nets = (
        Net("HV_BPLUS", (("Q101", "S"), ("R110", "2"), ("D102", "K"), ("C107", "2")), "84V"),
        Net("D13_GATE", (("Q101", "G"), ("R110", "1"), ("D102", "A"), ("C105", "1"),
                         ("C107", "1"), ("R101A", "1")), "84V"),
        Net("D13_MID", (("R101A", "2"), ("R101B", "1")), "84V"),
        Net("D13_PD", (("R101B", "2"), ("Q105", "D")), "84V"),
        Net("HV_SW", (("Q101", "D"), ("C105", "2")), "84V"),
        Net("D13_EN", (("Q105", "G"), ("R113", "1")), "12V"),
        Net(q105_source, (("Q105", "S"), ("R113", "2")),
            "GND" if q105_source == "GND" else "84V"),
    )
    return Design(parts, nets)


def test_the_gate_network_is_read_by_following_the_copper():
    c = ss.circuit_from(d13_fragment(r101=("270k", "270k")))
    assert ss.differences(c, ss.SPEC) == []
    assert c.r_pd == pytest.approx(540e3)           # the two halves, in series


def test_a_changed_resistor_in_the_netlist_is_the_one_simulated():
    c = ss.circuit_from(d13_fragment(r101=("330k", "330k")))
    assert c.r_pd == pytest.approx(660e3)
    assert ss.differences(c, ss.SPEC) == ["r_pd: 660000 vs 540000"]


def test_a_pull_down_that_reaches_no_ground_is_read_as_absent():
    # The far end of R101 on the key switch's B+ side instead of on a grounded
    # switch -- an easy way to draw it, and V_GS is then 0 for ever. Read from the copper, it is
    # "no pull-down", and the verdict follows without anyone typing it.
    c = ss.circuit_from(d13_fragment(q105_source="KEY_SW_OUT"))
    assert c.r_pd is None
    assert any("never turns on" in f for f in ss.assess(c))


def test_a_gate_with_no_bias_resistor_is_refused():
    with pytest.raises(ValueError, match="not biased OFF"):
        ss.circuit_from(d13_fragment().without_part("R110"))


@pytest.mark.parametrize("kind, text, expected", [
    ("R", "270k", 270e3), ("R", "1k00 1%", 1000.0), ("R", "5k1", 5100.0),
    ("R", "0R", 0.0), ("R", "120R", 120.0), ("R", "1M", 1e6), ("R", "2k0 1%", 2000.0),
    ("C", "68nF C0G/film ≥250 V", 68e-9), ("C", "4.7uF 25V", 4.7e-6),
    ("C", "100pF", 100e-12), ("ZENER", "15V", 15.0),
])
def test_value_strings_as_the_netlist_writes_them(kind, text, expected):
    from tools.model import Part
    part = Part("X1", "X", "0805", "POWER", kind, ("1", "2"), 1.0, value=text)
    assert ss._value(part) == pytest.approx(expected)


def test_an_unreadable_value_is_an_error_not_a_zero():
    from tools.model import Part
    with pytest.raises(ValueError, match="R9"):
        ss._value(Part("R9", "X", "0805", "POWER", "R", ("1", "2"), 1.0, value="TBD"))


def test_the_real_netlists_gate_network_fails_only_on_the_key_off_line(capsys):
    try:
        from tools import netlist
        design = netlist.current()
    except Exception as exc:                  # the netlist is its own test's job
        pytest.skip(f"tools.netlist does not build a Design: {type(exc).__name__}: {exc}")
    c = ss.circuit_from(design)
    assert [f for f in ss.assess(c) if not f.startswith("key off")] == []
    assert [f for f in ss.assess(c) if f.startswith("key off, 84 V")] != []
    # The same design as the specified one, to within a 5 % resistor.
    assert ss.differences(c, ss.SPEC, rel=0.05) == []
    assert ss.main([]) == 1
    assert "read off tools/netlist.py" in capsys.readouterr().out


# --- ⛔ the two wrong circuits, pinned ----------------------------------------------
def test_no_pull_down_path_means_it_never_turns_on(capsys):
    c = ss.Circuit(r_pd=None)
    for v in (84.0, 60.0):
        r = ss.simulate_key_on(v, c)
        assert not r.turns_on
        assert "never turns on" in r.why_not and "no pull-down path" in r.why_not
        assert not r.soa_ok                 # a dead switch is not a pass
    assert any("never turns on" in f for f in ss.assess(c))
    assert ss.main([], c) == 1
    assert "FAIL" in capsys.readouterr().out


def test_a_divider_that_stops_short_of_threshold_never_turns_on():
    r = ss.simulate_key_on(60.0, ss.Circuit(r_pd=3.3e6), ss.SLOW)
    assert not r.turns_on and "never turns on" in r.why_not
    assert r.v_sg_on == pytest.approx(60.0 * 100 / 3400)


def test_a_100k_pull_down_is_a_fast_ramp_over_the_soa_target(capsys):
    r = ss.simulate_key_on(84.0, WRONG_100K)
    assert r.turns_on
    assert r.ramp_s < 0.015                 # ~8 ms, not 50 ms
    assert r.p_peak_w > 350                 # ~450 W, not 114 W
    assert not r.soa_ok
    fails = ss.assess(WRONG_100K)
    assert any("over the SOA target" in f for f in fails)
    assert any("outside the" in f and "ms target" in f for f in fails)
    assert ss.main([], WRONG_100K) == 1
    assert "FAIL" in capsys.readouterr().out


def test_adding_c107_alone_does_not_rescue_the_100k_pull_down():
    fails = ss.assess(replace(WRONG_100K, c_gs=4.7e-6))
    assert ss.simulate_key_on(84.0, replace(WRONG_100K, c_gs=4.7e-6)).ramp_s < 0.015
    assert any("ms target" in f for f in fails)


# --- the tool must never report on a design it could not read -------------------
def test_main_fails_when_the_netlist_cannot_be_read(monkeypatch, capsys):
    monkeypatch.setattr(ss, "_netlisted", lambda: (None, "ValueError: gate not biased"))
    assert ss.main([]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "PASS" not in out


def test_the_level_shifter_divider_is_read_off_the_netlist():
    from tools import netlist
    top, bottom, cap = ss.enable_from(netlist.current())
    assert top == pytest.approx(998e3) and bottom == pytest.approx(100e3)
    assert cap == pytest.approx(100e-9)


def test_a_weak_level_shifter_divider_fails():
    # bottom resistor 10 k instead of 100 k: 0.43 V at 43 V -- Q105 never turns on
    fails = ss.assess(ss.SPEC, en=(998e3, 10e3, 100e-9))
    assert any("level shifter" in f for f in fails)
    assert not any("level shifter" in f for f in ss.assess(ss.SPEC))


def test_a_zener_at_the_gate_rating_fails():
    from dataclasses import replace as _replace
    assert any("D102" in f for f in ss.assess(_replace(ss.SPEC, v_zener=20.0)))
