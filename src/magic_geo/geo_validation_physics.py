from __future__ import annotations

import math
from collections import Counter
from typing import Any

from .crust_dry_rock_accounting_validation import (
    validate_crust_dry_rock_accounting,
)
from .crust_material_shadow_validation import validate_crust_material_shadow
from .crust_overlap_candidate_fate_validation import (
    validate_crust_overlap_candidate_fate,
)
from .crust_transport_validation import validate_crust_overlap_transport
from .initial_oceanic_crust_age_validation import (
    validate_initial_oceanic_crust_age,
)
from .oceanic_age_depth_validation import validate_oceanic_age_depth
from .plate_boundary_edge_validation import validate_plate_boundary_edges
from .sediment_source_partition_validation import (
    validate_sediment_source_partitions,
)
from .sediment_interface_validation import validate_sediment_interfaces


SOLAR_CONSTANT_W_M2 = 1361.0
STEFAN_BOLTZMANN_W_M2_K4 = 5.670374419e-8
SURFACE_LONGWAVE_EMISSIVITY = 0.96
MATURATION_REFERENCE_TIMESTEP_MA = 5.0
NOMINAL_TIME_MODEL = "configured_maturation_timestep_nominal_elapsed_time_v1"
NOMINAL_TIME_BASIS = (
    "configured_maturation_timestep_ma_per_erosion_transition_v1"
)
NOMINAL_TIME_SOURCE_PARAMETER = "erosion.maturation_timestep_ma"
ITERATION_PROCESS_ORDER = (
    "{plate_motion->crust_transport->crust_evolution->"
    "precommit_tendency_evaluation[tectonic_elevation+hillslope_sediment+"
    "stream_power_incision;prior_stabilized_surface_hydrology]->"
    "provisional_terrain_composition->fluvial_sediment_routing["
    "prior_flow_graph+provisional_accommodation]->"
    "finite_alluvium_bedrock_inventory_and_terrain_commit->"
    "(sea_level->climate->"
    "causal_water_budget->hydrology->numeric_depression_correction)*"
    "until_stable}*configured_erosion_iterations->cryosphere_state->"
    "glacial_sediment_transport->"
    "finite_alluvium_bedrock_inventory_and_terrain_commit->"
    "(sea_level->climate->causal_water_budget->hydrology->"
    "numeric_depression_correction)*until_stable->cryosphere_state_recompute"
)
EROSION_TRANSITION_COUPLING_SEMANTICS = (
    "hillslope_and_stream_use_prior_stabilized_surface_and_hydrology_with_"
    "updated_crust_state;tectonic_hillslope_stream_tendencies_are_combined_"
    "before_terrain_commit;fluvial_routing_uses_prior_flow_graph_and_"
    "provisional_terrain_accommodation"
)
NOMINAL_TIME_RECORD_FIELDS = frozenset(
    {
        "nominal_time_model",
        "nominal_time_unit",
        "nominal_time_basis",
        "nominal_time_source_parameter",
        "nominal_time_role",
        "nominal_interval_start_ma",
        "nominal_interval_end_ma",
        "nominal_interval_duration_ma",
        "nominal_elapsed_time_ma",
        "advances_nominal_time",
        "nominal_time_calibrated",
        "physical_time_resolved",
    }
)

CRUST_NAMES = (
    "oceanic",
    "continental",
    "transitional",
    "volcanic_arc",
    "craton",
    "orogen",
    "rift_basin",
    "sedimentary_basin",
    "accreted_terrane",
)
LITHOLOGY_NAMES = (
    "basalt",
    "granite",
    "limestone",
    "sandstone",
    "shale",
    "volcanic",
    "metamorphic",
)


def _append_check(
    checks: list[dict[str, Any]],
    *,
    domain: str,
    name: str,
    passed: bool,
    message: str,
    observed: Any,
    expected: Any,
    evidence: dict[str, Any] | None = None,
) -> None:
    checks.append(
        {
            "id": len(checks),
            "domain": domain,
            "name": name,
            "status": "passed" if passed else "failed",
            "passed": passed,
            "severity": "error",
            "message": message,
            "observed": observed,
            "expected": expected,
            "evidence": evidence or {},
        }
    )


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _number(value: Any) -> float | None:
    if not _finite_number(value):
        return None
    return float(value)


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _close(
    actual: Any,
    expected: float,
    *,
    absolute: float = 1.0e-6,
    relative: float = 1.0e-8,
) -> bool:
    value = _number(actual)
    return value is not None and abs(value - expected) <= max(
        absolute, abs(expected) * relative
    )


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _planet_value(world: dict[str, Any], key: str, default: float) -> float:
    parameters = world.get("planet_parameters")
    if not isinstance(parameters, dict):
        return default
    value = _number(parameters.get(key))
    return default if value is None else value


def _unit_vector(value: Any, tolerance: float = 0.01) -> bool:
    if not isinstance(value, list) or len(value) != 3:
        return False
    components = [_number(component) for component in value]
    if any(component is None for component in components):
        return False
    length = math.sqrt(sum(float(component) ** 2 for component in components))
    return abs(length - 1.0) <= tolerance


def _record_violation(violations: list[str], message: str) -> None:
    # Reports remain useful on large worlds without copying thousands of errors.
    if len(violations) < 40:
        violations.append(message)


def _validate_nominal_time_record(
    record: dict[str, Any],
    *,
    label: str,
    expected_start_ma: float,
    expected_end_ma: float,
    expected_role: str,
    violations: list[str],
) -> None:
    missing = NOMINAL_TIME_RECORD_FIELDS - set(record)
    if missing:
        _record_violation(
            violations,
            f"{label} is missing nominal-time fields: {', '.join(sorted(missing))}",
        )

    if (
        record.get("nominal_time_model") != NOMINAL_TIME_MODEL
        or record.get("nominal_time_unit") != "Ma"
        or record.get("nominal_time_basis") != NOMINAL_TIME_BASIS
        or record.get("nominal_time_source_parameter")
        != NOMINAL_TIME_SOURCE_PARAMETER
        or record.get("nominal_time_role") != expected_role
    ):
        _record_violation(violations, f"{label} nominal-time metadata is invalid")

    expected_duration_ma = expected_end_ma - expected_start_ma
    expected_values = {
        "nominal_interval_start_ma": expected_start_ma,
        "nominal_interval_end_ma": expected_end_ma,
        "nominal_interval_duration_ma": expected_duration_ma,
        "nominal_elapsed_time_ma": expected_end_ma,
    }
    for field, expected in expected_values.items():
        if not _close(record.get(field), expected, absolute=1.0e-10, relative=1.0e-12):
            _record_violation(
                violations,
                f"{label} {field} does not match its configured nominal interval",
            )

    advances = expected_duration_ma > 0.0
    if record.get("advances_nominal_time") is not advances:
        _record_violation(
            violations,
            f"{label} advances_nominal_time does not match its interval duration",
        )
    if record.get("nominal_time_calibrated") is not False:
        _record_violation(
            violations, f"{label} must not claim calibrated nominal time"
        )
    if record.get("physical_time_resolved") is not False:
        _record_violation(
            violations, f"{label} must not claim resolved physical time"
        )


def _feedback_stage_clock_position(
    feedback_stage_id: int,
    erosion_iterations: int,
    nominal_timestep_ma: float,
) -> tuple[str, int, float] | None:
    if feedback_stage_id == 0:
        return "initial_climate_hydrology", -1, 0.0
    if 1 <= feedback_stage_id <= erosion_iterations:
        return (
            "erosion_iteration",
            feedback_stage_id,
            feedback_stage_id * nominal_timestep_ma,
        )
    if feedback_stage_id == erosion_iterations + 1:
        return (
            "cryosphere_coupling",
            -1,
            erosion_iterations * nominal_timestep_ma,
        )
    return None


def _validate_stage_end_snapshot_history(
    world: dict[str, Any],
    *,
    key: str,
    role: str,
    erosion_iterations: int,
    nominal_timestep_ma: float,
    require_each_feedback_stage: bool,
    violations: list[str],
) -> list[dict[str, Any]]:
    records = world.get(key)
    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        _record_violation(violations, f"{key} must be a list of objects")
        return []

    seen_feedback_stage_ids: set[int] = set()
    previous_elapsed_ma = -math.inf
    for index, record in enumerate(records):
        label = f"{key}[{index}]"
        if _integer(record.get("id")) != index:
            _record_violation(violations, f"{label} id is not sequential")
        feedback_stage_id = _integer(record.get("feedback_stage_id"))
        if feedback_stage_id is None:
            _record_violation(violations, f"{label} feedback stage id is invalid")
            continue
        position = _feedback_stage_clock_position(
            feedback_stage_id, erosion_iterations, nominal_timestep_ma
        )
        if position is None:
            _record_violation(
                violations, f"{label} lies outside the configured nominal clock"
            )
            continue
        expected_stage, expected_iteration, expected_elapsed_ma = position
        seen_feedback_stage_ids.add(feedback_stage_id)
        if record.get("stage") != expected_stage:
            _record_violation(
                violations, f"{label} stage does not match its feedback stage"
            )
        if _integer(record.get("erosion_iteration")) != expected_iteration:
            _record_violation(
                violations,
                f"{label} erosion iteration does not match its feedback stage",
            )
        _validate_nominal_time_record(
            record,
            label=label,
            expected_start_ma=expected_elapsed_ma,
            expected_end_ma=expected_elapsed_ma,
            expected_role=role,
            violations=violations,
        )
        if expected_elapsed_ma + 1.0e-10 < previous_elapsed_ma:
            _record_violation(
                violations, f"{key} nominal elapsed time is not monotonic"
            )
        previous_elapsed_ma = expected_elapsed_ma

    if require_each_feedback_stage and seen_feedback_stage_ids != set(
        range(erosion_iterations + 2)
    ):
        _record_violation(
            violations,
            f"{key} does not cover every configured feedback-stage endpoint",
        )
    return records


def _validate_interval_transport_history(
    world: dict[str, Any],
    *,
    key: str,
    role: str,
    erosion_iterations: int,
    nominal_timestep_ma: float,
    violations: list[str],
) -> list[dict[str, Any]]:
    records = world.get(key)
    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        _record_violation(violations, f"{key} must be a list of objects")
        return []
    if len(records) != erosion_iterations:
        _record_violation(
            violations,
            f"{key} length does not match configured erosion transitions",
        )
    for index, record in enumerate(records):
        transition_id = index + 1
        label = f"{key}[{index}]"
        if _integer(record.get("id")) != index:
            _record_violation(violations, f"{label} id is not sequential")
        if _integer(record.get("feedback_stage_id")) != transition_id:
            _record_violation(
                violations, f"{label} feedback-stage link is invalid"
            )
        if _integer(record.get("erosion_iteration")) != transition_id:
            _record_violation(
                violations, f"{label} erosion iteration is invalid"
            )
        _validate_nominal_time_record(
            record,
            label=label,
            expected_start_ma=index * nominal_timestep_ma,
            expected_end_ma=transition_id * nominal_timestep_ma,
            expected_role=role,
            violations=violations,
        )
    return records


