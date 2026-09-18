"""The PCB document: what it measures, not just what it contains.

⛔ THE FAILURE THIS FILE EXISTS TO CATCH IS A BOARD THAT IS TEN TIMES TOO BIG.
PCB documents are in mil and schematic documents in 0.01 inch, and the vendor's
own prose says 0.01 inch for both. A board written in the wrong unit opens
cleanly, looks right, and is 420 x 1860 mm. So the outline is not tested for
"a POLY on layer 11 exists" -- it is converted back to millimetres and compared
against `board_params`, which is the envelope the enclosure budget proved.

Everything else here follows the same rule: measure the outcome, not the
mechanism. Four PAD records is not four mounting holes; four non-plated
3.2 mm drills at the four corners of the board is.
"""
import json

import pytest

from tools.board_params import BOARD_L, BOARD_W
from tools.eprj3.pcb import (
    BOTTOM_COPPER, DesignRules, M3_CLEARANCE_MM, M3_INSET_MM, MULTI_LAYER,
    OUTLINE_LAYER, SAFE_SPACING_CLASSES, SUBSTRATE_LAYER, Pcb, Stackup,
    dim_colour,
)
from tools.eprj3.units import PCB_MM_PER_UNIT, mm_to_pcb, pcb_to_mm

#: The file carries 4 decimals of a mil, so a value converted to units and back
#: can be out by half of that -- 0.00005 mil, or 1.27e-6 mm. Anything bigger is
#: a real error, and the errors this file guards against are 10x and 39x.
ROUND_TRIP_TOLERANCE_MM = 0.5e-4 * PCB_MM_PER_UNIT


def make_pcb(**kwargs):
    return Pcb("PCB1", "1111111111111111", "2222222222222222",
               "3333333333333333", 1788000000000, **kwargs)


def parse_document(text):
    pairs = []
    for record in text.split("|\n"):
        header, sep, body = record.partition("||")
        assert sep == "||", f"record without a '||' separator: {record[:60]!r}"
        pairs.append((json.loads(header), json.loads(body) if body else None))
    return pairs


