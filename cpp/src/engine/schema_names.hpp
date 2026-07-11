#pragma once

#include <array>

namespace magic_geo::detail {

inline constexpr std::array<const char*, 9> CRUST_NAMES = {
    "oceanic", "continental", "transitional", "volcanic_arc",
    "craton", "orogen", "rift_basin", "sedimentary_basin", "accreted_terrane",
};
inline constexpr std::array<const char*, 7> LITHOLOGY_NAMES = {
    "basalt", "granite", "limestone", "sandstone", "shale", "volcanic", "metamorphic",
};
inline constexpr std::array<const char*, 5> BOUNDARY_NAMES = {
    "interior", "convergent", "divergent", "transform", "mixed",
};
inline constexpr std::array<const char*, 11> SOIL_NAMES = {
    "none", "thin_mountain", "volcanic", "alluvial", "arid", "tropical",
    "temperate", "boreal", "tundra", "wetland", "saline",
};
inline constexpr std::array<const char*, 16> BIOME_NAMES = {
    "ocean", "continental_shelf", "lake", "ice_cap", "tundra", "boreal_forest",
    "temperate_forest", "temperate_grassland", "mediterranean_scrub", "cold_desert",
    "hot_desert", "savanna", "tropical_seasonal_forest", "tropical_rainforest",
    "alpine", "wetland",
};
inline constexpr std::array<const char*, 9> RESOURCE_NAMES = {
    "none", "volcanic_arc_metals", "craton_iron_gold", "sedimentary_fuels",
    "evaporites", "placer_metals", "geothermal", "fertile_alluvium", "coastal_fisheries",
};
inline constexpr std::array<const char*, 4> ATMOSPHERIC_CELL_NAMES = {
    "tropical_ascent", "subtropical_high", "midlatitude_westerly", "polar_cell",
};
inline constexpr std::array<const char*, 6> WATER_BODY_NAMES = {
    "land", "ocean", "continental_shelf", "inland_sea", "fresh_lake", "saline_basin",
};
inline constexpr std::array<const char*, 20> LANDFORM_NAMES = {
    "open_ocean", "continental_shelf", "inland_sea", "lacustrine_basin",
    "salt_flat", "ice_field", "mountain_belt", "volcanic_arc",
    "rift_valley", "trench", "river_valley", "floodplain",
    "delta", "alluvial_fan", "coastal_plain", "stable_lowland",
    "fjord", "glacial_valley", "moraine", "glacial_lake",
};
inline constexpr std::array<const char*, 6> SETTLEMENT_TYPE_NAMES = {
    "river_city", "port", "mining_town", "agricultural_town", "oasis", "frontier_town",
};
inline constexpr std::array<const char*, 4> ROUTE_TYPE_NAMES = {
    "overland", "river_corridor", "coastal_sea", "mountain_pass",
};
inline constexpr std::array<const char*, 5> WATERSHED_OUTLET_NAMES = {
    "ocean", "lake", "saline_basin", "inland_sea", "closed_land",
};
inline constexpr std::array<const char*, 6> DEPRESSION_POLICY_NAMES = {
    "none", "corrected_numeric", "preserved_geologic", "overflow_spill", "dry_closed",
    "temporary_numeric_lake",
};
inline constexpr std::array<const char*, 6> POLITICAL_REGION_TYPE_NAMES = {
    "river_realm", "maritime_league", "mountain_march",
    "mining_domain", "agrarian_state", "frontier_territory",
};
inline constexpr std::array<const char*, 6> BORDER_TYPE_NAMES = {
    "open_lowland", "river", "mountain", "desert", "ice", "coastal",
};
inline constexpr std::array<const char*, 8> CULTURE_TYPE_NAMES = {
    "river_valley", "maritime", "highland", "desert_oasis",
    "agrarian_lowland", "mining_frontier", "boreal_frontier", "forest_realm",
};
inline constexpr std::array<const char*, 6> LANGUAGE_FAMILY_NAMES = {
    "riverine", "coastal", "highland", "arid", "lowland", "frontier",
};
inline constexpr std::array<const char*, 6> SACRED_AREA_TYPE_NAMES = {
    "mountain_shrine", "spring_oracle", "sacred_grove",
    "volcanic_sanctuary", "ancestral_coast", "desert_sanctuary",
};
inline constexpr std::array<const char*, 6> RUIN_TYPE_NAMES = {
    "ruined_city", "abandoned_mine", "desert_outpost",
    "mountain_fortress", "old_harbor", "glacial_relic",
};
inline constexpr std::array<const char*, 6> ABANDONMENT_REASON_NAMES = {
    "aridity", "tectonic_hazard", "glaciation",
    "salinization", "trade_decline", "frontier_isolation",
};
inline constexpr std::array<const char*, 7> HISTORY_EVENT_TYPE_NAMES = {
    "state_foundation", "dynastic_change", "migration",
    "language_split", "trade_boom", "sacred_founding", "ruin_abandonment",
};
inline constexpr std::array<const char*, 4> HISTORICAL_PROCESS_NAMES = {
    "founding", "expansion", "fragmentation", "integration",
};
inline constexpr std::array<const char*, 6> CONFLICT_CAUSE_NAMES = {
    "water_rights", "fertile_plain", "mining_claim",
    "trade_chokepoint", "border_fragmentation", "sacred_site",
};
inline constexpr std::array<const char*, 5> CONFLICT_OUTCOME_NAMES = {
    "stalemate", "region_a_victory", "region_b_victory",
    "border_shift", "exhaustion",
};
inline constexpr std::array<const char*, 6> DYNASTY_COLLAPSE_REASON_NAMES = {
    "continuity", "succession_crisis", "resource_shock",
    "trade_decline", "migration_pressure", "conflict_defeat",
};
inline constexpr std::array<const char*, 4> CALIBRATION_DATASET_NAMES = {
    "ETOPO_reference_range", "WorldClim_reference_range",
    "HydroSHEDS_reference_range", "NaturalEarth_reference_range",
};
inline constexpr std::array<const char*, 5> CALIBRATION_LAYER_NAMES = {
    "relief_bathymetry", "climate", "hydrology", "biomes", "cartography",
};
inline constexpr std::array<const char*, 12> CALIBRATION_METRIC_NAMES = {
    "ocean_fraction", "mean_land_elevation_m", "hypsometric_span_m",
    "global_mean_temperature_c", "mean_land_precipitation_mm_y",
    "mean_monthly_temperature_range_c", "river_cell_fraction",
    "endorheic_watershed_fraction", "desert_land_fraction",
    "ice_land_fraction", "forest_land_fraction", "coastal_land_fraction",
};
inline constexpr std::array<const char*, 6> COASTAL_FEATURE_TYPE_NAMES = {
    "beach", "barrier_bar", "barrier_island", "delta_lobe", "tidal_marsh", "coastal_cliff",
};
inline constexpr std::array<const char*, 5> SHORELINE_TREND_NAMES = {
    "stable", "prograding", "eroding", "landward_migration", "delta_switching",
};
inline constexpr std::array<const char*, 6> SEDIMENTARY_BASIN_TYPE_NAMES = {
    "rift_basin", "foreland_basin", "passive_margin", "lacustrine_basin", "evaporite_basin", "deltaic_basin",
};
inline constexpr std::array<const char*, 9> STRATIGRAPHIC_FACIES_NAMES = {
    "alluvial_fan", "fluvial_channel", "floodplain_mud", "deltaic_sand",
    "lacustrine_mud", "evaporite", "shallow_marine", "deep_marine", "glacial_till",
};
inline constexpr std::array<const char*, 5> SEQUENCE_PHASE_NAMES = {
    "aggradation", "progradation", "retrogradation", "starved", "erosional",
};
inline constexpr std::array<const char*, 5> ICE_RETREAT_STAGE_NAMES = {
    "advancing", "stable", "retreating", "stagnant", "relict",
};

}  // namespace magic_geo::detail
