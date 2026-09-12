"""Real complete public worlds and rejected missing/mixed child certificates."""
from copy import deepcopy
import json

import pytest
from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.geo_validation import validate_geo_world
from support.prescribed_natural_public_worlds import (
    OWNERSHIP, archived_world, current_world_readonly, natural_owned,
)


MODELS = {
    'ecosystem': ('ecosystem_dynamics_model', 'model', 'heuristic_ecosystem_climate_support_v5'),
    'species': ('species_ranges_model', 'model', 'heuristic_species_parent_support_v4'),
    'fire': ('wildfire_disturbance_model', 'model', 'heuristic_wildfire_native_seasonal_prescribed_natural_parent_availability_v7'),
    'resource': ('resource_deposit_model', 'model_type', 'causal_geologic_resource_deposit_diagnostics_v4'),
    'commodity': ('commodity_occurrence_model', 'model_type', 'causal_resource_commodity_occurrences_with_parent_support_v2'),
    'worldbuilding': ('worldbuilding_realism_model', 'model_type', 'causal_upstream_evidence_worldbuilding_realism_checks_v3'),
}


def run_cli(world, tmp_path):
    path = tmp_path / 'world.json'
    path.write_text(json.dumps(world, allow_nan=False))
    return CliRunner().invoke(app, ['validate', '--world', str(path)])


def assert_public_rejected(world, tmp_path):
    result = run_cli(world, tmp_path)
    assert result.exit_code == 1, (result.output, repr(result.exception))
    assert isinstance(result.exception, SystemExit), repr(result.exception)
    assert 'FAIL' in result.output


def test_actual_complete_full_chain_passes_public_cli(tmp_path):
    world = current_world_readonly()
    for key, field, expected in MODELS.values():
        assert world[key][field] == expected
    result = run_cli(world, tmp_path)
    assert result.exit_code == 0, (result.output, repr(result.exception))


def test_actual_geo_public_report_and_natural_full_geo_invariance():
    world = current_world_readonly('geo')
    assert natural_owned(world) == natural_owned(current_world_readonly())
    report = validate_geo_world(world, profile='generic')
    assert report['passed'], [c for c in report['checks'] if not c['passed']]
    assert 'worldbuilding_realism_model' not in world


def test_actual_geo_world_passes_its_public_cli(tmp_path):
    path = tmp_path / 'geo.json'
    path.write_text(json.dumps(current_world_readonly('geo'), allow_nan=False))
    result = CliRunner().invoke(app, ['validate-geo', '--world', str(path)])
    assert result.exit_code == 0, (result.output, repr(result.exception))


def test_actual_historical_complete_full_world_still_passes_cli(tmp_path):
    result = run_cli(archived_world(), tmp_path)
    assert result.exit_code == 0, (result.output, repr(result.exception))


@pytest.mark.parametrize('stage', MODELS)
@pytest.mark.parametrize('mutation', ('missing', 'partial', 'null', 'list', 'unknown', 'historical'))
def test_public_chain_rejects_absent_partial_or_cross_family_models(stage, mutation, tmp_path):
    world = deepcopy(current_world_readonly())
    key, field, _ = MODELS[stage]
    if mutation == 'missing':
        del world[key]
    elif mutation == 'partial':
        world[key] = {field: world[key][field]}
    elif mutation == 'null':
        world[key] = None
    elif mutation == 'list':
        world[key] = []
    elif mutation == 'unknown':
        world[key][field] = 'unrecognized_future_model'
    else:
        world[key] = deepcopy(archived_world()[key])
    assert_public_rejected(world, tmp_path)


@pytest.mark.parametrize('stage', ('species', 'fire', 'resource', 'commodity', 'worldbuilding'))
def test_public_chain_cannot_downgrade_by_deleting_all_owned_publication(stage, tmp_path):
    world = deepcopy(current_world_readonly())
    owned = OWNERSHIP[stage]
    for cell in world['cells']:
        for key in owned['cell_fields']:
            del cell[key]
    for key in owned['summary_fields']:
        del world['summary'][key]
    for key in owned['top_level']:
        del world[key]
    assert_public_rejected(world, tmp_path)


@pytest.mark.parametrize('key', (
    'wetland_systems', 'reef_systems', 'aquifer_systems',
    'sedimentary_resource_systems', 'settlements', 'routes', 'political_regions', 'borders',
))
def test_missing_previous_stage_collection_is_rejected_publicly(key, tmp_path):
    world = deepcopy(current_world_readonly())
    del world[key]
    assert_public_rejected(world, tmp_path)


@pytest.mark.parametrize('stage', ('ecosystem', 'species', 'fire'))
def test_old_natural_activity_values_cannot_be_relabelled_with_new_metadata(stage, tmp_path):
    world = deepcopy(current_world_readonly())
    old = archived_world()
    owned = OWNERSHIP[stage]
    for cell, previous in zip(world['cells'], old['cells']):
        for key in owned['cell_fields']:
            cell[key] = deepcopy(previous[key])
    for key in owned['summary_fields']:
        world['summary'][key] = deepcopy(old['summary'][key])
    model_key = MODELS[stage][0]
    for key in owned['top_level']:
        if key != model_key:
            world[key] = deepcopy(old[key])
    assert_public_rejected(world, tmp_path)


@pytest.mark.parametrize('field', ('volcanic_potential_index', 'sedimentary_resource_system_id', 'petroleum_potential_index'))
def test_public_cli_rejects_missing_commodity_source_evidence(field, tmp_path):
    world = deepcopy(current_world_readonly())
    record = next(r for r in world['commodity_occurrences'] if field in r['formation_evidence'])
    del record['formation_evidence'][field]
    assert_public_rejected(world, tmp_path)


@pytest.mark.parametrize('source_id', (-1, 999999, True))
def test_public_cli_rejects_forged_commodity_source_id(source_id, tmp_path):
    world = deepcopy(current_world_readonly())
    record = next(r for r in world['commodity_occurrences'] if 'sedimentary_resource_system_id' in r['formation_evidence'])
    record['formation_evidence']['sedimentary_resource_system_id'] = source_id
    assert_public_rejected(world, tmp_path)
