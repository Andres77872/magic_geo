#include "cuda_compute.hpp"

#include <cuda_runtime.h>

#include <algorithm>
#include <chrono>
#include <climits>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace magic_geo::detail {
namespace {

constexpr int CUDA_BLOCK_THREADS = 256;
constexpr int CUDA_WARP_THREADS = 32;
constexpr int CUDA_WARPS_PER_BLOCK = CUDA_BLOCK_THREADS / CUDA_WARP_THREADS;

template <typename T>
__device__ __forceinline__ T read_only(const T* pointer) {
#if defined(__CUDA_ARCH__) && __CUDA_ARCH__ >= 350
    return __ldg(pointer);
#else
    return *pointer;
#endif
}

__global__ __launch_bounds__(CUDA_BLOCK_THREADS) void assign_plates_kernel(
    const double* __restrict__ position_x,
    const double* __restrict__ position_y,
    const double* __restrict__ position_z,
    const double* __restrict__ center_x,
    const double* __restrict__ center_y,
    const double* __restrict__ center_z,
    int center_count,
    int cell_count,
    int* __restrict__ plate_ids
) {
    const int cell_id = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
    if (cell_id >= cell_count) {
        return;
    }
    const double px = read_only(position_x + cell_id);
    const double py = read_only(position_y + cell_id);
    const double pz = read_only(position_z + cell_id);
    double best = -2.0;
    int best_plate = 0;
    for (int plate_id = 0; plate_id < center_count; ++plate_id) {
        double score = px * read_only(center_x + plate_id);
        score = score + py * read_only(center_y + plate_id);
        score = score + pz * read_only(center_z + plate_id);
        if (score > best) {
            best = score;
            best_plate = plate_id;
        }
    }
    plate_ids[cell_id] = best_plate;
}

__global__ __launch_bounds__(CUDA_BLOCK_THREADS) void smooth_field_kernel(
    const int* __restrict__ neighbor_offsets,
    const int* __restrict__ neighbor_ids,
    const double* __restrict__ current,
    double* __restrict__ next,
    int cell_count,
    double self_weight
) {
    const int cell_id = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
    if (cell_id >= cell_count) {
        return;
    }
    const int begin = read_only(neighbor_offsets + cell_id);
    const int end = read_only(neighbor_offsets + cell_id + 1);
    double sum = 0.0;
    for (int position = begin; position < end; ++position) {
        const int neighbor_id = read_only(neighbor_ids + position);
        sum = sum + read_only(current + neighbor_id);
    }
    const double value = read_only(current + cell_id);
    const double average = end == begin
        ? value
        : sum / static_cast<double>(end - begin);
    next[cell_id] = self_weight * value + (1.0 - self_weight) * average;
}

__global__ __launch_bounds__(CUDA_BLOCK_THREADS) void smooth_three_fields_kernel(
    const int* __restrict__ neighbor_offsets,
    const int* __restrict__ neighbor_ids,
    const double* __restrict__ current,
    double* __restrict__ next,
    int cell_count,
    double self_weight_a,
    double self_weight_b,
    double self_weight_c
) {
    const int cell_id = static_cast<int>(blockIdx.x * blockDim.x + threadIdx.x);
    if (cell_id >= cell_count) {
        return;
    }
    const int begin = read_only(neighbor_offsets + cell_id);
    const int end = read_only(neighbor_offsets + cell_id + 1);
    const std::size_t stride = static_cast<std::size_t>(cell_count);
    const std::size_t index = static_cast<std::size_t>(cell_id);
    double sum_a = 0.0;
    double sum_b = 0.0;
    double sum_c = 0.0;
    for (int position = begin; position < end; ++position) {
        const int neighbor_id = read_only(neighbor_ids + position);
        const std::size_t neighbor = static_cast<std::size_t>(neighbor_id);
        sum_a = sum_a + read_only(current + neighbor);
        sum_b = sum_b + read_only(current + stride + neighbor);
        sum_c = sum_c + read_only(current + 2U * stride + neighbor);
    }
    const int degree = end - begin;
    const double value_a = read_only(current + index);
    const double value_b = read_only(current + stride + index);
    const double value_c = read_only(current + 2U * stride + index);
    const double average_a = degree == 0 ? value_a : sum_a / static_cast<double>(degree);
    const double average_b = degree == 0 ? value_b : sum_b / static_cast<double>(degree);
    const double average_c = degree == 0 ? value_c : sum_c / static_cast<double>(degree);
    next[index] = self_weight_a * value_a + (1.0 - self_weight_a) * average_a;
    next[stride + index] =
        self_weight_b * value_b + (1.0 - self_weight_b) * average_b;
    next[2U * stride + index] =
        self_weight_c * value_c + (1.0 - self_weight_c) * average_c;
}

__global__ __launch_bounds__(CUDA_BLOCK_THREADS) void remap_crust_sources_kernel(
    const double* __restrict__ mesh_x,
    const double* __restrict__ mesh_y,
    const double* __restrict__ mesh_z,
    const double* __restrict__ query_x,
    const double* __restrict__ query_y,
    const double* __restrict__ query_z,
    const int* __restrict__ current_plate_ids,
    const int* __restrict__ candidate_offsets,
    const int* __restrict__ candidate_ids,
    int cell_count,
    int* __restrict__ source_cell_ids
) {
    const int lane = static_cast<int>(threadIdx.x) & (CUDA_WARP_THREADS - 1);
    const int warp_in_block = static_cast<int>(threadIdx.x) / CUDA_WARP_THREADS;
    const int cell_id =
        static_cast<int>(blockIdx.x) * CUDA_WARPS_PER_BLOCK + warp_in_block;
    if (cell_id >= cell_count) {
        return;
    }
    constexpr unsigned FULL_WARP = 0xffffffffU;
    double qx = lane == 0 ? read_only(query_x + cell_id) : 0.0;
    double qy = lane == 0 ? read_only(query_y + cell_id) : 0.0;
    double qz = lane == 0 ? read_only(query_z + cell_id) : 0.0;
    qx = __shfl_sync(FULL_WARP, qx, 0);
    qy = __shfl_sync(FULL_WARP, qy, 0);
    qz = __shfl_sync(FULL_WARP, qz, 0);
    const int plate_id = read_only(current_plate_ids + cell_id);
    const int begin = read_only(candidate_offsets + plate_id);
    const int end = read_only(candidate_offsets + plate_id + 1);

    double best_score = -2.0;
    int best_position = INT_MAX;
    int best_source = cell_id;
    for (std::int64_t position = static_cast<std::int64_t>(begin) + lane;
         position < static_cast<std::int64_t>(end);
         position += CUDA_WARP_THREADS) {
        const int candidate = read_only(candidate_ids + position);
        double score = qx * read_only(mesh_x + candidate);
        score = score + qy * read_only(mesh_y + candidate);
        score = score + qz * read_only(mesh_z + candidate);
        if (score > best_score) {
            best_score = score;
            best_position = static_cast<int>(position);
            best_source = candidate;
        }
    }
    for (int offset = CUDA_WARP_THREADS / 2; offset > 0; offset /= 2) {
        const double other_score = __shfl_down_sync(FULL_WARP, best_score, offset);
        const int other_position = __shfl_down_sync(FULL_WARP, best_position, offset);
        const int other_source = __shfl_down_sync(FULL_WARP, best_source, offset);
        if (other_score > best_score ||
            (other_score == best_score && other_position < best_position)) {
            best_score = other_score;
            best_position = other_position;
            best_source = other_source;
        }
    }
    if (lane == 0) {
        source_cell_ids[cell_id] = best_source;
    }
}

// Host-side session implementation follows below. It intentionally lives in
// this translation unit so non-CUDA builds can link cuda_compute_stub.cpp.

}  // namespace
}  // namespace magic_geo::detail

