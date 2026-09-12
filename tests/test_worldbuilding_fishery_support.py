"""Historical E4/WB2 stage tests and retained geo evidence; no native generation."""
from copy import deepcopy
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS
from magic_geo.biological_resource_validation import validate_biological_resources
from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
from magic_geo.resource_dynamics import enrich_world_with_resource_deposits
from magic_geo.worldbuilding_realism import (
    MARINE_WATER_TYPES,
    _is_coastal_land,
    enrich_world_with_worldbuilding_realism,
)
from magic_geo.worldbuilding_fishery_validation import (
    WorldbuildingFisheryValidationError,
    validate_worldbuilding_fishery_context,
)

DATA = Path(__file__).parent / 'data'
LEGACY = json.loads((DATA / 'worldbuilding_fishery_legacy.json').read_text())
V1 = LEGACY['expected']['worldbuilding_realism_model']
V2_NAME = 'causal_upstream_evidence_worldbuilding_realism_checks_v2'


def source_world(name):
    metadata = json.loads((DATA / 'worldbuilding_fishery_provenance.json').read_text())[name]
    raw = (DATA / (name + '.world.json.gz')).read_bytes()
    decoded = gzip.decompress(raw)
    assert hashlib.sha256(raw).hexdigest() == metadata['compressed_sha256']
    assert hashlib.sha256(decoded).hexdigest() == metadata['uncompressed_sha256']
    result = json.loads(decoded)
    assert len(result['cells']) == metadata['cell_count']
    return result


def parent(*cells, water='fresh_lake', temperature=18.0, zero=False):
    base = {'id': 0, 'area_km2': 1.0, 'neighbors': [], 'temperature_c': temperature,
            'is_water': water in MARINE_WATER_TYPES, 'is_lake': water == 'fresh_lake',
            'water_body_type': water, 'resource': 'coastal_fisheries',
            'biome': 'freshwater_lake', 'flow_accumulation': 1.0, 'runoff_mm_y': 0.0}
    world = {'cells': list(cells) or [base], 'summary': {'unrelated': {'keep': True}},
             'ecosystem_dynamics_model': deepcopy(_EXPECTED_MODELS['heuristic_ecosystem_climate_support_v4'])}
    enrich_world_with_ecosystem_dynamics(world)
    if zero:
        for cell in world['cells']:
            cell.update(primary_productivity_index=0.0, fishery_productivity_index=0.0)
        world['renewable_resource_records'] = []
    enrich_world_with_resource_deposits(world)
    assert validate_biological_resources(world, include_commodities=False) == []
    return world


def run(world):
    assert enrich_world_with_worldbuilding_realism(world) is world
    assert validate_worldbuilding_fishery_context(world) == []
    assert world['worldbuilding_realism_model']['model_type'] == V2_NAME
    return world['worldbuilding_realism_checks'][4]


@pytest.mark.parametrize('water', ['ocean', 'continental_shelf', 'inland_sea', 'fresh_lake'])
@pytest.mark.parametrize('zero', [False, True])
def test_known_supported_fishery_inputs_include_fresh_lakes_and_zero(water, zero):
    world = parent(water=water, zero=zero)
    if water == 'fresh_lake':
        assert world['cells'][0]['is_water'] is False
        assert world['cells'][0]['is_lake'] is True
    check = run(world)
    assert check['value'] == 1.0
    assert check['evidence']['supported_resource_counts'] == {'coastal_fisheries': 1}
    assert check['evidence']['source_context_supported_resource_deposit_count'] == 1
    assert check['evidence']['emitted_resource_evidence_available'] is True
    assert check['evidence']['fishery_resource_proxy_supported_cell_count'] == 1
    assert 'commodity_occurrence_model' not in world  # Not a consumed prerequisite.


