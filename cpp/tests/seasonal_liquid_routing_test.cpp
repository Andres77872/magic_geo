#include "seasonal_liquid_routing.hpp"

#include <algorithm>
#include <array>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

using namespace magic_geo::detail;

namespace {
constexpr std::size_t planned_groups = 30;
constexpr std::size_t maximum_capture_attempts = 21;
constexpr std::size_t maximum_route_attempts = 26;
constexpr std::uint64_t fixture_revision = 73;
constexpr double two53 = 9007199254740992.0;
constexpr double two53plus2 = 9007199254740994.0;

std::string quoted(const std::string& value) {
    std::ostringstream out;
    out << '"';
    for (const unsigned char c : value) {
        if (c == '"' || c == '\\') out << '\\' << c;
        else if (c < 0x20) out << "\\u" << std::hex << std::setw(4)
                                << std::setfill('0') << static_cast<unsigned>(c) << std::dec;
        else out << c;
    }
    out << '"';
    return out.str();
}

std::string bits(double value) {
    std::array<unsigned char, sizeof(double)> raw{};
    std::memcpy(raw.data(), &value, sizeof value);
    std::ostringstream out;
    // Object bytes are a read-only witness, not an arithmetic interpretation.
    for (unsigned char c : raw) out << std::hex << std::setw(2)
                                  << std::setfill('0') << static_cast<unsigned>(c);
    return out.str();
}

std::vector<Cell> baseline_cells() {
    std::vector<Cell> cells(6);
    constexpr std::array<double, 6> areas{1e-6, 2e-6, 4e-6, 8e-6, 16e-6, 32e-6};
    constexpr std::array<double, 6> heights{60, 50, 40, 30, 20, 10};
    constexpr std::array<int, 6> receivers{2, 2, 3, 4, 5, -1};
    const std::array<std::vector<int>, 6> neighbors{
        std::vector<int>{2}, {2}, {0, 1, 3}, {2, 4}, {3, 5}, {4}};
    for (std::size_t i = 0; i < cells.size(); ++i) {
        auto& cell = cells[i];
        cell.id = static_cast<int>(i);
        cell.area_km2 = areas[i];
        cell.elevation_m = heights[i];
        cell.filled_elevation_m = heights[i];
        cell.hydrologic_surface_elevation_m = heights[i];
        cell.hydrologic_surface_conditioned = true;
        cell.hydrologic_flow_slope = i == 5 ? 0 : 1;
        cell.flow_to = receivers[i];
        cell.neighbors = neighbors[i];
        cell.precipitation_mm_y = 120;
        cell.precipitation_monthly_mm.fill(10);
        cell.temperature_c = 8;
        cell.p = {1, 0, 0};
    }
    cells[3].is_lake = true;
    cells[3].water_body = 4;
    cells[3].water_depth_m = 2;
    cells[3].depression_component_id = 0;
    cells[3].depression_sink_cell_id = 3;
    cells[3].lake_fill_fraction = 0.5;
    cells[5].is_water = true;
    cells[5].water_body = 1;
    cells[5].water_depth_m = 3;
    return cells;
}

SeasonalLiquidMassRequest main_request() {
    return {"finite-event", true, 1000,
            {{"left", 0, 1}, {"right", 1, 2}, {"below-lake", 4, 4}}};
}

struct CaptureSpec {
    std::string key;
    std::vector<Cell> cells;
    SeasonalLiquidRoutingLimits limits;
    std::string expected_failure;
    std::optional<SeasonalLiquidMassRequest> declared_unused_request;
};
struct RouteSpec {
    std::string label;
    std::string graph_key;
    SeasonalLiquidMassRequest request;
    std::string expected_failure;
    bool expected_request_retained = true;
};
struct Group {
    int id;
    std::string name;
    std::vector<CaptureSpec> captures;
    std::vector<RouteSpec> routes;
};

std::vector<Group> fixed_plan() {
    const auto original = baseline_cells();
    const auto request = main_request();
    const SeasonalLiquidRoutingLimits defaults{};
    std::vector<Group> plan;
    auto accepted = [&](int id, std::string name, std::string graph_key,
                        SeasonalLiquidMassRequest supplied) -> Group& {
        plan.push_back({id, std::move(name), {},
                        {{"route", std::move(graph_key), std::move(supplied), ""}}});
        return plan.back();
    };
    auto rejected_capture = [&](int id, std::string name, std::vector<Cell> cells,
                                SeasonalLiquidRoutingLimits limits = {}) -> Group& {
        plan.push_back({id, std::move(name),
                        {{"capture", std::move(cells), limits, "invalid_graph", std::nullopt}}, {}});
        return plan.back();
    };
    auto rejected_route = [&](int id, std::string name,
                              SeasonalLiquidMassRequest supplied) -> Group& {
        plan.push_back({id, std::move(name), {},
                        {{"route", "baseline", std::move(supplied), "invalid_input"}}});
        return plan.back();
    };

    accepted(1, "unequal-area branch merge and distinct wet terminals", "baseline", request)
        .captures.push_back({"baseline", original, defaults, "", std::nullopt});
    auto cells = original;
    cells[3].lake_overflows = true;
    accepted(2, "overflowing lake still stops delivery", "overflowing-lake", request)
        .captures.push_back({"overflowing-lake", cells, defaults, "", std::nullopt});
    cells = original;
    cells[5].is_water = false;
    cells[5].water_body = 0;
    cells[5].water_depth_m = 0;
    accepted(3, "dry terminal", "dry", request)
        .captures.push_back({"dry", cells, defaults, "", std::nullopt});
    auto changed = request;
    changed.sources.clear();
    accepted(4, "explicit complete empty supply", "baseline", changed);
    changed = request;
    changed.sources.push_back({"known-zero", 2, 0});
    accepted(5, "known zero exposed source", "baseline", changed);
    changed = request;
    changed.sources = {{"large", 0, two53}, {"unit", 1, 1}};
    accepted(6, "two to the fifty-third plus one rounded loss", "baseline", changed);
    accepted(7, "immutable capture and retained-input mutation detection", "baseline", request);
    cells = original;
    cells[0].precipitation_mm_y = 9000;
    cells[0].precipitation_monthly_mm.fill(750);
    accepted(8, "original annual precipitation is irrelevant", "changed-P", request)
        .captures.push_back({"changed-P", cells, defaults, "", std::nullopt});
    changed = request;
    changed.sources = {{"large", 0, two53}, {"unit-a", 0, 1}, {"unit-b", 0, 1}};
    auto& reorder = accepted(9, "source permutation retains ideal mass", "baseline", changed);
    reorder.routes[0].label = "large-first";
    changed.sources = {{"unit-a", 0, 1}, {"unit-b", 0, 1}, {"large", 0, two53}};
    reorder.routes.push_back({"small-first", "baseline", changed, ""});
    auto& repeat = accepted(10, "repeated pure call is deterministic", "baseline", request);
    repeat.routes[0].label = "first";
    repeat.routes.push_back({"second", "baseline", request, ""});

    rejected_capture(11, "empty cell list", {});
    cells = original;
    cells[2].id = 99;
    rejected_capture(12, "noncanonical cell id", cells);
    cells = original;
    cells[0].flow_to = 6;
    rejected_capture(13, "receiver out of range", cells);
    cells = original;
    cells[0].flow_to = 0;
    rejected_capture(14, "self receiver", cells);
    cells = original;
    cells[0].neighbors.clear();
    cells[2].neighbors = {1, 3};
    rejected_capture(15, "receiver absent from reciprocal neighbor graph", cells);
    cells = original;
    cells[5].flow_to = 3;
    cells[5].neighbors.push_back(3);
    cells[3].neighbors.push_back(5);
    cells[5].hydrologic_flow_slope = 1;
    changed = request;
    changed.sources.clear();
    rejected_capture(16, "whole raw graph cycle despite complete zero supply", cells)
        .captures[0].declared_unused_request = changed;
    cells = original;
    cells[3].is_water = true;
    rejected_capture(17, "contradictory marine and lake flags", cells);
    cells = original;
    cells[0].area_km2 = 0;
    rejected_capture(18, "nonpositive canonical area", cells);
    cells = original;
    cells[0].area_km2 = std::numeric_limits<double>::max();
    rejected_capture(19, "area conversion overflow", cells).captures[0].expected_failure = "arithmetic_refusal";
    cells = original;
    cells[0].neighbors.push_back(2);
    auto& neighbors = rejected_capture(20, "duplicate and out-of-range neighbors", cells);
    neighbors.captures[0].key = "duplicate";
    cells = original;
    cells[0].neighbors.push_back(6);
    neighbors.captures.push_back({"out-of-range", cells, defaults, "invalid_graph", std::nullopt});
    auto limits = defaults;
    limits.max_cells = 5;
    auto& cell_cap = rejected_capture(21, "cell admission and configured hard caps", original, limits);
    cell_cap.captures[0].key = "cell-admission-cap";
    limits = defaults;
    limits.max_cells = 200001;
    cell_cap.captures.push_back({"configured-hard-cap", original, limits, "invalid_limits", std::nullopt});
    limits = defaults;
    limits.max_neighbor_entries = 9;
    rejected_capture(22, "neighbor incidence admission cap", original, limits);

    changed = request;
    changed.sources[0].cell_id = 6;
    auto& source_coverage = rejected_route(23, "unknown source cell and incomplete declaration", changed);
    source_coverage.routes[0].label = "unknown-cell";
    changed = request;
    changed.complete_source_list = false;
    source_coverage.routes.push_back({"incomplete-source-list", "baseline", changed, "invalid_input"});
    changed = request;
    changed.sources[0].cell_id = 3;
    changed.sources[0].mass_kg = 0;
    rejected_route(24, "wet source remains invalid at known zero", changed);
    changed = request;
    changed.sources[1].id = changed.sources[0].id;
    auto& identifiers = rejected_route(25, "duplicate and empty source identifiers", changed);
    identifiers.routes[0].label = "duplicate-source-id";
    changed = request;
    changed.sources[0].id.clear();
    identifiers.routes.push_back({"empty-source-id", "baseline", changed, "invalid_input", false});
    changed = request;
    changed.sources[0].mass_kg = -1;
    auto& invalid_mass = rejected_route(26, "negative and nonfinite source masses", changed);
    invalid_mass.routes[0].label = "negative";
    changed.sources[0].mass_kg = std::numeric_limits<double>::quiet_NaN();
    invalid_mass.routes.push_back({"nonfinite", "baseline", changed, "invalid_input"});
    changed = request;
    changed.reference_water_density_kg_m3 = 0;
    auto& density = rejected_route(27, "zero and nonfinite reference density", changed);
    density.routes[0].label = "zero";
    changed.reference_water_density_kg_m3 = std::numeric_limits<double>::infinity();
    density.routes.push_back({"nonfinite", "baseline", changed, "invalid_input"});
    limits = defaults;
    limits.max_sources = 2;
    auto& source_cap = rejected_route(28, "source count admission cap", request);
    source_cap.routes[0].graph_key = "source-cap";
    source_cap.routes[0].expected_request_retained = false;
    source_cap.captures.push_back({"source-cap", original, limits, "", std::nullopt});
    changed = request;
    changed.sources = {{"large-a", 0, std::numeric_limits<double>::max()},
                       {"large-b", 0, std::numeric_limits<double>::max()}};
    auto& arithmetic = rejected_route(29, "accumulation overflow and positive depth underflow", changed);
    arithmetic.routes[0].label = "overflow";
    arithmetic.routes[0].expected_failure = "arithmetic_refusal";
    cells = original;
    for (auto& cell : cells) cell.area_km2 = 1e300;
    arithmetic.captures.push_back({"underflow", cells, defaults, "", std::nullopt});
    changed = request;
    changed.sources = {{"small-positive", 0, 1e-300}};
    arithmetic.routes.push_back({"positive-depth-underflow", "underflow", changed, "arithmetic_refusal"});
    limits = defaults;
    limits.max_arithmetic_groups = 4;
    auto& work = rejected_route(30, "late arithmetic work cap retains only observations", request);
    work.routes[0].graph_key = "work-cap";
    work.routes[0].expected_failure = "work_cap";
    work.captures.push_back({"work-cap", original, limits, "", std::nullopt});
    return plan;
}

// Observe actual caller object storage and separately owned vector elements.
// No Cell is copied and substituted for the original during the read-only check.
struct CellSnapshot {
    std::vector<unsigned char> object_bytes;
    std::vector<std::vector<int>> neighbors, edge_neighbors;
    std::vector<std::vector<unsigned char>> vertices;
    explicit CellSnapshot(const std::vector<Cell>& cells) {
        const auto* bytes = reinterpret_cast<const unsigned char*>(cells.data());
        if (!cells.empty()) object_bytes.assign(bytes, bytes + cells.size() * sizeof(Cell));
        for (const auto& cell : cells) {
            neighbors.push_back(cell.neighbors);
            edge_neighbors.push_back(cell.control_volume_edge_neighbor_ids);
            std::vector<unsigned char> vertex_bytes(cell.control_volume_vertices.size() * sizeof(Vec3));
            if (!vertex_bytes.empty()) std::memcpy(vertex_bytes.data(), cell.control_volume_vertices.data(), vertex_bytes.size());
            vertices.push_back(std::move(vertex_bytes));
        }
    }
    bool equals(const std::vector<Cell>& cells) const {
        const CellSnapshot after(cells);
        return object_bytes == after.object_bytes && neighbors == after.neighbors &&
               edge_neighbors == after.edge_neighbors && vertices == after.vertices;
    }
};

std::string capture_json(const CaptureSpec& capture) {
    std::ostringstream out;
    out << "{\"key\":" << quoted(capture.key)
        << ",\"input\":" << seasonal_liquid_routing_input_json(capture.cells, fixture_revision, capture.limits)
        << ",\"expected_failure\":" << quoted(capture.expected_failure)
        << ",\"caller_precipitation_bits\":[";
    for (std::size_t i = 0; i < capture.cells.size(); ++i) {
        if (i) out << ',';
        out << quoted(bits(capture.cells[i].precipitation_mm_y));
    }
    out << "],\"declared_unused_request\":";
    if (capture.declared_unused_request) out << seasonal_liquid_mass_request_json(*capture.declared_unused_request);
    else out << "null";
    out << '}';
    return out.str();
}

void emit_group_inventory(const Group& group) {
    std::cout << "{\"record\":\"case_inventory\",\"group\":" << group.id
              << ",\"name\":" << quoted(group.name) << ",\"captures\":[";
    for (std::size_t i = 0; i < group.captures.size(); ++i) {
        if (i) std::cout << ',';
        std::cout << capture_json(group.captures[i]);
    }
    std::cout << "],\"routes\":[";
    for (std::size_t i = 0; i < group.routes.size(); ++i) {
        const auto& route = group.routes[i];
        if (i) std::cout << ',';
        std::cout << "{\"label\":" << quoted(route.label) << ",\"graph_key\":" << quoted(route.graph_key)
                  << ",\"request\":" << seasonal_liquid_mass_request_json(route.request)
                  << ",\"expected_failure\":" << quoted(route.expected_failure)
                  << ",\"expected_request_retained\":" << (route.expected_request_retained ? "true" : "false") << '}';
    }
    std::cout << "]}" << '\n';
}

bool contains(SeasonalLiquidInterval interval, double exact) {
    return std::isfinite(interval.lower) && std::isfinite(interval.upper) &&
           interval.lower <= exact && exact <= interval.upper;
}
bool encloses_odd_two53plus1(SeasonalLiquidInterval interval) {
    // The adjacent binary64 endpoints independently bracket the exact odd integer.
    return std::isfinite(interval.lower) && std::isfinite(interval.upper) &&
           interval.lower <= two53 && interval.upper >= two53plus2;
}

struct Driver {
    std::size_t captures = 0, routes = 0, checks = 0, failures = 0;
    std::size_t groups_completed = 0, unavailable_groups = 0;
    std::size_t unavailable_capability_subcontrols = 0;
    std::map<std::string, SeasonalLiquidRoutingGraph> graphs;
    std::map<std::string, std::string> graph_captures;
    std::map<std::string, const std::vector<Cell>*> graph_callers;
    std::optional<SeasonalLiquidRoutingReceipt> baseline_receipt;

