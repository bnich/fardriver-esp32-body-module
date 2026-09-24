"""The project index is a web of uuid cross-references with nothing to check it.

Nothing in the `.eprj3` format validates that `profile.sheets[].schematic_uuid`
names a schematic that exists, or that a PCB and a schematic agree about which
board they belong to. A project with a broken link still opens -- it just opens
with a board that has silently lost its PCB. So the referential integrity of
the index is tested here directly, field by field, rather than trusting the
generator's own `referential_errors()` to be the whole story.

The second thing these tests pin is DETERMINISM. Every uuid is a SHA-1 of a
namespaced name and every timestamp comes from a stated constant, so two runs
must produce byte-identical trees. That is the only cheap way to tell a
regenerated project from a changed one.
"""
import json
import re

import pytest

from tools.board_params import STACK_ORDER
from tools.eprj3.project import DEFAULT_EPOCH_MS, Project

HEX16 = re.compile(r"^[0-9a-f]{16}$")
HEX32 = re.compile(r"^[0-9a-f]{32}$")


def parse_document(text):
    """Split a document into (header, body) pairs using the record grammar.

    Raises rather than returning junk: a document that does not split cleanly
    is a defect, not a test result.
    """
    pairs = []
    for record in text.split("|\n"):
        header, sep, body = record.partition("||")
        assert sep == "||", f"record without a '||' separator: {record[:60]!r}"
        pairs.append((json.loads(header), json.loads(body) if body else None))
    return pairs


def rejoin(pairs):
    """Re-serialise parsed records back into a document body."""
    def compact(obj):
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return "|\n".join(
        compact(head) + "||" + ("" if body is None else compact(body))
        for head, body in pairs)


@pytest.fixture
def project():
    project = Project("esp32-body-module")
    project.add_board("POWER")
    project.add_board("LOGIC", sheets=("P1", "P2"))
    return project


# --- the tree ---------------------------------------------------------------
def test_the_tree_is_the_documented_folder_layout(project, tmp_path):
    root = project.write(tmp_path)
    produced = sorted(
        str(path.relative_to(root)) for path in root.rglob("*")
        if path.is_file())
    assert produced == [
        "esp32-body-module.eprj3",
        "pcb/LOGIC.epcb2",
        "pcb/POWER.epcb2",
        "sch/LOGIC/LOGIC.ecfg",
        "sch/LOGIC/P1.esch2",
        "sch/LOGIC/P2.esch2",
        "sch/POWER/P1.esch2",
        "sch/POWER/POWER.ecfg",
    ]


def test_unused_folders_are_absent_not_empty(project, tmp_path):
    # An absent folder is legal; the editor creates them lazily. There are no
    # panels and no assembly variants, so neither may appear.
    root = project.write(tmp_path)
    assert not (root / "panel").exists()
    assert not list(root.rglob("*.evar"))


def test_folder_basename_and_index_name_are_one_string(project, tmp_path):
    root = project.write(tmp_path)
    index = json.loads((root / f"{project.name}.eprj3").read_text("utf-8"))
    assert root.name == project.name == index["name"]


def test_index_is_pretty_printed_json_with_one_trailing_newline(project):
    text = project.index_text()
    assert text.endswith("}\n")
    assert not text.endswith("}\n\n")
    assert '\n  "name": "esp32-body-module",\n' in text   # 2-space indent


# --- uuids ------------------------------------------------------------------
def test_document_uuids_are_sixteen_lowercase_hex(project):
    profile = project.index()["profile"]
    for map_name in ("boards", "schematics", "sheets", "pcbs"):
        for key, entry in profile[map_name].items():
            assert HEX16.match(key), f"{map_name} key {key!r}"
            assert entry["uuid"] == key


def test_account_uuids_are_thirty_two_lowercase_hex(project):
    index = project.index()
    for field in ("owner_uuid", "creator_uuid", "modifier_uuid"):
        assert HEX32.match(index[field]), field
    assert index["profile"]["owner"]["uuid"] == index["owner_uuid"]


def test_every_uuid_in_the_project_is_distinct(project):
    profile = project.index()["profile"]
    seen = [key for name in ("boards", "schematics", "sheets", "pcbs")
            for key in profile[name]]
    assert len(seen) == len(set(seen))


def test_a_board_schematic_and_pcb_of_the_same_name_do_not_collide():
    # add_board() defaults all three names to the board title, so the uuid
    # derivation has to be namespaced or the index collapses to one entry.
    project = Project("collide")
    project.add_board("OUTPUTS")
    profile = project.index()["profile"]
    board = next(iter(profile["boards"]))
    schematic = next(iter(profile["schematics"]))
    pcb = next(iter(profile["pcbs"]))
    assert len({board, schematic, pcb}) == 3


