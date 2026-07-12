#include "engine/internal.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {

using namespace magic_geo::detail;

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << "check failed at line " << __LINE__ << ": "          \
                      << #condition << '\n';                                    \
            return false;                                                       \
        }                                                                       \
    } while (false)

bool close(double first, double second, double tolerance = 1.0e-12) {
    return std::abs(first - second) <= tolerance *
        std::max({1.0, std::abs(first), std::abs(second)});
}

double dot3(Vec3 first, Vec3 second) {
    return first.x * second.x + first.y * second.y + first.z * second.z;
}

double norm3(Vec3 value) {
    return std::sqrt(dot3(value, value));
}

Vec3 scale3(Vec3 value, double scale) {
    return {value.x * scale, value.y * scale, value.z * scale};
}

bool close3(Vec3 first, Vec3 second, double tolerance = 1.0e-12) {
    return close(first.x, second.x, tolerance) &&
        close(first.y, second.y, tolerance) &&
        close(first.z, second.z, tolerance);
}

std::vector<Cell> two_cell_three_segment_mesh(bool cross_plate = true) {
    const double root_three_over_two = std::sqrt(3.0) / 2.0;
    const Vec3 first{1.0, 0.0, 0.0};
    const Vec3 second{-0.5, root_three_over_two, 0.0};
    const Vec3 third{-0.5, -root_three_over_two, 0.0};

    Cell left;
    left.id = 0;
    left.p = {0.0, 0.0, 1.0};
    left.plate_id = 0;
    left.control_volume_vertices = {first, second, third};
    left.control_volume_edge_neighbor_ids = {1, 1, 1};

    Cell right;
    right.id = 1;
    right.p = {0.0, 0.0, -1.0};
    right.plate_id = cross_plate ? 1 : 0;
    right.control_volume_vertices = {first, third, second};
    right.control_volume_edge_neighbor_ids = {0, 0, 0};
    return {left, right};
}

std::vector<Cell> reversed_two_cell_three_segment_mesh() {
    std::vector<Cell> cells = two_cell_three_segment_mesh();
    std::swap(cells[0].p, cells[1].p);
    std::swap(
        cells[0].control_volume_vertices,
        cells[1].control_volume_vertices
    );
    return cells;
}

std::vector<Plate> two_plates() {
    Plate left;
    left.id = 0;
    left.axis = {1.0, 0.0, 0.0};
    left.angular_speed = 0.4;
    Plate right;
    right.id = 1;
    right.axis = {0.0, 1.0, 0.0};
    right.angular_speed = 0.7;
    return {left, right};
}

Plate plate_from_angular_velocity(int id, Vec3 angular_velocity) {
    const double speed = norm3(angular_velocity);
    Plate plate;
    plate.id = id;
    plate.axis = speed == 0.0
        ? Vec3{1.0, 0.0, 0.0}
        : scale3(angular_velocity, 1.0 / speed);
    plate.angular_speed = speed;
    return plate;
}

CrustTransportPlan opening_crust() {
    CrustTransportPlan plan;
    plan.remapped_crust_type_by_cell = {0, 1};
    plan.remapped_lithology_by_cell = {0, 1};
    plan.remapped_crust_age_ma_by_cell = {20.0, 1200.0};
    plan.remapped_crust_thickness_km_by_cell = {7.0, 35.0};
    plan.remapped_crust_density_by_cell = {3.0, 2.72};
    return plan;
}

CrustTransportPlan reversed_opening_crust() {
    CrustTransportPlan plan = opening_crust();
    std::swap(
        plan.remapped_crust_type_by_cell[0],
        plan.remapped_crust_type_by_cell[1]
    );
    std::swap(
        plan.remapped_lithology_by_cell[0],
        plan.remapped_lithology_by_cell[1]
    );
    std::swap(
        plan.remapped_crust_age_ma_by_cell[0],
        plan.remapped_crust_age_ma_by_cell[1]
    );
    std::swap(
        plan.remapped_crust_thickness_km_by_cell[0],
        plan.remapped_crust_thickness_km_by_cell[1]
    );
    std::swap(
        plan.remapped_crust_density_by_cell[0],
        plan.remapped_crust_density_by_cell[1]
    );
    return plan;
}

