#include "opencl_compute.hpp"
#include "cuda_compute.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#if defined(__linux__)
#include <dlfcn.h>
#endif

#ifdef _OPENMP
#include <omp.h>
#endif

namespace magic_geo::detail {
namespace {

using cl_bool = std::uint32_t;
using cl_int = std::int32_t;
using cl_uint = std::uint32_t;
using cl_ulong = std::uint64_t;
using cl_bitfield = cl_ulong;
using cl_device_type = cl_bitfield;
using cl_command_queue_properties = cl_bitfield;
using cl_mem_flags = cl_bitfield;
using cl_device_fp_config = cl_bitfield;
using cl_platform_info = cl_uint;
using cl_device_info = cl_uint;
using cl_program_build_info = cl_uint;
using cl_kernel_work_group_info = cl_uint;
using cl_context_properties = std::intptr_t;

struct _cl_platform_id;
struct _cl_device_id;
struct _cl_context;
struct _cl_command_queue;
struct _cl_mem;
struct _cl_program;
struct _cl_kernel;
struct _cl_event;

using cl_platform_id = _cl_platform_id*;
using cl_device_id = _cl_device_id*;
using cl_context = _cl_context*;
using cl_command_queue = _cl_command_queue*;
using cl_mem = _cl_mem*;
using cl_program = _cl_program*;
using cl_kernel = _cl_kernel*;
using cl_event = _cl_event*;

constexpr cl_int CL_SUCCESS = 0;
constexpr cl_int CL_DEVICE_NOT_FOUND = -1;
constexpr cl_device_type CL_DEVICE_TYPE_CPU = 1ULL << 1U;
constexpr cl_device_type CL_DEVICE_TYPE_GPU = 1ULL << 2U;
constexpr cl_device_type CL_DEVICE_TYPE_ACCELERATOR = 1ULL << 3U;
constexpr cl_device_type CL_DEVICE_TYPE_ALL = 0xFFFFFFFFULL;
constexpr cl_bool CL_FALSE = 0;
constexpr cl_bool CL_TRUE = 1;

constexpr cl_platform_info CL_PLATFORM_VERSION = 0x0901;
constexpr cl_platform_info CL_PLATFORM_NAME = 0x0902;
constexpr cl_platform_info CL_PLATFORM_VENDOR = 0x0903;
constexpr cl_device_info CL_DEVICE_TYPE = 0x1000;
constexpr cl_device_info CL_DEVICE_MAX_COMPUTE_UNITS = 0x1002;
constexpr cl_device_info CL_DEVICE_MAX_WORK_ITEM_DIMENSIONS = 0x1003;
constexpr cl_device_info CL_DEVICE_MAX_WORK_GROUP_SIZE = 0x1004;
constexpr cl_device_info CL_DEVICE_MAX_WORK_ITEM_SIZES = 0x1005;
constexpr cl_device_info CL_DEVICE_ADDRESS_BITS = 0x100D;
constexpr cl_device_info CL_DEVICE_MAX_MEM_ALLOC_SIZE = 0x1010;
constexpr cl_device_info CL_DEVICE_GLOBAL_MEM_SIZE = 0x101F;
constexpr cl_device_info CL_DEVICE_ENDIAN_LITTLE = 0x1026;
constexpr cl_device_info CL_DEVICE_AVAILABLE = 0x1027;
constexpr cl_device_info CL_DEVICE_COMPILER_AVAILABLE = 0x1028;
constexpr cl_device_info CL_DEVICE_NAME = 0x102B;
constexpr cl_device_info CL_DEVICE_VENDOR = 0x102C;
constexpr cl_device_info CL_DRIVER_VERSION = 0x102D;
constexpr cl_device_info CL_DEVICE_VERSION = 0x102F;
constexpr cl_device_info CL_DEVICE_EXTENSIONS = 0x1030;
constexpr cl_device_info CL_DEVICE_DOUBLE_FP_CONFIG = 0x1032;
constexpr cl_device_info CL_DEVICE_OPENCL_C_VERSION = 0x103D;
constexpr cl_context_properties CL_CONTEXT_PLATFORM = 0x1084;
constexpr cl_command_queue_properties CL_QUEUE_PROFILING_ENABLE = 1ULL << 1U;
constexpr cl_mem_flags CL_MEM_READ_WRITE = 1ULL << 0U;
constexpr cl_mem_flags CL_MEM_READ_ONLY = 1ULL << 2U;
constexpr cl_program_build_info CL_PROGRAM_BUILD_LOG = 0x1183;
constexpr cl_kernel_work_group_info CL_KERNEL_WORK_GROUP_SIZE = 0x11B0;
constexpr cl_kernel_work_group_info CL_KERNEL_PREFERRED_WORK_GROUP_SIZE_MULTIPLE = 0x11B3;
constexpr int OPENCL_AUTO_MIN_CELL_COUNT = 32768;
constexpr int CUDA_SM_120_AUTO_MIN_CELL_COUNT = 8192;
constexpr int CUDA_UNCALIBRATED_AUTO_MIN_CELL_COUNT = 32768;
constexpr cl_device_fp_config CL_FP_DENORM = 1ULL << 0U;
constexpr cl_device_fp_config CL_FP_INF_NAN = 1ULL << 1U;
constexpr cl_device_fp_config CL_FP_ROUND_TO_NEAREST = 1ULL << 2U;

using ContextNotify = void (*)(const char*, const void*, std::size_t, void*);
using ProgramNotify = void (*)(cl_program, void*);

struct OpenClApi {
    void* library = nullptr;

    cl_int (*get_platform_ids)(cl_uint, cl_platform_id*, cl_uint*) = nullptr;
    cl_int (*get_platform_info)(cl_platform_id, cl_platform_info, std::size_t, void*, std::size_t*) = nullptr;
    cl_int (*get_device_ids)(cl_platform_id, cl_device_type, cl_uint, cl_device_id*, cl_uint*) = nullptr;
    cl_int (*get_device_info)(cl_device_id, cl_device_info, std::size_t, void*, std::size_t*) = nullptr;
    cl_context (*create_context)(const cl_context_properties*, cl_uint, const cl_device_id*, ContextNotify, void*, cl_int*) = nullptr;
    cl_int (*release_context)(cl_context) = nullptr;
    cl_command_queue (*create_command_queue)(cl_context, cl_device_id, cl_command_queue_properties, cl_int*) = nullptr;
    cl_int (*release_command_queue)(cl_command_queue) = nullptr;
    cl_program (*create_program_with_source)(cl_context, cl_uint, const char**, const std::size_t*, cl_int*) = nullptr;
    cl_int (*build_program)(cl_program, cl_uint, const cl_device_id*, const char*, ProgramNotify, void*) = nullptr;
    cl_int (*get_program_build_info)(cl_program, cl_device_id, cl_program_build_info, std::size_t, void*, std::size_t*) = nullptr;
    cl_int (*release_program)(cl_program) = nullptr;
    cl_kernel (*create_kernel)(cl_program, const char*, cl_int*) = nullptr;
    cl_int (*release_kernel)(cl_kernel) = nullptr;
    cl_mem (*create_buffer)(cl_context, cl_mem_flags, std::size_t, void*, cl_int*) = nullptr;
    cl_int (*release_mem_object)(cl_mem) = nullptr;
    cl_int (*set_kernel_arg)(cl_kernel, cl_uint, std::size_t, const void*) = nullptr;
    cl_int (*enqueue_write_buffer)(cl_command_queue, cl_mem, cl_bool, std::size_t, std::size_t, const void*, cl_uint, const cl_event*, cl_event*) = nullptr;
    cl_int (*enqueue_read_buffer)(cl_command_queue, cl_mem, cl_bool, std::size_t, std::size_t, void*, cl_uint, const cl_event*, cl_event*) = nullptr;
    cl_int (*enqueue_ndrange_kernel)(cl_command_queue, cl_kernel, cl_uint, const std::size_t*, const std::size_t*, const std::size_t*, cl_uint, const cl_event*, cl_event*) = nullptr;
    cl_int (*get_kernel_work_group_info)(cl_kernel, cl_device_id, cl_kernel_work_group_info, std::size_t, void*, std::size_t*) = nullptr;

    ~OpenClApi() {
#if defined(__linux__)
        if (library != nullptr) {
            dlclose(library);
        }
#endif
    }

    template <typename T>
    bool load_symbol(T& output, const char* name, std::string& error) {
#if defined(__linux__)
        output = reinterpret_cast<T>(dlsym(library, name));
        if (output == nullptr) {
            error = std::string("OpenCL loader is missing required symbol ") + name;
            return false;
        }
        return true;
#else
        (void)output;
        (void)name;
        error = "OpenCL dynamic loading is only implemented on Linux";
        return false;
#endif
    }

    static std::unique_ptr<OpenClApi> load(bool& loader_found, std::string& error) {
        auto api = std::make_unique<OpenClApi>();
#if defined(__linux__)
        api->library = dlopen("libOpenCL.so.1", RTLD_NOW | RTLD_LOCAL);
        if (api->library == nullptr) {
            api->library = dlopen("libOpenCL.so", RTLD_NOW | RTLD_LOCAL);
        }
        if (api->library == nullptr) {
            error = "OpenCL loader library was not found";
            return nullptr;
        }
        loader_found = true;
#else
        error = "OpenCL dynamic loading is only implemented on Linux";
        return nullptr;
#endif

#define MAGIC_GEO_LOAD_OPENCL(member, symbol) \
        if (!api->load_symbol(api->member, symbol, error)) { return nullptr; }
        MAGIC_GEO_LOAD_OPENCL(get_platform_ids, "clGetPlatformIDs")
        MAGIC_GEO_LOAD_OPENCL(get_platform_info, "clGetPlatformInfo")
        MAGIC_GEO_LOAD_OPENCL(get_device_ids, "clGetDeviceIDs")
        MAGIC_GEO_LOAD_OPENCL(get_device_info, "clGetDeviceInfo")
        MAGIC_GEO_LOAD_OPENCL(create_context, "clCreateContext")
        MAGIC_GEO_LOAD_OPENCL(release_context, "clReleaseContext")
        MAGIC_GEO_LOAD_OPENCL(create_command_queue, "clCreateCommandQueue")
        MAGIC_GEO_LOAD_OPENCL(release_command_queue, "clReleaseCommandQueue")
        MAGIC_GEO_LOAD_OPENCL(create_program_with_source, "clCreateProgramWithSource")
        MAGIC_GEO_LOAD_OPENCL(build_program, "clBuildProgram")
        MAGIC_GEO_LOAD_OPENCL(get_program_build_info, "clGetProgramBuildInfo")
        MAGIC_GEO_LOAD_OPENCL(release_program, "clReleaseProgram")
        MAGIC_GEO_LOAD_OPENCL(create_kernel, "clCreateKernel")
        MAGIC_GEO_LOAD_OPENCL(release_kernel, "clReleaseKernel")
        MAGIC_GEO_LOAD_OPENCL(create_buffer, "clCreateBuffer")
        MAGIC_GEO_LOAD_OPENCL(release_mem_object, "clReleaseMemObject")
        MAGIC_GEO_LOAD_OPENCL(set_kernel_arg, "clSetKernelArg")
        MAGIC_GEO_LOAD_OPENCL(enqueue_write_buffer, "clEnqueueWriteBuffer")
        MAGIC_GEO_LOAD_OPENCL(enqueue_read_buffer, "clEnqueueReadBuffer")
        MAGIC_GEO_LOAD_OPENCL(enqueue_ndrange_kernel, "clEnqueueNDRangeKernel")
        MAGIC_GEO_LOAD_OPENCL(get_kernel_work_group_info, "clGetKernelWorkGroupInfo")
#undef MAGIC_GEO_LOAD_OPENCL
        return api;
    }
};

std::string opencl_error(const char* operation, cl_int code) {
    return std::string(operation) + " failed with OpenCL error " + std::to_string(code);
}

void require_success(cl_int code, const char* operation) {
    if (code != CL_SUCCESS) {
        throw std::runtime_error(opencl_error(operation, code));
    }
}

std::string platform_string(OpenClApi& api, cl_platform_id platform, cl_platform_info key) {
    std::size_t size = 0;
    if (api.get_platform_info(platform, key, 0, nullptr, &size) != CL_SUCCESS || size == 0) {
        return {};
    }
    std::string value(size, '\0');
    if (api.get_platform_info(platform, key, size, value.data(), nullptr) != CL_SUCCESS) {
        return {};
    }
    while (!value.empty() && value.back() == '\0') {
        value.pop_back();
    }
    return value;
}

std::string device_string(OpenClApi& api, cl_device_id device, cl_device_info key) {
    std::size_t size = 0;
    if (api.get_device_info(device, key, 0, nullptr, &size) != CL_SUCCESS || size == 0) {
        return {};
    }
    std::string value(size, '\0');
    if (api.get_device_info(device, key, size, value.data(), nullptr) != CL_SUCCESS) {
        return {};
    }
    while (!value.empty() && value.back() == '\0') {
        value.pop_back();
    }
    return value;
}

template <typename T>
T device_value(OpenClApi& api, cl_device_id device, cl_device_info key, T fallback = T{}) {
    T value = fallback;
    if (api.get_device_info(device, key, sizeof(T), &value, nullptr) != CL_SUCCESS) {
        return fallback;
    }
    return value;
}

struct DeviceRecord {
    cl_platform_id platform = nullptr;
    cl_device_id device = nullptr;
    cl_device_type type = 0;
    bool available = false;
    bool compiler_available = false;
    bool fp64_supported = false;
    bool fp64_denorm = false;
    bool fp64_inf_nan = false;
    bool fp64_round_to_nearest = false;
    bool endian_little = false;
    bool endian_matches_host = false;
    bool opencl_c_12_supported = false;
    cl_device_fp_config double_fp_config = 0;
    cl_uint compute_units = 0;
    cl_uint address_bits = 0;
    cl_uint max_work_item_dimensions = 0;
    std::size_t max_work_item_size_0 = 0;
    std::size_t max_work_group_size = 0;
    cl_ulong global_memory_bytes = 0;
    cl_ulong max_allocation_bytes = 0;
    std::string platform_name;
    std::string platform_vendor;
    std::string platform_version;
    std::string name;
    std::string vendor;
    std::string driver_version;
    std::string device_version;
    std::string opencl_c_version;
    std::string extensions;

