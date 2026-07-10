from __future__ import annotations

import math
from typing import Any


FACE_NAMES = ("+x", "-x", "+y", "-y", "+z", "-z")


def _max_lod_level(cell_count: int) -> int:
    if cell_count <= 0:
        return 0
    nominal = max(1.0, cell_count / 6.0)
    return max(1, min(6, int(math.ceil(math.log(nominal, 4.0)))))


def _cell_xyz(cell: dict[str, Any]) -> tuple[float, float, float]:
    lat = math.radians(float(cell["lat_deg"]))
    lon = math.radians(float(cell["lon_deg"]))
    cos_lat = math.cos(lat)
    return cos_lat * math.cos(lon), cos_lat * math.sin(lon), math.sin(lat)


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


def _tile_xy(level: int, u: float, v: float) -> tuple[int, int]:
    scale = 1 << level
    x = min(scale - 1, max(0, int((u + 1.0) * 0.5 * scale)))
    y = min(scale - 1, max(0, int((v + 1.0) * 0.5 * scale)))
    return x, y


def _tile_id(level: int, face: int, x: int, y: int) -> int:
    scale = 1 << level
    return face * scale * scale + y * scale + x


def _tile_code(level: int, face: int, x: int, y: int) -> str:
    return f"L{level}F{face}X{x}Y{y}"


def _tile_for_level(level: int, face: int, u: float, v: float) -> tuple[int, int, int, str]:
    x, y = _tile_xy(level, u, v)
    return x, y, _tile_id(level, face, x, y), _tile_code(level, face, x, y)


def _centroid_from_xyz(x: float, y: float, z: float) -> tuple[float, float]:
    length = math.sqrt(x * x + y * y + z * z)
    if length <= 0.0:
        return 0.0, 0.0
    nx = x / length
    ny = y / length
    nz = z / length
    return math.degrees(math.asin(max(-1.0, min(1.0, nz)))), math.degrees(math.atan2(ny, nx))


def enrich_world_with_mesh_lod(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    max_level = _max_lod_level(len(cells))
    tiles: dict[tuple[int, int], dict[str, Any]] = {}

    for cell in cells:
        x, y, z = _cell_xyz(cell)
        face, u, v = _cube_face_uv(x, y, z)
        area_km2 = float(cell.get("area_km2", 0.0))
        tile_ids: list[int] = []
        tile_codes: list[str] = []

        for level in range(max_level + 1):
            tile_x, tile_y, tile_id, tile_code = _tile_for_level(level, face, u, v)
            parent_tile_id = -1
            if level > 0:
                parent_tile_id = _tile_id(level - 1, face, tile_x // 2, tile_y // 2)
            key = (level, tile_id)
            tile = tiles.get(key)
            if tile is None:
                tile = {
                    "level": level,
                    "tile_id": tile_id,
                    "tile_code": tile_code,
                    "parent_tile_id": parent_tile_id,
                    "face": FACE_NAMES[face],
                    "face_id": face,
                    "x": tile_x,
                    "y": tile_y,
                    "cell_count": 0,
                    "child_tile_count": 0,
                    "representative_cell_id": int(cell["id"]),
                    "area_km2": 0.0,
                    "_sum_x": 0.0,
                    "_sum_y": 0.0,
                    "_sum_z": 0.0,
                }
                tiles[key] = tile
            tile["cell_count"] += 1
            tile["area_km2"] += area_km2
            tile["_sum_x"] += x
            tile["_sum_y"] += y
            tile["_sum_z"] += z
            tile_ids.append(tile_id)
            tile_codes.append(tile_code)

        cell["mesh_lod_face"] = FACE_NAMES[face]
        cell["mesh_lod_face_id"] = face
        cell["mesh_lod_tile_ids"] = tile_ids
        cell["mesh_lod_codes"] = tile_codes
        cell["mesh_lod_finest_tile_id"] = tile_ids[-1]

    child_counts: dict[tuple[int, int], int] = {}
    for (level, _tile_id_value), tile in tiles.items():
        if level > 0:
            parent_key = (level - 1, int(tile["parent_tile_id"]))
            child_counts[parent_key] = child_counts.get(parent_key, 0) + 1

    tile_records: list[dict[str, Any]] = []
    for key in sorted(tiles):
        tile = tiles[key]
        centroid_lat, centroid_lon = _centroid_from_xyz(
            float(tile.pop("_sum_x")),
            float(tile.pop("_sum_y")),
            float(tile.pop("_sum_z")),
        )
        tile["centroid_lat_deg"] = round(centroid_lat, 6)
        tile["centroid_lon_deg"] = round(centroid_lon, 6)
        tile["area_km2"] = round(float(tile["area_km2"]), 6)
        tile["child_tile_count"] = child_counts.get(key, 0)
        tile_records.append(tile)

    level_summaries: list[dict[str, Any]] = []
    for level in range(max_level + 1):
        level_tiles = [tile for tile in tile_records if int(tile["level"]) == level]
        tile_count = len(level_tiles)
        cell_sum = sum(int(tile["cell_count"]) for tile in level_tiles)
        max_cell_count = max((int(tile["cell_count"]) for tile in level_tiles), default=0)
        area_sum = sum(float(tile["area_km2"]) for tile in level_tiles)
        level_summaries.append(
            {
                "level": level,
                "nominal_tile_count": 6 * (4 ** level),
                "occupied_tile_count": tile_count,
                "cell_count": cell_sum,
                "mean_cells_per_tile": round(cell_sum / tile_count, 6) if tile_count else 0.0,
                "max_cells_per_tile": max_cell_count,
                "mean_tile_area_km2": round(area_sum / tile_count, 6) if tile_count else 0.0,
            }
        )

    world["mesh_lod"] = {
        "index": "cube_quadtree_v0",
        "description": "Dependency-free spherical cube-face quadtree over generated cell centroids.",
        "max_level": max_level,
        "root_face_count": len(FACE_NAMES),
        "level_summaries": level_summaries,
        "tiles": tile_records,
    }

    summary = world.setdefault("summary", {})
    summary["mesh_lod_index"] = "cube_quadtree_v0"
    summary["mesh_lod_max_level"] = max_level
    summary["mesh_lod_level_count"] = max_level + 1
    summary["mesh_lod_tile_count"] = len(tile_records)
    summary["mesh_lod_finest_tile_count"] = level_summaries[-1]["occupied_tile_count"]
    summary["mesh_lod_mean_finest_tile_cell_count"] = level_summaries[-1]["mean_cells_per_tile"]

    return world