    void check(int group, const std::string& label, bool passed) {
        ++checks;
        if (!passed) ++failures;
        std::cout << "{\"record\":\"check\",\"group\":" << group
                  << ",\"sequence\":" << checks << ",\"label\":" << quoted(label)
                  << ",\"passed\":" << (passed ? "true" : "false") << "}\n";
    }

    void capture(int group, const CaptureSpec& spec) {
        if (captures >= maximum_capture_attempts) {
            check(group, "capture hard call limit prevents invocation", false);
            return;
        }
        ++captures;
        std::cout << "{\"record\":\"capture_attempt\",\"group\":" << group
                  << ",\"attempt\":" << captures << ",\"context\":" << capture_json(spec) << "}\n";
        const CellSnapshot before(spec.cells);
        try {
            auto graph = capture_seasonal_liquid_routing_graph(spec.cells, fixture_revision, spec.limits);
            const auto serialized = seasonal_liquid_routing_graph_json(graph);
            std::cout << "{\"record\":\"capture_result\",\"group\":" << group
                      << ",\"key\":" << quoted(spec.key) << ",\"accepted\":true,\"graph\":" << serialized << "}\n";
            check(group, spec.key + " expected capture outcome", spec.expected_failure.empty());
            check(group, spec.key + " captured identity matches caller", graph.matches(spec.cells));
            graph_captures.emplace(spec.key, capture_json(spec));
            graph_callers.emplace(spec.key, &spec.cells);
            graphs.emplace(spec.key, std::move(graph));
        } catch (const SeasonalLiquidRoutingError& error) {
            std::cout << "{\"record\":\"capture_result\",\"group\":" << group
                      << ",\"key\":" << quoted(spec.key) << ",\"accepted\":false,\"failure_code\":"
                      << quoted(error.code) << ",\"detail\":" << quoted(error.what()) << ",\"graph\":null}\n";
            check(group, spec.key + " exact typed capture refusal", !spec.expected_failure.empty() && error.code == spec.expected_failure);
        } catch (const std::exception& error) {
            std::cout << "{\"record\":\"unexpected_capture_exception\",\"group\":" << group
                      << ",\"detail\":" << quoted(error.what()) << "}\n";
            check(group, spec.key + " capture uses typed refusal", false);
        }
        check(group, spec.key + " capture and match leave actual caller cells unchanged", before.equals(spec.cells));
    }

