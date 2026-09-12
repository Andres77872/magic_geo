"""Hash-checked complete retained inputs and deliberate owned-stage migration."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
import gzip,hashlib,json
from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
from magic_geo.reef_diagnostics import enrich_world_with_reef_diagnostics
from magic_geo.species_ranges import enrich_world_with_species_ranges
from magic_geo.wildfire_disturbance import enrich_world_with_wildfire_disturbance
from magic_geo.aquatic_climate_validation import validate_aquatic_climate_support
from magic_geo.species_habitat_validation import (
    validate_species_habitat_support, PRESCRIBED_SPECIES_CELL_FIELDS as SPECIES_CELLS,
    PRESCRIBED_SPECIES_SUMMARY_FIELDS as SPECIES_SUMMARY,
)
from magic_geo.wildfire_aquatic_validation import (
    validate_wildfire_aquatic_exclusion, PRESCRIBED_FIRE_CELL_FIELDS as FIRE_CELLS,
    PRESCRIBED_FIRE_SUMMARY_FIELDS as FIRE_SUMMARY,
)
from magic_geo.prescribed_natural_ecosystem_validation import CELL_FIELDS as ECO_CELLS, SUMMARY_FIELDS as ECO_SUMMARY, RECORD_FIELDS as ECO_RECORDS
DATA=Path(__file__).parents[1]/'data/prescribed_natural_ecosystem'
NATIVE_KEYS=('climate_model','climate_energy_model','climate_energy_balance_records','climate_energy_forcing_intervals','climate_energy_transport_edges')

@lru_cache(maxsize=None)
def archived_activity_world(scope='full'):
    m=json.loads((DATA/'manifest.json').read_text())[scope]
    packed=(DATA/m['file']).read_bytes();assert hashlib.sha256(packed).hexdigest()==m['compressed_sha256']
    raw=gzip.decompress(packed);assert hashlib.sha256(raw).hexdigest()==m['raw_sha256']
    world=json.loads(raw)
    assert len(world['cells'])==m['cell_count']
    assert validate_aquatic_climate_support(world)==[]
    assert validate_species_habitat_support(world)==[]
    assert validate_wildfire_aquatic_exclusion(world)==[]
    return world

def clear_stage(world,cell_fields,summary_fields,top_fields):
    for c in world['cells']:
        for k in cell_fields:c.pop(k,None)
    for k in summary_fields:world['summary'].pop(k,None)
    for k in top_fields:world.pop(k,None)

def fresh_activity_world(scope='full'):
    world=deepcopy(archived_activity_world(scope))
    clear_stage(world,SPECIES_CELLS,SPECIES_SUMMARY,('species_ranges_model','species_range_records'))
    clear_stage(world,FIRE_CELLS,FIRE_SUMMARY,('wildfire_disturbance_model','wildfire_spread_histories'))
    clear_stage(world,ECO_CELLS,ECO_SUMMARY,('ecosystem_dynamics_model',*ECO_RECORDS))
    return world

def build_to_species_inputs(world):
    enrich_world_with_ecosystem_dynamics(world)
    enrich_world_with_reef_diagnostics(world)
    return world

def build_activity_world(world):
    build_to_species_inputs(world)
    enrich_world_with_species_ranges(world)
    enrich_world_with_wildfire_disturbance(world)
    return world

def stage_owned(world,stage):
    cell_fields,summary_fields,top_fields=(
        (SPECIES_CELLS,SPECIES_SUMMARY,('species_ranges_model','species_range_records')) if stage=='species' else
        (FIRE_CELLS,FIRE_SUMMARY,('wildfire_disturbance_model','wildfire_spread_histories')))
    return {'cells':[{k:c[k] for k in cell_fields} for c in world['cells']],
            'summary':{k:world['summary'][k] for k in summary_fields},**{k:world[k] for k in top_fields}}
