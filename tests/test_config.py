from pathlib import Path
import ctypes
import math
from unittest import TestCase

from magic_geo.api import generate_world
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
    load_config,
)
from magic_geo.native import NativeConfigV1, NativeConfigV2, _native_config


class ConfigTests(TestCase):
    def test_seed_config_loads(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))

        self.assertEqual(config.run.seed, 424242)
        self.assertEqual(config.mesh.backend, "fibonacci_sphere")
        self.assertEqual(config.mesh.cell_count, 4096)
        self.assertLess(config.tectonics.plate_count, config.mesh.cell_count)
        self.assertEqual(config.tectonics.plate_motion_scale_deg_per_step, 2.0)
        self.assertEqual(config.tectonics.oceanic_crust_aging_ma_per_step, 5.0)
        self.assertEqual(config.tectonics.continental_crust_fraction_target, 0.34)
        self.assertEqual(config.planet.ocean_water_inventory_km3, 1_338_000_000.0)
        self.assertEqual(config.climate.subtropical_drying_strength, 0.65)
        self.assertEqual(config.climate.precipitation_scale, 0.8)
        self.assertIs(config.output.include_cells, True)

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
        self.assertEqual(NativeConfigV2.base.offset, 0)
        self.assertEqual(NativeConfigV2.compute_backend.offset, 304)
        self.assertEqual(NativeConfigV2.opencl_prefer_gpu.offset, 308)

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
