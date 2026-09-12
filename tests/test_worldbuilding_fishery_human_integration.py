"""Full human/public CLI replay on a retained complete world; no generation."""
from copy import deepcopy
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest
from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.human_geography_validation import validate_human_geography_replay
from magic_geo.io import write_json
from magic_geo.worldbuilding_realism import enrich_world_with_worldbuilding_realism
from magic_geo.worldbuilding_fishery_validation import validate_worldbuilding_fishery_context

DATA = Path(__file__).parent / 'data'
WORLD_ERROR = 'worldbuilding realism model or causal replay invalid'


@pytest.fixture(scope='module')
def complete_versions():
    metadata = json.loads((DATA / 'worldbuilding_full_provenance.json').read_text())
    raw = (DATA / 'worldbuilding_full_world.json.gz').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == metadata['compressed_sha256']
    decoded = gzip.decompress(raw)
    assert hashlib.sha256(decoded).hexdigest() == metadata['uncompressed_sha256']
    legacy = json.loads(decoded)
    assert len(legacy['cells']) == metadata['cell_count'] == 128
    assert legacy.get('generation_scope', 'full_world') == 'full_world'
    assert len(legacy['settlements']) == 4 and len(legacy['routes']) == 5
    assert legacy['worldbuilding_realism_model']['model_type'].endswith('_v1')
    current = deepcopy(legacy)
    # Deliberate own-stage migration. No upstream records/physics are recomputed.
    del current['worldbuilding_realism_model']
    del current['summary']['worldbuilding_realism_model']
    enrich_world_with_worldbuilding_realism(current)
    assert current['worldbuilding_realism_model']['model_type'].endswith('_v2')
    assert current['worldbuilding_realism_checks'][:4] == legacy['worldbuilding_realism_checks'][:4]
    owned = {'summary', 'worldbuilding_realism_model', 'worldbuilding_realism_checks'}
    assert all(current[key] == value for key, value in legacy.items() if key not in owned)
    return {'v1': legacy, 'v2': current}


@pytest.mark.parametrize('version', ['v1', 'v2'])
def test_complete_human_controls_and_intentional_version_preservation(complete_versions, version):
    world = deepcopy(complete_versions[version])
    before = deepcopy(world)
    assert validate_human_geography_replay(world) == []
    assert world == before
    enrich_world_with_worldbuilding_realism(world)
    assert world == before


@pytest.mark.parametrize('index', range(4))
def test_each_human_check_is_independently_replayed_beyond_fishery_helper(complete_versions, index):
    world = deepcopy(complete_versions['v2'])
    world['worldbuilding_realism_checks'][index]['question'] += ' tampered'
    # The bounded fishery helper deliberately does not claim these four checks.
    assert validate_worldbuilding_fishery_context(world) == []
    before = deepcopy(world)
    assert WORLD_ERROR in validate_human_geography_replay(world)
    assert world == before


@pytest.mark.parametrize('key', [
    'large_settlement_water_access_index', 'route_barrier_avoidance_index',
    'political_region_connectivity_index', 'natural_border_alignment_index',
])
def test_each_human_summary_is_independently_replayed(complete_versions, key):
    world = deepcopy(complete_versions['v2'])
    world['summary'][key] = .123456
    assert validate_worldbuilding_fishery_context(world) == []
    assert WORLD_ERROR in validate_human_geography_replay(world)


def test_new_first_four_contract_does_not_accept_boolean_as_numeric_id(complete_versions):
    world = deepcopy(complete_versions['v2'])
    world['worldbuilding_realism_checks'][0]['id'] = False
    assert validate_worldbuilding_fishery_context(world) == []
    assert WORLD_ERROR in validate_human_geography_replay(world)


def test_actual_route_cost_input_replays_without_trusting_retained_check(complete_versions):
    world = deepcopy(complete_versions['v2'])
    world['routes'][0]['cost'] = 1e10
    assert validate_worldbuilding_fishery_context(world) == []
    assert WORLD_ERROR in validate_human_geography_replay(world)


