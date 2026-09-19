"""THE KEY TEST: re-derive every board's nets from the emitted BYTES and
compare them, net by net and pin by pin, with `netlist.current()`.

The mechanism here is "the file parses".  The job is "the right pins are on the
right net".  So nothing below asks the emitter what it meant: a reader written
independently of it parses the sheet, transforms every symbol pin by its
component's placement (spec §9, by trigonometry, not by the emitter's lookup
table), unions `LINE` endpoints per `lineGroup`, then names each conductor from
the net flags touching it (`Global Net Name`) and from the wires' `NET`
attributes, and merges conductors that share a name.  The result must equal
each board's slice of the netlist exactly -- nothing extra, nothing missing.

The reader was calibrated before it was trusted: run on the official example's
sheet it yields VCC = {R1.2, R2.2, C1.2, L1.2} and GND = {R1.1, R2.1, C1.1,
L1.1}, and on the spec's two-resistor example SIG1 = {R1.2, R2.1}.  Those files
are vendor material and are not in this repository; the negative controls at
the bottom are what keep the reader honest here -- a moved component and a
renamed flag must each break the comparison.

The helpers in this module (`parse_records`, `derive_nets`, ...) are imported
by the other `.eprj3` test modules.
"""
import collections
import json
import math
from dataclasses import dataclass, field, replace

import pytest

from tools import netlist
from tools.board_params import STACK_ORDER
from tools.eprj3 import placement, schematic
from tools.eprj3 import symbols as sym
from tools.eprj3.project import Project

DESIGN = netlist.current()
_DEC = json.JSONDecoder()


# ============================================================================
# The independent reader
# ============================================================================
from tools.eprj3.reader import (  # noqa: E402,F401 -- re-exported for the other tests
    Derived, ReadError, Sheet, derive_nets, diff, documents, expected_floating,
    netlist_slice, parse_records, read_sheet, reserialise, transform,
)


# ============================================================================
# Building the sheets
# ============================================================================
def build_sheets(design=DESIGN, naming=None):
    """board -> (document text, BoardSheet)."""
    project = Project.for_stack("test-schematic")
    ids = schematic.project_unique_ids(design, STACK_ORDER)
    out = {}
    for board in project.boards:
        sheet = board.schematic.sheets[0]
        bs = schematic.emit_board(design, board.title, sheet, naming=naming,
                                  unique_ids=ids)
        out[board.title] = (sheet.document(), bs)
    return out


@pytest.fixture(scope="module")
def sheets_by_mode():
    return {mode: build_sheets(naming=mode) for mode in schematic.NAMINGS}


# ============================================================================
# ⭐ The key test
# ============================================================================
@pytest.mark.parametrize("board", STACK_ORDER)
@pytest.mark.parametrize("mode", ["both", "flag", "wire"])
def test_derived_nets_equal_the_netlist_slice(sheets_by_mode, mode, board):
    text, _ = sheets_by_mode[mode][board]
    derived = derive_nets(text)
    assert derived.conflicts == []
    assert derived.unnamed == []
    assert derived.dangling_flags == []
    want = netlist_slice(DESIGN, board)
    assert derived.nets == want, "\n".join(diff(derived.nets, want))


@pytest.mark.parametrize("board", STACK_ORDER)
def test_the_naming_switch_is_honoured_at_call_time(monkeypatch, board):
    # The module-level switch, not only the keyword, must drive the output.
    for mode in ("flag", "wire"):
        monkeypatch.setattr(schematic, "NAMING", mode)
        text, bs = build_sheets()[board]
        assert bs.naming == mode
        sheet = read_sheet(text)
        flags = [c for c in sheet.components if sheet.is_flag(c)]
        names = [sheet.attr(w, "NET") for w in sheet.wires]
        if mode == "flag":
            assert flags and all(n == "" for n in names)
        else:
            assert not flags and all(names)
        assert derive_nets(text).nets == netlist_slice(DESIGN, board)


@pytest.mark.parametrize("board", STACK_ORDER)
def test_unconnected_pins_are_exactly_nc_and_unused_cavities(sheets_by_mode,
                                                           board):
    text, _ = sheets_by_mode["both"][board]
    assert derive_nets(text).floating == expected_floating(DESIGN, board)


@pytest.mark.parametrize("board", STACK_ORDER)
def test_every_part_and_connector_of_the_board_is_placed(sheets_by_mode,
                                                        board):
    text, _ = sheets_by_mode["both"][board]
    sheet = read_sheet(text)
    placed = sorted(sheet.attr(c, "Designator") for c in sheet.components
                    if not sheet.is_flag(c))
    assert placed == sorted(schematic.board_refs(DESIGN, board))