template <typename Callable>
bool throws_runtime_error(Callable&& callable) {
    try {
        callable();
    } catch (const std::runtime_error&) {
        return true;
    }
    return false;
}

bool canonical_geometry_kinematics_and_polarity_are_exact() {
    magic_geo::Params params;
    params.radius_km = 6371.0;
    params.plate_motion_scale_deg_per_step = 2.0;
    const std::vector<Cell> cells = two_cell_three_segment_mesh();
    const std::vector<Plate> plates = two_plates();
    const CrustTransportPlan crust = opening_crust();
    int mesh_segment_count = -1;
    const std::vector<PlateBoundarySegment> segments =
        build_plate_boundary_segments(
            params, cells, plates, crust, &mesh_segment_count
        );
    CHECK(mesh_segment_count == 3);
    CHECK(segments.size() == 3);
    const double velocity_scale = params.radius_km *
        params.plate_motion_scale_deg_per_step * (PI / 180.0) /
        MATURATION_REFERENCE_TIMESTEP_MA;
    bool saw_convergent = false;
    for (std::size_t index = 0; index < segments.size(); ++index) {
        const PlateBoundarySegment& segment = segments[index];
        CHECK(segment.segment_id == static_cast<int>(index));
        CHECK(segment.mesh_segment_id == static_cast<int>(index));
        CHECK(segment.left_cell_id == 0);
        CHECK(segment.right_cell_id == 1);
        CHECK(segment.left_edge_index == static_cast<int>(index));
        CHECK(segment.right_edge_index == 2 - static_cast<int>(index));
        CHECK(segment.left_plate_id == 0);
        CHECK(segment.right_plate_id == 1);
        CHECK(close(norm3(segment.start_unit), 1.0));
        CHECK(close(norm3(segment.midpoint_unit), 1.0));
        CHECK(close(norm3(segment.end_unit), 1.0));
        CHECK(close(norm3(segment.tangent_unit), 1.0));
        CHECK(close(norm3(segment.left_to_right_normal_unit), 1.0));
        CHECK(close(dot3(segment.midpoint_unit, segment.tangent_unit), 0.0));
        CHECK(close(
            dot3(segment.midpoint_unit, segment.left_to_right_normal_unit),
            0.0
        ));
        CHECK(close(
            dot3(segment.tangent_unit, segment.left_to_right_normal_unit),
            0.0
        ));
        CHECK(segment.left_to_right_normal_unit.z < -0.999999999999);
        CHECK(close(segment.angular_length_rad, 2.0 * PI / 3.0));
        CHECK(close(
            segment.length_km,
            params.radius_km * segment.angular_length_rad
        ));
        CHECK(close(
            segment.relative_velocity_km_per_ma.x,
            segment.right_euler_velocity_km_per_ma.x -
                segment.left_euler_velocity_km_per_ma.x
        ));
        CHECK(close(
            segment.relative_velocity_km_per_ma.y,
            segment.right_euler_velocity_km_per_ma.y -
                segment.left_euler_velocity_km_per_ma.y
        ));
        CHECK(close(
            segment.relative_velocity_km_per_ma.z,
            segment.right_euler_velocity_km_per_ma.z -
                segment.left_euler_velocity_km_per_ma.z
        ));
        CHECK(close(
            segment.signed_opening_rate_km_per_ma,
            segment.signed_opening_index * velocity_scale
        ));
        CHECK(close(
            segment.signed_convergence_rate_km_per_ma,
            -segment.signed_opening_rate_km_per_ma
        ));
        CHECK(close(
            segment.signed_slip_rate_km_per_ma,
            segment.signed_slip_index * velocity_scale
        ));
        CHECK(close(
            segment.direct_convergent_strength,
            std::clamp(segment.signed_convergence_index * 1.25, 0.0, 1.0)
        ));
        CHECK(close(
            segment.direct_divergent_strength,
            std::clamp(segment.signed_opening_index * 1.25, 0.0, 1.0)
        ));
        CHECK(close(
            segment.direct_transform_strength,
            std::clamp(
                (std::abs(segment.signed_slip_index) -
                    0.35 * std::abs(segment.signed_opening_index)) * 1.05,
                0.0,
                1.0
            )
        ));
        CHECK(segment.left_opening_oceanic_like);
        CHECK(!segment.right_opening_oceanic_like);
        CHECK(segment.left_opening_crust_state_available);
        CHECK(segment.right_opening_crust_state_available);
        if (segment.convergence_active) {
            saw_convergent = true;
            CHECK(segment.polarity_candidate_status == "left_oceanic_only");
            CHECK(segment.candidate_subducting_side == "left");
            CHECK(segment.candidate_overriding_side == "right");
            CHECK(segment.physical_polarity_status == "unknown_unresolved");
            CHECK(segment.physical_polarity_source == "none");
            CHECK(segment.physical_subducting_side == "unknown");
            CHECK(segment.physical_overriding_side == "unknown");
            CHECK(segment.physical_polarity_confidence == 0.0);
        } else {
            CHECK(
                segment.polarity_candidate_status == "no_active_convergence"
            );
            CHECK(segment.candidate_subducting_side == "none");
            CHECK(segment.candidate_overriding_side == "none");
            CHECK(
                segment.physical_polarity_status ==
                "not_applicable_no_active_convergence"
            );
            CHECK(segment.physical_polarity_source == "none");
            CHECK(segment.physical_subducting_side == "none");
            CHECK(segment.physical_overriding_side == "none");
            CHECK(segment.physical_polarity_confidence == 0.0);
        }
    }
    CHECK(saw_convergent);
    return true;
}

