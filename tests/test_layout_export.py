"""`tools/layout_export.py` and `tools/layout_hooks.py`: the body module
described to `pcb-layout-tools`.

The export must be DETERMINISTIC -- the same project gives the same bytes, so
a diff of `layout.yaml` is a diff of the design -- and it must be a document
pcblayout's own loader accepts.  The second half runs only where pcblayout is
installed (the body module does not depend on it).
"""
from __future__ import annotations

import importlib.util
import json
import shutil

import pytest

from tools import eprj2, layout_export, layout_hooks, place, route, soft_start
from tests.test_place import OWNER, _stream, design, ix, template  # noqa: F401 (fixtures)

#: The copper layer table the editor writes on a four-layer board, plus one
#: layer that is not copper -- which the export must leave out -- and one
#: copper layer the board does not use.
LAYERS = ((1, "TOP", "Top Layer", True), (2, "BOTTOM", "Bottom Layer", True),
          (3, "TOP_SILK", "Top Silkscreen Layer", True), (15, "SIGNAL", "Inner1", True),
          (16, "SIGNAL", "Inner2", True), (17, "SIGNAL", "Inner3", False))


def _with_layers(text: str) -> str:
    """The synthetic stream with each PCB document's LAYER table, where the
    editor puts it: after the document's META."""
    out, in_pcb = [], False
    for h, p in eprj2.split_records(text):
        out.append((h, p))
        if h["type"] == "DOCHEAD":
            in_pcb = json.loads(p).get("docType") == "PCB"
        elif h["type"] == "META" and in_pcb:
            for lid, kind, name, use in LAYERS:
                out.append(({"type": "LAYER", "id": json.dumps(["LAYER", lid],
                                                               separators=(",", ":"))},
                            eprj2._compact({"layerId": lid, "layerType": kind,
                                            "layerName": name, "use": use})))
    return eprj2.join(out)


def _project(tmp_path_factory, template, design, ix, omit=()):  # noqa: F811
    path = tmp_path_factory.mktemp("export") / "revv1-module.eprj2"
    eprj2.write(template, path, _with_layers(_stream(design, ix, omit=omit)), {"boards": {}},
                "revv1-module", owner=OWNER)
    return path


@pytest.fixture(scope="module")
def project_path(tmp_path_factory, template, design, ix):  # noqa: F811
    return _project(tmp_path_factory, template, design, ix)


@pytest.fixture(scope="module")
def exported(project_path, design):  # noqa: F811
    return layout_export.export(place.load(project_path), design)


# --- the export ---------------------------------------------------------------------
def test_the_export_is_deterministic(project_path, design, exported):  # noqa: F811
    again = layout_export.export(place.load(project_path), design)
    assert again.text() == exported.text()
    assert again.notes == exported.notes


def test_every_board_has_its_four_copper_layers_in_stack_order(exported):
    names = [[layer["name"] for layer in b["layers"]] for b in exported.doc["boards"]]
    assert names == [["Top Layer", "Inner1", "Inner2", "Bottom Layer"]] * 4


def test_every_netclass_figure_is_routes(exported):
    """One fact, one home: a width or a clearance typed a second time here
    would drift from the figure `tools/route.py` writes into the editor."""
    table = {c.name: c for c in layout_export.CLASSES}
    for row in exported.doc["netclasses"]:
        c = table[row["name"]]
        assert (row["min_width_mm"], row["clearance_mm"]) == \
            (c.width_mm, {"default": c.clearance_mm})


def test_class_copper_is_on_the_heavy_classes_and_no_other(exported):
    """`pcbl route copper` lays the classes `route.py --heavy` lays -- the list
    is `route.heavy_classes`, never typed here."""
    laid = {row["name"] for row in exported.doc["netclasses"] if row.get("class_copper")}
    used = {row["name"] for row in exported.doc["netclasses"]}
    assert laid == {c.name for c in route.heavy_classes()} & used
    assert laid, "no class is laid by rule"


def test_every_board_states_routes_pour_inset(exported):
    assert {b["pour_inset_mm"] for b in exported.doc["boards"]} == {route.POUR_INSET}


def test_the_cable_states_no_gap(exported):
    """The loom's height is the stack's to derive (`stack.cable_gap`)."""
    cables = [c for c in exported.doc["constraints"] if c["kind"] == "cable"]
    assert cables and all("gap_mm" not in c for c in cables)


