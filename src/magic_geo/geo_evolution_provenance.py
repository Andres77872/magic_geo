"""Truthful temporal provenance for natural generation outputs.

Many exported objects use the word ``history``.  Only some of them are direct
records of state-mutating native pipeline stages; others are bounded diagnostic
trajectories reconstructed from the final state.  Keeping the distinction in a
machine-readable registry prevents downstream users from treating a synthetic
sequence as a physically timed simulation.
"""

from __future__ import annotations

import math
from typing import Any


EVOLUTION_PROVENANCE_MODEL_TYPE = "geo_evolution_provenance_registry_v2"
NOMINAL_TIME_MODEL = "configured_maturation_timestep_nominal_elapsed_time_v1"
NOMINAL_TIME_BASIS = (
    "configured_maturation_timestep_ma_per_erosion_transition_v1"
)
NOMINAL_TIME_SOURCE_PARAMETER = "erosion.maturation_timestep_ma"
SOIL_LINKED_TIME_BASIS = "posthoc_diagnostic_steps_linked_to_native_nominal_endpoints"


NATIVE_STATE_HISTORY_FAMILIES: tuple[str, ...] = (
    "plate_motion_history",
    "earth_system_feedback_history",
    "hydrologic_water_budget_history",
    "numeric_depression_correction_history",
    "hillslope_sediment_transport_history",
    "fluvial_sediment_routing_history",
    "glacial_sediment_transport_history",
)


NATIVE_STATE_MUTATION_EVIDENCE: dict[str, str] = {
    family: (
        "mixed"
        if family == "numeric_depression_correction_history"
        else "yes"
    )
    for family in NATIVE_STATE_HISTORY_FAMILIES
}


DIAGNOSTIC_TRAJECTORY_FAMILIES: tuple[str, ...] = (
    "climate_seasonal_histories",
    "lake_overflow_histories",
    "lake_overflow_channel_histories",
    "river_reorganization_histories",
    "sediment_routing_histories",
    "sediment_transport_histories",
    "sequence_stratigraphy_histories",
    "ice_sheet_histories",
    "ice_sheet_stability_histories",
    "ice_flowline_histories",
    "soil_profile_histories",
    "vegetation_succession_histories",
    "wildfire_spread_histories",
)


