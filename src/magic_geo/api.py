from __future__ import annotations

from pathlib import Path
from typing import Any

from .aquifer_resources import enrich_world_with_aquifer_resources
from .biome_dynamics import enrich_world_with_biome_diagnostics
from .biome_ecotones import enrich_world_with_biome_ecotones
from .biome_realism import enrich_world_with_biome_realism
from .boundary_geometry import (
    enrich_world_with_boundary_geometry,
    enrich_world_with_physical_boundary_geometry,
)
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
from .geo_evolution_provenance import enrich_world_with_geo_evolution_provenance
from .graph_diagnostics import (
    enrich_world_with_graph_diagnostics,
    enrich_world_with_physical_graph_diagnostics,
)
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
from .planet_parameters import planet_parameter_snapshot
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


# Native geo-only generation skips civilization simulation. The serializer
# retains stable empty/default schema fields, so the Python geo API removes
# those placeholders before any natural-system enricher can observe them.
NATIVE_CIVILIZATION_TOP_LEVEL_FIELDS = frozenset(
    {
        "borders",
        "conflicts",
        "cultures",
        "dynasties",
        "historical_eras",
        "historical_events",
        "language_regions",
        "political_regions",
        "population_regions",
        "routes",
        "ruins",
        "sacred_areas",
        "settlements",
        "territorial_snapshots",
        "trade_flows",
    }
)

NATIVE_CIVILIZATION_CELL_FIELDS = frozenset(
    {
        "culture_region_id",
        "language_region_id",
        "political_region_id",
        "settlement_score",
    }
)

NATIVE_CIVILIZATION_SUMMARY_FIELDS = frozenset(
    {
        "border_segment_count",
        "border_total_length_km",
        "conflict_count",
        "culturally_assigned_land_fraction",
        "culture_region_count",
        "dynastic_change_count",
        "dynastic_lineage_count",
        "dynasty_count",
        "dynasty_root_count",
        "dynasty_successor_link_count",
        "estimated_world_population",
        "high_economic_disruption_conflict_count",
        "high_intensity_conflict_count",
        "historical_era_count",
        "historical_event_count",
        "interregional_trade_fraction",
        "language_lineage_count",
        "language_region_count",
        "largest_culture_area_km2",
        "largest_region_area_km2",
        "linguistically_assigned_land_fraction",
        "max_conflict_casualty_rate",
        "max_dynasty_lineage_depth",
        "mean_conflict_casualty_rate",
        "mean_conflict_economic_disruption_index",
        "mean_conflict_intensity",
        "mean_conflict_logistics_strain_index",
        "mean_cultural_continuity",
        "mean_dynastic_continuity_index",
        "mean_historical_instability",
        "mean_inherited_phonology_fraction",
        "mean_language_change_rate",
        "mean_phonological_complexity",
        "mean_population_pressure",
        "mean_snapshot_boundary_perimeter_km",
        "mean_snapshot_compactness_index",
        "mean_snapshot_fragmentation_index",
        "mean_snapshot_geometry_quality",
        "mean_snapshot_polygon_area_error_fraction",
        "mean_sound_shift_index",
        "mean_trade_friction",
        "mean_war_duration_years",
        "migration_event_count",
        "natural_border_fraction",
        "politically_assigned_land_fraction",
        "political_region_count",
        "population_region_count",
        "route_count",
        "ruin_count",
        "sacred_area_count",
        "settlement_count",
        "snapshot_polygon_region_count",
        "snapshot_region_record_count",
        "territorial_snapshot_count",
        "top_settlement_score",
        "total_mobilized_population",
        "trade_flow_count",
        "trade_total_volume_index",
    }
)


def backend_info() -> dict[str, Any]:
    from .native import backend_info as native_backend_info

    return native_backend_info()


def generate_world(config: WorldConfig) -> dict[str, Any]:
    from .native import generate_world as native_generate_world

    world = native_generate_world(config_to_native(config))
    # Python enrichers consume this snapshot, so expose it before the first one
    # runs rather than waiting for the later planet-realism diagnostics.
    world["planet_parameters"] = planet_parameter_snapshot(config.planet)
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