bool analytic_euler_modes_and_invariances_are_exact() {
    magic_geo::Params params;
    params.radius_km = 6371.0;
    params.plate_motion_scale_deg_per_step = 2.0;
    const std::vector<Cell> cells = two_cell_three_segment_mesh();
    const CrustTransportPlan crust = opening_crust();
    int mesh_segment_count = -1;

    // Edge zero has midpoint (1/2, sqrt(3)/2, 0), tangent
    // (-sqrt(3)/2, 1/2, 0), and left-to-right normal (0, 0, -1).
    const double root_three_over_two = std::sqrt(3.0) / 2.0;
    const Vec3 midpoint{0.5, root_three_over_two, 0.0};
    const Vec3 tangent{-root_three_over_two, 0.5, 0.0};

    Plate stationary;
    stationary.id = 0;
    stationary.axis = {1.0, 0.0, 0.0};
    stationary.angular_speed = 0.0;

    Plate moving;
    moving.id = 1;
    moving.axis = tangent;
    moving.angular_speed = 0.6;
    std::vector<Plate> plates{stationary, moving};
    std::vector<PlateBoundarySegment> segments = build_plate_boundary_segments(
        params, cells, plates, crust, &mesh_segment_count
    );
    CHECK(mesh_segment_count == 3);
    CHECK(segments.size() == 3);
    const PlateBoundarySegment& opening = segments[0];
    CHECK(close3(opening.midpoint_unit, midpoint));
    CHECK(close(opening.signed_opening_index, 0.6));
    CHECK(close(opening.signed_convergence_index, -0.6));
    CHECK(close(opening.signed_slip_index, 0.0));
    CHECK(opening.direct_boundary_class == "divergent");
    CHECK(!opening.convergence_active);
    CHECK(opening.polarity_candidate_status == "no_active_convergence");

    plates[1].axis = scale3(tangent, -1.0);
    segments = build_plate_boundary_segments(
        params, cells, plates, crust, &mesh_segment_count
    );
    const PlateBoundarySegment& convergence = segments[0];
    CHECK(close(convergence.signed_opening_index, -0.6));
    CHECK(close(convergence.signed_convergence_index, 0.6));
    CHECK(close(convergence.signed_slip_index, 0.0));
    CHECK(convergence.direct_boundary_class == "convergent");
    CHECK(convergence.convergence_active);

    // A transform-dominant oblique boundary still has active normal
    // convergence, so polarity must remain unknown/candidate-eligible rather
    // than becoming physically not applicable.
    plates[1] = plate_from_angular_velocity(
        1,
        {0.4 * root_three_over_two, -0.2, 0.8}
    );
    segments = build_plate_boundary_segments(
        params, cells, plates, crust, &mesh_segment_count
    );
    const PlateBoundarySegment& oblique = segments[0];
    CHECK(close(oblique.signed_convergence_index, 0.4));
    CHECK(close(oblique.signed_slip_index, 0.8));
    CHECK(oblique.direct_boundary_class == "transform");
    CHECK(oblique.convergence_active);
    CHECK(oblique.polarity_candidate_status == "left_oceanic_only");
    CHECK(oblique.candidate_subducting_side == "left");
    CHECK(oblique.candidate_overriding_side == "right");
    CHECK(oblique.physical_polarity_status == "unknown_unresolved");
    CHECK(oblique.physical_subducting_side == "unknown");
    CHECK(oblique.physical_overriding_side == "unknown");

    plates[1].axis = {0.0, 0.0, 1.0};
    plates[1].angular_speed = 0.6;
    segments = build_plate_boundary_segments(
        params, cells, plates, crust, &mesh_segment_count
    );
    const PlateBoundarySegment& slip = segments[0];
    CHECK(close(slip.signed_opening_index, 0.0));
    CHECK(close(slip.signed_convergence_index, 0.0));
    CHECK(close(slip.signed_slip_index, 0.6));
    CHECK(slip.direct_boundary_class == "transform");
    CHECK(!slip.convergence_active);
    CHECK(slip.polarity_candidate_status == "no_active_convergence");

    // A common rigid angular velocity cancels from every relative field.
    Plate common_left;
    common_left.id = 0;
    common_left.axis = {0.0, 0.0, 1.0};
    common_left.angular_speed = 0.75;
    Plate common_right = common_left;
    common_right.id = 1;
    segments = build_plate_boundary_segments(
        params,
        cells,
        std::vector<Plate>{common_left, common_right},
        crust,
        &mesh_segment_count
    );
    for (const PlateBoundarySegment& segment : segments) {
        CHECK(close3(
            segment.left_euler_velocity_km_per_ma,
            segment.right_euler_velocity_km_per_ma
        ));
        CHECK(close3(segment.relative_velocity_km_per_ma, {0.0, 0.0, 0.0}));
        CHECK(close(segment.signed_opening_index, 0.0));
        CHECK(close(segment.signed_convergence_index, 0.0));
        CHECK(close(segment.signed_slip_index, 0.0));
        CHECK(segment.direct_boundary_class == "inactive");
    }


    // Adding one arbitrary angular-velocity vector to both unequal plates
    // changes their absolute velocities but not their relative kinematics.
    const std::vector<Plate> unequal = two_plates();
    const std::vector<PlateBoundarySegment> unequal_segments =
        build_plate_boundary_segments(
            params, cells, unequal, crust, &mesh_segment_count
        );
    const Vec3 common_offset{0.1, -0.2, 0.3};
    const std::vector<Plate> shifted{
        plate_from_angular_velocity(0, {0.5, -0.2, 0.3}),
        plate_from_angular_velocity(1, {0.1, 0.5, 0.3}),
    };
    const std::vector<PlateBoundarySegment> shifted_segments =
        build_plate_boundary_segments(
            params, cells, shifted, crust, &mesh_segment_count
        );
    CHECK(unequal_segments.size() == shifted_segments.size());
    CHECK(norm3(common_offset) > 0.0);
    for (std::size_t index = 0; index < unequal_segments.size(); ++index) {
        const PlateBoundarySegment& first = unequal_segments[index];
        const PlateBoundarySegment& second = shifted_segments[index];
        CHECK(close3(
            first.relative_velocity_km_per_ma,
            second.relative_velocity_km_per_ma
        ));
        CHECK(close(first.signed_opening_index, second.signed_opening_index));
        CHECK(close(
            first.signed_convergence_index,
            second.signed_convergence_index
        ));
        CHECK(close(first.signed_slip_index, second.signed_slip_index));
        CHECK(close(
            first.signed_opening_rate_km_per_ma,
            second.signed_opening_rate_km_per_ma
        ));
        CHECK(close(
            first.signed_convergence_rate_km_per_ma,
            second.signed_convergence_rate_km_per_ma
        ));
        CHECK(close(
            first.signed_slip_rate_km_per_ma,
            second.signed_slip_rate_km_per_ma
        ));
        CHECK(close(
            first.direct_convergent_strength,
            second.direct_convergent_strength
        ));
        CHECK(close(
            first.direct_divergent_strength,
            second.direct_divergent_strength
        ));
        CHECK(close(
            first.direct_transform_strength,
            second.direct_transform_strength
        ));
        CHECK(first.direct_boundary_class == second.direct_boundary_class);
    }

    // At an Euler pole omega x r is zero even for non-zero angular speed.
    plates = {stationary, moving};
    plates[1].axis = midpoint;
    plates[1].angular_speed = 0.9;
    segments = build_plate_boundary_segments(
        params, cells, plates, crust, &mesh_segment_count
    );
    const PlateBoundarySegment& pole = segments[0];
    CHECK(close3(pole.right_euler_velocity_km_per_ma, {0.0, 0.0, 0.0}));
    CHECK(close3(pole.relative_velocity_km_per_ma, {0.0, 0.0, 0.0}));
    CHECK(close(pole.signed_opening_index, 0.0));
    CHECK(close(pole.signed_slip_index, 0.0));
    CHECK(pole.direct_boundary_class == "inactive");
    return true;
}