def enrich_world_with_geo_evolution_provenance(
    world: dict[str, Any],
) -> dict[str, Any]:
    """Attach a complete history-family classification to a geo-only world."""

    clock = world.get("simulation_clock")
    clock_record = clock if isinstance(clock, dict) else {}
    families: list[dict[str, Any]] = []
    for family in NATIVE_STATE_HISTORY_FAMILIES:
        records = world.get(family)
        families.append(
            {
                "family": family,
                "record_count": len(records) if isinstance(records, list) else -1,
                "temporal_role": (
                    "native_mixed_mutation_and_counterfactual_event_ledger"
                    if family == "numeric_depression_correction_history"
                    else "native_state_mutation_ledger"
                ),
                "state_mutation_evidence": NATIVE_STATE_MUTATION_EVIDENCE[
                    family
                ],
                "physical_time_resolved": False,
                "nominal_time_coordinate_available": True,
                "nominal_time_calibrated": False,
                "time_basis": NOMINAL_TIME_BASIS,
            }
        )
    for family in DIAGNOSTIC_TRAJECTORY_FAMILIES:
        records = world.get(family)
        linked_nominal_coordinate = (
            family == "soil_profile_histories"
            and isinstance(world.get("soil_pedogenesis_model"), dict)
            and world["soil_pedogenesis_model"].get(
                "linked_nominal_time_coordinate_available"
            )
            is True
        )
        families.append(
            {
                "family": family,
                "record_count": len(records) if isinstance(records, list) else -1,
                "temporal_role": "posthoc_diagnostic_trajectory",
                "state_mutation_evidence": "no",
                "physical_time_resolved": False,
                "nominal_time_coordinate_available": linked_nominal_coordinate,
                "nominal_time_calibrated": False,
                "nominal_time_linkage": (
                    "contextual_native_stage_link_without_state_mutation"
                    if linked_nominal_coordinate
                    else "none"
                ),
                "time_basis": (
                    "monthly_climatology"
                    if family == "climate_seasonal_histories"
                    else (
                        SOIL_LINKED_TIME_BASIS
                        if linked_nominal_coordinate
                        else "diagnostic_index_step"
                    )
                ),
            }
        )

    world["geo_evolution_provenance"] = {
        "model_type": EVOLUTION_PROVENANCE_MODEL_TYPE,
        "generation_scope": str(world.get("generation_scope", "unknown")),
        "physical_time_resolved": False,
        "nominal_time_coordinate_available": True,
        "nominal_time_calibrated": False,
        "nominal_time_model": NOMINAL_TIME_MODEL,
        "nominal_time_basis": NOMINAL_TIME_BASIS,
        "nominal_time_source_parameter": NOMINAL_TIME_SOURCE_PARAMETER,
        "nominal_timestep_ma": clock_record.get("nominal_timestep_ma"),
        "final_nominal_elapsed_time_ma": clock_record.get(
            "final_nominal_elapsed_time_ma"
        ),
        "native_state_history_family_count": len(NATIVE_STATE_HISTORY_FAMILIES),
        "diagnostic_trajectory_family_count": len(
            DIAGNOSTIC_TRAJECTORY_FAMILIES
        ),
        "family_count": len(families),
        "native_state_history_families": list(NATIVE_STATE_HISTORY_FAMILIES),
        "diagnostic_trajectory_families": list(
            DIAGNOSTIC_TRAJECTORY_FAMILIES
        ),
        "families": families,
        "limitations": [
            "native mutation histories use a nominal geological coordinate, not calibrated physical time",
            "reference-step scaling has not demonstrated whole-coupling timestep convergence",
            "diagnostic trajectories do not prove that intermediate states mutated the world",
            "soil, vegetation, species, and wildfire diagnostics do not feed back into the native physical clock",
            "the cryosphere mutates terrain once in a final bulk coupling stage",
        ],
    }
    return world


