from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from typing import Any


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


# Internal compatibility alias for code that imported the previous private
# class name while the versioned ABI was being introduced.
NativeConfig = NativeConfigV3


def _library_path() -> Path:
    override = os.environ.get("MAGIC_GEO_NATIVE_LIBRARY")
    if override:
        candidate = Path(override).expanduser().resolve()
        if not candidate.is_file():
            raise RuntimeError(
                f"MAGIC_GEO_NATIVE_LIBRARY does not name a file: {candidate}"
            )
        return candidate
    suffixes = ["libmagic_geo_native.so", "magic_geo_native.dll", "libmagic_geo_native.dylib"]
    package_dir = Path(__file__).resolve().parent
    for suffix in suffixes:
        candidate = package_dir / suffix
        if candidate.exists():
            return candidate
    raise RuntimeError(
        "native library was not found. Build it with: "
        "cmake -S . -B build && cmake --build build"
    )


def _load_library() -> ctypes.CDLL:
    lib = ctypes.CDLL(str(_library_path()))
    lib.magic_geo_backend_info_json.argtypes = []
    lib.magic_geo_backend_info_json.restype = ctypes.c_void_p
    lib.magic_geo_generate_json.argtypes = [ctypes.POINTER(NativeConfigV1)]
    lib.magic_geo_generate_json.restype = ctypes.c_void_p
    lib.magic_geo_generate_json_v2.argtypes = [ctypes.POINTER(NativeConfigV2)]
    lib.magic_geo_generate_json_v2.restype = ctypes.c_void_p
    generate_v3 = getattr(lib, "magic_geo_generate_json_v3", None)
    if generate_v3 is not None:
        generate_v3.argtypes = [ctypes.POINTER(NativeConfigV3)]
        generate_v3.restype = ctypes.c_void_p
    geo_generate = getattr(lib, "magic_geo_generate_geo_json_v2", None)
    if geo_generate is not None:
        geo_generate.argtypes = [ctypes.POINTER(NativeConfigV2)]
        geo_generate.restype = ctypes.c_void_p
    geo_generate_v3 = getattr(lib, "magic_geo_generate_geo_json_v3", None)
    if geo_generate_v3 is not None:
        geo_generate_v3.argtypes = [ctypes.POINTER(NativeConfigV3)]
        geo_generate_v3.restype = ctypes.c_void_p
    lib.magic_geo_free_string.argtypes = [ctypes.c_void_p]
    lib.magic_geo_free_string.restype = None
    return lib


def _consume_json_pointer(lib: ctypes.CDLL, ptr: int) -> dict[str, Any]:
    if not ptr:
        raise RuntimeError("native library returned a null JSON pointer")
    try:
        raw = ctypes.cast(ptr, ctypes.c_char_p).value
        if raw is None:
            raise RuntimeError("native library returned an empty JSON pointer")
        payload = json.loads(raw.decode("utf-8"))
    finally:
        lib.magic_geo_free_string(ptr)
    if isinstance(payload, dict) and "error" in payload:
        raise RuntimeError(str(payload["error"]))
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


def generate_world(data: dict[str, Any]) -> dict[str, Any]:
    lib = _load_library()
    generate_v3 = getattr(lib, "magic_geo_generate_json_v3", None)
    if generate_v3 is None:
        raise RuntimeError(
            "native library does not support the nominal maturation clock; "
            "rebuild magic_geo_native from the current source tree"
        )
    native_config = _native_config(data)
    return _consume_json_pointer(lib, generate_v3(ctypes.byref(native_config)))


def generate_geo_world(data: dict[str, Any]) -> dict[str, Any]:
    lib = _load_library()
    geo_generate_v3 = getattr(lib, "magic_geo_generate_geo_json_v3", None)
    if geo_generate_v3 is None:
        raise RuntimeError(
            "native library does not support geo-only generation with the "
            "nominal maturation clock; rebuild "
            "magic_geo_native from the current source tree"
        )
    native_config = _native_config(data)
    return _consume_json_pointer(
        lib,
        geo_generate_v3(ctypes.byref(native_config)),
    )
