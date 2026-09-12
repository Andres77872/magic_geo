"""Complete retained-source replay for the E5 resource chain; never generate.

Only the ecosystem/resource/commodity/worldbuilding owned outputs are upgraded.
Unrerun species/fire/other human descendants remain explicitly outside this
stage-focused fixture's consistency claim.
"""
from copy import deepcopy
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path

from magic_geo.aquatic_climate_validation import validate_aquatic_climate_support
from magic_geo.biological_resource_validation import (
    RESOURCE_CELL_FIELDS, RESOURCE_SUMMARY_FIELDS, RESOURCE_TOP_FIELDS,
    COMMODITY_CELL_FIELDS, COMMODITY_SUMMARY_FIELDS, COMMODITY_TOP_FIELDS,
    validate_biological_resources,
)
from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
from magic_geo.prescribed_natural_ecosystem_validation import CELL_FIELDS, SUMMARY_FIELDS, RECORD_FIELDS
from magic_geo.worldbuilding_fishery_validation import WORLDBUILDING_SUMMARY_FIELDS, validate_worldbuilding_fishery_context

DATA=Path(__file__).parents[1]/"data/prescribed_natural_ecosystem"
OWNERS={
    "ecosystem":(CELL_FIELDS,SUMMARY_FIELDS,("ecosystem_dynamics_model",*RECORD_FIELDS)),
    "resource":(RESOURCE_CELL_FIELDS,RESOURCE_SUMMARY_FIELDS,RESOURCE_TOP_FIELDS),
    "commodity":(COMMODITY_CELL_FIELDS,COMMODITY_SUMMARY_FIELDS,COMMODITY_TOP_FIELDS),
    "worldbuilding":((),WORLDBUILDING_SUMMARY_FIELDS,("worldbuilding_realism_model","worldbuilding_realism_checks")),
}


@lru_cache(maxsize=None)
def _retained(scope):
    entry=json.loads((DATA/"manifest.json").read_text())[scope]
    packed=(DATA/entry["file"]).read_bytes()
    assert hashlib.sha256(packed).hexdigest()==entry["compressed_sha256"]
    raw=gzip.decompress(packed)
    assert hashlib.sha256(raw).hexdigest()==entry["raw_sha256"]
    world=json.loads(raw)
    assert len(world["cells"])==entry["cell_count"]
    assert validate_aquatic_climate_support(world)==[]
    assert validate_biological_resources(world)==[]
    if scope=="full":assert validate_worldbuilding_fishery_context(world)==[]
    return world


def retained_resource_world(scope="full"):
    return deepcopy(_retained(scope))


def clear_resource_stage(world,stage):
    fields,summary,tops=OWNERS[stage]
    for cell in world["cells"]:
        for key in fields:cell.pop(key,None)
    for key in summary:world["summary"].pop(key,None)
    for key in tops:world.pop(key,None)


def owned_resource_stage(world,stage):
    fields,summary,tops=OWNERS[stage]
    return {"cells":[{k:c[k] for k in fields if k in c} for c in world["cells"]],
            "summary":{k:world["summary"][k] for k in summary if k in world["summary"]},
            **{k:world[k] for k in tops if k in world}}


def fresh_resource_inputs(scope="full"):
    world=retained_resource_world(scope)
    # Audit the actual old complete matched chain above, then clear ALL mirrors,
    # records and identities, rather than retagging old output under E5 names.
    for stage in OWNERS:clear_resource_stage(world,stage)
    enrich_world_with_ecosystem_dynamics(world)
    assert validate_aquatic_climate_support(world)==[]
    return world
