"""IO-10: all eight aux outputs at 1 A on at once must stay inside the 12 V
converter's input choke and the module's tap fuse at the 60 V LVC (plan
§3.2.3 / §3.2.6: size at the LVC, never at full charge).

⚠️ The mutations below are the point of the file.  A budget that only ever
prints a number agrees with itself; these fail it with a 2 A choke, a 2 A tap
fuse, a converter asked for more than it makes, a rating nobody can read off
the part, and a converter that is not there at all -- the ways the input path
can be under-sized or unmeasurable.
"""
from dataclasses import replace

import pytest

from tools import netlist, power_budget as pb
from tools.model import Net, Part

D = netlist.current()


# --- the design ------------------------------------------------------------------------
def test_the_real_design_fits():
    r = pb.budget(D)
    assert 8.3 < r.load_12v_a < 8.7          # 2.62 + 4 × 1.0 + 20 W / 0.9 / 12 V = 8.47
    assert r.problems == []


def test_the_numbers_are_the_ones_the_spec_states():
    """Design spec §8's table, to two decimals: 8.47 A at 12 V and 1.88 A into
    the converter at the LVC.  ⚠️ The spec prints 1.89 A, and the TOOL is
    right: 8.4721 A × 12 V / 0.9 / 60 V = 1.8827 A.  The spec reached 1.89 by
    rounding the 101.6 W of 12 V load up to 102 W first.  Fix the spec, not
    these figures.

    If the netlist grows a channel these move, and everything below is then
    out of date -- the spec's §8 table, and the copies typed into
    tools/netlist.py at L101's `source` (1.88 A), PWR-OUT's comment, V12's
    `source` and `_HAND_BY_MPN` (8.47 A), each of which cites
    tools/power_budget.py as this number's home."""
    r = pb.budget(D)
    assert r.aux12_a == pytest.approx(4.00, abs=0.005)
    assert r.aux5_a == pytest.approx(1.85, abs=0.005)
    assert r.load_12v_a == pytest.approx(8.47, abs=0.005)
    assert r.conv_in_a == pytest.approx(1.88, abs=0.005)
    assert r.tap_a == pytest.approx(1.93, abs=0.005)


def test_the_aux_load_is_counted_from_the_netlist_not_typed():
    """Add a ninth aux channel and the budget grows by exactly one channel.
    The counts are derived; nothing in the tool says 'four'."""
    more = D.with_net(Net("AUX12V_5", (), domain="12V",
                          source="fixture: a fifth 12 V aux channel")) \
            .with_net(Net("AUX5V_5", (), domain="5V",
                          source="fixture: a fifth 5 V aux channel"))
    grew = pb.AUX_OUTPUT_A + pb.AUX_OUTPUT_A * pb.V5 / pb.BUCK_EFF / pb.V12
    assert pb.budget(more).load_12v_a == pytest.approx(
        pb.budget(D).load_12v_a + grew)


def test_the_tenth_aux_channel_is_counted_too():
    """⛔ THE REGEX TRAP.  `AUX12V_\\d` matches AUX12V_1 … AUX12V_9 and NOT
    AUX12V_10, so a tenth channel of each kind vanished from the derived sum
    and the tool under-stated the load by 1.46 A -- silently, in the one check
    whose whole purpose is to be derived rather than typed.  The test above
    could not see it: it only ever adds a fifth.

    Ten 12 V and ten 5 V channels, by hand:
        base                                                       2.6200 A
        12 V aux   10 × 1.0 A                                     10.0000 A
        5 V aux    10 × 1.0 A × 5 V / 0.9 / 12 V                    4.6296 A
        buck standing                                              0.0003 A
                                                                  ---------
                                                                  17.2499 A
    With the `\\d` regex this came out at 9 channels each = 15.7869 A."""
    more = D
    for n in range(5, 11):
        more = more.with_net(Net(f"AUX12V_{n}", (), domain="12V",
                                 source=f"fixture: 12 V aux channel {n}")) \
                   .with_net(Net(f"AUX5V_{n}", (), domain="5V",
                                 source=f"fixture: 5 V aux channel {n}"))
    r = pb.budget(more)
    assert r.aux12_a == pytest.approx(10.0, abs=0.005)
    assert r.aux5_a == pytest.approx(4.6296, abs=0.005)
    assert r.load_12v_a == pytest.approx(17.25, abs=0.005)