def _validate_nominal_process_histories(
    world: dict[str, Any],
    *,
    clock: dict[str, Any],
    motion_history: list[dict[str, Any]],
    erosion_iterations: int,
    nominal_timestep_ma: float,
    maturation_timestep_scale: float,
    violations: list[str],
) -> dict[str, int]:
    nominal_elapsed_ma = erosion_iterations * nominal_timestep_ma

    for index, record in enumerate(motion_history):
        label = f"plate_motion_history[{index}]"
        is_initial = index == 0
        expected_iteration = -1 if is_initial else index
        if index > erosion_iterations:
            _record_violation(
                violations, f"{label} lies outside the configured nominal clock"
            )
        if _integer(record.get("id")) != index:
            _record_violation(violations, f"{label} id is not sequential")
        if record.get("stage") != (
            "initial_plate_domains" if is_initial else "plate_motion_iteration"
        ):
            _record_violation(violations, f"{label} stage is invalid")
        if _integer(record.get("erosion_iteration")) != expected_iteration:
            _record_violation(
                violations, f"{label} erosion iteration is invalid"
            )
        _validate_nominal_time_record(
            record,
            label=label,
            expected_start_ma=(index - 1) * nominal_timestep_ma
            if not is_initial
            else 0.0,
            expected_end_ma=index * nominal_timestep_ma,
            expected_role=(
                "initial_plate_state_snapshot"
                if is_initial
                else "plate_motion_transition"
            ),
            violations=violations,
        )

    hydrologic_history = _validate_stage_end_snapshot_history(
        world,
        key="hydrologic_water_budget_history",
        role="stage_end_stabilization_recomputation_snapshot",
        erosion_iterations=erosion_iterations,
        nominal_timestep_ma=nominal_timestep_ma,
        require_each_feedback_stage=True,
        violations=violations,
    )
    numeric_history = _validate_stage_end_snapshot_history(
        world,
        key="numeric_depression_correction_history",
        role="stage_end_stabilization_event",
        erosion_iterations=erosion_iterations,
        nominal_timestep_ma=nominal_timestep_ma,
        require_each_feedback_stage=False,
        violations=violations,
    )
    hillslope_history = _validate_interval_transport_history(
        world,
        key="hillslope_sediment_transport_history",
        role="erosion_interval_bulk_hillslope_transport",
        erosion_iterations=erosion_iterations,
        nominal_timestep_ma=nominal_timestep_ma,
        violations=violations,
    )
    fluvial_history = _validate_interval_transport_history(
        world,
        key="fluvial_sediment_routing_history",
        role="erosion_interval_bulk_fluvial_routing",
        erosion_iterations=erosion_iterations,
        nominal_timestep_ma=nominal_timestep_ma,
        violations=violations,
    )

    glacial_history = world.get("glacial_sediment_transport_history")
    if not isinstance(glacial_history, list) or not all(
        isinstance(record, dict) for record in glacial_history
    ):
        _record_violation(
            violations,
            "glacial_sediment_transport_history must be a list of objects",
        )
        glacial_history = []
    if len(glacial_history) != 1:
        _record_violation(
            violations,
            "glacial sediment history must contain one final cryosphere record",
        )
    for index, record in enumerate(glacial_history):
        label = f"glacial_sediment_transport_history[{index}]"
        if _integer(record.get("id")) != index:
            _record_violation(violations, f"{label} id is not sequential")
        if _integer(record.get("feedback_stage_id")) != erosion_iterations + 1:
            _record_violation(
                violations, f"{label} final cryosphere link is invalid"
            )
        _validate_nominal_time_record(
            record,
            label=label,
            expected_start_ma=nominal_elapsed_ma,
            expected_end_ma=nominal_elapsed_ma,
            expected_role="final_cryosphere_coupling_bulk_transport",
            violations=violations,
        )

    model = world.get("plate_kinematic_model")
    model_required = {
        "model_type",
        "time_unit",
        "physical_time_resolved",
        "nominal_time_calibrated",
        "process_rate_calibration_resolved",
        "time_step_convergence_demonstrated",
        "nominal_time_model",
        "nominal_time_unit",
        "nominal_time_basis",
        "nominal_time_source_parameter",
        "nominal_timestep_ma",
        "reference_timestep_ma",
        "maturation_timestep_scale",
        "timestep_scaling_model",
        "motion_scale_deg_per_step",
        "reference_motion_scale_deg_per_reference_step",
        "effective_motion_scale_deg_per_step",
        "reference_oceanic_crust_aging_ma_per_reference_step",
        "effective_oceanic_crust_aging_ma_per_step",
        "configured_motion_step_count",
        "history_step_count",
        "crust_transport_ledger_format",
        "crust_transport_coverage_model",
        "crust_transport_coverage_histogram_model",
        "crust_categorical_remap_model",
        "crust_categorical_remap_tie_break",
        "oceanic_state_classification_model",
        "transitional_oceanic_provenance_rule",
        "volcanic_arc_oceanic_state_rule",
        "crust_transport_coverage_arrangement_fragment_limit",
        "crust_transport_execution_backend",
        "canonical_crust_mixture_provenance_location",
        "crust_density_unit",
        "density_weighted_crust_volume_unit",
        "density_weighted_crust_volume_to_mass_kg_factor",
        "crust_advection_resolved",
        "crust_volume_conserving_transport",
        "density_weighted_volume_conserving_transport",
        "crust_age_volume_moment_conserving_transport",
        "mass_conserving_crust_transport",
        "mass_conservation_scope",
        "destination_overlap_areas_normalized",
        "tectonic_process_inventory_changes_separately_ledgered",
        "tectonic_process_inventory_ledger_granularity",
        "tectonic_process_reason_resolved_inventory_ledgered",
        "tectonic_process_inventory_ledger_scope",
        "tectonic_process_inventory_attribution_format",
        "tectonic_process_rule_model",
        "tectonic_process_inventory_reason_order",
        "tectonic_process_boundary_input_locations",
        "tectonic_process_internal_heat_input",
        "tectonic_process_geological_age_ga_input",
        "tectonic_activity_formula",
        "tectonic_activity_index",
        "tectonic_process_rule_state_source_sink_accounting_resolved",
        "tectonic_process_source_sink_attribution_resolved",
        "tectonic_process_source_sink_attribution_semantics",
        "tectonic_process_material_provenance_resolved",
        "tectonic_process_attribution_order_dependent",
        "tectonic_process_changed_cell_count_semantics",
        "oceanic_convergence_subduction_proxy_semantics",
        "plate_crossing_accretion_proxy_semantics",
    }
    if not isinstance(model, dict):
        _record_violation(violations, "plate_kinematic_model must be an object")
        model = {}
    else:
        missing = model_required - set(model)
        if missing:
            _record_violation(
                violations,
                f"plate_kinematic_model is missing fields: {', '.join(sorted(missing))}",
            )
    if (
        model.get("model_type") != "rotating_voronoi_plate_domains_v3"
        or model.get("time_unit") != "model_step"
        or model.get("physical_time_resolved") is not False
        or model.get("nominal_time_calibrated") is not False
        or model.get("process_rate_calibration_resolved") is not False
        or model.get("time_step_convergence_demonstrated") is not False
        or model.get("nominal_time_model") != NOMINAL_TIME_MODEL
        or model.get("nominal_time_unit") != "Ma"
        or model.get("nominal_time_basis") != NOMINAL_TIME_BASIS
        or model.get("nominal_time_source_parameter")
        != NOMINAL_TIME_SOURCE_PARAMETER
        or model.get("timestep_scaling_model")
        != "reference_normalized_partial_process_scaling_v1"
        or model.get("crust_transport_ledger_format")
        != "destination_csr_spherical_forward_overlap_v1"
        or model.get("crust_transport_coverage_model")
        != "destination_local_gnomonic_line_arrangement_multiplicity_v1"
        or model.get("crust_transport_coverage_histogram_model")
        != "global_area_by_integer_source_multiplicity_v1"
        or model.get("crust_categorical_remap_model")
        != "joint_crust_type_lithology_dominant_incoming_volume_v1"
        or model.get("crust_categorical_remap_tie_break")
        != "lowest_crust_type_then_lowest_lithology"
        or model.get("oceanic_state_classification_model")
        != "crust_type_with_transitional_lithology_provenance_and_arc_numeric_guard_v2"
        or model.get("transitional_oceanic_provenance_rule")
        != "crust_type_2_is_oceanic_iff_lithology_0_basalt"
        or model.get("volcanic_arc_oceanic_state_rule")
        != "crust_type_3_is_oceanic_iff_age_le_320_ma_thickness_le_18_km_density_ge_2_84"
        or _integer(
            model.get("crust_transport_coverage_arrangement_fragment_limit")
        )
        != 16384
        or model.get("crust_transport_execution_backend") != "cpu"
        or model.get("canonical_crust_mixture_provenance_location")
        != "plate_motion_history[].crust_overlap_ledger"
        or model.get("crust_density_unit") != "g_cm3"
        or model.get("density_weighted_crust_volume_unit") != "g_cm3_km3"
        or not _close(
            model.get("density_weighted_crust_volume_to_mass_kg_factor"),
            1.0e12,
            absolute=1.0e-6,
            relative=1.0e-12,
        )
        or model.get("crust_advection_resolved") is not True
        or model.get("crust_volume_conserving_transport") is not True
        or model.get("density_weighted_volume_conserving_transport") is not True
        or model.get("crust_age_volume_moment_conserving_transport") is not True
        or model.get("mass_conserving_crust_transport") is not True
        or model.get("mass_conservation_scope")
        != "transport_only_before_rule_based_tectonic_processes"
        or model.get("destination_overlap_areas_normalized") is not False
        or model.get("tectonic_process_inventory_changes_separately_ledgered")
        is not True
        or model.get("tectonic_process_inventory_ledger_granularity")
        != "transported_post_and_rule_reason_positive_negative_per_step_v2"
        or model.get("tectonic_process_reason_resolved_inventory_ledgered")
        is not True
        or model.get("tectonic_process_inventory_ledger_scope")
        != "transported_pre_process_to_post_process_with_sequential_rule_attribution"
        or model.get("tectonic_process_inventory_attribution_format")
        != "sequential_rule_extensive_state_delta_v1"
        or model.get("tectonic_process_rule_model")
        != "ordered_thresholded_crust_state_transition_v2"
        or model.get("tectonic_process_inventory_reason_order")
        != [
            "quiet_oceanic_aging",
            "oceanic_ridge_rejuvenation",
            "oceanic_ridge_creation_relaxation",
            "divergent_continental_rifting",
            "oceanic_convergence_subduction_proxy",
            "continental_collision_orogeny",
            "plate_crossing_accretion_proxy",
            "age_bound_enforcement",
            "thickness_bound_enforcement",
            "density_bound_enforcement",
        ]
        or model.get("tectonic_process_boundary_input_locations")
        != [
            "plate_motion_history[].boundary_convergent_by_cell",
            "plate_motion_history[].boundary_divergent_by_cell",
            "plate_motion_history[].boundary_transform_by_cell",
        ]
        or model.get("tectonic_process_rule_state_source_sink_accounting_resolved")
        is not True
        or model.get("tectonic_process_source_sink_attribution_resolved")
        is not False
        or model.get("tectonic_process_source_sink_attribution_semantics")
        != "componentwise_positive_negative_ordered_rule_state_delta_not_physical_material_flux"
        or model.get("tectonic_process_material_provenance_resolved") is not False
        or model.get("tectonic_process_attribution_order_dependent") is not True
        or model.get("tectonic_process_changed_cell_count_semantics")
        != "numeric_age_thickness_density_change_only_excludes_categorical_transitions"
        or model.get("oceanic_convergence_subduction_proxy_semantics")
        != "rule_adds_thickness_and_reduces_age_not_a_crust_removal_flux"
        or model.get("plate_crossing_accretion_proxy_semantics")
        != "extra_continental_convergence_thickening_not_external_reservoir_provenance"
    ):
        _record_violation(violations, "plate kinematic time metadata is invalid")

    for field, expected in (
        ("nominal_timestep_ma", nominal_timestep_ma),
        ("reference_timestep_ma", MATURATION_REFERENCE_TIMESTEP_MA),
        ("maturation_timestep_scale", maturation_timestep_scale),
    ):
        if not _close(model.get(field), expected, absolute=1.0e-12, relative=1.0e-12):
            _record_violation(
                violations, f"plate kinematic {field} does not mirror the clock"
            )
    if _integer(model.get("configured_motion_step_count")) != erosion_iterations:
        _record_violation(
            violations,
            "plate kinematic configured motion steps do not mirror the clock",
        )
    if _integer(model.get("history_step_count")) != len(motion_history):
        _record_violation(
            violations,
            "plate kinematic history step count does not mirror motion history",
        )

    motion_scale = _number(model.get("motion_scale_deg_per_step"))
    reference_motion_scale = _number(
        model.get("reference_motion_scale_deg_per_reference_step")
    )
    effective_motion_scale = _number(
        model.get("effective_motion_scale_deg_per_step")
    )
    reference_aging = _number(
        model.get("reference_oceanic_crust_aging_ma_per_reference_step")
    )
    effective_aging = _number(
        model.get("effective_oceanic_crust_aging_ma_per_step")
    )
    if (
        motion_scale is None
        or reference_motion_scale is None
        or effective_motion_scale is None
        or min(motion_scale, reference_motion_scale, effective_motion_scale) < 0.0
        or not _close(
            effective_motion_scale,
            reference_motion_scale * maturation_timestep_scale,
            absolute=1.0e-12,
            relative=1.0e-12,
        )
        or not _close(
            motion_scale,
            effective_motion_scale,
            absolute=1.0e-12,
            relative=1.0e-12,
        )
    ):
        _record_violation(
            violations,
            "plate kinematic effective/reference motion scales do not replay",
        )
    if (
        reference_aging is None
        or effective_aging is None
        or min(reference_aging, effective_aging) < 0.0
        or not _close(
            effective_aging,
            reference_aging * maturation_timestep_scale,
            absolute=1.0e-12,
            relative=1.0e-12,
        )
    ):
        _record_violation(
            violations,
            "plate kinematic effective/reference oceanic aging scales do not replay",
        )

    # The clock is the canonical config echo; all time-aware model metadata must
    # mirror it rather than silently establishing a second elapsed-time basis.
    if not _close(
        clock.get("final_nominal_elapsed_time_ma"),
        nominal_elapsed_ma,
        absolute=1.0e-10,
        relative=1.0e-12,
    ):
        _record_violation(
            violations, "nominal process histories do not share the clock endpoint"
        )

    return {
        "hydrologic_water_budget_history": len(hydrologic_history),
        "numeric_depression_correction_history": len(numeric_history),
        "hillslope_sediment_transport_history": len(hillslope_history),
        "fluvial_sediment_routing_history": len(fluvial_history),
        "glacial_sediment_transport_history": len(glacial_history),
    }


