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

⚠️ TWO loads, and the tests hold each to its own event (IO-16, 2026-09-20):
KEY ON charges 440 µF against `I_LOAD_MAX`, the whole tap, while the key-off
decay carries `I_LOAD_SHED`, because the firmware releases every aux output
when `KEY_SENSE` goes inactive. That makes a PART's SOA margin depend on a
FIRMWARE behaviour, so three things are pinned here and not left to prose: the
shed figure keeps the 5 V buck's unsheddable standing draw, the key-off gate
still FIRES on a heavier shed load, and the un-shed case is still over the
line and still in the report.
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


def test_the_spec_circuit_passes_every_criterion(capsys):
    # Every KEY ON corner is inside its own SOA line, and the key-off decay
    # clears the DC line on the SHED tap (IO-16). ⚠️ The report still carries
    # the un-shed figure beside it as the residual risk -- pinned below.
    assert ss.assess() == []
    assert ss.main([], ss.SPEC) == 0
    out = capsys.readouterr().out
    assert "✅ PASS" in out and "⛔ FAIL" not in out


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
    """And the number reaches the simulation, not just the report's header.

    ⚠️ Each load moves its OWN event and not the other's. A ninth aux channel
    is on the tap at key-on, so it makes the ramp hotter; by the time the
    key-off decay starts the firmware has released it (IO-16), so it must not
    move that one -- and a heavier SHED load must move key-off alone.
    """
    from tools import netlist
    heavier = ss.tap_current_a(one_more_aux_channel(netlist.current()))
    base_on, base_off = ss.simulate_key_on(84.0), ss.key_off(84.0)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(ss, "I_LOAD_MAX", heavier)
        mp.setattr(ss, "P_LOAD", heavier * ss.V_LVC)
        assert ss.simulate_key_on(84.0).i_peak_a > base_on.i_peak_a
        assert ss.simulate_key_on(84.0).p_peak_w > base_on.p_peak_w
        assert ss.key_off(84.0).p_max_w == pytest.approx(base_off.p_max_w)
    shed = ss.I_LOAD_SHED * 1.5
    monkeypatch.setattr(ss, "I_LOAD_SHED", shed)
    monkeypatch.setattr(ss, "P_LOAD_SHED", shed * ss.V_LVC)
    assert ss.key_off(84.0).p_max_w > base_off.p_max_w
    assert ss.simulate_key_on(84.0).p_peak_w == pytest.approx(base_on.p_peak_w)


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
    monkeypatch.setattr(ss, "load_current", lambda v_d, i_load_a=None: 0.0)
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
    # at the SHED load, which is what key-off carries (IO-16).
    tau = 100e3 * (4.7e-6 + 68e-9 + ss.C_ISS)
    v_pl = 2.0 + math.sqrt(ss.I_LOAD_SHED / ss.FAST.k)
    assert ss.key_off_delay_s(84.0) == pytest.approx(
        tau * math.log((84.0 * 100 / 640) / v_pl))
    # ⚠️ A LIGHTER load holds on LONGER -- it pinches off at a lower gate
    # drive -- so the un-shed hold is the SHORTER of the two. That shorter one
    # is the window the firmware has to release the outputs in, which is the
    # conservative way round to quote it.
    un_shed = ss.key_off_delay_s(84.0, i_load_a=ss.I_LOAD_MAX)
    assert un_shed < ss.key_off_delay_s(84.0)
    assert 0.7 < un_shed < 0.9
    assert ss.key_off_delay_s(84.0, ss.Circuit(c_gs=0.0)) < 0.02


# --- key OFF: the criterion that is IN the verdict ---------------------------------
def test_the_key_off_line_is_in_the_verdict_and_clears_on_the_shed_load():
    # IO-16: the firmware releases every aux output on KEY_SENSE going
    # inactive, inside Q101's key-off hold, so the decay carries the SHED tap
    # and the FET clears its derated DC line with 2.6x in hand.
    hot = ss.key_off(84.0)
    assert hot.i_load_a == pytest.approx(ss.I_LOAD_SHED)
    assert hot.p_max_w == pytest.approx(ss.I_LOAD_SHED * 84.0)
    assert hot.soa_limit_w == pytest.approx(ss.SOA_DC_84V_TC70 * ss.SOA_DERATE)
    assert hot.ok and hot.sim_ok
    assert hot.soa_limit_w / hot.p_max_w > 2.5
    assert [f for f in ss.assess() if f.startswith("key off")] == []
    assert ss.main([], ss.SPEC) == 0


