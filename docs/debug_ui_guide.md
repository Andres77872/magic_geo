# Web workbench UI guide

The local workbench combines world creation, operations, complete exported-data
browsing, the Three.js map debugger, backend telemetry, and live API docs.
Start it with:

```bash
pip install -e '.[debug]'
magic-geo serve
# http://127.0.0.1:8642
```

No `-d` argument is required. With the default `--workspace runs`, `runs/debug`
is loaded when present; with another workspace, the corresponding
`<workspace>/debug` is used. Otherwise the workbench starts cacheless and the
Config, Operations, and API tabs remain fully usable. See
[debugger.md](debugger.md) for architecture/security and
[configuration_helpers.md](configuration_helpers.md) for YAML/Python details.

## Global navigation

The header has five semantic tabs. Click one, use Left/Right/Home/End while a tab
has focus, or use the URL hashes `#map`, `#data`, `#config`, `#operations`, and
`#api`.

| View | What it covers | Needs a cache? |
|---|---|---|
| **Map** | Globe/2-D layer visualization and complete cell inspector | Yes; shows a useful empty state otherwise |
| **Data** | Every manifest class: scalars, skips, layers, cell schema, stages, full families, sections | Yes |
| **Config** | Profiles, YAML editor, validation, schema help, save/download | No |
| **Operations** | Generation, validation, calibration, rendering/export jobs, logs/artifacts/cancel | No |
| **API** | Native backend diagnostics and embedded/open Swagger | No |

The header cache selector lists every compatible cache discovered in the
workspace and switches through `/api/worlds/select`; the status badge says
**Cache ready** or **No cache** and shows workspace and package version. When a
Generate job finishes with “Prepare browser cache,” the page detects the
selected cache and initializes the map/data views.

At tablet/mobile widths the workspaces stack vertically; the map sidebars dock
over the viewport instead of permanently consuming horizontal space.

## Recommended browser-first workflow

1. Open **Config** and choose `smoke` for a fast first run or `earthlike` for
   the calibrated reference.
2. Edit YAML. Search the schema reference for a field, then validate.
3. Save it; the status reports a workspace path such as
   `runs/configs/world.yaml`.
4. Open **Operations**, select **Generate world**, set the saved config path and
   desired world output, and leave **Prepare browser cache** enabled.
5. Watch the queued/running job, streamed command log, and resulting artifacts.
6. When it succeeds, open **Map** for layers/cells or **Data** for generic
   families, sections, stages, and diagnostics.
7. Run validation/calibration/render/export operations against the saved world.

## Config view

### Profiles and editing

The profile selector comes from `/api/config/profiles`. Selecting a profile is
non-destructive; **Reset from profile** explicitly requests its complete
normalized template and replaces current editor changes. Delayed profile
responses cannot overwrite newer edits. The editor supports Tab indentation
(two spaces).

Profiles are starting points:

- `default` — exact neutral schema defaults;
- `earthlike` — calibrated Earth starter;
- `smoke` — 128-cell deterministic CPU integration run.

The editor remains raw YAML so every current/future field is usable without a
frontend release. **Validate YAML** sends it through the same duplicate-key-safe
parser and Pydantic model used by CLI/Python. Errors include source, line/column
when available, and field paths. Pathological nesting/alias expansion and YAML
over 1,000,000 UTF-8 bytes are rejected before model construction.

### Schema reference

The right panel resolves `$ref` entries from `/api/config/schema` and flattens
all nine sections/all 44 properties. Each card shows:

- dotted path;
- type and required status;
- authoritative description;
- default and enum choices when applicable.

The filter matches path, type, and description. Numeric bounds remain available
in Swagger/JSON Schema even if the compact card does not repeat every keyword.

### Save versus download

**Download YAML** creates a browser download only; it does not touch the server
filesystem. **Save configuration** validates and atomically writes below
`<workspace>/configs`. The filename accepts letters, digits, `.`, `_`, and `-`;
`.yaml` is added when missing. Existing names return a conflict and the UI asks
for explicit replacement confirmation. Arbitrary host paths and symlink escapes
are never accepted.

## Operations view

The operation form is generated from `/api/operations`, not hard-coded command
strings. Fields render as number inputs, choice/boolean selects, paths, or
one-path-per-line text areas. Types, choices, and bounds mirror the CLI.
Conventional browser output defaults are instead rebased under the configured
workspace. In particular, **Prepare browser cache** and **Export
browser/ParaView cache** default to `<workspace>/debug`; CLI `export-debug`
without `--output` derives `<world parent>/debug`. Generate and geo-suite forms
default their base YAML to `<workspace>/configs/world.yaml`, matching the Config
view's default save name. The geo-suite scenario matrix is deliberately
required: an installed wheel does not pretend the repository's example
`configs/geo_validation_matrix.yaml` exists.

