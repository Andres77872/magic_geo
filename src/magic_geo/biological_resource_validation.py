"""Independent, read-only historical/E5 and settlement-v3 resource contracts.

Old families retain their biological/source-link scope. Resource-v5 additionally
replays all raw material diagnostic indices needed by economic availability via
the independent resource-access helper. No measured reserve or yield claim is
made, and no resource/commodity producer functions or constants are imported.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from . import resource_access_validation as _access

from .aquatic_climate_validation import _EXPECTED_MODELS, validate_aquatic_climate_support


_PARENT = "heuristic_ecosystem_climate_support_v4"
_WATER = {"continental_shelf", "fresh_lake", "inland_sea", "ocean"}
_DEPOSIT_V2 = {
    "model_type": "causal_geologic_resource_deposit_diagnostics_v2",
    "flow_accumulation_normalization_model": "positive_cell_p95_v1",
    "flow_accumulation_units": "runoff_mm_y_times_upstream_area_km2",
    "physical_time_resolved": False,
    "model_limitation": "diagnostic formation evidence without geochemical transport or reserve-volume simulation",
}
_DEPOSIT_V3 = {
    **_DEPOSIT_V2,
    "model_type": "causal_geologic_resource_deposit_diagnostics_v3",
    "biological_resource_types": ["coastal_fisheries"],
    "source_ecosystem_model": _PARENT,
    "biological_parent_policy": "native_fishery_resource_requires_supported_primary_and_derived_fishery",
    "fishery_water_body_types": sorted(_WATER),
    "unsupported_biological_record_policy": "retain_native_resource_label_emit_no_deposit",
    "material_resource_policy": "preserve_nonfishery_diagnostics_independent_of_current_ecosystem_productivity",
    "renewability_scope": "static_resource_category_prior_not_observed_replenishment",
    "summary_support_scope": "emitted_record_means_with_unsupported_fishery_source_counts",
}
_COMMODITY_V1 = {
    "model_type": "causal_resource_commodity_occurrences_with_parent_support_v1",
    "source_resource_deposit_model": _DEPOSIT_V3["model_type"],
    "source_ecosystem_model": _PARENT,
    "fishery_parent_policy": "supported_matching_deposit_primary_and_derived_fishery_required",
    "unsupported_fishery_occurrence_policy": "no_record_not_observed_zero_biomass",
    "fertile_soils_scope": "soil_material_descriptor_not_current_crop_yield",
    "material_commodity_policy": "preserve_existing_nonfishery_equations_and_mapping",
    "summary_support_scope": "emitted_record_means_with_unsupported_fishery_source_counts",
}

_NATURAL_PARENT = "heuristic_ecosystem_climate_support_v5"
_DEPOSIT_V4 = {**_DEPOSIT_V3,
    "model_type": "causal_geologic_resource_deposit_diagnostics_v4",
    "source_ecosystem_model": _NATURAL_PARENT,
}
_COMMODITY_V2 = {**_COMMODITY_V1,
    "model_type": "causal_resource_commodity_occurrences_with_parent_support_v2",
    "source_resource_deposit_model": _DEPOSIT_V4["model_type"],
    "source_ecosystem_model": _NATURAL_PARENT,
}
_DEPOSIT_BY_PARENT = {_PARENT: _DEPOSIT_V3, _NATURAL_PARENT: _DEPOSIT_V4}
_COMMODITY_BY_PARENT = {_PARENT: _COMMODITY_V1, _NATURAL_PARENT: _COMMODITY_V2}
RESOURCE_CELL_FIELDS = ('fishery_resource_proxy_applicable', 'fishery_resource_proxy_supported')
RESOURCE_SUMMARY_FIELDS = ('agricultural_resource_deposit_count', 'energy_resource_deposit_count', 'fishery_resource_proxy_applicable_cell_count', 'fishery_resource_proxy_supported_cell_count', 'high_viability_resource_deposit_count', 'mean_resource_economic_viability_index', 'mean_resource_geologic_confidence_index', 'mean_resource_reserve_potential_index', 'metal_resource_deposit_count', 'resource_deposit_class_counts', 'resource_deposit_count', 'resource_deposit_total_area_km2', 'unsupported_fishery_resource_proxy_cell_count')
RESOURCE_TOP_FIELDS = ('resource_deposits', 'resource_deposit_model')
COMMODITY_CELL_FIELDS = ('fishery_commodity_applicable', 'fishery_commodity_supported')
COMMODITY_SUMMARY_FIELDS = ('bioproductive_commodity_occurrence_count', 'commodity_occurrence_count', 'commodity_occurrence_group_counts', 'commodity_occurrence_total_area_km2', 'commodity_occurrence_type_counts', 'fishery_commodity_applicable_cell_count', 'fishery_commodity_supported_cell_count', 'fuel_commodity_occurrence_count', 'gemstone_commodity_occurrence_count', 'geothermal_commodity_occurrence_count', 'high_potential_commodity_occurrence_count', 'industrial_mineral_commodity_occurrence_count', 'mean_commodity_occurrence_confidence_index', 'mean_commodity_occurrence_potential_index', 'metallic_commodity_occurrence_count', 'unsupported_fishery_commodity_cell_count')
COMMODITY_TOP_FIELDS = ('commodity_occurrences', 'commodity_occurrence_model')


def resource_deposit_expected_model(world: dict[str, Any], chain: str) -> dict[str, Any]:
    own = world.get("resource_deposit_model")
    name = own.get("model_type") if isinstance(own, dict) else None
    new = name == _access.DEPOSIT or (own is None and chain == _NATURAL_PARENT and _access.is_new_source(world))
    if new:
        return {**_DEPOSIT_V4, "model_type": _access.DEPOSIT, **_access.access_policy(world)}
    return _DEPOSIT_BY_PARENT[chain]


def commodity_expected_model(world: dict[str, Any], chain: str) -> dict[str, Any]:
    if resource_deposit_expected_model(world, chain)["model_type"] == _access.DEPOSIT:
        return {**_COMMODITY_V2, "model_type": _access.COMMODITY, "source_resource_deposit_model": _access.DEPOSIT,
                "economic_access_policy": "copy_exact_nullable_source_access_support_and_geographic_baseline"}
    return _COMMODITY_BY_PARENT[chain]


def resource_access_v5(world: dict[str, Any]) -> bool:
    return resource_deposit_expected_model(world, _NATURAL_PARENT)["model_type"] == _access.DEPOSIT

_MAPPING = {
    "volcanic_arc_metals": ("copper", "gold", "silver", "sulfide_ore"),
    "craton_iron_gold": ("diamond", "gold", "iron"),
    "sedimentary_fuels": ("coal", "natural_gas", "petroleum"),
    "evaporites": ("gypsum", "potash", "salt"),
    "placer_metals": ("placer_gold", "tin"),
    "geothermal": ("geothermal_heat", "obsidian", "sulfur"),
    "fertile_alluvium": ("fertile_soils",),
    "coastal_fisheries": ("fishery_biomass",),
}
_FLAGS = (
    "fishery_resource_proxy_applicable", "fishery_resource_proxy_supported",
    "fishery_commodity_applicable", "fishery_commodity_supported",
)
_COUNTS = tuple(key + "_cell_count" for key in _FLAGS) + (
    "unsupported_fishery_resource_proxy_cell_count", "unsupported_fishery_commodity_cell_count",
)


class BiologicalResourceValidationError(ValueError):
    """A bounded, actionable error, raised before a new producer mutates input."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BiologicalResourceValidationError(message)