def test_the_twin_is_routes_return_rule(exported, ix):  # noqa: F811
    """The ground twin is stated where `route._return_twin` would lay one: the
    board that makes the bus, each ground reaching the converter and the
    contact it leaves by, over those and the bus parts on that ground."""
    twins = [c for c in exported.doc["constraints"] if c["kind"] == "twin"]
    assert [(t["board"], t["net"], t["beside"]) for t in twins] == [
        ("POWER", "GND", route.PWR12.name)]
    src, away, parts = place.v12_output(ix, "POWER")
    [t] = twins
    assert t["parts"][:2] == [src, away]
    assert set(t["parts"][2:]) == {r for r in parts if "GND" in ix.items[r].nets} - {away}
    assert len(set(t["parts"])) == len(t["parts"])
    assert "BASEPLATE" not in {t["net"] for t in twins}


def test_the_hv_region_takes_the_non_plane_grounds_as_neutral(exported, ix):  # noqa: F811
    """Ground is on both sides of POWER's partition (`place.hv_pins`); a ground
    no plane carries -- `BASEPLATE` -- must be named, or C203/C204 read as
    straddlers and are turned round."""
    [region] = [c for c in exported.doc["constraints"] if c["kind"] == "region"]
    assert region["board"] == "POWER" and region["classes"] == [route.HV.name]
    assert region["neutral_nets"] == ["BASEPLATE"]


def _net_row(exported, name):
    return next(n for n in exported.doc["nets"] if n["name"] == name)


def test_a_net_two_classes_on_two_boards_states_each(exported, ix):  # noqa: F811
    """`V12` is PWR12 where the brick and the driver line carry it and RAIL
    where it is one trace to a converter.  The row states every board's class
    as `route.net_class` gives it -- never one class everywhere, and never a
    note in place of the statement."""
    row = _net_row(exported, "V12")
    boards = sorted({ix.items[r].board for r, _ in ix.members["V12"] if r in ix.items})
    per = {b: route.net_class(ix, b, "V12").name for b in boards}
    assert len(set(per.values())) > 1           # the case is real on this netlist
    stated = {b: row.get("class_by_board", {}).get(b, row["net_class"]) for b in boards}
    assert stated == per
    assert not any(n.startswith("class: ") for n in exported.notes)


def test_a_net_one_class_everywhere_names_no_board(exported):
    assert "class_by_board" not in _net_row(exported, "GND")


def test_supply_marks_the_grounds_and_the_rails_and_nothing_else(exported, ix):  # noqa: F811
    """`supply` is what check 20 does not measure (`place.routed_nets`): the
    grounds and every net feeding a part's SUPPLY pin."""
    marked = {n["name"] for n in exported.doc["nets"] if n.get("supply")}
    assert marked == (ix.gnd | ix.rails) & set(ix.members)
    assert "BASEPLATE" in marked and "V5AUX" in marked
    assert "EN" not in marked


def test_parts_and_nets_are_in_the_netlists_order(exported, ix):  # noqa: F811
    """The order is a fact of the design: pcbl breaks a tie by stated order,
    and legacy meets parts and nets in the netlist's.  A sorted list places
    tied parts differently from the placer the export is held to."""
    parts = [p["refdes"] for p in exported.doc["parts"]]
    assert parts == [r for r in ix.items if r in set(parts)]
    assert parts != sorted(parts)               # the case is real on this netlist
    nets = [n["name"] for n in exported.doc["nets"]]
    assert nets == list(ix.members)


def test_a_nets_order_is_stated_only_where_it_differs_from_the_parts(exported, ix):  # noqa: F811
    """`order` is the netlist's order of a net's members (`ix.members`), the
    order legacy lends a band in; it is written only where part order would
    say otherwise, and always names exactly the net's exported members."""
    at = {p["refdes"]: i for i, p in enumerate(exported.doc["parts"])}
    stated = 0
    for row in exported.doc["nets"]:
        met = list(dict.fromkeys(r for r, _ in ix.members[row["name"]] if r in at))
        if "order" in row:
            stated += 1
            assert row["order"] == met
            assert met != sorted(met, key=at.__getitem__)
        else:
            assert met == sorted(met, key=at.__getitem__)
    assert stated                               # the case is real on this netlist


def test_the_brake_corridor_is_stated_from_legacys_own_rule(exported, ix):  # noqa: F811
    """Check 14's brake clause, as a generic `corridor`: the path from the
    brake terminal to the module, the I2C pull-ups kept `CORRIDOR_CLEAR` off
    it -- every figure read from `place`, never typed here."""
    rows = [c for c in exported.doc["constraints"] if c["kind"] == "corridor"]
    [module] = [it for it in ix.on("LOGIC") if it.kind == "MODULE"]
    term = place.brake_terminal(ix, "LOGIC", module.refdes)
    assert rows == [{"kind": "corridor", "name": f"{term}-{module.refdes}-BRAKE",
                     "ends": [term, module.refdes],
                     "parts": list(place.i2c_pullups(ix, "LOGIC")),
                     "clear_mm": place.CORRIDOR_CLEAR,
                     "reason": rows[0]["reason"]}]
    assert rows[0]["parts"]


