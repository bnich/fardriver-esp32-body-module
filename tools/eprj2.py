#!/usr/bin/env python3
"""EasyEDA Pro `.eprj2` projects: read them, write them, and wrap a generated
`.eprj3` folder as one.  EasyEDA Pro 3.2.149 opens `.eprj2` and not `.eprj3`.

An `.eprj2` is SQLite.  The whole design is ONE snapshot: the V3 record
stream (`{"type":...}||{...}` records joined by "|\\n", the same records the
`.eprj3` files hold), gzip'd, AES-128-GCM encrypted under a random key that is
stored in the same file, base64'd.  The `schematics`, `documents` and
`components` tables stay EMPTY -- a writer that fills them makes a project that
opens empty.

    python3 tools/eprj2.py info       FILE.eprj2
    python3 tools/eprj2.py decode     FILE.eprj2 OUTDIR
    python3 tools/eprj2.py from-eprj3 [--template T.eprj2] FOLDER OUT.eprj2
    python3 tools/eprj2.py encode     --template T --stream S --structure J --name N OUT.eprj2
    python3 tools/eprj2.py roundtrip  FILE.eprj2

The TEMPLATE is any `.eprj2` the installed editor saved.  The new file copies
its schema, its db version and the account uuid, so the output always has the
installed editor's schema; nothing of the editor's is stored here.  With no
--template, `find_template()` looks in the editor's own folders.

Self-contained on purpose (stdlib + `cryptography`), so it also runs as a
script outside the repo.  Needs the `cryptography` package.
"""
import argparse
import base64
import datetime
import gzip
import hashlib
import json
import os
import secrets
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

SEP = "|\n"
#: Document order inside a snapshot, as the editor writes it (read from
#: projects it saved).  A document type with no place here is refused.
DOC_ORDER = ("FOOTPRINT", "SYMBOL", "DEVICE", "BOARD", "SCH", "SCH_PAGE", "PCB",
             "PANEL", "PANEL_LIB", "SIMULATION_SCH", "SIMULATION", "CONFIG",
             "BLOB", "FONT")
#: Editor-global rows, copied from the template rather than generated.
COPY_ROWS = ("db_versions", "users", "system_config", "system_attributes")
#: Tables a template must have for `write` to fill.  The history table is
#: named per branch and checked separately.
NEEDED_TABLES = ("projects", "branches", "history_data", "project_structures",
                 "project_members", "db_versions", "users")
#: The .eprj3 files that hold documents.
DOC_SUFFIXES = (".esch2", ".ecfg", ".epcb2", ".epan2", ".esym2", ".efoo2",
                ".edev2")
#: Where the editor keeps projects it saved.  Examples first: the editor
#: converted them itself, so they are never this tool's own output.
EDITOR_DIRS = ("Documents/EasyEDA-Pro/example-projects",
               "Documents/EasyEDA-Pro/projects")


def _aesgcm(key_hex):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise RuntimeError("writing or reading .eprj2 needs the `cryptography` "
                           "package (python3 -m pip install cryptography)") from exc
    return AESGCM(bytes.fromhex(key_hex))


def _compact(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


# --- records ------------------------------------------------------------------
def split_records(text):
    """Stream -> [(header dict, payload text)].  Refuses what the editor would
    drop without a word: no `||`, or a header that is not an object with a
    string `type`."""
    out = []
    for i, rec in enumerate(text.split(SEP)):
        head, sep, payload = rec.partition("||")
        if not sep:
            raise ValueError(f"record {i}: no '||'")
        h = json.loads(head)
        if not isinstance(h, dict) or not isinstance(h.get("type"), str):
            raise ValueError(f"record {i}: the header is not an object with a "
                             f"string 'type'; the editor would drop it")
        out.append((h, payload))
    return out


def documents(records):
    """(records before the first DOCHEAD, [(docType, uuid, records)])."""
    docs, lead = [], []
    for h, p in records:
        if h["type"] == "DOCHEAD":
            body = json.loads(p)
            docs.append((body["docType"], body.get("uuid", ""), [(h, p)]))
        elif docs:
            docs[-1][2].append((h, p))
        else:
            lead.append((h, p))
    return lead, docs


def join(records):
    return SEP.join(_compact(h) + "||" + p for h, p in records)


# --- reading --------------------------------------------------------------------
def _open_ro(path):
    return sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)


