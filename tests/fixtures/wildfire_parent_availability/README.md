# Historical wildfire compatibility fixture

Exact projection of existing `runs/seasonal-scenario-migration/earthlike_seed.world.json.gz`; no generation or climate mutation.

Source SHA-256: `a59ca1981f92eac2b6a7fc61d0cbf09f590d59434f8e78f9c1326bf6acee63c8`.

Retains full cells, native climate certificate/enrichment and original ecosystem-v3/fire-v3 metadata, histories and summary. Other unrelated world sections are omitted; tests exercise the historical wildfire validator, not full-world validation.

## Supported legacy coefficient parity fixture

`supported_legacy_v2_world.json` is a synthetic three-cell land chain at annual18 C, generated with the frozen ecosystem-v3/fire-v2 producers. It retains the old .06 energy-stress ignition term. All parents are supported when migrated to ecosystem v4, so new fire-v4 shared numerical/history fields must equal this archived output. New availability/coverage fields are checked separately. Tests load this JSON and never import a temporary baseline source.

Source SHA-256:

- `ecosystem_dynamics.py`: `ea30f3343067d6244e17f886d3f532768630ed1cb66c5344d19537cc194f49ee`
- `wildfire_disturbance.py`: `d1f2201581e58e09ae4b7dfcb271ee0d5bcb7c4725da4b9854eaefd5e6a6f1cf`

Reproduce with those source versions: create IDs0–2 with reciprocal chain neighbors, annual temperature18, unit area/fertility/moisture/fire-frequency/aridity/settlement/east-wind/legacy-energy-stress, zero latitude/north-wind, longitude equal to ID, temperate_forest land, and soil_organic_carbon_fraction0.2. Apply ecosystem enrichment then wildfire enrichment; serialize sorted indented JSON. This is a legacy coefficient regression, not a physical energy or fire certificate.
