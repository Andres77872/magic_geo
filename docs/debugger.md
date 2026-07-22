# Local web workbench

`magic-geo serve` hosts a local browser workbench over the same configuration,
generation, validation, calibration, rendering, and export workflows as the
CLI. It also contains the GPU layer explorer previously called the GUI
debugger. No external service is required and no data is uploaded.

Related references:

- [UI guide](debug_ui_guide.md) — every browser view and control;
- [configuration helpers](configuration_helpers.md) — YAML profiles, Python
  API, validation, and config endpoints;
- [layer reference](layers_reference.md) — meaning and status of exported
  layers;
- [configuration reference](configuration_reference.md) — all 44 generation
  properties;
- [layer pipeline review](layers_pipeline_review.md) — exporter/viewer findings.
- [web refactor review](web_refactor_review.md) — pre-change evidence,
  requirement-by-requirement decisions, verification, and remaining limits.

## Start with or without a world

```bash
pip install -e '.[debug]'
magic-geo serve
# http://127.0.0.1:8642
```

`-d` is optional. With the default `--workspace runs`, the server auto-selects
`runs/debug` when it contains a manifest, and otherwise falls back to the newest
nested `runs/**/debug` cache. Only when no cache exists at all does it open
cacheless: Config, Operations, Backend, jobs, and OpenAPI still work. A successful browser
generation can create and select the cache without a restart.

If a cache already exists:

```bash
# Conventional paths: runs/world.json -> runs/debug -> no -d needed
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.json
magic-geo export-debug --world runs/world.json --output runs/debug --no-vtu
magic-geo serve

# Select a different cache explicitly
magic-geo serve -d runs/earthlike/debug
```

`--workspace runs` controls the root allowed for browser-created configs,
worlds, reports, maps, and exports. Conventional browser output defaults are
rebased under that root, so both **Prepare browser cache** and the browser
`export-debug` operation default to `<workspace>/debug`, including when a
non-default workspace is selected. CLI `export-debug` is different: omitting
its `--output` derives `<world parent>/debug`. `--host` defaults to loopback and
`--port` defaults to `8642`. `--workspace`, `--host`, and `--port` also read
the `MAGIC_GEO_WORKSPACE`, `MAGIC_GEO_HOST`, and `MAGIC_GEO_PORT` environment
variables when the flag is omitted; the Docker deployment
(`docs/docker_deployment.md`) configures the server this way from `.env`.

## Feature parity

Every CLI command has a web action or a direct equivalent:

| CLI command | Web equivalent |
|---|---|
| `init-config` | Config view and `/api/config/*` |
| `backend` | Backend & API view and `/api/backend` |
| `generate` | Generate world operation; full/geo-only, cell override, JSON/summary/CSV, optional automatic debug export |
| `validate` | Validate world operation and live log |
| `validate-geo` | Natural-geography validation operation with profile/report/warning policy |
| `validate-geo-suite` | Scenario-suite operation with JSON/Markdown artifacts |
| `calibrate` | Single-world calibration operation |
| `calibrate-ensemble` | Ensemble operation with repeatable target bundles |
| `derive-targets` | Target derivation operation |
| `render` | SVG operation with projection, size, labels, contours, and downloadable artifact |
| `render-raster` | PPM operation with projection, size, sampling, and texture controls |
| `export-debug` | Browser/ParaView cache operation |
| `export-debug-map` | Map view **Export PNG** / **Prompt .md**, with matching layer, time, projection, camera, overlay, and color-codex CLI options |
| `export-rerun` | Rerun operation when the optional package is installed |
| `serve` | The current workbench process/status |

The web service never accepts an arbitrary command line. Operations come from a
fixed typed catalog. Input paths must be regular files inside the current
project; operation-specific preflight follows nested calibration/source and
geo-suite derivation paths as well. Output paths must stay inside the workspace
and cannot replace an input. Commands run without a shell in a single
process-isolated background queue. Logs, status, cancellation, and downloadable
file artifacts are visible in Operations. The browser requires an explicit
geo-suite matrix instead of assuming a source-checkout example exists.

