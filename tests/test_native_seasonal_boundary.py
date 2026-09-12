from __future__ import annotations

import ctypes
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import msgpack
import pytest
from pydantic import ValidationError

from magic_geo import native
from magic_geo.seasonal_config import SeasonalWorldConfig
from magic_geo.native_climate_energy_validation import NativeClimateEnergyValidationError
from tests.support.native_climate_energy import native_climate_world


SYMBOLS = (
    "magic_geo_generate_json_v4", "magic_geo_generate_geo_json_v4",
    "magic_geo_generate_msgpack_v4", "magic_geo_generate_geo_msgpack_v4",
    "magic_geo_free_string", "magic_geo_free_buffer",
)


def stub_library():
    return SimpleNamespace(**{name: Mock() for name in SYMBOLS})


def config():
    return SeasonalWorldConfig(config_version=2, mesh={"cell_count": 128},
                               tectonics={"plate_count": 8}, output={"float_precision": 8})


def identity_world():
    world = native_climate_world()
    # The permanent numerical witness omits unrelated world-envelope fields.
    world["schema_version"] = 2
    return world


def test_v4_standalone_layout_and_complete_configuration_mapping():
    data = config().model_dump()
    data.update({
        "run": {"seed": 2**64 - 1, "name": "seasonal_🌎"},
        "planet": dict(zip(data["planet"], [7012.0, 0.9, 25.0, 31.0, 0.11, 1.2, 0.8,
                                            0.6, 0.62, 1.2e9, 0.7, 3.8])),
        "mesh": {"backend": "geodesic_icosahedron", "cell_count": 258, "neighbor_count": 9},
        "tectonics": {"plate_count": 12, "continental_plate_fraction": 0.31,
                      "continental_crust_fraction_target": 0.33, "min_angular_speed": 0.04,
                      "max_angular_speed": 0.5, "boundary_smoothing_steps": 3,
                      "plate_motion_scale_deg_per_step": 3.4, "oceanic_crust_aging_ma_per_step": 4.2},
        "climate": {"months": 12, "reference_infrared_optical_depth": 0.73,
                    "precipitation_scale": 0.81, "subtropical_drying_strength": 0.41},
        "hydrology": {"river_percentile": 0.84, "preserve_geologic_depressions": False},
        "erosion": {"iterations": 2, "maturation_timestep_ma": 2.3,
                    "stream_power_coefficient": 8.3, "drainage_exponent": 0.43,
                    "slope_exponent": 1.3, "hillslope_diffusion": 0.07, "tectonic_uplift_scale": 0.67},
        "compute": {"threads": 3, "backend": "cuda", "opencl_prefer_gpu": False},
        "output": {"include_cells": False, "float_precision": 7},
    })
    marshaled = native._native_seasonal_config(SeasonalWorldConfig.model_validate(data))
    expected = [
        2**64-1, "seasonal_🌎".encode(), 7012.0, 0.9, 25.0, 31.0, 0.11, 1.2,
        0.8, 0.6, 0.62, 1.2e9, 0.7, 3.8, 258, 1, 9, 12, 0.31, 0.33, 0.04,
        0.5, 3, 3.4, 4.2, 12, 0.73, 0.81, 0.41, 0, 0.84, 2, 8.3, 0.43,
        1.3, 0.07, 0.67, 3, 0, 7, 2.3, 3, 0,
    ]
    assert len(native.NativeConfigV4._fields_) == len(expected) == 43
    assert [getattr(marshaled, name) for name, _ in native.NativeConfigV4._fields_] == expected
    assert not hasattr(marshaled, "base_temperature_c")
    assert not hasattr(marshaled, "lapse_rate_c_per_km")
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(marshaled) == 312
        assert ctypes.alignment(marshaled) == 8
        assert [getattr(native.NativeConfigV4, name).offset for name, _ in native.NativeConfigV4._fields_] == [
            0, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 116,
            120, 124, 128, 136, 144, 152, 160, 168, 176, 184, 192, 200, 208,
            216, 224, 232, 240, 248, 256, 264, 272, 280, 284, 288, 296, 304, 308,
        ]
        assert [ctypes.sizeof(cls) for cls in (native.NativeConfigV1, native.NativeConfigV2,
                                              native.NativeConfigV3)] == [304, 312, 320]