bool radius_and_canonical_orientation_invariances_are_exact() {
    magic_geo::Params base_params;
    base_params.radius_km = 3100.0;
    base_params.plate_motion_scale_deg_per_step = 1.7;
    magic_geo::Params scaled_params = base_params;
    const double radius_factor = 2.5;
    scaled_params.radius_km *= radius_factor;
    const std::vector<Cell> cells = two_cell_three_segment_mesh();
    const std::vector<Plate> plates = two_plates();
    const CrustTransportPlan crust = opening_crust();
    int mesh_segment_count = -1;
    const std::vector<PlateBoundarySegment> base = build_plate_boundary_segments(
        base_params, cells, plates, crust, &mesh_segment_count
    );
    CHECK(mesh_segment_count == 3);
    const std::vector<PlateBoundarySegment> scaled =
        build_plate_boundary_segments(
            scaled_params, cells, plates, crust, &mesh_segment_count
        );
    CHECK(base.size() == scaled.size());
    for (std::size_t index = 0; index < base.size(); ++index) {
        const PlateBoundarySegment& first = base[index];
        const PlateBoundarySegment& second = scaled[index];
        CHECK(close(first.angular_length_rad, second.angular_length_rad));
        CHECK(close(second.length_km, first.length_km * radius_factor));
        CHECK(close(first.signed_opening_index, second.signed_opening_index));
        CHECK(close(
            first.signed_convergence_index,
            second.signed_convergence_index
        ));
        CHECK(close(first.signed_slip_index, second.signed_slip_index));
        CHECK(first.direct_boundary_class == second.direct_boundary_class);
        CHECK(close3(
            second.left_euler_velocity_km_per_ma,
            scale3(first.left_euler_velocity_km_per_ma, radius_factor)
        ));
        CHECK(close3(
            second.right_euler_velocity_km_per_ma,
            scale3(first.right_euler_velocity_km_per_ma, radius_factor)
        ));
        CHECK(close3(
            second.relative_velocity_km_per_ma,
            scale3(first.relative_velocity_km_per_ma, radius_factor)
        ));
        CHECK(close(
            second.signed_opening_rate_km_per_ma,
            first.signed_opening_rate_km_per_ma * radius_factor
        ));
        CHECK(close(
            second.signed_convergence_rate_km_per_ma,
            first.signed_convergence_rate_km_per_ma * radius_factor
        ));
        CHECK(close(
            second.signed_slip_rate_km_per_ma,
            first.signed_slip_rate_km_per_ma * radius_factor
        ));
    }

    std::vector<Plate> reversed_plates{plates[1], plates[0]};
    reversed_plates[0].id = 0;
    reversed_plates[1].id = 1;
    const std::vector<PlateBoundarySegment> reversed =
        build_plate_boundary_segments(
            base_params,
            reversed_two_cell_three_segment_mesh(),
            reversed_plates,
            reversed_opening_crust(),
            &mesh_segment_count
        );
    CHECK(base.size() == reversed.size());
    for (std::size_t index = 0; index < base.size(); ++index) {
        const PlateBoundarySegment& forward = base[index];
        const PlateBoundarySegment& backward =
            reversed[base.size() - 1 - index];
        CHECK(close3(backward.start_unit, forward.end_unit));
        CHECK(close3(backward.midpoint_unit, forward.midpoint_unit));
        CHECK(close3(backward.end_unit, forward.start_unit));
        CHECK(close3(
            backward.tangent_unit,
            scale3(forward.tangent_unit, -1.0)
        ));
        CHECK(close3(
            backward.left_to_right_normal_unit,
            scale3(forward.left_to_right_normal_unit, -1.0)
        ));
        CHECK(close3(
            backward.left_euler_velocity_km_per_ma,
            forward.right_euler_velocity_km_per_ma
        ));
        CHECK(close3(
            backward.right_euler_velocity_km_per_ma,
            forward.left_euler_velocity_km_per_ma
        ));
        CHECK(close3(
            backward.relative_velocity_km_per_ma,
            scale3(forward.relative_velocity_km_per_ma, -1.0)
        ));
        CHECK(close(
            backward.signed_opening_index,
            forward.signed_opening_index
        ));
        CHECK(close(
            backward.signed_convergence_index,
            forward.signed_convergence_index
        ));
        CHECK(close(backward.signed_slip_index, forward.signed_slip_index));
        CHECK(close(
            backward.signed_opening_rate_km_per_ma,
            forward.signed_opening_rate_km_per_ma
        ));
        CHECK(close(
            backward.signed_convergence_rate_km_per_ma,
            forward.signed_convergence_rate_km_per_ma
        ));
        CHECK(close(
            backward.signed_slip_rate_km_per_ma,
            forward.signed_slip_rate_km_per_ma
        ));
        CHECK(
            backward.direct_boundary_class == forward.direct_boundary_class
        );
        CHECK(
            backward.left_opening_crust_type ==
            forward.right_opening_crust_type
        );
        CHECK(
            backward.right_opening_crust_type ==
            forward.left_opening_crust_type
        );
        if (forward.candidate_subducting_side == "left") {
            CHECK(backward.candidate_subducting_side == "right");
            CHECK(backward.candidate_overriding_side == "left");
        } else if (forward.candidate_subducting_side == "right") {
            CHECK(backward.candidate_subducting_side == "left");
            CHECK(backward.candidate_overriding_side == "right");
        } else {
            CHECK(backward.candidate_subducting_side == "none");
            CHECK(backward.candidate_overriding_side == "none");
        }
        CHECK(
            backward.physical_polarity_status ==
            forward.physical_polarity_status
        );
        CHECK(
            backward.physical_subducting_side ==
            forward.physical_subducting_side
        );
        CHECK(
            backward.physical_overriding_side ==
            forward.physical_overriding_side
        );
    }

    // Ledger rates in km/Ma are numerically equal to rates in mm/yr because
    // both numerator and denominator acquire the same factor of one million.
    constexpr double MM_PER_KM = 1.0e6;
    constexpr double YEARS_PER_MA = 1.0e6;
    constexpr double KM_PER_MA_TO_MM_PER_YR = MM_PER_KM / YEARS_PER_MA;
    static_assert(KM_PER_MA_TO_MM_PER_YR == 1.0);
    CHECK(close(KM_PER_MA_TO_MM_PER_YR, 1.0));
    return true;
}

