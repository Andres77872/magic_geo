#include "layered_ice_owner_metadata.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <charconv>
#include <limits>
#include <type_traits>

namespace magic_geo::detail {
LayeredIceOwnerMetadataError::LayeredIceOwnerMetadataError(std::string c, const char* detail)
    : std::runtime_error(detail), code(std::move(c)) {}
namespace {
using Shape = LayeredIceOwnerMetadataShape;
using Size = LayeredIceOwnerMetadataSize;
using Sink = LayeredIceOwnerMetadataSink;
using Buffer = std::array<std::byte,layered_ice_owner_metadata_buffer_bytes>;
[[noreturn]] void refuse(const char* code, const char* detail) {
    throw LayeredIceOwnerMetadataError(code, detail);
}
std::uint64_t plus(std::uint64_t a, std::uint64_t b) {
    if(b>UINT64_MAX-a) refuse("metadata_overflow","metadata size arithmetic overflow");
    return a+b;
}
std::uint64_t times(std::uint64_t a, std::uint64_t b) {
    if(a && b>UINT64_MAX/a) refuse("metadata_overflow","metadata size arithmetic overflow");
    return a*b;
}
struct Writer;
struct Object {
    Writer& w; bool first=true;
    template<class F> void field(std::string_view key,F emit);
    void num(std::string_view,double);
    template<class T> void integer(std::string_view,T);
    void flag(std::string_view,bool);
    void text(std::string_view,std::string_view,std::uint64_t);
    void fixed(std::string_view,std::string_view);
};
struct Writer {
    const Shape& shape;
    const Sink* sink=nullptr;
    bool maximum=false,material_style=false;
    std::uint64_t limit=UINT64_MAX;
    Size size;
    Buffer* buffer=nullptr;
    std::size_t used=0;
    Writer(const Shape& s,bool m,std::uint64_t l=UINT64_MAX,const Sink* out=nullptr,Buffer* b=nullptr)
        :shape(s),sink(out),maximum(m),limit(l),buffer(b) {}
    void charge(std::uint64_t n) {
        size.json_bytes=plus(size.json_bytes,n);
        if(size.json_bytes>limit) refuse("metadata_cap","complete metadata exceeds admitted extent");
    }
    void flush() {
        if(!used)return;
        try {(*sink)(std::span<const std::byte>(buffer->data(),used));}
        catch(...) {refuse("metadata_sink_failure","metadata sink did not accept the complete span");}
        used=0;
    }
    void raw(std::string_view s) {
        charge(s.size()); if(!sink)return;
        while(!s.empty()) {
            const auto n=std::min(s.size(),buffer->size()-used);
            std::copy_n(reinterpret_cast<const std::byte*>(s.data()),n,buffer->data()+used);
            used+=n;s.remove_prefix(n);if(used==buffer->size())flush();
        }
    }
    void quote(std::string_view s) {
        static constexpr char hex[]="0123456789abcdef";
        raw("\"");
        for(unsigned char c:s) {
            if(c=='\"'||c=='\\') {char b[2]={'\\',static_cast<char>(c)};raw({b,2});}
            // Uniform byte escaping makes the external format valid UTF-8 JSON
            // even when legacy material diagnostics contain arbitrary bytes.
            else if(c<32 || c>126) {
                char b[6]={'\\','u','0','0',hex[c>>4],hex[c&15]};raw({b,6});
            } else {const char b=static_cast<char>(c);raw({&b,1});}
        }
        raw("\"");
    }
    void text(std::string_view s,std::uint64_t cap) {
        if(maximum) {charge(plus(2,times(6,cap)));size.visited_string_bytes=plus(size.visited_string_bytes,cap);return;}
        if(s.size()>cap)refuse("metadata_cap","metadata string exceeds declared shape");
        size.visited_string_bytes=plus(size.visited_string_bytes,s.size());quote(s);
    }
    void number(double x) {
        if(maximum){charge(64);return;}
        const auto bits=std::bit_cast<std::uint64_t>(x);
        if((bits&UINT64_C(0x7ff0000000000000))==UINT64_C(0x7ff0000000000000)) {
            raw(material_style?"{\"binary64_bits\":\"":"{\"nonfinite_binary64_bits\":\"");
            char b[16];auto r=std::to_chars(b,b+16,bits,16);
            if(r.ec!=std::errc{})refuse("metadata_arithmetic","binary64 formatting failed");
            raw({b,static_cast<std::size_t>(r.ptr-b)});raw("\"}");return;
        }
        char b[64];auto r=std::to_chars(b,b+64,x,std::chars_format::general,17);
        if(r.ec!=std::errc{})refuse("metadata_arithmetic","binary64 formatting failed");
        raw({b,static_cast<std::size_t>(r.ptr-b)});
    }
    template<class T> void integer(T x) {
        if(maximum){charge(21);return;}
        char b[32];auto r=std::to_chars(b,b+32,x);
        if(r.ec!=std::errc{})refuse("metadata_arithmetic","integer formatting failed");
        raw({b,static_cast<std::size_t>(r.ptr-b)});
    }
    void flag(bool x) {if(maximum)charge(5);else raw(x?"true":"false");}
    template<class F> void object(F emit) {raw("{");Object o{*this};emit(o);raw("}");}
    template<class T,class F> void optional(const T* value,F emit) {
        if(maximum||value)emit(*this,value);else raw("null");
    }
    template<class Range,class F> void array(const Range* values,std::uint64_t cap,F emit) {
        using T=std::remove_cvref_t<decltype(*values->begin())>;
        if(maximum) {
            charge(2);
            if(!cap)return;
            Writer child(shape,true);child.material_style=material_style;
            emit(child,static_cast<const T*>(nullptr));
            charge(plus(times(cap,child.size.json_bytes),cap-1));
            size.visited_vector_elements=plus(size.visited_vector_elements,times(cap,plus(1,child.size.visited_vector_elements)));
            size.visited_string_bytes=plus(size.visited_string_bytes,times(cap,child.size.visited_string_bytes));
            return;
        }
        if(!values)refuse("metadata_state","missing required metadata vector");
        if(values->size()>cap)refuse("metadata_cap","metadata vector exceeds declared shape");
        size.visited_vector_elements=plus(size.visited_vector_elements,values->size());
        raw("[");bool first=true;
        for(const auto& value:*values){if(!first)raw(",");first=false;emit(*this,&value);}raw("]");
    }
};
struct Style {
    Writer& w;bool saved;
    Style(Writer& x,bool material):w(x),saved(x.material_style){w.material_style=material;}
    ~Style(){w.material_style=saved;}
};
template<class F> void Object::field(std::string_view key,F emit) {
    if(!first)w.raw(",");
    first=false;w.quote(key);w.raw(":");emit();
}
void Object::num(std::string_view k,double x){field(k,[&]{w.number(x);});}
template<class T>void Object::integer(std::string_view k,T x){field(k,[&]{w.integer(x);});}
void Object::flag(std::string_view k,bool x){field(k,[&]{w.flag(x);});}
void Object::text(std::string_view k,std::string_view x,std::uint64_t cap){field(k,[&]{w.text(x,cap);});}
void Object::fixed(std::string_view k,std::string_view x){field(k,[&]{w.quote(x);});}

#define BEGIN(T) void emit(Writer& w,const T* x){w.object([&](Object& o){
#define END });}
#define N(k) o.num(#k,x?x->k:0)
#define Z(k) o.integer(#k,x?x->k:0)
#define B(k) o.flag(#k,x?x->k:false)
#define S(k) o.text(#k,x?std::string_view(x->k):std::string_view{},w.shape.max_identifier_bytes)
#define D(k) o.text(#k,x?std::string_view(x->k):std::string_view{},w.shape.max_diagnostic_bytes)
#define V(k) o.field(#k,[&]{emit(w,x?&x->k:nullptr);})
#define A(k,cap) o.field(#k,[&]{w.array(x?&x->k:nullptr,w.shape.cap,[](Writer& z,const auto* v){emit(z,v);});})
#define O(k) o.field(#k,[&]{w.optional(x&&x->k?&*x->k:nullptr,[](Writer& z,const auto* v){emit(z,v);});})

void emit(Writer& w,const double* x){w.number(x?*x:0);}
void emit(Writer& w,const int* x){w.integer(x?*x:0);}
void emit(Writer& w,const std::string* x){w.text(x?std::string_view(*x):std::string_view{},w.shape.max_identifier_bytes);}
BEGIN(EnthalpyMeshInterval) N(lower);N(upper);END
BEGIN(SeasonalLiquidInterval) N(lower);N(upper);END
BEGIN(LayeredMaterialAddress) Z(cell_id);Z(layer_id);END
BEGIN(LayeredIceRemapLocation) B(deep);Z(layer_id);END
BEGIN(cryosphere_prototype::WaterProperties)
    N(freezing_temperature_k);N(solid_heat_capacity_j_kg_k);N(liquid_heat_capacity_j_kg_k);N(latent_heat_j_kg);
END
BEGIN(LayeredIceLimits)
    Z(max_columns);Z(max_layers_per_column);Z(max_thermal_nodes);Z(max_edges);Z(max_identifier_bytes);
END
BEGIN(EnergyTransportEdge) Z(first_cell);Z(second_cell);N(conductance_w_k);END
BEGIN(SurfaceEnergyColumn) N(area_m2);N(heat_capacity_j_m2_k);N(longwave_emissivity);END
BEGIN(EnthalpyMeshOptions)
    N(duration_seconds);N(maximum_stage_error_j);N(maximum_endpoint_error_j);Z(maximum_sweeps);
    Z(maximum_coordinate_iterations);Z(maximum_scalar_evaluations);Z(reconstruction_leaves);B(allow_pure_water_columns);
END
BEGIN(EnthalpyMeshRequest)
    V(water);A(columns,max_nodes);A(edges,max_edges);A(water_mass_kg_m2,max_nodes);
    A(initial_enthalpy_j_m2,max_nodes);A(absorbed_shortwave_w_m2,max_nodes);
    o.field("options",[&]{EnthalpyMeshOptions options;options.allow_pure_water_columns=true;emit(w,w.maximum?nullptr:&options);});
END
BEGIN(LayeredIceLayerInput)
    Z(layer_id);N(water_mass_kg_m2);N(enthalpy_j_m2);N(density_kg_m3);N(conductivity_w_m_k);
END
BEGIN(LayeredIceDeepInventoryInput) N(water_mass_kg_m2);N(enthalpy_j_m2);N(density_kg_m3);END

void closure(Writer& w,LayeredIceTopClosure value) {
    if(w.maximum){w.charge(64);return;}
    switch(value){
    case LayeredIceTopClosure::unspecified:w.quote("unspecified");break;
    case LayeredIceTopClosure::prescribed_top_energy:w.quote("prescribed_top_energy");break;
    case LayeredIceTopClosure::prescribed_nonwater_top_capacity:w.quote("prescribed_nonwater_top_capacity");break;
    case LayeredIceTopClosure::coarse_combined_surface_atmosphere:w.quote("coarse_combined_surface_atmosphere");break;
    default:w.raw("\"unknown_enum_");w.integer(static_cast<int>(value));w.raw("\"");}
}
BEGIN(LayeredIceColumnInput)
    Z(cell_id);N(area_m2);o.field("top_closure",[&]{closure(w,x?x->top_closure:LayeredIceTopClosure{});});
    N(top_nonwater_heat_capacity_j_m2_k);N(top_longwave_emissivity);N(top_absorbed_shortwave_w_m2);
    A(layers,max_layers_per_column);O(deep_inventory);
END
void emit(Writer& w,const LayeredIceInput* x) {
    Style style(w,false);w.object([&](Object& o){S(id);B(complete_horizontal_coverage_declared);
        o.field("bottom_boundary",[&]{
            if(w.maximum){w.charge(40);return;}
            if(x->bottom_boundary==LayeredIceBottomBoundary::unspecified)w.quote("unspecified");
            else if(x->bottom_boundary==LayeredIceBottomBoundary::insulated)w.quote("insulated");
            else {w.raw("\"unknown_enum_");w.integer(static_cast<int>(x->bottom_boundary));w.raw("\"");}
        });V(water);V(limits);A(columns,max_columns);A(horizontal_climate_edges,max_edges);
    });
}
BEGIN(LayeredIceInventoryConversion)
    N(represented_mass_kg);N(represented_enthalpy_j);V(exact_mass_kg);V(exact_enthalpy_j);
    V(mass_conversion_difference_kg);V(enthalpy_conversion_difference_j);
END
BEGIN(LayeredIceGeometryConversion)
    N(represented_thickness_m);V(exact_thickness_m);V(thickness_conversion_difference_m);
    V(thickness_mass_reconstruction_difference_kg_m2);
END
BEGIN(LayeredIceNode)
    Z(thermal_node_id);Z(cell_id);Z(layer_id);V(geometry);V(inventory);
    N(represented_depth_begin_m);N(represented_depth_end_m);V(exact_depth_begin_m);V(exact_depth_end_m);
    V(depth_begin_difference_m);V(depth_end_difference_m);
END
BEGIN(LayeredIceVerticalEdge)
    Z(first_thermal_node);Z(second_thermal_node);N(area_m2);N(first_thickness_m);N(second_thickness_m);
    N(first_conductivity_w_m_k);N(second_conductivity_w_m_k);
    N(represented_first_half_resistance_m2_k_w);N(represented_second_half_resistance_m2_k_w);
    N(represented_total_resistance_m2_k_w);N(represented_conductance_w_k);
    V(exact_first_half_resistance_m2_k_w);V(exact_second_half_resistance_m2_k_w);
    V(exact_total_resistance_m2_k_w);V(exact_conductance_w_k);
    V(first_half_resistance_difference_m2_k_w);V(second_half_resistance_difference_m2_k_w);
    V(total_resistance_difference_m2_k_w);V(conductance_difference_w_k);
END
BEGIN(LayeredIceDeepInventory) Z(cell_id);V(geometry);V(inventory);END
BEGIN(LayeredIceInventories) V(active);V(deep);V(combined);END
void emit(Writer& w,const LayeredIceGraph* x) {
    Style style(w,false);w.object([&](Object& o){
        o.fixed("model","fixed_geometry_layered_ice_thermal_graph_v1");
        o.field("input",[&]{emit(w,x?&x->input():nullptr);});
        o.field("mesh",[&]{emit(w,x?&x->mesh_request():nullptr);});
        o.fixed("geometry_scope","prescribed_fixed_mass_density_conductivity_v1");
        o.fixed("mass_area_scope","full_horizontal_footprint_coverage_fraction_one_v1");
        o.fixed("conductance_scope","equal_area_center_to_center_series_resistance_v1");
        o.fixed("conversion_scope","canonical_binary64_operands_outward_bounds_v1");
        o.fixed("active_enthalpy_scope","thermal_nodes_including_declared_top_nonwater_capacity_v1");
        o.fixed("deep_enthalpy_scope","pure_water_relative_to_solid_at_freezing_temperature_v1");
        o.fixed("combined_enthalpy_scope","active_thermal_nodes_plus_isolated_deep_water_not_ice_only_v1");
        for(const char* key:{"original_source_accuracy_certified","geometry_conversion_error_in_thermal_certificate",
            "source_operations_supported","deep_reservoir_thermally_coupled","geothermal_flux_resolved",
            "water_percolation_resolved","material_remapping_supported","ordinary_generation_changed",
            "world_horizontal_coverage_authenticated"})o.flag(key,false);
        o.field("top_thermal_node_ids",[&]{w.array(x?&x->top_thermal_node_ids():nullptr,w.shape.max_columns,[](Writer& z,const auto* v){emit(z,v);});});
        o.field("nodes",[&]{w.array(x?&x->nodes():nullptr,w.shape.max_nodes,[](Writer& z,const auto* v){emit(z,v);});});
        o.field("vertical_edges",[&]{w.array(x?&x->vertical_edges():nullptr,w.shape.max_edges,[](Writer& z,const auto* v){emit(z,v);});});
        o.field("deep_inventories",[&]{w.array(x?&x->deep_inventories():nullptr,w.shape.max_deep_inventories,[](Writer& z,const auto* v){emit(z,v);});});
        o.field("inventories",[&]{emit(w,x?&x->inventories():nullptr);});
    });
}

BEGIN(SeasonalLiquidRoutingLimits)
    Z(max_cells);Z(max_neighbor_entries);Z(max_sources);Z(max_identifier_bytes);Z(max_arithmetic_groups);
END
BEGIN(SeasonalLiquidRoutingNode)
    Z(cell_id);Z(original_receiver);A(neighbors,max_neighbors_per_node);
    B(is_water);B(is_lake);B(is_closed_basin);B(lake_overflows);B(hydrologic_surface_conditioned);
    Z(water_body);Z(depression_component_id);Z(depression_sink_cell_id);
    N(area_km2);N(elevation_m);N(filled_elevation_m);N(hydrologic_surface_elevation_m);
    N(hydrologic_flow_slope);N(water_depth_m);N(lake_fill_fraction);Z(effective_receiver);
    o.field("terminal",[&]{
        if(w.maximum){w.charge(8);return;}
        switch(x->terminal){
        case SeasonalLiquidTerminal::none:w.quote("none");break;
        case SeasonalLiquidTerminal::dry:w.quote("dry");break;
        case SeasonalLiquidTerminal::lake:w.quote("lake");break;
        case SeasonalLiquidTerminal::marine:w.quote("marine");break;
        default:refuse("metadata_state","unknown routing terminal");}
    });N(area_m2);V(area_conversion_difference_m2);
END
void emit(Writer& w,const SeasonalLiquidRoutingGraph* x) {
    Style style(w,false);w.object([&](Object& o){
        o.fixed("model","fixed_terrain_finite_liquid_mass_routing_v1");
        o.fixed("terminal_policy","first_wet_or_dry_terminal_v1");
        o.fixed("mass_scope","canonical_represented_source_kg_outward_rounding_bounds_v1");
        o.fixed("depth_scope","equivalent_throughput_depth_not_water_storage_v1");
        for(const char* key:{"original_source_accuracy_certified","owner_commit_authenticated",
            "external_delivery_acknowledged","downstream_energy_certified","physical_travel_time_resolved",
            "ordinary_generation_changed"})o.flag(key,false);
        o.integer("revision",x?x->revision():0);
        o.field("limits",[&]{emit(w,x?&x->limits():nullptr);});
        o.field("nodes",[&]{w.array(x?&x->nodes():nullptr,w.shape.max_geographic_nodes,[](Writer& z,const auto* v){emit(z,v);});});
        o.field("topological_order",[&]{w.array(x?&x->topological_order():nullptr,w.shape.max_geographic_nodes,[](Writer& z,const auto* v){emit(z,v);});});
    });
}

BEGIN(LayeredMaterialMovement)
    S(id);V(donor);V(recipient);o.integer("phase",x?static_cast<int>(x->phase):0);
    N(mass_kg);N(import_temperature_k);
END
BEGIN(LayeredMaterialParcelCertificate)
    V(movement);N(donor_temperature_k);N(specific_enthalpy_j_kg);N(carried_enthalpy_j);
    V(ideal_specific_enthalpy_j_kg);V(ideal_carried_enthalpy_j);V(energy_projection_j);B(external_outbox);
END
BEGIN(LayeredIceOwnedParcel) S(transaction_id);Z(source_revision);V(parcel);Z(geographic_cell_id);END
BEGIN(LayeredMaterialNodeCertificate)
    V(address);N(area_m2);N(nonwater_capacity_j_m2_k);N(initial_W);N(initial_H);N(final_W);N(final_H);
    V(before_H);V(before_floor);V(after_H);V(after_floor);V(gross_solid_kg);V(gross_liquid_kg);
    V(ideal_final_W);V(ideal_final_H);V(mass_projection_kg_m2);V(energy_projection_j_m2);
END
BEGIN(LayeredMaterialRequest)
    V(initial);N(inherited_energy_error_j);N(maximum_final_energy_error_j);A(movements,max_movements);
END
void emit(Writer& w,const LayeredMaterialReceipt* x) {
    Style style(w,true);w.object([&](Object& o){
        o.fixed("model","layered_initial_phase_material_event_v1");
        o.fixed("energy_error_scope","canonical_projected_W_joint_retained_new_outbox_L1_joules_v1");
        for(const char* k:{"original_mass_trajectory_certified","original_source_accuracy_certified",
            "geometry_error_certified","automatic_drainage_policy","owner_commit_available","ordinary_generation_changed"})o.flag(k,false);
        B(accepted);D(failure_code);D(detail);Z(graph_builds_started);Z(mass_calls_started);
        O(request);O(initial_graph);O(final_graph);A(nodes,max_node_certificates);A(parcels,max_parcel_certificates);
        N(retained_energy_defect_upper_j);N(outbox_energy_defect_upper_j);N(joint_final_energy_error_upper_j);
        V(retained_mass_change_kg);V(external_net_mass_kg);V(mass_balance_residual_kg);
        V(retained_energy_change_j);V(external_net_energy_j);V(energy_balance_residual_j);
        B(gross_initial_phase_inventory_proved);B(joint_nonexpansion_proved);
    });
}

BEGIN(LayeredIceRemapTargetLayer) Z(layer_id);N(density_kg_m3);N(conductivity_w_m_k);END
BEGIN(LayeredIceRemapTargetColumn) Z(cell_id);A(layers,max_target_layers_per_column);O(deep_density_kg_m3);END
BEGIN(LayeredIceRemapAllocation) V(destination);Z(weight);END
BEGIN(LayeredIceRemapDonor) Z(cell_id);V(source);A(allocations,max_allocations_per_donor);END
BEGIN(LayeredIceRemapLimits) Z(max_columns);Z(max_active_nodes);Z(max_donors);Z(max_allocations);Z(max_arithmetic_groups);END
BEGIN(LayeredIceTopologyLimits)
    Z(max_columns);Z(max_active_nodes);Z(max_donors);Z(max_allocations);Z(max_arithmetic_groups);Z(max_exports);
END
BEGIN(LayeredIceWholeInventoryExport) S(id);V(donor);o.integer("phase",x?static_cast<int>(x->phase):0);END
BEGIN(LayeredIceRemapRequest)
    S(id);V(source);N(inherited_global_energy_error_j);N(maximum_final_energy_error_j);
    V(limits);A(targets,max_targets);A(donors,max_donors);
END
BEGIN(LayeredIceTopologyRequest)
    S(id);V(source);N(inherited_global_energy_error_j);N(maximum_final_energy_error_j);
    V(limits);A(targets,max_targets);A(donors,max_donors);A(exports,max_export_certificates);
END
BEGIN(LayeredIceRemapWork)
    Z(source_builder_calls_started);Z(output_builder_calls_started);Z(donors_completed);
    Z(allocations_completed);Z(targets_completed);Z(arithmetic_groups_started);
END
BEGIN(LayeredIceTopologyWork)
    Z(source_builder_calls_started);Z(output_builder_calls_started);Z(donors_completed);
    Z(allocations_completed);Z(exports_completed);Z(targets_completed);Z(arithmetic_groups_started);
END
BEGIN(LayeredIceRemapDecomposition)
    Z(cell_id);V(source);N(initial_water_mass_kg_m2);N(initial_complete_enthalpy_j_m2);
    N(nonwater_capacity_j_m2_k);N(represented_water_enthalpy_j_m2);N(represented_stationary_nonwater_enthalpy_j_m2);
    V(ideal_water_enthalpy_j_m2);V(ideal_stationary_nonwater_enthalpy_j_m2);
END
BEGIN(LayeredIceRemapTransfer)
    Z(cell_id);V(source);V(destination);Z(weight);Z(total_weight);N(represented_fraction);V(ideal_fraction);
    N(represented_water_mass_kg_m2);N(represented_water_enthalpy_j_m2);
    V(ideal_water_mass_kg_m2);V(ideal_water_enthalpy_j_m2);
END
BEGIN(LayeredIceRemapProjection)
    Z(cell_id);V(destination);N(represented_water_mass_kg_m2);N(represented_complete_enthalpy_j_m2);
    V(ideal_water_mass_kg_m2);V(ideal_complete_enthalpy_j_m2);V(mass_projection_difference_kg_m2);
    V(enthalpy_projection_difference_j_m2);B(exact_identity_used);
END
BEGIN(LayeredIceRemapFinal)
    V(graph);N(energy_projection_defect_upper_j);N(final_global_energy_error_j);
    V(represented_total_mass_change_kg);V(represented_total_enthalpy_change_j);
    A(decompositions,max_donors);A(transfers,max_transfers);A(projections,max_node_certificates);
END
BEGIN(LayeredIceRemapReceipt)
    o.fixed("model","fixed_canonical_water_homogeneous_layer_remap_v1");
    B(accepted);D(failure_code);D(detail);O(request);O(source_graph);
    o.fixed("allocation_scope","same_column_complete_exact_integer_normalized_water_allocations_v1");
    o.fixed("energy_error_scope","global_area_weighted_enthalpy_l1_inherited_once_plus_projection_v1");
    o.fixed("nonwater_energy_scope","stationary_geographic_top_capacity_and_energy_v1");
    o.fixed("empty_deep_error_scope","zero_mass_deep_energy_exactly_zero_not_independent_error_coordinate_v1");
    o.fixed("mass_scope","canonical_represented_output_water_with_separate_projection_bounds_v1");
    o.fixed("target_material_scope","explicit_density_conductivity_geometry_replacement_not_volume_conservation_v1");
    for(const char* k:{"original_mass_trajectory_certified","imported_source_accuracy_certified",
        "geometry_conversion_error_certified","spatial_discretization_error_certified","external_water_source_or_sink",
        "phase_selective_drainage","ordinary_generation_changed"})o.flag(k,false);
    V(work);O(final);
END

BEGIN(LayeredIceTopologyDomain)
    V(address);N(area_m2);N(water_mass_kg_m2);N(enthalpy_j_m2);N(nonwater_capacity_j_m2_k);
    N(global_energy_error_j);V(enthalpy_ball_j_m2);V(physical_floor_j_m2);B(constrained_empty_deep);B(proved);
END
BEGIN(LayeredIceTopologyExportCertificate)
    V(selection);N(source_area_m2);N(source_water_mass_kg_m2);N(source_complete_enthalpy_j_m2);
    N(source_nonwater_capacity_j_m2_k);N(represented_full_mass_kg);V(exact_full_mass_kg);
    V(source_complete_energy_ball_j);V(full_latent_energy_j);B(exact_mass_representable);B(whole_phase_proved);V(parcel);
END
BEGIN(LayeredIceTopologyFinal)
    V(graph);A(parcels,max_parcel_certificates);N(retained_energy_defect_upper_j);
    N(outbox_energy_defect_upper_j);N(final_global_energy_error_j);
END
BEGIN(LayeredIceTopologyReceipt)
    o.fixed("model","fixed_canonical_whole_donor_export_and_homogeneous_topology_v1");
    B(accepted);D(failure_code);D(detail);O(request);O(source_graph);
    o.fixed("allocation_scope","complete_initial_positive_donors_owned_once_by_same_column_exact_weight_rows_or_whole_exports_v1");
    o.fixed("energy_error_scope","global_retained_and_old_outbox_l1_inherited_once_plus_direct_final_retained_and_new_outbox_projection_v1");
    o.fixed("nonwater_energy_scope","stationary_geographic_top_capacity_and_energy_v1");
    o.fixed("deleted_coordinate_scope","ideal_structural_zero_after_complete_water_allocation_not_unchecked_raw_subtraction_v1");
    o.fixed("empty_deep_error_scope","zero_mass_deep_energy_exactly_zero_not_independent_error_coordinate_v1");
    o.fixed("export_mass_scope","exact_representable_source_area_times_entire_canonical_donor_W_or_refusal_v1");
    o.fixed("export_energy_scope","saved_J_direct_projection_of_area_times_water_enthalpy_not_rounded_temperature_v1");
    o.fixed("export_phase_scope","entire_initial_marginal_global_error_ball_declared_solid_or_liquid_v1");
    o.fixed("mass_scope","canonical_represented_output_water_with_separate_projection_bounds_v1");
    o.fixed("target_material_scope","explicit_density_conductivity_geometry_replacement_not_volume_conservation_v1");
    o.fixed("target_layer_id_scope","explicit_complete_canonical_target_order_old_parcel_layer_ids_remain_historical_v1");
    o.fixed("builder_scope","existing_nonempty_active_graph_and_dry_top_deep_policy_unchanged_v1");
    o.fixed("old_pending_outbox_scope","identity_coordinates_retained_by_joint_owner_v1");
    for(const char* k:{"original_mass_trajectory_certified","imported_source_accuracy_certified",
        "geometry_conversion_error_certified","spatial_discretization_error_certified","external_imports",
        "autonomous_ablation_policy","ordinary_generation_changed"})o.flag(k,false);
    o.integer("thermal_or_calorimeter_calls",0);V(work);A(source_domain,max_domain_coordinates);A(final_domain,max_domain_coordinates);
    N(retained_energy_defect_upper_j);N(outbox_energy_defect_upper_j);N(final_global_energy_error_j);
    V(retained_mass_change_kg);V(exported_mass_kg);V(mass_balance_residual_kg);
    V(retained_energy_change_j);V(exported_energy_j);V(energy_balance_residual_j);
    A(export_certificates,max_export_certificates);A(decompositions,max_donors);A(transfers,max_transfers);
    A(projections,max_node_certificates);O(final);
END

BEGIN(LayeredIceAbsorptionSelection) S(transaction_id);S(event_id);V(recipient);END
BEGIN(LayeredIceAbsorptionRequest)
    V(initial);A(pending_outboxes,max_pending_outboxes);A(selections,max_absorption_selections);
    N(inherited_joint_energy_error_j);N(maximum_final_energy_error_j);
END
BEGIN(LayeredIceAbsorptionNode)
    V(address);N(area_m2);N(nonwater_capacity_j_m2_k);N(initial_W);N(initial_H);N(final_W);N(final_H);
    V(absorbed_mass_kg);V(absorbed_energy_j);V(ideal_final_W);V(ideal_final_H);
    V(mass_projection_kg_m2);V(energy_projection_j_m2);V(before_H);V(before_floor);V(after_H);V(after_floor);
END
BEGIN(LayeredIceAbsorptionWork) Z(source_builder_calls_started);Z(output_builder_calls_started);Z(parcels_absorbed);Z(nodes_updated);END
BEGIN(LayeredIceAbsorptionResult) V(graph);A(pending_outboxes,max_pending_outboxes);N(final_joint_energy_error_j);END
BEGIN(LayeredIceAbsorptionReceipt)
    o.fixed("model","same_joint_owner_prescribed_whole_parcel_absorption_v1");
    o.fixed("energy_error_scope","canonical_projected_W_joint_retained_remaining_pending_L1_joules_v1");
    for(const char* k:{"original_mass_trajectory_certified","source_history_authenticated","automatic_routing_policy",
        "external_delivery_acknowledged","ordinary_generation_changed"})o.flag(k,false);
    B(accepted);D(failure_code);D(detail);O(request);O(source_graph);A(nodes,max_node_certificates);V(work);
    N(energy_projection_defect_upper_j);V(absorbed_mass_kg);V(absorbed_energy_j);
    V(retained_mass_change_kg);V(retained_energy_change_j);V(mass_balance_residual_kg);V(energy_balance_residual_j);O(final);
END

BEGIN(LayeredIceOwnerForcing)
    S(id);N(begin_seconds);N(end_seconds);A(absorbed_shortwave_w_m2,max_forcing_values_per_record);
END
BEGIN(LayeredIceOwnerRemap) S(id);V(limits);A(targets,max_targets);A(donors,max_donors);END
BEGIN(LayeredIceOwnerTopology) S(id);V(limits);A(targets,max_targets);A(donors,max_donors);A(exports,max_export_certificates);END
BEGIN(LayeredIceOwnerRequest)
    S(id);Z(expected_revision);N(end_seconds);A(movements,max_movements);O(remap);O(forcing);O(thermal);
    A(absorptions,max_absorption_selections);O(topology);O(maximum_thermal_error_increment_j);
END
BEGIN(LayeredIceOwnerLimits)
    Z(max_prepare_attempts);Z(max_commits);Z(max_concurrent_preparations);Z(max_events_per_transition);
    Z(max_consumed_events);Z(max_pending_outboxes);Z(max_thermal_nodes);Z(max_thermal_edges);Z(max_node_leaves);
    Z(max_receipt_bytes);Z(max_history_bytes);Z(max_stored_forcing_values);Z(max_private_receipt_bytes);Z(max_retained_preparations);
END
BEGIN(LayeredIceOwnerDomainCoordinate) V(address);V(enthalpy_box_j_m2);V(physical_floor_j_m2);END
BEGIN(LayeredIceOwnerWork)
    Z(prepare_attempts);Z(graph_builds_started);Z(material_calls_started);Z(calorimeter_calls_started);
    Z(remap_calls_started);Z(thermal_calls_started);Z(absorption_calls_started);Z(topology_calls_started);
    Z(internal_be_calls_started);Z(scalar_evaluations);B(observed_counts_complete);
END
BEGIN(LayeredIceOwnerThermalLedger)
    V(storage_change_j);V(weighted_shortwave_j);V(weighted_emission_j);V(physical_duration_shortwave_j);
    V(shortwave_duration_bridge_j);V(balance_residual_j);V(assembled_defect_j);
    A(weighted_edge_transfer_j,max_edges);A(first_field_conversion_defect_j_m2,max_nodes);
END
BEGIN(LayeredIceOwnerThermalErrorCharge)
    N(before_global_energy_error_j);N(local_endpoint_error_upper_j);N(after_global_energy_error_j);
    V(charged_increment_j);O(maximum_thermal_error_increment_j);B(quota_passed);
END
BEGIN(LayeredIceOwnerMetadataHead)
    o.text("owner_id",x?x->owner_id:std::string_view{},w.shape.max_identifier_bytes);
    Z(snapshot_revision);Z(committed_sequence);Z(committed_attempt);
END
BEGIN(LayeredIceOwnerThermalSection)
    o.fixed("section","thermal");o.fixed("schema","enthalpy_mesh_proof_codec_v1");
    Z(payload_offset);Z(frame_bytes);Z(codec_version);
END

void snapshot(Writer& w,const LayeredIceOwnerSnapshot* x,const LayeredIceOwnerSnapshot* prefix,
              const LayeredIceOwnerMetadataHead* head,bool normalized) {
    if(!w.maximum && normalized) {
        if(!prefix || !head || x->owner_id!=prefix->owner_id ||
           &x->geographic_epoch.nodes()!=&prefix->geographic_epoch.nodes() ||
           x->geographic_cell_ids!=prefix->geographic_cell_ids ||
           !x->forcing_history.has_prefix(prefix->forcing_history) ||
           x->forcing_history.size()-prefix->forcing_history.size()>1)
            refuse("metadata_reference","final snapshot does not extend its committed source");
        if(x->forcing_history.size()>w.shape.max_forcing_records)
            refuse("metadata_cap","normalized forcing history exceeds declared shape");
    }
    w.object([&](Object& o){
        S(owner_id);Z(revision);N(elapsed_seconds);N(joint_energy_error_j);V(graph);
        if(normalized){
            o.field("geographic_epoch_ref",[&]{emit(w,head);});
            o.field("geographic_cell_ids_ref",[&]{emit(w,head);});
        }else{V(geographic_epoch);A(geographic_cell_ids,max_columns);}
        A(pending_outboxes,max_pending_outboxes);A(consumed_event_ids,max_consumed_event_ids);
        if(normalized)o.integer("forcing_history_prefix_length",x?x->forcing_history.size():0);
        else A(forcing_history,max_forcing_records);
    });
}

void receipt(Writer& w,const LayeredIceOwnerReceipt* x,const LayeredIceOwnerMetadataContext* context) {
    w.object([&](Object& o){
        o.fixed("model","mapped_atomic_layered_ice_owner_v5");
        o.fixed("energy_error_scope","canonical_projected_W_joint_active_deep_pending_outbox_L1_joules_v1");
        for(const char* k:{"original_mass_trajectory_certified","imported_source_accuracy_certified",
            "geometry_error_certified","spatial_discretization_error_certified","external_delivery_acknowledged",
            "ordinary_generation_changed"})o.flag(k,false);
        o.fixed("thermal_quota_scope","actual_outward_joint_E_increment_after_sources_not_extra_error_charge_v1");
        o.fixed("forcing_storage_scope","immutable_shared_prefix_values_lossless_normalized_journal_v1");
        o.fixed("retention_scope","normalized_journal_and_private_record_wire_bytes_not_peak_resident_memory_v1");
        o.flag("fixed_refusal_metadata_excluded_from_rich_retention_caps",true);
        o.flag("full_calendar_schedule_admitted",false);
        B(prepared);D(failure_code);D(detail);V(limits);N(maximum_joint_energy_error_j);O(request);
        o.field("initial",[&]{
            if(w.maximum || x->initial)emit(w,context?&context->initial_head:nullptr);else w.raw("null");
        });
        o.field("final",[&]{
            if(w.maximum || x->final)snapshot(w,x&&x->final?x->final.get():nullptr,
                x&&x->initial?x->initial.get():nullptr,context?&context->initial_head:nullptr,true);
            else w.raw("null");
        });
        O(material);O(remap);
        o.field("thermal",[&]{
            w.optional(context&&context->thermal_section?&*context->thermal_section:nullptr,
                [](Writer& z,const auto* v){emit(z,v);});
        });
        O(thermal_ledger);O(thermal_error_charge);O(absorption);O(topology);
        A(initial_domain,max_domain_coordinates);A(final_domain,max_domain_coordinates);V(work);
    });
}
void record(Writer& w,const LayeredIceOwnerReceipt* x,std::string_view key,
            const LayeredIceOwnerMetadataContext* context) {
    if(!w.maximum) {
        if(!context || !context->current_attempt || !context->seed_attempt)
            refuse("metadata_reference","record and seed attempt identities are required");
        if(x->initial && (x->initial->owner_id!=context->initial_head.owner_id ||
                         x->initial->revision!=context->initial_head.snapshot_revision))
            refuse("metadata_reference","initial snapshot differs from supplied committed head");
        if(x->final && (!x->initial || x->initial->revision==UINT64_MAX ||
                       x->final->revision!=x->initial->revision+1))
            refuse("metadata_reference","final snapshot has no immediate committed source");
        if(x->thermal.has_value()!=context->thermal_section.has_value())
            refuse("metadata_reference","thermal presence and complete external section disagree");
        if(context->thermal_section) {
            const auto& t=*context->thermal_section;
            if(t.codec_version!=1 || !t.frame_bytes || t.frame_bytes>UINT64_MAX-t.payload_offset)
                refuse("metadata_reference","invalid thermal section version or extent");
        }
    }
    w.object([&](Object& o){
        o.fixed("record_model","lossless_layered_owner_external_metadata_v1");
        o.integer("current_attempt",context?context->current_attempt:0);
        o.integer("seed_attempt",context?context->seed_attempt:0);
        o.field("committed_base",[&]{emit(w,context?&context->initial_head:nullptr);});
        o.text("replay_key",key,w.shape.max_replay_key_bytes);
        o.field("appended_forcing",[&]{
            std::span<const LayeredIceOwnerForcing> appended;
            if(!w.maximum && x->initial && x->final &&
               x->final->forcing_history.size()==x->initial->forcing_history.size()+1)
                appended={&x->final->forcing_history[x->initial->forcing_history.size()],1};
            w.array(&appended,1,[](Writer& z,const auto* v){emit(z,v);});
        });
        o.field("receipt",[&]{receipt(w,x,context);});
    });
}

#undef BEGIN
#undef END
#undef N
#undef Z
#undef B
#undef S
#undef D
#undef V
#undef A
#undef O

void valid_limits(const LayeredIceOwnerMetadataLimits& limits) {
    if(!limits.maximum_json_bytes)refuse("metadata_cap","an explicit metadata byte extent is required");
}
template<class F>Size exact(const LayeredIceOwnerMetadataLimits& limits,F visit) {
    valid_limits(limits);Writer w(limits.shape,false,limits.maximum_json_bytes);visit(w);return w.size;
}
template<class F>void streamed(const LayeredIceOwnerMetadataLimits& limits,const Sink& sink,F visit) {
    if(!sink)refuse("metadata_sink_failure","a metadata sink is required");
    const auto promised=exact(limits,visit);
    Buffer buffer;
    Writer w(limits.shape,false,limits.maximum_json_bytes,&sink,&buffer);visit(w);w.flush();
    if(w.size.json_bytes!=promised.json_bytes || w.size.visited_vector_elements!=promised.visited_vector_elements ||
       w.size.visited_string_bytes!=promised.visited_string_bytes)
        refuse("metadata_state","metadata changed between exact count and streaming traversal");
}
} // namespace

LayeredIceOwnerMetadataSize layered_ice_owner_metadata_size(const LayeredIceOwnerReceipt& receipt,
    std::string_view key,const LayeredIceOwnerMetadataContext& context,const LayeredIceOwnerMetadataLimits& limits) {
    return exact(limits,[&](Writer& w){record(w,&receipt,key,&context);});
}
void stream_layered_ice_owner_metadata(const LayeredIceOwnerReceipt& receipt,std::string_view key,
    const LayeredIceOwnerMetadataContext& context,const LayeredIceOwnerMetadataSink& sink,
    const LayeredIceOwnerMetadataLimits& limits) {
    streamed(limits,sink,[&](Writer& w){record(w,&receipt,key,&context);});
}
LayeredIceOwnerMetadataSize layered_ice_owner_metadata_max_size(const LayeredIceOwnerMetadataShape& shape) {
    Writer w(shape,true);record(w,nullptr,{},nullptr);return w.size;
}
LayeredIceOwnerMetadataSize layered_ice_owner_metadata_seed_size(const LayeredIceOwnerSnapshot& seed,
    const LayeredIceOwnerMetadataLimits& limits) {
    return exact(limits,[&](Writer& w){snapshot(w,&seed,nullptr,nullptr,false);});
}
void stream_layered_ice_owner_metadata_seed(const LayeredIceOwnerSnapshot& seed,
    const LayeredIceOwnerMetadataSink& sink,const LayeredIceOwnerMetadataLimits& limits) {
    streamed(limits,sink,[&](Writer& w){snapshot(w,&seed,nullptr,nullptr,false);});
}
LayeredIceOwnerMetadataSize layered_ice_owner_metadata_seed_max_size(const LayeredIceOwnerMetadataShape& shape) {
    Writer w(shape,true);snapshot(w,nullptr,nullptr,nullptr,false);return w.size;
}
LayeredIceOwnerMetadataSize layered_ice_owner_metadata_request_size(const LayeredIceOwnerRequest& request,
    const LayeredIceOwnerMetadataLimits& limits) {
    return exact(limits,[&](Writer& w){emit(w,&request);});
}
void stream_layered_ice_owner_metadata_request(const LayeredIceOwnerRequest& request,
    const LayeredIceOwnerMetadataSink& sink,const LayeredIceOwnerMetadataLimits& limits) {
    streamed(limits,sink,[&](Writer& w){emit(w,&request);});
}
LayeredIceOwnerMetadataSize layered_ice_owner_metadata_request_max_size(const LayeredIceOwnerMetadataShape& shape) {
    Writer w(shape,true);emit(w,static_cast<const LayeredIceOwnerRequest*>(nullptr));return w.size;
}
} // namespace magic_geo::detail
