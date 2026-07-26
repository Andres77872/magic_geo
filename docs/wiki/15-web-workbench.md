# Web Workbench

[Wiki home](./README.md) > Web Workbench

The web workbench is a local, single-user browser application served by `magic-geo serve`. It wraps the same configuration, generation, validation, calibration, rendering and export workflows the CLI exposes, adds a GPU layer explorer over an exported debug cache, and publishes a documented REST API at `/api/docs`. It is implemented by `src/magic_geo/debug_server.py` (FastAPI + DuckDB), `src/magic_geo/web_jobs.py` (typed background job queue) and `src/magic_geo/debug_ui/` (build-free ES-module frontend). It has **no authentication, no authorization, no per-user isolation and no TLS** — read [Security model](#security-model-trusted-local-single-user) before binding it anywhere but loopback.

## On this page

- [What the workbench is](#what-the-workbench-is)
- [Security model: trusted-local, single-user](#security-model-trusted-local-single-user)
- [Starting the server: workspace, host and port resolution](#starting-the-server-workspace-host-and-port-resolution)
- [Cache discovery and selection](#cache-discovery-and-selection)
- [The browser shell: tabs, routing and keyboard model](#the-browser-shell-tabs-routing-and-keyboard-model)
- [Config view](#config-view)
- [Operations view](#operations-view)
- [Data view](#data-view)
- [Map view](#map-view)
- [Backend and API view](#backend-and-api-view)
- [The job system](#the-job-system)
- [Job lifecycle state machine](#job-lifecycle-state-machine)
- [Cancellation and the commit boundary](#cancellation-and-the-commit-boundary)
- [Artifact snapshotting](#artifact-snapshotting)
- [Staging-then-publish for cache outputs](#staging-then-publish-for-cache-outputs)
- [Input and output path policy](#input-and-output-path-policy)
- [REST API route table](#rest-api-route-table)
- [Per-route detail](#per-route-detail)
- [Manifest-revision consistency model](#manifest-revision-consistency-model)
- [JSON versus binary layer responses and non-finite handling](#json-versus-binary-layer-responses-and-non-finite-handling)
- [OpenAPI and Swagger](#openapi-and-swagger)
- [Worked examples](#worked-examples)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## What the workbench is

`magic-geo serve` (`src/magic_geo/cli/commands/serve.py:13`) constructs a FastAPI application with `create_app()` (`src/magic_geo/debug_server.py:877`) and runs it under uvicorn at `log_level="warning"` (`src/magic_geo/cli/commands/serve.py:109`). The application is composed of three cooperating pieces:

| Piece | Module | Responsibility |
|---|---|---|
| Cache manager | `_CacheManager`, `src/magic_geo/debug_server.py:504` | Selects, validates, fingerprints, reloads and atomically republishes one exported debug-cache directory. |
| Job manager | `JobManager`, `src/magic_geo/web_jobs.py:408` | Runs fixed CLI operations as isolated subprocesses, one at a time, with typed arguments and a strict path policy. |
| Static UI | `src/magic_geo/debug_ui/` mounted at `/` | `index.html` + `app.js` (3,265 lines) + `layer_docs.js` + `style.css` + vendored three.js, mounted with `StaticFiles(directory=ui_dir, html=True)` **last** so `/api` and `/mesh` win (`src/magic_geo/debug_server.py:1205`). |

The server starts **with or without** a debug cache. Without one, Config, Operations, Backend, jobs and the OpenAPI surface still work; every cache-backed data route answers `409` until a cache exists (`src/magic_geo/debug_server.py:684`). The module docstring states this contract directly (`src/magic_geo/debug_server.py:1-10`).

The workbench never accepts an arbitrary command line. Every executable action comes from the fixed catalog `_OPERATIONS` in `src/magic_geo/web_jobs.py:109`, and each spawned command is the argument vector `[sys.executable, "-m", "magic_geo", <command>, …]` (`src/magic_geo/web_jobs.py:878`) run without a shell.

---

## Security model: trusted-local, single-user

State this plainly, because the source and `docs/debugger.md:216-220` state it plainly:

> These controls are containment measures, **not a tenant boundary**. The server has no login, authorization, per-user isolation, or TLS, and anyone who can reach it can inspect workspace data and submit or cancel jobs.

Concretely, anyone who can open a TCP connection to the bound port can:

- read every file the selected debug cache references, and every world/report/config under the workspace, through the data and artifact routes;
- enumerate and switch caches (`GET /api/worlds`, `POST /api/worlds/select`);
- submit jobs that spawn `python -m magic_geo …` subprocesses on the host as the serving user, consuming CPU/GPU/disk;
- overwrite any workspace path reachable by an operation's output field, including an existing debug cache directory;
- cancel anyone else's running job (there is no ownership notion — `POST /api/jobs/{id}/cancel` takes only an id).

### What *is* enforced

| Boundary | Where | What it does |
|---|---|---|
| Loopback default bind | `src/magic_geo/cli/commands/serve.py:37` | `--host` defaults to `127.0.0.1`. |
| Workspace containment | `src/magic_geo/cli/commands/serve.py:56-63`, `debug_server.py:513`, `web_jobs.py:426` | Resolved workspace must be inside the project root; CLI exits 2, the managers raise `ValueError("web workspace must be inside the project directory")`. |
| Component-aware path confinement | `_is_relative_to`, `debug_server.py:50`, `web_jobs.py:342` | Every cache file, mesh asset, JSONL sidecar, index, staging dir, backup and artifact is checked with `Path.relative_to`, never a string prefix. |
| Cache-root confinement | `_required_file` `debug_server.py:155`, `_data_path` `:241`, `mesh_path` `:255` | Manifest-referenced paths must be relative, must resolve inside the cache root, and must be regular files. |
| Symlink rejection | `debug_server.py:99-110`, `:1021`, `:1031`; `web_jobs.py:430`, `:438` | `manifest.json` / `sections.json` must resolve inside the cache; `<workspace>/configs` and the save target may not be symlinks; `.magic-geo-web` and `.magic-geo-web/artifacts` may not be symlinks. |
| DuckDB identifier quoting | `_quote_identifier`, `debug_server.py:58` | Manifest-sourced column names are double-quote-escaped; an embedded NUL raises `400 invalid NUL in field name`. |
| Config-save name policy | `debug_server.py:46`, `:1010-1043` | `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`, `.`/`..` rejected, writes confined to `<workspace>/configs`, overwrite requires explicit `force`. |
| YAML size/complexity caps | `debug_server.py:45`, `web_jobs.py:47-50` | Editor YAML capped at 1,000,000 UTF-8 bytes (`413`); job manifests capped at 8 MiB, 20,000 YAML events, depth 64, 64 aliases, parsed with `yaml.SafeLoader`. |
| Fixed subprocess argv | `web_jobs.py:878`, `:1188-1197` | No shell; `subprocess.Popen(list, cwd=project_root, …)` with typed, normalized values only. |
| Direct + transitive input confinement | `web_jobs.py:598`, `:617`, `:699`, `:752` | Inputs must be existing regular files under the project root, including paths reached through calibration source manifests and geo-suite matrices. |
| Output confinement | `web_jobs.py:604-614` | Outputs must be under the workspace, may not equal the workspace root, and may not live under `.magic-geo-web`. |
| Success-only cache publication | `web_jobs.py:1121`, `debug_server.py:601` | Browser cache exports build in a private staging sibling and publish with rollback; a failed export leaves the existing cache intact. |
| Immutable artifact downloads | `web_jobs.py:1026`, `:572` | Downloads read job-owned snapshots re-verified by `(st_dev, st_ino, st_size, st_mtime_ns)`, not the live output path. |
| Explicit layer format enum | `debug_server.py:1142` | `format` is `Literal["f32", "arrow"]`; anything else is a `422`. |
| Strict JSON numbers | `_StrictJSONResponse`, `debug_server.py:86` | Every JSON response recursively rewrites NaN/±Inf to `null`. |

None of these is an access-control mechanism. They bound what a *legitimate* local request can reach; they do not distinguish callers.

### Exposing it safely if you must

The Docker deployment is the supported pattern for a non-loopback bind, and it deliberately splits the *container* bind address from the *published* host interface (`.env.example`, `docker-compose.yml:26-34`):

```bash
# .env — container binds 0.0.0.0 so the published port can reach it,
# but Docker publishes only on the loopback interface of the host.
MAGIC_GEO_CONTAINER_WORKSPACE=/app/runs
MAGIC_GEO_HOST=0.0.0.0
MAGIC_GEO_PORT=8642
MAGIC_GEO_PUBLISH_HOST=127.0.0.1
```

`.env.example` says of `MAGIC_GEO_PUBLISH_HOST`: "The workbench has no authentication, so the default only exposes it to the local machine. Set to `0.0.0.0` only behind a trusted network boundary or authenticating proxy."

If you need remote access, the repository's stated position (`docs/debugger.md:218-220`, `docs/debug_ui_guide.md:446-449`) is exactly this and nothing more: keep the loopback bind, or put a **trusted network boundary plus an authenticating proxy** in front of it. No source in this repository prescribes any other remote-access mechanism. Do not bind a public or untrusted interface directly. Nothing in the workbench will fail closed if you do.

---

## Starting the server: workspace, host and port resolution

```bash
pip install -e '.[debug]'
magic-geo serve
# Serving web workbench with automatic workspace cache discovery … at http://127.0.0.1:8642
```

### Options

| Option | Type / bounds | Default | Env var | Help (verbatim) |
|---|---|---|---|---|
| `--debug-dir`, `-d` | `Path`, `exists=True`, `file_okay=False` | `None` | — | `Optional cache from export-debug; auto-loads <workspace>/debug when present.` |
| `--workspace` | `Path` | `runs` | `MAGIC_GEO_WORKSPACE` | `Directory for browser-created configs, worlds, reports, and exports.` |
| `--host` | `str` | `127.0.0.1` | `MAGIC_GEO_HOST` | `Bind address.` |
| `--port` | `int`, `1 <= x <= 65535` | `8642` | `MAGIC_GEO_PORT` | `Bind port.` |

Declared at `src/magic_geo/cli/commands/serve.py:15-47`.

### Precedence

These are Typer `envvar=` options, so precedence is fixed by Click:

| Rank | Source | Example |
|---|---|---|
| 1 (wins) | Explicit flag | `magic-geo serve --port 9000` |
| 2 | Environment variable | `MAGIC_GEO_PORT=9000 magic-geo serve` |
| 3 | Declared default | `8642` |

An environment variable applies **only when the flag is omitted**. `serve` is the only command in the CLI that declares `envvar=`.

### Workspace resolution rules

1. `project_root = Path.cwd().resolve()` (`serve.py:50`).
2. An absolute `--workspace` is used as-is; a relative one resolves against the project root (`serve.py:51-55`).
3. The resolved workspace must satisfy `relative_to(project_root)`, otherwise the CLI prints `Web workspace must stay inside <project_root>: <workspace>` on stderr and exits `2` (`serve.py:56-63`).
4. `_CacheManager.__init__` (`debug_server.py:507-515`) and `JobManager.__init__` (`web_jobs.py:421-428`) independently re-apply the same rule, then `mkdir(parents=True, exist_ok=True)` the workspace. Embedding `create_app()` directly cannot bypass it.
5. `JobManager` reserves `<workspace>/.magic-geo-web/` and `<workspace>/.magic-geo-web/artifacts/`, rejecting a symlink at either level (`web_jobs.py:429-442`).

Note the asymmetry at `serve.py:64-69`: cache auto-discovery is tested against the **unresolved** `workspace / "debug"` path, while `create_app` is handed the same unresolved `workspace=` value and resolves it itself. Both agree for the ordinary relative-path case.

### Output-default rebasing

`_workspace_default()` (`web_jobs.py:278`) rebases any catalog default that begins with `runs/` under a non-default workspace, but only for fields whose `path_role == "output"` or whose `workspace_relative` flag is set. This makes the displayed browser form and the server-side path policy agree: with `--workspace myruns`, **Prepare browser cache** and the browser `export-debug` operation both default to `myruns/debug`. CLI `export-debug` is different — omitting `--output` there derives `<world parent>/debug`.

### Startup failure modes

| Condition | Behaviour |
|---|---|
| `-d` given but `<dir>/manifest.json` is not a file | `No manifest.json in <dir>; choose an export-debug cache or omit -d.` → exit 2 (`serve.py:70-75`) |
| `uvicorn` or `debug_server` cannot be imported | `Serving requires the optional debug dependencies: pip install 'magic-geo[debug]' (…)` → exit 2 (`serve.py:80-82`) |
| Auto-discovered cache turns out invalid (`ValueError` from `create_app`) | `Ignoring invalid automatic cache <dir>: <exc>` on stderr, then a **second** `create_app(None, …)` starts cacheless (`serve.py:85-96`) |
| Explicit `-d` cache invalid, or the cacheless retry also fails | `Unable to start web workbench: <exc>` → exit 2 (`serve.py:94-102`) |

`serve` otherwise blocks in `uvicorn.run` and never returns normally.

---

## Cache discovery and selection

`_CacheManager` resolves a cache in this order:

| Step | Rule | Source |
|---|---|---|
| 1 | If `debug_dir` was passed, resolve it (relative → against project root) and `select()` it immediately, fully validating before any live handle exists. | `debug_server.py:516-522`, `:569` |
| 2 | Otherwise, if `<workspace>/debug/manifest.json` is a file and its parent resolves inside the workspace, select that directory. | `debug_server.py:535-538` |
| 3 | Otherwise glob `<workspace>/**/debug/manifest.json`, keep candidates whose resolved parent stays inside the workspace, sort by `(st_mtime_ns, posix path)` descending, and take the newest. | `debug_server.py:539-550` |
| 4 | Otherwise start cacheless; `status()` reports `cache_available: false`. | `debug_server.py:678-688`, `:741` |

`_discover_default()` is re-run on **every** `get()` (`debug_server.py:680`), so a cache created after startup is picked up without a restart.

`GET /api/worlds` uses a different, broader scan (`debug_server.py:751-799`): every `<workspace>/**/manifest.json` (plus `<workspace>/manifest.json`), keeping only payloads whose `format`/`version` match exactly, and skipping any path containing a `.magic-geo-web` component or a component that starts with `.` and ends with `.staging` or `.backup`.

A cache is only accepted when `_DebugCache.__init__` (`debug_server.py:93-147`) succeeds, which requires:

- `manifest.json` and `sections.json` both resolve inside the cache root and are regular files;
- both parse as JSON objects;
- `manifest["format"] == "magic-geo-debug-cache"` and `type(manifest["version"]) is int and == 1` (`debug_export.py:30-31`; check at `debug_server.py:118-128`);
- `manifest["world"]["cell_count"] >= 1` and `manifest["layers"]` is a list of dicts with unique string `id`s;
- `_validate_manifest_files()` (`debug_server.py:173-236`) finds **every** referenced file: the cells parquet plus optional `details_jsonl`/`details_index`, the optional monthly parquet, each stage history's `stage_cells_parquet` + `stages_parquet` + optional `extras_jsonl`, at least one data file per family, all five mesh buffers (`positions`, `cell_ids`, `indices`, `pos_equirect`, `pos_mollweide`), the optional ParaView `pvd`, and that every name in `manifest["sections"]` exists as a key in `sections.json`.

The cache format version is independent of the package version, the HTTP API version and the world schema version (`docs/debugger.md:186-189`). A mismatched format or version is rejected outright rather than read best-effort.

---

## The browser shell: tabs, routing and keyboard model

Five semantic tabs are declared in `src/magic_geo/debug_ui/index.html:18-24` with `role="tablist"` / `role="tab"` / `aria-controls`.

| Tab | Panel id | Hash | Needs a cache? |
|---|---|---|---|
| Map | `#view-map` | `#map` | Yes — otherwise `#map-empty` empty state with "Create configuration" / "Open operations" buttons |
| Data | `#view-data` | `#data` | Yes — otherwise `#data-unavailable` notice |
| Config | `#view-config` | `#config` | No |
| Operations | `#view-operations` | `#operations` | No |
| API | `#view-api` | `#api` | No |

`setView()` (`app.js:1865`) hides every other panel, sets `aria-selected`/`tabIndex`, and pushes a history entry when the switch is user-initiated (`history.pushState(null, '', '#view')`), so browser Back/Forward moves between visited views. A `hashchange` listener re-syncs with `{ updateHash: false }`, so Back/Forward does not push again (`app.js:2968`). Entering a view triggers its refresh: Map resizes the renderer, Data reloads the current selection, Operations calls `refreshJobs()`, API calls `loadBackend()` (`app.js:1879-1882`).

Arrow-key tab navigation (`ArrowLeft`/`ArrowRight`/`Home`/`End`) is wired at `app.js:2953-2965`.

Two polling loops run from `main()` (`app.js:3239-3249`):

| Loop | Interval | Guard |
|---|---|---|
| `refreshJobs()` | 2500 ms | Skipped when `document.hidden`, and skipped when the active view is not `operations` **and** no job is active |
| `loadServerStatus()` | 5000 ms | Skipped when `document.hidden` |

The header (`index.html:25-32`) carries the cache `<select id="world-select">` (fed by `GET /api/worlds`, switched with `POST /api/worlds/select`), the `#cache-state` pill (`Connecting…` → `Cache ready` / `No cache` / `Switch failed` / `Startup error`), and `#workspace-state`, which renders `cache <dir> · workspace <ws> · error: … · v<version>` from `/api/status` (`app.js:1885-1901`).

The help overlay (`?`, the floating `?` button, or the docs-card `?`) is wired outside the map-only handlers so it works without a cache (`app.js:2975-2991`); it is assembled from `UI_GUIDE`, `KEY_REFERENCE` and `docsCoverage()` exported by `layer_docs.js`.

---

## Config view

Panels: a YAML editor on the left, a flattened schema reference on the right (`index.html:171-196`).

| Control | Element | Behaviour |
|---|---|---|
| Profile select | `#config-profile` | Populated from `GET /api/config/profiles`. Selecting a profile is **non-destructive** — it only prints `Selected <profile>. Choose Reset from profile to replace the editor.` (`app.js:3008-3016`). |
| Reset from profile | `#config-reset` | Fetches `GET /api/config/template?profile=…` and replaces the editor. Confirms first if there are unsaved edits, and refuses to apply a late response if the editor changed while loading (`app.js:2471-2497`). |
| YAML editor | `#config-yaml` | Raw textarea; `Tab` inserts two spaces (`app.js:3022-3029`). Every input bumps `state.configEditRevision`. |
| Validate YAML | `#config-validate` | `POST /api/config/validate`. Renders `source:line:column` plus dotted field paths from `ConfigError.to_dict()` issues (`app.js:2499-2540`, error shape at `src/magic_geo/config.py:70-82`). |
| Save as | `#config-name` | Default value `world`, `pattern="[A-Za-z0-9][A-Za-z0-9._-]*"`. Client adds `.yaml` when missing (`app.js:2542-2546`). |
| Save configuration | `#config-save` | `POST /api/config/save`. On `409` it asks "A configuration with this name already exists. Replace it?" and retries with `force: true` (`app.js:2576-2586`). |
| Download YAML | `#config-download` | Pure client-side `Blob` download; never touches the server filesystem (`app.js:2548-2550`). |
| Schema filter | `#schema-search` | Filters the flattened schema cards on path, type and description (`app.js:2459-2469`). |

The schema panel resolves `$ref` entries from `GET /api/config/schema` and flattens nested objects up to depth 12, including array item objects rendered as `path[]` (`app.js:2420-2457`). Each card shows dotted path, type, required flag, description, default and enum choices.

The default save name `world` produces `<workspace>/configs/world.yaml`, which is exactly the default `config` value of the `generate` and `validate-geo-suite` operations (`web_jobs.py:115`, `:149`) — the two views are wired to agree.

---

## Operations view

Three panels (`index.html:203-222`): the operation launcher, the jobs list, and the selected-job detail.

The form is **generated** from `GET /api/operations`, not hard-coded (`renderOperationForm`, `app.js:2671`). Field rendering:

| Catalog `kind` | Rendered control | Notes |
|---|---|---|
| `choice` (has `choices`) | `<select>`; a `—` blank option is prepended when not required | `app.js:2687-2691` |
| `boolean` | `<select>` with `Default` / `Yes` / `No` | blank means "omit, use server default" |
| `path_list` | `<textarea>` with placeholder `One path per line` | split on newlines client-side |
| `integer`, `number` | `<input type="number">` with `step`, `min`, `max` from `minimum`/`maximum` | |
| `path`, anything else | `<input type="text">` | |

An operation whose catalog entry has `available: false` disables the submit button and appends `This operation is unavailable until <dependency> is installed.` to the description (`app.js:2673-2676`). Only `export-rerun` declares `optional_dependency: "rerun"` (`web_jobs.py:237`); availability is computed with `importlib.util.find_spec` at catalog build time (`web_jobs.py:316`).

Empty fields are dropped before submit (`collectOperationArguments`, `app.js:2726-2747`), so the server default applies.

The jobs list rebuilds only when `selectedJobId | id:status | …` changes, so polling never steals keyboard focus or swaps a node under a click (`app.js:2792-2795`). The detail panel renders status pill, an **indeterminate** progress bar for active jobs (the server reports no progress field — `app.js:2838-2842`), meta table, normalized arguments, the bounded combined log, and artifact download links. Artifact hrefs are restricted client-side to same-origin paths or `http(s)` URLs so a `javascript:` scheme in server data cannot be rendered (`app.js:2820-2824`).

**Cancel job** asks `window.confirm('Cancel this job?')` first (`app.js:2906-2917`).

---

## Data view

The Data tab is the generic escape hatch: every exporter/API resource is browsable even when it has no bespoke map overlay.

| `#data-kind` value | Title | Source | Raw JSON link |
|---|---|---|---|
| `overview` | Overview | Client-side counts from the catalog + first 40 family names with `kind` and `row_count` | no |
| `scalars` | Scalars | `catalog.scalars` as a key/value table | no |
| `skipped` | Skipped outputs | Merged JSON of `skipped_sections`, `cells.skipped_fields`, `cells.skipped_layers`, `monthly.skipped_layers`, and per-history `skipped_layers` / `skipped_per_cell_fields` / `skipped_summary_fields` (`app.js:2311-2326`) | no |
| `layers` | Layers | `catalog.layers` as a table | no |
| `cells` | Cell schema | `catalog.cells` as formatted JSON | no |
| `stages` | Stage history | `GET /api/stage-summary/{history}` — first 500 rows plus a "Showing 500 of N stages" notice, then a **Retained stage extras** table (`app.js:2343-2358`) | yes |
| `families` | Record family | `GET /api/family/{name}?limit&offset&detail` | yes |
| `sections` | Model section | `GET /api/section/{name}` as formatted JSON | yes |

Controls: `#data-resource` (names from `catalog.stage_histories` / `families` / `sections`, `app.js:2228-2234`), `#family-detail` (`full` = nested JSONL records, `scalars` = compact Parquet sidecar), `#data-limit` (10/25/50/100, default 10) and a pager (`index.html:146-162`). The detail select and the pager are shown only for the `families` kind (`app.js:2250-2251`); every other kind returns its whole payload. The **Open raw JSON ↗** link points at the exact revision-pinned API URL that produced the view (`app.js:2380-2382`), which makes every screen reproducible from `curl`.

`jsonPreview()` truncates rendered JSON at 100,000 characters (`app.js:1810`); the raw link is the un-truncated path.

---

## Map view

Layout is sidebar / viewport / inspector (`index.html:36-124`).

### Rendering model

One merged indexed `THREE.BufferGeometry` with attributes `position`, `aPosEq`, `aPosMo`, `aCellId` (`app.js:378-385`), built from the five binary mesh buffers fetched in parallel from `/mesh/*` (`app.js:362-369`). Per-cell values live in an R32F `DataTexture` of size `ceil(sqrt(cellCount)) × ceil(cellCount / width)` indexed by cell id, initialized to the missing sentinel (`app.js:394-400`). Switching layer, stage or month uploads one `Float32Array`; **geometry is never rebuilt**.

`MISSING_SENTINEL = 3.0e38` (`app.js:14`) replaces `NaN` after every layer fetch because "NaN replacement survives every GPU driver". The hover readout treats any value `>= 1e37` as missing and prints `—` (`app.js:1789-1797`).

Scene constants: background `0x10141a`, `PerspectiveCamera(50, 1, 0.01, 100)` at `z = 3.0`, `OrbitControls` with `enableDamping`, `dampingFactor 0.08`, `minDistance 1.05`, `maxDistance 12` (`app.js:371-377`). Switching to a flat projection resets the camera to `z = 3.4` and the target to the origin (`app.js:3064-3067`). Picking renders encoded cell ids into an offscreen target and reads one pixel (`app.js:617-654`).

### Layer selection

Layers are grouped by `layer.source` into collapsible groups; kind badges are `numeric_stage → "stages"`, `categorical_stage → "stage cat"`, `numeric_monthly → "monthly"`, `categorical → "cat"` (`app.js:1561-1565`). The initial layer is `cells/elevation_m`, else the first `kind == "numeric"` layer, else the first layer (`app.js:2184-2186`).

`fetchLayerValues()` (`app.js:318`) keys an LRU on `` `${cacheIdentity}|${layer.id}|${stageKey}|${monthKey}` `` where only the axis the layer actually varies along participates, capped at 48 buffers (`app.js:340-342`). Stages `±1` and `±2` are prefetched (`app.js:346-359`). Stale responses are dropped through `fetchSeq`, `cacheEpoch` and `cacheContextIsCurrent(context)`; a failed fetch rolls the UI back to the previous layer and prints `Layer load failed: …` (`app.js:1444-1465`).

### Legend, colors and time

Numeric layers use the manifest `p2..p98` range, fixed across the whole time axis so one color is comparable between stages/months; `≤`/`≥` markers mark clipped true extremes. Categorical layers use golden-angle hues (`index * 0.61803398875`, `app.js:61`) both in JS and in the fragment shader (`app.js:145`), with category chips in the legend.

The stage bar (`#stagebar`) exposes a slider, an exact-value number input, prev/next buttons and a contextual label. Slider scrubbing updates the label immediately but coalesces the layer fetch on a 120 ms timer, so dragging across N stages issues one request (`app.js:3136-3151`).

### Cell inspector

A click (movement under 4 px, `app.js:3177-3186`) picks a cell and opens `GET /api/cell/{id}`. The panel renders, in order: a field filter, **Ledger slices (per stage)** sparklines with a marker at the current stage when the active layer belongs to that history, **Monthly** sparklines, **Fields** (every scalar column plus merged detail-sidecar fields), and **Adjacency (N edges)** rows showing `plate_boundary` / `land_water_transition` / `biome_transition` flags, the great-circle distance in km, and a click-through link to the neighbouring cell (`app.js:1674-1770`).

### Map keyboard reference

| Key | Action | Source |
|---|---|---|
| `1` / `2` / `3` | Globe / Equirectangular / Mollweide | `app.js:3218-3220` |
| `w` / `b` / `g` | Wireframe / plate boundaries / graticule | `app.js:3221-3223` |
| `,` / `.` | Previous / next stage or month | `app.js:3216-3217` |
| `d` | Toggle the layer docs card | `app.js:3224` |
| `/` | Focus the layer filter | `app.js:3225` |
| `?` | Toggle help (works without a cache) | `app.js:2987-2990` |
| `Esc` | Close the inspector, else blur the focused field; closes help first | `app.js:3206-3212`, `:2982-2985` |

Shortcuts are suppressed while the help overlay is open and while focus is inside an `input`, `textarea` or `select`.

### Export PNG / Prompt .md

Two toolbar buttons (`index.html:82-85`) produce the browser side of the `export-debug-map` pair. Both are **entirely client-side**: no image-generation service is contacted.

- **Export PNG** re-renders the scene synchronously at the final projection state (so an in-progress morph cannot leak into the image), copies the WebGL canvas into a 2-D canvas, and encodes `image/png` (`app.js:932-983`).
- **Prompt .md** writes a `text/markdown` GPT Image prompt with a color codex; it reuses the exact view of the last PNG for this data slice when one exists, so the Markdown never invents a companion filename the user never downloaded (`app.js:894-906`, `:1268-1284`).

Both are disabled when the snapshot is not current or when `exportMeshIssue()` fires — `cells_without_ring > 0` or `triangle_count < 1` (`app.js:837-846`). Filenames share one base built by `mapExportBaseName()` (`app.js:778`) including a `view-<fingerprint>` component from the FNV-1a-64 `mapViewFingerprint()` (`app.js:755`), which the CLI reimplements byte-for-byte for parity. See [Debug Exports and Visualization](./16-debug-and-visualization.md).

---

## Backend and API view

Two panels (`index.html:230-233`): **Backend information** renders `GET /api/backend` (which delegates to `magic_geo.api.backend_info()`) as formatted JSON, isolating a probe failure as a warning notice instead of breaking the workbench (`app.js:2940-2949`); the right panel embeds Swagger in an `<iframe src="/api/docs">`, with an **Open Swagger ↗** button to `/api/docs` in a new tab.

| Control | Element | Behaviour |
|---|---|---|
| Refresh backend | `#backend-refresh` | Calls `loadBackend()`; shows a `Loading…` pill, then the probe payload inside a `<pre>` (`app.js:2941-2945`). Entering the API view calls the same function (`app.js:1882`). |
| Backend output | `#backend-output` | A failed probe — the route answers `503 backend probe failed: …` (`debug_server.py:944-951`) — is rendered as a warning notice in this panel only (`app.js:2946-2948`). |
| Open Swagger ↗ | `<a href="/api/docs" target="_blank" rel="noopener">` | Opens the same Swagger UI in a new tab (`index.html:228`). |
| Interactive documentation | `#api-docs-frame` | `<iframe src="/api/docs">` (`index.html:232`). |

This view needs no cache: both `/api/backend` and `/api/docs` are always-available routes, so it works on a cacheless start. What `backend_info()` actually reports is documented in [Compute Backends](./09-compute-backends.md), not here.

---

## The job system

### Operation catalog

Eleven executable operations (`web_jobs.py:109-243`) plus four non-executable equivalents (`web_jobs.py:246-275`). `GET /api/operations` returns `{operations, equivalents, coverage}` where `coverage = {cli_command_count: 15, background_operation_count: 11, equivalent_view_count: 4}` (`web_jobs.py:330-334`).

| Operation id | CLI command | Title |
|---|---|---|
| `generate` | `generate` | Generate world |
| `validate` | `validate` | Validate world |
| `validate-geo` | `validate-geo` | Validate natural geography |
| `validate-geo-suite` | `validate-geo-suite` | Run geo validation suite |
| `calibrate` | `calibrate` | Calibrate world |
| `calibrate-ensemble` | `calibrate-ensemble` | Calibrate ensemble |
| `derive-targets` | `derive-targets` | Derive calibration targets |
| `render` | `render` | Render SVG map |
| `render-raster` | `render-raster` | Render raster map |
| `export-debug` | `export-debug` | Export browser/ParaView cache |
| `export-rerun` | `export-rerun` | Export Rerun recording (requires `rerun`) |

| Equivalent id | `equivalent_view` | Why it is not a job |
|---|---|---|
| `init-config` | `config` | Provided by the Config view and `/api/config/*` |
| `backend` | `api` | Provided by `/api/backend` and the API view |
| `export-debug-map` | `map` | Provided by the Map view's Export PNG / Prompt .md controls |
| `serve` | `current` | This process is the active serve operation |

Field descriptors carry `name`, `label`, `kind`, `flag`, `required`, `default`, `help`, `cli`, `workspace_relative`, and optionally `choices`, `minimum`, `maximum`, `path_role`, `negative_flag` (`_field`, `web_jobs.py:53-91`).

### Per-operation parameters

**`generate`** (`web_jobs.py:110-126`)

| Field | Kind | Flag | Default | Bounds / choices | Role |
|---|---|---|---|---|---|
| `config` | path | `--config` | `runs/configs/world.yaml` | — | input, `workspace_relative` |
| `output` | path | `--output` | `runs/world.json` | — | output |
| `summary` | path | `--summary` | — | — | output |
| `cells_csv` | path | `--cells-csv` | — | — | output |
| `cells` | integer | `--cells` | — | `>= 128` | — |
| `geo_only` | boolean | `--geo-only` | `false` | — | — |
| `world_format` | choice | `--format` | `auto` | `auto`, `json`, `mgeo` | — |
| `open_in_web` | boolean | *(none, `cli: false`)* | `true` | — | UI-only |
| `debug_output` | path | *(none, `cli: false`)* | `runs/debug` | — | output, becomes a **cache** artifact when `open_in_web` |
| `debug_vtu` | boolean | *(none, `cli: false`)* | `false` | — | UI-only |

**`validate`** (`web_jobs.py:127-132`): `world` (path, `--world`, **required**, input).

**`validate-geo`** (`web_jobs.py:133-143`)

| Field | Kind | Flag | Default | Choices | Role |
|---|---|---|---|---|---|
| `world` | path | `--world` | — (required) | — | input |
| `profile` | choice | `--profile` | `generic` | `generic`, `earthlike` | — |
| `output` | path | `--output` | — | — | output |
| `fail_on_warnings` | boolean | `--fail-on-warnings` | `false` | — | — |

**`validate-geo-suite`** (`web_jobs.py:144-154`)

| Field | Kind | Flag | Default | Role |
|---|---|---|---|---|
| `config` | path | `--config` | `runs/configs/world.yaml` | input, `workspace_relative` |
| `matrix` | path | `--matrix` | — (**required**) | input |
| `output` | path | `--output` | `runs/geo_validation.json` | output |
| `summary` | path | `--summary` | — | output |

The matrix is deliberately required: an installed wheel must not assume the repository's example `configs/geo_validation_matrix.yaml` exists (`web_jobs.py:150`).

**`calibrate`** (`web_jobs.py:155-167`)

| Field | Kind | Flag | Default | Role |
|---|---|---|---|---|
| `world` | path | `--world` | — (required) | input |
| `targets` | path | `--targets` | — (**required**) | input |
| `output` | path | `--output` | `runs/calibration.json` | output |
| `summary` | path | `--summary` | — | output |
| `require_all_metrics` | boolean | `--require-all-metrics` | `false` | — |
| `require_all_passed` | boolean | `--require-all-passed` | `false` | — |

**`calibrate-ensemble`** (`web_jobs.py:168-181`)

| Field | Kind | Flag | Default | Role |
|---|---|---|---|---|
| `config` | path | `--config` | — (**required**) | input |
| `matrix` | path | `--matrix` | — (**required**) | input |
| `targets` | **path_list** | `--targets` | — (**required**) | input, one path per line, flag repeated per item |
| `output` | path | `--output` | `runs/calibration_ensemble.json` | output |
| `summary` | path | `--summary` | — | output |
| `require_all_metrics` | boolean | `--require-all-metrics` | `false` | — |
| `require_all_passed` | boolean | `--require-all-passed` | `false` | — |

**`derive-targets`** (`web_jobs.py:182-191`): `sources` (path, `--sources`, **required**, input), `output` (path, `--output`, `runs/calibration_targets.json`, output), `summary` (path, `--summary`, output).

**`render`** (`web_jobs.py:192-207`)

| Field | Kind | Flag | Default | Bounds / choices | Role |
|---|---|---|---|---|---|
| `world` | path | `--world` | — (**required**) | — | input |
| `output` | path | `--output` | `runs/world.svg` | — | output |
| `width` | integer | `--width` | `1600` | `320…6400` | — |
| `height` | integer | `--height` | `800` | `160…3200` | — |
| `projection` | choice | `--projection` | `equirectangular` | `equirectangular`, `mollweide`, `orthographic` | — |
| `labels` | boolean | `--labels` / `--no-labels` | `false` | — | — |
| `max_cells` | integer | `--max-cells` | — | `>= 128` | — |
| `contours` | boolean | `--contours` / `--no-contours` | `true` | — | — |
| `contour_interval` | number | `--contour-interval` | `500.0` | `>= 50.0` | — |

**`render-raster`** (`web_jobs.py:208-221`): same `world`/`width`/`height`/`projection`/`max_cells` fields, `output` default `runs/world.ppm`, plus `texture` (boolean, `--texture` / `--no-texture`, default `true`).

**`export-debug`** (`web_jobs.py:222-232`)

| Field | Kind | Flag | Default | Bounds | Role |
|---|---|---|---|---|---|
| `world` | path | `--world` | — (**required**) | — | input |
| `output` | path | `--output` | `runs/debug` | — | output, **`kind: "cache"`** |
| `vtu` | boolean | `--vtu` / `--no-vtu` | `true` | — | — |
| `elevation_exaggeration` | number | `--elevation-exaggeration` | `30.0` | `>= 1.0` | — |

**`export-rerun`** (`web_jobs.py:233-242`): `world` (required input), `output` (path, `--output`, `runs/world.rrd`, output). Catalog entry reports `available: false` and `dependency: "rerun"` when `importlib.util.find_spec("rerun")` returns `None`.

### Value normalization

`_normalize_scalar()` (`web_jobs.py:823-867`) enforces the declared kind before anything reaches a command line:

| Kind | Accepted | Rejected |
|---|---|---|
| `boolean` | `true` / `false` only | anything non-`bool` → `<name> must be true or false` |
| `integer` | `int`, integral `float`, base-10 `str`; range `-2^63 … 2^63-1` | `bool`, non-integral float, non-finite, other types |
| `number` | anything `float()` accepts, must be finite | `NaN`/`Inf` → `<name> must be finite` |
| `choice`, `string` | coerced with `str()`, then checked against `choices` | `<name> must be one of: …` |

`minimum` / `maximum` are applied after conversion. Unknown argument names are rejected up front: `unknown arguments for <operation>: …` (`web_jobs.py:873-876`).

Command assembly (`web_jobs.py:936-949`): fields with `cli: false` are recorded in `arguments` but never appear in the argv. Booleans append `flag` when true, `negative_flag` when false and one exists, and nothing otherwise. `path_list` repeats `flag value` per item.

---

## Job lifecycle state machine

`JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled"` (`web_jobs.py:38`).

```text
            submit()                _run() start                exit 0
   (none) ──────────▶ queued ─────────────────────▶ running ─────────────▶ succeeded
                        │                             │
              cancel()  │                             │ exit != 0
                        ▼                             ▼
                    cancelled                       failed
                        ▲                             ▲
                        │  cancel() before commit     │  worker exception
                        └─────────────────────────────┘  (exit_code = -1)
```

`WebJob` fields (`web_jobs.py:350-374`):

| Field | Type | Meaning |
|---|---|---|
| `id` | str | `uuid.uuid4().hex[:12]` — 12 hex characters |
| `operation` | str | catalog id |
| `arguments` | dict | normalized values, including `cli: false` UI-only fields |
| `command` | list[str] | exact argv, starting with `sys.executable` |
| `status` | JobStatus | see above |
| `created_at` / `started_at` / `finished_at` | ISO-8601 UTC or `null` | `datetime.now(timezone.utc).isoformat()` |
| `exit_code` | int or `null` | process exit code, or `-1` for a worker exception |
| `log` | str | combined stdout+stderr, bounded |
| `artifacts` | list[dict] | `{name, path, kind, available[, bytes]}` |
| `cache_dir` | str or `null` | project-relative path of a published cache |

`public()` returns all of the above; `summary()` (used by `GET /api/jobs`) drops `arguments`, `command` and `log` (`web_jobs.py:392-405`).

Run sequence (`_run`, `web_jobs.py:1223-1298`):

1. Bail immediately if cancellation was already requested; else set `running` and `started_at`.
2. Snapshot pre-run fingerprints of every `kind == "file"` artifact (`_snapshot_artifact_inputs`, `web_jobs.py:1015`).
3. Echo `$ <command>` into the log.
4. `export-debug` goes through `_run_debug_export`; every other operation goes through `_spawn`.
5. If `generate` succeeded and was not cancelled, capture its artifacts **now**, before the optional cache export, so a failing export cannot lose a complete world/summary/CSV.
6. If `generate` succeeded and `open_in_web` is true, build a second argv `… export-debug --world <output> --output <debug_output> (--vtu|--no-vtu)` and run it through `_run_debug_export` (`web_jobs.py:1250-1265`). The final exit code becomes that of the export.
7. Final status: `cancelled` if requested, else `succeeded` when the code is 0, else `failed`; `_finalizing` is set at the same instant for the non-cancelled branch.
8. Capture artifacts on success, **or** on failure when the operation is in `_REPORTING_OPERATIONS = {validate-geo, validate-geo-suite, calibrate, calibrate-ensemble}` (`web_jobs.py:41-46`, `:1274-1277`).
9. `finally`: clear `_process`/`_publishing`/`_finalizing`, commit status, exit code and `finished_at`, then invoke `on_complete`. A failing callback is logged as `job completion callback failed: …` rather than raised.

An uncaught worker exception logs `web job failed: <Type>: <msg>` and sets `exit_code = -1` (`web_jobs.py:1278-1282`).

`on_complete` in the server (`debug_server.py:888-894`) selects `job.cache_dir` as the live cache when a job succeeded and published one, swallowing a `ValueError` if selection fails.

### Concurrency and limits

| Limit | Value | Source |
|---|---|---|
| Concurrent jobs | 1 — `ThreadPoolExecutor(max_workers=1, thread_name_prefix="magic-geo-web")` | `web_jobs.py:445` |
| Retained job records | `max_jobs = 100`; terminal jobs evicted oldest-first (with their artifact directories); still full → `job queue is full (100); wait for or cancel existing work` | `web_jobs.py:419`, `:518-532` |
| Log cap | `max_log_bytes = 2_000_000`; the tail is kept behind a `[earlier output truncated]\n` prefix | `web_jobs.py:418`, `:1177-1183` |
| Subprocess environment | inherited, plus `PYTHONUNBUFFERED=1`; `cwd = project_root`; stdout+stderr merged, `text=True`, `bufsize=1`; `start_new_session=True` on POSIX | `web_jobs.py:1185-1197` |

Submit-time deduplication and conflict rules (`web_jobs.py:499-517`):

| Situation | Result |
|---|---|
| An active job has the same `(operation, normalized arguments)` | That job is returned; no new job is created |
| A new declared output conflicts with an active job's artifact | `JobInputError: output already targeted by an active job: …` → `422` |
| Two declared outputs of the *same* job conflict | `JobInputError: declared outputs overlap: A and B` |

`_artifacts_conflict()` (`web_jobs.py:986-996`) treats equal paths as conflicting, and treats a `kind == "cache"` artifact as conflicting with anything nested beneath it.

---

## Cancellation and the commit boundary

`cancel()` (`web_jobs.py:543-570`):

| Job state | Effect |
|---|---|
| `succeeded` / `failed` / `cancelled` | No-op; the current record is returned |
| `_publishing` or `_finalizing` set | **No-op** — the record is returned unchanged |
| `queued` | Status becomes `cancelled` immediately, `finished_at` set; no subprocess is ever started |
| `running` | `_cancel_requested = True`, then `SIGTERM` to the process group via `os.killpg` on POSIX (`process.terminate()` elsewhere); a 5.0 s daemon `threading.Timer` escalates to `SIGKILL` / `process.kill()` if the process is still alive (`web_jobs.py:560-569`, `:1211-1221`) |

The `_publishing` / `_finalizing` guard exists because cache publication and terminal artifact snapshotting are commit phases: the code comment states that "once either begins, cancellation cannot be made truthful without rolling back a completed publication/snapshot" (`web_jobs.py:550-553`). A late cancel is therefore ignored and the job completes normally, rather than reporting a false `cancelled` state after it already published a cache.

`_spawn` also re-checks `_cancel_requested` right after `Popen` and terminates immediately if a cancel landed in the gap (`web_jobs.py:1198-1202`).

`close()` (`web_jobs.py:452-468`) marks queued jobs `cancelled`, cancels running jobs, then `executor.shutdown(wait=True, cancel_futures=True)`. The FastAPI lifespan calls `jobs.close()` before `caches.close()` (`debug_server.py:903-909`), so no child can still be writing when DuckDB connections are closed.

---

## Artifact snapshotting

Artifacts are declared at submit time from every field with `path_role == "output"` (`web_jobs.py:904-922`):

```json
{"name": "output", "path": "runs/world.json", "kind": "file", "available": false}
```

`kind` is `"cache"` for `export-debug.output` and for `generate.debug_output` when `open_in_web` is enabled; otherwise `"file"`. A `cli: false` output field that is not a cache — i.e. `debug_output` with `open_in_web` disabled — is deliberately **not** declared, so it neither reserves the path nor exposes a pre-existing file there (`web_jobs.py:912-914`).

Snapshotting (`_capture_artifacts`, `web_jobs.py:1026-1072`):

1. Only `kind == "file"` artifacts are considered.
2. The source must resolve inside the workspace.
3. Its post-run fingerprint `(st_dev, st_ino, st_size, st_mtime_ns)` must exist **and differ** from the pre-run one. An untouched pre-existing file is never presented as new output.
4. It is `shutil.copy2`'d to `<workspace>/.magic-geo-web/artifacts/<job_id>/<index>/<name>` via a `.<name>.<uuid>.tmp` temporary plus `os.replace`.
5. On success the artifact gains `available: true` and `bytes`. A snapshot failure logs `unable to snapshot <name>: <err>` and leaves the artifact unavailable.

Downloads (`artifact_path`, `web_jobs.py:572-596`) re-verify: negative index → `KeyError`; unknown job or index → `KeyError` → `404 unknown artifact`; `available == false` → `FileNotFoundError` → `404 artifact is not available`; the resolved snapshot must still be inside `_artifact_root`; and its fingerprint must still equal the recorded one. The route returns `FileResponse(path, filename=path.name)` (`debug_server.py:1081-1089`).

Consequences worth stating explicitly:

- A later job overwriting or deleting the requested output does **not** change an earlier job's download.
- Reporting operations that write a report and then exit non-zero for a requested policy gate still expose that report from the failed job.
- Cancelled jobs never snapshot partial output.
- Job records and their snapshot links are **process-local**: they vanish on eviction (`max_jobs`) or server restart. The requested output files persist independently (`docs/debugger.md:111-113`).

---

## Staging-then-publish for cache outputs

Web-triggered cache exports never build inside the selected cache. `_run_debug_export` (`web_jobs.py:1121-1175`):

1. `destination.parent.mkdir(parents=True, exist_ok=True)`.
2. `tempfile.mkdtemp(prefix=f".{destination.name}.{job.id}.", suffix=".staging", dir=destination.parent)` — a job-private sibling.
3. The argv's `--output` value is rewritten to the staging path. If the command has no `--output`, it raises `export-debug command has no output argument`.
4. Run. If the exit code is non-zero **or** cancellation was requested, return without publishing.
5. `_validate_debug_cache(staging)` (`web_jobs.py:1074-1098`) parses `manifest.json` + `sections.json`, requires both to be objects, requires `format == "magic-geo-debug-cache"` and `version` to be exactly the int `1`, and requires `world` to be a dict and `layers` to be a list.
6. Set `_publishing = True`, then call the publisher: the server's `caches.publish` when wired (`debug_server.py:900`), else the standalone `_replace_cache_directory` fallback (`web_jobs.py:1100-1119`).
7. On completion set `_finalizing = True` in the same locked section that clears `_publishing`, keeping the publish→terminal transition indivisible from the cancellation API's point of view.
8. The published path must still resolve inside the workspace, else `published debug cache escaped the web workspace`.
9. `job.cache_dir` is set to the project-relative published path.
10. `finally`: the staging directory is always `shutil.rmtree`'d.

`_CacheManager.publish()` (`debug_server.py:601-666`) is the authoritative path:

| Phase | Action |
|---|---|
| Pre-lock | Both staging and destination must be inside the workspace; destination must not exist as a non-directory; the staged cache is fully constructed as a `_DebugCache` and closed again — validation happens **before** the lock and before the live path is touched. |
| Under the manager lock | If the destination exists, `os.replace(destination, backup)` where `backup = .{name}.{uuid4().hex}.backup`; then `os.replace(staging, destination)`; then reopen `_DebugCache(destination)` and re-stat `manifest.json`. |
| Failure inside the lock | Remove the moved-in destination and `os.replace(backup, destination)` to roll back. |
| Success | Swap the live cache handle, update `_selected` / `_fingerprint`, clear `_error`, close the previous handle (a close failure is swallowed so cleanup cannot roll the filesystem back under a live replacement), and delete the backup. |

Because the swap happens under the same lock `with_cache()` uses, cache-backed reads are paused for the duration. Failed or cancelled exports discard staging and leave the previously selected cache intact.

This guarantee applies to **browser jobs only**. Direct CLI `export-debug` writes the path it is given (`docs/debugger.md:149-151`).

---

## Input and output path policy

`_resolve_path()` (`web_jobs.py:598-615`):

| Rule | Detail |
|---|---|
| Expansion | `Path(value).expanduser()`; relative paths resolve against `project_root` |
| Input root | must be inside `project_root`, else `input path must stay inside <root>: <value>` |
| Input kind | must be an existing regular file, else `input path must name an existing regular file: <value>` |
| Output root | must be inside `workspace`, else `output path must stay inside <root>: <value>` |
| Output exclusions | may not equal the workspace root (`output path must not replace the web workspace`); may not be under `.magic-geo-web` (`output path uses the reserved web-internal directory`) |

Post-assembly checks (`web_jobs.py:954-982`):

- an output may not equal any resolved input → `output must not replace an input: <path>`;
- a `kind == "cache"` output that already exists must be a directory → `cache output must be a directory path: <path>`;
- a cache output may not equal or contain any input → `cache output must not replace or contain an input: <cache> contains <input>`.

### Transitive input confinement

CLI workflows accept absolute paths inside manifests; the browser is narrower. Two operations have their nested references resolved and confined **before** a subprocess can read them (`web_jobs.py:617-639` explains the rationale):

| Operation | Manifest walked | Fields followed |
|---|---|---|
| `derive-targets` | `sources` (JSON) | `sources[i].path`, `sources[i].dbf_path`, `sources[i].prj_path`; when `format` is `hydrobasins_archive_catalog` or `hydrobasins_catalog`, the referenced catalog's `archives[j].path` (`web_jobs.py:699-750`) |
| `validate-geo-suite` | `matrix` (YAML) | `scenarios[i].empirical_calibration.target_bundle`, then that bundle's `derivation.source_manifests[j].path` and `derivation.supplemental_target_derivations[j].path` (`web_jobs.py:752-812`) |

Each discovered path must be a non-empty string, must resolve inside `project_root`, and must be an existing regular file. Manifests themselves are bounded first (`web_jobs.py:641-697`): 8 MiB text limit, and for YAML a streaming `yaml.parse` pass capped at 20,000 events, depth 64 and 64 aliases before `yaml.safe_load` runs.

A rejected path is a policy error, not a missing CLI feature.

---

## REST API route table

FastAPI application metadata (`debug_server.py:911-920`): title `magic-geo web workbench API`, version `1.0`, `docs_url="/api/docs"`, `redoc_url="/api/redoc"`, `openapi_url="/api/openapi.json"`, `default_response_class=_StrictJSONResponse`.

| Method | Path | Purpose | Request | Response | Errors |
|---|---|---|---|---|---|
| GET | `/api/status` | Cache availability, selected path, revision, workspace, version | — | `{cache_available, cache_dir, cache_error, cache_revision, workspace, project, version, api_docs}` | — |
| GET | `/api/operations` | Typed catalog of every executable/equivalent CLI feature | — | `{operations[], equivalents[], coverage{cli_command_count, background_operation_count, equivalent_view_count}}` | — |
| GET | `/api/backend` | Native CPU/OpenCL/CUDA probe | — | `magic_geo.api.backend_info()` dict | `503 backend probe failed: …` |
| GET | `/api/config/schema` | Described JSON Schema incl. `x-magic-geo.profiles` | — | JSON Schema object | — |
| GET | `/api/config/profiles` | Profile list and UI default | — | `{profiles:[{name, description}], default:"earthlike"}` | — |
| GET | `/api/config/template` | Normalized YAML + values for a profile | query `profile` (default `earthlike`) | `{profile, yaml, config}` | `422` `ConfigError.to_dict()` |
| POST | `/api/config/render` | Profile plus dotted overrides → YAML | `{profile?, overrides?}`, extra keys forbidden | `{profile, yaml, config}` | `422` |
| POST | `/api/config/validate` | Strict YAML validation and normalization | `{yaml}` | `{valid: true, yaml, config}` | `413` >1,000,000 bytes; `422` |
| POST | `/api/config/save` | Atomic workspace-confined save | `{yaml, name?, force?}` | `{saved: true, path, yaml}` | `413`; `422` name/symlink/escape/config; `409` exists without `force`; `500` OSError |
| GET | `/api/jobs` | List jobs, newest first | — | `{jobs:[summary()]}` | — |
| POST | `/api/jobs` | Queue one fixed operation (**202**) | `{operation, arguments?}` | `public()` | `422 JobInputError` |
| GET | `/api/jobs/{job_id}` | Full job record incl. command and log | — | `public()` | `404 unknown job <id>` |
| POST | `/api/jobs/{job_id}/cancel` | Cancel queued/running work | — | `public()` | `404 unknown job <id>` |
| GET | `/api/jobs/{job_id}/artifacts/{artifact_index}` | Download an immutable snapshot | — | `FileResponse` with `filename=<basename>` | `404 unknown artifact`, `404 artifact is not available` |
| GET | `/api/worlds` | Discover compatible caches in the workspace | — | `{worlds:[{id, cache_dir, name, cell_count, generation_scope, selected}]}` | — |
| POST | `/api/worlds/select` | Select a workspace cache | `{cache_dir}` | `caches.status()` | `422` unresolvable / outside workspace / no manifest |
| GET | `/api/manifest` | Full exporter manifest | query `revision?` | manifest dict | `409`, `500` |
| GET | `/api/catalog` | UI-oriented subset of the manifest | query `revision?` | `{world, scalars, layers, stage_histories, families, sections, skipped_sections, cells, monthly, mesh}` | `409`, `500` |
| GET | `/api/layer/{layer_id:path}` | One value per cell | query `stage? >= 0`, `month? 0…11`, `format=f32\|arrow`, `revision?` | binary Float32 or Arrow IPC stream | `400`, `404`, `409`, `422` |
| GET | `/api/cell/{cell_id}` | Complete cell + ledgers + monthly + adjacency | query `revision?` | `{cell, ledgers, adjacency_edges, monthly, complete}` | `404`, `409`, `500` |
| GET | `/api/stage-summary/{history_name:path}` | Per-stage scalar table + retained extras | query `revision?` | `{name, stage_count, columns, rows[, extras]}` | `404 unknown stage history …`, `409` |
| GET | `/api/family/{family_name:path}` | Paged full or scalar records | query `limit=100 (1…5000)`, `offset=0 (0…2^63-1)`, `detail=full\|scalars`, `revision?` | `{name, total, offset, limit, next_offset, detail, rows}` | `404`, `409`, `422` |
| GET | `/api/section/{section_name:path}` | One exported dictionary/graph/clock section | query `revision?` | raw section JSON | `404 unknown section …`, `409` |
| GET | `/api/plate-boundaries` | Lat/lon boundary segments | query `revision?` | `[[lat1, lon1, lat2, lon2], …]` | `409` |
| GET | `/mesh/{asset_path:path}` | Confined binary GPU mesh asset (**not in the schema**) | query `revision?` | `application/octet-stream`, `Cache-Control: no-store` | `400`, `404`, `409` |
| GET | `/*` | Static UI (`debug_ui/`, `html=True`) | — | HTML/JS/CSS | `404` |

Every cache-backed route funnels through `caches.with_cache(action, revision)` (`debug_server.py:723`) and therefore shares two error shapes:

- `409 no debug cache selected; generate a world or run export-debug` when nothing is selected (`debug_server.py:684-687`);
- `409 debug cache revision changed; refresh status and retry` when a supplied `revision` no longer matches (`debug_server.py:734-738`).

---

## Per-route detail

### `GET /api/layer/{layer_id:path}`

Layer ids are the manifest ids (`debug_export.py:226`, `:313`, `:463`, `:480`) and contain a `/`, hence the `:path` converter:

| Layer `kind` | Id shape | `source` | Time axis | Table read |
|---|---|---|---|---|
| `numeric` | `cells/<column>` | `cells` | none | `SELECT id, "<col>" FROM read_parquet(cells.parquet)` |
| `categorical` | `cells/<column>` | `cells` | none | same, values mapped to category index |
| `numeric_monthly` | `monthly/<column>` | `cells_monthly` | 12 months | `… WHERE month = ?` |
| `numeric_stage` | `<history>/<field>` | `<history>` | history-specific | `… WHERE stage_idx = ?` |
| `categorical_stage` | `<history>/<field>` | `<history>` | history-specific | same, values mapped to category index |

`layer_values()` (`debug_server.py:277-331`) allocates `[NaN] * cell_count`, so cells absent from the queried slice stay missing. Category mapping uses the manifest's sorted `categories` list; a value not in that list becomes `-1.0` (`debug_server.py:318-324`). Numeric values that are non-finite in Parquet become `NaN` (`debug_server.py:326-330`).

Errors specific to this route:

| Status | Detail |
|---|---|
| `400` | `invalid NUL in field name`; `month <n> out of range`; `stage <n> out of range`; `cache paths must be relative`; `cache path escapes root: …` |
| `404` | `unknown layer <id>`; `monthly table is unavailable`; `missing stage history <source>`; `cells table is unavailable`; `missing cache file <rel>` |
| `422` | `format` not in `{f32, arrow}`, `stage < 0`, `month` outside `0…11` |

Both response bodies set `Cache-Control: no-store` (`debug_server.py:802-827`).

### `GET /api/cell/{cell_id}`

`cell_record()` (`debug_server.py:359-415`) composes four reads:

| Key | Content |
|---|---|
| `cell` | `SELECT * FROM cells.parquet WHERE id = ?`, then merged with the indexed detail sidecar record for that cell |
| `ledgers` | For every stage history: `SELECT * … WHERE cell_id = ? ORDER BY stage_idx`, reshaped to `{stage_idx: [...], fields: {col: [...]}}` with `stage_idx` and `cell_id` removed from `fields` |
| `adjacency_edges` | Rows of the `cell_adjacency_edges` family Parquet where `cell_a_id = ?` OR `cell_b_id = ?` |
| `monthly` | `SELECT * … WHERE cell_id = ? ORDER BY month`, one array per column other than `cell_id`/`month` |
| `complete` | `bool(manifest["cells"]["details_jsonl"])` — false for caches exported before the sidecar existed |

The sidecar is read by byte offset: `tables/cell_details_index.json` is loaded once and cached under the cache lock, then `seek(offset)` + `readline()` (`debug_server.py:335-357`). A malformed index yields `500 invalid cell details index`; a malformed record yields `500 invalid cell details record`.

Errors: `404 cell <id> out of range` (outside `0…cell_count-1`), `404 cell <id> not found` (no Parquet row).

### `GET /api/family/{family_name:path}`

Selection logic (`debug_server.py:453-484`) is order-sensitive:

| Family shape | `detail=full` | `detail=scalars` |
|---|---|---|
| flat (`parquet` only) | Parquet rows, reported `detail: "full"` | Parquet rows, reported `detail: "full"` |
| nested (`jsonl` only) | JSONL records | JSONL records |
| nested with sidecar (`jsonl` + `scalars_parquet`) | JSONL records, `detail: "full"` | sidecar Parquet rows, `detail: "scalars"` |

`total` comes from `family["row_count"]` (falling back to the returned row count). `next_offset` is `offset + len(rows)` when that is below `total`, else `null`. `404 unknown family <name>` for an unknown name; `404 family <name> has no readable data` when the manifest entry declares no file.

### `GET /api/stage-summary/{history_name:path}`

Returns the whole per-stage scalar table ordered by `stage_idx` — there is no pagination. When the history declares `extras_jsonl`, up to `max(1, stage_count)` extras records are read from offset 0 and attached as `extras` (`debug_server.py:431-437`).

### `POST /api/config/save`

The request body is `ConfigSaveRequest` (`debug_server.py:843-845`): `yaml` (required), `name` (`min_length=1`, `max_length=128`, server-side default `web-config.yaml` when the field is omitted — the browser always sends `#config-name`, so `world.yaml` is what the UI produces), and `force` (default `false`). Extra keys are rejected by `_StrictRequest`'s `extra="forbid"` (`debug_server.py:830-831`).

Ordered checks (`debug_server.py:1007-1054`):

1. UTF-8 size ≤ 1,000,000 bytes, else `413`. A YAML string that is not encodable as UTF-8 raises the `ConfigError` payload `422` instead (`debug_server.py:861-874`).
2. `name` matches `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` and is not `.` or `..`, else `422 name must use only letters, digits, '.', '_', and '-'`.
3. `.yaml` appended unless the name already ends in `.yaml` or `.yml`.
4. YAML parsed with the strict duplicate-key-safe parser; a `ConfigError` becomes `422` with its full `{message, source, issues[, line, column]}` payload.
5. `<workspace>/configs` must not be a symlink; it is created; its resolved form must stay inside the workspace.
6. The target must not be a symlink and must resolve inside the configs directory.
7. Existing target without `force` → `409 configuration already exists: <name>; confirm overwrite to replace it`.
8. `write_config(target, config, force=…)`; `FileExistsError` → `409`, other `OSError` → `500 unable to save configuration: …`.

### `POST /api/worlds/select`

Resolves `cache_dir` (relative → against the project root), requires it to resolve inside `jobs.workspace`, then calls `caches.select()`, which fully constructs and validates the replacement `_DebugCache` before swapping any live handle (`debug_server.py:569-589`). Any `ValueError` — including `no manifest.json in <dir>` and every `_DebugCache` validation failure — surfaces as `422`. The response is the fresh `caches.status()`.

### `GET /mesh/{asset_path:path}`

Registered with `include_in_schema=False`, so it does **not** appear in Swagger/ReDoc/OpenAPI (`debug_server.py:1191`). Paths are resolved under `<cache>/mesh` with a double confinement check (mesh root inside the cache, asset inside the mesh root; `debug_server.py:255-267`). The bytes are read **inside** `with_cache`, i.e. while the manager lock is held, because "a cache may be atomically replaced at the same directory. Stable mesh URLs must therefore be materialized while the cache-manager read lock is held, rather than streamed from a path that can later be replaced" (`debug_server.py:1193-1198`).

The five assets the frontend requests are `/mesh/positions.f32`, `/mesh/cell_ids.u32`, `/mesh/indices.u32`, `/mesh/pos_equirect.f32`, `/mesh/pos_mollweide.f32` (`app.js:363-367`).

---

## Manifest-revision consistency model

The revision token is a hex-joined fingerprint of `manifest.json`'s `(st_dev, st_ino, st_size, st_mtime_ns)`:

```python
# src/magic_geo/debug_server.py:558-567
@staticmethod
def _manifest_fingerprint(stat: os.stat_result) -> CacheFingerprint:
    # Device/inode distinguish atomic replacements even when generated
    # manifests happen to retain the same byte length and timestamp.
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)

def _revision_unlocked(self) -> str | None:
    if self._fingerprint is None:
        return None
    return "-".join(f"{value:x}" for value in self._fingerprint)
```

Device and inode are in the tuple specifically so that an `os.replace`-based swap is detected even when the new manifest has the same size and timestamp as the old one.

`get()` (`debug_server.py:678-721`) re-stats the manifest on **every** access and transparently reopens `_DebugCache` (closing the previous DuckDB connection) whenever the fingerprint changes. If reopening fails it records `_error` and keeps serving the previous handle when one exists, raising `500` only when there was no live cache to fall back on.

`with_cache(action, expected_revision)` (`debug_server.py:723-739`) takes the manager lock, resolves the cache, compares the client's `revision` against the current one, and **fails the read** rather than serving it:

```
409 {"detail": "debug cache revision changed; refresh status and retry"}
```

This is the deliberate design choice the brief calls out: **a stale read fails instead of silently mixing two worlds.** Because the mesh route, the catalog route and every layer request all pass the same expected revision, a publication that lands mid-page-load cannot produce a frame whose geometry comes from one cache and whose values come from another.

The browser side mirrors it (`app.js:1903-1931`):

| Mechanism | Purpose |
|---|---|
| `cacheIdentityFor(status)` = `JSON.stringify([cache_available, cache_dir, cache_revision])` | One string that changes whenever the served world changes |
| `state.cacheEpoch` | Bumped by `resetCacheDerivedState()`/`beginCacheTransition()` to invalidate every in-flight cache-derived request |
| `cacheContextIsCurrent(context)` | Every async continuation re-checks identity, epoch, revision and availability before committing anything |
| `cacheRevisionUrl(url, context)` | Appends `?revision=…` to catalog, manifest, section, family, stage-summary, cell and mesh URLs |
| `layerCacheKey(..., identity)` | The client-side LRU is namespaced by cache identity, so buffers never leak across caches |

`switchWorld()` (`app.js:2094-2122`) deliberately calls `beginCacheTransition(cacheDir)` **after** the server has switched but **before** refreshing status, so old mesh/layer requests cannot commit against the new cache; on failure it restores the displayed selection and force-rebuilds the list.

The revision parameter is optional. Omitting it reads whatever is current — convenient for `curl`, unsafe for a multi-request render.

---

## JSON versus binary layer responses and non-finite handling

Two different, deliberate representations coexist.

| Surface | Media type | Non-finite handling | Source |
|---|---|---|---|
| Any JSON response | `application/json` | `_json_safe()` recursively rewrites every non-finite float to `null` — in dicts, lists and tuples alike | `debug_server.py:66-90` |
| `format=f32` layer | `application/octet-stream` | Little-endian IEEE-754 `float32`, one per cell, in cell-id order; missing/non-finite values are literal `NaN` | `debug_server.py:802-807` |
| `format=arrow` layer | `application/vnd.apache.arrow.stream` | Arrow IPC stream of one table `{cell_id: int32, value: float32}`; `NaN` preserved natively | `debug_server.py:810-827` |

The rationale is written into the code: "Parquet legitimately preserves NaN/Infinity for scientific diagnostics, but Starlette's strict JSON renderer rejects those values. Binary layer responses keep their existing Float32/Arrow semantics; JSON views expose a portable null for each non-finite number" (`debug_server.py:66-73`).

Practical consequences:

- A `null` in `/api/cell/{id}`, `/api/family/...`, `/api/stage-summary/...` or `/api/manifest` may mean either a genuine SQL `NULL` **or** an original NaN/±Inf. The JSON surface cannot distinguish them; the binary surface can.
- The `f32` payload length is exactly `4 × world.cell_count` bytes. Cells with no row in the queried slice are `NaN`, not zero.
- Categorical layers are served as **category indices**, not strings: `float(index)` into the manifest's sorted `categories`, and `-1.0` for a value that is not listed. Clients must map back through `categories` (as `app.js:1792-1794` does for the hover readout).
- The browser converts `NaN` to `MISSING_SENTINEL = 3.0e38` immediately after decoding so GPU drivers handle it uniformly (`app.js:336-338`), and treats `>= 1e37` as missing when reading values back.

`_StrictJSONResponse` is the app's `default_response_class`, so it covers route return values. FastAPI's built-in exception handler emits its own `JSONResponse`; error `detail` payloads in this codebase are strings or `ConfigError.to_dict()` dictionaries and contain no floats.

---

## OpenAPI and Swagger

| Surface | URL | Notes |
|---|---|---|
| Swagger UI | `/api/docs` | Also embedded in the API view's iframe (`index.html:232`) |
| ReDoc | `/api/redoc` | |
| Machine-readable schema | `/api/openapi.json` | |

`GET /api/status` advertises `"api_docs": "/api/docs"` so a client can discover it without hard-coding (`debug_server.py:937`).

Routes are tagged `workbench`, `operations`, `configuration`, `jobs` and `data`, which is how Swagger groups them. Every route above appears there **except** `GET /mesh/{asset_path}` (`include_in_schema=False`) and the static UI mount.

```bash
curl -s http://127.0.0.1:8642/api/openapi.json | jq '.info, (.paths | keys)'
```

---

## Worked examples

### Browser-first workflow, from the shell

```bash
# 1. Start cacheless in a fresh project
magic-geo serve --workspace runs --host 127.0.0.1 --port 8642

# 2. Render and save a config through the API (equivalent to the Config view)
curl -s -X POST http://127.0.0.1:8642/api/config/render \
  -H 'Content-Type: application/json' \
  -d '{"profile":"smoke","overrides":{}}' | jq -r .yaml > /tmp/world.yaml

jq -n --rawfile y /tmp/world.yaml '{yaml: $y, name: "world", force: false}' \
  | curl -s -X POST http://127.0.0.1:8642/api/config/save \
      -H 'Content-Type: application/json' --data-binary @-
# -> {"saved":true,"path":"runs/configs/world.yaml","yaml":"..."}

# 3. Queue a generation that also prepares the browser cache
curl -s -X POST http://127.0.0.1:8642/api/jobs \
  -H 'Content-Type: application/json' \
  -d '{"operation":"generate",
       "arguments":{"config":"runs/configs/world.yaml",
                    "output":"runs/world.json",
                    "open_in_web":true,
                    "debug_output":"runs/debug",
                    "debug_vtu":false}}'
# -> 202 {"id":"<12 hex>","status":"queued", ...}

# 4. Poll it
curl -s http://127.0.0.1:8642/api/jobs/<job_id> | jq '{status, exit_code, cache_dir}'

# 5. Download a declared artifact snapshot (index 0 == the first output field)
curl -sOJ http://127.0.0.1:8642/api/jobs/<job_id>/artifacts/0
```

### Revision-pinned reads

```bash
REV=$(curl -s http://127.0.0.1:8642/api/status | jq -r .cache_revision)

# Catalog and one layer, guaranteed to come from the same cache revision
curl -s "http://127.0.0.1:8642/api/catalog?revision=$REV" | jq '.layers | length'
curl -s "http://127.0.0.1:8642/api/layer/cells%2Felevation_m?format=f32&revision=$REV" \
  -o elevation.f32

# A stage layer at stage 3, as Arrow
curl -s "http://127.0.0.1:8642/api/layer/hydrologic_water_budget_history%2Frunoff_mm_y?stage=3&format=arrow&revision=$REV" \
  -o runoff_stage3.arrow

# A stale token fails loudly rather than mixing worlds
curl -s -o /dev/null -w '%{http_code}\n' \
  "http://127.0.0.1:8642/api/catalog?revision=deadbeef"
# 409
```

### Switching caches

```bash
curl -s http://127.0.0.1:8642/api/worlds | jq -r '.worlds[] | "\(.selected)  \(.cache_dir)  \(.cell_count)"'
curl -s -X POST http://127.0.0.1:8642/api/worlds/select \
  -H 'Content-Type: application/json' \
  -d '{"cache_dir":"runs/earthlike/debug"}' | jq
```

### Cancelling

```bash
curl -s -X POST http://127.0.0.1:8642/api/jobs/<job_id>/cancel | jq '{status, finished_at}'
# "cancelled" if the request landed before the commit boundary;
# the unchanged record if publication/finalization had already begun.
```

---

## Limitations and unresolved claims

- **No security boundary.** There is no login, authorization, per-user isolation or TLS. Every containment control listed above is a containment control, not a tenant boundary (`docs/debugger.md:216-220`). Treat the port as equivalent to a shell on the serving account's project directory.
- **Cancellation is not a rollback.** A cancel accepted after `_publishing`/`_finalizing` began is silently a no-op and the job completes normally (`web_jobs.py:550-553`). This is intentional — the alternative would report `cancelled` for a job that already published a cache — but it means "cancel" is best-effort, not a guarantee.
- **Job records are process-local.** They are in-memory only, evicted oldest-first at 100 records, and lost on restart. Artifact snapshots live under `<workspace>/.magic-geo-web/artifacts/<job_id>/` and are removed with the record. Requested output files persist independently.
- **No progress reporting.** The server exposes no progress field; the UI renders an indeterminate bar for active jobs precisely because a bar pinned at 0% would imply no work had happened (`app.js:2838-2842`).
- **Single worker.** One job at a time. A long `validate` or `calibrate-ensemble` blocks every other operation, including a quick render.
- **JSON `null` is ambiguous.** In JSON responses a `null` may be a SQL `NULL` or an original NaN/±Inf. Only the `f32`/`arrow` layer surfaces preserve the distinction.
- **`complete: false` cells.** `/api/cell/{id}` reports `complete: false` for caches exported before the indexed non-scalar sidecar existed; those cells honestly omit boundary rings, neighbour lists, LOD paths and linked ids rather than pretending to be whole.
- **Categorical layers are capped.** The exporter promotes a column to a categorical layer only when it has at most `_CATEGORY_LIMIT = 64` distinct values (`debug_export.py:34`); above that the column stays in Parquet and is reported under skipped layers. A value outside the recorded category list is served as `-1`.
- **Stage `lithology` codes are not resolved.** The per-stage `lithology` layer is serialized as numeric codes 0–6 and the debug cache contains no authoritative code-to-name table for those stage values; the map/prompt path preserves the numeric scale and repeats the warning rather than borrowing the alphabetical order from the separate final `cells/lithology` layer (`docs/debug_ui_guide.md:326-331`).
- **`mesh_lod` is not consumed by the workbench.** The generation-time cube-quadtree LOD index is exported as ordinary data (scalar `mesh_lod_*` layers, list-valued fields in the cell-details sidecar, and a `mesh_lod` section) but neither `app.js` nor `debug_export.py` references it; the renderer always uploads the full merged mesh. Verified by absence: `grep -rn mesh_lod src/magic_geo/debug_ui/ src/magic_geo/debug_export.py` returns nothing.
- **Map seams are a known geometry diagnostic.** Visible cell-ring seams and antimeridian polygons extending past a 2-D edge are documented diagnostics of the boundary-ring geometry, not missing cache records (`docs/debug_ui_guide.md:378-381`).
- **Export fails closed, by design.** Both the browser and CLI map exports refuse to run when the cache reports `cells_without_ring > 0` or `triangle_count < 1`, because those cells would otherwise render as background holes and the prompt could ask an image model to erase real geography.
- **The workbench does not adjudicate physics.** It is a viewer and a job runner. Layers it lists include authoritative results, non-authoritative shadows, counter-models and pure diagnostics side by side, with no visual distinction beyond whatever `layer_docs.js` prose says. Claims that the repository marks unresolved or false elsewhere in this wiki (subduction polarity, mass provenance, physical time calibration, accelerator parity) remain exactly as unresolved when displayed here; rendering a field on a globe confers no additional confidence. Consult the relevant feature page before treating a layer as physically meaningful.
- **`_jsonl_rows` does not guard JSON decoding.** A malformed line in a family or stage-extras JSONL raises an uncaught `json.JSONDecodeError` inside the request (`debug_server.py:449`), which surfaces as a `500` rather than a typed `4xx`. Reported as observed in source; no explicit handler exists.
- **Unverified here.** The exact contents of `backend_info()`, and the internal behaviour of the CLI subcommands the job manager spawns, are not restated on this page — see [Compute Backends](./09-compute-backends.md) and [CLI Reference](./06-cli-reference.md).

---

## See also

- [CLI Reference](./06-cli-reference.md) — every flag of `serve` and of the commands the job system spawns
- [Debug Exports and Visualization](./16-debug-and-visualization.md) — the debug cache layout, `export-debug`, `export-debug-map` and `export-rerun`
- [Configuration Reference](./05-configuration-reference.md) — the schema behind the Config view
- [Docker Deployment](./19-docker-deployment.md) — `.env`, published ports and the workspace bind mount
- [Architecture](./04-architecture.md) — where the workbench sits relative to the generation pipeline
- [Validation](./12-validation.md) and [Geo Validation Suite](./13-geo-validation-suite.md) — what the validation operations actually check
- [Calibration Against Real-Earth Data](./14-calibration.md) — the calibrate / calibrate-ensemble / derive-targets operations
- [Rendering and Map Output](./17-rendering.md) — the `render` and `render-raster` operations
- [Troubleshooting and FAQ](./22-troubleshooting.md) — cacheless startup, rejected paths, blank layers
- [Quickstart](./03-quickstart.md) — the shortest path to a cache the workbench can open
