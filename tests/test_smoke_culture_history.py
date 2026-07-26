"""Cultures, languages, and historical record assertions for the generated world.

Split out of the former single-method smoke test: each method re-derives
what it needs from the shared world, so they no longer depend on order.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from click.testing import Result
from typer.testing import CliRunner

from magic_geo.cli import app

from support import worlds
from support.cli import assert_no_cli_crash


class SmokeCultureHistoryTests(TestCase):
    def test_cultures(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        self.assertEqual(summary["culture_region_count"], len(world["cultures"]))
        self.assertGreater(summary["culture_region_count"], 0)
        self.assertEqual(summary["language_region_count"], len(world["language_regions"]))
        self.assertGreater(summary["language_region_count"], 0)
        self.assertEqual(summary["historical_era_count"], len(world["historical_eras"]))
        self.assertGreater(summary["historical_era_count"], 0)
        self.assertEqual(summary["historical_event_count"], len(world["historical_events"]))
        self.assertGreater(summary["historical_event_count"], 0)
        self.assertIn("migration_event_count", summary)
        self.assertEqual(
            summary["migration_event_count"],
            sum(1 for event in world["historical_events"] if event["type"] == "migration"),
        )
        self.assertIn("dynastic_change_count", summary)
        self.assertEqual(
            summary["dynastic_change_count"],
            sum(1 for event in world["historical_events"] if event["type"] == "dynastic_change"),
        )
        self.assertIn("language_lineage_count", summary)
        self.assertEqual(
            summary["language_lineage_count"],
            sum(1 for language in world["language_regions"] if language["parent_language_region_id"] >= 0),
        )
        if summary["language_region_count"] > 1:
            self.assertGreater(summary["language_lineage_count"], 0)
        self.assertIn("mean_historical_instability", summary)
        self.assertIn("mean_cultural_continuity", summary)
        self.assertIn("mean_language_change_rate", summary)
        self.assertIn("mean_phonological_complexity", summary)
        self.assertIn("mean_sound_shift_index", summary)
        self.assertIn("mean_inherited_phonology_fraction", summary)
        self.assertGreaterEqual(summary["mean_phonological_complexity"], 0.0)
        self.assertLessEqual(summary["mean_phonological_complexity"], 1.0)
        self.assertGreaterEqual(summary["mean_sound_shift_index"], 0.0)
        self.assertLessEqual(summary["mean_sound_shift_index"], 1.0)
        self.assertGreaterEqual(summary["mean_inherited_phonology_fraction"], 0.0)
        self.assertLessEqual(summary["mean_inherited_phonology_fraction"], 1.0)
        self.assertEqual(summary["phonological_history_count"], len(world["phonological_histories"]))
        self.assertEqual(summary["phonological_history_count"], len(world["language_regions"]))
        self.assertEqual(
            summary["phonological_history_step_count"],
            sum(history["step_count"] for history in world["phonological_histories"]),
        )
        self.assertEqual(summary["phonological_rule_count"], len(world["phonological_rules"]))
        self.assertGreater(summary["phonological_rule_count"], 0)
        self.assertEqual(summary["lexical_correspondence_count"], len(world["lexical_correspondences"]))
        self.assertGreater(summary["lexical_correspondence_count"], 0)
        self.assertEqual(summary["lexical_diffusion_history_count"], len(world["lexical_diffusion_histories"]))
        self.assertEqual(summary["lexical_diffusion_history_count"], len(world["language_regions"]))
        self.assertEqual(
            summary["lexical_diffusion_step_count"],
            sum(history["step_count"] for history in world["lexical_diffusion_histories"]),
        )
        self.assertEqual(summary["speaker_population_history_count"], len(world["speaker_population_histories"]))
        self.assertEqual(summary["speaker_population_history_count"], len(world["language_regions"]))
        self.assertEqual(
            summary["speaker_population_step_count"],
            sum(history["step_count"] for history in world["speaker_population_histories"]),
        )
    def test_language_regions(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        summary = world["summary"]
        self.assertEqual(
            summary["lexical_correspondence_language_count"],
            sum(1 for language in world["language_regions"] if language["lexical_correspondence_count"] > 0),
        )
        self.assertEqual(
            summary["lexical_diffusion_language_count"],
            sum(1 for language in world["language_regions"] if language["lexical_diffusion_history_id"] >= 0),
        )
        self.assertEqual(
            summary["phonological_rule_language_count"],
            sum(1 for language in world["language_regions"] if language["sound_change_rule_count"] > 0),
        )
        self.assertEqual(
            summary["max_phonological_shift_stage"],
            max((rule["stage_index"] for rule in world["phonological_rules"]), default=0),
        )
        self.assertGreaterEqual(summary["mean_phonological_rule_probability_index"], 0.0)
        self.assertLessEqual(summary["mean_phonological_rule_probability_index"], 1.0)
        self.assertGreaterEqual(summary["mean_phonological_rule_regularity_index"], 0.0)
        self.assertLessEqual(summary["mean_phonological_rule_regularity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_lexical_replacement_index"], 0.0)
        self.assertLessEqual(summary["mean_lexical_replacement_index"], 1.0)
        self.assertGreaterEqual(summary["mean_phonological_contact_influence_index"], 0.0)
        self.assertLessEqual(summary["mean_phonological_contact_influence_index"], 1.0)
        self.assertGreaterEqual(summary["mean_phonological_drift_index"], 0.0)
        self.assertLessEqual(summary["mean_phonological_drift_index"], 1.0)
        self.assertGreaterEqual(summary["mean_language_prosodic_complexity_index"], 0.0)
        self.assertLessEqual(summary["mean_language_prosodic_complexity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_phonotactic_complexity_index"], 0.0)
        self.assertLessEqual(summary["mean_phonotactic_complexity_index"], 1.0)
        self.assertGreaterEqual(summary["mean_regular_correspondence_fraction"], 0.0)
        self.assertLessEqual(summary["mean_regular_correspondence_fraction"], 1.0)
        self.assertGreaterEqual(summary["mean_lexical_correspondence_replacement_index"], 0.0)
        self.assertLessEqual(summary["mean_lexical_correspondence_replacement_index"], 1.0)
        self.assertGreaterEqual(summary["mean_lexical_prosodic_weight_index"], 0.0)
        self.assertLessEqual(summary["mean_lexical_prosodic_weight_index"], 1.0)
        self.assertGreaterEqual(summary["mean_lexical_diffusion_adoption_index"], 0.0)
        self.assertLessEqual(summary["mean_lexical_diffusion_adoption_index"], 1.0)
        self.assertGreaterEqual(summary["mean_lexical_innovation_index"], 0.0)
        self.assertLessEqual(summary["mean_lexical_innovation_index"], 1.0)
        self.assertGreaterEqual(summary["mean_semantic_shift_index"], 0.0)
        self.assertLessEqual(summary["mean_semantic_shift_index"], 1.0)
        self.assertGreater(summary["total_estimated_speaker_population"], 0.0)
        self.assertGreaterEqual(summary["mean_speaker_allophonic_variation_index"], 0.0)
        self.assertLessEqual(summary["mean_speaker_allophonic_variation_index"], 1.0)
        self.assertGreaterEqual(summary["mean_speaker_syllable_pressure_index"], 0.0)
        self.assertLessEqual(summary["mean_speaker_syllable_pressure_index"], 1.0)
        self.assertGreaterEqual(summary["mean_speaker_contact_index"], 0.0)
        self.assertLessEqual(summary["mean_speaker_contact_index"], 1.0)
        self.assertGreaterEqual(summary["mean_speaker_population_adoption_index"], 0.0)
        self.assertLessEqual(summary["mean_speaker_population_adoption_index"], 1.0)
        self.assertGreaterEqual(summary["mean_speaker_phonetic_reduction_index"], 0.0)
        self.assertLessEqual(summary["mean_speaker_phonetic_reduction_index"], 1.0)
        self.assertGreaterEqual(summary["mean_speaker_lexical_diffusion_pressure_index"], 0.0)
        self.assertLessEqual(summary["mean_speaker_lexical_diffusion_pressure_index"], 1.0)
        self.assertAlmostEqual(
            summary["mean_phonological_rule_probability_index"],
            sum(rule["probability_index"] for rule in world["phonological_rules"]) / len(world["phonological_rules"]),
            delta=0.0001,
        )
        self.assertAlmostEqual(
            summary["mean_regular_correspondence_fraction"],
            sum(record["regular_correspondence_fraction"] for record in world["lexical_correspondences"])
            / len(world["lexical_correspondences"]),
            delta=0.0001,
        )
        self.assertAlmostEqual(
            summary["mean_lexical_diffusion_adoption_index"],
            sum(history["mean_diffusion_adoption_index"] for history in world["lexical_diffusion_histories"])
            / len(world["lexical_diffusion_histories"]),
            delta=0.0001,
        )
    def test_cultures_2(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        first_culture = world["cultures"][0]
        self.assertIn("language_region_id", first_culture)
        self.assertIn("homeland_region_id", first_culture)
        self.assertIn("type", first_culture)
        self.assertIn("agricultural_area_km2", first_culture)
        self.assertIn("mining_area_km2", first_culture)
        self.assertIn("migration_pressure", first_culture)
        self.assertIn("continuity_index", first_culture)
        self.assertIn("estimated_age_years", first_culture)

        first_language = world["language_regions"][0]
        self.assertIn("family", first_language)
        self.assertIn("culture_ids", first_language)
        self.assertIn("trade_contact_index", first_language)
        self.assertIn("parent_language_region_id", first_language)
        self.assertIn("lineage_depth", first_language)
        self.assertIn("divergence_age_years", first_language)
        self.assertIn("change_rate", first_language)
        self.assertIn("phoneme_inventory_size", first_language)
        self.assertIn("phonological_complexity", first_language)
        self.assertIn("sound_shift_index", first_language)
        self.assertIn("inherited_phonology_fraction", first_language)
        self.assertIn("phonological_history_id", first_language)
        self.assertIn("sound_change_rule_ids", first_language)
        self.assertIn("sound_change_rule_count", first_language)
        self.assertIn("final_phoneme_inventory_size", first_language)
        self.assertIn("phonological_drift_index", first_language)
        self.assertIn("lexical_correspondence_ids", first_language)
        self.assertIn("lexical_correspondence_count", first_language)
        self.assertIn("lexical_diffusion_history_id", first_language)
        self.assertIn("speaker_population_history_id", first_language)
        self.assertIn("syllable_template", first_language)
        self.assertIn("stress_system", first_language)
        self.assertIn("allowed_coda_count", first_language)
        self.assertIn("prosodic_complexity_index", first_language)
        self.assertIn("phonotactic_complexity_index", first_language)
        self.assertGreaterEqual(first_language["phoneme_inventory_size"], 16)
        self.assertLessEqual(first_language["phoneme_inventory_size"], 58)
        self.assertGreaterEqual(first_language["phonological_complexity"], 0.0)
        self.assertLessEqual(first_language["phonological_complexity"], 1.0)
        self.assertGreaterEqual(first_language["sound_shift_index"], 0.0)
        self.assertLessEqual(first_language["sound_shift_index"], 1.0)
        self.assertGreaterEqual(first_language["inherited_phonology_fraction"], 0.0)
        self.assertLessEqual(first_language["inherited_phonology_fraction"], 1.0)
        self.assertEqual(first_language["sound_change_rule_count"], len(first_language["sound_change_rule_ids"]))
        self.assertEqual(first_language["lexical_correspondence_count"], len(first_language["lexical_correspondence_ids"]))
        self.assertEqual(first_language["final_phoneme_inventory_size"], first_language["phoneme_inventory_size"])
        self.assertGreaterEqual(first_language["phonological_drift_index"], 0.0)
        self.assertLessEqual(first_language["phonological_drift_index"], 1.0)
        self.assertGreaterEqual(first_language["allowed_coda_count"], 1)
        self.assertTrue(first_language["syllable_template"])
        self.assertTrue(first_language["stress_system"])
        self.assertGreaterEqual(first_language["prosodic_complexity_index"], 0.0)
        self.assertLessEqual(first_language["prosodic_complexity_index"], 1.0)
        self.assertGreaterEqual(first_language["phonotactic_complexity_index"], 0.0)
        self.assertLessEqual(first_language["phonotactic_complexity_index"], 1.0)

        first_phonology_history = world["phonological_histories"][0]
        self.assertIn("language_region_id", first_phonology_history)
        self.assertIn("parent_language_region_id", first_phonology_history)
        self.assertIn("initial_phoneme_inventory_size", first_phonology_history)
        self.assertIn("final_phoneme_inventory_size", first_phonology_history)
        self.assertIn("sound_change_rule_ids", first_phonology_history)
        self.assertIn("sound_change_rule_count", first_phonology_history)
        self.assertIn("step_count", first_phonology_history)
        self.assertIn("cumulative_sound_shift_index", first_phonology_history)
        self.assertIn("phonological_drift_index", first_phonology_history)
        self.assertIn("syllable_template", first_phonology_history)
        self.assertIn("stress_system", first_phonology_history)
        self.assertIn("allowed_coda_count", first_phonology_history)
        self.assertIn("prosodic_complexity_index", first_phonology_history)
        self.assertIn("phonotactic_complexity_index", first_phonology_history)
        self.assertEqual(first_phonology_history["step_count"], len(first_phonology_history["steps"]))
        self.assertEqual(first_phonology_history["sound_change_rule_count"], len(first_phonology_history["sound_change_rule_ids"]))
        self.assertEqual(first_phonology_history["final_phoneme_inventory_size"], first_language["phoneme_inventory_size"])
        self.assertGreaterEqual(first_phonology_history["initial_phoneme_inventory_size"], 1)
        self.assertGreaterEqual(first_phonology_history["cumulative_sound_shift_index"], 0.0)
        self.assertLessEqual(first_phonology_history["cumulative_sound_shift_index"], 1.0)
        self.assertGreaterEqual(first_phonology_history["phonological_drift_index"], 0.0)
        self.assertLessEqual(first_phonology_history["phonological_drift_index"], 1.0)
        self.assertEqual(first_phonology_history["syllable_template"], first_language["syllable_template"])
        self.assertEqual(first_phonology_history["stress_system"], first_language["stress_system"])
        self.assertGreaterEqual(first_phonology_history["allowed_coda_count"], 1)
        self.assertGreaterEqual(first_phonology_history["prosodic_complexity_index"], 0.0)
        self.assertLessEqual(first_phonology_history["prosodic_complexity_index"], 1.0)
        self.assertGreaterEqual(first_phonology_history["phonotactic_complexity_index"], 0.0)
        self.assertLessEqual(first_phonology_history["phonotactic_complexity_index"], 1.0)
        for index, step in enumerate(first_phonology_history["steps"]):
            self.assertEqual(step["stage_index"], index + 1)
            self.assertIn("era_id", step)
            self.assertIn("rule_ids", step)
            self.assertEqual(step["rule_count"], len(step["rule_ids"]))
            self.assertGreaterEqual(step["start_year_bp"], step["end_year_bp"])
            self.assertGreaterEqual(step["inventory_size"], 1)
            self.assertEqual(step["syllable_template"], first_language["syllable_template"])
            self.assertEqual(step["stress_system"], first_language["stress_system"])
            self.assertGreaterEqual(step["cumulative_sound_shift_index"], 0.0)
            self.assertLessEqual(step["cumulative_sound_shift_index"], 1.0)
            self.assertGreaterEqual(step["inherited_phonology_fraction"], 0.0)
            self.assertLessEqual(step["inherited_phonology_fraction"], 1.0)
            self.assertGreaterEqual(step["contact_influence_index"], 0.0)
            self.assertLessEqual(step["contact_influence_index"], 1.0)
            self.assertGreaterEqual(step["phonotactic_complexity_index"], 0.0)
            self.assertLessEqual(step["phonotactic_complexity_index"], 1.0)
            self.assertGreaterEqual(step["prosodic_weight_index"], 0.0)
            self.assertLessEqual(step["prosodic_weight_index"], 1.0)
        self.assertEqual(
            first_phonology_history["steps"][-1]["inventory_size"],
            first_phonology_history["final_phoneme_inventory_size"],
        )

        first_rule = world["phonological_rules"][0]
        self.assertIn("language_region_id", first_rule)
        self.assertIn("parent_language_region_id", first_rule)
        self.assertIn("era_id", first_rule)
        self.assertIn("stage_index", first_rule)
        self.assertIn("rule_type", first_rule)
        self.assertIn("source_segment", first_rule)
        self.assertIn("target_segment", first_rule)
        self.assertIn("source_features", first_rule)
        self.assertIn("target_features", first_rule)
        self.assertIn("articulatory_shift", first_rule)
        self.assertIn("environment", first_rule)
        self.assertIn("conditioned_by", first_rule)
        self.assertIn("prosodic_domain", first_rule)
        self.assertIn("probability_index", first_rule)
        self.assertIn("regularity_index", first_rule)
        self.assertIn("lexical_replacement_index", first_rule)
        self.assertIn("contact_influence_index", first_rule)
        self.assertIn("inventory_delta", first_rule)
        self.assertGreater(first_rule["stage_index"], 0)
        self.assertIsInstance(first_rule["source_features"], dict)
        self.assertIsInstance(first_rule["target_features"], dict)
        self.assertTrue(first_rule["articulatory_shift"])
        self.assertTrue(first_rule["prosodic_domain"])
        self.assertNotEqual(first_rule["source_segment"], first_rule["target_segment"])
        self.assertGreaterEqual(first_rule["start_year_bp"], first_rule["end_year_bp"])
        self.assertGreaterEqual(first_rule["probability_index"], 0.0)
        self.assertLessEqual(first_rule["probability_index"], 1.0)
        self.assertGreaterEqual(first_rule["regularity_index"], 0.0)
        self.assertLessEqual(first_rule["regularity_index"], 1.0)
        self.assertGreaterEqual(first_rule["lexical_replacement_index"], 0.0)
        self.assertLessEqual(first_rule["lexical_replacement_index"], 1.0)
        self.assertGreaterEqual(first_rule["contact_influence_index"], 0.0)
        self.assertLessEqual(first_rule["contact_influence_index"], 1.0)

        first_correspondence = world["lexical_correspondences"][0]
        self.assertIn("language_region_id", first_correspondence)
        self.assertIn("parent_language_region_id", first_correspondence)
        self.assertIn("meaning", first_correspondence)
        self.assertIn("semantic_domain", first_correspondence)
        self.assertIn("proto_form", first_correspondence)
        self.assertIn("inherited_form", first_correspondence)
        self.assertIn("derived_form", first_correspondence)
        self.assertIn("applied_rule_ids", first_correspondence)
        self.assertIn("applied_rule_count", first_correspondence)
        self.assertIn("replacement_count", first_correspondence)
        self.assertIn("regular_correspondence_fraction", first_correspondence)
        self.assertIn("lexical_replacement_index", first_correspondence)
        self.assertIn("stress_pattern", first_correspondence)
        self.assertIn("syllable_count", first_correspondence)
        self.assertIn("syllable_pattern", first_correspondence)
        self.assertIn("mora_count", first_correspondence)
        self.assertIn("prosodic_weight_index", first_correspondence)
        self.assertIn("diffusion_stage_index", first_correspondence)
        self.assertIn("diffusion_adoption_index", first_correspondence)
        self.assertIn("semantic_shift_index", first_correspondence)
        self.assertIn("borrowed", first_correspondence)
        self.assertEqual(first_correspondence["language_region_id"], first_language["id"])
        self.assertEqual(first_correspondence["applied_rule_count"], len(first_correspondence["applied_rule_ids"]))
        self.assertGreaterEqual(first_correspondence["replacement_count"], 0)
        self.assertGreater(first_correspondence["syllable_count"], 0)
        self.assertGreater(first_correspondence["mora_count"], 0)
        self.assertTrue(first_correspondence["meaning"])
        self.assertTrue(first_correspondence["derived_form"])
        self.assertTrue(first_correspondence["syllable_pattern"])
        self.assertGreaterEqual(first_correspondence["regular_correspondence_fraction"], 0.0)
        self.assertLessEqual(first_correspondence["regular_correspondence_fraction"], 1.0)
        self.assertGreaterEqual(first_correspondence["lexical_replacement_index"], 0.0)
        self.assertLessEqual(first_correspondence["lexical_replacement_index"], 1.0)
        self.assertAlmostEqual(
            first_correspondence["regular_correspondence_fraction"] + first_correspondence["lexical_replacement_index"],
            1.0,
            delta=0.001,
        )
        self.assertGreaterEqual(first_correspondence["prosodic_weight_index"], 0.0)
        self.assertLessEqual(first_correspondence["prosodic_weight_index"], 1.0)
        self.assertGreater(first_correspondence["diffusion_stage_index"], 0)
        self.assertGreaterEqual(first_correspondence["diffusion_adoption_index"], 0.0)
        self.assertLessEqual(first_correspondence["diffusion_adoption_index"], 1.0)
        self.assertGreaterEqual(first_correspondence["semantic_shift_index"], 0.0)
        self.assertLessEqual(first_correspondence["semantic_shift_index"], 1.0)
        self.assertIsInstance(first_correspondence["borrowed"], bool)

        first_diffusion = world["lexical_diffusion_histories"][0]
        self.assertIn("language_region_id", first_diffusion)
        self.assertIn("parent_language_region_id", first_diffusion)
        self.assertIn("phonological_history_id", first_diffusion)
        self.assertIn("lexical_correspondence_ids", first_diffusion)
        self.assertIn("lexical_correspondence_count", first_diffusion)
        self.assertIn("step_count", first_diffusion)
        self.assertIn("syllable_template", first_diffusion)
        self.assertIn("stress_system", first_diffusion)
        self.assertIn("mean_diffusion_adoption_index", first_diffusion)
        self.assertIn("mean_lexical_innovation_index", first_diffusion)
        self.assertIn("mean_semantic_shift_index", first_diffusion)
        self.assertIn("contact_borrowing_index", first_diffusion)
        self.assertIn("steps", first_diffusion)
        self.assertEqual(first_language["lexical_diffusion_history_id"], first_diffusion["id"])
        self.assertEqual(first_diffusion["language_region_id"], first_language["id"])
        self.assertEqual(first_diffusion["phonological_history_id"], first_language["phonological_history_id"])
        self.assertEqual(first_diffusion["lexical_correspondence_count"], len(first_diffusion["lexical_correspondence_ids"]))
        self.assertEqual(first_diffusion["step_count"], len(first_diffusion["steps"]))
        self.assertEqual(set(first_diffusion["lexical_correspondence_ids"]), set(first_language["lexical_correspondence_ids"]))
        self.assertEqual(first_diffusion["syllable_template"], first_language["syllable_template"])
        self.assertEqual(first_diffusion["stress_system"], first_language["stress_system"])
        self.assertGreaterEqual(first_diffusion["mean_diffusion_adoption_index"], 0.0)
        self.assertLessEqual(first_diffusion["mean_diffusion_adoption_index"], 1.0)
        self.assertGreaterEqual(first_diffusion["mean_lexical_innovation_index"], 0.0)
        self.assertLessEqual(first_diffusion["mean_lexical_innovation_index"], 1.0)
        self.assertGreaterEqual(first_diffusion["mean_semantic_shift_index"], 0.0)
        self.assertLessEqual(first_diffusion["mean_semantic_shift_index"], 1.0)
        self.assertGreaterEqual(first_diffusion["contact_borrowing_index"], 0.0)
        self.assertLessEqual(first_diffusion["contact_borrowing_index"], 1.0)
        for index, step in enumerate(first_diffusion["steps"]):
            self.assertEqual(step["stage_index"], index + 1)
            self.assertIn("era_id", step)
            self.assertIn("affected_correspondence_ids", step)
            self.assertIn("affected_meanings", step)
            self.assertEqual(step["affected_correspondence_count"], len(step["affected_correspondence_ids"]))
            self.assertEqual(len(step["affected_meanings"]), len(step["affected_correspondence_ids"]))
            self.assertGreaterEqual(step["start_year_bp"], step["end_year_bp"])
            self.assertGreaterEqual(step["affected_domain_count"], 0)
            self.assertGreaterEqual(step["adoption_fraction"], 0.0)
            self.assertLessEqual(step["adoption_fraction"], 1.0)
            self.assertGreaterEqual(step["innovation_fraction"], 0.0)
            self.assertLessEqual(step["innovation_fraction"], 1.0)
            self.assertGreaterEqual(step["contact_borrowing_index"], 0.0)
            self.assertLessEqual(step["contact_borrowing_index"], 1.0)
            self.assertGreaterEqual(step["regularization_index"], 0.0)
            self.assertLessEqual(step["regularization_index"], 1.0)
            self.assertGreaterEqual(step["semantic_shift_index"], 0.0)
            self.assertLessEqual(step["semantic_shift_index"], 1.0)
    def test_historical_eras(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        first_era = world["historical_eras"][0]
        self.assertIn("dominant_process", first_era)
        self.assertIn("start_year_bp", first_era)
        self.assertIn("end_year_bp", first_era)
        self.assertIn("event_count", first_era)
        self.assertIn("mean_instability", first_era)

        first_event = world["historical_events"][0]
        self.assertIn("era_id", first_event)
        self.assertIn("type", first_event)
        self.assertIn("year_bp", first_event)
        self.assertIn("region_id", first_event)
        self.assertIn("culture_region_id", first_event)
        self.assertIn("language_region_id", first_event)
        self.assertIn("pressure_index", first_event)
        self.assertIn("continuity_index", first_event)
    def test_culture_history_models_declare_their_documented_identities(self) -> None:
        """Every culture/history replay names its documented model and emits records.

        Field-by-field tamper coverage for these replays lives in
        ``test_cultural_geography_validation``, ``test_historical_geography_validation``
        and ``test_phonology_history_validation``, which call the validators directly
        against the 128-cell replay world and assert the undone tamper replays clean
        again -- a claim a CLI verdict line cannot make.
        """

        world = worlds.cached_world_readonly("mid_512")

        for model_key, model_type in (
            (
                "culture_region_model",
                "causal_political_homeland_barrier_trade_culture_regions_v1",
            ),
            ("language_region_model", "causal_trade_union_family_lineage_phonology_v1"),
            ("cultural_site_model", "causal_terrain_culture_ranked_sacred_ruin_sites_v1"),
            (
                "historical_event_model",
                "causal_region_culture_language_trade_site_timeline_v1",
            ),
            (
                "phonology_history_model",
                "causal_language_era_sound_rule_lexical_diffusion_speaker_history_v1",
            ),
        ):
            with self.subTest(model=model_key):
                self.assertEqual(world[model_key]["model_type"], model_type)

        for family in (
            "cultures",
            "language_regions",
            "sacred_areas",
            "ruins",
            "historical_events",
            "phonological_rules",
            "phonological_histories",
            "lexical_correspondences",
            "lexical_diffusion_histories",
            "speaker_population_histories",
        ):
            with self.subTest(family=family):
                self.assertTrue(world[family], family)

        self.assertEqual(len(world["historical_eras"]), 4)

    def test_validate_reports_every_culture_history_replay_verdict(self) -> None:
        """``validate`` reaches and reports the culture, history and phonology replays.

        Wiring is the one claim the dedicated validator modules cannot make -- they
        never go through the public command. One tamper per verdict in a single pass
        is all that claim needs.
        """

        world = worlds.cached_world("mid_512")
        runner = CliRunner()

        with TemporaryDirectory() as temporary_directory:
            world_path = Path(temporary_directory) / "world.json"

            def validate_current() -> Result:
                world_path.write_text(json.dumps(world), encoding="utf-8")
                return runner.invoke(app, ["validate", "--world", str(world_path)])

            control = validate_current()
            assert_no_cli_crash(self, control, command="validate")
            self.assertEqual(control.exit_code, 0, control.output)

            culture = world["cultures"][0]
            culture["type"] = (
                "agrarian_lowland" if culture["type"] != "agrarian_lowland" else "river_valley"
            )
            world["historical_events"][0]["year_bp"] += 2.0
            world["phonological_rules"][0]["probability_index"] += 0.01

            result = validate_current()

        assert_no_cli_crash(self, result, command="validate")
        self.assertEqual(result.exit_code, 1, result.output)
        for message in (
            "cultural geography model or causal replay invalid",
            "historical geography model or causal replay invalid",
            "phonology history model or causal replay invalid",
        ):
            with self.subTest(message=message):
                self.assertIn(message, result.output)
