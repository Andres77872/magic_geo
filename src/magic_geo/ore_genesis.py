from __future__ import annotations

import math
from collections import Counter, deque
from typing import Any


ORE_RESOURCES = {"volcanic_arc_metals", "craton_iron_gold", "placer_metals", "geothermal"}
METAL_RESOURCES = {"volcanic_arc_metals", "craton_iron_gold", "placer_metals"}
ORE_SYSTEM_THRESHOLD = 0.34
HIGH_ORE_THRESHOLD = 0.50
HIGH_HYDROTHERMAL_THRESHOLD = 0.34
HIGH_FERTILITY_THRESHOLD = 0.42
HIGH_PLACER_THRESHOLD = 0.32


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _round(value: float) -> float:
    return round(value, 6)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _flow_accumulation_scale(cells: list[dict[str, Any]]) -> float:
    positive = sorted(
        max(0.0, float(cell.get("flow_accumulation", 0.0)))
        for cell in cells
        if max(0.0, float(cell.get("flow_accumulation", 0.0))) > 0.0
    )
    if not positive:
        return 1.0
    return max(1.0, positive[int(0.95 * (len(positive) - 1))])


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


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
    return _round(lat), _round(lon)


def _cells_by_id(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    cells = world.get("cells", [])
    if not isinstance(cells, list):
        return {}
    return {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}


def _ore_deposits_by_cell(world: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    deposits = world.get("resource_deposits", [])
    by_cell: dict[int, list[dict[str, Any]]] = {}
    if not isinstance(deposits, list):
        return by_cell
    for deposit in deposits:
        if not isinstance(deposit, dict) or str(deposit.get("resource", "")) not in ORE_RESOURCES:
            continue
        cell_id = int(deposit.get("cell_id", -1))
        if cell_id >= 0:
            by_cell.setdefault(cell_id, []).append(deposit)
    return by_cell


def _cell_indices(
    cell: dict[str, Any], flow_accumulation_scale: float
) -> dict[str, float]:
    resource = str(cell.get("resource", "none"))
    lithology = str(cell.get("lithology", "unknown"))
    landform = str(cell.get("landform", "unknown"))
    crust_type = str(cell.get("crust_type", "unknown"))
    boundary_type = str(cell.get("boundary_type", "unknown"))
    convergent = _clamp(float(cell.get("boundary_convergent", 0.0)))
    divergent = _clamp(float(cell.get("boundary_divergent", 0.0)))
    transform = _clamp(float(cell.get("boundary_transform", 0.0)))
    zone_strength = _clamp(float(cell.get("tectonic_zone_strength", 0.0)))
    volcanic = _clamp(float(cell.get("volcanic_potential_index", 0.0)))
    fault = _clamp(float(cell.get("fault_slip_rate_index", 0.0)))
    seismic = _clamp(float(cell.get("seismic_hazard_index", 0.0)))
    crust_age = _clamp(float(cell.get("crust_age_ma", 0.0)) / 2500.0)
    crust_thickness = _clamp(float(cell.get("crust_thickness_km", 0.0)) / 55.0)
    sediment = _clamp(float(cell.get("sediment_thickness_m", 0.0)) / 5.0)
    flow = _clamp(
        float(cell.get("flow_accumulation", 0.0))
        / max(1.0, flow_accumulation_scale)
    )
    river = 1.0 if bool(cell.get("is_river", False)) else 0.0
    relief = _clamp(abs(float(cell.get("elevation_m", 0.0)) - float(cell.get("filled_elevation_m", 0.0))) / 1200.0)

    arc_lithology = 0.12 if lithology in {"andesite", "basalt", "metamorphic"} else 0.04 if lithology == "granite" else 0.0
    craton_lithology = 0.14 if lithology in {"granite", "metamorphic"} else 0.04 if lithology == "sandstone" else 0.0
    placer_lithology = 0.08 if lithology in {"sandstone", "metamorphic", "granite"} else 0.0
    volcanic_landform = 0.14 if landform in {"volcanic_arc", "rift_valley"} else 0.0
    craton_landform = 0.08 if landform in {"stable_lowland", "mountain_belt"} else 0.0
    placer_landform = 0.18 if landform in {"river_valley", "floodplain", "delta", "alluvial_fan"} else 0.0
    arc_deposit = 0.24 if resource == "volcanic_arc_metals" else 0.0
    craton_deposit = 0.24 if resource == "craton_iron_gold" else 0.0
    placer_deposit = 0.26 if resource == "placer_metals" else 0.0
    geothermal_deposit = 0.18 if resource == "geothermal" else 0.0

    hydrothermal = _clamp(
        convergent * 0.25
        + divergent * 0.14
        + volcanic * 0.24
        + fault * 0.14
        + zone_strength * 0.10
        + volcanic_landform
        + arc_lithology
        + arc_deposit
        + geothermal_deposit
    )
    fertility = _clamp(
        crust_age * 0.20
        + crust_thickness * 0.12
        + (0.18 if crust_type == "craton" else 0.0)
        + convergent * 0.12
        + volcanic * 0.10
        + craton_lithology
        + craton_landform
        + arc_deposit * 0.50
        + craton_deposit
    )
    structural = _clamp(
        fault * 0.24
        + seismic * 0.16
        + transform * 0.14
        + zone_strength * 0.16
        + relief * 0.08
        + (0.08 if boundary_type in {"convergent", "transform", "divergent"} else 0.0)
        + arc_deposit * 0.20
        + craton_deposit * 0.14
    )
    placer = _clamp(
        flow * 0.24
        + river * 0.18
        + sediment * 0.14
        + placer_landform
        + placer_lithology
        + placer_deposit
        + _clamp(convergent + fertility * 0.5) * 0.08
    )
    ore = _clamp(
        max(hydrothermal, fertility, placer) * 0.34
        + hydrothermal * 0.20
        + fertility * 0.20
        + structural * 0.14
        + placer * 0.12
        + (0.12 if resource in ORE_RESOURCES else 0.0)
    )
    return {
        "ore": ore,
        "hydrothermal": hydrothermal,
        "fertility": fertility,
        "structural": structural,
        "placer": placer,
    }


def _system_type(cells: list[dict[str, Any]], metrics_by_id: dict[int, dict[str, float]]) -> str:
    resource_counts = Counter(str(cell.get("resource", "none")) for cell in cells)
    geothermal_count = resource_counts.get("geothermal", 0)
    if geothermal_count > max(
        resource_counts.get("volcanic_arc_metals", 0),
        resource_counts.get("craton_iron_gold", 0),
        resource_counts.get("placer_metals", 0),
        0,
    ):
        return "rift_geothermal_hydrothermal"
    if resource_counts.get("placer_metals", 0) > max(
        resource_counts.get("volcanic_arc_metals", 0),
        resource_counts.get("craton_iron_gold", 0),
        geothermal_count,
        0,
    ):
        return "fluvial_placer_system"
    if resource_counts.get("craton_iron_gold", 0) > 0:
        return "ancient_craton_metallogenic"
    if resource_counts.get("volcanic_arc_metals", 0) > 0:
        return "subduction_arc_hydrothermal"
    if resource_counts.get("geothermal", 0) > 0:
        return "rift_geothermal_hydrothermal"
    hydrothermal = _mean([metrics_by_id[int(cell.get("id", -1))]["hydrothermal"] for cell in cells])
    fertility = _mean([metrics_by_id[int(cell.get("id", -1))]["fertility"] for cell in cells])
    placer = _mean([metrics_by_id[int(cell.get("id", -1))]["placer"] for cell in cells])
    ranked = sorted(
        [
            ("subduction_arc_hydrothermal", hydrothermal),
            ("ancient_craton_metallogenic", fertility),
            ("fluvial_placer_system", placer),
        ],
        key=lambda item: (-item[1], item[0]),
    )
    if len(ranked) > 1 and ranked[1][1] >= ORE_SYSTEM_THRESHOLD and ranked[0][1] - ranked[1][1] <= 0.05:
        return "mixed_metallogenic_province"
    return ranked[0][0]


def _connected_components(candidate_ids: set[int], cells_by_id: dict[int, dict[str, Any]]) -> list[list[int]]:
    components: list[list[int]] = []
    remaining = set(candidate_ids)
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue: deque[int] = deque([start])
        component = [start]
        while queue:
            current_id = queue.popleft()
            current = cells_by_id[current_id]
            for raw_neighbor_id in current.get("neighbors", []):
                neighbor_id = int(raw_neighbor_id)
                if neighbor_id not in remaining:
                    continue
                remaining.remove(neighbor_id)
                queue.append(neighbor_id)
                component.append(neighbor_id)
        components.append(sorted(component))
    return sorted(components, key=lambda item: (min(item), len(item)))


def _step(
    index: int,
    process: str,
    active_ids: list[int],
    cell_ids: list[int],
    deposits: list[dict[str, Any]],
    cells_by_id: dict[int, dict[str, Any]],
    metric_key: str,
    cell_field: str,
) -> dict[str, Any]:
    selected_ids = active_ids or cell_ids
    selected_cells = [cells_by_id[cell_id] for cell_id in selected_ids]
    selected_deposit_ids = sorted(
        int(deposit.get("id", -1)) for deposit in deposits if int(deposit.get("cell_id", -1)) in set(selected_ids)
    )
    return {
        "step_index": index,
        "process": process,
        "active_cell_ids": selected_ids,
        "active_cell_count": len(selected_ids),
        "linked_resource_deposit_ids": selected_deposit_ids,
        "mean_ore_genesis_potential_index": _round(_mean([float(cell.get("ore_genesis_potential_index", 0.0)) for cell in selected_cells])),
        "mean_process_intensity_index": _round(_mean([float(cell.get(cell_field, 0.0)) for cell in selected_cells])),
        "process_metric": metric_key,
    }


def _formation_steps(
    cell_ids: list[int],
    deposits: list[dict[str, Any]],
    system_type: str,
    cells_by_id: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    source_ids = [
        cell_id
        for cell_id in cell_ids
        if float(cells_by_id[cell_id].get("metallogenic_fertility_index", 0.0)) >= HIGH_FERTILITY_THRESHOLD
        or str(cells_by_id[cell_id].get("resource", "none")) in {"volcanic_arc_metals", "craton_iron_gold"}
    ]
    hydrothermal_ids = [
        cell_id
        for cell_id in cell_ids
        if float(cells_by_id[cell_id].get("hydrothermal_alteration_index", 0.0)) >= HIGH_HYDROTHERMAL_THRESHOLD
        or str(cells_by_id[cell_id].get("resource", "none")) in {"volcanic_arc_metals", "geothermal"}
    ]
    structural_ids = [
        cell_id
        for cell_id in cell_ids
        if float(cells_by_id[cell_id].get("ore_structural_control_index", 0.0)) >= 0.30
        or str(cells_by_id[cell_id].get("resource", "none")) in {"volcanic_arc_metals", "craton_iron_gold"}
    ]
    placer_ids = [
        cell_id
        for cell_id in cell_ids
        if float(cells_by_id[cell_id].get("placer_concentration_index", 0.0)) >= HIGH_PLACER_THRESHOLD
        or str(cells_by_id[cell_id].get("resource", "none")) == "placer_metals"
    ]
    steps = [
        _step(0, "source_fertility", sorted(source_ids), cell_ids, deposits, cells_by_id, "metallogenic_fertility", "metallogenic_fertility_index")
    ]
    if system_type == "fluvial_placer_system":
        steps.append(
            _step(1, "erosion_transport", sorted(placer_ids), cell_ids, deposits, cells_by_id, "placer_concentration", "placer_concentration_index")
        )
        steps.append(
            _step(2, "placer_concentration", sorted(placer_ids), cell_ids, deposits, cells_by_id, "placer_concentration", "placer_concentration_index")
        )
    else:
        steps.append(
            _step(1, "hydrothermal_mobilization", sorted(hydrothermal_ids), cell_ids, deposits, cells_by_id, "hydrothermal_alteration", "hydrothermal_alteration_index")
        )
        steps.append(
            _step(2, "structural_concentration", sorted(structural_ids), cell_ids, deposits, cells_by_id, "ore_structural_control", "ore_structural_control_index")
        )
    return steps


def _build_ore_genesis(world: dict[str, Any], *, economic_availability: bool = False) -> dict[str, Any]:
    cells_by_id = _cells_by_id(world)
    if not cells_by_id and not economic_availability:
        return world

    deposits_by_cell = _ore_deposits_by_cell(world)
    flow_accumulation_scale = _flow_accumulation_scale(
        list(cells_by_id.values())
    )
    metrics_by_id = {
        cell_id: _cell_indices(cell, flow_accumulation_scale)
        for cell_id, cell in cells_by_id.items()
    }
    for cell_id, cell in cells_by_id.items():
        metrics = metrics_by_id[cell_id]
        cell["ore_genesis_potential_index"] = _round(metrics["ore"])
        cell["hydrothermal_alteration_index"] = _round(metrics["hydrothermal"])
        cell["metallogenic_fertility_index"] = _round(metrics["fertility"])
        cell["ore_structural_control_index"] = _round(metrics["structural"])
        cell["placer_concentration_index"] = _round(metrics["placer"])
        cell["ore_genesis_system_id"] = -1

    candidate_ids = {
        cell_id
        for cell_id, cell in cells_by_id.items()
        if metrics_by_id[cell_id]["ore"] >= ORE_SYSTEM_THRESHOLD or str(cell.get("resource", "none")) in ORE_RESOURCES
    }
    systems: list[dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    assigned_ids: set[int] = set()
    for component_ids in _connected_components(candidate_ids, cells_by_id):
        if any(cell_id in assigned_ids for cell_id in component_ids):
            continue
        component_cells = [cells_by_id[cell_id] for cell_id in component_ids]
        max_ore = max(metrics_by_id[cell_id]["ore"] for cell_id in component_ids)
        deposits = sorted(
            [deposit for cell_id in component_ids for deposit in deposits_by_cell.get(cell_id, [])],
            key=lambda deposit: int(deposit.get("id", -1)),
        )
        if not deposits and max_ore < HIGH_ORE_THRESHOLD:
            continue
        system_type = _system_type(component_cells, metrics_by_id)
        area = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in component_cells)
        centroid_lat, centroid_lon = _centroid(component_cells)
        resource_counts = Counter(str(cell.get("resource", "none")) for cell in component_cells)
        lithology_counts = Counter(str(cell.get("lithology", "unknown")) for cell in component_cells)
        landform_counts = Counter(str(cell.get("landform", "unknown")) for cell in component_cells)
        boundary_counts = Counter(str(cell.get("boundary_type", "unknown")) for cell in component_cells)
        plate_ids = sorted({int(cell.get("plate_id", -1)) for cell in component_cells if int(cell.get("plate_id", -1)) >= 0})
        tectonic_zone_ids = sorted(
            {
                int(cell.get(zone_key, -1))
                for cell in component_cells
                for zone_key in ("collision_zone_id", "subduction_zone_id", "rift_zone_id")
                if int(cell.get(zone_key, -1)) >= 0
            }
        )
        fault_system_ids = sorted({int(cell.get("fault_system_id", -1)) for cell in component_cells if int(cell.get("fault_system_id", -1)) >= 0})
        deposit_ids = [int(deposit.get("id", -1)) for deposit in deposits]
        representative_id = sorted(
            component_ids,
            key=lambda cell_id: (-float(cells_by_id[cell_id].get("ore_genesis_potential_index", 0.0)), cell_id),
        )[0]
        steps = _formation_steps(component_ids, deposits, system_type, cells_by_id)
        systems.append(
            {
                "id": len(systems),
                "system_type": system_type,
                "cell_ids": component_ids,
                "cell_count": len(component_ids),
                "area_km2": _round(area),
                "centroid_lat_deg": centroid_lat,
                "centroid_lon_deg": centroid_lon,
                "representative_cell_id": representative_id,
                "resource_deposit_ids": deposit_ids,
                "resource_deposit_count": len(deposit_ids),
                "metal_deposit_count": sum(1 for deposit in deposits if str(deposit.get("resource", "")) in METAL_RESOURCES),
                "geothermal_deposit_count": sum(1 for deposit in deposits if str(deposit.get("resource", "")) == "geothermal"),
                "placer_deposit_count": sum(1 for deposit in deposits if str(deposit.get("resource", "")) == "placer_metals"),
                "dominant_resource": _primary_key(resource_counts, "none"),
                "dominant_lithology": _primary_key(lithology_counts, "unknown"),
                "dominant_landform": _primary_key(landform_counts, "unknown"),
                "dominant_tectonic_context": _primary_key(boundary_counts, "unknown"),
                "plate_ids": plate_ids,
                "tectonic_zone_ids": tectonic_zone_ids,
                "fault_system_ids": fault_system_ids,
                "mean_ore_genesis_potential_index": _round(_mean([metrics_by_id[cell_id]["ore"] for cell_id in component_ids])),
                "max_ore_genesis_potential_index": _round(max_ore),
                "mean_hydrothermal_alteration_index": _round(_mean([metrics_by_id[cell_id]["hydrothermal"] for cell_id in component_ids])),
                "mean_metallogenic_fertility_index": _round(_mean([metrics_by_id[cell_id]["fertility"] for cell_id in component_ids])),
                "mean_ore_structural_control_index": _round(_mean([metrics_by_id[cell_id]["structural"] for cell_id in component_ids])),
                "mean_placer_concentration_index": _round(_mean([metrics_by_id[cell_id]["placer"] for cell_id in component_ids])),
                "mean_resource_viability_index": _round(
                    _mean([float(deposit.get("geographic_economic_viability_baseline_index", 0.0) if economic_availability else deposit.get("economic_viability_index", 0.0)) for deposit in deposits])
                )
                if deposits
                else 0.0,
                "ore_genesis_confidence_index": _round(
                    _clamp(
                        _mean([metrics_by_id[cell_id]["ore"] for cell_id in component_ids]) * 0.34
                        + _mean([metrics_by_id[cell_id]["hydrothermal"] for cell_id in component_ids]) * 0.14
                        + _mean([metrics_by_id[cell_id]["fertility"] for cell_id in component_ids]) * 0.16
                        + _mean([metrics_by_id[cell_id]["structural"] for cell_id in component_ids]) * 0.12
                        + _clamp(len(deposit_ids) / max(1.0, float(len(component_ids)))) * 0.16
                        + _clamp(len(plate_ids) / 3.0) * 0.08
                    )
                ),
                "formation_step_count": len(steps),
                "formation_steps": steps,
            }
        )
        if economic_availability:
            count = sum(d["economic_viability_supported"] for d in deposits)
            complete = count == len(deposits)
            systems[-1].update({
                "mean_geographic_resource_viability_baseline_index": systems[-1]["mean_resource_viability_index"],
                "mean_resource_viability_index": _round(_mean([d["economic_viability_index"] for d in deposits])) if complete else None,
                "mean_resource_viability_supported": complete,
                "resource_viability_applicable_deposit_count": len(deposits),
                "resource_viability_supported_deposit_count": count,
            })
        system_id = len(systems) - 1
        type_counts[system_type] += 1
        assigned_ids.update(component_ids)
        for cell_id in component_ids:
            cells_by_id[cell_id]["ore_genesis_system_id"] = system_id

    cells = list(cells_by_id.values())
    cell_count = len(cells)
    divisor = float(cell_count) if cell_count else 1.0
    summary = world.setdefault("summary", {})
    world["ore_genesis_model"] = {
        "model_type": "causal_tectonic_lithologic_ore_genesis_diagnostics_v2",
        "flow_accumulation_normalization_model": "positive_cell_p95_v1",
        "flow_accumulation_scale": _round(flow_accumulation_scale),
        "flow_accumulation_units": "runoff_mm_y_times_upstream_area_km2",
        "physical_time_resolved": False,
        "model_limitation": "diagnostic metallogenic potential without reactive geochemical transport",
    }
    summary["ore_genesis_system_count"] = len(systems)
    summary["ore_genesis_cell_count"] = sum(1 for cell in cells if int(cell.get("ore_genesis_system_id", -1)) >= 0)
    summary["ore_resource_deposit_count"] = sum(1 for deposits in deposits_by_cell.values() for _deposit in deposits)
    summary["high_ore_genesis_potential_cell_count"] = sum(
        1 for cell in cells if float(cell.get("ore_genesis_potential_index", 0.0)) >= HIGH_ORE_THRESHOLD
    )
    summary["high_hydrothermal_alteration_cell_count"] = sum(
        1 for cell in cells if float(cell.get("hydrothermal_alteration_index", 0.0)) >= HIGH_HYDROTHERMAL_THRESHOLD
    )
    summary["high_metallogenic_fertility_cell_count"] = sum(
        1 for cell in cells if float(cell.get("metallogenic_fertility_index", 0.0)) >= HIGH_FERTILITY_THRESHOLD
    )
    summary["high_placer_concentration_cell_count"] = sum(
        1 for cell in cells if float(cell.get("placer_concentration_index", 0.0)) >= HIGH_PLACER_THRESHOLD
    )
    summary["ore_genesis_total_area_km2"] = _round(sum(float(system.get("area_km2", 0.0)) for system in systems))
    summary["mean_ore_genesis_potential_index"] = _round(
        sum(float(cell.get("ore_genesis_potential_index", 0.0)) for cell in cells) / divisor
    )
    summary["mean_hydrothermal_alteration_index"] = _round(
        sum(float(cell.get("hydrothermal_alteration_index", 0.0)) for cell in cells) / divisor
    )
    summary["mean_metallogenic_fertility_index"] = _round(
        sum(float(cell.get("metallogenic_fertility_index", 0.0)) for cell in cells) / divisor
    )
    summary["mean_ore_structural_control_index"] = _round(
        sum(float(cell.get("ore_structural_control_index", 0.0)) for cell in cells) / divisor
    )
    summary["mean_placer_concentration_index"] = _round(
        sum(float(cell.get("placer_concentration_index", 0.0)) for cell in cells) / divisor
    )
    summary["ore_genesis_system_type_counts"] = dict(sorted(type_counts.items()))
    world["ore_genesis_systems"] = systems
    return world


def enrich_world_with_ore_genesis(world: dict[str, Any]) -> dict[str, Any]:
    from .ore_resource_availability_validation import version, POLICY, CELL_FIELDS, SUMMARY_FIELDS, TOP_FIELDS, validate_ore_resource_availability, require_physical_sources
    if version(world) == 2:
        return _build_ore_genesis(world)
    from .biological_resource_validation import audit_biological_resource_deposits
    audit_biological_resource_deposits(world)
    require_physical_sources(world)
    staged = {**world, "cells": [dict(c) for c in world["cells"]], "summary": dict(world["summary"])}
    _build_ore_genesis(staged, economic_availability=True)
    staged["ore_genesis_model"].update(POLICY)
    errors = validate_ore_resource_availability(staged)
    if errors:
        raise ValueError(errors[0])
    for original, result in zip(world["cells"], staged["cells"]):
        original.update({key: result[key] for key in CELL_FIELDS})
    world.update({key: staged[key] for key in TOP_FIELDS})
    world["summary"].update({key: staged["summary"][key] for key in SUMMARY_FIELDS})
    return world
