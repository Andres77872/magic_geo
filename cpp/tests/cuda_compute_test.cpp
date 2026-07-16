#include "cuda_compute.hpp"

#include <cuda_runtime_api.h>

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using magic_geo::detail::Cell;
using magic_geo::detail::CudaComputeSession;
using magic_geo::detail::CrustTransportPlan;
using magic_geo::detail::Vec3;
using magic_geo::detail::replay_crust_overlap_continuous_reduction_cpu;
using magic_geo::detail::validate_crust_overlap_continuous_shadow_result;

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error(message);
}

void check(bool condition, const std::string& message) {
    if (!condition) {
        fail(message);
    }
}

std::vector<Cell> make_cells(std::size_t count) {
    const Vec3 positions[] = {
        {1.0, 0.0, 0.0},
        {0.0, 1.0, 0.0},
        {-1.0, 0.0, 0.0},
        {0.0, -1.0, 0.0},
        {0.5, 0.5, 0.5},
        {-0.5, 0.5, -0.5},
    };
    std::vector<Cell> cells(count);
    for (std::size_t index = 0; index < count; ++index) {
        cells[index].id = static_cast<int>(index);
        cells[index].p = positions[index % 6U];
        cells[index].plate_id = static_cast<int>(index % 4U);
        if (index == 0 || count == 1) {
            continue;
        }
        cells[index].neighbors.push_back(static_cast<int>((index + 7U) % count));
        cells[index].neighbors.push_back(static_cast<int>((index + count - 1U) % count));
        cells[index].neighbors.push_back(static_cast<int>((index + 1U) % count));
        if (index == count / 2U) {
            cells[index].neighbors.clear();
            const std::size_t dense_degree = std::min<std::size_t>(65U, count - 1U);
            for (std::size_t neighbor = 0; neighbor < dense_degree; ++neighbor) {
                if (neighbor != index) {
                    cells[index].neighbors.push_back(static_cast<int>(neighbor));
                }
            }
        }
    }
    return cells;
}

std::vector<double> make_field(std::size_t count, int multiplier, int bias) {
    std::vector<double> field(count);
    for (std::size_t index = 0; index < count; ++index) {
        const int numerator =
            (static_cast<int>(index % 101U) * multiplier + bias) % 127 - 63;
        field[index] = std::ldexp(static_cast<double>(numerator), -7);
    }
    return field;
}

std::vector<int> reference_assign(
    const std::vector<Vec3>& centers,
    const std::vector<Cell>& cells
) {
    std::vector<int> output(cells.size(), 0);
    for (std::size_t cell_id = 0; cell_id < cells.size(); ++cell_id) {
        double best = -2.0;
        int best_plate = 0;
        for (std::size_t plate_id = 0; plate_id < centers.size(); ++plate_id) {
            double score = cells[cell_id].p.x * centers[plate_id].x;
            score = score + cells[cell_id].p.y * centers[plate_id].y;
            score = score + cells[cell_id].p.z * centers[plate_id].z;
            if (score > best) {
                best = score;
                best_plate = static_cast<int>(plate_id);
            }
        }
        output[cell_id] = best_plate;
    }
    return output;
}

std::vector<double> reference_smooth(
    const std::vector<Cell>& cells,
    const std::vector<double>& input,
    int steps,
    double self_weight
) {
    std::vector<double> current = input;
    std::vector<double> next(input.size());
    for (int step = 0; step < steps; ++step) {
        for (std::size_t cell_id = 0; cell_id < cells.size(); ++cell_id) {
            double sum = 0.0;
            for (int neighbor_id : cells[cell_id].neighbors) {
                sum = sum + current[static_cast<std::size_t>(neighbor_id)];
            }
            const double value = current[cell_id];
            const double average = cells[cell_id].neighbors.empty()
                ? value
                : sum / static_cast<double>(cells[cell_id].neighbors.size());
            next[cell_id] =
                self_weight * value + (1.0 - self_weight) * average;
        }
        current.swap(next);
    }
    return current;
}

void check_bitwise_equal(
    const std::vector<double>& actual,
    const std::vector<double>& expected,
    const std::string& operation
) {
    check(actual.size() == expected.size(), operation + " output size differs");
    for (std::size_t index = 0; index < actual.size(); ++index) {
        if (std::bit_cast<std::uint64_t>(actual[index]) !=
            std::bit_cast<std::uint64_t>(expected[index])) {
            fail(operation + " raw FP64 mismatch at index " + std::to_string(index));
        }
    }
}

}  // namespace

