#include "finalized_enthalpy_context.hpp"

#include <bit>
#include <cmath>
#include <iomanip>
#include <locale>
#include <sstream>

namespace magic_geo::detail {
namespace {
std::string num(double value) {
    std::ostringstream out; out.imbue(std::locale::classic());
    if (std::isfinite(value)) out << std::setprecision(17) << value;
    else out << "{\"nonfinite_binary64_bits\":\"" << std::hex << std::bit_cast<std::uint64_t>(value) << "\"}";
    return out.str();
}
struct Object {
    std::string value="{";
    void add(const char* name, const std::string& json) {
        if (value.size()>1) value+=',';
        value+='"'+std::string(name)+"\":"+json;
    }
    void number(const char* name, double x) { add(name,num(x)); }
    std::string finish() const { return value+'}'; }
};
template<class T,class F> std::string array(const std::vector<T>& values,F encode) {
    std::string out="[";
    for (const auto& x:values) { if (out.size()>1) out+=','; out+=encode(x); }
    return out+']';
}
std::string vector3(const Vec3& v) { return '['+num(v.x)+','+num(v.y)+','+num(v.z)+']'; }
std::string cell(const Cell& c) {
    Object o;
    o.add("cell_id",std::to_string(c.id));
    o.add("is_water",c.is_water?"true":"false"); o.add("is_lake",c.is_lake?"true":"false");
    o.add("water_body",std::to_string(c.water_body));
    o.number("area_km2",c.area_km2); o.number("elevation_m",c.elevation_m);
    o.number("lat",c.lat); o.number("lon",c.lon); o.add("position",vector3(c.p));
    o.number("water_depth_m",c.water_depth_m);
    o.add("neighbors",array(c.neighbors,[](int i){return std::to_string(i);}));
    o.add("control_volume_vertices",array(c.control_volume_vertices,vector3));
    o.add("control_volume_edge_neighbor_ids",array(c.control_volume_edge_neighbor_ids,[](int i){return std::to_string(i);}));
    o.number("temperature_c",c.temperature_c); o.number("original_precipitation_mm_y",c.precipitation_mm_y);
    o.number("sediment_thickness_m",c.sediment_thickness_m); o.add("lithology",std::to_string(c.lithology));
    o.add("depression_component_id",std::to_string(c.depression_component_id));
    o.add("depression_sink_cell_id",std::to_string(c.depression_sink_cell_id));
    o.number("spill_elevation_m",c.spill_elevation_m); o.number("lake_fill_fraction",c.lake_fill_fraction);
    return o.finish();
}
}

std::string finalized_enthalpy_context_json(const FinalizedEnthalpyContext& c) {
    Object o;
    o.add("schema","\"magic_geo.finalized_enthalpy_context.v1\"");
    o.add("surface_revision",std::to_string(c.surface().surface_revision()));
    o.add("mesh_backend",std::to_string(c.mesh_backend())); o.number("radius_m",c.radius_m());
    const auto& raw=c.planet_inputs(); Object planet;
    planet.add("mesh_backend",std::to_string(raw.mesh_backend)); planet.number("radius_km",raw.radius_km);
    planet.number("gravity_g",raw.gravity_g); planet.number("atmosphere_pressure_bar",raw.atmosphere_pressure_bar);
    planet.number("reference_infrared_optical_depth",raw.reference_infrared_optical_depth);
    planet.number("greenhouse_factor",raw.greenhouse_factor); o.add("planet_inputs",planet.finish());
    Object options;
    options.number("marine_mixed_layer_depth_m",c.options().marine_mixed_layer_depth_m);
    options.add("lake_mixed_layer_depth_m",c.options().lake_mixed_layer_depth_m ? num(*c.options().lake_mixed_layer_depth_m) : "null");
    options.number("water_volumetric_heat_capacity_j_m3_k",CLIMATE_WATER_VOLUMETRIC_HEAT_CAPACITY_J_M3_K);
    options.number("land_slab_heat_capacity_j_m2_k",CLIMATE_LAND_SLAB_HEAT_CAPACITY_J_M2_K);
    o.add("slab_options",options.finish());
    const auto& a=c.atmosphere(); Object atmosphere;
    atmosphere.number("mean_surface_pressure_pa",a.mean_surface_pressure_pa);
    atmosphere.number("gravity_m_s2",a.gravity_m_s2);
    atmosphere.number("profile_temperature_k",a.profile_temperature_k);
    atmosphere.number("reference_infrared_optical_depth",a.reference_infrared_optical_depth);
    atmosphere.number("greenhouse_factor",a.greenhouse_factor);
    atmosphere.number("atmospheric_diffusivity_m2_s",a.atmospheric_diffusivity_m2_s);
    o.add("atmosphere_options",atmosphere.finish());
    o.add("surface_cells",array(c.surface().cells(),cell));
    o.add("surfaces",array(c.surfaces(),[](const auto& s){
        Object x; x.number("area_m2",s.area_m2); x.number("interface_elevation_m",s.interface_elevation_m);
        x.number("surface_heat_capacity_j_m2_k",s.surface_heat_capacity_j_m2_k); return x.finish();
    }));
    o.add("lakes",array(c.lakes(),[](const auto& l){
        Object x;
        x.add("cell_id",std::to_string(l.cell_id)); x.add("sink_cell_id",std::to_string(l.sink_cell_id));
        x.add("depression_component_id",std::to_string(l.depression_component_id));
        x.number("fill_fraction",l.fill_fraction); x.number("sink_elevation_m",l.sink_elevation_m);
        x.number("sink_spill_elevation_m",l.sink_spill_elevation_m);
        x.number("free_surface_elevation_m",l.free_surface_elevation_m);
        x.number("reconstructed_depth_m",l.reconstructed_depth_m);
        x.number("diagnostic_depth_m",l.diagnostic_depth_m); x.number("mixed_layer_depth_m",l.mixed_layer_depth_m);
        return x.finish();
    }));
    const auto& p=c.physical_columns(); Object physical;
    physical.add("surface_pressure_pa",array(p.surface_pressure_pa,num));
    physical.add("atmospheric_heat_capacity_j_m2_k",array(p.atmospheric_heat_capacity_j_m2_k,num));
    physical.add("infrared_optical_depth",array(p.infrared_optical_depth,num));
    physical.add("horizontal_conductivity_w_k",array(p.horizontal_conductivity_w_k,num));
    physical.number("total_area_m2",p.total_area_m2);
    physical.number("atmospheric_scale_height_m",p.atmospheric_scale_height_m);
    physical.number("area_weighted_mean_surface_pressure_pa",p.area_weighted_mean_surface_pressure_pa);
    physical.number("mean_surface_pressure_residual_pa",p.mean_surface_pressure_residual_pa);
    physical.number("total_atmospheric_mass_kg",p.total_atmospheric_mass_kg);
    physical.number("atmospheric_mass_residual_kg",p.atmospheric_mass_residual_kg);
    o.add("physical_columns",physical.finish());
    o.add("owner_properties",enthalpy_mesh_properties_json(c.properties()));
    o.add("source_calendar_available","false");
    o.add("original_source_accuracy_certified","false");
    o.add("lake_ice_or_stratification_solved","false");
    o.add("hydrology_delivery_or_descendant_rebuild_available","false");
    return o.finish();
}

std::string finalized_enthalpy_epoch_json(const FinalizedEnthalpyEpoch& epoch) {
    Object o;
    o.add("schema","\"magic_geo.finalized_enthalpy_epoch.v1\"");
    o.add("context",finalized_enthalpy_context_json(epoch.context()));
    o.add("owner",enthalpy_mesh_owner_context_json(epoch.owner()));
    return o.finish();
}

} // namespace magic_geo::detail
