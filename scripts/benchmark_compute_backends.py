#!/usr/bin/env python3
"""Benchmark native CPU/OpenCL/CUDA generation and verify physical parity.

This intentionally calls the native boundary directly so Python enrichment does
not hide acceleration gains. Backend telemetry is the only payload field
excluded from parity comparisons.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from magic_geo.config import load_config
from magic_geo.native import _library_path, backend_info, generate_world


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACCELERATOR_BACKENDS = {"opencl", "cuda"}


def _parse_csv_ints(value: str) -> list[int]:
    values = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not values or any(item < 128 for item in values):
        raise argparse.ArgumentTypeError("cell counts must be comma-separated integers >= 128")
    return values


def _parse_backends(value: str) -> list[str]:
    values = [item.strip() for item in value.split(",") if item.strip()]
    invalid = sorted(set(values) - {"cpu", "opencl", "cuda", "auto"})
    if not values or invalid:
        raise argparse.ArgumentTypeError(
            f"backends must be selected from cpu,opencl,cuda,auto; invalid={invalid}"
        )
    return values


def _parse_auto_expectations(value: str) -> dict[int, str]:
    expectations: dict[int, str] = {}
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        cell_text, separator, backend = item.partition("=")
        if not separator:
            raise argparse.ArgumentTypeError(
                "auto expectations must use CELL_COUNT=BACKEND entries"
            )
        try:
            cell_count = int(cell_text.strip())
        except ValueError as error:
            raise argparse.ArgumentTypeError(
                f"invalid auto expectation cell count: {cell_text!r}"
            ) from error
        backend = backend.strip()
        if cell_count < 128:
            raise argparse.ArgumentTypeError(
                "auto expectation cell counts must be >= 128"
            )
        if backend not in {"cpu", "opencl", "cuda"}:
            raise argparse.ArgumentTypeError(
                "auto expectation backends must be cpu, opencl, or cuda"
            )
        if cell_count in expectations:
            raise argparse.ArgumentTypeError(
                f"duplicate auto expectation for {cell_count} cells"
            )
        expectations[cell_count] = backend
    if not expectations:
        raise argparse.ArgumentTypeError(
            "auto expectations must contain at least one CELL_COUNT=BACKEND entry"
        )
    return expectations


def _physical_payload_digest(world: dict[str, Any]) -> str:
    # A shallow replacement avoids retaining a second copy of the very large
    # nested physical payload while still hashing every non-telemetry field.
    normalized = dict(world)
    normalized["backend"] = {}
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_json_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _git_metadata() -> dict[str, Any]:
    def run(*arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    try:
        commit = run("rev-parse", "HEAD")
        dirty = bool(run("status", "--porcelain"))
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError) as error:
        return {
            "commit": None,
            "dirty": None,
            "error": f"{type(error).__name__}: {error}",
        }


def _actual_cell_count(world: dict[str, Any]) -> int:
    summary = world.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("native payload has no summary object")
    value = summary.get("cell_count")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RuntimeError("native payload summary has no valid cell_count")
    return value


def _dispatch_count(telemetry: dict[str, Any], backend: str) -> int:
    field = f"{backend}_kernel_dispatch_count"
    value = telemetry.get(field, 0)
    if isinstance(value, bool):
        raise RuntimeError(f"backend telemetry {field} is not an integer")
    try:
        count = int(value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"backend telemetry {field} is not an integer") from error
    if count < 0:
        raise RuntimeError(f"backend telemetry {field} is negative")
    return count


def _validate_backend_execution(
    world: dict[str, Any],
    requested_backend: str,
    expected_auto_backend: str | None,
) -> tuple[dict[str, Any], str]:
    telemetry = world.get("backend")
    if not isinstance(telemetry, dict):
        raise RuntimeError("native payload has no backend telemetry object")
    selected_backend = telemetry.get("selected_backend")
    if selected_backend not in {"cpu", "opencl", "cuda"}:
        raise RuntimeError(f"native payload selected invalid backend {selected_backend!r}")

    if requested_backend != "auto" and selected_backend != requested_backend:
        raise RuntimeError(
            f"explicit {requested_backend} request selected {selected_backend}"
        )
    if expected_auto_backend is not None and selected_backend != expected_auto_backend:
        raise RuntimeError(
            "automatic backend expectation failed: "
            f"expected {expected_auto_backend}, selected {selected_backend}"
        )

    opencl_dispatches = _dispatch_count(telemetry, "opencl")
    cuda_dispatches = _dispatch_count(telemetry, "cuda")
    if selected_backend == "opencl" and opencl_dispatches <= 0:
        raise RuntimeError("OpenCL selected without an OpenCL kernel dispatch")
    if selected_backend == "cuda" and cuda_dispatches <= 0:
        raise RuntimeError("CUDA selected without a CUDA kernel dispatch")
    if selected_backend == "cpu" and (opencl_dispatches > 0 or cuda_dispatches > 0):
        raise RuntimeError("CPU selected despite accelerator kernel dispatches")
    return telemetry, selected_backend


def _is_initial_explicit_unavailability(backend: str, error: Exception) -> bool:
    if backend not in ACCELERATOR_BACKENDS or not isinstance(error, RuntimeError):
        return False
    display_name = "OpenCL" if backend == "opencl" else "CUDA"
    return str(error).startswith(
        f"explicit {display_name} backend requested but initialization failed:"
    )


def _percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def _run_once(config: dict[str, Any], backend: str) -> tuple[float, dict[str, Any]]:
    candidate = copy.deepcopy(config)
    candidate["compute"]["backend"] = backend
    start = time.perf_counter()
    world = generate_world(candidate)
    return time.perf_counter() - start, world


def _effective_config_digest(config: dict[str, Any], backend: str) -> str:
    candidate = copy.deepcopy(config)
    candidate["compute"]["backend"] = backend
    return _canonical_json_digest(candidate)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/earthlike_seed.yaml"),
        help="base world configuration",
    )
    parser.add_argument(
        "--cells",
        type=_parse_csv_ints,
        default=_parse_csv_ints("4096,16384,32768"),
        help="comma-separated requested cell counts",
    )
    parser.add_argument(
        "--backends",
        type=_parse_backends,
        default=_parse_backends("cpu,opencl,cuda"),
        help="comma-separated backends",
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--threads", type=int, default=0)
    parser.add_argument("--erosion-iterations", type=int, default=6)
    parser.add_argument(
        "--include-cells",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="include final cells in parity and timing payloads (default: true)",
    )
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="fail instead of recording an unavailable explicit backend",
    )
    parser.add_argument(
        "--expect-auto",
        type=_parse_auto_expectations,
        default={},
        metavar="CELL_COUNT=BACKEND,...",
        help=(
            "expected automatic selections, for example "
            "4096=cpu,8192=cuda; adds auto to the measured backends"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="also write the complete JSON report to this path",
    )
    args = parser.parse_args()
    if args.repeats < 1 or args.warmups < 0:
        parser.error("--repeats must be >= 1 and --warmups must be >= 0")
    unexpected_cells = sorted(set(args.expect_auto) - set(args.cells))
    if unexpected_cells:
        parser.error(
            "--expect-auto contains cell counts not selected by --cells: "
            + ",".join(str(value) for value in unexpected_cells)
        )

    config_path = args.config.expanduser().resolve()
    native_library_path = _library_path().resolve()
    base = load_config(config_path).model_dump(mode="json")
    base["compute"]["threads"] = args.threads
    base["erosion"]["iterations"] = args.erosion_iterations
    base["output"]["include_cells"] = args.include_cells
    base["output"]["float_precision"] = 8

    report: dict[str, Any] = {
        "benchmark": "native_compute_backend_end_to_end_v2",
        "timestamp_utc": _utc_timestamp(),
        "config": str(args.config),
        "config_absolute_path": str(config_path),
        "config_sha256": _file_digest(config_path),
        "native_library": {
            "absolute_path": str(native_library_path),
            "sha256": _file_digest(native_library_path),
        },
        "git": _git_metadata(),
        "runtime": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "repeats": args.repeats,
        "warmups": args.warmups,
        "threads": args.threads,
        "erosion_iterations": args.erosion_iterations,
        "include_cells": args.include_cells,
        "float_precision": base["output"]["float_precision"],
        "float_precision_scope": "native JSON numeric serialization",
        "scope": {
            "boundary": "native generate_world JSON boundary",
            "timed_operation": (
                "ctypes config packing/call, complete native world generation and JSON "
                "serialization, UTF-8 copy/decode, and Python json.loads"
            ),
            "parity": "all returned payload fields except backend telemetry",
            "excluded_pipeline": "Python post-generation enrichment",
            "include_cells": args.include_cells,
        },
        "expected_auto_backends": {
            str(cell_count): backend
            for cell_count, backend in sorted(args.expect_auto.items())
        },
        "cases": [],
    }

    for cell_count in args.cells:
        config = copy.deepcopy(base)
        config["mesh"]["cell_count"] = cell_count
        reference_digest: str | None = None
        reference_median: float | None = None
        case: dict[str, Any] = {
            "requested_cell_count": cell_count,
            "actual_cell_count": None,
            "backends": [],
        }
        ordered_backends = ["cpu", *[item for item in args.backends if item != "cpu"]]
        if args.expect_auto and "auto" not in ordered_backends:
            ordered_backends.append("auto")
        for backend in ordered_backends:
            expected_auto_backend = (
                args.expect_auto.get(cell_count) if backend == "auto" else None
            )
            measurement: dict[str, Any] = {
                "requested_backend": backend,
                "effective_config_sha256": _effective_config_digest(config, backend),
            }
            try:
                first_generation_seconds, first_world = _run_once(config, backend)
            except Exception as error:
                if (
                    not args.require_all
                    and _is_initial_explicit_unavailability(backend, error)
                ):
                    measurement.update(
                        {
                            "status": "unavailable",
                            "error": f"{type(error).__name__}: {error}",
                        }
                    )
                    case["backends"].append(measurement)
                    continue
                raise

            first_telemetry, first_selected_backend = _validate_backend_execution(
                first_world, backend, expected_auto_backend
            )
            actual_cell_count = _actual_cell_count(first_world)
            if case["actual_cell_count"] is None:
                case["actual_cell_count"] = actual_cell_count
            elif case["actual_cell_count"] != actual_cell_count:
                raise RuntimeError(
                    f"{backend} generated {actual_cell_count} cells; "
                    f"CPU generated {case['actual_cell_count']}"
                )

            for _ in range(args.warmups):
                _, warmup_world = _run_once(config, backend)
                _validate_backend_execution(
                    warmup_world, backend, expected_auto_backend
                )
                if _actual_cell_count(warmup_world) != actual_cell_count:
                    raise RuntimeError(
                        f"{backend} actual cell count changed during warmup"
                    )

            elapsed: list[float] = []
            payload_digests: list[str] = []
            world: dict[str, Any] | None = None
            telemetry: dict[str, Any] = first_telemetry
            selected_backend = first_selected_backend
            for _ in range(args.repeats):
                duration, world = _run_once(config, backend)
                telemetry, selected_backend = _validate_backend_execution(
                    world, backend, expected_auto_backend
                )
                if _actual_cell_count(world) != actual_cell_count:
                    raise RuntimeError(
                        f"{backend} actual cell count changed during measured repeats"
                    )
                elapsed.append(duration)
                payload_digests.append(_physical_payload_digest(world))
            if len(set(payload_digests)) != 1:
                raise RuntimeError(
                    f"{backend} physical payload is nondeterministic at "
                    f"{cell_count} requested cells: {payload_digests}"
                )

            assert world is not None
            payload_digest = payload_digests[0]
            median = statistics.median(elapsed)
            measurement.update(
                {
                    "status": "ok",
                    "selected_backend": selected_backend,
                    "active_backend": telemetry.get("active_backend", "unknown"),
                    "actual_cell_count": actual_cell_count,
                    "pre_measurement_first_generation_seconds": first_generation_seconds,
                    "seconds": elapsed,
                    "median_seconds": median,
                    "min_seconds": min(elapsed),
                    "max_seconds": max(elapsed),
                    "p95_seconds": _percentile_95(elapsed),
                    "standard_deviation_seconds": (
                        statistics.stdev(elapsed) if len(elapsed) > 1 else 0.0
                    ),
                    "coefficient_of_variation": (
                        statistics.stdev(elapsed) / statistics.mean(elapsed)
                        if len(elapsed) > 1
                        else 0.0
                    ),
                    "physical_payload_sha256": payload_digest,
                    "physical_payload_sha256_per_repeat": payload_digests,
                    "backend_telemetry": telemetry,
                }
            )
            if backend == "cpu":
                reference_digest = payload_digest
                reference_median = median
                measurement["physical_payload_equal_to_cpu"] = True
                measurement["speedup_over_cpu"] = 1.0
            else:
                if reference_digest is None or reference_median is None:
                    raise RuntimeError("CPU reference measurement is missing")
                measurement["physical_payload_equal_to_cpu"] = (
                    payload_digest == reference_digest
                )
                if not measurement["physical_payload_equal_to_cpu"]:
                    raise RuntimeError(
                        f"{backend} physical payload differs from CPU at {cell_count} cells"
                    )
                measurement["speedup_over_cpu"] = reference_median / median
            case["backends"].append(measurement)
        report["cases"].append(case)

    # Probe only after every timed generation so capability discovery cannot
    # warm up a CUDA/OpenCL runtime or otherwise bias first-generation timings.
    report["capability"] = backend_info()
    report["completed_at_utc"] = _utc_timestamp()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        output_path = args.output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
