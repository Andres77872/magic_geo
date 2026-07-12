#include "internal.hpp"
#include "world.hpp"

namespace magic_geo::detail {

std::string crust_material_shadow_model_json();
std::string crust_material_shadow_history_json(
    const std::vector<CrustMaterialShadowStep>& history
);
std::string summary_with_crust_material_shadow_json(
    std::string summary,
    const std::vector<CrustMaterialShadowStep>& history
);
std::string crust_dry_rock_accounting_model_json();
std::string crust_dry_rock_accounting_history_json(
    const std::vector<CrustDryRockAccountingStep>& history
);
std::string summary_with_crust_dry_rock_accounting_json(
    std::string summary,
    const std::vector<CrustDryRockAccountingStep>& history
);

std::string serialize_world(const Params& params, const GeneratedWorld& world) {
    const EarthSystemState& earth = world.earth;
    const NaturalArtifacts& natural = world.natural;
    const SocietyArtifacts& society = world.society;

    std::string out = "{";
    bool first = true;
    add_int(out, first, "schema_version", 1);
    add_str(out, first, "name", params.name);
    add_str(out, first, "mesh_backend", mesh_backend_name(params.mesh_backend));
    add_str(out, first, "cell_area_model", cell_area_model_name(params.mesh_backend));
    add_raw(out, first, "summary",
        summary_with_crust_dry_rock_accounting_json(
            summary_with_crust_material_shadow_json(summary_json(
            params,
            earth.cells,
            natural.watersheds,
            natural.lake_basins,
            natural.coastal_features,
            natural.sedimentary_basins,
            natural.stratigraphic_columns,
            natural.ice_sheets,
            society.political_regions,
            society.borders,
            society.trade_flows,
            society.cultural_layers,
            society.historical_layers,
            society.population_regions,
            society.conflicts,
            society.dynasties,
            society.territorial_snapshots,
            world.calibration_checks,
            society.settlements,
            society.routes,
            earth.feedback_history,
            earth.plate_motion_history,
            earth.numeric_depression_fill_history,
            earth.hillslope_transport_history,
            earth.glacial_transport_history
            ), earth.crust_material_shadow.history),
            earth.crust_dry_rock_accounting.history
        ));
    add_raw(out, first, "backend", backend_info_json());
    add_raw(out, first, "climate_model", climate_model_json(params));
    add_raw(out, first, "hydrologic_water_budget_model",
        hydrologic_water_budget_model_json(
            earth.hydrologic_water_budget_history,
            params.float_precision
        ));
    add_raw(out, first, "hydrologic_water_budget_history",
        hydrologic_water_budget_history_json(
            params,
            earth.hydrologic_water_budget_history,
            params.float_precision
        ));
    add_raw(out, first, "simulation_clock",
        simulation_clock_json(params, earth.feedback_history));
    add_raw(out, first, "earth_system_feedback_history",
        earth_system_feedback_history_json(
            params,
            earth.feedback_history,
            params.float_precision
        ));
    add_raw(out, first, "sediment_interface_model",
        sediment_interface_model_json(
            earth.cells,
            params.float_precision
        ));
    add_raw(out, first, "sediment_inventory_model",
        sediment_inventory_model_json(
            earth.cells,
            earth.feedback_history,
            earth.numeric_depression_fill_history,
            earth.hillslope_transport_history,
            earth.sediment_routing_history,
            earth.glacial_transport_history,
            params.float_precision
        ));
    add_raw(out, first, "numeric_depression_fill_history",
        numeric_depression_fill_history_json(
            params,
            earth.numeric_depression_fill_history,
            params.float_precision
        ));
    add_raw(out, first, "hillslope_sediment_transport_model",
        hillslope_sediment_transport_model_json(
            params,
            earth.hillslope_transport_history
        ));
    add_raw(out, first, "hillslope_sediment_transport_history",
        hillslope_sediment_transport_history_json(
            params,
            earth.hillslope_transport_history,
            params.float_precision
        ));
    add_raw(out, first, "glacial_sediment_transport_model",
        glacial_sediment_transport_model_json(
            earth.glacial_transport_history,
            params.float_precision
        ));
    add_raw(out, first, "glacial_sediment_transport_history",
        glacial_sediment_transport_history_json(
            params,
            earth.glacial_transport_history,
            params.float_precision
        ));
    add_raw(out, first, "fluvial_sediment_routing_model",
        fluvial_sediment_routing_model_json(
            earth.sediment_routing_history,
            params.float_precision
        ));
    add_raw(out, first, "fluvial_sediment_routing_history",
        fluvial_sediment_routing_history_json(
            params,
            earth.sediment_routing_history,
            params.float_precision
        ));
    add_raw(out, first, "plate_kinematic_model",
        plate_kinematic_model_json(
            params,
            earth.plate_motion_history,
            earth.cells
        ));
    add_raw(out, first, "plate_boundary_segment_model",
        plate_boundary_segment_model_json(
            params,
            earth.plate_motion_history
        ));
    add_raw(out, first, "initial_oceanic_crust_age_model",
        initial_oceanic_crust_age_model_json(
            earth.initial_oceanic_crust_age
        ));
    add_raw(out, first, "initial_oceanic_crust_age_ledger",
        initial_oceanic_crust_age_ledger_json(
            earth.initial_oceanic_crust_age
        ));
    add_raw(out, first, "crust_overlap_candidate_fate_model",
        crust_overlap_candidate_fate_model_json());
    add_raw(out, first, "oceanic_age_depth_model",
        oceanic_age_depth_model_json());
    add_raw(out, first, "crust_material_shadow_model",
        crust_material_shadow_model_json());
    add_raw(out, first, "crust_dry_rock_accounting_model",
        crust_dry_rock_accounting_model_json());
    add_raw(out, first, "sea_level_model",
        sea_level_model_json(params, earth.cells));
    add_raw(out, first, "plate_motion_history",
        plate_motion_history_json(
            params,
            earth.plate_motion_history,
            params.float_precision
        ));
    add_raw(out, first, "crust_material_shadow_history",
        crust_material_shadow_history_json(
            earth.crust_material_shadow.history
        ));
    add_raw(out, first, "crust_dry_rock_accounting_history",
        crust_dry_rock_accounting_history_json(
            earth.crust_dry_rock_accounting.history
        ));
    add_raw(out, first, "plates",
        plates_json(earth.plates, params.float_precision));
    add_raw(out, first, "watersheds",
        watersheds_json(natural.watersheds, params.float_precision));
    add_raw(out, first, "lake_basins",
        lake_basins_json(natural.lake_basins, params.float_precision));
    add_raw(out, first, "coastal_features",
        coastal_features_json(natural.coastal_features, params.float_precision));
    add_raw(out, first, "sedimentary_basins",
        sedimentary_basins_json(
            natural.sedimentary_basins,
            params.float_precision
        ));
    add_raw(out, first, "stratigraphic_columns",
        stratigraphic_columns_json(
            natural.stratigraphic_columns,
            params.float_precision
        ));
    add_raw(out, first, "ice_sheets",
        ice_sheets_json(natural.ice_sheets, params.float_precision));
    add_raw(out, first, "political_regions",
        political_regions_json(
            society.political_regions,
            params.float_precision
        ));
    add_raw(out, first, "cultures",
        cultures_json(
            society.cultural_layers.cultures,
            params.float_precision
        ));
    add_raw(out, first, "language_regions",
        language_regions_json(
            society.cultural_layers.language_regions,
            params.float_precision
        ));
    add_raw(out, first, "historical_eras",
        historical_eras_json(
            society.historical_layers.eras,
            params.float_precision
        ));
    add_raw(out, first, "historical_events",
        historical_events_json(
            society.historical_layers.events,
            params.float_precision
        ));
    add_raw(out, first, "population_regions",
        population_regions_json(
            society.population_regions,
            params.float_precision
        ));
    add_raw(out, first, "conflicts",
        conflicts_json(society.conflicts, params.float_precision));
    add_raw(out, first, "dynasties",
        dynasties_json(society.dynasties, params.float_precision));
    add_raw(out, first, "territorial_snapshots",
        territorial_snapshots_json(
            society.territorial_snapshots,
            params.float_precision
        ));
    add_raw(out, first, "calibration_checks",
        calibration_checks_json(
            world.calibration_checks,
            params.float_precision
        ));
    add_raw(out, first, "sacred_areas",
        sacred_areas_json(
            society.cultural_layers.sacred_areas,
            params.float_precision
        ));
    add_raw(out, first, "ruins",
        ruins_json(
            society.cultural_layers.ruins,
            params.float_precision
        ));
    add_raw(out, first, "borders",
        borders_json(society.borders, params.float_precision));
    add_raw(out, first, "settlements",
        settlements_json(
            earth.cells,
            society.settlements,
            params.float_precision
        ));
    add_raw(out, first, "routes",
        routes_json(society.routes, params.float_precision));
    add_raw(out, first, "trade_flows",
        trade_flows_json(society.trade_flows, params.float_precision));
    add_raw(out, first, "cells",
        params.include_cells ?
            cells_json(earth.cells, params.float_precision) : "[]");
    out += "}";
    return out;
}

}  // namespace magic_geo::detail
