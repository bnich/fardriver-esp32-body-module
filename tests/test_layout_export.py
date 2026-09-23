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


def test_the_hv_region_takes_the_non_plane_grounds_as_neutral(exported, ix):  # noqa: F811
    """Ground is on both sides of POWER's partition (`place.hv_pins`); a ground
    no plane carries -- `BASEPLATE` -- must be named, or C203/C204 read as
    straddlers and are turned round."""
    [region] = [c for c in exported.doc["constraints"] if c["kind"] == "region"]
    assert region["board"] == "POWER" and region["classes"] == [route.HV.name]
    assert region["neutral_nets"] == ["BASEPLATE"]


def test_a_net_two_classes_on_two_boards_is_reported(exported):
    """The model holds one class per net; `V12` is PWR12 where the brick and
    the driver line carry it and RAIL on LOGIC and CTRL.  The export takes the
    stronger and SAYS so -- never silently."""
    assert any(n.startswith("class: V12 ") for n in exported.notes)


def test_a_constraint_naming_a_part_the_project_does_not_place_is_refused(
        tmp_path_factory, template, design, ix):  # noqa: F811
    path = _project(tmp_path_factory, template, design, ix, omit=("U404",))
    with pytest.raises(SystemExit, match="U404"):
        layout_export.export(place.load(path), design)


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
