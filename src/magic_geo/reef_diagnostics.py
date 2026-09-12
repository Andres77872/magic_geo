from __future__ import annotations

import math
from collections import Counter, deque
from typing import Any

from .climate_model_dispatch import ecology_uses_native_seasonal_climate

MARINE_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea"}
REEF_GROWTH_THRESHOLD = 0.46
REEF_THERMAL_MINIMUM_C = 4.0
REEF_THERMAL_MAXIMUM_C = 39.0
VOLCANIC_LANDFORMS = {"volcanic_arc", "island_arc", "ridge"}
REEF_COASTAL_FEATURE_TYPES = {"beach", "barrier_bar", "barrier_island", "coastal_cliff"}
REEF_LANDMASS_CLASSES = {"islet", "island", "large_island"}

LEGACY_REEF_MODEL = {
    "model": "heuristic_coastal_reef_v2",
    "thermal_eligibility": "annual_and_all_monthly_means_inside_existing_suitability_support",
    "minimum_temperature_c": REEF_THERMAL_MINIMUM_C,
    "maximum_temperature_c": REEF_THERMAL_MAXIMUM_C,
    "temperature_bounds": "exclusive",
    "monthly_temperature_count": 12,
    "missing_monthly_temperature_policy": "annual_only_if_field_absent",
    "invalid_monthly_temperature_policy": "ineligible",
    "bleaching_model": "legacy_energy_aridity_current_proxy_v1",
    "thermal_limits_scope": "empirical_model_support_not_universal_coral_survival_limits",
}
NATIVE_REEF_MODEL = {
    **LEGACY_REEF_MODEL,
    "model": "heuristic_coastal_reef_native_seasonal_v3",
    "bleaching_model": "not_modelled_no_reference_climatology",
    "bleaching_estimate_available": False,
    "bleaching_output_policy": "omit_cell_record_and_summary_legacy_risk_fields",
    "growth_model": "thermal_habitat_gated_existing_bonuses_without_bleaching_penalty",
    "remaining_growth_weights": "unchanged_without_renormalization",
    "climate_input_policy": "requires_known_native_identity_and_upstream_energy_enrichment",
}