    std::optional<SeasonalLiquidRoutingReceipt> route(int group, const RouteSpec& spec) {
        const auto found = graphs.find(spec.graph_key);
        if (found == graphs.end()) {
            std::cout << "{\"record\":\"route_unavailable\",\"group\":" << group
                      << ",\"label\":" << quoted(spec.label) << ",\"reason\":\"capture did not produce graph\"}\n";
            check(group, spec.label + " graph available", false);
            return std::nullopt;
        }
        if (routes >= maximum_route_attempts) {
            check(group, "route hard call limit prevents invocation", false);
            return std::nullopt;
        }
        ++routes;
        const auto& graph = found->second;
        const auto& caller = *graph_callers.at(spec.graph_key);
        const CellSnapshot before(caller);
        const auto graph_before = seasonal_liquid_routing_graph_json(graph);
        const auto request_before = seasonal_liquid_mass_request_json(spec.request);
        std::cout << "{\"record\":\"route_attempt\",\"group\":" << group
                  << ",\"attempt\":" << routes << ",\"label\":" << quoted(spec.label)
                  << ",\"captured_context\":" << graph_captures.at(spec.graph_key)
                  << ",\"caller_context\":" << seasonal_liquid_routing_input_json(caller, fixture_revision, graph.limits())
                  << ",\"graph\":" << graph_before << ",\"request\":" << request_before << "}\n";
        try {
            const auto receipt = route_seasonal_liquid_mass(graph, spec.request);
            std::cout << "{\"record\":\"route_receipt\",\"group\":" << group
                      << ",\"attempt\":" << routes << ",\"label\":" << quoted(spec.label)
                      << ",\"receipt\":" << seasonal_liquid_routing_receipt_json(receipt) << "}\n";
            check(group, spec.label + " actual caller cells unchanged", before.equals(caller));
            check(group, spec.label + " captured graph unchanged", graph_before == seasonal_liquid_routing_graph_json(graph));
            check(group, spec.label + " request unchanged", request_before == seasonal_liquid_mass_request_json(spec.request));
            check(group, spec.label + " graph revision retained", receipt.graph_revision == fixture_revision);
            check(group, spec.label + " final availability agrees with acceptance", receipt.accepted == receipt.final.has_value());
            check(group, spec.label + " bounded work observations", receipt.work.arithmetic_groups_started <= graph.limits().max_arithmetic_groups &&
                  receipt.work.sources_completed <= spec.request.sources.size() &&
                  receipt.work.edges_completed <= graph.nodes().size() &&
                  receipt.work.conversions_completed <= graph.nodes().size() &&
                  receipt.work.terminals_completed <= graph.nodes().size());
            if (spec.expected_failure.empty()) {
                check(group, spec.label + " accepted with no failure", receipt.accepted && receipt.failure_code.empty());
                check(group, spec.label + " admitted request retained exactly", receipt.request.has_value() &&
                      seasonal_liquid_mass_request_json(*receipt.request) == request_before);
                check(group, spec.label + " all declared work completed", receipt.work.sources_completed == spec.request.sources.size() &&
                      receipt.work.edges_completed == 4 && receipt.work.conversions_completed == 6 &&
                      receipt.work.terminals_completed == 2);
            } else {
                check(group, spec.label + " exact route refusal and absent final", !receipt.accepted && !receipt.final &&
                      receipt.failure_code == spec.expected_failure);
                if (spec.expected_failure == "invalid_input")
                    check(group, spec.label + " malformed input starts no arithmetic", receipt.work.arithmetic_groups_started == 0 &&
                          receipt.work.sources_completed == 0 && receipt.work.edges_completed == 0 &&
                          receipt.work.conversions_completed == 0 && receipt.work.terminals_completed == 0);
                check(group, spec.label + " request retained only after bounded admission", !spec.expected_request_retained ? !receipt.request :
                      receipt.request.has_value() && seasonal_liquid_mass_request_json(*receipt.request) == request_before);
            }
            return receipt;
        } catch (const std::exception& error) {
            std::cout << "{\"record\":\"unexpected_route_exception\",\"group\":" << group
                      << ",\"attempt\":" << routes << ",\"detail\":" << quoted(error.what()) << "}\n";
            check(group, spec.label + " route returns receipt", false);
            check(group, spec.label + " exceptional route caller unchanged", before.equals(caller));
            return std::nullopt;
        }
    }

