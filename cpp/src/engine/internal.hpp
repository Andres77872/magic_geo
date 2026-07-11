#pragma once

#include "model.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <map>
#include <numeric>
#include <queue>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

namespace magic_geo::detail {

// Shared numeric, geometry, configuration, and JSON primitives.
double climate_stellar_temperature_forcing_c(const Params& params);
double climate_greenhouse_temperature_forcing_c(const Params& params);
double climate_thermal_moisture_temperature_anomaly_c(const Params& params);
double climate_thermal_moisture_capacity_factor(const Params& params);
double crust_age_ceiling_ma(const Params& params, double model_ceiling_ma);
Vec3 add(Vec3 a, Vec3 b);
Vec3 sub(Vec3 a, Vec3 b);
Vec3 mul(Vec3 a, double scalar);
double dot(Vec3 a, Vec3 b);
Vec3 cross(Vec3 a, Vec3 b);
double norm(Vec3 a);
Vec3 normalize(Vec3 a);
Vec3 rotate_about_axis(Vec3 value, Vec3 axis, double angle_rad);
double angular_distance(Vec3 a, Vec3 b);
double spherical_triangle_area_steradians(Vec3 a, Vec3 b, Vec3 c);
const char* mesh_backend_name(int backend);
const char* cell_area_model_name(int backend);
std::uint64_t splitmix64(std::uint64_t value);
double hash01(std::uint64_t seed, std::uint64_t a, std::uint64_t b = 0);
double signed_noise(std::uint64_t seed, std::uint64_t a, std::uint64_t b = 0);
std::string json_escape(const std::string& value);
std::string num(double value, int precision);
void comma(std::string& out, bool& first);
void add_raw(std::string& out, bool& first, const char* key, const std::string& raw);
void add_str(std::string& out, bool& first, const char* key, const std::string& value);
void add_int(std::string& out, bool& first, const char* key, int value);
void add_u64(std::string& out, bool& first, const char* key, std::uint64_t value);
void add_double(std::string& out, bool& first, const char* key, double value, int precision);
void add_bool(std::string& out, bool& first, const char* key, bool value);

class ScopedThreadConfiguration {
public:
    explicit ScopedThreadConfiguration(int requested_threads);
    ~ScopedThreadConfiguration();

