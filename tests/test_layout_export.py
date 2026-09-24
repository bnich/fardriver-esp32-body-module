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

from tools import eprj2, layout_export, layout_hooks, soft_start
from tools import layout_facts as facts
from tests.synthetic_project import OWNER, _stream, design, ix, template  # noqa: F401 (fixtures)

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
    return layout_export.export(facts.load(project_path), design)


# --- the export ---------------------------------------------------------------------
def test_the_export_is_deterministic(project_path, design, exported):  # noqa: F811
    again = layout_export.export(facts.load(project_path), design)
    assert again.text() == exported.text()
    assert again.notes == exported.notes


def test_every_board_has_its_four_copper_layers_in_stack_order(exported):
    names = [[layer["name"] for layer in b["layers"]] for b in exported.doc["boards"]]
    assert names == [["Top Layer", "Inner1", "Inner2", "Bottom Layer"]] * 4


def test_every_netclass_figure_is_routes(exported):
    """One fact, one home: a width or a clearance typed a second time here
    would drift from the figure the build's net classes state.
    EVERY class states `layout_facts`' width -- a current class too, whose stated
    width pcbl widens where IPC-2221 says more and never narrows."""
    table = {c.name: c for c in layout_export.CLASSES}
    for row in exported.doc["netclasses"]:
        c = table[row["name"]]
        assert row["clearance_mm"] == {"default": c.clearance_mm}
        assert row["min_width_mm"] == c.width_mm, row["name"]


def test_the_current_classes_state_their_route_widths(exported):
    """⭐ The stated widths are the design's: CH12 1.00 and CH5 0.80 stand
    though IPC-2221 would allow 0.97 and 0.48 at their currents."""
    rows = {row["name"]: row for row in exported.doc["netclasses"]}
    assert {n: rows[n]["min_width_mm"] for n in ("HV", "HVSIG", "PWR12", "PWR5AUX",
                                                 "CH12", "CH5")} == \
        {"HV": 0.5, "HVSIG": 0.5, "PWR12": 5.0, "PWR5AUX": 2.0, "CH12": 1.0, "CH5": 0.8}


def test_class_copper_is_on_the_heavy_classes_and_no_other(exported):
    """`pcbl route copper` lays the classes the build lays by rule -- the list
    is `facts.heavy_classes`, never typed here."""
    laid = {row["name"] for row in exported.doc["netclasses"] if row.get("class_copper")}
    used = {row["name"] for row in exported.doc["netclasses"]}
    assert laid == ({c.name for c in facts.heavy_classes()} | {"HVSIG"}) & used
    assert laid, "no class is laid by rule"


def test_vias_are_stated_on_ch12_pwr5aux_and_the_signal_classes_only(exported):
    """No HV via: a pack-voltage barrel would need a 1.25 mm antipad through
    each inner GND plane.  The signal classes the signal router lays carry
    one, or a net with pads on both faces cannot be completed.  What one via carries is pcbl's to derive from the
    hole, the board's plating and the class's rise: the class states none."""
    rows = {row["name"]: row for row in exported.doc["netclasses"]}
    viad = {n for n, row in rows.items() if row.get("via_mm")}
    assert viad == set(layout_export.VIA_CLASSES) & set(rows)
    assert not viad & {"HV", "HVSIG"}
    assert {"DIFF", "SENSE", "default"} & set(rows) <= viad
    for n in viad:
        assert rows[n]["via_mm"] == [0.6, 0.3]
    assert not any("via_current_a" in row for row in rows.values())


def test_each_current_class_states_one_current_and_its_rise(exported):
    """CH12 / CH5 at their strongest channel's limit, PWR5AUX at four 5 V
    limiters together, PWR12 at the limited 12 V load, HV at the pack tap in
    that case -- each with the rise `layout_facts` sized it for."""
    rows = {row["name"]: row for row in exported.doc["netclasses"]}
    got = {n: (rows[n]["current_a"], rows[n]["rise_c"]) for n in rows if "current_a" in rows[n]}
    assert got == {"HV": (pytest.approx(2.58), 10.0), "PWR12": (pytest.approx(11.386), 20.0),
                   "PWR5AUX": (pytest.approx(5.553), 20.0),
                   "CH12": (pytest.approx(2.323), 10.0), "CH5": (pytest.approx(1.388), 10.0)}
    assert "current_a" not in rows["HVSIG"] and "rise_c" not in rows["HVSIG"]


