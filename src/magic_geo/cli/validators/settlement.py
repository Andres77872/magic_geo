"""Settlement selection and route-network replay checks."""

from __future__ import annotations

import math
from typing import Any
from .settlement_climate import replay_settlement_climate, exact_support_declaration

from .._constants import (
    ROUTE_LINKS_PER_SETTLEMENT,
    ROUTE_NETWORK_MODEL,
    SETTLEMENT_DESERT_BIOMES,
    SETTLEMENT_MINIMUM_SEPARATION_FACTOR,
    SETTLEMENT_MINING_RESOURCES,
    SETTLEMENT_SCORE_THRESHOLD,
    SETTLEMENT_SELECTION_MODEL,
    SETTLEMENT_TARGET_CELL_DIVISOR,
    SETTLEMENT_TARGET_MAXIMUM,
    SETTLEMENT_TARGET_MINIMUM,
)


def _validate_settlement_selection(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    """Replay native settlement score, selection, type, and record mirrors."""

    failure = ["settlement selection model or causal replay invalid"]
    model = payload.get("settlement_selection_model", {})
    settlements = payload.get("settlements", [])
    try:
        selection_model, annual_inputs = replay_settlement_climate(payload)
        seasonal = annual_inputs is not None
        metadata_invalid = (
            not isinstance(model, dict)
            or not isinstance(settlements, list)
            or model.get("model_type") != selection_model
            or model.get("score_model")
            != ("native_soil_biome_resource_water_climate_hazard_landform_score_with_annual_proxy_support_v3" if seasonal else "native_soil_biome_resource_water_climate_hazard_landform_score_v2")
            or model.get("candidate_model")
            != ("nonmarine_nonlake_annual_proxy_supported_raw_score_threshold_neighbor_local_max_v3" if seasonal else "nonmarine_nonlake_raw_score_threshold_neighbor_local_max_v2")
            or (not exact_support_declaration(model.get("annual_climate_applicability")) if seasonal else "annual_climate_applicability" in model)
            or model.get("rank_model")
            != "descending_raw_score_then_cell_id_v1"
            or model.get("selection_model")
            != "greedy_spherical_minimum_separation_until_target_v1"
            or model.get("target_model")
            != "clamp_floor_cell_count_divisor_minimum_maximum_v1"
            or model.get("type_model")
            != "adjacent_water_river_mining_agriculture_oasis_frontier_priority_v1"
            or abs(
                float(model.get("score_threshold", -1.0))
                - SETTLEMENT_SCORE_THRESHOLD
            )
            > 1.0e-12
            or int(model.get("target_cell_divisor", -1))
            != SETTLEMENT_TARGET_CELL_DIVISOR
            or int(model.get("target_minimum", -1))
            != SETTLEMENT_TARGET_MINIMUM
            or int(model.get("target_maximum", -1))
            != SETTLEMENT_TARGET_MAXIMUM
            or abs(
                float(model.get("minimum_separation_factor", -1.0))
                - SETTLEMENT_MINIMUM_SEPARATION_FACTOR
            )
            > 1.0e-12
            or model.get("score_weights")
            != {
                "water_access": 0.38,
                "fertility": 0.30,
                "climate": 0.18,
                "resource_bonus": 0.18,
            }
            or model.get("hazard_weights")
            != {
                "convergent": 0.28,
                "transform": 0.18,
                "relief": 0.24,
                "ice": 0.22,
                "maximum": 0.65,
            }
            or float(model.get("cold_biome_multiplier", -1.0)) != 0.18
            or model.get("landform_score_adjustments")
            != {
                "delta_or_floodplain_add": 0.08,
                "alluvial_fan_add": 0.03,
                "salt_flat_multiplier": 0.55,
                "glacial_valley_or_moraine_multiplier": 0.42,
                "glacial_lake_multiplier": 0.72,
                "coastal_plain_add": 0.04,
            }
            or model.get("threshold_and_rank_semantics")
            != "unrounded_native_scores"
            or int(model.get("selection_score_precision", -1))
            != max(8, int(summary.get("output_float_precision", -1)))
            or model.get("formula_replay_tolerance_model")
            != "max_16_selection_units_one_output_unit"
            or model.get("record_order")
            != "selection_order_with_sequential_ids"
            or model.get("deterministic") is not True
            or model.get("model_limitation")
            != "static_suitability_selection_without_population_growth_land_market_or_infrastructure_feedback"
            or summary.get("settlement_selection_model")
            != selection_model
        )
    except (TypeError, ValueError, OverflowError):
        return failure
    if metadata_invalid or not cells_by_id:
        return failure
    if any(not isinstance(settlement, dict) for settlement in settlements):
        return failure

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def neighbors(cell: dict[str, Any]) -> list[dict[str, Any]]:
        raw_neighbor_ids = cell.get("neighbors", [])
        if not isinstance(raw_neighbor_ids, list):
            raise ValueError("neighbors must be a list")
        result = []
        for raw_neighbor_id in raw_neighbor_ids:
            neighbor = cells_by_id.get(int(raw_neighbor_id))
            if neighbor is None:
                raise ValueError("neighbor does not exist")
            result.append(neighbor)
        return result

    def local_relief(cell: dict[str, Any]) -> float:
        adjacent = neighbors(cell)
        if not adjacent:
            return 0.0
        mean_neighbor_elevation = sum(
            float(neighbor.get("elevation_m", 0.0)) for neighbor in adjacent
        ) / len(adjacent)
        return max(
            0.0,
            float(cell.get("elevation_m", 0.0)) - mean_neighbor_elevation,
        )

    def native_score(cell: dict[str, Any]) -> float:
        if bool(cell.get("is_water", False)) or bool(cell.get("is_lake", False)):
            return 0.0
        relief = local_relief(cell)
        slope_penalty = clamp(relief / 1800.0)
        temperature = annual_inputs[cell["id"]] if seasonal else float(cell.get("temperature_c", 0.0))
        precipitation = float(cell.get("precipitation_mm_y", 0.0))
        aridity = precipitation / max(1.0, (temperature + 8.0) * 31.0)
        latitude = abs(float(cell.get("lat_deg", 0.0)))
        latitude_pet_factor = 0.66 + 0.34 * (
            1.0 - min(1.0, latitude / 90.0)
        )
        temperatures = cell.get("temperature_monthly_c", [])
        precipitations = cell.get("precipitation_monthly_mm", [])
        if not isinstance(temperatures, list) or not isinstance(
            precipitations, list
        ):
            raise ValueError("monthly climate must be lists")
        dry_months = 0
        wet_months = 0
        for monthly_temperature, monthly_precipitation in zip(
            temperatures, precipitations
        ):
            monthly_pet = (
                max(0.0, float(monthly_temperature) + 5.0)
                * 3.1
                * latitude_pet_factor
            )
            dry_months += float(monthly_precipitation) < monthly_pet * 0.35
            wet_months += float(monthly_precipitation) >= monthly_pet * 0.75
        warm_seasonal = dry_months >= 2 and wet_months >= 3
        lithology = str(cell.get("lithology", ""))
        lithology_base = (
            0.78
            if lithology == "volcanic"
            else 0.50
            if lithology == "granite"
            else 0.44
            if lithology == "shale"
            else 0.58
        )
        climate_soil = clamp(precipitation / 1300.0, 0.0, 1.2) * clamp(
            (temperature + 8.0) / 30.0, 0.0, 1.1
        )
        fertility = clamp(
            lithology_base
            + 0.20 * climate_soil
            + (0.24 if bool(cell.get("is_river", False)) else 0.0)
            - 0.35 * slope_penalty
            - (0.28 if aridity < 0.45 else 0.0)
        )
        elevation = float(cell.get("elevation_m", 0.0))
        ice = float(cell.get("ice_thickness_m", 0.0))
        if ice > 180.0 or (
            temperature < -8.0 and (latitude > 55.0 or elevation > 1600.0)
        ):
            soil = "tundra"
            biome = "ice_cap"
        elif elevation > 2800.0 and temperature < 6.0:
            soil = "thin_mountain"
            biome = "alpine"
        elif temperature < -2.0:
            soil = "tundra"
            biome = "tundra"
        elif aridity < 0.32:
            soil = "arid"
            biome = "cold_desert" if temperature < 11.0 else "hot_desert"
        elif temperature > 23.0 and precipitation > 2100.0:
            soil = "tropical"
            biome = "tropical_rainforest"
        elif temperature > 21.0 and precipitation > 950.0:
            soil = "tropical"
            biome = "tropical_seasonal_forest"
        elif temperature > 18.0 and aridity < 0.82 and warm_seasonal:
            soil = "arid"
            biome = "savanna"
        elif temperature > 8.0 and precipitation > 760.0:
            soil = "temperate"
            biome = "temperate_forest"
        elif temperature > 5.0 and aridity > 0.45:
            soil = "temperate"
            biome = (
                "temperate_forest"
                if aridity > 1.1
                else "temperate_grassland"
            )
        elif temperature > -1.0 and precipitation > 420.0:
            soil = "boreal"
            biome = "boreal_forest"
        else:
            soil = "arid"
            biome = (
                "tundra"
                if temperature < 2.0
                and precipitation > 320.0
                and aridity > 0.55
                else "cold_desert"
                if temperature < 8.0
                else "hot_desert"
            )
        if (
            bool(cell.get("is_river", False))
            and relief < 450.0
            and precipitation > 500.0
        ):
            soil = "alluvial"
            if biome not in {"tropical_rainforest", "ice_cap"}:
                biome = "wetland"
        elif lithology == "volcanic" and soil != "tundra":
            soil = "volcanic"

        crust_type = str(cell.get("crust_type", ""))
        convergent = float(cell.get("boundary_convergent", 0.0))
        divergent = float(cell.get("boundary_divergent", 0.0))
        has_resource = (
            (convergent > 0.38 and (crust_type == "volcanic_arc" or lithology == "volcanic"))
            or (crust_type == "craton" and float(cell.get("crust_age_ma", 0.0)) > 1800.0)
            or crust_type == "sedimentary_basin"
            or lithology in {"shale", "limestone"}
            or float(cell.get("sediment_thickness_m", 0.0)) > 1.4
            or (bool(cell.get("is_river", False)) and convergent > 0.16)
            or divergent > 0.42
            or (lithology == "volcanic" and temperature > 0.0)
            or (soil == "alluvial" and fertility > 0.62)
        )
        coast = any(
            bool(neighbor.get("is_water", False))
            for neighbor in neighbors(cell)
        )
        water_access = (
            1.0
            if bool(cell.get("is_river", False))
            else 0.78
            if coast
            else clamp(float(cell.get("runoff_mm_y", 0.0)) / 550.0, 0.0, 0.55)
        )
        climate_score = clamp(1.0 - abs(temperature - 17.0) / 31.0)
        hazard = clamp(
            convergent * 0.28
            + float(cell.get("boundary_transform", 0.0)) * 0.18
            + slope_penalty * 0.24
            + clamp(ice / 2200.0) * 0.22,
            0.0,
            0.65,
        )
        score = clamp(
            0.38 * water_access
            + 0.30 * fertility
            + 0.18 * climate_score
            + (0.18 if has_resource else 0.0)
            - hazard
        )
        if biome in {"ice_cap", "tundra", "alpine", "ocean"}:
            score *= 0.18
        landform = str(cell.get("landform", ""))
        if landform in {"delta", "floodplain"}:
            score = clamp(score + 0.08)
        elif landform == "alluvial_fan":
            score = clamp(score + 0.03)
        elif landform == "salt_flat":
            score *= 0.55
        elif landform in {"glacial_valley", "moraine", "glacial_lake"}:
            score *= 0.72 if landform == "glacial_lake" else 0.42
        elif landform == "coastal_plain" and score > 0.0:
            score = clamp(score + 0.04)
        return score if not seasonal or -14.0 < temperature < 48.0 else 0.0

    try:
        score_unit = 10.0 ** (-int(model["selection_score_precision"]))
        input_unit = 10.0 ** (-int(summary["output_float_precision"]))
        score_tolerance = max(1.0e-9, score_unit * 16.0, input_unit)
        for cell in cells_by_id.values():
            if (
                abs(
                    float(cell.get("settlement_score", math.inf))
                    - native_score(cell)
                )
                > score_tolerance
            ):
                return failure
    except (KeyError, TypeError, ValueError, OverflowError):
        return failure

    try:
        candidates = []
        for cell_id, cell in cells_by_id.items():
            score = float(cell.get("settlement_score", 0.0))
            if (
                bool(cell.get("is_water", False))
                or bool(cell.get("is_lake", False))
                or (seasonal and not -14.0 < annual_inputs[cell_id] < 48.0)
                or score < SETTLEMENT_SCORE_THRESHOLD
            ):
                continue
            if any(
                not bool(neighbor.get("is_water", False))
                and not bool(neighbor.get("is_lake", False))
                and (not seasonal or -14.0 < annual_inputs[neighbor["id"]] < 48.0)
                and float(neighbor.get("settlement_score", 0.0)) > score
                for neighbor in neighbors(cell)
            ):
                continue
            candidates.append(cell_id)
        candidates.sort(
            key=lambda cell_id: (
                -float(cells_by_id[cell_id].get("settlement_score", 0.0)),
                cell_id,
            )
        )
        target = max(
            SETTLEMENT_TARGET_MINIMUM,
            min(
                SETTLEMENT_TARGET_MAXIMUM,
                len(cells_by_id) // SETTLEMENT_TARGET_CELL_DIVISOR,
            ),
        )
        minimum_separation = SETTLEMENT_MINIMUM_SEPARATION_FACTOR * math.sqrt(
            4.0 * math.pi / max(1, len(cells_by_id))
        )

        def position(cell_id: int) -> tuple[float, float, float]:
            values = cells_by_id[cell_id].get("position_3d", [])
            if not isinstance(values, list) or len(values) != 3:
                raise ValueError("position_3d invalid")
            return float(values[0]), float(values[1]), float(values[2])

        def angular_distance(first_id: int, second_id: int) -> float:
            first = position(first_id)
            second = position(second_id)
            dot = sum(a * b for a, b in zip(first, second))
            return math.acos(clamp(dot, -1.0, 1.0))

        selected_ids: list[int] = []
        for cell_id in candidates:
            if any(
                angular_distance(cell_id, selected_id) < minimum_separation
                for selected_id in selected_ids
            ):
                continue
            selected_ids.append(cell_id)
            if len(selected_ids) >= target:
                break
    except (TypeError, ValueError, OverflowError):
        return failure

    if (
        [int(settlement.get("cell_id", -1)) for settlement in settlements]
        != selected_ids
        or int(model.get("candidate_cell_count", -1)) != len(candidates)
        or int(model.get("target_count", -1)) != target
        or int(model.get("settlement_count", -1)) != len(selected_ids)
        or int(summary.get("settlement_count", -1)) != len(selected_ids)
    ):
        return failure

    precision = int(summary.get("output_float_precision", -1))
    mirror_tolerance = 0.5 * 10.0 ** (-precision) + 1.0e-12

    # Settlement allegiance uses different basin/coast discounts and can add a
    # direct-route discount. Its assignment can differ from the territorial
    # cell partition even without a direct route to either capital.
    # Check the region/settlement links here. The independent political replay
    # reconstructs both assignment costs and verifies the chosen capitals.
    region_membership: dict[int, int] = {}
    regions = payload.get("political_regions", [])
    if not isinstance(regions, list):
        return failure
    region_ids: set[int] = set()
    try:
        for region in regions:
            if not isinstance(region, dict):
                return failure
            region_id = int(region.get("id", -1))
            member_ids = region.get("settlement_ids")
            if region_id < 0 or region_id in region_ids or not isinstance(member_ids, list):
                return failure
            region_ids.add(region_id)
            for raw_member_id in member_ids:
                member_id = int(raw_member_id)
                if member_id < 0 or member_id >= len(settlements) or member_id in region_membership:
                    return failure
                region_membership[member_id] = region_id
            if int(region.get("capital_settlement_id", -1)) not in region_membership or (
                region_membership[int(region["capital_settlement_id"])] != region_id
            ):
                return failure
        if set(region_membership) != set(range(len(settlements))):
            return failure
    except (KeyError, TypeError, ValueError, OverflowError):
        return failure

    def settlement_type(cell: dict[str, Any]) -> str:
        if any(
            bool(neighbor.get("is_water", False)) for neighbor in neighbors(cell)
        ):
            return "port"
        if bool(cell.get("is_river", False)):
            return "river_city"
        if str(cell.get("resource", "")) in SETTLEMENT_MINING_RESOURCES:
            return "mining_town"
        if (
            float(cell.get("fertility", 0.0)) > 0.66
            or str(cell.get("resource", "")) == "fertile_alluvium"
        ):
            return "agricultural_town"
        if str(cell.get("biome", "")) in SETTLEMENT_DESERT_BIOMES and (
            float(cell.get("runoff_mm_y", 0.0)) > 120.0
            or bool(cell.get("is_lake", False))
        ):
            return "oasis"
        return "frontier_town"

    try:
        for settlement_id, settlement in enumerate(settlements):
            cell = cells_by_id[selected_ids[settlement_id]]
            if (
                int(settlement.get("id", -1)) != settlement_id
                or str(settlement.get("type", "")) != settlement_type(cell)
                or float(settlement.get("score", math.inf))
                != float(cell.get("settlement_score", -math.inf))
                or abs(
                    float(settlement.get("lat_deg", math.inf))
                    - float(cell.get("lat_deg", -math.inf))
                )
                > mirror_tolerance
                or abs(
                    float(settlement.get("lon_deg", math.inf))
                    - float(cell.get("lon_deg", -math.inf))
                )
                > mirror_tolerance
                or str(settlement.get("biome", ""))
                != str(cell.get("biome", ""))
                or str(settlement.get("resource", ""))
                != str(cell.get("resource", ""))
                or str(settlement.get("water_body_type", ""))
                != str(cell.get("water_body_type", ""))
                or abs(
                    float(settlement.get("fertility", math.inf))
                    - float(cell.get("fertility", -math.inf))
                )
                > mirror_tolerance
                or bool(settlement.get("is_river", False))
                != bool(cell.get("is_river", False))
                or int(settlement.get("region_id", -2))
                != region_membership[settlement_id]
                or int(settlement.get("culture_region_id", -2))
                != int(cell.get("culture_region_id", -1))
                or int(settlement.get("language_region_id", -2))
                != int(cell.get("language_region_id", -1))
            ):
                return failure
    except (IndexError, TypeError, ValueError):
        return failure
    expected_top_score = (
        float(settlements[0].get("score", 0.0)) if settlements else 0.0
    )
    if float(summary.get("top_settlement_score", math.inf)) != expected_top_score:
        return failure
    return []


def _validate_route_network(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
) -> list[str]:
    """Replay native endpoint ranking, pair selection, cost, and route type."""

    failure = ["route network model or causal replay invalid"]
    model = payload.get("route_network_model", {})
    routes = payload.get("routes", [])
    settlements = payload.get("settlements", [])
    planet = payload.get("planet_parameters", {})
    try:
        selection_model, annual_inputs = replay_settlement_climate(payload)
        seasonal = annual_inputs is not None
        metadata_invalid = (
            not isinstance(model, dict)
            or not isinstance(routes, list)
            or not isinstance(settlements, list)
            or not isinstance(planet, dict)
            or model.get("model_type") != ROUTE_NETWORK_MODEL
            or model.get("source_settlement_model")
            != selection_model
            or model.get("ranking_model")
            != "endpoint_great_circle_distance_times_barrier_with_port_or_river_discount_v1"
            or model.get("barrier_model")
            != "endpoint_mountain_tectonic_hazard_and_desert_multiplier_v1"
            or model.get("selection_model")
            != "two_lowest_ranked_neighbors_per_settlement_then_unique_unordered_pair_v1"
            or model.get("route_type_model")
            != "port_pair_river_basin_mountain_hazard_overland_priority_v1"
            or model.get("record_order")
            != "source_settlement_order_then_rank_with_first_unique_pair_v1"
            or int(model.get("links_per_settlement", -1))
            != ROUTE_LINKS_PER_SETTLEMENT
            or model.get("planet_radius_source")
            != "planet_parameters.radius_km"
            or model.get("barrier_parameters")
            != {
                "mountain_start_m": 1200.0,
                "mountain_scale_m": 2600.0,
                "mountain_weight": 0.95,
                "convergent_pair_weight": 0.50,
                "transform_pair_weight": 0.25,
                "tectonic_weight": 0.45,
                "desert_addition": 0.18,
            }
            or model.get("ranking_discounts")
            != {"port_pair": 0.68, "shared_basin_river": 0.78}
            or float(model.get("mountain_route_elevation_threshold_m", -1.0))
            != 1300.0
            or float(model.get("mountain_route_convergence_threshold", -1.0))
            != 0.24
            or model.get("deterministic") is not True
            or model.get("model_limitation")
            != "endpoint_only_network_selection_before_downstream_cell_path_routing_capacity_congestion_and_equilibrium"
            or summary.get("route_network_model") != ROUTE_NETWORK_MODEL
        )
    except (TypeError, ValueError, OverflowError):
        return failure
    if metadata_invalid or any(
        not isinstance(record, dict) for record in [*settlements, *routes]
    ):
        return failure

    settlements_by_id = {
        int(settlement.get("id", -1)): settlement for settlement in settlements
    }
    if sorted(settlements_by_id) != list(range(len(settlements))):
        return failure

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def endpoint_cell(settlement_id: int) -> dict[str, Any]:
        settlement = settlements_by_id[settlement_id]
        cell = cells_by_id.get(int(settlement.get("cell_id", -1)))
        if cell is None:
            raise ValueError("settlement cell does not exist")
        return cell

    def angular_distance(first: dict[str, Any], second: dict[str, Any]) -> float:
        first_position = first.get("position_3d", [])
        second_position = second.get("position_3d", [])
        if (
            not isinstance(first_position, list)
            or not isinstance(second_position, list)
            or len(first_position) != 3
            or len(second_position) != 3
        ):
            raise ValueError("position_3d invalid")
        dot = sum(
            float(first_value) * float(second_value)
            for first_value, second_value in zip(
                first_position, second_position
            )
        )
        return math.acos(clamp(dot, -1.0, 1.0))

    def barrier(first: dict[str, Any], second: dict[str, Any]) -> float:
        mountain = clamp(
            (
                max(
                    float(first.get("elevation_m", 0.0)),
                    float(second.get("elevation_m", 0.0)),
                )
                - 1200.0
            )
            / 2600.0
        )
        tectonic_hazard = 0.50 * (
            float(first.get("boundary_convergent", 0.0))
            + float(second.get("boundary_convergent", 0.0))
        ) + 0.25 * (
            float(first.get("boundary_transform", 0.0))
            + float(second.get("boundary_transform", 0.0))
        )
        desert = (
            0.18
            if str(first.get("biome", "")) in SETTLEMENT_DESERT_BIOMES
            or str(second.get("biome", "")) in SETTLEMENT_DESERT_BIOMES
            else 0.0
        )
        return 1.0 + 0.95 * mountain + 0.45 * clamp(tectonic_hazard) + desert

    def route_type(
        first_settlement: dict[str, Any],
        second_settlement: dict[str, Any],
        first_cell: dict[str, Any],
        second_cell: dict[str, Any],
    ) -> str:
        if (
            str(first_settlement.get("type", "")) == "port"
            and str(second_settlement.get("type", "")) == "port"
        ):
            return "coastal_sea"
        if (
            bool(first_cell.get("is_river", False))
            and bool(second_cell.get("is_river", False))
            and int(first_cell.get("basin_id", -1))
            == int(second_cell.get("basin_id", -2))
        ):
            return "river_corridor"
        if (
            float(first_cell.get("elevation_m", 0.0)) > 1300.0
            or float(second_cell.get("elevation_m", 0.0)) > 1300.0
            or float(first_cell.get("boundary_convergent", 0.0)) > 0.24
            or float(second_cell.get("boundary_convergent", 0.0)) > 0.24
        ):
            return "mountain_pass"
        return "overland"

    try:
        radius = float(planet.get("radius_km", -1.0))
        if radius <= 0.0:
            return failure
        expected_routes: list[dict[str, Any]] = []
        used_pairs: set[tuple[int, int]] = set()
        for settlement_id in range(len(settlements)):
            settlement = settlements_by_id[settlement_id]
            first_cell = endpoint_cell(settlement_id)
            ranked: list[tuple[float, int]] = []
            for other_id in range(len(settlements)):
                if settlement_id == other_id:
                    continue
                other = settlements_by_id[other_id]
                other_cell = endpoint_cell(other_id)
                distance = angular_distance(first_cell, other_cell) * radius
                rank_cost = distance * barrier(first_cell, other_cell)
                if (
                    str(settlement.get("type", "")) == "port"
                    and str(other.get("type", "")) == "port"
                ):
                    rank_cost *= 0.68
                elif (
                    int(first_cell.get("basin_id", -1))
                    == int(other_cell.get("basin_id", -2))
                    and (
                        bool(first_cell.get("is_river", False))
                        or bool(other_cell.get("is_river", False))
                    )
                ):
                    rank_cost *= 0.78
                ranked.append((rank_cost, other_id))
            ranked.sort()
            for _, other_id in ranked[:ROUTE_LINKS_PER_SETTLEMENT]:
                first_id = min(settlement_id, other_id)
                second_id = max(settlement_id, other_id)
                pair = (first_id, second_id)
                if pair in used_pairs:
                    continue
                used_pairs.add(pair)
                source = settlements_by_id[first_id]
                target = settlements_by_id[second_id]
                source_cell = endpoint_cell(first_id)
                target_cell = endpoint_cell(second_id)
                distance = angular_distance(source_cell, target_cell) * radius
                selected_type = route_type(
                    source, target, source_cell, target_cell
                )
                cost = distance * barrier(source_cell, target_cell)
                if selected_type == "coastal_sea":
                    cost *= 0.68
                elif selected_type == "river_corridor":
                    cost *= 0.78
                expected_routes.append(
                    {
                        "id": len(expected_routes),
                        "from": first_id,
                        "to": second_id,
                        "type": selected_type,
                        "distance_km": distance,
                        "cost": cost,
                    }
                )
    except (KeyError, TypeError, ValueError):
        return failure

    if (
        len(routes) != len(expected_routes)
        or int(model.get("settlement_count", -1)) != len(settlements)
        or int(model.get("route_count", -1)) != len(expected_routes)
        or int(summary.get("route_count", -1)) != len(expected_routes)
    ):
        return failure
    precision = int(summary.get("output_float_precision", -1))
    output_unit = 10.0 ** (-precision)
    try:
        for actual, expected in zip(routes, expected_routes):
            distance = float(expected["distance_km"])
            cost_tolerance = max(
                output_unit,
                distance * 0.45 * 0.75 * output_unit + output_unit,
            )
            if (
                int(actual.get("id", -1)) != expected["id"]
                or int(actual.get("from", -1)) != expected["from"]
                or int(actual.get("to", -1)) != expected["to"]
                or str(actual.get("type", "")) != expected["type"]
                or abs(float(actual.get("distance_km", math.inf)) - distance)
                > output_unit
                or abs(float(actual.get("cost", math.inf)) - float(expected["cost"]))
                > cost_tolerance
            ):
                return failure
    except (TypeError, ValueError, OverflowError):
        return failure
    return []
