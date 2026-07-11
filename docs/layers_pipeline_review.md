# Layers Pipeline Review (2026-07-10)

Deep review of the layer path: `debug_export.py` (world.json → debug cache) →
`debug_server.py` (cache → HTTP) → `debug_ui/app.js` (HTTP → pixels). Findings
are ordered by severity within each component; none block day-to-day use.
Verified against the earthlike run: 32 768 cells, 446 layers, stage histories of
16 and 1600 stages, 118 record families.

## Findings

### F1 — Stage scrub can display a stale stage (app.js, medium)

`activateLayer()` guards against superseded fetches with
`if (state.activeLayer !== layer) return;` — but not against superseded
*stage/month* on the same layer. Dragging the slider fires one fetch per input
event; whichever response resolves last wins the texture, while
`updateStageBar()` always shows the *requested* stage. On
`numeric_depression_fill_history` (1600 stages) this reproduces easily: the
label says stage 900 while the colors are stage 850's.

Fix shape: capture `const requested = ${layer.id}|${state.stage}|${state.month}`
before the `await` and re-check it after, or keep a monotonically increasing
request sequence number.

### F2 — 88 of 118 record families are unreachable in full through the API (debug_server.py, medium)

`family_rows()` prefers the Parquet sidecar whenever one exists:
`if "parquet" in family or "scalars_parquet" in family`. For the 88
`jsonl+scalars` families, the scalar sidecar is returned and the nested JSONL
records (the actual provenance/event payloads) are never served — only the 2
plain-`jsonl` families reach clients intact. The UI doesn't use nested rows, so
nothing visibly breaks, but the API contract implied by the manifest
("families have `jsonl` files") is unfulfillable over HTTP. Either add
`?full=1` to page the JSONL, or document the sidecar-only behavior.

### F3 — Layers dropped silently, contradicting the exporter's contract (debug_export.py, low-medium)

The module docstring promises "anything that is skipped is recorded in the
manifest rather than dropped silently", and `skipped_fields` honors that for
columns. But `_layer_entry()` returns `None` for numeric fields with no finite
values and for categoricals with > 64 distinct values, and the caller just
doesn't append — no manifest record. On the earthlike run, `s2_like_token` and
`healpix_like_pixel_code` exist in `cells.parquet` but appear in no layer list
and no skip list. Record them, e.g. `manifest["cells"]["fields_without_layers"]
= {name: reason}`.

### F4 — Prefetch and cache keys disagree across kinds (app.js, low)

`layerCacheKey(layerId, stage, month)` incorporates both time axes for every
kind, but `prefetchNeighborStages()` hardcodes `month = 0`. After viewing a
monthly layer with `state.month = 7`, activating a stage layer fetches under
`…|stage|7` while its prefetched neighbors sit under `…|stage|0`: prefetch
misses, and identical buffers are stored twice. Normalize the key per kind
(stage layers → month 0; monthly layers → stage 0; static layers → 0/0).

### F5 — Mixed-type stage-summary columns crash the export (debug_export.py, low, latent)

In `_export_stage_history()`, a summary column whose values mix strings and
numbers classifies as `"mixed"` and is then forced to `"float"`, so
`_pa_column()` calls `float("...")` → uncaught `ValueError`. Engine output is
currently type-stable so this doesn't fire, but a single stage record emitting
`"stage": "init"` alongside numeric stages would kill the whole export. Guard
by skipping (and manifest-recording) mixed summary columns.

### F6 — Ragged monthly arrays crash the export (debug_export.py, low, latent)

`_export_cells()` classifies a field as monthly from the *first* non-null
sample (`len(sample) == 12`) but then indexes `value[month]` for every cell.
Any cell holding a list of another length raises `IndexError`. Same class as
F5: type-stable today, one malformed record from failing. Check
`len(value) == 12` per cell.

### F7 — VTU export crashes on null per-cell values (debug_export.py, low, latent)

`_write_vtu_stages()` renders `f"{float(values[row]):.6f}"` — a JSON `null`
inside a `*_by_cell` array raises `TypeError`. The Parquet path handles nulls;
the VTU path should fall back to `"0"` the way it already does for missing
rows. (Also: `start = offset` … `del start` is dead code.)

### F8 — Path-prefix check uses `startswith` (debug_server.py, hardening)

`_table_path()` validates `str(path).startswith(str(self.dir))`, which accepts
sibling directories like `…/debug-evil` for a cache at `…/debug`. Inputs come
from the trusted manifest, and the server binds 127.0.0.1 by default, so this
is hardening rather than a vulnerability: use `path.is_relative_to(self.dir)`.
Similarly, layer/field names are interpolated into DuckDB SQL as quoted
identifiers — fine for engine-generated names, but a `"` in a field name would
break the query; escaping doubles the quote.

### F9 — `struct.pack(f"<{n}f", *values)` scales poorly (debug_server.py, perf)

Unpacking n floats as Python call arguments is fine at 32 768 cells (~128 KB)
but becomes a visible per-request cost at 10⁶-cell runs. `array('f',
values).tobytes()` (or numpy) is the drop-in replacement. In the same vein,
every `/api/layer` response is `Cache-Control: no-store`; the client-side LRU
compensates, but ETag-based validation would let reloads reuse buffers.

### F10 — Layer-id namespace can collide (debug_export.py, nit)

Layer ids are `cells/{name}`, `monthly/{name}`, and `{history}/{field}`. A
stage history literally named `cells` or `monthly` would collide with the
static namespaces. Unlikely with current engine naming; worth an assert in
`export_debug_cache()`.

## Verified non-issues

Checked and found correct, for the record:

- **Categorical legend/shader color match** — `THREE.Color.setHSL` with the
  default color-space argument performs no conversion in the vendored r185, so
  the JS golden-angle chips and the GLSL `fract(v · φ)` hue formula produce
  identical colors.
- **Pick-buffer encoding** — the white clear color decodes to id 16 777 215,
  safely above any cell count; the pick target has no MSAA to smear ids.
- **NaN transport** — server sends real NaNs in the f32 stream; the client
  rewrites them to a 3.0e38 sentinel before upload, and the shader treats both
  `> 1e37` and `isnan` as missing. Robust across drivers.
- **Legend p2/p98 fallbacks** — degenerate stats (`p2 == p98`, all-equal
  columns) fall back through min/max to a synthetic +1 span; no divide-by-zero
  (the shader also clamps with a 1e-12 floor).
- **Stage/month clamping** — server clamps `stage` and `month` into range;
  unknown layer ids 404 before any SQL runs.
- **Antimeridian cells** — ring vertices are wrapped near the cell center and
  allowed to exceed the 2D map edge, keeping polygons contiguous in all three
  projections.

## Scope notes

- `debug_rerun.py` (Rerun export) and the ParaView content itself were not
  deep-reviewed; only the export path that feeds them.
- The known thread-count determinism regression is tracked separately in
  [debugger.md](debugger.md) and is upstream of this pipeline.
