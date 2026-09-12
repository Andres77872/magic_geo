# Genuine complete natural-stage fixtures

These four fixtures preserve complete connected source meshes: public full128,
public geo128, Continental162 and Glasswind128. They retain every consumed input,
output, model declaration, system record, graph link and summary for aquifer,
groundwater, channel, hydraulics and karst. Every original material deposit and
both climate declarations are retained as unrelated source controls. The bulk
native energy certificate is omitted: these are stage projections, not full
world/native-energy validation fixtures. No coefficients or source values have
been synthesized. Tests load only these portable files.

`manifest.json` lists exact retained fields, original archive SHA256, projection
SHA256 and every original complete source-cell hash. The historical producer
outputs remain stored unchanged. Tests explicitly remove aquifer/groundwater/
channel/hydraulic own objects and corresponding summary identities before
building current natural v2. Historical karst has no own declaration; its first
new declaration is only published after an intentional parent upgrade.

The public pair was originally produced from `public-pair-config.yaml`, seed
424242, actual128 Fibonacci cells,8 plates,1 erosion iteration, display4. The
original command was:

```sh
/home/andres/CLionProjects/magic-geo/.venv/bin/python /tmp/settlement-native-integration/public_probe.py
```

That probe imported the isolated settlement candidate's `work/src`, pinned the
native library SHA256
`06313362db4969042e05fc91a5c251668716d7a40a37d67512b6a1ba8a185e36`, and called
`api.generate_world(config)` and `api.generate_geo_world(config)`. Its exact
configuration SHA256 is
`b294bedf369796881503a0069d7ab2388786a25a8fb6db46c45c7887b6ca8e49`.
The original full/geo files were retained before this natural-water change;
their independent original hashes are in the manifest. That temporary probe
is provenance, never a fixture test dependency.

Continental/Glasswind come from the existing scenario migration run, generated
with this repository's `scripts/research/scenario_migration_probe.py` using raw
V4 native generation followed by same-state public geo enrichment. The stored
`continental_realm.config.json` and `glasswind_desert.config.json` are the exact
requested configs. Continental's requested128 geodesic mesh has actual162
cells; it contains6 channel systems and8 karst systems. Glasswind contains no
channels and3 karst systems, providing an independent empty-channel control.
The corresponding original reproduction command was:

```sh
.venv/bin/python scripts/research/scenario_migration_probe.py --output runs/seasonal-scenario-migration-replay --compare-legacy
```

The research runner also accepts `--only continental_realm` or
`--only glasswind_desert`. Later code changes can intentionally change historical
outputs; regenerating with current code is not a substitute for these exact
retained sources. Re-extraction verifies original hashes and needs no solver:

```sh
python tests/data/natural_downstream/extract.py --public-directory /path/to/original/public-json --scenario-directory /path/to/original/scenario-archives
```

The source hash manifest detects an accidental wrong archive; it does not claim
that a hash independently proves physical correctness. Numerical, ancestry,
record and mutation checks are implemented separately in the test module and
producer-independent replay helpers. No native generation ran while preparing
these projections or the downstream candidate.
