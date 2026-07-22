"""Public ``validate`` CLI violations for core schema and hydrology gates.

Covers the schema/planet gate, mesh and summary headline checks, crust-age
replay, sea-level model reconstruction, hydrologic flow routing, depression
components and lake basins, and numeric depression-correction provenance.

Every case drives the public CLI over a temporary world file: one tamper on a
private deep copy of the shared 128-cell world, asserting the exact ``FAIL``
lines the command prints.

Three properties keep the cases honest:

* **The tamper must bite.**  :meth:`ValidateWorldTamperTest.run_tampered`
  refuses a tamper that leaves the world equal to the baseline, and the
  ``set_field`` / ``drop_field`` / ``add_field`` / ``set_on_all`` helpers refuse
  a write whose value is already there.  A hardcoded tamper value that happens
  to match the generated one therefore fails loudly instead of passing silently.
* **A crash is not a pass.**  ``CliRunner`` reports ``exit_code == 1`` both for
  the validation gate and for an uncaught exception, and click writes *no*
  traceback into ``result.output`` -- a crashing command produces empty output.
  So the harness inspects ``result.exception`` and rejects anything that is not
  the ``SystemExit`` raised by ``typer.Exit``.
* **The report must be specific.**  The subsystem verdicts (``sea level model
  metadata or connectivity invalid`` and friends) are each appended exactly once
  in the source, so a message alone cannot say *which* check inside the
  subsystem fired.  Each case therefore pins the complete ordered list of
  ``FAIL`` lines, which nails the tamper's whole blast radius: the discriminating
  detail lines other validators emit for it, and the absence of any further
  cascade.  The handful of tampers that sweep dozens of downstream validators
  pin the leading run of lines plus an explicit discriminator instead.

The untampered control run is executed once for the class and re-asserted by
every case, so each tamper carries its own proof that the fixture is healthy.
"""

from __future__ import annotations

import copy
import traceback
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from unittest import TestCase

from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.io import write_json

from support import worlds
import pytest

# Exhaustive branch coverage of ``validate``: every case invokes the full CLI
# over a generated world. Deselect locally with -m "not slow".
pytestmark = pytest.mark.slow

World = dict[str, Any]
Tamper = Callable[[World], None]

SEA_LEVEL_FAILURE = "sea level model metadata or connectivity invalid"
FLOW_FAILURE = "hydrology flow routing or accumulation invalid"
DEPRESSION_FAILURE = "hydrology depression components or lake basin aggregation invalid"
NUMERIC_FAILURE = "numeric depression correction provenance invalid"
CRUST_AGE_FAILURE = "crust ages exceed configured geological age"
CLOCK_FAILURE = "simulation clock or earth-system feedback history invalid"
PLATE_FAILURE = "plate kinematic model or motion history invalid"
WATER_BUDGET_FAILURE = "hydrologic water budget model or replay invalid"
NON_NUMERIC_ELEVATION = "sediment interface replay invalid: elevation_m must be numeric"

#: Emitted downstream of any tamper that disturbs depression/lake membership.
LAKE_AGGREGATION_CASCADE = (
    "simulated_lake_basin_count does not match basins with lake cells",
    "lake_overflow_histories do not match basins with lake cells",
    "lake overflow history fields invalid",
    "max_lake_overflow_fill_fraction does not match histories",
)

_MISSING = object()

#: Every key a ``numeric_depression_correction_history`` event must carry.
EVENT_KEYS = (
    "applied_alluvium_entrainment_volume_km3",
    "applied_bedrock_erosion_volume_km3",
    "applied_breach_deposition_volume_km3",
    "applied_breach_excavation_volume_km3",
    "area_km2",
    "breach_alluvium_entrainment_depth_m_by_cell",
    "breach_bedrock_erosion_depth_m_by_cell",
    "breach_deposition_capacity_km3",
    "breach_deposition_capacity_sufficient",
    "breach_deposition_cell_count",
    "breach_deposition_cell_ids",
    "breach_deposition_depth_m_by_cell",
    "breach_depth_bound_passed",
    "breach_diagnostic_model",
    "breach_elevation_before_m_by_cell",
    "breach_excavation_area_km2",
    "breach_excavation_depth_m_by_cell",
    "breach_excavation_volume_km3",
    "breach_feasible",
    "breach_gradient_step_m",
    "breach_has_lower_adjustment_volume",
    "breach_outlet_cell_id",
    "breach_path_cell_ids",
    "breach_path_length_km",
    "breach_same_pass_conflict_free",
    "breach_sediment_thickness_before_excavation_m_by_cell",
    "breach_target_elevation_m_by_cell",
    "breach_to_fill_volume_ratio",
    "cell_count",
    "cell_ids",
    "correction_mass_balance_residual_km3",
    "correction_method",
    "elevation_after_fill_m_by_cell",
    "elevation_before_fill_m_by_cell",
    "erosion_iteration",
    "feedback_stage_id",
    "fill_candidate_applied",
    "fill_candidate_model",
    "fill_depth_m_by_cell",
    "fill_volume_km3",
    "id",
    "lower_adjustment_volume_method",
    "max_breach_excavation_depth_m",
    "max_fill_depth_m",
    "sediment_thickness_before_correction_m_by_cell",
    "selected_correction_method",
    "sink_boundary_convergent",
    "sink_boundary_divergent",
    "sink_cell_id",
    "sink_crust_type",
    "sink_is_geologic",
    "source_depression_component_id",
    "source_depression_policy",
    "stabilization_pass",
    "stage",
    "temporary_numeric_lake_selected",
)
_LIST_EVENT_KEYS = tuple(
    key for key in EVENT_KEYS if key.endswith("_by_cell") or key.endswith("_ids")
)
_TEXT_EVENT_KEYS = (
    "correction_method",
    "fill_candidate_model",
    "source_depression_policy",
    "breach_diagnostic_model",
    "lower_adjustment_volume_method",
    "selected_correction_method",
)