def _validate_plate_aggregates(
    world: dict[str, Any], checks: list[dict[str, Any]]
) -> None:
    cells = world.get("cells")
    plates = world.get("plates")
    summary = world.get("summary")
    violations: list[str] = []
    maximum_residuals = {
        "area_km2": 0.0,
        "mean_crust_age_ma": 0.0,
        "mean_crust_density": 0.0,
        "mean_crust_thickness_km": 0.0,
        "mean_boundary_activity": 0.0,
        "mean_heat_flow_mw_m2": 0.0,
    }

    if not isinstance(cells, list) or not cells or not all(
        isinstance(cell, dict) for cell in cells
    ):
        _record_violation(violations, "cells must be a non-empty list of objects")
        cells = []
    if not isinstance(plates, list) or not plates or not all(
        isinstance(plate, dict) for plate in plates
    ):
        _record_violation(violations, "plates must be a non-empty list of objects")
        plates = []

    plate_ids: list[int] = []
    for index, plate in enumerate(plates):
        plate_id = _integer(plate.get("id"))
        if plate_id is None:
            _record_violation(violations, f"plate[{index}] id is not an integer")
            continue
        plate_ids.append(plate_id)
        if plate_id != index:
            _record_violation(
                violations, f"plate[{index}] id {plate_id} is not sequential"
            )
    if len(set(plate_ids)) != len(plate_ids):
        _record_violation(violations, "plate ids are duplicated")

    aggregates: dict[int, dict[str, Any]] = {
        plate_id: {
            "count": 0,
            "area": 0.0,
            "age": 0.0,
            "density": 0.0,
            "thickness": 0.0,
            "boundary": 0.0,
            "heat": 0.0,
            "crust_area": {name: 0.0 for name in CRUST_NAMES},
            "lithology_area": {name: 0.0 for name in LITHOLOGY_NAMES},
        }
        for plate_id in plate_ids
    }
    internal_heat = _planet_value(world, "internal_heat", 1.0)
    if not math.isfinite(internal_heat) or internal_heat < 0.0:
        _record_violation(violations, "planet internal_heat is not nonnegative")

    for index, cell in enumerate(cells):
        plate_id = _integer(cell.get("plate_id"))
        if plate_id not in aggregates:
            _record_violation(
                violations, f"cell[{index}] has unknown plate_id {plate_id!r}"
            )
            continue
        numeric_fields = (
            "area_km2",
            "crust_age_ma",
            "crust_density",
            "crust_thickness_km",
            "boundary_convergent",
            "boundary_divergent",
            "boundary_transform",
        )
        values = {field: _number(cell.get(field)) for field in numeric_fields}
        if any(value is None for value in values.values()):
            _record_violation(
                violations, f"cell[{index}] has non-finite plate aggregate inputs"
            )
            continue
        area = float(values["area_km2"])
        age = float(values["crust_age_ma"])
        density = float(values["crust_density"])
        thickness = float(values["crust_thickness_km"])
        convergent = float(values["boundary_convergent"])
        divergent = float(values["boundary_divergent"])
        transform = float(values["boundary_transform"])
        if (
            area <= 0.0
            or age < 0.0
            or density <= 0.0
            or thickness <= 0.0
            or any(
                value < 0.0 or value > 1.0
                for value in (convergent, divergent, transform)
            )
        ):
            _record_violation(
                violations, f"cell[{index}] has out-of-range plate aggregate inputs"
            )

        crust = str(cell.get("crust_type", ""))
        lithology = str(cell.get("lithology", ""))
        if crust not in CRUST_NAMES:
            _record_violation(violations, f"cell[{index}] has unknown crust_type")
        if lithology not in LITHOLOGY_NAMES:
            _record_violation(violations, f"cell[{index}] has unknown lithology")
        boundary = max(convergent, divergent, transform)
        oceanic = (
            crust == "oceanic"
            or (crust == "transitional" and lithology == "basalt")
            or (
                crust == "volcanic_arc"
                and age <= 320.0
                and thickness <= 18.0
                and density >= 2.84
            )
        )
        age_heat = (
            45.0 + 95.0 * math.exp(-age / 60.0)
            if oceanic
            else 38.0 + 34.0 * math.exp(-age / 1400.0)
        )
        boundary_heat = (
            55.0 * divergent
            + 30.0 * convergent
            + 18.0 * transform
            + (24.0 if crust == "volcanic_arc" else 0.0)
        )
        heat = _clamp(internal_heat * (age_heat + boundary_heat), 18.0, 240.0)
        aggregate = aggregates[plate_id]
        aggregate["count"] += 1
        aggregate["area"] += area
        aggregate["age"] += age * area
        aggregate["density"] += density * area
        aggregate["thickness"] += thickness * area
        aggregate["boundary"] += boundary * area
        aggregate["heat"] += heat * area
        if crust in CRUST_NAMES:
            aggregate["crust_area"][crust] += area
        if lithology in LITHOLOGY_NAMES:
            aggregate["lithology_area"][lithology] += area

    required_fields = {
        "id",
        "kind",
        "axis",
        "initial_center",
        "center",
        "angular_speed",
        "cumulative_rotation_deg",
        "crust_density",
        "crust_thickness_km",
        "cell_count",
        "area_km2",
        "mean_crust_age_ma",
        "mean_crust_density",
        "mean_crust_thickness_km",
        "dominant_crust_type",
        "dominant_lithology",
        "mean_boundary_activity",
        "mean_heat_flow_mw_m2",
        "thermal_state",
    }
    geological_age_ma = max(
        0.0, _planet_value(world, "geological_age_ga", 4.5) * 1000.0
    )
    for index, plate in enumerate(plates):
        missing = required_fields - set(plate)
        if missing:
            _record_violation(
                violations,
                f"plate[{index}] is missing fields: {', '.join(sorted(missing))}",
            )
            continue
        plate_id = _integer(plate.get("id"))
        aggregate = aggregates.get(plate_id) if plate_id is not None else None
        if aggregate is None:
            _record_violation(violations, f"plate[{index}] cannot be aggregated")
            continue
        if str(plate.get("kind")) not in {"oceanic", "continental", "mixed"}:
            _record_violation(violations, f"plate[{index}] kind is invalid")
        for vector_field in ("axis", "initial_center", "center"):
            if not _unit_vector(plate.get(vector_field)):
                _record_violation(
                    violations, f"plate[{index}] {vector_field} is not a unit vector"
                )

        positive_fields = (
            "crust_density",
            "crust_thickness_km",
            "area_km2",
            "mean_crust_density",
            "mean_crust_thickness_km",
            "mean_heat_flow_mw_m2",
        )
        for field in positive_fields:
            value = _number(plate.get(field))
            if value is None or value <= 0.0:
                _record_violation(
                    violations, f"plate[{index}] {field} is not finite and positive"
                )
        nonnegative_fields = (
            "angular_speed",
            "cumulative_rotation_deg",
            "mean_crust_age_ma",
        )
        for field in nonnegative_fields:
            value = _number(plate.get(field))
            if value is None or value < 0.0:
                _record_violation(
                    violations, f"plate[{index}] {field} is not finite and nonnegative"
                )
        mean_age = _number(plate.get("mean_crust_age_ma"))
        if mean_age is not None and mean_age > geological_age_ma + 1.0e-4:
            _record_violation(violations, f"plate[{index}] mean crust age exceeds planet age")
        boundary_value = _number(plate.get("mean_boundary_activity"))
        if boundary_value is None or not 0.0 <= boundary_value <= 1.0:
            _record_violation(
                violations, f"plate[{index}] mean boundary activity is out of range"
            )
        heat_value = _number(plate.get("mean_heat_flow_mw_m2"))
        if heat_value is None or not 18.0 <= heat_value <= 240.0:
            _record_violation(violations, f"plate[{index}] heat flow is out of range")

        area = float(aggregate["area"])
        divisor = area if area > 0.0 else 1.0
        expected_values = {
            "area_km2": area,
            "mean_crust_age_ma": float(aggregate["age"]) / divisor,
            "mean_crust_density": float(aggregate["density"]) / divisor,
            "mean_crust_thickness_km": float(aggregate["thickness"]) / divisor,
            "mean_boundary_activity": float(aggregate["boundary"]) / divisor,
            "mean_heat_flow_mw_m2": float(aggregate["heat"]) / divisor,
        }
        tolerances = {
            "area_km2": (1.0, 1.0e-4),
            "mean_crust_age_ma": (0.01, 1.0e-4),
            "mean_crust_density": (0.001, 0.0),
            "mean_crust_thickness_km": (0.01, 0.0),
            "mean_boundary_activity": (0.001, 0.0),
            "mean_heat_flow_mw_m2": (0.01, 1.0e-4),
        }
        for field, expected in expected_values.items():
            actual = _number(plate.get(field))
            residual = math.inf if actual is None else abs(actual - expected)
            maximum_residuals[field] = max(maximum_residuals[field], residual)
            absolute, relative = tolerances[field]
            if not _close(
                plate.get(field), expected, absolute=absolute, relative=relative
            ):
                _record_violation(
                    violations,
                    f"plate[{index}] {field} does not replay from member cells",
                )
        if _integer(plate.get("cell_count")) != aggregate["count"]:
            _record_violation(
                violations, f"plate[{index}] cell_count does not match member cells"
            )
        expected_crust = max(
            CRUST_NAMES, key=lambda name: aggregate["crust_area"][name]
        )
        expected_lithology = max(
            LITHOLOGY_NAMES, key=lambda name: aggregate["lithology_area"][name]
        )
        if plate.get("dominant_crust_type") != expected_crust:
            _record_violation(
                violations, f"plate[{index}] dominant crust type is inconsistent"
            )
        if plate.get("dominant_lithology") != expected_lithology:
            _record_violation(
                violations, f"plate[{index}] dominant lithology is inconsistent"
            )
        if heat_value is not None:
            expected_thermal_state = (
                "hot_active"
                if heat_value >= 95.0
                else ("warm_active" if heat_value >= 65.0 else "cool_stable")
            )
            if plate.get("thermal_state") != expected_thermal_state:
                _record_violation(
                    violations, f"plate[{index}] thermal_state is inconsistent"
                )

    if not isinstance(summary, dict) or _integer(summary.get("plate_count")) != len(
        plates
    ):
        _record_violation(violations, "summary plate_count does not match plates")
    reconstructed_surface_area = sum(
        float(aggregate["area"]) for aggregate in aggregates.values()
    )
    cell_surface_area = sum(
        float(_number(cell.get("area_km2")) or 0.0) for cell in cells
    )
    if not _close(
        reconstructed_surface_area,
        cell_surface_area,
        absolute=0.01,
        relative=1.0e-10,
    ):
        _record_violation(violations, "plate areas do not cover the cell surface")

    _append_check(
        checks,
        domain="tectonics",
        name="plate_aggregate_replay",
        passed=not violations,
        message=(
            "plate counts, areas, area-weighted crust/heat aggregates, categories, "
            "and finite physical fields must replay from assigned cells"
        ),
        observed={
            "cell_count": len(cells),
            "plate_count": len(plates),
            "violation_count": len(violations),
            "maximum_replay_residuals": maximum_residuals,
        },
        expected={
            "all_cells_assigned_once": True,
            "plate_aggregates_match_cells": True,
            "physical_fields_finite_and_nonnegative": True,
        },
        evidence={"violations": violations},
    )