# --- the 5 V buck is on the budget whether or not a channel is switched on ---------------
def test_the_buck_enable_is_still_tied_to_its_input():
    """The standing term below is only honest while this holds: U305's EN on
    the same net as its PVIN (SNVSAH5A p.4, 'Can be tied to PVIN') means the
    5 V aux rail is live whenever the 12 V rail is -- firmware or not, every
    channel disabled, the expander in reset.  Put EN on an expander bit and
    the buck stops being a permanent load, and this test says so."""
    assert D.net_of("U305", "EN").name == D.net_of("U305", "PVIN").name == "V12"


def test_the_five_volt_buck_itself_sits_on_the_12_v_budget():
    r = pb.budget(D)
    switched = (pb.BASE_12V_A + 4 * pb.AUX_OUTPUT_A
                + 4 * pb.AUX_OUTPUT_A * pb.V5 / pb.BUCK_EFF / pb.V12)
    assert r.buck_standing_a > 0
    assert r.load_12v_a == pytest.approx(switched + r.buck_standing_a)


# --- the SHED case: what is left when the firmware releases the outputs -----------------
def test_the_shed_case_is_the_load_minus_exactly_the_aux_channels():
    """IO-16: at key-off the firmware releases all eight aux channels, and
    `tools/soft_start.py` holds Q101's key-off SOA to what is left.  It is
    this sum minus `aux12_a` and `aux5_a` -- so it follows the base by
    construction and nobody retypes 2.62."""
    r = pb.budget(D)
    assert r.load_12v_a - r.shed_load_12v_a == pytest.approx(r.aux12_a + r.aux5_a)
    assert r.shed_conv_in_a == pytest.approx(r.shed_load_12v_a * pb.V12
                                             / pb.CONV_EFF / pb.LVC_V)
    assert r.shed_tap_a == pytest.approx(r.shed_conv_in_a
                                         + pb.LOGIC_IN_W / pb.LVC_V)
    assert r.shed_tap_a == pytest.approx(0.632, abs=0.002)


def test_the_shed_case_keeps_the_buck_the_firmware_cannot_release():
    """⛔ THE OMISSION THAT WOULD PASS SILENTLY.  U305's EN is tied to its own
    PVIN, so the 5 V aux rail is live whenever the 12 V rail is: no firmware
    releases it, and dropping it here would understate the load a PART's SOA
    margin now rests on -- in the direction that passes."""
    r = pb.budget(D)
    assert r.shed_load_12v_a == pytest.approx(pb.BASE_12V_A + r.buck_standing_a)
    assert r.shed_load_12v_a > pb.BASE_12V_A


def test_the_shed_case_follows_the_base_and_not_the_aux_block(monkeypatch):
    """Two mutations, opposite ways round.  A ninth aux channel moves the
    nominal load and NOT the shed one -- it is shed.  A heavier base moves
    both."""
    more = D.with_net(Net("AUX12V_5", (), domain="12V",
                          source="fixture: a fifth 12 V aux channel"))
    assert pb.budget(more).load_12v_a > pb.budget(D).load_12v_a
    assert pb.budget(more).shed_tap_a == pytest.approx(pb.budget(D).shed_tap_a)
    monkeypatch.setattr(pb, "BASE_12V_A", pb.BASE_12V_A + 1.0)
    assert pb.budget(D).shed_tap_a == pytest.approx(
        pb.budget(D).shed_conv_in_a + pb.LOGIC_IN_W / pb.LVC_V)
    assert pb.budget(D).shed_load_12v_a > 3.6


# --- the mutations ----------------------------------------------------------------------
def test_a_2_a_choke_fails():
    bad = D.replace_part("L101", value="10 mH · 2 A @ 70 °C · 300 V AC")
    assert any("L101" in p for p in pb.budget(bad).problems)


def test_a_2_a_tap_fuse_fails(monkeypatch):
    monkeypatch.setattr(pb, "TAP_FUSE_A", 2.0)
    assert any("fuse" in p for p in pb.budget(D).problems)


def test_a_choke_whose_value_states_no_current_fails():
    """⛔ An unreadable rating is a FAILURE, never a skip: 'no number' is the
    one case where a check that shrugs passes an under-rated part."""
    mute = D.replace_part("L101", value="5 mH common-mode choke")
    assert any("L101" in p and "states no current rating" in p
               for p in pb.budget(mute).problems)


