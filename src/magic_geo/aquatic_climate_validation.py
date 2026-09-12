"""Independent validation of versioned annual ecosystem-proxy applicability.

These checks deliberately do not import ecosystem producer helpers/constants.
Direct climate support and derived fishery support are different: unsupported
primary productivity's numeric zero is not a known upstream productivity input.
Missing model metadata alone retains legacy structural validation.
"""

from __future__ import annotations

from typing import Any


_FISHERY_WATER_TYPES = {"continental_shelf", "fresh_lake", "inland_sea", "ocean"}
_EXPECTED_V2_MODEL = {
    "model": "heuristic_ecosystem_climate_support_v2",
    "aquatic_temperature_source": "annual_surface_air_climate_proxy",
    "aquatic_selector": "is_water_or_is_lake_or_fishery_water_body_type",
    "fishery_water_body_types": ["continental_shelf", "fresh_lake", "inland_sea", "ocean"],
    "aquatic_primary_minimum_temperature_c": -16.0,
    "aquatic_primary_maximum_temperature_c": 52.0,
    "fishery_minimum_temperature_c": -20.0,
    "fishery_maximum_temperature_c": 44.0,
    "temperature_bounds": "exclusive",
    "support_relationship": "fishery_estimate_requires_own_climate_and_supported_primary_input",
    "monthly_temperature_policy": "not_used",
    "invalid_annual_temperature_policy": "unsupported_without_numeric_coercion",
    "unsupported_productivity_policy": "numeric_zero_with_false_support_flag",
    "unsupported_fishery_record_policy": "no_record_without_supported_fishery_productivity",
    "support_scope": "empirical_climate_proxy_not_aquatic_survival_limits",
}
_EXPECTED_MODELS = {
    "heuristic_ecosystem_climate_support_v2": _EXPECTED_V2_MODEL,
    "heuristic_ecosystem_climate_support_v3": {
        **_EXPECTED_V2_MODEL,
        "model": "heuristic_ecosystem_climate_support_v3",
        "aquatic_ecology_policy": "shared_aquatic_selector_for_primary_and_terrestrial_exclusion",
    },
}
_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"] = {
    **_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v3"],
    "model": "heuristic_ecosystem_climate_support_v4",
    "terrestrial_temperature_source": "annual_surface_air_climate_proxy",
    "terrestrial_selector": "complement_of_shared_aquatic_selector",
    "terrestrial_primary_minimum_temperature_c": -16.0,
    "terrestrial_primary_maximum_temperature_c": 52.0,
    "terrestrial_support_scope": "existing_annual_primary_proxy_not_plant_survival_biome_phenology_crop_or_fuel_limits",
    "primary_availability_policy": "supported_aquatic_or_terrestrial_climate_input",
    "terrestrial_dependency_policy": "biomass_requires_supported_terrestrial_primary_forest_and_succession_require_supported_primary_biomass_and_disturbance",
    "unsupported_terrestrial_estimate_policy": "numeric_zero_with_false_support_flag_not_observed_physical_zero",
    "unsupported_terrestrial_succession_policy": "terrestrial_primary_proxy_unavailable_zero_recovery_years_no_history",
    "unsupported_forest_record_policy": "no_record_without_supported_forest_growth",
    "summary_availability_policy": "all_cell_means_include_unavailable_zero_sentinels_with_supported_cell_counts",
    "species_richness_availability_policy": "requires_supported_primary_and_terrestrial_biomass_or_aquatic_structural_zero",
    "ecosystem_wildfire_availability_policy": "requires_supported_terrestrial_biomass_aquatic_risk_is_known_zero",
    "ecosystem_disturbance_availability_policy": "requires_supported_ecosystem_wildfire_risk_aquatic_descriptors_remain_applicable",
    "vegetation_recovery_availability_policy": "requires_supported_primary_and_disturbance_and_terrestrial_biomass_or_aquatic_structural_zero",
    "renewable_record_availability_policy": "requires_supported_resource_productivity_primary_disturbance_recovery_and_terrestrial_biomass_or_aquatic_structural_zero",
    "unsupported_parent_estimate_policy": "numeric_zero_with_false_support_flag_not_absence_damage_or_physical_nonburnability",
    "ecosystem_disturbance_input_scope": "static_empirical_fire_frequency_aridity_ecotone_erosion_settlement_wind_descriptors_not_observed_fire_or_final_wildfire_feedback",
    "aquatic_biomass_input_policy": "structural_zero_for_aquatic_richness_recovery_and_renewable_inputs_not_terrestrial_biomass_estimate",
}


