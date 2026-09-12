# Archived terrestrial-primary inputs

`cells.json` contains five unchanged cell-input subsets from actual seasonal
scenario generation, plus the five original ecosystem-v3 outputs used to show
the additive support defect and preserve ordinary behavior. It is not a full
native climate certificate. The standalone tests do not load ignored files,
compile C++, regenerate climate, or import the extraction script.

The hot witnesses are Verdant cell 21 (annual 73.7713 C, all months above 70 C)
and Young cell 8 (annual 63.1827 C). Cryogenic cell 0 is the cold witness
(annual -53.9266 C). Earthlike cells 16 and 30 are ordinary terrestrial and
marine controls. These temperatures are inputs to the audit, not fitted values.
The original positive outputs outside the declared primary-temperature domain
are preserved under `expected_v3`; they are not expected corrected outputs.

The source archives were produced by the preserved-forcing scenario probe:

```sh
.venv/bin/python scripts/research/scenario_migration_probe.py --output runs/seasonal-scenario-migration-replay --compare-legacy
```

That command reads `configs/earthlike_seed.yaml` and `configs/seeds/*.yaml`,
retains their physical inputs, uses 128 cells and zero erosion iterations for
these shipped scenarios, then applies the public Python geo enrichment to the
same native world. This fixture was captured before applying ecosystem v4.
To recreate the historical `expected_v3` outputs, use the pre-patch v3 producer;
the extraction tool rejects other ecosystem model versions instead of silently
replacing the baseline with corrected output. The captured producer SHA-256 is
`ea30f3343067d6244e17f886d3f532768630ed1cb66c5344d19537cc194f49ee`.

Extract the archived cells without recomputing any coefficient or field:

```sh
.venv/bin/python scripts/research/extract_terrestrial_primary_support_fixture.py --archive runs/seasonal-scenario-migration-replay --output tests/fixtures/terrestrial_primary_support/cells.json
```

Each case records the source archive filename, compressed-byte SHA-256 and cell
ID. The extractor copies the listed producer inputs only when they are present;
an absent field remains absent. It copies the original five ecosystem outputs
verbatim. Re-extraction from the original archives must reproduce this file
byte for byte. New runs can differ in archive hashes if unrelated serialized
fields change; do not discard the recorded original provenance for that reason.

These witnesses establish availability behavior for the existing annual-air
primary-productivity proxy. They do not validate Köppen labels as resident
forest ecology, a biological temperature limit, growing-season applicability,
species ranges, agriculture, settlement, fuel or wildfire.
