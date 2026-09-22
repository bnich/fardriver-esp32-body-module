"""IO-1 / IO-2: four 12 V and four 5 V aux outputs, 1 A each, on expander #3.

The 12 V four are a third TPS4H160B, identical in hardware to the lamp
channels; the 5 V four are a buck of their own and four current-limited load
switches.  ⚠️ Nothing here is a hardware function: every one of the eight is
OFF until firmware drives expander #3, and the expander's bits come out of
reset as inputs.
"""
import re

from tools import netlist, rules
from tools.eprj3.schematic import landed_pins
from tools.model import resistance

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


def test_expander_3_sits_where_its_lines_each_cross_one_pair():
    """⭐ ON LOGIC SINCE IO-26 2a, and the board is arithmetic. The four 5 V
    switches it enables went to CTRL with J314 and the three 12 V drivers it
    commands stayed on OUTPUTS, so wherever this part sits, something crosses:

      on LOGIC   eight 5 V lines cross CTRL-STACK, six 12 V commands cross
                 STACK -- ONE pair each, and the I²C bus and the RESET stay on
                 this board's own copper.
      on OUTPUTS the eight cross STACK *and* CTRL-STACK, which wants 2 × 32
                 contacts on a spine whose family stops at 2 × 30.
      on CTRL    the six cross both pairs, and V3P3 has to follow the part up.

    Protects: that the expander's board is the one where no line crosses
    twice, and that all three expanders share one bus on one board."""
    assert D.part("U304").board == "LOGIC"
    for bus, pin in (("SDA", "SDA"), ("SCL", "SCK")):
        assert _net("U304", pin) == bus
        assert D.net(bus).interface is None, "one board's copper"
        assert {r for r, _ in D.net(bus).pins if r.startswith("U")} == \
            {"U401", "U402", "U403", "U304"}
        assert {D.board_of(r) for r, _ in D.net(bus).pins} == {"LOGIC"}
    assert _net("U304", "RESET") == "EN"
    assert D.net("EN").interface is None
    # Every line this part drives or reads crosses exactly one pair.
    for n in range(1, 5):
        for kind, iface in (("EN", "CTRL-STACK"), ("FAULT", "CTRL-STACK")):
            assert D.net(f"AUX5V_{n}_{kind}").interface == iface
        assert D.net(f"AUX12_{n}_CMD").interface == "STACK"
    for name in ("DIAG3_CMD", "AUX12_CMD"):
        assert D.net(name).interface == "STACK"


#: TI SLVSCV8E eq. 10 (p.29): R_CL = V_CL(th) × K_CL / I_OUT, with 0.8 V and
#: 2500; §6.5 (p.8) gives dK(CL)/K(CL) = ±15 % for a limit of 0.5-7 A (±20 %
#: below 0.5 A, which no aux channel is set to). The resistor is 1 %.
TPS_CL_V, TPS_CL_K, TPS_CL_TOL = 0.8, 2500.0, 0.15
#: IO-2: every aux output delivers 1 A. Spec §8.6 puts the floor at 1.06 A --
#: the limit must not bite the load at any corner -- and the lamp channels'
#: own 2 A is the ceiling a 1 A wire should not be asked to carry.
AUX_LOAD_A, CL_FLOOR_A, CL_CEILING_A = 1.0, 1.06, 2.0


def test_the_third_tps4h160b_shares_cs2_and_fault2_through_its_own_diag_en():
    assert _net("U303", "CS") == _net("U302", "CS") == "CS2_RAW"
    assert _net("U303", "FAULT") == _net("U302", "FAULT") == "FAULT2_DEV"
    assert _net("U303", "DIAG_EN") != _net("U302", "DIAG_EN")


def _limit_band(d):
    """(min, max) current U303 limits at, from the resistor actually fitted."""
    cl = [r for r, _ in d.net("CL3").pins if r.startswith("R")]
    assert len(cl) == 1, cl
    nominal = TPS_CL_V * TPS_CL_K / resistance(d.part(cl[0]).value)
    return nominal * (1 - TPS_CL_TOL), nominal * (1 + TPS_CL_TOL)


def test_the_12_v_aux_limit_clears_the_load_at_every_corner():
    """⚠️ The BAND, not the value: what matters about R359 is that a 1 A load
    never trips the limit and a fault still trips it well under the lamp
    channels' 2 A. 1.5 kΩ (JLC Basic) gives 1.12-1.55 A; the 1.6 kΩ first
    asked for gives 1.06-1.44 A and also clears -- either is a pass, which is
    what a band is for."""
    low, high = _limit_band(D)
    assert low > AUX_LOAD_A and low >= CL_FLOOR_A, (
        f"limits from {low:.2f} A: a {AUX_LOAD_A:g} A load trips it")
    assert high <= CL_CEILING_A, f"limits up to {high:.2f} A on a 1 A wire"


def test_the_neighbouring_basic_value_would_bite_the_load():
    """2.0 kΩ is the next JLC Basic value up and limits at 0.85 A worst case:
    the aux output would fold back under its own rated load. That is the
    defect the band exists to catch, and it is why 1.5 kΩ was chosen over the
    Basic part one step away."""
    low, _ = _limit_band(D.replace_part("R359", value="2k0 1%"))
    assert low < AUX_LOAD_A


