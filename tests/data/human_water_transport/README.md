# Retained human water transport fixtures

These are complete genuine retained worlds, compressed with deterministic gzip
mtime zero. `manifest.json` records the original source path/file hash, decoded
JSON hash and portable gzip hash. Tests verify both local hashes before loading;
they never read the original paths and never generate a native world.

- `legacy_full.json.gz`: original full128 with valid natural v1 and human v1.
- `natural_parents_full.json.gz`: same native/human source, with only the frozen
  aquifer/groundwater/channel/hydraulics/karst chain upgraded. Its historical
  navigation/ports/corridors are deliberately stale; tests remove both own and
  summary identities and recompute those three stages in order.
- `natural_geo.json.gz`: matching genuine geo128 with the five natural stages
  upgraded. Human sections remain absent and direct human-stage publication is
  rejected as inapplicable.

`source-config.yaml` is the exact retained public-pair configuration from the
frozen natural-stage fixtures. The full/geo natural source identity is preserved.
The stage-specific synthetic threshold, Dijkstra tie and endpoint-skip controls
in the test module are explicitly isolated policy tests, not full-world proofs.

The full positive witness has 4 settlements, 5 coastal-sea routes, 2 waterways,
4 ports and 5 corridors. It covers both empty and nonempty waterway human-link
sets but is not evidence for all route classes or ecological/settlement support
domains. No downstream population, market, ecology or whole public CLI acceptance
is inferred from these stage checks.