### Available workflows

- **Generate world** — config, world JSON/MessagePack path, optional Markdown
  summary/CSV, cell override, full versus geo-only, optional automatic browser
  cache and VTU export.
- **Validate world** — complete structural/replay CLI validation.
- **Validate natural geography** — generic/Earth-like profile, JSON report,
  warning policy.
- **Run geo validation suite** — base config, scenario matrix, JSON/Markdown.
- **Calibrate world/ensemble** — target bundles, completeness/fit policies,
  reports.
- **Derive calibration targets** — local source manifest to JSON/Markdown.
- **Render SVG/raster** — projections, dimensions, labels/contours or texture,
  sampling controls.
- **Export browser/ParaView cache** — full columnar cache with optional VTU,
  built in staging and published to its workspace destination only on success.
- **Export Rerun** — available only when `rerun-sdk` is installed.

Configuration creation, backend inspection, and serving are shown as direct
equivalent views rather than recursive background jobs.

### Job states and logs

Only one heavy job runs at a time; additional work is queued. The UI polls every
2.5 seconds while visible and shows:

- queued/running/succeeded/failed/cancelled state;
- job ID and timestamps;
- normalized typed arguments;
- exact argument-vector command (no shell);
- bounded combined stdout/stderr log;
- exit code and immutable downloadable file snapshots;
- the cache directory selected by successful generation.

Cancel marks queued work cancelled without starting it. For running work it
terminates the child process group on POSIX (the child process elsewhere) and
escalates to a kill after five seconds. Closing the server cancels queued work,
terminates the active child, and waits for it to reach a terminal state before
closing cache connections. Cancellation and cache publication/artifact
finalization share an atomic commit boundary: a request accepted before commit
produces `cancelled` and discards staging; once commit has begun, a late cancel
is ignored and the job completes normally rather than reporting a false
cancelled state after publishing output.

For a successful job, each new or changed declared file output is copied to a
job-owned immutable snapshot. Download links read that snapshot, so later
replacement or deletion of the requested output does not change an earlier
job's download. The reporting operations (`validate-geo`,
`validate-geo-suite`, `calibrate`, and `calibrate-ensemble`) may write a report
and then exit nonzero because of a requested policy gate; a report newly written
or changed by that run remains downloadable from the failed job. An unchanged
pre-existing target is not claimed as new output. Cancelled jobs do not snapshot
partial files. If the primary Generate command completed before optional cache
preparation later failed or was cancelled, its completed world/summary/CSV
snapshots remain available.

Jobs and their snapshot links are in-memory records for the server lifetime and
can also be evicted when the bounded history fills. Requested outputs remain on
disk independently. Browser cache directories are different from downloadable
files: they are built in a job-private sibling staging directory, published only
after success, and discarded on failure or cancellation so the prior selected
cache remains intact. During the rollback-safe old/new directory swap,
cache-backed reads are paused. Browser reads also send the selected manifest
revision; a stale request receives `409` and is discarded, so parallel mesh,
catalog, and layer requests cannot combine two cache revisions.

Input paths must resolve to regular files within the project. That check follows
the nested source/DBF/PRJ/HydroBASINS-catalog paths used by `derive-targets` and
the target-bundle/derivation paths used by `validate-geo-suite`; manifests are
size/complexity bounded before this preflight. Outputs must resolve within the
workspace (`runs/` by default), cannot replace an input, and cannot overlap
another declared output. A rejected path is a policy error, not a missing CLI
feature.

## Data view

The Data tab is the generic escape hatch that makes every exporter/API resource
usable even when it has no custom map overlay.

The server supports debug manifests with `format: magic-geo-debug-cache` and
`version: 1`. A missing/different format or version is rejected; it is not
interpreted as a best-effort older/newer cache.

### Overview and diagnostics

- **Overview** counts layers, stage histories, families, sections, scalars, and
  skipped outputs, then lists record families/row counts.
- **Scalars** displays top-level scalar metadata.
- **Skipped outputs** exposes empty/unhandled top-level sections, non-scalar
  cell fields, and columns not promoted to visual layers. Skipped does not mean
  silently lost: new caches retain non-scalar cell values in the full cell
  sidecar.
- **Layer catalog** displays all layer manifest entries/stats.
- **Cell schema** displays scalar fields, skipped-layer reasons, and detail
  sidecar metadata.

### Stages, families, and sections

- **Stage summaries** uses `/api/stage-summary/{history}` for every history,
  rendering the full per-stage scalar table plus retained JSON stage extras for
  non-scalar metadata and mixed per-cell fields.
- **Record families** includes every exported list-of-records. Choose **Full
  nested records** for JSONL arrays/objects/provenance or **Scalar columns** for
  the compact Parquet sidecar. Pagination supports 25/50/100/200 rows.
