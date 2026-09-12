"""Historical species v3 consumes explicit E4 parent availability."""
from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS
from magic_geo.species_ranges import enrich_world_with_species_ranges, SPECIES_PARENT_MODEL
from magic_geo.species_habitat_validation import validate_species_habitat_support


GUILDS = (
    "canopy_tree", "grassland_grazer", "desert_specialist", "alpine_tundra_specialist",
    "large_predator", "wetland_amphibian", "freshwater_fish", "marine_fish",
    "reef_builder", "mangrove_coastal_bird",
)
DESCRIPTOR_FLAGS = ("species_composition_confidence_supported", "species_endemism_supported", "species_record_descriptors_supported")


def cell(temperature=18.0, **changes):
    result = {
        "id": 0, "is_water": False, "is_lake": False, "water_body_type": "land",
        "temperature_c": temperature, "temperature_monthly_c": [temperature]*12,
        "biome": "temperate_forest", "precipitation_mm_y": 1800.0,
        "potential_evapotranspiration_mm_y": 800.0, "soil_moisture_index": .8,
        "fertility": .9, "growing_season_months": 12, "soil_organic_matter_fraction": .2,
        "wind_east": .2, "biome_confidence_index": .8, "reef_growth_index": 0.0,
        "wetland_extent_index": 0.0, "wetland_hydrology_index": 0.0,
        "area_km2": 100.0, "lat_deg": 0.0, "lon_deg": 0.0, "neighbors": [],
    }
    result.update(changes)
    return result


def parent(*cells):
    world = {"cells": list(cells or [cell()]), "summary": {},
             "ecosystem_dynamics_model": deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])}
    enrich_world_with_ecosystem_dynamics(world)
    return world


def species(world):
    assert enrich_world_with_species_ranges(world) is world
    assert validate_species_habitat_support(world) == []
    return world


def test_healthy_scores_and_record_means_have_independently_checked_sources():
    world = species(parent())
    c = world["cells"][0]
    assert set(c["species_guild_scores"]) == set(GUILDS)
    assert c["species_applicable_guild_count"] == 8  # five land plus three legacy habitats
    assert c["species_composition_status"] == "partial"  # alpine own term and reef fishery input unavailable
    assert c["species_canopy_tree_score_supported"] is True
    assert c["species_guild_scores"]["canopy_tree"] > .46
    assert c["species_alpine_tundra_specialist_score_supported"] is False
    assert all(c[k] is True for k in DESCRIPTOR_FLAGS)
    record = next(r for r in world["species_range_records"] if r["guild_type"] == "canopy_tree")
    assert "mean_forest_growth_index" in record["habitat_evidence"]
    assert "mean_fishery_productivity_index" not in record["habitat_evidence"]
    assert record["mean_primary_productivity_index"] == c["primary_productivity_index"]
    snapshot = deepcopy(world)
    species(world)
    assert world == snapshot


@pytest.mark.parametrize("temperature", [-80.0, -16.0, 52.0, 80.0])
def test_unavailable_parent_production_is_not_reported_as_absent_species(temperature):
    world = species(parent(cell(temperature, biome="tropical_rainforest", wetland_extent_index=1.0)))
    c = world["cells"][0]
    assert c["species_applicable_guild_count"] == 8
    assert c["species_supported_guild_count"] == 0
    assert c["species_composition_status"] == "unavailable"
    assert c["dominant_species_guild"] == "none"
    assert c["species_guild_richness_count"] == 0
    assert all(c[f"species_{g}_score_supported"] is False and c["species_guild_scores"][g] == 0 for g in GUILDS)
    assert all(c[k] is False for k in DESCRIPTOR_FLAGS)
    assert world["species_range_records"] == []