def _matches_reef_model(value: Any, expected: dict[str, Any]) -> bool:
    if not isinstance(value, dict) or value.keys() != expected.keys():
        return False
    return all(
        value[key] == item
        and (type(item) not in (bool, int) or type(value[key]) is type(item))
        and (type(item) is not float or (isinstance(value[key], (int, float)) and not isinstance(value[key], bool)))
        for key, item in expected.items()
    )


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _marine_neighbors(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    neighbors: list[dict[str, Any]] = []
    for neighbor_id_raw in cell.get("neighbors", []):
        neighbor = cells_by_id.get(int(neighbor_id_raw))
        if neighbor is not None and str(neighbor.get("water_body_type", "land")) in MARINE_WATER_TYPES:
            neighbors.append(neighbor)
    return neighbors


def _land_neighbors(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    neighbors: list[dict[str, Any]] = []
    for neighbor_id_raw in cell.get("neighbors", []):
        neighbor = cells_by_id.get(int(neighbor_id_raw))
        if neighbor is not None and not bool(neighbor.get("is_water", False)):
            neighbors.append(neighbor)
    return neighbors


def _temperature_suitability(temperature_c: float) -> float:
    if temperature_c < REEF_THERMAL_MINIMUM_C:
        return 0.0
    if temperature_c < 18.0:
        return _clamp((temperature_c - 4.0) / 14.0) * 0.55
    return _clamp(1.0 - abs(temperature_c - 26.0) / 13.0)


def _thermal_habitat_eligible(cell: dict[str, Any]) -> bool:
    """Require the existing empirical curve to support persistent habitat.

    NOAA describes cold-water corals at 4--12 C and many shallow corals as
    growing best at 23--29 C, with 40 C tolerated only briefly:
    https://oceanexplorer.noaa.gov/ocean-fact/coral-water/
    https://oceanservice.noaa.gov/education/tutorial_corals/coral05_distribution.html
    The open (4, 39) C interval is this model's existing positive-suitability
    support, not a universal physiological limit. A monthly mean outside it
    cannot be offset by island, shelf, or fishery bonuses. Monthly means do
    not resolve brief extreme exposure or depth-specific water temperature.
    """
    annual = cell.get("temperature_c")
    monthly = cell.get("temperature_monthly_c", [annual] * 12)
    if not isinstance(monthly, list) or len(monthly) != 12:
        return False
    return all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and REEF_THERMAL_MINIMUM_C < value < REEF_THERMAL_MAXIMUM_C
        for value in [annual, *monthly]
    )


def _shallow_water_suitability(cell: dict[str, Any]) -> float:
    depth = max(0.0, float(cell.get("water_depth_m", 0.0)))
    water_body = str(cell.get("water_body_type", "land"))
    if water_body == "continental_shelf":
        return _clamp(1.0 - max(0.0, depth - 5.0) / 210.0)
    if water_body == "inland_sea":
        return _clamp(0.82 - max(0.0, depth - 5.0) / 260.0)
    return _clamp(0.42 - max(0.0, depth - 25.0) / 360.0)


def _coastal_feature_by_cell(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    by_cell: dict[int, dict[str, Any]] = {}
    coastal_features = world.get("coastal_features", [])
    if not isinstance(coastal_features, list):
        return by_cell
    for feature in coastal_features:
        if not isinstance(feature, dict):
            continue
        cell_id = int(feature.get("cell_id", -1))
        if cell_id >= 0:
            by_cell[cell_id] = feature
    return by_cell


def _settlements_by_cell(world: dict[str, Any]) -> dict[int, list[int]]:
    by_cell: dict[int, list[int]] = {}
    settlements = world.get("settlements", [])
    if not isinstance(settlements, list):
        return by_cell
    for settlement in settlements:
        if not isinstance(settlement, dict):
            continue
        settlement_id = int(settlement.get("id", -1))
        cell_id = int(settlement.get("cell_id", -1))
        if settlement_id >= 0 and cell_id >= 0:
            by_cell.setdefault(cell_id, []).append(settlement_id)
    return by_cell


def _fishery_records_by_cell(world: dict[str, Any]) -> dict[int, list[int]]:
    by_cell: dict[int, list[int]] = {}
    records = world.get("renewable_resource_records", [])
    if not isinstance(records, list):
        return by_cell
    for record in records:
        if not isinstance(record, dict) or str(record.get("resource_type", "")) != "fishery_productivity":
            continue
        record_id = int(record.get("id", -1))
        cell_id = int(record.get("cell_id", -1))
        if record_id >= 0 and cell_id >= 0:
            by_cell.setdefault(cell_id, []).append(record_id)
    return by_cell


def _sediment_stress(cell: dict[str, Any], land_neighbors: list[dict[str, Any]], coastal_features_by_cell: dict[int, dict[str, Any]]) -> float:
    river_pressure = 0.32 if any(bool(land.get("is_river", False)) for land in land_neighbors) else 0.0
    delta_pressure = 0.28 if any(str(land.get("landform", "")) in {"delta", "floodplain"} for land in land_neighbors) else 0.0
    runoff = max((float(land.get("runoff_mm_y", 0.0)) for land in land_neighbors), default=0.0)
    sediment_export = max(
        (
            float(
                land.get(
                    "fluvial_sediment_routed_outgoing_m",
                    land.get("sediment_export_m", 0.0),
                )
            )
            for land in land_neighbors
        ),
        default=0.0,
    )
    feature_supply = max(
        (
            float(coastal_features_by_cell.get(int(land.get("id", -1)), {}).get("sediment_supply_index", 0.0))
            for land in land_neighbors
        ),
        default=0.0,
    )
    local_sediment = _clamp(float(cell.get("sediment_thickness_m", 0.0)) / 4.0)
    return _clamp(
        river_pressure
        + delta_pressure
        + _clamp(runoff / 1300.0) * 0.18
        + _clamp(sediment_export / 2.0) * 0.18
        + feature_supply * 0.24
        + local_sediment * 0.10
    )


def _wave_exposure(cell: dict[str, Any], land_neighbors: list[dict[str, Any]], coastal_features_by_cell: dict[int, dict[str, Any]]) -> float:
    feature_waves = [
        float(coastal_features_by_cell.get(int(land.get("id", -1)), {}).get("wave_energy_index", 0.0))
        for land in land_neighbors
        if int(land.get("id", -1)) in coastal_features_by_cell
    ]
    if feature_waves:
        feature_wave = max(feature_waves)
    else:
        wind_speed = math.sqrt(float(cell.get("wind_east", 0.0)) ** 2 + float(cell.get("wind_north", 0.0)) ** 2)
        feature_wave = _clamp(wind_speed)
    return _clamp(feature_wave)


def _island_support(cell: dict[str, Any], land_neighbors: list[dict[str, Any]]) -> float:
    if not land_neighbors:
        return 0.0
    island = max((0.62 if str(land.get("island_class", "")) in REEF_LANDMASS_CLASSES else 0.0 for land in land_neighbors), default=0.0)
    volcanic = max(
        (
            max(
                _clamp(float(land.get("volcanic_potential_index", 0.0)) * 2.6),
                0.55 if str(land.get("landform", "")) in VOLCANIC_LANDFORMS else 0.0,
                0.42 if str(land.get("lithology", "")) in {"basalt", "andesite"} else 0.0,
            )
            for land in land_neighbors
        ),
        default=0.0,
    )
    young_coast = max((_clamp((120.0 - float(land.get("crust_age_ma", 120.0))) / 120.0) for land in land_neighbors), default=0.0)
    return _clamp(island * 0.40 + volcanic * 0.38 + young_coast * 0.22)


def _bleaching_risk(cell: dict[str, Any]) -> float:
    temperature = float(cell.get("temperature_c", 0.0))
    warm_stress = _clamp((temperature - 29.0) / 7.0)
    energy_stress = _clamp(float(cell.get("climate_energy_stress_index", 0.0)))
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    current_warmth = _clamp(float(cell.get("ocean_current_temperature_c", 0.0)) / 5.0)
    return _clamp(warm_stress * 0.44 + energy_stress * 0.24 + aridity * 0.16 + current_warmth * 0.16)


def _reef_growth_index(
    cell: dict[str, Any],
    land_neighbors: list[dict[str, Any]],
    coastal_features_by_cell: dict[int, dict[str, Any]],
    *, native_seasonal: bool = False,
) -> tuple[float, float, float, float, float | None]:
    if str(cell.get("water_body_type", "land")) not in MARINE_WATER_TYPES or not bool(cell.get("is_water", False)):
        return 0.0, 0.0, 0.0, 0.0, None if native_seasonal else 0.0
    if not land_neighbors:
        return 0.0, 0.0, 0.0, 0.0, None if native_seasonal else 0.0
    temperature = _temperature_suitability(float(cell.get("temperature_c", 0.0)))
    shallow = _shallow_water_suitability(cell)
    water_body = str(cell.get("water_body_type", "land"))
    shelf_bonus = 0.24 if water_body == "continental_shelf" else (0.14 if water_body == "inland_sea" else 0.04)
    island = _island_support(cell, land_neighbors)
    sediment = _sediment_stress(cell, land_neighbors, coastal_features_by_cell)
    wave = _wave_exposure(cell, land_neighbors, coastal_features_by_cell)
    # A repeating surface-temperature cycle has no independent local MMM or
    # exposure history. Do not label a missing bleaching estimate as zero risk.
    bleaching = None if native_seasonal else _bleaching_risk(cell)
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 60.0)
    wave_window = _clamp(1.0 - abs(wave - 0.42) / 0.58)
    fishery = _clamp(float(cell.get("fishery_productivity_index", 0.0)))
    growth = _clamp(
        temperature * 0.26
        + shallow * 0.25
        + shelf_bonus
        + island * 0.15
        + wave_window * 0.10
        + fishery * 0.08
        - sediment * 0.22
        - (bleaching * 0.16 if bleaching is not None else 0.0)
        - ice * 0.54
    )
    if not _thermal_habitat_eligible(cell):
        growth = 0.0
    return growth, sediment, wave, island, bleaching


def _reef_type(cell: dict[str, Any], land_neighbors: list[dict[str, Any]], coastal_features_by_cell: dict[int, dict[str, Any]]) -> str:
    temperature = float(cell.get("temperature_c", 0.0))
    if temperature < 18.0:
        return "cold_water_reef"
    feature_types = {
        str(coastal_features_by_cell.get(int(land.get("id", -1)), {}).get("type", ""))
        for land in land_neighbors
        if int(land.get("id", -1)) in coastal_features_by_cell
    }
    landmass_classes = {str(land.get("island_class", "")) for land in land_neighbors}
    land_neighbor_count = len(land_neighbors)
    if landmass_classes & {"islet", "island"} and land_neighbor_count <= 2:
        return "atoll_reef"
    if feature_types & {"barrier_bar", "barrier_island"}:
        return "barrier_reef"
    if land_neighbor_count >= 1:
        return "fringing_reef"
    return "patch_reef"


def _connected_components(candidate_ids: set[int], cells_by_id: dict[int, dict[str, Any]]) -> list[list[dict[str, Any]]]:
    components: list[list[dict[str, Any]]] = []
    remaining = set(candidate_ids)
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue: deque[int] = deque([start])
        component_ids = [start]
        while queue:
            current_id = queue.popleft()
            current = cells_by_id[current_id]
            for neighbor_id_raw in current.get("neighbors", []):
                neighbor_id = int(neighbor_id_raw)
                if neighbor_id not in remaining:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
                component_ids.append(neighbor_id)
        components.append([cells_by_id[cell_id] for cell_id in sorted(component_ids)])
    return components


def _centroid(component: list[dict[str, Any]]) -> tuple[float, float]:
    if not component:
        return 0.0, 0.0
    weight_sum = 0.0
    x_sum = 0.0
    y_sum = 0.0
    z_sum = 0.0
    for cell in component:
        weight = max(0.0, float(cell.get("area_km2", 0.0))) or 1.0
        lat = math.radians(float(cell.get("lat_deg", 0.0)))
        lon = math.radians(float(cell.get("lon_deg", 0.0)))
        cos_lat = math.cos(lat)
        x_sum += math.cos(lon) * cos_lat * weight
        y_sum += math.sin(lon) * cos_lat * weight
        z_sum += math.sin(lat) * weight
        weight_sum += weight
    if weight_sum <= 0.0:
        return 0.0, 0.0
    lon = math.degrees(math.atan2(y_sum / weight_sum, x_sum / weight_sum))
    hyp = math.hypot(x_sum / weight_sum, y_sum / weight_sum)
    lat = math.degrees(math.atan2(z_sum / weight_sum, hyp))
    return round(lat, 6), round(lon, 6)


def _enrich_reef_stage(world: dict[str, Any], *, available_port_links: bool = False) -> dict[str, Any]:
    native_seasonal = ecology_uses_native_seasonal_climate(world)
    model = NATIVE_REEF_MODEL if native_seasonal else LEGACY_REEF_MODEL
    if "reef_diagnostics_model" in world and not _matches_reef_model(world["reef_diagnostics_model"], model):
        # Explicitly migrate a known old reef diagnostic when a verified
        # native source replaces it; unknown metadata never grants a fallback.
        if not native_seasonal or not _matches_reef_model(world["reef_diagnostics_model"], LEGACY_REEF_MODEL):
            raise ValueError("reef diagnostics require exact known model metadata")
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world
    world["reef_diagnostics_model"] = dict(model)
    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    coastal_features_by_cell = _coastal_feature_by_cell(world)
    settlements_by_cell = _settlements_by_cell(world)
    fishery_records_by_cell = _fishery_records_by_cell(world)

    candidate_ids: set[int] = set()
    growth_sum = 0.0
    sediment_sum = 0.0
    wave_sum = 0.0
    island_sum = 0.0
    bleaching_sum = 0.0

    for cell in cells:
        land_neighbors = _land_neighbors(cell, cells_by_id)
        growth, sediment, wave, island, bleaching = _reef_growth_index(
            cell, land_neighbors, coastal_features_by_cell, native_seasonal=native_seasonal,
        )
        cell["reef_growth_index"] = round(growth, 6)
        cell["reef_sediment_stress_index"] = round(sediment, 6)
        cell["reef_wave_exposure_index"] = round(wave, 6)
        cell["reef_island_support_index"] = round(island, 6)
        if native_seasonal:
            cell.pop("reef_bleaching_risk_index", None)
        else:
            cell["reef_bleaching_risk_index"] = round(bleaching, 6)
        cell["reef_type"] = "none"
        cell["reef_system_id"] = -1
        if growth >= REEF_GROWTH_THRESHOLD:
            reef_type = _reef_type(cell, land_neighbors, coastal_features_by_cell)
            cell["reef_type"] = reef_type
            candidate_ids.add(int(cell.get("id", -1)))
        growth_sum += growth
        sediment_sum += sediment
        wave_sum += wave
        island_sum += island
        if bleaching is not None:
            bleaching_sum += bleaching

    records: list[dict[str, Any]] = []
    for component in _connected_components(candidate_ids, cells_by_id):
        reef_id = len(records)
        for cell in component:
            cell["reef_system_id"] = reef_id
        cell_ids = [int(cell.get("id", -1)) for cell in component]
        adjacent_land_neighbors = [
            neighbor
            for cell in component
            for neighbor in _land_neighbors(cell, cells_by_id)
        ]
        adjacent_marine_neighbors = [
            neighbor
            for cell in component
            for neighbor in _marine_neighbors(cell, cells_by_id)
        ]
        adjacent_landmass_ids = sorted(
            {
                int(land.get("landmass_id", -1))
                for land in adjacent_land_neighbors
                if int(land.get("landmass_id", -1)) >= 0
            }
        )
        marine_region_ids = sorted(
            {
                int(cell.get("marine_region_id", -1))
                for cell in component + adjacent_marine_neighbors
                if int(cell.get("marine_region_id", -1)) >= 0
            }
        )
        coastal_feature_ids = sorted(
            {
                int(coastal_features_by_cell[int(land.get("id", -1))].get("id", -1))
                for land in adjacent_land_neighbors
                if int(land.get("id", -1)) in coastal_features_by_cell
            }
        )
        settlement_ids = sorted(
            {
                settlement_id
                for land in adjacent_land_neighbors
                for settlement_id in settlements_by_cell.get(int(land.get("id", -1)), [])
            }
        )
        nearby_cell_ids = set(cell_ids) | {int(land.get("id", -1)) for land in adjacent_land_neighbors}
        port_site_ids = sorted(
            {
                int(cells_by_id[cell_id].get("port_site_id", -1))
                for cell_id in nearby_cell_ids
                if cell_id in cells_by_id
                and (not available_port_links or cells_by_id[cell_id]["port_site_selection_supported"])
                and int(cells_by_id[cell_id].get("port_site_id", -1)) >= 0
            }
        )
        fishery_resource_ids = sorted(
            {
                record_id
                for cell_id in cell_ids
                for record_id in fishery_records_by_cell.get(cell_id, [])
            }
        )
        volcanic_land_cell_count = sum(
            1
            for land in adjacent_land_neighbors
            if str(land.get("landform", "")) in VOLCANIC_LANDFORMS
            or float(land.get("volcanic_potential_index", 0.0)) >= 0.20
            or str(land.get("lithology", "")) in {"basalt", "andesite"}
        )
        type_counts = Counter(str(cell.get("reef_type", "patch_reef")) for cell in component)
        area_sum = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in component)
        centroid_lat, centroid_lon = _centroid(component)
        records.append(
            {
                "id": reef_id,
                "reef_type": _primary_key(type_counts, "patch_reef"),
                "cell_count": len(component),
                "cell_ids": cell_ids,
                "area_km2": round(area_sum, 6),
                "centroid_lat_deg": centroid_lat,
                "centroid_lon_deg": centroid_lon,
                "mean_reef_growth_index": round(sum(float(cell.get("reef_growth_index", 0.0)) for cell in component) / len(component), 6),
                "mean_reef_sediment_stress_index": round(sum(float(cell.get("reef_sediment_stress_index", 0.0)) for cell in component) / len(component), 6),
                "mean_reef_wave_exposure_index": round(sum(float(cell.get("reef_wave_exposure_index", 0.0)) for cell in component) / len(component), 6),
                "mean_reef_island_support_index": round(sum(float(cell.get("reef_island_support_index", 0.0)) for cell in component) / len(component), 6),
                **({"mean_reef_bleaching_risk_index": round(sum(float(cell.get("reef_bleaching_risk_index", 0.0)) for cell in component) / len(component), 6)} if not native_seasonal else {}),
                "mean_water_depth_m": round(sum(float(cell.get("water_depth_m", 0.0)) for cell in component) / len(component), 6),
                "mean_temperature_c": round(sum(float(cell.get("temperature_c", 0.0)) for cell in component) / len(component), 6),
                "mean_fishery_productivity_index": round(sum(float(cell.get("fishery_productivity_index", 0.0)) for cell in component) / len(component), 6),
                "adjacent_landmass_ids": adjacent_landmass_ids,
                "marine_region_ids": marine_region_ids,
                "coastal_feature_ids": coastal_feature_ids,
                "settlement_ids": settlement_ids,
                "port_site_ids": port_site_ids,
                **({"port_site_links_complete": all(cells_by_id[cid]["port_site_selection_supported"] for cid in nearby_cell_ids)} if available_port_links else {}),
                "fishery_resource_record_ids": fishery_resource_ids,
                "adjacent_volcanic_land_cell_count": volcanic_land_cell_count,
                "reef_type_counts": dict(sorted(type_counts.items())),
            }
        )

    type_counts = Counter(str(record.get("reef_type", "patch_reef")) for record in records)
    summary = world.setdefault("summary", {})
    cell_count = len(cells)
    summary["reef_system_count"] = len(records)
    summary["reef_cell_count"] = len(candidate_ids)
    summary["reef_total_area_km2"] = round(sum(float(record.get("area_km2", 0.0)) for record in records), 6)
    summary["mean_reef_growth_index"] = round(growth_sum / cell_count, 6)
    summary["mean_reef_sediment_stress_index"] = round(sediment_sum / cell_count, 6)
    summary["mean_reef_wave_exposure_index"] = round(wave_sum / cell_count, 6)
    summary["mean_reef_island_support_index"] = round(island_sum / cell_count, 6)
    if native_seasonal:
        summary.pop("mean_reef_bleaching_risk_index", None)
    else:
        summary["mean_reef_bleaching_risk_index"] = round(bleaching_sum / cell_count, 6)
    summary["fringing_reef_system_count"] = type_counts.get("fringing_reef", 0)
    summary["barrier_reef_system_count"] = type_counts.get("barrier_reef", 0)
    summary["atoll_reef_system_count"] = type_counts.get("atoll_reef", 0)
    summary["patch_reef_system_count"] = type_counts.get("patch_reef", 0)
    summary["cold_water_reef_system_count"] = type_counts.get("cold_water_reef", 0)
    summary["reef_type_counts"] = dict(sorted(type_counts.items()))
    world["reef_systems"] = records
    return world


