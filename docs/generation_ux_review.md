# Generation workbench UX review

Review date: 2026-09-12. Scope: configuration handoff, operation launch, queue,
generation, browser-cache preparation, completion, errors, cancellation, and
navigation between the Map, Data, Config, Operations and API views.

## Evidence and verification status

This review was made directly against the workbench controllers, HTML, CSS, job
API implementation and existing UI regression tests. The findings below describe
the implementation at the start of this change, before the generation UX work.
Function names are included because line numbers move during the fixes.

The original UI exposed process status, timestamps, an indeterminate progress
bar and a log. It did not explain which part of generation was active, what that
part accomplished, or whether the world was already saved while browser data
was still being prepared. The complaint that generation did not communicate
what it was doing is supported by the implementation.

The final verification record below distinguishes real-browser observations
from automated checks and scenarios that were not exercised in the browser.
P1 means a direct progress, recovery or
interaction failure; P2 means a substantial navigation or clarity problem; P3
means a secondary clarity improvement. These are product-review priorities.

## Findings and required outcomes

| ID | Priority | Confirmed implementation and impact | Required outcome | Implemented resolution and evidence |
| --- | --- | --- | --- | --- |
| G01 | P1 | `renderJobDetail` shows a status, generic progress bar, raw timestamps and logs. It provides no current phase, explanation, elapsed duration or observed work count. Long work appears motionless or opaque. | Show the current activity and its purpose, measured elapsed time, observed counters where available, and the last engine event. Keep unknown completion indeterminate. | Implemented: structured engine phases, explanations, measured durations and current-stage counters. Live browser evidence below. |
| G02 | P1 | `JobManager._run` performs generation followed by optional browser export under the same running status. The user cannot distinguish simulation from saving, browser export, validation or publication. | Expose actual lifecycle phases, including world writing, browser preparation and publication. Do not call a map ready until its cache is usable. | Implemented: generation, world writing, cache export and publication phases. World/cache success observed live; individual brief export phases covered by targeted regressions. |
| G03 | P1 | The baseline UI reads `job.error`, but `WebJob.public` exposes `exit_code` and `log`. Failures generally appear as a failed badge and an empty/zero progress bar with the cause buried in logs. | Show an error summary, failure phase and relevant recovery action, with technical output available separately. | Implemented: API error summary plus contextual failure heading, explanation and retry guidance. Automated coverage; failure not injected live. |
| G04 | P1 | Generation captures primary world artifacts before optional export. Export can then fail. `renderJobActions` offers reuse/validate/render but no direct retry of browser export from the saved world. | Clearly distinguish saved-world success from browser preparation failure; retain world downloads and prepare the map from the existing world. | Implemented: saved-world availability and Prepare browser map recovery using a preserved world snapshot. Automated coverage; export failure not injected live. |
| G05 | P1 | The fixed 2.5-second interval starts requests without waiting for earlier ones. `refreshJobs` and `selectJob` invalidate older requests by sequence number. With sustained latency longer than the interval, earlier responses can all become obsolete. | Ensure automatic polling does not overlap itself or starve progress. Preserve explicit user selection ordering. | Implemented: concurrent automatic refreshes share the outstanding poll. Controlled slow-response regression reported passing. |
| G06 | P1 | `renderJobDetail` replaces its complete subtree on active polling. Expanded submitted settings are recreated closed; focused descendants and text selection can be lost. Only log scroll is carried forward. | Preserve user-opened disclosures, focused controls and manual log position through updates. | Implemented: update status and output sections without replacing settings/log disclosures. Expanded state and focused log disclosure observed across completion. |
| G07 | P1 | A detail GET error replaces the previous useful detail, while the list can still say Live. A failed refresh of an already completed task is not retried when its status remains unchanged. | Keep the last useful task snapshot with a visible stale marker, distinguish list/detail connectivity, and make manual refresh recover completed details. | Implemented: preserve last details, show disconnection and retry even completed tasks after a failed detail read. Automated coverage; offline notice observed live. |
| G08 | P2 | Active jobs are polled but nothing displays their status outside Operations. The Map can show a prior cache as ready or a generic empty state while a different world is generating. | Provide persistent activity and a route back to its detail; separately identify the currently displayed map. | Implemented: persistent task activity and link outside Operations, alongside selected-cache identity. Running activity observed on Map. |
| G09 | P2 | Initial `selectedJobId` is null and job refresh does not select existing active work. Reloading loses the progress context and leaves the user to search job history. | Make ongoing work discoverable immediately after reload without overriding a user's deliberate selection. | Implemented: initial refresh selects existing active work while preserving explicit selection. Covered by controller behavior; active-job reload not separately exercised live. |
| G10 | P2 | The mobile layout follows launcher, history, selected detail. The active result can be below a long form and the job list. Detail and logs create nested scrolling. | Put selected progress ahead of history, reveal submitted work, and keep the layout readable without horizontal overflow on small screens. | Implemented: selected detail precedes launcher/history in DOM and mobile display; submission reveals its heading. Desktop and 390-CSS-pixel mobile checks passed. |
| G11 | P2 | Queue feedback says only that the worker is unavailable. It provides neither queue position nor waiting duration. | Show actual queue position and elapsed waiting; identify other active work where the API can support it. | Implemented: actual queue position and measured waiting duration. Queue presentation regression reported passing; multi-job queue not exercised live. |
| G12 | P2 | `generateFromSavedConfig` changes the launcher guidance but retains the previous submission's `operation-result.dataset.jobId`. `refreshJobs` then overwrites the new-config guidance with the old job's status. | Clear the previous submission association before entering Operations with a new saved configuration. | Implemented: clear previous submission association before Config-to-Operations navigation. Controller regression included in UI verification. |
| G13 | P2 | The log is an always-visible unstructured block. It lacks a clear latest event, technical-details disclosure, download/follow controls and truncation explanation. Empty output reads only No log output. | Explain current work without requiring log parsing; keep logs accessible for diagnosis and manual reading. Report clipping if the server retains only a tail. | Implemented: separate readable stage information and collapsible technical log, keyboard-focusable output, scroll-to-pause behavior and retention explanation. Disclosure observed live. |
| G14 | P2 | Cancellation has generic confirmation and a status pill. Cancelling still counts as active, so the cancel control can be offered again. The result does not explain completed outputs or recovery. | Clearly communicate cancellation requested/stopping/cancelled, disable duplicate requests while stopping, and describe usable completed results. | Implemented: requesting-stop/stopping/cancelled states, duplicate-stop prevention, publication restrictions and saved-world outcome. Keyboard cancellation observed live. |
| G15 | P2 | Job detail has no dedicated live phase/status announcement. The main live message concerns only the last submission. Job-row accessible names omit identity, so same-operation/same-status jobs sound identical. | Give task rows distinguishable names and announce meaningful phase or terminal changes without re-announcing every timer tick or entire log. | Implemented: unique task-row accessible names, concise status announcements and aligned DOM/visual reading order. AX structure and keyboard cancellation checked; full screen-reader audit not performed. |
| G16 | P3 | The generic generation form does not summarize output implications. Browser preparation and geography-only choices need translation by the user, and old per-operation drafts can retain overrides when a new YAML file is chosen. | Explain what will be produced and where, identify optional browser preparation and retained overrides, and make the primary action specific to generation. | Implemented: generation-specific action and lifecycle description, explicit output paths and browser/geography choices retained in the form. Reviewed in the live launcher. |
| G17 | P1 | Reusing a browser-cache destination for a new task could leave an older job offering Open map for a cache now belonging to the newer world. Reusing a mutable world output path also risks regenerating that map from the wrong world. | Pin recovery to the job's preserved world, invalidate outdated map availability, and explain when a newer job replaced the cache. | Implemented: preserved `world_path`, `map_superseded`, removal of the outdated Open map action, explanatory result text and Prepare browser map recovery. Targeted backend/UI regressions; final backend behavior not rechecked in the browser. |
| G18 | P2 | The live cancellation result listed output/cache destinations under Artifacts without saying that no output was available. A path alone could be mistaken for a saved result. | Label pending destinations, unavailable downloads and browser-map availability explicitly. | Implemented after browser finding: Destination · pending, No download produced by this job, No browser map for this job, and Available via Open map. Covered by the added UI regression; not reloaded in the browser after this final label-only change. |

