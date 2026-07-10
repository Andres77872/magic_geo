from __future__ import annotations

import heapq
import math
from collections import Counter
from typing import Any


SOURCE_ROCK_THRESHOLD = 0.42
MATURE_SOURCE_THRESHOLD = 0.42
TRAP_THRESHOLD = 0.34
HIGH_ACCUMULATION_THRESHOLD = 0.50
MAX_PATHS_PER_SYSTEM = 4

SOURCE_LANDFORMS = {"delta", "floodplain", "lacustrine_basin", "inland_sea", "continental_shelf", "stable_lowland"}
RESERVOIR_LANDFORMS = {"delta", "floodplain", "river_valley", "coastal_plain", "continental_shelf", "rift_valley"}
SEAL_LANDFORMS = {"lacustrine_basin", "inland_sea", "salt_flat", "stable_lowland", "continental_shelf"}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _round(value: float) -> float:
    return round(value, 6)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _primary_key(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _cell_distance_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    lat_a = math.radians(float(a.get("lat_deg", 0.0)))
    lat_b = math.radians(float(b.get("lat_deg", 0.0)))
    lon_a = math.radians(float(a.get("lon_deg", 0.0)))
    lon_b = math.radians(float(b.get("lon_deg", 0.0)))
    dlon = lon_b - lon_a
    while dlon > math.pi:
        dlon -= math.tau
    while dlon < -math.pi:
        dlon += math.tau
    dlat = lat_b - lat_a
    hav = math.sin(dlat * 0.5) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon * 0.5) ** 2
    return 6371.0 * 2.0 * math.asin(min(1.0, math.sqrt(hav)))


def _path_distance_km(path: list[int], cells_by_id: dict[int, dict[str, Any]]) -> float:
    total = 0.0
    for left, right in zip(path, path[1:]):
        total += _cell_distance_km(cells_by_id[left], cells_by_id[right])
    return total


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


