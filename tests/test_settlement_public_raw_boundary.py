"""Raw schema tests on retained native units, never a full climate claim."""
from copy import deepcopy
import gzip
import hashlib
import json
import math
from pathlib import Path

import pytest

from magic_geo.api import _strip_native_civilization_outputs
from magic_geo.native_social_public_validation import (
    require_raw_native_social_publication, validate_public_native_social,
    NATIVE_SOCIAL_PUBLIC_MODELS, RECORDED_SUMMARY_FIELDS,
)
from support.native_social_worlds import native_social_unit_world


def check(world, *, cells=True, geo=False, current=True):
    require_raw_native_social_publication(world, geography_only=geo, include_cells=cells, require_current=current)


@pytest.mark.parametrize('include_cells',[True,False])
def test_actual_retained_v4_native_raw_world_and_summary_projection(include_cells):
    folder=Path(__file__).parent/'fixtures/settlement_public_raw'
    manifest=json.loads((folder/'manifest.json').read_text())
    stored=(folder/'c_api_v4_world.json.gz').read_bytes()
    assert hashlib.sha256(stored).hexdigest()==manifest['stored_sha256']
    raw=gzip.decompress(stored)
    assert hashlib.sha256(raw).hexdigest()==manifest['raw_sha256']
    world=json.loads(raw)
    if not include_cells:world['cells']=[]
    before=deepcopy(world)
    check(world,cells=include_cells)
    assert world==before
    assert 'population_region_model' not in world


@pytest.mark.parametrize('case', ['environment_stage_healthy','environment_stage_mixed'])
@pytest.mark.parametrize('include_cells',[True,False])
def test_retained_raw_native_units_and_summary_shape(case,include_cells):
    world=native_social_unit_world(case)
    if not include_cells:
        world['cells']=[]
    before=deepcopy(world)
    check(world,cells=include_cells)
    assert world==before
    # No Python own-model identity or physical certificate is fabricated by
    # the structural gate; complete annotated numerical replay still refuses.
    assert validate_public_native_social(world)[1]


@pytest.mark.parametrize('mutation',[
    lambda w:w.pop('native_social_availability_model'),
    lambda w:w['native_social_availability_model'].update(extra=True),
    lambda w:w['native_social_availability'].update(ruin_inference_available=1),
    lambda w:w['native_social_availability'].update(ruin_inference_available=True),
    lambda w:w['native_social_availability'].update(ruin_supported_candidate_cell_count=True),
    lambda w:w['native_social_availability']['ruin_unavailable_cell_ids'].append(999999),
    lambda w:w['summary']['native_social_summary_availability'].update(estimated_world_population=0),
    lambda w:w['summary'].update(estimated_world_population=0),
    lambda w:w['summary'].update(recorded_ruin_count=True),
    lambda w:w['summary'].update(recorded_historical_event_count=999),
    lambda w:w['summary'].update(available_population_region_count=999),
    lambda w:w['cells'][0].update(settlement_climate_supported=0),
    lambda w:w['cells'][0].update(is_lake=0),
    lambda w:w['cells'][0].update(settlement_climate_temperature_c=math.inf),
    lambda w:w['population_regions'][0].update(site_input_complete=1),
    lambda w:w['population_regions'][0].update(site_input_supported_cell_count=True),
    lambda w:w['population_regions'][0].update(site_strength_index=0),
    lambda w:w['territorial_snapshots'][0].pop('geometry_estimate_available'),
    lambda w:w['native_social_availability']['historical_event_family_coverage'][0].update(recorded_event_count=999),
])
def test_raw_typed_and_coverage_mutations_reject_without_writes(mutation):
    world=native_social_unit_world('environment_stage_mixed')
    mutation(world);before=deepcopy(world)
    with pytest.raises(ValueError):check(world)
    assert world==before


def test_current_raw_family_must_not_disappear():
    world=native_social_unit_world('environment_stage_mixed')
    world.pop('native_social_availability');world.pop('native_social_availability_model')
    with pytest.raises(ValueError):check(world)
    with pytest.raises(ValueError):check(world,current=False)


def test_geo_strip_removes_new_owned_envelopes_and_mirrors_but_preserves_physics():
    world=native_social_unit_world('environment_stage_mixed')
    for key in NATIVE_SOCIAL_PUBLIC_MODELS:
        world.setdefault(key,{'model_type':'deliberate test marker'})
        world['summary'][key]='deliberate test marker'
    physical=[{key:cell[key] for key in ('is_water','is_lake','temperature_c','fertility')} for cell in world['cells']]
    _strip_native_civilization_outputs(world)
    check(world,geo=True)
    assert not (NATIVE_SOCIAL_PUBLIC_MODELS|{'native_social_availability'}).intersection(world)
    assert not (NATIVE_SOCIAL_PUBLIC_MODELS|RECORDED_SUMMARY_FIELDS).intersection(world['summary'])
    assert all('settlement_score' not in cell and 'settlement_climate_supported' not in cell and 'settlement_climate_temperature_c' not in cell for cell in world['cells'])
    assert [{key:cell[key] for key in item} for cell,item in zip(world['cells'],physical)]==physical