- **Model sections** renders every exported dictionary—summary/model contracts,
  graphs, simulation clock, backend telemetry, validation/calibration content,
  and other named sections—as formatted JSON.

This closes the old gap where stage summaries, all families, and all sections
had server routes but no browser view.

## Map view

The map remains optimized for per-cell spatial fields. It does not try to turn
every record family into bespoke geometry; use Data for generic access.

### Layout

```text
┌────────────┬──────────────────────────────────────┬────────────┐
│ layer      │ projection/overlay/help controls     │ selected   │
│ sidebar    │ legend                               │ cell       │
│ world meta │                                      │ inspector  │
│ search     │ globe / equirect / Mollweide         │ fields     │
│ grouped    │                                      │ ledgers    │
│ layers     │ stage/month bar                      │ monthly    │
│ docs card  │ hover status                         │ adjacency  │
└────────────┴──────────────────────────────────────┴────────────┘
```

### Layers and legend

A layer is one per-cell column cataloged by the manifest and served as Float32
(`format=f32`, with Arrow also available to API clients). Four kinds exist:

| Kind | Time axis | Example |
|---|---|---|
| `numeric` | none | `cells/elevation_m` |
| `categorical` | none | `cells/biome` |
| `numeric_monthly` | 12 months | `monthly/temperature_monthly_c` |
| `numeric_stage` | history-specific stages | `hydrologic_water_budget_history/runoff_mm_y` |
| `categorical_stage` | history-specific stages | `hydrologic_water_budget_history/phase` |

Switching layers swaps one cached `Float32Array` into a GPU texture; geometry is
not rebuilt. Neighboring stages are prefetched.

JSON views convert NaN and positive/negative infinity to `null` so browser/API
serialization remains valid. Binary Float32 and Arrow layer downloads preserve
their existing non-finite/missing-value representation.

Numeric colors use the manifest p2–p98 range across the complete time axis, so
one color is comparable between stages/months. `≤`/`≥` markers indicate clipped
true extremes. Hover for the exact finite value. Categorical values use stable
golden-angle hues and category chips. Numeric `*_id` fields remain labels even
though the generic renderer uses a continuous scale.

The docs card (`d` or ⓘ) combines curated text, naming-pattern roles, inferred
units, source-family descriptions, stats, and categories. `/` searches names,
families, units, roles, and documentation.

### Exporting a GPT Image reference package

The map toolbar can download two matching, client-side artifacts for a GPT
Image refinement workflow:

- **Export PNG** captures the active layer at the final selected projection,
  using the current camera framing and every currently visible map overlay. It
  also reflects the selected stage or month. The browser writes an `image/png`
  file; the workbench does not send the map anywhere.
- **Export image prompt** writes a complete, copy/paste-ready GPT Image prompt
  as `text/markdown`. It names the paired PNG reference and records the world,
  layer, projection, time selection, and visible overlays. Its color codex lists
  every category and its cell color for categorical layers, or explains the
  numeric Viridis scale with representative color/value stops, range, clipping,
  and missing-data color for numeric layers.

The PNG and Markdown downloads share one sanitized base filename. Attach the
PNG as the reference image, then paste the Markdown prompt into GPT Image. The
prompt asks the image model to preserve the reference geography, projection,
color-coded region placement, semantic meaning, and composition while producing
the polished map described there. Diagnostic cell seams and overlays remain
spatial guides rather than required final-map decoration. Exporting creates only
these local files: it does **not** call OpenAI or any other image-generation API,
and it does not generate the final image inside the workbench.

The same export functionality is available without starting the web workbench.
The CLI independently reads the same debug cache and exposes both artifact
types, every layer and time slice, all three projections, explicit raster
dimensions, canonical camera center/distance framing, exact Three.js camera
pose replay, and every diagnostic overlay:

```bash
magic-geo export-debug-map \
  --debug-dir runs/debug \
  --layer cells/biome \
  --projection mollweide \
  --output runs/biome-reference
```

That command writes `runs/biome-reference.png` and
`runs/biome-reference.gpt-image-prompt.md`. Use `--no-image` or `--no-prompt`
for either web button's individual behavior; `--stage`, `--month`,
`--center-lat`, `--center-lon`, `--camera-distance`, `--wireframe`, `--plates`,
and `--graticule` expose the corresponding map snapshot controls. For an exact
interactive-camera replay, copy the position, target, up vector, and field of
view recorded in the web Markdown into `--camera-position`, `--camera-target`,
`--camera-up`, and `--vertical-fov`. This web/CLI parity is required for
map-export features; neither path invokes an image model.

