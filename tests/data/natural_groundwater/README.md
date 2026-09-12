# Retained natural-groundwater stage fixtures

These are complete **128-cell source-mesh projections** from the genuine public
full and geography-only outputs produced by the isolated settlement integration
on 2026-09-10. Every consumed aquifer/groundwater input, cell output, system,
source graph link and summary is retained unchanged. Every original resource
deposit is also retained as a noninterference control. Climate model declarations
are preserved as opaque objects; the large native energy arrays are not in this
projection, so it is not a full-world energy certificate.

`manifest.json` records exact raw-world and projection hashes, retained field
lists, all original full-cell hashes, and the original aquifer/groundwater source
hashes. No test reads `/tmp`, ignored `runs/` artifacts or an old producer module.
Tests explicitly remove both old aquifer/flow model identities and their summary
identities before requesting a natural-v2 rebuild. The old fixtures remain v1.

Original generation used the retained `source-config.yaml` (seed424242, actual128
Fibonacci cells, eight plates, one erosion iteration, twelve climate months,
native seasonal energy, output precision4). Both public calls were:

```python
config = load_config(config_path)
full_world = api.generate_world(config)
geo_only = api.generate_geo_world(config)
```

The original isolated command was:

```sh
/home/andres/CLionProjects/magic-geo/.venv/bin/python /tmp/settlement-native-integration/public_probe.py
```

It pinned `MAGIC_GEO_NATIVE_LIBRARY` to the isolated settlement candidate library
SHA256 `06313362db4969042e05fc91a5c251668716d7a40a37d67512b6a1ba8a185e36`
and imported that candidate's `work/src`. The configuration SHA256 is
`b294bedf369796881503a0069d7ab2388786a25a8fb6db46c45c7887b6ca8e49`.
Re-running a newer default producer need not produce these historical bytes;
the fixture hashes preserve that distinction.

To reproduce the extraction from those exact retained raw worlds:

```sh
python tests/data/natural_groundwater/extract.py --source-directory /path/to/original/json
```

The script requires files named `full_world.json` and `geo_only.json`, checks
their hashes before reading fields, and checks the resulting projection hashes
before writing. It performs no native generation. Separate review-only evidence
also replays both untrimmed originals and eleven retained scenario archives;
those ignored files are never required for the permanent tests.
