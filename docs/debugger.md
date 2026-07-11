# GUI Debugger

Implementation of the local-web debugger recommended by
[gui_debug_visualization_research.md](gui_debug_visualization_research.md): the CLI stays the only
generation interface; the debugger is a read-mostly visualization layer over generated artifacts.

**Reference docs:**
[layers_reference.md](layers_reference.md) — deep catalog of every layer (props, meaning, status,
gaps), grouped by domain · [configuration_reference.md](configuration_reference.md) — every
generation config property (type, default, range, effect) · [layers_review.md](layers_review.md) —
pipeline review with ranked, verified findings.

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

One merged indexed `BufferGeometry` (fan per cell around its site, per-vertex `cell_id`), per-cell
values in an R32F `DataTexture` fetched by cell id in the vertex shader, viridis/categorical
colormap in the fragment shader. Layer switch and stage scrub swap one `Float32Array` — no
geometry rebuild. Vendored three.js 0.185 (`debug_ui/vendor/`), loaded via import map.

- Layer panel: grouped by record family, search filter (`/`), numeric + categorical + monthly +
  per-stage layers (446 layers on the default earthlike run).
- Docs helper: a docs card under the layer panel explains the active layer (unit, role, value
  range, category list) and a `?` help overlay documents every control plus the field-naming
  conventions. See [Docs helper](#docs-helper-layer_docsjs) below.
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

## Docs helper (`layer_docs.js`)

With ~450 layers per world, the UI ships a data-driven documentation layer so you never have to
guess what a field means. It resolves docs for the active layer in decreasing specificity — a
curated paragraph, then the field-naming convention (`*_id`, `*_index`, `*_mm_y`, `initial_*`,
`cumulative_*`, `*_residual_*`, …), then the record-family description, then a generated fallback
that infers the unit from the name suffix and reports the value range from manifest stats. On the
default earthlike run this documents all 446 layers with only ~19 falling to the pure generated
fallback; the exact split is shown in the help overlay's "Docs coverage" box.

- **Docs card** (under the layer panel, toggle `d`): the active layer's name, a role badge
  (ID / index / class / initial / cumulative / diagnostic / …), inferred unit, description,
  min/max vs the p2–p98 colour-scale range, category chips for categoricals, and a one-line
  description of the containing record family. Collapse it with the header caret.
- **Help overlay** (`?`, close with `Esc` or the backdrop): a full keyboard reference, a control
  guide (layers, stage/month scrubbing, projections, overlays, cell inspector), a "reading the
  data honestly" section (identifiers are labels not magnitudes; `_index` fields are derived;
  residuals should be ~0; ring seams are expected), and the live docs-coverage report.
- **Legend clip markers**: the colour ramp normalises to p2–p98, so heavy-tailed layers now show
  `≥`/`≤` on the legend ends when the true min/max extends past the ramp (e.g. `flow_accumulation`
  whose max ≈ 4.76e9 sits far above its p98 ≈ 5.2e7). Hover the label for the true extreme.

To document a new field with bespoke prose, add it to `CURATED` in
[`debug_ui/layer_docs.js`](../src/magic_geo/debug_ui/layer_docs.js); everything else is picked up
automatically from the naming conventions. A deep review of the whole layer pipeline (export →
server → UI), with verified findings and a fix order, is in
[layers_review.md](layers_review.md).

## Build/determinism notes (verified 2026-07-10)

- `CMakeLists.txt` now defaults `CMAKE_BUILD_TYPE` to Release (the shipped library had been built
  unoptimized) and pins `-ffp-contract=off` so FMA fusion cannot introduce backend drift.
- Run-to-run output at a fixed thread count is bit-stable (identical SHA-256).
- Optimized vs unoptimized builds differ by last-ULP rounding in accumulated fields
  (e.g. `flow_accumulation`) and a few `-0.0`/`0.0` signs; strict `validate` passes on both.
- **Output currently varies with `OMP_NUM_THREADS`** (1/4/16 all differ) — a determinism
  regression against the project's thread-invariance goal; tracked as a separate task.
