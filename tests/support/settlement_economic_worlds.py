"""Portable subsystem fixtures; no native generation or full-world claim.

Actual pinned annual climate/selection sources are the reviewed native extension
fixtures. Missing downstream soil/ecology/ore descriptors below are explicitly
prescribed synthetic inputs, not regenerated geological or human-world evidence.
"""
from copy import deepcopy
from test_settlement_climate_support import ARCHIVES, enrich
from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
from magic_geo.resource_dynamics import enrich_world_with_resource_deposits
from magic_geo.commodity_resources import enrich_world_with_commodity_occurrences


def stage_world(name='earthlike_seed'):
    world=enrich(deepcopy(ARCHIVES[name]['seasonal_supported_selection']))
    defaults=dict(potential_evapotranspiration_mm_y=1000.0,soil_moisture_index=.5,
                  growing_season_months=6.0,soil_organic_matter_fraction=.1,
                  fire_frequency_index=.3,seasonal_aridity_index=.2,ecotone_index=.4,
                  groundwater_recharge_mm_y=0.0,soil_salinity_index=0.0,soil_erodibility_index=.2,
                  tectonic_zone_strength=0.0,fault_slip_rate_index=0.0,seismic_hazard_index=0.0,
                  collision_zone_id=-1,subduction_zone_id=-1,rift_zone_id=-1,fault_system_id=-1)
    for cell in world['cells']:
        for key,value in defaults.items():cell.setdefault(key,value)
    world['sedimentary_resource_systems']=[]
    world['borders']=[]  # Explicit downstream test input; not a complete border-stage replay.
    enrich_world_with_ecosystem_dynamics(world)
    return world


def deposits(name='earthlike_seed'):
    world=stage_world(name)
    enrich_world_with_resource_deposits(world)
    return world


def commodities(name='earthlike_seed'):
    world=deposits(name)
    enrich_world_with_commodity_occurrences(world)
    return world
