from __future__ import annotations

from pathlib import Path
from typing import Any

from .aquifer_resources import enrich_world_with_aquifer_resources
from .biome_dynamics import enrich_world_with_biome_diagnostics
from .biome_ecotones import enrich_world_with_biome_ecotones
from .biome_realism import enrich_world_with_biome_realism
from .boundary_geometry import enrich_world_with_boundary_geometry
from .cell_geometry import enrich_world_with_cell_geometry
from .climate_continentality import enrich_world_with_climate_continentality
from .climate_energy import enrich_world_with_climate_energy_balance
from .climate_dynamics import enrich_world_with_seasonal_climate_history
from .climate_realism import enrich_world_with_climate_realism
from .commodity_resources import enrich_world_with_commodity_occurrences
from .civilization_geography import enrich_world_with_civilization_geography_models
from .cultural_geography import enrich_world_with_cultural_geography_models
from .config import WorldConfig, config_to_native, load_config
from .cryosphere_dynamics import enrich_world_with_ice_sheet_history
from .cryosphere_flow import enrich_world_with_ice_flowline_history
from .cryosphere_stability import enrich_world_with_ice_sheet_stability
from .demographic_agents import enrich_world_with_demographic_agents
from .dynasty_genealogy import enrich_world_with_dynasty_genealogy
from .economy_dynamics import enrich_world_with_economy_history
from .ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
from .fault_systems import enrich_world_with_fault_systems
from .geology_realism import enrich_world_with_geology_realism
from .glacial_landforms import enrich_world_with_glacial_landforms
from .graph_diagnostics import enrich_world_with_graph_diagnostics
from .groundwater_flow import enrich_world_with_groundwater_flow
from .historical_geography import enrich_world_with_historical_geography_model
from .history_dynamics import enrich_world_with_population_history
from .hydrology_dynamics import enrich_world_with_lake_overflow_history
from .hydrology_budget import enrich_world_with_hydrology_budget
from .hydrology_realism import enrich_world_with_hydrology_realism
from .karst_diagnostics import enrich_world_with_karst_diagnostics
from .land_use_zones import enrich_world_with_land_use_zones
from .logistics_history import enrich_world_with_logistics_history
from .market_clearing import enrich_world_with_market_clearing
from .mesh_lod import enrich_world_with_mesh_lod
from .natural_frontiers import enrich_world_with_natural_frontiers
from .navigability_diagnostics import enrich_world_with_navigability_diagnostics
from .ocean_circulation import enrich_world_with_ocean_circulation
from .ore_genesis import enrich_world_with_ore_genesis
from .permafrost_diagnostics import enrich_world_with_permafrost_diagnostics
from .phonology_history import enrich_world_with_phonology_history
from .planet_realism import enrich_world_with_planet_realism
from .political_geography import enrich_world_with_political_geography_models
from .port_sites import enrich_world_with_port_sites
from .petroleum_migration import enrich_world_with_petroleum_migration
from .reef_diagnostics import enrich_world_with_reef_diagnostics
from .river_network_evolution import enrich_world_with_river_network_evolution
from .river_channel_morphology import enrich_world_with_river_channel_morphology
from .river_hydraulics import enrich_world_with_river_hydraulics
from .resource_dynamics import enrich_world_with_resource_deposits
from .route_corridors import enrich_world_with_route_corridors
from .sea_level_diagnostics import enrich_world_with_sea_level_diagnostics
from .sediment_dynamics import enrich_world_with_sediment_transport_history
from .sediment_routing import enrich_world_with_sediment_routing_history
from .sedimentary_resource_systems import enrich_world_with_sedimentary_resource_systems
from .sequence_stratigraphy import enrich_world_with_sequence_stratigraphy
from .settlement_routes import enrich_world_with_settlement_route_models
from .soil_dynamics import enrich_world_with_soil_diagnostics
from .species_ranges import enrich_world_with_species_ranges
from .spherical_index import enrich_world_with_spherical_index
from .tectonic_zones import enrich_world_with_tectonic_zones
from .territorial_geography import enrich_world_with_territorial_geography_model
from .watershed_diagnostics import enrich_world_with_watershed_diagnostics
from .wetland_diagnostics import enrich_world_with_wetland_diagnostics
from .wildfire_disturbance import enrich_world_with_wildfire_disturbance
from .worldbuilding_realism import enrich_world_with_worldbuilding_realism


