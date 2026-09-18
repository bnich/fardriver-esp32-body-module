"""V2 footprint -> V3 records, checked against the editor's own conversion.

Three kinds of evidence, strongest last:

  * a SYNTHETIC V2 footprint, written here by hand, whose every expected V3
    payload is spelled out below -- the only one that runs everywhere;
  * a live LCSC library footprint, when this machine has the fixture;
  * the 19 example footprints EasyEDA Pro 3.2 converted itself, compared
    record for record, when this machine has them.

⛔ The last two are vendor material and stay outside this repository.  The
oracle is read straight from EasyEDA's own files: opening the shipped
"Example_Quick Start" project makes the editor convert it, and it keeps the V2
original as `.eprj_backup` beside the V3 `.eprj2`.  EASYEDA_EXAMPLES names that
folder (default ~/Documents/EasyEDA-Pro/example-projects); LCSC_FOOTPRINT_FIXTURE
names the library footprint.  Without them those tests skip.
"""
import collections
import json
import os
import sqlite3
from pathlib import Path

import pytest

from tools.eprj3 import v2footprint as v2
from tools.eprj3.records import serialize_record

EXAMPLES = Path(os.environ.get(
    "EASYEDA_EXAMPLES", Path.home() / "Documents/EasyEDA-Pro/example-projects"))
ORACLE_V2 = EXAMPLES / "Example_Quick Start.eprj_backup"
ORACLE_V3 = EXAMPLES / "Example_Quick Start.eprj2"
LCSC_FIXTURE = Path(os.environ.get(
    "LCSC_FOOTPRINT_FIXTURE",
    Path.home() / "tools/lcsc-search/tests/fixtures/easyeda_component_footprint.json"))

IDENTITY = dict(uuid="0123456789abcdef0123456789abcdef", client="fedcba9876543210",
                epoch_ms=1788000000000)


# --- (a) a synthetic footprint, every payload checked by hand ----------------

#: Two pads, one outline, one attribute.  The POLY sits BETWEEN the pads, so
#: the output has to regroup by type and open a second PAD run.
SYNTHETIC = "\n".join([
    '["DOCTYPE","FOOTPRINT","1.3"]',
    '["LAYER",1,"TOP","Top Layer",3,"#ff0000",1,"#7f0000",1]',
    '["LAYER",3,"TOP_SILK","Top Silkscreen Layer",3,"#ffcc00",1,"#7f6600",1]',
    '["LAYER",12,"MULTI","Multi-Layer",3,"#c0c0c0",1,"#606060",1]',
    '["ACTIVE_LAYER",1]',
    '["PAD","e1",0,"",1,"1",-40,10,0,null,["RECT",30,50],[],0,0,0,1,0,null,null,null,null,0]',
    '["POLY","e2",0,"",3,6,[-80,40,"L",80,40,80,-40,-80,-40,-80,40],0]',
    '["PAD","e3",0,"",12,"2",40,-10,90,["ROUND",20,20],["ELLIPSE",40,40],[],0,0,0,1,0,2,2,0,0,1]',
    '["ATTR","e4",0,"",3,null,null,"Designator","U?",0,0,"default",45,6,0,0,3,0,0,0,0,0]',
    '["CANVAS",0,0,"mil",5,5]',
])


def _layer(lid, ltype, name, active, inactive):
    return {"layerType": ltype, "layerName": name, "use": True, "show": True,
            "locked": False, "activeColor": active, "activateTransparency": 1,
            "inactiveColor": inactive, "inactiveTransparency": 0.5}


def _pad(num, x, y, angle, layer, hole, shape, solder, locked, z):
    return {"groupId": 0, "netName": "", "layerId": layer, "num": num,
            "centerX": x, "centerY": y, "padAngle": angle, "hole": hole,
            "defaultPad": shape, "specialPad": [], "padOffsetX": 0,
            "padOffsetY": 0, "relativeAngle": 0, "plated": True,
            "padType": "NORMAL", "topSolderExpansion": solder,
            "bottomSolderExpansion": solder,
            "topPasteExpansion": 0 if solder is not None else None,
            "bottomPasteExpansion": 0 if solder is not None else None,
            "locked": locked, "zIndex": z, "connectMode": None,
            "spokeSpace": None, "spokeWidth": None, "spokeAngle": None,
            "padLen": 0}


