#include "phase_segment.hpp"
#include "outward.hpp"
#include "hermite_residual.hpp"
#include <algorithm>
#include <array>
#include <cfenv>
#include <cfloat>
#include <cstdint>
#include <limits>
#include <optional>
#include <stdexcept>

#if !defined(PHASE_SEGMENT_DISABLE_BACKEND) && !defined(MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER) && LDBL_MANT_DIG >= 64 && LDBL_MAX_EXP >= 16384
#define PHASE_HAS_BACKEND 1
#else
#define PHASE_HAS_BACKEND 0
#endif

namespace phase_segment_prototype {
namespace {
namespace b = bounds;
namespace t = higher_order_thermal_prototype;
using I = Interval;
constexpr double represented_g = 0.2928932188134525;
constexpr double represented_b = 1.0 - represented_g;
struct Refusal : std::runtime_error {
    std::string code;
    Refusal(std::string code, const char *reason)
        : std::runtime_error(reason), code(std::move(code)) {}
};
void need(bool ok, const char *code, const char *why) {
    if (!ok)
        throw Refusal(code, why);
}
bool finite(double x) { return std::isfinite(x); }
void identifier(const std::string &s) {
    need(!s.empty() && s.size() <= 64, "invalid_input", "identifier length");
    for (unsigned char c : s)
        need(c >= 33 && c <= 126, "invalid_input", "identifier must be visible ASCII");
}
bool exact_sum(double x, double y, double z) {
    if (!finite(z) || x + y != z)
        return false;
    const double p = z - x;
    return (x - (z - p)) + (y - p) == 0;
}
struct Boundary {
    double rounded = 0;
    double remainder = 0;
    bool decomposition_exact = true;
    I original{0, 0};
};
Boundary latent_boundary(const Input &in) {
    if (in.water_mass_kg_m2 == 0)
        return {};
    Boundary x;
    x.rounded = in.water_mass_kg_m2 * in.water.latent_heat_j_kg;
    need(finite(x.rounded) && x.rounded > 0, "representation_failure",
         "latent boundary product overflow/underflow");
    const int exponent_sum =
        std::ilogb(in.water_mass_kg_m2) + std::ilogb(in.water.latent_heat_j_kg);
    x.decomposition_exact = exponent_sum >= -970;
    if (x.decomposition_exact) {
        // Product has at most 106 significand bits; its least possible bit is
        // no smaller than 2^-1074 under this guard. FMA then retains the exact
        // product-minus-rounded-product remainder, including subnormals.
        x.remainder = std::fma(in.water_mass_kg_m2, in.water.latent_heat_j_kg, -x.rounded);
        if (x.remainder == 0)
            x.original = b::point(x.rounded);
        else if (x.remainder < 0)
            x.original = {b::down(x.rounded), x.rounded};
        else
            x.original = {x.rounded, b::up(x.rounded)};
    } else {
        x.original = b::mul(b::point(in.water_mass_kg_m2), b::point(in.water.latent_heat_j_kg));
    }
    return x;
}
int compare_boundary(double H, const Boundary &x) {
    if (x.decomposition_exact) {
        if (H < x.rounded)
            return -1;
        if (H > x.rounded)
            return 1;
        return x.remainder > 0 ? -1 : (x.remainder < 0 ? 1 : 0);
    }
    if (H < x.original.lower)
        return -1;
    if (H > x.original.upper)
        return 1;
    throw Refusal("phase_domain_unproved", "ambiguous original latent boundary comparison");
}
I surface_temperature(const Input &in, double H, const Boundary &boundary) {
    const I tf = b::point(in.water.freezing_temperature_k),
            cb = b::point(in.column.dry_heat_capacity_j_m2_k);
    if (in.water_mass_kg_m2 == 0)
        return b::add(tf, b::div(b::point(H), cb));
    if (H < 0) {
        const I capacity = b::add(cb, b::mul(b::point(in.water_mass_kg_m2),
                                             b::point(in.water.solid_heat_capacity_j_kg_k)));
        return b::add(tf, b::div(b::point(H), capacity));
    }
    if (compare_boundary(H, boundary) <= 0)
        return tf;
    const I capacity = b::add(
        cb, b::mul(b::point(in.water_mass_kg_m2), b::point(in.water.liquid_heat_capacity_j_kg_k)));
    return b::add(tf, b::div(b::sub(b::point(H), boundary.original), capacity));
}
I air_temperature(const Input &in, double Ea) {
    if (in.column.atmospheric_heat_capacity_j_m2_k == 0) {
        need(Ea == 0, "phase_domain_unproved", "airless energy must be zero");
        return {0, 0};
    }
    return b::add(b::point(in.water.freezing_temperature_k),
                  b::div(b::point(Ea), b::point(in.column.atmospheric_heat_capacity_j_m2_k)));
}
FluxBox ideal_flux(const Input &in, Energy x, const Boundary &boundary) {
    const I ts = surface_temperature(in, x.surface_enthalpy_j_m2, boundary);
    const I ta = air_temperature(in, x.atmospheric_energy_j_m2);
    need(ts.lower >= 0 && ta.lower >= 0, "phase_domain_unproved",
         "tube or stage temperature domain unproved");
    const I a = b::point(in.column.atmospheric_longwave_absorptivity);
    const I k = b::point(in.column.sensible_exchange_w_m2_k);
    const I ls = b::mul(b::point(t::sigma_w_m2_k4), b::fourth(ts));
    const I la = b::mul(a, b::mul(b::point(t::sigma_w_m2_k4), b::fourth(ta)));
    const I sensible = b::mul(k, b::sub(ts, ta));
    const I asr = b::mul(b::sub(b::point(1), b::point(in.column.surface_shortwave_albedo)),
                         b::point(in.incident_shortwave_w_m2));
    return {b::sub(b::sub(b::add(asr, la), ls), sensible),
            in.column.atmospheric_heat_capacity_j_m2_k == 0
                ? I{0, 0}
                : b::add(b::sub(b::mul(a, ls), b::mul(b::point(2), la)), sensible)};
}
FluxBox field_box(const Input &in, const StateBox &box, const Boundary &boundary) {
    // Opposite corners attain extrema by the sign of each Jacobian entry.
    const auto low = ideal_flux(
        in, {box.surface_enthalpy_j_m2.upper, box.atmospheric_energy_j_m2.lower}, boundary);
    const auto high = ideal_flux(
        in, {box.surface_enthalpy_j_m2.lower, box.atmospheric_energy_j_m2.upper}, boundary);
    return {{low.surface_net_w_m2.lower, high.surface_net_w_m2.upper},
            {high.atmospheric_net_w_m2.lower, low.atmospheric_net_w_m2.upper}};
}
bool branch_contains(Branch branch, double H, const Boundary &boundary,
                     bool include_boundary = true) {
    switch (branch) {
    case Branch::dry:
        return true;
    case Branch::solid:
        return include_boundary ? H <= 0 : H < 0;
    case Branch::mixed:
        return H >= 0 && compare_boundary(H, boundary) <= 0;
    case Branch::liquid:
        return include_boundary ? compare_boundary(H, boundary) >= 0
                                : compare_boundary(H, boundary) > 0;
    }
    return false;
}
void validate_input(const Input &in) {
    need(PHASE_HAS_BACKEND, "capability_unavailable", "extended long-double backend unavailable");
    need(std::numeric_limits<double>::is_iec559 && std::numeric_limits<double>::digits == 53 &&
             std::fegetround() == FE_TONEAREST,
         "capability_unavailable", "binary64 nearest arithmetic required");
    volatile double minimum_normal = std::numeric_limits<double>::min();
    volatile double minimum_subnormal = std::numeric_limits<double>::denorm_min();
    volatile double tenth = 0.1;
    volatile double one = 1.0;
    volatile double inexact_subnormal = minimum_normal * tenth;
    volatile double retained_subnormal = minimum_subnormal * one;
    need(inexact_subnormal > 0 && retained_subnormal > 0, "capability_unavailable",
         "gradual binary64 arithmetic required; FTZ/DAZ unsupported");
    identifier(in.segment_id);
    identifier(in.physical_boundary_id);
    need(!in.is_water && !in.is_lake, "invalid_domain",
         "only exposed freshwater columns supported");
    const auto &c = in.column;
    const auto &w = in.water;
    for (double x : {w.freezing_temperature_k,
                     w.solid_heat_capacity_j_kg_k,
                     w.liquid_heat_capacity_j_kg_k,
                     w.latent_heat_j_kg,
                     c.area_m2,
                     c.dry_heat_capacity_j_m2_k,
                     c.atmospheric_heat_capacity_j_m2_k,
                     c.atmospheric_longwave_absorptivity,
                     c.sensible_exchange_w_m2_k,
                     c.surface_shortwave_albedo,
                     in.water_mass_kg_m2,
                     in.incident_shortwave_w_m2,
                     in.initial.surface_enthalpy_j_m2,
                     in.initial.atmospheric_energy_j_m2,
                     in.start_seconds,
                     in.physical_boundary_seconds,
                     in.maximum_duration_seconds,
                     in.clock_quantum_seconds,
                     in.budgets.maximum_numerical_equation_defect_j_m2,
                     in.budgets.maximum_locator_width_seconds,
                     in.budgets.maximum_physical_time_error_seconds,
                     in.budgets.maximum_physical_event_state_error_j_m2})
        need(finite(x), "invalid_input", "nonfinite scalar");
    need(w.freezing_temperature_k > 0 && w.solid_heat_capacity_j_kg_k > 0 &&
             w.liquid_heat_capacity_j_kg_k > 0 && w.latent_heat_j_kg > 0,
         "invalid_input", "water constants must be positive");
    need(c.area_m2 > 0 && c.dry_heat_capacity_j_m2_k > 0 &&
             c.atmospheric_heat_capacity_j_m2_k >= 0 && c.atmospheric_longwave_absorptivity >= 0 &&
             c.atmospheric_longwave_absorptivity <= 1 && c.sensible_exchange_w_m2_k >= 0 &&
             c.surface_shortwave_albedo >= 0 && c.surface_shortwave_albedo <= 1,
         "invalid_input", "invalid column coefficients");
    need(in.water_mass_kg_m2 >= 0 && in.incident_shortwave_w_m2 >= 0 && in.start_seconds >= 0 &&
             in.maximum_duration_seconds > 0,
         "invalid_input", "invalid mass/forcing/clock");
    need(c.atmospheric_heat_capacity_j_m2_k > 0 ||
             (c.atmospheric_longwave_absorptivity == 0 && c.sensible_exchange_w_m2_k == 0 &&
              in.initial.atmospheric_energy_j_m2 == 0),
         "invalid_input", "airless coefficient/state mismatch");
    need((in.incoming_branch == Branch::dry) == (in.water_mass_kg_m2 == 0), "invalid_input",
         "dry branch mass mismatch");
    need(in.goal == Goal::within_branch || in.goal == Goal::next_phase_boundary ||
             in.goal == Goal::fixed_duration,
         "invalid_input", "unknown segment goal");
    need((in.endpoint_certificate == EndpointCertificate::direct_tube && in.reconstruction_leaves == 0) ||
             (in.endpoint_certificate == EndpointCertificate::hermite_residual &&
              in.goal == Goal::fixed_duration && in.reconstruction_leaves > 0 &&
              in.reconstruction_leaves <= 64 &&
              (in.reconstruction_leaves & (in.reconstruction_leaves - 1)) == 0),
         "invalid_input", "endpoint certificate policy or dyadic work count invalid");
    need(in.budgets.maximum_numerical_equation_defect_j_m2 > 0 &&
             in.budgets.maximum_locator_width_seconds > 0 &&
             in.budgets.maximum_physical_time_error_seconds > 0 &&
             in.budgets.maximum_physical_event_state_error_j_m2 > 0,
         "invalid_input", "budgets must be positive exact represented binary64 targets");
    need(in.limits.maximum_duration_trials > 0 && in.limits.maximum_duration_trials <= 64 &&
             in.limits.maximum_air_iterations_per_trial > 0 &&
             in.limits.maximum_air_iterations_per_trial <= 96 &&
             in.limits.maximum_stage_calls > 0 && in.limits.maximum_stage_calls <= 64 &&
             in.limits.maximum_total_flux_evaluations > 0 &&
             in.limits.maximum_total_flux_evaluations <= 32768,
         "invalid_input", "work caps outside finite policy");
    need(finite(in.stage_options.absolute_tolerance_w_m2) &&
             in.stage_options.absolute_tolerance_w_m2 > 0 &&
             finite(in.stage_options.relative_tolerance) &&
             in.stage_options.relative_tolerance >= 0 && in.stage_options.relative_tolerance <= 1,
         "invalid_input", "invalid stage tolerance");
    need(in.stage_options.maximum_newton_iterations >= 0 &&
             in.stage_options.maximum_newton_iterations <= 100 &&
             in.stage_options.maximum_backtracks >= 0 && in.stage_options.maximum_backtracks <= 100,
         "invalid_input", "stage work limits outside finite policy");
    need(exact_sum(in.start_seconds, in.maximum_duration_seconds,
                   in.start_seconds + in.maximum_duration_seconds) &&
             in.start_seconds + in.maximum_duration_seconds <= in.physical_boundary_seconds,
         "clock_refusal", "horizon crosses physical boundary or exact clock closure fails");
    (void)b::checked(in.proposed_tube.surface_enthalpy_j_m2.lower,
                     in.proposed_tube.surface_enthalpy_j_m2.upper);
    (void)b::checked(in.proposed_tube.atmospheric_energy_j_m2.lower,
                     in.proposed_tube.atmospheric_energy_j_m2.upper);
}
void build_guard(const Input &in, Receipt &receipt, const Boundary &boundary) {
    auto &g = receipt.guard;
    g.tube = in.proposed_tube;
    (void)ideal_flux(in, in.initial, boundary);
    (void)surface_temperature(in, g.tube.surface_enthalpy_j_m2.lower, boundary);
    const auto f = field_box(in, g.tube, boundary);
    g.field = f;
    g.domain_proved = true;
    g.picard_image.surface_enthalpy_j_m2 =
        b::add(b::point(in.initial.surface_enthalpy_j_m2),
               b::mul({0, in.maximum_duration_seconds}, f.surface_net_w_m2));
    g.picard_image.atmospheric_energy_j_m2 =
        b::add(b::point(in.initial.atmospheric_energy_j_m2),
               b::mul({0, in.maximum_duration_seconds}, f.atmospheric_net_w_m2));
    const bool air = in.column.atmospheric_heat_capacity_j_m2_k > 0;
    need(b::strict_inside(g.picard_image.surface_enthalpy_j_m2, g.tube.surface_enthalpy_j_m2) &&
             (air ? b::strict_inside(g.picard_image.atmospheric_energy_j_m2,
                                     g.tube.atmospheric_energy_j_m2)
                  : (b::zero(g.tube.atmospheric_energy_j_m2) && b::zero(f.atmospheric_net_w_m2))),
         "tube_unproved", "finite-horizon Picard inclusion failed");
    g.finite_horizon_tube_proved = true;
    if (f.surface_net_w_m2.lower > 0)
        g.direction = 1;
    else if (f.surface_net_w_m2.upper < 0)
        g.direction = -1;
    g.signed_surface_rate_w_m2 = g.direction < 0 ? b::neg(f.surface_net_w_m2) : f.surface_net_w_m2;
    g.transverse_monotonicity_proved = g.direction != 0;
    const double h0 = in.initial.surface_enthalpy_j_m2;
    need(branch_contains(in.incoming_branch, h0, boundary), "branch_refusal",
         "initial state outside declared incoming branch");
    if (in.goal == Goal::fixed_duration) {
        // The phase law is continuous and locally Lipschitz across both latent
        // boundaries. The proved global-field Picard tube therefore encloses
        // the physical flow even when its phase changes or direction reverses.
        // Incoming branch labels only the raw initial state in this mode.
        g.physical_event_state = {
            b::add(b::point(h0), b::mul(b::point(in.maximum_duration_seconds), f.surface_net_w_m2)),
            b::add(b::point(in.initial.atmospheric_energy_j_m2),
                   b::mul(b::point(in.maximum_duration_seconds), f.atmospheric_net_w_m2))};
        g.fixed_time_endpoint_proved = true;
        return;
    }
    if (in.water_mass_kg_m2 > 0) {
        if (h0 == 0)
            need((in.incoming_branch == Branch::mixed && g.direction > 0) ||
                     (in.incoming_branch == Branch::solid && g.direction < 0),
                 "phase_event_unresolved", "zero boundary outgoing direction unproved");
        if (compare_boundary(h0, boundary) == 0)
            need((in.incoming_branch == Branch::mixed && g.direction < 0) ||
                     (in.incoming_branch == Branch::liquid && g.direction > 0),
                 "phase_event_unresolved", "latent boundary outgoing direction unproved");
    }
    if (in.goal == Goal::within_branch) {
        I range = g.picard_image.surface_enthalpy_j_m2;
        // A certified strict direction also bounds the initial-side extremum
        // exactly; do not mistake outward arithmetic slack for a new crossing.
        if (g.direction > 0)
            range.lower = std::max(range.lower, h0);
        if (g.direction < 0)
            range.upper = std::min(range.upper, h0);
        bool no_hit = false;
        if (in.incoming_branch == Branch::dry)
            no_hit = true;
        else if (in.incoming_branch == Branch::solid)
            no_hit = range.upper < 0 || (h0 == 0 && g.direction < 0 && range.upper <= 0);
        else if (in.incoming_branch == Branch::liquid)
            no_hit = compare_boundary(range.lower, boundary) > 0 ||
                     (compare_boundary(h0, boundary) == 0 && g.direction > 0 &&
                      compare_boundary(range.lower, boundary) >= 0);
        else if (in.incoming_branch == Branch::mixed) {
            const bool lower = range.lower > 0 || (h0 == 0 && g.direction > 0 && range.lower >= 0);
            const bool upper = compare_boundary(range.upper, boundary) < 0 ||
                               (compare_boundary(h0, boundary) == 0 && g.direction < 0 &&
                                compare_boundary(range.upper, boundary) <= 0);
            no_hit = lower && upper;
        }
        need(no_hit, "phase_event_unresolved",
             "physical flow enclosure does not strictly exclude the next guard");
        g.no_physical_hit_proved = true;
        g.physical_event_state = {
            b::add(b::point(h0), b::mul(b::point(in.maximum_duration_seconds), f.surface_net_w_m2)),
            b::add(b::point(in.initial.atmospheric_energy_j_m2),
                   b::mul(b::point(in.maximum_duration_seconds), f.atmospheric_net_w_m2))};
        return;
    }
    need(in.goal == Goal::next_phase_boundary && g.direction != 0, "phase_event_unresolved",
         "transverse next-hit direction unproved");
    bool upper = false;
    if (in.incoming_branch == Branch::solid && g.direction > 0)
        upper = false;
    else if (in.incoming_branch == Branch::mixed)
        upper = g.direction > 0;
    else if (in.incoming_branch == Branch::liquid && g.direction < 0)
        upper = true;
    else
        throw Refusal("phase_event_unresolved", "no adjacent latent guard in proved direction");
    g.original_boundary_j_m2 = upper ? boundary.original : I{0, 0};
    g.represented_boundary_j_m2 = upper ? boundary.rounded : 0;
    g.boundary_product_remainder_j_m2 = upper ? boundary.remainder : 0;
    g.boundary_product_decomposition_exact = !upper || boundary.decomposition_exact;
    g.boundary_representation_bridge_j_m2 =
        b::sub(b::point(g.represented_boundary_j_m2), g.original_boundary_j_m2);
    I distance = b::sub(g.original_boundary_j_m2, b::point(h0));
    if (g.direction < 0)
        distance = b::neg(distance);
    need(distance.lower > 0, "phase_event_unresolved",
         "strict positive first-hit distance unproved");
    g.physical_first_hit_seconds = b::div(distance, g.signed_surface_rate_w_m2);
    need(g.physical_first_hit_seconds.lower > 0 &&
             g.physical_first_hit_seconds.upper <= in.maximum_duration_seconds,
         "phase_event_unresolved", "first-hit existence not proved within physical horizon");
    g.first_physical_hit_proved = true;
    g.physical_event_state = {g.original_boundary_j_m2,
                              b::add(b::point(in.initial.atmospheric_energy_j_m2),
                                     b::mul(g.physical_first_hit_seconds, f.atmospheric_net_w_m2))};
}
struct Clock {
    double quantum;
    std::uint64_t ticks;
};
Clock make_clock(const Input &in) {
    const double scale = std::max({in.start_seconds, in.maximum_duration_seconds,
                                   in.start_seconds + in.maximum_duration_seconds});
    need(in.clock_quantum_seconds >= 0, "clock_refusal", "negative declared clock quantum");
    const double quantum = in.clock_quantum_seconds == 0
        ? std::nextafter(scale, std::numeric_limits<double>::infinity()) - scale
        : in.clock_quantum_seconds;
    need(finite(quantum) && quantum > 0, "clock_refusal", "clock quantum is not finite positive");
    int exponent = 0;
    need(std::frexp(quantum, &exponent) == 0.5, "clock_refusal",
         "declared clock quantum must be a power of two");
    for (double x : {in.start_seconds, in.maximum_duration_seconds,
                     in.start_seconds + in.maximum_duration_seconds}) {
        const double units = x / quantum;
        need(finite(units) && units == std::floor(units) && units <= 9007199254740992.0 &&
                 units * quantum == x,
             "clock_refusal", "initial clock is not on the declared common lattice");
    }
    return {quantum, static_cast<std::uint64_t>(in.maximum_duration_seconds / quantum)};
}
void validate_trial_clock(const Input &in, double tau) {
    const double end = in.start_seconds + tau, remaining = in.maximum_duration_seconds - tau;
    need(tau > 0 && tau <= in.maximum_duration_seconds && end > in.start_seconds &&
             end <= in.physical_boundary_seconds && exact_sum(in.start_seconds, tau, end) &&
             remaining >= 0 && exact_sum(tau, remaining, in.maximum_duration_seconds),
         "clock_refusal", "trial duration/end/remainder does not close exactly");
}
double represent(long double x) {
    const double y = static_cast<double>(x);
    need(finite(y) && (y != 0 || x == 0), "representation_failure",
         "nonrepresentable flux/state value");
    return y;
}
Flux numerical_flux(const Input &in, Energy x, Receipt &receipt, bool &started) {
    need(receipt.total_flux_evaluations < in.limits.maximum_total_flux_evaluations, "work_cap",
         "flux evaluation cap");
    ++receipt.total_flux_evaluations;
    started = true;
    Flux f{};
#if PHASE_HAS_BACKEND
    f.surface = cryosphere_prototype::phase_state(
        in.water, {in.column.area_m2, in.column.dry_heat_capacity_j_m2_k},
        {in.water_mass_kg_m2, x.surface_enthalpy_j_m2});
    f.atmosphere_present = in.column.atmospheric_heat_capacity_j_m2_k > 0;
    if (f.atmosphere_present)
        f.atmospheric_temperature_k =
            cryosphere_prototype::phase_state(
                in.water, {in.column.area_m2, in.column.atmospheric_heat_capacity_j_m2_k},
                {0, x.atmospheric_energy_j_m2})
                .temperature_k;
    else
        need(x.atmospheric_energy_j_m2 == 0, "stage_domain_refusal", "airless stage energy");
#else
    (void)x;
    throw Refusal("capability_unavailable", "phase calorimeter backend unavailable");
#endif
    const long double ts = f.surface.temperature_k, ta = f.atmospheric_temperature_k;
    const long double a = in.column.atmospheric_longwave_absorptivity,
                      k = in.column.sensible_exchange_w_m2_k;
    const long double ls = static_cast<long double>(t::sigma_w_m2_k4) * ts * ts * ts * ts;
    const long double la = a * t::sigma_w_m2_k4 * ta * ta * ta * ta;
    f.incident_shortwave_w_m2 = in.incident_shortwave_w_m2;
    f.reflected_shortwave_w_m2 = represent(
        static_cast<long double>(in.column.surface_shortwave_albedo) * in.incident_shortwave_w_m2);
    f.absorbed_shortwave_w_m2 =
        represent((1 - static_cast<long double>(in.column.surface_shortwave_albedo)) *
                  in.incident_shortwave_w_m2);
    f.surface_longwave_w_m2 = represent(ls);
    f.atmospheric_absorbed_longwave_w_m2 = represent(a * ls);
    f.atmospheric_upward_longwave_w_m2 = represent(la);
    f.atmospheric_downward_longwave_w_m2 = represent(la);
    f.sensible_surface_to_air_w_m2 = represent(k * (ts - ta));
    f.outgoing_longwave_w_m2 = represent((1 - a) * ls + la);
    return f;
}
Energy component_net(const Flux &f) {
    return {f.absorbed_shortwave_w_m2 + f.atmospheric_downward_longwave_w_m2 -
                f.surface_longwave_w_m2 - f.sensible_surface_to_air_w_m2,
            f.atmospheric_absorbed_longwave_w_m2 - f.atmospheric_upward_longwave_w_m2 -
                f.atmospheric_downward_longwave_w_m2 + f.sensible_surface_to_air_w_m2};
}
t::StageInput stage_input(const Input &in, double tau, const std::string &id, Energy reference,
                          Energy guess) {
    const double d = represented_g * tau;
    need(finite(d) && d > 0, "representation_failure",
         "stage effective duration underflow/overflow");
    return {id, in.water,  in.column, in.water_mass_kg_m2, in.incident_shortwave_w_m2,
            d,  reference, guess,     in.stage_options};
}
void stage_call(const Input &in, const t::StageInput &request, t::Receipt &result, Receipt &receipt,
                bool &called) {
    const std::int64_t worst =
        1 + static_cast<std::int64_t>(in.stage_options.maximum_newton_iterations) *
                (static_cast<std::int64_t>(in.stage_options.maximum_backtracks) + 1);
    need(receipt.stage_calls_started < in.limits.maximum_stage_calls &&
             worst <= in.limits.maximum_total_flux_evaluations - receipt.total_flux_evaluations,
         "work_cap", "stage call has no complete worst-case flux reservation");
    ++receipt.stage_calls_started;
    called = true;
    result = t::solve_stage(request);
    need(result.flux_evaluations >= 0 && result.flux_evaluations <= worst, "stage_protocol_refusal",
         "stage flux counter outside bound");
    receipt.total_flux_evaluations += result.flux_evaluations;
    need(result.accepted, "stage_refusal", "frozen thermal stage refused");
}
void equation_bounds(const Input &in, DurationTrial &trial, const Boundary &boundary) {
    const I tau = b::point(trial.duration_seconds), g = b::gamma(), weight = b::sub(b::point(1), g);
    const auto f1 = ideal_flux(in, trial.first_stage.candidate, boundary),
               f2 = ideal_flux(in, trial.endpoint, boundary);
    const auto defect1 = [&](double y1, double y0, I f) {
        return b::sub(b::sub(b::point(y1), b::point(y0)), b::mul(b::mul(tau, g), f));
    };
    const auto defect2 = [&](double y2, double y0, I first, I second) {
        return b::sub(b::sub(b::point(y2), b::point(y0)),
                      b::mul(tau, b::add(b::mul(weight, first), b::mul(g, second))));
    };
    trial.nominal_first_stage_defect = {
        defect1(trial.first_stage.candidate.surface_enthalpy_j_m2, in.initial.surface_enthalpy_j_m2,
                f1.surface_net_w_m2),
        defect1(trial.first_stage.candidate.atmospheric_energy_j_m2,
                in.initial.atmospheric_energy_j_m2, f1.atmospheric_net_w_m2)};
    trial.nominal_endpoint_quadrature_defect = {
        defect2(trial.endpoint.surface_enthalpy_j_m2, in.initial.surface_enthalpy_j_m2,
                f1.surface_net_w_m2, f2.surface_net_w_m2),
        defect2(trial.endpoint.atmospheric_energy_j_m2, in.initial.atmospheric_energy_j_m2,
                f1.atmospheric_net_w_m2, f2.atmospheric_net_w_m2)};
    I sum = b::point(0);
    for (auto x : {trial.nominal_first_stage_defect.surface_enthalpy_j_m2,
                   trial.nominal_first_stage_defect.atmospheric_energy_j_m2,
                   trial.nominal_endpoint_quadrature_defect.surface_enthalpy_j_m2,
                   trial.nominal_endpoint_quadrature_defect.atmospheric_energy_j_m2})
        sum = b::add(sum, b::point(b::absmax(x)));
    trial.nominal_equation_l1_upper_j_m2 = sum.upper;
    trial.nominal_defects_available = true;
}
void surface_and_air_defects(const Input &in, DurationTrial &trial) {
    const auto f1 = component_net(trial.first_stage.flux), f2 = component_net(trial.endpoint_flux);
    const double tau = trial.duration_seconds;
    trial.represented_surface_equation_defect_j_m2 =
        trial.endpoint.surface_enthalpy_j_m2 - in.initial.surface_enthalpy_j_m2 -
        tau * (represented_b * f1.surface_enthalpy_j_m2 + represented_g * f2.surface_enthalpy_j_m2);
    trial.represented_air_equation_defect_j_m2 = trial.endpoint.atmospheric_energy_j_m2 -
                                                 in.initial.atmospheric_energy_j_m2 -
                                                 tau * (represented_b * f1.atmospheric_energy_j_m2 +
                                                        represented_g * f2.atmospheric_energy_j_m2);
    need(finite(trial.represented_surface_equation_defect_j_m2) &&
             finite(trial.represented_air_equation_defect_j_m2),
         "representation_failure", "nonfinite represented equation defects");
    trial.represented_defects_available = true;
}
void fitted_air(const Input &in, DurationTrial &trial, Receipt &receipt) {
    const double H = receipt.guard.represented_boundary_j_m2, tau = trial.duration_seconds;
    const auto f1 = component_net(trial.first_stage.flux);
    auto evaluate = [&](double Ea) {
        trial.air_trials.emplace_back();
        auto &attempt = trial.air_trials.back();
        attempt.energy_j_m2 = Ea;
        try {
            attempt.flux = numerical_flux(in, {H, Ea}, receipt, attempt.evaluation_started);
            attempt.flux_available = true;
            const double residual =
                Ea - in.initial.atmospheric_energy_j_m2 -
                tau * (represented_b * f1.atmospheric_energy_j_m2 +
                       represented_g * component_net(attempt.flux).atmospheric_energy_j_m2);
            need(finite(residual), "representation_failure", "air equation overflow");
            attempt.represented_equation_defect_j_m2 = residual;
            attempt.equation_defect_available = true;
        } catch (const Refusal &error) {
            attempt.failure_code = error.code;
            throw;
        } catch (const cryosphere_prototype::Error &) {
            attempt.failure_code = "stage_domain_refusal";
            throw;
        } catch (const std::exception &) {
            attempt.failure_code = "interval_or_internal_refusal";
            throw;
        }
        return attempt;
    };
    if (in.column.atmospheric_heat_capacity_j_m2_k == 0) {
        const auto point = evaluate(0);
        trial.endpoint = {H, 0};
        trial.endpoint_flux = point.flux;
        return;
    }
    auto low = evaluate(in.proposed_tube.atmospheric_energy_j_m2.lower);
    auto high = evaluate(in.proposed_tube.atmospheric_energy_j_m2.upper);
    need(low.represented_equation_defect_j_m2 <= 0 && high.represented_equation_defect_j_m2 >= 0,
         "air_locator_unresolved", "sampled air equation not enclosed by supplied box");
    auto best = std::abs(low.represented_equation_defect_j_m2) <
                        std::abs(high.represented_equation_defect_j_m2)
                    ? low
                    : high;
    for (int j = 0; j < in.limits.maximum_air_iterations_per_trial; ++j) {
        if (std::abs(best.represented_equation_defect_j_m2) <=
            in.budgets.maximum_numerical_equation_defect_j_m2 / 16)
            break;
        const double mid = low.energy_j_m2 + (high.energy_j_m2 - low.energy_j_m2) / 2;
        if (!(mid > low.energy_j_m2 && mid < high.energy_j_m2))
            break;
        auto point = evaluate(mid);
        if (std::abs(point.represented_equation_defect_j_m2) <
            std::abs(best.represented_equation_defect_j_m2))
            best = point;
        if (point.represented_equation_defect_j_m2 < 0)
            low = point;
        else
            high = point;
    }
    trial.endpoint = {H, best.energy_j_m2};
    trial.endpoint_flux = best.flux;
}
int duration_trial(const Input &in, double tau, Receipt &receipt, const Boundary &boundary) {
    need(receipt.duration_trials_started < in.limits.maximum_duration_trials, "work_cap",
         "duration trial cap");
    validate_trial_clock(in, tau);
    ++receipt.duration_trials_started;
    receipt.trials.emplace_back();
    auto &trial = receipt.trials.back();
    trial.duration_seconds = tau;
    trial.first_stage_input = stage_input(in, tau, "phase_stage_1", in.initial, in.initial);
    trial.first_stage_requested = true;
    stage_call(in, trial.first_stage_input, trial.first_stage, receipt, trial.first_stage_called);
    trial.first_stage_in_incoming_branch = branch_contains(
        in.incoming_branch, trial.first_stage.candidate.surface_enthalpy_j_m2, boundary);
    // A global-phase-law predictor may leave the incoming branch. Phase-fitted
    // and within-branch goals cannot select it; fixed-duration evolution can.
    if (in.goal == Goal::next_phase_boundary)
        fitted_air(in, trial, receipt);
    else {
        const auto f = component_net(trial.first_stage.flux);
        const Energy ref{
            in.initial.surface_enthalpy_j_m2 + tau * (represented_b * f.surface_enthalpy_j_m2),
            in.initial.atmospheric_energy_j_m2 + tau * (represented_b * f.atmospheric_energy_j_m2)};
        trial.second_stage_input =
            stage_input(in, tau, "phase_stage_2", ref, trial.first_stage.candidate);
        trial.second_stage_used = true;
        stage_call(in, trial.second_stage_input, trial.second_stage, receipt,
                   trial.second_stage_called);
        trial.endpoint = trial.second_stage.candidate;
        trial.endpoint_flux = trial.second_stage.flux;
        need(in.goal == Goal::fixed_duration ||
                 branch_contains(in.incoming_branch, trial.endpoint.surface_enthalpy_j_m2, boundary),
             "stage_branch_refusal", "accepted endpoint left incoming branch");
    }
    trial.candidate_available = true;
    surface_and_air_defects(in, trial);
    equation_bounds(in, trial, boundary);
    return static_cast<int>(receipt.trials.size() - 1);
}
bool prefer_trial(const DurationTrial &next, const DurationTrial &current) {
    if (next.first_stage_in_incoming_branch != current.first_stage_in_incoming_branch)
        return next.first_stage_in_incoming_branch;
    if (next.nominal_defects_available != current.nominal_defects_available)
        return next.nominal_defects_available;
    return next.nominal_defects_available &&
           next.nominal_equation_l1_upper_j_m2 < current.nominal_equation_l1_upper_j_m2;
}
void retain_selected(const Input &in, Receipt &receipt, int selected) {
    const auto &trial = receipt.trials.at(static_cast<std::size_t>(selected));
    receipt.selected_trial = selected;
    receipt.numerical_candidate_available = trial.candidate_available;
    receipt.selected_duration_seconds = trial.duration_seconds;
    receipt.selected_end_seconds = in.start_seconds + trial.duration_seconds;
    receipt.remaining_duration_seconds = in.maximum_duration_seconds - trial.duration_seconds;
    receipt.selected_first_stage_in_incoming_branch = trial.first_stage_in_incoming_branch;
    receipt.numerical_budget_passed =
        trial.nominal_defects_available &&
        trial.nominal_equation_l1_upper_j_m2 <= in.budgets.maximum_numerical_equation_defect_j_m2;
}
ComponentFluences quadrature(const Input &in, const DurationTrial &trial) {
    const auto &f1 = trial.first_stage.flux;
    const auto &f2 = trial.endpoint_flux;
    const auto fluence = [&](double first, double second) {
        const double value = in.column.area_m2 * trial.duration_seconds *
                             (represented_b * first + represented_g * second);
        need(finite(value), "representation_failure", "component fluence overflow");
        return value;
    };
    ComponentFluences q{};
    q.incident_shortwave_j = fluence(f1.incident_shortwave_w_m2, f2.incident_shortwave_w_m2);
    q.reflected_shortwave_j = fluence(f1.reflected_shortwave_w_m2, f2.reflected_shortwave_w_m2);
    q.absorbed_shortwave_j = fluence(f1.absorbed_shortwave_w_m2, f2.absorbed_shortwave_w_m2);
    q.surface_longwave_j = fluence(f1.surface_longwave_w_m2, f2.surface_longwave_w_m2);
    q.atmospheric_absorbed_longwave_j =
        fluence(f1.atmospheric_absorbed_longwave_w_m2, f2.atmospheric_absorbed_longwave_w_m2);
    q.atmospheric_upward_longwave_j =
        fluence(f1.atmospheric_upward_longwave_w_m2, f2.atmospheric_upward_longwave_w_m2);
    q.atmospheric_downward_longwave_j =
        fluence(f1.atmospheric_downward_longwave_w_m2, f2.atmospheric_downward_longwave_w_m2);
    q.sensible_surface_to_air_j =
        fluence(f1.sensible_surface_to_air_w_m2, f2.sensible_surface_to_air_w_m2);
    q.outgoing_longwave_j = fluence(f1.outgoing_longwave_w_m2, f2.outgoing_longwave_w_m2);
    q.surface_storage_j = in.column.area_m2 *
                          (trial.endpoint.surface_enthalpy_j_m2 - in.initial.surface_enthalpy_j_m2);
    q.air_storage_j = in.column.area_m2 *
                      (trial.endpoint.atmospheric_energy_j_m2 - in.initial.atmospheric_energy_j_m2);
    q.surface_component_residual_j = q.surface_storage_j - q.absorbed_shortwave_j -
                                     q.atmospheric_downward_longwave_j + q.surface_longwave_j +
                                     q.sensible_surface_to_air_j;
    q.air_component_residual_j = q.air_storage_j - q.atmospheric_absorbed_longwave_j +
                                 q.atmospheric_upward_longwave_j +
                                 q.atmospheric_downward_longwave_j - q.sensible_surface_to_air_j;
    q.combined_component_residual_j = q.surface_storage_j + q.air_storage_j -
                                      q.incident_shortwave_j + q.reflected_shortwave_j +
                                      q.outgoing_longwave_j;
    for (double v : {q.surface_storage_j, q.air_storage_j, q.surface_component_residual_j,
                     q.air_component_residual_j, q.combined_component_residual_j})
        need(finite(v), "representation_failure", "storage/component residual overflow");
    return q;
}
void retained_bounds_and_quadrature(const Input &in, Receipt &receipt) {
    if (!receipt.numerical_candidate_available)
        return;
    const auto &trial = receipt.trials.at(static_cast<std::size_t>(receipt.selected_trial));
    const auto computed = quadrature(in, trial);
    receipt.quadrature = computed;
    receipt.quadrature_available = true;
    const auto &actual = receipt.guard.physical_event_state;
    const I h_error = b::absolute(
        b::sub(b::point(trial.endpoint.surface_enthalpy_j_m2), actual.surface_enthalpy_j_m2));
    const I a_error = b::absolute(
        b::sub(b::point(trial.endpoint.atmospheric_energy_j_m2), actual.atmospheric_energy_j_m2));
    receipt.physical_event_state_error_j_m2 = b::add(h_error, a_error);
    receipt.direct_tube_state_error_j_m2 = receipt.physical_event_state_error_j_m2;
    receipt.direct_tube_error_available = true;
    if (in.endpoint_certificate == EndpointCertificate::hermite_residual) {
        build_hermite_residual(in, trial.endpoint, trial.duration_seconds, receipt.reconstruction);
        need(receipt.reconstruction.available, "reconstruction_unproved", "incomplete residual certificate");
        receipt.physical_event_state_error_j_m2 = receipt.reconstruction.endpoint_l1_error_j_m2;
    }
    receipt.physical_time_error_seconds =
        in.goal == Goal::next_phase_boundary
            ? b::absolute(b::sub(b::point(trial.duration_seconds),
                                 receipt.guard.physical_first_hit_seconds))
            : I{0, 0};
    receipt.physical_error_bounds_available = true;
    receipt.physical_budget_passed =
        receipt.physical_event_state_error_j_m2.upper <=
            in.budgets.maximum_physical_event_state_error_j_m2 &&
        receipt.physical_time_error_seconds.upper <= in.budgets.maximum_physical_time_error_seconds;
}
} // namespace

TubeProposalReceipt propose_fixed_duration_tube(const Input &skeleton, int maximum_passes) {
    TubeProposalReceipt out;
    out.maximum_passes = maximum_passes;
    try {
        need(maximum_passes > 0 && maximum_passes <= 8, "invalid_input", "automatic tube pass cap");
        Input in = skeleton;
        // These are derived proposal metadata, never caller-supplied authority.
        in.incoming_branch = in.water_mass_kg_m2 == 0 ? Branch::dry : Branch::mixed;
        in.proposed_tube = {};
        validate_input(in);
        need(in.goal == Goal::fixed_duration, "invalid_input", "automatic tube requires fixed duration");
        (void)make_clock(in);
        const Boundary boundary = latent_boundary(in);
        if (in.water_mass_kg_m2 > 0) {
            const double H = in.initial.surface_enthalpy_j_m2;
            in.incoming_branch = H < 0 ? Branch::solid
                : compare_boundary(H, boundary) <= 0 ? Branch::mixed : Branch::liquid;
        }
        const auto first = ideal_flux(in, in.initial, boundary);
        const bool air = in.column.atmospheric_heat_capacity_j_m2_k > 0;
        const auto pad = [](I range, double initial) {
            const double scale = std::max({1.0, std::abs(initial), b::absmax(range)});
            const double spacing = b::up(scale) - scale;
            const double excursion = b::absmax(b::sub(range, b::point(initial)));
            // This is only a deterministic proposal. The existing strict
            // outward Picard proof, not the padding formula, authorizes it.
            const double padding = std::max(16 * spacing, excursion * .125);
            need(finite(padding) && padding > 0, "representation_failure", "tube padding unavailable");
            return b::checked(b::down(range.lower - padding), b::up(range.upper + padding));
        };
        const auto predictor = [&](double initial, I rate) {
            return b::add(b::point(initial), b::mul({0, in.maximum_duration_seconds}, rate));
        };
        in.proposed_tube = {
            pad(predictor(in.initial.surface_enthalpy_j_m2, first.surface_net_w_m2), in.initial.surface_enthalpy_j_m2),
            air ? pad(predictor(in.initial.atmospheric_energy_j_m2, first.atmospheric_net_w_m2), in.initial.atmospheric_energy_j_m2)
                : I{0,0}};
        out.passes.reserve(static_cast<std::size_t>(maximum_passes));
        for (int i = 0; i < maximum_passes; ++i) {
            out.generated_input = in;
            out.input_available = true;
            ++out.passes_started;
            TubeProposalPass pass;
            pass.proposed_tube = in.proposed_tube;
            Receipt probe{};
            try {
                build_guard(in, probe, boundary);
                pass.guard = probe.guard;
                pass.accepted = true;
                out.passes.push_back(pass);
                out.accepted = true;
                return out;
            } catch (const Refusal &e) {
                pass.guard = probe.guard;
                pass.failure_code = e.code;
                out.passes.push_back(pass);
                if (e.code != "tube_unproved") throw;
            } catch (const std::bad_alloc &) { throw;
            } catch (const std::exception &) {
                pass.guard = probe.guard;
                pass.failure_code = "interval_or_internal_refusal";
                out.passes.push_back(pass);
                throw;
            }
            if (i + 1 == maximum_passes)
                throw Refusal("tube_unproved", "automatic Picard tube pass cap exhausted");
            in.proposed_tube = {
                pad(b::hull(in.proposed_tube.surface_enthalpy_j_m2, probe.guard.picard_image.surface_enthalpy_j_m2), in.initial.surface_enthalpy_j_m2),
                air ? pad(b::hull(in.proposed_tube.atmospheric_energy_j_m2, probe.guard.picard_image.atmospheric_energy_j_m2), in.initial.atmospheric_energy_j_m2)
                    : I{0,0}};
        }
    } catch (const std::bad_alloc &) { throw;
    } catch (const Refusal &e) {
        out.failure_code = e.code; out.detail = e.what();
    } catch (const std::exception &e) {
        out.failure_code = "interval_or_internal_refusal"; out.detail = e.what();
    }
    return out;
}

Receipt advance_phase_segment(const Input &in) {
    Receipt receipt{};
    receipt.request = in;
    try {
        validate_input(in);
        const Boundary boundary = latent_boundary(in);
        const Clock clock = make_clock(in);
        receipt.clock_quantum_seconds = clock.quantum;
        receipt.represented_gamma = represented_g;
        receipt.represented_second_weight = represented_b;
        receipt.nominal_gamma = b::gamma();
        build_guard(in, receipt, boundary);
        if (in.goal == Goal::within_branch || in.goal == Goal::fixed_duration) {
            const int index = duration_trial(in, in.maximum_duration_seconds, receipt, boundary);
            retain_selected(in, receipt, index);
            receipt.sampled_duration_locator_seconds = {in.maximum_duration_seconds,
                                                        in.maximum_duration_seconds};
            receipt.sampled_locator_available = true;
        } else {
            const int first = duration_trial(in, in.maximum_duration_seconds, receipt, boundary);
            retain_selected(in, receipt, first);
            std::uint64_t low = 0, high = clock.ticks;
            receipt.sampled_duration_locator_seconds = {0, in.maximum_duration_seconds};
            receipt.sampled_locator_available = true;
            const double initial_sign =
                receipt.guard.direction *
                receipt.trials[first].represented_surface_equation_defect_j_m2;
            need(initial_sign <= 0, "duration_locator_unresolved",
                 "sampled constrained equation does not change sign within horizon");
            while ((high - low) * clock.quantum > in.budgets.maximum_locator_width_seconds ||
                   (!receipt.numerical_budget_passed ||
                    !receipt.selected_first_stage_in_incoming_branch)) {
                const auto middle = low + (high - low) / 2;
                if (middle == low || middle == high)
                    break;
                const int index = duration_trial(in, static_cast<double>(middle) * clock.quantum,
                                                 receipt, boundary);
                if (prefer_trial(receipt.trials[index], receipt.trials[receipt.selected_trial]))
                    retain_selected(in, receipt, index);
                const double sign = receipt.guard.direction *
                                    receipt.trials[index].represented_surface_equation_defect_j_m2;
                if (sign > 0)
                    low = middle;
                else
                    high = middle;
                receipt.sampled_duration_locator_seconds = {
                    static_cast<double>(low) * clock.quantum,
                    static_cast<double>(high) * clock.quantum};
            }
            need((high - low) * clock.quantum <= in.budgets.maximum_locator_width_seconds,
                 "numerical_budget_refusal", "sampled duration locator resolution unmet");
        }
        retained_bounds_and_quadrature(in, receipt);
        need(in.goal == Goal::fixed_duration || receipt.selected_first_stage_in_incoming_branch,
             "stage_branch_refusal",
             "no eligible selected first stage in the incoming branch");
        need(receipt.numerical_budget_passed, "numerical_budget_refusal",
             "nominal equation defect budget unmet");
        need(receipt.physical_budget_passed, "physical_budget_refusal",
             in.endpoint_certificate == EndpointCertificate::direct_tube
                 ? "direct tube time or joint H/Ea budget unmet"
                 : "Hermite same-time joint H/Ea budget unmet");
        receipt.final_state = receipt.trials[receipt.selected_trial].endpoint;
        receipt.final_state_available = true;
        receipt.accepted = true;
    } catch (const Refusal &error) {
        receipt.failure_code = error.code;
        receipt.detail = error.what();
    } catch (const cryosphere_prototype::Error &error) {
        receipt.failure_code = "stage_domain_refusal";
        receipt.detail = error.what();
    } catch (const std::exception &error) {
        receipt.failure_code = "interval_or_internal_refusal";
        receipt.detail = error.what();
    }
    if (!receipt.accepted) {
        for (int j = 0; j < static_cast<int>(receipt.trials.size()); ++j) {
            if (receipt.trials[j].candidate_available &&
                (receipt.selected_trial < 0 ||
                 prefer_trial(receipt.trials[j], receipt.trials[receipt.selected_trial])))
                retain_selected(in, receipt, j);
        }
    }
    if (!receipt.accepted && receipt.numerical_candidate_available &&
        !receipt.quadrature_available) {
        try {
            retained_bounds_and_quadrature(in, receipt);
        } catch (const std::exception &) { /* Original refusal remains authoritative; availability
                                              flags stay honest. */
        }
    }
    receipt.selected_in_locator =
        receipt.numerical_candidate_available && receipt.sampled_locator_available &&
        receipt.selected_duration_seconds >= receipt.sampled_duration_locator_seconds.lower &&
        receipt.selected_duration_seconds <= receipt.sampled_duration_locator_seconds.upper;
    return receipt;
}
} // namespace phase_segment_prototype
