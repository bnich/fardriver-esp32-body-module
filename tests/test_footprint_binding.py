"""Library footprints bound to devices, their pads renamed to our pins.

A fake library stands in for EasyEDA's: a SOT-23 footprint whose pads are
numbered 1-3 as every SOT-23 is, and a 3-position screw terminal.  What must
hold: the bound footprint's pads carry our pin names by the pad map, one
footprint per device, and nothing is bound without a library.
"""
import json
from dataclasses import replace

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
    design, sheet, bs = _emit("OUTPUTS", {code: ("SOT-23-3", SOT23)})
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
    design, sheet, bs = _emit("POWER", {code: ("TB6", TB6)})
    fp = next(d for d in _docs(sheet)["FOOTPRINT"] if d[1][1]["title"] == "TB6")
    assert sorted(p["num"] for h, p in fp if h["type"] == "PAD") == [str(i) for i in range(1, 7)]
    assert "J101" in bs.footprints_bound


def test_a_pad_the_map_does_not_know_is_refused():
    code = next(p.lcsc for p in netlist.current().parts if p.mpn == "AO3400A")
    odd = _v2([_pad("e1", "1", 0), _pad("e2", "2", 10), _pad("e3", "3", 20), _pad("e4", "9", 30)])
    with pytest.raises(ValueError, match="in no pad map"):
        _emit("OUTPUTS", {code: ("SOT-23-3?", odd)})


def test_a_footprint_that_leaves_a_pin_without_a_pad_is_refused():
    code = next(p.lcsc for p in netlist.current().parts if p.mpn == "AO3400A")
    short = _v2([_pad("e1", "1", 0), _pad("e2", "2", 10)])
    with pytest.raises(ValueError, match="no pad"):
        _emit("OUTPUTS", {code: ("SOT-23-2?", short)})


def test_without_a_library_only_generated_footprints_are_bound():
    design = netlist.current()
    project = Project("t")
    project.add_board("OUTPUTS")
    sheet = project.boards[0].schematic.sheets[0]
    bs = emit_board(design, "OUTPUTS", sheet)
    assert set(bs.footprints_bound) == {"J307", "J308", "J311", "J312"}
    assert "Q301" in bs.footprints_unbound


def test_the_inter_board_connectors_get_a_2_54_mm_header_pattern():
    """Three of the four crossings are 2.54 mm families -- PWR-LOGIC's and
    STACK's Hong Cheng pair and CTRL's box header -- so their land is the
    2.54 mm grid whatever their bodies do above it.  ⛔ The fourth is not:
    PWR-OUT is a 3.96 mm JST wafer, which the test below covers."""
    design, sheet, bs = _emit("OUTPUTS", {})
    fps = _docs(sheet)["FOOTPRINT"]
    by_title = {d[1][1]["title"]: d for d in fps}
    n = len(design.connector("J308").pins)
    stack = next(d for t, d in by_title.items() if f"2X{n // 2}" in t.upper())
    assert sorted(int(p["num"]) for h, p in stack if h["type"] == "PAD") == list(range(1, n + 1))
    assert {"J307", "J308"} <= set(bs.footprints_bound)


#: The VH post is □1.14 (JST drawing p.1): its diagonal is what the finished
#: hole has to clear.  JLC finishes a plated hole +0.13/-0.08 on the drill.
#: JST's PCB layout gives ø1.65 +0.1/0, and asks for a ring JLC's 0.25 mm
#: minimum annular ring satisfies.
VH_POST_DIAG_MM = 1.14 * 2 ** 0.5          # 1.612
JLC_HOLE_UNDER_MM = 0.08
JST_VH_HOLE_MAX_MM = 1.75
MIN_RING_MM = 0.25


def vh_drill_problems(conn):
    """Every way the generated VH land's drill could fail to take the header,
    from the emitted pads and not the netlist's number: a low batch under the
    post's diagonal, a nominal outside JST's band, a ring under JLC's minimum."""
    _title, pads, _s, _o = footprint_lib.generated(conn)
    out = []
    for p in pads:
        low = p.hole_mm - JLC_HOLE_UNDER_MM
        if not low > VH_POST_DIAG_MM:
            out.append(f"{conn.refdes} pad {p.num}: a low batch finishes at "
                       f"{low:.3f}, under the post's {VH_POST_DIAG_MM:.3f} diagonal")
        if p.hole_mm > JST_VH_HOLE_MAX_MM:
            out.append(f"{conn.refdes} pad {p.num}: ø{p.hole_mm} is over JST's "
                       f"{JST_VH_HOLE_MAX_MM} maximum")
        ring = (min(p.w_mm, p.h_mm) - p.hole_mm) / 2
        if ring < MIN_RING_MM:
            out.append(f"{conn.refdes} pad {p.num}: {ring:.3f} mm ring under "
                       f"JLC's {MIN_RING_MM}")
    return out


