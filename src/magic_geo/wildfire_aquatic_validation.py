"""Independent versioned validation of terrestrial wildfire's water exclusion.

No producer constants or habitat helpers are imported. An absent model key
alone keeps the legacy structural path; a present declaration must be exact.
The current history schema records ignition, affected cells and active/new
fronts, rather than explicit spread edges or per-cell severity/burn fractions.
"""

from __future__ import annotations

from typing import Any
import math
from collections import Counter

from .climate_model_dispatch import ecology_uses_native_seasonal_climate
from .aquatic_climate_validation import _EXPECTED_MODELS as _ECOSYSTEM_MODELS


_AQUATIC_WATER_TYPES = {"ocean", "continental_shelf", "inland_sea", "fresh_lake"}
_EXPECTED_MODEL = {
    "model": "heuristic_wildfire_aquatic_exclusion_v2",
    "aquatic_selector": "is_water_or_is_lake_or_fishery_water_body_type",
    "aquatic_fire_policy": "zero_fuel_ignition_and_spread_non_burnable_no_history",
    "neighbor_fuel_policy": "terrestrial_biomass_neighbors",
    "ignition_model": "legacy_energy_aridity_fuel_wind_settlement_proxy_v1",
}
_NATIVE_MODEL = {
    **_EXPECTED_MODEL,
    "model": "heuristic_wildfire_native_seasonal_v3",
    "ignition_model": "aridity_fuel_wind_settlement_susceptibility_without_energy_stress_v1",
    "lightning_model": "not_modelled",
    "energy_stress_input_policy": "omitted_without_substitute",
    "remaining_ignition_weights": "unchanged_without_renormalization",
    "history_interpretation": "heuristic_disturbance_scenario_not_observed_fire_or_lightning",
    "climate_input_policy": "requires_known_native_identity_and_upstream_energy_enrichment",
}


