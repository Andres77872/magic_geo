#include "engine/physical_columns.hpp"
#include "engine/types/core.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <vector>

namespace {

using namespace magic_geo::detail;

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << "check failed at line " << __LINE__ << ": "           \
                      << #condition << '\n';                                    \
            return false;                                                       \
        }                                                                       \
    } while (false)

bool close(long double actual, long double expected, long double relative = 3.0e-15L) {
    return std::abs(actual - expected) <= relative * std::max(1.0L, std::abs(expected));
}

template <typename Callable>
bool rejects(Callable&& callable) {
    try {
        callable();
    } catch (const std::runtime_error&) {
        return true;
    }
    return false;
}

bool normalized_pressure_mass_and_coefficients() {
    const std::vector<PrescribedSurfaceColumn> surfaces{
        {1.0e12, -1200.0, 4.0e6}, {2.0e12, 0.0, 8.0e6},
        {7.0e12, 2300.0, 2.0e8}, {3.0e11, 9000.0, 5.0e6},
    };
    PrescribedAtmosphereOptions options;
    options.mean_surface_pressure_pa = 73000.0;
    options.gravity_m_s2 = 7.1;
    options.profile_temperature_k = 260.0;
    options.reference_infrared_optical_depth = 1.7;
    options.greenhouse_factor = 0.8;
    options.atmospheric_diffusivity_m2_s = 123456.0;
    const auto result = build_prescribed_climate_columns(surfaces, options);
    const long double height = 287.05L * options.profile_temperature_k / options.gravity_m_s2;
    long double area = 0.0L;
    long double normalization = 0.0L;
    for (const auto& surface : surfaces) {
        area += surface.area_m2;
        normalization += surface.area_m2 * std::exp(-surface.interface_elevation_m / height);
    }
    long double pressure_area = 0.0L;
    CHECK(result.columns.size() == surfaces.size());
    for (std::size_t i = 0; i < surfaces.size(); ++i) {
        const long double pressure = options.mean_surface_pressure_pa * area *
            std::exp(-surfaces[i].interface_elevation_m / height) / normalization;
        const long double atmospheric_capacity = 1004.0L * pressure / options.gravity_m_s2;
        const long double tau = 1.7L * 0.8L * pressure / 100000.0L * 9.80665L / 7.1L;
        CHECK(close(result.surface_pressure_pa[i], pressure));
        CHECK(close(result.atmospheric_heat_capacity_j_m2_k[i], atmospheric_capacity));
        CHECK(close(result.infrared_optical_depth[i], tau));
        CHECK(close(result.horizontal_conductivity_w_k[i], 123456.0L * atmospheric_capacity));
        CHECK(close(result.columns[i].heat_capacity_j_m2_k,
                    surfaces[i].surface_heat_capacity_j_m2_k + atmospheric_capacity));
        CHECK(close(result.columns[i].longwave_emissivity, 1.0L / (1.0L + 0.75L * tau)));
        CHECK(result.columns[i].area_m2 == surfaces[i].area_m2);
        pressure_area += static_cast<long double>(surfaces[i].area_m2) * result.surface_pressure_pa[i];
        if (i > 0) {
            CHECK(close(result.surface_pressure_pa[i] / result.surface_pressure_pa[0],
                        std::exp(-(surfaces[i].interface_elevation_m - surfaces[0].interface_elevation_m) / height)));
        }
    }
    CHECK(close(result.total_area_m2, area));
    CHECK(close(result.atmospheric_scale_height_m, height));
    CHECK(close(result.area_weighted_mean_surface_pressure_pa, options.mean_surface_pressure_pa));
    CHECK(close(result.total_atmospheric_mass_kg, options.mean_surface_pressure_pa * area / options.gravity_m_s2));
    // Diagnostics expose the arithmetic residual of the represented columns;
    // they must not report a manufactured exact zero after recentering pressure.
    CHECK(result.mean_surface_pressure_residual_pa == static_cast<double>(
                pressure_area / area - options.mean_surface_pressure_pa));
    CHECK(result.atmospheric_mass_residual_kg == static_cast<double>(
                (pressure_area - options.mean_surface_pressure_pa * area) / options.gravity_m_s2));
    return true;
}

