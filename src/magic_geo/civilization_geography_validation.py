from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


POPULATION_REGION_MODEL = "causal_area_weighted_capacity_occupancy_population_regions_v1"
CONFLICT_MODEL = "causal_border_pair_pressure_trade_conflict_selection_v1"
DYNASTY_MODEL = "causal_foundation_continuity_pressure_dynasty_lineages_v1"
HARD_TRADE_BORDER_TYPES = {"river", "mountain", "coastal"}
CONFLICT_CAUSES = (
    "water_rights",
    "fertile_plain",
    "mining_claim",
    "trade_chokepoint",
    "border_fragmentation",
    "sacred_site",
)


def _population_model() -> dict[str, Any]:
    return {
        "model_type": POPULATION_REGION_MODEL,
        "deterministic": True,
        "membership_model": "nonwater_political_region_cells_v1",
        "water_security_model": "runoff_river_lake_water_neighbor_saline_penalty_v1",
        "climate_suitability_model": "temperature_precipitation_ice_bounded_index_v1",
        "hazard_mortality_model": "tectonic_local_relief_ice_bounded_index_v1",
        "density_capacity_model": "fertility_water_climate_and_site_strength_v1",
        "density_capacity_parameters": {
            "base_people_per_km2": 1.5,
            "agricultural_weight": 64.0,
            "site_strength_weight": 12.0,
            "minimum_people_per_km2": 0.2,
            "maximum_people_per_km2": 90.0,
        },
        "urbanization_model": "settlement_route_and_site_strength_v1",
        "occupancy_model": "continuity_urbanization_routes_hazard_v1",
        "growth_model": "agriculture_water_pressure_hazard_bounded_rate_v1",
        "migration_balance_model": "one_half_minus_culture_migration_pressure_v1",
        "model_limitation": "static_diagnostic_capacity_and_occupancy_without_age_structure_land_use_feedback_disease_or_observed_demographic_calibration",
    }


def _conflict_model() -> dict[str, Any]:
    return {
        "model_type": CONFLICT_MODEL,
        "deterministic": True,
        "candidate_model": "highest_score_border_per_sorted_region_pair_v1",
        "minimum_candidate_score": 0.24,
        "maximum_conflicts_per_region": 2,
        "cause_model": "water_fertility_resource_trade_then_nonopen_border_priority_v1",
        "resource_pressure_if_present": 0.72,
        "trade_chokepoint_model": "interregional_pair_flow_volume_times_friction_plus_hard_border_v1",
        "hard_border_trade_bonus": 0.34,
        "intensity_model": "population_border_resource_water_trade_weighted_index_v1",
        "candidate_score_fertility_weight": 0.08,
        "record_order": "descending_raw_candidate_score_then_region_pair_v1",
        "contested_cell_model": "border_cell_a_if_intensity_at_least_one_half_else_cell_b_v1",
        "chronology_model": "intensity_candidate_map_size_duration_and_era_v1",
        "war_diagnostics_model": "population_route_urbanization_logistics_mobilization_casualty_disruption_v1",
        "outcome_model": "exhaustion_stalemate_border_shift_or_force_advantage_v1",
        "model_limitation": "one_diagnostic_conflict_per_adjacent_region_pair_without_strategy_diplomacy_uncertainty_or_observed_war_calibration",
    }


def _dynasty_model() -> dict[str, Any]:
    return {
        "model_type": DYNASTY_MODEL,
        "deterministic": True,
        "foundation_model": "oldest_state_foundation_event_per_region_v1",
        "succession_pressure_model": "population_conflict_route_and_culture_continuity_v1",
        "dynasty_count_thresholds": [0.36, 0.66],
        "lineage_model": "contiguous_region_chain_with_root_parent_child_successor_links_v1",
        "duration_model": "equal_foundation_year_partition_by_region_dynasty_count_v1",
        "legitimacy_model": "continuity_settlement_succession_and_conflict_v1",
        "dynastic_continuity_model": "legitimacy_duration_and_inverse_succession_pressure_v1",
        "collapse_reason_model": "continuity_conflict_migration_resource_trade_then_succession_priority_v1",
        "model_limitation": "single_linear_dynasty_chain_per_region_without_person_level_succession_branch_competition_or_observed_genealogy_calibration",
    }


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _close(actual: Any, expected: float, tolerance: float) -> bool:
    try:
        return abs(float(actual) - expected) <= tolerance
    except (TypeError, ValueError):
        return False


