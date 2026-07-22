"""Causal replay checks for the population and economy history model.

``validate_history_economy_replay`` recomputes every population and economy
history from the raw region, era, snapshot, conflict and trade records, so a
passing payload can only come from the generator itself. Each tamper test
therefore starts from the canonical 128-cell world, asserts it replays clean,
and applies exactly one tamper.

The structural tests do not call the validator at all: they re-derive the
documented identities (era-to-era population chaining, output composition,
treasury closure, summary aggregates) straight from the payload, so a generator
regression is caught even if the validator were changed to agree with it.

The validator compares only the keys it recomputes, so plausible-looking edits
outside that surface are silently ignored; ``test_unreplayed_keys_are_ignored``
pins that boundary and doubles as proof that the tamper tests trip for a
specific reason rather than for any mutation at all.
"""

from __future__ import annotations

from typing import Any, Callable
from unittest import TestCase

from magic_geo.history_economy_validation import (
    ECONOMY_HISTORY_MODEL,
    POPULATION_HISTORY_MODEL,
    validate_history_economy_replay,
)

from support import worlds

FAILURE = "population or economy history model causal replay invalid"

#: Model identifiers documented in ``README.md`` and ``docs/r1_status_audit.md``.
#: Pinned as literals so that renaming the constants in ``src`` cannot silently
#: keep this file green.
POPULATION_MODEL_ID = "causal_era_snapshot_logistic_migration_conflict_population_history_v1"
ECONOMY_MODEL_ID = "causal_population_trade_conflict_treasury_economy_history_v1"

#: Records round every derived quantity to six decimals, so recomposing a value
#: from its rounded parts drifts by a few units in the last place.
ROUNDING_TOLERANCE = 5e-6