Cancelling queued work marks it cancelled without starting a subprocess.
Cancelling running work terminates its child process group on POSIX (the child
process elsewhere) and escalates to a kill if it does not stop within five
seconds. Server shutdown rejects new work, cancels queued work, terminates the
active child, and waits for the worker to reach a terminal state before cache
connections are closed. Cancellation is accepted until cache publication or
terminal artifact snapshotting begins; those commit phases finish atomically,
so a late cancel is ignored and cannot produce a `cancelled` job that already
published a cache.

For successful jobs, new or changed downloadable files are copied to job-owned
immutable snapshots; the download endpoint does not reopen the mutable requested
output. A later job may overwrite or remove that output without changing the
earlier download. The reporting operations (`validate-geo`,
`validate-geo-suite`, `calibrate`, and `calibrate-ensemble`) can intentionally
write a report and then exit nonzero for a requested policy gate. A report newly
produced or changed by that run is still snapshotted and downloadable from the
failed job; an unchanged pre-existing target is not presented as a new artifact.
Cancelled jobs do not snapshot partial outputs. If generation itself completed
before its optional cache-preparation step later failed or was cancelled, its
already-complete world/summary/CSV snapshots remain available.

Job records and their snapshot links are process-local; requested output files
persist independently, but the links disappear when the record is evicted or
the server restarts.

## Workbench architecture

```text
browser
  ├─ Config ───────────────▶ described WorldConfig JSON Schema
  │                           strict YAML parse/validate/render/save
  ├─ Operations ───────────▶ fixed typed operation catalog
  │                           one process-isolated job at a time
  │                           logs/status/cancel/artifacts
  ├─ Data ─────────────────▶ complete generic cache APIs
  │                           scalars/layers/stages/families/sections/skips
  ├─ Map ──────────────────▶ Float32 layer columns + binary mesh assets
  └─ Backend & API ────────▶ native probe + Swagger/OpenAPI

world.json ── export-debug ──▶ debug/
                               ├─ manifest.json
                               ├─ sections.json
                               ├─ tables/*.parquet
                               ├─ events/*.jsonl
                               ├─ events/cell_details.jsonl
                               ├─ tables/cell_details_index.json
                               ├─ mesh/*.f32|*.u32
                               └─ vtu/ + world.pvd (optional)
```

The server uses a reloadable cache manager. It discovers `<workspace>/debug`
first, then the newest nested `<workspace>/**/debug/manifest.json`; a completed
Generate job can select its cache. Cache changes made after startup are detected
from the manifest fingerprint. `/api/worlds` lists workspace caches and
`/api/worlds/select` switches between them.

Web-triggered cache-directory exports never build inside the selected cache.
They write a job-private sibling staging directory and publish it to the
requested cache path only after the export succeeds. Failed or cancelled stages
are discarded, leaving an existing cache intact. This staged-publication
guarantee applies to browser jobs; direct CLI `export-debug` writes the path it
is given. Publication validates the staged cache, pauses cache-backed reads for
the rollback-safe old/new directory swap, reopens the destination, and then
releases readers. Status exposes a device/inode/size/mtime revision token;
cache-backed endpoints accept that expected revision and reject a stale token
with `409`. Parallel browser mesh, catalog, and layer requests therefore cannot
silently combine old and new caches even if publication happens during startup.

## Export completeness

The exporter classifies the generated payload generically:

- scalar cell fields become one wide Parquet table and visual layers;
- 12-value numeric arrays become a monthly long table;
- cell-indexed histories become stage-cell and stage-summary Parquet tables;
- non-scalar stage metadata and mixed per-cell values become stage-extras JSONL
  exposed by the stage-summary API/Data view;
