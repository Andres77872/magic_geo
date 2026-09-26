"""Safe background execution for the local web workbench.

The workbench exposes the existing CLI workflows without accepting arbitrary
shell commands.  Each operation has a fixed command, a typed argument schema,
and explicit input/output path policy. Inputs and outputs are confined to the
configured runtime roots, which may live outside the source checkout.

This module deliberately has no FastAPI dependency.  The HTTP layer and the
browser consume the same operation catalog, while tests can exercise command
construction and job state directly.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

import yaml
from yaml.events import AliasEvent, CollectionEndEvent, CollectionStartEvent

from .paths import RuntimePaths
from .config_store import ConfigStore


JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
FileFingerprint = tuple[int, int, int, int]
CachePublisher = Callable[[Path, Path], Path]
_REPORTING_OPERATIONS = {
    "validate-geo",
    "validate-geo-suite",
    "calibrate",
    "calibrate-ensemble",
}
_MAX_WEB_MANIFEST_BYTES = 8 * 1024 * 1024
_MAX_WEB_MANIFEST_EVENTS = 20_000
_MAX_WEB_MANIFEST_DEPTH = 64
_MAX_WEB_MANIFEST_ALIASES = 64
_PROGRESS_PREFIX = "MAGIC_GEO_PROGRESS "


def _field(
    name: str,
    label: str,
    kind: str,
    *,
    flag: str | None = None,
    required: bool = False,
    default: Any = None,
    help: str = "",
    choices: list[str] | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    path_role: str | None = None,
    negative_flag: str | None = None,
    cli: bool = True,
    workspace_relative: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "label": label,
        "kind": kind,
        "flag": flag,
        "required": required,
        "default": default,
        "help": help,
        "cli": cli,
        "workspace_relative": workspace_relative,
    }
    if choices is not None:
        result["choices"] = choices
    if minimum is not None:
        result["minimum"] = minimum
    if maximum is not None:
        result["maximum"] = maximum
    if path_role is not None:
        result["path_role"] = path_role
    if negative_flag is not None:
        result["negative_flag"] = negative_flag
    return result


_WORLD_INPUT = lambda: _field(
    "world",
    "World file",
    "path",
    flag="--world",
    required=True,
    help="A saved world (.json or .mgeo) produced by Generate world.",
    path_role="input",
)


# This catalog mirrors every executable CLI workflow.  ``init-config`` and
# ``backend`` have richer first-class HTTP endpoints, and ``serve`` is the
# currently running workbench, so they are represented in operation_catalog()
# as equivalents instead of recursively starting another server.
_OPERATIONS: dict[str, dict[str, Any]] = {
    "generate": {
        "title": "Generate world",
        "description": "Simulate a planet from a YAML configuration and save it as JSON or MessagePack. With Prepare browser map on, its layers and mesh are exported so the Map and Data views open it automatically. Progress is reported stage by stage.",
        "command": "generate",
        "fields": [
            _field("config", "YAML config", "path", flag="--config", default="runs/configs/world.yaml", path_role="input", workspace_relative=True, help="World definition to simulate. Use Configure to create or edit one."),
            _field("output", "World file", "path", flag="--output", default="runs/world.json", path_role="output", help="Where to save the generated world (.json, or .mgeo for compact MessagePack)."),
            _field("summary", "Markdown summary", "path", flag="--summary", path_role="output", help="Optional Markdown report of the world's key statistics."),
            _field("cells_csv", "Cells CSV", "path", flag="--cells-csv", path_role="output", help="Optional flat table with one row per cell, for spreadsheets."),
            _field("cells", "Cell count override", "integer", flag="--cells", minimum=128, help="Overrides mesh.cell_count for a quick, coarse run (minimum 128). Leave blank to use the configuration."),
            _field("geo_only", "Natural geography only", "boolean", flag="--geo-only", default=False, help="Stop after natural geography: skip settlements, routes, borders, cultures and history."),
            _field("world_format", "World serialization", "choice", flag="--format", default="auto", choices=["auto", "json", "mgeo"], help="Auto picks from the file extension; choose json or mgeo to force a format."),
            _field("open_in_web", "Prepare browser map", "boolean", default=True, cli=False, help="Export layers and mesh after generation and open the new world in this workbench."),
            _field("debug_output", "Browser map folder", "path", default="runs/debug", path_role="output", cli=False, help="Folder for the browser map (the debug cache read by Map and Data)."),
            _field("debug_vtu", "Include ParaView VTU", "boolean", default=False, cli=False, help="Also write ParaView VTU stage files (larger and slower)."),
        ],
    },
    "validate": {
        "title": "Validate world",
        "description": "Run every structural, conservation and replay check on a saved world. The job fails if any contract is broken.",
        "command": "validate",
        "fields": [_WORLD_INPUT()],
    },
    "validate-geo": {
        "title": "Validate natural geography",
        "description": "Check natural-system contracts and realism gates for terrain, climate, water, ice, soils and ecology.",
        "command": "validate-geo",
        "fields": [
            _WORLD_INPUT(),
            _field("profile", "Profile", "choice", flag="--profile", default="generic", choices=["generic", "earthlike"], help="generic applies universal physical checks; earthlike also compares against Earth reference ranges."),
            _field("output", "Report JSON", "path", flag="--output", path_role="output", help="Optional JSON report for scripts and CI."),
            _field("fail_on_warnings", "Fail on warnings", "boolean", flag="--fail-on-warnings", default=False, help="Treat evidence-backed warnings as failures."),
        ],
    },
    "validate-geo-suite": {
        "title": "Run geo validation suite",
        "description": "Generate every scenario in a matrix from one base configuration and check their paired responses.",
        "command": "validate-geo-suite",
        "fields": [
            _field("config", "Base YAML config", "path", flag="--config", default="runs/configs/world.yaml", path_role="input", workspace_relative=True),
            _field("matrix", "Scenario matrix", "path", flag="--matrix", required=True, path_role="input", help="Project-local geo-validation matrix; installed packages do not assume the repository's example matrix is present."),
            _field("output", "Report JSON", "path", flag="--output", default="runs/geo_validation.json", path_role="output"),
            _field("summary", "Markdown summary", "path", flag="--summary", path_role="output"),
        ],
    },
    "calibrate": {
        "title": "Calibrate world",
        "description": "Compare one saved world with target ranges derived from external data and report which metrics fall inside.",
        "command": "calibrate",
        "fields": [
            _WORLD_INPUT(),
            _field("targets", "Target bundle", "path", flag="--targets", required=True, path_role="input"),
            _field("output", "Report JSON", "path", flag="--output", default="runs/calibration.json", path_role="output"),
            _field("summary", "Markdown summary", "path", flag="--summary", path_role="output"),
            _field("require_all_metrics", "Require every metric", "boolean", flag="--require-all-metrics", default=False),
            _field("require_all_passed", "Require every target to pass", "boolean", flag="--require-all-passed", default=False),
        ],
    },
    "calibrate-ensemble": {
        "title": "Calibrate ensemble",
        "description": "Generate an explicit set of seeds and resolutions, then evaluate the whole ensemble against target bundles.",
        "command": "calibrate-ensemble",
        "fields": [
            _field("config", "Base YAML config", "path", flag="--config", required=True, path_role="input"),
            _field("matrix", "Ensemble manifest", "path", flag="--matrix", required=True, path_role="input"),
            _field("targets", "Target bundles", "path_list", flag="--targets", required=True, path_role="input", help="One path per line."),
            _field("output", "Report JSON", "path", flag="--output", default="runs/calibration_ensemble.json", path_role="output"),
            _field("summary", "Markdown summary", "path", flag="--summary", path_role="output"),
            _field("require_all_metrics", "Require every metric", "boolean", flag="--require-all-metrics", default=False),
            _field("require_all_passed", "Require every target to pass", "boolean", flag="--require-all-passed", default=False),
        ],
    },
    "derive-targets": {
        "title": "Derive calibration targets",
        "description": "Build calibration target ranges from a local manifest of source datasets.",
        "command": "derive-targets",
        "fields": [
            _field("sources", "Source manifest", "path", flag="--sources", required=True, path_role="input"),
            _field("output", "Targets JSON", "path", flag="--output", default="runs/calibration_targets.json", path_role="output"),
            _field("summary", "Markdown summary", "path", flag="--summary", path_role="output"),
        ],
    },
    "render": {
        "title": "Render SVG map",
        "description": "Draw a downloadable vector map with terrain, water, borders, and optional labels and contours.",
        "command": "render",
        "fields": [
            _WORLD_INPUT(),
            _field("output", "SVG output", "path", flag="--output", default="runs/world.svg", path_role="output"),
            _field("width", "Width", "integer", flag="--width", default=1600, minimum=320, maximum=6400),
            _field("height", "Height", "integer", flag="--height", default=800, minimum=160, maximum=3200),
            _field("projection", "Projection", "choice", flag="--projection", default="equirectangular", choices=["equirectangular", "mollweide", "orthographic"]),
            _field("labels", "Settlement labels", "boolean", flag="--labels", negative_flag="--no-labels", default=False),
            _field("max_cells", "Maximum cells", "integer", flag="--max-cells", minimum=128),
            _field("contours", "Elevation contours", "boolean", flag="--contours", negative_flag="--no-contours", default=True),
            _field("contour_interval", "Contour interval (m)", "number", flag="--contour-interval", default=500.0, minimum=50.0),
        ],
    },
    "render-raster": {
        "title": "Render raster map",
        "description": "Draw a shaded raster map (PPM) without extra dependencies.",
        "command": "render-raster",
        "fields": [
            _WORLD_INPUT(),
            _field("output", "PPM output", "path", flag="--output", default="runs/world.ppm", path_role="output"),
            _field("width", "Width", "integer", flag="--width", default=1600, minimum=320, maximum=6400),
            _field("height", "Height", "integer", flag="--height", default=800, minimum=160, maximum=3200),
            _field("projection", "Projection", "choice", flag="--projection", default="equirectangular", choices=["equirectangular", "mollweide", "orthographic"]),
            _field("max_cells", "Maximum cells", "integer", flag="--max-cells", minimum=128),
            _field("texture", "Terrain texture", "boolean", flag="--texture", negative_flag="--no-texture", default=True),
        ],
    },
    "export-debug": {
        "title": "Prepare browser map",
        "description": "Export a saved world's layers, tables and mesh so Map and Data can open it, with optional ParaView VTU stages. Use this to reopen a world generated without its browser map.",
        "command": "export-debug",
        "fields": [
            _WORLD_INPUT(),
            _field("output", "Cache directory", "path", flag="--output", default="runs/debug", path_role="output"),
            _field("vtu", "Include ParaView VTU", "boolean", flag="--vtu", negative_flag="--no-vtu", default=True),
            _field("elevation_exaggeration", "VTU elevation exaggeration", "number", flag="--elevation-exaggeration", default=30.0, minimum=1.0),
        ],
    },
    "export-rerun": {
        "title": "Export Rerun recording",
        "description": "Write a Rerun (.rrd) recording you can scrub stage by stage in the Rerun viewer.",
        "command": "export-rerun",
        "optional_dependency": "rerun",
        "fields": [
            _WORLD_INPUT(),
            _field("output", "Rerun output", "path", flag="--output", default="runs/world.rrd", path_role="output"),
        ],
    },
}


_EQUIVALENT_OPERATIONS: list[dict[str, Any]] = [
    {
        "id": "init-config",
        "title": "Create YAML config",
        "description": "Provided by the Configure view, the New world dialog and /api/config endpoints.",
        "equivalent_view": "config",
        "available": True,
    },
    {
        "id": "backend",
        "title": "Inspect compute backend",
        "description": "Provided by /api/backend and the API view.",
        "equivalent_view": "api",
        "available": True,
    },
    {
        "id": "export-debug-map",
        "title": "Export debug map reference",
        "description": "Provided directly by the Map view's PNG and Prompt export buttons.",
        "equivalent_view": "map",
        "available": True,
    },
    {
        "id": "serve",
        "title": "Serve web workbench",
        "description": "This process is the active serve operation.",
        "equivalent_view": "current",
        "available": True,
    },
]


def _operation_default(paths: RuntimePaths, operation: str, spec: dict[str, Any]) -> Any:
    value = spec.get("default")
    if spec["name"] == "config" and value:
        selected = ConfigStore(paths).default()
        return paths.display(selected) if selected else (
            paths.display(paths.saved_config_dir / "world.yaml") if value else value
        )
    if spec.get("path_role") == "output" and value:
        category = "report" if operation in _REPORTING_OPERATIONS or operation == "derive-targets" else (
            "export" if operation.startswith("render") or operation == "export-rerun" else "output"
        )
        return paths.display(paths.rebase_default(value, category=category))
    return value


def operation_catalog(
    project_root: Path | None = None,
    workspace: Path | None = None,
    *, paths: RuntimePaths | None = None,
) -> dict[str, Any]:
    """Return browser-safe metadata for every CLI feature.

    When a non-default workspace is supplied, conventional ``runs/...`` output
    defaults are rebased below it so the displayed form and server policy agree.
    """

    if paths is None and project_root is not None and workspace is not None:
        paths = RuntimePaths.resolve(project_root, workspace)
    operations: list[dict[str, Any]] = []
    for operation_id, spec in _OPERATIONS.items():
        item = copy.deepcopy(spec)
        dependency = item.pop("optional_dependency", None)
        item["id"] = operation_id
        item["available"] = dependency is None or importlib.util.find_spec(dependency) is not None
        if dependency is not None:
            item["dependency"] = dependency
        for field_spec in item["fields"]:
            if paths is not None:
                field_spec["default"] = _operation_default(paths, operation_id, field_spec)
            # UI grouping is part of the shared catalog, not a second schema.
            name = field_spec["name"]
            field_spec["group"] = "essentials" if name in {
                "config", "world", "output", "matrix", "targets", "sources", "cells", "geo_only", "open_in_web"
            } else "advanced"
            if operation_id == "generate" and name in {"debug_output", "debug_vtu"}:
                field_spec["depends_on"] = "open_in_web"
        operations.append(item)
    return {
        "operations": operations,
        "equivalents": copy.deepcopy(_EQUIVALENT_OPERATIONS),
        "coverage": {
            "cli_command_count": len(operations) + len(_EQUIVALENT_OPERATIONS),
            "background_operation_count": len(operations),
            "equivalent_view_count": len(_EQUIVALENT_OPERATIONS),
        },
    }


class JobInputError(ValueError):
    """Raised when a requested job is not in the fixed safe operation schema."""


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


@dataclass
class WebJob:
    id: str
    operation: str
    arguments: dict[str, Any]
    command: list[str]
    status: JobStatus = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    log: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    cache_dir: str | None = None
    map_superseded: bool = False
    progress: dict[str, Any] = field(default_factory=lambda: {
        "phase": "queued", "label": "Waiting in queue",
        "detail": "Starts when the current operation finishes.",
        "current": None, "total": None,
    })
    last_activity_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: str | None = None
    _started_monotonic: float | None = field(default=None, repr=False)
    _finished_monotonic: float | None = field(default=None, repr=False)
    _phase_started_monotonic: float = field(default_factory=time.monotonic, repr=False)
    _activity_monotonic: float = field(default_factory=time.monotonic, repr=False)
    _last_output: str = field(default="", repr=False)
    _process: subprocess.Popen[str] | None = field(default=None, repr=False)
    _stopping_process: subprocess.Popen[str] | None = field(default=None, repr=False)
    _process_active: bool = field(default=False, repr=False)
    _stop_timer: threading.Timer | None = field(default=None, repr=False)
    _cancel_requested: bool = field(default=False, repr=False)
    _publishing: bool = field(default=False, repr=False)
    _finalizing: bool = field(default=False, repr=False)
    _artifact_before: dict[int, FileFingerprint | None] = field(
        default_factory=dict, repr=False
    )
    _artifact_paths: dict[int, Path] = field(default_factory=dict, repr=False)
    _artifact_fingerprints: dict[int, FileFingerprint] = field(
        default_factory=dict, repr=False
    )
    _artifact_sources: dict[int, FileFingerprint] = field(default_factory=dict, repr=False)

    def telemetry(self) -> dict[str, Any]:
        """Report measured durations; silence is never invented progress."""
        now = self._finished_monotonic if self._finished_monotonic is not None else time.monotonic()
        progress = copy.deepcopy(self.progress)
        progress.setdefault("updated_at", self.created_at)
        world_index = next((
            index for index, artifact in enumerate(self.artifacts)
            if self.operation == "generate" and artifact.get("name") == "output" and artifact.get("available")
        ), None)
        world_path = self._artifact_paths.get(world_index) if world_index is not None else None
        return {
            "progress": progress,
            "elapsed_seconds": round(max(0.0, now - self._started_monotonic), 1) if self._started_monotonic is not None else 0.0,
            "phase_elapsed_seconds": round(max(0.0, now - self._phase_started_monotonic), 1),
            "last_activity_at": self.last_activity_at,
            "seconds_since_activity": round(max(0.0, now - self._activity_monotonic), 1),
            "queue_position": None,
            "cancellable": self.status in {"queued", "running"} and not (self._cancel_requested or self._publishing or self._finalizing),
            "cancel_requested": self._cancel_requested,
            "error": self.error,
            "world_available": world_index is not None,
            "world_path": str(world_path) if world_path is not None else None,
            "map_superseded": self.map_superseded,
        }

    def public(self) -> dict[str, Any]:
        return {
            **self.telemetry(),
            "id": self.id,
            "operation": self.operation,
            "arguments": copy.deepcopy(self.arguments),
            "command": list(self.command),
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "log": self.log,
            "artifacts": copy.deepcopy(self.artifacts),
            "cache_dir": self.cache_dir,
        }

    def summary(self) -> dict[str, Any]:
        """Lightweight list representation; logs/arguments stay on detail GET."""

        return {
            **self.telemetry(),
            "id": self.id,
            "operation": self.operation,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "artifacts": copy.deepcopy(self.artifacts),
            "cache_dir": self.cache_dir,
        }


class JobManager:
    """Single-worker process-isolated job queue for the local browser UI."""

    def __init__(
        self,
        project_root: Path,
        workspace: Path,
        *,
        paths: RuntimePaths | None = None,
        on_complete: Callable[[WebJob], None] | None = None,
        publish_cache: CachePublisher | None = None,
        max_log_bytes: int = 2_000_000,
        max_jobs: int = 100,
    ) -> None:
        self.paths = paths or RuntimePaths.resolve(project_root, workspace)
        self.project_root = self.paths.project
        self.workspace = self.paths.workspace
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._internal_root = self.paths.state_dir
        if self._internal_root.is_symlink():
            raise ValueError("web internal directory must not be a symbolic link")
        self._internal_root.mkdir(parents=True, exist_ok=True)
        self._artifact_root = self._internal_root / "artifacts"
        if self._artifact_root.is_symlink():
            raise ValueError("web artifact directory must not be a symbolic link")
        self._artifact_root.mkdir(exist_ok=True)
        self._artifact_root = self._artifact_root.resolve()
        if not _is_relative_to(self._artifact_root, self._internal_root):
            raise ValueError("web artifact directory must stay inside the internal directory")
        self._jobs: dict[str, WebJob] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="magic-geo-web")
        self._on_complete = on_complete
        self._publish_cache = publish_cache
        self._max_log_bytes = max_log_bytes
        self._max_jobs = max_jobs
        self._closed = False

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            now = datetime.now(timezone.utc).isoformat()
            queued = [job for job in self._jobs.values() if job.status == "queued"]
            for job in queued:
                job._cancel_requested = True
                job.status = "cancelled"
                job.finished_at = now
                self._set_progress(job, "cancelled", "Cancelled", "Removed from the queue before starting.")
                job._finished_monotonic = time.monotonic()
            running = [job for job in self._jobs.values() if job.status == "running"]
        for job in running:
            self.cancel(job.id)
        # Cancellation escalates from TERM to KILL after five seconds. Waiting
        # here guarantees no child can keep writing after FastAPI teardown.
        self._executor.shutdown(wait=True, cancel_futures=True)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
            return [self._public(job, summary=True) for job in jobs]

    def _public(self, job: WebJob, *, summary: bool = False) -> dict[str, Any]:
        result = job.summary() if summary else job.public()
        if job.status == "queued":
            queued = [candidate.id for candidate in self._jobs.values() if candidate.status == "queued"]
            result["queue_position"] = queued.index(job.id) + 1
        return result

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return self._public(job)

    def submit(self, operation: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            if self._closed:
                raise JobInputError("web job manager is closed")
        if operation not in _OPERATIONS:
            raise JobInputError(f"unknown operation: {operation}")
        normalized, command, artifacts = self._build_command(operation, arguments or {})
        job = WebJob(
            id=uuid.uuid4().hex[:12],
            operation=operation,
            arguments=normalized,
            command=command,
            artifacts=artifacts,
        )
        with self._lock:
            if self._closed:
                raise JobInputError("web job manager is closed")
            active = [
                candidate
                for candidate in self._jobs.values()
                if candidate.status in {"queued", "running"}
            ]
            for candidate in active:
                if candidate.operation == operation and candidate.arguments == normalized:
                    return self._public(candidate)
                conflicts = {
                    new_artifact["path"]
                    for new_artifact in artifacts
                    for active_artifact in candidate.artifacts
                    if self._artifacts_conflict(new_artifact, active_artifact)
                }
                if conflicts:
                    raise JobInputError(
                        "output already targeted by an active job: "
                        + ", ".join(sorted(conflicts))
                    )
            if len(self._jobs) >= self._max_jobs:
                # Recovery/validation jobs can read immutable world snapshots.
                # Keep their source job alive until these readers finish.
                retained_sources: set[str] = set()
                for reader in [*active, job]:
                    for value in reader.arguments.values():
                        values = value if isinstance(value, list) else [value]
                        for item in values:
                            if not isinstance(item, str):
                                continue
                            path = Path(item)
                            if _is_relative_to(path, self._artifact_root):
                                parts = path.relative_to(self._artifact_root).parts
                                if parts:
                                    retained_sources.add(parts[0])
                terminal = [
                    candidate
                    for candidate in self._jobs.values()
                    if candidate.status in {"succeeded", "failed", "cancelled"}
                    and candidate.id not in retained_sources
                ]
                terminal.sort(key=lambda candidate: candidate.created_at)
                while len(self._jobs) >= self._max_jobs and terminal:
                    removed = terminal.pop(0)
                    self._jobs.pop(removed.id, None)
                    shutil.rmtree(self._artifact_root / removed.id, ignore_errors=True)
            if len(self._jobs) >= self._max_jobs:
                raise JobInputError(
                    f"job queue is full ({self._max_jobs}); wait for or cancel existing work"
                )
            self._jobs[job.id] = job
            # Submit before releasing the lock so close() cannot shut down the
            # executor between recording and scheduling the job.
            try:
                self._executor.submit(self._run, job)
            except RuntimeError as exc:
                self._jobs.pop(job.id, None)
                raise JobInputError("web job executor is unavailable") from exc
            return self._public(job)

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status in {"succeeded", "failed", "cancelled"}:
                return self._public(job)
            # Cache publication and terminal artifact snapshotting are commit
            # phases. Once either begins, cancellation cannot be made truthful
            # without rolling back a completed publication/snapshot.
            if job._publishing or job._finalizing:
                return self._public(job)
            job._cancel_requested = True
            process = job._process
            if job.status == "queued":
                job.status = "cancelled"
                job.finished_at = datetime.now(timezone.utc).isoformat()
                self._set_progress(job, "cancelled", "Cancelled", "Removed from the queue before starting.")
                job._finished_monotonic = time.monotonic()
            else:
                self._set_progress(job, "cancelling", "Stopping operation", "Waiting for the process and its child processes to stop.")
        if process is not None:
            self._request_process_stop(job, process)
        return self.get(job_id)

    def artifact_path(self, job_id: str, artifact_index: int) -> Path:
        if artifact_index < 0:
            raise KeyError(f"{job_id}:{artifact_index}")
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            try:
                artifact = job.artifacts[artifact_index]
                relative = artifact["path"]
            except (IndexError, KeyError) as exc:
                raise KeyError(f"{job_id}:{artifact_index}") from exc
            if not artifact.get("available", False):
                raise FileNotFoundError(relative)
            path = job._artifact_paths.get(artifact_index)
            expected = job._artifact_fingerprints.get(artifact_index)
        if path is None or expected is None:
            raise FileNotFoundError(path)
        resolved = path.resolve()
        if not _is_relative_to(resolved, self._artifact_root):
            raise FileNotFoundError(resolved)
        if self._file_fingerprint(resolved) != expected:
            raise FileNotFoundError(resolved)
        path = resolved
        return path

    def _resolve_path(self, value: str, role: str) -> Path:
        raw = Path(value).expanduser()
        try:
            path = (raw if raw.is_absolute() else self.project_root / raw).resolve()
        except (OSError, RuntimeError) as exc:
            raise JobInputError(f"unable to resolve {role} path {value!r}: {exc}") from exc
        root = self.project_root if role == "input" else self.workspace
        if role == "output" and _is_relative_to(path, self._internal_root):
            raise JobInputError("output path uses the reserved web-internal directory")
        if not (self.paths.allows_input(path) if role == "input" else self.paths.allows_output(path)):
            noun = "input" if role == "input" else "output"
            raise JobInputError(f"{noun} path must stay inside {root}: {value}")
        if role == "input" and not path.is_file():
            raise JobInputError(f"input path must name an existing regular file: {value}")
        if role == "output":
            if path in self.paths.output_roots and path != self.paths.debug_dir:
                raise JobInputError("output path must not replace the web workspace")
            if _is_relative_to(path, self._internal_root):
                raise JobInputError("output path uses the reserved web-internal directory")
        return path

    def _resolve_indirect_input(self, value: Any, base: Path, context: str) -> Path:
        """Resolve a path declared inside a web-supplied manifest.

        CLI workflows intentionally support absolute paths. The browser is a
        narrower trusted-local surface: every direct *and transitive* input is
        confined to the selected project before a subprocess can read it.
        """

        if not isinstance(value, str) or not value.strip():
            raise JobInputError(f"{context} must be a non-empty path string")
        raw = Path(value)
        try:
            path = (raw if raw.is_absolute() else base / raw).resolve()
        except (OSError, RuntimeError) as exc:
            raise JobInputError(f"unable to resolve {context} {value!r}: {exc}") from exc
        if not self.paths.allows_input(path):
            raise JobInputError(
                f"indirect input path must stay inside {self.project_root}: "
                f"{context}={value}"
            )
        if not path.is_file():
            raise JobInputError(f"{context} must name an existing regular file: {value}")
        return path

    @staticmethod
    def _read_manifest_text(path: Path, context: str) -> str:
        try:
            size = path.stat().st_size
            if size > _MAX_WEB_MANIFEST_BYTES:
                raise JobInputError(
                    f"{context} exceeds the {_MAX_WEB_MANIFEST_BYTES}-byte web limit"
                )
            return path.read_text(encoding="utf-8")
        except JobInputError:
            raise
        except (OSError, UnicodeError) as exc:
            raise JobInputError(f"unable to read {context}: {path}: {exc}") from exc

    def _load_json_manifest(self, path: Path, context: str) -> Any:
        try:
            return json.loads(self._read_manifest_text(path, context))
        except (json.JSONDecodeError, RecursionError, MemoryError, ValueError) as exc:
            raise JobInputError(f"invalid {context}: {path}: {exc}") from exc

    def _load_yaml_manifest(self, path: Path, context: str) -> Any:
        text = self._read_manifest_text(path, context)
        depth = 0
        events = 0
        aliases = 0
        try:
            for event in yaml.parse(text, Loader=yaml.SafeLoader):
                events += 1
                if events > _MAX_WEB_MANIFEST_EVENTS:
                    raise JobInputError(
                        f"{context} exceeds the {_MAX_WEB_MANIFEST_EVENTS}-event web limit"
                    )
                if isinstance(event, CollectionStartEvent):
                    depth += 1
                    if depth > _MAX_WEB_MANIFEST_DEPTH:
                        raise JobInputError(
                            f"{context} exceeds the {_MAX_WEB_MANIFEST_DEPTH}-level web limit"
                        )
                elif isinstance(event, CollectionEndEvent):
                    depth = max(0, depth - 1)
                elif isinstance(event, AliasEvent):
                    aliases += 1
                    if aliases > _MAX_WEB_MANIFEST_ALIASES:
                        raise JobInputError(
                            f"{context} exceeds the {_MAX_WEB_MANIFEST_ALIASES}-alias web limit"
                        )
            return yaml.safe_load(text)
        except JobInputError:
            raise
        except (
            yaml.YAMLError,
            RecursionError,
            MemoryError,
            ValueError,
            OverflowError,
        ) as exc:
            raise JobInputError(f"invalid {context}: {path}: {exc}") from exc

    def _derive_target_inputs(self, manifest_path: Path) -> list[Path]:
        payload = self._load_json_manifest(manifest_path, "calibration source manifest")
        sources = payload.get("sources") if isinstance(payload, dict) else payload
        if not isinstance(sources, list):
            raise JobInputError(
                "calibration source manifest must be an array or an object with a sources array"
            )
        discovered: list[Path] = []
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                raise JobInputError(f"calibration sources[{index}] must be an object")
            primary = self._resolve_indirect_input(
                source.get("path"),
                manifest_path.parent,
                f"calibration sources[{index}].path",
            )
            discovered.append(primary)
            for key in ("dbf_path", "prj_path"):
                if key in source:
                    discovered.append(
                        self._resolve_indirect_input(
                            source[key],
                            manifest_path.parent,
                            f"calibration sources[{index}].{key}",
                        )
                    )

            source_format = str(source.get("format", "")).strip().lower()
            if source_format not in {
                "hydrobasins_archive_catalog",
                "hydrobasins_catalog",
            }:
                continue
            catalog = self._load_json_manifest(primary, "HydroBASINS archive catalog")
            archives = catalog.get("archives") if isinstance(catalog, dict) else None
            if not isinstance(archives, list) or not archives:
                raise JobInputError(
                    "HydroBASINS archive catalog must contain a non-empty archives array"
                )
            for archive_index, archive in enumerate(archives):
                if not isinstance(archive, dict):
                    raise JobInputError(
                        f"HydroBASINS archives[{archive_index}] must be an object"
                    )
                discovered.append(
                    self._resolve_indirect_input(
                        archive.get("path"),
                        primary.parent,
                        f"HydroBASINS archives[{archive_index}].path",
                    )
                )
        return discovered

    def _geo_suite_inputs(self, matrix_path: Path) -> list[Path]:
        payload = self._load_yaml_manifest(matrix_path, "geo-validation matrix")
        scenarios = payload.get("scenarios") if isinstance(payload, dict) else None
        if not isinstance(scenarios, list):
            raise JobInputError("geo-validation matrix must contain a scenarios array")
        discovered: list[Path] = []
        for scenario_index, scenario in enumerate(scenarios):
            if not isinstance(scenario, dict):
                raise JobInputError(
                    f"geo-validation scenarios[{scenario_index}] must be an object"
                )
            empirical = scenario.get("empirical_calibration")
            if empirical is None:
                continue
            if not isinstance(empirical, dict):
                raise JobInputError(
                    f"geo-validation scenarios[{scenario_index}].empirical_calibration "
                    "must be an object"
                )
            bundle = self._resolve_indirect_input(
                empirical.get("target_bundle"),
                matrix_path.parent,
                f"geo-validation scenarios[{scenario_index}].empirical_calibration.target_bundle",
            )
            discovered.append(bundle)
            bundle_payload = self._load_json_manifest(bundle, "empirical target bundle")
            derivation = (
                bundle_payload.get("derivation")
                if isinstance(bundle_payload, dict)
                else None
            )
            if derivation is None:
                continue
            if not isinstance(derivation, dict):
                raise JobInputError("empirical target bundle derivation must be an object")
            for field in (
                "source_manifests",
                "supplemental_target_derivations",
            ):
                records = derivation.get(field)
                if records is None:
                    continue
                if not isinstance(records, list):
                    raise JobInputError(
                        f"empirical target bundle derivation.{field} must be an array"
                    )
                for record_index, record in enumerate(records):
                    if not isinstance(record, dict):
                        raise JobInputError(
                            f"empirical target bundle derivation.{field}[{record_index}] "
                            "must be an object"
                        )
                    discovered.append(
                        self._resolve_indirect_input(
                            record.get("path"),
                            bundle.parent,
                            f"empirical target bundle derivation.{field}"
                            f"[{record_index}].path",
                        )
                    )
        return discovered

    def _indirect_input_paths(
        self, operation: str, normalized: dict[str, Any]
    ) -> list[Path]:
        if operation == "derive-targets" and "sources" in normalized:
            return self._derive_target_inputs(Path(normalized["sources"]))
        if operation == "validate-geo-suite" and "matrix" in normalized:
            return self._geo_suite_inputs(Path(normalized["matrix"]))
        return []

    def _normalize_scalar(self, field_spec: dict[str, Any], value: Any) -> Any:
        kind = field_spec["kind"]
        name = field_spec["name"]
        if kind == "boolean":
            if not isinstance(value, bool):
                raise JobInputError(f"{name} must be true or false")
            return value
        if kind == "integer":
            if isinstance(value, bool):
                raise JobInputError(f"{name} must be an integer")
            if isinstance(value, int):
                converted = value
            elif isinstance(value, float):
                if not math.isfinite(value) or not value.is_integer():
                    raise JobInputError(f"{name} must be an integer")
                converted = int(value)
            elif isinstance(value, str):
                try:
                    converted = int(value, 10)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise JobInputError(f"{name} must be an integer") from exc
            else:
                raise JobInputError(f"{name} must be an integer")
            if not -(2**63) <= converted <= 2**63 - 1:
                raise JobInputError(f"{name} is outside the supported 64-bit range")
            value = converted
        elif kind == "number":
            if isinstance(value, bool):
                raise JobInputError(f"{name} must be a number")
            try:
                value = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise JobInputError(f"{name} must be a number") from exc
            if not math.isfinite(value):
                raise JobInputError(f"{name} must be finite")
        elif kind in {"choice", "string"}:
            value = str(value)
        minimum = field_spec.get("minimum")
        maximum = field_spec.get("maximum")
        if minimum is not None and value < minimum:
            raise JobInputError(f"{name} must be >= {minimum}")
        if maximum is not None and value > maximum:
            raise JobInputError(f"{name} must be <= {maximum}")
        choices = field_spec.get("choices")
        if choices is not None and value not in choices:
            raise JobInputError(f"{name} must be one of: {', '.join(choices)}")
        return value

    def _build_command(
        self, operation: str, supplied: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
        spec = _OPERATIONS[operation]
        known = {field["name"] for field in spec["fields"]}
        unknown = sorted(set(supplied) - known)
        if unknown:
            raise JobInputError(f"unknown arguments for {operation}: {', '.join(unknown)}")

        command = [sys.executable, "-m", "magic_geo", spec["command"]]
        normalized: dict[str, Any] = {}
        artifacts: list[dict[str, Any]] = []
        input_paths: list[Path] = []
        for field_spec in spec["fields"]:
            name = field_spec["name"]
            default = _operation_default(self.paths, operation, field_spec)
            value = supplied.get(name, default)
            missing = value is None or value == "" or value == []
            if missing:
                if field_spec.get("required"):
                    raise JobInputError(f"missing required argument: {name}")
                continue

            kind = field_spec["kind"]
            role = field_spec.get("path_role")
            if kind == "path":
                path = self._resolve_path(str(value), role or "input")
                value = str(path)
                if role == "input":
                    input_paths.append(path)
                if role == "output":
                    relative = self.paths.display(path)
                    is_cache = operation == "export-debug" or (
                        operation == "generate"
                        and name == "debug_output"
                        and normalized.get("open_in_web", True)
                    )
                    # The generate-only debug path is irrelevant when browser
                    # preparation is disabled and must not reserve or expose a
                    # pre-existing file at that path.
                    if field_spec.get("cli", True) or is_cache:
                        artifacts.append(
                            {
                                "name": name,
                                "path": relative,
                                "kind": "cache" if is_cache else "file",
                                "available": False,
                            }
                        )
            elif kind == "path_list":
                raw_values = value.splitlines() if isinstance(value, str) else value
                if not isinstance(raw_values, list) or not raw_values:
                    raise JobInputError(f"{name} must contain at least one path")
                value = [str(self._resolve_path(str(item), role or "input")) for item in raw_values if str(item).strip()]
                if role == "input":
                    input_paths.extend(Path(item) for item in value)
                if not value and field_spec.get("required"):
                    raise JobInputError(f"{name} must contain at least one path")
            else:
                value = self._normalize_scalar(field_spec, value)
            normalized[name] = value

            if not field_spec.get("cli", True):
                continue
            flag = field_spec.get("flag")
            if kind == "boolean":
                if value:
                    if flag:
                        command.append(flag)
                elif field_spec.get("negative_flag"):
                    command.append(field_spec["negative_flag"])
            elif kind == "path_list":
                for item in value:
                    command.extend([flag, item])
            elif flag:
                command.extend([flag, str(value)])

        input_paths.extend(self._indirect_input_paths(operation, normalized))
        input_paths = list(dict.fromkeys(input_paths))

        for index, artifact in enumerate(artifacts):
            for other in artifacts[index + 1 :]:
                if self._artifacts_conflict(artifact, other):
                    raise JobInputError(
                        "declared outputs overlap: "
                        f"{artifact['path']} and {other['path']}"
                    )

            artifact_path = (self.project_root / str(artifact["path"])).resolve()
            for input_path in input_paths:
                if artifact_path == input_path:
                    raise JobInputError(
                        "output must not replace an input: "
                        f"{artifact['path']}"
                    )

            if artifact.get("kind") == "cache":
                cache_path = artifact_path
                if cache_path.exists() and not cache_path.is_dir():
                    raise JobInputError(
                        f"cache output must be a directory path: {artifact['path']}"
                    )
                for input_path in input_paths:
                    if input_path == cache_path or _is_relative_to(input_path, cache_path):
                        raise JobInputError(
                            "cache output must not replace or contain an input: "
                            f"{artifact['path']} contains "
                            f"{self.paths.display(input_path)}"
                        )

        return normalized, command, artifacts

    @staticmethod
    def _artifacts_conflict(first: dict[str, Any], second: dict[str, Any]) -> bool:
        first_path = Path(str(first["path"]))
        second_path = Path(str(second["path"]))
        if first_path == second_path:
            return True
        return (
            first.get("kind") == "cache" and _is_relative_to(second_path, first_path)
        ) or (
            second.get("kind") == "cache" and _is_relative_to(first_path, second_path)
        )

    @staticmethod
    def _file_fingerprint(path: Path) -> FileFingerprint | None:
        """Return an identity/content-change fingerprint for a regular file."""

        try:
            if not path.is_file():
                return None
            stat_result = path.stat()
        except OSError:
            return None
        return (
            stat_result.st_dev,
            stat_result.st_ino,
            stat_result.st_size,
            stat_result.st_mtime_ns,
        )

    def _snapshot_artifact_inputs(self, job: WebJob) -> None:
        before: dict[int, FileFingerprint | None] = {}
        for index, artifact in enumerate(job.artifacts):
            if artifact.get("kind") != "file":
                continue
            before[index] = self._file_fingerprint(
                self.project_root / str(artifact["path"])
            )
        with self._lock:
            job._artifact_before = before

    def _capture_artifacts(self, job: WebJob) -> None:
        """Copy files produced by this job into immutable per-job storage.

        A changed report remains downloadable even when a validation or
        calibration gate exits non-zero. Pre-existing, untouched paths are not
        exposed. Downloads use these snapshots rather than live output paths.
        """

        for index, artifact in enumerate(job.artifacts):
            if artifact.get("kind") != "file":
                continue
            source = (self.project_root / str(artifact["path"])).resolve()
            if not self.paths.allows_output(source):
                continue
            after = self._file_fingerprint(source)
            if after is None or after == job._artifact_before.get(index) or after == job._artifact_sources.get(index):
                continue
            destination_dir = self._artifact_root / job.id / str(index)
            try:
                destination_dir.mkdir(parents=True, exist_ok=True)
                destination_dir = destination_dir.resolve()
            except (OSError, RuntimeError) as exc:
                self._append_log(job, f"unable to snapshot {artifact['name']}: {exc}\n")
                continue
            if not _is_relative_to(destination_dir, self._artifact_root):
                self._append_log(job, f"unable to snapshot {artifact['name']}: unsafe path\n")
                continue
            destination = destination_dir / source.name
            temporary = destination_dir / f".{destination.name}.{uuid.uuid4().hex}.tmp"
            try:
                shutil.copy2(source, temporary)
                os.replace(temporary, destination)
                snapshot_fingerprint = self._file_fingerprint(destination)
                if snapshot_fingerprint is None:
                    raise OSError(f"artifact snapshot is not a regular file: {destination}")
            except OSError as exc:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
                self._append_log(job, f"unable to snapshot {artifact['name']}: {exc}\n")
                continue
            with self._lock:
                job._artifact_paths[index] = destination
                job._artifact_fingerprints[index] = snapshot_fingerprint
                job._artifact_sources[index] = after
                artifact["available"] = True
                artifact["bytes"] = snapshot_fingerprint[2]

    @staticmethod
    def _validate_debug_cache(path: Path) -> None:
        from .debug_export import FORMAT_NAME, FORMAT_VERSION

        try:
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            sections = json.loads((path / "sections.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"export produced an invalid debug cache: {exc}") from exc
        if not isinstance(manifest, dict) or not isinstance(sections, dict):
            raise RuntimeError("export produced non-object manifest or sections metadata")
        version = manifest.get("version")
        if (
            manifest.get("format") != FORMAT_NAME
            or type(version) is not int
            or version != FORMAT_VERSION
        ):
            raise RuntimeError(
                "export produced an unsupported debug cache format/version: "
                f"{manifest.get('format')!r} v{manifest.get('version')!r}"
            )
        if not isinstance(manifest.get("world"), dict) or not isinstance(
            manifest.get("layers"), list
        ):
            raise RuntimeError("export produced incomplete world/layer metadata")

    @staticmethod
    def _replace_cache_directory(staging: Path, destination: Path) -> Path:
        """Publish a validated cache with rollback when no server hook exists."""

        if destination.exists() and not destination.is_dir():
            raise RuntimeError(f"cache destination is not a directory: {destination}")
        backup = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.backup"
        moved_old = False
        try:
            if destination.exists():
                os.replace(destination, backup)
                moved_old = True
            os.replace(staging, destination)
        except Exception:
            if moved_old and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if moved_old:
            shutil.rmtree(backup, ignore_errors=True)
        return destination

    def _run_debug_export(
        self,
        job: WebJob,
        command: list[str],
        destination: Path,
    ) -> int:
        """Export to a private sibling and publish only a complete cache."""

        self._set_progress(job, "export_cache", "Preparing browser map", "Building map geometry, layers and tables from the saved world.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{destination.name}.{job.id}.",
                suffix=".staging",
                dir=destination.parent,
            )
        )
        staged_command = list(command)
        try:
            output_index = staged_command.index("--output") + 1
            staged_command[output_index] = str(staging)
        except (ValueError, IndexError) as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise RuntimeError("export-debug command has no output argument") from exc

        try:
            with self._lock:
                job._last_output = ""
            code = self._spawn(job, staged_command)
            with self._lock:
                cancelled = job._cancel_requested
            if code != 0 or cancelled:
                return code
            self._validate_debug_cache(staging)
            publisher = self._publish_cache or self._replace_cache_directory
            with self._lock:
                if job._cancel_requested:
                    return code
                job._publishing = True
                self._set_progress(job, "publishing", "Opening the generated map", "Publishing the complete browser cache. This final step cannot be cancelled.")
            publication_completed = False
            try:
                published = publisher(staging, destination)
                publication_completed = True
            finally:
                with self._lock:
                    job._publishing = False
                    if publication_completed:
                        # Keep the publish-to-terminal transition indivisible
                        # from the cancellation API's point of view.
                        job._finalizing = True
            published = Path(published).resolve()
            if not self.paths.allows_output(published):
                raise RuntimeError("published debug cache escaped the web workspace")
            with self._lock:
                # A destination can be reused by a later generation/export.
                # Every stored cache_dir is already a canonical display path
                # from its resolved publication destination; older jobs must
                # never advertise the replacement map as their own result.
                cache_dir = self.paths.display(published)
                for previous in self._jobs.values():
                    if previous is not job and previous.cache_dir == cache_dir:
                        previous.cache_dir = None
                        previous.map_superseded = True
                job.cache_dir = cache_dir
                job.map_superseded = False
            return code
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _append_log(self, job: WebJob, text: str, *, diagnostic: bool = False) -> None:
        with self._lock:
            job.last_activity_at = datetime.now(timezone.utc).isoformat()
            job._activity_monotonic = time.monotonic()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if lines and not diagnostic and not text.startswith("$ "):
                job._last_output = lines[-1][-1000:]
            job.log += text
            encoded = job.log.encode("utf-8", errors="replace")
            if len(encoded) > self._max_log_bytes:
                tail = encoded[-self._max_log_bytes :].decode("utf-8", errors="replace")
                job.log = "[earlier output truncated]\n" + tail

    def _set_progress(
        self, job: WebJob, phase: str, label: str, detail: str = "", *,
        current: int | float | None = None, total: int | float | None = None,
    ) -> None:
        with self._lock:
            if job._cancel_requested and phase not in {"cancelling", "cancelled"}:
                return
            now = time.monotonic()
            timestamp = datetime.now(timezone.utc).isoformat()
            if job.progress.get("phase") != phase:
                job._phase_started_monotonic = now
            job.progress = {
                "phase": phase, "label": label, "detail": detail,
                "current": current, "total": total, "updated_at": timestamp,
            }
            job.last_activity_at = timestamp
            job._activity_monotonic = now

    def _consume_output(self, job: WebJob, line: str) -> None:
        """Consume opt-in stage events while preserving ordinary/error output."""
        if line.startswith(_PROGRESS_PREFIX) and len(line) <= 16_384:
            try:
                event = json.loads(line[len(_PROGRESS_PREFIX):])
                if not isinstance(event, dict):
                    raise ValueError("progress event must be an object")
                phase, label, detail = event.get("phase"), event.get("label"), event.get("detail", "")
                if not isinstance(phase, str) or not phase.strip() or len(phase) > 80:
                    raise ValueError("invalid phase")
                if not isinstance(label, str) or not label.strip() or len(label) > 200:
                    raise ValueError("invalid label")
                if not isinstance(detail, str) or len(detail) > 4000:
                    raise ValueError("invalid detail")
                current, total = event.get("current"), event.get("total")
                if not (
                    type(current) in {int, float} and type(total) in {int, float}
                    and math.isfinite(current) and math.isfinite(total)
                    and 0 <= current <= total and total > 0
                ):
                    current = total = None
            except (ValueError, TypeError, OverflowError, RecursionError):
                pass  # A malformed diagnostic must never terminate the job.
            else:
                with self._lock:
                    if not job._cancel_requested:
                        self._set_progress(job, phase, label, detail, current=current, total=total)
                counts = f" ({current}/{total})" if total is not None else ""
                self._append_log(job, f"[{label}]{counts} {detail}\n", diagnostic=True)
                return
        self._append_log(job, line)

    def _spawn(self, job: WebJob, command: list[str]) -> int:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["MAGIC_GEO_PROGRESS"] = "1"
        process = subprocess.Popen(
            command,
            cwd=self.project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            start_new_session=os.name == "posix",
        )
        try:
            with self._lock:
                job._process = process
                job._process_active = True
                job._stopping_process = None
                cancel_immediately = job._cancel_requested
            if cancel_immediately:
                self._request_process_stop(job, process)
            assert process.stdout is not None
            for line in process.stdout:
                self._consume_output(job, line)
            process.stdout.close()

            # Keep the leader unreaped while descendants can hold its output
            # pipe. After EOF, serialize reaping with timer invalidation so a
            # delayed group signal cannot target a reused process ID. A child
            # may close stdout before exiting, so cancellation stays enabled.
            while True:
                with self._lock:
                    code = process.poll()
                    if code is not None:
                        self._finish_process(job, process)
                        return code
                time.sleep(0.05)
        except BaseException:
            # Reading, decoding or consuming output can fail while the child
            # is still writing. Do not publish failure or release its handle
            # until the group has been stopped and the direct child reaped.
            with self._lock:
                self._terminate_process(process, force=True)
                self._finish_process(job, process)
            try:
                if process.stdout is not None:
                    process.stdout.close()
            except Exception:
                pass  # Preserve the original output-handling failure.
            process.wait()
            raise

    def _finish_process(self, job: WebJob, process: subprocess.Popen[str]) -> None:
        """Disable signals while reaping and completion share the manager lock."""
        if job._process is process:
            job._process_active = False
            if job._stop_timer is not None:
                job._stop_timer.cancel()
                job._stop_timer = None

    def _request_process_stop(self, job: WebJob, process: subprocess.Popen[str]) -> None:
        # cancel() may run before Popen returns. Both cancellation paths must
        # include escalation, and overlapping/repeated requests share one timer.
        with self._lock:
            if (
                job._process is not process
                or not job._process_active
                or job._stopping_process is process
            ):
                return
            job._stopping_process = process
            self._terminate_process(process)

            def force_stop() -> None:
                with self._lock:
                    if job._process is process and job._process_active:
                        self._terminate_process(process, force=True)

            timer = threading.Timer(5.0, force_stop)
            job._stop_timer = timer
            timer.daemon = True
            timer.start()

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str], *, force: bool = False) -> None:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
            elif force:
                process.kill()
            else:
                process.terminate()
        except (OSError, ProcessLookupError):
            pass

    def _run(self, job: WebJob) -> None:
        with self._lock:
            if job._cancel_requested:
                return
            job.status = "running"
            job.started_at = datetime.now(timezone.utc).isoformat()
            job._started_monotonic = time.monotonic()
            self._set_progress(
                job, "generate" if job.operation == "generate" else "running",
                "Starting world generation" if job.operation == "generate" else _OPERATIONS[job.operation]["title"],
                "Starting the generator and loading the selected configuration." if job.operation == "generate" else "The operation is running; its output will appear below.",
            )
        final_status: JobStatus = "failed"
        final_exit_code = -1
        failure_label: str | None = None
        try:
            self._snapshot_artifact_inputs(job)
            self._append_log(job, "$ " + " ".join(job.command) + "\n")
            if job.operation == "export-debug":
                code = self._run_debug_export(
                    job,
                    job.command,
                    Path(job.arguments["output"]),
                )
            else:
                code = self._spawn(job, job.command)
            with self._lock:
                cancelled = job._cancel_requested

            # Generation can complete successfully even if its optional cache
            # export later fails. Preserve those complete primary artifacts now.
            if code == 0 and job.operation == "generate" and not cancelled:
                self._set_progress(job, "saving_artifacts", "Preserving the generated world", "Preserving a downloadable copy of the completed world.")
                self._capture_artifacts(job)

            if code == 0 and job.operation == "generate" and job.arguments.get("open_in_web", True) and not cancelled:
                world = job.arguments["output"]
                debug_dir = job.arguments.get("debug_output") or str(self.paths.debug_dir)
                export_command = [
                    sys.executable,
                    "-m",
                    "magic_geo",
                    "export-debug",
                    "--world",
                    world,
                    "--output",
                    debug_dir,
                    "--vtu" if job.arguments.get("debug_vtu", False) else "--no-vtu",
                ]
                self._append_log(job, "$ " + " ".join(export_command) + "\n")
                code = self._run_debug_export(job, export_command, Path(debug_dir))

            final_exit_code = code
            with self._lock:
                if job._cancel_requested:
                    final_status = "cancelled"
                else:
                    final_status = "succeeded" if code == 0 else "failed"
                    job._finalizing = True
                    if code != 0:
                        job.error = job._last_output or f"Process exited with code {code}."
                        failure_label = job.progress.get("label")
            if final_status == "succeeded" or (
                final_status == "failed" and job.operation in _REPORTING_OPERATIONS
            ):
                self._set_progress(job, "finalizing", "Finishing operation", "Preserving downloadable results. This final step cannot be cancelled.")
                self._capture_artifacts(job)
        except Exception as exc:  # Keep worker failures visible in the browser.
            self._append_log(job, f"web job failed: {type(exc).__name__}: {exc}\n")
            with self._lock:
                final_status = "cancelled" if job._cancel_requested else "failed"
                job.error = f"{type(exc).__name__}: {exc}"[-1000:]
                failure_label = job.progress.get("label")
            final_exit_code = -1
        finally:
            with self._lock:
                job._process = None
                job._stopping_process = None
                job._process_active = False
                job._stop_timer = None
                job._publishing = False
                job._finalizing = False
                job.status = final_status
                job.exit_code = final_exit_code
                job.finished_at = datetime.now(timezone.utc).isoformat()
                previous_label = failure_label or job.progress.get("label", "operation")
                if final_status == "succeeded":
                    detail = "The generated map is ready to explore." if job.cache_dir else "The operation finished. Available results can be downloaded below."
                    self._set_progress(job, "succeeded", "Complete", detail)
                elif final_status == "cancelled":
                    job.error = None
                    self._set_progress(job, "cancelled", "Cancelled", "The process has stopped. Any completed world download remains available.")
                else:
                    self._set_progress(job, "failed", "Operation failed", f"{previous_label}: {job.error or 'See the operation output for details.'}")
                job._finished_monotonic = time.monotonic()
            if self._on_complete is not None:
                try:
                    self._on_complete(job)
                except Exception as exc:
                    self._append_log(
                        job,
                        f"job completion callback failed: {type(exc).__name__}: {exc}\n",
                    )
