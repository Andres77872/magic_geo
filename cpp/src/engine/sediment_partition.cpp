#include "internal.hpp"

namespace magic_geo::detail {

namespace {

long double forward_error_bound(
    long double absolute_term_sum,
    std::size_t arithmetic_term_count,
    long double absolute_floor
) {
    return std::max(
        absolute_floor,
        128.0L * static_cast<long double>(
            std::numeric_limits<double>::epsilon()
        ) * static_cast<long double>(
            std::max<std::size_t>(1, arithmetic_term_count)
        ) * (1.0L + std::abs(absolute_term_sum))
    );
}

void require_context(const char* context) {
    if (context == nullptr || *context == '\0') {
        throw std::runtime_error(
            "sediment-interface validation context is missing"
        );
    }
}

double checked_interface_value(long double value, const char* message) {
    if (
        !std::isfinite(value) ||
        std::abs(value) > static_cast<long double>(
            std::numeric_limits<double>::max()
        )
    ) {
        throw std::runtime_error(message);
    }
    return static_cast<double>(value);
}

void validate_interface_values(
    double bedrock_surface_elevation_m,
    double sediment_thickness_m,
    double elevation_m,
    const char* context
) {
    require_context(context);
    if (
        !std::isfinite(bedrock_surface_elevation_m) ||
        !std::isfinite(sediment_thickness_m) ||
        sediment_thickness_m < 0.0 ||
        !std::isfinite(elevation_m)
    ) {
        throw std::runtime_error(
            std::string(context) +
            " sediment-interface state is nonfinite or negative"
        );
    }
    const long double reconstructed_surface_m =
        static_cast<long double>(bedrock_surface_elevation_m) +
        static_cast<long double>(sediment_thickness_m);
    const long double term_sum =
        std::abs(static_cast<long double>(elevation_m)) +
        std::abs(static_cast<long double>(bedrock_surface_elevation_m)) +
        std::abs(static_cast<long double>(sediment_thickness_m));
    if (
        std::abs(
            static_cast<long double>(elevation_m) -
            reconstructed_surface_m
        ) > forward_error_bound(term_sum, 3, 1.0e-12L)
    ) {
        throw std::runtime_error(
            std::string(context) +
            " sediment-interface surface closure failed"
        );
    }
}

}  // namespace

void validate_sediment_interface(const Cell& cell, const char* context) {
    validate_interface_values(
        cell.bedrock_surface_elevation_m,
        cell.sediment_thickness_m,
        cell.elevation_m,
        context
    );
}

void initialize_sediment_interface(Cell& cell, const char* context) {
    require_context(context);
    if (
        !std::isfinite(cell.elevation_m) ||
        !std::isfinite(cell.sediment_thickness_m) ||
        cell.sediment_thickness_m < 0.0
    ) {
        throw std::runtime_error(
            std::string(context) +
            " sediment-interface initialization input is invalid"
        );
    }
    const double bedrock_surface_elevation_m = checked_interface_value(
        static_cast<long double>(cell.elevation_m) -
            static_cast<long double>(cell.sediment_thickness_m),
        "sediment-interface initialization overflowed"
    );
    const double elevation_m = checked_interface_value(
        static_cast<long double>(bedrock_surface_elevation_m) +
            static_cast<long double>(cell.sediment_thickness_m),
        "sediment-interface initialized surface overflowed"
    );
    validate_interface_values(
        bedrock_surface_elevation_m,
        cell.sediment_thickness_m,
        elevation_m,
        context
    );
    cell.bedrock_surface_elevation_m = bedrock_surface_elevation_m;
    cell.elevation_m = elevation_m;
}

void shift_sediment_interface_datum(
    Cell& cell,
    double elevation_change_m,
    const char* context
) {
    validate_sediment_interface(cell, context);
    if (!std::isfinite(elevation_change_m)) {
        throw std::runtime_error(
            std::string(context) +
            " sediment-interface datum shift is nonfinite"
        );
    }
    const double bedrock_surface_elevation_m = checked_interface_value(
        static_cast<long double>(cell.bedrock_surface_elevation_m) +
            static_cast<long double>(elevation_change_m),
        "sediment-interface datum shift overflowed"
    );
    const double elevation_m = checked_interface_value(
        static_cast<long double>(bedrock_surface_elevation_m) +
            static_cast<long double>(cell.sediment_thickness_m),
        "sediment-interface shifted surface overflowed"
    );
    validate_interface_values(
        bedrock_surface_elevation_m,
        cell.sediment_thickness_m,
        elevation_m,
        context
    );
    cell.bedrock_surface_elevation_m = bedrock_surface_elevation_m;
    cell.elevation_m = elevation_m;
}

void apply_sediment_interface_material_change(
    Cell& cell,
    double vertical_displacement_m,
    double bedrock_erosion_depth_m,
    double alluvium_entrainment_depth_m,
    double deposition_depth_m,
    const char* context
) {
    validate_sediment_interface(cell, context);
    if (
        !std::isfinite(vertical_displacement_m) ||
        !std::isfinite(bedrock_erosion_depth_m) ||
        bedrock_erosion_depth_m < 0.0 ||
        !std::isfinite(alluvium_entrainment_depth_m) ||
        alluvium_entrainment_depth_m < 0.0 ||
        !std::isfinite(deposition_depth_m) || deposition_depth_m < 0.0
    ) {
        throw std::runtime_error(
            std::string(context) +
            " sediment-interface material change is invalid"
        );
    }

    const long double opening_mobile_depth_m =
        cell.sediment_thickness_m;
    const long double alluvium_depth_m =
        alluvium_entrainment_depth_m;
    const long double availability_bound = forward_error_bound(
        std::abs(opening_mobile_depth_m) + std::abs(alluvium_depth_m),
        2,
        1.0e-12L
    );
    if (alluvium_depth_m > opening_mobile_depth_m + availability_bound) {
        throw std::runtime_error(
            std::string(context) +
            " sediment-interface entrainment exceeds mobile inventory"
        );
    }

    long double closing_mobile_depth_m =
        opening_mobile_depth_m - alluvium_depth_m +
        static_cast<long double>(deposition_depth_m);
    if (closing_mobile_depth_m < -availability_bound) {
        throw std::runtime_error(
            std::string(context) +
            " sediment-interface closing mobile inventory is negative"
        );
    }
    closing_mobile_depth_m = std::max(0.0L, closing_mobile_depth_m);
    const long double closing_bedrock_surface_m =
        static_cast<long double>(cell.bedrock_surface_elevation_m) +
        static_cast<long double>(vertical_displacement_m) -
        static_cast<long double>(bedrock_erosion_depth_m);
    const double bedrock_surface_elevation_m = checked_interface_value(
        closing_bedrock_surface_m,
        "sediment-interface bedrock surface update overflowed"
    );
    const double sediment_thickness_m = checked_interface_value(
        closing_mobile_depth_m,
        "sediment-interface mobile inventory update overflowed"
    );
    const double elevation_m = checked_interface_value(
        static_cast<long double>(bedrock_surface_elevation_m) +
            static_cast<long double>(sediment_thickness_m),
        "sediment-interface closing surface overflowed"
    );
    validate_interface_values(
        bedrock_surface_elevation_m,
        sediment_thickness_m,
        elevation_m,
        context
    );
    cell.bedrock_surface_elevation_m = bedrock_surface_elevation_m;
    cell.sediment_thickness_m = sediment_thickness_m;
    cell.elevation_m = elevation_m;
}

double maximum_sediment_interface_closure_residual_m(
    const std::vector<Cell>& cells,
    const char* context
) {
    require_context(context);
    if (cells.empty()) {
        throw std::runtime_error(
            std::string(context) + " sediment-interface cell set is empty"
        );
    }
    long double maximum_residual_m = 0.0L;
    for (const Cell& cell : cells) {
        validate_sediment_interface(cell, context);
        maximum_residual_m = std::max(
            maximum_residual_m,
            std::abs(
                static_cast<long double>(cell.elevation_m) -
                static_cast<long double>(
                    cell.bedrock_surface_elevation_m
                ) -
                static_cast<long double>(cell.sediment_thickness_m)
            )
        );
    }
    return checked_interface_value(
        maximum_residual_m,
        "sediment-interface closure residual overflowed"
    );
}

void validate_sediment_source_partition(
    const std::vector<Cell>& cells,
    const std::vector<double>& source_depth_m_by_cell,
    const std::vector<double>& alluvium_entrainment_depth_m_by_cell,
    const std::vector<double>& bedrock_erosion_depth_m_by_cell,
    double alluvium_entrainment_volume_km3,
    double bedrock_erosion_volume_km3,
    const char* context
) {
    const std::size_t cell_count = cells.size();
    if (
        context == nullptr || *context == '\0' || cell_count == 0 ||
        source_depth_m_by_cell.size() != cell_count ||
        alluvium_entrainment_depth_m_by_cell.size() != cell_count ||
        bedrock_erosion_depth_m_by_cell.size() != cell_count
    ) {
        throw std::runtime_error(
            "sediment source-partition audit linkage is malformed"
        );
    }
    if (
        !std::isfinite(alluvium_entrainment_volume_km3) ||
        alluvium_entrainment_volume_km3 < 0.0 ||
        !std::isfinite(bedrock_erosion_volume_km3) ||
        bedrock_erosion_volume_km3 < 0.0
    ) {
        throw std::runtime_error(
            std::string(context) +
            " sediment source-partition aggregate is invalid"
        );
    }

    long double reconstructed_alluvium_volume_km3 = 0.0L;
    long double reconstructed_bedrock_volume_km3 = 0.0L;
    for (std::size_t cell_id = 0; cell_id < cell_count; ++cell_id) {
        const Cell& cell = cells[cell_id];
        const double source_depth_m = source_depth_m_by_cell[cell_id];
        const double alluvium_depth_m =
            alluvium_entrainment_depth_m_by_cell[cell_id];
        const double bedrock_depth_m =
            bedrock_erosion_depth_m_by_cell[cell_id];
        if (
            cell.id != static_cast<int>(cell_id) ||
            !std::isfinite(cell.area_km2) || cell.area_km2 <= 0.0
        ) {
            throw std::runtime_error(
                std::string(context) +
                " sediment source-partition cell linkage is invalid"
            );
        }
        if (
            !std::isfinite(source_depth_m) || source_depth_m < 0.0 ||
            !std::isfinite(alluvium_depth_m) || alluvium_depth_m < 0.0 ||
            !std::isfinite(bedrock_depth_m) || bedrock_depth_m < 0.0
        ) {
            throw std::runtime_error(
                std::string(context) +
                " sediment source-partition depth is invalid"
            );
        }

        const long double partition_depth_m =
            static_cast<long double>(alluvium_depth_m) +
            static_cast<long double>(bedrock_depth_m);
        const long double depth_term_sum =
            std::abs(static_cast<long double>(source_depth_m)) +
            std::abs(static_cast<long double>(alluvium_depth_m)) +
            std::abs(static_cast<long double>(bedrock_depth_m));
        if (
            std::abs(
                partition_depth_m -
                static_cast<long double>(source_depth_m)
            ) > forward_error_bound(depth_term_sum, 3, 1.0e-12L)
        ) {
            throw std::runtime_error(
                std::string(context) +
                " sediment source depth is not partitioned exactly"
            );
        }

        const long double volume_factor =
            static_cast<long double>(cell.area_km2) / 1000.0L;
        reconstructed_alluvium_volume_km3 +=
            static_cast<long double>(alluvium_depth_m) * volume_factor;
        reconstructed_bedrock_volume_km3 +=
            static_cast<long double>(bedrock_depth_m) * volume_factor;
    }

    const long double alluvium_term_sum =
        std::abs(reconstructed_alluvium_volume_km3) +
        std::abs(static_cast<long double>(
            alluvium_entrainment_volume_km3
        ));
    const long double bedrock_term_sum =
        std::abs(reconstructed_bedrock_volume_km3) +
        std::abs(static_cast<long double>(bedrock_erosion_volume_km3));
    const std::size_t volume_operation_count = cell_count * 2 + 4;
    if (
        std::abs(
            reconstructed_alluvium_volume_km3 -
            static_cast<long double>(alluvium_entrainment_volume_km3)
        ) > forward_error_bound(
            alluvium_term_sum, volume_operation_count, 1.0e-12L
        ) ||
        std::abs(
            reconstructed_bedrock_volume_km3 -
            static_cast<long double>(bedrock_erosion_volume_km3)
        ) > forward_error_bound(
            bedrock_term_sum, volume_operation_count, 1.0e-12L
        )
    ) {
        throw std::runtime_error(
            std::string(context) +
            " sediment source-partition volumes do not reconstruct"
        );
    }
}

}  // namespace magic_geo::detail
