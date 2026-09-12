#include "layered_ice_owner.hpp"
#include "terrestrial_thermal/outward.hpp"

#include <cmath>
#include <stdexcept>

namespace magic_geo::detail {
namespace {
namespace b = phase_segment_prototype::bounds;
using I = EnthalpyMeshInterval;

void require(bool condition, const char* message) {
    if (!condition) throw std::invalid_argument(message);
}

I interval(I value) { return b::checked(value.lower, value.upper); }
} // namespace

LayeredIceOwnerThermalLedger layered_ice_owner_thermal_ledger(const EnthalpyMeshSdirk2Receipt& r) {
    require(r.accepted && r.request && r.final_enthalpy_j_m2 &&
            r.tableau_bridges_available && r.first_stage && r.second_stage &&
            r.first_stage->accepted && r.second_stage->accepted,
            "thermal ledger requires an accepted complete SDIRK2 receipt");
    const auto& q = *r.request;
    const auto& first = *r.first_stage;
    const auto& second = *r.second_stage;
    const auto n = q.columns.size();
    require(n > 0 && q.initial_enthalpy_j_m2.size() == n &&
            q.absorbed_shortwave_w_m2.size() == n && r.final_enthalpy_j_m2->size() == n &&
            r.first_stage_heating_w_m2.size() == n && r.second_stage_base_defect_j_m2.size() == n &&
            first.candidate_field.net_heating_w_m2.size() == n &&
            first.candidate_field.emitted_longwave_w_m2.size() == n &&
            second.candidate_field.emitted_longwave_w_m2.size() == n &&
            second.stage_residual_j_m2.size() == n &&
            first.candidate_field.edge_heat_w.size() == q.edges.size() &&
            second.candidate_field.edge_heat_w.size() == q.edges.size(),
            "thermal ledger receipt dimensions differ");
    require(std::isfinite(q.options.duration_seconds) && q.options.duration_seconds > 0 &&
            std::isfinite(r.off_diagonal_duration_seconds) && r.off_diagonal_duration_seconds > 0 &&
            std::isfinite(r.diagonal_duration_seconds) && r.diagonal_duration_seconds > 0,
            "thermal ledger requires positive finite physical and stage durations");

    const I beta_time = b::point(r.off_diagonal_duration_seconds);
    const I diagonal_time = b::point(r.diagonal_duration_seconds);
    const I method_time = b::add(beta_time, diagonal_time);
    const I physical_time = b::point(q.options.duration_seconds);
    LayeredIceOwnerThermalLedger ledger;
    ledger.first_field_conversion_defect_j_m2.reserve(n);
    ledger.weighted_edge_transfer_j.reserve(q.edges.size());
    I shortwave_power = b::point(0);
    for (std::size_t i = 0; i < n; ++i) {
        require(std::isfinite(q.columns[i].area_m2) && q.columns[i].area_m2 > 0 &&
                std::isfinite(q.absorbed_shortwave_w_m2[i]) && q.absorbed_shortwave_w_m2[i] >= 0,
                "thermal ledger requires positive areas and nonnegative finite shortwave");
        const I area = b::point(q.columns[i].area_m2);
        shortwave_power = b::add(shortwave_power,
            b::mul(area, b::point(q.absorbed_shortwave_w_m2[i])));
        ledger.storage_change_j = b::add(ledger.storage_change_j,
            b::mul(area, b::sub(b::point((*r.final_enthalpy_j_m2)[i]),
                              b::point(q.initial_enthalpy_j_m2[i]))));
        ledger.weighted_emission_j = b::add(ledger.weighted_emission_j, b::mul(area,
            b::add(b::mul(beta_time, interval(first.candidate_field.emitted_longwave_w_m2[i])),
                   b::mul(diagonal_time, interval(second.candidate_field.emitted_longwave_w_m2[i])))));

        // B2 - H0 - beta_time*F1 already includes conversion of F1 to its
        // represented midpoint and both raw base arithmetic operations. The
        // separately retained midpoint diagnostic must never be added again.
        ledger.first_field_conversion_defect_j_m2.push_back(b::mul(beta_time,
            b::sub(b::point(r.first_stage_heating_w_m2[i]),
                   interval(first.candidate_field.net_heating_w_m2[i]))));
        ledger.assembled_defect_j = b::add(ledger.assembled_defect_j, b::mul(area,
            b::add(interval(r.second_stage_base_defect_j_m2[i]),
                   interval(second.stage_residual_j_m2[i]))));
    }
    ledger.weighted_shortwave_j = b::mul(method_time, shortwave_power);
    ledger.physical_duration_shortwave_j = b::mul(physical_time, shortwave_power);
    // Sign: weighted minus physical. Thus a balance written with h*S equals
    // balance_residual_j + shortwave_duration_bridge_j. Retain the represented
    // tableau's duration bridge rather than declaring beta_time+a_time == h.
    ledger.shortwave_duration_bridge_j = b::mul(
        interval(r.duration_sum_defect_seconds), shortwave_power);
    ledger.balance_residual_j = b::add(
        b::sub(ledger.storage_change_j, ledger.weighted_shortwave_j),
        ledger.weighted_emission_j);

    // One signed extensive transfer per undirected edge is shared by both
    // endpoints: positive into the first and negative into the second. Such
    // internal transfers cancel in the ideal global discrete ledger. This
    // does not cancel independently bounded errors from the ODE certificate.
    for (std::size_t e = 0; e < q.edges.size(); ++e)
        ledger.weighted_edge_transfer_j.push_back(b::add(
            b::mul(beta_time, interval(first.candidate_field.edge_heat_w[e])),
            b::mul(diagonal_time, interval(second.candidate_field.edge_heat_w[e]))));

    // ΔH - beta_time*F1 - a_time*F2 = (B2-H0-beta_time*F1)
    //                              + (Y2-B2-a_time*F2).
    // This is method quadrature, not an exact continuous-flow radiation
    // integral. No first-stage storage or internal BE endpoint bound is added.
    require(ledger.balance_residual_j.lower <= ledger.assembled_defect_j.upper &&
            ledger.assembled_defect_j.lower <= ledger.balance_residual_j.upper,
            "thermal ledger and assembled stage/base defect are disjoint");
    return ledger;
}

} // namespace magic_geo::detail
