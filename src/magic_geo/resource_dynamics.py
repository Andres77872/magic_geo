from __future__ import annotations

from collections import Counter
from typing import Any


METAL_RESOURCES = {"volcanic_arc_metals", "craton_iron_gold", "placer_metals"}
ENERGY_RESOURCES = {"sedimentary_fuels", "geothermal"}
AGRICULTURAL_RESOURCES = {"fertile_alluvium", "coastal_fisheries"}


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _flow_accumulation_scale(cells: list[dict[str, Any]]) -> float:
    positive = sorted(
        max(0.0, float(cell.get("flow_accumulation", 0.0)))
        for cell in cells
        if max(0.0, float(cell.get("flow_accumulation", 0.0))) > 0.0
    )
    if not positive:
        return 1.0
    return max(1.0, positive[int(0.95 * (len(positive) - 1))])


def _resource_class(resource: str) -> str:
    if resource in METAL_RESOURCES:
        return "metal"
    if resource in ENERGY_RESOURCES:
        return "energy"
    if resource == "evaporites":
        return "industrial_mineral"
    if resource in AGRICULTURAL_RESOURCES:
        return "bioproductive"
    return "other"


def _formation_process(resource: str) -> str:
    processes = {
        "volcanic_arc_metals": "subduction_arc_hydrothermal",
        "craton_iron_gold": "ancient_craton_metallogeny",
        "sedimentary_fuels": "buried_sedimentary_basin",
        "evaporites": "closed_basin_evaporation",
        "placer_metals": "fluvial_placer_concentration",
        "geothermal": "rift_or_volcanic_heat",
        "fertile_alluvium": "alluvial_soil_resource",
        "coastal_fisheries": "shelf_coastal_bioproductivity",
    }
    return processes.get(resource, "undifferentiated_resource")


def _reserve_potential(
    resource: str,
    cell: dict[str, Any],
    flow_accumulation_scale: float,
) -> float:
    convergent = _clamp(float(cell.get("boundary_convergent", 0.0)))
    divergent = _clamp(float(cell.get("boundary_divergent", 0.0)))
    sediment = _clamp(float(cell.get("sediment_thickness_m", 0.0)) / 3.0)
    crust_age = _clamp(float(cell.get("crust_age_ma", 0.0)) / 2500.0)
    fertility = _clamp(float(cell.get("fertility", 0.0)))
    salinity = _clamp(float(cell.get("soil_salinity_index", 0.0)))
    runoff = _clamp(float(cell.get("runoff_mm_y", 0.0)) / 900.0)
    flow = _clamp(
        float(cell.get("flow_accumulation", 0.0))
        / max(1.0, flow_accumulation_scale)
    )
    resource_weights = {
        "volcanic_arc_metals": 0.34 + convergent * 0.42 + (0.18 if cell.get("landform") == "volcanic_arc" else 0.0),
        "craton_iron_gold": 0.28 + crust_age * 0.46 + (0.20 if cell.get("crust_type") == "craton" else 0.0),
        "sedimentary_fuels": 0.26 + sediment * 0.48 + (0.12 if "basin" in str(cell.get("landform", "")) else 0.0),
        "evaporites": 0.30 + salinity * 0.36 + (0.24 if cell.get("landform") == "salt_flat" else 0.0),
        "placer_metals": 0.24 + flow * 0.34 + convergent * 0.20 + sediment * 0.14,
        "geothermal": 0.26 + divergent * 0.34 + convergent * 0.20 + (0.18 if cell.get("landform") in {"volcanic_arc", "rift_valley"} else 0.0),
        "fertile_alluvium": 0.24 + fertility * 0.42 + runoff * 0.16 + (0.16 if cell.get("landform") in {"floodplain", "delta"} else 0.0),
        "coastal_fisheries": 0.30 + (0.26 if cell.get("water_body_type") == "continental_shelf" else 0.0) + runoff * 0.12,
    }
    return _clamp(resource_weights.get(resource, 0.18))