namespace magic_geo::detail {
namespace {

std::string cuda_error_message(const char* operation, cudaError_t status) {
    return std::string(operation) + " failed with CUDA error " +
        std::to_string(static_cast<int>(status)) + " (" +
        cudaGetErrorName(status) + "): " + cudaGetErrorString(status);
}

void require_cuda(cudaError_t status, const char* operation) {
    if (status != cudaSuccess) {
        throw std::runtime_error(cuda_error_message(operation, status));
    }
}

class ScopedCudaDevice final {
public:
    explicit ScopedCudaDevice(int selected_device) {
        require_cuda(
            cudaGetDevice(&previous_device_),
            "cudaGetDevice(before CUDA session operation)"
        );
        if (previous_device_ != selected_device) {
            require_cuda(
                cudaSetDevice(selected_device),
                "cudaSetDevice(CUDA session operation)"
            );
            restore_ = true;
        }
    }

    ~ScopedCudaDevice() {
        if (restore_) {
            (void)cudaSetDevice(previous_device_);
        }
    }

    ScopedCudaDevice(const ScopedCudaDevice&) = delete;
    ScopedCudaDevice& operator=(const ScopedCudaDevice&) = delete;

private:
    int previous_device_ = -1;
    bool restore_ = false;
};

bool supports_fp64(const cudaDeviceProp& properties) {
    return properties.major > 1 ||
        (properties.major == 1 && properties.minor >= 3);
}

std::size_t checked_bytes(
    std::size_t count,
    std::size_t element_size,
    const char* description
) {
    if (element_size != 0 &&
        count > std::numeric_limits<std::size_t>::max() / element_size) {
        throw std::runtime_error(std::string(description) + " size overflow");
    }
    return count * element_size;
}

int checked_int_count(std::size_t count, const char* description) {
    if (count > static_cast<std::size_t>(std::numeric_limits<int>::max())) {
        throw std::runtime_error(
            std::string(description) + " exceeds 32-bit CUDA kernel indices"
        );
    }
    return static_cast<int>(count);
}

std::uint64_t grid_blocks_for_threads(std::size_t logical_threads) {
    return static_cast<std::uint64_t>(
        (logical_threads + CUDA_BLOCK_THREADS - 1) / CUDA_BLOCK_THREADS
    );
}

std::string format_uuid(const cudaUUID_t& uuid) {
    std::ostringstream output;
    output << std::hex << std::setfill('0');
    for (int index = 0; index < 16; ++index) {
        if (index == 4 || index == 6 || index == 8 || index == 10) {
            output << '-';
        }
        output << std::setw(2)
               << static_cast<unsigned int>(
                      static_cast<unsigned char>(uuid.bytes[index])
                  );
    }
    return output.str();
}

template <typename T>
struct DeviceBuffer {
    T* data = nullptr;
    std::size_t capacity = 0;
};

struct HostToDeviceCopy {
    void* destination = nullptr;
    const void* source = nullptr;
    std::size_t bytes = 0;
};

}  // namespace

struct CudaComputeSession::Impl {
    explicit Impl(int requested_device_ordinal) {
        state.compiled = true;
        try {
            initialize(requested_device_ordinal);
        } catch (const std::exception& error) {
            state.available = false;
            state.error = error.what();
            release_all_noexcept();
        } catch (...) {
            state.available = false;
            state.error = "unknown CUDA initialization failure";
            release_all_noexcept();
        }
    }

    ~Impl() {
        release_all_noexcept();
    }