    void known_totals(int group, const SeasonalLiquidRoutingReceipt& receipt,
                      const std::array<double, 6>& mass, const std::array<double, 6>& depth,
                      double total, SeasonalLiquidTerminal last = SeasonalLiquidTerminal::marine) {
        if (!receipt.final) return;
        const auto& result = *receipt.final;
        check(group, "complete per-cell table", result.cells.size() == mass.size());
        check(group, "independent source and terminal totals", result.represented_source_total_kg == total &&
              result.represented_terminal_total_kg == total && contains(result.exact_source_total_kg, total) &&
              contains(result.exact_terminal_total_kg, total) && contains(result.exact_represented_terminal_sum_kg, total));
        check(group, "global difference enclosures contain independent zero", contains(result.source_sum_difference_kg, 0) &&
              contains(result.terminal_sum_difference_kg, 0) && contains(result.terminal_total_minus_source_mass_kg, 0));
        check(group, "all and only terminal ids retained", result.terminal_cell_ids == std::vector<int>({3, 5}));
        constexpr std::array<int, 6> receivers{2, 2, 3, -1, 5, -1};
        for (std::size_t i = 0; i < result.cells.size() && i < mass.size(); ++i) {
            const auto& cell = result.cells[i];
            const auto terminal = i == 3 ? SeasonalLiquidTerminal::lake :
                                  i == 5 ? last : SeasonalLiquidTerminal::none;
            const auto label = "cell " + std::to_string(i);
            check(group, label + " independent routing identity", cell.cell_id == static_cast<int>(i) &&
                  cell.effective_receiver == receivers[i] && cell.terminal == terminal);
            check(group, label + " independent known mass and enclosure", cell.represented_throughput_mass_kg == mass[i] &&
                  contains(cell.exact_source_mass_kg, mass[i]) && contains(cell.representation_difference_kg, 0));
            check(group, label + " independent canonical depth enclosed", cell.represented_depth_mm == depth[i] &&
                  contains(cell.exact_depth_mm, depth[i]) &&
                  contains(cell.represented_mass_exact_depth_mm, depth[i]) &&
                  contains(cell.depth_conversion_difference_mm, cell.represented_depth_mm - depth[i]) &&
                  contains(cell.depth_total_difference_mm, cell.represented_depth_mm - depth[i]));
        }
    }

