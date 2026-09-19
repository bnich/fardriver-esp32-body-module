"""The `.eprj2` container: what EasyEDA Pro 3.2.149 actually opens.

The writer is checked three ways: its output decodes to exactly what went in;
the snapshot decrypts by the documented recipe with nothing but sqlite3 and the
cipher (so the file does not merely agree with its own reader); and an `.eprj3`
folder is wrapped with every structure entry backed by a document.  The
template here is synthetic, built from a minimal schema, so no file of the
editor's is committed.  One test also runs against an editor-saved template
when this machine has one.
"""
import base64
import gzip
import json
import shutil
import sqlite3

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402

from tools import eprj2, gauge  # noqa: E402
from tools.build_project import write as write_project  # noqa: E402

OWNER = "0123456789abcdef0123456789abcdef"
TEMPLATE_DDL = [
    'CREATE TABLE "projects" ("uuid" varchar PRIMARY KEY NOT NULL, "archive" boolean NOT NULL, '
    '"name" varchar NOT NULL, "content" varchar NOT NULL, "cbb_project" boolean NOT NULL DEFAULT (0), '
    '"thumb" varchar NOT NULL, "ticket" integer NOT NULL, "g_ticket" integer NOT NULL DEFAULT (1), '
    '"owner_uuid" varchar, "creator_uuid" varchar, "created_at" datetime, "updated_at" datetime, '
    '"modifier_uuid" varchar, "boards" varchar NOT NULL DEFAULT (\'{}\'), '
    '"block_symbol_attrs_groups" varchar NOT NULL DEFAULT (\'{}\'), "pcb_count" integer NOT NULL DEFAULT (0), '
    '"branch_uuid" varchar NULL, "default_sheet" text DEFAULT \'\')',
    'CREATE TABLE "branches" ("id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, "uuid" varchar NOT NULL, '
    '"project_uuid" varchar NOT NULL, "name" varchar NOT NULL, "history_uuid" varchar NULL, '
    '"creator_uuid" varchar NOT NULL, "description" varchar NOT NULL, "parent_uuid" varchar NULL, '
    '"modifier_uuid" varchar NOT NULL, "node" integer NOT NULL DEFAULT (0), '
    '"delete_status" integer NOT NULL DEFAULT (0), "created_at" datetime, "updated_at" datetime)',
    'CREATE TABLE project_history_aaaa0000aaaa0000aaaa0000aaaa0000 (id integer NOT NULL PRIMARY KEY, '
    'uuid varchar NOT NULL UNIQUE, parent varchar NULL, snapshot varchar NULL, key varchar NOT NULL, '
    'is_lock integer NOT NULL DEFAULT 0, num integer NOT NULL DEFAULT 0, created_at datetime, '
    'updated_at datetime, lock_time datetime, snapshot_num integer NOT NULL DEFAULT 0)',
    'CREATE TABLE "history_data" ("id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
    '"uuid" varchar UNIQUE NOT NULL, "history_uuid" varchar NOT NULL, "dataStr" TEXT NOT NULL, '
    '"created_at" datetime, "updated_at" datetime)',
    'CREATE TABLE "project_structures" ("id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
    '"ticket" integer NOT NULL DEFAULT (0), "project_uuid" varchar NOT NULL, '
    '"branch_uuid" varchar NOT NULL, "structure" TEXT NOT NULL)',
    'CREATE TABLE "project_members" ("role" integer NOT NULL, "project_uuid" varchar NOT NULL, '
    '"user_uuid" varchar NOT NULL, "created_at" datetime, "updated_at" datetime, '
    'PRIMARY KEY ("project_uuid", "user_uuid"))',
    'CREATE TABLE "db_versions" ("key" varchar PRIMARY KEY NOT NULL, "value" varchar NOT NULL)',
    'CREATE TABLE "users" ("uuid" varchar PRIMARY KEY NOT NULL, "username" varchar NOT NULL, '
    '"nickname" varchar NOT NULL)',
]


@pytest.fixture
def template(tmp_path):
    path = tmp_path / "template.eprj2"
    db = sqlite3.connect(path)
    for sql in TEMPLATE_DDL:
        db.execute(sql)
    db.execute("insert into projects (uuid, archive, name, content, thumb, ticket, owner_uuid) "
               "values ('p', 0, 'T', '', '', 1, ?)", (OWNER,))
    db.execute("insert into db_versions values ('sqlite', 'test')")
    db.execute("insert into users values ('u', 'LCSC', 'LCSC')")
    db.commit()
    db.close()
    return path


