#pragma once

#include "adaptive_energy_balance.hpp"
#include "physical_columns.hpp"
#include "solar_insolation.hpp"

#include <vector>

namespace magic_geo::detail {

struct Cell;

struct PrescribedSeasonalClimateOptions {
    PrescribedAtmosphereOptions atmosphere;
    double radius_m = 6371000.0;
    double axial_tilt_deg = 23.5;
    double orbital_eccentricity = 0.016;
    double stellar_luminosity = 1.0;
    double year_duration_seconds = 365.2422 * 86400.0;
    // Effective top-of-atmosphere reflection; fixed during the solve. This
    // first adapter has no cloud, biome, lake, grounded-ice or sea-ice feedback.
    double top_of_atmosphere_albedo = 0.3;
    double marine_mixed_layer_depth_m = 50.0;
    int forcing_refinement_level = 0;
    // Explicit allocation/work bound for the current dense forcing adapter.
    std::size_t maximum_stored_forcing_values = 32'000'000;
    AdaptivePeriodicSurfaceEnergyOptions integration;

    PrescribedSeasonalClimateOptions();
    bool operator==(const PrescribedSeasonalClimateOptions&) const = default;
};

struct PrescribedSeasonalClimate {
    // Retain the actual inputs, independent of later terrain/ecology changes.
    PrescribedSeasonalClimateOptions options;
    int mesh_backend = 0;
    std::vector<double> latitudes_rad;
    std::vector<bool> marine_surface;
    std::vector<double> water_depth_m;
    std::vector<PrescribedSurfaceColumn> surfaces;
    PrescribedClimateColumns physical_columns;
    std::vector<EnergyTransportEdge> transport_edges;
    // Shared astronomical nodes suffice for replay with the retained latitude
    // and albedo. The interval-by-cell shortwave matrix is temporary work.
    std::vector<SolarOrbitInterval> forcing_intervals;
    AdaptivePeriodicSurfaceEnergyYear solution;
    double atmospheric_scale_height_to_radius = 0.0;
    double maximum_interface_elevation_to_radius = 0.0;
};

// Assemble and solve the prescribed marine/land thermal model on the actual
// native mesh. Requires fresh sea-level/marine state; stale lakes are rejected.
// The optional initial vector is a phase-boundary starting iterate, never an
// imposed mean temperature. It does not skip convergence or accuracy checks.
// Empty initial input uses local annual radiative equilibrium as a first guess.
// No Cell is mutated and no legacy Celsius correction is applied here. The
// explicit seasonal compute_climate path uses an owning cache of this result.
PrescribedSeasonalClimate solve_prescribed_seasonal_climate(
    int mesh_backend,
    const std::vector<Cell>& cells,
    const PrescribedSeasonalClimateOptions& options = {},
    const std::vector<double>& initial_phase_temperature_k = {}
);

}  // namespace magic_geo::detail
