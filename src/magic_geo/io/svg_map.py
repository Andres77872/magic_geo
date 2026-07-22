"""Layer-driven SVG map rendering."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import html


def write_svg_map(
    path: Path,
    world: dict[str, Any],
    *,
    width: int = 1600,
    height: int = 800,
    projection: str = "equirectangular",
    labels: bool = False,
    max_cells: int | None = None,
    contours: bool = True,
    contour_interval_m: float = 500.0,
) -> None:
    cells = world.get("cells", [])
    settlements = world.get("settlements", [])
    routes = world.get("routes", [])
    sacred_areas = world.get("sacred_areas", [])
    ruins = world.get("ruins", [])
    path.parent.mkdir(parents=True, exist_ok=True)
    projection = projection.lower().replace("_", "-")
    if projection not in {"equirectangular", "mollweide", "orthographic"}:
        raise ValueError(f"unknown projection: {projection}")

    palette = {
        "ocean": "#1f5f8b",
        "continental_shelf": "#2e8bb3",
        "lake": "#3c9fc2",
        "ice_cap": "#f1f7f5",
        "tundra": "#b9c6b0",
        "boreal_forest": "#466d55",
        "temperate_forest": "#2f7d4f",
        "temperate_grassland": "#9caf62",
        "mediterranean_scrub": "#b7a565",
        "cold_desert": "#c7b98e",
        "hot_desert": "#d8bb72",
        "savanna": "#c0a44e",
        "tropical_seasonal_forest": "#27824c",
        "tropical_rainforest": "#176b3b",
        "alpine": "#9c9f97",
        "wetland": "#527f73",
    }
    settlement_colors = {
        "river_city": "#f4f1d0",
        "port": "#f6c65b",
        "mining_town": "#d98559",
        "agricultural_town": "#d9e27d",
        "oasis": "#7ed6c4",
        "frontier_town": "#e8dfbd",
    }
    cell_by_id = {int(cell["id"]): cell for cell in cells if "id" in cell}

    def hex_to_rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))

    def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
        return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, channel)) for channel in rgb))

    def blend(color_a: str, color_b: str, amount: float) -> str:
        amount = max(0.0, min(1.0, amount))
        a = hex_to_rgb(color_a)
        b = hex_to_rgb(color_b)
        return rgb_to_hex(tuple(round(a[i] * (1.0 - amount) + b[i] * amount) for i in range(3)))

    def shade(color: str, factor: float) -> str:
        factor = max(0.0, min(2.0, factor))
        rgb = hex_to_rgb(color)
        if factor >= 1.0:
            return rgb_to_hex(tuple(round(channel + (255 - channel) * (factor - 1.0)) for channel in rgb))
        return rgb_to_hex(tuple(round(channel * factor) for channel in rgb))

    def elevation_color(elevation_m: float) -> str:
        if elevation_m < 120.0:
            return blend("#8ba66a", "#d2c080", max(0.0, elevation_m) / 120.0)
        if elevation_m < 900.0:
            return blend("#d2c080", "#9a875c", (elevation_m - 120.0) / 780.0)
        if elevation_m < 1900.0:
            return blend("#9a875c", "#80756a", (elevation_m - 900.0) / 1000.0)
        return blend("#80756a", "#eee8d0", min(1.0, (elevation_m - 1900.0) / 1800.0))

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

    def terrain_style(cell: dict[str, Any]) -> tuple[str, str, str, float]:
        biome = str(cell.get("biome", "ocean"))
        landform = str(cell.get("landform", ""))
        elevation_m = float(cell.get("elevation_m", 0.0))
        water_depth_m = float(cell.get("water_depth_m", 0.0))
        relief = relief_by_id.get(int(cell.get("id", -1)), 0.0)
        if cell.get("is_water"):
            depth = max(0.0, water_depth_m)
            fill = blend("#71b9c9", "#153f67", min(1.0, depth / 4200.0))
            if str(cell.get("water_body_type", "")) == "continental_shelf":
                fill = blend(fill, "#74c5c7", 0.42)
            elif str(cell.get("water_body_type", "")) == "inland_sea":
                fill = blend(fill, "#4fa5bb", 0.30)
            reef_growth = float(cell.get("reef_growth_index", 0.0))
            if int(cell.get("reef_system_id", -1)) >= 0 or reef_growth >= 0.46:
                fill = blend(fill, "#8df0d2", 0.34 + 0.34 * min(1.0, reef_growth))
            stroke = "#82d0d2" if landform == "fjord" else fill
            return fill, stroke, "0.18", 0.94

        fill = blend(palette.get(biome, "#777777"), elevation_color(elevation_m), 0.46)
        aridity = float(cell.get("precipitation_mm_y", 0.0)) / max(1.0, (float(cell.get("temperature_c", 0.0)) + 8.0) * 31.0)
        if aridity < 0.45:
            fill = blend(fill, "#d8bf7a", 0.40)
        elif aridity > 1.15 and float(cell.get("temperature_c", 0.0)) > 12.0:
            fill = blend(fill, "#2f7651", 0.24)
        if float(cell.get("ice_thickness_m", 0.0)) > 80.0 or biome == "ice_cap":
            fill = blend(fill, "#f4f6ed", 0.78)
        if landform in {"mountain_belt", "volcanic_arc", "glacial_valley"}:
            fill = shade(fill, 0.84)
        elif landform in {"delta", "floodplain", "wetland"}:
            fill = blend(fill, "#6fa78f", 0.44)
        elif landform == "salt_flat":
            fill = blend(fill, "#ece6cf", 0.62)
        elif landform == "moraine":
            fill = blend(fill, "#8f9185", 0.50)

        relief_shade = 0.86 + 0.22 * min(1.0, relief / 1800.0)
        fill = shade(fill, relief_shade)
        contour = elevation_m > 950.0 and abs(elevation_m % 500.0) < 55.0
        if cell.get("is_river"):
            return fill, "#9bd3df", "0.42", 0.98
        if contour:
            return fill, "#f0e0ad", "0.36", 0.97
        if landform in {"delta", "alluvial_fan", "floodplain", "moraine", "glacial_valley"}:
            return fill, "#ead58c", "0.30", 0.97
        return fill, shade(fill, 0.72), "0.08", 0.96

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

    render_cells = cells
    if max_cells is not None and max_cells > 0 and len(cells) > max_cells:
        stride = max(1, math.ceil(len(cells) / max_cells))
        render_cells = cells[::stride]
    render_cell_ids = {int(cell.get("id", -1)) for cell in render_cells}

    radius = max(0.7, min(3.2, (width * height / max(1, len(render_cells))) ** 0.5 * 0.23))
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" data-projection="{projection}" data-renderer="terrain-v1" data-contours="{str(contours).lower()}">',
        f"<title>{html.escape(str(world.get('name', 'magic-geo world')))} {projection} causal terrain map</title>",
        "<defs>",
        '<filter id="terrain-soften" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="0.08"/></filter>',
        "</defs>",
        '<rect width="100%" height="100%" fill="#173b56"/>',
    ]
    if projection == "orthographic":
        r = min(width, height) * 0.47
        lines.append(
            f'<circle cx="{width * 0.5:.2f}" cy="{height * 0.5:.2f}" r="{r:.2f}" '
            'fill="#173b56" stroke="#8fb6c6" stroke-width="1.2"/>'
        )

    for cell in render_cells:
        point = projected_cell(cell)
        if point is None:
            continue
        x, y = point
        fill, stroke, stroke_width, opacity = terrain_style(cell)
        lines.append(
            f'<circle class="terrain-cell" cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{stroke_width}" opacity="{opacity:.2f}" filter="url(#terrain-soften)"/>'
        )

    if contours:
        contour_interval = max(50.0, float(contour_interval_m))
        land_elevations = [
            float(cell.get("elevation_m", 0.0))
            for cell in render_cells
            if not cell.get("is_water") and float(cell.get("elevation_m", 0.0)) > contour_interval
        ]
        if land_elevations:
            first_level = math.ceil(min(land_elevations) / contour_interval) * contour_interval
            last_level = math.floor(max(land_elevations) / contour_interval) * contour_interval
            contour_levels = [
                first_level + contour_interval * index
                for index in range(int(max(0.0, (last_level - first_level) / contour_interval)) + 1)
            ]
            lines.append(f'<g class="terrain-contours" data-contour-interval-m="{contour_interval:.0f}">')
            for cell in render_cells:
                try:
                    cell_id = int(cell["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                if cell.get("is_water"):
                    continue
                elevation = float(cell.get("elevation_m", 0.0))
                point_a = projected_cell(cell)
                if point_a is None:
                    continue
                x1, y1 = point_a
                for neighbor_id_raw in cell.get("neighbors", []):
                    try:
                        neighbor_id = int(neighbor_id_raw)
                    except (TypeError, ValueError):
                        continue
                    if neighbor_id <= cell_id or neighbor_id not in render_cell_ids:
                        continue
                    neighbor = cell_by_id.get(neighbor_id)
                    if not neighbor or neighbor.get("is_water"):
                        continue
                    neighbor_elevation = float(neighbor.get("elevation_m", 0.0))
                    low = min(elevation, neighbor_elevation)
                    high = max(elevation, neighbor_elevation)
                    if high < contour_interval or high == low:
                        continue
                    crossed_levels = [level for level in contour_levels if low <= level <= high]
                    if not crossed_levels:
                        continue
                    point_b = projected_cell(neighbor)
                    if point_b is None:
                        continue
                    x2, y2 = point_b
                    if projection == "equirectangular" and abs(x1 - x2) > width * 0.55:
                        continue
                    for level in crossed_levels:
                        major = int(round(level / contour_interval)) % 2 == 0
                        stroke = "#f4e7b8" if major else "#c9b77e"
                        stroke_width = 0.62 if major else 0.38
                        opacity = 0.54 if major else 0.34
                        lines.append(
                            f'<line class="terrain-contour {"terrain-contour-major" if major else "terrain-contour-minor"}" '
                            f'data-elevation-m="{level:.0f}" x1="{x1:.2f}" y1="{y1:.2f}" '
                            f'x2="{x2:.2f}" y2="{y2:.2f}" stroke="{stroke}" '
                            f'stroke-width="{stroke_width:.2f}" stroke-opacity="{opacity:.2f}" '
                            'stroke-linecap="round"/>'
                        )
            lines.append("</g>")

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
        x1, y1 = point_a
        x2, y2 = point_b
        if projection == "equirectangular" and abs(x1 - x2) > width * 0.55:
            continue
        color = "#f0d38a" if route.get("type") != "coastal_sea" else "#9bd3df"
        lines.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{color}" stroke-width="1.15" stroke-opacity="0.78"/>'
        )

    for site in sacred_areas:
        cell = cell_by_id.get(int(site.get("cell_id", -1)))
        if not cell:
            continue
        point = projected_cell(cell)
        if point is None:
            continue
        x, y = point
        size = 4.0 + 3.0 * float(site.get("significance", 0.0))
        points = f"{x:.2f},{y - size:.2f} {x - size:.2f},{y + size:.2f} {x + size:.2f},{y + size:.2f}"
        lines.append(
            f'<polygon points="{points}" fill="#fff0a6" stroke="#6f4c1e" stroke-width="0.95" '
            f'stroke-opacity="0.9"><title>{html.escape(str(site.get("type", "sacred area")))}</title></polygon>'
        )

    for ruin in ruins:
        cell = cell_by_id.get(int(ruin.get("cell_id", -1)))
        if not cell:
            continue
        point = projected_cell(cell)
        if point is None:
            continue
        x, y = point
        size = 3.6 + 2.8 * float(ruin.get("significance", 0.0))
        lines.append(
            f'<rect x="{x - size / 2.0:.2f}" y="{y - size / 2.0:.2f}" width="{size:.2f}" height="{size:.2f}" '
            f'fill="#8b6d5c" stroke="#2b1f17" stroke-width="0.9" transform="rotate(45 {x:.2f} {y:.2f})">'
            f'<title>{html.escape(str(ruin.get("type", "ruin")))}</title></rect>'
        )

    for settlement in settlements:
        cell = cell_by_id.get(int(settlement.get("cell_id", -1)))
        if not cell:
            continue
        point = projected_cell(cell)
        if point is None:
            continue
        x, y = point
        color = settlement_colors.get(str(settlement.get("type", "frontier_town")), "#f0e6bd")
        size = 2.7 + 4.2 * float(settlement.get("score", 0.0))
        lines.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{size:.2f}" fill="{color}" '
            f'stroke="#2b1f17" stroke-width="1.15"/>'
        )

    if labels:
        labeled = sorted(settlements, key=lambda item: float(item.get("score", 0.0)), reverse=True)[:24]
        for settlement in labeled:
            cell = cell_by_id.get(int(settlement.get("cell_id", -1)))
            if not cell:
                continue
            point = projected_cell(cell)
            if point is None:
                continue
            x, y = point
            kind = str(settlement.get("type", "settlement")).replace("_", " ").title()
            text = html.escape(f"{kind} {settlement.get('id', '')}".strip())
            lines.append(
                f'<text x="{x + 7.0:.2f}" y="{y - 7.0:.2f}" font-family="serif" font-size="10" '
                f'fill="#f7f0cf" stroke="#1b2430" stroke-width="2.4" paint-order="stroke">{text}</text>'
            )

    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