def test_a_converter_whose_value_states_no_current_fails():
    """The same branch on the other part, which had no test.  A brick with no
    readable rating is a brick this check cannot hold to anything."""
    mute = D.replace_part("U201", value="43-160 V → 12 V, isolated")
    assert any("U201" in p and "states no current rating" in p
               for p in pb.budget(mute).problems)


def test_a_design_with_no_converter_on_the_12_v_rail_fails():
    """Delete the brick and nothing makes the rail.  ⛔ It must SAY so: a tool
    that skipped the converter tests here would still print a load figure and
    a PASS, over a design with no source for the load at all."""
    gone = D.without_part("U201")
    problems = pb.budget(gone).problems
    assert any("no converter makes the 12 V rail" in p for p in problems)
    assert any("no common-mode choke" in p for p in problems)


def test_a_load_over_the_converters_own_rating_fails(monkeypatch):
    """3 A per channel: 2.62 + 12 + 5.56 = 20.2 A, where the brick makes
    12.5 A.  The choke and the fuse fire too -- the converter must also."""
    monkeypatch.setattr(pb, "AUX_OUTPUT_A", 3.0)
    problems = pb.budget(D).problems
    assert any("U201" in p and "12.5 A" in p for p in problems)


def test_the_converters_gate_is_a_named_constant_that_can_be_tightened():
    """CONV_DERATE is 1.00 because the 12.5 A is TDK's rating at TDK's own
    conditions, not because nothing was decided.  Tighten it and the real
    design fails -- which is what makes it a gate rather than a comment."""
    assert pb.CONV_DERATE == 1.00
    r = pb.budget(D)
    tight = r.load_12v_a / r.conv_rated_a * 0.99       # just under the load
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pb, "CONV_DERATE", tight)
        assert any("U201" in p and "where it makes" in p
                   for p in pb.budget(D).problems)


def test_the_choke_and_fuse_derates_are_pinned_by_value():
    """M3: set to 0.93 / 0.90 the real design still passed. CHOKE_DERATE is
    0.80 for the sealed box the 70 °C rating does not describe; FUSE_DERATE is
    0.75, Littelfuse's 25 °C continuous-duty convention -- each stated in its
    own comment, and each a gate the real design sits under with margin."""
    assert pb.CHOKE_DERATE == 0.80
    assert pb.FUSE_DERATE == 0.75
    r = pb.budget(D)
    assert r.conv_in_a < r.choke_rated_a * pb.CHOKE_DERATE
    assert r.tap_a < pb.TAP_FUSE_A * pb.FUSE_DERATE
    with pytest.MonkeyPatch.context() as mp:                # each is a gate:
        mp.setattr(pb, "CHOKE_DERATE", r.conv_in_a / r.choke_rated_a * 0.99)
        assert any("L101" in p and "of its 3 A rating" in p for p in pb.budget(D).problems)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(pb, "FUSE_DERATE", r.tap_a / pb.TAP_FUSE_A * 0.99)
        assert any("tap fuse" in p and "of its rating" in p for p in pb.budget(D).problems)


# --- M1: what bounds a sustained 12 V-side overload is the brick's OCP, not the fuse -----
def test_the_ocp_ceiling_is_derived_from_the_bricks_band():
    """TDK CN-B p.3: OCP 102-150 % of rating, constant current. At 12.5 A that
    is 12.75-18.75 A out; through CONV_EFF at the LVC, 2.83-4.17 A at the
    choke (94-139 % of 3 A) and 2.88-4.22 A on the tap (96-141 % of the fuse)."""
    lim = pb.limit_case(D)
    assert lim.problems == []
    assert lim.ocp_out_a == pytest.approx((12.75, 18.75))
    assert lim.ocp_conv_in_a == pytest.approx((2.833, 4.167), abs=0.001)
    assert lim.ocp_tap_a == pytest.approx((2.883, 4.217), abs=0.001)
    assert (pb.CONV_OCP_MIN, pb.CONV_OCP_MAX) == (1.02, 1.50)
    out = pb.report(D)
    assert "OCP CEILING 12.75-18.75 A at 12 V" in out
    assert "Choke 2.83-4.17 A = 94%-139% of its 3 A at 70 °C" in out
    assert "tap 2.88-4.22 A = 96%-141% of the fuse" in out


