#include "internal.hpp"

namespace magic_geo::detail {
namespace {

constexpr std::array<double, 10> INITIAL_AGE_CDF_THRESHOLDS_MA = {
    20.0,
    40.0,
    60.0,
    80.0,
    100.0,
    120.0,
    140.0,
    160.0,
    180.0,
    200.0,
};

double great_circle_distance_km(
    double radius_km,
    Vec3 first,
    Vec3 second
) {
    const Vec3 cross_value = cross(first, second);
    const double angular_distance = std::atan2(
        norm(cross_value),
        clamp(dot(first, second), -1.0, 1.0)
    );
    const double distance_km = radius_km * angular_distance;
    if (!std::isfinite(distance_km) || distance_km < 0.0) {
        throw std::runtime_error(
            "initial oceanic crust age graph edge distance is invalid"
        );
    }
    return distance_km;
}

bool initial_oceanic_like(const Cell& cell) {
    return is_oceanic_crust_state(
        cell.crust_type,
        cell.lithology,
        cell.crust_age_ma,
        cell.crust_thickness_km,
        cell.crust_density
    );
}

}  // namespace

std::vector<double> build_initial_oceanic_crust_age_field(
    const Params& params,
    const std::vector<Cell>& cells,
    const std::vector<PlateBoundarySegment>& boundary_segments,
    InitialOceanicCrustAgeDiagnostics* diagnostics
) {
    if (cells.size() > static_cast<std::size_t>(
            std::numeric_limits<int>::max()
        )) {
        throw std::runtime_error(
            "initial oceanic crust age cell count exceeds int range"
        );
    }
    if (!std::isfinite(params.radius_km) || params.radius_km <= 0.0) {
        throw std::runtime_error(
            "initial oceanic crust age model requires positive finite radius"
        );
    }
    const double maximum_age_ma = crust_age_ceiling_ma(
        params,
        INITIAL_OCEANIC_CRUST_MAX_AGE_MA
    );
    InitialOceanicCrustAgeDiagnostics result;
    result.cell_count = static_cast<int>(cells.size());
    result.maximum_age_ma = maximum_age_ma;
    result.unclamped_graph_age_ma_by_cell.assign(cells.size(), -1.0);
    result.status_id_by_cell.assign(
        cells.size(), INITIAL_OCEANIC_AGE_NOT_OCEANIC_LIKE
    );
    result.predecessor_cell_id_by_cell.assign(cells.size(), -1);
    result.origin_ridge_seed_cell_id_by_cell.assign(cells.size(), -1);
    result.cdf_thresholds_ma.assign(
        INITIAL_AGE_CDF_THRESHOLDS_MA.begin(),
        INITIAL_AGE_CDF_THRESHOLDS_MA.end()
    );
    result.area_weighted_cdf_le_threshold.assign(
        INITIAL_AGE_CDF_THRESHOLDS_MA.size(), 0.0
    );
    std::vector<double> ages(cells.size(), 0.0);
    std::vector<bool> oceanic(cells.size(), false);
    for (std::size_t index = 0; index < cells.size(); ++index) {
        if (cells[index].id != static_cast<int>(index)) {
            throw std::runtime_error(
                "initial oceanic crust age cells are not in canonical id order"
            );
        }
        oceanic[index] = initial_oceanic_like(cells[index]);
        if (oceanic[index]) {
            ages[index] = std::numeric_limits<double>::infinity();
            result.oceanic_like_cell_count++;
        } else {
            result.non_oceanic_like_cell_count++;
        }
    }

    std::vector<int> ridge_seed_cell_ids;
    for (const PlateBoundarySegment& segment : boundary_segments) {
        if (
            segment.direct_boundary_class != "divergent" ||
            !segment.left_opening_oceanic_like ||
            !segment.right_opening_oceanic_like
        ) {
            continue;
        }
        if (
            segment.left_cell_id < 0 ||
            segment.right_cell_id < 0 ||
            segment.left_cell_id >= static_cast<int>(cells.size()) ||
            segment.right_cell_id >= static_cast<int>(cells.size()) ||
            !std::isfinite(segment.length_km) ||
            segment.length_km <= 0.0 ||
            !std::isfinite(segment.signed_opening_rate_km_per_ma) ||
            segment.signed_opening_rate_km_per_ma < 0.0
        ) {
            throw std::runtime_error(
                "initial oceanic crust age divergent segment is invalid"
            );
        }
        if (segment.signed_opening_rate_km_per_ma == 0.0) {
            // A geometrically divergent boundary with zero configured motion
            // is not an active spreading ridge.  With no positive-rate seed,
            // the containing oceanic component is handled below as an
            // unresolved extinct basin at the explicit age ceiling.
            continue;
        }
        result.eligible_ridge_segment_ids.push_back(segment.segment_id);
        result.opening_rate_length_sum_km2_per_ma +=
            segment.signed_opening_rate_km_per_ma * segment.length_km;
        result.eligible_ridge_total_length_km += segment.length_km;
        ridge_seed_cell_ids.push_back(segment.left_cell_id);
        ridge_seed_cell_ids.push_back(segment.right_cell_id);
    }
    std::sort(
        result.eligible_ridge_segment_ids.begin(),
        result.eligible_ridge_segment_ids.end()
    );
    std::sort(ridge_seed_cell_ids.begin(), ridge_seed_cell_ids.end());
    ridge_seed_cell_ids.erase(
        std::unique(
            ridge_seed_cell_ids.begin(),
            ridge_seed_cell_ids.end()
        ),
        ridge_seed_cell_ids.end()
    );
    result.ridge_seed_cell_ids = ridge_seed_cell_ids;

    result.representative_full_spreading_rate_km_per_ma =
        result.eligible_ridge_total_length_km > 0.0
            ? result.opening_rate_length_sum_km2_per_ma /
                result.eligible_ridge_total_length_km
            : 0.0;
    result.representative_half_spreading_rate_km_per_ma =
        0.5 * result.representative_full_spreading_rate_km_per_ma;
    if (
        !std::isfinite(
            result.representative_half_spreading_rate_km_per_ma
        ) ||
        result.representative_half_spreading_rate_km_per_ma < 0.0
    ) {
        throw std::runtime_error(
            "initial oceanic crust age representative spreading rate is invalid"
        );
    }

    using QueueEntry = std::pair<double, int>;
    std::priority_queue<
        QueueEntry,
        std::vector<QueueEntry>,
        std::greater<QueueEntry>
    > pending;
    if (result.representative_half_spreading_rate_km_per_ma > 0.0) {
        for (int cell_id : ridge_seed_cell_ids) {
            if (!oceanic[static_cast<std::size_t>(cell_id)]) {
                throw std::runtime_error(
                    "initial oceanic crust age ridge seed is not oceanic"
                );
            }
            ages[static_cast<std::size_t>(cell_id)] = 0.0;
            result.status_id_by_cell[static_cast<std::size_t>(cell_id)] =
                INITIAL_OCEANIC_AGE_RIDGE_SEED;
            result.origin_ridge_seed_cell_id_by_cell[
                static_cast<std::size_t>(cell_id)
            ] = cell_id;
            pending.emplace(0.0, cell_id);
        }
    }

    while (!pending.empty()) {
        const auto [current_age_ma, cell_id] = pending.top();
        pending.pop();
        if (current_age_ma != ages[static_cast<std::size_t>(cell_id)]) {
            continue;
        }
        const Cell& cell = cells[static_cast<std::size_t>(cell_id)];
        for (int neighbor_id : cell.neighbors) {
            if (
                neighbor_id < 0 ||
                neighbor_id >= static_cast<int>(cells.size())
            ) {
                throw std::runtime_error(
                    "initial oceanic crust age neighbor id is invalid"
                );
            }
            if (!oceanic[static_cast<std::size_t>(neighbor_id)]) {
                continue;
            }
            const double candidate_age_ma = current_age_ma +
                great_circle_distance_km(
                    params.radius_km,
                    cell.p,
                    cells[static_cast<std::size_t>(neighbor_id)].p
                ) /
                result.representative_half_spreading_rate_km_per_ma;
            if (
                candidate_age_ma <
                ages[static_cast<std::size_t>(neighbor_id)]
            ) {
                ages[static_cast<std::size_t>(neighbor_id)] =
                    candidate_age_ma;
                result.predecessor_cell_id_by_cell[
                    static_cast<std::size_t>(neighbor_id)
                ] = cell_id;
                result.origin_ridge_seed_cell_id_by_cell[
                    static_cast<std::size_t>(neighbor_id)
                ] = result.origin_ridge_seed_cell_id_by_cell[
                    static_cast<std::size_t>(cell_id)
                ];
                pending.emplace(candidate_age_ma, neighbor_id);
            }
        }
    }

    double age_area_sum_ma_km2 = 0.0;
    result.minimum_oceanic_like_age_ma =
        std::numeric_limits<double>::infinity();
    for (std::size_t index = 0; index < cells.size(); ++index) {
        if (!oceanic[index]) {
            ages[index] = 0.0;
            continue;
        }
        if (!std::isfinite(ages[index])) {
            // An oceanic graph component without an active divergent segment
            // represents an unresolved extinct basin.  Assigning the
            // procedural model ceiling is explicit and avoids inventing a
            // ridge or claiming a physical maximum seafloor age.
            ages[index] = maximum_age_ma;
            result.status_id_by_cell[index] =
                INITIAL_OCEANIC_AGE_UNRESOLVED_NO_ACTIVE_RIDGE_PATH_CEILING;
            result.unreachable_oceanic_like_cell_count++;
        } else {
            result.unclamped_graph_age_ma_by_cell[index] = ages[index];
            result.reachable_oceanic_like_cell_count++;
            if (ages[index] > maximum_age_ma) {
                result.status_id_by_cell[index] =
                    INITIAL_OCEANIC_AGE_RIDGE_REACHABLE_CEILING_CLAMPED;
                result.reachable_ceiling_clamped_cell_count++;
            } else if (
                result.status_id_by_cell[index] !=
                    INITIAL_OCEANIC_AGE_RIDGE_SEED
            ) {
                result.status_id_by_cell[index] =
                    INITIAL_OCEANIC_AGE_RIDGE_REACHABLE;
            }
            ages[index] = clamp(ages[index], 0.0, maximum_age_ma);
        }
        const double area_km2 = cells[index].area_km2;
        if (!std::isfinite(area_km2) || area_km2 < 0.0) {
            throw std::runtime_error(
                "initial oceanic crust age cell area is invalid"
            );
        }
        result.oceanic_like_area_km2 += area_km2;
        age_area_sum_ma_km2 += area_km2 * ages[index];
        result.minimum_oceanic_like_age_ma = std::min(
            result.minimum_oceanic_like_age_ma,
            ages[index]
        );
        result.maximum_oceanic_like_age_ma = std::max(
            result.maximum_oceanic_like_age_ma,
            ages[index]
        );
        for (std::size_t threshold_index = 0;
             threshold_index < result.cdf_thresholds_ma.size();
             ++threshold_index) {
            if (ages[index] <= result.cdf_thresholds_ma[threshold_index]) {
                result.area_weighted_cdf_le_threshold[threshold_index] +=
                    area_km2;
            }
        }
    }
    if (result.oceanic_like_cell_count == 0) {
        result.minimum_oceanic_like_age_ma = 0.0;
    }
    if (result.oceanic_like_area_km2 > 0.0) {
        result.area_weighted_mean_age_ma =
            age_area_sum_ma_km2 / result.oceanic_like_area_km2;
        for (double& value : result.area_weighted_cdf_le_threshold) {
            value /= result.oceanic_like_area_km2;
        }
    }
    if (
        !std::isfinite(result.opening_rate_length_sum_km2_per_ma) ||
        !std::isfinite(result.eligible_ridge_total_length_km) ||
        !std::isfinite(result.oceanic_like_area_km2) ||
        !std::isfinite(result.area_weighted_mean_age_ma)
    ) {
        throw std::runtime_error(
            "initial oceanic crust age diagnostic aggregate is invalid"
        );
    }
    result.age_ma_by_cell = ages;
    if (diagnostics != nullptr) {
        *diagnostics = std::move(result);
    }
    return ages;
}

}  // namespace magic_geo::detail