    bool qualifies() const {
        return available && compiler_available && fp64_supported && fp64_denorm &&
            fp64_inf_nan && fp64_round_to_nearest && endian_matches_host &&
            opencl_c_12_supported && address_bits >= 64 &&
            max_work_group_size > 0 && max_work_item_size_0 > 0 &&
            max_allocation_bytes > 0;
    }
};

bool host_is_little_endian() {
    const std::uint16_t value = 1;
    return *reinterpret_cast<const std::uint8_t*>(&value) == 1;
}

bool supports_opencl_c_12(const std::string& version) {
    const std::size_t marker = version.find("OpenCL C ");
    if (marker == std::string::npos) {
        return false;
    }
    std::istringstream parser(version.substr(marker + 9));
    int major = 0;
    int minor = 0;
    char dot = '\0';
    parser >> major >> dot >> minor;
    return parser && dot == '.' && (major > 1 || (major == 1 && minor >= 2));
}

struct Discovery {
    std::unique_ptr<OpenClApi> api;
    bool loader_found = false;
    bool probe_ok = false;
    cl_uint platform_count = 0;
    cl_uint gpu_device_count = 0;
    cl_uint cpu_device_count = 0;
    cl_uint accelerator_device_count = 0;
    cl_uint fp64_device_count = 0;
    cl_uint qualifying_device_count = 0;
    cl_uint qualifying_gpu_device_count = 0;
    std::string error;
    std::vector<DeviceRecord> devices;
};

Discovery discover_opencl() {
    Discovery result;
    result.api = OpenClApi::load(result.loader_found, result.error);
    if (!result.api) {
        return result;
    }

    cl_uint platform_count = 0;
    cl_int rc = result.api->get_platform_ids(0, nullptr, &platform_count);
    if (rc != CL_SUCCESS) {
        result.error = opencl_error("clGetPlatformIDs", rc);
        return result;
    }
    result.platform_count = platform_count;
    if (platform_count == 0) {
        result.error = "OpenCL loader is present but no platforms were reported";
        return result;
    }

    std::vector<cl_platform_id> platforms(platform_count);
    rc = result.api->get_platform_ids(platform_count, platforms.data(), nullptr);
    if (rc != CL_SUCCESS) {
        result.error = opencl_error("clGetPlatformIDs platform fetch", rc);
        return result;
    }

    bool unexpected_device_error = false;
    for (cl_platform_id platform : platforms) {
        cl_uint device_count = 0;
        rc = result.api->get_device_ids(platform, CL_DEVICE_TYPE_ALL, 0, nullptr, &device_count);
        if (rc == CL_DEVICE_NOT_FOUND) {
            continue;
        }
        if (rc != CL_SUCCESS) {
            unexpected_device_error = true;
            if (result.error.empty()) {
                result.error = opencl_error("clGetDeviceIDs", rc);
            }
            continue;
        }
        if (device_count == 0) {
            continue;
        }
        std::vector<cl_device_id> devices(device_count);
        rc = result.api->get_device_ids(
            platform, CL_DEVICE_TYPE_ALL, device_count, devices.data(), nullptr
        );
        if (rc != CL_SUCCESS) {
            unexpected_device_error = true;
            if (result.error.empty()) {
                result.error = opencl_error("clGetDeviceIDs device fetch", rc);
            }
            continue;
        }
        for (cl_device_id device : devices) {
            DeviceRecord record;
            record.platform = platform;
            record.device = device;
            record.type = device_value<cl_device_type>(*result.api, device, CL_DEVICE_TYPE);
            record.available = device_value<cl_bool>(*result.api, device, CL_DEVICE_AVAILABLE) != 0;
            record.compiler_available =
                device_value<cl_bool>(*result.api, device, CL_DEVICE_COMPILER_AVAILABLE) != 0;
            record.double_fp_config = device_value<cl_device_fp_config>(
                *result.api, device, CL_DEVICE_DOUBLE_FP_CONFIG
            );
            record.fp64_supported = record.double_fp_config != 0;
            record.fp64_denorm =
                (record.double_fp_config & CL_FP_DENORM) != 0;
            record.fp64_inf_nan =
                (record.double_fp_config & CL_FP_INF_NAN) != 0;
            record.fp64_round_to_nearest =
                (record.double_fp_config & CL_FP_ROUND_TO_NEAREST) != 0;
            record.endian_little = device_value<cl_bool>(
                *result.api, device, CL_DEVICE_ENDIAN_LITTLE
            ) != 0;
            record.endian_matches_host =
                record.endian_little == host_is_little_endian();
            record.compute_units = device_value<cl_uint>(
                *result.api, device, CL_DEVICE_MAX_COMPUTE_UNITS
            );
            record.address_bits = device_value<cl_uint>(
                *result.api, device, CL_DEVICE_ADDRESS_BITS
            );
            record.max_work_item_dimensions = device_value<cl_uint>(
                *result.api, device, CL_DEVICE_MAX_WORK_ITEM_DIMENSIONS
            );
            if (record.max_work_item_dimensions > 0 &&
                record.max_work_item_dimensions <= 16) {
                std::vector<std::size_t> work_item_sizes(
                    record.max_work_item_dimensions, 0
                );
                if (result.api->get_device_info(
                        device,
                        CL_DEVICE_MAX_WORK_ITEM_SIZES,
                        work_item_sizes.size() * sizeof(std::size_t),
                        work_item_sizes.data(),
                        nullptr
                    ) == CL_SUCCESS) {
                    record.max_work_item_size_0 = work_item_sizes.front();
                }
            }
            record.max_work_group_size = device_value<std::size_t>(
                *result.api, device, CL_DEVICE_MAX_WORK_GROUP_SIZE
            );
            record.global_memory_bytes = device_value<cl_ulong>(
                *result.api, device, CL_DEVICE_GLOBAL_MEM_SIZE
            );
            record.max_allocation_bytes = device_value<cl_ulong>(
                *result.api, device, CL_DEVICE_MAX_MEM_ALLOC_SIZE
            );
            record.platform_name = platform_string(*result.api, platform, CL_PLATFORM_NAME);
            record.platform_vendor = platform_string(*result.api, platform, CL_PLATFORM_VENDOR);
            record.platform_version = platform_string(*result.api, platform, CL_PLATFORM_VERSION);
            record.name = device_string(*result.api, device, CL_DEVICE_NAME);
            record.vendor = device_string(*result.api, device, CL_DEVICE_VENDOR);
            record.driver_version = device_string(*result.api, device, CL_DRIVER_VERSION);
            record.device_version = device_string(*result.api, device, CL_DEVICE_VERSION);
            record.opencl_c_version = device_string(*result.api, device, CL_DEVICE_OPENCL_C_VERSION);
            record.opencl_c_12_supported = supports_opencl_c_12(record.opencl_c_version);
            record.extensions = device_string(*result.api, device, CL_DEVICE_EXTENSIONS);

            result.gpu_device_count += (record.type & CL_DEVICE_TYPE_GPU) != 0 ? 1U : 0U;
            result.cpu_device_count += (record.type & CL_DEVICE_TYPE_CPU) != 0 ? 1U : 0U;
            result.accelerator_device_count +=
                (record.type & CL_DEVICE_TYPE_ACCELERATOR) != 0 ? 1U : 0U;
            result.fp64_device_count += record.fp64_supported ? 1U : 0U;
            result.qualifying_device_count += record.qualifies() ? 1U : 0U;
            result.qualifying_gpu_device_count +=
                record.qualifies() && (record.type & CL_DEVICE_TYPE_GPU) != 0 ? 1U : 0U;
            result.devices.push_back(std::move(record));
        }
    }
    result.probe_ok = !unexpected_device_error;
    if (result.devices.empty() && result.error.empty()) {
        result.error = "OpenCL platforms reported no devices";
    } else if (result.qualifying_device_count == 0 && result.error.empty()) {
        result.error =
            "no available compiler-capable 64-bit-address OpenCL device supports "
            "the required IEEE FP64 behavior";
    }
    return result;
}

int device_score(const DeviceRecord& device, bool prefer_gpu) {
    int score = static_cast<int>(std::min<cl_uint>(device.compute_units, 1000U));
    if ((device.type & CL_DEVICE_TYPE_GPU) != 0) {
        score += prefer_gpu ? 10000 : 3000;
    } else if ((device.type & CL_DEVICE_TYPE_ACCELERATOR) != 0) {
        score += 2000;
    } else if ((device.type & CL_DEVICE_TYPE_CPU) != 0) {
        score += 1000;
    }
    return score;
}

const char* device_type_name(cl_device_type type) {
    if ((type & CL_DEVICE_TYPE_GPU) != 0) {
        return "gpu";
    }
    if ((type & CL_DEVICE_TYPE_ACCELERATOR) != 0) {
        return "accelerator";
    }
    if ((type & CL_DEVICE_TYPE_CPU) != 0) {
        return "cpu";
    }
    return "other";
}

const char* requested_backend_name(int backend) {
    switch (backend) {
        case 0: return "auto";
        case 1: return "cpu";
        case 2: return "opencl";
        case 3: return "cuda";
        default: return "invalid";
    }
}

std::string clean_build_log(std::string value) {
    for (char& ch : value) {
        if (ch == '\n' || ch == '\r' || ch == '\t') {
            ch = ' ';
        }
    }
    if (value.size() > 4000) {
        value.resize(4000);
        value += "...";
    }
    return value;
}

constexpr const char* OPENCL_KERNEL_SOURCE = R"CLC(
#if defined(cl_khr_fp64)
#pragma OPENCL EXTENSION cl_khr_fp64 : enable
#elif defined(cl_amd_fp64)
#pragma OPENCL EXTENSION cl_amd_fp64 : enable
#endif
#pragma OPENCL FP_CONTRACT OFF

__kernel void assign_plates(
    __global const double4* positions,
    __global const double4* centers,
    const int center_count,
    const int cell_count,
    __global int* plate_ids
) {
    const int cell_id = (int)get_global_id(0);
    if (cell_id >= cell_count) {
        return;
    }
    const double4 position = positions[cell_id];
    double best = -2.0;
    int best_plate = 0;
    for (int plate_id = 0; plate_id < center_count; ++plate_id) {
        const double4 center = centers[plate_id];
        const double score =
            position.x * center.x + position.y * center.y + position.z * center.z;
        if (score > best) {
            best = score;
            best_plate = plate_id;
        }
    }
    plate_ids[cell_id] = best_plate;
}

__kernel void smooth_neighbor_field(
    __global const int* neighbor_offsets,
    __global const int* neighbor_ids,
    __global const double* current,
    __global double* next,
    const int cell_count,
    const double self_weight
) {
    const int cell_id = (int)get_global_id(0);
    if (cell_id >= cell_count) {
        return;
    }
    const int begin = neighbor_offsets[cell_id];
    const int end = neighbor_offsets[cell_id + 1];
    double sum = 0.0;
    for (int position = begin; position < end; ++position) {
        sum += current[neighbor_ids[position]];
    }
    const double average = end == begin
        ? current[cell_id]
        : sum / (double)(end - begin);
    next[cell_id] =
        self_weight * current[cell_id] + (1.0 - self_weight) * average;
}

__kernel void smooth_three_neighbor_fields(
    __global const int* neighbor_offsets,
    __global const int* neighbor_ids,
    __global const double* current,
    __global double* next,
    const int cell_count,
    const double self_weight_a,
    const double self_weight_b,
    const double self_weight_c
) {
    const int cell_id = (int)get_global_id(0);
    if (cell_id >= cell_count) {
        return;
    }
    const int begin = neighbor_offsets[cell_id];
    const int end = neighbor_offsets[cell_id + 1];
    double sum_a = 0.0;
    double sum_b = 0.0;
    double sum_c = 0.0;
    for (int position = begin; position < end; ++position) {
        const int neighbor_id = neighbor_ids[position];
        sum_a += current[neighbor_id];
        sum_b += current[cell_count + neighbor_id];
        sum_c += current[2 * cell_count + neighbor_id];
    }
    const int degree = end - begin;
    const double average_a = degree == 0
        ? current[cell_id]
        : sum_a / (double)degree;
    const double average_b = degree == 0
        ? current[cell_count + cell_id]
        : sum_b / (double)degree;
    const double average_c = degree == 0
        ? current[2 * cell_count + cell_id]
        : sum_c / (double)degree;
    next[cell_id] =
        self_weight_a * current[cell_id] +
        (1.0 - self_weight_a) * average_a;
    next[cell_count + cell_id] =
        self_weight_b * current[cell_count + cell_id] +
        (1.0 - self_weight_b) * average_b;
    next[2 * cell_count + cell_id] =
        self_weight_c * current[2 * cell_count + cell_id] +
        (1.0 - self_weight_c) * average_c;
}

__kernel void reduce_crust_overlap_continuous_shadow(
    __global const int* destination_offsets,
    __global const int* source_cell_ids,
    __global const double* overlap_area_km2,
    __global const double* destination_area_km2,
    __global const double* source_state,
    const int cell_count,
    __global double* output
) {
    const size_t destination = get_global_id(0);
    const size_t stride = (size_t)cell_count;
    if (destination >= stride) {
        return;
    }
    double volume = 0.0;
    double density_volume = 0.0;
    double age_moment = 0.0;
    const int begin = destination_offsets[destination];
    const int end = destination_offsets[destination + 1];
    for (int edge = begin; edge < end; ++edge) {
        const int source = source_cell_ids[edge];
        const double edge_volume =
            overlap_area_km2[edge] * source_state[source];
        volume = volume + edge_volume;
        density_volume = density_volume +
            edge_volume * source_state[stride + (size_t)source];
        age_moment = age_moment +
            edge_volume * source_state[2 * stride + (size_t)source];
    }
    output[destination] = volume;
    output[stride + destination] = density_volume;
    output[2 * stride + destination] = age_moment;
    output[3 * stride + destination] = volume > 0.0
        ? volume / destination_area_km2[destination]
        : 0.0;
    output[4 * stride + destination] = volume > 0.0
        ? density_volume / volume
        : source_state[stride + destination];
    output[5 * stride + destination] = volume > 0.0
        ? age_moment / volume
        : 0.0;
}

__kernel void remap_crust_sources(
    __global const double4* mesh_positions,
    __global const double4* backtraced_positions,
    __global const int* current_plate_ids,
    __global const int* candidate_offsets,
    __global const int* candidate_ids,
    const int plate_count,
    const int cell_count,
    __global int* source_cell_ids
) {
    const int cell_id = (int)get_global_id(0);
    if (cell_id >= cell_count) {
        return;
    }
    const int plate_id = current_plate_ids[cell_id];
    if (plate_id < 0 || plate_id >= plate_count) {
        source_cell_ids[cell_id] = -1;
        return;
    }
    const double4 query = backtraced_positions[cell_id];
    const int begin = candidate_offsets[plate_id];
    const int end = candidate_offsets[plate_id + 1];
    int best_source = cell_id;
    double best_score = -2.0;
    for (int position = begin; position < end; ++position) {
        const int candidate = candidate_ids[position];
        const double4 source = mesh_positions[candidate];
        const double score =
            query.x * source.x + query.y * source.y + query.z * source.z;
        if (score > best_score) {
            best_score = score;
            best_source = candidate;
        }
    }
    source_cell_ids[cell_id] = best_source;
}
)CLC";

std::string json_escape_local(const std::string& value) {
    static constexpr char HEX[] = "0123456789abcdef";
    std::string output;
    output.reserve(value.size() + 8);
    for (unsigned char ch : value) {
        switch (ch) {
            case '"': output += "\\\""; break;
            case '\\': output += "\\\\"; break;
            case '\b': output += "\\b"; break;
            case '\f': output += "\\f"; break;
            case '\n': output += "\\n"; break;
            case '\r': output += "\\r"; break;
            case '\t': output += "\\t"; break;
            default:
                if (ch < 0x20U) {
                    output += "\\u00";
                    output += HEX[(ch >> 4U) & 0x0FU];
                    output += HEX[ch & 0x0FU];
                } else {
                    output += static_cast<char>(ch);
                }
                break;
        }
    }
    return output;
}

void json_separator(std::string& output, bool& first) {
    if (!first) {
        output += ',';
    }
    first = false;
}

void json_string(std::string& output, bool& first, const char* key, const std::string& value) {
    json_separator(output, first);
    output += '"';
    output += key;
    output += "\":\"";
    output += json_escape_local(value);
    output += '"';
}

void json_bool(std::string& output, bool& first, const char* key, bool value) {
    json_separator(output, first);
    output += '"';
    output += key;
    output += "\":";
    output += value ? "true" : "false";
}

template <typename T>
void json_integer(std::string& output, bool& first, const char* key, T value) {
    json_separator(output, first);
    output += '"';
    output += key;
    output += "\":";
    output += std::to_string(value);
}

void json_number(std::string& output, bool& first, const char* key, double value) {
    json_separator(output, first);
    output += '"';
    output += key;
    output += "\":";
    std::ostringstream encoded;
    encoded << std::setprecision(9) << value;
    output += encoded.str();
}

void merge_crust_overlap_shadow_validation_maxima(
    CrustOverlapContinuousShadowValidation& maxima,
    const CrustOverlapContinuousShadowValidation& value
) {
    maxima.maximum_crust_volume_error_km3 = std::max(
        maxima.maximum_crust_volume_error_km3,
        value.maximum_crust_volume_error_km3
    );
    maxima.maximum_crust_volume_error_bound_km3 = std::max(
        maxima.maximum_crust_volume_error_bound_km3,
        value.maximum_crust_volume_error_bound_km3
    );
    maxima.maximum_density_weighted_volume_error = std::max(
        maxima.maximum_density_weighted_volume_error,
        value.maximum_density_weighted_volume_error
    );
    maxima.maximum_density_weighted_volume_error_bound = std::max(
        maxima.maximum_density_weighted_volume_error_bound,
        value.maximum_density_weighted_volume_error_bound
    );
    maxima.maximum_crust_age_volume_moment_error = std::max(
        maxima.maximum_crust_age_volume_moment_error,
        value.maximum_crust_age_volume_moment_error
    );
    maxima.maximum_crust_age_volume_moment_error_bound = std::max(
        maxima.maximum_crust_age_volume_moment_error_bound,
        value.maximum_crust_age_volume_moment_error_bound
    );
    maxima.maximum_remapped_thickness_error_km = std::max(
        maxima.maximum_remapped_thickness_error_km,
        value.maximum_remapped_thickness_error_km
    );
    maxima.maximum_remapped_thickness_error_bound_km = std::max(
        maxima.maximum_remapped_thickness_error_bound_km,
        value.maximum_remapped_thickness_error_bound_km
    );
    maxima.maximum_remapped_density_error = std::max(
        maxima.maximum_remapped_density_error,
        value.maximum_remapped_density_error
    );
    maxima.maximum_remapped_density_error_bound = std::max(
        maxima.maximum_remapped_density_error_bound,
        value.maximum_remapped_density_error_bound
    );
    maxima.maximum_remapped_age_error_ma = std::max(
        maxima.maximum_remapped_age_error_ma,
        value.maximum_remapped_age_error_ma
    );
    maxima.maximum_remapped_age_error_bound_ma = std::max(
        maxima.maximum_remapped_age_error_bound_ma,
        value.maximum_remapped_age_error_bound_ma
    );
    maxima.maximum_error_to_bound_ratio = std::max(
        maxima.maximum_error_to_bound_ratio,
        value.maximum_error_to_bound_ratio
    );
}

struct alignas(32) PackedVec4 {
    double x;
    double y;
    double z;
    double w;
};
static_assert(sizeof(PackedVec4) == 32);

thread_local ComputeSession::Impl* active_compute_session = nullptr;

}  // namespace

