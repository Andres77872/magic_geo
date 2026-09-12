"""Independent natural aquifer/groundwater contract and complete replay.

The legacy arithmetic below is retained from the independent hydrology validator.
Natural v2 reuses that arithmetic with explicitly mapped natural inputs; the
producer is never imported. This does not validate Darcy physics or safe yield.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
import math
from typing import Any

from .marine_distance_validation import require_marine_distance


class NaturalGroundwaterError(ValueError):
    """A typed source, declaration or independently replayed output is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise NaturalGroundwaterError("natural groundwater: " + message)


def _finite(value: Any) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _rounded_close(actual: Any, expected: float, digits: int) -> bool:
    """Fixed binary64 allowance, independent of producer-declared tolerances."""
    if not _finite(actual) or not _finite(expected):
        return False
    target = round(expected, digits)
    allowance = max(1.0e-10 if digits <= 6 else 1.0e-12, 8 * math.ulp(target))
    return math.isfinite(allowance) and abs(actual - target) <= allowance


def _same(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(_same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(_same(a, b) for a, b in zip(actual, expected))
    if type(expected) in (int, float) and type(actual) in (int, float):
        return _finite(actual) and actual == expected
    return type(actual) is type(expected) and actual == expected


def _finite_tree(value: Any, path: str) -> None:
    if isinstance(value, dict):
        _require(all(isinstance(k, str) for k in value), path + " object keys must be strings")
        for k, v in value.items():
            _finite_tree(v, path + "." + k)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _finite_tree(v, f"{path}[{i}]")
    elif type(value) in (int, float):
        _require(_finite(value), path + " must be finite and representable")
    else:
        _require(type(value) in (str, bool, type(None)), path + " has unsupported type")


def _declaration_version(world: dict[str, Any], key: str, *, required: bool = False) -> int:
    summary = world.get("summary", {})
    _require(isinstance(summary, dict), "summary must be an object")
    if key not in world:
        _require(not required, key + " declaration is required")
        _require(key not in summary, key + " summary identity lacks its declaration")
        return 2
    model = world[key]
    _require(isinstance(model, dict), key + " must be an object")
    for version, policies in ((1, _LEGACY_POLICIES), (2, _NATURAL_POLICIES)):
        policy = policies[key]
        dynamic = _MODEL_DYNAMIC[key]
        if model.keys() == policy.keys() | dynamic.keys() and all(_same(model[k], v) for k, v in policy.items()):
            for k, kind in dynamic.items():
                _require(type(model[k]) is int and model[k] >= 0 if kind == "count" else _finite(model[k]), key + "." + k + " has invalid type or range")
            _require(summary.get(key) == policy["model_type"], key + " summary identity mismatch")
            return version
    raise NaturalGroundwaterError("natural groundwater: unknown or malformed " + key)


def natural_groundwater_model_version(world: dict[str, Any], stage: str) -> int:
    """Own-version dispatch, requiring an exact compatible groundwater parent."""
    _require(isinstance(world, dict), "world must be an object")
    _require(stage in ("aquifer", "groundwater"), "unknown stage")
    key = "aquifer_resource_model" if stage == "aquifer" else "groundwater_flow_model"
    version = _declaration_version(world, key)
    if stage == "groundwater":
        parent = _declaration_version(world, "aquifer_resource_model", required=True)
        _require(parent == version, "groundwater and aquifer model versions must match")
    elif "groundwater_flow_model" in world or "groundwater_flow_model" in world.get("summary", {}):
        downstream = _declaration_version(world, "groundwater_flow_model", required=True)
        _require(downstream == version, "groundwater and aquifer model versions must match")
    if "groundwater_recharge_model" in world or "groundwater_recharge_model" in world.get("summary", {}):
        _declaration_version(world, "groundwater_recharge_model", required=True)
    if version == 1:
        summary = world.get("summary", {})
        mixed = bool({"mean_aquifer_natural_limitation_index", "high_natural_limitation_aquifer_cell_count"} & summary.keys())
        for family in ("cells", "aquifer_systems", "groundwater_flow_systems"):
            records = world.get(family, [])
            if isinstance(records, list):
                mixed = mixed or any(isinstance(r, dict) and bool({"aquifer_natural_limitation_index", "mean_aquifer_natural_limitation_index", "high_natural_limitation_cell_count"} & r.keys()) for r in records)
        _require(not mixed, "natural v2 mirrors cannot be declared as historical v1")
    return version


def validate_natural_groundwater_inputs(world: dict[str, Any], stage: str) -> None:
    """Validate consumed natural sources before mutation; social fields are unused."""
    _require(isinstance(world, dict), "world must be an object")
    _require(isinstance(world.get("summary", {}), dict), "summary must be an object")
    cells = world.get("cells")
    _require(isinstance(cells, list), "cells must be a list")
    marine_contract = require_marine_distance(world)
    ids: set[int] = set()
    for c in cells:
        _require(isinstance(c, dict), "every cell must be an object")
        cid = c.get("id")
        _require(type(cid) is int and cid >= 0 and cid not in ids, "cell IDs must be unique nonnegative integers")
        ids.add(cid)
        _require(_finite(c.get("area_km2")) and c["area_km2"] > 0, f"cell {cid}: area_km2 must be finite and positive")
        for key in ("is_water", "is_lake", "is_closed_basin"):
            _require(type(c.get(key)) is bool, f"cell {cid}: {key} must be an explicit boolean")
        for key in ("water_body_type", "lithology", "landform"):
            _require(isinstance(c.get(key), str) and bool(c[key]), f"cell {cid}: {key} must be a nonempty string")
        neighbors = c.get("neighbors")
        _require(isinstance(neighbors, list) and all(type(n) is int and n >= 0 for n in neighbors), f"cell {cid}: neighbors must contain integer IDs")
        _require(len(neighbors) == len(set(neighbors)) and cid not in neighbors, f"cell {cid}: neighbors must be unique and nonself")
        _require(type(c.get("basin_id")) is int and c["basin_id"] >= -1, f"cell {cid}: basin_id must be an integer >= -1")
        if c["water_body_type"] not in {"ocean", "continental_shelf", "inland_sea"}:
            for key in ("sediment_thickness_m", "soil_drainage_index", "soil_moisture_index", "soil_salinity_index",
                        "seasonal_aridity_index", "ice_thickness_m", "flow_accumulation", "infiltration_mm_y"):
                _require(_finite(c.get(key)), f"cell {cid}: {key} must be finite numeric, not boolean")
        if stage == "groundwater":
            for key in ("elevation_m", "water_depth_m"):
                _require(_finite(c.get(key)), f"cell {cid}: {key} must be finite numeric")
            _require(c["water_depth_m"] >= 0, f"cell {cid}: water_depth_m must be nonnegative")
            _require(type(c.get("is_river")) is bool, f"cell {cid}: is_river must be a boolean")
            for key in ("wetland_extent_index", "distance_to_marine_water_km"):
                if key == "distance_to_marine_water_km" and marine_contract:
                    continue  # The complete typed source was independently replayed above.
                _require(_finite(c.get(key)), f"cell {cid}: {key} must be finite numeric")
    for c in cells:
        _require(all(n in ids for n in c["neighbors"]), f"cell {c['id']}: unknown neighbor")
        _require(c["basin_id"] == -1 or c["basin_id"] in ids, f"cell {c['id']}: basin outlet references unknown cell")
    _require(math.isfinite(sum(float(c["area_km2"]) for c in cells)), "total cell area is unrepresentable")
    if stage == "groundwater":
        errors = validate_natural_aquifer_resources(world)
        _require(not errors, "groundwater requires independently validated aquifer parent: " + (errors[0] if errors else ""))


def _owned_output_shape(world: dict[str, Any], stage: str, version: int) -> None:
    cells = world.get("cells")
    _require(isinstance(cells, list) and all(isinstance(c, dict) for c in cells), "cells must be objects")
    fields = set(_OWNED[stage]["cell"])
    summary_fields = set(_OWNED[stage]["summary"])
    if stage == "aquifer" and version == 2:
        fields.remove("aquifer_extraction_risk_index")
        fields.add("aquifer_natural_limitation_index")
        summary_fields -= {"mean_aquifer_extraction_risk_index", "groundwater_stressed_cell_count"}
        summary_fields |= {"mean_aquifer_natural_limitation_index", "high_natural_limitation_aquifer_cell_count"}
    for c in cells:
        cid = c.get("id")
        for key in fields:
            _require(key in c, f"cell {cid}: missing " + key)
            value = c[key]
            if key.endswith("_id"):
                _require(type(value) is int and value >= -1, f"cell {cid}: " + key + " must be an integer >= -1")
            elif key.endswith(("_class", "_regime")):
                _require(isinstance(value, str) and bool(value), f"cell {cid}: " + key + " must be a string")
            else:
                _require(_finite(value), f"cell {cid}: " + key + " must be finite numeric")
        if version == 2:
            _require("aquifer_extraction_risk_index" not in c, f"cell {cid}: legacy extraction-risk alias in natural v2")
    summary = world.get("summary")
    _require(isinstance(summary, dict), "summary must be an object")
    for key in summary_fields:
        _require(key in summary, "missing summary " + key)
        value = summary[key]
        _finite_tree(value, "summary." + key)
        if key.endswith("_count"):
            _require(type(value) is int and value >= 0, "summary " + key + " must be a count")
        elif key.endswith("_counts"):
            _require(isinstance(value, dict) and all(type(v) is int and v >= 0 for v in value.values()), "summary " + key + " must contain counts")
        elif not key.endswith("_model"):
            _require(_finite(value), "summary " + key + " must be finite numeric")
    if version == 2:
        _require(not {"mean_aquifer_extraction_risk_index", "groundwater_stressed_cell_count"} & summary.keys(), "legacy risk/stress summary aliases in natural v2")
    family = "aquifer_systems" if stage == "aquifer" else "groundwater_flow_systems"
    records = world.get(family)
    _require(isinstance(records, list), family + " must be a list")
    for index, r in enumerate(records):
        _require(isinstance(r, dict), family + " records must be objects")
        _finite_tree(r, family + f"[{index}]")
        _require(type(r.get("id")) is int and r["id"] == index, family + " IDs must be sequential")
        for key, value in r.items():
            if key.endswith(("_count", "_id")) or key == "id":
                _require(type(value) is int, family + "." + key + " must be an integer")
            elif key.endswith("_ids"):
                _require(isinstance(value, list) and all(type(i) is int and i >= 0 for i in value) and len(value) == len(set(value)), family + "." + key + " must contain unique IDs")
            elif key.endswith("_counts"):
                _require(isinstance(value, dict) and all(type(v) is int and v >= 0 for v in value.values()), family + "." + key + " must contain counts")
            elif key.startswith(("mean_", "total_")) or key.endswith(("_km3_y", "_km2", "_ratio", "_fraction")):
                _require(_finite(value), family + "." + key + " must be finite numeric")
        if version == 2:
            _require(not {"mean_aquifer_extraction_risk_index", "stressed_cell_count"} & r.keys(), family + ": legacy risk/stress aliases in natural v2")


def _legacy_replay_view(world: dict[str, Any], stage: str) -> dict[str, Any]:
    """Local independent-oracle view; never published or passed to producers.

    N is replayed from raw natural inputs by the legacy equation with its social
    term exactly zero. Mapping field labels reuses an established independent
    equation without modifying caller certificates or inferring N from old risk.
    """
    view = {**world, "cells": [dict(c) for c in world["cells"]], "summary": dict(world["summary"])}
    for c in view["cells"]:
        c["settlement_score"] = 0.0
        c["aquifer_extraction_risk_index"] = c["aquifer_natural_limitation_index"]
    for key in ("aquifer_resource_model", "groundwater_flow_model"):
        if key not in world or (key == "groundwater_flow_model" and stage != "groundwater"):
            continue
        view[key] = {**_LEGACY_POLICIES[key], **{k:world[key][k] for k in _MODEL_DYNAMIC[key]}}
        view["summary"][key] = _LEGACY_POLICIES[key]["model_type"]
    view["summary"]["mean_aquifer_extraction_risk_index"] = world["summary"]["mean_aquifer_natural_limitation_index"]
    view["summary"]["groundwater_stressed_cell_count"] = world["summary"]["high_natural_limitation_aquifer_cell_count"]
    for family in ("aquifer_systems", "groundwater_flow_systems"):
        if family not in world or (family == "groundwater_flow_systems" and stage != "groundwater"):
            continue
        view[family] = []
        for r in world[family]:
            copy = dict(r)
            copy["mean_aquifer_extraction_risk_index"] = copy.pop("mean_aquifer_natural_limitation_index")
            if family == "aquifer_systems":
                copy["stressed_cell_count"] = copy.pop("high_natural_limitation_cell_count")
            view[family].append(copy)
    return view


def validate_natural_aquifer_resources(world: Any) -> list[str]:
    """At most one diagnostic; exact known v1 or natural v2 source/output replay."""
    try:
        version = natural_groundwater_model_version(world, "aquifer")
        _declaration_version(world, "aquifer_resource_model", required=True)
        _declaration_version(world, "groundwater_recharge_model", required=True)
        if version == 2:
            validate_natural_groundwater_inputs(world, "aquifer")
        _owned_output_shape(world, "aquifer", version)
        view = _legacy_replay_view(world, "aquifer") if version == 2 else world
        args = view, view["summary"], {c["id"]: c for c in view["cells"]}
        _require(len(args[2]) == len(view["cells"]), "duplicate cell IDs")
        for errors in (_validate_groundwater_recharge(*args, strict=version == 2), _validate_aquifer_resources(*args, strict=version == 2)):
            _require(not errors, errors[0] if errors else "")
        return []
    except NaturalGroundwaterError as exc:
        return [str(exc)]
    except (TypeError, ValueError, KeyError, OverflowError, ArithmeticError) as exc:
        return ["natural groundwater: malformed aquifer input or output (" + type(exc).__name__ + ")"]


def validate_natural_groundwater_flow(world: Any) -> list[str]:
    """At most one diagnostic; checks aquifer parent then every routed output."""
    try:
        version = natural_groundwater_model_version(world, "groundwater")
        _declaration_version(world, "groundwater_flow_model", required=True)
        if version == 2:
            validate_natural_groundwater_inputs(world, "groundwater")
        else:
            errors = validate_natural_aquifer_resources(world)
            _require(not errors, errors[0] if errors else "")
        _owned_output_shape(world, "groundwater", version)
        view = _legacy_replay_view(world, "groundwater") if version == 2 else world
        errors = _validate_groundwater_flow(view, view["summary"], {c["id"]:c for c in view["cells"]}, natural=version == 2)
        _require(not errors, errors[0] if errors else "")
        # Complete record/schema coverage applies to historical valid outputs
        # as well, without changing their equations or accepted numeric values.
        if version == 1:
            _validate_flow_records_and_means(view, view["summary"], {c["id"]:c for c in view["cells"]})
        return []
    except NaturalGroundwaterError as exc:
        return [str(exc)]
    except (TypeError, ValueError, KeyError, OverflowError, ArithmeticError) as exc:
        return ["natural groundwater: malformed flow input or output (" + type(exc).__name__ + ")"]


def _validate_flow_records_and_means(world: dict[str, Any], summary: dict[str, Any], by_id: dict[int, dict[str, Any]]) -> None:
    """Replay all record coverage and aggregates from independently checked cells."""
    candidates = {cid:c for cid,c in by_id.items() if c["aquifer_class"] != "marine_excluded" and c["water_body_type"] not in {"ocean", "continental_shelf", "inland_sea"}}
    groups: dict[int, list[int]] = {}
    for cid in sorted(candidates):
        source = candidates[cid]["aquifer_system_id"]
        if source >= 0:
            groups.setdefault(source, []).append(cid)
    aquifers = {r["id"]:r for r in world["aquifer_systems"]}
    expected_records = []
    assignment = {}
    volume_fields = {
        "total_groundwater_recharge_km3_y":"groundwater_recharge_km3_y",
        "total_groundwater_lateral_inflow_km3_y":"groundwater_lateral_inflow_km3_y",
        "total_groundwater_internal_lateral_outflow_km3_y":"groundwater_internal_lateral_outflow_km3_y",
        "total_groundwater_discharge_km3_y":"groundwater_discharge_km3_y",
        "total_groundwater_lateral_flow_km3_y":"groundwater_lateral_flow_km3_y",
        "total_groundwater_retained_storage_km3_y":"groundwater_retained_storage_km3_y",
        "groundwater_flow_mass_balance_residual_km3_y":"groundwater_flow_mass_balance_residual_km3_y",
    }
    mean_fields = {
        "mean_hydraulic_head_m":"groundwater_hydraulic_head_m",
        "mean_groundwater_gradient_index":"groundwater_gradient_index",
        "mean_groundwater_discharge_mm_y":"groundwater_discharge_mm_y",
        "mean_spring_discharge_index":"spring_discharge_index",
        "mean_baseflow_support_index":"baseflow_support_index",
        "mean_aquifer_extraction_risk_index":"aquifer_extraction_risk_index",
    }
    for source, ids in sorted(groups.items()):
        _require(source in aquifers, "flow system references unknown aquifer")
        group = [by_id[cid] for cid in ids]
        index = len(expected_records)
        assignment.update({cid:index for cid in ids})
        regimes = Counter(c["groundwater_flow_regime"] for c in group)
        terminals = [cid for cid in ids if by_id[cid]["groundwater_flow_to_cell_id"] not in ids]
        discharge_ids = [cid for cid in ids if by_id[cid]["groundwater_discharge_mm_y"] >= 25.0 or by_id[cid]["spring_discharge_index"] >= .45]
        recharge_ids = [cid for cid in ids if by_id[cid]["groundwater_recharge_mm_y"] >= 50.0]
        outlet = min(discharge_ids or terminals or ids, key=lambda cid:(-by_id[cid]["groundwater_discharge_km3_y"],cid))
        sums = {key:sum(float(c[field]) for c in group) for key,field in volume_fields.items()}
        recharge = sums["total_groundwater_recharge_km3_y"]
        discharge = sums["total_groundwater_discharge_km3_y"]
        record = {
            "id":index,"aquifer_system_id":source,"basin_id":aquifers[source]["basin_id"],
            "flow_regime":min(regimes, key=lambda k:(-regimes[k],k)),"cell_count":len(ids),"cell_ids":ids,
            "recharge_cell_ids":recharge_ids,"discharge_cell_ids":discharge_ids,"terminal_cell_ids":terminals,
            "outlet_cell_id":outlet,"area_km2":round(sum(float(c["area_km2"]) for c in group),6),
            **{key:round(value,12 if key == "groundwater_flow_mass_balance_residual_km3_y" else 6) for key,value in sums.items()},
            "groundwater_balance_residual_km3_y":round(recharge-discharge,6),
            "discharge_to_recharge_ratio":round(discharge/recharge,6) if recharge>0 else 0.0,
            **{key:round(sum(float(c[field]) for c in group)/len(ids),6) for key,field in mean_fields.items()},
            "river_cell_count":sum(bool(c["is_river"]) for c in group),
            "lake_cell_count":sum(bool(c["is_lake"]) for c in group),
            "wetland_cell_count":sum(c["wetland_extent_index"] >= .35 for c in group),
            "closed_basin_cell_count":sum(bool(c["is_closed_basin"]) for c in group),
            "flow_regime_counts":dict(sorted(regimes.items())),
        }
        _finite_tree(record, f"replayed flow system {index}")
        expected_records.append(record)
    _require(_same(world.get("groundwater_flow_systems"),expected_records), "groundwater system records, source links or aggregates mismatch")
    for cid,c in by_id.items():
        _require(c["groundwater_flow_system_id"] == assignment.get(cid,-1), f"cell {cid}: groundwater system inverse membership mismatch")
    values = [candidates[cid] for cid in sorted(candidates)]
    expected_summary = {
        "groundwater_flow_model":GROUNDWATER_FLOW_MODEL,
        "groundwater_flow_cell_count":len(assignment),
        "groundwater_flow_system_count":len(groups),
        "groundwater_discharge_cell_count":sum(c["groundwater_discharge_mm_y"]>=25 for c in values),
        "spring_candidate_cell_count":sum(c["spring_discharge_index"]>=.45 for c in values),
        "baseflow_supported_river_cell_count":sum(bool(c["is_river"]) and c["baseflow_support_index"]>=.35 for c in values),
        "groundwater_flow_regime_counts":dict(sorted(Counter(c["groundwater_flow_regime"] for c in by_id.values()).items())),
    }
    for key in ("mean_groundwater_gradient_index","mean_groundwater_discharge_mm_y","mean_spring_discharge_index","mean_baseflow_support_index"):
        expected_summary[key] = round(sum(float(c[mean_fields[key]]) for c in values)/len(values),6) if values else 0.0
    for key,value in expected_summary.items():
        _require(_same(summary.get(key),value), "summary " + key + " mismatch")
    # The legacy summary uses raw discharge, whereas source cells are rounded;
    # its independent raw value is already checked in the arithmetic replay.
    recharge = sum(float(c["groundwater_recharge_km3_y"]) for c in values)
    residual_expected = recharge-float(summary["total_groundwater_discharge_km3_y"])
    _require(_finite(residual_expected) and abs(summary["total_groundwater_flow_balance_residual_km3_y"]-residual_expected)<=1.1e-6,
             "summary annual undischarged remainder mismatch")

GROUNDWATER_RECHARGE_MODEL = "infiltration_bounded_aquifer_recharge_v1"
GROUNDWATER_MIN_RECHARGE_FRACTION = 0.05
GROUNDWATER_MAX_RECHARGE_FRACTION = 0.85
AQUIFER_RESOURCE_MODEL = "finite_recharge_causal_aquifer_resources_v1"
AQUIFER_MIN_SYSTEM_PRODUCTIVITY_INDEX = 0.18
AQUIFER_MIN_SYSTEM_RECHARGE_MM_Y = 25.0
GROUNDWATER_FLOW_MODEL = "descending_head_recharge_conserving_groundwater_flow_v1"
GROUNDWATER_FLOW_MINIMUM_RECEIVER_HEAD_DROP_M = 0.5
GROUNDWATER_FLOW_GRADIENT_SCALE_M = 900.0
GROUNDWATER_FLOW_MAXIMUM_LATERAL_EXPORT_FRACTION = 0.82
GROUNDWATER_ALLUVIAL_LANDFORMS = {
    "floodplain",
    "delta",
    "river_valley",
    "coastal_plain",
    "lacustrine_basin",
    "glacial_lake",
}
GROUNDWATER_LITHOLOGY_PERMEABILITY = {
    "limestone": 0.82,
    "sandstone": 0.76,
    "basalt": 0.44,
    "volcanic": 0.48,
    "granite": 0.30,
    "metamorphic": 0.28,
    "shale": 0.18,
}
def _validate_groundwater_recharge(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
    *, strict: bool = False,
) -> list[str]:
    """Replay the infiltration-bounded aquifer/vadose source partition."""

    failure = ["groundwater recharge model or source partition invalid"]
    model = payload.get("groundwater_recharge_model", {})
    if (
        not isinstance(model, dict)
        or model.get("model_type") != GROUNDWATER_RECHARGE_MODEL
        or model.get("source_field") != "infiltration_mm_y"
        or model.get("domain") != "non_marine_cells"
        or model.get("recharge_fraction_model")
        != "lithology_soil_drainage_sediment_lake_salinity_ice_aridity_v1"
        or model.get("marine_cell_treatment")
        != "zero_source_recharge_and_vadose_retention"
        or not bool(model.get("mass_conserving_source_partition", False))
        or model.get("model_limitation")
        != "annual_diagnostic_partition_without_transient_vadose_storage_or_groundwater_return_flow"
        or summary.get("groundwater_recharge_model")
        != GROUNDWATER_RECHARGE_MODEL
        or abs(
            float(model.get("minimum_recharge_fraction", -1.0))
            - GROUNDWATER_MIN_RECHARGE_FRACTION
        )
        > 1.0e-12
        or abs(
            float(model.get("maximum_recharge_fraction", -1.0))
            - GROUNDWATER_MAX_RECHARGE_FRACTION
        )
        > 1.0e-12
    ):
        return failure

    source_volume = 0.0
    recharge_volume = 0.0
    vadose_volume = 0.0
    residual_volume = 0.0
    marine_types = {"ocean", "continental_shelf", "inland_sea"}
    for cell in cells_by_id.values():
        try:
            water_body = str(cell.get("water_body_type", "land"))
            is_marine = water_body in marine_types
            area = max(0.0, float(cell.get("area_km2", 0.0)))
            source = float(
                cell.get("groundwater_recharge_source_infiltration_mm_y", -1.0)
            )
            fraction = float(cell.get("groundwater_recharge_fraction", -1.0))
            recharge = float(cell.get("groundwater_recharge_mm_y", -1.0))
            recharge_km3 = float(cell.get("groundwater_recharge_km3_y", -1.0))
            vadose = float(cell.get("vadose_zone_retention_mm_y", -1.0))
            vadose_km3 = float(cell.get("vadose_zone_retention_km3_y", -1.0))
            residual = float(
                cell.get("groundwater_recharge_mass_balance_residual_mm_y", math.inf)
            )
        except (TypeError, ValueError):
            return failure
        if area <= 0.0:
            return failure

        expected_source = 0.0
        expected_fraction = 0.0
        if not is_marine:
            expected_source = max(0.0, float(cell.get("infiltration_mm_y", 0.0)))
            lithology = str(cell.get("lithology", "unknown"))
            landform = str(cell.get("landform", "unknown"))
            permeability = GROUNDWATER_LITHOLOGY_PERMEABILITY.get(
                lithology, 0.34
            )
            if landform in {"rift_valley", "glacial_valley"}:
                permeability += 0.10
            if landform in GROUNDWATER_ALLUVIAL_LANDFORMS:
                permeability += 0.08
            permeability = max(0.0, min(1.0, permeability))
            drainage = max(
                0.0, min(1.0, float(cell.get("soil_drainage_index", 0.0)))
            )
            sediment = max(
                0.0,
                min(1.0, float(cell.get("sediment_thickness_m", 0.0)) / 3.0),
            )
            salinity = max(
                0.0, min(1.0, float(cell.get("soil_salinity_index", 0.0)))
            )
            ice = max(
                0.0,
                min(1.0, float(cell.get("ice_thickness_m", 0.0)) / 1600.0),
            )
            aridity = max(
                0.0, min(1.0, float(cell.get("seasonal_aridity_index", 0.0)))
            )
            expected_fraction = max(
                GROUNDWATER_MIN_RECHARGE_FRACTION,
                min(
                    GROUNDWATER_MAX_RECHARGE_FRACTION,
                    0.08
                    + permeability * 0.45
                    + drainage * 0.18
                    + sediment * 0.12
                    + (0.04 if water_body == "fresh_lake" else 0.0)
                    - salinity * 0.10
                    - ice * 0.12
                    - aridity * 0.06,
                ),
            )
        expected_recharge = expected_source * expected_fraction
        expected_vadose = expected_source - expected_recharge
        expected_residual = (
            expected_source - expected_recharge - expected_vadose
        )
        expected_recharge_km3 = expected_recharge * area * 1.0e-6
        expected_vadose_km3 = expected_vadose * area * 1.0e-6
        if strict and not all(_rounded_close(actual, target, digits) for actual, target, digits in (
            (source,expected_source,6),(fraction,expected_fraction,6),(recharge,expected_recharge,6),
            (vadose,expected_vadose,6),(residual,expected_residual,10),
            (recharge_km3,expected_recharge_km3,6),(vadose_km3,expected_vadose_km3,6),
        )):
            return failure
        if (
            source < 0.0
            or recharge < 0.0
            or vadose < 0.0
            or recharge > source + 0.001
            or abs(source - expected_source) > 0.001
            or abs(fraction - expected_fraction) > 0.001
            or abs(recharge - expected_recharge) > 0.001
            or abs(vadose - expected_vadose) > 0.001
            or abs(residual - expected_residual) > 1.0e-8
            or abs(recharge_km3 - expected_recharge_km3)
            > max(0.001, expected_recharge_km3 * 0.0001)
            or abs(vadose_km3 - expected_vadose_km3)
            > max(0.001, expected_vadose_km3 * 0.0001)
        ):
            return failure
        if not is_marine:
            source_volume += expected_source * area * 1.0e-6
            recharge_volume += expected_recharge_km3
            vadose_volume += expected_vadose_km3
            residual_volume += expected_residual * area * 1.0e-6

    expected_model = {
        "total_source_infiltration_volume_km3_y": source_volume,
        "total_groundwater_recharge_volume_km3_y": recharge_volume,
        "total_vadose_zone_retention_volume_km3_y": vadose_volume,
        "mass_balance_residual_km3_y": residual_volume,
    }
    if strict and any(not _rounded_close(model.get(key), value, 12 if key == "mass_balance_residual_km3_y" else 9)
                      for key,value in expected_model.items()):
        return failure
    if any(
        abs(float(model.get(key, math.inf)) - expected)
        > max(0.001, abs(expected) * 0.0001)
        for key, expected in expected_model.items()
    ):
        return failure
    expected_summary = {
        "total_groundwater_recharge_source_infiltration_km3_y": source_volume,
        "total_groundwater_recharge_km3_y": recharge_volume,
        "total_vadose_zone_retention_km3_y": vadose_volume,
        "groundwater_recharge_mass_balance_residual_km3_y": residual_volume,
    }
    if strict and any(not _rounded_close(summary.get(key), value, 9 if key == "groundwater_recharge_mass_balance_residual_km3_y" else 6)
                      for key,value in expected_summary.items()):
        return failure
    if any(
        abs(float(summary.get(key, math.inf)) - expected)
        > max(0.001, abs(expected) * 0.0001)
        for key, expected in expected_summary.items()
    ):
        return failure
    if not strict and abs(
        source_volume - float(summary.get("total_infiltration_km3_y", math.inf))
    ) > max(0.001, source_volume * 0.0001):
        return failure
    return []


def _validate_aquifer_resources(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
    *, strict: bool = False,
) -> list[str]:
    """Replay aquifer properties, classification, and basin grouping."""

    failure = ["aquifer resource model or causal replay invalid"]
    model = payload.get("aquifer_resource_model", {})
    systems = payload.get("aquifer_systems", [])
    try:
        metadata_invalid = (
            not isinstance(model, dict)
            or not isinstance(systems, list)
            or model.get("model_type") != AQUIFER_RESOURCE_MODEL
            or model.get("source_recharge_model")
            != GROUNDWATER_RECHARGE_MODEL
            or model.get("domain") != "non_marine_cells"
            or model.get("permeability_model")
            != "lithology_with_rift_glacial_and_alluvial_landform_adjustments_v1"
            or model.get("storage_model")
            != "permeability_sediment_moisture_alluvium_lake_aridity_ice_v1"
            or model.get("quality_model")
            != "recharge_limestone_salinity_closed_basin_aridity_v1"
            or model.get("extraction_risk_model")
            != "aridity_settlement_low_recharge_salinity_ice_closed_basin_v1"
            or model.get("productivity_model")
            != "storage_recharge_quality_flow_extraction_risk_v1"
            or model.get("classification_model")
            != "quality_salinity_productivity_storage_recharge_thresholds_v1"
            or model.get("system_grouping_model")
            != "basin_id_over_productivity_or_recharge_eligible_cells_v1"
            or model.get("marine_cell_treatment")
            != "zero_properties_marine_excluded_class_and_no_system"
            or model.get("deterministic") is not True
            or model.get("model_limitation")
            != "diagnostic_annual_resource_properties_without_transient_saturated_flow_storage_drawdown_or_geochemistry"
            or summary.get("aquifer_resource_model")
            != AQUIFER_RESOURCE_MODEL
            or abs(
                float(model.get("minimum_system_productivity_index", -1.0))
                - AQUIFER_MIN_SYSTEM_PRODUCTIVITY_INDEX
            )
            > 1.0e-12
            or abs(
                float(model.get("minimum_system_recharge_mm_y", -1.0))
                - AQUIFER_MIN_SYSTEM_RECHARGE_MM_Y
            )
            > 1.0e-12
        )
    except (TypeError, ValueError):
        return failure
    if metadata_invalid:
        return failure

    marine_types = {"ocean", "continental_shelf", "inland_sea"}

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def primary_key(counter: Counter[str], fallback: str) -> str:
        if not counter:
            return fallback
        return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[
            0
        ][0]

    def aquifer_class(
        productivity: float,
        storage: float,
        quality: float,
        recharge_mm_y: float,
        salinity: float,
    ) -> str:
        if quality < 0.34 or salinity >= 0.58:
            return "brackish_or_saline_aquifer"
        if productivity >= 0.66 and quality >= 0.55:
            return "major_fresh_aquifer"
        if storage >= 0.54 and recharge_mm_y < 65.0:
            return "fossil_or_slow_recharge_aquifer"
        if productivity >= 0.38:
            return "local_fresh_aquifer"
        if recharge_mm_y >= 80.0:
            return "perched_recharge_zone"
        return "poor_aquifer"

    expected_by_id: dict[int, dict[str, Any]] = {}
    basin_groups: dict[int, list[int]] = {}
    class_counts: Counter[str] = Counter()
    aquifer_cell_count = 0
    recharge_cell_count = 0
    high_productivity_count = 0
    stressed_cell_count = 0
    recharge_sum_mm = 0.0
    recharge_sum_km3 = 0.0
    storage_sum = 0.0
    quality_sum = 0.0
    productivity_sum = 0.0
    risk_sum = 0.0

    for cell_id, cell in cells_by_id.items():
        try:
            water_body = str(cell.get("water_body_type", "land"))
            lithology = str(cell.get("lithology", "unknown"))
            landform = str(cell.get("landform", "unknown"))
            area = max(0.0, float(cell.get("area_km2", 0.0)))
            marine_excluded = water_body in marine_types
            if marine_excluded:
                recharge_mm = 0.0
                recharge_km3 = 0.0
                storage = 0.0
                quality = 0.0
                productivity = 0.0
                extraction_risk = 0.0
                expected_class = "marine_excluded"
            else:
                permeability = GROUNDWATER_LITHOLOGY_PERMEABILITY.get(
                    lithology, 0.34
                )
                if landform in {"rift_valley", "glacial_valley"}:
                    permeability += 0.10
                if landform in GROUNDWATER_ALLUVIAL_LANDFORMS:
                    permeability += 0.08
                permeability = clamp(permeability)
                sediment = clamp(
                    float(cell.get("sediment_thickness_m", 0.0)) / 3.0
                )
                drainage = clamp(float(cell.get("soil_drainage_index", 0.0)))
                moisture = clamp(float(cell.get("soil_moisture_index", 0.0)))
                salinity = clamp(float(cell.get("soil_salinity_index", 0.0)))
                aridity = clamp(
                    float(cell.get("seasonal_aridity_index", 0.0))
                )
                ice = clamp(float(cell.get("ice_thickness_m", 0.0)) / 1600.0)
                flow = clamp(
                    float(cell.get("flow_accumulation", 0.0)) / 40_000_000.0
                )
                settlement = clamp(float(cell.get("settlement_score", 0.0)))
                closed_basin = bool(cell.get("is_closed_basin", False))
                source = max(0.0, float(cell.get("infiltration_mm_y", 0.0)))
                recharge_fraction = clamp(
                    0.08
                    + permeability * 0.45
                    + drainage * 0.18
                    + sediment * 0.12
                    + (0.04 if water_body == "fresh_lake" else 0.0)
                    - salinity * 0.10
                    - ice * 0.12
                    - aridity * 0.06,
                    GROUNDWATER_MIN_RECHARGE_FRACTION,
                    GROUNDWATER_MAX_RECHARGE_FRACTION,
                )
                recharge_mm = source * recharge_fraction
                recharge_km3 = recharge_mm * area * 1.0e-6
                alluvial_bonus = (
                    0.15 if landform in GROUNDWATER_ALLUVIAL_LANDFORMS else 0.0
                )
                fresh_lake_bonus = 0.16 if water_body == "fresh_lake" else 0.0
                storage = clamp(
                    0.08
                    + permeability * 0.34
                    + sediment * 0.26
                    + moisture * 0.12
                    + alluvial_bonus
                    + fresh_lake_bonus * 0.7
                    - aridity * 0.10
                    - ice * 0.12
                )
                quality = clamp(
                    0.80
                    + clamp(recharge_mm / 360.0) * 0.16
                    + (0.05 if lithology == "limestone" else 0.0)
                    - salinity * 0.50
                    - (0.18 if closed_basin else 0.0)
                    - (0.18 if water_body == "saline_basin" else 0.0)
                    - aridity * 0.08
                )
                extraction_risk = clamp(
                    0.14
                    + aridity * 0.30
                    + settlement * 0.18
                    + (1.0 - clamp(recharge_mm / 240.0)) * 0.20
                    + salinity * 0.18
                    + ice * 0.10
                    + (0.08 if closed_basin else 0.0)
                )
                productivity = clamp(
                    storage * 0.38
                    + clamp(recharge_mm / 320.0) * 0.34
                    + quality * 0.18
                    + flow * 0.08
                    - extraction_risk * 0.16
                )
                expected_class = aquifer_class(
                    productivity,
                    storage,
                    quality,
                    recharge_mm,
                    salinity,
                )
        except (TypeError, ValueError):
            return failure

        expected = {
            "recharge_mm": round(recharge_mm, 6),
            "recharge_km3": round(recharge_km3, 6),
            "storage": round(storage, 6),
            "quality": round(quality, 6),
            "productivity": round(productivity, 6),
            "risk": round(extraction_risk, 6),
            "class": expected_class,
            "system_id": -1,
        }
        expected_by_id[cell_id] = expected
        class_counts[expected_class] += 1
        try:
            actual_values = (
                float(cell.get("aquifer_storage_index", math.inf)),
                float(cell.get("aquifer_quality_index", math.inf)),
                float(cell.get("aquifer_productivity_index", math.inf)),
                float(cell.get("aquifer_extraction_risk_index", math.inf)),
            )
        except (TypeError, ValueError):
            return failure
        expected_values = (
            expected["storage"],
            expected["quality"],
            expected["productivity"],
            expected["risk"],
        )
        if (
            any(
                abs(actual - target) > 1.0e-9
                for actual, target in zip(actual_values, expected_values)
            )
            or str(cell.get("aquifer_class", "")) != expected_class
        ):
            return failure

        if not marine_excluded:
            aquifer_cell_count += 1
            recharge_sum_mm += recharge_mm
            recharge_sum_km3 += recharge_km3
            storage_sum += storage
            quality_sum += quality
            productivity_sum += productivity
            risk_sum += extraction_risk
            recharge_cell_count += int(recharge_mm >= 50.0)
            high_productivity_count += int(productivity >= 0.65)
            stressed_cell_count += int(extraction_risk >= 0.65)
            if (
                productivity >= AQUIFER_MIN_SYSTEM_PRODUCTIVITY_INDEX
                or recharge_mm >= AQUIFER_MIN_SYSTEM_RECHARGE_MM_Y
            ):
                basin_id = int(cell.get("basin_id", -1))
                basin_groups.setdefault(basin_id, []).append(cell_id)

    expected_systems: list[dict[str, Any]] = []
    for basin_id, group_ids in sorted(basin_groups.items()):
        system_id = len(expected_systems)
        group_cells = [cells_by_id[cell_id] for cell_id in group_ids]
        for cell_id in group_ids:
            expected_by_id[cell_id]["system_id"] = system_id
        group_count = len(group_ids)
        class_counter = Counter(
            str(expected_by_id[cell_id]["class"]) for cell_id in group_ids
        )
        lithology_counter = Counter(
            str(cell.get("lithology", "unknown")) for cell in group_cells
        )
        landform_counter = Counter(
            str(cell.get("landform", "unknown")) for cell in group_cells
        )
        expected_systems.append(
            {
                "id": system_id,
                "basin_id": basin_id,
                "aquifer_class": primary_key(class_counter, "poor_aquifer"),
                "primary_lithology": primary_key(
                    lithology_counter, "unknown"
                ),
                "dominant_landform": primary_key(
                    landform_counter, "unknown"
                ),
                "cell_count": group_count,
                "cell_ids": group_ids,
                "area_km2": round(
                    sum(
                        max(0.0, float(cell.get("area_km2", 0.0)))
                        for cell in group_cells
                    ),
                    6,
                ),
                "mean_groundwater_recharge_mm_y": round(
                    sum(expected_by_id[cell_id]["recharge_mm"] for cell_id in group_ids)
                    / group_count,
                    6,
                ),
                "total_groundwater_recharge_km3_y": round(
                    sum(expected_by_id[cell_id]["recharge_km3"] for cell_id in group_ids),
                    6,
                ),
                "mean_aquifer_storage_index": round(
                    sum(expected_by_id[cell_id]["storage"] for cell_id in group_ids)
                    / group_count,
                    6,
                ),
                "mean_aquifer_quality_index": round(
                    sum(expected_by_id[cell_id]["quality"] for cell_id in group_ids)
                    / group_count,
                    6,
                ),
                "mean_aquifer_productivity_index": round(
                    sum(expected_by_id[cell_id]["productivity"] for cell_id in group_ids)
                    / group_count,
                    6,
                ),
                "mean_aquifer_extraction_risk_index": round(
                    sum(expected_by_id[cell_id]["risk"] for cell_id in group_ids)
                    / group_count,
                    6,
                ),
                "recharge_cell_count": sum(
                    expected_by_id[cell_id]["recharge_mm"] >= 50.0
                    for cell_id in group_ids
                ),
                "high_productivity_cell_count": sum(
                    expected_by_id[cell_id]["productivity"] >= 0.65
                    for cell_id in group_ids
                ),
                "stressed_cell_count": sum(
                    expected_by_id[cell_id]["risk"] >= 0.65
                    for cell_id in group_ids
                ),
                "closed_basin_fraction": round(
                    sum(
                        bool(cell.get("is_closed_basin", False))
                        for cell in group_cells
                    )
                    / group_count,
                    6,
                ),
                "aquifer_class_counts": dict(sorted(class_counter.items())),
            }
        )

    for cell_id, expected in expected_by_id.items():
        try:
            if int(cells_by_id[cell_id].get("aquifer_system_id", -2)) != int(
                expected["system_id"]
            ):
                return failure
        except (TypeError, ValueError):
            return failure

    if len(systems) != len(expected_systems):
        return failure
    for actual, expected in zip(systems, expected_systems):
        if strict and not _same(actual, expected):
            return failure
        if not isinstance(actual, dict) or any(
            actual.get(key) != value for key, value in expected.items()
        ):
            return failure

    expected_model_counts = {
        "aquifer_cell_count": aquifer_cell_count,
        "system_eligible_cell_count": sum(map(len, basin_groups.values())),
        "aquifer_system_count": len(expected_systems),
    }
    if any(
        int(model.get(key, -1)) != expected
        for key, expected in expected_model_counts.items()
    ):
        return failure

    divisor = aquifer_cell_count if aquifer_cell_count else 1
    expected_summary = {
        "aquifer_resource_model": AQUIFER_RESOURCE_MODEL,
        "aquifer_cell_count": aquifer_cell_count,
        "aquifer_system_count": len(expected_systems),
        "groundwater_recharge_cell_count": recharge_cell_count,
        "high_productivity_aquifer_cell_count": high_productivity_count,
        "groundwater_stressed_cell_count": stressed_cell_count,
        "total_groundwater_recharge_km3_y": round(recharge_sum_km3, 6),
        "mean_groundwater_recharge_mm_y": (
            round(recharge_sum_mm / divisor, 6) if aquifer_cell_count else 0.0
        ),
        "mean_aquifer_storage_index": (
            round(storage_sum / divisor, 6) if aquifer_cell_count else 0.0
        ),
        "mean_aquifer_quality_index": (
            round(quality_sum / divisor, 6) if aquifer_cell_count else 0.0
        ),
        "mean_aquifer_productivity_index": (
            round(productivity_sum / divisor, 6) if aquifer_cell_count else 0.0
        ),
        "mean_aquifer_extraction_risk_index": (
            round(risk_sum / divisor, 6) if aquifer_cell_count else 0.0
        ),
        "aquifer_class_counts": dict(sorted(class_counts.items())),
    }
    if any(summary.get(key) != value for key, value in expected_summary.items()):
        return failure
    return []


def _validate_groundwater_flow(
    payload: dict[str, Any],
    summary: dict[str, Any],
    cells_by_id: dict[int, dict[str, Any]],
    *, natural: bool = False,
) -> list[str]:
    """Replay deterministic head routing and every local recharge-volume split."""

    failure = ["groundwater flow model or routing replay invalid"]
    model = payload.get("groundwater_flow_model", {})
    if (
        not isinstance(model, dict)
        or model.get("model_type") != GROUNDWATER_FLOW_MODEL
        or model.get("source_field") != "groundwater_recharge_km3_y"
        or model.get("domain") != "non_marine_aquifer_cells"
        or model.get("hydraulic_head_model")
        != "terrain_minus_diagnostic_depth_to_water_v1"
        or model.get("receiver_model")
        != "steepest_head_drop_within_aquifer_system_or_surface_sink_v1"
        or model.get("routing_order")
        != "descending_hydraulic_head_then_cell_id"
        or model.get("lateral_export_model")
        != "bounded_gradient_productivity_storage_extraction_fraction_v1"
        or model.get("surface_discharge_model")
        != "surface_target_export_plus_fraction_of_remaining_volume_v1"
        or model.get("local_mass_balance_equation")
        != "recharge_plus_lateral_inflow_minus_internal_lateral_outflow_minus_discharge_minus_retained_storage"
        or not bool(model.get("mass_conserving", False))
        or not bool(model.get("acyclic_flow_required", False))
        or model.get("model_limitation")
        != "annual_diagnostic_head_and_flux_routing_without_transient_aquifer_storage_or_groundwater_surface_water_feedback"
        or summary.get("groundwater_flow_model") != GROUNDWATER_FLOW_MODEL
        or abs(
            float(model.get("minimum_receiver_head_drop_m", -1.0))
            - GROUNDWATER_FLOW_MINIMUM_RECEIVER_HEAD_DROP_M
        )
        > 1.0e-12
        or abs(
            float(model.get("gradient_scale_m", -1.0))
            - GROUNDWATER_FLOW_GRADIENT_SCALE_M
        )
        > 1.0e-12
        or abs(
            float(model.get("maximum_lateral_export_fraction", -1.0))
            - GROUNDWATER_FLOW_MAXIMUM_LATERAL_EXPORT_FRACTION
        )
        > 1.0e-12
    ):
        return failure

    marine_types = {"ocean", "continental_shelf", "inland_sea"}
    surface_water_types = {"fresh_lake"} if natural else {"fresh_lake", "saline_basin"}
    flow_regimes = {
        "excluded",
        "recharge_mound",
        "recharge_throughflow",
        "throughflow",
        "discharge_zone",
        "lowland_discharge",
        "stagnant_or_low_yield",
    }

    def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def is_candidate(cell: dict[str, Any]) -> bool:
        return (
            str(cell.get("aquifer_class", "")) != "marine_excluded"
            and str(cell.get("water_body_type", "land")) not in marine_types
        )

    candidate_ids = {
        cell_id for cell_id, cell in cells_by_id.items() if is_candidate(cell)
    }
    if int(model.get("candidate_cell_count", -1)) != len(candidate_ids):
        return failure

    def water_surface_head(cell: dict[str, Any]) -> float:
        elevation = float(cell.get("elevation_m", 0.0))
        if bool(cell.get("is_water", False)):
            return elevation + max(0.0, float(cell.get("water_depth_m", 0.0)))
        return elevation

    def hydraulic_head(cell: dict[str, Any]) -> float:
        if not is_candidate(cell):
            return water_surface_head(cell)
        elevation = float(cell.get("elevation_m", 0.0))
        recharge = clamp(float(cell.get("groundwater_recharge_mm_y", 0.0)) / 360.0)
        storage = clamp(float(cell.get("aquifer_storage_index", 0.0)))
        quality = clamp(float(cell.get("aquifer_quality_index", 0.0)))
        moisture = clamp(float(cell.get("soil_moisture_index", 0.0)))
        aridity = clamp(float(cell.get("seasonal_aridity_index", 0.0)))
        salinity = clamp(float(cell.get("soil_salinity_index", 0.0)))
        extraction_risk = clamp(
            float(cell.get("aquifer_extraction_risk_index", 0.0))
        )
        water_bonus = (
            0.18
            if (natural and bool(cell.get("is_water", False)))
            or bool(cell.get("is_lake", False))
            or str(cell.get("water_body_type", "land")) in surface_water_types
            else 0.0
        )
        river_bonus = 0.10 if bool(cell.get("is_river", False)) else 0.0
        saturation = clamp(
            recharge * 0.28
            + storage * 0.26
            + quality * 0.10
            + moisture * 0.18
            + water_bonus
            + river_bonus
            - aridity * 0.12
            - salinity * 0.08
            - extraction_risk * 0.08
        )
        depth_to_water = max(
            0.0,
            12.0
            + (1.0 - saturation) * 210.0
            + aridity * 70.0
            + extraction_risk * 45.0
            - storage * 35.0,
        )
        return elevation - depth_to_water

    heads = {
        cell_id: hydraulic_head(cell) for cell_id, cell in cells_by_id.items()
    }
    flow_to_by_id: dict[int, int] = {}
    gradient_by_id: dict[int, float] = {}
    for cell_id in sorted(candidate_ids):
        cell = cells_by_id[cell_id]
        head = heads[cell_id]
        aquifer_system_id = int(cell.get("aquifer_system_id", -1))
        best_neighbor_id = -1
        best_drop = 0.0
        neighbors = cell.get("neighbors", [])
        if not isinstance(neighbors, list):
            return failure
        for raw_neighbor_id in neighbors:
            neighbor_id = int(raw_neighbor_id)
            neighbor = cells_by_id.get(neighbor_id)
            if neighbor is None:
                return failure
            same_system = (
                neighbor_id in candidate_ids
                and int(neighbor.get("aquifer_system_id", -2))
                == aquifer_system_id
            )
            surface_sink = neighbor_id not in candidate_ids
            if not same_system and not surface_sink:
                continue
            drop = head - heads[neighbor_id]
            if natural:
                _require(_finite(drop), "unrepresentable independently replayed head difference")
            if drop > best_drop:
                best_drop = drop
                best_neighbor_id = neighbor_id
        if best_drop >= GROUNDWATER_FLOW_MINIMUM_RECEIVER_HEAD_DROP_M:
            flow_to_by_id[cell_id] = best_neighbor_id
            gradient_by_id[cell_id] = clamp(
                best_drop / GROUNDWATER_FLOW_GRADIENT_SCALE_M
            )
        else:
            flow_to_by_id[cell_id] = -1
            gradient_by_id[cell_id] = 0.0

    available_by_id = {
        cell_id: max(
            0.0,
            float(cells_by_id[cell_id].get("groundwater_recharge_km3_y", 0.0)),
        )
        for cell_id in candidate_ids
    }
    lateral_inflow_by_id = {cell_id: 0.0 for cell_id in candidate_ids}
    lateral_export_by_id = {cell_id: 0.0 for cell_id in candidate_ids}
    internal_outflow_by_id = {cell_id: 0.0 for cell_id in candidate_ids}
    processed_available_by_id: dict[int, float] = {}
    for cell_id in sorted(candidate_ids, key=lambda item: (-heads[item], item)):
        cell = cells_by_id[cell_id]
        available = max(0.0, available_by_id[cell_id])
        processed_available_by_id[cell_id] = available
        gradient = gradient_by_id[cell_id]
        storage = clamp(float(cell.get("aquifer_storage_index", 0.0)))
        productivity = clamp(float(cell.get("aquifer_productivity_index", 0.0)))
        extraction_risk = clamp(
            float(cell.get("aquifer_extraction_risk_index", 0.0))
        )
        export_fraction = clamp(
            0.12
            + gradient * 0.56
            + productivity * 0.18
            + storage * 0.08
            - extraction_risk * 0.12,
            0.0,
            GROUNDWATER_FLOW_MAXIMUM_LATERAL_EXPORT_FRACTION,
        )
        flow_to = flow_to_by_id[cell_id]
        export = available * export_fraction if flow_to >= 0 else 0.0
        lateral_export_by_id[cell_id] = export
        if flow_to in candidate_ids:
            available_by_id[flow_to] += export
            lateral_inflow_by_id[flow_to] += export
            internal_outflow_by_id[cell_id] = export

    def surface_connection(cell: dict[str, Any]) -> float:
        water_body = str(cell.get("water_body_type", "land"))
        connection = 0.0
        if bool(cell.get("is_river", False)):
            connection = max(connection, 0.62)
        if (natural and bool(cell.get("is_water", False))) or bool(cell.get("is_lake", False)) or water_body in surface_water_types:
            connection = max(connection, 0.56)
        if float(cell.get("wetland_extent_index", 0.0)) >= 0.35:
            connection = max(connection, 0.42)
        if bool(cell.get("is_closed_basin", False)):
            connection = max(connection, 0.24)
        if cell.get("marine_distance_status") != "no_marine_source" and float(cell.get("distance_to_marine_water_km", 9999.0)) <= 160.0:
            connection = max(connection, 0.28)
        return clamp(connection)

    def flow_regime(
        cell: dict[str, Any],
        gradient: float,
        discharge_mm_y: float,
        spring_index: float,
        flow_to: int,
    ) -> str:
        if not is_candidate(cell):
            return "excluded"
        recharge = float(cell.get("groundwater_recharge_mm_y", 0.0))
        if spring_index >= 0.45 and discharge_mm_y >= 20.0:
            return "discharge_zone"
        if recharge >= 60.0 and gradient >= 0.08 and flow_to >= 0:
            return "recharge_throughflow"
        if recharge >= 60.0:
            return "recharge_mound"
        if gradient >= 0.05 and flow_to >= 0:
            return "throughflow"
        if discharge_mm_y >= 12.0:
            return "lowland_discharge"
        return "stagnant_or_low_yield"

    expected_by_id: dict[int, dict[str, float | int | str]] = {}
    for cell_id, cell in cells_by_id.items():
        if cell_id not in candidate_ids:
            expected_by_id[cell_id] = {
                "head": heads[cell_id],
                "gradient": 0.0,
                "lateral_export": 0.0,
                "lateral_inflow": 0.0,
                "available": 0.0,
                "internal_outflow": 0.0,
                "discharge_mm": 0.0,
                "discharge_km3": 0.0,
                "retained": 0.0,
                "residual": 0.0,
                "flow_to": -1,
                "spring": 0.0,
                "baseflow": 0.0,
                "regime": "excluded",
            }
            continue
        area = max(0.0, float(cell.get("area_km2", 0.0)))
        if area <= 0.0:
            return failure
        available = processed_available_by_id[cell_id]
        export = lateral_export_by_id[cell_id]
        internal_outflow = internal_outflow_by_id[cell_id]
        flow_to = flow_to_by_id[cell_id]
        flow_to_candidate = flow_to in candidate_ids
        gradient = gradient_by_id[cell_id]
        productivity = clamp(float(cell.get("aquifer_productivity_index", 0.0)))
        storage = clamp(float(cell.get("aquifer_storage_index", 0.0)))
        quality = clamp(float(cell.get("aquifer_quality_index", 0.0)))
        extraction_risk = clamp(
            float(cell.get("aquifer_extraction_risk_index", 0.0))
        )
        connection = surface_connection(cell)
        local_available = max(
            0.0,
            available - (export if flow_to >= 0 else 0.0),
        )
        surface_fraction = clamp(
            connection * 0.58
            + (1.0 - gradient) * 0.10
            + productivity * 0.08
            - extraction_risk * 0.12
        )
        if flow_to >= 0 and not flow_to_candidate:
            discharge_km3 = min(
                available,
                export + local_available * surface_fraction,
            )
        else:
            discharge_km3 = min(available, local_available * surface_fraction)
        discharge_mm = discharge_km3 / (area * 1.0e-6)
        spring = clamp(
            discharge_mm / 260.0 * 0.42
            + gradient * 0.20
            + connection * 0.18
            + productivity * 0.12
            + quality * 0.08
        )
        baseflow = clamp(
            discharge_mm / 260.0 * 0.42
            + float(cell.get("groundwater_recharge_mm_y", 0.0))
            / 340.0
            * 0.16
            + storage * 0.16
            + productivity * 0.16
            + (0.12 if bool(cell.get("is_river", False)) else 0.0)
            - extraction_risk * 0.10
        )
        retained = max(
            0.0,
            available - internal_outflow - discharge_km3,
        )
        residual = available - internal_outflow - discharge_km3 - retained
        expected_by_id[cell_id] = {
            "head": heads[cell_id],
            "gradient": gradient,
            "lateral_export": export,
            "lateral_inflow": lateral_inflow_by_id[cell_id],
            "available": available,
            "internal_outflow": internal_outflow,
            "discharge_mm": discharge_mm,
            "discharge_km3": discharge_km3,
            "retained": retained,
            "residual": residual,
            "flow_to": flow_to,
            "spring": spring,
            "baseflow": baseflow,
            "regime": flow_regime(
                cell,
                gradient,
                discharge_mm,
                spring,
                flow_to,
            ),
        }

    field_map = {
        "groundwater_hydraulic_head_m": ("head", 6),
        "groundwater_gradient_index": ("gradient", 6),
        "groundwater_lateral_flow_km3_y": ("lateral_export", 6),
        "groundwater_lateral_inflow_km3_y": ("lateral_inflow", 6),
        "groundwater_available_volume_km3_y": ("available", 6),
        "groundwater_internal_lateral_outflow_km3_y": (
            "internal_outflow",
            6,
        ),
        "groundwater_discharge_mm_y": ("discharge_mm", 6),
        "groundwater_discharge_km3_y": ("discharge_km3", 6),
        "groundwater_retained_storage_km3_y": ("retained", 6),
        "groundwater_flow_mass_balance_residual_km3_y": ("residual", 12),
        "spring_discharge_index": ("spring", 6),
        "baseflow_support_index": ("baseflow", 6),
    }
    for cell_id, cell in cells_by_id.items():
        expected = expected_by_id[cell_id]
        try:
            for field, (expected_key, digits) in field_map.items():
                actual = float(cell.get(field, math.inf))
                target = round(float(expected[expected_key]), digits)
                if natural and not _rounded_close(actual, float(expected[expected_key]), digits):
                    return failure
                tolerance = 2.0e-10 if digits == 12 else 2.0e-6
                if abs(actual - target) > tolerance:
                    return failure
            if (
                int(cell.get("groundwater_flow_to_cell_id", -2))
                != int(expected["flow_to"])
                or str(cell.get("groundwater_flow_regime", ""))
                != str(expected["regime"])
                or str(expected["regime"]) not in flow_regimes
            ):
                return failure
        except (TypeError, ValueError):
            return failure

        if cell_id in candidate_ids:
            recharge = float(cell.get("groundwater_recharge_km3_y", 0.0))
            inflow = float(cell.get("groundwater_lateral_inflow_km3_y", 0.0))
            available = float(cell.get("groundwater_available_volume_km3_y", 0.0))
            internal_outflow = float(
                cell.get("groundwater_internal_lateral_outflow_km3_y", 0.0)
            )
            discharge = float(cell.get("groundwater_discharge_km3_y", 0.0))
            retained = float(cell.get("groundwater_retained_storage_km3_y", 0.0))
            residual = float(
                cell.get("groundwater_flow_mass_balance_residual_km3_y", 0.0)
            )
            if (
                abs(available - recharge - inflow) > 3.0e-6
                or abs(
                    available
                    - internal_outflow
                    - discharge
                    - retained
                    - residual
                )
                > 4.0e-6
            ):
                return failure

    def raw_sum(key: str) -> float:
        return sum(
            float(expected_by_id[cell_id][key])
            for cell_id in candidate_ids
        )

    expected_model = {
        "total_source_recharge_volume_km3_y": sum(
            float(cells_by_id[cell_id].get("groundwater_recharge_km3_y", 0.0))
            for cell_id in candidate_ids
        ),
        "total_internal_lateral_inflow_volume_km3_y": raw_sum(
            "lateral_inflow"
        ),
        "total_internal_lateral_outflow_volume_km3_y": raw_sum(
            "internal_outflow"
        ),
        "total_lateral_throughput_volume_km3_y": raw_sum(
            "lateral_export"
        ),
        "total_groundwater_discharge_volume_km3_y": raw_sum(
            "discharge_km3"
        ),
        "total_retained_storage_volume_km3_y": raw_sum("retained"),
        "mass_balance_residual_km3_y": raw_sum("residual"),
    }
    for key, expected in expected_model.items():
        if natural and not _rounded_close(model.get(key), expected, 12 if key == "mass_balance_residual_km3_y" else 9):
            return failure
        tolerance = 1.0e-8 if key == "mass_balance_residual_km3_y" else 2.0e-5
        if abs(float(model.get(key, math.inf)) - expected) > tolerance:
            return failure
    if abs(
        expected_model["total_internal_lateral_inflow_volume_km3_y"]
        - expected_model["total_internal_lateral_outflow_volume_km3_y"]
    ) > 0.001:
        return failure
    if abs(
        expected_model["total_source_recharge_volume_km3_y"]
        - expected_model["total_groundwater_discharge_volume_km3_y"]
        - expected_model["total_retained_storage_volume_km3_y"]
    ) > 0.001:
        return failure

    expected_summary = {
        "total_groundwater_discharge_km3_y": expected_model[
            "total_groundwater_discharge_volume_km3_y"
        ],
        "total_groundwater_lateral_flow_km3_y": expected_model[
            "total_lateral_throughput_volume_km3_y"
        ],
        "total_groundwater_internal_lateral_flow_km3_y": expected_model[
            "total_internal_lateral_outflow_volume_km3_y"
        ],
        "total_groundwater_retained_storage_km3_y": expected_model[
            "total_retained_storage_volume_km3_y"
        ],
        "groundwater_flow_mass_balance_residual_km3_y": expected_model[
            "mass_balance_residual_km3_y"
        ],
    }
    for key, expected in expected_summary.items():
        if natural and not _rounded_close(summary.get(key), expected, 12 if key == "groundwater_flow_mass_balance_residual_km3_y" else 6):
            return failure
        tolerance = (
            1.0e-8
            if key == "groundwater_flow_mass_balance_residual_km3_y"
            else 0.00002
        )
        if abs(float(summary.get(key, math.inf)) - expected) > tolerance:
            return failure
    if abs(
        expected_model["total_source_recharge_volume_km3_y"]
        - float(
            payload.get("groundwater_recharge_model", {}).get(
                "total_groundwater_recharge_volume_km3_y",
                math.inf,
            )
        )
    ) > 0.001:
        return failure
    if natural:
        _validate_flow_records_and_means(payload, summary, cells_by_id)
    return []


_MODEL_DYNAMIC = {'aquifer_resource_model': {'aquifer_cell_count': 'count',
                            'system_eligible_cell_count': 'count',
                            'aquifer_system_count': 'count'},
 'groundwater_recharge_model': {'total_source_infiltration_volume_km3_y': 'number',
                                'total_groundwater_recharge_volume_km3_y': 'number',
                                'total_vadose_zone_retention_volume_km3_y': 'number',
                                'mass_balance_residual_km3_y': 'number'},
 'groundwater_flow_model': {'candidate_cell_count': 'count',
                            'total_source_recharge_volume_km3_y': 'number',
                            'total_internal_lateral_inflow_volume_km3_y': 'number',
                            'total_internal_lateral_outflow_volume_km3_y': 'number',
                            'total_lateral_throughput_volume_km3_y': 'number',
                            'total_groundwater_discharge_volume_km3_y': 'number',
                            'total_retained_storage_volume_km3_y': 'number',
                            'mass_balance_residual_km3_y': 'number'}}


_LEGACY_POLICIES = {'aquifer_resource_model': {'model_type': 'finite_recharge_causal_aquifer_resources_v1',
                            'source_recharge_model': 'infiltration_bounded_aquifer_recharge_v1',
                            'domain': 'non_marine_cells',
                            'permeability_model': 'lithology_with_rift_glacial_and_alluvial_landform_adjustments_v1',
                            'storage_model': 'permeability_sediment_moisture_alluvium_lake_aridity_ice_v1',
                            'quality_model': 'recharge_limestone_salinity_closed_basin_aridity_v1',
                            'extraction_risk_model': 'aridity_settlement_low_recharge_salinity_ice_closed_basin_v1',
                            'productivity_model': 'storage_recharge_quality_flow_extraction_risk_v1',
                            'classification_model': 'quality_salinity_productivity_storage_recharge_thresholds_v1',
                            'system_grouping_model': 'basin_id_over_productivity_or_recharge_eligible_cells_v1',
                            'minimum_system_productivity_index': 0.18,
                            'minimum_system_recharge_mm_y': 25.0,
                            'marine_cell_treatment': 'zero_properties_marine_excluded_class_and_no_system',
                            'deterministic': True,
                            'model_limitation': 'diagnostic_annual_resource_properties_without_transient_saturated_flow_storage_drawdown_or_geochemistry'},
 'groundwater_recharge_model': {'model_type': 'infiltration_bounded_aquifer_recharge_v1',
                                'source_field': 'infiltration_mm_y',
                                'domain': 'non_marine_cells',
                                'recharge_fraction_model': 'lithology_soil_drainage_sediment_lake_salinity_ice_aridity_v1',
                                'minimum_recharge_fraction': 0.05,
                                'maximum_recharge_fraction': 0.85,
                                'marine_cell_treatment': 'zero_source_recharge_and_vadose_retention',
                                'mass_conserving_source_partition': True,
                                'model_limitation': 'annual_diagnostic_partition_without_transient_vadose_storage_or_groundwater_return_flow'},
 'groundwater_flow_model': {'model_type': 'descending_head_recharge_conserving_groundwater_flow_v1',
                            'source_field': 'groundwater_recharge_km3_y',
                            'domain': 'non_marine_aquifer_cells',
                            'hydraulic_head_model': 'terrain_minus_diagnostic_depth_to_water_v1',
                            'receiver_model': 'steepest_head_drop_within_aquifer_system_or_surface_sink_v1',
                            'minimum_receiver_head_drop_m': 0.5,
                            'gradient_scale_m': 900.0,
                            'routing_order': 'descending_hydraulic_head_then_cell_id',
                            'lateral_export_model': 'bounded_gradient_productivity_storage_extraction_fraction_v1',
                            'maximum_lateral_export_fraction': 0.82,
                            'surface_discharge_model': 'surface_target_export_plus_fraction_of_remaining_volume_v1',
                            'local_mass_balance_equation': 'recharge_plus_lateral_inflow_minus_internal_lateral_outflow_minus_discharge_minus_retained_storage',
                            'mass_conserving': True,
                            'acyclic_flow_required': True,
                            'model_limitation': 'annual_diagnostic_head_and_flux_routing_without_transient_aquifer_storage_or_groundwater_surface_water_feedback'}}


_NATURAL_POLICIES = {'aquifer_resource_model': {'model_type': 'natural_recharge_causal_aquifer_resources_v2',
                            'source_recharge_model': 'infiltration_bounded_aquifer_recharge_v1',
                            'domain': 'non_marine_cells',
                            'permeability_model': 'lithology_with_rift_glacial_and_alluvial_landform_adjustments_v1',
                            'storage_model': 'permeability_sediment_moisture_alluvium_lake_aridity_ice_v1',
                            'quality_model': 'recharge_limestone_salinity_closed_basin_aridity_v1',
                            'productivity_model': 'storage_recharge_quality_flow_natural_limitation_v2',
                            'classification_model': 'quality_salinity_productivity_storage_recharge_thresholds_v1',
                            'system_grouping_model': 'basin_id_over_productivity_or_recharge_eligible_cells_v1',
                            'minimum_system_productivity_index': 0.18,
                            'minimum_system_recharge_mm_y': 25.0,
                            'marine_cell_treatment': 'zero_properties_marine_excluded_class_and_no_system',
                            'deterministic': True,
                            'model_limitation': 'heuristic_annual_natural_resource_properties_not_measured_storativity_conductivity_potability_or_sustainable_yield',
                            'natural_limitation_model': 'aridity_low_recharge_salinity_ice_closed_basin_v1',
                            'natural_limitation_field': 'aquifer_natural_limitation_index',
                            'natural_input_policy': 'independent_of_settlement_suitability_population_and_human_records',
                            'human_withdrawals_modelled': False,
                            'natural_limitation_count_policy': 'summary_raw_and_system_six_decimal_indices_greater_than_or_equal_0_65'},
 'groundwater_recharge_model': {'model_type': 'infiltration_bounded_aquifer_recharge_v1',
                                'source_field': 'infiltration_mm_y',
                                'domain': 'non_marine_cells',
                                'recharge_fraction_model': 'lithology_soil_drainage_sediment_lake_salinity_ice_aridity_v1',
                                'minimum_recharge_fraction': 0.05,
                                'maximum_recharge_fraction': 0.85,
                                'marine_cell_treatment': 'zero_source_recharge_and_vadose_retention',
                                'mass_conserving_source_partition': True,
                                'model_limitation': 'annual_diagnostic_partition_without_transient_vadose_storage_or_groundwater_return_flow'},
 'groundwater_flow_model': {'model_type': 'descending_head_natural_recharge_partition_v2',
                            'source_field': 'groundwater_recharge_km3_y',
                            'domain': 'non_marine_aquifer_cells',
                            'hydraulic_head_model': 'terrain_minus_natural_diagnostic_depth_to_water_v2',
                            'receiver_model': 'steepest_head_drop_within_aquifer_system_or_surface_sink_v1',
                            'minimum_receiver_head_drop_m': 0.5,
                            'gradient_scale_m': 900.0,
                            'routing_order': 'descending_hydraulic_head_then_cell_id',
                            'lateral_export_model': 'bounded_gradient_productivity_storage_natural_limitation_fraction_v2',
                            'maximum_lateral_export_fraction': 0.82,
                            'surface_discharge_model': 'surface_target_export_plus_natural_fraction_of_remaining_volume_v2',
                            'local_mass_balance_equation': 'recharge_plus_lateral_inflow_minus_internal_lateral_outflow_minus_discharge_minus_retained_storage',
                            'mass_conserving': True,
                            'acyclic_flow_required': True,
                            'model_limitation': 'heuristic_annual_natural_head_and_recharge_partition_without_pumping_transient_storage_or_groundwater_surface_water_feedback',
                            'source_aquifer_model': 'natural_recharge_causal_aquifer_resources_v2',
                            'natural_limitation_field': 'aquifer_natural_limitation_index',
                            'surface_water_selector': 'is_water_or_is_lake_or_fresh_lake_water_body_type',
                            'natural_input_policy': 'independent_of_settlement_suitability_population_and_human_records',
                            'human_withdrawals_modelled': False,
                            'transient_storage_modelled': False,
                            'darcy_flow_modelled': False,
                            'retained_storage_semantics': 'unadvanced_annual_recharge_partition_remainder_not_stored_water_stock'}}


_OWNED = {'aquifer': {'cell': ['aquifer_class',
                      'aquifer_extraction_risk_index',
                      'aquifer_productivity_index',
                      'aquifer_quality_index',
                      'aquifer_storage_index',
                      'aquifer_system_id',
                      'groundwater_recharge_fraction',
                      'groundwater_recharge_km3_y',
                      'groundwater_recharge_mass_balance_residual_mm_y',
                      'groundwater_recharge_mm_y',
                      'groundwater_recharge_source_infiltration_mm_y',
                      'vadose_zone_retention_km3_y',
                      'vadose_zone_retention_mm_y'],
             'world': ['aquifer_resource_model', 'aquifer_systems', 'groundwater_recharge_model'],
             'summary': ['aquifer_cell_count',
                         'aquifer_class_counts',
                         'aquifer_resource_model',
                         'aquifer_system_count',
                         'groundwater_recharge_cell_count',
                         'groundwater_recharge_mass_balance_residual_km3_y',
                         'groundwater_recharge_model',
                         'groundwater_stressed_cell_count',
                         'high_productivity_aquifer_cell_count',
                         'mean_aquifer_extraction_risk_index',
                         'mean_aquifer_productivity_index',
                         'mean_aquifer_quality_index',
                         'mean_aquifer_storage_index',
                         'mean_groundwater_recharge_mm_y',
                         'total_groundwater_recharge_km3_y',
                         'total_groundwater_recharge_source_infiltration_km3_y',
                         'total_vadose_zone_retention_km3_y']},
 'groundwater': {'cell': ['baseflow_support_index',
                          'groundwater_available_volume_km3_y',
                          'groundwater_discharge_km3_y',
                          'groundwater_discharge_mm_y',
                          'groundwater_flow_mass_balance_residual_km3_y',
                          'groundwater_flow_regime',
                          'groundwater_flow_system_id',
                          'groundwater_flow_to_cell_id',
                          'groundwater_gradient_index',
                          'groundwater_hydraulic_head_m',
                          'groundwater_internal_lateral_outflow_km3_y',
                          'groundwater_lateral_flow_km3_y',
                          'groundwater_lateral_inflow_km3_y',
                          'groundwater_retained_storage_km3_y',
                          'spring_discharge_index'],
                 'world': ['groundwater_flow_model', 'groundwater_flow_systems'],
                 'summary': ['baseflow_supported_river_cell_count',
                             'groundwater_discharge_cell_count',
                             'groundwater_flow_cell_count',
                             'groundwater_flow_mass_balance_residual_km3_y',
                             'groundwater_flow_model',
                             'groundwater_flow_regime_counts',
                             'groundwater_flow_system_count',
                             'mean_baseflow_support_index',
                             'mean_groundwater_discharge_mm_y',
                             'mean_groundwater_gradient_index',
                             'mean_spring_discharge_index',
                             'spring_candidate_cell_count',
                             'total_groundwater_discharge_km3_y',
                             'total_groundwater_flow_balance_residual_km3_y',
                             'total_groundwater_internal_lateral_flow_km3_y',
                             'total_groundwater_lateral_flow_km3_y',
                             'total_groundwater_retained_storage_km3_y']}}