def _deposits_by_id(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    deposits = world.get("resource_deposits", [])
    if not isinstance(deposits, list):
        return {}
    return {int(deposit.get("id", -1)): deposit for deposit in deposits if isinstance(deposit, dict)}


def _cell_indices(cell: dict[str, Any], system: dict[str, Any]) -> dict[str, float]:
    lithology = str(cell.get("lithology", "unknown"))
    landform = str(cell.get("landform", "unknown"))
    resource = str(cell.get("resource", "none"))
    sediment = _clamp(float(cell.get("sediment_thickness_m", 0.0)) / 6.0)
    subsidence = _clamp(float(system.get("mean_subsidence_index", 0.0)))
    system_source = _clamp(float(system.get("source_rock_index", 0.0)))
    system_reservoir = _clamp(float(system.get("reservoir_quality_index", 0.0)))
    system_seal = _clamp(float(system.get("seal_quality_index", 0.0)))
    system_trap = _clamp(float(system.get("structural_trap_index", 0.0)))
    petroleum = _clamp(float(system.get("petroleum_potential_index", 0.0)))
    gas = _clamp(float(system.get("gas_potential_index", 0.0)))
    salt = _clamp(float(system.get("evaporite_salt_potential_index", 0.0)))
    age_ma = max(0.0, float(system.get("depositional_age_ma", 0.0)))
    salinity = _clamp(float(cell.get("soil_salinity_index", 0.0)))
    seismic = _clamp(float(cell.get("seismic_hazard_index", 0.0)))
    fault_slip = _clamp(float(cell.get("fault_slip_rate_index", 0.0)))
    volcanic = _clamp(float(cell.get("volcanic_potential_index", 0.0)))
    divergent = _clamp(float(cell.get("boundary_divergent", 0.0)))
    convergent = _clamp(float(cell.get("boundary_convergent", 0.0)))

    source_lithology = 0.16 if lithology == "shale" else (0.10 if lithology == "limestone" else 0.06 if lithology == "sandstone" else 0.0)
    reservoir_lithology = 0.18 if lithology == "sandstone" else (0.12 if lithology == "limestone" else 0.04 if lithology == "shale" else 0.0)
    seal_lithology = 0.18 if lithology == "shale" else (0.08 if lithology == "limestone" else 0.02)
    source_landform = 0.10 if landform in SOURCE_LANDFORMS or "basin" in landform else 0.0
    reservoir_landform = 0.12 if landform in RESERVOIR_LANDFORMS else 0.0
    seal_landform = 0.10 if landform in SEAL_LANDFORMS or bool(cell.get("is_closed_basin", False)) else 0.0
    fuel_evidence = 0.10 if resource == "sedimentary_fuels" else 0.0
    evaporite_evidence = 0.08 if resource == "evaporites" else 0.0

    oil_window = _clamp(1.0 - abs(age_ma - 95.0) / 130.0)
    gas_window = _clamp((age_ma - 55.0) / 185.0)
    burial_heat = _clamp(sediment * 0.65 + subsidence * 0.22 + (divergent + convergent + volcanic) * 0.08)
    thermal_overprint = _clamp((seismic + fault_slip + volcanic) / 2.2)

    source = _clamp(system_source * 0.42 + sediment * 0.18 + source_lithology + source_landform + fuel_evidence + petroleum * 0.08)
    maturation = _clamp(
        burial_heat * 0.32
        + oil_window * 0.24
        + gas_window * 0.12
        + subsidence * 0.14
        + system_source * 0.10
        + gas * 0.08
        - max(0.0, thermal_overprint - 0.70) * 0.16
    )
    reservoir = _clamp(system_reservoir * 0.46 + reservoir_lithology + reservoir_landform + sediment * 0.08 + petroleum * 0.08)
    seal = _clamp(system_seal * 0.50 + seal_lithology + seal_landform + salinity * 0.08 + salt * 0.08 + evaporite_evidence)
    leakage_pressure = _clamp(seismic * 0.16 + fault_slip * 0.14 + volcanic * 0.10)
    trap = _clamp(
        system_trap * 0.36
        + seal * 0.26
        + reservoir * 0.12
        + subsidence * 0.10
        + _clamp(1.0 - float(cell.get("erosion_rate", 0.0)) / 0.08) * 0.08
        + evaporite_evidence * 0.08
        - leakage_pressure
    )
    migration = _clamp(
        maturation * 0.20
        + reservoir * 0.20
        + max(petroleum, gas) * 0.20
        + source * 0.12
        + seal * 0.08
        + trap * 0.10
        + _clamp(1.0 - leakage_pressure) * 0.10
    )
    accumulation = _clamp(source * 0.20 + maturation * 0.20 + reservoir * 0.18 + seal * 0.16 + trap * 0.18 + migration * 0.08)
    return {
        "source": source,
        "maturation": maturation,
        "reservoir": reservoir,
        "seal": seal,
        "migration": migration,
        "trap": trap,
        "accumulation": accumulation,
        "leakage_pressure": leakage_pressure,
    }


def _best_path(
    source_id: int,
    trap_id: int,
    allowed_ids: set[int],
    cells_by_id: dict[int, dict[str, Any]],
    metrics_by_id: dict[int, dict[str, float]],
) -> list[int]:
    if source_id == trap_id:
        return [source_id]
    queue: list[tuple[float, int]] = [(0.0, source_id)]
    best_cost = {source_id: 0.0}
    previous: dict[int, int] = {}
    while queue:
        cost, cell_id = heapq.heappop(queue)
        if cost > best_cost.get(cell_id, math.inf):
            continue
        if cell_id == trap_id:
            break
        cell = cells_by_id[cell_id]
        for raw_neighbor_id in cell.get("neighbors", []):
            neighbor_id = int(raw_neighbor_id)
            if neighbor_id not in allowed_ids or neighbor_id not in cells_by_id:
                continue
            neighbor = cells_by_id[neighbor_id]
            relief_penalty = _clamp(abs(float(neighbor.get("elevation_m", 0.0)) - float(cell.get("elevation_m", 0.0))) / 3500.0) * 0.20
            fault_penalty = _clamp(float(neighbor.get("seismic_hazard_index", 0.0))) * 0.08
            migration_bonus = metrics_by_id.get(neighbor_id, {}).get("migration", 0.0) * 0.42
            next_cost = cost + 1.0 + relief_penalty + fault_penalty - migration_bonus
            if next_cost >= best_cost.get(neighbor_id, math.inf):
                continue
            best_cost[neighbor_id] = next_cost
            previous[neighbor_id] = cell_id
            heapq.heappush(queue, (next_cost, neighbor_id))
    if trap_id not in previous:
        return []
    path = [trap_id]
    current = trap_id
    while current != source_id:
        current = previous[current]
        path.append(current)
    return list(reversed(path))


def _step_record(
    step_index: int,
    source_id: int,
    trap_id: int,
    path: list[int],
    cells_by_id: dict[int, dict[str, Any]],
    metrics_by_id: dict[int, dict[str, float]],
    system: dict[str, Any],
) -> dict[str, Any]:
    path_metrics = [metrics_by_id[cell_id] for cell_id in path]
    path_cells = [cells_by_id[cell_id] for cell_id in path]
    source_metrics = metrics_by_id[source_id]
    trap_metrics = metrics_by_id[trap_id]
    mean_migration = _mean([metrics["migration"] for metrics in path_metrics])
    mean_trap = _mean([metrics["trap"] for metrics in path_metrics])
    mean_leakage = _mean([metrics["leakage_pressure"] for metrics in path_metrics])
    charge = _clamp(
        source_metrics["source"] * 0.30
        + source_metrics["maturation"] * 0.26
        + max(float(system.get("petroleum_potential_index", 0.0)), float(system.get("gas_potential_index", 0.0))) * 0.18
        + mean_migration * 0.18
        + trap_metrics["accumulation"] * 0.08
    )
    leakage = _clamp(mean_leakage * 0.42 + (1.0 - mean_trap) * 0.36 + (1.0 - _mean([metrics["seal"] for metrics in path_metrics])) * 0.18)
    probability = _clamp(charge * 0.44 + mean_migration * 0.30 + trap_metrics["accumulation"] * 0.26 - leakage * 0.22)
    return {
        "step_index": step_index,
        "source_cell_id": source_id,
        "target_trap_cell_id": trap_id,
        "path_cell_ids": path,
        "path_length_cell_count": len(path),
        "migration_distance_km": _round(_path_distance_km(path, cells_by_id)),
        "mean_path_migration_index": _round(mean_migration),
        "mean_path_trap_integrity_index": _round(mean_trap),
        "hydrocarbon_charge_index": _round(charge),
        "leakage_risk_index": _round(leakage),
        "accumulation_probability_index": _round(probability),
    }


def _system_type(system: dict[str, Any], mean_source: float, mean_maturation: float, leakage: float) -> str:
    petroleum = _clamp(float(system.get("petroleum_potential_index", 0.0)))
    gas = _clamp(float(system.get("gas_potential_index", 0.0)))
    if mean_source >= SOURCE_ROCK_THRESHOLD and mean_maturation < 0.34:
        return "immature_source_basin"
    if leakage >= 0.58:
        return "breached_trap_complex"
    if gas > petroleum + 0.04 or mean_maturation >= 0.68:
        return "gas_migration_fairway"
    if abs(petroleum - gas) <= 0.05:
        return "mixed_hydrocarbon_fairway"
    return "oil_migration_fairway"


def enrich_world_with_petroleum_migration(world: dict[str, Any]) -> dict[str, Any]:
    cells_by_id = _cells_by_id(world)
    if not cells_by_id:
        return world
    sedimentary_systems = world.get("sedimentary_resource_systems", [])
    if not isinstance(sedimentary_systems, list):
        return world

    for cell in cells_by_id.values():
        cell["petroleum_source_rock_index"] = 0.0
        cell["petroleum_maturation_index"] = 0.0
        cell["petroleum_migration_path_index"] = 0.0
        cell["petroleum_trap_integrity_index"] = 0.0
        cell["petroleum_accumulation_index"] = 0.0
        cell["petroleum_system_id"] = -1

    deposits_by_id = _deposits_by_id(world)
    records: list[dict[str, Any]] = []
    type_counts: Counter[str] = Counter()
    assigned_cell_ids: set[int] = set()

    for system in sedimentary_systems:
        if not isinstance(system, dict):
            continue
        raw_cell_ids = system.get("cell_ids", [])
        if not isinstance(raw_cell_ids, list):
            continue
        system_cell_ids = [int(cell_id) for cell_id in raw_cell_ids if int(cell_id) in cells_by_id]
        if not system_cell_ids:
            continue
        metrics_by_id = {cell_id: _cell_indices(cells_by_id[cell_id], system) for cell_id in system_cell_ids}
        for cell_id, metrics in metrics_by_id.items():
            cell = cells_by_id[cell_id]
            if metrics["accumulation"] >= float(cell.get("petroleum_accumulation_index", 0.0)):
                cell["petroleum_source_rock_index"] = _round(metrics["source"])
                cell["petroleum_maturation_index"] = _round(metrics["maturation"])
                cell["petroleum_migration_path_index"] = _round(metrics["migration"])
                cell["petroleum_trap_integrity_index"] = _round(metrics["trap"])
                cell["petroleum_accumulation_index"] = _round(metrics["accumulation"])

        max_hydrocarbon_potential = max(
            _clamp(float(system.get("petroleum_potential_index", 0.0))),
            _clamp(float(system.get("gas_potential_index", 0.0))),
        )
        source_candidates = [
            cell_id
            for cell_id, metrics in metrics_by_id.items()
            if metrics["source"] >= SOURCE_ROCK_THRESHOLD and metrics["maturation"] >= 0.36
        ]
        if not source_candidates:
            source_candidates = [
                cell_id
                for cell_id, metrics in metrics_by_id.items()
                if metrics["source"] >= 0.36 and metrics["maturation"] >= 0.30 and max_hydrocarbon_potential >= 0.42
            ][:1]
        trap_candidates = [
            cell_id
            for cell_id, metrics in metrics_by_id.items()
            if metrics["trap"] >= 0.30 and metrics["reservoir"] >= 0.24 and metrics["seal"] >= 0.18 and metrics["accumulation"] >= 0.34
        ]
        if not source_candidates or not trap_candidates:
            continue

        source_candidates = sorted(
            source_candidates,
            key=lambda cell_id: (
                -metrics_by_id[cell_id]["source"] * metrics_by_id[cell_id]["maturation"],
                cell_id,
            ),
        )
        trap_candidates = sorted(
            trap_candidates,
            key=lambda cell_id: (-metrics_by_id[cell_id]["accumulation"], -metrics_by_id[cell_id]["trap"], cell_id),
        )
        allowed_ids = set(system_cell_ids)
        steps: list[dict[str, Any]] = []
        used_pairs: set[tuple[int, int]] = set()
        for source_id in source_candidates[:3]:
            for trap_id in trap_candidates[:4]:
                if (source_id, trap_id) in used_pairs:
                    continue
                path = _best_path(source_id, trap_id, allowed_ids, cells_by_id, metrics_by_id)
                if not path:
                    continue
                step = _step_record(len(steps), source_id, trap_id, path, cells_by_id, metrics_by_id, system)
                if float(step["accumulation_probability_index"]) < 0.34 and max_hydrocarbon_potential < 0.48:
                    continue
                steps.append(step)
                used_pairs.add((source_id, trap_id))
                if len(steps) >= MAX_PATHS_PER_SYSTEM:
                    break
            if len(steps) >= MAX_PATHS_PER_SYSTEM:
                break
        if not steps:
            continue

        migration_cell_ids = sorted({cell_id for step in steps for cell_id in step["path_cell_ids"]})
        source_cell_ids = sorted(
            {
                cell_id
                for cell_id in source_candidates
                if metrics_by_id[cell_id]["source"] >= SOURCE_ROCK_THRESHOLD or cell_id in {step["source_cell_id"] for step in steps}
            }
        )
        reservoir_cell_ids = sorted(cell_id for cell_id, metrics in metrics_by_id.items() if metrics["reservoir"] >= 0.42)
        seal_cell_ids = sorted(cell_id for cell_id, metrics in metrics_by_id.items() if metrics["seal"] >= 0.40)
        trap_cell_ids = sorted(
            {
                cell_id
                for cell_id in trap_candidates
                if metrics_by_id[cell_id]["trap"] >= TRAP_THRESHOLD or cell_id in {step["target_trap_cell_id"] for step in steps}
            }
        )
        candidate_fairway_cell_ids = (
            set(source_cell_ids)
            | set(migration_cell_ids)
            | set(reservoir_cell_ids)
            | set(seal_cell_ids)
            | set(trap_cell_ids)
        )
        if not candidate_fairway_cell_ids or candidate_fairway_cell_ids & assigned_cell_ids:
            continue
        fairway_cell_ids = sorted(candidate_fairway_cell_ids)

        source_cell_ids = [cell_id for cell_id in source_cell_ids if cell_id in fairway_cell_ids]
        migration_cell_ids = [cell_id for cell_id in migration_cell_ids if cell_id in fairway_cell_ids]
        reservoir_cell_ids = [cell_id for cell_id in reservoir_cell_ids if cell_id in fairway_cell_ids]
        seal_cell_ids = [cell_id for cell_id in seal_cell_ids if cell_id in fairway_cell_ids]
        trap_cell_ids = [cell_id for cell_id in trap_cell_ids if cell_id in fairway_cell_ids]
        fairway_cells = [cells_by_id[cell_id] for cell_id in fairway_cell_ids]
        fairway_metrics = [metrics_by_id[cell_id] for cell_id in fairway_cell_ids]
        area_km2 = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in fairway_cells)
        centroid_lat, centroid_lon = _centroid(fairway_cells)
        mean_source = _mean([metrics["source"] for metrics in fairway_metrics])
        mean_maturation = _mean([metrics["maturation"] for metrics in fairway_metrics])
        mean_migration = _mean([metrics["migration"] for metrics in fairway_metrics])
        mean_reservoir = _mean([metrics["reservoir"] for metrics in fairway_metrics])
        mean_seal = _mean([metrics["seal"] for metrics in fairway_metrics])
        mean_trap = _mean([metrics["trap"] for metrics in fairway_metrics])
        mean_accumulation = _mean([metrics["accumulation"] for metrics in fairway_metrics])
        migration_efficiency = _mean([float(step["accumulation_probability_index"]) for step in steps])
        leakage_risk = _mean([float(step["leakage_risk_index"]) for step in steps])
        confidence = _clamp(
            _clamp(float(system.get("system_confidence_index", 0.0))) * 0.30
            + mean_source * 0.14
            + mean_maturation * 0.14
            + mean_migration * 0.16
            + mean_trap * 0.16
            + _clamp(len(steps) / float(MAX_PATHS_PER_SYSTEM)) * 0.10
            - leakage_risk * 0.10
        )
        system_type = _system_type(system, mean_source, mean_maturation, leakage_risk)
        lithology_counts = Counter(str(cell.get("lithology", "unknown")) for cell in fairway_cells)
        landform_counts = Counter(str(cell.get("landform", "unknown")) for cell in fairway_cells)
        deposit_ids = [
            int(deposit_id)
            for deposit_id in system.get("resource_deposit_ids", [])
            if int(deposit_id) in deposits_by_id and str(deposits_by_id[int(deposit_id)].get("resource", "")) == "sedimentary_fuels"
        ]
        record = {
            "id": len(records),
            "sedimentary_resource_system_id": int(system.get("id", -1)),
            "sedimentary_basin_id": int(system.get("sedimentary_basin_id", -1)),
            "basin_id": int(system.get("basin_id", -1)),
            "system_type": system_type,
            "cell_ids": fairway_cell_ids,
            "cell_count": len(fairway_cell_ids),
            "area_km2": _round(area_km2),
            "centroid_lat_deg": centroid_lat,
            "centroid_lon_deg": centroid_lon,
            "source_cell_ids": source_cell_ids,
            "source_cell_count": len(source_cell_ids),
            "migration_cell_ids": migration_cell_ids,
            "migration_cell_count": len(migration_cell_ids),
            "reservoir_cell_ids": reservoir_cell_ids,
            "reservoir_cell_count": len(reservoir_cell_ids),
            "seal_cell_ids": seal_cell_ids,
            "seal_cell_count": len(seal_cell_ids),
            "trap_cell_ids": trap_cell_ids,
            "trap_cell_count": len(trap_cell_ids),
            "resource_deposit_ids": deposit_ids,
            "sedimentary_fuel_deposit_count": len(deposit_ids),
            "stratigraphic_column_id": int(system.get("stratigraphic_column_id", -1)),
            "sediment_transport_history_id": int(system.get("sediment_transport_history_id", -1)),
            "mean_source_rock_index": _round(mean_source),
            "mean_maturation_index": _round(mean_maturation),
            "mean_migration_path_index": _round(mean_migration),
            "mean_reservoir_quality_index": _round(mean_reservoir),
            "mean_seal_quality_index": _round(mean_seal),
            "mean_trap_integrity_index": _round(mean_trap),
            "mean_accumulation_index": _round(mean_accumulation),
            "petroleum_potential_index": _round(float(system.get("petroleum_potential_index", 0.0))),
            "gas_potential_index": _round(float(system.get("gas_potential_index", 0.0))),
            "migration_efficiency_index": _round(migration_efficiency),
            "leakage_risk_index": _round(leakage_risk),
            "confidence_index": _round(confidence),
            "dominant_lithology": _primary_key(lithology_counts, "unknown"),
            "dominant_landform": _primary_key(landform_counts, "unknown"),
            "path_step_count": len(steps),
            "migration_steps": steps,
        }
        records.append(record)
        type_counts[system_type] += 1
        assigned_cell_ids.update(fairway_cell_ids)
        for cell_id in fairway_cell_ids:
            cells_by_id[cell_id]["petroleum_system_id"] = int(record["id"])

    cells = list(cells_by_id.values())
    cell_count = len(cells)
    summary = world.setdefault("summary", {})
    summary["petroleum_migration_system_count"] = len(records)
    summary["petroleum_migration_cell_count"] = sum(1 for cell in cells if int(cell.get("petroleum_system_id", -1)) >= 0)
    summary["petroleum_source_rock_cell_count"] = sum(
        1 for cell in cells if float(cell.get("petroleum_source_rock_index", 0.0)) >= SOURCE_ROCK_THRESHOLD
    )
    summary["petroleum_mature_source_cell_count"] = sum(
        1
        for cell in cells
        if float(cell.get("petroleum_source_rock_index", 0.0)) >= SOURCE_ROCK_THRESHOLD
        and float(cell.get("petroleum_maturation_index", 0.0)) >= MATURE_SOURCE_THRESHOLD
    )
    summary["petroleum_trap_cell_count"] = sum(
        1 for cell in cells if float(cell.get("petroleum_trap_integrity_index", 0.0)) >= TRAP_THRESHOLD
    )
    summary["high_petroleum_accumulation_cell_count"] = sum(
        1 for cell in cells if float(cell.get("petroleum_accumulation_index", 0.0)) >= HIGH_ACCUMULATION_THRESHOLD
    )
    summary["petroleum_migration_total_area_km2"] = _round(sum(float(record.get("area_km2", 0.0)) for record in records))
    divisor = float(cell_count) if cell_count else 1.0
    summary["mean_petroleum_source_rock_index"] = _round(
        sum(float(cell.get("petroleum_source_rock_index", 0.0)) for cell in cells) / divisor
    )
    summary["mean_petroleum_maturation_index"] = _round(
        sum(float(cell.get("petroleum_maturation_index", 0.0)) for cell in cells) / divisor
    )
    summary["mean_petroleum_migration_path_index"] = _round(
        sum(float(cell.get("petroleum_migration_path_index", 0.0)) for cell in cells) / divisor
    )
    summary["mean_petroleum_trap_integrity_index"] = _round(
        sum(float(cell.get("petroleum_trap_integrity_index", 0.0)) for cell in cells) / divisor
    )
    summary["mean_petroleum_accumulation_index"] = _round(
        sum(float(cell.get("petroleum_accumulation_index", 0.0)) for cell in cells) / divisor
    )
    summary["petroleum_migration_system_type_counts"] = dict(sorted(type_counts.items()))
    world["petroleum_migration_systems"] = records
    return world
