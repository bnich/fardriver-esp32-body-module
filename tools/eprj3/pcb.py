"""The `.epcb2` PCB document: a rectangular board, a 4-layer stackup, four M3
mounting holes and a board-wide clearance rule.

⛔ EVERY BYTE HERE IS AUTHORED, NOT HARVESTED.  The layer table, the display
configuration, the stackup and the rule set are *generated* from the documented
enumerations plus the stated stackup and rule parameters below.  No part of
EasyEDA's example project is copied into this repository as data -- the example
was read once to check that what this module generates is shaped the same way.
That matters because this repo is public and the example is vendor material.

What the format demands, and where it is written down:

  * A record is `header||body`, records joined by `"|" + LF`, no trailing `|`
    and no trailing newline.  `records.serialize_record` formats a record and
    `records.join_records` owns the separator; this module does neither, and
    never formats JSON itself except for the composite `id` strings, which ARE
    JSON (a compact array serialised into a string).
  * ⛔ PCB coordinates are MIL (0.0254 mm).  Schematic units are ten times
    larger.  Nothing here writes a conversion factor; `units.mm_to_pcb` is the
    single home for it.
  * `"R"` paths give the TOP-LEFT corner: the rectangle covers
    `x in [x, x+width]` and `y in [y-height, y]`.  +Y is up, so the board sits
    in the first quadrant with its bottom-left corner on the origin.
  * ⚠️ A rule's `"unit":"mm"` is a display hint and is a LIE about the numbers
    beside it -- they are mil like everything else.  Hence every rule number
    below is stated in mm and converted, never typed in file units.

The board envelope is NOT stated here.  It comes from `board_params`, which is
its one home, so the outline cannot drift from the budget that proved it fits.
"""
import hashlib
import json

from ..board_params import BOARD_L, BOARD_W
from .records import join_records, serialize_record
from .units import mm_to_pcb

#: The editor version this document claims to have been written by.  There is
#: no per-document format-version record in `.eprj3`; `editVersion` replaced it.
EDIT_VERSION = "2.3.0"

# --- layer ids -------------------------------------------------------------
# Fixed by the editor's implementation, identical in every real file.  The
# format itself does not mandate them ("the implementation decides"), but
# everything that reads a board assumes these, so they are effectively fixed.
TOP_COPPER = 1
BOTTOM_COPPER = 2
TOP_SILK = 3
BOT_SILK = 4
TOP_MASK = 5
BOT_MASK = 6
TOP_PASTE = 7
BOT_PASTE = 8
OUTLINE_LAYER = 11      # where the board edge lives
MULTI_LAYER = 12        # through-hole pads and non-plated holes
DOCUMENT_LAYER = 13
FIRST_INNER_LAYER = 15  # 15..46 are the 32 SIGNAL inner layers
INNER_LAYER_COUNT = 32
SUBSTRATE_LAYER = 361   # first dielectric; 362, 363... for thicker stacks

#: Outline stroke, cosmetic only: the board edge is the path centreline.
OUTLINE_STROKE_MM = 0.254

#: M3 clearance hole.  3.2 mm passes an M3 screw with the usual 0.2 mm slop.
M3_CLEARANCE_MM = 3.2
#: Hole centre inset from both edges.  3.5 mm leaves 1.9 mm of FR4 between the
#: drill and the board edge, which survives routing and a washer's footprint.
M3_INSET_MM = 3.5


def _u(mm):
    """mm -> file units, rounded to the 4 decimals the editor itself writes.

    4 dp of a mil is 2.5 nm, far below any tolerance that exists in a PCB.
    An exactly-integral result is emitted as an int, because that is what the
    editor writes and it keeps the file diffable against one it saves.
    """
    v = round(mm_to_pcb(mm), 4)
    return int(v) if v == int(v) else v


def _num(value):
    """Emit an integral float as an int, as the editor does.

    Not a conversion -- just the difference between `10` and `10.0` in the
    file. Applies to the handful of numbers that are already in their final
    unit and so never pass through `_u`.
    """
    value = round(value, 4)
    return int(value) if value == int(value) else value


def _cid(*parts):
    """A composite record id: the compact JSON array, as a string."""
    return json.dumps(list(parts), ensure_ascii=False, separators=(",", ":"))


def _oid(*parts):
    """A deterministic 16-hex object id for a drawn primitive.

    ⚠️ Deterministic on purpose.  A random id would make two runs of the
    generator differ, which destroys the only cheap check we have that a
    regenerated board is the same board.
    """
    key = ":".join(str(p) for p in parts).encode("utf-8")
    return hashlib.sha1(key).hexdigest()[:16]