def _native_ignition_error(cell: dict[str, Any]) -> str | None:
    def finite(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError
        value = float(value)
        if not math.isfinite(value):
            raise ValueError
        return value

    def bounded(value: Any) -> float:
        value = finite(value)
        return max(0.0, min(1.0, value))

    try:
        expected = bounded(
            bounded(cell.get("wildfire_spread_risk_index", 0.0)) * 0.34
            + bounded(cell["wildfire_fuel_continuity_index"]) * 0.28
            + bounded(cell.get("seasonal_aridity_index", 0.0)) * 0.16
            + bounded(cell.get("ecosystem_disturbance_pressure_index", 0.0)) * 0.10
            + bounded(cell["wildfire_wind_alignment_index"]) * 0.08
            + bounded(cell.get("settlement_score", 0.0)) * 0.08
            - bounded(cell["wildfire_firebreak_index"]) * 0.18
            - bounded(finite(cell.get("ice_thickness_m", 0.0)) / 500.0) * 0.18
        )
        actual = cell.get("wildfire_ignition_potential_index")
        # Six-decimal fuel/wind/firebreak errors contribute <=0.27e-6; output
        # rounding contributes <=0.5e-6. No solver tolerance enters this check.
        if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not 0.0 <= actual <= 1.0 or abs(actual - expected) > 1e-6:
            return f"wildfire native cell {cell.get('id')}: ignition must omit energy stress without renormalizing weights"
    except (KeyError, TypeError, ValueError, OverflowError):
        return f"wildfire native cell {cell.get('id')}: invalid ignition replay inputs"
    return None


def _numeric_equal(value: Any, expected: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == expected


def _validate_wildfire_historical(world: dict[str, Any]) -> list[str]:
    if not isinstance(world, dict):
        return ["wildfire availability requires a world object"]
    parent = world.get("ecosystem_dynamics_model")
    if "ecosystem_dynamics_model" in world:
        parent_name = parent.get("model") if isinstance(parent, dict) else None
        parent_expected = _ECOSYSTEM_MODELS.get(parent_name) if isinstance(parent_name, str) else None
        if parent_expected is None or parent != parent_expected:
            return ["wildfire availability: unknown or partial ecosystem parent"]
    markers = ("terrestrial_primary_climate_supported", "primary_productivity_supported", "vegetation_biomass_supported",
        "ecosystem_wildfire_spread_risk_supported", "ecosystem_disturbance_pressure_supported",
        "wildfire_fuel_continuity_supported", "wildfire_firebreak_supported", "wildfire_ignition_potential_supported")
    cells = world.get("cells")
    if (not isinstance(parent, dict) or parent.get("model") != "heuristic_ecosystem_climate_support_v4") and isinstance(cells, list) and any(isinstance(c, dict) and any(k in c for k in markers) for c in cells):
        return ["wildfire availability: parent availability fields require the ecosystem v4 declaration"]
    if "wildfire_disturbance_model" not in world:
        if isinstance(parent, dict) and parent.get("model") == "heuristic_ecosystem_climate_support_v4":
            return ["wildfire availability: ecosystem v4 requires the parent-aware fire contract"]
        return []
    try:
        native = ecology_uses_native_seasonal_climate(world)
    except ValueError as error:
        return [f"wildfire aquatic climate dependency: {error}"]
    model = world["wildfire_disturbance_model"]
    name = model.get("model") if isinstance(model, dict) else None
    if name in ("heuristic_wildfire_parent_availability_v4", "heuristic_wildfire_native_seasonal_parent_availability_v5"):
        return _validate_parent_fire(world, native)
    parent = world.get("ecosystem_dynamics_model")
    if isinstance(parent, dict) and parent.get("model") == "heuristic_ecosystem_climate_support_v4":
        return ["wildfire availability: ecosystem v4 requires the parent-aware fire contract"]
    expected_model = _NATIVE_MODEL if native else _EXPECTED_MODEL
    model = world["wildfire_disturbance_model"]
    if not isinstance(model, dict) or model.keys() != expected_model.keys():
        return ["wildfire aquatic model metadata is missing fields, malformed, or unsupported"]
    errors = [
        f"wildfire aquatic model metadata has invalid {key}"
        for key, expected in expected_model.items() if model[key] != expected
    ]
    if errors:
        return errors

    cells = world.get("cells")
    if not isinstance(cells, list) or any(not isinstance(cell, dict) for cell in cells):
        return ["wildfire aquatic exclusion requires a valid cell list"]
    cells_by_id: dict[int, dict[str, Any]] = {}
    aquatic_ids: set[int] = set()
    for cell in cells:
        cell_id = cell.get("id")
        if type(cell_id) is not int or cell_id < 0 or cell_id in cells_by_id:
            errors.append("wildfire aquatic exclusion requires unique nonnegative integer cell IDs")
        else:
            cells_by_id[cell_id] = cell
        water_type = cell.get("water_body_type", "land")
        aquatic = (
            bool(cell.get("is_water", False)) or bool(cell.get("is_lake", False))
            or (isinstance(water_type, str) and water_type in _AQUATIC_WATER_TYPES)
        )
        if not aquatic:
            if native:
                error = _native_ignition_error(cell)
                if error:
                    errors.append(error)
            continue
        if type(cell_id) is int and cell_id >= 0:
            aquatic_ids.add(cell_id)
        for field, expected in (
            ("wildfire_fuel_continuity_index", 0.0),
            ("wildfire_ignition_potential_index", 0.0),
            ("wildfire_firebreak_index", 1.0),
        ):
            if not _numeric_equal(cell.get(field), expected):
                errors.append(f"wildfire aquatic cell {cell_id}: {field} must be numeric {expected:g}")
        if cell.get("wildfire_disturbance_regime") != "non_burnable_water":
            errors.append(f"wildfire aquatic cell {cell_id}: regime must be non_burnable_water")
        if cell.get("wildfire_spread_history_ids") != []:
            errors.append(f"wildfire aquatic cell {cell_id}: history IDs must be an empty list")

    def check_reference(value: Any, context: str) -> None:
        if type(value) is not int or value not in cells_by_id:
            errors.append(f"wildfire aquatic {context}: invalid source cell {value}")
        elif value in aquatic_ids:
            errors.append(f"wildfire aquatic {context}: aquatic source cell {value}")

    def check_references(value: Any, context: str) -> None:
        if not isinstance(value, list):
            errors.append(f"wildfire aquatic {context}: requires a cell ID list")
            return
        for cell_id in value:
            check_reference(cell_id, context)

    histories = world.get("wildfire_spread_histories")
    if not isinstance(histories, list):
        errors.append("wildfire aquatic exclusion requires a valid history list")
        return errors
    for history in histories:
        if not isinstance(history, dict):
            errors.append("wildfire aquatic exclusion requires valid history records")
            continue
        context = f"history {history.get('id')}"
        check_reference(history.get("ignition_cell_id"), context + " ignition")
        check_references(history.get("cell_ids"), context + " affected cells")
        steps = history.get("steps")
        if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
            errors.append(f"wildfire aquatic {context}: requires valid spread steps")
            continue
        for index, step in enumerate(steps):
            for field in ("newly_burned_cell_ids", "active_front_cell_ids"):
                check_references(step.get(field), f"{context} step {index} {field}")
    return errors


# Independently held exact version declaration; no fire/parent producer imports.
_PARENT_POLICY = {'ecosystem_parent_model': 'heuristic_ecosystem_climate_support_v4',
 'fuel_input_policy': 'own_supported_primary_biomass_ecosystem_risk_and_every_terrestrial_neighbor_biomass',
 'neighbor_availability_policy': 'one_hop_biomass_not_recursive_neighbor_fuel',
 'neighbor_denominator_policy': 'all_declared_neighbors_aquatic_known_excluded_zero_no_renormalization',
 'firebreak_input_policy': 'requires_available_fuel_no_unknown_as_sparse_fuel',
 'ignition_input_policy': 'requires_available_fuel_firebreak_and_own_ecosystem_risk_disturbance',
 'aquatic_availability_policy': 'known_excluded_fuel_zero_ignition_zero_firebreak_one_all_three_supported',
 'unsupported_estimate_policy': 'numeric_zero_with_false_support_flag_not_physical_absence_or_barrier',
 'unsupported_regime': 'fuel_proxy_unavailable_before_ice_or_sparse_fuel_classification_aquatic_rule_independent',
 'spread_input_policy': 'no_seed_or_source_target_spread_comparison_without_available_inputs',
 'front_coverage_policy': 'all_burned_active_front_adjacency_with_explicit_directed_unmodelled_edges',
 'containment_scope': 'coefficient_index_on_modelled_cells_not_physical_containment',
 'summary_availability_policy': 'all_cell_means_include_unavailable_zero_sentinels_with_supported_counts',
 'counter_policy': 'supported_estimates_only_existing_six_decimal_thresholds',
 'fire_support_scope': 'existing_parent_dependent_proxy_no_new_fire_temperature_or_dead_fuel_model'}

_FIRE_FLAGS = ("wildfire_fuel_continuity_supported", "wildfire_firebreak_supported", "wildfire_ignition_potential_supported")


def _validate_parent_fire(world: dict[str, Any], native: bool, *, prescribed_natural: bool = False) -> list[str]:
    """Replay declared parent availability, local formulas and finite scenarios.

    Uses source habitat/annual inputs to reconstruct parent support; never
    imports producer support or spread functions. This is a static proxy replay,
    not physical fire, standing/dead-fuel or atmospheric-energy validation.
    """
    def need(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)

    def number(value: Any) -> float:
        need(type(value) in (int, float), "non-numeric consumed input")
        result = float(value)
        need(math.isfinite(result), "nonfinite consumed input")
        return result

    def clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    def read(cell, name):
        return number(cell.get(name, 0.0))

    def aquatic(cell):
        kind = cell.get("water_body_type", "land")
        return bool(cell.get("is_water", False)) or bool(cell.get("is_lake", False)) or (isinstance(kind, str) and kind in _AQUATIC_WATER_TYPES)

    def close(value, expected, context):
        need(number(value) == round(expected, 6), context)

    def same(actual, expected):
        if isinstance(expected, dict):
            return isinstance(actual, dict) and actual.keys() == expected.keys() and all(same(actual[k], v) for k, v in expected.items())
        if isinstance(expected, list):
            return isinstance(actual, list) and len(actual) == len(expected) and all(same(a, b) for a, b in zip(actual, expected))
        if type(expected) in (bool, int, str):
            return type(actual) is type(expected) and actual == expected
        if isinstance(expected, float):
            return type(actual) in (int, float) and actual == expected
        return actual == expected

    def alignment(a, b):
        lat1, lat2 = math.radians(read(a, "lat_deg")), math.radians(read(b, "lat_deg"))
        delta = math.radians(read(b, "lon_deg")) - math.radians(read(a, "lon_deg"))
        while delta > math.pi: delta -= math.tau
        while delta < -math.pi: delta += math.tau
        east, north = delta * math.cos((lat1 + lat2) * .5), lat2 - lat1
        length = math.hypot(east, north)
        if length <= 0: return 0.0
        east, north = east / length, north / length
        we, wn = read(a, "wind_east"), read(a, "wind_north")
        speed = clamp(math.hypot(we, wn))
        if speed <= 0: return 0.0
        dot = (we * east + wn * north) / max(.000001, math.hypot(we, wn))
        return clamp((dot + 1) * .5) * speed

    try:
        expected_model = {**(_NATIVE_MODEL if native else _EXPECTED_MODEL), **_PARENT_POLICY,
            "model": "heuristic_wildfire_native_seasonal_parent_availability_v5" if native else "heuristic_wildfire_parent_availability_v4"}
        if prescribed_natural:
            expected_model = _NATURAL_FIRE_MODELS[native]
            validate_prescribed_fire_inputs(world, native=native)
        need(world.get("wildfire_disturbance_model") == expected_model, "unknown or partial fire metadata")
        need(world.get("ecosystem_dynamics_model") == _ECOSYSTEM_MODELS["heuristic_ecosystem_climate_support_v5" if prescribed_natural else "heuristic_ecosystem_climate_support_v4"], "unknown or partial ecosystem parent")
        cells = world.get("cells")
        need(isinstance(cells, list) and all(isinstance(c, dict) for c in cells), "invalid cells")
        by_id = {}
        parent = {}
        for c in cells:
            i = c.get("id")
            need(type(i) is int and i >= 0 and i not in by_id, "invalid cell IDs")
            by_id[i] = c
            t = c.get("temperature_c")
            p = isinstance(t, (int, float)) and not isinstance(t, bool) and -16 < t < 52
            b = not aquatic(c) and p
            risk = aquatic(c) or b
            parent[i] = (p, b, risk, risk)
            for flag, field, supported in zip(
                ("primary_productivity_supported", "vegetation_biomass_supported", "ecosystem_wildfire_spread_risk_supported", "ecosystem_disturbance_pressure_supported"),
                ("primary_productivity_index", "vegetation_biomass_index", "wildfire_spread_risk_index", "ecosystem_disturbance_pressure_index"), parent[i]):
                need(type(c.get(flag)) is bool and c[flag] == supported, f"cell {i}: parent {flag}")
                value = number(c.get(field))
                need(0 <= value <= 1 and (supported or value == 0), f"cell {i}: parent {field}")
            if aquatic(c): need(c["vegetation_biomass_index"] == 0, f"cell {i}: aquatic biomass")
            for field in ("seasonal_aridity_index", "wetland_extent_index", "ice_thickness_m", "floodplain_connectivity_index", "wind_east", "wind_north", "lat_deg", "lon_deg", "elevation_m", "area_km2") + (() if prescribed_natural else ("settlement_score",)):
                read(c, field)
            if not native: read(c, "climate_energy_stress_index")
            need(-90 <= read(c, "lat_deg") <= 90 and -180 <= read(c, "lon_deg") <= 180, f"cell {i}: canonical latitude/longitude")
            need("biome" not in c or isinstance(c["biome"], str), f"cell {i}: biome descriptor")
            need(math.isfinite(math.hypot(read(c, "wind_east"), read(c, "wind_north"))), f"cell {i}: finite wind magnitude")
        for i, c in by_id.items():
            ns = c.get("neighbors", [])
            need(isinstance(ns, list) and all(type(j) is int and j in by_id and j != i for j in ns) and len(ns) == len(set(ns)), f"cell {i}: complete neighbor list")

        supports = {}
        raw = {}
        regimes = {}
        for i, c in by_id.items():
            ns = [by_id[j] for j in c.get("neighbors", [])]
            water = aquatic(c)
            fuel_known = water or (all(parent[i][:3]) and all(aquatic(n) or parent[n["id"]][1] for n in ns))
            flags = (fuel_known, fuel_known, water or (fuel_known and parent[i][2] and parent[i][3]))
            supports[i] = flags
            for flag, expected in zip(_FIRE_FLAGS, flags):
                need(type(c.get(flag)) is bool and c[flag] == expected, f"cell {i}: {flag}")
            wind = max((alignment(c, n) for n in ns), default=0.0)
            aridity, wetland, ice = clamp(read(c, "seasonal_aridity_index")), clamp(read(c, "wetland_extent_index")), clamp(read(c, "ice_thickness_m") / 500)
            fuel = 0.0
            if not water and fuel_known:
                fraction = sum(not aquatic(n) and read(n, "vegetation_biomass_index") >= .20 for n in ns) / len(ns) if ns else 0.0
                forest = .10 if "forest" in str(c.get("biome", "")) else 0.0
                grass = .08 if str(c.get("biome", "")) in {"savanna", "temperate_grassland", "mediterranean_scrub"} else 0.0
                fuel = clamp(clamp(read(c, "vegetation_biomass_index")) * .32 + clamp(read(c, "primary_productivity_index")) * .16 + clamp(read(c, "wildfire_spread_risk_index")) * .20 + aridity * .14 + fraction * .12 + forest + grass - wetland * .18 - ice * .34)
            firebreak = 1.0 if water else 0.0
            if not water and flags[1]:
                water_fraction = sum(aquatic(n) for n in ns) / len(ns) if ns else 0.0
                firebreak = clamp(water_fraction * .34 + wetland * .24 + (.18 if bool(c.get("is_river", False)) else 0.0) + clamp(read(c, "floodplain_connectivity_index")) * .12 + ice * .30 + clamp(1 - fuel) * .18)
            ignition = 0.0
            if not water and flags[2]:
                energy = 0.0 if native else clamp(read(c, "climate_energy_stress_index")) * .06
                ignition = clamp(clamp(read(c, "wildfire_spread_risk_index")) * .34 + fuel * .28 + aridity * .16 + clamp(read(c, "ecosystem_disturbance_pressure_index")) * .10 + wind * .08 + (0.0 if prescribed_natural else clamp(read(c, "settlement_score")) * .08) + energy - firebreak * .18 - ice * .18)
            regime = "non_burnable_water" if water else "fuel_proxy_unavailable" if not all(flags) else (
                "ice_or_barren_firebreak" if c.get("biome") == "ice_cap" or read(c, "ice_thickness_m") > 120 else
                "sparse_fuel" if fuel < .12 else "fragmented_firebreak_mosaic" if firebreak >= .55 else
                "wind_driven_crown_fire" if ignition >= .34 and fuel >= .35 and wind >= .35 else
                "seasonal_surface_fire" if ignition >= .28 else "low_fire_activity")
            raw[i] = (ignition, fuel, wind, firebreak)
            regimes[i] = regime
            for field, expected in zip(("wildfire_ignition_potential_index", "wildfire_fuel_continuity_index", "wildfire_wind_alignment_index", "wildfire_firebreak_index"), raw[i]):
                close(c.get(field), expected, f"cell {i}: {field}")
            need(c.get("wildfire_disturbance_regime") == regime, f"cell {i}: regime")

        def coverage(ids):
            unknown, known = set(), set()
            for i in ids:
                for j in by_id[i].get("neighbors", []):
                    (known if aquatic(by_id[j]) or all(supports[j]) else unknown).add((i, j))
            return {
                "front_coverage_status": "partial_unavailable_inputs" if unknown else "complete_for_examined_adjacency",
                "unmodelled_adjacent_cell_ids": sorted({b for _, b in unknown}),
                "unmodelled_front_cell_ids": sorted({a for a, _ in unknown}),
                "unmodelled_front_edges": [{"from_cell_id": a, "to_cell_id": b} for a, b in sorted(unknown)],
                "unmodelled_front_edge_count": len(unknown), "supported_front_edge_count": len(known),
            }

        def spread(i, j):
            a, b = by_id[i], by_id[j]
            if aquatic(a) or aquatic(b): return 0.0
            if not all(supports[i]) or not all(supports[j]): return None
            if regimes[j] == "ice_or_barren_firebreak": return 0.0
            return clamp(read(b, "wildfire_ignition_potential_index") * .26 + read(b, "wildfire_fuel_continuity_index") * .28 + alignment(a, b) * .20 + read(a, "wildfire_fuel_continuity_index") * .08 + (.06 if a.get("biome", "") == b.get("biome", "") else 0) + (.04 if read(b, "elevation_m") <= read(a, "elevation_m") else 0) - read(b, "wildfire_firebreak_index") * .22)

        histories = world.get("wildfire_spread_histories")
        need(isinstance(histories, list) and all(isinstance(h, dict) for h in histories), "invalid histories")
        assigned = set()
        expected_histories = []
        candidates = sorted((i for i in by_id if all(supports[i]) and read(by_id[i], "wildfire_ignition_potential_index") >= .28 and read(by_id[i], "wildfire_fuel_continuity_index") >= .18 and regimes[i] not in {"non_burnable_water", "ice_or_barren_firebreak"}), key=lambda i: (-read(by_id[i], "wildfire_ignition_potential_index"), i))
        for ignition_id in candidates:
            if len(expected_histories) == 96: break
            if ignition_id in assigned: continue
            burned, active = {ignition_id}, {ignition_id}
            step_probabilities = {ignition_id: read(by_id[ignition_id], "wildfire_ignition_potential_index")}
            steps = []
            for step in range(6):
                if step == 0:
                    newly = [ignition_id]; probabilities = [step_probabilities[ignition_id]]
                else:
                    possibles = {}
                    for source in active:
                        for target in by_id[source].get("neighbors", []):
                            if target in burned or target in assigned: continue
                            probability = spread(source, target)
                            if probability is not None and probability >= .30: possibles[target] = max(possibles.get(target, 0), probability)
                    selected = sorted(possibles, key=lambda i: (-possibles[i], i))[:max(0, 96 - len(burned))]
                    newly = sorted(selected); probabilities = [possibles[i] for i in newly]
                    if not newly: break
                    burned.update(newly); active = set(newly)
                    for i in newly: step_probabilities[i] = possibles[i]
                mean_p = sum(probabilities) / len(probabilities) if probabilities else 0
                mean_break = sum(read(by_id[i], "wildfire_firebreak_index") for i in newly) / len(newly)
                steps.append({"step_index": step, "newly_burned_cell_ids": newly, "active_front_cell_ids": sorted(active),
                    "cumulative_burned_cell_count": len(burned), "burned_area_km2": round(sum(max(0.0, read(by_id[i], "area_km2")) for i in sorted(burned)), 6),
                    "mean_spread_probability_index": round(mean_p, 6), "containment_index": round(clamp(mean_break + (1 - mean_p) * .28), 6),
                    **coverage(active), "containment_scope": "coefficient_index_on_modelled_cells_not_physical_containment"})
            member_ids = sorted(burned)
            def average(field): return sum(read(by_id[i], field) for i in member_ids) / len(member_ids)
            biome_counts = Counter(str(by_id[i].get("biome", "unknown")) for i in member_ids)
            regime_counts = Counter(regimes[i] for i in member_ids)
            highest = max(step_probabilities.values())
            expected = {"id": len(expected_histories), "ignition_cell_id": ignition_id, "cell_count": len(member_ids), "cell_ids": member_ids,
                "area_km2": round(sum(max(0.0, read(by_id[i], "area_km2")) for i in member_ids), 6),
                "dominant_biome": sorted(biome_counts, key=lambda key: (-biome_counts[key], key))[0],
                "dominant_disturbance_regime": sorted(regime_counts, key=lambda key: (-regime_counts[key], key))[0],
                "max_spread_probability_index": round(highest, 6), "containment_index": round(clamp(average("wildfire_firebreak_index") * .62 + (1 - highest) * .20), 6),
                "spread_step_count": len(steps), "steps": steps, "disturbance_regime_counts": dict(sorted(regime_counts.items())),
                **coverage(burned), "containment_scope": "coefficient_index_on_modelled_cells_not_physical_containment",
                "spread_limit_reached": len(steps) == 6 or len(burned) == 96}
            for field in ("wildfire_spread_risk_index", "wildfire_ignition_potential_index", "wildfire_fuel_continuity_index", "wildfire_wind_alignment_index", "wildfire_firebreak_index", "ecosystem_disturbance_pressure_index"):
                output = "mean_" + field.removeprefix("wildfire_") if field not in ("wildfire_spread_risk_index", "ecosystem_disturbance_pressure_index") else "mean_" + field
                expected[output] = round(average(field), 6)
            # Centroid is a geometric display descriptor, checked separately by
            # existing generic validators; the availability replay does not
            # manufacture coordinates or claim a new geodesic-centroid model.
            if prescribed_natural:
                total = x = y = z = 0.0
                for i in member_ids:
                    c = by_id[i]
                    weight = max(0.0, read(c, "area_km2")) or 1.0
                    lat, lon = math.radians(read(c, "lat_deg")), math.radians(read(c, "lon_deg"))
                    cosine = math.cos(lat)
                    x += math.cos(lon)*cosine*weight; y += math.sin(lon)*cosine*weight; z += math.sin(lat)*weight; total += weight
                need(all(math.isfinite(v) for v in (x, y, z, total)), "unrepresentable centroid accumulation")
                expected["centroid_lon_deg"] = round(math.degrees(math.atan2(y/total, x/total)), 6)
                expected["centroid_lat_deg"] = round(math.degrees(math.atan2(z/total, math.hypot(x/total, y/total))), 6)
            expected_histories.append(expected); assigned.update(burned)
        need(len(histories) == len(expected_histories), "history count or seed selection")
        for actual, expected in zip(histories, expected_histories):
            if prescribed_natural:
                need(actual.keys() == expected.keys(), "exact history field coverage required")
            for key, value in expected.items():
                need(same(actual.get(key), value), f"history {expected['id']}: {key}")
        for i, c in by_id.items():
            need(same(c.get("wildfire_spread_history_ids"), [h["id"] for h in expected_histories if i in h["cell_ids"]]), f"cell {i}: inverse histories")

        summary = world.get("summary")
        need(isinstance(summary, dict), "summary missing")
        counts = {"wildfire_spread_history_count": len(histories), "wildfire_disturbance_cell_count": len(assigned), "wildfire_spread_step_count": sum(len(h["steps"]) for h in expected_histories),
            "high_wildfire_ignition_potential_cell_count": sum(supports[i][2] and read(c, "wildfire_ignition_potential_index") >= .28 for i, c in by_id.items()),
            "high_wildfire_fuel_continuity_cell_count": sum(supports[i][0] and read(c, "wildfire_fuel_continuity_index") >= .35 for i, c in by_id.items()),
            "high_wildfire_firebreak_cell_count": sum(supports[i][1] and read(c, "wildfire_firebreak_index") >= .55 for i, c in by_id.items()),
            "wildfire_unavailable_cell_count": sum(not all(flags) for flags in supports.values()),
            "wildfire_partial_front_history_count": sum(h["front_coverage_status"] == "partial_unavailable_inputs" for h in expected_histories),
            "wildfire_unmodelled_adjacent_cell_count": len({i for h in expected_histories for i in h["unmodelled_adjacent_cell_ids"]}),
            "wildfire_unmodelled_front_edge_count": sum(h["unmodelled_front_edge_count"] for h in expected_histories),
            "wildfire_supported_front_edge_count": sum(h["supported_front_edge_count"] for h in expected_histories)}
        counts.update({flag + "_cell_count": sum(flags[j] for flags in supports.values()) for j, flag in enumerate(_FIRE_FLAGS)})
        for key, value in counts.items(): need(type(summary.get(key)) is int and summary[key] == value, f"summary {key}")
        need(same(summary.get("wildfire_disturbance_regime_counts"), dict(sorted(Counter(regimes.values()).items()))), "summary regimes")
        for j, field in enumerate(("wildfire_ignition_potential_index", "wildfire_fuel_continuity_index", "wildfire_wind_alignment_index", "wildfire_firebreak_index")):
            close(summary.get("mean_" + field), sum(values[j] for values in raw.values()) / len(cells) if cells else 0, "summary mean " + field)
        close(summary.get("wildfire_total_burned_area_km2"), sum(h["area_km2"] for h in expected_histories), "summary burned area")
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        return [f"wildfire availability: {error}"]
    return []


_NATURAL_ACTIVITY_POLICY = {
    "ecosystem_parent_model": "heuristic_ecosystem_climate_support_v5",
    "activity_forcing_policy": "prescribed_natural_scenario_without_anthropogenic_activity_input",
    "settlement_score_input_policy": "not_read_omitted_without_substitute_or_renormalization",
    "activity_scope": "scenario_boundary_not_inferred_absence_of_people_or_observed_fire",
    "physical_input_policy": "explicit_finite_consumed_descriptors_typed_habitat_and_reciprocal_complete_graph_no_missing_value_substitution",
}
_NATURAL_FIRE_MODELS = {
    False: {**_EXPECTED_MODEL, **_PARENT_POLICY, **_NATURAL_ACTIVITY_POLICY,
        "model": "heuristic_wildfire_prescribed_natural_parent_availability_v6",
        "ignition_model": "legacy_energy_aridity_fuel_wind_prescribed_natural_proxy_without_settlement_v1"},
    True: {**_NATIVE_MODEL, **_PARENT_POLICY, **_NATURAL_ACTIVITY_POLICY,
        "model": "heuristic_wildfire_native_seasonal_prescribed_natural_parent_availability_v7",
        "ignition_model": "aridity_fuel_wind_prescribed_natural_susceptibility_without_settlement_v1"},
}
PRESCRIBED_FIRE_CELL_FIELDS = (*_FIRE_FLAGS, "wildfire_ignition_potential_index",
    "wildfire_fuel_continuity_index", "wildfire_wind_alignment_index", "wildfire_firebreak_index",
    "wildfire_disturbance_regime", "wildfire_spread_history_ids")
PRESCRIBED_FIRE_SUMMARY_FIELDS = (
    "wildfire_spread_history_count", "wildfire_disturbance_cell_count", "wildfire_spread_step_count",
    "high_wildfire_ignition_potential_cell_count", "high_wildfire_fuel_continuity_cell_count",
    "high_wildfire_firebreak_cell_count", "wildfire_total_burned_area_km2",
    "mean_wildfire_ignition_potential_index", "mean_wildfire_fuel_continuity_index",
    "mean_wildfire_wind_alignment_index", "mean_wildfire_firebreak_index",
    "wildfire_disturbance_regime_counts", *(f + "_cell_count" for f in _FIRE_FLAGS),
    "wildfire_unavailable_cell_count", "wildfire_partial_front_history_count",
    "wildfire_unmodelled_adjacent_cell_count", "wildfire_unmodelled_front_edge_count",
    "wildfire_supported_front_edge_count",
)
_NATURAL_FIRE_NUMERIC_INPUTS = (
    "primary_productivity_index", "vegetation_biomass_index", "wildfire_spread_risk_index",
    "ecosystem_disturbance_pressure_index", "seasonal_aridity_index", "wetland_extent_index",
    "ice_thickness_m", "floodplain_connectivity_index", "wind_east", "wind_north",
    "lat_deg", "lon_deg", "elevation_m", "area_km2",
)


def _same_natural_structure(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_same_natural_structure(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_same_natural_structure(a, b) for a, b in zip(actual, expected))
    return actual == expected


def validate_prescribed_fire_inputs(world, *, native):
    from .aquatic_climate_validation import validate_aquatic_climate_support
    def need(ok, message):
        if not ok:
            raise ValueError("prescribed natural wildfire: " + message[:540])
    def finite(value):
        if type(value) not in (int, float):
            return False
        try:
            return math.isfinite(value)
        except OverflowError:
            return False
    need(isinstance(world, dict), "world must be an object")
    need(_same_natural_structure(world.get("ecosystem_dynamics_model"), _ECOSYSTEM_MODELS["heuristic_ecosystem_climate_support_v5"]), "requires exact ecosystem v5 parent")
    errors = validate_aquatic_climate_support(world)
    need(not errors, "invalid ecosystem parent: " + (errors[0] if errors else ""))
    by_id = {c["id"]: c for c in world["cells"]}
    for i, c in by_id.items():
        for field in _NATURAL_FIRE_NUMERIC_INPUTS + (() if native else ("climate_energy_stress_index",)):
            need(finite(c.get(field)), f"cell {i}: explicit finite numeric {field} required")
        for field in ("is_water", "is_lake", "is_river"):
            need(type(c.get(field)) is bool, f"cell {i}: explicit boolean {field} required")
        for field in ("biome", "water_body_type"):
            need(isinstance(c.get(field), str) and bool(c[field].strip()), f"cell {i}: explicit nonempty {field} required")
        need(-90 <= c["lat_deg"] <= 90 and -180 <= c["lon_deg"] <= 180, f"cell {i}: canonical latitude/longitude required")
        need(math.isfinite(math.hypot(c["wind_east"], c["wind_north"])), f"cell {i}: finite wind magnitude required")
        ns = c.get("neighbors")
        need(isinstance(ns, list) and all(type(j) is int and j in by_id and j != i for j in ns) and len(ns) == len(set(ns)), f"cell {i}: explicit complete unique nonself neighbors required")
    for i, c in by_id.items():
        need(all(i in by_id[j]["neighbors"] for j in c["neighbors"]), f"cell {i}: reciprocal neighbors required")


def validate_wildfire_aquatic_exclusion(world: dict[str, Any]) -> list[str]:
    if not isinstance(world, dict):
        return ["wildfire availability requires a world object"]
    model, parent = world.get("wildfire_disturbance_model"), world.get("ecosystem_dynamics_model")
    names = ("heuristic_wildfire_prescribed_natural_parent_availability_v6", "heuristic_wildfire_native_seasonal_prescribed_natural_parent_availability_v7")
    new_own = isinstance(model, dict) and model.get("model") in names
    new_parent = isinstance(parent, dict) and parent.get("model") == "heuristic_ecosystem_climate_support_v5"
    if new_own or new_parent:
        try:
            native = ecology_uses_native_seasonal_climate(world)
            if not _same_natural_structure(model, _NATURAL_FIRE_MODELS[native]):
                return ["prescribed natural wildfire: exact matching fire6/7 declaration required"]
            return [error[:600] for error in _validate_parent_fire(world, native, prescribed_natural=True)[:64]]
        except (TypeError, ValueError, KeyError, ArithmeticError, AttributeError) as error:
            return [("prescribed natural wildfire: " + str(error))[:600]]
    return _validate_wildfire_historical(world)