def correction_event(**overrides: Any) -> dict[str, Any]:
    """A structurally complete but unverifiable numeric-correction event.

    Every declared key is present with a value the command can coerce, so the
    replay walks its whole extraction block before rejecting the event.
    """

    event: dict[str, Any] = {key: 0 for key in EVENT_KEYS}
    for key in _LIST_EVENT_KEYS:
        event[key] = []
    for key in _TEXT_EVENT_KEYS:
        event[key] = "unverified"
    event["stage"] = "initial_climate_hydrology"
    event["sink_crust_type"] = "continental"
    event.update(overrides)
    return event


def set_field(container: dict[str, Any], key: str, value: Any) -> None:
    """Overwrite ``container[key]``, refusing a write that changes nothing."""

    before = container.get(key, _MISSING)
    if before is not _MISSING and before == value:
        raise AssertionError(f"tamper is a no-op: {key!r} is already {value!r}")
    container[key] = value


def drop_field(container: dict[str, Any], key: str) -> None:
    """Delete ``container[key]``, refusing to "remove" an absent key."""

    if key not in container:
        raise AssertionError(f"tamper is a no-op: {key!r} is already absent")
    del container[key]


def add_field(container: dict[str, Any], key: str, value: Any) -> None:
    """Introduce ``container[key]``, refusing to "add" a key already there."""

    if key in container:
        raise AssertionError(f"tamper is a no-op: {key!r} is already present")
    container[key] = value


def set_on_all(records: list[dict[str, Any]], key: str, value: Any) -> None:
    """Set ``key`` on every record, refusing if every one already holds it."""

    if not records:
        raise AssertionError(f"tamper is a no-op: no record carries {key!r}")
    changed = any(record.get(key, _MISSING) != value for record in records)
    if not changed:
        raise AssertionError(f"tamper is a no-op: every {key!r} is already {value!r}")
    for record in records:
        record[key] = value


def cells_by_id(world: World) -> dict[int, dict[str, Any]]:
    return {int(cell["id"]): cell for cell in world["cells"]}


def depression_cells(world: World) -> list[dict[str, Any]]:
    return [
        cell
        for cell in world["cells"]
        if int(cell.get("depression_component_id", -1)) >= 0
    ]


def depression_sink_id(world: World) -> int:
    return int(depression_cells(world)[0]["depression_sink_cell_id"])