class HistoryEconomyModelStructureTest(TestCase):
    """The generated histories satisfy the documented causal identities."""

    def setUp(self) -> None:
        self.world = worlds.cached_world_readonly("replay_128")

    def test_generated_world_replays_clean(self) -> None:
        self.assertEqual(validate_history_economy_replay(self.world), [])
        self.assertEqual(POPULATION_HISTORY_MODEL, POPULATION_MODEL_ID)
        self.assertEqual(ECONOMY_HISTORY_MODEL, ECONOMY_MODEL_ID)
        self.assertEqual(
            self.world["population_history_model"]["model_type"], POPULATION_MODEL_ID
        )
        self.assertEqual(
            self.world["economy_history_model"]["model_type"], ECONOMY_MODEL_ID
        )
        self.assertEqual(
            self.world["summary"]["population_history_model"], POPULATION_MODEL_ID
        )
        self.assertEqual(
            self.world["summary"]["economy_history_model"], ECONOMY_MODEL_ID
        )

    def test_every_population_region_gets_one_history_per_era(self) -> None:
        regions = self.world["population_regions"]
        eras = self.world["historical_eras"]
        histories = self.world["population_histories"]
        self.assertEqual(len(regions), 1)
        self.assertEqual(len(eras), 4)
        self.assertEqual(len(histories), len(regions))
        self.assertEqual(
            sorted(int(history["region_id"]) for history in histories),
            sorted(int(region["region_id"]) for region in regions),
        )
        # Eras are replayed oldest first, so step order follows descending
        # start year. On this world that happens to coincide with the storage
        # order of ``historical_eras``; sorting keeps the assertion honest if a
        # later generator emits eras in another order.
        expected_era_ids = [
            int(era["id"])
            for era in sorted(eras, key=lambda era: -float(era["start_year_bp"]))
        ]
        for history in histories:
            with self.subTest(population_history=history["id"]):
                steps = history["steps"]
                self.assertEqual(len(steps), len(eras))
                self.assertEqual(history["time_step_count"], len(eras))
                self.assertEqual([int(step["era_id"]) for step in steps], expected_era_ids)

    def test_population_steps_chain_end_to_start_across_eras(self) -> None:
        for history in self.world["population_histories"]:
            steps = history["steps"]
            with self.subTest(population_history=history["id"]):
                self.assertEqual(
                    history["initial_population"], steps[0]["start_population"]
                )
                self.assertEqual(history["final_population"], steps[-1]["end_population"])
                self.assertEqual(
                    history["peak_population"],
                    max(
                        [steps[0]["start_population"]]
                        + [step["end_population"] for step in steps]
                    ),
                )
                self.assertEqual(
                    history["peak_pressure_index"],
                    max(step["pressure_index"] for step in steps),
                )
                for index, step in enumerate(steps):
                    with self.subTest(step=index):
                        if index:
                            self.assertEqual(
                                step["start_population"],
                                steps[index - 1]["end_population"],
                            )
                        self.assertAlmostEqual(
                            step["population_change"],
                            step["end_population"] - step["start_population"],
                            delta=ROUNDING_TOLERANCE,
                        )
                        self.assertAlmostEqual(
                            step["pressure_index"],
                            step["end_population"] / step["carrying_capacity"],
                            delta=ROUNDING_TOLERANCE,
                        )
                        self.assertEqual(
                            step["pressure_index"], step["carrying_capacity_used_fraction"]
                        )
                        self.assertGreaterEqual(step["end_population"], 0.0)
                        self.assertGreaterEqual(step["conflict_loss"], 0.0)
                        self.assertGreater(step["duration_years"], 0.0)

    def test_economy_steps_compose_output_and_close_the_treasury(self) -> None:
        population_by_region = {
            int(history["region_id"]): history
            for history in self.world["population_histories"]
        }
        economy_histories = self.world["economy_histories"]
        self.assertEqual(len(economy_histories), len(population_by_region))
        for history in economy_histories:
            steps = history["steps"]
            population_steps = population_by_region[int(history["region_id"])]["steps"]
            with self.subTest(economy_history=history["id"]):
                self.assertEqual(len(steps), len(population_steps))
                self.assertEqual(history["time_step_count"], len(steps))
                self.assertEqual(
                    history["final_gross_output_index"], steps[-1]["gross_output_index"]
                )
                self.assertEqual(
                    history["final_treasury_index"], steps[-1]["treasury_end_index"]
                )
                self.assertEqual(
                    history["peak_gross_output_index"],
                    max(step["gross_output_index"] for step in steps),
                )
                self.assertEqual(
                    history["max_army_capacity_population"],
                    max(step["army_capacity_population"] for step in steps),
                )
                previous_treasury: float | None = None
                for index, (step, population_step) in enumerate(
                    zip(steps, population_steps, strict=True)
                ):
                    with self.subTest(step=index):
                        self.assertEqual(step["era_id"], population_step["era_id"])
                        self.assertEqual(
                            step["population"], population_step["end_population"]
                        )
                        self.assertAlmostEqual(
                            step["gross_output_index"],
                            step["agricultural_output_index"]
                            + step["resource_output_index"]
                            + step["trade_output_index"]
                            + step["urban_services_index"],
                            delta=ROUNDING_TOLERANCE,
                        )
                        if previous_treasury is not None:
                            self.assertEqual(
                                step["treasury_start_index"], previous_treasury
                            )
                        closed = (
                            step["treasury_start_index"]
                            + step["tax_revenue_index"]
                            + step["trade_revenue_index"]
                            + step["insolvency_adjustment_index"]
                            - step["administration_cost_index"]
                            - step["army_maintenance_cost_index"]
                            - step["war_cost_index"]
                        )
                        self.assertAlmostEqual(
                            closed, step["treasury_end_index"], delta=ROUNDING_TOLERANCE
                        )
                        self.assertEqual(step["balance_residual_index"], 0.0)
                        self.assertGreaterEqual(step["treasury_end_index"], 0.0)
                        self.assertGreaterEqual(step["insolvency_adjustment_index"], 0.0)
                        for bounded in (
                            "prosperity_index",
                            "food_security_index",
                            "trade_dependency_index",
                            "military_burden_index",
                            "stability_index",
                        ):
                            self.assertGreaterEqual(step[bounded], 0.0)
                            self.assertLessEqual(step[bounded], 1.0)
                        previous_treasury = step["treasury_end_index"]

    def test_summary_aggregates_match_the_nested_records(self) -> None:
        summary = self.world["summary"]
        population_histories = self.world["population_histories"]
        economy_histories = self.world["economy_histories"]
        population_steps = [
            step for history in population_histories for step in history["steps"]
        ]
        economy_steps = [step for history in economy_histories for step in history["steps"]]

        self.assertEqual(summary["population_history_count"], len(population_histories))
        self.assertEqual(summary["population_history_step_count"], len(population_steps))
        self.assertAlmostEqual(
            summary["historical_final_population"],
            sum(history["final_population"] for history in population_histories),
            delta=ROUNDING_TOLERANCE,
        )
        self.assertEqual(
            summary["historical_peak_population_pressure"],
            max(step["pressure_index"] for step in population_steps),
        )
        self.assertAlmostEqual(
            summary["max_population_decline_fraction"],
            max(
                max(0.0, -step["population_change"] / max(1.0, step["start_population"]))
                for step in population_steps
            ),
            delta=ROUNDING_TOLERANCE,
        )

        self.assertEqual(summary["economy_history_count"], len(economy_histories))
        self.assertEqual(summary["economy_history_step_count"], len(economy_steps))
        self.assertAlmostEqual(
            summary["historical_final_gross_output_index"],
            sum(history["final_gross_output_index"] for history in economy_histories),
            delta=ROUNDING_TOLERANCE,
        )
        self.assertAlmostEqual(
            summary["historical_final_treasury_index"],
            sum(history["final_treasury_index"] for history in economy_histories),
            delta=ROUNDING_TOLERANCE,
        )
        for summary_key, step_key in (
            ("historical_total_tax_revenue_index", "tax_revenue_index"),
            ("historical_total_trade_revenue_index", "trade_revenue_index"),
            ("historical_total_war_cost_index", "war_cost_index"),
        ):
            with self.subTest(summary_key=summary_key):
                self.assertAlmostEqual(
                    summary[summary_key],
                    sum(step[step_key] for step in economy_steps),
                    delta=ROUNDING_TOLERANCE,
                )
        self.assertAlmostEqual(
            summary["historical_peak_army_capacity_population"],
            max(step["army_capacity_population"] for step in economy_steps),
            delta=ROUNDING_TOLERANCE,
        )
        for summary_key, step_key in (
            ("mean_historical_prosperity_index", "prosperity_index"),
            ("mean_historical_trade_dependency_index", "trade_dependency_index"),
            ("mean_historical_military_burden_index", "military_burden_index"),
        ):
            with self.subTest(summary_key=summary_key):
                self.assertAlmostEqual(
                    summary[summary_key],
                    sum(step[step_key] for step in economy_steps) / len(economy_steps),
                    delta=ROUNDING_TOLERANCE,
                )
        self.assertEqual(
            summary["high_military_burden_economy_step_count"],
            sum(1 for step in economy_steps if step["military_burden_index"] >= 0.65),
        )