def _surface_albedo(cell: dict[str, Any]) -> tuple[float, str]:
    biome = str(cell.get("biome", "unknown"))
    water_body = str(cell.get("water_body_type", "land"))
    temperature = float(cell.get("temperature_c", 0.0))
    precipitation = float(cell.get("precipitation_mm_y", 0.0))
    seasonal_aridity = _clamp(float(cell.get("seasonal_aridity_index", 0.0)))
    elevation = float(cell.get("elevation_m", 0.0))
    ice = max(0.0, float(cell.get("ice_thickness_m", 0.0)))

    if bool(cell.get("is_water", False)):
        if water_body in {"fresh_lake", "saline_basin", "inland_sea"}:
            base, regime = 0.10, "lake_water"
        elif water_body == "continental_shelf":
            base, regime = 0.08, "shallow_ocean"
        else:
            base, regime = 0.065, "open_ocean"
    elif ice > 20.0 or biome == "ice_cap":
        base = 0.58 + _clamp(ice / 2500.0) * 0.12
        regime = "ice_albedo"
    elif biome in {"tundra", "alpine"}:
        base, regime = (0.34 if temperature < -2.0 else 0.28), "cold_sparse_cover"
    elif biome in {"hot_desert", "cold_desert"}:
        base, regime = (0.36 if biome == "hot_desert" else 0.32), "arid_high_albedo"
    elif biome in {"savanna", "temperate_grassland", "mediterranean_scrub"}:
        base, regime = 0.21, "seasonal_grassland"
    elif "forest" in biome:
        base, regime = (0.14 if biome != "tropical_rainforest" else 0.12), "forest_canopy"
    else:
        base, regime = 0.22, "mixed_land"

    cloud_albedo = _clamp(precipitation / 2800.0) * 0.055 + max(
        0.0, float(cell.get("vertical_velocity_index", 0.0))
    ) * 0.018
    dry_brightening = seasonal_aridity * (
        0.035 if not bool(cell.get("is_water", False)) else 0.0
    )
    snow_brightening = (
        0.08
        if not bool(cell.get("is_water", False))
        and temperature < -3.0
        and precipitation >= 250.0
        else 0.0
    )
    elevation_brightening = (
        _clamp((elevation - 2600.0) / 2600.0) * 0.035
        if elevation > 2600.0
        else 0.0
    )
    return (
        _clamp(
            base
            + 0.055
            + cloud_albedo
            + dry_brightening
            + snow_brightening
            + elevation_brightening,
            0.04,
            0.86,
        ),
        regime,
    )


def _greenhouse_effect_c(
    cell: dict[str, Any], greenhouse_factor: float, pressure_bar: float
) -> float:
    humidity = _clamp(
        float(cell.get("humidity_transport_index", 0.0)) * 0.35
        + (float(cell.get("ocean_current_moisture_factor", 1.0)) - 0.72)
        / 0.56
        * 0.25
        + _clamp(float(cell.get("precipitation_mm_y", 0.0)) / 2600.0) * 0.25
        + _clamp(float(cell.get("vapor_evaporation_mm_y", 0.0)) / 1500.0) * 0.15
    )
    dry_penalty = _clamp(float(cell.get("seasonal_aridity_index", 0.0))) * 2.5
    ice_penalty = _clamp(float(cell.get("ice_thickness_m", 0.0)) / 1800.0) * 3.0
    water_bonus = 1.5 if bool(cell.get("is_water", False)) else 0.0
    return max(
        0.0,
        (
            13.5
            + humidity * 8.0
            + water_bonus
            - dry_penalty
            - ice_penalty
        )
        * greenhouse_factor
        * math.sqrt(max(0.0, pressure_bar)),
    )


def _seasonal_insolation_series(
    latitude_radians: float,
    stellar_luminosity: float,
    axial_tilt_degrees: float,
    orbital_eccentricity: float,
    months: int,
) -> tuple[list[float], list[float]]:
    eccentricity = _clamp(orbital_eccentricity, 0.0, 0.8)
    tilt = _clamp(axial_tilt_degrees, 0.0, 90.0)
    tilt_radians = math.radians(tilt)
    tilt_contrast = 1.0 + (tilt / 90.0 - 23.5 / 90.0) * 0.18
    latitude_factor = 0.46 + 0.72 * max(
        0.0, math.cos(latitude_radians)
    ) * tilt_contrast
    monthly: list[float] = []
    orbital_factors: list[float] = []
    for month in range(max(1, months)):
        season_angle = 2.0 * math.pi * (float(month) - 5.5) / max(1, months)
        declination = tilt_radians * math.cos(season_angle)
        seasonal_latitude_factor = _clamp(
            1.0 + 0.65 * math.sin(latitude_radians) * math.sin(declination),
            0.08,
            1.92,
        )
        true_anomaly = 2.0 * math.pi * float(month) / max(1, months)
        orbital_distance_au = (1.0 - eccentricity * eccentricity) / max(
            0.02, 1.0 + eccentricity * math.cos(true_anomaly)
        )
        orbital_factor = 1.0 / max(
            0.02, orbital_distance_au * orbital_distance_au
        )
        monthly.append(
            SOLAR_CONSTANT_W_M2
            * stellar_luminosity
            * latitude_factor
            * seasonal_latitude_factor
            * orbital_factor
            / 4.0
        )
        orbital_factors.append(orbital_factor)
    return monthly, orbital_factors


