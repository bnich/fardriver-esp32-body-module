"""tools/route.py: the class table, the rules, the planes, the rule-driven
copper, and the check -- every one of the check's rules proven to fire on a
mutation of a route that passes it.

The project under test is the SAME SYNTHETIC one `tests/test_place.py` builds
(its `_stream`), placed by the engine and then routed by this tool: no file of
the owner's is committed.  `REVV1_PLACE_PROJECT=/path/to/saved.eprj2` runs the
same tests against a real save.

⚠️ THE CLEAN ROUTE IS THE TOOL'S OWN OUTPUT, which is the only honest thing to
mutate: a hand-written "clean" route would be a route nobody has to keep
clean.  Every mutation test therefore starts from `--rules --pours --heavy` and
breaks exactly one thing.
"""
import json
import os

import pytest

pytest.importorskip("cryptography")

from tests.test_eprj2 import OWNER  # noqa: E402
from tests.test_place import _stream, template  # noqa: E402,F401  (template is a fixture)
from tools import board_params as bp, eprj2, layout_rules, netlist, place, route  # noqa: E402

MIL = route.MIL_PER_MM


# --- fixtures -----------------------------------------------------------------------
@pytest.fixture(scope="module")
def design():
    return netlist.checked()


@pytest.fixture(scope="module")
def ix(design):
    return place.Index(design)


def _with_rules(text):
    """`_stream`'s synthetic project plus the design rules the BUILD writes --
    the JLCPCB capability template and its board-wide 0.2 mm / 5 mil defaults.

    ⚠️ Taken from `tools.eprj3.pcb.DesignRules`, the build's own, not typed
    here: `--rules` builds each class rule out of the document's DEFAULT one,
    so a fixture with rules of its own invention would prove the tool against
    a document no build ever writes."""
    from tools.eprj3.pcb import DesignRules
    rules = DesignRules()
    recs, out = eprj2.split_records(text), []
    for h, p in recs:
        out.append((h, p))
        if h["type"] == "META" and json.loads(p).get("title") in bp.STACK_ORDER:
            out.append(({"type": "RULE_TEMPLATE", "id": "RULE_TEMPLATE"},
                        eprj2._compact({"name": rules.template_name})))
            for cls, name, state, ctx in rules.entries():
                out.append(({"type": "RULE",
                             "id": json.dumps(["RULE", cls, name], separators=(",", ":"))},
                            eprj2._compact({"ruleState": state, "ruleContext": ctx})))
    return eprj2.join(out)


@pytest.fixture(scope="module")
def placed_project(tmp_path_factory, template, design, ix):  # noqa: F811
    """A saved .eprj2 with every board PLACED -- what routing starts from."""
    env = os.environ.get("REVV1_PLACE_PROJECT")
    if env:
        return env
    path = tmp_path_factory.mktemp("routed") / "revv1-module.eprj2"
    eprj2.write(template, path, _with_rules(_stream(design, ix)), {"boards": {}},
                "revv1-module", owner=OWNER)
    project = place.load(path)
    pl = place.stack(project, ix)
    place.apply(project, pl)
    text = eprj2.join(project.records)
    out = path.with_name("placed.eprj2")
    eprj2.write(path, out, text, project.snap["structure"], project.snap["name"], owner=OWNER)
    return out


def _load(path, ix):
    project = place.load(path)
    return project, place.Placement.from_file(project, ix)


@pytest.fixture(scope="module")
def routed(placed_project, ix):
    """(project, placement) after --rules, --pours and --heavy, in memory."""
    project, pl = _load(placed_project, ix)
    route.write_rules(project, pl, ix)
    route.write_pours(project, pl, ix)
    route.write_heavy(project, pl, ix)
    return project, pl


@pytest.fixture
def fresh(placed_project, ix):
    """A per-test copy of the routed project, so a mutation cannot leak."""
    project, pl = _load(placed_project, ix)
    route.write_rules(project, pl, ix)
    route.write_pours(project, pl, ix)
    route.write_heavy(project, pl, ix)
    return project, pl


def _problems(project, pl, ix, board=None):
    return route.check_routing(project, pl, ix, boards=[board] if board else None)


def _doc(project, board):
    return route.DocEdit(project, board)


def _add(project, board, type_, payload, rid=None):
    _doc(project, board).append(type_, rid or route._rid(type_, json.dumps(payload)), payload)


def _line(frame, net, layer, u0, v0, u1, v1, width):
    x0, y0 = frame.to_file(u0, v0)
    x1, y1 = frame.to_file(u1, v1)
    return {"partitionId": "", "groupId": 0, "netName": net, "layerId": layer,
            "startX": route._mil(x0), "startY": route._mil(y0),
            "endX": route._mil(x1), "endY": route._mil(y1),
            "width": route._mil(width), "locked": False, "zIndex": -1}


# --- R0: the class table ------------------------------------------------------------
def test_every_class_states_what_its_figures_protect():
    for cls in route.CLASS_ORDER + (route.DEFAULT,):
        assert cls.why and len(cls.why) > 20, cls.name
        assert cls.width_mm > 0 and cls.clearance_mm > 0, cls.name


def test_the_hv_clearance_is_the_repo_s_one_figure():
    """⛔ Not a second copy of 1.25: the class reads `layout_rules`, so the
    placement proxy (check 7) and the routing rule cannot drift apart."""
    assert route.HV.clearance_mm == layout_rules.HV_CLEARANCE_MM


def test_pack_voltage_beats_rail(ix):
    """`HV_C1_P` and `HV_C2_HOLD` are in `rules.rails(d)` AND at 84 V. Reached
    by the RAIL row first they would be routed at 0.6 mm and 0.25 mm of
    clearance while sitting at pack voltage."""
    for net in ("HV_C1_P", "HV_C2_HOLD"):
        assert net in ix.rails
        assert route.net_class(ix, "POWER", net) is route.HV


