"""Public routing and failures using retained complete source meshes."""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

import pytest
from typer.testing import CliRunner

from magic_geo.aquifer_resources import enrich_world_with_aquifer_resources
from magic_geo.groundwater_flow import enrich_world_with_groundwater_flow
from magic_geo.groundwater_validation_dispatch import validate_public_natural_groundwater
from magic_geo.natural_groundwater_validation import validate_natural_groundwater_flow
from magic_geo.geo_validation import validate_geo_world
from magic_geo.cli import app
from magic_geo.io import write_json
from support.ecology_worlds import current_ecology_world_readonly
from support.natural_water_worlds import upgrade_natural_water


DATA = Path(__file__).parent / "data/natural_groundwater"


def _upgrade(world):
    for key in ("aquifer_resource_model", "groundwater_flow_model"):
        del world[key]
        del world["summary"][key]
    enrich_world_with_aquifer_resources(world)
    enrich_world_with_groundwater_flow(world)
    return world


@pytest.fixture(scope="module")
def stage_world():
    manifest = json.loads((DATA / "manifest.json").read_text())
    raw = (DATA / "full_world.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["fixtures"]["full_world"]["projection_sha256"]
    return _upgrade(json.loads(raw))


def test_retained_current_stage_passes_without_rewriting_any_output(stage_world):
    world = deepcopy(stage_world)
    original = deepcopy(world)
    assert validate_public_natural_groundwater(world) == (True, [])
    assert world == original


@pytest.mark.parametrize("value", [None, True, "0", math.inf, math.nan, 1 << 20000],
                         ids=["null", "boolean", "string", "infinity", "nan", "huge-integer"])
@pytest.mark.parametrize("field", ["aquifer_natural_limitation_index", "groundwater_discharge_km3_y"])
def test_non_numeric_natural_output_is_a_diagnostic(stage_world, field, value):
    world = deepcopy(stage_world)
    world["cells"][1][field] = value
    natural, errors = validate_public_natural_groundwater(world)
    assert natural and errors
    assert field in " ".join(errors)


@pytest.mark.parametrize("mutation", [
    lambda w: w.pop("aquifer_resource_model"),
    lambda w: w.pop("groundwater_flow_model"),
    lambda w: w["summary"].pop("aquifer_resource_model"),
    lambda w: w["groundwater_flow_model"].update(model_type="unknown"),
    lambda w: w["aquifer_resource_model"].update(model_type="finite_recharge_causal_aquifer_resources_v1"),
    lambda w: w["cells"][1].update(aquifer_extraction_risk_index=0),
    lambda w: w["summary"].update(groundwater_stressed_cell_count=0),
])
def test_partial_mixed_and_forged_contracts_fail(stage_world, mutation):
    world = deepcopy(stage_world)
    mutation(world)
    assert validate_public_natural_groundwater(world)[1]


@pytest.mark.parametrize("value", [None, False, math.nan, "unknown", "missing", "plus-one"])
def test_final_infiltration_mirror_is_required_only_at_public_output(stage_world, value):
    world = deepcopy(stage_world)
    if value == "missing":
        del world["summary"]["total_infiltration_km3_y"]
    elif value == "plus-one":
        world["summary"]["total_infiltration_km3_y"] += 1
    else:
        world["summary"]["total_infiltration_km3_y"] = value
    # This later summary is intentionally not a producer prerequisite.
    assert validate_natural_groundwater_flow(world) == []
    natural, errors = validate_public_natural_groundwater(world)
    assert natural and errors and "infiltration" in " ".join(errors)


@pytest.mark.parametrize("field", ["aquifer_natural_limitation_index", "groundwater_discharge_km3_y"])
def test_complete_world_public_boundaries_reject_malformed_natural_values(field, tmp_path):
    # Retain the actual native certificate. Only this scoped natural chain is
    # upgraded here; acceptance of its downstream migration is tested separately.
    world = upgrade_natural_water(deepcopy(current_ecology_world_readonly()))
    assert validate_public_natural_groundwater(world) == (True, [])
    world["cells"][1][field] = "unavailable"
    path = tmp_path / "world.json"
    write_json(path, world)
    result = CliRunner().invoke(app, ["validate", "--world", str(path)])
    assert result.exit_code == 1, (result.output, repr(result.exception))
    assert field in result.output and "natural groundwater" in result.output
    assert not isinstance(result.exception, (ValueError, TypeError, KeyError))
    report = validate_geo_world(world)
    check = next(item for item in report["checks"] if item["name"] == "declared_groundwater_contract")
    assert not report["passed"] and not check["passed"]
    assert field in " ".join(check["observed"]["errors"])