struct ComputeSession::Impl {
    Impl(
        const Params&,
        const ComputeOptions& compute_options,
        bool capability_only = false
    )
        : requested_backend(compute_options.compute_backend),
          prefer_gpu(compute_options.opencl_prefer_gpu) {
        if (!capability_only && requested_backend == 1) {
            selected_backend = "cpu";
            selection_reason =
                "CPU backend explicitly requested; CUDA/OpenCL probes skipped";
            return;
        }
        if (!capability_only && requested_backend == 0) {
            auto_selection_pending = true;
            selection_reason =
                "automatic accelerator selection is deferred until the actual mesh size is known";
            return;
        }

        if (capability_only || requested_backend == 3) {
            initialize_cuda_probe(requested_backend == 3 && !capability_only);
            if (!capability_only && requested_backend == 3) {
                if (!cuda_session || !cuda_session->available()) {
                    const std::string reason = cuda_status().error.empty()
                        ? "no usable NVIDIA CUDA device is available"
                        : cuda_status().error;
                    throw std::runtime_error(
                        "explicit CUDA backend requested but initialization failed: " + reason
                    );
                }
                selected_backend = "cuda";
                initial_selected_backend = "cuda";
                selection_reason = cuda_status().sm_120_optimized
                    ? "native CUDA selected for an NVIDIA sm_120 device"
                    : "highest-scoring FP64 NVIDIA CUDA device";
                return;
            }
        }

        probe_opencl();
        if (capability_only) {
            selected_backend = "cpu";
            selection_reason = "capability-only probe; no generation is active";
            return;
        }
        select_opencl_or_fallback(true);
    }

    ~Impl() {
        release_runtime();
    }

    const CudaTelemetry& cuda_status() const {
        return cuda_session ? cuda_session->telemetry() : cuda_probe;
    }

    void initialize_cuda_probe(bool create_session) {
        cuda_probe_performed = true;
        if (create_session) {
            cuda_session = std::make_unique<CudaComputeSession>();
            cuda_probe = cuda_session->telemetry();
        } else {
            cuda_probe = CudaComputeSession::probe();
        }
        if (cuda_status().available) {
            cuda_auto_min_cell_count = cuda_status().sm_120_optimized
                ? CUDA_SM_120_AUTO_MIN_CELL_COUNT
                : CUDA_UNCALIBRATED_AUTO_MIN_CELL_COUNT;
        }
    }

    void probe_opencl() {
        if (probe_performed) {
            return;
        }
        probe_performed = true;
        Discovery discovery = discover_opencl();
        api = std::move(discovery.api);
        loader_found = discovery.loader_found;
        probe_ok = discovery.probe_ok;
        platform_count = discovery.platform_count;
        gpu_device_count = discovery.gpu_device_count;
        cpu_device_count = discovery.cpu_device_count;
        accelerator_device_count = discovery.accelerator_device_count;
        fp64_device_count = discovery.fp64_device_count;
        qualifying_device_count = discovery.qualifying_device_count;
        qualifying_gpu_device_count = discovery.qualifying_gpu_device_count;
        probe_error = std::move(discovery.error);
        devices = std::move(discovery.devices);
    }

    bool select_opencl_or_fallback(bool explicit_request) {
        probe_opencl();
        selected_device_index = choose_device_for_records();
        if (selected_device_index < 0) {
            std::string reason;
            if (requested_backend == 0 && prefer_gpu &&
                qualifying_gpu_device_count == 0) {
                reason = "automatic GPU preference found no qualifying GPU OpenCL device";
            } else if (requested_backend == 0 && qualifying_device_count > 0) {
                reason =
                    "automatic OpenCL selection found no qualifying non-CPU device";
            } else {
                reason = probe_error.empty()
                    ? "no qualifying FP64 OpenCL device is available"
                    : probe_error;
            }
            if (explicit_request) {
                throw std::runtime_error(
                    "explicit OpenCL backend requested but initialization failed: " + reason
                );
            }
            selected_backend = "cpu";
            fallback_used = true;
            fallback_stage = "device_selection";
            fallback_reason = reason;
            selection_reason = "automatic OpenCL selection fell back to CPU";
            return false;
        }

        selected_backend = "opencl";
        initial_selected_backend = "opencl";
        selection_reason = prefer_gpu
            ? "highest-scoring qualifying GPU-preferred FP64 device"
            : (requested_backend == 0
                ? "highest-scoring qualifying non-CPU FP64 device"
                : "highest-scoring qualifying FP64 device");
        try {
            initialize_runtime();
        } catch (const std::exception& error) {
            if (explicit_request) {
                release_runtime();
                throw std::runtime_error(
                    std::string("explicit OpenCL backend requested but initialization failed: ") +
                    error.what()
                );
            }
            fall_back_to_cpu("runtime_initialization", error.what());
            return false;
        }
        return true;
    }

    void ensure_auto_backend(std::size_t actual_cell_count) {
        if (requested_backend != 0 || !auto_selection_pending) {
            return;
        }
        auto_selection_pending = false;
        auto_planning_cell_count = actual_cell_count;
        bool cuda_probe_eligible = false;
#ifdef MAGIC_GEO_HAS_CUDA
        cuda_probe_eligible = actual_cell_count >=
            static_cast<std::size_t>(CUDA_SM_120_AUTO_MIN_CELL_COUNT);
#endif
        cuda_auto_offload_eligible = false;
        auto_offload_eligible =
            actual_cell_count >= static_cast<std::size_t>(OPENCL_AUTO_MIN_CELL_COUNT);

        if (!cuda_probe_eligible && !auto_offload_eligible) {
            selected_backend = "cpu";
            selection_reason =
                "automatic acceleration is below the evidence-based actual-mesh thresholds; "
                "CUDA/OpenCL probes skipped";
            return;
        }

        std::string cuda_reason;
        bool cuda_below_policy_threshold = false;
        if (cuda_probe_eligible) {
            initialize_cuda_probe(true);
            if (cuda_session && cuda_session->available()) {
                cuda_auto_min_cell_count = cuda_status().sm_120_optimized
                    ? CUDA_SM_120_AUTO_MIN_CELL_COUNT
                    : CUDA_UNCALIBRATED_AUTO_MIN_CELL_COUNT;
                cuda_auto_offload_eligible = actual_cell_count >=
                    static_cast<std::size_t>(cuda_auto_min_cell_count);
                if (cuda_auto_offload_eligible) {
                    selected_backend = "cuda";
                    initial_selected_backend = "cuda";
                    selection_reason = cuda_status().sm_120_optimized
                        ? "automatic selection chose native CUDA for an NVIDIA sm_120 device"
                        : "automatic selection chose an uncalibrated FP64 NVIDIA CUDA device at the conservative threshold";
                    return;
                }
                cuda_reason =
                    "the detected non-sm_120 CUDA device is below its conservative " +
                    std::to_string(CUDA_UNCALIBRATED_AUTO_MIN_CELL_COUNT) +
                    "-cell automatic threshold";
                cuda_below_policy_threshold = true;
            } else {
                cuda_reason = cuda_status().error.empty()
                    ? "no usable NVIDIA CUDA device is available"
                    : cuda_status().error;
            }
            cuda_session.reset();
        }

        if (cuda_below_policy_threshold && !auto_offload_eligible) {
            selected_backend = "cpu";
            selection_reason =
                "automatic CUDA probe found an uncalibrated device below its "
                "conservative actual-mesh threshold; CPU retained by policy";
            return;
        }

        std::string opencl_reason;
        if (auto_offload_eligible) {
            if (select_opencl_or_fallback(false)) {
                if (!cuda_reason.empty()) {
                    selection_reason =
                        "automatic CUDA selection was unavailable (" + cuda_reason +
                        "); selected qualifying OpenCL device";
                }
                return;
            }
            opencl_reason = fallback_reason;
            if (fallback_stage == "runtime_initialization") {
                if (!cuda_reason.empty()) {
                    fallback_reason =
                        "CUDA: " + cuda_reason + "; OpenCL: " + fallback_reason;
                }
                selection_reason =
                    "automatic accelerator initialization fell back to CPU";
                return;
            }
        }

        selected_backend = "cpu";
        fallback_used = true;
        fallback_stage = "device_selection";
        if (!cuda_reason.empty() && !opencl_reason.empty()) {
            fallback_reason = "CUDA: " + cuda_reason + "; OpenCL: " + opencl_reason;
        } else if (!cuda_reason.empty()) {
            fallback_reason = "CUDA: " + cuda_reason;
        } else if (!opencl_reason.empty()) {
            fallback_reason = "OpenCL: " + opencl_reason;
        } else {
            fallback_reason = "no qualifying accelerator is available";
        }
        selection_reason = "automatic accelerator selection fell back to CPU";
    }

    int choose_device_for_records() const {
        int best_index = -1;
        int best_score = std::numeric_limits<int>::min();
        for (std::size_t index = 0; index < devices.size(); ++index) {
            const DeviceRecord& device = devices[index];
            if (!device.qualifies()) {
                continue;
            }
            if (requested_backend == 0 &&
                (device.type & CL_DEVICE_TYPE_CPU) != 0) {
                continue;
            }
            if (requested_backend == 0 && prefer_gpu &&
                (device.type & CL_DEVICE_TYPE_GPU) == 0) {
                continue;
            }
            const int score = device_score(device, prefer_gpu);
            if (score > best_score) {
                best_score = score;
                best_index = static_cast<int>(index);
            }
        }
        return best_index;
    }

    const DeviceRecord* selected_device() const {
        if (selected_device_index < 0 ||
            selected_device_index >= static_cast<int>(devices.size())) {
            return nullptr;
        }
        return &devices[static_cast<std::size_t>(selected_device_index)];
    }

    void initialize_runtime() {
        if (!api) {
            throw std::runtime_error("OpenCL loader API is unavailable");
        }
        const DeviceRecord* device_record = selected_device();
        if (device_record == nullptr) {
            throw std::runtime_error("OpenCL device selection is invalid");
        }

        const cl_context_properties properties[] = {
            CL_CONTEXT_PLATFORM,
            reinterpret_cast<cl_context_properties>(device_record->platform),
            0,
        };
        const cl_device_id device = device_record->device;
        cl_int rc = CL_SUCCESS;
        context = api->create_context(properties, 1, &device, nullptr, nullptr, &rc);
        require_success(rc, "clCreateContext");
        if (context == nullptr) {
            throw std::runtime_error("clCreateContext returned a null context");
        }

        queue = api->create_command_queue(
            context, device, CL_QUEUE_PROFILING_ENABLE, &rc
        );
        require_success(rc, "clCreateCommandQueue");
        if (queue == nullptr) {
            throw std::runtime_error("clCreateCommandQueue returned a null queue");
        }

        const char* source = OPENCL_KERNEL_SOURCE;
        const std::size_t source_size = std::strlen(source);
        program = api->create_program_with_source(context, 1, &source, &source_size, &rc);
        require_success(rc, "clCreateProgramWithSource");
        if (program == nullptr) {
            throw std::runtime_error("clCreateProgramWithSource returned a null program");
        }
        constexpr const char* BUILD_OPTIONS = "-cl-std=CL1.2";
        rc = api->build_program(program, 1, &device, BUILD_OPTIONS, nullptr, nullptr);
        if (rc != CL_SUCCESS) {
            std::size_t log_size = 0;
            api->get_program_build_info(
                program, device, CL_PROGRAM_BUILD_LOG, 0, nullptr, &log_size
            );
            std::string log(log_size, '\0');
            if (log_size > 0) {
                api->get_program_build_info(
                    program, device, CL_PROGRAM_BUILD_LOG, log_size, log.data(), nullptr
                );
                while (!log.empty() && log.back() == '\0') {
                    log.pop_back();
                }
            }
            throw std::runtime_error(
                opencl_error("clBuildProgram", rc) + ": " + clean_build_log(log)
            );
        }
        program_built = true;
        program_ever_built = true;

        assign_kernel = api->create_kernel(program, "assign_plates", &rc);
        require_success(rc, "clCreateKernel(assign_plates)");
        smooth_kernel = api->create_kernel(program, "smooth_neighbor_field", &rc);
        require_success(rc, "clCreateKernel(smooth_neighbor_field)");
        smooth_three_kernel = api->create_kernel(
            program, "smooth_three_neighbor_fields", &rc
        );
        require_success(rc, "clCreateKernel(smooth_three_neighbor_fields)");
        overlap_shadow_kernel = api->create_kernel(
            program, "reduce_crust_overlap_continuous_shadow", &rc
        );
        require_success(
            rc, "clCreateKernel(reduce_crust_overlap_continuous_shadow)"
        );
        assign_local_work_size = choose_local_work_size(assign_kernel);
        smooth_local_work_size = choose_local_work_size(smooth_kernel);
        smooth_three_local_work_size = choose_local_work_size(smooth_three_kernel);
        overlap_shadow_local_work_size = choose_local_work_size(
            overlap_shadow_kernel
        );
        runtime_ready = true;
    }