def test_the_twelve_volt_bus_is_pwr12_only_where_the_current_is(ix):
    """R0 scopes PWR12 to "on OUTPUTS and POWER"; `carries_bus` derives it."""
    assert route.carries_bus(ix, "POWER") and route.carries_bus(ix, "OUTPUTS")
    assert not route.carries_bus(ix, "LOGIC") and not route.carries_bus(ix, "CTRL")
    assert route.net_class(ix, "POWER", "V12") is route.PWR12
    assert route.net_class(ix, "OUTPUTS", "V12") is route.PWR12
    assert route.net_class(ix, "LOGIC", "V12") is route.RAIL
    assert route.net_class(ix, "CTRL", "V12") is route.RAIL


def test_the_driver_line_is_on_outputs_and_nowhere_else(ix):
    assert route.v12_line(ix, "OUTPUTS") == ("U301", "U302", "U303")
    for board in ("POWER", "LOGIC", "CTRL"):
        assert route.v12_line(ix, board) == ()


def test_the_can_pair_comes_from_the_transceiver_s_pins(ix):
    """Derived from a part with pins named CANH/CANL, never from a net name."""
    assert route.diff_nets(ix, "LOGIC") == {"CANH", "CANL"}
    assert route.net_class(ix, "LOGIC", "CANH") is route.DIFF


def test_the_pair_follows_the_pin_and_not_the_name(design):
    """⛔ The class is the transceiver's pins, not a net called CANH. Move the
    `CANH` pin onto a net with another name and the class moves with it; the
    net that keeps the name and loses the pin drops out."""
    d = design.replace_net("CANH", pins=tuple(
        p for p in design.net("CANH").pins if p[0] != "U404"))
    d = d.replace_net("CAN_RS", pins=design.net("CAN_RS").pins + (("U404", "CANH"),))
    ix2 = place.Index(d)
    pair = route.diff_nets(ix2, "LOGIC")
    assert "CAN_RS" in pair and "CANH" not in pair


def test_a_sense_net_is_not_a_rail(ix):
    for net in ("CS1", "KEY_SENSE_PIN", "V12_SENSE"):
        assert route.net_class(ix, "LOGIC", net) in (route.SENSE, route.DEFAULT)
    assert route.net_class(ix, "OUTPUTS", "CS1") is route.SENSE


# --- the tool's own output passes its own check --------------------------------------
def test_rules_pours_and_heavy_leave_a_route_the_check_passes(routed, ix):
    project, pl = routed
    assert route.check_routing(project, pl, ix) == []


def test_heavy_writes_nothing_its_own_check_refuses(routed, ix):
    """⛔ The one property that keeps the tool from arguing with itself."""
    project, pl = routed
    for board in bp.STACK_ORDER:
        c = route.copper(project, pl, ix, board)
        assert route._check_widths(c, ix, board) == []
        assert route._check_clearances(c, ix, board) == []


# --- R3: every rule proven to fire ----------------------------------------------------
def test_the_width_rule_fires_on_a_thinned_heavy_run(fresh, ix):
    project, pl = fresh
    doc = _doc(project, "POWER")
    hit = None
    for i, (h, p) in enumerate(doc.recs):
        o = json.loads(p) if h["type"] == "LINE" else {}
        if o.get("netName") == "V12" and o["width"] > route.PWR12.width_mm * MIL - 1:
            hit = doc.start + i
            o["width"] = route._mil(0.254)
            doc.replace(hit, o)
            break
    assert hit is not None, "the fixture has no full-width V12 segment to thin"
    problems = _problems(project, pl, ix, "POWER")
    assert any("class PWR12 width" in p for p in problems), problems


def test_the_width_rule_does_not_fire_on_a_neck(fresh, ix):
    """A short narrow segment that lands on a pad of its own net is a NECK --
    how a 5 mm run enters a 3.96 mm-pitch contact -- and passes."""
    project, pl = fresh
    c = route.copper(project, pl, ix, "POWER")
    necks = [s for s in c.segs
             if route.net_class(ix, "POWER", s.net) is route.PWR12
             and s.width < route.PWR12.width_mm - route.TOL]
    assert necks, "the fixture routed no necked run"
    assert all(route.is_neck(c, s) for s in necks)
    assert route._check_widths(c, ix, "POWER") == []


def test_a_neck_too_long_is_not_a_neck(fresh, ix):
    """Lengthen the neck past `NECK_MM` and the width rule fires: the
    exemption is bounded by the millivolts it costs, not by where it starts."""
    project, pl = fresh
    frame = pl.frame("POWER")
    c = route.copper(project, pl, ix, "POWER")
    neck = next(s for s in c.segs
                if route.net_class(ix, "POWER", s.net) is route.PWR12
                and s.width < route.PWR12.width_mm - route.TOL)
    k = (route.NECK_MM + 2.0) / max(neck.length, 1e-6)
    _add(project, "POWER", "LINE",
         _line(frame, neck.net, neck.layer, neck.u0, neck.v0,
               neck.u0 + (neck.u1 - neck.u0) * k, neck.v0 + (neck.v1 - neck.v0) * k, neck.width))
    assert any("class PWR12 width" in p for p in _problems(project, pl, ix, "POWER"))


def test_a_neck_landing_between_two_pads_of_one_pin_is_still_a_neck():
    """⭐ THE REGRESSION. One pin can own several pads (`U303.OUT1` owns two),
    and the point `--heavy` aims a run at is their mean -- which falls BETWEEN
    them and inside neither. Testing "on a pad" against a single pad's box
    made the tool write a neck its own check then called a thin bus:
    `AUX12V_1`, 0.993 mm over 3.0 mm, the first time the clustered placement
    was routed. The land of a PIN is what both of them answer to.

    ⚠️ The synthetic project cannot catch this -- its footprints give every
    pin one pad -- which is why this one is built by hand."""
    left = route.Pad("U303", "OUT1", "CH", place.Box(9.0, 9.6, 9.8, 10.4), (1,), False)
    right = route.Pad("U303", "OUT1", "CH", place.Box(10.2, 9.6, 11.0, 10.4), (1,), False)
    c = route.Copper("OUTPUTS", None, pads=[left, right])
    mean_u = (left.u + right.u) / 2
    assert not route._point_in(left.box, mean_u, 10.0)
    assert not route._point_in(right.box, mean_u, 10.0)
    neck = route.Seg("CH", 1, mean_u + 3.0, 10.0, mean_u, 10.0, 0.8)
    assert route.is_neck(c, neck)
    far = route.Seg("CH", 1, mean_u + 9.0, 10.0, mean_u + 6.0, 10.0, 0.8)
    assert not route.is_neck(c, far)


