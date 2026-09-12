# Seasonal climate configuration and ABI migration plan

Inventory date: 2026-09-09. **Standalone C ABI V4 and seasonal default adoption are implemented in source.** `WorldConfig()`, all three profiles, ten shipped complete configurations, the workbench and direct C++ defaults select the seasonal model. YAML requires exact integer `config_version: 2`; unversioned documents receive migration errors. Explicit `LegacyWorldConfig` and C ABI V1–V3 preserve compatibility behavior. The [integration record](seasonal_climate_native_integration.md) distinguishes prior explicit-V4 checks from the ongoing broad default regression, and the [scenario migration report](seasonal_scenario_migration.md) records observed changes without inheriting old calibration claims.

The model and integration constraints are established in [the research note, §7](seasonal_energy_balance_model_research.md#7-native-integration-map-and-temperature-contract-migration). Measured adaptive accuracy, performance and remaining applicability limits are recorded in [the same research note, §11](seasonal_energy_balance_model_research.md#11-adaptive-methods-at-the-same-monthly-verification-gate). This document inventories the code and data migration rather than replacing those findings.

The [vertical-model note](seasonal_climate_vertical_model_research.md#implemented-adapter-and-verification) records the physical-column/composition adapters. The [output contract](seasonal_climate_output_contract.md) describes native budgets, independent validation and Python annual aggregation. Consumer, presentation and default-profile migration are tracked separately from the completed V4 boundary.

The implemented version-2 configuration uses finite, nonnegative `climate.reference_infrared_optical_depth` (`tau_ref`), with declared default 1 and numerical representability/work failures instead of an arbitrary finite upper bound. `planet.greenhouse_factor` is explicitly described as an opacity multiplier. Generated mean temperature is an output. There is **no scientifically exact automatic conversion from the old imposed global temperature to the new model's opacity**. Old Celsius/lapse controls are rejected with field-specific guidance in version-2 constructors, YAML and overrides. Shared physical controls retain their existing bounds; new section models reject coercion and nonfinite values before native marshaling.

## 1. Current configuration and version contracts

| Current surface | Implemented behavior |
| --- | --- |
| `config.py::WorldConfig`, public section types | Current strict seasonal model with deliberate constructor default version 2; `SeasonalWorldConfig` requires an explicit version even in direct construction. Shared old constraints live in `_config_models.py`; `LegacyWorldConfig` names compatibility use explicitly. |
| `parse_config_yaml`, `load_config` | Exact integer version 2 required; missing/old/future/wrong-type versions and both obsolete temperature controls receive source-aware issues. Empty documents are rejected. |
| `create_config`, all shipped YAML | New version, explicit reference opacity 1, preserved non-climate inputs and profile names. Earth reference is no longer described as calibrated for the new climate model. |
| `config_schema`, workbench | Schema URI/metadata version 2, required scalar root version, current templates/rendering and searchable opacity guidance; stale/mismatched responses cannot replace editor state. |
| `dump_config_yaml`, `write_config`, overrides | Version preserved; exact saved bytes revalidated before atomic publication; field-specific obsolete-control errors. Explicit legacy model instances remain available only for compatibility use and cannot silently lose a copied version marker. |
| `config_to_native`, Python API | Version/physical inputs preserved into V4; no temperature-to-opacity conversion or fallback. All dependent enrichment runs before final cell omission. |

Configuration-document version, native ABI version and world-output schema are separate contracts. The prior 1,206-test explicit-V4 integration run established that interface, not the complete acceptance of newly changed defaults. Current regression work retains generic geology and downstream tests on the new model and reserves legacy fixtures for assertions about the preserved old equations/ABI.

## 2. Shipped YAML migration

**Ten complete world configurations now use version 2 and reference opacity 1.** Their retired temperature controls are recorded below as historical provenance; all other physical inputs were preserved. Generated outcomes and limits are in the [scenario report](seasonal_scenario_migration.md).

| File | Retired base °C | Retired lapse °C/km |
| --- | ---: | ---: |
| [`configs/earthlike_seed.yaml`](../configs/earthlike_seed.yaml) | 15 | 6.5 |
| [`configs/seeds/continental_realm.yaml`](../configs/seeds/continental_realm.yaml) | 14 | 6.5 |
| [`configs/seeds/cryogenic_slushball.yaml`](../configs/seeds/cryogenic_slushball.yaml) | −10 | 6.5 |
| [`configs/seeds/glasswind_desert.yaml`](../configs/seeds/glasswind_desert.yaml) | 32 | 7.5 |
| [`configs/seeds/ironroot_super_earth.yaml`](../configs/seeds/ironroot_super_earth.yaml) | 14 | 6.0 |
| [`configs/seeds/oldstone_stagnant.yaml`](../configs/seeds/oldstone_stagnant.yaml) | 8 | 6.5 |
| [`configs/seeds/pelagic_archipelago.yaml`](../configs/seeds/pelagic_archipelago.yaml) | 18 | 6.0 |
| [`configs/seeds/solstice_extreme.yaml`](../configs/seeds/solstice_extreme.yaml) | 12 | 6.5 |
| [`configs/seeds/verdant_hothouse.yaml`](../configs/seeds/verdant_hothouse.yaml) | 30 | 5.5 |
| [`configs/seeds/young_volcanic.yaml`](../configs/seeds/young_volcanic.yaml) | 32 | 7.0 |

[`configs/geo_validation_matrix.yaml`](../configs/geo_validation_matrix.yaml) previously had **two obsolete overrides**: snowball used `base_temperature_c: -10`; hothouse used `35`. Both overrides now explicitly use reference opacity 1. Their other physical inputs and original validation expectations are retained for reassessment. The matrix's `schema_version: 1` describes the validation manifest, not a world configuration; do not change it merely because the climate configuration changes.

The old values above are inventory evidence, not a conversion table. Select new controls under their declared physical meaning and retain the scenarios' intended behavioral coverage. Updating fixture inputs is not evidence that the new model preserves the old generated climate.

## 3. Native boundary and legacy behavior

[`cpp/include/magic_geo/native.hpp`](../cpp/include/magic_geo/native.hpp) defines C++ `Params` and the stable `CConfig`, `CConfigV2`, `CConfigV3` structures. [`src/magic_geo/native.py`](../src/magic_geo/native.py) mirrors their layout with `NativeConfigV1/V2/V3`.

The currently asserted ABI sizes are **304, 312 and 320 bytes**. The legacy lapse field remains at offset **192**, base temperature at **200**, V2 compute fields at **304/308**, and V3 maturation timestep at **312**. These old structures must remain byte-for-byte unchanged. In particular, do not insert a model selector or optical depth into a legacy structure.

| Source/function | Required action |
| --- | --- |
| `native.hpp::Params` | Implemented: scoped `ClimateTemperatureModel`, prescribed-seasonal default and named reference optical depth. Direct C++ callers must rebuild when `Params` changes; it is not the stable C ABI. |
| [`c_api.cpp::params_from_c_config(const CConfig&)`](../cpp/src/c_api.cpp) | Implemented: explicitly selects legacy climate behavior and retains old field meanings. Future `Params` default changes cannot silently select seasonal behavior here. |
| `c_api.cpp::params_from_c_config(const CConfigV3&)` | Implemented: preserves legacy model selection through the V1 adapter while applying V3 maturation timestep. V2 uses the same base adapter plus compute options. |
| `CConfigV4` and `params_from_c_config(const CConfigV4&)` | Implemented standalone seasonal-only layout below. Unconditionally selects `prescribed_seasonal`; no legacy Celsius fields or prefix. |
| `native.py::_native_seasonal_config` | Implemented strict versioned marshaling to `NativeConfigV4`, including revalidation of constructed/mutated instances. Legacy `_native_config` retains its V3 meaning. |
| `native.py::_load_seasonal_library` | Requires and binds all four V4 JSON/MessagePack entry points. Missing symbols produce a rebuild error; no downgrade. |
| `native.py::generate_seasonal_world`, `generate_seasonal_geo_world` | Implemented all V4 routes, strict decoding, configured-input checks and independent budget audit. `api.generate_world`/`generate_geo_world` select these for `SeasonalWorldConfig`. |
| [`core.cpp::validate_params`](../cpp/src/engine/core.cpp) | Implemented: model-appropriate control validation, including finite nonnegative seasonal opacity; legacy mean/lapse checks remain specific to legacy calls. |
| [`climate.cpp::compute_climate`](../cpp/src/engine/climate.cpp), `core.cpp::climate_thermal_moisture_temperature_anomaly_c`, [`process_serialization.cpp::climate_model_json`](../cpp/src/engine/process_serialization.cpp) | Implemented for explicit C++ selection: retained seasonal temperature and solved-mean rainfall dependency, with separate state-aware output. Legacy helper/model behavior remains isolated. New public configuration must preserve this dispatch. |

### Implemented standalone V4 layout

Use a **standalone seasonal-only structure**, rather than extending a V3 prefix that still carries obsolete temperature controls. V4 has no runtime temperature-model selector: calling a V4 generation symbol selects the prescribed seasonal model. The function suffix specifies the C ABI; the configuration-document discriminator and serialized climate-model identifiers remain separate contracts. No legacy structure is cast to V4, and structure size alone must never select a version.

The implemented field order below keeps common fields in their familiar order, replaces the two Celsius fields with named optical depth, and adds maturation and compute controls explicitly. All integral controls use `std::int32_t`; the seed uses `std::uint64_t`. Natural platform alignment is used without packing pragmas. **Every listed offset, alignment 8 and total size 312 are checked in C++ and Python tests on the current 64-bit, 8-byte-double ABI.** These values do not assert an untested 32-bit layout. The ctypes mirror uses `c_uint64`, `c_char_p`, `c_double` and `c_int32`, without an anonymous legacy base.

```cpp
// Declared in native.hpp and mirrored by NativeConfigV4.
struct CConfigV4 {
    std::uint64_t seed;                         // 0
    const char* name;                           // 8
    double radius_km;                          // 16
    double gravity_g;                          // 24
    double day_length_hours;                   // 32
    double axial_tilt_deg;                     // 40
    double orbital_eccentricity;                // 48
    double stellar_luminosity;                  // 56
    double atmosphere_pressure_bar;            // 64
    double greenhouse_factor;                  // 72
    double ocean_fraction_target;              // 80
    double ocean_water_inventory_km3;           // 88
    double internal_heat;                      // 96
    double geological_age_ga;                 // 104
    std::int32_t cell_count;                   // 112
    std::int32_t mesh_backend;                 // 116
    std::int32_t neighbor_count;               // 120
    std::int32_t plate_count;                  // 124
    double continental_plate_fraction;        // 128
    double continental_crust_fraction_target; // 136
    double min_angular_speed;                 // 144
    double max_angular_speed;                 // 152
    std::int32_t boundary_smoothing_steps;     // 160
    double plate_motion_scale_deg_per_step;   // 168
    double oceanic_crust_aging_ma_per_step;    // 176
    std::int32_t months;                       // 184
    double reference_infrared_optical_depth;  // 192
    double precipitation_scale;               // 200
    double subtropical_drying_strength;       // 208
    std::int32_t preserve_geologic_depressions;// 216
    double river_percentile;                  // 224
    std::int32_t erosion_iterations;           // 232
    double stream_power_coefficient;          // 240
    double drainage_exponent;                 // 248
    double slope_exponent;                    // 256
    double hillslope_diffusion;               // 264
    double tectonic_uplift_scale;              // 272
    std::int32_t threads;                      // 280
    std::int32_t include_cells;                // 284
    std::int32_t float_precision;              // 288
    double maturation_timestep_ma;            // 296
    std::int32_t compute_backend;              // 304
    std::int32_t opencl_prefer_gpu;             // 308
};                                            // sizeof 312, alignof 8
```

The size happens to equal V2's size; the layouts and semantics are different. Typed C++ declarations and ctypes `argtypes` require the specific V4 structure. V1/V2/V3 declarations, sizes, offsets and symbols remain unchanged. A future incompatible extension needs another explicit ABI rather than changing this structure in place.

The implemented adapters are `params_from_c_config(const CConfigV4&)` and `compute_options_from_c_config(const CConfigV4&)`. The former starts with `Params`, explicitly selects `prescribed_seasonal`, and copies every named science/output field, including optical depth and maturation timestep. It must not call a legacy-prefix conversion or derive a physical control from obsolete defaults. The compute adapter copies the existing backend policy unchanged. V4 uses strict `0`/`1` validation for the three V4 flag fields before conversion to C++ `bool`; retain the older adapters' existing nonzero interpretation. A null name may retain the established `"world"` fallback. The pointed-to, NUL-terminated name is borrowed only for the call and copied into `Params`; Python must retain its encoded bytes through that call.

V4 uses the implemented seasonal validation: finite nonnegative optical depth with no arbitrary finite upper limit, exactly 12 months, and the existing bounds on the other shared controls. Unrepresentable derived coefficients or numerical work failures remain explicit generation errors, never a fallback to legacy climate. This minimal boundary does not expose albedo, year length, hydrostatic profile, slab constants or solver controls; their prescribed defaults and actual values remain declared in the native model output. Additional controls would need a deliberate design decision and a new deliberate public contract.

All seven existing generation entry points retain their declared behavior: unversioned `magic_geo_generate_json`; V2 full/geography JSON; and V3 full/geography JSON and MessagePack. Four corresponding V4 entry points are implemented. Existing allocation/free conventions and exception-to-error transport remain applicable.

The four implemented signatures are `magic_geo_generate_json_v4(const CConfigV4*)`, `magic_geo_generate_geo_json_v4(const CConfigV4*)`, `magic_geo_generate_msgpack_v4(const CConfigV4*, std::size_t*)`, and `magic_geo_generate_geo_msgpack_v4(const CConfigV4*, std::size_t*)`, with the same return types and matching free functions as V3. Each wrapper dispatches through its V4 science and compute adapters to the existing full/geography C++ generator. JSON remains an owned NUL-terminated allocation freed by `magic_geo_free_string`; MessagePack remains an owned byte buffer with explicit length, freed by `magic_geo_free_buffer`.

The V4 exception boundary is nonthrowing, including error serialization and allocation. The existing `copy_error_msgpack_noexcept` pattern handles the binary case; an analogous JSON error-copy helper handles the new wrappers. A null configuration produces an encoded error when allocation succeeds. A null binary size pointer returns null without reading the configuration; initialize a supplied size to zero before work. If result or error allocation fails, return null with binary size zero. No C++ exception may escape even while formatting an earlier failure. This recommendation does not change old symbols' error behavior.

The current native output gate, `native.py::_require_current_world_schema`, independently requires world schema 2 and a valid planetary snapshot. **That is insufficient for V4:** a symbol-complete library returning legacy schema-2 output must be rejected before enrichment. Require `climate_model.model_type == "prescribed_seasonal_surface_energy_v1"`, `climate_energy_model.model == "native_prescribed_seasonal_energy_v1"`, budget schema 1 and native ownership, together with the three complete forcing/edge/per-cell budget arrays and their supported declarations. Preserve the native records for downstream verification. This identity/presence gate complements, rather than replaces, physical replay and consumer model dispatch.

Python's seasonal loader binds all four V4 symbols with `POINTER(NativeConfigV4)` and raw `c_void_p` results, retaining the current explicit freeing paths. A library missing any required V4 symbol gets a clear rebuild error; never retry V3 or silently switch JSON/MessagePack/model semantics. `serialization="auto"` continues to choose MessagePack. Validate the chosen configuration-document version and reject obsolete/missing fields before marshaling; do not let ctypes integer wrapping or permissive numeric conversion reinterpret an unvalidated mapping. Configuration version, C ABI version and world-output schema remain separate contracts; make any broader output-schema change explicit.

## 4. Web editor, saved files and actionable errors

[`debug_server.py::create_app`](../src/magic_geo/debug_server.py) provides `/api/config/schema`, `/profiles`, `/template`, `/render`, `/validate` and `/save`. Templates and schema are generated from the current Python models, so the editor has no hard-coded climate field form to replace.

`validate_config` and `save_config` already call `parse_config_yaml`. `_config_error` returns HTTP 422 with `ConfigError.to_dict()`. In [`debug_ui/app.js`](../src/magic_geo/debug_ui/app.js), `validationErrorMarkup` and `validateConfig` render issue paths/messages, and `fetchJson`/`saveConfig` preserve the composed error text. Actionable obsolete-field messages can therefore use the existing transport. Add endpoint/UI regressions instead of introducing a separate migration error protocol.

`flattenSchema`, `renderSchemaDocs`, `fetchTemplate` and `loadConfigWorkbench` discover fields, descriptions and defaults dynamically. The scalar root version is displayed, and the browser requires matching version-2 schema/profile/template envelopes with request-identity checks. YAML validation remains authoritative on the server.

Saved configurations are canonical validated YAML in `<workspace>/configs/<name>.yaml` (normally `runs/configs/`). `write_config` retains atomic write/revalidation and the server confines paths and checks overwrite conflicts. Browser `state.savedConfig` holds a name/YAML/path snapshot **only in memory**; there is no localStorage/sessionStorage version record, saved-file migration loader, or automatic saved-file conversion. Schema/template loading now checks version agreement. Existing save/template race protections should remain intact.

`generateFromSavedConfig` transfers the saved path into the operation form. [`web_jobs.py::JobManager._build_command`](../src/magic_geo/web_jobs.py) confines the input path but does not parse its YAML. An existing obsolete file is rejected later by [`cli/commands/generate.py::generate`](../src/magic_geo/cli/commands/generate.py), which prints the source-aware configuration error and exits 2; the workbench displays that failure in job logs. Inline validation already gives a better field-level experience, but generation from a path needs equally clear migration wording. Do not rewrite stored files automatically.

## 5. Test inventory and remaining acceptance

| Test surface | Current coverage and remaining work |
| --- | --- |
| `test_config.py`, `test_config_cli.py`, `test_seasonal_config.py` | Current profiles/schema, scalar root version, exact shipped equality, strict parsing/overrides, obsolete fields and V4 marshaling. Frozen V1–V3 layout checks retained. The combined maximum-input V4 generation passes; full-maturation gallery generation is included in the broader regression. |
| `test_native_boundary.py`, `test_native_messagepack.py` | Explicit V3 compatibility fixtures through `build_legacy_config`; their old-layout/ownership/error assertions are preserved. |
| `test_native_seasonal_boundary.py`, other `native_seasonal_*` and `native_climate_*` tests | Active V4 identity/configuration matching, ownership, strict decoding, raw/full/geo generation, independent certificate and annual-field validation, ecology dispatch and exports. |
| `c_api_v4_test.cpp`, `c_api_v4_allocation_test.cpp` | Every-field layout/mapping, four V4 generation routes and nonthrowing allocation/error paths. |
| `native_api_test.cpp`, frozen V1 client/layout tests | Preserved V1–V3 behavior and layouts, including explicit old-model output identity after `Params` default adoption. |
| `seasonal_climate_pipeline_test.cpp` and direct geological C++ integrations | Implicit seasonal default, retained budget and downstream temperature linkage; crust, sediment and ocean-age tests now use the new default. All 27 CTest cases pass in 158.90 seconds (`runs/review-native-seasonal-default-tests.log`). |
| `test_default_public_generation.py`, shared fixtures, climate/society smoke tests | Current-model generic fixtures and explicit old-equation controls; full downstream behavioral acceptance is still in progress. Obsolete lapse-based society witnesses require supported current inputs, without weakening branch coverage. |
| `test_seasonal_config_workbench.py`, `test_seasonal_workbench_schema.py`, `test_debug_ui.mjs` | Version-2 schema/templates/rendering, located obsolete-field errors, save/overwrite and job inputs, schema/template version agreement and request races. The workbench route suite has 31 passing cases. |
| `test_debug_server.py`, `test_web_jobs.py` | Valid YAML fixtures explicitly versioned; 115 tests and 200 subtests pass, including actual generation through the debug-cache workflow. |
| Slow public CLI tamper tests | Some old metadata/message and upstream-certificate assumptions still require migration. Retain healthy current controls and meaningful failures instead of silently switching whole suites to legacy. |

The full replay migration also touches [`geo_validation.py`](../src/magic_geo/geo_validation.py), [`geo_validation_physics.py`](../src/magic_geo/geo_validation_physics.py), [`cli/commands/validate.py`](../src/magic_geo/cli/commands/validate.py), and [`climate_energy.py`](../src/magic_geo/climate_energy.py). Follow research §7: preserve the native solved coefficients/budget as authoritative and validate the new discrete equation rather than the old mean-temperature identity or a separate diagnostic equilibrium. Configuration/ABI tests alone cannot establish physical or downstream integration correctness.

For the additive ABI itself, keep numerical generation coverage bounded: use one declared small seasonal configuration to exercise full/geography JSON and MessagePack, compare each transport's decoded authoritative energy values, and replay the resulting budget independently. Reuse the existing C++ producer tests for thermal accuracy and obsolete-Celsius independence. Add cheap conversion/invalid-input cases for zero, negative, NaN and infinite opacity; maximum-width seed and integer controls; malformed flags; null configuration; null size pointer; nonzero initial binary size; and freeing null pointers. Check allocation/error-formatting failures with a deterministic test seam where available, rather than attempting enormous allocations. The new ABI is not accepted until every wrapper's error path is nonthrowing and allocation ownership is preserved on decode failures.

**Readiness:** the V4 boundary, downstream native certificate/annual-field dispatch, current configuration/schema and default-source adoption are implemented. Broader tests are still being migrated and run against actual new-model outputs; the migration is not accepted merely because a configuration or ABI test passes. Lake/ice/cloud/latent feedback, Earth calibration and larger/extreme-domain performance remain separate scientific work.

Implementation acceptance requires explicit new-version configuration, actionable obsolete-field refusal, preserved old C layouts and behavior, verified new V4 marshaling, migrated shipped inputs, and model-appropriate output/replay tests. Scientific applicability, lake/ice coupling and accuracy limits remain governed by the research note; completing this migration would not resolve those limits by itself.