def _accessibility(cell: dict[str, Any]) -> float:
    settlement = _clamp(float(cell.get("settlement_score", 0.0)))
    relief = _clamp(abs(float(cell.get("elevation_m", 0.0))) / 3000.0)
    water_access = 0.20 if bool(cell.get("is_river", False)) or cell.get("water_body_type") in {"continental_shelf", "fresh_lake"} else 0.0
    return _clamp(0.28 + settlement * 0.42 + water_access - relief * 0.20)


def _extraction_hazard(cell: dict[str, Any]) -> float:
    tectonic = _clamp(float(cell.get("boundary_convergent", 0.0)) * 0.42 + float(cell.get("boundary_transform", 0.0)) * 0.30)
    relief = _clamp(abs(float(cell.get("elevation_m", 0.0))) / 3600.0)
    ice = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 1600.0)
    aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    salinity = _clamp(float(cell.get("soil_salinity_index", 0.0)))
    return _clamp(tectonic + relief * 0.20 + ice * 0.20 + aridity * 0.10 + salinity * 0.08)


def _confidence(
    resource: str,
    cell: dict[str, Any],
    reserve: float,
    flow_accumulation_scale: float,
) -> float:
    evidence = 0.18
    if resource == "volcanic_arc_metals":
        evidence += _clamp(float(cell.get("boundary_convergent", 0.0))) * 0.36
        evidence += 0.22 if cell.get("landform") == "volcanic_arc" else 0.0
    elif resource == "craton_iron_gold":
        evidence += _clamp(float(cell.get("crust_age_ma", 0.0)) / 2500.0) * 0.34
        evidence += 0.24 if cell.get("crust_type") == "craton" else 0.0
    elif resource == "sedimentary_fuels":
        evidence += _clamp(float(cell.get("sediment_thickness_m", 0.0)) / 3.0) * 0.38
        evidence += 0.18 if "basin" in str(cell.get("landform", "")) else 0.0
    elif resource == "evaporites":
        evidence += _clamp(float(cell.get("soil_salinity_index", 0.0))) * 0.32
        evidence += 0.22 if cell.get("landform") == "salt_flat" else 0.0
    elif resource == "placer_metals":
        evidence += 0.22 if bool(cell.get("is_river", False)) else 0.0
        evidence += _clamp(
            float(cell.get("flow_accumulation", 0.0))
            / max(1.0, flow_accumulation_scale)
        ) * 0.26
    elif resource == "geothermal":
        evidence += _clamp(max(float(cell.get("boundary_divergent", 0.0)), float(cell.get("boundary_convergent", 0.0)))) * 0.34
        evidence += 0.18 if cell.get("landform") in {"volcanic_arc", "rift_valley"} else 0.0
    elif resource == "fertile_alluvium":
        evidence += _clamp(float(cell.get("fertility", 0.0))) * 0.32
        evidence += 0.20 if cell.get("landform") in {"floodplain", "delta"} else 0.0
    elif resource == "coastal_fisheries":
        evidence += 0.32 if cell.get("water_body_type") == "continental_shelf" else 0.0
        evidence += _clamp(float(cell.get("runoff_mm_y", 0.0)) / 900.0) * 0.12
    return _clamp(evidence * 0.72 + reserve * 0.28)


def _formation_evidence(cell: dict[str, Any]) -> dict[str, Any]:
    return {
        "boundary_type": str(cell.get("boundary_type", "unknown")),
        "boundary_convergent": round(_clamp(float(cell.get("boundary_convergent", 0.0))), 6),
        "boundary_divergent": round(_clamp(float(cell.get("boundary_divergent", 0.0))), 6),
        "crust_age_ma": round(max(0.0, float(cell.get("crust_age_ma", 0.0))), 6),
        "sediment_thickness_m": round(max(0.0, float(cell.get("sediment_thickness_m", 0.0))), 6),
        "flow_accumulation": round(max(0.0, float(cell.get("flow_accumulation", 0.0))), 6),
        "fertility": round(_clamp(float(cell.get("fertility", 0.0))), 6),
        "salinity_index": round(_clamp(float(cell.get("soil_salinity_index", 0.0))), 6),
    }