def test_a_thin_run_that_touches_no_pad_is_not_a_neck(fresh, ix):
    """The second half of the neck rule: short is not enough."""
    project, pl = fresh
    frame = pl.frame("POWER")
    _add(project, "POWER", "LINE", _line(frame, "V12", 1, 120.0, 20.0, 121.0, 20.0, 0.254))
    assert any("class PWR12 width" in p for p in _problems(project, pl, ix, "POWER"))


def test_the_clearance_rule_fires_on_copper_laid_beside_another_net(fresh, ix):
    project, pl = fresh
    frame = pl.frame("POWER")
    c = route.copper(project, pl, ix, "POWER")
    victim = next(s for s in c.segs if s.net in ix.hv["POWER"])
    off = 0.2                                       # far inside the 1.25 mm the class wants
    _add(project, "POWER", "LINE",
         _line(frame, "GND", victim.layer, victim.u0, victim.v0 + victim.width / 2 + off,
               victim.u1, victim.v1 + victim.width / 2 + off, 0.2))
    problems = _problems(project, pl, ix, "POWER")
    assert any("class HV clearance" in p for p in problems), problems


def test_the_clearance_rule_measures_a_round_pad_as_a_circle(routed, ix):
    """⚠️ A pad's SHAPE, not its bounding box. A diagonal trace clipping the
    corner of a round through-hole pad's square reads as a violation that is
    not there -- half a millimetre of phantom on this project's 2.4 mm pads."""
    project, pl = routed
    c = route.copper(project, pl, ix, "POWER")
    round_pads = [p for p in c.pads if p.radius]
    if not round_pads:
        pytest.skip("the synthetic footprints draw no ELLIPSE pads")
    p = round_pads[0]
    s = route.Seg(p.net + "_other", p.layers[0],
                  p.u - 5, p.v - 5 - p.radius * 1.4, p.u + 5, p.v + 5 - p.radius * 1.4, 0.2)
    assert route.gap(s, p) > 0.0


def test_hv_over_a_ground_plane_fires(fresh, ix):
    """R1: 84 V over a plane is 84 V across one 0.2 mm prepreg."""
    project, pl = fresh
    frame = pl.frame("POWER")
    low, far, line = place.hv_partition(pl, ix, "POWER")
    # widen the plane back over the 84 V end, then put a pack-voltage trace on it
    doc = _doc(project, "POWER")
    for i, (h, p) in enumerate(doc.recs):
        if h["type"] == "POUR":
            o = json.loads(p)
            if o["layerId"] == route.STACK_LAYER[2]:
                doc.replace(doc.start + i,
                            route._pour_record(frame, "GND", o["layerId"],
                                               place.Box(1.5, 1.5, frame.length - 1.5,
                                                         frame.width - 1.5), "POUR1", 0))
    net = sorted(ix.hv["POWER"])[0]
    _add(project, "POWER", "LINE",
         _line(frame, net, route.STACK_LAYER[2], 10.0, 10.0, 20.0, 10.0, 0.5))
    problems = _problems(project, pl, ix, "POWER")
    assert any("pack-voltage segment(s) on layer" in p for p in problems), problems


def test_an_hv_via_through_the_plane_fires(fresh, ix):
    project, pl = fresh
    frame = pl.frame("POWER")
    doc = _doc(project, "POWER")
    for i, (h, p) in enumerate(doc.recs):
        if h["type"] == "POUR":
            o = json.loads(p)
            doc.replace(doc.start + i,
                        route._pour_record(frame, "GND", o["layerId"],
                                           place.Box(1.5, 1.5, frame.length - 1.5,
                                                     frame.width - 1.5), o["name"], o["order"]))
    net = sorted(ix.hv["POWER"])[0]
    x, y = frame.to_file(10.0, 10.0)
    _add(project, "POWER", "VIA", {
        "partitionId": "", "groupId": 0, "netName": net, "ruleName": "",
        "centerX": route._mil(x), "centerY": route._mil(y), "holeDiameter": 12.0078,
        "viaDiameter": 24.0158, "viaType": "NORMAL", "topSolderExpansion": None,
        "bottomSolderExpansion": None, "locked": False, "unusedInnerLayers": []})
    problems = _problems(project, pl, ix, "POWER")
    assert any("pack-voltage via(s)" in p for p in problems), problems


def test_the_pour_extent_rule_fires_when_a_plane_crosses_the_partition(fresh, ix):
    project, pl = fresh
    frame = pl.frame("POWER")
    doc = _doc(project, "POWER")
    hit = next(doc.start + i for i, (h, _) in enumerate(doc.recs) if h["type"] == "POUR")
    doc.replace(hit, route._pour_record(frame, "GND", route.STACK_LAYER[2],
                                        place.Box(1.5, 1.5, frame.length - 1.5, frame.width - 1.5),
                                        "POUR1", 0))
    problems = _problems(project, pl, ix, "POWER")
    assert any("R1 pour extent" in p for p in problems), problems


def test_the_pour_extent_rule_passes_on_what_pours_writes(routed, ix):
    project, pl = routed
    c = route.copper(project, pl, ix, "POWER")
    assert route._check_pour_extent(c, ix, "POWER", pl) == []
    low, far, line = place.hv_partition(pl, ix, "POWER")
    for p in c.pours:
        assert p.box.u0 >= line - route.TOL, (p.net, p.layer, p.box)


