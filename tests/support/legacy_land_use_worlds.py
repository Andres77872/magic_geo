"""Complete historical land-use worlds for explicit v1 numerical diagnostics.

The existing adjacent human-water fixtures retain the original land-use,
frontier and worldbuilding declarations too. Reuse those complete hash-checked
artifacts instead of relabelling a freshly generated world or storing a second
copy. Current-model tests continue to use the current-world fixtures.
"""

from copy import deepcopy
from functools import lru_cache

from magic_geo.human_geography_validation import validate_human_geography_replay
from support.legacy_human_water_worlds import legacy_human_water_world_readonly


@lru_cache(maxsize=None)
def legacy_land_use_world_readonly(key="replay_128"):
    world = legacy_human_water_world_readonly(key)
    model = "causal_soil_climate_resource_connected_land_use_zones_v1"
    assert world["land_use_zone_model"]["model_type"] == model
    assert world["summary"]["land_use_zone_model"] == model
    assert validate_human_geography_replay(world) == []
    return world


def legacy_land_use_world(key="replay_128"):
    return deepcopy(legacy_land_use_world_readonly(key))