def _history_table(db):
    names = [r[0] for r in db.execute(
        "select name from sqlite_master where type='table' "
        "and name like 'project_history_%'")]
    if len(names) != 1:
        raise ValueError(f"expected one project_history_<branch> table, "
                         f"found {names}")
    return names[0]


def read(path):
    """The newest snapshot: {text, structure, name, owner, branch, history}."""
    db = _open_ro(path)
    try:
        table = _history_table(db)
        hid, key = db.execute(f'select uuid, key from "{table}" '
                              f'order by id desc limit 1').fetchone()
        data = db.execute("select dataStr from history_data where uuid=?",
                          (hid,)).fetchone()[0]
        plain = _aesgcm(key).decrypt(bytes.fromhex(hid),
                                     base64.b64decode(data), None)
        structure = json.loads(db.execute(
            "select structure from project_structures order by id desc "
            "limit 1").fetchone()[0])
        name, owner, branch = db.execute(
            "select name, owner_uuid, branch_uuid from projects").fetchone()
    finally:
        db.close()
    return {"text": gzip.decompress(plain).decode("utf-8"),
            "structure": structure, "name": name, "owner": owner,
            "branch": branch, "history": hid}


# --- writing --------------------------------------------------------------------
def _ids(seed):
    """Every id a new project needs: from `seed` if given, else random."""
    def make(label, nbytes):
        if seed is None:
            return secrets.token_hex(nbytes)
        return hashlib.sha256(f"{seed}/{label}".encode()).hexdigest()[:2 * nbytes]
    return {"project": make("project", 32), "start": make("start", 16),
            "main": make("main", 16), "history": make("history", 16),
            "key": make("key", 16)}


def check_template(template):
    """Problems that stop `template` serving as one, as text; [] if none."""
    try:
        db = _open_ro(template)
        have = {r[0] for r in db.execute(
            "select name from sqlite_master where type='table'")}
        problems = [f"no `{t}` table" for t in NEEDED_TABLES if t not in have]
        if not problems:
            _history_table(db)
            if db.execute("select count(*) from projects").fetchone()[0] != 1:
                problems.append("not exactly one project")
        db.close()
        return problems
    except (sqlite3.DatabaseError, ValueError) as exc:
        return [str(exc)]


