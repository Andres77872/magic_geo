# Native seasonal energy witnesses

These compressed JSON fixtures come from the C++ serializers. No physical
coefficient, forcing node, temperature, moment, budget, tolerance or achieved
metric was recomputed for Python tests. Tests read these checked-in files and
do not require any ignored `build/`, `runs/` or `/tmp/` artifact.

`world_128.json.gz` retains the four complete native certificate objects,
`climate_model`, `planet_parameters`, and the ten cell fields listed in its
manifest. It is the first reference world emitted by
[`seasonal_climate_pipeline_test.cpp`](../../../cpp/tests/seasonal_climate_pipeline_test.cpp):
`Params` defaults (seed 424242, Fibonacci mesh, Earth orbital/atmosphere
parameters) with name `seasonal_climate_pipeline`, 128 cells, eight plates,
zero erosion iterations, one thread, eight display decimal places, and the
explicit `prescribed_seasonal` temperature model. The fixture includes
heterogeneous land/marine storage, pressure and conservative transport, plus
two cells classified as lakes after the retained pre-flow solve.

The two `certificate_12_*.json.gz` fixtures are the independently solved
TR-BDF2 and backward-Euler cases from
[`seasonal_climate_serialization_test.cpp`](../../../cpp/tests/seasonal_climate_serialization_test.cpp).
They use 12 Fibonacci cells with exposed elevation `1300 + 200*z` metres and
cell zero as a 7.123456789012345-metre marine column. They intentionally lack
full-world linkage fields and are accepted only by explicitly requesting a
certificate-only audit.

From the repository root, reproduce the sources and extract the fixtures:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build build --target magic_geo_seasonal_climate_pipeline_test magic_geo_seasonal_climate_serialization_test -j2
build/magic_geo_seasonal_climate_pipeline_test /tmp/generated_128_native_world.json
build/magic_geo_seasonal_climate_serialization_test /tmp/serialization_12_witness.json
.venv/bin/python scripts/research/extract_native_climate_fixture.py /tmp/generated_128_native_world.json tests/fixtures/native_climate_energy/world_128.json.gz
.venv/bin/python scripts/research/extract_native_climate_fixture.py /tmp/serialization_12_witness.json tests/fixtures/native_climate_energy/certificate_12_tr_bdf2.json.gz
.venv/bin/python scripts/research/extract_native_climate_fixture.py /tmp/serialization_12_witness.json.be.json tests/fixtures/native_climate_energy/certificate_12_backward_euler.json.gz
```

The extraction tool only selects fields and encodes JSON with deterministic
key ordering and gzip `mtime=0`. Adjacent manifests record the source JSON,
retained JSON and gzip SHA256 hashes, byte sizes and complete retained-field
lists. Floating-point solver differences across toolchains can change source
hashes; regenerations must be reviewed and audited, never adjusted to satisfy
a fixture expectation. The source hashes identify the exact archived outputs
used to create the current fixtures.
