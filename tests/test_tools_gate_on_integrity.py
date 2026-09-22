"""Every tool that reports on the design reads it through `netlist.checked()`,
and a design integrity rejects gets no report at all.

Until 2026-09-21 only `build_project.py` ran integrity first (H10). On the
2026-09-18 defect verbatim -- D101.K lifted off HV_BPLUS and J406 on LOGIC's
top face, so both STACK halves stand on top and cannot mate -- integrity said
2 problems and exit 1 while board_fit, gpio_budget, power_budget and
soft_start printed ✅ PASS, jlc_bom emitted the full BOM, layout_rules the HV
class and tel_check compared an export against it. The documented run order
was the only thing holding that together.

Each test here hands that design to one tool's ENTRY POINT, `main()`, by
making `netlist.current()` return it, and asserts a non-zero exit, the two
integrity problems in what was printed, and no PASS.
"""
import pytest

from tools import (board_fit, gpio_budget, jlc_bom, layout_rules, lcsc_fixture,
                   netlist, power_budget, rules, soft_start, tel_check)

REAL = netlist.current()
#: The 2026-09-18 defect, verbatim.
BROKEN = REAL.without_pin("D101", "K").replace_connector("J406", side="top")
PROBLEMS = ("floating: D101.K (SMCJ90A) is on no net",
            "interface: J308 must stand on top of OUTPUTS and J406 hang under "
            "LOGIC to face each other; they are top and top")


@pytest.fixture
def broken_netlist(monkeypatch):
    monkeypatch.setattr(netlist, "current", lambda: BROKEN)


def _refused(text: str) -> None:
    assert "2 integrity problem(s)" in text, text
    for p in PROBLEMS:
        assert p in text, text
    assert "PASS" not in text and "identical" not in text, text


# --- checked() itself ------------------------------------------------------------
def test_checked_is_the_real_design_when_it_is_a_circuit():
    assert netlist.checked() == REAL


def test_checked_refuses_a_design_that_is_not_a_circuit(broken_netlist):
    with pytest.raises(netlist.NotACircuit) as e:
        netlist.checked()
    _refused(str(e.value))
    assert isinstance(e.value, ValueError)         # a caller catching ValueError still stops


def test_current_stays_ungated_for_the_fixtures_that_need_it(broken_netlist):
    """The tests build broken designs on purpose; `current()` is theirs."""
    assert netlist.current() == BROKEN


# --- every tool's entry point ------------------------------------------------------
def test_board_fit_refuses(broken_netlist, capsys):
    assert board_fit.main([]) == 1
    _refused(capsys.readouterr().out)


def test_gpio_budget_refuses(broken_netlist, capsys):
    assert gpio_budget.main([]) == 1
    _refused(capsys.readouterr().out)


def test_power_budget_refuses(broken_netlist, capsys):
    assert power_budget.main() == 1
    _refused(capsys.readouterr().out)


def test_soft_start_refuses(broken_netlist, capsys):
    assert soft_start.main([]) == 1
    out = capsys.readouterr().out
    assert "⛔ FAIL" in out and "could not be read off the netlist: NotACircuit" in out
    _refused(out)


def test_jlc_bom_refuses(broken_netlist, capsys, tmp_path):
    out_csv = tmp_path / "bom.csv"
    assert jlc_bom.main(["--out", str(out_csv)]) == 1
    captured = capsys.readouterr()
    _refused(captured.err)
    assert not out_csv.exists() and "LCSC Part #" not in captured.out


def test_layout_rules_refuses(broken_netlist, capsys):
    assert layout_rules.main([]) == 1
    captured = capsys.readouterr()
    _refused(captured.err)
    assert "Net class" not in captured.out


def test_rules_refuses_rather_than_grading_a_non_circuit(broken_netlist, capsys):
    """Green rules on a netlist that fails integrity mean nothing (CLAUDE.md):
    a TVS with one leg landed passes every rule."""
    assert rules.main([]) == 1
    captured = capsys.readouterr()
    _refused(captured.out)
    assert "rule violation(s)" not in captured.out


def test_lcsc_fixture_refuses_before_touching_the_library(broken_netlist, capsys, monkeypatch,
                                                            tmp_path):
    monkeypatch.setattr(lcsc_fixture, "service", lambda: pytest.fail("the library was reached"))
    monkeypatch.setattr(lcsc_fixture, "FIXTURE", tmp_path / "lcsc.json")
    assert lcsc_fixture.main([]) == 1
    _refused(capsys.readouterr().out)
    assert not (tmp_path / "lcsc.json").exists()


def test_tel_check_refuses_before_reading_the_export(broken_netlist, capsys, tmp_path):
    tel = tmp_path / "Netlist_LOGIC.tel"
    tel.write_text("", encoding="utf-8")            # never parsed: the refusal comes first
    assert tel_check.main(["LOGIC", str(tel)]) == 1
    _refused(capsys.readouterr().out)


# --- and the same entry points on the real design still run -------------------------
def test_the_real_design_still_reaches_every_report(capsys):
    # ⭐ board_fit is back to 0 (IO-26 2a, 2026-09-22): the 5 V block and J314
    # left OUTPUTS for CTRL, and all four edges fit. It exited 1 on the ROWS
    # verdict alone from the day IO-26 found the two-face error until that
    # landed; ⛔ if it ever returns 1 again, the row is a real overrun and not
    # a known one.
    assert board_fit.main([]) == 0
    out = capsys.readouterr().out
    assert "⛔ DOES NOT FIT" not in out and "✅ PASS" in out
    assert gpio_budget.main([]) == 0
    assert power_budget.main() == 0
    assert soft_start.main([]) == 0
    assert layout_rules.main([]) == 0
    assert rules.main([]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "Net class HV" in out and "0 rule violation(s)" in out
