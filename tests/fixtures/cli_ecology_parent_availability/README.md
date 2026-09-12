# Original full-world inputs for consumer availability integration

These compact archives retain three actual complete public generation outputs.
They contain the older, explicitly declared ecosystem-v3 consumer chain. The
tests replay the current Python consumer stages from these original inputs;
they do not substitute a migrated output as the only input or regenerate native
terrain and climate. `manifest.json` records the compressed and raw SHA-256
hashes, original provenance and the companion generation configuration.

| Fixture | Original climate/configuration | Coverage |
| --- | --- | --- |
| `warm.json.gz` | Version 2 seasonal Earth-like, seed 424242, 128 Fibonacci cells, 8 plates, erosion 1, one CPU thread | Supported biological resources and ranges; complete fire fronts |
| `cold.json.gz` | Version 2 seasonal cryogenic, seed 12051004, 128 Fibonacci cells, 12 plates, erosion 0, one CPU thread | Unavailable terrestrial parents and fisheries; icy unknown fuel must not become a known barrier |
| `legacy.json.gz` | Explicit `LegacyWorldConfig`, seed 424242, 128 Fibonacci cells, 8 plates, erosion 0, one CPU thread | Historical energy compatibility and a current consumer replay with two partial fire histories and four unmodelled directed front edges |

The legacy configuration is the recorded explicit legacy constructor input, not
a current unversioned YAML recipe. The old temperature controls retain their
historical meaning only in that constructor.

`test_cli_ecology_parent_availability.py` checks hashes, loads each complete
original, and calls the unchanged API consumer order: ecosystem, reef, species,
wildfire, deposits, ore, sedimentary basins, petroleum and commodities, followed
by the actual full-world land-use/human/graph/phonology tail. This refreshes
downstream ID links when unsupported fishery deposits are omitted. Physical cell
fields and native climate/material tables are asserted unchanged, and the native
energy certificate or explicit historical energy equations are independently
checked. Both originals and replays must pass the complete public CLI.

The same originals may be used by `test_geo_parent_availability.py` to inspect
selected natural checks in a full-world geo report. Their scope remains a full
world; they are not relabeled as geo-only outputs. Small numerical boundary tests
in the CLI module are explicitly stage tests and make no physical-world claim.

The absolute paths in the provenance manifest identify the review that captured
the sources. Test loading uses only these portable files and has no dependency
on those paths, ignored `runs` data, network access or native generation.
