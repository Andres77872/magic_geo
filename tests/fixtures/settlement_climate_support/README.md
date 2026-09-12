# Retained settlement applicability fixtures

These inputs exercise the settlement subsystem. They are not complete physical
world fixtures, and synthetic climate linkage records do not certify energy
balance. No test generates a new climate or reads a temporary build directory.

`native-unit-worlds.json.gz` contains five outputs of the real native
environment/settlement/route/political functions: supported, hot, immediately
inside the upper endpoint, the endpoint, and explicit legacy mode. The native
CTest target independently runs those functions and boundary assertions. Its
optional JSON output is a build artifact, not a Python fixture prerequisite.

The Earth-like, hothouse and young-volcanic archives retain actual accepted
128-cell seasonal climate source records. Their two branches rerun only the
environment/settlement/route/political stages on those same retained inputs,
once with the historical selection and once with applicability-aware selection.
The old branch is explicitly labelled `old_selection_on_same_seasonal_inputs`;
it is a selection comparison, not an old native climate simulation.

`legacy-enriched.json` retains the exact compact JSON produced by the frozen
historical Python metadata producer for the native legacy unit case. The test
compares current output bytes with it without importing an old source module.

`manifest.json` records raw and deterministic-gzip hashes and the frozen legacy
producer hash. Its retained-source paths document the original review run;
runtime loading uses only the adjacent fixture filenames. All material and
climate fields in the paired archives remain unchanged by the applicability
finalizer. Supported scores retain their existing formulas.
