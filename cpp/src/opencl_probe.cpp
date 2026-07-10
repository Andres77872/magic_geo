#include "magic_geo/native.hpp"

#include <cstdlib>
#include <sstream>
#include <string>
#include <vector>

#if defined(__linux__)
#include <dlfcn.h>
#endif

#ifdef _OPENMP
#include <omp.h>
#endif

namespace magic_geo {
namespace {

struct OpenClProbe {
    bool loader_found = false;
    bool probe_ok = false;
    unsigned int platform_count = 0;
    unsigned int gpu_device_count = 0;
    unsigned int cpu_device_count = 0;
    std::string error;
};

std::string json_escape(const std::string& value) {
    std::string out;
    out.reserve(value.size() + 8);
    for (char ch : value) {
        switch (ch) {
            case '"':
                out += "\\\"";
                break;
            case '\\':
                out += "\\\\";
                break;
            case '\n':
                out += "\\n";
                break;
            case '\r':
                out += "\\r";
                break;
            case '\t':
                out += "\\t";
                break;
            default:
                out += ch;
                break;
        }
    }
    return out;
}

void comma(std::string& out, bool& first) {
    if (!first) {
        out += ",";
    }
    first = false;
}

void add_bool(std::string& out, bool& first, const char* key, bool value) {
    comma(out, first);
    out += "\"";
    out += key;
    out += "\":";
    out += value ? "true" : "false";
}

void add_int(std::string& out, bool& first, const char* key, int value) {
    comma(out, first);
    out += "\"";
    out += key;
    out += "\":";
    out += std::to_string(value);
}

void add_str(std::string& out, bool& first, const char* key, const std::string& value) {
    comma(out, first);
    out += "\"";
    out += key;
    out += "\":\"";
    out += json_escape(value);
    out += "\"";
}

OpenClProbe probe_opencl() {
    OpenClProbe out;

#if defined(__linux__)
    void* lib = dlopen("libOpenCL.so.1", RTLD_LAZY);
    if (lib == nullptr) {
        lib = dlopen("libOpenCL.so", RTLD_LAZY);
    }
    if (lib == nullptr) {
        out.error = "OpenCL loader library was not found";
        return out;
    }
    out.loader_found = true;

    using cl_int = int;
    using cl_uint = unsigned int;
    using cl_platform_id = void*;
    using cl_device_id = void*;
    using cl_device_type = unsigned long;
    constexpr cl_int CL_SUCCESS = 0;
    constexpr cl_device_type CL_DEVICE_TYPE_CPU = 1UL << 1;
    constexpr cl_device_type CL_DEVICE_TYPE_GPU = 1UL << 2;

    using GetPlatformIDs = cl_int (*)(cl_uint, cl_platform_id*, cl_uint*);
    using GetDeviceIDs = cl_int (*)(cl_platform_id, cl_device_type, cl_uint, cl_device_id*, cl_uint*);

    auto get_platform_ids = reinterpret_cast<GetPlatformIDs>(dlsym(lib, "clGetPlatformIDs"));
    auto get_device_ids = reinterpret_cast<GetDeviceIDs>(dlsym(lib, "clGetDeviceIDs"));
    if (get_platform_ids == nullptr || get_device_ids == nullptr) {
        out.error = "OpenCL loader is present but required symbols were not found";
        dlclose(lib);
        return out;
    }

    cl_uint platforms = 0;
    cl_int rc = get_platform_ids(0, nullptr, &platforms);
    if (rc != CL_SUCCESS) {
        out.error = "clGetPlatformIDs failed with code " + std::to_string(rc);
        dlclose(lib);
        return out;
    }
    out.platform_count = platforms;
    if (platforms == 0) {
        out.error = "OpenCL loader is present but no platforms were reported";
        dlclose(lib);
        return out;
    }

    std::vector<cl_platform_id> ids(platforms);
    rc = get_platform_ids(platforms, ids.data(), nullptr);
    if (rc != CL_SUCCESS) {
        out.error = "clGetPlatformIDs platform fetch failed with code " + std::to_string(rc);
        dlclose(lib);
        return out;
    }

    for (cl_platform_id platform : ids) {
        cl_uint gpu_count = 0;
        rc = get_device_ids(platform, CL_DEVICE_TYPE_GPU, 0, nullptr, &gpu_count);
        if (rc == CL_SUCCESS) {
            out.gpu_device_count += gpu_count;
        }
        cl_uint cpu_count = 0;
        rc = get_device_ids(platform, CL_DEVICE_TYPE_CPU, 0, nullptr, &cpu_count);
        if (rc == CL_SUCCESS) {
            out.cpu_device_count += cpu_count;
        }
    }

    out.probe_ok = true;
    dlclose(lib);
#else
    out.error = "OpenCL runtime probe is only implemented for Linux in this build";
#endif

    return out;
}

}  // namespace

std::string backend_info_json() {
    const OpenClProbe opencl = probe_opencl();
    std::string out = "{";
    bool first = true;
    add_str(out, first, "native_core", "c++20");
#ifdef MAGIC_GEO_HAS_OPENMP
    add_bool(out, first, "openmp_enabled", true);
#else
    add_bool(out, first, "openmp_enabled", false);
#endif
#ifdef _OPENMP
    add_int(out, first, "openmp_max_threads", omp_get_max_threads());
#else
    add_int(out, first, "openmp_max_threads", 1);
#endif
    add_bool(out, first, "opencl_loader_found", opencl.loader_found);
    add_bool(out, first, "opencl_probe_ok", opencl.probe_ok);
    add_int(out, first, "opencl_platform_count", static_cast<int>(opencl.platform_count));
    add_int(out, first, "opencl_gpu_device_count", static_cast<int>(opencl.gpu_device_count));
    add_int(out, first, "opencl_cpu_device_count", static_cast<int>(opencl.cpu_device_count));
    add_bool(out, first, "opencl_available", opencl.probe_ok && (opencl.gpu_device_count + opencl.cpu_device_count > 0));
    add_str(out, first, "opencl_error", opencl.error);
    add_str(out, first, "active_backend", "cpu");
    out += "}";
    return out;
}

}  // namespace magic_geo
