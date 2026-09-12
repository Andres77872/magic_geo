"""Full public contracts retain real native worlds and independent water replay."""

from copy import deepcopy

import pytest
from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.human_water_validation_dispatch import validate_public_human_water_transport
from magic_geo.io import write_json
from magic_geo.natural_water_validation_dispatch import validate_public_natural_water_chain
from support.ecology_worlds import current_ecology_world_readonly
from support.natural_human_worlds import current_natural_human_world_readonly


@pytest.fixture(scope="module")
def natural_world():
    return current_natural_human_world_readonly()


@pytest.mark.parametrize("natural", [False, True])
def test_complete_current_and_historical_water_contracts_pass_without_mutation(natural_world, natural):
    world = natural_world if natural else current_ecology_world_readonly()
    before = deepcopy(world)
    assert validate_public_natural_water_chain(world) == (natural, [])
    assert validate_public_human_water_transport(world, natural_water=natural) == (natural, [])
    assert world == before


@pytest.mark.parametrize("key", ["navigability_model", "port_site_model", "route_corridor_model"])
@pytest.mark.parametrize("change", ["missing", "summary-missing", "unknown", "forged-parent", "legacy"])
def test_each_published_human_stage_must_match_its_actual_parents(natural_world, key, change):
    world = deepcopy(natural_world)
    if change == "missing":
        del world[key]
        del world["summary"][key]
    elif change == "summary-missing":
        del world["summary"][key]
    elif change == "unknown":
        world[key]["model_type"] = "unknown"
    elif change == "legacy":
        world[key] = deepcopy(current_ecology_world_readonly()[key])
        world["summary"][key] = world[key]["model_type"]
    else:
        source = next(field for field in world[key] if field.startswith("source_"))
        world[key][source] = "unknown"
    assert validate_public_human_water_transport(world, natural_water=True)[1]


@pytest.mark.parametrize("family,field", [
    ("navigable_waterways", "watershed_ids"),
    ("port_sites", "navigable_waterway_ids"),
    ("route_corridors", "cell_ids"),
])
def test_linked_record_corruption_is_caught_at_public_preflight(natural_world, family, field, tmp_path):
    world = deepcopy(natural_world)
    assert world[family]
    world[family][0][field] = [999999]
    errors = validate_public_human_water_transport(world, natural_water=True)[1]
    assert errors and "human water transport" in errors[0]
    path = tmp_path / "world.json"
    write_json(path, world)
    result = CliRunner().invoke(app, ["validate", "--world", str(path)])
    assert result.exit_code == 1, (result.output, repr(result.exception))
    assert "FAIL human water transport" in result.output
    assert not isinstance(result.exception, (TypeError, ValueError, KeyError))


@pytest.mark.parametrize("natural", [False, True])
def test_full_cli_accepts_complete_ordered_worlds(natural_world, natural, tmp_path):
    world = natural_world if natural else current_ecology_world_readonly()
    path = tmp_path / "world.json"
    write_json(path, world)
    result = CliRunner().invoke(app, ["validate", "--world", str(path)])
    assert result.exit_code == 0, (result.output, repr(result.exception))
