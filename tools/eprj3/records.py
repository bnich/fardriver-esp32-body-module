"""THE ENCODING BOUNDARY.

EasyEDA document two record encodings and they do not agree with each other:

  ARRAY   `fmt2 general/conventions.md`: "The file is line-oriented; each line
          is a valid JSON array".  Header `["DOCTYPE","SCH","1.0"]`, then
          `["HEAD",{...}]`.

  OBJECT  what the real `.eprj3` example project actually contains:
          `{"type":"DOCHEAD"}||{"docType":"SYMBOL",...}|`
          -- JSON objects, `||` between header and payload, trailing `|`.

Which one a current EasyEDA Pro accepts for a `.eprj3` folder project is
UNKNOWN until a human opens a generated file.  That is what the gauge exists
for, and it is why `ENCODING` starts as None and `serialize_record` REFUSES to
guess: a wrong encoding found on a four-board project costs the whole
generator, and found on a two-resistor gauge costs a minute.

Every record emitted anywhere in this package goes through `serialize_record`,
so settling the question changes exactly this file.
"""
import json

ARRAY = "array"
OBJECT = "object"

#: Settled by the gauge (plan Task 1).  None = not yet proven against the
#: real editor.  Set it here, with the date and who tested it, once known.
ENCODING = None


class EncodingNotSettled(RuntimeError):
    """Raised when something tries to emit before the gauge has run."""


def _compact(obj) -> str:
    """JSON with no whitespace, matching what the real files contain."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def serialize_record(record, encoding: str | None = None, payload=None) -> str:
    """Serialize one record in the settled (or explicitly requested) encoding.

    `payload` is used only by OBJECT, which splits each record into a header
    object and a payload object separated by `||`.
    """
    enc = encoding or ENCODING
    if enc is None:
        raise EncodingNotSettled(
            "Record encoding is not settled. Generate the gauge project, have "
            "it opened in EasyEDA Pro, then set records.ENCODING. "
            "See docs/plans/2026-09-15-board-set.md Task 1."
        )
    if enc == ARRAY:
        return _compact(record)
    if enc == OBJECT:
        return f"{_compact(record)}||{_compact(payload if payload is not None else {})}|"
    raise ValueError(f"unknown encoding {enc!r}; expected {ARRAY!r} or {OBJECT!r}")