# ============================================================================
# Geometry invariants
# ============================================================================
@pytest.mark.parametrize("board", STACK_ORDER)
def test_no_anchor_collisions(sheets_by_mode, board):
    """No coordinate point carries two part pins, two flags or two wires --
    so no two different nets can share one, and no `nc` pin can land on a
    wire by accident."""
    text, _ = sheets_by_mode["both"][board]
    sheet = read_sheet(text)
    pins = collections.defaultdict(list)
    flags = collections.defaultdict(list)
    wires = collections.defaultdict(set)
    for cid in sheet.components:
        bucket = flags if sheet.is_flag(cid) else pins
        for point, number in sheet.anchors(cid):
            bucket[point].append((sheet.attr(cid, "Designator"), number))
    for ln in sheet.lines:
        for pt in ((ln["startX"], ln["startY"]), (ln["endX"], ln["endY"])):
            wires[(float(pt[0]), float(pt[1]))].add(ln["lineGroup"])
    assert [v for v in pins.values() if len(v) > 1] == []
    assert [v for v in flags.values() if len(v) > 1] == []
    assert [v for v in wires.values() if len(v) > 1] == []
    floating = expected_floating(DESIGN, board)
    for point, owners in pins.items():
        if set(owners) <= floating:
            assert point not in wires and point not in flags, owners


@pytest.mark.parametrize("board", STACK_ORDER)
def test_every_anchor_and_endpoint_is_an_integer_on_the_grid(sheets_by_mode,
                                                            board):
    text, _ = sheets_by_mode["both"][board]
    sheet = read_sheet(text)
    points = [pt for cid in sheet.components for pt, _ in sheet.anchors(cid)]
    for ln in sheet.lines:
        points += [(ln["startX"], ln["startY"]), (ln["endX"], ln["endY"])]
    for c in sheet.components.values():
        points.append((c["x"], c["y"]))
    off = [p for p in points
           if any(v != int(v) or int(v) % sym.GRID for v in p)]
    assert off == []
    for ln in sheet.lines:
        for key in ("startX", "startY", "endX", "endY"):
            assert isinstance(ln[key], int)


@pytest.mark.parametrize("board", STACK_ORDER)
def test_every_stub_is_one_line_from_a_pin_to_its_flag(sheets_by_mode, board):
    text, _ = sheets_by_mode["both"][board]
    sheet = read_sheet(text)
    pin_at, flag_at = {}, {}
    for cid in sheet.components:
        for point, _ in sheet.anchors(cid):
            if sheet.is_flag(cid):
                flag_at[point] = (cid, sheet.global_net_name(cid))
            else:
                pin_at[point] = cid
    per_wire = collections.defaultdict(list)
    for ln in sheet.lines:
        per_wire[ln["lineGroup"]].append(ln)
    assert set(per_wire) == sheet.wires
    for wid, lines in per_wire.items():
        assert len(lines) == 1
        ln = lines[0]
        a = (float(ln["startX"]), float(ln["startY"]))
        b = (float(ln["endX"]), float(ln["endY"]))
        assert a[1] == b[1] and abs(a[0] - b[0]) == placement.STUB
        assert a in pin_at and b in flag_at
        # Both names agree: a flag touching a wire renames it anyway.
        assert sheet.attr(wid, "NET") == flag_at[b][1]


@pytest.mark.parametrize("board", STACK_ORDER)
def test_placement_cells_never_overlap(sheets_by_mode, board):
    _, bs = sheets_by_mode["both"][board]
    assert placement.overlaps(bs.layout) == []
    for x, y in bs.layout.origins.values():
        assert x % sym.GRID == 0 and y % sym.GRID == 0


@pytest.mark.parametrize("board", STACK_ORDER)
def test_content_is_in_the_sheet_body_quadrant(sheets_by_mode, board):
    # (0, 0) is the sheet's bottom-left corner and +Y points DOWN (§4.2).
    _, bs = sheets_by_mode["both"][board]
    x1, y1, x2, y2 = bs.layout.extent
    assert x1 > 0 and y2 < 0


@pytest.mark.parametrize("board", STACK_ORDER)
def test_connectors_run_along_the_left_edge(sheets_by_mode, board):
    _, bs = sheets_by_mode["both"][board]
    conns = [i.ref for i in bs.items if i.is_connector]
    parts = [i.ref for i in bs.items if not i.is_connector]
    right_of_connectors = max(bs.layout.cells[r][2] for r in conns)
    assert right_of_connectors < min(bs.layout.cells[r][0] for r in parts)


def test_two_pin_parts_group_with_the_anchor_they_serve():
    # R110 (gate pull-up) and C107 hang off Q101's gate node D13_GATE.
    items = schematic.board_items(DESIGN, "POWER")
    group = next(g for g in placement.groups(items) if g[0] == "Q101")
    assert {"R110", "C107", "D102"} <= set(group)