def _relative_close(actual: Any, expected: float, fraction: float = 0.0005) -> bool:
    return _close(actual, expected, max(1.0, abs(expected) * fraction))


def _local_relief(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> float:
    neighbors = [cells_by_id[int(value)] for value in cell.get("neighbors", [])]
    if not neighbors:
        return 0.0
    mean_elevation = sum(float(neighbor.get("elevation_m", 0.0)) for neighbor in neighbors) / len(neighbors)
    return max(0.0, float(cell.get("elevation_m", 0.0)) - mean_elevation)


def _has_water_neighbor(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> bool:
    return any(bool(cells_by_id[int(value)].get("is_water", False)) for value in cell.get("neighbors", []))


def _water_security(cell: dict[str, Any], cells_by_id: dict[int, dict[str, Any]]) -> float:
    water = _clamp(float(cell.get("runoff_mm_y", 0.0)) / 1300.0, 0.0, 0.70)
    if bool(cell.get("is_river", False)):
        water += 0.24
    if bool(cell.get("is_lake", False)) or str(cell.get("water_body_type", "land")) == "fresh_lake":
        water += 0.18
    if _has_water_neighbor(cell, cells_by_id):
        water += 0.08
    if str(cell.get("water_body_type", "land")) == "saline_basin" or str(cell.get("soil_type", "none")) == "saline":
        water -= 0.18
    return _clamp(water)


def _era_for_year(year_bp: float) -> int:
    if year_bp > 2400.0:
        return 0
    if year_bp > 1300.0:
        return 1
    if year_bp > 450.0:
        return 2
    return 3


def _population_records(
    cells: list[dict[str, Any]],
    regions: list[dict[str, Any]],
    cultures: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cells_by_id = {int(cell["id"]): cell for cell in cells}
    region_to_culture = {
        int(culture.get("homeland_region_id", -1)): int(culture["id"])
        for culture in cultures
        if int(culture.get("homeland_region_id", -1)) >= 0
    }
    populations: list[dict[str, Any]] = []
    for region in regions:
        population: dict[str, Any] = {
            "id": len(populations),
            "region_id": int(region["id"]),
            "culture_region_id": -1,
            "language_region_id": -1,
            "settlement_count": int(region.get("settlement_count", 0)),
            "carrying_capacity": 0.0,
            "estimated_population": 0.0,
            "agricultural_capacity_index": 0.0,
            "water_security_index": 0.0,
            "urbanization_fraction": 0.0,
            "growth_rate_per_year": 0.0,
            "population_pressure": 0.0,
            "migration_balance": 0.0,
            "hazard_mortality_index": 0.0,
        }
        region_id = int(region["id"])
        culture_id = region_to_culture.get(region_id, -1)
        if 0 <= culture_id < len(cultures):
            culture = cultures[culture_id]
            population["culture_region_id"] = culture_id
            population["language_region_id"] = int(culture.get("language_region_id", -1))
            population["migration_balance"] = _clamp(
                0.5 - float(culture.get("migration_pressure", 0.0)), -1.0, 1.0
            )

        area = 0.0
        fertility_sum = 0.0
        water_sum = 0.0
        climate_sum = 0.0
        hazard_sum = 0.0
        urban_site_sum = 0.0
        cell_count = 0
        for cell in cells:
            if bool(cell.get("is_water", False)) or int(cell.get("political_region_id", -1)) != region_id:
                continue
            cell_area = float(cell.get("area_km2", 0.0))
            water = _water_security(cell, cells_by_id)
            climate = _clamp(
                1.0
                - abs(float(cell.get("temperature_c", 0.0)) - 17.0) / 42.0
                - max(0.0, 360.0 - float(cell.get("precipitation_mm_y", 0.0))) / 1400.0
                - float(cell.get("ice_thickness_m", 0.0)) / 2800.0
            )
            hazard = _clamp(
                0.35 * float(cell.get("boundary_convergent", 0.0))
                + 0.25 * float(cell.get("boundary_transform", 0.0))
                + _local_relief(cell, cells_by_id) / 4200.0
                + float(cell.get("ice_thickness_m", 0.0)) / 3200.0
            )
            area += cell_area
            fertility_sum += float(cell.get("fertility", 0.0)) * cell_area
            water_sum += water * cell_area
            climate_sum += climate * cell_area
            hazard_sum += hazard * cell_area
            urban_site_sum += float(cell.get("settlement_score", 0.0)) * cell_area
            cell_count += 1
        if area <= 0.0 or cell_count == 0:
            populations.append(population)
            continue

        fertility = fertility_sum / area
        water = water_sum / area
        climate = climate_sum / area
        hazard = hazard_sum / area
        site_strength = urban_site_sum / area
        settlement_count = int(region.get("settlement_count", 0))
        route_factor = _clamp(float(region.get("route_count", 0)) / max(1.0, float(settlement_count)))
        density_capacity = _clamp(
            1.5 + 64.0 * fertility * water * climate + 12.0 * site_strength,
            0.2,
            90.0,
        )
        population["agricultural_capacity_index"] = _clamp(fertility * climate * (0.55 + 0.45 * water))
        population["water_security_index"] = water
        population["hazard_mortality_index"] = hazard
        population["urbanization_fraction"] = _clamp(
            0.04 + 0.025 * settlement_count + 0.16 * route_factor + 0.12 * site_strength,
            0.02,
            0.62,
        )
        population["carrying_capacity"] = area * density_capacity
        continuity = (
            float(cultures[culture_id].get("continuity_index", 0.5))
            if 0 <= culture_id < len(cultures)
            else 0.5
        )
        occupancy = _clamp(
            0.22
            + 0.30 * continuity
            + 0.26 * float(population["urbanization_fraction"])
            + 0.18 * route_factor
            - 0.18 * hazard,
            0.05,
            0.93,
        )
        population["estimated_population"] = float(population["carrying_capacity"]) * occupancy
        population["population_pressure"] = _clamp(
            float(population["estimated_population"]) / float(population["carrying_capacity"]),
            0.0,
            1.4,
        )
        population["growth_rate_per_year"] = _clamp(
            0.0015
            + 0.0065 * float(population["agricultural_capacity_index"])
            + 0.0025 * float(population["water_security_index"])
            - 0.0030 * float(population["population_pressure"])
            - 0.0045 * hazard,
            -0.012,
            0.018,
        )
        populations.append(population)
    return populations


def _population_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    exact_keys = ("id", "region_id", "culture_region_id", "language_region_id", "settlement_count")
    if any(actual.get(key) != expected[key] for key in exact_keys):
        return False
    if not all(
        _close(actual.get(key), float(expected[key]), tolerance)
        for key, tolerance in (
            ("agricultural_capacity_index", 0.002),
            ("water_security_index", 0.002),
            ("urbanization_fraction", 0.002),
            ("growth_rate_per_year", 0.0002),
            ("population_pressure", 0.002),
            ("migration_balance", 0.002),
            ("hazard_mortality_index", 0.002),
        )
    ):
        return False
    return _relative_close(actual.get("carrying_capacity"), float(expected["carrying_capacity"])) and _relative_close(
        actual.get("estimated_population"), float(expected["estimated_population"])
    )


def _conflict_records(
    cells: list[dict[str, Any]],
    regions: list[dict[str, Any]],
    borders: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    cultures: list[dict[str, Any]],
    populations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cells_by_id = {int(cell["id"]): cell for cell in cells}
    region_to_culture = {
        int(culture.get("homeland_region_id", -1)): int(culture["id"])
        for culture in cultures
        if int(culture.get("homeland_region_id", -1)) >= 0
    }
    populations_by_region = {int(population["region_id"]): population for population in populations}
    regions_by_id = {int(region["id"]): region for region in regions}
    trade_chokepoint: defaultdict[tuple[int, int], float] = defaultdict(float)
    for flow in flows:
        region_from = int(flow.get("region_from", -1))
        region_to = int(flow.get("region_to", -1))
        if not bool(flow.get("interregional", False)) or region_from < 0 or region_to < 0:
            continue
        pair = tuple(sorted((region_from, region_to)))
        trade_chokepoint[pair] += float(flow.get("volume_index", 0.0)) * float(flow.get("friction", 0.0)) / 100.0

    best_by_pair: dict[tuple[int, int], tuple[float, dict[str, Any]]] = {}
    for border in borders:
        region_a_raw = int(border.get("region_a", -1))
        region_b_raw = int(border.get("region_b", -1))
        cell_a_id = int(border.get("cell_a", -1))
        cell_b_id = int(border.get("cell_b", -1))
        if min(region_a_raw, region_b_raw, cell_a_id, cell_b_id) < 0:
            continue
        first_cell = cells_by_id[cell_a_id]
        second_cell = cells_by_id[cell_b_id]
        pair = tuple(sorted((region_a_raw, region_b_raw)))
        pop_a = populations_by_region.get(pair[0])
        pop_b = populations_by_region.get(pair[1])
        region_a = regions_by_id.get(pair[0])
        region_b = regions_by_id.get(pair[1])
        pressure = 0.5 * (
            (float(pop_a["population_pressure"]) if pop_a is not None else 0.35)
            + (float(pop_b["population_pressure"]) if pop_b is not None else 0.35)
        )
        resource_pressure = (
            0.72
            if str(first_cell.get("resource", "none")) != "none"
            or str(second_cell.get("resource", "none")) != "none"
            else 0.0
        )
        water_stress = _clamp(
            1.0 - 0.5 * (_water_security(first_cell, cells_by_id) + _water_security(second_cell, cells_by_id))
        )
        fertility_pressure = _clamp(
            0.5 * (float(first_cell.get("fertility", 0.0)) + float(second_cell.get("fertility", 0.0)))
        )
        border_type = str(border.get("type", "open_lowland"))
        pair_trade = _clamp(
            trade_chokepoint[pair] * 0.24 + (0.34 if border_type in HARD_TRADE_BORDER_TYPES else 0.0)
        )
        cause_score = water_stress
        cause_index = 0
        if fertility_pressure > cause_score:
            cause_score = fertility_pressure
            cause_index = 1
        if resource_pressure > cause_score:
            cause_score = resource_pressure
            cause_index = 2
        if pair_trade > cause_score:
            cause_score = pair_trade
            cause_index = 3
        barrier_score = float(border.get("barrier_score", 0.0))
        if barrier_score > cause_score and border_type != "open_lowland":
            cause_index = 4
        intensity = _clamp(
            0.12
            + 0.28 * pressure
            + 0.22 * barrier_score
            + 0.18 * resource_pressure
            + 0.16 * water_stress
            + 0.18 * pair_trade
        )
        score = intensity + 0.08 * fertility_pressure
        if score < 0.24:
            continue
        start_year = _clamp(160.0 + 1850.0 * intensity + 17.0 * (len(best_by_pair) + 1), 90.0, 2600.0)
        duration = _clamp(12.0 + 90.0 * intensity + 18.0 * pair_trade, 8.0, 160.0)
        population_a = float(pop_a["estimated_population"]) if pop_a is not None else 0.0
        population_b = float(pop_b["estimated_population"]) if pop_b is not None else 0.0
        average_population = 0.5 * (population_a + population_b)
        total_population = population_a + population_b
        route_factor_a = (
            _clamp(float(region_a.get("route_count", 0)) / max(1.0, float(region_a.get("settlement_count", 0))))
            if region_a is not None
            else 0.0
        )
        route_factor_b = (
            _clamp(float(region_b.get("route_count", 0)) / max(1.0, float(region_b.get("settlement_count", 0))))
            if region_b is not None
            else 0.0
        )
        urban_a = float(pop_a["urbanization_fraction"]) if pop_a is not None else 0.05
        urban_b = float(pop_b["urbanization_fraction"]) if pop_b is not None else 0.05
        logistics = _clamp(
            0.24 * barrier_score
            + 0.22 * water_stress
            + 0.20 * pair_trade
            + 0.18 * intensity
            + (0.10 if border_type in {"river", "mountain"} else 0.0)
        )
        mobilization_rate = _clamp(
            0.012 + 0.070 * intensity + 0.022 * pair_trade + 0.015 * pressure - 0.018 * logistics,
            0.004,
            0.16,
        )
        force_a = max(
            0.0,
            population_a
            * mobilization_rate
            * (0.72 + 0.28 * urban_a + 0.14 * route_factor_a - 0.22 * logistics),
        )
        force_b = max(
            0.0,
            population_b
            * mobilization_rate
            * (0.72 + 0.28 * urban_b + 0.14 * route_factor_b - 0.22 * logistics),
        )
        mobilized = force_a + force_b
        casualties = average_population * intensity * (0.006 + 0.025 * intensity)
        casualty_rate = _clamp(casualties / total_population) if total_population > 0.0 else 0.0
        disruption = _clamp(
            0.18 * intensity
            + 0.18 * logistics
            + 0.18 * pair_trade
            + 0.16 * resource_pressure
            + 0.14 * water_stress
            + 0.16 * (duration / 160.0)
        )
        effectiveness_a = force_a * (1.0 + 0.26 * route_factor_a + 0.18 * urban_a - 0.38 * logistics)
        effectiveness_b = force_b * (1.0 + 0.26 * route_factor_b + 0.18 * urban_b - 0.38 * logistics)
        advantage = (effectiveness_a - effectiveness_b) / max(1.0, mobilized)
        if logistics > 0.72 and intensity > 0.58:
            outcome = "exhaustion"
        elif abs(advantage) < 0.08:
            outcome = "stalemate"
        elif abs(advantage) < 0.20 and pair_trade > 0.38:
            outcome = "border_shift"
        else:
            outcome = "region_a_victory" if advantage > 0.0 else "region_b_victory"
        record = {
            "region_a": pair[0],
            "region_b": pair[1],
            "culture_a": region_to_culture.get(pair[0], -1),
            "culture_b": region_to_culture.get(pair[1], -1),
            "cause": CONFLICT_CAUSES[cause_index],
            "outcome": outcome,
            "contested_cell_id": cell_a_id if intensity >= 0.5 else cell_b_id,
            "start_year_bp": start_year,
            "end_year_bp": max(0.0, start_year - duration),
            "war_duration_years": min(start_year, duration),
            "era_id": _era_for_year(start_year),
            "intensity": intensity,
            "resource_pressure": resource_pressure,
            "water_stress": water_stress,
            "trade_chokepoint_index": pair_trade,
            "region_a_force_estimate": force_a,
            "region_b_force_estimate": force_b,
            "mobilized_population": mobilized,
            "casualty_rate": casualty_rate,
            "logistics_strain_index": logistics,
            "economic_disruption_index": disruption,
            "estimated_casualties": casualties,
        }
        if pair not in best_by_pair or score > best_by_pair[pair][0]:
            best_by_pair[pair] = (score, record)

    candidates = sorted(
        best_by_pair.items(),
        key=lambda item: (-item[1][0], item[0]),
    )
    target = min(len(candidates), max(0, len(regions) * 2))
    conflicts: list[dict[str, Any]] = []
    for _, (_, record) in candidates[:target]:
        record["id"] = len(conflicts)
        conflicts.append(record)
    return conflicts


def _conflict_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    exact_keys = (
        "id",
        "era_id",
        "region_a",
        "region_b",
        "culture_a",
        "culture_b",
        "cause",
        "outcome",
        "contested_cell_id",
    )
    if any(actual.get(key) != expected[key] for key in exact_keys):
        return False
    if not all(
        _close(actual.get(key), float(expected[key]), tolerance)
        for key, tolerance in (
            ("start_year_bp", 0.30),
            ("end_year_bp", 0.30),
            ("war_duration_years", 0.20),
            ("intensity", 0.003),
            ("resource_pressure", 0.001),
            ("water_stress", 0.003),
            ("trade_chokepoint_index", 0.003),
            ("casualty_rate", 0.001),
            ("logistics_strain_index", 0.003),
            ("economic_disruption_index", 0.003),
        )
    ):
        return False
    return all(
        _relative_close(actual.get(key), float(expected[key]), 0.001)
        for key in (
            "region_a_force_estimate",
            "region_b_force_estimate",
            "mobilized_population",
            "estimated_casualties",
        )
    )


def _dynasty_records(
    regions: list[dict[str, Any]],
    cultures: list[dict[str, Any]],
    historical_events: list[dict[str, Any]],
    populations: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    region_to_culture = {
        int(culture.get("homeland_region_id", -1)): int(culture["id"])
        for culture in cultures
        if int(culture.get("homeland_region_id", -1)) >= 0
    }
    populations_by_region = {int(population["region_id"]): population for population in populations}
    conflict_pressure: defaultdict[int, float] = defaultdict(float)
    for conflict in conflicts:
        conflict_pressure[int(conflict["region_a"])] += float(conflict["intensity"])
        conflict_pressure[int(conflict["region_b"])] += float(conflict["intensity"])
    founding_event_by_region: dict[int, int] = {}
    founding_year_by_region: dict[int, float] = {}
    for event in historical_events:
        if str(event.get("type", "")) != "state_foundation" or int(event.get("region_id", -1)) < 0:
            continue
        region_id = int(event["region_id"])
        year = float(event.get("year_bp", 0.0))
        if region_id not in founding_event_by_region or year > founding_year_by_region[region_id]:
            founding_event_by_region[region_id] = int(event["id"])
            founding_year_by_region[region_id] = year

    dynasties: list[dict[str, Any]] = []
    for region in regions:
        region_id = int(region["id"])
        culture_id = region_to_culture.get(region_id, -1)
        language_id = (
            int(cultures[culture_id].get("language_region_id", -1))
            if 0 <= culture_id < len(cultures)
            else -1
        )
        continuity = (
            float(cultures[culture_id].get("continuity_index", 0.5))
            if 0 <= culture_id < len(cultures)
            else 0.5
        )
        population = populations_by_region.get(region_id)
        population_pressure = float(population["population_pressure"]) if population is not None else 0.4
        regional_conflict_pressure = _clamp(conflict_pressure[region_id] / 3.0)
        succession_pressure = _clamp(
            0.18
            + 0.34 * population_pressure
            + 0.36 * regional_conflict_pressure
            + (0.10 if int(region.get("route_count", 0)) == 0 else 0.0)
            - 0.24 * continuity
        )
        dynasty_count = 1 + int(succession_pressure > 0.36) + int(succession_pressure > 0.66)
        founding_year = founding_year_by_region.get(
            region_id,
            _clamp(620.0 + 240.0 * (region_id + 1), 260.0, 3200.0),
        )
        founding_event_id = founding_event_by_region.get(region_id, -1)
        parent_id = -1
        founder_id = -1
        for lineage_depth in range(dynasty_count):
            dynasty_id = len(dynasties)
            if lineage_depth == 0:
                founder_id = dynasty_id
            start_year = founding_year * (1.0 - lineage_depth / dynasty_count)
            end_year = (
                0.0
                if lineage_depth == dynasty_count - 1
                else founding_year * (1.0 - (lineage_depth + 1) / dynasty_count)
            )
            duration = max(0.0, start_year - end_year)
            dynasty_succession_pressure = _clamp(succession_pressure + 0.10 * lineage_depth)
            legitimacy = _clamp(
                0.34
                + 0.42 * continuity
                + 0.18 * float(region.get("mean_settlement_score", 0.0))
                - 0.22 * dynasty_succession_pressure
                - 0.10 * regional_conflict_pressure
            )
            dynastic_continuity = _clamp(
                0.26
                + 0.34 * legitimacy
                + 0.22 * (duration / max(1.0, founding_year))
                + 0.18 * (1.0 - dynasty_succession_pressure)
            )
            if lineage_depth == dynasty_count - 1:
                collapse_reason = "continuity"
            elif regional_conflict_pressure > 0.45:
                collapse_reason = "conflict_defeat"
            elif population_pressure > 0.68:
                collapse_reason = "migration_pressure"
            elif str(region.get("dominant_resource", "none")) != "none" and str(region.get("type", "")) == "mining_domain":
                collapse_reason = "resource_shock"
            elif int(region.get("route_count", 0)) == 0:
                collapse_reason = "trade_decline"
            else:
                collapse_reason = "succession_crisis"
            dynasties.append(
                {
                    "id": dynasty_id,
                    "region_id": region_id,
                    "culture_region_id": culture_id,
                    "language_region_id": language_id,
                    "parent_dynasty_id": parent_id,
                    "founder_dynasty_id": founder_id,
                    "successor_dynasty_id": -1,
                    "founding_event_id": founding_event_id if lineage_depth == 0 else -1,
                    "collapse_reason": collapse_reason,
                    "lineage_depth": lineage_depth,
                    "child_dynasty_count": 0,
                    "child_dynasty_ids": [],
                    "start_year_bp": start_year,
                    "end_year_bp": end_year,
                    "duration_years": duration,
                    "legitimacy_index": legitimacy,
                    "succession_pressure": dynasty_succession_pressure,
                    "dynastic_continuity_index": dynastic_continuity,
                }
            )
            parent_id = dynasty_id
    for dynasty in dynasties:
        parent_id = int(dynasty["parent_dynasty_id"])
        if not 0 <= parent_id < len(dynasties):
            continue
        parent = dynasties[parent_id]
        parent["child_dynasty_ids"].append(int(dynasty["id"]))
        parent["child_dynasty_count"] = len(parent["child_dynasty_ids"])
        successor_id = int(parent["successor_dynasty_id"])
        if successor_id < 0 or float(dynasty["start_year_bp"]) > float(dynasties[successor_id]["start_year_bp"]):
            parent["successor_dynasty_id"] = int(dynasty["id"])
    return dynasties


def _dynasty_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    exact_keys = (
        "id",
        "region_id",
        "culture_region_id",
        "language_region_id",
        "parent_dynasty_id",
        "founder_dynasty_id",
        "successor_dynasty_id",
        "founding_event_id",
        "collapse_reason",
        "lineage_depth",
        "child_dynasty_count",
        "child_dynasty_ids",
    )
    if any(actual.get(key) != expected[key] for key in exact_keys):
        return False
    return all(
        _close(actual.get(key), float(expected[key]), tolerance)
        for key, tolerance in (
            ("start_year_bp", 0.20),
            ("end_year_bp", 0.20),
            ("duration_years", 0.20),
            ("legitimacy_index", 0.003),
            ("succession_pressure", 0.003),
            ("dynastic_continuity_index", 0.003),
        )
    )


def _replay_valid(payload: dict[str, Any]) -> bool:
    summary = payload.get("summary", {})
    cells = payload.get("cells", [])
    regions = payload.get("political_regions", [])
    borders = payload.get("borders", [])
    flows = payload.get("trade_flows", [])
    cultures = payload.get("cultures", [])
    actual_populations = payload.get("population_regions", [])
    actual_conflicts = payload.get("conflicts", [])
    historical_events = payload.get("historical_events", [])
    actual_dynasties = payload.get("dynasties", [])
    collections = (
        cells,
        regions,
        borders,
        flows,
        cultures,
        actual_populations,
        actual_conflicts,
        historical_events,
        actual_dynasties,
    )
    if not isinstance(summary, dict) or not all(isinstance(value, list) for value in collections):
        return False
    if not all(all(isinstance(record, dict) for record in records) for records in collections):
        return False
    if (
        payload.get("population_region_model") != _population_model()
        or payload.get("conflict_model") != _conflict_model()
        or payload.get("dynasty_model") != _dynasty_model()
        or summary.get("population_region_model") != POPULATION_REGION_MODEL
        or summary.get("conflict_model") != CONFLICT_MODEL
        or summary.get("dynasty_model") != DYNASTY_MODEL
    ):
        return False
    if any(int(record.get("id", -1)) != index for records in collections for index, record in enumerate(records)):
        return False

    populations = _population_records(cells, regions, cultures)
    if len(actual_populations) != len(populations) or any(
        not _population_matches(actual, expected)
        for actual, expected in zip(actual_populations, populations, strict=True)
    ):
        return False
    conflicts = _conflict_records(cells, regions, borders, flows, cultures, populations)
    if len(actual_conflicts) != len(conflicts) or any(
        not _conflict_matches(actual, expected)
        for actual, expected in zip(actual_conflicts, conflicts, strict=True)
    ):
        return False
    dynasties = _dynasty_records(regions, cultures, historical_events, populations, conflicts)
    if len(actual_dynasties) != len(dynasties) or any(
        not _dynasty_matches(actual, expected)
        for actual, expected in zip(actual_dynasties, dynasties, strict=True)
    ):
        return False

    if int(summary.get("population_region_count", -1)) != len(populations):
        return False
    if not _relative_close(
        summary.get("estimated_world_population"),
        sum(float(population["estimated_population"]) for population in populations),
    ):
        return False
    mean_pressure = (
        sum(float(population["population_pressure"]) for population in populations) / len(populations)
        if populations
        else 0.0
    )
    if not _close(summary.get("mean_population_pressure"), mean_pressure, 0.002):
        return False

    precision = max(0, min(8, int(summary.get("output_float_precision", 4))))
    scale = 10.0**precision
    rounded_intensities = [math.floor(float(conflict["intensity"]) * scale + 0.5) / scale for conflict in conflicts]
    expected_counts = {
        "conflict_count": len(conflicts),
        "high_intensity_conflict_count": sum(value >= 0.65 for value in rounded_intensities),
        "high_economic_disruption_conflict_count": sum(
            float(conflict["economic_disruption_index"]) >= 0.65 for conflict in conflicts
        ),
    }
    if any(int(summary.get(key, -1)) != value for key, value in expected_counts.items()):
        return False
    divisor = len(conflicts) if conflicts else 1
    expected_means = {
        "mean_conflict_intensity": sum(float(conflict["intensity"]) for conflict in conflicts) / divisor,
        "mean_war_duration_years": sum(float(conflict["war_duration_years"]) for conflict in conflicts) / divisor,
        "mean_conflict_logistics_strain_index": sum(
            float(conflict["logistics_strain_index"]) for conflict in conflicts
        )
        / divisor,
        "mean_conflict_economic_disruption_index": sum(
            float(conflict["economic_disruption_index"]) for conflict in conflicts
        )
        / divisor,
        "mean_conflict_casualty_rate": sum(float(conflict["casualty_rate"]) for conflict in conflicts) / divisor,
        "max_conflict_casualty_rate": max((float(conflict["casualty_rate"]) for conflict in conflicts), default=0.0),
    }
    if not all(_close(summary.get(key), value, 0.004) for key, value in expected_means.items()):
        return False
    if not _relative_close(
        summary.get("total_mobilized_population"),
        sum(float(conflict["mobilized_population"]) for conflict in conflicts),
        0.001,
    ):
        return False
    expected_dynasty_counts = {
        "dynasty_count": len(dynasties),
        "dynastic_lineage_count": sum(int(dynasty["parent_dynasty_id"]) >= 0 for dynasty in dynasties),
        "dynasty_root_count": sum(int(dynasty["parent_dynasty_id"]) < 0 for dynasty in dynasties),
        "dynasty_successor_link_count": sum(int(dynasty["successor_dynasty_id"]) >= 0 for dynasty in dynasties),
        "max_dynasty_lineage_depth": max((int(dynasty["lineage_depth"]) for dynasty in dynasties), default=0),
    }
    if any(int(summary.get(key, -1)) != value for key, value in expected_dynasty_counts.items()):
        return False
    mean_continuity = (
        sum(float(dynasty["dynastic_continuity_index"]) for dynasty in dynasties) / len(dynasties)
        if dynasties
        else 0.0
    )
    return _close(summary.get("mean_dynastic_continuity_index"), mean_continuity, 0.004)


def validate_civilization_geography_replay(payload: dict[str, Any]) -> list[str]:
    try:
        valid = _replay_valid(payload)
    except (IndexError, KeyError, TypeError, ValueError, ZeroDivisionError):
        valid = False
    return [] if valid else ["population, conflict, or dynasty model causal replay invalid"]
