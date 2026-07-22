"""Evaluating expectations, relations, and empirical fit."""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from typing import Any, Callable

from pydantic import ValidationError

from ..api import generate_geo_world
from ..calibration import CalibrationError, evaluate_calibration_targets
from ..config import WorldConfig
from ..geo_validation import (
    GEO_MODEL_LIMITATIONS,
    GEO_VALIDATION_SCOPE,
    extract_geo_metrics,
    validate_geo_world,
)
from ._constants import (
    CIVILIZATION_NESTED_FIELDS,
    CIVILIZATION_TOP_LEVEL_FIELDS,
    GEO_VALIDATION_SUITE_SCHEMA_VERSION,
)
from .errors import GeoValidationSuiteError
from ._helpers import _deep_merge


def geo_fingerprint(world: dict[str, Any]) -> str:
    def natural_projection(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: natural_projection(item)
                for key, item in value.items()
                if key not in CIVILIZATION_NESTED_FIELDS
                and key not in CIVILIZATION_TOP_LEVEL_FIELDS
            }
        if isinstance(value, list):
            return [natural_projection(item) for item in value]
        if isinstance(value, float) and not math.isfinite(value):
            return {"nonfinite_float": str(value)}
        return value

    projection = {
        key: natural_projection(value)
        for key, value in world.items()
        if key not in CIVILIZATION_TOP_LEVEL_FIELDS
    }
    encoded = json.dumps(projection, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _evaluate_expectations(
    scenario_id: str,
    metrics: dict[str, Any],
    expectations: dict[str, dict[str, float]],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for metric, bounds in expectations.items():
        raw_value = metrics.get(metric)
        numeric = isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool) and math.isfinite(float(raw_value))
        passed = numeric
        if numeric and "min" in bounds:
            passed = passed and float(raw_value) >= bounds["min"]
        if numeric and "max" in bounds:
            passed = passed and float(raw_value) <= bounds["max"]
        checks.append(
            {
                "id": len(checks),
                "scenario_id": scenario_id,
                "metric": metric,
                "passed": passed,
                "observed": raw_value,
                "expected": bounds,
                "message": "scenario metric is within its regime-specific envelope" if passed else "scenario metric violates its regime-specific envelope",
            }
        )
    return checks


def _evaluate_relation(
    relation: dict[str, Any],
    metrics_by_scenario: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    metric = relation["metric"]
    left_raw = metrics_by_scenario[relation["left"]].get(metric)
    right_raw = metrics_by_scenario[relation["right"]].get(metric)
    numeric = all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        for value in (left_raw, right_raw)
    )
    passed = False
    difference = None
    if numeric:
        left = float(left_raw)
        right = float(right_raw)
        difference = left - right
        minimum = float(relation["minimum_difference"])
        tolerance = float(relation["tolerance"])
        operator = relation["operator"]
        if operator == "lt":
            passed = left < right and left <= right - minimum + tolerance
        elif operator == "le":
            passed = left <= right - minimum + tolerance
        elif operator == "gt":
            passed = left > right and left >= right + minimum - tolerance
        elif operator == "ge":
            passed = left >= right + minimum - tolerance
        else:
            passed = abs(left - right) <= tolerance
    return {
        **relation,
        "passed": passed,
        "left_value": left_raw,
        "right_value": right_raw,
        "difference": difference,
        "message": "paired scenario response is coherent" if passed else "paired scenario response is missing or incoherent",
    }


def _evaluate_empirical_calibration(
    scenario_id: str,
    definition: dict[str, Any] | None,
    world: dict[str, Any],
) -> dict[str, Any] | None:
    if definition is None:
        return None
    bundle = definition["target_bundle"]
    try:
        evaluation = evaluate_calibration_targets(world, bundle["targets"])
    except CalibrationError as exc:
        raise GeoValidationSuiteError(
            f"scenario '{scenario_id}' external empirical calibration failed: {exc}"
        ) from exc
    summary = evaluation["summary"]
    check_count = int(summary["external_calibration_check_count"])
    pass_count = int(summary["external_calibration_pass_count"])
    complete = bool(summary["external_calibration_complete"])
    all_targets_passed = complete and check_count > 0 and pass_count == check_count
    require_complete = bool(definition["require_complete"])
    require_all_passed = bool(definition["require_all_passed"])
    policy_passed = (
        (complete or not require_complete)
        and (all_targets_passed or not require_all_passed)
    )
    bundle_provenance = {
        key: deepcopy(value)
        for key, value in bundle.items()
        if key != "targets"
    }
    return {
        "target_bundle": bundle_provenance,
        "policy": {
            "require_complete": require_complete,
            "require_all_passed": require_all_passed,
        },
        "policy_passed": policy_passed,
        "coverage_complete": complete,
        "all_targets_passed": all_targets_passed,
        **evaluation,
        "failed_checks": [
            check for check in evaluation["checks"] if not bool(check["passed"])
        ],
    }


def evaluate_geo_validation_suite(
    base_config: WorldConfig,
    manifest: dict[str, Any],
    *,
    world_factory: Callable[[WorldConfig], dict[str, Any]] = generate_geo_world,
    progress: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if manifest.get("schema_version") != GEO_VALIDATION_SUITE_SCHEMA_VERSION:
        raise GeoValidationSuiteError("geo validation manifest was not loaded or normalized")
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise GeoValidationSuiteError("geo validation manifest has no scenarios")
    base_data = base_config.model_dump(mode="python")
    members: list[dict[str, Any]] = []
    for index, scenario in enumerate(scenarios):
        if progress is not None:
            progress(index, len(scenarios), scenario)
        config_data = _deep_merge(base_data, scenario["overrides"])
        if not bool(config_data.get("output", {}).get("include_cells", False)):
            raise GeoValidationSuiteError(
                f"scenario '{scenario['id']}' must keep output.include_cells=true for deep validation"
            )
        try:
            config = type(base_config).model_validate(config_data)
        except ValidationError as exc:
            raise GeoValidationSuiteError(f"scenario '{scenario['id']}' config is invalid: {exc}") from exc
        fingerprints: list[str] = []
        first_world: dict[str, Any] | None = None
        for _repeat_index in range(int(scenario["repeat"])):
            try:
                world = world_factory(config)
            except RuntimeError as exc:
                raise GeoValidationSuiteError(
                    f"scenario '{scenario['id']}' generation failed: {exc}"
                ) from exc
            fingerprints.append(geo_fingerprint(world))
            if first_world is None:
                first_world = world
        assert first_world is not None
        validation = validate_geo_world(first_world, profile=scenario["profile"])
        metrics = extract_geo_metrics(first_world)
        expectation_checks = _evaluate_expectations(
            scenario["id"], metrics, scenario["expectations"]
        )
        determinism_tested = int(scenario["repeat"]) >= 2
        deterministic: bool | None = (
            len(set(fingerprints)) == 1 if determinism_tested else None
        )
        internal_validation_passed = (
            bool(validation["passed"])
            and all(check["passed"] for check in expectation_checks)
            and deterministic is not False
        )
        empirical_calibration = _evaluate_empirical_calibration(
            scenario["id"], scenario.get("empirical_calibration"), first_world
        )
        empirical_calibration_passed = (
            None
            if empirical_calibration is None
            else bool(empirical_calibration["policy_passed"])
        )
        member_passed = (
            internal_validation_passed
            and empirical_calibration_passed is not False
        )
        members.append(
            {
                "id": scenario["id"],
                "description": scenario["description"],
                "profile": scenario["profile"],
                "tags": scenario["tags"],
                "repeat": scenario["repeat"],
                "passed": member_passed,
                "internal_validation_passed": internal_validation_passed,
                "empirical_calibration_configured": empirical_calibration is not None,
                "empirical_calibration_passed": empirical_calibration_passed,
                "empirical_calibration": empirical_calibration,
                "determinism_tested": determinism_tested,
                "deterministic": deterministic,
                "geo_fingerprint_sha256": fingerprints[0],
                "geo_fingerprint_sha256_by_repeat": fingerprints,
                "config": config.model_dump(mode="json"),
                "metrics": metrics,
                "validation_summary": validation["summary"],
                "validation_failures": [
                    check
                    for check in validation["checks"]
                    if check["status"] == "failed" and check["severity"] == "error"
                ],
                "realism_deviations": [
                    check
                    for check in validation["checks"]
                    if check["status"] == "failed" and check["severity"] == "warning"
                ],
                "not_applicable_realism_checks": [
                    check["name"]
                    for check in validation["checks"]
                    if check["domain"] == "realism_evidence" and check["status"] == "not_applicable"
                ],
                "expectation_checks": expectation_checks,
            }
        )

    metrics_by_scenario = {member["id"]: member["metrics"] for member in members}
    relation_results = [
        _evaluate_relation(relation, metrics_by_scenario)
        for relation in manifest.get("relations", [])
    ]
    member_pass_count = sum(member["passed"] for member in members)
    internal_member_pass_count = sum(
        member["internal_validation_passed"] for member in members
    )
    relation_pass_count = sum(relation["passed"] for relation in relation_results)
    empirical_members = [
        member for member in members if member["empirical_calibration_configured"]
    ]
    empirical_policy_pass_count = sum(
        member["empirical_calibration_passed"] is True
        for member in empirical_members
    )
    empirical_check_count = sum(
        int(member["empirical_calibration"]["summary"]["external_calibration_check_count"])
        for member in empirical_members
    )
    empirical_evaluated_count = sum(
        int(member["empirical_calibration"]["summary"]["external_calibration_evaluated_metric_count"])
        for member in empirical_members
    )
    empirical_pass_count = sum(
        int(member["empirical_calibration"]["summary"]["external_calibration_pass_count"])
        for member in empirical_members
    )
    empirical_missing_count = sum(
        int(member["empirical_calibration"]["summary"]["external_calibration_missing_metric_count"])
        for member in empirical_members
    )
    empirical_failed_checks = [
        {"scenario_id": member["id"], **check}
        for member in empirical_members
        for check in member["empirical_calibration"]["failed_checks"]
    ]
    all_passed = member_pass_count == len(members) and relation_pass_count == len(relation_results)
    return {
        "schema_version": GEO_VALIDATION_SUITE_SCHEMA_VERSION,
        "report_type": "geo_pipeline_validation_suite_v1",
        "name": manifest["name"],
        "scope": GEO_VALIDATION_SCOPE,
        "excluded_scope": "civilization and all settlement, political, cultural, historical, demographic, economic, market, campaign, and language layers",
        "model_limitations": list(GEO_MODEL_LIMITATIONS),
        "passed": all_passed,
        "summary": {
            "scenario_count": len(members),
            "scenario_pass_count": member_pass_count,
            "scenario_pass_fraction": round(member_pass_count / len(members), 6),
            "internal_scenario_pass_count": internal_member_pass_count,
            "internal_scenario_pass_fraction": round(
                internal_member_pass_count / len(members), 6
            ),
            "relation_count": len(relation_results),
            "relation_pass_count": relation_pass_count,
            "relation_pass_fraction": round(relation_pass_count / len(relation_results), 6)
            if relation_results
            else None,
            "response_validation_performed": bool(relation_results),
            "determinism_tested_scenario_count": sum(
                bool(member["determinism_tested"]) for member in members
            ),
            "deterministic_scenario_count": sum(
                member["deterministic"] is True for member in members
            ),
            "empirical_calibration_scenario_count": len(empirical_members),
            "empirical_calibration_policy_pass_count": empirical_policy_pass_count,
            "empirical_calibration_check_count": empirical_check_count,
            "empirical_calibration_evaluated_metric_count": empirical_evaluated_count,
            "empirical_calibration_pass_count": empirical_pass_count,
            "empirical_calibration_missing_metric_count": empirical_missing_count,
            "empirical_calibration_metric_coverage_fraction": (
                round(empirical_evaluated_count / empirical_check_count, 6)
                if empirical_check_count
                else None
            ),
            "empirical_calibration_pass_fraction": (
                round(empirical_pass_count / empirical_check_count, 6)
                if empirical_check_count
                else None
            ),
            "empirical_calibration_evaluated_pass_fraction": (
                round(empirical_pass_count / empirical_evaluated_count, 6)
                if empirical_evaluated_count
                else None
            ),
            "all_internal_scenarios_passed": internal_member_pass_count == len(members),
            "all_empirical_calibrations_passed": (
                empirical_policy_pass_count == len(empirical_members)
                if empirical_members
                else None
            ),
            "all_scenarios_passed": member_pass_count == len(members),
            "all_relations_passed": (
                relation_pass_count == len(relation_results) if relation_results else None
            ),
        },
        "empirical_calibration": {
            "scope": (
                "external empirical Earth-reference model-fit targets; independent "
                "from structural, conservation, determinism, and paired-response validation"
            ),
            "configured_scenario_ids": [member["id"] for member in empirical_members],
            "failed_checks": empirical_failed_checks,
        },
        "members": members,
        "relations": relation_results,
    }
