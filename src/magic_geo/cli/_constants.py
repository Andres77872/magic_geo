"""Domain thresholds and model identifiers shared by the CLI validators."""

from __future__ import annotations


HYDROLOGIC_SURFACE_MODEL = "priority_flood_fill_with_deterministic_flat_gradient_v1"
HYDROLOGIC_FLAT_GRADIENT_STEP_M = 0.001
RIVER_EXTRACTION_MODEL = (
    "flow_accumulation_percentile_on_conditioned_hydrologic_surface_v1"
)
NUMERIC_DEPRESSION_CORRECTION_MODEL = (
    "bounded_mass_conserving_breach_or_zero_material_temporary_lake_with_coupled_recomputation_v3"
)
NUMERIC_DEPRESSION_TEMPORARY_LAKE_METHOD = (
    "zero_material_temporary_numeric_lake_deferral_v1"
)
NUMERIC_DEPRESSION_BREACH_METHOD = (
    "bounded_mass_conserving_breach_with_local_deposition_v1"
)
NUMERIC_DEPRESSION_CORRECTION_MAX_PASSES = 16
NUMERIC_DEPRESSION_FILL_DEPTH_TOLERANCE_M = 1.0e-9
NUMERIC_DEPRESSION_CORRECTION_SELECTION_MODEL = (
    "lower_volume_full_cell_breach_with_50m_depth_bound_else_temporary_lake_v3"
)
NUMERIC_DEPRESSION_BREACH_DIAGNOSTIC_MODEL = (
    "weighted_graph_excavation_proxy_monotone_lower_outlet_v1"
)
NUMERIC_DEPRESSION_BREACH_GRADIENT_STEP_M = 0.001
NUMERIC_DEPRESSION_SELECTED_BREACH_MAX_DEPTH_M = 50.0
NUMERIC_DEPRESSION_BREACH_MASS_TRANSFER_MODEL = (
    "local_excavation_to_nonchannel_depression_deposition_volume_closure_v1"
)
NUMERIC_DEPRESSION_CORRECTION_SELECTION_REASON = (
    "apply_only_lower_volume_depth_bounded_capacity_sufficient_conflict_free_breaches_else_defer_without_material"
)
FLUVIAL_SEDIMENT_ROUTING_MODEL = (
    "topological_capacity_limited_fluvial_sediment_routing_v1"
)
FLUVIAL_SEDIMENT_MIN_TRANSPORT_CAPACITY_FRACTION = 0.90
FLUVIAL_SEDIMENT_MAX_TRANSPORT_CAPACITY_FRACTION = 0.995
FLUVIAL_SEDIMENT_LAKE_TRAP_FRACTION = 0.35
FLUVIAL_SEDIMENT_CLOSED_LAKE_TRAP_FRACTION = 0.65
FLUVIAL_SEDIMENT_OPEN_OCEAN_DEPOSITION_FRACTION = 0.12
FLUVIAL_SEDIMENT_SHELF_DEPOSITION_FRACTION = 0.55
FLUVIAL_SEDIMENT_INLAND_SEA_DEPOSITION_FRACTION = 0.30
HILLSLOPE_SEDIMENT_TRANSPORT_MODEL = (
    "pairwise_lithology_dependent_volume_conserving_hillslope_transport_v2"
)
HILLSLOPE_SEDIMENT_MAX_EFFECTIVE_DIFFUSIVITY = 0.45
HILLSLOPE_SEDIMENT_LITHOLOGY_RESISTANCE = {
    "basalt": 0.85,
    "granite": 1.25,
    "limestone": 0.75,
    "sandstone": 0.82,
    "shale": 0.62,
    "volcanic": 0.95,
    "metamorphic": 1.35,
}
GLACIAL_SEDIMENT_TRANSPORT_MODEL = (
    "downhill_area_conserving_glacial_sediment_transport_v2"
)
GLACIAL_SEDIMENT_MOBILE_FRACTION = 0.28
SEDIMENT_INVENTORY_MODEL = "finite_alluvium_bedrock_sediment_inventory_v1"
MATURATION_REFERENCE_TIMESTEP_MA = 5.0
NOMINAL_TIME_MODEL = "configured_maturation_timestep_nominal_elapsed_time_v1"
NOMINAL_TIME_BASIS = (
    "configured_maturation_timestep_ma_per_erosion_transition_v1"
)
NOMINAL_TIME_SOURCE_PARAMETER = "erosion.maturation_timestep_ma"
ITERATION_PROCESS_ORDER = (
    "{plate_motion->crust_transport->crust_evolution->"
    "precommit_tendency_evaluation[tectonic_elevation+hillslope_sediment+"
    "stream_power_incision;prior_stabilized_surface_hydrology]->"
    "provisional_terrain_composition->fluvial_sediment_routing["
    "prior_flow_graph+provisional_accommodation]->"
    "finite_alluvium_bedrock_inventory_and_terrain_commit->"
    "(sea_level->climate->causal_water_budget->hydrology->"
    "numeric_depression_correction)*until_stable}*"
    "configured_erosion_iterations->cryosphere_state->"
    "glacial_sediment_transport->"
    "finite_alluvium_bedrock_inventory_and_terrain_commit->"
    "(sea_level->climate->causal_water_budget->hydrology->"
    "numeric_depression_correction)*until_stable->cryosphere_state_recompute"
)
EROSION_TRANSITION_COUPLING_SEMANTICS = (
    "hillslope_and_stream_use_prior_stabilized_surface_and_hydrology_with_"
    "updated_crust_state;tectonic_hillslope_stream_tendencies_are_combined_"
    "before_terrain_commit;fluvial_routing_uses_prior_flow_graph_and_"
    "provisional_terrain_accommodation"
)
NOMINAL_TIME_RECORD_FIELDS = {
    "nominal_time_model",
    "nominal_time_unit",
    "nominal_time_basis",
    "nominal_time_source_parameter",
    "nominal_time_role",
    "nominal_interval_start_ma",
    "nominal_interval_end_ma",
    "nominal_interval_duration_ma",
    "nominal_elapsed_time_ma",
    "advances_nominal_time",
    "nominal_time_calibrated",
    "physical_time_resolved",
}
HYDROLOGIC_WATER_BUDGET_MODEL = "causal_land_climate_loss_partition_v1"
HYDROLOGIC_PET_TEMPERATURE_OFFSET_C = 8.0
HYDROLOGIC_PET_SCALE_MM_Y_PER_C = 31.0
HYDROLOGIC_CLIMATE_LOSS_FRACTION = 0.68
HYDROLOGIC_INFILTRATION_BASE_SHARE = 0.10
HYDROLOGIC_INFILTRATION_CAPACITY_SHARE = 0.50
HYDROLOGIC_MIN_INFILTRATION_CAPACITY = 0.02
HYDROLOGIC_MAX_INFILTRATION_CAPACITY = 0.90
HYDROLOGIC_LITHOLOGY_PERMEABILITY = {
    "basalt": 0.46,
    "granite": 0.31,
    "limestone": 0.82,
    "sandstone": 0.76,
    "shale": 0.18,
    "volcanic": 0.48,
    "metamorphic": 0.30,
}
HYDROLOGIC_LITHOLOGY_NAMES = tuple(HYDROLOGIC_LITHOLOGY_PERMEABILITY)
GROUNDWATER_RECHARGE_MODEL = "infiltration_bounded_aquifer_recharge_v1"
GROUNDWATER_MIN_RECHARGE_FRACTION = 0.05
GROUNDWATER_MAX_RECHARGE_FRACTION = 0.85
AQUIFER_RESOURCE_MODEL = "finite_recharge_causal_aquifer_resources_v1"
AQUIFER_MIN_SYSTEM_PRODUCTIVITY_INDEX = 0.18
AQUIFER_MIN_SYSTEM_RECHARGE_MM_Y = 25.0
GROUNDWATER_FLOW_MODEL = "descending_head_recharge_conserving_groundwater_flow_v1"
GROUNDWATER_FLOW_MINIMUM_RECEIVER_HEAD_DROP_M = 0.5
GROUNDWATER_FLOW_GRADIENT_SCALE_M = 900.0
GROUNDWATER_FLOW_MAXIMUM_LATERAL_EXPORT_FRACTION = 0.82
GROUNDWATER_ALLUVIAL_LANDFORMS = {
    "floodplain",
    "delta",
    "river_valley",
    "coastal_plain",
    "lacustrine_basin",
    "glacial_lake",
}
GROUNDWATER_LITHOLOGY_PERMEABILITY = {
    "limestone": 0.82,
    "sandstone": 0.76,
    "basalt": 0.44,
    "volcanic": 0.48,
    "granite": 0.30,
    "metamorphic": 0.28,
    "shale": 0.18,
}
RIVER_CHANNEL_MORPHOLOGY_MODEL = (
    "causal_flow_sediment_wetland_baseflow_channel_morphology_v1"
)
RIVER_CHANNEL_LOWLAND_FORMS = {
    "delta",
    "floodplain",
    "river_valley",
    "coastal_plain",
    "lacustrine_basin",
}
RIVER_CHANNEL_CLASSES = {
    "non_channel",
    "small_headwater",
    "incised_bedrock_channel",
    "braided_sediment_rich_channel",
    "deep_alluvial_channel",
    "navigable_lowland_channel",
    "ephemeral_wadi",
    "glacial_outwash_channel",
}
RIVER_HYDRAULICS_MODEL = "manning_blended_diagnostic_river_hydraulics_v1"
RIVER_HYDRAULICS_WATER_DENSITY_KG_M3 = 1000.0
RIVER_HYDRAULICS_NAVIGABILITY_THRESHOLD = 0.55
RIVER_HYDRAULICS_HIGH_SHEAR_STRESS_PA = 120.0
RIVER_HYDRAULICS_ROUGHNESS_BY_CLASS = {
    "small_headwater": 0.045,
    "incised_bedrock_channel": 0.038,
    "braided_sediment_rich_channel": 0.048,
    "deep_alluvial_channel": 0.032,
    "navigable_lowland_channel": 0.030,
    "ephemeral_wadi": 0.052,
    "glacial_outwash_channel": 0.046,
}
NAVIGABILITY_MODEL = "causal_channel_hydraulic_coastal_navigability_v1"
NAVIGABILITY_THRESHOLD = 0.52
NAVIGABILITY_HIGH_HARBOR_THRESHOLD = 0.62
NAVIGABILITY_TRANSPORT_CHOKEPOINT_THRESHOLD = 0.55
NAVIGABILITY_MARINE_WATER_TYPES = {
    "ocean",
    "continental_shelf",
    "inland_sea",
}
PORT_SITE_MODEL = "causal_navigability_coastal_port_site_selection_v1"
PORT_SITE_THRESHOLD = 0.58
PORT_PROTECTED_BAY_THRESHOLD = 0.55
PORT_RIVER_MOUTH_THRESHOLD = 0.50
PORT_STRAIT_ACCESS_THRESHOLD = 0.55
ROUTE_CORRIDOR_MODEL = "causal_feature_weighted_dijkstra_route_corridors_v1"
ROUTE_FEATURE_THRESHOLD = 0.45
ROUTE_MOUNTAIN_LANDFORMS = {
    "mountain",
    "mountain_range",
    "volcanic_arc",
    "highland",
    "ridge",
    "glacial_valley",
}
ROUTE_RIVER_VALLEY_LANDFORMS = {
    "delta",
    "floodplain",
    "river_valley",
    "alluvial_fan",
    "wetland",
}
ROUTE_DESERT_BIOMES = {
    "hot_desert",
    "cold_desert",
    "desert",
    "semi_arid_desert",
}
SETTLEMENT_SELECTION_MODEL = (
    "causal_native_score_local_max_separated_settlement_selection_v1"
)
ROUTE_NETWORK_MODEL = "causal_endpoint_barrier_ranked_route_network_v1"
SETTLEMENT_SCORE_THRESHOLD = 0.48
SETTLEMENT_TARGET_CELL_DIVISOR = 180
SETTLEMENT_TARGET_MINIMUM = 8
SETTLEMENT_TARGET_MAXIMUM = 64
SETTLEMENT_MINIMUM_SEPARATION_FACTOR = 2.4
ROUTE_LINKS_PER_SETTLEMENT = 2
SETTLEMENT_MINING_RESOURCES = {
    "volcanic_arc_metals",
    "craton_iron_gold",
    "placer_metals",
    "geothermal",
}
SETTLEMENT_DESERT_BIOMES = {"cold_desert", "hot_desert"}
POLITICAL_REGION_MODEL = "causal_capital_barrier_partition_political_regions_v1"
POLITICAL_BORDER_MODEL = "causal_adjacent_region_terrain_border_segments_v1"
TRADE_FLOW_MODEL = "causal_route_endpoint_complement_trade_flows_v1"
POLITICAL_BIOME_ORDER = (
    "ocean",
    "continental_shelf",
    "lake",
    "ice_cap",
    "tundra",
    "boreal_forest",
    "temperate_forest",
    "temperate_grassland",
    "mediterranean_scrub",
    "cold_desert",
    "hot_desert",
    "savanna",
    "tropical_seasonal_forest",
    "tropical_rainforest",
    "alpine",
    "wetland",
)
POLITICAL_RESOURCE_ORDER = (
    "none",
    "volcanic_arc_metals",
    "craton_iron_gold",
    "sedimentary_fuels",
    "evaporites",
    "placer_metals",
    "geothermal",
    "fertile_alluvium",
    "coastal_fisheries",
)
TRADE_RESOURCE_PRIORITY = {
    "volcanic_arc_metals": 6,
    "craton_iron_gold": 6,
    "placer_metals": 6,
    "sedimentary_fuels": 5,
    "evaporites": 5,
    "geothermal": 4,
    "fertile_alluvium": 3,
    "coastal_fisheries": 2,
    "none": 0,
}
