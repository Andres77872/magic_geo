"""Independent surface-domain and membership audit for native grounded ice.

This audits the static native contract, not seasonal mass/energy conservation.
The configured-precision thickness is a display mirror; the separately retained
native thickness owns the strict active-member threshold. No producer imports.
"""
from __future__ import annotations

import math
from typing import Any


MODEL = {
    "model_type": "exposed_land_annual_grounded_ice_diagnostic_v1",
    "surface_domain": "nonmarine_nonlake_cells_v1",
    "thickness_model": "annual_cold_moisture_latitude_elevation_proxy_v1",
    "surface_mass_balance_model": "annual_precipitation_temperature_proxy_v1",
    "dynamics_model": "local_downhill_velocity_erosion_proxy_v1",
    "active_membership_model": "eligible_cells_with_thickness_strictly_above_25m_v1",
    "association_model": "active_ice_or_one_edge_adjacent_glacial_terrain_v1",
    "water_context_policy": "lake_glacial_lake_or_marine_fjord_only",
    "active_thickness_field": "grounded_ice_diagnostic_thickness_m",
    "active_thickness_precision": "roundtrip_binary64_decimal_v1",
    "lake_ice_resolved": False,
    "sea_ice_resolved": False,
    "physical_time_resolved": False,
    "water_mass_budget_resolved": False,
    "energy_budget_resolved": False,
    "model_limitation": "static_grounded_ice_diagnostic_without_seasonal_phase_change_perennial_mass_evolution_or_observed_glacier_calibration",
}
RAW_THICKNESS = "grounded_ice_diagnostic_thickness_m"
APPLICABLE = "grounded_ice_surface_applicable"
TRANSPORT_MODEL = "downhill_area_conserving_glacial_sediment_transport_v3"
STABILITY_MODEL = {
    "model_type": "source_guarded_contextual_ice_sheet_stability_diagnostic_v1",
    "source_grounded_ice_model": MODEL["model_type"],
    "cell_scope": "active_members_and_permitted_one_edge_context_associations_v1",
    "equation_model": "legacy_bounded_sheet_history_risk_proxy_v1",
    "physical_time_resolved": False,
}
_ACTIVE_NUMBERS = (
    "ice_thickness_m", RAW_THICKNESS, "ice_surface_mass_balance_m_y",
    "basal_sliding_index", "ice_velocity_m_y", "glacial_erosion_m",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"grounded ice: {message}")


