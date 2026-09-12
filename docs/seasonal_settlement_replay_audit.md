# Seasonal settlement witness and political membership replay

The migrated route smoke tests retain the original Earthlike seed 424242,
Fibonacci 256 cells, eight plates and one erosion iteration. They now use the
current version-2 physical controls, including reference optical depth 1;
the obsolete lapse overrides 4 and 2 were removed without substituting fitted
temperature controls or changing any settlement criterion. The two now-identical
fixtures share a module-local generated cache and copy it before mutation.

The actual seasonal witness contains six settlements, nine routes and route
corridors, four nonmarine river cells and four port sites. Its original public
validation failed even though the generated settlement scores, candidate set,
ranking, separation, types and political assignment replay were correct.

## Demonstrated cause

Settlement 4 occupies cell 44. Its `region_id` is 1, while the cell's
`political_region_id` is 0. These are different declared calculations in
[`civilization.cpp`](../cpp/src/engine/civilization.cpp):

- Settlement allegiance uses basin/coast discounts 0.76/0.72 and, if present,
  a direct-route discount of 0.45 or 0.58.
- Territorial cell assignment uses basin/coast discounts 0.80/0.76 and does
  not apply a direct-route discount.

The independent costs from this exact published world are:

| Candidate region | Capital cell | Settlement allegiance cost | Territorial cell cost |
| --- | ---: | ---: | ---: |
| 0 | 40 | 22162.740614224 | 22162.740614224 |
| 1 | 103 | 21246.175000247 | 22426.518055816 |

Here the different coastal coefficients cause the different assignments.
Neither capital has a direct route to settlement 4; this is not evidence of a
direct-route discount being applied. The native metadata explicitly declares
the separate assignment models and coefficients. No assertion of real political
behavior follows from these procedural costs.

The settlement validator incorrectly required allegiance to equal host-cell
territory. Its corrected check verifies existing region IDs, unique and complete
region-to-settlement membership, each capital's membership in its own region,
and each settlement's reverse region link. The independent political validator
continues to reconstruct both costs and capital selection. Settlement score,
type, geometry, fertility, resource, culture and language checks are retained.
No native selection, territorial assignment, climate, or hydrology code changed.

## Verification and reproduction

The unchanged captured world now returns `OK` from the full public `validate`
command. The final three focused smoke cases pass, including 14 subtests, in
58.80 seconds. They retain positive settlement/route/rivers assertions, add
explicit native-model/port/corridor witnesses, exercise all five river/coastal
model tamper verdicts, and reject corrupted membership, duplicate/omitted
members, unknown regions and a capital assigned to a foreign region. Both
assignment replays reject substituting the host territory for valid allegiance.
The other four smoke-module tests passed in the earlier full run; its two
baseline CLI failures were the defect described above.

```bash
.venv/bin/python -m pytest tests/test_smoke_settlements_routes.py -q \
  -k 'settlement_cost_allegiance or two_settlement_regime or validate_reports_every'
```

The generated artifact is retained as
`runs/seasonal-settlement-256-witness.json.gz` (with an uncompressed `.json`
copy for CLI replay), and the independently computed costs are in
`runs/seasonal-settlement-256-allegiance-costs.json`. The archived world took
54.91 seconds to generate on this development machine; it is not necessary to
regenerate it for each validator experiment. Focused results are in
`runs/review-seasonal-settlement-route-witness-tests.xml`. The test imports
current shipped inputs and generates its own witness; it does not depend on
ignored artifacts or temporary scripts.