bool datum_area_and_pressure_scaling() {
    const std::vector<PrescribedSurfaceColumn> surfaces{
        {2.0, -1000.0, 4.0e6}, {3.0, 2000.0, 6.0e6}, {7.0, 4000.0, 8.0e6},
    };
    const auto reference = build_prescribed_climate_columns(surfaces);
    auto shifted = surfaces;
    for (auto& surface : shifted) surface.interface_elevation_m += 1.0e12;
    const auto datum = build_prescribed_climate_columns(shifted);
    for (std::size_t i = 0; i < surfaces.size(); ++i) {
        CHECK(datum.surface_pressure_pa[i] == reference.surface_pressure_pa[i]);
        CHECK(datum.columns[i].heat_capacity_j_m2_k == reference.columns[i].heat_capacity_j_m2_k);
        CHECK(datum.columns[i].longwave_emissivity == reference.columns[i].longwave_emissivity);
    }
    auto scaled = surfaces;
    for (auto& surface : scaled) surface.area_m2 *= 9.0;
    const auto larger = build_prescribed_climate_columns(scaled);
    PrescribedAtmosphereOptions double_pressure;
    double_pressure.mean_surface_pressure_pa *= 2.0;
    const auto denser = build_prescribed_climate_columns(surfaces, double_pressure);
    for (std::size_t i = 0; i < surfaces.size(); ++i) {
        CHECK(close(larger.surface_pressure_pa[i], reference.surface_pressure_pa[i]));
        CHECK(close(denser.surface_pressure_pa[i], 2.0 * reference.surface_pressure_pa[i]));
        CHECK(close(denser.infrared_optical_depth[i], 2.0 * reference.infrared_optical_depth[i]));
        CHECK(close(denser.horizontal_conductivity_w_k[i], 2.0 * reference.horizontal_conductivity_w_k[i]));
    }
    CHECK(close(larger.total_atmospheric_mass_kg, 9.0 * reference.total_atmospheric_mass_kg));
    return true;
}

bool flat_airless_and_high_storage_limits() {
    const std::vector<PrescribedSurfaceColumn> flat{{2.0e6, 1.0e100, 4.0e6}, {5.0e6, 1.0e100, 2.0e8}};
    const auto reference = build_prescribed_climate_columns(flat);
    for (std::size_t i = 0; i < flat.size(); ++i) {
        CHECK(reference.surface_pressure_pa[i] == 100000.0);
        CHECK(reference.infrared_optical_depth[i] == 1.0);
        CHECK(close(reference.columns[i].longwave_emissivity, 4.0L / 7.0L));
    }
    PrescribedAtmosphereOptions options;
    options.mean_surface_pressure_pa = 0.0;
    // Finite coefficients with no atmospheric mass do not create a ghost
    // atmosphere, even if products would overflow for a positive pressure.
    options.reference_infrared_optical_depth = std::numeric_limits<double>::max();
    options.greenhouse_factor = std::numeric_limits<double>::max();
    options.atmospheric_diffusivity_m2_s = std::numeric_limits<double>::max();
    const auto airless = build_prescribed_climate_columns(flat, options);
    for (std::size_t i = 0; i < flat.size(); ++i) {
        CHECK(airless.surface_pressure_pa[i] == 0.0);
        CHECK(airless.atmospheric_heat_capacity_j_m2_k[i] == 0.0);
        CHECK(airless.infrared_optical_depth[i] == 0.0);
        CHECK(airless.horizontal_conductivity_w_k[i] == 0.0);
        CHECK(airless.columns[i].heat_capacity_j_m2_k == flat[i].surface_heat_capacity_j_m2_k);
        CHECK(airless.columns[i].longwave_emissivity == 1.0);
    }
    CHECK(airless.total_atmospheric_mass_kg == 0.0);
    CHECK(airless.mean_surface_pressure_residual_pa == 0.0);
    CHECK(airless.atmospheric_mass_residual_kg == 0.0);
    options = {};
    options.mean_surface_pressure_pa = 1.0e8;
    options.gravity_m_s2 = 0.050001;
    const auto heavy = build_prescribed_climate_columns(flat, options);
    CHECK(close(heavy.atmospheric_heat_capacity_j_m2_k[0], 1004.0L * 1.0e8L / 0.050001L));
    CHECK(heavy.columns[0].heat_capacity_j_m2_k > 2.0e12);
    CHECK(heavy.columns[0].longwave_emissivity > 0.0);
    options = {};
    options.greenhouse_factor = 0.0;
    options.atmospheric_diffusivity_m2_s = 0.0;
    const auto transparent = build_prescribed_climate_columns(flat, options);
    CHECK(transparent.columns[0].longwave_emissivity == 1.0);
    CHECK(transparent.infrared_optical_depth[0] == 0.0);
    CHECK(transparent.horizontal_conductivity_w_k[0] == 0.0);
    CHECK(transparent.atmospheric_heat_capacity_j_m2_k[0] > 0.0);
    return true;
}