def test_the_twelve_volt_carrier_rule_fires_when_the_pour_goes(fresh, ix):
    """OUTPUTS' bus is a POUR; delete it and the 1 mm channels that remain are
    not a bus, so the rule says so."""
    project, pl = fresh
    doc = _doc(project, "OUTPUTS")
    drop = [doc.start + i for i, (h, p) in enumerate(doc.recs)
            if h["type"] == "POUR" and json.loads(p)["netName"] == "V12"]
    assert drop, "the fixture poured no V12"
    doc.drop(drop)
    frame = pl.frame("OUTPUTS")
    _add(project, "OUTPUTS", "LINE", _line(frame, "V12", 1, 100.0, 22.0, 110.0, 22.0, 0.254))
    problems = _problems(project, pl, ix, "OUTPUTS")
    assert any("carried by neither a pour nor" in p for p in problems), problems


def test_a_sense_net_beside_the_bus_fires(fresh, ix):
    project, pl = fresh
    frame = pl.frame("OUTPUTS")
    c = route.copper(project, pl, ix, "OUTPUTS")
    loud = next(s for s in c.segs if route.net_class(ix, "OUTPUTS", s.net) is route.CH12)
    sense = sorted(n for n in ix.classes["SENSE"]
                   if any(ix.items[r].board == "OUTPUTS" for r, _ in ix.members[n]))
    if not sense:
        pytest.skip("no SENSE net on OUTPUTS")
    off = loud.width / 2 + 0.5                      # clears 0.3 mm, breaks the 1.0 mm keep
    _add(project, "OUTPUTS", "LINE",
         _line(frame, sense[0], loud.layer, loud.u0, loud.v0 + off, loud.u1, loud.v1 + off, 0.25))
    problems = _problems(project, pl, ix, "OUTPUTS")
    assert any("SENSE beside power" in p for p in problems), problems


def test_the_check_is_quiet_on_a_board_with_no_copper(placed_project, ix):
    """A placed, unrouted board has nothing to fail: the check is a DRC, not a
    completion report, and the ~250 signal nets are the editor's job."""
    project, pl = _load(placed_project, ix)
    assert route.check_routing(project, pl, ix) == []


# --- R0 written into the project ------------------------------------------------------
def test_rules_writes_a_named_rule_and_one_selector_per_net(fresh, ix):
    project, pl = fresh
    doc = _doc(project, "POWER")
    rules = {tuple(json.loads(h["id"])): json.loads(p)
             for h, p in doc.recs if h["type"] == "RULE"}
    assert ("RULE", "SAFE", "HV") in rules and ("RULE", "TRACK", "HV") in rules
    safe = rules[("RULE", "SAFE", "HV")]
    assert safe["ruleState"] == route.RULE_STATE
    want = layout_rules.HV_CLEARANCE_MM * MIL
    for layer in safe["ruleContext"]["safeSpacing"]:
        for row in layer["content"]:
            assert all(v >= want - 1e-3 for v in row)
    track = rules[("RULE", "TRACK", "HV")]
    for row in track["ruleContext"]["track"]["content"]:
        assert abs(row["stroMin"] - route.HV.width_mm * MIL) < 1e-3
        assert abs(row["stroDef"] - route.HV.width_mm * MIL) < 1e-3
    sels = {tuple(json.loads(h["id"])[1]): json.loads(p)
            for h, p in doc.recs if h["type"] == "RULE_SELECTOR"}
    for net in ix.hv["POWER"]:
        assert ("NET", net) in sels, net
        assert sels[("NET", net)]["ruleKeyValue"]["SAFE"] == "HV"
        assert sels[("NET", net)]["ruleKeyValue"]["TRACK"] == "HV"
        assert sels[("NET", net)]["ruleOrder"] == route.NET_RULE_ORDER


def test_rules_leaves_the_jlc_template_and_the_all_nets_default_alone(placed_project, ix):
    """⛔ The board-wide 0.2 mm is RIGHT for the ~250 signal nets, and the
    capability template is the fab's. Neither is replaced -- the classes are
    added beside them."""
    before, pl = _load(placed_project, ix)
    doc0 = _doc(before, "POWER")
    def defaults(doc):
        return [(h["type"], h.get("id"), p) for h, p in doc.recs
                if h["type"] in ("RULE", "RULE_TEMPLATE")
                and json.loads(p).get("ruleState") != "NORMAL"]
    keep = defaults(doc0)
    template_rec = next(p for h, p in doc0.recs if h["type"] == "RULE_TEMPLATE")
    assert "JLCPCB" in template_rec or json.loads(template_rec).get("name") is not None
    project, pl2 = _load(placed_project, ix)
    route.write_rules(project, pl2, ix)
    doc1 = _doc(project, "POWER")
    assert defaults(doc1) == keep


def test_rules_is_idempotent(placed_project, ix):
    project, pl = _load(placed_project, ix)
    route.write_rules(project, pl, ix)
    once = list(project.records)
    route.write_rules(project, pl, ix)
    assert project.records == once


def test_a_net_selector_the_owner_already_set_keeps_its_other_categories(fresh, ix):
    """POWER's saved file carries a `GND` selector with `COPPER: copperRegion`
    from the owner's own pour. A class that lands on a net with a selector
    must MERGE into it, not replace it."""
    project, pl = fresh
    doc = _doc(project, "POWER")
    rid = json.dumps(["RULE_SELECTOR", ["NET", "V12"]], separators=(",", ":"))
    hit = doc.find("RULE_SELECTOR", rid)
    assert hit
    payload = json.loads(hit[2])
    payload["ruleKeyValue"]["COPPER"] = "copperRegion"
    doc.replace(hit[0], payload)
    route.write_rules(project, pl, ix, boards=["POWER"])
    doc = _doc(project, "POWER")
    again = json.loads(doc.find("RULE_SELECTOR", rid)[2])
    assert again["ruleKeyValue"]["COPPER"] == "copperRegion"
    assert again["ruleKeyValue"]["TRACK"] == "PWR12"


def test_the_rules_document_names_every_class_and_its_nets(ix):
    text = route.rules_text(ix)
    for cls in route.CLASS_ORDER:
        assert cls.name in text and cls.why[:20] in text
    assert "HV_BPLUS" in text and "Net Class" in text