def test_the_fuse_never_opens_on_the_limited_case_and_the_report_says_so():
    """KLKD003 at 86 %: the agency table (littelfuse_klkd.pdf p.4) holds 100 %
    to temperature stabilisation and opens 135 % within 60 min. 'A fast-blow
    fuse opening on it is the fuse doing its job' was false (M1)."""
    lim = pb.limit_case(D)
    share = lim.tap_a / pb.TAP_FUSE_A
    assert 0.85 < share < 0.87
    assert pb.fuse_time_at(share).startswith("indefinitely")
    out = pb.report(D)
    assert "The fuse carries 86% indefinitely" in out
    assert "doing its job" not in out and "doing its job" not in pb.__doc__
    assert "short-circuit device for the 84 V side" in out


@pytest.mark.parametrize("share, starts", [
    (0.86, "indefinitely"), (1.00, "indefinitely"),
    (1.01, "for more than 60 min"), (1.13, "for more than 60 min"),
    (1.20, "for up to and beyond 60 min"), (1.34, "for up to and beyond 60 min"),
    (1.35, "for up to 60 min"), (1.41, "for up to 60 min"), (2.0, "for up to 60 min"),
])
def test_time_at_current_follows_the_agency_table(share, starts):
    assert pb.fuse_time_at(share).startswith(starts), share
    assert (pb.FUSE_HOLDS_PCT, pb.FUSE_HOLDS_60MIN_PCT, pb.FUSE_OPENS_60MIN_PCT) == (1.00, 1.13, 1.35)


def test_the_choke_is_graded_against_the_ocp_ceiling_with_a_time():
    out = pb.report(D)
    line = next(l for l in out.splitlines() if l.startswith("OCP CEILING"))
    assert "the choke sits at 94% until the brick's over-temperature protection" in line
    assert "the choke carries 139% for that long" in line and "opens within an hour at 135%" in line


def test_the_ocp_ceiling_moves_with_the_bricks_rating():
    """Derived, not typed: a 200 W brick (16.7 A) lifts the whole band."""
    d = D.replace_part("U201", value=D.part("U201").value.replace("12.5 A", "16.7 A"))
    assert "16.7 A" in d.part("U201").value
    lim = pb.limit_case(d)
    assert lim.ocp_out_a == pytest.approx((16.7 * 1.02, 16.7 * 1.50))


# --- the parts are found through the copper, not by refdes ------------------------------
def test_the_converter_and_its_choke_are_found_through_the_copper():
    r = pb.budget(D)
    assert (r.converter.refdes, r.choke.refdes) == ("U201", "L101")
    assert r.choke_rated_a == 3.0 and r.conv_rated_a == 12.5


def test_the_choke_named_is_the_one_on_the_12_v_brick_not_the_other():
    """L102 shares GND with L101 and with the brick, and HV_SW with L101.  A
    lookup that walked any shared net would pick whichever came first in the
    parts tuple; this one follows the 84 V nets of the brick that makes 12 V,
    which are HV_C1_P and HV_C1_N alone.

    ⚠️ BOTH halves are needed.  The value mutation alone passes against a
    naive shared-net lookup, because L101 is declared before L102 and next()
    takes the first -- it proves declaration order, not topology.  The
    reversed-parts fixture is what makes the order hostile."""
    swapped = D.replace_part("L102", value="10 mH · 0.5 A @ 70 °C · 300 V AC")
    assert pb.budget(swapped).problems == []
    rev = replace(D, parts=tuple(reversed(D.parts)))
    assert pb._input_choke(rev, pb._converter_12v(rev)).refdes == "L101"


def test_a_second_choke_in_the_input_path_is_a_defect_not_a_coin_toss():
    """Put L102 on the brick's own input nets and the two share the current in
    a ratio nobody has stated.  First-match would grade one and ignore it."""
    both = D.replace_part("L102", board="POWER")
    both = replace(both, nets=tuple(
        replace(n, pins=n.pins + (("L102", "2"),)) if n.name == "HV_C1_P"
        else replace(n, pins=n.pins + (("L102", "3"),)) if n.name == "HV_C1_N"
        else n for n in both.nets))
    assert any("2 common-mode chokes" in p for p in pb.budget(both).problems)