One source-data exception is retained rather than guessed: the per-stage
`lithology` layer is serialized as numeric codes 0–6, but the debug cache does
not contain an authoritative code-to-name table for those stage values. Its
Markdown codex therefore preserves the numeric scale and repeats the warning;
it does not borrow the alphabetical category order from the separate final
`cells/lithology` layer or invent rock names for the stage codes.

Both exporters fail closed when the cache reports cells without boundary rings
or no renderable triangles. Otherwise those real cells would appear as
background holes and the prompt could incorrectly ask the image model to erase
them.

The generated prompt follows OpenAI's
[GPT Image prompting guidance](https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide):
short labeled sections, an explicit goal and composition, concrete visual
details, and a strict separation between what may change and what must remain
invariant.

### Stage/month controls

Stage/month layers reveal a slider, exact-value input, previous/next buttons,
and contextual metadata. `,` and `.` step backward/forward. Out-of-order fetches
cannot replace the newest selection; finite neighboring values are cached.

### Complete cell inspector

GPU ID-buffer picking opens `/api/cell/{id}`. For a newly exported cache it
contains:

- every scalar cell column;
- original vectors and all nested/non-scalar fields from the indexed detail
  sidecar (boundary ring, neighbors, LOD paths, linked IDs, etc.);
- every per-stage ledger slice and sparkline;
- monthly arrays/sparklines;
- adjacency rows with transition/boundary flags and click-through neighbors.

Old caches without the sidecar still work and report `complete: false`.

### Projection and overlays

| Key | Action |
|---|---|
| `1` / `2` / `3` | Globe / Equirectangular / Mollweide |
| `w` | Mesh wireframe |
| `b` | Plate-boundary segments |
| `g` | Graticule |
| `,` / `.` | Previous/next stage or month |
| `/` | Layer search |
| `d` | Layer docs |
| `?` | Map help |
| `Esc` | Close help, then inspector |

Drag rotates/pans, wheel zooms, hover reports cell/value, and click selects.
Projection morphs happen in the vertex shader; wireframe, boundaries, and grid
follow the same morph. Antimeridian polygons may extend past a 2-D edge to stay
contiguous. Visible cell-ring seams are a documented geometry diagnostic.

## Backend & API view

**Backend information** calls `/api/backend` and displays native CPU/OpenCL/CUDA
probe and selection data. Probe failures are isolated from the rest of the
workbench and displayed as a warning.

The right panel embeds Swagger at `/api/docs`; **Open Swagger** opens it in a new
tab. ReDoc is `/api/redoc` and machine-readable OpenAPI is
`/api/openapi.json`. Swagger documents config bodies, job requests, cache reads,
query bounds/enums, status codes, and artifact downloads.

## Extending the UI

### New generation field

Add it—with description/default/bounds—to the Pydantic model. The Config schema
reference automatically discovers it. Update the profile YAML and
[configuration reference](configuration_reference.md) when semantics change.

### New CLI/web operation field

Add one descriptor to `web_jobs.py`. The same catalog drives the form and
server-side normalization/path policy. Never add a free-form shell argument.

### New world output

The generic exporter automatically classifies scalar cells, monthly arrays,
stage histories, record families, dictionaries, and skipped shapes. The Data
view sees the manifest entry without frontend changes. Add a map layer or custom
overlay only when spatial visualization materially helps.

### Layer documentation

`debug_ui/layer_docs.js` resolves a layer in this order: curated field text,
pattern/role rule, unit rule, source-family text, then generated fallback. After
changes, regenerate [layers_reference.md](layers_reference.md):

```bash
node scripts/gen_layers_reference.mjs
```

## Troubleshooting

- **No cache** — normal on first start. Create/save YAML and run Generate with
  browser-cache preparation.
- **Config save fails** — use a simple filename, not a path; server saves below
  workspace `configs/`.
- **Operation rejected** — check required inputs, project/workspace path policy,
  numeric range, and enum choice.
- **Job fails** — select it and read the combined log/exit code. A validation or
  calibration report produced before a policy failure is still downloadable.
- **Data family lacks arrays** — switch detail from Scalar to Full nested.
- **Cell is incomplete** — re-export an old cache to create cell detail/index
  files.
- **Whole map layer is background** — current stage/month has no finite values.
- **Map cannot initialize** — Data/API still work; inspect `/api/status`, cache
  error, manifest, and mesh assets.
- **Cache format rejected** — re-export it as `magic-geo-debug-cache` version
  `1`.
- **Rerun disabled** — install `rerun-sdk`; its catalog entry intentionally
  advertises the missing dependency.
- **Running on another device** — this is a trusted-local, single-user service.
  It has no login, authorization, per-user isolation, or TLS; anyone who can
  reach it can inspect data and submit/cancel jobs. Keep loopback binding unless
  a trusted network boundary and authenticating proxy protect it.
