from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .api import generate_world
from .calibration import CalibrationError, evaluate_calibration_targets
from .config import WorldConfig


ENSEMBLE_SCHEMA_VERSION = 1
ENSEMBLE_REPORT_TYPE = "calibration_ensemble_v1"
MAX_ENSEMBLE_MEMBER_COUNT = 256


def _required_text(payload: dict[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CalibrationError(f"{context} requires non-empty '{key}'")
    return value.strip()


def load_calibration_ensemble_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CalibrationError(f"invalid calibration ensemble JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CalibrationError("calibration ensemble manifest must be an object")
    if payload.get("schema_version") != ENSEMBLE_SCHEMA_VERSION:
        raise CalibrationError(
            f"calibration ensemble schema_version must be {ENSEMBLE_SCHEMA_VERSION}"
        )
    name = _required_text(payload, "name", "calibration ensemble manifest")
    members = payload.get("members")
    if not isinstance(members, list) or not members:
        raise CalibrationError("calibration ensemble manifest requires a non-empty 'members' list")
    if len(members) > MAX_ENSEMBLE_MEMBER_COUNT:
        raise CalibrationError(
            f"calibration ensemble cannot exceed {MAX_ENSEMBLE_MEMBER_COUNT} members"
        )

    normalized_members: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_coordinates: set[tuple[int, int]] = set()
    for index, raw_member in enumerate(members):
        context = f"calibration ensemble member {index}"
        if not isinstance(raw_member, dict):
            raise CalibrationError(f"{context} must be an object")
        member_id = _required_text(raw_member, "id", context)
        if member_id in seen_ids:
            raise CalibrationError(f"calibration ensemble duplicates member id '{member_id}'")
        seed = raw_member.get("seed")
        cell_count = raw_member.get("cell_count")
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**64 - 1:
            raise CalibrationError(f"{context} seed must be an unsigned 64-bit integer")
        if isinstance(cell_count, bool) or not isinstance(cell_count, int) or cell_count < 128:
            raise CalibrationError(f"{context} cell_count must be an integer of at least 128")
        coordinate = (seed, cell_count)
        if coordinate in seen_coordinates:
            raise CalibrationError(
                f"calibration ensemble duplicates seed/cell_count coordinate {coordinate}"
            )
        raw_groups = raw_member.get("groups", [])
        if not isinstance(raw_groups, list) or any(
            not isinstance(group, str) or not group.strip() for group in raw_groups
        ):
            raise CalibrationError(f"{context} groups must be non-empty strings")
        groups = sorted({group.strip() for group in raw_groups})
        if "all" in groups:
            raise CalibrationError(f"{context} group name 'all' is reserved")
        normalized_members.append(
            {
                "id": member_id,
                "seed": seed,
                "cell_count": cell_count,
                "groups": groups,
            }
        )
        seen_ids.add(member_id)
        seen_coordinates.add(coordinate)

    return {
        "schema_version": ENSEMBLE_SCHEMA_VERSION,
        "name": name,
        "members": normalized_members,
    }


def _normalized_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not targets:
        raise CalibrationError("calibration ensemble requires at least one target")
    normalized: list[dict[str, Any]] = []
    seen_metrics: set[str] = set()
    for index, raw_target in enumerate(targets):
        if not isinstance(raw_target, dict):
            raise CalibrationError(f"calibration ensemble target {index} must be an object")
        target = dict(raw_target)
        metric = _required_text(target, "metric", f"calibration ensemble target {index}")
        _required_text(target, "dataset", f"calibration ensemble target {index}")
        _required_text(target, "layer", f"calibration ensemble target {index}")
        if metric in seen_metrics:
            raise CalibrationError(f"calibration ensemble duplicates target metric '{metric}'")
        try:
            target_min = float(target["target_min"])
            target_max = float(target["target_max"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CalibrationError(
                f"calibration ensemble target '{metric}' requires numeric bounds"
            ) from exc
        if not math.isfinite(target_min) or not math.isfinite(target_max):
            raise CalibrationError(f"calibration ensemble target '{metric}' bounds must be finite")
        if target_max < target_min:
            raise CalibrationError(f"calibration ensemble target '{metric}' range is inverted")
        normalized.append(target)
        seen_metrics.add(metric)
    return normalized


def _metric_results(
    members: list[dict[str, Any]],
    targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for target in targets:
        metric = str(target["metric"])
        checks = [
            check
            for member in members
            for check in member["checks"]
            if check["metric"] == metric
        ]
        values = [float(check["value"]) for check in checks if check["value"] is not None]
        pass_count = sum(1 for check in checks if check["passed"])
        results.append(
            {
                "metric": metric,
                "dataset": str(target["dataset"]),
                "layer": str(target["layer"]),
                "target_min": float(target["target_min"]),
                "target_max": float(target["target_max"]),
                "member_count": len(members),
                "evaluated_member_count": len(values),
                "coverage_fraction": round(len(values) / len(members), 6) if members else 0.0,
                "pass_count": pass_count,
                "pass_fraction": round(pass_count / len(members), 6) if members else 0.0,
                "value_min": min(values) if values else None,
                "value_max": max(values) if values else None,
                "value_mean": round(sum(values) / len(values), 12) if values else None,
            }
        )
    return results


def _dataset_results(
    members: list[dict[str, Any]],
    targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    datasets: list[str] = []
    metrics_by_dataset: dict[str, list[str]] = {}
    for target in targets:
        dataset = str(target["dataset"])
        if dataset not in metrics_by_dataset:
            datasets.append(dataset)
            metrics_by_dataset[dataset] = []
        metrics_by_dataset[dataset].append(str(target["metric"]))

    results: list[dict[str, Any]] = []
    for dataset in datasets:
        metrics = metrics_by_dataset[dataset]
        complete_count = 0
        pass_count = 0
        for member in members:
            checks = [check for check in member["checks"] if check["metric"] in metrics]
            complete = len(checks) == len(metrics) and all(
                not check["missing_metric"] for check in checks
            )
            passed = complete and all(check["passed"] for check in checks)
            complete_count += int(complete)
            pass_count += int(passed)
        results.append(
            {
                "dataset": dataset,
                "metrics": metrics,
                "target_count": len(metrics),
                "member_count": len(members),
                "complete_member_count": complete_count,
                "coverage_fraction": round(complete_count / len(members), 6) if members else 0.0,
                "all_metrics_passed_member_count": pass_count,
                "all_metrics_passed_member_fraction": (
                    round(pass_count / len(members), 6) if members else 0.0
                ),
            }
        )
    return results


def _scope_summary(
    name: str,
    members: list[dict[str, Any]],
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    complete_count = sum(1 for member in members if member["complete"])
    all_passed_count = sum(1 for member in members if member["all_targets_passed"])
    return {
        "name": name,
        "member_ids": [member["id"] for member in members],
        "member_count": len(members),
        "complete_member_count": complete_count,
        "complete_member_fraction": round(complete_count / len(members), 6) if members else 0.0,
        "all_targets_passed_member_count": all_passed_count,
        "all_targets_passed_member_fraction": (
            round(all_passed_count / len(members), 6) if members else 0.0
        ),
        "all_members_complete": bool(members) and complete_count == len(members),
        "all_members_passed": bool(members) and all_passed_count == len(members),
        "datasets": _dataset_results(members, targets),
        "metrics": _metric_results(members, targets),
    }


def evaluate_calibration_ensemble(
    base_config: WorldConfig,
    manifest: dict[str, Any],
    targets: list[dict[str, Any]],
    *,
    provenance: dict[str, Any] | None = None,
    world_factory: Callable[[WorldConfig], dict[str, Any]] = generate_world,
    progress: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    normalized_targets = _normalized_targets(targets)
    members = manifest.get("members")
    if manifest.get("schema_version") != ENSEMBLE_SCHEMA_VERSION or not isinstance(members, list):
        raise CalibrationError("calibration ensemble manifest was not loaded or normalized")

    member_reports: list[dict[str, Any]] = []
    for index, member in enumerate(members):
        if progress is not None:
            progress(index, len(members), member)
        config_data = base_config.model_dump(mode="python")
        config_data["run"]["seed"] = int(member["seed"])
        config_data["mesh"]["cell_count"] = int(member["cell_count"])
        member_config = type(base_config).model_validate(config_data)
        try:
            world = world_factory(member_config)
        except RuntimeError as exc:
            raise CalibrationError(
                f"calibration ensemble member '{member['id']}' generation failed: {exc}"
            ) from exc
        calibration = evaluate_calibration_targets(world, normalized_targets)
        calibration_summary = calibration["summary"]
        check_count = int(calibration_summary["external_calibration_check_count"])
        pass_count = int(calibration_summary["external_calibration_pass_count"])
        complete = bool(calibration_summary["external_calibration_complete"])
        all_targets_passed = complete and check_count > 0 and pass_count == check_count
        member_reports.append(
            {
                "id": str(member["id"]),
                "seed": int(member["seed"]),
                "requested_cell_count": int(member["cell_count"]),
                "generated_cell_count": int(world.get("summary", {}).get("cell_count", 0)),
                "mesh_backend": str(world.get("mesh_backend", "unknown")),
                "groups": ["all", *member.get("groups", [])],
                "complete": complete,
                "all_targets_passed": all_targets_passed,
                "target_count": check_count,
                "pass_count": pass_count,
                "pass_fraction": float(
                    calibration_summary["external_calibration_pass_fraction"]
                ),
                "mean_score": float(calibration_summary["external_mean_calibration_score"]),
                "missing_world_metrics": list(calibration.get("missing_world_metrics", [])),
                "checks": calibration["checks"],
            }
        )

    group_names = sorted(
        {
            group
            for member in member_reports
            for group in member["groups"]
            if group != "all"
        }
    )
    overall = _scope_summary("all", member_reports, normalized_targets)
    group_reports = [
        _scope_summary(
            group,
            [member for member in member_reports if group in member["groups"]],
            normalized_targets,
        )
        for group in group_names
    ]
    config_payload = json.dumps(
        base_config.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": ENSEMBLE_SCHEMA_VERSION,
        "report_type": ENSEMBLE_REPORT_TYPE,
        "name": str(manifest.get("name", "calibration_ensemble")),
        "provenance": {
            "base_config_sha256": hashlib.sha256(config_payload).hexdigest(),
            **(provenance or {}),
        },
        "base_config": {
            "name": base_config.run.name,
            "seed": base_config.run.seed,
            "mesh_backend": base_config.mesh.backend,
            "cell_count": base_config.mesh.cell_count,
        },
        "summary": {
            "member_count": overall["member_count"],
            "group_count": len(group_reports),
            "target_count": len(normalized_targets),
            "dataset_count": len(overall["datasets"]),
            "complete_member_count": overall["complete_member_count"],
            "complete_member_fraction": overall["complete_member_fraction"],
            "all_targets_passed_member_count": overall[
                "all_targets_passed_member_count"
            ],
            "all_targets_passed_member_fraction": overall[
                "all_targets_passed_member_fraction"
            ],
            "reference_matrix_complete": overall["all_members_complete"],
            "reference_matrix_all_passed": overall["all_members_passed"],
        },
        "members": member_reports,
        "datasets": overall["datasets"],
        "metrics": overall["metrics"],
        "groups": group_reports,
    }


def write_calibration_ensemble_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report.get("summary", {})
    lines = ["# Calibration Ensemble Report", "", "## Summary", ""]
    for key in [
        "member_count",
        "group_count",
        "target_count",
        "dataset_count",
        "complete_member_count",
        "complete_member_fraction",
        "all_targets_passed_member_count",
        "all_targets_passed_member_fraction",
        "reference_matrix_complete",
        "reference_matrix_all_passed",
    ]:
        lines.append(f"- `{key}`: {summary.get(key)}")

    lines.extend(
        [
            "",
            "## Members",
            "",
            "| ID | Seed | Requested cells | Generated cells | Groups | Complete | All passed | Pass fraction |",
            "| --- | ---: | ---: | ---: | --- | --- | --- | ---: |",
        ]
    )
    for member in report.get("members", []):
        lines.append(
            f"| {member['id']} | {member['seed']} | {member['requested_cell_count']} | "
            f"{member['generated_cell_count']} | {', '.join(member['groups'])} | "
            f"{member['complete']} | {member['all_targets_passed']} | {member['pass_fraction']:.6f} |"
        )

    lines.extend(
        [
            "",
            "## Dataset Fit",
            "",
            "| Scope | Dataset | Targets | Members | Complete | All metrics passed | Pass fraction |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    scopes = [
        {"name": "all", "datasets": report.get("datasets", [])},
        *report.get("groups", []),
    ]
    for scope in scopes:
        for dataset in scope.get("datasets", []):
            lines.append(
                f"| {scope['name']} | {dataset['dataset']} | {dataset['target_count']} | "
                f"{dataset['member_count']} | {dataset['complete_member_count']} | "
                f"{dataset['all_metrics_passed_member_count']} | "
                f"{dataset['all_metrics_passed_member_fraction']:.6f} |"
            )

    lines.extend(
        [
            "",
            "## Metric Fit",
            "",
            "| Metric | Dataset | Members | Evaluated | Passed | Pass fraction | Min | Mean | Max |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for metric in report.get("metrics", []):
        lines.append(
            f"| {metric['metric']} | {metric['dataset']} | {metric['member_count']} | "
            f"{metric['evaluated_member_count']} | {metric['pass_count']} | "
            f"{metric['pass_fraction']:.6f} | {metric['value_min']} | "
            f"{metric['value_mean']} | {metric['value_max']} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