@pytest.mark.parametrize("guild,lower,upper", [
    ("canopy_tree",-6.0,42.0), ("grassland_grazer",-6.0,42.0),
    ("wetland_amphibian",11.0,39.0), ("mangrove_coastal_bird",11.0,39.0),
    ("freshwater_fish",-10.0,38.0), ("marine_fish",-11.0,37.0), ("reef_builder",11.0,39.0),
])
@pytest.mark.parametrize("which,inside", [("lower",False),("inside_lower",True),("inside_upper",True),("upper",False)])
def test_own_original_open_temperature_windows(guild,lower,upper,which,inside):
    t={"lower":lower,"inside_lower":math.nextafter(lower,math.inf),"inside_upper":math.nextafter(upper,-math.inf),"upper":upper}[which]
    changes={}
    if guild == "freshwater_fish":
        changes={"is_lake":True,"water_body_type":"fresh_lake"}
    elif guild in {"marine_fish","reef_builder"}:
        changes={"is_water":True,"water_body_type":"continental_shelf"}
    world=species(parent(cell(t,**changes)))
    assert world["cells"][0][f"species_{guild}_score_supported"] is inside
    if not inside:
        assert world["cells"][0]["species_guild_scores"][guild] == 0.0


def test_no_invented_desert_predator_or_alpine_lower_temperature_limit():
    world=species(parent(cell(-15.0,biome="tundra")))
    c=world["cells"][0]
    assert c["species_desert_specialist_score_supported"] is True
    assert c["species_large_predator_score_supported"] is True
    assert c["species_alpine_tundra_specialist_score_supported"] is True
    assert "desert_specialist" not in world["species_ranges_model"]["own_temperature_support_c"]
    assert "large_predator" not in world["species_ranges_model"]["own_temperature_support_c"]
    assert world["species_ranges_model"]["own_temperature_support_c"]["alpine_tundra_specialist"]["lower_exclusive"] is None
    for t,expected in [(math.nextafter(8.0,-math.inf),True),(8.0,False)]:
        assert species(parent(cell(t)))["cells"][0]["species_alpine_tundra_specialist_score_supported"] is expected


def test_outside_own_temperature_does_not_reduce_habitat_denominator():
    cool=species(parent(cell(18.0)))["cells"][0]
    hot=species(parent(cell(43.0)))["cells"][0]
    assert cool["species_applicable_guild_count"] == hot["species_applicable_guild_count"] == 8
    assert hot["species_terrestrial_habitat_eligible"] is True
    assert hot["species_canopy_tree_score_supported"] is False
    assert hot["species_composition_status"] == "partial"
    assert hot["species_supported_guild_count"] < cool["species_supported_guild_count"]


@pytest.mark.parametrize("water", [{"is_water":True,"water_body_type":"ocean"},{"is_lake":True,"water_body_type":"fresh_lake"},{"is_lake":True,"water_body_type":"saline_basin"}])
def test_aquatic_structural_biomass_zero_does_not_block_common_descriptors(water):
    world=species(parent(cell(**water)))
    c=world["cells"][0]
    assert c["vegetation_biomass_supported"] is False and c["vegetation_biomass_index"] == 0
    assert all(c[k] is True for k in DESCRIPTOR_FLAGS)
    assert c["species_canopy_tree_score_supported"] is False
    assert all(r["guild_type"] not in {"canopy_tree","grassland_grazer","desert_specialist","alpine_tundra_specialist","large_predator"} for r in world["species_range_records"])


def test_supported_zero_score_is_available_and_differs_from_no_supported_guilds():
    world=species(parent(cell(-5.0,biome="cold_desert",precipitation_mm_y=0.0,soil_moisture_index=0.0,fertility=0.0,growing_season_months=0,soil_organic_matter_fraction=0.0,ice_thickness_m=1200.0,wind_east=0.0)))
    c=world["cells"][0]
    assert c["primary_productivity_supported"] is True
    assert c["primary_productivity_index"] == 0.0
    assert c["species_canopy_tree_score_supported"] is True
    assert c["species_guild_scores"]["canopy_tree"] == 0.0
    assert c["species_supported_guild_count"] > 0
    assert c["species_composition_status"] != "unavailable"


def test_river_fish_omits_standing_fishery_in_score_and_record_evidence():
    world=parent(cell(is_river=True,river_channel_width_m=180.0,river_channel_depth_m=9.0))
    assert world["cells"][0]["fishery_productivity_supported"] is False
    species(world)
    c=world["cells"][0]
    assert c["species_freshwater_fish_score_supported"] is True
    fish=next(r for r in world["species_range_records"] if r["guild_type"]=="freshwater_fish")
    assert "mean_fishery_productivity_index" not in fish["habitat_evidence"]
    assert "mean_forest_growth_index" not in fish["habitat_evidence"]
    # Even a finite stale scalar cannot enter the direct river score.
    from magic_geo.species_ranges import _guild_scores
    baseline=_guild_scores(c)["freshwater_fish"]
    c["fishery_productivity_index"]=1.0
    assert _guild_scores(c)["freshwater_fish"]==baseline
    c["primary_productivity_supported"]=False
    assert _guild_scores(c)["freshwater_fish"]==0.0


