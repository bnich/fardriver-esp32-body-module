"""Symbols: the pins are where the netlist says, on the grid, facing the right
way, and each one's `Pin Number` is the netlist's own pin id.

A symbol is where a wrong pin rotation or an off-grid anchor would hide: the
sheet would still open and draw, with every wire a hair away from its pin.  So
the invariants are tested here directly, and `check_symbol` -- the guard the
emitter runs on every symbol it embeds -- is shown to FIRE on each defect it
exists to catch.
"""
import json
from dataclasses import replace

import pytest

from tools import netlist
from tools.eprj3 import symbols as sym
from tools.eprj3.schematic import place_point

DESIGN = netlist.current()


def all_symbols():
    """Every distinct symbol the real design needs, flags included."""
    out = {}
    for p in DESIGN.parts:
        s = sym.for_part(p)
        out[s.key] = s
    for c in DESIGN.connectors:
        s = sym.for_connector(c)
        out[s.key] = s
    for n in DESIGN.nets:
        s = sym.net_flag(n.name)
        out[s.key] = s
    return list(out.values())


SYMBOLS = all_symbols()


def parse(records):
    out = []
    for r in records:
        head, sep, body = r.partition("||")
        assert sep
        out.append((json.loads(head), json.loads(body) if body else None))
    return out


# --- invariants on every real symbol -----------------------------------------
def test_every_symbol_passes_its_own_guard():
    problems = [p for s in SYMBOLS for p in sym.check_symbol(s)]
    assert problems == []


@pytest.mark.parametrize("origin", [(0, 0), (130, -470), (2240, -1130)])
@pytest.mark.parametrize("rotation", [0, 180])
def test_every_anchor_lands_on_the_grid_after_placement(origin, rotation):
    off = []
    for s in SYMBOLS:
        for p in s.pins:
            x, y = place_point(p.x, p.y, *origin, rotation)
            if not (isinstance(x, int) and isinstance(y, int)
                    and x % sym.GRID == 0 and y % sym.GRID == 0):
                off.append((s.title, p.number, x, y))
    assert off == []


@pytest.mark.parametrize("part", DESIGN.parts, ids=lambda p: p.refdes)
def test_part_symbol_carries_exactly_the_parts_pins(part):
    numbers = [p.number for p in sym.for_part(part).pins]
    assert sorted(numbers) == sorted(part.pins + part.nc)
    assert len(numbers) == len(set(numbers))


@pytest.mark.parametrize("conn", DESIGN.connectors, ids=lambda c: c.refdes)
def test_connector_symbol_carries_exactly_its_table(conn):
    numbers = [p.number for p in sym.for_connector(conn).pins]
    assert sorted(numbers) == sorted(cp.pin for cp in conn.pins)


def test_every_pin_faces_left_or_right_only():
    # The emitter uses rotations 0 and 180 only, which are handedness-free
    # (spec §9).  A pin on a top or bottom edge would need 90/270 stubs.
    for s in SYMBOLS:
        for p in s.pins:
            assert p.rotation in (sym.FACES_LEFT, sym.FACES_RIGHT), s.title


# --- the verified pin convention (§5.5, §10) ----------------------------------
def test_resistor_matches_the_verified_two_resistor_example_geometry():
    r = sym.for_part(DESIGN.part("R110"))
    one, two = r.pin("1"), r.pin("2")
    assert (one.x, one.y, one.rotation) == (-20, 0, 0)
    assert (two.x, two.y, two.rotation) == (20, 0, 180)


def test_pin_line_runs_from_anchor_to_body():
    # file rotation 0 -> line runs +X, 180 -> -X (spec §5.5).  The drawn end
    # must land on the body edge; a V2-minded 180 flip would miss by 2 x L.
    for s in SYMBOLS:
        if s.doc_type == sym.DOC_NETFLAG:
            continue
        bx1, _, bx2, _ = s.body
        for p in s.pins:
            inner = p.x + (p.length if p.rotation == 0 else -p.length)
            assert inner == (bx1 if p.rotation == 0 else bx2), (s.title, p)


@pytest.mark.parametrize("kind", ["D", "ZENER", "TVS"])
def test_diode_polarity_anode_left_cathode_right(kind):
    for pins in (("A", "K"), ("K", "A")):
        s = sym._part_symbol(kind, pins)
        assert s.pin("A").x < 0 < s.pin("K").x


def test_polarised_cap_plus_on_the_left():
    part = next(p for p in DESIGN.parts if p.kind == "C" and "+" in p.pins)
    s = sym.for_part(part)
    assert s.pin("+").x < 0 < s.pin("-").x
    assert s.title == "C_POL"


def test_fet_gate_left_drain_and_source_right():
    for kind in ("NFET", "PFET"):
        s = sym._part_symbol(kind, ("G", "D", "S"))
        assert s.pin("G").x < 0
        assert s.pin("D").x > 0 and s.pin("S").x > 0
        assert s.pin("D").y < s.pin("S").y      # drain above source


def test_nc_pins_are_drawn_on_the_symbol():
    u401 = DESIGN.part("U401")
    numbers = {p.number for p in sym.for_part(u401).pins}
    assert set(u401.nc) <= numbers


