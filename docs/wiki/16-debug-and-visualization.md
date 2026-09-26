# Debug Exports and Visualization

[Wiki home](./README.md) > Debug Exports and Visualization

magic-geo ships three offline export paths that turn one monolithic generated world into inspectable artifacts: `export-debug` (a columnar **debug cache** of Parquet tables, JSONL sidecars, GPU-ready mesh buffers, and optional ParaView `.vtu` stages), `export-debug-map` (a browserless PNG + GPT Image prompt rendered from an existing cache), and `export-rerun` (an optional `.rrd` recording). This page is the reference for the on-disk contract of all three: the manifest field tables, every Parquet family with its column schema, the binary mesh buffer layouts, the layer addressing scheme, the `layer_docs.js` documentation catalog, the unused mesh LOD index, and the exact default-path rules that differ between CLI and browser invocations. Everything below was read out of the implementation; anything the source does not state is marked as such.

## On this page

- [The debug cache: purpose and scope](#the-debug-cache-purpose-and-scope)
- [On-disk directory layout](#on-disk-directory-layout)
- [`manifest.json` field reference](#manifestjson-field-reference)
- [Parquet table families and column schemas](#parquet-table-families-and-column-schemas)
- [JSONL sidecars and the cell-details index](#jsonl-sidecars-and-the-cell-details-index)
- [Mesh assets and their binary layouts](#mesh-assets-and-their-binary-layouts)
- [The ParaView VTU option](#the-paraview-vtu-option)
- [Layer addressing and what a "layer" is](#layer-addressing-and-what-a-layer-is)
- [The layer catalog and `layer_docs.js`](#the-layer-catalog-and-layer_docsjs)
- [The mesh LOD index](#the-mesh-lod-index)
- [`export-debug-map`: projections, layers, formats, parity](#export-debug-map-projections-layers-formats-parity)
- [`export-rerun` and its optional dependency](#export-rerun-and-its-optional-dependency)
- [Default output paths: CLI versus browser](#default-output-paths-cli-versus-browser)
- [Per-layer reference](#per-layer-reference)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## The debug cache: purpose and scope

`src/magic_geo/debug_export.py` converts a world payload (the same dict `generate` writes to `world.json` / `.mgeo`) into a directory of columnar tables, indexed JSONL, binary mesh buffers, and a machine-readable catalog. The module docstring (`src/magic_geo/debug_export.py:1`) states the design intent explicitly: the classifier is **generic on purpose** — record families are discovered from payload *shape* (scalar list-of-dicts, per-stage `cell_ids` + `*_by_cell` histories, nested event records, dict sections) rather than from hardcoded column lists, so new engine or enricher output is picked up without editing the exporter, and *anything skipped is recorded in the manifest rather than dropped silently*.

| Property | Value | Source |
| --- | --- | --- |
| Format name | `magic-geo-debug-cache` | `src/magic_geo/debug_export.py:30` |
| Format version | `1` (int; strictly compared) | `src/magic_geo/debug_export.py:31` |
| Entry point | `export_debug_cache(world, out_dir, *, source_path=None, include_vtu=True, elevation_exaggeration=30.0)` | `src/magic_geo/debug_export.py:819` |
| Hard precondition | `world["cells"]` must be a non-empty list, else `ValueError("world payload has no cells; generate with output.include_cells enabled")` | `src/magic_geo/debug_export.py:831` |
| Mesh precondition | cell ids must be contiguous `0..n-1`, else `ValueError("debug export requires contiguous cell ids 0..n-1")` | `src/magic_geo/debug_export.py:600` |
| Parquet compression | `zstd` via `pyarrow.parquet.write_table` | `src/magic_geo/debug_export.py:111` |
| Categorical cardinality limit | `_CATEGORY_LIMIT = 64` | `src/magic_geo/debug_export.py:34` |
| Vector fields expanded to scalars | `position_3d`, `normal_3d` | `src/magic_geo/debug_export.py:35` |
| Optional dependency group | `magic-geo[debug]` → `pyarrow>=19`, `duckdb>=1.2`, `fastapi>=0.115`, `uvicorn[standard]>=0.34` | `pyproject.toml:19` |

The cache version is independent of the package version, the HTTP API version, and the generated-world schema version (`docs/debugger.md:188`). The reader (`_DebugCache`) rejects a missing or different `format`/`version` rather than attempting a best-effort read (`src/magic_geo/debug_server.py:118`).

### CLI invocation

```bash
magic-geo export-debug --world runs/world.json --output runs/debug --no-vtu
magic-geo export-debug --world runs/world.json --vtu --elevation-exaggeration 30
```

| Flag | Type | Default | Meaning | Source |
| --- | --- | --- | --- | --- |
| `--world` / `-w` | existing path | required | Generated `.json` or `.mgeo` world | `src/magic_geo/cli/commands/export.py:166` |
| `--output` / `-o` | path | `<world dir>/debug` | Debug cache directory | `src/magic_geo/cli/commands/export.py:167`, default applied at `:187` |
| `--vtu` / `--no-vtu` | bool | `True` | Also emit ParaView `.vtu` stage files and `world.pvd` | `src/magic_geo/cli/commands/export.py:171` |
| `--elevation-exaggeration` | float, `min=1.0` | `30.0` | Radial elevation exaggeration for `.vtu` geometry only | `src/magic_geo/cli/commands/export.py:175` |

On success the command prints `Wrote <out_dir> | layers=… stage_histories=… families=… mesh_vertices=… mesh_triangles=…` (`src/magic_geo/cli/commands/export.py:200`). A missing optional dependency exits `2` with `pip install 'magic-geo[debug]'` (`:184`); a `ValueError` from the exporter also exits `2` (`:196`).

---

## On-disk directory layout

```
<cache>/
  manifest.json                              # the catalog; also the revision anchor
  sections.json                              # every dict-valued (and non-record list) world key
  world.pvd                                  # only with --vtu and a non-empty water-budget history
  tables/
    cells.parquet                            # one row per cell, scalar columns only
    cells_monthly.parquet                    # only when 12-length numeric arrays exist
    cell_details_index.json                  # {"<cell_id>": byte offset} into events/cell_details.jsonl
    <stem>_stage_cells.parquet               # one per stage history
    <stem>_stages.parquet                    # one per stage history
    <stem>.parquet                           # flat record family
    <stem>.scalars.parquet                   # nested record family scalar sidecar
  events/
    cell_details.jsonl                       # one JSON object per cell, non-scalar fields
    <stem>_stage_extras.jsonl                # skipped per-cell arrays + non-scalar stage metadata
    <stem>.jsonl                             # nested record family, full records
  mesh/
    positions.f32  cell_ids.u32  indices.u32
    pos_equirect.f32  pos_mollweide.f32
    mesh.json                                # copy of manifest.mesh
  vtu/
    stage_0000.vtu  stage_0001.vtu  …        # only with --vtu
```

### `<stem>`: the storage-name mapping

Arbitrary world keys become one collision-resistant filename via `_storage_stem` (`src/magic_geo/debug_export.py:38`):

| Step | Rule | Source |
| --- | --- | --- |
| 1 | Replace every run of characters outside `[A-Za-z0-9._-]` with `_` | `:42` |
| 2 | Strip leading/trailing `.`, `_`, `-`; truncate to 72 characters; fall back to `entry` if empty | `:42` |
| 3 | Append `-` + the **full 64-hex-character SHA-256** of the original key (UTF-8, `surrogatepass`) | `:43` |

So `hydrologic_water_budget_history` becomes `hydrologic_water_budget_history-<64 hex chars>_stage_cells.parquet`. Only `manifest.json`, `sections.json`, `world.pvd`, the `cells*`/`cell_details*` files, and the five mesh buffers have stable, guessable names. **Always resolve family and history paths through the manifest**, never by reconstructing a stem.

### What the reader validates

`_DebugCache._validate_manifest_files` (`src/magic_geo/debug_server.py:173`) checks, before any query runs, that every manifest-referenced path is a non-empty relative string, resolves inside the cache root, and is an existing regular file: the cells parquet plus optional `details_jsonl`/`details_index`; the monthly parquet when `monthly` is present; both parquets and the optional `extras_jsonl` of every stage history; at least one of `parquet` / `scalars_parquet` / `jsonl` per family; all five mesh buffers; and the ParaView `pvd` when `paraview` is present. It also requires every name in `manifest["sections"]` to exist as a key in `sections.json` (`:215`). `mesh/mesh.json` is written but is **not** in the validated set — the buffer catalog is read from `manifest["mesh"]["buffers"]`.

---

## `manifest.json` field reference

`manifest.json` is written last, with `json.dumps(..., allow_nan=False, indent=2, sort_keys=True)` (`src/magic_geo/debug_export.py:914`). Every value passes through `_json_safe` first (`:51`), which rewrites non-finite floats to `null` recursively — so the manifest is standards-compliant JSON with no `NaN`/`Infinity` tokens.

### Top-level keys

| Key | Type | Always present | Meaning | Source |
| --- | --- | --- | --- | --- |
| `format` | string | yes | Literal `"magic-geo-debug-cache"` | `:841` |
| `version` | int | yes | Literal `1` | `:842` |
| `world` | object | yes | `{name, schema_version, mesh_backend, generation_scope, cell_count}`; `generation_scope` defaults to `"full"`, `cell_count` is `len(cells)` | `:843`–`:849` |
| `layers` | array | yes | Every renderable layer descriptor (five kinds, below) | `:850`, appended at `:269`, `:311`, `:461`, `:478` |
| `stage_histories` | object | yes (may be `{}`) | Keyed by the original world key | `:851`, `:443` |
| `families` | object | yes (may be `{}`) | Keyed by the original world key | `:852`, `:537`/`:566` |
| `sections` | array of string | yes | Sorted names, mirrors the keys of `sections.json` | `:853`, `:891` |
| `scalars` | object | yes | Every **top-level scalar** world key (str/int/float/bool/None) | `:854`, `:873` |
| `skipped_sections` | object | yes | `{world key: reason}` for outputs no exporter branch handled | `:855`, `:878`, `:886` |
| `cells` | object | yes | Cells-table descriptor (below) | `:234`, extended at `:262` |
| `mesh` | object | yes | Mesh buffer catalog (below); identical content to `mesh/mesh.json` | `:671` |
| `source` | object | only when `source_path` is passed | `{path, bytes, sha256}` of the world file actually read | `:857`–`:863` |
| `monthly` | object | only when at least one 12-length numeric array field exists | Monthly long-table descriptor | `:293` |
| `simulation_clock` | object | only when `world["simulation_clock"]` is a dict | 8 selected keys, see below | `:894`–`:908` |
| `paraview` | object | only when `--vtu` and at least one VTU stage was written | `{pvd, stage_count, elevation_exaggeration}` | `:808`–`:812` |

### `manifest.cells`

| Field | Type | Meaning | Source |
| --- | --- | --- | --- |
| `parquet` | string | `"tables/cells.parquet"` | `:235` |
| `row_count` | int | Rows written | `:236` |
| `fields` | array of `{name, dtype}` | Column order as written; `dtype` ∈ `str`, `bool`, `int`, `float` | `:237` |
| `skipped_fields` | object | `{cell key: reason}` for keys that produced **no** Parquet column | `:238` |
| `skipped_layers` | object | `{column: reason}` for columns that exist in Parquet but produced **no** layer | `:239` |
| `details_jsonl` | string | `"events/cell_details.jsonl"` — present only when `detail_fields` is non-empty | `:264` |
| `details_index` | string | `"tables/cell_details_index.json"` — same condition | `:265` |
| `detail_fields` | array of string | Keys stored per cell in the JSONL sidecar, in first-seen order | `:266` |

### `manifest.monthly`

| Field | Type | Meaning | Source |
| --- | --- | --- | --- |
| `parquet` | string | `"tables/cells_monthly.parquet"` | `:294` |
| `row_count` | int | `cell_count × 12` | `:295` |
| `fields` | array of string | **Sorted** monthly column names | `:296` |
| `skipped_layers` | object | `{column: "no finite values (column kept in cells_monthly.parquet)"}` | `:297`, `:309` |

### `manifest.stage_histories[<world key>]`

| Field | Type | Meaning | Source |
| --- | --- | --- | --- |
| `stage_count` | int | `len(records)` | `:444` |
| `stage_cells_parquet` | string | `tables/<stem>_stage_cells.parquet` | `:445`, `:429` |
| `stages_parquet` | string | `tables/<stem>_stages.parquet` | `:446`, `:430` |
| `per_cell_fields` | array of string | Sorted names of `*_by_cell` fields that became typed columns | `:447` |
| `row_count` | int | Rows in the stage-cells parquet (`Σ len(cell_ids)`) | `:448` |
| `stages` | array of object | Per-stage scalar metadata dicts, each carrying at least `stage_idx` | `:449`, built at `:391` |
| `skipped_layers` | object | Per-cell fields that produced no layer, with reason | `:450`, `:459`, `:475` |
| `skipped_per_cell_fields` | object | `*_by_cell` fields that produced no column | `:451`, `:377` |
| `skipped_summary_fields` | object | Stage metadata that produced no summary column | `:452`, `:425`, `:427` |
| `extras_jsonl` | string | `events/<stem>_stage_extras.jsonl` — present only when something was skipped | `:503` |

### `manifest.families[<world key>]`

| `kind` | Extra fields | Condition | Source |
| --- | --- | --- | --- |
| `"parquet"` | `parquet`, `row_count` | Every value in every record is scalar | `:531`–`:541` |
| `"jsonl"` | `jsonl`, `row_count` | At least one non-scalar value, and fewer than 3 scalar fields *or* fewer than 2 records | `:550`–`:554` |
| `"jsonl+scalars"` | `jsonl`, `row_count`, `scalars_parquet`, `scalar_row_count` | Nested **and** ≥ 3 scalar fields **and** ≥ 2 records | `:557`–`:565` |

### `manifest.simulation_clock`

Copied verbatim (with `.get`, so missing keys become `null`) from `world["simulation_clock"]` (`src/magic_geo/debug_export.py:896`): `clock_type`, `time_unit`, `stage_count`, `initial_stage_id`, `current_stage_id`, `final_stage_id`, `feedback_recompute_count`, `hydrologic_water_budget_recompute_count`.

### Every skip reason the exporter can emit

| Manifest location | Exact reason string | Emitted when | Source |
| --- | --- | --- | --- |
| `cells.skipped_fields` | `all null` | Every cell has `None` for that key | `:196` |
| `cells.skipped_fields` | `non-scalar field retained in indexed cell details` | List/dict-valued field that is not a uniform 12-length numeric array | `:217` |
| `cells.skipped_layers` | `more than 64 distinct values (column kept in cells.parquet)` | String/bool column above `_CATEGORY_LIMIT` | `:230` |
| `cells.skipped_layers` | `no finite values (column kept in cells.parquet)` | Numeric column with no finite value | `:232` |
| `monthly.skipped_layers` | `no finite values (column kept in cells_monthly.parquet)` | Monthly column with no finite value | `:309` |
| `stage_histories[*].skipped_layers` | `no finite values (column kept in the stage-cells parquet)` | Numeric per-cell stage column with no finite value | `:459` |
| `stage_histories[*].skipped_layers` | `more than 64 categories (column kept in stage parquet)` | String/bool per-cell stage column above the limit | `:474` |
| `stage_histories[*].skipped_per_cell_fields` | `empty or mixed non-scalar stage field retained in stage extras` | `_field_kind` returned `None` or `mixed` | `:377` |
| `stage_histories[*].skipped_summary_fields` | `mixed scalar types retained in manifest stage metadata` | A stage summary key holds mixed scalar types across stages | `:425` |
| `stage_histories[*].skipped_summary_fields` | `non-scalar stage metadata retained in stage extras` | A non-`_by_cell`, non-`cell_ids` stage key is not scalar | `:427` |
| `skipped_sections` | `empty list` | A top-level world key is `[]` | `:878` |
| `skipped_sections` | `unhandled type <typename>` | A top-level world value is neither scalar, dict, nor list | `:886` |

Nothing that gets a skip reason is lost: string columns above the category limit stay in `cells.parquet` and are reachable via `/api/cell/{id}`; non-scalar cell fields move to `events/cell_details.jsonl`; skipped stage arrays move to the stage-extras JSONL.

### Layer descriptor variants

Every entry of `manifest["layers"]` carries `id`, `source`, `name`, `kind`. The five variants:

| `kind` | `id` shape | `source` | Extra fields | Emitted by |
| --- | --- | --- | --- | --- |
| `numeric` | `cells/<column>` | `cells` | `stats {min, max, p2, p98}` | `:146`, `:226` |
| `categorical` | `cells/<column>` | `cells` | `categories []` (sorted, ≤ 64) | `:151`, `:226` |
| `numeric_monthly` | `monthly/<column>` | `cells_monthly` | `month_count: 12`, `stats` | `:311`–`:320` |
| `numeric_stage` | `<history key>/<field>` | `<history key>` | `stage_count`, `stats` | `:461`–`:470` |
| `categorical_stage` | `<history key>/<field>` | `<history key>` | `stage_count`, `categories []` | `:478`–`:487` |

`stats` is computed by `_numeric_stats` (`:115`) over **finite values only**, sorted; `p2`/`p98` are nearest-rank picks at `int(0.02 * (n-1))` and `int(0.98 * (n-1))` — not interpolated percentiles. A column with zero finite values yields no layer at all.

---

## Parquet table families and column schemas

Column typing is decided by `_field_kind` (`src/magic_geo/debug_export.py:67`), which walks the values, ignores `None`, and returns `str` / `bool` / `int` / `float` / `mixed` / `None` (empty). `int` + `float` widens to `float`; any other disagreement, or any non-scalar value, is `mixed`. Arrow types are `pa.string()`, `pa.bool_()`, `pa.int64()`, `pa.float64()` (`:93`).

### `tables/cells.parquet`

One row per cell, in payload order.

| Column group | Columns | dtype | Notes | Source |
| --- | --- | --- | --- | --- |
| Scalar cell keys | every key whose `_field_kind` is `str`/`bool`/`int`/`float` | as classified | Emitted in **first-seen key order** across all cells | `:165`–`:201` |
| Position expansion | `position_3d_x`, `position_3d_y`, `position_3d_z` | `float` | From the 3-element `position_3d` list; `None` when the value is not a 3-list | `:186`–`:192` |
| Normal expansion | `normal_3d_x`, `normal_3d_y`, `normal_3d_z` | `float` | Same rule for `normal_3d` | `:186`–`:192` |

`id` is the join key: the server queries `SELECT id, "<column>" FROM read_parquet(?)` for cell layers (`src/magic_geo/debug_server.py:316`) and `SELECT * FROM read_parquet(?) WHERE id = ?` for the cell inspector (`:363`). Note that the raw `position_3d` / `normal_3d` lists are **also** added to `detail_fields` (`:186`), so the unexpanded vectors remain retrievable from the JSONL sidecar.

### `tables/cells_monthly.parquet`

Long form — one row per `(cell, month)`.

| Column | dtype | Meaning | Source |
| --- | --- | --- | --- |
| `cell_id` | `int` | `int(cell["id"])` | `:272`, `:280` |
| `month` | `int` | `0`–`11` | `:279`, `:281` |
| `<field>` | `float` | One column per detected monthly field; `None` where the array slot was `None` | `:283`–`:290` |

A field qualifies as monthly only when **every** non-`None` value is a list of exactly 12 items whose entries are `None` or numeric (`src/magic_geo/debug_export.py:205`). Ragged or partly non-numeric arrays fall through to `skipped_fields` and the cell-details sidecar instead of being partially flattened — `docs/debugger.md:183` records this as a deliberate fix. Detection is purely shape-based; the exporter does not consult field names.

### `tables/<stem>_stage_cells.parquet`

Built from records shaped as `cell_ids` + one or more `*_by_cell` parallel arrays; `_is_stage_history` (`:327`) requires the **first** record to have a list `cell_ids` and at least one `_by_cell` key.

| Column | dtype | Meaning | Source |
| --- | --- | --- | --- |
| `stage_idx` | `int` | 0-based record index | `:382`, `:408` |
| `cell_id` | `int` | From that record's `cell_ids` | `:382`, `:409` |
| `<field>` | classified across **all** stages | One column per `<field>_by_cell` whose flattened kind is scalar | `:358`–`:386`, `:410`–`:415` |

Field typing is decided once over the concatenation of every stage (`:358`–`:379`), so a field that is numeric in one stage and string in another becomes `mixed` and is diverted wholesale to stage extras. When a record's `<field>_by_cell` is missing or has the wrong length, that stage contributes `None` for the column instead of misaligning rows (`:412`).

### `tables/<stem>_stages.parquet`

One row per stage, holding the scalar metadata that sits alongside the per-cell arrays.

| Column | dtype | Meaning | Source |
| --- | --- | --- | --- |
| `stage_idx` | `int` | 0-based record index | `:342`, `:392` |
| `<key>` | classified across all stages | Every non-`cell_ids`, non-`*_by_cell` **scalar** record key | `:393`–`:404` |

Keys first seen at stage *k* are back-filled with `None` for stages `0..k-1` (`:398`) and every column is padded to equal length after each stage (`:402`). Keys whose values disagree in scalar type across stages are dropped from the table and recorded in `skipped_summary_fields` — but their values survive in `manifest.stage_histories[*].stages[i]`, which records every scalar key per stage (`:396`).

### `tables/<stem>.parquet` and `tables/<stem>.scalars.parquet` (families)

A **family** is any top-level world key holding a non-empty list where every element is a dict and the list is not a stage history (`:881`).

| Table | Columns | Condition | Source |
| --- | --- | --- | --- |
| `tables/<stem>.parquet` | Every key whose flattened kind is `str`/`bool`/`int`/`float` | `flat` — no record contained a non-scalar value | `:519`, `:531` |
| `tables/<stem>.scalars.parquet` | Same scalar-column selection | Nested family with ≥ 3 scalar fields and ≥ 2 records | `:557` |

Column presence is union-based: a key seen on any record becomes a column with `None` for records lacking it (`:521`).

The family the rest of the system depends on by name is **`cell_adjacency_edges`**: the server reads it for cell-inspector adjacency (`src/magic_geo/debug_server.py:388`) and for `/api/plate-boundaries` (`:486`), where it selects `boundary_segment_start_lat_deg`, `boundary_segment_start_lon_deg`, `boundary_segment_end_lat_deg`, `boundary_segment_end_lon_deg` `WHERE plate_boundary` (`:492`). `export-debug-map --plates` and `export-rerun` read the same fields (`src/magic_geo/debug_map_export.py:1174`, `src/magic_geo/debug_rerun.py:156`). If that family is nested rather than flat, `plate_boundary_segments()` returns `[]` because it requires the `parquet` key specifically (`src/magic_geo/debug_server.py:488`).

---

## JSONL sidecars and the cell-details index

| File | One line per | Content | Encoding | Source |
| --- | --- | --- | --- | --- |
| `events/cell_details.jsonl` | cell, in payload order | `{key: value}` restricted to `detail_fields` | compact separators, `ensure_ascii=False`, UTF-8, non-finite floats → `null` | `:245`–`:256` |
| `events/<stem>_stage_extras.jsonl` | stage | `stage_idx`, `cell_ids`, every skipped `<field>_by_cell`, every non-scalar stage metadata key | same | `:491`–`:502` |
| `events/<stem>.jsonl` | record | The complete record, `sort_keys=True` | `_json_dumps` | `:546`–`:549` |

`tables/cell_details_index.json` maps `str(cell_id)` → the **byte offset** of that cell's line, captured with `handle.tell()` while writing (`:250`), and is written with sorted keys and compact separators (`:258`). The reader loads it once, caches it, then `seek`s and `readline`s a single record (`src/magic_geo/debug_server.py:341`–`:352`). `cell_id` comes from `int(cell.get("id", row_index))`, so a cell without `id` is indexed by its row position (`:249`).

---

## Mesh assets and their binary layouts

`_export_mesh` (`src/magic_geo/debug_export.py:599`) triangulates each cell as a **fan**: one center vertex plus one vertex per `boundary_ring` point, then `ring_count` triangles `(center, ring[i], ring[(i+1) % ring_count])` (`:640`). Cells whose `boundary_ring` is absent or shorter than 3 points contribute nothing and increment `cells_without_ring` (`:615`–`:617`).

| Per-cell geometry decision | Rule | Source |
| --- | --- | --- |
| Center 3D position | Normalized `position_3d` when it is a 3-list (dividing by its norm, or `1.0` if the norm is zero); otherwise `lat_deg`/`lon_deg` → unit XYZ | `:620`–`:625` |
| Ring 3D positions | `_xyz_from_lat_lon(lat, lon)` on the **raw** ring longitude | `:636`, `:573` |
| Center 2D positions | equirect `(lon/180, lat/90)`; mollweide from the center lat/lon | `:630`–`:631` |
| Ring 2D positions | Longitude first wrapped to the branch nearest the cell center via `_wrap_lon_near` (`anchor + ((lon - anchor + 180) mod 360) - 180`), then projected | `:635`, `:638`–`:639`, `:595` |
| Mollweide solve | `_mollweide_theta`: Newton on `2θ + sin 2θ = π sin φ` to convergence (step < 1e-14, at most 50), starting near the poles (`|φ| > 1.4`) from the asymptotic solution `π/2 − θ ≈ (3πδ²/8)^(1/3)`, δ = π/2 − |φ|; exact at the poles. The earlier fixed 8-step solve stalled next to the poles (0.1° wrong at 89.9°); the latitude round trip is now within 2·10⁻¹¹° everywhere | `debug_export.py` `_mollweide_theta` |

### Binary buffer layout

All five buffers are written with Python `array.tobytes()` and are strictly parallel — index *i* of `positions`, `cell_ids`, `pos_equirect`, and `pos_mollweide` describe the same vertex.

| File | `array` typecode | dtype | Components | Bytes per element | Element count | Contents |
| --- | --- | --- | --- | --- | --- | --- |
| `mesh/positions.f32` | `f` | `float32` | 3 | 12 per vertex | `vertex_count` | Unit-sphere XYZ in the planet frame |
| `mesh/cell_ids.u32` | `I` | `uint32` | 1 | 4 per vertex | `vertex_count` | Owning cell id for each vertex |
| `mesh/indices.u32` | `I` | `uint32` | 3 | 12 per triangle | `triangle_count` | Triangle list into the vertex arrays |
| `mesh/pos_equirect.f32` | `f` | `float32` | 2 | 8 per vertex | `vertex_count` | `(lon/180, lat/90)`, ring longitudes wrapped near the cell center |
| `mesh/pos_mollweide.f32` | `f` | `float32` | 2 | 8 per vertex | `vertex_count` | Normalized Mollweide `(x, y)` of the same wrapped coordinates |

Declared in `manifest["mesh"]["buffers"]` (`:662`–`:668`) and duplicated to `mesh/mesh.json` (`:670`).

### `manifest.mesh` / `mesh.json`

| Field | Type | Meaning | Source |
| --- | --- | --- | --- |
| `vertex_count` | int | `len(cell_ids)` — total fan vertices | `:657` |
| `triangle_count` | int | `len(indices) // 3` | `:658` |
| `cell_count` | int | Number of cells considered (`len(by_id)`), **not** the number rendered | `:659` |
| `cells_without_ring` | int | Cells excluded for a missing/short `boundary_ring` | `:660` |
| `endianness` | string | Literal `"little"` | `:661` |
| `buffers` | object | `{name: {file, dtype, components}}` for the five buffers | `:662` |

The Python reader in `export-debug-map` byteswaps when `sys.byteorder != "little"` (`src/magic_geo/debug_map_export.py:689`) and rejects a buffer whose byte length is not divisible by its item size (`:686`). The writer, however, uses host byte order unconditionally, and `"endianness": "little"` is a hardcoded literal rather than a probe (`src/magic_geo/debug_export.py:661`) — on a big-endian host the declared value would not match the bytes. No big-endian handling on the write path exists in source.

### Consumers

The browser fetches all five buffers through `GET /mesh/<name>?revision=…` and builds a single merged indexed `BufferGeometry` with attributes `position`, `aPosEq`, `aPosMo`, `aCellId` (`src/magic_geo/debug_ui/app.js:363`–`:391`). Layer values are uploaded separately into an R32F `DataTexture` of width `ceil(sqrt(cell_count))` and height `ceil(cell_count / width)`, indexed by cell id with nearest filtering (`:393`–`:400`), so **switching layers never rebuilds geometry**. The mesh route materializes bytes while the cache-manager read lock is held, precisely because a cache directory can be atomically replaced under a stable URL (`src/magic_geo/debug_server.py:1191`–`:1198`).

---

## The ParaView VTU option

`_write_vtu_stages` (`src/magic_geo/debug_export.py:679`) runs only when `include_vtu` is true. It returns immediately (writing nothing, and leaving `manifest["paraview"]` absent) when `world["hydrologic_water_budget_history"]` is not a non-empty list, when there are no cells (`:688`), or when no cell has a ring of ≥ 3 points (`:698`).

| Aspect | Behavior | Source |
| --- | --- | --- |
| One file per stage | `vtu/stage_%04d.vtu`, indexed by the water-budget history record order | `:767` |
| Cell type | VTK type `7` (polygon) for every cell | `:786` |
| Geometry | Ring vertices only — no fan center; `_xyz_from_lat_lon` per ring point | `:696` |
| Radial exaggeration | `1.0 + elevation_exaggeration * elevation / (radius_km * 1000.0)` | `:738` |
| Planet radius | `world["planet_parameters"]["radius_km"]` when finite and positive, else `6371.0` | `:701`–`:707` |
| Elevation source | That stage's `elevation_m_by_cell`, mapped through the record's `cell_ids`; missing / non-finite → `0.0` | `:711`–`:737` |
| CellData arrays | One `Float32` array per `*_by_cell` key whose `_field_kind` is `int`/`float`, named with `_by_cell` stripped, sorted | `:714`–`:720`, `:748` |
| CellData formatting | `%.6f`; missing rows → `0`; non-finite → the literal `nan` | `:753`–`:760` |
| Collection | `world.pvd`, one `<DataSet timestep="i" … file="vtu/stage_XXXX.vtu"/>` per stage | `:797`–`:807` |
| Manifest record | `{pvd: "world.pvd", stage_count, elevation_exaggeration}` | `:808` |

All arrays are ASCII-formatted (`format="ascii"`), which makes VTU by far the bulkiest part of a cache. Open with:

```bash
magic-geo export-debug --world runs/world.json --output runs/debug --vtu
paraview runs/debug/world.pvd
```

The exaggeration is a **display transform only** — it changes VTU point coordinates and nothing else. The mesh buffers, the Parquet tables, and every layer value are unaffected.

---

## Layer addressing and what a "layer" is

A **layer** is one scalar value per cell that a viewer can color the globe by (`docs/layers_reference.md:13`). The exporter discovers layers generically from payload shape; there is no curated list of renderable fields.

| `kind` | Address (`id`) | Time axis | Value domain | Color treatment |
| --- | --- | --- | --- | --- |
| `numeric` | `cells/<column>` | none | float | `numericScale()`: Viridis, Cool–warm (signed), Terrain (elevation crossing 0 m) or identifier colours, over `p2..p98` |
| `categorical` | `cells/<column>` | none | category index | one guide colour per class (semantic where recognized, e.g. ocean blue; see `palettes.js`) |
| `numeric_monthly` | `monthly/<column>` | month `0`–`11` | float | as `numeric`, scale fixed across all 12 months |
| `numeric_stage` | `<history key>/<field>` | stage `0`–`stage_count-1` | float | as `numeric`, scale fixed across all stages |
| `categorical_stage` | `<history key>/<field>` | stage | category index | one guide colour per class (semantic where recognized) |

Because a history key becomes the `source` verbatim, ids can contain `/` inside the history name; the HTTP route therefore declares `{layer_id:path}` (`src/magic_geo/debug_server.py:1137`) and the browser URL-encodes the id (`src/magic_geo/debug_ui/app.js:331`).

### How a layer is resolved to values

`_DebugCache.layer_values(layer_id, stage, month)` (`src/magic_geo/debug_server.py:277`) starts from an all-NaN array of length `cell_count` and fills it:

| Layer kind | Query | Range check | Source |
| --- | --- | --- | --- |
| `numeric_monthly` | `SELECT cell_id, "<name>" FROM read_parquet(?) WHERE month = ?` | `0 ≤ month < month_count` else HTTP 400 | `:286`–`:297` |
| `*_stage` | `SELECT cell_id, "<name>" FROM read_parquet(?) WHERE stage_idx = ?` | `0 ≤ stage < stage_count` else HTTP 400 | `:298`–`:310` |
| everything else | `SELECT id, "<name>" FROM read_parquet(?)` | — | `:311`–`:316` |

Categorical layers are then converted to the **index into `layer["categories"]`**, with `-1` for a value that is not in the list (`:318`–`:324`); numeric layers keep their float value, with non-finite rewritten to NaN (`:326`–`:330`). Column names are quoted as DuckDB identifiers before interpolation, and a NUL in a field name is rejected (`docs/debugger.md:199`).

### The three "role, units, doc status" axes

These are viewer-side interpretations layered on top of the exporter's `kind`, all resolved by `src/magic_geo/debug_ui/layer_docs.js` from the **bare field name** (never the `source/` prefix).

**Role** — assigned by the first matching rule in `PATTERN_RULES` (`layer_docs.js:59`), with a categorical fallback:

| Role | Trigger | Source |
| --- | --- | --- |
| `identifier` | `name === 'id'`; or `*_id`, `flow_to`, `spill_to`, `glacier_flow_to`, `*_cell_id`, `*_basin_id` | `:62`, `:66` |
| `provenance` | `initial_*` | `:71` |
| `accumulator` | `cumulative_*` | `:76` |
| `diagnostic` | `*_edge_count`, `boundary_vertex_count`, `*neighbor_boundary_segment_count`; `*_event_count`, `*_transfer_count`, `*_path_count`; name contains `residual` or `consistency` | `:83`, `:88`, `:95` |
| `classification` | `*_class`, `*_regime`, `*_type`, `*_policy`, `*_stage`; or any `categorical*` kind that matched nothing else | `:100`, `:388` |
| `index` | `*_index` | `:105` |
| `ratio` | `*_fraction`, `*_factor` | `:110` |
| `seasonal` | `*_months` | `:115` |
| `measurement` | default | `:372` |

**Units** — `EXACT_UNITS` first (only `crust_density` → `g/cm³`, `layer_docs.js:20`), then the longest-suffix-first `UNIT_RULES` list (`:24`): `_km3_y`, `_m3_s`, `_m_s`, `_mm_y`, `_m_y`, `_w_m2`, `_km2`, `_km3`, `_km`, `_hpa`, `_kpa`, `_pa`, `_ka`, `_ma`, `_ph`, `_deg`, `_c`, `_m3`, `_m2`, `_mm`, `_m_per_step`, `_years`, `_months`, `_count`, `_fraction`, `_index`, `_m`. There is deliberately **no bare `_y` rule**, because it would mislabel coordinate fields such as `position_3d_y` and `s2_like_y` as per-year quantities (`:52`–`:54`). Categorical layers with no suffix match report the unit `category` (`:436`). `debug_map_export.py` carries the same 27 suffixes in the same order, mapped to the same unit strings, for the CLI prompt (`_UNIT_RULES`, `src/magic_geo/debug_map_export.py:59`–`:87`, consumed by `_infer_unit` at `:292`–`:298`); the Python table is `(suffix, unit)` pairs and drops the JS gloss sentences, and `crust_density` is special-cased inline rather than through an `EXACT_UNITS` map.

**Doc status** — `docStatus(layer)` (`layer_docs.js:476`) reports which documentation tier resolved the layer:

| Tier | Condition | Renamed to (in the generated reference) |
| --- | --- | --- |
| `curated` | `CURATED[name]` exists | `curated` |
| `pattern` | Any `PATTERN_RULES` rule matches, or the kind starts with `categorical` | `convention` |
| `unit` | Only `inferUnit(name)` matched | `unit` |
| `generated` | Pure fallback ("inspect a cell for context") | `generated` |

The rename happens in `scripts/gen_layers_reference.mjs:175` (`STATUS_LABEL`).

---

## The layer catalog and `layer_docs.js`

### Server side

`GET /api/catalog` (`src/magic_geo/debug_server.py:1119`) is a pure projection of the manifest — it invents nothing:

| Key | Manifest source |
| --- | --- |
| `world` | `manifest["world"]` |
| `scalars` | `manifest["scalars"]` |
| `layers` | `manifest["layers"]` |
| `stage_histories` | `manifest["stage_histories"]` |
| `families` | `manifest["families"]` |
| `sections` | `manifest["sections"]` |
| `skipped_sections` | `manifest["skipped_sections"]` |
| `cells` | `manifest["cells"]` |
| `monthly` | `manifest["monthly"]` (may be `null`) |
| `mesh` | `manifest["mesh"]` |

### Client side

`src/magic_geo/debug_ui/layer_docs.js` resolves documentation in four tiers of decreasing specificity (module header, `:1`–`:16`): exact `CURATED[name]`, then suffix/prefix `PATTERN_RULES`, then `SOURCE_DOCS` family prose, then a generated fallback built from `kind` + inferred unit. Its exports:

| Export | Returns | Source |
| --- | --- | --- |
| `describeLayer(layer)` | `{title, unit, role, roleBadge, description, family, familyDoc, stats{min,max,p2,p98 formatted}, categories, kind, notes[]}` | `:365` |
| `layerTooltip(layer)` | `"<id> [<unit>] — <first sentence>"` | `:457` |
| `searchTerms(layer)` | Role, unit, family, description, and category names joined — what the `/` filter matches beyond `source name` | `:465` |
| `docStatus(layer)` | `'curated' \| 'pattern' \| 'unit' \| 'generated'` | `:476` |
| `docsCoverage(layers)` | `{counts: {curated, pattern, unit, generated, total}, byRole: {kind: n}}` | `:486` |
| `UI_GUIDE` | The seven-section help overlay text | `:498` |
| `KEY_REFERENCE` | The seven keyboard bindings | `:560` |

`SOURCE_DOCS` (`:313`) supplies a title and paragraph for exactly four sources: `cells`, `cells_monthly`, `hydrologic_water_budget_history`, `numeric_depression_correction_history`. `ROLE_BADGES` (`:333`) supplies a short pill label and hint per role. `describeLayer` also attaches contextual notes: a stage-count note for `*_stage` layers, a month-count note for `numeric_monthly`, and "Values are labels, not magnitudes. Colours repeat every 18 ids; −1 means none and is drawn in the no-data grey." for `identifier` (`:423`–`:432`).

### Cross-module reuse by the CLI

`debug_map_export.py` does **not** duplicate the prose catalog. `_load_web_curated_descriptions()` (`src/magic_geo/debug_map_export.py:103`) reads the packaged `debug_ui/layer_docs.js`, splits on the literal `const CURATED = {` … `\n};`, and `ast.literal_eval`s each single-line `identifier: 'string',` entry. If the file cannot be read or the block cannot be located, it falls back to `_FALLBACK_CURATED_DESCRIPTIONS` — seven entries covering `elevation_m`, `temperature_c`, `precipitation_mm_y`, `flow_accumulation`, `flow_to`, `is_water`, `biome` (`:89`–`:100`). The comment at `:106` states the reason plainly: the catalog stays canonical in `layer_docs.js` because that module also owns the interactive help, and the one-entry-per-line convention is what lets the CLI reuse the exact prose instead of maintaining a second 100+ field catalog.

The same file also carries `_FAMILY_DESCRIPTIONS` (`:134`) — prose for the same four sources, worded almost but not exactly identically to `SOURCE_DOCS`; unknown sources fall back to the raw source name (`:346`).

`scripts/gen_layers_reference.mjs` imports `describeLayer`, `docStatus`, and `docsCoverage` directly from `layer_docs.js` (`:24`) and runs them over a real `manifest.json`, which is why `docs/layers_reference.md` cannot drift from the in-app docs card.

---

## The mesh LOD index

`src/magic_geo/mesh_lod.py` builds a spherical **cube-face quadtree** over cell centroids. It is a *generation-time world enrichment*, called from `api.py:200` (`generate_world`) and `api.py:308` (the geo-only path) — not a viewer or exporter feature.

| Aspect | Value | Source |
| --- | --- | --- |
| Index name | `cube_quadtree_v0` | `src/magic_geo/mesh_lod.py:167` |
| Faces | `+x, -x, +y, -y, +z, -z` (6) | `:7` |
| Max level | `max(1, min(6, ceil(log_4(max(1.0, cell_count / 6)))))` | `:10`–`:14` |
| Levels emitted | `0 .. max_level` inclusive | `:87` |
| Tile id | `face * 4^level + y * 2^level + x` | `:48` |
| Tile code | `L{level}F{face}X{x}Y{y}` | `:53` |

`world["mesh_lod"]` holds `index`, `description`, `max_level`, `root_face_count`, `level_summaries[]`, and `tiles[]` (`:166`–`:173`).

| Tile record field | Meaning | Source |
| --- | --- | --- |
| `level`, `tile_id`, `tile_code`, `parent_tile_id` | Address and parent link (`-1` at level 0) | `:96`–`:99` |
| `face`, `face_id`, `x`, `y` | Cube face name/index and tile coordinates | `:100`–`:103` |
| `cell_count`, `child_tile_count` | Occupancy and number of occupied children | `:104`, `:144` |
| `representative_cell_id` | The first cell that created the tile | `:106` |
| `area_km2` | Summed `area_km2`, rounded to 6 decimals | `:143` |
| `centroid_lat_deg`, `centroid_lon_deg` | Normalized mean of member cell unit vectors, rounded to 6 decimals | `:141`–`:142` |

| Level summary field | Meaning | Source |
| --- | --- | --- |
| `level` | Quadtree level | `:156` |
| `nominal_tile_count` | `6 * 4^level` | `:157` |
| `occupied_tile_count` | Tiles that actually contain cells | `:158` |
| `cell_count`, `mean_cells_per_tile`, `max_cells_per_tile`, `mean_tile_area_km2` | Occupancy statistics | `:159`–`:162` |

Per cell it writes `mesh_lod_face`, `mesh_lod_face_id`, `mesh_lod_tile_ids[]`, `mesh_lod_codes[]`, `mesh_lod_finest_tile_id` (`:121`–`:125`), and six `summary.mesh_lod_*` keys (`:176`–`:181`).

### How the viewer uses it: it does not

There is no `mesh_lod` reference anywhere in `src/magic_geo/debug_ui/app.js` or `src/magic_geo/debug_export.py` — the index surfaces only as ordinary exported data:

| Enriched key | Where it lands in the cache | Why |
| --- | --- | --- |
| `mesh_lod_face` | `cells.parquet` column + a `categorical` layer (6 classes) | string with ≤ 64 distinct values |
| `mesh_lod_face_id`, `mesh_lod_finest_tile_id` | `cells.parquet` columns + `numeric` layers | int scalars |
| `mesh_lod_tile_ids`, `mesh_lod_codes` | `events/cell_details.jsonl` via `detail_fields` | list-valued → `skipped_fields` reason `non-scalar field retained in indexed cell details` |
| `world["mesh_lod"]` | `sections.json` entry, browsable under Data → Model sections | dict-valued top-level key (`debug_export.py:874`) |

The map renderer always uploads the full merged mesh with `frustumCulled = false` and performs no tile selection (`src/magic_geo/debug_ui/app.js:443` for the wire mesh). `docs/gui_debug_visualization_research.md:160` records the same conclusion for the whole index family — "exactly the right scaffolding for LOD/culling, but the cell payload is not partitioned or sorted by tile, so they are dead weight until an export layer exploits them" — and `:178` notes that `render --max-cells` is naive stride slicing that ignores the purpose-built quadtree.

---

## `export-debug-map`: projections, layers, formats, parity

`src/magic_geo/debug_map_export.py` is the CLI counterpart of the Map view's **Export PNG** / **Prompt .md** buttons. Its docstring is explicit that it reads the same committed debug-cache layer/mesh data, renders the same diagnostic palette without a browser, and **never calls an image-generation service** (`:1`–`:7`). It imports `_DebugCache` from `debug_server` (`:27`), so layer values come from the exact same code path the HTTP API uses.

```bash
magic-geo export-debug-map \
  --debug-dir runs/debug \
  --layer cells/biome \
  --projection mollweide \
  --output runs/biome-reference
```

### CLI options

| Option | Type / bounds | Default | Meaning | Source |
| --- | --- | --- | --- | --- |
| `--debug-dir` / `-d` | existing directory | `runs/debug` | Debug cache produced by `export-debug` | `src/magic_geo/cli/commands/export.py:15` |
| `--layer` / `-l` | string | `None` → auto | Manifest layer id | `:25` |
| `--output` / `-o` | path basename | `None` → generated | Suffixes are appended, not taken literally | `:33` |
| `--projection` | string | `globe` | `globe`, `equirect`, or `mollweide` (aliases below) | `:41` |
| `--width` | int, 320–6400 | `1600` | PNG width | `:45` |
| `--height` | int, 160–3200 | `900` | PNG height | `:46` |
| `--stage` | int, ≥ 0 | `0` | Zero-based stage for `*_stage` layers | `:47` |
| `--month` | int, 1–12 | `1` | Month for monthly layers; converted to 0-based at `:139` | `:48` |
| `--center-lat` | float, −90…90 | `0.0` | Latitude at the view center | `:49` |
| `--center-lon` | float, −360…360 | `0.0` | Longitude at the view center (normalized to −180…180 at `debug_map_export.py:1328`) | `:54` |
| `--camera-distance` | float, 1.01–100 | `None` → `3.0` globe / `3.4` flat | Canonical camera distance | `:57`, default at `debug_map_export.py:814` |
| `--camera-position` | `"x,y,z"` | `None` | Exact Three.js camera position; switches to explicit pose replay | `:66` |
| `--camera-target` | `"x,y,z"` | `None` → `0,0,0` | OrbitControls target; requires `--camera-position` | `:73` |
| `--camera-up` | `"x,y,z"` | `None` → `0,1,0` | Camera up vector; requires `--camera-position` | `:80` |
| `--vertical-fov` | float, 1–179 | `50.0` | Perspective vertical field of view in degrees | `:87` |
| `--cache-identity` | string | `None` → derived | Browser cache-identity override for byte-exact fingerprint/name parity | `:91` |
| `--wireframe` / `--no-wireframe` | bool | `False` | Diagnostic cell outlines (the boundary edge of each fan triangle only) | `:98` |
| `--plates` / `--no-plates` | bool | `False` | Diagnostic plate-boundary guides | `:103` |
| `--graticule` / `--no-graticule` | bool | `False` | Diagnostic lat/lon guides | `:106` |
| `--image` / `--no-image` | bool | `True` | Write the PNG | `:110` |
| `--prompt` / `--no-prompt` | bool | `True` | Write the GPT Image Markdown prompt | `:114` |

Errors (`OSError`, `ValueError`) print `Unable to export debug map: …` and exit `2` (`:154`); a missing `[debug]` extra exits `2` with the install hint (`:123`). On success the command prints `Wrote <paths> | layer=… projection=… stage=… month=…` with the month re-reported 1-based (`:158`).

The Python API is `export_map_reference(debug_dir, *, layer_id=None, output=None, projection="globe", width=1600, height=900, stage=0, month=0, center_lat=0.0, center_lon=0.0, camera_distance=None, camera_position=None, camera_target=None, camera_up=None, vertical_fov=50.0, cache_identity=None, wireframe=False, plates=False, graticule=False, write_image=True, write_prompt=True)` (`src/magic_geo/debug_map_export.py:1291`); note `month` is **0-based** in the API and 1-based on the CLI.

### Projections

Normalization is `projection.lower().replace("_", "-")`, then alias mapping, then a whitelist (`debug_map_export.py:1317`–`:1321`):

| Accepted input | Canonical | Mesh buffers read | Notes |
| --- | --- | --- | --- |
| `globe`, `orthographic` | `globe` | `positions.f32` | Axis remap `globe(x,y,z) = world(y,z,x)` to match the Three.js scene (`:869`) |
| `equirect`, `equirectangular` | `equirect` | `pos_equirect.f32` | `flat_center_y = center_lat / 90` (`:851`) |
| `mollweide` | `mollweide` | `pos_mollweide.f32` **and** `pos_equirect.f32` | equirect supplies lat/lon and the per-cell longitude anchor (`:1127`, `:1137`–`:1152`) |

Flat projections re-center on `center_lat`/`center_lon` through `flat_geo` (`:883`), which composes the anchor delta and the point delta so a cell's ring stays on one longitude branch. `globe` performs no re-centering of geometry; the center is expressed entirely through the canonical camera pose.

### Camera

Two mutually exclusive modes (`_resolve_camera_pose`, `:780`):

| Mode | Inputs | Rules |
| --- | --- | --- |
| Canonical | `--center-lat`, `--center-lon`, `--camera-distance` | Distance must be finite and within `1.01 … 100` (`:815`). Globe: camera sits on the remapped surface normal at `distance`, target `(0,0,0)`, up = remapped local north (`:759`–`:771`). Flat: position `(0, 0, distance)`, target `(0,0,0)`, up `(0,1,0)` (`:772`) |
| Explicit pose | `--camera-position` (+ optional `--camera-target`, `--camera-up`) | Cannot be combined with `--camera-distance` or a non-zero center (`:801`). `--camera-target`/`--camera-up` without `--camera-position` is rejected (`:798`). All components must be finite (`:728`). An up vector parallel to the view direction is rejected (`:810`) |

`--vertical-fov` must be finite and within `1 … 179` in both modes (`:794`).

### Layer selection and default resolution

`--layer` is a manifest layer id. When omitted, resolution is: `cells/elevation_m` → the first layer with `kind == "numeric"` → the first layer at all (`:1376`–`:1380`). An unknown id raises `unknown or unavailable layer '<id>'; available examples: <first 12 sorted ids>` (`:1385`). The browser uses the identical fallback chain for its initial layer.

### Output formats and naming

Both artifacts share one basename. `--output` is treated as a basename with any of `.gpt-image-prompt.md`, `.png`, `.md` stripped, first match wins (`_output_base`, `:1196`); an empty remainder raises. At least one of PNG/prompt must be enabled (`:1322`).

| Artifact | Suffix | Written when | Encoder |
| --- | --- | --- | --- |
| Reference image | `<base>.png` | `--image` | Hand-rolled 8-bit RGB PNG: `IHDR` (bit depth 8, color type 2), `IDAT` via `zlib.compress(..., 6)`, `IEND`, CRC-32 per chunk (`:1048`–`:1056`) |
| GPT Image prompt | `<base>.gpt-image-prompt.md` | `--prompt` | UTF-8 Markdown (`:1461`) |

When `--output` is omitted the base is `Path("runs") / map_export_base_name(...)` (`:1433`). `map_export_base_name` (`:192`) joins slugified parts with `--`:

| Part | Value | Condition |
| --- | --- | --- |
| 1 | world name slug (fallback `world`) | always |
| 2 | layer id slug (fallback `layer`) | always |
| 3 | projection slug (fallback `map`) | always |
| 4 | `stage-<stage>` | `kind` ends with `_stage` |
| 5 | `month-<month+1>` | `kind == "numeric_monthly"` |
| 6 | `view-<fingerprint>` | a view fingerprint is supplied (always, from the CLI) |

Slugification is NFKD → ASCII → lowercase, non-alphanumerics collapsed to single `-`, trimmed, truncated to 80 characters (`_filename_slug`, `:177`). The browser's counterpart is `filenameSlug` (`src/magic_geo/debug_ui/app.js:717`), which strips combining marks instead of dropping every non-ASCII code point, so the two agree on ASCII-representable names but can differ on a name with non-Latin characters between alphanumerics; the part assembly itself is `mapExportBaseName` (`:778`), which builds the identical part list in the identical order.

Both files are written to `.<name>.<uuid4hex>.tmp` beside the destination and moved with `os.replace` only after the whole export succeeded (`:1268`, `:1485`); temporaries are unlinked in a `finally` block (`:1500`).

### The rasterizer and palette

| Element | Value | Source |
| --- | --- | --- |
| Background | `(16, 20, 26)` = `#10141a` | `:34`–`:35` |
| Missing / no-data | `(41, 46, 54)` = `#292e36` | `:36`–`:37` |
| Numeric ramp | `_numeric_scale()` picks Viridis, Cool–warm, Terrain (two slopes about 0 m), identifier colours or a single constant colour, mirroring `numericScale()` in `colormaps.js`; the 256-entry tables are read from `debug_ui/colormaps.js` (`_load_colormap_luts`) and sampled at `min(255, floor(t * 256))` | `_numeric_scale`, `_colormap_lut_rgb` |
| Numeric normalization | `t = clamp((value − low) / max(high − low, 1e-12))` where `(low, high)` is `p2..p98`, falling back to `min..max`, then to `min..min+1` | `:401`–`:421` |
| Categorical hue | `hue = (index * 0.61803398875) % 1`, HLS `(hue, 0.55, 0.55)` | `:369`–`:372` |
| "Missing" predicate | `not math.isfinite(v) or v >= 1.0e37`, plus `v < -0.5` for categorical | `:397`, `:413`–`:416` |
| Cell outlines | black, α `0.5525` (the browser scales the fill by 0.4475), radius 0, only the ring edge `(i+1, i+2)` of each fan triangle | `render` in `debug_map_export.py` |
| Plate boundaries | `(255, 107, 81)`, α `0.90`, radius `1` when `min(width, height) ≥ 600` else `0` | `:1167`–`:1178` |
| Graticule | `(114, 140, 178)`, α `0.28`, radius 0; parallels every 30° from −60 to 60 spanning the full −180…180 longitude range, meridians every 30° from −180 to 150 spanning only −85…85 latitude, both emitted as 5° segments | `:1012`–`:1018`, `:1179` |

Triangles are filled by a software scanline rasterizer with per-pixel edge functions, perspective-correct `1/z` interpolation, and a float z-buffer (`_rasterize_triangles`, `:961`). Overlay lines depth-test with a `0.025` tolerance so guides sit on the surface without z-fighting (`:956`). A triangle takes its color from the **first vertex's** cell id (`:985`).

### Limits and fail-closed checks

| Check | Limit / condition | Source |
| --- | --- | --- |
| Raster area | `width * height ≤ 8_294_400` (only when writing an image) | `:40`, `:1335` |
| Cell count | `cache.cell_count ≤ 200_000` | `:41`, `:1370` |
| Mesh vertices | `≤ 2_000_000`, checked against both the manifest and the on-disk buffer size | `:42`, `:1097`, `:1372` |
| Mesh triangles | `≤ 2_000_000`, same double check | `:43`, `:1095`, `:1374` |
| Incomplete mesh | Any `cells_without_ring > 0` **fails the export**: "a semantic image prompt would mislabel those holes as outside-map background" | `:1363` |
| Empty mesh | `triangle_count < 1` fails | `:1368` |
| Buffer agreement | Manifest `vertex_count`/`triangle_count` must equal the buffer lengths; position and cell-id buffers must agree | `:1108`–`:1119`, `:1133` |

### Cache-change protection

Fingerprints are `(st_dev, st_ino, st_size, st_mtime_ns)` (`:1218`). `_snapshot_read_paths` (`:1235`) collects `manifest.json`, the layer's data table (monthly parquet / stage-cells parquet / cells parquet), the mesh buffers the chosen projection needs, and — with `--plates` — the `cell_adjacency_edges` parquet. The manifest fingerprint is taken *before* `_DebugCache` is constructed and re-checked twice afterwards (`:1350`, `:1354`, `:1395`); the whole snapshot is re-verified after reading values (`:1404`) and again immediately before the `os.replace` (`:1484`). Any mismatch raises `ValueError("debug cache changed during map export; retry")` (`:1288`) or `"…while its export snapshot was being opened; retry"` (`:1277`).

### The view fingerprint and browser parity

`map_view_fingerprint` (`:255`) is FNV-1a-64 over a canonical string of length-prefixed components, where the length is the **UTF-16 code-unit count** (`len(component.encode('utf-16-le')) // 2`, `:287`) — matching JavaScript's `String.length`.

| # | Component | Notes |
| --- | --- | --- |
| 1 | `magic-geo-map-view-v1` | Version tag |
| 2 | cache identity | Default `json.dumps([True, <cwd-relative cache dir>, <revision>], separators=(",",":"))` (`:1223`); `--cache-identity` overrides |
| 3 | layer id | Resolved id, not the raw `--layer` |
| 4–5 | `stage`, `month` | Decimal strings; month is 0-based |
| 6 | projection | Canonical name |
| 7–9 | wireframe, plates, graticule | `"1"` / `"0"` |
| 10–11 | width, height | Decimal strings |
| 12–14 | camera position x, y, z | via `_js_number_string` |
| 15–17 | camera target x, y, z | via `_js_number_string` |
| 18–20 | camera up x, y, z | via `_js_number_string` |
| 21 | vertical FOV | via `_js_number_string` |

`_js_number_string` (`:217`) is a hand-written reimplementation of ECMAScript `Number.prototype.toString`, including the `−6 ≤ exponent < 21` fixed-notation window and the `e+N` / `e-N` exponent spelling, so a Python float and a JS number produce the same text. The browser's `mapViewFingerprint` (`src/magic_geo/debug_ui/app.js:755`) builds the same component list in the same order.

The default cache identity uses `Path.cwd()`-relative posix form of the cache directory and the revision token `"-".join(hex(dev), hex(ino), hex(size), hex(mtime_ns))` of `manifest.json` (`:1231`). The browser's identity is `JSON.stringify([cache_available, cache_dir, cache_revision])` (`src/magic_geo/debug_ui/app.js:1903`). To reproduce a browser export byte-for-byte in its **name and fingerprint**, pass that exact string to `--cache-identity` along with matching width/height/camera/overlay flags.

### What parity does and does not mean

Shared between the CLI exporter and the browser — identical in source except where the row states otherwise:

| Aspect | CLI | Browser | Verified at |
| --- | --- | --- | --- |
| Layer values | `_DebugCache.layer_values` | `GET /api/layer` → same function | `debug_map_export.py:27`, `debug_server.py:1145` |
| Numeric LUTs | 256-entry tables parsed from `colormaps.js`, nearest-sampled | 256×1 RGBA `DataTexture` from the same tables, read with `texelFetch` | `debug_map_export.py` `_COLORMAP_LUTS`, `app.js` `applyLayerColors` |
| Categorical hue | `(i * 0.61803398875) % 1`, HLS lightness/saturation `0.55` | Same constants in JS and in the fragment shader | `debug_map_export.py:369`, `app.js:60`, `app.js:145` |
| Background / missing colors | `#10141a` / `#292e36` | `#10141a` / `#292e36` | `debug_map_export.py:34`, `app.js:16` |
| Missing threshold | `v < 1.0e37` | `Number.isFinite(v) && v < 1.0e37` | `debug_map_export.py:397`, `app.js:813` |
| Overlay colors | white α0.10, `(255,107,81)` α0.90, `(114,140,178)` α0.28 | `[1,1,1,0.10]`, `[1.0,0.42,0.32]` α0.9, `[0.45,0.55,0.7]` α0.28 — the same nominal colors, but the browser hands floats to a shader uniform, so the emitted bytes depend on the GPU's float→unorm rounding and on alpha blending; no source asserts they match the CLI's floored integers | `debug_map_export.py:1166`–`:1189`, `app.js:437`, `:536`, `:567` |
| Graticule geometry | parallels −60…60 step 30, meridians −180…150 step 30, 5° segments | identical loops | `debug_map_export.py:1012`, `app.js:554` |
| Filenames | `map_export_base_name` + `_filename_slug` | `mapExportBaseName` + `filenameSlug` (same parts and order; slug differs only for non-ASCII names) | `debug_map_export.py:192`, `:177`, `app.js:778`, `:717` |
| View fingerprint | `map_view_fingerprint` | `mapViewFingerprint` | `debug_map_export.py:255`, `app.js:755` |
| Curated prose | Parsed out of `layer_docs.js` | `layer_docs.js` directly | `debug_map_export.py:103` |

**Not** claimed identical: the pixels. The browser PNG is a readback of the antialiased WebGL canvas at the renderer's device-pixel-ratio size, copied to a 2D canvas and encoded by `canvas.toBlob` (`app.js:932`–`:986`, `:1245`); the CLI PNG comes from a non-antialiased software rasterizer at the requested `--width`/`--height`. The two agree on data, palette, geometry source, naming, and fingerprint — not on sampling or antialiasing. No source in this repository asserts pixel equality.

### The prompt Markdown

`build_image_prompt_markdown` (`:585`) emits fixed sections: title, an attach-instruction blockquote, **Goal**, **Priority order** (spatial fidelity → semantic fidelity → natural detail → artistic finish), **What must remain unchanged**, **What to remove** (with per-overlay removal lines from `_overlay_prompt`, `:556`), **Reference geometry**, **Mapped field**, **Color codex**, **Output**.

| Reference-geometry line | Value | Source |
| --- | --- | --- |
| Companion image | `<base>.png` filename | `:649` |
| View fingerprint | 16 hex characters | `:650` |
| World | `manifest.world.name`, Markdown-escaped | `:651` |
| Projection/view | `"<Projection> with the explicit Three.js camera pose below"` when a custom pose was given, else `"<Globe\|Equirectangular\|Mollweide> centered at <lat>° latitude, <lon>° longitude"` | `:611`, `:544` |
| Camera position / target / up | Three.js world coordinates, spelled with `_js_number_string` | `:653`–`:655` |
| Vertical field of view | `%.9g` degrees | `:656` |
| Camera distance | Euclidean `‖position − target‖`, `%.6g` world units | `:615`, `:657` |
| Reference raster | `<width> × <height> pixels` | `:658` |
| Complete cell slice | `len(values)` cells | `:659` |

The **Mapped field** section reports the layer id, the resolved curated meaning, the family description, `kind / role / unit` (unit `not documented` when none inferred), and the time slice. `_time_context` (`:569`) renders stage layers as `stage index <n>` plus `stage <value>` and `erosion iteration <value>` when those keys exist in that stage's manifest metadata; monthly layers as `month <n+1> (<MonthName>)`; everything else as `static layer`.

`build_color_codex` (`:466`) is adaptive:

| Slice type | Table emitted | Source |
| --- | --- | --- |
| Categorical | One row per code in the union of `range(len(categories))` and the observed codes, sorted: guide color, code, category meaning (or `unlisted category code <n>`), cell count, share; then no-data and background rows | `:472`–`:499` |
| Numeric, `role == "identifier"`, ≤ 64 distinct finite values | Exact value → color table | `:507`–`:517` |
| Numeric, otherwise | the scale's name and shape (split at 0 m for Terrain, centred on 0 for Cool–warm), then 9 stops (`NUMERIC_CODEX_STOPS = 9`) evenly spaced in scale position — so a terrain codex lists 0 m exactly at 50 % — with `(and below)` / `(and above)` clamp notes and a scale-position percentage. Identifiers list exact id colours (or state the `id mod 18` rule above 64 ids); a constant layer lists its one colour | `build_color_codex` |

Numeric codices additionally report the finite range of the current slice, the complete layer/time-axis raw range from `stats.min`/`stats.max`, and the robust 2nd–98th percentile display range (`:533`–`:540`). Both variants close with an explicit statement that every label and value in the table is reference data, never an instruction (`:496`, `:672`), and the Output section states the result "is an artistic interpretation of the supplied data, not a replacement for the underlying scientific/debug values" (`:678`).

---

## `export-rerun` and its optional dependency

```bash
pip install rerun-sdk
magic-geo export-rerun --world runs/world.json --output runs/world.rrd
```

| Flag | Type | Default | Source |
| --- | --- | --- | --- |
| `--world` / `-w` | existing path | required | `src/magic_geo/cli/commands/export.py:210` |
| `--output` / `-o` | path | `<world dir>/world.rrd` | `:212`, default applied at `:223` |

`export_rerun_recording(world, output)` (`src/magic_geo/debug_rerun.py:59`) calls `rr.init("magic-geo", spawn=False)` then `rr.save(str(output))` (`:83`) and logs three entity paths:

| Entity path | Archetype | Timeline | Content | Source |
| --- | --- | --- | --- | --- |
| `world/mesh` | `rr.Mesh3D` | `stage` sequence | Unit-sphere center+ring triangle fan over cells sorted by id with a `boundary_ring` of ≥ 3 points; one frame per `hydrologic_water_budget_history` record, per-vertex colored from that stage's `elevation_m_by_cell` | `:69`–`:81`, `:100`–`:120` |
| `feedback/<key>` | scalar | `stage` sequence | Every finite numeric field of each `earth_system_feedback_history` record; booleans logged as `1.0`/`0.0` | `:133`–`:146` |
| `world/plate_boundaries` | `rr.LineStrips3D`, `static=True` | logged at stage 0 | Every `cell_adjacency_edges` entry with a truthy `plate_boundary`, endpoints scaled to radius `1.003`, color `(255, 107, 82)` | `:148`–`:164` |

Vertex coloring normalizes each stage's values to that stage's own p2–p98 span, with a zero span replaced by `1.0` and missing values rendered `(60, 60, 60)` (`:86`–`:97`). With no water-budget history, a single stage-0 frame is logged from each cell's `elevation_m` (`:121`–`:131`).

Return value (`:166`): `{output, vertices, triangles, stages, feedback_scalars, plate_boundary_segments}`. The CLI echoes `stages`, `vertices`, `feedback_scalars`, `plate_segments` (`src/magic_geo/cli/commands/export.py:229`).

### Optional-dependency handling

| Surface | Behavior | Source |
| --- | --- | --- |
| Module import | `import rerun as rr` at module top level | `src/magic_geo/debug_rerun.py:17` |
| Packaging | `rerun-sdk` is **not** in any `[project.optional-dependencies]` group — `debug` covers only `pyarrow`, `duckdb`, `fastapi`, `uvicorn` | `pyproject.toml:19` |
| CLI | Catches `ImportError` and exits `2` with `Rerun export requires the rerun-sdk package: pip install rerun-sdk (…)` | `src/magic_geo/cli/commands/export.py:219` |
| Web operations catalog | `optional_dependency: "rerun"`; `operation_catalog` always republishes it as `dependency: "rerun"` and sets `available` to `importlib.util.find_spec("rerun") is not None` | `src/magic_geo/web_jobs.py:237`, `:316`, `:318` |

Two SDK-version shims exist: `rr.set_time("stage", sequence=…)` falling back to `rr.set_time_sequence` on `TypeError` (`debug_rerun.py:46`), and `rr.Scalars` falling back to `rr.Scalar` (`:54`). The module docstring calls this exporter "the plan's v0 accelerator alongside the full web debugger" (`:1`) — it is a companion viewer, not an authoritative artifact, and it contains no manifest, no provenance hash, and no skip diagnostics.

---

## Default output paths: CLI versus browser

This is the single most common source of "where did my cache go" confusion, and the two defaults genuinely differ.

| Invocation | Field | Default | Rebased by workspace? | Source |
| --- | --- | --- | --- | --- |
| CLI `export-debug` without `--output` | cache directory | `<world file's parent>/debug` | no | `src/magic_geo/cli/commands/export.py:187` |
| CLI `export-rerun` without `--output` | recording | `<world file's parent>/world.rrd` | no | `src/magic_geo/cli/commands/export.py:223` |
| CLI `export-debug-map` without `--output` | artifact base | `runs/<generated base name>` (literal `runs`, relative to the process cwd) | no | `src/magic_geo/debug_map_export.py:1433` |
| CLI `export-debug-map` `--debug-dir` | input cache | `runs/debug` | no | `src/magic_geo/cli/commands/export.py:24` |
| Browser `export-debug` job | `output` | `runs/debug` | **yes** | `src/magic_geo/web_jobs.py:228` |
| Browser `generate` job | `debug_output` | `runs/debug` | **yes** | `src/magic_geo/web_jobs.py:123` |
| Browser `export-rerun` job | `output` | `runs/world.rrd` | **yes** | `src/magic_geo/web_jobs.py:240` |

"Rebased" means `_workspace_default` (`src/magic_geo/web_jobs.py:278`): for fields with `path_role == "output"` (or `workspace_relative`), a relative default whose first path component is exactly `runs` has that component replaced by the configured `--workspace`, and the result is re-expressed relative to the project root (`:294`–`:298`). So under `--workspace runs/alpha`, the browser's cache default becomes `runs/alpha/debug` while CLI `export-debug --world runs/world.json` still writes `runs/debug`. `README.md:64`–`:69` states the same distinction in prose.

Two further browser-only behaviors:

- **Chained export after generate.** A successful `generate` job with `open_in_web` enabled (default `True`, `web_jobs.py:122`) runs a second command `python -m magic_geo export-debug --world <output> --output <debug_output> --vtu|--no-vtu`, where the VTU flag comes from `debug_vtu` (default `False`, `:124`). The generate job's own artifacts are captured *before* that chained export, so a failing cache export cannot lose them (`web_jobs.py:1247`–`:1266`).
- **Staged publication.** Browser cache exports run into `tempfile.mkdtemp(prefix=".<dest>.<job_id>.", suffix=".staging", dir=dest.parent)` with `--output` rewritten to the staging directory (`web_jobs.py:1130`–`:1140`). The staged cache is validated (`manifest.json` and `sections.json` parse as objects; `format` exactly `magic-geo-debug-cache`; `version` exactly the int `1`; `world` a dict and `layers` a list — `_validate_debug_cache`, `:1075`–`:1098`) and only then published by an `os.replace` swap with a `.{name}.{uuid}.backup` rollback (`:1101`–`:1115`). CLI `export-debug` writes in place with no staging, no validation pass, and no rollback.

---

## Per-layer reference

`docs/layers_reference.md` is the exhaustive per-layer catalog. It is auto-generated by `node scripts/gen_layers_reference.mjs [manifest.json] [out.md]` (defaults: `runs/debug/manifest.json` → `docs/layers_reference.md`, `scripts/gen_layers_reference.mjs:20`–`:22`) from the same `layer_docs.js` that powers the in-app docs card, so it cannot drift from what the UI shows. Its columns are `Layer | Kind | Unit | Range (min … max) | Role | Doc | What it is`.

The numbers below are those of the checked-in generation: world `earthlike_mvp`, 4,096 cells, mesh `fibonacci_sphere`, scope `full`, **439 layers** — 361 numeric, 47 categorical, 27 per-stage, 4 monthly (`docs/layers_reference.md:54`–`:56`). Regenerating against a different world will change every count.

| Domain section | Anchor | Layers | Curated | Generated (doc gaps) | Line |
| --- | --- | --: | --: | --: | --- |
| Mesh & geometry | [`#geometry`](../layers_reference.md#geometry) | 40 | 14 | 7 | `docs/layers_reference.md:88` |
| Tectonics & solid earth | [`#tectonics`](../layers_reference.md#tectonics) | 37 | 20 | 1 | `:147` |
| Elevation & landforms | [`#geomorphology`](../layers_reference.md#geomorphology) | 13 | 10 | 0 | `:203` |
| Sediment & stratigraphy | [`#sediment`](../layers_reference.md#sediment) | 35 | 8 | 0 | `:233` |
| Surface hydrology & rivers | [`#hydrology`](../layers_reference.md#hydrology) | 78 | 34 | 2 | `:285` |
| Water budget & atmospheric moisture | [`#water-budget`](../layers_reference.md#water-budget) | 27 | 14 | 0 | `:382` |
| Groundwater, aquifers & karst | [`#groundwater`](../layers_reference.md#groundwater) | 30 | 8 | 0 | `:426` |
| Climate & atmosphere | [`#climate`](../layers_reference.md#climate) | 38 | 19 | 0 | `:473` |
| Oceans & coasts | [`#ocean`](../layers_reference.md#ocean) | 31 | 8 | 1 | `:528` |
| Cryosphere (ice, glaciers, permafrost) | [`#cryosphere`](../layers_reference.md#cryosphere) | 25 | 8 | 0 | `:578` |
| Soils | [`#soil`](../layers_reference.md#soil) | 14 | 7 | 0 | `:620` |
| Ecology, biomes & disturbance | [`#ecology`](../layers_reference.md#ecology) | 35 | 9 | 1 | `:651` |
| Resources & economic geology | [`#resources`](../layers_reference.md#resources) | 15 | 6 | 0 | `:705` |
| Human & political geography | [`#human`](../layers_reference.md#human) | 20 | 9 | 0 | `:737` |

Documentation-tier coverage over those 439 layers: curated 174 (39.6%), convention 181 (41.2%), unit 72 (16.4%), generated 12 (2.7%) (`docs/layers_reference.md:60`–`:65`). To close a gap, add one line to `CURATED` in `src/magic_geo/debug_ui/layer_docs.js`; the docs card, the help-overlay coverage box, the CLI prompt's "Meaning" line, and the generated reference all read from that one map (`docs/layers_reference.md:786`).

---

## Limitations and unresolved claims

**Debug-cache scope.**

- The cache is a **derived view**, not an authoritative artifact. It is regenerated from `world.json` / `.mgeo` and adds no information; `manifest["source"]` records the source path, byte length, and SHA-256 only when `source_path` is supplied (`debug_export.py:857`), and the CLI always supplies it (`cli/commands/export.py:192`).
- Mesh export fails outright unless cell ids are contiguous `0..n-1` (`debug_export.py:600`). There is no partial-mesh mode.
- Cells whose `boundary_ring` is missing or shorter than 3 points are silently excluded from the mesh and only counted in `mesh.cells_without_ring` (`:610`, `:660`). `export-debug-map` refuses to run at all when that count is non-zero, on the stated grounds that the resulting holes would be mislabeled as outside-map background (`debug_map_export.py:1363`); the browser applies the same guard (`app.js:840`).
- Boundary rings are approximate and do **not** tessellate — `docs/gui_debug_visualization_research.md:158` records that the README explicitly defers exact native edge polygons. Visible gaps between cells in the flat projections are the documented ring mismatch, diagnosable through `mean_neighbor_boundary_segment_mismatch_km`, not a rendering bug (`layer_docs.js:555`).
- Monthly detection is a pure shape heuristic (any field whose non-null values are all 12-element numeric lists, `debug_export.py:205`). No field-name check is applied.
- `"endianness": "little"` in `manifest.mesh` is a hardcoded literal while the writer emits host-order bytes (`debug_export.py:654`, `:661`). Big-endian write behavior is not verified in source.
- `p2`/`p98` are nearest-rank picks over finite values only (`:115`). `docs/layers_reference.md:784` records that 62 layers in the reference world have `p2 == p98`, in which case the color scale falls back to `min..max`; a layer whose `min == max` is drawn in one colour and described as constant rather than given an invented `min..min+1` range.
- Identifier layers (`*_id`, `*_to`) are rendered as continuous ramps. Both the UI and the generated reference flag this with the `identifier` role, but the ramp itself remains meaningless — "same colour ≈ same group", and percentile statistics on ids are not meaningful (`layer_docs.js:68`).
- Per-stage `lithology` ships as numeric codes 0–6 while `cells/lithology` uses alphabetical names, and **no code→name table is emitted**; the code order here is alphabetical and may not match the engine enum (`layer_docs.js:144`, `docs/layers_reference.md:781`).
- High-cardinality string fields (for example `healpix_like_pixel_code`, `s2_like_token`) produce no layer. They are not dropped: the column stays in `cells.parquet` and the reason is recorded in `cells.skipped_layers` (`docs/layers_reference.md:780`).

**Mesh LOD.**

- `mesh_lod` (`cube_quadtree_v0`) is exported but consumed by nothing in the debugger or the exporter. The map renderer uploads the full merged mesh with culling disabled and performs no tile selection. `docs/gui_debug_visualization_research.md:160` calls the index (together with the HEALPix-like and S2-like ids) "dead weight until an export layer exploits them", and `:178` notes `render --max-cells` is naive stride slicing that ignores it.
- `mesh_lod.py` performs no validation of its own inputs beyond requiring `lat_deg`/`lon_deg` and a non-empty cell list (`mesh_lod.py:73`–`:81`); `area_km2` defaults to `0.0` when absent (`:83`).

**Map export.**

- Parity with the browser is established for data, palette, geometry source, filenames, and the view fingerprint. It is **not** pixel parity: the browser reads back an antialiased WebGL canvas, the CLI runs a non-antialiased software rasterizer. No source claims byte-identical images.
- Reproducing a browser export's *name and fingerprint* requires passing the browser's exact cache-identity string via `--cache-identity` plus matching width, height, camera pose, FOV, and overlay flags. Without it the CLI derives its own identity from the cwd-relative cache path and manifest revision (`debug_map_export.py:1223`).
- The exporter never contacts an image-generation service; it only writes a local PNG and a local Markdown prompt (`debug_map_export.py:1`, `layer_docs.js:537`). The generated prompt's own Output section states the result is an artistic interpretation, not a replacement for the underlying values (`:678`).
- `--month` on the CLI is 1-based while the Python API's `month=` is 0-based (`cli/commands/export.py:139`). The view fingerprint uses the 0-based value.
- The plate overlay silently renders nothing when `cell_adjacency_edges` was exported as a nested family, because `plate_boundary_segments()` requires the `parquet` key (`debug_server.py:488`).

**Rerun.**

- `rerun-sdk` is not part of any declared extra, so `magic-geo[debug]` does not install it.
- The recording carries no manifest, no source hash, no skipped-output diagnostics, and no category tables. It is a viewer companion, not a reproducible export.
- Vertex colors are re-normalized to **each stage's own** p2–p98 span (`debug_rerun.py:88`–`:92`), unlike the debug cache and web map, whose scales are fixed across the whole time axis. Apparent brightness change between Rerun frames therefore does not imply a change in absolute values.
- Its plate-boundary color `(255, 107, 82)` (`debug_rerun.py:163`) differs by one unit from the map exporter's and the browser's `(255, 107, 81)` (`debug_map_export.py:1174`, `app.js:536`).

**Scientific interpretation of exported fields.** The cache faithfully re-serializes whatever the generator produced, including fields the project marks explicitly unresolved. Nothing about being visualized upgrades a hedged claim:

- Physical subduction polarity, slab selection/geometry/transfer, and material fate remain **unresolved**; an oceanic-like side is recorded only as a *candidate* subducting side, and the physical fields stay `unknown` with source `none` and zero confidence wherever convergence is active (`README.md:348`).
- The `km/Ma` scale of the boundary ledger is **nominal**, not an observed or calibrated plate speed, and physical-time calibration is unresolved (`README.md:348`, `:347`).
- The dry-rock accounting model is a **non-authoritative numerical counter-model**; every transfer carries `physical_basis_resolved: false`, and cell-state authority, material provenance, mantle/slab resolution, and subduction polarity all remain false (`README.md:351`).
- Accelerator/GPU parity for crust transport remains **false**; geometry, coverage, membership classes, categories, and scientific state are CPU-authoritative (`docs/geo_generation_maturation_deep_audit.md:414`).
- `crust_age_ma` is a procedural crust-state age after remap and maturation rules — explicitly "not a reconstructed geological creation age or proof of a ridge-to-subduction flowline" (`layer_docs.js:143`).
- `energy_balance_residual_c` is a diagnostic model mismatch, not the residual of a solved energy-closure equation, and is **not** expected to be zero (`layer_docs.js:213`).
- Coarse-resolution fields such as `water_depth_m` and `continental_shelf_id` represent an entire ~400 km control volume and do not resolve subcell shelf, slope, coastline, or strait geometry (`layer_docs.js:150`, `:198`).

**Server exposure.** The debug cache is served by a workbench that is explicitly *containment measures, not a tenant boundary*: no login, no authorization, no per-user isolation, no TLS. Anyone who can reach the port can read workspace data and submit or cancel jobs (`docs/debugger.md:216`). See [Web Workbench](./15-web-workbench.md).

---

## See also

- [Web Workbench](./15-web-workbench.md) — the server, HTTP routes, job system, and the interactive map/data/inspector views that consume this cache
- [Rendering and Map Output](./17-rendering.md) — `render` / `render-raster`, the other (browser-free) image path
- [CLI Reference](./06-cli-reference.md) — every command, including `export-debug`, `export-debug-map`, `export-rerun`, and `serve`
- [World Document Schema](./10-world-schema.md) — the payload shape the exporter classifies
- [Serialization and World Formats](./11-serialization.md) — the `.json` / `.mgeo` inputs to `export-debug`
- [Mesh and Geometry](./features/mesh-and-geometry.md) — `boundary_ring`, cell geometry quality, and the spatial indices behind the LOD scaffolding
- [Tectonics and Plates](./features/tectonics-and-plates.md) and [Plate Boundary Segment Ledger](./features/plate-boundary-ledger.md) — the source of the plate-boundary overlay and its unresolved polarity claims
- [Validation](./12-validation.md) and [Geo Validation Suite](./13-geo-validation-suite.md) — the authoritative checks that the debug cache visualizes but does not perform
- [Architecture](./04-architecture.md) — where `mesh_lod` and the other enrichers sit in the generation pipeline
- [Troubleshooting and FAQ](./22-troubleshooting.md) — cache-format rejection, missing sidecars, and unavailable optional dependencies
- [Glossary](./21-glossary.md) — layer, kind, role, stage history, family, section
