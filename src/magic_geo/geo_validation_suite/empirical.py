"""Loading and validating empirical target bundles."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ._constants import (
    EMPIRICAL_TARGET_BUNDLE_SCHEMA_VERSION,
    SETON_CDF_THRESHOLDS_MA,
    SETON_SOURCE_ID,
    SETON_SUPPLEMENTAL_NAME,
    SETON_SUPPLEMENTAL_TOOL,
)
from .errors import GeoValidationSuiteError
from ._helpers import _finite, _required_bool, _required_integer, _required_sha256, _required_text, _validate_exact_fields


def _validate_seton_supplemental_derivation(
    *,
    artifact_path: Path,
    artifact_bytes: bytes,
    record_tool: str,
    bundle_source: dict[str, Any],
    bundle_targets: list[dict[str, Any]],
    context: str,
) -> None:
    artifact_context = f"{context} Seton supplemental target derivation"
    try:
        artifact = json.loads(artifact_bytes)
    except json.JSONDecodeError as exc:
        raise GeoValidationSuiteError(
            f"{artifact_context} is not a readable JSON object: {artifact_path}"
        ) from exc
    artifact = _validate_exact_fields(
        artifact,
        {
            "schema_version",
            "name",
            "description",
            "derivation",
            "source",
            "statistics",
        },
        artifact_context,
    )
    if artifact.get("schema_version") != 1:
        raise GeoValidationSuiteError(f"{artifact_context} schema_version must be 1")
    if artifact.get("name") != SETON_SUPPLEMENTAL_NAME:
        raise GeoValidationSuiteError(
            f"{artifact_context} name must be {SETON_SUPPLEMENTAL_NAME}"
        )
    _required_text(artifact.get("description"), f"{artifact_context} description")

    supplemental_derivation = _validate_exact_fields(
        artifact.get("derivation"),
        {
            "accumulation",
            "cdf_rule",
            "derived_on",
            "runtime_requires_raw_sources",
            "tool",
            "weighting",
        },
        f"{artifact_context} derivation",
    )
    expected_derivation_metadata: dict[str, Any] = {
        "accumulation": "canonical_file_order_math_fsum_chunks_of_8192",
        "cdf_rule": "finite_source_age_ma_less_than_or_equal_to_threshold",
        "runtime_requires_raw_sources": False,
        "tool": SETON_SUPPLEMENTAL_TOOL,
        "weighting": (
            "longitude_endpoint_trapezoid_factor_times_exact_spherical_"
            "latitude_band_sine_difference"
        ),
    }
    for field, expected in expected_derivation_metadata.items():
        if supplemental_derivation.get(field) != expected:
            raise GeoValidationSuiteError(
                f"{artifact_context} derivation metadata '{field}' does not "
                "match the canonical Seton derivation"
            )
    _required_text(
        supplemental_derivation.get("derived_on"),
        f"{artifact_context} derivation derived_on",
    )
    if record_tool != supplemental_derivation["tool"]:
        raise GeoValidationSuiteError(
            f"{artifact_context} tool does not match its bundle witness record"
        )

    supplemental_source = _validate_exact_fields(
        artifact.get("source"),
        {
            "dataset",
            "format",
            "layer",
            "source",
            "source_acquired_on",
            "source_citation",
            "source_doi",
            "source_finite_maximum_age_ma",
            "source_finite_minimum_age_ma",
            "source_finite_node_count",
            "source_grid_dimensions",
            "source_horizontal_crs",
            "source_license",
            "source_license_url",
            "source_native_resolution",
            "source_processing",
            "source_sha256",
            "source_total_node_count",
            "source_url",
            "source_variable_units",
            "source_version",
        },
        f"{artifact_context} source",
    )
    source_metadata_mapping = {
        "dataset": "dataset",
        "format": "source_format",
        "layer": "layer",
        "source": "source",
        "source_acquired_on": "source_acquired_on",
        "source_citation": "source_citation",
        "source_doi": "source_doi",
        "source_horizontal_crs": "source_horizontal_crs",
        "source_license": "source_license",
        "source_license_url": "source_license_url",
        "source_native_resolution": "source_native_resolution",
        "source_sha256": "source_sha256",
        "source_url": "source_url",
        "source_version": "source_version",
    }
    if set(bundle_source) != set(source_metadata_mapping.values()):
        raise GeoValidationSuiteError(
            f"{artifact_context} cannot exactly substantiate the Seton bundle "
            "source metadata fields"
        )
    for supplemental_field, bundle_field in source_metadata_mapping.items():
        supplemental_value = supplemental_source.get(supplemental_field)
        if supplemental_field == "source_sha256":
            supplemental_value = _required_sha256(
                supplemental_value,
                f"{artifact_context} source source_sha256",
            )
        else:
            supplemental_value = _required_text(
                supplemental_value,
                f"{artifact_context} source {supplemental_field}",
            )
        if supplemental_value != bundle_source[bundle_field]:
            raise GeoValidationSuiteError(
                f"{artifact_context} source metadata '{bundle_field}' does "
                "not match the canonical bundle"
            )

    grid_dimensions = supplemental_source.get("source_grid_dimensions")
    if grid_dimensions != [1801, 3601]:
        raise GeoValidationSuiteError(
            f"{artifact_context} source_grid_dimensions must be [1801, 3601]"
        )
    total_node_count = _required_integer(
        supplemental_source.get("source_total_node_count"),
        f"{artifact_context} source_total_node_count",
    )
    if total_node_count != grid_dimensions[0] * grid_dimensions[1]:
        raise GeoValidationSuiteError(
            f"{artifact_context} source_total_node_count conflicts with the grid"
        )
    finite_node_count = _required_integer(
        supplemental_source.get("source_finite_node_count"),
        f"{artifact_context} source_finite_node_count",
    )
    if not 0 < finite_node_count <= total_node_count:
        raise GeoValidationSuiteError(
            f"{artifact_context} source_finite_node_count is out of range"
        )
    finite_minimum = _finite(
        supplemental_source.get("source_finite_minimum_age_ma"),
        f"{artifact_context} source_finite_minimum_age_ma",
    )
    finite_maximum = _finite(
        supplemental_source.get("source_finite_maximum_age_ma"),
        f"{artifact_context} source_finite_maximum_age_ma",
    )
    if finite_minimum < 0.0 or finite_maximum < finite_minimum:
        raise GeoValidationSuiteError(
            f"{artifact_context} finite source-age range is invalid"
        )
    source_units = _required_text(
        supplemental_source.get("source_variable_units"),
        f"{artifact_context} source_variable_units",
    )
    if source_units != "Ma":
        raise GeoValidationSuiteError(
            f"{artifact_context} source_variable_units must be Ma"
        )
    expected_source_processing = (
        "Parse finite ages from the 1801 by 3601 grid in canonical file order; "
        "apply longitude endpoint trapezoid factors and exact spherical latitude-"
        "band factors; compute the finite-ocean weighted mean and inclusive "
        "age<=threshold CDF ordinates."
    )
    if supplemental_source.get("source_processing") != expected_source_processing:
        raise GeoValidationSuiteError(
            f"{artifact_context} source_processing does not match the canonical "
            "Seton derivation"
        )

    statistics = _validate_exact_fields(
        artifact.get("statistics"),
        {
            "area_weighted_cdf_le_threshold",
            "area_weighted_mean_age_ma",
            "cdf_thresholds_ma",
        },
        f"{artifact_context} statistics",
    )
    raw_thresholds = statistics.get("cdf_thresholds_ma")
    if not isinstance(raw_thresholds, list):
        raise GeoValidationSuiteError(
            f"{artifact_context} cdf_thresholds_ma must be an array"
        )
    thresholds = [
        _required_integer(value, f"{artifact_context} cdf_thresholds_ma[{index}]")
        for index, value in enumerate(raw_thresholds)
    ]
    if len(set(thresholds)) != len(thresholds):
        raise GeoValidationSuiteError(
            f"{artifact_context} cdf_thresholds_ma contains duplicate thresholds"
        )
    if tuple(thresholds) != SETON_CDF_THRESHOLDS_MA:
        raise GeoValidationSuiteError(
            f"{artifact_context} cdf_thresholds_ma has missing or extra thresholds"
        )
    raw_cdf_values = statistics.get("area_weighted_cdf_le_threshold")
    if not isinstance(raw_cdf_values, list):
        raise GeoValidationSuiteError(
            f"{artifact_context} area_weighted_cdf_le_threshold must be an array"
        )
    if len(raw_cdf_values) != len(thresholds):
        raise GeoValidationSuiteError(
            f"{artifact_context} CDF values do not map one-to-one to thresholds"
        )
    cdf_values = [
        _finite(
            value,
            f"{artifact_context} area_weighted_cdf_le_threshold[{index}]",
        )
        for index, value in enumerate(raw_cdf_values)
    ]
    if any(value < 0.0 or value > 1.0 for value in cdf_values) or any(
        right < left for left, right in zip(cdf_values, cdf_values[1:])
    ):
        raise GeoValidationSuiteError(
            f"{artifact_context} CDF values must be monotone fractions"
        )
    mean_age = _finite(
        statistics.get("area_weighted_mean_age_ma"),
        f"{artifact_context} area_weighted_mean_age_ma",
    )
    if mean_age < finite_minimum or mean_age > finite_maximum:
        raise GeoValidationSuiteError(
            f"{artifact_context} area_weighted_mean_age_ma is outside the source range"
        )

    seton_targets = [
        target
        for target in bundle_targets
        if target.get("source_id") == SETON_SOURCE_ID
    ]
    mean_metric = "initial_oceanic_crust_age_area_weighted_mean_ma"
    expected_metrics = {mean_metric} | {
        f"initial_oceanic_crust_age_area_weighted_cdf_le_{threshold}_ma"
        for threshold in thresholds
    }
    targets_by_metric = {target["metric"]: target for target in seton_targets}
    actual_metrics = set(targets_by_metric)
    if len(targets_by_metric) != len(seton_targets):
        raise GeoValidationSuiteError(
            f"{artifact_context} bundle targets contain duplicate Seton metrics"
        )
    if actual_metrics != expected_metrics:
        missing = sorted(expected_metrics - actual_metrics)
        extra = sorted(actual_metrics - expected_metrics)
        raise GeoValidationSuiteError(
            f"{artifact_context} bundle targets have missing or extra Seton "
            f"statistics (missing={missing}, extra={extra})"
        )

    def validate_target_metadata(
        target: dict[str, Any],
        *,
        expected_source_metric: str,
        expected_statistic: str,
        expected_processing: str,
        expected_units: str,
        expected_value: float,
    ) -> None:
        metric = target["metric"]
        target_context = f"{artifact_context} bundle target '{metric}'"
        if target.get("source_metric") != expected_source_metric:
            raise GeoValidationSuiteError(
                f"{target_context} source_metric does not match its statistic"
            )
        if target.get("source_statistic") != expected_statistic:
            raise GeoValidationSuiteError(
                f"{target_context} source_statistic does not match its statistic"
            )
        if target.get("source_processing") != expected_processing:
            raise GeoValidationSuiteError(
                f"{target_context} source_processing does not match its statistic"
            )
        if target.get("source_variable_units") != expected_units:
            raise GeoValidationSuiteError(
                f"{target_context} source_variable_units does not match the source"
            )
        sample_count = _required_integer(
            target.get("source_sample_record_count"),
            f"{target_context} source_sample_record_count",
        )
        if sample_count != finite_node_count:
            raise GeoValidationSuiteError(
                f"{target_context} source_sample_record_count does not match the source"
            )
        if target.get("source_value") != expected_value:
            raise GeoValidationSuiteError(
                f"{target_context} source_value is not substantiated by the "
                "checked supplemental artifact"
            )

    validate_target_metadata(
        targets_by_metric[mean_metric],
        expected_source_metric="seton_grid_area_weighted_mean_age_ma",
        expected_statistic="spherical_grid_node_area_weighted_mean",
        expected_processing=(
            "Finite 6 arc-minute XYZ nodes weighted by longitude endpoint "
            "trapezoids and exact spherical latitude-band area; repository-derived "
            "from the pinned grid, not quoted from the paper"
        ),
        expected_units=source_units,
        expected_value=mean_age,
    )
    for threshold, cdf_value in zip(thresholds, cdf_values):
        metric = (
            "initial_oceanic_crust_age_area_weighted_cdf_le_"
            f"{threshold}_ma"
        )
        validate_target_metadata(
            targets_by_metric[metric],
            expected_source_metric=(
                f"seton_grid_area_weighted_cdf_le_{threshold}_ma"
            ),
            expected_statistic="repository_derived_spherical_area_cdf",
            expected_processing=(
                "Same finite-node spherical quadrature; inclusive age <= "
                f"{threshold} Ma"
            ),
            expected_units="fraction",
            expected_value=cdf_value,
        )


def _validated_empirical_derivation(
    raw: dict[str, Any],
    *,
    bundle_path: Path,
    context: str,
    sources: dict[str, dict[str, Any]],
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate local derivation witnesses and their declared byte digests."""

    derivation = deepcopy(raw)
    if "runtime_requires_raw_sources" in derivation:
        derivation["runtime_requires_raw_sources"] = _required_bool(
            derivation["runtime_requires_raw_sources"],
            f"{context} derivation runtime_requires_raw_sources",
        )
    if "tool" in derivation:
        derivation["tool"] = _required_text(
            derivation["tool"], f"{context} derivation tool"
        )

    supplemental_artifacts: list[tuple[dict[str, str], Path, bytes]] = []
    for field, allowed_fields in (
        ("source_manifests", {"path", "sha256"}),
        (
            "supplemental_target_derivations",
            {"path", "sha256", "tool"},
        ),
    ):
        if field not in derivation:
            continue
        records = derivation[field]
        if not isinstance(records, list) or not records:
            raise GeoValidationSuiteError(
                f"{context} derivation {field} must be a non-empty array"
            )
        normalized_records: list[dict[str, str]] = []
        seen_paths: set[str] = set()
        for index, record in enumerate(records):
            record_context = f"{context} derivation {field}[{index}]"
            if not isinstance(record, dict) or set(record) != allowed_fields:
                raise GeoValidationSuiteError(
                    f"{record_context} fields must be "
                    f"{', '.join(sorted(allowed_fields))}"
                )
            declared_path = _required_text(
                record.get("path"), f"{record_context} path"
            )
            if declared_path in seen_paths:
                raise GeoValidationSuiteError(
                    f"{context} derivation {field} duplicates {declared_path}"
                )
            seen_paths.add(declared_path)
            expected_digest = _required_sha256(
                record.get("sha256"), f"{record_context} sha256"
            )
            artifact_path = Path(declared_path)
            if not artifact_path.is_absolute():
                artifact_path = bundle_path.parent / artifact_path
            try:
                artifact_bytes = artifact_path.read_bytes()
            except OSError as exc:
                raise GeoValidationSuiteError(
                    f"{record_context} artifact is unavailable: {artifact_path}"
                ) from exc
            actual_digest = hashlib.sha256(artifact_bytes).hexdigest()
            if actual_digest != expected_digest:
                raise GeoValidationSuiteError(
                    f"{record_context} SHA-256 mismatch: expected "
                    f"{expected_digest}, got {actual_digest}"
                )
            normalized = {
                "path": declared_path,
                "sha256": expected_digest,
            }
            if "tool" in allowed_fields:
                normalized["tool"] = _required_text(
                    record.get("tool"), f"{record_context} tool"
                )
            normalized_records.append(normalized)
            if field == "supplemental_target_derivations":
                supplemental_artifacts.append(
                    (normalized, artifact_path, artifact_bytes)
                )
        derivation[field] = normalized_records

    has_seton_metrics = any(
        target.get("metric")
        == "initial_oceanic_crust_age_area_weighted_mean_ma"
        or str(target.get("metric", "")).startswith(
            "initial_oceanic_crust_age_area_weighted_cdf_le_"
        )
        for target in targets
    )
    has_seton_witness = any(
        record["tool"] == SETON_SUPPLEMENTAL_TOOL
        for record, _, _ in supplemental_artifacts
    )
    if SETON_SOURCE_ID in sources or has_seton_metrics or has_seton_witness:
        if SETON_SOURCE_ID not in sources:
            raise GeoValidationSuiteError(
                f"{context} Seton targets require source id '{SETON_SOURCE_ID}'"
            )
        seton_artifacts = [
            (record, artifact_path, artifact_bytes)
            for record, artifact_path, artifact_bytes in supplemental_artifacts
            if record["tool"] == SETON_SUPPLEMENTAL_TOOL
        ]
        if len(seton_artifacts) != 1:
            raise GeoValidationSuiteError(
                f"{context} derivation must declare exactly one checked Seton "
                "supplemental target derivation"
            )
        seton_record, seton_artifact_path, seton_artifact_bytes = (
            seton_artifacts[0]
        )
        _validate_seton_supplemental_derivation(
            artifact_path=seton_artifact_path,
            artifact_bytes=seton_artifact_bytes,
            record_tool=seton_record["tool"],
            bundle_source=sources[SETON_SOURCE_ID],
            bundle_targets=targets,
            context=context,
        )
    return derivation


