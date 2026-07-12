#!/usr/bin/env python3
"""Benchmark JSON and .mgeo persistence on an existing generated world."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import msgpack

from magic_geo.io import read_world, write_json, write_world
from magic_geo.serialization import validate_world_payload

try:
    import resource
except ImportError:  # Windows
    resource = None  # type: ignore[assignment]


T = TypeVar("T")


def timed(operation: Callable[[], T]) -> tuple[T, float]:
    started = time.perf_counter()
    result = operation()
    return result, time.perf_counter() - started


def value_digest(world: dict[str, Any]) -> str:
    packed = msgpack.packb(world, use_bin_type=True)
    return hashlib.sha256(packed).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("world", type=Path, help="Existing generated JSON world")
    parser.add_argument(
        "--skip-json-write",
        action="store_true",
        help="Skip the memory-intensive pretty JSON write comparison",
    )
    args = parser.parse_args()

    source = args.world.resolve()
    with tempfile.TemporaryDirectory(prefix="magic-geo-serialization-") as directory:
        root = Path(directory)
        json_target = root / "world.json"
        binary_target = root / "world.mgeo"
        strict_binary_target = root / "world-strict.mgeo"

        world, json_load_seconds = timed(
            lambda: read_world(source, format="json", validate_model=False)
        )
        _, validation_seconds = timed(lambda: validate_world_payload(world))
        expected_digest = value_digest(world)

        json_save_seconds: float | None = None
        if not args.skip_json_write:
            _, json_save_seconds = timed(lambda: write_json(json_target, world))
        _, binary_save_seconds = timed(
            lambda: write_world(binary_target, world, validate_model=False)
        )
        _, strict_binary_save_seconds = timed(
            lambda: write_world(strict_binary_target, world, validate_model=True)
        )
        binary_size = binary_target.stat().st_size
        json_size = (
            source.stat().st_size
            if args.skip_json_write
            else json_target.stat().st_size
        )

        del world
        gc.collect()
        loaded, binary_load_seconds = timed(
            lambda: read_world(binary_target, validate_model=False)
        )
        actual_digest = value_digest(loaded)
        del loaded
        gc.collect()
        strict_loaded, strict_binary_load_seconds = timed(
            lambda: read_world(binary_target, validate_model=True)
        )
        strict_actual_digest = value_digest(strict_loaded)

        peak_rss_bytes: int | None = None
        if resource is not None:
            raw_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            peak_rss_bytes = raw_peak if sys.platform == "darwin" else raw_peak * 1024

        result = {
            "source": str(source),
            "semantic_sha256_equal": (
                actual_digest == expected_digest == strict_actual_digest
            ),
            "json_bytes": json_size,
            "mgeo_bytes": binary_size,
            "mgeo_to_json_size_ratio": binary_size / json_size,
            "json_load_seconds": json_load_seconds,
            "json_model_validation_seconds": validation_seconds,
            "json_strict_load_estimate_seconds": (
                json_load_seconds + validation_seconds
            ),
            "json_save_seconds": json_save_seconds,
            "mgeo_load_seconds": binary_load_seconds,
            "mgeo_save_seconds": binary_save_seconds,
            "mgeo_strict_load_seconds": strict_binary_load_seconds,
            "mgeo_strict_save_seconds": strict_binary_save_seconds,
            "load_speedup": json_load_seconds / binary_load_seconds,
            "strict_load_speedup": (
                (json_load_seconds + validation_seconds)
                / strict_binary_load_seconds
            ),
            "save_speedup": (
                None
                if json_save_seconds is None
                else json_save_seconds / binary_save_seconds
            ),
            "strict_save_speedup": (
                None
                if json_save_seconds is None
                else json_save_seconds / strict_binary_save_seconds
            ),
            "peak_rss_bytes": peak_rss_bytes,
        }
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
