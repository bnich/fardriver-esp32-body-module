"""The checks review's mutations (2026-09-19), each an electrically wrong change
to the REAL netlist that once passed every gate.  Each must now be caught by
the rule named, and the real design must stay clean (test_design_clean.py).
"""
from dataclasses import replace

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


def test_m36_a_resistor_from_the_horn_gate_to_the_12_v_rail():
    bad = add(D, _r("R399", "OUTPUTS", "1k"), {"1": "HORN_GATE", "2": "V12"})
    assert any("HORN" in e for e in fired(bad, "LV-LOGIC")), "IO42 sees ~11 V"


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
def test_m27_a_100_ohm_open_load_pull_up_burns_an_0805():
    """R345 hangs the stop lamp's output on V12: 12 V across 100 Ω is 1.44 W."""
    assert any("R345" in e for e in fired(D.replace_part("R345", value="100R"), "VR-POWER"))


def test_h18_the_1k_lamp_series_resistor_in_an_0805_is_over_by_15_percent():
    """The near-threshold case: R426 (1 kΩ across 12 V, 144 mW) is a 1206 at
    58 % of 250 mW. In an 0805 it is 144 mW on 125 mW -- 1.15×, the region the
    design lives in (R401 73 %, R426-R429 58 %). A rule that let the threshold
    drift to 2× let this ship (H18)."""
    errs = fired(D.replace_part("R426", package="0805"), "VR-POWER")
    assert errs == ["VR-POWER: R426 (1k, 0805) can see 12 V and dissipate 0.144 W; "
                    "its package is rated 0.125 W."]
    assert fired(D, "VR-POWER") == []


def test_h19_a_flattering_clamp_typed_on_a_real_tvs_is_caught():
    """SMS05T1G 9.8 → 4.0 and SMCJ90A 146 → 50 passed 1479 tests (H19)."""
    for ref, clamp, real in (("D404", 4.0, "9.8 V"), ("D101", 50.0, "146 V")):
        errs = fired(D.replace_part(ref, v_clamp=clamp), "VR-DATASHEET")
        assert any(ref in e and f"v_clamp={clamp:g} V" in e and real in e for e in errs), errs
    assert fired(D, "VR-DATASHEET") == []


# ── CK-11: a gate divider that cannot switch its FET (review 2026-09-19) ─────
def test_m37_a_series_resistor_that_leaves_the_motor_cut_ungateable():
    """The defect the review found: R114 = 100k puts 3.3 V × 10k / 110k = 0.30 V
    on Q106's gate. BL_CMD is wired, biased OFF, commanded by the right pin and
    unswitchable — integrity, D14, TURN-ON, every VR rule and 1233 tests pass."""
    bad = D.replace_part("R114", value="100k")
    errs = fired(bad, "GATE-VGS")
    assert any("Q106" in e and "0.3 V" in e for e in errs), errs


def test_m37b_a_bias_resistor_that_swallows_the_gate_drive():
    """The same divider from the other end: a 100 Ω bias against R114's 100 Ω
    halves the drive to 1.65 V. Guarding one resistor would not have caught it."""
    assert any("Q106" in e for e in fired(D.replace_part("R115", value="100R"),
                                         "GATE-VGS"))


def test_m37c_a_fet_with_no_stated_vgs_is_refused_not_skipped():
    """A logic-driven gate whose part has no figure in DATASHEET_VGS_SPEC is an
    UNCHECKED divider, so the rule says so rather than passing it."""
    bad = D.replace_part("Q106", mpn="SI2302")
    assert any("Q106" in e and "DATASHEET_VGS_SPEC" in e
               for e in fired(bad, "GATE-VGS"))


def test_m37d_a_p_fet_whose_source_gives_it_no_swing_is_refused():
    """The polarity term: a P-FET rests at its source and is driven DOWN, so a
    source at ground potential leaves no swing at all to turn it on with."""
    bad = D.replace_part("Q106", kind="PFET")
    assert any("Q106" in e and "0 V swing" in e for e in fired(bad, "GATE-VGS"))


