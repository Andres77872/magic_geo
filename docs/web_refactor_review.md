# Web/API/configuration deep review and refactor record

Date: 2026-07-11

This review records the repository evidence that drove the workbench refactor,
the implemented contracts, and the limitations that remain. It is intentionally
separate from the physical layer review: the subject here is whether users can
create configuration and use the project feature/API surface from a browser.

## Requirements derived from the request

1. `serve -d ...` must not be required.
2. Omitting `-d` must be useful even before a cache exists, not merely produce a
   later missing-manifest error.
3. Every existing cache read API/data class must have a browser view.
4. CLI/Python generation features must be usable from the web rather than the
   CLI remaining the only orchestration interface.
5. YAML creation must be schema-driven, validated, reusable from CLI/Python/web,
   and documented in detail.
6. Installed-package behavior, path safety, tests, and honest completeness
   metadata are part of the result.

## Pre-refactor evidence

### Required cache argument

`serve(debug_dir: Path)` had no default, so Typer displayed `[required]` and
rejected no-argument invocation before application code ran. `create_app` then
eagerly read `manifest.json`/`sections.json`; making only the option nullable
would not have enabled first-run YAML creation.

The existing CLI pipeline already implied a conventional default:

```text
generate default:     runs/world.json
export-debug default: <world parent>/debug
therefore:             runs/debug
```

That derivation describes CLI `export-debug` when `--output` is omitted. The
browser now has a separate workspace-rooted contract described below.

### Dormant read APIs

The old server exposed seven cache JSON surfaces plus mesh assets. Frontend
fetches used only manifest, layer, cell, plate boundaries, and mesh. These had no
browser consumer:

- `/api/stage-summary/{history}`;
- `/api/family/{name}`;
- `/api/section/{name}`;
- Arrow layer format.

A measured 128-cell full-world export contained 191 top-level keys, 437 visual
layers, 106 record families, 64 dictionary sections, and four scalars. The map
could reach the layers and scalar cell projection but none of the 106 family
tables or 64 model/graph/summary sections.

### Incomplete generic records

Sixty measured families used JSONL plus a scalar Parquet sidecar. The old family
route always chose Parquet when a sidecar existed, making nested `cell_ids`,
resource/route/settlement links, and provenance inaccessible even to direct API
clients.

The old cell route called itself “full” but the exporter dropped non-scalar
boundary rings, neighbor/edge arrays, LOD paths, and linked record IDs. Ragged
monthly arrays could raise `IndexError` during export.

### CLI-only features

The old debugger document explicitly said the CLI was the only generation
interface. Browser parity was absent for config creation, backend diagnostics,
full/geo-only generation, three validation modes, calibration/ensemble/target
derivation, SVG/raster rendering, debug/VTU export, Rerun export, jobs, logs,
cancellation, artifacts, and cache selection.

### Configuration drift and weak helper surface

There were three implicit “defaults”:

- `WorldConfig()` used plate-motion scale `2.0` and precipitation scale `1.0`;
- packaged `seed_config.yaml` used `4.0` and `1.0`;
- `configs/earthlike_seed.yaml` used `4.0` and `0.8`.

`init-config` copied the packaged file and defaulted to a checked-in path that
already existed in a source checkout. There were no profiles, YAML dump,
override, schema, or atomic generic-write helpers. `yaml.safe_load` silently
accepted duplicate keys. Pydantic JSON Schema had constraints but zero field or
section descriptions, so it could not honestly drive a documented form.

Malformed YAML was not normalized into the friendly generation error path.

### Packaging and safety

`pyproject.toml` included only the seed and native library as package data; a
built wheel could omit the entire UI/vendor tree. Cache confinement used string
prefixes, which do not distinguish `/cache` from `/cache-secret`; nested JSONL
did not use the same path check. Manifest field names were interpolated into SQL
without identifier escaping, and unknown `format=` values silently became f32.

There were no focused server/exporter/browser/serve/config-CLI tests.

## Implemented design

### Cache-optional server

`serve` now accepts `Path | None`; `-d` is an optional explicit selector.
Without it, `<workspace>/debug` is auto-selected when present (`runs/debug` in
the default workspace). Without any cache, the FastAPI app and static workbench
still start, with Config/Operations/API usable.

A reloadable cache manager fingerprints `manifest.json`, discovers workspace
caches, supports selection, closes DuckDB connections, and can select a cache
created by a successful background generation.

The operation catalog rebases conventional `runs/...` output defaults beneath
the configured workspace. Thus both automatic cache preparation and the
browser `export-debug` form default to `<workspace>/debug`; this intentionally
differs from the CLI's `<world parent>/debug` default.

### Complete data browser

The Data tab covers every manifest class:

- top-level scalars;
- skipped outputs and reasons;
- complete layer and cell-schema catalogs;
- all stage summaries plus retained non-scalar/mixed stage extras;
- all families with full/scalar mode and pagination;
- all dictionary sections.

Nested family mode defaults to JSONL; scalar mode explicitly chooses the
sidecar. Cell export writes an indexed JSONL sidecar for every non-scalar field,
and `/api/cell` merges it with the Parquet scalar record. Old caches advertise
`complete: false`. Ragged monthly arrays remain inspectable rather than
crashing/partially flattening.

