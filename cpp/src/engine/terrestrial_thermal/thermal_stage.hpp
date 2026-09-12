#pragma once

#include "../terrestrial_calorimeter/cryosphere_enthalpy.hpp"
#include <string>

namespace higher_order_thermal_prototype {

inline constexpr double sigma_w_m2_k4=5.670374419e-8;
using Water=cryosphere_prototype::WaterProperties;

struct Column {
    double area_m2;
    double dry_heat_capacity_j_m2_k;
    double atmospheric_heat_capacity_j_m2_k;
    double atmospheric_longwave_absorptivity;
    double sensible_exchange_w_m2_k;
    double surface_shortwave_albedo;
};
struct Energy {
    double surface_enthalpy_j_m2;
    double atmospheric_energy_j_m2;
    bool operator==(const Energy&) const = default;
};
struct Options {
    double absolute_tolerance_w_m2=1e-9;
    double relative_tolerance=1e-12;
    int maximum_newton_iterations=100;
    int maximum_backtracks=100;
};
struct StageInput {
    std::string stage_id;
    Water water;
    Column column;
    double water_mass_kg_m2;
    double incident_shortwave_w_m2;
    // Positive coefficient d of X-d F(X)=reference; not a physical clock tick.
    double effective_duration_seconds;
    // A finite signed algebraic reference. It is not a physical initial state.
    Energy reference;
    Energy guess;
    Options options;
};
struct Flux {
    cryosphere_prototype::PhaseState surface;
    bool atmosphere_present;
    double atmospheric_temperature_k;
    double incident_shortwave_w_m2;
    double reflected_shortwave_w_m2;
    double absorbed_shortwave_w_m2;
    double surface_longwave_w_m2;
    double atmospheric_absorbed_longwave_w_m2;
    double atmospheric_upward_longwave_w_m2;
    double atmospheric_downward_longwave_w_m2;
    double sensible_surface_to_air_w_m2;
    double outgoing_longwave_w_m2;
};
struct Receipt {
    bool accepted=false;
    std::string failure_code;
    std::string detail;
    bool candidate_available=false;
    Energy candidate{};
    Flux flux{};
    // Extended-arithmetic solver diagnostics. The exact producer wrapper reports
    // original-state / represented-component defects and their bridges separately.
    double surface_residual_w_m2=0;
    double atmospheric_residual_w_m2=0;
    double surface_solver_tolerance_w_m2=0;
    double atmospheric_solver_tolerance_w_m2=0;
    double surface_roundoff_allowance_j_m2=0;
    double atmospheric_roundoff_allowance_j_m2=0;
    int newton_iterations=0;
    int backtracks=0;
    int flux_evaluations=0;
};

// Pure approximate signed-reference solve, with nonnegative phase temperatures
// at every evaluated guess/trial. Acceptance alone is not an exact root/domain
// certificate. The method wrapper must separately certify the nominal sequential
// stages and compute exact ideal-equation defects before publishing uncertainty.
// No mass transfer, latent correction, BE fallback, extrapolated state or clock.
Receipt solve_stage(const StageInput& input);

} // namespace higher_order_thermal_prototype
