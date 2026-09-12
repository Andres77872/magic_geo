"""Availability tail controls; retained native inputs only, no generation.

Explicit scoped equation controls below use declared synthetic populations or
three economy fields. They do not bypass public source gates or claim full
world acceptance.
"""
import ast
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest
from support.native_social_worlds import annotated_environment_social_world
from magic_geo.phonology_history import enrich_world_with_phonology_history
from magic_geo.phonology_history_validation import validate_phonology_history_replay
from magic_geo.dynasty_genealogy import enrich_world_with_dynasty_genealogy
from magic_geo.dynasty_genealogy_validation import validate_dynasty_genealogy_replay
from magic_geo import phonology_history_availability as phonology
from magic_geo import native_phonology_history_validation as phonology_audit
from magic_geo import dynasty_genealogy_availability as genealogy
from magic_geo import native_dynasty_genealogy_validation as genealogy_audit


def typed_json(value):return json.dumps(value,sort_keys=True,allow_nan=False)

@pytest.fixture(scope='module',params=['healthy','mixed'])
def phonology_world(request):
    world=annotated_environment_social_world(request.param)
    enrich_world_with_phonology_history(world)
    return world


def test_public_phonology_complete_mixed_readonly_and_idempotent(phonology_world):
    before=typed_json(phonology_world)
    assert validate_phonology_history_replay(phonology_world)==[]
    assert typed_json(phonology_world)==before
    copy=deepcopy(phonology_world)
    assert enrich_world_with_phonology_history(copy) is copy
    assert typed_json(copy)==before
    assert copy['phonological_rules'] and copy['lexical_correspondences']

PHONOLOGY_TAMPERS=[
    lambda w:w['phonology_history_model'].update(deterministic=1),
    lambda w:w['phonology_history_model'].update(source_population_region_model='old'),
    lambda w:w['phonology_history_model'].update(extra=True),
    lambda w:w['summary'].update(phonology_history_model='old'),
    lambda w:w['phonological_rules'][0].update(probability_index=.123456),
    lambda w:w['lexical_correspondences'][0].update(derived_form='bogus'),
    lambda w:w['phonological_histories'][0]['steps'][0].update(era_id=True),
    lambda w:w['lexical_diffusion_histories'][0]['steps'][0].update(adoption_fraction=None),
    lambda w:w['speaker_population_histories'][0].update(population_region_ids=[]),
    lambda w:w['speaker_population_histories'][0].update(population_region_count=True),
    lambda w:w['speaker_population_histories'][0].update(estimate_available=1),
    lambda w:w['speaker_population_histories'][0]['estimate_availability'].update(final_speaker_population=1),
    lambda w:w['speaker_population_histories'][0].update(final_speaker_population=777.),
    lambda w:w['speaker_population_histories'][0]['steps'][0].update(speaker_fraction_index=.77),
    lambda w:w['speaker_population_histories'][0]['steps'][0].update(register_divergence_index=.77),
    lambda w:w['speaker_population_histories'][0]['steps'][0].update(estimate_available=1),
    lambda w:w['speaker_population_histories'][0]['steps'][0]['estimate_availability'].update(contact_pressure_index=1),
    lambda w:w['speaker_population_histories'][0]['steps'].pop(),
    lambda w:w['language_regions'][0].update(speaker_population_history_id=True),
    lambda w:w['summary']['speaker_history_summary_availability'].update(total_estimated_speaker_population=1),
    lambda w:w['summary'].update(total_estimated_speaker_population=999.),
    lambda w:w['summary'].update(available_speaker_population_history_count=True),
    lambda w:w['population_regions'][0].update(population_estimate_available=1),
    lambda w:w['population_regions'][0].update(estimated_population=999.),
    lambda w:w['historical_eras'][0].update(start_year_bp=999.),
]
@pytest.mark.parametrize('mutate',PHONOLOGY_TAMPERS)
def test_phonology_rejects_and_preserves_existing_tampered_output(phonology_world,mutate):
    changed=deepcopy(phonology_world);mutate(changed)
    assert typed_json(changed)!=typed_json(phonology_world)
    before=typed_json(changed)
    assert validate_phonology_history_replay(changed)
    with pytest.raises(ValueError):enrich_world_with_phonology_history(changed)
    assert typed_json(changed)==before