    void initialize(int requested_device_ordinal) {
        require_cuda(cudaDriverGetVersion(&state.driver_version), "cudaDriverGetVersion");
        require_cuda(cudaRuntimeGetVersion(&state.runtime_version), "cudaRuntimeGetVersion");
        require_cuda(cudaGetDeviceCount(&state.device_count), "cudaGetDeviceCount");
        if (state.device_count <= 0) {
            throw std::runtime_error("CUDA runtime reported no NVIDIA devices");
        }

        std::vector<cudaDeviceProp> properties(
            static_cast<std::size_t>(state.device_count)
        );
        std::vector<int> compute_modes(static_cast<std::size_t>(state.device_count));
        std::vector<int> core_clocks_khz(static_cast<std::size_t>(state.device_count));
        std::vector<int> memory_clocks_khz(static_cast<std::size_t>(state.device_count));
        std::vector<int> fp64_perf_ratios(static_cast<std::size_t>(state.device_count));
        for (int ordinal = 0; ordinal < state.device_count; ++ordinal) {
            require_cuda(
                cudaGetDeviceProperties(
                    &properties[static_cast<std::size_t>(ordinal)], ordinal
                ),
                "cudaGetDeviceProperties"
            );
            require_cuda(
                cudaDeviceGetAttribute(
                    &compute_modes[static_cast<std::size_t>(ordinal)],
                    cudaDevAttrComputeMode,
                    ordinal
                ),
                "cudaDeviceGetAttribute(compute mode)"
            );
            require_cuda(
                cudaDeviceGetAttribute(
                    &core_clocks_khz[static_cast<std::size_t>(ordinal)],
                    cudaDevAttrClockRate,
                    ordinal
                ),
                "cudaDeviceGetAttribute(clock rate)"
            );
            require_cuda(
                cudaDeviceGetAttribute(
                    &memory_clocks_khz[static_cast<std::size_t>(ordinal)],
                    cudaDevAttrMemoryClockRate,
                    ordinal
                ),
                "cudaDeviceGetAttribute(memory clock rate)"
            );
            require_cuda(
                cudaDeviceGetAttribute(
                    &fp64_perf_ratios[static_cast<std::size_t>(ordinal)],
                    cudaDevAttrSingleToDoublePrecisionPerfRatio,
                    ordinal
                ),
                "cudaDeviceGetAttribute(FP32-to-FP64 performance ratio)"
            );
        }

        require_cuda(
            cudaGetDevice(&previous_device),
            "cudaGetDevice(before CUDA session selection)"
        );

        const auto meets_kernel_requirements = [&](int ordinal) {
            const cudaDeviceProp& candidate =
                properties[static_cast<std::size_t>(ordinal)];
            return supports_fp64(candidate) &&
                compute_modes[static_cast<std::size_t>(ordinal)] !=
                    cudaComputeModeProhibited &&
                candidate.warpSize == CUDA_WARP_THREADS &&
                candidate.maxThreadsPerBlock >= CUDA_BLOCK_THREADS &&
                candidate.maxThreadsDim[0] >= CUDA_BLOCK_THREADS;
        };
        std::vector<cudaFuncAttributes> kernel_attributes(
            static_cast<std::size_t>(state.device_count)
        );
        std::vector<bool> kernel_compatible(
            static_cast<std::size_t>(state.device_count), false
        );
        for (int ordinal = 0; ordinal < state.device_count; ++ordinal) {
            if (!meets_kernel_requirements(ordinal)) {
                continue;
            }
            cudaError_t status = cudaSetDevice(ordinal);
            if (status == cudaSuccess) {
                status = cudaFree(nullptr);
            }
            if (status == cudaSuccess) {
                status = cudaFuncGetAttributes(
                    &kernel_attributes[static_cast<std::size_t>(ordinal)],
                    assign_plates_kernel
                );
            }
            if (status == cudaSuccess) {
                kernel_compatible[static_cast<std::size_t>(ordinal)] = true;
            } else {
                (void)cudaGetLastError();
            }
        }

        if (requested_device_ordinal >= state.device_count) {
            throw std::runtime_error(
                "requested CUDA device ordinal " +
                std::to_string(requested_device_ordinal) + " is out of range"
            );
        }
        if (requested_device_ordinal >= 0) {
            selected_device = requested_device_ordinal;
        } else {
            long long best_fp64_score = std::numeric_limits<long long>::min();
            long long best_bandwidth_score = std::numeric_limits<long long>::min();
            std::uint64_t best_memory = 0;
            int best_capability = -1;
            for (int ordinal = 0; ordinal < state.device_count; ++ordinal) {
                const cudaDeviceProp& candidate =
                    properties[static_cast<std::size_t>(ordinal)];
                if (!kernel_compatible[static_cast<std::size_t>(ordinal)]) {
                    continue;
                }
                const int fp64_ratio = std::max(
                    1, fp64_perf_ratios[static_cast<std::size_t>(ordinal)]
                );
                const long long fp64_score =
                    static_cast<long long>(candidate.multiProcessorCount) *
                    static_cast<long long>(
                        core_clocks_khz[static_cast<std::size_t>(ordinal)]
                    ) * 1024LL / fp64_ratio;
                const long long bandwidth_score =
                    static_cast<long long>(
                        memory_clocks_khz[static_cast<std::size_t>(ordinal)]
                    ) * static_cast<long long>(candidate.memoryBusWidth);
                const int capability = candidate.major * 100 + candidate.minor;
                const bool better = fp64_score > best_fp64_score ||
                    (fp64_score == best_fp64_score &&
                     bandwidth_score > best_bandwidth_score) ||
                    (fp64_score == best_fp64_score &&
                     bandwidth_score == best_bandwidth_score &&
                     candidate.totalGlobalMem > best_memory) ||
                    (fp64_score == best_fp64_score &&
                     bandwidth_score == best_bandwidth_score &&
                     candidate.totalGlobalMem == best_memory &&
                     capability > best_capability);
                if (better) {
                    best_fp64_score = fp64_score;
                    best_bandwidth_score = bandwidth_score;
                    best_memory = candidate.totalGlobalMem;
                    best_capability = capability;
                    selected_device = ordinal;
                }
            }
        }
        if (selected_device < 0) {
            throw std::runtime_error(
                "no available CUDA device supports the required FP64 and "
                "256-thread kernel configuration"
            );
        }

        const cudaDeviceProp& selected =
            properties[static_cast<std::size_t>(selected_device)];
        if (!supports_fp64(selected)) {
            throw std::runtime_error("selected CUDA device does not support FP64");
        }
        if (compute_modes[static_cast<std::size_t>(selected_device)] ==
            cudaComputeModeProhibited) {
            throw std::runtime_error("selected CUDA device is in prohibited compute mode");
        }
        if (selected.warpSize != CUDA_WARP_THREADS ||
            selected.maxThreadsPerBlock < CUDA_BLOCK_THREADS ||
            selected.maxThreadsDim[0] < CUDA_BLOCK_THREADS) {
            throw std::runtime_error(
                "selected CUDA device cannot run the required 256-thread, 32-lane kernels"
            );
        }
        if (!kernel_compatible[static_cast<std::size_t>(selected_device)]) {
            throw std::runtime_error(
                "selected CUDA device has no executable image for the configured "
                "MAGIC_GEO_CUDA_ARCHITECTURES"
            );
        }

        state.selected_device_ordinal = selected_device;
        state.nvidia_device = true;
        state.device_vendor = "NVIDIA";
        state.device_name = selected.name;
        state.fp64_supported = true;
        state.compute_capability_major = selected.major;
        state.compute_capability_minor = selected.minor;
        state.total_global_memory_bytes =
            static_cast<std::uint64_t>(selected.totalGlobalMem);
        state.multiprocessor_count = selected.multiProcessorCount;
        state.warp_size = selected.warpSize;
        state.max_threads_per_block = selected.maxThreadsPerBlock;
        state.max_threads_per_multiprocessor = selected.maxThreadsPerMultiProcessor;
        for (int dimension = 0; dimension < 3; ++dimension) {
            state.max_block_dimensions[static_cast<std::size_t>(dimension)] =
                selected.maxThreadsDim[dimension];
            state.max_grid_dimensions[static_cast<std::size_t>(dimension)] =
                selected.maxGridSize[dimension];
        }
        state.l2_cache_bytes = static_cast<std::uint64_t>(selected.l2CacheSize);
        state.shared_memory_per_block_bytes =
            static_cast<std::uint64_t>(selected.sharedMemPerBlock);
        state.shared_memory_per_multiprocessor_bytes =
            static_cast<std::uint64_t>(selected.sharedMemPerMultiprocessor);
        state.registers_per_block = selected.regsPerBlock;
        state.registers_per_multiprocessor = selected.regsPerMultiprocessor;
        state.core_clock_khz =
            core_clocks_khz[static_cast<std::size_t>(selected_device)];
        state.memory_clock_khz =
            memory_clocks_khz[static_cast<std::size_t>(selected_device)];
        state.memory_bus_width_bits = selected.memoryBusWidth;

        require_cuda(cudaSetDevice(selected_device), "cudaSetDevice");
        selected_device_activated = true;
        require_cuda(cudaFree(nullptr), "CUDA primary-context initialization");
        std::size_t free_memory = 0;
        std::size_t total_memory = 0;
        require_cuda(
            cudaMemGetInfo(&free_memory, &total_memory),
            "cudaMemGetInfo"
        );
        state.free_global_memory_bytes = static_cast<std::uint64_t>(free_memory);
        state.total_global_memory_bytes = static_cast<std::uint64_t>(total_memory);

        char pci_bus_id[32]{};
        require_cuda(
            cudaDeviceGetPCIBusId(
                pci_bus_id, static_cast<int>(sizeof(pci_bus_id)), selected_device
            ),
            "cudaDeviceGetPCIBusId"
        );
        state.pci_bus_id = pci_bus_id;
        state.device_uuid = format_uuid(selected.uuid);

        require_cuda(
            cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking),
            "cudaStreamCreateWithFlags"
        );
        require_cuda(cudaEventCreate(&timing_start), "cudaEventCreate(start)");
        require_cuda(cudaEventCreate(&timing_stop), "cudaEventCreate(stop)");

