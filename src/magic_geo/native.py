from __future__ import annotations

import ctypes
import json
import math
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import msgpack

from .planet_parameters import PLANET_PARAMETER_DEFAULTS
from .serialization import CURRENT_WORLD_SCHEMA_VERSION, retired_world_schema_fields
from .seasonal_config import SeasonalWorldConfig


MESH_BACKEND_IDS = {
    "fibonacci_sphere": 0,
    "geodesic_icosahedron": 1,
}

COMPUTE_BACKEND_IDS = {
    "auto": 0,
    "cpu": 1,
    "opencl": 2,
    "cuda": 3,
}


def _native_library_names() -> tuple[str]:
    """Return only the shared-library filename native to this host."""

    if sys.platform == "win32":
        return ("magic_geo_native.dll",)
    if sys.platform == "darwin":
        return ("libmagic_geo_native.dylib",)
    return ("libmagic_geo_native.so",)


def _reject_msgpack_extension(code: int, data: bytes) -> Any:
    del data
    raise ValueError(
        f"MessagePack extension type {code} is not valid in a native world"
    )


class NativeConfigV1(ctypes.Structure):
    _fields_ = [
        ("seed", ctypes.c_uint64),
        ("name", ctypes.c_char_p),
        ("radius_km", ctypes.c_double),
        ("gravity_g", ctypes.c_double),
        ("day_length_hours", ctypes.c_double),
        ("axial_tilt_deg", ctypes.c_double),
        ("orbital_eccentricity", ctypes.c_double),
        ("stellar_luminosity", ctypes.c_double),
        ("atmosphere_pressure_bar", ctypes.c_double),
        ("greenhouse_factor", ctypes.c_double),
        ("ocean_fraction_target", ctypes.c_double),
        ("ocean_water_inventory_km3", ctypes.c_double),
        ("internal_heat", ctypes.c_double),
        ("geological_age_ga", ctypes.c_double),
        ("cell_count", ctypes.c_int),
        ("mesh_backend", ctypes.c_int),
        ("neighbor_count", ctypes.c_int),
        ("plate_count", ctypes.c_int),
        ("continental_plate_fraction", ctypes.c_double),
        ("continental_crust_fraction_target", ctypes.c_double),
        ("min_angular_speed", ctypes.c_double),
        ("max_angular_speed", ctypes.c_double),
        ("boundary_smoothing_steps", ctypes.c_int),
        ("plate_motion_scale_deg_per_step", ctypes.c_double),
        ("oceanic_crust_aging_ma_per_step", ctypes.c_double),
        ("months", ctypes.c_int),
        ("lapse_rate_c_per_km", ctypes.c_double),
        ("base_temperature_c", ctypes.c_double),
        ("precipitation_scale", ctypes.c_double),
        ("subtropical_drying_strength", ctypes.c_double),
        ("preserve_geologic_depressions", ctypes.c_int),
        ("river_percentile", ctypes.c_double),
        ("erosion_iterations", ctypes.c_int),
        ("stream_power_coefficient", ctypes.c_double),
        ("drainage_exponent", ctypes.c_double),
        ("slope_exponent", ctypes.c_double),
        ("hillslope_diffusion", ctypes.c_double),
        ("tectonic_uplift_scale", ctypes.c_double),
        ("threads", ctypes.c_int),
        ("include_cells", ctypes.c_int),
        ("float_precision", ctypes.c_int),
    ]


class NativeConfigV2(ctypes.Structure):
    _anonymous_ = ("base",)
    _fields_ = [
        ("base", NativeConfigV1),
        ("compute_backend", ctypes.c_int),
        ("opencl_prefer_gpu", ctypes.c_int),
    ]


class NativeConfigV3(ctypes.Structure):
    _anonymous_ = ("base",)
    _fields_ = [
        ("base", NativeConfigV2),
        ("maturation_timestep_ma", ctypes.c_double),
    ]


