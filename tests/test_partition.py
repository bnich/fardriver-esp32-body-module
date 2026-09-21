"""Three boards, bottom to top: POWER (84 V, both converters, the controller
row), OUTPUTS (every driver, the 12 V and 5 V rows), LOGIC (the S3, the
inputs row). Design spec IO-7."""
from tools import board_params as bp, integrity, netlist
from tools.model import CROSSING


def test_three_boards_bottom_to_top():
    assert bp.STACK_ORDER == ("POWER", "OUTPUTS", "LOGIC")


def test_every_item_sits_on_one_of_the_three():
    d = netlist.current()
    assert {x.board for x in (*d.parts, *d.connectors)} == {"POWER", "OUTPUTS", "LOGIC"}


def test_pack_voltage_stays_on_power():
    d = netlist.current()
    for n in d.nets:
        if n.domain == "84V":
            assert {d.board_of(r) for r, _ in n.pins} == {"POWER"}, n.name


def test_the_power_board_is_built_around_the_brick_on_its_floor_seat():
    """BD-27: U201's baseplate bolts to the box floor through a thermal pad and
    is the stack's only heatsink, so both converters ride POWER's underside --
    U202 at 10.7 mm clears under the brick's 12.7 mm seat. The 18.5 mm bulk cans
    go on top, where nothing may hang deeper than that seat does."""
    d = netlist.current()
    assert bp.FLOOR_SEAT == "U201" and bp.STACK_ORDER[0] == "POWER"
    assert [(d.part(r).board, d.part(r).side) for r in ("U201", "U202")] \
        == [("POWER", "bottom")] * 2
    assert [(d.part(r).board, d.part(r).side) for r in ("C201", "C202")] \
        == [("POWER", "top")] * 2


def test_every_interface_joins_neighbours():
    assert integrity.INTERFACE_BOARDS == {
        "PWR-OUT": ("POWER", "OUTPUTS"),
        "CTRL": ("POWER", "OUTPUTS"),
        "PWR-LOGIC": ("OUTPUTS", "LOGIC"),
        "STACK": ("OUTPUTS", "LOGIC"),
    }


def test_each_crossing_declares_how_it_crosses():
    """IO-20: no stocked connector spans the 25.1 mm POWER → OUTPUTS gap, so
    those two crossings are CABLES; the 11.0 mm ones stay mated pairs. The two
    kinds are held to different truths, so a crossing with no declared kind is
    a crossing whose checks nobody chose -- `integrity` reports one."""
    assert CROSSING == {
        "PWR-OUT": "cable",
        "CTRL": "cable",
        "PWR-LOGIC": "pair",
        "STACK": "pair",
    }
    assert set(CROSSING) == set(integrity.INTERFACE_BOARDS)
