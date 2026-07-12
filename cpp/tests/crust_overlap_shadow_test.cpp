#include "crust_overlap_shadow.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using magic_geo::detail::Cell;
using magic_geo::detail::CrustOverlapContinuousShadowResult;
using magic_geo::detail::CrustTransportPlan;
using magic_geo::detail::replay_crust_overlap_continuous_reduction_cpu;
using magic_geo::detail::validate_crust_overlap_continuous_shadow_input;
using magic_geo::detail::validate_crust_overlap_continuous_shadow_result;

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error(message);
}

void check(bool condition, const std::string& message) {
    if (!condition) {
        fail(message);
    }
}

template <typename Callable>
void check_throws(Callable&& callable, const std::string& message) {
    bool threw = false;
    try {
        callable();
    } catch (const std::exception&) {
        threw = true;
    }
    check(threw, message);
}

struct Fixture {
    std::vector<Cell> cells;
    CrustTransportPlan transport;
    std::vector<double> thickness;
    std::vector<double> density;
    std::vector<double> age;
};

Fixture make_fixture() {
    constexpr std::size_t CELL_COUNT = 32;
    Fixture fixture;
    fixture.cells.resize(CELL_COUNT);
    fixture.thickness.resize(CELL_COUNT);
    fixture.density.resize(CELL_COUNT);
    fixture.age.resize(CELL_COUNT);
    for (std::size_t index = 0; index < CELL_COUNT; ++index) {
        fixture.cells[index].id = static_cast<int>(index);
        fixture.cells[index].area_km2 = 10.0 +
            static_cast<double>(index % 3U) * 0.5;
        fixture.thickness[index] = 1.0 +
            static_cast<double>(index % 7U) * 0.25;
        fixture.density[index] = 2.5 +
            static_cast<double>(index % 5U) * 0.125;
        fixture.age[index] = static_cast<double>(index) * 3.5;
    }

    fixture.transport.destination_offsets.assign(CELL_COUNT + 1U, 0);
    auto append = [&](std::size_t destination, int source, double area) {
        fixture.transport.source_cell_ids.push_back(source);
        fixture.transport.overlap_area_km2.push_back(area);
        fixture.transport.destination_offsets[destination + 1U] =
            static_cast<int>(fixture.transport.source_cell_ids.size());
    };
    append(0, 0, fixture.cells[0].area_km2);  // identity row
    append(1, 0, 2.0);                        // raw gap row
    append(1, 1, 3.0);
    fixture.transport.destination_offsets[3] =
        fixture.transport.destination_offsets[2];  // empty/full-gap row
    for (int source = 0; source < 24; ++source) {
        append(3, source, 0.5);                // 24-way raw overlap row
    }
    for (std::size_t destination = 4;
         destination < CELL_COUNT;
         ++destination) {
        append(
            destination,
            static_cast<int>(destination),
            fixture.cells[destination].area_km2
        );
    }
    for (std::size_t destination = 1;
         destination < fixture.transport.destination_offsets.size();
         ++destination) {
        if (fixture.transport.destination_offsets[destination] == 0) {
            fixture.transport.destination_offsets[destination] =
                fixture.transport.destination_offsets[destination - 1U];
        }
    }

    const CrustOverlapContinuousShadowResult replay =
        replay_crust_overlap_continuous_reduction_cpu(
            fixture.transport,
            fixture.cells,
            fixture.thickness,
            fixture.density,
            fixture.age
        );
    fixture.transport.remapped_crust_thickness_km_by_cell =
        replay.remapped_crust_thickness_km_by_destination;
    fixture.transport.remapped_crust_density_by_cell =
        replay.remapped_crust_density_by_destination;
    fixture.transport.remapped_crust_age_ma_by_cell =
        replay.remapped_crust_age_ma_by_destination;
    for (std::size_t destination = 0;
         destination < CELL_COUNT;
         ++destination) {
        fixture.transport.transported_crust_volume_km3 +=
            replay.crust_volume_km3_by_destination[destination];
        fixture.transport.transported_density_weighted_crust_volume +=
            replay.density_weighted_crust_volume_by_destination[destination];
        fixture.transport.transported_crust_age_volume_moment +=
            replay.crust_age_volume_moment_by_destination[destination];
    }
    return fixture;
}

}  // namespace

