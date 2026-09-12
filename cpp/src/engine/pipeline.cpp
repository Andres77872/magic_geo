#include "internal.hpp"
#include "world.hpp"

namespace magic_geo::detail {

struct GeographicFoundation::Data {
    Params params;
    GeneratedWorld world;
    FeedbackReference pre_cryosphere_reference;
    HydrologyStabilizationResult cryosphere_stabilization;
};
GeographicFoundation::GeographicFoundation(std::unique_ptr<Data> data):data_(std::move(data)) {}
GeographicFoundation::~GeographicFoundation()=default;
GeographicFoundation::GeographicFoundation(GeographicFoundation&&) noexcept=default;
GeographicFoundation& GeographicFoundation::operator=(GeographicFoundation&&) noexcept=default;
const EarthSystemState& GeographicFoundation::earth() const {
    if(!data_) throw TerrestrialWaterError("foundation_consumed","geographic foundation has been consumed");
    return data_->world.earth;
}
const Params& GeographicFoundation::params() const {
    if(!data_) throw TerrestrialWaterError("foundation_consumed","geographic foundation has been consumed");
    return data_->params;
}
FinalizedEnthalpyContext GeographicFoundation::enthalpy_context(
    FinalizedEnthalpyOptions options,std::uint64_t revision
) const {
    // Geometry is authoritative here; no late descendants-complete flag is
    // needed. The context validates all used coefficients and lake operands.
    return build_finalized_enthalpy_context(earth().cells,params(),std::move(options),revision);
}
SeasonalLiquidRoutingGraph GeographicFoundation::routing_graph(
    std::uint64_t revision,SeasonalLiquidRoutingLimits limits
) const {
    return capture_seasonal_liquid_routing_graph(earth().cells,revision,limits);
}

GeographicFoundation prepare_geographic_foundation(const Params& params) {
    GeneratedWorld world;
    EarthSystemState& earth = world.earth;

    earth.cells = build_mesh(params);
    if (params.plate_count >= static_cast<int>(earth.cells.size())) {
        throw std::runtime_error("plate_count must be smaller than generated mesh cell count");
    }

    earth.plates = generate_plates(params);
    const std::vector<int> seeds = choose_plate_seeds(
        params,
        static_cast<int>(earth.cells.size())
    );
    std::vector<Vec3> plate_centers;
    plate_centers.reserve(earth.plates.size());
    for (std::size_t index = 0; index < earth.plates.size(); ++index) {
        const Vec3 center = earth.cells[static_cast<std::size_t>(seeds[index])].p;
        earth.plates[index].initial_center = center;
        earth.plates[index].center = center;
        plate_centers.push_back(center);
    }
    assign_plates(plate_centers, earth.cells);
    classify_boundaries(params, earth.plates, earth.cells);
    derive_crust_and_topography(
        params,
        earth.plates,
        earth.cells,
        &earth.initial_oceanic_crust_age
    );
    CrustMotionDiagnostics initial_crust_motion;
    initial_crust_motion.transport_plan = build_identity_crust_transport_plan(
        earth.cells
    );
    std::vector<double> initial_isostatic_equilibrium_m;
    std::vector<double> initial_thermal_subsidence_target_m;
    initial_isostatic_equilibrium_m.reserve(earth.cells.size());
    initial_thermal_subsidence_target_m.reserve(earth.cells.size());
    for (const Cell& cell : earth.cells) {
        const bool oceanic_like = is_oceanic_crust_state(
            cell.crust_type,
            cell.lithology,
            cell.crust_age_ma,
            cell.crust_thickness_km,
            cell.crust_density
        );
        initial_isostatic_equilibrium_m.push_back(
            crust_equilibrium_elevation_m(
                cell.crust_thickness_km,
                cell.crust_density,
                oceanic_like
            )
        );
        initial_thermal_subsidence_target_m.push_back(
            cell.thermal_subsidence_target_m
        );
    }
    const std::vector<double> initial_zero_change_m(
        earth.cells.size(),
        0.0
    );
    earth.plate_motion_history.push_back(summarize_plate_motion_step(
        params,
        earth.cells,
        earth.plates,
        0,
        -1,
        "initial_plate_domains",
        {},
        std::vector<double>(earth.plates.size(), 0.0),
        initial_crust_motion,
        std::vector<double>(earth.cells.size(), 0.0),
        std::vector<double>(earth.cells.size(), 0.0),
        std::vector<double>(earth.cells.size(), 0.0),
        std::vector<double>(earth.cells.size(), 0.0),
        initial_isostatic_equilibrium_m,
        initial_zero_change_m,
        initial_thermal_subsidence_target_m,
        initial_zero_change_m,
        initial_zero_change_m,
        initial_zero_change_m
    ));
    initialize_crust_material_shadow(
        earth.cells,
        earth.plate_motion_history.back().id,
        earth.plate_motion_history.back().erosion_iteration,
        earth.plate_motion_history.back().stage,
        earth.crust_material_shadow
    );
    initialize_crust_dry_rock_accounting(
        earth.cells,
        static_cast<int>(earth.plates.size()),
        earth.plate_motion_history.back().id,
        earth.crust_material_shadow.history.back().id,
        earth.plate_motion_history.back().erosion_iteration,
        earth.plate_motion_history.back().stage,
        earth.crust_dry_rock_accounting
    );

    const HydrologyStabilizationResult initial_stabilization =
        stabilize_numeric_depressions(
            params,
            earth.cells,
            0,
            "initial_climate_hydrology",
            -1,
            earth.numeric_depression_correction_history,
            earth.hydrologic_water_budget_history,
            &earth.climate_cache
        );
    earth.feedback_history.push_back(summarize_feedback_step(
        earth.cells,
        0,
        "initial_climate_hydrology",
        -1,
        initial_stabilization,
        nullptr,
        nullptr,
        nullptr,
        false,
        false,
        false,
        false,
        false,
        0,
        nullptr
    ));

    erode(
        params,
        earth.plates,
        earth.cells,
        earth.feedback_history,
        earth.plate_motion_history,
        earth.crust_material_shadow,
        earth.crust_dry_rock_accounting,
        earth.numeric_depression_correction_history,
        earth.hydrologic_water_budget_history,
        earth.sediment_routing_history,
        earth.hillslope_transport_history,
        &earth.climate_cache
    );

    const FeedbackReference pre_cryosphere_reference =
        capture_feedback_reference(earth.cells);
    derive_cryosphere_state(params, earth.cells);
    earth.glacial_transport_history.push_back(transport_glacial_sediment(
        0,
        static_cast<int>(earth.feedback_history.size()),
        earth.cells
    ));
    const HydrologyStabilizationResult cryosphere_stabilization =
        stabilize_numeric_depressions(
            params,
            earth.cells,
            static_cast<int>(earth.feedback_history.size()),
            "cryosphere_coupling",
            -1,
            earth.numeric_depression_correction_history,
            earth.hydrologic_water_budget_history,
            &earth.climate_cache
        );
    return GeographicFoundation(std::make_unique<GeographicFoundation::Data>(
        GeographicFoundation::Data{params,std::move(world),pre_cryosphere_reference,cryosphere_stabilization}));
}

GeneratedWorld finish_legacy_generation(GeographicFoundation&& foundation, bool include_society) {
    if(!foundation.data_)
        throw TerrestrialWaterError("foundation_consumed","geographic foundation has been consumed");
    auto data=std::move(foundation.data_);
    const Params& params=data->params;
    GeneratedWorld world=std::move(data->world);
    EarthSystemState& earth=world.earth;
    NaturalArtifacts& natural=world.natural;
    SocietyArtifacts& society=world.society;
    const auto& pre_cryosphere_reference=data->pre_cryosphere_reference;
    const auto& cryosphere_stabilization=data->cryosphere_stabilization;
    derive_cryosphere_state(params, earth.cells);
    earth.feedback_history.push_back(summarize_feedback_step(
        earth.cells,
        static_cast<int>(earth.feedback_history.size()),
        "cryosphere_coupling",
        -1,
        cryosphere_stabilization,
        nullptr,
        nullptr,
        &earth.glacial_transport_history.back(),
        false,
        true,
        false,
        false,
        false,
        earth.plate_motion_history.back().id,
        &pre_cryosphere_reference
    ));

    summarize_plates(params, earth.cells, earth.plates);
    derive_soils_biomes_resources(params, earth.cells);
    derive_landforms(earth.cells);
    finalize_settlement_climate_applicability(params, earth.cells);
    natural.ice_sheets = generate_ice_sheets(earth.cells);
    natural.lake_basins = generate_lake_basins(params, earth.cells);
    natural.watersheds = generate_watersheds(params, earth.cells);
    natural.coastal_features = generate_coastal_features(params, earth.cells);
    natural.sedimentary_basins = generate_sedimentary_basins(earth.cells);
    natural.stratigraphic_columns = generate_stratigraphic_columns(
        earth.cells,
        natural.sedimentary_basins
    );

    if (include_society) {
        society.availability.enabled = params.temperature_model == ClimateTemperatureModel::prescribed_seasonal;
        society.settlements = generate_settlements(params, earth.cells);
        society.routes = generate_routes(params, earth.cells, society.settlements);
        society.political_regions = generate_political_regions(
            params,
            earth.cells,
            society.settlements,
            society.routes
        );
        society.borders = generate_border_segments(params, earth.cells);
        society.trade_flows = generate_trade_flows(
            earth.cells,
            society.settlements,
            society.routes
        );
        society.cultural_layers = generate_cultural_layers(
            params,
            earth.cells,
            society.settlements,
            society.political_regions,
            society.borders,
            society.trade_flows,
            &society.availability
        );
        society.historical_layers = generate_historical_layers(
            earth.cells,
            society.settlements,
            society.political_regions,
            society.borders,
            society.trade_flows,
            society.cultural_layers,
            &society.availability
        );
        society.population_regions = generate_population_regions(
            earth.cells,
            society.political_regions,
            society.cultural_layers,
            &society.availability
        );
        society.conflicts = generate_conflicts(
            earth.cells,
            society.political_regions,
            society.borders,
            society.trade_flows,
            society.cultural_layers,
            society.population_regions,
            &society.availability
        );
        society.dynasties = generate_dynasties(
            society.political_regions,
            society.cultural_layers,
            society.historical_layers,
            society.population_regions,
            society.conflicts,
            &society.availability
        );
        society.territorial_snapshots = generate_territorial_snapshots(
            params,
            earth.cells,
            society.political_regions,
            society.settlements,
            society.cultural_layers,
            society.historical_layers,
            society.population_regions,
            society.conflicts,
            &society.availability
        );
    }
    world.calibration_checks = generate_calibration_checks(
        earth.cells,
        natural.watersheds
    );
    // This remains descendants-complete readiness. Lake classification was
    // already fixed at the earlier geographic foundation; later basin
    // generation annotates and aggregates that hydrologic state.
    earth.finalized_enthalpy_planet = finalized_enthalpy_planet_inputs(params);
    earth.terrestrial_surface_finalized = true;
    return world;
}

TerrestrialWaterOwner begin_terrestrial_water_epoch(
    EarthSystemState& earth, TerrestrialWaterProperties properties,
    TerrestrialWaterRestart restart, std::uint64_t surface_revision,
    TerrestrialWaterLimits limits
) {
    if (!earth.terrestrial_surface_finalized) {
        throw TerrestrialWaterError("surface_not_finalized",
            "terrestrial interval requires a completed generated surface");
    }
    if (earth.terrestrial_surface_epoch) {
        throw TerrestrialWaterError("epoch_already_started",
            "this generated surface already has a terrestrial water epoch");
    }
    auto snapshot = capture_terrestrial_surface(earth.cells, surface_revision);
    // Construction may reject a malformed restart or an unavailable backend.
    // Do not publish a context until all owner initialization has succeeded.
    TerrestrialWaterOwner owner(snapshot, std::move(properties),
                                std::move(restart), limits);
    earth.terrestrial_surface_epoch.emplace(std::move(snapshot));
    earth.terrestrial_owner_mode = TerrestrialOwnerMode::prescribed_water;
    return owner;
}

namespace {
template<class Owner>
void require_current_terrestrial_epoch(
    const EarthSystemState& earth, const Owner& owner, TerrestrialOwnerMode mode
) {
    if (!earth.terrestrial_surface_finalized || !earth.terrestrial_surface_epoch) {
        throw TerrestrialWaterError("epoch_not_started",
            "generated surface has no active terrestrial water epoch");
    }
    if (!same_terrestrial_surface_epoch(*earth.terrestrial_surface_epoch,
                                        owner.surface())) {
        throw TerrestrialWaterError("epoch_mismatch",
            "terrestrial owner belongs to a different surface epoch");
    }
    if (earth.terrestrial_owner_mode != mode) {
        throw TerrestrialWaterError("owner_mode_mismatch",
            "this epoch is claimed by a different terrestrial owner mode");
    }
    if (!terrestrial_surface_matches(owner.surface(), earth.cells)) {
        throw TerrestrialWaterError("surface_changed",
            "terrain, wet domain or hydrology operands changed during the epoch");
    }
}
} // namespace

TerrestrialIntervalCandidate prepare_terrestrial_water_interval(
    const EarthSystemState& earth, const TerrestrialWaterOwner& owner,
    const TerrestrialIntervalRequest& request
) {
    require_current_terrestrial_epoch(earth, owner, TerrestrialOwnerMode::prescribed_water);
    return owner.prepare(request);
}

void commit_terrestrial_water_interval(
    const EarthSystemState& earth, TerrestrialWaterOwner& owner,
    const TerrestrialIntervalCandidate& candidate
) {
    require_current_terrestrial_epoch(earth, owner, TerrestrialOwnerMode::prescribed_water);
    owner.commit(candidate);
}

TerrestrialCoupledOwner begin_terrestrial_coupled_epoch(
    EarthSystemState& earth, CoupledProperties properties, CoupledRestart restart,
    CoupledAcceptancePolicy policy, std::uint64_t surface_revision, CoupledLimits limits
) {
    if (!earth.terrestrial_surface_finalized) {
        throw TerrestrialWaterError("surface_not_finalized",
            "coupled interval requires a completed generated surface");
    }
    if (earth.terrestrial_surface_epoch) {
        throw TerrestrialWaterError("epoch_already_started",
            "this generated surface already has a terrestrial owner epoch");
    }
    auto snapshot = capture_terrestrial_surface(earth.cells, surface_revision);
    TerrestrialCoupledOwner owner(snapshot, std::move(properties), std::move(restart), policy, limits);
    earth.terrestrial_surface_epoch.emplace(std::move(snapshot));
    earth.terrestrial_owner_mode = TerrestrialOwnerMode::coupled_energy;
    return owner;
}

CoupledPreparation prepare_terrestrial_coupled_interval(
    const EarthSystemState& earth, TerrestrialCoupledOwner& owner, const CoupledIntervalPlan& plan
) {
    require_current_terrestrial_epoch(earth, owner, TerrestrialOwnerMode::coupled_energy);
    return owner.prepare(plan);
}

CoupledPreparation prepare_terrestrial_coupled_interval(
    const EarthSystemState& earth, TerrestrialCoupledOwner& owner, const CoupledAutomaticRequest& request
) {
    require_current_terrestrial_epoch(earth, owner, TerrestrialOwnerMode::coupled_energy);
    return owner.prepare(request);
}

void commit_terrestrial_coupled_interval(
    const EarthSystemState& earth, TerrestrialCoupledOwner& owner,
    const CoupledIntervalCandidate& candidate
) {
    require_current_terrestrial_epoch(earth, owner, TerrestrialOwnerMode::coupled_energy);
    owner.commit(candidate);
}

GeneratedWorld simulate_world(const Params& params) {
    return finish_legacy_generation(prepare_geographic_foundation(params), true);
}

GeneratedWorld simulate_geo_world(const Params& params) {
    return finish_legacy_generation(prepare_geographic_foundation(params), false);
}

}  // namespace magic_geo::detail