@pytest.mark.parametrize("missing", [None, *SYMBOLS])
def test_all_four_v4_symbols_required_and_typed(missing):
    lib = stub_library()
    if missing:
        delattr(lib, missing)
    with patch.object(native, "_library_path", return_value="stub"), patch.object(native.ctypes, "CDLL", return_value=lib):
        if missing:
            with pytest.raises(RuntimeError, match="seasonal V4.*rebuild"):
                native._load_seasonal_library()
        else:
            assert native._load_seasonal_library() is lib
            for name in SYMBOLS:
                function = getattr(lib, name)
                if "free_" in name:
                    assert function.argtypes == [ctypes.c_void_p]
                    assert function.restype is None
                else:
                    expected = [ctypes.POINTER(native.NativeConfigV4)]
                    if "msgpack" in name:
                        expected += [ctypes.POINTER(ctypes.c_size_t)]
                    assert function.argtypes == expected
                    assert function.restype is ctypes.c_void_p


@pytest.mark.parametrize("generator", [native.generate_seasonal_world, native.generate_seasonal_geo_world])
@pytest.mark.parametrize("serialization", ["json", "msgpack", "auto"])
def test_routes_decode_retained_budget_and_free_once(generator, serialization):
    world = identity_world()
    lib = stub_library()
    fmt = "msgpack" if serialization == "auto" else serialization
    raw = json.dumps(world).encode() if fmt == "json" else msgpack.packb(world, use_bin_type=True)
    buffer = ctypes.create_string_buffer(raw)
    pointer = ctypes.addressof(buffer)
    def result(config_pointer, *args):
        assert ctypes.cast(config_pointer, ctypes.POINTER(native.NativeConfigV4)).contents.reference_infrared_optical_depth == 1
        if args:
            ctypes.cast(args[0], ctypes.POINTER(ctypes.c_size_t)).contents.value = len(raw)
        return pointer
    route = "magic_geo_generate_" + ("geo_" if generator is native.generate_seasonal_geo_world else "") + fmt + "_v4"
    getattr(lib, route).side_effect = result
    with patch.object(native, "_load_seasonal_library", return_value=lib):
        assert generator(config(), serialization=serialization) == world
    getattr(lib, route).assert_called_once()
    for name in SYMBOLS[:4]:
        if name != route:
            getattr(lib, name).assert_not_called()
    getattr(lib, "magic_geo_free_" + ("string" if fmt == "json" else "buffer")).assert_called_once_with(pointer)


@pytest.mark.parametrize("generator", [native.generate_seasonal_world, native.generate_seasonal_geo_world])
def test_input_errors_and_old_configuration_never_load_native_library(generator):
    with patch.object(native, "_load_seasonal_library") as loader:
        for data in ({}, {"config_version": True}, {"config_version": 2, "output": {"include_cells": "false"}},
                     {"config_version": 2, "climate": {"base_temperature_c": 15}}):
            with pytest.raises(ValidationError):
                generator(data)
        with pytest.raises(ValueError, match="serialization"):
            generator(config(), serialization="yaml")
        invalid = config()
        invalid.run.seed = -1
        with pytest.raises(ValidationError):
            generator(invalid)
        loader.assert_not_called()


@pytest.mark.parametrize("fmt", ["json", "msgpack"])
@pytest.mark.parametrize("kind", ["duplicate", "nan", "infinity", "malformed", "native_error"])
def test_strict_decoding_rejects_bad_payload_and_always_frees(fmt, kind):
    lib = stub_library()
    if kind == "duplicate":
        raw = b'{"a":1,"a":2}' if fmt == "json" else b'\x82\xa1a\x01\xa1a\x02'
    elif kind == "malformed":
        raw = b'{' if fmt == "json" else b'\xc1'
    else:
        value = {"error": "solver failed"} if kind == "native_error" else {"bad": float("nan" if kind == "nan" else "inf")}
        raw = json.dumps(value).encode() if fmt == "json" else msgpack.packb(value)
    buffer = ctypes.create_string_buffer(raw)
    pointer = ctypes.addressof(buffer)
    with pytest.raises((ValueError, RuntimeError)):
        if fmt == "json":
            native._consume_json_pointer(lib, pointer, strict=True)
        else:
            native._consume_msgpack_pointer(lib, pointer, len(raw), strict=True)
    getattr(lib, "magic_geo_free_" + ("string" if fmt == "json" else "buffer")).assert_called_once_with(pointer)