## Source map

- `src/magic_geo/debug_ui/operations-workbench.js`: `renderJobActions`,
  `submitOperation`, `renderJobs`, `renderJobDetail`, `selectJob`, `refreshJobs`,
  `cancelSelectedJob`, `artifactMarkup`. These establish G01, G03–G07, G09,
  G11, G13–G15, G17 and G18.
- `src/magic_geo/debug_ui/app.js`: initial state, `setView`,
  `applyServerStatus`, and `main` polling establish G05, G08 and G09.
- `src/magic_geo/debug_ui/config-workbench.js`:
  `generateFromSavedConfig` establishes G12 and the retained-draft aspect of G16.
- `src/magic_geo/debug_ui/index.html`: Operations panel order, status regions,
  and generic empty states support G08, G10 and G15.
- `src/magic_geo/debug_ui/style.css`: `.operations-grid`, `.job-detail`,
  `.job-log`, and the 760px media query establish G10.
- `src/magic_geo/web_jobs.py`: `WebJob.public`, `WebJob.summary`,
  `JobManager._run`, and the generation operation catalog establish the API/UI
  mismatch, optional export lifecycle, available artifact recovery and field
  descriptions in G02–G04, G11 and G16. `_run_debug_export` and preserved
  artifact paths establish the ownership fix in G17.

