# Design-time tooling

Generates the EasyEDA Pro project for the four-board set from a checked-in
netlist.  **Stdlib only** — no dependencies, no virtualenv needed.

| | |
|---|---|
| `board-fit.py` | Area and height budget. Parametric on the cavity (M18) and part heights (M19) — edit the two PARAMETERS blocks and re-run |
| `eprj3/` | The `.eprj3` emitter. `records.py` is the encoding boundary; `units.py` is mm ↔ 0.01 inch |

## Running

```bash
python3 -m pytest tests/ -v     # the suite
python3 tools/board-fit.py      # area + height budget
```

## Rules

- ⛔ **Never hand-edit a generated project.** It is a build artefact. Change the
  netlist and regenerate, or the next build silently reverts your edit.
- ⛔ **Never store native units outside `units.py`.** Geometry is millimetres
  everywhere; conversion happens once, at emit.
- **Every constant states what it protects**, so it cannot be silently re-broken.

📄 The design this builds: [`../docs/board-design-record.md`](../docs/board-design-record.md)