def test_a_second_converter_on_the_12_v_rail_is_a_defect():
    """Two bricks paralleled onto one rail share the load in a way this check
    does not model; it must say so rather than size one of them."""
    twin = D.with_part(replace(D.part("U201"), refdes="U299"))
    twin = replace(twin, nets=tuple(
        replace(n, pins=n.pins + (("U299", "+V"),)) if n.name == "V12" else n
        for n in twin.nets))
    assert any("2 converters" in p for p in pb.budget(twin).problems)


def test_a_design_with_no_choke_on_the_input_fails():
    assert any("no common-mode choke" in p
               for p in pb.budget(D.without_part("L101")).problems)


def test_the_five_volt_buck_is_not_mistaken_for_the_brick():
    """U305 is fed FROM V12 and switches on a 12 V-domain net (V5AUX_SW), so
    it is exactly the part a loose finder would grade as the source of the
    rail.  Its `kind` is what excludes it -- reclassify it and the check must
    not quietly start measuring the wrong part."""
    assert D.part("U305").kind == "IC"
    assert D.net_of("U305", "SW").domain == "12V"
    assert pb._converters_12v(D) == (D.part("U201"),)


# --- the limit case, derived from the copper --------------------------------------------
def test_the_limit_case_is_derived_from_the_programming_resistors():
    """11.4 A is the figure the module docstring warns about, and it now comes
    off the copper: R359 (1k5, U303's CL) and R373-6 (20k, the TPS2553 ILIM
    pins).  12 V channel: 0.8 V × 2500 / (1500 × 0.99) × 1.15 = 1.549 A.
    5 V channel: 22980 / 19.8^0.94 = 1388 mA."""
    lim = pb.limit_case(D)
    assert lim.problems == []
    assert (lim.n12, lim.n5) == (4, 4)
    assert lim.per_12v_a == pytest.approx(1.549, abs=0.002)
    assert lim.per_5v_a == pytest.approx(1.388, abs=0.002)
    assert lim.load_12v_a == pytest.approx(11.39, abs=0.01)
    assert lim.conv_in_a == pytest.approx(2.53, abs=0.01)
    assert lim.tap_a == pytest.approx(2.58, abs=0.01)


def test_changing_the_12_v_limiters_resistor_moves_the_limit_case():
    """⚠️ THE POINT OF DERIVING IT.  R359 sets what four 12 V channels can
    pass.  1k5 → 1k2 raises each channel by 1500/1200 = 1.25×, so the four
    together go from 6.20 A to 7.74 A and the LIMITED figure with them.  While
    this was prose in the docstring, that edit changed nothing and the
    paragraph went silently wrong."""
    before = pb.limit_case(D)
    after = pb.limit_case(D.replace_part("R359", value="1k2 1%"))
    assert after.per_12v_a == pytest.approx(before.per_12v_a * 1500 / 1200,
                                            abs=0.002)
    assert after.load_12v_a == pytest.approx(before.load_12v_a + 4 * (
        after.per_12v_a - before.per_12v_a), abs=0.002)
    assert after.load_12v_a > before.load_12v_a + 1.5


def test_a_limiter_nobody_has_an_equation_for_fails_loudly():
    """⛔ Never a skip.  A switch this module has no datasheet equation for
    means the ceiling is unknown, and an unknown ceiling must not quietly
    become a smaller number."""
    odd = D.replace_part("U303", mpn="SOME-OTHER-QUAD-SWITCH")
    lim = pb.limit_case(odd)
    assert any("SOME-OTHER-QUAD-SWITCH" in p for p in lim.problems)
    assert lim.load_12v_a is None
    assert any("limit case is not derivable" in p
               for p in pb.budget(odd).problems)


def test_a_limiter_whose_programming_resistor_is_unreadable_fails_loudly():
    """A value with no resistance in it, and a 0 Ω link, are both "no rating"
    on a programming pin -- the ceiling is then unknown, and unknown must not
    become a number."""
    # A value with no resistance in it never reaches the budget: the model
    # refuses the resistor at construction (M11).
    with pytest.raises(ValueError, match="R359: value='as marked'"):
        D.replace_part("R359", value="as marked")
    lim = pb.limit_case(D.replace_part("R359", value="0R"))
    assert any("U303" in p and "not derivable" in p for p in lim.problems), lim.problems
    assert lim.load_12v_a is None


