"""Exact actual-world migration of the complete prescribed-natural child chain."""
from copy import deepcopy
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from magic_geo import api
from magic_geo.aquatic_climate_validation import validate_aquatic_climate_support
from magic_geo.biological_resource_validation import validate_biological_resources
from magic_geo.climate_energy_validation_dispatch import validate_native_climate_energy_output
from magic_geo.human_geography_validation import validate_human_geography_replay
from magic_geo.species_habitat_validation import validate_species_habitat_support
from magic_geo.wildfire_aquatic_validation import validate_wildfire_aquatic_exclusion


DATA = Path(__file__).resolve().parents[1] / 'data'
OWNERSHIP = json.loads((DATA / 'prescribed_natural_public/ownership.json').read_text())
NATURAL_STAGES = ('ecosystem', 'species', 'fire')
FULL_SUCCESSORS = (
    'enrich_world_with_land_use_zones', 'enrich_world_with_natural_frontiers',
    'enrich_world_with_worldbuilding_realism', 'enrich_world_with_population_history',
    'enrich_world_with_economy_history', 'enrich_world_with_dynasty_genealogy',
    'enrich_world_with_logistics_history', 'enrich_world_with_demographic_agents',
    'enrich_world_with_market_clearing', 'enrich_world_with_graph_diagnostics',
    'enrich_world_with_boundary_geometry', 'enrich_world_with_phonology_history',
)


def audit_sources(world, scope):
    native_errors, _ = validate_native_climate_energy_output(world)
    assert native_errors == [], native_errors
    for audit in (validate_aquatic_climate_support, validate_species_habitat_support,
                  validate_wildfire_aquatic_exclusion, validate_biological_resources):
        errors = audit(world)
        assert errors == [], (audit.__name__, errors)
    if scope == 'full':
        errors = validate_human_geography_replay(world)
        assert errors == [], errors
    else:
        assert world['generation_scope'] == 'geo_only'
        assert 'worldbuilding_realism_model' not in world


@lru_cache(maxsize=None)
def _archive(scope):
    data = DATA / 'prescribed_natural_ecosystem'
    manifest = json.loads((data / 'manifest.json').read_text())[scope]
    compressed = (data / manifest['file']).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == manifest['compressed_sha256']
    raw = gzip.decompress(compressed)
    assert hashlib.sha256(raw).hexdigest() == manifest['raw_sha256']
    world = json.loads(raw)
    assert len(world['cells']) == manifest['cell_count']
    assert world['ecosystem_dynamics_model']['model'] == 'heuristic_ecosystem_climate_support_v4'
    audit_sources(world, scope)
    return world


def archived_world(scope='full'):
    return deepcopy(_archive(scope))


def clear_for_deliberate_upgrade(world, scope):
    """Never infer an upgrade from a new tag on retained old owned outputs."""
    audit_sources(world, scope)
    for name, stage in OWNERSHIP.items():
        if name == 'worldbuilding' and scope == 'geo':
            assert all(key not in world for key in stage['top_level'])
            assert all(key not in world['summary'] for key in stage['summary_fields'])
            continue
        for cell in world['cells']:
            for key in stage['cell_fields']:
                del cell[key]
        for key in stage['summary_fields']:
            del world['summary'][key]
        for key in stage['top_level']:
            del world[key]


def natural_owned(world):
    selected = {}
    for name in NATURAL_STAGES:
        stage = OWNERSHIP[name]
        selected[name] = {
            'cells': [{key: cell[key] for key in stage['cell_fields']} for cell in world['cells']],
            'summary': {key: world['summary'][key] for key in stage['summary_fields']},
            **{key: world[key] for key in stage['top_level']},
        }
    return selected


def _no_generation(*args, **kwargs):
    raise AssertionError('native generation is prohibited in retained-source public replay')


def replay_tail(world, scope):
    from magic_geo import native
    with patch.multiple(native, generate_world=_no_generation, generate_geo_world=_no_generation,
                        generate_seasonal_world=_no_generation, generate_seasonal_geo_world=_no_generation):
        api._enrich_ecosystems_and_resources(world)
        if scope == 'full':
            for name in FULL_SUCCESSORS:
                getattr(api, name)(world)
        else:
            api.enrich_world_with_physical_graph_diagnostics(world)
            api.enrich_world_with_physical_boundary_geometry(world)
            api.enrich_world_with_geo_evolution_provenance(world)
    audit_sources(world, scope)
    return world


def upgraded_world(scope='full'):
    world = archived_world(scope)
    clear_for_deliberate_upgrade(world, scope)
    return replay_tail(world, scope)


@lru_cache(maxsize=None)
def current_world_readonly(scope='full'):
    """Callers must copy before mutation; generation remains explicitly blocked."""
    return upgraded_world(scope)
