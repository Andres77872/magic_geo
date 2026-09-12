#include "finalized_layered_state.hpp"
#include "world.hpp"

namespace magic_geo::detail {

FinalizedLayeredStateInitialization GeographicFoundation::initialize_layered_state(
    FinalizedEnthalpyOptions options,const FinalizedLayeredStateRequest& request,
    std::uint64_t revision,SeasonalLiquidRoutingLimits routing_limits
) const {
    auto context=enthalpy_context(std::move(options),revision);
    auto routing=routing_graph(revision,routing_limits);
    return initialize_finalized_layered_state(context,routing,earth().cells,params(),revision,request);
}

} // namespace magic_geo::detail