    void ensure_legacy_remap_kernel() {
        if (remap_kernel != nullptr) {
            return;
        }
        cl_int rc = CL_SUCCESS;
        remap_kernel = api->create_kernel(program, "remap_crust_sources", &rc);
        require_success(rc, "clCreateKernel(remap_crust_sources legacy test hook)");
        if (remap_kernel == nullptr) {
            throw std::runtime_error(
                "clCreateKernel(remap_crust_sources legacy test hook) returned null"
            );
        }
        remap_local_work_size = choose_local_work_size(remap_kernel);
    }

    std::size_t choose_local_work_size(cl_kernel kernel) const {
        const DeviceRecord* record = selected_device();
        if (record == nullptr) {
            return 1;
        }
        std::size_t kernel_limit = record->max_work_group_size;
        if (api->get_kernel_work_group_info(
                kernel,
                record->device,
                CL_KERNEL_WORK_GROUP_SIZE,
                sizeof(kernel_limit),
                &kernel_limit,
                nullptr
            ) != CL_SUCCESS) {
            kernel_limit = record->max_work_group_size;
        }
        std::size_t preferred = 1;
        if (api->get_kernel_work_group_info(
                kernel,
                record->device,
                CL_KERNEL_PREFERRED_WORK_GROUP_SIZE_MULTIPLE,
                sizeof(preferred),
                &preferred,
                nullptr
            ) != CL_SUCCESS || preferred == 0) {
            preferred = 1;
        }
        std::size_t limit = std::min<std::size_t>(
            256,
            std::min(
                kernel_limit,
                std::min(record->max_work_group_size, record->max_work_item_size_0)
            )
        );
        if (limit == 0) {
            return 1;
        }
        if (preferred <= limit) {
            limit -= limit % preferred;
        }
        return std::max<std::size_t>(1, limit);
    }

    void release_mem(cl_mem& memory) {
        if (memory != nullptr && api) {
            api->release_mem_object(memory);
            memory = nullptr;
        }
    }

    void reset_mesh_buffers() {
        release_mem(position_buffer);
        release_mem(neighbor_offset_buffer);
        release_mem(neighbor_id_buffer);
        mesh_identity = nullptr;
        mesh_cell_count = 0;
        positions_ready = false;
        adjacency_ready = false;
    }

    void release_runtime() {
        reset_mesh_buffers();
        release_mem(center_buffer);
        release_mem(plate_id_buffer);
        release_mem(smooth_a_buffer);
        release_mem(smooth_b_buffer);
        release_mem(smooth_three_a_buffer);
        release_mem(smooth_three_b_buffer);
        release_mem(remap_query_buffer);
        release_mem(remap_plate_id_buffer);
        release_mem(remap_candidate_offset_buffer);
        release_mem(remap_candidate_id_buffer);
        release_mem(remap_source_id_buffer);
        release_mem(overlap_shadow_destination_offset_buffer);
        release_mem(overlap_shadow_source_id_buffer);
        release_mem(overlap_shadow_area_buffer);
        release_mem(overlap_shadow_destination_area_buffer);
        release_mem(overlap_shadow_source_state_buffer);
        release_mem(overlap_shadow_output_buffer);
        center_capacity = 0;
        plate_capacity = 0;
        smooth_capacity = 0;
        smooth_three_capacity = 0;
        remap_cell_capacity = 0;
        remap_plate_capacity = 0;
        remap_candidate_capacity = 0;
        overlap_shadow_cell_capacity = 0;
        overlap_shadow_edge_capacity = 0;
        if (assign_kernel != nullptr && api) {
            api->release_kernel(assign_kernel);
            assign_kernel = nullptr;
        }
        if (smooth_kernel != nullptr && api) {
            api->release_kernel(smooth_kernel);
            smooth_kernel = nullptr;
        }
        if (smooth_three_kernel != nullptr && api) {
            api->release_kernel(smooth_three_kernel);
            smooth_three_kernel = nullptr;
        }
        if (remap_kernel != nullptr && api) {
            api->release_kernel(remap_kernel);
            remap_kernel = nullptr;
        }
        if (overlap_shadow_kernel != nullptr && api) {
            api->release_kernel(overlap_shadow_kernel);
            overlap_shadow_kernel = nullptr;
        }
        if (program != nullptr && api) {
            api->release_program(program);
            program = nullptr;
        }
        if (queue != nullptr && api) {
            api->release_command_queue(queue);
            queue = nullptr;
        }
        if (context != nullptr && api) {
            api->release_context(context);
            context = nullptr;
        }
        runtime_ready = false;
        program_built = false;
    }

    void fall_back_to_cpu(const std::string& stage, const std::string& reason) {
        if (cuda_session) {
            cuda_probe = cuda_session->telemetry();
            cuda_session.reset();
            cuda_probe.allocated_device_bytes = 0;
        }
        release_runtime();
        selected_backend = "cpu";
        fallback_used = true;
        fallback_stage = stage;
        fallback_reason = reason;
    }

    void ensure_mesh_identity(const std::vector<Cell>& cells) {
        const Cell* identity = cells.empty() ? nullptr : cells.data();
        if (mesh_identity != identity || mesh_cell_count != cells.size()) {
            reset_mesh_buffers();
            mesh_identity = identity;
            mesh_cell_count = cells.size();
        }
    }

    cl_mem create_buffer(cl_mem_flags flags, std::size_t byte_count, const char* name) {
        if (byte_count == 0) {
            throw std::runtime_error(std::string(name) + " cannot have zero bytes");
        }
        const DeviceRecord* record = selected_device();
        if (record == nullptr) {
            throw std::runtime_error("OpenCL buffer allocation has no selected device");
        }
        if (byte_count > record->max_allocation_bytes) {
            throw std::runtime_error(
                std::string(name) + " exceeds CL_DEVICE_MAX_MEM_ALLOC_SIZE"
            );
        }
        cl_int rc = CL_SUCCESS;
        cl_mem result = api->create_buffer(context, flags, byte_count, nullptr, &rc);
        require_success(rc, name);
        if (result == nullptr) {
            throw std::runtime_error(std::string(name) + " returned a null buffer");
        }
        return result;
    }

    void write_buffer(cl_mem buffer, std::size_t bytes, const void* source) {
        require_success(
            api->enqueue_write_buffer(
                queue, buffer, CL_TRUE, 0, bytes, source, 0, nullptr, nullptr
            ),
            "clEnqueueWriteBuffer"
        );
        host_to_device_bytes += bytes;
    }

    void read_buffer(cl_mem buffer, std::size_t bytes, void* target) {
        require_success(
            api->enqueue_read_buffer(
                queue, buffer, CL_TRUE, 0, bytes, target, 0, nullptr, nullptr
            ),
            "clEnqueueReadBuffer"
        );
        device_to_host_bytes += bytes;
    }

    void ensure_positions(const std::vector<Cell>& cells) {
        ensure_mesh_identity(cells);
        if (positions_ready) {
            return;
        }
        std::vector<PackedVec4> packed(cells.size());
        for (std::size_t index = 0; index < cells.size(); ++index) {
            packed[index] = {cells[index].p.x, cells[index].p.y, cells[index].p.z, 0.0};
        }
        const std::size_t bytes = packed.size() * sizeof(PackedVec4);
        position_buffer = create_buffer(CL_MEM_READ_ONLY, bytes, "position buffer allocation");
        write_buffer(position_buffer, bytes, packed.data());
        positions_ready = true;
    }

    void ensure_adjacency(const std::vector<Cell>& cells) {
        ensure_mesh_identity(cells);
        if (adjacency_ready) {
            return;
        }
        if (cells.size() > static_cast<std::size_t>(std::numeric_limits<cl_int>::max())) {
            throw std::runtime_error("OpenCL mesh has too many cells for 32-bit kernel indices");
        }
        std::vector<cl_int> offsets(cells.size() + 1, 0);
        std::size_t edge_count = 0;
        for (std::size_t index = 0; index < cells.size(); ++index) {
            edge_count += cells[index].neighbors.size();
            if (edge_count > static_cast<std::size_t>(std::numeric_limits<cl_int>::max())) {
                throw std::runtime_error("OpenCL adjacency exceeds 32-bit kernel indices");
            }
            offsets[index + 1] = static_cast<cl_int>(edge_count);
        }
        std::vector<cl_int> neighbors;
        neighbors.reserve(edge_count);
        for (const Cell& cell : cells) {
            for (int neighbor : cell.neighbors) {
                if (neighbor < 0 || neighbor >= static_cast<int>(cells.size())) {
                    throw std::runtime_error("OpenCL adjacency contains an invalid cell id");
                }
                neighbors.push_back(static_cast<cl_int>(neighbor));
            }
        }
        const std::size_t offset_bytes = offsets.size() * sizeof(cl_int);
        const std::size_t neighbor_bytes = neighbors.size() * sizeof(cl_int);
        neighbor_offset_buffer = create_buffer(
            CL_MEM_READ_ONLY, offset_bytes, "neighbor offset buffer allocation"
        );
        neighbor_id_buffer = create_buffer(
            CL_MEM_READ_ONLY,
            std::max<std::size_t>(sizeof(cl_int), neighbor_bytes),
            "neighbor id buffer allocation"
        );
        write_buffer(neighbor_offset_buffer, offset_bytes, offsets.data());
        if (neighbor_bytes > 0) {
            write_buffer(neighbor_id_buffer, neighbor_bytes, neighbors.data());
        }
        adjacency_ready = true;
    }

    void ensure_plate_buffers(std::size_t center_count, std::size_t cell_count) {
        if (center_count > center_capacity) {
            release_mem(center_buffer);
            center_buffer = create_buffer(
                CL_MEM_READ_ONLY,
                center_count * sizeof(PackedVec4),
                "plate center buffer allocation"
            );
            center_capacity = center_count;
        }
        if (cell_count > plate_capacity) {
            release_mem(plate_id_buffer);
            plate_id_buffer = create_buffer(
                CL_MEM_READ_WRITE,
                cell_count * sizeof(cl_int),
                "plate id buffer allocation"
            );
            plate_capacity = cell_count;
        }
    }

    void ensure_smooth_buffers(std::size_t cell_count) {
        if (cell_count <= smooth_capacity) {
            return;
        }
        release_mem(smooth_a_buffer);
        release_mem(smooth_b_buffer);
        const std::size_t bytes = cell_count * sizeof(double);
        smooth_a_buffer = create_buffer(
            CL_MEM_READ_WRITE, bytes, "smoothing input buffer allocation"
        );
        smooth_b_buffer = create_buffer(
            CL_MEM_READ_WRITE, bytes, "smoothing output buffer allocation"
        );
        smooth_capacity = cell_count;
    }

    void ensure_smooth_three_buffers(std::size_t cell_count) {
        if (cell_count <= smooth_three_capacity) {
            return;
        }
        release_mem(smooth_three_a_buffer);
        release_mem(smooth_three_b_buffer);
        if (cell_count > std::numeric_limits<std::size_t>::max() / (3 * sizeof(double))) {
            throw std::runtime_error("batched smoothing buffer size overflow");
        }
        const std::size_t bytes = 3 * cell_count * sizeof(double);
        smooth_three_a_buffer = create_buffer(
            CL_MEM_READ_WRITE, bytes, "batched smoothing input buffer allocation"
        );
        smooth_three_b_buffer = create_buffer(
            CL_MEM_READ_WRITE, bytes, "batched smoothing output buffer allocation"
        );
        smooth_three_capacity = cell_count;
    }

    void ensure_remap_buffers(
        std::size_t cell_count,
        std::size_t plate_count,
        std::size_t candidate_count
    ) {
        if (cell_count > remap_cell_capacity) {
            release_mem(remap_query_buffer);
            release_mem(remap_plate_id_buffer);
            release_mem(remap_source_id_buffer);
            remap_query_buffer = create_buffer(
                CL_MEM_READ_ONLY,
                cell_count * sizeof(PackedVec4),
                "crust remap query buffer allocation"
            );
            remap_plate_id_buffer = create_buffer(
                CL_MEM_READ_ONLY,
                cell_count * sizeof(cl_int),
                "crust remap plate buffer allocation"
            );
            remap_source_id_buffer = create_buffer(
                CL_MEM_READ_WRITE,
                cell_count * sizeof(cl_int),
                "crust remap output buffer allocation"
            );
            remap_cell_capacity = cell_count;
        }
        if (plate_count + 1 > remap_plate_capacity) {
            release_mem(remap_candidate_offset_buffer);
            remap_candidate_offset_buffer = create_buffer(
                CL_MEM_READ_ONLY,
                (plate_count + 1) * sizeof(cl_int),
                "crust remap candidate-offset buffer allocation"
            );
            remap_plate_capacity = plate_count + 1;
        }
        if (candidate_count > remap_candidate_capacity) {
            release_mem(remap_candidate_id_buffer);
            remap_candidate_id_buffer = create_buffer(
                CL_MEM_READ_ONLY,
                candidate_count * sizeof(cl_int),
                "crust remap candidate-id buffer allocation"
            );
            remap_candidate_capacity = candidate_count;
        }
    }

    static std::size_t checked_opencl_bytes(
        std::size_t count,
        std::size_t element_size,
        const char* context
    ) {
        if (
            element_size != 0 &&
            count > std::numeric_limits<std::size_t>::max() / element_size
        ) {
            throw std::runtime_error(
                std::string(context) + " byte count overflow"
            );
        }
        return count * element_size;
    }