_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v5"] = {
    **_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"],
    "model": "heuristic_ecosystem_climate_support_v5",
    "ecosystem_disturbance_input_scope": "static_empirical_fire_frequency_aridity_ecotone_erosion_wind_descriptors_not_observed_fire_or_final_wildfire_feedback",
    "activity_forcing_policy": "prescribed_natural_scenario_without_anthropogenic_activity_input",
    "settlement_score_input_policy": "not_read_omitted_without_substitute_or_renormalization",
    "activity_scope": "scenario_boundary_not_inferred_absence_of_people_or_observed_fire",
    "physical_input_policy": "explicit_finite_nonboolean_descriptors_and_typed_habitat_biome_sources_no_missing_value_substitution",
}


def _inside(value: Any, minimum: float, maximum: float) -> bool:
    # Bounds reject NaN/infinities and enormous integers without overflowing
    # a float conversion. Numeric strings and booleans are not source values.
    return isinstance(value, (int, float)) and not isinstance(value, bool) and minimum < value < maximum


def _numeric_zero(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0.0


_V4_ONLY_FLAGS = (
    "terrestrial_primary_climate_supported", "primary_productivity_supported",
    "vegetation_biomass_supported", "forest_growth_supported", "vegetation_succession_supported",
    "species_richness_supported", "ecosystem_wildfire_spread_risk_supported",
    "ecosystem_disturbance_pressure_supported", "vegetation_recovery_supported",
)


def validate_aquatic_climate_support(world: dict[str, Any]) -> list[str]:
    """Check v2/v3 aquatic policies and v4's terrestrial primary dependencies.

    The historical entry-point name is retained for existing CLI/subsystem
    callers. No producer eligibility function or model constant is imported.
    """
    if not isinstance(world, dict):
        return ["aquatic climate support requires a world object"]
    model = world.get("ecosystem_dynamics_model")
    model_name = model.get("model") if isinstance(model, dict) else None
    if model_name == "heuristic_ecosystem_climate_support_v5":
        from .prescribed_natural_ecosystem_validation import validate_prescribed_natural_ecosystem
        return validate_prescribed_natural_ecosystem(world)
    if model_name != "heuristic_ecosystem_climate_support_v4":
        cells = world.get("cells")
        summary = world.get("summary")
        if ((isinstance(cells, list) and any(isinstance(c, dict) and any(k in c for k in _V4_ONLY_FLAGS) for c in cells))
                or (isinstance(summary, dict) and any(k + "_cell_count" in summary for k in _V4_ONLY_FLAGS))):
            return ["ecosystem parent availability fields require the exact ecosystem v4 declaration"]
    if "ecosystem_dynamics_model" not in world:
        return []
    expected_model = _EXPECTED_MODELS.get(model_name) if isinstance(model_name, str) else None
    if expected_model is None or model.keys() != expected_model.keys():
        return ["aquatic climate model metadata is missing fields, malformed, or unsupported"]
    errors: list[str] = []
    for key, expected in expected_model.items():
        observed = model[key]
        if observed != expected or (isinstance(expected, float) and (
            not isinstance(observed, (int, float)) or isinstance(observed, bool)
        )):
            errors.append(f"aquatic climate model metadata has invalid {key}")
    if errors:
        return errors

    cells = world.get("cells")
    if not isinstance(cells, list) or any(not isinstance(cell, dict) for cell in cells):
        return ["aquatic climate support requires a valid cell list"]
    check_terrestrial = model_name == "heuristic_ecosystem_climate_support_v4"
    check_aquatic_ecology = model_name in {
        "heuristic_ecosystem_climate_support_v3", "heuristic_ecosystem_climate_support_v4",
    }
    derived_support_by_id: dict[int, bool] = {}
    terrestrial_support_by_id: dict[int, bool] = {}
    forest_support_by_id: dict[int, bool] = {}
    succession_support_by_id: dict[int, bool] = {}
    renewable_parent_support_by_id: dict[int, bool] = {}
    expected_support_counts = dict.fromkeys(_V4_ONLY_FLAGS, 0)
    aquatic_cell_ids: set[int] = set()
    for cell in cells:
        cell_id = cell.get("id")
        water_type = cell.get("water_body_type", "land")
        fishery_water = isinstance(water_type, str) and water_type in _FISHERY_WATER_TYPES
        aquatic = bool(cell.get("is_water", False)) or bool(cell.get("is_lake", False)) or fishery_water
        temperature = cell.get("temperature_c")
        primary_supported = aquatic and _inside(temperature, -16.0, 52.0)
        terrestrial_supported = not aquatic and _inside(temperature, -16.0, 52.0)
        own_fishery_supported = fishery_water and _inside(temperature, -20.0, 44.0)
        derived_supported = primary_supported and own_fishery_supported
        # Reconstruct each parent relationship from original habitat/climate
        # inputs, never from potentially forged producer availability flags.
        any_primary_supported = primary_supported or terrestrial_supported
        biomass_supported = terrestrial_supported
        biomass_input_known = aquatic or biomass_supported
        risk_supported = aquatic or biomass_supported
        disturbance_supported = risk_supported
        richness_supported = any_primary_supported and biomass_input_known
        recovery_supported = any_primary_supported and biomass_input_known and disturbance_supported
        forest_supported = terrestrial_supported and biomass_supported and disturbance_supported
        succession_supported = forest_supported
        expected_flags = {
            "aquatic_climate_proxy_applicable": aquatic,
            "aquatic_primary_climate_supported": primary_supported,
            "fishery_climate_supported": own_fishery_supported,
            "fishery_productivity_supported": derived_supported,
        }
        if check_terrestrial:
            expected_flags.update({
                "terrestrial_primary_climate_supported": terrestrial_supported,
                "primary_productivity_supported": any_primary_supported,
                "vegetation_biomass_supported": biomass_supported,
                "forest_growth_supported": forest_supported,
                "vegetation_succession_supported": succession_supported,
                "species_richness_supported": richness_supported,
                "ecosystem_wildfire_spread_risk_supported": risk_supported,
                "ecosystem_disturbance_pressure_supported": disturbance_supported,
                "vegetation_recovery_supported": recovery_supported,
            })
        for flag, expected in expected_flags.items():
            if cell.get(flag) is not expected:
                prefix = "terrestrial primary support" if flag in expected_support_counts else "aquatic climate support"
                errors.append(f"{prefix} cell {cell_id}: {flag} mismatch")
            if check_terrestrial and flag in expected_support_counts:
                expected_support_counts[flag] += int(expected)
        if check_terrestrial:
            for field, available in (
                ("species_richness_index", richness_supported),
                ("wildfire_spread_risk_index", risk_supported),
                ("ecosystem_disturbance_pressure_index", disturbance_supported),
            ):
                if not available and not _numeric_zero(cell.get(field)):
                    errors.append(f"ecosystem parent support cell {cell_id}: unsupported {field} must be numeric zero")
            recovery = cell.get("vegetation_recovery_years")
            if not recovery_supported:
                if type(recovery) is not int or recovery != 0:
                    errors.append(f"ecosystem parent support cell {cell_id}: recovery years must be integer zero unavailable sentinel")
            elif type(recovery) is not int or recovery < 1:
                errors.append(f"ecosystem parent support cell {cell_id}: supported recovery years must be a positive integer")
        if check_terrestrial and not aquatic and not terrestrial_supported:
            for field in ("primary_productivity_index", "vegetation_biomass_index", "forest_growth_index"):
                if not _numeric_zero(cell.get(field)):
                    errors.append(f"terrestrial primary support cell {cell_id}: unsupported {field} must be numeric zero")
            if cell.get("vegetation_succession_stage") != "terrestrial_primary_proxy_unavailable":
                errors.append(f"terrestrial primary support cell {cell_id}: succession must be unavailable")
        if aquatic and not primary_supported and not _numeric_zero(cell.get("primary_productivity_index")):
            errors.append(f"aquatic climate support cell {cell_id}: unsupported primary_productivity_index must be numeric zero")
        if not derived_supported and not _numeric_zero(cell.get("fishery_productivity_index")):
            errors.append(f"aquatic climate support cell {cell_id}: unsupported fishery_productivity_index must be numeric zero")
        if type(cell_id) is int:
            if check_terrestrial and (cell_id < 0 or cell_id in terrestrial_support_by_id):
                errors.append("terrestrial primary support requires unique nonnegative integer cell IDs")
            terrestrial_support_by_id[cell_id] = terrestrial_supported
            forest_support_by_id[cell_id] = forest_supported
            succession_support_by_id[cell_id] = succession_supported and risk_supported
            renewable_parent_support_by_id[cell_id] = recovery_supported
            derived_support_by_id[cell_id] = derived_supported
            if aquatic:
                aquatic_cell_ids.add(cell_id)
        elif check_terrestrial:
            errors.append("terrestrial primary support requires unique nonnegative integer cell IDs")
        if check_aquatic_ecology and aquatic:
            for field in ("vegetation_biomass_index", "forest_growth_index", "wildfire_spread_risk_index"):
                if not _numeric_zero(cell.get(field)):
                    errors.append(f"aquatic ecology cell {cell_id}: {field} must be numeric zero")
            if cell.get("vegetation_succession_stage") != "aquatic_primary_productivity":
                errors.append(f"aquatic ecology cell {cell_id}: vegetation_succession_stage must be aquatic_primary_productivity")

    if check_terrestrial:
        summary = world.get("summary")
        if not isinstance(summary, dict):
            errors.append("terrestrial primary support requires a summary with availability counts")
        else:
            for flag, expected in expected_support_counts.items():
                field = flag + "_cell_count"
                if type(summary.get(field)) is not int or summary[field] != expected:
                    errors.append(f"terrestrial primary support summary: {field} mismatch")

    if check_aquatic_ecology:
        histories = world.get("vegetation_succession_histories")
        if not isinstance(histories, list):
            errors.append("aquatic ecology requires a valid succession history list")
        else:
            for history in histories:
                if not isinstance(history, dict):
                    errors.append("aquatic ecology requires valid succession histories")
                    continue
                cell_id = history.get("cell_id")
                if check_terrestrial and (
                    type(cell_id) is not int or not succession_support_by_id.get(cell_id, False)
                ):
                    errors.append(f"terrestrial primary support succession history {history.get('id')}: unsupported source cell {cell_id}")
                if type(cell_id) is int and cell_id in aquatic_cell_ids:
                    errors.append(f"aquatic ecology succession history {history.get('id')}: aquatic source cell {cell_id}")

    records = world.get("renewable_resource_records")
    if not isinstance(records, list):
        errors.append("aquatic climate support requires a valid renewable record list")
        return errors
    for record in records:
        if not isinstance(record, dict):
            errors.append("aquatic climate support requires valid renewable records")
            continue
        resource_type = record.get("resource_type")
        if not isinstance(resource_type, str):
            errors.append(f"aquatic climate support renewable record {record.get('id')}: resource_type must be a string")
            continue
        cell_id = record.get("cell_id")
        if check_terrestrial and record.get("resource_type") == "forest_growth" and (
            type(cell_id) is not int or not forest_support_by_id.get(cell_id, False)
        ):
            errors.append(f"terrestrial primary support forest record {record.get('id')}: unsupported source cell {cell_id}")
        if check_terrestrial and resource_type in {"forest_growth", "fishery_productivity"} and (
            type(cell_id) is not int or not renewable_parent_support_by_id.get(cell_id, False)
        ):
            errors.append(f"ecosystem parent support renewable record {record.get('id')}: unsupported source cell {cell_id}")
        if (
            check_aquatic_ecology and record.get("resource_type") == "forest_growth"
            and type(cell_id) is int and cell_id in aquatic_cell_ids
        ):
            errors.append(f"aquatic ecology forest record {record.get('id')}: aquatic source cell {cell_id}")
        if record.get("resource_type") != "fishery_productivity":
            continue
        if type(cell_id) is not int or not derived_support_by_id.get(cell_id, False):
            errors.append(
                f"aquatic climate support fishery record {record.get('id')}: unsupported source cell {cell_id}"
            )
    return errors
