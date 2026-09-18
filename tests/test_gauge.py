"""The gauge project: four experiments, each built exactly as specified.

The gauge only answers the owner's question if each experiment isolates ONE
mechanism.  An experiment 2 whose stubs happened to touch would test geometry,
not wire names, and its "yes" would switch the whole build to a mechanism that
does not work.  So each experiment's construction is asserted from the emitted
bytes: which records exist, what they are named, and what geometry is shared.
"""
import collections
from pathlib import Path

import pytest

from tools import gauge
from tools.eprj3 import placement
from tests.test_schematic import (derive_nets, parse_records, read_sheet,
                                  reserialise)

EXP = {e.number: e for e in gauge.EXPERIMENTS}


@pytest.fixture(scope="module")
def sheet_text():
    project, _ = gauge.build()
    return project.boards[0].schematic.sheets[0].document()


@pytest.fixture(scope="module")
def sheet(sheet_text):
    return read_sheet(sheet_text)


def by_ref(sheet):
    return {sheet.attr(c, "Designator"): c for c in sheet.components
            if not sheet.is_flag(c)}


def anchor(sheet, ref, pin):
    cid = by_ref(sheet)[ref]
    return dict((num, pt) for pt, num in sheet.anchors(cid))[pin]


def wires_touching(sheet, point):
    """wire id -> its lines, for every wire with an endpoint at `point`."""
    lines = collections.defaultdict(list)
    for ln in sheet.lines:
        lines[ln["lineGroup"]].append(ln)
    out = {}
    for wid, lns in lines.items():
        ends = {(float(ln[k + "X"]), float(ln[k + "Y"]))
                for ln in lns for k in ("start", "end")}
        if point in ends:
            out[wid] = lns
    return out


def points_of(lines):
    return {(float(ln[k + "X"]), float(ln[k + "Y"]))
            for ln in lines for k in ("start", "end")}


def flags_at(sheet, point):
    return [sheet.global_net_name(c) for c in sheet.components
            if sheet.is_flag(c) and any(pt == point for pt, _ in
                                        sheet.anchors(c))]


def stub(sheet, ref, pin):
    """The one wire on a pin, its single line, and the stub's outer end."""
    a = anchor(sheet, ref, pin)
    touching = wires_touching(sheet, a)
    assert len(touching) == 1, (ref, pin, touching)
    (wid, lines), = touching.items()
    assert len(lines) == 1
    outer = (points_of(lines) - {a}).pop()
    return wid, lines, a, outer


# --- the whole sheet --------------------------------------------------------
def test_one_board_one_sheet_eight_resistors():
    project, _ = gauge.build()
    assert [b.title for b in project.boards] == [gauge.BOARD]
    assert len(project.boards[0].schematic.sheets) == 1
    sheet = read_sheet(project.boards[0].schematic.sheets[0].document())
    assert sorted(by_ref(sheet)) == [f"R{i}" for i in range(1, 9)]


def test_exactly_four_experiments_and_four_net_names(sheet):
    assert [e.number for e in gauge.EXPERIMENTS] == [1, 2, 3, 4]
    names = {sheet.attr(w, "NET") for w in sheet.wires} - {""}
    names |= {sheet.global_net_name(c) for c in sheet.components
              if sheet.is_flag(c)}
    assert names == {"GAUGE_GEOM", "GAUGE_WIRE", "GAUGE_FLAG", "GAUGE_BOTH"}


def test_the_free_ends_are_unconnected(sheet_text):
    derived = derive_nets(sheet_text)
    assert derived.floating == {(e.left, "1") for e in gauge.EXPERIMENTS} | \
        {(e.right, "2") for e in gauge.EXPERIMENTS}


def test_each_pair_joins_under_its_own_name_in_our_model(sheet_text):
    derived = derive_nets(sheet_text)
    assert derived.conflicts == [] and derived.unnamed == []
    assert derived.nets == {e.net: {(e.left, "2"), (e.right, "1")}
                            for e in gauge.EXPERIMENTS}


# --- experiment by experiment -------------------------------------------------
def test_experiment_1_one_wire_drawn_anchor_to_anchor(sheet):
    e = EXP[1]
    a, b = anchor(sheet, e.left, "2"), anchor(sheet, e.right, "1")
    touching = wires_touching(sheet, a)
    assert list(touching) == list(wires_touching(sheet, b))   # one wire, both
    (wid, lines), = touching.items()
    assert len(lines) == 1 and points_of(lines) == {a, b}
    assert sheet.attr(wid, "NET") == "GAUGE_GEOM"
    assert flags_at(sheet, a) == [] and flags_at(sheet, b) == []


