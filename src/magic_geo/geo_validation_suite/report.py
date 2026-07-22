"""Markdown suite report."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def write_geo_validation_suite_markdown(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    lines = [
        f"# Geo Pipeline Validation: {report['name']}",
        "",
        f"Overall verdict: **{'PASS' if report['passed'] else 'FAIL'}**",
        "",
        f"Scope: {report['scope']}.",
        "",
        f"Excluded scope: {report['excluded_scope']}.",
        "",
        f"Scenarios: {summary['scenario_pass_count']}/{summary['scenario_count']} passed. ",
        (
            f"Internal geo gates: {summary['internal_scenario_pass_count']}/"
            f"{summary['scenario_count']} scenarios passed."
        ),
        (
            "External empirical calibration: not configured."
            if summary["empirical_calibration_scenario_count"] == 0
            else (
                f"External empirical calibration: "
                f"{summary['empirical_calibration_policy_pass_count']}/"
                f"{summary['empirical_calibration_scenario_count']} scenario policies passed; "
                f"{summary['empirical_calibration_pass_count']}/"
                f"{summary['empirical_calibration_check_count']} target metrics in range; "
                f"coverage {summary['empirical_calibration_evaluated_metric_count']}/"
                f"{summary['empirical_calibration_check_count']}."
            )
        ),
        (
            f"Paired response gates: {summary['relation_pass_count']}/{summary['relation_count']} passed."
            if summary["response_validation_performed"]
            else "Paired response gates: not run."
        ),
        "",
        "## Declared Model Limitations",
        "",
        *[f"- {limitation}." for limitation in report.get("model_limitations", [])],
        "",
        "## Scenario Results",
        "",
        "| Scenario | Profile | Verdict | Internal gates | External empirical fit | Cells | Ocean | Temperature | Land precipitation | Evidence coverage | Internal diagnostic fit | Deviations | Determinism |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for member in report["members"]:
        metrics = member["metrics"]
        precipitation = metrics.get("mean_land_precipitation_mm_y")
        empirical = member.get("empirical_calibration")
        empirical_fit = "not configured"
        if empirical is not None:
            empirical_summary = empirical["summary"]
            empirical_fit = (
                f"{empirical_summary['external_calibration_pass_count']}/"
                f"{empirical_summary['external_calibration_check_count']} "
                f"({'PASS' if empirical['policy_passed'] else 'FAIL'})"
            )
        lines.append(
            "| {id} | {profile} | {verdict} | {internal} | {empirical} | {cells} | {ocean:.3f} | {temperature:.2f} C | {precip} | {coverage:.3f} | {calibration:.3f} | {deviations} | {determinism} |".format(
                id=member["id"],
                profile=member["profile"],
                verdict="PASS" if member["passed"] else "FAIL",
                internal="PASS" if member["internal_validation_passed"] else "FAIL",
                empirical=empirical_fit,
                cells=metrics.get("cell_count", 0),
                ocean=float(metrics.get("ocean_fraction", 0.0)),
                temperature=float(metrics.get("global_mean_temperature_c", 0.0)),
                precip="n/a" if precipitation is None else f"{float(precipitation):.1f} mm/y",
                coverage=float(metrics.get("realism_evidence_coverage_fraction", 0.0)),
                calibration=float(metrics.get("calibration_pass_fraction", 0.0)),
                deviations=len(member.get("realism_deviations", [])),
                determinism=(
                    "not tested"
                    if not member.get("determinism_tested", False)
                    else ("PASS" if member.get("deterministic") else "FAIL")
                ),
            )
        )
    empirical_members = [
        member
        for member in report["members"]
        if member.get("empirical_calibration") is not None
    ]
    if empirical_members:
        lines.extend(
            [
                "",
                "## External Empirical Calibration",
                "",
                "These Earth-reference model-fit checks are reported independently from internal replay, conservation, determinism, and response gates.",
                "",
            ]
        )
        for member in empirical_members:
            empirical = member["empirical_calibration"]
            bundle = empirical["target_bundle"]
            empirical_summary = empirical["summary"]
            lines.extend(
                [
                    f"### {member['id']}",
                    "",
                    f"Target bundle: `{bundle['name']}` (`{bundle['sha256']}`); "
                    f"coverage {empirical_summary['external_calibration_evaluated_metric_count']}/"
                    f"{empirical_summary['external_calibration_check_count']}; fit "
                    f"{empirical_summary['external_calibration_pass_count']}/"
                    f"{empirical_summary['external_calibration_check_count']}; policy "
                    f"**{'PASS' if empirical['policy_passed'] else 'FAIL'}**.",
                    "",
                    "| Dataset | Metric | Observed | Target range | Score | Status |",
                    "|---|---|---:|---:|---:|---:|",
                ]
            )
            for check in empirical["checks"]:
                status = (
                    "MISSING"
                    if check["missing_metric"]
                    else ("PASS" if check["passed"] else "FAIL")
                )
                lines.append(
                    f"| {check['dataset']} | `{check['metric']}` | "
                    f"{'n/a' if check['value'] is None else check['value']} | "
                    f"[{check['target_min']}, {check['target_max']}] | "
                    f"{check['score']} | {status} |"
                )
    lines.extend(
        [
            "",
            "## Paired Physical Responses",
            "",
            "| Relation | Metric | Comparison | Difference | Verdict |",
            "|---|---|---|---:|---:|",
        ]
    )
    for relation in report["relations"]:
        difference = relation.get("difference")
        lines.append(
            f"| {relation['id']} | {relation['metric']} | "
            f"{relation['left']} {relation['operator']} {relation['right']} | "
            f"{'n/a' if difference is None else f'{float(difference):.6f}'} | "
            f"{'PASS' if relation['passed'] else 'FAIL'} |"
        )
    failed_details = [
        (member["id"], failure)
        for member in report["members"]
        for failure in member["validation_failures"]
    ]
    failed_expectations = [
        (member["id"], check)
        for member in report["members"]
        for check in member["expectation_checks"]
        if not check["passed"]
    ]
    failed_relations = [relation for relation in report["relations"] if not relation["passed"]]
    if failed_details or failed_expectations or failed_relations:
        lines.extend(["", "## Internal Validation and Response Failures", ""])
        for scenario_id, failure in failed_details:
            lines.append(f"- `{scenario_id}` / `{failure['domain']}.{failure['name']}`: {failure['message']}")
        for scenario_id, check in failed_expectations:
            lines.append(
                f"- `{scenario_id}` / `{check['metric']}`: observed `{check['observed']}`, expected `{check['expected']}`"
            )
        for relation in failed_relations:
            lines.append(
                f"- `{relation['id']}`: `{relation['left_value']}` {relation['operator']} `{relation['right_value']}` with minimum difference `{relation['minimum_difference']}`"
            )
    empirical_failures = report.get("empirical_calibration", {}).get(
        "failed_checks", []
    )
    if empirical_failures:
        lines.extend(["", "## External Empirical Calibration Failures", ""])
        for check in empirical_failures:
            lines.append(
                f"- `{check['scenario_id']}` / `{check['dataset']}` / "
                f"`{check['metric']}`: observed `{check['value']}`, expected "
                f"`[{check['target_min']}, {check['target_max']}]`"
            )
    realism_deviations = [
        (member["id"], deviation)
        for member in report["members"]
        for deviation in member.get("realism_deviations", [])
    ]
    if realism_deviations:
        lines.extend(["", "## Nonfatal Realism Deviations", ""])
        for scenario_id, deviation in realism_deviations:
            lines.append(
                f"- `{scenario_id}` / `{deviation['name']}`: "
                f"observed `{deviation.get('observed')}`, expected `{deviation.get('expected')}`"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
