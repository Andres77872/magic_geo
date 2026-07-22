"""Calibration ensemble manifests, grouped fit arithmetic, and reader guards.

``tests/test_calibration.py`` drives the ensemble through the CLI on a healthy
matrix; everything here takes the rejecting path instead. The manifest cases
mutate exactly one field of a manifest that is asserted to load cleanly, and
the evaluation cases replace ``world_factory`` with a stub so the grouped
coverage arithmetic can be pinned exactly without generating any world.
"""

from __future__ import annotations

import json
import math
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from zipfile import ZIP_DEFLATED, ZipFile

from magic_geo.calibration import (
    CalibrationError,
    _hydrorivers_archive_summary,
    _iter_dbf_numeric_records,
    _read_dbf_numeric_columns_from_bytes,
)
from magic_geo.config import WorldConfig
from magic_geo.ensemble_calibration import (
    ENSEMBLE_REPORT_TYPE,
    ENSEMBLE_SCHEMA_VERSION,
    MAX_ENSEMBLE_MEMBER_COUNT,
    evaluate_calibration_ensemble,
    load_calibration_ensemble_manifest,
    write_calibration_ensemble_markdown,
)
from magic_geo.scaling import HACK_FIT_MINIMUM_BASIN_AREA_KM2

from support.shapefiles import write_dbf_table

_DROP = object()

_BASE_MEMBER: dict[str, Any] = {
    "id": "member_a",
    "seed": 11,
    "cell_count": 128,
    "groups": ["reference"],
}

_BASE_MANIFEST: dict[str, Any] = {
    "schema_version": 1,
    "name": "unit_matrix",
    "members": [deepcopy(_BASE_MEMBER)],
}


def _encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=repr)


