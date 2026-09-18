"""Where each part goes on its board's sheet: grouped by function, never
overlapping, on the grid.

Every part occupies a CELL: its body, its pins, the 2-grid stub on every
connected pin, the net flag at the stub's end, the flag's name text, and the
designator and name lines above and below.  Cells are stacked with a gap and
never overlap, so no flag, stub or anchor of one part can land on anything of
another's.  `schematic.py` then only has to place each part at the origin this
module returns; the tests re-derive the anchors from the emitted file and
check that no point carries two nets.

Grouping, deterministic:

  * An ANCHOR is a part that is not a two-pin part: an IC, a module, a
    converter, a FET, a choke, a TVS array.
  * Every two-pin part joins the anchor it reaches in the fewest hops over
    SIGNAL nets through other two-pin parts (ties go to the lowest refdes).
    Rails and ground are not signal nets for this purpose: everything touches
    GND, so following it would put the whole board in one group.
  * Two-pin parts that reach no anchor group with each other by the signal
    nets they share.
  * Connectors are laid out as one column along the left edge.

The layout is a set of columns: groups are stacked top-down and a new column
starts when the next group would pass the sheet's height, which is chosen for
a roughly landscape sheet.  A group taller than that wraps into sub-columns.

Nothing here is electrical: it only decides positions.  ⚠️ Text widths are
ESTIMATES (`symbols.CHAR_W`) because the theme-default font size is not stated
in the format.  The estimate is generous; if the real font is wider still,
labels can overlap each other.  Text carries no connectivity, so that can make
the sheet harder to read but can never join or split a net.
"""
import math
import re
from collections import deque
from dataclasses import dataclass

from . import symbols as sym
from .symbols import CHAR_W, GRID, TEXT_H

#: Stub length: two grid steps from the pin anchor to the net flag.
STUB = 2 * GRID
#: Gap between a flag glyph and its name text.
LABEL_GAP = 3
#: Clear space between two cells, and between columns.
CELL_GAP = 2 * GRID
COLUMN_GAP = 4 * GRID
#: Target width:height of a board's sheet.
ASPECT = 1.5
#: Top-left corner of the content: the sheet body lives at x > 0, y < 0 (§4.2).
MARGIN = 10 * GRID
#: A net touching more pins than this on one board is treated like a rail for
#: grouping, whatever its name -- following it would merge unrelated groups.
MAX_SIGNAL_FANOUT = 12

_REF = re.compile(r"^([A-Z]+)(\d+)(.*)$")


def refdes_key(ref):
    """Natural refdes order: R2 < R10 < R101A < R101B."""
    m = _REF.match(ref)
    if not m:
        return (ref, 0, "")
    return (m.group(1), int(m.group(2)), m.group(3))


def _floor(v):
    return int(math.floor(v / GRID) * GRID)


def _ceil(v):
    return int(math.ceil(v / GRID) * GRID)


@dataclass
class Item:
    """One placeable thing: a part or a connector."""
    ref: str
    symbol: object
    #: pin number -> net name, for the pins that get a wire.
    nets: dict
    designator: str
    name: str
    is_connector: bool = False

    def extent(self):
        """The cell in symbol-local coordinates, (x1, y1, x2, y2), on grid.

        Covers the body, every pin, every stub + flag + flag text, and the
        designator/name lines.  Anything drawn for this item is inside it.
        """
        bx1, by1, bx2, by2 = self.symbol.body
        x1, x2 = bx1, bx2
        ys = [by1, by2]
        for p in self.symbol.pins:
            ys.append(p.y)
            x1, x2 = min(x1, p.x), max(x2, p.x)
            if p.label:
                w = len(p.name) * CHAR_W
                lx = p.label[0]
                x1, x2 = min(x1, lx - w), max(x2, lx + w)
            net = self.nets.get(p.number)
            if net is None:
                continue
            reach = (STUB + sym.net_flag(net).reach + LABEL_GAP
                     + len(net) * CHAR_W)
            end = p.x + p.outward * reach
            x1, x2 = min(x1, end), max(x2, end)
        half_label = max(len(self.designator), len(self.name)) * CHAR_W / 2
        x1, x2 = min(x1, -half_label), max(x2, half_label)
        y1 = min(ys) - 4 - (TEXT_H + 5)   # designator line above the body
        y2 = max(ys) + 4 + (TEXT_H + 5)   # name line below it
        return (_floor(x1), _floor(y1), _ceil(x2), _ceil(y2))