@pytest.mark.parametrize('mutation',[
    lambda w:w['population_regions'][0].update(estimated_population=999.),
    lambda w:w['historical_event_model'].update(deterministic=1),
    lambda w:w['summary'].update(total_estimated_speaker_population=0.),
    lambda w:w.update(speaker_population_histories=[]),
    lambda w:w['language_regions'][0].update(speaker_population_history_id=0),
])
def test_phonology_first_annotation_is_atomic(mutation):
    world=annotated_environment_social_world('mixed');mutation(world);before=typed_json(world)
    with pytest.raises(ValueError):enrich_world_with_phonology_history(world)
    assert typed_json(world)==before


def scoped_phonology(world):
    actual=deepcopy(world);phonology._calculate(actual)
    expected=phonology_audit._expected(world)
    for key,value in zip(phonology_audit.COLLECTIONS,expected[:5]):assert actual[key]==value
    for key,value in expected[-1].items():assert actual['summary'][key]==value
    return actual


def test_scoped_known_zero_speakers_never_use_area_fallback():
    world=annotated_environment_social_world('healthy')
    for pop in world['population_regions']:pop['estimated_population']=0.
    result=scoped_phonology(world)
    history=result['speaker_population_histories'][0]
    assert history['final_speaker_population']==0.
    assert all(s['speaker_population']==s['speaker_fraction_index']==0. for s in history['steps'])
    assert history['estimate_available']
    # These altered primitive inputs are only a pure equation control.
    assert validate_phonology_history_replay(result)


def test_scoped_local_population_fields_survive_unknown_other_language():
    world=annotated_environment_social_world('healthy')
    other=deepcopy(world['language_regions'][0]);other['id']=1
    world['language_regions'].append(other)
    world['population_regions'][1]['language_region_id']=1
    world['population_regions'][1]['estimated_population']=None
    world['population_regions'][1]['population_estimate_available']=False
    result=scoped_phonology(world)
    known,unknown=result['speaker_population_histories']
    assert known['final_speaker_population'] is not None
    assert unknown['final_speaker_population'] is None
    for step in known['steps']:
        assert step['contact_pressure_index'] is not None
        assert step['syllable_pressure_index'] is not None
        assert step['phonetic_reduction_index'] is not None
        for field in ('speaker_fraction_index','allophonic_variation_index','population_adoption_index','register_divergence_index','pronunciation_regularization_index'):
            assert step[field] is None and step['estimate_availability'][field] is False
    assert all(s['contact_pressure_index'] is None for s in unknown['steps'])


def scoped_genealogy_world():
    world=annotated_environment_social_world('healthy')
    fields=('peak_gross_output_index','peak_treasury_index','max_army_capacity_population')
    world['economy_histories']=[{'region_id':r['id'],**dict(zip(fields,(800.,125.,1000.))),
        'estimate_availability':{key:True for key in fields}} for r in world['political_regions']]
    return world


def scoped_genealogy(world):
    before=typed_json(world)
    expected=genealogy_audit.expected_genealogy_available(world)
    assert typed_json(world)==before
    private=deepcopy(world);rows=genealogy._coverage(private)
    available={r['region_id'] for r in rows if r['lineage_inference_available']}
    genealogy._calculate(private,available,len(available)==len(rows))
    annotations={d['id']:{k:d[k] for k in genealogy.GENEALOGY_FIELDS} for d in private['dynasties'] if d['region_id'] in available}
    coverage=genealogy._finish_genealogy(private,rows,private['rulers'],private['marriage_alliances'],private['cadet_branches'],annotations,private['summary'])
    for key,value in zip(genealogy_audit.COLLECTIONS,expected[:3]):assert private[key]==value
    assert annotations==expected[3] and coverage==expected[5]
    for key,value in expected[4].items():assert private['summary'][key]==value
    return private,annotations,coverage


def test_scoped_genealogy_complete_actual_equations():
    result,annotations,coverage=scoped_genealogy(scoped_genealogy_world())
    assert result['rulers'] and result['cadet_branches'] and result['marriage_alliances']
    assert coverage['lineage_inference_available'] and coverage['alliance_inference_available']
    assert all(r['lineage_estimate_available'] and r['alliance_estimate_available'] for r in result['rulers'])