def test_mixed_river_and_standing_component_omits_an_unsupported_aggregate_fishery_mean():
    world=species(parent(
        cell(id=0,is_river=True,river_channel_width_m=180.0,river_channel_depth_m=9.0,neighbors=[1]),
        cell(id=1,is_lake=True,water_body_type="fresh_lake",neighbors=[0]),
    ))
    fish=next(r for r in world["species_range_records"] if r["guild_type"]=="freshwater_fish")
    assert fish["cell_ids"]==[0,1]
    assert "mean_fishery_productivity_index" not in fish["habitat_evidence"]


def test_score_remains_supported_when_common_record_descriptor_is_unavailable():
    world=parent(cell())
    del world["cells"][0]["biome_confidence_index"]
    species(world)
    c=world["cells"][0]
    assert c["species_canopy_tree_score_supported"] is True
    assert c["species_guild_scores"]["canopy_tree"] >= .46
    assert c["species_composition_confidence_supported"] is False
    assert c["species_record_descriptors_supported"] is False
    assert c["species_composition_confidence_index"] == 0
    assert c["species_guild_richness_count"] > 0
    assert c["species_range_record_ids"] == [] and world["species_range_records"] == []


@pytest.mark.parametrize("guild",GUILDS)
def test_independent_validator_rejects_score_or_support_and_counter_forgery(guild):
    world=species(parent())
    broken=deepcopy(world)
    c=broken["cells"][0]
    c[f"species_{guild}_score_supported"]=not c[f"species_{guild}_score_supported"]
    broken["summary"]["species_score_supported_cell_counts"][guild]=int(c[f"species_{guild}_score_supported"])
    assert validate_species_habitat_support(broken)
    broken=deepcopy(world)
    broken["cells"][0]["species_guild_scores"][guild]+=.001
    assert any("score mismatch" in e for e in validate_species_habitat_support(broken))


@pytest.mark.parametrize("flag",DESCRIPTOR_FLAGS)
def test_independent_descriptor_support_cannot_be_forged(flag):
    world=species(parent())
    world["cells"][0][flag]=False
    world["summary"][flag+"_cell_count"]=0
    assert any(flag in e for e in validate_species_habitat_support(world))


@pytest.mark.parametrize("field",["species_applicable_guild_count","species_supported_guild_count","species_guild_richness_count"])
@pytest.mark.parametrize("value",[True,None,-1,999])
def test_composition_counts_are_exact_integers(field,value):
    world=species(parent())
    world["cells"][0][field]=value
    assert validate_species_habitat_support(world)


@pytest.mark.parametrize("value",["complete","unavailable","not_applicable",None,{}])
def test_composition_status_cannot_hide_partial_support(value):
    world=species(parent())
    assert world["cells"][0]["species_composition_status"]=="partial"
    world["cells"][0]["species_composition_status"]=value
    assert validate_species_habitat_support(world)


@pytest.mark.parametrize("field",["mean_primary_productivity_index","mean_species_richness_index","mean_disturbance_pressure_index","mean_composition_confidence_index"])
def test_record_common_means_are_replayed(field):
    world=species(parent())
    world["species_range_records"][0][field]+=.001
    assert any(field in e for e in validate_species_habitat_support(world))


@pytest.mark.parametrize("mutation",["extra_record","missing_record","member","inverse","unused_fishery_mean","metadata"])
def test_record_coverage_and_consumed_evidence_mutations(mutation):
    world=species(parent())
    if mutation=="extra_record": world["species_range_records"].append(deepcopy(world["species_range_records"][0]))
    elif mutation=="missing_record": world["species_range_records"].pop()
    elif mutation=="member": world["species_range_records"][0]["cell_ids"]=[False]
    elif mutation=="inverse": world["cells"][0]["species_range_record_ids"]=[]
    elif mutation=="unused_fishery_mean": world["species_range_records"][0]["habitat_evidence"]["mean_fishery_productivity_index"]=0.0
    else: world["species_ranges_model"]["score_parent_inputs"]["canopy_tree"]=[]
    assert validate_species_habitat_support(world)


