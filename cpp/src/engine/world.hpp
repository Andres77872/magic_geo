#pragma once

#include "model.hpp"

#include <string>
#include <vector>

namespace magic_geo::detail {

struct EarthSystemState {
    std::vector<Cell> cells;
    std::vector<Plate> plates;
    std::vector<PlateMotionStep> plate_motion_history;
    std::vector<NumericDepressionFillEvent> numeric_depression_fill_history;
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

GeneratedWorld simulate_world(const Params& params);
std::string serialize_world(const Params& params, const GeneratedWorld& world);

}  // namespace magic_geo::detail