def test_every_board_states_the_fab_copper(exported):
    assert {(b["copper_um"], b["via_plating_um"]) for b in exported.doc["boards"]} == \
        {(35.0, 18.0)}



def test_every_board_states_its_design_width_and_the_filled_via_allowance(exported):
    """The outline width is `board_params.board_width` -- POWER deeper than
    the rest (owner, 2026-09-24) -- and every board allows a filled via in a
    pad (POFV, owner, 2026-09-24), which pcbl uses only where neither a via
    beside the pad nor a short escape fits, and names each pad it uses."""
    from tools import board_params as bp
    widths = {b["name"]: b["width_mm"] for b in exported.doc["boards"]}
    assert widths["POWER"] == bp.POWER_W
    assert all(w == pytest.approx(bp.BOARD_W, abs=1e-6)
               for n, w in widths.items() if n != "POWER")
    assert all(b["filled_vias_in_pad"] is True for b in exported.doc["boards"])
    assert any("POWER is drawn 41.84 mm wide" in n for n in exported.notes)

def test_a_channel_with_no_derivable_limit_is_refused(design, ix, monkeypatch):  # noqa: F811
    from tools import power_budget
    monkeypatch.setattr(power_budget, "_channel_limit_a",
                        lambda d, net: (None, f"{net}: no limiter"))
    with pytest.raises(SystemExit, match="CH12 current"):
        layout_export._class_current_a(design, ix)


def test_an_underivable_limited_case_is_refused(design, ix, monkeypatch):  # noqa: F811
    from tools import power_budget
    real = power_budget.limit_case

    def broken(d=None):
        lim = real(d)
        lim.tap_a = None
        return lim
    monkeypatch.setattr(power_budget, "limit_case", broken)
    with pytest.raises(SystemExit, match="PWR12 / HV current"):
        layout_export._class_current_a(design, ix)


def test_the_class_currents_are_read_off_the_circuit(design, ix):  # noqa: F811
    assert layout_export._class_current_a(design, ix) == \
        {"CH12": pytest.approx(2.323), "CH5": pytest.approx(1.388),
         "PWR5AUX": pytest.approx(5.553), "PWR12": pytest.approx(11.386),
         "HV": pytest.approx(2.58)}


def test_every_board_states_routes_pour_inset(exported):
    assert {b["pour_inset_mm"] for b in exported.doc["boards"]} == {facts.POUR_INSET}


def test_the_cable_states_no_gap(exported):
    """The loom's height is the stack's to derive (`stack.cable_gap`)."""
    cables = [c for c in exported.doc["constraints"] if c["kind"] == "cable"]
    assert cables and all("gap_mm" not in c for c in cables)


def test_the_twin_is_routes_return_rule(exported, ix):  # noqa: F811
    """The ground twin is stated where the 12 V run needs one: the
    board that makes the bus, each ground reaching the converter and the
    contact it leaves by, over those and the bus parts on that ground.  (A
    region's own ground twin is the next test's.)"""
    regions = {c["name"] for c in exported.doc["constraints"] if c["kind"] == "region"}
    twins = [c for c in exported.doc["constraints"] if c["kind"] == "twin"
             and not any(c["name"].startswith(f"{r}-") for r in regions)]
    assert [(t["board"], t["net"], t["beside"]) for t in twins] == [
        ("POWER", "GND", facts.PWR12.name)]
    src, away, parts = facts.v12_output(ix, "POWER")
    [t] = twins
    assert t["parts"][:2] == [src, away]
    assert set(t["parts"][2:]) == {r for r in parts if "GND" in ix.items[r].nets} - {away}
    assert len(set(t["parts"])) == len(t["parts"])
    assert "BASEPLATE" not in {t["net"] for t in twins}


def test_the_hv_region_takes_the_non_plane_grounds_as_neutral(exported, ix):  # noqa: F811
    """Ground is on both sides of POWER's partition; a ground
    no plane carries -- `BASEPLATE` -- must be named, or C203/C204 read as
    straddlers and are turned round."""
    [region] = [c for c in exported.doc["constraints"] if c["kind"] == "region"]
    assert region["board"] == "POWER" and region["classes"] == ["HV", "HVSIG"]
    assert region["neutral_nets"] == ["BASEPLATE"]


