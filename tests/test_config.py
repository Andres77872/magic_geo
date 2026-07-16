from pathlib import Path
import ctypes
import math
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import magic_geo.native as native_module
import yaml
from magic_geo.api import generate_geo_world, generate_world
from magic_geo.config import (
    MAX_ANGULAR_SPEED,
    MAX_ATMOSPHERE_PRESSURE_BAR,
    MAX_COMPUTE_THREADS,
    MAX_DAY_LENGTH_HOURS,
    MAX_GEOLOGICAL_AGE_GA,
    MAX_GREENHOUSE_FACTOR,
    MAX_INTERNAL_HEAT,
    MAX_PLANET_RADIUS_KM,
    MAX_SEED,
    MAX_STELLAR_LUMINOSITY,
    ConfigError,
    WorldConfig,
    apply_config_overrides,
    config_schema,
    create_config,
    dump_config_yaml,
    list_config_profiles,
    load_config,
    parse_config_overrides,
    parse_config_yaml,
    write_config,
)
from magic_geo.native import (
    NativeConfigV1,
    NativeConfigV2,
    NativeConfigV3,
    _native_config,
)


class ConfigTests(TestCase):
    def test_example_seed_catalog_is_complete_and_self_contained(self) -> None:
        seed_directory = Path("configs/seeds")
        expected_filenames = {
            "continental_realm.yaml",
            "cryogenic_slushball.yaml",
            "glasswind_desert.yaml",
            "ironroot_super_earth.yaml",
            "oldstone_stagnant.yaml",
            "pelagic_archipelago.yaml",
            "solstice_extreme.yaml",
            "verdant_hothouse.yaml",
            "young_volcanic.yaml",
        }
        paths = sorted(seed_directory.glob("*.yaml"))

        self.assertEqual({path.name for path in paths}, expected_filenames)
        expected_sections = set(WorldConfig.model_fields)
        configs = []
        for path in paths:
            with self.subTest(path=path):
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                self.assertIsInstance(raw, dict)
                self.assertEqual(set(raw), expected_sections)
                for section_name, section_field in WorldConfig.model_fields.items():
                    section_model = section_field.annotation
                    self.assertEqual(
                        set(raw[section_name]),
                        set(section_model.model_fields),
                    )

                config = load_config(path)
                self.assertEqual(config.run.name, path.stem)
                self.assertEqual(config.compute.backend, "cpu")
                self.assertEqual(config.compute.threads, 1)
                self.assertIs(config.output.include_cells, True)
                configs.append(config)

        self.assertEqual(len({config.run.name for config in configs}), len(configs))
        self.assertEqual(len({config.run.seed for config in configs}), len(configs))

    def test_example_seed_catalog_spans_distinct_world_regimes(self) -> None:
        configs = {
            path.stem: load_config(path)
            for path in Path("configs/seeds").glob("*.yaml")
        }

        self.assertEqual(
            {config.mesh.backend for config in configs.values()},
            {"fibonacci_sphere", "geodesic_icosahedron"},
        )
        self.assertEqual(configs["glasswind_desert"].planet.ocean_water_inventory_km3, 0.0)
        self.assertLess(configs["glasswind_desert"].climate.precipitation_scale, 0.15)
        self.assertGreater(
            configs["pelagic_archipelago"].planet.ocean_water_inventory_km3,
            2_000_000_000.0,
        )
        self.assertLess(configs["cryogenic_slushball"].planet.stellar_luminosity, 0.60)
        self.assertLessEqual(configs["cryogenic_slushball"].climate.base_temperature_c, -10.0)
        self.assertGreater(configs["verdant_hothouse"].climate.precipitation_scale, 1.5)
        self.assertGreater(configs["verdant_hothouse"].planet.greenhouse_factor, 1.4)
        self.assertIs(configs["verdant_hothouse"].hydrology.preserve_geologic_depressions, False)
        self.assertTrue(
            any(
                config.hydrology.preserve_geologic_depressions
                for config in configs.values()
            )
        )
        self.assertGreaterEqual(configs["solstice_extreme"].planet.axial_tilt_deg, 70.0)
        self.assertGreaterEqual(configs["ironroot_super_earth"].planet.gravity_g, 1.5)
        self.assertGreaterEqual(configs["ironroot_super_earth"].planet.radius_km, 9_000.0)
        self.assertEqual(
            configs["ironroot_super_earth"].planet.ocean_water_inventory_km3,
            3_020_000_000.0,
        )
        self.assertLessEqual(configs["young_volcanic"].planet.geological_age_ga, 1.0)
        self.assertGreaterEqual(configs["young_volcanic"].planet.internal_heat, 2.0)
        self.assertEqual(configs["young_volcanic"].erosion.iterations, 6)
        self.assertEqual(configs["glasswind_desert"].tectonics.plate_count, 8)
        self.assertEqual(
            configs["solstice_extreme"].planet.ocean_water_inventory_km3,
            1_100_000_000.0,
        )
        self.assertEqual(
            configs["oldstone_stagnant"].planet.ocean_water_inventory_km3,
            430_000_000.0,
        )
        self.assertEqual(configs["oldstone_stagnant"].tectonics.max_angular_speed, 0.0)
        self.assertEqual(
            configs["oldstone_stagnant"].tectonics.plate_motion_scale_deg_per_step,
            0.0,
        )
        self.assertGreater(
            len({config.planet.day_length_hours for config in configs.values()}),
            4,
        )
        self.assertGreaterEqual(
            max(config.planet.orbital_eccentricity for config in configs.values()),
            0.10,
        )
        self.assertEqual(
            {config.mesh.neighbor_count for config in configs.values()},
            {7, 8},
        )
        self.assertLessEqual(
            min(
                config.tectonics.continental_crust_fraction_target
                for config in configs.values()
            ),
            0.20,
        )
        self.assertGreaterEqual(
            max(
                config.tectonics.continental_crust_fraction_target
                for config in configs.values()
            ),
            0.65,
        )
        self.assertLessEqual(
            min(config.tectonics.boundary_smoothing_steps for config in configs.values()),
            2,
        )
        self.assertGreaterEqual(
            max(config.tectonics.boundary_smoothing_steps for config in configs.values()),
            12,
        )
        self.assertEqual(
            min(
                config.tectonics.oceanic_crust_aging_ma_per_step
                for config in configs.values()
            ),
            0.0,
        )
        self.assertGreaterEqual(
            max(config.climate.lapse_rate_c_per_km for config in configs.values())
            - min(config.climate.lapse_rate_c_per_km for config in configs.values()),
            2.0,
        )
        self.assertLessEqual(
            min(config.hydrology.river_percentile for config in configs.values()),
            0.86,
        )
        self.assertGreaterEqual(
            max(config.hydrology.river_percentile for config in configs.values()),
            0.97,
        )
        self.assertEqual(
            min(config.erosion.tectonic_uplift_scale for config in configs.values()),
            0.0,
        )
        self.assertGreaterEqual(
            max(config.erosion.tectonic_uplift_scale for config in configs.values()),
            2.0,
        )

    def test_example_seed_catalog_generates_downscaled_geo_smoke(self) -> None:
        for path in sorted(Path("configs/seeds").glob("*.yaml")):
            with self.subTest(path=path):
                config = load_config(path)
                data = config.model_dump(mode="python")
                data["mesh"]["cell_count"] = 128
                data["tectonics"]["plate_count"] = min(
                    data["tectonics"]["plate_count"],
                    12,
                )
                smoke_config = type(config).model_validate(data)

                world = generate_geo_world(smoke_config)

                self.assertGreaterEqual(world["summary"]["cell_count"], 128)
                self.assertEqual(
                    len(world["cells"]),
                    world["summary"]["cell_count"],
                )

    def test_native_library_requires_the_current_v3_transport_abi(self) -> None:
        class FakeFunction:
            argtypes: list | None = None
            restype: object | None = None

        class IncompleteLibrary:
            magic_geo_backend_info_json = FakeFunction()
            magic_geo_generate_json_v3 = FakeFunction()
            magic_geo_free_string = FakeFunction()

        incomplete = IncompleteLibrary()
        with (
            patch.object(
                native_module, "_library_path", return_value=Path("incomplete.so")
            ),
            patch.object(native_module.ctypes, "CDLL", return_value=incomplete),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "does not expose the current V3 JSON and MessagePack ABI"
            ):
                native_module._load_library()

    def test_seed_config_loads(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))

        self.assertEqual(config.run.seed, 424242)
        self.assertEqual(config.mesh.backend, "fibonacci_sphere")
        self.assertEqual(config.mesh.cell_count, 4096)
        self.assertLess(config.tectonics.plate_count, config.mesh.cell_count)
        self.assertEqual(config.tectonics.plate_motion_scale_deg_per_step, 4.0)
        self.assertEqual(config.tectonics.oceanic_crust_aging_ma_per_step, 5.0)
        self.assertEqual(config.erosion.maturation_timestep_ma, 5.0)
        self.assertEqual(config.tectonics.continental_crust_fraction_target, 0.34)
        self.assertEqual(config.planet.ocean_water_inventory_km3, 1_338_000_000.0)
        self.assertEqual(config.climate.subtropical_drying_strength, 0.65)
        self.assertEqual(config.climate.precipitation_scale, 0.8)
        self.assertIs(config.output.include_cells, True)

    def test_builtin_profiles_are_explicit_and_reference_seed_is_earthlike(self) -> None:
        self.assertEqual(
            list_config_profiles(),
            ("default", "earthlike", "smoke"),
        )

        default = create_config("default")
        earthlike = create_config("earthlike")
        smoke = create_config("smoke")

        self.assertEqual(default.tectonics.plate_motion_scale_deg_per_step, 2.0)
        self.assertEqual(default.climate.precipitation_scale, 1.0)
        self.assertEqual(earthlike.tectonics.plate_motion_scale_deg_per_step, 4.0)
        self.assertEqual(earthlike.climate.precipitation_scale, 0.8)
        self.assertEqual(load_config(Path("configs/earthlike_seed.yaml")), earthlike)

        self.assertEqual(smoke.run.name, "smoke")
        self.assertEqual(smoke.mesh.cell_count, 128)
        self.assertEqual(smoke.tectonics.plate_count, 8)
        self.assertEqual(smoke.erosion.iterations, 1)
        self.assertEqual(smoke.compute.backend, "cpu")
        self.assertEqual(smoke.compute.threads, 1)

        with self.assertRaisesRegex(ConfigError, "unknown configuration profile"):
            create_config("unknown")

    def test_yaml_dump_is_stable_and_round_trips_every_profile(self) -> None:
        expected_section_order = list(WorldConfig.model_fields)
        for profile in list_config_profiles():
            with self.subTest(profile=profile):
                config = create_config(profile)
                text = dump_config_yaml(config)
                parsed = parse_config_yaml(text, source=f"{profile}.yaml")

                self.assertEqual(parsed, config)
                self.assertEqual(dump_config_yaml(parsed), text)
                self.assertTrue(text.endswith("\n"))
                self.assertEqual(
                    list(yaml.safe_load(text)),
                    expected_section_order,
                )

        self.assertEqual(parse_config_yaml("", source="empty.yaml"), create_config())

    def test_yaml_errors_are_source_aware_and_duplicate_keys_are_rejected(self) -> None:
        duplicate = "run:\n  seed: 1\n  seed: 2\n"
        with self.assertRaises(ConfigError) as duplicate_context:
            parse_config_yaml(duplicate, source="duplicate.yaml")
        duplicate_error = duplicate_context.exception
        self.assertEqual(duplicate_error.source, "duplicate.yaml")
        self.assertEqual(duplicate_error.line, 3)
        self.assertIn("duplicate key 'seed'", str(duplicate_error))

        with self.assertRaises(ConfigError) as malformed_context:
            parse_config_yaml("run: [\n", source="malformed.yaml")
        malformed_error = malformed_context.exception
        self.assertEqual(malformed_error.source, "malformed.yaml")
        self.assertIsNotNone(malformed_error.line)
        self.assertIn("invalid YAML", str(malformed_error))

        with self.assertRaises(ConfigError) as root_context:
            parse_config_yaml("- not\n- a\n- mapping\n", source="list.yaml")
        self.assertEqual(root_context.exception.issues[0]["path"], "<root>")

        with self.assertRaises(ConfigError) as validation_context:
            parse_config_yaml(
                "planet:\n  radius_km: 10\n",
                source="invalid.yaml",
            )
        validation_error = validation_context.exception
        self.assertEqual(validation_error.source, "invalid.yaml")
        self.assertEqual(validation_error.issues[0]["path"], "planet.radius_km")
        self.assertIn("planet.radius_km", validation_error.to_dict()["message"])

        deeply_nested = "[" * 80 + "0" + "]" * 80
        with self.assertRaisesRegex(ConfigError, "nesting exceeds"):
            parse_config_yaml(deeply_nested, source="deep.yaml")

        alias_document = "value: &item 1\nrefs: [" + ",".join(["*item"] * 65) + "]\n"
        with self.assertRaisesRegex(ConfigError, "alias limit"):
            parse_config_yaml(alias_document, source="aliases.yaml")

        for document in (
            "run:\n  seed: " + "1" * 4301 + "\n",
            "run:\n  name: 2020-02-30\n",
            "\ud800",
        ):
            with self.subTest(document=document[:40]):
                with self.assertRaises(ConfigError):
                    parse_config_yaml(document, source="construction.yaml")

        for document in (
            'run:\n  name: "bad\\0name"\n',
            'run:\n  name: "\\uD800"\n',
            'run:\n  name: ""\n',
            f"run:\n  name: {'x' * 257}\n",
        ):
            with self.subTest(name_document=document[:40]):
                with self.assertRaises(ConfigError):
                    parse_config_yaml(document, source="name.yaml")

    def test_dotted_overrides_are_validated_and_do_not_mutate_input(self) -> None:
        base = create_config("earthlike")
        snapshot = base.model_dump(mode="python")
        changed = apply_config_overrides(
            base,
            {
                "run.name": "custom",
                "mesh.cell_count": "256",
                "tectonics.plate_count": 12,
                "climate.precipitation_scale": 0.5,
            },
            source="request overrides",
        )

        self.assertEqual(base.model_dump(mode="python"), snapshot)
        self.assertEqual(changed.run.name, "custom")
        self.assertEqual(changed.mesh.cell_count, 256)
        self.assertEqual(changed.tectonics.plate_count, 12)
        self.assertEqual(changed.climate.precipitation_scale, 0.5)

        via_factory = create_config(
            "smoke",
            {"run.seed": 99, "erosion.iterations": 0},
        )
        self.assertEqual(via_factory.run.seed, 99)
        self.assertEqual(via_factory.erosion.iterations, 0)

        for invalid_overrides in (
            {"mesh.unknown": 1},
            {"mesh": {}},
            {"mesh.cell_count": 64},
            {"mesh.cell_count": 128, "tectonics.plate_count": 128},
        ):
            with self.subTest(overrides=invalid_overrides):
                with self.assertRaises(ConfigError):
                    apply_config_overrides(base, invalid_overrides)

    def test_override_assignment_and_atomic_write_helpers(self) -> None:
        overrides = parse_config_overrides(
            [
                "mesh.cell_count=256",
                "hydrology.preserve_geologic_depressions=false",
                "run.name=helper demo",
            ]
        )
        config = create_config("smoke", overrides)
        self.assertEqual(config.mesh.cell_count, 256)
        self.assertFalse(config.hydrology.preserve_geologic_depressions)
        self.assertEqual(config.run.name, "helper demo")

        with self.assertRaisesRegex(ConfigError, "duplicate configuration override"):
            parse_config_overrides(["mesh.cell_count=128", "mesh.cell_count=256"])
        with self.assertRaisesRegex(ConfigError, "section.field=value"):
            parse_config_overrides(["mesh.cell_count"])

        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "nested" / "world.yaml"
            write_config(target, config)
            self.assertEqual(load_config(target), config)
            self.assertEqual(list(target.parent.glob(".*.tmp")), [])
            with self.assertRaises(FileExistsError):
                write_config(target, create_config("default"))
            replacement = create_config("earthlike")
            write_config(target, replacement, force=True)
            self.assertEqual(load_config(target), replacement)

    def test_config_schema_describes_every_section_field_and_profile(self) -> None:
        schema = config_schema()
        self.assertTrue(schema["description"])
        described_field_count = 0

        for section_name, section_schema in schema["properties"].items():
            with self.subTest(section=section_name):
                self.assertTrue(section_schema["description"])
                reference = section_schema.get("$ref")
                if reference is None:
                    reference = section_schema["allOf"][0]["$ref"]
                definition = schema["$defs"][reference.rsplit("/", 1)[-1]]
                self.assertTrue(definition["description"])
                for field_name, field_schema in definition["properties"].items():
                    with self.subTest(section=section_name, field=field_name):
                        self.assertTrue(field_schema["description"])
                        described_field_count += 1

        self.assertEqual(described_field_count, 44)
        metadata = schema["x-magic-geo"]
        self.assertEqual(metadata["section_order"], list(WorldConfig.model_fields))
        self.assertEqual(
            [profile["name"] for profile in metadata["profiles"]],
            list(list_config_profiles()),
        )
        for profile in metadata["profiles"]:
            self.assertTrue(profile["description"])
            self.assertEqual(
                WorldConfig.model_validate(profile["values"]),
                create_config(profile["name"]),
            )

    def test_load_preserves_io_error_contract(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing.yaml"
            with self.assertRaises(FileNotFoundError):
                load_config(missing)

    def test_climate_month_count_is_twelve(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["climate"]["months"] = 6

        with self.assertRaises(ValueError):
            type(config).model_validate(data)

    def test_continental_crust_fraction_target_is_bounded(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["tectonics"]["continental_crust_fraction_target"] = 0.96

        with self.assertRaises(ValueError):
            type(config).model_validate(data)

    def test_maturation_timestep_is_positive_and_refinement_only(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        for invalid_timestep in (0.0, 5.000001):
            data = config.model_dump(mode="python")
            data["erosion"]["maturation_timestep_ma"] = invalid_timestep
            with self.subTest(invalid_timestep=invalid_timestep):
                with self.assertRaises(ValueError):
                    type(config).model_validate(data)

    def test_ocean_water_inventory_is_bounded(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["planet"]["ocean_water_inventory_km3"] = -1.0

        with self.assertRaises(ValueError):
            type(config).model_validate(data)

    def test_compute_backend_is_marshaled_to_native_abi(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="json")
        data["compute"]["backend"] = "opencl"
        data["compute"]["opencl_prefer_gpu"] = False

        native = _native_config(data)

        self.assertEqual(native.compute_backend, 2)
        self.assertEqual(native.opencl_prefer_gpu, 0)
        self.assertEqual(ctypes.sizeof(NativeConfigV1), 304)
        self.assertEqual(ctypes.sizeof(NativeConfigV2), 312)
        self.assertEqual(ctypes.sizeof(NativeConfigV3), 320)
        self.assertEqual(NativeConfigV2.base.offset, 0)
        self.assertEqual(NativeConfigV2.compute_backend.offset, 304)
        self.assertEqual(NativeConfigV2.opencl_prefer_gpu.offset, 308)
        self.assertEqual(NativeConfigV3.base.offset, 0)
        self.assertEqual(NativeConfigV3.maturation_timestep_ma.offset, 312)
        self.assertEqual(native.maturation_timestep_ma, 5.0)

        data["compute"]["backend"] = "cuda"
        cuda_native = _native_config(data)
        self.assertEqual(cuda_native.compute_backend, 3)

        expected_v1_offsets = {
            "seed": 0,
            "name": 8,
            "radius_km": 16,
            "gravity_g": 24,
            "day_length_hours": 32,
            "axial_tilt_deg": 40,
            "orbital_eccentricity": 48,
            "stellar_luminosity": 56,
            "atmosphere_pressure_bar": 64,
            "greenhouse_factor": 72,
            "ocean_fraction_target": 80,
            "ocean_water_inventory_km3": 88,
            "internal_heat": 96,
            "geological_age_ga": 104,
            "cell_count": 112,
            "mesh_backend": 116,
            "neighbor_count": 120,
            "plate_count": 124,
            "continental_plate_fraction": 128,
            "continental_crust_fraction_target": 136,
            "min_angular_speed": 144,
            "max_angular_speed": 152,
            "boundary_smoothing_steps": 160,
            "plate_motion_scale_deg_per_step": 168,
            "oceanic_crust_aging_ma_per_step": 176,
            "months": 184,
            "lapse_rate_c_per_km": 192,
            "base_temperature_c": 200,
            "precipitation_scale": 208,
            "subtropical_drying_strength": 216,
            "preserve_geologic_depressions": 224,
            "river_percentile": 232,
            "erosion_iterations": 240,
            "stream_power_coefficient": 248,
            "drainage_exponent": 256,
            "slope_exponent": 264,
            "hillslope_diffusion": 272,
            "tectonic_uplift_scale": 280,
            "threads": 288,
            "include_cells": 292,
            "float_precision": 296,
        }
        self.assertEqual(
            {
                name: getattr(NativeConfigV1, name).offset
                for name, _field_type in NativeConfigV1._fields_
            },
            expected_v1_offsets,
        )

    def test_non_finite_physical_parameter_is_rejected(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["planet"]["radius_km"] = math.inf

        with self.assertRaises(ValueError):
            type(config).model_validate(data)

    def test_supported_numeric_extrema_and_integer_abi_bounds(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["run"]["seed"] = MAX_SEED
        data["planet"].update(
            {
                "radius_km": MAX_PLANET_RADIUS_KM,
                "day_length_hours": MAX_DAY_LENGTH_HOURS,
                "stellar_luminosity": MAX_STELLAR_LUMINOSITY,
                "atmosphere_pressure_bar": MAX_ATMOSPHERE_PRESSURE_BAR,
                "greenhouse_factor": MAX_GREENHOUSE_FACTOR,
                "internal_heat": MAX_INTERNAL_HEAT,
                "geological_age_ga": MAX_GEOLOGICAL_AGE_GA,
            }
        )
        data["tectonics"]["min_angular_speed"] = MAX_ANGULAR_SPEED
        data["tectonics"]["max_angular_speed"] = MAX_ANGULAR_SPEED
        data["compute"]["threads"] = MAX_COMPUTE_THREADS

        bounded = type(config).model_validate(data)
        native = _native_config(bounded.model_dump(mode="json"))
        self.assertEqual(native.base.seed, MAX_SEED)
        self.assertEqual(native.base.radius_km, MAX_PLANET_RADIUS_KM)
        self.assertEqual(native.base.threads, MAX_COMPUTE_THREADS)

        generation_data = bounded.model_dump(mode="python")
        generation_data["mesh"]["cell_count"] = 128
        generation_data["erosion"]["iterations"] = 0
        generation_data["compute"]["backend"] = "cpu"
        generation_data["compute"]["threads"] = 1
        world = generate_world(type(config).model_validate(generation_data))
        pending: list[object] = [world]
        finite_float_count = 0
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
            elif isinstance(value, float):
                self.assertTrue(math.isfinite(value))
                finite_float_count += 1
        self.assertGreater(finite_float_count, 0)

        invalid_values = (
            (("run", "seed"), -1),
            (("run", "seed"), MAX_SEED + 1),
            (("planet", "radius_km"), MAX_PLANET_RADIUS_KM + 1.0),
            (("planet", "day_length_hours"), MAX_DAY_LENGTH_HOURS + 1.0),
            (("planet", "stellar_luminosity"), MAX_STELLAR_LUMINOSITY + 1.0),
            (
                ("planet", "atmosphere_pressure_bar"),
                MAX_ATMOSPHERE_PRESSURE_BAR + 1.0,
            ),
            (("planet", "greenhouse_factor"), MAX_GREENHOUSE_FACTOR + 1.0),
            (("planet", "internal_heat"), MAX_INTERNAL_HEAT + 1.0),
            (("planet", "geological_age_ga"), MAX_GEOLOGICAL_AGE_GA + 1.0),
            (("tectonics", "max_angular_speed"), MAX_ANGULAR_SPEED + 1.0),
            (("compute", "threads"), MAX_COMPUTE_THREADS + 1),
        )
        for path, value in invalid_values:
            with self.subTest(path=path, value=value):
                candidate = config.model_dump(mode="python")
                candidate[path[0]][path[1]] = value
                with self.assertRaises(ValueError):
                    type(config).model_validate(candidate)
