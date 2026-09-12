#include "terrestrial_coupled_error.hpp"
#include "terrestrial_thermal/outward.hpp"
#include <bit>
#include <cfenv>
#include <cstdint>

namespace magic_geo::detail {
namespace {
namespace p = phase_segment_prototype;
namespace b = p::bounds;
using I = p::Interval;
struct Refusal : std::runtime_error {
    std::string code;
    Refusal(const char *c, const char *why) : std::runtime_error(why), code(c) {}
};
void need(bool ok, const char *code, const char *why) {
    if (!ok) throw Refusal(code, why);
}
void arithmetic() {
    need(std::numeric_limits<double>::is_iec559 && std::numeric_limits<double>::digits == 53 &&
             std::fegetround() == FE_TONEAREST,
         "capability_unavailable", "nearest binary64 arithmetic required");
    volatile double normal = std::numeric_limits<double>::min();
    volatile double tiny = std::numeric_limits<double>::denorm_min();
    volatile double tenth = 0.1, one = 1;
    volatile double product = normal * tenth, retained = tiny * one;
    need(product > 0 && retained > 0, "capability_unavailable", "gradual underflow required");
}
void parameters(const p::Water &w, const p::Column &c, double W, p::Energy x, double e) {
    arithmetic();
    for (double v : {w.freezing_temperature_k, w.solid_heat_capacity_j_kg_k,
                     w.liquid_heat_capacity_j_kg_k, w.latent_heat_j_kg, c.area_m2,
                     c.dry_heat_capacity_j_m2_k, c.atmospheric_heat_capacity_j_m2_k,
                     c.atmospheric_longwave_absorptivity, c.sensible_exchange_w_m2_k,
                     c.surface_shortwave_albedo, W, x.surface_enthalpy_j_m2,
                     x.atmospheric_energy_j_m2, e})
        need(std::isfinite(v), "invalid_error_input", "nonfinite error operand");
    need(w.freezing_temperature_k > 0 && w.solid_heat_capacity_j_kg_k > 0 &&
             w.liquid_heat_capacity_j_kg_k > 0 && w.latent_heat_j_kg > 0 &&
             c.area_m2 > 0 && c.dry_heat_capacity_j_m2_k > 0 &&
             c.atmospheric_heat_capacity_j_m2_k >= 0 && W >= 0 && e >= 0 &&
             c.atmospheric_longwave_absorptivity >= 0 &&
             c.atmospheric_longwave_absorptivity <= 1 && c.sensible_exchange_w_m2_k >= 0 &&
             c.surface_shortwave_albedo >= 0 && c.surface_shortwave_albedo <= 1,
         "invalid_error_input", "invalid physical/error operand");
    need(c.atmospheric_heat_capacity_j_m2_k > 0 ||
             (x.atmospheric_energy_j_m2 == 0 && c.atmospheric_longwave_absorptivity == 0 &&
              c.sensible_exchange_w_m2_k == 0),
         "invalid_error_input", "airless state/coefficient mismatch");
}
void policy(double e, double maximum) {
    need(std::isfinite(maximum) && maximum > 0, "invalid_error_input", "invalid error budget");
    need(e <= maximum, "cumulative_error_budget", "canonical joint energy error exceeds policy");
}
I radius(double x, double e) { return b::add(b::point(x), {-e, e}); }
I nonnegative(I x) { return b::checked(std::max(0.0, x.lower), std::max(0.0, x.upper)); }
I sum_mass(const std::vector<CanonicalMovement> &moves) {
    need(moves.size() <= 8192, "invalid_error_input", "movement bound");
    I result{0, 0};
    for (const auto &x : moves) {
        need(std::isfinite(x.mass_kg) && x.mass_kg > 0 && std::isfinite(x.carried_enthalpy_j),
             "invalid_error_input", "invalid canonical movement");
        result = b::add(result, b::point(x.mass_kg));
    }
    return result;
}
I sum_energy(const std::vector<CanonicalMovement> &moves) {
    I result{0, 0};
    for (const auto &x : moves) result = b::add(result, b::point(x.carried_enthalpy_j));
    return result;
}
I liquid_specific_enthalpy(const p::Water &w, const p::Column &c, double W, double H) {
    const I capacity = b::add(b::point(c.dry_heat_capacity_j_m2_k),
                             b::mul(b::point(W), b::point(w.liquid_heat_capacity_j_kg_k)));
    const I above = nonnegative(b::sub(b::point(H), b::mul(b::point(W),
                                                         b::point(w.latent_heat_j_kg))));
    return b::add(b::point(w.latent_heat_j_kg),
                  b::mul(b::point(w.liquid_heat_capacity_j_kg_k), b::div(above, capacity)));
}
template<class T> void failure(T &r, const std::exception &e) {
    if (const auto *specific = dynamic_cast<const Refusal *>(&e)) r.failure_code = specific->code;
    else r.failure_code = "error_enclosure_failure";
    r.detail = e.what();
}
void require_domain(const CoupledDomainCertificate &r) {
    need(r.accepted, "uncertain_physical_domain", "full canonical uncertainty box domain unproved");
}
} // namespace

CoupledDomainCertificate certify_coupled_domain(const p::Water &w, const p::Column &c,
                                               double W, p::Energy x, double e) {
    CoupledDomainCertificate r;
    try {
        parameters(w, c, W, x, e);
        r.uncertainty_box.surface_enthalpy_j_m2 = radius(x.surface_enthalpy_j_m2, e);
        r.uncertainty_box.atmospheric_energy_j_m2 = c.atmospheric_heat_capacity_j_m2_k == 0
            ? b::point(0) : radius(x.atmospheric_energy_j_m2, e);
        r.surface_floor_j_m2 = b::neg(b::mul(
            b::add(b::point(c.dry_heat_capacity_j_m2_k),
                   b::mul(b::point(W), b::point(w.solid_heat_capacity_j_kg_k))),
            b::point(w.freezing_temperature_k)));
        r.air_floor_j_m2 = b::neg(b::mul(b::point(c.atmospheric_heat_capacity_j_m2_k),
                                        b::point(w.freezing_temperature_k)));
        // Compare to the upper floor bound: the rounded box must sit above the
        // exact physical floor, not merely above its outward lower endpoint.
        need(r.uncertainty_box.surface_enthalpy_j_m2.lower >= r.surface_floor_j_m2.upper &&
                 r.uncertainty_box.atmospheric_energy_j_m2.lower >= r.air_floor_j_m2.upper,
             "uncertain_physical_domain", "canonical error box crosses a physical floor");
        r.accepted = true;
    } catch (const std::exception &e) { failure(r, e); }
    return r;
}

CoupledJumpCertificate certify_canonical_jump(
    const p::Water &w, const p::Column &c, double Wi, p::Energy initial,
    double Wf, p::Energy final, double inherited,
    const std::vector<CanonicalMovement> &imports,
    const std::vector<CanonicalMovement> &withdrawals, double maximum) {
    CoupledJumpCertificate r;
    r.inherited_error_j_m2 = inherited;
    try {
        parameters(w, c, Wi, initial, inherited);
        parameters(w, c, Wf, final, inherited);
        policy(inherited, maximum);
        need(std::bit_cast<std::uint64_t>(initial.atmospheric_energy_j_m2) ==
                 std::bit_cast<std::uint64_t>(final.atmospheric_energy_j_m2),
             "air_jump_not_identity", "mass event changed atmospheric energy bits");
        r.before_domain = certify_coupled_domain(w, c, Wi, initial, inherited);
        require_domain(r.before_domain);
        const I area = b::point(c.area_m2), im = sum_mass(imports), ex = sum_mass(withdrawals);
        const I importJ = sum_energy(imports), exportJ = sum_energy(withdrawals);
        r.withdrawal_density_kg_m2 = b::div(ex, area);
        r.import_energy_j_m2 = b::div(importJ, area);
        r.canonical_mass_projection_kg_m2 = b::sub(b::point(Wf),
            b::add(b::point(Wi), b::div(b::sub(im, ex), area)));
        if (!withdrawals.empty()) {
            const I available = b::mul(area, b::point(Wi));
            const I required = b::mul(ex, b::point(w.latent_heat_j_kg));
            const I lowerH = b::mul(area, b::point(
                r.before_domain.uncertainty_box.surface_enthalpy_j_m2.lower));
            need(ex.upper <= available.lower && required.upper <= lowerH.lower,
                 "uncertain_liquid_inventory", "gross liquid withdrawal exceeds uncertainty-safe inventory");
        }
        r.liquid_feasibility_proved = true;
        const I specific = withdrawals.empty() ? b::point(0)
            : liquid_specific_enthalpy(w, c, Wi, initial.surface_enthalpy_j_m2);
        const I idealExport = b::mul(r.withdrawal_density_kg_m2, specific);
        r.ideal_jump_j_m2 = b::sub(
            b::add(b::point(initial.surface_enthalpy_j_m2), r.import_energy_j_m2), idealExport);
        r.state_projection_j_m2 = b::sub(b::point(final.surface_enthalpy_j_m2),
            b::add(b::point(initial.surface_enthalpy_j_m2), b::div(b::sub(importJ, exportJ), area)));
        r.export_bridge_j_m2 = b::sub(b::div(exportJ, area), idealExport);
        r.jump_defect_upper_j_m2 = b::absmax(b::sub(b::point(final.surface_enthalpy_j_m2),
                                                   r.ideal_jump_j_m2));
        r.final_error_j_m2 = b::add(b::point(inherited), b::point(r.jump_defect_upper_j_m2)).upper;
        // Outbox bounds are separate evidence, not an extra state-error debit.
        const I capacity = b::add(b::point(c.dry_heat_capacity_j_m2_k),
            b::mul(b::point(Wi), b::point(w.liquid_heat_capacity_j_kg_k)));
        I outbox{0, 0};
        for (const auto &x : withdrawals) {
            const I defect = b::absolute(b::sub(b::point(x.carried_enthalpy_j),
                                               b::mul(b::point(x.mass_kg), specific)));
            const I sensitivity = b::div(
                b::mul(b::point(x.mass_kg), b::point(w.liquid_heat_capacity_j_kg_k)), capacity);
            const I total = b::add(defect, b::mul(sensitivity, b::point(inherited)));
            r.per_withdrawal_error_upper_j.push_back(total.upper);
            outbox = b::add(outbox, b::point(total.upper));
        }
        r.outbox_error_upper_j = outbox.upper;
        r.after_domain = certify_coupled_domain(w, c, Wf, final, r.final_error_j_m2);
        require_domain(r.after_domain);
        policy(r.final_error_j_m2, maximum);
        r.accepted = true;
    } catch (const std::exception &e) { failure(r, e); }
    return r;
}

CoupledSegmentCertificate certify_coupled_segment(const p::Receipt &segment, double inherited,
                                                  double maximum) {
    CoupledSegmentCertificate r;
    r.inherited_error_j_m2 = inherited;
    try {
        const auto &in = segment.request;
        parameters(in.water, in.column, in.water_mass_kg_m2, in.initial, inherited);
        policy(inherited, maximum);
        need(segment.accepted && segment.final_state_available &&
                 segment.numerical_budget_passed && segment.physical_budget_passed &&
                 segment.physical_error_bounds_available && segment.guard.domain_proved &&
                 segment.guard.finite_horizon_tube_proved,
             "thermal_certificate_refused", "native accepted physical segment required");
        r.before_domain = certify_coupled_domain(in.water, in.column, in.water_mass_kg_m2,
                                                in.initial, inherited);
        require_domain(r.before_domain);
        const auto local = b::checked(segment.physical_event_state_error_j_m2.lower,
                                       segment.physical_event_state_error_j_m2.upper);
        const auto time = b::checked(segment.physical_time_error_seconds.lower,
                                      segment.physical_time_error_seconds.upper);
        // Absolute-error enclosures may have a negative outward lower tail
        // (e.g. adding two [0,u] intervals rounds zero down by one subnormal).
        // The true norms are nonnegative; only their certified upper bounds
        // enter this recurrence. An entirely negative enclosure still refuses.
        need(local.upper >= 0 && time.upper >= 0, "thermal_certificate_refused", "negative error upper bound");
        if (in.endpoint_certificate == p::EndpointCertificate::hermite_residual) {
            const auto &proof = segment.reconstruction;
            need(in.goal == p::Goal::fixed_duration && in.reconstruction_leaves > 0 &&
                     in.reconstruction_leaves <= 64 &&
                     (in.reconstruction_leaves & (in.reconstruction_leaves-1)) == 0 &&
                     proof.started && proof.available && proof.leaves_started == in.reconstruction_leaves &&
                     proof.leaves.size() == static_cast<std::size_t>(in.reconstruction_leaves) &&
                     segment.selected_trial >= 0 &&
                     static_cast<std::size_t>(segment.selected_trial) < segment.trials.size(),
                 "thermal_certificate_refused", "complete native reconstruction required");
            const auto &trial = segment.trials[static_cast<std::size_t>(segment.selected_trial)];
            need(trial.candidate_available && trial.duration_seconds == segment.selected_duration_seconds &&
                     trial.endpoint.surface_enthalpy_j_m2 == segment.final_state.surface_enthalpy_j_m2 &&
                     trial.endpoint.atmospheric_energy_j_m2 == segment.final_state.atmospheric_energy_j_m2,
                 "thermal_certificate_refused", "reconstruction raw endpoint or duration mismatch");
            I surface{0,0}, air{0,0};
            for (std::size_t j = 0; j < proof.leaves.size(); ++j) {
                const auto &leaf = proof.leaves[j];
                need(leaf.index == static_cast<int>(j), "thermal_certificate_refused", "reconstruction coverage mismatch");
                const auto s = b::checked(leaf.surface_residual_integral_j_m2.lower,
                                           leaf.surface_residual_integral_j_m2.upper);
                const auto a = b::checked(leaf.air_residual_integral_j_m2.lower,
                                           leaf.air_residual_integral_j_m2.upper);
                need(s.upper >= 0 && a.upper >= 0, "thermal_certificate_refused", "negative residual upper bound");
                surface = b::add(surface,s); air = b::add(air,a);
            }
            const auto total = b::add(surface,air);
            need(surface.upper == proof.surface_residual_integral_j_m2.upper &&
                     air.upper == proof.air_residual_integral_j_m2.upper &&
                     total.upper == proof.endpoint_l1_error_j_m2.upper && local.upper == total.upper,
                 "thermal_certificate_refused", "selected residual bound or component sum mismatch");
        } else {
            need(in.endpoint_certificate == p::EndpointCertificate::direct_tube && in.reconstruction_leaves == 0 &&
                     !segment.reconstruction.started && !segment.reconstruction.available,
                 "thermal_certificate_refused", "endpoint certificate policy mismatch");
        }
        if (in.goal == p::Goal::next_phase_boundary) {
            need(segment.guard.first_physical_hit_proved,
                 "thermal_certificate_refused", "point-start first hit not proved");
            const auto rate = b::add(b::point(b::absmax(segment.guard.field.surface_net_w_m2)),
                b::point(b::absmax(segment.guard.field.atmospheric_net_w_m2)));
            r.time_transport_upper_j_m2 = b::mul(rate, b::point(time.upper)).upper;
        } else if (in.goal == p::Goal::fixed_duration) {
            need(segment.guard.fixed_time_endpoint_proved &&
                     !segment.guard.first_physical_hit_proved && !segment.guard.no_physical_hit_proved &&
                     segment.selected_duration_seconds == in.maximum_duration_seconds && time.upper == 0,
                 "thermal_certificate_refused", "same-time global-phase endpoint required");
        } else {
            need(in.goal == p::Goal::within_branch && segment.guard.no_physical_hit_proved &&
                     segment.selected_duration_seconds == in.maximum_duration_seconds &&
                     time.upper == 0,
                 "thermal_certificate_refused", "same-time no-hit endpoint required");
        }
        r.local_same_time_error_upper_j_m2 = b::add(b::point(local.upper),
            b::point(r.time_transport_upper_j_m2)).upper;
        r.final_error_j_m2 = b::add(b::point(inherited),
            b::point(r.local_same_time_error_upper_j_m2)).upper;
        r.after_domain = certify_coupled_domain(in.water, in.column, in.water_mass_kg_m2,
                                                segment.final_state, r.final_error_j_m2);
        require_domain(r.after_domain);
        policy(r.final_error_j_m2, maximum);
        r.accepted = true;
    } catch (const std::exception &e) { failure(r, e); }
    return r;
}
} // namespace magic_geo::detail