        const cudaFuncAttributes& attributes =
            kernel_attributes[static_cast<std::size_t>(selected_device)];
        state.kernel_binary_version = attributes.binaryVersion;
        state.kernel_ptx_version = attributes.ptxVersion;
        state.sm_120_optimized = selected.major == 12 && selected.minor == 0 &&
            (attributes.binaryVersion >= 120 || attributes.ptxVersion >= 120);
        state.runtime_initialized = true;
        state.available = true;
        state.error.clear();
        if (previous_device != selected_device) {
            require_cuda(
                cudaSetDevice(previous_device),
                "cudaSetDevice(restore after CUDA session initialization)"
            );
        }
    }

    void ensure_available() const {
        if (!state.available || !state.runtime_initialized) {
            throw std::runtime_error(
                state.error.empty()
                    ? "CUDA compute session is not available"
                    : "CUDA compute session is not available: " + state.error
            );
        }
    }

    template <typename T>
    void release_buffer_checked(DeviceBuffer<T>& buffer, const char* operation) {
        if (buffer.data == nullptr) {
            buffer.capacity = 0;
            return;
        }
        const std::uint64_t bytes = static_cast<std::uint64_t>(
            buffer.capacity * sizeof(T)
        );
        require_cuda(cudaFree(buffer.data), operation);
        buffer.data = nullptr;
        buffer.capacity = 0;
        state.allocated_device_bytes =
            state.allocated_device_bytes >= bytes
                ? state.allocated_device_bytes - bytes
                : 0;
    }

    template <typename T>
    void release_buffer_noexcept(DeviceBuffer<T>& buffer) noexcept {
        if (buffer.data != nullptr) {
            (void)cudaFree(buffer.data);
            buffer.data = nullptr;
        }
        buffer.capacity = 0;
    }

    template <typename T>
    void ensure_capacity(
        DeviceBuffer<T>& buffer,
        std::size_t required_count,
        const char* description
    ) {
        if (required_count <= buffer.capacity) {
            return;
        }
        const std::size_t bytes = checked_bytes(
            required_count, sizeof(T), description
        );
        release_buffer_checked(buffer, "cudaFree(replaced capacity buffer)");
        T* allocation = nullptr;
        require_cuda(
            cudaMalloc(reinterpret_cast<void**>(&allocation), bytes),
            description
        );
        if (allocation == nullptr) {
            throw std::runtime_error(std::string(description) + " returned null");
        }
        buffer.data = allocation;
        buffer.capacity = required_count;
        state.device_allocation_count++;
        state.allocated_device_bytes += static_cast<std::uint64_t>(bytes);
        state.peak_allocated_device_bytes = std::max(
            state.peak_allocated_device_bytes, state.allocated_device_bytes
        );
    }

    template <typename Callable>
    double timed_stream_segment(Callable&& callable) {
        require_cuda(cudaEventRecord(timing_start, stream), "cudaEventRecord(start)");
        callable();
        require_cuda(cudaEventRecord(timing_stop, stream), "cudaEventRecord(stop)");
        require_cuda(cudaEventSynchronize(timing_stop), "cudaEventSynchronize(stop)");
        float milliseconds = 0.0F;
        require_cuda(
            cudaEventElapsedTime(&milliseconds, timing_start, timing_stop),
            "cudaEventElapsedTime"
        );
        return static_cast<double>(milliseconds);
    }

    void copy_host_to_device(
        void* destination,
        const void* source,
        std::size_t bytes
    ) {
        const HostToDeviceCopy copy{destination, source, bytes};
        copy_host_to_device_batch(&copy, 1);
    }

    void copy_host_to_device_batch(
        const HostToDeviceCopy* copies,
        std::size_t copy_count
    ) {
        std::uint64_t total_bytes = 0;
        for (std::size_t index = 0; index < copy_count; ++index) {
            if (copies[index].bytes >
                std::numeric_limits<std::uint64_t>::max() - total_bytes) {
                throw std::runtime_error("CUDA host-to-device byte counter overflow");
            }
            total_bytes += static_cast<std::uint64_t>(copies[index].bytes);
        }
        if (total_bytes == 0) {
            return;
        }
        const double milliseconds = timed_stream_segment([&] {
            for (std::size_t index = 0; index < copy_count; ++index) {
                if (copies[index].bytes == 0) {
                    continue;
                }
                require_cuda(
                    cudaMemcpyAsync(
                        copies[index].destination,
                        copies[index].source,
                        copies[index].bytes,
                        cudaMemcpyHostToDevice,
                        stream
                    ),
                    "cudaMemcpyAsync(host-to-device)"
                );
            }
        });
        state.host_to_device_bytes += total_bytes;
        state.transfer_time_ms += milliseconds;
        operation_transfer_time_ms += milliseconds;
    }

    void copy_device_to_host(
        void* destination,
        const void* source,
        std::size_t bytes
    ) {
        if (bytes == 0) {
            return;
        }
        const double milliseconds = timed_stream_segment([&] {
            require_cuda(
                cudaMemcpyAsync(
                    destination, source, bytes, cudaMemcpyDeviceToHost, stream
                ),
                "cudaMemcpyAsync(device-to-host)"
            );
        });
        state.device_to_host_bytes += static_cast<std::uint64_t>(bytes);
        state.transfer_time_ms += milliseconds;
        operation_transfer_time_ms += milliseconds;
    }

