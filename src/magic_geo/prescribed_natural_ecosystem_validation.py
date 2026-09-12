"""Independent raw-input replay of the prescribed-natural ecosystem v5.

No ecosystem producer functions or constants are imported. Internal raw values
feed this stage's descendants; published six-decimal values feed later stages.
Settlement suitability and selected settlement records are not inputs.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Any


V5_NAME = "heuristic_ecosystem_climate_support_v5"
NATURAL_POLICY = {
    "model": V5_NAME,
    "ecosystem_disturbance_input_scope": "static_empirical_fire_frequency_aridity_ecotone_erosion_wind_descriptors_not_observed_fire_or_final_wildfire_feedback",
    "activity_forcing_policy": "prescribed_natural_scenario_without_anthropogenic_activity_input",
    "settlement_score_input_policy": "not_read_omitted_without_substitute_or_renormalization",
    "activity_scope": "scenario_boundary_not_inferred_absence_of_people_or_observed_fire",
    "physical_input_policy": "explicit_finite_nonboolean_descriptors_and_typed_habitat_biome_sources_no_missing_value_substitution",
}
FLAGS = (
    "aquatic_climate_proxy_applicable", "aquatic_primary_climate_supported",
    "fishery_climate_supported", "fishery_productivity_supported",
    "terrestrial_primary_climate_supported", "primary_productivity_supported",
    "vegetation_biomass_supported", "species_richness_supported",
    "ecosystem_wildfire_spread_risk_supported", "ecosystem_disturbance_pressure_supported",
    "forest_growth_supported", "vegetation_succession_supported", "vegetation_recovery_supported",
)
INDICES = (
    "primary_productivity_index", "vegetation_biomass_index", "species_richness_index",
    "wildfire_spread_risk_index", "ecosystem_disturbance_pressure_index",
    "forest_growth_index", "fishery_productivity_index",
)
CELL_FIELDS = FLAGS + INDICES + ("vegetation_succession_stage", "vegetation_recovery_years")
RECORD_FIELDS = ("vegetation_succession_histories", "renewable_resource_records")
SUMMARY_FIELDS = (
    "vegetation_succession_history_count", "vegetation_succession_step_count",
    *("mean_" + key for key in INDICES), "high_wildfire_spread_risk_cell_count",
    "mature_vegetation_cell_fraction", "renewable_resource_record_count",
    "forest_growth_resource_count", "fishery_productivity_resource_count",
    "vegetation_succession_stage_counts", "renewable_resource_type_counts",
    *(key + "_cell_count" for key in FLAGS[4:]),
)
_WATER = {"ocean", "continental_shelf", "inland_sea", "fresh_lake"}
_FOREST = {"tropical_rainforest", "tropical_seasonal_forest", "temperate_forest", "boreal_forest"}
_GRASS = {"savanna", "temperate_grassland", "mediterranean_scrub"}
_BARREN = {"ice_cap", "tundra", "alpine", "hot_desert", "cold_desert"}
_NUMERIC_INPUTS = (
    "precipitation_mm_y", "potential_evapotranspiration_mm_y", "soil_moisture_index",
    "fertility", "growing_season_months", "runoff_mm_y", "ocean_current_temperature_c",
    "ocean_current_east", "ice_thickness_m", "seasonal_aridity_index",
    "soil_organic_matter_fraction", "fire_frequency_index", "ecotone_index",
    "erosion_rate", "wind_east", "wind_north", "groundwater_recharge_mm_y",
)


class PrescribedNaturalEcosystemError(ValueError):
    """A bounded input or independent numerical-replay failure."""


def _need(ok: bool, message: str) -> None:
    if not ok:
        raise PrescribedNaturalEcosystemError("prescribed natural ecosystem: " + message)


def _finite(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def _n(cell: dict[str, Any], key: str) -> float:
    value = cell.get(key)
    _need(_finite(value), f"cell {cell['id']}: {key} requires an explicit finite nonboolean numeric source")
    return float(value)


def _same(actual: Any, expected: Any, path: str) -> None:
    _need(type(actual) is type(expected), path + " has wrong type")
    if isinstance(expected, dict):
        _need(actual.keys() == expected.keys(), path + " keys differ")
        for key in expected:
            _same(actual[key], expected[key], path + "." + str(key))
    elif isinstance(expected, list):
        _need(len(actual) == len(expected), path + " length differs")
        for index, (a, e) in enumerate(zip(actual, expected)):
            _same(a, e, path + f"[{index}]")
    else:
        _need(actual == expected, path + " differs from raw-input replay")


def _source_cells(world: dict[str, Any]) -> list[dict[str, Any]]:
    _need(isinstance(world, dict), "world must be an object")
    _need(isinstance(world.get("cells"), list), "cells must be a list")
    _need(isinstance(world.get("summary", {}), dict), "summary must be an object")
    seen = set()
    for cell in world["cells"]:
        _need(isinstance(cell, dict), "cells must contain objects")
        cid = cell.get("id")
        _need(type(cid) is int and cid >= 0 and cid not in seen, "cell IDs must be unique nonnegative integers")
        seen.add(cid)
        for key in _NUMERIC_INPUTS:
            _n(cell, key)
        for key in ("is_water", "is_lake"):
            _need(type(cell.get(key)) is bool, f"cell {cid}: {key} requires an explicit boolean source")
        for key in ("biome", "water_body_type"):
            value = cell.get(key)
            _need(isinstance(value, str) and bool(value.strip()), f"cell {cid}: {key} requires a nonempty text source")
    return world["cells"]


def validate_prescribed_natural_inputs(world: dict[str, Any]) -> None:
    """Complete uniform physical source schema; S and human records are not read.

    These fields precede ecosystems in both API pipelines. Explicit zero is a
    value; omission is missing upstream data. Annual temperature retains its
    separately declared unsupported-value policy. The uniform schema does not
    imply that every descriptor contributes to every habitat's equation.
    """
    _source_cells(world)


def _state(c: dict[str, Any]) -> dict[str, Any]:
    n = lambda k: _n(c, k)
    unit = lambda k: _clip(n(k))
    water = c["water_body_type"]
    aquatic = c["is_water"] or c["is_lake"] or water in _WATER
    temperature = c.get("temperature_c")
    finite_t = _finite(temperature)
    primary_ok = bool(finite_t and -16.0 < temperature < 52.0)
    fish_climate = bool(water in _WATER and finite_t and -20.0 < temperature < 44.0)
    fish_ok = aquatic and primary_ok and fish_climate
    land_ok = not aquatic and primary_ok
    risk_ok = aquatic or land_ok
    recovery_ok = primary_ok and (aquatic or land_ok) and risk_ok
    thermal = _clip(1.0 - abs(float(temperature) - 18.0) / 34.0) if finite_t else 0.0
    moisture = unit("soil_moisture_index")
    aridity = unit("seasonal_aridity_index")
    ice = _clip(n("ice_thickness_m") / 1200.0)
    biome = c["biome"]
    p = b = risk = disturbance = forest = fish = richness = 0.0
    if primary_ok:
        if aquatic:
            shelf = .20 if water == "continental_shelf" else (.12 if water in {"fresh_lake", "inland_sea"} else .04)
            p = _clip(.12 + shelf + thermal * .24 + _clip(n("runoff_mm_y") / 900.0) * .22 + _clip(abs(n("ocean_current_temperature_c")) / 4.5) * .12)
        else:
            p = _clip(thermal * .26 + _clip(n("precipitation_mm_y") / max(1.0, n("potential_evapotranspiration_mm_y"))) * .22 + moisture * .18 + unit("fertility") * .18 + _clip(n("growing_season_months") / 12.0) * .18 - aridity * .14 - ice * .18)
    if land_ok:
        bonus = .28 if biome in _FOREST else (.13 if biome in _GRASS else (-.16 if biome in _BARREN else .02))
        b = _clip(p * .52 + unit("soil_organic_matter_fraction") * .18 + moisture * .14 + bonus - ice * .22)
    if risk_ok:
        wind = _clip((n("wind_east") ** 2 + n("wind_north") ** 2) ** .5)
        risk = 0.0 if aquatic else _clip(unit("fire_frequency_index") * .38 + b * .22 + aridity * .22 + wind * .10)
        disturbance = _clip(risk * .42 + unit("ecotone_index") * .16 + _clip(abs(n("erosion_rate")) / .08) * .14 + aridity * .12)
    if primary_ok:
        richness = _clip(p * .34 + b * .22 + unit("ecotone_index") * .18 + thermal * .16 + moisture * .10)
    if land_ok:
        if biome in _FOREST or "forest" in biome:
            forest = _clip(p * .44 + b * .28 + moisture * .14 + unit("fertility") * .12 - disturbance * .16)
        elif biome in _GRASS:
            forest = _clip(p * .20 + b * .12)
    if fish_ok:
        shelf = .30 if water == "continental_shelf" else (.18 if water in {"fresh_lake", "inland_sea"} else .08)
        fish = _clip(shelf + p * .34 + _clip(n("runoff_mm_y") / 900.0) * .20 + _clip(abs(n("ocean_current_temperature_c")) / 4.5 + abs(n("ocean_current_east")) * .4) * .14 + _clip(1.0 - abs(float(temperature) - 12.0) / 32.0) * .12)
    recovery = int(round(4 + (1.0 - p) * 46 + disturbance * 34 + (1.0 - b) * 18)) if recovery_ok else 0
    return dict(c=c, aquatic=aquatic, water=water, biome=biome, primary_ok=primary_ok,
                fish_climate=fish_climate, fish_ok=fish_ok, land_ok=land_ok, risk_ok=risk_ok,
                recovery_ok=recovery_ok, p=p, b=b, risk=risk, d=disturbance, forest=forest,
                fish=fish, richness=richness, recovery=recovery, thermal=thermal)


def _stage(s: dict[str, Any], b: float, d: float) -> str:
    if s["aquatic"]:
        return "aquatic_primary_productivity"
    if not s["land_ok"]:
        return "terrestrial_primary_proxy_unavailable"
    if s["biome"] == "ice_cap" or _n(s["c"], "ice_thickness_m") > 120.0:
        return "barren_ice"
    if b < .08 or s["p"] < .12:
        return "pioneer_sparse_cover"
    if d >= .58:
        return "disturbance_mosaic"
    if s["forest"] >= .62 and b >= .62:
        return "mature_closed_canopy"
    return "mid_successional_cover" if b >= .44 else "early_successional_cover"


def _reconstruct(world: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    cells = _source_cells(world)
    patches, histories, renewables = [], [], []
    stage_counts, resource_counts = Counter(), Counter()
    totals = dict.fromkeys(INDICES, 0.0)
    high_risk = mature = 0
    for c in cells:
        s = _state(c)
        p, b, d, risk, forest, fish = (s[k] for k in ("p", "b", "d", "risk", "forest", "fish"))
        stage = _stage(s, b, d)
        flags = (s["aquatic"], s["aquatic"] and s["primary_ok"], s["fish_climate"], s["fish_ok"],
                 s["land_ok"], s["primary_ok"], s["land_ok"], s["primary_ok"], s["risk_ok"],
                 s["risk_ok"], s["land_ok"], s["land_ok"], s["recovery_ok"])
        raw = (p, b, s["richness"], risk, d, forest, fish)
        patch = dict(zip(FLAGS, flags))
        patch.update({key: round(v, 6) for key, v in zip(INDICES, raw)})
        patch.update(vegetation_succession_stage=stage, vegetation_recovery_years=s["recovery"])
        patches.append(patch)
        for key, value in zip(INDICES, raw):
            totals[key] += value
        stage_counts[stage] += 1
        high_risk += int(s["risk_ok"] and risk >= .65)
        mature += int(stage == "mature_closed_canopy")
        if s["land_ok"] and s["recovery_ok"] and stage not in {"barren_ice", "pioneer_sparse_cover"} and b > .06:
            steps = []
            initial = _clip(b * (.38 + (1.0 - d) * .26))
            for i, (phase, year) in enumerate((("establishment", 0), ("canopy_building", 25), ("mature_state", 60), ("disturbance_recovery", 90))):
                progress = i / 3
                sb = _clip(initial + (b - initial) * progress + p * .04 * i - d * .025 * i)
                sd = _clip(d * (1.0 - progress * .18) + risk * (.08 if i == 3 else 0.0))
                steps.append({"phase": phase, "years_since_start": year, "succession_stage": _stage(s, sb, sd),
                    "biomass_index": round(sb, 6), "canopy_closure_index": round(_clip(sb * (.50 + forest * .42)), 6),
                    "primary_productivity_index": round(p, 6), "disturbance_pressure_index": round(sd, 6),
                    "wildfire_spread_risk_index": round(risk, 6), "recovery_fraction": round(_clip(progress * (1.0 - sd * .38)), 6)})
            histories.append({"id": len(histories), "cell_id": c["id"], "biome": s["biome"],
                "initial_succession_stage": steps[0]["succession_stage"], "final_succession_stage": steps[-1]["succession_stage"],
                "step_count": 4, "recovery_years": s["recovery"],
                **{"mean_" + key: round(sum(step[key] for step in steps) / 4, 6) for key in ("biomass_index", "canopy_closure_index", "disturbance_pressure_index")},
                "max_wildfire_spread_risk_index": max(step["wildfire_spread_risk_index"] for step in steps), "steps": steps})
        resource, productivity = "", 0.0
        if s["land_ok"] and s["recovery_ok"] and forest >= .25:
            resource, productivity = "forest_growth", forest
        if s["fish_ok"] and s["recovery_ok"] and fish >= .35 and fish >= productivity:
            resource, productivity = "fishery_productivity", fish
        if resource:
            resource_counts[resource] += 1
            renewables.append({"id": len(renewables), "cell_id": c["id"], "resource_type": resource,
                "biome": s["biome"], "water_body_type": s["water"], "productivity_index": round(productivity, 6),
                "sustainable_yield_index": round(_clip(productivity * .56 + p * .20 + b * .14 - d * .18), 6),
                "regeneration_years": max(1, int(round(s["recovery"] * (.35 if resource == "fishery_productivity" else 1.0)))),
                "climate_dependency_index": round(_clip(1.0 - s["thermal"] + _clip(_n(c, "seasonal_aridity_index")) * .35), 6),
                "water_dependency_index": round(_clip(_clip(_n(c, "soil_moisture_index")) * .45 + _n(c, "groundwater_recharge_mm_y") / 450.0 * .35 + (.30 if s["aquatic"] else 0.0)), 6),
                "disturbance_risk_index": round(d, 6), "formation_evidence": {
                    "primary_productivity_index": round(p, 6), "vegetation_biomass_index": round(b, 6),
                    "forest_growth_index": round(forest, 6), "fishery_productivity_index": round(fish, 6),
                    "runoff_mm_y": round(max(0.0, _n(c, "runoff_mm_y")), 6),
                    "soil_moisture_index": round(_clip(_n(c, "soil_moisture_index")), 6)}})
    count = len(cells)
    summary = {"vegetation_succession_history_count": len(histories), "vegetation_succession_step_count": 4 * len(histories),
        **{"mean_" + k: round(v / count, 6) if count else 0.0 for k, v in totals.items()},
        "high_wildfire_spread_risk_cell_count": high_risk, "mature_vegetation_cell_fraction": round(mature / count, 6) if count else 0.0,
        "renewable_resource_record_count": len(renewables), "forest_growth_resource_count": resource_counts["forest_growth"],
        "fishery_productivity_resource_count": resource_counts["fishery_productivity"],
        "vegetation_succession_stage_counts": dict(sorted(stage_counts.items())), "renewable_resource_type_counts": dict(sorted(resource_counts.items()))}
    summary.update({key + "_cell_count": sum(patch[key] for patch in patches) for key in FLAGS[4:]})
    return patches, summary, dict(zip(RECORD_FIELDS, (histories, renewables)))


def audit_prescribed_natural_ecosystem(world: dict[str, Any]) -> None:
    """Raise one bounded error; metadata is supplied by the independent contract owner."""
    _need(isinstance(world, dict), "world must be an object")
    from .aquatic_climate_validation import _EXPECTED_MODELS
    expected_model = _EXPECTED_MODELS[V5_NAME]
    _same(world.get("ecosystem_dynamics_model"), expected_model, "ecosystem_dynamics_model")
    _need(expected_model.get("model") == V5_NAME, "v5 contract required")
    patches, summary, records = _reconstruct(world)
    for cell, patch in zip(world["cells"], patches):
        for key, expected in patch.items():
            _same(cell.get(key), expected, f"cell {cell['id']}.{key}")
    for key, expected in summary.items():
        _same(world.get("summary", {}).get(key), expected, "summary." + key)
    for key, expected in records.items():
        _same(world.get(key), expected, key)


def validate_prescribed_natural_ecosystem(world: dict[str, Any]) -> list[str]:
    try:
        audit_prescribed_natural_ecosystem(world)
        return []
    except PrescribedNaturalEcosystemError as exc:
        return [str(exc)[:600]]
    except (TypeError, ValueError, KeyError, ArithmeticError, AttributeError) as exc:
        return ["prescribed natural ecosystem: malformed or unrepresentable source/output (" + type(exc).__name__ + ")"]
