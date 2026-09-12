#pragma once

#include "model.hpp"
#include "seasonal_climate_cache.hpp"
#include "terrestrial_water.hpp"
#include "terrestrial_coupled.hpp"
#include "finalized_enthalpy_context.hpp"
#include "seasonal_liquid_routing.hpp"

#include <memory>
#include <optional>

#include <string>
#include <vector>

namespace magic_geo::detail {

enum class TerrestrialOwnerMode { none, prescribed_water, coupled_energy, combined_enthalpy };

struct EarthSystemState {
    std::vector<Cell> cells;
    PrescribedSeasonalClimateCache climate_cache;
    // Numerical climate/lake retries never initialize or advance this epoch.
    // Full Cell snapshots are allocated only by the explicit interval entry.
    bool terrestrial_surface_finalized = false;
    std::optional<FinalizedEnthalpyPlanetInputs> finalized_enthalpy_planet;
    std::optional<TerrestrialSurfaceSnapshot> terrestrial_surface_epoch;
    TerrestrialOwnerMode terrestrial_owner_mode = TerrestrialOwnerMode::none;
    InitialOceanicCrustAgeDiagnostics initial_oceanic_crust_age;
    CrustMaterialShadowState crust_material_shadow;
    CrustDryRockAccountingState crust_dry_rock_accounting;
    std::vector<Plate> plates;
    std::vector<PlateMotionStep> plate_motion_history;
    std::vector<NumericDepressionCorrectionEvent> numeric_depression_correction_history;
    std::vector<HydrologicWaterBudgetStage> hydrologic_water_budget_history;
    std::vector<EarthSystemFeedbackStep> feedback_history;
    std::vector<FluvialSedimentRoutingStage> sediment_routing_history;
    std::vector<HillslopeSedimentTransportStage> hillslope_transport_history;
    std::vector<GlacialSedimentTransportStage> glacial_transport_history;
};

struct NaturalArtifacts {
    std::vector<IceSheet> ice_sheets;
    std::vector<LakeBasin> lake_basins;
    std::vector<Watershed> watersheds;
    std::vector<CoastalFeature> coastal_features;
    std::vector<SedimentaryBasin> sedimentary_basins;
    std::vector<StratigraphicColumn> stratigraphic_columns;
};

struct SocietyArtifacts {
    SocialAvailability availability;
    std::vector<Settlement> settlements;
    std::vector<Route> routes;
    std::vector<PoliticalRegion> political_regions;
    std::vector<BorderSegment> borders;
    std::vector<TradeFlow> trade_flows;
    CulturalLayers cultural_layers;
    HistoricalLayers historical_layers;
    std::vector<PopulationRegion> population_regions;
    std::vector<ConflictRecord> conflicts;
    std::vector<DynastyRecord> dynasties;
    std::vector<TerritorialSnapshot> territorial_snapshots;
};

struct GeneratedWorld {
    EarthSystemState earth;
    NaturalArtifacts natural;
    SocietyArtifacts society;
    std::vector<CalibrationCheck> calibration_checks;
};

// A generation stage, not a completed public world. Created only after the
// last terrain/climate/hydrology stabilizer succeeds, before the final annual
// ice diagnostic and every natural/social descendant. Its read-only source
// may initialize a physical model without claiming those descendants exist.
struct FinalizedLayeredStateRequest;
struct FinalizedLayeredStateInitialization;
class GeographicFoundation {
    struct Data;
    std::unique_ptr<Data> data_;
    explicit GeographicFoundation(std::unique_ptr<Data>);
    friend GeographicFoundation prepare_geographic_foundation(const Params&);
    friend GeneratedWorld finish_legacy_generation(GeographicFoundation&&, bool);
public:
    ~GeographicFoundation();
    GeographicFoundation(GeographicFoundation&&) noexcept;
    GeographicFoundation& operator=(GeographicFoundation&&) noexcept;
    GeographicFoundation(const GeographicFoundation&) = delete;
    GeographicFoundation& operator=(const GeographicFoundation&) = delete;
    // Borrowed references; invalid after this stage is finished or destroyed.
    const EarthSystemState& earth() const;
    const Params& params() const;
    // These capture independently validated, immutable climate/lake and
    // routing operands from the same authoritative pre-descendant source.
    FinalizedEnthalpyContext enthalpy_context(FinalizedEnthalpyOptions,
                                             std::uint64_t surface_revision = 0) const;
    SeasonalLiquidRoutingGraph routing_graph(std::uint64_t surface_revision = 0,
                                             SeasonalLiquidRoutingLimits = {}) const;
    // Compile an explicitly supplied physical initial condition on this source.
    // Creates a private owner; performs no evolution or descendant publication.
    FinalizedLayeredStateInitialization initialize_layered_state(
        FinalizedEnthalpyOptions, const FinalizedLayeredStateRequest&,
        std::uint64_t surface_revision = 0, SeasonalLiquidRoutingLimits = {}) const;
};

GeographicFoundation prepare_geographic_foundation(const Params&);
// Consume the foundation through the existing annual diagnostic branch.
// A future physical publication branch must have its own completion contract.
// Consumption is one-shot, including when a downstream stage throws.
GeneratedWorld finish_legacy_generation(GeographicFoundation&&, bool include_society);

// Internal opt-in prescribed intervals on a finalized generated surface. These
// entries leave existing climate, hydrology and natural/social artifacts intact.
TerrestrialWaterOwner begin_terrestrial_water_epoch(
    EarthSystemState&, TerrestrialWaterProperties, TerrestrialWaterRestart,
    std::uint64_t surface_revision = 0, TerrestrialWaterLimits = {});
TerrestrialIntervalCandidate prepare_terrestrial_water_interval(
    const EarthSystemState&, const TerrestrialWaterOwner&,
    const TerrestrialIntervalRequest&);
void commit_terrestrial_water_interval(
    const EarthSystemState&, TerrestrialWaterOwner&,
    const TerrestrialIntervalCandidate&);

TerrestrialCoupledOwner begin_terrestrial_coupled_epoch(
    EarthSystemState&, CoupledProperties, CoupledRestart, CoupledAcceptancePolicy,
    std::uint64_t surface_revision = 0, CoupledLimits = {});
CoupledPreparation prepare_terrestrial_coupled_interval(
    const EarthSystemState&, TerrestrialCoupledOwner&, const CoupledIntervalPlan&);
CoupledPreparation prepare_terrestrial_coupled_interval(
    const EarthSystemState&, TerrestrialCoupledOwner&, const CoupledAutomaticRequest&);
void commit_terrestrial_coupled_interval(
    const EarthSystemState&, TerrestrialCoupledOwner&, const CoupledIntervalCandidate&);

GeneratedWorld simulate_world(const Params& params);
GeneratedWorld simulate_geo_world(const Params& params);
std::string serialize_world(const Params& params, const GeneratedWorld& world);

}  // namespace magic_geo::detail