def test_the_keyed_power_header_leaves_its_omitted_post_empty():
    """⭐ The key is COPPER, not a note. `B4P(5-3)-VH` is a five-wide wafer with
    the third post omitted, so the land must have four holes on a five-position
    3.96 mm grid with the middle one absent, drilled for a □1.14 post -- not
    the ø1.0 that suits the 0.64 mm posts every 2.54 mm family here uses.

    The drill is checked as a FIT, not a number. The post's diagonal is 1.14 ×
    √2 = 1.612 mm; JLC finishes a hole as much as 0.08 under the drill, so the
    drill must exceed 1.692. JST's own ø1.65 fails that -- 1.65 - 0.08 = 1.57
    -- which is why the land drills 1.73: 1.73 - 0.08 = 1.65, JST's minimum,
    0.038 over the diagonal, and 1.73 is inside JST's 1.65…1.75 band. The ring
    is (2.43 - 1.73) / 2 = 0.35 mm, over JLC's 0.25 minimum, because
    `header()` grows the pad with the drill.

    Protects: the one thing that makes this connector keyed at all, and that a
    low-tolerance batch takes the header. A 1x4 land would take four evenly
    spaced holes, the part would not go in it, and every net check would still
    pass."""
    d = netlist.current()
    for ref in ("J202", "J311"):
        j = d.connector(ref)
        title, pads, _shared, _outline = footprint_lib.generated(j)
        assert title == "HDR-TH_1X5(5-3)-P3_96MM"
        assert [(p.num, p.x_mm) for p in pads] == [
            ("1", -7.92), ("2", -3.96), ("4", 3.96), ("5", 7.92)]
        assert not any(p.x_mm == 0.0 for p in pads), "the key position is empty"
        assert vh_drill_problems(j) == []
        assert all(p.hole_mm - JLC_HOLE_UNDER_MM == pytest.approx(1.65)
                   for p in pads), "JLC's low side is meant to land on JST's minimum"


def test_the_vh_drill_check_fails_a_hole_that_does_not_take_the_post():
    """⚠️ THE MUTATIONS for the drill check above. JST's own 1.65 -- the figure
    this land carried until 2026-09-21 -- finishes at 1.57 on a low batch,
    under the 1.612 diagonal. And a 2.0 drill is over JST's 1.75: `header()`
    keeps the 0.35 ring at any drill, so the band is what bounds it above."""
    d = netlist.current()
    low = d.replace_connector("J202", hole_mm=1.65)
    problems = vh_drill_problems(low.connector("J202"))
    assert len(problems) == 4 and all("under the post's 1.612 diagonal" in p
                                      for p in problems), problems
    wide = d.replace_connector("J202", hole_mm=2.0)
    problems = vh_drill_problems(wide.connector("J202"))
    assert len(problems) == 4 and all("over JST's 1.75 maximum" in p
                                      for p in problems), problems


def test_the_land_fills_the_key_in_when_the_contacts_are_renumbered():
    """⚠️ THE MUTATION for the test above. Number the same four contacts 1-4 --
    which is what anyone reading 'a 4-way connector' would do -- and the
    generator spaces four holes evenly across a four-position body. The key is
    gone, silently, and only the contact numbers ever said it was there."""
    d = netlist.current()
    filled = d.replace_connector("J202", pins=tuple(
        replace(cp, pin=str(i + 1)) for i, cp in enumerate(d.connector("J202").pins)))
    title, pads, _s, _o = footprint_lib.generated(filled.connector("J202"))
    assert title == "HDR-TH_1X4-P3_96MM"
    assert [p.x_mm for p in pads] == [-5.94, -1.98, 1.98, 5.94]


def test_every_footprint_title_is_safe_for_an_allegro_netlist():
    """EasyEDA's netlist export (.tel) is Allegro's format, which rejects
    '; ! .' and spaces in a footprint name (the editor warns and names the
    parts).  Library titles also carry non-ASCII text ('弯插,P=2mm')."""
    code = next(p.lcsc for p in netlist.current().parts if p.mpn == "AO3400A")
    design, sheet, bs = _emit("OUTPUTS", {code: ("SOT-23-3_L2.9-W1.3 弯插", SOT23)})
    import re
    for d in _docs(sheet)["FOOTPRINT"]:
        title = d[1][1]["title"]
        assert re.fullmatch(r"[A-Za-z0-9_\-()+=,#]+", title), title
