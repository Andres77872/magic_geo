#pragma once

#include "enthalpy_mesh_owner.hpp"
#include "solar_insolation.hpp"

namespace magic_geo::detail {
class FinalizedEnthalpyContext;

struct SolarCalendarOptions {
    std::string id = "solar-year-0";
    double axial_tilt_deg = 23.5, orbital_eccentricity = .016, stellar_luminosity = 1;
    double year_duration_seconds = 365.2422 * 86400;
    double top_of_atmosphere_albedo = .3;
    double thermal_error_budget_j = 0; // Required, positive, for this whole year.
    int forcing_refinement_level = 0;
    std::size_t maximum_windows = 2048, maximum_stored_forcing_values = 2097152;
};
struct SolarCalendarWindow {
    SolarOrbitInterval orbital;
    std::uint64_t begin_tick = 0, end_tick = 0;
    EnthalpyMeshForcing forcing;
    double duration_seconds = 0, thermal_error_allowance_j = 0;
    // Exact-real differences between canonical binary64 operands, enclosed
    // outward. They do not bound the original orbital quadrature's accuracy.
    EnthalpyMeshInterval endpoint_rounding_seconds{}, duration_change_seconds{};
    std::vector<EnthalpyMeshInterval> fluence_change_j_m2;
};

// Exact ties-to-even rounding of the binary64 fraction times the integer
// year tick count. No floating multiplication, long-double assumption or
// nonstandard integer type is used. Collapsed windows are refused by build.
std::uint64_t round_solar_calendar_tick(double fraction, std::uint64_t year_ticks);

class SolarCalendar {
public:
    const SolarCalendarOptions& options() const;
    const std::vector<double>& latitudes_rad() const;
    const std::vector<SolarCalendarWindow>& windows() const;
    double clock_quantum_seconds() const;
    std::uint64_t year_ticks() const;
    // Fresh-owner full-year forcing admission only. Source IDs, thermal work and output
    // retention need their own complete schedule preflight before execution.
    void require_owner_capacity(const EnthalpyMeshOwnerLimits&) const;
private:
    struct Data;
    std::shared_ptr<const Data> data_;
    explicit SolarCalendar(std::shared_ptr<const Data>);
    friend SolarCalendar build_solar_calendar(const std::vector<double>&, SolarCalendarOptions);
};

SolarCalendar build_solar_calendar(const std::vector<double>& latitudes_rad, SolarCalendarOptions);
// Uses the complete finalized cell ordering and requires the same year length.
// Orbital inputs remain explicit: the old finalized planet identity does not
// contain them. No initial W/H, precipitation phase or source events inferred.
SolarCalendar build_finalized_solar_calendar(const FinalizedEnthalpyContext&, SolarCalendarOptions);
std::string solar_calendar_json(const SolarCalendar&);
} // namespace magic_geo::detail