def test_every_aux_output_reaches_its_terminal_with_a_clamp():
    for n in range(1, 5):
        v12 = {r for r, _ in D.net(f"AUX12V_{n}").pins}
        assert "J313" in v12 and any(D.part(r).mpn == "SMF18A"
                                     for r in v12 if r.startswith("D"))
        v5 = {r for r, _ in D.net(f"AUX5V_{n}").pins}
        assert "J314" in v5 and any(D.part(r).kind == "TVS"
                                    for r in v5 if r.startswith("D"))
    # ⛔ A clamp is on the board its terminal is on, never "on OUTPUTS" --
    # PROT reads the board, and J314 moved to CTRL's top face with the whole
    # 5 V block (IO-26 2a). The pitch is tests/test_rows.py's fact and is not
    # restated here.
    assert (D.connector("J314").board, D.connector("J314").side) == ("CTRL", "top")
    assert all(D.part(f"D{330 + n}").board == D.connector("J314").board
               for n in range(1, 5))
    # ...and the whole switched side of each channel is on that board too,
    # while the flag's pull-up is on LOGIC at the bit that reads it.
    for n in range(1, 5):
        for ref in (f"U{305 + n}", f"R{364 + n}", f"R{372 + n}", f"C{325 + n}"):
            assert D.part(ref).board == "CTRL", ref
        assert D.part(f"R{368 + n}").board == "LOGIC"


def test_the_12_v_terminal_shares_returns_so_it_can_be_seven_way():
    """⚠️ SEVEN contacts, because 3.81 × 8 is what the two general-input
    terminals are and a plug must not cross rows (tests/test_rows.py).  Each
    ground contact carries at most two outputs: 2 A against the family's 8 A.
    """
    nets = [cp.net for cp in D.connector("J313").pins]
    assert nets == ["AUX12V_1", "GND", "AUX12V_2", "GND", "AUX12V_3", "GND",
                    "AUX12V_4"]
    assert nets.count("GND") == 3 and len(nets) - nets.count("GND") == 4


#: TI SNVSAH5A Table 3 (p.27), 5 V out at 500 kHz: 88 µF of output
#: capacitance -- and its footnote, "All the COUT values are after derating.
#: Add more when using ceramics".
TI_COUT_UF = 88.0
#: What a 25 V X5R 1206 is ASSUMED to keep at a 5 V DC bias once its ±10 %
#: tolerance and ageing are counted: half of its marked value.
#: ⬜ A CLASS figure, not this part's measured curve -- Samsung publishes no
#: DC-bias data in the catalogue on file -- and deliberately pessimistic, so
#: the count stands even if the real curve is worse than typical. If a measured
#: curve ever lands, change this number and let the test re-derive the count:
#: nominal × this must clear TI_COUT_UF. Today eight 22 µF parts, the 470 nF
#: and the four switches' own 100 nF are 176.87 µF nominal = 88.4 µF derated,
#: a hair over. TI's own example of four parts scores 44.4 µF and seven parts
#: 77.4 µF: both fail here, which is the point.
DC_BIAS_KEEP = 0.5


def _microfarads(value):
    m = re.match(r"([\d.]+)\s*([munp])F", value)
    assert m, f"no capacitance in {value!r}"
    return float(m.group(1)) * {"m": 1e3, "u": 1.0, "n": 1e-3, "p": 1e-6}[m.group(2)]


def _v5aux_bulk_uf(d):
    """Every fitted capacitor from V5AUX to ground, in µF nominal."""
    total = 0.0
    for ref, pin in d.net("V5AUX").pins:
        if not ref.startswith("C") or d.part(ref).dnp:
            continue
        far = d.net_of(ref, "2" if pin == "1" else "1")
        if far is not None and far.name == "GND":
            total += _microfarads(d.part(ref).value)
    return total


def test_the_5_v_bulk_meets_tis_table_after_dc_bias_derating():
    """⚠️ The count of output capacitors is the most judgement-heavy number in
    this block, and TI's TABLE and TI's EXAMPLE disagree: the table asks 88 µF
    AFTER derating, the example fits four 22 µF parts, which is 88 µF NOMINAL
    and about half that in circuit. Nothing else here would notice the example
    being copied, so this test holds the count to the table."""
    nominal = _v5aux_bulk_uf(D)
    assert nominal * DC_BIAS_KEEP >= TI_COUT_UF, (
        f"{nominal:.1f} µF nominal = {nominal * DC_BIAS_KEEP:.1f} µF derated, "
        f"against TI's {TI_COUT_UF:g} µF after derating")


def test_tis_own_four_capacitor_example_does_not_meet_its_own_table():
    """The defect this exists for: the example copied instead of the table."""
    bad = D
    for ref in ("C322", "C323", "C324", "C325"):
        bad = bad.without_part(ref)
    assert _v5aux_bulk_uf(bad) * DC_BIAS_KEEP < TI_COUT_UF


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
    assert rules.d14_gate_bias(D) == []
