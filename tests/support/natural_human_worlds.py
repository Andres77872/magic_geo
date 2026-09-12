"""Ordered natural and human-tail upgrades of complete retained worlds."""

from copy import deepcopy
from functools import lru_cache

from magic_geo import api
from support.ecology_worlds import current_ecology_world_readonly
from support.natural_water_worlds import upgrade_natural_water


def upgrade_natural_human_world(world):
    """Recompute the physical water chain and every following Python consumer."""
    upgrade_natural_water(world)
    for key, producer in (
        ("navigability_model", api.enrich_world_with_navigability_diagnostics),
        ("port_site_model", api.enrich_world_with_port_sites),
        ("route_corridor_model", api.enrich_world_with_route_corridors),
    ):
        del world[key]
        del world["summary"][key]
        producer(world)
    # Ports and corridors precede reef links, resources and societal evidence.
    api._enrich_ecosystems_and_resources(world)
    for producer in (
        api.enrich_world_with_land_use_zones, api.enrich_world_with_natural_frontiers,
        api.enrich_world_with_worldbuilding_realism, api.enrich_world_with_population_history,
        api.enrich_world_with_economy_history, api.enrich_world_with_dynasty_genealogy,
        api.enrich_world_with_logistics_history, api.enrich_world_with_demographic_agents,
        api.enrich_world_with_market_clearing, api.enrich_world_with_graph_diagnostics,
        api.enrich_world_with_boundary_geometry, api.enrich_world_with_phonology_history,
    ):
        producer(world)
    return world


@lru_cache(maxsize=None)
def current_natural_human_world_readonly():
    return upgrade_natural_human_world(deepcopy(current_ecology_world_readonly()))