# --- referential integrity --------------------------------------------------
def test_every_cross_reference_in_the_index_resolves(project):
    profile = project.index()["profile"]
    boards = set(profile["boards"])
    schematics = set(profile["schematics"])

    assert boards and schematics and profile["pcbs"] and profile["sheets"]
    for entry in profile["schematics"].values():
        assert entry["board"] in boards
    for entry in profile["pcbs"].values():
        assert entry["board"] in boards
    for entry in profile["sheets"].values():
        assert entry["schematic_uuid"] in schematics


def test_each_board_is_named_by_exactly_one_schematic_and_one_pcb(project):
    profile = project.index()["profile"]
    for board in profile["boards"]:
        schematics = [e for e in profile["schematics"].values()
                      if e["board"] == board]
        pcbs = [e for e in profile["pcbs"].values() if e["board"] == board]
        assert len(schematics) == 1
        assert len(pcbs) == 1


def test_both_documents_restate_the_board_uuid_the_index_gives(project):
    # The board is the join table: index, .ecfg META and .epcb2 META must all
    # carry the same uuid or the PCB is orphaned from its schematic.
    profile = project.index()["profile"]
    documents = project.documents()
    for board_uuid, board in profile["boards"].items():
        schematic = next(e for e in profile["schematics"].values()
                         if e["board"] == board_uuid)
        pcb = next(e for e in profile["pcbs"].values()
                   if e["board"] == board_uuid)

        ecfg = parse_document(
            documents[f"sch/{schematic['name']}/{schematic['name']}.ecfg"])
        meta = next(body for head, body in ecfg if head["type"] == "META")
        assert meta["board"] == board_uuid
        assert meta["title"] == schematic["name"]

        epcb = parse_document(documents[f"pcb/{pcb['title']}.epcb2"])
        meta = next(body for head, body in epcb if head["type"] == "META")
        assert meta["board"] == board_uuid
        assert meta["title"] == pcb["title"]
        assert board["title"]        # a board is index-only, it has no file


def test_a_sheet_names_its_schematic_in_both_spellings(project):
    # The index says "schematic_uuid"; the sheet's own META says "schematic".
    profile = project.index()["profile"]
    documents = project.documents()
    for sheet in profile["sheets"].values():
        schematic = profile["schematics"][sheet["schematic_uuid"]]
        path = f"sch/{schematic['name']}/{sheet['title']}.esch2"
        meta = next(body for head, body in parse_document(documents[path])
                    if head["type"] == "META")
        assert meta["schematic"] == sheet["schematic_uuid"]
        assert meta["zIndex"] == sheet["zIndex"]


def test_sheet_z_index_is_one_based_within_its_schematic(project):
    profile = project.index()["profile"]
    brain = next(k for k, v in profile["schematics"].items()
                 if v["name"] == "LOGIC")
    order = sorted(e["zIndex"] for e in profile["sheets"].values()
                   if e["schematic_uuid"] == brain)
    assert order == [1, 2]


def test_the_generators_own_integrity_check_agrees(project):
    assert project.referential_errors() == []


def test_a_broken_link_is_reported_rather_than_written(project, tmp_path):
    project.boards[0].pcb.board_uuid = "0" * 16
    assert project.referential_errors()
    with pytest.raises(ValueError, match="inconsistent"):
        project.write(tmp_path)


# --- determinism ------------------------------------------------------------
def test_two_runs_produce_byte_identical_trees(tmp_path):
    def build(where):
        project = Project("esp32-body-module")
        project.add_board("POWER")
        project.add_board("LOGIC", sheets=("P1", "P2"))
        return project.write(where)

    first = build(tmp_path / "a")
    second = build(tmp_path / "b")
    names = sorted(str(p.relative_to(first)) for p in first.rglob("*")
                   if p.is_file())
    assert names == sorted(str(p.relative_to(second))
                           for p in second.rglob("*") if p.is_file())
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_the_timestamp_is_a_stated_constant_not_the_clock(project):
    index = project.index()
    assert index["created_at"] == index["updated_at"]
    assert index["profile"]["pcbs"][
        next(iter(index["profile"]["pcbs"]))]["updateTime"] == DEFAULT_EPOCH_MS
    # "%Y-%m-%d %H:%M:%S" -- not ISO-8601, no timezone marker.
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$",
                    index["created_at"])


def test_a_different_project_name_gives_different_uuids():
    a = Project("one")
    a.add_board("POWER")
    b = Project("two")
    b.add_board("POWER")
    assert set(a.index()["profile"]["boards"]) != \
        set(b.index()["profile"]["boards"])


# --- the record grammar -----------------------------------------------------
def test_every_document_round_trips_byte_for_byte(project):
    for name, text in project.documents().items():
        if name.endswith(".eprj3"):
            continue                      # the index is plain JSON, not records
        assert rejoin(parse_document(text)) == text, name


def test_no_document_has_a_trailing_separator_or_newline(project):
    for name, text in project.documents().items():
        if name.endswith(".eprj3"):
            continue
        assert not text.endswith("|"), name
        assert not text.endswith("\n"), name