@pytest.mark.parametrize('case', [
    'own_unknown','own_missing','own_policy_missing','own_mixed_summary','own_boolean',
    'ecosystem_unknown','ecosystem_partial','resource_parent_missing','resource_parent_unknown',
    'deposit_missing','deposit_equation','parent_forged','source_count','fifth_metric',
])
def test_public_human_wrapper_refuses_malformed_v2_or_parent_contracts(complete_versions, case):
    world = deepcopy(complete_versions['v2'])
    if case == 'own_unknown': world['worldbuilding_realism_model']['model_type'] = 'future'
    elif case == 'own_missing': del world['worldbuilding_realism_model']
    elif case == 'own_policy_missing': del world['worldbuilding_realism_model']['fishery_support_policy']
    elif case == 'own_mixed_summary': world['summary']['worldbuilding_realism_model'] = complete_versions['v1']['summary']['worldbuilding_realism_model']
    elif case == 'own_boolean': world['worldbuilding_realism_model']['deterministic'] = 1
    elif case == 'ecosystem_unknown': world['ecosystem_dynamics_model']['model'] = 'future'
    elif case == 'ecosystem_partial': del world['ecosystem_dynamics_model']['aquatic_ecology_policy']
    elif case == 'resource_parent_missing': del world['resource_deposit_model']
    elif case == 'resource_parent_unknown': world['resource_deposit_model']['model_type'] = 'future'
    elif case == 'deposit_missing': world['resource_deposits'].pop()
    elif case == 'deposit_equation':
        record = next(r for r in world['resource_deposits'] if r['resource'] == 'coastal_fisheries')
        record['reserve_potential_index'] = .123456
    elif case == 'parent_forged':
        cell = next(c for c in world['cells'] if c['resource'] == 'coastal_fisheries')
        cell['fishery_productivity_supported'] = False
    elif case == 'source_count': world['worldbuilding_realism_checks'][4]['evidence']['fishery_resource_proxy_supported_cell_count'] = 0
    elif case == 'fifth_metric': world['worldbuilding_realism_checks'][4]['metric'] = 'fraction_resource_deposits_with_resource_specific_geologic_support'
    before = deepcopy(world)
    failures = validate_human_geography_replay(world)
    assert WORLD_ERROR in failures
    assert len(failures) <= 3
    assert world == before


@pytest.mark.parametrize('case', ['temperature','deposit_record','settlement_score','region_members','route_cost'])
def test_public_human_wrapper_bounds_malformed_conversion_failures(complete_versions, case):
    world = deepcopy(complete_versions['v2'])
    if case == 'temperature': world['cells'][0]['temperature_c'] = None
    elif case == 'deposit_record': world['resource_deposits'][0] = None
    elif case == 'settlement_score': world['settlements'][0]['score'] = 'not a number'
    elif case == 'region_members': world['political_regions'][0]['settlement_ids'] = None
    elif case == 'route_cost': world['routes'][0]['cost'] = math.inf
    before = deepcopy(world)
    failures = validate_human_geography_replay(world)
    assert failures and len(failures) <= 3
    assert WORLD_ERROR in failures
    assert world == before


def test_v2_parent_audit_runs_once_per_full_human_replay(complete_versions, monkeypatch):
    import magic_geo.worldbuilding_fishery_validation as helper
    original = helper.audit_biological_resource_deposits
    calls = []
    def counted(world):
        calls.append(1)
        return original(world)
    monkeypatch.setattr(helper, 'audit_biological_resource_deposits', counted)
    assert validate_human_geography_replay(complete_versions['v2']) == []
    assert len(calls) == 1


def invoke(world, tmp_path):
    path = tmp_path / 'world.json'
    write_json(path, world)
    result = CliRunner().invoke(app, ['validate', '--world', str(path)])
    assert result.exception is None or isinstance(result.exception, SystemExit), repr(result.exception)
    return result


@pytest.mark.parametrize('version', ['v1', 'v2'])
def test_actual_complete_versions_pass_full_public_cli(complete_versions, version, tmp_path):
    result = invoke(complete_versions[version], tmp_path)
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize('target', ['first_human_check','resource_check','own_policy','own_summary'])
def test_actual_complete_public_cli_reports_worldbuilding_tampering(complete_versions, target, tmp_path):
    world = deepcopy(complete_versions['v2'])
    if target == 'first_human_check': world['worldbuilding_realism_checks'][0]['question'] += ' tampered'
    elif target == 'resource_check': world['worldbuilding_realism_checks'][4]['evidence']['source_context_supported_resource_deposit_count'] = 0
    elif target == 'own_policy': world['worldbuilding_realism_model']['fishery_water_body_types'].remove('fresh_lake')
    elif target == 'own_summary': world['summary']['worldbuilding_realism_model'] = 'unknown'
    result = invoke(world, tmp_path)
    assert result.exit_code == 1, result.output
    assert 'FAIL ' + WORLD_ERROR in result.output.splitlines()


def test_frozen_original_v1_mixed_material_and_society_record_replay():
    from magic_geo.human_geography_validation import _worldbuilding_replay_valid
    world = json.loads((DATA / 'worldbuilding_fishery_legacy.json').read_text())['expected']
    before = deepcopy(world)
    assert _worldbuilding_replay_valid(world)
    assert world == before