SYNTHETIC_EXPECTED = [
    ({"type": "DOCHEAD"},
     {"docType": "FOOTPRINT", "client": IDENTITY["client"],
      "uuid": IDENTITY["uuid"], "updateTime": 1788000000000,
      "version": "1788000000000", "editVersion": v2.EDIT_VERSION, "user": {}}),
    ({"type": "META", "ticket": 1, "id": "META"},
     {"title": "SYN-2PAD", "description": "", "tags": [], "source": ""}),
    ({"type": "LAYER", "ticket": 2, "id": '["LAYER",1]'},
     _layer(1, "TOP", "Top Layer", "#ff0000", "#7f0000")),
    ({"type": "LAYER", "ticket": 3, "id": '["LAYER",3]'},
     _layer(3, "TOP_SILK", "Top Silkscreen Layer", "#ffcc00", "#7f6600")),
    ({"type": "LAYER", "ticket": 4, "id": '["LAYER",12]'},
     _layer(12, "MULTI", "Multi-Layer", "#c0c0c0", "#606060")),
    ({"type": "ACTIVE_LAYER", "ticket": 5, "id": "ACTIVE_LAYER"},
     {"layerId": 1}),
    ({"type": "CANVAS", "ticket": 6, "id": "CANVAS"},
     {"originX": 0, "originY": 0, "unit": "mil", "gridXSize": 5,
      "gridYSize": 5, "gridType": "NONE", "multiGridType": "NONE",
      "highlightValue": 0.5}),
    # PAD first: it is the first primitive type V2 names.  e1 opens the run.
    ({"type": "ELE_PLACEHOLDER", "ticket": 7, "id": "placeholder1"},
     {"dataType": "PAD", "max": 1}),
    ({"type": "PAD", "ticket": 8, "id": "e1"},
     _pad("1", -40, 10, 0, 1, None,
          {"padType": "RECT", "width": 30, "height": 50}, None, False, 1)),
    # e3 is not e1 + 1: a new run, one element number (e2) skipped.
    ({"type": "ELE_PLACEHOLDER", "ticket": 9, "id": "placeholder2"},
     {"dataType": "PAD", "max": 1}),
    ({"type": "PAD", "ticket": 10, "id": "e3"},
     _pad("2", 40, -10, 90, 12,
          {"holeType": "ROUND", "width": 20, "height": 20},
          {"padType": "ELLIPSE", "width": 40, "height": 40}, 2, True, 3)),
    ({"type": "ELE_PLACEHOLDER", "ticket": 11, "id": "placeholder3"},
     {"dataType": "POLY", "max": 2}),
    ({"type": "POLY", "ticket": 12, "id": "e2"},
     {"groupId": 0, "netName": "", "layerId": 3, "width": 6,
      "path": [-80, 40, "L", 80, 40, 80, -40, -80, -40, -80, 40],
      "locked": False, "zIndex": 2, "polyType": "NORMAL"}),
    ({"type": "ELE_PLACEHOLDER", "ticket": 13, "id": "placeholder4"},
     {"dataType": "ATTR", "max": 4}),
    ({"type": "ATTR", "ticket": 14, "id": "e4"},
     {"groupId": 0, "parentId": "", "layerId": 3, "x": None, "y": None,
      "key": "Designator", "value": "U?", "keyVisible": False,
      "valueVisible": False, "fontFamily": "default", "fontSize": 45,
      "strokeWidth": 6, "bold": False, "italic": False,
      "origin": "LEFT_BOTTOM", "angle": 0, "reverse": False, "expansion": 0,
      "mirror": False, "locked": False, "zIndex": 4}),
]


def convert(text, title="SYN-2PAD", **kw):
    return v2.convert(text, title=title, **IDENTITY, **kw)


def test_synthetic_footprint_converts_exactly_as_worked_by_hand():
    """Byte for byte, so key order and number formatting are checked too."""
    expected = [serialize_record(h, p) for h, p in SYNTHETIC_EXPECTED]
    got = convert(SYNTHETIC)
    assert len(got) == len(expected)
    for g, e in zip(got, expected):
        assert g == e


def test_coordinates_pass_through_without_unit_change_or_y_flip():
    """Footprints keep V2's mil and +Y-up.  (Schematics negate y; that rule
    must not leak in here.)"""
    pads = {p["num"]: p for h, p in v2.parse_records(convert(SYNTHETIC))
            if h["type"] == "PAD"}
    assert (pads["1"]["centerX"], pads["1"]["centerY"]) == (-40, 10)
    assert (pads["2"]["centerX"], pads["2"]["centerY"]) == (40, -10)


