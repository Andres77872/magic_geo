# Python enrichment dependency audit

Audit date: 2026-09-09. Scope: the two public generation entrypoints and Python
enrichers. This review traces current producer/consumer reads and verifies
generated values; it does not establish physical calibration of the models.

## Corrected defects

The geo-only path previously built permafrost regions before biome diagnostics.
Its permafrost cell calculation could derive freezing months from monthly
temperature, but its region aggregation read the not-yet-created `frost_months`
field with a zero default. The resulting regions reported zero freezing months
even when their cells experienced freezing weather. Both entrypoints now use
the same physical enrichment sequence, publishing soil and seasonal biome
diagnostics before permafrost and glacial records. Permafrost also derives its
freezing-month count directly from monthly temperature, so standalone calls
remain consistent when a biome cache is absent or stale.

The full-world path previously forwarded `output.include_cells: false` to the
native serializer before enrichment. This removed the prerequisite cell data
while allowing dependent models to run; many silently produced empty or absent
records and incorrect summary counts. The full API now requests cell data
internally, completes enrichment, and returns `cells: []` only at the output
boundary. Every other field matches a run with cells included. Geo-only
generation retains its explicit requirement for cells because that product
supports complete natural-system validation.

## Execution boundaries and dependency evidence

`api._enrich_physical_foundation` is shared by both entrypoints. Its order
preserves geometry before spatial records; sea/ocean state before climate
diagnostics; climate before water diagnostics; sediment transport histories
before sequence stratigraphy; ice-sheet histories before stability; soils
before biomes and permafrost; aquifer/recharge records before groundwater flow;
and channel morphology before hydraulic reaches.

Native generation has already completed the physical simulation and, in a full
world, generated settlements and society. Python functions such as
`enrich_world_with_settlement_route_models` attach provenance for those native
records; they do not regenerate settlements. Moving these metadata functions
around cannot repair a native simulation-order defect.

The second shared helper, `api._enrich_ecosystems_and_resources`, runs after the
physical foundation. Full generation creates navigability and ports first
because reef records link to Python-generated port IDs. Ecosystem renewable
records precede reef fishery links, and deposits precede ore/sedimentary systems,
which precede petroleum and commodity occurrences. Geo-only generation strips
native civilization placeholders before either helper runs, preserving the
existing no-human branches of mixed models.

## Verification

`tests/test_enrichment_pipeline.py` compares complete full-world payloads for
the two cell-output settings and verifies the caller's configuration remains
unchanged. It independently counts negative monthly temperatures for every
permafrost region in full and geo-only generated worlds, exercises missing and
stale biome caches, and corrupts an aggregate to confirm validation rejects it.

`geo_validation_subsystems._validate_cryosphere` now replays regional means for
freezing months, permafrost extent, active-layer depth, and ground-ice content
from their member cells. Previously the validator checked membership, bounded
cell fields, area/counts, and summary counts but could accept stale regional
means.

Cell-free full-world exports preserve useful records and summaries; they are
not standalone inputs for spatial validation, rendering, or the debugger.
Their records still reference omitted cell IDs, and omitting cells does not
reduce the enrichment work or its peak memory.
