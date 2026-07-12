#include "engine/internal.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace magic_geo::detail {

// Minimal production-equivalent dependencies keep this unit test focused on
// the graph-age algorithm without linking the monolithic native engine.
double crust_age_ceiling_ma(const Params& params, double model_ceiling_ma) {
    return std::max(
        0.0,
        std::min(model_ceiling_ma, params.geological_age_ga * 1000.0)
    );
}

double dot(Vec3 a, Vec3 b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

Vec3 cross(Vec3 a, Vec3 b) {
    return {
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    };
}

double norm(Vec3 a) {
    return std::sqrt(dot(a, a));
}

bool is_oceanic_crust_state(
    int crust_type,
    int lithology,
    double age_ma,
    double thickness_km,
    double density
) {
    if (crust_type == 0) {
        return true;
    }
    if (crust_type == 2) {
        return lithology == 0;
    }
    return crust_type == 3 && age_ma <= 320.0 &&
        thickness_km <= 18.0 && density >= 2.84;
}

}  // namespace magic_geo::detail

namespace {

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << "check failed at line " << __LINE__ << ": "          \
                      << #condition << '\n';                                    \
            return false;                                                       \
        }                                                                       \
    } while (false)

using magic_geo::Params;
using magic_geo::detail::Cell;
using magic_geo::detail::InitialOceanicCrustAgeDiagnostics;
using magic_geo::detail::PlateBoundarySegment;
using magic_geo::detail::Vec3;

Cell oceanic_cell(int id, double longitude_rad, std::vector<int> neighbors) {
    Cell cell;
    cell.id = id;
    cell.p = {std::cos(longitude_rad), std::sin(longitude_rad), 0.0};
    cell.neighbors = std::move(neighbors);
    cell.crust_type = 0;
    cell.lithology = 0;
    cell.crust_age_ma = 0.0;
    cell.crust_thickness_km = 7.0;
    cell.crust_density = 3.0;
    cell.area_km2 = 1.0;
    return cell;
}

PlateBoundarySegment ridge_segment(
    int left_cell_id,
    int right_cell_id,
    double length_km,
    double full_spreading_rate_km_per_ma,
    int segment_id = 0
) {
    PlateBoundarySegment segment;
    segment.segment_id = segment_id;
    segment.left_cell_id = left_cell_id;
    segment.right_cell_id = right_cell_id;
    segment.length_km = length_km;
    segment.signed_opening_rate_km_per_ma =
        full_spreading_rate_km_per_ma;
    segment.direct_boundary_class = "divergent";
    segment.left_opening_oceanic_like = true;
    segment.right_opening_oceanic_like = true;
    return segment;
}

