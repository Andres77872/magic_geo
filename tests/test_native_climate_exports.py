"""Export native annual budgets without converting unavailable legacy fields to zero."""
import csv
from copy import deepcopy

from magic_geo.climate_energy import enrich_world_with_climate_energy_balance
from magic_geo.io import write_cells_csv, write_summary_markdown
from magic_geo.native_climate_energy import CELL_FIELDS, SUMMARY_FIELDS
from tests.support.native_climate_energy import native_climate_world


# The native budget block remains at 407..417. These additive fields follow it
# in the adopted parent/species/fire, natural-water and land-use CSV contract.
POST_NATIVE_FIELDS = [
    "terrestrial_primary_climate_supported", "primary_productivity_supported",
    "vegetation_biomass_supported", "forest_growth_supported", "vegetation_succession_supported",
    "species_richness_supported", "ecosystem_wildfire_spread_risk_supported",
    "ecosystem_disturbance_pressure_supported", "vegetation_recovery_supported",
    "species_canopy_tree_score_supported", "species_grassland_grazer_score_supported",
    "species_desert_specialist_score_supported", "species_alpine_tundra_specialist_score_supported",
    "species_large_predator_score_supported", "species_wetland_amphibian_score_supported",
    "species_reef_builder_score_supported", "species_mangrove_coastal_bird_score_supported",
    "species_composition_confidence_supported", "species_endemism_supported",
    "species_record_descriptors_supported", "species_guild_scores",
    "species_applicable_guild_count", "species_supported_guild_count", "species_composition_status",
    "wildfire_fuel_continuity_supported", "wildfire_firebreak_supported",
    "wildfire_ignition_potential_supported", "aquifer_natural_limitation_index",
    "agricultural_habitat_applicable", "agricultural_climate_supported",
    "agricultural_potential_supported", "mining_surface_applicable",
]


def test_csv_keeps_native_energy_values_and_legacy_absence(tmp_path):
    world = native_climate_world()
    enrich_world_with_climate_energy_balance(world)
    before = deepcopy(world)
    path = tmp_path / "native.csv"
    write_cells_csv(path, world)
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        header = reader.fieldnames
    assert len(header) == 450 == len(set(header))
    assert header[396] == "thermal_subsidence_target_m"
    assert header[406] == "species_freshwater_fishery_input_mode"
    assert set(header[407:418]) == CELL_FIELDS
    assert header[418:] == POST_NATIVE_FIELDS
    for row, cell in zip(rows, world["cells"]):
        for field in CELL_FIELDS:
            assert float(row[field]) == cell[field]
        for field in ("climate_energy_stress_index", "reef_bleaching_risk_index", "absorbed_shortwave_w_m2"):
            assert row[field] == ""
    assert world == before


def test_legacy_csv_leaves_new_budget_fields_blank(tmp_path):
    path = tmp_path / "legacy.csv"
    write_cells_csv(path, {"cells": [{"id": 0, "absorbed_shortwave_w_m2": 123.0, "reef_bleaching_risk_index": 0}]})
    with path.open(newline="", encoding="utf-8") as stream:
        row = next(csv.DictReader(stream))
    assert row["absorbed_shortwave_w_m2"] == "123.0"
    assert row["reef_bleaching_risk_index"] == "0"
    assert all(row[field] == "" for field in CELL_FIELDS)


def test_markdown_reports_native_weighted_budgets_and_bleaching_unavailability(tmp_path):
    world = native_climate_world()
    enrich_world_with_climate_energy_balance(world)
    world["reef_diagnostics_model"] = {
        "model": "heuristic_coastal_reef_native_seasonal_v3", "bleaching_estimate_available": False,
    }
    path = tmp_path / "summary.md"
    write_summary_markdown(path, world)
    text = path.read_text()
    for key in SUMMARY_FIELDS:
        assert f"- `{key}`: {world['summary'][key]}" in text
    assert "Reef bleaching: not estimated" in text
    assert "`mean_reef_bleaching_risk_index`" not in text
    assert "`mean_climate_energy_stress_index`" not in text