# --- the pack-voltage classes, split by current ---------------------------------------
#: What the load and pre-charge current flow through on POWER, by the circuit:
#: B+ through the switch Q101 to HV_SW, both chokes (each with its return
#: winding), D201 and the fuse into C2's hold.
POWER_HV = ["HV_BPLUS", "HV_C1_N", "HV_C1_P", "HV_C2_HOLD", "HV_C2_HOLD_IN", "HV_C2_N",
            "HV_C2_P", "HV_SW"]
#: The gate drive, the key sense and the level shifter's string.
SIGNAL_HV = ["D13_EN_MID", "D13_GATE", "D13_PD", "D13_PD_MID", "KEY_SENSE_MID", "KSW"]


def test_the_power_hv_class_is_the_load_path(design, ix):  # noqa: F811
    """Silent, and the answer: the walk from the converters' supply nets
    finds the load path and nothing a zener, TVS or resistor hangs off it."""
    hv = ix.hv["POWER"]
    power = layout_export._hv_power_nets(design, hv)
    assert sorted(power) == POWER_HV
    assert sorted(hv - power) == SIGNAL_HV


def test_each_hv_net_is_in_the_class_its_current_says(exported):
    got = {n["name"]: n["net_class"] for n in exported.doc["nets"]
           if n["name"] in POWER_HV + SIGNAL_HV}
    assert got == {**{n: "HV" for n in POWER_HV}, **{n: "HVSIG" for n in SIGNAL_HV}}


def test_a_return_winding_carries_the_load(design, ix):  # noqa: F811
    """The chokes' second windings are reached ONLY by the return-winding
    clause: nothing else the load flows through joins HV_C1_N / HV_C2_N to
    the power nets.  Without the clause they would be laid at 0.5 mm."""
    from tools import rules
    rix = rules._index(design)
    for n in ("HV_C1_N", "HV_C2_N"):
        into = {other for other, part, *_ in rix.adj[n] if part.kind != "CMCHOKE"
                and (rules._kind(part) in soft_start._DC_SHORT or part.kind in rules.FETS
                     or part.kind == "D")}
        assert not into & set(POWER_HV), n


def test_both_hv_classes_are_pairwise_and_keep_one_clearance(exported):
    rows = {row["name"]: row for row in exported.doc["netclasses"]}
    for n in ("HV", "HVSIG"):
        assert rows[n]["pairwise_by_voltage"] is True
        assert rows[n]["clearance_mm"] == {"default": facts.HV.clearance_mm}
    assert not any(r.get("pairwise_by_voltage") for n, r in rows.items()
                   if n not in ("HV", "HVSIG"))


def test_a_board_whose_hv_nets_feed_no_supply_is_refused(design, monkeypatch):  # noqa: F811
    """Fires: with no pack-voltage net feeding a SUPPLY pin every HV net would
    be laid at the low-current width, the tap current through copper nobody
    sized.  Refused, not exported."""
    from tools import rules
    fresh = facts.Index(design)
    monkeypatch.setattr(rules, "rails", lambda d: frozenset({"V12"}))
    with pytest.raises(SystemExit, match="power HV class would be empty"):
        layout_export._net_classes(fresh)


def _net_row(exported, name):
    return next(n for n in exported.doc["nets"] if n["name"] == name)


def test_the_current_enters_at_the_converter_and_leaves_by_the_parts_it_feeds(exported):
    """`sources` / `sinks` are read off the copper: the brick's +V makes
    V12, the drivers that switch it are its sinks, and the buck's SW feeds
    the inductor.  A pull-up or a decoupler on the net is neither."""
    v12 = _net_row(exported, "V12")
    assert "U201" in v12["sources"]
    assert {"U301", "U302", "U303", "U305", "J202"} <= set(v12["sinks"])
    assert not {"R301", "C303", "D315"} & set(v12["sources"] + v12["sinks"])
    sw = _net_row(exported, "V5AUX_SW")
    assert (sw["sources"], sw["sinks"]) == (["U305"], ["L301"])
    aux = _net_row(exported, "V5AUX")
    assert aux["sources"] == ["L301"]
    assert set(aux["sinks"]) == {"U306", "U307", "U308", "U309"}


