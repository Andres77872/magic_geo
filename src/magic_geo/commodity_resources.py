from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from .biological_resource_validation import (
    BiologicalResourceValidationError,
    audit_biological_resource_deposits,
    biological_resource_contract,
    commodity_expected_model,
    resource_access_v5,
    audit_biological_commodity_inputs,
    COMMODITY_SUMMARY_FIELDS,
    validate_biological_resources,
)


COMMODITY_OCCURRENCE_MODEL = {
    "model_type": "causal_resource_commodity_occurrences_with_parent_support_v1",
    "source_resource_deposit_model": "causal_geologic_resource_deposit_diagnostics_v3",
    "source_ecosystem_model": "heuristic_ecosystem_climate_support_v4",
    "fishery_parent_policy": "supported_matching_deposit_primary_and_derived_fishery_required",
    "unsupported_fishery_occurrence_policy": "no_record_not_observed_zero_biomass",
    "fertile_soils_scope": "soil_material_descriptor_not_current_crop_yield",
    "material_commodity_policy": "preserve_existing_nonfishery_equations_and_mapping",
    "summary_support_scope": "emitted_record_means_with_unsupported_fishery_source_counts",
}


COMMODITY_PRESCRIBED_NATURAL_MODEL = {
    **COMMODITY_OCCURRENCE_MODEL,
    "model_type": "causal_resource_commodity_occurrences_with_parent_support_v2",
    "source_resource_deposit_model": "causal_geologic_resource_deposit_diagnostics_v4",
    "source_ecosystem_model": "heuristic_ecosystem_climate_support_v5",
}
_COMMODITY_MODELS = {
    "heuristic_ecosystem_climate_support_v4": COMMODITY_OCCURRENCE_MODEL,
    "heuristic_ecosystem_climate_support_v5": COMMODITY_PRESCRIBED_NATURAL_MODEL,
}


COMMODITY_BY_RESOURCE = {
    "volcanic_arc_metals": {"copper", "gold", "silver", "sulfide_ore"},
    "craton_iron_gold": {"iron", "gold", "diamond"},
    "sedimentary_fuels": {"coal", "petroleum", "natural_gas"},
    "evaporites": {"salt", "gypsum", "potash"},
    "placer_metals": {"placer_gold", "tin"},
    "geothermal": {"geothermal_heat", "sulfur", "obsidian"},
    "fertile_alluvium": {"fertile_soils"},
    "coastal_fisheries": {"fishery_biomass"},
}

COMMODITY_GROUPS = {
    "coal": "fuel",
    "copper": "base_metal",
    "diamond": "gemstone",
    "fertile_soils": "agricultural",
    "fishery_biomass": "fishery",
    "geothermal_heat": "geothermal",
    "gold": "precious_metal",
    "gypsum": "industrial_mineral",
    "iron": "ferrous_metal",
    "natural_gas": "fuel",
    "obsidian": "volcanic_material",
    "petroleum": "fuel",
    "placer_gold": "precious_metal",
    "potash": "industrial_mineral",
    "salt": "industrial_mineral",
    "silver": "precious_metal",
    "sulfide_ore": "base_metal",
    "sulfur": "industrial_mineral",
    "tin": "base_metal",
}

COMMODITY_VALUE_INDEX = {
    "coal": 0.50,
    "copper": 0.78,
    "diamond": 0.88,
    "fertile_soils": 0.64,
    "fishery_biomass": 0.58,
    "geothermal_heat": 0.62,
    "gold": 0.92,
    "gypsum": 0.42,
    "iron": 0.64,
    "natural_gas": 0.68,
    "obsidian": 0.36,
    "petroleum": 0.76,
    "placer_gold": 0.86,
    "potash": 0.70,
    "salt": 0.38,
    "silver": 0.72,
    "sulfide_ore": 0.74,
    "sulfur": 0.48,
    "tin": 0.66,
}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _round(value: float) -> float:
    return round(value, 6)


