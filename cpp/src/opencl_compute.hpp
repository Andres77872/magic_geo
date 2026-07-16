#pragma once

#include "crust_overlap_shadow.hpp"
#include "engine/model.hpp"

#include <memory>
#include <string>
#include <vector>

namespace magic_geo::detail {

// Owns one generation's CPU/OpenCL/CUDA selection and accelerator resources.
// The active session is thread-local so the existing simulation signatures
// remain stable; every accelerated operation still receives and returns
// ordinary host data.
class ComputeSession {
public:
    struct Impl;

    ComputeSession(const Params& params, const ComputeOptions& compute_options);
    ~ComputeSession();

    ComputeSession(const ComputeSession&) = delete;
    ComputeSession& operator=(const ComputeSession&) = delete;
    ComputeSession(ComputeSession&&) = delete;
    ComputeSession& operator=(ComputeSession&&) = delete;

private:
    std::unique_ptr<Impl> impl_;
};

// Return true only when the selected accelerator produced a complete host
// result. In auto mode a runtime failure atomically disables acceleration for
// the rest of the generation and returns false so the caller can execute its
// unchanged CPU implementation. Explicit OpenCL/CUDA requests throw instead.
bool try_accelerated_assign_plates(
    const std::vector<Vec3>& centers,
    const std::vector<Cell>& cells,
    std::vector<int>& plate_ids
);

bool try_accelerated_smooth_field(
    const std::vector<Cell>& cells,
    const std::vector<double>& input,
    int steps,
    double self_weight,
    std::vector<double>& output
);

bool try_accelerated_smooth_three_fields(
    const std::vector<Cell>& cells,
    const std::vector<double>& input_a,
    const std::vector<double>& input_b,
    const std::vector<double>& input_c,
    int steps,
    double self_weight_a,
    double self_weight_b,
    double self_weight_c,
    std::vector<double>& output_a,
    std::vector<double>& output_b,
    std::vector<double>& output_c
);

// Run a diagnostic-only device replay of the continuous extensive-state
// reduction over a CPU-authoritative spherical-overlap CSR. Device output is
// validated against the CPU plan and discarded; this function never mutates
// the plan, cells, categorical state, or coverage geometry.
void reconcile_accelerated_crust_overlap_continuous_shadow(
    const CrustTransportPlan& transport,
    const std::vector<Cell>& cells,
    const std::vector<double>& source_crust_thickness_km,
    const std::vector<double>& source_crust_density,
    const std::vector<double>& source_crust_age_ma
);

// Record one successfully constructed CPU-authoritative conservative overlap
// plan in the active generation session. This is measured execution telemetry,
// not a copy of the configured iteration count.
void record_cpu_conservative_crust_overlap_transition();

// During generation this describes the active ComputeSession. Outside a
// generation it performs a capability-only probe and reports CPU as active.
std::string compute_backend_info_json();

}  // namespace magic_geo::detail