def _validate_climate_energy(
    world: dict[str, Any], checks: list[dict[str, Any]]
) -> None:
    cells = world.get("cells")
    records = world.get("climate_energy_balance_records")
    summary = world.get("summary")
    violations: list[str] = []
    maximum_equation_residual = 0.0

    if not isinstance(cells, list) or not cells or not all(
        isinstance(cell, dict) for cell in cells
    ):
        _record_violation(violations, "cells must be a non-empty list of objects")
        cells = []
    if not isinstance(records, list):
        _record_violation(violations, "climate energy records must be a list")
        records = []
    if not isinstance(summary, dict):
        _record_violation(violations, "summary must be an object")
        summary = {}

    cells_by_id: dict[int, dict[str, Any]] = {}
    for index, cell in enumerate(cells):
        cell_id = _integer(cell.get("id"))
        if cell_id is None or cell_id in cells_by_id:
            _record_violation(violations, f"cell[{index}] has invalid or duplicate id")
            continue
        cells_by_id[cell_id] = cell

    first_months = cells[0].get("temperature_monthly_c") if cells else None
    month_count = len(first_months) if isinstance(first_months, list) else 12
    if month_count <= 0:
        month_count = 12
    for index, cell in enumerate(cells):
        monthly_temperature = cell.get("temperature_monthly_c")
        if (
            not isinstance(monthly_temperature, list)
            or len(monthly_temperature) != month_count
            or any(not _finite_number(value) for value in monthly_temperature)
        ):
            _record_violation(
                violations,
                f"cell[{index}] monthly temperature coverage is inconsistent",
            )

    stellar_luminosity = max(0.01, _planet_value(world, "stellar_luminosity", 1.0))
    greenhouse_factor = max(0.0, _planet_value(world, "greenhouse_factor", 1.0))
    pressure_bar = max(0.0, _planet_value(world, "atmosphere_pressure_bar", 1.0))
    axial_tilt = _clamp(_planet_value(world, "axial_tilt_deg", 23.5), 0.0, 90.0)
    eccentricity = _clamp(
        _planet_value(world, "orbital_eccentricity", 0.016), 0.0, 0.8
    )

    required_fields = {
        "id",
        "cell_id",
        "latitude_deg",
        "biome",
        "water_body_type",
        "surface_albedo_regime",
        "stellar_luminosity_factor",
        "planetary_greenhouse_factor",
        "atmosphere_pressure_bar",
        "orbital_eccentricity",
        "mean_orbital_distance_factor",
        "temperature_c",
        "monthly_top_of_atmosphere_insolation_w_m2",
        "top_of_atmosphere_insolation_w_m2",
        "seasonal_insolation_range_w_m2",
        "orbital_insolation_variability_index",
        "peak_seasonal_insolation_w_m2",
        "low_seasonal_insolation_w_m2",
        "surface_albedo_index",
        "absorbed_shortwave_w_m2",
        "outgoing_longwave_w_m2",
        "greenhouse_trapping_w_m2",
        "net_radiative_balance_w_m2",
        "no_greenhouse_equilibrium_temperature_c",
        "radiative_equilibrium_temperature_c",
        "energy_balance_residual_c",
        "climate_energy_stress_index",
    }
    expected_by_cell: dict[int, dict[str, Any]] = {}
    regime_counts: Counter[str] = Counter()
    sums = Counter()
    high_stress_count = 0
    for cell_id, cell in cells_by_id.items():
        try:
            latitude = float(cell["lat_deg"])
            observed_temperature = float(cell["temperature_c"])
            ocean_current_temperature = float(
                cell.get("ocean_current_temperature_c", 0.0)
            )
            albedo, regime = _surface_albedo(cell)
            greenhouse_effect = _greenhouse_effect_c(
                cell, greenhouse_factor, pressure_bar
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            _record_violation(
                violations, f"cell {cell_id} has invalid climate-energy inputs"
            )
            continue
        if not all(
            math.isfinite(value)
            for value in (
                latitude,
                observed_temperature,
                ocean_current_temperature,
                albedo,
                greenhouse_effect,
            )
        ):
            _record_violation(
                violations, f"cell {cell_id} has non-finite climate-energy inputs"
            )
            continue
        monthly, orbital_factors = _seasonal_insolation_series(
            math.radians(latitude),
            stellar_luminosity,
            axial_tilt,
            eccentricity,
            month_count,
        )
        top = sum(monthly) / len(monthly)
        peak = max(monthly)
        low = min(monthly)
        seasonal_range = peak - low
        orbital_variability = _clamp(seasonal_range / max(1.0, top))
        mean_orbital_factor = sum(orbital_factors) / len(orbital_factors)
        absorbed = top * (1.0 - albedo)
        no_greenhouse_c = (
            (absorbed / STEFAN_BOLTZMANN_W_M2_K4) ** 0.25 - 273.15
            if absorbed > 0.0
            else -273.15
        )
        equilibrium_c = (
            no_greenhouse_c
            + greenhouse_effect
            + ocean_current_temperature * 0.35
        )
        observed_kelvin = max(1.0, observed_temperature + 273.15)
        equilibrium_kelvin = max(1.0, equilibrium_c + 273.15)
        outgoing = (
            SURFACE_LONGWAVE_EMISSIVITY
            * STEFAN_BOLTZMANN_W_M2_K4
            * observed_kelvin**4
        )
        equilibrium_longwave = (
            SURFACE_LONGWAVE_EMISSIVITY
            * STEFAN_BOLTZMANN_W_M2_K4
            * equilibrium_kelvin**4
        )
        trapping = max(0.0, equilibrium_longwave - absorbed)
        net = absorbed + trapping - outgoing
        residual_c = observed_temperature - equilibrium_c
        stress = _clamp(abs(residual_c) / 28.0 + abs(net) / 220.0)
        expected = {
            "latitude_deg": latitude,
            "stellar_luminosity_factor": stellar_luminosity,
            "planetary_greenhouse_factor": greenhouse_factor,
            "atmosphere_pressure_bar": pressure_bar,
            "orbital_eccentricity": eccentricity,
            "mean_orbital_distance_factor": mean_orbital_factor,
            "temperature_c": observed_temperature,
            "monthly_top_of_atmosphere_insolation_w_m2": monthly,
            "top_of_atmosphere_insolation_w_m2": top,
            "seasonal_insolation_range_w_m2": seasonal_range,
            "orbital_insolation_variability_index": orbital_variability,
            "peak_seasonal_insolation_w_m2": peak,
            "low_seasonal_insolation_w_m2": low,
            "surface_albedo_index": albedo,
            "absorbed_shortwave_w_m2": absorbed,
            "outgoing_longwave_w_m2": outgoing,
            "greenhouse_trapping_w_m2": trapping,
            "net_radiative_balance_w_m2": net,
            "no_greenhouse_equilibrium_temperature_c": no_greenhouse_c,
            "radiative_equilibrium_temperature_c": equilibrium_c,
            "energy_balance_residual_c": residual_c,
            "climate_energy_stress_index": stress,
            "surface_albedo_regime": regime,
        }
        expected_by_cell[cell_id] = expected
        regime_counts[regime] += 1
        sums["top"] += top
        sums["albedo"] += albedo
        sums["absorbed"] += absorbed
        sums["outgoing"] += outgoing
        sums["trapping"] += trapping
        sums["net"] += net
        sums["residual_abs"] += abs(residual_c)
        sums["stress"] += stress
        sums["seasonal_range"] += seasonal_range
        sums["orbital_variability"] += orbital_variability
        sums["peak"] += peak
        sums["low"] += low
        sums["orbital_factor"] += mean_orbital_factor
        high_stress_count += stress >= 0.65

    seen_cell_ids: set[int] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            _record_violation(violations, f"energy record[{index}] is not an object")
            continue
        missing = required_fields - set(record)
        if missing:
            _record_violation(
                violations,
                f"energy record[{index}] is missing fields: {', '.join(sorted(missing))}",
            )
            continue
        record_id = _integer(record.get("id"))
        cell_id = _integer(record.get("cell_id"))
        if record_id != index:
            _record_violation(violations, f"energy record[{index}] id is not sequential")
        if cell_id is None or cell_id in seen_cell_ids:
            _record_violation(
                violations, f"energy record[{index}] has invalid or duplicate cell_id"
            )
            continue
        seen_cell_ids.add(cell_id)
        cell = cells_by_id.get(cell_id)
        expected = expected_by_cell.get(cell_id)
        if cell is None or expected is None:
            _record_violation(
                violations, f"energy record[{index}] does not reference a valid cell"
            )
            continue
        if record.get("biome") != str(cell.get("biome", "unknown")):
            _record_violation(violations, f"energy record[{index}] biome is stale")
        if record.get("water_body_type") != str(
            cell.get("water_body_type", "land")
        ):
            _record_violation(
                violations, f"energy record[{index}] water body type is stale"
            )
        if record.get("surface_albedo_regime") != expected["surface_albedo_regime"]:
            _record_violation(
                violations, f"energy record[{index}] albedo regime is inconsistent"
            )

        monthly = record.get("monthly_top_of_atmosphere_insolation_w_m2")
        expected_monthly = expected["monthly_top_of_atmosphere_insolation_w_m2"]
        if (
            not isinstance(monthly, list)
            or len(monthly) != month_count
            or any(not _finite_number(value) or float(value) < 0.0 for value in monthly)
        ):
            _record_violation(
                violations, f"energy record[{index}] monthly insolation is invalid"
            )
        else:
            for actual, expected_value in zip(monthly, expected_monthly):
                residual = abs(float(actual) - float(expected_value))
                maximum_equation_residual = max(
                    maximum_equation_residual, residual
                )
                if not _close(actual, expected_value, absolute=1.1e-6, relative=0.0):
                    _record_violation(
                        violations,
                        f"energy record[{index}] monthly insolation does not replay",
                    )
                    break

        for field, expected_value in expected.items():
            if field in {
                "monthly_top_of_atmosphere_insolation_w_m2",
                "surface_albedo_regime",
            }:
                continue
            residual = (
                math.inf
                if _number(record.get(field)) is None
                else abs(float(record[field]) - float(expected_value))
            )
            maximum_equation_residual = max(maximum_equation_residual, residual)
            if not _close(
                record.get(field), expected_value, absolute=1.1e-6, relative=0.0
            ):
                _record_violation(
                    violations, f"energy record[{index}] {field} does not replay"
                )

        nonnegative_fields = (
            "top_of_atmosphere_insolation_w_m2",
            "seasonal_insolation_range_w_m2",
            "peak_seasonal_insolation_w_m2",
            "low_seasonal_insolation_w_m2",
            "absorbed_shortwave_w_m2",
            "outgoing_longwave_w_m2",
            "greenhouse_trapping_w_m2",
        )
        if any(
            _number(record.get(field)) is None or float(record[field]) < 0.0
            for field in nonnegative_fields
        ):
            _record_violation(
                violations, f"energy record[{index}] contains negative energy flux"
            )
        for field in (
            "surface_albedo_index",
            "orbital_insolation_variability_index",
            "climate_energy_stress_index",
        ):
            value = _number(record.get(field))
            if value is None or not 0.0 <= value <= 1.0:
                _record_violation(
                    violations, f"energy record[{index}] {field} is out of range"
                )

        cell_mirrors = {
            "top_of_atmosphere_insolation_w_m2": "top_of_atmosphere_insolation_w_m2",
            "surface_albedo_index": "surface_albedo_index",
            "absorbed_shortwave_w_m2": "absorbed_shortwave_w_m2",
            "outgoing_longwave_w_m2": "outgoing_longwave_w_m2",
            "greenhouse_trapping_w_m2": "greenhouse_trapping_w_m2",
            "net_radiative_balance_w_m2": "net_radiative_balance_w_m2",
            "no_greenhouse_equilibrium_temperature_c": "no_greenhouse_equilibrium_temperature_c",
            "radiative_equilibrium_temperature_c": "radiative_equilibrium_temperature_c",
            "energy_balance_residual_c": "energy_balance_residual_c",
            "climate_energy_stress_index": "climate_energy_stress_index",
            "seasonal_insolation_range_w_m2": "seasonal_insolation_range_w_m2",
            "orbital_insolation_variability_index": "orbital_insolation_variability_index",
            "peak_seasonal_insolation_w_m2": "peak_seasonal_insolation_w_m2",
            "low_seasonal_insolation_w_m2": "low_seasonal_insolation_w_m2",
        }
        for cell_field, expected_field in cell_mirrors.items():
            if not _close(
                cell.get(cell_field),
                expected[expected_field],
                absolute=1.1e-6,
                relative=0.0,
            ):
                _record_violation(
                    violations,
                    f"cell {cell_id} {cell_field} does not mirror the replay",
                )
        if cell.get("surface_albedo_regime") != expected["surface_albedo_regime"]:
            _record_violation(
                violations, f"cell {cell_id} surface_albedo_regime is inconsistent"
            )

    if seen_cell_ids != set(cells_by_id):
        _record_violation(
            violations,
            "energy records do not provide exactly one record for every cell",
        )

    cell_count = len(cells_by_id)
    divisor = max(1, cell_count)
    expected_summary = {
        "climate_energy_balance_record_count": len(records),
        "mean_top_of_atmosphere_insolation_w_m2": sums["top"] / divisor,
        "mean_surface_albedo_index": sums["albedo"] / divisor,
        "mean_absorbed_shortwave_w_m2": sums["absorbed"] / divisor,
        "mean_outgoing_longwave_w_m2": sums["outgoing"] / divisor,
        "mean_greenhouse_trapping_w_m2": sums["trapping"] / divisor,
        "mean_net_radiative_balance_w_m2": sums["net"] / divisor,
        "mean_abs_energy_balance_residual_c": sums["residual_abs"] / divisor,
        "mean_climate_energy_stress_index": sums["stress"] / divisor,
        "mean_seasonal_insolation_range_w_m2": sums["seasonal_range"] / divisor,
        "mean_orbital_insolation_variability_index": sums[
            "orbital_variability"
        ]
        / divisor,
        "mean_peak_seasonal_insolation_w_m2": sums["peak"] / divisor,
        "mean_low_seasonal_insolation_w_m2": sums["low"] / divisor,
        "mean_orbital_distance_factor": sums["orbital_factor"] / divisor,
        "orbital_eccentricity": eccentricity,
        "high_climate_energy_stress_cell_count": high_stress_count,
    }
    for field, expected in expected_summary.items():
        if field in {
            "climate_energy_balance_record_count",
            "high_climate_energy_stress_cell_count",
        }:
            if _integer(summary.get(field)) != expected:
                _record_violation(
                    violations, f"summary {field} does not mirror energy records"
                )
        elif not _close(summary.get(field), expected, absolute=1.1e-6, relative=0.0):
            _record_violation(
                violations, f"summary {field} does not mirror the energy replay"
            )
    if summary.get("surface_albedo_regime_counts") != dict(
        sorted(regime_counts.items())
    ):
        _record_violation(
            violations, "summary surface_albedo_regime_counts is inconsistent"
        )

    _append_check(
        checks,
        domain="climate",
        name="climate_energy_balance_replay",
        passed=not violations,
        message=(
            "each cell's monthly insolation, albedo, greenhouse, longwave, net "
            "balance, stress, cell mirrors, and global aggregates must replay the producer equations"
        ),
        observed={
            "cell_count": len(cells),
            "record_count": len(records),
            "month_count": month_count,
            "unique_recorded_cell_count": len(seen_cell_ids),
            "violation_count": len(violations),
            "maximum_equation_residual": maximum_equation_residual,
        },
        expected={
            "record_count": len(cells),
            "unique_recorded_cell_count": len(cells),
            "monthly_values_per_record": month_count,
            "equations_and_summary_match": True,
        },
        evidence={"violations": violations},
    )


FEEDBACK_BOOLEAN_FIELDS = frozenset(
    {
        "sea_level_recomputed",
        "climate_recomputed",
        "hydrologic_water_budget_recomputed",
        "hydrology_recomputed",
        "erosion_applied",
        "cryosphere_applied",
        "plate_motion_applied",
        "crust_transport_applied",
        "crust_evolution_applied",
    }
)

FEEDBACK_COUNT_FIELDS = frozenset(
    {
        "sea_level_recompute_count",
        "climate_recompute_count",
        "hydrologic_water_budget_recompute_count",
        "hydrology_recompute_count",
        "numeric_depression_correction_pass_count",
        "numeric_depression_correction_event_count",
        "numeric_depression_breach_selected_event_count",
        "numeric_depression_breach_excavation_cell_application_count",
        "numeric_depression_breach_deposition_cell_application_count",
        "numeric_depression_temporary_lake_event_count",
        "numeric_depression_temporary_lake_cell_application_count",
        "numeric_depression_temporary_lake_unique_cell_count",
        "fluvial_sediment_active_cell_step_count",
        "fluvial_sediment_routed_edge_count",
        "fluvial_sediment_land_terminal_count",
        "fluvial_sediment_marine_terminal_count",
        "fluvial_sediment_terminal_allocation_count",
        "hillslope_sediment_transport_edge_count",
        "hillslope_sediment_source_cell_count",
        "hillslope_sediment_target_cell_count",
        "hillslope_sediment_land_to_land_edge_count",
        "hillslope_sediment_land_to_marine_edge_count",
        "glacial_sediment_transfer_count",
        "glacial_sediment_source_cell_count",
        "glacial_sediment_target_cell_count",
        "glacial_sediment_land_target_transfer_count",
        "glacial_sediment_marine_target_transfer_count",
        "cell_count",
        "land_cell_count",
        "water_cell_count",
        "river_cell_count",
    }
)

FEEDBACK_VALUE_FIELDS = frozenset(
    {
        "sea_level_adjustment_m",
        "numeric_depression_breach_excavation_volume_km3",
        "numeric_depression_breach_deposition_volume_km3",
        "numeric_depression_correction_mass_balance_residual_km3",
        "numeric_depression_temporary_lake_candidate_area_km2",
        "numeric_depression_temporary_lake_candidate_volume_km3",
        "max_numeric_depression_temporary_lake_depth_m",
        "fluvial_sediment_local_source_volume_km3",
        "fluvial_sediment_routed_throughput_volume_km3",
        "fluvial_sediment_capacity_deposition_volume_km3",
        "fluvial_sediment_depression_fill_deposition_volume_km3",
        "fluvial_sediment_lake_trap_deposition_volume_km3",
        "fluvial_sediment_terminal_land_deposition_volume_km3",
        "fluvial_sediment_marine_deposition_volume_km3",
        "fluvial_sediment_terminal_export_volume_km3",
        "fluvial_sediment_mass_balance_residual_km3",
        "hillslope_sediment_production_volume_km3",
        "hillslope_sediment_deposition_volume_km3",
        "hillslope_sediment_mass_balance_residual_km3",
        "max_hillslope_sediment_source_production_depth_m",
        "max_hillslope_sediment_target_deposition_depth_m",
        "mean_hillslope_effective_diffusivity",
        "glacial_sediment_production_volume_km3",
        "glacial_sediment_deposition_volume_km3",
        "glacial_sediment_mass_balance_residual_km3",
        "glacial_sediment_terrain_volume_change_residual_km3",
        "max_glacial_sediment_source_production_depth_m",
        "max_glacial_sediment_target_deposition_depth_m",
        "sediment_alluvium_entrainment_volume_km3",
        "sediment_bedrock_erosion_volume_km3",
        "sediment_inventory_volume_km3",
        "sediment_source_partition_residual_km3",
        "sediment_inventory_mass_balance_residual_km3",
        "surface_area_km2",
        "ocean_area_km2",
        "ocean_volume_km3",
        "ocean_fraction",
        "mean_elevation_m",
        "mean_land_elevation_m",
        "min_elevation_m",
        "max_elevation_m",
        "mean_temperature_c",
        "mean_precipitation_mm_y",
        "mean_runoff_mm_y",
        "hydrologic_land_precipitation_volume_km3_y",
        "hydrologic_actual_evapotranspiration_volume_km3_y",
        "hydrologic_infiltration_volume_km3_y",
        "hydrologic_runoff_volume_km3_y",
        "hydrologic_water_budget_residual_km3_y",
        "max_abs_hydrologic_water_budget_cell_residual_mm_y",
        "mean_stream_power_response_m_per_reference_step",
        "mean_sediment_thickness_m",
        "mean_cumulative_sediment_production_m",
        "mean_cumulative_sediment_deposition_m",
        "mean_cumulative_sediment_export_m",
        "cumulative_sediment_production_volume_km3",
        "cumulative_sediment_deposition_volume_km3",
        "cumulative_sediment_export_volume_km3",
        "mean_abs_elevation_change_m_from_previous_stage",
        "mean_abs_temperature_change_c_from_previous_stage",
        "mean_abs_precipitation_change_mm_y_from_previous_stage",
        "mean_abs_runoff_change_mm_y_from_previous_stage",
    }
)

FEEDBACK_REQUIRED_FIELDS = frozenset(
    {"id", "stage", "erosion_iteration", "plate_motion_history_id"}
) | FEEDBACK_BOOLEAN_FIELDS | FEEDBACK_COUNT_FIELDS | FEEDBACK_VALUE_FIELDS


def _feedback_close(actual: Any, expected: float) -> bool:
    return _close(actual, expected, absolute=0.01, relative=2.0e-4)


def _validate_feedback_structure(
    world: dict[str, Any], checks: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    clock = world.get("simulation_clock")
    history = world.get("earth_system_feedback_history")
    cells = world.get("cells")
    motion_history = world.get("plate_motion_history")
    violations: list[str] = []

    clock_required = {
        "clock_type",
        "time_unit",
        "physical_time_resolved",
        "nominal_time_calibrated",
        "absolute_geological_age_resolved",
        "process_rate_calibration_resolved",
        "time_step_convergence_demonstrated",
        "clock_limitation",
        "nominal_time_model",
        "nominal_time_unit",
        "nominal_time_basis",
        "nominal_time_source_parameter",
        "nominal_time_direction",
        "cell_erosion_rate_semantics",
        "stream_incision_update",
        "erosion_transition_coupling_semantics",
        "nominal_timestep_ma",
        "reference_timestep_ma",
        "maturation_timestep_scale",
        "nominal_timed_transition_count",
        "initial_nominal_elapsed_time_ma",
        "current_nominal_elapsed_time_ma",
        "final_nominal_elapsed_time_ma",
        "cryosphere_advances_nominal_time",
        "iteration_process_order",
        "geological_age_ga",
        "configured_erosion_iteration_count",
        "configured_cryosphere_coupling_stage_count",
        "cryosphere_coupling_stage_count",
        "feedback_recompute_count",
        "hydrologic_water_budget_recompute_count",
        "stage_count",
        "initial_stage_id",
        "current_stage_id",
        "final_stage_id",
        "final_cryosphere_stage_id",
    }
    if not isinstance(clock, dict):
        _record_violation(violations, "simulation_clock must be an object")
        clock = {}
    else:
        missing = clock_required - set(clock)
        if missing:
            _record_violation(
                violations,
                f"simulation_clock is missing fields: {', '.join(sorted(missing))}",
            )
    if not isinstance(history, list) or not all(
        isinstance(step, dict) for step in history
    ):
        _record_violation(
            violations, "earth_system_feedback_history must be a list of objects"
        )
        history = []
    if not isinstance(cells, list) or not all(isinstance(cell, dict) for cell in cells):
        _record_violation(violations, "cells must be a list of objects")
        cells = []
    if not isinstance(motion_history, list) or not all(
        isinstance(step, dict) for step in motion_history
    ):
        _record_violation(violations, "plate_motion_history must be a list of objects")
        motion_history = []

    erosion_iterations = _integer(clock.get("configured_erosion_iteration_count"))
    configured_cryo = _integer(
        clock.get("configured_cryosphere_coupling_stage_count")
    )
    cryo_count = _integer(clock.get("cryosphere_coupling_stage_count"))
    stage_count = _integer(clock.get("stage_count"))
    expected_stage_count = (
        erosion_iterations + 2 if erosion_iterations is not None else None
    )
    final_id = len(history) - 1
    if (
        clock.get("clock_type") != "coupled_geodynamic_stage_clock_v12"
        or clock.get("time_unit") != "model_step"
        or clock.get("physical_time_resolved") is not False
        or clock.get("nominal_time_calibrated") is not False
        or clock.get("absolute_geological_age_resolved") is not False
        or clock.get("process_rate_calibration_resolved") is not False
        or clock.get("time_step_convergence_demonstrated") is not False
        or clock.get("clock_limitation")
        != "nominal_geological_intervals_without_calibrated_physical_time_or_timestep_convergence"
        or clock.get("nominal_time_model") != NOMINAL_TIME_MODEL
        or clock.get("nominal_time_unit") != "Ma"
        or clock.get("nominal_time_basis") != NOMINAL_TIME_BASIS
        or clock.get("nominal_time_source_parameter")
        != NOMINAL_TIME_SOURCE_PARAMETER
        or clock.get("nominal_time_direction")
        != "forward_from_initial_generated_state"
        or clock.get("cell_erosion_rate_semantics")
        != "stream_power_response_per_reference_step_not_applied_transition_depth"
        or clock.get("stream_incision_update")
        != "cell_erosion_rate_times_maturation_timestep_scale"
        or clock.get("erosion_transition_coupling_semantics")
        != EROSION_TRANSITION_COUPLING_SEMANTICS
        or clock.get("cryosphere_advances_nominal_time") is not False
        or clock.get("iteration_process_order") != ITERATION_PROCESS_ORDER
    ):
        _record_violation(violations, "simulation clock metadata is invalid")

    nominal_timestep_ma = _number(clock.get("nominal_timestep_ma"))
    reference_timestep_ma = _number(clock.get("reference_timestep_ma"))
    maturation_timestep_scale = _number(clock.get("maturation_timestep_scale"))
    if nominal_timestep_ma is None or nominal_timestep_ma <= 0.0:
        _record_violation(violations, "simulation clock nominal timestep is invalid")
    if reference_timestep_ma is None or not _close(
        reference_timestep_ma,
        MATURATION_REFERENCE_TIMESTEP_MA,
        absolute=1.0e-12,
        relative=0.0,
    ):
        _record_violation(
            violations, "simulation clock reference timestep is invalid"
        )
    if (
        nominal_timestep_ma is not None
        and reference_timestep_ma is not None
        and nominal_timestep_ma > reference_timestep_ma
    ):
        _record_violation(
            violations,
            "simulation clock nominal timestep exceeds the configured reference step",
        )
    if (
        nominal_timestep_ma is not None
        and reference_timestep_ma is not None
        and reference_timestep_ma > 0.0
        and not _close(
            maturation_timestep_scale,
            nominal_timestep_ma / reference_timestep_ma,
            absolute=1.0e-12,
            relative=1.0e-12,
        )
    ):
        _record_violation(
            violations,
            "simulation clock maturation timestep scale does not replay",
        )

    nominal_elapsed_ma = (
        nominal_timestep_ma * erosion_iterations
        if nominal_timestep_ma is not None and erosion_iterations is not None
        else None
    )
    if _integer(clock.get("nominal_timed_transition_count")) != erosion_iterations:
        _record_violation(
            violations,
            "simulation clock nominal transition count does not match erosion iterations",
        )
    if not _close(
        clock.get("initial_nominal_elapsed_time_ma"),
        0.0,
        absolute=1.0e-12,
        relative=0.0,
    ):
        _record_violation(
            violations, "simulation clock initial nominal elapsed time is not zero"
        )
    if nominal_elapsed_ma is not None:
        for field in (
            "current_nominal_elapsed_time_ma",
            "final_nominal_elapsed_time_ma",
        ):
            if not _close(
                clock.get(field),
                nominal_elapsed_ma,
                absolute=1.0e-10,
                relative=1.0e-12,
            ):
                _record_violation(
                    violations,
                    f"simulation clock {field} does not replay from timestep and transitions",
                )
    clock_age = _number(clock.get("geological_age_ga"))
    planet_age = _planet_value(world, "geological_age_ga", 4.5)
    if clock_age is None or clock_age < 0.0 or not _close(
        clock_age, planet_age, absolute=1.0e-6, relative=0.0
    ):
        _record_violation(
            violations, "simulation clock geological age does not mirror the planet"
        )
    if erosion_iterations is None or erosion_iterations < 0:
        _record_violation(violations, "configured erosion iteration count is invalid")
    if configured_cryo != 1 or cryo_count != 1:
        _record_violation(violations, "cryosphere stage count must be exactly one")
    if stage_count != expected_stage_count or len(history) != expected_stage_count:
        _record_violation(
            violations, "feedback history length does not match configured stages"
        )
    expected_clock_ids = {
        "initial_stage_id": 0,
        "current_stage_id": final_id,
        "final_stage_id": final_id,
        "final_cryosphere_stage_id": final_id,
    }
    for field, expected in expected_clock_ids.items():
        if _integer(clock.get(field)) != expected:
            _record_violation(violations, f"simulation clock {field} is inconsistent")
    if erosion_iterations is not None and len(motion_history) != erosion_iterations + 1:
        _record_violation(
            violations, "plate motion history length does not match erosion stages"
        )

    process_history_counts: dict[str, int] = {}
    if (
        erosion_iterations is not None
        and erosion_iterations >= 0
        and nominal_timestep_ma is not None
        and nominal_timestep_ma > 0.0
        and maturation_timestep_scale is not None
        and maturation_timestep_scale > 0.0
    ):
        process_history_counts = _validate_nominal_process_histories(
            world,
            clock=clock,
            motion_history=motion_history,
            erosion_iterations=erosion_iterations,
            nominal_timestep_ma=nominal_timestep_ma,
            maturation_timestep_scale=maturation_timestep_scale,
            violations=violations,
        )

    previous_sediment = (0.0, 0.0, 0.0)
    for index, step in enumerate(history):
        is_initial = index == 0
        is_erosion = (
            erosion_iterations is not None and 1 <= index <= erosion_iterations
        )
        is_cryo = index == final_id and not is_initial
        if nominal_timestep_ma is not None and nominal_timestep_ma > 0.0:
            if is_initial:
                interval_start_ma = 0.0
                interval_end_ma = 0.0
                interval_role = "initial_state_snapshot"
            elif is_erosion:
                interval_start_ma = (index - 1) * nominal_timestep_ma
                interval_end_ma = index * nominal_timestep_ma
                interval_role = "erosion_transition"
            else:
                interval_start_ma = (
                    nominal_elapsed_ma if nominal_elapsed_ma is not None else 0.0
                )
                interval_end_ma = interval_start_ma
                interval_role = "final_cryosphere_coupling_snapshot"
            _validate_nominal_time_record(
                step,
                label=f"feedback step[{index}]",
                expected_start_ma=interval_start_ma,
                expected_end_ma=interval_end_ma,
                expected_role=interval_role,
                violations=violations,
            )

        missing = FEEDBACK_REQUIRED_FIELDS - set(step)
        if missing:
            _record_violation(
                violations,
                f"feedback step[{index}] is missing fields: {', '.join(sorted(missing))}",
            )
            continue
        if _integer(step.get("id")) != index:
            _record_violation(violations, f"feedback step[{index}] id is not sequential")
        if any(type(step.get(field)) is not bool for field in FEEDBACK_BOOLEAN_FIELDS):
            _record_violation(
                violations, f"feedback step[{index}] has non-boolean process flags"
            )
        invalid_counts = [
            field
            for field in FEEDBACK_COUNT_FIELDS
            if _integer(step.get(field)) is None or int(step[field]) < 0
        ]
        if invalid_counts:
            _record_violation(
                violations, f"feedback step[{index}] has invalid count fields"
            )
        if any(not _finite_number(step.get(field)) for field in FEEDBACK_VALUE_FIELDS):
            _record_violation(
                violations, f"feedback step[{index}] has non-finite numeric fields"
            )
        expected_stage = (
            "initial_climate_hydrology"
            if is_initial
            else ("erosion_iteration" if is_erosion else "cryosphere_coupling")
        )
        expected_iteration = index if is_erosion else -1
        expected_motion_id = index if is_erosion else (0 if is_initial else max(0, index - 1))
        if step.get("stage") != expected_stage:
            _record_violation(violations, f"feedback step[{index}] stage is invalid")
        if _integer(step.get("erosion_iteration")) != expected_iteration:
            _record_violation(
                violations, f"feedback step[{index}] erosion_iteration is invalid"
            )
        if _integer(step.get("plate_motion_history_id")) != expected_motion_id:
            _record_violation(
                violations, f"feedback step[{index}] plate motion link is invalid"
            )
        expected_flags = {
            "erosion_applied": is_erosion,
            "cryosphere_applied": is_cryo,
            "plate_motion_applied": is_erosion,
            "crust_transport_applied": is_erosion,
            "crust_evolution_applied": is_erosion,
        }
        for field, expected in expected_flags.items():
            if step.get(field) is not expected:
                _record_violation(
                    violations, f"feedback step[{index}] {field} is inconsistent"
                )

        recompute_fields = (
            "sea_level_recompute_count",
            "climate_recompute_count",
            "hydrologic_water_budget_recompute_count",
            "hydrology_recompute_count",
        )
        recompute_counts = [_integer(step.get(field)) for field in recompute_fields]
        if (
            any(value is None or value <= 0 for value in recompute_counts)
            or len(set(recompute_counts)) != 1
        ):
            _record_violation(
                violations, f"feedback step[{index}] recompute counts are inconsistent"
            )
        for boolean_field, count_field in (
            ("sea_level_recomputed", "sea_level_recompute_count"),
            ("climate_recomputed", "climate_recompute_count"),
            (
                "hydrologic_water_budget_recomputed",
                "hydrologic_water_budget_recompute_count",
            ),
            ("hydrology_recomputed", "hydrology_recompute_count"),
        ):
            count = _integer(step.get(count_field))
            if step.get(boolean_field) is not (count is not None and count > 0):
                _record_violation(
                    violations,
                    f"feedback step[{index}] {boolean_field} does not mirror its count",
                )
        correction_passes = _integer(
            step.get("numeric_depression_correction_pass_count")
        )
        hydrology_recomputes = _integer(step.get("hydrology_recompute_count"))
        if (
            correction_passes is not None
            and hydrology_recomputes is not None
            and hydrology_recomputes != correction_passes + 1
        ):
            _record_violation(
                violations,
                f"feedback step[{index}] hydrology/correction pass counts are inconsistent",
            )
        cell_count = _integer(step.get("cell_count"))
        land_count = _integer(step.get("land_cell_count"))
        water_count = _integer(step.get("water_cell_count"))
        river_count = _integer(step.get("river_cell_count"))
        if (
            cell_count is not None
            and land_count is not None
            and water_count is not None
            and cell_count != land_count + water_count
        ):
            _record_violation(
                violations, f"feedback step[{index}] land/water counts do not close"
            )
        if (
            river_count is not None
            and cell_count is not None
            and river_count > cell_count
        ):
            _record_violation(
                violations, f"feedback step[{index}] river count exceeds cells"
            )

        if is_initial:
            for field in (
                "mean_abs_elevation_change_m_from_previous_stage",
                "mean_abs_temperature_change_c_from_previous_stage",
                "mean_abs_precipitation_change_mm_y_from_previous_stage",
                "mean_abs_runoff_change_mm_y_from_previous_stage",
            ):
                if not _close(step.get(field), 0.0, absolute=0.001, relative=0.0):
                    _record_violation(
                        violations, f"initial feedback step {field} must be zero"
                    )

        sediment = tuple(
            float(step.get(field, math.nan))
            for field in (
                "cumulative_sediment_production_volume_km3",
                "cumulative_sediment_deposition_volume_km3",
                "cumulative_sediment_export_volume_km3",
            )
        )
        if all(math.isfinite(value) and value >= 0.0 for value in sediment):
            if any(
                current + 0.01 < previous
                for current, previous in zip(sediment, previous_sediment)
            ):
                _record_violation(
                    violations,
                    f"feedback step[{index}] cumulative sediment regresses",
                )
            if abs(sediment[0] - sediment[1] - sediment[2]) > max(
                0.01, sediment[0] * 1.0e-6
            ):
                _record_violation(
                    violations,
                    f"feedback step[{index}] cumulative sediment mass does not close",
                )
            previous_sediment = sediment
        else:
            _record_violation(
                violations, f"feedback step[{index}] cumulative sediment is invalid"
            )

    # Replay the final state fields that remain unchanged by natural enrichers.
    if history and cells:
        final = history[-1]
        try:
            cell_count = len(cells)
            land = [cell for cell in cells if not bool(cell.get("is_water", False))]
            surface_area = sum(float(cell["area_km2"]) for cell in cells)
            ocean_area = sum(
                float(cell["area_km2"])
                for cell in cells
                if bool(cell.get("is_water", False))
            )
            ocean_volume = sum(
                float(cell["area_km2"])
                * max(0.0, float(cell.get("water_depth_m", 0.0)))
                / 1000.0
                for cell in cells
                if bool(cell.get("is_water", False))
            )
            divisor = max(1, cell_count)
            cumulative_sediment_gross_depths_m = [
                float(cell["sediment_alluvium_entrainment_m"])
                + float(cell["sediment_bedrock_erosion_m"])
                for cell in cells
            ]
            expected_final: dict[str, float | int] = {
                "cell_count": cell_count,
                "land_cell_count": len(land),
                "water_cell_count": cell_count - len(land),
                "river_cell_count": sum(
                    bool(cell.get("is_river", False)) for cell in cells
                ),
                "surface_area_km2": surface_area,
                "ocean_area_km2": ocean_area,
                "ocean_volume_km3": ocean_volume,
                "ocean_fraction": ocean_area / max(1.0, surface_area),
                "mean_elevation_m": sum(
                    float(cell.get("elevation_m", 0.0)) for cell in cells
                )
                / divisor,
                "mean_land_elevation_m": sum(
                    float(cell.get("elevation_m", 0.0)) for cell in land
                )
                / max(1, len(land)),
                "min_elevation_m": min(
                    (float(cell.get("elevation_m", 0.0)) for cell in cells),
                    default=0.0,
                ),
                "max_elevation_m": max(
                    (float(cell.get("elevation_m", 0.0)) for cell in cells),
                    default=0.0,
                ),
                "mean_temperature_c": sum(
                    float(cell.get("temperature_c", 0.0)) for cell in cells
                )
                / divisor,
                "mean_precipitation_mm_y": sum(
                    float(cell.get("precipitation_mm_y", 0.0)) for cell in cells
                )
                / divisor,
                "mean_runoff_mm_y": sum(
                    float(cell.get("runoff_mm_y", 0.0)) for cell in cells
                )
                / divisor,
                "mean_stream_power_response_m_per_reference_step": sum(
                    float(cell.get("erosion_rate", 0.0)) for cell in cells
                )
                / divisor,
                "mean_sediment_thickness_m": sum(
                    float(cell.get("sediment_thickness_m", 0.0)) for cell in cells
                )
                / divisor,
                "mean_cumulative_sediment_production_m": sum(
                    cumulative_sediment_gross_depths_m
                )
                / divisor,
                "mean_cumulative_sediment_deposition_m": sum(
                    float(cell.get("sediment_deposition_m", 0.0)) for cell in cells
                )
                / divisor,
                "mean_cumulative_sediment_export_m": sum(
                    float(cell.get("sediment_export_m", 0.0)) for cell in cells
                )
                / divisor,
                "cumulative_sediment_production_volume_km3": sum(
                    cumulative_sediment_gross_depths_m[index]
                    * float(cell.get("area_km2", 0.0))
                    / 1000.0
                    for index, cell in enumerate(cells)
                ),
                "cumulative_sediment_deposition_volume_km3": sum(
                    float(cell.get("sediment_deposition_m", 0.0))
                    * float(cell.get("area_km2", 0.0))
                    / 1000.0
                    for cell in cells
                ),
                "cumulative_sediment_export_volume_km3": sum(
                    float(cell.get("sediment_export_m", 0.0))
                    * float(cell.get("area_km2", 0.0))
                    / 1000.0
                    for cell in cells
                ),
            }
        except (KeyError, TypeError, ValueError, OverflowError):
            _record_violation(violations, "final cells contain invalid replay fields")
            expected_final = {}
        precision = 4
        world_summary = world.get("summary")
        if isinstance(world_summary, dict):
            candidate_precision = _integer(world_summary.get("output_float_precision"))
            if candidate_precision is not None and 0 <= candidate_precision <= 8:
                precision = candidate_precision
        sediment_volume_tolerance = max(
            0.01, surface_area * 0.5001 * 10.0 ** (-precision) / 1000.0
        ) if expected_final else 0.01
        integer_final_fields = {
            "cell_count",
            "land_cell_count",
            "water_cell_count",
            "river_cell_count",
        }
        for field, expected in expected_final.items():
            if field in integer_final_fields:
                valid = _integer(final.get(field)) == int(expected)
            elif field in {
                "cumulative_sediment_production_volume_km3",
                "cumulative_sediment_deposition_volume_km3",
                "cumulative_sediment_export_volume_km3",
            }:
                valid = _close(
                    final.get(field),
                    expected,
                    absolute=sediment_volume_tolerance,
                    relative=0.0,
                )
            elif field in {"surface_area_km2", "ocean_area_km2", "ocean_volume_km3"}:
                valid = _close(
                    final.get(field), expected, absolute=0.02, relative=1.0e-9
                )
            else:
                valid = _feedback_close(final.get(field), expected)
            if not valid:
                _record_violation(
                    violations, f"final feedback {field} does not replay from cells"
                )

    _append_check(
        checks,
        domain="simulation",
        name="coupled_stage_feedback_replay",
        passed=not violations,
        message=(
            "the simulation clock and every complete feedback stage must follow the "
            "configured initial/erosion/cryosphere sequence and the final stage must replay from cells"
        ),
        observed={
            "configured_erosion_iteration_count": erosion_iterations,
            "nominal_timestep_ma": nominal_timestep_ma,
            "reference_timestep_ma": reference_timestep_ma,
            "maturation_timestep_scale": maturation_timestep_scale,
            "nominal_elapsed_time_ma": nominal_elapsed_ma,
            "clock_stage_count": stage_count,
            "feedback_record_count": len(history),
            "plate_motion_record_count": len(motion_history),
            "time_aware_process_history_counts": process_history_counts,
            "violation_count": len(violations),
        },
        expected={
            "feedback_record_count": expected_stage_count,
            "plate_motion_record_count": (
                erosion_iterations + 1 if erosion_iterations is not None else None
            ),
            "complete_stage_records": True,
            "nominal_intervals_match_configured_timestep": True,
            "physical_time_and_convergence_claims": False,
            "plate_reference_and_effective_scales_replay": True,
            "final_stage_matches_cells": True,
        },
        evidence={"violations": violations},
    )
    return history, clock, violations


def _validate_feedback_summary(
    world: dict[str, Any],
    history: list[dict[str, Any]],
    clock: dict[str, Any],
    checks: list[dict[str, Any]],
) -> None:
    summary = world.get("summary")
    violations: list[str] = []
    if not isinstance(summary, dict):
        _record_violation(violations, "summary must be an object")
        summary = {}

    erosion_steps = [
        step for step in history if step.get("erosion_applied") is True
    ]
    cryosphere_steps = [
        step for step in history if step.get("cryosphere_applied") is True
    ]
    count_mirrors = {
        "simulation_clock_stage_count": len(history),
        "simulation_clock_erosion_iteration_count": len(erosion_steps),
        "simulation_clock_cryosphere_coupling_stage_count": len(
            cryosphere_steps
        ),
        "simulation_clock_sea_level_recompute_count": sum(
            _integer(step.get("sea_level_recompute_count")) or 0
            for step in history
        ),
        "simulation_clock_climate_recompute_count": sum(
            _integer(step.get("climate_recompute_count")) or 0
            for step in history
        ),
        "simulation_clock_hydrologic_water_budget_recompute_count": sum(
            _integer(step.get("hydrologic_water_budget_recompute_count")) or 0
            for step in history
        ),
        "simulation_clock_hydrology_recompute_count": sum(
            _integer(step.get("hydrology_recompute_count")) or 0
            for step in history
        ),
    }
    for field, expected in count_mirrors.items():
        if _integer(summary.get(field)) != expected:
            _record_violation(
                violations, f"summary {field} does not mirror feedback history"
            )

    final = history[-1] if history else {}
    try:
        value_mirrors = {
            "mean_erosion_iteration_elevation_change_m": sum(
                float(step["mean_abs_elevation_change_m_from_previous_stage"])
                for step in erosion_steps
            )
            / max(1, len(erosion_steps)),
            "total_feedback_mean_abs_elevation_change_m": sum(
                float(step["mean_abs_elevation_change_m_from_previous_stage"])
                for step in history
            ),
            "final_feedback_mean_abs_temperature_change_c": float(
                final.get("mean_abs_temperature_change_c_from_previous_stage", 0.0)
            ),
            "final_feedback_mean_abs_precipitation_change_mm_y": float(
                final.get(
                    "mean_abs_precipitation_change_mm_y_from_previous_stage", 0.0
                )
            ),
            "final_feedback_mean_abs_runoff_change_mm_y": float(
                final.get("mean_abs_runoff_change_mm_y_from_previous_stage", 0.0)
            ),
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        _record_violation(violations, "feedback summary inputs are non-numeric")
        value_mirrors = {}
    for field, expected in value_mirrors.items():
        if not math.isfinite(expected) or not _feedback_close(
            summary.get(field), expected
        ):
            _record_violation(
                violations, f"summary {field} does not mirror feedback history"
            )

    recomputed_feedback_count = sum(
        (step.get("erosion_applied") is True or step.get("cryosphere_applied") is True)
        and step.get("sea_level_recomputed") is True
        and step.get("climate_recomputed") is True
        and step.get("hydrologic_water_budget_recomputed") is True
        and step.get("hydrology_recomputed") is True
        for step in history
    )
    if _integer(clock.get("feedback_recompute_count")) != recomputed_feedback_count:
        _record_violation(
            violations, "clock feedback_recompute_count does not mirror stages"
        )
    if _integer(clock.get("hydrologic_water_budget_recompute_count")) != count_mirrors[
        "simulation_clock_hydrologic_water_budget_recompute_count"
    ]:
        _record_violation(
            violations,
            "clock hydrologic water-budget recompute count does not mirror stages",
        )

    _append_check(
        checks,
        domain="simulation",
        name="coupled_stage_summary_mirrors",
        passed=not violations,
        message=(
            "simulation-clock counters and summary feedback metrics must be "
            "reconstructed from the exported stage history"
        ),
        observed={
            "summary_count_mirrors": {
                field: summary.get(field) for field in count_mirrors
            },
            "clock_feedback_recompute_count": clock.get(
                "feedback_recompute_count"
            ),
            "violation_count": len(violations),
        },
        expected={
            "summary_count_mirrors": count_mirrors,
            "clock_feedback_recompute_count": recomputed_feedback_count,
        },
        evidence={"violations": violations},
    )


def validate_physics_replays(world: dict[str, Any]) -> list[dict[str, Any]]:
    """Deeply replay natural-system physical aggregate and stage diagnostics.

    The helper intentionally has no dependency on the top-level geo validator so
    it can be composed there or exercised independently.  Malformed payloads are
    reported as failed checks instead of propagating conversion errors.
    """

    checks: list[dict[str, Any]] = []
    if not isinstance(world, dict):
        world = {}
    _validate_plate_aggregates(world, checks)
    boundary_edges = validate_plate_boundary_edges(world)
    _append_check(
        checks,
        domain="tectonics",
        name="exact_directed_plate_boundary_segment_replay",
        passed=bool(boundary_edges["passed"]),
        message=(
            "every cross-plate reciprocal control-volume segment, including "
            "duplicate neighbor segments, must replay in canonical order from "
            "the mesh, per-step plate assignments, Euler kinematics, and "
            "opening crust state without legacy smoothed boundary inputs; "
            "candidate sides remain separate from an explicit unknown physical "
            "polarity decision and cannot select a slab"
        ),
        observed=boundary_edges["metrics"],
        expected={
            "authoritative_reciprocal_control_volume_geometry_replayed": True,
            "direct_unsmoothed_euler_kinematics_replayed": True,
            "opening_crust_state_and_polarity_candidate_replayed": True,
            "explicit_unknown_physical_polarity_replayed": True,
            "top_level_euler_parameters_cross_checked": True,
            "step_rotations_replayed": True,
            "plate_center_history_replayed": True,
            "cell_plate_assignments_replayed": True,
            "legacy_smoothed_boundary_fields_used": False,
            "subduction_polarity_resolved": False,
            "subducted_slab_geometry_resolved": False,
        },
        evidence={"violations": boundary_edges["failures"]},
    )
    initial_oceanic_age = validate_initial_oceanic_crust_age(world)
    _append_check(
        checks,
        domain="tectonics",
        name="initial_oceanic_crust_age_graph_replay",
        passed=bool(initial_oceanic_age["passed"]),
        message=(
            "the provisional oceanic-like mask, eligible nominal ridge "
            "segments, global representative spreading rate, multi-source "
            "Dijkstra path witness, ceiling policy, area-weighted summaries, "
            "CDF, and identity-overlap history checkpoint must replay independently; "
            "this procedural initialization is not a physical seafloor "
            "creation, flowline, local spreading-rate, or subduction-history model"
        ),
        observed=initial_oceanic_age["metrics"],
        expected={
            "provisional_oceanic_mask_replayed": True,
            "eligible_ridge_segments_replayed": True,
            "representative_spreading_rates_replayed": True,
            "ridge_seed_cells_replayed": True,
            "dijkstra_unclamped_ages_replayed": True,
            "dijkstra_path_witness_replayed": True,
            "clamped_ages_and_status_replayed": True,
            "summary_statistics_replayed": True,
            "cdf_replayed": True,
            "oceanic_cell_aliases_replayed": True,
            "oceanic_history_aliases_replayed": True,
            "procedural_authority": True,
            "physical_seafloor_creation_resolved": False,
            "spreading_rate_calibrated": False,
            "local_spreading_rates_resolved": False,
            "ridge_flowlines_resolved": False,
            "subduction_sink_history_resolved": False,
            "convergence_history_resolved": False,
            "seton_2020_age_grid_used_as_generation_input": False,
        },
        evidence={"violations": initial_oceanic_age["failures"]},
    )
    _validate_climate_energy(world, checks)
    history, clock, _ = _validate_feedback_structure(world, checks)
    _validate_feedback_summary(world, history, clock, checks)
    crust_transport = validate_crust_overlap_transport(world)
    _append_check(
        checks,
        domain="tectonics",
        name="conservative_crust_overlap_replay",
        passed=bool(crust_transport["passed"]),
        message=(
            "forward spherical overlap CSR, source-area closure, coverage "
            "multiplicity, transported extensive moments, and process split "
            "must replay independently"
        ),
        observed=crust_transport["metrics"],
        expected={
            "source_area_rows_close": True,
            "crust_volume_conserved_during_transport": True,
            "density_weighted_volume_conserved_during_transport": True,
            "age_volume_moment_conserved_during_transport": True,
            "gap_equals_overlap_excess_globally": True,
        },
        evidence={"violations": crust_transport["failures"]},
    )
    oceanic_age_depth = validate_oceanic_age_depth(world)
    _append_check(
        checks,
        domain="tectonics",
        name="oceanic_age_depth_thermal_target_replay",
        passed=bool(oceanic_age_depth["passed"]),
        message=(
            "oceanic-like thermal subsidence targets and continental isostatic "
            "equilibrium targets must replay from round-trip transport/process "
            "age, thickness, density, type, and lithology roots; their full "
            "same-cell target differences are applied outside the bounded "
            "dynamic-relief clamp and must compose exactly into each tectonic "
            "elevation change. This quasi-static operator is not a calibrated "
            "transient relaxation, separately tracked realized thermal-relief "
            "state, absolute basement, heat-flow, flexural, or dynamics solution"
        ),
        observed=oceanic_age_depth["metrics"],
        expected={
            "independent_crust_transport_root_replay_passed": True,
            "analytical_checkpoint_count": 7,
            "initial_isostatic_targets_replayed": True,
            "initial_thermal_aliases_replayed": True,
            "final_thermal_target_replayed": True,
            "isostatic_target_application_replayed": True,
            "dynamic_relief_clamp_replayed": True,
            "tectonic_elevation_change_composition_replayed": True,
            "authoritative_for_relative_thermal_subsidence_target_curve": True,
            "authoritative_for_realized_thermal_relief_component": False,
            "realized_thermal_relief_state_tracked": False,
            "thermal_relaxation_timescale_calibrated": False,
            "unapplied_thermal_tendency_residual_carried_forward": False,
            "unapplied_thermal_equilibrium_residual_zero_by_construction": True,
            "thermal_contribution_outside_bounded_dynamic_relief_clamp_resolved": True,
            "thermal_contribution_to_tectonic_elevation_change_replayed": True,
            "thermal_equilibrium_change_application_replayed": True,
            "absolute_basement_depth_calibrated": False,
            "physical_crust_creation_age_provenance": False,
            "ridge_age_distance_consistency": False,
            "thermal_structure_represented": False,
            "heat_flow_represented": False,
            "dynamic_topography_represented": False,
            "flexure_represented": False,
            "physical_dynamics_represented": False,
        },
        evidence={"violations": oceanic_age_depth["failures"]},
    )
    candidate_fate = validate_crust_overlap_candidate_fate(world)
    _append_check(
        checks,
        domain="tectonics",
        name="overlap_candidate_fate_crosswalk_replay",
        passed=bool(candidate_fate["passed"]),
        message=(
            "every same-step unordered boundary plate-pair consensus and every "
            "multiplicity-at-least-two overlap membership class must replay "
            "independently into a complete diagnostic overlap-excess partition; "
            "the crosswalk may reflect independently validated upstream physical "
            "polarity but cannot originate or promote it; pair endpoint incidence "
            "is coarse pair-wide evidence rather than a local atom/fragment link, "
            "candidate contributor IDs are global contributor-CSR indices, and the "
            "crosswalk cannot allocate material, resolve topology/slab/fate, "
            "calculate swept area, or mutate state or accounting shadows"
        ),
        observed=candidate_fate["metrics"],
        expected={
            "independent_boundary_root_replay_passed": True,
            "independent_membership_root_replay_passed": True,
            "every_boundary_pair_consensus_replayed": True,
            "every_overlap_excess_class_candidate_replayed": True,
            "overlap_excess_partition_closed": True,
            "deterministic_crosswalk_authoritative": True,
            "pair_wide_consensus_only": True,
            "candidate_allocation_authoritative": False,
            "local_segment_link_resolved": False,
            "connected_atom_topology_resolved": False,
            "local_fragment_topology_resolved": False,
            "swept_area_calculated": False,
            "crust_material_shadow_mutation_performed": False,
            "crust_reservoir_mutation_performed": False,
            "physical_material_fate_resolved": False,
            "slab_selection_resolved": False,
            "slab_transfer_resolved": False,
            "state_mutation_performed": False,
        },
        evidence={"violations": candidate_fate["failures"]},
    )
    crust_material_shadow = validate_crust_material_shadow(world)
    _append_check(
        checks,
        domain="tectonics",
        name="persistent_crust_material_shadow_replay",
        passed=bool(crust_material_shadow["passed"]),
        message=(
            "persistent sparse surface-crust dry-rock mass packets, normalized "
            "overlap advection, and ordered unresolved rule source/sink "
            "adjustments must replay independently; this diagnostic shadow is "
            "not an authoritative physical crust-cycle reservoir"
        ),
        observed=crust_material_shadow["metrics"],
        expected={
            "transported_packets_replay": True,
            "ordered_rule_adjustments_replay": True,
            "closing_packets_match_scalar_crust_mass": True,
            "physical_source_sink_resolved": False,
            "global_crust_cycle_mass_conservation_resolved": False,
        },
        evidence={"violations": crust_material_shadow["failures"]},
    )
    crust_dry_rock_accounting = validate_crust_dry_rock_accounting(world)
    _append_check(
        checks,
        domain="tectonics",
        name="finite_crust_dry_rock_accounting_replay",
        passed=bool(crust_dry_rock_accounting["passed"]),
        message=(
            "the bounded surface/exchange/empty-slab dry-rock counter-model, "
            "source-normalized transport, and ordered legacy compensation "
            "transactions must replay independently; numerical closure does "
            "not resolve physical mantle, slab, sediment, phase, or fate"
        ),
        observed=crust_dry_rock_accounting["metrics"],
        expected={
            "finite_exchange_inventory_enforced": True,
            "global_per_origin_and_reservoir_accounting_closed": True,
            "subducted_slab_tables_empty": True,
            "physical_source_sink_resolved": False,
            "material_provenance_resolved": False,
            "global_crust_cycle_mass_conservation_resolved": False,
        },
        evidence={"violations": crust_dry_rock_accounting["failures"]},
    )
    sediment_source_partitions = validate_sediment_source_partitions(world)
    _append_check(
        checks,
        domain="sediment",
        name="sediment_alluvium_bedrock_source_partition_replay",
        passed=bool(sediment_source_partitions["passed"]),
        message=(
            "hillslope, fluvial, and glacial per-cell production demand must "
            "partition alluvium first and bedrock second, reconstruct every "
            "bulk-volume aggregate, and retain explicit non-mass, "
            "non-provenance semantics"
        ),
        observed=sediment_source_partitions["metrics"],
        expected={
            "source_demand_partitioned_per_cell": True,
            "bulk_reference_volume_reconstructed": True,
            "alluvium_first_rule_replayed": True,
            "dry_rock_mass_claim": False,
            "material_provenance_claim": False,
        },
        evidence={"violations": sediment_source_partitions["failures"]},
    )
    sediment_interfaces = validate_sediment_interfaces(world)
    _append_check(
        checks,
        domain="sediment",
        name="bedrock_mobile_sediment_interface_replay",
        passed=bool(sediment_interfaces["passed"]),
        message=(
            "the canonical bedrock surface must replay from initial terrain, "
            "tectonic displacement, bedrock-only erosion, and sea-level datum "
            "changes, while surface elevation closes as bedrock plus mobile "
            "sediment; this geometric state does not claim dry mass, "
            "porosity, compaction, or grain provenance"
        ),
        observed=sediment_interfaces["metrics"],
        expected={
            "authoritative_interface_geometry": True,
            "surface_elevation_derived_from_interfaces": True,
            "all_native_sediment_mutation_paths_replayed": True,
            "dry_rock_mass_resolved": False,
            "porosity_resolved": False,
            "grain_provenance_resolved": False,
        },
        evidence={"violations": sediment_interfaces["failures"]},
    )
    return checks


__all__ = ["validate_physics_replays"]
