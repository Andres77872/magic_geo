"""Independent population, conflict and dynasty replay for the new native family."""
from __future__ import annotations

import math
from typing import Any

from .native_social_availability import (
    NATIVE_SOCIAL_MODEL, SOCIAL_MODEL_TYPES, exact_contract, finite_number,
    indexed_records, require_native_social_availability, native_area_matches,
)
from .civilization_geography_validation import (
    _clamp, _close, _relative_close, _local_relief, _water_security,
    _population_model, _conflict_model, _dynasty_model,
    _conflict_records, _conflict_matches, _dynasty_records, _dynasty_matches,
)


def _models() -> dict[str, dict[str, Any]]:
    models = {"population_region_model": _population_model(), "conflict_model": _conflict_model(), "dynasty_model": _dynasty_model()}
    sources = {
        "population_region_model": {
            "source_settlement_model": "causal_native_score_local_max_separated_settlement_selection_v3",
            "source_culture_region_model": "causal_political_homeland_barrier_trade_culture_regions_v2",
            "source_political_region_model": "causal_capital_barrier_partition_political_regions_v1",
            "source_route_network_model": "causal_endpoint_barrier_ranked_route_network_v1",
            "availability_policy": "unchanged_total_territory_denominator_complete_site_capacity_and_culture_population",
        },
        "conflict_model": {
            "source_population_region_model": "causal_area_weighted_capacity_occupancy_population_regions_v2",
            "source_political_region_model": "causal_capital_barrier_partition_political_regions_v1",
            "source_political_border_model": "causal_adjacent_region_terrain_border_segments_v1",
            "source_trade_flow_model": "causal_route_endpoint_complement_trade_flows_v1",
            "availability_policy": "complete_actual_border_pair_population_inputs_before_global_rank_cap",
        },
        "dynasty_model": {
            "source_population_region_model": "causal_area_weighted_capacity_occupancy_population_regions_v2",
            "source_culture_region_model": "causal_political_homeland_barrier_trade_culture_regions_v2",
            "source_historical_event_model": "causal_region_culture_language_trade_site_timeline_v2",
            "source_conflict_model": "causal_border_pair_pressure_trade_conflict_selection_v2",
            "availability_policy": "available_region_lineages_with_explicit_incomplete_collection_coverage",
        },
    }
    for key, model in models.items():
        model["model_type"] = SOCIAL_MODEL_TYPES[key]
        model["source_native_social_availability_model"] = NATIVE_SOCIAL_MODEL["model_type"]
        model.update(sources[key])
    return models


