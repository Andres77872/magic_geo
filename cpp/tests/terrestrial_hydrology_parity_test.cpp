#include "internal.hpp"
#include <iostream>

namespace magic_geo::detail {
HydrologicWaterBudgetStage compute_hydrologic_water_budget(
    std::vector<Cell>&, int, int, const std::string&, int, int);
}
int main() {
    using namespace magic_geo::detail;
    std::vector<Cell> cells(32);
    for (int i = 0; i < 32; ++i) {
        auto& c = cells[i];
        c.id = i;
        c.area_km2 = 1.25 + i * 1.5;
        c.elevation_m = (i % 7 - 3) * 1700.125;
        c.temperature_c = (i % 9 - 4) * 13.125;
        c.precipitation_mm_y = i == 0 ? 0 : (i % 6) * 271.25 + .125;
        c.sediment_thickness_m = (i % 5) * .875;
        c.lithology = i % 9;
        c.ice_thickness_m = (i % 4) * 33.125;
        c.is_water = i % 8 == 0;
        c.is_lake = i % 8 == 1;
        c.neighbors = {(i + 1) % 32, (i + 31) % 32};
    }
    const auto stage = compute_hydrologic_water_budget(cells, 3, 5,
        "deterministic_diverse_annual_parity", 2, 1);
    magic_geo::Params params;
    std::cout << "{\"history\":" << hydrologic_water_budget_history_json(params, {stage}, 17)
              << ",\"all_assigned_cell_fields\":[";
    for (std::size_t i = 0; i < cells.size(); ++i) {
        if (i) std::cout << ',';
        const auto& c = cells[i];
        std::cout << roundtrip_double_array_json({
            c.hydrologic_potential_evapotranspiration_mm_y,
            c.actual_evapotranspiration_mm_y, c.infiltration_capacity_index,
            c.infiltration_mm_y, c.hydrologic_water_balance_mm_y,
            c.water_budget_runoff_mm_y, c.runoff_mm_y,
            c.runoff_budget_residual_mm_y, c.runoff_budget_consistency_index,
            c.hydrologic_deficit_mm_y, c.runoff_generation_fraction});
    }
    std::cout << "]}\n";
}