def _sedimentary_system_by_basin_id(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    by_basin: dict[int, dict[str, Any]] = {}
    systems = world.get("sedimentary_resource_systems", [])
    if not isinstance(systems, list):
        return by_basin
    for system in systems:
        if not isinstance(system, dict):
            continue
        basin_id = int(system.get("basin_id", -1))
        if basin_id < 0:
            continue
        current = by_basin.get(basin_id)
        current_confidence = float(current.get("system_confidence_index", -1.0)) if isinstance(current, dict) else -1.0
        if float(system.get("system_confidence_index", 0.0)) >= current_confidence:
            by_basin[basin_id] = system
    return by_basin


def _formation_evidence(deposit: dict[str, Any], cell: dict[str, Any], sedimentary_system: dict[str, Any] | None) -> dict[str, Any]:
    evidence = deposit.get("formation_evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}
    payload = {
        "boundary_type": str(evidence.get("boundary_type", cell.get("boundary_type", "unknown"))),
        "boundary_convergent": _round(_clamp(float(evidence.get("boundary_convergent", cell.get("boundary_convergent", 0.0))))),
        "boundary_divergent": _round(_clamp(float(evidence.get("boundary_divergent", cell.get("boundary_divergent", 0.0))))),
        "volcanic_potential_index": _round(_clamp(float(cell.get("volcanic_potential_index", 0.0)))),
        "crust_age_ma": _round(max(0.0, float(evidence.get("crust_age_ma", cell.get("crust_age_ma", 0.0))))),
        "sediment_thickness_m": _round(max(0.0, float(evidence.get("sediment_thickness_m", cell.get("sediment_thickness_m", 0.0))))),
        "flow_accumulation": _round(max(0.0, float(evidence.get("flow_accumulation", cell.get("flow_accumulation", 0.0))))),
        "salinity_index": _round(_clamp(float(evidence.get("salinity_index", cell.get("soil_salinity_index", 0.0))))),
        "fertility": _round(_clamp(float(evidence.get("fertility", cell.get("fertility", 0.0))))),
    }
    if sedimentary_system is not None:
        payload["sedimentary_resource_system_id"] = int(sedimentary_system.get("id", -1))
        payload["petroleum_potential_index"] = _round(_clamp(float(sedimentary_system.get("petroleum_potential_index", 0.0))))
        payload["gas_potential_index"] = _round(_clamp(float(sedimentary_system.get("gas_potential_index", 0.0))))
        payload["coal_potential_index"] = _round(_clamp(float(sedimentary_system.get("coal_potential_index", 0.0))))
        payload["evaporite_salt_potential_index"] = _round(
            _clamp(float(sedimentary_system.get("evaporite_salt_potential_index", 0.0)))
        )
    return payload


def _base_indices(deposit: dict[str, Any], cell: dict[str, Any], *, economic_availability: bool = False) -> dict[str, float]:
    return {
        "reserve": _clamp(float(deposit.get("reserve_potential_index", 0.0))),
        "confidence": _clamp(float(deposit.get("geologic_confidence_index", 0.0))),
        **({"accessibility": _clamp(float(deposit.get("accessibility_index", 0.0))),
            "viability": _clamp(float(deposit.get("economic_viability_index", 0.0)))} if not economic_availability else {}),
        "hazard": _clamp(float(deposit.get("extraction_hazard_index", 0.0))),
        "convergent": _clamp(float(cell.get("boundary_convergent", 0.0))),
        "divergent": _clamp(float(cell.get("boundary_divergent", 0.0))),
        "volcanic": _clamp(float(cell.get("volcanic_potential_index", 0.0))),
        "crust_age": _clamp(float(cell.get("crust_age_ma", 0.0)) / 3000.0),
        "flow": _clamp(float(cell.get("flow_accumulation", 0.0)) / 600_000_000.0),
        "salinity": _clamp(float(cell.get("soil_salinity_index", 0.0))),
        "sediment": _clamp(float(cell.get("sediment_thickness_m", 0.0)) / 8.0),
        "fertility": _clamp(float(cell.get("fertility", 0.0))),
    }


def _commodity_potential(
    commodity: str,
    deposit: dict[str, Any],
    cell: dict[str, Any],
    sedimentary_system: dict[str, Any] | None,
    *, economic_availability: bool = False,
) -> float:
    index = _base_indices(deposit, cell, economic_availability=economic_availability)
    resource = str(deposit.get("resource", "none"))
    lithology = str(cell.get("lithology", "unknown"))
    crust = str(cell.get("crust_type", "unknown"))
    landform = str(cell.get("landform", "unknown"))
    water_body = str(cell.get("water_body_type", "land"))

    if commodity == "copper":
        return _clamp(index["reserve"] * 0.42 + index["convergent"] * 0.30 + index["volcanic"] * 0.18 + index["confidence"] * 0.10)
    if commodity == "gold":
        age_or_convergence = max(index["crust_age"], index["convergent"])
        return _clamp(index["reserve"] * 0.36 + age_or_convergence * 0.26 + index["confidence"] * 0.22 + index["flow"] * 0.08)
    if commodity == "silver":
        return _clamp(index["reserve"] * 0.34 + index["convergent"] * 0.28 + index["volcanic"] * 0.16 + index["confidence"] * 0.16)
    if commodity == "sulfide_ore":
        return _clamp(index["reserve"] * 0.34 + index["convergent"] * 0.28 + index["volcanic"] * 0.22 + (0.08 if crust == "volcanic_arc" else 0.0))
    if commodity == "iron":
        return _clamp(index["reserve"] * 0.38 + index["crust_age"] * 0.30 + (0.18 if crust == "craton" else 0.0) + index["confidence"] * 0.14)
    if commodity == "diamond":
        return _clamp(index["reserve"] * 0.28 + index["crust_age"] * 0.34 + (0.24 if crust == "craton" else 0.0) + (0.08 if lithology == "granite" else 0.0))
    if commodity == "coal":
        system_potential = _clamp(float((sedimentary_system or {}).get("coal_potential_index", 0.0)))
        return _clamp(index["reserve"] * 0.28 + system_potential * 0.50 + index["sediment"] * 0.12 + index["confidence"] * 0.10)
    if commodity == "petroleum":
        system_potential = _clamp(float((sedimentary_system or {}).get("petroleum_potential_index", 0.0)))
        return _clamp(index["reserve"] * 0.24 + system_potential * 0.54 + index["sediment"] * 0.10 + index["confidence"] * 0.12)
    if commodity == "natural_gas":
        system_potential = _clamp(float((sedimentary_system or {}).get("gas_potential_index", 0.0)))
        return _clamp(index["reserve"] * 0.24 + system_potential * 0.56 + index["sediment"] * 0.10 + index["confidence"] * 0.10)
    if commodity == "salt":
        system_potential = _clamp(float((sedimentary_system or {}).get("evaporite_salt_potential_index", 0.0)))
        return _clamp(index["reserve"] * 0.34 + index["salinity"] * 0.26 + system_potential * 0.22 + (0.12 if landform == "salt_flat" else 0.0))
    if commodity == "gypsum":
        return _clamp(index["reserve"] * 0.42 + index["salinity"] * 0.22 + index["sediment"] * 0.16 + index["confidence"] * 0.14)
    if commodity == "potash":
        return _clamp(index["reserve"] * 0.36 + index["salinity"] * 0.30 + index["sediment"] * 0.12 + index["confidence"] * 0.16)
    if commodity == "placer_gold":
        return _clamp(index["reserve"] * 0.34 + index["flow"] * 0.34 + index["convergent"] * 0.16 + (0.08 if bool(cell.get("is_river", False)) else 0.0))
    if commodity == "tin":
        return _clamp(index["reserve"] * 0.34 + index["flow"] * 0.24 + index["convergent"] * 0.16 + index["sediment"] * 0.10 + index["confidence"] * 0.10)
    if commodity == "geothermal_heat":
        return _clamp(index["reserve"] * 0.36 + max(index["divergent"], index["convergent"]) * 0.30 + index["volcanic"] * 0.22 + index["confidence"] * 0.10)
    if commodity == "sulfur":
        return _clamp(index["reserve"] * 0.26 + max(index["divergent"], index["convergent"]) * 0.22 + index["volcanic"] * 0.30 + (0.10 if landform == "volcanic_arc" else 0.0))
    if commodity == "obsidian":
        volcanic_lithology = 0.18 if lithology in {"volcanic", "basalt"} else 0.0
        return _clamp(index["reserve"] * 0.20 + index["volcanic"] * 0.38 + index["divergent"] * 0.16 + volcanic_lithology + (0.08 if landform in {"volcanic_arc", "rift_valley"} else 0.0))
    if commodity == "fertile_soils":
        return _clamp(index["reserve"] * 0.24 + index["fertility"] * 0.42 + (0.16 if landform in {"floodplain", "delta", "river_valley"} else 0.0) + index["confidence"] * 0.12)
    if commodity == "fishery_biomass":
        marine_bonus = 0.24 if water_body in {"ocean", "continental_shelf", "inland_sea"} else 0.0
        shelf_bonus = 0.16 if water_body == "continental_shelf" else 0.0
        return _clamp(index["reserve"] * 0.30 + marine_bonus + shelf_bonus + index["confidence"] * 0.18 + _clamp(float(cell.get("fishery_productivity_index", 0.0))) * 0.20)
    return _clamp(index["reserve"] * 0.70 + index["confidence"] * 0.30) if resource != "none" else 0.0


def _build_commodity_occurrences(world: dict[str, Any], *, allow_empty: bool = False, economic_availability: bool = False) -> dict[str, Any]:
    cells = world.get("cells", [])
    deposits = world.get("resource_deposits", [])
    if not isinstance(cells, list) or (not cells and not allow_empty) or not isinstance(deposits, list):
        return world

    cells_by_id = {int(cell.get("id", -1)): cell for cell in cells if isinstance(cell, dict)}
    sedimentary_systems_by_basin = _sedimentary_system_by_basin_id(world)
    occurrences: list[dict[str, Any]] = []
    commodity_counts: Counter[str] = Counter()
    group_counts: Counter[str] = Counter()
    potential_sum = 0.0
    confidence_sum = 0.0
    total_area = 0.0
    high_potential_count = 0

    for deposit in deposits:
        if not isinstance(deposit, dict):
            continue
        source_resource = str(deposit.get("resource", "none"))
        commodities = sorted(COMMODITY_BY_RESOURCE.get(source_resource, set()))
        if not commodities:
            continue
        cell_id = int(deposit.get("cell_id", -1))
        cell = cells_by_id.get(cell_id, {})
        sedimentary_system = sedimentary_systems_by_basin.get(int(deposit.get("basin_id", -1)))
        for commodity in commodities:
            potential = _commodity_potential(commodity, deposit, cell, sedimentary_system, economic_availability=economic_availability)
            confidence = _clamp(
                float(deposit.get("geologic_confidence_index", 0.0)) * 0.54
                + potential * 0.30
                + float(deposit.get("reserve_potential_index", 0.0)) * 0.16
            )
            group = COMMODITY_GROUPS.get(commodity, "other")
            area = max(0.0, float(deposit.get("area_km2", 0.0)))
            commodity_counts[commodity] += 1
            group_counts[group] += 1
            potential_sum += potential
            confidence_sum += confidence
            total_area += area
            if potential >= 0.62:
                high_potential_count += 1
            occurrences.append(
                {
                    "id": len(occurrences),
                    "resource_deposit_id": int(deposit.get("id", -1)),
                    "cell_id": cell_id,
                    "commodity": commodity,
                    "commodity_group": group,
                    "source_resource": source_resource,
                    "formation_process": str(deposit.get("formation_process", "undifferentiated_resource")),
                    "host_crust_type": str(deposit.get("host_crust_type", cell.get("crust_type", "unknown"))),
                    "host_lithology": str(deposit.get("host_lithology", cell.get("lithology", "unknown"))),
                    "landform": str(deposit.get("landform", cell.get("landform", "unknown"))),
                    "basin_id": int(deposit.get("basin_id", -1)),
                    "political_region_id": int(deposit.get("political_region_id", -1)),
                    "culture_region_id": int(deposit.get("culture_region_id", -1)),
                    "area_km2": _round(area),
                    "occurrence_potential_index": _round(potential),
                    "market_value_index": _round(COMMODITY_VALUE_INDEX.get(commodity, 0.50)),
                    "accessibility_index": deposit["accessibility_index"] if economic_availability else _round(_clamp(float(deposit.get("accessibility_index", 0.0)))),
                    **({key: deposit[key] for key in ("accessibility_supported", "geographic_accessibility_baseline_index")} if economic_availability else {}),
                    "extraction_hazard_index": _round(_clamp(float(deposit.get("extraction_hazard_index", 0.0)))),
                    "geologic_confidence_index": _round(confidence),
                    "formation_evidence": _formation_evidence(deposit, cell, sedimentary_system),
                }
            )

    divisor = len(occurrences) if occurrences else 1
    world["commodity_occurrences"] = occurrences
    summary = world.setdefault("summary", {})
    summary["commodity_occurrence_count"] = len(occurrences)
    summary["metallic_commodity_occurrence_count"] = sum(
        group_counts.get(group, 0) for group in ("base_metal", "ferrous_metal", "precious_metal")
    )
    summary["fuel_commodity_occurrence_count"] = group_counts.get("fuel", 0)
    summary["industrial_mineral_commodity_occurrence_count"] = group_counts.get("industrial_mineral", 0)
    summary["gemstone_commodity_occurrence_count"] = group_counts.get("gemstone", 0)
    summary["geothermal_commodity_occurrence_count"] = group_counts.get("geothermal", 0)
    summary["bioproductive_commodity_occurrence_count"] = group_counts.get("agricultural", 0) + group_counts.get("fishery", 0)
    summary["high_potential_commodity_occurrence_count"] = high_potential_count
    summary["commodity_occurrence_total_area_km2"] = _round(total_area)
    summary["mean_commodity_occurrence_potential_index"] = _round(potential_sum / divisor) if occurrences else 0.0
    summary["mean_commodity_occurrence_confidence_index"] = _round(confidence_sum / divisor) if occurrences else 0.0
    summary["commodity_occurrence_type_counts"] = dict(sorted(commodity_counts.items()))
    summary["commodity_occurrence_group_counts"] = dict(sorted(group_counts.items()))
    return world


def _enrich_world_with_commodity_occurrences_legacy(world: dict[str, Any]) -> dict[str, Any]:
    """Historical absent-model mapping and equations, including empty behavior."""
    return _build_commodity_occurrences(world)


def enrich_world_with_commodity_occurrences(world: dict[str, Any]) -> dict[str, Any]:
    chain = biological_resource_contract(world)
    if chain is None:
        return _enrich_world_with_commodity_occurrences_legacy(world)
    # Missing supported sources are incomplete input, never zero-confidence
    # substitutes. Validate every source before touching any caller-owned value.
    support = audit_biological_resource_deposits(world)
    audit_biological_commodity_inputs(world)
    staged = {**world, "cells": [dict(cell) for cell in world["cells"]], "summary": dict(world["summary"])}
    _build_commodity_occurrences(staged, allow_empty=True, economic_availability=resource_access_v5(world) and chain == "heuristic_ecosystem_climate_support_v5")
    staged["commodity_occurrence_model"] = deepcopy(commodity_expected_model(world, chain))
    for cell in staged["cells"]:
        cell["fishery_commodity_applicable"], cell["fishery_commodity_supported"] = support[cell["id"]]
    staged["summary"].update({
        "fishery_commodity_applicable_cell_count": sum(a for a, _ in support.values()),
        "fishery_commodity_supported_cell_count": sum(s for _, s in support.values()),
        "unsupported_fishery_commodity_cell_count": sum(a and not s for a, s in support.values()),
    })
    errors = validate_biological_resources(staged)
    if errors:
        raise BiologicalResourceValidationError(errors[0])
    for cell, patch in zip(world["cells"], staged["cells"]):
        for key in ("fishery_commodity_applicable", "fishery_commodity_supported"):
            cell[key] = patch[key]
    world["commodity_occurrences"] = staged["commodity_occurrences"]
    world["commodity_occurrence_model"] = staged["commodity_occurrence_model"]
    world["summary"].update({key: staged["summary"][key] for key in COMMODITY_SUMMARY_FIELDS})
    return world
