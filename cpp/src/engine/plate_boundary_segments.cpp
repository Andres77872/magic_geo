#include "internal.hpp"

namespace magic_geo::detail {
namespace {

constexpr double RECIPROCAL_ENDPOINT_TOLERANCE = 1.0e-10;
constexpr std::size_t MAX_CONTROL_VOLUME_SEGMENTS_PER_CELL = 64;
constexpr std::size_t MAX_RECIPROCAL_MESH_SEGMENTS_PER_CELL = 8;
constexpr double EULER_AXIS_UNIT_TOLERANCE = 1.0e-12;
constexpr double UNIT_SPHERE_VECTOR_NORM_TOLERANCE = 3.0e-12;

double dot3(Vec3 first, Vec3 second) {
    return first.x * second.x + first.y * second.y + first.z * second.z;
}

Vec3 add3(Vec3 first, Vec3 second) {
    return {
        first.x + second.x,
        first.y + second.y,
        first.z + second.z,
    };
}

Vec3 subtract3(Vec3 first, Vec3 second) {
    return {
        first.x - second.x,
        first.y - second.y,
        first.z - second.z,
    };
}

Vec3 scale3(Vec3 value, double scale) {
    return {value.x * scale, value.y * scale, value.z * scale};
}

Vec3 cross3(Vec3 first, Vec3 second) {
    return {
        first.y * second.z - first.z * second.y,
        first.z * second.x - first.x * second.z,
        first.x * second.y - first.y * second.x,
    };
}

double norm3(Vec3 value) {
    return std::sqrt(dot3(value, value));
}

Vec3 checked_normalize3(Vec3 value, const char* context) {
    const double magnitude = norm3(value);
    if (!std::isfinite(magnitude) || magnitude <= 1.0e-14) {
        throw std::runtime_error(
            std::string("plate-boundary ") + context + " is degenerate"
        );
    }
    return scale3(value, 1.0 / magnitude);
}

void require_finite3(Vec3 value, const char* context) {
    if (
        !std::isfinite(value.x) ||
        !std::isfinite(value.y) ||
        !std::isfinite(value.z)
    ) {
        throw std::runtime_error(
            std::string("plate-boundary ") + context + " is not finite"
        );
    }
}

bool oceanic_like_opening_state(
    int crust_type,
    int lithology,
    double age_ma,
    double thickness_km,
    double density_g_cm3
) {
    if (crust_type == 0) {
        return true;
    }
    if (crust_type == 2) {
        return lithology == 0;
    }
    return crust_type == 3 && age_ma <= 320.0 && thickness_km <= 18.0 &&
        density_g_cm3 >= 2.84;
}

double reverse_endpoint_error(
    Vec3 start,
    Vec3 end,
    Vec3 reciprocal_start,
    Vec3 reciprocal_end
) {
    return std::max(
        norm3(subtract3(start, reciprocal_end)),
        norm3(subtract3(end, reciprocal_start))
    );
}

const char* direct_boundary_class(
    double convergent,
    double divergent,
    double transform
) {
    const double maximum = std::max(convergent, std::max(divergent, transform));
    if (maximum < 0.08) {
        return "inactive";
    }
    if (convergent == maximum) {
        return "convergent";
    }
    if (divergent == maximum) {
        return "divergent";
    }
    return "transform";
}

void validate_opening_crust_arrays(
    const CrustTransportPlan& opening_crust,
    std::size_t cell_count
) {
    for (std::size_t size : {
        opening_crust.remapped_crust_type_by_cell.size(),
        opening_crust.remapped_lithology_by_cell.size(),
        opening_crust.remapped_crust_age_ma_by_cell.size(),
        opening_crust.remapped_crust_thickness_km_by_cell.size(),
        opening_crust.remapped_crust_density_by_cell.size(),
    }) {
        if (size != cell_count) {
            throw std::runtime_error(
                "plate-boundary opening/remapped crust array size mismatch"
            );
        }
    }
    for (std::size_t index = 0; index < cell_count; ++index) {
        const int crust_type =
            opening_crust.remapped_crust_type_by_cell[index];
        const int lithology =
            opening_crust.remapped_lithology_by_cell[index];
        const double age_ma =
            opening_crust.remapped_crust_age_ma_by_cell[index];
        const double thickness_km =
            opening_crust.remapped_crust_thickness_km_by_cell[index];
        const double density_g_cm3 =
            opening_crust.remapped_crust_density_by_cell[index];
        if (
            crust_type < 0 ||
            crust_type >= static_cast<int>(CRUST_NAMES.size()) ||
            lithology < 0 ||
            lithology >= static_cast<int>(LITHOLOGY_NAMES.size())
        ) {
            throw std::runtime_error(
                "plate-boundary opening/remapped crust category is invalid"
            );
        }
        if (
            !std::isfinite(age_ma) || age_ma < 0.0 ||
            !std::isfinite(thickness_km) || thickness_km < 0.0 ||
            !std::isfinite(density_g_cm3) || density_g_cm3 <= 0.0
        ) {
            throw std::runtime_error(
                "plate-boundary opening/remapped crust state is invalid"
            );
        }
        const bool unavailable =
            age_ma == 0.0 && thickness_km == 0.0;
        if (!unavailable && thickness_km <= 0.0) {
            throw std::runtime_error(
                "plate-boundary opening/remapped crust state is partial"
            );
        }
    }
}

}  // namespace

std::vector<PlateBoundarySegment> build_plate_boundary_segments(
    const Params& params,
    const std::vector<Cell>& cells,
    const std::vector<Plate>& plates,
    const CrustTransportPlan& opening_crust,
    int* reciprocal_mesh_segment_count
) {
    if (reciprocal_mesh_segment_count == nullptr) {
        throw std::runtime_error(
            "plate-boundary reciprocal mesh segment count output is null"
        );
    }
    *reciprocal_mesh_segment_count = 0;
    validate_opening_crust_arrays(opening_crust, cells.size());
    if (
        !std::isfinite(params.radius_km) || params.radius_km <= 0.0 ||
        !std::isfinite(params.plate_motion_scale_deg_per_step) ||
        params.plate_motion_scale_deg_per_step < 0.0
    ) {
        throw std::runtime_error(
            "plate-boundary nominal velocity scale inputs are invalid"
        );
    }
    const double velocity_scale_km_per_ma =
        params.radius_km * params.plate_motion_scale_deg_per_step *
        (PI / 180.0) / MATURATION_REFERENCE_TIMESTEP_MA;
    if (!std::isfinite(velocity_scale_km_per_ma)) {
        throw std::runtime_error(
            "plate-boundary nominal velocity scale is not finite"
        );
    }

    std::vector<std::vector<bool>> reciprocal_edge_used;
    reciprocal_edge_used.reserve(cells.size());
    for (std::size_t cell_index = 0; cell_index < cells.size(); ++cell_index) {
        const Cell& cell = cells[cell_index];
        if (cell.id != static_cast<int>(cell_index)) {
            throw std::runtime_error(
                "plate-boundary cells are not in canonical id order"
            );
        }
        require_finite3(cell.p, "cell position");
        if (
            std::abs(norm3(cell.p) - 1.0) >
                UNIT_SPHERE_VECTOR_NORM_TOLERANCE
        ) {
            throw std::runtime_error(
                "plate-boundary cell position is not on the unit sphere"
            );
        }
        if (
            cell.control_volume_vertices.size() !=
                cell.control_volume_edge_neighbor_ids.size() ||
            cell.control_volume_vertices.size() < 3
        ) {
            throw std::runtime_error(
                "plate-boundary control-volume geometry is incomplete"
            );
        }
        if (
            cell.control_volume_vertices.size() >
                MAX_CONTROL_VOLUME_SEGMENTS_PER_CELL
        ) {
            throw std::runtime_error(
                "plate-boundary per-cell control-volume segment cap exceeded"
            );
        }
        if (
            cell.plate_id < 0 ||
            cell.plate_id >= static_cast<int>(plates.size())
        ) {
            throw std::runtime_error("plate-boundary plate id is invalid");
        }
        for (const Vec3& vertex : cell.control_volume_vertices) {
            require_finite3(vertex, "control-volume vertex");
            if (
                std::abs(norm3(vertex) - 1.0) >
                    UNIT_SPHERE_VECTOR_NORM_TOLERANCE
            ) {
                throw std::runtime_error(
                    "plate-boundary control-volume vertex is not on the unit sphere"
                );
            }
        }
        reciprocal_edge_used.emplace_back(
            cell.control_volume_vertices.size(), false
        );
    }

    std::vector<PlateBoundarySegment> segments;
    int mesh_segment_id = 0;
    for (std::size_t left_index = 0; left_index < cells.size(); ++left_index) {
        const Cell& left = cells[left_index];
        for (std::size_t left_edge_index = 0;
             left_edge_index < left.control_volume_vertices.size();
             ++left_edge_index) {
            const int right_cell_id =
                left.control_volume_edge_neighbor_ids[left_edge_index];
            if (
                right_cell_id < 0 ||
                right_cell_id >= static_cast<int>(cells.size()) ||
                right_cell_id == static_cast<int>(left_index)
            ) {
                throw std::runtime_error(
                    "plate-boundary control-volume neighbor id is invalid"
                );
            }
            if (right_cell_id < static_cast<int>(left_index)) {
                continue;
            }

            const Cell& right = cells[static_cast<std::size_t>(right_cell_id)];
            const Vec3 start = left.control_volume_vertices[left_edge_index];
            const Vec3 end = left.control_volume_vertices[
                (left_edge_index + 1) % left.control_volume_vertices.size()
            ];
            require_finite3(start, "segment start");
            require_finite3(end, "segment end");

            int right_edge_index = -1;
            int matching_edge_count = 0;
            for (std::size_t candidate_index = 0;
                 candidate_index < right.control_volume_vertices.size();
                 ++candidate_index) {
                if (
                    right.control_volume_edge_neighbor_ids[candidate_index] !=
                        static_cast<int>(left_index) ||
                    reciprocal_edge_used[static_cast<std::size_t>(right_cell_id)]
                        [candidate_index]
                ) {
                    continue;
                }
                const Vec3 reciprocal_start =
                    right.control_volume_vertices[candidate_index];
                const Vec3 reciprocal_end = right.control_volume_vertices[
                    (candidate_index + 1) %
                    right.control_volume_vertices.size()
                ];
                if (
                    reverse_endpoint_error(
                        start, end, reciprocal_start, reciprocal_end
                    ) <= RECIPROCAL_ENDPOINT_TOLERANCE
                ) {
                    right_edge_index = static_cast<int>(candidate_index);
                    matching_edge_count++;
                }
            }
            if (matching_edge_count != 1) {
                throw std::runtime_error(
                    "plate-boundary segment lacks one unique reciprocal edge"
                );
            }
            reciprocal_edge_used[static_cast<std::size_t>(right_cell_id)]
                [static_cast<std::size_t>(right_edge_index)] = true;

            const int current_mesh_segment_id = mesh_segment_id++;
            if (
                static_cast<std::size_t>(mesh_segment_id) >
                MAX_RECIPROCAL_MESH_SEGMENTS_PER_CELL * cells.size()
            ) {
                throw std::runtime_error(
                    "plate-boundary reciprocal mesh segment cap exceeded"
                );
            }
            if (left.plate_id == right.plate_id) {
                continue;
            }

            const Vec3 edge_plane_normal = checked_normalize3(
                cross3(start, end), "edge plane normal"
            );
            if (dot3(left.p, edge_plane_normal) <= 0.0) {
                throw std::runtime_error(
                    "plate-boundary canonical left edge is not counter-clockwise"
                );
            }
            const Vec3 midpoint = checked_normalize3(
                add3(start, end), "segment midpoint"
            );
            const Vec3 tangent = checked_normalize3(
                cross3(edge_plane_normal, midpoint), "segment tangent"
            );
            const Vec3 left_to_right_normal = checked_normalize3(
                cross3(tangent, midpoint), "left-to-right normal"
            );
            if (
                dot3(
                    left_to_right_normal,
                    subtract3(right.p, left.p)
                ) <= 0.0
            ) {
                throw std::runtime_error(
                    "plate-boundary normal does not point left-to-right"
                );
            }
            const double angular_length = std::atan2(
                norm3(cross3(start, end)),
                std::clamp(dot3(start, end), -1.0, 1.0)
            );
            if (!std::isfinite(angular_length) || angular_length <= 0.0) {
                throw std::runtime_error(
                    "plate-boundary angular segment length is invalid"
                );
            }

            const Plate& left_plate =
                plates[static_cast<std::size_t>(left.plate_id)];
            const Plate& right_plate =
                plates[static_cast<std::size_t>(right.plate_id)];
            require_finite3(left_plate.axis, "left Euler axis");
            require_finite3(right_plate.axis, "right Euler axis");
            if (
                std::abs(norm3(left_plate.axis) - 1.0) >
                    EULER_AXIS_UNIT_TOLERANCE ||
                std::abs(norm3(right_plate.axis) - 1.0) >
                    EULER_AXIS_UNIT_TOLERANCE
            ) {
                throw std::runtime_error(
                    "plate-boundary Euler axis is not unit length"
                );
            }
            if (
                !std::isfinite(left_plate.angular_speed) ||
                left_plate.angular_speed < 0.0 ||
                !std::isfinite(right_plate.angular_speed) ||
                right_plate.angular_speed < 0.0
            ) {
                throw std::runtime_error(
                    "plate-boundary intrinsic angular speed is not finite"
                );
            }
            const Vec3 left_raw_velocity = cross3(
                scale3(left_plate.axis, left_plate.angular_speed), midpoint
            );
            const Vec3 right_raw_velocity = cross3(
                scale3(right_plate.axis, right_plate.angular_speed), midpoint
            );
            const Vec3 raw_relative_velocity =
                subtract3(right_raw_velocity, left_raw_velocity);
            const double signed_opening_index =
                dot3(raw_relative_velocity, left_to_right_normal);
            const double signed_slip_index =
                dot3(raw_relative_velocity, tangent);
            const Vec3 left_velocity =
                scale3(left_raw_velocity, velocity_scale_km_per_ma);
            const Vec3 right_velocity =
                scale3(right_raw_velocity, velocity_scale_km_per_ma);
            const Vec3 relative_velocity =
                subtract3(right_velocity, left_velocity);
            const double signed_opening_rate =
                dot3(relative_velocity, left_to_right_normal);
            const double signed_slip_rate =
                dot3(relative_velocity, tangent);

            PlateBoundarySegment segment;
            segment.segment_id = static_cast<int>(segments.size());
            segment.mesh_segment_id = current_mesh_segment_id;
            segment.left_cell_id = static_cast<int>(left_index);
            segment.right_cell_id = right_cell_id;
            segment.left_edge_index = static_cast<int>(left_edge_index);
            segment.right_edge_index = right_edge_index;
            segment.left_plate_id = left.plate_id;
            segment.right_plate_id = right.plate_id;
            segment.start_unit = start;
            segment.midpoint_unit = midpoint;
            segment.end_unit = end;
            segment.tangent_unit = tangent;
            segment.left_to_right_normal_unit = left_to_right_normal;
            segment.angular_length_rad = angular_length;
            segment.length_km = params.radius_km * angular_length;
            segment.left_euler_velocity_km_per_ma = left_velocity;
            segment.right_euler_velocity_km_per_ma = right_velocity;
            segment.relative_velocity_km_per_ma = relative_velocity;
            segment.signed_opening_rate_km_per_ma = signed_opening_rate;
            segment.signed_convergence_rate_km_per_ma = -signed_opening_rate;
            segment.signed_slip_rate_km_per_ma = signed_slip_rate;
            segment.signed_opening_index = signed_opening_index;
            segment.signed_convergence_index = -signed_opening_index;
            segment.signed_slip_index = signed_slip_index;
            segment.direct_convergent_strength = std::clamp(
                segment.signed_convergence_index * 1.25, 0.0, 1.0
            );
            segment.direct_divergent_strength = std::clamp(
                segment.signed_opening_index * 1.25, 0.0, 1.0
            );
            segment.direct_transform_strength = std::clamp(
                (
                    std::abs(segment.signed_slip_index) -
                    std::abs(segment.signed_opening_index) * 0.35
                ) * 1.05,
                0.0,
                1.0
            );
            segment.direct_boundary_class = direct_boundary_class(
                segment.direct_convergent_strength,
                segment.direct_divergent_strength,
                segment.direct_transform_strength
            );
            segment.convergence_active =
                segment.direct_convergent_strength >= 0.08;

            const std::size_t left_crust_index = left_index;
            const std::size_t right_crust_index =
                static_cast<std::size_t>(right_cell_id);
            segment.left_opening_crust_type =
                opening_crust.remapped_crust_type_by_cell[left_crust_index];
            segment.left_opening_lithology =
                opening_crust.remapped_lithology_by_cell[left_crust_index];
            segment.left_opening_crust_age_ma =
                opening_crust.remapped_crust_age_ma_by_cell[left_crust_index];
            segment.left_opening_crust_thickness_km =
                opening_crust.remapped_crust_thickness_km_by_cell[
                    left_crust_index
                ];
            segment.left_opening_crust_density_g_cm3 =
                opening_crust.remapped_crust_density_by_cell[left_crust_index];
            segment.left_opening_crust_state_available = !(
                segment.left_opening_crust_age_ma == 0.0 &&
                segment.left_opening_crust_thickness_km == 0.0
            );
            segment.left_opening_oceanic_like =
                segment.left_opening_crust_state_available &&
                oceanic_like_opening_state(
                    segment.left_opening_crust_type,
                    segment.left_opening_lithology,
                    segment.left_opening_crust_age_ma,
                    segment.left_opening_crust_thickness_km,
                    segment.left_opening_crust_density_g_cm3
                );
            segment.right_opening_crust_type =
                opening_crust.remapped_crust_type_by_cell[right_crust_index];
            segment.right_opening_lithology =
                opening_crust.remapped_lithology_by_cell[right_crust_index];
            segment.right_opening_crust_age_ma =
                opening_crust.remapped_crust_age_ma_by_cell[right_crust_index];
            segment.right_opening_crust_thickness_km =
                opening_crust.remapped_crust_thickness_km_by_cell[
                    right_crust_index
                ];
            segment.right_opening_crust_density_g_cm3 =
                opening_crust.remapped_crust_density_by_cell[
                    right_crust_index
                ];
            segment.right_opening_crust_state_available = !(
                segment.right_opening_crust_age_ma == 0.0 &&
                segment.right_opening_crust_thickness_km == 0.0
            );
            segment.right_opening_oceanic_like =
                segment.right_opening_crust_state_available &&
                oceanic_like_opening_state(
                    segment.right_opening_crust_type,
                    segment.right_opening_lithology,
                    segment.right_opening_crust_age_ma,
                    segment.right_opening_crust_thickness_km,
                    segment.right_opening_crust_density_g_cm3
                );
            if (!segment.convergence_active) {
                segment.polarity_candidate_status = "no_active_convergence";
            } else if (
                !segment.left_opening_crust_state_available ||
                !segment.right_opening_crust_state_available
            ) {
                segment.polarity_candidate_status =
                    "unresolved_missing_opening_crust_state";
            } else if (
                segment.left_opening_oceanic_like &&
                !segment.right_opening_oceanic_like
            ) {
                segment.polarity_candidate_status = "left_oceanic_only";
            } else if (
                !segment.left_opening_oceanic_like &&
                segment.right_opening_oceanic_like
            ) {
                segment.polarity_candidate_status = "right_oceanic_only";
            } else if (
                segment.left_opening_oceanic_like &&
                segment.right_opening_oceanic_like
            ) {
                segment.polarity_candidate_status =
                    "ambiguous_both_oceanic";
            } else {
                segment.polarity_candidate_status =
                    "unresolved_no_oceanic_side";
            }
            if (segment.polarity_candidate_status == "left_oceanic_only") {
                segment.candidate_subducting_side = "left";
                segment.candidate_overriding_side = "right";
            } else if (
                segment.polarity_candidate_status == "right_oceanic_only"
            ) {
                segment.candidate_subducting_side = "right";
                segment.candidate_overriding_side = "left";
            } else {
                segment.candidate_subducting_side = "none";
                segment.candidate_overriding_side = "none";
            }
            segment.physical_polarity_source = "none";
            segment.physical_polarity_confidence = 0.0;
            if (segment.convergence_active) {
                segment.physical_polarity_status = "unknown_unresolved";
                segment.physical_subducting_side = "unknown";
                segment.physical_overriding_side = "unknown";
            } else {
                segment.physical_polarity_status =
                    "not_applicable_no_active_convergence";
                segment.physical_subducting_side = "none";
                segment.physical_overriding_side = "none";
            }
            segments.push_back(std::move(segment));
        }
    }

    for (std::size_t cell_index = 0; cell_index < cells.size(); ++cell_index) {
        const Cell& cell = cells[cell_index];
        for (std::size_t edge_index = 0;
             edge_index < cell.control_volume_vertices.size();
             ++edge_index) {
            if (
                cell.control_volume_edge_neighbor_ids[edge_index] <
                    static_cast<int>(cell_index) &&
                !reciprocal_edge_used[cell_index][edge_index]
            ) {
                throw std::runtime_error(
                    "plate-boundary reciprocal edge was not consumed"
                );
            }
        }
    }
    *reciprocal_mesh_segment_count = mesh_segment_id;
    return segments;
}

}  // namespace magic_geo::detail
