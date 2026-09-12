"""Public natural water dependency checks on complete retained native worlds."""

from copy import deepcopy

import pytest

from magic_geo.geo_layer_contracts import evaluate_geo_layer_contracts
from magic_geo.natural_water_validation_dispatch import validate_public_natural_water_chain
from support.ecology_worlds import current_ecology_world_readonly
from support.natural_water_worlds import upgrade_natural_water


@pytest.fixture(scope="module")
def natural_world():
    return upgrade_natural_water(deepcopy(current_ecology_world_readonly()))


def test_retained_full_natural_chain_passes_without_rewriting_parents(natural_world):
    before = deepcopy(natural_world)
    assert validate_public_natural_water_chain(natural_world) == (True, [])
    assert natural_world == before


@pytest.mark.parametrize("key", ["river_channel_morphology_model", "river_hydraulics_model", "karst_diagnostics_model"])
@pytest.mark.parametrize("change", ["missing", "summary-missing", "unknown", "forged-parent"])
def test_complete_output_requires_each_exact_downstream_declaration(natural_world, key, change):
    world = deepcopy(natural_world)
    assert validate_public_natural_water_chain(world) == (True, [])
    if change == "missing":
        del world[key]
        del world["summary"][key]
    elif change == "summary-missing":
        del world["summary"][key]
    elif change == "unknown":
        world[key]["model_type"] = "unknown"
    else:
        source = next(field for field in world[key] if field.startswith("source_"))
        world[key][source] = "unknown"
    assert validate_public_natural_water_chain(world)[1]


@pytest.mark.parametrize("field", ["river_channel_depth_m", "flow_velocity_m_s", "karst_potential_index"])
@pytest.mark.parametrize("value", [None, False, "unknown"])
def test_current_numeric_outputs_cannot_evade_independent_replay(natural_world, field, value):
    world = deepcopy(natural_world)
    world["cells"][0][field] = value
    assert validate_public_natural_water_chain(world)[1]


@pytest.mark.parametrize("key", ["aquifer_resource_model", "river_channel_morphology_model", "river_hydraulics_model", "karst_diagnostics_model"])
def test_hydrology_layer_lists_required_natural_declarations(natural_world, key):
    world = deepcopy(natural_world)
    if key == "aquifer_resource_model":
        # The known v2 chain requires the aquifer declaration alongside its
        # downstream declarations in the reported layer contract.
        layer = next(item for item in evaluate_geo_layer_contracts(world, [])["layers"] if item["id"] == "hydrology")
        assert key in layer["required_outputs"]
        return
    del world[key]
    layer = next(item for item in evaluate_geo_layer_contracts(world, [])["layers"] if item["id"] == "hydrology")
    assert key in layer["missing_or_invalid_outputs"]
