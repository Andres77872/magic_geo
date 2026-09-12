"""Resident habitat and upstream-input gates for empirical species ranges."""

from copy import deepcopy
import math

import pytest

from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
from magic_geo.species_ranges import _guild_scores, enrich_world_with_species_ranges
from support.species_stage_worlds import species_parent_world


TERRESTRIAL = {
    "canopy_tree", "grassland_grazer", "desert_specialist",
    "alpine_tundra_specialist", "large_predator",
}


def cell(**overrides):
    return {
        "id": 0, "neighbors": [], "area_km2": 100.0,
        "is_water": False, "is_lake": False, "water_body_type": "land",
        "biome": "temperate_forest", "temperature_c": 18.0,
        "biome_confidence_index": 0.8, "fertility": 0.9,
        "growing_season_months": 12, "soil_organic_matter_fraction": 0.2,
        "precipitation_mm_y": 800.0, "seasonal_aridity_index": 0.4,
        "soil_moisture_index": 0.7, "primary_productivity_index": 0.7,
        "vegetation_biomass_index": 0.6, "species_richness_index": 0.65,
        "ecosystem_disturbance_pressure_index": 0.2,
        "forest_growth_index": 0.5, "fishery_productivity_index": 0.8,
        "wetland_extent_index": 0.4, "wetland_hydrology_index": 0.5,
        "reef_growth_index": 0.6,
        "river_channel_width_m": 90.0, "river_channel_depth_m": 4.5,
        "aquatic_primary_climate_supported": True,
        "fishery_productivity_supported": True,
        **overrides,
    }


def enrich(*cells):
    return enrich_world_with_species_ranges(species_parent_world(*cells))


def records_for(world, guild):
    return [record for record in world["species_range_records"] if record["guild_type"] == guild]


def score_vector(**overrides):
    """Prescribed valid scalar vector for coefficient checks, not a full parent."""
    result = cell(**overrides)
    for name in ("primary_productivity", "vegetation_biomass", "forest_growth",
                 "species_richness", "ecosystem_disturbance_pressure", "fishery_productivity"):
        result[name + "_supported"] = True
    return result


@pytest.mark.parametrize("selector", [
    {"is_lake": True, "water_body_type": "fresh_lake"},
    {"is_lake": True, "water_body_type": "saline_basin"},
    {"is_lake": True, "water_body_type": "land"},
    {"is_water": True, "water_body_type": "land"},
    {"water_body_type": "fresh_lake"},
    {"water_body_type": "inland_sea"},
    {"water_body_type": "continental_shelf"},
    {"water_body_type": "ocean"},
])
def test_all_physical_aquatic_selectors_exclude_five_terrestrial_guilds(selector):
    # Deliberately stale favorable forest/grass/desert/alpine inputs cannot
    # defeat the physical habitat classification, even with is_water false.
    aquatic = cell(**selector)
    world = enrich(aquatic)
    assert aquatic["species_terrestrial_habitat_eligible"] is False
    assert all(_guild_scores(aquatic)[guild] == 0.0 for guild in TERRESTRIAL)
    assert aquatic["dominant_species_guild"] not in TERRESTRIAL
    assert all(record["guild_type"] not in TERRESTRIAL for record in world["species_range_records"])


@pytest.mark.parametrize("water_body, fresh, marine, expected_fresh, expected_marine", [
    ("fresh_lake", True, False, 0.837333, 0.0),
    ("ocean", False, True, 0.0, 0.813167),
    ("continental_shelf", False, True, 0.0, 0.893167),
    # Native inland_sea denotes a separate marine connected component.
    ("inland_sea", False, True, 0.0, 0.813167),
    ("saline_basin", False, False, 0.0, 0.0),
    ("unknown", False, False, 0.0, 0.0),
])
def test_resident_fish_habitat_and_supported_formulas(water_body, fresh, marine, expected_fresh, expected_marine):
    aquatic = cell(is_lake=True, water_body_type=water_body)
    world = enrich(aquatic)
    assert aquatic["species_freshwater_habitat_eligible"] is fresh
    assert aquatic["species_marine_habitat_eligible"] is marine
    assert aquatic["species_freshwater_fish_score_supported"] is fresh
    assert aquatic["species_marine_fish_score_supported"] is marine
    # Original coefficients remain exact on a separately prescribed input
    # vector. The integrated world above uses actual ecosystem output values.
    scores = _guild_scores(score_vector(is_lake=True, water_body_type=water_body))
    assert scores["freshwater_fish"] == expected_fresh
    assert scores["marine_fish"] == expected_marine
    for guild, eligible in (("freshwater_fish", fresh), ("marine_fish", marine)):
        assert bool(records_for(world, guild)) is eligible
        for record in records_for(world, guild):
            assert record["habitat_evidence"]["water_cell_fraction"] == 1.0


