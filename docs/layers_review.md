# Deep Review: the Debugger Layer Pipeline

Reviewed 2026-07-10 against the code in this branch and the real `runs/earthlike/debug`
cache (32,768 cells, **446 layers**: 368 `numeric`, 47 `categorical`, 27 `numeric_stage`,
4 `numeric_monthly`; 2 stage histories with 16 and 1,600 stages; 118 record families).

Scope: the full life of a *layer* — classification and manifest generation in
[debug_export.py](../src/magic_geo/debug_export.py), serving in
[debug_server.py](../src/magic_geo/debug_server.py), and rendering/interaction in
[debug_ui/app.js](../src/magic_geo/debug_ui/app.js). Findings marked **confirmed** were
reproduced against the earthlike cache or are unambiguous from control flow; **plausible**
findings need a payload shape that the earthlike run does not produce.

## 1. How a layer flows through the system (architecture recap)

1. **Classification** (`debug_export.py`). Cell fields become `cells/*` layers: int/float →
   `numeric` (with min/max/p2/p98 stats), str/bool → `categorical` (sorted distinct values,
   ≤ 64). 12-long numeric lists become `monthly/*` (`numeric_monthly`) layers. Record
   families shaped as `cell_ids` + `*_by_cell` become `<family>/<field>` (`numeric_stage`)
   layers. Everything lands in `manifest.json`.
2. **Serving** (`debug_server.py`). `/api/layer/{id}?stage=&month=` runs a DuckDB query over
   the relevant Parquet and returns one dense little-endian Float32 buffer indexed by cell
   id (`NaN` = missing; categorical values are indices into the manifest's `categories`,
   `-1` = unknown).
3. **Rendering** (`app.js`). Values go into an R32F `DataTexture` fetched by per-vertex
   cell id; the fragment shader applies viridis (numeric, normalized to p2–p98) or a
   golden-ratio HSL cycle (categorical). `NaN` is replaced client-side by a `3.0e38`
   sentinel that the shader treats as missing. Stage/month scrubbing swaps one
   `Float32Array` through an LRU cache (48 entries) with ±2-stage prefetch.

This design is sound: no geometry rebuilds on layer/stage switches, missing data survives
every GPU driver, and the generic classifier means new engine output shows up as layers
with zero exporter changes. The findings below are ordered by severity.

## 2. Findings

### F1 — Stage/month scrub race can display stale data (confirmed, bug — **fixed**)

**Fixed:** `activateLayer` now tags every request with a monotonic token
(`state.fetchSeq`, [app.js:707](../src/magic_geo/debug_ui/app.js:707)) and drops any
response that is no longer the newest request, so out-of-order responses can never
overwrite the display.

Original issue: the resolved fetch was guarded only with
`if (state.activeLayer !== layer)` — object identity. Scrubbing the same layer issued
concurrent fetches for different stages; the guard passed for all of them, so whichever
response resolved **last** won, not the one matching the UI state (easy to hit on the
1,600-stage `numeric_depression_correction_history`).

### F2 — High-cardinality string fields are dropped silently (confirmed, contract violation — **fixed**)

**Fixed:** columns that are written to Parquet but yield no layer entry are now recorded
under `skipped_layers` manifest keys with a reason — in `cells` (> 64 distinct values or
no finite values), in each `stage_histories` entry, and in `monthly`. The columns still
appear per cell via `/api/cell`.

Original issue: the module docstring promises "Anything that is skipped is recorded in
the manifest rather than dropped silently", but when `_categories` exceeded the 64-value
limit or a numeric column had no finite values, `_layer_entry` returned `None` and the
field simply got no layer and no skip record. Confirmed in the earthlike cache:
`healpix_like_pixel_code` and `s2_like_token` existed as columns in `cells.parquet` with
no layer entry and no skip record.

### F3 — Per-stage `lithology` is numeric codes; per-cell `lithology` is strings (confirmed, data-model inconsistency)

`hydrologic_water_budget_history/lithology` renders as a `numeric_stage` layer with values
0–6, while `cells/lithology` is categorical with
`['basalt', 'granite', 'limestone', 'metamorphic', 'sandstone', 'shale', 'volcanic']`.
The engine serializes coded lithology in the ledger and names in the cells table, and no
code→name table ships in the manifest. Worse, the categorical layer's indices are
**alphabetical** (export-side `sorted(distinct)`), which very likely differs from the
engine's enum order — so a user cross-referencing "3.0 in the history layer" against the
category chips can silently read the wrong rock type. Same pattern applies to boolean
ledger fields (`is_marine` arrives as 0/1 floats — acceptable, but undocumented).