# ============================================================================
# The file
# ============================================================================
@pytest.mark.parametrize("board", STACK_ORDER)
def test_round_trip_is_byte_identical(sheets_by_mode, board):
    for mode in schematic.NAMINGS:
        text, _ = sheets_by_mode[mode][board]
        assert reserialise(parse_records(text)) == text


@pytest.mark.parametrize("board", STACK_ORDER)
def test_self_validator_invariants(sheets_by_mode, board):
    """Spec §11.1: ids and tickets unique per document, header shapes, no
    '||' in a header, bytes as the editor writes them."""
    text, _ = sheets_by_mode["both"][board]
    assert not text.startswith("﻿") and "\r" not in text
    assert not text.endswith("\n") and not text.endswith("|")
    records = parse_records(text)
    for head, _, raw in records:
        assert "||" not in raw[:raw.index("||")]
        assert set(head) in ({"type"}, {"type", "ticket", "id"})
    for d in documents(records):
        tickets = [h["ticket"] for h, _ in d["records"]]
        ids = [h["id"] for h, _ in d["records"]]
        assert len(tickets) == len(set(tickets)), d["uuid"]
        assert len(ids) == len(set(ids)), d["uuid"]
    kinds = [d["docType"] for d in documents(records)]
    assert kinds[-1] == "SCH_PAGE" and kinds.count("SCH_PAGE") == 1
    assert set(kinds[:-1]) <= {"FOOTPRINT", "SYMBOL", "DEVICE"}


@pytest.mark.parametrize("board", STACK_ORDER)
def test_every_component_names_an_embedded_symbol_and_device(sheets_by_mode,
                                                             board):
    text, _ = sheets_by_mode["both"][board]
    sheet = read_sheet(text)
    for cid, c in sheet.components.items():
        assert sheet.attr(cid, "Symbol") in sheet.symbols
        dev = sheet.attr(cid, "Device")
        assert dev in sheet.devices
        assert sheet.devices[dev]["Symbol"] == sheet.attr(cid, "Symbol")
        if not sheet.is_flag(cid):
            assert json.loads(c["attrs"]["DeviceName"])["uuid"] == dev
            assert sheet.attr(cid, "Unique ID").startswith("gge")


@pytest.mark.parametrize("board", STACK_ORDER)
def test_one_flag_symbol_per_net_name(sheets_by_mode, board):
    text, _ = sheets_by_mode["both"][board]
    sheet = read_sheet(text)
    flag_devices = [a["Global Net Name"] for a in sheet.devices.values()
                    if "Global Net Name" in a]
    assert sorted(flag_devices) == sorted(set(flag_devices))
    assert set(flag_devices) == set(netlist_slice(DESIGN, board))


def test_flag_component_carries_the_exemplified_attrs(sheets_by_mode):
    text, _ = sheets_by_mode["both"]["POWER"]
    sheet = read_sheet(text)
    flag = next(c for c in sheet.components if sheet.is_flag(c))
    assert set(sheet.attrs[flag]) == {"Symbol", "Device", "Relevance",
                                      "Name", "Global Net Name"}
    assert sheet.attr(flag, "Name") == sheet.attr(flag, "Global Net Name")
    assert sheet.attrs[flag]["Name"]["valueVisible"] is True


def test_part_attrs_carry_catalogue_data(sheets_by_mode):
    text, _ = sheets_by_mode["both"]["POWER"]
    sheet = read_sheet(text)
    q = next(c for c in sheet.components
             if sheet.attr(c, "Designator") == "Q101")
    part = DESIGN.part("Q101")
    assert sheet.attr(q, "Manufacturer Part") == part.mpn
    assert sheet.attr(q, "Value") == part.value
    assert sheet.attr(q, "Description") == part.package
    assert sheet.attr(q, "Name") == schematic.part_name(part)


def test_dnp_is_marked():
    dnp = [p for p in DESIGN.parts if p.dnp]
    if not dnp:
        pytest.skip("no DNP part in the design")
    part = dnp[0]
    text, _ = build_sheets()[part.board]
    sheet = read_sheet(text)
    c = next(c for c in sheet.components
             if sheet.attr(c, "Designator") == part.refdes)
    assert sheet.attr(c, "DNP") == "yes"
    assert sheet.attr(c, "Name").endswith("(DNP)")


def test_emission_is_deterministic():
    a = build_sheets()
    b = build_sheets()
    assert {k: v[0] for k, v in a.items()} == {k: v[0] for k, v in b.items()}


# ============================================================================
# Net names: refused, never rewritten
# ============================================================================
def test_every_netlist_name_is_valid_and_returned_unchanged():
    for net in DESIGN.nets:
        assert schematic.validate_net_name(net.name) == net.name


@pytest.mark.parametrize("bad", ["gnd", "V 12", "V$1", "VÖ", "", "V12\t",
                                 "NET(1)"])