def signal_nets(fanout):
    """Net names usable for grouping: not ground, not a rail, not a bus.

    `fanout` maps net name -> how many items on this board touch it.
    """
    out = set()
    for net, count in fanout.items():
        if net in sym.GROUND_NETS or net in sym.RAIL_NETS:
            continue
        if count > MAX_SIGNAL_FANOUT:
            continue
        out.add(net)
    return out


def groups(items):
    """[[ref, ...], ...] -- connectors first, then one group per anchor, then
    the anchor-less clusters.  Deterministic."""
    by_ref = {i.ref: i for i in items}
    fanout = {}
    for i in items:
        for net in i.nets.values():
            fanout[net] = fanout.get(net, 0) + 1
    signal = signal_nets(fanout)

    net_members = {}
    for i in items:
        for net in sorted(set(i.nets.values())):
            if net in signal:
                net_members.setdefault(net, []).append(i.ref)

    def neighbours(ref):
        out = set()
        for net in by_ref[ref].nets.values():
            if net in signal:
                out.update(net_members[net])
        out.discard(ref)
        return sorted(out, key=refdes_key)

    connectors = sorted((i.ref for i in items if i.is_connector),
                        key=refdes_key)
    parts = [i for i in items if not i.is_connector]
    anchors = sorted((i.ref for i in parts
                      if not _is_two_pin(i.symbol)), key=refdes_key)
    anchor_set = set(anchors)
    small = sorted((i.ref for i in parts if i.ref not in anchor_set),
                   key=refdes_key)

    home = {}   # small ref -> (distance, anchor)
    for ref in small:
        seen = {ref}
        frontier = deque([(ref, 0)])
        best = None
        while frontier:
            here, dist = frontier.popleft()
            if best is not None and dist >= best[0]:
                break
            for nb in neighbours(here):
                if nb in seen or by_ref[nb].is_connector:
                    continue
                seen.add(nb)
                if nb in anchor_set:
                    cand = (dist + 1, refdes_key(nb), nb)
                    if best is None or cand < best:
                        best = cand
                else:
                    frontier.append((nb, dist + 1))
        if best is not None:
            home[ref] = (best[0], best[2])

    out = [connectors] if connectors else []
    for a in anchors:
        members = sorted((r for r, (_, h) in home.items() if h == a),
                         key=lambda r: (home[r][0], refdes_key(r)))
        out.append([a] + members)

    # Anchor-less two-pin parts: clusters over shared signal nets.
    rest = [r for r in small if r not in home]
    rest_set = set(rest)
    seen = set()
    clusters = []
    for ref in rest:
        if ref in seen:
            continue
        comp, queue = [], deque([ref])
        seen.add(ref)
        while queue:
            here = queue.popleft()
            comp.append(here)
            for nb in neighbours(here):
                if nb in rest_set and nb not in seen:
                    seen.add(nb)
                    queue.append(nb)
        clusters.append(sorted(comp, key=refdes_key))
    clusters.sort(key=lambda c: refdes_key(c[0]))
    return out + clusters


def _is_two_pin(symbol):
    return symbol.key[0] == "part" and symbol.key[1] in sym.TWO_PIN_KINDS \
        and len(symbol.key[2]) <= 2