    void ensure_overlap_shadow_buffers(
        std::size_t cell_count,
        std::size_t edge_count
    ) {
        const std::size_t offset_bytes = checked_opencl_bytes(
            cell_count + 1, sizeof(cl_int),
            "OpenCL crust-overlap shadow destination offsets"
        );
        const std::size_t edge_id_bytes = checked_opencl_bytes(
            edge_count, sizeof(cl_int),
            "OpenCL crust-overlap shadow source ids"
        );
        const std::size_t edge_area_bytes = checked_opencl_bytes(
            edge_count, sizeof(double),
            "OpenCL crust-overlap shadow edge areas"
        );
        const std::size_t destination_area_bytes = checked_opencl_bytes(
            cell_count, sizeof(double),
            "OpenCL crust-overlap shadow destination areas"
        );
        const std::size_t source_state_bytes = checked_opencl_bytes(
            cell_count, 3U * sizeof(double),
            "OpenCL crust-overlap shadow source state"
        );
        const std::size_t output_bytes = checked_opencl_bytes(
            cell_count, 6U * sizeof(double),
            "OpenCL crust-overlap shadow output"
        );
        std::size_t required_bytes = 0;
        for (std::size_t bytes : {
                 offset_bytes,
                 edge_id_bytes,
                 edge_area_bytes,
                 destination_area_bytes,
                 source_state_bytes,
                 output_bytes,
             }) {
            if (bytes > std::numeric_limits<std::size_t>::max() - required_bytes) {
                throw std::runtime_error(
                    "OpenCL crust-overlap shadow aggregate allocation size overflow"
                );
            }
            required_bytes += bytes;
        }
        const DeviceRecord* record = selected_device();
        if (
            record == nullptr ||
            (record->global_memory_bytes != 0 &&
             required_bytes > record->global_memory_bytes)
        ) {
            throw std::runtime_error(
                "OpenCL crust-overlap shadow buffers exceed device global memory"
            );
        }

        if (cell_count > overlap_shadow_cell_capacity) {
            release_mem(overlap_shadow_destination_offset_buffer);
            release_mem(overlap_shadow_destination_area_buffer);
            release_mem(overlap_shadow_source_state_buffer);
            release_mem(overlap_shadow_output_buffer);
            overlap_shadow_destination_offset_buffer = create_buffer(
                CL_MEM_READ_ONLY,
                offset_bytes,
                "crust-overlap shadow destination-offset buffer allocation"
            );
            overlap_shadow_destination_area_buffer = create_buffer(
                CL_MEM_READ_ONLY,
                destination_area_bytes,
                "crust-overlap shadow destination-area buffer allocation"
            );
            overlap_shadow_source_state_buffer = create_buffer(
                CL_MEM_READ_ONLY,
                source_state_bytes,
                "crust-overlap shadow source-state buffer allocation"
            );
            overlap_shadow_output_buffer = create_buffer(
                CL_MEM_READ_WRITE,
                output_bytes,
                "crust-overlap shadow output buffer allocation"
            );
            overlap_shadow_cell_capacity = cell_count;
        }
        if (std::max<std::size_t>(1, edge_count) > overlap_shadow_edge_capacity) {
            release_mem(overlap_shadow_source_id_buffer);
            release_mem(overlap_shadow_area_buffer);
            const std::size_t allocated_edge_count = std::max<std::size_t>(
                1, edge_count
            );
            overlap_shadow_source_id_buffer = create_buffer(
                CL_MEM_READ_ONLY,
                checked_opencl_bytes(
                    allocated_edge_count,
                    sizeof(cl_int),
                    "OpenCL crust-overlap shadow source-id allocation"
                ),
                "crust-overlap shadow source-id buffer allocation"
            );
            overlap_shadow_area_buffer = create_buffer(
                CL_MEM_READ_ONLY,
                checked_opencl_bytes(
                    allocated_edge_count,
                    sizeof(double),
                    "OpenCL crust-overlap shadow edge-area allocation"
                ),
                "crust-overlap shadow edge-area buffer allocation"
            );
            overlap_shadow_edge_capacity = allocated_edge_count;
        }
    }

    static std::size_t rounded_global_size(std::size_t count, std::size_t local) {
        if (local == 0 || count > std::numeric_limits<std::size_t>::max() - (local - 1)) {
            throw std::runtime_error("OpenCL global work size overflow");
        }
        return ((count + local - 1) / local) * local;
    }

    void set_arg(cl_kernel kernel, cl_uint index, std::size_t size, const void* value) {
        require_success(api->set_kernel_arg(kernel, index, size, value), "clSetKernelArg");
    }

    void run_assign_plates(
        const std::vector<Vec3>& centers,
        const std::vector<Cell>& cells,
        std::vector<int>& plate_ids
    ) {
        if (!runtime_ready || selected_backend != "opencl") {
            throw std::runtime_error("OpenCL plate assignment runtime is not active");
        }
        if (centers.empty()) {
            throw std::runtime_error("OpenCL plate assignment requires at least one center");
        }
        if (centers.size() > static_cast<std::size_t>(std::numeric_limits<cl_int>::max()) ||
            cells.size() > static_cast<std::size_t>(std::numeric_limits<cl_int>::max())) {
            throw std::runtime_error("OpenCL plate assignment exceeds 32-bit kernel indices");
        }
        ensure_positions(cells);
        ensure_plate_buffers(centers.size(), cells.size());

        std::vector<PackedVec4> packed_centers(centers.size());
        for (std::size_t index = 0; index < centers.size(); ++index) {
            packed_centers[index] = {
                centers[index].x, centers[index].y, centers[index].z, 0.0
            };
        }
        write_buffer(
            center_buffer,
            packed_centers.size() * sizeof(PackedVec4),
            packed_centers.data()
        );

        const cl_int center_count = static_cast<cl_int>(centers.size());
        const cl_int cell_count = static_cast<cl_int>(cells.size());
        set_arg(assign_kernel, 0, sizeof(position_buffer), &position_buffer);
        set_arg(assign_kernel, 1, sizeof(center_buffer), &center_buffer);
        set_arg(assign_kernel, 2, sizeof(center_count), &center_count);
        set_arg(assign_kernel, 3, sizeof(cell_count), &cell_count);
        set_arg(assign_kernel, 4, sizeof(plate_id_buffer), &plate_id_buffer);

        const std::size_t global = rounded_global_size(
            cells.size(), assign_local_work_size
        );
        require_success(
            api->enqueue_ndrange_kernel(
                queue,
                assign_kernel,
                1,
                nullptr,
                &global,
                &assign_local_work_size,
                0,
                nullptr,
                nullptr
            ),
            "clEnqueueNDRangeKernel(assign_plates)"
        );
        std::vector<cl_int> gpu_ids(cells.size(), 0);
        read_buffer(
            plate_id_buffer,
            gpu_ids.size() * sizeof(cl_int),
            gpu_ids.data()
        );
        plate_ids.resize(gpu_ids.size());
        for (std::size_t index = 0; index < gpu_ids.size(); ++index) {
            if (gpu_ids[index] < 0 || gpu_ids[index] >= center_count) {
                throw std::runtime_error("OpenCL plate assignment returned an invalid plate id");
            }
            plate_ids[index] = static_cast<int>(gpu_ids[index]);
        }
        kernel_dispatch_count++;
        plate_assignment_dispatch_count++;
        last_global_work_size = global;
        last_local_work_size = assign_local_work_size;
    }

    void run_smooth_field(
        const std::vector<Cell>& cells,
        const std::vector<double>& input,
        int steps,
        double self_weight,
        std::vector<double>& output
    ) {
        if (!runtime_ready || selected_backend != "opencl") {
            throw std::runtime_error("OpenCL smoothing runtime is not active");
        }
        if (input.size() != cells.size()) {
            throw std::runtime_error("OpenCL smoothing input size does not match the mesh");
        }
        if (steps < 0 || !std::isfinite(self_weight)) {
            throw std::runtime_error("OpenCL smoothing parameters are invalid");
        }
        if (steps == 0) {
            output = input;
            return;
        }
        ensure_adjacency(cells);
        ensure_smooth_buffers(cells.size());
        const std::size_t bytes = input.size() * sizeof(double);
        write_buffer(smooth_a_buffer, bytes, input.data());

        cl_mem current = smooth_a_buffer;
        cl_mem next = smooth_b_buffer;
        const cl_int cell_count = static_cast<cl_int>(cells.size());
        const std::size_t global = rounded_global_size(
            cells.size(), smooth_local_work_size
        );
        for (int step = 0; step < steps; ++step) {
            set_arg(smooth_kernel, 0, sizeof(neighbor_offset_buffer), &neighbor_offset_buffer);
            set_arg(smooth_kernel, 1, sizeof(neighbor_id_buffer), &neighbor_id_buffer);
            set_arg(smooth_kernel, 2, sizeof(current), &current);
            set_arg(smooth_kernel, 3, sizeof(next), &next);
            set_arg(smooth_kernel, 4, sizeof(cell_count), &cell_count);
            set_arg(smooth_kernel, 5, sizeof(self_weight), &self_weight);
            require_success(
                api->enqueue_ndrange_kernel(
                    queue,
                    smooth_kernel,
                    1,
                    nullptr,
                    &global,
                    &smooth_local_work_size,
                    0,
                    nullptr,
                    nullptr
                ),
                "clEnqueueNDRangeKernel(smooth_neighbor_field)"
            );
            std::swap(current, next);
            kernel_dispatch_count++;
            smoothing_kernel_dispatch_count++;
        }
        output.assign(input.size(), 0.0);
        read_buffer(current, bytes, output.data());
        smoothing_operation_count++;
        last_global_work_size = global;
        last_local_work_size = smooth_local_work_size;
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
        if (!runtime_ready || selected_backend != "opencl") {
            throw std::runtime_error("OpenCL batched smoothing runtime is not active");
        }
        if (input_a.size() != cells.size() || input_b.size() != cells.size() ||
            input_c.size() != cells.size()) {
            throw std::runtime_error(
                "OpenCL batched smoothing inputs do not match the mesh"
            );
        }
        if (steps < 0 || !std::isfinite(self_weight_a) ||
            !std::isfinite(self_weight_b) || !std::isfinite(self_weight_c)) {
            throw std::runtime_error("OpenCL batched smoothing parameters are invalid");
        }
        if (steps == 0) {
            output_a = input_a;
            output_b = input_b;
            output_c = input_c;
            return;
        }
        ensure_adjacency(cells);
        ensure_smooth_three_buffers(cells.size());
        const std::size_t field_size = cells.size();
        std::vector<double> packed(3 * field_size, 0.0);
        std::copy(input_a.begin(), input_a.end(), packed.begin());
        std::copy(input_b.begin(), input_b.end(), packed.begin() + field_size);
        std::copy(input_c.begin(), input_c.end(), packed.begin() + 2 * field_size);
        const std::size_t bytes = packed.size() * sizeof(double);
        write_buffer(smooth_three_a_buffer, bytes, packed.data());

        cl_mem current = smooth_three_a_buffer;
        cl_mem next = smooth_three_b_buffer;
        const cl_int cell_count = static_cast<cl_int>(cells.size());
        const std::size_t global = rounded_global_size(
            cells.size(), smooth_three_local_work_size
        );
        for (int step = 0; step < steps; ++step) {
            set_arg(
                smooth_three_kernel,
                0,
                sizeof(neighbor_offset_buffer),
                &neighbor_offset_buffer
            );
            set_arg(
                smooth_three_kernel,
                1,
                sizeof(neighbor_id_buffer),
                &neighbor_id_buffer
            );
            set_arg(smooth_three_kernel, 2, sizeof(current), &current);
            set_arg(smooth_three_kernel, 3, sizeof(next), &next);
            set_arg(smooth_three_kernel, 4, sizeof(cell_count), &cell_count);
            set_arg(
                smooth_three_kernel, 5, sizeof(self_weight_a), &self_weight_a
            );
            set_arg(
                smooth_three_kernel, 6, sizeof(self_weight_b), &self_weight_b
            );
            set_arg(
                smooth_three_kernel, 7, sizeof(self_weight_c), &self_weight_c
            );
            require_success(
                api->enqueue_ndrange_kernel(
                    queue,
                    smooth_three_kernel,
                    1,
                    nullptr,
                    &global,
                    &smooth_three_local_work_size,
                    0,
                    nullptr,
                    nullptr
                ),
                "clEnqueueNDRangeKernel(smooth_three_neighbor_fields)"
            );
            std::swap(current, next);
            kernel_dispatch_count++;
            batched_smoothing_kernel_dispatch_count++;
        }
        read_buffer(current, bytes, packed.data());
        output_a.assign(packed.begin(), packed.begin() + field_size);
        output_b.assign(
            packed.begin() + field_size, packed.begin() + 2 * field_size
        );
        output_c.assign(packed.begin() + 2 * field_size, packed.end());
        batched_smoothing_operation_count++;
        last_global_work_size = global;
        last_local_work_size = smooth_three_local_work_size;
    }

