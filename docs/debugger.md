# GUI Debugger

Implementation of the local-web debugger recommended by
[gui_debug_visualization_research.md](gui_debug_visualization_research.md): the CLI stays the only
generation interface; the debugger is a read-mostly visualization layer over generated artifacts.

## Quickstart

```bash
pip install -e '.[debug]'            # pyarrow, duckdb, fastapi, uvicorn

magic-geo generate  --config configs/earthlike_seed.yaml --output runs/earthlike/world.json
magic-geo export-debug --world runs/earthlike/world.json      # → runs/earthlike/debug/
magic-geo serve -d runs/earthlike/debug                       # → http://127.0.0.1:8642
```

Optional companion viewers from the same artifacts:

```bash
magic-geo export-rerun --world runs/earthlike/world.json      # → world.rrd  (rerun world.rrd)
paraview runs/earthlike/debug/world.pvd                       # VCR stage-stepping in ParaView
```

## Pipeline

```text
world.json ── export-debug ──▶ debug/
                               ├─ manifest.json          field catalog, layer stats, stage index
                               ├─ tables/*.parquet       cells (wide), per-stage ledgers (long),
                               │                         flat record families, scalar sidecars
                               ├─ events/*.jsonl         nested provenance/event families
                               ├─ sections.json          dict sections (models, graphs, clock)
                               ├─ mesh/*.f32|*.u32       fan-triangulated GPU mesh: positions,
                               │                         per-vertex cell ids, indices, precomputed
                               │                         equirectangular + Mollweide 2D positions
                               └─ vtu/ + world.pvd       ParaView per-stage companion export

debug/ ── serve ──▶ FastAPI + DuckDB
                    ├─ /api/layer/{id}?stage=&month=&format=f32|arrow   one Float32 column per cell
                    ├─ /api/cell/{id}          full record + per-stage ledger slices + edges
                    ├─ /api/stage-summary/{h}  per-stage scalar table (sparklines)
                    ├─ /api/family/{name}      paged rows from any record family
                    ├─ /api/section/{name}     models/graphs/clock sections
                    └─ /  three.js frontend (debug_ui/), /mesh/* binary assets
```

The exporter classifies record families generically from payload shape (scalar list-of-dicts →
Parquet; `cell_ids` + `*_by_cell` parallel arrays → stage tables; nested records → JSONL with a
scalar-column Parquet sidecar; dicts → sections). New engine/enricher output is picked up without
touching the exporter, and skipped fields are recorded in the manifest instead of dropped silently.

## Frontend (system browser, no build step)

Full UI reference: [debug_ui_guide.md](debug_ui_guide.md). Pipeline review with known
issues: [layers_pipeline_review.md](layers_pipeline_review.md).

One merged indexed `BufferGeometry` (fan per cell around its site, per-vertex `cell_id`), per-cell
values in an R32F `DataTexture` fetched by cell id in the vertex shader, viridis/categorical
colormap in the fragment shader. Layer switch and stage scrub swap one `Float32Array` — no
geometry rebuild. Vendored three.js 0.185 (`debug_ui/vendor/`), loaded via import map.

- Layer panel: grouped by record family, search filter (`/`) that also matches layer docs and
  units, doc tooltips, numeric + categorical + monthly + per-stage layers (446 layers on the
  default earthlike run).
- Docs helper (`debug_ui/docs.js`): help overlay (`?`/`h`), per-layer doc card (`i` or legend ⓘ)
  with curated summaries, unit/subsystem inference from field-name conventions, and stats.
- Stage control: slider + exact-value field + step buttons (`,` / `.`), ±2-stage prefetch.
- Projections: globe / equirectangular / Mollweide with animated vertex-shader morph (`1`/`2`/`3`);
  every overlay follows the morph via a shared shader chunk.
- Picking: GPU id-buffer (cell id encoded to RGB, one-pixel readback); hover shows the value,
  click opens the inspector with all ~400 fields, per-stage ledger sparklines, monthly series,
  and adjacency edges (with plate-boundary / transition flags, click-through to neighbors).
- Overlays: mesh wireframe (`w`), plate boundaries (`b`), graticule (`g`).
- `window.__magicGeo` exposes `{ state, three }` in the console for debugging the debugger.

Cell polygons come from the approximate `boundary_ring`s; visible seams between rings are the
documented ring mismatch, useful as a mesh-quality debug signal (mismatch metrics ship as layers).

## Build/determinism notes (verified 2026-07-10)

- `CMakeLists.txt` now defaults `CMAKE_BUILD_TYPE` to Release (the shipped library had been built
  unoptimized) and pins `-ffp-contract=off` so FMA fusion cannot introduce backend drift.
- Run-to-run output at a fixed thread count is bit-stable (identical SHA-256).
- Optimized vs unoptimized builds differ by last-ULP rounding in accumulated fields
  (e.g. `flow_accumulation`) and a few `-0.0`/`0.0` signs; strict `validate` passes on both.
- **Output currently varies with `OMP_NUM_THREADS`** (1/4/16 all differ) — a determinism
  regression against the project's thread-invariance goal; tracked as a separate task.