## Information hierarchy

1. **Persistent activity:** world/config identity, running/queued/final state,
   current activity and a direct link to the task. The selected map identity is
   separate from the world being generated.
2. **Selected task:** a plain-language activity heading and purpose; elapsed
   total and phase duration; actual work count when supplied; time since the
   last engine event. Server polling freshness is a separate fact from engine
   progress. A responsive HTTP endpoint does not prove simulation advancement.
3. **Lifecycle:** queued, preparing inputs, generating requested systems,
   writing world, preparing browser data, publishing and ready. Show completed
   and current phases based on actual events. Do not turn phase count into an
   estimated percentage of runtime.
4. **Outcome and next action:** world/map availability, downloads and a
   recovery action that uses existing completed output when possible. Failure
   location and cancellation outcomes remain visible after the task ends.
5. **Secondary details:** phase history and durations, submitted settings,
   technical logs and storage paths. Polling must respect the reader's open
   disclosures and scroll position.

Generation is a potentially long computation, so an unsupported ETA or an
animated bar that looks determinate would create a new trust problem. Accurate
activity, duration, work counts and clearly unknown remaining time are enough
to make the task understandable without fabricating speed or completion.

## Acceptance checks

The following are required evidence targets, not a record of checks already run.

| Scenario | Observable acceptance condition |
| --- | --- |
| Submit and queue | The accepted task is revealed with its identity, actual queue position and waiting duration. Repeated clicks do not create unintended duplicate submissions. |
| Slow engine phase | Current work and purpose remain visible. Elapsed time advances. No fresh engine event is reported honestly without claiming that the whole service is offline. |
| Phase update | A phase change updates detail and history while the API status remains running. No invented percentage or ETA appears. |
| Browser export | A saved world is distinguished from browser data still being prepared; a map-ready action appears only after usable publication. |
| Browser preparation disabled | World completion and downloads remain clear, with an explicit action to prepare browser data if desired. |
| Export failure | The world artifact survives; the failure identifies browser preparation; recovery reuses the existing world. |
| Generation failure | The failed phase and concise error are visible without scanning the full log. Technical detail remains accessible. |
| Cancellation | Queue cancellation, active-process stopping and final cancellation are distinguishable. Duplicate stop requests are disabled, and completed results are accurately identified. |
| Slow HTTP | Controlled responses longer than the poll interval eventually render. Requests do not continuously invalidate all prior responses. |
| Detail outage | Last useful detail remains visible as stale. A later successful refresh recovers it, including for a completed task with unchanged status. |
| Reading while polling | Expanded settings/history/log panels, focused controls and manual log position survive background updates. |
| Selection race | Selecting another job while a submission or detail request is outstanding preserves the latest explicit selection. |
| Reload and navigation | Active work is discoverable after reload and from other views. The app does not steal navigation to announce updates. |
| New configuration handoff | Previous submission feedback cannot overwrite the selected configuration's guidance. Retained generation overrides are visible and understandable. |
| Desktop/mobile | Selected progress is easy to reach, before history; controls and long paths fit narrow screens; scrolling remains usable. |
| Accessibility | Keyboard actions remain operable during polling; repeated jobs have distinct accessible names; significant phase and outcome changes are announced without timer/log spam. |

`tests/test_debug_ui.mjs` already exercises useful async request ordering, config
preservation, job selection and cancellation races. Its small DOM stand-in does
not establish CSS layout, actual focus/disclosure preservation or assistive
announcement behavior. Those need targeted real-browser checks in addition to
the controller and backend regression tests.

## Final verification record

### Real-browser check, 2026-09-12 local / 2026-09-13 UTC

The workbench was exercised through the supported browser UI tools in Brave at
`http://127.0.0.1:8648`, with an isolated output workspace at
`/tmp/magic-geo-generation-ux`. This was actual native generation with
`configs/seasonal_smoke.yaml`, 128 cells, zero erosion iterations, full world
scope, and browser-cache preparation enabled. No production-sized world was
generated for this check.