def test_m37e_a_zero_ohm_gate_bias_holds_v_gs_at_zero_for_ever():
    """0 Ω is a VALUE here, not 'absent'. A link or NET-TIE from gate to source
    passes D14 (a resistor is there) and TURN-ON (a pin does reach the gate)."""
    assert any("Q106" in e for e in fired(D.replace_part("R115", value="0R"),
                                         "GATE-VGS"))


def test_m37f_a_high_side_n_fet_a_logic_pin_cannot_lift_is_refused():
    """Q106 moved to the high side: its gate would have to go above 12 V, and a
    3.3 V pin cannot. The rule refuses the case instead of computing a swing of
    12 - 3.3 V that no copper ever sees."""
    bad = move(move(D, "Q106", "S", "V12"), "R115", "2", "V12")
    errs = fired(bad, "GATE-VGS")
    assert any("Q106" in e and "HIGH-SIDE" in e for e in errs), errs


# ── CK-10: a switch to ground needs a pull-UP ────────────────────────────────
def test_m17_a_pull_down_where_the_boost_button_needs_a_pull_up():
    assert any("IN07" in e for e in fired(move(D, "R409", "2", "GND"), "PULL-DIR"))


def test_m33_a_gate_tied_to_its_own_source():
    assert any("Q301" in e for e in fired(move(D, "Q301", "G", D.net_of("Q301", "S").name),
                                          "TURN-ON"))


# ── review 2026-09-20: the aux block's two new holes ─────────────────────────
def test_m38_a_ground_pin_landed_on_the_rail_the_part_makes():
    """U305's PGND on V5AUX passed integrity, every test and every other rule:
    the buck referenced to its own output. Splitting AGND, PGND and the DAP is
    the point of this part's layout, and nothing but GND-PIN says where they
    go."""
    bad = move(D, "U305", "PGND", "V5AUX")
    assert any("U305.PGND" in e for e in fired(bad, "GND-PIN"))


def test_m38b_an_ic_with_no_ground_pins_entry_is_reported_not_assumed_fine():
    """As SUPPLY does: a part nobody has typed a return for is a part nobody
    has checked."""
    bad = D.replace_part("U306", mpn="SY6280AAC")
    assert any("U306" in e and "GROUND_PINS" in e for e in fired(bad, "GND-PIN"))


def test_m39_an_enable_named_shdn_is_an_enable():
    """D14 matched the one string "EN" until this review, so a part naming its
    enable anything else walked past the rule written for it."""
    part = Part("U310", "TPS26600PWPR", "HTSSOP-16", "OUTPUTS", "IC",
                ("IN", "OUT", "GND", "SHDN"), 1.2, v_max=60.0)
    bad = add(D, part, {"IN": "V5AUX", "OUT": ("AUX5V_9", "5V"),
                        "GND": "GND", "SHDN": ("AUX5V_9_EN", "3V3")})
    assert any("U310" in e and "SHDN" in e for e in fired(bad, "D14"))


# ── H4: D14 solves the RESTING voltage, not the existence of a pull-down ─────
def test_h4_a_pull_up_beside_the_horn_gates_pull_down_rests_it_on():
    """1 kΩ HORN_GATE → V3P3 beside R307's 10 kΩ: the gate rests at 3.0 V, Q301
    hard ON, the horn sounding whenever AUX12 is live. 0 violations before."""
    bad = add(D, _r("R901", "OUTPUTS", "1k"), {"1": "HORN_GATE", "2": "V3P3"})
    errs = fired(bad, "D14")
    assert len(errs) == 1 and "Q301" in errs[0] and "rests at 3 V" in errs[0]
    assert "V_GS(th) minimum 0.65 V" in errs[0] and "aos_ao3400a" in errs[0]


