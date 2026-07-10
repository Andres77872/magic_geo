from __future__ import annotations

import math
from typing import Any


FACE_NAMES = ("+x", "-x", "+y", "-y", "+z", "-z")


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _cell_xyz(cell: dict[str, Any]) -> tuple[float, float, float]:
    lat = math.radians(float(cell["lat_deg"]))
    lon = math.radians(float(cell["lon_deg"]))
    cos_lat = math.cos(lat)
    return cos_lat * math.cos(lon), cos_lat * math.sin(lon), math.sin(lat)


def _lat_lon_from_xyz(x: float, y: float, z: float) -> tuple[float, float]:
    length = math.sqrt(x * x + y * y + z * z)
    if length <= 0.0:
        return 0.0, 0.0
    nz = _clamp(z / length, -1.0, 1.0)
    return math.degrees(math.asin(nz)), math.degrees(math.atan2(y, x))


def _cube_face_uv(x: float, y: float, z: float) -> tuple[int, float, float]:
    ax = abs(x)
    ay = abs(y)
    az = abs(z)
    if ax >= ay and ax >= az:
        if x >= 0.0:
            return 0, y / ax, z / ax
        return 1, -y / ax, z / ax
    if ay >= ax and ay >= az:
        if y >= 0.0:
            return 2, -x / ay, z / ay
        return 3, x / ay, z / ay
    if z >= 0.0:
        return 4, y / az, -x / az
    return 5, y / az, x / az


def _power_of_two_near(value: float, upper: int) -> int:
    if value <= 1.0:
        return 1
    exponent = max(0, min(int(math.log2(upper)), int(round(math.log2(value)))))
    return 1 << exponent


def _healpix_like_nside(cell_count: int) -> int:
    return _power_of_two_near(math.sqrt(max(1.0, cell_count / 12.0)), 64)


def _s2_like_level(cell_count: int) -> int:
    if cell_count <= 0:
        return 0
    nominal = math.sqrt(max(1.0, cell_count / 6.0))
    return max(0, min(12, int(round(math.log2(nominal)))))


def _healpix_like_pixel(lat_deg: float, lon_deg: float, nside: int) -> tuple[int, int, int, str, str]:
    ring_count = 3 * nside
    lon_bin_count = 4 * nside
    z = math.sin(math.radians(lat_deg))
    ring = min(ring_count - 1, max(0, int((1.0 - z) * 0.5 * ring_count)))
    lon_norm = (lon_deg + 180.0) % 360.0
    lon_bin = min(lon_bin_count - 1, max(0, int(lon_norm / 360.0 * lon_bin_count)))
    pixel_id = ring * lon_bin_count + lon_bin
    if ring < nside:
        zone = "north_polar"
    elif ring >= 2 * nside:
        zone = "south_polar"
    else:
        zone = "equatorial"
    return ring, lon_bin, pixel_id, f"H{nside}R{ring}C{lon_bin}", zone


def _s2_like_cell(face: int, u: float, v: float, level: int) -> tuple[int, int, int, str]:
    scale = 1 << level
    x = min(scale - 1, max(0, int((u + 1.0) * 0.5 * scale)))
    y = min(scale - 1, max(0, int((v + 1.0) * 0.5 * scale)))
    cell_id = face * scale * scale + y * scale + x
    digits: list[str] = []
    for bit in range(level - 1, -1, -1):
        digit = ((y >> bit) & 1) * 2 + ((x >> bit) & 1)
        digits.append(str(digit))
    token = f"F{face}" + ("-" + "".join(digits) if digits else "")
    return x, y, cell_id, token


def _finalize_record(record: dict[str, Any]) -> dict[str, Any]:
    lat, lon = _lat_lon_from_xyz(float(record.pop("_sum_x")), float(record.pop("_sum_y")), float(record.pop("_sum_z")))
    record["area_km2"] = round(float(record["area_km2"]), 6)
    record["centroid_lat_deg"] = round(lat, 6)
    record["centroid_lon_deg"] = round(lon, 6)
    return record