def test_the_shed_load_is_the_base_plus_the_buck_and_never_the_base_alone():
    """⛔ The omission this test exists to stop, because it passes silently.

    U305's EN is tied to its own PVIN, so the 5 V aux rail is live whenever
    the 12 V rail is: firmware cannot release it, and it stays inside the
    figure Q101's SOA margin now rests on. What the firmware DOES take off is
    the aux channels, and exactly them.
    """
    from tools import power_budget as pb
    r = pb.budget()
    assert ss.I_LOAD_SHED == pytest.approx(r.shed_tap_a)
    assert ss.I_LOAD_SHED == pytest.approx(ss.shed_tap_current_a())
    assert ss.P_LOAD_SHED == pytest.approx(ss.I_LOAD_SHED * ss.V_LVC)
    assert r.shed_load_12v_a == pytest.approx(pb.BASE_12V_A + r.buck_standing_a)
    assert r.shed_load_12v_a > pb.BASE_12V_A
    assert r.load_12v_a - r.shed_load_12v_a == pytest.approx(r.aux12_a + r.aux5_a)
    # the whole tap, both converters, at the LVC -- the Cincon is not shed either
    assert ss.I_LOAD_SHED == pytest.approx(
        r.shed_conv_in_a + pb.LOGIC_IN_W / pb.LVC_V)
    assert ss.I_LOAD_SHED == pytest.approx(0.63, abs=0.005)
    assert ss.I_LOAD_SHED < ss.I_LOAD_MAX / 3


def test_the_key_off_gate_still_bites_at_a_heavier_shed_load():
    """⛔ A criterion that can no longer say no is not a criterion.

    138 W / 84 V = 1.64 A. A shed tap above that puts the bound back over the
    derated DC line, wherever the extra current came from.
    """
    assert ss.SOA_DC_84V_TC70 * ss.SOA_DERATE / 84.0 == pytest.approx(
        1.637, abs=0.002)
    assert ss.key_off(84.0, i_load_a=1.60).ok
    assert not ss.key_off(84.0, i_load_a=1.70).ok


def test_a_heavier_base_12_v_load_fails_the_key_off_gate(monkeypatch, capsys):
    """The same mutation end to end, through the number's own home.

    Nothing about the aux block changes and the firmware still sheds all
    eight channels: the BASE 12 V load alone goes to 7.6 A, which lands the
    shed tap at ~1.74 A -- over the 1.64 A the line allows. The gate fires,
    names the shed case, and the tool exits 1.
    """
    from tools import power_budget as pb
    monkeypatch.setattr(pb, "BASE_12V_A", 7.6)
    heavier = ss.shed_tap_current_a()
    assert heavier > 1.64
    monkeypatch.setattr(ss, "I_LOAD_SHED", heavier)
    monkeypatch.setattr(ss, "P_LOAD_SHED", heavier * ss.V_LVC)
    assert not ss.key_off(84.0).ok
    fails = [f for f in ss.assess() if f.startswith("key off, 84 V")]
    assert fails and "SHED" in fails[0]
    # and nothing else broke: KEY ON still follows the un-shed tap
    assert [f for f in ss.assess() if not f.startswith("key off")] == []
    assert ss.main([], ss.SPEC) == 1
    assert "⛔ FAIL" in capsys.readouterr().out


def test_the_decay_is_not_a_short_pulse_so_the_dc_line_is_the_right_row():
    hot = ss.key_off(84.0)
    assert hot.pulse_s > 0.100                                  # past the last row
    assert hot.soa_at_pulse_w == pytest.approx(hot.soa_limit_w)
    # ⚠️ What makes it slow is the GATE's RC, not the 440 µF: the caps alone
    # would be emptied in ~58 ms at the shed load, while the gate bleeds with
    # R110 x (C107 + C105 + C_ISS) = 0.48 s. The pulse sits between the two.
    assert hot.pulse_s > 2 * (ss.C_LOAD * 84.0 / ss.I_LOAD_SHED)
    assert hot.pulse_s < 100e3 * (4.7e-6 + 68e-9 + ss.C_ISS)


def test_the_decay_integration_step_is_fine_enough():
    coarse, fine = ss.key_off_decay(84.0, dt=50e-6), ss.key_off_decay(84.0, dt=2e-6)
    assert coarse[0] == pytest.approx(fine[0], rel=1e-3)     # peak
    assert coarse[1] == pytest.approx(fine[1], rel=1e-3)     # energy


def test_the_60_v_corner_was_never_the_one_that_failed():
    # 84 V is the corner the shed load rescued; 60 V was under the line even
    # un-shed, so a check that only ever looked here would have said nothing.
    assert ss.key_off(60.0).ok and ss.key_off(60.0, i_load_a=ss.I_LOAD_MAX).ok
    assert not ss.key_off(84.0, i_load_a=ss.I_LOAD_MAX).ok
    assert [f for f in ss.assess() if f.startswith("key off")] == []