@pytest.fixture
def gauge_folder(tmp_path):
    project, _ = gauge.build()
    root, _ = write_project(project, tmp_path / "gen")
    return root


STREAM = ('{"type":"EDIT_HEAD"}||{"uuid":"x"}|\n'
          '{"type":"DOCHEAD"}||{"docType":"CONFIG","uuid":"CONFIG"}|\n'
          '{"type":"META","ticket":1,"id":"META"}||{"defaultSheet":""}')


# --- the container ---------------------------------------------------------------
def test_written_file_decodes_to_the_stream_and_structure(template, tmp_path):
    out = tmp_path / "a.eprj2"
    eprj2.write(template, out, STREAM, {"boards": {}}, "A")
    snap = eprj2.read(out)
    assert snap["text"] == STREAM
    assert snap["structure"] == {"boards": {}}
    assert snap["name"] == "A" and snap["owner"] == OWNER


def test_snapshot_decrypts_by_the_documented_recipe(template, tmp_path):
    """Independent of `read`: key from the history row, IV = the snapshot
    uuid's bytes, AES-128-GCM with the tag appended, then gzip."""
    out = tmp_path / "a.eprj2"
    ids = eprj2.write(template, out, STREAM, {}, "A")
    db = sqlite3.connect(out)
    (table,) = db.execute("select name from sqlite_master "
                          "where name like 'project_history_%'").fetchone()
    assert table == "project_history_" + ids["main"]
    hid, key = db.execute(f"select uuid, key from {table}").fetchone()
    data = db.execute("select dataStr from history_data where uuid=?", (hid,)).fetchone()[0]
    plain = AESGCM(bytes.fromhex(key)).decrypt(bytes.fromhex(hid), base64.b64decode(data), None)
    assert gzip.decompress(plain).decode() == STREAM
    # the branch the project points at is the one that owns the snapshot
    branch = db.execute("select branch_uuid from projects").fetchone()[0]
    assert db.execute("select history_uuid from branches where uuid=?",
                      (branch,)).fetchone()[0] == hid


def test_design_tables_stay_empty_and_editor_rows_are_copied(template, tmp_path):
    out = tmp_path / "a.eprj2"
    eprj2.write(template, out, STREAM, {}, "A")
    db = sqlite3.connect(out)
    assert db.execute("select value from db_versions").fetchone()[0] == "test"
    assert db.execute("select count(*) from project_structures").fetchone()[0] == 1
    assert db.execute("select count(*) from branches").fetchone()[0] == 2
    assert db.execute("select count(*) from history_data").fetchone()[0] == 1


@pytest.mark.parametrize("bad", ['["DOCHEAD"]||{}', '{"id":"x"}||{}', 'no separator'])
def test_a_record_the_editor_would_drop_is_refused(template, tmp_path, bad):
    with pytest.raises(ValueError):
        eprj2.write(template, tmp_path / "a.eprj2", bad, {}, "A")
    assert not (tmp_path / "a.eprj2").exists()


def test_existing_output_and_bad_template_are_refused(template, tmp_path):
    out = tmp_path / "a.eprj2"
    out.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        eprj2.write(template, out, STREAM, {}, "A")
    assert out.read_bytes() == b"keep"
    empty = tmp_path / "empty.eprj2"
    sqlite3.connect(empty).close()
    with pytest.raises(ValueError, match="not a usable template"):
        eprj2.write(empty, tmp_path / "b.eprj2", STREAM, {}, "A")


# --- wrapping an .eprj3 folder -----------------------------------------------------
def test_gauge_folder_wraps_with_every_entry_backed(gauge_folder, template):
    stream, structure, name = eprj2.from_eprj3(gauge_folder, OWNER, 1)
    lead, docs = eprj2.documents(eprj2.split_records(stream))
    assert [h["type"] for h, _ in lead] == ["EDIT_HEAD"]
    types = [d[0] for d in docs]
    assert types == sorted(types, key=eprj2.DOC_ORDER.index)
    for kind, doc_type in (("boards", "BOARD"), ("schematics", "SCH"),
                           ("sheets", "SCH_PAGE"), ("pcbs", "PCB")):
        assert set(structure[kind]) == {u for t, u, _ in docs if t == doc_type}
        assert structure[kind]
    assert "FOOTPRINT" in types and types.count("CONFIG") == 1
    index = json.loads(next(gauge_folder.glob("*.eprj3")).read_text())
    assert structure["sheets"].keys() == index["profile"]["sheets"].keys()
    assert name == "gauge-revv1"