def write(template, out, stream, structure, name, *, seed=None, now=None):
    """Write a new `.eprj2` at `out` holding `stream` as its one snapshot.

    Refuses a malformed stream, a bad template and an existing `out`.  Reads
    the written file back and fails unless it decodes to exactly `stream`.
    """
    out = Path(out)
    if out.exists():
        raise FileExistsError(out)
    problems = check_template(template)
    if problems:
        raise ValueError(f"{template} is not a usable template: "
                         + "; ".join(problems))
    split_records(stream)
    ids = _ids(seed)
    if now is None:
        now = ("2026-08-29 10:40:00" if seed is not None else
               datetime.datetime.now(datetime.timezone.utc)
               .strftime("%Y-%m-%d %H:%M:%S"))
    tpl = _open_ro(template)
    owner = tpl.execute("select owner_uuid from projects").fetchone()[0]
    old_history = _history_table(tpl)
    new_history = "project_history_" + ids["main"]
    ddl = tpl.execute(
        "select sql from sqlite_master where sql is not null "
        "and name != 'sqlite_sequence' "
        "order by case type when 'table' then 0 else 1 end, rowid").fetchall()
    tmp = out.with_name(out.name + ".partial")
    if tmp.exists():
        tmp.unlink()
    db = sqlite3.connect(tmp)
    try:
        for (sql,) in ddl:
            db.execute(sql.replace(old_history, new_history))
        for table in COPY_ROWS:
            cols = [r[1] for r in tpl.execute(f'pragma table_info("{table}")')]
            if not cols:
                continue
            names = ",".join(f'"{c}"' for c in cols)
            for row in tpl.execute(f'select {names} from "{table}"'):
                db.execute(f'insert into "{table}" ({names}) values '
                           f'({",".join("?" * len(cols))})', row)
        blob = _aesgcm(ids["key"]).encrypt(
            bytes.fromhex(ids["history"]),
            gzip.compress(stream.encode("utf-8"), compresslevel=1, mtime=0),
            None)
        p = ids["project"]
        db.execute(
            "insert into projects (uuid, archive, name, content, cbb_project, "
            "thumb, ticket, g_ticket, owner_uuid, creator_uuid, created_at, "
            "updated_at, modifier_uuid, boards, block_symbol_attrs_groups, "
            "pcb_count, branch_uuid, default_sheet) "
            "values (?,0,?,'',0,'',1,1,?,?,?,?,?,'{}','{}',0,?,'')",
            (p, name, owner, owner, now, now, owner, ids["main"]))
        for bname, uuid, history, parent, node in (
                ("start", ids["start"], None, None, 1),
                ("main", ids["main"], ids["history"], ids["start"], 0)):
            db.execute(
                "insert into branches (uuid, project_uuid, name, history_uuid, "
                "creator_uuid, description, parent_uuid, modifier_uuid, node, "
                "created_at, updated_at) values (?,?,?,?,?,'',?,?,?,?,?)",
                (uuid, p, bname, history, owner, parent, owner, node, now, now))
        db.execute(f'insert into "{new_history}" (uuid, parent, snapshot, key, '
                   f'created_at, updated_at) values (?,NULL,NULL,?,?,?)',
                   (ids["history"], ids["key"], now, now))
        db.execute("insert into history_data (uuid, history_uuid, dataStr, "
                   "created_at, updated_at) values (?,?,?,?,?)",
                   (ids["history"], ids["history"],
                    base64.b64encode(blob).decode(), now, now))
        db.execute("insert into project_structures (ticket, project_uuid, "
                   "branch_uuid, structure) values (1,?,?,?)",
                   (p, ids["main"], _compact(structure)))
        db.execute("insert into project_members (role, project_uuid, user_uuid, "
                   "created_at, updated_at) values (1,?,?,?,?)",
                   (p, owner, now, now))
        db.commit()
    finally:
        db.close()
        tpl.close()
    os.replace(tmp, out)
    if read(out)["text"] != stream:
        raise RuntimeError(f"{out} does not decode to the stream written")
    return ids


# --- an .eprj3 folder as a stream -------------------------------------------------
def index_of(folder):
    folder = Path(folder)
    if folder.is_file():
        return folder
    found = sorted(folder.glob("*.eprj3"))
    if len(found) != 1:
        raise ValueError(f"{folder}: expected one .eprj3 index, found "
                         f"{[f.name for f in found]}")
    return found[0]


def _head(doc_type, uuid, stamp_ms):
    return ({"type": "DOCHEAD"},
            _compact({"docType": doc_type, "client": "0" * 16, "uuid": uuid,
                      "updateTime": stamp_ms, "version": str(stamp_ms),
                      "user": {}}))


def _meta(payload):
    return ({"type": "META", "ticket": 1, "id": "META"}, _compact(payload))