std::vector<Cell> fresh_cells() {
    std::vector<Cell> cells(5);
    const double elevations[]{1200.0, -30.0, -1.0e-8, -7.0, -500.0};
    for (std::size_t i = 0; i < cells.size(); ++i) {
        cells[i].id = static_cast<int>(i);
        cells[i].area_km2 = 0.5 + static_cast<double>(i);
        cells[i].elevation_m = elevations[i];
        cells[i].is_water = i >= 2;
        cells[i].water_body = cells[i].is_water ? 1 : 0;
        cells[i].water_depth_m = cells[i].is_water ? -cells[i].elevation_m : 0.0;
    }
    return cells;
}

bool actual_marine_storage_and_fresh_state() {
    auto cells = fresh_cells();
    const auto result = prescribed_surface_columns_from_cells(cells);
    CHECK(result.size() == cells.size());
    for (std::size_t i = 0; i < cells.size(); ++i) {
        CHECK(result[i].area_m2 == cells[i].area_km2 * 1.0e6);
        CHECK(result[i].interface_elevation_m == (cells[i].is_water ? 0.0 : cells[i].elevation_m));
    }
    CHECK(result[0].surface_heat_capacity_j_m2_k == 4.0e6);
    CHECK(result[1].surface_heat_capacity_j_m2_k == 4.0e6);
    CHECK(close(result[2].surface_heat_capacity_j_m2_k, 4.1813e6L * 1.0e-8L));
    CHECK(close(result[3].surface_heat_capacity_j_m2_k, 4.1813e6L * 7.0L));
    CHECK(close(result[4].surface_heat_capacity_j_m2_k, 4.1813e6L * 50.0L));
    const auto shallower = prescribed_surface_columns_from_cells(cells, 3.0);
    CHECK(shallower[2].surface_heat_capacity_j_m2_k == result[2].surface_heat_capacity_j_m2_k);
    CHECK(close(shallower[3].surface_heat_capacity_j_m2_k, 4.1813e6L * 3.0L));
    CHECK(shallower[4].surface_heat_capacity_j_m2_k == shallower[3].surface_heat_capacity_j_m2_k);
    // Downstream ice and diagnostic fields are not inputs to this prescription.
    for (auto& cell : cells) {
        cell.ice_thickness_m = 10000.0;
        cell.ice_sheet_id = 17;
        cell.biome = 999;
        cell.lake_fill_fraction = 0.8;
    }
    const auto later_diagnostics = prescribed_surface_columns_from_cells(cells);
    for (std::size_t i = 0; i < cells.size(); ++i) {
        CHECK(later_diagnostics[i].surface_heat_capacity_j_m2_k == result[i].surface_heat_capacity_j_m2_k);
        CHECK(later_diagnostics[i].interface_elevation_m == result[i].interface_elevation_m);
    }
    cells[3].is_lake = true;
    CHECK(rejects([&] { prescribed_surface_columns_from_cells(cells); }));
    cells[3].is_lake = false;
    for (int stale_code : {4, 5}) {
        cells[3].water_body = stale_code;
        CHECK(rejects([&] { prescribed_surface_columns_from_cells(cells); }));
    }
    cells = fresh_cells();
    cells[1].water_body = 4;
    CHECK(rejects([&] { prescribed_surface_columns_from_cells(cells); }));
    cells = fresh_cells();
    cells[3].water_body = 0;
    CHECK(rejects([&] { prescribed_surface_columns_from_cells(cells); }));
    for (int marine_code : {1, 2, 3}) {
        cells[3].water_body = marine_code;
        CHECK(prescribed_surface_columns_from_cells(cells)[3].surface_heat_capacity_j_m2_k ==
              result[3].surface_heat_capacity_j_m2_k);
    }
    return true;
}

