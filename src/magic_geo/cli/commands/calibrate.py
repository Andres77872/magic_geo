"""`calibrate`, `calibrate-ensemble`, and `derive-targets` commands."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError

from .._app import _load_world_for_cli, app
from .._paths import runtime_path
from ...calibration import (
    CalibrationError,
    derive_calibration_targets,
    evaluate_calibration_targets,
    load_calibration_sources,
    load_calibration_targets,
    write_calibration_markdown,
    write_target_derivation_markdown,
)
from ...config import load_config
from ...ensemble_calibration import (
    evaluate_calibration_ensemble,
    load_calibration_ensemble_manifest,
    write_calibration_ensemble_markdown,
)
from ...io import write_json


@app.command("calibrate")
def calibrate(
    world: Annotated[Path, typer.Option("--world", "-w", exists=True, help="Generated .json or .mgeo world.")],
    targets: Annotated[
        Path,
        typer.Option(
            "--targets",
            "-t",
            exists=False,
            help="JSON calibration target ranges derived from external datasets.",
            callback=runtime_path,
        ),
    ],
    output: Annotated[Path, typer.Option("--output", "-o", help="Calibration report JSON path.", callback=runtime_path)] = Path(
        "runs/calibration.json"
    ),
    summary: Annotated[Path | None, typer.Option("--summary", help="Optional Markdown calibration report path.")] = None,
    require_all_metrics: Annotated[
        bool,
        typer.Option(
            "--require-all-metrics/--allow-missing-metrics",
            help="Exit nonzero after writing the report when any target metric is unavailable.",
        ),
    ] = False,
    require_all_passed: Annotated[
        bool,
        typer.Option(
            "--require-all-passed/--allow-fit-failures",
            help="Exit nonzero after writing the report unless every target metric is available and in range.",
        ),
    ] = False,
) -> None:
    """Compare a generated world against external dataset-derived calibration ranges."""
    payload = _load_world_for_cli(world)
    try:
        report = evaluate_calibration_targets(payload, load_calibration_targets(targets))
    except (CalibrationError, json.JSONDecodeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc

    write_json(output, report)
    if summary is not None:
        write_calibration_markdown(summary, report)

    report_summary = report["summary"]
    typer.echo(
        f"Wrote {output} | checks={report_summary['external_calibration_check_count']} "
        f"coverage={report_summary['external_calibration_metric_coverage_fraction']:.3f} "
        f"pass_fraction={report_summary['external_calibration_pass_fraction']:.3f}"
    )
    if require_all_metrics and not report_summary["external_calibration_complete"]:
        missing = ", ".join(report.get("missing_world_metrics", []))
        detail = f"missing world metrics: {missing}" if missing else "no calibration targets were evaluated"
        typer.echo(f"Calibration coverage incomplete; {detail}", err=True)
        raise typer.Exit(1)
    if require_all_passed:
        failed_metrics = [str(check.get("metric", "unknown")) for check in report["checks"] if not check["passed"]]
        if failed_metrics or not report["checks"]:
            detail = f"failed metrics: {', '.join(failed_metrics)}" if failed_metrics else "no calibration targets"
            typer.echo(f"Calibration fit failed; {detail}", err=True)
            raise typer.Exit(1)


@app.command("calibrate-ensemble")
def calibrate_ensemble(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", exists=False, help="Base YAML config path.", callback=runtime_path),
    ],
    matrix: Annotated[
        Path,
        typer.Option(
            "--matrix",
            "-m",
            exists=False,
            help="JSON manifest containing explicit seed/cell-count ensemble members.",
            callback=runtime_path,
        ),
    ],
    targets: Annotated[
        list[Path],
        typer.Option(
            "--targets",
            "-t",
            exists=False,
            help="Calibration target JSON path; repeat for multiple non-overlapping target bundles.",
            callback=runtime_path,
        ),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Calibration ensemble report JSON path.", callback=runtime_path),
    ] = Path("runs/calibration_ensemble.json"),
    summary: Annotated[
        Path | None,
        typer.Option("--summary", help="Optional Markdown calibration ensemble report path."),
    ] = None,
    require_all_metrics: Annotated[
        bool,
        typer.Option(
            "--require-all-metrics/--allow-missing-metrics",
            help="Exit nonzero after writing unless every member covers every target.",
        ),
    ] = False,
    require_all_passed: Annotated[
        bool,
        typer.Option(
            "--require-all-passed/--allow-fit-failures",
            help="Exit nonzero after writing unless every member passes every target.",
        ),
    ] = False,
) -> None:
    """Generate and evaluate an explicit seed/resolution calibration matrix."""
    try:
        base_config = load_config(config)
        manifest = load_calibration_ensemble_manifest(matrix)
        combined_targets: list[dict[str, Any]] = []
        target_bundle_provenance: list[dict[str, Any]] = []
        for target_path in targets:
            loaded_targets = load_calibration_targets(target_path)
            combined_targets.extend(loaded_targets)
            target_bundle_provenance.append(
                {
                    "name": target_path.name,
                    "sha256": hashlib.sha256(target_path.read_bytes()).hexdigest(),
                    "target_count": len(loaded_targets),
                }
            )

        def report_progress(index: int, count: int, member: dict[str, Any]) -> None:
            typer.echo(
                f"[{index + 1}/{count}] {member['id']} "
                f"seed={member['seed']} cells={member['cell_count']}"
            )

        report = evaluate_calibration_ensemble(
            base_config,
            manifest,
            combined_targets,
            provenance={
                "matrix_sha256": hashlib.sha256(matrix.read_bytes()).hexdigest(),
                "target_bundles": target_bundle_provenance,
            },
            progress=report_progress,
        )
    except (CalibrationError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc

    write_json(output, report)
    if summary is not None:
        write_calibration_ensemble_markdown(summary, report)

    report_summary = report["summary"]
    typer.echo(
        f"Wrote {output} | members={report_summary['member_count']} "
        f"coverage={report_summary['complete_member_fraction']:.3f} "
        f"all_passed={report_summary['all_targets_passed_member_fraction']:.3f}"
    )
    if require_all_metrics and not report_summary["reference_matrix_complete"]:
        typer.echo("Calibration ensemble coverage incomplete", err=True)
        raise typer.Exit(1)
    if require_all_passed and not report_summary["reference_matrix_all_passed"]:
        failed_members = [
            member["id"] for member in report["members"] if not member["all_targets_passed"]
        ]
        typer.echo(
            f"Calibration ensemble fit failed; failed members: {', '.join(failed_members)}",
            err=True,
        )
        raise typer.Exit(1)


@app.command("derive-targets")
def derive_targets(
    sources: Annotated[
        Path,
        typer.Option(
            "--sources",
            "-s",
            exists=False,
            help="JSON source manifest for deriving calibration target ranges from local raster/vector data.",
            callback=runtime_path,
        ),
    ],
    output: Annotated[Path, typer.Option("--output", "-o", help="Derived calibration targets JSON path.", callback=runtime_path)] = Path(
        "runs/calibration_targets.json"
    ),
    summary: Annotated[Path | None, typer.Option("--summary", help="Optional Markdown target derivation report path.")] = None,
) -> None:
    """Derive target ranges from supported local raster, vector, and archive sources."""
    try:
        report = derive_calibration_targets(load_calibration_sources(sources))
    except (CalibrationError, json.JSONDecodeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc

    write_json(output, report)
    if summary is not None:
        write_target_derivation_markdown(summary, report)

    report_summary = report["summary"]
    typer.echo(
        f"Wrote {output} | targets={report_summary['derived_target_count']} "
        f"sources={report_summary['source_count']}"
    )