Fix: either serialize names in the ledger, or emit the engine's code table into the
manifest so the UI can label ledger codes.

### F4 — Stage prefetch caches under the wrong key when month ≠ 0 (confirmed, bug — **fixed**)

**Fixed:** `layerCacheKey` now normalizes per layer kind
([app.js:232](../src/magic_geo/debug_ui/app.js:232)) — month is zeroed for
`numeric_stage` keys and stage for `numeric_monthly` keys — and
`prefetchNeighborStages` fetches with the live `state.month`
([app.js:264](../src/magic_geo/debug_ui/app.js:264)), so prefetched buffers always hit.

Original issue: prefetch cached under `id|stage|0` while `activateLayer` fetched with the
persisted `state.month`, producing keys like `id|stage|5` after viewing a monthly layer —
every prefetched buffer missed the cache and each scrub step re-downloaded.

### F5 — Latent exporter crashes on plausible payload shapes (plausible)

- Every `*_by_cell` array is hard-typed float
  ([debug_export.py:250](../src/magic_geo/debug_export.py:250)); a string-valued ledger
  field (exactly what F3's `lithology` would become if the engine switched to names) makes
  `_pa_column` call `float("basalt")` → `ValueError`, killing the whole export.
- Stage-summary scalars that mix strings and numbers across stages fall back to `"float"`
  ([debug_export.py:284](../src/magic_geo/debug_export.py:284)) with the same crash.
- A cells monthly field whose first non-None entry is a 12-long numeric list is accepted
  for all rows ([debug_export.py:166](../src/magic_geo/debug_export.py:166)); a later row
  with a shorter list raises `IndexError` at
  [debug_export.py:205](../src/magic_geo/debug_export.py:205).

Fix: validate per-row and route offenders into `skipped_fields` instead of crashing.

### F6 — Legend implies min/max but shows p2/p98 without any clip indication (confirmed, UX-correctness — **mostly fixed**)

**Fixed (clip indication):** the legend now prefixes clipped ends with `≤`/`≥` and shows
the true min/max in the label tooltip ([app.js:561-568](../src/magic_geo/debug_ui/app.js:561));
the docs card additionally shows min/max next to the p2–p98 colour-scale range.

Still open: 62 of 446 layers have p2 == p98 (mass-zero fields like
`cells/froude_number`), where the silent fallback to min/max
([app.js:571](../src/magic_geo/debug_ui/app.js:571)) changes scale semantics between
layers with no visual cue; and there is no way to switch to full range, log scale, or a
diverging ramp for signed fields (`sediment_net_budget_m`, `*_residual_*`).

### F7 — Docs drift: `/api/stage-summary` is not used by the frontend (confirmed)

[debugger.md](debugger.md) describes "per-stage summary tables for sparklines", but the
inspector sparklines are built from `/api/cell` ledger slices
([app.js:879-886](../src/magic_geo/debug_ui/app.js:879)); nothing in `app.js` calls
`/api/stage-summary`. The endpoint works (verified by hand) but is dead from the UI's
perspective — either wire per-stage *world aggregate* sparklines into the stage bar (the
data is exactly right for it) or mark the endpoint as external-consumer API.

### F8 — Identifier fields render as continuous gradients (confirmed, interpretability)

30+ layers are identifiers or graph references (`basin_id`, `plate_id`, `*_system_id`,
`flow_to`, `spill_to`, `*_cell_id`, `s2_like_cell_id`…). They classify as `numeric`, so
adjacent ids get adjacent viridis colors — the resulting gradients look meaningful but are
noise, and percentile stats on ids are meaningless. A hash-to-color ramp (like the
categorical path) for `*_id`/`*_to` fields would make region structure actually visible.
(The new in-UI docs helper flags these as identifier layers as a first mitigation.)

### F9 — Robustness nits in the server (confirmed, low severity for a local tool)

- `_table_path` guards traversal with `str(path).startswith(str(self.dir))`
  ([debug_server.py:40](../src/magic_geo/debug_server.py:40)) — a sibling directory like
  `<dir>2` passes the check. Use `Path.is_relative_to`.
- Column names are interpolated into SQL as `"{name}"`
  ([debug_server.py:63](../src/magic_geo/debug_server.py:63),
  [71](../src/magic_geo/debug_server.py:71),
  [76](../src/magic_geo/debug_server.py:76)); a field name containing `"` breaks the
  query. Field names come from world-payload keys, so this is a correctness edge more than
  an attack surface.
- `_float32_response` packs with `struct.pack(f"<{n}f", *values)`
  ([debug_server.py:199](../src/magic_geo/debug_server.py:199)) — a finite float64 above
  float32 range would raise `OverflowError` (500), and unpacking 32k+ values through
  `*args` is measurably slower than `array('f', values).tobytes()`.

### F10 — 2D projections: dateline-crossing cells overhang the map edge (confirmed, accepted tradeoff)

Ring vertices are wrapped near the cell center
([debug_export.py:441](../src/magic_geo/debug_export.py:441)), so a cell straddling ±180°
renders as one polygon sticking out past the plane edge instead of splitting into two.
Same for plate-boundary segments ([app.js:384](../src/magic_geo/debug_ui/app.js:384)).
Reasonable for a debugger (splitting fans is real work); worth documenting so nobody
debugs it as a mesh defect. The globe projection is unaffected.

### F11 — Layer list: search does not open collapsed groups (confirmed, minor UX)

Group collapse works by toggling the group body's `display`
([app.js:795-797](../src/magic_geo/debug_ui/app.js:795)), while search toggles per-item
`display` ([app.js:818-821](../src/magic_geo/debug_ui/app.js:818)). Matches inside a
collapsed group stay invisible, and titles of fully-filtered-out groups remain visible.
With 446 layers, search is the primary navigation — this deserves a fix.

### F12 — Performance notes (observations)

- Every layer request re-reads Parquet through DuckDB with no server-side caching; fine at
  32k cells (415-column file, but projection pushdown keeps it cheap), will not scale to
  million-cell runs. An in-memory LRU of materialized columns is the obvious lever.
- `numeric_depression_correction_history` has 1,600 stages; scrubbing it end-to-end is 1,600
  requests (×5 with prefetch). Server-side downsampling or range requests would help.
- Stats for `numeric_monthly` layers are computed over all 12 months flattened
  ([debug_export.py:213](../src/magic_geo/debug_export.py:213)), and `numeric_stage` stats
  over all stages — deliberate and good (stable color scale while scrubbing), but
  undocumented until now.
- `del start` at [debug_export.py:538](../src/magic_geo/debug_export.py:538) is dead code.

### What holds up well (positive findings)

- The NaN→sentinel→shader-guard chain is careful and driver-proof; missing cells render
  as a distinct neutral rather than colormap ends.
- One merged geometry + value-texture indirection is the right architecture: layer and
  stage switches upload 128 KB and touch nothing else.
- GPU id-buffer picking with overlay suppression during the pick pass is correct,
  including through projection morphs (shared `uMorph` chunk across all four materials).
- The generic payload-shape classifier has proven itself: all 446 layers, 118 families,
  and both stage histories were discovered with zero per-field code.
- Bool categorical round-trip (Python bool → `"True"`/`"False"` categories → DuckDB bool →
  `str()` lookup) is consistent end-to-end (verified).

## 3. Recommended fix order

| Priority | Finding | Effort | Status |
|---|---|---|---|
| 1 | F1 stage-scrub race | small (request token) | **fixed** |
| 2 | F4 prefetch cache key | one line | **fixed** |
| 3 | F2 silent layer drops | small (manifest bookkeeping) | **fixed** |
| 4 | F6 legend clip indication | small (UI) | **fixed** (range-mode toggle still open) |
| 5 | F11 search vs collapsed groups | small (UI) | open |
| 6 | F3 ledger code tables | needs engine/serializer touch | open |
| 7 | F5 exporter hardening | medium | open |
| 8 | F8 id-layer color mode | medium | open |
| 9 | F7, F9, F10, F12 | as convenient | open |

## 4. Reviewed inventory snapshot (earthlike run)

- 446 layers = 415 `cells/*` + 16 `hydrologic_water_budget_history/*` +
  11 `numeric_depression_correction_history/*` + 4 `monthly/*`.
- 47 categorical layers, 2–18 categories each; 64-category limit not hit by any kept layer.
- Stage histories: water budget 16 stages (8 clock stages × recomputes), depression fill
  1,600 stages.
- Mesh: 482,156 vertices / 449,388 triangles / 0 cells without rings.
- Layer stats extremes: `flow_accumulation` max 4.76e9 (largest magnitude); all values
  comfortably inside float32 range.
