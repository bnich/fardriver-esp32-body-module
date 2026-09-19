"""Footprint documents, and a device's link to one.

EasyEDA Pro refuses a netlist export while any placed part has no footprint:
its schematic DRC calls that fatal.  A device names its footprint by the uuid of
a FOOTPRINT document, so what matters is that the link resolves, that every pin
has a pad, and that a part does not override the link with an empty value.
"""
import json

import pytest

from tools import gauge
from tools.eprj3 import footprints, schematic
from tools.eprj3 import symbols as sym
from tools.eprj3.units import pcb_to_mm
from tools.model import Part


def records(lines):
    """[(header, payload)] from serialised records."""
    out = []
    for line in lines:
        head, _, payload = line.partition("||")
        out.append((json.loads(head), json.loads(payload) if payload else None))
    return out


def documents(text):
    """{docType: [[(header, payload)...], ...]} from a joined document."""
    docs = {}
    cur = None
    for head, payload in records(text.split("|\n")):
        if head["type"] == "DOCHEAD":
            cur = [(head, payload)]
            docs.setdefault(payload["docType"], []).append(cur)
        else:
            cur.append((head, payload))
    return docs


def resistor(ref="R1"):
    return Part(ref, "R-10k", "0805", "GAUGE", "R", ("1", "2"), 0.6, value="10k")


def page():
    return schematic.Page("5c4e0000000005c1", client="0123456789abcdef",
                          epoch_ms=1788000000000)


# --- the footprint document ----------------------------------------------------
def test_two_pad_is_centred_and_pitched():
    a, b = footprints.two_pad(1.9, 1.0, 1.3)
    assert (a.num, b.num) == ("1", "2")
    assert (a.x_mm, b.x_mm) == (-0.95, 0.95)
    assert a.y_mm == b.y_mm == 0


def test_footprint_document_shape_and_units():
    recs = records(footprints.footprint_records(
        "fp01", "R0805_T", footprints.two_pad(1.9, 1.0, 1.3),
        client="0123456789abcdef", epoch_ms=1))
    head = recs[0]
    assert head[0] == {"type": "DOCHEAD"} and head[1]["docType"] == "FOOTPRINT"
    assert head[1]["uuid"] == "fp01"
    pads = [p for h, p in recs if h["type"] == "PAD"]
    assert [p["num"] for p in pads] == ["1", "2"]
    # Stored in PCB units (mil); the land pattern must survive the conversion.
    assert pcb_to_mm(pads[1]["centerX"]) == pytest.approx(0.95, abs=1e-4)
    assert pcb_to_mm(pads[0]["defaultPad"]["height"]) == pytest.approx(1.3, abs=1e-4)
    assert all(p["hole"] is None and p["layerId"] == footprints.TOP_LAYER for p in pads)
    tickets = [h["ticket"] for h, _ in recs[1:]]
    assert tickets == list(range(1, len(tickets) + 1))


def test_repeated_pad_numbers_are_refused():
    pads = (footprints.Pad("1", 0, 0, 1, 1), footprints.Pad("1", 2, 0, 1, 1))
    with pytest.raises(ValueError, match="repeat"):
        footprints.footprint_records("fp", "BAD", pads, client="c", epoch_ms=1)


# --- binding a footprint to a placed symbol ----------------------------------------
def test_pads_must_match_the_symbols_pins():
    p = page()
    symbol = sym.for_part(resistor())
    with pytest.raises(ValueError, match="do not match"):
        p.bind_footprint(symbol, "ONE_PAD", (footprints.Pad("1", 0, 0, 1, 1),))


def test_a_footprint_for_a_symbol_never_placed_is_refused():
    p = page()
    p.bind_footprint(sym.for_part(resistor()), "R0805_T", footprints.two_pad(1.9, 1.0, 1.3))
    with pytest.raises(ValueError, match="never placed"):
        p.library_records()


def test_a_net_flag_never_takes_a_footprint():
    flag = sym.net_flag("GAUGE_FLAG")
    with pytest.raises(ValueError, match="net flag"):
        sym.device_records(flag, "dev", "sym", client="c", epoch_ms=1,
                           footprint_uuid="fp")


# --- the gauge: the one project that binds footprints today ------------------------
@pytest.fixture(scope="module")
def gauge_docs():
    project, _ = gauge.build()
    return documents(project.boards[0].schematic.sheets[0].document())


def test_every_gauge_part_device_names_a_footprint_that_exists(gauge_docs):
    fps = {d[0][1]["uuid"]: d for d in gauge_docs["FOOTPRINT"]}
    parts = [d for d in gauge_docs["DEVICE"]
             if "Global Net Name" not in d[1][1]["attributes"]]
    assert parts, "the gauge has no part device"
    for dev in parts:
        assert dev[1][1]["attributes"]["Footprint"] in fps


