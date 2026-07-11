#include "internal.hpp"
#include "world.hpp"

namespace magic_geo::detail {

GeneratedWorld simulate_world(const Params& params) {
    GeneratedWorld world;
    EarthSystemState& earth = world.earth;
    NaturalArtifacts& natural = world.natural;
    SocietyArtifacts& society = world.society;

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
    derive_crust_and_topography(params, earth.plates, earth.cells);
    earth.plate_motion_history.push_back(summarize_plate_motion_step(
        earth.cells,
        earth.plates,
        0,
        -1,
        "initial_plate_domains",
        {},
        std::vector<double>(earth.plates.size(), 0.0),
        CrustMotionDiagnostics{},
        std::vector<double>(earth.cells.size(), 0.0),
        std::vector<double>(earth.cells.size(), 0.0),
        std::vector<double>(earth.cells.size(), 0.0),
        std::vector<double>(earth.cells.size(), 0.0)
    ));

    const HydrologyStabilizationResult initial_stabilization =
        stabilize_numeric_depressions(
            params,
            earth.cells,
            0,
            "initial_climate_hydrology",
            -1,
            earth.numeric_depression_fill_history,
            earth.hydrologic_water_budget_history
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
        earth.numeric_depression_fill_history,
        earth.hydrologic_water_budget_history,
        earth.sediment_routing_history,
        earth.hillslope_transport_history
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
            earth.numeric_depression_fill_history,
            earth.hydrologic_water_budget_history
        );
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
    natural.ice_sheets = generate_ice_sheets(earth.cells);
    natural.lake_basins = generate_lake_basins(params, earth.cells);
    natural.watersheds = generate_watersheds(params, earth.cells);
    natural.coastal_features = generate_coastal_features(params, earth.cells);
    natural.sedimentary_basins = generate_sedimentary_basins(earth.cells);
    natural.stratigraphic_columns = generate_stratigraphic_columns(
        earth.cells,
        natural.sedimentary_basins
    );

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
        society.trade_flows
    );
    society.historical_layers = generate_historical_layers(
        earth.cells,
        society.settlements,
        society.political_regions,
        society.borders,
        society.trade_flows,
        society.cultural_layers
    );
    society.population_regions = generate_population_regions(
        earth.cells,
        society.political_regions,
        society.cultural_layers
    );
    society.conflicts = generate_conflicts(
        earth.cells,
        society.political_regions,
        society.borders,
        society.trade_flows,
        society.cultural_layers,
        society.population_regions
    );
    society.dynasties = generate_dynasties(
        society.political_regions,
        society.cultural_layers,
        society.historical_layers,
        society.population_regions,
        society.conflicts
    );
    society.territorial_snapshots = generate_territorial_snapshots(
        params,
        earth.cells,
        society.political_regions,
        society.settlements,
        society.cultural_layers,
        society.historical_layers,
        society.population_regions,
        society.conflicts
    );
    world.calibration_checks = generate_calibration_checks(
        earth.cells,
        natural.watersheds
    );
    return world;
}

}  // namespace magic_geo::detail