def test_blank_lines_and_empty_arrays_carry_nothing():
    lines = SYNTHETIC.split("\n")
    padded = "\n".join([lines[0], "", *lines[1:5], "[]", "  ", *lines[5:], ""])
    assert convert(padded) == convert(SYNTHETIC)


def test_connect_becomes_the_fill_refs_and_leaves_no_record():
    text = SYNTHETIC.replace(
        '["CANVAS"',
        '["FILL","e5",0,"",50,0.2,0,[-50,5,"L",-30,5,-30,-5,-50,-5,-50,5],0]\n'
        '["CONNECT","e5",["e1"]]\n["CANVAS"')
    recs = v2.parse_records(convert(text))
    assert "CONNECT" not in {h["type"] for h, _ in recs}
    fill = [p for h, p in recs if h["type"] == "FILL"]
    assert fill == [{"groupId": 0, "netName": "", "layerId": 50, "width": 0.2,
                     "fillStyle": "SOLID",
                     "path": [-50, 5, "L", -30, 5, -30, -5, -50, -5, -50, 5],
                     "locked": False, "zIndex": 5, "isBridgingCopper": False,
                     "networkList": [], "refs": ["e1"]}]


def test_substrate_layers_are_renumbered_into_v3s_range():
    text = SYNTHETIC.replace(
        '["ACTIVE_LAYER"',
        '["LAYER",101,"SUBSTRATE","SUBSTRATE1",0,"#000000",1,"#000000",1]\n'
        '["ACTIVE_LAYER"')
    layers = [(h["id"], p["use"]) for h, p in v2.parse_records(convert(text))
              if h["type"] == "LAYER"]
    assert layers[-1] == ('["LAYER",361]', False)


# --- (d) what is not understood raises ----------------------------------------

@pytest.mark.parametrize("change, message", [
    (('["CANVAS"', '["VIA","e9",0,"",0,0,0,20,10,0]\n["CANVAS"'),
     "record type 'VIA'"),
    (('["CANVAS"', '["HEAD",{"editorVersion":"4.7.8"}]\n["CANVAS"'),
     "record type 'HEAD'"),
    (('0,0,3,0,0,0,0,0]', '0,0,5,0,0,0,0,0]'), "text alignment 5"),
    (('["ROUND",20,20]', '["RECT",20,20]'), "hole"),
    (('["RECT",30,50]', '["POLY",[["L",1,1,3,3]]]'), "pad shape"),
    (('["CANVAS"', '["CONNECT","e2",["e1"]]\n["CANVAS"'), "not FILLs"),
    (('["CANVAS"', '[7,"x"]\n["CANVAS"'), "no type string"),
])
def test_anything_not_seen_converted_raises(change, message):
    old, new = change
    assert old in SYNTHETIC
    with pytest.raises(v2.V2FootprintError, match=message):
        convert(SYNTHETIC.replace(old, new, 1))


# --- (c) a live LCSC library footprint ----------------------------------------

def test_a_live_lcsc_footprint_converts_with_its_pads():
    if not LCSC_FIXTURE.is_file():
        pytest.skip(f"no LCSC footprint fixture at {LCSC_FIXTURE}")
    doc = json.loads(LCSC_FIXTURE.read_text())["result"]
    text = doc["dataStr"]
    raw = [json.loads(line) for line in text.split("\n") if line.strip()]
    assert [] in raw, "the fixture's empty-array line is what this exercises"
    assert sum(r[:1] == ["ACTIVE_LAYER"] for r in raw) == 2
    v2_pads = {r[5]: (r[6], r[7]) for r in raw if r[:1] == ["PAD"]}

    recs = v2.parse_records(v2.convert(text, title=doc["display_title"],
                                       **IDENTITY))
    pads = [p for h, p in recs if h["type"] == "PAD"]
    # MSOP/HVSSOP-8 with an exposed thermal pad: pins 1..8 plus pad 9.
    assert sorted(p["num"] for p in pads) == [str(i) for i in range(1, 10)]
    assert {p["num"]: (p["centerX"], p["centerY"]) for p in pads} == v2_pads
    assert [h["type"] for h, _ in recs].count("ACTIVE_LAYER") == 1


# --- (b) the editor's own conversion of 19 footprints --------------------------