# --- R1 written into the project ------------------------------------------------------
def test_pours_gives_every_board_a_ground_plane_on_the_second_layer(routed, ix):
    project, pl = routed
    for board in bp.STACK_ORDER:
        c = route.copper(project, pl, ix, board)
        planes = [p for p in c.pours if p.layer == route.STACK_LAYER[2]]
        assert len(planes) == 1 and planes[0].net in ix.gnd, board


def test_pours_gives_each_board_the_third_layer_r1_says(routed, ix):
    project, pl = routed
    third = {}
    for board in bp.STACK_ORDER:
        c = route.copper(project, pl, ix, board)
        got = [p for p in c.pours if p.layer == route.STACK_LAYER[3]]
        assert len(got) == 1, board
        third[board] = got[0].net
    assert third["OUTPUTS"] == "V12"
    assert third["LOGIC"] == "V3P3"
    assert third["CTRL"] in ("GND", "BASEPLATE")
    assert third["POWER"] in ("GND", "BASEPLATE")


def test_the_v12_pour_spans_the_driver_line_and_the_feed(routed, ix):
    project, pl = routed
    box = route.v12_pour_box(pl, ix, "OUTPUTS")
    assert box is not None
    pwr12 = ix.classes["PWR12"]
    frame = pl.frame("OUTPUTS")
    for ref in route.v12_line(ix, "OUTPUTS") + (place.v12_bus(ix, "OUTPUTS")[1],):
        p = pl.get(ref)
        us = [u for num, u, _ in p.pads(frame) if ix.items[ref].pin_net.get(num) in pwr12]
        assert us, ref
        assert box.u0 - route.TOL <= min(us) and max(us) <= box.u1 + route.TOL, ref


def test_no_poured_record_is_written(routed):
    """⭐ The editor regenerates the FILL. Its own example project
    (`Example_3D Shell Design.eprj2`, which this editor converted) carries POUR
    records with no POURED beside them, so a POURED written here would be this
    tool's idea of a fill standing in for the editor's."""
    project, _ = routed
    for board in bp.STACK_ORDER:
        assert not any(h["type"] == "POURED" for h, _ in _doc(project, board).recs), board


def test_pours_replaces_a_plane_that_is_already_there(fresh, ix):
    """An autoroute's plane over the whole board is what `--pours` exists to
    correct, so it replaces rather than adds."""
    project, pl = fresh
    before = sum(1 for h, _ in _doc(project, "POWER").recs if h["type"] == "POUR")
    route.write_pours(project, pl, ix, boards=["POWER"])
    after = sum(1 for h, _ in _doc(project, "POWER").recs if h["type"] == "POUR")
    assert before == after == 2


# --- R2 written into the project ------------------------------------------------------
def test_heavy_routes_the_twelve_volt_bus_from_the_brick_to_the_contact(routed, ix):
    """The chain check 19 measures: the brick's `+V`, the bulk cap and the
    contact the 8.47 A leaves by, joined by >= 5 mm of copper."""
    project, pl = routed
    src, away, _ = place.v12_output(ix, "POWER")
    legs, refusals = route.heavy_runs(project, pl, ix, "POWER")
    joined = {(leg.a.split(".")[0], leg.b.split(".")[0]) for leg in legs
              if leg.cls == route.PWR12.name}
    refs = {r for pair in joined for r in pair}
    assert src in refs and away in refs, (joined, [str(r) for r in refusals])
    body = [s for leg in legs if leg.cls == route.PWR12.name for s in leg.segs]
    assert max(s.width for s in body) >= route.PWR12.width_mm - route.TOL


def test_heavy_routes_the_return_twin_and_not_the_baseplate(routed, ix):
    """⚠️ `BASEPLATE` is a ground-domain net on `U201` too, and it is not a
    return: it never reaches the connector the 8.47 A leaves by."""
    project, pl = routed
    legs, _ = route.heavy_runs(project, pl, ix, "POWER")
    twin = [leg for leg in legs if leg.cls == "PWR12 return"]
    assert twin, "no ground twin routed"
    assert {leg.net for leg in twin} == {"GND"}


def test_heavy_refuses_rather_than_routing_round_an_obstacle(routed, ix):
    """Every refusal names the pair and what stopped it. ⛔ The tool never
    detours: a bus that wanders is a bus whose length nobody derived."""
    project, pl = routed
    seen = 0
    for board in bp.STACK_ORDER:
        _, refusals = route.heavy_runs(project, pl, ix, board)
        for r in refusals:
            seen += 1
            assert r.a and r.b and r.why
            assert "." in r.a and "." in r.b
            assert str(r).startswith(r.net)
    assert seen, "no board refused anything -- the refusal path is untested"


def test_heavy_leaves_the_signals_alone(routed, ix):
    """Only the rule-driven classes are written; everything else waits for the
    editor's autorouter."""
    project, pl = routed
    heavy = {cls.name for cls in route.heavy_classes()} | {"PWR12 return"}
    for board in bp.STACK_ORDER:
        legs, _ = route.heavy_runs(project, pl, ix, board)
        assert {leg.cls for leg in legs} <= heavy, board


def test_heavy_skips_a_net_a_pour_carries(routed, ix):
    """R1 gives OUTPUTS' bus to the plane; a trace beside a plane is a second
    conductor nobody sized."""
    project, pl = routed
    legs, _ = route.heavy_runs(project, pl, ix, "OUTPUTS")
    assert not any(leg.net == "V12" for leg in legs)


