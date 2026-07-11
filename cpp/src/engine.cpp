#include "magic_geo/native.hpp"

#include "engine/internal.hpp"
#include "engine/world.hpp"

namespace magic_geo {

std::string generate_world_json(const Params& params) {
    detail::validate_params(params);
    detail::configure_threads(params);
    return detail::serialize_world(params, detail::simulate_world(params));
}

}  // namespace magic_geo
