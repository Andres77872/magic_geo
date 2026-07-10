from __future__ import annotations

from typing import Any


TEXTURE_FRACTIONS = {
    "sand": (0.82, 0.10, 0.08),
    "loamy_sand": (0.74, 0.16, 0.10),
    "sandy_loam": (0.62, 0.26, 0.12),
    "loam": (0.42, 0.40, 0.18),
    "silt_loam": (0.20, 0.62, 0.18),
    "clay_loam": (0.30, 0.34, 0.36),
    "clay": (0.18, 0.32, 0.50),
    "peat": (0.12, 0.70, 0.18),
    "volcanic_ash": (0.56, 0.34, 0.10),
    "alluvial_silt": (0.18, 0.68, 0.14),
    "saline_crust": (0.35, 0.45, 0.20),
    "glacial_till": (0.48, 0.32, 0.20),
}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _lithology_ph(lithology: str) -> float:
    return {
        "granite": 5.9,
        "basalt": 6.7,
        "volcanic": 6.8,
        "limestone": 7.8,
        "sandstone": 6.2,
        "shale": 6.7,
        "metamorphic": 6.4,
    }.get(lithology, 6.5)


def _texture_factor(texture: str) -> float:
    return {
        "sand": 0.22,
        "loamy_sand": 0.30,
        "sandy_loam": 0.42,
        "loam": 0.55,
        "silt_loam": 0.72,
        "clay_loam": 0.68,
        "clay": 0.76,
        "peat": 0.38,
        "volcanic_ash": 0.48,
        "alluvial_silt": 0.70,
        "saline_crust": 0.58,
        "glacial_till": 0.52,
    }.get(texture, 0.0)


def _parent_material(lithology: str, landform: str, sediment: float) -> str:
    if landform in {"moraine", "glacial_lake", "ice_field", "fjord"}:
        return "glacial_till"
    if landform in {"river_valley", "delta", "floodplain"} or sediment >= 1.5:
        return "alluvium"
    if landform in {"coastal_plain", "beach", "barrier_bar", "barrier_island"}:
        return "marine_sediment"
    if lithology == "volcanic":
        return "volcanic_ash"
    if lithology in {"sandstone", "shale", "limestone"}:
        return "sedimentary_regolith"
    if lithology in {"granite", "metamorphic"}:
        return "crystalline_regolith"
    if lithology == "basalt":
        return "mafic_regolith"
    return "mixed_regolith"


def _profile_class(
    soil_type: str,
    texture: str,
    salinity: float,
    drainage: float,
    moisture: float,
    development: float,
    parent_material: str,
) -> str:
    if salinity >= 0.55:
        return "saline_arid_profile"
    if soil_type == "wetland" or texture == "peat" or (drainage <= 0.25 and moisture >= 0.60):
        return "histic_wetland_profile"
    if parent_material == "glacial_till":
        return "glacial_young_profile"
    if parent_material == "alluvium":
        return "alluvial_profile"
    if parent_material == "volcanic_ash":
        return "volcanic_andic_profile"
    if development >= 0.62:
        return "mature_weathered_profile"
    if development <= 0.25:
        return "thin_weakly_developed_profile"
    return "moderately_developed_profile"


def _texture_fractions(texture: str, horizon_name: str) -> tuple[float, float, float]:
    sand, silt, clay = TEXTURE_FRACTIONS.get(texture, (0.42, 0.40, 0.18))
    if horizon_name == "O":
        sand *= 0.35
        silt = max(silt, 0.52)
        clay *= 0.65
    elif horizon_name == "B":
        clay = min(0.70, clay + 0.08)
        sand = max(0.05, sand - 0.05)
    elif horizon_name == "C":
        clay = max(0.04, clay - 0.04)
        sand = min(0.90, sand + 0.06)
    total = max(0.001, sand + silt + clay)
    return sand / total, silt / total, clay / total