def test_a_constraint_naming_a_part_the_project_does_not_place_is_refused(
        tmp_path_factory, template, design, ix):  # noqa: F811
    path = _project(tmp_path_factory, template, design, ix, omit=("U404",))
    with pytest.raises(SystemExit, match="U404"):
        layout_export.export(place.load(path), design)


def test_the_stack_states_what_sets_each_gap_and_no_gap(exported, design):  # noqa: F811
    """pcbl derives every gap; the export hands it the setters and board_params'
    own figures, never a gap (a stated one would be a second home)."""
    st = exported.doc["stack"]
    assert "gaps" not in st
    assert (st["available_mm"], st["clearance_mm"], st["tail_mm"]) == (
        layout_export.bp.AVAIL_H, layout_export.bp.CLEARANCE, layout_export.bp.TAIL)
    assert st["floor"] == {"liner_mm": layout_export.bp.FLOOR_LINER_T,
                           "min_mm": layout_export.bp.FLOOR_STANDOFF_MIN,
                           "seat": layout_export.bp.FLOOR_SEAT,
                           "seat_pad_mm": layout_export.bp.THERMAL_PAD_T}
    want = [(s.name, *s.between, s.height_mm, {"sets": "sets", "shimmed": "short"}[s.seating])
            for s in design.standoffs if s.seating != "shim"]
    assert [(s["name"], s["below"], s["above"], s["mm"], s["seating"])
            for s in st["standoffs"]] == want
    assert st["lid"] is True


def test_lead_mm_is_stated_only_on_a_through_hole_footprint(exported, design):  # noqa: F811
    fps = {f["name"]: f for f in exported.doc["footprints"]}
    leads = {x.refdes: x.lead_mm for x in (*design.parts, *design.connectors)
             if getattr(x, "lead_mm", None) is not None}
    rows = {p["refdes"]: p for p in exported.doc["parts"]}
    stated = [r for r in rows if "lead_mm" in rows[r]]
    assert stated, "no part carries its leads"
    for ref in stated:
        assert rows[ref]["lead_mm"] == leads[ref]
        assert any(p.get("crosses_board") for p in fps[rows[ref]["footprint"]]["pads"])
    for ref in set(leads) & set(rows) - set(stated):
        assert any(f"{ref} states lead_mm" in n for n in exported.notes), ref


def test_the_export_validates_with_pcblayouts_loader(exported):
    model = pytest.importorskip("pcblayout.model")
    d = model.loads(exported.text())
    assert [b.name for b in d.boards] == ["POWER", "OUTPUTS", "LOGIC", "CTRL"]
    assert model.loads(model.dumps(d)) == d


# --- the hook ------------------------------------------------------------------------
def test_one_operating_point_per_soft_start_world(design):  # noqa: F811
    points = layout_hooks.operating_points()
    assert len(points) == len(soft_start.operating_points(design))
    assert all(row.keys() == route.hv_node_voltages(design).keys() for row in points.values())


def test_the_hook_validates_with_pcblayout(exported):
    model = pytest.importorskip("pcblayout.model")
    from pcblayout.model.yaml_io import load_hooks, with_hooks
    hooks = load_hooks(layout_hooks.__file__)
    assert hooks.names == ("operating_points",)
    d = with_hooks(model.loads(exported.text()), hooks)
    assert d.voltages is not None


def test_a_copied_hook_refuses_rather_than_guess(tmp_path):
    """A COPY beside the yaml cannot find the netlist; it must say so, not
    import whatever `tools` package happens to be on the path."""
    copy = tmp_path / "layout_hooks.py"
    shutil.copy(layout_hooks.__file__, copy)
    spec = importlib.util.spec_from_file_location("copied_layout_hooks", copy)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pytest.raises(ImportError, match="symlink"):
        mod.operating_points()


def test_a_symlinked_hook_finds_the_netlist(tmp_path):
    link = tmp_path / "layout_hooks.py"
    link.symlink_to(layout_hooks.__file__)
    spec = importlib.util.spec_from_file_location("linked_layout_hooks", link)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.operating_points() == layout_hooks.operating_points()