    void run_crust_overlap_continuous_shadow(
        const CrustTransportPlan& transport,
        const std::vector<Cell>& cells,
        const std::vector<double>& source_crust_thickness_km,
        const std::vector<double>& source_crust_density,
        const std::vector<double>& source_crust_age_ma,
        CrustOverlapContinuousShadowResult& output
    ) {
        if (!runtime_ready || selected_backend != "opencl") {
            throw std::runtime_error(
                "OpenCL crust-overlap continuous shadow runtime is not active"
            );
        }
        validate_crust_overlap_continuous_shadow_input(
            transport,
            cells,
            source_crust_thickness_km,
            source_crust_density,
            source_crust_age_ma
        );
        if (cells.empty()) {
            output = {};
            return;
        }
        const std::size_t cell_count = cells.size();
        const std::size_t edge_count = transport.source_cell_ids.size();
        ensure_overlap_shadow_buffers(cell_count, edge_count);

        std::vector<cl_int> destination_offsets(
            transport.destination_offsets.begin(),
            transport.destination_offsets.end()
        );
        std::vector<cl_int> source_cell_ids(
            transport.source_cell_ids.begin(),
            transport.source_cell_ids.end()
        );
        std::vector<double> destination_area(cell_count);
        std::vector<double> source_state(3U * cell_count);
        for (std::size_t index = 0; index < cell_count; ++index) {
            destination_area[index] = cells[index].area_km2;
            source_state[index] = source_crust_thickness_km[index];
            source_state[cell_count + index] = source_crust_density[index];
            source_state[2U * cell_count + index] = source_crust_age_ma[index];
        }
        const std::size_t offset_bytes = checked_opencl_bytes(
            transport.destination_offsets.size(),
            sizeof(cl_int),
            "OpenCL crust-overlap shadow offset upload"
        );
        const std::size_t source_id_bytes = checked_opencl_bytes(
            edge_count,
            sizeof(cl_int),
            "OpenCL crust-overlap shadow source-id upload"
        );
        const std::size_t edge_area_bytes = checked_opencl_bytes(
            edge_count,
            sizeof(double),
            "OpenCL crust-overlap shadow edge-area upload"
        );
        const std::size_t destination_area_bytes = checked_opencl_bytes(
            cell_count,
            sizeof(double),
            "OpenCL crust-overlap shadow destination-area upload"
        );
        const std::size_t source_state_bytes = checked_opencl_bytes(
            source_state.size(),
            sizeof(double),
            "OpenCL crust-overlap shadow source-state upload"
        );
        const std::size_t output_count = 6U * cell_count;
        const std::size_t output_bytes = checked_opencl_bytes(
            output_count,
            sizeof(double),
            "OpenCL crust-overlap shadow output readback"
        );
        write_buffer(
            overlap_shadow_destination_offset_buffer,
            offset_bytes,
            destination_offsets.data()
        );
        if (edge_count > 0) {
            write_buffer(
                overlap_shadow_source_id_buffer,
                source_id_bytes,
                source_cell_ids.data()
            );
            write_buffer(
                overlap_shadow_area_buffer,
                edge_area_bytes,
                transport.overlap_area_km2.data()
            );
        }
        write_buffer(
            overlap_shadow_destination_area_buffer,
            destination_area_bytes,
            destination_area.data()
        );
        write_buffer(
            overlap_shadow_source_state_buffer,
            source_state_bytes,
            source_state.data()
        );

        const cl_int kernel_cell_count = static_cast<cl_int>(cell_count);
        set_arg(
            overlap_shadow_kernel,
            0,
            sizeof(overlap_shadow_destination_offset_buffer),
            &overlap_shadow_destination_offset_buffer
        );
        set_arg(
            overlap_shadow_kernel,
            1,
            sizeof(overlap_shadow_source_id_buffer),
            &overlap_shadow_source_id_buffer
        );
        set_arg(
            overlap_shadow_kernel,
            2,
            sizeof(overlap_shadow_area_buffer),
            &overlap_shadow_area_buffer
        );
        set_arg(
            overlap_shadow_kernel,
            3,
            sizeof(overlap_shadow_destination_area_buffer),
            &overlap_shadow_destination_area_buffer
        );
        set_arg(
            overlap_shadow_kernel,
            4,
            sizeof(overlap_shadow_source_state_buffer),
            &overlap_shadow_source_state_buffer
        );
        set_arg(
            overlap_shadow_kernel,
            5,
            sizeof(kernel_cell_count),
            &kernel_cell_count
        );
        set_arg(
            overlap_shadow_kernel,
            6,
            sizeof(overlap_shadow_output_buffer),
            &overlap_shadow_output_buffer
        );
        const std::size_t global = rounded_global_size(
            cell_count, overlap_shadow_local_work_size
        );
        require_success(
            api->enqueue_ndrange_kernel(
                queue,
                overlap_shadow_kernel,
                1,
                nullptr,
                &global,
                &overlap_shadow_local_work_size,
                0,
                nullptr,
                nullptr
            ),
            "clEnqueueNDRangeKernel(reduce_crust_overlap_continuous_shadow)"
        );
        kernel_dispatch_count++;
        crust_overlap_continuous_shadow_dispatch_count++;

        std::vector<double> packed_output(output_count);
        read_buffer(
            overlap_shadow_output_buffer,
            output_bytes,
            packed_output.data()
        );
        output.crust_volume_km3_by_destination.assign(
            packed_output.begin(), packed_output.begin() + cell_count
        );
        output.density_weighted_crust_volume_by_destination.assign(
            packed_output.begin() + cell_count,
            packed_output.begin() + 2U * cell_count
        );
        output.crust_age_volume_moment_by_destination.assign(
            packed_output.begin() + 2U * cell_count,
            packed_output.begin() + 3U * cell_count
        );
        output.remapped_crust_thickness_km_by_destination.assign(
            packed_output.begin() + 3U * cell_count,
            packed_output.begin() + 4U * cell_count
        );
        output.remapped_crust_density_by_destination.assign(
            packed_output.begin() + 4U * cell_count,
            packed_output.begin() + 5U * cell_count
        );
        output.remapped_crust_age_ma_by_destination.assign(
            packed_output.begin() + 5U * cell_count,
            packed_output.end()
        );
        last_global_work_size = global;
        last_local_work_size = overlap_shadow_local_work_size;
    }

    void run_remap_crust_sources(
        const std::vector<Cell>& cells,
        const std::vector<Vec3>& backtraced_positions,
        const std::vector<std::vector<int>>& previous_cells_by_plate,
        std::vector<int>& source_cell_ids
    ) {
        if (!runtime_ready || selected_backend != "opencl") {
            throw std::runtime_error("OpenCL crust-source remap runtime is not active");
        }
        if (cells.size() != backtraced_positions.size() ||
            previous_cells_by_plate.empty()) {
            throw std::runtime_error("OpenCL crust-source remap input shape is invalid");
        }
        if (cells.size() > static_cast<std::size_t>(std::numeric_limits<cl_int>::max()) ||
            previous_cells_by_plate.size() >
                static_cast<std::size_t>(std::numeric_limits<cl_int>::max())) {
            throw std::runtime_error("OpenCL crust-source remap exceeds 32-bit kernel indices");
        }
        ensure_legacy_remap_kernel();

        std::vector<PackedVec4> packed_queries(cells.size());
        std::vector<cl_int> current_plate_ids(cells.size(), -1);
        for (std::size_t index = 0; index < cells.size(); ++index) {
            const Vec3& query = backtraced_positions[index];
            packed_queries[index] = {query.x, query.y, query.z, 0.0};
            const int plate_id = cells[index].plate_id;
            if (plate_id < 0 ||
                plate_id >= static_cast<int>(previous_cells_by_plate.size())) {
                throw std::runtime_error("OpenCL crust-source remap has an invalid plate id");
            }
            current_plate_ids[index] = static_cast<cl_int>(plate_id);
        }

        std::vector<cl_int> candidate_offsets(
            previous_cells_by_plate.size() + 1, 0
        );
        std::vector<cl_int> candidate_ids;
        candidate_ids.reserve(cells.size());
        for (std::size_t plate_id = 0;
             plate_id < previous_cells_by_plate.size();
             ++plate_id) {
            int previous_id = -1;
            for (int candidate : previous_cells_by_plate[plate_id]) {
                if (candidate < 0 || candidate >= static_cast<int>(cells.size()) ||
                    candidate <= previous_id) {
                    throw std::runtime_error(
                        "OpenCL crust-source candidates must be valid ascending cell ids"
                    );
                }
                candidate_ids.push_back(static_cast<cl_int>(candidate));
                previous_id = candidate;
            }
            if (candidate_ids.size() >
                static_cast<std::size_t>(std::numeric_limits<cl_int>::max())) {
                throw std::runtime_error(
                    "OpenCL crust-source candidate list exceeds 32-bit kernel indices"
                );
            }
            candidate_offsets[plate_id + 1] =
                static_cast<cl_int>(candidate_ids.size());
        }
        if (candidate_ids.empty()) {
            throw std::runtime_error("OpenCL crust-source remap has no candidates");
        }

        ensure_positions(cells);
        ensure_remap_buffers(
            cells.size(), previous_cells_by_plate.size(), candidate_ids.size()
        );
        write_buffer(
            remap_query_buffer,
            packed_queries.size() * sizeof(PackedVec4),
            packed_queries.data()
        );
        write_buffer(
            remap_plate_id_buffer,
            current_plate_ids.size() * sizeof(cl_int),
            current_plate_ids.data()
        );
        write_buffer(
            remap_candidate_offset_buffer,
            candidate_offsets.size() * sizeof(cl_int),
            candidate_offsets.data()
        );
        write_buffer(
            remap_candidate_id_buffer,
            candidate_ids.size() * sizeof(cl_int),
            candidate_ids.data()
        );

        const cl_int plate_count =
            static_cast<cl_int>(previous_cells_by_plate.size());
        const cl_int cell_count = static_cast<cl_int>(cells.size());
        set_arg(remap_kernel, 0, sizeof(position_buffer), &position_buffer);
        set_arg(remap_kernel, 1, sizeof(remap_query_buffer), &remap_query_buffer);
        set_arg(remap_kernel, 2, sizeof(remap_plate_id_buffer), &remap_plate_id_buffer);
        set_arg(
            remap_kernel,
            3,
            sizeof(remap_candidate_offset_buffer),
            &remap_candidate_offset_buffer
        );
        set_arg(
            remap_kernel,
            4,
            sizeof(remap_candidate_id_buffer),
            &remap_candidate_id_buffer
        );
        set_arg(remap_kernel, 5, sizeof(plate_count), &plate_count);
        set_arg(remap_kernel, 6, sizeof(cell_count), &cell_count);
        set_arg(
            remap_kernel, 7, sizeof(remap_source_id_buffer), &remap_source_id_buffer
        );

        const std::size_t global = rounded_global_size(
            cells.size(), remap_local_work_size
        );
        require_success(
            api->enqueue_ndrange_kernel(
                queue,
                remap_kernel,
                1,
                nullptr,
                &global,
                &remap_local_work_size,
                0,
                nullptr,
                nullptr
            ),
            "clEnqueueNDRangeKernel(remap_crust_sources)"
        );
        std::vector<cl_int> gpu_source_ids(cells.size(), -1);
        read_buffer(
            remap_source_id_buffer,
            gpu_source_ids.size() * sizeof(cl_int),
            gpu_source_ids.data()
        );

        source_cell_ids.resize(gpu_source_ids.size());
        for (std::size_t index = 0; index < gpu_source_ids.size(); ++index) {
            const int source_id = static_cast<int>(gpu_source_ids[index]);
            const int plate_id = current_plate_ids[index];
            const std::vector<int>& candidates =
                previous_cells_by_plate[static_cast<std::size_t>(plate_id)];
            const bool valid_source = candidates.empty()
                ? source_id == static_cast<int>(index)
                : std::binary_search(candidates.begin(), candidates.end(), source_id);
            if (!valid_source) {
                throw std::runtime_error(
                    "OpenCL crust-source remap returned a source outside its plate segment"
                );
            }
            source_cell_ids[index] = source_id;
        }
        kernel_dispatch_count++;
        crust_remap_dispatch_count++;
        last_global_work_size = global;
        last_local_work_size = remap_local_work_size;
    }