bool bilateral_distance_over_half_rate_is_exact() {
    Params params;
    params.radius_km = 1000.0;
    params.geological_age_ga = 4.5;
    std::vector<Cell> cells = {
        oceanic_cell(0, -0.15, {1}),
        oceanic_cell(1, -0.05, {0, 2}),
        oceanic_cell(2, 0.05, {1, 3}),
        oceanic_cell(3, 0.15, {2}),
    };
    InitialOceanicCrustAgeDiagnostics diagnostics;
    const std::vector<double> ages =
        magic_geo::detail::build_initial_oceanic_crust_age_field(
            params,
            cells,
            {ridge_segment(1, 2, 100.0, 20.0, 17)},
            &diagnostics
        );
    CHECK(ages.size() == 4);
    CHECK(ages[1] == 0.0);
    CHECK(ages[2] == 0.0);
    CHECK(std::abs(ages[0] - 10.0) < 1.0e-12);
    CHECK(std::abs(ages[3] - 10.0) < 1.0e-12);
    CHECK(diagnostics.age_ma_by_cell == ages);
    CHECK((diagnostics.eligible_ridge_segment_ids == std::vector<int>{17}));
    CHECK((diagnostics.ridge_seed_cell_ids == std::vector<int>{1, 2}));
    CHECK((diagnostics.status_id_by_cell == std::vector<int>{2, 1, 1, 2}));
    CHECK((diagnostics.predecessor_cell_id_by_cell ==
        std::vector<int>{1, -1, -1, 2}));
    CHECK((diagnostics.origin_ridge_seed_cell_id_by_cell ==
        std::vector<int>{1, 1, 2, 2}));
    CHECK(std::abs(diagnostics.unclamped_graph_age_ma_by_cell[0] - 10.0) <
        1.0e-12);
    CHECK(diagnostics.unclamped_graph_age_ma_by_cell[1] == 0.0);
    CHECK(diagnostics.unclamped_graph_age_ma_by_cell[2] == 0.0);
    CHECK(std::abs(diagnostics.unclamped_graph_age_ma_by_cell[3] - 10.0) <
        1.0e-12);
    CHECK(diagnostics.cell_count == 4);
    CHECK(diagnostics.oceanic_like_cell_count == 4);
    CHECK(diagnostics.non_oceanic_like_cell_count == 0);
    CHECK(diagnostics.reachable_oceanic_like_cell_count == 4);
    CHECK(diagnostics.unreachable_oceanic_like_cell_count == 0);
    CHECK(diagnostics.reachable_ceiling_clamped_cell_count == 0);
    CHECK(diagnostics.eligible_ridge_total_length_km == 100.0);
    CHECK(diagnostics.opening_rate_length_sum_km2_per_ma == 2000.0);
    CHECK(diagnostics.representative_full_spreading_rate_km_per_ma == 20.0);
    CHECK(diagnostics.representative_half_spreading_rate_km_per_ma == 10.0);
    CHECK(diagnostics.oceanic_like_area_km2 == 4.0);
    CHECK(std::abs(diagnostics.area_weighted_mean_age_ma - 5.0) < 1.0e-12);
    CHECK(diagnostics.area_weighted_cdf_le_threshold.front() == 1.0);
    return true;
}

bool length_weighted_global_rate_is_used() {
    Params params;
    params.radius_km = 1000.0;
    params.geological_age_ga = 4.5;
    std::vector<Cell> cells = {
        oceanic_cell(0, 0.0, {1}),
        oceanic_cell(1, 0.1, {0, 2}),
        oceanic_cell(2, 0.2, {1}),
    };
    const std::vector<PlateBoundarySegment> segments = {
        ridge_segment(0, 1, 1.0, 20.0, 7),
        ridge_segment(0, 1, 3.0, 40.0, 8),
    };
    InitialOceanicCrustAgeDiagnostics diagnostics;
    const std::vector<double> ages =
        magic_geo::detail::build_initial_oceanic_crust_age_field(
            params,
            cells,
            segments,
            &diagnostics
        );
    // Full rate=(1*20+3*40)/4=35 km/Ma; half rate=17.5 km/Ma.
    CHECK(ages[0] == 0.0);
    CHECK(ages[1] == 0.0);
    CHECK(std::abs(ages[2] - 100.0 / 17.5) < 1.0e-12);
    CHECK((diagnostics.eligible_ridge_segment_ids ==
        std::vector<int>{7, 8}));
    CHECK(diagnostics.eligible_ridge_total_length_km == 4.0);
    CHECK(diagnostics.opening_rate_length_sum_km2_per_ma == 140.0);
    CHECK(diagnostics.representative_full_spreading_rate_km_per_ma == 35.0);
    CHECK(diagnostics.representative_half_spreading_rate_km_per_ma == 17.5);
    return true;
}

