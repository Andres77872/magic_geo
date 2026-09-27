# Workbench UX and storage refactor — September 12, 2026

## Findings and implemented behavior

| Finding | Change |
| --- | --- |
| CLI, cache manager and job worker independently assumed source-local `runs` paths; external workspaces were rejected. | `RuntimePaths` now owns defaults, environment overrides, display paths and allowed storage roots. CLI/API/jobs share it; output snapshots and staged cache publication work across external roots. |
| Config always opened a profile; users had to type file paths into operations. | `ConfigStore` discovers real world configurations, excludes scenario matrices, reports explicit-default failures and supplies both the editor picker and generation defaults. |
| Loading/saving did not form a continuous workflow. | Show the opened file and save destination. Save under the same name edits the source; rename creates a copy. Save & continue prepares generation. Existing valid files can be used directly. |
| Saving normalized YAML discarded comments. Competing file edits had no revision check. | Shared atomic text writer validates exact YAML before publication. Opened files carry a content revision; a stale save requires reload or a new copy. |
| Config and operations were embedded in a large rendering module. | Separate controllers own config and operation workflows. App services are injected, and controller tests use separate module scopes to catch missing dependencies. |
| Switching operations discarded form edits; irrelevant cache options stayed visible. | Retain a draft per operation, use catalog-driven essential/advanced groups, and disable dependent cache fields when cache preparation is off. |
| Completed jobs did not provide a natural next step. | Reuse settings, open the produced map, or prepare validation/rendering for the generated world. Submission status follows the actual job state. |
| Data overview was passive, with long unfiltered resource lists. | Overview counts and family entries navigate directly. Resource filters work across families, sections and histories and retain a way to clear an empty result. |
| Small layouts and keyboard navigation obscured the next action. | Restructure editor/job layouts, show the primary save/continue action in the heading, retain Tab navigation, add save/validate shortcuts, and load API documentation only when requested. |

## Verification

- Browser workflow used `configs/seasonal_smoke.yaml`, saved an exact YAML copy to
  `/tmp/magic-geo-ux-review/configs/ux-review.yaml`, and completed generation plus
  cache publication outside the repository. The result exposed 444 map layers,
  68 families and 46 sections. Job `a89132653649` completed successfully in the
  preview session; job records remain process-local.
- Browser checks covered the loaded default, saving a copy, generation, map
  rendering at mobile width, Data overview navigation, filtered/paginated family
  records, retained operation drafts, disabled dependent cache options and an
  empty browser error log. Temporary viewport overrides were reset.
- 89 JavaScript handler tests passed, including request ordering, exact YAML,
  competing file opens, stale-save handling, numeric inputs and resource search.
- 58 storage/configuration/static-asset/deployment checks passed. A separate
  13-test run passed storage/publication and process-group cleanup checks.
- The larger regression run recorded 182 passes and 289 passing subtests before
  interruption during the unrelated all-seed native simulation sweep. Its one
  failure was the existing 60-second generation deadline with the six-step
  Earthlike configuration. The cache integration test now uses the repository's
  dedicated seasonal smoke fixture, covering the same cache contract exercised
  successfully in the browser. The final combined rerun was declined, so this
  record does not claim that the entire test suite passed.

## Preserved limits

Jobs and logs are process-local and run through a single worker. The workbench
has no authentication or multi-user isolation. Revision checks detect changes
before saving; they are not a distributed filesystem transaction. Native
simulation behavior and scientific validators were not changed.

See [runtime storage](runtime_storage.md) for environment settings, defaults,
discovery precedence and a relocation example.
