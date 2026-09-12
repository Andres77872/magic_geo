#!/usr/bin/env python3
"""Run pytest with durable progress and snapshots of already-generated fixtures.

Example: python scripts/research/regression_sweep.py --output-dir runs/sweep-01 \
    -- tests/test_human_validators.py -q

This startup-only plugin never generates a world, mutates a fixture, imports a
test to find its cache, or restores archived caches. Configurations are rebuilt
with the existing fixture's exact recipe at archive time; source hashes expose
changes during a run, but this is not interception of the original generator
call. Use frozen source/config files when exact generation provenance matters.
Serial pytest is supported; worker-process caches from xdist are not inspected.
With --archive-failure-worlds, ordinary failed calls also retain world-shaped
local dictionaries from the failing test's traceback. These are explicitly
failure-time snapshots, not original generation/configuration provenance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import faulthandler
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any

import pytest


REPO = Path(__file__).resolve().parents[2]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _diagnostic_repr(value: Any) -> str:
    """Bound reporting-only Python values; never coerce archived world data."""
    try:
        rendered = repr(value)
    except Exception:
        rendered = f"<{type(value).__name__}: repr failed>"
    return rendered if len(rendered) <= 2048 else rendered[:2048] + "... <truncated>"


def _write_json(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _provenance() -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(REPO), *args], text=True, timeout=20)

    result: dict[str, Any] = {"repository": str(REPO), "source_sha256": {}}
    try:
        result["git_head"] = git("rev-parse", "HEAD").strip()
        result["git_status"] = git("status", "--porcelain=v1")
        names = git("ls-files", "--cached", "--others", "--exclude-standard", "-z", "--",
                    "src", "cpp", "configs", "tests", "scripts/research", "pyproject.toml")
        for name in sorted(set(names.split("\0")) - {""}):
            path = REPO / name
            if path.is_file():
                result["source_sha256"][name] = _sha256(path)
    except (OSError, subprocess.SubprocessError) as exc:
        result["git_provenance_error"] = f"{type(exc).__name__}: {exc}"
    override = os.environ.get("MAGIC_GEO_NATIVE_LIBRARY")
    candidates = [Path(override).expanduser()] if override else [
        REPO / "src/magic_geo" / name
        for name in ("libmagic_geo_native.so", "libmagic_geo_native.dylib", "magic_geo_native.dll")
    ]
    result["native_library_candidates_sha256"] = {
        str(path.resolve()): _sha256(path) for path in candidates if path.is_file()
    }
    return result


class SweepRecorder:
    """Pytest hooks record reports before teardown can block."""

    def __init__(self, output: Path, *, archive_failure_worlds: bool = False) -> None:
        self.output = output
        self.events = (output / "events.jsonl").open("x", encoding="utf-8")
        self.failures = (output / "failures.txt").open("x", encoding="utf-8")
        self.completed = (output / "completed-nodeids.jsonl").open("x", encoding="utf-8")
        self.archives = (output / "world-archives.jsonl").open("x", encoding="utf-8")
        self.world_dir = output / "worlds"
        self.world_dir.mkdir()
        self.config_dir = output / "configs"
        self.config_dir.mkdir()
        # Strong references prevent Python from reusing an archived object's ID.
        self.seen_worlds: dict[int, tuple[Any, dict[str, Any]]] = {}
        self.seen_aliases: set[tuple[str, str, str, int]] = set()
        self.outcomes: dict[str, list[str]] = {}
        self.archive_errors = 0
        self.archive_failure_worlds = archive_failure_worlds
        self.pending_failure_worlds: dict[str, list[tuple[Any, dict[str, Any]]]] = {}

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: Any, call: Any) -> Any:
        outcome = yield
        report = outcome.get_result()
        if not self.archive_failure_worlds or not report.failed or call.when != "call" or call.excinfo is None:
            return
        pending = []
        seen = set()
        for entry in call.excinfo.traceback:
            # Inspect only this test's own frames, not unrelated library locals.
            if Path(str(entry.path)).resolve() != Path(item.path).resolve():
                continue
            for name, value in tuple(entry.frame.f_locals.items()):
                if (type(value) is not dict or type(value.get("cells")) is not list
                        or type(value.get("summary")) is not dict
                        or type(value.get("planet_parameters")) is not dict
                        or id(value) in seen or id(value) in self.seen_worlds):
                    continue
                seen.add(id(value))
                pending.append((value, {"source_file": str(entry.path),
                    "source_line": entry.lineno + 1, "local_name": name}))
        self.pending_failure_worlds[report.nodeid] = pending

    def event(self, kind: str, *, durable: bool = False, **fields: Any) -> None:
        record = {"event": kind, "utc": _now(), "monotonic_seconds": time.monotonic(), **fields}
        self.events.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        self.events.flush()
        if durable:
            os.fsync(self.events.fileno())

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_logstart(self, nodeid: str, location: Any) -> None:
        self.outcomes[nodeid] = []
        self.event("test_start", nodeid=nodeid, location=location)

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_logreport(self, report: Any) -> None:
        context = getattr(report, "context", None)
        subtest = None if context is None else {
            "encoding": "bounded_repr_of_report_context",
            "message_repr": _diagnostic_repr(context.msg),
            "parameters_repr": {str(key): _diagnostic_repr(value) for key, value in context.kwargs.items()},
        }
        self.outcomes.setdefault(report.nodeid, []).append(report.outcome)
        self.event("test_report", durable=report.failed, nodeid=report.nodeid,
                   phase=report.when, outcome=report.outcome,
                   duration_seconds=report.duration, subtest=subtest)
        if report.failed:
            # Write the complete failure before attempting any possibly large
            # world snapshot, and before pytest begins the teardown phase.
            self.failures.write(f"\n[{_now()}] {report.nodeid} ({report.when})\n")
            if subtest is not None:
                self.failures.write(json.dumps(subtest, ensure_ascii=False) + "\n")
            self.failures.write(report.longreprtext + "\n")
            for heading, content in report.sections:
                self.failures.write(f"--- {heading} ---\n{content}\n")
            self.failures.flush()
            os.fsync(self.failures.fileno())
        # Failure text is durable before any potentially large local snapshot.
        for world, location in self.pending_failure_worlds.pop(report.nodeid, []):
            try:
                snapshot = self._write_world(world)
                record = {"utc": _now(), "trigger": f"{report.nodeid}:{report.when}",
                          "cache": "failure_frame", "object_id": id(world), **location, **snapshot,
                          "config_file": None,
                          "config_provenance": "unavailable_not_observed_at_generation",
                          "world_provenance": "test_local_value_at_failure_may_include_test_mutations"}
                self.archives.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                self.archives.flush()
                os.fsync(self.archives.fileno())
                self.event("world_archived", **record)
            except Exception as exc:
                self.archive_errors += 1
                self.event("archive_error", durable=True, cache="failure_frame", **location,
                           error=f"{type(exc).__name__}: {exc}")
        self.archive_worlds(trigger=f"{report.nodeid}:{report.when}")

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_logfinish(self, nodeid: str, location: Any) -> None:
        outcomes = self.outcomes.pop(nodeid, [])
        outcome = "failed" if "failed" in outcomes else "skipped" if "skipped" in outcomes else "passed"
        self.event("test_end", nodeid=nodeid, outcome=outcome)
        self.completed.write(json.dumps(nodeid, ensure_ascii=False) + "\n")
        self.completed.flush()
        os.fsync(self.completed.fileno())
        self.archive_worlds(trigger=f"{nodeid}:end")

    def pytest_collection_finish(self, session: Any) -> None:
        paths = {Path(item.path).resolve() for item in session.items}
        _write_json(self.output / "collected-sources.json", {
            str(path): _sha256(path) for path in sorted(paths) if path.is_file()
        })
        self.event("collection_finish", count=len(session.items))

    @pytest.hookimpl(tryfirst=True)
    def pytest_collectreport(self, report: Any) -> None:
        if report.failed:
            self.event("collection_failure", durable=True, nodeid=report.nodeid)
            self.failures.write(f"\n[{_now()}] {report.nodeid} (collection)\n{report.longreprtext}\n")
            self.failures.flush()
            os.fsync(self.failures.fileno())

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> None:
        self.event("session_finish", durable=True, exit_status=int(exitstatus))
        self.archive_worlds(trigger="session_finish")

    def _write_world(self, world: Any) -> dict[str, Any]:
        cached = self.seen_worlds.get(id(world))
        if cached is not None:
            return cached[1]
        digest = hashlib.sha256()
        size = 0
        # Stream the full unfiltered JSON, buffering encoder fragments so large
        # climate certificates do not need a second full in-memory byte copy.
        with tempfile.NamedTemporaryFile(dir=self.world_dir, suffix=".tmp", delete=False) as raw:
            temporary = Path(raw.name)
            try:
                with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
                    fragments: list[str] = []
                    fragment_size = 0
                    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                    for fragment in encoder.iterencode(world):
                        fragments.append(fragment)
                        fragment_size += len(fragment)
                        if fragment_size >= 65536:
                            data = "".join(fragments).encode("utf-8")
                            compressed.write(data)
                            digest.update(data)
                            size += len(data)
                            fragments, fragment_size = [], 0
                    if fragments:
                        data = "".join(fragments).encode("utf-8")
                        compressed.write(data)
                        digest.update(data)
                        size += len(data)
                raw.flush()
                os.fsync(raw.fileno())
                name = digest.hexdigest() + ".json.gz"
                destination = self.world_dir / name
                if destination.exists():
                    temporary.unlink()
                else:
                    temporary.replace(destination)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        record = {"world_file": str(destination.relative_to(self.output)),
                  "uncompressed_sha256": digest.hexdigest(), "uncompressed_bytes": size}
        self.seen_worlds[id(world)] = (world, record)
        return record

    def archive_worlds(self, *, trigger: str) -> None:
        modules = dict(sys.modules)
        for name, module in modules.items():
            if name in {"support.worlds", "tests.support.worlds"}:
                cache_names = ("_cache", "_legacy_cache")
            elif name.rsplit(".", 1)[-1] == "test_civilization_geography_validation":
                cache_names = ("_ONE_OFF_WORLDS",)
            else:
                continue
            for cache_name in cache_names:
                cache = getattr(module, cache_name, None)
                if not isinstance(cache, dict):
                    continue
                for key, world in tuple(cache.items()):
                    identity = (name, cache_name, repr(key), id(world))
                    if identity in self.seen_aliases:
                        continue
                    try:
                        snapshot = self._write_world(world)
                        if cache_name == "_cache":
                            recipe = {"function": "canonical_config", "key": key}
                            config = module.canonical_config(key)
                        elif cache_name == "_legacy_cache":
                            recipe = {"function": "build_legacy_config", "overrides": module.LEGACY_CANONICAL[key]}
                            config = module.build_legacy_config(**recipe["overrides"])
                        else:
                            cell_count, seed = key
                            recipe = {"function": "build_config", "overrides": {"mesh.cell_count": cell_count, "run.seed": seed}}
                            config = module.worlds.build_config(**recipe["overrides"])
                        config_data = config.model_dump(mode="json")
                        alias = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
                        config_path = self.config_dir / (alias + ".json")
                        _write_json(config_path, config_data)
                        source = getattr(module, "__file__", None)
                        record = {"utc": _now(), "trigger": trigger, "module": name,
                                  "cache": cache_name, "key": key, "object_id": id(world),
                                  **snapshot, "config_file": str(config_path.relative_to(self.output)),
                                  "config_recipe": recipe,
                                  "config_provenance": "reconstructed_at_archive_time_with_existing_fixture_builder",
                                  "cache_module_source_sha256": _sha256(Path(source)) if source and Path(source).is_file() else None}
                        self.archives.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                        self.archives.flush()
                        os.fsync(self.archives.fileno())
                        self.event("world_archived", **record)
                        self.seen_aliases.add(identity)
                    except Exception as exc:
                        self.archive_errors += 1
                        self.event("archive_error", durable=True, module=name, cache=cache_name,
                                   key=repr(key), error=f"{type(exc).__name__}: {exc}")
                        # Avoid retrying the same failed object every subtest;
                        # errors remain visible and make a green run nonzero.
                        self.seen_aliases.add(identity)

    def close(self) -> None:
        for stream in (self.events, self.failures, self.completed, self.archives):
            stream.close()


def main(argv: list[str] | None = None) -> int:
    # Match `python -m pytest`: direct script execution otherwise puts only
    # scripts/research on sys.path and breaks repository-local test imports.
    working_directory = str(Path.cwd())
    if working_directory not in sys.path:
        sys.path.insert(0, working_directory)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True, help="New or empty directory; existing run files are never overwritten")
    parser.add_argument("--traceback-interval", type=float, default=300.0,
                        help="Repeat all-thread traceback diagnostics every N seconds without aborting; 0 disables")
    parser.add_argument("--archive-failure-worlds", action="store_true",
                        help="Retain world-shaped test locals on ordinary call failure; snapshots may contain test mutations")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Arguments after -- are passed to pytest")
    args = parser.parse_args(argv)
    if not math.isfinite(args.traceback_interval) or args.traceback_interval < 0:
        parser.error("--traceback-interval must be finite and nonnegative")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error("--output-dir must be empty; use a new directory to retain previous evidence")
    requested = args.pytest_args[1:] if args.pytest_args[:1] == ["--"] else args.pytest_args
    # Pytest's faulthandler exception hooks cancel the process-wide timer; own
    # that diagnostic here so a failed call cannot disable teardown diagnostics.
    effective = ["-p", "no:faulthandler", *requested]
    _write_json(output / "run.json", {
        "started_utc": _now(), "pid": os.getpid(), "cwd": str(Path.cwd()),
        "executable": sys.executable, "python_version": sys.version,
        "runner_argv": sys.argv if argv is None else argv,
        "pytest_version": pytest.__version__, "requested_pytest_args": requested,
        "effective_pytest_args": effective, "traceback_interval_seconds": args.traceback_interval,
        "cache_policy": "snapshot_existing_serial_process_caches_never_generate_mutate_or_restore",
        "archive_failure_worlds": args.archive_failure_worlds,
        **_provenance(),
    })
    recorder = SweepRecorder(output, archive_failure_worlds=args.archive_failure_worlds)
    trace = (output / "tracebacks.log").open("w", encoding="utf-8")
    exit_code = 2
    try:
        # Replace the disabled builtin plugin's fatal-fault diagnostics as well
        # as its timer, retaining traceback evidence if the process crashes.
        faulthandler.enable(file=trace, all_threads=True)
        if args.traceback_interval:
            faulthandler.dump_traceback_later(args.traceback_interval, repeat=True, file=trace, exit=False)
        recorder.event("runner_start", durable=True)
        exit_code = int(pytest.main(effective, plugins=[recorder]))
    except BaseException as exc:
        recorder.event("runner_exception", durable=True, error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        recorder.archive_worlds(trigger="runner_finally")
        if exit_code == 0 and recorder.archive_errors:
            exit_code = 2
        recorder.event("runner_exit", durable=True, exit_status=exit_code,
                       archive_error_count=recorder.archive_errors)
        if args.traceback_interval:
            faulthandler.cancel_dump_traceback_later()
        faulthandler.disable()
        trace.close()
        recorder.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