def test_a_document_missing_from_the_folder_is_refused(gauge_folder):
    shutil.rmtree(gauge_folder / "pcb")
    with pytest.raises(ValueError, match="no document for"):
        eprj2.from_eprj3(gauge_folder, OWNER, 1)


def test_one_library_document_that_differs_between_files_is_refused(gauge_folder):
    sheet = next(gauge_folder.rglob("*.esch2"))
    text = sheet.read_text()
    first_symbol = text.split("|\n")
    head = next(i for i, r in enumerate(first_symbol) if '"docType":"SYMBOL"' in r)
    end = next(i for i in range(head + 1, len(first_symbol))
               if first_symbol[i].startswith('{"type":"DOCHEAD"'))
    copy = "|\n".join(first_symbol[head:end]).replace('"ticket":1,', '"ticket":99,', 1)
    (sheet.parent / "EXTRA.esch2").write_text(copy)
    with pytest.raises(ValueError, match="differs between files"):
        eprj2.from_eprj3(gauge_folder, OWNER, 1)


def test_convert_is_deterministic_and_content_addressed(gauge_folder, template, tmp_path):
    a = eprj2.convert(gauge_folder, tmp_path / "a.eprj2", template)
    b = eprj2.convert(gauge_folder, tmp_path / "b.eprj2", template)
    assert a.read_bytes() == b.read_bytes()
    uuid = lambda p: sqlite3.connect(p).execute("select uuid from projects").fetchone()[0]
    sheet = next(gauge_folder.rglob("*.esch2"))
    sheet.write_text(sheet.read_text().replace('"10k"', '"12k"', 1))
    c = eprj2.convert(gauge_folder, tmp_path / "c.eprj2", template)
    assert uuid(c) != uuid(a), "a changed design must not reuse the old project's id"


def test_find_template_prefers_env_then_examples(template, tmp_path, monkeypatch):
    monkeypatch.delenv("EASYEDA_EPRJ2_TEMPLATE", raising=False)
    home = tmp_path / "home"
    assert eprj2.find_template(home) is None
    projects = home / "Documents/EasyEDA-Pro/projects"
    examples = home / "Documents/EasyEDA-Pro/example-projects"
    projects.mkdir(parents=True)
    examples.mkdir(parents=True)
    shutil.copy(template, projects / "mine.eprj2")
    assert eprj2.find_template(home) == projects / "mine.eprj2"
    (examples / "broken.eprj2").write_bytes(b"not sqlite")
    shutil.copy(template, examples / "ex.eprj2")
    assert eprj2.find_template(home) == examples / "ex.eprj2"
    monkeypatch.setenv("EASYEDA_EPRJ2_TEMPLATE", str(template))
    assert eprj2.find_template(home) == template


def test_with_this_machines_editor_template_when_there_is_one(gauge_folder, tmp_path):
    real = eprj2.find_template()
    if real is None:
        pytest.skip("no editor-saved .eprj2 on this machine")
    out = eprj2.convert(gauge_folder, tmp_path / "g.eprj2", real)
    owner = eprj2.find_account() or eprj2.read(real)["owner"]
    stream, _, _ = eprj2.from_eprj3(gauge_folder, owner, 1788000000000)
    snap = eprj2.read(out)
    assert snap["text"] == stream and snap["owner"] == owner


# --- the build writes it ------------------------------------------------------------
def test_the_build_writes_an_openable_eprj2_for_every_board(template, tmp_path, capsys):
    from tools import build_project
    from tools.board_params import STACK_ORDER
    assert build_project.main(["--out", str(tmp_path), "--template", str(template)]) == 0
    out = tmp_path / f"{build_project.PROJECT_NAME}.eprj2"
    snap = eprj2.read(out)
    assert sorted(b["title"] for b in snap["structure"]["boards"].values()) == sorted(STACK_ORDER)
    assert f"open in EasyEDA Pro: {out}" in capsys.readouterr().out


