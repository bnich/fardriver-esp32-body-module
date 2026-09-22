# Where the EasyEDA project lives

**One place, one file: `~/Documents/EasyEDA-Pro/projects/revv1-module.eprj2`** (owner, 2026-09-22:
*"all easyeda files should be in ~/Documents/EasyEDA-Pro/projects"*). Open it there; save it there.
Nothing else on this machine is an `.eprj2` of this design.

**What the build does with it.** `python3 tools/build_project.py` (and `tools/gate.sh`) writes the
generated folder, zip and `layout-rules.txt` under `build-eprj3/`, and writes the **`.eprj2` into the
editor's folder** — ⚠️ **unless the file already there has been SAVED by the editor**, in which case it
is the owner's layout and the build **refuses to overwrite it**, exits `INCOMPLETE`, and says so. A
generated project carries the build's fixed timestamp on every document; a saved one carries the
editor's real one — that is how the two are told apart (`build_project._is_generated`).

**So the workflow is:**

| Situation | What to do |
|---|---|
| No layout yet (today) | run the build; open the `.eprj2` it writes; Import Changes on each of the **four** PCBs; **flip the six bottom parts**; save |
| Layout exists, netlist unchanged | just open the file; the build will not touch it |
| Layout exists, netlist changed | fix `netlist.py`; run the gate (it writes a fresh **`build-eprj3/`** folder and refuses the `.eprj2`); open your layout; re-import only the changed board's **schematic sheet** from `build-eprj3/revv1-module/sch/<BOARD>/`; Import Changes on that PCB — placement survives, changed parts land unplaced; export and `tel_check`. ⚠️ A repartition touches **every** board it moved a part off or onto: do all four when in doubt |
| You want a clean regenerated project anyway | move or rename your layout first; then build |

⛔ Never run the build or the gate while EasyEDA is open — the gate refuses, and it is right to.

**The six parts that must be on the bottom layer** — the generated project carries no layer, so
Import Changes puts everything on top: POWER `U201`, `U202` · OUTPUTS `J311` · LOGIC `J406`, `J407`
· CTRL `J501`. `J406`, `J407` and `J501` are the upper halves of mated pairs and their footprints
are pre-mirrored for this; `J311`, the loom's OUTPUTS-side header, deliberately is not — a cable
has no mate to line up with. `J314` is **not** in this list any more: since IO-26 2a it stands on
CTRL's top face.

**This directory** holds only this README. The `.eprj2` is not in the repo: it is a binary the editor
rewrites on every save, it lives where the editor looks for it, and the design it encodes is
`tools/netlist.py` plus the owner's placement — the netlist is versioned here, the placement in the
editor's own history.
