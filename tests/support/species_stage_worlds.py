"""Actual ecosystem-v4 stage inputs for species tests; no physical-world claim."""
from copy import deepcopy
from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS, validate_aquatic_climate_support
from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics


def species_parent_world(*cells):
    world = {"cells": list(cells), "summary": {},
             "ecosystem_dynamics_model": deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])}
    enrich_world_with_ecosystem_dynamics(world)
    assert validate_aquatic_climate_support(world) == []
    assert world["ecosystem_dynamics_model"]["model"] == "heuristic_ecosystem_climate_support_v4"
    return world