| Observation | Evidence and outcome |
| --- | --- |
| Real generation and cache completion | Job `e96c94e93989` completed with exit code 0. The UI displayed 15 seconds elapsed. The generated cache contained 494 layers, 115 record families and one stage history. The world and cache destinations were `/tmp/magic-geo-generation-ux/world.json` and `/tmp/magic-geo-generation-ux/debug`. |
| Meaningful live progress | While the job was running, the selected heading and header activity both read “Checking seasonal climate accuracy”. The explanation identified month 1 of 12 and the possibility of further refinement. The detail showed `1 / 12 · current stage`, 3 seconds elapsed, phase duration, and last worker output 0 seconds ago. It did not claim that one twelfth of the total runtime was complete. |
| Settings and log during completion | Both “Submitted settings & timestamps” and “Technical log” were opened as generation progressed. At completion both were still expanded, and browser focus remained on the Technical log disclosure. The log contained actual mesh, climate, water, geography, population, serialization and export activity. |
| Successful result | “Browser map ready”, completed generation/cache workflow items, a downloadable world, and Open map / Validate world / Render map / Reuse settings actions were visible. |
| Open map | The Open map action navigated to Map and rendered the actual colored 128-cell globe with the expected world identity and 494-layer catalog. The browser error-log check returned no error entries at that point. |
| Activity outside Operations | During job `c4686eaf5365`, the Map tab retained the generated globe and cache identity while the header displayed the second task's “Checking seasonal climate accuracy” activity. This distinguished visible map content from ongoing generation. |
| Browser-action limitation | An attempted activity-button click during the second job hit a 3-second browser-control timeout. That job finished before cancellation was delivered, displaying 16 seconds elapsed. It is a second successful smoke generation, **not** evidence of successful cancellation. |
| Keyboard cancellation | Job `3f203a3a42c8` used `/tmp/magic-geo-generation-ux/cancel-immediate.json`. The Cancel job button was activated with Enter immediately after submission. The browser returned a terminal cancelled state in the same 1.94-second tool invocation, showing 0 seconds elapsed, “The worker has stopped. You can reuse the submitted settings”, a Reuse settings action and no Cancel button. The existing browser cache remained ready. |
| Offline display | A controlled server restart before submission produced the visible connection-loss notice, preserved last-state explanation and Offline badge. Reloading after the server restarted restored the live workbench. |
| Mobile layout | At 390 CSS pixels wide, the document width and scroll width were both 390: no horizontal page overflow was observed. The selected task appeared above the launcher and history. Its phase/result, actions, elapsed time, output and disclosures were readable in the mobile screenshot. The browser's existing zoom required a 585-pixel viewport override to obtain 390 CSS pixels; the override was reset afterwards. A narrower 260-CSS-pixel snapshot also kept the selected task first. |
| Reading order fix | The first browser check found that CSS reordered the selected detail visually while DOM/AX order remained launcher → history → detail. After the coordinating task moved the section, a fresh page load confirmed DOM/AX order as selected detail → launcher → history. |

The successful smoke run validates this UX path and small configuration; it
does not establish production runtime, a fix for Solstice ocean closure, or
scientific correctness of every generated field.

### Automated verification

Final integration checks run by the coordinating task:

- `node tests/test_debug_ui.mjs`: **102 passed**, exit 0.
- `.venv/bin/python -m pytest tests/test_web_jobs.py tests/test_debug_server.py tests/test_generation_progress.py -q -o faulthandler_timeout=20`: **130 passed, 199 subtests passed**, exit 0 in **15.22 seconds**, outside the restricted sandbox using the approved pytest command.
- Incremental native build passed. Six opt-in telemetry tests passed; a native probe preserved exact seasonal temperatures, fluxes, residuals and work counts with logging enabled/disabled.
- One complete CLI generation with **128 cells and one erosion iteration** finished in **20.753 seconds**, exit 0, emitting **71 genuine stage events**. The browser tests above separately used zero erosion iterations.
- `git diff --check`: passed.

Two earlier restricted-environment repeats stalled at the ASGI file-download test and were stopped/timed out; they are not counted as passing. The isolated test passed, and the complete approved run outside that environment passed without test or application changes to accommodate the stall.

Machine-readable results, source hashes and evidence paths are in
`runs/ui-generation-progress/integration-verification.json` and
`runs/ui-generation-progress/validation.json`. Detailed UI output is in
`runs/ui-generation-progress/ui-tests.txt`.

### Remaining browser coverage and follow-up

- The short smoke run did not permit a prolonged manual-log reading test or
  every intermediate export/publication phase to be observed separately. The
  expanded-disclosure outcome was observed across the completion transition.
- Export failure, immutable-world recovery, older-cache supersession,
  deliberately slow HTTP, completed-detail recovery and queue position depend
  on the targeted automated regressions; they were not injected in this live
  browser session.
- The cancellation view initially listed unavailable output destinations under
  “Artifacts” without marking them as unavailable. G18 records the implemented
  pending/not-produced labels and added controller regression. This final
  wording change was not reloaded in the browser.
- Dedicated screen-reader software was not used. Browser AX snapshots and
  keyboard activation establish accessible structure and operability for the
  checked controls, not a complete assistive-technology audit.