def test_a_pass_part_sink_is_stated_at_what_it_feeds(exported, design, ix):  # noqa: F811
    """An equal share of V12 is a fuse under a driver whose four channels
    all sit at their limiters: each TPS4H160B is stated at its channels'
    sum, and the buck at its output class's current."""
    cur = layout_export._class_current_a(design, ix)
    own = _net_row(exported, "V12")["part_current_a"]
    for u in ("U301", "U302", "U303"):
        assert own[u] == pytest.approx(4 * cur["CH12"], abs=1e-3)
        assert own[u] > cur["PWR12"] / len(_net_row(exported, "V12")["sinks"])
    assert own["U305"] == pytest.approx(cur["PWR5AUX"], abs=1e-3)
    assert "J202" not in own                    # a connector takes the equal share


def test_the_v12_pour_span_names_every_v12_pad_on_its_board(exported, ix):  # noqa: F811
    """A surface pad reaches the V12 pour only by a stitch via beside it, so
    the pour must reach every V12 pad on the board, not only the driver
    line's: the pull-ups and terminals were left with no sheet in reach."""
    spans = [c for c in exported.doc["constraints"] if c["kind"] == "pour_span"]
    assert spans
    for c in spans:
        want = {(it.refdes, p) for it in ix.on(c["board"])
                for p, n in it.pin_net.items() if n == c["net"]}
        assert {tuple(p) for p in c["pads"]} == want
        assert c["feed"] in {r for r, _ in want}



def test_the_region_ground_is_a_twin_across_every_ground_pin_in_the_region(exported, ix):  # noqa: F811
    """Decision 5: POWER's ground plane stops short of the pack-voltage end,
    so the ground pins in it are joined as copper -- a twin beside the
    region's power class.  Every region member with a ground pin is named
    (read here from the net classes, not from the export's own list), and
    nothing without a ground pin is."""
    rows = {n["name"]: n for n in exported.doc["nets"]}

    def cls(net, board):
        r = rows.get(net)
        return None if r is None else r.get("class_by_board", {}).get(board, r["net_class"])

    regions = [c for c in exported.doc["constraints"] if c["kind"] == "region"]
    twins = {c["name"]: c for c in exported.doc["constraints"] if c["kind"] == "twin"}
    assert regions
    for r in regions:
        t = twins[f"{r['name']}-GND-RETURN"]
        assert (t["board"], t["net"], t["beside"]) == (r["board"], "GND", r["classes"][0])
        members = {it.refdes for it in ix.on(r["board"]) if "GND" in it.nets
                   and any(cls(n, r["board"]) in r["classes"] for n in it.nets)}
        assert members and members <= set(t["parts"])
        assert all("GND" in ix.items[p].nets for p in t["parts"])
    assert twins["POWER-HV-GND-RETURN"]["parts"] == [
        "C212", "D101", "J101", "L101", "L102", "Q105", "U201", "U202"]


def test_every_part_on_a_converters_switch_node_stands_beside_it(exported, ix):  # noqa: F811
    """The buck's bootstrap capacitor and inductor share its `SW` net: each is
    a reach satellite of the converter at `SW_REACH`, or the placer is free to
    seat the inductor 23 mm away (it did, and `V5AUX_SW` could not be laid)."""
    reaches = {(c["host"], c["satellite"]): c for c in exported.doc["constraints"]
               if c["kind"] == "reach"}
    want = {(it.refdes, r) for it in ix.items.values() if it.kind == "IC" and "SW" in it.pin_net
            for r, _ in ix.members[it.pin_net["SW"]]
            if r != it.refdes and r in ix.items and ix.items[r].board == it.board}
    assert ("U305", "L301") in want and ("U305", "C314") in want
    for pair in want:
        assert reaches[pair]["within_mm"] == facts.SW_REACH

def test_a_net_two_classes_on_two_boards_states_each(exported, ix):  # noqa: F811
    """`V12` is PWR12 where the brick and the driver line carry it and RAIL
    where it is one trace to a converter.  The row states every board's class
    as `facts.net_class` gives it -- never one class everywhere, and never a
    note in place of the statement."""
    row = _net_row(exported, "V12")
    boards = sorted({ix.items[r].board for r, _ in ix.members["V12"] if r in ix.items})
    per = {b: facts.net_class(ix, b, "V12").name for b in boards}
    assert len(set(per.values())) > 1           # the case is real on this netlist
    stated = {b: row.get("class_by_board", {}).get(b, row["net_class"]) for b in boards}
    assert stated == per
    assert not any(n.startswith("class: ") for n in exported.notes)