def from_eprj3(folder, owner, stamp_ms):
    """(stream, structure, name) for the `.eprj3` project in `folder`.

    Library documents repeated across sheet files must be identical, and are
    written once.  Boards live only in the index in `.eprj3`, so their BOARD
    documents are made here, and so is the CONFIG document.  Every structure
    entry must have its document and every top-level document its entry.
    """
    index_path = index_of(folder)
    root = index_path.parent
    index = json.loads(index_path.read_text(encoding="utf-8"))
    prof = index.get("profile", {})
    seen, docs = {}, []
    for f in sorted(p for p in root.rglob("*") if p.suffix in DOC_SUFFIXES):
        _, found = documents(split_records(f.read_text(encoding="utf-8")))
        for dt, uuid, recs in found:
            if (dt, uuid) in seen:
                if join(seen[(dt, uuid)]) != join(recs):
                    raise ValueError(f"{dt} {uuid} differs between files; "
                                     f"refusing to pick one")
                continue
            seen[(dt, uuid)] = recs
            docs.append((dt, uuid, recs))
    have = set(seen)
    for b in prof.get("boards", {}).values():
        if ("BOARD", b["uuid"]) not in have:
            docs.append(("BOARD", b["uuid"], [
                _head("BOARD", b["uuid"], stamp_ms),
                _meta({"title": b["title"], "zIndex": b.get("zIndex")})]))
    if ("CONFIG", "CONFIG") not in have:
        docs.append(("CONFIG", "CONFIG", [
            _head("CONFIG", "CONFIG", stamp_ms),
            _meta({"defaultSheet": index.get("default_sheet", "")})]))
    unknown = sorted({dt for dt, _, _ in docs} - set(DOC_ORDER))
    if unknown:
        raise ValueError(f"document types with no place in a snapshot: {unknown}")
    docs.sort(key=lambda d: DOC_ORDER.index(d[0]))
    lead = [({"type": "EDIT_HEAD"},
             _compact({"uuid": owner, "username": "", "nickname": "",
                       "updateTime": stamp_ms}))]
    stream = join(lead + [r for _, _, recs in docs for r in recs])

    def pick(entry, keys, defaults):
        return {k: entry.get(k, defaults.get(k)) for k in keys}
    structure = {
        "boards": {u: pick(e, ("uuid", "title", "zIndex"), {})
                   for u, e in prof.get("boards", {}).items()},
        "schematics": {u: pick(e, ("uuid", "name", "board", "version",
                                   "updateTime"), {"board": ""})
                       for u, e in prof.get("schematics", {}).items()},
        "sheets": {u: pick(e, ("uuid", "title", "schematic_uuid", "zIndex",
                               "version", "updateTime"), {})
                   for u, e in prof.get("sheets", {}).items()},
        "pcbs": {u: pick(e, ("uuid", "title", "board", "zIndex", "parent_uuid",
                             "version", "updateTime"),
                         {"board": "", "parent_uuid": ""})
                 for u, e in prof.get("pcbs", {}).items()},
        "panels": prof.get("panels", {}),
        "blockSymbols": prof.get("blockSymbols", {}),
        "owner": {"uuid": ""},
    }
    need = ({("BOARD", u) for u in structure["boards"]}
            | {("SCH", u) for u in structure["schematics"]}
            | {("SCH_PAGE", u) for u in structure["sheets"]}
            | {("PCB", u) for u in structure["pcbs"]})
    got = {(dt, u) for dt, u, _ in docs if dt in ("BOARD", "SCH", "SCH_PAGE", "PCB")}
    if need != got:
        raise ValueError(f"index and documents disagree: no document for "
                         f"{sorted(need - got)}, not in the index "
                         f"{sorted(got - need)}")
    return stream, structure, index.get("name") or root.name


