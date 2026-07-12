#include "crust_overlap_shadow.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <string>

namespace magic_geo::detail {
namespace {

constexpr std::size_t SHADOW_OUTPUT_COMPONENT_COUNT = 6;

void require_finite_result_array(
    const std::vector<double>& values,
    std::size_t expected_size,
    const char* name
) {
    if (values.size() != expected_size) {
        throw std::runtime_error(
            std::string("crust overlap continuous shadow ") + name +
            " cardinality is invalid"
        );
    }
    if (std::any_of(values.begin(), values.end(), [](double value) {
            return !std::isfinite(value);
        })) {
        throw std::runtime_error(
            std::string("crust overlap continuous shadow ") + name +
            " contains a non-finite value"
        );
    }
}

double binary64_ulp(double value) {
    const double magnitude = std::abs(value);
    if (!std::isfinite(magnitude)) {
        throw std::runtime_error(
            "crust overlap continuous shadow ULP operand is non-finite"
        );
    }
    const double next = std::nextafter(
        magnitude, std::numeric_limits<double>::infinity()
    );
    const double ulp = std::isfinite(next)
        ? next - magnitude
        : magnitude - std::nextafter(magnitude, 0.0);
    if (!std::isfinite(ulp) || ulp <= 0.0) {
        throw std::runtime_error(
            "crust overlap continuous shadow ULP envelope is invalid"
        );
    }
    return ulp;
}

double two_execution_forward_error_bound(
    std::size_t operation_count,
    long double operand_magnitude,
    double expected,
    double actual
) {
    if (
        !std::isfinite(operand_magnitude) || operand_magnitude < 0.0L ||
        !std::isfinite(expected) || !std::isfinite(actual)
    ) {
        throw std::runtime_error(
            "crust overlap continuous shadow error-bound operand is invalid"
        );
    }
    const long double epsilon = static_cast<long double>(
        std::numeric_limits<double>::epsilon()
    );
    const long double scaled_operations =
        static_cast<long double>(operation_count) * epsilon;
    if (!std::isfinite(scaled_operations) || scaled_operations >= 0.5L) {
        throw std::runtime_error(
            "crust overlap continuous shadow operation-count gamma is invalid"
        );
    }
    const long double gamma = scaled_operations / (1.0L - scaled_operations);
    const long double ulp_envelope = 8.0L * static_cast<long double>(
        binary64_ulp(std::max(std::abs(expected), std::abs(actual)))
    );
    const long double bound =
        2.0L * gamma * operand_magnitude + ulp_envelope;
    if (
        !std::isfinite(bound) || bound <= 0.0L ||
        bound > static_cast<long double>(std::numeric_limits<double>::max())
    ) {
        throw std::runtime_error(
            "crust overlap continuous shadow forward-error bound is invalid"
        );
    }
    const double result = static_cast<double>(bound);
    if (!std::isfinite(result) || result <= 0.0) {
        throw std::runtime_error(
            "crust overlap continuous shadow binary64 error bound is invalid"
        );
    }
    return result;
}

void record_comparison(
    double expected,
    double actual,
    std::size_t operation_count,
    long double operand_magnitude,
    double& maximum_error,
    double& maximum_bound,
    CrustOverlapContinuousShadowValidation& validation,
    const std::string& label
) {
    const double error = std::abs(actual - expected);
    const double bound = two_execution_forward_error_bound(
        operation_count, operand_magnitude, expected, actual
    );
    maximum_error = std::max(maximum_error, error);
    maximum_bound = std::max(maximum_bound, bound);
    const double raw_ratio = error / bound;
    const double finite_ratio = std::isfinite(raw_ratio)
        ? raw_ratio
        : std::numeric_limits<double>::max();
    validation.maximum_error_to_bound_ratio = std::max(
        validation.maximum_error_to_bound_ratio, finite_ratio
    );
    if (error > bound && validation.failure.empty()) {
        validation.failure = label + " exceeded its binary64 gamma-plus-ULP bound";
    }
}

std::size_t checked_operation_count(
    std::size_t item_count,
    std::size_t operations_per_item,
    std::size_t fixed_operations
) {
    if (
        operations_per_item != 0 &&
        item_count >
            (std::numeric_limits<std::size_t>::max() - fixed_operations) /
                operations_per_item
    ) {
        throw std::runtime_error(
            "crust overlap continuous shadow operation count overflow"
        );
    }
    return item_count * operations_per_item + fixed_operations;
}

}  // namespace

void validate_crust_overlap_continuous_shadow_input(
    const CrustTransportPlan& transport,
    const std::vector<Cell>& cells,
    const std::vector<double>& source_crust_thickness_km,
    const std::vector<double>& source_crust_density,
    const std::vector<double>& source_crust_age_ma
) {
    const std::size_t cell_count = cells.size();
    const std::size_t edge_count = transport.source_cell_ids.size();
    if (cell_count == 0) {
        throw std::runtime_error(
            "crust overlap continuous shadow requires a nonempty mesh"
        );
    }
    if (
        cell_count > static_cast<std::size_t>(std::numeric_limits<int>::max()) ||
        edge_count > static_cast<std::size_t>(std::numeric_limits<int>::max())
    ) {
        throw std::runtime_error(
            "crust overlap continuous shadow exceeds 32-bit kernel indices"
        );
    }
    if (
        cell_count >
            std::numeric_limits<std::size_t>::max() /
                SHADOW_OUTPUT_COMPONENT_COUNT
    ) {
        throw std::runtime_error(
            "crust overlap continuous shadow packed output cardinality overflow"
        );
    }
    if (
        transport.destination_offsets.size() != cell_count + 1 ||
        source_crust_thickness_km.size() != cell_count ||
        source_crust_density.size() != cell_count ||
        source_crust_age_ma.size() != cell_count ||
        transport.overlap_area_km2.size() != edge_count ||
        transport.destination_offsets.empty() ||
        transport.destination_offsets.front() != 0 ||
        transport.destination_offsets.back() != static_cast<int>(edge_count)
    ) {
        throw std::runtime_error(
            "crust overlap continuous shadow input cardinality or CSR root is invalid"
        );
    }

    for (std::size_t source = 0; source < cell_count; ++source) {
        if (
            !std::isfinite(cells[source].area_km2) ||
            cells[source].area_km2 <= 0.0 ||
            !std::isfinite(source_crust_thickness_km[source]) ||
            source_crust_thickness_km[source] < 0.0 ||
            !std::isfinite(source_crust_density[source]) ||
            source_crust_density[source] <= 0.0 ||
            !std::isfinite(source_crust_age_ma[source]) ||
            source_crust_age_ma[source] < 0.0
        ) {
            throw std::runtime_error(
                "crust overlap continuous shadow cell area or source state is invalid"
            );
        }
    }

    for (std::size_t destination = 0; destination < cell_count; ++destination) {
        const int begin = transport.destination_offsets[destination];
        const int end = transport.destination_offsets[destination + 1];
        if (
            begin < 0 || end < begin ||
            end > static_cast<int>(edge_count)
        ) {
            throw std::runtime_error(
                "crust overlap continuous shadow destination offsets are invalid"
            );
        }
        int previous_source = -1;
        for (int edge_id = begin; edge_id < end; ++edge_id) {
            const std::size_t edge = static_cast<std::size_t>(edge_id);
            const int source = transport.source_cell_ids[edge];
            const double area = transport.overlap_area_km2[edge];
            if (
                source <= previous_source ||
                source < 0 || source >= static_cast<int>(cell_count) ||
                !std::isfinite(area) || area <= 0.0
            ) {
                throw std::runtime_error(
                    "crust overlap continuous shadow edge order, source, or area is invalid"
                );
            }
            previous_source = source;
        }
    }
}

CrustOverlapContinuousShadowResult replay_crust_overlap_continuous_reduction_cpu(
    const CrustTransportPlan& transport,
    const std::vector<Cell>& cells,
    const std::vector<double>& source_crust_thickness_km,
    const std::vector<double>& source_crust_density,
    const std::vector<double>& source_crust_age_ma
) {
    validate_crust_overlap_continuous_shadow_input(
        transport,
        cells,
        source_crust_thickness_km,
        source_crust_density,
        source_crust_age_ma
    );
    const std::size_t cell_count = cells.size();
    CrustOverlapContinuousShadowResult result;
    result.crust_volume_km3_by_destination.assign(cell_count, 0.0);
    result.density_weighted_crust_volume_by_destination.assign(cell_count, 0.0);
    result.crust_age_volume_moment_by_destination.assign(cell_count, 0.0);
    result.remapped_crust_thickness_km_by_destination.assign(cell_count, 0.0);
    result.remapped_crust_density_by_destination.assign(cell_count, 0.0);
    result.remapped_crust_age_ma_by_destination.assign(cell_count, 0.0);

    for (std::size_t destination = 0; destination < cell_count; ++destination) {
        const int begin = transport.destination_offsets[destination];
        const int end = transport.destination_offsets[destination + 1];
        double volume = 0.0;
        double density_volume = 0.0;
        double age_moment = 0.0;
        for (int edge_id = begin; edge_id < end; ++edge_id) {
            const std::size_t edge = static_cast<std::size_t>(edge_id);
            const std::size_t source = static_cast<std::size_t>(
                transport.source_cell_ids[edge]
            );
            const double edge_volume =
                transport.overlap_area_km2[edge] *
                source_crust_thickness_km[source];
            volume = volume + edge_volume;
            density_volume = density_volume +
                edge_volume * source_crust_density[source];
            age_moment = age_moment +
                edge_volume * source_crust_age_ma[source];
        }
        result.crust_volume_km3_by_destination[destination] = volume;
        result.density_weighted_crust_volume_by_destination[destination] =
            density_volume;
        result.crust_age_volume_moment_by_destination[destination] = age_moment;
        if (volume > 0.0) {
            result.remapped_crust_thickness_km_by_destination[destination] =
                volume / cells[destination].area_km2;
            result.remapped_crust_density_by_destination[destination] =
                density_volume / volume;
            result.remapped_crust_age_ma_by_destination[destination] =
                age_moment / volume;
        } else {
            result.remapped_crust_density_by_destination[destination] =
                source_crust_density[destination];
        }
    }
    return result;
}

CrustOverlapContinuousShadowValidation
validate_crust_overlap_continuous_shadow_result(
    const CrustTransportPlan& transport,
    const std::vector<Cell>& cells,
    const std::vector<double>& source_crust_thickness_km,
    const std::vector<double>& source_crust_density,
    const std::vector<double>& source_crust_age_ma,
    const CrustOverlapContinuousShadowResult& actual
) {
    validate_crust_overlap_continuous_shadow_input(
        transport,
        cells,
        source_crust_thickness_km,
        source_crust_density,
        source_crust_age_ma
    );
    const std::size_t cell_count = cells.size();
    require_finite_result_array(
        actual.crust_volume_km3_by_destination, cell_count, "volume output"
    );
    require_finite_result_array(
        actual.density_weighted_crust_volume_by_destination,
        cell_count,
        "density-weighted-volume output"
    );
    require_finite_result_array(
        actual.crust_age_volume_moment_by_destination,
        cell_count,
        "age-volume-moment output"
    );
    require_finite_result_array(
        actual.remapped_crust_thickness_km_by_destination,
        cell_count,
        "thickness output"
    );
    require_finite_result_array(
        actual.remapped_crust_density_by_destination,
        cell_count,
        "density output"
    );
    require_finite_result_array(
        actual.remapped_crust_age_ma_by_destination,
        cell_count,
        "age output"
    );
    const auto has_negative = [](const std::vector<double>& values) {
        return std::any_of(values.begin(), values.end(), [](double value) {
            return value < 0.0;
        });
    };
    if (
        has_negative(actual.crust_volume_km3_by_destination) ||
        has_negative(actual.density_weighted_crust_volume_by_destination) ||
        has_negative(actual.crust_age_volume_moment_by_destination) ||
        has_negative(actual.remapped_crust_thickness_km_by_destination) ||
        has_negative(actual.remapped_crust_age_ma_by_destination) ||
        std::any_of(
            actual.remapped_crust_density_by_destination.begin(),
            actual.remapped_crust_density_by_destination.end(),
            [](double value) { return value <= 0.0; }
        )
    ) {
        throw std::runtime_error(
            "crust overlap continuous shadow device result has an invalid sign"
        );
    }
    if (
        transport.remapped_crust_thickness_km_by_cell.size() != cell_count ||
        transport.remapped_crust_density_by_cell.size() != cell_count ||
        transport.remapped_crust_age_ma_by_cell.size() != cell_count ||
        !std::isfinite(transport.transported_crust_volume_km3) ||
        !std::isfinite(transport.transported_density_weighted_crust_volume) ||
        !std::isfinite(transport.transported_crust_age_volume_moment)
    ) {
        throw std::runtime_error(
            "crust overlap continuous shadow CPU authority operands are invalid"
        );
    }

    const CrustOverlapContinuousShadowResult expected =
        replay_crust_overlap_continuous_reduction_cpu(
            transport,
            cells,
            source_crust_thickness_km,
            source_crust_density,
            source_crust_age_ma
        );
    CrustOverlapContinuousShadowValidation validation;
    double actual_global_volume = 0.0;
    double actual_global_density_volume = 0.0;
    double actual_global_age_moment = 0.0;
    long double global_volume_magnitude = 0.0L;
    long double global_density_volume_magnitude = 0.0L;
    long double global_age_moment_magnitude = 0.0L;

    for (std::size_t destination = 0; destination < cell_count; ++destination) {
        const int begin = transport.destination_offsets[destination];
        const int end = transport.destination_offsets[destination + 1];
        const std::size_t contributor_count = static_cast<std::size_t>(end - begin);
        long double volume_magnitude = 0.0L;
        long double density_volume_magnitude = 0.0L;
        long double age_moment_magnitude = 0.0L;
        for (int edge_id = begin; edge_id < end; ++edge_id) {
            const std::size_t edge = static_cast<std::size_t>(edge_id);
            const std::size_t source = static_cast<std::size_t>(
                transport.source_cell_ids[edge]
            );
            const long double edge_volume =
                static_cast<long double>(transport.overlap_area_km2[edge]) *
                static_cast<long double>(source_crust_thickness_km[source]);
            volume_magnitude += std::abs(edge_volume);
            density_volume_magnitude += std::abs(
                edge_volume * static_cast<long double>(
                    source_crust_density[source]
                )
            );
            age_moment_magnitude += std::abs(
                edge_volume * static_cast<long double>(
                    source_crust_age_ma[source]
                )
            );
        }
        global_volume_magnitude += volume_magnitude;
        global_density_volume_magnitude += density_volume_magnitude;
        global_age_moment_magnitude += age_moment_magnitude;

        const std::size_t volume_operations = checked_operation_count(
            contributor_count, 2, 0
        );
        const std::size_t moment_operations = checked_operation_count(
            contributor_count, 3, 0
        );
        const std::size_t quotient_operations = checked_operation_count(
            contributor_count, 5, 2
        );
        record_comparison(
            expected.crust_volume_km3_by_destination[destination],
            actual.crust_volume_km3_by_destination[destination],
            volume_operations,
            volume_magnitude,
            validation.maximum_crust_volume_error_km3,
            validation.maximum_crust_volume_error_bound_km3,
            validation,
            "crust volume at destination " + std::to_string(destination)
        );
        record_comparison(
            expected.density_weighted_crust_volume_by_destination[destination],
            actual.density_weighted_crust_volume_by_destination[destination],
            moment_operations,
            density_volume_magnitude,
            validation.maximum_density_weighted_volume_error,
            validation.maximum_density_weighted_volume_error_bound,
            validation,
            "density-weighted volume at destination " +
                std::to_string(destination)
        );
        record_comparison(
            expected.crust_age_volume_moment_by_destination[destination],
            actual.crust_age_volume_moment_by_destination[destination],
            moment_operations,
            age_moment_magnitude,
            validation.maximum_crust_age_volume_moment_error,
            validation.maximum_crust_age_volume_moment_error_bound,
            validation,
            "age-volume moment at destination " +
                std::to_string(destination)
        );

        const double expected_thickness =
            transport.remapped_crust_thickness_km_by_cell[destination];
        const double expected_density =
            transport.remapped_crust_density_by_cell[destination];
        const double expected_age =
            transport.remapped_crust_age_ma_by_cell[destination];
        if (
            !std::isfinite(expected_thickness) || expected_thickness < 0.0 ||
            !std::isfinite(expected_density) || expected_density <= 0.0 ||
            !std::isfinite(expected_age) || expected_age < 0.0
        ) {
            throw std::runtime_error(
                "crust overlap continuous shadow CPU remapped state is invalid"
            );
        }
        record_comparison(
            expected_thickness,
            actual.remapped_crust_thickness_km_by_destination[destination],
            quotient_operations,
            std::max(
                std::abs(static_cast<long double>(expected_thickness)),
                std::abs(static_cast<long double>(
                    actual.remapped_crust_thickness_km_by_destination[destination]
                ))
            ),
            validation.maximum_remapped_thickness_error_km,
            validation.maximum_remapped_thickness_error_bound_km,
            validation,
            "remapped thickness at destination " +
                std::to_string(destination)
        );
        record_comparison(
            expected_density,
            actual.remapped_crust_density_by_destination[destination],
            quotient_operations,
            std::max(
                std::abs(static_cast<long double>(expected_density)),
                std::abs(static_cast<long double>(
                    actual.remapped_crust_density_by_destination[destination]
                ))
            ),
            validation.maximum_remapped_density_error,
            validation.maximum_remapped_density_error_bound,
            validation,
            "remapped density at destination " +
                std::to_string(destination)
        );
        record_comparison(
            expected_age,
            actual.remapped_crust_age_ma_by_destination[destination],
            quotient_operations,
            std::max(
                std::abs(static_cast<long double>(expected_age)),
                std::abs(static_cast<long double>(
                    actual.remapped_crust_age_ma_by_destination[destination]
                ))
            ),
            validation.maximum_remapped_age_error_ma,
            validation.maximum_remapped_age_error_bound_ma,
            validation,
            "remapped age at destination " + std::to_string(destination)
        );

        actual_global_volume = actual_global_volume +
            actual.crust_volume_km3_by_destination[destination];
        actual_global_density_volume = actual_global_density_volume +
            actual.density_weighted_crust_volume_by_destination[destination];
        actual_global_age_moment = actual_global_age_moment +
            actual.crust_age_volume_moment_by_destination[destination];
    }

    const std::size_t edge_count = transport.source_cell_ids.size();
    record_comparison(
        transport.transported_crust_volume_km3,
        actual_global_volume,
        checked_operation_count(edge_count, 2, cell_count),
        global_volume_magnitude,
        validation.maximum_crust_volume_error_km3,
        validation.maximum_crust_volume_error_bound_km3,
        validation,
        "global transported crust volume"
    );
    record_comparison(
        transport.transported_density_weighted_crust_volume,
        actual_global_density_volume,
        checked_operation_count(edge_count, 3, cell_count),
        global_density_volume_magnitude,
        validation.maximum_density_weighted_volume_error,
        validation.maximum_density_weighted_volume_error_bound,
        validation,
        "global transported density-weighted crust volume"
    );
    record_comparison(
        transport.transported_crust_age_volume_moment,
        actual_global_age_moment,
        checked_operation_count(edge_count, 3, cell_count),
        global_age_moment_magnitude,
        validation.maximum_crust_age_volume_moment_error,
        validation.maximum_crust_age_volume_moment_error_bound,
        validation,
        "global transported crust-age volume moment"
    );
    validation.passed = validation.failure.empty();
    return validation;
}

}  // namespace magic_geo::detail