    void semantics(int group, const std::vector<SeasonalLiquidRoutingReceipt>& receipts) {
        constexpr std::array<double, 6> main_mass{1, 2, 3, 3, 4, 4};
        constexpr std::array<double, 6> main_depth{1, 1, 0.75, 0.375, 0.25, 0.125};
        if (receipts.empty()) return;
        const auto& receipt = receipts[0];
        if (group == 1 || group == 2 || group == 3 || group == 5 || group == 7 || group == 8 || group == 10)
            known_totals(group, receipt, main_mass, main_depth, 7,
                         group == 3 ? SeasonalLiquidTerminal::dry : SeasonalLiquidTerminal::marine);
        if (group == 4) known_totals(group, receipt, {}, {}, 0);
        if (group == 1 && receipt.accepted) {
            baseline_receipt = receipt;
            const auto& graph = graphs.at("baseline");
            constexpr std::array<double, 6> canonical_area{1, 2, 4, 8, 16, 32};
            check(group, "whole original graph topological table", graph.topological_order().size() == 6);
            check(group, "raw lake outgoing retained and effective lake cut", graph.nodes().size() == 6 &&
                  graph.nodes()[3].original_receiver == 4 && graph.nodes()[3].effective_receiver == -1);
            for (std::size_t i = 0; i < graph.nodes().size() && i < canonical_area.size(); ++i)
                check(group, "canonical area " + std::to_string(i), graph.nodes()[i].area_m2 == canonical_area[i]);
        }
        if (group == 6 && receipt.final && receipt.final->cells.size() == 6) {
            const auto& result = *receipt.final;
            check(group, "odd exact source total independently enclosed", encloses_odd_two53plus1(result.exact_source_total_kg));
            check(group, "source represented sum loses one kg", result.represented_source_total_kg == two53 &&
                  contains(result.source_sum_difference_kg, -1));
            for (int id : {2, 3}) {
                const auto& cell = result.cells[static_cast<std::size_t>(id)];
                check(group, "merge loss at cell " + std::to_string(id), cell.represented_throughput_mass_kg == two53 &&
                      encloses_odd_two53plus1(cell.exact_source_mass_kg) &&
                      contains(cell.representation_difference_kg, -1) &&
                      cell.representation_difference_kg.lower < 0);
            }
            check(group, "terminal loss retained independently", result.represented_terminal_total_kg == two53 &&
                  contains(result.terminal_total_minus_source_mass_kg, -1) &&
                  result.terminal_total_minus_source_mass_kg.lower < 0);
            check(group, "terminal ideal mass and represented aggregation are separate", encloses_odd_two53plus1(result.exact_terminal_total_kg) &&
                  contains(result.exact_represented_terminal_sum_kg, two53) && contains(result.terminal_sum_difference_kg, 0));
        }
        if ((group == 7 || group == 8) && baseline_receipt)
            check(group, "unchanged routing receipt matches original capture", seasonal_liquid_routing_receipt_json(receipt) ==
                  seasonal_liquid_routing_receipt_json(*baseline_receipt));
        if (group == 9 && receipts.size() == 2 && receipts[0].final && receipts[1].final) {
            for (std::size_t i = 0; i < receipts.size(); ++i) {
                const auto& result = *receipts[i].final;
                const double represented = i == 0 ? two53 : two53plus2;
                const double difference = i == 0 ? -2 : 0;
                check(group, "permutation " + std::to_string(i) + " independently known exact total", contains(result.exact_source_total_kg, two53plus2));
                check(group, "permutation " + std::to_string(i) + " ordered represented sum", result.represented_source_total_kg == represented);
                check(group, "permutation " + std::to_string(i) + " retained sum and terminal error", contains(result.source_sum_difference_kg, difference) &&
                      contains(result.terminal_total_minus_source_mass_kg, difference));
                check(group, "permutation " + std::to_string(i) + " independent delivered terminal mass", result.represented_terminal_total_kg == represented &&
                      result.cells.size() == 6 && result.cells[3].represented_throughput_mass_kg == represented &&
                      result.cells[5].represented_throughput_mass_kg == 0);
            }
        }
        if (group == 10 && receipts.size() == 2)
            check(group, "repeated calls retain identical full receipts", seasonal_liquid_routing_receipt_json(receipts[0]) ==
                  seasonal_liquid_routing_receipt_json(receipts[1]));
        if (group == 30) {
            check(group, "late cap has an exact observed completed prefix", receipt.work.sources_completed == 3 &&
                  receipt.work.edges_completed == 1 && receipt.work.arithmetic_groups_started == 4);
            check(group, "late refusal makes complete totals unavailable", !receipt.accepted && !receipt.final);
        }
    }
};

void emit_capability_inventory() {
    std::cout << "{\"record\":\"capability_subcontrol_inventory\",\"group\":0,"
                 "\"name\":\"non-nearest rounding refusal with restoration\",\"graph_key\":\"baseline\","
                 "\"rounding_mode\":\"FE_UPWARD\",\"maximum_capture_attempts\":0,\"maximum_route_attempts\":1,"
                 "\"expected_failure\":\"capability_unavailable\",\"request\":"
              << seasonal_liquid_mass_request_json(main_request()) << "}\n";
}

void non_nearest_subcontrol(Driver& driver) {
    if (driver.routes >= maximum_route_attempts) {
        driver.check(0, "capability route hard call limit prevents invocation", false);
        return;
    }
    const auto found = driver.graphs.find("baseline");
    const auto request = main_request();
    const auto fallback_caller = baseline_cells();
    const auto& caller = found == driver.graphs.end() ? fallback_caller : *driver.graph_callers.at("baseline");
    const CellSnapshot before(caller);
    const auto graph_before = found == driver.graphs.end() ? "null" : seasonal_liquid_routing_graph_json(found->second);
    const auto request_before = seasonal_liquid_mass_request_json(request);
    const int original_rounding = std::fegetround();
    struct RoundingRestoration {
        int original;
        bool restored = false;
        ~RoundingRestoration() { if (!restored && original != -1) std::fesetround(original); }
        bool restore() {
            restored = original != -1 && std::fesetround(original) == 0 && std::fegetround() == original;
            return restored;
        }
    } restoration{original_rounding};
    const bool switched = original_rounding != -1 && std::fesetround(FE_UPWARD) == 0;
    if (!switched) {
        restoration.restore();
        ++driver.unavailable_capability_subcontrols;
        std::cout << "{\"record\":\"capability_subcontrol_unavailable\",\"reason\":\"FE_UPWARD cannot be selected\"}\n";
        return;
    }
    // All observations under the modified environment are buffered until after
    // restoration; route() is not used because it emits numeric serialization.
    std::optional<SeasonalLiquidRoutingReceipt> receipt;
    std::string exception;
    std::optional<SeasonalLiquidRoutingCapability> capability;
    if (found != driver.graphs.end()) {
        try {
            capability = seasonal_liquid_routing_capability();
            ++driver.routes;
            receipt = route_seasonal_liquid_mass(found->second, request);
        }
        catch (const std::exception& error) { exception = error.what(); }
    }
    const bool restored = restoration.restore();
    std::cout << "{\"record\":\"capability_subcontrol\",\"group\":0,\"route_attempt\":";
    if (found != driver.graphs.end()) std::cout << driver.routes; else std::cout << "null";
    std::cout << ",\"rounding_restored\":" << (restored ? "true" : "false")
              << ",\"captured_context\":";
    if (found != driver.graphs.end()) std::cout << driver.graph_captures.at("baseline"); else std::cout << "null";
    std::cout << ",\"graph\":" << graph_before
              << ",\"request\":" << request_before
              << ",\"capability_available\":";
    if (capability) std::cout << (capability->available ? "true" : "false"); else std::cout << "null";
    std::cout << ",\"capability_reason\":" << quoted(capability ? capability->reason : "unavailable")
              << ",\"receipt\":";
    if (receipt) std::cout << seasonal_liquid_routing_receipt_json(*receipt); else std::cout << "null";
    std::cout << ",\"exception\":" << quoted(exception) << "}\n";
    driver.check(0, "rounding mode restored before observations", restored);
    driver.check(0, "non-nearest control leaves actual caller cells unchanged", before.equals(caller));
    driver.check(0, "non-nearest control leaves captured graph unchanged", found != driver.graphs.end() &&
                 graph_before == seasonal_liquid_routing_graph_json(found->second));
    driver.check(0, "non-nearest control leaves request unchanged", request_before == seasonal_liquid_mass_request_json(request));
    driver.check(0, "non-nearest capability explicitly unavailable", capability && !capability->available);
    driver.check(0, "non-nearest routing refuses without final or arithmetic", receipt && !receipt->accepted &&
                 !receipt->final && receipt->failure_code == "capability_unavailable" &&
                 receipt->work.arithmetic_groups_started == 0);
}
} // namespace

