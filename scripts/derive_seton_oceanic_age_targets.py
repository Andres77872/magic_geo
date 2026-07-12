#!/usr/bin/env python3
"""Derive compact Earth age-distribution targets from the pinned Seton XYZ."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any


EXPECTED_ROW_COUNT = 1_801 * 3_601
EXPECTED_FINITE_COUNT = 3_189_443
CHUNK_SIZE = 8_192


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("configs/calibration_sources.seton_2020_oceanic_age.json"),
    )
    parser.add_argument("--source", type=Path, help="Override the manifest source path.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--derived-on", default="2026-07-11")
    return parser


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"source manifest field {key!r} must be nonempty text")
    return value


def _flush_chunk(
    weight_values: list[float],
    age_weight_values: list[float],
    cdf_weight_values: list[list[float]],
    weight_partials: list[float],
    age_weight_partials: list[float],
    cdf_weight_partials: list[list[float]],
) -> None:
    if not weight_values:
        return
    weight_partials.append(math.fsum(weight_values))
    age_weight_partials.append(math.fsum(age_weight_values))
    for index, values in enumerate(cdf_weight_values):
        cdf_weight_partials[index].append(math.fsum(values))
        values.clear()
    weight_values.clear()
    age_weight_values.clear()


def derive(source_path: Path, source: dict[str, Any], derived_on: str) -> dict[str, Any]:
    thresholds = source.get("cdf_thresholds_ma")
    if not isinstance(thresholds, list) or not thresholds:
        raise ValueError("cdf_thresholds_ma must be a nonempty array")
    threshold_values = [float(value) for value in thresholds]
    if (
        any(not math.isfinite(value) or value < 0.0 for value in threshold_values)
        or threshold_values != sorted(set(threshold_values))
    ):
        raise ValueError("cdf_thresholds_ma must be sorted unique finite nonnegative values")

    digest = hashlib.sha256()
    row_count = 0
    finite_count = 0
    minimum_age = math.inf
    maximum_age = -math.inf
    weight_values: list[float] = []
    age_weight_values: list[float] = []
    cdf_weight_values = [[] for _ in threshold_values]
    weight_partials: list[float] = []
    age_weight_partials: list[float] = []
    cdf_weight_partials = [[] for _ in threshold_values]

    with source_path.open("rb") as handle:
        for raw_line in handle:
            digest.update(raw_line)
            try:
                fields = raw_line.decode("ascii").split()
            except UnicodeDecodeError as exc:
                raise ValueError(f"row {row_count + 1} is not ASCII") from exc
            if len(fields) != 3:
                raise ValueError(f"row {row_count + 1} must have longitude, latitude, and age")
            longitude = float(fields[0])
            latitude = float(fields[1])
            expected_latitude_index, expected_longitude_index = divmod(row_count, 3_601)
            expected_longitude = -180.0 + 0.1 * expected_longitude_index
            expected_latitude = 90.0 - 0.1 * expected_latitude_index
            if not math.isclose(longitude, expected_longitude, abs_tol=5.0e-10, rel_tol=0.0):
                raise ValueError(f"row {row_count + 1} longitude is outside canonical order")
            if not math.isclose(latitude, expected_latitude, abs_tol=5.0e-10, rel_tol=0.0):
                raise ValueError(f"row {row_count + 1} latitude is outside canonical order")
            row_count += 1

            if fields[2] == "NaN":
                continue
            age_ma = float(fields[2])
            if not math.isfinite(age_ma) or age_ma < 0.0:
                raise ValueError(f"row {row_count} has invalid finite age")
            finite_count += 1
            minimum_age = min(minimum_age, age_ma)
            maximum_age = max(maximum_age, age_ma)
            longitude_factor = 0.5 if expected_longitude_index in (0, 3_600) else 1.0
            north_edge = min(90.0, latitude + 0.05)
            south_edge = max(-90.0, latitude - 0.05)
            latitude_factor = math.sin(math.radians(north_edge)) - math.sin(
                math.radians(south_edge)
            )
            weight = longitude_factor * latitude_factor
            weight_values.append(weight)
            age_weight_values.append(weight * age_ma)
            for index, threshold in enumerate(threshold_values):
                if age_ma <= threshold:
                    cdf_weight_values[index].append(weight)
            if len(weight_values) >= CHUNK_SIZE:
                _flush_chunk(
                    weight_values,
                    age_weight_values,
                    cdf_weight_values,
                    weight_partials,
                    age_weight_partials,
                    cdf_weight_partials,
                )

    _flush_chunk(
        weight_values,
        age_weight_values,
        cdf_weight_values,
        weight_partials,
        age_weight_partials,
        cdf_weight_partials,
    )
    actual_sha256 = digest.hexdigest()
    expected_sha256 = _required_text(source, "source_sha256").lower()
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"source SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )
    if row_count != EXPECTED_ROW_COUNT:
        raise ValueError(f"expected {EXPECTED_ROW_COUNT} rows, found {row_count}")
    if finite_count != EXPECTED_FINITE_COUNT:
        raise ValueError(f"expected {EXPECTED_FINITE_COUNT} finite ages, found {finite_count}")

    total_weight = math.fsum(weight_partials)
    weighted_age = math.fsum(age_weight_partials)
    cdf = [math.fsum(partials) / total_weight for partials in cdf_weight_partials]
    source_metadata = {
        key: value
        for key, value in source.items()
        if key not in {"cdf_thresholds_ma", "path"}
    }
    return {
        "schema_version": 1,
        "name": "seton_2020_oceanic_crust_age_targets_v1",
        "description": (
            "Repository-derived spherical-grid statistics from the checksum-pinned "
            "Seton et al. 2020 age grid; the CDF ordinates are not values published "
            "in the paper."
        ),
        "derivation": {
            "derived_on": derived_on,
            "runtime_requires_raw_sources": False,
            "tool": "scripts/derive_seton_oceanic_age_targets.py",
            "weighting": (
                "longitude_endpoint_trapezoid_factor_times_exact_spherical_"
                "latitude_band_sine_difference"
            ),
            "cdf_rule": "finite_source_age_ma_less_than_or_equal_to_threshold",
            "accumulation": f"canonical_file_order_math_fsum_chunks_of_{CHUNK_SIZE}",
        },
        "source": {
            **source_metadata,
            "source": str(source_path),
            "source_sha256": actual_sha256,
            "source_total_node_count": row_count,
            "source_finite_node_count": finite_count,
            "source_finite_minimum_age_ma": minimum_age,
            "source_finite_maximum_age_ma": maximum_age,
        },
        "statistics": {
            "area_weighted_mean_age_ma": round(weighted_age / total_weight, 12),
            # Preserve the manifest's canonical integer thresholds in the
            # artifact while using binary64 values for the comparisons above.
            "cdf_thresholds_ma": thresholds,
            "area_weighted_cdf_le_threshold": [round(value, 12) for value in cdf],
        },
    }


def _logical_source_path(manifest_path: Path, source: dict[str, Any]) -> str:
    """Return stable project-relative provenance, independent of input override."""

    declared = Path(_required_text(source, "path"))
    logical = declared if declared.is_absolute() else manifest_path.parent / declared
    logical = Path(os.path.normpath(logical))
    try:
        return logical.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return logical.as_posix()


def main() -> int:
    args = _parser().parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    sources = manifest.get("sources")
    if not isinstance(sources, list) or len(sources) != 1 or not isinstance(sources[0], dict):
        raise ValueError("Seton source manifest must contain exactly one source object")
    source = sources[0]
    source_path = args.source
    if source_path is None:
        source_path = Path(_required_text(source, "path"))
        if not source_path.is_absolute():
            source_path = args.manifest.parent / source_path
    payload = derive(source_path, source, args.derived_on)
    payload["source"]["source"] = _logical_source_path(args.manifest, source)
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
