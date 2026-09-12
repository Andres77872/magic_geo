#pragma once

#include "enthalpy_mesh.hpp"

#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace magic_geo::detail {

// Fixed material geometry over a declared interval. These are thermal nodes,
// not synthetic geographic Cells. All water is retained until another,
// separately qualified component explicitly changes the state/geometry.
enum class LayeredIceTopClosure {
    unspecified,
    prescribed_top_energy,
    prescribed_nonwater_top_capacity,
    coarse_combined_surface_atmosphere
};
enum class LayeredIceBottomBoundary { unspecified, insulated };
struct LayeredIceLayerInput {
    int layer_id = -1;
    // Mass/enthalpy are per complete horizontal footprint (coverage fraction
    // one). Density is prescribed bulk mass per layer volume; no subgrid ice
    // fraction is inferred from the amount of water supplied.
    double water_mass_kg_m2 = 0, enthalpy_j_m2 = 0;
    // H is relative to solid water and any top nonwater capacity at Tf. Thus
    // top H includes the declared nonwater/combined-atmosphere energy; interior
    // H is pure water energy. These totals must not be called ice-only energy.
    // A cold top starts at H=(Ctop+W*ci)*(T-Tf), not W*ci*(T-Tf).
    double density_kg_m3 = 0, conductivity_w_m_k = 0;
};
struct LayeredIceDeepInventoryInput {
    // Same full horizontal footprint as the active layers. H is pure-water
    // enthalpy relative to solid water at the freezing temperature.
    double water_mass_kg_m2 = 0, enthalpy_j_m2 = 0, density_kg_m3 = 0;
};
struct LayeredIceColumnInput {
    int cell_id = -1;
    double area_m2 = 0;
    LayeredIceTopClosure top_closure = LayeredIceTopClosure::unspecified;
    double top_nonwater_heat_capacity_j_m2_k = 0;
    double top_longwave_emissivity = 0, top_absorbed_shortwave_w_m2 = 0;
    std::vector<LayeredIceLayerInput> layers;
    // This same-area inventory is deliberately outside the thermal graph.
    // Its upper boundary is insulated; mass and enthalpy are not discarded.
    std::optional<LayeredIceDeepInventoryInput> deep_inventory;
};
struct LayeredIceLimits {
    std::size_t max_columns = 4096, max_layers_per_column = 32;
    std::size_t max_thermal_nodes = 16384, max_edges = 131072;
    std::size_t max_identifier_bytes = 96;
};
struct LayeredIceInput {
    std::string id;
    bool complete_horizontal_coverage_declared = false;
    LayeredIceBottomBoundary bottom_boundary = LayeredIceBottomBoundary::unspecified;
    cryosphere_prototype::WaterProperties water{};
    std::vector<LayeredIceColumnInput> columns;
    // IDs refer to horizontal columns; only their top nodes receive these.
    std::vector<EnergyTransportEdge> horizontal_climate_edges;
    LayeredIceLimits limits;
};
struct LayeredIceError : std::runtime_error {
    std::string code;
    LayeredIceError(std::string code, std::string detail);
};
struct LayeredIceCapability { bool available; std::string reason; };
LayeredIceCapability layered_ice_capability();

struct LayeredIceInventoryConversion {
    double represented_mass_kg = 0, represented_enthalpy_j = 0;
    EnthalpyMeshInterval exact_mass_kg{}, exact_enthalpy_j{};
    EnthalpyMeshInterval mass_conversion_difference_kg{}, enthalpy_conversion_difference_j{};
};
struct LayeredIceGeometryConversion {
    double represented_thickness_m = 0;
    EnthalpyMeshInterval exact_thickness_m{}, thickness_conversion_difference_m{};
    // rho * represented thickness minus supplied W, with retained operands.
    EnthalpyMeshInterval thickness_mass_reconstruction_difference_kg_m2{};
};
struct LayeredIceNode {
    int thermal_node_id = -1, cell_id = -1, layer_id = -1;
    LayeredIceGeometryConversion geometry;
    LayeredIceInventoryConversion inventory;
    double represented_depth_begin_m = 0, represented_depth_end_m = 0;
    EnthalpyMeshInterval exact_depth_begin_m{}, exact_depth_end_m{};
    EnthalpyMeshInterval depth_begin_difference_m{}, depth_end_difference_m{};
};
struct LayeredIceVerticalEdge {
    int first_thermal_node = -1, second_thermal_node = -1;
    double area_m2 = 0, first_thickness_m = 0, second_thickness_m = 0;
    double first_conductivity_w_m_k = 0, second_conductivity_w_m_k = 0;
    double represented_first_half_resistance_m2_k_w = 0;
    double represented_second_half_resistance_m2_k_w = 0;
    double represented_total_resistance_m2_k_w = 0, represented_conductance_w_k = 0;
    // Exact physical formula uses original W/rho, not rounded thickness.
    EnthalpyMeshInterval exact_first_half_resistance_m2_k_w{};
    EnthalpyMeshInterval exact_second_half_resistance_m2_k_w{};
    EnthalpyMeshInterval exact_total_resistance_m2_k_w{}, exact_conductance_w_k{};
    EnthalpyMeshInterval first_half_resistance_difference_m2_k_w{};
    EnthalpyMeshInterval second_half_resistance_difference_m2_k_w{};
    EnthalpyMeshInterval total_resistance_difference_m2_k_w{}, conductance_difference_w_k{};
};
struct LayeredIceDeepInventory {
    int cell_id = -1;
    LayeredIceGeometryConversion geometry;
    LayeredIceInventoryConversion inventory;
};
struct LayeredIceInventories {
    LayeredIceInventoryConversion active, deep, combined;
};

class LayeredIceGraph {
    struct Data;
    std::shared_ptr<const Data> data_;
    explicit LayeredIceGraph(std::shared_ptr<const Data>);
    friend LayeredIceGraph build_layered_ice_graph(const LayeredIceInput&);
public:
    const LayeredIceInput& input() const;
    const std::vector<LayeredIceNode>& nodes() const;
    const std::vector<int>& top_thermal_node_ids() const;
    const std::vector<LayeredIceVerticalEdge>& vertical_edges() const;
    const std::vector<LayeredIceDeepInventory>& deep_inventories() const;
    const LayeredIceInventories& inventories() const;
    // Copies the declared graph and initial state; performs no advancement.
    // This explicit path enables Cbase=0,W>0 admission in the thermal core.
    // Borrow the immutable canonical mesh without a request copy or rebuild.
    // The reference remains valid while this graph's shared data is retained.
    const EnthalpyMeshRequest& mesh_request() const;
    EnthalpyMeshRequest make_mesh_request(const EnthalpyMeshOptions&) const;
};

LayeredIceGraph build_layered_ice_graph(const LayeredIceInput&);
// Input serialization is nonvalidating and may be used before qualification.
std::string layered_ice_input_json(const LayeredIceInput&);
std::string layered_ice_graph_json(const LayeredIceGraph&);

} // namespace magic_geo::detail
