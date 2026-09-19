"""The JLC assembly BOM, written from the netlist: one line per LCSC part."""
import csv
import io

from tools import jlc_bom, netlist


def rows():
    return list(csv.DictReader(io.StringIO(jlc_bom.bom_csv(netlist.current()))))


def test_header_is_the_one_jlc_reads():
    text = jlc_bom.bom_csv(netlist.current())
    assert text.splitlines()[0] == "Comment,Designator,Footprint,LCSC Part #"


def test_every_jlc_placed_item_appears_exactly_once():
    d = netlist.current()
    want = sorted(x.refdes for x in list(d.parts) + list(d.connectors)
                  if x.assembly == "jlc" and not getattr(x, "dnp", False))
    got = sorted(r for row in rows() for r in row["Designator"].split(","))
    assert got == want


def test_one_line_per_lcsc_part_and_no_hand_or_dnp_item():
    d = netlist.current()
    codes = [row["LCSC Part #"] for row in rows()]
    assert len(codes) == len(set(codes))
    placed = {r for row in rows() for r in row["Designator"].split(",")}
    for x in list(d.parts) + list(d.connectors):
        if x.assembly == "hand" or getattr(x, "dnp", False):
            assert x.refdes not in placed, x.refdes


def test_hand_list_names_every_hand_soldered_item():
    d = netlist.current()
    text = jlc_bom.hand_list(d)
    for x in list(d.parts) + list(d.connectors):
        if x.assembly == "hand":
            assert x.refdes in text


def test_the_loose_plugs_are_listed_by_part_with_their_count():
    """The screw plugs are not placed: they are ordered with the boards and
    wired by the owner.  One line per plug part, with every terminal it fits.
    A parked terminal has no header fitted, so no plug is bought for it."""
    d = netlist.current()
    lines = jlc_bom.plug_list(d).splitlines()
    by_part = {}
    for c in d.connectors:
        if c.plug and not c.dnp:
            by_part.setdefault(c.plug, []).append(c.refdes)
    parked = [c.refdes for c in d.connectors if c.parked]
    assert parked and not any(r in jlc_bom.plug_list(d) for r in parked)
    assert len(lines) == len(by_part)
    for plug, refs in by_part.items():
        line = next(l for l in lines if l.startswith(plug))
        assert f" x{len(refs)} " in line and all(r in line for r in refs)