def test_h4_a_pull_up_beside_a_load_switch_enable_rests_it_on():
    """1 kΩ AUX5V_1_EN → V3P3 beside R365's 100 kΩ: 5 V aux 1 ON from power-up,
    with no firmware, and un-sheddable through Q101's decay (IO-16)."""
    bad = add(D, _r("R902", "OUTPUTS", "1k"), {"1": "AUX5V_1_EN", "2": "V3P3"})
    errs = fired(bad, "D14")
    assert len(errs) == 1 and "U306" in errs[0] and "rests at 3.267 V" in errs[0]
    assert "V_IL 0.66 V" in errs[0] and "IO-16" in errs[0]


def test_h4_a_499k_from_the_84_v_gate_to_ground_rests_the_p_fet_on():
    """499 kΩ D13_GATE → GND against R110's 100 kΩ to B+: the gate rests 14 V
    below its source with the key OFF -- Q101 hard ON, silently."""
    bad = add(D, _r("R903", "POWER", "499k", "1206"), {"1": "D13_GATE", "2": "GND"})
    errs = fired(bad, "D14")
    assert len(errs) == 1 and "Q101" in errs[0] and "V_GS -14.023 V" in errs[0]
    assert "V_GS(th) minimum 2 V" in errs[0]


def test_m09_a_load_switch_enable_tied_to_a_rail_is_a_channel_nobody_controls():
    """U306.EN on V5: permanently ON, breaking IO-16. A regulator's enable on
    a rail (U305 on V12, U405 on V5) is the always-on connection its datasheet
    gives, and passes."""
    errs = fired(move(D, "U306", "EN", "V5"), "D14")
    assert len(errs) == 1 and "U306" in errs[0] and "tied to the rail 'V5'" in errs[0]
    assert "ALWAYS_ON_ENABLE" in errs[0]
    for ref in ("U305", "U405"):
        assert D.part(ref).mpn[:6] in "".join(rules.ALWAYS_ON_ENABLE), ref


def test_h4_the_real_gates_and_enables_rest_at_their_off_level():
    """The control, stated as figures: every N-FET gate and every enable at
    0 V; Q101's gate at its source's 84 V (V_GS 0); KSW -- a wire, a command --
    is open at rest, so Q105's gate is not held up by it."""
    ix = rules._index(D)
    for q in ix.fets():
        g, s = ix.nets_of_pin(q.refdes, "G")[0], ix.nets_of_pin(q.refdes, "S")[0]
        vg, _ = rules._resting(ix, g, reference=s)
        vs, _ = rules._resting(ix, s, reference=s)
        assert vg == vs == (84.0 if q.refdes == "Q101" else 0.0), (q.refdes, vg, vs)
    assert rules._resting(ix, "D13_EN", reference="GND") == (0.0, [])
    assert ix.divided("D13_EN")[0] > 7        # the key-ON figure the solver knows
    for ref in ("U306", "U307", "U308", "U309", "U301", "U302", "U303"):
        for pin in ("EN", "DIAG_EN"):
            for net in ix.nets_of_pin(ref, pin):
                assert rules._resting(ix, net)[0] == 0.0, (ref, pin)
    assert fired(D, "D14") == []


def test_h4_an_unlisted_fet_resting_off_its_source_is_refused_not_guessed():
    bad = add(D, _r("R901", "OUTPUTS", "1k"), {"1": "HORN_GATE", "2": "V3P3"})
    bad = bad.replace_part("Q301", mpn="SI2302")
    errs = fired(bad, "D14")
    assert any("Q301" in e and "DATASHEET_VGS_TH_MIN has no line" in e for e in errs)


def test_h4_a_gate_resting_under_its_threshold_is_off():
    """Near the line, the right way round: 100 kΩ HORN_GATE → V3P3 against
    the 10 kΩ pull-down rests the gate at 0.30 V, under the AO3400A's 0.65."""
    ok = add(D, _r("R901", "OUTPUTS", "100k"), {"1": "HORN_GATE", "2": "V3P3"})
    assert fired(ok, "D14") == []
    on = add(D, _r("R901", "OUTPUTS", "27k"), {"1": "HORN_GATE", "2": "V3P3"})
    assert any("Q301" in e and "rests at 0.892 V" in e for e in fired(on, "D14"))


