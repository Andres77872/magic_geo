#include "magic_geo/native.hpp"

#include "engine/internal.hpp"
#include "engine/world.hpp"
#include "opencl_compute.hpp"

namespace magic_geo {

std::string generate_world_json(const Params& params) {
    ComputeOptions cpu_options;
    cpu_options.compute_backend = 1;
    return generate_world_json(params, cpu_options);
}

std::string generate_world_json(
    const Params& params,
    const ComputeOptions& compute_options
) {
    detail::validate_compute_options(compute_options);
    detail::validate_params(params);
    detail::ScopedThreadConfiguration thread_configuration(params.threads);
    detail::ComputeSession compute_session(params, compute_options);
    return detail::serialize_world(params, detail::simulate_world(params));
}

}  // namespace magic_geo