@pytest.mark.parametrize('field',('peak_gross_output_index','peak_treasury_index','max_army_capacity_population'))
def test_scoped_genealogy_partial_region_keeps_local_lineage_but_no_global_alliances(field):
    world=scoped_genealogy_world()
    world['economy_histories'][1][field]=None
    world['economy_histories'][1]['estimate_availability'][field]=False
    result,annotations,coverage=scoped_genealogy(world)
    assert coverage['available_region_count']==1
    assert result['rulers'] and all(r['region_id']==0 for r in result['rulers'])
    assert result['marriage_alliances']==[]
    assert all(r['spouse_ruler_id'] is None and r['marriage_alliance_id'] is None for r in result['rulers'])
    assert result['summary']['ruler_count'] is None and result['summary']['recorded_ruler_count']>0
    assert coverage['region_coverage'][1]['ruler_count'] is None
    assert annotations[world['dynasties'][1]['id']]['founder_ruler_id'] is None


def test_scoped_empty_lineage_domain_is_known_zero():
    world=scoped_genealogy_world()
    for key in ('political_regions','dynasties','economy_histories','borders'):world[key]=[]
    result,_,coverage=scoped_genealogy(world)
    assert coverage['lineage_inference_available'] and coverage['applicable_region_count']==0
    assert result['summary']['ruler_count']==0 and result['rulers']==[]


def test_legacy_retained_tail_replay_unchanged():
    base=Path(__file__).parent/'fixtures/legacy_human_water';entry=json.loads((base/'manifest.json').read_text())['replay_128']
    raw=(base/entry['fixture']).read_bytes();assert hashlib.sha256(raw).hexdigest()==entry['fixture_gzip_sha256']
    world=json.loads(gzip.decompress(raw));before=typed_json(world)
    assert validate_phonology_history_replay(world)==[]
    assert validate_dynasty_genealogy_replay(world)==[]
    assert typed_json(world)==before
    enrich_world_with_phonology_history(world);enrich_world_with_dynasty_genealogy(world)
    assert typed_json(world)==before


def test_independent_tail_validators_do_not_import_producer_math():
    root=Path(__file__).parents[1]/'src/magic_geo'
    forbidden={'phonology_history','phonology_history_availability','dynasty_genealogy','dynasty_genealogy_availability'}
    for name in ('native_phonology_history_validation.py','native_dynasty_genealogy_validation.py'):
        tree=ast.parse((root/name).read_text())
        assert not any(isinstance(n,ast.ImportFrom) and n.module in forbidden for n in ast.walk(tree))

@pytest.fixture(scope='module',params=['healthy','mixed'])
def genealogy_world(request):
    from magic_geo.history_dynamics import enrich_world_with_population_history
    from magic_geo.economy_dynamics import enrich_world_with_economy_history
    world=annotated_environment_social_world(request.param)
    enrich_world_with_population_history(world);enrich_world_with_economy_history(world)
    enrich_world_with_dynasty_genealogy(world)
    return world


def test_public_genealogy_readonly_and_atomic_repeat(genealogy_world):
    before=typed_json(genealogy_world)
    assert validate_dynasty_genealogy_replay(genealogy_world)==[]
    assert typed_json(genealogy_world)==before
    copy=deepcopy(genealogy_world)
    assert enrich_world_with_dynasty_genealogy(copy) is copy
    assert typed_json(copy)==before
    envelope=copy['genealogy_availability']
    assert len(envelope['region_coverage'])==len(copy['political_regions'])
    if not envelope['lineage_inference_available']:
        assert copy['summary']['ruler_count'] is None
        assert copy['summary']['recorded_ruler_count']==0
        assert copy['marriage_alliances']==[]