@pytest.mark.parametrize('temperature,supported', [
    (-100., False), (-18., False), (-16., False),
    (math.nextafter(-16., math.inf), True), (0., True),
    (math.nextafter(44., -math.inf), True), (44., False), (100., False),
])
def test_upstream_domain_omissions_are_explicit_without_new_temperature_window(temperature, supported):
    world = parent(temperature=temperature)
    check = run(world)
    assert len(world['resource_deposits']) == int(supported)
    evidence = check['evidence']
    assert evidence['emitted_resource_evidence_available'] is supported
    assert evidence['fishery_resource_proxy_applicable_cell_count'] == 1
    assert evidence['fishery_resource_proxy_supported_cell_count'] == int(supported)
    assert evidence['unsupported_fishery_resource_proxy_cell_count'] == int(not supported)
    assert check['value'] == 1.0  # Conditional consistency, including empty emission.
    assert world['worldbuilding_realism_model']['empty_resource_deposit_policy'] == 'conditional_fraction_one_not_global_resource_availability'


@pytest.mark.parametrize('water,is_lake,is_river', [
    ('land', False, False), ('land', False, True),
    ('saline_basin', False, False), ('saline_basin', True, False), ('unknown', False, False),
])
def test_fishery_native_label_does_not_override_upstream_habitat(water, is_lake, is_river):
    cell = {'id': 0, 'resource': 'coastal_fisheries', 'water_body_type': water,
            'is_lake': is_lake, 'is_water': False, 'is_river': is_river,
            'temperature_c': 18., 'area_km2': 1., 'neighbors': []}
    world = parent(cell)
    evidence = run(world)['evidence']
    assert evidence['fishery_resource_proxy_supported_cell_count'] == 0
    assert evidence['emitted_resource_evidence_available'] is False


def test_fresh_lake_does_not_become_marine_coast_or_port_habitat():
    assert MARINE_WATER_TYPES == {'ocean', 'continental_shelf', 'inland_sea'}
    land = {'id': 0, 'neighbors': [1]}
    assert not _is_coastal_land(land, {1: {'water_body_type': 'fresh_lake'}})
    assert _is_coastal_land(land, {1: {'water_body_type': 'continental_shelf'}})


@pytest.mark.parametrize('version', [None, 'heuristic_ecosystem_climate_support_v2', 'heuristic_ecosystem_climate_support_v3'])
def test_historical_output_exactly_matches_frozen_original(version):
    world = deepcopy(LEGACY['input'])
    expected = deepcopy(LEGACY['expected'])
    if version:
        world['ecosystem_dynamics_model'] = deepcopy(_EXPECTED_MODELS[version])
        expected['ecosystem_dynamics_model'] = deepcopy(_EXPECTED_MODELS[version])
    enrich_world_with_worldbuilding_realism(world)
    assert world == expected
    assert validate_worldbuilding_fishery_context(world) == []
    check = world['worldbuilding_realism_checks'][4]
    assert check['evidence']['resource_counts']['coastal_fisheries'] == 2
    assert check['evidence']['supported_resource_counts']['coastal_fisheries'] == 1


def test_explicit_v1_is_not_silently_upgraded_and_upgrade_is_deliberate():
    world = parent()
    world['worldbuilding_realism_model'] = deepcopy(V1)
    world['summary']['worldbuilding_realism_model'] = V1['model_type']
    enrich_world_with_worldbuilding_realism(world)
    assert world['worldbuilding_realism_model'] == V1
    assert world['worldbuilding_realism_checks'][4]['value'] == 0.0
    assert validate_worldbuilding_fishery_context(world) == []
    del world['worldbuilding_realism_model']
    del world['summary']['worldbuilding_realism_model']
    assert run(world)['value'] == 1.0