- flat record families become Parquet;
- nested families become full JSONL plus a scalar Parquet sidecar;
- dictionaries become named model/graph/clock sections;
- unsupported/empty outputs remain visible as skipped diagnostics.

Nested family reads default to the full JSONL record. Use
`detail=scalars` for the compact sidecar. This matters for records containing
`cell_ids`, route/resource links, provenance arrays, and other non-scalar
content.

Cell scalar reads stay fast through Parquet. Non-scalar cell fields—boundary
rings, neighbors, LOD paths, linked record IDs, original vectors, and monthly
arrays—are stored once in an indexed JSONL sidecar and merged into
`/api/cell/{id}`. The endpoint reports whether that complete sidecar exists, so
old caches degrade honestly.

Ragged 12-month arrays no longer crash export; they remain in cell details and
are reported as non-scalar instead of being partially flattened.

The supported cache manifest contract is `format: magic-geo-debug-cache` with
`version: 1`. The server rejects a missing/different format or version instead
of attempting a best-effort read. This cache version is independent of the
package version, HTTP API version, and generated-world schema version.

## Server and filesystem safety

The workbench is intended for a trusted local user, but it still enforces these
boundaries:

- default binding is `127.0.0.1`;
- cache paths use component-aware `Path.relative_to` confinement, not string
  prefixes;
- Parquet column names are quoted as DuckDB identifiers;
- JSONL, table, index, and mesh paths all pass the same cache-root check;
- fixed `manifest.json`/`sections.json` files cannot be symlinks outside the
  cache, and cache discovery rejects escaping manifest links before reading;
- config save names are restricted, symlink escapes are rejected, existing
  names require explicit overwrite, and writes stay under `<workspace>/configs`;
- direct and supported transitive job inputs stay under the project, outputs
  stay under the workspace, and an output cannot replace an input;
- browser cache exports use success-only staged publication;
- artifact downloads use immutable, job-owned file snapshots;
- subprocess arguments are fixed/typed and never evaluated by a shell;
- submitted YAML is capped at 1,000,000 UTF-8 bytes, bounded for
  nesting/events/aliases, and duplicate keys are rejected;
- layer format is the explicit `f32 | arrow` enum.
- strict JSON responses map non-finite scientific values to `null`; binary
  layer formats retain their Float32/Arrow representation.

These controls are containment measures, not a tenant boundary. The server has
no login, authorization, per-user isolation, or TLS, and anyone who can reach it
can inspect workspace data and submit or cancel jobs. Do not bind to a public or
untrusted interface; keep loopback or put the workbench behind a trusted network
boundary and authenticating proxy.

## API groups

Every endpoint below except `GET /mesh/{asset}` is served as an interactive
contract at `/api/docs` (Swagger), `/api/redoc`, and `/api/openapi.json`; the
mesh asset route is registered with `include_in_schema=False` and so does not
appear there.

### Workbench and worlds

| Endpoint | Purpose |
|---|---|
| `GET /api/status` | Cache availability/error, selected path, workspace, package version, and cache revision. |
| `GET /api/worlds` | Discover exported caches in the workspace. |
| `POST /api/worlds/select` | Select a workspace cache. |

### Configuration and backend

| Endpoint | Purpose |
|---|---|
| `GET /api/backend` | Native CPU/OpenCL/CUDA availability and selection telemetry. |
| `GET /api/config/schema` | Described schema and complete profile metadata. |
| `GET /api/config/profiles` | Profile list and UI default. |
| `GET /api/config/template` | Normalized YAML and values for a profile. |
| `POST /api/config/render` | Profile plus dotted overrides to YAML. |
| `POST /api/config/validate` | Strict YAML validation and normalization. |
| `POST /api/config/save` | Atomic workspace-confined save. |

### Operations and jobs