int main(int argc, char** argv) {
    std::cout.imbue(std::locale::classic());
    std::cout << std::setprecision(17);
    const bool inventory = argc == 2 && std::string(argv[1]) == "--inventory";
    if (argc != 1 && !inventory) {
        std::cout << "{\"record\":\"usage_error\",\"usage\":\"seasonal_liquid_routing_test [--inventory]\"}\n";
        return 2;
    }
    auto plan = fixed_plan();
    std::cout << "{\"record\":\"fixed_plan\",\"inventory_only\":" << (inventory ? "true" : "false")
              << ",\"control_groups\":" << planned_groups << ",\"maximum_capture_attempts\":" << maximum_capture_attempts
              << ",\"maximum_route_attempts_including_capability\":" << maximum_route_attempts
              << ",\"parameter_retries\":0,\"owner_commit_verified\":false,\"downstream_energy_available\":false}\n";
    for (const auto& group : plan) emit_group_inventory(group);
    emit_capability_inventory();
    if (inventory) {
        std::cout << "{\"record\":\"inventory_counters\",\"capture_attempts\":0,\"route_attempts\":0,\"capability_probes\":0}\n";
        return 0;
    }

    Driver driver;
    driver.check(0, "fixed thirty-group matrix", plan.size() == planned_groups);
    std::size_t capture_count = 0, route_count = 1;
    for (const auto& group : plan) { capture_count += group.captures.size(); route_count += group.routes.size(); }
    driver.check(0, "declared exact maximum capture count", capture_count == maximum_capture_attempts);
    driver.check(0, "declared exact maximum route count includes capability", route_count == maximum_route_attempts);
    if (plan.size() != planned_groups || capture_count != maximum_capture_attempts || route_count != maximum_route_attempts) {
        std::cout << "{\"record\":\"terminal_counters\",\"groups_completed\":0,\"capture_attempts\":0,"
                     "\"route_attempts\":0,\"parameter_retries\":0,\"plan_refused\":true}\n";
        return 1;
    }
    const auto capability = seasonal_liquid_routing_capability();
    std::cout << "{\"record\":\"platform_capability\",\"available\":" << (capability.available ? "true" : "false")
              << ",\"reason\":" << quoted(capability.reason) << "}\n";
    if (!capability.available) {
        for (const auto& group : plan) {
            ++driver.unavailable_groups;
            std::cout << "{\"record\":\"case_unavailable\",\"group\":" << group.id
                      << ",\"reason\":\"required arithmetic capability unavailable\"}\n";
        }
    } else {
        for (const auto& group : plan) {
            std::cout << "{\"record\":\"case_start\",\"group\":" << group.id << ",\"name\":" << quoted(group.name) << "}\n";
            for (const auto& spec : group.captures) driver.capture(group.id, spec);
            const auto baseline = driver.graphs.find("baseline");
            if (group.id == 7 && baseline != driver.graphs.end()) {
                const auto saved_graph = seasonal_liquid_routing_graph_json(baseline->second);
                // This is the same Cell vector passed to capture in group 1.
                auto& caller = plan.front().captures.front().cells;
                caller[0].hydrologic_surface_conditioned = false;
                const CellSnapshot flag_before(caller);
                const bool flag_matches = baseline->second.matches(caller);
                std::cout << "{\"record\":\"retained_identity_probe\",\"group\":7,"
                             "\"changed_field\":\"hydrologic_surface_conditioned\",\"caller_context\":"
                          << seasonal_liquid_routing_input_json(caller, fixture_revision, baseline->second.limits())
                          << ",\"matched\":" << (flag_matches ? "true" : "false") << "}\n";
                driver.check(7, "conditioned-surface flag mutation is detected", !flag_matches);
                driver.check(7, "flag matcher leaves actual caller unchanged", flag_before.equals(caller));
                caller[0].hydrologic_surface_conditioned = true;
                caller[0].area_km2 = 8e-6;
                const CellSnapshot before(caller);
                driver.check(7, "retained input mutation is detected", !baseline->second.matches(caller));
                driver.check(7, "matcher leaves actual mutated caller cells unchanged", before.equals(caller));
                driver.check(7, "caller mutation leaves immutable graph unchanged", saved_graph == seasonal_liquid_routing_graph_json(baseline->second));
            }
            if (group.id == 8 && baseline != driver.graphs.end()) {
                const auto& caller = group.captures.front().cells;
                const CellSnapshot before(caller);
                driver.check(8, "annual and monthly precipitation do not affect retained identity", baseline->second.matches(caller));
                driver.check(8, "precipitation matcher leaves actual caller cells unchanged", before.equals(caller));
            }
            std::vector<SeasonalLiquidRoutingReceipt> receipts;
            for (const auto& spec : group.routes) {
                auto result = driver.route(group.id, spec);
                if (result) receipts.push_back(std::move(*result));
            }
            driver.semantics(group.id, receipts);
            ++driver.groups_completed;
            std::cout << "{\"record\":\"case_end\",\"group\":" << group.id << "}\n";
        }
        non_nearest_subcontrol(driver);
    }
    driver.check(0, "capture attempts stay within the declared maximum", driver.captures <= maximum_capture_attempts);
    driver.check(0, "all route attempts including refusals stay within the declared maximum", driver.routes <= maximum_route_attempts);
    std::cout << "{\"record\":\"terminal_counters\",\"groups_completed\":" << driver.groups_completed
              << ",\"groups_unavailable\":" << driver.unavailable_groups << ",\"capture_attempts\":" << driver.captures
              << ",\"route_attempts\":" << driver.routes << ",\"checks\":" << driver.checks
              << ",\"failed_checks\":" << driver.failures
              << ",\"unavailable_capability_subcontrols\":" << driver.unavailable_capability_subcontrols
              << ",\"parameter_retries\":0}\n";
    if (!capability.available) return 77;
    if (driver.failures == 0 && driver.unavailable_capability_subcontrols != 0) return 77;
    return driver.failures == 0 ? 0 : 1;
}
