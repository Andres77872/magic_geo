#pragma once

#include "crust_overlap_shadow.hpp"
#include "engine/model.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace magic_geo::detail {

// CUDA capability, device, resource, transfer, dispatch, and timing data for
// one session. Counters are cumulative; the last_* fields describe the most
// recently completed operation/launch.
struct CudaTelemetry {
    bool compiled = false;
    bool runtime_initialized = false;
    bool available = false;
    bool nvidia_device = false;
    bool fp64_supported = false;
    bool sm_120_optimized = false;
    std::string error;

    int device_count = 0;
    int selected_device_ordinal = -1;
    std::string device_vendor;
    std::string device_name;
    std::string device_uuid;
    std::string pci_bus_id;
    int compute_capability_major = 0;
    int compute_capability_minor = 0;
    int kernel_binary_version = 0;
    int kernel_ptx_version = 0;
    int driver_version = 0;
    int runtime_version = 0;

    std::uint64_t total_global_memory_bytes = 0;
    std::uint64_t free_global_memory_bytes = 0;
    int multiprocessor_count = 0;
    int warp_size = 0;
    int max_threads_per_block = 0;
    int max_threads_per_multiprocessor = 0;
    std::array<int, 3> max_block_dimensions{};
    std::array<int, 3> max_grid_dimensions{};
    std::uint64_t l2_cache_bytes = 0;
    std::uint64_t shared_memory_per_block_bytes = 0;
    std::uint64_t shared_memory_per_multiprocessor_bytes = 0;
    int registers_per_block = 0;
    int registers_per_multiprocessor = 0;
    int core_clock_khz = 0;
    int memory_clock_khz = 0;
    int memory_bus_width_bits = 0;

    std::uint64_t kernel_dispatch_count = 0;
    std::uint64_t plate_assignment_dispatch_count = 0;
    std::uint64_t smoothing_operation_count = 0;
    std::uint64_t smoothing_kernel_dispatch_count = 0;
    std::uint64_t batched_smoothing_operation_count = 0;
    std::uint64_t batched_smoothing_kernel_dispatch_count = 0;
    std::uint64_t crust_source_remap_dispatch_count = 0;
    std::uint64_t crust_overlap_continuous_shadow_dispatch_count = 0;
    std::uint64_t host_to_device_bytes = 0;
    std::uint64_t device_to_host_bytes = 0;
    std::uint64_t device_allocation_count = 0;
    std::uint64_t mesh_upload_count = 0;
    std::uint64_t allocated_device_bytes = 0;
    std::uint64_t peak_allocated_device_bytes = 0;

    double kernel_time_ms = 0.0;
    double transfer_time_ms = 0.0;
    double operation_time_ms = 0.0;
    double last_kernel_time_ms = 0.0;
    double last_transfer_time_ms = 0.0;
    double last_operation_time_ms = 0.0;
    std::uint64_t last_logical_work_items = 0;
    std::uint64_t last_grid_blocks = 0;
    std::uint32_t last_threads_per_block = 0;
    std::uint32_t last_warps_per_block = 0;
};

// Owns a CUDA device context, a nonblocking stream, timing events, persistent
// mesh CSR/position buffers, and reusable operation buffers for one world
// generation. The Cell vector's storage, p coordinates, and neighbor lists are
// the generation cache key and must remain stable; other Cell fields may change.
// A negative ordinal selects the highest-scoring compatible FP64 NVIDIA GPU.
// A session is not thread-safe and must be used and destroyed on its creating
// thread; each operation preserves that thread's previously current device.
class CudaComputeSession final {
public:
    struct Impl;

    explicit CudaComputeSession(int requested_device_ordinal = -1);
    ~CudaComputeSession();

    CudaComputeSession(const CudaComputeSession&) = delete;
    CudaComputeSession& operator=(const CudaComputeSession&) = delete;
    CudaComputeSession(CudaComputeSession&&) = delete;
    CudaComputeSession& operator=(CudaComputeSession&&) = delete;

    static CudaTelemetry probe(int requested_device_ordinal = -1);

    [[nodiscard]] bool available() const noexcept;
    [[nodiscard]] const CudaTelemetry& telemetry() const noexcept;

    void run_assign_plates(
        const std::vector<Vec3>& centers,
        const std::vector<Cell>& cells,
        std::vector<int>& plate_ids
    );

    void run_smooth_field(
        const std::vector<Cell>& cells,
        const std::vector<double>& input,
        int steps,
        double self_weight,
        std::vector<double>& output
    );

    void run_smooth_three_fields(
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

    void run_remap_crust_sources(
        const std::vector<Cell>& cells,
        const std::vector<Vec3>& backtraced_positions,
        const std::vector<std::vector<int>>& previous_cells_by_plate,
        std::vector<int>& source_cell_ids
    );

    void run_crust_overlap_continuous_shadow(
        const CrustTransportPlan& transport,
        const std::vector<Cell>& cells,
        const std::vector<double>& source_crust_thickness_km,
        const std::vector<double>& source_crust_density,
        const std::vector<double>& source_crust_age_ma,
        CrustOverlapContinuousShadowResult& output
    );

private:
    Impl* impl_ = nullptr;
};

}  // namespace magic_geo::detail