int main() {
    try {
        int caller_device = -1;
        if (cudaGetDevice(&caller_device) != cudaSuccess) {
            (void)cudaGetLastError();
        }

        CudaComputeSession session;
        if (!session.available()) {
            std::cout << "CUDA kernel test skipped: " << session.telemetry().error << '\n';
            return 77;
        }
        if (caller_device >= 0) {
            int current_device = -1;
            check(cudaGetDevice(&current_device) == cudaSuccess,
                  "cudaGetDevice failed after session construction");
            check(current_device == caller_device,
                  "session construction changed the caller's current CUDA device");
        }

        std::vector<Cell> small_cells = make_cells(129);
        std::vector<Cell> cells = make_cells(513);
        const std::vector<Vec3> centers = {
            {1.0, 0.0, 0.0},
            {1.0, 0.0, 0.0},  // exact tie: strict comparison must retain index 0
            {0.0, 1.0, 0.0},
            {-1.0, 0.0, 0.0},
            {0.0, -1.0, 0.0},
        };
        std::vector<int> plate_ids;
        session.run_assign_plates(centers, cells, plate_ids);
        check(plate_ids == reference_assign(centers, cells),
              "plate assignment differs from ordered CPU reference");

        const std::vector<double> small_input = make_field(small_cells.size(), 17, 9);
        const std::vector<double> input_a = make_field(cells.size(), 17, 9);
        const std::vector<double> input_b = make_field(cells.size(), 29, 5);
        const std::vector<double> input_c = make_field(cells.size(), 43, 3);
        std::vector<double> output;
        session.run_smooth_field(small_cells, small_input, 3, 0.625, output);
        check_bitwise_equal(
            output,
            reference_smooth(small_cells, small_input, 3, 0.625),
            "growing scalar smoothing"
        );
        session.run_smooth_field(cells, input_a, 7, 0.625, output);
        check_bitwise_equal(
            output,
            reference_smooth(cells, input_a, 7, 0.625),
            "scalar smoothing"
        );
        session.run_smooth_field(cells, input_a, 0, 0.625, output);
        check_bitwise_equal(output, input_a, "zero-step scalar smoothing");

        std::vector<double> output_a;
        std::vector<double> output_b;
        std::vector<double> output_c;
        session.run_smooth_three_fields(
            cells,
            input_a,
            input_b,
            input_c,
            5,
            0.625,
            0.375,
            0.8125,
            output_a,
            output_b,
            output_c
        );
        check_bitwise_equal(
            output_a,
            reference_smooth(cells, input_a, 5, 0.625),
            "fused smoothing field A"
        );
        check_bitwise_equal(
            output_b,
            reference_smooth(cells, input_b, 5, 0.375),
            "fused smoothing field B"
        );
        check_bitwise_equal(
            output_c,
            reference_smooth(cells, input_c, 5, 0.8125),
            "fused smoothing field C"
        );

        // This is a shadow replay of the many-contributor conservative v3 CSR.
        // Device results are validated and discarded by the production
        // reconciliation path.
        std::vector<Cell> shadow_cells = make_cells(33);
        std::vector<double> shadow_thickness(shadow_cells.size());
        std::vector<double> shadow_density(shadow_cells.size());
        std::vector<double> shadow_age(shadow_cells.size());
        for (std::size_t index = 0; index < shadow_cells.size(); ++index) {
            shadow_cells[index].area_km2 = 10.0 +
                static_cast<double>(index % 3U) * 0.5;
            shadow_thickness[index] = 1.0 +
                static_cast<double>(index % 7U) * 0.25;
            shadow_density[index] = 2.5 +
                static_cast<double>(index % 5U) * 0.125;
            shadow_age[index] = static_cast<double>(index) * 3.5;
        }
        CrustTransportPlan shadow_plan;
        shadow_plan.destination_offsets.assign(shadow_cells.size() + 1U, 0);
        auto append_shadow_edge = [&](std::size_t destination, int source, double area) {
            shadow_plan.source_cell_ids.push_back(source);
            shadow_plan.overlap_area_km2.push_back(area);
            shadow_plan.destination_offsets[destination + 1U] =
                static_cast<int>(shadow_plan.source_cell_ids.size());
        };
        append_shadow_edge(0, 0, shadow_cells[0].area_km2);
        append_shadow_edge(1, 0, 2.0);
        append_shadow_edge(1, 1, 3.0);
        shadow_plan.destination_offsets[3] = shadow_plan.destination_offsets[2];
        for (int source = 0; source < 24; ++source) {
            append_shadow_edge(3, source, 0.5);
        }
        for (std::size_t destination = 4;
             destination < shadow_cells.size();
             ++destination) {
            append_shadow_edge(
                destination,
                static_cast<int>(destination),
                shadow_cells[destination].area_km2
            );
        }
        const auto shadow_reference =
            replay_crust_overlap_continuous_reduction_cpu(
                shadow_plan,
                shadow_cells,
                shadow_thickness,
                shadow_density,
                shadow_age
            );
        shadow_plan.remapped_crust_thickness_km_by_cell =
            shadow_reference.remapped_crust_thickness_km_by_destination;
        shadow_plan.remapped_crust_density_by_cell =
            shadow_reference.remapped_crust_density_by_destination;
        shadow_plan.remapped_crust_age_ma_by_cell =
            shadow_reference.remapped_crust_age_ma_by_destination;
        for (std::size_t destination = 0;
             destination < shadow_cells.size();
             ++destination) {
            shadow_plan.transported_crust_volume_km3 +=
                shadow_reference.crust_volume_km3_by_destination[destination];
            shadow_plan.transported_density_weighted_crust_volume +=
                shadow_reference.
                    density_weighted_crust_volume_by_destination[destination];
            shadow_plan.transported_crust_age_volume_moment +=
                shadow_reference.
                    crust_age_volume_moment_by_destination[destination];
        }
        magic_geo::detail::CrustOverlapContinuousShadowResult shadow_output;
        session.run_crust_overlap_continuous_shadow(
            shadow_plan,
            shadow_cells,
            shadow_thickness,
            shadow_density,
            shadow_age,
            shadow_output
        );
        const auto shadow_validation =
            validate_crust_overlap_continuous_shadow_result(
                shadow_plan,
                shadow_cells,
                shadow_thickness,
                shadow_density,
                shadow_age,
                shadow_output
            );
        check(shadow_validation.passed, shadow_validation.failure);
        check(shadow_output.crust_volume_km3_by_destination[2] == 0.0,
              "CUDA shadow empty row did not preserve a zero volume");
        check(shadow_output.remapped_crust_density_by_destination[2] ==
                  shadow_density[2],
              "CUDA shadow empty row did not preserve fallback density");
        CrustTransportPlan invalid_shadow_plan = shadow_plan;
        invalid_shadow_plan.overlap_area_km2[0] =
            std::numeric_limits<double>::quiet_NaN();
        bool invalid_shadow_rejected = false;
        try {
            session.run_crust_overlap_continuous_shadow(
                invalid_shadow_plan,
                shadow_cells,
                shadow_thickness,
                shadow_density,
                shadow_age,
                shadow_output
            );
        } catch (const std::exception&) {
            invalid_shadow_rejected = true;
        }
        check(invalid_shadow_rejected,
              "CUDA shadow accepted a non-finite overlap operand");
        check(session.telemetry().crust_overlap_continuous_shadow_dispatch_count == 1,
              "rejected CUDA shadow input incremented its dispatch count");

        bool invalid_rejected = false;
        try {
            session.run_smooth_field(cells, std::vector<double>(1), 1, 0.5, output);
        } catch (const std::exception&) {
            invalid_rejected = true;
        }
        check(invalid_rejected, "invalid smoothing input was not rejected");
        check(!session.telemetry().error.empty(),
              "runtime input error was not persisted in telemetry");
        session.run_smooth_field(cells, input_a, 0, 0.5, output);
        check(session.telemetry().error.empty(),
              "a valid operation did not clear the previous CUDA error");

        const auto& telemetry = session.telemetry();
        check(telemetry.plate_assignment_dispatch_count == 1,
              "unexpected plate-assignment dispatch count");
        check(telemetry.smoothing_kernel_dispatch_count == 10,
              "unexpected scalar-smoothing dispatch count");
        check(telemetry.batched_smoothing_kernel_dispatch_count == 5,
              "unexpected fused-smoothing dispatch count");
        check(telemetry.crust_overlap_continuous_shadow_dispatch_count == 1,
              "unexpected conservative-overlap shadow dispatch count");
        check(telemetry.last_threads_per_block == 256,
              "CUDA launch geometry is not the audited 256-thread block");

        if (caller_device >= 0) {
            int current_device = -1;
            check(cudaGetDevice(&current_device) == cudaSuccess,
                  "cudaGetDevice failed after CUDA operations");
            check(current_device == caller_device,
                  "CUDA operation changed the caller's current device");
        }

        const auto invalid_probe = CudaComputeSession::probe(
            session.telemetry().device_count
        );
        check(!invalid_probe.available,
              "out-of-range explicit CUDA ordinal unexpectedly succeeded");
        check(!invalid_probe.error.empty(),
              "out-of-range CUDA ordinal did not report an error");
        std::cout << "CUDA raw-kernel edge tests passed\n";
        return EXIT_SUCCESS;
    } catch (const std::exception& error) {
        std::cerr << "CUDA raw-kernel edge test failed: " << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
