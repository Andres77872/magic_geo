from __future__ import annotations

from collections import Counter
from typing import Any


SEDIMENTARY_SYSTEM_THRESHOLD = 0.42
SEDIMENTARY_DEPOSIT_RESOURCES = {"sedimentary_fuels", "evaporites"}
SEDIMENTARY_LITHOLOGIES = {"shale", "sandstone", "limestone"}
SEDIMENTARY_LANDFORMS = {
    "coastal_plain",
    "continental_shelf",
    "delta",
    "floodplain",
    "inland_sea",
    "lacustrine_basin",
    "rift_valley",
    "river_valley",
    "stable_lowland",
}
ORGANIC_FACIES = {"deep_marine", "lacustrine_mud", "floodplain_mud", "deltaic_sand"}
RESERVOIR_FACIES = {"deltaic_sand", "fluvial_channel", "shallow_marine", "alluvial_fan"}
SEAL_FACIES = {"deep_marine", "lacustrine_mud", "floodplain_mud"}
COAL_FACIES = {"deltaic_sand", "floodplain_mud", "fluvial_channel", "lacustrine_mud"}
MARINE_FACIES = {"deep_marine", "shallow_marine", "deltaic_sand"}
WET_ORGANIC_BIOMES = {"wetland", "temperate_forest", "tropical_seasonal_forest"}
WET_ORGANIC_LANDFORMS = {"delta", "floodplain", "lacustrine_basin", "river_valley"}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _round(value: float) -> float:
    return round(value, 6)