bool invalid_and_unrepresentable_inputs() {
    const std::vector<PrescribedSurfaceColumn> good{{1.0, 0.0, 4.0e6}, {2.0, 1000.0, 4.0e6}};
    CHECK(rejects([&] { build_prescribed_climate_columns({}); }));
    for (double bad : {-1.0, std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN()}) {
        for (double PrescribedAtmosphereOptions::* member : {
                 &PrescribedAtmosphereOptions::mean_surface_pressure_pa,
                 &PrescribedAtmosphereOptions::reference_infrared_optical_depth,
                 &PrescribedAtmosphereOptions::greenhouse_factor,
                 &PrescribedAtmosphereOptions::atmospheric_diffusivity_m2_s,
                 &PrescribedAtmosphereOptions::gravity_m_s2,
                 &PrescribedAtmosphereOptions::profile_temperature_k}) {
            PrescribedAtmosphereOptions options;
            options.*member = bad;
            CHECK(rejects([&] { build_prescribed_climate_columns(good, options); }));
        }
    }
    for (double PrescribedAtmosphereOptions::* member : {
             &PrescribedAtmosphereOptions::gravity_m_s2, &PrescribedAtmosphereOptions::profile_temperature_k}) {
        PrescribedAtmosphereOptions options;
        options.*member = 0.0;
        CHECK(rejects([&] { build_prescribed_climate_columns(good, options); }));
    }
    for (double bad : {0.0, -1.0, std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN()}) {
        for (double PrescribedSurfaceColumn::* member : {
                 &PrescribedSurfaceColumn::area_m2, &PrescribedSurfaceColumn::surface_heat_capacity_j_m2_k}) {
            auto surfaces = good;
            surfaces[0].*member = bad;
            CHECK(rejects([&] { build_prescribed_climate_columns(surfaces); }));
        }
    }
    auto surfaces = good;
    surfaces[0].interface_elevation_m = std::numeric_limits<double>::infinity();
    CHECK(rejects([&] { build_prescribed_climate_columns(surfaces); }));
    surfaces = good;
    surfaces[1].interface_elevation_m = 1.0e20;
    CHECK(rejects([&] { build_prescribed_climate_columns(surfaces); }));
    for (double PrescribedAtmosphereOptions::* member : {
             &PrescribedAtmosphereOptions::mean_surface_pressure_pa,
             &PrescribedAtmosphereOptions::atmospheric_diffusivity_m2_s,
             &PrescribedAtmosphereOptions::profile_temperature_k}) {
        PrescribedAtmosphereOptions options;
        options.*member = std::numeric_limits<double>::max();
        CHECK(rejects([&] { build_prescribed_climate_columns(good, options); }));
    }
    PrescribedAtmosphereOptions options;
    options.reference_infrared_optical_depth = std::numeric_limits<double>::max();
    options.greenhouse_factor = 100.0;
    CHECK(rejects([&] { build_prescribed_climate_columns(good, options); }));
    options = {};
    options.reference_infrared_optical_depth = std::numeric_limits<double>::denorm_min();
    options.greenhouse_factor = 1.0e-300;
    CHECK(rejects([&] { build_prescribed_climate_columns(good, options); }));
    surfaces = good;
    for (auto& surface : surfaces) surface.area_m2 = 1.0e307;
    CHECK(rejects([&] { build_prescribed_climate_columns(surfaces); }));
    CHECK(rejects([&] { prescribed_surface_columns_from_cells({}); }));
    auto cells = fresh_cells();
    for (double bad : {0.0, -1.0, std::numeric_limits<double>::infinity()}) {
        CHECK(rejects([&] { prescribed_surface_columns_from_cells(cells, bad); }));
    }
    cells[0].id = 1;
    CHECK(rejects([&] { prescribed_surface_columns_from_cells(cells); }));
    cells = fresh_cells();
    cells[0].area_km2 = std::numeric_limits<double>::max();
    CHECK(rejects([&] { prescribed_surface_columns_from_cells(cells); }));
    cells = fresh_cells();
    cells[1].water_depth_m = 30.0;
    CHECK(rejects([&] { prescribed_surface_columns_from_cells(cells); }));
    cells = fresh_cells();
    cells[3].water_depth_m = std::nextafter(7.0, 8.0);
    CHECK(rejects([&] { prescribed_surface_columns_from_cells(cells); }));
    cells = fresh_cells();
    cells[3].elevation_m = 7.0;
    CHECK(rejects([&] { prescribed_surface_columns_from_cells(cells); }));
    cells = fresh_cells();
    cells[3].water_depth_m = 0.0;
    CHECK(rejects([&] { prescribed_surface_columns_from_cells(cells); }));
    return true;
}

}  // namespace

int main() {
    if (!normalized_pressure_mass_and_coefficients() ||
        !datum_area_and_pressure_scaling() ||
        !flat_airless_and_high_storage_limits() ||
        !actual_marine_storage_and_fresh_state() ||
        !invalid_and_unrepresentable_inputs()) {
        return 1;
    }
    return 0;
}