    template <typename Callable>
    void launch_timed(Callable&& callable) {
        const double milliseconds = timed_stream_segment([&] {
            callable();
            require_cuda(cudaPeekAtLastError(), "CUDA kernel launch");
        });
        state.kernel_time_ms += milliseconds;
        operation_kernel_time_ms += milliseconds;
    }

    std::chrono::steady_clock::time_point begin_operation() {
        operation_kernel_time_ms = 0.0;
        operation_transfer_time_ms = 0.0;
        return std::chrono::steady_clock::now();
    }

    void finish_operation(std::chrono::steady_clock::time_point started) {
        const double milliseconds =
            std::chrono::duration<double, std::milli>(
                std::chrono::steady_clock::now() - started
            ).count();
        state.last_kernel_time_ms = operation_kernel_time_ms;
        state.last_transfer_time_ms = operation_transfer_time_ms;
        state.last_operation_time_ms = milliseconds;
        state.operation_time_ms += milliseconds;
    }

    void set_last_launch(
        std::size_t logical_items,
        std::uint64_t grid_blocks,
        std::uint32_t warps_per_block
    ) {
        state.last_logical_work_items = static_cast<std::uint64_t>(logical_items);
        state.last_grid_blocks = grid_blocks;
        state.last_threads_per_block = CUDA_BLOCK_THREADS;
        state.last_warps_per_block = warps_per_block;
    }

    void ensure_mesh_identity(const std::vector<Cell>& cells) {
        const Cell* identity = cells.empty() ? nullptr : cells.data();
        if (mesh_identity != identity || mesh_cell_count != cells.size()) {
            mesh_identity = identity;
            mesh_cell_count = cells.size();
            positions_ready = false;
            adjacency_ready = false;
        }
    }

    void ensure_positions(const std::vector<Cell>& cells) {
        ensure_mesh_identity(cells);
        if (positions_ready) {
            return;
        }
        checked_int_count(cells.size(), "CUDA mesh cell count");
        if (cells.empty()) {
            positions_ready = true;
            return;
        }
        std::vector<double> x(cells.size());
        std::vector<double> y(cells.size());
        std::vector<double> z(cells.size());
        for (std::size_t index = 0; index < cells.size(); ++index) {
            x[index] = cells[index].p.x;
            y[index] = cells[index].p.y;
            z[index] = cells[index].p.z;
        }
        ensure_capacity(mesh_x, cells.size(), "cudaMalloc(mesh x positions)");
        ensure_capacity(mesh_y, cells.size(), "cudaMalloc(mesh y positions)");
        ensure_capacity(mesh_z, cells.size(), "cudaMalloc(mesh z positions)");
        const std::size_t bytes = checked_bytes(
            cells.size(), sizeof(double), "CUDA mesh position upload"
        );
        const HostToDeviceCopy copies[] = {
            {mesh_x.data, x.data(), bytes},
            {mesh_y.data, y.data(), bytes},
            {mesh_z.data, z.data(), bytes},
        };
        copy_host_to_device_batch(copies, 3);
        positions_ready = true;
        state.mesh_upload_count++;
    }

    void ensure_adjacency(const std::vector<Cell>& cells) {
        ensure_mesh_identity(cells);
        if (adjacency_ready) {
            return;
        }
        checked_int_count(cells.size(), "CUDA mesh cell count");
        std::vector<int> offsets(cells.size() + 1, 0);
        std::size_t edge_count = 0;
        for (std::size_t cell_id = 0; cell_id < cells.size(); ++cell_id) {
            if (cells[cell_id].neighbors.size() >
                static_cast<std::size_t>(std::numeric_limits<int>::max()) - edge_count) {
                throw std::runtime_error(
                    "CUDA mesh adjacency exceeds 32-bit kernel indices"
                );
            }
            edge_count += cells[cell_id].neighbors.size();
            offsets[cell_id + 1] = static_cast<int>(edge_count);
        }
        std::vector<int> neighbors;
        neighbors.reserve(edge_count);
        for (const Cell& cell : cells) {
            for (int neighbor_id : cell.neighbors) {
                if (neighbor_id < 0 ||
                    neighbor_id >= static_cast<int>(cells.size())) {
                    throw std::runtime_error(
                        "CUDA mesh adjacency contains an invalid cell id"
                    );
                }
                neighbors.push_back(neighbor_id);
            }
        }
        ensure_capacity(
            neighbor_offsets, offsets.size(), "cudaMalloc(neighbor offsets)"
        );
        ensure_capacity(
            neighbor_ids,
            std::max<std::size_t>(1, neighbors.size()),
            "cudaMalloc(neighbor ids)"
        );
        const HostToDeviceCopy copies[] = {
            {
                neighbor_offsets.data,
                offsets.data(),
                checked_bytes(offsets.size(), sizeof(int), "neighbor offset upload")
            },
            {
                neighbor_ids.data,
                neighbors.empty() ? nullptr : neighbors.data(),
                checked_bytes(neighbors.size(), sizeof(int), "neighbor id upload")
            },
        };
        copy_host_to_device_batch(copies, 2);
        adjacency_ready = true;
        state.mesh_upload_count++;
    }

    void run_assign_plates(
        const std::vector<Vec3>& centers,
        const std::vector<Cell>& cells,
        std::vector<int>& plate_ids
    ) {
        ensure_available();
        state.error.clear();
        const ScopedCudaDevice device_guard(selected_device);
        if (centers.empty()) {
            throw std::runtime_error(
                "CUDA plate assignment requires at least one center"
            );
        }
        const int center_count = checked_int_count(
            centers.size(), "CUDA plate center count"
        );
        const int cell_count = checked_int_count(
            cells.size(), "CUDA plate-assignment cell count"
        );
        if (cells.empty()) {
            plate_ids.clear();
            return;
        }
        const auto started = begin_operation();
        ensure_positions(cells);
        ensure_capacity(center_x, centers.size(), "cudaMalloc(plate center x)");
        ensure_capacity(center_y, centers.size(), "cudaMalloc(plate center y)");
        ensure_capacity(center_z, centers.size(), "cudaMalloc(plate center z)");
        ensure_capacity(plate_id_output, cells.size(), "cudaMalloc(plate id output)");

        std::vector<double> x(centers.size());
        std::vector<double> y(centers.size());
        std::vector<double> z(centers.size());
        for (std::size_t index = 0; index < centers.size(); ++index) {
            x[index] = centers[index].x;
            y[index] = centers[index].y;
            z[index] = centers[index].z;
        }
        const std::size_t center_bytes = checked_bytes(
            centers.size(), sizeof(double), "CUDA plate center upload"
        );
        const HostToDeviceCopy center_copies[] = {
            {center_x.data, x.data(), center_bytes},
            {center_y.data, y.data(), center_bytes},
            {center_z.data, z.data(), center_bytes},
        };
        copy_host_to_device_batch(center_copies, 3);

        const std::uint64_t blocks = grid_blocks_for_threads(cells.size());
        if (blocks > static_cast<std::uint64_t>(state.max_grid_dimensions[0])) {
            throw std::runtime_error("CUDA plate-assignment grid exceeds device limits");
        }
        launch_timed([&] {
            assign_plates_kernel<<<
                static_cast<unsigned int>(blocks), CUDA_BLOCK_THREADS, 0, stream
            >>>(
                mesh_x.data,
                mesh_y.data,
                mesh_z.data,
                center_x.data,
                center_y.data,
                center_z.data,
                center_count,
                cell_count,
                plate_id_output.data
            );
            require_cuda(cudaPeekAtLastError(), "assign_plates_kernel launch");
        });
        state.kernel_dispatch_count++;
        state.plate_assignment_dispatch_count++;
        set_last_launch(cells.size(), blocks, CUDA_WARPS_PER_BLOCK);
        std::vector<int> gpu_plate_ids(cells.size());
        copy_device_to_host(
            gpu_plate_ids.data(),
            plate_id_output.data,
            checked_bytes(
                gpu_plate_ids.size(), sizeof(int), "CUDA plate id download"
            )
        );
        for (int plate_id : gpu_plate_ids) {
            if (plate_id < 0 || plate_id >= center_count) {
                throw std::runtime_error(
                    "CUDA plate assignment returned an invalid plate id"
                );
            }
        }
        plate_ids = std::move(gpu_plate_ids);
        finish_operation(started);
    }