class ValidateWorldTamperTest(TestCase):
    """Shared 128-cell world plus a one-tamper-per-case CLI harness."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.world = worlds.cached_world("replay_128")
        cls._directory = TemporaryDirectory()
        cls.directory = Path(cls._directory.name)
        control_path = cls.directory / "control.json"
        write_json(control_path, cls.world)
        cls.control = CliRunner().invoke(app, ["validate", "--world", str(control_path)])

    @classmethod
    def tearDownClass(cls) -> None:
        cls._directory.cleanup()

    @staticmethod
    def failure_lines(result: Any) -> list[str]:
        """The reported messages, in order, with the ``FAIL `` prefix stripped."""

        return [
            line[len("FAIL ") :]
            for line in result.output.splitlines()
            if line.startswith("FAIL ")
        ]

    def assert_no_crash(self, result: Any) -> None:
        """Require that the command reported rather than raised.

        ``CliRunner`` turns an uncaught exception into ``exit_code == 1`` with an
        empty ``output`` and no traceback text anywhere, so only ``exception``
        tells the two apart: the gate leaves the ``SystemExit`` that
        ``typer.Exit`` raises, a crash leaves the original exception.
        """

        exception = result.exception
        if exception is not None and not isinstance(exception, SystemExit):
            formatted = "".join(traceback.format_exception(*result.exc_info))
            raise AssertionError(f"validate raised instead of reporting:\n{formatted}")
        self.assertNotIn("Traceback", result.output)

    def assert_control_clean(self) -> None:
        """The untampered fixture must validate, or no tamper proves anything."""

        self.assert_no_crash(self.control)
        self.assertEqual(self.control.exit_code, 0, self.control.output)
        self.assertEqual(self.failure_lines(self.control), [])

    def run_tampered(self, tamper: Tamper) -> Any:
        world = copy.deepcopy(self.world)
        tamper(world)
        if world == self.world:
            raise AssertionError("the tamper left the world unchanged")
        world_path = self.directory / "tampered.json"
        write_json(world_path, world)
        return CliRunner().invoke(app, ["validate", "--world", str(world_path)])

    def run_reporting(self, tamper: Tamper) -> Any:
        """Apply ``tamper`` and require a clean, non-crashing rejection."""

        self.assert_control_clean()
        result = self.run_tampered(tamper)
        self.assert_no_crash(result)
        self.assertEqual(result.exit_code, 1, result.output)
        return result

    def assert_exact_failures(self, tamper: Tamper, *expected: str) -> Any:
        """Run ``tamper`` and pin the complete ordered list of ``FAIL`` lines."""

        result = self.run_reporting(tamper)
        self.assertEqual(self.failure_lines(result), list(expected))
        return result

    def assert_failures_start_with(self, tamper: Tamper, *expected: str) -> Any:
        """Pin the leading ``FAIL`` lines of a tamper with a wide cascade.

        Used only where the tamper invalidates dozens of unrelated subsystems;
        callers add their own discriminator for what follows.
        """

        result = self.run_reporting(tamper)
        observed = self.failure_lines(result)
        self.assertEqual(observed[: len(expected)], list(expected))
        self.assertGreater(len(observed), len(expected))
        return result

    def assert_table(self, cases: dict[str, tuple[Tamper, tuple[str, ...]]]) -> None:
        """Run a table of ``name -> (tamper, expected lines)``, one CLI run each."""

        for name, (tamper, expected) in cases.items():
            with self.subTest(name):
                self.assert_exact_failures(tamper, *expected)


class SchemaGateTest(ValidateWorldTamperTest):
    """The opening gate: schema version, retired fields, planet parameters.

    This gate exits before any other check runs, so its three failures are the
    only lines the command prints.
    """

    def test_untampered_world_validates(self) -> None:
        self.assert_control_clean()
        self.assertEqual(self.control.exit_code, 0)

    def test_schema_gate_violations(self) -> None:
        def wrong_schema_version(world: World) -> None:
            set_field(world, "schema_version", 0)

        def retired_field(world: World) -> None:
            add_field(
                world["simulation_clock"],
                "legacy_mean_erosion_rate_field_semantics",
                True,
            )

        def non_positive_radius(world: World) -> None:
            set_field(world["planet_parameters"], "radius_km", -1.0)

        self.assert_table(
            {
                "wrong_schema_version": (
                    wrong_schema_version,
                    ("world schema_version must be 2, got 0",),
                ),
                "retired_schema_field": (
                    retired_field,
                    (
                        "world schema contains retired fields: "
                        "simulation_clock.legacy_mean_erosion_rate_field_semantics",
                    ),
                ),
                "non_positive_planet_radius": (
                    non_positive_radius,
                    (
                        "planet parameters invalid: "
                        "planet_parameters.radius_km must be finite and positive",
                    ),
                ),
            }
        )


class HeadlineSummaryTest(ValidateWorldTamperTest):
    """Mesh backend and the headline summary scalars."""

    def test_unknown_mesh_backend_also_breaks_the_summary_agreement(self) -> None:
        def tamper(world: World) -> None:
            set_field(world, "mesh_backend", "bogus")

        self.assert_exact_failures(
            tamper,
            "unknown mesh_backend: bogus",
            "summary mesh_backend does not match top-level mesh_backend",
            "native cell area model or spherical area closure invalid",
        )

    def test_summary_mesh_backend_disagreement_is_reported_alone(self) -> None:
        def tamper(world: World) -> None:
            set_field(world["summary"], "mesh_backend", "geodesic_icosahedron")

        self.assert_exact_failures(
            tamper, "summary mesh_backend does not match top-level mesh_backend"
        )

    def test_headline_summary_scalars_out_of_range(self) -> None:
        def out_of_range_ocean_fraction(world: World) -> None:
            set_field(world["summary"], "ocean_fraction", 1.5)

        def low_downhill_fraction(world: World) -> None:
            set_field(world["summary"], "river_downhill_fraction", 0.5)

        def wrong_cell_count(world: World) -> None:
            set_field(world["summary"], "cell_count", 3)

        self.assert_table(
            {
                "ocean_fraction": (
                    out_of_range_ocean_fraction,
                    (
                        "ocean_fraction out of range: 1.5",
                        "native cell area model or spherical area closure invalid",
                    ),
                ),
                "river_downhill_fraction": (
                    low_downhill_fraction,
                    ("river_downhill_fraction too low: 0.5",),
                ),
                "cell_count": (
                    wrong_cell_count,
                    (
                        "cell_count does not match cells length",
                        "atmospheric_cell_counts does not match cell_count",
                        "seasonal_humidity_regime_counts does not match cell_count",
                    ),
                ),
            }
        )


class CrustAgeReplayTest(ValidateWorldTamperTest):
    """The initial-versus-final crust age bound taken from the overlap ledger."""

    def test_crust_age_replay_violations(self) -> None:
        ledger_field = "remapped_crust_age_ma_by_cell"

        def missing_ledger(world: World) -> None:
            drop_field(world["plate_motion_history"][0], "crust_overlap_ledger")

        def ledger_length_mismatch(world: World) -> None:
            ledger = world["plate_motion_history"][0]["crust_overlap_ledger"]
            set_field(
                ledger, ledger_field, list(ledger[ledger_field]) + [1.0]
            )

        def missing_cell_age(world: World) -> None:
            drop_field(world["cells"][0], "crust_age_ma")

        def negative_cell_age(world: World) -> None:
            set_field(world["cells"][0], "crust_age_ma", -5.0)

        prefix = "plate_motion_history[0].crust_overlap_ledger"
        self.assert_table(
            {
                "missing_overlap_ledger": (
                    missing_ledger,
                    (
                        f"oceanic age-depth equilibrium replay invalid: {prefix} is missing",
                        f"initial oceanic crust age replay invalid: {prefix} must be an object",
                        f"plate boundary segment replay invalid: {prefix} is missing",
                        "crust material shadow: crust material shadow history 0 fields are invalid",
                        PLATE_FAILURE,
                        CRUST_AGE_FAILURE,
                    ),
                ),
                "ledger_length_mismatch": (
                    ledger_length_mismatch,
                    (
                        "oceanic age-depth equilibrium replay invalid: "
                        f"{prefix}.{ledger_field} must contain exactly 128 entries",
                        "initial oceanic crust age replay invalid: "
                        f"{prefix}.{ledger_field} must contain exactly 128 values",
                        "plate boundary segment replay invalid: "
                        f"{prefix}.{ledger_field} must contain exactly 128 entries",
                        PLATE_FAILURE,
                        CRUST_AGE_FAILURE,
                    ),
                ),
                "missing_cell_crust_age": (
                    missing_cell_age,
                    (
                        "plate summary fields invalid",
                        "oceanic age-depth equilibrium replay invalid: "
                        "independent crust transport/process root replay did not pass",
                        PLATE_FAILURE,
                        CRUST_AGE_FAILURE,
                        "land use zone model or causal replay invalid",
                    ),
                ),
                "negative_cell_crust_age": (
                    negative_cell_age,
                    (
                        "plate summary fields invalid",
                        "oceanic age-depth equilibrium replay invalid: "
                        "independent crust transport/process root replay did not pass",
                        PLATE_FAILURE,
                        CRUST_AGE_FAILURE,
                        "land use zone model or causal replay invalid",
                    ),
                ),
            }
        )


class SeaLevelModelTest(ValidateWorldTamperTest):
    """The sea-level model metadata and its flood reconstruction."""

    def test_sea_level_model_violations(self) -> None:
        def missing_key(world: World) -> None:
            drop_field(world["sea_level_model"], "model_type")

        def non_numeric_area(world: World) -> None:
            set_field(world["sea_level_model"], "surface_area_km2", "big")

        def non_numeric_planet_target(world: World) -> None:
            set_field(world["planet_parameters"], "ocean_fraction_target", "lots")

        def unreachable_inventory(world: World) -> None:
            set_field(world["sea_level_model"], "ocean_water_inventory_km3", 1.0e15)

        def overflowing_inventory(world: World) -> None:
            set_field(world["sea_level_model"], "ocean_water_inventory_km3", 1.0e308)

        self.assert_table(
            {
                "missing_model_key": (missing_key, (SEA_LEVEL_FAILURE,)),
                "non_numeric_surface_area": (non_numeric_area, (SEA_LEVEL_FAILURE,)),
                "non_numeric_planet_target": (
                    non_numeric_planet_target,
                    (SEA_LEVEL_FAILURE, "planet_parameters values invalid"),
                ),
                "inventory_above_every_flood_interval": (
                    unreachable_inventory,
                    (SEA_LEVEL_FAILURE,),
                ),
                "inventory_overflowing_the_flood_solve": (
                    overflowing_inventory,
                    (SEA_LEVEL_FAILURE,),
                ),
            }
        )

    def test_ocean_free_world_reports_sea_level_and_flow_failures(self) -> None:
        def drain_the_ocean(world: World) -> None:
            set_on_all(world["cells"], "is_water", False)

        result = self.assert_failures_start_with(
            drain_the_ocean,
            SEA_LEVEL_FAILURE,
            FLOW_FAILURE,
            DEPRESSION_FAILURE,
            CLOCK_FAILURE,
            "native cell area model or spherical area closure invalid",
        )
        # The elevations survive this tamper; the sibling case below strips them.
        self.assertNotIn(NON_NUMERIC_ELEVATION, self.failure_lines(result))


class FlowRoutingTest(ValidateWorldTamperTest):
    """Priority-flood reconstruction, emitted flow fields and accumulation."""

    def test_flow_routing_violations(self) -> None:
        def wrong_flat_gradient_step(world: World) -> None:
            set_field(world["summary"], "hydrologic_flat_gradient_step_m", 5.0)

        def unbounded_neighbour_elevation(world: World) -> None:
            land = [cell for cell in world["cells"] if not cell.get("is_water")]
            drop_field(land[0], "elevation_m")

        def non_numeric_flow_slope(world: World) -> None:
            set_field(world["cells"][-1], "hydrologic_flow_slope", None)

        def impossible_depression_depth(world: World) -> None:
            land = [cell for cell in world["cells"] if not cell.get("is_water")]
            set_field(land[-1], "depression_depth_m", 5000.0)

        def reroute_flag_on_water(world: World) -> None:
            water = [cell for cell in world["cells"] if cell.get("is_water")]
            set_field(water[-1], "equal_filled_raw_downhill_rerouted", True)

        def shifted_hydrologic_surface(world: World) -> None:
            cell = world["cells"][-1]
            set_field(
                cell,
                "hydrologic_surface_elevation_m",
                float(cell["hydrologic_surface_elevation_m"]) + 25.0,
            )

        def inflated_flow_accumulation(world: World) -> None:
            set_field(world["cells"][-1], "flow_accumulation", 1.0e18)

        depression_cascade = (FLOW_FAILURE, DEPRESSION_FAILURE) + LAKE_AGGREGATION_CASCADE
        self.assert_table(
            {
                "flat_gradient_step": (wrong_flat_gradient_step, depression_cascade),
                "unbounded_neighbour_elevation": (
                    unbounded_neighbour_elevation,
                    (
                        FLOW_FAILURE,
                        DEPRESSION_FAILURE,
                        CLOCK_FAILURE,
                        *LAKE_AGGREGATION_CASCADE,
                        WATER_BUDGET_FAILURE,
                        NON_NUMERIC_ELEVATION,
                        "settlement selection model or causal replay invalid",
                        "political region model or causal replay invalid",
                        "cultural geography model or causal replay invalid",
                        "population, conflict, or dynasty model causal replay invalid",
                        "groundwater flow model or routing replay invalid",
                        "route corridor model or causal replay invalid",
                    ),
                ),
                "non_numeric_flow_slope": (non_numeric_flow_slope, (FLOW_FAILURE,)),
                "impossible_depression_depth": (
                    impossible_depression_depth,
                    depression_cascade,
                ),
                "reroute_flag_on_water_cell": (reroute_flag_on_water, (FLOW_FAILURE,)),
                "shifted_hydrologic_surface": (
                    shifted_hydrologic_surface,
                    (FLOW_FAILURE,),
                ),
                "inflated_flow_accumulation": (
                    inflated_flow_accumulation,
                    (
                        FLOW_FAILURE,
                        "river channel morphology model or causal replay invalid",
                        "navigability model or causal replay invalid",
                        "port site model or causal replay invalid",
                        "route corridor model or causal replay invalid",
                    ),
                ),
            }
        )

    def test_neighbour_id_outside_the_mesh_is_reported_with_its_position(self) -> None:
        """The rejected neighbour is named by the position the tamper wrote it to."""

        seeded: dict[str, int] = {}

        def neighbour_outside_the_mesh(world: World) -> None:
            for position, cell in enumerate(world["cells"]):
                if not cell.get("is_water"):
                    continue
                # The reports index ``cells`` positionally; the mesh numbers its
                # cells the same way, so the two agree.
                if position != int(cell["id"]):
                    raise AssertionError("cell ids are no longer positional")
                seeded["cell"] = position
                seeded["slot"] = len(cell["neighbors"])
                set_field(cell, "neighbors", list(cell["neighbors"]) + [9999])
                return
            raise AssertionError("the world has no water cell to seed the flood")

        result = self.run_reporting(neighbour_outside_the_mesh)
        self.assertEqual(
            self.failure_lines(result),
            [
                FLOW_FAILURE,
                DEPRESSION_FAILURE,
                "initial oceanic crust age replay invalid: "
                f"cells[{seeded['cell']}].neighbors[{seeded['slot']}] is invalid",
                PLATE_FAILURE,
                *LAKE_AGGREGATION_CASCADE,
                WATER_BUDGET_FAILURE,
                "hillslope sediment transport mesh topology invalid",
                "glacial sediment transport topology invalid",
                "species range records invalid",
                "species range record ids are not unique",
                "species range record membership does not match cells",
                "species_guild_type_counts does not match records",
                "species_habitat_class_counts does not match records",
                "wetland_species_range_count does not match records",
                "species_range_total_area_km2 does not match records",
            ],
        )

    def test_ocean_free_world_without_elevations_seeds_from_no_finite_low(
        self,
    ) -> None:
        def drain_and_strip(world: World) -> None:
            set_on_all(world["cells"], "is_water", False)
            stripped = sum(
                cell.pop("elevation_m", _MISSING) is not _MISSING
                for cell in world["cells"]
            )
            if not stripped:
                raise AssertionError("no cell carried an elevation to strip")

        result = self.assert_failures_start_with(
            drain_and_strip,
            SEA_LEVEL_FAILURE,
            FLOW_FAILURE,
            DEPRESSION_FAILURE,
            CLOCK_FAILURE,
            "native cell area model or spherical area closure invalid",
        )
        # The stripped elevations are what separates this from the drained-only
        # world, whose cascade is otherwise identical.
        self.assertIn(NON_NUMERIC_ELEVATION, self.failure_lines(result))

    def test_two_land_cells_flowing_into_each_other_break_routing(self) -> None:
        def make_cycle(world: World) -> None:
            by_id = cells_by_id(world)
            for cell in world["cells"]:
                if cell.get("is_water") or int(
                    cell.get("depression_component_id", -1)
                ) >= 0:
                    continue
                for raw_neighbour in cell.get("neighbors", []):
                    neighbour = by_id.get(int(raw_neighbour))
                    if neighbour is None or neighbour.get("is_water"):
                        continue
                    if int(neighbour.get("depression_component_id", -1)) >= 0:
                        continue
                    cell["flow_to"] = int(neighbour["id"])
                    neighbour["flow_to"] = int(cell["id"])
                    return
            raise AssertionError("no adjacent land pair outside the depression")

        self.assert_exact_failures(
            make_cycle,
            FLOW_FAILURE,
            DEPRESSION_FAILURE,
            *LAKE_AGGREGATION_CASCADE,
            "watershed network diagnostics invalid",
            "watershed_outlet_type_counts does not match watersheds",
            "watershed_main_channel_count does not match watersheds",
            "watershed_mean_main_channel_length_km does not match watersheds",
            "watershed_mean_hack_coefficient does not match watersheds",
            "watershed_hack_fit_coefficient does not match watersheds",
            "watershed_mean_abs_hack_residual_fraction does not match watersheds",
            "watershed_hack_fitted_observation_count does not match watersheds",
            "watershed_hack_fitted_exponent does not match watersheds",
            "watershed_hack_fitted_coefficient does not match watersheds",
            "watershed_hack_fitted_log_rmse does not match watersheds",
        )

    def test_river_flag_on_a_sub_threshold_cell_breaks_extraction(self) -> None:
        def flag_a_non_river(world: World) -> None:
            for cell in world["cells"]:
                if not cell.get("is_water") and not cell.get("is_river"):
                    set_field(cell, "is_river", True)
                    return
            raise AssertionError("every land cell is already a river")

        result = self.assert_failures_start_with(
            flag_a_non_river,
            FLOW_FAILURE,
            CLOCK_FAILURE,
            "hydrologic budget region records invalid",
            "runoff_surplus_region_count does not match records",
            "water_deficit_region_count does not match records",
            "river channel morphology model or causal replay invalid",
        )
        # River extraction is downstream of the depression aggregation, which
        # this tamper leaves intact.
        self.assertNotIn(DEPRESSION_FAILURE, self.failure_lines(result))


class DepressionRoutingTest(ValidateWorldTamperTest):
    """Depression components, their sink units and the lake basin records."""

    def test_depression_cell_field_violations(self) -> None:
        def non_numeric_component_id(world: World) -> None:
            set_field(world["cells"][0], "depression_component_id", "one")

        def sink_outside_the_mesh(world: World) -> None:
            set_on_all(depression_cells(world), "depression_sink_cell_id", 99999)

        def component_id_on_a_plain_cell(world: World) -> None:
            plain = [
                cell
                for cell in world["cells"]
                if not cell.get("is_water")
                and int(cell.get("depression_component_id", -1)) < 0
            ]
            set_field(plain[0], "depression_component_id", -3)

        def non_numeric_lake_basin_id(world: World) -> None:
            set_field(world["cells"][0], "lake_basin_id", "one")

        def lake_basin_id_on_an_outside_cell(world: World) -> None:
            for cell in world["cells"]:
                if not cell.get("is_water") and int(cell.get("lake_basin_id", -1)) < 0:
                    set_field(cell, "lake_basin_id", 0)
                    return
            raise AssertionError("every land cell already belongs to a basin")

        cascade = (DEPRESSION_FAILURE,) + LAKE_AGGREGATION_CASCADE
        self.assert_table(
            {
                "non_numeric_component_id": (non_numeric_component_id, cascade),
                "sink_outside_the_mesh": (sink_outside_the_mesh, cascade),
                "component_id_on_a_plain_cell": (component_id_on_a_plain_cell, cascade),
                "non_numeric_lake_basin_id": (non_numeric_lake_basin_id, cascade),
                "lake_basin_id_on_an_outside_cell": (
                    lake_basin_id_on_an_outside_cell,
                    cascade,
                ),
            }
        )

    def test_lake_basin_record_violations(self) -> None:
        def basins_not_a_list(world: World) -> None:
            set_field(world, "lake_basins", {})

        def negative_basin_id(world: World) -> None:
            set_field(world["lake_basins"][0], "id", -1)

        def unknown_basin_component(world: World) -> None:
            set_field(world["lake_basins"][0], "depression_component_id", 7)

        def non_numeric_storage_capacity(world: World) -> None:
            set_field(world["lake_basins"][0], "storage_capacity_km3", "lots")

        cascade = (DEPRESSION_FAILURE,) + LAKE_AGGREGATION_CASCADE
        self.assert_table(
            {
                "basins_not_a_list": (
                    basins_not_a_list,
                    (
                        DEPRESSION_FAILURE,
                        "lake_basin_count does not match lake_basins length",
                        "preserved_geologic_depression_count does not match "
                        "lake basin policies",
                        *LAKE_AGGREGATION_CASCADE,
                    ),
                ),
                "negative_basin_id": (negative_basin_id, cascade),
                "unknown_basin_component": (unknown_basin_component, cascade),
                "non_numeric_storage_capacity": (
                    non_numeric_storage_capacity,
                    (DEPRESSION_FAILURE,),
                ),
            }
        )

    def test_depression_component_violations(self) -> None:
        def split_policies(world: World) -> None:
            set_field(depression_cells(world)[0], "depression_policy", "dry_closed")

        def sink_outside_its_component(world: World) -> None:
            component = depression_cells(world)
            member_ids = {int(cell["id"]) for cell in component}
            outside = next(
                int(cell["id"])
                for cell in world["cells"]
                if int(cell["id"]) not in member_ids
            )
            set_on_all(component, "depression_sink_cell_id", outside)

        def sink_with_a_lower_neighbour(world: World) -> None:
            component = depression_cells(world)
            highest = max(component, key=lambda cell: float(cell["elevation_m"]))
            set_on_all(component, "depression_sink_cell_id", int(highest["id"]))

        self.assert_table(
            {
                "split_policies": (split_policies, (DEPRESSION_FAILURE,)),
                "sink_outside_its_component": (
                    sink_outside_its_component,
                    (DEPRESSION_FAILURE,),
                ),
                "sink_with_a_lower_neighbour": (
                    sink_with_a_lower_neighbour,
                    (DEPRESSION_FAILURE,),
                ),
            }
        )

    def test_closed_depression_drainage_violations(self) -> None:
        def sink_is_not_terminal(world: World) -> None:
            by_id = cells_by_id(world)
            sink = by_id[depression_sink_id(world)]
            member_ids = {int(cell["id"]) for cell in depression_cells(world)}
            for raw_neighbour in sink.get("neighbors", []):
                if int(raw_neighbour) not in member_ids:
                    set_field(sink, "flow_to", int(raw_neighbour))
                    return
            raise AssertionError("the sink has no neighbour outside its component")

        def member_drains_out_of_the_component(world: World) -> None:
            by_id = cells_by_id(world)
            sink_id = depression_sink_id(world)
            member_ids = {int(cell["id"]) for cell in depression_cells(world)}
            for identifier in sorted(member_ids):
                if identifier == sink_id:
                    continue
                for raw_neighbour in by_id[identifier].get("neighbors", []):
                    if int(raw_neighbour) not in member_ids:
                        set_field(by_id[identifier], "flow_to", int(raw_neighbour))
                        return
            raise AssertionError("no member drains outside the component")

        def members_flow_into_each_other(world: World) -> None:
            by_id = cells_by_id(world)
            sink_id = depression_sink_id(world)
            member_ids = {int(cell["id"]) for cell in depression_cells(world)}
            for identifier in sorted(member_ids - {sink_id}):
                cell = by_id[identifier]
                for raw_neighbour in cell.get("neighbors", []):
                    other = int(raw_neighbour)
                    if other in member_ids and other not in {sink_id, identifier}:
                        cell["flow_to"] = other
                        by_id[other]["flow_to"] = identifier
                        return
            raise AssertionError("no adjacent non-sink member pair")

        self.assert_table(
            {
                "sink_is_not_terminal": (
                    sink_is_not_terminal,
                    (FLOW_FAILURE, DEPRESSION_FAILURE),
                ),
                "member_drains_out_of_the_component": (
                    member_drains_out_of_the_component,
                    (FLOW_FAILURE, DEPRESSION_FAILURE),
                ),
                "members_flow_into_each_other": (
                    members_flow_into_each_other,
                    (
                        FLOW_FAILURE,
                        DEPRESSION_FAILURE,
                        "river reorganization history records invalid",
                        "river reorganization history ids are not unique",
                        "river reorganization histories do not match events",
                        "mean_river_reorganization_risk_index does not match "
                        "river reorganization histories",
                        "total_river_divide_lowering_m does not match "
                        "river reorganization histories",
                        "total_river_sediment_reworked_m does not match "
                        "river reorganization histories",
                        "high_river_reorganization_pressure_count does not match "
                        "river reorganization histories",
                        "river channel morphology model or causal replay invalid",
                        "river_graph records invalid",
                        "river_graph_edge_count does not match river flow links",
                        "river_graph_total_channel_length_km does not match graph edges",
                    ),
                ),
            }
        )

    def test_open_depression_policy_violations(self) -> None:
        def overflow_policy_on_a_terminal_sink(world: World) -> None:
            set_on_all(depression_cells(world), "depression_policy", "overflow_spill")

        def temporary_lake_policy(world: World) -> None:
            set_on_all(
                depression_cells(world), "depression_policy", "temporary_numeric_lake"
            )

        self.assert_table(
            {
                "overflow_policy_on_a_terminal_sink": (
                    overflow_policy_on_a_terminal_sink,
                    (DEPRESSION_FAILURE,),
                ),
                "temporary_lake_policy": (
                    temporary_lake_policy,
                    (DEPRESSION_FAILURE,),
                ),
            }
        )

    def test_corrected_numeric_policy_also_invalidates_correction_provenance(
        self,
    ) -> None:
        def corrected_numeric_policy(world: World) -> None:
            by_id = cells_by_id(world)
            set_on_all(depression_cells(world), "depression_policy", "corrected_numeric")
            sink = by_id[depression_sink_id(world)]
            set_field(sink, "flow_to", int(sink.get("spill_to", -1)))

        self.assert_exact_failures(
            corrected_numeric_policy,
            FLOW_FAILURE,
            DEPRESSION_FAILURE,
            NUMERIC_FAILURE,
        )


class NumericCorrectionProvenanceTest(ValidateWorldTamperTest):
    """The numeric depression-correction summary and its event history."""

    def test_numeric_correction_summary_violations(self) -> None:
        def non_numeric_erosion_iterations(world: World) -> None:
            set_field(
                world["simulation_clock"], "configured_erosion_iteration_count", "many"
            )

        def history_is_not_a_list(world: World) -> None:
            set_field(world, "numeric_depression_correction_history", {})

        def non_numeric_max_pass_count(world: World) -> None:
            set_field(
                world["summary"],
                "numeric_depression_correction_max_pass_count",
                "sixteen",
            )

        def wrong_fill_tolerance(world: World) -> None:
            set_field(
                world["summary"], "numeric_depression_fill_depth_tolerance_m", 1.0
            )

        def wrong_pass_count(world: World) -> None:
            set_field(world["summary"], "numeric_depression_correction_pass_count", 3)

        def non_numeric_candidate_area(world: World) -> None:
            set_field(
                world["summary"], "numeric_depression_fill_candidate_area_km2", "big"
            )

        def wrong_candidate_area(world: World) -> None:
            set_field(
                world["summary"], "numeric_depression_fill_candidate_area_km2", 5.0
            )

        def non_numeric_cell_breach_count(world: World) -> None:
            set_field(
                world["cells"][-1], "numeric_depression_breach_event_count", "one"
            )

        def unexplained_cell_breach_depth(world: World) -> None:
            set_field(
                world["cells"][-1],
                "cumulative_numeric_depression_breach_excavation_m",
                5.0,
            )

        self.assert_table(
            {
                "non_numeric_erosion_iterations": (
                    non_numeric_erosion_iterations,
                    (
                        NUMERIC_FAILURE,
                        CLOCK_FAILURE,
                        PLATE_FAILURE,
                        WATER_BUDGET_FAILURE,
                        "fluvial sediment routing metadata values invalid",
                        "hillslope sediment transport metadata values invalid",
                        "glacial sediment transport stage values invalid",
                        "sediment inventory metadata values invalid",
                    ),
                ),
                "history_is_not_a_list": (
                    history_is_not_a_list,
                    (
                        NUMERIC_FAILURE,
                        "sediment inventory model or provenance missing",
                        "sediment interface replay invalid: "
                        "numeric_depression_correction_history must be a list of objects",
                    ),
                ),
                "non_numeric_max_pass_count": (
                    non_numeric_max_pass_count,
                    (NUMERIC_FAILURE,),
                ),
                "wrong_fill_tolerance": (wrong_fill_tolerance, (NUMERIC_FAILURE,)),
                "wrong_pass_count": (wrong_pass_count, (NUMERIC_FAILURE,)),
                "non_numeric_candidate_area": (
                    non_numeric_candidate_area,
                    (NUMERIC_FAILURE,),
                ),
                "wrong_candidate_area": (wrong_candidate_area, (NUMERIC_FAILURE,)),
                "non_numeric_cell_breach_count": (
                    non_numeric_cell_breach_count,
                    (NUMERIC_FAILURE,),
                ),
                "unexplained_cell_breach_depth": (
                    unexplained_cell_breach_depth,
                    (NUMERIC_FAILURE,),
                ),
            }
        )

    def test_correction_history_event_violations(self) -> None:
        def event_is_not_an_object(world: World) -> None:
            set_field(world, "numeric_depression_correction_history", ["bogus"])

        def event_field_is_not_numeric(world: World) -> None:
            set_field(
                world,
                "numeric_depression_correction_history",
                [correction_event(id="zero")],
            )

        def initial_stage_event(world: World) -> None:
            set_field(
                world, "numeric_depression_correction_history", [correction_event()]
            )

        def erosion_stage_event(world: World) -> None:
            set_field(
                world,
                "numeric_depression_correction_history",
                [correction_event(feedback_stage_id=1, stage="erosion_iteration")],
            )

        def cryosphere_stage_event(world: World) -> None:
            set_field(
                world,
                "numeric_depression_correction_history",
                [correction_event(feedback_stage_id=99, stage="cryosphere_coupling")],
            )

        unverifiable_method = (
            NUMERIC_FAILURE,
            "sediment interface replay invalid: numeric correction method is invalid",
        )
        self.assert_table(
            {
                "event_is_not_an_object": (
                    event_is_not_an_object,
                    (
                        NUMERIC_FAILURE,
                        "sediment inventory numeric event order invalid",
                        "sediment interface replay invalid: "
                        "numeric_depression_correction_history must be a list of objects",
                    ),
                ),
                "event_field_is_not_numeric": (
                    event_field_is_not_numeric,
                    (
                        NUMERIC_FAILURE,
                        "sediment inventory numeric event order invalid",
                        "sediment interface replay invalid: numeric.id must be an integer",
                    ),
                ),
                "unverifiable_initial_stage_event": (
                    initial_stage_event,
                    unverifiable_method,
                ),
                "unverifiable_erosion_stage_event": (
                    erosion_stage_event,
                    unverifiable_method,
                ),
                "unverifiable_cryosphere_stage_event": (
                    cryosphere_stage_event,
                    (
                        NUMERIC_FAILURE,
                        "sediment inventory numeric event order invalid",
                        "sediment interface replay invalid: "
                        "numeric event feedback link is invalid",
                    ),
                ),
            }
        )