| Endpoint | Purpose |
|---|---|
| `GET /api/operations` | Typed fields for every executable/equivalent CLI feature. |
| `POST /api/jobs` | Queue one fixed operation. |
| `GET /api/jobs` | List jobs, newest first. |
| `GET /api/jobs/{id}` | Status, arguments, command, log, artifacts, selected cache. |
| `POST /api/jobs/{id}/cancel` | Cancel queued/running work. |
| `GET /api/jobs/{id}/artifacts/{n}` | Download an immutable job snapshot, including a report produced before a policy failure. |

### Complete cache reads

| Endpoint | Purpose |
|---|---|
| `GET /api/manifest?revision=` | Full exporter manifest, optionally pinned to a status revision. |
| `GET /api/catalog?revision=` | UI-oriented scalars/layers/stages/families/sections/skips catalog. |
| `GET /api/layer/{id}?stage=&month=&format=f32|arrow&revision=` | One value per cell. |
| `GET /api/cell/{id}` | Complete cell plus ledgers, monthly values, and adjacency. |
| `GET /api/stage-summary/{history}` | Per-stage scalar table and retained non-scalar extras. |
| `GET /api/family/{name}?detail=full|scalars&limit=&offset=` | Paged complete or scalar records. |
| `GET /api/section/{name}` | Model/graph/clock dictionary. |
| `GET /api/plate-boundaries` | Lat/lon boundary segments. |
| `GET /mesh/{asset}` | Confined binary GPU mesh asset. |

## Frontend implementation

The frontend has no compilation step. Vendored three.js 0.185 is loaded by an
import map. One merged indexed `BufferGeometry` represents the planet; cell
values are an R32F texture, so layer and stage changes upload one
`Float32Array` without rebuilding geometry. GPU ID-buffer picking opens the
complete cell inspector. Projection morphs and overlays remain in shaders.

The app initializes the Three scene only when a cache is available. Cacheless
startup therefore works on machines that only need configuration or job
control. The layout becomes stacked at tablet/mobile widths, tab controls are
semantic, and operation/data controls are keyboard accessible.

Static HTML/CSS/JS and vendored Three modules are declared as package data, so
the workbench works from a built wheel as well as an editable source checkout.
Wheel creation requires the CMake-staged native library, rejects a missing core,
and emits an OS/architecture platform tag (`py3-none-<platform>`) rather than an
unsafe universal tag.

## Optional companion viewers

```bash
pip install rerun-sdk
magic-geo export-rerun --world runs/world.json --output runs/world.rrd
paraview runs/debug/world.pvd
```

Rerun is intentionally optional and the operation catalog marks it unavailable
when the package cannot be imported. ParaView files are controlled by
`export-debug --vtu/--no-vtu` (or the corresponding browser field).

## Troubleshooting

- **No cache badge** — expected before generation. Config, Operations, and API
  remain usable. Generate with “Prepare browser cache” or run `export-debug`.
- **Explicit `-d` rejected** — it must be a directory containing
  `manifest.json`; omit it for cacheless startup.
- **Cache format rejected** — the server accepts
  `magic-geo-debug-cache` version `1`; re-export incompatible caches.
- **Old cache cell says `complete: false`** — re-run `export-debug` to add the
  indexed non-scalar cell sidecar.
- **A family looks narrower than expected** — choose “Full nested records”;
  scalar mode intentionally omits nested arrays/objects.
- **Rerun unavailable** — install `rerun-sdk`; all other operations remain
  available.
- **Job fails immediately** — inspect its log. Input files must exist inside
  the project and output paths must be below the workspace. If a validation or
  calibration policy produced a report before exiting nonzero, its snapshot is
  still available in the artifact list.
- **Map is blank after cache creation** — refresh status/Data; cache selection
  normally triggers map initialization automatically.
- **Whole layer is background** — no finite values exist at the selected
  stage/month.
- **Visible polygon seams** — boundary-ring mismatch is a known mesh diagnostic,
  not a missing cache record.