@pytest.mark.parametrize(("section", "key", "value"), [
    ("climate_model", "model_type", "empirical_temperature_v1"),
    ("climate_model", "temperature_source", "unknown"),
    ("climate_model", "native_temperature_forcing_coupled", 1),
    ("climate_model", "imposed_mean_temperature", True),
    ("climate_model", "reference_infrared_optical_depth", 2),
    ("climate_model", "configured_month_count", 12.0),
    ("climate_energy_model", "model", "unknown"),
    ("climate_energy_model", "budget_schema_version", True),
    ("climate_energy_model", "ownership", "python"),
    ("climate_energy_model", "mesh_backend", 1),
    ("climate_energy_model", "mesh_backend", False),
    ("climate_energy_model", "radius_m", 7000000),
    ("planet_parameters", "gravity_g", 0.9),
])
def test_identity_and_configured_parameters_reject_stale_output(section, key, value):
    world = identity_world()
    world[section][key] = value
    with pytest.raises(RuntimeError):
        native._require_seasonal_world_identity(world, config=config())


@pytest.mark.parametrize("section", ["climate_model", "climate_energy_model", "climate_energy_balance_records",
                                    "climate_energy_forcing_intervals", "climate_energy_transport_edges", "cells"])
def test_identity_requires_complete_native_envelope(section):
    world = identity_world()
    world.pop(section)
    with pytest.raises(RuntimeError):
        native._require_seasonal_world_identity(world, config=config())


def test_empty_airless_graph_is_an_identity_valid_array():
    world = identity_world()
    world["climate_energy_transport_edges"] = []
    # This gate establishes identity only. The numerical verifier separately
    # checks whether a world's pressure/transport actually permits an empty graph.
    assert native._require_seasonal_world_identity(world, config=config()) is world


def test_explicit_cell_omission_and_canonical_budget_coverage():
    world = identity_world()
    world["cells"] = []
    with pytest.raises(RuntimeError, match="coverage"):
        native._require_seasonal_world_identity(world, config=config())
    omitted = config()
    omitted.output.include_cells = False
    assert native._require_seasonal_world_identity(world, config=omitted) is world
    world["climate_energy_balance_records"][0]["cell_id"] = True
    with pytest.raises(RuntimeError, match="canonical"):
        native._require_seasonal_world_identity(world, config=omitted)


@pytest.mark.parametrize("truncated", ["climate_energy_balance_records", "climate_energy_forcing_intervals"])
def test_generation_checks_complete_budget_before_exposing_result(truncated):
    world = identity_world()
    if truncated == "climate_energy_balance_records":
        world[truncated] = [{"cell_id": i} for i in range(128)]
    else:
        world[truncated] = [{}]
    with patch.object(native, "_load_seasonal_library", return_value=stub_library()), \
         patch.object(native, "_consume_json_pointer", return_value=world):
        with pytest.raises(NativeClimateEnergyValidationError):
            native.generate_seasonal_world(config(), serialization="json")


def test_generation_explicit_omission_validates_retained_certificate_only():
    world = identity_world()
    world["cells"] = []
    omitted = config()
    omitted.output.include_cells = False
    with patch.object(native, "_load_seasonal_library", return_value=stub_library()), \
         patch.object(native, "_consume_json_pointer", return_value=world):
        assert native.generate_seasonal_world(omitted, serialization="json") is world
        # A requested full world must fail; elapsed work never weakens scope.
        with pytest.raises(RuntimeError, match="coverage"):
            native.generate_seasonal_world(config(), serialization="json")


@pytest.mark.parametrize(("generic", "seasonal"), [
    (native.generate_world, "generate_seasonal_world"),
    (native.generate_geo_world, "generate_seasonal_geo_world"),
])
def test_generic_native_entrypoints_never_drop_explicit_document_version(generic, seasonal):
    data = config().model_dump()
    with patch.object(native, seasonal, return_value={"selected": "seasonal"}) as selected, \
         patch.object(native, "_load_library", side_effect=AssertionError("legacy library loaded")):
        assert generic(data, serialization="json") == {"selected": "seasonal"}
    selected.assert_called_once_with(data, serialization="json")
    with patch.object(native, "_load_library", side_effect=AssertionError("legacy library loaded")):
        for version in (1, 3, True, "2"):
            with pytest.raises(ValidationError):
                generic({"config_version": version})