class NativeConfigV4(ctypes.Structure):
    """Standalone seasonal-only C ABI; never reinterpret a V1–V3 prefix."""

    _fields_ = [
        ("seed", ctypes.c_uint64),
        ("name", ctypes.c_char_p),
        ("radius_km", ctypes.c_double),
        ("gravity_g", ctypes.c_double),
        ("day_length_hours", ctypes.c_double),
        ("axial_tilt_deg", ctypes.c_double),
        ("orbital_eccentricity", ctypes.c_double),
        ("stellar_luminosity", ctypes.c_double),
        ("atmosphere_pressure_bar", ctypes.c_double),
        ("greenhouse_factor", ctypes.c_double),
        ("ocean_fraction_target", ctypes.c_double),
        ("ocean_water_inventory_km3", ctypes.c_double),
        ("internal_heat", ctypes.c_double),
        ("geological_age_ga", ctypes.c_double),
        ("cell_count", ctypes.c_int32),
        ("mesh_backend", ctypes.c_int32),
        ("neighbor_count", ctypes.c_int32),
        ("plate_count", ctypes.c_int32),
        ("continental_plate_fraction", ctypes.c_double),
        ("continental_crust_fraction_target", ctypes.c_double),
        ("min_angular_speed", ctypes.c_double),
        ("max_angular_speed", ctypes.c_double),
        ("boundary_smoothing_steps", ctypes.c_int32),
        ("plate_motion_scale_deg_per_step", ctypes.c_double),
        ("oceanic_crust_aging_ma_per_step", ctypes.c_double),
        ("months", ctypes.c_int32),
        ("reference_infrared_optical_depth", ctypes.c_double),
        ("precipitation_scale", ctypes.c_double),
        ("subtropical_drying_strength", ctypes.c_double),
        ("preserve_geologic_depressions", ctypes.c_int32),
        ("river_percentile", ctypes.c_double),
        ("erosion_iterations", ctypes.c_int32),
        ("stream_power_coefficient", ctypes.c_double),
        ("drainage_exponent", ctypes.c_double),
        ("slope_exponent", ctypes.c_double),
        ("hillslope_diffusion", ctypes.c_double),
        ("tectonic_uplift_scale", ctypes.c_double),
        ("threads", ctypes.c_int32),
        ("include_cells", ctypes.c_int32),
        ("float_precision", ctypes.c_int32),
        ("maturation_timestep_ma", ctypes.c_double),
        ("compute_backend", ctypes.c_int32),
        ("opencl_prefer_gpu", ctypes.c_int32),
    ]


def _library_path() -> Path:
    override = os.environ.get("MAGIC_GEO_NATIVE_LIBRARY")
    if override:
        candidate = Path(override).expanduser().resolve()
        if not candidate.is_file():
            raise RuntimeError(
                f"MAGIC_GEO_NATIVE_LIBRARY does not name a file: {candidate}"
            )
        return candidate
    package_dir = Path(__file__).resolve().parent
    for suffix in _native_library_names():
        candidate = package_dir / suffix
        if candidate.exists():
            return candidate
    raise RuntimeError(
        "native library was not found. Build it with: "
        "cmake -S . -B build && cmake --build build"
    )