def test_dry_saline_land_retains_terrestrial_formulas_without_becoming_river_habitat():
    land = cell()
    dry = cell(water_body_type="saline_basin", is_river=True)
    enrich(land)
    enrich(dry)
    for guild, value in {
        "canopy_tree": 0.8, "grassland_grazer": 0.564,
        "desert_specialist": 0.129,
        "large_predator": 0.62,
    }.items():
        assert _guild_scores(land)[guild] == _guild_scores(dry)[guild]
        assert _guild_scores(score_vector())[guild] == value
    # The old additive alpine result at 18 C had zero own-curve support.
    assert land["species_alpine_tundra_specialist_score_supported"] is False
    assert _guild_scores(land)["alpine_tundra_specialist"] == 0.0
    assert _guild_scores(score_vector(temperature_c=5.0))["alpine_tundra_specialist"] == 0.108
    assert dry["species_terrestrial_habitat_eligible"] is True
    assert dry["species_freshwater_habitat_eligible"] is False
    assert dry["species_freshwater_fishery_input_mode"] == "not_applicable"
    assert _guild_scores(dry)["freshwater_fish"] == 0.0


@pytest.mark.parametrize("water_body", ["fresh_lake", "continental_shelf"])
@pytest.mark.parametrize("overrides", [
    {"temperature_c": -18.0, "primary_productivity_index": 0.0,
     "aquatic_primary_climate_supported": False, "fishery_climate_supported": True},
    {"temperature_c": 48.0, "fishery_productivity_supported": False},
    {"temperature_c": -16.0}, {"temperature_c": 44.0},
    {"temperature_c": -100.0}, {"temperature_c": 100.0},
    {"aquatic_primary_climate_supported": False},
    {"fishery_productivity_supported": False},
    {"aquatic_primary_climate_supported": 1},
    {"fishery_productivity_supported": "true"},
    {"primary_productivity_index": -0.01}, {"primary_productivity_index": 1.01},
    {"fishery_productivity_index": -0.01}, {"fishery_productivity_index": 1.01},
])
def test_unsupported_standing_inputs_cannot_become_fish_ranges(water_body, overrides):
    aquatic = cell(is_lake=True, water_body_type=water_body,
                   **{k: v for k, v in overrides.items() if k == "temperature_c"})
    world = species_parent_world(aquatic)
    if "temperature_c" not in overrides:
        aquatic.update(overrides)
        if any(key.endswith("_supported") for key in overrides):
            before = deepcopy(world)
            with pytest.raises(ValueError, match="valid ecosystem parents"):
                enrich_world_with_species_ranges(world)
            assert world == before
            return
    enrich_world_with_species_ranges(world)
    # Habitat remains eligible; the numeric zero records unavailable modeling
    # inputs, rather than a conclusion that this habitat contains no fish.
    assert aquatic["species_freshwater_habitat_eligible"] or aquatic["species_marine_habitat_eligible"]
    assert aquatic["species_freshwater_fish_score_supported"] is False
    assert aquatic["species_marine_fish_score_supported"] is False
    assert _guild_scores(aquatic)["freshwater_fish"] == 0.0
    assert _guild_scores(aquatic)["marine_fish"] == 0.0
    assert not records_for(world, "freshwater_fish")
    assert not records_for(world, "marine_fish")


@pytest.mark.parametrize("key", [
    "primary_productivity_index", "fishery_productivity_index",
    "aquatic_primary_climate_supported", "fishery_productivity_supported",
])
def test_absent_standing_input_is_unavailable_despite_legacy_diagnostic_defaults(key):
    aquatic = cell(is_lake=True, water_body_type="fresh_lake")
    world = species_parent_world(aquatic)
    del aquatic[key]
    if key.endswith("_supported"):
        before = deepcopy(world)
        with pytest.raises(ValueError, match="valid ecosystem parents"):
            enrich_world_with_species_ranges(world)
        assert world == before
        return
    enrich_world_with_species_ranges(world)
    assert aquatic["species_freshwater_habitat_eligible"] is True
    assert aquatic["species_freshwater_fish_score_supported"] is False
    assert _guild_scores(aquatic)["freshwater_fish"] == 0.0


@pytest.mark.parametrize("water_body, guild, expected", [
    ("fresh_lake", "freshwater_fish", 0.383333),
    ("ocean", "marine_fish", 0.379167),
])
def test_supported_numeric_zero_productivity_retains_original_fish_baseline(water_body, guild, expected):
    aquatic = cell(water_body_type=water_body, primary_productivity_index=0.0,
                   fishery_productivity_index=0.0, river_channel_width_m=0.0,
                   river_channel_depth_m=0.0)
    world = species_parent_world(aquatic)
    # Explicit supported scalar-zero consumer inputs. This is a local species
    # contract vector, not a claim that the upstream aquatic formula emits zero.
    aquatic.update(primary_productivity_index=0.0, fishery_productivity_index=0.0)
    enrich_world_with_species_ranges(world)
    assert aquatic[f"species_{guild}_score_supported"] is True
    assert _guild_scores(aquatic)[guild] == expected
    # Preserve the 0.46 record threshold; a supported score need not form a range.
    assert not records_for(world, guild)