def test_experiment_2_named_stubs_only_no_shared_geometry(sheet):
    e = EXP[2]
    w1, l1, _, out1 = stub(sheet, e.left, "2")
    w2, l2, _, out2 = stub(sheet, e.right, "1")
    assert w1 != w2
    assert points_of(l1).isdisjoint(points_of(l2))
    assert sheet.attr(w1, "NET") == sheet.attr(w2, "NET") == "GAUGE_WIRE"
    assert flags_at(sheet, out1) == [] and flags_at(sheet, out2) == []
    # With no flag, the wire's own name is the visible label.
    assert sheet.attrs[w1]["NET"]["valueVisible"] is True


def test_experiment_3_flags_only_empty_wire_names(sheet):
    e = EXP[3]
    w1, l1, _, out1 = stub(sheet, e.left, "2")
    w2, l2, _, out2 = stub(sheet, e.right, "1")
    assert w1 != w2
    assert points_of(l1).isdisjoint(points_of(l2))
    assert sheet.attr(w1, "NET") == sheet.attr(w2, "NET") == ""
    assert flags_at(sheet, out1) == flags_at(sheet, out2) == ["GAUGE_FLAG"]


def test_experiment_4_is_the_production_connection(sheet):
    e = EXP[4]
    w1, l1, _, out1 = stub(sheet, e.left, "2")
    w2, l2, _, out2 = stub(sheet, e.right, "1")
    assert w1 != w2
    assert points_of(l1).isdisjoint(points_of(l2))
    assert sheet.attr(w1, "NET") == sheet.attr(w2, "NET") == "GAUGE_BOTH"
    assert flags_at(sheet, out1) == flags_at(sheet, out2) == ["GAUGE_BOTH"]
    # The production stub: one line, STUB long, horizontal, name hidden
    # because the flag shows it.
    for lines, wid in ((l1, w1), (l2, w2)):
        ln = lines[0]
        assert ln["startY"] == ln["endY"]
        assert abs(ln["endX"] - ln["startX"]) == placement.STUB
        assert sheet.attrs[wid]["NET"]["valueVisible"] is False


def test_experiments_use_the_mechanisms_they_claim():
    assert [e.mechanism for e in gauge.EXPERIMENTS] == \
        ["geometry", "wire", "flag", "both"]


def test_no_two_experiments_share_a_point(sheet):
    """Each experiment's points -- its resistors' anchors, every line of every
    wire on them, every flag at those lines' ends -- are disjoint from every
    other experiment's, so no experiment can join through another."""
    points = {}
    for e in gauge.EXPERIMENTS:
        pts = set()
        for ref in (e.left, e.right):
            for pt, _ in sheet.anchors(by_ref(sheet)[ref]):
                pts.add(pt)
                for lines in wires_touching(sheet, pt).values():
                    pts |= points_of(lines)
        for c in sheet.components:
            if sheet.is_flag(c):
                pts |= {pt for pt, _ in sheet.anchors(c) if pt in pts}
        points[e.number] = pts
    for a in points:
        for b in points:
            if a < b:
                assert points[a].isdisjoint(points[b]), (a, b)
    every_line_point = points_of(sheet.lines)
    assert every_line_point <= set().union(*points.values())


# --- the files ----------------------------------------------------------------
def test_gauge_round_trips_and_is_deterministic(sheet_text):
    assert reserialise(parse_records(sheet_text)) == sheet_text
    project, _ = gauge.build()
    assert project.boards[0].schematic.sheets[0].document() == sheet_text


def test_main_writes_project_zip_and_instructions(tmp_path, capsys):
    assert gauge.main(["--out", str(tmp_path)]) == 0
    assert (tmp_path / gauge.PROJECT_NAME /
            f"{gauge.PROJECT_NAME}.eprj3").is_file()
    assert (tmp_path / f"{gauge.PROJECT_NAME}.zip").is_file()
    notes = (tmp_path / gauge.INSTRUCTIONS).read_text(encoding="utf-8")
    for e in gauge.EXPERIMENTS:
        assert e.net in notes
    # The decision table names every outcome and the switch it sets.
    for phrase in ('`NAMING = "flag"`', '`NAMING = "wire"`',
                   '(`NAMING = "both"`)', "draw real wires",
                   "tools/eprj3/schematic.py", "copy any"):
        assert phrase in notes, phrase
    assert "4 experiments" in capsys.readouterr().out


def test_two_gauge_runs_are_byte_identical(tmp_path):
    def tree(root):
        return {p.relative_to(root).as_posix(): p.read_bytes()
                for p in sorted(Path(root).rglob("*")) if p.is_file()}
    assert gauge.main(["--out", str(tmp_path / "a")]) == 0
    assert gauge.main(["--out", str(tmp_path / "b")]) == 0
    assert tree(tmp_path / "a") == tree(tmp_path / "b")