def test_a_net_one_class_everywhere_names_no_board(exported):
    assert "class_by_board" not in _net_row(exported, "GND")


def test_supply_marks_the_grounds_and_the_rails_and_nothing_else(exported, ix):  # noqa: F811
    """`supply` is what `routability_span` does not measure: the
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
    """The brake clause, as a generic `corridor`: the path from the
    brake terminal to the module, the I2C pull-ups kept `CORRIDOR_CLEAR` off
    it -- every figure read from `layout_facts`, never typed here."""
    rows = [c for c in exported.doc["constraints"] if c["kind"] == "corridor"]
    [module] = [it for it in ix.on("LOGIC") if it.kind == "MODULE"]
    term = facts.brake_terminal(ix, "LOGIC", module.refdes)
    assert rows == [{"kind": "corridor", "name": f"{term}-{module.refdes}-BRAKE",
                     "ends": [term, module.refdes],
                     "parts": list(facts.i2c_pullups(ix, "LOGIC")),
                     "clear_mm": facts.CORRIDOR_CLEAR,
                     "reason": rows[0]["reason"]}]
    assert rows[0]["parts"]


def test_a_constraint_naming_a_part_the_project_does_not_place_is_refused(
        tmp_path_factory, template, design, ix):  # noqa: F811
    path = _project(tmp_path_factory, template, design, ix, omit=("U404",))
    with pytest.raises(SystemExit, match="U404"):
        layout_export.export(facts.load(path), design)


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


def _pad_record(angle, w=1.8, h=4.5, x=0.0, y=0.0):
    mil = layout_export.MIL_PER_MM
    return ({"type": "PAD", "id": "p"}, json.dumps(
        {"num": "1", "centerX": x * mil, "centerY": y * mil, "padAngle": angle,
         "defaultPad": {"padType": "RECT", "width": w * mil, "height": h * mil}}))


@pytest.mark.parametrize("angle, half", [(0, (0.9, 2.25)), (180, (0.9, 2.25)),
                                         (90, (2.25, 0.9)), (270, (2.25, 0.9)),
                                         (None, (0.9, 2.25))])
def test_a_pad_is_stated_as_its_pad_angle_turns_it(angle, half):
    """`U305`'s exposed pad is 1.8 x 4.5 mm drawn at 270: read unturned it
    lies across both pin rows and grounds `CBOOT` and `VCC`, which no router
    can then leave."""
    fp = layout_export._footprint("u", [_pad_record(angle)])
    pad = fp["pads"][0]
    assert (round(pad["hw"], 6), round(pad["hh"], 6)) == half
    assert [round(v, 6) for v in fp["body"]] == [-half[0], -half[1], half[0], half[1]]


def test_a_pad_turned_off_the_quarter_is_the_box_that_holds_it():
    pad = layout_export._footprint("u", [_pad_record(45, w=2.0, h=1.0)])["pads"][0]
    r = 1.5 / 2 ** 0.5
    assert (round(pad["hw"], 6), round(pad["hh"], 6)) == (round(r, 6), round(r, 6))


@pytest.mark.parametrize("angle", [0, 45, 90, 180, 270, 300, None])
def test_the_export_turns_a_pad_as_pcbl_reads_it(angle):
    """One pad, one geometry: the export states a turned pad exactly as
    pcbl's own reader turns it (`pcblayout.io.easyeda.read._turned`)."""
    read = pytest.importorskip("pcblayout.io.easyeda.read")
    pad = layout_export._footprint("u", [_pad_record(angle, w=2.0, h=0.6)])["pads"][0]
    want = read._turned(1.0, 0.3, angle)
    assert (pad["hw"], pad["hh"]) == pytest.approx(want)


def test_vias_in_pad_is_stated_on_the_exposed_pads_and_no_other(exported):
    """The thermal pads' via arrays are a per-pad allowance: every PAD/EPAD
    pad states it (the drivers', the buck's, the LDO's and the module's), and
    no other pad does -- a via anywhere else wicks the joint's solder."""
    stated = [(f["name"], p["number"]) for f in exported.doc["footprints"]
              for p in f["pads"] if p.get("vias_in_pad")]
    exposed = [(f["name"], p["number"]) for f in exported.doc["footprints"]
               for p in f["pads"] if p["number"] in facts.EXPOSED_PADS]
    assert stated and stated == exposed
    assert {n for _, n in stated} == {"PAD", "EPAD"}
    rows = {p["refdes"]: p["footprint"] for p in exported.doc["parts"]}
    for ref in ("U301", "U302", "U303", "U305", "U405", "U401"):
        assert any(f == rows[ref] for f, _ in stated), ref


