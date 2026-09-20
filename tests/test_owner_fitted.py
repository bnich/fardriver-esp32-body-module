"""Parts JLC must not fit, and how each output says so.

Through-hole parts the height budget counts LYING on the board would be
inserted upright by JLC; the fuse clips into a holder.  They are ordered from
LCSC with the boards ('loose') and fitted by the owner.  EasyEDA's own BOM and
assembly order read `Add into BOM`, never `DNP`, so every part JLC must not
fit says `Add into BOM: no`.
"""
from tools import jlc_bom, netlist, rules
from tools.eprj3 import schematic

LYING = {"C201", "C202", "C203", "C204", "C205", "C206", "C207"}


def test_parts_that_lie_flat_and_the_fuse_are_fitted_by_the_owner():
    d = netlist.current()
    loose = {p.refdes for p in d.parts if p.assembly == "loose"}
    assert loose == LYING | {"F201", "FH201"}
    for ref in LYING:
        p = d.part(ref)
        assert "lying" in p.package.lower() or "flat" in p.package.lower(), ref
        assert p.lcsc


def test_jlc_places_none_of_them_and_the_order_list_counts_them():
    d = netlist.current()
    bom = jlc_bom.bom_csv(d)
    listed = jlc_bom.loose_list(d)
    for ref in LYING | {"F201", "FH201"}:
        assert ref not in bom and ref in listed, ref
    fh = next(line for line in listed.splitlines() if "for FH201" in line)
    assert fh.split()[1] == "x2", "two clips make one holder"
    y2 = next(line for line in listed.splitlines() if "for C203" in line)
    assert y2.split()[1] == "x4"


def _attrs(d, ref):
    part = next((p for p in d.parts if p.refdes == ref), None)
    conn = None if part else d.connector(ref)
    item = next(i for i in schematic.board_items(d, (part or conn).board) if i.ref == ref)
    return dict((a[0], a[1]) for a in
                schematic._part_attrs(item, 0, 0, "u", part=part, connector=conn))


def test_easyeda_is_told_which_parts_jlc_must_not_fit():
    d = netlist.current()
    for ref in ("C201", "F201", "U201", "L101", "U406", "D317", "J408"):
        assert _attrs(d, ref).get("Add into BOM") == "no", ref
    for ref in ("R401", "U401", "J302", "J409"):
        assert "Add into BOM" not in _attrs(d, ref), ref


def test_the_fuse_holder_conducts_only_through_its_fuse():
    """Its two clips are two nets; take the fuse out and nothing joins them."""
    d = netlist.current()
    fh = d.part("FH201")
    a, b = (d.net_of("FH201", pin).name for pin in fh.pins)
    assert a != b and {a, b} == {n.name for n in d.nets_of("F201")}
    ix = rules._index(d.without_part("F201"))
    assert b not in ix.walk(a, rules._SERIES, fitted_only=False)
