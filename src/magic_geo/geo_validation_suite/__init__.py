"""Manifest-driven geo validation suite.

`manifest` loads and validates the YAML matrix and its empirical
target bundles, `evaluate` runs the expectations against generated
worlds, and `report` renders the markdown summary."""

from __future__ import annotations

from ._constants import *  # noqa: F401,F403
from .errors import GeoValidationSuiteError
from ._helpers import (
    _required_text,
    _finite,
    _required_bool,
    _required_integer,
    _required_sha256,
    _validate_exact_fields,
    _deep_merge,
)
from .empirical import (
    _validate_seton_supplemental_derivation,
    _validated_empirical_derivation,
    _load_empirical_target_bundle,
    _normalize_empirical_calibration,
)
from .manifest import _normalize_expectations, load_geo_validation_manifest
from .evaluate import (
    geo_fingerprint,
    _evaluate_expectations,
    _evaluate_relation,
    _evaluate_empirical_calibration,
    evaluate_geo_validation_suite,
)
from .report import write_geo_validation_suite_markdown

__all__ = [
    "CIVILIZATION_NESTED_FIELDS",
    "CIVILIZATION_TOP_LEVEL_FIELDS",
    "COMPARISON_OPERATORS",
    "EMPIRICAL_TARGET_BUNDLE_SCHEMA_VERSION",
    "GEO_VALIDATION_SUITE_SCHEMA_VERSION",
    "GeoValidationSuiteError",
    "MAX_SCENARIO_COUNT",
    "SETON_CDF_THRESHOLDS_MA",
    "SETON_SOURCE_ID",
    "SETON_SUPPLEMENTAL_NAME",
    "SETON_SUPPLEMENTAL_TOOL",
    "_deep_merge",
    "_evaluate_empirical_calibration",
    "_evaluate_expectations",
    "_evaluate_relation",
    "_finite",
    "_load_empirical_target_bundle",
    "_normalize_empirical_calibration",
    "_normalize_expectations",
    "_required_bool",
    "_required_integer",
    "_required_sha256",
    "_required_text",
    "_validate_exact_fields",
    "_validate_seton_supplemental_derivation",
    "_validated_empirical_derivation",
    "evaluate_geo_validation_suite",
    "geo_fingerprint",
    "load_geo_validation_manifest",
    "write_geo_validation_suite_markdown",
]
