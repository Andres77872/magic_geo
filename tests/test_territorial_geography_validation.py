"""Causal-replay coverage for :mod:`magic_geo.territorial_geography_validation`.

``validate_territorial_geography_replay`` rebuilds every era-scaled territorial
snapshot -- region membership, centroids, sampled boundary rings, perimeters,
projected areas, stability and the derived summary aggregates -- from the rest
of the generated world and compares the result record by record.  So a passing
payload for a populated world cannot be hand-built: the happy path runs the real
canonical world, and every failure case starts from a private copy of that same
world and applies exactly one mutation.

Two kinds of mutation are exercised, and both matter:

* *recorded* tampers edit the stored snapshot records, and prove the validator
  compares what it recomputed against what the world actually carries;
* *upstream* tampers edit the inputs the replay is derived from (cells,
  cultures, eras, populations, conflicts, planet radius) and leave the recorded
  snapshots untouched.  These are the ones that would survive a regression
  turning the validator into a self-consistency check.

``magic_geo.cli`` calls this validator from the ``validate`` command, so the
entry point must also swallow malformed payloads rather than raise.
"""

from __future__ import annotations

from typing import Any, Callable
from unittest import TestCase

from support import worlds

from magic_geo.territorial_geography_validation import (
    TERRITORIAL_SNAPSHOT_MODEL,
    _replay_valid,
    validate_territorial_geography_replay,
)

#: The single message the validator returns for any mismatch.
FAILURE = "territorial snapshot model or causal replay invalid"

CANONICAL_WORLD = "replay_128"

Tamper = Callable[[dict[str, Any]], Any]


def _tampered(mutate: Tamper) -> dict[str, Any]:
    """A private copy of the canonical world with one mutation applied.

    A tamper that fails to change anything observable is not silently tolerated:
    the untouched copy replays cleanly (asserted in
    ``test_untouched_copy_of_the_canonical_world_still_replays``), so a no-op
    mutation yields ``[]`` and fails its ``assertEqual`` below.
    """
    payload = worlds.cached_world(CANONICAL_WORLD)
    mutate(payload)
    return payload


def _first_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return payload["territorial_snapshots"][0]


def _first_region(payload: dict[str, Any]) -> dict[str, Any]:
    return _first_snapshot(payload)["regions"][0]


def _first_assigned_land_cell(payload: dict[str, Any]) -> dict[str, Any]:
    """The first land cell belonging to the first political region."""
    region_id = int(payload["political_regions"][0]["id"])
    for cell in payload["cells"]:
        if not bool(cell.get("is_water", False)) and int(cell.get("political_region_id", -1)) == region_id:
            return cell
    raise AssertionError("canonical world has no land cell assigned to region 0")


