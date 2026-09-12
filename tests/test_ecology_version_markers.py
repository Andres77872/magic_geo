"""New support fields cannot silently alter the meaning of historical output."""
from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from magic_geo.aquatic_climate_validation import validate_aquatic_climate_support
from magic_geo.species_habitat_validation import validate_species_habitat_support


PARENT_FLAGS = (
    "terrestrial_primary_climate_supported", "primary_productivity_supported", "vegetation_biomass_supported",
    "forest_growth_supported", "vegetation_succession_supported", "species_richness_supported",
    "ecosystem_wildfire_spread_risk_supported", "ecosystem_disturbance_pressure_supported", "vegetation_recovery_supported",
)
SPECIES_FLAGS = tuple(f"species_{guild}_score_supported" for guild in (
    "canopy_tree", "grassland_grazer", "desert_specialist", "alpine_tundra_specialist", "large_predator",
    "reef_builder", "wetland_amphibian", "mangrove_coastal_bird")) + (
    "species_composition_confidence_supported", "species_endemism_supported", "species_record_descriptors_supported",
)
CASES = (
    [("parent", "cell", k) for k in PARENT_FLAGS]
    + [("parent", "summary", k + "_cell_count") for k in PARENT_FLAGS]
    + [("species", "cell", k) for k in (*SPECIES_FLAGS, "species_applicable_guild_count",
        "species_supported_guild_count", "species_composition_status", "species_guild_scores")]
    + [("species", "summary", k) for k in ("species_score_supported_cell_counts", "species_composition_status_counts",
        "species_composition_confidence_supported_cell_count", "species_endemism_supported_cell_count",
        "species_record_descriptors_supported_cell_count")]
)


@pytest.fixture(scope="module")
def historical():
    path = Path(__file__).parent / "fixtures/cli_ecology_parent_availability/warm.json.gz"
    world = json.loads(gzip.decompress(path.read_bytes()))
    assert validate_aquatic_climate_support(world) == []
    assert validate_species_habitat_support(world) == []
    return world


@pytest.mark.parametrize("domain,location,field", CASES)
@pytest.mark.parametrize("declared", [True, False])
def test_every_new_support_marker_requires_its_own_model(historical, domain, location, field, declared):
    world = deepcopy(historical)
    declaration = "ecosystem_dynamics_model" if domain == "parent" else "species_ranges_model"
    helper = validate_aquatic_climate_support if domain == "parent" else validate_species_habitat_support
    if not declared:
        world.pop(declaration)
        assert helper(world) == []
    target = world["cells"][0] if location == "cell" else world["summary"]
    target[field] = False if location == "cell" else 0
    assert helper(world), (domain, location, field)


@pytest.mark.parametrize("value", [None, [], 12, "world"])
def test_parent_helper_returns_diagnostic_for_malformed_root(value):
    assert validate_aquatic_climate_support(value)
