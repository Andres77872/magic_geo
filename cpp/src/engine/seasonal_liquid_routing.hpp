#pragma once

#include "types/core.hpp"
#include <cstdint>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace magic_geo::detail {

// Canonical finite masses on a captured receiver graph. This component never
// computes annual hydrology, changes lake geometry or authenticates an owner.
struct SeasonalLiquidInterval { double lower = 0, upper = 0; };
struct SeasonalLiquidRoutingLimits {
    std::size_t max_cells = 4096, max_neighbor_entries = 32768;
    std::size_t max_sources = 4096, max_identifier_bytes = 96;
    std::uint64_t max_arithmetic_groups = 65536;
};
struct SeasonalLiquidRoutingError : std::runtime_error {
    std::string code;
    SeasonalLiquidRoutingError(std::string code, std::string detail);
};
struct SeasonalLiquidRoutingCapability { bool available; std::string reason; };
SeasonalLiquidRoutingCapability seasonal_liquid_routing_capability();

enum class SeasonalLiquidTerminal { none, dry, lake, marine };
struct SeasonalLiquidRoutingNode {
    int cell_id = -1, original_receiver = -1, effective_receiver = -1;
    std::vector<int> neighbors;
    bool is_water = false, is_lake = false, is_closed_basin = false, lake_overflows = false;
    bool hydrologic_surface_conditioned = false;
    int water_body = 0, depression_component_id = -1, depression_sink_cell_id = -1;
    double area_km2 = 0, area_m2 = 0, elevation_m = 0, filled_elevation_m = 0;
    double hydrologic_surface_elevation_m = 0, hydrologic_flow_slope = 0;
    double water_depth_m = 0, lake_fill_fraction = 0;
    SeasonalLiquidInterval area_conversion_difference_m2;
    SeasonalLiquidTerminal terminal = SeasonalLiquidTerminal::none;
};
class SeasonalLiquidRoutingGraph {
    struct Data;
    std::shared_ptr<const Data> data_;
    explicit SeasonalLiquidRoutingGraph(std::shared_ptr<const Data>);
    friend SeasonalLiquidRoutingGraph capture_seasonal_liquid_routing_graph(
        const std::vector<Cell>&, std::uint64_t, SeasonalLiquidRoutingLimits);
public:
    const std::vector<SeasonalLiquidRoutingNode>& nodes() const;
    const std::vector<int>& topological_order() const;
    const SeasonalLiquidRoutingLimits& limits() const;
    std::uint64_t revision() const;
    bool matches(const std::vector<Cell>&) const;
};
SeasonalLiquidRoutingGraph capture_seasonal_liquid_routing_graph(
    const std::vector<Cell>&, std::uint64_t revision,
    SeasonalLiquidRoutingLimits = {});

struct SeasonalLiquidMassSource { std::string id; int cell_id = -1; double mass_kg = 0; };
struct SeasonalLiquidMassRequest {
    std::string id;
    bool complete_source_list = false;
    double reference_water_density_kg_m3 = 1000;
    std::vector<SeasonalLiquidMassSource> sources;
};
struct SeasonalLiquidRoutingWork {
    std::uint64_t arithmetic_groups_started = 0;
    std::size_t sources_completed = 0, edges_completed = 0;
    std::size_t conversions_completed = 0, terminals_completed = 0;
};
struct SeasonalLiquidCellReceipt {
    int cell_id = -1, effective_receiver = -1;
    SeasonalLiquidTerminal terminal = SeasonalLiquidTerminal::none;
    double represented_throughput_mass_kg = 0;
    SeasonalLiquidInterval exact_source_mass_kg, representation_difference_kg;
    double represented_depth_mm = 0; // Equivalent throughput depth, not storage.
    SeasonalLiquidInterval exact_depth_mm, represented_mass_exact_depth_mm;
    SeasonalLiquidInterval depth_conversion_difference_mm, depth_total_difference_mm;
};
struct SeasonalLiquidRoutingResult {
    std::vector<SeasonalLiquidCellReceipt> cells;
    std::vector<int> terminal_cell_ids;
    double represented_source_total_kg = 0, represented_terminal_total_kg = 0;
    SeasonalLiquidInterval exact_source_total_kg, exact_terminal_total_kg;
    SeasonalLiquidInterval exact_represented_terminal_sum_kg;
    SeasonalLiquidInterval source_sum_difference_kg, terminal_sum_difference_kg;
    // Difference from exact represented input masses, including routed rounding.
    SeasonalLiquidInterval terminal_total_minus_source_mass_kg;
};
struct SeasonalLiquidRoutingReceipt {
    bool accepted = false;
    std::string failure_code, detail;
    std::uint64_t graph_revision = 0;
    std::optional<SeasonalLiquidMassRequest> request;
    SeasonalLiquidRoutingWork work;
    std::optional<SeasonalLiquidRoutingResult> final;
};
SeasonalLiquidRoutingReceipt route_seasonal_liquid_mass(
    const SeasonalLiquidRoutingGraph&, const SeasonalLiquidMassRequest&);

// Input serializers perform no graph validation or routing; inventory may use
// them. Invalid numeric inputs are losslessly represented by binary64 bit tags.
std::string seasonal_liquid_routing_input_json(
    const std::vector<Cell>&, std::uint64_t, const SeasonalLiquidRoutingLimits&);
std::string seasonal_liquid_routing_graph_json(const SeasonalLiquidRoutingGraph&);
std::string seasonal_liquid_mass_request_json(const SeasonalLiquidMassRequest&);
std::string seasonal_liquid_routing_receipt_json(const SeasonalLiquidRoutingReceipt&);

} // namespace magic_geo::detail