def _load_library() -> ctypes.CDLL:
    lib = ctypes.CDLL(str(_library_path()))
    try:
        backend_info = lib.magic_geo_backend_info_json
        generate_v3 = lib.magic_geo_generate_json_v3
        geo_generate_v3 = lib.magic_geo_generate_geo_json_v3
        msgpack_generate_v3 = lib.magic_geo_generate_msgpack_v3
        geo_msgpack_generate_v3 = lib.magic_geo_generate_geo_msgpack_v3
        free_string = lib.magic_geo_free_string
        free_buffer = lib.magic_geo_free_buffer
    except AttributeError as exc:
        raise RuntimeError(
            "native library does not expose the current V3 JSON and MessagePack ABI; "
            "rebuild magic_geo_native from the current source tree"
        ) from exc

    backend_info.argtypes = []
    backend_info.restype = ctypes.c_void_p
    generate_v3.argtypes = [ctypes.POINTER(NativeConfigV3)]
    generate_v3.restype = ctypes.c_void_p
    geo_generate_v3.argtypes = [ctypes.POINTER(NativeConfigV3)]
    geo_generate_v3.restype = ctypes.c_void_p
    msgpack_generate_v3.argtypes = [
        ctypes.POINTER(NativeConfigV3),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    msgpack_generate_v3.restype = ctypes.c_void_p
    geo_msgpack_generate_v3.argtypes = [
        ctypes.POINTER(NativeConfigV3),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    geo_msgpack_generate_v3.restype = ctypes.c_void_p
    free_string.argtypes = [ctypes.c_void_p]
    free_string.restype = None
    free_buffer.argtypes = [ctypes.c_void_p]
    free_buffer.restype = None
    return lib


def _load_seasonal_library() -> ctypes.CDLL:
    """Require all four V4 routes; an old library must never cause fallback."""
    lib = ctypes.CDLL(str(_library_path()))
    symbols = (
        "magic_geo_generate_json_v4", "magic_geo_generate_geo_json_v4",
        "magic_geo_generate_msgpack_v4", "magic_geo_generate_geo_msgpack_v4",
        "magic_geo_free_string", "magic_geo_free_buffer",
    )
    try:
        functions = [getattr(lib, name) for name in symbols]
    except AttributeError as exc:
        raise RuntimeError(
            "native library does not expose the seasonal V4 JSON and MessagePack ABI; "
            "rebuild magic_geo_native from the current source tree"
        ) from exc
    for name, function in zip(symbols, functions):
        if name.startswith("magic_geo_free_"):
            function.argtypes = [ctypes.c_void_p]
            function.restype = None
        else:
            function.argtypes = [ctypes.POINTER(NativeConfigV4)]
            if "msgpack" in name:
                function.argtypes.append(ctypes.POINTER(ctypes.c_size_t))
            function.restype = ctypes.c_void_p
    return lib


def _unique_native_object(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if not isinstance(key, str):
            raise ValueError("native object keys must be strings")
        if key in result:
            raise ValueError(f"duplicate native object key {key!r}")
        result[key] = value
    return result


def _require_finite_native_tree(payload: Any) -> None:
    pending = [payload]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("native world contains a nonfinite number")


def _consume_json_pointer(
    lib: ctypes.CDLL, ptr: int, *, strict: bool = False,
) -> dict[str, Any]:
    if not ptr:
        raise RuntimeError("native library returned a null JSON pointer")
    try:
        raw = ctypes.cast(ptr, ctypes.c_char_p).value
        if raw is None:
            raise RuntimeError("native library returned an empty JSON pointer")
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_native_object if strict else None,
        )
        if strict:
            _require_finite_native_tree(payload)
    finally:
        lib.magic_geo_free_string(ptr)
    if isinstance(payload, dict) and "error" in payload:
        raise RuntimeError(str(payload["error"]))
    return payload


def _consume_msgpack_pointer(
    lib: ctypes.CDLL,
    ptr: int,
    size: int,
    *,
    strict: bool = False,
) -> dict[str, Any]:
    free_buffer = lib.magic_geo_free_buffer
    if not ptr:
        raise RuntimeError("native library returned a null MessagePack pointer")
    if size <= 0:
        free_buffer(ptr)
        raise RuntimeError("native library returned an empty MessagePack buffer")

    view: memoryview | None = None
    try:
        native_array = (ctypes.c_ubyte * size).from_address(int(ptr))
        view = memoryview(native_array).cast("B")
        try:
            payload = msgpack.unpackb(
                view,
                raw=False,
                use_list=True,
                strict_map_key=True,
                ext_hook=_reject_msgpack_extension,
                max_str_len=size,
                max_bin_len=0,
                max_array_len=size,
                max_map_len=size,
                max_ext_len=0,
                object_pairs_hook=_unique_native_object if strict else None,
            )
            if strict:
                _require_finite_native_tree(payload)
        except (
            msgpack.ExtraData,
            msgpack.FormatError,
            msgpack.StackError,
            UnicodeDecodeError,
            ValueError,
        ) as exc:
            raise RuntimeError(
                f"native library returned invalid MessagePack: {exc}"
            ) from exc
    finally:
        if view is not None:
            view.release()
        free_buffer(ptr)
    if not isinstance(payload, dict):
        raise RuntimeError("native MessagePack root is not an object")
    if "error" in payload:
        raise RuntimeError(str(payload["error"]))
    return payload


def _require_current_world_schema(payload: dict[str, Any]) -> dict[str, Any]:
    actual = payload.get("schema_version") if isinstance(payload, dict) else None
    if type(actual) is not int or actual != CURRENT_WORLD_SCHEMA_VERSION:
        raise RuntimeError(
            "native library returned unsupported world schema_version "
            f"{actual!r}; expected {CURRENT_WORLD_SCHEMA_VERSION}; rebuild "
            "magic_geo_native from the current source tree"
        )
    retired_fields = retired_world_schema_fields(payload)
    if retired_fields:
        raise RuntimeError(
            "native library returned retired fields in a schema-2 world: "
            + ", ".join(retired_fields)
        )
    parameters = payload.get("planet_parameters")
    if not isinstance(parameters, dict):
        raise RuntimeError(
            "native library returned schema 2 without explicit planet_parameters"
        )
    missing_parameters = set(PLANET_PARAMETER_DEFAULTS) - set(parameters)
    if missing_parameters:
        raise RuntimeError(
            "native library returned an incomplete planet_parameters snapshot: "
            + ", ".join(sorted(missing_parameters))
        )
    for key in PLANET_PARAMETER_DEFAULTS:
        raw = parameters[key]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise RuntimeError(
                f"native library returned invalid planet_parameters.{key}"
            )
        try:
            value = float(raw)
        except OverflowError as exc:
            raise RuntimeError(
                f"native library returned invalid planet_parameters.{key}"
            ) from exc
        if not math.isfinite(value) or (
            key in {"radius_km", "gravity_g", "geological_age_ga"}
            and value <= 0.0
        ):
            raise RuntimeError(
                f"native library returned invalid planet_parameters.{key}"
            )
    return payload


def _native_config(data: dict[str, Any]) -> NativeConfigV3:
    run = data["run"]
    planet = data["planet"]
    mesh = data["mesh"]
    tectonics = data["tectonics"]
    climate = data["climate"]
    hydrology = data["hydrology"]
    erosion = data["erosion"]
    compute = data["compute"]
    output = data["output"]
    base = NativeConfigV1(
        int(run["seed"]),
        str(run["name"]).encode("utf-8"),
        float(planet["radius_km"]),
        float(planet["gravity_g"]),
        float(planet["day_length_hours"]),
        float(planet["axial_tilt_deg"]),
        float(planet["orbital_eccentricity"]),
        float(planet["stellar_luminosity"]),
        float(planet["atmosphere_pressure_bar"]),
        float(planet["greenhouse_factor"]),
        float(planet["ocean_fraction_target"]),
        float(planet["ocean_water_inventory_km3"]),
        float(planet["internal_heat"]),
        float(planet["geological_age_ga"]),
        int(mesh["cell_count"]),
        int(MESH_BACKEND_IDS[str(mesh["backend"])]),
        int(mesh["neighbor_count"]),
        int(tectonics["plate_count"]),
        float(tectonics["continental_plate_fraction"]),
        float(tectonics["continental_crust_fraction_target"]),
        float(tectonics["min_angular_speed"]),
        float(tectonics["max_angular_speed"]),
        int(tectonics["boundary_smoothing_steps"]),
        float(tectonics["plate_motion_scale_deg_per_step"]),
        float(tectonics["oceanic_crust_aging_ma_per_step"]),
        int(climate["months"]),
        float(climate["lapse_rate_c_per_km"]),
        float(climate["base_temperature_c"]),
        float(climate["precipitation_scale"]),
        float(climate["subtropical_drying_strength"]),
        1 if hydrology["preserve_geologic_depressions"] else 0,
        float(hydrology["river_percentile"]),
        int(erosion["iterations"]),
        float(erosion["stream_power_coefficient"]),
        float(erosion["drainage_exponent"]),
        float(erosion["slope_exponent"]),
        float(erosion["hillslope_diffusion"]),
        float(erosion["tectonic_uplift_scale"]),
        int(compute["threads"]),
        1 if output["include_cells"] else 0,
        int(output["float_precision"]),
    )
    return NativeConfigV3(
        NativeConfigV2(
            base,
            int(COMPUTE_BACKEND_IDS[str(compute["backend"])]),
            1 if compute["opencl_prefer_gpu"] else 0,
        ),
        float(erosion["maturation_timestep_ma"]),
    )


def backend_info() -> dict[str, Any]:
    lib = _load_library()
    return _consume_json_pointer(lib, lib.magic_geo_backend_info_json())


def _native_seasonal_config(config: SeasonalWorldConfig) -> NativeConfigV4:
    # Revalidate models as well as mappings, including instances constructed or
    # subsequently modified without validation. No ctypes integer truncation or
    # truthiness conversion can turn invalid input into a different valid run.
    config = SeasonalWorldConfig.model_validate(config, strict=True)
    values: dict[str, Any] = {}
    for section in (config.run, config.planet, config.mesh, config.tectonics,
                    config.climate, config.hydrology, config.erosion,
                    config.compute, config.output):
        values.update(section.model_dump(exclude={"backend"}))
    values["name"] = config.run.name.encode("utf-8")
    values["mesh_backend"] = MESH_BACKEND_IDS[config.mesh.backend]
    values["compute_backend"] = COMPUTE_BACKEND_IDS[config.compute.backend]
    values["erosion_iterations"] = values.pop("iterations")
    for flag in ("preserve_geologic_depressions", "include_cells", "opencl_prefer_gpu"):
        values[flag] = int(values[flag])
    return NativeConfigV4(**values)


def _require_seasonal_world_identity(
    payload: dict[str, Any], *, config: SeasonalWorldConfig,
) -> dict[str, Any]:
    """Check model identity and coverage, not numerical budget correctness."""
    _require_current_world_schema(payload)
    declarations = {
        "climate_model": {
            "model_type": "prescribed_seasonal_surface_energy_v1",
            "temperature_model": "periodic_graybody_storage_conservative_transport_v1",
            "temperature_source": "climate_energy_balance_records_monthly_mean_temperature_k",
            "native_temperature_forcing_coupled": True,
            "imposed_mean_temperature": False,
            "post_solve_temperature_adjustments": False,
            "configured_month_count": config.climate.months,
            "display_temperature_decimal_places": config.output.float_precision,
        },
        "climate_energy_model": {
            "model": "native_prescribed_seasonal_energy_v1",
            "budget_schema_version": 1,
            "ownership": "native_temperature_producer",
            "native_temperature_forcing_coupled": True,
            "mesh_backend": MESH_BACKEND_IDS[config.mesh.backend],
        },
    }
    for section, expected_fields in declarations.items():
        model = payload.get(section)
        if not isinstance(model, dict):
            raise RuntimeError(f"native V4 output requires {section}")
        for key, expected in expected_fields.items():
            actual = model.get(key)
            if type(actual) is not type(expected) or actual != expected:
                raise RuntimeError(f"native V4 output has unsupported {section}.{key}: {actual!r}")
    for section in ("climate_energy_balance_records", "climate_energy_forcing_intervals"):
        if not isinstance(payload.get(section), list) or not payload[section]:
            raise RuntimeError(f"native V4 output requires nonempty {section}")
    if not isinstance(payload.get("climate_energy_transport_edges"), list):
        raise RuntimeError("native V4 output requires climate_energy_transport_edges array")
    for key, expected in config.planet.model_dump().items():
        if payload["planet_parameters"][key] != expected:
            raise RuntimeError(f"native V4 output does not match configured planet.{key}")
    for key in ("reference_infrared_optical_depth", "precipitation_scale", "subtropical_drying_strength"):
        actual = payload["climate_model"].get(key)
        if type(actual) not in (int, float) or actual != getattr(config.climate, key):
            raise RuntimeError(f"native V4 output does not match configured climate.{key}")
    model = payload["climate_energy_model"]
    expected_inputs = {
        "radius_m": config.planet.radius_km * 1000.0,
        "gravity_m_s2": config.planet.gravity_g * 9.80665,
        "mean_surface_pressure_pa": config.planet.atmosphere_pressure_bar * 100000.0,
        "reference_infrared_optical_depth": config.climate.reference_infrared_optical_depth,
        **{key: getattr(config.planet, key) for key in (
            "axial_tilt_deg", "orbital_eccentricity", "stellar_luminosity", "greenhouse_factor",
        )},
    }
    for key, expected in expected_inputs.items():
        actual = model.get(key)
        if type(actual) not in (int, float) or actual != expected:
            raise RuntimeError(f"native V4 budget does not match configured {key}")
    records = payload["climate_energy_balance_records"]
    if any(not isinstance(record, dict) or type(record.get("cell_id")) is not int
           or record["cell_id"] != i for i, record in enumerate(records)):
        raise RuntimeError("native V4 budget records must cover canonical cell IDs")
    cells = payload.get("cells")
    if not isinstance(cells, list):
        raise RuntimeError("native V4 output requires a cells array")
    if config.mesh.backend == "fibonacci_sphere" and len(records) != config.mesh.cell_count:
        raise RuntimeError("native V4 budget record count does not match configured mesh.cell_count")
    if config.output.include_cells:
        if len(cells) != len(records) or any(
            not isinstance(cell, dict) or type(cell.get("id")) is not int or cell["id"] != i
            for i, cell in enumerate(cells)
        ):
            raise RuntimeError("native V4 output cells do not match budget record coverage")
    elif cells:
        raise RuntimeError("native V4 output ignored include_cells=False")
    return payload


def _generate_seasonal_world(
    data: Mapping[str, Any] | SeasonalWorldConfig, *, geography_only: bool,
    serialization: str,
) -> dict[str, Any]:
    if serialization not in {"auto", "json", "msgpack"}:
        raise ValueError("serialization must be auto, json, or msgpack")
    config = SeasonalWorldConfig.model_validate(data, strict=True)
    native_config = _native_seasonal_config(config)
    lib = _load_seasonal_library()
    prefix = "magic_geo_generate_geo_" if geography_only else "magic_geo_generate_"
    if serialization in {"auto", "msgpack"}:
        size = ctypes.c_size_t()
        ptr = getattr(lib, prefix + "msgpack_v4")(ctypes.byref(native_config), ctypes.byref(size))
        payload = _consume_msgpack_pointer(lib, ptr, size.value, strict=True)
    else:
        ptr = getattr(lib, prefix + "json_v4")(ctypes.byref(native_config))
        payload = _consume_json_pointer(lib, ptr, strict=True)
    _require_seasonal_world_identity(payload, config=config)
    from .native_climate_energy_validation import audit_native_climate_energy

    if config.output.include_cells:
        audit_native_climate_energy(payload)
    else:
        # Explicit raw-ABI omission: the identity gate already required cells=[]
        # and matched the configured physical inputs. Audit the full retained
        # certificate without claiming unavailable display-field linkage. This
        # is never a fallback for missing or malformed requested cells.
        certificate = {key: payload[key] for key in (
            "climate_energy_model", "climate_energy_balance_records",
            "climate_energy_forcing_intervals", "climate_energy_transport_edges",
        )}
        audit_native_climate_energy(certificate, require_cell_linkage=False)
    from .native_social_public_validation import require_raw_native_social_publication
    try:
        require_raw_native_social_publication(
            payload, geography_only=geography_only,
            include_cells=config.output.include_cells, require_current=True,
        )
    except (ValueError, TypeError, KeyError, OverflowError, IndexError) as exc:
        raise RuntimeError("native V4 social publication invalid: " + str(exc)[:500]) from exc
    return payload


def generate_seasonal_world(
    data: Mapping[str, Any] | SeasonalWorldConfig, *, serialization: str = "auto",
) -> dict[str, Any]:
    """Generate raw native seasonal state from explicit config_version 2.

    Checks model identity, configured physical inputs and the published native
    energy certificate independently. Explicit include_cells=False validates
    the retained certificate without unavailable cell-display linkage. No
    Python enrichment runs here; unexported trajectories remain unverified.
    """
    return _generate_seasonal_world(data, geography_only=False, serialization=serialization)


def generate_seasonal_geo_world(
    data: Mapping[str, Any] | SeasonalWorldConfig, *, serialization: str = "auto",
) -> dict[str, Any]:
    """Generate raw seasonal geography without native civilization simulation."""
    return _generate_seasonal_world(data, geography_only=True, serialization=serialization)


def generate_world(
    data: dict[str, Any],
    *,
    serialization: str = "auto",
) -> dict[str, Any]:
    if "config_version" in data:
        return generate_seasonal_world(data, serialization=serialization)
    lib = _load_library()
    native_config = _native_config(data)
    if serialization not in {"auto", "json", "msgpack"}:
        raise ValueError("serialization must be auto, json, or msgpack")
    if serialization in {"auto", "msgpack"}:
        size = ctypes.c_size_t()
        ptr = lib.magic_geo_generate_msgpack_v3(
            ctypes.byref(native_config),
            ctypes.byref(size),
        )
        return _require_current_world_schema(
            _consume_msgpack_pointer(lib, ptr, size.value)
        )
    return _require_current_world_schema(
        _consume_json_pointer(
            lib,
            lib.magic_geo_generate_json_v3(ctypes.byref(native_config)),
        )
    )


def generate_geo_world(
    data: dict[str, Any],
    *,
    serialization: str = "auto",
) -> dict[str, Any]:
    if "config_version" in data:
        return generate_seasonal_geo_world(data, serialization=serialization)
    lib = _load_library()
    native_config = _native_config(data)
    if serialization not in {"auto", "json", "msgpack"}:
        raise ValueError("serialization must be auto, json, or msgpack")
    if serialization in {"auto", "msgpack"}:
        size = ctypes.c_size_t()
        ptr = lib.magic_geo_generate_geo_msgpack_v3(
            ctypes.byref(native_config),
            ctypes.byref(size),
        )
        return _require_current_world_schema(
            _consume_msgpack_pointer(lib, ptr, size.value)
        )
    return _require_current_world_schema(
        _consume_json_pointer(
            lib,
            lib.magic_geo_generate_geo_json_v3(ctypes.byref(native_config)),
        )
    )
