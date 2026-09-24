# PCB layout — the process

Placement, routing and the checks are done by **`pcb-layout-tools`** (`pcbl`, tag **v0.1.0**). The
procedure — every step, what it writes, what its exit codes mean, and why the order is what it is —
is that repository's **`docs/process.md`**. This file holds only what is particular to this board
set: where its constraints come from, and the order its copper is laid in.

## What this repository gives `pcbl`

| File | What it is |
|---|---|
| `layout.yaml` | **Generated**, never hand-edited: `python3 -m tools.layout_export PROJECT.eprj2 -o layout.yaml`. Every figure is read from where it already lives in this repository (`tools/layout_export.py` says where, block by block) |
| `tools/layout_hooks.py` | Goes beside `layout.yaml`. It answers the pack-voltage nets' operating points, which are code (`tools/soft_start.py`), not data |
| `tools/layout_facts.py` | The layout facts the two files above read: the board frame, the net classes and the rules that assign them, the decoupler hosts, the heavy path |

Write the yaml and link the hooks beside a **copy** of the project, and follow `docs/process.md`
from `pcbl prove` onwards. The owner's project is `~/Documents/EasyEDA-Pro/projects/revv1-module.eprj2`
(📄 `README.md` in this directory); ⛔ every `pcbl` write refuses while the editor is running.

`tools/gate.sh` exports `layout.yaml` from the owner's project and runs `pcbl stack` on it, and
refuses with a clear message when `pcbl` v0.1.0 is not installed. `pcbl check` is the layout's own
bar (`docs/process.md`), not the gate's.

## The order the copper goes down

Power first, because it needs the room; signals last, because they can go around anything.
`pcbl route copper` lays the class copper (1–4) where the placement leaves a run and refuses by name
where it does not; `pcbl route signals` lays the rest. What either refuses is drawn by hand and then
locked.

1. **The 84 V chain on POWER** (HV). `J101.B+ → FH201 → Q101 → HV_SW → L101`/`L102` →
   `C201`/`C202` → `U201`/`U202` `+Vin`, and the negative twin on `HV_C1_N` / `HV_C2_N`. 0.5 mm
   minimum, 1.25 mm from low-voltage copper and each pair's own voltage difference between two
   84 V nets (IO-29), on one layer.
2. **The 12 V bus on POWER** (PWR12). `U201.+V`/`+S` → `C207.+` → `J202.V12` and its ground twin,
   ≥ 5 mm. A trace, not a pour: the inner planes stop at the partition.
3. **The 12 V bus on OUTPUTS** (PWR12). The pour is the bus; `J311`'s power contacts onto it, each
   driver's `VS` down with two vias, `J311`'s GND contact to the layer-2 plane the same way.
4. **The channels** (CH12 / CH5) and **the 5 V aux supply** (PWR5AUX): driver `OUTx` → clamp diode
   → terminal, in that order, so a surge meets the clamp first. On CTRL, `V12` reaches the buck
   through `PWR-LOGIC` and `CTRL-STACK`, then `U305`'s input, `L301` and the output caps in a tight
   loop, then `V5AUX` to the four switches. `V5AUX_SW` is the noisiest net on CTRL and is in class
   PWR5AUX, whose rule allows a via. Keeping `U305.SW → C314 → L301` short, wide and on one layer
   is a placement matter — `L301` and `C314` beside `U305` — and ⚠️ **`layout.yaml` does not yet
   state it**: no reach holds either part to the buck, and the current placement leaves `L301.1`
   about 23 mm from `U305.SW`. Until a constraint does, check it by eye on `placement-CTRL.png`
   and `copper-CTRL.png`, and do not accept a long switch node.
5. **The face rows' returns**: every terminal's GND to the plane by its own via, beside the pad.
6. **The differential pair** (DIFF): `U404` → `J411` on LOGIC and on to `J501` on CTRL. Paired,
   same layer, one via each if a via is needed at all.
7. **Sense lines** (SENSE): from their dividers to the S3 or the `CS` pins, away from every CH12
   and PWR trace, on the layer opposite the pour.
8. **Everything else.**

## DRC on POWER

The editor's HV rule is 1.25 mm to everything, because its rules bind to a net and not to a pair.
`pcbl route exceptions --docs DIR` writes `POWER-drc-exceptions.md`: every join the editor will flag
and IO-29 accepts, with its gap, the volts between the two nets and the IPC-2221B B2 figure it
meets. `layout/POWER-drc-exceptions.md` is that file for the owner's project as last written by
`pcbl`; it is regenerated, never hand-edited, and replaced whenever the project's copper is.
⛔ **An editor DRC hit that is not on that list is a defect.**