@pytest.mark.parametrize('name,source_count,emitted_count', [
    ('continental_realm', 79, 79), ('cryogenic_slushball', 83, 0), ('verdant_hothouse', 85, 0),
])
def test_retained_complete_geo_inputs_replay_without_generation_or_source_mutation(name, source_count, emitted_count):
    world = source_world(name)
    before = deepcopy(world)
    identities = {key: id(value) for key, value in world.items() if key != 'summary'}
    old = deepcopy(world)
    old['worldbuilding_realism_model'] = deepcopy(V1)
    old['summary']['worldbuilding_realism_model'] = V1['model_type']
    enrich_world_with_worldbuilding_realism(old)
    check = run(world)
    assert world['worldbuilding_realism_checks'][:4] == old['worldbuilding_realism_checks'][:4]
    assert all(world[k] == value and id(world[k]) == identities[k] for k, value in before.items() if k != 'summary')
    assert all(world['summary'][k] == value for k, value in before['summary'].items())
    evidence = check['evidence']
    assert evidence['fishery_resource_proxy_applicable_cell_count'] == source_count
    assert evidence['fishery_resource_proxy_supported_cell_count'] == emitted_count
    assert evidence['unsupported_fishery_resource_proxy_cell_count'] == source_count - emitted_count
    if name == 'continental_realm':
        by_id = {cell['id']: cell for cell in world['cells']}
        lake_ids = [r['cell_id'] for r in world['resource_deposits'] if r['resource'] == 'coastal_fisheries' and by_id[r['cell_id']]['water_body_type'] == 'fresh_lake']
        assert lake_ids == [24, 45, 58, 101, 110]
        assert all(not by_id[i]['is_water'] and by_id[i]['is_lake'] for i in lake_ids)
        assert evidence['source_context_supported_resource_deposit_count'] == 102
        assert old['worldbuilding_realism_checks'][4]['evidence']['geologically_supported_resource_deposit_count'] == 97
        assert check['value'] == .962264
        assert evidence['resource_counts']['evaporites'] == 4
        assert 'evaporites' not in evidence['supported_resource_counts']  # No material rule relaxed.
    after = deepcopy(world)
    run(world)
    assert world == after
    assert all(id(world[k]) == identities[k] for k in before if k != 'summary')


def test_v2_preserves_material_predicates_and_all_unrelated_check_records():
    cells = deepcopy(LEGACY['input']['cells'])
    for cell in cells:
        cell['area_km2'] = 1.
    world = parent(*cells)
    legacy = deepcopy(world)
    legacy['worldbuilding_realism_model'] = deepcopy(V1)
    legacy['summary']['worldbuilding_realism_model'] = V1['model_type']
    enrich_world_with_worldbuilding_realism(legacy)
    evidence = run(world)['evidence']
    old = legacy['worldbuilding_realism_checks'][4]['evidence']
    assert world['worldbuilding_realism_checks'][:4] == legacy['worldbuilding_realism_checks'][:4]
    assert evidence['resource_counts'] == old['resource_counts']
    assert {k: v for k, v in evidence['supported_resource_counts'].items() if k != 'coastal_fisheries'} == {k: v for k, v in old['supported_resource_counts'].items() if k != 'coastal_fisheries'}
    assert evidence['supported_resource_counts']['coastal_fisheries'] == old['supported_resource_counts']['coastal_fisheries'] + 1


def mutate(world, case):
    if case == 'unknown_own': world['worldbuilding_realism_model'] = {'model_type': 'future'}
    elif case == 'malformed_own': world['worldbuilding_realism_model'] = []
    elif case == 'own_summary_only': world['summary']['worldbuilding_realism_model'] = V2_NAME
    elif case == 'mixed_own_summary':
        run(world)
        world['summary']['worldbuilding_realism_model'] = V1['model_type']
    elif case == 'own_v2_missing_parent':
        run(world)
        del world['ecosystem_dynamics_model']
    elif case == 'unknown_ecosystem': world['ecosystem_dynamics_model']['model'] = 'future'
    elif case == 'partial_ecosystem': del world['ecosystem_dynamics_model']['aquatic_ecology_policy']
    elif case == 'missing_deposit_model': del world['resource_deposit_model']
    elif case == 'unknown_deposit': world['resource_deposit_model']['model_type'] = 'future'
    elif case == 'missing_supported_deposit': world['resource_deposits'] = []
    elif case == 'forged_parent_support': world['cells'][0]['fishery_productivity_supported'] = False
    elif case == 'forged_resource_support': world['cells'][0]['fishery_resource_proxy_supported'] = False
    elif case == 'wrong_deposit_cell': world['resource_deposits'][0]['cell_id'] = 999
    elif case == 'malformed_deposit': world['resource_deposits'][0]['resource'] = []
    elif case == 'changed_deposit_equation': world['resource_deposits'][0]['reserve_potential_index'] = .999999
    elif case == 'late_human_error': world['settlements'] = [{'id': 1, 'cell_id': 0, 'score': 'broken'}]
    else: raise AssertionError(case)