GENEALOGY_TAMPERS=[
    lambda w:w['ruler_genealogy_model'].update(deterministic=1),
    lambda w:w['ruler_genealogy_model'].update(source_economy_history_model='old'),
    lambda w:w['ruler_genealogy_model'].update(extra=True),
    lambda w:w['summary'].update(ruler_genealogy_model='old'),
    lambda w:w['genealogy_availability'].update(lineage_inference_available=1),
    lambda w:w['genealogy_availability'].update(alliance_inference_available=1),
    lambda w:w['genealogy_availability'].update(applicable_region_count=True),
    lambda w:w['genealogy_availability'].update(available_region_count=999),
    lambda w:w['genealogy_availability']['region_coverage'][0].update(source_dynasty_inference_available=1),
    lambda w:w['genealogy_availability']['region_coverage'][0].update(source_dynasty_ids=[999]),
    lambda w:w['genealogy_availability']['region_coverage'][0].update(ruler_count=999),
    lambda w:w['genealogy_availability']['region_coverage'][0].update(unavailable_economy_fields=['bogus']),
    lambda w:w['genealogy_availability']['region_coverage'].pop(),
    lambda w:w['summary'].update(ruler_count=999),
    lambda w:w['summary'].update(recorded_ruler_count=999),
    lambda w:w['summary'].update(mean_ruler_legitimacy_index=.777),
    lambda w:w['summary']['genealogy_summary_availability'].update(ruler_count=1),
    lambda w:w['economy_histories'][0]['estimate_availability'].update(peak_gross_output_index=1),
    lambda w:w['economy_histories'][0].update(peak_gross_output_index=999.),
    lambda w:w['native_social_availability'].update(dynasty_inference_available=1),
]
@pytest.mark.parametrize('mutate',GENEALOGY_TAMPERS)
def test_genealogy_complete_nullable_coverage_tampers_atomic(genealogy_world,mutate):
    changed=deepcopy(genealogy_world);mutate(changed)
    assert typed_json(changed)!=typed_json(genealogy_world)
    before=typed_json(changed)
    assert validate_dynasty_genealogy_replay(changed)
    with pytest.raises(ValueError):enrich_world_with_dynasty_genealogy(changed)
    assert typed_json(changed)==before

@pytest.mark.parametrize('collection,key,value',[
    ('rulers','name','Bogus'),('rulers','legitimacy_index',.777),('rulers','spouse_ruler_id',True),
    ('rulers','lineage_estimate_available',1),('rulers','alliance_estimate_available',1),
    ('marriage_alliances','alliance_strength',.777),('cadet_branches','claim_strength',.777),
    ('dynasties','founder_ruler_id',True),('dynasties','genealogy_estimate_available',1),
])
def test_available_genealogy_equations_and_typed_links(collection,key,value):
    from magic_geo.history_dynamics import enrich_world_with_population_history
    from magic_geo.economy_dynamics import enrich_world_with_economy_history
    world=annotated_environment_social_world('healthy')
    enrich_world_with_population_history(world);enrich_world_with_economy_history(world);enrich_world_with_dynasty_genealogy(world)
    assert validate_dynasty_genealogy_replay(world)==[]
    before=typed_json(world);world[collection][0][key]=value
    assert typed_json(world)!=before
    assert validate_dynasty_genealogy_replay(world)

@pytest.mark.parametrize('mutation',[
    lambda w:w['economy_histories'][0].update(peak_treasury_index=999.),
    lambda w:w.update(rulers=[]),
    lambda w:w['summary'].update(recorded_ruler_count=0),
    lambda w:w['dynasties'][0].update(founder_ruler_id=0),
])
def test_genealogy_first_annotation_failure_is_atomic(mutation):
    from magic_geo.history_dynamics import enrich_world_with_population_history
    from magic_geo.economy_dynamics import enrich_world_with_economy_history
    world=annotated_environment_social_world('healthy')
    enrich_world_with_population_history(world);enrich_world_with_economy_history(world)
    mutation(world);before=typed_json(world)
    with pytest.raises(ValueError):enrich_world_with_dynasty_genealogy(world)
    assert typed_json(world)==before

@pytest.mark.parametrize('mutation,validate',[
    (lambda w:w['speaker_population_histories'][0]['steps'][0].update(estimate_available=True),validate_phonology_history_replay),
    (lambda w:w['speaker_population_histories'][0].update(estimate_available=True),validate_phonology_history_replay),
    (lambda w:w['summary'].update(available_speaker_population_history_count=1),validate_phonology_history_replay),
    (lambda w:w['rulers'][0].update(lineage_estimate_available=True),validate_dynasty_genealogy_replay),
    (lambda w:w['dynasties'][0].update(genealogy_estimate_available=True),validate_dynasty_genealogy_replay),
    (lambda w:w['summary'].update(recorded_ruler_count=5),validate_dynasty_genealogy_replay),
])
def test_orphan_new_field_cannot_hide_under_exact_legacy_model(mutation,validate):
    base=Path(__file__).parent/'fixtures/legacy_human_water';entry=json.loads((base/'manifest.json').read_text())['replay_128']
    world=json.loads(gzip.decompress((base/entry['fixture']).read_bytes()))
    assert validate(world)==[]
    mutation(world)
    assert validate(world)
