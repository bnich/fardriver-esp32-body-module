"""Library footprints bound to devices, their pads renamed to our pins.

A fake library stands in for EasyEDA's: a SOT-23 footprint whose pads are
numbered 1-3 as every SOT-23 is, and a 3-position screw terminal.  What must
hold: the bound footprint's pads carry our pin names by the pad map, one
footprint per device, and nothing is bound without a library.
"""
import json

import pytest

from tools import footprint_lib, netlist
from tools.eprj3.project import Project
from tools.eprj3.schematic import emit_board


def _pad(eid, num, x):
    return (f'["PAD","{eid}",0,"",1,"{num}",{x},0,0,null,["RECT",30,40],[],0,0,0,1,0,'
            f'null,null,null,null,0]')


def _v2(pads):
    return "\n".join(['["DOCTYPE","FOOTPRINT","1.3"]',
                      '["LAYER",1,"TOP","Top Layer",3,"#ff0000",1,"#7f0000",1]',
                      '["LAYER",12,"MULTI","Multi-Layer",3,"#c0c0c0",1,"#606060",1]',
                      '["ACTIVE_LAYER",1]', *pads, '["CANVAS",0,0,"mil",5,5]'])


SOT23 = _v2([_pad("e1", "1", -40), _pad("e2", "2", 40), _pad("e3", "3", 0)])
TB6 = _v2([_pad(f"e{i}", str(i), i * 300) for i in range(1, 7)])


def _docs(sheet):
    docs, cur = {}, None
    for rec in sheet.library_records:
        head, _, payload = rec.partition("||")
        h, p = json.loads(head), json.loads(payload)
        if h["type"] == "DOCHEAD":
            cur = [(h, p)]
            docs.setdefault(p["docType"], []).append(cur)
        else:
            cur.append((h, p))
    return docs


def _emit(board, table):
    design = netlist.current()
    project = Project("t")
    project.add_board(board)
    sheet = project.boards[0].schematic.sheets[0]
    bs = emit_board(design, board, sheet, library=footprint_lib.FakeLibrary(table))
    return design, sheet, bs


def test_a_fets_footprint_pads_become_gate_source_drain():
    code = next(p.lcsc for p in netlist.current().parts if p.mpn == "AO3400A")
    design, sheet, bs = _emit("DRV", {code: ("SOT-23-3", SOT23)})
    docs = _docs(sheet)
    devices = [d for d in docs["DEVICE"] if d[1][1]["attributes"].get("Supplier Part") == code]
    assert len(devices) == 1, "one device, so one footprint, for every AO3400A"
    fp_uuid = devices[0][1][1]["attributes"]["Footprint"]
    fp = next(d for d in docs["FOOTPRINT"] if d[0][1]["uuid"] == fp_uuid)
    pads = {p["num"]: (p["centerX"]) for h, p in fp if h["type"] == "PAD"}
    assert pads == {"G": -40, "S": 40, "D": 0}
    assert set(r for r in bs.footprints_bound) >= {"Q301", "Q302"}


def test_the_b_plus_terminal_binds_its_library_footprint_pad_for_pin():
    """J101 is a 6-position 7.62 mm screw terminal: B+, empty, B−, B−, empty, KSW."""
    code = netlist.current().connector("J101").lcsc
    design, sheet, bs = _emit("HVIN", {code: ("TB6", TB6)})
    fp = next(d for d in _docs(sheet)["FOOTPRINT"] if d[1][1]["title"] == "TB6")
    assert sorted(p["num"] for h, p in fp if h["type"] == "PAD") == [str(i) for i in range(1, 7)]
    assert "J101" in bs.footprints_bound


def test_a_pad_the_map_does_not_know_is_refused():
    code = next(p.lcsc for p in netlist.current().parts if p.mpn == "AO3400A")
    odd = _v2([_pad("e1", "1", 0), _pad("e2", "2", 10), _pad("e3", "3", 20), _pad("e4", "9", 30)])
    with pytest.raises(ValueError, match="in no pad map"):
        _emit("DRV", {code: ("SOT-23-3?", odd)})


def test_a_footprint_that_leaves_a_pin_without_a_pad_is_refused():
    code = next(p.lcsc for p in netlist.current().parts if p.mpn == "AO3400A")
    short = _v2([_pad("e1", "1", 0), _pad("e2", "2", 10)])
    with pytest.raises(ValueError, match="no pad"):
        _emit("DRV", {code: ("SOT-23-2?", short)})


def test_without_a_library_only_generated_footprints_are_bound():
    design = netlist.current()
    project = Project("t")
    project.add_board("DRV")
    sheet = project.boards[0].schematic.sheets[0]
    bs = emit_board(design, "DRV", sheet)
    assert set(bs.footprints_bound) == {"J307", "J308", "J311"}
    assert "Q301" in bs.footprints_unbound


def test_the_inter_board_connectors_get_a_2_54_mm_header_pattern():
    """The family is the owner's open choice, but every option on the list is
    on the 2.54 mm grid: the family sets the mated height, not the holes."""
    design, sheet, bs = _emit("DRV", {})
    fps = _docs(sheet)["FOOTPRINT"]
    by_title = {d[1][1]["title"]: d for d in fps}
    stack = next(d for t, d in by_title.items() if "2X25" in t.upper())
    assert sorted(int(p["num"]) for h, p in stack if h["type"] == "PAD") == list(range(1, 51))
    assert {"J307", "J308"} <= set(bs.footprints_bound)


def test_every_footprint_title_is_safe_for_an_allegro_netlist():
    """EasyEDA's netlist export (.tel) is Allegro's format, which rejects
    '; ! .' and spaces in a footprint name (the editor warns and names the
    parts).  Library titles also carry non-ASCII text ('弯插,P=2mm')."""
    code = next(p.lcsc for p in netlist.current().parts if p.mpn == "AO3400A")
    design, sheet, bs = _emit("DRV", {code: ("SOT-23-3_L2.9-W1.3 弯插", SOT23)})
    import re
    for d in _docs(sheet)["FOOTPRINT"]:
        title = d[1][1]["title"]
        assert re.fullmatch(r"[A-Za-z0-9_\-()+=,#]+", title), title
