#pragma once

#include "seasonal_energy_balance.hpp"
#include "terrestrial_calorimeter/cryosphere_enthalpy.hpp"
#include "terrestrial_thermal/phase_segment.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace magic_geo::detail {

// Explicit combined-temperature successor core. C is the complete prescribed
// non-retained-water sensible capacity (including the production atmosphere).
// No separate atmospheric energy, source calendar, or production dispatch.
struct EnthalpyMeshOptions {
    double duration_seconds = 0;
    double maximum_stage_error_j = 0;
    double maximum_endpoint_error_j = 0;
    int maximum_sweeps = 128;
    int maximum_coordinate_iterations = 64;
    std::uint64_t maximum_scalar_evaluations = 1048576;
    int reconstruction_leaves = 32;
    // Explicit generalized thermal-node mode. Pure-water nodes have Cbase=0,
    // W>0; both effective sensible capacities must be positive. Empty C=W=0
    // nodes refuse. The physical heating bound uses min(Cs,Cl) in this mode.
    // Geographic ownership, layer movement and source/remap proof are separate.
    bool allow_pure_water_columns = false;
};
struct EnthalpyMeshRequest {
    cryosphere_prototype::WaterProperties water{};
    std::vector<SurfaceEnergyColumn> columns;
    std::vector<EnergyTransportEdge> edges;
    std::vector<double> water_mass_kg_m2;
    std::vector<double> initial_enthalpy_j_m2;
    std::vector<double> absorbed_shortwave_w_m2;
    EnthalpyMeshOptions options;
};
using EnthalpyMeshInterval = phase_segment_prototype::Interval;
struct EnthalpyMeshField {
    std::vector<EnthalpyMeshInterval> temperature_k, emitted_longwave_w_m2;
    // One flux per undirected edge, positive into its first endpoint.
    std::vector<EnthalpyMeshInterval> edge_heat_w;
    std::vector<EnthalpyMeshInterval> heat_convergence_w_m2, net_heating_w_m2;
};
struct EnthalpyMeshSweep {
    int completed_sweeps = 0;
    std::uint64_t scalar_evaluations = 0;
    double stage_error_upper_j = 0;
};
struct EnthalpyMeshLeaf {
    int index = 0;
    bool complete = false;
    std::vector<EnthalpyMeshInterval> enthalpy_range_j_m2;
    EnthalpyMeshField field;
    std::vector<EnthalpyMeshInterval> residual_integral_j_m2;
    double weighted_residual_upper_j = 0;
};
struct EnthalpyMeshReceipt {
    bool accepted = false;
    std::string failure_code, detail;
    std::optional<EnthalpyMeshRequest> request;
    bool physical_domain_proved = false;
    double physical_temperature_upper_k = 0;
    std::vector<EnthalpyMeshInterval> physical_floor_j_m2;
    bool candidate_available = false, stage_error_available = false;
    std::vector<double> candidate_enthalpy_j_m2;
    EnthalpyMeshField candidate_field;
    std::vector<EnthalpyMeshInterval> stage_residual_j_m2;
    double stage_error_upper_j = 0;
    bool stage_accepted = false;
    std::vector<EnthalpyMeshSweep> sweeps;
    std::vector<EnthalpyMeshLeaf> leaves;
    bool endpoint_error_available = false;
    double local_endpoint_error_upper_j = 0;
    std::optional<std::vector<double>> final_enthalpy_j_m2;
    std::uint64_t scalar_evaluations = 0, field_evaluations = 0;
    int sweeps_started = 0, coordinate_solves_started = 0, leaves_started = 0;
};

// Actual raw backward-Euler endpoint; both a resolvent algebraic error gate
// and an independent exact-curve same-time residual gate must pass. The latter
// already includes the actual endpoint's numerical defect: never add it twice.
// The error norm is sum_i area_i*abs(delta H_i), in joules, from the canonical
// point start. It is not a per-cell J/m2, original-source, or annual certificate.
EnthalpyMeshReceipt advance_enthalpy_mesh(const EnthalpyMeshRequest&);
std::string enthalpy_mesh_request_json(const EnthalpyMeshRequest&);
std::string enthalpy_mesh_receipt_json(const EnthalpyMeshReceipt&);

} // namespace magic_geo::detail