def test_m39c_an_enable_named_ce_or_on_is_an_enable():
    """M9: `CE` and `ON` are the other names a load switch's enable goes by;
    each floating (no resistor to GND) is the same D14 failure as `EN`."""
    for pin in ("CE", "ON", "PWR_ON"):
        part = Part("U310", "TPS22918", "SOT-23-6", "OUTPUTS", "IC",
                    ("VIN", "VOUT", "GND", pin), 1.2, v_max=6.5)
        bad = add(D, part, {"VIN": "V5AUX", "VOUT": ("AUX5V_9", "5V"), "GND": "GND",
                            pin: ("AUX5V_9_EN", "3V3")})
        errs = fired(bad, "D14")
        assert any("U310" in e and f" {pin} on 'AUX5V_9_EN'" in e for e in errs), (pin, errs)


def test_m39b_the_internal_pulldown_table_is_what_keeps_diag_en_quiet(monkeypatch):
    """DIAG_EN matches the enable family and has no resistor to ground: what
    makes that correct is TI's own pulldown, typed in INTERNAL_PULLDOWN. Empty
    the table and the rule fires -- so the design's silence is the datasheet's
    doing, not the regex's."""
    assert fired(D, "D14") == []
    monkeypatch.setattr(rules, "INTERNAL_PULLDOWN", {})
    assert any("DIAG_EN" in e for e in fired(D, "D14"))


# ── BUS-ORDER on the real crossings: order for a pair, keying for a cable ────
def _rebus(d, iface, nets):
    """Both halves of an interface re-tabled onto `nets`, contact for contact."""
    for c in list(d.connectors):
        if c.interface == iface:
            d = d.replace_connector(c.refdes, pins=tuple(
                replace(cp, net=n) for cp, n in zip(c.pins, nets)))
    return d


def test_m40_the_rigid_power_bus_passes_because_it_is_a_palindrome():
    """⚠️ Not by luck, and not because BUS-ORDER looked away. PWR-LOGIC carries
    the 3.3 V rail back DOWN to OUTPUTS, on two contacts placed symmetrically;
    swap the V3P3 at contact 3 with the ground beside it and the tuple stops
    reading the same from both ends, so a half mated reversed — or mirrored by
    hanging under LOGIC, which this one is — lands the 3.3 V rail on a ground.
    The rule says so."""
    nets = [cp.net for cp in D.connector("J307").pins]
    assert len(nets) == 9 and nets == nets[::-1]
    assert fired(D, "BUS-ORDER") == []
    nets[2], nets[3] = nets[3], nets[2]
    errs = fired(_rebus(D, "PWR-LOGIC", nets), "BUS-ORDER")
    assert any("both ends" in e and "V3P3 is a supply rail" in e
               and "SHORTS it to GND" in e for e in errs), errs


def test_m40b_the_real_cable_passes_because_both_ends_are_keyed():
    """⭐ The other half of the same rule, on the real design. PWR-OUT's four
    conductors cannot be ordered so that a reversed mate is harmless — reversed,
    V12 meets KEY_SENSE whatever order they sit in — so what protects it is the
    connector: JST's locking wafer takes its housing one way round only. Take
    that claim off J202 and BUS-ORDER fires, naming the end that lost it.

    ⛔ This is the test that stops anyone 'simplifying' the rule into an
    exemption for cables. An exemption passes this mutation."""
    for ref in ("J202", "J311", "J105", "J312"):
        assert D.connector(ref).keyed, ref
    assert fired(D, "BUS-ORDER") == []
    errs = fired(D.replace_connector("J202", keyed=""), "BUS-ORDER")
    assert len(errs) == 1 and "J202" in errs[0], errs
    assert "CABLE and names no keying" in errs[0]


def test_the_real_design_passes_every_new_rule():
    for rule_id in ("VR-CLAMP", "VR-POWER", "PULL-DIR", "GATE-VGS", "GND-PIN",
                    "D14"):
        assert fired(D, rule_id) == [], rule_id
