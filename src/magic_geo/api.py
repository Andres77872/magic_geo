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
from .seasonal_config import SeasonalWorldConfig
from .grounded_ice_validation import require_grounded_ice
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
from .native_social_public_validation import (
    NATIVE_SOCIAL_PUBLIC_MODELS, RECORDED_SUMMARY_FIELDS,
)
from .ocean_circulation import enrich_world_with_ocean_circulation
from .ore_genesis import enrich_world_with_ore_genesis
from .permafrost_diagnostics import enrich_world_with_permafrost_diagnostics
from .phonology_history import enrich_world_with_phonology_history
from .planet_realism import enrich_world_with_planet_realism
from .political_geography import enrich_world_with_political_geography_models
from .port_sites import enrich_world_with_port_sites
from .planet_parameters import planet_parameter_snapshot
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
) | NATIVE_SOCIAL_PUBLIC_MODELS | {"native_social_availability"}

NATIVE_CIVILIZATION_CELL_FIELDS = frozenset(
    {
        "culture_region_id",
        "language_region_id",
        "political_region_id",
        "settlement_score",
        "settlement_climate_supported",
        "settlement_climate_temperature_c",
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
) | NATIVE_SOCIAL_PUBLIC_MODELS | RECORDED_SUMMARY_FIELDS


def backend_info() -> dict[str, Any]:
    from .native import backend_info as native_backend_info

    return native_backend_info()


def _require_configured_planet_snapshot(
    world: dict[str, Any],
    config: WorldConfig,
) -> None:
    if world.get("planet_parameters") != planet_parameter_snapshot(config.planet):
        raise RuntimeError(
            "native planet_parameters do not match the configured planet snapshot"
        )


def _enrich_physical_foundation(world: dict[str, Any], config: WorldConfig) -> None:
    """Enrich shared natural prerequisites in producer-before-consumer order.

    Both entrypoints use the same sequence. Native generation has already
    evolved relief, climate, hydrology, soils, biomes, and resources; these
    Python layers diagnose that final state and add linked derived records.
    """
    require_grounded_ice(world)
    enrich_world_with_mesh_lod(world)
    enrich_world_with_spherical_index(world)
    enrich_world_with_cell_geometry(world)
    enrich_world_with_geology_realism(world)
    enrich_world_with_tectonic_zones(world)
    enrich_world_with_fault_systems(world)
    enrich_world_with_sea_level_diagnostics(world)
    enrich_world_with_ocean_circulation(world)
    enrich_world_with_climate_continentality(world)
    enrich_world_with_seasonal_climate_history(world)
    enrich_world_with_climate_energy_balance(world, config.planet)
    enrich_world_with_planet_realism(world, config.planet)
    enrich_world_with_climate_realism(world)
    enrich_world_with_lake_overflow_history(world)
    enrich_world_with_watershed_diagnostics(world)
    enrich_world_with_hydrology_realism(world)
    enrich_world_with_sediment_routing_history(world)
    enrich_world_with_river_network_evolution(world)
    enrich_world_with_sediment_transport_history(world)
    enrich_world_with_sequence_stratigraphy(world)
    enrich_world_with_ice_sheet_history(world)
    enrich_world_with_ice_sheet_stability(world)
    enrich_world_with_ice_flowline_history(world)
    enrich_world_with_soil_diagnostics(world)
    # Publish seasonal biome diagnostics before the linked frozen-ground
    # records, which also consume soil moisture and organic matter.
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
    enrich_world_with_karst_diagnostics(world)


def _enrich_ecosystems_and_resources(world: dict[str, Any]) -> None:
    """Complete soil/water-dependent ecosystems and geologic occurrences.

    In a full world, ports must exist before reef records link nearby ports.
    In a geo-only world those optional human inputs have been removed.
    """
    enrich_world_with_ecosystem_dynamics(world)
    enrich_world_with_reef_diagnostics(world)
    enrich_world_with_species_ranges(world)
    enrich_world_with_wildfire_disturbance(world)
    enrich_world_with_resource_deposits(world)
    enrich_world_with_ore_genesis(world)
    enrich_world_with_sedimentary_resource_systems(world)
    enrich_world_with_petroleum_migration(world)
    enrich_world_with_commodity_occurrences(world)


def generate_world(config: WorldConfig) -> dict[str, Any]:
    if isinstance(config, SeasonalWorldConfig):
        config = SeasonalWorldConfig.model_validate(config, strict=True)
        from .native import generate_seasonal_world as native_generate_world
    else:
        from .native import generate_world as native_generate_world

    # include_cells is an output choice, not permission to omit prerequisite
    # simulation data. Enrichers need the complete state even for summary-only
    # exports; suppress cells only after all linked records have been built.
    native_config = config_to_native(config)
    native_config["output"]["include_cells"] = True
    world = native_generate_world(native_config)
    _require_configured_planet_snapshot(world, config)
    _enrich_physical_foundation(world, config)
    enrich_world_with_settlement_route_models(world)
    enrich_world_with_political_geography_models(world)
    enrich_world_with_cultural_geography_models(world)
    enrich_world_with_historical_geography_model(world)
    enrich_world_with_civilization_geography_models(world)
    enrich_world_with_territorial_geography_model(world)
    enrich_world_with_navigability_diagnostics(world)
    enrich_world_with_port_sites(world)
    enrich_world_with_route_corridors(world)
    _enrich_ecosystems_and_resources(world)
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
    if not config.output.include_cells:
        world["cells"] = []
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
    models use their declared geographic scope. Current resource economics are
    unavailable here; separately named geographic baselines remain numeric.
    """
    if isinstance(config, SeasonalWorldConfig):
        config = SeasonalWorldConfig.model_validate(config, strict=True)
        from .native import generate_seasonal_geo_world as native_generate_geo_world
    else:
        from .native import generate_geo_world as native_generate_geo_world

    if not config.output.include_cells:
        raise ValueError(
            "generate_geo_world requires output.include_cells=true because "
            "natural enrichers and layer validation consume per-cell state"
        )

    world = native_generate_geo_world(config_to_native(config))
    _require_configured_planet_snapshot(world, config)
    _strip_native_civilization_outputs(world)
    world["generation_scope"] = "geo_only"

    _enrich_physical_foundation(world, config)
    _enrich_ecosystems_and_resources(world)

    # Only physical graph and boundary products are valid in this scope.
    enrich_world_with_physical_graph_diagnostics(world)
    enrich_world_with_physical_boundary_geometry(world)
    enrich_world_with_geo_evolution_provenance(world)
    return world


def generate_from_file(path: Path) -> dict[str, Any]:
    """Load a YAML file and generate the complete world feature set."""

    return generate_world(load_config(path))


def generate_geo_from_file(path: Path) -> dict[str, Any]:
    """Load a YAML file and generate only natural-geography systems."""

    return generate_geo_world(load_config(path))