    std::string json() const {
        std::string output = "{";
        bool first = true;
        json_string(output, first, "native_core", "c++20");
#ifdef MAGIC_GEO_HAS_OPENMP
        json_bool(output, first, "openmp_enabled", true);
#else
        json_bool(output, first, "openmp_enabled", false);
#endif
#ifdef _OPENMP
        json_integer(output, first, "openmp_max_threads", omp_get_max_threads());
#else
        json_integer(output, first, "openmp_max_threads", 1);
#endif
        json_string(
            output, first, "requested_backend", requested_backend_name(requested_backend)
        );
        const CudaTelemetry& cuda = cuda_status();
        const std::uint64_t accelerator_dispatch_count =
            kernel_dispatch_count + cuda.kernel_dispatch_count;
        json_string(output, first, "selected_backend", selected_backend);
        const std::string active_backend =
            fallback_used && accelerator_dispatch_count > 0
                ? "hybrid"
                : selected_backend;
        json_string(output, first, "active_backend", active_backend);
        json_string(output, first, "initial_selected_backend", initial_selected_backend);
        json_string(output, first, "backend_selection_reason", selection_reason);
        json_string(
            output,
            first,
            "backend_scope",
            "accelerated_native_kernels_not_end_to_end_pipeline"
        );
        json_string(
            output,
            first,
            "crust_transport_execution_backend",
            "cpu"
        );
        json_string(
            output,
            first,
            "crust_transport_execution_model",
            "forward_spherical_control_volume_overlap_v1"
        );
        json_integer(
            output,
            first,
            "crust_transport_accelerator_dispatch_count",
            0
        );
        json_integer(
            output,
            first,
            "cpu_conservative_crust_overlap_transition_count",
            cpu_conservative_crust_overlap_transition_count
        );
        json_string(
            output,
            first,
            "crust_overlap_geometry_and_csr_authoritative_backend",
            "cpu"
        );
        json_string(
            output,
            first,
            "crust_overlap_continuous_production_remap_authoritative_backend",
            "cpu"
        );
        json_string(
            output,
            first,
            "crust_overlap_continuous_shadow_model",
            "cpu_authoritative_overlap_csr_continuous_moment_shadow_v1"
        );
        json_string(
            output,
            first,
            "crust_overlap_continuous_shadow_scope",
            "raw_extensive_moments_and_derived_continuous_state_only"
        );
        json_string(
            output,
            first,
            "crust_overlap_continuous_shadow_error_summary_semantics",
            "per_quantity_maximum_error_and_maximum_bound_are_independent_uniform_maxima_paired_worst_case_is_maximum_error_to_bound_ratio"
        );
        json_string(
            output,
            first,
            "crust_transport_accelerator_dispatch_count_semantics",
            "complete_authoritative_forward_overlap_plan_dispatches_only"
        );
        json_bool(
            output,
            first,
            "crust_overlap_continuous_shadow_only",
            true
        );
        json_bool(
            output,
            first,
            "crust_overlap_continuous_shadow_authoritative",
            false
        );
        json_bool(
            output,
            first,
            "crust_overlap_continuous_shadow_result_used_for_state",
            false
        );
        json_bool(
            output,
            first,
            "crust_overlap_accelerator_geometry_parity_demonstrated",
            false
        );
        json_bool(
            output,
            first,
            "crust_overlap_accelerator_coverage_membership_parity_demonstrated",
            false
        );
        json_bool(
            output,
            first,
            "crust_overlap_accelerator_categorical_parity_demonstrated",
            false
        );
        json_bool(
            output,
            first,
            "crust_overlap_accelerator_complete_parity_demonstrated",
            false
        );
        json_bool(
            output,
            first,
            "crust_overlap_accelerator_state_authoritative",
            false
        );
        const std::uint64_t shadow_device_dispatch_count =
            crust_overlap_continuous_shadow_dispatch_count +
            cuda.crust_overlap_continuous_shadow_dispatch_count;
        json_integer(
            output,
            first,
            "crust_overlap_continuous_shadow_device_dispatch_count",
            shadow_device_dispatch_count
        );
        json_integer(
            output,
            first,
            "crust_overlap_continuous_shadow_validated_transition_count",
            crust_overlap_continuous_shadow_validated_transition_count
        );
        json_integer(
            output,
            first,
            "crust_overlap_continuous_shadow_failure_count",
            crust_overlap_continuous_shadow_failure_count
        );
        json_bool(
            output,
            first,
            "crust_overlap_continuous_shadow_last_validation_passed",
            crust_overlap_continuous_shadow_last_validation_passed
        );
        json_bool(
            output,
            first,
            "crust_overlap_continuous_shadow_all_validated_transitions_passed",
            crust_overlap_continuous_shadow_validated_transition_count > 0 &&
                crust_overlap_continuous_shadow_failure_count == 0
        );
        const char* shadow_status =
            crust_overlap_continuous_shadow_failure_count > 0
                ? "failed_and_cpu_authority_retained"
                : (crust_overlap_continuous_shadow_validated_transition_count > 0 &&
                        crust_overlap_continuous_shadow_validated_transition_count ==
                            static_cast<std::uint64_t>(
                                cpu_conservative_crust_overlap_transition_count
                            )
                    ? "passed"
                    : (crust_overlap_continuous_shadow_validated_transition_count > 0
                        ? "partial_pass_before_cpu_fallback"
                        : (cpu_conservative_crust_overlap_transition_count == 0
                            ? "not_run_no_conservative_transition"
                            : "not_run_no_active_accelerator")));
        json_string(
            output,
            first,
            "crust_overlap_continuous_shadow_validation_status",
            shadow_status
        );
        json_number(
            output,
            first,
            "crust_overlap_continuous_shadow_maximum_crust_volume_error_km3",
            crust_overlap_continuous_shadow_maxima.
                maximum_crust_volume_error_km3
        );
        json_number(
            output,
            first,
            "crust_overlap_continuous_shadow_maximum_crust_volume_error_bound_km3",
            crust_overlap_continuous_shadow_maxima.
                maximum_crust_volume_error_bound_km3
        );
        json_number(
            output,
            first,
            "crust_overlap_continuous_shadow_maximum_density_weighted_volume_error",
            crust_overlap_continuous_shadow_maxima.
                maximum_density_weighted_volume_error
        );
        json_number(
            output,
            first,
            "crust_overlap_continuous_shadow_maximum_density_weighted_volume_error_bound",
            crust_overlap_continuous_shadow_maxima.
                maximum_density_weighted_volume_error_bound
        );
        json_number(
            output,
            first,
            "crust_overlap_continuous_shadow_maximum_age_volume_moment_error",
            crust_overlap_continuous_shadow_maxima.
                maximum_crust_age_volume_moment_error
        );
        json_number(
            output,
            first,
            "crust_overlap_continuous_shadow_maximum_age_volume_moment_error_bound",
            crust_overlap_continuous_shadow_maxima.
                maximum_crust_age_volume_moment_error_bound
        );
        json_number(
            output,
            first,
            "crust_overlap_continuous_shadow_maximum_remapped_thickness_error_km",
            crust_overlap_continuous_shadow_maxima.
                maximum_remapped_thickness_error_km
        );
        json_number(
            output,
            first,
            "crust_overlap_continuous_shadow_maximum_remapped_thickness_error_bound_km",
            crust_overlap_continuous_shadow_maxima.
                maximum_remapped_thickness_error_bound_km
        );
        json_number(
            output,
            first,
            "crust_overlap_continuous_shadow_maximum_remapped_density_error",
            crust_overlap_continuous_shadow_maxima.
                maximum_remapped_density_error
        );
        json_number(
            output,
            first,
            "crust_overlap_continuous_shadow_maximum_remapped_density_error_bound",
            crust_overlap_continuous_shadow_maxima.
                maximum_remapped_density_error_bound
        );
        json_number(
            output,
            first,
            "crust_overlap_continuous_shadow_maximum_remapped_age_error_ma",
            crust_overlap_continuous_shadow_maxima.
                maximum_remapped_age_error_ma
        );
        json_number(
            output,
            first,
            "crust_overlap_continuous_shadow_maximum_remapped_age_error_bound_ma",
            crust_overlap_continuous_shadow_maxima.
                maximum_remapped_age_error_bound_ma
        );
        json_number(
            output,
            first,
            "crust_overlap_continuous_shadow_maximum_error_to_bound_ratio",
            crust_overlap_continuous_shadow_maxima.maximum_error_to_bound_ratio
        );
        json_bool(
            output,
            first,
            "accelerator_crust_source_remap_kernel_production_active",
            false
        );
        json_bool(
            output,
            first,
            "legacy_nearest_source_remap_world_pipeline_enabled",
            false
        );
        json_bool(
            output,
            first,
            "legacy_crust_source_remap_dispatch_counters_deprecated",
            true
        );
        json_string(
            output,
            first,
            "accelerator_crust_source_remap_kernel_role",
            "legacy_nearest_donor_test_hook_not_used_by_v3_transport"
        );
        json_integer(
            output, first, "automatic_planning_cell_count", auto_planning_cell_count
        );
        json_integer(
            output, first, "accelerator_kernel_dispatch_count", accelerator_dispatch_count
        );
        json_bool(output, first, "opencl_prefer_gpu", prefer_gpu);
        json_integer(
            output, first, "cuda_auto_min_cell_count", cuda_auto_min_cell_count
        );
        json_integer(
            output,
            first,
            "cuda_sm_120_auto_min_cell_count",
            CUDA_SM_120_AUTO_MIN_CELL_COUNT
        );
        json_integer(
            output,
            first,
            "cuda_uncalibrated_auto_min_cell_count",
            CUDA_UNCALIBRATED_AUTO_MIN_CELL_COUNT
        );
        json_bool(
            output, first, "cuda_auto_offload_eligible", cuda_auto_offload_eligible
        );
        json_integer(
            output, first, "opencl_auto_min_cell_count", OPENCL_AUTO_MIN_CELL_COUNT
        );
        json_bool(
            output, first, "opencl_auto_offload_eligible", auto_offload_eligible
        );
        json_bool(output, first, "backend_fallback_used", fallback_used);
        json_string(output, first, "backend_fallback_stage", fallback_stage);
        json_string(output, first, "backend_fallback_reason", fallback_reason);

#ifdef MAGIC_GEO_HAS_CUDA
        constexpr bool cuda_backend_compiled = true;
#else
        constexpr bool cuda_backend_compiled = false;
#endif
        json_bool(output, first, "cuda_compiled", cuda_backend_compiled);
        json_bool(output, first, "cuda_probe_performed", cuda_probe_performed);
        const std::string cuda_capability_status = !cuda_probe_performed
            ? "not_probed"
            : (!cuda_backend_compiled
                ? "not_compiled"
                : (cuda.available ? "available" : "unavailable"));
        json_string(output, first, "cuda_capability_status", cuda_capability_status);
        json_bool(output, first, "cuda_runtime_initialized", cuda.runtime_initialized);
        json_bool(output, first, "cuda_available", cuda.available);
        json_bool(output, first, "cuda_nvidia_device", cuda.nvidia_device);
        json_bool(output, first, "cuda_fp64_supported", cuda.fp64_supported);
        json_bool(output, first, "cuda_sm_120_optimized", cuda.sm_120_optimized);
        json_string(output, first, "cuda_error", cuda.error);
        json_integer(output, first, "cuda_device_count", cuda.device_count);
        json_integer(
            output, first, "cuda_selected_device_ordinal", cuda.selected_device_ordinal
        );
        json_string(output, first, "cuda_device_vendor", cuda.device_vendor);
        json_string(output, first, "cuda_device_name", cuda.device_name);
        json_string(output, first, "cuda_device_uuid", cuda.device_uuid);
        json_string(output, first, "cuda_pci_bus_id", cuda.pci_bus_id);
        json_integer(
            output,
            first,
            "cuda_compute_capability_major",
            cuda.compute_capability_major
        );
        json_integer(
            output,
            first,
            "cuda_compute_capability_minor",
            cuda.compute_capability_minor
        );
        json_integer(
            output, first, "cuda_kernel_binary_version", cuda.kernel_binary_version
        );
        json_integer(output, first, "cuda_kernel_ptx_version", cuda.kernel_ptx_version);
        json_integer(output, first, "cuda_driver_version", cuda.driver_version);
        json_integer(output, first, "cuda_runtime_version", cuda.runtime_version);
        json_integer(
            output, first, "cuda_total_global_memory_bytes", cuda.total_global_memory_bytes
        );
        json_integer(
            output, first, "cuda_free_global_memory_bytes", cuda.free_global_memory_bytes
        );
        json_integer(
            output, first, "cuda_multiprocessor_count", cuda.multiprocessor_count
        );
        json_integer(output, first, "cuda_warp_size", cuda.warp_size);
        json_integer(
            output, first, "cuda_max_threads_per_block", cuda.max_threads_per_block
        );
        json_integer(
            output,
            first,
            "cuda_max_threads_per_multiprocessor",
            cuda.max_threads_per_multiprocessor
        );
        json_integer(
            output, first, "cuda_max_block_dimension_x", cuda.max_block_dimensions[0]
        );
        json_integer(
            output, first, "cuda_max_block_dimension_y", cuda.max_block_dimensions[1]
        );
        json_integer(
            output, first, "cuda_max_block_dimension_z", cuda.max_block_dimensions[2]
        );
        json_integer(
            output, first, "cuda_max_grid_dimension_x", cuda.max_grid_dimensions[0]
        );
        json_integer(
            output, first, "cuda_max_grid_dimension_y", cuda.max_grid_dimensions[1]
        );
        json_integer(
            output, first, "cuda_max_grid_dimension_z", cuda.max_grid_dimensions[2]
        );
        json_integer(output, first, "cuda_l2_cache_bytes", cuda.l2_cache_bytes);
        json_integer(
            output,
            first,
            "cuda_shared_memory_per_block_bytes",
            cuda.shared_memory_per_block_bytes
        );
        json_integer(
            output,
            first,
            "cuda_shared_memory_per_multiprocessor_bytes",
            cuda.shared_memory_per_multiprocessor_bytes
        );
        json_integer(output, first, "cuda_registers_per_block", cuda.registers_per_block);
        json_integer(
            output,
            first,
            "cuda_registers_per_multiprocessor",
            cuda.registers_per_multiprocessor
        );
        json_integer(output, first, "cuda_core_clock_khz", cuda.core_clock_khz);
        json_integer(output, first, "cuda_memory_clock_khz", cuda.memory_clock_khz);
        json_integer(
            output, first, "cuda_memory_bus_width_bits", cuda.memory_bus_width_bits
        );
        json_string(output, first, "cuda_fp_contract", "off");
        json_integer(output, first, "cuda_kernel_dispatch_count", cuda.kernel_dispatch_count);
        json_integer(
            output,
            first,
            "cuda_plate_assignment_dispatch_count",
            cuda.plate_assignment_dispatch_count
        );
        json_integer(
            output, first, "cuda_smoothing_operation_count", cuda.smoothing_operation_count
        );
        json_integer(
            output,
            first,
            "cuda_smoothing_kernel_dispatch_count",
            cuda.smoothing_kernel_dispatch_count
        );
        json_integer(
            output,
            first,
            "cuda_batched_smoothing_operation_count",
            cuda.batched_smoothing_operation_count
        );
        json_integer(
            output,
            first,
            "cuda_batched_smoothing_kernel_dispatch_count",
            cuda.batched_smoothing_kernel_dispatch_count
        );
        json_integer(
            output,
            first,
            "cuda_crust_source_remap_dispatch_count",
            cuda.crust_source_remap_dispatch_count
        );
        json_integer(
            output,
            first,
            "cuda_crust_overlap_continuous_shadow_dispatch_count",
            cuda.crust_overlap_continuous_shadow_dispatch_count
        );
        json_integer(
            output, first, "cuda_host_to_device_bytes", cuda.host_to_device_bytes
        );
        json_integer(
            output, first, "cuda_device_to_host_bytes", cuda.device_to_host_bytes
        );
        json_integer(
            output, first, "cuda_device_allocation_count", cuda.device_allocation_count
        );
        json_integer(output, first, "cuda_mesh_upload_count", cuda.mesh_upload_count);
        json_integer(
            output, first, "cuda_allocated_device_bytes", cuda.allocated_device_bytes
        );
        json_integer(
            output,
            first,
            "cuda_peak_allocated_device_bytes",
            cuda.peak_allocated_device_bytes
        );
        json_number(output, first, "cuda_kernel_time_ms", cuda.kernel_time_ms);
        json_number(output, first, "cuda_transfer_time_ms", cuda.transfer_time_ms);
        json_number(output, first, "cuda_operation_time_ms", cuda.operation_time_ms);
        json_number(
            output, first, "cuda_last_kernel_time_ms", cuda.last_kernel_time_ms
        );
        json_number(
            output, first, "cuda_last_transfer_time_ms", cuda.last_transfer_time_ms
        );
        json_number(
            output, first, "cuda_last_operation_time_ms", cuda.last_operation_time_ms
        );
        json_integer(
            output, first, "cuda_last_logical_work_items", cuda.last_logical_work_items
        );
        json_integer(output, first, "cuda_last_grid_blocks", cuda.last_grid_blocks);
        json_integer(
            output, first, "cuda_last_threads_per_block", cuda.last_threads_per_block
        );
        json_integer(
            output, first, "cuda_last_warps_per_block", cuda.last_warps_per_block
        );

        json_bool(output, first, "opencl_probe_performed", probe_performed);
        const std::string capability_status = !probe_performed
            ? "not_probed"
            : (!probe_ok
                ? "probe_failed"
                : (qualifying_device_count > 0 ? "available" : "no_qualifying_device"));
        json_string(output, first, "opencl_capability_status", capability_status);
        json_bool(output, first, "opencl_loader_found", loader_found);
        json_bool(output, first, "opencl_probe_ok", probe_ok);
        json_integer(output, first, "opencl_platform_count", platform_count);
        json_integer(output, first, "opencl_gpu_device_count", gpu_device_count);
        json_integer(output, first, "opencl_cpu_device_count", cpu_device_count);
        json_integer(
            output, first, "opencl_accelerator_device_count", accelerator_device_count
        );
        json_integer(output, first, "opencl_fp64_device_count", fp64_device_count);
        json_integer(
            output, first, "opencl_qualifying_device_count", qualifying_device_count
        );
        json_integer(
            output,
            first,
            "opencl_qualifying_gpu_device_count",
            qualifying_gpu_device_count
        );
        json_bool(
            output,
            first,
            "opencl_auto_preferred_gpu_available",
            qualifying_gpu_device_count > 0
        );
        json_bool(output, first, "opencl_fp64_required", true);
        json_bool(output, first, "opencl_available", qualifying_device_count > 0);
        json_string(output, first, "opencl_error", probe_error);
        json_bool(output, first, "opencl_program_built", program_ever_built);
        json_bool(output, first, "opencl_program_active", program_built);
        json_string(output, first, "opencl_build_options", "-cl-std=CL1.2");
        json_string(output, first, "opencl_fp_contract", "off");
        json_bool(output, first, "opencl_profiling_queue_enabled", runtime_ready);
        json_integer(output, first, "opencl_kernel_dispatch_count", kernel_dispatch_count);
        json_integer(
            output,
            first,
            "opencl_plate_assignment_dispatch_count",
            plate_assignment_dispatch_count
        );
        json_integer(
            output,
            first,
            "opencl_smoothing_operation_count",
            smoothing_operation_count
        );
        json_integer(
            output,
            first,
            "opencl_smoothing_kernel_dispatch_count",
            smoothing_kernel_dispatch_count
        );
        json_integer(
            output,
            first,
            "opencl_batched_smoothing_operation_count",
            batched_smoothing_operation_count
        );
        json_integer(
            output,
            first,
            "opencl_batched_smoothing_kernel_dispatch_count",
            batched_smoothing_kernel_dispatch_count
        );
        json_integer(
            output,
            first,
            "opencl_crust_source_remap_dispatch_count",
            crust_remap_dispatch_count
        );
        json_integer(
            output,
            first,
            "opencl_crust_overlap_continuous_shadow_dispatch_count",
            crust_overlap_continuous_shadow_dispatch_count
        );
        json_integer(output, first, "opencl_host_to_device_bytes", host_to_device_bytes);
        json_integer(output, first, "opencl_device_to_host_bytes", device_to_host_bytes);
        json_integer(output, first, "opencl_last_global_work_size", last_global_work_size);
        json_integer(output, first, "opencl_last_local_work_size", last_local_work_size);

        const DeviceRecord* device = selected_device();
        if (device == nullptr) {
            for (const DeviceRecord& candidate : devices) {
                if (candidate.qualifies()) {
                    device = &candidate;
                    break;
                }
            }
        }
        if (device != nullptr) {
            json_string(output, first, "opencl_platform_name", device->platform_name);
            json_string(output, first, "opencl_platform_vendor", device->platform_vendor);
            json_string(output, first, "opencl_platform_version", device->platform_version);
            json_string(output, first, "opencl_device_name", device->name);
            json_string(output, first, "opencl_device_vendor", device->vendor);
            json_string(output, first, "opencl_device_type", device_type_name(device->type));
            json_string(output, first, "opencl_driver_version", device->driver_version);
            json_string(output, first, "opencl_device_version", device->device_version);
            json_string(output, first, "opencl_c_version", device->opencl_c_version);
            json_bool(output, first, "opencl_device_available", device->available);
            json_bool(
                output, first, "opencl_device_compiler_available", device->compiler_available
            );
            json_bool(output, first, "opencl_device_fp64", device->fp64_supported);
            json_bool(
                output, first, "opencl_device_fp64_denorm", device->fp64_denorm
            );
            json_bool(
                output,
                first,
                "opencl_device_fp64_round_to_nearest",
                device->fp64_round_to_nearest
            );
            json_bool(
                output, first, "opencl_device_fp64_inf_nan", device->fp64_inf_nan
            );
            json_bool(
                output, first, "opencl_device_endian_little", device->endian_little
            );
            json_bool(
                output,
                first,
                "opencl_device_endian_matches_host",
                device->endian_matches_host
            );
            json_bool(
                output,
                first,
                "opencl_device_opencl_c_1_2",
                device->opencl_c_12_supported
            );
            json_integer(output, first, "opencl_device_address_bits", device->address_bits);
            json_integer(output, first, "opencl_device_compute_units", device->compute_units);
            json_integer(
                output,
                first,
                "opencl_device_global_memory_bytes",
                device->global_memory_bytes
            );
            json_integer(
                output,
                first,
                "opencl_device_max_allocation_bytes",
                device->max_allocation_bytes
            );
            json_integer(
                output,
                first,
                "opencl_device_max_work_group_size",
                device->max_work_group_size
            );
            json_integer(
                output,
                first,
                "opencl_device_max_work_item_size_0",
                device->max_work_item_size_0
            );
        } else {
            json_string(output, first, "opencl_platform_name", "");
            json_string(output, first, "opencl_platform_vendor", "");
            json_string(output, first, "opencl_platform_version", "");
            json_string(output, first, "opencl_device_name", "");
            json_string(output, first, "opencl_device_vendor", "");
            json_string(output, first, "opencl_device_type", "");
            json_string(output, first, "opencl_driver_version", "");
            json_string(output, first, "opencl_device_version", "");
            json_string(output, first, "opencl_c_version", "");
            json_bool(output, first, "opencl_device_available", false);
            json_bool(output, first, "opencl_device_compiler_available", false);
            json_bool(output, first, "opencl_device_fp64", false);
            json_bool(output, first, "opencl_device_fp64_denorm", false);
            json_bool(output, first, "opencl_device_fp64_round_to_nearest", false);
            json_bool(output, first, "opencl_device_fp64_inf_nan", false);
            json_bool(output, first, "opencl_device_endian_little", false);
            json_bool(output, first, "opencl_device_endian_matches_host", false);
            json_bool(output, first, "opencl_device_opencl_c_1_2", false);
            json_integer(output, first, "opencl_device_address_bits", 0);
            json_integer(output, first, "opencl_device_compute_units", 0);
            json_integer(output, first, "opencl_device_global_memory_bytes", 0);
            json_integer(output, first, "opencl_device_max_allocation_bytes", 0);
            json_integer(output, first, "opencl_device_max_work_group_size", 0);
            json_integer(output, first, "opencl_device_max_work_item_size_0", 0);
        }
        output += '}';
        return output;
    }