int main() {
    try {
        Fixture fixture = make_fixture();
        const CrustOverlapContinuousShadowResult exact =
            replay_crust_overlap_continuous_reduction_cpu(
                fixture.transport,
                fixture.cells,
                fixture.thickness,
                fixture.density,
                fixture.age
            );
        const auto exact_validation =
            validate_crust_overlap_continuous_shadow_result(
                fixture.transport,
                fixture.cells,
                fixture.thickness,
                fixture.density,
                fixture.age,
                exact
            );
        check(exact_validation.passed, exact_validation.failure);
        check(exact_validation.maximum_error_to_bound_ratio == 0.0,
              "exact CPU shadow replay reported a nonzero normalized error");
        check(exact.crust_volume_km3_by_destination[2] == 0.0,
              "empty destination did not retain zero incoming volume");
        check(exact.remapped_crust_thickness_km_by_destination[2] == 0.0,
              "empty destination did not retain zero thickness");
        check(exact.remapped_crust_density_by_destination[2] == fixture.density[2],
              "empty destination did not retain its source-snapshot density");
        check(exact.remapped_crust_age_ma_by_destination[2] == 0.0,
              "empty destination did not retain zero age");
        check(exact.remapped_crust_thickness_km_by_destination[1] <
                  fixture.thickness[1],
              "raw gap row appears to have been destination-normalized");
        check(exact.remapped_crust_thickness_km_by_destination[3] > 0.0,
              "24-way overlap row produced no transported thickness");

        Fixture maximum_finite;
        maximum_finite.cells.resize(1);
        maximum_finite.cells[0].area_km2 =
            std::numeric_limits<double>::max();
        maximum_finite.thickness = {1.0};
        maximum_finite.density = {1.0};
        maximum_finite.age = {0.0};
        maximum_finite.transport.destination_offsets = {0, 1};
        maximum_finite.transport.source_cell_ids = {0};
        maximum_finite.transport.overlap_area_km2 = {
            std::numeric_limits<double>::max()
        };
        const CrustOverlapContinuousShadowResult maximum_finite_exact =
            replay_crust_overlap_continuous_reduction_cpu(
                maximum_finite.transport,
                maximum_finite.cells,
                maximum_finite.thickness,
                maximum_finite.density,
                maximum_finite.age
            );
        maximum_finite.transport.remapped_crust_thickness_km_by_cell =
            maximum_finite_exact.remapped_crust_thickness_km_by_destination;
        maximum_finite.transport.remapped_crust_density_by_cell =
            maximum_finite_exact.remapped_crust_density_by_destination;
        maximum_finite.transport.remapped_crust_age_ma_by_cell =
            maximum_finite_exact.remapped_crust_age_ma_by_destination;
        maximum_finite.transport.transported_crust_volume_km3 =
            maximum_finite_exact.crust_volume_km3_by_destination[0];
        maximum_finite.transport.transported_density_weighted_crust_volume =
            maximum_finite_exact.
                density_weighted_crust_volume_by_destination[0];
        maximum_finite.transport.transported_crust_age_volume_moment =
            maximum_finite_exact.crust_age_volume_moment_by_destination[0];
        const auto maximum_finite_validation =
            validate_crust_overlap_continuous_shadow_result(
                maximum_finite.transport,
                maximum_finite.cells,
                maximum_finite.thickness,
                maximum_finite.density,
                maximum_finite.age,
                maximum_finite_exact
            );
        check(maximum_finite_validation.passed,
              "exact finite DBL_MAX shadow replay did not validate");

        CrustOverlapContinuousShadowResult corrupted = exact;
        corrupted.crust_volume_km3_by_destination[3] += 1.0;
        const auto corrupted_validation =
            validate_crust_overlap_continuous_shadow_result(
                fixture.transport,
                fixture.cells,
                fixture.thickness,
                fixture.density,
                fixture.age,
                corrupted
            );
        check(!corrupted_validation.passed,
              "injected accelerator shadow mismatch was accepted");
        check(corrupted_validation.maximum_error_to_bound_ratio > 1.0,
              "injected mismatch did not exceed its operation-derived bound");

        corrupted = exact;
        corrupted.remapped_crust_age_ma_by_destination.pop_back();
        check_throws(
            [&] {
                (void)validate_crust_overlap_continuous_shadow_result(
                    fixture.transport,
                    fixture.cells,
                    fixture.thickness,
                    fixture.density,
                    fixture.age,
                    corrupted
                );
            },
            "device-result cardinality mismatch was accepted"
        );

        corrupted = exact;
        corrupted.density_weighted_crust_volume_by_destination[0] =
            std::numeric_limits<double>::infinity();
        check_throws(
            [&] {
                (void)validate_crust_overlap_continuous_shadow_result(
                    fixture.transport,
                    fixture.cells,
                    fixture.thickness,
                    fixture.density,
                    fixture.age,
                    corrupted
                );
            },
            "non-finite device-result value was accepted"
        );

        Fixture invalid = fixture;
        invalid.transport.destination_offsets[2] =
            invalid.transport.destination_offsets[3] + 1;
        check_throws(
            [&] {
                validate_crust_overlap_continuous_shadow_input(
                    invalid.transport,
                    invalid.cells,
                    invalid.thickness,
                    invalid.density,
                    invalid.age
                );
            },
            "descending/out-of-range CSR offsets were accepted"
        );

        invalid = fixture;
        invalid.transport.source_cell_ids[1] =
            invalid.transport.source_cell_ids[2];
        check_throws(
            [&] {
                validate_crust_overlap_continuous_shadow_input(
                    invalid.transport,
                    invalid.cells,
                    invalid.thickness,
                    invalid.density,
                    invalid.age
                );
            },
            "duplicate or noncanonical row sources were accepted"
        );

        invalid = fixture;
        invalid.transport.overlap_area_km2[0] =
            std::numeric_limits<double>::quiet_NaN();
        check_throws(
            [&] {
                validate_crust_overlap_continuous_shadow_input(
                    invalid.transport,
                    invalid.cells,
                    invalid.thickness,
                    invalid.density,
                    invalid.age
                );
            },
            "non-finite overlap area was accepted"
        );

        invalid = fixture;
        invalid.density.pop_back();
        check_throws(
            [&] {
                validate_crust_overlap_continuous_shadow_input(
                    invalid.transport,
                    invalid.cells,
                    invalid.thickness,
                    invalid.density,
                    invalid.age
                );
            },
            "source-state cardinality mismatch was accepted"
        );

        invalid = fixture;
        invalid.cells[0].area_km2 = std::numeric_limits<double>::infinity();
        check_throws(
            [&] {
                validate_crust_overlap_continuous_shadow_input(
                    invalid.transport,
                    invalid.cells,
                    invalid.thickness,
                    invalid.density,
                    invalid.age
                );
            },
            "non-finite destination area was accepted"
        );

        invalid = Fixture{};
        invalid.transport.destination_offsets = {0};
        check_throws(
            [&] {
                validate_crust_overlap_continuous_shadow_input(
                    invalid.transport,
                    invalid.cells,
                    invalid.thickness,
                    invalid.density,
                    invalid.age
                );
            },
            "empty shadow mesh was accepted as a validated transition"
        );

        std::cout << "crust overlap continuous shadow validation passed\n";
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "crust overlap continuous shadow validation failed: "
                  << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
