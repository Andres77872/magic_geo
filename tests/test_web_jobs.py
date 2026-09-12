"""Direct coverage for the web workbench job manager and operation catalog.

``tests/test_debug_server.py`` exercises :mod:`magic_geo.web_jobs` through the
HTTP layer and pins the CLI-parity of the catalog. This module owns the unit
level instead: workspace sandboxing, per-field argument validation, manifest
confinement, queue accounting, and every job state transition including
failure, cancellation, and cache publication.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import SkipTest, TestCase
from unittest.mock import call, patch

from magic_geo.web_jobs import (
    _EQUIVALENT_OPERATIONS,
    _OPERATIONS,
    JobInputError,
    JobManager,
    WebJob,
    _workspace_default,
    operation_catalog,
)

_BACKGROUND_OPERATIONS = {
    "generate",
    "validate",
    "validate-geo",
    "validate-geo-suite",
    "calibrate",
    "calibrate-ensemble",
    "derive-targets",
    "render",
    "render-raster",
    "export-debug",
    "export-rerun",
}


def field_spec(operation: str, name: str) -> dict[str, Any]:
    """Return a private copy of one catalog field definition."""

    for spec in _OPERATIONS[operation]["fields"]:
        if spec["name"] == name:
            return copy.deepcopy(spec)
    raise AssertionError(f"{operation} has no field {name}")


def wait_for_job(manager: JobManager, job_id: str, timeout: float = 15.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.005)
    raise AssertionError(f"job {job_id} did not finish: {manager.get(job_id)}")


def wait_until(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


class BlockingSpawn:
    """A ``_spawn`` stand-in that parks the worker until released."""

    def __init__(self, exit_code: int = 0) -> None:
        self.release = threading.Event()
        self.entered = threading.Event()
        self.commands: list[list[str]] = []
        self.calls = 0
        self._exit_code = exit_code

    def __call__(self, job: WebJob, command: list[str]) -> int:
        self.calls += 1
        self.commands.append(list(command))
        self.entered.set()
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if self.release.is_set() or job._cancel_requested:
                break
            time.sleep(0.005)
        return 143 if job._cancel_requested else self._exit_code


class WritingSpawn:
    """A ``_spawn`` stand-in that writes each declared ``--output`` file."""

    def __init__(self, payload: bytes = b"<svg/>", exit_code: int = 0) -> None:
        self.payload = payload
        self.exit_code = exit_code
        self.calls = 0

    def __call__(self, job: WebJob, command: list[str]) -> int:
        self.calls += 1
        target = Path(command[command.index("--output") + 1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.payload)
        return self.exit_code


class OperationCatalogTests(TestCase):
    def test_catalog_reports_every_operation_with_complete_metadata(self) -> None:
        catalog = operation_catalog()
        operations = {entry["id"]: entry for entry in catalog["operations"]}
        self.assertEqual(set(operations), _BACKGROUND_OPERATIONS)
        self.assertEqual(
            catalog["coverage"],
            {
                "cli_command_count": len(_BACKGROUND_OPERATIONS) + 4,
                "background_operation_count": len(_BACKGROUND_OPERATIONS),
                "equivalent_view_count": 4,
            },
        )
        for operation_id, entry in operations.items():
            with self.subTest(operation=operation_id):
                self.assertNotIn("optional_dependency", entry)
                self.assertEqual(entry["command"], _OPERATIONS[operation_id]["command"])
                self.assertIsInstance(entry["title"], str)
                self.assertIsInstance(entry["description"], str)
                self.assertIsInstance(entry["available"], bool)
                required_keys = {
                    "name",
                    "label",
                    "kind",
                    "flag",
                    "required",
                    "default",
                    "help",
                    "cli",
                    "workspace_relative",
                }
                for field in entry["fields"]:
                    self.assertEqual(required_keys - set(field), set(), field)
                    self.assertIn(
                        field["kind"],
                        {"path", "path_list", "integer", "number", "boolean", "choice", "string"},
                    )

        self.assertEqual(operations["export-rerun"]["dependency"], "rerun")
        self.assertEqual(
            operations["export-rerun"]["available"],
            importlib.util.find_spec("rerun") is not None,
        )
        self.assertNotIn("dependency", operations["validate"])
        self.assertIs(operations["validate"]["available"], True)

        self.assertEqual(
            [(entry["id"], entry["equivalent_view"]) for entry in catalog["equivalents"]],
            [
                ("init-config", "config"),
                ("backend", "api"),
                ("export-debug-map", "map"),
                ("serve", "current"),
            ],
        )

    def test_optional_dependency_availability_follows_the_import_system(self) -> None:
        # The local environment must not decide this assertion: drive the
        # importer both ways instead of restating the implementation's check.
        for label, found, expected in [
            ("dependency missing", None, False),
            ("dependency installed", importlib.util.find_spec("json"), True),
        ]:
            with self.subTest(case=label):
                with patch(
                    "magic_geo.web_jobs.importlib.util.find_spec", return_value=found
                ) as finder:
                    catalog = operation_catalog()
                entries = {entry["id"]: entry for entry in catalog["operations"]}
                self.assertEqual(finder.call_args_list, [call("rerun")])
                self.assertEqual(entries["export-rerun"]["dependency"], "rerun")
                self.assertIs(entries["export-rerun"]["available"], expected)
                self.assertIs(entries["validate"]["available"], True)

    def test_catalog_hands_out_private_copies(self) -> None:
        first = operation_catalog()
        generate = next(entry for entry in first["operations"] if entry["id"] == "generate")
        output = next(field for field in generate["fields"] if field["name"] == "output")
        self.assertEqual(output["default"], "runs/world.json")
        output["default"] = "/etc/passwd"
        first["equivalents"][0]["id"] = "tampered"

        second = operation_catalog()
        generate_again = next(entry for entry in second["operations"] if entry["id"] == "generate")
        output_again = next(field for field in generate_again["fields"] if field["name"] == "output")
        self.assertEqual(output_again["default"], "runs/world.json")
        self.assertEqual(second["equivalents"][0]["id"], "init-config")
        self.assertEqual(_EQUIVALENT_OPERATIONS[0]["id"], "init-config")

    def test_workspace_defaults_rebase_only_runs_relative_managed_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            workspace = root / "runs" / "ws"
            output = field_spec("generate", "output")
            config = field_spec("generate", "config")
            world = field_spec("validate", "world")
            cases = [
                ("rebased output", output, "runs/world.json", "runs/ws/world.json"),
                ("nested output", output, "runs/a/b.json", "runs/ws/a/b.json"),
                ("bare runs directory", output, "runs", "runs/ws"),
                ("absolute output", output, "/etc/passwd", "/etc/passwd"),
                ("foreign prefix", output, "outputs/x.json", "outputs/x.json"),
                ("empty value", output, "", ""),
                ("missing value", output, None, None),
                ("workspace-relative input", config, "runs/configs/world.yaml", "runs/ws/configs/world.yaml"),
                ("plain input", world, "runs/world.json", "runs/world.json"),
            ]
            for label, spec, value, expected in cases:
                with self.subTest(case=label):
                    self.assertEqual(
                        _workspace_default(value, spec, root, workspace), expected
                    )
            self.assertEqual(
                _workspace_default("runs/world.json", output, None, workspace),
                "runs/world.json",
            )
            self.assertEqual(
                _workspace_default("runs/world.json", output, root, None),
                "runs/world.json",
            )

    def test_catalog_defaults_follow_a_custom_workspace(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            manager = JobManager(root, Path("runs/custom"))
            try:
                catalog = operation_catalog(root, manager.workspace)
                defaults = {
                    (entry["id"], field["name"]): field["default"]
                    for entry in catalog["operations"]
                    for field in entry["fields"]
                }
            finally:
                manager.close()
            self.assertEqual(defaults[("generate", "output")], "runs/custom/world.json")
            self.assertEqual(defaults[("generate", "debug_output")], "runs/custom/debug")
            self.assertEqual(
                defaults[("generate", "config")], "runs/custom/configs/world.yaml"
            )
            self.assertEqual(defaults[("render", "output")], "runs/custom/world.svg")
            self.assertEqual(
                defaults[("calibrate", "output")], "runs/custom/calibration.json"
            )
            # Non-path defaults are untouched by workspace rebasing.
            self.assertEqual(defaults[("render", "width")], 1600)
            self.assertIs(defaults[("generate", "open_in_web")], True)
            self.assertIsNone(defaults[("generate", "summary")])


class WorkspaceSandboxTests(TestCase):
    def test_workspace_must_stay_inside_the_project(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory() as other_dir:
            root = Path(temp_dir).resolve()
            outside = Path(other_dir).resolve()
            with self.assertRaisesRegex(
                ValueError, r"^web workspace must be inside the project directory$"
            ):
                JobManager(root, outside)

            # A symlinked workspace resolves before the containment check.
            (root / "escape").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(
                ValueError, r"^web workspace must be inside the project directory$"
            ):
                JobManager(root, Path("escape"))

            manager = JobManager(root, Path("runs"))
            try:
                self.assertEqual(manager.workspace, root / "runs")
                self.assertTrue((root / "runs" / ".magic-geo-web" / "artifacts").is_dir())
            finally:
                manager.close()

    def test_internal_directories_must_not_be_symlinks(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory() as other_dir:
            root = Path(temp_dir).resolve()
            outside = Path(other_dir).resolve()
            workspace = root / "runs"
            workspace.mkdir()
            (workspace / ".magic-geo-web").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(
                ValueError, r"^web internal directory must not be a symbolic link$"
            ):
                JobManager(root, Path("runs"))

            (workspace / ".magic-geo-web").unlink()
            internal = workspace / ".magic-geo-web"
            internal.mkdir()
            (internal / "artifacts").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(
                ValueError, r"^web artifact directory must not be a symbolic link$"
            ):
                JobManager(root, Path("runs"))

    def test_resolve_path_confines_inputs_and_outputs(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory() as other_dir:
            root = Path(temp_dir).resolve()
            outside = Path(other_dir).resolve()
            (outside / "external.json").write_text("{}", encoding="utf-8")
            (root / "configs").mkdir()
            (root / "configs" / "world.yaml").write_text("config_version: 2\n", encoding="utf-8")
            manager = JobManager(root, Path("runs"))
            try:
                self.assertEqual(
                    manager._resolve_path("configs/world.yaml", "input"),
                    root / "configs" / "world.yaml",
                )
                self.assertEqual(
                    manager._resolve_path("runs/reports/out.json", "output"),
                    root / "runs" / "reports" / "out.json",
                )

                cases = [
                    (
                        "input escapes project",
                        str(outside / "external.json"),
                        "input",
                        rf"^input path must stay inside {root}: ",
                    ),
                    (
                        "input traversal",
                        "configs/../../external.json",
                        "input",
                        rf"^input path must stay inside {root}: ",
                    ),
                    (
                        "missing input",
                        "configs/absent.yaml",
                        "input",
                        r"^input path must name an existing regular file: configs/absent\.yaml$",
                    ),
                    (
                        "directory input",
                        "configs",
                        "input",
                        r"^input path must name an existing regular file: configs$",
                    ),
                    (
                        "output escapes workspace",
                        "configs/world.yaml",
                        "output",
                        rf"^output path must stay inside {root / 'runs'}: ",
                    ),
                    (
                        "output replaces workspace",
                        "runs",
                        "output",
                        r"^output path must not replace the web workspace$",
                    ),
                    (
                        "output in reserved directory",
                        "runs/.magic-geo-web/artifacts/stolen.json",
                        "output",
                        r"^output path uses the reserved web-internal directory$",
                    ),
                ]
                for label, value, role, message in cases:
                    with self.subTest(case=label):
                        with self.assertRaisesRegex(JobInputError, message):
                            manager._resolve_path(value, role)

                with patch.object(Path, "resolve", side_effect=OSError("simulated")):
                    with self.assertRaisesRegex(
                        JobInputError,
                        r"^unable to resolve input path 'configs/world\.yaml': simulated$",
                    ):
                        manager._resolve_path("configs/world.yaml", "input")
            finally:
                manager.close()


class ArgumentValidationTests(TestCase):
    def setUp(self) -> None:
        self._temp = TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name).resolve()
        (self.root / "configs").mkdir()
        (self.root / "runs").mkdir()
        self.world = self.root / "runs" / "world.json"
        self.world.write_text("{}", encoding="utf-8")
        self.config = self.root / "configs" / "world.yaml"
        self.config.write_text("config_version: 2\nmesh: {}\n", encoding="utf-8")
        # The catalog default for ``config`` is workspace-relative; several
        # operations resolve it when the caller supplies only required fields.
        default_config = self.root / "runs" / "configs" / "world.yaml"
        default_config.parent.mkdir()
        default_config.write_text("config_version: 2\nmesh: {}\n", encoding="utf-8")
        self.targets = self.root / "configs" / "targets.json"
        self.targets.write_text("{}", encoding="utf-8")
        self.data = self.root / "configs" / "data.asc"
        self.data.write_text("data", encoding="utf-8")
        self.sources = self.root / "configs" / "sources.json"
        self.sources.write_text(
            json.dumps({"sources": [{"path": "data.asc"}]}), encoding="utf-8"
        )
        self.matrix = self.root / "configs" / "matrix.yaml"
        self.matrix.write_text("scenarios:\n  - name: base\n", encoding="utf-8")
        self.manager = JobManager(self.root, Path("runs"))
        self.addCleanup(self.manager.close)

    def required_arguments(self) -> dict[str, dict[str, Any]]:
        return {
            "validate": {"world": str(self.world)},
            "validate-geo": {"world": str(self.world)},
            "validate-geo-suite": {"matrix": str(self.matrix)},
            "calibrate": {"world": str(self.world), "targets": str(self.targets)},
            "calibrate-ensemble": {
                "config": str(self.config),
                "matrix": str(self.matrix),
                "targets": str(self.targets),
            },
            "derive-targets": {"sources": str(self.sources)},
            "render": {"world": str(self.world)},
            "render-raster": {"world": str(self.world)},
            "export-debug": {"world": str(self.world)},
            "export-rerun": {"world": str(self.world)},
        }

    def test_every_operation_rejects_each_missing_required_argument(self) -> None:
        supplied_by_operation = self.required_arguments()
        for operation, arguments in supplied_by_operation.items():
            required = {
                spec["name"]
                for spec in _OPERATIONS[operation]["fields"]
                if spec.get("required")
            }
            self.assertEqual(set(arguments), required, operation)
            with self.subTest(operation=operation, case="complete"):
                _, command, _ = self.manager._build_command(operation, arguments)
                self.assertEqual(
                    command[:4],
                    [sys.executable, "-m", "magic_geo", _OPERATIONS[operation]["command"]],
                )
            for name in sorted(required):
                with self.subTest(operation=operation, missing=name):
                    partial = {key: value for key, value in arguments.items() if key != name}
                    with self.assertRaisesRegex(
                        JobInputError, rf"^missing required argument: {name}$"
                    ):
                        self.manager._build_command(operation, partial)
                with self.subTest(operation=operation, blank=name):
                    blanked = dict(arguments)
                    blanked[name] = ""
                    with self.assertRaisesRegex(
                        JobInputError, rf"^missing required argument: {name}$"
                    ):
                        self.manager._build_command(operation, blanked)
        self.assertNotIn("generate", supplied_by_operation)
        self.assertEqual(
            [spec["name"] for spec in _OPERATIONS["generate"]["fields"] if spec.get("required")],
            [],
        )

    def test_unknown_operations_and_arguments_are_rejected(self) -> None:
        with self.assertRaisesRegex(JobInputError, r"^unknown operation: teleport$"):
            self.manager.submit("teleport", {})
        with self.assertRaisesRegex(JobInputError, r"^unknown operation: $"):
            self.manager.submit("", {})
        with self.assertRaisesRegex(JobInputError, r"^unknown operation: _OPERATIONS$"):
            self.manager.submit("_OPERATIONS", {})
        with self.assertRaisesRegex(
            JobInputError, r"^unknown arguments for validate: shell, sudo$"
        ):
            self.manager._build_command(
                "validate", {"world": str(self.world), "sudo": True, "shell": "rm -rf /"}
            )
        with self.assertRaisesRegex(
            JobInputError, r"^unknown arguments for render: open_in_web$"
        ):
            self.manager._build_command(
                "render", {"world": str(self.world), "open_in_web": True}
            )

    def test_scalar_arguments_are_normalized_or_rejected(self) -> None:
        rejected = [
            ("render", "labels", "yes", r"^labels must be true or false$"),
            ("render", "labels", 1, r"^labels must be true or false$"),
            ("generate", "cells", True, r"^cells must be an integer$"),
            ("generate", "cells", 128.5, r"^cells must be an integer$"),
            ("generate", "cells", float("nan"), r"^cells must be an integer$"),
            ("generate", "cells", "12x", r"^cells must be an integer$"),
            # Strings are parsed as base-10 integers, never coerced via float.
            ("generate", "cells", "256.5", r"^cells must be an integer$"),
            ("render", "width", "4e2", r"^width must be an integer$"),
            ("generate", "cells", None, r"^cells must be an integer$"),
            ("generate", "cells", 2**63, r"^cells is outside the supported 64-bit range$"),
            ("generate", "cells", 4, r"^cells must be >= 128$"),
            ("render", "width", 100, r"^width must be >= 320$"),
            ("render", "width", 9000, r"^width must be <= 6400$"),
            ("render", "contour_interval", "abc", r"^contour_interval must be a number$"),
            ("export-debug", "elevation_exaggeration", True, r"^elevation_exaggeration must be a number$"),
            ("render", "contour_interval", float("inf"), r"^contour_interval must be finite$"),
            ("render", "contour_interval", 10.0, r"^contour_interval must be >= 50\.0$"),
            (
                "render",
                "projection",
                "cube",
                r"^projection must be one of: equirectangular, mollweide, orthographic$",
            ),
            (
                "generate",
                "world_format",
                "yaml",
                r"^world_format must be one of: auto, json, mgeo$",
            ),
        ]
        for operation, name, value, message in rejected:
            with self.subTest(field=name, value=repr(value)):
                with self.assertRaisesRegex(JobInputError, message):
                    self.manager._normalize_scalar(field_spec(operation, name), value)

        accepted = [
            ("generate", "cells", "256", 256),
            ("generate", "cells", 256.0, 256),
            ("generate", "cells", 256, 256),
            ("render", "width", 320, 320),
            ("render", "contour_interval", 50, 50.0),
            ("render", "contour_interval", "512.5", 512.5),
            ("render", "labels", True, True),
            ("render", "projection", "mollweide", "mollweide"),
            ("generate", "world_format", "mgeo", "mgeo"),
        ]
        for operation, name, value, expected in accepted:
            with self.subTest(field=name, value=repr(value)):
                result = self.manager._normalize_scalar(field_spec(operation, name), value)
                self.assertEqual(result, expected)
                self.assertIs(type(result), type(expected))

    def test_boolean_and_flag_rendering_matches_the_field_policy(self) -> None:
        _, command, artifacts = self.manager._build_command(
            "render",
            {
                "world": str(self.world),
                "output": "runs/map.svg",
                "labels": True,
                "contours": False,
                "width": 800,
                "projection": "mollweide",
            },
        )
        self.assertEqual(
            command,
            [
                sys.executable,
                "-m",
                "magic_geo",
                "render",
                "--world",
                str(self.world),
                "--output",
                str(self.root / "runs" / "map.svg"),
                "--width",
                "800",
                "--height",
                "800",
                "--projection",
                "mollweide",
                "--labels",
                "--no-contours",
                "--contour-interval",
                "500.0",
            ],
        )
        self.assertEqual(
            artifacts,
            [
                {
                    "name": "output",
                    "path": "runs/map.svg",
                    "kind": "file",
                    "available": False,
                }
            ],
        )

        normalized, generate_command, generate_artifacts = self.manager._build_command(
            "generate",
            {
                "config": "configs/world.yaml",
                "output": "runs/world-out.json",
                "geo_only": False,
                "open_in_web": False,
                "debug_output": "runs/debug",
            },
        )
        self.assertNotIn("--geo-only", generate_command)
        self.assertIs(normalized["open_in_web"], False)
        # Browser-only fields never reach the subprocess command line.
        for hidden in ("--open-in-web", "--debug-output", "runs/debug"):
            self.assertNotIn(hidden, generate_command)
        self.assertEqual(
            [artifact["path"] for artifact in generate_artifacts], ["runs/world-out.json"]
        )

        # The ``cli`` flag is what withholds browser-only fields, not the
        # incidental absence of a flag spelling: give them one and they must
        # still be excluded while remaining part of the recorded arguments.
        flagged = copy.deepcopy(_OPERATIONS)
        for spec in flagged["generate"]["fields"]:
            if spec["name"] == "debug_output":
                spec["flag"] = "--debug-output"
            elif spec["name"] == "open_in_web":
                spec["flag"] = "--open-in-web"
        with patch.dict(_OPERATIONS, flagged, clear=True):
            browser_args, guarded_command, _ = self.manager._build_command(
                "generate",
                {
                    "config": "configs/world.yaml",
                    "output": "runs/world-out.json",
                    "open_in_web": True,
                    "debug_output": "runs/debug",
                },
            )
        for hidden in (
            "--open-in-web",
            "--debug-output",
            str(self.root / "runs" / "debug"),
            "True",
        ):
            self.assertNotIn(hidden, guarded_command)
        self.assertIs(browser_args["open_in_web"], True)
        self.assertEqual(browser_args["debug_output"], str(self.root / "runs" / "debug"))

        _, no_vtu_command, cache_artifacts = self.manager._build_command(
            "export-debug", {"world": str(self.world), "output": "runs/cache", "vtu": False}
        )
        self.assertIn("--no-vtu", no_vtu_command)
        self.assertNotIn("--vtu", no_vtu_command)
        self.assertEqual(cache_artifacts[0]["kind"], "cache")

    def test_path_list_arguments_expand_to_repeated_flags(self) -> None:
        second = self.root / "configs" / "targets_b.json"
        second.write_text("{}", encoding="utf-8")
        normalized, command, _ = self.manager._build_command(
            "calibrate-ensemble",
            {
                "config": "configs/world.yaml",
                "matrix": "configs/matrix.yaml",
                "targets": "configs/targets.json\nconfigs/targets_b.json\n",
            },
        )
        self.assertEqual(normalized["targets"], [str(self.targets), str(second)])
        self.assertEqual(
            [command[index + 1] for index, item in enumerate(command) if item == "--targets"],
            [str(self.targets), str(second)],
        )

        base = {"config": "configs/world.yaml", "matrix": "configs/matrix.yaml"}
        with self.assertRaisesRegex(
            JobInputError, r"^targets must contain at least one path$"
        ):
            self.manager._build_command(
                "calibrate-ensemble", {**base, "targets": {"path": "configs/targets.json"}}
            )
        with self.assertRaisesRegex(
            JobInputError, r"^targets must contain at least one path$"
        ):
            self.manager._build_command("calibrate-ensemble", {**base, "targets": ["   "]})
        with self.assertRaisesRegex(
            JobInputError, r"^input path must name an existing regular file: configs/absent\.json$"
        ):
            self.manager._build_command(
                "calibrate-ensemble", {**base, "targets": ["configs/absent.json"]}
            )

    def test_declared_outputs_must_not_overlap_or_shadow_inputs(self) -> None:
        with self.assertRaisesRegex(
            JobInputError, r"^declared outputs overlap: runs/same\.json and runs/same\.json$"
        ):
            self.manager._build_command(
                "generate",
                {
                    "output": "runs/same.json",
                    "summary": "runs/same.json",
                    "open_in_web": False,
                },
            )
        plain_file = self.root / "runs" / "not-a-directory.txt"
        plain_file.write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(
            JobInputError,
            r"^cache output must be a directory path: runs/not-a-directory\.txt$",
        ):
            self.manager._build_command(
                "export-debug",
                {"world": str(self.world), "output": "runs/not-a-directory.txt"},
            )
        with self.assertRaisesRegex(
            JobInputError, r"^output must not replace an input: runs/world\.json$"
        ):
            self.manager._build_command(
                "render-raster", {"world": str(self.world), "output": "runs/world.json"}
            )
        nested_input = self.root / "runs" / "debug" / "world.json"
        nested_input.parent.mkdir()
        nested_input.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(
            JobInputError,
            r"^cache output must not replace or contain an input: runs/debug contains "
            r"runs/debug/world\.json$",
        ):
            self.manager._build_command(
                "export-debug", {"world": str(nested_input), "output": "runs/debug"}
            )

    def test_manifest_declared_inputs_are_enforced_when_building_a_command(self) -> None:
        with TemporaryDirectory() as other_dir:
            outside = Path(other_dir).resolve() / "external.asc"
            outside.write_text("external", encoding="utf-8")
            self.sources.write_text(
                json.dumps({"sources": [{"path": str(outside)}]}), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                JobInputError,
                rf"^indirect input path must stay inside {self.root}: "
                r"calibration sources\[0\]\.path=",
            ):
                self.manager._build_command(
                    "derive-targets", {"sources": str(self.sources)}
                )

        # Transitive inputs also participate in the output-overlap policy.
        managed_input = self.root / "runs" / "data.asc"
        managed_input.write_text("data", encoding="utf-8")
        self.sources.write_text(
            json.dumps({"sources": [{"path": "../runs/data.asc"}]}), encoding="utf-8"
        )
        with self.assertRaisesRegex(
            JobInputError, r"^output must not replace an input: runs/data\.asc$"
        ):
            self.manager._build_command(
                "derive-targets",
                {"sources": str(self.sources), "output": "runs/data.asc"},
            )

        bundle = self.root / "runs" / "bundle.json"
        bundle.write_text("{}", encoding="utf-8")
        self.matrix.write_text(
            "scenarios:\n"
            "  - empirical_calibration:\n"
            "      target_bundle: ../runs/bundle.json\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            JobInputError, r"^output must not replace an input: runs/bundle\.json$"
        ):
            self.manager._build_command(
                "validate-geo-suite",
                {"matrix": str(self.matrix), "output": "runs/bundle.json"},
            )

    def test_artifact_conflicts_cover_containment_in_both_directions(self) -> None:
        cache = {"path": "runs/debug", "kind": "cache"}
        cases = [
            (
                "identical files",
                {"path": "runs/a.json", "kind": "file"},
                {"path": "runs/a.json", "kind": "file"},
                True,
            ),
            ("cache contains file", cache, {"path": "runs/debug/manifest.json", "kind": "file"}, True),
            ("file inside cache", {"path": "runs/debug/manifest.json", "kind": "file"}, cache, True),
            (
                "sibling files",
                {"path": "runs/a.json", "kind": "file"},
                {"path": "runs/b.json", "kind": "file"},
                False,
            ),
            (
                "nested files without a cache",
                {"path": "runs/a", "kind": "file"},
                {"path": "runs/a/b.json", "kind": "file"},
                False,
            ),
            ("disjoint caches", cache, {"path": "runs/other", "kind": "cache"}, False),
        ]
        for label, first, second, expected in cases:
            with self.subTest(case=label):
                self.assertIs(JobManager._artifacts_conflict(first, second), expected)


class ManifestConfinementTests(TestCase):
    def setUp(self) -> None:
        self._temp = TemporaryDirectory()
        self._outside = TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.addCleanup(self._outside.cleanup)
        self.root = Path(self._temp.name).resolve()
        self.outside = Path(self._outside.name).resolve()
        (self.root / "configs").mkdir()
        (self.root / "runs").mkdir()
        self.data = self.root / "configs" / "data.asc"
        self.data.write_text("data", encoding="utf-8")
        (self.outside / "external.asc").write_text("external", encoding="utf-8")
        self.sources = self.root / "configs" / "sources.json"
        self.manager = JobManager(self.root, Path("runs"))
        self.addCleanup(self.manager.close)

    def write_sources(self, payload: Any) -> Path:
        self.sources.write_text(json.dumps(payload), encoding="utf-8")
        return self.sources

    def test_source_manifest_paths_are_resolved_and_confined(self) -> None:
        dbf = self.root / "configs" / "shapes.dbf"
        prj = self.root / "configs" / "shapes.prj"
        dbf.write_text("dbf", encoding="utf-8")
        prj.write_text("prj", encoding="utf-8")
        path = self.write_sources(
            {
                "sources": [
                    {"path": "data.asc", "dbf_path": "shapes.dbf", "prj_path": "shapes.prj"}
                ]
            }
        )
        self.assertEqual(
            self.manager._derive_target_inputs(path), [self.data, dbf, prj]
        )
        # A bare array manifest is accepted as the sources list itself.
        self.assertEqual(
            self.manager._derive_target_inputs(self.write_sources([{"path": "data.asc"}])),
            [self.data],
        )

    def test_source_manifest_rejects_unsafe_or_malformed_records(self) -> None:
        cases = [
            (
                "not a list",
                {"sources": {"path": "data.asc"}},
                r"^calibration source manifest must be an array or an object with a sources array$",
            ),
            (
                "record not an object",
                {"sources": ["data.asc"]},
                r"^calibration sources\[0\] must be an object$",
            ),
            (
                "missing path",
                {"sources": [{"format": "ascii"}]},
                r"^calibration sources\[0\]\.path must be a non-empty path string$",
            ),
            (
                "blank path",
                {"sources": [{"path": "   "}]},
                r"^calibration sources\[0\]\.path must be a non-empty path string$",
            ),
            (
                "non-string path",
                {"sources": [{"path": 7}]},
                r"^calibration sources\[0\]\.path must be a non-empty path string$",
            ),
            (
                "absolute escape",
                {"sources": [{"path": str(self.outside / "external.asc")}]},
                rf"^indirect input path must stay inside {self.root}: "
                r"calibration sources\[0\]\.path=",
            ),
            (
                "traversal escape",
                {"sources": [{"path": "../../external.asc"}]},
                rf"^indirect input path must stay inside {self.root}: ",
            ),
            (
                "missing file",
                {"sources": [{"path": "absent.asc"}]},
                r"^calibration sources\[0\]\.path must name an existing regular file: absent\.asc$",
            ),
            (
                "secondary escape",
                {
                    "sources": [
                        {"path": "data.asc", "dbf_path": str(self.outside / "external.asc")}
                    ]
                },
                r"calibration sources\[0\]\.dbf_path=",
            ),
        ]
        for label, payload, message in cases:
            with self.subTest(case=label):
                path = self.write_sources(payload)
                with self.assertRaisesRegex(JobInputError, message):
                    self.manager._derive_target_inputs(path)

    def test_hydrobasins_catalog_entries_are_validated(self) -> None:
        catalog = self.root / "configs" / "catalog.json"
        archive = self.root / "configs" / "basins.zip"
        archive.write_text("zip", encoding="utf-8")
        catalog.write_text(
            json.dumps({"archives": [{"path": "basins.zip"}]}), encoding="utf-8"
        )
        path = self.write_sources(
            {
                "sources": [
                    {"path": "catalog.json", "format": "HydroBASINS_Archive_Catalog"}
                ]
            }
        )
        self.assertEqual(self.manager._derive_target_inputs(path), [catalog, archive])

        cases = [
            (
                "no archives key",
                {},
                r"^HydroBASINS archive catalog must contain a non-empty archives array$",
            ),
            (
                "empty archives",
                {"archives": []},
                r"^HydroBASINS archive catalog must contain a non-empty archives array$",
            ),
            (
                "archive not an object",
                {"archives": ["basins.zip"]},
                r"^HydroBASINS archives\[0\] must be an object$",
            ),
            (
                "archive escapes project",
                {"archives": [{"path": str(self.outside / "external.asc")}]},
                r"^indirect input path must stay inside .*HydroBASINS archives\[0\]\.path=",
            ),
        ]
        for label, payload, message in cases:
            with self.subTest(case=label):
                catalog.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(JobInputError, message):
                    self.manager._derive_target_inputs(path)

        # A source that is not a catalog format is never opened as one.
        catalog.write_text("not json at all", encoding="utf-8")
        plain = self.write_sources({"sources": [{"path": "catalog.json", "format": "ascii_grid"}]})
        self.assertEqual(self.manager._derive_target_inputs(plain), [catalog])

    def test_manifest_reads_enforce_size_encoding_and_syntax_limits(self) -> None:
        matrix = self.root / "configs" / "matrix.yaml"
        matrix.write_text("scenarios: []\n", encoding="utf-8")
        with patch("magic_geo.web_jobs._MAX_WEB_MANIFEST_BYTES", 8):
            with self.assertRaisesRegex(
                JobInputError, r"^geo-validation matrix exceeds the 8-byte web limit$"
            ):
                self.manager._geo_suite_inputs(matrix)

        matrix.write_bytes(b"scenarios: [\xff\xfe]\n")
        with self.assertRaisesRegex(
            JobInputError, rf"^unable to read geo-validation matrix: {matrix}: "
        ):
            self.manager._geo_suite_inputs(matrix)

        missing = self.root / "configs" / "absent.yaml"
        with self.assertRaisesRegex(
            JobInputError, rf"^unable to read geo-validation matrix: {missing}: "
        ):
            self.manager._geo_suite_inputs(missing)

        # JSON manifests surface the same read guards through their parse error.
        path = self.write_sources({"sources": [{"path": "data.asc"}]})
        with patch("magic_geo.web_jobs._MAX_WEB_MANIFEST_BYTES", 8):
            with self.assertRaisesRegex(
                JobInputError,
                rf"^invalid calibration source manifest: {path}: calibration source "
                r"manifest exceeds the 8-byte web limit$",
            ):
                self.manager._derive_target_inputs(path)

        path.write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(
            JobInputError,
            rf"^invalid calibration source manifest: {path}: Expecting property name",
        ):
            self.manager._derive_target_inputs(path)

        path.write_bytes(b'{"sources": [{"path": "\xff\xfe.asc"}]}')
        with self.assertRaisesRegex(
            JobInputError,
            rf"^invalid calibration source manifest: {path}: unable to read "
            r"calibration source manifest: ",
        ):
            self.manager._derive_target_inputs(path)

    def test_geo_validation_matrix_inputs_are_resolved_and_confined(self) -> None:
        matrix = self.root / "configs" / "matrix.yaml"
        bundle = self.root / "configs" / "bundle.json"
        manifest = self.root / "configs" / "manifest.json"
        supplemental = self.root / "configs" / "supplemental.json"
        manifest.write_text("{}", encoding="utf-8")
        supplemental.write_text("{}", encoding="utf-8")
        bundle.write_text(
            json.dumps(
                {
                    "derivation": {
                        "source_manifests": [{"path": "manifest.json"}],
                        "supplemental_target_derivations": [{"path": "supplemental.json"}],
                    }
                }
            ),
            encoding="utf-8",
        )
        matrix.write_text(
            "scenarios:\n"
            "  - name: plain\n"
            "  - name: empirical\n"
            "    empirical_calibration:\n"
            "      target_bundle: bundle.json\n",
            encoding="utf-8",
        )
        self.assertEqual(
            self.manager._geo_suite_inputs(matrix), [bundle, manifest, supplemental]
        )

        cases = [
            (
                "no scenarios",
                "profiles:\n  - generic\n",
                r"^geo-validation matrix must contain a scenarios array$",
            ),
            (
                "scenario not an object",
                "scenarios:\n  - plain\n",
                r"^geo-validation scenarios\[0\] must be an object$",
            ),
            (
                "empirical not an object",
                "scenarios:\n  - empirical_calibration: bundle.json\n",
                r"^geo-validation scenarios\[0\]\.empirical_calibration must be an object$",
            ),
            (
                "bundle escapes project",
                "scenarios:\n"
                "  - empirical_calibration:\n"
                f"      target_bundle: {self.outside / 'external.asc'}\n",
                r"^indirect input path must stay inside .*"
                r"geo-validation scenarios\[0\]\.empirical_calibration\.target_bundle=",
            ),
            (
                "invalid yaml",
                "scenarios: [\n",
                r"^invalid geo-validation matrix: ",
            ),
        ]
        for label, text, message in cases:
            with self.subTest(case=label):
                matrix.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(JobInputError, message):
                    self.manager._geo_suite_inputs(matrix)

    def test_target_bundle_derivation_records_are_validated(self) -> None:
        matrix = self.root / "configs" / "matrix.yaml"
        bundle = self.root / "configs" / "bundle.json"
        matrix.write_text(
            "scenarios:\n"
            "  - empirical_calibration:\n"
            "      target_bundle: bundle.json\n",
            encoding="utf-8",
        )
        cases = [
            (
                "derivation not an object",
                {"derivation": ["manifest.json"]},
                r"^empirical target bundle derivation must be an object$",
            ),
            (
                "records not an array",
                {"derivation": {"source_manifests": {"path": "manifest.json"}}},
                r"^empirical target bundle derivation\.source_manifests must be an array$",
            ),
            (
                "record not an object",
                {"derivation": {"supplemental_target_derivations": ["manifest.json"]}},
                r"^empirical target bundle derivation\.supplemental_target_derivations\[0\] "
                r"must be an object$",
            ),
            (
                "record escapes project",
                {
                    "derivation": {
                        "source_manifests": [{"path": str(self.outside / "external.asc")}]
                    }
                },
                r"^indirect input path must stay inside .*"
                r"empirical target bundle derivation\.source_manifests\[0\]\.path=",
            ),
        ]
        for label, payload, message in cases:
            with self.subTest(case=label):
                bundle.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(JobInputError, message):
                    self.manager._geo_suite_inputs(matrix)

        # No derivation block at all is a valid, fully confined bundle.
        bundle.write_text(json.dumps({"targets": []}), encoding="utf-8")
        self.assertEqual(self.manager._geo_suite_inputs(matrix), [bundle])

    def test_yaml_manifest_structure_limits_are_enforced(self) -> None:
        matrix = self.root / "configs" / "matrix.yaml"
        matrix.write_text(
            "scenarios:\n" + "".join(f"  - name: s{index}\n" for index in range(4)),
            encoding="utf-8",
        )
        with patch("magic_geo.web_jobs._MAX_WEB_MANIFEST_EVENTS", 5):
            with self.assertRaisesRegex(
                JobInputError, r"^geo-validation matrix exceeds the 5-event web limit$"
            ):
                self.manager._geo_suite_inputs(matrix)

        nested = "scenarios:\n" + "".join("  " * (index + 1) + "- \n" for index in range(70))
        matrix.write_text(nested, encoding="utf-8")
        with self.assertRaisesRegex(
            JobInputError, r"^geo-validation matrix exceeds the 64-level web limit$"
        ):
            self.manager._geo_suite_inputs(matrix)

        aliased = (
            "anchor: &shared value\n"
            "scenarios:\n"
            + "".join(f"  - name: s{index}\n    ref: *shared\n" for index in range(4))
        )
        matrix.write_text(aliased, encoding="utf-8")
        with patch("magic_geo.web_jobs._MAX_WEB_MANIFEST_ALIASES", 2):
            with self.assertRaisesRegex(
                JobInputError, r"^geo-validation matrix exceeds the 2-alias web limit$"
            ):
                self.manager._geo_suite_inputs(matrix)

    def test_indirect_resolution_reports_unresolvable_paths(self) -> None:
        with patch.object(Path, "resolve", side_effect=OSError("simulated")):
            with self.assertRaisesRegex(
                JobInputError,
                r"^unable to resolve calibration sources\[0\]\.path 'data\.asc': simulated$",
            ):
                self.manager._resolve_indirect_input(
                    "data.asc", self.root / "configs", "calibration sources[0].path"
                )


class JobLifecycleTests(TestCase):
    def setUp(self) -> None:
        self._temp = TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name).resolve()
        (self.root / "runs").mkdir()
        self.world = self.root / "runs" / "world.json"
        self.world.write_text("{}", encoding="utf-8")
        self.other_world = self.root / "runs" / "other.json"
        self.other_world.write_text("{}", encoding="utf-8")

    def manager(self, **kwargs: Any) -> JobManager:
        manager = JobManager(self.root, Path("runs"), **kwargs)
        self.addCleanup(manager.close)
        return manager

    def test_queued_and_running_jobs_are_summarized_newest_first(self) -> None:
        manager = self.manager()
        blocker = BlockingSpawn()
        with patch.object(manager, "_spawn", side_effect=blocker):
            first = manager.submit("validate", {"world": str(self.world)})
            self.assertTrue(blocker.entered.wait(5.0))
            second = manager.submit("validate", {"world": str(self.other_world)})
            self.assertEqual(first["status"], "queued")
            self.assertIsNone(first["started_at"])
            self.assertIsNone(first["exit_code"])
            self.assertEqual(first["artifacts"], [])

            listing = manager.list()
            self.assertEqual(
                [entry["id"] for entry in listing], [second["id"], first["id"]]
            )
            self.assertEqual(
                set(listing[0]),
                {
                    "id",
                    "operation",
                    "status",
                    "created_at",
                    "started_at",
                    "finished_at",
                    "exit_code",
                    "artifacts",
                    "cache_dir",
                },
            )
            self.assertEqual(listing[1]["status"], "running")
            self.assertEqual(listing[0]["status"], "queued")
            blocker.release.set()
            first_done = wait_for_job(manager, first["id"])
            second_done = wait_for_job(manager, second["id"])

        self.assertEqual(first_done["status"], "succeeded")
        self.assertEqual(first_done["exit_code"], 0)
        self.assertIsNotNone(first_done["started_at"])
        self.assertIsNotNone(first_done["finished_at"])
        self.assertEqual(second_done["status"], "succeeded")
        self.assertEqual(blocker.calls, 2)
        self.assertEqual(
            blocker.commands[0],
            [sys.executable, "-m", "magic_geo", "validate", "--world", str(self.world)],
        )

    def test_nonzero_exit_marks_the_job_failed(self) -> None:
        manager = self.manager()

        def failing(job: WebJob, command: list[str]) -> int:
            manager._append_log(job, "boom\n")
            return 3

        with patch.object(manager, "_spawn", side_effect=failing):
            submitted = manager.submit("validate", {"world": str(self.world)})
            finished = wait_for_job(manager, submitted["id"])
        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["exit_code"], 3)
        self.assertEqual(
            finished["log"],
            "$ "
            + " ".join(
                [sys.executable, "-m", "magic_geo", "validate", "--world", str(self.world)]
            )
            + "\nboom\n",
        )

    def test_worker_exceptions_are_reported_on_the_job(self) -> None:
        manager = self.manager()
        with patch.object(manager, "_spawn", side_effect=RuntimeError("spawn exploded")):
            submitted = manager.submit("validate", {"world": str(self.world)})
            finished = wait_for_job(manager, submitted["id"])
        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["exit_code"], -1)
        self.assertIn("web job failed: RuntimeError: spawn exploded\n", finished["log"])

    def test_completion_callback_receives_terminal_jobs_and_survives_failure(self) -> None:
        seen: list[tuple[str, str, int | None]] = []

        def on_complete(job: WebJob) -> None:
            seen.append((job.id, job.status, job.exit_code))
            raise ValueError("callback exploded")

        manager = self.manager(on_complete=on_complete)
        with patch.object(manager, "_spawn", return_value=0):
            submitted = manager.submit("validate", {"world": str(self.world)})
            finished = wait_for_job(manager, submitted["id"])
        self.assertEqual(seen, [(submitted["id"], "succeeded", 0)])
        self.assertIn(
            "job completion callback failed: ValueError: callback exploded\n",
            manager.get(submitted["id"])["log"],
        )
        self.assertEqual(finished["status"], "succeeded")

    def test_duplicate_and_conflicting_submissions_are_deduplicated(self) -> None:
        manager = self.manager()
        blocker = BlockingSpawn()
        try:
            with patch.object(manager, "_spawn", side_effect=blocker):
                first = manager.submit(
                    "render", {"world": str(self.world), "output": "runs/map.svg"}
                )
                self.assertTrue(blocker.entered.wait(5.0))
                repeat = manager.submit(
                    "render", {"world": str(self.world), "output": "runs/map.svg"}
                )
                self.assertEqual(repeat["id"], first["id"])
                self.assertEqual(len(manager.list()), 1)

                with self.assertRaisesRegex(
                    JobInputError,
                    r"^output already targeted by an active job: runs/map\.svg$",
                ):
                    manager.submit(
                        "render",
                        {"world": str(self.other_world), "output": "runs/map.svg"},
                    )
                self.assertEqual(len(manager.list()), 1)
                self.assertEqual(blocker.calls, 1)
        finally:
            blocker.release.set()
        wait_for_job(manager, first["id"])

    def test_terminal_jobs_are_evicted_once_the_queue_is_full(self) -> None:
        manager = self.manager(max_jobs=2)
        spawn = WritingSpawn()
        with patch.object(manager, "_spawn", side_effect=spawn):
            first = manager.submit(
                "render", {"world": str(self.world), "output": "runs/a.svg"}
            )
            self.assertEqual(wait_for_job(manager, first["id"])["status"], "succeeded")
            second = manager.submit(
                "render", {"world": str(self.world), "output": "runs/b.svg"}
            )
            self.assertEqual(wait_for_job(manager, second["id"])["status"], "succeeded")
            self.assertTrue((manager._artifact_root / first["id"]).is_dir())

            third = manager.submit(
                "render", {"world": str(self.world), "output": "runs/c.svg"}
            )
            self.assertEqual(wait_for_job(manager, third["id"])["status"], "succeeded")

        self.assertEqual(
            [entry["id"] for entry in manager.list()], [third["id"], second["id"]]
        )
        with self.assertRaises(KeyError):
            manager.get(first["id"])
        self.assertFalse((manager._artifact_root / first["id"]).exists())

    def test_a_full_queue_of_active_jobs_is_rejected(self) -> None:
        manager = self.manager(max_jobs=1)
        blocker = BlockingSpawn()
        try:
            with patch.object(manager, "_spawn", side_effect=blocker):
                active = manager.submit("validate", {"world": str(self.world)})
                self.assertTrue(blocker.entered.wait(5.0))
                with self.assertRaisesRegex(
                    JobInputError,
                    r"^job queue is full \(1\); wait for or cancel existing work$",
                ):
                    manager.submit("validate", {"world": str(self.other_world)})
                self.assertEqual([entry["id"] for entry in manager.list()], [active["id"]])
        finally:
            blocker.release.set()
        wait_for_job(manager, active["id"])

    def test_submission_is_refused_once_the_manager_is_closed(self) -> None:
        manager = self.manager()
        manager.close()
        manager.close()  # Idempotent.
        with self.assertRaisesRegex(JobInputError, r"^web job manager is closed$"):
            manager.submit("validate", {"world": str(self.world)})
        # The closed state is reported before any argument is resolved, so a
        # shut-down manager never answers with an unrelated validation error.
        with self.assertRaisesRegex(JobInputError, r"^web job manager is closed$"):
            manager.submit("validate", {"world": "runs/absent.json"})

        racing = self.manager()
        original = racing._build_command

        def close_then_build(operation: str, supplied: dict[str, Any]):
            result = original(operation, supplied)
            racing.close()
            return result

        with patch.object(racing, "_build_command", side_effect=close_then_build):
            with self.assertRaisesRegex(JobInputError, r"^web job manager is closed$"):
                racing.submit("validate", {"world": str(self.world)})
        self.assertEqual(racing.list(), [])

    def test_unavailable_executor_does_not_record_a_job(self) -> None:
        manager = self.manager()
        with patch.object(
            manager._executor, "submit", side_effect=RuntimeError("cannot schedule")
        ):
            with self.assertRaisesRegex(
                JobInputError, r"^web job executor is unavailable$"
            ):
                manager.submit("validate", {"world": str(self.world)})
        self.assertEqual(manager.list(), [])

    def test_cancel_rejects_unknown_jobs_and_leaves_terminal_jobs_alone(self) -> None:
        manager = self.manager()
        with self.assertRaisesRegex(KeyError, r"^'does-not-exist'$"):
            manager.cancel("does-not-exist")
        with self.assertRaisesRegex(KeyError, r"^'does-not-exist'$"):
            manager.get("does-not-exist")

        with patch.object(manager, "_spawn", return_value=0):
            submitted = manager.submit("validate", {"world": str(self.world)})
            finished = wait_for_job(manager, submitted["id"])
        cancelled = manager.cancel(submitted["id"])
        self.assertEqual(cancelled["status"], "succeeded")
        self.assertEqual(cancelled["exit_code"], 0)
        self.assertEqual(cancelled["finished_at"], finished["finished_at"])
        # Nothing at all changed: a terminal job is returned untouched rather
        # than quietly acquiring a pending cancellation.
        self.assertEqual(cancelled, finished)
        self.assertFalse(manager._jobs[submitted["id"]]._cancel_requested)

    def test_cancelling_a_queued_job_prevents_it_from_ever_spawning(self) -> None:
        manager = self.manager()
        blocker = BlockingSpawn()
        try:
            with patch.object(manager, "_spawn", side_effect=blocker):
                running = manager.submit("validate", {"world": str(self.world)})
                self.assertTrue(blocker.entered.wait(5.0))
                queued = manager.submit("validate", {"world": str(self.other_world)})
                cancelled = manager.cancel(queued["id"])
                self.assertEqual(cancelled["status"], "cancelled")
                self.assertIsNotNone(cancelled["finished_at"])
                self.assertIsNone(cancelled["started_at"])
                self.assertIsNone(cancelled["exit_code"])
                blocker.release.set()
                wait_for_job(manager, running["id"])
                self.assertTrue(
                    wait_until(lambda: manager.get(queued["id"])["status"] == "cancelled")
                )
        finally:
            blocker.release.set()
        self.assertEqual(blocker.calls, 1)
        self.assertEqual(manager.get(queued["id"])["log"], "")

    def test_cancelling_a_running_job_terminates_the_child_process(self) -> None:
        if os.name != "posix":
            raise SkipTest("process-group cancellation is asserted on POSIX only")
        manager = self.manager()
        real_popen = subprocess.Popen
        child = [
            sys.executable,
            "-c",
            "import sys, time\nprint('child-started', flush=True)\ntime.sleep(30)\n",
        ]

        def fake_popen(command, **kwargs):
            return real_popen(child, **kwargs)

        with patch("magic_geo.web_jobs.subprocess.Popen", side_effect=fake_popen):
            submitted = manager.submit("validate", {"world": str(self.world)})
            self.assertTrue(
                wait_until(
                    lambda: "child-started" in manager.get(submitted["id"])["log"]
                ),
                manager.get(submitted["id"]),
            )
            manager.cancel(submitted["id"])
            finished = wait_for_job(manager, submitted["id"])
        self.assertEqual(finished["status"], "cancelled")
        self.assertEqual(finished["exit_code"], -signal.SIGTERM)
        self.assertIn("child-started", finished["log"])

    def test_close_cancels_active_work_and_preserves_terminal_history(self) -> None:
        manager = self.manager()
        with patch.object(manager, "_spawn", return_value=0):
            done = manager.submit("validate", {"world": str(self.world)})
            finished = wait_for_job(manager, done["id"])
        self.assertEqual(finished["status"], "succeeded")

        blocker = BlockingSpawn()
        try:
            with patch.object(manager, "_spawn", side_effect=blocker):
                running = manager.submit("validate", {"world": str(self.other_world)})
                self.assertTrue(blocker.entered.wait(5.0))
                queued = manager.submit(
                    "render", {"world": str(self.world), "output": "runs/map.svg"}
                )
                manager.close()
        finally:
            blocker.release.set()

        self.assertEqual(manager.get(running["id"])["status"], "cancelled")
        self.assertEqual(manager.get(queued["id"])["status"], "cancelled")
        self.assertIsNotNone(manager.get(queued["id"])["finished_at"])
        self.assertIsNone(manager.get(queued["id"])["started_at"])
        # A completed job keeps its terminal record across shutdown.
        self.assertEqual(manager.get(done["id"])["status"], "succeeded")
        self.assertEqual(manager.get(done["id"])["finished_at"], finished["finished_at"])
        self.assertEqual(blocker.calls, 1)

    def test_cancel_is_ignored_during_the_commit_phase(self) -> None:
        manager = self.manager()
        blocker = BlockingSpawn()
        try:
            with patch.object(manager, "_spawn", side_effect=blocker):
                submitted = manager.submit("validate", {"world": str(self.world)})
                self.assertTrue(blocker.entered.wait(5.0))
                job = manager._jobs[submitted["id"]]
                for phase in ("_finalizing", "_publishing"):
                    with self.subTest(phase=phase):
                        with manager._lock:
                            setattr(job, phase, True)
                        ignored = manager.cancel(submitted["id"])
                        self.assertEqual(ignored["status"], "running")
                        self.assertFalse(job._cancel_requested)
                        with manager._lock:
                            setattr(job, phase, False)
                blocker.release.set()
                completed = wait_for_job(manager, submitted["id"])
        finally:
            blocker.release.set()
        self.assertEqual(completed["status"], "succeeded")
        self.assertEqual(completed["exit_code"], 0)

    def test_cancellation_racing_the_spawn_still_kills_the_child(self) -> None:
        if os.name != "posix":
            raise SkipTest("process-group cancellation is asserted on POSIX only")
        manager = self.manager()
        job = WebJob(id="early", operation="validate", arguments={}, command=[])
        job._cancel_requested = True
        manager._jobs[job.id] = job
        code = manager._spawn(job, [sys.executable, "-c", "import time; time.sleep(30)"])
        self.assertEqual(code, -signal.SIGTERM)

        # Termination signals the whole process group and escalates to KILL.
        with patch("magic_geo.web_jobs.os.killpg") as killpg:
            JobManager._terminate_process(job._process)
            JobManager._terminate_process(job._process, force=True)
        self.assertEqual(
            killpg.call_args_list,
            [
                call(job._process.pid, signal.SIGTERM),
                call(job._process.pid, signal.SIGKILL),
            ],
        )

        # A child that has already exited is not an error.
        with patch(
            "magic_geo.web_jobs.os.killpg", side_effect=ProcessLookupError("already gone")
        ) as reaped:
            self.assertIsNone(JobManager._terminate_process(job._process))
            self.assertIsNone(JobManager._terminate_process(job._process, force=True))
        self.assertEqual(reaped.call_count, 2)

    def _assert_stubborn_spawn_is_cancelled(self, *, shutdown: bool) -> None:
        if os.name != "posix":
            raise SkipTest("process-group cancellation is asserted on POSIX only")
        manager = self.manager()
        real_popen = subprocess.Popen
        real_timer = threading.Timer
        spawned = threading.Event()
        release_spawn = threading.Event()
        release_escalation = threading.Event()
        escalation_scheduled = threading.Event()
        children = []
        timers = []
        shutdown_thread = None
        child = [
            sys.executable, "-c",
            "import signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "print('ready', flush=True)\n"
            "time.sleep(30)\n",
        ]

        def delayed_popen(command, **kwargs):
            if children:
                process = real_popen(
                    [sys.executable, "-c", "print('next-job-finished')"], **kwargs
                )
                children.append(process)
                return process
            process = real_popen(child, **kwargs)
            children.append(process)
            # The handler is installed before cancel(), while _spawn has not
            # yet received the child handle. No scheduler timing is assumed.
            self.assertEqual(process.stdout.readline(), "ready\n")
            spawned.set()
            if not release_spawn.wait(5.0):
                raise AssertionError("test did not release Popen")
            return process

        def short_timer(interval, function):
            self.assertEqual(interval, 5.0)

            def fire():
                if release_escalation.wait(5.0):
                    function()

            timer = real_timer(0.05, fire)
            timers.append(timer)
            escalation_scheduled.set()
            return timer

        try:
            with patch("magic_geo.web_jobs.subprocess.Popen", side_effect=delayed_popen), patch(
                "magic_geo.web_jobs.threading.Timer", side_effect=short_timer
            ):
                submitted = manager.submit("validate", {"world": str(self.world)})
                self.assertTrue(spawned.wait(5.0))
                job = manager._jobs[submitted["id"]]
                self.assertIsNone(job._process)
                queued = manager.submit("validate", {"world": str(self.other_world)})
                if shutdown:
                    shutdown_thread = threading.Thread(target=manager.close)
                    shutdown_thread.start()
                    self.assertTrue(wait_until(lambda: job._cancel_requested, timeout=2.0))
                else:
                    manager.cancel(job.id)
                self.assertTrue(job._cancel_requested)
                release_spawn.set()
                self.assertTrue(
                    escalation_scheduled.wait(1.0),
                    "cancellation during Popen did not schedule forced termination",
                )
                manager.cancel(job.id)
                manager.cancel(job.id)
                self.assertEqual(len(timers), 1)
                self.assertEqual(manager.get(job.id)["status"], "running")
                self.assertIsNone(children[0].poll())
                release_escalation.set()
                finished = wait_for_job(manager, job.id, timeout=3.0)
                self.assertEqual(finished["status"], "cancelled")
                self.assertEqual(finished["exit_code"], -signal.SIGKILL)
                self.assertIsNone(job._process)
                self.assertEqual(children[0].returncode, -signal.SIGKILL)
                if shutdown_thread is not None:
                    shutdown_thread.join(timeout=2.0)
                    self.assertFalse(shutdown_thread.is_alive())
                    self.assertEqual(manager.get(queued["id"])["status"], "cancelled")
                    self.assertEqual(len(children), 1)
                else:
                    next_finished = wait_for_job(manager, queued["id"], timeout=3.0)
                    self.assertEqual(next_finished["status"], "succeeded")
                    self.assertIn("next-job-finished", next_finished["log"])
                    self.assertEqual(len(children), 2)
        finally:
            release_spawn.set()
            release_escalation.set()
            # The unfixed implementation must fail without leaving its
            # deliberately TERM-ignoring child or executor alive.
            for process in children:
                if process.poll() is None:
                    JobManager._terminate_process(process, force=True)
                process.wait(timeout=3.0)
            for timer in timers:
                timer.join(timeout=2.0)
            if shutdown_thread is not None:
                shutdown_thread.join(timeout=3.0)
            manager.close()

    def test_cancellation_during_spawn_escalates_for_a_term_ignoring_child(self) -> None:
        self._assert_stubborn_spawn_is_cancelled(shutdown=False)

    def test_shutdown_during_spawn_escalates_and_reaps_a_term_ignoring_child(self) -> None:
        self._assert_stubborn_spawn_is_cancelled(shutdown=True)

    def test_children_run_in_the_project_root_with_unbuffered_output(self) -> None:
        manager = self.manager()
        job = WebJob(id="environment", operation="validate", arguments={}, command=[])
        code = manager._spawn(
            job,
            [
                sys.executable,
                "-c",
                "import os, sys\n"
                "sys.stdout.write(os.getcwd() + '\\n')\n"
                "sys.stdout.write(os.environ.get('PYTHONUNBUFFERED', '<unset>') + '\\n')\n",
            ],
        )
        self.assertEqual(code, 0)
        self.assertEqual(job.log, f"{self.root}\n1\n")

    def test_log_growth_is_truncated_from_the_front(self) -> None:
        manager = self.manager(max_log_bytes=64)
        job = WebJob(id="log", operation="validate", arguments={}, command=[])
        manager._append_log(job, "head\n")
        manager._append_log(job, "A" * 200)
        self.assertEqual(job.log, "[earlier output truncated]\n" + "A" * 64)


class ArtifactSnapshotTests(TestCase):
    def setUp(self) -> None:
        self._temp = TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name).resolve()
        (self.root / "runs").mkdir()
        self.world = self.root / "runs" / "world.json"
        self.world.write_text("{}", encoding="utf-8")
        self.manager = JobManager(self.root, Path("runs"))
        self.addCleanup(self.manager.close)

    def render_job(self) -> dict[str, Any]:
        with patch.object(self.manager, "_spawn", side_effect=WritingSpawn(b"<svg/>")):
            submitted = self.manager.submit(
                "render", {"world": str(self.world), "output": "runs/map.svg"}
            )
            return wait_for_job(self.manager, submitted["id"])

    def test_successful_run_publishes_one_downloadable_snapshot(self) -> None:
        finished = self.render_job()
        self.assertEqual(finished["status"], "succeeded")
        self.assertEqual(
            finished["artifacts"],
            [
                {
                    "name": "output",
                    "path": "runs/map.svg",
                    "kind": "file",
                    "available": True,
                    "bytes": 6,
                }
            ],
        )
        snapshot = self.manager.artifact_path(finished["id"], 0)
        self.assertEqual(snapshot.read_bytes(), b"<svg/>")
        self.assertEqual(
            snapshot,
            (self.manager._artifact_root / finished["id"] / "0" / "map.svg"),
        )

        # Detail and list payloads are private copies; a caller that edits one
        # cannot rewrite the manager's own record of the job.
        detail = self.manager.get(finished["id"])
        detail["artifacts"][0]["path"] = "../../etc/passwd"
        detail["arguments"]["world"] = "/etc/shadow"
        listed = self.manager.list()[0]
        listed["artifacts"][0]["path"] = "../../etc/passwd"
        again = self.manager.get(finished["id"])
        self.assertEqual(again["artifacts"][0]["path"], "runs/map.svg")
        self.assertEqual(again["arguments"]["world"], str(self.world))
        self.assertEqual(self.manager.list()[0]["artifacts"][0]["path"], "runs/map.svg")

    def test_artifact_lookup_rejects_unknown_jobs_and_indexes(self) -> None:
        finished = self.render_job()
        for label, job_id, index, message in [
            ("unknown job", "no-such-job", 0, r"^'no-such-job'$"),
            ("index past the end", finished["id"], 1, rf"^'{finished['id']}:1'$"),
            ("negative index", finished["id"], -1, rf"^'{finished['id']}:-1'$"),
        ]:
            with self.subTest(case=label):
                with self.assertRaisesRegex(KeyError, message):
                    self.manager.artifact_path(job_id, index)

    def test_tampered_or_missing_snapshots_are_not_served(self) -> None:
        finished = self.render_job()
        job = self.manager._jobs[finished["id"]]
        snapshot = self.manager.artifact_path(finished["id"], 0)
        fingerprint = job._artifact_fingerprints[0]

        # A byte-identical copy outside the artifact store is still refused:
        # its recorded fingerprint matches, so only containment can reject it.
        outside = self.root / "runs" / "elsewhere.svg"
        outside.write_bytes(b"<svg/>")
        job._artifact_paths[0] = outside
        job._artifact_fingerprints[0] = JobManager._file_fingerprint(outside)
        self.assertIsNotNone(job._artifact_fingerprints[0])
        with self.assertRaises(FileNotFoundError) as relocated:
            self.manager.artifact_path(finished["id"], 0)
        self.assertEqual(relocated.exception.args, (outside,))

        job._artifact_paths[0] = snapshot
        job._artifact_fingerprints[0] = fingerprint
        snapshot.write_bytes(b"<svg>tampered</svg>")
        with self.assertRaises(FileNotFoundError) as tampered:
            self.manager.artifact_path(finished["id"], 0)
        self.assertEqual(tampered.exception.args, (snapshot,))

        job._artifact_fingerprints.pop(0)
        with self.assertRaises(FileNotFoundError) as unfingerprinted:
            self.manager.artifact_path(finished["id"], 0)
        self.assertEqual(unfingerprinted.exception.args, (snapshot,))

        job._artifact_paths.pop(0)
        with self.assertRaises(FileNotFoundError) as unrecorded:
            self.manager.artifact_path(finished["id"], 0)
        self.assertEqual(unrecorded.exception.args, (None,))

        job.artifacts[0]["available"] = False
        with self.assertRaisesRegex(FileNotFoundError, r"runs/map\.svg"):
            self.manager.artifact_path(finished["id"], 0)

    def test_untouched_outputs_are_never_exposed_as_downloads(self) -> None:
        stale = self.root / "runs" / "map.svg"
        stale.write_bytes(b"<stale/>")

        def leave_output_alone(job: WebJob, command: list[str]) -> int:
            return 0

        with patch.object(self.manager, "_spawn", side_effect=leave_output_alone):
            skipped = self.manager.submit(
                "render", {"world": str(self.world), "output": "runs/map.svg"}
            )
            finished = wait_for_job(self.manager, skipped["id"])
        self.assertEqual(finished["status"], "succeeded")
        self.assertEqual(
            finished["artifacts"],
            [
                {
                    "name": "output",
                    "path": "runs/map.svg",
                    "kind": "file",
                    "available": False,
                }
            ],
        )
        self.assertNotIn("unable to snapshot", finished["log"])
        self.assertFalse((self.manager._artifact_root / skipped["id"]).exists())
        with self.assertRaises(FileNotFoundError):
            self.manager.artifact_path(skipped["id"], 0)
        self.assertEqual(stale.read_bytes(), b"<stale/>")

        # Rewriting the same pre-existing path does publish a snapshot.
        with patch.object(
            self.manager, "_spawn", side_effect=WritingSpawn(b"<fresh/><g/>")
        ):
            rewritten = self.manager.submit(
                "render", {"world": str(self.world), "output": "runs/map.svg"}
            )
            refreshed = wait_for_job(self.manager, rewritten["id"])
        self.assertNotEqual(rewritten["id"], skipped["id"])
        self.assertEqual(
            refreshed["artifacts"],
            [
                {
                    "name": "output",
                    "path": "runs/map.svg",
                    "kind": "file",
                    "available": True,
                    "bytes": 12,
                }
            ],
        )
        self.assertEqual(
            self.manager.artifact_path(rewritten["id"], 0).read_bytes(), b"<fresh/><g/>"
        )

    def test_failed_runs_publish_reports_but_withhold_other_outputs(self) -> None:
        cases = [
            ("reporting operation", "validate-geo", "runs/report.json", True),
            ("plain operation", "render", "runs/map.svg", False),
        ]
        for label, operation, output, expected in cases:
            with self.subTest(case=label):
                with patch.object(
                    self.manager, "_spawn", side_effect=WritingSpawn(b"{}", exit_code=2)
                ):
                    submitted = self.manager.submit(
                        operation, {"world": str(self.world), "output": output}
                    )
                    finished = wait_for_job(self.manager, submitted["id"])
                self.assertEqual(finished["status"], "failed")
                self.assertEqual(finished["exit_code"], 2)
                self.assertEqual(finished["artifacts"][0]["path"], output)
                self.assertIs(finished["artifacts"][0]["available"], expected)
                if expected:
                    self.assertEqual(finished["artifacts"][0]["bytes"], 2)
                    self.assertEqual(
                        self.manager.artifact_path(submitted["id"], 0).read_bytes(), b"{}"
                    )
                else:
                    self.assertNotIn("bytes", finished["artifacts"][0])
                    with self.assertRaises(FileNotFoundError):
                        self.manager.artifact_path(submitted["id"], 0)

    def test_snapshot_failures_are_logged_without_failing_the_job(self) -> None:
        with (
            patch.object(self.manager, "_spawn", side_effect=WritingSpawn(b"<svg/>")),
            patch("magic_geo.web_jobs.shutil.copy2", side_effect=OSError("disk full")),
        ):
            submitted = self.manager.submit(
                "render", {"world": str(self.world), "output": "runs/map.svg"}
            )
            finished = wait_for_job(self.manager, submitted["id"])
        self.assertEqual(finished["status"], "succeeded")
        self.assertEqual(finished["exit_code"], 0)
        self.assertIs(finished["artifacts"][0]["available"], False)
        self.assertIn("unable to snapshot output: disk full\n", finished["log"])
        with self.assertRaises(FileNotFoundError):
            self.manager.artifact_path(submitted["id"], 0)

    def test_unwritable_artifact_storage_is_logged_without_failing_the_job(self) -> None:
        def write_output(job: WebJob, command: list[str]) -> int:
            Path(command[command.index("--output") + 1]).write_bytes(b"<svg/>")
            return 0

        with (
            patch.object(self.manager, "_spawn", side_effect=write_output),
            patch.object(Path, "mkdir", side_effect=OSError("no space left")),
        ):
            submitted = self.manager.submit(
                "render", {"world": str(self.world), "output": "runs/map.svg"}
            )
            finished = wait_for_job(self.manager, submitted["id"])
        self.assertEqual(finished["status"], "succeeded")
        self.assertIs(finished["artifacts"][0]["available"], False)
        self.assertIn("unable to snapshot output: no space left\n", finished["log"])

    def test_file_fingerprints_identify_only_readable_regular_files(self) -> None:
        target = self.root / "runs" / "sample.txt"
        target.write_text("abc", encoding="utf-8")
        stat_result = target.stat()
        self.assertEqual(
            JobManager._file_fingerprint(target),
            (stat_result.st_dev, stat_result.st_ino, 3, stat_result.st_mtime_ns),
        )
        self.assertIsNone(JobManager._file_fingerprint(self.root / "runs"))
        self.assertIsNone(JobManager._file_fingerprint(self.root / "runs" / "absent.txt"))

        real_stat = Path.stat
        calls: list[int] = []

        def flaky_stat(self, *args: Any, **kwargs: Any):
            calls.append(1)
            if len(calls) > 1:
                raise OSError("stat vanished")
            return real_stat(self, *args, **kwargs)

        with patch.object(Path, "stat", flaky_stat):
            self.assertIsNone(JobManager._file_fingerprint(target))


class DebugCachePublicationTests(TestCase):
    def setUp(self) -> None:
        self._temp = TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name).resolve()
        (self.root / "runs").mkdir()
        self.world = self.root / "runs" / "world.json"
        self.world.write_text("{}", encoding="utf-8")

    def manager(self, **kwargs: Any) -> JobManager:
        manager = JobManager(self.root, Path("runs"), **kwargs)
        self.addCleanup(manager.close)
        return manager

    def test_debug_cache_validation_rejects_incomplete_exports(self) -> None:
        try:
            from magic_geo.debug_export import FORMAT_NAME, FORMAT_VERSION
        except ImportError as exc:  # pragma: no cover - depends on installed extras
            raise SkipTest(f"debug cache validation requires magic-geo[debug]: {exc}") from exc

        valid_manifest = {
            "format": FORMAT_NAME,
            "version": FORMAT_VERSION,
            "world": {"name": "tiny"},
            "layers": [],
        }
        cases = [
            ("missing files", None, None, r"^export produced an invalid debug cache: "),
            ("invalid json", "{not json", "{}", r"^export produced an invalid debug cache: "),
            (
                "non-object manifest",
                json.dumps([valid_manifest]),
                "{}",
                r"^export produced non-object manifest or sections metadata$",
            ),
            (
                "non-object sections",
                json.dumps(valid_manifest),
                "[]",
                r"^export produced non-object manifest or sections metadata$",
            ),
            (
                "foreign format",
                json.dumps({**valid_manifest, "format": "other-cache"}),
                "{}",
                r"^export produced an unsupported debug cache format/version: "
                r"'other-cache' v1$",
            ),
            (
                "future version",
                json.dumps({**valid_manifest, "version": FORMAT_VERSION + 1}),
                "{}",
                r"^export produced an unsupported debug cache format/version: ",
            ),
            (
                "boolean version",
                json.dumps({**valid_manifest, "version": True}),
                "{}",
                r"^export produced an unsupported debug cache format/version: ",
            ),
            (
                "missing world metadata",
                json.dumps({**valid_manifest, "world": "tiny"}),
                "{}",
                r"^export produced incomplete world/layer metadata$",
            ),
            (
                "missing layer metadata",
                json.dumps({**valid_manifest, "layers": {}}),
                "{}",
                r"^export produced incomplete world/layer metadata$",
            ),
        ]
        for index, (label, manifest_text, sections_text, message) in enumerate(cases):
            with self.subTest(case=label):
                cache = self.root / "runs" / f"cache-{index}"
                cache.mkdir()
                if manifest_text is not None:
                    (cache / "manifest.json").write_text(manifest_text, encoding="utf-8")
                if sections_text is not None:
                    (cache / "sections.json").write_text(sections_text, encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, message):
                    JobManager._validate_debug_cache(cache)

        complete = self.root / "runs" / "cache-valid"
        complete.mkdir()
        (complete / "manifest.json").write_text(json.dumps(valid_manifest), encoding="utf-8")
        (complete / "sections.json").write_text("{}", encoding="utf-8")
        self.assertIsNone(JobManager._validate_debug_cache(complete))

    def test_cache_replacement_swaps_directories_and_rolls_back(self) -> None:
        destination = self.root / "runs" / "debug"
        staging = self.root / "runs" / "staging"
        staging.mkdir()
        (staging / "manifest.json").write_text("new", encoding="utf-8")

        published = JobManager._replace_cache_directory(staging, destination)
        self.assertEqual(published, destination)
        self.assertEqual((destination / "manifest.json").read_text(encoding="utf-8"), "new")
        self.assertFalse(staging.exists())

        second_staging = self.root / "runs" / "staging2"
        second_staging.mkdir()
        (second_staging / "manifest.json").write_text("newer", encoding="utf-8")
        JobManager._replace_cache_directory(second_staging, destination)
        self.assertEqual((destination / "manifest.json").read_text(encoding="utf-8"), "newer")
        self.assertEqual(
            [entry.name for entry in (self.root / "runs").iterdir() if ".backup" in entry.name],
            [],
        )

        file_destination = self.root / "runs" / "not-a-directory"
        file_destination.write_text("x", encoding="utf-8")
        third_staging = self.root / "runs" / "staging3"
        third_staging.mkdir()
        with self.assertRaisesRegex(
            RuntimeError, rf"^cache destination is not a directory: {file_destination}$"
        ):
            JobManager._replace_cache_directory(third_staging, file_destination)

        real_replace = os.replace
        calls: list[int] = []

        def failing_replace(source, target, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise OSError("cross-device publish failed")
            return real_replace(source, target, **kwargs)

        with patch("magic_geo.web_jobs.os.replace", side_effect=failing_replace):
            with self.assertRaisesRegex(OSError, r"^cross-device publish failed$"):
                JobManager._replace_cache_directory(third_staging, destination)
        self.assertEqual((destination / "manifest.json").read_text(encoding="utf-8"), "newer")
        self.assertTrue(third_staging.is_dir())

    def test_export_without_an_output_argument_is_reported(self) -> None:
        manager = self.manager()
        job = WebJob(id="noout", operation="export-debug", arguments={}, command=[])
        with self.assertRaisesRegex(
            RuntimeError, r"^export-debug command has no output argument$"
        ):
            manager._run_debug_export(
                job,
                [sys.executable, "-m", "magic_geo", "export-debug"],
                self.root / "runs" / "debug",
            )
        self.assertEqual(
            sorted(
                entry.name
                for entry in (self.root / "runs").iterdir()
                if entry.name != ".magic-geo-web"
            ),
            ["world.json"],
        )

    def test_published_cache_must_stay_inside_the_workspace(self) -> None:
        escaped = self.root / "escaped-cache"

        def publisher(staging: Path, destination: Path) -> Path:
            escaped.mkdir(exist_ok=True)
            return escaped

        manager = self.manager(publish_cache=publisher)
        with (
            patch.object(manager, "_spawn", return_value=0),
            patch.object(manager, "_validate_debug_cache", return_value=None),
        ):
            submitted = manager.submit(
                "export-debug",
                {"world": str(self.world), "output": "runs/debug", "vtu": False},
            )
            finished = wait_for_job(manager, submitted["id"])
        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["exit_code"], -1)
        self.assertIsNone(finished["cache_dir"])
        self.assertIn(
            "web job failed: RuntimeError: published debug cache escaped the web workspace\n",
            finished["log"],
        )

    def test_successful_export_publishes_the_cache_directory(self) -> None:
        manager = self.manager()

        def stage_cache(job: WebJob, command: list[str]) -> int:
            staging = Path(command[command.index("--output") + 1])
            (staging / "manifest.json").write_text("staged", encoding="utf-8")
            return 0

        with (
            patch.object(manager, "_spawn", side_effect=stage_cache),
            patch.object(manager, "_validate_debug_cache", return_value=None),
        ):
            submitted = manager.submit(
                "export-debug",
                {"world": str(self.world), "output": "runs/debug", "vtu": False},
            )
            finished = wait_for_job(manager, submitted["id"])
        self.assertEqual(finished["status"], "succeeded", finished["log"])
        self.assertEqual(finished["cache_dir"], "runs/debug")
        self.assertEqual(
            (self.root / "runs" / "debug" / "manifest.json").read_text(encoding="utf-8"),
            "staged",
        )
        self.assertEqual(
            [artifact["kind"] for artifact in finished["artifacts"]], ["cache"]
        )

    def test_failed_export_never_publishes_and_cleans_up_staging(self) -> None:
        manager = self.manager()
        existing = self.root / "runs" / "debug"
        existing.mkdir()
        (existing / "manifest.json").write_text("previous", encoding="utf-8")

        staged: list[Path] = []

        def failing_stage(job: WebJob, command: list[str]) -> int:
            staging = Path(command[command.index("--output") + 1])
            staged.append(staging)
            (staging / "partial.txt").write_text("partial", encoding="utf-8")
            return 4

        with patch.object(manager, "_spawn", side_effect=failing_stage):
            submitted = manager.submit(
                "export-debug",
                {"world": str(self.world), "output": "runs/debug", "vtu": False},
            )
            finished = wait_for_job(manager, submitted["id"])
        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["exit_code"], 4)
        self.assertIsNone(finished["cache_dir"])
        # Staging is a hidden sibling of the destination so a partial export is
        # never visible at the published name and never crosses a device.
        self.assertEqual(len(staged), 1)
        self.assertEqual(staged[0].parent, existing.parent)
        self.assertTrue(staged[0].name.startswith(".debug."), staged[0].name)
        self.assertTrue(staged[0].name.endswith(".staging"), staged[0].name)
        self.assertFalse(staged[0].exists())
        self.assertEqual(
            [entry.name for entry in existing.iterdir()], ["manifest.json"]
        )
        self.assertEqual(
            (existing / "manifest.json").read_text(encoding="utf-8"), "previous"
        )
        self.assertEqual(
            sorted(
                entry.name
                for entry in (self.root / "runs").iterdir()
                if entry.name != ".magic-geo-web"
            ),
            ["debug", "world.json"],
        )

    def test_cancellation_before_publication_leaves_the_cache_untouched(self) -> None:
        for label, cancel_during in [
            ("during the export", "spawn"),
            ("after validation", "validate"),
        ]:
            with self.subTest(case=label):
                manager = self.manager()
                destination = self.root / "runs" / f"debug-{cancel_during}"
                running: list[WebJob] = []
                validated: list[Path] = []

                def stage_cache(job: WebJob, command: list[str]) -> int:
                    running.append(job)
                    staging = Path(command[command.index("--output") + 1])
                    (staging / "manifest.json").write_text("staged", encoding="utf-8")
                    if cancel_during == "spawn":
                        manager.cancel(job.id)
                    return 0

                def validate(path: Path) -> None:
                    validated.append(path)
                    if cancel_during == "validate":
                        manager.cancel(running[0].id)

                with (
                    patch.object(manager, "_spawn", side_effect=stage_cache),
                    patch.object(manager, "_validate_debug_cache", side_effect=validate),
                ):
                    submitted = manager.submit(
                        "export-debug",
                        {
                            "world": str(self.world),
                            "output": f"runs/{destination.name}",
                            "vtu": False,
                        },
                    )
                    finished = wait_for_job(manager, submitted["id"])

                self.assertEqual(finished["status"], "cancelled")
                self.assertEqual(finished["exit_code"], 0)
                self.assertIsNone(finished["cache_dir"])
                self.assertFalse(destination.exists())
                # A cancellation seen before validation stops the export there;
                # one seen during validation stops it before publication.
                if cancel_during == "spawn":
                    self.assertEqual(validated, [])
                else:
                    self.assertEqual(len(validated), 1)
                    self.assertEqual(validated[0].parent, destination.parent)
                    self.assertNotEqual(validated[0], destination)
                self.assertEqual(
                    [
                        entry.name
                        for entry in (self.root / "runs").iterdir()
                        if ".staging" in entry.name
                    ],
                    [],
                )

    def test_generation_artifacts_survive_a_failing_cache_export(self) -> None:
        manager = self.manager()
        config = self.root / "runs" / "configs" / "world.yaml"
        config.parent.mkdir()
        config.write_text("config_version: 2\nmesh: {}\n", encoding="utf-8")

        def spawn(job: WebJob, command: list[str]) -> int:
            target = Path(command[command.index("--output") + 1])
            if command[3] == "generate":
                target.write_text('{"schema_version": 1}', encoding="utf-8")
                return 0
            return 7

        with patch.object(manager, "_spawn", side_effect=spawn):
            submitted = manager.submit(
                "generate",
                {
                    "output": "runs/world-out.json",
                    "open_in_web": True,
                    "debug_output": "runs/debug",
                    "debug_vtu": False,
                },
            )
            finished = wait_for_job(manager, submitted["id"])

        self.assertEqual(finished["status"], "failed")
        self.assertEqual(finished["exit_code"], 7)
        self.assertIsNone(finished["cache_dir"])
        self.assertFalse((self.root / "runs" / "debug").exists())
        # The completed world stays downloadable even though the optional
        # browser cache export failed afterwards.
        self.assertEqual(
            finished["artifacts"][0],
            {
                "name": "output",
                "path": "runs/world-out.json",
                "kind": "file",
                "available": True,
                "bytes": 21,
            },
        )
        self.assertEqual(
            manager.artifact_path(submitted["id"], 0).read_text(encoding="utf-8"),
            '{"schema_version": 1}',
        )

    def test_generate_chains_a_browser_cache_export(self) -> None:
        manager = self.manager()
        config = self.root / "runs" / "configs" / "world.yaml"
        config.parent.mkdir()
        config.write_text("config_version: 2\nmesh: {}\n", encoding="utf-8")
        commands: list[list[str]] = []

        def spawn(job: WebJob, command: list[str]) -> int:
            commands.append(list(command))
            target = Path(command[command.index("--output") + 1])
            if command[3] == "generate":
                target.write_text('{"schema_version": 1}', encoding="utf-8")
            else:
                target.mkdir(parents=True, exist_ok=True)
                (target / "manifest.json").write_text("staged", encoding="utf-8")
            return 0

        with (
            patch.object(manager, "_spawn", side_effect=spawn),
            patch.object(manager, "_validate_debug_cache", return_value=None),
        ):
            submitted = manager.submit(
                "generate",
                {
                    "output": "runs/world-out.json",
                    "open_in_web": True,
                    "debug_output": "runs/debug",
                    "debug_vtu": False,
                },
            )
            finished = wait_for_job(manager, submitted["id"])

        self.assertEqual(finished["status"], "succeeded", finished["log"])
        self.assertEqual(finished["cache_dir"], "runs/debug")
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][3], "generate")
        self.assertEqual(
            commands[1][:6],
            [
                sys.executable,
                "-m",
                "magic_geo",
                "export-debug",
                "--world",
                str(self.root / "runs" / "world-out.json"),
            ],
        )
        self.assertEqual(commands[1][-1], "--no-vtu")
        self.assertEqual(
            finished["artifacts"],
            [
                {
                    "name": "output",
                    "path": "runs/world-out.json",
                    "kind": "file",
                    "available": True,
                    "bytes": 21,
                },
                {
                    "name": "debug_output",
                    "path": "runs/debug",
                    "kind": "cache",
                    "available": False,
                },
            ],
        )
        self.assertEqual(
            (self.root / "runs" / "debug" / "manifest.json").read_text(encoding="utf-8"),
            "staged",
        )
        self.assertEqual(
            manager.artifact_path(submitted["id"], 0).read_text(encoding="utf-8"),
            '{"schema_version": 1}',
        )
