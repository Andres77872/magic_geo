"""Violation and subsystem-absent branches of the water replay validators.

Covers ``magic_geo.cli.validators.hydrology`` (water budget, groundwater
recharge, aquifer resources, groundwater flow), ``...validators.rivers``
(channel morphology and hydraulics) and ``...validators.navigability``.

Every check is driven through the public ``validate`` CLI on a temporary world
file: one tamper per branch, asserting the exact failure text plus a clean
``typer.Exit(1)`` from the validation gate, against an untampered control run
that passes.  A small number of ``except (TypeError, ValueError)`` guards cannot
be reached that way because the ``validate`` command itself parses the same
field with a bare ``float()`` and dies before the validator is consulted; those
call the validator directly and assert its exact return value.

Exit code alone never decides a case: ``CliRunner`` reports ``exit_code == 1``
both for a clean ``FAIL``/``Exit(1)`` and for an uncaught ``ValueError``, so
every CLI assertion pins the failure text *and* requires the command to have
left through ``SystemExit`` rather than crashing.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.cli.validators import (
    _validate_aquifer_resources,
    _validate_groundwater_flow,
    _validate_groundwater_recharge,
    _validate_hydrologic_water_budget,
    _validate_navigability,
    _validate_river_channel_morphology,
    _validate_river_hydraulics,
)
from magic_geo.navigability_diagnostics import (
    enrich_world_with_navigability_diagnostics,
)

from support import worlds

WATER_BUDGET_FAILURE = "hydrologic water budget model or replay invalid"
RECHARGE_FAILURE = "groundwater recharge model or source partition invalid"
AQUIFER_FAILURE = "aquifer resource model or causal replay invalid"
GROUNDWATER_FLOW_FAILURE = "groundwater flow model or routing replay invalid"
CHANNEL_FAILURE = "river channel morphology model or causal replay invalid"
HYDRAULICS_FAILURE = "river hydraulics model or causal replay invalid"
NAVIGABILITY_FAILURE = "navigability model or causal replay invalid"

World = dict[str, Any]
Tamper = Callable[[World], None]


def _run_validate(world: World) -> Any:
    """Write ``world`` to a temporary file and run ``validate`` over it."""

    with TemporaryDirectory() as temporary_directory:
        world_path = Path(temporary_directory) / "world.json"
        world_path.write_text(json.dumps(world), encoding="utf-8")
        return CliRunner().invoke(app, ["validate", "--world", str(world_path)])


def _direct_failures(validator: Callable[..., list[str]], world: World) -> list[str]:
    cells_by_id = {int(cell["id"]): cell for cell in world["cells"]}
    return validator(world, world["summary"], cells_by_id)


def _fail_lines(result: Any) -> list[str]:
    return [line for line in result.output.splitlines() if line.startswith("FAIL ")]


def _land_cell(world: World) -> dict[str, Any]:
    return next(
        cell
        for cell in world["cells"]
        if not cell["is_water"] and cell["water_body_type"] == "land"
    )


def _marine_cell(world: World) -> dict[str, Any]:
    return next(cell for cell in world["cells"] if cell["water_body_type"] == "ocean")


def _river_cells(world: World) -> list[dict[str, Any]]:
    return [cell for cell in world["cells"] if cell["is_river"] and not cell["is_water"]]


def _ice_free_river_cell(world: World) -> dict[str, Any]:
    return next(cell for cell in _river_cells(world) if cell["ice_thickness_m"] == 0.0)


def _quietest_river_cell(world: World) -> dict[str, Any]:
    return min(
        (cell for cell in _river_cells(world) if cell["ice_thickness_m"] == 0.0),
        key=lambda cell: float(cell["flow_accumulation"]),
    )


def _force_froude(world: World, target: float) -> None:
    """Saturate channel velocity and pick the depth that lands on ``target``."""

    model = world["river_hydraulics_model"]
    gravity = float(model["gravity_m_s2"])
    maximum_velocity = float(model["maximum_velocity_m_s"])
    cell = _ice_free_river_cell(world)
    cell["river_channel_depth_m"] = (maximum_velocity / target) ** 2 / gravity
    cell["bankfull_discharge_m3_s"] = 1.0e9


class WaterValidatorCliCase(TestCase):
    """Shared tamper-then-validate driver for the CLI-reachable branches."""

    world_key = "replay_128"

    def assert_clean_validation_failure(self, result: Any) -> None:
        """The command must have reached the ``FAIL`` gate, not crashed.

        ``CliRunner`` turns an uncaught exception into ``exit_code == 1`` as
        well, so the exit code on its own cannot tell a rejected world from a
        traceback.  ``typer.Exit(1)`` surfaces as ``SystemExit``.
        """

        self.assertIsInstance(result.exception, SystemExit, result.exception)
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertNotEqual(_fail_lines(result), [], result.output)

    def assert_tamper_reported(
        self,
        tamper: Tamper,
        message: str,
        *,
        absent: str | None = None,
    ) -> None:
        world = worlds.cached_world(self.world_key)
        tamper(world)
        result = _run_validate(world)
        self.assert_clean_validation_failure(result)
        self.assertIn(f"FAIL {message}", _fail_lines(result))
        if absent is not None:
            self.assertNotIn(f"FAIL {absent}", _fail_lines(result))

    def assert_all_tampers_reported(
        self,
        cases: tuple[tuple[str, Tamper], ...],
        message: str,
    ) -> None:
        for label, tamper in cases:
            with self.subTest(tamper=label):
                self.assert_tamper_reported(tamper, message)


class WaterValidatorControlTests(TestCase):
    def test_untampered_world_passes_validate(self) -> None:
        result = _run_validate(worlds.cached_world_readonly("replay_128"))

        self.assertIsNone(result.exception)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(result.output.strip(), "OK")

    def test_untampered_world_passes_every_water_validator_directly(self) -> None:
        """The exact-``[message]`` assertions below only mean something if the
        pristine world makes every one of these validators return ``[]``."""

        world = worlds.cached_world_readonly("replay_128")

        for name, validator in (
            ("water_budget", _validate_hydrologic_water_budget),
            ("recharge", _validate_groundwater_recharge),
            ("aquifer", _validate_aquifer_resources),
            ("groundwater_flow", _validate_groundwater_flow),
            ("channel_morphology", _validate_river_channel_morphology),
            ("hydraulics", _validate_river_hydraulics),
            ("navigability", _validate_navigability),
        ):
            with self.subTest(validator=name):
                self.assertEqual(_direct_failures(validator, world), [])

    def test_control_world_exercises_every_water_subsystem(self) -> None:
        world = worlds.cached_world_readonly("replay_128")
        summary = world["summary"]

        self.assertGreater(len(_river_cells(world)), 0)
        self.assertGreater(len(world["river_channel_systems"]), 0)
        self.assertGreater(len(world["river_hydraulic_reaches"]), 0)
        self.assertGreater(len(world["navigable_waterways"]), 0)
        self.assertGreater(len(world["aquifer_systems"]), 0)
        self.assertGreater(len(world["marine_chokepoints"]), 0)
        self.assertGreater(len(world["hydrologic_water_budget_history"]), 0)
        self.assertGreater(len(world["earth_system_feedback_history"]), 0)
        self.assertGreater(len(world["settlements"]), 0)
        self.assertGreater(len(world["routes"]), 0)
        self.assertEqual(
            summary["hydrologic_water_budget_model"],
            "causal_land_climate_loss_partition_v1",
        )
        self.assertEqual(
            summary["navigability_model"],
            "causal_channel_hydraulic_coastal_navigability_v1",
        )

    def test_control_world_supports_every_tamper_helper(self) -> None:
        """Pin the structural assumptions the tampers below are built on.

        Each of these is a way a regenerated fixture could silently turn a
        tamper into a no-op (or into a different tamper than the one named).
        """

        world = worlds.cached_world_readonly("replay_128")
        cells = world["cells"]

        # ``river_cell_on_top_of_downstream`` reads the downstream cell as
        # ``world["cells"][flow_to]``, i.e. it assumes id == list position.
        for position, cell in enumerate(cells):
            self.assertEqual(int(cell["id"]), position)

        # ``_ice_free_river_cell`` / ``_quietest_river_cell`` must both resolve,
        # and the chosen cell must really flow to a *different* cell so that
        # zeroing ``flow_to`` and collapsing the two positions are distinct
        # tampers rather than accidental no-ops.
        headwater = _ice_free_river_cell(world)
        self.assertEqual(float(headwater["ice_thickness_m"]), 0.0)
        downstream_id = int(headwater["flow_to"])
        self.assertNotEqual(downstream_id, -1)
        self.assertNotEqual(downstream_id, int(headwater["id"]))
        downstream = cells[downstream_id]
        self.assertNotEqual(
            (headwater["lat_deg"], headwater["lon_deg"]),
            (downstream["lat_deg"], downstream["lon_deg"]),
        )

        quiet = _quietest_river_cell(world)
        self.assertGreater(float(quiet["flow_accumulation"]), 0.0)

        # The classification tampers only move a cell into a *new* class if it
        # is not already in it.
        self.assertNotEqual(headwater["channel_morphology_class"], "ephemeral_wadi")
        self.assertNotEqual(
            headwater["channel_morphology_class"], "incised_bedrock_channel"
        )
        self.assertNotEqual(quiet["channel_morphology_class"], "small_headwater")
        self.assertEqual(headwater["hydraulic_flow_regime"], "subcritical")

        # ``extra_channel_system`` / ``channel_system_without_cells`` copy
        # ``river_channel_systems[0]``: it must carry cells to begin with.
        self.assertGreater(len(world["river_channel_systems"][0]["cell_ids"]), 0)

        # ``_land_cell`` and ``_marine_cell`` must both resolve, with a land
        # cell that is genuinely inland (the ``distance_to_marine_water_km``
        # tamper lowers that distance to 10 km).
        land = _land_cell(world)
        self.assertGreater(float(land["area_km2"]), 0.0)
        self.assertGreater(float(land["distance_to_marine_water_km"]), 10.0)
        self.assertTrue(_marine_cell(world)["is_water"])


class HydrologicWaterBudgetValidatorTests(WaterValidatorCliCase):
    def test_water_budget_replay_violations_are_reported(self) -> None:
        def model_domain(world: World) -> None:
            world["hydrologic_water_budget_model"]["domain"] = "tampered_domain"

        def clock_timestep_not_numeric(world: World) -> None:
            world["simulation_clock"]["nominal_timestep_ma"] = "later"

        def clock_timestep_not_positive(world: World) -> None:
            world["simulation_clock"]["nominal_timestep_ma"] = 0.0

        def duplicate_feedback_stage(world: World) -> None:
            history = world["earth_system_feedback_history"]
            history.append(copy.deepcopy(history[-1]))

        def history_stage_not_a_mapping(world: World) -> None:
            world["hydrologic_water_budget_history"].append(None)
            world["hydrologic_water_budget_model"]["history_stage_count"] += 1

        def stage_cell_count_mismatch(world: World) -> None:
            world["hydrologic_water_budget_history"][-1]["cell_count"] = 999

        def stage_duplicate_cell_id(world: World) -> None:
            stage = world["hydrologic_water_budget_history"][-1]
            stage["cell_ids"][0] = stage["cell_ids"][1]

        def stage_marine_flag_out_of_range(world: World) -> None:
            world["hydrologic_water_budget_history"][-1]["is_marine_by_cell"][0] = 7

        def stage_relief_inconsistent(world: World) -> None:
            world["hydrologic_water_budget_history"][-1]["local_relief_m_by_cell"][
                0
            ] += 10.0

        def stage_land_cell_count(world: World) -> None:
            world["hydrologic_water_budget_history"][-1]["land_cell_count"] += 1

        def feedback_recompute_count(world: World) -> None:
            world["earth_system_feedback_history"][-1][
                "hydrologic_water_budget_recompute_count"
            ] += 1

        def model_final_land_cell_count(world: World) -> None:
            world["hydrologic_water_budget_model"]["final_land_cell_count"] += 1

        def stage_id_not_numeric(world: World) -> None:
            world["hydrologic_water_budget_history"][0]["id"] = "first"

        def stage_cell_id_not_numeric(world: World) -> None:
            world["hydrologic_water_budget_history"][-1]["cell_ids"][0] = "first"

        self.assert_all_tampers_reported(
            (
                ("model_domain", model_domain),
                ("clock_timestep_not_numeric", clock_timestep_not_numeric),
                ("clock_timestep_not_positive", clock_timestep_not_positive),
                ("duplicate_feedback_stage", duplicate_feedback_stage),
                ("history_stage_not_a_mapping", history_stage_not_a_mapping),
                ("stage_cell_count_mismatch", stage_cell_count_mismatch),
                ("stage_duplicate_cell_id", stage_duplicate_cell_id),
                ("stage_marine_flag_out_of_range", stage_marine_flag_out_of_range),
                ("stage_relief_inconsistent", stage_relief_inconsistent),
                ("stage_land_cell_count", stage_land_cell_count),
                ("feedback_recompute_count", feedback_recompute_count),
                ("model_final_land_cell_count", model_final_land_cell_count),
                # Both stage-id guards *are* reachable from the CLI: the
                # command never re-parses those two fields itself, so the
                # validator's ``except (TypeError, ValueError)`` returns a
                # normal FAIL line instead of the command dying.
                ("stage_id_not_numeric", stage_id_not_numeric),
                ("stage_cell_id_not_numeric", stage_cell_id_not_numeric),
            ),
            WATER_BUDGET_FAILURE,
        )


class GroundwaterRechargeValidatorTests(WaterValidatorCliCase):
    def test_recharge_partition_violations_are_reported(self) -> None:
        def model_domain(world: World) -> None:
            world["groundwater_recharge_model"]["domain"] = "tampered_domain"

        def cell_vadose_retention_not_numeric(world: World) -> None:
            _land_cell(world)["vadose_zone_retention_mm_y"] = "wet"

        def summary_vadose_total(world: World) -> None:
            world["summary"]["total_vadose_zone_retention_km3_y"] += 1.0

        def summary_total_infiltration(world: World) -> None:
            summary = world["summary"]
            summary["total_infiltration_km3_y"] = (
                float(summary["total_infiltration_km3_y"]) * 2.0 + 1.0
            )

        self.assert_all_tampers_reported(
            (
                ("model_domain", model_domain),
                (
                    "cell_vadose_retention_not_numeric",
                    cell_vadose_retention_not_numeric,
                ),
                ("summary_vadose_total", summary_vadose_total),
                ("summary_total_infiltration", summary_total_infiltration),
            ),
            RECHARGE_FAILURE,
        )

    def test_zero_area_land_cell_breaks_recharge_and_groundwater_flow(self) -> None:
        """One tamper, two independent area guards.

        Both validators divide per-cell volumes by ``area_km2``; a zero-area
        land cell has to be rejected rather than divided by, which is why this
        insists on a clean ``FAIL`` gate and not merely a non-zero exit.
        """

        world = worlds.cached_world(self.world_key)
        _land_cell(world)["area_km2"] = 0.0

        result = _run_validate(world)

        self.assert_clean_validation_failure(result)
        self.assertIn(f"FAIL {RECHARGE_FAILURE}", _fail_lines(result))
        self.assertIn(f"FAIL {GROUNDWATER_FLOW_FAILURE}", _fail_lines(result))


class AquiferResourceValidatorTests(WaterValidatorCliCase):
    def test_aquifer_replay_violations_are_reported(self) -> None:
        def model_minimum_productivity_not_numeric(world: World) -> None:
            world["aquifer_resource_model"][
                "minimum_system_productivity_index"
            ] = "high"

        def cell_soil_salinity(world: World) -> None:
            _land_cell(world)["soil_salinity_index"] = 0.95

        def cell_system_id(world: World) -> None:
            _land_cell(world)["aquifer_system_id"] = 999

        def extra_aquifer_system(world: World) -> None:
            systems = world["aquifer_systems"]
            systems.append(copy.deepcopy(systems[0]))

        def model_aquifer_cell_count(world: World) -> None:
            world["aquifer_resource_model"]["aquifer_cell_count"] += 1

        def summary_mean_quality(world: World) -> None:
            world["summary"]["mean_aquifer_quality_index"] += 0.5

        self.assert_all_tampers_reported(
            (
                (
                    "model_minimum_productivity_not_numeric",
                    model_minimum_productivity_not_numeric,
                ),
                ("cell_soil_salinity", cell_soil_salinity),
                ("cell_system_id", cell_system_id),
                ("extra_aquifer_system", extra_aquifer_system),
                ("model_aquifer_cell_count", model_aquifer_cell_count),
                ("summary_mean_quality", summary_mean_quality),
            ),
            AQUIFER_FAILURE,
        )


class GroundwaterFlowValidatorTests(WaterValidatorCliCase):
    def test_groundwater_flow_replay_violations_are_reported(self) -> None:
        def model_domain(world: World) -> None:
            world["groundwater_flow_model"]["domain"] = "tampered_domain"

        def model_candidate_cell_count(world: World) -> None:
            world["groundwater_flow_model"]["candidate_cell_count"] += 1

        def marine_cell_not_flagged_as_water(world: World) -> None:
            _marine_cell(world)["is_water"] = False

        def cell_close_to_marine_water(world: World) -> None:
            _land_cell(world)["distance_to_marine_water_km"] = 10.0

        def cell_flow_target(world: World) -> None:
            _land_cell(world)["groundwater_flow_to_cell_id"] = 12345

        def summary_retained_storage(world: World) -> None:
            world["summary"]["total_groundwater_retained_storage_km3_y"] += 1.0

        self.assert_all_tampers_reported(
            (
                ("model_domain", model_domain),
                ("model_candidate_cell_count", model_candidate_cell_count),
                (
                    "marine_cell_not_flagged_as_water",
                    marine_cell_not_flagged_as_water,
                ),
                ("cell_close_to_marine_water", cell_close_to_marine_water),
                ("cell_flow_target", cell_flow_target),
                ("summary_retained_storage", summary_retained_storage),
            ),
            GROUNDWATER_FLOW_FAILURE,
        )


class RiverChannelMorphologyValidatorTests(WaterValidatorCliCase):
    def test_channel_morphology_violations_are_reported(self) -> None:
        def model_slope_normalization_not_numeric(world: World) -> None:
            world["river_channel_morphology_model"]["slope_normalization"] = "steep"

        def river_cell_without_downstream(world: World) -> None:
            _ice_free_river_cell(world)["flow_to"] = -1

        def river_cell_on_top_of_downstream(world: World) -> None:
            cell = _ice_free_river_cell(world)
            downstream = world["cells"][int(cell["flow_to"])]
            cell["lat_deg"] = downstream["lat_deg"]
            cell["lon_deg"] = downstream["lon_deg"]

        def arid_channel_without_runoff(world: World) -> None:
            cell = _ice_free_river_cell(world)
            cell["seasonal_aridity_index"] = 0.95
            cell["runoff_mm_y"] = 10.0

        def steep_sediment_free_channel(world: World) -> None:
            cell = _ice_free_river_cell(world)
            cell["hydrologic_surface_elevation_m"] = (
                float(cell["hydrologic_surface_elevation_m"]) + 200000.0
            )
            cell["fluvial_sediment_routed_outgoing_m"] = 0.0
            cell["sediment_deposition_m"] = 0.0
            cell["sediment_thickness_m"] = 0.0

        def channel_without_flow_accumulation(world: World) -> None:
            _quietest_river_cell(world)["flow_accumulation"] = 0.0

        def cell_channel_system_id(world: World) -> None:
            _ice_free_river_cell(world)["river_channel_system_id"] = 99

        def extra_channel_system(world: World) -> None:
            systems = world["river_channel_systems"]
            systems.append(copy.deepcopy(systems[0]))

        def model_system_count(world: World) -> None:
            world["river_channel_morphology_model"]["system_count"] += 1

        def summary_floodplain_connected_count(world: World) -> None:
            world["summary"]["floodplain_connected_channel_cell_count"] += 1

        self.assert_all_tampers_reported(
            (
                (
                    "model_slope_normalization_not_numeric",
                    model_slope_normalization_not_numeric,
                ),
                ("river_cell_without_downstream", river_cell_without_downstream),
                (
                    "river_cell_on_top_of_downstream",
                    river_cell_on_top_of_downstream,
                ),
                ("arid_channel_without_runoff", arid_channel_without_runoff),
                ("steep_sediment_free_channel", steep_sediment_free_channel),
                (
                    "channel_without_flow_accumulation",
                    channel_without_flow_accumulation,
                ),
                ("cell_channel_system_id", cell_channel_system_id),
                ("extra_channel_system", extra_channel_system),
                ("model_system_count", model_system_count),
                (
                    "summary_floodplain_connected_count",
                    summary_floodplain_connected_count,
                ),
            ),
            CHANNEL_FAILURE,
        )


class RiverHydraulicsValidatorTests(WaterValidatorCliCase):
    def test_hydraulics_violations_are_reported(self) -> None:
        def model_water_density_not_numeric(world: World) -> None:
            world["river_hydraulics_model"]["water_density_kg_m3"] = "dense"

        def supercritical_channel(world: World) -> None:
            _force_froude(world, 1.2)

        def transitional_channel(world: World) -> None:
            _force_froude(world, 0.9)

        def extra_hydraulic_reach(world: World) -> None:
            reaches = world["river_hydraulic_reaches"]
            reaches.append(copy.deepcopy(reaches[0]))

        def reach_navigable_cell_count(world: World) -> None:
            world["river_hydraulic_reaches"][0][
                "hydraulically_navigable_cell_count"
            ] += 1

        def model_reach_count(world: World) -> None:
            world["river_hydraulics_model"]["reach_count"] += 1

        def summary_supercritical_count(world: World) -> None:
            world["summary"]["supercritical_flow_cell_count"] += 1

        self.assert_all_tampers_reported(
            (
                (
                    "model_water_density_not_numeric",
                    model_water_density_not_numeric,
                ),
                ("supercritical_channel", supercritical_channel),
                ("transitional_channel", transitional_channel),
                ("extra_hydraulic_reach", extra_hydraulic_reach),
                ("reach_navigable_cell_count", reach_navigable_cell_count),
                ("model_reach_count", model_reach_count),
                ("summary_supercritical_count", summary_supercritical_count),
            ),
            HYDRAULICS_FAILURE,
        )

    def test_channel_system_without_channel_cells_is_skipped_by_reaches(self) -> None:
        def channel_system_without_cells(world: World) -> None:
            systems = world["river_channel_systems"]
            empty = copy.deepcopy(systems[0])
            empty["cell_ids"] = []
            systems.append(empty)

        # The extra system has no channel cells, so the reach model skips it and
        # only the morphology replay notices the surplus record.
        self.assert_tamper_reported(
            channel_system_without_cells,
            CHANNEL_FAILURE,
            absent=HYDRAULICS_FAILURE,
        )


class NavigabilityValidatorTests(WaterValidatorCliCase):
    def test_navigability_violations_are_reported(self) -> None:
        def model_threshold_not_numeric(world: World) -> None:
            world["navigability_model"]["navigable_threshold"] = "high"

        def cell_waterway_id(world: World) -> None:
            world["cells"][0]["navigable_waterway_id"] = 999

        def extra_waterway(world: World) -> None:
            waterways = world["navigable_waterways"]
            waterways.append(copy.deepcopy(waterways[0]))

        def model_waterway_count(world: World) -> None:
            world["navigability_model"]["waterway_count"] += 1

        def summary_high_harbor_count(world: World) -> None:
            world["summary"]["high_harbor_suitability_cell_count"] += 1

        self.assert_all_tampers_reported(
            (
                ("model_threshold_not_numeric", model_threshold_not_numeric),
                ("cell_waterway_id", cell_waterway_id),
                ("extra_waterway", extra_waterway),
                ("model_waterway_count", model_waterway_count),
                ("summary_high_harbor_count", summary_high_harbor_count),
            ),
            NAVIGABILITY_FAILURE,
        )


class ChokepointFreeNavigabilityTests(WaterValidatorCliCase):
    """Waterway typing when the marine chokepoint subsystem is absent.

    With no chokepoint records at all every component falls through to the
    harbor / river-mouth / river / coastal fallbacks, which is the only way the
    ``harbor_cluster`` and ``river_mouth_corridor`` labels are produced.
    """

    #: Emptying ``marine_chokepoints`` necessarily invalidates the chokepoint
    #: subsystem.  Requiring this exact line proves the run reached the
    #: ``FAIL``/``Exit(1)`` gate, which is what makes the *absence* of the
    #: navigability line below evidence of anything at all.
    CHOKEPOINT_FAILURE = "marine_chokepoint_count does not match marine_chokepoints length"

    def build_world(self) -> World:
        world = worlds.cached_world("routed_512")
        world["marine_chokepoints"] = []
        enrich_world_with_navigability_diagnostics(world)
        return world

    def test_pristine_routed_world_passes_validate(self) -> None:
        """Without this the "still invalid overall" runs below prove nothing."""

        result = _run_validate(worlds.cached_world_readonly("routed_512"))

        self.assertIsNone(result.exception)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(result.output.strip(), "OK")

    def test_absent_chokepoints_yield_harbor_and_river_mouth_waterways(self) -> None:
        world = self.build_world()

        waterway_types = {
            waterway["waterway_type"] for waterway in world["navigable_waterways"]
        }
        self.assertIn("harbor_cluster", waterway_types)
        self.assertIn("river_mouth_corridor", waterway_types)
        # No chokepoint records means the top-priority label is unreachable, so
        # the harbor / river-mouth fallbacks really are what produced the two
        # labels above.
        self.assertNotIn("transport_chokepoint", waterway_types)

        result = _run_validate(world)

        # The chokepoint subsystem is gone, so the world as a whole is invalid,
        # but the navigability replay itself still reproduces every record.
        self.assert_clean_validation_failure(result)
        self.assertIn(f"FAIL {self.CHOKEPOINT_FAILURE}", _fail_lines(result))
        self.assertNotIn(f"FAIL {NAVIGABILITY_FAILURE}", _fail_lines(result))

    def test_mislabelled_harbor_cluster_is_rejected(self) -> None:
        world = self.build_world()
        harbor_cluster = next(
            waterway
            for waterway in world["navigable_waterways"]
            if waterway["waterway_type"] == "harbor_cluster"
        )
        harbor_cluster["waterway_type"] = "coastal_corridor"

        result = _run_validate(world)

        self.assert_clean_validation_failure(result)
        # Same world as the test above, one label changed: the navigability
        # line is now present where it was absent before.
        self.assertIn(f"FAIL {self.CHOKEPOINT_FAILURE}", _fail_lines(result))
        self.assertIn(f"FAIL {NAVIGABILITY_FAILURE}", _fail_lines(result))


class WaterValidatorDirectGuardTests(TestCase):
    """Guards the ``validate`` command cannot reach.

    ``validate`` parses these very fields with a bare ``float()``/``int()`` (or
    indexes ``cells_by_id`` directly) before or after the validator runs, so a
    non-numeric value or a dangling neighbour id aborts the command with an
    exception instead of a ``FAIL`` line.  The validators themselves degrade
    gracefully, which is what these cases pin down.

    Every tamper here was checked against the CLI first: each one makes
    ``validate`` raise ``ValueError``/``AttributeError``/``KeyError`` and print
    no ``FAIL`` line at all.  ``WaterValidatorCliCase`` owns anything the CLI
    can actually report.
    """

    def assert_guard(
        self,
        validator: Callable[..., list[str]],
        tamper: Tamper,
        message: str,
    ) -> None:
        world = worlds.cached_world("replay_128")
        tamper(world)
        self.assertEqual(_direct_failures(validator, world), [message])

    def test_water_budget_guards(self) -> None:
        def neighbour_outside_mesh(world: World) -> None:
            # ``validate`` indexes ``cells_by_id[neighbor]`` itself and dies
            # with ``KeyError(9999)`` before printing anything.
            _land_cell(world)["neighbors"].append(9999)

        for label, tamper in (("neighbour_outside_mesh", neighbour_outside_mesh),):
            with self.subTest(tamper=label):
                self.assert_guard(
                    _validate_hydrologic_water_budget, tamper, WATER_BUDGET_FAILURE
                )

    def test_aquifer_guards(self) -> None:
        def soil_drainage_not_numeric(world: World) -> None:
            _land_cell(world)["soil_drainage_index"] = "well_drained"

        def storage_index_not_numeric(world: World) -> None:
            _land_cell(world)["aquifer_storage_index"] = "large"

        def system_id_not_numeric(world: World) -> None:
            _land_cell(world)["aquifer_system_id"] = "first"

        for label, tamper in (
            ("soil_drainage_not_numeric", soil_drainage_not_numeric),
            ("storage_index_not_numeric", storage_index_not_numeric),
            ("system_id_not_numeric", system_id_not_numeric),
        ):
            with self.subTest(tamper=label):
                self.assert_guard(_validate_aquifer_resources, tamper, AQUIFER_FAILURE)

    def test_groundwater_flow_guards(self) -> None:
        def neighbours_not_a_list(world: World) -> None:
            _land_cell(world)["neighbors"] = "north"

        def neighbour_outside_mesh(world: World) -> None:
            _land_cell(world)["neighbors"].append(9999)

        def hydraulic_head_not_numeric(world: World) -> None:
            _land_cell(world)["groundwater_hydraulic_head_m"] = "high"

        for label, tamper in (
            ("neighbours_not_a_list", neighbours_not_a_list),
            ("neighbour_outside_mesh", neighbour_outside_mesh),
            ("hydraulic_head_not_numeric", hydraulic_head_not_numeric),
        ):
            with self.subTest(tamper=label):
                self.assert_guard(
                    _validate_groundwater_flow, tamper, GROUNDWATER_FLOW_FAILURE
                )

    def test_channel_morphology_guards(self) -> None:
        def flow_accumulation_not_numeric(world: World) -> None:
            _land_cell(world)["flow_accumulation"] = "lots"

        def wetland_extent_not_numeric(world: World) -> None:
            _ice_free_river_cell(world)["wetland_extent_index"] = "boggy"

        def channel_width_not_numeric(world: World) -> None:
            _ice_free_river_cell(world)["river_channel_width_m"] = "wide"

        def neighbours_not_a_list(world: World) -> None:
            _ice_free_river_cell(world)["neighbors"] = "downstream"

        def channel_system_id_not_numeric(world: World) -> None:
            _ice_free_river_cell(world)["river_channel_system_id"] = "first"

        for label, tamper in (
            ("flow_accumulation_not_numeric", flow_accumulation_not_numeric),
            ("wetland_extent_not_numeric", wetland_extent_not_numeric),
            ("channel_width_not_numeric", channel_width_not_numeric),
            ("neighbours_not_a_list", neighbours_not_a_list),
            ("channel_system_id_not_numeric", channel_system_id_not_numeric),
        ):
            with self.subTest(tamper=label):
                self.assert_guard(
                    _validate_river_channel_morphology, tamper, CHANNEL_FAILURE
                )

    def test_hydraulics_guards(self) -> None:
        def channel_slope_not_numeric(world: World) -> None:
            _ice_free_river_cell(world)["channel_slope_index"] = "steep"

        def froude_number_not_numeric(world: World) -> None:
            _ice_free_river_cell(world)["froude_number"] = "fast"

        def channel_system_not_a_mapping(world: World) -> None:
            world["river_channel_systems"].append("tampered")

        for label, tamper in (
            ("channel_slope_not_numeric", channel_slope_not_numeric),
            ("froude_number_not_numeric", froude_number_not_numeric),
            ("channel_system_not_a_mapping", channel_system_not_a_mapping),
        ):
            with self.subTest(tamper=label):
                self.assert_guard(
                    _validate_river_hydraulics, tamper, HYDRAULICS_FAILURE
                )

    def test_navigability_guards(self) -> None:
        def land_cell_neighbours_not_a_list(world: World) -> None:
            _land_cell(world)["neighbors"] = "seaward"

        def marine_cell_neighbours_not_a_list(world: World) -> None:
            _marine_cell(world)["neighbors"] = "landward"

        def chokepoints_not_a_list(world: World) -> None:
            world["marine_chokepoints"] = "none"

        def flow_accumulation_not_numeric(world: World) -> None:
            _land_cell(world)["flow_accumulation"] = "lots"

        def navigability_index_not_numeric(world: World) -> None:
            _land_cell(world)["navigability_index"] = "high"

        def settlements_not_a_list(world: World) -> None:
            world["settlements"] = "none"

        def settlement_not_a_mapping(world: World) -> None:
            world["settlements"].append("tampered")

        def route_not_a_mapping(world: World) -> None:
            world["routes"].append("tampered")

        def waterway_id_not_numeric(world: World) -> None:
            _land_cell(world)["navigable_waterway_id"] = "first"

        for label, tamper in (
            ("land_cell_neighbours_not_a_list", land_cell_neighbours_not_a_list),
            ("marine_cell_neighbours_not_a_list", marine_cell_neighbours_not_a_list),
            ("chokepoints_not_a_list", chokepoints_not_a_list),
            ("flow_accumulation_not_numeric", flow_accumulation_not_numeric),
            ("navigability_index_not_numeric", navigability_index_not_numeric),
            ("settlements_not_a_list", settlements_not_a_list),
            ("settlement_not_a_mapping", settlement_not_a_mapping),
            ("route_not_a_mapping", route_not_a_mapping),
            ("waterway_id_not_numeric", waterway_id_not_numeric),
        ):
            with self.subTest(tamper=label):
                self.assert_guard(_validate_navigability, tamper, NAVIGABILITY_FAILURE)

    def test_navigability_rejects_a_world_without_cells(self) -> None:
        """The empty-mesh guard, which every per-cell mean divides by.

        With no cells there are no candidates, no components and no waterways,
        so zeroing the two model counters lets every earlier check pass and the
        ``len(cells_by_id) <= 0`` guard is the only remaining exit.  Deleting
        that guard does not make this pass: control would fall through to
        ``navigability_sum / count`` and raise ``ZeroDivisionError``, which
        ``assertEqual`` reports just as loudly.
        """

        world = worlds.cached_world("replay_128")
        world["navigable_waterways"] = []
        world["navigability_model"]["candidate_cell_count"] = 0
        world["navigability_model"]["waterway_count"] = 0

        self.assertEqual(
            _validate_navigability(world, world["summary"], {}),
            [NAVIGABILITY_FAILURE],
        )

        # The same payload with its mesh intact is rejected for a different
        # reason entirely (the emptied waterway list), so the assertion above
        # is not simply "any tampered world fails".
        self.assertEqual(
            _direct_failures(_validate_navigability, worlds.cached_world("replay_128")),
            [],
        )