# --- the command line -------------------------------------------------------------------
def test_main_prints_the_numbers_and_passes(capsys):
    assert pb.main() == 0
    out = capsys.readouterr().out
    assert out.splitlines()[-1] == "PASS"
    assert "U201" in out and "L101" in out and "KLKD003" in out


def test_the_printed_line_names_the_case_it_is_quoting(capsys):
    """⚠️ Tasks 8-9 paste this line into reader-facing documents.  It once read
    '12 V worst case 8.47 A' three lines under a docstring that opens by
    saying 8.47 A is NOT the worst case.  It must name the case it models and
    show the limiters' figure beside it."""
    pb.main()
    out = capsys.readouterr().out
    assert "worst case" not in out
    assert "12 V nominal load 8.47 A" in out
    assert "LIMITED 11.39 A" in out and "converter input" in out
    assert "SHED 2.62 A" in out and "tap 0.63 A" in out and "IO-16" in out
    assert "TDK" not in out, "the module does not name the brick's maker"


def test_main_fails_loudly(capsys, monkeypatch):
    monkeypatch.setattr(pb, "TAP_FUSE_A", 2.0)
    assert pb.main() == 1
    out = capsys.readouterr().out
    assert out.splitlines()[-1] == "FAIL" and "⛔" in out


def test_the_docstring_says_which_case_it_models():
    """AUX_OUTPUT_A is the NOMINAL load, not the limiters' ceiling.  Whoever
    reads 8.47 A must be able to see, in the module itself, that the eight
    limiters can pass more than that -- and that the 2.62 A base inside the
    limiters' own figure is nominal too."""
    doc = pb.__doc__.lower()
    assert "nominal" in doc and "current limit" in doc
    assert "limit_case" in doc and "limited" in doc


def test_nothing_in_the_module_is_named_after_a_manufacturer():
    """The module goes out of its way not to name L101 or U201, because a
    check that names a refdes stops checking when the part is renumbered.  A
    field called `tdk_in_a` broke the same rule one level up: rename the brick
    and the result field is a lie.  ⚠️ `Part.mpn` is fine -- that IS the part."""
    names = set(vars(pb)) | set(pb.Result.__dataclass_fields__)
    assert not [n for n in names if "tdk" in n.lower()]
    assert "conv_in_a" in pb.Result.__dataclass_fields__
    assert pb.CONV_EFF == 0.90


# --- the two mated pairs the 5 V buck is fed through (IO-26 2a) ------------------------
def test_the_buck_rail_contacts_are_sized_on_both_pairs():
    """⭐ The 5 V aux buck is on CTRL and `U201` makes V12 on POWER, so the
    rail crosses PWR-LOGIC and then CTRL-STACK. Nothing else in the design
    derives what those contacts carry.

    The arithmetic, all of it from the copper: four channels at their ILIM
    resistors' upper threshold (1.39 A each, `limit_case`), 5 V out, 90 %
    efficient, off 12 V -> 2.57 A. Two V12 contacts on each pair carry 1.29 A
    each in service.

    ⛔ THE GATE IS THE ONE-CONTACT CASE, not the shared one -- 2.57 A against
    the 3 A Hong Cheng contact, 86 %. Contacts in parallel share until one of
    them stops, and an open contact is silent, which is the same reasoning
    IO-27 used for PWR-OUT's two 16 AWG returns. The 3 A is
    `Connector.contact_a`, read off Hong Cheng's HC-PM254-8.5H /
    HC-PZ254-11.5L drawings and stated once, in netlist.py."""
    r = pb.budget(D)
    assert r.problems == []
    assert r.buck_in_a == pytest.approx(4 * 1.39 * 5.0 / 0.90 / 12.0, abs=0.02)
    by = {(c.interface, c.net): c for c in r.contacts}
    assert set(by) == {("PWR-LOGIC", "V12"), ("PWR-LOGIC", "GND"),
                       ("CTRL-STACK", "V12"), ("CTRL-STACK", "GND")}
    for iface in ("PWR-LOGIC", "CTRL-STACK"):
        rail = by[(iface, "V12")]
        assert rail.refdes == (("J307", "J407") if iface == "PWR-LOGIC"
                               else ("J411", "J501"))
        assert rail.n == 2 and rail.rating_a == 3.0
        assert rail.shared_a == pytest.approx(r.buck_in_a / 2, abs=0.01)
        assert rail.alone_a == pytest.approx(r.buck_in_a, abs=0.01)
        assert rail.ok and rail.alone_a / rail.rating_a < 0.90
        # ...and the return it goes out and comes back through, on the same
        # pair: more contacts, the same one-contact gate.
        gnd = by[(iface, "GND")]
        assert gnd.n >= 6 and gnd.ok


