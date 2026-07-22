"""Causal-replay validation of the demographic agent and life-event models.

:func:`magic_geo.demographic_agents_validation.validate_demographic_agents_replay`
recomputes the household cohorts, firm agents, demographic histories, sampled
individuals and their life events from the rest of the payload and compares the
result record by record. It returns an empty list when the payload replays and a
single fixed failure string otherwise, so every test below asserts against that
exact string rather than mere truthiness.

The validator only compares the keys it recomputes, so some plausible edits are
silently ignored and are deliberately *not* used as tamper vectors:

* ``household_cohorts[0]["cohort_size"]`` is not a recomputed key.
* Political regions are checked for ``firm_agent_ids``/``firm_agent_count`` only,
  so deleting ``household_cohort_count`` from a political region is not detected
  even though deleting it from a population region is.
* ``market_exchanges[0]["friction"]`` is masked by the ``max()`` over exchanges,
  and a small ``conflict_loss`` bump rounds away against a population of 10^8.

Every tamper used below was confirmed to flip the verdict on its own, and
:meth:`_payload` asserts the untampered copy replays clean first, so no tamper
test can pass on an unchanged payload.
"""

from __future__ import annotations

import copy
from collections import Counter
from typing import Any
from unittest import TestCase

from support import worlds

from magic_geo.demographic_agents_validation import (
    DEMOGRAPHIC_AGENT_MODEL,
    INDIVIDUAL_LIFE_EVENT_MODEL,
    validate_demographic_agents_replay,
)

FAILURE = "demographic agent or individual life-event causal replay invalid"
WORLD = "replay_128"


