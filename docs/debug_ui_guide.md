# Debug UI Guide

Deep reference for the GUI debugger frontend (`src/magic_geo/debug_ui/`). For the
pipeline that produces the data it renders, see [debugger.md](debugger.md); for a
review of that pipeline, see [layers_pipeline_review.md](layers_pipeline_review.md).

In-app: press `?` (or the `?` button) for the built-in help overlay, and `d`
(or the legend's ⓘ button) for the docs card describing the active layer. Both are
driven by [layer_docs.js](../src/magic_geo/debug_ui/layer_docs.js) — see
[Extending the docs helper](#extending-the-docs-helper).

## Quickstart

```bash
pip install -e '.[debug]'
magic-geo generate  --config configs/earthlike_seed.yaml --output runs/earthlike/world.json
magic-geo export-debug --world runs/earthlike/world.json      # → runs/earthlike/debug/
magic-geo serve -d runs/earthlike/debug                       # → http://127.0.0.1:8642
```

## Screen layout

```text
┌────────────┬──────────────────────────────────────┬────────────┐
│ sidebar    │ topbar: projections · overlays · ?   │ inspector  │
│  world     │         legend (+ ⓘ)                 │  (opens on │
│  meta      │                                      │   click)   │
│  search    │            globe / map               │  fields    │
│  layer     │                                      │  ledgers   │
│  list      │      stage/month bar (when the       │  monthly   │
│  docs card │      layer has a time axis)          │  adjacency │
│            │ status: layer · cell · value         │            │
└────────────┴──────────────────────────────────────┴────────────┘
```

## Layers

A **layer** is one per-cell column of the exported world, cataloged in
`manifest.json` and served as a Float32 buffer from `/api/layer/{id}`. The
sidebar groups layers by record family (source). On the default earthlike run
there are 446 layers over 4 096 cells, in four kinds:

| kind | badge | time axis | example |
|---|---|---|---|
| `numeric` | — | none | `cells/elevation_m` |
| `categorical` | `cat` | none | `cells/biome` |
| `numeric_monthly` | `monthly` | 12 months | `monthly/temperature_monthly_c` |
| `numeric_stage` | `stages` | simulation stages | `hydrologic_water_budget_history/runoff_mm_y` |

Selecting a layer swaps a single `Float32Array` into a GPU texture — geometry is
never rebuilt, so switching is instant once the buffer is fetched. Buffers are
LRU-cached (48 entries) and stage scrubbing prefetches ±2 stages.

### Reading the legend

- **Numeric** legends span the **p2–p98** percentile range of the data, not
  min–max. The extreme 2 % on each side render saturated. This keeps skewed
  layers (e.g. `flow_accumulation`) readable; hover a cell for the exact value.
  The docs card (`d`) shows both min/max and the p2/p98 legend bounds.
- **Monthly and stage** legend ranges span *all* months/stages at once, so a
  color means the same thing at every slider position — change over time reads
  as change in color.
- **Categorical** layers map each category to a golden-angle hue; the legend
  lists every chip. Color similarity is meaningless.
- Layers ending in `_id` are numeric labels (basins, plates, regions) rendered
  on the continuous ramp; treat the colors as labels, not magnitudes.
- Cells with no value for the current layer/stage/month render as the dark
  background color.

### Field-name conventions

Field names carry their units as suffixes; the docs helper decodes these
automatically (`_m`, `_km`, `_km2`, `_km3_y`, `_mm_y`, `_m3_s`, `_m_s`, `_m_y`,
`_w_m2`, `_pa`/`_kpa`/`_hpa`, `_c`, `_ka`/`_ma`/`_years`, `_deg`, `_ph`,
`_fraction`, `_index`, `_factor`, `_count`, `_id`). Prefixes identify the
subsystem (`groundwater_*`, `glacial_*`, `wildfire_*`, `petroleum_*`, …); the
doc card names the subsystem and explains it for every layer, including fields
added after this guide was written.

### The two stage histories (earthlike run)

- `hydrologic_water_budget_history` — 16 stages × 16 fields. Snapshots of the
  coupled water-budget recompute: climate inputs (precipitation, PET,
  temperature) and hydrologic outputs (infiltration, runoff, residual) at each
  feedback stage. `residual_mm_y` should be near zero everywhere — hotspots
  flag conservation bugs.
- `numeric_depression_fill_history` — 1600 stages × 11 fields. One record per
  depression fill/breach *event* during hydrologic conditioning, so most cells
  are empty at any single stage; scrub or use the inspector's ledger sparklines
  to see a cell's events in context.

## Controls

### Keyboard

| key | action |
|---|---|
| `1` / `2` / `3` | Globe / Equirectangular / Mollweide (animated morph) |
| `w` | Mesh wireframe overlay |
| `b` | Plate-boundary overlay |
| `g` | Graticule overlay |
| `,` / `.` | Step stage or month backward / forward |
| `/` | Focus the layer search |
| `d` | Toggle the layer docs card |
| `?` | Toggle the help overlay |
| `Esc` | Close help → inspector (in that order) |

### Mouse

Drag rotates (or pans in 2D); wheel zooms; hovering shows cell id and value in
the status bar; clicking a cell opens the inspector. Inside the inspector,
neighbor links jump to adjacent cells.

### Search

The layer filter matches the layer name, its family, **and its documentation** —
units, subsystem, and description text. Searching `upwelling` finds
`fishery_productivity_index` because its doc mentions upwelling; searching
`W/m²`-style units or `monsoon` works the same way. Hovering a layer shows its
one-line doc as a tooltip.

### Stage/month bar

Appears only for layers with a time axis. Slider, exact-value field, and step
buttons all set the same stage; the label shows stage metadata (engine stage id,
erosion iteration) when the history provides it. Scrubbing fetches on demand;
±2 neighboring stages prefetch in the background.

## Inspector

Click any cell:

- **Ledger slices** — per-stage sparklines for every stage-history field at
  this cell; an orange marker tracks the active stage when the active layer
  belongs to that history.
- **Monthly** — 12-point sparklines for monthly fields.
- **Fields** — all ~400 static fields with a filter box.
- **Adjacency** — every neighbor edge with distance and flags
  (`plate_boundary`, `land_water_transition`, `biome_transition`); click a
  neighbor to jump.

## Projections and overlays

Projection morphs are vertex-shader blends between the unit sphere and
precomputed equirectangular/Mollweide plane positions; every overlay (wireframe,
plates, graticule) follows the same morph via a shared shader chunk. Cells
straddling the antimeridian keep their polygons contiguous by letting them poke
past the map edge in 2D — this is intentional, not a bug.

Visible seams between cell polygons are the documented `boundary_ring`
approximation; `mean_neighbor_boundary_segment_mismatch_km` and
`cell_polygon_area_error_fraction` are the layers that measure it.

## API quick reference

All endpoints are read-only over the exported cache:

| endpoint | returns |
|---|---|
| `/api/manifest` | layer catalog, stats, stage index, world metadata |
| `/api/layer/{id}?stage=&month=&format=f32\|arrow` | one Float32 value per cell |
| `/api/cell/{id}` | full record + ledger slices + monthly + adjacency |
| `/api/stage-summary/{history}` | per-stage scalar table (sparkline source) |
| `/api/family/{name}?limit=&offset=` | paged rows from any record family |
| `/api/section/{name}` | dict sections (models, graphs, clock) |
| `/api/plate-boundaries` | plate-boundary segments as lat/lon pairs |
| `/mesh/*` | binary mesh buffers (positions, cell ids, indices, 2D positions) |

`window.__magicGeo` exposes `{ state, three }` in the console for debugging the
debugger.

## Extending the docs helper

[layer_docs.js](../src/magic_geo/debug_ui/layer_docs.js) resolves documentation
for each layer in priority order (`describeLayer`):

1. `CURATED` — curated one-liners keyed by bare field name. Add new entries
   here when a field needs more than convention can say.
2. `PATTERN_RULES` — ordered name-pattern predicates that assign a role
   (identifier, index, diagnostic, …) and a convention blurb. Order matters:
   specific rules before broad ones.
3. `UNIT_RULES` — ordered suffix → unit from the conventions above (plus
   `EXACT_UNITS` for names that carry no suffix).
4. A generated fallback: kind + inferred unit + value range from manifest stats.

`SOURCE_DOCS` describes record families (shown at the bottom of the docs card),
`UI_GUIDE` and `KEY_REFERENCE` feed the help overlay, and `docsCoverage()`
reports in the overlay how many layers resolve through each tier — so it is
obvious when new engine output has no bespoke docs yet. The layer-list tooltips
and doc-text search (`layerTooltip`/`searchTerms`) are built on the same
resolution. Everything degrades gracefully: an unknown field still gets a unit,
a role, or at minimum its kind explained.

After editing `CURATED` or the rules, regenerate the markdown reference with
`node scripts/gen_layers_reference.mjs` (see
[layers_reference.md](layers_reference.md)).

## Troubleshooting

- **Blank page / fetch errors** — `serve` must point at a directory produced by
  `export-debug` (it needs `manifest.json`); regenerate the cache after
  changing the exporter.
- **Whole layer renders as background** — the layer has no finite values at the
  current stage/month (common in `numeric_depression_fill_history`, where
  stages are sparse events).
- **Colors look flat** — heavy-tailed layer; the p2–p98 clamp is compressing
  the tail. Hover cells to read actual values.
- **Stage scrub feels laggy on 1600-stage histories** — each stage is a
  DuckDB-filtered fetch. Out-of-order responses are dropped (only the newest
  request may update the display), so fast scrubbing simply waits for the
  latest fetch; ±2 neighbours prefetch to keep stepping instant.
- **Seams between polygons** — documented ring mismatch (see above), useful as
  a mesh-quality signal.