def _typed_equal(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(_typed_equal(actual[k], v) for k, v in expected.items())
    if type(expected) is list:
        return len(actual) == len(expected) and all(_typed_equal(a, e) for a, e in zip(actual, expected))
    return actual == expected


def _number(value: Any, path: str, *, minimum: float | None = None) -> float:
    _require(type(value) in (int, float), f"{path} must be a finite number, not a boolean")
    result = float(value)
    _require(math.isfinite(result), f"{path} must be finite")
    _require(type(value) is not int or result == value, f"{path} integer must be exactly representable")
    _require(minimum is None or result >= minimum, f"{path} is below its domain")
    return result


def _integer(value: Any, path: str, minimum: int = -1) -> int:
    _require(type(value) is int and minimum <= value < 2**31, f"{path} must be a typed integer >= {minimum}")
    return value


def grounded_ice_version(world: dict[str, Any]) -> int:
    """Resolve own identity before inputs; unmarked historical worlds stay old."""
    _require(type(world) is dict, "world must be an object")
    summary = world.get("summary", {})
    _require(type(summary) is dict, "summary must be an object")
    own = world.get("grounded_ice_model")
    history = world.get("glacial_sediment_transport_history", [])
    cells = world.get("cells", [])
    transport = world.get("glacial_sediment_transport_model", {})
    marked = (
        "grounded_ice_model" in world or "grounded_ice_model" in summary
        or "grounded_ice_stability_model" in world or "grounded_ice_stability_model" in summary
        or (type(cells) is list and any(type(c) is dict and (APPLICABLE in c or RAW_THICKNESS in c) for c in cells))
        or (type(transport) is dict and (transport.get("model_type") == TRANSPORT_MODEL or "source_grounded_ice_model" in transport))
        or (type(history) is list and any(type(stage) is dict and type(stage.get("input_cells")) is list and any(type(c) is dict and "is_lake" in c for c in stage["input_cells"]) for stage in history))
    )
    if not marked:
        return 0
    _require(_typed_equal(own, MODEL), "own model must match the complete exact current declaration")
    _require(type(summary.get("grounded_ice_model")) is str and summary["grounded_ice_model"] == MODEL["model_type"], "summary model must match own model")
    if "glacial_sediment_transport_model" in world:
        _require(type(transport) is dict and transport.get("model_type") == TRANSPORT_MODEL and transport.get("source_grounded_ice_model") == MODEL["model_type"], "current grounded ice requires its exact transport successor")
    if "ice_sheet_stability_histories" in world:
        _require("grounded_ice_stability_model" in world, "current stability histories require their own context-scope declaration")
    if "grounded_ice_stability_model" in world or "grounded_ice_stability_model" in summary:
        _require(_typed_equal(world.get("grounded_ice_stability_model"), STABILITY_MODEL), "stability declaration invalid")
        _require(summary.get("grounded_ice_stability_model") == STABILITY_MODEL["model_type"], "stability summary model invalid")
    return 1


def _display_close(actual: float, reference: float, precision: int, *, source_allowance: float = 0.0, terms: int = 1) -> bool:
    # One configured decimal half-unit per rounded source/output, plus a
    # separate finite binary arithmetic/publication bound. No threshold fuzz.
    allowance = 0.5 * 10.0**(-precision) + source_allowance
    allowance += 16 * max(1, terms) * max(math.ulp(actual), math.ulp(reference))
    return math.isfinite(allowance) and abs(actual - reference) <= allowance


def require_grounded_stage_inputs(stage: dict[str, Any]) -> None:
    """Validate v3's stage-local surface domain, never final-cell lake flags."""
    _require(type(stage) is dict and type(stage.get("input_cells")) is list, "v3 transport requires explicit input cells")
    inputs = stage["input_cells"]
    for index, cell in enumerate(inputs):
        _require(type(cell) is dict and _integer(cell.get("cell_id"), "stage cell id", 0) == index, "stage input cells must be ID-indexed objects")
        for flag in ("is_water", "is_lake"):
            _require(type(cell.get(flag)) is bool, f"stage cell {index}.{flag} must be a boolean")
        _require(not (cell["is_water"] and cell["is_lake"]), "stage cell cannot be both native marine and lake")
        ice = _number(cell.get("ice_thickness_m"), "stage ice thickness", minimum=0.0)
        erosion = _number(cell.get("glacial_erosion_m"), "stage glacial erosion", minimum=0.0)
        target = _integer(cell.get("glacier_flow_to_cell_id"), "stage glacier target")
        if cell["is_water"] or cell["is_lake"]:
            _require(ice == 0.0 and erosion == 0.0 and target == -1, "wet stage cell cannot be an active grounded donor")


def require_grounded_ice(world: dict[str, Any], *, diagnostics: bool = True) -> bool:
    """Validate current raw parents before enrichment; return False for old data."""
    if grounded_ice_version(world) == 0:
        return False
    summary = world["summary"]
    precision = _integer(summary.get("output_float_precision"), "output_float_precision", 0)
    _require(precision <= 8, "configured output_float_precision must be within native 0..8; raw precision is separate")
    cells, sheets = world.get("cells"), world.get("ice_sheets")
    _require(type(cells) is list and type(sheets) is list, "explicit cells and ice_sheets lists are required")
    by_id: dict[int, dict[str, Any]] = {}
    for cell in cells:
        _require(type(cell) is dict, "cell must be an object")
        cid = _integer(cell.get("id"), "cell.id", 0)
        _require(cid not in by_id, "duplicate cell id")
        by_id[cid] = cell
        for flag in ("is_water", "is_lake", APPLICABLE):
            _require(type(cell.get(flag)) is bool, f"cell {cid}.{flag} must be a boolean")
        _require(not (cell["is_water"] and cell["is_lake"]), f"cell {cid} cannot be both native marine and lake")
        exposed = not cell["is_water"] and not cell["is_lake"]
        _require(cell[APPLICABLE] is exposed, f"cell {cid} applicability does not match surface")
        for key in _ACTIVE_NUMBERS:
            _number(cell.get(key), f"cell {cid}.{key}", minimum=None if key == "ice_surface_mass_balance_m_y" else 0.0)
        for key in ("area_km2", "moraine_deposition_m", "deglaciation_age_ka"):
            _number(cell.get(key), f"cell {cid}.{key}", minimum=0.0)
        _require(cell["area_km2"] > 0.0, f"cell {cid} must have a positive represented control-volume area")
        for key in ("elevation_m", "lat_deg", "lon_deg", "temperature_c", "precipitation_mm_y"):
            _number(cell.get(key), f"cell {cid}.{key}")
        _require(type(cell.get("landform")) is str, f"cell {cid}.landform must be explicit")
        _integer(cell.get("ice_sheet_id"), f"cell {cid}.ice_sheet_id")
        _integer(cell.get("glacier_flow_to"), f"cell {cid}.glacier_flow_to")
        _require(_display_close(cell["ice_thickness_m"], cell[RAW_THICKNESS], precision), f"cell {cid} displayed thickness differs from native diagnostic")
        if not exposed:
            _require(all(cell[k] == 0.0 for k in _ACTIVE_NUMBERS) and cell["glacier_flow_to"] == -1, f"cell {cid} wet surface has active grounded ice")
        if cell[RAW_THICKNESS] == 0.0:
            _require(all(cell[k] == 0.0 for k in _ACTIVE_NUMBERS) and cell["glacier_flow_to"] == -1, f"cell {cid} ice-free surface has active dynamics")
    _require(list(by_id) == list(range(len(cells))), "native cells must retain sequential ID order")
    for cid, cell in by_id.items():
        neighbors = cell.get("neighbors")
        _require(type(neighbors) is list, f"cell {cid}.neighbors must be explicit")
        _require(all(type(n) is int and n in by_id and n != cid for n in neighbors) and len(set(neighbors)) == len(neighbors), f"cell {cid} invalid neighbors")
        _require(all(type(by_id[n].get("neighbors")) is list and cid in by_id[n]["neighbors"] for n in neighbors), f"cell {cid} nonreciprocal neighbors")
        target = cell["glacier_flow_to"]
        if target >= 0:
            _require(target in neighbors and cell[APPLICABLE] and cell[RAW_THICKNESS] > 0.0, f"cell {cid} invalid grounded donor link")
            _require(by_id[target]["elevation_m"] <= cell["elevation_m"] + 10.0**(-precision), f"cell {cid} uphill grounded donor link")
    active = {cid for cid, c in by_id.items() if c[APPLICABLE] and c[RAW_THICKNESS] > 25.0}
    remaining = set(active)
    components: list[list[int]] = []
    while remaining:
        todo = [min(remaining)]
        remaining.remove(todo[0])
        component: list[int] = []
        while todo:
            cid = todo.pop()
            component.append(cid)
            for neighbor in by_id[cid]["neighbors"]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    todo.append(neighbor)
        components.append(sorted(component))
    _require(len(sheets) == len(components), "sheet count differs from exposed active components")
    component_by_sheet: dict[int, list[int]] = {}
    for members in components:
        assigned = {by_id[cid]["ice_sheet_id"] for cid in members}
        _require(len(assigned) == 1, "active component has inconsistent sheet IDs")
        sid = next(iter(assigned))
        _require(0 <= sid < len(sheets) and sid not in component_by_sheet, "active sheet ID merges disconnected components")
        component_by_sheet[sid] = members
    active_sheet: dict[int, int] = {}
    previous_area: float | None = None
    previous_terms = 0
    for sid, sheet in enumerate(sheets):
        members = component_by_sheet[sid]
        _require(type(sheet) is dict and _integer(sheet.get("id"), "sheet.id", 0) == sid, "sheet ids/order invalid")
        for key in ("mean_surface_mass_balance_m_y", "mean_basal_sliding_index", "mean_ice_velocity_m_y", "retreat_rate_m_y", "accumulation_area_fraction", "mean_moraine_deposition_m", "mean_deglaciation_age_ka", "equilibrium_line_altitude_m"):
            _number(sheet.get(key), f"sheet {sid}.{key}")
        _number(sheet.get("mean_glacial_erosion_m"), f"sheet {sid}.mean_glacial_erosion_m", minimum=0.0)
        _integer(sheet.get("moraine_cell_count"), f"sheet {sid}.moraine_cell_count", 0)
        _require(type(sheet.get("retreat_stage")) is str, f"sheet {sid}.retreat_stage must be explicit")
        _require(_integer(sheet.get("cell_count"), "sheet.cell_count", 0) == len(members), f"sheet {sid} active member count invalid")
        area = math.fsum(by_id[cid]["area_km2"] for cid in members)
        # Native accumulates areas in BFS order; independently summed areas
        # only order components when their rounding intervals are disjoint.
        if previous_area is not None:
            order_allowance = (previous_terms + len(members)) * 0.5e-17 + 16 * (previous_terms + len(members)) * max(math.ulp(area), math.ulp(previous_area))
            _require(previous_area + order_allowance >= area, "sheet areas are out of descending order")
        previous_area, previous_terms = area, len(members)
        weighted = math.fsum(by_id[cid]["area_km2"] * by_id[cid][RAW_THICKNESS] for cid in members)
        expected_mean = weighted / area if area else 0.0
        # Cell areas use fixed 17 decimal places, unlike roundtrip thickness.
        # Bound that source publication separately from sheet-output rounding.
        area_error = math.fsum(0.5e-17 + math.ulp(by_id[cid]["area_km2"]) for cid in members)
        _require(area > area_error, f"sheet {sid} represented area cannot resolve weighted mean")
        mean_area_error = math.fsum((0.5e-17 + math.ulp(by_id[cid]["area_km2"])) * abs(by_id[cid][RAW_THICKNESS] - expected_mean) for cid in members) / (area - area_error)
        for key, expected in (("area_km2", area), ("mean_ice_thickness_m", expected_mean), ("max_ice_thickness_m", max(by_id[cid][RAW_THICKNESS] for cid in members))):
            actual = _number(sheet.get(key), f"sheet {sid}.{key}", minimum=0.0)
            source_allowance = area_error if key == "area_km2" else mean_area_error if key == "mean_ice_thickness_m" else 0.0
            _require(_display_close(actual, expected, precision, source_allowance=source_allowance, terms=len(members)), f"sheet {sid}.{key} active aggregate invalid")
        for cid in members:
            _require(by_id[cid]["ice_sheet_id"] == sid, f"cell {cid} active sheet assignment invalid")
            active_sheet[cid] = sid
    for cid, cell in by_id.items():
        sid = cell["ice_sheet_id"]
        if cid in active:
            continue
        context_allowed = cell[APPLICABLE] or (cell["is_lake"] and cell["landform"] == "glacial_lake") or (cell["is_water"] and cell["landform"] == "fjord")
        neighbors = [n for n in cell["neighbors"] if n in active_sheet]
        if sid >= 0:
            _require(context_allowed and any(active_sheet[n] == sid for n in neighbors), f"cell {cid} context must link a directly adjacent active sheet")
        elif context_allowed and neighbors:
            _require(False, f"cell {cid} direct active context association is missing")
        if sid < 0:
            _require(cell["moraine_deposition_m"] == 0.0 and cell["deglaciation_age_ka"] == 0.0, f"cell {cid} orphan glacial context")
        if diagnostics and not cell[APPLICABLE]:
            for key in ("ice_flowline_flux_km3_y", "ice_flowline_driving_stress_kpa", "ice_flowline_strain_heating_index", "ice_flowline_path_count"):
                if key in cell:
                    _require(type(cell[key]) in (int, float) and not isinstance(cell[key], bool) and cell[key] == 0, f"cell {cid} wet grounded-flow annotation")
            if "glacial_landform_type" in cell:
                _require(cell["glacial_landform_type"] in {"none", "glacial_lake", "fjord"}, f"cell {cid} wet active grounded landform")
    if diagnostics and "ice_flowline_histories" in world:
        flowlines = world["ice_flowline_histories"]
        _require(type(flowlines) is list, "flowline histories must be a list")
        for flowline in flowlines:
            _require(type(flowline) is dict and type(flowline.get("flowline_cell_ids")) is list, "flowline path must be explicit")
            for cid in flowline["flowline_cell_ids"]:
                _require(type(cid) is int and cid in by_id and by_id[cid][APPLICABLE] and by_id[cid][RAW_THICKNESS] > 0.0, "current grounded flowline crosses an ice-free or wet cell")
    if "ice_sheet_count" in summary:
        _require(type(summary["ice_sheet_count"]) is int and summary["ice_sheet_count"] == len(sheets), "summary ice_sheet_count mismatch")
    return True


def validate_grounded_ice(world: dict[str, Any], *, diagnostics: bool = True) -> list[str]:
    try:
        require_grounded_ice(world, diagnostics=diagnostics)
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        return [str(error)]
    return []