@pytest.mark.parametrize("field",["reef_growth_index","wetland_extent_index","biome_confidence_index","temperature_c","primary_productivity_index","ecosystem_disturbance_pressure_index"])
@pytest.mark.parametrize("value",[None,True,"0.1",[],{},math.inf,10**400])
def test_invalid_present_sources_fail_before_species_mutation(field,value):
    world=parent()
    world["cells"][0][field]=value
    before=deepcopy(world)
    with pytest.raises(ValueError): enrich_world_with_species_ranges(world)
    assert world==before


def test_source_certificates_and_monthly_values_are_not_modified_or_consulted_as_feedback():
    world=parent()
    markers={key:{"unchanged":[1,2]} for key in ("climate_model","climate_energy_model","climate_energy_balance_records","climate_energy_forcing_intervals","climate_energy_transport_edges")}
    world.update(markers)
    monthly=world["cells"][0]["temperature_monthly_c"]
    species(world)
    assert all(world[k] is value for k,value in markers.items())
    assert world["cells"][0]["temperature_monthly_c"] is monthly
    baseline=deepcopy(world)
    world["wildfire_spread_histories"]=[{"downstream":True}]
    world["cells"][0]["wildfire_fuel_continuity_index"]=999
    species(world)
    del world["wildfire_spread_histories"]
    del world["cells"][0]["wildfire_fuel_continuity_index"]
    assert world==baseline


def test_component_links_are_rebuilt_after_parent_availability_changes():
    world=species(parent(cell(id=0,neighbors=[1]),cell(id=1,neighbors=[0,2]),cell(id=2,neighbors=[1])))
    assert next(r for r in world["species_range_records"] if r["guild_type"]=="canopy_tree")["cell_ids"]==[0,1,2]
    world["cells"][1]["temperature_c"]=80.0
    enrich_world_with_ecosystem_dynamics(world)
    species(world)
    assert [r["cell_ids"] for r in world["species_range_records"] if r["guild_type"]=="canopy_tree"]==[[0],[2]]
    assert world["cells"][1]["species_range_record_ids"]==[]
    assert world["summary"]["species_composition_status_counts"]=={"partial":2,"unavailable":1}
    before=deepcopy(world)
    species(world)
    assert world==before


@pytest.mark.parametrize("field", ["range_fragmentation_index", "endemism_index", "conservation_stress_index", "mean_habitat_suitability_index", "max_habitat_suitability_index"])
def test_record_derived_descriptors_are_independently_replayed(field):
    world = species(parent())
    world["species_range_records"][0][field] += .01
    assert any(field in error for error in validate_species_habitat_support(world))


@pytest.mark.parametrize("field", ["mean_species_habitat_suitability_index", "mean_species_composition_confidence_index", "mean_species_endemism_index", "species_range_total_area_km2"])
def test_summary_means_cannot_hide_a_stale_record_or_unavailable_sentinel(field):
    world = species(parent())
    world["summary"][field] += .01
    assert any(field in error for error in validate_species_habitat_support(world))


@pytest.mark.parametrize("bad", [None, [], {}, "wrong", True, 1.0])
@pytest.mark.parametrize("target", ["model", "scores", "record", "record_members", "inverse", "summary", "dominant"])
def test_malformed_output_values_report_errors_without_raising(target, bad):
    world = species(parent())
    if target == "model":
        world["species_ranges_model"] = bad
    elif target == "scores":
        world["cells"][0]["species_guild_scores"] = bad
    elif target == "record":
        world["species_range_records"][0] = bad
    elif target == "record_members":
        world["species_range_records"][0]["cell_ids"] = bad
    elif target == "inverse":
        world["cells"][0]["species_range_record_ids"] = bad
    elif target == "summary":
        world["summary"] = bad
    else:
        world["cells"][0]["dominant_species_guild"] = bad
    assert validate_species_habitat_support(world)