class HistoryEconomyReplayValidationTest(TestCase):
    """``validate_history_economy_replay`` accepts only the generated model."""

    def _tampered(self, mutate: Callable[[dict[str, Any]], None]) -> list[str]:
        payload = worlds.cached_world("replay_128")
        self.assertEqual(validate_history_economy_replay(payload), [])
        mutate(payload)
        return validate_history_economy_replay(payload)

    def test_unreplayed_keys_are_ignored(self) -> None:
        """Edits outside the recomputed surface leave the payload valid.

        Population steps carry ``start_population``/``end_population``, so a
        stray ``population`` key is never compared. This pins the boundary and
        shows the tamper tests below react to the tampered value rather than to
        the mere fact that the payload was touched.
        """

        def stray_key(payload: dict[str, Any]) -> None:
            payload["population_histories"][0]["steps"][0]["population"] = 1.0

        self.assertEqual(self._tampered(stray_key), [])

    def test_population_history_tampers_are_rejected(self) -> None:
        def final_population(payload: dict[str, Any]) -> None:
            payload["population_histories"][0]["final_population"] = 1.0

        def step_end_population(payload: dict[str, Any]) -> None:
            payload["population_histories"][0]["steps"][0]["end_population"] = 5.0

        def step_migration_delta(payload: dict[str, Any]) -> None:
            payload["population_histories"][0]["steps"][0]["migration_delta"] += 1.0

        def history_region_id(payload: dict[str, Any]) -> None:
            payload["population_histories"][0]["region_id"] = 77

        def dropped_step(payload: dict[str, Any]) -> None:
            payload["population_histories"][0]["steps"].pop()

        def emptied_histories(payload: dict[str, Any]) -> None:
            payload["population_histories"] = []

        def snapshot_population(payload: dict[str, Any]) -> None:
            payload["territorial_snapshots"][0]["regions"][0][
                "estimated_population"
            ] = 12345.0

        def carrying_capacity(payload: dict[str, Any]) -> None:
            payload["population_regions"][0]["carrying_capacity"] = 5.0

        def growth_rate(payload: dict[str, Any]) -> None:
            payload["population_regions"][0]["growth_rate_per_year"] = 0.05

        def era_start_year(payload: dict[str, Any]) -> None:
            payload["historical_eras"][0]["start_year_bp"] = 999999.0

        cases = (
            ("final_population", final_population),
            ("step_end_population", step_end_population),
            ("step_migration_delta", step_migration_delta),
            ("history_region_id", history_region_id),
            ("dropped_step", dropped_step),
            ("emptied_population_histories", emptied_histories),
            ("snapshot_estimated_population", snapshot_population),
            ("region_carrying_capacity", carrying_capacity),
            ("region_growth_rate_per_year", growth_rate),
            ("era_start_year_bp", era_start_year),
        )
        for name, mutate in cases:
            with self.subTest(tamper=name):
                self.assertEqual(self._tampered(mutate), [FAILURE])

    def test_economy_history_tampers_are_rejected(self) -> None:
        def emptied_histories(payload: dict[str, Any]) -> None:
            payload["economy_histories"] = []

        def dropped_step(payload: dict[str, Any]) -> None:
            payload["economy_histories"][0]["steps"].pop()

        def final_gross_output(payload: dict[str, Any]) -> None:
            payload["economy_histories"][0]["final_gross_output_index"] = 1.0

        def step_treasury(payload: dict[str, Any]) -> None:
            payload["economy_histories"][0]["steps"][0]["treasury_end_index"] = 0.0

        def step_balance_residual(payload: dict[str, Any]) -> None:
            payload["economy_histories"][0]["steps"][0]["balance_residual_index"] = 0.5

        def max_army_capacity(payload: dict[str, Any]) -> None:
            payload["economy_histories"][0]["max_army_capacity_population"] = 1.0

        def dominant_resource(payload: dict[str, Any]) -> None:
            payload["economy_histories"][0]["dominant_resource"] = "unobtainium"

        def political_dominant_resource(payload: dict[str, Any]) -> None:
            payload["political_regions"][0]["dominant_resource"] = "diamonds"

        def political_route_count(payload: dict[str, Any]) -> None:
            payload["political_regions"][0]["route_count"] = 99.0

        def trade_volume(payload: dict[str, Any]) -> None:
            payload["trade_flows"][0]["volume_index"] = 999.0

        def trade_friction(payload: dict[str, Any]) -> None:
            payload["trade_flows"][0]["friction"] = 3.5

        def snapshot_stability(payload: dict[str, Any]) -> None:
            payload["territorial_snapshots"][0]["regions"][0]["stability_index"] = 0.123456

        def injected_conflict(payload: dict[str, Any]) -> None:
            # No conflicts survive at 128 cells, so a bogus record changes both
            # the expected population steps and the expected economy steps.
            payload["conflicts"].append(
                {
                    "era_id": int(payload["historical_eras"][0]["id"]),
                    "region_a": int(payload["population_regions"][0]["region_id"]),
                    "region_b": -1,
                    "estimated_casualties": 25000.0,
                    "region_a_force_estimate": 5000.0,
                    "region_b_force_estimate": 0.0,
                    "intensity": 0.5,
                    "logistics_strain_index": 0.4,
                    "economic_disruption_index": 0.3,
                }
            )

        cases = (
            ("emptied_economy_histories", emptied_histories),
            ("dropped_economy_step", dropped_step),
            ("final_gross_output_index", final_gross_output),
            ("step_treasury_end_index", step_treasury),
            ("step_balance_residual_index", step_balance_residual),
            ("max_army_capacity_population", max_army_capacity),
            ("dominant_resource", dominant_resource),
            ("political_dominant_resource", political_dominant_resource),
            ("political_route_count", political_route_count),
            ("trade_flow_volume_index", trade_volume),
            ("trade_flow_friction", trade_friction),
            ("snapshot_stability_index", snapshot_stability),
            ("injected_conflict", injected_conflict),
        )
        for name, mutate in cases:
            with self.subTest(tamper=name):
                self.assertEqual(self._tampered(mutate), [FAILURE])

    def test_model_descriptor_tampers_are_rejected(self) -> None:
        def population_growth_model(payload: dict[str, Any]) -> None:
            payload["population_history_model"]["growth_model"] = "linear_v1"

        def missing_economy_model(payload: dict[str, Any]) -> None:
            del payload["economy_history_model"]

        def summary_population_model(payload: dict[str, Any]) -> None:
            payload["summary"]["population_history_model"] = "bogus_v1"

        def summary_economy_model(payload: dict[str, Any]) -> None:
            payload["summary"]["economy_history_model"] = "bogus_v1"

        cases = (
            ("population_history_model_field", population_growth_model),
            ("missing_economy_history_model", missing_economy_model),
            ("summary_population_history_model", summary_population_model),
            ("summary_economy_history_model", summary_economy_model),
        )
        for name, mutate in cases:
            with self.subTest(tamper=name):
                self.assertEqual(self._tampered(mutate), [FAILURE])

    def test_summary_aggregate_tampers_are_rejected(self) -> None:
        def replace(key: str, value: Any) -> Callable[[dict[str, Any]], None]:
            def mutate(payload: dict[str, Any]) -> None:
                # A tamper equal to the generated value would prove nothing.
                self.assertNotEqual(payload["summary"][key], value)
                payload["summary"][key] = value

            return mutate

        cases = (
            ("population_history_count", 99),
            ("population_history_step_count", 3),
            ("historical_final_population", 1.0),
            ("historical_peak_population_pressure", 0.5),
            ("economy_history_step_count", 0),
            ("historical_final_treasury_index", 0.0),
            ("historical_total_war_cost_index", 12.5),
            ("mean_historical_military_burden_index", 0.9),
            ("high_military_burden_economy_step_count", 7),
        )
        for key, value in cases:
            with self.subTest(summary_key=key):
                self.assertEqual(self._tampered(replace(key, value)), [FAILURE])

    def test_malformed_payloads_fail_without_raising(self) -> None:
        def missing_snapshots(payload: dict[str, Any]) -> None:
            del payload["territorial_snapshots"]

        def non_list_population_regions(payload: dict[str, Any]) -> None:
            payload["population_regions"] = None

        def non_dict_summary(payload: dict[str, Any]) -> None:
            payload["summary"] = ["not a mapping"]

        def missing_summary(payload: dict[str, Any]) -> None:
            del payload["summary"]

        def emptied_eras(payload: dict[str, Any]) -> None:
            # ``_expected_population_histories`` indexes ``eras[0]``; the
            # resulting IndexError must surface as the failure string.
            payload["historical_eras"] = []

        self.assertEqual(validate_history_economy_replay({}), [FAILURE])
        cases = (
            ("missing_territorial_snapshots", missing_snapshots),
            ("population_regions_not_a_list", non_list_population_regions),
            ("summary_not_a_mapping", non_dict_summary),
            ("missing_summary", missing_summary),
            ("emptied_historical_eras", emptied_eras),
        )
        for name, mutate in cases:
            with self.subTest(payload=name):
                self.assertEqual(self._tampered(mutate), [FAILURE])