def _load_empirical_target_bundle(path: Path, context: str) -> dict[str, Any]:
    try:
        raw_bytes = path.read_bytes()
        payload = json.loads(raw_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise GeoValidationSuiteError(
            f"{context} target bundle is invalid: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise GeoValidationSuiteError(f"{context} target bundle root must be an object")
    unknown_root = set(payload) - {
        "schema_version",
        "name",
        "description",
        "derivation",
        "sources",
        "targets",
    }
    if unknown_root:
        raise GeoValidationSuiteError(
            f"{context} target bundle has unknown fields: {', '.join(sorted(unknown_root))}"
        )
    if payload.get("schema_version") != EMPIRICAL_TARGET_BUNDLE_SCHEMA_VERSION:
        raise GeoValidationSuiteError(
            f"{context} target bundle schema_version must be "
            f"{EMPIRICAL_TARGET_BUNDLE_SCHEMA_VERSION}"
        )
    bundle_name = _required_text(payload.get("name"), f"{context} target bundle name")
    derivation = payload.get("derivation", {})
    if not isinstance(derivation, dict):
        raise GeoValidationSuiteError(f"{context} target bundle derivation must be an object")
    sources = payload.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise GeoValidationSuiteError(f"{context} target bundle requires non-empty sources")
    allowed_source_keys = {
        "dataset",
        "layer",
        "source",
        "source_format",
        "source_url",
        "source_archive_url",
        "source_version",
        "source_license",
        "source_license_url",
        "source_acquired_on",
        "source_citation",
        "source_doi",
        "source_horizontal_crs",
        "source_geographic_coverage",
        "source_vertical_datum",
        "source_native_resolution",
        "source_sha256",
        "source_archive_sha256",
    }
    normalized_sources: dict[str, dict[str, Any]] = {}
    for raw_source_id, raw_source in sources.items():
        source_id = _required_text(raw_source_id, f"{context} source id")
        if not isinstance(raw_source, dict):
            raise GeoValidationSuiteError(f"{context} source '{source_id}' must be an object")
        unknown = set(raw_source) - allowed_source_keys
        if unknown:
            raise GeoValidationSuiteError(
                f"{context} source '{source_id}' has unknown fields: "
                f"{', '.join(sorted(unknown))}"
            )
        source = dict(raw_source)
        for key in ("dataset", "layer", "source"):
            source[key] = _required_text(source.get(key), f"{context} source '{source_id}' {key}")
        for key, value in source.items():
            if key not in {"dataset", "layer", "source"}:
                source[key] = _required_text(
                    value, f"{context} source '{source_id}' {key}"
                )
        for digest_key in ("source_sha256", "source_archive_sha256"):
            digest = source.get(digest_key)
            if digest is not None and (
                len(digest) != 64
                or any(character not in "0123456789abcdefABCDEF" for character in digest)
            ):
                raise GeoValidationSuiteError(
                    f"{context} source '{source_id}' {digest_key} must be a SHA-256 digest"
                )
            if digest is not None:
                source[digest_key] = digest.lower()
        normalized_sources[source_id] = source

    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise GeoValidationSuiteError(f"{context} target bundle requires non-empty targets")
    allowed_target_keys = {
        "source_id",
        "metric",
        "source_metric",
        "source_value",
        "target_min",
        "target_max",
        "tolerance_basis",
        "source_statistic",
        "source_processing",
        "source_variable_units",
        "source_sample_cell_count",
        "source_sample_record_count",
        "source_sample_neighbor_count",
        "source_minimum_upstream_area_km2",
    }
    targets: list[dict[str, Any]] = []
    semantic_targets: list[dict[str, Any]] = []
    metrics: set[str] = set()
    for index, raw_target in enumerate(raw_targets):
        target_context = f"{context} target {index}"
        if not isinstance(raw_target, dict):
            raise GeoValidationSuiteError(f"{target_context} must be an object")
        unknown = set(raw_target) - allowed_target_keys
        if unknown:
            raise GeoValidationSuiteError(
                f"{target_context} has unknown fields: {', '.join(sorted(unknown))}"
            )
        source_id = _required_text(raw_target.get("source_id"), f"{target_context} source_id")
        if source_id not in normalized_sources:
            raise GeoValidationSuiteError(f"{target_context} references unknown source '{source_id}'")
        metric = _required_text(raw_target.get("metric"), f"{target_context} metric")
        if metric in metrics:
            raise GeoValidationSuiteError(
                f"{context} target bundle duplicates world metric '{metric}'"
            )
        source_metric = _required_text(
            raw_target.get("source_metric", metric), f"{target_context} source_metric"
        )
        source_value = _finite(raw_target.get("source_value"), f"{target_context} source_value")
        target_min = _finite(raw_target.get("target_min"), f"{target_context} target_min")
        target_max = _finite(raw_target.get("target_max"), f"{target_context} target_max")
        if target_max < target_min:
            raise GeoValidationSuiteError(f"{target_context} range is inverted")
        expanded = {
            **normalized_sources[source_id],
            "metric": metric,
            "source_metric": source_metric,
            "source_value": source_value,
            "target_min": target_min,
            "target_max": target_max,
        }
        for key, value in raw_target.items():
            if key in {
                "source_id",
                "metric",
                "source_metric",
                "source_value",
                "target_min",
                "target_max",
            }:
                continue
            if key.startswith("source_sample_") or key == "source_minimum_upstream_area_km2":
                expanded[key] = _finite(value, f"{target_context} {key}")
            else:
                expanded[key] = _required_text(value, f"{target_context} {key}")
        targets.append(expanded)
        semantic_targets.append(
            {
                **raw_target,
                "source_id": source_id,
                "metric": metric,
                "source_metric": source_metric,
                "source_value": source_value,
                "target_min": target_min,
                "target_max": target_max,
            }
        )
        metrics.add(metric)
    derivation = _validated_empirical_derivation(
        derivation,
        bundle_path=path,
        context=context,
        sources=normalized_sources,
        targets=semantic_targets,
    )
    return {
        "name": bundle_name,
        "description": str(payload.get("description", "")).strip(),
        "path": str(path),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "source_count": len(normalized_sources),
        "target_count": len(targets),
        "derivation": derivation,
        "targets": targets,
    }


def _normalize_empirical_calibration(
    raw: Any,
    *,
    manifest_path: Path,
    context: str,
) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise GeoValidationSuiteError(f"{context} empirical_calibration must be an object")
    unknown = set(raw) - {"target_bundle", "require_complete", "require_all_passed"}
    if unknown:
        raise GeoValidationSuiteError(
            f"{context} empirical_calibration has unknown fields: {', '.join(sorted(unknown))}"
        )
    raw_path = _required_text(
        raw.get("target_bundle"), f"{context} empirical_calibration target_bundle"
    )
    target_path = Path(raw_path)
    if not target_path.is_absolute():
        target_path = manifest_path.parent / target_path
    return {
        "target_bundle": _load_empirical_target_bundle(
            target_path, f"{context} empirical_calibration"
        ),
        "require_complete": _required_bool(
            raw.get("require_complete", True),
            f"{context} empirical_calibration require_complete",
        ),
        "require_all_passed": _required_bool(
            raw.get("require_all_passed", True),
            f"{context} empirical_calibration require_all_passed",
        ),
    }