def find_template(home=None):
    """An editor-saved `.eprj2` to use as a template, or None.

    `EASYEDA_EPRJ2_TEMPLATE` wins; then the editor's example projects, then its
    projects folder, newest first."""
    env = os.environ.get("EASYEDA_EPRJ2_TEMPLATE")
    if env:
        return Path(env)
    home = Path(home or Path.home())
    for d in EDITOR_DIRS:
        cands = sorted((home / d).glob("*.eprj2"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for c in cands:
            if not check_template(c):
                return c
    return None


def convert(folder, out, template, *, name=None, stamp_ms=None):
    """Wrap the `.eprj3` project in `folder` as `out`, replacing an earlier
    `out`.  Deterministic: the ids and key derive from the content, so the
    same design gives the same file and a changed design a new project."""
    tpl_owner = _open_ro(template).execute(
        "select owner_uuid from projects").fetchone()[0]
    stamp = 1788000000000 if stamp_ms is None else stamp_ms
    stream, structure, found = from_eprj3(folder, tpl_owner, stamp)
    seed = hashlib.sha256(stream.encode("utf-8")).hexdigest()
    out = Path(out)
    if out.exists():
        out.unlink()
    write(template, out, stream, structure, name or found, seed=seed)
    return out


# --- command line ------------------------------------------------------------------
def _cmd_info(a):
    db = _open_ro(a.file)
    print("tables with rows:")
    for (t,) in db.execute("select name from sqlite_master where type='table' "
                           "order by name"):
        n = db.execute(f'select count(*) from "{t}"').fetchone()[0]
        if n:
            print(f"  {t:50} {n}")
    print("db version:", dict(db.execute("select key, value from db_versions")))
    snap = read(a.file)
    print(f"project {snap['name']!r}  owner {snap['owner']}  "
          f"snapshot {snap['history']}")
    for k in ("boards", "schematics", "sheets", "pcbs", "panels"):
        print(f"  {k:11}", [e.get("title") or e.get("name")
                            for e in snap["structure"].get(k, {}).values()])
    _, docs = documents(split_records(snap["text"]))
    print("documents:", dict(Counter(d[0] for d in docs)))
    print("editVersion:", dict(Counter(json.loads(d[2][0][1]).get("editVersion")
                                       for d in docs)))


def _cmd_decode(a):
    snap = read(a.file)
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stream.txt").write_text(snap["text"], encoding="utf-8")
    (out / "structure.json").write_text(
        json.dumps(snap["structure"], indent=1, ensure_ascii=False),
        encoding="utf-8")
    _, docs = documents(split_records(snap["text"]))
    for dt, uuid, recs in docs:
        (out / "docs" / dt).mkdir(parents=True, exist_ok=True)
        (out / "docs" / dt / f"{uuid}.txt").write_text(join(recs),
                                                        encoding="utf-8")
    print(f"{a.file} -> {out}: stream.txt, structure.json, {len(docs)} documents")


def _template(a):
    t = a.template or find_template()
    if t is None:
        sys.exit("no template: pass --template, set EASYEDA_EPRJ2_TEMPLATE, or "
                 "open any project in EasyEDA Pro once so it saves an .eprj2")
    return t


def _cmd_from_eprj3(a):
    out = convert(a.folder, a.out, _template(a), name=a.name)
    _, docs = documents(split_records(read(out)["text"]))
    print(f"wrote {out}: {dict(Counter(d[0] for d in docs))}")


def _cmd_encode(a):
    write(_template(a), a.out, Path(a.stream).read_text(encoding="utf-8"),
          json.loads(Path(a.structure).read_text(encoding="utf-8")), a.name,
          seed=a.seed)
    print(f"wrote {a.out}")


def _cmd_roundtrip(a):
    snap = read(a.file)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "rt.eprj2"
        write(a.file, out, snap["text"], snap["structure"], snap["name"])
        back = read(out)
    same = back["text"] == snap["text"] and back["structure"] == snap["structure"]
    print("roundtrip:", "IDENTICAL" if same else "DIFFERS")
    return 0 if same else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info"); p.add_argument("file"); p.set_defaults(f=_cmd_info)
    p = sub.add_parser("decode"); p.add_argument("file"); p.add_argument("outdir")
    p.set_defaults(f=_cmd_decode)
    p = sub.add_parser("from-eprj3"); p.add_argument("--template")
    p.add_argument("--name"); p.add_argument("folder"); p.add_argument("out")
    p.set_defaults(f=_cmd_from_eprj3)
    p = sub.add_parser("encode"); p.add_argument("--template")
    p.add_argument("--stream", required=True)
    p.add_argument("--structure", required=True)
    p.add_argument("--name", required=True); p.add_argument("--seed")
    p.add_argument("out"); p.set_defaults(f=_cmd_encode)
    p = sub.add_parser("roundtrip"); p.add_argument("file")
    p.set_defaults(f=_cmd_roundtrip)
    a = ap.parse_args(argv)
    return a.f(a) or 0


if __name__ == "__main__":
    sys.exit(main())