def rejoin(pairs):
    def compact(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return "|\n".join(
        compact(head) + "||" + ("" if body is None else compact(body))
        for head, body in pairs)


def bodies(records, type_):
    return [body for head, body in records if head["type"] == type_]


@pytest.fixture
def records():
    return parse_document(make_pcb().document())


# --- the outline: the measurement the whole module is for --------------------
def test_there_is_exactly_one_board_outline(records):
    outlines = [b for b in bodies(records, "POLY")
                if b["polyType"] == "BOARD_OUTLINE"]
    assert len(outlines) == 1
    assert outlines[0]["layerId"] == OUTLINE_LAYER
    assert outlines[0]["netName"] == ""
    assert outlines[0]["locked"] is False


def test_the_outline_measures_the_board_params_envelope(records):
    outline = next(b for b in bodies(records, "POLY"))
    kind, x, y, width, height, rotation, ccw = outline["path"]
    assert kind == "R"

    # ⛔ The point of the whole test file. Read the emitted numbers back
    # through the PCB conversion and they must be the envelope in mm.
    assert pcb_to_mm(width) == pytest.approx(BOARD_W, abs=ROUND_TRIP_TOLERANCE_MM)
    assert pcb_to_mm(height) == pytest.approx(BOARD_L, abs=ROUND_TRIP_TOLERANCE_MM)
    # and exactly, at the 4-decimal precision the file actually carries
    assert round(pcb_to_mm(width), 4) == BOARD_W
    assert round(pcb_to_mm(height), 4) == BOARD_L
    assert rotation == 0 and ccw == 0


def test_the_outline_is_not_ten_times_too_big(records):
    # The mistake this catches reads the vendor prose (0.01 inch) instead of
    # the file (1 mil). It produces a board larger than A4 and opens cleanly.
    outline = next(b for b in bodies(records, "POLY"))
    _, _, _, width, height, _, _ = outline["path"]
    assert width == pytest.approx(mm_to_pcb(BOARD_W), abs=1e-3)
    assert height == pytest.approx(mm_to_pcb(BOARD_L), abs=1e-3)


def test_the_board_sits_in_the_first_quadrant_with_its_corner_on_the_origin(records):
    # "R" gives the TOP-LEFT corner and +Y is up, so y is the board's height
    # and the board covers y in [0, height].
    outline = next(b for b in bodies(records, "POLY"))
    _, x, y, width, height, _, _ = outline["path"]
    assert x == 0
    assert y == height
    assert y - height == 0


def test_a_deliberately_different_envelope_is_honoured():
    # Proves the outline is computed, not a constant: board_params is the one
    # home for the standard envelope, but the class is not welded to it.
    pcb = make_pcb(width_mm=20.0, length_mm=30.0, hole_inset_mm=3.0)
    outline = next(b for b in bodies(parse_document(pcb.document()), "POLY"))
    _, _, _, width, height, _, _ = outline["path"]
    assert round(pcb_to_mm(width), 4) == 20.0
    assert round(pcb_to_mm(height), 4) == 30.0


def test_the_outline_stroke_is_a_quarter_millimetre(records):
    outline = next(b for b in bodies(records, "POLY"))
    assert round(pcb_to_mm(outline["width"]), 3) == 0.254


# --- mounting holes ---------------------------------------------------------
def test_there_are_four_mounting_holes(records):
    pads = bodies(records, "PAD")
    assert len(pads) == 4
    assert all(p["layerId"] == MULTI_LAYER for p in pads)


def test_each_hole_is_a_3_2_mm_m3_clearance_drill(records):
    for pad in bodies(records, "PAD"):
        assert pad["hole"]["holeType"] == "ROUND"
        diameter = round(pcb_to_mm(pad["hole"]["width"]), 4)
        assert diameter == M3_CLEARANCE_MM
        assert pad["hole"]["height"] == pad["hole"]["width"]   # round, not a slot


def test_each_hole_is_non_plated_with_no_annular_ring(records):
    # Copper exactly the size of the drill means nothing survives the drill,
    # which is what makes it a mounting hole rather than a big via.
    for pad in bodies(records, "PAD"):
        assert pad["plated"] is False
        assert pad["defaultPad"]["width"] == pad["hole"]["width"]
        assert pad["defaultPad"]["height"] == pad["hole"]["height"]
        assert pad["netName"] == ""


def test_the_holes_are_one_at_each_corner_of_the_board(records):
    centres = sorted((round(pcb_to_mm(p["centerX"]), 3),
                      round(pcb_to_mm(p["centerY"]), 3))
                     for p in bodies(records, "PAD"))
    near, far_x, far_y = M3_INSET_MM, BOARD_W - M3_INSET_MM, BOARD_L - M3_INSET_MM
    assert centres == [(near, near), (near, far_y), (far_x, near), (far_x, far_y)]


def test_the_holes_are_inset_from_the_edge_that_is_actually_written(records):
    # The inset must be exact against the ROUNDED board edge in the file, not
    # against the unrounded ideal, or the far holes drift by a rounding step.
    outline = next(b for b in bodies(records, "POLY"))
    _, _, _, width, height, _, _ = outline["path"]
    inset = mm_to_pcb(M3_INSET_MM)
    xs = {p["centerX"] for p in bodies(records, "PAD")}
    ys = {p["centerY"] for p in bodies(records, "PAD")}
    assert max(xs) == pytest.approx(width - inset, abs=1e-4)
    assert max(ys) == pytest.approx(height - inset, abs=1e-4)


def test_a_hole_that_falls_off_the_board_is_refused():
    with pytest.raises(ValueError, match="inside the board edge"):
        make_pcb(hole_inset_mm=1.0)
    with pytest.raises(ValueError, match="does not fit"):
        make_pcb(hole_inset_mm=BOARD_W)


# --- the stackup ------------------------------------------------------------
def test_the_stackup_is_two_copper_layers(records):
    phys = {json.loads(head["id"])[1]: body
            for head, body in records if head["type"] == "LAYER_PHYS"}
    # silk, paste, mask, copper, substrate, copper, mask, paste, silk
    assert len(phys) == 9
    assert sorted(phys) == [1, 2, 3, 4, 5, 6, 7, 8, SUBSTRATE_LAYER]
    assert phys[1]["zIndex"] == 1000                 # top copper
    assert phys[SUBSTRATE_LAYER]["zIndex"] == 1001   # the single dielectric
    assert phys[BOTTOM_COPPER]["zIndex"] == 9000     # bottom copper


def test_the_stack_z_indices_run_top_to_bottom(records):
    phys = [(body["zIndex"], json.loads(head["id"])[1])
            for head, body in records if head["type"] == "LAYER_PHYS"]
    assert phys == sorted(phys), "LAYER_PHYS records must be in stack order"


def test_the_board_is_1_6_mm_of_fr4_in_1_oz_copper(records):
    phys = {json.loads(head["id"])[1]: body
            for head, body in records if head["type"] == "LAYER_PHYS"}
    copper = pcb_to_mm(phys[1]["thickness"])
    assert round(copper, 4) == 0.035                  # 35 um == 1 oz
    total = sum(pcb_to_mm(phys[i]["thickness"])
                for i in (1, SUBSTRATE_LAYER, BOTTOM_COPPER))
    assert total == pytest.approx(1.58, abs=0.005)
    assert Stackup().board_thickness_mm == pytest.approx(1.58, abs=0.005)
    assert phys[SUBSTRATE_LAYER]["material"] == "FR4"
    assert phys[SUBSTRATE_LAYER]["permittivity"] == 4.5


def test_a_thicker_stack_moves_the_thickness_not_the_structure():
    pcb = make_pcb(stackup=Stackup(dielectric_mm=0.76))
    phys = {json.loads(head["id"])[1]: body
            for head, body in parse_document(pcb.document())
            if head["type"] == "LAYER_PHYS"}
    assert round(pcb_to_mm(phys[SUBSTRATE_LAYER]["thickness"]), 3) == 0.76
    assert len(phys) == 9


# --- the layer table --------------------------------------------------------
def test_the_layer_table_covers_every_layer_the_editor_expects(records):
    layers = {body["layerId"]: body for body in bodies(records, "LAYER")}
    assert len(layers) == 60
    assert set(layers) == set(range(1, 60)) | {SUBSTRATE_LAYER}
    assert layers[OUTLINE_LAYER]["layerType"] == "OUTLINE"
    assert layers[MULTI_LAYER]["layerType"] == "MULTI"
    assert layers[1]["layerType"] == "TOP" and layers[1]["use"] is True
    assert layers[2]["layerType"] == "BOTTOM" and layers[2]["use"] is True


def test_the_thirty_two_inner_layers_are_present_but_unused(records):
    layers = {body["layerId"]: body for body in bodies(records, "LAYER")}
    inner = [layers[i] for i in range(15, 47)]
    assert len(inner) == 32
    assert all(layer["layerType"] == "SIGNAL" for layer in inner)
    assert all(layer["use"] is False and layer["show"] is False
               for layer in inner), "a 2-layer board must not enable an inner"
    assert [layer["layerName"] for layer in inner] == \
        [f"Inner{i}" for i in range(1, 33)]


def test_every_layer_colour_is_a_well_formed_hex_triple(records):
    for layer in bodies(records, "LAYER"):
        for key in ("activeColor", "inactiveColor"):
            value = layer[key]
            assert len(value) == 7 and value[0] == "#", (layer["layerId"], key)
            int(value[1:], 16)       # raises on the editor's own "#a.492f" bug


def test_the_inactive_colour_is_the_active_one_halved(records):
    for layer in bodies(records, "LAYER"):
        assert layer["inactiveColor"] == dim_colour(layer["activeColor"])
    assert dim_colour("#ff0000") == "#7f0000"
    assert dim_colour("#66cc33") == "#336619"
    assert dim_colour("#000000") == "#000000"


def test_only_the_solder_masks_are_drawn_transparent(records):
    for layer in bodies(records, "LAYER"):
        expected = 0.7 if layer["layerId"] in (5, 6) else 1
        assert layer["activateTransparency"] == expected, layer["layerId"]
        assert layer["inactiveTransparency"] == 1


# --- design rules -----------------------------------------------------------
def rule(records, cls, name):
    for head, body in records:
        if head["type"] == "RULE" and json.loads(head["id"])[1:] == [cls, name]:
            return body
    raise AssertionError(f"no RULE {cls}/{name}")


def test_the_clearance_rule_is_board_wide(records):
    body = rule(records, "SAFE", "copperThickness1oz")
    assert body["ruleState"] == "DEFAULT"
    context = body["ruleContext"]
    assert context["isForAll"] == "ALL", "one matrix must cover every layer"
    assert len(context["safeSpacing"]) == 1


def test_the_clearance_matrix_is_uniform_and_lower_triangular(records):
    # ⚠️ Nothing documents which object class each row is, and columnNames is
    # empty. A uniform matrix is the only clearance that cannot be wrong.
    content = rule(records, "SAFE",
                   "copperThickness1oz")["ruleContext"]["safeSpacing"][0]["content"]
    assert len(content) == SAFE_SPACING_CLASSES == 13
    assert [len(row) for row in content] == list(range(1, 14))
    values = {cell for row in content for cell in row}
    assert len(values) == 1
    assert round(pcb_to_mm(values.pop()), 4) == 0.2


def test_the_clearance_rule_follows_its_parameter():
    pcb = make_pcb(rules=DesignRules(clearance_mm=0.15))
    content = rule(parse_document(pcb.document()), "SAFE",
                   "copperThickness1oz")["ruleContext"]["safeSpacing"][0]["content"]
    assert round(pcb_to_mm(content[0][0]), 4) == 0.15


def test_rule_numbers_are_mil_even_though_the_rule_says_mm(records):
    # ⚠️ "unit":"mm" beside a number that is in mil is the format's nastiest
    # trap: believing it makes every clearance 39x too small.
    body = rule(records, "OTHER", "otherClearance")
    assert body["ruleContext"]["unit"] == "mm"
    assert round(pcb_to_mm(body["ruleContext"]["holeClearance"]), 4) == 0.3
    track = rule(records, "TRACK", "copperThickness1oz")
    row = track["ruleContext"]["track"]["content"][0]
    assert round(pcb_to_mm(row["stroMin"]), 4) == 0.127
    assert round(pcb_to_mm(row["stroDef"]), 4) == 0.254
    assert round(pcb_to_mm(row["stroMax"]), 4) == 2.54


def test_the_default_via_the_editor_offers_satisfies_the_via_rule(records):
    radius = rule(records, "RADIUS", "viaSize")["ruleContext"]
    preference = bodies(records, "PREFERENCE")[0]
    assert preference["lastViaDiameter"] == pytest.approx(
        2 * radius["defRadius"], abs=1e-4)
    assert preference["lastViaInnerDiameter"] == pytest.approx(
        2 * radius["defInner"], abs=1e-4)
    assert radius["minRadius"] <= radius["defRadius"] <= radius["maxRadius"]


def test_there_is_exactly_one_default_rule_per_class(records):
    defaults = {}
    for head, body in records:
        if head["type"] != "RULE":
            continue
        cls = json.loads(head["id"])[1]
        if body["ruleState"] == "DEFAULT":
            assert cls not in defaults, f"two defaults for {cls}"
            defaults[cls] = body
    assert "SAFE" in defaults and "TRACK" in defaults


def test_no_blind_vias_on_a_two_layer_board(records):
    assert rule(records, "BLIND", "blindVia")["ruleContext"]["blinds"]["content"] == []


def test_the_autorouter_is_limited_to_the_two_copper_layers(records):
    layers = rule(records, "AUTO_ROUTER", "Common")["ruleContext"]["layers"]
    assert layers == [1, 2, MULTI_LAYER]


# --- the record grammar and document shape ----------------------------------
def test_the_document_opens_with_dochead_then_meta(records):
    assert records[0][0] == {"type": "DOCHEAD"}
    assert records[0][1]["docType"] == "PCB"
    assert records[1][0]["type"] == "META" and records[1][0]["id"] == "META"


def test_tickets_are_unique_and_sequential_after_dochead(records):
    tickets = [head["ticket"] for head, _ in records if "ticket" in head]
    assert tickets == list(range(1, len(records)))
    assert len(set(tickets)) == len(tickets)


def test_geometry_comes_last(records):
    types = [head["type"] for head, _ in records]
    assert types[-5:] == ["POLY", "PAD", "PAD", "PAD", "PAD"]


def test_a_config_record_id_is_a_compact_json_array(records):
    for head, _ in records:
        id_ = head.get("id", "")
        if id_.startswith("["):
            assert ", " not in id_ and '": ' not in id_
            assert json.dumps(json.loads(id_), separators=(",", ":")) == id_


def test_a_drawn_primitive_id_is_sixteen_lowercase_hex(records):
    drawn = [head["id"] for head, _ in records
             if head["type"] in ("POLY", "PAD")]
    assert len(drawn) == 5
    assert len(set(drawn)) == 5
    for id_ in drawn:
        assert len(id_) == 16
        int(id_, 16)
        assert id_ == id_.lower()


def test_every_record_round_trips_byte_for_byte():
    text = make_pcb().document()
    assert rejoin(parse_document(text)) == text


def test_the_document_has_no_trailing_separator_or_newline():
    text = make_pcb().document()
    assert not text.endswith("|")
    assert not text.endswith("\n")
    assert text.count("|\n") == len(parse_document(text)) - 1


def test_the_separator_is_formatted_in_records_py_and_nowhere_else():
    # One joiner, one home. A second copy of the separator is a second chance
    # to put a `|` after the last record, which costs the file its last record
    # without an error.
    import inspect
    from tools.eprj3 import pcb, records
    assert pcb.join_records is records.join_records
    source = inspect.getsource(pcb)
    assert '"|\\n"' not in source and "'|\\n'" not in source
    assert "def join_records" not in source


def test_no_record_has_an_empty_body():
    # Empty-body records occur in real files and are most likely deletion
    # tombstones. A generator must never emit one.
    for head, body in parse_document(make_pcb().document()):
        assert body is not None, head


def test_two_runs_produce_the_same_bytes():
    assert make_pcb().document() == make_pcb().document()
    assert Pcb("A", "1" * 16, "2" * 16, "3" * 16, 1).document() != \
        Pcb("B", "1" * 16, "2" * 16, "3" * 16, 1).document()
