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