bool zero_motion_and_disconnected_components_use_explicit_ceiling() {
    Params params;
    params.radius_km = 1000.0;
    params.geological_age_ga = 4.5;
    std::vector<Cell> cells = {
        oceanic_cell(0, 0.0, {1}),
        oceanic_cell(1, 0.1, {0}),
        oceanic_cell(2, 1.0, {}),
        oceanic_cell(3, 1.2, {}),
    };
    cells[3].crust_type = 1;
    cells[3].lithology = 1;
    cells[3].crust_thickness_km = 35.0;
    cells[3].crust_density = 2.72;
    InitialOceanicCrustAgeDiagnostics zero_motion_diagnostics;
    const std::vector<double> zero_motion_ages =
        magic_geo::detail::build_initial_oceanic_crust_age_field(
            params,
            cells,
            {ridge_segment(0, 1, 100.0, 0.0, 5)},
            &zero_motion_diagnostics
        );
    CHECK(zero_motion_ages[0] == 200.0);
    CHECK(zero_motion_ages[1] == 200.0);
    CHECK(zero_motion_ages[2] == 200.0);
    CHECK(zero_motion_ages[3] == 0.0);
    CHECK(zero_motion_diagnostics.eligible_ridge_segment_ids.empty());
    CHECK(zero_motion_diagnostics.ridge_seed_cell_ids.empty());
    CHECK(zero_motion_diagnostics.reachable_oceanic_like_cell_count == 0);
    CHECK(zero_motion_diagnostics.unreachable_oceanic_like_cell_count == 3);
    CHECK((zero_motion_diagnostics.status_id_by_cell ==
        std::vector<int>{4, 4, 4, 0}));
    CHECK((zero_motion_diagnostics.unclamped_graph_age_ma_by_cell ==
        std::vector<double>{-1.0, -1.0, -1.0, -1.0}));

    InitialOceanicCrustAgeDiagnostics active_diagnostics;
    const std::vector<double> active_ages =
        magic_geo::detail::build_initial_oceanic_crust_age_field(
            params,
            cells,
            {ridge_segment(0, 1, 100.0, 20.0, 6)},
            &active_diagnostics
        );
    CHECK(active_ages[0] == 0.0);
    CHECK(active_ages[1] == 0.0);
    CHECK(active_ages[2] == 200.0);
    CHECK(active_ages[3] == 0.0);
    CHECK((active_diagnostics.status_id_by_cell ==
        std::vector<int>{1, 1, 4, 0}));
    CHECK(active_diagnostics.reachable_oceanic_like_cell_count == 2);
    CHECK(active_diagnostics.unreachable_oceanic_like_cell_count == 1);
    CHECK(active_diagnostics.area_weighted_cdf_le_threshold.front() ==
        2.0 / 3.0);
    CHECK(active_diagnostics.area_weighted_cdf_le_threshold.back() == 1.0);
    return true;
}

bool planet_age_ceiling_and_invalid_rate_are_enforced() {
    Params params;
    params.radius_km = 1000.0;
    params.geological_age_ga = 0.05;
    const std::vector<Cell> cells = {
        oceanic_cell(0, 0.0, {1}),
        oceanic_cell(1, 0.1, {0, 2}),
        oceanic_cell(2, 2.0, {1}),
    };
    InitialOceanicCrustAgeDiagnostics diagnostics;
    const std::vector<double> ages =
        magic_geo::detail::build_initial_oceanic_crust_age_field(
            params,
            cells,
            {ridge_segment(0, 1, 100.0, 2.0, 11)},
            &diagnostics
        );
    CHECK(ages[0] == 0.0);
    CHECK(ages[1] == 0.0);
    CHECK(ages[2] == 50.0);
    CHECK(diagnostics.maximum_age_ma == 50.0);
    CHECK(diagnostics.reachable_ceiling_clamped_cell_count == 1);
    CHECK((diagnostics.status_id_by_cell == std::vector<int>{1, 1, 3}));
    CHECK(std::abs(diagnostics.unclamped_graph_age_ma_by_cell[2] - 1900.0) <
        1.0e-12);
    CHECK(diagnostics.predecessor_cell_id_by_cell[2] == 1);
    CHECK(diagnostics.origin_ridge_seed_cell_id_by_cell[2] == 1);

    bool threw = false;
    try {
        static_cast<void>(
            magic_geo::detail::build_initial_oceanic_crust_age_field(
                params,
                cells,
                {ridge_segment(0, 1, 100.0, -1.0)}
            )
        );
    } catch (const std::runtime_error&) {
        threw = true;
    }
    CHECK(threw);
    return true;
}

}  // namespace

int main() {
    return bilateral_distance_over_half_rate_is_exact() &&
        length_weighted_global_rate_is_used() &&
        zero_motion_and_disconnected_components_use_explicit_ceiling() &&
        planet_age_ceiling_and_invalid_rate_are_enforced()
        ? 0
        : 1;
}