_ARCHIVED_CASES = json.loads((Path(__file__).parent / "fixtures/terrestrial_primary_support/cells.json").read_text())["cases"]


@pytest.mark.parametrize("case", _ARCHIVED_CASES, ids=lambda case: case["name"])
def test_actual_archived_primary_inputs_keep_temperature_and_missing_descriptors_explicit(case):
    inputs = deepcopy(case["inputs"])
    temperature = inputs["temperature_c"]
    monthly = inputs["temperature_monthly_c"]
    world = species(parent(inputs))
    c = world["cells"][0]
    assert c["temperature_c"] == temperature
    assert c["temperature_monthly_c"] is monthly
    # The retained parent fixture intentionally lacks downstream reef/wetland/
    # biome-confidence descriptors; do not invent them to manufacture a record.
    assert c["species_record_descriptors_supported"] is False
    assert world["species_range_records"] == []
    if not -16.0 < temperature < 52.0:
        assert c["species_composition_status"] == "unavailable"
    else:
        assert c["species_supported_guild_count"] > 0
        assert c["species_composition_status"] == "partial"


def test_complete_habitat_composition_is_distinct_from_record_or_species_count():
    world = species(parent(cell(is_water=True, water_body_type="ocean")))
    c = world["cells"][0]
    assert c["species_applicable_guild_count"] == c["species_supported_guild_count"] == 4
    assert c["species_composition_status"] == "complete"
    # All four models are applicable and supported; a low score is not a gap.
    assert c["species_guild_richness_count"] < 4


def test_frozen_v2_archive_retains_its_declared_scope_and_rejects_forged_habitat():
    world = json.loads((Path(__file__).parent / "fixtures/species_parent_support/legacy_v2.json").read_text())
    assert world["species_ranges_model"]["model"] == "heuristic_species_habitat_support_v2"
    assert validate_species_habitat_support(world) == []
    world["cells"][0]["species_terrestrial_habitat_eligible"] = True
    assert any("species_terrestrial_habitat_eligible" in error for error in validate_species_habitat_support(world))


def test_absent_model_compatibility_is_not_unknown_or_partial_metadata_fallback():
    assert validate_species_habitat_support({"cells": []}) == []
    world = species(parent())
    del world["species_ranges_model"]["parent_model"]
    assert validate_species_habitat_support(world)
    world["species_ranges_model"] = {"model": "heuristic_species_parent_support_v999"}
    assert validate_species_habitat_support(world)


def test_exact_metadata_bool_number_confusion_is_rejected():
    world = species(parent())
    world["species_ranges_model"]["own_temperature_support_c"]["alpine_tundra_specialist"]["lower_exclusive"] = False
    assert validate_species_habitat_support(world)


@pytest.mark.parametrize("bad", [8, True, "8", None, [], {}])
def test_malformed_own_window_metadata_is_rejected_before_producer_mutation(bad):
    world = species(parent())
    world["species_ranges_model"]["own_temperature_support_c"]["alpine_tundra_specialist"]["upper_exclusive"] = bad
    snapshot = deepcopy(world)
    with pytest.raises(ValueError, match="exact known model metadata"):
        enrich_world_with_species_ranges(world)
    assert world == snapshot
    assert validate_species_habitat_support(world)


@pytest.mark.parametrize("bad", [None, [], "world", True, 1])
def test_malformed_world_roots_raise_a_deliberate_error(bad):
    snapshot = deepcopy(bad)
    with pytest.raises(ValueError, match="world object"):
        enrich_world_with_species_ranges(bad)
    assert bad == snapshot


@pytest.mark.parametrize("bad", [None, {}, "cells", True, 1])
def test_present_non_list_cells_are_rejected_without_mutation(bad):
    world = {"cells": bad, "summary": {"retained": 7}}
    snapshot = deepcopy(world)
    with pytest.raises(ValueError, match="cell list"):
        enrich_world_with_species_ranges(world)
    assert world == snapshot


@pytest.mark.parametrize("world", [{}, {"cells": []}, {"cells": [], "summary": {"retained": 7}}])
def test_undeclared_empty_world_remains_an_unchanged_noop(world):
    snapshot = deepcopy(world)
    assert enrich_world_with_species_ranges(world) is world
    assert world == snapshot