@dataclass
class Layout:
    #: ref -> (x, y) component origin, absolute sheet coordinates.
    origins: dict
    #: ref -> absolute cell (x1, y1, x2, y2).
    cells: dict
    #: the whole content, (x1, y1, x2, y2).
    extent: tuple
    groups: list


def layout(items):
    """Place every item.  Returns a `Layout`; all origins are on the grid."""
    by_ref = {i.ref: i for i in items}
    ext = {i.ref: i.extent() for i in items}
    size = {r: (e[2] - e[0], e[3] - e[1]) for r, e in ext.items()}
    grouped = groups(items)

    area = sum((w + CELL_GAP) * (h + CELL_GAP) for w, h in size.values())
    tallest = max((h for _, h in size.values()), default=0)
    height = max(tallest, _ceil(math.sqrt(area / ASPECT)), 40 * GRID)

    # Each group -> a block of sub-columns no taller than `height`.
    blocks = []
    for members in grouped:
        subcols, col, col_h = [], [], 0
        for ref in members:
            h = size[ref][1]
            if col and col_h + CELL_GAP + h > height:
                subcols.append(col)
                col, col_h = [], 0
            col_h += (CELL_GAP if col else 0) + h
            col.append(ref)
        if col:
            subcols.append(col)
        widths = [max(size[r][0] for r in c) for c in subcols]
        heights = [sum(size[r][1] for r in c) + CELL_GAP * (len(c) - 1)
                   for c in subcols]
        blocks.append((subcols, widths,
                       sum(widths) + CELL_GAP * (len(widths) - 1),
                       max(heights)))

    # Blocks -> page columns.  The connector block, when there is one, is
    # first and gets a column of its own: the left edge of the sheet.
    columns, start = [], 0
    if grouped and by_ref[grouped[0][0]].is_connector:
        columns.append([blocks[0]])
        start = 1
    col, col_h = [], 0
    for block in blocks[start:]:
        bh = block[3]
        if col and col_h + CELL_GAP + bh > height:
            columns.append(col)
            col, col_h = [], 0
        col_h += (CELL_GAP if col else 0) + bh
        col.append(block)
    if col:
        columns.append(col)

    total_h = max((sum(b[3] for b in c) + CELL_GAP * (len(c) - 1)
                   for c in columns), default=0)
    top = -(MARGIN + _ceil(total_h))
    origins, cells = {}, {}
    x = MARGIN
    for column in columns:
        y = top
        col_w = max(b[2] for b in column)
        for subcols, widths, bw, bh in column:
            sx = x
            for sub, w in zip(subcols, widths):
                sy = y
                for ref in sub:
                    ex1, ey1, ex2, ey2 = ext[ref]
                    ox, oy = sx - ex1, sy - ey1
                    origins[ref] = (ox, oy)
                    cells[ref] = (sx, sy, sx + ex2 - ex1, sy + ey2 - ey1)
                    sy += (ey2 - ey1) + CELL_GAP
                sx += w + CELL_GAP
            y += bh + CELL_GAP
        x += col_w + COLUMN_GAP

    xs1 = min((c[0] for c in cells.values()), default=0)
    ys1 = min((c[1] for c in cells.values()), default=0)
    xs2 = max((c[2] for c in cells.values()), default=0)
    ys2 = max((c[3] for c in cells.values()), default=0)
    return Layout(origins=origins, cells=cells, extent=(xs1, ys1, xs2, ys2),
                  groups=grouped)


def overlaps(layout_):
    """Every pair of cells that intersect, as (ref, ref).  Must be empty."""
    refs = sorted(layout_.cells, key=refdes_key)
    out = []
    for i, a in enumerate(refs):
        ax1, ay1, ax2, ay2 = layout_.cells[a]
        for b in refs[i + 1:]:
            bx1, by1, bx2, by2 = layout_.cells[b]
            if ax1 < bx2 and bx1 < ax2 and ay1 < by2 and by1 < ay2:
                out.append((a, b))
    return out
