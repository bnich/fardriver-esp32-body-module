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

#: ⭐ SETTLED 2026-09-15 from the editor's own source, not from the gauge.
#:
#: EasyEDA Pro 2.2.45.4 is installed on this host (/opt/easyeda-pro). Its
#: parser, in resources/app/assets/pro-api/.../api.js, reads:
#:
#:   parseLine(e,t,i){ let r=e.indexOf("||"), n=r!==-1,
#:     s=n?Oc(e,0,r):e,      // header, before ||
#:     a=n?Oc(e,r+2):"",     // payload, after ||
#:     o=JSON.parse(s);      // header parsed...
#:     this.onLine(o.id,o.ticket,a,o.type,o.client,...) }  // ...read by NAME
#:
#: `o.type` on a JSON ARRAY is undefined, so V2 array records inside a V3
#: document are silently dropped -- no error, just missing geometry.
#: fmt2/README says it plainly: "Since version 3 ... stopped using the file
#: format of version 2". fmt2 describes V2; .esch2/.epcb2 are V3.
#:
#: Independently confirmed by byte-exact round-trip: splitting every example
#: document on "|\n", JSON-parsing both halves and re-joining reproduces the
#: original bytes exactly.
ENCODING = OBJECT


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