def test_the_buck_rail_check_fires_on_a_clone_contact_and_on_a_bigger_buck():
    """A check nothing can fail is not a check, and both mutations are real:

    ⛔ THE CLONE. A 2.54 mm header that lists the same body at 2 A instead of
    Hong Cheng's 3 A -- the Blue Sea and the CAX 'VH' failure again, a right
    family with a wrong rating line. ⚠️ 2 A is chosen because it PASSES the
    shared figure: 1.29 A a contact looks comfortable, and only the
    one-contact case says the pair has a silent failure in it.
    ⛔ MORE 5 V CHANNELS. IO-1 says more aux outputs are acceptable; eight of
    them put 5.15 A through the same two contacts, and the pair has to say so
    rather than the buck quietly out-growing its feed."""
    clone = D.replace_connector("J411", contact_a=2.0)
    errs = pb.budget(clone).problems
    assert any("J411+J501 (CTRL-STACK) V12" in e and "ONE contact rated 2 A" in e
               for e in errs), errs
    assert all("PWR-LOGIC" not in e for e in errs), "only the clone half fails"
    # ...and 1.29 A each is what makes the shared figure look fine:
    rail = next(c for c in pb.budget(clone).contacts
                if (c.interface, c.net) == ("CTRL-STACK", "V12"))
    assert rail.shared_a < rail.rating_a < rail.alone_a

    big = D
    for n in range(5, 9):
        big = (big.with_part(replace(D.part("U306"), refdes=f"U{305 + n}"))
                  .with_part(replace(D.part("R373"), refdes=f"R{372 + n}"))
                  .with_net(Net(f"AUX5V_{n}", (("R901", "1"),
                                               (f"U{305 + n}", "OUT")), "5V"))
                  .with_net(Net(f"AUX5V_{n}_ILIM", ((f"U{305 + n}", "ILIM"),
                                                    (f"R{372 + n}", "1")), "3V3")))
    r = pb.budget(big)
    assert r.buck_in_a > 5.0
    assert any("V12" in e and "ONE contact rated 3 A" in e for e in r.problems), \
        r.problems


def test_a_pair_with_no_rating_cannot_be_sized():
    """⚠️ `contact_a=None` means the maker's drawing states none, so nothing
    may be assumed -- and the un-sizeable case is a PROBLEM, never a skip."""
    blank = D.replace_connector("J307", contact_a=None)
    errs = pb.budget(blank).problems
    assert any("J307+J407 (PWR-LOGIC)" in e and "no per-contact rating" in e
               for e in errs), errs


def test_a_rail_that_never_reaches_the_board_that_draws_it_is_a_problem():
    """⛔ The other half of the check: parts on CTRL draw V12, so a pair must
    carry it. Take V12 off both pairs' pin tables and the rail no longer
    reaches the buck -- which `integrity` also catches, and which this states
    in the language of the thing that is sized."""
    stripped = D
    for ref in ("J307", "J407", "J411", "J501"):
        j = stripped.connector(ref)
        stripped = stripped.replace_connector(ref, pins=tuple(
            replace(cp, net="GND") if cp.net == "V12" else cp for cp in j.pins))
    errs = pb.budget(stripped).problems
    assert any("draw V12 on CTRL and no mated pair carries it" in e
               for e in errs), errs


def test_a_cable_is_not_sized_by_dividing_its_current_over_contacts():
    """⛔ PWR-OUT carries V12 too and is deliberately NOT in this list: a loom
    sizes its CONDUCTOR and the one crimped contact it lands on (IO-20), which
    tests/test_interconnect.py holds it to at the full 8.47 A. Dividing a
    cable's current over contacts is the mistake that rule replaced, and a
    check that did it here would report the loom as four times safer than it
    is."""
    r = pb.budget(D)
    assert {c.interface for c in r.contacts} == {"PWR-LOGIC", "CTRL-STACK"}
    assert "PWR-OUT" not in {c.interface for c in r.contacts}
    assert "V12" in {cp.net for cp in D.connector("J202").pins}
