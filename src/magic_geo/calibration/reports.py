"""Markdown reports for calibration and target derivation."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def write_calibration_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report.get("summary", {})
    lines = ["# Calibration Report", "", "## Summary", ""]
    for key in [
        "external_calibration_check_count",
        "external_calibration_evaluated_metric_count",
        "external_calibration_pass_count",
        "external_calibration_missing_metric_count",
        "external_calibration_metric_coverage_fraction",
        "external_calibration_pass_fraction",
        "external_calibration_evaluated_pass_fraction",
        "external_mean_calibration_score",
        "external_mean_evaluated_calibration_score",
        "external_calibration_complete",
    ]:
        if key in summary:
            lines.append(f"- `{key}`: {summary[key]}")
    lines.extend(["", "## Checks", ""])
    for check in report.get("checks", []):
        status = "missing" if check.get("missing_metric") else ("pass" if check.get("passed") else "fail")
        source_metric = check.get("source_metric")
        mapping = f", source_metric={source_metric}" if source_metric != check.get("metric") else ""
        provenance = ""
        if check.get("source_version"):
            provenance += f", source_version={check.get('source_version')}"
        if check.get("source_sha256"):
            provenance += f", source_sha256={check.get('source_sha256')}"
        if check.get("tolerance_basis"):
            provenance += f", tolerance_basis={check.get('tolerance_basis')}"
        lines.append(
            f"- `{check.get('metric')}` ({check.get('dataset')}/{check.get('layer')}): {status}, "
            f"value={check.get('value')}, target=[{check.get('target_min')}, {check.get('target_max')}], "
            f"score={check.get('score')}{mapping}{provenance}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_target_derivation_markdown(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report.get("summary", {})
    lines = ["# Calibration Target Derivation", "", "## Summary", ""]
    for key in ["derived_target_count", "source_count", "mapped_target_count", "unique_world_metric_count"]:
        if key in summary:
            lines.append(f"- `{key}`: {summary[key]}")
    lines.extend(["", "## Targets", ""])
    for target in report.get("targets", []):
        source_metric = target.get("source_metric")
        mapping = f", source_metric={source_metric}" if source_metric != target.get("metric") else ""
        provenance = ""
        if target.get("source_version"):
            provenance += f", source_version={target.get('source_version')}"
        if target.get("source_sha256"):
            provenance += f", source_sha256={target.get('source_sha256')}"
        if target.get("tolerance_basis"):
            provenance += f", tolerance_basis={target.get('tolerance_basis')}"
        lines.append(
            f"- `{target.get('metric')}` ({target.get('dataset')}/{target.get('layer')}): "
            f"value={target.get('source_value')}, target=[{target.get('target_min')}, {target.get('target_max')}], "
            f"source={target.get('source')}{mapping}{provenance}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