def backend_info() -> dict[str, Any]:
    from .native import backend_info as native_backend_info

    return native_backend_info()


def generate_world(config: WorldConfig) -> dict[str, Any]:
    from .native import generate_world as native_generate_world

    world = native_generate_world(config_to_native(config))
    enrich_world_with_mesh_lod(world)
    enrich_world_with_spherical_index(world)
    enrich_world_with_cell_geometry(world)
    enrich_world_with_sea_level_diagnostics(world)
    enrich_world_with_ocean_circulation(world)
    enrich_world_with_climate_continentality(world)
    enrich_world_with_geology_realism(world)
    enrich_world_with_tectonic_zones(world)
    enrich_world_with_fault_systems(world)
    enrich_world_with_seasonal_climate_history(world)
    enrich_world_with_climate_energy_balance(world, config.planet)
    enrich_world_with_planet_realism(world, config.planet)
    enrich_world_with_climate_realism(world)
    enrich_world_with_lake_overflow_history(world)
    enrich_world_with_watershed_diagnostics(world)
    enrich_world_with_sediment_routing_history(world)
    enrich_world_with_hydrology_realism(world)
    enrich_world_with_river_network_evolution(world)
    enrich_world_with_sediment_transport_history(world)
    enrich_world_with_sequence_stratigraphy(world)
    enrich_world_with_ice_sheet_history(world)
    enrich_world_with_ice_sheet_stability(world)
    enrich_world_with_ice_flowline_history(world)
    enrich_world_with_soil_diagnostics(world)
    enrich_world_with_biome_diagnostics(world)
    enrich_world_with_permafrost_diagnostics(world)
    enrich_world_with_glacial_landforms(world)
    enrich_world_with_biome_ecotones(world)
    enrich_world_with_biome_realism(world)
    enrich_world_with_aquifer_resources(world)
    enrich_world_with_hydrology_budget(world)
    enrich_world_with_wetland_diagnostics(world)
    enrich_world_with_groundwater_flow(world)
    enrich_world_with_river_channel_morphology(world)
    enrich_world_with_river_hydraulics(world)
    enrich_world_with_settlement_route_models(world)
    enrich_world_with_political_geography_models(world)
    enrich_world_with_cultural_geography_models(world)
    enrich_world_with_historical_geography_model(world)
    enrich_world_with_civilization_geography_models(world)
    enrich_world_with_territorial_geography_model(world)
    enrich_world_with_navigability_diagnostics(world)
    enrich_world_with_port_sites(world)
    enrich_world_with_route_corridors(world)
    enrich_world_with_karst_diagnostics(world)
    enrich_world_with_ecosystem_dynamics(world)
    enrich_world_with_reef_diagnostics(world)
    enrich_world_with_species_ranges(world)
    enrich_world_with_wildfire_disturbance(world)
    enrich_world_with_resource_deposits(world)
    enrich_world_with_ore_genesis(world)
    enrich_world_with_sedimentary_resource_systems(world)
    enrich_world_with_petroleum_migration(world)
    enrich_world_with_commodity_occurrences(world)
    enrich_world_with_land_use_zones(world)
    enrich_world_with_natural_frontiers(world)
    enrich_world_with_worldbuilding_realism(world)
    enrich_world_with_population_history(world)
    enrich_world_with_economy_history(world)
    enrich_world_with_dynasty_genealogy(world)
    enrich_world_with_logistics_history(world)
    enrich_world_with_demographic_agents(world)
    enrich_world_with_market_clearing(world)
    enrich_world_with_graph_diagnostics(world)
    enrich_world_with_boundary_geometry(world)
    enrich_world_with_phonology_history(world)
    return world


def generate_from_file(path: Path) -> dict[str, Any]:
    return generate_world(load_config(path))