def test_bad_net_names_are_refused(bad):
    with pytest.raises(ValueError):
        schematic.validate_net_name(bad)


def test_emit_refuses_a_design_with_a_bad_net_name():
    bad = replace(DESIGN, nets=tuple(
        replace(n, name="k sw") if n.name == "KSW" else n
        for n in DESIGN.nets))
    project = Project.for_stack("test-bad-name")
    sheet = project.boards[0].schematic.sheets[0]
    with pytest.raises(ValueError, match="k sw"):
        schematic.emit_board(bad, "POWER", sheet)
    assert sheet.page_records == ()      # nothing half-written


def test_unknown_naming_mode_is_refused():
    with pytest.raises(ValueError):
        schematic.naming_mode("labels")


# ============================================================================
# The placement transform
# ============================================================================
@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("mirror", [False, True])
def test_place_point_matches_the_spec_formula(rotation, mirror):
    for px, py in ((-20, 0), (20, 0), (30, -10), (-40, 70)):
        got = schematic.place_point(px, py, 400, -400, rotation, mirror)
        assert got == transform(px, py, 400, -400, rotation, mirror)


# ============================================================================
# Negative controls: the key test must be able to FAIL
# ============================================================================
def _mutate(text, predicate, change):
    out = []
    for head, payload, raw in parse_records(text):
        if predicate(head, payload):
            payload = change(dict(payload))
        out.append((head, payload, raw))
    return reserialise(out)


def test_control_a_part_moved_one_grid_step_breaks_the_comparison():
    text, _ = build_sheets()["POWER"]
    sheet = read_sheet(text)
    q = next(c for c in sheet.components
             if sheet.attr(c, "Designator") == "Q101")
    moved = _mutate(text, lambda h, p: h.get("id") == q,
                    lambda p: {**p, "x": p["x"] + 10})
    derived = derive_nets(moved)
    assert derived.nets != netlist_slice(DESIGN, "POWER")
    assert {("Q101", "G"), ("Q101", "D"), ("Q101", "S")} <= derived.floating


def test_control_a_renamed_flag_breaks_the_comparison():
    text, _ = build_sheets(naming="flag")["POWER"]
    renamed = _mutate(
        text,
        lambda h, p: (h["type"] == "ATTR" and p and p["key"] ==
                      "Global Net Name" and p["value"] == "KSW"),
        lambda p: {**p, "value": "KSW2"})
    assert derive_nets(renamed).nets != netlist_slice(DESIGN, "POWER")


def test_control_a_flag_and_wire_that_disagree_are_a_conflict():
    text, _ = build_sheets(naming="both")["POWER"]
    clash = _mutate(
        text,
        lambda h, p: (h["type"] == "ATTR" and p and p["key"] == "NET"
                      and p["value"] == "KSW"),
        lambda p: {**p, "value": "KSW_OTHER"})
    assert derive_nets(clash).conflicts


def test_control_a_rotation_v2_style_detaches_the_pins():
    # Rewrite every symbol pin's rotation the V2 way (+180).  Anchors do not
    # move -- so connectivity survives -- but the drawn pin no longer reaches
    # the body, which the symbol guard reports.  (The guard, not the netlist,
    # is what catches this class.)
    s = sym.for_part(DESIGN.part("R110"))
    flipped = replace(s, pins=tuple(replace(p, rotation=(p.rotation + 180)
                                            % 360) for p in s.pins))
    assert sym.check_symbol(flipped)


def test_control_derivation_of_a_hand_built_pair():
    # Two resistors wired by one line between their anchors, named by the
    # wire alone: exactly the spec's verified §10 construction, rebuilt here
    # through the emitter's own Page so the reader is exercised on it.
    project = Project("test-pair")
    project.add_board("PAIR")
    sheet = project.boards[0].schematic.sheets[0]
    page = schematic.Page(sheet.uuid, client=sheet.client,
                          epoch_ms=sheet.epoch_ms)
    r = sym._part_symbol("R", ("1", "2"))
    placed = []
    for ref, x in (("R1", 400), ("R2", 500)):
        item = placement.Item(ref, r, {}, ref, "10k")
        placed.append(schematic.place_part(page, item, x, -400, "gge" + ref))
    a, b = placed[0].anchors["2"], placed[1].anchors["1"]
    assert (a, b) == ((420, -400), (480, -400))    # the spec's §10 numbers
    page.wire([(a[0], a[1], b[0], b[1])], role=("sig",), net="SIG1",
              label=(450, -400, None), show=True)
    sheet.library_records = page.library_records()
    sheet.page_records = page.page_records()
    derived = derive_nets(sheet.document())
    assert derived.nets == {"SIG1": {("R1", "2"), ("R2", "1")}}
    assert derived.floating == {("R1", "1"), ("R2", "2")}