    ScopedThreadConfiguration(const ScopedThreadConfiguration&) = delete;
    ScopedThreadConfiguration& operator=(const ScopedThreadConfiguration&) = delete;

private:
    int previous_max_threads_ = 0;
    bool restore_on_destruction_ = false;
};

void validate_compute_options(const ComputeOptions& compute_options);
void validate_params(const Params& params);
std::vector<Cell> build_mesh(const Params& params);

// Tectonic and relief stages.
std::vector<Plate> generate_plates(const Params& params);
std::vector<int> choose_plate_seeds(const Params& params, int cell_count);
void assign_plates(const std::vector<Vec3>& centers, std::vector<Cell>& cells);
void classify_boundaries(
    const Params& params,
    const std::vector<Plate>& plates,
    std::vector<Cell>& cells
);
double lithology_resistance(int lithology);
void derive_crust_and_topography(
    const Params& params,
    const std::vector<Plate>& plates,
    std::vector<Cell>& cells
);
PlateMotionStep summarize_plate_motion_step(
    const std::vector<Cell>& cells,
    const std::vector<Plate>& plates,
    int id,
    int erosion_iteration,
    const std::string& stage,
    const std::vector<int>& previous_plate_ids,
    const std::vector<double>& step_rotation_deg,
    const CrustMotionDiagnostics& crust_motion,
    const std::vector<double>& crust_age_change_ma,
    const std::vector<double>& crust_thickness_change_km,
    const std::vector<double>& crust_density_change,
    const std::vector<double>& tectonic_elevation_change_m
);
std::vector<double> advance_plate_motion_and_crust(
    const Params& params,
    int erosion_iteration,
    std::vector<Plate>& plates,
    std::vector<Cell>& cells,
    std::vector<PlateMotionStep>& plate_motion_history
);
void summarize_plates(
    const Params& params,
    const std::vector<Cell>& cells,
    std::vector<Plate>& plates
);
double apply_sea_level(const Params& params, std::vector<Cell>& cells);

// Climate, hydrology, erosion, and cryosphere stages.
void label_marine_water_bodies(std::vector<Cell>& cells);
std::vector<int> ocean_distance(const std::vector<Cell>& cells);
double wrap_angle(double radians);
double local_relief(const std::vector<Cell>& cells, int cell_id);
void compute_climate(const Params& params, std::vector<Cell>& cells);
double hydrologic_lithology_permeability(int lithology);
double neighbor_distance_m(const Params& params, const Cell& a, const Cell& b);
bool is_geologic_depression(const Cell& cell);
HydrologyStabilizationResult stabilize_numeric_depressions(
    const Params& params,
    std::vector<Cell>& cells,
    int feedback_stage_id,
    const std::string& stage,
    int erosion_iteration,
    std::vector<NumericDepressionFillEvent>& fill_history,
    std::vector<HydrologicWaterBudgetStage>& water_budget_history
);
FeedbackReference capture_feedback_reference(const std::vector<Cell>& cells);
EarthSystemFeedbackStep summarize_feedback_step(
    const std::vector<Cell>& cells,
    int id,
    const std::string& stage,
    int erosion_iteration,
    const HydrologyStabilizationResult& stabilization,
    const FluvialSedimentRoutingStage* sediment_routing,
    const HillslopeSedimentTransportStage* hillslope_transport,
    const GlacialSedimentTransportStage* glacial_transport,
    bool erosion_applied,
    bool cryosphere_applied,
    bool plate_motion_applied,
    bool crust_transport_applied,
    bool crust_evolution_applied,
    int plate_motion_history_id,
    const FeedbackReference* previous
);
void erode(
    const Params& params,
    std::vector<Plate>& plates,
    std::vector<Cell>& cells,
    std::vector<EarthSystemFeedbackStep>& feedback_history,
    std::vector<PlateMotionStep>& plate_motion_history,
    std::vector<NumericDepressionFillEvent>& numeric_depression_fill_history,
    std::vector<HydrologicWaterBudgetStage>& hydrologic_water_budget_history,
    std::vector<FluvialSedimentRoutingStage>& sediment_routing_history,
    std::vector<HillslopeSedimentTransportStage>& hillslope_transport_history
);
bool has_ocean_neighbor(const std::vector<Cell>& cells, int cell_id);
bool has_glacier_neighbor(
    const std::vector<Cell>& cells,
    int cell_id,
    double threshold_m = 80.0
);
void derive_cryosphere_state(const Params& params, std::vector<Cell>& cells);
GlacialSedimentTransportStage transport_glacial_sediment(
    int id,
    int feedback_stage_id,
    std::vector<Cell>& cells
);
void derive_soils_biomes_resources(const Params& params, std::vector<Cell>& cells);
void derive_landforms(std::vector<Cell>& cells);
std::vector<CoastalFeature> generate_coastal_features(
    const Params& params,
    const std::vector<Cell>& cells
);
std::vector<SedimentaryBasin> generate_sedimentary_basins(const std::vector<Cell>& cells);
std::vector<StratigraphicColumn> generate_stratigraphic_columns(
    const std::vector<Cell>& cells,
    const std::vector<SedimentaryBasin>& basins
);
std::vector<IceSheet> generate_ice_sheets(std::vector<Cell>& cells);

// Derived physical and civilization artifacts.
std::vector<Settlement> generate_settlements(
    const Params& params,
    const std::vector<Cell>& cells
);
std::vector<Route> generate_routes(
    const Params& params,
    const std::vector<Cell>& cells,
    const std::vector<Settlement>& settlements
);
double route_barrier_cost(const Cell& a, const Cell& b);
std::vector<LakeBasin> generate_lake_basins(
    const Params& params,
    std::vector<Cell>& cells
);
std::vector<Watershed> generate_watersheds(
    const Params& params,
    const std::vector<Cell>& cells
);
std::vector<LatLon> watershed_boundary_ring(
    const std::vector<Cell>& cells,
    const std::vector<int>& boundary_cell_ids,
    Vec3 weighted_center,
    int max_points
);
Vec3 latlon_to_vec(const LatLon& point);
double ring_perimeter_km(const Params& params, const std::vector<LatLon>& ring);
double ring_projected_area_km2(
    const Params& params,
    const std::vector<LatLon>& ring,
    Vec3 weighted_center
);
std::vector<PoliticalRegion> generate_political_regions(
    const Params& params,
    std::vector<Cell>& cells,
    std::vector<Settlement>& settlements,
    const std::vector<Route>& routes
);
std::vector<BorderSegment> generate_border_segments(
    const Params& params,
    const std::vector<Cell>& cells
);
std::vector<TradeFlow> generate_trade_flows(
    const std::vector<Cell>& cells,
    const std::vector<Settlement>& settlements,
    const std::vector<Route>& routes
);
CulturalLayers generate_cultural_layers(
    const Params& params,
    std::vector<Cell>& cells,
    std::vector<Settlement>& settlements,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<BorderSegment>& borders,
    const std::vector<TradeFlow>& trade_flows
);
HistoricalLayers generate_historical_layers(
    const std::vector<Cell>& cells,
    const std::vector<Settlement>& settlements,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<BorderSegment>& borders,
    const std::vector<TradeFlow>& trade_flows,
    const CulturalLayers& cultural_layers
);
std::vector<PopulationRegion> generate_population_regions(
    const std::vector<Cell>& cells,
    const std::vector<PoliticalRegion>& political_regions,
    const CulturalLayers& cultural_layers
);
std::vector<ConflictRecord> generate_conflicts(
    const std::vector<Cell>& cells,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<BorderSegment>& borders,
    const std::vector<TradeFlow>& trade_flows,
    const CulturalLayers& cultural_layers,
    const std::vector<PopulationRegion>& population_regions
);
std::vector<DynastyRecord> generate_dynasties(
    const std::vector<PoliticalRegion>& political_regions,
    const CulturalLayers& cultural_layers,
    const HistoricalLayers& historical_layers,
    const std::vector<PopulationRegion>& population_regions,
    const std::vector<ConflictRecord>& conflicts
);
std::vector<TerritorialSnapshot> generate_territorial_snapshots(
    const Params& params,
    const std::vector<Cell>& cells,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<Settlement>& settlements,
    const CulturalLayers& cultural_layers,
    const HistoricalLayers& historical_layers,
    const std::vector<PopulationRegion>& population_regions,
    const std::vector<ConflictRecord>& conflicts
);
std::vector<CalibrationCheck> generate_calibration_checks(
    const std::vector<Cell>& cells,
    const std::vector<Watershed>& watersheds
);

// Output rendering. Simulation stages do not depend on these functions.
std::string summary_json(
    const Params& params,
    const std::vector<Cell>& cells,
    const std::vector<Watershed>& watersheds,
    const std::vector<LakeBasin>& lake_basins,
    const std::vector<CoastalFeature>& coastal_features,
    const std::vector<SedimentaryBasin>& sedimentary_basins,
    const std::vector<StratigraphicColumn>& stratigraphic_columns,
    const std::vector<IceSheet>& ice_sheets,
    const std::vector<PoliticalRegion>& political_regions,
    const std::vector<BorderSegment>& borders,
    const std::vector<TradeFlow>& trade_flows,
    const CulturalLayers& cultural_layers,
    const HistoricalLayers& historical_layers,
    const std::vector<PopulationRegion>& population_regions,
    const std::vector<ConflictRecord>& conflicts,
    const std::vector<DynastyRecord>& dynasties,
    const std::vector<TerritorialSnapshot>& territorial_snapshots,
    const std::vector<CalibrationCheck>& calibration_checks,
    const std::vector<Settlement>& settlements,
    const std::vector<Route>& routes,
    const std::vector<EarthSystemFeedbackStep>& feedback_history,
    const std::vector<PlateMotionStep>& plate_motion_history,
    const std::vector<NumericDepressionFillEvent>& numeric_depression_fill_history,
    const std::vector<HillslopeSedimentTransportStage>& hillslope_transport_history,
    const std::vector<GlacialSedimentTransportStage>& glacial_transport_history
);
std::string plates_json(const std::vector<Plate>& plates, int precision);
std::string int_array_json(const std::vector<int>& values);
std::string double_array_json(const std::vector<double>& values, int precision);
template <std::size_t Size>
std::string double_array_json(
    const std::array<double, Size>& values,
    int precision
) {
    std::string out = "[";
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index > 0) {
            out += ",";
        }
        out += num(values[index], precision);
    }
    out += "]";
    return out;
}
std::string vec3_json(Vec3 value, int precision);
std::string latlon_ring_json(const std::vector<LatLon>& ring, int precision);
std::string cells_json(const std::vector<Cell>& cells, int precision);
std::string settlements_json(
    const std::vector<Cell>& cells,
    const std::vector<Settlement>& settlements,
    int precision
);
std::string routes_json(const std::vector<Route>& routes, int precision);
std::string trade_flows_json(const std::vector<TradeFlow>& flows, int precision);
std::string watersheds_json(const std::vector<Watershed>& watersheds, int precision);
std::string lake_basins_json(const std::vector<LakeBasin>& basins, int precision);
std::string coastal_features_json(const std::vector<CoastalFeature>& features, int precision);
std::string sedimentary_basins_json(const std::vector<SedimentaryBasin>& basins, int precision);
std::string stratigraphic_columns_json(
    const std::vector<StratigraphicColumn>& columns,
    int precision
);
std::string ice_sheets_json(const std::vector<IceSheet>& sheets, int precision);
std::string political_regions_json(const std::vector<PoliticalRegion>& regions, int precision);
std::string cultures_json(const std::vector<CultureRegion>& cultures, int precision);
std::string language_regions_json(const std::vector<LanguageRegion>& languages, int precision);
std::string sacred_areas_json(const std::vector<SacredArea>& sacred_areas, int precision);
std::string ruins_json(const std::vector<Ruin>& ruins, int precision);
std::string historical_eras_json(const std::vector<HistoricalEra>& eras, int precision);
std::string historical_events_json(const std::vector<HistoricalEvent>& events, int precision);
std::string population_regions_json(
    const std::vector<PopulationRegion>& populations,
    int precision
);
std::string conflicts_json(const std::vector<ConflictRecord>& conflicts, int precision);
std::string dynasties_json(const std::vector<DynastyRecord>& dynasties, int precision);
std::string snapshot_regions_json(const std::vector<SnapshotRegion>& regions, int precision);
std::string territorial_snapshots_json(
    const std::vector<TerritorialSnapshot>& snapshots,
    int precision
);
std::string climate_model_json(const Params& params);
std::string hydrologic_water_budget_model_json(
    const std::vector<HydrologicWaterBudgetStage>& history,
    int precision
);
std::string hydrologic_water_budget_history_json(
    const std::vector<HydrologicWaterBudgetStage>& history,
    int precision
);
std::string numeric_depression_fill_history_json(
    const std::vector<NumericDepressionFillEvent>& history,
    int precision
);
std::string glacial_sediment_transport_model_json(
    const std::vector<GlacialSedimentTransportStage>& history,
    int precision
);
std::string glacial_sediment_transport_history_json(
    const std::vector<GlacialSedimentTransportStage>& history,
    int precision
);
std::string hillslope_sediment_transport_model_json(
    const Params& params,
    const std::vector<HillslopeSedimentTransportStage>& history
);
std::string hillslope_sediment_transport_history_json(
    const std::vector<HillslopeSedimentTransportStage>& history,
    int precision
);
std::string fluvial_sediment_routing_model_json(
    const std::vector<FluvialSedimentRoutingStage>& history,
    int precision
);
std::string fluvial_sediment_routing_history_json(
    const std::vector<FluvialSedimentRoutingStage>& history,
    int precision
);
std::string sediment_inventory_model_json(
    const std::vector<Cell>& cells,
    const std::vector<EarthSystemFeedbackStep>& feedback_history,
    const std::vector<NumericDepressionFillEvent>& numeric_history,
    const std::vector<HillslopeSedimentTransportStage>& hillslope_history,
    const std::vector<FluvialSedimentRoutingStage>& fluvial_history,
    const std::vector<GlacialSedimentTransportStage>& glacial_history,
    int precision
);
std::string simulation_clock_json(
    const Params& params,
    const std::vector<EarthSystemFeedbackStep>& feedback_history
);
std::string earth_system_feedback_history_json(
    const std::vector<EarthSystemFeedbackStep>& feedback_history,
    int precision
);
std::string plate_kinematic_model_json(
    const Params& params,
    const std::vector<PlateMotionStep>& history,
    const std::vector<Cell>& cells
);
std::string sea_level_model_json(const Params& params, const std::vector<Cell>& cells);
std::string plate_motion_history_json(
    const std::vector<PlateMotionStep>& history,
    int precision
);
std::string calibration_checks_json(
    const std::vector<CalibrationCheck>& checks,
    int precision
);
std::string borders_json(const std::vector<BorderSegment>& borders, int precision);

}  // namespace magic_geo::detail
