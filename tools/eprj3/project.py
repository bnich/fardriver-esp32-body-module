"""The `.eprj3` project container: the index file and the folder tree under it.

A project is a folder, not an archive:

    <name>/
      <name>.eprj3                     the index -- ordinary JSON, 2-space
                                       indent, ONE trailing newline
      sch/<schematic>/<schematic>.ecfg  the schematic document itself
      sch/<schematic>/<sheet>.esch2     one file per sheet
      pcb/<board>.epcb2                 one file per PCB

⚠️ `.ecfg` is NOT a side-file of settings.  It IS the schematic document: the
schematic's title and its link to a board exist nowhere else.

⚠️ A PCB is bound to a schematic INDIRECTLY, through a board.  There is no
pcb -> schematic field anywhere.  The chain is

    profile.schematics[SCH].board == BOARD    and    profile.pcbs[PCB].board == BOARD

and both documents restate it in their own META.  All four references must
agree or the editor shows an orphaned board.  `referential_errors()` checks
exactly that, and the tests run it.

⚠️ UUIDS ARE DERIVED, NOT RANDOM.  `uuid4()` would make two runs of the
generator produce different files for the same board, which destroys the only
cheap check that a regenerated project is the same project.  Every id here is
a SHA-1 of a namespaced name, so the tree is a pure function of its inputs --
and so is `epoch_ms`, which is why it defaults to a stated constant rather
than the clock.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..board_params import STACK_ORDER
from .pcb import EDIT_VERSION, Pcb
from .records import join_records, serialize_record

#: Default timestamp for every document, so two runs are byte-identical.
#: Overridable, but a caller that passes `time.time()` gives up determinism.
DEFAULT_EPOCH_MS = 1788000000000

#: Titles become path components.  The format imposes no restriction, but the
#: v2 packaging did, and a title with a slash in it makes a folder.  ⚠️ This
#: guard lives in the shared helper, not at each call site, so it protects
#: every caller including the ones that do not exist yet.
_SAFE_TITLE = re.compile(r"^[A-Za-z0-9 _.-]+$")


def _check_title(kind, title):
    if not isinstance(title, str) or not _SAFE_TITLE.match(title):
        raise ValueError(
            f"{kind} title {title!r} must match [A-Za-z0-9 _.-]+ -- it becomes "
            f"a file or folder name")
    return title


def _uid(*parts, length=16):
    """A deterministic lowercase-hex id.

    The namespace parts matter: a board, a schematic and a PCB in this project
    may all be called "HVIN", and three identical uuids would collapse the
    index into nonsense.  Every caller passes its kind first.
    """
    key = ":".join(str(p) for p in parts).encode("utf-8")
    return hashlib.sha1(key).hexdigest()[:length]


def _timestamp(epoch_ms):
    """`"%Y-%m-%d %H:%M:%S"` -- not ISO-8601, no timezone marker.

    Rendered in UTC so the tree does not change when the machine moves.
    """
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S")


class Sheet:
    """One schematic page. Holds no canvas and no layers: DOCHEAD + META."""

    def __init__(self, title, uuid, schematic_uuid, z_index, client, epoch_ms,
                 edit_version=EDIT_VERSION):
        self.title = _check_title("sheet", title)
        self.uuid = uuid
        self.schematic_uuid = schematic_uuid
        self.z_index = z_index
        self.client = client
        self.epoch_ms = epoch_ms
        self.edit_version = edit_version

    def document(self):
        head = serialize_record(
            {"type": "DOCHEAD"},
            payload={"docType": "SCH_PAGE", "client": self.client,
                     "uuid": self.uuid, "updateTime": self.epoch_ms,
                     "version": str(self.epoch_ms),
                     "editVersion": self.edit_version, "user": {}})
        # The sheet's META names the schematic with the key "schematic";
        # the index's entry for the same link is "schematic_uuid".
        meta = serialize_record(
            {"type": "META", "ticket": 1, "id": "META"},
            payload={"title": self.title, "schematic": self.schematic_uuid,
                     "source": "", "zIndex": self.z_index})
        return join_records([head, meta])


class Schematic:
    """A schematic and its sheets. The `.ecfg` is the schematic document."""

    def __init__(self, name, uuid, board_uuid, client, epoch_ms,
                 edit_version=EDIT_VERSION):
        self.name = _check_title("schematic", name)
        self.uuid = uuid
        self.board_uuid = board_uuid
        self.client = client
        self.epoch_ms = epoch_ms
        self.edit_version = edit_version
        self.sheets = []

    def add_sheet(self, title):
        sheet = Sheet(title, _uid("sheet", self.uuid, title),
                      self.uuid, len(self.sheets) + 1,
                      self.client, self.epoch_ms, self.edit_version)
        self.sheets.append(sheet)
        return sheet

    def document(self):
        head = serialize_record(
            {"type": "DOCHEAD"},
            payload={"docType": "SCH", "client": self.client,
                     "uuid": self.uuid, "updateTime": self.epoch_ms,
                     "version": str(self.epoch_ms),
                     "editVersion": self.edit_version, "user": {}})
        # Note "name" in the index but "title" here -- schematics are the one
        # item type that disagrees with itself about which key to use.
        meta = serialize_record(
            {"type": "META", "ticket": 1, "id": "META"},
            payload={"title": self.name, "source": "",
                     "board": self.board_uuid, "zIndex": None})
        return join_records([head, meta])


class Board:
    """A board: the join between a schematic and a PCB.

    ⚠️ There is no file for a board.  It exists only as an index entry plus
    the uuid references that point at it.
    """

    def __init__(self, title, uuid, z_index):
        self.title = _check_title("board", title)
        self.uuid = uuid
        self.z_index = z_index
        self.schematic = None
        self.pcb = None


class Project:
    """An `.eprj3` folder project.

    Usage:

        project = Project("esp32-body-module")
        project.add_board("HVIN")
        project.write("/somewhere")

    `write()` returns the project folder it created.  Writing twice with the
    same inputs produces byte-identical trees.
    """

    def __init__(self, name, *, epoch_ms=DEFAULT_EPOCH_MS,
                 edit_version=EDIT_VERSION, content=""):
        self.name = _check_title("project", name)
        self.epoch_ms = epoch_ms
        self.edit_version = edit_version
        self.content = content
        # The cloud account ids.  Locally authored projects have no account,
        # so they are derived from the project name: stable, and obviously not
        # a real person's id.
        self.owner_uuid = _uid("owner", name, length=32)
        self.client = _uid("client", name)
        self.boards = []

    # -- construction --------------------------------------------------------
    def add_board(self, title, *, schematic_name=None, pcb_title=None,
                  sheets=("P1",), **pcb_kwargs):
        """Add a board with its schematic, its sheets and its PCB.

        Returns the `Pcb`, which is the object a caller normally wants to
        adjust (size, holes, rules).
        """
        if any(b.title == title for b in self.boards):
            raise ValueError(
                f"board {title!r} already exists -- titles derive the uuids, "
                f"so a duplicate would collide")
        if not sheets:
            raise ValueError("a schematic with no sheets has nothing to open")

        board = Board(title, _uid("board", self.name, title),
                      len(self.boards) + 1)

        schematic_name = schematic_name or title
        board.schematic = Schematic(
            schematic_name, _uid("schematic", self.name, schematic_name),
            board.uuid, self.client, self.epoch_ms, self.edit_version)
        for sheet_title in sheets:
            board.schematic.add_sheet(sheet_title)

        pcb_title = pcb_title or title
        board.pcb = Pcb(_check_title("pcb", pcb_title),
                        _uid("pcb", self.name, pcb_title),
                        board.uuid, self.client, self.epoch_ms,
                        edit_version=self.edit_version, **pcb_kwargs)

        self.boards.append(board)
        return board.pcb

    @classmethod
    def for_stack(cls, name, layers=STACK_ORDER, **kwargs):
        """One board per layer of the physical stack, bottom to top.

        The stack order is `board_params.STACK_ORDER`, its one home, so the
        project cannot list a board the enclosure budget does not know about.
        """
        project = cls(name, **kwargs)
        for layer in layers:
            project.add_board(layer)
        return project

    # -- the index -----------------------------------------------------------
    def index(self):
        """The `<name>.eprj3` content, as a dict."""
        stamp = _timestamp(self.epoch_ms)
        version = str(self.epoch_ms)

        boards, schematics, sheets, pcbs = {}, {}, {}, {}
        for board in self.boards:
            boards[board.uuid] = {"uuid": board.uuid, "title": board.title,
                                  "zIndex": board.z_index}
            schematic = board.schematic
            schematics[schematic.uuid] = {
                "uuid": schematic.uuid, "name": schematic.name,
                "board": board.uuid, "source": "",
                "version": version, "updateTime": self.epoch_ms}
            for sheet in schematic.sheets:
                sheets[sheet.uuid] = {
                    "uuid": sheet.uuid, "title": sheet.title,
                    "schematic_uuid": schematic.uuid, "zIndex": sheet.z_index,
                    "source": "", "version": version,
                    "updateTime": self.epoch_ms}
            pcb = board.pcb
            pcbs[pcb.uuid] = {"uuid": pcb.uuid, "title": pcb.title,
                              "board": board.uuid, "parent_uuid": "",
                              "source": "", "version": version,
                              "updateTime": self.epoch_ms}

        return {
            "name": self.name,
            "owner_uuid": self.owner_uuid,
            "creator_uuid": self.owner_uuid,
            "modifier_uuid": self.owner_uuid,
            "created_at": stamp,
            "updated_at": stamp,
            "content": self.content,
            "archive": False,
            # An integer 0/1, unlike `archive`, which really is a boolean.
            "cbb_project": 0,
            "thumb": "",
            "ticket": 1,
            "g_ticket": 1,
            # ⚠️ Vestigial and always empty: the real board list is
            # profile.boards.  A real saved project leaves it [] too.
            "boards": [],
            "block_symbol_attrs_groups": {},
            "default_sheet": "",
            "branch_uuid": "",
            # Not validated on load -- a real saved project with one PCB also
            # says 0 -- but there is no reason to write a wrong number.
            "pcb_count": len(self.boards),
            # The only place the folder format declares itself.
            "format": "folder",
            "profile": {
                "boards": boards,
                "schematics": schematics,
                "sheets": sheets,
                "pcbs": pcbs,
                "panels": {},
                "blockSymbols": {},
                "owner": {"uuid": self.owner_uuid},
                "simSchematics": {},
                "simulations": {},
            },
            # defaultSheet is duplicated here in camelCase and at top level in
            # snake_case.  Keep both, keep them equal.
            "config": {"defaultSheet": "", "settings": {}},
        }

    def index_text(self):
        return json.dumps(self.index(), ensure_ascii=False, indent=2) + "\n"

    # -- the tree ------------------------------------------------------------
    def documents(self):
        """Relative path -> file text, for every file in the project.

        Folders are created lazily by the editor and an absent one is legal,
        so there is no `panel/` and no `.evar` here: nothing uses them.
        """
        files = {f"{self.name}.eprj3": self.index_text()}
        for board in self.boards:
            schematic = board.schematic
            folder = f"sch/{schematic.name}"
            files[f"{folder}/{schematic.name}.ecfg"] = schematic.document()
            for sheet in schematic.sheets:
                files[f"{folder}/{sheet.title}.esch2"] = sheet.document()
            files[f"pcb/{board.pcb.title}.epcb2"] = board.pcb.document()
        return files

    def write(self, dest_dir):
        """Write the project folder under `dest_dir`; return its path.

        The folder basename, the `.eprj3` basename and `index["name"]` are all
        the same string -- that three-way identity is the project's name and
        nothing in the format enforces it for you.
        """
        errors = self.referential_errors()
        if errors:
            raise ValueError("project index is inconsistent: "
                             + "; ".join(errors))
        root = Path(dest_dir) / self.name
        for relative, text in self.documents().items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        return root

    # -- the check that the whole format hangs on ----------------------------
    def referential_errors(self):
        """Every broken cross-reference in the index, as readable strings.

        Empty means the four-way board binding holds and every map key equals
        the uuid inside its entry.  A dangling reference does not stop the
        project opening -- it opens with a board that has lost its PCB, which
        is precisely the failure that is hard to see by eye.
        """
        index = self.index()
        profile = index["profile"]
        errors = []

        for map_name in ("boards", "schematics", "sheets", "pcbs"):
            for key, entry in profile[map_name].items():
                if entry["uuid"] != key:
                    errors.append(
                        f"profile.{map_name}[{key}].uuid is {entry['uuid']}")

        boards = set(profile["boards"])
        for key, entry in profile["schematics"].items():
            if entry["board"] not in boards:
                errors.append(f"schematic {key} -> unknown board "
                              f"{entry['board']}")
        for key, entry in profile["pcbs"].items():
            if entry["board"] not in boards:
                errors.append(f"pcb {key} -> unknown board {entry['board']}")
        schematics = set(profile["schematics"])
        for key, entry in profile["sheets"].items():
            if entry["schematic_uuid"] not in schematics:
                errors.append(f"sheet {key} -> unknown schematic "
                              f"{entry['schematic_uuid']}")

        if profile["owner"]["uuid"] != index["owner_uuid"]:
            errors.append("profile.owner.uuid != owner_uuid")
        if index["config"]["defaultSheet"] != index["default_sheet"]:
            errors.append("config.defaultSheet != default_sheet")

        # The documents must restate the same board uuid as the index does.
        for board in self.boards:
            if board.schematic.board_uuid != board.uuid:
                errors.append(f"{board.schematic.name}.ecfg META.board "
                              f"!= board {board.title}")
            if board.pcb.board_uuid != board.uuid:
                errors.append(f"{board.pcb.title}.epcb2 META.board "
                              f"!= board {board.title}")
            for sheet in board.schematic.sheets:
                if sheet.schematic_uuid != board.schematic.uuid:
                    errors.append(f"sheet {sheet.title} META.schematic "
                                  f"!= schematic {board.schematic.name}")
        return errors