def _same(observed: Any, expected: Any) -> bool:
    if type(observed) is not type(expected):
        return False
    if isinstance(expected, dict):
        return observed.keys() == expected.keys() and all(_same(observed[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(observed) == len(expected) and all(_same(a, b) for a, b in zip(observed, expected))
    return observed == expected


def _finite(value: Any) -> bool:
    if not isinstance(value, (float, int)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _unit(value: Any) -> bool:
    return _finite(value) and 0 <= value <= 1


def _deposit_metadata(model: Any, expected: dict[str, Any]) -> bool:
    return (isinstance(model, dict) and "flow_accumulation_scale" in model
            and _finite(model["flow_accumulation_scale"]) and model["flow_accumulation_scale"] >= 1
            and _same({k: v for k, v in model.items() if k != "flow_accumulation_scale"}, expected))


def biological_resource_contract(world: dict[str, Any]) -> str | None:
    """Select the exact matched chain, validating own identities before parents.

    E4 preserves its established deposit-v2 to v3 promotion. E5 never retags an
    old declaration and refuses undeclared output mirrors; archive migration
    must audit and clear each changed stage explicitly before rebuilding it.
    """
    _require(isinstance(world, dict), "biological resources: world must be an object")
    deposit = world.get("resource_deposit_model")
    commodity = world.get("commodity_occurrence_model")
    deposit_name = None
    if "resource_deposit_model" in world:
        matched = [m for m in (_DEPOSIT_V2, _DEPOSIT_V3, _DEPOSIT_V4, {**_DEPOSIT_V4, "model_type": _access.DEPOSIT, **_access.access_policy(world)}) if _deposit_metadata(deposit, m)]
        _require(bool(matched), "biological resources: malformed or unknown resource_deposit_model")
        deposit_name = matched[0]["model_type"]
    commodity_name = None
    if "commodity_occurrence_model" in world:
        matched = [m for m in (_COMMODITY_V1, _COMMODITY_V2, {**_COMMODITY_V2, "model_type": _access.COMMODITY, "source_resource_deposit_model": _access.DEPOSIT, "economic_access_policy": "copy_exact_nullable_source_access_support_and_geographic_baseline"}) if _same(commodity, m)]
        _require(bool(matched), "biological resources: malformed or unknown commodity_occurrence_model")
        commodity_name = matched[0]["model_type"]
    parent = world.get("ecosystem_dynamics_model")
    name = None
    if "ecosystem_dynamics_model" in world:
        name = parent.get("model") if isinstance(parent, dict) else None
        expected = _EXPECTED_MODELS.get(name) if isinstance(name, str) else None
        _require(expected is not None and _same(parent, expected), "biological resources require exact known ecosystem model metadata")
    chain = name if name in _DEPOSIT_BY_PARENT else None
    if chain is None:
        # These are already version-owned parent availability declarations, not
        # evidence from which to infer an absent biological production estimate.
        parent_flags = ("terrestrial_primary_climate_supported", "primary_productivity_supported",
            "vegetation_biomass_supported", "species_richness_supported", "ecosystem_wildfire_spread_risk_supported",
            "ecosystem_disturbance_pressure_supported", "forest_growth_supported", "vegetation_succession_supported",
            "vegetation_recovery_supported")
        cells = world.get("cells", [])
        summary = world.get("summary", {})
        markers = (isinstance(cells, list) and any(isinstance(c, dict) and any(k in c for k in parent_flags) for c in cells)) or (
            isinstance(summary, dict) and any(k + "_cell_count" in summary for k in parent_flags))
        _require(not markers, "biological resources: parent availability outputs require their exact ecosystem declaration")
    if deposit_name in (_DEPOSIT_V3["model_type"], _DEPOSIT_V4["model_type"], _access.DEPOSIT):
        _require(chain is not None and deposit_name == resource_deposit_expected_model(world, chain)["model_type"],
                 "biological resources: resource declaration has a mismatched ecosystem parent")
    if deposit_name == _access.DEPOSIT:
        _require(chain == _NATURAL_PARENT, "resource-v5 requires ecosystem-v5")
    if deposit_name == _DEPOSIT_V2["model_type"]:
        _require(chain != _NATURAL_PARENT, "biological resources: historical deposit-v2 cannot use ecosystem-v5")
    if commodity_name is not None:
        _require(chain is not None and commodity_name == commodity_expected_model(world, chain)["model_type"]
                 and deposit_name == resource_deposit_expected_model(world, chain)["model_type"],
                 "biological resources: commodity declaration requires its exact matched deposit/ecosystem parents")
    cells = world.get("cells", [])
    summary = world.get("summary", {})
    for prefix, declared in (("fishery_resource_proxy", deposit_name in (_DEPOSIT_V3["model_type"], _DEPOSIT_V4["model_type"], _access.DEPOSIT)),
                             ("fishery_commodity", commodity_name is not None)):
        fields = (prefix + "_applicable", prefix + "_supported")
        counts = tuple(k + "_cell_count" for k in fields) + ("unsupported_" + prefix + "_cell_count",)
        present = (isinstance(cells, list) and any(isinstance(c, dict) and any(k in c for k in fields) for c in cells)) or (isinstance(summary, dict) and any(k in summary for k in counts))
        _require(not present or declared, "biological resources: undeclared " + prefix + " availability fields")
    if chain == _NATURAL_PARENT:
        _require(isinstance(cells, list) and isinstance(summary, dict), "biological resources: cells list and summary object required")
        for declaration, top, fields, counts in (
            (deposit_name, RESOURCE_TOP_FIELDS, RESOURCE_CELL_FIELDS, RESOURCE_SUMMARY_FIELDS),
            (commodity_name, COMMODITY_TOP_FIELDS, COMMODITY_CELL_FIELDS, COMMODITY_SUMMARY_FIELDS),
        ):
            present = any(k in world for k in top) or any(k in summary for k in counts) or any(isinstance(c, dict) and any(k in c for k in fields) for c in cells)
            _require(declaration is not None or not present, "biological resources: undeclared existing owned outputs require an explicit audited archive upgrade")
        if deposit_name is not None:
            _require(type(deposit["flow_accumulation_scale"]) is float,
                     "biological resources: deposit-v4 normalization must be a float")
    if _access.is_new_source(world) and world.get("generation_scope") != "geo_only":
        _require(chain == _NATURAL_PARENT and resource_access_v5(world), "settlement-v3 or its support mirrors require ecosystem-v5/resource-v5")
    if chain == _NATURAL_PARENT:
        new = resource_access_v5(world)
        _require(not (isinstance(world.get("settlement_selection_model"), dict) and world["settlement_selection_model"].get("model_type") == _access.SETTLEMENT) or new,
                 "biological resources: settlement-v3 requires resource-v5, no stale economic child")
        _require(deposit_name != _access.DEPOSIT or _access.is_new_source(world), "resource-v5 requires exact full settlement-v3 or explicit geo scope")
    mirrors = any(k in summary for k in _access.ACCESS_SUMMARY_FIELDS) or any(isinstance(r,dict) and any(k in r for k in _access.RECORD_FIELDS) for r in world.get("resource_deposits", []))
    _require(not mirrors or deposit_name == _access.DEPOSIT, "resource access availability mirrors require their own v5 declaration")
    commodity_mirrors = any(isinstance(r, dict) and any(k in r for k in ("accessibility_supported", "geographic_accessibility_baseline_index")) for r in world.get("commodity_occurrences", []))
    _require(not commodity_mirrors or commodity_name == _access.COMMODITY, "commodity access mirrors require their own v3 declaration")
    return chain


def uses_biological_resource_support(world: dict[str, Any]) -> bool:
    """Compatibility predicate; producers select with the exact-chain resolver."""
    return biological_resource_contract(world) is not None


def _natural_resource_sources(world: dict[str, Any], support: dict[int, tuple[bool, bool]]) -> None:
    """Explicit inputs for the unchanged v4 deposit equations and evidence.

    The all-cell normalization consumes flow even on omitted sources. Other
    material/access inputs are required only for records the model will emit.
    Prospective settlement score and human linkage remain optional historical
    diagnostics; this stage does not claim natural/access invariance.
    """
    numeric = ("boundary_convergent", "boundary_divergent", "boundary_transform", "sediment_thickness_m",
               "crust_age_ma", "fertility", "soil_salinity_index", "runoff_mm_y", "elevation_m",
               "ice_thickness_m", "seasonal_aridity_index", "area_km2", "lat_deg", "lon_deg")
    categorical = ("water_body_type", "landform", "crust_type", "lithology", "boundary_type")
    for cell in world["cells"]:
        context = f"resource-v4 source cell {cell['id']}"
        _require(type(cell.get("resource")) is str, context + ": explicit resource string required")
        _require(_finite(cell.get("flow_accumulation")), context + ": explicit finite flow_accumulation required")
        if cell["resource"] == "none" or (support[cell["id"]][0] and not support[cell["id"]][1]):
            continue
        for key in numeric:
            _require(_finite(cell.get(key)), context + ": explicit finite " + key + " required")
        for key in categorical:
            _require(type(cell.get(key)) is str, context + ": explicit " + key + " string required")
        _require(type(cell.get("is_river")) is bool, context + ": explicit is_river boolean required")
        _require(type(cell.get("basin_id")) is int, context + ": explicit basin_id integer required")
        if "settlement_score" in cell:
            _require(_finite(cell["settlement_score"]), context + ": optional settlement_score must be finite numeric")
        for key in ("political_region_id", "culture_region_id"):
            if key in cell:
                _require(type(cell[key]) is int, context + ": optional " + key + " must be an integer")


def audit_biological_commodity_inputs(world: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Required v2 material inputs; absence of a matching system is still zero.

    An explicitly empty systems list is valid, unlike a missing producer stage.
    Return independently selected sources for exact v2 evidence replay.
    Selection/tie semantics and all existing material equations remain intact.
    """
    if biological_resource_contract(world) != _NATURAL_PARENT:
        return {}
    systems = world.get("sedimentary_resource_systems")
    _require(isinstance(systems, list), "commodity-v2: explicit sedimentary_resource_systems list required")
    selected = {}
    for index, system in enumerate(systems):
        context = f"commodity-v2 sedimentary source {index}"
        _require(isinstance(system, dict), context + ": object required")
        _require(type(system.get("basin_id")) is int, context + ": basin_id integer required")
        if system["basin_id"] < 0:
            continue  # Preserved historical sentinel skip.
        _require(_finite(system.get("system_confidence_index")), context + ": explicit finite system_confidence_index required")
        previous = selected.get(system["basin_id"])
        # The unchanged producer starts at -1, so a first confidence below -1
        # does not select a source. Equal confidence retains the last source.
        current_confidence = float(previous["system_confidence_index"]) if previous is not None else -1.0
        if float(system["system_confidence_index"]) >= current_confidence:
            selected[system["basin_id"]] = system
    by_cell = {c["id"]: c for c in world["cells"]}
    for deposit in world["resource_deposits"]:
        if deposit["resource"] in _MAPPING:
            cell = by_cell[deposit["cell_id"]]
            _require(_finite(cell.get("volcanic_potential_index")),
                     f"commodity-v2 source cell {cell['id']}: explicit finite volcanic_potential_index required")
            system = selected.get(deposit["basin_id"])
            if system is not None:
                context = f"commodity-v2 selected sedimentary source basin {deposit['basin_id']}"
                for key in ("petroleum_potential_index", "gas_potential_index", "coal_potential_index", "evaporite_salt_potential_index"):
                    _require(_finite(system.get(key)), context + ": explicit finite " + key + " required")
                source_id = system.get("id")
                _require(type(source_id) is int and source_id >= 0,
                         context + ": explicit nonnegative id integer required")
                _require(sum(type(other.get("id")) is int and other["id"] == source_id for other in systems) == 1,
                         context + ": selected source id must identify exactly one declared record")
    return selected


def _commodity_v2_formation_evidence(deposit, cell, system):
    """Replay evidence from audited sources, independently of commodity producer."""
    inherited = deposit["formation_evidence"]
    evidence = {"boundary_type": inherited["boundary_type"]}
    for key in ("boundary_convergent", "boundary_divergent", "salinity_index", "fertility"):
        evidence[key] = round(_clamp(float(inherited[key])), 6)
    for key in ("crust_age_ma", "sediment_thickness_m", "flow_accumulation"):
        evidence[key] = round(max(0.0, float(inherited[key])), 6)
    evidence["volcanic_potential_index"] = round(_clamp(float(cell["volcanic_potential_index"])), 6)
    if system is not None:
        evidence["sedimentary_resource_system_id"] = system["id"]
        for key in ("petroleum_potential_index", "gas_potential_index", "coal_potential_index", "evaporite_salt_potential_index"):
            evidence[key] = round(_clamp(float(system[key])), 6)
    return evidence


def biological_resource_parent_support(world: dict[str, Any]) -> dict[int, tuple[bool, bool]]:
    """Audit matched ecosystem-v4/v5 ancestry and independently reconstruct fishery support.

Positive proxy values are inputs, not a producer-specific equation replay: a
known supported zero remains usable. Missing/nonunit inputs make this consumer
unavailable, while forged upstream support flags are invalid declarations.
"""
    chain = biological_resource_contract(world)
    _require(chain is not None, "biological resources require a matched ecosystem-v4 or ecosystem-v5 parent")
    errors = validate_aquatic_climate_support(world)
    _require(not errors, "biological resources ecosystem parent: " + (errors[0] if errors else ""))
    support: dict[int, tuple[bool, bool]] = {}
    for cell in world["cells"]:
        cell_id = cell["id"]
        resource = cell.get("resource", "none")
        _require(isinstance(resource, str), f"biological resources cell {cell_id}: resource must be a string")
        water = cell.get("water_body_type")
        temperature = cell.get("temperature_c")
        applicable = resource == "coastal_fisheries"
        supported = (applicable and isinstance(water, str) and water in _WATER
                     and _finite(temperature) and -16.0 < temperature < 44.0
                     and _unit(cell.get("primary_productivity_index"))
                     and _unit(cell.get("fishery_productivity_index")))
        support[cell_id] = (applicable, supported)
    if chain == _NATURAL_PARENT:
        _natural_resource_sources(world, support)
    return support


def _number(record: dict[str, Any], key: str, context: str, default: Any = None) -> float:
    value = record.get(key, default)
    _require(_finite(value), f"{context}: {key} must be finite numeric")
    return float(value)


def _close(actual: Any, expected: float, context: str, tolerance: float = 5e-10) -> None:
    _require(_finite(actual) and _finite(expected) and abs(actual - expected) <= tolerance,
             f"{context}: numerical replay mismatch")


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _fishery_deposit(cell: dict[str, Any]) -> dict[str, float]:
    context = f"fishery deposit cell {cell['id']}"
    get = lambda key: _number(cell, key, context, 0.0)
    runoff = _clamp(get("runoff_mm_y") / 900.0)
    shelf = cell.get("water_body_type") == "continental_shelf"
    reserve = _clamp(.30 + .26 * shelf + .12 * runoff)
    access = _clamp(.28 + .42 * _clamp(get("settlement_score"))
                    + .20 * (bool(cell.get("is_river", False)) or cell.get("water_body_type") in {"continental_shelf", "fresh_lake"})
                    - .20 * _clamp(abs(get("elevation_m")) / 3000.0))
    hazard = _clamp(_clamp(.42 * get("boundary_convergent") + .30 * get("boundary_transform"))
                    + .20 * _clamp(abs(get("elevation_m")) / 3600.0)
                    + .20 * _clamp(get("ice_thickness_m") / 1600.0)
                    + .10 * _clamp(get("seasonal_aridity_index")) + .08 * _clamp(get("soil_salinity_index")))
    confidence = _clamp((.18 + .32 * shelf + .12 * runoff) * .72 + reserve * .28)
    return {
        "reserve_potential_index": reserve, "accessibility_index": access,
        "extraction_hazard_index": hazard, "geologic_confidence_index": confidence,
        "renewability_index": .78,
        "economic_viability_index": _clamp(.46 * reserve + .30 * access + .20 * confidence - .18 * hazard + .10 * .78),
    }


def _source_evidence(cell: dict[str, Any]) -> dict[str, Any]:
    context = f"resource source evidence cell {cell['id']}"
    get = lambda key: _number(cell, key, context, 0.0)
    return {
        "boundary_type": str(cell.get("boundary_type", "unknown")),
        "boundary_convergent": round(_clamp(get("boundary_convergent")), 6),
        "boundary_divergent": round(_clamp(get("boundary_divergent")), 6),
        "crust_age_ma": round(max(0.0, get("crust_age_ma")), 6),
        "sediment_thickness_m": round(max(0.0, get("sediment_thickness_m")), 6),
        "flow_accumulation": round(max(0.0, get("flow_accumulation")), 6),
        "fertility": round(_clamp(get("fertility")), 6),
        "salinity_index": round(_clamp(get("soil_salinity_index")), 6),
    }


def _count(summary: dict[str, Any], key: str, expected: int) -> None:
    _require(type(summary.get(key)) is int and summary[key] == expected, "biological resource summary: " + key + " mismatch")


def _serialized_threshold_count(
    summary: dict[str, Any], key: str, values: list[float], threshold: float,
    *, replayed_values: list[float],
) -> None:
    # Biological raw values are independently replayed from their actual inputs,
    # using binary64 operations before display rounding. Their count is exact.
    # Only unreplayed material records retain the six-place uncertainty interval.
    known = sum(v >= threshold for v in replayed_values)
    lower = known + sum(v >= threshold + .500001e-6 for v in values)
    upper = known + sum(v >= threshold - .500001e-6 for v in values)
    _require(type(summary.get(key)) is int and lower <= summary[key] <= upper,
             "biological resource summary: " + key + " exceeds rounded-record threshold bounds")


def _check_support(world: dict[str, Any], support: dict[int, tuple[bool, bool]], prefix: str) -> None:
    for cell in world["cells"]:
        for suffix, expected in zip(("applicable", "supported"), support[cell["id"]]):
            field = prefix + "_" + suffix
            _require(cell.get(field) is expected, f"biological resources cell {cell['id']}: {field} mismatch")
    expected_counts = {
        prefix + "_applicable_cell_count": sum(a for a, _ in support.values()),
        prefix + "_supported_cell_count": sum(s for _, s in support.values()),
        "unsupported_" + prefix + "_cell_count": sum(a and not s for a, s in support.values()),
    }
    for key, expected in expected_counts.items():
        _require(type(world["summary"].get(key)) is int and world["summary"][key] == expected,
                 f"biological resource summary: {key} mismatch")


def _audit_deposits(world: dict[str, Any], support: dict[int, tuple[bool, bool]]) -> dict[int, dict[str, Any]]:
    chain = biological_resource_contract(world)
    _require(chain is not None and _deposit_metadata(world.get("resource_deposit_model"), resource_deposit_expected_model(world, chain)),
             "biological resources require the complete matched resource-deposit parent")
    new_access = resource_access_v5(world) if chain == _NATURAL_PARENT else False
    cells = world["cells"]
    positive = sorted(max(0.0, _number(c, "flow_accumulation", f"cell {c['id']}", 0.0)) for c in cells)
    positive = [v for v in positive if v > 0]
    scale = max(1.0, positive[int(.95 * (len(positive) - 1))]) if positive else 1.0
    _close(world["resource_deposit_model"]["flow_accumulation_scale"], round(scale, 6), "resource all-cell p95 normalization")
    records = world.get("resource_deposits")
    _require(isinstance(records, list), "biological resources require a resource_deposits list")
    expected = [c for c in cells if c.get("resource", "none") != "none" and (not support[c["id"]][0] or support[c["id"]][1])]
    _require(len(records) == len(expected), "resource deposit coverage: missing supported deposit or unexpected unsupported deposit")
    by_cell: dict[int, dict[str, Any]] = {}
    biological_viability: list[float] = []
    for index, (record, cell) in enumerate(zip(records, expected)):
        context = f"resource deposit {index} cell {cell['id']}"
        _require(isinstance(record, dict), context + ": record must be an object")
        _require(type(record.get("id")) is int and record["id"] == index, context + ": IDs must be dense in cell order")
        _require(type(record.get("cell_id")) is int and record["cell_id"] == cell["id"] and record.get("resource") == cell.get("resource"),
                 context + ": source linkage mismatch")
        for key in ("reserve_potential_index", "accessibility_index", "extraction_hazard_index", "economic_viability_index", "renewability_index", "geologic_confidence_index"):
            if new_access and key in ("accessibility_index", "economic_viability_index"):
                continue
            _require(_unit(record.get(key)), context + f": {key} must be a finite unit index")
        _close(record.get("area_km2"), round(max(0.0, _number(cell, "area_km2", context, 0.0)), 6), context + " area")
        for key, source, default in (("host_crust_type", "crust_type", "unknown"), ("host_lithology", "lithology", "unknown"),
                                     ("landform", "landform", "unknown")):
            _require(record.get(key) == str(cell.get(source, default)), context + ": " + key + " source mismatch")
        for key in ("basin_id", "political_region_id", "culture_region_id"):
            _require(type(record.get(key)) is int and record[key] == int(cell.get(key, -1)), context + ": " + key + " source mismatch")
        for key, source in (("latitude_deg", "lat_deg"), ("longitude_deg", "lon_deg")):
            _close(record.get(key), round(_number(cell, source, context, 0.0), 6), context + " " + key)
        _require(_same(record.get("formation_evidence"), _source_evidence(cell)), context + ": missing or mismatched formation evidence")
        resource = cell.get("resource")
        category = ("metal" if resource in {"volcanic_arc_metals", "craton_iron_gold", "placer_metals"}
                    else "energy" if resource in {"sedimentary_fuels", "geothermal"}
                    else "industrial_mineral" if resource == "evaporites"
                    else "bioproductive" if resource in {"fertile_alluvium", "coastal_fisheries"} else "other")
        _require(record.get("deposit_class") == category, context + ": resource category mismatch")
        if support[cell["id"]][0]:
            biological = _fishery_deposit(cell)
            biological_viability.append(biological["economic_viability_index"])
            for key, value in biological.items():
                if new_access and key in ("accessibility_index", "economic_viability_index"):
                    continue
                _close(record.get(key), round(value, 6), context + " " + key)
            _require(record.get("formation_process") == "shelf_coastal_bioproductivity" and record.get("deposit_class") == "bioproductive",
                     context + ": biological category mismatch")
        by_cell[cell["id"]] = record
    _check_support(world, support, "fishery_resource_proxy")
    summary = world["summary"]
    _count(summary, "resource_deposit_count", len(records))
    categories = Counter(r["deposit_class"] for r in records)
    for field, category in (("metal_resource_deposit_count", "metal"), ("energy_resource_deposit_count", "energy"),
                            ("agricultural_resource_deposit_count", "bioproductive")):
        _count(summary, field, categories.get(category, 0))
    _require(_same(summary.get("resource_deposit_class_counts"), dict(sorted(categories.items()))), "resource deposit class counts mismatch")
    if new_access:
        _access.audit(world, records, scale)
    else:
        _serialized_threshold_count(summary, "high_viability_resource_deposit_count",
                                    [r["economic_viability_index"] for r in records if r["resource"] != "coastal_fisheries"],
                                    .65, replayed_values=biological_viability)
    total_area = math.fsum(max(0.0, _number(c, "area_km2", "deposit total area", 0.0)) for c in expected)
    _close(summary.get("resource_deposit_total_area_km2"), round(total_area, 6), "resource deposit total area", max(5e-7, 16 * len(records) * math.ulp(total_area)))
    for out, field in (("mean_resource_reserve_potential_index", "reserve_potential_index"),
                       ("mean_resource_economic_viability_index", "economic_viability_index"),
                       ("mean_resource_geologic_confidence_index", "geologic_confidence_index")):
        if new_access and field == "economic_viability_index":
            continue
        mean = math.fsum(r[field] / len(records) for r in records) if records else 0.0
        _close(world["summary"].get(out), mean, out, 1.000001e-6)
    return by_cell


def audit_biological_resource_deposits(world: dict[str, Any]) -> dict[int, tuple[bool, bool]]:
    """Validate the new source stage and return independently derived support."""
    try:
        support = biological_resource_parent_support(world)
        _audit_deposits(world, support)
        return support
    except BiologicalResourceValidationError:
        raise
    except (TypeError, ValueError, KeyError, OverflowError, ArithmeticError) as exc:
        raise BiologicalResourceValidationError("biological resource envelope is malformed: " + type(exc).__name__) from exc


def validate_biological_resources(world: dict[str, Any], *, include_commodities: bool = True) -> list[str]:
    """Return at most one error; no-model/known historical envelopes are allowed."""
    try:
        chain = biological_resource_contract(world)
        if chain is None:
            return []
        support = audit_biological_resource_deposits(world)
        if not include_commodities:
            return []
        _require(_same(world.get("commodity_occurrence_model"), commodity_expected_model(world, chain)), "biological resources require exact matched commodity model metadata")
        new_access = resource_access_v5(world) if chain == _NATURAL_PARENT else False
        selected_sources = audit_biological_commodity_inputs(world)
        records = world.get("commodity_occurrences")
        _require(isinstance(records, list), "biological resources require a commodity_occurrences list")
        expected = [(d, name) for d in world["resource_deposits"] for name in _MAPPING.get(d["resource"], ())]
        _require(len(records) == len(expected), "commodity coverage: missing supported occurrence or unexpected record")
        by_cell = {c["id"]: c for c in world["cells"]}
        biological_potential: list[float] = []
        for index, (record, (deposit, name)) in enumerate(zip(records, expected)):
            context = f"commodity occurrence {index}"
            _require(isinstance(record, dict), context + ": record must be an object")
            _require(type(record.get("id")) is int and record["id"] == index, context + ": IDs must be dense")
            for key, value in (("resource_deposit_id", deposit["id"]), ("cell_id", deposit["cell_id"]), ("commodity", name), ("source_resource", deposit["resource"])):
                _require(_same(record.get(key), value), context + f": {key} linkage mismatch")
            if new_access:
                for key in ("accessibility_index", "accessibility_supported", "geographic_accessibility_baseline_index"):
                    _require(key in record and _same(record[key], deposit[key]), context + ": " + key + " source mismatch")
            for key in ("occurrence_potential_index", "geologic_confidence_index", "accessibility_index", "extraction_hazard_index", "market_value_index"):
                if new_access and key == "accessibility_index":
                    continue
                _require(_unit(record.get(key)), context + f": {key} must be a finite unit index")
            for key in ("formation_process", "host_crust_type", "host_lithology", "landform", "basin_id", "political_region_id", "culture_region_id", "area_km2"):
                _require(_same(record.get(key), deposit.get(key)), context + ": " + key + " source mismatch")
            _require(isinstance(record.get("formation_evidence"), dict), context + ": formation evidence must be an object")
            if chain == _NATURAL_PARENT:
                expected_evidence = _commodity_v2_formation_evidence(
                    deposit, by_cell[deposit["cell_id"]], selected_sources.get(deposit["basin_id"]))
                _require(_same(record["formation_evidence"], expected_evidence),
                         context + ": exact formation evidence differs from selected sources")
            else:
                for key, value in deposit["formation_evidence"].items():
                    _require(_same(record["formation_evidence"].get(key), value), context + ": inherited evidence " + key + " mismatch")
            if name == "fishery_biomass":
                cell = by_cell[deposit["cell_id"]]
                _require(support[cell["id"]][1], context + ": fishery input is unavailable")
                water = cell["water_body_type"]
                potential = _clamp(.30 * deposit["reserve_potential_index"] + .24 * (water in {"ocean", "continental_shelf", "inland_sea"})
                                   + .16 * (water == "continental_shelf") + .18 * deposit["geologic_confidence_index"] + .20 * cell["fishery_productivity_index"])
                confidence = _clamp(.54 * deposit["geologic_confidence_index"] + .30 * potential + .16 * deposit["reserve_potential_index"])
                biological_potential.append(potential)
                for key, value in (("occurrence_potential_index", potential), ("geologic_confidence_index", confidence),
                                   ("accessibility_index", deposit["accessibility_index"]), ("extraction_hazard_index", deposit["extraction_hazard_index"]), ("market_value_index", .58)):
                    if new_access and key == "accessibility_index":
                        continue
                    _close(record.get(key), round(value, 6), context + " " + key)
                _require(record.get("commodity_group") == "fishery", context + ": fishery group mismatch")
        _check_support(world, support, "fishery_commodity")
        summary = world["summary"]
        _count(summary, "commodity_occurrence_count", len(records))
        groups = Counter(r.get("commodity_group") for r in records)
        _require(all(isinstance(key, str) for key in groups), "commodity groups must be strings")
        _require(_same(summary.get("commodity_occurrence_group_counts"), dict(sorted(groups.items()))), "commodity group counts mismatch")
        for field, included in (
            ("metallic_commodity_occurrence_count", ("base_metal", "ferrous_metal", "precious_metal")),
            ("fuel_commodity_occurrence_count", ("fuel",)), ("industrial_mineral_commodity_occurrence_count", ("industrial_mineral",)),
            ("gemstone_commodity_occurrence_count", ("gemstone",)), ("geothermal_commodity_occurrence_count", ("geothermal",)),
            ("bioproductive_commodity_occurrence_count", ("agricultural", "fishery")),
        ):
            _count(summary, field, sum(groups.get(group, 0) for group in included))
        _serialized_threshold_count(summary, "high_potential_commodity_occurrence_count",
                                    [r["occurrence_potential_index"] for r in records if r["commodity"] != "fishery_biomass"],
                                    .62, replayed_values=biological_potential)
        total_area = math.fsum(r["area_km2"] for r in records)
        _close(summary.get("commodity_occurrence_total_area_km2"), round(total_area, 6), "commodity total area", max(5e-7, 16 * len(records) * math.ulp(total_area)))
        for out, field in (("mean_commodity_occurrence_potential_index", "occurrence_potential_index"), ("mean_commodity_occurrence_confidence_index", "geologic_confidence_index")):
            mean = math.fsum(r[field] / len(records) for r in records) if records else 0.0
            _close(world["summary"].get(out), mean, out, 1.000001e-6)
        counts = dict(sorted(Counter(r["commodity"] for r in records).items()))
        _require(_same(world["summary"].get("commodity_occurrence_type_counts"), counts), "commodity type count mismatch")
        return []
    except BiologicalResourceValidationError as exc:
        return [str(exc)]
    except (TypeError, ValueError, KeyError, OverflowError, ArithmeticError) as exc:
        return ["biological resource envelope is malformed: " + type(exc).__name__]