def test_the_tree_offers_every_leg_before_refusing_a_node():
    """⭐ The regression for POWER's bus: a plain minimum spanning tree hung
    the connector off the nearest chip cap, that one leg was blocked, and the
    run the 8.47 A takes went unrouted while the stubs got drawn."""
    class N:
        def __init__(self, ref, u, v):
            self.ref, self.pin, self.u, self.v = ref, "1", u, v

    a, b, c = N("A", 0, 0), N("B", 1, 0), N("C", 5, 0)
    calls = []

    def draw(x, y):
        calls.append((x.ref, y.ref))
        if {x.ref, y.ref} == {"B", "C"}:
            return None, "blocked"
        return f"{x.ref}-{y.ref}", ""
    drawn, refused = route._tree([a, b, c], draw)
    assert refused == []
    assert {leg for _, _, leg in drawn} == {"A-B", "A-C"}
    assert ("B", "C") in calls                      # the short one was tried first


def test_a_node_no_leg_reaches_is_refused_once():
    class N:
        def __init__(self, ref, u, v):
            self.ref, self.pin, self.u, self.v = ref, "1", u, v
    drawn, refused = route._tree([N("A", 0, 0), N("B", 1, 0)], lambda x, y: (None, "walled in"))
    assert drawn == [] and len(refused) == 1 and refused[0][2] == "walled in"


# --- stripping ------------------------------------------------------------------------
def test_strip_removes_the_copper_and_nothing_else(routed, ix, tmp_path):
    project, pl = routed
    before = {}
    for board in bp.STACK_ORDER:
        before[board] = [(json.dumps(h, sort_keys=True), p) for h, p in _doc(project, board).recs]
    counts = route.strip_routing(project, ["POWER"])
    assert counts["POWER"]["LINE"] > 0 and counts["POWER"]["POUR"] == 2
    for board in bp.STACK_ORDER:
        now = [(json.dumps(h, sort_keys=True), p) for h, p in _doc(project, board).recs]
        if board != "POWER":
            assert now == before[board], board
        else:
            kept = [r for r in before[board]
                    if json.loads(r[0])["type"] not in route.STRIP_TYPES]
            assert now == kept


def test_strip_is_a_no_op_on_a_board_with_no_copper(placed_project, ix):
    project, pl = _load(placed_project, ix)
    before = list(project.records)
    route.strip_routing(project, ["LOGIC"])
    assert project.records == before


# --- the round trip --------------------------------------------------------------------
def test_the_written_file_re_reads_record_for_record(placed_project, ix, tmp_path, monkeypatch):
    monkeypatch.setattr(place, "editor_running", lambda: False)
    project, pl = _load(placed_project, ix)
    route.write_rules(project, pl, ix)
    route.write_pours(project, pl, ix)
    route.write_heavy(project, pl, ix)
    want = eprj2.split_records(eprj2.join(project.records))
    out = tmp_path / "routed.eprj2"
    route._write(project, pl, placed_project, out)
    got = eprj2.split_records(eprj2.read(out)["text"])
    assert len(got) == len(want)
    assert got == want


def test_the_writer_refuses_while_the_editor_is_open(placed_project, ix, tmp_path, monkeypatch):
    monkeypatch.setattr(place, "editor_running", lambda: True)
    project, pl = _load(placed_project, ix)
    with pytest.raises(RuntimeError, match="EasyEDA Pro is running"):
        route._write(project, pl, placed_project, tmp_path / "x.eprj2")


def test_the_untouched_documents_come_through_byte_for_byte(placed_project, ix, tmp_path,
                                                            monkeypatch):
    monkeypatch.setattr(place, "editor_running", lambda: False)
    project, pl = _load(placed_project, ix)
    lead0, docs0 = eprj2.documents(list(project.records))
    route.write_rules(project, pl, ix, boards=["POWER"])
    route.write_pours(project, pl, ix, boards=["POWER"])
    out = tmp_path / "one-board.eprj2"
    route._write(project, pl, placed_project, out)
    lead1, docs1 = eprj2.documents(eprj2.split_records(eprj2.read(out)["text"]))
    assert lead0 == lead1
    changed = []
    for (t0, u0, r0), (t1, u1, r1) in zip(docs0, docs1):
        assert (t0, u0) == (t1, u1)
        if r0 != r1:
            changed.append(u0)
    power = next(u for t, u, r in docs0 if t == "PCB" and any(
        json.loads(p).get("title") == "POWER" for h, p in r if h["type"] == "META"))
    assert changed == [power]


# --- the command line --------------------------------------------------------------------
def test_check_routing_exits_one_on_a_route_it_refuses(placed_project, ix, tmp_path, monkeypatch,
                                                       capsys):
    monkeypatch.setattr(place, "editor_running", lambda: False)
    project, pl = _load(placed_project, ix)
    frame = pl.frame("POWER")
    _add(project, "POWER", "LINE",
         _line(frame, sorted(ix.hv["POWER"])[0], 1, 10.0, 10.0, 60.0, 10.0, 0.254))
    out = tmp_path / "bad.eprj2"
    route._write(project, pl, placed_project, out)
    assert route.main(["--check-routing", "--file", str(out)]) == route.EXIT_PROBLEMS
    assert "class HV width" in capsys.readouterr().out


def test_check_routing_exits_zero_on_what_the_tool_wrote(placed_project, ix, tmp_path, monkeypatch,
                                                         capsys):
    monkeypatch.setattr(place, "editor_running", lambda: False)
    out = tmp_path / "written.eprj2"
    src = str(placed_project)
    assert route.main(["--rules", "--file", src, "--out", str(out)]) == 0
    assert route.main(["--pours", "--file", str(out), "--out", str(out)]) == 0
    assert route.main(["--heavy", "--file", str(out), "--out", str(out),
                       "--docs", str(tmp_path / "docs")]) == 0
    capsys.readouterr()
    assert route.main(["--check-routing", "--file", str(out)]) == 0
    assert "passes every class rule" in capsys.readouterr().out


def test_the_cli_refuses_a_file_that_is_not_there(tmp_path, capsys):
    assert route.main(["--check-routing", "--file", str(tmp_path / "nope.eprj2")]) \
        == route.EXIT_REFUSED


def test_the_cli_needs_a_mode(capsys):
    with pytest.raises(SystemExit):
        route.main(["--file", "x"])