    int requested_backend = 0;
    bool prefer_gpu = true;
    int cpu_conservative_crust_overlap_transition_count = 0;
    std::uint64_t crust_overlap_continuous_shadow_validated_transition_count = 0;
    std::uint64_t crust_overlap_continuous_shadow_failure_count = 0;
    bool crust_overlap_continuous_shadow_last_validation_passed = false;
    CrustOverlapContinuousShadowValidation crust_overlap_continuous_shadow_maxima;
    bool auto_selection_pending = false;
    std::size_t auto_planning_cell_count = 0;
    int cuda_auto_min_cell_count = CUDA_SM_120_AUTO_MIN_CELL_COUNT;
    bool cuda_auto_offload_eligible = false;
    bool auto_offload_eligible = false;
    std::string selected_backend = "cpu";
    std::string initial_selected_backend = "cpu";
    std::string selection_reason;
    bool fallback_used = false;
    std::string fallback_stage;
    std::string fallback_reason;

    std::unique_ptr<CudaComputeSession> cuda_session;
    CudaTelemetry cuda_probe;
    bool cuda_probe_performed = false;

    std::unique_ptr<OpenClApi> api;
    bool probe_performed = false;
    bool loader_found = false;
    bool probe_ok = false;
    cl_uint platform_count = 0;
    cl_uint gpu_device_count = 0;
    cl_uint cpu_device_count = 0;
    cl_uint accelerator_device_count = 0;
    cl_uint fp64_device_count = 0;
    cl_uint qualifying_device_count = 0;
    cl_uint qualifying_gpu_device_count = 0;
    std::string probe_error;
    std::vector<DeviceRecord> devices;
    int selected_device_index = -1;

    cl_context context = nullptr;
    cl_command_queue queue = nullptr;
    cl_program program = nullptr;
    cl_kernel assign_kernel = nullptr;
    cl_kernel smooth_kernel = nullptr;
    cl_kernel smooth_three_kernel = nullptr;
    cl_kernel overlap_shadow_kernel = nullptr;
    cl_kernel remap_kernel = nullptr;
    bool runtime_ready = false;
    bool program_built = false;
    bool program_ever_built = false;
    std::size_t assign_local_work_size = 1;
    std::size_t smooth_local_work_size = 1;
    std::size_t smooth_three_local_work_size = 1;
    std::size_t overlap_shadow_local_work_size = 1;
    std::size_t remap_local_work_size = 1;

    const Cell* mesh_identity = nullptr;
    std::size_t mesh_cell_count = 0;
    bool positions_ready = false;
    bool adjacency_ready = false;
    cl_mem position_buffer = nullptr;
    cl_mem neighbor_offset_buffer = nullptr;
    cl_mem neighbor_id_buffer = nullptr;
    cl_mem center_buffer = nullptr;
    cl_mem plate_id_buffer = nullptr;
    cl_mem smooth_a_buffer = nullptr;
    cl_mem smooth_b_buffer = nullptr;
    cl_mem smooth_three_a_buffer = nullptr;
    cl_mem smooth_three_b_buffer = nullptr;
    cl_mem remap_query_buffer = nullptr;
    cl_mem remap_plate_id_buffer = nullptr;
    cl_mem remap_candidate_offset_buffer = nullptr;
    cl_mem remap_candidate_id_buffer = nullptr;
    cl_mem remap_source_id_buffer = nullptr;
    cl_mem overlap_shadow_destination_offset_buffer = nullptr;
    cl_mem overlap_shadow_source_id_buffer = nullptr;
    cl_mem overlap_shadow_area_buffer = nullptr;
    cl_mem overlap_shadow_destination_area_buffer = nullptr;
    cl_mem overlap_shadow_source_state_buffer = nullptr;
    cl_mem overlap_shadow_output_buffer = nullptr;
    std::size_t center_capacity = 0;
    std::size_t plate_capacity = 0;
    std::size_t smooth_capacity = 0;
    std::size_t smooth_three_capacity = 0;
    std::size_t remap_cell_capacity = 0;
    std::size_t remap_plate_capacity = 0;
    std::size_t remap_candidate_capacity = 0;
    std::size_t overlap_shadow_cell_capacity = 0;
    std::size_t overlap_shadow_edge_capacity = 0;

    std::uint64_t kernel_dispatch_count = 0;
    std::uint64_t plate_assignment_dispatch_count = 0;
    std::uint64_t smoothing_operation_count = 0;
    std::uint64_t smoothing_kernel_dispatch_count = 0;
    std::uint64_t batched_smoothing_operation_count = 0;
    std::uint64_t batched_smoothing_kernel_dispatch_count = 0;
    std::uint64_t crust_remap_dispatch_count = 0;
    std::uint64_t crust_overlap_continuous_shadow_dispatch_count = 0;
    std::uint64_t host_to_device_bytes = 0;
    std::uint64_t device_to_host_bytes = 0;
    std::size_t last_global_work_size = 0;
    std::size_t last_local_work_size = 0;
    Impl* previous_session = nullptr;
};

ComputeSession::ComputeSession(
    const Params& params,
    const ComputeOptions& compute_options
)
    : impl_(std::make_unique<Impl>(params, compute_options)) {
    impl_->previous_session = active_compute_session;
    active_compute_session = impl_.get();
}

ComputeSession::~ComputeSession() {
    if (impl_ && active_compute_session == impl_.get()) {
        active_compute_session = impl_->previous_session;
    }
}

bool try_accelerated_assign_plates(
    const std::vector<Vec3>& centers,
    const std::vector<Cell>& cells,
    std::vector<int>& plate_ids
) {
    if (active_compute_session == nullptr) {
        return false;
    }
    try {
        active_compute_session->ensure_auto_backend(cells.size());
        if (active_compute_session->selected_backend == "cuda") {
            active_compute_session->cuda_session->run_assign_plates(
                centers, cells, plate_ids
            );
        } else if (active_compute_session->selected_backend == "opencl") {
            active_compute_session->run_assign_plates(centers, cells, plate_ids);
        } else {
            return false;
        }
        return true;
    } catch (const std::exception& error) {
        if (active_compute_session->requested_backend == 2 ||
            active_compute_session->requested_backend == 3) {
            throw;
        }
        active_compute_session->fall_back_to_cpu("plate_assignment", error.what());
        return false;
    }
}

bool try_accelerated_smooth_field(
    const std::vector<Cell>& cells,
    const std::vector<double>& input,
    int steps,
    double self_weight,
    std::vector<double>& output
) {
    if (active_compute_session == nullptr) {
        return false;
    }
    try {
        active_compute_session->ensure_auto_backend(cells.size());
        if (active_compute_session->selected_backend == "cuda") {
            active_compute_session->cuda_session->run_smooth_field(
                cells, input, steps, self_weight, output
            );
        } else if (active_compute_session->selected_backend == "opencl") {
            active_compute_session->run_smooth_field(
                cells, input, steps, self_weight, output
            );
        } else {
            return false;
        }
        return true;
    } catch (const std::exception& error) {
        if (active_compute_session->requested_backend == 2 ||
            active_compute_session->requested_backend == 3) {
            throw;
        }
        active_compute_session->fall_back_to_cpu("neighbor_field_smoothing", error.what());
        return false;
    }
}

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
) {
    if (active_compute_session == nullptr) {
        return false;
    }
    try {
        active_compute_session->ensure_auto_backend(cells.size());
        if (active_compute_session->selected_backend == "cuda") {
            active_compute_session->cuda_session->run_smooth_three_fields(
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
        } else if (active_compute_session->selected_backend == "opencl") {
            active_compute_session->run_smooth_three_fields(
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
        } else {
            return false;
        }
        return true;
    } catch (const std::exception& error) {
        if (active_compute_session->requested_backend == 2 ||
            active_compute_session->requested_backend == 3) {
            throw;
        }
        active_compute_session->fall_back_to_cpu(
            "batched_neighbor_field_smoothing", error.what()
        );
        return false;
    }
}

bool try_accelerated_remap_crust_sources(
    const std::vector<Cell>& cells,
    const std::vector<Vec3>& backtraced_positions,
    const std::vector<std::vector<int>>& previous_cells_by_plate,
    std::vector<int>& source_cell_ids
) {
    if (active_compute_session == nullptr) {
        return false;
    }
    try {
        active_compute_session->ensure_auto_backend(cells.size());
        if (active_compute_session->selected_backend == "cuda") {
            active_compute_session->cuda_session->run_remap_crust_sources(
                cells,
                backtraced_positions,
                previous_cells_by_plate,
                source_cell_ids
            );
        } else if (active_compute_session->selected_backend == "opencl") {
            active_compute_session->run_remap_crust_sources(
                cells,
                backtraced_positions,
                previous_cells_by_plate,
                source_cell_ids
            );
        } else {
            return false;
        }
        return true;
    } catch (const std::exception& error) {
        if (active_compute_session->requested_backend == 2 ||
            active_compute_session->requested_backend == 3) {
            throw;
        }
        active_compute_session->fall_back_to_cpu("crust_source_remap", error.what());
        return false;
    }
}

void reconcile_accelerated_crust_overlap_continuous_shadow(
    const CrustTransportPlan& transport,
    const std::vector<Cell>& cells,
    const std::vector<double>& source_crust_thickness_km,
    const std::vector<double>& source_crust_density,
    const std::vector<double>& source_crust_age_ma
) {
    if (active_compute_session == nullptr) {
        return;
    }
    active_compute_session->ensure_auto_backend(cells.size());
    if (active_compute_session->selected_backend == "cpu") {
        return;
    }
    try {
        CrustOverlapContinuousShadowResult result;
        if (active_compute_session->selected_backend == "cuda") {
            active_compute_session->cuda_session->run_crust_overlap_continuous_shadow(
                transport,
                cells,
                source_crust_thickness_km,
                source_crust_density,
                source_crust_age_ma,
                result
            );
        } else if (active_compute_session->selected_backend == "opencl") {
            active_compute_session->run_crust_overlap_continuous_shadow(
                transport,
                cells,
                source_crust_thickness_km,
                source_crust_density,
                source_crust_age_ma,
                result
            );
        } else {
            throw std::runtime_error(
                "crust overlap continuous shadow selected an invalid backend"
            );
        }
        const CrustOverlapContinuousShadowValidation validation =
            validate_crust_overlap_continuous_shadow_result(
                transport,
                cells,
                source_crust_thickness_km,
                source_crust_density,
                source_crust_age_ma,
                result
            );
        merge_crust_overlap_shadow_validation_maxima(
            active_compute_session->crust_overlap_continuous_shadow_maxima,
            validation
        );
        if (!validation.passed) {
            throw std::runtime_error(
                "accelerator crust-overlap continuous shadow mismatch: " +
                validation.failure
            );
        }
        active_compute_session->
            crust_overlap_continuous_shadow_validated_transition_count++;
        active_compute_session->
            crust_overlap_continuous_shadow_last_validation_passed = true;
    } catch (const std::exception& error) {
        active_compute_session->crust_overlap_continuous_shadow_failure_count++;
        active_compute_session->
            crust_overlap_continuous_shadow_last_validation_passed = false;
        if (
            active_compute_session->requested_backend == 2 ||
            active_compute_session->requested_backend == 3
        ) {
            throw;
        }
        active_compute_session->fall_back_to_cpu(
            "crust_overlap_continuous_shadow_reconciliation", error.what()
        );
    }
}

void record_cpu_conservative_crust_overlap_transition() {
    if (active_compute_session != nullptr) {
        active_compute_session->cpu_conservative_crust_overlap_transition_count++;
    }
}

std::string compute_backend_info_json() {
    if (active_compute_session != nullptr) {
        return active_compute_session->json();
    }
    Params probe_params;
    ComputeOptions probe_options;
    probe_options.compute_backend = 1;
    ComputeSession::Impl probe(probe_params, probe_options, true);
    return probe.json();
}

}  // namespace magic_geo::detail

namespace magic_geo {

std::string backend_info_json() {
    return detail::compute_backend_info_json();
}

}  // namespace magic_geo
