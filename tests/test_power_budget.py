"""IO-10: all eight aux outputs at 1 A on at once must stay inside the 12 V
converter's input choke and the module's tap fuse at the 60 V LVC (plan
§3.2.3 / §3.2.6: size at the LVC, never at full charge).

⚠️ The mutations below are the point of the file.  A budget that only ever
prints a number agrees with itself; these fail it with a 2 A choke, a 2 A tap
fuse, a converter asked for more than it makes, and a rating nobody can read
off the part -- the four ways the input path can be under-sized.
"""
import pytest

from tools import netlist, power_budget as pb
from tools.model import Net

D = netlist.current()


# --- the design ------------------------------------------------------------------------
def test_the_real_design_fits():
    r = pb.budget(D)
    assert 8.3 < r.load_12v_a < 8.7          # 2.62 + 4 × 1.0 + 20 W / 0.9 / 12 V = 8.47
    assert r.problems == []


def test_the_numbers_are_the_ones_the_spec_states():
    """Design spec §8's table, to two decimals: 8.47 A at 12 V and 1.89 A into
    the TDK at the LVC.  If the netlist grows a channel these move, and the
    spec is then the thing that is out of date -- not this."""
    r = pb.budget(D)
    assert r.aux12_a == pytest.approx(4.00, abs=0.005)
    assert r.aux5_a == pytest.approx(1.85, abs=0.005)
    assert r.load_12v_a == pytest.approx(8.47, abs=0.005)
    assert r.tdk_in_a == pytest.approx(1.88, abs=0.005)
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


def test_a_load_over_the_converters_own_rating_fails(monkeypatch):
    """3 A per channel: 2.62 + 12 + 5.56 = 20.2 A, where the brick makes
    12.5 A.  The choke and the fuse fire too -- the converter must also."""
    monkeypatch.setattr(pb, "AUX_OUTPUT_A", 3.0)
    problems = pb.budget(D).problems
    assert any("U201" in p and "12.5 A" in p for p in problems)


# --- the parts are found through the copper, not by refdes ------------------------------
def test_the_converter_and_its_choke_are_found_through_the_copper():
    r = pb.budget(D)
    assert (r.converter.refdes, r.choke.refdes) == ("U201", "L101")
    assert r.choke_rated_a == 3.0 and r.conv_rated_a == 12.5


def test_the_choke_named_is_the_one_on_the_12_v_brick_not_the_other():
    """L102 shares HV_SW and GND with L101.  A lookup that walked any shared
    net would pick whichever came first in the parts tuple; this one follows
    the 84 V nets of the brick that makes 12 V."""
    swapped = D.replace_part("L102", value="10 mH · 0.5 A @ 70 °C · 300 V AC")
    assert pb.budget(swapped).problems == []


def test_a_design_with_no_choke_on_the_input_fails():
    assert any("no common-mode choke" in p
               for p in pb.budget(D.without_part("L101")).problems)


# --- the command line -------------------------------------------------------------------
def test_main_prints_the_numbers_and_passes(capsys):
    assert pb.main() == 0
    out = capsys.readouterr().out
    assert out.splitlines()[-1] == "PASS"
    assert "U201" in out and "L101" in out and "KLKD003" in out


def test_main_fails_loudly(capsys, monkeypatch):
    monkeypatch.setattr(pb, "TAP_FUSE_A", 2.0)
    assert pb.main() == 1
    out = capsys.readouterr().out
    assert out.splitlines()[-1] == "FAIL" and "⛔" in out


def test_the_docstring_says_which_case_it_models():
    """AUX_OUTPUT_A is the NOMINAL load, not the limiters' ceiling.  Whoever
    reads 8.47 A must be able to see, in the module itself, that the eight
    limiters can pass more than that."""
    doc = pb.__doc__.lower()
    assert "nominal" in doc and "current limit" in doc