def _tampered(
    testcase: TestCase,
    base: dict[str, Any],
    overrides: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    """A deep copy of ``base`` with ``overrides`` applied, guarded against no-ops.

    A hardcoded tamper value that happens to equal the fixture's own value
    makes the case silently inert, so every override must actually change
    something and every ``_DROP`` must actually remove a present key. The
    comparison is on the JSON encoding rather than on ``==`` because the
    manifest round-trips through JSON, where ``128.0`` and ``True`` are real
    tampers of ``128`` and ``1`` even though Python calls them equal.
    """
    payload = deepcopy(base)
    for key, value in overrides.items():
        if value is _DROP:
            testcase.assertIn(key, payload, f"{label}: '{key}' is already absent")
            payload.pop(key)
            continue
        current = payload.get(key, _DROP)
        testcase.assertFalse(
            current is not _DROP and _encoded(current) == _encoded(value),
            f"{label}: overriding '{key}' with the value it already holds is a no-op",
        )
        payload[key] = value
    return payload


def _member(testcase: TestCase, **overrides: Any) -> dict[str, Any]:
    return _tampered(testcase, _BASE_MEMBER, overrides, "member")


def _manifest(testcase: TestCase, **overrides: Any) -> dict[str, Any]:
    return _tampered(testcase, _BASE_MANIFEST, overrides, "manifest")


def _write_manifest(root: Path, payload: Any, name: str = "matrix.json") -> Path:
    path = root / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class EnsembleManifestTests(TestCase):
    """``load_calibration_ensemble_manifest`` normalization and rejections."""

    def _assert_error(self, path: Path, expected: str) -> None:
        with self.assertRaises(CalibrationError) as caught:
            load_calibration_ensemble_manifest(path)
        self.assertEqual(str(caught.exception), expected)

    def test_valid_manifest_is_normalized(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = _write_manifest(
                root,
                {
                    "schema_version": 1,
                    "name": "  unit_matrix  ",
                    "members": [
                        {
                            "id": "  member_b  ",
                            "seed": 0,
                            "cell_count": 128,
                            "groups": ["zeta", " alpha ", "alpha"],
                        },
                        {"id": "member_a", "seed": 2**64 - 1, "cell_count": 256},
                    ],
                },
            )

            manifest = load_calibration_ensemble_manifest(path)

            self.assertEqual(
                manifest,
                {
                    "schema_version": ENSEMBLE_SCHEMA_VERSION,
                    "name": "unit_matrix",
                    "members": [
                        {
                            "id": "member_b",
                            "seed": 0,
                            "cell_count": 128,
                            "groups": ["alpha", "zeta"],
                        },
                        {
                            "id": "member_a",
                            "seed": 2**64 - 1,
                            "cell_count": 256,
                            "groups": [],
                        },
                    ],
                },
            )

    def test_unreadable_and_non_object_manifests_are_refused(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            control = _write_manifest(root, _BASE_MANIFEST, "control.json")
            self.assertEqual(
                load_calibration_ensemble_manifest(control)["name"], "unit_matrix"
            )

            truncated = root / "truncated.json"
            truncated.write_text('{"schema_version": 1,', encoding="utf-8")
            self._assert_error(
                truncated, f"invalid calibration ensemble JSON: {truncated}"
            )

            for label, payload in [
                ("list", [_BASE_MANIFEST]),
                ("string", "matrix"),
                ("null", None),
            ]:
                with self.subTest(payload=label):
                    path = _write_manifest(root, payload, f"{label}.json")
                    self._assert_error(
                        path, "calibration ensemble manifest must be an object"
                    )

    def test_manifest_level_fields_are_validated(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            control = _write_manifest(root, _manifest(self), "control.json")
            self.assertEqual(len(load_calibration_ensemble_manifest(control)["members"]), 1)

            oversized = [
                {"id": f"member_{index}", "seed": index, "cell_count": 128}
                for index in range(MAX_ENSEMBLE_MEMBER_COUNT + 1)
            ]
            cases: list[tuple[str, dict[str, Any], str]] = [
                (
                    "schema_version_missing",
                    {"schema_version": _DROP},
                    f"calibration ensemble schema_version must be {ENSEMBLE_SCHEMA_VERSION}",
                ),
                (
                    "schema_version_future",
                    {"schema_version": 2},
                    f"calibration ensemble schema_version must be {ENSEMBLE_SCHEMA_VERSION}",
                ),
                (
                    "schema_version_text",
                    {"schema_version": "1"},
                    f"calibration ensemble schema_version must be {ENSEMBLE_SCHEMA_VERSION}",
                ),
                (
                    "name_missing",
                    {"name": _DROP},
                    "calibration ensemble manifest requires non-empty 'name'",
                ),
                (
                    "name_blank",
                    {"name": "   "},
                    "calibration ensemble manifest requires non-empty 'name'",
                ),
                (
                    "name_not_text",
                    {"name": 7},
                    "calibration ensemble manifest requires non-empty 'name'",
                ),
                (
                    "members_missing",
                    {"members": _DROP},
                    "calibration ensemble manifest requires a non-empty 'members' list",
                ),
                (
                    "members_empty",
                    {"members": []},
                    "calibration ensemble manifest requires a non-empty 'members' list",
                ),
                (
                    "members_mapping",
                    {"members": {"member_a": {"seed": 11, "cell_count": 128}}},
                    "calibration ensemble manifest requires a non-empty 'members' list",
                ),
                (
                    "members_over_limit",
                    {"members": oversized},
                    f"calibration ensemble cannot exceed {MAX_ENSEMBLE_MEMBER_COUNT} members",
                ),
            ]
            for label, overrides, expected in cases:
                with self.subTest(case=label):
                    path = _write_manifest(root, _manifest(self, **overrides), f"{label}.json")
                    self._assert_error(path, expected)

    def test_member_records_are_validated(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            control = _write_manifest(root, _manifest(self), "control.json")
            self.assertEqual(
                load_calibration_ensemble_manifest(control)["members"][0]["id"], "member_a"
            )

            cases: list[tuple[str, Any, str]] = [
                ("not_an_object", ["member_a", 11, 128], "calibration ensemble member 0 must be an object"),
                ("id_missing", _member(self, id=_DROP), "calibration ensemble member 0 requires non-empty 'id'"),
                ("id_blank", _member(self, id=" "), "calibration ensemble member 0 requires non-empty 'id'"),
                ("id_not_text", _member(self, id=3), "calibration ensemble member 0 requires non-empty 'id'"),
                (
                    "seed_missing",
                    _member(self, seed=_DROP),
                    "calibration ensemble member 0 seed must be an unsigned 64-bit integer",
                ),
                (
                    "seed_bool",
                    _member(self, seed=True),
                    "calibration ensemble member 0 seed must be an unsigned 64-bit integer",
                ),
                (
                    "seed_text",
                    _member(self, seed="11"),
                    "calibration ensemble member 0 seed must be an unsigned 64-bit integer",
                ),
                (
                    "seed_float",
                    _member(self, seed=11.5),
                    "calibration ensemble member 0 seed must be an unsigned 64-bit integer",
                ),
                (
                    "seed_negative",
                    _member(self, seed=-1),
                    "calibration ensemble member 0 seed must be an unsigned 64-bit integer",
                ),
                (
                    "seed_overflow",
                    _member(self, seed=2**64),
                    "calibration ensemble member 0 seed must be an unsigned 64-bit integer",
                ),
                (
                    "cell_count_missing",
                    _member(self, cell_count=_DROP),
                    "calibration ensemble member 0 cell_count must be an integer of at least 128",
                ),
                (
                    "cell_count_bool",
                    _member(self, cell_count=True),
                    "calibration ensemble member 0 cell_count must be an integer of at least 128",
                ),
                (
                    "cell_count_float",
                    _member(self, cell_count=128.0),
                    "calibration ensemble member 0 cell_count must be an integer of at least 128",
                ),
                (
                    "cell_count_below_floor",
                    _member(self, cell_count=127),
                    "calibration ensemble member 0 cell_count must be an integer of at least 128",
                ),
                (
                    "groups_not_a_list",
                    _member(self, groups="reference"),
                    "calibration ensemble member 0 groups must be non-empty strings",
                ),
                (
                    "groups_blank_entry",
                    _member(self, groups=["reference", "  "]),
                    "calibration ensemble member 0 groups must be non-empty strings",
                ),
                (
                    "groups_non_text_entry",
                    _member(self, groups=["reference", 4]),
                    "calibration ensemble member 0 groups must be non-empty strings",
                ),
                (
                    "groups_reserved_all",
                    _member(self, groups=[" all "]),
                    "calibration ensemble member 0 group name 'all' is reserved",
                ),
            ]
            for label, member, expected in cases:
                with self.subTest(case=label):
                    path = _write_manifest(
                        root, _manifest(self, members=[member]), f"{label}.json"
                    )
                    self._assert_error(path, expected)

    def test_duplicate_member_ids_are_refused_after_stripping(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            distinct = _write_manifest(
                root,
                _manifest(
                    self,
                    members=[
                        _member(self, id="dup"),
                        _member(self, id="other", seed=12),
                    ],
                ),
                "distinct.json",
            )
            self.assertEqual(
                [member["id"] for member in load_calibration_ensemble_manifest(distinct)["members"]],
                ["dup", "other"],
            )

            path = _write_manifest(
                root,
                _manifest(
                    self,
                    members=[
                        _member(self, id="dup"),
                        _member(self, id="  dup  ", seed=12),
                    ],
                ),
                "duplicate.json",
            )
            self._assert_error(path, "calibration ensemble duplicates member id 'dup'")

    def test_duplicate_seed_cell_count_coordinates_are_refused(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reused_seed = _write_manifest(
                root,
                _manifest(
                    self,
                    members=[
                        _member(self, id="first"),
                        _member(self, id="second", cell_count=256),
                    ],
                ),
                "reused_seed.json",
            )
            self.assertEqual(len(load_calibration_ensemble_manifest(reused_seed)["members"]), 2)

            path = _write_manifest(
                root,
                _manifest(
                    self,
                    members=[
                        _member(self, id="first"),
                        _member(self, id="second"),
                    ],
                ),
                "duplicate_coordinate.json",
            )
            self._assert_error(
                path, "calibration ensemble duplicates seed/cell_count coordinate (11, 128)"
            )


def _stub_world(
    metrics: dict[str, float],
    *,
    cell_count: int,
    mesh_backend: str,
) -> dict[str, Any]:
    """The smallest world ``evaluate_calibration_targets`` will score."""
    return {
        "calibration_checks": [
            {"metric": metric, "value": value} for metric, value in metrics.items()
        ],
        "summary": {"cell_count": cell_count},
        "mesh_backend": mesh_backend,
    }


_MATRIX_TARGETS: list[dict[str, Any]] = [
    {
        "dataset": "alpha",
        "layer": "summary",
        "metric": "metric_a",
        "target_min": 0.0,
        "target_max": 1.0,
    },
    {
        "dataset": "alpha",
        "layer": "summary",
        "metric": "metric_c",
        "target_min": 0.0,
        "target_max": 1.0,
    },
    {
        "dataset": "beta",
        "layer": "summary",
        "metric": "metric_b",
        "target_min": 10.0,
        "target_max": 20.0,
    },
]

# "full" covers and passes every target, "half" is missing metric_b and fails
# metric_c, and "blank" covers nothing at all, so group "sparse" == {half, blank}
# has no evaluated value for metric_b anywhere. "half" fails metric_c by exactly
# half a target width so its mean score (0.5) differs from its pass fraction
# (1/3) -- a member whose out-of-range value scored 0.0 would make the two
# indistinguishable.
_MATRIX_MANIFEST: dict[str, Any] = {
    "schema_version": 1,
    "name": "grouped_matrix",
    "members": [
        {"id": "full", "seed": 11, "cell_count": 128, "groups": ["reference"]},
        {"id": "half", "seed": 22, "cell_count": 256, "groups": ["reference", "sparse"]},
        {"id": "blank", "seed": 33, "cell_count": 128, "groups": ["sparse"]},
    ],
}

_MATRIX_WORLDS: dict[int, dict[str, Any]] = {
    11: _stub_world(
        {"metric_a": 0.5, "metric_c": 0.25, "metric_b": 15.0},
        cell_count=130,
        mesh_backend="stub_full",
    ),
    22: _stub_world(
        {"metric_a": 0.5, "metric_c": 1.5},
        cell_count=260,
        mesh_backend="stub_half",
    ),
    33: _stub_world({}, cell_count=132, mesh_backend="stub_blank"),
}


class _RecordingFactory:
    """A ``world_factory`` that records the per-member config it was handed."""

    def __init__(self, worlds_by_seed: dict[int, dict[str, Any]]) -> None:
        self._worlds_by_seed = worlds_by_seed
        self.configs: list[tuple[int, int]] = []

    def __call__(self, config: WorldConfig) -> dict[str, Any]:
        self.configs.append((config.run.seed, config.mesh.cell_count))
        return deepcopy(self._worlds_by_seed[config.run.seed])


def _evaluate_matrix(
    base_config: WorldConfig | None = None,
) -> tuple[dict[str, Any], _RecordingFactory, list[tuple[int, int, str]]]:
    factory = _RecordingFactory(_MATRIX_WORLDS)
    progress: list[tuple[int, int, str]] = []
    report = evaluate_calibration_ensemble(
        WorldConfig() if base_config is None else base_config,
        deepcopy(_MATRIX_MANIFEST),
        deepcopy(_MATRIX_TARGETS),
        provenance={"matrix_sha256": "a" * 64},
        world_factory=factory,
        progress=lambda index, count, member: progress.append(
            (index, count, str(member["id"]))
        ),
    )
    return report, factory, progress


class EnsembleTargetValidationTests(TestCase):
    """``evaluate_calibration_ensemble`` rejects targets before generating."""

    def _assert_error(
        self,
        targets: list[Any],
        expected: str,
        *,
        manifest: dict[str, Any] | None = None,
    ) -> None:
        def refuse(config: WorldConfig) -> dict[str, Any]:
            raise AssertionError("world_factory must not run for a rejected manifest")

        with self.assertRaises(CalibrationError) as caught:
            evaluate_calibration_ensemble(
                WorldConfig(),
                deepcopy(_MATRIX_MANIFEST) if manifest is None else manifest,
                targets,
                world_factory=refuse,
            )
        self.assertEqual(str(caught.exception), expected)

    def test_target_records_are_validated_before_any_world_is_built(self) -> None:
        report, _factory, _progress = _evaluate_matrix()
        self.assertEqual(report["summary"]["target_count"], 3)

        base = _MATRIX_TARGETS[0]
        cases: list[tuple[str, list[Any], str]] = [
            ("empty", [], "calibration ensemble requires at least one target"),
            (
                "not_an_object",
                [["metric_a", 0.0, 1.0]],
                "calibration ensemble target 0 must be an object",
            ),
            (
                "metric_missing",
                [_tampered(self, base, {"metric": _DROP}, "target")],
                "calibration ensemble target 0 requires non-empty 'metric'",
            ),
            (
                "metric_blank",
                [_tampered(self, base, {"metric": "  "}, "target")],
                "calibration ensemble target 0 requires non-empty 'metric'",
            ),
            (
                "dataset_missing",
                [_tampered(self, base, {"dataset": _DROP}, "target")],
                "calibration ensemble target 0 requires non-empty 'dataset'",
            ),
            (
                "layer_not_text",
                [_tampered(self, base, {"layer": 5}, "target")],
                "calibration ensemble target 0 requires non-empty 'layer'",
            ),
            (
                "duplicate_metric",
                [base, _tampered(self, base, {"dataset": "gamma"}, "target")],
                "calibration ensemble duplicates target metric 'metric_a'",
            ),
            (
                "bounds_missing",
                [_tampered(self, base, {"target_max": _DROP}, "target")],
                "calibration ensemble target 'metric_a' requires numeric bounds",
            ),
            (
                "bounds_null",
                [_tampered(self, base, {"target_min": None}, "target")],
                "calibration ensemble target 'metric_a' requires numeric bounds",
            ),
            (
                "bounds_text",
                [_tampered(self, base, {"target_max": "wide"}, "target")],
                "calibration ensemble target 'metric_a' requires numeric bounds",
            ),
            (
                "bounds_infinite",
                [_tampered(self, base, {"target_max": math.inf}, "target")],
                "calibration ensemble target 'metric_a' bounds must be finite",
            ),
            (
                "bounds_nan",
                [_tampered(self, base, {"target_min": math.nan}, "target")],
                "calibration ensemble target 'metric_a' bounds must be finite",
            ),
            (
                "inverted",
                [_tampered(self, base, {"target_min": 2.0}, "target")],
                "calibration ensemble target 'metric_a' range is inverted",
            ),
        ]
        for label, targets, expected in cases:
            with self.subTest(case=label):
                self._assert_error(targets, expected)

    def test_manifest_must_be_loaded_and_normalized(self) -> None:
        expected = "calibration ensemble manifest was not loaded or normalized"
        cases: list[tuple[str, dict[str, Any]]] = [
            ("empty", {}),
            ("wrong_schema_version", {**deepcopy(_MATRIX_MANIFEST), "schema_version": 2}),
            ("members_not_a_list", {"schema_version": 1, "members": "member_a"}),
            ("members_missing", {"schema_version": 1, "name": "grouped_matrix"}),
        ]
        for label, manifest in cases:
            with self.subTest(case=label):
                self._assert_error(
                    deepcopy(_MATRIX_TARGETS), expected, manifest=manifest
                )


class EnsembleEvaluationTests(TestCase):
    """Per-member reports and the grouped coverage/fit arithmetic."""

    def test_member_reports_use_per_member_configs(self) -> None:
        base_config = WorldConfig()
        report, factory, progress = _evaluate_matrix(base_config)

        self.assertEqual(factory.configs, [(11, 128), (22, 256), (33, 128)])
        self.assertEqual(
            progress, [(0, 3, "full"), (1, 3, "half"), (2, 3, "blank")]
        )
        # Every member gets its own validated copy; the caller's config is intact.
        self.assertEqual(base_config.run.seed, WorldConfig().run.seed)
        self.assertEqual(base_config.mesh.cell_count, WorldConfig().mesh.cell_count)
        self.assertEqual(
            report["base_config"],
            {
                "name": base_config.run.name,
                "seed": base_config.run.seed,
                "mesh_backend": base_config.mesh.backend,
                "cell_count": base_config.mesh.cell_count,
            },
        )
        self.assertEqual(report["schema_version"], ENSEMBLE_SCHEMA_VERSION)
        self.assertEqual(report["report_type"], ENSEMBLE_REPORT_TYPE)
        self.assertEqual(report["name"], "grouped_matrix")
        self.assertEqual(report["provenance"]["matrix_sha256"], "a" * 64)
        self.assertEqual(len(report["provenance"]["base_config_sha256"]), 64)

        members = {member["id"]: member for member in report["members"]}
        self.assertEqual(list(members), ["full", "half", "blank"])
        self.assertEqual(members["half"]["seed"], 22)
        self.assertEqual(members["half"]["requested_cell_count"], 256)
        self.assertEqual(members["half"]["generated_cell_count"], 260)
        self.assertEqual(members["half"]["mesh_backend"], "stub_half")
        self.assertEqual(members["half"]["groups"], ["all", "reference", "sparse"])
        self.assertEqual(members["blank"]["groups"], ["all", "sparse"])

        self.assertTrue(members["full"]["complete"])
        self.assertTrue(members["full"]["all_targets_passed"])
        self.assertEqual(members["full"]["pass_count"], 3)
        self.assertEqual(members["full"]["pass_fraction"], 1.0)
        self.assertEqual(members["full"]["mean_score"], 1.0)
        self.assertEqual(members["full"]["missing_world_metrics"], [])

        self.assertFalse(members["half"]["complete"])
        self.assertFalse(members["half"]["all_targets_passed"])
        self.assertEqual(members["half"]["target_count"], 3)
        # metric_a passes, metric_c is out of range, metric_b is not reported.
        self.assertEqual(members["half"]["pass_count"], 1)
        self.assertEqual(members["half"]["pass_fraction"], 0.333333)
        # metric_c = 1.5 sits half a target width above the ceiling, so it still
        # scores 0.5: (1.0 + 0.5 + 0.0) / 3 is the mean score, not the 1/3 pass
        # fraction, and the two fields cannot be confused for one another.
        self.assertEqual(members["half"]["mean_score"], 0.5)
        self.assertNotEqual(
            members["half"]["mean_score"], members["half"]["pass_fraction"]
        )
        self.assertEqual(members["half"]["missing_world_metrics"], ["metric_b"])

        self.assertFalse(members["blank"]["complete"])
        self.assertEqual(members["blank"]["pass_count"], 0)
        self.assertEqual(
            members["blank"]["missing_world_metrics"],
            ["metric_a", "metric_b", "metric_c"],
        )

    def test_overall_metric_and_dataset_fit(self) -> None:
        report, _factory, _progress = _evaluate_matrix()

        self.assertEqual(
            report["summary"],
            {
                "member_count": 3,
                "group_count": 2,
                "target_count": 3,
                "dataset_count": 2,
                "complete_member_count": 1,
                "complete_member_fraction": 0.333333,
                "all_targets_passed_member_count": 1,
                "all_targets_passed_member_fraction": 0.333333,
                "reference_matrix_complete": False,
                "reference_matrix_all_passed": False,
            },
        )

        metrics = {metric["metric"]: metric for metric in report["metrics"]}
        self.assertEqual([metric["metric"] for metric in report["metrics"]], ["metric_a", "metric_c", "metric_b"])
        self.assertEqual(
            metrics["metric_a"],
            {
                "metric": "metric_a",
                "dataset": "alpha",
                "layer": "summary",
                "target_min": 0.0,
                "target_max": 1.0,
                "member_count": 3,
                "evaluated_member_count": 2,
                "coverage_fraction": 0.666667,
                "pass_count": 2,
                "pass_fraction": 0.666667,
                "value_min": 0.5,
                "value_max": 0.5,
                "value_mean": 0.5,
            },
        )
        self.assertEqual(metrics["metric_c"]["pass_count"], 1)
        # Both members report metric_c but only one passes it, so coverage counts
        # evaluated members while the pass fraction counts passing ones.
        self.assertEqual(metrics["metric_c"]["evaluated_member_count"], 2)
        self.assertEqual(metrics["metric_c"]["coverage_fraction"], 0.666667)
        self.assertEqual(metrics["metric_c"]["pass_fraction"], 0.333333)
        self.assertEqual(metrics["metric_c"]["value_min"], 0.25)
        self.assertEqual(metrics["metric_c"]["value_max"], 1.5)
        self.assertEqual(metrics["metric_c"]["value_mean"], 0.875)
        self.assertEqual(metrics["metric_b"]["evaluated_member_count"], 1)
        self.assertEqual(metrics["metric_b"]["coverage_fraction"], 0.333333)
        self.assertEqual(metrics["metric_b"]["value_mean"], 15.0)

        datasets = {dataset["dataset"]: dataset for dataset in report["datasets"]}
        self.assertEqual([dataset["dataset"] for dataset in report["datasets"]], ["alpha", "beta"])
        self.assertEqual(
            datasets["alpha"],
            {
                "dataset": "alpha",
                "metrics": ["metric_a", "metric_c"],
                "target_count": 2,
                "member_count": 3,
                "complete_member_count": 2,
                "coverage_fraction": 0.666667,
                "all_metrics_passed_member_count": 1,
                "all_metrics_passed_member_fraction": 0.333333,
            },
        )
        self.assertEqual(datasets["beta"]["target_count"], 1)
        self.assertEqual(datasets["beta"]["complete_member_count"], 1)
        self.assertEqual(datasets["beta"]["all_metrics_passed_member_count"], 1)

    def test_group_scopes_cover_a_group_with_no_evaluated_metric(self) -> None:
        report, _factory, _progress = _evaluate_matrix()

        groups = {group["name"]: group for group in report["groups"]}
        self.assertEqual([group["name"] for group in report["groups"]], ["reference", "sparse"])
        self.assertNotIn("all", groups)

        reference = groups["reference"]
        self.assertEqual(reference["member_ids"], ["full", "half"])
        self.assertEqual(reference["member_count"], 2)
        self.assertEqual(reference["complete_member_count"], 1)
        self.assertEqual(reference["complete_member_fraction"], 0.5)
        self.assertEqual(reference["all_targets_passed_member_count"], 1)
        self.assertEqual(reference["all_targets_passed_member_fraction"], 0.5)
        self.assertFalse(reference["all_members_complete"])
        self.assertFalse(reference["all_members_passed"])

        sparse = groups["sparse"]
        self.assertEqual(sparse["member_ids"], ["half", "blank"])
        self.assertEqual(sparse["complete_member_count"], 0)
        self.assertEqual(sparse["complete_member_fraction"], 0.0)
        self.assertEqual(sparse["all_targets_passed_member_count"], 0)

        sparse_metrics = {metric["metric"]: metric for metric in sparse["metrics"]}
        self.assertEqual(sparse_metrics["metric_a"]["evaluated_member_count"], 1)
        self.assertEqual(sparse_metrics["metric_a"]["coverage_fraction"], 0.5)
        # "half" reports metric_c but fails it, so within this group coverage and
        # the pass fraction disagree.
        self.assertEqual(sparse_metrics["metric_c"]["evaluated_member_count"], 1)
        self.assertEqual(sparse_metrics["metric_c"]["coverage_fraction"], 0.5)
        self.assertEqual(sparse_metrics["metric_c"]["pass_count"], 0)
        self.assertEqual(sparse_metrics["metric_c"]["pass_fraction"], 0.0)
        # Neither sparse member reports metric_b, so the whole group is unevaluated.
        self.assertEqual(sparse_metrics["metric_b"]["member_count"], 2)
        self.assertEqual(sparse_metrics["metric_b"]["evaluated_member_count"], 0)
        self.assertEqual(sparse_metrics["metric_b"]["coverage_fraction"], 0.0)
        self.assertEqual(sparse_metrics["metric_b"]["pass_count"], 0)
        self.assertEqual(sparse_metrics["metric_b"]["pass_fraction"], 0.0)
        self.assertIsNone(sparse_metrics["metric_b"]["value_min"])
        self.assertIsNone(sparse_metrics["metric_b"]["value_max"])
        self.assertIsNone(sparse_metrics["metric_b"]["value_mean"])

        sparse_datasets = {dataset["dataset"]: dataset for dataset in sparse["datasets"]}
        self.assertEqual(sparse_datasets["beta"]["complete_member_count"], 0)
        self.assertEqual(sparse_datasets["beta"]["coverage_fraction"], 0.0)
        self.assertEqual(sparse_datasets["beta"]["all_metrics_passed_member_count"], 0)
        self.assertEqual(sparse_datasets["beta"]["all_metrics_passed_member_fraction"], 0.0)
        self.assertEqual(sparse_datasets["alpha"]["complete_member_count"], 1)
        self.assertEqual(sparse_datasets["alpha"]["all_metrics_passed_member_count"], 0)

    def test_all_members_flags_are_true_for_a_uniform_matrix(self) -> None:
        manifest = {
            "schema_version": 1,
            "name": "uniform_matrix",
            "members": [
                {"id": "first", "seed": 11, "cell_count": 128, "groups": []},
                {"id": "second", "seed": 22, "cell_count": 128, "groups": []},
            ],
        }
        factory = _RecordingFactory(
            {
                11: _stub_world({"metric_a": 0.1}, cell_count=128, mesh_backend="stub"),
                22: _stub_world({"metric_a": 0.2}, cell_count=128, mesh_backend="stub"),
            }
        )

        report = evaluate_calibration_ensemble(
            WorldConfig(),
            manifest,
            [_MATRIX_TARGETS[0]],
            world_factory=factory,
        )

        self.assertEqual(report["groups"], [])
        self.assertEqual(report["summary"]["group_count"], 0)
        self.assertTrue(report["summary"]["reference_matrix_complete"])
        self.assertTrue(report["summary"]["reference_matrix_all_passed"])
        self.assertEqual(report["summary"]["complete_member_fraction"], 1.0)
        self.assertEqual(report["metrics"][0]["value_min"], 0.1)
        self.assertEqual(report["metrics"][0]["value_max"], 0.2)
        # (0.1 + 0.2) / 2 is 0.15000000000000002 in binary floating point, so this
        # pins the report's 12-decimal rounding rather than the raw mean.
        self.assertNotEqual((0.1 + 0.2) / 2, 0.15)
        self.assertEqual(report["metrics"][0]["value_mean"], 0.15)
        self.assertEqual(list(report["provenance"]), ["base_config_sha256"])

    def test_empty_member_list_zeroes_every_scope_without_dividing_by_zero(self) -> None:
        """``evaluate`` only requires ``members`` to be a list, not a non-empty one.

        ``load_calibration_ensemble_manifest`` refuses an empty matrix, but a
        caller assembling the manifest itself can still reach this, and every
        fraction in the report is a division by the member count.
        """

        def refuse(config: WorldConfig) -> dict[str, Any]:
            raise AssertionError("world_factory must not run for an empty member list")

        report = evaluate_calibration_ensemble(
            WorldConfig(),
            {"schema_version": 1, "name": "empty_matrix", "members": []},
            deepcopy(_MATRIX_TARGETS),
            world_factory=refuse,
        )

        self.assertEqual(report["members"], [])
        self.assertEqual(report["groups"], [])
        self.assertEqual(
            report["summary"],
            {
                "member_count": 0,
                "group_count": 0,
                "target_count": 3,
                "dataset_count": 2,
                "complete_member_count": 0,
                "complete_member_fraction": 0.0,
                "all_targets_passed_member_count": 0,
                "all_targets_passed_member_fraction": 0.0,
                # An empty matrix is vacuously "every member complete"; the report
                # must not claim the reference matrix was satisfied.
                "reference_matrix_complete": False,
                "reference_matrix_all_passed": False,
            },
        )
        self.assertEqual(
            report["metrics"][0],
            {
                "metric": "metric_a",
                "dataset": "alpha",
                "layer": "summary",
                "target_min": 0.0,
                "target_max": 1.0,
                "member_count": 0,
                "evaluated_member_count": 0,
                "coverage_fraction": 0.0,
                "pass_count": 0,
                "pass_fraction": 0.0,
                "value_min": None,
                "value_max": None,
                "value_mean": None,
            },
        )
        self.assertEqual(
            report["datasets"][0],
            {
                "dataset": "alpha",
                "metrics": ["metric_a", "metric_c"],
                "target_count": 2,
                "member_count": 0,
                "complete_member_count": 0,
                "coverage_fraction": 0.0,
                "all_metrics_passed_member_count": 0,
                "all_metrics_passed_member_fraction": 0.0,
            },
        )

    def test_provenance_hash_tracks_the_base_config(self) -> None:
        report, _factory, _progress = _evaluate_matrix()
        repeat, _repeat_factory, _repeat_progress = _evaluate_matrix()

        config_data = WorldConfig().model_dump(mode="python")
        self.assertNotEqual(config_data["run"]["name"], "other_run")
        config_data["run"]["name"] = "other_run"
        other, _other_factory, _other_progress = _evaluate_matrix(
            WorldConfig.model_validate(config_data)
        )

        digest = report["provenance"]["base_config_sha256"]
        self.assertEqual(len(digest), 64)
        # Same base config, same digest; a different base config, a different one.
        self.assertEqual(repeat["provenance"]["base_config_sha256"], digest)
        self.assertNotEqual(other["provenance"]["base_config_sha256"], digest)
        self.assertEqual(other["base_config"]["name"], "other_run")

    def test_member_generation_failure_names_the_member(self) -> None:
        manifest = deepcopy(_MATRIX_MANIFEST)

        def failing(config: WorldConfig) -> dict[str, Any]:
            if config.run.seed == 22:
                raise RuntimeError("native mesh backend unavailable")
            return deepcopy(_MATRIX_WORLDS[config.run.seed])

        with self.assertRaises(CalibrationError) as caught:
            evaluate_calibration_ensemble(
                WorldConfig(),
                manifest,
                deepcopy(_MATRIX_TARGETS),
                world_factory=failing,
            )
        self.assertEqual(
            str(caught.exception),
            "calibration ensemble member 'half' generation failed: "
            "native mesh backend unavailable",
        )

    def test_non_runtime_factory_errors_are_not_wrapped(self) -> None:
        def failing(config: WorldConfig) -> dict[str, Any]:
            raise ValueError("configuration rejected")

        with self.assertRaises(ValueError) as caught:
            evaluate_calibration_ensemble(
                WorldConfig(),
                deepcopy(_MATRIX_MANIFEST),
                deepcopy(_MATRIX_TARGETS),
                world_factory=failing,
            )
        self.assertEqual(str(caught.exception), "configuration rejected")


class EnsembleMarkdownTests(TestCase):
    def test_markdown_renders_group_scopes_and_unevaluated_metrics(self) -> None:
        report, _factory, _progress = _evaluate_matrix()
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "ensemble.md"

            write_calibration_ensemble_markdown(path, report)

            text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Calibration Ensemble Report"))
        # Newline-terminated so a longer value cannot satisfy the prefix.
        self.assertIn("- `member_count`: 3\n", text)
        self.assertIn("- `reference_matrix_all_passed`: False\n", text)
        self.assertIn("| full | 11 | 128 | 130 | all, reference | True | True | 1.000000 |", text)
        self.assertIn("| half | 22 | 256 | 260 | all, reference, sparse | False | False | 0.333333 |", text)
        self.assertIn("| all | beta | 1 | 3 | 1 | 1 | 0.333333 |", text)
        self.assertIn("| sparse | beta | 1 | 2 | 0 | 0 | 0.000000 |", text)
        self.assertIn("| metric_c | alpha | 3 | 2 | 1 | 0.333333 | 0.25 | 0.875 | 1.5 |", text)
        self.assertIn("| metric_b | beta | 3 | 1 | 1 | 0.333333 | 15.0 | 15.0 | 15.0 |", text)

    def test_markdown_writes_none_for_a_metric_no_member_evaluated(self) -> None:
        report, _factory, _progress = _evaluate_matrix()
        sparse = next(group for group in report["groups"] if group["name"] == "sparse")
        report["metrics"] = sparse["metrics"]
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ensemble.md"

            write_calibration_ensemble_markdown(path, report)

            text = path.read_text(encoding="utf-8")
        self.assertIn("| metric_b | beta | 2 | 0 | 0 | 0.000000 | None | None | None |", text)


_HYDRORIVERS_COLUMNS: dict[str, list[float | None]] = {
    "NEXT_DOWN": [0.0, 0.0, 0.0],
    "ENDORHEIC": [0.0, 0.0, 0.0],
    "ORD_CLAS": [1.0, 1.0, 1.0],
    "UPLAND_SKM": [1_000_000.0, 1_440_000.0, 1_690_000.0],
    "DIST_UP_KM": [2_000.0, 2_400.0, 2_600.0],
}


class CalibrationDbfColumnSelectionTests(TestCase):
    """Column-name guards shared by the buffered and streamed DBF readers."""

    def _dbf_bytes(self, root: Path) -> bytes:
        path = root / "table.dbf"
        write_dbf_table(path, {"ENDO": [0.0, 1.0], "SUB_AREA": [5.0, 7.0]})
        return path.read_bytes()

    def test_buffered_reader_rejects_blank_and_duplicate_column_names(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data = self._dbf_bytes(Path(temp_dir))

            self.assertEqual(
                _read_dbf_numeric_columns_from_bytes(data, "table.dbf", ["ENDO", "SUB_AREA"]),
                {"ENDO": [0.0, 1.0], "SUB_AREA": [5.0, 7.0]},
            )

            cases: list[tuple[str, list[str], str]] = [
                ("no_columns", [], "DBF numeric column names must be non-empty"),
                ("blank_column", ["ENDO", ""], "DBF numeric column names must be non-empty"),
                (
                    "duplicate_column",
                    ["ENDO", "SUB_AREA", "endo"],
                    "DBF numeric column names must be unique",
                ),
            ]
            for label, names, expected in cases:
                with self.subTest(case=label):
                    with self.assertRaises(CalibrationError) as caught:
                        _read_dbf_numeric_columns_from_bytes(data, "table.dbf", names)
                    self.assertEqual(str(caught.exception), expected)

    def test_streaming_reader_rejects_blank_and_duplicate_column_names(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data = self._dbf_bytes(Path(temp_dir))

            self.assertEqual(
                list(_iter_dbf_numeric_records(BytesIO(data), "table.dbf", ["SUB_AREA"])),
                [{"SUB_AREA": 5.0}, {"SUB_AREA": 7.0}],
            )

            cases: list[tuple[str, list[str], str]] = [
                ("no_columns", [], "DBF numeric column names must be non-empty"),
                ("blank_column", [""], "DBF numeric column names must be non-empty"),
                (
                    "duplicate_column",
                    ["SUB_AREA", "sub_area"],
                    "DBF numeric column names must be unique",
                ),
            ]
            for label, names, expected in cases:
                with self.subTest(case=label):
                    records = _iter_dbf_numeric_records(BytesIO(data), "table.dbf", names)
                    with self.assertRaises(CalibrationError) as caught:
                        list(records)
                    self.assertEqual(str(caught.exception), expected)


class HydroriversMinimumAreaTests(TestCase):
    def _archive(self, root: Path) -> Path:
        staging = root / "reaches.dbf"
        write_dbf_table(staging, _HYDRORIVERS_COLUMNS)
        archive_path = root / "hydrorivers.zip"
        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("reaches.dbf", staging.read_bytes())
        return archive_path

    def test_non_positive_minimum_upstream_area_is_refused(self) -> None:
        with TemporaryDirectory() as temp_dir:
            archive_path = self._archive(Path(temp_dir))

            summary = _hydrorivers_archive_summary(
                str(archive_path), HACK_FIT_MINIMUM_BASIN_AREA_KM2
            )
            self.assertEqual(summary["sample_network_count"], 3)
            self.assertAlmostEqual(summary["hack_fitted_exponent"], 0.5, places=9)
            self.assertEqual(
                summary["minimum_upstream_area_km2"], HACK_FIT_MINIMUM_BASIN_AREA_KM2
            )

            for label, minimum in [
                ("zero", 0.0),
                ("negative", -1.0),
                ("nan", math.nan),
                ("infinite", math.inf),
            ]:
                with self.subTest(case=label):
                    self.assertNotEqual(minimum, HACK_FIT_MINIMUM_BASIN_AREA_KM2)
                    with self.assertRaises(CalibrationError) as caught:
                        _hydrorivers_archive_summary(str(archive_path), minimum)
                    self.assertEqual(
                        str(caught.exception),
                        "HydroRIVERS minimum_upstream_area_km2 must be finite and positive",
                    )
