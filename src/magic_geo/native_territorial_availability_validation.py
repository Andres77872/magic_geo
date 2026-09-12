"""Independent base-territory and available historical snapshot replay."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import math
from typing import Any

from .native_social_availability import (
    NATIVE_SOCIAL_MODEL, exact_contract, finite_number, require_native_social_availability,
)
from .territorial_geography_validation import (
    AREA_FACTORS, POPULATION_FACTORS, _base_regions, _clamp, _close,
    _relative_close, _ring_matches, _model,
)

_GEOMETRY_FIELDS = (
    "area_km2", "stability_index", "boundary_perimeter_km", "dissolved_polygon_area_km2",
    "polygon_area_error_fraction", "compactness_index", "geometry_quality",
)


def _model_v2():
    model = _model()
    model.update({
        "model_type":"causal_era_scaled_spherical_region_territorial_snapshots_v2",
        "source_native_social_availability_model":NATIVE_SOCIAL_MODEL["model_type"],
        "source_population_region_model":"causal_area_weighted_capacity_occupancy_population_regions_v2",
        "source_culture_region_model":"causal_political_homeland_barrier_trade_culture_regions_v2",
        "source_historical_event_model":"causal_region_culture_language_trade_site_timeline_v2",
        "source_conflict_model":"causal_border_pair_pressure_trade_conflict_selection_v2",
        "source_political_region_model":"causal_capital_barrier_partition_political_regions_v1",
        "availability_policy":"retain_unscaled_base_geometry_null_unavailable_historical_geometry_population",
        "geometry_radius_source":"planet_parameters.radius_km_native_geometry_parameter",
    })
    return model


def snapshot_records_v2(payload: dict[str, Any]) -> list[dict[str, Any]]:
    populations = {p["region_id"]:p for p in payload["population_regions"]}
    conflicts = defaultdict(float)
    for conflict in payload["conflicts"]:
        for key in ("region_a","region_b"):
            conflicts[(conflict[key],conflict["era_id"])] += finite_number(conflict["intensity"])
    pairs = {tuple(sorted((b["region_a"],b["region_b"]))) for b in payload["borders"] if min(b["region_a"],b["region_b"],b["cell_a"],b["cell_b"]) >= 0}
    candidate_regions = {r for pair in pairs for r in pair}
    conflict_complete = payload["native_social_availability"]["conflict_inference_available"]
    for cell in payload["cells"]:
        if finite_number(cell["area_km2"]) < 0:
            raise ValueError("negative physical area")
        finite_number(cell["lon_deg"])
    radius = finite_number(payload["planet_parameters"]["radius_km"])
    if radius <= 0:
        raise ValueError("positive native geometry radius required")
    bases, land_area = _base_regions(payload, radius_km=radius)
    snapshots = []
    for era in payload["historical_eras"]:
        era_id = era["id"]
        factor_index = min(3,max(0,era_id))
        rows = []
        regional_conflicts = []
        for original in bases:
            row = deepcopy(original)
            region_id = row["region_id"]
            population = populations.get(region_id)
            culture_id = row["culture_region_id"]
            culture = payload["cultures"][culture_id] if culture_id >= 0 else None
            row["base_area_km2"] = row["area_km2"]
            row["base_dissolved_polygon_area_km2"] = row["dissolved_polygon_area_km2"]
            row["base_boundary_perimeter_km"] = row["boundary_perimeter_km"]
            geometry_available = row["base_area_km2"] > 0 and culture is not None and culture["continuity_estimate_available"] and (conflict_complete or region_id not in candidate_regions) and era["mean_connectivity_available"]
            population_available = geometry_available and population is not None and population["population_estimate_available"]
            row["geometry_estimate_available"] = geometry_available
            row["population_estimate_available"] = population_available
            row["estimated_population"] = None
            if not geometry_available:
                for key in _GEOMETRY_FIELDS:
                    row[key] = None
                rows.append(row)
                continue
            regional_conflict = _clamp(conflicts[(region_id,era_id)]/2.0)
            regional_conflicts.append(regional_conflict)
            stability = _clamp(.42+.42*finite_number(culture["continuity_index"])-.30*regional_conflict+.10*finite_number(era["mean_connectivity"]))
            factor = AREA_FACTORS[factor_index]*(.82+.18*stability)
            row["area_km2"] *= factor
            row["dissolved_polygon_area_km2"] *= factor
            row["boundary_perimeter_km"] *= math.sqrt(factor)
            if row["area_km2"] > 0 and row["dissolved_polygon_area_km2"] > 0:
                row["polygon_area_error_fraction"] = abs(row["dissolved_polygon_area_km2"]-row["area_km2"])/row["area_km2"]
            if row["boundary_perimeter_km"] > 0 and row["dissolved_polygon_area_km2"] > 0:
                row["compactness_index"] = _clamp(4*math.pi*row["dissolved_polygon_area_km2"]/max(1.0,row["boundary_perimeter_km"]**2))
            row["geometry_quality"] = _clamp(.62*_clamp(1-row["polygon_area_error_fraction"])+.38*_clamp(len(row["boundary_ring"])/24.0))
            row["stability_index"] = stability
            if population_available:
                row["estimated_population"] = finite_number(population["estimated_population"])*POPULATION_FACTORS[factor_index]*(.82+.22*stability)
            rows.append(row)
        geometry_available = bool(rows) and land_area > 0 and all(r["geometry_estimate_available"] for r in rows)
        population_available = bool(rows) and all(r["population_estimate_available"] for r in rows)
        snapshot = {
            "id":len(snapshots), "era_id":era_id, "dominant_process":era["dominant_process"],
            "year_bp":.5*(finite_number(era["start_year_bp"])+finite_number(era["end_year_bp"])),
            "region_count":len(rows), "regions":rows,
            "geometry_estimate_available":geometry_available, "population_estimate_available":population_available,
            "estimated_population":sum(r["estimated_population"] for r in rows) if population_available else None,
            "assigned_land_fraction":None, "largest_region_area_km2":None, "largest_region_id":None,
            "fragmentation_index":None,
        }
        if geometry_available:
            assigned = _clamp(sum(r["area_km2"] for r in rows)/land_area)
            largest = max(rows,key=lambda r:r["area_km2"])
            share = largest["area_km2"]/(assigned*land_area) if assigned > 0 else 0.0
            snapshot.update({"assigned_land_fraction":assigned,"largest_region_area_km2":largest["area_km2"],"largest_region_id":largest["region_id"],"fragmentation_index":_clamp((1-share if len(rows)>1 else 0)*.72+sum(regional_conflicts)/len(rows)*.28)})
        snapshots.append(snapshot)
    return snapshots


def _matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    if type(actual) is not dict:
        return False
    for key,value in expected.items():
        if key not in actual:
            return False
        if key == "regions":
            if type(actual[key]) is not list or len(actual[key]) != len(value) or any(not _matches(a,e) for a,e in zip(actual[key],value)):
                return False
        elif key == "boundary_ring":
            if not _ring_matches(actual[key],value):
                return False
        elif value is None or key in {"id","era_id","region_id","capital_settlement_id","culture_region_id","language_region_id","cell_count","region_count","largest_region_id","crosses_antimeridian","boundary_cell_ids","geometry_estimate_available","population_estimate_available","dominant_process"}:
            if not exact_contract(actual[key],value):
                return False
        else:
            finite_number(actual[key]);finite_number(value)
            if key in {"area_km2","boundary_perimeter_km","dissolved_polygon_area_km2","estimated_population","largest_region_area_km2","base_area_km2","base_dissolved_polygon_area_km2","base_boundary_perimeter_km"}:
                if not _relative_close(actual[key],value):
                    return False
            elif not _close(actual[key],value,.001 if key in {"centroid_lat_deg","centroid_lon_deg","year_bp"} else .003):
                return False
    return True


def _replay(payload):
    envelope = require_native_social_availability(payload)
    model = _model_v2()
    summary = payload["summary"]
    if not exact_contract(payload.get("territorial_snapshot_model"),model) or summary.get("territorial_snapshot_model") != model["model_type"]:
        return False
    expected = snapshot_records_v2(payload)
    if len(payload["territorial_snapshots"]) != len(expected) or any(not _matches(a,e) for a,e in zip(payload["territorial_snapshots"],expected)):
        return False
    complete = all(s["geometry_estimate_available"] and s["population_estimate_available"] for s in expected)
    if envelope["territorial_snapshot_inference_available"] is not complete:
        return False
    for key,value in (("territorial_snapshot_count",len(expected)),("snapshot_region_record_count",sum(s["region_count"] for s in expected))):
        if type(summary.get(key)) is not int or summary[key] != value:
            return False
    geometry_complete = all(s["geometry_estimate_available"] for s in expected)
    flags = summary.get("native_social_summary_availability")
    if type(flags) is not dict:
        return False
    keys = ("snapshot_polygon_region_count","mean_snapshot_fragmentation_index","mean_snapshot_polygon_area_error_fraction","mean_snapshot_compactness_index","mean_snapshot_geometry_quality","mean_snapshot_boundary_perimeter_km")
    if any(type(flags.get(k)) is not bool or flags[k] != geometry_complete or k not in summary for k in keys):
        return False
    if not geometry_complete:
        return all(summary[k] is None for k in keys)
    polygon = [r for s in expected for r in s["regions"] if len(r["boundary_ring"]) >= 3]
    values = {"snapshot_polygon_region_count":len(polygon),"mean_snapshot_fragmentation_index":sum(s["fragmentation_index"] for s in expected)/max(1,len(expected))}
    for key,field in (("mean_snapshot_polygon_area_error_fraction","polygon_area_error_fraction"),("mean_snapshot_compactness_index","compactness_index"),("mean_snapshot_geometry_quality","geometry_quality"),("mean_snapshot_boundary_perimeter_km","boundary_perimeter_km")):
        values[key]=sum(r[field] for r in polygon)/max(1,len(polygon))
    for key,value in values.items():
        if key == "snapshot_polygon_region_count":
            if type(summary[key]) is not int or summary[key] != value:
                return False
        else:
            finite_number(summary[key])
            if not _close(summary[key],value,max(.004,abs(value)*.001) if key=="mean_snapshot_boundary_perimeter_km" else .004):
                return False
    return True


def validate_native_territorial_availability(payload: dict[str, Any]) -> list[str]:
    try:
        valid = _replay(payload)
    except (AttributeError,IndexError,KeyError,TypeError,ValueError,OverflowError,ZeroDivisionError):
        valid = False
    return [] if valid else ["native territorial availability causal replay invalid"]
