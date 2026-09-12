#pragma once

#include "enthalpy_mesh_owner.hpp"
#include "physical_columns.hpp"

namespace magic_geo::detail {

struct EarthSystemState;

// Raw planet inputs consumed by this context; retained by successful world
// finalization before any opt-in epoch. Orbital forcing is a separate contract.
struct FinalizedEnthalpyPlanetInputs {
    int mesh_backend = 0;
    double radius_km = 0, gravity_g = 0, atmosphere_pressure_bar = 0;
    double reference_infrared_optical_depth = 0, greenhouse_factor = 0;
};
FinalizedEnthalpyPlanetInputs finalized_enthalpy_planet_inputs(const Params&);
bool same_finalized_enthalpy_planet_inputs(
    const FinalizedEnthalpyPlanetInputs&, const FinalizedEnthalpyPlanetInputs&);

struct FinalizedEnthalpyOptions {
    // Prescribed sensible slabs, not diagnosed ocean/lake mixing or lake ice.
    double marine_mixed_layer_depth_m = 50;
    // Required if the finalized surface contains lakes. No universal default.
    std::optional<double> lake_mixed_layer_depth_m;
    cryosphere_prototype::WaterProperties water{273.15, 2100, 4186, 334000};
    double reference_water_density_kg_m3 = 1000;
    double year_duration_seconds = 365.2422 * 86400;
};

struct FinalizedLakeColumn {
    int cell_id = -1, sink_cell_id = -1, depression_component_id = -1;
    double fill_fraction = 0, sink_elevation_m = 0, sink_spill_elevation_m = 0;
    double free_surface_elevation_m = 0, reconstructed_depth_m = 0;
    double diagnostic_depth_m = 0, mixed_layer_depth_m = 0;
};

// Immutable, bounded reconstruction from finalized native cells. This rebuilds
// every pressure/combined sensible column and the geometry-derived graph;
// the earlier fresh-marine climate cache is deliberately not an input.
class FinalizedEnthalpyContext {
public:
    const TerrestrialSurfaceSnapshot& surface() const;
    const FinalizedEnthalpyOptions& options() const;
    const FinalizedEnthalpyPlanetInputs& planet_inputs() const;
    int mesh_backend() const;
    double radius_m() const;
    const PrescribedAtmosphereOptions& atmosphere() const;
    const std::vector<PrescribedSurfaceColumn>& surfaces() const;
    const std::vector<FinalizedLakeColumn>& lakes() const;
    const PrescribedClimateColumns& physical_columns() const;
    const EnthalpyMeshProperties& properties() const;
    // Binds all used planet parameters, immutable geometry/baseline hydrology,
    // and retained basin operands, including those omitted by the old matcher.
    bool matches(const std::vector<Cell>&, const Params&) const;
private:
    struct Data;
    std::shared_ptr<const Data> data_;
    explicit FinalizedEnthalpyContext(std::shared_ptr<const Data>);
    friend FinalizedEnthalpyContext build_finalized_enthalpy_context(
        const std::vector<Cell>&, const Params&, FinalizedEnthalpyOptions, std::uint64_t);
};

FinalizedEnthalpyContext build_finalized_enthalpy_context(
    const std::vector<Cell>&, const Params&, FinalizedEnthalpyOptions,
    std::uint64_t surface_revision = 0);

// The only mutable owner access goes through the final-surface epoch guards.
// W/H and forcing remain explicit caller inputs; no annual/monthly mean is
// silently promoted to an instantaneous initial condition or source calendar.
class FinalizedEnthalpyEpoch {
public:
    ~FinalizedEnthalpyEpoch();
    FinalizedEnthalpyEpoch(FinalizedEnthalpyEpoch&&) noexcept;
    FinalizedEnthalpyEpoch& operator=(FinalizedEnthalpyEpoch&&) noexcept;
    FinalizedEnthalpyEpoch(const FinalizedEnthalpyEpoch&) = delete;
    FinalizedEnthalpyEpoch& operator=(const FinalizedEnthalpyEpoch&) = delete;
    const FinalizedEnthalpyContext& context() const;
    const EnthalpyMeshOwner& owner() const;
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
    explicit FinalizedEnthalpyEpoch(std::unique_ptr<Impl>);
    friend FinalizedEnthalpyEpoch begin_finalized_enthalpy_epoch(
        EarthSystemState&, const Params&, FinalizedEnthalpyOptions, EnthalpyMeshRestart,
        double, std::uint64_t, EnthalpyMeshOwnerLimits);
    friend EnthalpyMeshPreparation prepare_finalized_enthalpy_interval(
        const EarthSystemState&, const Params&, FinalizedEnthalpyEpoch&,
        const EnthalpyMeshIntervalRequest&);
    friend void commit_finalized_enthalpy_interval(
        const EarthSystemState&, const Params&, FinalizedEnthalpyEpoch&,
        const EnthalpyMeshIntervalCandidate&);
};

FinalizedEnthalpyEpoch begin_finalized_enthalpy_epoch(
    EarthSystemState&, const Params&, FinalizedEnthalpyOptions, EnthalpyMeshRestart,
    double maximum_cumulative_error_j, std::uint64_t surface_revision = 0,
    EnthalpyMeshOwnerLimits = {});
EnthalpyMeshPreparation prepare_finalized_enthalpy_interval(
    const EarthSystemState&, const Params&, FinalizedEnthalpyEpoch&,
    const EnthalpyMeshIntervalRequest&);
void commit_finalized_enthalpy_interval(
    const EarthSystemState&, const Params&, FinalizedEnthalpyEpoch&,
    const EnthalpyMeshIntervalCandidate&);

std::string finalized_enthalpy_context_json(const FinalizedEnthalpyContext&);
std::string finalized_enthalpy_epoch_json(const FinalizedEnthalpyEpoch&);

} // namespace magic_geo::detail