def test_no_template_is_said_loudly_not_silently(tmp_path, monkeypatch):
    from tools import build_project
    monkeypatch.setattr(eprj2, "find_template", lambda home=None: None)
    path, why = build_project.write_eprj2(tmp_path / "revv1-module", None)
    assert path is None and "no template" in why
    assert "NO .eprj2 WRITTEN" in build_project.eprj2_line(path, why)


# --- whose project it is --------------------------------------------------------------
def _web_db(home, users):
    d = home / "Documents/EasyEDA-Pro/database"
    d.mkdir(parents=True)
    db = sqlite3.connect(d / "web.db")
    db.execute('CREATE TABLE "users" ("uuid" varchar PRIMARY KEY NOT NULL, '
               '"username" varchar NOT NULL, "nickname" varchar NOT NULL)')
    db.executemany("insert into users values (?,?,?)", users)
    db.commit()
    db.close()


def test_the_owner_is_the_editors_signed_in_account_not_the_templates(template, tmp_path):
    """An example project the editor converted keeps its original author as
    owner.  A project written from it must belong to whoever uses this editor."""
    home = tmp_path / "home"
    me = "f4c6f02f03e4435fb20223c287a18db1"
    _web_db(home, [("0819f05c4eef4c71ace90d822a990e87", "LCSC", "LCSC"), (me, "me", "me")])
    assert eprj2.find_account(home) == me
    out = tmp_path / "a.eprj2"
    eprj2.write(template, out, STREAM, {}, "A", owner=me)
    db = sqlite3.connect(out)
    assert db.execute("select owner_uuid, creator_uuid, modifier_uuid from projects").fetchone() == (me, me, me)
    assert db.execute("select user_uuid from project_members").fetchone()[0] == me


def test_no_account_or_an_ambiguous_one_falls_back_to_the_template(template, tmp_path):
    assert eprj2.find_account(tmp_path / "nobody") is None
    home = tmp_path / "two"
    _web_db(home, [("a" * 32, "one", "one"), ("b" * 32, "two", "two")])
    assert eprj2.find_account(home) is None
    out = tmp_path / "a.eprj2"
    eprj2.write(template, out, STREAM, {}, "A")
    assert eprj2.read(out)["owner"] == OWNER


# --- a project the editor has saved into: a chain of deltas ---------------------------
def _append_delta(path, delta_text, parent_hid, hid, key="11" * 16):
    """Append a history entry the way the editor does on save: a child row
    whose snapshot holds only what changed."""
    import base64, gzip
    db = sqlite3.connect(path)
    (table,) = db.execute("select name from sqlite_master where name like 'project_history_%'").fetchone()
    blob = AESGCM(bytes.fromhex(key)).encrypt(bytes.fromhex(hid), gzip.compress(delta_text.encode()), None)
    db.execute(f"insert into {table} (uuid, parent, snapshot, key) values (?,?,NULL,?)", (hid, parent_hid, key))
    db.execute("insert into history_data (uuid, history_uuid, dataStr) values (?,?,?)",
               (hid, hid, base64.b64encode(blob).decode()))
    db.commit()
    db.close()


BASE = ('{"type":"EDIT_HEAD"}||{"uuid":"x","updateTime":1}|\n'
        '{"type":"DOCHEAD"}||{"docType":"PCB","uuid":"P1","updateTime":1}|\n'
        '{"type":"META","ticket":1,"id":"META"}||{"title":"A"}|\n'
        '{"type":"LINE","ticket":2,"id":"e1"}||{"w":1}|\n'
        '{"type":"LINE","ticket":3,"id":"e2"}||{"w":2}')


def test_an_editor_saved_project_reads_as_the_chain_replayed(template, tmp_path):
    """Editor saves append a delta: the same (document, record) replaces the
    base's, a new record is added.  read() must give the design, not the last
    fragment."""
    out = tmp_path / "a.eprj2"
    ids = eprj2.write(template, out, BASE, {}, "A")
    delta = ('{"type":"EDIT_HEAD"}||{"uuid":"x","updateTime":2}|\n'
             '{"type":"DOCHEAD","ticket":9}||{"docType":"PCB","uuid":"P1","updateTime":2}|\n'
             '{"type":"LINE","ticket":10,"id":"e2"}||{"w":5}|\n'
             '{"type":"NET","ticket":11,"id":"[\\"NET\\",\\"\\"]"}||{"n":0}')
    _append_delta(out, delta, ids["history"], "22" * 16)
    snap = eprj2.read(out)
    recs = {(h["type"], h.get("id")): p for h, p in eprj2.split_records(snap["text"])}
    assert recs[("LINE", "e1")] == '{"w":1}'          # untouched
    assert recs[("LINE", "e2")] == '{"w":5}'          # replaced by the delta
    assert ("NET", '["NET",""]') in recs                # added by the delta
    assert snap["deltas"] == 1