def _horizon_thicknesses(depth: float, organic: float, development: float, soil_type: str) -> list[tuple[str, float]]:
    remaining = max(0.0, depth)
    horizons: list[tuple[str, float]] = []
    if remaining <= 0.0:
        return horizons

    has_organic_horizon = organic >= 0.12 or soil_type == "wetland"
    if has_organic_horizon and remaining > 0.12:
        thickness = min(max(depth * 0.10, 0.04), 0.18, remaining * 0.35)
        horizons.append(("O", thickness))
        remaining -= thickness

    if remaining > 0.0:
        a_thickness = min(max(depth * 0.20, 0.06), 0.42, remaining)
        if remaining - a_thickness < 0.08:
            a_thickness = remaining
        horizons.append(("A", a_thickness))
        remaining -= a_thickness

    if remaining > 0.12 and development >= 0.22:
        b_thickness = min(max(depth * 0.34, 0.10), remaining * 0.72)
        horizons.append(("B", b_thickness))
        remaining -= b_thickness

    if remaining > 0.0:
        if remaining < 0.04 and horizons:
            last_name, last_thickness = horizons[-1]
            horizons[-1] = (last_name, last_thickness + remaining)
        else:
            horizons.append(("C", remaining))
    return horizons


def _neighbor_relief(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> float:
    elevation = float(cell.get("elevation_m", 0.0))
    relief = 0.0
    for neighbor_id in cell.get("neighbors", []):
        neighbor = cells_by_id.get(int(neighbor_id))
        if neighbor is None:
            continue
        relief = max(relief, abs(elevation - float(neighbor.get("elevation_m", elevation))))
    return _clamp(relief / 1800.0, 0.0, 1.0)


def _sorted_eras(world: dict[str, Any]) -> list[dict[str, Any]]:
    eras = world.get("historical_eras", [])
    if not isinstance(eras, list) or not eras:
        return [
            {
                "id": 0,
                "start_year_bp": 1.0,
                "end_year_bp": 0.0,
                "dominant_process": "undated",
            }
        ]
    return sorted(
        eras,
        key=lambda era: (
            -float(era.get("start_year_bp", 0.0)),
            int(era.get("id", 0)),
        ),
    )


def _classify_texture(
    lithology: str,
    soil_type: str,
    landform: str,
    salinity: float,
    organic: float,
    aridity: float,
    sediment: float,
    fertility: float,
) -> str:
    if salinity >= 0.62:
        return "saline_crust"
    if landform in {"moraine", "glacial_lake", "ice_field", "fjord"} or soil_type == "tundra":
        return "glacial_till"
    if landform in {"river_valley", "delta", "floodplain"} or soil_type == "alluvial":
        return "alluvial_silt" if sediment >= 0.35 else "silt_loam"
    if soil_type == "wetland" or organic >= 0.18:
        return "peat"
    if lithology == "volcanic":
        return "volcanic_ash"
    if lithology == "sandstone":
        return "sand" if aridity >= 0.72 else "sandy_loam"
    if lithology in {"shale", "limestone"}:
        return "clay" if aridity < 0.35 else "clay_loam"
    if lithology == "basalt":
        return "loam"
    if lithology == "granite":
        return "sandy_loam"
    if sediment >= 1.0 and fertility >= 0.45:
        return "silt_loam"
    return "loam"


def enrich_world_with_soil_diagnostics(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        summary = world.setdefault("summary", {})
        summary["soil_diagnostic_cell_count"] = 0
        summary["soil_texture_counts"] = {}
        summary["soil_profile_count"] = 0
        summary["soil_horizon_count"] = 0
        summary["soil_profile_history_count"] = 0
        summary["soil_pedogenesis_step_count"] = 0
        summary["total_soil_production_m"] = 0.0
        summary["total_soil_erosion_loss_m"] = 0.0
        summary["mean_pedogenic_weathering_index"] = 0.0
        summary["mean_pedogenic_leaching_index"] = 0.0
        summary["mean_pedogenic_bioturbation_index"] = 0.0
        summary["mean_horizon_differentiation_index"] = 0.0
        summary["mean_pedogenic_flux_index"] = 0.0
        summary["high_erosion_pedogenesis_count"] = 0
        summary["soil_profile_class_counts"] = {}
        world["soil_profiles"] = []
        world["soil_horizons"] = []
        world["soil_profile_histories"] = []
        return world

    cells_by_id = {int(cell.get("id", index)): cell for index, cell in enumerate(cells)}
    soil_profiles: list[dict[str, Any]] = []
    soil_horizons: list[dict[str, Any]] = []
    texture_counts: dict[str, int] = {}
    profile_class_counts: dict[str, int] = {}
    soil_count = 0
    drainage_sum = 0.0
    moisture_sum = 0.0
    ph_sum = 0.0
    organic_sum = 0.0
    salinity_sum = 0.0
    erodibility_sum = 0.0
    profile_sum = 0.0
    saline_count = 0
    erodible_count = 0
    waterlogged_count = 0
    profile_depth_sum = 0.0
    horizon_count_sum = 0.0
    topsoil_organic_sum = 0.0
    weathering_sum = 0.0
    leaching_sum = 0.0
    bioturbation_sum = 0.0
    mature_profile_count = 0
    shallow_profile_count = 0

    for cell in cells:
        water_body = str(cell.get("water_body_type", "land"))
        soil_type = str(cell.get("soil_type", "none"))
        depth = max(0.0, float(cell.get("soil_depth_m", 0.0)))
        fertility = _clamp(float(cell.get("fertility", 0.0)), 0.0, 1.0)
        is_soil = water_body == "land" and soil_type != "none" and depth > 0.0

        if not is_soil:
            cell["soil_texture_class"] = "none"
            cell["soil_drainage_index"] = 0.0
            cell["soil_moisture_index"] = 0.0
            cell["soil_ph"] = 7.0
            cell["soil_organic_matter_fraction"] = 0.0
            cell["soil_salinity_index"] = 0.0
            cell["soil_erodibility_index"] = 0.0
            cell["soil_profile_development_index"] = 0.0
            cell["soil_profile_id"] = -1
            cell["soil_horizon_count"] = 0
            texture_counts["none"] = texture_counts.get("none", 0) + 1
            continue

        lithology = str(cell.get("lithology", "unknown"))
        landform = str(cell.get("landform", "stable_lowland"))
        relief = _neighbor_relief(cell, cells_by_id)
        precipitation = max(0.0, float(cell.get("precipitation_mm_y", 0.0)))
        runoff = max(0.0, float(cell.get("runoff_mm_y", 0.0)))
        temperature = float(cell.get("temperature_c", 0.0))
        sediment = max(0.0, float(cell.get("sediment_thickness_m", 0.0)))
        erosion = max(0.0, float(cell.get("erosion_rate", 0.0)))
        seasonal_aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)), 0.0, 1.0)
        closed_basin = bool(cell.get("is_closed_basin", False))
        saline_water = water_body == "saline_basin" or str(cell.get("depression_policy", "")) == "preserve_geologic_sink"

        wetness = _clamp(precipitation / 1600.0 * 0.55 + runoff / 900.0 * 0.25 + (0.20 if bool(cell.get("is_river", False)) else 0.0), 0.0, 1.0)
        aridity = _clamp(seasonal_aridity * 0.65 + (1.0 - wetness) * 0.35, 0.0, 1.0)
        salinity = _clamp(
            (0.48 if saline_water else 0.0)
            + (0.24 if closed_basin else 0.0)
            + max(0.0, aridity - 0.55) * 0.70
            + (0.10 if soil_type == "arid" else 0.0)
            - wetness * 0.18,
            0.0,
            1.0,
        )
        temperature_factor = _clamp((temperature + 8.0) / 32.0, 0.0, 1.0)
        cool_storage = _clamp((12.0 - temperature) / 24.0, 0.0, 0.45)
        organic = _clamp(
            0.018
            + fertility * 0.055
            + wetness * 0.065
            + _clamp(depth / 5.0, 0.0, 1.0) * 0.035
            + cool_storage
            - salinity * 0.045
            - relief * 0.030,
            0.0,
            0.35,
        )
        texture = _classify_texture(lithology, soil_type, landform, salinity, organic, aridity, sediment, fertility)
        sandy_bonus = 0.18 if texture in {"sand", "loamy_sand", "sandy_loam", "volcanic_ash"} else 0.0
        clay_penalty = 0.18 if texture in {"clay", "clay_loam", "alluvial_silt", "peat"} else 0.0
        drainage = _clamp(
            0.42
            + relief * 0.32
            + sandy_bonus
            - clay_penalty
            - wetness * 0.22
            - (0.18 if landform in {"river_valley", "glacial_lake"} else 0.0)
            - (0.25 if soil_type == "wetland" else 0.0),
            0.0,
            1.0,
        )
        moisture = _clamp(wetness * 0.74 + (1.0 - drainage) * 0.20 + (0.08 if soil_type == "wetland" else 0.0), 0.0, 1.0)
        soil_ph = _clamp(_lithology_ph(lithology) + salinity * 1.20 - organic * 2.40 + aridity * 0.35 - wetness * 0.18, 3.8, 9.2)
        erodibility = _clamp(
            _texture_factor(texture) * 0.48
            + relief * 0.24
            + _clamp(runoff / 1200.0, 0.0, 1.0) * 0.15
            + _clamp(erosion * 90.0, 0.0, 1.0) * 0.10
            - organic * 0.34
            - fertility * 0.08,
            0.0,
            1.0,
        )
        profile = _clamp(
            depth / 5.0 * 0.34
            + fertility * 0.18
            + temperature_factor * wetness * 0.22
            + min(1.0, sediment / 4.0) * 0.10
            + max(0.0, 1.0 - relief) * 0.16
            - salinity * 0.10
            - (0.18 if landform in {"moraine", "glacial_lake", "ice_field"} else 0.0),
            0.0,
            1.0,
        )
        parent_material = _parent_material(lithology, landform, sediment)
        profile_class = _profile_class(soil_type, texture, salinity, drainage, moisture, profile, parent_material)
        weathering = _clamp(profile * 0.46 + temperature_factor * wetness * 0.22 + fertility * 0.16 + min(1.0, depth / 3.0) * 0.16 - salinity * 0.10, 0.0, 1.0)
        leaching = _clamp(wetness * 0.58 + drainage * 0.24 + temperature_factor * 0.10 - salinity * 0.22 - aridity * 0.12, 0.0, 1.0)
        bioturbation = _clamp(fertility * 0.38 + organic * 1.60 + moisture * 0.20 + temperature_factor * 0.18 - salinity * 0.18 - relief * 0.12, 0.0, 1.0)
        profile_age = max(0.0, depth * 18.0 + profile * 36.0 + max(0.0, 1.0 - relief) * 16.0 - erosion * 120.0)

        cell["soil_texture_class"] = texture
        cell["soil_drainage_index"] = round(drainage, 6)
        cell["soil_moisture_index"] = round(moisture, 6)
        cell["soil_ph"] = round(soil_ph, 6)
        cell["soil_organic_matter_fraction"] = round(organic, 6)
        cell["soil_salinity_index"] = round(salinity, 6)
        cell["soil_erodibility_index"] = round(erodibility, 6)
        cell["soil_profile_development_index"] = round(profile, 6)

        profile_id = len(soil_profiles)
        horizon_ids: list[int] = []
        top_depth = 0.0
        for sequence_index, (horizon_name, horizon_thickness) in enumerate(_horizon_thicknesses(depth, organic, profile, soil_type)):
            bottom_depth = top_depth + horizon_thickness
            mid_fraction = _clamp((top_depth + bottom_depth) / max(0.001, depth * 2.0), 0.0, 1.0)
            sand_fraction, silt_fraction, clay_fraction = _texture_fractions(texture, horizon_name)
            horizon_organic = _clamp(organic * (1.85 if horizon_name == "O" else 1.0 if horizon_name == "A" else 0.38 if horizon_name == "B" else 0.12), 0.0, 0.70)
            horizon_ph = _clamp(soil_ph + (0.20 if horizon_name == "C" else -0.12 if horizon_name == "O" else 0.0) + salinity * mid_fraction * 0.18, 3.5, 9.5)
            horizon_weathering = _clamp(weathering * (1.0 - mid_fraction * 0.48) + (0.10 if horizon_name == "B" else 0.0), 0.0, 1.0)
            horizon_id = len(soil_horizons)
            soil_horizons.append(
                {
                    "id": horizon_id,
                    "soil_profile_id": profile_id,
                    "cell_id": int(cell.get("id", -1)),
                    "horizon_name": horizon_name,
                    "sequence_index": sequence_index,
                    "top_depth_m": round(top_depth, 6),
                    "bottom_depth_m": round(bottom_depth, 6),
                    "thickness_m": round(horizon_thickness, 6),
                    "texture_class": texture,
                    "sand_fraction": round(sand_fraction, 6),
                    "silt_fraction": round(silt_fraction, 6),
                    "clay_fraction": round(clay_fraction, 6),
                    "organic_matter_fraction": round(horizon_organic, 6),
                    "ph": round(horizon_ph, 6),
                    "carbonate_index": round(_clamp((soil_ph - 6.9) / 2.3 + salinity * 0.20, 0.0, 1.0), 6),
                    "salinity_index": round(_clamp(salinity * (0.78 + mid_fraction * 0.32), 0.0, 1.0), 6),
                    "root_density_index": round(_clamp((1.0 - mid_fraction) * 0.72 + fertility * 0.20 + moisture * 0.08 - salinity * 0.18, 0.0, 1.0), 6),
                    "weathering_index": round(horizon_weathering, 6),
                }
            )
            horizon_ids.append(horizon_id)
            top_depth = bottom_depth

        soil_profiles.append(
            {
                "id": profile_id,
                "cell_id": int(cell.get("id", -1)),
                "soil_type": soil_type,
                "texture_class": texture,
                "lithology": lithology,
                "landform": landform,
                "parent_material": parent_material,
                "profile_class": profile_class,
                "horizon_ids": horizon_ids,
                "horizon_count": len(horizon_ids),
                "total_depth_m": round(depth, 6),
                "profile_age_ka": round(profile_age, 6),
                "drainage_index": round(drainage, 6),
                "moisture_index": round(moisture, 6),
                "ph": round(soil_ph, 6),
                "organic_matter_fraction": round(organic, 6),
                "salinity_index": round(salinity, 6),
                "erodibility_index": round(erodibility, 6),
                "development_index": round(profile, 6),
                "weathering_index": round(weathering, 6),
                "leaching_index": round(leaching, 6),
                "bioturbation_index": round(bioturbation, 6),
            }
        )
        cell["soil_profile_id"] = profile_id
        cell["soil_horizon_count"] = len(horizon_ids)

        texture_counts[texture] = texture_counts.get(texture, 0) + 1
        profile_class_counts[profile_class] = profile_class_counts.get(profile_class, 0) + 1
        soil_count += 1
        drainage_sum += drainage
        moisture_sum += moisture
        ph_sum += soil_ph
        organic_sum += organic
        salinity_sum += salinity
        erodibility_sum += erodibility
        profile_sum += profile
        saline_count += 1 if salinity >= 0.55 else 0
        erodible_count += 1 if erodibility >= 0.65 else 0
        waterlogged_count += 1 if drainage <= 0.25 and moisture >= 0.60 else 0
        profile_depth_sum += depth
        horizon_count_sum += len(horizon_ids)
        topsoil_organic_sum += float(soil_horizons[horizon_ids[0]]["organic_matter_fraction"]) if horizon_ids else 0.0
        weathering_sum += weathering
        leaching_sum += leaching
        bioturbation_sum += bioturbation
        mature_profile_count += 1 if profile >= 0.62 else 0
        shallow_profile_count += 1 if depth <= 0.55 else 0

    soil_profile_histories: list[dict[str, Any]] = []
    eras = _sorted_eras(world)
    pedogenic_weathering_sum = 0.0
    pedogenic_leaching_sum = 0.0
    pedogenic_bioturbation_sum = 0.0
    horizon_differentiation_sum = 0.0
    pedogenic_flux_sum = 0.0
    total_soil_production = 0.0
    total_erosion_loss = 0.0
    high_erosion_pedogenesis_count = 0

    for profile_record in soil_profiles:
        profile_id = int(profile_record.get("id", -1))
        cell_id = int(profile_record.get("cell_id", -1))
        cell = cells_by_id.get(cell_id, {})
        total_depth = max(0.0, float(profile_record.get("total_depth_m", 0.0)))
        profile_age = max(0.0, float(profile_record.get("profile_age_ka", 0.0)))
        drainage = _clamp(float(profile_record.get("drainage_index", 0.0)), 0.0, 1.0)
        moisture = _clamp(float(profile_record.get("moisture_index", 0.0)), 0.0, 1.0)
        soil_ph = _clamp(float(profile_record.get("ph", 7.0)), 3.5, 9.5)
        organic = _clamp(float(profile_record.get("organic_matter_fraction", 0.0)), 0.0, 1.0)
        salinity = _clamp(float(profile_record.get("salinity_index", 0.0)), 0.0, 1.0)
        erodibility = _clamp(float(profile_record.get("erodibility_index", 0.0)), 0.0, 1.0)
        development = _clamp(float(profile_record.get("development_index", 0.0)), 0.0, 1.0)
        weathering = _clamp(float(profile_record.get("weathering_index", 0.0)), 0.0, 1.0)
        leaching = _clamp(float(profile_record.get("leaching_index", 0.0)), 0.0, 1.0)
        bioturbation = _clamp(float(profile_record.get("bioturbation_index", 0.0)), 0.0, 1.0)
        horizon_count = max(0, int(profile_record.get("horizon_count", 0)))
        relief = _neighbor_relief(cell, cells_by_id) if cell else 0.0
        runoff = _clamp(float(cell.get("runoff_mm_y", 0.0)) / 1200.0, 0.0, 1.0) if cell else 0.0
        erosion_rate = _clamp(float(cell.get("erosion_rate", 0.0)) * 90.0, 0.0, 1.0) if cell else 0.0
        age_fraction = _clamp(profile_age / 85.0, 0.0, 1.0)
        initial_depth = total_depth * _clamp(
            0.34 + age_fraction * 0.18 + development * 0.12 - erodibility * 0.08,
            0.18,
            0.86,
        )
        previous_depth = initial_depth
        steps: list[dict[str, Any]] = []
        history_soil_production = 0.0
        history_erosion_loss = 0.0
        step_weathering_sum = 0.0
        step_leaching_sum = 0.0
        step_bioturbation_sum = 0.0
        step_differentiation_sum = 0.0
        step_flux_sum = 0.0
        high_erosion = False

        for index, era in enumerate(eras):
            stage_index = index + 1
            progress = stage_index / max(1, len(eras))
            start_depth = previous_depth
            end_depth = initial_depth + (total_depth - initial_depth) * progress
            erosion_pressure = _clamp(
                erodibility * 0.42
                + relief * 0.20
                + runoff * 0.18
                + erosion_rate * 0.14
                + (1.0 - organic) * 0.06,
                0.0,
                1.0,
            )
            era_span_ky = max(0.001, (float(era.get("start_year_bp", 0.0)) - float(era.get("end_year_bp", 0.0))) / 1000.0)
            erosion_loss = total_depth * erosion_pressure * (0.0035 + 0.0015 * era_span_ky)
            soil_production = max(0.0, end_depth - start_depth + erosion_loss)
            organic_accumulation = _clamp(
                organic * 1.45 + bioturbation * 0.18 + moisture * 0.14 - salinity * 0.18 - erosion_pressure * 0.08,
                0.0,
                1.0,
            )
            clay_translocation = _clamp(
                leaching * 0.40 + development * 0.24 + moisture * 0.14 + (1.0 - drainage) * 0.12 + progress * 0.10,
                0.0,
                1.0,
            )
            carbonate_mobilization = _clamp(
                max(0.0, soil_ph - 6.6) / 2.8 * 0.30 + salinity * 0.26 + leaching * 0.22 + (1.0 - moisture) * 0.10,
                0.0,
                1.0,
            )
            salinization = _clamp(
                salinity * 0.62 + (1.0 - leaching) * 0.18 + (1.0 - moisture) * 0.12 + max(0.0, soil_ph - 7.2) / 2.3 * 0.08,
                0.0,
                1.0,
            )
            horizon_differentiation = _clamp(
                development * 0.36
                + min(1.0, horizon_count / 4.0) * 0.20
                + weathering * 0.16
                + clay_translocation * 0.14
                + progress * 0.14,
                0.0,
                1.0,
            )
            pedogenic_flux = _clamp(
                soil_production / max(0.001, total_depth) * 0.32
                + weathering * 0.20
                + leaching * 0.16
                + bioturbation * 0.14
                + horizon_differentiation * 0.10
                + organic_accumulation * 0.08,
                0.0,
                1.0,
            )
            step_weathering = _clamp(weathering * (0.74 + progress * 0.26), 0.0, 1.0)
            step_leaching = _clamp(leaching * (0.78 + progress * 0.22), 0.0, 1.0)
            step_bioturbation = _clamp(bioturbation * (0.82 + progress * 0.18), 0.0, 1.0)
            steps.append(
                {
                    "era_id": int(era.get("id", -1)),
                    "stage_index": stage_index,
                    "start_year_bp": round(float(era.get("start_year_bp", 0.0)), 6),
                    "end_year_bp": round(float(era.get("end_year_bp", 0.0)), 6),
                    "start_depth_m": round(start_depth, 6),
                    "end_depth_m": round(end_depth, 6),
                    "soil_production_m": round(soil_production, 6),
                    "erosion_loss_m": round(erosion_loss, 6),
                    "weathering_index": round(step_weathering, 6),
                    "leaching_index": round(step_leaching, 6),
                    "bioturbation_index": round(step_bioturbation, 6),
                    "organic_accumulation_index": round(organic_accumulation, 6),
                    "horizon_differentiation_index": round(horizon_differentiation, 6),
                    "clay_translocation_index": round(clay_translocation, 6),
                    "carbonate_mobilization_index": round(carbonate_mobilization, 6),
                    "salinization_index": round(salinization, 6),
                    "erosion_pressure_index": round(erosion_pressure, 6),
                    "pedogenic_flux_index": round(pedogenic_flux, 6),
                }
            )
            previous_depth = end_depth
            history_soil_production += soil_production
            history_erosion_loss += erosion_loss
            step_weathering_sum += step_weathering
            step_leaching_sum += step_leaching
            step_bioturbation_sum += step_bioturbation
            step_differentiation_sum += horizon_differentiation
            step_flux_sum += pedogenic_flux
            if erosion_pressure >= 0.65:
                high_erosion = True

        if steps:
            steps[-1]["end_depth_m"] = round(total_depth, 6)
        step_divisor = len(steps) if steps else 1
        mean_weathering = step_weathering_sum / step_divisor if steps else 0.0
        mean_leaching = step_leaching_sum / step_divisor if steps else 0.0
        mean_bioturbation = step_bioturbation_sum / step_divisor if steps else 0.0
        mean_differentiation = step_differentiation_sum / step_divisor if steps else 0.0
        mean_flux = step_flux_sum / step_divisor if steps else 0.0
        soil_profile_histories.append(
            {
                "id": len(soil_profile_histories),
                "soil_profile_id": profile_id,
                "cell_id": cell_id,
                "horizon_ids": list(profile_record.get("horizon_ids", [])),
                "horizon_count": horizon_count,
                "parent_material": profile_record.get("parent_material", ""),
                "profile_class": profile_record.get("profile_class", ""),
                "initial_depth_m": round(initial_depth, 6),
                "final_depth_m": round(total_depth, 6),
                "final_profile_age_ka": round(profile_age, 6),
                "total_soil_production_m": round(history_soil_production, 6),
                "total_erosion_loss_m": round(history_erosion_loss, 6),
                "mean_weathering_index": round(_clamp(mean_weathering, 0.0, 1.0), 6),
                "mean_leaching_index": round(_clamp(mean_leaching, 0.0, 1.0), 6),
                "mean_bioturbation_index": round(_clamp(mean_bioturbation, 0.0, 1.0), 6),
                "mean_horizon_differentiation_index": round(_clamp(mean_differentiation, 0.0, 1.0), 6),
                "mean_pedogenic_flux_index": round(_clamp(mean_flux, 0.0, 1.0), 6),
                "high_erosion_pressure": bool(high_erosion),
                "step_count": len(steps),
                "steps": steps,
            }
        )
        profile_record["soil_profile_history_id"] = soil_profile_histories[-1]["id"]
        pedogenic_weathering_sum += mean_weathering
        pedogenic_leaching_sum += mean_leaching
        pedogenic_bioturbation_sum += mean_bioturbation
        horizon_differentiation_sum += mean_differentiation
        pedogenic_flux_sum += mean_flux
        total_soil_production += history_soil_production
        total_erosion_loss += history_erosion_loss
        if high_erosion:
            high_erosion_pedogenesis_count += 1

    world["soil_profiles"] = soil_profiles
    world["soil_horizons"] = soil_horizons
    world["soil_profile_histories"] = soil_profile_histories
    summary = world.setdefault("summary", {})
    summary["soil_diagnostic_cell_count"] = soil_count
    summary["soil_texture_counts"] = dict(sorted(texture_counts.items()))
    summary["soil_profile_count"] = len(soil_profiles)
    summary["soil_horizon_count"] = len(soil_horizons)
    summary["soil_profile_history_count"] = len(soil_profile_histories)
    summary["soil_pedogenesis_step_count"] = sum(int(history.get("step_count", 0)) for history in soil_profile_histories)
    summary["soil_profile_class_counts"] = dict(sorted(profile_class_counts.items()))
    divisor = float(soil_count) if soil_count else 1.0
    summary["mean_soil_drainage_index"] = round(drainage_sum / divisor, 6) if soil_count else 0.0
    summary["mean_soil_moisture_index"] = round(moisture_sum / divisor, 6) if soil_count else 0.0
    summary["mean_soil_ph"] = round(ph_sum / divisor, 6) if soil_count else 7.0
    summary["mean_soil_organic_matter_fraction"] = round(organic_sum / divisor, 6) if soil_count else 0.0
    summary["mean_soil_salinity_index"] = round(salinity_sum / divisor, 6) if soil_count else 0.0
    summary["mean_soil_erodibility_index"] = round(erodibility_sum / divisor, 6) if soil_count else 0.0
    summary["mean_soil_profile_development_index"] = round(profile_sum / divisor, 6) if soil_count else 0.0
    summary["saline_soil_cell_fraction"] = round(saline_count / divisor, 6) if soil_count else 0.0
    summary["high_erodibility_soil_fraction"] = round(erodible_count / divisor, 6) if soil_count else 0.0
    summary["waterlogged_soil_cell_fraction"] = round(waterlogged_count / divisor, 6) if soil_count else 0.0
    summary["mean_soil_profile_depth_m"] = round(profile_depth_sum / divisor, 6) if soil_count else 0.0
    summary["mean_soil_horizon_count"] = round(horizon_count_sum / divisor, 6) if soil_count else 0.0
    summary["mean_topsoil_organic_matter_fraction"] = round(topsoil_organic_sum / divisor, 6) if soil_count else 0.0
    summary["mean_soil_weathering_index"] = round(weathering_sum / divisor, 6) if soil_count else 0.0
    summary["mean_soil_leaching_index"] = round(leaching_sum / divisor, 6) if soil_count else 0.0
    summary["mean_soil_bioturbation_index"] = round(bioturbation_sum / divisor, 6) if soil_count else 0.0
    summary["mature_soil_profile_fraction"] = round(mature_profile_count / divisor, 6) if soil_count else 0.0
    summary["shallow_soil_profile_fraction"] = round(shallow_profile_count / divisor, 6) if soil_count else 0.0
    history_divisor = float(len(soil_profile_histories)) if soil_profile_histories else 1.0
    summary["total_soil_production_m"] = round(total_soil_production, 6)
    summary["total_soil_erosion_loss_m"] = round(total_erosion_loss, 6)
    summary["mean_pedogenic_weathering_index"] = (
        round(pedogenic_weathering_sum / history_divisor, 6) if soil_profile_histories else 0.0
    )
    summary["mean_pedogenic_leaching_index"] = (
        round(pedogenic_leaching_sum / history_divisor, 6) if soil_profile_histories else 0.0
    )
    summary["mean_pedogenic_bioturbation_index"] = (
        round(pedogenic_bioturbation_sum / history_divisor, 6) if soil_profile_histories else 0.0
    )
    summary["mean_horizon_differentiation_index"] = (
        round(horizon_differentiation_sum / history_divisor, 6) if soil_profile_histories else 0.0
    )
    summary["mean_pedogenic_flux_index"] = (
        round(pedogenic_flux_sum / history_divisor, 6) if soil_profile_histories else 0.0
    )
    summary["high_erosion_pedogenesis_count"] = high_erosion_pedogenesis_count
    return world