    void run_smooth_field(
        const std::vector<Cell>& cells,
        const std::vector<double>& input,
        int steps,
        double self_weight,
        std::vector<double>& output
    ) {
        ensure_available();
        state.error.clear();
        const ScopedCudaDevice device_guard(selected_device);
        if (input.size() != cells.size()) {
            throw std::runtime_error(
                "CUDA smoothing input size does not match the mesh"
            );
        }
        if (steps < 0 || !std::isfinite(self_weight)) {
            throw std::runtime_error("CUDA smoothing parameters are invalid");
        }
        checked_int_count(cells.size(), "CUDA smoothing cell count");
        if (steps == 0 || cells.empty()) {
            output = input;
            return;
        }
        const auto started = begin_operation();
        ensure_adjacency(cells);
        ensure_capacity(smooth_a, cells.size(), "cudaMalloc(smoothing buffer a)");
        ensure_capacity(smooth_b, cells.size(), "cudaMalloc(smoothing buffer b)");
        const std::size_t bytes = checked_bytes(
            input.size(), sizeof(double), "CUDA smoothing field"
        );
        copy_host_to_device(smooth_a.data, input.data(), bytes);

        double* current = smooth_a.data;
        double* next = smooth_b.data;
        const int cell_count = static_cast<int>(cells.size());
        const std::uint64_t blocks = grid_blocks_for_threads(cells.size());
        if (blocks > static_cast<std::uint64_t>(state.max_grid_dimensions[0])) {
            throw std::runtime_error("CUDA smoothing grid exceeds device limits");
        }
        launch_timed([&] {
            for (int step = 0; step < steps; ++step) {
                smooth_field_kernel<<<
                    static_cast<unsigned int>(blocks), CUDA_BLOCK_THREADS, 0, stream
                >>>(
                    neighbor_offsets.data,
                    neighbor_ids.data,
                    current,
                    next,
                    cell_count,
                    self_weight
                );
                require_cuda(
                    cudaPeekAtLastError(), "smooth_field_kernel launch"
                );
                std::swap(current, next);
            }
        });
        state.kernel_dispatch_count += static_cast<std::uint64_t>(steps);
        state.smoothing_kernel_dispatch_count += static_cast<std::uint64_t>(steps);
        set_last_launch(cells.size(), blocks, CUDA_WARPS_PER_BLOCK);
        std::vector<double> gpu_output(input.size());
        copy_device_to_host(gpu_output.data(), current, bytes);
        output = std::move(gpu_output);
        state.smoothing_operation_count++;
        finish_operation(started);
    }

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
    ) {
        ensure_available();
        state.error.clear();
        const ScopedCudaDevice device_guard(selected_device);
        if (input_a.size() != cells.size() || input_b.size() != cells.size() ||
            input_c.size() != cells.size()) {
            throw std::runtime_error(
                "CUDA batched smoothing inputs do not match the mesh"
            );
        }
        if (steps < 0 || !std::isfinite(self_weight_a) ||
            !std::isfinite(self_weight_b) || !std::isfinite(self_weight_c)) {
            throw std::runtime_error(
                "CUDA batched smoothing parameters are invalid"
            );
        }
        checked_int_count(cells.size(), "CUDA batched-smoothing cell count");
        if (steps == 0 || cells.empty()) {
            output_a = input_a;
            output_b = input_b;
            output_c = input_c;
            return;
        }
        if (cells.size() >
            std::numeric_limits<std::size_t>::max() / 3U) {
            throw std::runtime_error("CUDA batched smoothing element-count overflow");
        }
        const auto started = begin_operation();
        ensure_adjacency(cells);
        const std::size_t field_size = cells.size();
        const std::size_t element_count = 3U * field_size;
        ensure_capacity(
            smooth_three_a, element_count, "cudaMalloc(batched smoothing buffer a)"
        );
        ensure_capacity(
            smooth_three_b, element_count, "cudaMalloc(batched smoothing buffer b)"
        );
        std::vector<double> packed(element_count);
        std::copy(input_a.begin(), input_a.end(), packed.begin());
        std::copy(input_b.begin(), input_b.end(), packed.begin() + field_size);
        std::copy(input_c.begin(), input_c.end(), packed.begin() + 2U * field_size);
        const std::size_t bytes = checked_bytes(
            element_count, sizeof(double), "CUDA batched smoothing fields"
        );
        copy_host_to_device(smooth_three_a.data, packed.data(), bytes);

        double* current = smooth_three_a.data;
        double* next = smooth_three_b.data;
        const int cell_count = static_cast<int>(cells.size());
        const std::uint64_t blocks = grid_blocks_for_threads(cells.size());
        if (blocks > static_cast<std::uint64_t>(state.max_grid_dimensions[0])) {
            throw std::runtime_error("CUDA batched-smoothing grid exceeds device limits");
        }
        launch_timed([&] {
            for (int step = 0; step < steps; ++step) {
                smooth_three_fields_kernel<<<
                    static_cast<unsigned int>(blocks), CUDA_BLOCK_THREADS, 0, stream
                >>>(
                    neighbor_offsets.data,
                    neighbor_ids.data,
                    current,
                    next,
                    cell_count,
                    self_weight_a,
                    self_weight_b,
                    self_weight_c
                );
                require_cuda(
                    cudaPeekAtLastError(), "smooth_three_fields_kernel launch"
                );
                std::swap(current, next);
            }
        });
        state.kernel_dispatch_count += static_cast<std::uint64_t>(steps);
        state.batched_smoothing_kernel_dispatch_count +=
            static_cast<std::uint64_t>(steps);
        set_last_launch(cells.size(), blocks, CUDA_WARPS_PER_BLOCK);
        copy_device_to_host(packed.data(), current, bytes);
        output_a.assign(packed.begin(), packed.begin() + field_size);
        output_b.assign(
            packed.begin() + field_size, packed.begin() + 2U * field_size
        );
        output_c.assign(packed.begin() + 2U * field_size, packed.end());
        state.batched_smoothing_operation_count++;
        finish_operation(started);
    }

    void run_remap_crust_sources(
        const std::vector<Cell>& cells,
        const std::vector<Vec3>& backtraced_positions,
        const std::vector<std::vector<int>>& previous_cells_by_plate,
        std::vector<int>& source_cell_ids
    ) {
        ensure_available();
        state.error.clear();
        const ScopedCudaDevice device_guard(selected_device);
        if (cells.size() != backtraced_positions.size() ||
            previous_cells_by_plate.empty()) {
            throw std::runtime_error("CUDA crust-source remap input shape is invalid");
        }
        const int cell_count = checked_int_count(
            cells.size(), "CUDA crust-source remap cell count"
        );
        checked_int_count(
            previous_cells_by_plate.size(), "CUDA crust-source remap plate count"
        );
        if (cells.empty()) {
            source_cell_ids.clear();
            return;
        }
        const auto started = begin_operation();

        std::vector<double> query_x(cells.size());
        std::vector<double> query_y(cells.size());
        std::vector<double> query_z(cells.size());
        std::vector<int> current_plate_ids(cells.size());
        for (std::size_t index = 0; index < cells.size(); ++index) {
            query_x[index] = backtraced_positions[index].x;
            query_y[index] = backtraced_positions[index].y;
            query_z[index] = backtraced_positions[index].z;
            const int plate_id = cells[index].plate_id;
            if (plate_id < 0 ||
                plate_id >= static_cast<int>(previous_cells_by_plate.size())) {
                throw std::runtime_error(
                    "CUDA crust-source remap has an invalid plate id"
                );
            }
            current_plate_ids[index] = plate_id;
        }

        std::vector<int> candidate_offsets(
            previous_cells_by_plate.size() + 1U, 0
        );
        std::vector<int> candidate_ids;
        candidate_ids.reserve(cells.size());
        for (std::size_t plate_id = 0;
             plate_id < previous_cells_by_plate.size();
             ++plate_id) {
            int previous_id = -1;
            for (int candidate : previous_cells_by_plate[plate_id]) {
                if (candidate < 0 || candidate >= cell_count ||
                    candidate <= previous_id) {
                    throw std::runtime_error(
                        "CUDA crust-source candidates must be valid ascending cell ids"
                    );
                }
                if (candidate_ids.size() ==
                    static_cast<std::size_t>(std::numeric_limits<int>::max())) {
                    throw std::runtime_error(
                        "CUDA crust-source candidate list exceeds 32-bit kernel indices"
                    );
                }
                candidate_ids.push_back(candidate);
                previous_id = candidate;
            }
            candidate_offsets[plate_id + 1U] =
                static_cast<int>(candidate_ids.size());
        }
        if (candidate_ids.empty()) {
            throw std::runtime_error("CUDA crust-source remap has no candidates");
        }
        ensure_positions(cells);
        ensure_capacity(remap_query_x, cells.size(), "cudaMalloc(remap query x)");
        ensure_capacity(remap_query_y, cells.size(), "cudaMalloc(remap query y)");
        ensure_capacity(remap_query_z, cells.size(), "cudaMalloc(remap query z)");
        ensure_capacity(remap_plate_ids, cells.size(), "cudaMalloc(remap plate ids)");
        ensure_capacity(remap_source_ids, cells.size(), "cudaMalloc(remap source ids)");
        ensure_capacity(
            remap_candidate_offsets,
            candidate_offsets.size(),
            "cudaMalloc(remap candidate offsets)"
        );
        ensure_capacity(
            remap_candidate_ids,
            candidate_ids.size(),
            "cudaMalloc(remap candidate ids)"
        );
        const std::size_t coordinate_bytes = checked_bytes(
            cells.size(), sizeof(double), "CUDA remap coordinate upload"
        );
        const std::size_t cell_id_bytes = checked_bytes(
            cells.size(), sizeof(int), "CUDA remap cell-id upload"
        );
        const HostToDeviceCopy remap_copies[] = {
            {remap_query_x.data, query_x.data(), coordinate_bytes},
            {remap_query_y.data, query_y.data(), coordinate_bytes},
            {remap_query_z.data, query_z.data(), coordinate_bytes},
            {remap_plate_ids.data, current_plate_ids.data(), cell_id_bytes},
            {
                remap_candidate_offsets.data,
                candidate_offsets.data(),
                checked_bytes(
                    candidate_offsets.size(),
                    sizeof(int),
                    "remap candidate-offset upload"
                )
            },
            {
                remap_candidate_ids.data,
                candidate_ids.data(),
                checked_bytes(
                    candidate_ids.size(), sizeof(int), "remap candidate-id upload"
                )
            },
        };
        copy_host_to_device_batch(remap_copies, 6);

        const std::uint64_t blocks = static_cast<std::uint64_t>(
            (cells.size() + CUDA_WARPS_PER_BLOCK - 1U) / CUDA_WARPS_PER_BLOCK
        );
        if (blocks > static_cast<std::uint64_t>(state.max_grid_dimensions[0])) {
            throw std::runtime_error("CUDA crust-source remap grid exceeds device limits");
        }
        launch_timed([&] {
            remap_crust_sources_kernel<<<
                static_cast<unsigned int>(blocks), CUDA_BLOCK_THREADS, 0, stream
            >>>(
                mesh_x.data,
                mesh_y.data,
                mesh_z.data,
                remap_query_x.data,
                remap_query_y.data,
                remap_query_z.data,
                remap_plate_ids.data,
                remap_candidate_offsets.data,
                remap_candidate_ids.data,
                cell_count,
                remap_source_ids.data
            );
            require_cuda(
                cudaPeekAtLastError(), "remap_crust_sources_kernel launch"
            );
        });
        state.kernel_dispatch_count++;
        state.crust_source_remap_dispatch_count++;
        set_last_launch(cells.size(), blocks, CUDA_WARPS_PER_BLOCK);
        std::vector<int> gpu_source_ids(cells.size());
        copy_device_to_host(
            gpu_source_ids.data(), remap_source_ids.data, cell_id_bytes
        );
        for (std::size_t index = 0; index < gpu_source_ids.size(); ++index) {
            const int source_id = gpu_source_ids[index];
            const int plate_id = current_plate_ids[index];
            const std::vector<int>& candidates =
                previous_cells_by_plate[static_cast<std::size_t>(plate_id)];
            const bool valid = candidates.empty()
                ? source_id == static_cast<int>(index)
                : std::binary_search(candidates.begin(), candidates.end(), source_id);
            if (!valid) {
                throw std::runtime_error(
                    "CUDA crust-source remap returned a source outside its plate segment"
                );
            }
        }
        source_cell_ids = std::move(gpu_source_ids);
        finish_operation(started);
    }

    void release_all_noexcept() noexcept {
        int device_to_restore = previous_device;
        if (state.available) {
            int current_device = -1;
            if (cudaGetDevice(&current_device) == cudaSuccess) {
                device_to_restore = current_device;
            } else {
                (void)cudaGetLastError();
            }
        }
        if (selected_device >= 0 && selected_device_activated) {
            (void)cudaSetDevice(selected_device);
        }
        release_buffer_noexcept(mesh_x);
        release_buffer_noexcept(mesh_y);
        release_buffer_noexcept(mesh_z);
        release_buffer_noexcept(neighbor_offsets);
        release_buffer_noexcept(neighbor_ids);
        release_buffer_noexcept(center_x);
        release_buffer_noexcept(center_y);
        release_buffer_noexcept(center_z);
        release_buffer_noexcept(plate_id_output);
        release_buffer_noexcept(smooth_a);
        release_buffer_noexcept(smooth_b);
        release_buffer_noexcept(smooth_three_a);
        release_buffer_noexcept(smooth_three_b);
        release_buffer_noexcept(remap_query_x);
        release_buffer_noexcept(remap_query_y);
        release_buffer_noexcept(remap_query_z);
        release_buffer_noexcept(remap_plate_ids);
        release_buffer_noexcept(remap_candidate_offsets);
        release_buffer_noexcept(remap_candidate_ids);
        release_buffer_noexcept(remap_source_ids);
        state.allocated_device_bytes = 0;
        if (timing_start != nullptr) {
            (void)cudaEventDestroy(timing_start);
            timing_start = nullptr;
        }
        if (timing_stop != nullptr) {
            (void)cudaEventDestroy(timing_stop);
            timing_stop = nullptr;
        }
        if (stream != nullptr) {
            (void)cudaStreamDestroy(stream);
            stream = nullptr;
        }
        state.runtime_initialized = false;
        state.available = false;
        selected_device = -1;
        selected_device_activated = false;
        previous_device = -1;
        if (device_to_restore >= 0) {
            (void)cudaSetDevice(device_to_restore);
        }
    }

    CudaTelemetry state;
    int selected_device = -1;
    bool selected_device_activated = false;
    int previous_device = -1;
    cudaStream_t stream = nullptr;
    cudaEvent_t timing_start = nullptr;
    cudaEvent_t timing_stop = nullptr;

    const Cell* mesh_identity = nullptr;
    std::size_t mesh_cell_count = 0;
    bool positions_ready = false;
    bool adjacency_ready = false;
    DeviceBuffer<double> mesh_x;
    DeviceBuffer<double> mesh_y;
    DeviceBuffer<double> mesh_z;
    DeviceBuffer<int> neighbor_offsets;
    DeviceBuffer<int> neighbor_ids;

    DeviceBuffer<double> center_x;
    DeviceBuffer<double> center_y;
    DeviceBuffer<double> center_z;
    DeviceBuffer<int> plate_id_output;
    DeviceBuffer<double> smooth_a;
    DeviceBuffer<double> smooth_b;
    DeviceBuffer<double> smooth_three_a;
    DeviceBuffer<double> smooth_three_b;
    DeviceBuffer<double> remap_query_x;
    DeviceBuffer<double> remap_query_y;
    DeviceBuffer<double> remap_query_z;
    DeviceBuffer<int> remap_plate_ids;
    DeviceBuffer<int> remap_candidate_offsets;
    DeviceBuffer<int> remap_candidate_ids;
    DeviceBuffer<int> remap_source_ids;

    double operation_kernel_time_ms = 0.0;
    double operation_transfer_time_ms = 0.0;
};