class DemographicAgentsReplayValidationTests(TestCase):
    def tearDown(self) -> None:
        # ``_payload`` hands out copies that are shallow outside the families a
        # test names, so a tamper reaching a family it forgot to deep-copy would
        # corrupt every later test in the process. Fail here, next to the cause.
        self.assertEqual(
            validate_demographic_agents_replay(worlds.cached_world_readonly(WORLD)), []
        )

    def _payload(self, *families: str) -> dict[str, Any]:
        """A payload copy, deep for ``families``, asserted to replay clean first.

        Deep-copying the whole 128-cell world costs ~0.3s, so only the top-level
        entries the caller tampers with are copied; everything else is shared and
        must not be mutated. The clean assertion is what keeps the tamper tests
        below non-vacuous: with the tamper removed they see ``[]``, not
        ``[FAILURE]``.
        """
        shared = worlds.cached_world_readonly(WORLD)
        world = dict(shared)
        for family in families:
            world[family] = copy.deepcopy(shared[family])
        self.assertEqual(validate_demographic_agents_replay(world), [])
        return world

    def test_generated_world_replays_clean(self) -> None:
        world = worlds.cached_world_readonly(WORLD)

        self.assertEqual(validate_demographic_agents_replay(world), [])
        self.assertEqual(
            world["demographic_agent_model"]["model_type"], DEMOGRAPHIC_AGENT_MODEL
        )
        self.assertEqual(
            world["individual_life_event_model"]["model_type"], INDIVIDUAL_LIFE_EVENT_MODEL
        )
        self.assertIs(world["demographic_agent_model"]["deterministic"], True)
        self.assertIs(world["individual_life_event_model"]["deterministic"], True)
        self.assertEqual(world["summary"]["demographic_agent_model"], DEMOGRAPHIC_AGENT_MODEL)
        self.assertEqual(
            world["summary"]["individual_life_event_model"], INDIVIDUAL_LIFE_EVENT_MODEL
        )

    def test_sampled_families_match_the_declared_models(self) -> None:
        """Family sizes follow from the declared model strings, not from output.

        The counts below are derived from the model names the payload declares,
        so they stay meaningful independently of what the implementation emits.
        """
        world = worlds.cached_world_readonly(WORLD)
        region_count = len(world["population_regions"])
        cohorts = world["household_cohorts"]
        individuals = world["individual_agents"]
        events = world["individual_life_events"]
        self.assertGreater(region_count, 0)

        # normalized_rural_urban_mobile_cohorts_from_final_population_v1: one
        # rural, one urban and one mobile cohort per population region, in that
        # order, with the whole final population split between them.
        self.assertEqual(
            [cohort["cohort_type"] for cohort in cohorts],
            ["rural_household", "urban_household", "mobile_household"] * region_count,
        )
        # two_individuals_per_household_cohort_capped_at_six_per_population_region_v1:
        # three cohorts * two samples is exactly the cap of six.
        self.assertEqual(len(individuals), 6 * region_count)
        # regional_adjacent_spouse_and_two_predecessor_parent_graph_v1: an even
        # sample count leaves nobody unpaired, and the first two individuals of a
        # region have no sampled predecessors to be born to.
        self.assertNotIn(-1, [person["married_person_id"] for person in individuals])
        self.assertEqual(
            [len(person["parent_person_ids"]) for person in individuals[:6]], [0, 0, 1, 2, 2, 2]
        )
        # birth_paired_marriage_property_transfer_and_death_events_v1: a birth, a
        # property transfer and a death each, plus one marriage event per partner.
        self.assertEqual(
            Counter(event["event_type"] for event in events),
            Counter(
                {
                    name: len(individuals)
                    for name in ("birth", "marriage", "property_transfer", "death")
                }
            ),
        )
        self.assertEqual(
            [person["event_count"] for person in individuals], [4] * len(individuals)
        )
        self.assertEqual(len(events), 4 * len(individuals))

        summary = world["summary"]
        self.assertEqual(summary["household_cohort_count"], len(cohorts))
        self.assertEqual(summary["firm_agent_count"], len(world["firm_agents"]))
        self.assertEqual(
            summary["demographic_agent_history_count"],
            len(world["demographic_agent_histories"]),
        )
        self.assertEqual(summary["individual_agent_count"], len(individuals))
        self.assertEqual(summary["individual_life_event_count"], len(events))
        self.assertEqual(summary["individual_birth_event_count"], len(individuals))
        self.assertEqual(summary["individual_death_event_count"], len(individuals))
        self.assertEqual(summary["individual_marriage_event_count"], len(individuals))
        self.assertEqual(summary["property_transfer_event_count"], len(individuals))

    def test_emptied_record_families_are_rejected(self) -> None:
        for key in (
            # recomputed and compared record by record
            "household_cohorts",
            "firm_agents",
            "demographic_agent_histories",
            "individual_agents",
            "individual_life_events",
            # upstream inputs the recomputation reads
            "population_regions",
            "population_histories",
            "economy_histories",
            "logistics_networks",
            "market_exchanges",
            "settlements",
            "political_regions",
            "historical_eras",
        ):
            with self.subTest(key=key):
                world = self._payload()
                self.assertTrue(world[key], "family already empty, so emptying is a no-op")
                world[key] = []

                self.assertEqual(validate_demographic_agents_replay(world), [FAILURE])

    def test_model_declaration_mismatches_are_rejected(self) -> None:
        def drop_agent_model(world: dict[str, Any]) -> None:
            del world["demographic_agent_model"]

        def drop_life_event_model(world: dict[str, Any]) -> None:
            del world["individual_life_event_model"]

        def retype_agent_model(world: dict[str, Any]) -> None:
            self.assertNotEqual(
                world["demographic_agent_model"]["model_type"], "hand_written_v0"
            )
            world["demographic_agent_model"]["model_type"] = "hand_written_v0"

        def undeclare_determinism(world: dict[str, Any]) -> None:
            world["demographic_agent_model"]["deterministic"] = False

        def drop_agent_model_limitation(world: dict[str, Any]) -> None:
            del world["demographic_agent_model"]["model_limitation"]

        def drop_event_model_key(world: dict[str, Any]) -> None:
            del world["individual_life_event_model"]["event_model"]

        def extend_life_event_model(world: dict[str, Any]) -> None:
            self.assertNotIn("undeclared_key", world["individual_life_event_model"])
            world["individual_life_event_model"]["undeclared_key"] = True

        def retitle_summary_agent_model(world: dict[str, Any]) -> None:
            world["summary"]["demographic_agent_model"] = "hand_written_v0"

        def retitle_summary_event_model(world: dict[str, Any]) -> None:
            world["summary"]["individual_life_event_model"] = "hand_written_v0"

        def drop_summary_event_model(world: dict[str, Any]) -> None:
            del world["summary"]["individual_life_event_model"]

        for label, tamper in (
            ("missing_demographic_agent_model", drop_agent_model),
            ("missing_individual_life_event_model", drop_life_event_model),
            ("wrong_demographic_model_type", retype_agent_model),
            ("nondeterministic_demographic_model", undeclare_determinism),
            ("missing_demographic_model_limitation", drop_agent_model_limitation),
            ("missing_life_event_model_key", drop_event_model_key),
            ("extra_life_event_model_key", extend_life_event_model),
            ("wrong_summary_agent_model_name", retitle_summary_agent_model),
            ("wrong_summary_event_model_name", retitle_summary_event_model),
            ("missing_summary_event_model_name", drop_summary_event_model),
        ):
            with self.subTest(tamper=label):
                world = self._payload(
                    "demographic_agent_model", "individual_life_event_model", "summary"
                )
                tamper(world)

                self.assertEqual(validate_demographic_agents_replay(world), [FAILURE])

    def test_recomputed_cohort_firm_and_history_fields_are_rejected(self) -> None:
        """Per-record fields, not just record counts, have to replay."""

        def bump_cohort_vulnerability(world: dict[str, Any]) -> None:
            cohort = world["household_cohorts"][0]
            cohort["vulnerability_index"] = round(cohort["vulnerability_index"] + 0.1, 6)

        def double_cohort_population(world: dict[str, Any]) -> None:
            cohort = world["household_cohorts"][0]
            self.assertGreater(cohort["population"], 0.0)
            cohort["population"] = round(cohort["population"] * 2.0, 6)

        def retype_cohort(world: dict[str, Any]) -> None:
            cohort = world["household_cohorts"][0]
            self.assertNotEqual(cohort["cohort_type"], "urban_household")
            cohort["cohort_type"] = "urban_household"

        def bump_cohort_mortality(world: dict[str, Any]) -> None:
            cohort = world["household_cohorts"][-1]
            self.assertNotEqual(cohort["mortality_risk_index"], 0.99)
            cohort["mortality_risk_index"] = 0.99

        def bump_firm_employment(world: dict[str, Any]) -> None:
            firm = world["firm_agents"][0]
            firm["employment_capacity"] = round(firm["employment_capacity"] + 1.0, 6)

        def resector_firm(world: dict[str, Any]) -> None:
            firm = world["firm_agents"][0]
            self.assertNotEqual(firm["sector"], "urban_services")
            firm["sector"] = "urban_services"

        def move_firm_settlement(world: dict[str, Any]) -> None:
            firm = world["firm_agents"][0]
            firm["settlement_id"] = firm["settlement_id"] + 1

        def bump_history_step_count(world: dict[str, Any]) -> None:
            history = world["demographic_agent_histories"][0]
            history["step_count"] = history["step_count"] + 1

        def drop_history_step(world: dict[str, Any]) -> None:
            history = world["demographic_agent_histories"][0]
            self.assertGreater(len(history["steps"]), 1)
            del history["steps"][-1]

        def bump_history_step_population(world: dict[str, Any]) -> None:
            step = world["demographic_agent_histories"][0]["steps"][0]
            self.assertGreater(step["end_population"], 0.0)
            step["end_population"] = round(step["end_population"] * 1.5, 6)

        def unlink_history_firms(world: dict[str, Any]) -> None:
            history = world["demographic_agent_histories"][0]
            self.assertTrue(history["firm_agent_ids"])
            history["firm_agent_ids"] = []

        for label, tamper in (
            ("cohort_vulnerability_index", bump_cohort_vulnerability),
            ("cohort_population", double_cohort_population),
            ("cohort_type", retype_cohort),
            ("cohort_mortality_risk_index", bump_cohort_mortality),
            ("firm_employment_capacity", bump_firm_employment),
            ("firm_sector", resector_firm),
            ("firm_settlement_id", move_firm_settlement),
            ("history_step_count", bump_history_step_count),
            ("history_dropped_step", drop_history_step),
            ("history_step_end_population", bump_history_step_population),
            ("history_firm_agent_ids", unlink_history_firms),
        ):
            with self.subTest(tamper=label):
                world = self._payload(
                    "household_cohorts", "firm_agents", "demographic_agent_histories"
                )
                tamper(world)

                self.assertEqual(validate_demographic_agents_replay(world), [FAILURE])

    def test_derived_agent_and_event_fields_are_rejected(self) -> None:
        def rename_individual(world: dict[str, Any]) -> None:
            self.assertNotEqual(world["individual_agents"][0]["name"], "Bob")
            world["individual_agents"][0]["name"] = "Bob"

        def rerole_individual(world: dict[str, Any]) -> None:
            self.assertNotEqual(world["individual_agents"][0]["role"], "tax_collector")
            world["individual_agents"][0]["role"] = "tax_collector"

        def shift_birth_year(world: dict[str, Any]) -> None:
            person = world["individual_agents"][0]
            person["birth_year_bp"] = round(person["birth_year_bp"] + 1.0, 6)

        def strip_property(world: dict[str, Any]) -> None:
            person = world["individual_agents"][0]
            self.assertGreater(person["property_value_index"], 0.0)
            person["property_value_index"] = 0.0

        def divorce_individual(world: dict[str, Any]) -> None:
            person = world["individual_agents"][1]
            self.assertNotEqual(person["married_person_id"], -1)
            person["married_person_id"] = -1

        def orphan_individual(world: dict[str, Any]) -> None:
            person = world["individual_agents"][2]
            self.assertTrue(person["parent_person_ids"])
            person["parent_person_ids"] = []

        def reorder_parents(world: dict[str, Any]) -> None:
            person = world["individual_agents"][3]
            self.assertEqual(len(person["parent_person_ids"]), 2)
            person["parent_person_ids"] = list(reversed(person["parent_person_ids"]))

        def disown_children(world: dict[str, Any]) -> None:
            person = world["individual_agents"][0]
            self.assertTrue(person["child_person_ids"])
            person["child_person_ids"] = []

        def reorder_event_ids(world: dict[str, Any]) -> None:
            person = world["individual_agents"][0]
            self.assertGreater(len(person["event_ids"]), 1)
            person["event_ids"] = list(reversed(person["event_ids"]))

        def miscount_events(world: dict[str, Any]) -> None:
            person = world["individual_agents"][0]
            self.assertNotEqual(person["event_count"], 3)
            person["event_count"] = 3

        def retype_event(world: dict[str, Any]) -> None:
            self.assertNotEqual(world["individual_life_events"][0]["event_type"], "coronation")
            world["individual_life_events"][0]["event_type"] = "coronation"

        def reorder_events(world: dict[str, Any]) -> None:
            events = world["individual_life_events"]
            self.assertNotEqual(events[0]["event_type"], events[1]["event_type"])
            events[0], events[1] = events[1], events[0]

        def shift_event_era(world: dict[str, Any]) -> None:
            event = world["individual_life_events"][0]
            event["era_id"] = event["era_id"] + 1

        def shift_event_year(world: dict[str, Any]) -> None:
            event = world["individual_life_events"][0]
            event["year_bp"] = round(event["year_bp"] + 1.0, 6)

        def reinherit_event(world: dict[str, Any]) -> None:
            event = world["individual_life_events"][0]
            self.assertNotEqual(event["inheritance_fraction"], 0.5)
            event["inheritance_fraction"] = 0.5

        def relate_event(world: dict[str, Any]) -> None:
            event = world["individual_life_events"][1]
            self.assertNotEqual(event["related_person_id"], 0)
            event["related_person_id"] = 0

        for label, tamper in (
            ("individual_name", rename_individual),
            ("individual_role", rerole_individual),
            ("individual_birth_year", shift_birth_year),
            ("individual_property_value", strip_property),
            ("individual_spouse", divorce_individual),
            ("individual_parents", orphan_individual),
            ("individual_parent_order", reorder_parents),
            ("individual_children", disown_children),
            ("individual_event_id_order", reorder_event_ids),
            ("individual_event_count", miscount_events),
            ("life_event_type", retype_event),
            ("life_event_order", reorder_events),
            ("life_event_era", shift_event_era),
            ("life_event_year", shift_event_year),
            ("life_event_inheritance_fraction", reinherit_event),
            ("life_event_related_person", relate_event),
        ):
            with self.subTest(tamper=label):
                world = self._payload("individual_agents", "individual_life_events")
                tamper(world)

                self.assertEqual(validate_demographic_agents_replay(world), [FAILURE])

    def test_region_annotation_mismatches_are_rejected(self) -> None:
        """Both annotation back-references are checked, against different key sets."""

        def drop_individual_ids(world: dict[str, Any]) -> None:
            self.assertIn("individual_agent_ids", world["population_regions"][0])
            del world["population_regions"][0]["individual_agent_ids"]

        def drop_cohort_ids(world: dict[str, Any]) -> None:
            self.assertIn("household_cohort_ids", world["population_regions"][0])
            del world["population_regions"][0]["household_cohort_ids"]

        def miscount_cohorts(world: dict[str, Any]) -> None:
            region = world["population_regions"][0]
            self.assertNotEqual(region["household_cohort_count"], 99)
            region["household_cohort_count"] = 99

        def miscount_individuals(world: dict[str, Any]) -> None:
            region = world["population_regions"][0]
            self.assertNotEqual(region["individual_agent_count"], 99)
            region["individual_agent_count"] = 99

        def relink_history(world: dict[str, Any]) -> None:
            region = world["population_regions"][0]
            self.assertNotEqual(region["demographic_agent_history_id"], 7)
            region["demographic_agent_history_id"] = 7

        def rewrite_representative_population(world: dict[str, Any]) -> None:
            region = world["population_regions"][0]
            self.assertNotEqual(region["representative_household_population"], -1.0)
            region["representative_household_population"] = -1.0

        def drop_firm_ids(world: dict[str, Any]) -> None:
            self.assertIn("firm_agent_ids", world["political_regions"][0])
            del world["political_regions"][0]["firm_agent_ids"]

        def reorder_firm_ids(world: dict[str, Any]) -> None:
            region = world["political_regions"][0]
            reordered = list(reversed(region["firm_agent_ids"]))
            self.assertNotEqual(reordered, region["firm_agent_ids"])
            region["firm_agent_ids"] = reordered

        def miscount_firms(world: dict[str, Any]) -> None:
            region = world["political_regions"][0]
            region["firm_agent_count"] = region["firm_agent_count"] + 1

        for label, tamper in (
            ("population_region_individual_agent_ids", drop_individual_ids),
            ("population_region_household_cohort_ids", drop_cohort_ids),
            ("population_region_household_cohort_count", miscount_cohorts),
            ("population_region_individual_agent_count", miscount_individuals),
            ("population_region_history_id", relink_history),
            ("population_region_representative_population", rewrite_representative_population),
            ("political_region_firm_agent_ids", drop_firm_ids),
            ("political_region_firm_agent_id_order", reorder_firm_ids),
            ("political_region_firm_agent_count", miscount_firms),
        ):
            with self.subTest(tamper=label):
                world = self._payload("population_regions", "political_regions")
                tamper(world)

                self.assertEqual(validate_demographic_agents_replay(world), [FAILURE])

    def test_upstream_inputs_are_recomputed_not_copied(self) -> None:
        """Perturbing an input the agents are derived from must break the replay.

        These tampers touch nothing the validator compares directly, so they can
        only be caught by actually recomputing the cohorts, firms, histories and
        individuals from the upstream payload.
        """

        def raise_urbanization(world: dict[str, Any]) -> None:
            region = world["population_regions"][0]
            self.assertLessEqual(region["urbanization_fraction"] + 0.1, 0.88)
            region["urbanization_fraction"] += 0.1

        def shift_migration_balance(world: dict[str, Any]) -> None:
            region = world["population_regions"][0]
            region["migration_balance"] += 0.2

        def raise_hazard(world: dict[str, Any]) -> None:
            region = world["population_regions"][0]
            self.assertNotEqual(region["hazard_mortality_index"], 0.9)
            region["hazard_mortality_index"] = 0.9

        def raise_prosperity(world: dict[str, Any]) -> None:
            step = world["economy_histories"][0]["steps"][-1]
            self.assertNotEqual(step["prosperity_index"], 0.9)
            step["prosperity_index"] = 0.9

        def silence_trade_sector(world: dict[str, Any]) -> None:
            step = world["economy_histories"][0]["steps"][-1]
            self.assertGreater(step["trade_output_index"], 0.0)
            step["trade_output_index"] = 0.0

        def drop_logistics_resilience(world: dict[str, Any]) -> None:
            network = world["logistics_networks"][0]
            self.assertNotEqual(network["logistics_resilience_index"], 0.1)
            network["logistics_resilience_index"] = 0.1

        def raise_market_disruption(world: dict[str, Any]) -> None:
            market = world["market_exchanges"][0]
            self.assertNotEqual(market["disruption_risk_index"], 0.99)
            market["disruption_risk_index"] = 0.99

        def detach_settlement(world: dict[str, Any]) -> None:
            settlement = world["settlements"][0]
            self.assertGreaterEqual(settlement["region_id"], 0)
            settlement["region_id"] = -1

        def move_capital(world: dict[str, Any]) -> None:
            region = world["political_regions"][0]
            region["capital_settlement_id"] += 1

        def grow_final_population(world: dict[str, Any]) -> None:
            history = world["population_histories"][0]
            self.assertGreater(history["final_population"], 0.0)
            history["final_population"] *= 1.1

        def shift_era_start(world: dict[str, Any]) -> None:
            era = world["historical_eras"][0]
            era["start_year_bp"] += 5.0

        def drop_last_era(world: dict[str, Any]) -> None:
            self.assertGreater(len(world["historical_eras"]), 1)
            del world["historical_eras"][-1]

        for label, tamper in (
            ("population_region_urbanization", raise_urbanization),
            ("population_region_migration_balance", shift_migration_balance),
            ("population_region_hazard", raise_hazard),
            ("economy_prosperity", raise_prosperity),
            ("economy_trade_sector_output", silence_trade_sector),
            ("logistics_resilience", drop_logistics_resilience),
            ("market_disruption_risk", raise_market_disruption),
            ("settlement_region", detach_settlement),
            ("political_region_capital", move_capital),
            ("population_history_final_population", grow_final_population),
            ("historical_era_start_year", shift_era_start),
            ("dropped_historical_era", drop_last_era),
        ):
            with self.subTest(tamper=label):
                world = self._payload(
                    "population_regions",
                    "economy_histories",
                    "logistics_networks",
                    "market_exchanges",
                    "settlements",
                    "political_regions",
                    "population_histories",
                    "historical_eras",
                )
                tamper(world)

                self.assertEqual(validate_demographic_agents_replay(world), [FAILURE])

    def test_summary_counter_mismatches_are_rejected(self) -> None:
        for key, value in (
            ("household_cohort_count", 99),
            ("firm_agent_count", 99),
            ("demographic_agent_history_count", 99),
            ("demographic_agent_step_count", 0),
            ("high_vulnerability_household_count", 42),
            ("total_household_cohort_population", 0.0),
            ("total_firm_employment_capacity", 0.0),
            ("mean_household_resilience_index", 0.5),
            ("mean_firm_productivity_index", 0.5),
            ("mean_demographic_vulnerability_index", 0.5),
            ("individual_agent_count", 99),
            ("individual_life_event_count", 0),
            ("individual_birth_event_count", 0),
            ("individual_marriage_event_count", 0),
            ("property_transfer_event_count", 0),
            ("mean_individual_lifespan_years", 1.0),
            ("total_property_transfer_value_index", -1.0),
        ):
            with self.subTest(summary_key=key):
                world = self._payload("summary")
                self.assertNotEqual(world["summary"][key], value)
                world["summary"][key] = value

                self.assertEqual(validate_demographic_agents_replay(world), [FAILURE])

    def test_malformed_payloads_fail_without_raising(self) -> None:
        world = self._payload()
        no_summary = dict(world)
        del no_summary["summary"]
        list_summary = dict(world, summary=[])
        mapping_cohorts = dict(world, household_cohorts={})
        string_individuals = dict(world, individual_agents="six")

        for label, payload in (
            ("empty_dict", {}),
            ("summary_only", {"summary": {}}),
            ("none", None),
            ("missing_summary", no_summary),
            ("summary_is_a_list", list_summary),
            ("household_cohorts_is_a_mapping", mapping_cohorts),
            ("individual_agents_is_a_string", string_individuals),
        ):
            with self.subTest(payload=label):
                self.assertEqual(validate_demographic_agents_replay(payload), [FAILURE])
