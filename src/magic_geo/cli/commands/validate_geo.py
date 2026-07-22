"""`validate-geo` and `validate-geo-suite` commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError

from .._app import _load_world_for_cli, app
from ...config import load_config
from ...geo_validation import validate_geo_world
from ...geo_validation_suite import (
    GeoValidationSuiteError,
    evaluate_geo_validation_suite,
    load_geo_validation_manifest,
    write_geo_validation_suite_markdown,
)
from ...io import write_json


@app.command("validate-geo")
def validate_geo(
    world: Annotated[
        Path,
        typer.Option("--world", "-w", exists=True, help="Generated .json or .mgeo world."),
    ],
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            help="Natural-system validation profile: generic or earthlike.",
        ),
    ] = "generic",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Optional machine-readable validation report."),
    ] = None,
    fail_on_warnings: Annotated[
        bool,
        typer.Option(
            "--fail-on-warnings/--allow-warnings",
            help="Treat failed evidence-backed realism diagnostics as fatal.",
        ),
    ] = False,
) -> None:
    """Validate only natural geography, conservation, and selected realism gates."""
    payload = _load_world_for_cli(world)
    if profile not in {"generic", "earthlike"}:
        typer.echo("--profile must be generic or earthlike", err=True)
        raise typer.Exit(2)
    report = validate_geo_world(payload, profile=profile)
    report_summary = report["summary"]
    failed_checks = [
        check
        for check in report["checks"]
        if check["status"] == "failed"
        and (check["severity"] == "error" or fail_on_warnings)
    ]
    policy_passed = bool(report["passed"]) and not failed_checks
    report["requested_policy"] = {
        "fail_on_warnings": fail_on_warnings,
        "policy_passed": policy_passed,
    }
    if output is not None:
        write_json(output, report)
    typer.echo(
        f"{'OK' if policy_passed else 'FAIL'} geo | "
        f"checks={report_summary['check_count']} "
        f"errors={report_summary['error_failure_count']} "
        f"warnings={report_summary['warning_failure_count']} "
        f"not_applicable={report_summary['not_applicable_count']}"
    )
    for check in failed_checks:
        typer.echo(
            f"FAIL {check['domain']}.{check['name']}: {check['message']}",
            err=True,
        )
    for layer in report.get("layer_contracts", {}).get("layers", []):
        if isinstance(layer, dict) and not layer.get("contract_passed", False):
            typer.echo(
                f"FAIL layer_contract.{layer.get('id', 'unknown')}: "
                "required artifacts, validation domains, or dependencies failed",
                err=True,
            )
    if not policy_passed:
        raise typer.Exit(1)


@app.command("validate-geo-suite")
def validate_geo_suite(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", exists=True, help="Base YAML config path."),
    ] = Path("configs/earthlike_seed.yaml"),
    matrix: Annotated[
        Path,
        typer.Option(
            "--matrix",
            "-m",
            exists=True,
            help="Geo scenario matrix with nested config overrides and paired gates.",
        ),
    ] = Path("configs/geo_validation_matrix.yaml"),
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Machine-readable suite report."),
    ] = Path("runs/geo_validation.json"),
    summary: Annotated[
        Path | None,
        typer.Option("--summary", help="Optional Markdown suite report."),
    ] = None,
) -> None:
    """Run geo-only replays, diverse response gates, and configured empirical fit."""
    try:
        base_config = load_config(config)
        manifest = load_geo_validation_manifest(matrix)

        def report_progress(index: int, count: int, scenario: dict[str, Any]) -> None:
            typer.echo(f"[{index + 1}/{count}] {scenario['id']}")

        report = evaluate_geo_validation_suite(
            base_config,
            manifest,
            progress=report_progress,
        )
    except (GeoValidationSuiteError, ValidationError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    write_json(output, report)
    if summary is not None:
        write_geo_validation_suite_markdown(summary, report)
    report_summary = report["summary"]
    typer.echo(
        f"Wrote {output} | scenarios={report_summary['scenario_pass_count']}/"
        f"{report_summary['scenario_count']} relations={report_summary['relation_pass_count']}/"
        f"{report_summary['relation_count']} empirical_fit="
        + (
            "not-configured"
            if report_summary["empirical_calibration_scenario_count"] == 0
            else (
                f"{report_summary['empirical_calibration_pass_count']}/"
                f"{report_summary['empirical_calibration_check_count']} "
                f"coverage={report_summary['empirical_calibration_evaluated_metric_count']}/"
                f"{report_summary['empirical_calibration_check_count']}"
            )
        )
    )
    if not report["passed"]:
        failed_members = [member["id"] for member in report["members"] if not member["passed"]]
        failed_relations = [relation["id"] for relation in report["relations"] if not relation["passed"]]
        if failed_members:
            typer.echo(f"Failed scenarios: {', '.join(failed_members)}", err=True)
        if failed_relations:
            typer.echo(f"Failed relations: {', '.join(failed_relations)}", err=True)
        failed_empirical_metrics = [
            f"{check['scenario_id']}:{check['metric']}"
            for check in report.get("empirical_calibration", {}).get(
                "failed_checks", []
            )
        ]
        if failed_empirical_metrics:
            typer.echo(
                "Failed external empirical metrics: "
                + ", ".join(failed_empirical_metrics),
                err=True,
            )
        raise typer.Exit(1)
