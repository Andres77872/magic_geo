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
inline constexpr double OCEANIC_AGE_DEPTH_YOUNG_CUTOFF_MA = 70.0;
inline constexpr double
    OCEANIC_AGE_DEPTH_YOUNG_COEFFICIENT_M_PER_SQRT_MA = 350.0;
inline constexpr double OCEANIC_AGE_DEPTH_OLD_EXPONENTIAL_SCALE_M = 3200.0;
inline constexpr double OCEANIC_AGE_DEPTH_OLD_EFOLDING_TIME_MA = 62.8;
inline constexpr double
    OCEANIC_AGE_DEPTH_TARGET_DIFFERENCE_GAIN = 1.0;
inline constexpr double
    TECTONIC_ISOSTATIC_TARGET_DIFFERENCE_GAIN = 1.0;
inline constexpr double TECTONIC_DYNAMIC_RELIEF_MINIMUM_CHANGE_M = -180.0;
inline constexpr double TECTONIC_DYNAMIC_RELIEF_MAXIMUM_CHANGE_M = 220.0;
inline constexpr double TECTONIC_UPLIFT_RATE_RESPONSE_FRACTION = 0.42;
double climate_stellar_temperature_forcing_c(const Params& params);
double climate_greenhouse_temperature_forcing_c(const Params& params);
double climate_thermal_moisture_temperature_anomaly_c(const Params& params);
double climate_thermal_moisture_capacity_factor(const Params& params);
double crust_age_ceiling_ma(const Params& params, double model_ceiling_ma);
double maturation_timestep_scale(const Params& params);
double timestep_scaled_fraction(double reference_fraction, double timestep_scale);
double oceanic_age_depth_thermal_subsidence_m(
    double crust_age_ma,
    bool oceanic_like
);
std::vector<double> build_initial_oceanic_crust_age_field(
    const Params& params,
    const std::vector<Cell>& cells,
    const std::vector<PlateBoundarySegment>& boundary_segments,
    InitialOceanicCrustAgeDiagnostics* diagnostics = nullptr
);
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
std::string roundtrip_num(double value);
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
CrustTransportPlan build_identity_crust_transport_plan(
    const std::vector<Cell>& cells
);
CrustTransportPlan build_forward_overlap_crust_transport_plan(
    const Params& params,
    const std::vector<Plate>& plates,
    const std::vector<Cell>& cells,
    const std::vector<int>& previous_plate_ids,
    const std::vector<int>& previous_crust_types,
    const std::vector<int>& previous_lithologies,
    const std::vector<double>& previous_crust_age_ma,
    const std::vector<double>& previous_crust_thickness_km,
    const std::vector<double>& previous_crust_density,
    const std::vector<double>& step_rotation_deg
);
void initialize_crust_material_shadow(
    const std::vector<Cell>& cells,
    int plate_motion_history_id,
    int erosion_iteration,
    const std::string& stage,
    CrustMaterialShadowState& state
);
void begin_crust_material_shadow_step(
    const std::vector<Cell>& cells,
    const CrustTransportPlan& transport_plan,
    int plate_motion_history_id,
    int erosion_iteration,
    const std::string& stage,
    CrustMaterialShadowState& state
);
void apply_crust_material_shadow_transition(
    CrustMaterialShadowState& state,
    int cell_id,
    int current_plate_id,
    CrustProcessReason process_reason,
    double area_km2,
    double before_thickness_km,
    double before_density_g_cm3,
    double after_thickness_km,
    double after_density_g_cm3
);
void finalize_crust_material_shadow_step(
    const std::vector<Cell>& cells,
    const CrustTransportPlan& transport_plan,
    CrustMaterialShadowState& state
);
void initialize_crust_dry_rock_accounting(
    const std::vector<Cell>& cells,
    int plate_count,
    int plate_motion_history_id,
    int crust_material_shadow_history_id,
    int erosion_iteration,
    const std::string& stage,
    CrustDryRockAccountingState& state
);
void advance_crust_dry_rock_accounting_step(
    const std::vector<Cell>& cells,
    int plate_count,
    const CrustTransportPlan& transport_plan,
    const CrustMaterialShadowStep& shadow_step,
    CrustDryRockAccountingState& state
);

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
    std::vector<Cell>& cells,
    InitialOceanicCrustAgeDiagnostics* initial_oceanic_crust_age = nullptr
);
bool is_oceanic_crust_state(
    int crust_type,
    int lithology,
    double age_ma,
    double thickness_km,
    double density
);
double crust_equilibrium_elevation_m(
    double thickness_km,
    double density,
    bool oceanic
);
PlateMotionStep summarize_plate_motion_step(
    const Params& params,
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
    const std::vector<double>& tectonic_elevation_change_m,
    const std::vector<double>& previous_local_isostatic_equilibrium_m,
    const std::vector<double>& isostatic_equilibrium_change_m,
    const std::vector<double>& previous_local_thermal_subsidence_target_m,
    const std::vector<double>& thermal_equilibrium_change_m,
    const std::vector<double>& unbounded_dynamic_relief_change_m,
    const std::vector<double>& bounded_dynamic_relief_change_m
);
std::vector<PlateBoundarySegment> build_plate_boundary_segments(
    const Params& params,
    const std::vector<Cell>& cells,
    const std::vector<Plate>& plates,
    const CrustTransportPlan& opening_crust,
    int* reciprocal_mesh_segment_count
);
CrustOverlapCandidateFateLedger build_crust_overlap_candidate_fate_ledger(
    const CrustTransportPlan& transport,
    const std::vector<PlateBoundarySegment>& boundary_segments,
    int step_id,
    int cell_count,
    int plate_count
);
std::vector<double> advance_plate_motion_and_crust(
    const Params& params,
    int erosion_iteration,
    std::vector<Plate>& plates,
    std::vector<Cell>& cells,
    std::vector<PlateMotionStep>& plate_motion_history,
    CrustMaterialShadowState& crust_material_shadow,
    CrustDryRockAccountingState& crust_dry_rock_accounting
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
    std::vector<NumericDepressionCorrectionEvent>& correction_history,
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
void initialize_sediment_interface(Cell& cell, const char* context);
void shift_sediment_interface_datum(
    Cell& cell,
    double elevation_change_m,
    const char* context
);
void apply_sediment_interface_material_change(
    Cell& cell,
    double vertical_displacement_m,
    double bedrock_erosion_depth_m,
    double alluvium_entrainment_depth_m,
    double deposition_depth_m,
    const char* context
);
void validate_sediment_interface(const Cell& cell, const char* context);
double maximum_sediment_interface_closure_residual_m(
    const std::vector<Cell>& cells,
    const char* context
);
void validate_sediment_source_partition(
    const std::vector<Cell>& cells,
    const std::vector<double>& source_depth_m_by_cell,
    const std::vector<double>& alluvium_entrainment_depth_m_by_cell,
    const std::vector<double>& bedrock_erosion_depth_m_by_cell,
    double alluvium_entrainment_volume_km3,
    double bedrock_erosion_volume_km3,
    const char* context
);
void erode(
    const Params& params,
    std::vector<Plate>& plates,
    std::vector<Cell>& cells,
    std::vector<EarthSystemFeedbackStep>& feedback_history,
    std::vector<PlateMotionStep>& plate_motion_history,
    CrustMaterialShadowState& crust_material_shadow,
    CrustDryRockAccountingState& crust_dry_rock_accounting,
    std::vector<NumericDepressionCorrectionEvent>& numeric_depression_correction_history,
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
    const std::vector<NumericDepressionCorrectionEvent>& numeric_depression_correction_history,
    const std::vector<HillslopeSedimentTransportStage>& hillslope_transport_history,
    const std::vector<GlacialSedimentTransportStage>& glacial_transport_history
);
std::string plates_json(const std::vector<Plate>& plates, int precision);
std::string int_array_json(const std::vector<int>& values);
std::string double_array_json(const std::vector<double>& values, int precision);
std::string roundtrip_double_array_json(const std::vector<double>& values);
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
    const Params& params,
    const std::vector<HydrologicWaterBudgetStage>& history,
    int precision
);
std::string numeric_depression_correction_history_json(
    const Params& params,
    const std::vector<NumericDepressionCorrectionEvent>& history,
    int precision
);
std::string glacial_sediment_transport_model_json(
    const std::vector<GlacialSedimentTransportStage>& history,
    int precision
);
std::string glacial_sediment_transport_history_json(
    const Params& params,
    const std::vector<GlacialSedimentTransportStage>& history,
    int precision
);
std::string hillslope_sediment_transport_model_json(
    const Params& params,
    const std::vector<HillslopeSedimentTransportStage>& history
);
std::string hillslope_sediment_transport_history_json(
    const Params& params,
    const std::vector<HillslopeSedimentTransportStage>& history,
    int precision
);
std::string fluvial_sediment_routing_model_json(
    const std::vector<FluvialSedimentRoutingStage>& history,
    int precision
);
std::string fluvial_sediment_routing_history_json(
    const Params& params,
    const std::vector<FluvialSedimentRoutingStage>& history,
    int precision
);
std::string sediment_inventory_model_json(
    const std::vector<Cell>& cells,
    const std::vector<EarthSystemFeedbackStep>& feedback_history,
    const std::vector<NumericDepressionCorrectionEvent>& numeric_history,
    const std::vector<HillslopeSedimentTransportStage>& hillslope_history,
    const std::vector<FluvialSedimentRoutingStage>& fluvial_history,
    const std::vector<GlacialSedimentTransportStage>& glacial_history,
    int precision
);
std::string sediment_interface_model_json(
    const std::vector<Cell>& cells,
    int precision
);
std::string simulation_clock_json(
    const Params& params,
    const std::vector<EarthSystemFeedbackStep>& feedback_history
);
std::string earth_system_feedback_history_json(
    const Params& params,
    const std::vector<EarthSystemFeedbackStep>& feedback_history,
    int precision
);
std::string plate_kinematic_model_json(
    const Params& params,
    const std::vector<PlateMotionStep>& history,
    const std::vector<Cell>& cells
);
std::string plate_boundary_segment_model_json(
    const Params& params,
    const std::vector<PlateMotionStep>& history
);
std::string initial_oceanic_crust_age_model_json(
    const InitialOceanicCrustAgeDiagnostics& diagnostics
);
std::string initial_oceanic_crust_age_ledger_json(
    const InitialOceanicCrustAgeDiagnostics& diagnostics
);
std::string crust_overlap_candidate_fate_model_json();
std::string oceanic_age_depth_model_json();
std::string sea_level_model_json(const Params& params, const std::vector<Cell>& cells);
std::string plate_motion_history_json(
    const Params& params,
    const std::vector<PlateMotionStep>& history,
    int precision
);
std::string calibration_checks_json(
    const std::vector<CalibrationCheck>& checks,
    int precision
);
std::string borders_json(const std::vector<BorderSegment>& borders, int precision);

}  // namespace magic_geo::detail