def dim_colour(colour):
    """The inactive (dimmed) form of a layer colour: each channel halved.

    Verified against a real saved file: this rule reproduces 59 of its 60
    inactive colours exactly.  The 60th is the editor's own malformed value
    `#a.492f` -- it renders a half-channel as `a.` instead of `0a` -- which we
    deliberately do not reproduce, because we do not ship that colour.
    """
    s = colour.lstrip("#")
    if len(s) != 6 or any(c not in "0123456789abcdefABCDEF" for c in s):
        raise ValueError(f"not a 6-digit hex colour: {colour!r}")
    return "#" + "".join(format(int(s[i:i + 2], 16) // 2, "02x")
                         for i in (0, 2, 4))


# --- the logical layer table ------------------------------------------------
# (layerId, layerType, layerName, use, show, locked, activeColour)
#
# The colours are the industry-standard per-function colours every EDA tool
# uses -- top copper red, bottom copper blue, outline magenta -- so that a
# generated board looks like a board to whoever opens it.  Each is here because
# of what the layer MEANS, not because it was copied from somewhere.
_FIXED_LAYERS = (
    (1,  "TOP",               "Top Layer",              True,  True,  False, "#ff0000"),
    (2,  "BOTTOM",            "Bottom Layer",           True,  True,  False, "#0000ff"),
    (3,  "TOP_SILK",          "Top Silkscreen Layer",   True,  True,  False, "#ffcc00"),
    (4,  "BOT_SILK",          "Bottom Silkscreen Layer", True, True,  False, "#66cc33"),
    (5,  "TOP_SOLDER_MASK",   "Top Solder Mask Layer",  True,  True,  False, "#800080"),
    (6,  "BOT_SOLDER_MASK",   "Bottom Solder Mask Layer", True, True, False, "#aa00ff"),
    (7,  "TOP_PASTE_MASK",    "Top Paste Mask Layer",   True,  True,  False, "#808080"),
    (8,  "BOT_PASTE_MASK",    "Bottom Paste Mask Layer", True, True, False, "#800000"),
    (9,  "TOP_ASSEMBLY",      "Top Assembly Layer",     True,  True,  False, "#33cc99"),
    (10, "BOT_ASSEMBLY",      "Bottom Assembly Layer",  True,  True,  False, "#5555ff"),
    (11, "OUTLINE",           "Board Outline Layer",    True,  True,  False, "#ff00ff"),
    (12, "MULTI",             "Multi-Layer",            True,  True,  False, "#c0c0c0"),
    (13, "DOCUMENT",          "Document Layer",         True,  True,  False, "#ffffff"),
    (14, "MECHANICAL",        "Mechanical Layer",       True,  True,  False, "#f022f0"),
)

_SPECIAL_LAYERS = (
    (47, "HOLE",              "Hole Layer",             True,  True,  False, "#222222"),
    (48, "COMPONENT_SHAPE",   "Component Shape Layer",  True,  False, False, "#00cccc"),
    (49, "COMPONENT_MARKING", "Component Marking Layer", True, False, False, "#66ffcc"),
    (50, "PIN_SOLDERING",     "Pin Soldering Layer",    True,  False, False, "#cc9999"),
    (51, "PIN_FLOATING",      "Pin Floating Layer",     True,  False, False, "#ff99ff"),
    (52, "COMPONENT_MODEL",   "Component Model Layer",  False, False, False, "#ffffff"),
    (53, "3D_SHELL_OUTLINE",  "3D Shell Outline Layer", True,  True,  False, "#66ff99"),
    (54, "3D_SHELL_TOP",      "3D Top Layer",           True,  True,  False, "#ffccff"),
    (55, "3D_SHELL_BOTTOM",   "3D Bottom Layer",        True,  True,  False, "#0066cc"),
    (56, "DRILL_DRAWING",     "Drill Drawing Layer",    True,  True,  False, "#008080"),
    # The ratline layer is locked so a stray drag cannot move a ratline.
    (57, "OTHER",             "Ratline Layer",          True,  True,  True,  "#6464ff"),
    (58, "TOP_STIFFENER",     "Top Stiffener Layer",    False, False, False, "#eee666"),
    (59, "BOTTOM_STIFFENER",  "Bottom Stiffener Layer", False, False, False, "#ccff00"),
)

#: Transparency of an active layer.  The two solder-mask layers are drawn
#: partly transparent so copper under them stays readable; everything else is
#: opaque.  Inactive layers are always opaque -- they are already dimmed.
_MASK_TRANSPARENCY = 0.7


def _hsv_hex(h, s, v):
    """HSV (h in turns) -> #rrggbb, so a palette can be generated rather than
    tabulated.  Only used for the 32 inner signal layers."""
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r, g, b = ((v, t, p), (q, v, p), (p, v, t),
               (p, q, v), (t, p, v), (v, p, q))[i]
    return "#" + "".join(format(int(round(c * 255)), "02x") for c in (r, g, b))


def inner_layer_specs():
    """The 32 SIGNAL inner layers; the stackup turns on the ones it uses.

    Their colours carry no meaning, so rather than tabulate 32 arbitrary
    values they are 32 evenly spaced hues: if a reader ever turns inner layers
    on, adjacent layers are guaranteed to be visually distinct.
    """
    out = []
    for i in range(INNER_LAYER_COUNT):
        layer_id = FIRST_INNER_LAYER + i
        colour = _hsv_hex(i / INNER_LAYER_COUNT, 0.6, 0.9)
        out.append((layer_id, "SIGNAL", f"Inner{i + 1}",
                    False, False, False, colour))
    return out


def layer_specs(inner_used=(), dielectrics=(SUBSTRATE_LAYER,)):
    """Every logical layer, in the order the table is written.

    `inner_used` names inner layer ids that are in the stackup; they get
    `use`/`show` true.  `dielectrics` are the stack's SUBSTRATE layer ids,
    361 upwards, one per dielectric -- a 4-layer board has three.  As in the
    editor's own files, a SUBSTRATE layer is never `use`: it is a film, not a
    layer anything is drawn on.
    """
    specs = list(_FIXED_LAYERS)
    for spec in inner_layer_specs():
        if spec[0] in inner_used:
            spec = spec[:3] + (True, True) + spec[5:]
        specs.append(spec)
    specs.extend(_SPECIAL_LAYERS)
    specs.extend((lid, "SUBSTRATE", f"Dielectric{lid - SUBSTRATE_LAYER + 1}",
                  False, False, False, "#000000") for lid in dielectrics)
    return specs


# --- the physical stackup ---------------------------------------------------
class Stackup:
    """The copper and dielectric stack, stated in millimetres, top to bottom.

    Every board is 4-layer (owner, 2026-09-18).  The default is JLC's standard
    4-layer 1.6 mm build, JLC04161H-7628 (jlcpcb.com/impedance): 1 oz outer
    copper, 7628 prepreg, 0.5 oz inner copper, a 1.065 mm core -- the stack JLC
    builds at no surcharge, 1.586 mm thick, inside the 1.6 mm that
    `board_params.PCB_T` books.  Prepreg is `PP` and the core `FR4`, the
    material names the editor writes.

    `copper_mm` lists every copper layer top to bottom; `dielectrics` lists
    the (material, mm, permittivity) between each pair.  Inner coppers take
    layer ids 15 upwards and dielectrics 361 upwards.

    `zIndex` orders the stack: 1,2,3 are the top non-copper films, 1000 the
    top copper, 1001 upwards the dielectrics and inner coppers in order, 9000
    the bottom copper, 10000+ the bottom non-copper films.
    """

    def __init__(self, copper_mm=(0.035, 0.0152, 0.0152, 0.035),
                 dielectrics=(("PP", 0.2104, 4.4), ("FR4", 1.065, 4.6),
                              ("PP", 0.2104, 4.4)),
                 mask_mm=0.01, loss_tangent=0.0, mask_permittivity=3.3,
                 mask_loss_tangent=0.02):
        if len(copper_mm) < 2 or len(dielectrics) != len(copper_mm) - 1:
            raise ValueError(f"{len(copper_mm)} copper layers need "
                             f"{len(copper_mm) - 1} dielectric(s) between them, "
                             f"not {len(dielectrics)}")
        self.copper_mm = tuple(copper_mm)
        self.dielectrics = tuple(dielectrics)
        self.mask_mm = mask_mm                # solder mask film
        self.loss_tangent = loss_tangent
        self.mask_permittivity = mask_permittivity
        self.mask_loss_tangent = mask_loss_tangent

    @property
    def board_thickness_mm(self):
        """Copper + dielectric only: what a fab means by "1.6 mm board"."""
        return sum(self.copper_mm) + sum(mm for _, mm, _ in self.dielectrics)

    def inner_layer_ids(self):
        return tuple(FIRST_INNER_LAYER + i for i in range(len(self.copper_mm) - 2))

    def dielectric_ids(self):
        return tuple(SUBSTRATE_LAYER + i for i in range(len(self.dielectrics)))

    def entries(self):
        """(layerId, body) pairs in stack order, top of board downwards."""
        mask = _u(self.mask_mm)

        def film(thickness, material=None, eps=None, tan=None, z=0):
            return {"material": material, "thickness": thickness,
                    "permittivity": eps, "lossTangent": tan,
                    "isKeepIsland": True, "zIndex": z}

        coppers = (TOP_COPPER,) + self.inner_layer_ids() + (BOTTOM_COPPER,)
        stack, z = [], 1000
        for i, (lid, mm) in enumerate(zip(coppers, self.copper_mm)):
            stack.append((lid, film(_u(mm), z=9000 if lid == BOTTOM_COPPER else z)))
            z += 1
            if i < len(self.dielectrics):
                material, d_mm, eps = self.dielectrics[i]
                stack.append((SUBSTRATE_LAYER + i,
                              film(_u(d_mm), material, eps, self.loss_tangent, z=z)))
                z += 1
        return [
            # Silk and paste are screen/stencil layers with no thickness.
            (TOP_SILK,   film(0, z=1)),
            (TOP_PASTE,  film(0, z=2)),
            (TOP_MASK,   film(mask, "", self.mask_permittivity,
                              self.mask_loss_tangent, z=3)),
            *stack,
            (BOT_MASK,   film(mask, "", self.mask_permittivity,
                              self.mask_loss_tangent, z=10000)),
            (BOT_PASTE,  film(0, z=10001)),
            (BOT_SILK,   film(0, z=10002)),
        ]


# --- design rules -----------------------------------------------------------
#: The `safeSpacing` matrix is 13x13 lower-triangular: row i has i+1 entries.
#: ⚠️ Nothing documents WHICH object class each row is, and the file's own
#: `columnNames` is empty.  Filling every cell with the same number is
#: therefore the only way to state a board-wide clearance that cannot be wrong.
SAFE_SPACING_CLASSES = 13

#: Sentinel meaning "suppress this layer for this object entirely".  It is not
#: a length, so it is never converted from mm.
_SUPPRESS = -1000


class DesignRules:
    """The board's rule set, every number stated in millimetres.

    Defaults are the fab's published TWO-layer capability, kept on the
    4-layer boards because they are coarser than its multilayer minimums:
    every number passes either.  They are a design decision, not format
    boilerplate, and changing one here changes it everywhere it is written.
    The template label names the multilayer template the editor offers.
    """

    def __init__(self, clearance_mm=0.2, hole_clearance_mm=0.3,
                 track_min_mm=0.127, track_def_mm=0.254, track_max_mm=2.54,
                 track_min_2oz_mm=0.203,
                 via_pad_mm=0.61, via_hole_mm=0.305,
                 via_pad_min_mm=0.5, via_pad_max_mm=10.0,
                 via_hole_min_mm=0.3, via_hole_max_mm=6.3,
                 diff_pair_space_mm=0.1524, diff_pair_tolerance_mm=10.0,
                 net_length_tolerance_mm=25.4,
                 thermal_spoke_mm=0.254, solder_mask_expansion_mm=0.0508,
                 template_name="JLCPCB Capability(Multiple Layers Board)"):
        self.clearance_mm = clearance_mm
        self.hole_clearance_mm = hole_clearance_mm
        self.track_min_mm = track_min_mm
        self.track_def_mm = track_def_mm
        self.track_max_mm = track_max_mm
        self.track_min_2oz_mm = track_min_2oz_mm
        # The RADIUS rule is written in RADII: defRadius*2 is the via pad
        # diameter and defInner*2 the drill diameter.  Stating diameters here
        # and halving on the way out keeps the callers honest.
        self.via_pad_mm = via_pad_mm
        self.via_hole_mm = via_hole_mm
        self.via_pad_min_mm = via_pad_min_mm
        self.via_pad_max_mm = via_pad_max_mm
        self.via_hole_min_mm = via_hole_min_mm
        self.via_hole_max_mm = via_hole_max_mm
        self.diff_pair_space_mm = diff_pair_space_mm
        self.diff_pair_tolerance_mm = diff_pair_tolerance_mm
        self.net_length_tolerance_mm = net_length_tolerance_mm
        self.thermal_spoke_mm = thermal_spoke_mm
        self.solder_mask_expansion_mm = solder_mask_expansion_mm
        self.template_name = template_name

    # -- the one rule this module exists to get right ------------------------
    def safe_spacing(self):
        """A uniform board-wide clearance, as the lower-triangular matrix."""
        c = _u(self.clearance_mm)
        return [{"layerId": TOP_COPPER, "isOpen": True,
                 "content": [[c] * (i + 1) for i in range(SAFE_SPACING_CLASSES)],
                 "columnNames": []}]

    def _track(self, min_mm):
        return {"isOpen": True,
                "content": [{"layerId": TOP_COPPER, "stroMin": _u(min_mm),
                             "stroDef": _u(self.track_def_mm),
                             "stroMax": _u(self.track_max_mm)}]}

    @property
    def via_pad_units(self):
        """Via pad diameter as twice the radius the RADIUS rule states.

        Derived rather than converted so the default via the editor offers can
        never be a hair outside the rule that governs it.
        """
        return round(2 * _u(self.via_pad_mm / 2), 4)

    @property
    def via_hole_units(self):
        return round(2 * _u(self.via_hole_mm / 2), 4)

    def _thermal(self):
        spoke = _u(self.thermal_spoke_mm)
        return {"isOpen": True,
                "content": [{"layerId": TOP_COPPER, "connType": "DIVERGENCE",
                             "spoSpac": spoke, "spoWidth": spoke,
                             "spoAng": 90}]}

    def entries(self):
        """(class, name, ruleState, ruleContext) in rule-manager order."""
        safe = self.safe_spacing()
        mask = _u(self.solder_mask_expansion_mm)
        return [
            # isForAll "ALL" makes the single matrix apply to every layer.
            ("SAFE", "copperThickness1oz", "DEFAULT",
             {"unit": "mm", "isForAll": "ALL", "safeSpacing": safe}),
            ("SAFE", "copperThickness2oz", "NORMAL",
             {"unit": "mm", "isForAll": "ALL", "safeSpacing": self.safe_spacing()}),
            ("OTHER", "otherClearance", "DEFAULT",
             {"unit": "mm", "deviceClearance": 0, "thru2SmdClearance": 0,
              "holeClearance": _u(self.hole_clearance_mm)}),
            ("CREEPAGE", "creepage", "DEFAULT",
             {"unit": "mm", "creepageDistance": 0, "ignoreLayer": True}),
            ("TRACK", "copperThickness1oz", "DEFAULT",
             {"unit": "mm", "track": self._track(self.track_min_mm)}),
            ("TRACK", "copperThickness2oz", "NORMAL",
             {"unit": "mm", "track": self._track(self.track_min_2oz_mm)}),
            ("NET_LENGTH", "netLength", "DEFAULT",
             {"unit": "mm", "netLenMin": 0, "netLenMax": 0}),
            ("NET_LENGTH_TOLERANCE", "netLengthTolerance", "DEFAULT",
             {"unit": "mm",
              "netLengthTolerance": _u(self.net_length_tolerance_mm)}),
            ("DIFFER_ENTAIL", "differentialPair", "DEFAULT",
             {"unit": "mm",
              "stroWidth": {"isOpen": True,
                            "content": [{"layerId": TOP_COPPER,
                                         "stroMin": _u(self.track_min_mm),
                                         "stroMax": _u(self.track_max_mm),
                                         "stroDef": _u(self.track_def_mm)}]},
              "spacing": {"isOpen": True,
                          "content": [{"layerId": TOP_COPPER,
                                       "spacMin": _u(self.diff_pair_space_mm),
                                       "spacDef": _u(self.diff_pair_space_mm)}]},
              # ⚠️ This one really is in the unit named beside it, unlike every
              # other number in a ruleContext.
              "differPairLenTolerMax": _num(self.diff_pair_tolerance_mm),
              "toleranceUnit": "mm"}),
            # Through vias only: no blind or buried vias are used.
            ("BLIND", "blindVia", "DEFAULT", {"blinds": {"content": []}}),
            ("RADIUS", "viaSize", "DEFAULT",
             {"unit": "mm",
              "minRadius": _u(self.via_pad_min_mm / 2),
              "defRadius": _u(self.via_pad_mm / 2),
              "maxRadius": _u(self.via_pad_max_mm / 2),
              "minInner": _u(self.via_hole_min_mm / 2),
              "defInner": _u(self.via_hole_mm / 2),
              "maxInner": _u(self.via_hole_max_mm / 2)}),
            ("PLANE", "innerPlane", "DEFAULT",
             {"unit": "mm", "mulPad": self._thermal()}),
            ("COPPER", "copperRegion", "DEFAULT",
             {"unit": "mm", "sglPad": self._thermal(),
              "mulPad": self._thermal(),
              "track": {"isOpen": True,
                        "content": [{"layerId": TOP_COPPER,
                                     "connType": "DIRECT"}]}}),
            ("PASTE", "pasteMaskExpansion", "DEFAULT",
             {"unit": "mm", "padTopExpan": 0, "padBotExpan": 0,
              "testPointTopExpan": _SUPPRESS, "testPointBotExpan": _SUPPRESS}),
            ("SOLDER", "solderMaskExpansion", "DEFAULT",
             {"unit": "mm", "padTopExpan": mask, "padBotExpan": mask,
              "viaTopExpan": _SUPPRESS, "viaBotExpan": _SUPPRESS,
              "testPointTopExpan": mask, "testPointBotExpan": mask}),
            ("AUTO_ROUTER", "Common", "DEFAULT",
             {"routingCorner": "L45", "isKeep": 1, "viaQuantity": "LESS",
              "routingEffectPriority": "COMPLETION_FIRST",
              "layers": [TOP_COPPER, BOTTOM_COPPER, MULTI_LAYER],
              "ignoreNets": []}),
        ]


# --- display configuration --------------------------------------------------
# Object classes the editor can show or hide.  Names are the format's own
# enumeration, misspellings included (`FILLREGIEN`): they are keys, not prose,
# and correcting one would silently drop the setting.  `null` is the catch-all
# class.  Everything is displayed; the classes that are containers rather than
# drawn objects are not individually pickable.
_UNPICKABLE = frozenset({"ALL", "PADSPAIR", "NETWORK", None, "GROUP"})

_OBJECT_CLASSES = (
    "ALL", "COMPONENT", "PROPERTY", "TRACK", "FPC_STIFFENER", "TESTPOINT",
    "PAD", "VIA", "SUTUREHOLE", "TEXT", "IMAGE", "PICTURE", "DIMENSION",
    "BOARDOUTLINE", "SLOTREGION", "COPPEROUTLINE", "COPPERFILLED",
    "FILLREGIEN", "PROHIBITEDREGION", "LINE", "CONSTRAINT", "PADSPAIR",
    "NETWORK", "TEARDROP", None, "GROUP", "LOCKED", "UNLOCKED", "SHELL",
    "BOSS", "CREASE", "SIDESHELLCUT", "TOPSHELLCUT", "TOPBOTTOMENTITY",
    "SIDEENTITY", "D3BODY",
)

#: Editor chrome colours, written as `["PRIMITIVE", <what>]` records.
_CHROME = (
    ("CURSOR", "#00ffff"),
    ("BACKGROUND", "#000000"),
    ("GRID", "#ffffff"),
    ("BOLDGRID", "#ffffff"),
    ("COORDINATEAXIS", "#ffffff"),
    ("SELECTBOX", "#00ffff"),
)

#: Overlay colours, written as `["PRIMITIVE", <what>, <layerId>]`; layer 0
#: means "on every layer".
_OVERLAYS = (
    ("DRC", "#FFCC00"),
    ("PROHIBITEDREGION", "#9966FF"),
    ("BOARDSHAPE", "#6D6A69"),
    ("PARTITION", "#C0C0C0"),
)

#: Layers whose contents are hidden by default: the component shape/marking
#: and pin layers exist for 3D and assembly output, not for layout.
_HIDDEN_BY_DEFAULT_LAYERS = (48, 49, 50, 51)


class Pcb:
    """One `.epcb2` document: a rectangular board with mounting holes.

    The envelope defaults to `board_params.BOARD_W` x `board_params.BOARD_L`
    so that a board generated here is, by construction, the board the fit
    budget proved.  Pass `width_mm`/`length_mm` only to make a board that is
    deliberately not the standard card.
    """

    def __init__(self, title, uuid, board_uuid, client,
                 epoch_ms, *, width_mm=None, length_mm=None,
                 hole_diameter_mm=M3_CLEARANCE_MM, hole_inset_mm=M3_INSET_MM,
                 stackup=None, rules=None, edit_version=EDIT_VERSION):
        self.title = title
        self.uuid = uuid
        self.board_uuid = board_uuid
        self.client = client
        self.epoch_ms = epoch_ms
        self.width_mm = BOARD_W if width_mm is None else width_mm
        self.length_mm = BOARD_L if length_mm is None else length_mm
        self.hole_diameter_mm = hole_diameter_mm
        self.hole_inset_mm = hole_inset_mm
        self.stackup = stackup or Stackup()
        self.rules = rules or DesignRules()
        self.edit_version = edit_version

        if self.hole_inset_mm < self.hole_diameter_mm / 2:
            raise ValueError(
                f"hole inset {self.hole_inset_mm} mm is inside the board edge "
                f"for a {self.hole_diameter_mm} mm hole")
        if 2 * self.hole_inset_mm >= min(self.width_mm, self.length_mm):
            raise ValueError(
                f"hole inset {self.hole_inset_mm} mm does not fit a "
                f"{self.width_mm} x {self.length_mm} mm board")

    # -- geometry ------------------------------------------------------------
    @property
    def width_units(self):
        return _u(self.width_mm)

    @property
    def length_units(self):
        return _u(self.length_mm)

    def outline_path(self):
        """`["R", x, y, width, height, rot, isCCW]`.

        (x, y) is the TOP-LEFT corner, so with the board's bottom-left corner
        on the origin the y passed in is the board's full height.
        """
        return ["R", 0, self.length_units,
                self.width_units, self.length_units, 0, 0]

    def hole_centres(self):
        """The four mounting-hole centres, in file units.

        ⚠️ Computed by subtracting in UNITS, not in mm: the inset must be
        exact against the board edge that is actually written to the file,
        which is the rounded value, not the unrounded ideal.
        """
        inset = _u(self.hole_inset_mm)
        far_x = round(self.width_units - inset, 4)
        far_y = round(self.length_units - inset, 4)
        return [(inset, inset), (far_x, inset),
                (inset, far_y), (far_x, far_y)]

    # -- records -------------------------------------------------------------
    def _mounting_hole(self, centre_x, centre_y, oid):
        """A non-plated hole: a pad whose copper is exactly the drill, so no
        annular ring survives and the fab sees bare FR4 around the barrel."""
        d = _u(self.hole_diameter_mm)
        return "PAD", oid, {
            "partitionId": "", "groupId": 0, "netName": "",
            "layerId": MULTI_LAYER, "num": "",
            "centerX": centre_x, "centerY": centre_y, "padAngle": 0,
            "hole": {"holeType": "ROUND", "width": d, "height": d,
                     "cornerRadius": 0},
            "defaultPad": {"padType": "ELLIPSE", "width": d, "height": d},
            "specialPad": [], "padOffsetX": 0, "padOffsetY": 0,
            "relativeAngle": 0, "plated": False, "padType": "NORMAL",
            "topSolderExpansion": None, "bottomSolderExpansion": None,
            "topPasteExpansion": None, "bottomPasteExpansion": None,
            "locked": False, "zIndex": -1, "connectMode": None,
            "spokeSpace": None, "spokeWidth": None, "spokeAngle": None,
            "unusedInnerLayers": [], "padLen": 0, "propagationDelay": 0,
            "attrsMap": {},
        }

    def _bodies(self):
        """(type, id, body) for every record after DOCHEAD, in file order.

        Order follows a real saved file: configuration first, geometry last.
        Nothing proves the order matters beyond DOCHEAD coming first; matching
        what the editor writes is the cheapest way never to find out.
        """
        out = []
        out.append(("META", "META",
                    {"title": self.title, "parent": "", "source": "",
                     "board": self.board_uuid, "zIndex": None}))

        for cls in _OBJECT_CLASSES:
            out.append(("PRIMITIVE", _cid("PRIMITIVE", cls),
                        {"display": True, "pick": cls not in _UNPICKABLE}))

        out.append(("CANVAS", "CANVAS", {
            # originX/originY shift only the displayed coordinate readout;
            # "unit" is the display unit and does not change the file's units.
            "originX": 0, "originY": 0, "unit": "mil",
            "gridXSize": 5, "gridYSize": 5, "snapXSize": 5, "snapYSize": 5,
            "altSnapXSize": 1, "altSnapYSize": 1,
            "gridType": "GRID", "multiGridType": "NONE", "multiGridRatio": 5,
            "highlightValue": 0.5, "layerBrightness": "NORMAL"}))

        for (lid, ltype, lname, use, show, locked, colour) in layer_specs(
                inner_used=self.stackup.inner_layer_ids(),
                dielectrics=self.stackup.dielectric_ids()):
            out.append(("LAYER", _cid("LAYER", lid), {
                "layerId": lid, "layerType": ltype, "layerName": lname,
                "use": use, "show": show, "locked": locked,
                "activeColor": colour,
                "activateTransparency": (_MASK_TRANSPARENCY
                                         if lid in (TOP_MASK, BOT_MASK) else 1),
                "inactiveColor": dim_colour(colour),
                "inactiveTransparency": 1}))

        for lid, body in self.stackup.entries():
            out.append(("LAYER_PHYS", _cid("LAYER_PHYS", lid), body))

        out.append(("ACTIVE_LAYER", "ACTIVE_LAYER", {"layerId": TOP_COPPER}))

        out.append(("RULE_TEMPLATE", "RULE_TEMPLATE",
                    {"name": self.rules.template_name}))
        for cls, name, state, context in self.rules.entries():
            out.append(("RULE", _cid("RULE", cls, name),
                        {"ruleState": state, "ruleContext": context}))

        out.append(("PRIMITIVE", _cid("PRIMITIVE", "COMPONENTSILK"),
                    {"display": True, "pick": True}))
        # Ratlines and plane/partition shading are off until there is a netlist
        # to draw them from.
        out.append(("PRIMITIVE", _cid("PRIMITIVE", "RATLINE"),
                    {"display": False, "pick": False}))
        out.append(("PRIMITIVE", _cid("PRIMITIVE", "PLANE"),
                    {"display": False, "pick": False, "transparency": 0.35}))
        out.append(("PRIMITIVE", _cid("PRIMITIVE", "PARTITION"),
                    {"display": False, "pick": False, "transparency": 1}))

        for silk_layer in (TOP_SILK, BOT_SILK):
            out.append(("SILK_OPTS", _cid("SILK_OPTS", silk_layer),
                        {"defaultColor": "#000000", "baseColor": "#FFFFFF"}))

        out.append(("D3_ATTRIBUTE", "D3_ATTRIBUTE", {
            # 3D preview only; none of this reaches a fab.
            "materials": "substrate_yellow", "silkTechnology": "standardSilk",
            "backgroundColor": "#000000", "boardColor": "blue",
            "sprayColor": "gold", "layerExpose": 0, "substrateHeight": 0}))

        out.append(("PREFERENCE", "PREFERENCE", {
            "startTrackWidthFollowLast": False,
            "lastTrackWidth": _u(self.rules.track_def_mm),
            "startViaSizeFollowLast": False,
            "lastViaInnerDiameter": self.rules.via_hole_units,
            "lastViaDiameter": self.rules.via_pad_units,
            "snap": True, "routingMode": "SURROUND", "routingCorner": "L45",
            "removeLoop": True, "rotatingObject": False, "trackFollow": False,
            "stretchTrackMinCorner": 1,
            "realTimeUpdateUnusedLayers": False, "unusedPadRange": "VIA",
            "pushVia": "OPTIMIZA_OPEN", "pathOptimization4BePushed": "SINGLE",
            "currentPathOptimization4BePushed": "OPTIMIZA_WEAK",
            "removeCircuitsContainingVias": True, "removeAntenna": True}))

        out.append(("PANELIZE", "PANELIZE", self._panelize()))

        # Drill shading in the 3D view.
        for cls in ("PADMETALLICDRILLING", "PADNONMETALLICDRILLING"):
            out.append(("PRIMITIVE", _cid("PRIMITIVE", cls),
                        {"display": False, "pick": False, "transparency": 0}))

        out.append(("PRIMITIVE", _cid("PRIMITIVE", "ALL", 0),
                    {"display": True, "color": None}))
        for cls, colour in _OVERLAYS:
            out.append(("PRIMITIVE", _cid("PRIMITIVE", cls, 0),
                        {"color": colour}))
        for lid in _HIDDEN_BY_DEFAULT_LAYERS:
            out.append(("PRIMITIVE", _cid("PRIMITIVE", "ALL", lid),
                        {"display": False, "color": None}))
        for cls, colour in _CHROME:
            out.append(("PRIMITIVE", _cid("PRIMITIVE", cls),
                        {"display": True, "color": colour}))

        # -- geometry --------------------------------------------------------
        out.append(("POLY", _oid(self.uuid, "outline"), {
            "partitionId": "", "groupId": 0, "netName": "",
            "layerId": OUTLINE_LAYER, "width": _u(OUTLINE_STROKE_MM),
            "path": self.outline_path(), "locked": False, "zIndex": -1,
            "polyType": "BOARD_OUTLINE"}))

        for i, (x, y) in enumerate(self.hole_centres()):
            out.append(self._mounting_hole(x, y, _oid(self.uuid, "hole", i)))

        return out

    def _panelize(self):
        """Panelization, switched off.  The sub-objects are the editor's inert
        template defaults; with `on` false none of them has any effect."""
        def stamp():
            return {"on": False, "stampHoleGroupQuantity": 1,
                    "stampHoleDiameter": _u(0.55),
                    "stampHoleQuantityPerGroup": 8,
                    "stampHoleSpacing": _u(0.85), "center_percent": None}

        def rail(direction, on):
            return {"direction": direction, "on": on,
                    "sideHeight": _u(6.0), "positionHoleDiameter": _u(2.0),
                    "markDiameter": _u(1.0), "markExpansion": _u(0.5),
                    "borderRadius": _u(1.0)}

        return {"on": False, "row": 1, "column": 1,
                "rowSpacing": 0, "columnSpacing": 0, "onlyOutline": True,
                "horizontalStamp": stamp(), "verticalStamp": stamp(),
                "horizontalSize": rail(0, False), "verticalSize": rail(1, True),
                "mirrorBoard": False, "mirrorEvenRow": False,
                "mirrorEvenCol": False, "evenRowRotation": 0,
                "evenColRotation": 0, "showVCutIndicator": True,
                "vCutLayer": DOCUMENT_LAYER, "markPosition": None,
                "positionHolePosition": None, "panelizeVersion": "1.1"}

    def records(self):
        """Every record of the document, already serialised.

        Tickets run 1..N in file order.  They are proven to need to be unique
        within a document and nothing else; sequential is the cheapest way to
        guarantee that.  DOCHEAD carries none.
        """
        head = serialize_record(
            {"type": "DOCHEAD"},
            payload={"docType": "PCB", "client": self.client,
                     "uuid": self.uuid, "updateTime": self.epoch_ms,
                     "version": str(self.epoch_ms),
                     "editVersion": self.edit_version, "user": {}})
        out = [head]
        for ticket, (type_, id_, body) in enumerate(self._bodies(), start=1):
            out.append(serialize_record(
                {"type": type_, "ticket": ticket, "id": id_}, payload=body))
        return out

    def document(self):
        """The file's exact text: records joined by `"|" + LF`, no trailing
        `|` and no trailing newline."""
        return join_records(self.records())
