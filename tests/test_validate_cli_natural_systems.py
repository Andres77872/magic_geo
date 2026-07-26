"""Public ``validate`` CLI violations for indexed natural systems.

The ``validate`` command accumulates every complaint into one list and prints it
at a gate -- an early one after the schema checks, then one final one covering
everything else -- so a healthy generated world exercises only the passing side
of each check. These tests drive the reporting side: each case deep-copies the
canonical 128-cell world, breaks a derived quantity, and asserts the specific
``FAIL`` line the command owes that quantity -- the exact message, never just a
non-zero exit code, which a crash would also produce.

Every class re-runs the untampered world first (``test_untampered_world_validates``)
so each tampered assertion carries proof that the fixture itself is clean, and
every invocation asserts the command *reported* rather than *raised* so a check
that starts crashing is never mistaken for a check that reports. That guard has
to read ``result.exception``: ``CliRunner`` swallows an exception, still returns
``exit_code == 1`` and writes nothing at all, so a crash leaves no ``Traceback``
in the captured output to search for. Every tamper is also asserted to have
actually changed the world, so a hard-coded value that happens to equal the
generated one cannot pass as a tamper, and every expected message is matched
against a whole ``FAIL`` line rather than as a substring of the output.

Where several checks share a gate and cannot mask one another, one invocation
carries several tampers and asserts every resulting line -- the command is
supposed to report all of them, and asserting the whole set is a stronger claim
than asserting one. Where a check ``break``s out of a loop it shares with its
neighbours, the tamper stands alone.

Several record families fold every complaint into a single verdict:
``tectonic zone records invalid``, ``fault system records invalid``,
``watershed network diagnostics invalid`` and their neighbours are each appended
exactly once, from a flag a dozen separate branches can set. A ``subTest`` table
against such a verdict proves each branch is reachable and reported, and under
the real source the branch a case aims at is the one that fires -- it ``break``s
before its neighbours are evaluated, which is what the coverage shows. The
assertion still cannot name the branch: disable the branch a case targets and a
later one sets the same flag and prints the same line. Those tables say so, and
none of them claims more.

The slice covered here runs from the plate-motion summary roll-up through the
mesh LOD hierarchy, the spherical spatial index, cell geometry and adjacency
edges, tectonic zones, fault systems, lake basins and overflow histories,
watersheds and their cell-edge boundaries, and the hydrologic water budget.

Three checks in this slice are not assertable through the CLI, and the tests say
so where they touch them:

* ``watershed fitted Hack relation invalid`` fires only when ``fit_power_law``
  raises. It raises on three things, none of them reachable here. A non-finite
  fallback exponent cannot be written at all -- ``write_json`` serialises with
  ``allow_nan=False``. A non-positive or non-finite observation cannot survive
  the collector, which only appends areas above the fit minimum and lengths
  above zero. An overflowing fitted coefficient needs the fallback exponent to
  be used at all, which needs fewer than two observations; the 128-cell world
  contributes twenty-six, and an exponent large enough to overflow makes the
  per-watershed Hack replay divide by zero and crash first.
* A ``None`` (rather than merely non-list) zone family is measured with ``len``
  by the later cell-level zone check, so the command raises before its gate.
  The test uses a mapping instead.
* The guards around the fault-system and hydrologic-budget cell field
  conversions are shadowed by unguarded conversions of the same fields
  elsewhere; the tests aim their tamper at a cell those other readers skip.
"""

from __future__ import annotations

import copy
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from unittest import TestCase

from click.testing import Result
from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.io import write_json

from support import worlds
import pytest

# Exhaustive branch coverage of ``validate``: every case invokes the full CLI
# over a generated world. Deselect locally with -m "not slow".
pytestmark = pytest.mark.slow

WORLD_KEY = "replay_128"

Payload = dict[str, Any]
Tamper = Callable[[Payload], None]


def fail_lines(result: Result) -> list[str]:
    """Every ``FAIL`` line the command reported, whole lines, in order.

    The two gates print to different streams -- the early one to stdout, the
    final one to stderr -- so the mixed ``output`` is what has to be read.
    """
    return [line for line in result.output.splitlines() if line.startswith("FAIL ")]


def cells(payload: Payload) -> list[dict[str, Any]]:
    return payload["cells"]


def summary(payload: Payload) -> dict[str, Any]:
    return payload["summary"]