def test_a_pad_named_otherwise_states_no_vias_in_pad():
    assert "vias_in_pad" not in layout_export._footprint("u", [_pad_record(0)])["pads"][0]


def test_the_export_validates_with_pcblayouts_loader(exported):
    model = pytest.importorskip("pcblayout.model")
    d = model.loads(exported.text())
    assert [b.name for b in d.boards] == ["POWER", "OUTPUTS", "LOGIC", "CTRL"]
    assert model.loads(model.dumps(d)) == d


# --- the hook ------------------------------------------------------------------------
def _fuses(design):  # noqa: F811
    return sorted(p.refdes for p in design.parts if p.kind == "FUSE" and not p.dnp)


def test_one_operating_point_per_soft_start_world_and_one_per_fuse(design):  # noqa: F811
    """The 24 soft-start worlds, in their order and unchanged, then one fault
    point per fitted fuse -- nothing else."""
    points = layout_hooks.operating_points()
    worlds = soft_start.operating_points(design)
    names = list(points)
    assert len(points) == len(worlds) + len(_fuses(design))
    assert names[:len(worlds)] == [layout_hooks._name(w) for w in worlds]
    ceiling = soft_start.pack_ceiling_v(design)
    assert names[len(worlds):] == [f"{ceiling:g}V-on-{f}-open" for f in _fuses(design)]
    assert all(row.keys() == facts.hv_node_voltages(design).keys() for row in points.values())
    # the soft-start worlds are exactly soft_start's figures
    ranges = facts.hv_node_voltages(design)
    for i, name in enumerate(names[:len(worlds)]):
        assert all(points[name][n] == v[i] for n, v in ranges.items())


def test_every_fuse_open_stands_the_pack_across_it(design):  # noqa: F811
    """⚠️ Fuse open: the nets either side of every fuse are the pack's
    do-not-exceed apart, and only the load side moves."""
    points = layout_hooks.operating_points()
    ceiling = soft_start.pack_ceiling_v(design)
    assert _fuses(design) == ["F201"]
    for f in _fuses(design):
        row = points[f"{ceiling:g}V-on-{f}-open"]
        a, b = (design.net_of(f, pin).name for pin in ("1", "2"))
        assert abs(row[a] - row[b]) == ceiling
        working = soft_start.hv_node_voltages(design, ceiling, True, False, 0.0)
        moved = sorted(n for n in row if row[n] != working[n])
        assert moved == ["HV_C2_HOLD"]


def test_hv_sw_and_ksw_still_move_together_in_every_point(design):  # noqa: F811
    """The fault point must not pull apart the pair the soft-start worlds keep
    together: `HV_SW` and `KSW` swing as one."""
    points = layout_hooks.operating_points()
    assert max(abs(r["HV_SW"] - r["KSW"]) for r in points.values()) == 0.0


def test_a_fuse_with_a_bypass_is_refused():
    """Fires: a second path round the fuse means it never has the pack across
    it; the point would state a difference the circuit cannot show."""
    joins = [("TAP", "IN", "D1"), ("IN", "OUT", "F1"), ("TAP", "OUT", "R9")]
    with pytest.raises(ValueError, match="F1 open still has both ends fed"):
        layout_hooks._load_side("F1", "IN", "OUT", joins, ["TAP"])


def test_a_fuse_on_no_supply_is_refused():
    joins = [("X", "IN", "D1"), ("IN", "OUT", "F1")]
    with pytest.raises(ValueError, match="F1 open still has neither end fed"):
        layout_hooks._load_side("F1", "IN", "OUT", joins, ["TAP"])


def test_a_fuse_load_side_is_everything_only_it_feeds():
    """Silent, and the answer: the load side is the fuse's far net and what
    hangs off it, and nothing the tap still reaches."""
    joins = [("TAP", "IN", "D1"), ("IN", "OUT", "F1"), ("OUT", "LOAD", "L1"),
             ("TAP", "OTHER", "R1")]
    assert layout_hooks._load_side("F1", "IN", "OUT", joins, ["TAP"]) == {"OUT", "LOAD"}


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