def enrich_world_with_spherical_index(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    nside = _healpix_like_nside(len(cells))
    ring_count = 3 * nside
    lon_bin_count = 4 * nside
    pixel_count = ring_count * lon_bin_count
    s2_level = _s2_like_level(len(cells))
    s2_scale = 1 << s2_level
    s2_cell_count = len(FACE_NAMES) * s2_scale * s2_scale

    healpix_pixels: dict[int, dict[str, Any]] = {}
    s2_cells: dict[int, dict[str, Any]] = {}

    for cell in cells:
        cell_id = int(cell.get("id", -1))
        lat = float(cell.get("lat_deg", 0.0))
        lon = float(cell.get("lon_deg", 0.0))
        area = float(cell.get("area_km2", 0.0))
        x, y, z = _cell_xyz(cell)

        ring, lon_bin, pixel_id, pixel_code, pixel_zone = _healpix_like_pixel(lat, lon, nside)
        pixel = healpix_pixels.get(pixel_id)
        if pixel is None:
            pixel = {
                "pixel_id": pixel_id,
                "pixel_code": pixel_code,
                "ring": ring,
                "lon_bin": lon_bin,
                "zone": pixel_zone,
                "cell_count": 0,
                "representative_cell_id": cell_id,
                "area_km2": 0.0,
                "_sum_x": 0.0,
                "_sum_y": 0.0,
                "_sum_z": 0.0,
            }
            healpix_pixels[pixel_id] = pixel
        pixel["cell_count"] += 1
        pixel["area_km2"] += area
        pixel["_sum_x"] += x
        pixel["_sum_y"] += y
        pixel["_sum_z"] += z

        face, u, v = _cube_face_uv(x, y, z)
        s2_x, s2_y, s2_cell_id, s2_token = _s2_like_cell(face, u, v, s2_level)
        s2_record = s2_cells.get(s2_cell_id)
        if s2_record is None:
            s2_record = {
                "cell_id": s2_cell_id,
                "token": s2_token,
                "level": s2_level,
                "face": FACE_NAMES[face],
                "face_id": face,
                "x": s2_x,
                "y": s2_y,
                "cell_count": 0,
                "representative_cell_id": cell_id,
                "area_km2": 0.0,
                "_sum_x": 0.0,
                "_sum_y": 0.0,
                "_sum_z": 0.0,
            }
            s2_cells[s2_cell_id] = s2_record
        s2_record["cell_count"] += 1
        s2_record["area_km2"] += area
        s2_record["_sum_x"] += x
        s2_record["_sum_y"] += y
        s2_record["_sum_z"] += z

        cell["healpix_like_nside"] = nside
        cell["healpix_like_ring"] = ring
        cell["healpix_like_lon_bin"] = lon_bin
        cell["healpix_like_pixel_id"] = pixel_id
        cell["healpix_like_pixel_code"] = pixel_code
        cell["s2_like_face"] = FACE_NAMES[face]
        cell["s2_like_face_id"] = face
        cell["s2_like_cell_level"] = s2_level
        cell["s2_like_x"] = s2_x
        cell["s2_like_y"] = s2_y
        cell["s2_like_cell_id"] = s2_cell_id
        cell["s2_like_token"] = s2_token

    healpix_records = [_finalize_record(record) for _, record in sorted(healpix_pixels.items())]
    s2_records = [_finalize_record(record) for _, record in sorted(s2_cells.items())]
    face_summaries: list[dict[str, Any]] = []
    for face_id, face_name in enumerate(FACE_NAMES):
        face_records = [record for record in s2_records if int(record["face_id"]) == face_id]
        cell_count = sum(int(record["cell_count"]) for record in face_records)
        area_sum = sum(float(record["area_km2"]) for record in face_records)
        face_summaries.append(
            {
                "face": face_name,
                "face_id": face_id,
                "occupied_cell_count": len(face_records),
                "cell_count": cell_count,
                "area_km2": round(area_sum, 6),
            }
        )

    world["spherical_spatial_index"] = {
        "index": "healpix_s2_compat_v0",
        "description": (
            "Dependency-free HEALPix-inspired equal-area latitude/longitude pixels and "
            "S2-inspired cube-face tokens over generated cell centroids; metadata only, "
            "not a native HEALPix or S2 mesh backend."
        ),
        "healpix_like_nside": nside,
        "healpix_like_ring_count": ring_count,
        "healpix_like_lon_bin_count": lon_bin_count,
        "healpix_like_pixel_count": pixel_count,
        "healpix_like_occupied_pixel_count": len(healpix_records),
        "healpix_like_pixels": healpix_records,
        "s2_like_level": s2_level,
        "s2_like_cell_count": s2_cell_count,
        "s2_like_occupied_cell_count": len(s2_records),
        "s2_like_face_summaries": face_summaries,
        "s2_like_cells": s2_records,
    }

    summary = world.setdefault("summary", {})
    summary["spherical_spatial_index"] = "healpix_s2_compat_v0"
    summary["healpix_like_nside"] = nside
    summary["healpix_like_pixel_count"] = pixel_count
    summary["healpix_like_occupied_pixel_count"] = len(healpix_records)
    summary["healpix_like_mean_cells_per_occupied_pixel"] = round(len(cells) / len(healpix_records), 6) if healpix_records else 0.0
    summary["s2_like_cell_level"] = s2_level
    summary["s2_like_cell_count"] = s2_cell_count
    summary["s2_like_occupied_cell_count"] = len(s2_records)
    summary["s2_like_mean_cells_per_occupied_cell"] = round(len(cells) / len(s2_records), 6) if s2_records else 0.0

    return world
