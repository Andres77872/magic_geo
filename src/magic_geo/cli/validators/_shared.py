"""Helpers shared by more than one validator module."""

from __future__ import annotations

import math
from typing import Any

from .._constants import (
    NOMINAL_TIME_BASIS,
    NOMINAL_TIME_MODEL,
    NOMINAL_TIME_RECORD_FIELDS,
    NOMINAL_TIME_SOURCE_PARAMETER,
)


def _nominal_time_record_valid(
    record: dict[str, Any],
    *,
    expected_start_ma: float,
    expected_end_ma: float,
    expected_role: str,
) -> bool:
    """Validate the native nominal interval shared by all maturation histories."""

    if not NOMINAL_TIME_RECORD_FIELDS.issubset(record):
        return False
    if (
        record.get("nominal_time_model") != NOMINAL_TIME_MODEL
        or record.get("nominal_time_unit") != "Ma"
        or record.get("nominal_time_basis") != NOMINAL_TIME_BASIS
        or record.get("nominal_time_source_parameter")
        != NOMINAL_TIME_SOURCE_PARAMETER
        or record.get("nominal_time_role") != expected_role
        or record.get("nominal_time_calibrated") is not False
        or record.get("physical_time_resolved") is not False
    ):
        return False
    expected_duration_ma = expected_end_ma - expected_start_ma
    try:
        values = {
            "nominal_interval_start_ma": float(
                record["nominal_interval_start_ma"]
            ),
            "nominal_interval_end_ma": float(record["nominal_interval_end_ma"]),
            "nominal_interval_duration_ma": float(
                record["nominal_interval_duration_ma"]
            ),
            "nominal_elapsed_time_ma": float(record["nominal_elapsed_time_ma"]),
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    expected_values = {
        "nominal_interval_start_ma": expected_start_ma,
        "nominal_interval_end_ma": expected_end_ma,
        "nominal_interval_duration_ma": expected_duration_ma,
        "nominal_elapsed_time_ma": expected_end_ma,
    }
    return (
        all(math.isfinite(value) for value in values.values())
        and all(
            math.isclose(
                values[field],
                expected,
                abs_tol=1.0e-10,
                rel_tol=1.0e-12,
            )
            for field, expected in expected_values.items()
        )
        and record.get("advances_nominal_time")
        is (expected_duration_ma > 0.0)
    )
