"""Loading the validation manifest."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from ._constants import (
    COMPARISON_OPERATORS,
    GEO_VALIDATION_SUITE_SCHEMA_VERSION,
    MAX_SCENARIO_COUNT,
)
from .errors import GeoValidationSuiteError
from ._helpers import _finite, _required_text
from .empirical import _normalize_empirical_calibration


def _normalize_expectations(raw: Any, context: str) -> dict[str, dict[str, float]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise GeoValidationSuiteError(f"{context} expectations must be an object")
    expectations: dict[str, dict[str, float]] = {}
    for raw_metric, raw_bounds in raw.items():
        metric = _required_text(raw_metric, f"{context} expectation metric")
        if not isinstance(raw_bounds, dict) or not raw_bounds:
            raise GeoValidationSuiteError(f"{context} expectation '{metric}' must define min and/or max")
        unknown = set(raw_bounds) - {"min", "max"}
        if unknown:
            raise GeoValidationSuiteError(
                f"{context} expectation '{metric}' has unknown bounds: {', '.join(sorted(unknown))}"
            )
        bounds = {
            name: _finite(value, f"{context} expectation '{metric}' {name}")
            for name, value in raw_bounds.items()
        }
        if "min" in bounds and "max" in bounds and bounds["max"] < bounds["min"]:
            raise GeoValidationSuiteError(f"{context} expectation '{metric}' range is inverted")
        expectations[metric] = bounds
    return expectations


def load_geo_validation_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GeoValidationSuiteError(f"invalid geo validation manifest: {path}") from exc
    if not isinstance(payload, dict):
        raise GeoValidationSuiteError("geo validation manifest root must be an object")
    unknown_root_keys = set(payload) - {"schema_version", "name", "scenarios", "relations"}
    if unknown_root_keys:
        raise GeoValidationSuiteError(
            "geo validation manifest has unknown fields: "
            + ", ".join(sorted(unknown_root_keys))
        )
    if payload.get("schema_version") != GEO_VALIDATION_SUITE_SCHEMA_VERSION:
        raise GeoValidationSuiteError(
            f"geo validation manifest schema_version must be {GEO_VALIDATION_SUITE_SCHEMA_VERSION}"
        )
    name = _required_text(payload.get("name"), "geo validation manifest name")
    raw_scenarios = payload.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise GeoValidationSuiteError("geo validation manifest requires a non-empty scenarios list")
    if len(raw_scenarios) > MAX_SCENARIO_COUNT:
        raise GeoValidationSuiteError(
            f"geo validation manifest cannot exceed {MAX_SCENARIO_COUNT} scenarios"
        )
    scenarios: list[dict[str, Any]] = []
    scenario_ids: set[str] = set()
    for index, raw_scenario in enumerate(raw_scenarios):
        context = f"geo validation scenario {index}"
        if not isinstance(raw_scenario, dict):
            raise GeoValidationSuiteError(f"{context} must be an object")
        unknown_scenario_keys = set(raw_scenario) - {
            "id",
            "description",
            "empirical_calibration",
            "profile",
            "overrides",
            "expectations",
            "repeat",
            "tags",
        }
        if unknown_scenario_keys:
            raise GeoValidationSuiteError(
                f"{context} has unknown fields: {', '.join(sorted(unknown_scenario_keys))}"
            )
        scenario_id = _required_text(raw_scenario.get("id"), f"{context} id")
        if scenario_id in scenario_ids:
            raise GeoValidationSuiteError(f"geo validation manifest duplicates scenario id '{scenario_id}'")
        profile = _required_text(raw_scenario.get("profile", "generic"), f"{context} profile")
        if profile not in {"generic", "earthlike"}:
            raise GeoValidationSuiteError(f"{context} profile must be generic or earthlike")
        overrides = raw_scenario.get("overrides", {})
        if not isinstance(overrides, dict):
            raise GeoValidationSuiteError(f"{context} overrides must be an object")
        repeat = raw_scenario.get("repeat", 1)
        if isinstance(repeat, bool) or not isinstance(repeat, int) or not 1 <= repeat <= 3:
            raise GeoValidationSuiteError(f"{context} repeat must be an integer from 1 to 3")
        raw_tags = raw_scenario.get("tags", [])
        if not isinstance(raw_tags, list):
            raise GeoValidationSuiteError(f"{context} tags must be a list")
        tags = sorted({_required_text(tag, f"{context} tag") for tag in raw_tags})
        scenarios.append(
            {
                "id": scenario_id,
                "description": str(raw_scenario.get("description", "")).strip(),
                "profile": profile,
                "overrides": deepcopy(overrides),
                "expectations": _normalize_expectations(raw_scenario.get("expectations"), context),
                "empirical_calibration": _normalize_empirical_calibration(
                    raw_scenario.get("empirical_calibration"),
                    manifest_path=path,
                    context=context,
                ),
                "repeat": repeat,
                "tags": tags,
            }
        )
        scenario_ids.add(scenario_id)

    relations: list[dict[str, Any]] = []
    raw_relations = payload.get("relations", [])
    if not isinstance(raw_relations, list):
        raise GeoValidationSuiteError("geo validation manifest relations must be a list")
    relation_ids: set[str] = set()
    for index, raw_relation in enumerate(raw_relations):
        context = f"geo validation relation {index}"
        if not isinstance(raw_relation, dict):
            raise GeoValidationSuiteError(f"{context} must be an object")
        unknown_relation_keys = set(raw_relation) - {
            "id",
            "description",
            "left",
            "right",
            "metric",
            "operator",
            "minimum_difference",
            "tolerance",
        }
        if unknown_relation_keys:
            raise GeoValidationSuiteError(
                f"{context} has unknown fields: {', '.join(sorted(unknown_relation_keys))}"
            )
        relation_id = _required_text(raw_relation.get("id"), f"{context} id")
        if relation_id in relation_ids:
            raise GeoValidationSuiteError(f"geo validation manifest duplicates relation id '{relation_id}'")
        left = _required_text(raw_relation.get("left"), f"{context} left")
        right = _required_text(raw_relation.get("right"), f"{context} right")
        if left not in scenario_ids or right not in scenario_ids:
            raise GeoValidationSuiteError(f"{context} references an unknown scenario")
        if left == right:
            raise GeoValidationSuiteError(f"{context} must compare two different scenarios")
        metric = _required_text(raw_relation.get("metric"), f"{context} metric")
        operator = _required_text(raw_relation.get("operator"), f"{context} operator")
        if operator not in COMPARISON_OPERATORS:
            raise GeoValidationSuiteError(
                f"{context} operator must be one of {', '.join(sorted(COMPARISON_OPERATORS))}"
            )
        minimum_difference = _finite(
            raw_relation.get("minimum_difference", 0.0), f"{context} minimum_difference"
        )
        if minimum_difference < 0.0:
            raise GeoValidationSuiteError(f"{context} minimum_difference must be non-negative")
        if operator == "eq" and minimum_difference != 0.0:
            raise GeoValidationSuiteError(
                f"{context} equality relations require minimum_difference=0"
            )
        tolerance = _finite(raw_relation.get("tolerance", 1.0e-9), f"{context} tolerance")
        if tolerance < 0.0:
            raise GeoValidationSuiteError(f"{context} tolerance must be non-negative")
        relations.append(
            {
                "id": relation_id,
                "description": str(raw_relation.get("description", "")).strip(),
                "left": left,
                "right": right,
                "metric": metric,
                "operator": operator,
                "minimum_difference": minimum_difference,
                "tolerance": tolerance,
            }
        )
        relation_ids.add(relation_id)
    return {
        "schema_version": GEO_VALIDATION_SUITE_SCHEMA_VERSION,
        "name": name,
        "scenarios": scenarios,
        "relations": relations,
    }