def test_draw_writes_one_picture_per_board(routed, ix, tmp_path):
    pytest.importorskip("PIL")
    project, pl = routed
    paths = route.draw(project, pl, ix, tmp_path)
    assert len(paths) == len(bp.STACK_ORDER)
    assert all(p.exists() and p.stat().st_size > 1000 for p in paths)


# --- IO-29: the clearance between two HV nets is their own voltage difference --------
def test_the_ipc_table_is_the_standard_s_rows():
    """IPC-2221B (February 2012) Table 6-1, column B2 -- External Conductors,
    uncoated, sea level to 3050 m -- read against "Voltage Between Conductors
    (DC or AC Peaks)". A voltage between two integer rows takes the higher."""
    for volts, mm in ((0, 0.1), (15, 0.1), (16, 0.1), (30, 0.1), (31, 0.6), (50, 0.6),
                      (100, 0.6), (150, 0.6), (151, 1.25), (170, 1.25), (250, 1.25),
                      (300, 1.25), (500, 2.5)):
        assert route.ipc_clearance_mm(volts) == mm, volts
    assert route.ipc_clearance_mm(15.5) == 0.1          # between rows: the higher one
    assert route.ipc_clearance_mm(150.5) == 1.25
    assert route.ipc_clearance_mm(600) == pytest.approx(1.5)   # 0.0025 mm/V over 500


def test_ipc_table_self_check_fires(monkeypatch):
    """⛔ A check is not a check until a test shows it firing. Break the row the
    160 V do-not-exceed falls in and the table no longer reproduces the HV
    class's 1.25 mm, which `place`'s check 7 also stands on."""
    route._check_ipc_table()                       # the real table is consistent
    monkeypatch.setattr(route, "IPC_2221B_B2",
                        ((15, 0.1), (30, 0.1), (50, 0.6), (100, 0.6), (150, 0.6),
                         (170, 0.6), (250, 1.25), (300, 1.25), (500, 2.5)))
    with pytest.raises(RuntimeError, match="check 7"):
        route._check_ipc_table()


def test_three_pairs_by_hand():
    """HAND, from the node voltages `soft_start` derives:

      * `D13_GATE` to `HV_BPLUS` -- the gate against its own source. The widest
        they ever stand apart is D102's 15 V clamp (at a 160 V pack, the
        unclamped divider would give 25). 15 V is IPC-2221B B2's 0-15 row →
        **0.1 mm**, and the pair the decision was written about.
      * `HV_BPLUS` to `GND` -- pack voltage against low-voltage copper. `GND`
        is not in the class, so it is the 160 V figure → **1.25 mm**.
      * `HV_C1_P` to `HV_C1_N` -- the two sides of C201, the bulk cap across
        the brick's input. They are a whole pack apart with the key on, 160 V
        at the ceiling → **1.25 mm**. ⚠️ `HV_C1_N` sits at 0 V DC and still
        gets the pack figure here, because the voltage BETWEEN them is what the
        table asks for.
    """
    assert route.hv_pair_volts("D13_GATE", "HV_BPLUS") == 15.0
    assert route.pair_clearance("D13_GATE", "HV_BPLUS") == 0.1
    assert route.pair_clearance("HV_BPLUS", "GND") == layout_rules.HV_CLEARANCE_MM == 1.25
    assert route.hv_pair_volts("HV_C1_P", "HV_C1_N") == 160.0
    assert route.pair_clearance("HV_C1_P", "HV_C1_N") == 1.25


def test_two_nets_that_swing_together_are_not_a_pack_apart():
    """⛔ The difference is taken inside each operating point. `HV_SW` and `KSW`
    each swing 0 to 160 V, and are at the same voltage in every world -- an
    envelope of each would have called them 160 V apart."""
    assert route.hv_pair_volts("HV_SW", "KSW") == 0.0
    assert route.pair_clearance("HV_SW", "KSW") == 0.1


def test_the_hold_up_pair_keeps_the_full_figure():
    """⭐ D201 blocks, so during the ride-out `HV_C2_HOLD` is near pack voltage
    with `HV_SW` already at 0. Steady states alone would have read these two as
    one diode drop apart and relaxed the copper between them to 0.1 mm."""
    assert route.hv_pair_volts("HV_SW", "HV_C2_HOLD") == 160.0
    assert route.pair_clearance("HV_SW", "HV_C2_HOLD") == 1.25


def test_every_hv_net_has_a_derived_voltage(ix, design):
    nodes = route.hv_node_voltages(design)
    for board in bp.STACK_ORDER:
        assert set(ix.hv.get(board, ())) <= set(nodes), board
    assert set(nodes) == set(layout_rules.hv_nets(design, "POWER"))


def test_an_hv_net_with_no_derived_voltage_is_refused(monkeypatch, design):
    """⛔ A new 84 V net nothing derives must FAIL, never fall through to a
    relaxed figure by default."""
    from tools import soft_start
    real = soft_start.hv_node_ranges

    def short(d=None):
        out = dict(real(d))
        out.pop("HV_SW")
        return out
    monkeypatch.setattr(soft_start, "hv_node_ranges", short)
    monkeypatch.setattr(route, "_HV_VOLTS", {})
    with pytest.raises(RuntimeError, match="HV_SW.*no derived node voltage"):
        route.hv_node_voltages(design)


def test_required_clearance_keeps_the_floor_off_the_hv_branch(ix):
    """⛔ The floor is the run's own class figure, and applying it to an HV pair
    would undo IO-29: `max(1.25, 0.1)` is 1.25."""
    assert route.required_clearance(ix, "POWER", "D13_GATE", "HV_BPLUS",
                                    floor=route.HV.clearance_mm) == 0.1
    assert route.required_clearance(ix, "POWER", "V12", "GND", floor=route.PWR12.clearance_mm) \
        == route.PWR12.clearance_mm


