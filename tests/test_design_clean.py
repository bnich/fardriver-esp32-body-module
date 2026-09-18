"""The real design, held to both gates. No filter, no allow-list.

tests/test_rules.py proves each rule on a fixture. A rule proven only on a
fixture says nothing about the boards that get made: a one-line defect in
netlist.py can make `check_all` report an error while every fixture test stays
green. These tests close that gap, and they are the only ones that do.

A failure prints every problem, because the list IS the work remaining.
"""
from tools import integrity, netlist, rules


def test_the_real_netlist_is_a_circuit():
    problems = integrity.check(netlist.current())
    assert problems == [], (
        f"{len(problems)} integrity problem(s):\n" + "\n".join(problems))


def test_the_real_netlist_does_its_job():
    errs = rules.check_all(netlist.current())
    assert errs == [], f"{len(errs)} rule violation(s):\n" + "\n".join(errs)


def test_the_warnings_can_be_read():
    """Warnings never fail the gate; they must still be producible, so that
    `python3 -m tools.rules` can show them to whoever signs the boards off."""
    notes = rules.warnings(netlist.current())
    assert all(isinstance(w, str) and ":" in w for w in notes)