### Typed operations and jobs

`web_jobs.py` defines a fixed typed catalog for 11 executable workflows; config,
backend, map-reference export, and serve are four direct equivalents. The
coverage set exactly matches all 15 CLI commands.

The browser renders forms from that catalog. The job manager:

- normalizes booleans/numbers/enums/repeated paths;
- rejects unknown operations/arguments;
- confines inputs to the project and outputs to the workspace;
- invokes `python -m magic_geo` with an argument vector, never a shell;
- serializes heavy jobs through one worker;
- captures bounded combined logs, timestamps, status, exit code, and artifacts;
- cancels queued work without spawning and terminates running subprocesses
  (their process groups on POSIX), with a five-second kill escalation;
- waits for active cancellation/worker cleanup during server shutdown;
- snapshots new/changed successful file artifacts for immutable per-job
  downloads, plus new/changed reports written before a policy failure in the
  four reporting operations;
- stages cache-directory exports outside the destination and publishes them only
  on success;
- optionally chains `export-debug` after generation and selects its published
  cache.

The snapshot rule is intentionally tied to the run: overwriting or removing the
requested output later cannot change an earlier download, and an unchanged
pre-existing file is not attributed to a failed run. Cancelled partial files are
not snapshotted; complete primary Generate outputs are captured before optional
cache preparation, so they remain available if that later step fails or is
cancelled. Job records/snapshot links remain process-local. Cache staging
likewise means a failed or cancelled export is discarded while an existing
selected cache remains intact. Cancellation and commit are serialized: after
publication/final snapshotting begins, a late cancel is ignored and the job
finishes normally. The rollback-safe two-rename publication pauses cache reads
for the swap, so a request cannot mix old and new revisions.

This preserves the existing command implementations—including the large full
validator—while giving the browser actual parity. A future service extraction
could let CLI/HTTP call smaller typed business functions directly; current
process isolation is useful for cancellation and native-state isolation.

### Schema-driven configuration

The config model now has descriptions on every section/field and explicit
profiles:

- `default` = `WorldConfig()`;
- `earthlike` = calibrated checked-in reference profile;
- `smoke` = 128-cell deterministic CPU run.

Core helpers cover parse/load, stable dump, profile creation, non-mutating
dotted overrides, CLI assignment parsing, JSON Schema, and atomic write.
`ConfigError` carries source, line/column, and JSON-compatible per-field issues.
The YAML loader rejects duplicate keys.

CLI `init-config` uses the same helpers, writes the safe local target
`magic-geo.yaml`, supports profile/typed repeatable `--set`, and refuses
overwrite without `--force`.

The browser exposes schema/profile/template/render/validate/save APIs. Saves are
confined to `<workspace>/configs`, and raw download remains client-only.

### Workbench UI

The former single debugger screen now has semantic Map/Data/Config/Operations/API
tabs, URL hashes, keyboard tab navigation, cacheless empty state, responsive
layouts, job polling/logs/artifacts/cancel, backend telemetry, and embedded/open
Swagger. The existing GPU map, projections, overlays, stage controls, layer docs,
and cell inspector remain available.

### Hardening and install behavior

- component-aware cache confinement;
- one confined path function for Parquet, JSONL, detail indexes, and mesh;
- quoted DuckDB identifiers;
- explicit `f32 | arrow` format enum and query bounds;
- restricted config names, explicit overwrite, symlink-safe confinement, and a
  1,000,000-byte/complexity-bounded YAML request;
- project/workspace job path policy;
- transitive calibration/geo-suite manifest confinement and input/output
  collision rejection;
- background commands without a shell;
- supported debug manifest identity fixed to `magic-geo-debug-cache` version
  `1`, with other/missing identities rejected;
- success-only staged publication for web cache exports;
- immutable, job-owned download snapshots, including produced policy-failure
  reports;
- cancellation and waited job/DuckDB cleanup through FastAPI lifespan;
- cache metadata symlink rejection, revision-pinned reads, strict non-finite
  JSON normalization, routable slash-containing logical names, and numeric-only
  XML-escaped VTU stage arrays;
- HTML/CSS/JS/vendor patterns declared as package data;
- wheel builds require the CMake-staged native core and are tagged for their
  OS/architecture while remaining independent of the CPython ABI.

A no-build-isolation wheel was built and inspected; it was tagged
`py3-none-linux_x86_64`, declared `Root-Is-Purelib: false`, and contained the
native library, `index.html`, `style.css`, `app.js`, `layer_docs.js`, and all
three vendored Three modules.

The source archive was also inspected: it contains `CMakeLists.txt`, all C++
sources, Python/UI sources, tests/docs/config examples, and no staged
ELF/DLL/dylib. The wheel gate loads the current-platform library and checks
required ABI symbols; package data and the runtime loader exclude/ignore
other-platform native filenames.

## Verification evidence

Focused unit coverage now proves:

- serve help has no required `-d`;
- omitted cache path selects `runs/debug` when present;
- no-cache invocation starts the workbench;
- explicit cache/host/port behavior;
- profile/template parity and YAML round trips;
- described schema coverage for all fields;
- duplicate/malformed/root/Pydantic error normalization;
- non-mutating validated overrides;
- CLI profile/typed override/overwrite behavior;
- cacheless config/operation/status endpoints;
- every manifest class through synthetic cache endpoints;
- full nested versus scalar family reads;
- indexed full-cell merge and ragged-monthly retention;
- path-prefix escape rejection;
- arbitrary world-key filename confinement;
- fixed 15-command parity, direct/transitive job input confinement, and
  input/output collision rejection;
- non-default-workspace rebasing for browser output defaults;
- strict debug format/version rejection;
- metadata-symlink rejection, same-size/time replacement revision detection,
  revision-pinned cache reads, slash-name ASGI routing, and non-finite JSON;
- categorical VTU filtering/XML escaping and retained stage extras through
  exporter, API, and UI;
- staged cache success/failure publication and an atomic cancellation/commit
  boundary;
- immutable downloads and failed-policy report capture;
- terminal job visibility only after artifact finalization;
- queued/running cancellation and waited shutdown.

JavaScript syntax checks pass for the workbench and layer-doc modules. The
wheel build and asset listing pass. The broader project test/build gates remain
the final authority for native/model changes outside this refactor.

A follow-up UX review (2026-07-22) fixed 18 verified findings without changing
the contracts above: the map empty state restores its default copy after an
initialization error, catalog load failures surface in the Data view, hover
readouts no longer stream through the `aria-live` status region, help remains
reachable without a cache, job cancellation and profile-template reset ask for
confirmation, layer loads show a transient loading message and durable failure
notices, map shortcuts ignore form fields, job polling no longer rebuilds
unchanged rows, template/inspector/operation errors render as styled notices,
terminology and help-button labels were unified on “workbench” (including the
exported GPT-image prompt, kept identical to the CLI), glyph buttons carry
accessible names, dim text meets WCAG AA contrast, saving/validation disable
their buttons in flight, invalid operation JSON names its field, empty layer
filters show a placeholder, active jobs render an indeterminate progress bar,
and view switches push history entries so Back/Forward navigates views. The
focused UI/server/jobs/documentation/map-export test modules and a JavaScript
syntax check pass after the change.

## Remaining limitations (explicit, not hidden)

1. **Generic access is not bespoke geometry.** Every family is usable in Data,
   but only per-cell layers and plate segments have map renderers. Routes,
   rivers, settlements, borders, currents, faults, and corridors can receive
   custom overlays later without blocking data access now.
2. **Jobs are process-local and single-worker.** Status disappears on server
   restart, there is no persistent queue, resume, multi-user scheduling, SSE,
   or distributed execution. Requested output files persist, but job-owned
   snapshot links last only as long as their bounded in-memory job records.
3. **No authentication or tenant boundary.** The path and command controls do
   not add login, authorization, per-user isolation, or TLS. Anyone who can
   reach the service can inspect workspace data and submit/cancel jobs. Loopback
   is the default boundary; remote binding requires a trusted network and
   authenticating proxy.
4. **Progress is log/status polling.** The CLI does not publish a universal
   structured progress protocol; suites print member progress, while generation
   can remain at “running” until completion. The workbench therefore renders an
   indeterminate progress indicator for active jobs rather than a percentage
   that would sit pinned at 0%.
5. **Cancellation is process termination.** Web cache exports are staged and
   downloadable links are immutable snapshots, but non-cache commands still
   control their requested output paths and may leave partial files when
   terminated. Those partial files are not offered as downloads; already
   completed primary Generate snapshots are the exception. The job manager does
   not provide transactional publication for every CLI workflow.
6. **Config scalar coercion remains backward compatible.** Duplicate keys and
   invalid ranges are strict, but Pydantic still accepts some convertible scalar
   strings/numbers. Templates always emit canonical types.
7. **Layer identifier coloring remains generic.** Numeric `*_id` fields use the
   continuous shader ramp; documentation warns that colors are labels.
8. **Stage prefetch is not abortable.** Request sequencing prevents stale
   display, but rapid scrubbing can still create avoidable cache queries.
9. **Thread-count determinism remains a generator issue.** Configuration and
   output provenance should retain compute settings until that is resolved.
10. **CMake remains an explicit wheel prerequisite.** Setuptools refuses a
    missing/incompatible native core and emits non-universal platform tags, but
    it does not invoke CMake itself. Build/stage the Release library before
    requesting a wheel, including after extracting the binary-free source
    archive. A local `linux_x86_64` wheel is not audited as manylinux; its glibc,
    libstdc++, and OpenMP runtime baseline follows the build host.
11. **Large mesh responses are materialized for revision safety.** This avoids
    serving a path removed during cache publication, but parallel first-load
    assets can consume substantial server memory. A future ref-counted snapshot
    or streaming read lease can reduce that footprint without reopening the
    revision race.

These items do not restore the former CLI-only/cache-required gap; they define
the next hardening/performance/visualization increments.
