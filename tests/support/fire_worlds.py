"""Actual ecosystem-v4 parents for compact wildfire equation/graph controls.

These are bounded scalar/graph fixtures, not native climate certificates. Full
CLI tests instead use the hash-checked complete worlds in ecology_worlds.
"""
from copy import deepcopy
from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS, validate_aquatic_climate_support
from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics


def prepare_fire_parents(world):
    """Rebuild genuine parent outputs from source descriptors, retaining cells."""
    for cell in world['cells']:
        for key, value in {
            'fertility':1.0, 'soil_moisture_index':1.0,
            'soil_organic_matter_fraction':0.2, 'fire_frequency_index':1.0,
        }.items():
            cell.setdefault(key, value)
    world.setdefault("ecosystem_dynamics_model", deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"]))
    enrich_world_with_ecosystem_dynamics(world)
    assert world['ecosystem_dynamics_model']['model']=='heuristic_ecosystem_climate_support_v4'
    assert validate_aquatic_climate_support(world)==[]
    return world


def fire_input_world(cells):
    return prepare_fire_parents({'cells':cells})