def population_records_v2(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Reproduce only defined quantities, retaining the original area denominator."""
    cells = payload["cells"]
    by_id = {c["id"]: c for c in cells}
    culture_by_region = {c["homeland_region_id"]: c for c in payload["cultures"]}
    result = []
    for region in payload["political_regions"]:
        culture = culture_by_region[region["id"]]
        territory = [c for c in cells if not c["is_water"] and c["political_region_id"] == region["id"]]
        positive_cells = [c for c in territory if finite_number(c["area_km2"]) > 0]
        land = [c for c in positive_cells if not c["is_lake"]]
        supported = [c for c in land if -14.0 < finite_number(c["settlement_climate_temperature_c"]) < 48.0]
        water = [c for c in positive_cells if c["is_lake"]]
        area = sum(finite_number(c["area_km2"]) for c in territory)
        complete = len(supported) == len(land)
        capacity_available = area > 0 and complete
        population_available = capacity_available and culture["continuity_estimate_available"]
        pop = {
            "id":len(result), "region_id":region["id"], "culture_region_id":culture["id"],
            "language_region_id":culture["language_region_id"], "settlement_count":region["settlement_count"],
            "territory_cell_count":len(territory), "territory_area_km2":area,
            "site_input_applicable_cell_count":len(land), "site_input_applicable_area_km2":sum(c["area_km2"] for c in land),
            "site_input_supported_cell_count":len(supported), "site_input_supported_area_km2":sum(c["area_km2"] for c in supported),
            "structural_zero_site_cell_count":len(water), "structural_zero_site_area_km2":sum(c["area_km2"] for c in water),
            "site_input_complete":complete, "site_strength_available":capacity_available,
            "physical_means_available":area > 0, "capacity_estimate_available":capacity_available,
            "population_estimate_available":population_available, "migration_balance_available":True,
            "estimate_scope_status":"not_applicable_no_positive_territory" if area <= 0 else "complete" if population_available else "unavailable_inputs",
            "migration_balance":_clamp(0.5-finite_number(culture["migration_pressure"]),-1.0,1.0),
            "site_strength_index":None, "agricultural_capacity_index":None, "water_security_index":None,
            "hazard_mortality_index":None, "carrying_capacity":None, "urbanization_fraction":None,
            "estimated_population":None, "population_pressure":None, "growth_rate_per_year":None,
        }
        if area <= 0:
            result.append(pop)
            continue
        fertility_sum = water_sum = climate_sum = hazard_sum = 0.0
        for cell in territory:
            a = finite_number(cell["area_km2"])
            water_value = _water_security(cell, by_id)
            climate = _clamp(1.0-abs(finite_number(cell["temperature_c"])-17.0)/42.0-max(0.0,360.0-finite_number(cell["precipitation_mm_y"]))/1400.0-finite_number(cell["ice_thickness_m"])/2800.0)
            hazard = _clamp(.35*finite_number(cell["boundary_convergent"])+.25*finite_number(cell["boundary_transform"])+_local_relief(cell,by_id)/4200.0+finite_number(cell["ice_thickness_m"])/3200.0)
            fertility_sum += finite_number(cell["fertility"])*a
            water_sum += water_value*a
            climate_sum += climate*a
            hazard_sum += hazard*a
        fertility, water_mean, climate_mean, hazard_mean = (x/area for x in (fertility_sum,water_sum,climate_sum,hazard_sum))
        pop["agricultural_capacity_index"] = _clamp(fertility*climate_mean*(.55+.45*water_mean))
        pop["water_security_index"] = water_mean
        pop["hazard_mortality_index"] = hazard_mean
        if capacity_available:
            # Unsupported zero-area cells have no contribution; do not read
            # their unavailable site value even though their weight is zero.
            site = sum(finite_number(c["settlement_score"])*c["area_km2"] for c in positive_cells)/area
            route = _clamp(finite_number(region["route_count"])/max(1.0,finite_number(region["settlement_count"])))
            pop["site_strength_index"] = site
            density = _clamp(1.5+64.0*fertility*water_mean*climate_mean+12.0*site,.2,90.0)
            pop["carrying_capacity"] = area*density
            pop["urbanization_fraction"] = _clamp(.04+.025*region["settlement_count"]+.16*route+.12*site,.02,.62)
            if population_available:
                occupancy = _clamp(.22+.30*finite_number(culture["continuity_index"])+.26*pop["urbanization_fraction"]+.18*route-.18*hazard_mean,.05,.93)
                pop["estimated_population"] = pop["carrying_capacity"]*occupancy
                pop["population_pressure"] = _clamp(pop["estimated_population"]/pop["carrying_capacity"],0.0,1.4)
                pop["growth_rate_per_year"] = _clamp(.0015+.0065*pop["agricultural_capacity_index"]+.0025*water_mean-.0030*pop["population_pressure"]-.0045*hazard_mean,-.012,.018)
        result.append(pop)
    return result


def _population_matches_v2(actual: dict[str, Any], expected: dict[str, Any], precision: int) -> bool:
    for key, value in expected.items():
        if key not in actual:
            return False
        if value is None or type(value) in (str, bool) or key in {"id", "region_id", "culture_region_id", "language_region_id", "settlement_count"} or key.endswith("_cell_count"):
            if not exact_contract(actual[key], value):
                return False
        else:
            finite_number(actual[key])
            if key in {"carrying_capacity", "estimated_population"}:
                if not _relative_close(actual[key], value):
                    return False
            elif key.endswith("_area_km2"):
                count = expected[key.removesuffix("area_km2") + "cell_count"]
                if not native_area_matches(actual[key], value, count, precision):
                    return False
            elif not _close(actual[key], value, .0002 if key == "growth_rate_per_year" else max(.002, 10.0**-precision)):
                return False
    return True


def _typed_record_matches(actual: dict[str, Any], expected: dict[str, Any], matcher) -> bool:
    for key, value in expected.items():
        if key not in actual:
            return False
        if type(value) in (str, bool, int, list):
            if not exact_contract(actual[key], value):
                return False
        elif type(value) is float:
            finite_number(actual[key])
    return matcher(actual, expected)


def _summary_value(summary, flags, key, expected, available, tolerance=.004):
    if flags.get(key) is not available or type(flags.get(key)) is not bool or key not in summary:
        return False
    if not available:
        return summary[key] is None
    if key.endswith("_count") or key == "max_dynasty_lineage_depth":
        return type(summary[key]) is int and summary[key] == expected
    finite_number(summary[key])
    return _close(summary[key], expected, tolerance)


def _replay(payload: dict[str, Any]) -> bool:
    envelope = require_native_social_availability(payload)
    summary = payload["summary"]
    for key, expected in _models().items():
        if not exact_contract(payload.get(key), expected) or summary.get(key) != expected["model_type"]:
            return False
    flags = summary.get("native_social_summary_availability")
    if type(flags) is not dict:
        return False
    cells, regions, cultures = (payload[k] for k in ("cells", "political_regions", "cultures"))
    borders = indexed_records(payload,"borders")
    flows = indexed_records(payload,"trade_flows")
    populations = population_records_v2(payload)
    precision = summary["output_float_precision"]
    if any(not _population_matches_v2(actual, expected, precision) for actual, expected in zip(payload["population_regions"], populations, strict=True)):
        return False
    by_region = {p["region_id"]:p for p in populations}
    pairs = set()
    for border in borders:
        values = [border.get(k) for k in ("region_a", "region_b", "cell_a", "cell_b")]
        if any(type(v) is not int for v in values):
            return False
        if min(values) < 0:
            continue
        if values[0] == values[1] or values[0] not in by_region or values[1] not in by_region or values[2] not in range(len(cells)) or values[3] not in range(len(cells)):
            return False
        pairs.add(tuple(sorted(values[:2])))
    unavailable_pairs = sorted(pair for pair in pairs if not all(by_region[r]["population_estimate_available"] and by_region[r]["capacity_estimate_available"] for r in pair))
    complete_conflicts = not unavailable_pairs
    coverage = {"conflict_candidate_pair_count":len(pairs), "conflict_supported_pair_count":len(pairs)-len(unavailable_pairs), "conflict_unavailable_region_pairs":[list(p) for p in unavailable_pairs], "conflict_inference_available":complete_conflicts}
    if any(not exact_contract(envelope[k], v) for k,v in coverage.items()):
        return False
    # The existing independent equations are used only when every input
    # actually read by global candidate selection is available.
    conflicts = _conflict_records(cells,regions,borders,flows,cultures,populations) if complete_conflicts else []
    actual_conflicts = payload["conflicts"]
    if len(actual_conflicts) != len(conflicts) or any(not _typed_record_matches(a,e,_conflict_matches) for a,e in zip(actual_conflicts,conflicts)):
        return False
    culture_by_region = {c["homeland_region_id"]:c for c in cultures}
    founding_regions = {e["region_id"] for e in payload["historical_events"] if e["type"] == "state_foundation"}
    candidate_regions = {r for pair in pairs for r in pair}
    available_regions = [r for r in regions if by_region[r["id"]]["population_estimate_available"] and culture_by_region[r["id"]]["continuity_estimate_available"] and (complete_conflicts or r["id"] not in candidate_regions) and r["id"] in founding_regions]
    unavailable_regions = [r["id"] for r in regions if r not in available_regions]
    complete_dynasties = not unavailable_regions
    coverage = {"dynasty_applicable_region_count":len(regions), "dynasty_available_region_count":len(available_regions), "dynasty_unavailable_region_ids":unavailable_regions, "dynasty_inference_available":complete_dynasties}
    if any(not exact_contract(envelope[k],v) for k,v in coverage.items()):
        return False
    dynasties = _dynasty_records(available_regions,cultures,payload["historical_events"],populations,conflicts)
    if len(payload["dynasties"]) != len(dynasties) or any(not _typed_record_matches(a,e,_dynasty_matches) for a,e in zip(payload["dynasties"],dynasties)):
        return False
    population_complete = all(p["population_estimate_available"] for p in populations)
    if type(summary.get("population_region_count")) is not int or summary["population_region_count"] != len(populations):
        return False
    if type(summary.get("available_population_region_count")) is not int or summary["available_population_region_count"] != sum(p["population_estimate_available"] for p in populations):
        return False
    for key, expected in (("recorded_conflict_count",len(conflicts)),("recorded_dynasty_count",len(dynasties))):
        if type(summary.get(key)) is not int or summary[key] != expected:
            return False
    total = sum(p["estimated_population"] for p in populations) if population_complete else None
    pressure = sum(p["population_pressure"] for p in populations)/len(populations) if population_complete and populations else None
    if not _summary_value(summary,flags,"estimated_world_population",total,population_complete,max(1.0,abs(total or 0.0)*.0005)):
        return False
    if not _summary_value(summary,flags,"mean_population_pressure",pressure,population_complete and bool(populations),.002):
        return False
    divisor = max(1,len(conflicts));scale=10.0**precision
    values = {"conflict_count":len(conflicts), "high_intensity_conflict_count":sum(math.floor(c["intensity"]*scale+.5)/scale >= .65 for c in conflicts), "high_economic_disruption_conflict_count":sum(c["economic_disruption_index"] >= .65 for c in conflicts), "total_mobilized_population":sum(c["mobilized_population"] for c in conflicts), "max_conflict_casualty_rate":max((c["casualty_rate"] for c in conflicts),default=0.0)}
    for summary_key,record_key in (("mean_conflict_intensity","intensity"),("mean_war_duration_years","war_duration_years"),("mean_conflict_logistics_strain_index","logistics_strain_index"),("mean_conflict_economic_disruption_index","economic_disruption_index"),("mean_conflict_casualty_rate","casualty_rate")):
        values[summary_key]=sum(c[record_key] for c in conflicts)/divisor
    for key,value in values.items():
        if not _summary_value(summary,flags,key,value,complete_conflicts,max(1.0,abs(value)*.001) if key=="total_mobilized_population" else .004):
            return False
    values={"dynasty_count":len(dynasties),"dynastic_lineage_count":sum(d["parent_dynasty_id"]>=0 for d in dynasties),"dynasty_root_count":sum(d["parent_dynasty_id"]<0 for d in dynasties),"dynasty_successor_link_count":sum(d["successor_dynasty_id"]>=0 for d in dynasties),"max_dynasty_lineage_depth":max((d["lineage_depth"] for d in dynasties),default=0),"mean_dynastic_continuity_index":sum(d["dynastic_continuity_index"] for d in dynasties)/max(1,len(dynasties))}
    return all(_summary_value(summary,flags,k,v,complete_dynasties) for k,v in values.items())


def validate_native_civilization_availability(payload: dict[str, Any]) -> list[str]:
    try:
        valid = _replay(payload)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        valid = False
    return [] if valid else ["native population, conflict, or dynasty availability causal replay invalid"]