def test_a_record_with_an_empty_payload_in_a_delta_is_a_deletion(template, tmp_path):
    out = tmp_path / "a.eprj2"
    ids = eprj2.write(template, out, BASE, {}, "A")
    _append_delta(out, '{"type":"EDIT_HEAD"}||{"uuid":"x"}|\n'
                       '{"type":"DOCHEAD","ticket":9}||{"docType":"PCB","uuid":"P1"}|\n'
                       '{"type":"LINE","ticket":10,"id":"e1"}||', ids["history"], "33" * 16)
    types = [(h["type"], h.get("id")) for h, p in eprj2.split_records(eprj2.read(out)["text"])]
    assert ("LINE", "e1") not in types and ("LINE", "e2") in types


def _append_chunk(path, delta_text, hid):
    """Append to an existing history entry the way the editor's save does when
    it does not open a new one: history_data row `<hid>-<n>`, encrypted under
    that entry's key with IV = the entry's uuid, and the entry's `num` = n."""
    import base64, gzip
    db = sqlite3.connect(path)
    (table,) = db.execute("select name from sqlite_master where name like 'project_history_%'").fetchone()
    key, num = db.execute(f"select key, num from {table} where uuid=?", (hid,)).fetchone()
    blob = AESGCM(bytes.fromhex(key)).encrypt(bytes.fromhex(hid), gzip.compress(delta_text.encode()), None)
    db.execute("insert into history_data (uuid, history_uuid, dataStr) values (?,?,?)",
               (f"{hid}-{num + 1}", hid, base64.b64encode(blob).decode()))
    db.execute(f"update {table} set num=? where uuid=?", (num + 1, hid))
    db.commit()
    db.close()


def test_chunks_appended_to_a_history_entry_are_replayed_in_order(template, tmp_path):
    """A save can append to the newest entry instead of opening a new one
    (3.2.149 did this for a PCB import).  The chunks are that entry's later
    saves: all of them count, in order."""
    out = tmp_path / "a.eprj2"
    ids = eprj2.write(template, out, BASE, {}, "A")
    head = '{"type":"EDIT_HEAD"}||{"uuid":"x"}|\n{"type":"DOCHEAD"}||{"docType":"PCB","uuid":"P1"}|\n'
    _append_chunk(out, head + '{"type":"LINE","ticket":10,"id":"e2"}||{"w":7}|\n'
                              '{"type":"LINE","ticket":11,"id":"e3"}||{"w":3}', ids["history"])
    _append_chunk(out, head + '{"type":"LINE","ticket":12,"id":"e3"}||{"w":9}', ids["history"])
    snap = eprj2.read(out)
    recs = {(h["type"], h.get("id")): p for h, p in eprj2.split_records(snap["text"])}
    assert recs[("LINE", "e1")] == '{"w":1}'
    assert recs[("LINE", "e2")] == '{"w":7}'          # the first chunk
    assert recs[("LINE", "e3")] == '{"w":9}'          # the second overrides the first
    assert snap["deltas"] == 2


def test_a_missing_chunk_is_refused(template, tmp_path):
    out = tmp_path / "a.eprj2"
    ids = eprj2.write(template, out, BASE, {}, "A")
    _append_chunk(out, '{"type":"EDIT_HEAD"}||{"uuid":"x"}', ids["history"])
    db = sqlite3.connect(out)
    db.execute("delete from history_data where uuid=?", (ids["history"] + "-1",))
    db.commit()
    db.close()
    with pytest.raises(ValueError, match="missing"):
        eprj2.read(out)


def test_a_branching_history_is_refused(template, tmp_path):
    out = tmp_path / "a.eprj2"
    eprj2.write(template, out, BASE, {}, "A")
    _append_delta(out, '{"type":"EDIT_HEAD"}||{"uuid":"x"}', "ab" * 16, "44" * 16)
    with pytest.raises(ValueError, match="not a single chain"):
        eprj2.read(out)