bool reciprocal_matching_and_guards_fail_closed() {
    magic_geo::Params params;
    std::vector<Cell> cells = two_cell_three_segment_mesh();
    std::vector<Plate> plates = two_plates();
    CrustTransportPlan crust = opening_crust();
    int count = -1;

    std::vector<Cell> same_plate_cells = two_cell_three_segment_mesh(false);
    CHECK(build_plate_boundary_segments(
        params, same_plate_cells, plates, crust, &count
    ).empty());
    CHECK(count == 3);

    cells[1].control_volume_vertices[0].z = 0.01;
    CHECK(throws_runtime_error([&]() {
        build_plate_boundary_segments(params, cells, plates, crust, &count);
    }));

    cells = two_cell_three_segment_mesh();
    for (Cell& cell : cells) {
        cell.p.x *= 2.0;
        cell.p.y *= 2.0;
        cell.p.z *= 2.0;
        for (Vec3& vertex : cell.control_volume_vertices) {
            vertex.x *= 2.0;
            vertex.y *= 2.0;
            vertex.z *= 2.0;
        }
    }
    CHECK(throws_runtime_error([&]() {
        build_plate_boundary_segments(params, cells, plates, crust, &count);
    }));

    cells = two_cell_three_segment_mesh();
    cells[0].p.x = std::numeric_limits<double>::quiet_NaN();
    CHECK(throws_runtime_error([&]() {
        build_plate_boundary_segments(params, cells, plates, crust, &count);
    }));

    cells = two_cell_three_segment_mesh();
    cells[0].control_volume_vertices.resize(2);
    cells[0].control_volume_edge_neighbor_ids.resize(2);
    CHECK(throws_runtime_error([&]() {
        build_plate_boundary_segments(params, cells, plates, crust, &count);
    }));

    cells = two_cell_three_segment_mesh();
    crust = opening_crust();
    crust.remapped_crust_type_by_cell[0] =
        static_cast<int>(CRUST_NAMES.size());
    CHECK(throws_runtime_error([&]() {
        build_plate_boundary_segments(params, cells, plates, crust, &count);
    }));
    crust = opening_crust();
    crust.remapped_lithology_by_cell[0] = -1;
    CHECK(throws_runtime_error([&]() {
        build_plate_boundary_segments(params, cells, plates, crust, &count);
    }));

    crust = opening_crust();
    cells = two_cell_three_segment_mesh();
    plates[1].axis = {0.0, 2.0, 0.0};
    CHECK(throws_runtime_error([&]() {
        build_plate_boundary_segments(params, cells, plates, crust, &count);
    }));

    plates = two_plates();
    plates[1].angular_speed = -0.1;
    CHECK(throws_runtime_error([&]() {
        build_plate_boundary_segments(params, cells, plates, crust, &count);
    }));

    plates = two_plates();
    CrustTransportPlan unavailable_crust = opening_crust();
    unavailable_crust.remapped_crust_age_ma_by_cell[1] = 0.0;
    unavailable_crust.remapped_crust_thickness_km_by_cell[1] = 0.0;
    const std::vector<PlateBoundarySegment> unavailable_segments =
        build_plate_boundary_segments(
            params, cells, plates, unavailable_crust, &count
        );
    bool saw_unresolved_missing_state = false;
    for (const PlateBoundarySegment& segment : unavailable_segments) {
        CHECK(segment.left_opening_crust_state_available);
        CHECK(!segment.right_opening_crust_state_available);
        CHECK(!segment.right_opening_oceanic_like);
        if (segment.convergence_active) {
            saw_unresolved_missing_state = true;
            CHECK(
                segment.polarity_candidate_status ==
                "unresolved_missing_opening_crust_state"
            );
        }
    }
    CHECK(saw_unresolved_missing_state);

    crust = opening_crust();
    crust.remapped_crust_thickness_km_by_cell[0] = 0.0;
    CHECK(throws_runtime_error([&]() {
        build_plate_boundary_segments(params, cells, plates, crust, &count);
    }));

    cells = two_cell_three_segment_mesh();
    cells[0].control_volume_vertices.assign(65, Vec3{1.0, 0.0, 0.0});
    cells[0].control_volume_edge_neighbor_ids.assign(65, 1);
    crust = opening_crust();
    CHECK(throws_runtime_error([&]() {
        build_plate_boundary_segments(params, cells, plates, crust, &count);
    }));
    return true;
}

}  // namespace

int main() {
    if (!canonical_geometry_kinematics_and_polarity_are_exact() ||
        !analytic_euler_modes_and_invariances_are_exact() ||
        !radius_and_canonical_orientation_invariances_are_exact() ||
        !reciprocal_matching_and_guards_fail_closed()) {
        return 1;
    }
    return 0;
}