def _clear_spot(c, frame, want, need=3.0):
    """A (u, v) on layer 1 with nothing of anybody's within `need` mm of a
    `want` mm long strip there -- so a mutation measures itself and not the
    placement it happened to land on."""
    for v in [x / 2 for x in range(4, int(frame.width * 2) - 4)]:
        for u in [x for x in range(2, int(frame.length) - int(want) - 2)]:
            box = place.Box(u - need, v - need, u + want + need, v + need)
            if not any(it.box.overlaps(box) for it in c.on_layer(1)):
                return u, v
    raise AssertionError("no clear spot on POWER layer 1 for the mutation")


def _hv_pair_at(project, pl, ix, a, b, gap_mm):
    """Lay two segments `gap_mm` apart, edge to edge, on clear board -- the
    mutation both clearance tests are built on. The geometry is identical every
    time; only the two NETS change, which is what makes the verdict a statement
    about the voltage between them."""
    frame = pl.frame("POWER")
    c = route.copper(project, pl, ix, "POWER")
    w, length = 0.2, 10.0
    u, v = _clear_spot(c, frame, length)
    _add(project, "POWER", "LINE", _line(frame, a, 1, u, v, u + length, v, w))
    _add(project, "POWER", "LINE",
         _line(frame, b, 1, u, v + w + gap_mm, u + length, v + w + gap_mm, w))


def test_a_gate_network_pair_at_half_a_millimetre_passes(fresh, ix):
    """⭐ THE MUTATION IO-29 ASKS FOR, first half. Two HV-class segments 0.5 mm
    apart: under the class rule both would have failed at 1.25 mm. `D13_GATE`
    against `HV_BPLUS` is the zener's 15 V, which B2 meets at 0.1 mm."""
    project, pl = fresh
    _hv_pair_at(project, pl, ix, "D13_GATE", "HV_BPLUS", 0.5)
    assert [p for p in _problems(project, pl, ix, "POWER") if "clearance" in p] == []


def test_the_same_geometry_fails_when_the_voltage_says_so(fresh, ix):
    """⭐ And the other half: the SAME two segments in the same place, on the
    two sides of C201 instead. A whole pack stands across them, so 0.5 mm is
    short of the 1.25 mm B2 asks for -- the verdict is the voltage, not the
    class, and the class is HV both times."""
    project, pl = fresh
    _hv_pair_at(project, pl, ix, "HV_C1_P", "HV_C1_N", 0.5)
    bad = [p for p in _problems(project, pl, ix, "POWER") if "class HV clearance" in p]
    assert bad, "a 160 V pair at 0.5 mm has to fail"
    assert "needs 1.25 mm" in bad[0] and "160.0 V between them" in bad[0], bad[0]


def test_a_middling_pair_gets_the_middling_row(fresh, ix):
    """Not just the two ends: `D13_GATE` to `D13_PD_MID` is 72.5 V, IPC-2221B
    B2's 51-100 row, 0.6 mm -- so 0.5 mm fails and the message says 0.60."""
    project, pl = fresh
    _hv_pair_at(project, pl, ix, "D13_GATE", "D13_PD_MID", 0.5)
    bad = [p for p in _problems(project, pl, ix, "POWER") if "class HV clearance" in p]
    assert bad and "needs 0.60 mm" in bad[0], bad


# --- IO-29: the DRC exception list ---------------------------------------------------
def test_the_exception_list_holds_the_joins_the_editor_will_flag(routed, ix):
    """One line per pair inside the editor's 1.25 mm that IO-29 accepts, with
    the voltage and the IPC figure it meets."""
    project, pl = routed
    c = route.copper(project, pl, ix, "POWER")
    rows = route.drc_exceptions(c, ix, "POWER")
    assert rows, "no accepted join at all -- the list would prove nothing"
    hv = set(ix.hv["POWER"])
    for na, nb, pa, pb, layers, g, volts, want in rows:
        assert na in hv and nb in hv                    # never an HV-to-LV join
        assert g < layout_rules.HV_CLEARANCE_MM         # the editor WILL flag it
        assert g >= want - route.TOL                    # and IO-29 accepts it
        assert route.ipc_clearance_mm(volts) == want
        assert layers and pa and pb


def test_a_real_hv_violation_never_reaches_the_exception_list(fresh, ix):
    """⛔ THE MUTATION. Pack voltage 0.5 mm from `GND` is a defect, not an
    exception: it must be absent from the list and present in the check."""
    project, pl = fresh
    _hv_pair_at(project, pl, ix, "HV_BPLUS", "GND", 0.5)
    c = route.copper(project, pl, ix, "POWER")
    rows = route.drc_exceptions(c, ix, "POWER")
    assert not [r for r in rows if "GND" in (r[0], r[1])]
    assert [p for p in _problems(project, pl, ix, "POWER") if "class HV clearance" in p]


def test_the_exception_list_includes_pad_to_pad(routed, ix):
    """⚠️ Unlike the class check. `--rules` raises every cell of the editor's
    clearance matrix, so an 0603's own two pads on different 84 V nets ARE a
    DRC hit there, and the owner needs them listed."""
    project, pl = routed
    c = route.copper(project, pl, ix, "POWER")
    rows = route.drc_exceptions(c, ix, "POWER")
    pads = [r for r in rows if "." in r[2] and "." in r[3]]
    assert pads, "no pad-to-pad row: the sweep is not looking at land patterns"


def test_heavy_writes_the_exception_document(placed_project, ix, tmp_path, monkeypatch, capsys):
    """Generated, like the placement tables: regenerated on every `--heavy`,
    and the file says an unlisted DRC hit is a defect."""
    monkeypatch.setattr(place, "editor_running", lambda: False)
    out, docs = tmp_path / "w.eprj2", tmp_path / "docs"
    src = str(placed_project)
    assert route.main(["--rules", "--file", src, "--out", str(out)]) == 0
    assert route.main(["--pours", "--file", str(out), "--out", str(out)]) == 0
    assert route.main(["--heavy", "--file", str(out), "--out", str(out),
                       "--docs", str(docs)]) == 0
    capsys.readouterr()
    path = docs / "POWER-drc-exceptions.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "is a defect" in text and "IPC-2221B B2" in text
    # no board without pack voltage gets one
    assert not (docs / "LOGIC-drc-exceptions.md").exists()