def test_box_is_sized_so_names_fit():
    s = sym.for_part(DESIGN.part("U401"))
    bx1, _, bx2, _ = s.body
    left = max(len(p.name) for p in s.pins if p.rotation == 0)
    right = max(len(p.name) for p in s.pins if p.rotation == 180)
    assert bx2 - bx1 >= (left + right) * sym.CHAR_W


def test_symbol_is_a_pure_function_of_its_key():
    for p in DESIGN.parts:
        assert sym.for_part(p) == sym.for_part(p)
        assert sym.for_part(p).key == sym.part_key(p)


# --- net flags --------------------------------------------------------------
def test_flag_is_a_netflag_with_one_pin_at_the_origin():
    for name in ("GND", "V12", "HV_BPLUS", "IN01_TURN_L_WIRE"):
        f = sym.net_flag(name)
        assert f.doc_type == 18
        assert f.global_net_name == name
        assert [(p.x, p.y) for p in f.pins] == [(0, 0)]


def test_flag_styles():
    assert sym.flag_style("GND") == "ground"
    for rail in ("V12", "V5", "V3P3", "HV_BPLUS"):
        assert sym.flag_style(rail) == "rail"
    assert sym.flag_style("SDA") == "tag"


def test_flag_glyph_is_symmetric_about_its_axis():
    # Rotation 180 must draw the mirror image, which needs y-symmetry.
    for name in ("GND", "V5", "SDA"):
        pts = sorted((x, y) for g in sym.net_flag(name).graphics
                     for x, y in sym._points_of(g))
        assert pts == sorted((x, -y) for x, y in pts), name


# --- the documents ----------------------------------------------------------
def symbol_doc(symbol):
    return parse(sym.symbol_records(symbol, "a" * 16, client="c" * 16,
                                    epoch_ms=1788000000000))


@pytest.mark.parametrize("symbol", SYMBOLS[:40] + SYMBOLS[-5:],
                         ids=lambda s: s.title)
def test_symbol_document_structure(symbol):
    recs = symbol_doc(symbol)
    head, body = recs[0]
    assert head == {"type": "DOCHEAD"}
    assert body["docType"] == "SYMBOL" and body["uuid"] == "a" * 16
    types = [h["type"] for h, _ in recs[1:]]
    assert types[:3] == ["META", "CANVAS", "PART"]
    assert recs[1][1]["docType"] == symbol.doc_type
    assert recs[1][1]["source"] == ""
    part_id = recs[3][0]["id"]
    tickets = [h["ticket"] for h, _ in recs[1:]]
    ids = [h["id"] for h, _ in recs[1:]]
    assert len(set(tickets)) == len(tickets)
    assert len(set(ids)) == len(ids)
    pins = {h["id"]: b for h, b in recs if h["type"] == "PIN"}
    attrs = [b for h, b in recs if h["type"] == "ATTR"]
    for h, b in recs[4:]:
        if h["type"] in ("RECT", "POLY", "ARC", "PIN"):
            assert b["partId"] == part_id
        if h["type"] == "POLY":
            assert all(set(p) == {"x", "y"} for p in b["points"])
    for pid in pins:
        keys = sorted(a["key"] for a in attrs if a["parentId"] == pid)
        assert keys == ["Pin Name", "Pin Number", "Pin Type"]
    numbers = sorted(a["value"] for a in attrs if a["key"] == "Pin Number")
    assert numbers == sorted(p.number for p in symbol.pins)


def test_device_document_binds_its_symbol():
    s = sym.for_part(DESIGN.part("U401"))
    recs = parse(sym.device_records(s, "d" * 16, "a" * 16, client="c" * 16,
                                    epoch_ms=1788000000000))
    assert len(recs) == 2
    attrs = recs[1][1]["attributes"]
    assert attrs["Symbol"] == "a" * 16
    assert attrs["Footprint"] == ""           # no footprint bound
    assert json.loads(attrs["SymbolName"])["uuid"] == "a" * 16
    assert "Global Net Name" not in attrs


def test_flag_device_carries_the_global_net_name():
    recs = parse(sym.device_records(sym.net_flag("SDA"), "d" * 16, "a" * 16,
                                    client="c" * 16, epoch_ms=1))
    assert recs[1][1]["attributes"]["Global Net Name"] == "SDA"


# --- the guard fires --------------------------------------------------------
def test_guard_fires_on_an_off_grid_pin():
    s = sym.for_part(DESIGN.part("R110"))
    bad = replace(s, pins=(replace(s.pins[0], x=-25),) + s.pins[1:])
    assert any("grid" in p for p in sym.check_symbol(bad))


def test_guard_fires_on_a_pin_facing_up():
    s = sym.for_part(DESIGN.part("R110"))
    bad = replace(s, pins=(replace(s.pins[0], rotation=90),) + s.pins[1:])
    assert any("faces up or down" in p for p in sym.check_symbol(bad))


def test_guard_fires_on_a_v2_style_flipped_rotation():
    # The V2 convention is 180 degrees off: the line would run away from the
    # body.  This is the defect the spec warns detaches every pin.
    s = sym.for_part(DESIGN.part("R110"))
    bad = replace(s, pins=(replace(s.pins[0], rotation=180),) + s.pins[1:])
    assert sym.check_symbol(bad)


def test_guard_fires_on_a_duplicate_pin_number():
    s = sym.for_part(DESIGN.part("R110"))
    bad = replace(s, pins=(s.pins[0], replace(s.pins[1], number="1")))
    assert any("twice" in p for p in sym.check_symbol(bad))