def _dominant(counter: Counter[str], fallback: str) -> str:
    if not counter:
        return fallback
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _cells_by_basin_id(cells: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    by_basin: dict[int, list[dict[str, Any]]] = {}
    for cell in cells:
        basin_id = int(cell.get("basin_id", -1))
        if basin_id >= 0:
            by_basin.setdefault(basin_id, []).append(cell)
    return by_basin


def _columns_by_basin_id(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    columns: dict[int, dict[str, Any]] = {}
    raw_columns = world.get("stratigraphic_columns", [])
    if not isinstance(raw_columns, list):
        return columns
    for column in raw_columns:
        if not isinstance(column, dict):
            continue
        basin_id = int(column.get("basin_id", -1))
        if basin_id >= 0:
            columns[basin_id] = column
    return columns


def _histories_by_basin_id(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    histories: dict[int, dict[str, Any]] = {}
    raw_histories = world.get("sediment_transport_histories", [])
    if not isinstance(raw_histories, list):
        return histories
    for history in raw_histories:
        if not isinstance(history, dict):
            continue
        basin_id = int(history.get("basin_id", -1))
        if basin_id >= 0:
            histories[basin_id] = history
    return histories


def _deposits_by_basin_id(world: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    by_basin: dict[int, list[dict[str, Any]]] = {}
    deposits = world.get("resource_deposits", [])
    if not isinstance(deposits, list):
        return by_basin
    for deposit in deposits:
        if not isinstance(deposit, dict):
            continue
        if str(deposit.get("resource", "none")) not in SEDIMENTARY_DEPOSIT_RESOURCES:
            continue
        basin_id = int(deposit.get("basin_id", -1))
        if basin_id >= 0:
            by_basin.setdefault(basin_id, []).append(deposit)
    return by_basin


def _system_cells(group: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        cell
        for cell in group
        if (
            float(cell.get("sediment_thickness_m", 0.0)) > 0.0
            or str(cell.get("lithology", "unknown")) in SEDIMENTARY_LITHOLOGIES
            or str(cell.get("landform", "unknown")) in SEDIMENTARY_LANDFORMS
            or str(cell.get("resource", "none")) in SEDIMENTARY_DEPOSIT_RESOURCES
        )
    ]
    return sorted(candidates or group, key=lambda cell: int(cell.get("id", -1)))


def _weighted_layer_average(column: dict[str, Any] | None, key: str) -> float | None:
    """Return None only when no layer supplies this property.

    Partially missing properties retain their existing zero contribution and
    thickness weight; a supplied zero is available evidence, not a default.
    """
    layers = column.get("layers", []) if isinstance(column, dict) else []
    if not isinstance(layers, list) or not layers:
        return None
    weights = [max(0.001, float(layer.get("thickness_m", 0.0))) for layer in layers if isinstance(layer, dict)]
    if not weights:
        return None
    weighted_sum = sum(
        max(0.001, float(layer.get("thickness_m", 0.0))) * _clamp(float(layer.get(key, 0.0)))
        for layer in layers
        if isinstance(layer, dict)
    )
    if not any(key in layer for layer in layers if isinstance(layer, dict)):
        return None
    return weighted_sum / sum(weights)


def _weighted_facies_fraction(column: dict[str, Any] | None, facies_names: set[str]) -> float:
    layers = column.get("layers", []) if isinstance(column, dict) else []
    if not isinstance(layers, list) or not layers:
        return 0.0
    total = sum(max(0.001, float(layer.get("thickness_m", 0.0))) for layer in layers if isinstance(layer, dict))
    if total <= 0.0:
        return 0.0
    matched = sum(
        max(0.001, float(layer.get("thickness_m", 0.0)))
        for layer in layers
        if isinstance(layer, dict) and str(layer.get("facies", "")) in facies_names
    )
    return _clamp(matched / total)


def _petroleum_system_type(potentials: dict[str, float]) -> str:
    ranked = sorted(potentials.items(), key=lambda item: (-item[1], item[0]))
    if len(ranked) >= 2 and ranked[1][1] >= SEDIMENTARY_SYSTEM_THRESHOLD and ranked[0][1] - ranked[1][1] <= 0.06:
        return "mixed_sedimentary_resource"
    return ranked[0][0] if ranked else "mixed_sedimentary_resource"


def enrich_world_with_sedimentary_resource_systems(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    basins = world.get("sedimentary_basins", [])
    if not isinstance(cells, list) or not cells or not isinstance(basins, list):
        return world

    cells_by_basin = _cells_by_basin_id(cells)
    columns_by_basin = _columns_by_basin_id(world)
    histories_by_basin = _histories_by_basin_id(world)
    deposits_by_basin = _deposits_by_basin_id(world)

    systems: list[dict[str, Any]] = []
    system_type_counts: Counter[str] = Counter()
    petroleum_sum = 0.0
    gas_sum = 0.0
    coal_sum = 0.0
    salt_sum = 0.0
    confidence_sum = 0.0
    total_area = 0.0
    unique_system_cell_ids: set[int] = set()

    for basin in basins:
        if not isinstance(basin, dict):
            continue
        sedimentary_basin_id = int(basin.get("id", len(systems)))
        basin_id = int(basin.get("basin_id", -1))
        if basin_id < 0:
            continue
        basin_group = cells_by_basin.get(basin_id, [])
        if not basin_group:
            continue
        system_cells = _system_cells(basin_group)
        column = columns_by_basin.get(basin_id)
        history = histories_by_basin.get(basin_id, {})
        deposits = sorted(deposits_by_basin.get(basin_id, []), key=lambda deposit: int(deposit.get("id", -1)))

        group_count = len(system_cells)
        basin_cell_divisor = max(1, int(basin.get("cell_count", group_count)), group_count)
        area_km2 = sum(max(0.0, float(cell.get("area_km2", 0.0))) for cell in system_cells)
        sediment_index = _clamp(float(basin.get("mean_sediment_thickness_m", 0.0)) / 8.0)
        subsidence = _clamp(float(basin.get("mean_subsidence_index", 0.0)))
        depositional_age_ma = max(0.0, float(basin.get("depositional_age_ma", 0.0)))
        maturity_age = _clamp(depositional_age_ma / 180.0)
        preservation = _clamp(float((column or {}).get("preservation_potential", 0.45)))
        accommodation_ratio = _clamp(float((column or {}).get("mean_accommodation_to_deposition_ratio", 1.0)) / 1.8)
        final_fill_fraction = _clamp(float(history.get("final_accommodation_fill_fraction", 0.0)) / 1.25)

        fuel_deposit_count = sum(1 for deposit in deposits if str(deposit.get("resource", "")) == "sedimentary_fuels")
        evaporite_deposit_count = sum(1 for deposit in deposits if str(deposit.get("resource", "")) == "evaporites")
        fuel_deposit_evidence = _clamp(fuel_deposit_count / basin_cell_divisor)
        evaporite_deposit_evidence = _clamp(evaporite_deposit_count / basin_cell_divisor)
        deposit_evidence = _clamp((fuel_deposit_count + evaporite_deposit_count) / basin_cell_divisor)

        layer_organic = _weighted_layer_average(column, "organic_potential")
        layer_reservoir = _weighted_layer_average(column, "reservoir_quality")
        layer_seal = _weighted_layer_average(column, "seal_quality")
        if layer_organic is None:
            layer_organic = 0.35
        if layer_reservoir is None:
            layer_reservoir = 0.28
        if layer_seal is None:
            layer_seal = 0.30
        organic_facies = _weighted_facies_fraction(column, ORGANIC_FACIES)
        reservoir_facies = _weighted_facies_fraction(column, RESERVOIR_FACIES)
        seal_facies = _weighted_facies_fraction(column, SEAL_FACIES)
        coal_facies = _weighted_facies_fraction(column, COAL_FACIES)
        marine_facies = _weighted_facies_fraction(column, MARINE_FACIES)

        salinity = _mean([_clamp(float(cell.get("soil_salinity_index", 0.0))) for cell in system_cells])
        closed_basin_fraction = _mean([1.0 if bool(cell.get("is_closed_basin", False)) else 0.0 for cell in system_cells])
        salt_flat_fraction = _mean([1.0 if str(cell.get("landform", "")) == "salt_flat" else 0.0 for cell in system_cells])
        wet_organic_fraction = _mean(
            [
                1.0
                if str(cell.get("biome", "")) in WET_ORGANIC_BIOMES
                or str(cell.get("landform", "")) in WET_ORGANIC_LANDFORMS
                else 0.0
                for cell in system_cells
            ]
        )
        source_rock = _clamp(
            layer_organic * 0.40
            + organic_facies * 0.18
            + sediment_index * 0.14
            + subsidence * 0.10
            + fuel_deposit_evidence * 0.12
            + (0.06 if str(basin.get("dominant_resource", "none")) == "sedimentary_fuels" else 0.0)
        )
        reservoir_quality = _clamp(
            layer_reservoir * 0.50
            + reservoir_facies * 0.24
            + sediment_index * 0.10
            + marine_facies * 0.08
            + fuel_deposit_evidence * 0.08
        )
        seal_quality = _clamp(
            layer_seal * 0.56
            + seal_facies * 0.16
            + subsidence * 0.10
            + evaporite_deposit_evidence * 0.10
            + salinity * 0.05
            + closed_basin_fraction * 0.03
        )
        trap_index = _clamp(
            subsidence * 0.34
            + preservation * 0.18
            + accommodation_ratio * 0.14
            + final_fill_fraction * 0.10
            + closed_basin_fraction * 0.10
            + fuel_deposit_evidence * 0.10
            + evaporite_deposit_evidence * 0.04
        )
        age_window = _clamp(1.0 - abs(maturity_age - 0.55) / 0.55)
        petroleum_potential = _clamp(
            source_rock * 0.34
            + reservoir_quality * 0.24
            + seal_quality * 0.20
            + trap_index * 0.15
            + maturity_age * 0.07
        )
        gas_potential = _clamp(
            source_rock * 0.25
            + seal_quality * 0.24
            + trap_index * 0.18
            + sediment_index * 0.15
            + maturity_age * 0.18
        )
        coal_potential = _clamp(
            layer_organic * 0.24
            + coal_facies * 0.24
            + wet_organic_fraction * 0.18
            + sediment_index * 0.12
            + fuel_deposit_evidence * 0.16
            + age_window * 0.06
        )
        evaporite_salt_potential = _clamp(
            salinity * 0.30
            + closed_basin_fraction * 0.22
            + salt_flat_fraction * 0.22
            + evaporite_deposit_evidence * 0.18
            + seal_quality * 0.05
            + (1.0 - marine_facies) * 0.03
        )
        potentials = {
            "petroleum_system": petroleum_potential,
            "gas_system": gas_potential,
            "coal_basin": coal_potential,
            "evaporite_salt_system": evaporite_salt_potential,
        }
        max_potential = max(potentials.values(), default=0.0)
        if max_potential < SEDIMENTARY_SYSTEM_THRESHOLD and not deposits:
            continue

        confidence = _clamp(
            0.16
            + deposit_evidence * 0.24
            + preservation * 0.18
            + _clamp(group_count / 12.0) * 0.14
            + source_rock * 0.10
            + reservoir_quality * 0.08
            + seal_quality * 0.06
            + trap_index * 0.04
        )
        lithology_counter = Counter(str(cell.get("lithology", "unknown")) for cell in system_cells)
        landform_counter = Counter(str(cell.get("landform", "unknown")) for cell in system_cells)
        system_type = _petroleum_system_type(potentials)
        system_type_counts[system_type] += 1
        total_area += area_km2
        unique_system_cell_ids.update(int(cell.get("id", -1)) for cell in system_cells)
        petroleum_sum += petroleum_potential
        gas_sum += gas_potential
        coal_sum += coal_potential
        salt_sum += evaporite_salt_potential
        confidence_sum += confidence

        systems.append(
            {
                "id": len(systems),
                "sedimentary_basin_id": sedimentary_basin_id,
                "basin_id": basin_id,
                "system_type": system_type,
                "cell_ids": [int(cell.get("id", -1)) for cell in system_cells],
                "cell_count": group_count,
                "area_km2": _round(area_km2),
                "resource_deposit_ids": [int(deposit.get("id", -1)) for deposit in deposits],
                "resource_deposit_count": len(deposits),
                "sedimentary_fuel_deposit_count": fuel_deposit_count,
                "evaporite_deposit_count": evaporite_deposit_count,
                "mean_sediment_thickness_m": _round(float(basin.get("mean_sediment_thickness_m", 0.0))),
                "mean_subsidence_index": _round(subsidence),
                "depositional_age_ma": _round(depositional_age_ma),
                "source_rock_index": _round(source_rock),
                "reservoir_quality_index": _round(reservoir_quality),
                "seal_quality_index": _round(seal_quality),
                "structural_trap_index": _round(trap_index),
                "coal_potential_index": _round(coal_potential),
                "petroleum_potential_index": _round(petroleum_potential),
                "gas_potential_index": _round(gas_potential),
                "evaporite_salt_potential_index": _round(evaporite_salt_potential),
                "system_confidence_index": _round(confidence),
                "dominant_lithology": _dominant(lithology_counter, "unknown"),
                "dominant_landform": _dominant(landform_counter, "unknown"),
                "stratigraphic_column_id": int((column or {}).get("id", -1)),
                "sediment_transport_history_id": int(history.get("id", -1)) if isinstance(history, dict) else -1,
            }
        )

    divisor = len(systems) if systems else 1
    world["sedimentary_resource_systems"] = systems
    summary = world.setdefault("summary", {})
    summary["sedimentary_resource_system_count"] = len(systems)
    summary["petroleum_system_count"] = system_type_counts.get("petroleum_system", 0)
    summary["coal_system_count"] = system_type_counts.get("coal_basin", 0)
    summary["gas_system_count"] = system_type_counts.get("gas_system", 0)
    summary["evaporite_salt_system_count"] = system_type_counts.get("evaporite_salt_system", 0)
    summary["sedimentary_resource_system_cell_count"] = len(unique_system_cell_ids)
    summary["sedimentary_resource_system_total_area_km2"] = _round(total_area)
    summary["mean_petroleum_potential_index"] = _round(petroleum_sum / divisor) if systems else 0.0
    summary["mean_gas_potential_index"] = _round(gas_sum / divisor) if systems else 0.0
    summary["mean_coal_potential_index"] = _round(coal_sum / divisor) if systems else 0.0
    summary["mean_evaporite_salt_potential_index"] = _round(salt_sum / divisor) if systems else 0.0
    summary["mean_sedimentary_resource_confidence_index"] = _round(confidence_sum / divisor) if systems else 0.0
    summary["sedimentary_resource_system_type_counts"] = dict(sorted(system_type_counts.items()))
    return world