def _editor_footprints():
    """uuid -> the editor's V3 records for each FOOTPRINT in the converted
    project, as raw record strings: split, never re-serialised.

    A project the editor converted IN PLACE carries each document's DOCHEAD
    more than once (its migration history); a saved copy carries one.  The
    records after the first are otherwise identical -- checked on all 19 --
    so only the first DOCHEAD is kept."""
    pytest.importorskip("cryptography")
    from tools import eprj2
    text = eprj2.read(ORACLE_V3)["text"]
    out, cur = {}, None
    for rec in text.split("|\n"):
        head, _, payload = rec.partition("||")
        if json.loads(head)["type"] == "DOCHEAD":
            body = json.loads(payload)
            if body["docType"] != "FOOTPRINT":
                cur = None
            elif body["uuid"] in out:
                cur = out[body["uuid"]]
                continue                      # a repeated DOCHEAD: history
            else:
                cur = out.setdefault(body["uuid"], [])
        if cur is not None:
            cur.append(rec)
    return out


def _oracle_pairs():
    db = ORACLE_V2
    if not (ORACLE_V2.is_file() and ORACLE_V3.is_file()):
        pytest.skip(f"no editor-converted example project under {EXAMPLES}")
    v3 = _editor_footprints()
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select uuid, display_title, description, source, dataStr "
            "from components where docType = 4 order by uuid").fetchall()
    finally:
        con.close()
    for uuid, title, description, source, text in rows:
        yield uuid, title, description, source, text, v3[uuid]


def _meta_moved_to_front(theirs):
    """The editor's records with META directly after DOCHEAD.

    The oracle files were cut out of a whole-PROJECT history stream.  There,
    DOCHEAD and META take their tickets from the project's counter (every
    DOCHEAD is 3 above the previous document's; META is DOCHEAD + 2) while
    every other record is numbered 1..N within its document, and the stream is
    written in ticket order.  So META lands wherever its project ticket falls
    among the document's own records -- among the LAYERs in one file, after
    the last ATTR in another.  That position says nothing about the footprint;
    this asserts the explanation holds before relying on it.
    """
    heads = [json.loads(r.partition("||")[0]) for r in theirs]
    assert heads[0]["type"] == "DOCHEAD"
    meta = [i for i, h in enumerate(heads) if h["type"] == "META"]
    assert len(meta) == 1
    i = meta[0]
    assert heads[i]["ticket"] == heads[0]["ticket"] + 2
    own = [h["ticket"] for h in heads[1:] if h["type"] != "META"]
    assert own == list(range(1, len(own) + 1))
    return [theirs[0], theirs[i], *theirs[1:i], *theirs[i + 1:]]


def test_all_19_example_footprints_match_the_editors_conversion():
    total, matched, identical = (collections.Counter() for _ in range(3))
    failures = []
    pairs = list(_oracle_pairs())
    assert len(pairs) == 19
    for uuid, title, description, source, text, theirs in pairs:
        theirs = _meta_moved_to_front(theirs)
        ours = v2.convert(text, uuid=uuid, title=title, client="x",
                          epoch_ms=1, description=description, source=source)
        failures += [f"{title}: {d}" for d in v2.record_diff(ours, theirs)]
        for o, t, (head, _) in zip(ours, theirs, v2.parse_records(theirs)):
            kind = head["type"]
            total[kind] += 1
            matched[kind] += not v2.record_diff([o], [t])
            # Stronger than required: identical payload TEXT (key order and
            # number formatting) and identical record id.  DOCHEAD's payload
            # is identity only and is excluded.
            oh, _, op = o.partition("||")
            th, _, tp = t.partition("||")
            identical[kind] += (kind == "DOCHEAD" or (
                op == tp and json.loads(oh).get("id") == json.loads(th).get("id")))
    rates = {k: f"{matched[k]}/{total[k]}" for k in total}
    print("\nper-type match:", rates)
    assert not failures, "\n".join(failures[:20])
    assert matched == total and identical == total
    # The record set the task was specified against, so a silently shrunken
    # comparison cannot pass.
    assert total == {"LAYER": 2204, "POLY": 152, "FILL": 128,
                     "ELE_PLACEHOLDER": 111, "PAD": 58, "ATTR": 38,
                     "DOCHEAD": 19, "META": 19, "ACTIVE_LAYER": 19,
                     "CANVAS": 19}
