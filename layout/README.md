# `layout/` — the owner's PCB layout, saved from EasyEDA Pro

**This is where the laid-out project lives.** `build-eprj3/` is a build artefact: the generator
overwrites it, `tools/gate.sh` renames it `.stale`, and `.gitignore` excludes it. A layout saved there
is one build away from being lost. Save here instead.

**How:** `layout/revv1-module.eprj2` is seeded as a byte-identical copy of the generated project at
the netlist commit named below. **Open THIS file** in EasyEDA Pro, do the Import Changes here, place
and route here, save here. Never open `build-eprj3/revv1-module.eprj2` for layout — it is the
build's, and the build will replace it.

| Seeded from | Netlist commit | Date |
|---|---|---|
| `build-eprj3/revv1-module.eprj2`, fresh build | `d48f148` | 2026-09-22 |

**The rule:** `build-eprj3/` is generated FROM the netlist and holds an EMPTY PCB (outline, holes,
rules). `layout/` holds the netlist PLUS placement and routing. When the netlist changes, the fix is
**not** to rebuild and re-import from scratch — that discards the layout. It is:

1. Fix `tools/netlist.py`; run `tools/gate.sh` (the editor must be closed).
2. Open `layout/revv1-module.eprj2`, and in the schematic re-import the changed board's sheet from
   the fresh `build-eprj3/` — or, for a small change, edit the schematic to match the netlist.
3. *Import Changes* on the PCB; placement survives, the changed parts land unplaced.
4. Export each board's netlist; `python3 -m tools.tel_check BOARD file.tel` → identical.

⛔ Never run `build_project.py` or `gate.sh` while EasyEDA is open — the gate refuses, and it is
right to.

**What is committed:** the `.eprj2` here (it is the design's placement — a real artefact of the
owner's work, unlike the generated one). ⚠️ It is a binary blob to git; commit it at meaningful
points (a board placed, a board routed), not every save.

**Seven parts must be on the bottom layer** — the generated project carries no layer, so Import
Changes puts everything on top: POWER `U201`, `U202` · OUTPUTS `J314`, `J311`, `J312` · LOGIC
`J406`, `J407`. `J406`/`J407` footprints are pre-mirrored; `J311`/`J312` are deliberately not.
