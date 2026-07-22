"""Dependency-free PPM raster rendering."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any


def write_raster_map(
    path: Path,
    world: dict[str, Any],
    *,
    width: int = 1600,
    height: int = 800,
    projection: str = "equirectangular",
    max_cells: int | None = None,
    texture: bool = True,
) -> None:
    """Write a dependency-free PPM raster map from generated causal fields."""
    cells = world.get("cells", [])
    settlements = world.get("settlements", [])
    routes = world.get("routes", [])
    path.parent.mkdir(parents=True, exist_ok=True)
    projection = projection.lower().replace("_", "-")
    if projection not in {"equirectangular", "mollweide", "orthographic"}:
        raise ValueError(f"unknown projection: {projection}")

    palette: dict[str, tuple[int, int, int]] = {
        "ocean": (31, 95, 139),
        "continental_shelf": (55, 145, 178),
        "lake": (64, 160, 194),
        "ice_cap": (242, 247, 245),
        "tundra": (185, 198, 176),
        "boreal_forest": (70, 109, 85),
        "temperate_forest": (47, 125, 79),
        "temperate_grassland": (156, 175, 98),
        "mediterranean_scrub": (183, 165, 101),
        "cold_desert": (199, 185, 142),
        "hot_desert": (216, 187, 114),
        "savanna": (192, 164, 78),
        "tropical_seasonal_forest": (39, 130, 76),
        "tropical_rainforest": (23, 107, 59),
        "alpine": (156, 159, 151),
        "wetland": (82, 127, 115),
    }
    cell_by_id = {int(cell["id"]): cell for cell in cells if "id" in cell}

    def clamp_channel(value: float) -> int:
        return max(0, min(255, int(round(value))))

    def blend_rgb(a: tuple[int, int, int], b: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
        amount = max(0.0, min(1.0, amount))
        return tuple(clamp_channel(a[i] * (1.0 - amount) + b[i] * amount) for i in range(3))

    def shade_rgb(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
        factor = max(0.0, min(2.0, factor))
        if factor >= 1.0:
            return tuple(clamp_channel(channel + (255 - channel) * (factor - 1.0)) for channel in color)
        return tuple(clamp_channel(channel * factor) for channel in color)

    def elevation_rgb(elevation_m: float) -> tuple[int, int, int]:
        if elevation_m < 120.0:
            return blend_rgb((139, 166, 106), (210, 192, 128), max(0.0, elevation_m) / 120.0)
        if elevation_m < 900.0:
            return blend_rgb((210, 192, 128), (154, 135, 92), (elevation_m - 120.0) / 780.0)
        if elevation_m < 1900.0:
            return blend_rgb((154, 135, 92), (128, 117, 106), (elevation_m - 900.0) / 1000.0)
        return blend_rgb((128, 117, 106), (238, 232, 208), min(1.0, (elevation_m - 1900.0) / 1800.0))

    def cell_noise(cell_id: int) -> float:
        value = (cell_id * 1103515245 + 12345) & 0x7FFFFFFF
        value ^= (value >> 11)
        return (value & 0xFFFF) / 65535.0

    relief_by_id: dict[int, float] = {}
    for cell in cells:
        try:
            cell_id = int(cell["id"])
        except (KeyError, TypeError, ValueError):
            continue
        neighbors = [cell_by_id.get(int(neighbor)) for neighbor in cell.get("neighbors", [])]
        elevations = [float(neighbor.get("elevation_m", 0.0)) for neighbor in neighbors if neighbor]
        if elevations:
            relief_by_id[cell_id] = max(0.0, float(cell.get("elevation_m", 0.0)) - sum(elevations) / len(elevations))
        else:
            relief_by_id[cell_id] = 0.0

    def terrain_rgb(cell: dict[str, Any]) -> tuple[int, int, int]:
        cell_id = int(cell.get("id", -1))
        biome = str(cell.get("biome", "ocean"))
        landform = str(cell.get("landform", ""))
        elevation_m = float(cell.get("elevation_m", 0.0))
        relief = relief_by_id.get(cell_id, 0.0)
        if cell.get("is_water"):
            depth = max(0.0, float(cell.get("water_depth_m", 0.0)))
            color = blend_rgb((113, 185, 201), (21, 63, 103), min(1.0, depth / 4200.0))
            water_body = str(cell.get("water_body_type", ""))
            if water_body == "continental_shelf":
                color = blend_rgb(color, (116, 197, 199), 0.45)
            elif water_body == "inland_sea":
                color = blend_rgb(color, (79, 165, 187), 0.32)
            elif water_body in {"fresh_lake", "saline_basin"}:
                color = blend_rgb(color, (94, 184, 205), 0.25)
            reef_growth = float(cell.get("reef_growth_index", 0.0))
            if int(cell.get("reef_system_id", -1)) >= 0 or reef_growth >= 0.46:
                color = blend_rgb(color, (141, 240, 210), 0.34 + 0.34 * min(1.0, reef_growth))
            current = float(cell.get("ocean_current_moisture_factor", 1.0))
            color = shade_rgb(color, 0.92 + 0.10 * max(0.0, min(1.0, current - 0.6)))
            return color

        color = blend_rgb(palette.get(biome, (119, 119, 119)), elevation_rgb(elevation_m), 0.48)
        pet = max(1.0, (float(cell.get("temperature_c", 0.0)) + 8.0) * 31.0)
        aridity = float(cell.get("precipitation_mm_y", 0.0)) / pet
        sediment = min(1.0, float(cell.get("sediment_thickness_m", 0.0)) / 8.0)
        if aridity < 0.45:
            color = blend_rgb(color, (216, 191, 122), 0.40)
        elif aridity > 1.15 and float(cell.get("temperature_c", 0.0)) > 12.0:
            color = blend_rgb(color, (47, 118, 81), 0.24)
        if sediment > 0.10 and landform in {"delta", "floodplain", "alluvial_fan", "coastal_plain"}:
            color = blend_rgb(color, (117, 157, 104), 0.18 + 0.22 * sediment)
        if float(cell.get("ice_thickness_m", 0.0)) > 80.0 or biome == "ice_cap":
            color = blend_rgb(color, (244, 246, 237), 0.78)
        if landform in {"mountain_belt", "volcanic_arc", "glacial_valley"}:
            color = shade_rgb(color, 0.82)
        elif landform in {"delta", "floodplain", "wetland"}:
            color = blend_rgb(color, (111, 167, 143), 0.42)
        elif landform == "salt_flat":
            color = blend_rgb(color, (236, 230, 207), 0.62)
        elif landform == "moraine":
            color = blend_rgb(color, (143, 145, 133), 0.50)

        if texture:
            noise = cell_noise(cell_id)
            relief_factor = min(1.0, relief / 1800.0)
            erosion_factor = min(1.0, float(cell.get("erosion_rate", 0.0)) / 18.0)
            color = shade_rgb(color, 0.88 + 0.20 * relief_factor + 0.08 * erosion_factor + 0.10 * (noise - 0.5))
        return color

    def project(lat: float, lon: float) -> tuple[float, float] | None:
        if projection == "equirectangular":
            return ((lon + 180.0) / 360.0 * width, (90.0 - lat) / 180.0 * height)
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        if projection == "orthographic":
            cos_c = math.cos(lat_rad) * math.cos(lon_rad)
            if cos_c < 0.0:
                return None
            radius_px = min(width, height) * 0.47
            return (
                width * 0.5 + radius_px * math.cos(lat_rad) * math.sin(lon_rad),
                height * 0.5 - radius_px * math.sin(lat_rad),
            )
        theta = lat_rad
        for _ in range(8):
            denom = 2.0 + 2.0 * math.cos(2.0 * theta)
            if abs(denom) < 1.0e-9:
                break
            theta -= (2.0 * theta + math.sin(2.0 * theta) - math.pi * math.sin(lat_rad)) / denom
        x_norm = (2.0 * math.sqrt(2.0) / math.pi) * lon_rad * math.cos(theta)
        y_norm = math.sqrt(2.0) * math.sin(theta)
        return (
            width * (0.5 + x_norm / (4.0 * math.sqrt(2.0))),
            height * (0.5 - y_norm / (2.0 * math.sqrt(2.0))),
        )

    def projected_cell(cell: dict[str, Any]) -> tuple[float, float] | None:
        return project(float(cell.get("lat_deg", 0.0)), float(cell.get("lon_deg", 0.0)))

    def put_pixel(pixels: bytearray, x: int, y: int, color: tuple[int, int, int], alpha: float = 1.0) -> None:
        if x < 0 or x >= width or y < 0 or y >= height:
            return
        index = (y * width + x) * 3
        if alpha >= 1.0:
            pixels[index:index + 3] = bytes(color)
            return
        alpha = max(0.0, min(1.0, alpha))
        for offset, channel in enumerate(color):
            pixels[index + offset] = clamp_channel(pixels[index + offset] * (1.0 - alpha) + channel * alpha)

    def draw_disc(
        pixels: bytearray,
        cx: float,
        cy: float,
        radius: float,
        color: tuple[int, int, int],
        alpha: float = 1.0,
    ) -> None:
        radius = max(0.5, radius)
        min_x = max(0, int(math.floor(cx - radius)))
        max_x = min(width - 1, int(math.ceil(cx + radius)))
        min_y = max(0, int(math.floor(cy - radius)))
        max_y = min(height - 1, int(math.ceil(cy + radius)))
        radius_sq = radius * radius
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                dx = x + 0.5 - cx
                dy = y + 0.5 - cy
                distance_sq = dx * dx + dy * dy
                if distance_sq <= radius_sq:
                    edge = max(0.0, min(1.0, 1.0 - (distance_sq / radius_sq)))
                    put_pixel(pixels, x, y, color, alpha * (0.70 + 0.30 * edge))

    def draw_line(
        pixels: bytearray,
        a: tuple[float, float],
        b: tuple[float, float],
        color: tuple[int, int, int],
        radius: float,
        alpha: float,
    ) -> None:
        x1, y1 = a
        x2, y2 = b
        if projection == "equirectangular" and abs(x1 - x2) > width * 0.55:
            return
        steps = max(1, int(max(abs(x2 - x1), abs(y2 - y1))))
        for step in range(steps + 1):
            t = step / steps
            draw_disc(pixels, x1 * (1.0 - t) + x2 * t, y1 * (1.0 - t) + y2 * t, radius, color, alpha)

    render_cells = cells
    if max_cells is not None and max_cells > 0 and len(cells) > max_cells:
        stride = max(1, math.ceil(len(cells) / max_cells))
        render_cells = cells[::stride]

    pixels = bytearray((23, 59, 86) * (width * height))
    if projection == "orthographic":
        center_x = width * 0.5
        center_y = height * 0.5
        radius_px = min(width, height) * 0.47
        for y in range(height):
            for x in range(width):
                dx = x + 0.5 - center_x
                dy = y + 0.5 - center_y
                if dx * dx + dy * dy > radius_px * radius_px:
                    put_pixel(pixels, x, y, (12, 25, 37))

    radius = max(1.0, min(18.0, (width * height / max(1, len(render_cells))) ** 0.5 * 0.48))
    for cell in render_cells:
        point = projected_cell(cell)
        if point is None:
            continue
        x, y = point
        draw_disc(pixels, x, y, radius, terrain_rgb(cell), 0.96)

    for route in routes:
        from_index = int(route.get("from", -1))
        to_index = int(route.get("to", -1))
        from_settlement = settlements[from_index] if 0 <= from_index < len(settlements) else None
        to_settlement = settlements[to_index] if 0 <= to_index < len(settlements) else None
        if not from_settlement or not to_settlement:
            continue
        a = cell_by_id.get(int(from_settlement["cell_id"]))
        b = cell_by_id.get(int(to_settlement["cell_id"]))
        if not a or not b:
            continue
        point_a = projected_cell(a)
        point_b = projected_cell(b)
        if point_a is None or point_b is None:
            continue
        color = (240, 211, 138) if route.get("type") != "coastal_sea" else (155, 211, 223)
        draw_line(pixels, point_a, point_b, color, max(0.8, radius * 0.17), 0.70)

    for settlement in settlements:
        cell = cell_by_id.get(int(settlement.get("cell_id", -1)))
        if not cell:
            continue
        point = projected_cell(cell)
        if point is None:
            continue
        size = max(1.5, min(8.0, radius * (0.28 + 0.50 * float(settlement.get("score", 0.0)))))
        draw_disc(pixels, point[0], point[1], size + 1.0, (35, 31, 23), 0.92)
        draw_disc(pixels, point[0], point[1], size, (242, 221, 159), 0.95)

    header = (
        f"P6\n# magic-geo raster-terrain-v1 projection={projection} texture={str(texture).lower()}\n"
        f"{width} {height}\n255\n"
    ).encode("ascii")
    path.write_bytes(header + bytes(pixels))