@pytest.mark.parametrize("field", ["species_ranges_model", "ecosystem_dynamics_model"])
@pytest.mark.parametrize("bad", [None, [], "model", True, {}, {"model": "unknown"}])
@pytest.mark.parametrize("has_cells", [False, True])
def test_explicit_malformed_models_cannot_hide_behind_empty_world_noop(field, bad, has_cells):
    world = {field: deepcopy(bad)}
    if has_cells:
        world["cells"] = []
    snapshot = deepcopy(world)
    with pytest.raises(ValueError, match="exact known"):
        enrich_world_with_species_ranges(world)
    assert world == snapshot


@pytest.mark.parametrize("field", ["species_ranges_model", "ecosystem_dynamics_model"])
@pytest.mark.parametrize("mutation", ["missing", "extra", "partial", "wrong_type"])
def test_partial_known_models_are_rejected_before_empty_world_noop(field, mutation):
    declaration = deepcopy(species(parent())[field])
    if mutation == "missing":
        declaration.pop(next(key for key in declaration if key != "model"))
    elif mutation == "extra":
        declaration["extra"] = "unsupported"
    elif mutation == "partial":
        declaration = {"model": declaration["model"]}
    elif field == "species_ranges_model":
        declaration["own_temperature_support_c"]["alpine_tundra_specialist"]["lower_exclusive"] = False
    else:
        declaration["aquatic_primary_minimum_temperature_c"] = "-16.0"
    world = {"cells": [], field: declaration}
    snapshot = deepcopy(world)
    with pytest.raises(ValueError, match="exact known"):
        enrich_world_with_species_ranges(world)
    assert world == snapshot


def test_exact_historical_declarations_can_remain_an_empty_world_noop():
    from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS
    old = json.loads((Path(__file__).parent / "fixtures/species_parent_support/legacy_v2.json").read_text())
    for species_model in (old["species_ranges_model"], SPECIES_PARENT_MODEL):
        for version in (2, 3, 4):
            ecosystem_model = _EXPECTED_MODELS[f"heuristic_ecosystem_climate_support_v{version}"]
            world = {"cells": [], "species_ranges_model": deepcopy(species_model),
                     "ecosystem_dynamics_model": deepcopy(ecosystem_model)}
            snapshot = deepcopy(world)
            assert enrich_world_with_species_ranges(world) is world
            assert world == snapshot


@pytest.mark.parametrize("bad", [None, [], "summary", True, 1])
@pytest.mark.parametrize("nonempty", [False, True])
def test_present_summary_must_be_a_mapping_before_any_mutation(bad, nonempty):
    world = species(parent()) if nonempty else {"cells": []}
    world["summary"] = bad
    snapshot = deepcopy(world)
    with pytest.raises(ValueError, match="summary object"):
        enrich_world_with_species_ranges(world)
    assert world == snapshot


@pytest.mark.parametrize("field", ["wetland_system_id", "reef_system_id", "aquifer_system_id", "basin_id"])
@pytest.mark.parametrize("bad", [None, [], {}, "1", True, False, -2, -1.0, 0.0, math.nan, math.inf])
def test_consumed_foreign_ids_fail_before_any_cell_or_record_is_rebuilt(field, bad):
    world = species(parent(cell(id=0, neighbors=[1]), cell(id=1, neighbors=[0])))
    world["cells"][1][field] = bad
    snapshot = deepcopy(world)
    with pytest.raises(ValueError, match=f"integer {field} >= -1"):
        enrich_world_with_species_ranges(world)
    assert world == snapshot


@pytest.mark.parametrize("field, record_field", [
    ("wetland_system_id", "wetland_system_ids"), ("reef_system_id", "reef_system_ids"),
    ("aquifer_system_id", "aquifer_system_ids"), ("basin_id", "river_basin_ids"),
])
@pytest.mark.parametrize("value", [None, -1, 0, 7, 2**80])
def test_absent_or_exact_valid_foreign_ids_preserve_link_semantics(field, record_field, value):
    world = parent()
    if value is not None:
        world["cells"][0][field] = value
    species(world)
    assert world["species_range_records"]
    expected = [] if value is None or value == -1 else [value]
    assert all(record[record_field] == expected for record in world["species_range_records"])