def test_river_uses_channel_proxy_without_consuming_inapplicable_fishery_diagnostic():
    worlds = []
    for fishery in (0.0, 0.8, 1.0):
        river = cell(is_river=True, fishery_productivity_index=fishery,
                     aquatic_primary_climate_supported=False, fishery_productivity_supported=False)
        world = enrich(river)
        assert river["species_terrestrial_habitat_eligible"] is True
        assert river["species_freshwater_habitat_eligible"] is True
        assert river["species_freshwater_fish_score_supported"] is True
        assert river["species_freshwater_fishery_input_mode"] == "river_inapplicable_omitted"
        direct = score_vector(is_river=True, fishery_productivity_index=fishery)
        assert _guild_scores(direct)["freshwater_fish"] == 0.517333
        record, = records_for(world, "freshwater_fish")
        assert "mean_fishery_productivity_index" not in record["habitat_evidence"]
        assert record["habitat_evidence"]["river_cell_fraction"] == 1.0
        assert record["habitat_evidence"]["water_cell_fraction"] == 0.0
        worlds.append(world)
    assert len({records_for(world, "freshwater_fish")[0]["mean_habitat_suitability_index"] for world in worlds}) == 1


@pytest.mark.parametrize("primary", [None, -0.1, 1.1])
def test_river_still_requires_available_primary_input(primary):
    river = cell(is_river=True)
    world = species_parent_world(river)
    if primary is None:
        del river["primary_productivity_index"]
    else:
        river["primary_productivity_index"] = primary
    enrich_world_with_species_ranges(world)
    assert river["species_freshwater_habitat_eligible"] is True
    assert river["species_freshwater_fish_score_supported"] is False
    assert not records_for(world, "freshwater_fish")


@pytest.mark.parametrize("habitat, guild, lower, upper", [
    ({"water_body_type": "fresh_lake"}, "freshwater_fish", -10.0, 38.0),
    ({"is_river": True}, "freshwater_fish", -10.0, 38.0),
    ({"water_body_type": "continental_shelf"}, "marine_fish", -11.0, 37.0),
])
def test_fish_annual_air_proxy_support_uses_existing_open_thermal_window(habitat, guild, lower, upper):
    for temperature in (-100.0, lower, upper, 100.0):
        c = cell(temperature_c=temperature, **habitat)
        world = enrich(c)
        assert c[f"species_{guild}_score_supported"] is False
        assert _guild_scores(c)[guild] == 0.0
        assert not records_for(world, guild)
    # A supported point arbitrarily close to a boundary remains supported;
    # no invented thermal floor removes the original additive coefficients.
    for temperature in (math.nextafter(lower, upper), math.nextafter(upper, lower)):
        c = cell(temperature_c=temperature, **habitat)
        enrich(c)
        assert c[f"species_{guild}_score_supported"] is True
        assert _guild_scores(c)[guild] > 0.0


@pytest.mark.parametrize("guild,favorable", [
    ("canopy_tree", {"biome": "temperate_forest", "precipitation_mm_y": 1600.0}),
    ("grassland_grazer", {"biome": "temperate_grassland", "precipitation_mm_y": 1600.0}),
    ("desert_specialist", {"biome": "hot_desert", "precipitation_mm_y": 0.0,
                           "seasonal_aridity_index": 0.9, "soil_moisture_index": 0.0}),
    ("alpine_tundra_specialist", {"biome": "tundra", "temperature_c": -5.0,
                                 "elevation_m": 5000.0, "permafrost_extent_index": 1.0}),
    ("large_predator", {"biome": "temperate_forest", "precipitation_mm_y": 1600.0}),
])
def test_lake_cannot_join_terrestrial_components_and_range_links_rebuild_after_inundation(guild, favorable):
    # Each guild uses its own current supported habitat, instead of fabricated
    # all-one parent outputs making all five cross the threshold simultaneously.
    world = enrich(*[cell(id=index, neighbors=neighbors, **favorable)
                     for index, neighbors in enumerate(([1], [0, 2], [1]))])
    assert [record["cell_ids"] for record in records_for(world, guild)] == [[0, 1, 2]]
    world["cells"][1].update(is_lake=True, water_body_type="fresh_lake")
    enrich_world_with_ecosystem_dynamics(world)
    enrich_world_with_species_ranges(world)
    assert [record["cell_ids"] for record in records_for(world, guild)] == [[0], [2]]
    for c in world["cells"]:
        assert c["species_range_record_ids"] == [r["id"] for r in world["species_range_records"] if c["id"] in r["cell_ids"]]
    snapshot = deepcopy(world)
    enrich_world_with_species_ranges(world)
    assert world == snapshot
    world["cells"][0]["neighbors"].append(2)
    world["cells"][2]["neighbors"].append(0)
    enrich_world_with_species_ranges(world)
    assert [record["cell_ids"] for record in records_for(world, guild)] == [[0, 2]]


