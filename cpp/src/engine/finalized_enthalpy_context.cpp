#include "finalized_enthalpy_context.hpp"
#include "climate_transport.hpp"
#include "internal.hpp"
#include "world.hpp"

#include <bit>
#include <cmath>
#include <map>

namespace magic_geo::detail {
namespace {
void need(bool condition, const char* code, const char* message) {
    if (!condition) throw TerrestrialWaterError(code, message);
}
bool same(double x, double y) {
    return std::bit_cast<std::uint64_t>(x) == std::bit_cast<std::uint64_t>(y);
}
void positive(double x, const char* message) {
    need(std::isfinite(x) && x > 0, "invalid_finalized_context", message);
}
bool same_atmosphere(const PrescribedAtmosphereOptions& a, const PrescribedAtmosphereOptions& b) {
    return same(a.mean_surface_pressure_pa,b.mean_surface_pressure_pa) &&
        same(a.gravity_m_s2,b.gravity_m_s2) && same(a.profile_temperature_k,b.profile_temperature_k) &&
        same(a.reference_infrared_optical_depth,b.reference_infrared_optical_depth) &&
        same(a.greenhouse_factor,b.greenhouse_factor) &&
        same(a.atmospheric_diffusivity_m2_s,b.atmospheric_diffusivity_m2_s);
}
double water_capacity(double depth) {
    const double result = static_cast<double>(
        static_cast<long double>(CLIMATE_WATER_VOLUMETRIC_HEAT_CAPACITY_J_M3_K) * depth);
    positive(result, "water slab heat capacity must be representable and positive");
    return result;
}
}

FinalizedEnthalpyPlanetInputs finalized_enthalpy_planet_inputs(const Params& p) {
    return {p.mesh_backend,p.radius_km,p.gravity_g,p.atmosphere_pressure_bar,
        p.reference_infrared_optical_depth,p.greenhouse_factor};
}
bool same_finalized_enthalpy_planet_inputs(
    const FinalizedEnthalpyPlanetInputs& a, const FinalizedEnthalpyPlanetInputs& b
) {
    return a.mesh_backend==b.mesh_backend && same(a.radius_km,b.radius_km) && same(a.gravity_g,b.gravity_g) &&
        same(a.atmosphere_pressure_bar,b.atmosphere_pressure_bar) &&
        same(a.reference_infrared_optical_depth,b.reference_infrared_optical_depth) &&
        same(a.greenhouse_factor,b.greenhouse_factor);
}

struct FinalizedEnthalpyContext::Data {
    TerrestrialSurfaceSnapshot surface;
    FinalizedEnthalpyOptions options;
    int backend;
    double radius;
    PrescribedAtmosphereOptions atmosphere;
    FinalizedEnthalpyPlanetInputs planet;
    std::vector<PrescribedSurfaceColumn> surfaces;
    std::vector<FinalizedLakeColumn> lakes;
    PrescribedClimateColumns physical;
    EnthalpyMeshProperties properties;
    Data(TerrestrialSurfaceSnapshot s, FinalizedEnthalpyOptions o, int b, double r,
         PrescribedAtmosphereOptions a)
        : surface(std::move(s)), options(std::move(o)), backend(b), radius(r), atmosphere(a) {}
};
FinalizedEnthalpyContext::FinalizedEnthalpyContext(std::shared_ptr<const Data> p) : data_(std::move(p)) {}
const TerrestrialSurfaceSnapshot& FinalizedEnthalpyContext::surface() const { return data_->surface; }
const FinalizedEnthalpyOptions& FinalizedEnthalpyContext::options() const { return data_->options; }
const FinalizedEnthalpyPlanetInputs& FinalizedEnthalpyContext::planet_inputs() const { return data_->planet; }
int FinalizedEnthalpyContext::mesh_backend() const { return data_->backend; }
double FinalizedEnthalpyContext::radius_m() const { return data_->radius; }
const PrescribedAtmosphereOptions& FinalizedEnthalpyContext::atmosphere() const { return data_->atmosphere; }
const std::vector<PrescribedSurfaceColumn>& FinalizedEnthalpyContext::surfaces() const { return data_->surfaces; }
const std::vector<FinalizedLakeColumn>& FinalizedEnthalpyContext::lakes() const { return data_->lakes; }
const PrescribedClimateColumns& FinalizedEnthalpyContext::physical_columns() const { return data_->physical; }
const EnthalpyMeshProperties& FinalizedEnthalpyContext::properties() const { return data_->properties; }

bool FinalizedEnthalpyContext::matches(const std::vector<Cell>& cells, const Params& params) const {
    const auto climate = make_prescribed_seasonal_climate_options(params);
    if (!same_finalized_enthalpy_planet_inputs(data_->planet,finalized_enthalpy_planet_inputs(params)) ||
        params.mesh_backend != data_->backend || !same(climate.radius_m,data_->radius) ||
        !same_atmosphere(climate.atmosphere,data_->atmosphere) ||
        !terrestrial_surface_matches(surface(),cells)) return false;
    const auto& captured = surface().cells();
    for (std::size_t i=0; i<cells.size(); ++i) {
        const auto& a=captured[i]; const auto& b=cells[i];
        if (a.depression_component_id != b.depression_component_id ||
            a.depression_sink_cell_id != b.depression_sink_cell_id ||
            !same(a.spill_elevation_m,b.spill_elevation_m) ||
            !same(a.lake_fill_fraction,b.lake_fill_fraction)) return false;
    }
    return true;
}

FinalizedEnthalpyContext build_finalized_enthalpy_context(
    const std::vector<Cell>& input, const Params& params, FinalizedEnthalpyOptions options,
    std::uint64_t revision
) {
    need(!input.empty() && input.size() <= EnthalpyMeshOwnerLimits{}.max_cells,
         "invalid_finalized_context", "finalized context exceeds the bounded owner cell domain");
    std::size_t vertices=0, face_neighbors=0, neighbors=0;
    // Geodesic edges have two face segments per endpoint. This also permits
    // the global size of symmetrized native kNN lists at k<=16 and N<=4096.
    const std::size_t incidence_cap=4*EnthalpyMeshOwnerLimits{}.max_edges;
    for (const auto& c : input) {
        need(c.control_volume_vertices.size()<=incidence_cap-vertices &&
             c.control_volume_edge_neighbor_ids.size()<=incidence_cap-face_neighbors &&
             c.neighbors.size()<=incidence_cap-neighbors,
             "invalid_finalized_context", "finalized geometry exceeds the pre-copy incidence bound");
        vertices+=c.control_volume_vertices.size();
        face_neighbors+=c.control_volume_edge_neighbor_ids.size();
        neighbors+=c.neighbors.size();
    }
    positive(options.marine_mixed_layer_depth_m,"positive finite prescribed marine depth required");
    if (options.lake_mixed_layer_depth_m)
        positive(*options.lake_mixed_layer_depth_m,"positive finite prescribed lake depth required");
    for (double v : {options.year_duration_seconds,options.reference_water_density_kg_m3,
                    options.water.freezing_temperature_k,options.water.solid_heat_capacity_j_kg_k,
                    options.water.liquid_heat_capacity_j_kg_k,options.water.latent_heat_j_kg})
        positive(v,"positive finite water and physical time parameters required");
    const auto climate = make_prescribed_seasonal_climate_options(params);
    positive(climate.radius_m,"positive finite planetary radius required");
    auto data = std::make_shared<FinalizedEnthalpyContext::Data>(
        capture_terrestrial_surface(input,revision),std::move(options),params.mesh_backend,
        climate.radius_m,climate.atmosphere);
    data->planet=finalized_enthalpy_planet_inputs(params);
    const auto& cells = data->surface.cells();
    std::map<int,int> lake_components; // component -> unique raw sink
    for (const auto& c : cells) {
        need(std::isfinite(c.lat) && std::abs(c.lat) <= PI/2 &&
             std::abs(c.lat-std::atan2(c.p.z,std::hypot(c.p.x,c.p.y))) <= 1e-9,
             "invalid_finalized_geometry", "latitude must match the spherical cell centre");
        if (!c.is_lake) continue;
        need(data->options.lake_mixed_layer_depth_m.has_value(),"lake_depth_policy_required",
             "finalized lakes require an explicitly prescribed mixed-layer depth");
        need(!c.is_water && (c.water_body==4 || c.water_body==5) &&
             c.depression_component_id >= 0 && c.depression_sink_cell_id >= 0 &&
             static_cast<std::size_t>(c.depression_sink_cell_id) < cells.size(),
             "invalid_finalized_lake", "lake classification requires a valid basin sink");
        const auto& sink = cells[static_cast<std::size_t>(c.depression_sink_cell_id)];
        need(sink.is_lake && !sink.is_water && sink.depression_sink_cell_id==sink.id &&
             sink.depression_component_id==c.depression_component_id && sink.water_body==c.water_body &&
             std::isfinite(sink.spill_elevation_m) &&
             std::isfinite(c.lake_fill_fraction) && c.lake_fill_fraction>=0 && c.lake_fill_fraction<=1.5 &&
             same(c.lake_fill_fraction,sink.lake_fill_fraction),
             "invalid_finalized_lake", "lake cells must share the native sink and fill operands");
        const auto [where, inserted] = lake_components.emplace(c.depression_component_id,sink.id);
        need(inserted || where->second==sink.id,"invalid_finalized_lake","lake component has conflicting sinks");
    }
    // Reconstruct the existing hydrology's operation order, including display
    // clipping, for every member of each wet component. Never use the conditioned
    // routing surface as a free surface, or the 0.2 m sink floor as real storage.
    std::map<int,int> sink_components;
    for (const auto& [component,sink] : lake_components) sink_components.emplace(sink,component);
    for (const auto& c : cells) {
        const auto component = lake_components.find(c.depression_component_id);
        const auto by_sink = sink_components.find(c.depression_sink_cell_id);
        if (component==lake_components.end() && by_sink==sink_components.end()) continue;
        need(!c.is_water && component!=lake_components.end() && by_sink!=sink_components.end() &&
             component->second==c.depression_sink_cell_id && by_sink->second==c.depression_component_id,
             "invalid_finalized_lake", "wet basin footprint has inconsistent component or sink membership");
        const auto& sink = cells[static_cast<std::size_t>(component->second)];
        need(same(c.lake_fill_fraction,sink.lake_fill_fraction),"invalid_finalized_lake",
             "all members of a wet basin must share its retained fill fraction");
        const double rise = std::max(0.0,sink.spill_elevation_m-sink.elevation_m);
        const double surface = sink.elevation_m+std::min(1.0,sink.lake_fill_fraction)*rise;
        const double depth = std::max(0.0,surface-c.elevation_m);
        need(std::isfinite(rise) && std::isfinite(surface) && std::isfinite(depth),
             "invalid_finalized_lake", "lake reconstruction is not representable");
        need(c.is_lake == (c.id==sink.id || depth>1e-9),"invalid_finalized_lake",
             "wet classification does not replay the retained native lake surface");
        if (!c.is_lake) continue;
        need(depth>0,"invalid_finalized_lake","a forced diagnostic sink floor is not positive lake storage");
        const double diagnostic = c.id==sink.id ? clamp(std::max(0.2,surface-sink.elevation_m),0.2,240.0)
                                               : clamp(depth,0.2,240.0);
        need(same(c.water_depth_m,diagnostic),"invalid_finalized_lake",
             "diagnostic lake depth does not replay the native clipping operation");
        data->lakes.push_back({c.id,sink.id,c.depression_component_id,sink.lake_fill_fraction,
            sink.elevation_m,sink.spill_elevation_m,surface,depth,c.water_depth_m,
            std::min(depth,*data->options.lake_mixed_layer_depth_m)});
    }
    std::size_t lake_index=0;
    for (const auto& c : cells) {
        // This exact binary64 product is the owner's authoritative area.
        const double area = c.area_km2*1e6;
        double z=c.elevation_m, capacity=CLIMATE_LAND_SLAB_HEAT_CAPACITY_J_M2_K;
        if (c.is_water) {
            need(!c.is_lake && c.water_body>=1 && c.water_body<=3 && c.elevation_m<0 &&
                 c.water_depth_m>0 && same(c.water_depth_m,-c.elevation_m),"invalid_finalized_surface",
                 "marine depth must equal the depth below the sea-level datum");
            z=0; capacity=water_capacity(std::min(c.water_depth_m,data->options.marine_mixed_layer_depth_m));
        } else if (c.is_lake) {
            const auto& lake=data->lakes.at(lake_index++);
            need(lake.cell_id==c.id,"invalid_finalized_lake","incomplete canonical lake reconstruction");
            z=lake.free_surface_elevation_m; capacity=water_capacity(lake.mixed_layer_depth_m);
        } else {
            need(c.water_depth_m==0 && (c.water_body==0 || c.water_body==5),"invalid_finalized_surface",
                 "dry cells require zero depth and a land or dry saline-basin classification");
        }
        data->surfaces.push_back({area,z,capacity});
    }
    data->physical=build_prescribed_climate_columns(data->surfaces,data->atmosphere);
    const long double radius=data->radius;
    const long double expected=4.0L*static_cast<long double>(PI)*radius*radius;
    need(std::isfinite(expected) && expected>0 &&
         std::abs(static_cast<long double>(data->physical.total_area_m2)-expected)<=2e-8L*expected,
         "invalid_finalized_geometry", "cell areas must cover the declared planetary sphere");
    auto edges=build_climate_heat_transport_edges(data->backend,cells,data->physical.horizontal_conductivity_w_k);
    need(edges.size()<=EnthalpyMeshOwnerLimits{}.max_edges,"invalid_finalized_context",
         "finalized transport exceeds the bounded owner edge domain");
    data->properties={data->options.water,data->options.reference_water_density_kg_m3,
        data->options.year_duration_seconds,data->physical.columns,std::move(edges)};
    return FinalizedEnthalpyContext(std::move(data));
}

struct FinalizedEnthalpyEpoch::Impl {
    FinalizedEnthalpyContext context;
    EnthalpyMeshOwner owner;
    Impl(FinalizedEnthalpyContext c, EnthalpyMeshRestart r, double budget, EnthalpyMeshOwnerLimits limits)
        : context(std::move(c)), owner(context.surface(),context.properties(),std::move(r),budget,limits) {}
};
FinalizedEnthalpyEpoch::FinalizedEnthalpyEpoch(std::unique_ptr<Impl> p) : impl_(std::move(p)) {}
FinalizedEnthalpyEpoch::~FinalizedEnthalpyEpoch()=default;
FinalizedEnthalpyEpoch::FinalizedEnthalpyEpoch(FinalizedEnthalpyEpoch&&) noexcept=default;
FinalizedEnthalpyEpoch& FinalizedEnthalpyEpoch::operator=(FinalizedEnthalpyEpoch&&) noexcept=default;
const FinalizedEnthalpyContext& FinalizedEnthalpyEpoch::context() const { return impl_->context; }
const EnthalpyMeshOwner& FinalizedEnthalpyEpoch::owner() const { return impl_->owner; }

FinalizedEnthalpyEpoch begin_finalized_enthalpy_epoch(
    EarthSystemState& earth, const Params& params, FinalizedEnthalpyOptions options,
    EnthalpyMeshRestart restart, double budget, std::uint64_t revision, EnthalpyMeshOwnerLimits limits
) {
    need(earth.terrestrial_surface_finalized,"surface_not_finalized",
         "combined enthalpy epoch requires the completed generated surface");
    need(!earth.terrestrial_surface_epoch,"epoch_already_started","generated surface already has an owner epoch");
    need(earth.finalized_enthalpy_planet.has_value() &&
         same_finalized_enthalpy_planet_inputs(*earth.finalized_enthalpy_planet,finalized_enthalpy_planet_inputs(params)),
         "finalized_planet_mismatch","epoch planet parameters must match the completed native generation");
    auto context=build_finalized_enthalpy_context(earth.cells,params,std::move(options),revision);
    FinalizedEnthalpyEpoch epoch(std::make_unique<FinalizedEnthalpyEpoch::Impl>(
        std::move(context),std::move(restart),budget,limits));
    // Publish only after complete context/graph and owner/restart validation.
    earth.terrestrial_surface_epoch.emplace(epoch.context().surface());
    earth.terrestrial_owner_mode=TerrestrialOwnerMode::combined_enthalpy;
    return epoch;
}
namespace {
void require_epoch(const EarthSystemState& earth, const Params& params, const FinalizedEnthalpyEpoch& epoch) {
    need(earth.terrestrial_surface_finalized && earth.terrestrial_surface_epoch.has_value(),
         "epoch_not_started","generated surface has no active finalized enthalpy epoch");
    need(same_terrestrial_surface_epoch(*earth.terrestrial_surface_epoch,epoch.context().surface()),
         "epoch_mismatch","combined enthalpy owner belongs to a different surface epoch");
    need(earth.terrestrial_owner_mode==TerrestrialOwnerMode::combined_enthalpy,
         "owner_mode_mismatch","this epoch is claimed by another terrestrial owner mode");
    need(earth.finalized_enthalpy_planet.has_value() &&
         same_finalized_enthalpy_planet_inputs(*earth.finalized_enthalpy_planet,epoch.context().planet_inputs()),
         "finalized_planet_mismatch","generated planet provenance changed during the epoch");
    need(epoch.context().matches(earth.cells,params),"finalized_context_changed",
         "captured geometry, lake basin, climate coefficient or hydrology operands changed during the epoch");
}
}
EnthalpyMeshPreparation prepare_finalized_enthalpy_interval(
    const EarthSystemState& earth, const Params& params, FinalizedEnthalpyEpoch& epoch,
    const EnthalpyMeshIntervalRequest& request
) {
    require_epoch(earth,params,epoch);
    return epoch.impl_->owner.prepare(request);
}
void commit_finalized_enthalpy_interval(
    const EarthSystemState& earth, const Params& params, FinalizedEnthalpyEpoch& epoch,
    const EnthalpyMeshIntervalCandidate& candidate
) {
    require_epoch(earth,params,epoch);
    epoch.impl_->owner.commit(candidate);
}

} // namespace magic_geo::detail