def test_the_project_emitter_uses_the_one_joiner():
    import inspect
    from tools.eprj3 import project as project_module, records
    assert project_module.join_records is records.join_records
    source = inspect.getsource(project_module)
    assert '"|\\n"' not in source and "'|\\n'" not in source


def test_a_schematic_document_is_dochead_then_meta(project):
    text = project.documents()["sch/POWER/POWER.ecfg"]
    records = parse_document(text)
    assert [head["type"] for head, _ in records] == ["DOCHEAD", "META"]
    assert records[0][1]["docType"] == "SCH"
    assert "ticket" not in records[0][0] and "id" not in records[0][0]


def test_a_sheet_document_is_dochead_then_meta(project):
    records = parse_document(project.documents()["sch/POWER/P1.esch2"])
    assert [head["type"] for head, _ in records] == ["DOCHEAD", "META"]
    assert records[0][1]["docType"] == "SCH_PAGE"


def test_a_dochead_uuid_matches_its_index_key(project):
    profile = project.index()["profile"]
    documents = project.documents()
    for pcb in profile["pcbs"].values():
        head, body = parse_document(documents[f"pcb/{pcb['title']}.epcb2"])[0]
        assert body["uuid"] == pcb["uuid"]
    for schematic in profile["schematics"].values():
        path = f"sch/{schematic['name']}/{schematic['name']}.ecfg"
        head, body = parse_document(documents[path])[0]
        assert body["uuid"] == schematic["uuid"]


# --- the stack ---------------------------------------------------------------
def test_for_stack_makes_one_board_per_layer_of_the_physical_stack():
    project = Project.for_stack("esp32-body-module")
    profile = project.index()["profile"]
    titles = [e["title"] for e in profile["boards"].values()]
    assert titles == list(STACK_ORDER)
    assert len(profile["pcbs"]) == len(STACK_ORDER)
    assert project.index()["pcb_count"] == len(STACK_ORDER)



def test_power_is_deeper_with_its_holes_on_the_common_pattern():
    """POWER alone is POWER_W deep (owner, 2026-09-24); every board's four M3
    holes sit where OUTPUTS' do, because the standoffs join them. A POWER
    whose holes followed its own width would miss the posts by 0.46 mm."""
    from tools import board_params as bp
    project = Project.for_stack("esp32-body-module")
    pcbs = {b.title: b.pcb for b in project.boards}
    assert pcbs["POWER"].width_mm == bp.POWER_W > bp.BOARD_W
    assert {pcbs[b].width_mm for b in STACK_ORDER if b != "POWER"} == {bp.BOARD_W}
    holes = {b: pcbs[b].hole_centres() for b in STACK_ORDER}
    assert all(h == holes["OUTPUTS"] for h in holes.values())


def test_holes_laid_out_wider_than_the_board_are_refused():
    project = Project("guard")
    with pytest.raises(ValueError, match="do not fit"):
        project.add_board("POWER", width_mm=40.0, hole_span_mm=41.84)

def test_board_z_index_follows_the_stack_order():
    project = Project.for_stack("esp32-body-module")
    boards = project.index()["profile"]["boards"].values()
    by_z = sorted(boards, key=lambda e: e["zIndex"])
    assert [e["title"] for e in by_z] == list(STACK_ORDER)
    assert [e["zIndex"] for e in by_z] == list(range(1, len(STACK_ORDER) + 1))


# --- guards -----------------------------------------------------------------
@pytest.mark.parametrize("title", ["a/b", "a:b", "", "a*b", 'a"b'])
def test_a_title_that_would_break_a_path_is_refused(title):
    project = Project("guard")
    with pytest.raises(ValueError, match="A-Za-z0-9"):
        project.add_board(title)


def test_a_duplicate_board_title_is_refused():
    project = Project("guard")
    project.add_board("OUTPUTS")
    with pytest.raises(ValueError, match="already exists"):
        project.add_board("OUTPUTS")


def test_a_schematic_with_no_sheets_is_refused():
    project = Project("guard")
    with pytest.raises(ValueError, match="no sheets"):
        project.add_board("OUTPUTS", sheets=())


# --- fields that a real saved project gets specifically right ---------------
def test_the_index_declares_the_folder_format(project):
    index = project.index()
    assert index["format"] == "folder"


def test_the_vestigial_top_level_board_list_stays_empty(project):
    # The real board list is profile.boards; the top-level one is a leftover
    # and a real saved project leaves it empty even with a board present.
    assert project.index()["boards"] == []
    assert project.index()["profile"]["boards"]


def test_the_two_spellings_of_default_sheet_agree(project):
    index = project.index()
    assert index["default_sheet"] == index["config"]["defaultSheet"] == ""


def test_cbb_project_is_an_integer_and_archive_is_a_boolean(project):
    index = project.index()
    assert index["cbb_project"] == 0
    assert not isinstance(index["cbb_project"], bool)   # an int, unlike archive
    assert index["archive"] is False