def test_marine_component_cannot_connect_two_freshwater_ranges():
    world = enrich(
        cell(id=0, neighbors=[1], water_body_type="fresh_lake"),
        cell(id=1, neighbors=[0, 2], water_body_type="inland_sea"),
        cell(id=2, neighbors=[1], water_body_type="fresh_lake"),
    )
    assert [r["cell_ids"] for r in records_for(world, "freshwater_fish")] == [[0], [2]]
    assert [r["cell_ids"] for r in records_for(world, "marine_fish")] == [[1]]


@pytest.mark.parametrize("water_body, amphibian", [
    ("land", 0.411), ("fresh_lake", 0.465), ("inland_sea", 0.465),
])
def test_supported_wetland_reef_and_mobile_score_vectors_retain_prior_coefficients(water_body, amphibian):
    scores = _guild_scores(score_vector(water_body_type=water_body))
    assert scores["wetland_amphibian"] == amphibian
    assert scores["reef_builder"] == 0.444
    assert scores["mangrove_coastal_bird"] == 0.26


def test_historical_ecosystem_dependency_chain_uses_lake_habitat_and_support():
    aquatic = cell(is_lake=True, water_body_type="fresh_lake", biome="lake",
                   runoff_mm_y=900.0, soil_moisture_index=1.0,
                   seasonal_aridity_index=0.45)
    world = species_parent_world(aquatic)
    assert world["ecosystem_dynamics_model"]["model"] == "heuristic_ecosystem_climate_support_v4"
    enrich_world_with_species_ranges(world)
    assert aquatic["fishery_productivity_supported"] is True
    assert aquatic["species_freshwater_fish_score_supported"] is True
    assert records_for(world, "freshwater_fish")
    assert not records_for(world, "marine_fish")
    assert all(not records_for(world, guild) for guild in TERRESTRIAL)
    assert records_for(world, "freshwater_fish")[0]["habitat_evidence"]["water_cell_fraction"] == 1.0


@pytest.mark.parametrize("key", ["temperature_c", "primary_productivity_index", "fishery_productivity_index"])
@pytest.mark.parametrize("invalid", [None, True, "18", float("nan"), float("inf"), -float("inf"), 10 ** 400])
def test_invalid_later_dependency_rejects_before_any_world_mutation(key, invalid):
    world = enrich(cell(), cell(id=1))
    world["cells"][1][key] = invalid
    before = deepcopy(world)
    with pytest.raises(ValueError, match=f"valid ecosystem parents|finite numeric.*{key}"):
        enrich_world_with_species_ranges(world)
    assert world == before


def test_missing_annual_temperature_rejects_before_any_world_mutation():
    world = enrich(cell(), cell(id=1))
    bad = world["cells"][1]
    del bad["temperature_c"]
    before = deepcopy(world)
    with pytest.raises(ValueError, match="valid ecosystem parents"):
        enrich_world_with_species_ranges(world)
    assert world == before


def test_version_declares_scope_input_availability_and_river_diagnostic_semantics():
    model = enrich(cell())["species_ranges_model"]
    assert model["model"] == "heuristic_species_parent_support_v3"
    assert set(model["terrestrial_guilds"]) == TERRESTRIAL
    assert model["marine_water_body_types"] == ["continental_shelf", "inland_sea", "ocean"]
    assert model["freshwater_water_body_types"] == ["fresh_lake"]
    assert model["unsupported_estimate_policy"] == "numeric_zero_with_false_support_flag_not_species_absence"
    assert model["river_fishery_input_policy"] == "omit_standing_fishery_term_regardless_numeric_value_require_supported_primary"
    assert model["record_evidence_policy"] == "fishery_mean_only_when_all_members_consume_supported_fishery_forest_mean_only_for_canopy_tree"
    assert model["parent_input_policy"] == "exact_true_availability_and_finite_numeric_unit_interval_supported_zero_valid"
    assert model["source_input_policy"] == "finite_numeric_annual_and_present_numeric_descriptors_required_before_mutation_absent_biological_inputs_unavailable"
    assert model["scope"] == "empirical_resident_habitat_scores_not_population_survival_migration_or_global_habitability"
