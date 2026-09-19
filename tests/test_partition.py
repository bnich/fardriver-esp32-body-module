"""Three boards, bottom to top: POWER (84 V, both converters, the controller
row), OUTPUTS (every driver, the 12 V and 5 V rows), LOGIC (the S3, the
inputs row). Design spec IO-7."""
from tools import board_params as bp, integrity, netlist


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


def test_every_interface_joins_neighbours():
    assert integrity.INTERFACE_BOARDS == {
        "PWR-OUT": ("POWER", "OUTPUTS"),
        "PWR-LOGIC": ("OUTPUTS", "LOGIC"),
        "STACK": ("OUTPUTS", "LOGIC"),
    }
