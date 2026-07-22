"""Rerun (.rrd) exporter tests.

:func:`magic_geo.debug_rerun.export_rerun_recording` is checked through two
observables: the statistics it returns, and the ``rr.log`` calls it makes. The
recording file itself is only checked for existence and non-emptiness — the SDK
buffers asynchronously, so a freshly written ``.rrd`` does not yet contain the
payload.

The ``rr.log`` spy deliberately asserts on entity paths (which the module owns
outright) and on component batches read back through the public ``as_arrow_array``
accessor. It does not assume ``rr.Scalars`` over ``rr.Scalar`` or ``set_time``
over ``set_time_sequence``; the module branches on both because the SDK drifts.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import SkipTest, TestCase
from unittest.mock import patch

try:
    import rerun  # noqa: F401
except ImportError as exc:  # rerun-sdk is an undeclared, optional visualisation extra.
    raise SkipTest(f"rerun export tests require rerun-sdk: {exc}") from exc

from support import worlds

from magic_geo import debug_rerun
from magic_geo.debug_rerun import export_rerun_recording

NO_CELLS_MESSAGE = (
    r"^world payload has no cells; generate with output\.include_cells enabled$"
)


def _log_spy():
    """Patch ``rr.log`` with a recording wrapper that still calls the real one."""
    return patch.object(debug_rerun.rr, "log", wraps=debug_rerun.rr.log)


def _paths(spy) -> list[str]:
    return [call.args[0] for call in spy.call_args_list]


def _archetypes(spy, path: str) -> list[object]:
    return [call.args[1] for call in spy.call_args_list if call.args[0] == path]


def _kwargs(spy, path: str) -> list[dict]:
    return [call.kwargs for call in spy.call_args_list if call.args[0] == path]


def _packed_colors(mesh) -> list[int]:
    """Per-vertex colors of a logged ``Mesh3D`` as packed RGBA integers."""
    return mesh.vertex_colors.as_arrow_array().to_pylist()


def _scalar_value(archetype) -> float:
    """The single value carried by a logged ``Scalars``/``Scalar`` archetype."""
    batch = getattr(archetype, "scalars", None)
    if batch is None:  # pragma: no cover - older rerun-sdk naming
        batch = archetype.scalar
    return batch.as_arrow_array().to_pylist()[0]


def _square_ring(lat_deg: float, lon_deg: float) -> list[list[float]]:
    """A four-corner ``[lat, lon]`` ring around ``(lat_deg, lon_deg)``."""
    return [
        [lat_deg + 1.0, lon_deg - 1.0],
        [lat_deg + 1.0, lon_deg + 1.0],
        [lat_deg - 1.0, lon_deg + 1.0],
        [lat_deg - 1.0, lon_deg - 1.0],
    ]


def _cell(cell_id: int, lat_deg: float, lon_deg: float, elevation_m: float) -> dict:
    """A minimal ringed cell of the shape the exporter triangulates."""
    return {
        "id": cell_id,
        "lat_deg": lat_deg,
        "lon_deg": lon_deg,
        "elevation_m": elevation_m,
        "boundary_ring": _square_ring(lat_deg, lon_deg),
    }


def _three_cells() -> list[dict]:
    return [
        _cell(0, 0.0, 0.0, -1200.0),
        _cell(1, 12.0, 34.0, 250.0),
        _cell(2, -25.0, -80.0, 1800.0),
    ]


def _complete_edge() -> dict:
    return {
        "plate_boundary": True,
        "boundary_segment_start_lat_deg": 1.5,
        "boundary_segment_start_lon_deg": 2.5,
        "boundary_segment_end_lat_deg": 3.5,
        "boundary_segment_end_lon_deg": 4.5,
    }


class ExportRerunRecordingTests(TestCase):
    def test_payload_without_cells_raises_before_writing(self) -> None:
        for label, payload in (
            ("missing key", {}),
            ("empty list", {"cells": []}),
            ("null", {"cells": None}),
            ("mapping keyed by id", {"cells": {"0": _cell(0, 0.0, 0.0, 1.0)}}),
        ):
            with self.subTest(payload=label), TemporaryDirectory() as tmp:
                target = Path(tmp) / "world.rrd"
                with self.assertRaisesRegex(ValueError, NO_CELLS_MESSAGE):
                    export_rerun_recording(payload, target)
                self.assertFalse(
                    target.exists(), "no recording may be written for a cell-less payload"
                )

    def test_ringed_cells_without_histories_triangulate_into_a_single_stage_free_frame(self) -> None:
        cells = _three_cells()
        ring_len = len(cells[0]["boundary_ring"])
        with TemporaryDirectory() as tmp, _log_spy() as spy:
            target = Path(tmp) / "world.rrd"

            stats = export_rerun_recording({"cells": cells}, target)

            self.assertEqual(
                stats,
                {
                    "output": str(target),
                    "vertices": len(cells) * (1 + ring_len),
                    "triangles": len(cells) * ring_len,
                    "stages": 0,
                    "feedback_scalars": 0,
                    "plate_boundary_segments": 0,
                },
            )
            # Exactly one frame: no history means no stage timeline to scrub.
            self.assertEqual(_paths(spy), ["world/mesh"])
            self.assertEqual(
                len(_packed_colors(_archetypes(spy, "world/mesh")[0])),
                len(cells) * (1 + ring_len),
            )
            self.assertTrue(target.exists(), f"{target} was not written")
            self.assertGreater(target.stat().st_size, 0, f"{target} is empty")

    def test_cells_without_a_usable_boundary_ring_contribute_no_geometry(self) -> None:
        good = _cell(0, 0.0, 0.0, 10.0)
        ring_len = len(good["boundary_ring"])
        # A tuple has a usable length, so only the ``isinstance(ring, list)`` guard
        # can reject it; a two-corner ring can only be rejected by ``len(ring) < 3``.
        degenerate_rings = (
            ("absent", None),
            ("empty list", []),
            ("two corners", [[1.0, 1.0], [2.0, 2.0]]),
            ("tuple of four corners", tuple(_square_ring(40.0, 40.0))),
            ("mapping", {"lat": 1.0, "lon": 2.0, "alt": 3.0}),
        )
        for label, ring in degenerate_rings:
            with self.subTest(ring=label), TemporaryDirectory() as tmp, _log_spy() as spy:
                skipped = _cell(1, 40.0, 40.0, 20.0)
                if ring is None:
                    del skipped["boundary_ring"]
                else:
                    skipped["boundary_ring"] = ring
                target = Path(tmp) / "world.rrd"

                stats = export_rerun_recording({"cells": [good, skipped]}, target)

                self.assertEqual(stats["vertices"], 1 + ring_len)
                self.assertEqual(stats["triangles"], ring_len)
                # The skipped cell must not reach the logged mesh either.
                self.assertEqual(
                    len(_packed_colors(_archetypes(spy, "world/mesh")[0])), 1 + ring_len
                )

    def test_water_budget_history_records_become_per_stage_meshes_keyed_by_cell_id(self) -> None:
        cells = _three_cells()
        elevations = [-1200.0, 250.0, 1800.0]
        world = {
            "cells": cells,
            "hydrologic_water_budget_history": [
                {"cell_ids": [0, 1, 2], "elevation_m_by_cell": elevations},
                # Same elevations, cell ids reversed: the second stage must colour the
                # cells in the opposite order, which is only possible if the exporter
                # honours ``cell_ids`` instead of zipping positionally.
                {"cell_ids": [2, 1, 0], "elevation_m_by_cell": elevations},
            ],
        }
        with TemporaryDirectory() as tmp, _log_spy() as spy:
            target = Path(tmp) / "world.rrd"

            stats = export_rerun_recording(world, target)

            self.assertEqual(stats["stages"], 2)
            self.assertEqual(stats["vertices"], len(cells) * 5)
            self.assertEqual(stats["triangles"], len(cells) * 4)
            meshes = _archetypes(spy, "world/mesh")
            self.assertEqual(_paths(spy), ["world/mesh", "world/mesh"])
            self.assertEqual(len(meshes), stats["stages"])

            first, second = (_packed_colors(mesh) for mesh in meshes)
            # The 2nd/98th percentile window over three values is [min, median], so the
            # minimum cell takes the low colour and the other two clamp to the high one.
            low, high = first[0], first[5]
            self.assertNotEqual(low, high, "the colour ramp collapsed to a single colour")
            self.assertEqual(first, [low] * 5 + [high] * 10)
            self.assertEqual(second, [high] * 10 + [low] * 5)

    def test_feedback_ledger_logs_every_finite_number_and_both_boolean_states(self) -> None:
        world = {
            "cells": _three_cells(),
            "earth_system_feedback_history": [
                {
                    "sea_level_m": 1.0,
                    "erosion_applied": True,
                    "crust_transport_applied": False,
                    "cell_count": 7,
                    "stage": "erosion",
                    "not_a_number": float("nan"),
                    "runaway": float("inf"),
                    "collapse": float("-inf"),
                },
                ["records that are not mappings are skipped entirely"],
            ],
        }
        with TemporaryDirectory() as tmp, _log_spy() as spy:
            target = Path(tmp) / "world.rrd"

            stats = export_rerun_recording(world, target)

            # Two floats/ints and two booleans are logged; the string and the three
            # non-finite floats are not, and the list record contributes nothing.
            self.assertEqual(stats["feedback_scalars"], 4)
            self.assertEqual(stats["stages"], 0)
            self.assertEqual(
                _paths(spy),
                [
                    "world/mesh",
                    "feedback/sea_level_m",
                    "feedback/erosion_applied",
                    "feedback/crust_transport_applied",
                    "feedback/cell_count",
                ],
            )
            self.assertEqual(_scalar_value(_archetypes(spy, "feedback/sea_level_m")[0]), 1.0)
            self.assertEqual(_scalar_value(_archetypes(spy, "feedback/cell_count")[0]), 7.0)
            self.assertEqual(_scalar_value(_archetypes(spy, "feedback/erosion_applied")[0]), 1.0)
            self.assertEqual(
                _scalar_value(_archetypes(spy, "feedback/crust_transport_applied")[0]), 0.0
            )

    def test_plate_boundary_edges_need_all_four_segment_coordinates(self) -> None:
        incomplete = {
            "plate_boundary": True,
            "boundary_segment_start_lat_deg": 1.5,
            "boundary_segment_start_lon_deg": 2.5,
        }
        interior = {
            "plate_boundary": False,
            "boundary_segment_start_lat_deg": 9.0,
            "boundary_segment_start_lon_deg": 9.0,
            "boundary_segment_end_lat_deg": 9.5,
            "boundary_segment_end_lon_deg": 9.5,
        }
        world = {
            "cells": _three_cells(),
            "cell_adjacency_edges": [_complete_edge(), incomplete, interior],
        }
        with TemporaryDirectory() as tmp, _log_spy() as spy:
            target = Path(tmp) / "world.rrd"

            stats = export_rerun_recording(world, target)

            self.assertEqual(stats["plate_boundary_segments"], 1)
            self.assertEqual(_paths(spy), ["world/mesh", "world/plate_boundaries"])
            # Boundaries are stage-independent, so they must be logged as static data.
            self.assertEqual(_kwargs(spy, "world/plate_boundaries"), [{"static": True}])

    def test_plate_boundary_edges_with_unusable_coordinates_are_dropped(self) -> None:
        unusable = (
            ("null latitude", {"boundary_segment_start_lat_deg": None}),
            ("unparseable string", {"boundary_segment_end_lat_deg": "north"}),
            ("list instead of a number", {"boundary_segment_end_lon_deg": [4.5]}),
            ("end pair missing", {"boundary_segment_end_lat_deg": None, "boundary_segment_end_lon_deg": None}),
        )
        for label, override in unusable:
            with self.subTest(edge=label), TemporaryDirectory() as tmp, _log_spy() as spy:
                broken = _complete_edge()
                for key, value in override.items():
                    if label == "end pair missing":
                        del broken[key]
                    else:
                        broken[key] = value
                world = {
                    "cells": _three_cells(),
                    "cell_adjacency_edges": [broken, _complete_edge()],
                }
                target = Path(tmp) / "world.rrd"

                stats = export_rerun_recording(world, target)

                # The sibling edge is intact, so a zero here would mean the whole
                # boundary branch went inert rather than that ``broken`` was rejected.
                self.assertEqual(stats["plate_boundary_segments"], 1)
                self.assertEqual(_paths(spy), ["world/mesh", "world/plate_boundaries"])

    def test_world_without_plate_boundary_edges_logs_no_boundary_entity(self) -> None:
        interior = {
            "plate_boundary": False,
            "boundary_segment_start_lat_deg": 9.0,
            "boundary_segment_start_lon_deg": 9.0,
            "boundary_segment_end_lat_deg": 9.5,
            "boundary_segment_end_lon_deg": 9.5,
        }
        world = {"cells": _three_cells(), "cell_adjacency_edges": [interior, interior]}
        with TemporaryDirectory() as tmp, _log_spy() as spy:
            target = Path(tmp) / "world.rrd"

            stats = export_rerun_recording(world, target)

            self.assertEqual(stats["plate_boundary_segments"], 0)
            self.assertEqual(_paths(spy), ["world/mesh"])


class ExportRerunRecordingGeneratedWorldTests(TestCase):
    def test_generated_world_exports_every_history_stage_and_boundary_segment(self) -> None:
        world = worlds.cached_world_readonly("replay_128")  # Read-only: never mutated here.
        cells = world["cells"]
        rings = [
            cell["boundary_ring"]
            for cell in cells
            if isinstance(cell.get("boundary_ring"), list) and len(cell["boundary_ring"]) >= 3
        ]
        expected_vertices = sum(1 + len(ring) for ring in rings)
        expected_triangles = sum(len(ring) for ring in rings)
        expected_stages = len(world["hydrologic_water_budget_history"])
        edges = world["cell_adjacency_edges"]
        expected_segments = sum(
            1
            for edge in edges
            if edge.get("plate_boundary")
            and all(
                isinstance(edge.get(key), (int, float))
                for key in (
                    "boundary_segment_start_lat_deg",
                    "boundary_segment_start_lon_deg",
                    "boundary_segment_end_lat_deg",
                    "boundary_segment_end_lon_deg",
                )
            )
        )
        feedback = world["earth_system_feedback_history"]
        expected_scalars = sum(
            1
            for record in feedback
            for value in record.values()
            if isinstance(value, bool)
            or (isinstance(value, (int, float)) and value == value and abs(value) != float("inf"))
        )
        total_feedback_values = sum(len(record) for record in feedback)

        # Guard every expectation against silently collapsing to zero, which would
        # let a wholly inert exporter satisfy the equalities below.
        self.assertEqual(len(rings), len(cells), "every generated cell carries a usable ring")
        self.assertGreater(expected_triangles, len(cells), "rings have at least three corners")
        self.assertEqual(expected_vertices, len(rings) + expected_triangles)
        self.assertGreater(expected_stages, 0, "the replay world should carry a water budget history")
        self.assertGreater(expected_segments, 0, "plate boundaries should exist in a plate world")
        self.assertLess(expected_segments, len(edges), "interior edges must not be counted")
        self.assertGreater(expected_scalars, 0, "the feedback ledger should carry numbers")
        self.assertLess(
            expected_scalars, total_feedback_values, "non-numeric ledger fields must be skipped"
        )

        with TemporaryDirectory() as tmp, _log_spy() as spy:
            target = Path(tmp) / "world.rrd"

            stats = export_rerun_recording(world, target)

            self.assertEqual(stats["stages"], expected_stages)
            self.assertEqual(stats["vertices"], expected_vertices)
            self.assertEqual(stats["triangles"], expected_triangles)
            self.assertEqual(stats["plate_boundary_segments"], expected_segments)
            self.assertEqual(stats["feedback_scalars"], expected_scalars)
            self.assertEqual(stats["output"], str(target))
            # The counters must reflect real log traffic, not just loop arithmetic.
            self.assertEqual(len(_archetypes(spy, "world/mesh")), expected_stages)
            self.assertEqual(len(_archetypes(spy, "world/plate_boundaries")), 1)
            self.assertEqual(
                sum(1 for path in _paths(spy) if path.startswith("feedback/")), expected_scalars
            )
            self.assertTrue(target.exists(), f"{target} was not written")
            self.assertGreater(target.stat().st_size, 0, f"{target} is empty")
