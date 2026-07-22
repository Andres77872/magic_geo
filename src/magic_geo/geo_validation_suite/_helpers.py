"""Field coercion and validation helpers."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from .errors import GeoValidationSuiteError


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