class TerritorialGeographyReplayValidationTests(TestCase):
    def test_canonical_world_replays_without_failures(self) -> None:
        payload = worlds.cached_world_readonly(CANONICAL_WORLD)
        snapshots = payload["territorial_snapshots"]
        eras = payload["historical_eras"]
        summary = payload["summary"]
        regions = [region for snapshot in snapshots for region in snapshot["regions"]]

        self.assertEqual(validate_territorial_geography_replay(payload), [])
        # One snapshot per historical era, numbered in record order.
        self.assertEqual(len(snapshots), len(eras))
        self.assertEqual(
            [snapshot["id"] for snapshot in snapshots], list(range(len(snapshots)))
        )
        self.assertEqual(
            [snapshot["era_id"] for snapshot in snapshots], [era["id"] for era in eras]
        )
        self.assertEqual(
            [snapshot["region_count"] for snapshot in snapshots],
            [len(snapshot["regions"]) for snapshot in snapshots],
        )
        self.assertEqual(summary["territorial_snapshot_model"], TERRITORIAL_SNAPSHOT_MODEL)
        self.assertEqual(payload["territorial_snapshot_model"]["deterministic"], True)
        self.assertEqual(summary["territorial_snapshot_count"], len(snapshots))
        self.assertEqual(summary["snapshot_region_record_count"], len(regions))
        self.assertEqual(
            summary["snapshot_polygon_region_count"],
            sum(1 for region in regions if float(region["dissolved_polygon_area_km2"]) > 0.0),
        )

    def test_snapshot_aggregates_are_independently_reproducible(self) -> None:
        """Recompute the snapshot aggregates here, not from the validator.

        Every expected value below is derived from ``historical_eras`` and
        ``cells`` by this test, so it stays an independent statement of the
        contract even if the validator and the generator drift together.
        """
        payload = worlds.cached_world_readonly(CANONICAL_WORLD)
        land_area_km2 = sum(
            float(cell["area_km2"])
            for cell in payload["cells"]
            if not bool(cell.get("is_water", False))
        )
        self.assertGreater(land_area_km2, 0.0)

        for snapshot, era in zip(
            payload["territorial_snapshots"], payload["historical_eras"], strict=True
        ):
            with self.subTest(era=era["id"]):
                snapshot_regions = snapshot["regions"]
                # The snapshot is dated at the midpoint of its era.
                self.assertAlmostEqual(
                    float(snapshot["year_bp"]),
                    0.5 * (float(era["start_year_bp"]) + float(era["end_year_bp"])),
                    delta=0.001,
                )
                # Assigned land is the region area share of all land cell area.
                assigned_km2 = sum(float(region["area_km2"]) for region in snapshot_regions)
                self.assertAlmostEqual(
                    float(snapshot["assigned_land_fraction"]),
                    assigned_km2 / land_area_km2,
                    delta=0.0005,
                )
                # The recorded largest region is the largest region on record.
                largest = max(snapshot_regions, key=lambda region: float(region["area_km2"]))
                self.assertEqual(snapshot["largest_region_id"], largest["region_id"])
                self.assertAlmostEqual(
                    float(snapshot["largest_region_area_km2"]),
                    float(largest["area_km2"]),
                    delta=1.0,
                )
                # Snapshot population is the sum over its region records.
                population = sum(
                    float(region["estimated_population"]) for region in snapshot_regions
                )
                self.assertAlmostEqual(
                    float(snapshot["estimated_population"]),
                    population,
                    delta=max(1.0, 1e-6 * population),
                )
                # A single era with no regions would make every tamper below
                # unobservable, so pin the canonical world down.
                self.assertGreater(len(snapshot_regions), 0)

    def test_untouched_copy_of_the_canonical_world_still_replays(self) -> None:
        """The precondition for every ``FAILURE`` assertion in this file.

        If the deep copy handed out by ``worlds.cached_world`` did not itself
        replay cleanly, every tamper case would "pass" for the wrong reason.
        """
        self.assertEqual(
            validate_territorial_geography_replay(worlds.cached_world(CANONICAL_WORLD)), []
        )

        # ``settlements`` only feeds the centroid fallback for regions with no
        # land cells, and the canonical world has none, so emptying that list is
        # silently accepted -- an in-suite negative control showing the harness
        # returns the empty list unless the mutation is one the replay observes.
        self.assertTrue(worlds.cached_world_readonly(CANONICAL_WORLD)["settlements"])
        ignored = _tampered(lambda world: world.__setitem__("settlements", []))
        self.assertEqual(validate_territorial_geography_replay(ignored), [])

        # ...while emptying a list the replay does read is caught.
        observed = _tampered(lambda world: world.__setitem__("political_regions", []))
        self.assertEqual(validate_territorial_geography_replay(observed), [FAILURE])

    def test_snapshot_scalar_tampers_are_rejected(self) -> None:
        def shift_year(payload: dict[str, Any]) -> None:
            snapshot = _first_snapshot(payload)
            snapshot["year_bp"] = float(snapshot["year_bp"]) + 1.0

        cases: dict[str, Tamper] = {
            # The verified vector: the recorded count no longer matches the
            # rebuilt region list.
            "region_count": lambda payload: _first_snapshot(payload).__setitem__(
                "region_count", 42
            ),
            "id": lambda payload: _first_snapshot(payload).__setitem__("id", 9),
            "era_id": lambda payload: _first_snapshot(payload).__setitem__("era_id", 3),
            "dominant_process": lambda payload: _first_snapshot(payload).__setitem__(
                "dominant_process", "bogus_process"
            ),
            "largest_region_id": lambda payload: _first_snapshot(payload).__setitem__(
                "largest_region_id", -7
            ),
            "largest_region_area_km2": lambda payload: _first_snapshot(payload).__setitem__(
                "largest_region_area_km2", 1.0
            ),
            "year_bp": shift_year,
            "assigned_land_fraction": lambda payload: _first_snapshot(payload).__setitem__(
                "assigned_land_fraction", 0.9
            ),
            "fragmentation_index": lambda payload: _first_snapshot(payload).__setitem__(
                "fragmentation_index", 0.5
            ),
            "estimated_population": lambda payload: _first_snapshot(payload).__setitem__(
                "estimated_population", 0.0
            ),
            "id_key_removed": lambda payload: _first_snapshot(payload).pop("id"),
            "regions_key_removed": lambda payload: _first_snapshot(payload).pop("regions"),
        }
        for name, mutate in cases.items():
            with self.subTest(tamper=name):
                self.assertEqual(
                    validate_territorial_geography_replay(_tampered(mutate)), [FAILURE]
                )

    def test_nested_region_record_tampers_are_rejected(self) -> None:
        def scale(key: str, factor: float) -> Tamper:
            def mutate(payload: dict[str, Any]) -> None:
                region = _first_region(payload)
                region[key] = float(region[key]) * factor

            return mutate

        def shift(key: str, offset: float) -> Tamper:
            def mutate(payload: dict[str, Any]) -> None:
                region = _first_region(payload)
                region[key] = float(region[key]) + offset

            return mutate

        def shift_ring_latitude(payload: dict[str, Any]) -> None:
            point = _first_region(payload)["boundary_ring"][0]
            point[0] = float(point[0]) + 0.01

        def shift_ring_longitude(payload: dict[str, Any]) -> None:
            point = _first_region(payload)["boundary_ring"][0]
            point[1] = float(point[1]) + 0.01

        def rotate_ring(payload: dict[str, Any]) -> None:
            region = _first_region(payload)
            ring = region["boundary_ring"]
            region["boundary_ring"] = ring[1:] + ring[:1]

        def drop_ring_closure(payload: dict[str, Any]) -> None:
            region = _first_region(payload)
            region["boundary_ring"] = region["boundary_ring"][:-1]

        def flip_antimeridian(payload: dict[str, Any]) -> None:
            region = _first_region(payload)
            region["crosses_antimeridian"] = not bool(region["crosses_antimeridian"])

        def replace_boundary_cell_id(payload: dict[str, Any]) -> None:
            ids = _first_region(payload)["boundary_cell_ids"]
            ids[0] = max(int(value) for value in ids) + 1

        # Every key ``_region_matches`` compares -- exact, relative and absolute
        # tolerance alike -- has a vector here.
        cases: dict[str, Tamper] = {
            # The verified vector: a region area inside the nested region list.
            "area_km2": lambda payload: _first_region(payload).__setitem__("area_km2", 1.0),
            "region_id": lambda payload: _first_region(payload).__setitem__("region_id", 5),
            "capital_settlement_id": lambda payload: _first_region(payload).__setitem__(
                "capital_settlement_id", 2
            ),
            "cell_count": lambda payload: _first_region(payload).__setitem__(
                "cell_count", 999
            ),
            "culture_region_id": lambda payload: _first_region(payload).__setitem__(
                "culture_region_id", -1
            ),
            "language_region_id": lambda payload: _first_region(payload).__setitem__(
                "language_region_id", 4
            ),
            "crosses_antimeridian": flip_antimeridian,
            "estimated_population": lambda payload: _first_region(payload).__setitem__(
                "estimated_population", 0.0
            ),
            "boundary_perimeter_km": scale("boundary_perimeter_km", 2.0),
            "dissolved_polygon_area_km2": scale("dissolved_polygon_area_km2", 2.0),
            "polygon_area_error_fraction": lambda payload: _first_region(payload).__setitem__(
                "polygon_area_error_fraction", 0.0
            ),
            "geometry_quality": lambda payload: _first_region(payload).__setitem__(
                "geometry_quality", 1.0
            ),
            "stability_index": lambda payload: _first_region(payload).__setitem__(
                "stability_index", 0.123
            ),
            "compactness_index": lambda payload: _first_region(payload).__setitem__(
                "compactness_index", 0.9
            ),
            "centroid_lat_deg": shift("centroid_lat_deg", 0.5),
            "centroid_lon_deg": shift("centroid_lon_deg", 0.5),
            "area_km2_key_removed": lambda payload: _first_region(payload).pop("area_km2"),
            "boundary_ring_key_removed": lambda payload: _first_region(payload).pop(
                "boundary_ring"
            ),
            "boundary_ring_latitude": shift_ring_latitude,
            "boundary_ring_longitude": shift_ring_longitude,
            "boundary_ring_rotated": rotate_ring,
            "boundary_ring_shortened": drop_ring_closure,
            "boundary_ring_emptied": lambda payload: _first_region(payload).__setitem__(
                "boundary_ring", []
            ),
            "boundary_cell_ids_emptied": lambda payload: _first_region(
                payload
            ).__setitem__("boundary_cell_ids", []),
            "boundary_cell_ids_reordered": lambda payload: _first_region(payload)[
                "boundary_cell_ids"
            ].reverse(),
            "boundary_cell_ids_substituted": replace_boundary_cell_id,
            "boundary_cell_ids_extended": lambda payload: _first_region(payload)[
                "boundary_cell_ids"
            ].append(0),
        }
        for name, mutate in cases.items():
            with self.subTest(tamper=name):
                self.assertEqual(
                    validate_territorial_geography_replay(_tampered(mutate)), [FAILURE]
                )

    def test_snapshot_collection_shape_tampers_are_rejected(self) -> None:
        cases: dict[str, Tamper] = {
            # The verified vector: every snapshot removed.
            "snapshots_emptied": lambda payload: payload.__setitem__(
                "territorial_snapshots", []
            ),
            "snapshot_dropped": lambda payload: payload["territorial_snapshots"].pop(0),
            "extra_snapshot_appended": lambda payload: payload[
                "territorial_snapshots"
            ].append({}),
            "snapshots_reversed": lambda payload: payload[
                "territorial_snapshots"
            ].reverse(),
            "regions_emptied": lambda payload: _first_snapshot(payload).__setitem__(
                "regions", []
            ),
            "region_record_dropped": lambda payload: _first_snapshot(payload)[
                "regions"
            ].pop(0),
            "region_record_duplicated": lambda payload: _first_snapshot(payload)[
                "regions"
            ].append(dict(_first_region(payload))),
            "snapshots_not_a_list": lambda payload: payload.__setitem__(
                "territorial_snapshots", {"0": {}}
            ),
            "snapshot_record_not_a_mapping": lambda payload: payload[
                "territorial_snapshots"
            ].__setitem__(0, "not-a-snapshot"),
            "regions_not_a_list": lambda payload: _first_snapshot(payload).__setitem__(
                "regions", {"0": {}}
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(tamper=name):
                self.assertEqual(
                    validate_territorial_geography_replay(_tampered(mutate)), [FAILURE]
                )

    def test_upstream_world_tampers_are_rejected(self) -> None:
        """Edit the replay *inputs* and leave every snapshot record untouched.

        These are the cases a validator that only cross-checked the recorded
        snapshots against each other would miss: the recorded territory is
        unchanged and still internally consistent, but it is no longer the
        territory this world implies.
        """

        def flood_assigned_cell(payload: dict[str, Any]) -> None:
            _first_assigned_land_cell(payload)["is_water"] = True

        def unassign_cell(payload: dict[str, Any]) -> None:
            _first_assigned_land_cell(payload)["political_region_id"] = -1

        def grow_cell_area(payload: dict[str, Any]) -> None:
            cell = _first_assigned_land_cell(payload)
            cell["area_km2"] = float(cell["area_km2"]) * 1.5

        def move_cell(payload: dict[str, Any]) -> None:
            cell = _first_assigned_land_cell(payload)
            cell["lat_deg"] = float(cell["lat_deg"]) + 5.0

        def clear_every_neighbor_list(payload: dict[str, Any]) -> None:
            # Wipes the whole boundary-cell model: nothing borders water or
            # another region any more, so no ring can be rebuilt.
            for cell in payload["cells"]:
                cell["neighbors"] = []

        def shift_era_start(payload: dict[str, Any]) -> None:
            era = payload["historical_eras"][0]
            era["start_year_bp"] = float(era["start_year_bp"]) + 100.0

        def scale_population(payload: dict[str, Any]) -> None:
            region = payload["population_regions"][0]
            region["estimated_population"] = float(region["estimated_population"]) * 2.0

        def add_conflict(payload: dict[str, Any]) -> None:
            # Drives stability down, which rescales area, population and every
            # geometry aggregate derived from them.
            payload["conflicts"].append(
                {"era_id": 0, "region_a": 0, "region_b": 0, "intensity": 1.0}
            )

        def grow_planet(payload: dict[str, Any]) -> None:
            summary = payload["summary"]
            summary["surface_area_km2"] = float(summary["surface_area_km2"]) * 4.0

        cases: dict[str, Tamper] = {
            "cell_flooded": flood_assigned_cell,
            "cell_unassigned": unassign_cell,
            "cell_area_grown": grow_cell_area,
            "cell_moved": move_cell,
            "cells_emptied": lambda payload: payload.__setitem__("cells", []),
            "every_neighbor_list_cleared": clear_every_neighbor_list,
            "political_regions_emptied": lambda payload: payload.__setitem__(
                "political_regions", []
            ),
            "region_capital_changed": lambda payload: payload["political_regions"][
                0
            ].__setitem__("capital_settlement_id", 2),
            "cultures_emptied": lambda payload: payload.__setitem__("cultures", []),
            "culture_continuity_zeroed": lambda payload: payload["cultures"][
                0
            ].__setitem__("continuity_index", 0.0),
            "culture_homeland_detached": lambda payload: payload["cultures"][
                0
            ].__setitem__("homeland_region_id", -1),
            "culture_language_changed": lambda payload: payload["cultures"][
                0
            ].__setitem__("language_region_id", 7),
            "historical_eras_emptied": lambda payload: payload.__setitem__(
                "historical_eras", []
            ),
            "era_start_year_shifted": shift_era_start,
            "era_process_renamed": lambda payload: payload["historical_eras"][
                0
            ].__setitem__("dominant_process", "bogus_process"),
            "era_connectivity_raised": lambda payload: payload["historical_eras"][
                0
            ].__setitem__("mean_connectivity", 1.0),
            "era_id_changed": lambda payload: payload["historical_eras"][0].__setitem__(
                "id", 3
            ),
            "population_regions_emptied": lambda payload: payload.__setitem__(
                "population_regions", []
            ),
            "population_doubled": scale_population,
            "conflict_added": add_conflict,
            "planet_surface_area_grown": grow_planet,
        }
        for name, mutate in cases.items():
            with self.subTest(tamper=name):
                self.assertEqual(
                    validate_territorial_geography_replay(_tampered(mutate)), [FAILURE]
                )

    def test_model_and_summary_metadata_tampers_are_rejected(self) -> None:
        cases: dict[str, Tamper] = {
            # The verified vector: a wrong ``territorial_snapshot_model``.
            "model_type_renamed": lambda payload: payload[
                "territorial_snapshot_model"
            ].__setitem__("model_type", "hand_written_snapshots_v0"),
            "model_era_area_factors": lambda payload: payload[
                "territorial_snapshot_model"
            ].__setitem__("era_area_factors", [1.0, 1.0, 1.0, 1.0]),
            "model_ring_point_cap": lambda payload: payload[
                "territorial_snapshot_model"
            ].__setitem__("maximum_boundary_ring_points_before_closure", 32),
            "model_key_removed": lambda payload: payload[
                "territorial_snapshot_model"
            ].pop("perimeter_model"),
            "model_key_added": lambda payload: payload[
                "territorial_snapshot_model"
            ].__setitem__("undeclared_key", True),
            "model_removed": lambda payload: payload.pop("territorial_snapshot_model"),
            "summary_model_renamed": lambda payload: payload["summary"].__setitem__(
                "territorial_snapshot_model", "hand_written_snapshots_v0"
            ),
            "summary_model_removed": lambda payload: payload["summary"].pop(
                "territorial_snapshot_model"
            ),
            "summary_snapshot_count": lambda payload: payload["summary"].__setitem__(
                "territorial_snapshot_count", 999
            ),
            "summary_region_record_count": lambda payload: payload["summary"].__setitem__(
                "snapshot_region_record_count", 0
            ),
            "summary_polygon_region_count": lambda payload: payload["summary"].__setitem__(
                "snapshot_polygon_region_count", 0
            ),
            "summary_count_removed": lambda payload: payload["summary"].pop(
                "snapshot_region_record_count"
            ),
            # All five ``mean_snapshot_*`` aggregates the validator recomputes.
            "summary_mean_fragmentation_index": lambda payload: payload[
                "summary"
            ].__setitem__("mean_snapshot_fragmentation_index", 0.5),
            "summary_mean_polygon_area_error_fraction": lambda payload: payload[
                "summary"
            ].__setitem__("mean_snapshot_polygon_area_error_fraction", 0.0),
            "summary_mean_compactness_index": lambda payload: payload[
                "summary"
            ].__setitem__("mean_snapshot_compactness_index", 0.5),
            "summary_mean_geometry_quality": lambda payload: payload["summary"].__setitem__(
                "mean_snapshot_geometry_quality", 0.111
            ),
            "summary_mean_boundary_perimeter_km": lambda payload: payload[
                "summary"
            ].__setitem__("mean_snapshot_boundary_perimeter_km", 1.0),
            "summary_mean_removed": lambda payload: payload["summary"].pop(
                "mean_snapshot_fragmentation_index"
            ),
        }
        for name, mutate in cases.items():
            with self.subTest(tamper=name):
                self.assertEqual(
                    validate_territorial_geography_replay(_tampered(mutate)), [FAILURE]
                )

    def test_malformed_payloads_are_stopped_by_the_shape_guards(self) -> None:
        # None of these reach the replay: each one trips a guard in
        # ``_replay_valid`` before any rebuilding happens.  The payloads that do
        # reach the replay and raise are covered by the next test.
        payloads: dict[str, dict[str, Any]] = {
            "empty": {},
            "summary_not_a_mapping": {"summary": None},
            "collections_missing": {"summary": {}},
            "snapshots_not_a_list": {"summary": {}, "territorial_snapshots": {}},
            "snapshot_records_not_mappings": {
                "summary": {},
                "territorial_snapshots": [1, 2],
            },
            "cells_not_a_list": {"summary": {}, "cells": "nope"},
            # The summary advertises the model but the payload carries no
            # ``territorial_snapshot_model`` block, which is what this is
            # rejected for -- an empty world is not by itself a failure.
            "summary_model_without_model_block": {
                "summary": {"territorial_snapshot_model": TERRITORIAL_SNAPSHOT_MODEL},
                "cells": [],
                "political_regions": [],
                "settlements": [],
                "cultures": [],
                "historical_eras": [],
                "population_regions": [],
                "conflicts": [],
                "territorial_snapshots": [],
            },
        }
        for name, payload in payloads.items():
            with self.subTest(payload=name):
                self.assertIs(
                    _replay_valid(payload), False, "must be rejected without raising"
                )
                self.assertEqual(validate_territorial_geography_replay(payload), [FAILURE])

    def test_replay_exceptions_are_swallowed_by_the_entry_point(self) -> None:
        """The entry point must convert replay crashes into the failure string.

        ``magic_geo.cli`` calls this from ``validate``, so a payload that makes
        the rebuild blow up has to come back as ``FAILURE`` rather than an
        unhandled traceback.  Each case first asserts that the replay really
        does raise -- otherwise the case would silently degrade into yet another
        shape-guard test and stop covering the ``except`` clause at all.

        ``ZeroDivisionError`` is also caught by the entry point but has no known
        trigger: every division in the module is guarded by a positive check.
        """

        def model_only() -> dict[str, Any]:
            model = dict(worlds.cached_world(CANONICAL_WORLD)["territorial_snapshot_model"])
            return {
                "summary": {"territorial_snapshot_model": TERRITORIAL_SNAPSHOT_MODEL},
                "territorial_snapshot_model": model,
            }

        def cell_without_position() -> dict[str, Any]:
            return _tampered(
                lambda payload: _first_assigned_land_cell(payload).pop("position_3d")
            )

        def cell_area_not_a_number() -> dict[str, Any]:
            return _tampered(
                lambda payload: _first_assigned_land_cell(payload).__setitem__(
                    "area_km2", None
                )
            )

        def region_id_out_of_range() -> dict[str, Any]:
            return _tampered(
                lambda payload: payload["political_regions"][0].__setitem__("id", 5)
            )

        cases: dict[str, tuple[Callable[[], dict[str, Any]], type[Exception], str]] = {
            # KeyError: the replay reads collections the shape guards defaulted.
            "historical_eras_key_absent": (model_only, KeyError, "historical_eras"),
            # ValueError: raised by the module's own position guard.
            "cell_position_missing": (
                cell_without_position,
                ValueError,
                "cell position missing",
            ),
            # TypeError: a non-numeric area reaches ``float()``.
            "cell_area_is_none": (cell_area_not_a_number, TypeError, "NoneType"),
            # IndexError: a region id outside the rebuilt per-region arrays.
            "region_id_out_of_range": (
                region_id_out_of_range,
                IndexError,
                "list index out of range",
            ),
        }
        for name, (build, exception, message) in cases.items():
            with self.subTest(payload=name):
                with self.assertRaisesRegex(exception, message):
                    _replay_valid(build())
                self.assertEqual(
                    validate_territorial_geography_replay(build()), [FAILURE]
                )
