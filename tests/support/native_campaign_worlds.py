"""Synthetic social-unit campaign sources; no generator or climate certificate.

The retained environment-stage units carry explicitly synthetic climate inputs.
Campaigns additionally require seasonal_aridity_index, absent from that focused
native serializer. A fixed prescribed 0.2 is attached solely as the campaign
terrain-cost descriptor; it is not claimed to be a climate-derived estimate.
"""
from support.native_social_worlds import annotated_environment_social_world
from magic_geo.history_dynamics import enrich_world_with_population_history
from magic_geo.economy_dynamics import enrich_world_with_economy_history


def campaign_source_world(name):
    world=annotated_environment_social_world(name)
    for cell in world['cells']:
        cell['seasonal_aridity_index']=0.2
    enrich_world_with_population_history(world)
    enrich_world_with_economy_history(world)
    return world


def campaign_public_world(name):
    from magic_geo.logistics_availability import enrich_available_logistics
    world=campaign_source_world(name)
    enrich_available_logistics(world)
    return world