def enrich_world_with_resource_deposits(world: dict[str, Any]) -> dict[str, Any]:
    cells = world.get("cells", [])
    if not isinstance(cells, list) or not cells:
        return world

    deposits: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    reserve_sum = 0.0
    viability_sum = 0.0
    confidence_sum = 0.0
    total_area = 0.0
    high_viability = 0
    flow_accumulation_scale = _flow_accumulation_scale(cells)

    for cell in cells:
        resource = str(cell.get("resource", "none"))
        if resource == "none":
            continue
        reserve = _reserve_potential(resource, cell, flow_accumulation_scale)
        accessibility = _accessibility(cell)
        hazard = _extraction_hazard(cell)
        confidence = _confidence(
            resource, cell, reserve, flow_accumulation_scale
        )
        renewability = 0.78 if resource in AGRICULTURAL_RESOURCES else (0.32 if resource == "geothermal" else 0.02)
        viability = _clamp(reserve * 0.46 + accessibility * 0.30 + confidence * 0.20 - hazard * 0.18 + renewability * 0.10)
        deposit_class = _resource_class(resource)
        class_counts[deposit_class] += 1
        reserve_sum += reserve
        viability_sum += viability
        confidence_sum += confidence
        total_area += max(0.0, float(cell.get("area_km2", 0.0)))
        if viability >= 0.65:
            high_viability += 1
        deposits.append(
            {
                "id": len(deposits),
                "cell_id": int(cell.get("id", -1)),
                "resource": resource,
                "deposit_class": deposit_class,
                "formation_process": _formation_process(resource),
                "host_crust_type": str(cell.get("crust_type", "unknown")),
                "host_lithology": str(cell.get("lithology", "unknown")),
                "landform": str(cell.get("landform", "unknown")),
                "basin_id": int(cell.get("basin_id", -1)),
                "political_region_id": int(cell.get("political_region_id", -1)),
                "culture_region_id": int(cell.get("culture_region_id", -1)),
                "latitude_deg": round(float(cell.get("lat_deg", 0.0)), 6),
                "longitude_deg": round(float(cell.get("lon_deg", 0.0)), 6),
                "area_km2": round(max(0.0, float(cell.get("area_km2", 0.0))), 6),
                "reserve_potential_index": round(reserve, 6),
                "accessibility_index": round(accessibility, 6),
                "extraction_hazard_index": round(hazard, 6),
                "economic_viability_index": round(viability, 6),
                "renewability_index": round(renewability, 6),
                "geologic_confidence_index": round(confidence, 6),
                "formation_evidence": _formation_evidence(cell),
            }
        )

    world["resource_deposits"] = deposits
    world["resource_deposit_model"] = {
        "model_type": "causal_geologic_resource_deposit_diagnostics_v2",
        "flow_accumulation_normalization_model": "positive_cell_p95_v1",
        "flow_accumulation_scale": round(flow_accumulation_scale, 6),
        "flow_accumulation_units": "runoff_mm_y_times_upstream_area_km2",
        "physical_time_resolved": False,
        "model_limitation": "diagnostic formation evidence without geochemical transport or reserve-volume simulation",
    }
    summary = world.setdefault("summary", {})
    divisor = len(deposits) if deposits else 1
    summary["resource_deposit_count"] = len(deposits)
    summary["metal_resource_deposit_count"] = class_counts.get("metal", 0)
    summary["energy_resource_deposit_count"] = class_counts.get("energy", 0)
    summary["agricultural_resource_deposit_count"] = class_counts.get("bioproductive", 0)
    summary["high_viability_resource_deposit_count"] = high_viability
    summary["resource_deposit_total_area_km2"] = round(total_area, 6)
    summary["mean_resource_reserve_potential_index"] = round(reserve_sum / divisor, 6) if deposits else 0.0
    summary["mean_resource_economic_viability_index"] = round(viability_sum / divisor, 6) if deposits else 0.0
    summary["mean_resource_geologic_confidence_index"] = round(confidence_sum / divisor, 6) if deposits else 0.0
    summary["resource_deposit_class_counts"] = dict(sorted(class_counts.items()))
    return world