def first_edge_where(payload: Payload, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    """The first adjacency edge satisfying ``predicate``."""
    for edge in payload["cell_adjacency_edges"]:
        if predicate(edge):
            return edge
    raise AssertionError("the fixture world has no adjacency edge matching the predicate")


def cells_by_id(payload: Payload) -> dict[int, dict[str, Any]]:
    return {int(cell["id"]): cell for cell in payload["cells"]}


def lake_history_steps() -> list[dict[str, Any]]:
    """Twelve internally consistent lake-overflow steps, spilling in year one."""
    steps: list[dict[str, Any]] = []
    volume = 0.0
    for year in range(1, 13):
        spill = 10.0 if year == 1 else 0.0
        sink_loss = 5.0 if year == 1 else 0.0
        end_volume = volume + 100.0 - spill - sink_loss
        steps.append(
            {
                "year": year,
                "start_volume_km3": volume,
                "inflow_km3": 100.0,
                "evaporation_loss_km3": 0.0,
                "spill_volume_km3": spill,
                "sink_loss_km3": sink_loss,
                "end_volume_km3": end_volume,
                "fill_fraction": 0.5,
                "overflow_stage": 1 if year == 1 else 0,
                "avulsion_risk": 0.4 if year == 1 else 0.1,
                "avulsion_triggered": year == 1,
            }
        )
        volume = end_volume
    return steps


def spilling_lake_history() -> dict[str, Any]:
    """A lake-overflow history that spills and triggers an avulsion."""
    steps = lake_history_steps()
    return {
        "id": 0,
        "lake_basin_id": 0,
        "depression_policy": "preserved_geologic",
        "overflows": True,
        "simulation_year_count": len(steps),
        "time_step_count": len(steps),
        "storage_capacity_km3": 81437776.7686,
        "annual_runoff_km3": 27154.6671,
        "total_inflow_km3": 1200.0,
        "total_spill_km3": 10.0,
        "total_sink_loss_km3": 5.0,
        "max_fill_fraction": 0.5,
        "first_overflow_year": 1,
        "avulsion_triggered": True,
        "max_avulsion_risk": 0.4,
        "overflow_path_cell_ids": [],
        "steps": steps,
    }


def channel_history_steps() -> list[dict[str, Any]]:
    """Two internally consistent overflow-channel steps."""
    return [
        {
            "year": 1,
            "start_incision_depth_m": 0.0,
            "spill_volume_km3": 10.0,
            "stream_power_index": 0.5,
            "incision_m": 2.0,
            "bank_widening_m": 1.0,
            "sediment_evacuated_km3": 3.0,
            "end_incision_depth_m": 2.0,
            "avulsion_risk": 0.4,
            "channel_width_m": 50.0,
            "overflow_stage": 1,
            "avulsion_triggered": True,
        },
        {
            "year": 2,
            "start_incision_depth_m": 2.0,
            "spill_volume_km3": 5.0,
            "stream_power_index": 0.25,
            "incision_m": 1.0,
            "bank_widening_m": 0.5,
            "sediment_evacuated_km3": 1.5,
            "end_incision_depth_m": 3.0,
            "avulsion_risk": 0.2,
            "channel_width_m": 60.0,
            "overflow_stage": 1,
            "avulsion_triggered": False,
        },
    ]


def incising_channel_history() -> dict[str, Any]:
    """An overflow-channel history whose roll-ups match its steps exactly."""
    steps = channel_history_steps()
    return {
        "id": 0,
        "lake_basin_id": 0,
        "overflow_path_cell_ids": [0, 1],
        "channel_segment_count": 1,
        "time_step_count": len(steps),
        "steps": steps,
        "total_spill_km3": 15.0,
        "total_incision_m": 3.0,
        "total_bank_widening_m": 1.5,
        "total_sediment_evacuated_km3": 4.5,
        "max_stream_power_index": 0.5,
        "first_avulsion_year": 1,
        "final_incision_depth_m": 3.0,
        "avulsion_triggered": True,
    }


def attach_channel_history(payload: Payload) -> dict[str, Any]:
    """Give lake basin 0 an overflow path and one matching channel history."""
    payload["lake_basins"][0]["overflow_path_cell_ids"] = [0, 1]
    history = incising_channel_history()
    payload["lake_overflow_channel_histories"] = [history]
    return history


#: The untampered ``validate`` run, shared by every class below. All fourteen
#: slices tamper copies of the same ``replay_128`` world, so re-running the
#: control per class would repeat one identical serialization and one identical
#: full validation pass fourteen times over. The proof each class needs -- that
#: the fixture its tampers start from is itself clean -- is the same object.
_CONTROL: Result | None = None


def control_run() -> Result:
    global _CONTROL
    if _CONTROL is None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "control.json"
            write_json(path, worlds.cached_world_readonly(WORLD_KEY))
            _CONTROL = CliRunner().invoke(app, ["validate", "--world", str(path)])
    return _CONTROL


class ValidateSliceCase(TestCase):
    """One on-disk baseline world per class; tampered copies per case."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = TemporaryDirectory()
        cls.root = Path(cls._directory.name)
        cls.world = worlds.cached_world(WORLD_KEY)
        cls.runner = CliRunner()
        cls.control = control_run()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._directory.cleanup()

    def test_untampered_world_validates(self) -> None:
        """The fixture every tamper starts from passes the whole command."""
        self.assert_reported_not_raised(self.control)
        self.assertEqual(self.control.exit_code, 0, self.control.output)
        self.assertEqual(fail_lines(self.control), [])
        self.assertIn("OK", self.control.output)

    def assert_reported_not_raised(self, result: Result) -> None:
        """The command reached a gate instead of blowing up on the way there.

        A crash and a clean verdict are indistinguishable by exit code -- both
        are 1 -- and they are indistinguishable by output too, because
        ``CliRunner`` swallows the exception and returns with nothing written:
        there is no ``Traceback`` in ``result.output`` to look for. What does
        separate them is the exception object. The command's own gate raises
        ``typer.Exit``, which is a ``SystemExit`` and so not an ``Exception``;
        anything that is an ``Exception`` means a check raised rather than
        reported.
        """
        error = result.exception
        if isinstance(error, Exception):
            self.fail(
                "the command raised instead of reporting:\n"
                + "".join(
                    traceback.format_exception(type(error), error, error.__traceback__)
                )
            )

    def invoke_tampered(self, mutate: Tamper) -> Result:
        payload = copy.deepcopy(self.world)
        mutate(payload)
        self.assertNotEqual(
            payload,
            self.world,
            "the tamper left the world untouched, so this case proves nothing",
        )
        path = self.root / "tampered.json"
        write_json(path, payload)
        result = self.runner.invoke(app, ["validate", "--world", str(path)])
        self.assert_reported_not_raised(result)
        self.assertEqual(result.exit_code, 1, result.output)
        return result

    def assert_reports(self, mutate: Tamper, *messages: str) -> Result:
        """Tamper, then assert every ``message`` is reported as its own FAIL line.

        Each message is matched against a whole reported line rather than as a
        substring of the output, so a check whose message merely contains the
        expected one cannot stand in for the check under test.
        """
        self.assertTrue(messages, "a tamper with no expected message asserts nothing")
        result = self.invoke_tampered(mutate)
        reported = fail_lines(result)
        for message in messages:
            self.assertIn(f"FAIL {message}", reported, result.output)
        return result


MOTION_FAILURE = "plate kinematic model or motion history invalid"


class PlateMotionHistoryTest(ValidateSliceCase):
    """The plate motion replay, which folds every complaint into one verdict."""

    def test_motion_summary_roll_ups_are_checked_against_history(self) -> None:
        def mutate(payload: Payload) -> None:
            metrics = summary(payload)
            metrics["plate_motion_history_step_count"] += 1
            metrics["total_aged_oceanic_event_count"] += 1
            metrics["mean_plate_cumulative_rotation_deg"] += 1.0

        self.assert_reports(mutate, MOTION_FAILURE)

    def test_broken_motion_history_is_reported(self) -> None:
        """Each tamper trips a different branch of the shared motion verdict.

        The command reports one line for the whole replay, so these cases prove
        the branches are reachable and reported rather than which branch ran --
        the CLI cannot distinguish them, and this test does not claim to.
        """

        def swapped_rotation_axis(payload: Payload) -> None:
            axis = payload["plates"][0]["axis"]
            payload["plates"][0]["axis"] = [axis[1], axis[0], axis[2]]

        def doubled_angular_speed(payload: Payload) -> None:
            payload["plates"][0]["angular_speed"] *= 2.0

        def drifted_cumulative_rotation(payload: Payload) -> None:
            payload["plate_motion_history"][1]["plates"][0]["cumulative_rotation_deg"] += 5.0

        def drifted_mean_rotation(payload: Payload) -> None:
            payload["plate_motion_history"][1]["mean_plate_rotation_deg"] += 5.0

        def drifted_plate_cumulative_rotation(payload: Payload) -> None:
            payload["plates"][0]["cumulative_rotation_deg"] += 5.0

        def bumped_accreted_count(payload: Payload) -> None:
            payload["plate_motion_history"][-1]["accreted_terrane_cell_count"] += 1

        def truncated_overlap_ledger(payload: Payload) -> None:
            ledger = payload["plate_motion_history"][1]["crust_overlap_ledger"]
            ledger["remapped_crust_density_by_cell"] = ledger["remapped_crust_density_by_cell"][:5]

        broken: dict[str, Tamper] = {
            "truncated_overlap_ledger": truncated_overlap_ledger,
            "empty_plate_snapshot": lambda payload: payload["plate_motion_history"][1][
                "plates"
            ].__setitem__(0, {}),
            "non_numeric_snapshot_center": lambda payload: payload["plate_motion_history"][1][
                "plates"
            ][0].update(center="north"),
            "swapped_rotation_axis": swapped_rotation_axis,
            "doubled_angular_speed": doubled_angular_speed,
            "rotated_initial_snapshot": lambda payload: payload["plate_motion_history"][0][
                "plates"
            ][0].update(cumulative_rotation_deg=5.0),
            "drifted_cumulative_rotation": drifted_cumulative_rotation,
            "drifted_mean_rotation": drifted_mean_rotation,
            "drifted_plate_cumulative_rotation": drifted_plate_cumulative_rotation,
            "bumped_final_accreted_count": bumped_accreted_count,
            "non_numeric_cell_change_count": lambda payload: cells(payload)[0].update(
                plate_assignment_change_count="many"
            ),
        }
        for name, tamper in broken.items():
            with self.subTest(tamper=name):
                self.assert_reports(tamper, MOTION_FAILURE)


class InitialReliefTest(ValidateSliceCase):
    """Per-cell initial relief components and their summary means."""

    def test_relief_component_means_are_checked_against_cells(self) -> None:
        def mutate(payload: Payload) -> None:
            summary(payload)["mean_initial_ridge_uplift_m"] += 500.0
            summary(payload)["mean_initial_elevation_m"] += 500.0
            summary(payload)["high_volcanic_potential_cell_count"] += 7

        self.assert_reports(
            mutate,
            "mean_initial_ridge_uplift_m does not match cells",
            "mean_initial_elevation_m does not match cells",
            "high_volcanic_potential_cell_count does not match cells",
        )

    def test_missing_relief_field_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: cells(payload)[0].pop("initial_ridge_uplift_m"),
            "initial relief component fields invalid",
        )

    def test_non_numeric_relief_field_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: cells(payload)[0].update(initial_ridge_uplift_m="high"),
            "initial relief component fields invalid",
        )

    def test_relief_components_must_sum_to_initial_elevation(self) -> None:
        self.assert_reports(
            lambda payload: cells(payload)[0].update(initial_ridge_uplift_m=-25.0),
            "initial relief component fields invalid",
        )

    def test_missing_thermal_subsidence_target_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: payload["plate_motion_history"][0].pop(
                "post_process_local_thermal_subsidence_target_m"
            ),
            "initial relief component fields invalid",
        )


class MeshLodTest(ValidateSliceCase):
    """The cube-quadtree level-of-detail hierarchy and its summary mirrors."""

    def test_missing_hierarchy_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: payload.update(mesh_lod=None),
            "mesh_lod hierarchy missing",
        )

    def test_hierarchy_header_and_cell_paths_are_checked(self) -> None:
        def mutate(payload: Payload) -> None:
            payload["mesh_lod"]["index"] = "quadtree_v99"
            summary(payload)["mesh_lod_max_level"] += 1
            summary(payload)["mesh_lod_level_count"] += 1
            summary(payload)["mesh_lod_tile_count"] += 1
            summary(payload)["mesh_lod_finest_tile_count"] += 1
            cells(payload)[0].pop("mesh_lod_codes")
            cells(payload)[0]["mesh_lod_finest_tile_id"] = -1

        self.assert_reports(
            mutate,
            "mesh_lod index missing or unsupported",
            "summary mesh_lod_index does not match mesh_lod",
            "summary mesh_lod_max_level does not match mesh_lod",
            "summary mesh_lod_level_count invalid",
            "mesh_lod tile count invalid",
            "mesh_lod cell fields missing",
            "summary mesh_lod_finest_tile_count invalid",
            "mesh_lod cell tile path invalid",
        )

    def test_level_summary_list_length_is_checked(self) -> None:
        self.assert_reports(
            lambda payload: payload["mesh_lod"].update(level_summaries=[]),
            "mesh_lod level summaries invalid",
        )

    def test_level_summaries_and_tile_parents_are_checked(self) -> None:
        def mutate(payload: Payload) -> None:
            hierarchy = payload["mesh_lod"]
            hierarchy["level_summaries"][0]["occupied_tile_count"] += 1
            hierarchy["level_summaries"][0]["cell_count"] += 1
            for tile in hierarchy["tiles"]:
                if int(tile["level"]) == 0:
                    tile["cell_count"] = 0
                    break
            for tile in hierarchy["tiles"]:
                if int(tile["level"]) == 1:
                    tile["parent_tile_id"] = 4242
                    break

        self.assert_reports(
            mutate,
            "mesh_lod level 0 occupied tile count mismatch",
            "mesh_lod level 0 cell count mismatch",
            "mesh_lod level 0 tile 0 has no cells",
            "mesh_lod level 1 tile parent missing",
        )

    def test_root_tile_may_not_have_a_parent(self) -> None:
        def mutate(payload: Payload) -> None:
            for tile in payload["mesh_lod"]["tiles"]:
                if int(tile["level"]) == 0:
                    tile["parent_tile_id"] = 0
                    break

        self.assert_reports(mutate, "mesh_lod root tile has parent")

    def test_non_dict_tiles_are_skipped_but_still_counted(self) -> None:
        self.assert_reports(
            lambda payload: payload["mesh_lod"]["tiles"].append("not-a-tile"),
            "mesh_lod tile count invalid",
        )

    def test_child_tile_counts_are_checked(self) -> None:
        def mutate(payload: Payload) -> None:
            for tile in payload["mesh_lod"]["tiles"]:
                if int(tile["level"]) == 0:
                    tile["child_tile_count"] += 1
                    break

        self.assert_reports(mutate, "mesh_lod child tile count mismatch")


class SphericalSpatialIndexTest(ValidateSliceCase):
    """The HEALPix/S2 compatibility index, its records and its face summaries."""

    def test_missing_index_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: payload.update(spherical_spatial_index=None),
            "spherical_spatial_index missing",
        )

    def test_index_header_and_occupancy_means_are_checked(self) -> None:
        def mutate(payload: Payload) -> None:
            payload["spherical_spatial_index"]["index"] = "healpix_s2_compat_v99"
            summary(payload)["healpix_like_nside"] += 1
            summary(payload)["healpix_like_mean_cells_per_occupied_pixel"] += 1.0
            summary(payload)["s2_like_mean_cells_per_occupied_cell"] += 1.0

        self.assert_reports(
            mutate,
            "spherical_spatial_index index missing or unsupported",
            "summary healpix_like_nside does not match spherical_spatial_index",
            "healpix_like_mean_cells_per_occupied_pixel invalid",
            "s2_like_mean_cells_per_occupied_cell invalid",
        )

    def test_index_dimensions_must_be_self_consistent(self) -> None:
        self.assert_reports(
            lambda payload: payload["spherical_spatial_index"].update(healpix_like_nside=3),
            "spherical_spatial_index dimensions invalid",
        )

    def test_non_numeric_index_dimensions_are_reported(self) -> None:
        self.assert_reports(
            lambda payload: payload["spherical_spatial_index"].update(healpix_like_nside="big"),
            "spherical_spatial_index dimensions invalid",
        )

    def test_missing_record_lists_are_reported(self) -> None:
        def mutate(payload: Payload) -> None:
            payload["spherical_spatial_index"]["healpix_like_pixels"] = None
            payload["spherical_spatial_index"]["s2_like_face_summaries"] = None

        self.assert_reports(
            mutate,
            "spherical_spatial_index records missing",
            "spherical_spatial_index face summaries missing",
        )

    def test_non_numeric_cell_index_field_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: cells(payload)[0].update(healpix_like_ring="north"),
            "spherical spatial index cell fields invalid",
        )

    def test_cell_index_fields_must_match_the_cell_position(self) -> None:
        self.assert_reports(
            lambda payload: cells(payload)[0].update(healpix_like_ring=99),
            "spherical spatial index cell fields invalid",
        )

    def test_malformed_records_are_reported(self) -> None:
        """Non-dict pixel/cell records, plus a face-summary list of the wrong length.

        The face summaries are shortened rather than corrupted because the
        per-face loop reads ``s2_like_cells`` with ``record.get``: leaving the
        list full-length while a record is a string makes the command raise
        instead of report, so that combination cannot be asserted through the CLI.
        """

        def mutate(payload: Payload) -> None:
            index = payload["spherical_spatial_index"]
            index["healpix_like_pixels"][0] = "not-a-record"
            index["s2_like_cells"][0] = "not-a-record"
            index["s2_like_face_summaries"] = index["s2_like_face_summaries"][:-1]

        self.assert_reports(
            mutate,
            "healpix-like occupied pixel records invalid",
            "s2-like occupied cell records invalid",
            "s2-like face summaries invalid",
        )

    def test_face_summary_counts_are_checked_against_records(self) -> None:
        def mutate(payload: Payload) -> None:
            payload["spherical_spatial_index"]["s2_like_face_summaries"][0]["cell_count"] += 5

        self.assert_reports(mutate, "s2-like face summaries invalid")

    def test_record_cell_counts_are_checked_against_cells(self) -> None:
        def mutate(payload: Payload) -> None:
            index = payload["spherical_spatial_index"]
            index["healpix_like_pixels"][0]["cell_count"] += 5
            index["s2_like_cells"][0]["cell_count"] += 5

        self.assert_reports(
            mutate,
            "healpix-like occupied pixel records invalid",
            "s2-like occupied cell records invalid",
        )


class CellGeometryTest(ValidateSliceCase):
    """Per-cell boundary polygons and the geometry roll-ups over them."""

    def test_geometry_summary_metrics_are_checked_against_cells(self) -> None:
        def mutate(payload: Payload) -> None:
            metrics = summary(payload)
            metrics["cell_geometry_index"] = "native_spherical_control_volume_v99"
            metrics["cell_geometry_ring_count"] += 1
            metrics["cell_geometry_total_area_km2"] += 10_000_000.0
            metrics["cell_geometry_reference_area_km2"] += 10_000_000.0
            metrics["cell_geometry_mean_vertex_count"] += 1.0
            metrics["cell_geometry_mean_perimeter_km"] += 100.0
            metrics["cell_geometry_mean_area_error_fraction"] += 1.0
            metrics["cell_geometry_max_area_error_fraction"] += 1.0
            metrics["cell_geometry_mean_quality"] = 2.0

        self.assert_reports(
            mutate,
            "cell_geometry_index missing or unsupported",
            "cell_geometry_ring_count does not match cells length",
            "cell_geometry_total_area_km2 does not match cells",
            "cell_geometry_reference_area_km2 does not match cells",
            "cell_geometry_mean_vertex_count does not match cells",
            "cell_geometry_mean_perimeter_km does not match cells",
            "cell_geometry_mean_area_error_fraction does not match cells",
            "cell_geometry_max_area_error_fraction does not match cells",
            "cell_geometry_mean_quality does not match cells",
            "cell_geometry_mean_quality out of range",
        )

    def test_vertex_count_must_match_the_boundary_ring(self) -> None:
        self.assert_reports(
            lambda payload: cells(payload)[0].update(boundary_vertex_count=2),
            "cell boundary geometry fields invalid",
        )

    def test_boundary_ring_points_must_be_geographic(self) -> None:
        def mutate(payload: Payload) -> None:
            cells(payload)[0]["boundary_ring"][0] = [181.0, 400.0]

        self.assert_reports(mutate, "cell boundary geometry fields invalid")


class CellAdjacencyEdgeTest(ValidateSliceCase):
    """Adjacency edge records, their summary roll-ups and per-cell mirrors."""

    def test_edge_summary_roll_ups_are_checked_against_records(self) -> None:
        def mutate(payload: Payload) -> None:
            metrics = summary(payload)
            metrics["cell_adjacency_edge_count"] += 1
            metrics["cell_boundary_segment_geometry"] = "exact_voronoi_v9"
            metrics["cell_boundary_segment_count"] += 1
            metrics["cell_adjacency_edge_class_counts"] = {"invented_class": 1}
            metrics["mean_cell_adjacency_edge_length_km"] += 10.0
            metrics["max_cell_adjacency_edge_length_km"] += 10.0
            metrics["mean_cell_boundary_segment_length_km"] += 10.0
            metrics["max_cell_boundary_segment_length_km"] += 10.0
            metrics["mean_cell_boundary_segment_mismatch_km"] += 10.0
            metrics["mean_cell_boundary_segment_quality"] = 2.0
            metrics["tectonic_adjacency_edge_count"] += 1

        self.assert_reports(
            mutate,
            "cell_adjacency_edge_count does not match edge records",
            "cell_boundary_segment_geometry missing or unsupported",
            "cell_boundary_segment_count does not match edge records",
            "cell_adjacency_edge_class_counts does not match edge records",
            "mean_cell_adjacency_edge_length_km does not match edge records",
            "max_cell_adjacency_edge_length_km does not match edge records",
            "mean_cell_boundary_segment_length_km does not match edge records",
            "max_cell_boundary_segment_length_km does not match edge records",
            "mean_cell_boundary_segment_mismatch_km does not match edge records",
            "mean_cell_boundary_segment_quality does not match edge records",
            "mean_cell_boundary_segment_quality out of range",
            "tectonic_adjacency_edge_count does not match edge records",
        )

    def test_missing_edge_summary_metric_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: summary(payload).pop("mean_cell_boundary_segment_quality"),
            "cell adjacency edge summary metrics missing",
        )

    def test_missing_edge_list_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: payload.update(cell_adjacency_edges=None),
            "cell_adjacency_edges missing",
        )

    def test_missing_edge_field_breaks_the_edge_replay(self) -> None:
        self.assert_reports(
            lambda payload: payload["cell_adjacency_edges"][0].pop("bearing_a_to_b_deg"),
            "cell adjacency edge fields missing",
            "cell adjacency edge records invalid",
            "cell adjacency edge ids are not unique",
            "cell adjacency edges do not match neighbor pairs",
        )

    def test_per_cell_edge_ids_must_be_a_list(self) -> None:
        self.assert_reports(
            lambda payload: cells(payload)[0].update(cell_adjacency_edge_ids=None),
            "cell adjacency edge cell summaries invalid",
        )

    def test_per_cell_edge_count_is_checked(self) -> None:
        self.assert_reports(
            lambda payload: cells(payload)[0].update(cell_edge_count=99),
            "cell adjacency edge cell summaries invalid",
        )


class TectonicZoneTest(ValidateSliceCase):
    """Collision/subduction/rift zone records and the cell fields mirroring them."""

    def test_zone_summary_roll_ups_are_checked_against_records(self) -> None:
        def mutate(payload: Payload) -> None:
            metrics = summary(payload)
            metrics.pop("mean_tectonic_zone_strength")
            metrics["collision_zone_count"] += 1
            metrics["collision_zone_cell_count"] += 1
            metrics["tectonic_zone_count"] += 1
            metrics["tectonic_zone_total_area_km2"] += 10_000_000.0
            metrics["tectonic_zone_boundary_length_km"] += 1000.0

        self.assert_reports(
            mutate,
            "tectonic zone summary metrics missing",
            "collision_zone_count does not match records",
            "collision_zone_cell_count does not match records",
            "tectonic_zone_count does not match records",
            "tectonic_zone_total_area_km2 does not match records",
            "tectonic_zone_boundary_length_km does not match records",
            "mean_tectonic_zone_strength does not match records",
        )

    def test_missing_zone_list_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: payload.update(tectonic_zones=None),
            "tectonic_zones missing",
        )

    def test_zone_type_list_must_be_a_list(self) -> None:
        """A non-list zone family is reported, not consumed.

        The replacement is a mapping rather than ``None``: the cell-level zone
        check later measures ``len(zone_lists["rift"])`` against the original
        object, so a ``None`` rift list makes the command raise before it can
        report anything.
        """
        self.assert_reports(
            lambda payload: payload.update(rift_zones={}),
            "tectonic zone records invalid",
            "rift_zone_count does not match records",
        )

    def test_flat_zone_list_must_match_the_zone_type_lists(self) -> None:
        def mutate(payload: Payload) -> None:
            payload["tectonic_zones"] = payload["tectonic_zones"][:-1]

        self.assert_reports(
            mutate,
            "tectonic_zone_count does not match records",
            "tectonic_zones does not match zone-type records",
        )

    def test_broken_zone_records_are_reported(self) -> None:
        """One shared verdict per family; see the module docstring on attribution."""
        broken: dict[str, Tamper] = {
            "missing_field": lambda payload: payload["collision_zones"][0].pop("formation_evidence"),
            "non_numeric_area": lambda payload: payload["collision_zones"][0].update(area_km2="wide"),
            "cell_count_mismatch": lambda payload: payload["collision_zones"][0].update(cell_count=99),
            "area_mismatch": lambda payload: payload["collision_zones"][0].update(area_km2=1.0),
            "plate_ids_mismatch": lambda payload: payload["collision_zones"][0].update(plate_ids=[99]),
            "unknown_boundary_edge": lambda payload: payload["collision_zones"][0].update(
                boundary_edge_ids=[999_999]
            ),
            "boundary_edge_count_mismatch": lambda payload: payload["collision_zones"][0].update(
                boundary_edge_count=99
            ),
            "renumbered_zone_id": lambda payload: payload["collision_zones"][0].update(id=7),
        }
        for name, tamper in broken.items():
            with self.subTest(tamper=name):
                self.assert_reports(tamper, "tectonic zone records invalid")

    def test_zone_cell_ids_must_point_back_at_the_zone(self) -> None:
        def mutate(payload: Payload) -> None:
            zone = payload["collision_zones"][0]
            outsider = next(
                int(cell["id"])
                for cell in cells(payload)
                if int(cell.get("collision_zone_id", -1)) != int(zone["id"])
            )
            zone["cell_ids"] = [outsider]
            zone["cell_count"] = 1
            zone["representative_cell_id"] = outsider

        self.assert_reports(mutate, "tectonic zone records invalid")

    def test_zone_boundary_edges_must_touch_the_zone(self) -> None:
        def mutate(payload: Payload) -> None:
            zone = payload["collision_zones"][0]
            zone_cells = {int(cell_id) for cell_id in zone["cell_ids"]}
            edge = first_edge_where(
                payload,
                lambda candidate: bool(candidate.get("plate_boundary"))
                and int(candidate["cell_a_id"]) not in zone_cells
                and int(candidate["cell_b_id"]) not in zone_cells,
            )
            zone["boundary_edge_ids"] = [int(edge["id"])]

        self.assert_reports(mutate, "tectonic zone records invalid")

    def test_zone_cell_counts_are_checked_per_zone_type(self) -> None:
        self.assert_reports(
            lambda payload: summary(payload).update(collision_zone_cell_count=999),
            "collision_zone_cell_count does not match records",
        )

    def test_non_numeric_cell_zone_field_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: cells(payload)[0].update(tectonic_zone_strength="strong"),
            "cell tectonic zone fields invalid",
        )

    def test_unknown_dominant_zone_type_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: cells(payload)[0].update(dominant_tectonic_zone_type="obduction"),
            "cell tectonic zone fields invalid",
        )


class FaultSystemTest(ValidateSliceCase):
    """Fault system records, their seismic cell fields and summary roll-ups."""

    def test_fault_summary_roll_ups_are_checked(self) -> None:
        def mutate(payload: Payload) -> None:
            metrics = summary(payload)
            metrics.pop("mean_seismic_hazard_index")
            metrics["fault_system_count"] += 1
            metrics["fault_system_cell_count"] += 1
            metrics["high_seismic_hazard_cell_count"] += 1
            metrics["fault_system_total_area_km2"] += 10_000_000.0
            metrics["fault_system_boundary_length_km"] += 1000.0

        self.assert_reports(
            mutate,
            "fault system summary metrics missing",
            "fault_system_count does not match records",
            "mean_seismic_hazard_index does not match fault system cells",
            "fault_system_cell_count does not match cells",
            "high_seismic_hazard_cell_count does not match cells",
            "fault_system_total_area_km2 does not match records",
            "fault_system_boundary_length_km does not match records",
        )

    def test_missing_fault_system_list_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: payload.update(fault_systems=None),
            "fault_systems missing",
        )

    def test_non_numeric_seismic_cell_field_is_reported(self) -> None:
        """A non-numeric slip rate on a cell no fault system claims.

        A claimed cell would be re-read by the fault system record loop, which
        converts the same field outside a guard, so the command would raise
        before reaching its gate.
        """

        def mutate(payload: Payload) -> None:
            claimed = {
                int(cell_id)
                for system in payload["fault_systems"]
                for cell_id in system["cell_ids"]
            }
            unclaimed = next(
                cell for cell in cells(payload) if int(cell["id"]) not in claimed
            )
            unclaimed["fault_slip_rate_index"] = "fast"

        self.assert_reports(mutate, "fault system cell fields invalid")

    def test_out_of_range_seismic_hazard_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: cells(payload)[0].update(seismic_hazard_index=2.0),
            "fault system cell fields invalid",
        )

    def test_broken_fault_system_records_are_reported(self) -> None:
        """One shared verdict per family; see the module docstring on attribution."""
        broken: dict[str, Tamper] = {
            "missing_field": lambda payload: payload["fault_systems"][0].pop("plate_pair_ids"),
            "non_numeric_area": lambda payload: payload["fault_systems"][0].update(area_km2="wide"),
            "cell_count_mismatch": lambda payload: payload["fault_systems"][0].update(cell_count=99),
            "area_mismatch": lambda payload: payload["fault_systems"][0].update(area_km2=1.0),
            "unknown_boundary_edge": lambda payload: payload["fault_systems"][0].update(
                boundary_edge_ids=[999_999]
            ),
            "boundary_edge_count_mismatch": lambda payload: payload["fault_systems"][0].update(
                boundary_edge_count=99
            ),
        }
        for name, tamper in broken.items():
            with self.subTest(tamper=name):
                self.assert_reports(tamper, "fault system records invalid")

    def test_fault_system_cell_ids_must_point_back_at_the_system(self) -> None:
        def mutate(payload: Payload) -> None:
            system = payload["fault_systems"][0]
            outsider = next(
                int(cell["id"])
                for cell in cells(payload)
                if int(cell.get("fault_system_id", -1)) != int(system["id"])
            )
            system["cell_ids"] = [outsider]
            system["cell_count"] = 1
            system["representative_cell_id"] = outsider

        self.assert_reports(
            mutate,
            "fault system records invalid",
            "fault_system_id cell references do not match records",
        )

    def test_fault_boundary_edges_must_touch_the_system(self) -> None:
        def mutate(payload: Payload) -> None:
            system = payload["fault_systems"][0]
            system_cells = {int(cell_id) for cell_id in system["cell_ids"]}
            edge = first_edge_where(
                payload,
                lambda candidate: bool(candidate.get("plate_boundary"))
                and int(candidate["cell_a_id"]) not in system_cells
                and int(candidate["cell_b_id"]) not in system_cells,
            )
            system["boundary_edge_ids"] = [int(edge["id"])]

        self.assert_reports(mutate, "fault system records invalid")


class LakeBasinTest(ValidateSliceCase):
    """Lake basin counts, spill fields and the overflow history replay."""

    def test_lake_basin_summary_counts_are_checked(self) -> None:
        def mutate(payload: Payload) -> None:
            metrics = summary(payload)
            metrics["basin_count"] = 0
            metrics["lake_basin_count"] += 1
            metrics["overflowing_lake_basin_count"] += 1
            metrics["staged_overflow_lake_basin_count"] += 1
            metrics["high_avulsion_risk_lake_basin_count"] += 1
            metrics["preserved_geologic_depression_count"] += 1
            metrics["corrected_numeric_depression_count"] += 1
            metrics["simulated_lake_basin_count"] += 1
            metrics["lake_overflow_history_count"] += 1
            metrics["lake_overflow_history_step_count"] += 1
            payload["lake_basins"][0].pop("avulsion_risk")

        self.assert_reports(
            mutate,
            "basin_count missing or empty",
            "lake_basin_count does not match lake_basins length",
            "overflowing_lake_basin_count does not match overflowing lake basins",
            "staged_overflow_lake_basin_count does not match lake basin overflow stages",
            "high_avulsion_risk_lake_basin_count does not match lake basin avulsion risk",
            "preserved_geologic_depression_count does not match lake basin policies",
            "corrected_numeric_depression_count does not match lake basin policies",
            "lake basin spill/storage fields missing",
            "simulated_lake_basin_count does not match basins with lake cells",
            "lake_overflow_history_count does not match lake_overflow_histories length",
            "lake_overflow_history_step_count does not match lake histories",
        )

    def test_history_basin_ids_must_match_simulated_basins(self) -> None:
        self.assert_reports(
            lambda payload: payload["lake_overflow_histories"][0].update(lake_basin_id=97),
            "lake_overflow_histories do not match basins with lake cells",
            "lake overflow history fields invalid",
        )

    def test_broken_lake_history_records_are_reported(self) -> None:
        """One shared verdict per family; see the module docstring on attribution."""

        def step_tamper(index: int, **fields: Any) -> Tamper:
            def mutate(payload: Payload) -> None:
                payload["lake_overflow_histories"][0]["steps"][index].update(fields)

            return mutate

        def volume_discontinuity(payload: Payload) -> None:
            """Restart year two from an empty lake, keeping its own mass balance."""
            step = payload["lake_overflow_histories"][0]["steps"][1]
            step["start_volume_km3"] = 0.0
            step["end_volume_km3"] = (
                step["inflow_km3"]
                - step["evaporation_loss_km3"]
                - step["spill_volume_km3"]
                - step["sink_loss_km3"]
            )

        broken: dict[str, Tamper] = {
            "step_count_mismatch": lambda payload: payload["lake_overflow_histories"][0].update(
                time_step_count=99
            ),
            "negative_inflow": step_tamper(0, inflow_km3=-5.0),
            "volume_discontinuity": volume_discontinuity,
            "out_of_range_avulsion_risk": step_tamper(0, avulsion_risk=5.0),
            "total_spill_mismatch": lambda payload: payload["lake_overflow_histories"][0].update(
                total_spill_km3=500.0
            ),
            "total_sink_loss_mismatch": lambda payload: payload["lake_overflow_histories"][0].update(
                total_sink_loss_km3=500.0
            ),
            "first_overflow_year_mismatch": lambda payload: payload["lake_overflow_histories"][0].update(
                first_overflow_year=3
            ),
        }
        for name, tamper in broken.items():
            with self.subTest(tamper=name):
                self.assert_reports(tamper, "lake overflow history fields invalid")

    def test_spilling_history_is_accepted_and_rolled_up(self) -> None:
        """A consistent spilling history is replayed, then contradicts the summary."""

        def mutate(payload: Payload) -> None:
            payload["lake_overflow_histories"] = [spilling_lake_history()]

        result = self.assert_reports(
            mutate,
            "lake_overflow_active_history_count does not match histories",
            "lake_overflow_avulsion_trigger_count does not match histories",
            "lake_overflow_total_spill_km3 does not match histories",
            "lake_overflow_total_sink_loss_km3 does not match histories",
            "max_lake_overflow_fill_fraction does not match histories",
        )
        self.assertNotIn("FAIL lake overflow history fields invalid", result.output)


class LakeOverflowChannelTest(ValidateSliceCase):
    """The overflow-channel incision histories, absent from a healthy 128-cell world."""

    def test_channel_summary_counts_are_checked(self) -> None:
        def mutate(payload: Payload) -> None:
            metrics = summary(payload)
            metrics["lake_overflow_channel_history_count"] += 1
            metrics["lake_overflow_channel_step_count"] += 1
            metrics["lake_overflow_channel_cell_count"] += 1
            payload["lake_basins"][0]["overflow_path_cell_ids"] = [0, 1]
            cells(payload)[0].pop("overflow_channel_incision_m")

        self.assert_reports(
            mutate,
            "lake_overflow_channel_history_count does not match histories length",
            "lake_overflow_channel_histories length does not match lake basins with overflow paths",
            "lake_overflow_channel_step_count does not match histories",
            "lake_overflow_channel_cell_count does not match active cells",
            "overflow channel cell fields missing",
        )

    def test_channel_history_without_a_path_is_rejected(self) -> None:
        def mutate(payload: Payload) -> None:
            payload["lake_overflow_channel_histories"] = [
                {"lake_basin_id": 0, "overflow_path_cell_ids": [], "steps": []}
            ]

        self.assert_reports(mutate, "lake overflow channel history fields invalid")

    def test_incising_history_is_accepted_and_rolled_up(self) -> None:
        """A consistent channel history is replayed, then contradicts the summary."""
        result = self.assert_reports(
            lambda payload: attach_channel_history(payload),
            "active_lake_overflow_channel_count does not match histories",
            "lake_overflow_channel_avulsion_count does not match histories",
            "lake_overflow_total_channel_incision_m does not match histories",
            "max_lake_overflow_channel_incision_m does not match histories",
            "lake_overflow_total_channel_sediment_evacuated_km3 does not match histories",
            "mean_lake_overflow_channel_stream_power_index does not match histories",
        )
        self.assertNotIn("FAIL lake overflow channel history fields invalid", result.output)

    def test_broken_channel_history_records_are_reported(self) -> None:
        """One shared verdict per family; see the module docstring on attribution."""

        def history_tamper(**fields: Any) -> Tamper:
            def mutate(payload: Payload) -> None:
                attach_channel_history(payload).update(fields)

            return mutate

        def step_tamper(index: int, **fields: Any) -> Tamper:
            def mutate(payload: Payload) -> None:
                attach_channel_history(payload)["steps"][index].update(fields)

            return mutate

        def incision_discontinuity(payload: Payload) -> None:
            """Restart year two from an uncut channel, keeping its own depth sum."""
            step = attach_channel_history(payload)["steps"][1]
            step["start_incision_depth_m"] = 0.0
            step["end_incision_depth_m"] = step["incision_m"]

        broken: dict[str, Tamper] = {
            "segment_count_mismatch": history_tamper(channel_segment_count=9),
            "out_of_range_stream_power": step_tamper(0, stream_power_index=2.0),
            "incision_discontinuity": incision_discontinuity,
            "total_spill_mismatch": history_tamper(total_spill_km3=500.0),
            "total_incision_mismatch": history_tamper(total_incision_m=500.0),
            "total_widening_mismatch": history_tamper(total_bank_widening_m=500.0),
            "total_sediment_mismatch": history_tamper(total_sediment_evacuated_km3=500.0),
            "max_stream_power_mismatch": history_tamper(max_stream_power_index=0.9),
            "first_avulsion_year_mismatch": history_tamper(first_avulsion_year=2),
            "final_depth_mismatch": history_tamper(final_incision_depth_m=500.0),
        }
        for name, tamper in broken.items():
            with self.subTest(tamper=name):
                self.assert_reports(tamper, "lake overflow channel history fields invalid")


class WatershedNetworkTest(ValidateSliceCase):
    """Watershed geometry, main-channel replay and the Hack-relation roll-ups."""

    def test_watershed_geometry_summary_metrics_are_checked(self) -> None:
        def mutate(payload: Payload) -> None:
            metrics = summary(payload)
            metrics["watershed_count"] += 1
            metrics["watershed_geometry_count"] += 1
            metrics["watershed_polygon_count"] += 1
            metrics.pop("mean_watershed_compactness_index")
            metrics["mean_watershed_geometry_quality"] = 2.0
            payload["watersheds"][0].pop("geometry_quality")

        self.assert_reports(
            mutate,
            "watershed_count does not match watersheds length",
            "watershed_geometry_count does not match watersheds with boundary rings",
            "watershed_polygon_count does not match watersheds with polygon area",
            "watershed geometry fields missing",
            "watershed polygon summary metrics missing",
            "mean_watershed_geometry_quality out of range",
        )

    def test_network_summary_roll_ups_are_checked(self) -> None:
        def mutate(payload: Payload) -> None:
            metrics = summary(payload)
            metrics["watershed_outlet_type_counts"] = {"invented_outlet": 1}
            metrics["watershed_main_channel_count"] += 1
            metrics["watershed_total_river_length_km"] += 1000.0
            metrics["watershed_mean_main_channel_length_km"] += 1000.0
            metrics["watershed_max_main_channel_length_km"] += 1000.0
            metrics["watershed_mean_drainage_density_km_per_1000_km2"] += 10.0
            metrics["watershed_mean_hack_coefficient"] += 10.0
            metrics["watershed_mean_abs_hack_residual_fraction"] += 10.0
            metrics["watershed_hack_fitted_minimum_basin_area_km2"] += 10.0
            metrics["watershed_hack_fitted_observation_count"] += 1
            metrics["watershed_hack_fitted_exponent"] += 1.0
            metrics["watershed_hack_fitted_coefficient"] += 1.0
            metrics["watershed_hack_fitted_log_rmse"] += 1.0

        self.assert_reports(
            mutate,
            "watershed_outlet_type_counts does not match watersheds",
            "watershed_main_channel_count does not match watersheds",
            "watershed_total_river_length_km does not match watersheds",
            "watershed_mean_main_channel_length_km does not match watersheds",
            "watershed_max_main_channel_length_km does not match watersheds",
            "watershed_mean_drainage_density_km_per_1000_km2 does not match watersheds",
            "watershed_mean_hack_coefficient does not match watersheds",
            "watershed_mean_abs_hack_residual_fraction does not match watersheds",
            "watershed_hack_fitted_minimum_basin_area_km2 unsupported",
            "watershed_hack_fitted_observation_count does not match watersheds",
            "watershed_hack_fitted_exponent does not match watersheds",
            "watershed_hack_fitted_coefficient does not match watersheds",
            "watershed_hack_fitted_log_rmse does not match watersheds",
        )

    def test_missing_network_summary_metric_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: summary(payload).pop("watershed_hack_fit_coefficient"),
            "watershed network summary metrics missing",
        )

    def test_missing_network_field_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: payload["watersheds"][0].pop("hack_coefficient"),
            "watershed network fields missing",
            "watershed network diagnostics invalid",
        )

    def test_unsupported_hack_exponent_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: summary(payload).update(watershed_hack_exponent=0.5),
            "watershed_hack_exponent unsupported",
        )

    def test_fitted_hack_coefficient_is_checked(self) -> None:
        self.assert_reports(
            lambda payload: summary(payload).update(watershed_hack_fit_coefficient=999.0),
            "watershed_hack_fit_coefficient does not match watersheds",
        )

    def test_broken_watershed_network_diagnostics_are_reported(self) -> None:
        """One shared verdict per family; see the module docstring on attribution."""

        def watershed_tamper(**fields: Any) -> Tamper:
            def mutate(payload: Payload) -> None:
                payload["watersheds"][0].update(fields)

            return mutate

        def reversed_main_channel(payload: Payload) -> None:
            watershed = payload["watersheds"][0]
            path = list(reversed(watershed["main_channel_cell_ids"]))
            watershed["main_channel_cell_ids"] = path
            watershed["main_channel_source_cell_id"] = path[0]
            watershed["main_channel_outlet_cell_id"] = path[-1]

        def duplicated_main_channel(payload: Payload) -> None:
            watershed = payload["watersheds"][0]
            head = int(watershed["main_channel_cell_ids"][0])
            watershed["main_channel_cell_ids"] = [head, head]
            watershed["main_channel_source_cell_id"] = head
            watershed["main_channel_outlet_cell_id"] = head

        def foreign_basin(payload: Payload) -> None:
            payload["watersheds"][0]["basin_id"] = 9_999

        broken: dict[str, Tamper] = {
            "sinuosity_below_one": watershed_tamper(main_channel_sinuosity_index=0.5),
            "source_cell_mismatch": watershed_tamper(main_channel_source_cell_id=9_999),
            "duplicated_path_cells": duplicated_main_channel,
            "path_cells_from_another_basin": foreign_basin,
            "path_not_following_flow": reversed_main_channel,
            "main_channel_length_mismatch": watershed_tamper(main_channel_length_km=1.0),
            "channel_drop_mismatch": watershed_tamper(main_channel_drop_m=0.0),
            "empty_path_with_length": watershed_tamper(main_channel_cell_ids=[]),
            "drainage_density_mismatch": watershed_tamper(drainage_density_km_per_1000_km2=99.0),
            "hack_coefficient_mismatch": watershed_tamper(hack_coefficient=99.0),
            "hack_expected_length_mismatch": watershed_tamper(
                hack_expected_main_channel_length_km=1.0
            ),
            "hack_residual_mismatch": watershed_tamper(hack_residual_fraction=0.9),
        }
        for name, tamper in broken.items():
            with self.subTest(tamper=name):
                self.assert_reports(tamper, "watershed network diagnostics invalid")


class WatershedBoundaryTest(ValidateSliceCase):
    """Cell-edge watershed divides and the roll-ups over them."""

    def test_boundary_summary_roll_ups_are_checked(self) -> None:
        def mutate(payload: Payload) -> None:
            metrics = summary(payload)
            metrics["watershed_cell_edge_boundary_segment_count"] += 1
            metrics["watershed_cell_edge_boundary_directed_segment_count"] += 1
            metrics["watershed_with_cell_edge_boundary_count"] += 1
            metrics["watershed_cell_edge_boundary_length_km"] += 1000.0
            metrics["mean_watershed_cell_edge_boundary_length_km"] += 1000.0
            metrics["mean_watershed_cell_edge_boundary_segment_quality"] += 1.0

        self.assert_reports(
            mutate,
            "watershed_cell_edge_boundary_segment_count does not match records",
            "watershed_cell_edge_boundary_directed_segment_count does not match watersheds",
            "watershed_with_cell_edge_boundary_count does not match watersheds",
            "watershed_cell_edge_boundary_length_km does not match segments",
            "mean_watershed_cell_edge_boundary_length_km does not match watersheds",
            "mean_watershed_cell_edge_boundary_segment_quality does not match segments",
        )

    def test_missing_boundary_summary_metric_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: summary(payload).pop("mean_watershed_cell_edge_boundary_length_km"),
            "watershed cell-edge boundary summary metrics missing",
        )

    def test_missing_boundary_segment_list_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: payload.update(watershed_boundary_segments=None),
            "watershed_boundary_segments missing",
        )

    def test_segment_source_edge_must_exist(self) -> None:
        self.assert_reports(
            lambda payload: payload["watershed_boundary_segments"][0].update(source_edge_id=999_999),
            "watershed boundary segment records invalid",
        )

    def test_segment_source_edge_must_reference_known_cells(self) -> None:
        def mutate(payload: Payload) -> None:
            source_edge_id = int(payload["watershed_boundary_segments"][0]["source_edge_id"])
            payload["cell_adjacency_edges"][source_edge_id]["cell_a_id"] = 9_999

        self.assert_reports(mutate, "watershed boundary segment records invalid")

    def test_segment_must_separate_two_watersheds(self) -> None:
        def mutate(payload: Payload) -> None:
            lookup = cells_by_id(payload)
            edge = first_edge_where(
                payload,
                lambda candidate: int(lookup[int(candidate["cell_a_id"])].get("basin_id", -1))
                == int(lookup[int(candidate["cell_b_id"])].get("basin_id", -2)),
            )
            payload["watershed_boundary_segments"][0]["source_edge_id"] = int(edge["id"])

        self.assert_reports(mutate, "watershed boundary segment records invalid")

    def test_segment_length_must_match_its_edge(self) -> None:
        self.assert_reports(
            lambda payload: payload["watershed_boundary_segments"][0].update(length_km=1.0),
            "watershed boundary segment records invalid",
        )

    def test_per_watershed_boundary_fields_are_checked(self) -> None:
        self.assert_reports(
            lambda payload: payload["watersheds"][0].update(cell_edge_boundary_segment_count=999),
            "watershed boundary fields invalid",
        )


class HydrologyRealismTest(ValidateSliceCase):
    """The hydrology realism scorecard and its summary mirrors."""

    def test_realism_summary_roll_ups_are_checked(self) -> None:
        def mutate(payload: Payload) -> None:
            metrics = summary(payload)
            metrics["hydrology_realism_check_count"] += 1
            metrics["hydrology_realism_pass_count"] += 1
            metrics.pop("mean_hydrology_realism_score")
            metrics["hydrology_realism_pass_fraction"] += 0.5
            metrics["valid_river_sink_fraction"] = 0.25
            payload["hydrology_realism_checks"][0].pop("evidence")

        self.assert_reports(
            mutate,
            "hydrology_realism_check_count does not match hydrology_realism_checks length",
            "hydrology_realism_pass_count does not match hydrology realism checks",
            "hydrology realism summary metrics missing",
            "hydrology realism check fields missing",
            "hydrology_realism_pass_fraction does not match checks",
            "mean_hydrology_realism_score does not match checks",
            "valid_river_sink_fraction does not match hydrology realism check",
        )

    def test_out_of_range_check_score_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: payload["hydrology_realism_checks"][0].update(score=5.0),
            "hydrology realism check records invalid",
        )


class HydrologicBudgetTest(ValidateSliceCase):
    """Per-cell water budget fields, their roll-ups and the budget regions."""

    def test_budget_summary_roll_ups_are_checked(self) -> None:
        def mutate(payload: Payload) -> None:
            metrics = summary(payload)
            metrics.pop("mean_infiltration_mm_y")
            metrics["high_runoff_generation_cell_count"] += 1
            metrics["water_budget_deficit_cell_count"] += 1
            metrics["low_runoff_budget_consistency_cell_count"] += 1
            metrics["hydrologic_budget_class_counts"] = {"invented_class": 1}

        self.assert_reports(
            mutate,
            "hydrologic budget summary metrics missing",
            "mean_infiltration_mm_y does not match hydrologic budget cells",
            "high_runoff_generation_cell_count does not match cells",
            "water_budget_deficit_cell_count does not match cells",
            "low_runoff_budget_consistency_cell_count does not match cells",
            "hydrologic_budget_class_counts does not match cells",
        )

    def test_missing_budget_region_list_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: payload.update(hydrologic_budget_regions=None),
            "hydrologic_budget_regions missing",
        )

    def test_non_numeric_budget_cell_field_is_reported(self) -> None:
        """A non-numeric runoff fraction, withdrawn from its budget region.

        Every field of the budget cell replay is re-read outside a guard by
        either the water-budget validator that runs before it or the region
        replay that runs after it. Dropping the cell from its region's member
        list is what keeps the later reader away from the corrupted value, so
        the guard's own report is what reaches the gate.
        """

        def mutate(payload: Payload) -> None:
            cell = cells(payload)[0]
            cell["runoff_generation_fraction"] = "damp"
            cell_id = int(cell["id"])
            region_id = int(cell["hydrologic_budget_region_id"])
            for region in payload["hydrologic_budget_regions"]:
                if int(region["id"]) == region_id:
                    region["cell_ids"] = [
                        member for member in region["cell_ids"] if int(member) != cell_id
                    ]
                    region["cell_count"] = len(region["cell_ids"])

        self.assert_reports(mutate, "hydrologic budget cell fields invalid")

    def test_out_of_range_infiltration_capacity_is_reported(self) -> None:
        self.assert_reports(
            lambda payload: cells(payload)[0].update(infiltration_capacity_index=2.0),
            "hydrologic budget cell fields invalid",
        )

    def test_broken_budget_region_records_are_reported(self) -> None:
        """One shared verdict per family; see the module docstring on attribution."""

        def region_tamper(**fields: Any) -> Tamper:
            def mutate(payload: Payload) -> None:
                payload["hydrologic_budget_regions"][0].update(fields)

            return mutate

        def foreign_region_cells(payload: Payload) -> None:
            region = payload["hydrologic_budget_regions"][0]
            outsider = next(
                int(cell["id"])
                for cell in cells(payload)
                if int(cell.get("hydrologic_budget_region_id", -1)) != int(region["id"])
            )
            region["cell_ids"] = [outsider]
            region["cell_count"] = 1

        broken: dict[str, Tamper] = {
            "non_dict_region": lambda payload: payload["hydrologic_budget_regions"].__setitem__(
                0, "not-a-region"
            ),
            "non_numeric_area": region_tamper(area_km2="wide"),
            "cell_count_mismatch": region_tamper(cell_count=99),
            "cells_from_another_region": foreign_region_cells,
            "mean_precipitation_mismatch": region_tamper(mean_precipitation_mm_y=-5.0),
        }
        for name, tamper in broken.items():
            with self.subTest(tamper=name):
                self.assert_reports(tamper, "hydrologic budget region records invalid")
