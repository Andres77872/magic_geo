from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import ValidationError

from .api import generate_geo_world
from .calibration import CalibrationError, evaluate_calibration_targets
from .config import WorldConfig
from .geo_validation import (
    GEO_MODEL_LIMITATIONS,
    GEO_VALIDATION_SCOPE,
    extract_geo_metrics,
    validate_geo_world,
)


GEO_VALIDATION_SUITE_SCHEMA_VERSION = 1
EMPIRICAL_TARGET_BUNDLE_SCHEMA_VERSION = 1
MAX_SCENARIO_COUNT = 64

COMPARISON_OPERATORS = {"lt", "le", "gt", "ge", "eq"}

SETON_SOURCE_ID = "seton_2020_oceanic_age"
SETON_SUPPLEMENTAL_NAME = "seton_2020_oceanic_crust_age_targets_v1"
SETON_SUPPLEMENTAL_TOOL = "scripts/derive_seton_oceanic_age_targets.py"
SETON_CDF_THRESHOLDS_MA = tuple(range(20, 201, 20))

# Determinism is evaluated over the complete output minus explicitly excluded
# civilization layers. This is intentionally exclusion-based so new natural
# fields cannot silently escape the fingerprint.
CIVILIZATION_TOP_LEVEL_FIELDS = {
    "agricultural_zones",
    "borders",
    "cadet_branches",
    "campaign_front_histories",
    "campaign_movements",
    "campaign_operations_model",
    "campaign_path_segments",
    "conflict_model",
    "conflicts",
    "cultural_site_model",
    "culture_region_model",
    "cultures",
    "demographic_agent_histories",
    "demographic_agent_model",
    "dynasties",
    "dynasty_model",
    "economy_histories",
    "economy_history_model",
    "firm_agents",
    "historical_eras",
    "historical_event_model",
    "historical_events",
    "household_cohorts",
    "individual_agents",
    "individual_life_event_model",
    "individual_life_events",
    "land_use_zone_model",
    "language_region_model",
    "language_regions",
    "lexical_correspondences",
    "lexical_diffusion_histories",
    "logistics_exchange_model",
    "logistics_networks",
    "market_agent_orders",
    "market_clearing_model",
    "market_clearing_records",
    "market_exchanges",
    "market_inventory_histories",
    "market_price_iterations",
    "marriage_alliances",
    "mining_zones",
    "natural_frontier_model",
    "natural_frontiers",
    "navigability_model",
    "navigable_waterways",
    "phonological_histories",
    "phonological_rules",
    "phonology_history_model",
    "political_border_model",
    "political_region_graph",
    "political_region_model",
    "political_regions",
    "population_histories",
    "population_history_model",
    "population_region_model",
    "population_regions",
    "port_site_model",
    "port_sites",
    "route_capacity_constraints",
    "route_corridor_model",
    "route_corridors",
    "route_network_model",
    "routes",
    "ruins",
    "ruler_genealogy_model",
    "rulers",
    "sacred_areas",
    "settlement_selection_model",
    "settlements",
    "speaker_population_histories",
    "strategic_campaign_plans",
    "tactical_engagements",
    "territorial_boundary_segments",
    "territorial_snapshot_model",
    "territorial_snapshots",
    "trade_flow_model",
    "trade_flows",
    "trade_route_graph",
    "worldbuilding_realism_checks",
    "worldbuilding_realism_model",
}

CIVILIZATION_NESTED_FIELDS = {
    "agricultural_potential_index",
    "agricultural_zone_id",
    "coastal_navigability_index",
    "coastal_route_index",
    "culture_region_id",
    "culture_region_ids",
    "harbor_suitability_index",
    "language_region_id",
    "language_region_ids",
    "market_value_index",
    "mining_potential_index",
    "mining_zone_id",
    "mountain_pass_route_index",
    "natural_frontier_id",
    "natural_frontier_index",
    "natural_frontier_type",
    "navigability_class",
    "navigability_index",
    "navigable_waterway_id",
    "oasis_route_index",
    "political_region_id",
    "political_region_ids",
    "population",
    "port_site_id",
    "port_site_ids",
    "port_site_type",
    "port_suitability_index",
    "river_mouth_port_index",
    "river_navigability_index",
    "river_valley_route_index",
    "route_corridor_id",
    "route_corridor_index",
    "route_corridor_type",
    "route_ids",
    "settlement_id",
    "settlement_ids",
    "settlement_score",
    "strait_access_index",
    "transport_chokepoint_index",
}


class GeoValidationSuiteError(ValueError):
    pass


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GeoValidationSuiteError(f"{context} must be a non-empty string")
    return value.strip()


def _finite(value: Any, context: str) -> float:
    if isinstance(value, bool):
        raise GeoValidationSuiteError(f"{context} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise GeoValidationSuiteError(f"{context} must be a finite number") from exc
    if not math.isfinite(number):
        raise GeoValidationSuiteError(f"{context} must be a finite number")
    return number


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


def _required_bool(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        raise GeoValidationSuiteError(f"{context} must be a boolean")
    return value


def _required_integer(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GeoValidationSuiteError(f"{context} must be an integer")
    return value


def _required_sha256(value: Any, context: str) -> str:
    digest = _required_text(value, context).lower()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise GeoValidationSuiteError(f"{context} must be a SHA-256 digest")
    return digest


def _validate_exact_fields(
    value: Any,
    expected_fields: set[str],
    context: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GeoValidationSuiteError(f"{context} must be an object")
    actual_fields = set(value)
    if actual_fields != expected_fields:
        missing = sorted(expected_fields - actual_fields)
        extra = sorted(actual_fields - expected_fields)
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("extra " + ", ".join(extra))
        raise GeoValidationSuiteError(
            f"{context} fields do not match the canonical schema: "
            + "; ".join(details)
        )
    return value


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


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any], path: str = "") -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overrides.items():
        current_path = f"{path}.{key}" if path else str(key)
        if key not in merged:
            raise GeoValidationSuiteError(f"unknown config override '{current_path}'")
        if isinstance(merged[key], dict):
            if not isinstance(value, dict):
                raise GeoValidationSuiteError(f"config override '{current_path}' must be an object")
            merged[key] = _deep_merge(merged[key], value, current_path)
        elif isinstance(value, dict):
            raise GeoValidationSuiteError(f"config override '{current_path}' cannot be an object")
        else:
            merged[key] = value
    return merged


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