CudaComputeSession::CudaComputeSession(int requested_device_ordinal)
    : impl_(new Impl(requested_device_ordinal)) {}

CudaComputeSession::~CudaComputeSession() {
    delete impl_;
}

CudaTelemetry CudaComputeSession::probe(int requested_device_ordinal) {
    CudaComputeSession session(requested_device_ordinal);
    return session.telemetry();
}

bool CudaComputeSession::available() const noexcept {
    return impl_ != nullptr && impl_->state.available;
}

const CudaTelemetry& CudaComputeSession::telemetry() const noexcept {
    return impl_->state;
}

void CudaComputeSession::run_assign_plates(
    const std::vector<Vec3>& centers,
    const std::vector<Cell>& cells,
    std::vector<int>& plate_ids
) {
    try {
        impl_->run_assign_plates(centers, cells, plate_ids);
    } catch (const std::exception& error) {
        impl_->state.error = error.what();
        throw;
    }
}

void CudaComputeSession::run_smooth_field(
    const std::vector<Cell>& cells,
    const std::vector<double>& input,
    int steps,
    double self_weight,
    std::vector<double>& output
) {
    try {
        impl_->run_smooth_field(cells, input, steps, self_weight, output);
    } catch (const std::exception& error) {
        impl_->state.error = error.what();
        throw;
    }
}

void CudaComputeSession::run_smooth_three_fields(
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
) {
    try {
        impl_->run_smooth_three_fields(
            cells,
            input_a,
            input_b,
            input_c,
            steps,
            self_weight_a,
            self_weight_b,
            self_weight_c,
            output_a,
            output_b,
            output_c
        );
    } catch (const std::exception& error) {
        impl_->state.error = error.what();
        throw;
    }
}

void CudaComputeSession::run_remap_crust_sources(
    const std::vector<Cell>& cells,
    const std::vector<Vec3>& backtraced_positions,
    const std::vector<std::vector<int>>& previous_cells_by_plate,
    std::vector<int>& source_cell_ids
) {
    try {
        impl_->run_remap_crust_sources(
            cells,
            backtraced_positions,
            previous_cells_by_plate,
            source_cell_ids
        );
    } catch (const std::exception& error) {
        impl_->state.error = error.what();
        throw;
    }
}

}  // namespace magic_geo::detail