@pytest.mark.parametrize('case', [
    'unknown_own','malformed_own','own_summary_only','mixed_own_summary','own_v2_missing_parent',
    'unknown_ecosystem','partial_ecosystem','missing_deposit_model','unknown_deposit',
    'missing_supported_deposit','forged_parent_support','forged_resource_support','wrong_deposit_cell',
    'malformed_deposit','changed_deposit_equation','late_human_error',
])
def test_failure_precedes_any_mutation_including_late_nonfishery_input(case):
    world = parent()
    mutate(world, case)
    before = deepcopy(world)
    identities = {key: id(value) for key, value in world.items()}
    with pytest.raises(ValueError):
        enrich_world_with_worldbuilding_realism(world)
    assert world == before
    assert all(id(world[key]) == identity for key, identity in identities.items())


def test_unsupported_retained_record_rejected_instead_of_merely_scored_badly():
    supported = parent()
    world = parent(temperature=100.)
    world['resource_deposits'] = deepcopy(supported['resource_deposits'])
    before = deepcopy(world)
    with pytest.raises(WorldbuildingFisheryValidationError, match='coverage'):
        enrich_world_with_worldbuilding_realism(world)
    assert world == before


@pytest.mark.parametrize('target', ['context_count','available','source_count','ratio','metric','summary','model','total','nonfinite_score'])
def test_independent_validator_rejects_output_tampering_without_mutation(target):
    world = parent()
    check = run(world)
    if target == 'context_count': check['evidence']['source_context_supported_resource_deposit_count'] = 0
    elif target == 'available': check['evidence']['emitted_resource_evidence_available'] = 1  # Strict bool.
    elif target == 'source_count': check['evidence']['unsupported_fishery_resource_proxy_cell_count'] = 1
    elif target == 'ratio': check['value'] = .99
    elif target == 'metric': check['metric'] = 'fraction_resource_deposits_with_resource_specific_geologic_support'
    elif target == 'summary': world['summary']['resource_geology_dependency_index'] = .99
    elif target == 'model': world['worldbuilding_realism_model']['fishery_water_body_types'].remove('fresh_lake')
    elif target == 'total': world['summary']['worldbuilding_realism_pass_count'] = 0
    elif target == 'nonfinite_score': world['worldbuilding_realism_checks'][0]['score'] = math.inf
    before = deepcopy(world)
    errors = validate_worldbuilding_fishery_context(world)
    assert len(errors) == 1 and 'worldbuilding' in errors[0]
    assert world == before


def test_raw_new_parent_is_not_misreported_as_valid_worldbuilding_output():
    world = parent()
    before = deepcopy(world)
    errors = validate_worldbuilding_fishery_context(world)
    assert len(errors) == 1 and 'own model' in errors[0]
    assert world == before


def test_explicit_v2_cannot_run_on_an_absent_historical_parent():
    current = parent()
    run(current)
    old = deepcopy(LEGACY['input'])
    old['worldbuilding_realism_model'] = deepcopy(current['worldbuilding_realism_model'])
    old['summary']['worldbuilding_realism_model'] = V2_NAME
    before = deepcopy(old)
    with pytest.raises(WorldbuildingFisheryValidationError, match='requires'):
        enrich_world_with_worldbuilding_realism(old)
    assert old == before


def test_present_unknown_own_model_rejected_before_empty_cell_early_return():
    world = {'cells': [], 'worldbuilding_realism_model': {'model_type': 'future'}}
    before = deepcopy(world)
    with pytest.raises(WorldbuildingFisheryValidationError, match='unknown'):
        enrich_world_with_worldbuilding_realism(world)
    assert world == before


def test_independent_helper_has_no_worldbuilding_producer_dependency():
    import ast
    import magic_geo.worldbuilding_fishery_validation as module
    tree = ast.parse(Path(module.__file__).read_text())
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert 'worldbuilding_realism' not in imports
    assert 'resource_dynamics' not in imports
    assert 'ecosystem_dynamics' not in imports