def test_library_order_is_footprint_symbol_device_then_page(gauge_docs):
    project, _ = gauge.build()
    text = project.boards[0].schematic.sheets[0].document()
    order = [p["docType"] for h, p in records(text.split("|\n"))
             if h["type"] == "DOCHEAD"]
    ranks = {"FOOTPRINT": 0, "SYMBOL": 1, "DEVICE": 2, "SCH_PAGE": 3}
    assert [ranks[t] for t in order] == sorted(ranks[t] for t in order)


def test_no_part_overrides_its_devices_footprint(gauge_docs):
    """An editor-saved sheet carries a component `Footprint` ATTR only as a
    per-part override.  Writing one with no value could mask the device's."""
    page_recs = gauge_docs["SCH_PAGE"][0]
    assert not [p for h, p in page_recs
                if h["type"] == "ATTR" and p.get("key") == "Footprint"]


# --- one device per real part, one symbol per drawing ----------------------------
def test_parts_bought_as_one_part_share_a_device_and_others_do_not():
    """Every resistor draws the same symbol, but a 10k and a 100k are different
    parts: different LCSC numbers, so different devices.  Two 10k share one."""
    from tools import netlist as nl
    from tools.eprj3.project import Project
    from tools.eprj3.schematic import emit_board
    design = nl.current()
    project = Project("t")
    project.add_board("OUTPUTS")
    sheet = project.boards[0].schematic.sheets[0]
    emit_board(design, "OUTPUTS", sheet)
    docs = documents("|\n".join(sheet.library_records))
    devices = [d[1][1] for d in docs["DEVICE"]]
    by_supplier = {}
    for dev in devices:
        part_no = dev["attributes"].get("Supplier Part")
        if part_no:
            assert dev["attributes"].get("Supplier") == "LCSC"
            assert part_no not in by_supplier, f"{part_no} has two devices"
            by_supplier[part_no] = dev
    drv_lcsc = {p.lcsc for p in design.parts if p.board == "OUTPUTS" and p.lcsc and not p.dnp}
    assert drv_lcsc and drv_lcsc <= set(by_supplier), drv_lcsc - set(by_supplier)
    # the resistors' devices all point at ONE symbol
    r_symbols = {d["attributes"]["Symbol"] for d in devices if d["title"].startswith("R-")}
    assert len(r_symbols) == 1 and len([d for d in devices if d["title"].startswith("R-")]) > 1


def test_each_placed_part_names_the_device_of_its_own_lcsc_part():
    from tools import netlist as nl
    from tools.eprj3.project import Project
    from tools.eprj3.schematic import emit_board
    design = nl.current()
    project = Project("t")
    project.add_board("OUTPUTS")
    sheet = project.boards[0].schematic.sheets[0]
    emit_board(design, "OUTPUTS", sheet)
    docs = documents("|\n".join(sheet.library_records))
    lcsc_of_device = {d[0][1]["uuid"]: d[1][1]["attributes"].get("Supplier Part", "")
                      for d in docs["DEVICE"]}
    page = records(sheet.page_records)
    comp_of = {}
    attrs = {}
    for h, p in page:
        if h["type"] == "ATTR":
            attrs.setdefault(p["parentId"], {})[p["key"]] = p["value"]
    parts = {p.refdes: p for p in design.parts}
    checked = 0
    for cid, a in attrs.items():
        ref = a.get("Designator")
        if ref in parts and parts[ref].lcsc:
            assert lcsc_of_device[a["Device"]] == parts[ref].lcsc, ref
            checked += 1
    assert checked > 10


# --- through-hole pads and pin-header patterns ------------------------------------
def test_a_header_pattern_is_on_the_2_54_grid_with_pin_1_square():
    pads = footprints.header(9, 2.54)
    assert [p.num for p in pads] == [str(i) for i in range(1, 10)]
    assert [round(p.x_mm, 3) for p in pads] == [round(-10.16 + 2.54 * i, 3) for i in range(9)]
    assert all(p.hole_mm == footprints.HEADER_HOLE_MM for p in pads)
    assert pads[0].shape == "RECT" and {p.shape for p in pads[1:]} == {"ELLIPSE"}


def test_a_two_row_header_numbers_across_the_rows_as_headers_do():
    """2 x 25: pin 1 and pin 2 share a column, odd pins in one row."""
    pads = {p.num: p for p in footprints.header(50, 2.54, rows=2)}
    assert pads["1"].x_mm == pads["2"].x_mm and pads["1"].y_mm != pads["2"].y_mm
    assert pads["3"].x_mm - pads["1"].x_mm == pytest.approx(2.54)
    assert {p.y_mm for n, p in pads.items() if int(n) % 2} == {pads["1"].y_mm}


def test_through_hole_pads_are_on_every_layer_and_drilled():
    recs = records(footprints.footprint_records(
        "fpH", "HDR", footprints.header(3, 5.08), client="0123456789abcdef", epoch_ms=1))
    pads = [p for h, p in recs if h["type"] == "PAD"]
    assert all(p["layerId"] == footprints.MULTI_LAYER for p in pads)
    assert all(p["hole"]["holeType"] == "ROUND" for p in pads)
    assert pcb_to_mm(pads[1]["centerX"] - pads[0]["centerX"]) == pytest.approx(5.08, abs=1e-3)