_REEF_CELL_FIELDS = ("reef_growth_index", "reef_sediment_stress_index", "reef_wave_exposure_index", "reef_island_support_index", "reef_bleaching_risk_index", "reef_type", "reef_system_id")
_REEF_SUMMARY_FIELDS = ("reef_system_count", "reef_cell_count", "reef_total_area_km2", "mean_reef_growth_index", "mean_reef_sediment_stress_index", "mean_reef_wave_exposure_index", "mean_reef_island_support_index", "mean_reef_bleaching_risk_index", "fringing_reef_system_count", "barrier_reef_system_count", "atoll_reef_system_count", "patch_reef_system_count", "cold_water_reef_system_count", "reef_type_counts", "reef_port_links_model", "reef_port_links_complete", "reef_port_links_incomplete_system_count", "reef_source_port_selection_complete")


def enrich_world_with_reef_diagnostics(world: dict[str, Any]) -> dict[str, Any]:
    from .reef_port_links_validation import MODEL, PORTS3, validate_reef_port_links
    current = isinstance(world.get("port_site_model"), dict) and world["port_site_model"].get("model_type") == PORTS3
    if not current:
        errors = validate_reef_port_links(world)
        if errors:
            raise ValueError("; ".join(errors))
        return _enrich_reef_stage(world)
    from copy import deepcopy
    from .human_water_transport_validation import validate_versioned_port_sites
    errors = validate_versioned_port_sites(world)
    if errors:
        raise ValueError("reef port source: " + "; ".join(errors[:3])[:500])
    if "reef_port_links_model" in world and world["reef_port_links_model"] != MODEL:
        raise ValueError("unknown reef port annotation declaration")
    if "reef_port_links_model" in world.get("summary", {}) and world["summary"]["reef_port_links_model"] != MODEL["model_type"]:
        raise ValueError("unknown reef port annotation summary declaration")
    if ("reef_port_links_model" in world) != ("reef_port_links_model" in world["summary"]):
        raise ValueError("partial reef port annotation declaration")
    if "reef_port_links_model" not in world and (
        any(key in world["summary"] for key in ("reef_port_links_complete", "reef_port_links_incomplete_system_count", "reef_source_port_selection_complete"))
        or any("port_site_links_complete" in row for row in world.get("reef_systems", []))
    ):
        raise ValueError("undeclared reef port annotation outputs require deliberate clearing")
    staged = _enrich_reef_stage(deepcopy(world), available_port_links=True)
    staged["reef_port_links_model"] = dict(MODEL)
    incomplete = sum(not row["port_site_links_complete"] for row in staged["reef_systems"])
    staged["summary"].update(reef_port_links_model=MODEL["model_type"], reef_port_links_complete=incomplete == 0,
        reef_port_links_incomplete_system_count=incomplete,
        reef_source_port_selection_complete=staged["summary"]["port_site_selection_complete"])
    errors = validate_reef_port_links(staged)
    if errors:
        raise ValueError("; ".join(errors))
    for original, result in zip(world["cells"], staged["cells"]):
        for key in _REEF_CELL_FIELDS:
            if key in result:
                original[key] = result[key]
            else:
                original.pop(key, None)
    for key in _REEF_SUMMARY_FIELDS:
        if key in staged["summary"]:
            world["summary"][key] = staged["summary"][key]
        else:
            world["summary"].pop(key, None)
    for key in ("reef_diagnostics_model", "reef_port_links_model", "reef_systems"):
        world[key] = staged[key]
    return world