def validate_geo_evolution_provenance(world: Any) -> dict[str, Any]:
    """Return one standardized fatal check for the temporal registry."""

    violations: list[str] = []
    root = world if isinstance(world, dict) else {}
    provenance = root.get("geo_evolution_provenance")
    if not isinstance(provenance, dict):
        provenance = {}
        violations.append("geo_evolution_provenance must be an object")

    if provenance.get("model_type") != EVOLUTION_PROVENANCE_MODEL_TYPE:
        violations.append("model_type")
    if provenance.get("generation_scope") != "geo_only":
        violations.append("generation_scope")
    if provenance.get("physical_time_resolved") is not False:
        violations.append("physical_time_resolved must be false")
    if provenance.get("nominal_time_coordinate_available") is not True:
        violations.append("nominal_time_coordinate_available")
    if provenance.get("nominal_time_calibrated") is not False:
        violations.append("nominal_time_calibrated must be false")
    if provenance.get("nominal_time_model") != NOMINAL_TIME_MODEL:
        violations.append("nominal_time_model")
    if provenance.get("nominal_time_basis") != NOMINAL_TIME_BASIS:
        violations.append("nominal_time_basis")
    if (
        provenance.get("nominal_time_source_parameter")
        != NOMINAL_TIME_SOURCE_PARAMETER
    ):
        violations.append("nominal_time_source_parameter")

    clock = root.get("simulation_clock")
    if not isinstance(clock, dict) or clock.get("physical_time_resolved") is not False:
        violations.append("simulation_clock physical-time mirror")
        clock = {}
    if (
        clock.get("nominal_time_model") != NOMINAL_TIME_MODEL
        or clock.get("nominal_time_basis") != NOMINAL_TIME_BASIS
        or clock.get("nominal_time_source_parameter")
        != NOMINAL_TIME_SOURCE_PARAMETER
        or clock.get("nominal_time_calibrated") is not False
    ):
        violations.append("simulation_clock nominal-time mirror")
    if provenance.get("nominal_timestep_ma") != clock.get("nominal_timestep_ma"):
        violations.append("nominal_timestep_ma mirror")
    if provenance.get("final_nominal_elapsed_time_ma") != clock.get(
        "final_nominal_elapsed_time_ma"
    ):
        violations.append("final_nominal_elapsed_time_ma mirror")

    native = provenance.get("native_state_history_families")
    diagnostic = provenance.get("diagnostic_trajectory_families")
    if native != list(NATIVE_STATE_HISTORY_FAMILIES):
        violations.append("native family registry")
    if diagnostic != list(DIAGNOSTIC_TRAJECTORY_FAMILIES):
        violations.append("diagnostic family registry")

    raw_families = provenance.get("families")
    if not isinstance(raw_families, list) or not all(
        isinstance(record, dict) for record in raw_families
    ):
        raw_families = []
        violations.append("family records")
    by_name = {
        str(record.get("family", "")): record for record in raw_families
    }
    expected_names = set(NATIVE_STATE_HISTORY_FAMILIES) | set(
        DIAGNOSTIC_TRAJECTORY_FAMILIES
    )
    if set(by_name) != expected_names or len(by_name) != len(raw_families):
        violations.append("family record coverage/uniqueness")

    for family in expected_names:
        record = by_name.get(family, {})
        payload = root.get(family)
        expected_native = family in NATIVE_STATE_HISTORY_FAMILIES
        if not isinstance(payload, list):
            violations.append(f"{family}: payload is not a list")
            continue
        if record.get("record_count") != len(payload):
            violations.append(f"{family}: record_count")
        expected_mutation_evidence = (
            NATIVE_STATE_MUTATION_EVIDENCE[family]
            if expected_native
            else "no"
        )
        if record.get("state_mutation_evidence") != expected_mutation_evidence:
            violations.append(f"{family}: state_mutation_evidence")
        expected_role = (
            "native_mixed_mutation_and_counterfactual_event_ledger"
            if family == "numeric_depression_correction_history"
            else (
                "native_state_mutation_ledger"
                if expected_native
                else "posthoc_diagnostic_trajectory"
            )
        )
        if record.get("temporal_role") != expected_role:
            violations.append(f"{family}: temporal_role")
        if record.get("physical_time_resolved") is not False:
            violations.append(f"{family}: physical_time_resolved")
        if record.get("nominal_time_calibrated") is not False:
            violations.append(f"{family}: nominal_time_calibrated")
        expected_linked_soil_coordinate = (
            family == "soil_profile_histories"
            and isinstance(root.get("soil_pedogenesis_model"), dict)
            and root["soil_pedogenesis_model"].get(
                "linked_nominal_time_coordinate_available"
            )
            is True
        )
        expected_nominal_coordinate = (
            expected_native or expected_linked_soil_coordinate
        )
        if (
            record.get("nominal_time_coordinate_available")
            is not expected_nominal_coordinate
        ):
            violations.append(
                f"{family}: nominal_time_coordinate_available"
            )
        expected_time_basis = (
            NOMINAL_TIME_BASIS
            if expected_native
            else (
                "monthly_climatology"
                if family == "climate_seasonal_histories"
                else (
                    SOIL_LINKED_TIME_BASIS
                    if expected_linked_soil_coordinate
                    else "diagnostic_index_step"
                )
            )
        )
        if record.get("time_basis") != expected_time_basis:
            violations.append(f"{family}: time_basis")
        expected_linkage = (
            "contextual_native_stage_link_without_state_mutation"
            if expected_linked_soil_coordinate
            else "none"
        )
        if not expected_native and record.get("nominal_time_linkage") != expected_linkage:
            violations.append(f"{family}: nominal_time_linkage")
        if expected_native:
            for index, native_record in enumerate(payload):
                if not isinstance(native_record, dict):
                    violations.append(f"{family}[{index}]: record")
                    continue
                if (
                    native_record.get("nominal_time_model")
                    != NOMINAL_TIME_MODEL
                    or native_record.get("nominal_time_basis")
                    != NOMINAL_TIME_BASIS
                    or native_record.get("nominal_time_source_parameter")
                    != NOMINAL_TIME_SOURCE_PARAMETER
                    or native_record.get("nominal_time_unit") != "Ma"
                    or native_record.get("nominal_time_calibrated") is not False
                    or native_record.get("physical_time_resolved") is not False
                ):
                    violations.append(f"{family}[{index}]: nominal metadata")
                    continue
                try:
                    start = float(native_record["nominal_interval_start_ma"])
                    end = float(native_record["nominal_interval_end_ma"])
                    duration = float(
                        native_record["nominal_interval_duration_ma"]
                    )
                    elapsed = float(native_record["nominal_elapsed_time_ma"])
                except (KeyError, TypeError, ValueError):
                    violations.append(f"{family}[{index}]: nominal interval")
                    continue
                tolerance = max(1.0e-12, abs(end) * 1.0e-12)
                if (
                    not all(math.isfinite(value) for value in (
                        start,
                        end,
                        duration,
                        elapsed,
                    ))
                    or start < 0.0
                    or end + tolerance < start
                    or not math.isclose(
                        duration,
                        end - start,
                        abs_tol=tolerance,
                    )
                    or not math.isclose(elapsed, end, abs_tol=tolerance)
                    or native_record.get("advances_nominal_time")
                    is not (duration > 0.0)
                ):
                    violations.append(
                        f"{family}[{index}]: nominal interval consistency"
                    )

    if provenance.get("family_count") != len(expected_names):
        violations.append("family_count")
    if provenance.get("native_state_history_family_count") != len(
        NATIVE_STATE_HISTORY_FAMILIES
    ):
        violations.append("native_state_history_family_count")
    if provenance.get("diagnostic_trajectory_family_count") != len(
        DIAGNOSTIC_TRAJECTORY_FAMILIES
    ):
        violations.append("diagnostic_trajectory_family_count")

    passed = not violations
    return {
        "id": 0,
        "domain": "evolution_provenance",
        "name": "history_family_temporal_semantics",
        "status": "passed" if passed else "failed",
        "passed": passed,
        "severity": "error",
        "message": (
            "Every natural history family declares whether it records native state mutation or a post-hoc diagnostic trajectory."
            if passed
            else "Natural history temporal roles, counts, or physical-time claims are inconsistent."
        ),
        "observed": {
            "family_record_count": len(raw_families),
            "violation_count": len(violations),
        },
        "expected": {
            "native_state_history_family_count": len(
                NATIVE_STATE_HISTORY_FAMILIES
            ),
            "diagnostic_trajectory_family_count": len(
                DIAGNOSTIC_TRAJECTORY_FAMILIES
            ),
            "physical_time_resolved": False,
            "nominal_time_coordinate_available": True,
            "nominal_time_calibrated": False,
        },
        "evidence": {"violations": violations},
    }


__all__ = [
    "DIAGNOSTIC_TRAJECTORY_FAMILIES",
    "EVOLUTION_PROVENANCE_MODEL_TYPE",
    "NOMINAL_TIME_BASIS",
    "NOMINAL_TIME_MODEL",
    "NOMINAL_TIME_SOURCE_PARAMETER",
    "SOIL_LINKED_TIME_BASIS",
    "NATIVE_STATE_HISTORY_FAMILIES",
    "NATIVE_STATE_MUTATION_EVIDENCE",
    "enrich_world_with_geo_evolution_provenance",
    "validate_geo_evolution_provenance",
]