def _strip_native_civilization_outputs(world: dict[str, Any]) -> None:
    for field in NATIVE_CIVILIZATION_TOP_LEVEL_FIELDS:
        world.pop(field, None)

    summary = world.get("summary")
    if isinstance(summary, dict):
        for field in NATIVE_CIVILIZATION_SUMMARY_FIELDS:
            summary.pop(field, None)

    cells = world.get("cells")
    if isinstance(cells, list):
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            for field in NATIVE_CIVILIZATION_CELL_FIELDS:
                cell.pop(field, None)


def generate_geo_world(config: WorldConfig) -> dict[str, Any]:
    """Generate and enrich a world containing natural systems only.

    Native civilization simulation is skipped. Stable empty/default
    civilization schema fields are removed before enrichment so mixed natural
    models consistently take their documented no-human defaults.
    """
    from .native import generate_geo_world as native_generate_geo_world

    if not config.output.include_cells:
        raise ValueError(
            "generate_geo_world requires output.include_cells=true because "
            "natural enrichers and layer validation consume per-cell state"
        )

    world = native_generate_geo_world(config_to_native(config))
    _strip_native_civilization_outputs(world)
    world["generation_scope"] = "geo_only"
    world["planet_parameters"] = planet_parameter_snapshot(config.planet)

    # Geometry and physical topology.
    enrich_world_with_mesh_lod(world)
    enrich_world_with_spherical_index(world)
    enrich_world_with_cell_geometry(world)

    # Tectonic and geologic diagnostics consume the native crust simulation.
    enrich_world_with_geology_realism(world)
    enrich_world_with_tectonic_zones(world)
    enrich_world_with_fault_systems(world)

    # Sea state and ocean circulation precede atmospheric refinements.
    enrich_world_with_sea_level_diagnostics(world)
    enrich_world_with_ocean_circulation(world)

    # Equilibrium and seasonal climate layers.
    enrich_world_with_climate_continentality(world)
    enrich_world_with_seasonal_climate_history(world)
    enrich_world_with_climate_energy_balance(world, config.planet)
    enrich_world_with_planet_realism(world, config.planet)
    enrich_world_with_climate_realism(world)

    # Surface water routing and sediment evolution.
    enrich_world_with_lake_overflow_history(world)
    enrich_world_with_watershed_diagnostics(world)
    enrich_world_with_hydrology_realism(world)
    enrich_world_with_sediment_routing_history(world)
    enrich_world_with_river_network_evolution(world)
    enrich_world_with_sediment_transport_history(world)
    enrich_world_with_sequence_stratigraphy(world)

    # Cryosphere, soils, and climate-conditioned biomes.
    enrich_world_with_ice_sheet_history(world)
    enrich_world_with_ice_sheet_stability(world)
    enrich_world_with_ice_flowline_history(world)
    enrich_world_with_soil_diagnostics(world)
    enrich_world_with_permafrost_diagnostics(world)
    enrich_world_with_glacial_landforms(world)
    enrich_world_with_biome_diagnostics(world)
    enrich_world_with_biome_ecotones(world)
    enrich_world_with_biome_realism(world)

    # Soil- and biome-dependent water systems.
    enrich_world_with_aquifer_resources(world)
    enrich_world_with_hydrology_budget(world)
    enrich_world_with_wetland_diagnostics(world)
    enrich_world_with_groundwater_flow(world)
    enrich_world_with_river_channel_morphology(world)
    enrich_world_with_river_hydraulics(world)
    enrich_world_with_karst_diagnostics(world)

    # Ecosystems and disturbances.  Settlement/port inputs are deliberately
    # absent, so mixed models follow their natural baseline branches.
    enrich_world_with_ecosystem_dynamics(world)
    enrich_world_with_reef_diagnostics(world)
    enrich_world_with_species_ranges(world)
    enrich_world_with_wildfire_disturbance(world)

    # Natural-resource formation and occurrence diagnostics.
    enrich_world_with_resource_deposits(world)
    enrich_world_with_ore_genesis(world)
    enrich_world_with_sedimentary_resource_systems(world)
    enrich_world_with_petroleum_migration(world)
    enrich_world_with_commodity_occurrences(world)

    # Only physical graph and boundary products are valid in this scope.
    enrich_world_with_physical_graph_diagnostics(world)
    enrich_world_with_physical_boundary_geometry(world)
    enrich_world_with_geo_evolution_provenance(world)
    return world


def generate_from_file(path: Path) -> dict[str, Any]:
    return generate_world(load_config(path))
