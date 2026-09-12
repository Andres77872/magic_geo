# Natural groundwater and settlement dependencies

Review date: 2026-09-10. The observed dependency error below is now corrected in
main by the versioned natural-water chain. The original generated evidence and
historical v1 behavior remain retained; the adoption evidence is recorded below.

## Reproducible discrepancy

The isolated settlement candidate generated full and geography-only worlds from
the same unmodified 128-cell smoke configuration. All native climate certificates
and temperatures are identical. All 128 settlement-climate flags are true, so
this is not evidence of unavailable settlement inputs in that particular world.

Nevertheless, 47 cells differ in aquifer extraction risk, productivity and
hydraulic head, and 48 differ in groundwater discharge. At cell 0, full/geo
extraction risk is 0.354193/0.339 and hydraulic head is
2618.808315/2619.747242 metres. Recharge, aquifer storage and quality agree.
The relevant consumer sources matched the main repository at diagnosis time.

`api._strip_native_civilization_outputs` removes `settlement_score` before the
geography-only natural foundation. `aquifer_resources.py` reads that field with
a default zero and adds 0.18 times its bounded value to extraction risk. This
risk decreases aquifer productivity. `groundwater_flow.py` then uses risk in
saturation, depth to water, lateral export and discharge calculations. A
score intended for settlement selection therefore changes ostensibly natural
groundwater when the requested output scope changes.

Exact source hashes, unchanged generated inputs, comparisons and independently
replayed consumer checks are retained under
[`runs/groundwater-dependency-review`](../runs/groundwater-dependency-review/README.md).
The two public outputs are compressed with their original uncompressed hashes.
The evidence also records standing lake cells in native population membership;
that is a separate consumer issue and is not repaired by changing aquifers.

## Scientific distinction

Natural groundwater accounting separates recharge, discharge and storage change.
Actual withdrawal changes those terms and the flow system over time; natural
recharge alone is not a sustainable-yield calculation. A location's settlement
suitability does not supply a withdrawal volume or a pumping schedule.
[USGS groundwater development and water budgets](https://pubs.usgs.gov/circ/circ1186/html/gw_dev.html)

MODFLOW's well package represents a specified volumetric flow rate at a cell,
with pumping and injection distinguished by sign. Its groundwater framework
separates aquifer-property calculations from stresses such as wells, recharge,
rivers and drains. This supports an architectural distinction between the
natural aquifer calculation and a later explicit human-use stage; it does not
validate this simulator's present index coefficients or prescribed head formula.
[USGS Well Package](https://water.usgs.gov/ogw/modflow/MODFLOW-2005-Guide/wel.htm),
[USGS MODFLOW 6](https://www.usgs.gov/software/modflow-6-usgs-modular-hydrologic-model)

## Correction contract

The adopted v2 model makes natural aquifer/groundwater outputs independent of
settlement fields and output scope, retains exact historical-version replay, and
declares the remaining diagnostic character of head and productivity estimates.
Human water use can affect flow only through a separately declared stage with
explicit sources, units and water-budget consequences. A risk index must not be
presented as a withdrawal rate or measured depletion.

Acceptance must compare complete natural fields and record links for the same
physical inputs with settlement fields present, absent and altered; preserve
infiltration/recharge partition and groundwater volume ledgers; and rebuild
wetland, resource and downstream human links in their actual dependency order.
An independent formula/graph replay must reject forged model identities and
stale summaries. Successful ledger checks alone cannot establish calibrated
hydraulic heads, transmissivity or sustainable pumping capacity.

## Main adoption and acceptance

The reviewed change includes natural aquifer/groundwater v2, matching channel
and hydraulic v2, the declared karst model, and navigation/port/corridor v2.
Natural stages depend on actual physical parents; the human transport stages
follow them, then reef links, ecology, resources and subsequent society layers
run in API order. Independent public replay checks the complete declared chain
before eager numeric consumers. Historical v1 equations retain explicit dispatch.

Actual full and geography-only API outputs agree across all 128 comparisons of
natural owned fields, records/models and summaries on the retained physical
configuration. Both preserve five native climate objects and nine raw physical
and material fields exactly. The full world passes CLI validation; geography-only
passes generic geo validation while retaining absence of human transport stages.
Additional actual checks cover a non-Earth world and two custom 512-cell
hydrology configurations, including disabled preservation of geologic depressions.

The exact 77-path adoption contains 28 production and 49 test/fixture paths.
Fresh combined verification passes 848 tests and 612 subtests using complete
hash/config-checked archives, ordered current Python replay and native-generation
barriers. All applied hashes match; 541 unrelated existing files and the native
library are preserved. Post-application main checks pass 92 Python tests and
eight JavaScript checks. The complete patch, input provenance, retained outputs
and reports are in
[`runs/natural-water-main-adoption`](../runs/natural-water-main-adoption/README.md).

This removes the suitability dependency and ambiguous extraction-risk naming
from fresh natural outputs. It does not introduce groundwater withdrawals or
calibrate diagnostic hydraulic heads, material properties or sustainable yield.
Python agricultural availability has since been adopted through a separate
[land-use contract](agricultural_availability_review.md). Native population,
settlement applicability and seasonal ice coupling remain separate model work.