def test_the_key_off_figure_is_stated_as_a_bound_with_its_alternative(capsys):
    hot = ss.key_off(84.0)
    # The bound is the shed tap x V_pack; the constant-power case held to the
    # converters' stated 43 V input floor is lower, and the report says which
    # is which rather than quietly using the kinder one.
    assert hot.dropout_case_w < hot.p_max_w
    assert hot.dropout_case_w == pytest.approx(
        hot.i_load_a * ss.V_LVC * (84.0 / ss.V_CONVERTER_MIN - 1.0))
    ss.main([], ss.SPEC)
    out = capsys.readouterr().out
    assert "BOUND" in out and f"{ss.V_CONVERTER_MIN:.0f} V" in out


# --- key OFF: the residual risk the shed case does NOT erase -----------------------
def test_the_un_shed_case_is_still_over_the_line():
    """⚠️ RESIDUAL RISK, not a gate, and not deleted.

    Hold the outputs on through the decay and Q101 is back where it was:
    162 W against a 138 W line, 147 W and 21.3 J once the decay is integrated,
    over a pulse past the 100 ms row. Refining the bound into a simulation
    does not rescue it -- which is why the shed is the thing that had to
    change, not the arithmetic.
    """
    risk = ss.key_off(84.0, i_load_a=ss.I_LOAD_MAX)
    assert risk.p_max_w == pytest.approx(ss.I_LOAD_MAX * 84.0)
    assert risk.p_max_w > 160.0 and risk.soa_limit_w < 140.0
    assert not risk.ok
    assert risk.p_sim_w < risk.p_max_w      # so the bound is the stricter test
    assert not risk.sim_ok
    assert risk.energy_j > 15.0             # ~21 J, mostly after the hold
    assert risk.pulse_s > 0.100
    assert risk.p_max_w > 3 * ss.key_off(84.0).p_max_w


def test_the_report_keeps_the_un_shed_figure_beside_the_gate(capsys):
    """⛔ Do not delete the 162 W. Whoever reads the PASS has to see what the
    pass depends on, and how narrow the exposure actually is: a reset sheds
    the load by ITSELF (every driver enable comes out of reset pulled down),
    so what is left is a hang that holds the outputs on without tripping the
    watchdog, through the decay. Not a blanket "firmware might fail"."""
    assert ss.main([], ss.SPEC) == 0
    out = capsys.readouterr().out
    assert "RESIDUAL RISK" in out
    assert "162 W" in out and "138 W" in out and "53 W" in out
    assert "IO-16" in out and "KEY_SENSE" in out
    assert "RESET is NOT the exposure" in out and "HANG" in out


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


def test_the_real_netlists_gate_network_passes_every_criterion(capsys):
    try:
        from tools import netlist
        design = netlist.current()
    except Exception as exc:                  # the netlist is its own test's job
        pytest.skip(f"tools.netlist does not build a Design: {type(exc).__name__}: {exc}")
    c = ss.circuit_from(design)
    assert ss.assess(c) == []
    # The same design as the specified one, to within a 5 % resistor.
    assert ss.differences(c, ss.SPEC, rel=0.05) == []
    assert ss.main([]) == 0
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


# --- M18: the verdict TEXT agrees with the exit code, both ways -----------------------
def test_over_in_the_text_means_exit_1_and_exit_1_means_over_in_the_text(monkeypatch, capsys):
    """The 2026-09-20 defect: the key-off line printed `⛔ OVER` while the tool
    exited 0 with `✅ PASS`. `assess()` was fixed; this holds the TEXT to it.
    On the good circuit no line reads OVER and the exit is 0; with the shed
    tap pushed over the DC line the key-off lines read OVER and the exit is 1
    -- and the two agree because the same numbers feed both."""
    rc = ss.main([], ss.SPEC)
    out = capsys.readouterr().out
    assert ("⛔ OVER" in out) == (rc == 1) == False
    assert "✅ PASS" in out and "⛔ FAIL" not in out

    from tools import power_budget as pb
    monkeypatch.setattr(pb, "BASE_12V_A", 7.6)                # shed tap ~1.74 A
    heavier = ss.shed_tap_current_a()
    monkeypatch.setattr(ss, "I_LOAD_SHED", heavier)
    monkeypatch.setattr(ss, "P_LOAD_SHED", heavier * ss.V_LVC)
    rc = ss.main([], ss.SPEC)
    out = capsys.readouterr().out
    assert ("⛔ OVER" in out) == (rc == 1) == True
    assert "✅ PASS" not in out and "⛔ FAIL" in out
    over = [l for l in out.splitlines() if "⛔ OVER" in l]
    assert over and all("the derated DC line" in l or "allowed there" in l for l in over)
    assert any(f.startswith("key off, 84 V") for f in ss.assess())
