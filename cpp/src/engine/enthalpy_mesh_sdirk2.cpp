#include "enthalpy_mesh_sdirk2.hpp"
#include "terrestrial_thermal/outward.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <utility>

namespace magic_geo::detail {
namespace {
namespace b = phase_segment_prototype::bounds;
using I = EnthalpyMeshInterval;
using P = EnthalpyMeshPolynomial;
constexpr double sigma = 5.670374419e-8;
struct Refusal : std::runtime_error {
    std::string code;
    Refusal(const char* c, const char* why) : std::runtime_error(why), code(c) {}
};
void need(bool ok, const char* code, const char* why) { if (!ok) throw Refusal(code, why); }
int degree(const P& p) { return static_cast<int>(p.size()) - 1; }
constexpr int choose(int n, int k) {
    if (k < 0 || k > n) return 0;
    int v = 1;
    for (int j = 1; j <= k; ++j) v = v * (n - k + j) / j;
    return v;
}
I ratio(int a, int c) { return b::div(b::point(a), b::point(c)); }
P elevate(const P& p, int n) {
    const int m = degree(p);
    need(m >= 0 && m <= n && n <= 8, "enclosure_refusal", "polynomial degree cap");
    if (m == n) return p;
    P out(n + 1, b::point(0));
    for (int k = 0; k <= n; ++k)
        for (int i = std::max(0, k - (n - m)); i <= std::min(m, k); ++i)
            out[k] = b::add(out[k], b::mul(p[i], ratio(choose(m, i) * choose(n - m, k - i), choose(n, k))));
    return out;
}
P scale(P p, I s) { for (auto& x : p) x = b::mul(x, s); return p; }
P add(const P& p, const P& q) {
    const int n = std::max(degree(p), degree(q));
    P out = elevate(p, n); const P other = elevate(q, n);
    for (int i = 0; i <= n; ++i) out[i] = b::add(out[i], other[i]);
    return out;
}
P sub(const P& p, const P& q) { return add(p, scale(q, b::point(-1))); }
P product(const P& p, const P& q) {
    const int m = degree(p), n = degree(q), d = m + n;
    need(m >= 0 && n >= 0 && d <= 8, "enclosure_refusal", "polynomial product degree cap");
    P out(d + 1, b::point(0));
    for (int k = 0; k <= d; ++k)
        for (int i = std::max(0, k - n); i <= std::min(m, k); ++i)
            out[k] = b::add(out[k], b::mul(b::mul(p[i], q[k-i]), ratio(choose(m, i) * choose(n, k-i), choose(d, k))));
    return out;
}
P fourth(const P& p) { const P square = product(p, p); return product(square, square); }
I range(const P& p) { I out = p.front(); for (const I x : p) out = b::hull(out, x); return out; }
P derivative(const P& p) {
    P out(degree(p), b::point(0));
    for (int i = 0; i < degree(p); ++i) out[i] = b::mul(b::point(degree(p)), b::sub(p[i+1], p[i]));
    return out;
}
std::pair<P, P> split(const P& p) {
    // The exact de Casteljau result for a point-valued constant is the same
    // constant. Preserve this identity instead of widening a stationary curve
    // below the physical floor through redundant rounded additions.
    if (p.front().lower == p.front().upper && std::all_of(p.begin(), p.end(), [&](I x) {
        return x.lower == p.front().lower && x.upper == p.front().upper;
    })) return {p, p};
    const int n = degree(p); P temp = p, left(n+1), right(n+1);
    left[0] = temp[0]; right[n] = temp[n];
    for (int level = 1; level <= n; ++level) {
        for (int i = 0; i <= n-level; ++i) temp[i] = b::mul(b::add(temp[i], temp[i+1]), b::point(.5));
        left[level] = temp[0]; right[n-level] = temp[n-level];
    }
    return {std::move(left), std::move(right)};
}
I capacity(const EnthalpyMeshRequest& q, std::size_t i, bool liquid) {
    return b::add(b::point(q.columns[i].heat_capacity_j_m2_k), b::mul(b::point(q.water_mass_kg_m2[i]),
        b::point(liquid ? q.water.liquid_heat_capacity_j_kg_k : q.water.solid_heat_capacity_j_kg_k)));
}
I latent(const EnthalpyMeshRequest& q, std::size_t i) {
    return b::mul(b::point(q.water_mass_kg_m2[i]), b::point(q.water.latent_heat_j_kg));
}
P temperature(const EnthalpyMeshRequest& q, std::size_t i, const P& H, std::string& branch) {
    const P tf{b::point(q.water.freezing_temperature_k)};
    const I hr = range(H), L = latent(q, i);
    if (q.water_mass_kg_m2[i] == 0) {
        branch = "dry";
        return add(tf, scale(H, b::div(b::point(1), b::point(q.columns[i].heat_capacity_j_m2_k))));
    }
    if (hr.upper <= 0) {
        branch = "solid";
        return add(tf, scale(H, b::div(b::point(1), capacity(q, i, false))));
    }
    if (hr.lower >= 0 && hr.upper <= L.lower) { branch = "latent"; return tf; }
    if (hr.lower >= L.upper) {
        branch = "liquid";
        return add(tf, scale(sub(H, P{L}), b::div(b::point(1), capacity(q, i, true))));
    }
    // A degree-zero interval envelope remains valid pointwise even where no
    // single branch polynomial describes the whole leaf. Its wider residual
    // may refuse the requested budget; it never asserts smoothness at phase.
    branch = "phase_range";
    const I cold{std::min(0.0, hr.lower), std::min(0.0, hr.upper)};
    const I excess = b::sub(hr, L);
    const I warm{std::max(0.0, excess.lower), std::max(0.0, excess.upper)};
    const I value = b::add(tf[0], b::add(b::div(cold, capacity(q, i, false)), b::div(warm, capacity(q, i, true))));
    need(value.upper >= 0, "physical_curve_refusal", "temperature range contains no physical value");
    return P{b::checked(std::max(0.0, value.lower), value.upper)};
}
std::vector<P> heating(const EnthalpyMeshRequest& q, const std::vector<P>& T) {
    const auto n = T.size(); std::vector<P> out(n), exchange(n, P{b::point(0)});
    for (const auto& e : q.edges) {
        const P watts = scale(sub(T[e.second_cell], T[e.first_cell]), b::point(e.conductance_w_k));
        exchange[e.first_cell] = add(exchange[e.first_cell], watts);
        exchange[e.second_cell] = sub(exchange[e.second_cell], watts);
    }
    for (std::size_t i = 0; i < n; ++i) {
        const P radiation = scale(fourth(T[i]), b::mul(b::point(q.columns[i].longwave_emissivity), b::point(sigma)));
        out[i] = add(sub(P{b::point(q.absorbed_shortwave_w_m2[i])}, radiation),
            scale(exchange[i], b::div(b::point(1), b::point(q.columns[i].area_m2))));
    }
    return out;
}
void count(EnthalpyMeshSdirk2Receipt& r, const EnthalpyMeshReceipt& s) {
    r.scalar_evaluations += s.scalar_evaluations; r.field_evaluations += s.field_evaluations;
    r.sweeps_started += s.sweeps_started; r.coordinate_solves_started += s.coordinate_solves_started;
    r.backward_euler_leaves_started += s.leaves_started;
}
void certify(const EnthalpyMeshRequest& q, EnthalpyMeshSdirk2Receipt& r) {
    const auto n = q.columns.size(); const int N = q.options.reconstruction_leaves;
    std::vector<P> initial_T(n);
    for (std::size_t i = 0; i < n; ++i) {
        std::string branch;
        initial_T[i] = temperature(q, i, P{b::point(q.initial_enthalpy_j_m2[i])}, branch);
    }
    ++r.field_evaluations;
    const auto F0 = heating(q, initial_T);
    r.initial_heating_w_m2.resize(n);
    std::vector<std::vector<P>> curves(1, std::vector<P>(n));
    const auto& final = *r.second_stage->final_enthalpy_j_m2;
    for (std::size_t i = 0; i < n; ++i) {
        const I f = range(F0[i]); r.initial_heating_w_m2[i] = std::midpoint(f.lower, f.upper);
        const I start = b::point(q.initial_enthalpy_j_m2[i]);
        curves[0][i] = {start, b::add(start, b::mul(b::point(.5),
            b::mul(b::point(q.options.duration_seconds), b::point(r.initial_heating_w_m2[i])))), b::point(final[i])};
    }
    for (int count_leaves = 1; count_leaves < N; count_leaves *= 2) {
        std::vector<std::vector<P>> next(2*count_leaves, std::vector<P>(n));
        for (int j = 0; j < count_leaves; ++j) for (std::size_t i = 0; i < n; ++i) {
            auto [left, right] = split(curves[j][i]);
            next[2*j][i] = std::move(left); next[2*j+1][i] = std::move(right);
        }
        curves = std::move(next);
    }
    const I leaf_duration = b::div(b::point(q.options.duration_seconds), b::point(N));
    I total = b::point(0);
    for (int j = 0; j < N; ++j) {
        ++r.certificate_leaves_started;
        r.leaves.emplace_back(); auto& leaf = r.leaves.back(); leaf.index = j;
        leaf.enthalpy = std::move(curves[j]); leaf.temperature.resize(n); leaf.temperature_branch.resize(n);
        for (std::size_t i = 0; i < n; ++i) {
            need(range(leaf.enthalpy[i]).lower >= r.first_stage->physical_floor_j_m2[i].upper,
                 "physical_curve_refusal", "quadratic reconstruction physical floor not proved");
            leaf.temperature[i] = temperature(q, i, leaf.enthalpy[i], leaf.temperature_branch[i]);
        }
        ++r.field_evaluations;
        const auto F = heating(q, leaf.temperature); leaf.residual.resize(n);
        leaf.absolute_residual_integral_upper_j_m2.resize(n);
        I weighted = b::point(0);
        for (std::size_t i = 0; i < n; ++i) {
            leaf.residual[i] = sub(derivative(leaf.enthalpy[i]), scale(F[i], leaf_duration));
            I absolute_sum = b::point(0);
            for (const I coefficient : leaf.residual[i]) absolute_sum = b::add(absolute_sum, b::point(b::absmax(coefficient)));
            const double bound = b::div(absolute_sum, b::point(leaf.residual[i].size())).upper;
            leaf.absolute_residual_integral_upper_j_m2[i] = bound;
            weighted = b::add(weighted, b::mul(b::point(q.columns[i].area_m2), b::point(bound)));
        }
        leaf.weighted_residual_upper_j = weighted.upper; leaf.complete = true;
        total = b::add(total, b::point(weighted.upper));
    }
    r.physical_curve_proved = true; r.local_endpoint_error_upper_j = total.upper; r.endpoint_error_available = true;
}
} // namespace

EnthalpyMeshSdirk2Receipt advance_enthalpy_mesh_sdirk2(const EnthalpyMeshRequest& q) {
    EnthalpyMeshSdirk2Receipt r;
    try {
        need(q.columns.size() <= 16384 && q.edges.size() <= 131072 && q.water_mass_kg_m2.size() <= 16384 &&
             q.initial_enthalpy_j_m2.size() <= 16384 && q.absorbed_shortwave_w_m2.size() <= 16384,
             "invalid_input", "request retention cap");
        r.request = q;
        const auto& o = q.options;
        need(std::isfinite(o.duration_seconds) && o.duration_seconds > 0 &&
             std::isfinite(o.maximum_endpoint_error_j) && o.maximum_endpoint_error_j > 0,
             "invalid_input", "positive finite duration and endpoint budget required");
        need(o.reconstruction_leaves > 0 && o.reconstruction_leaves <= 64 &&
             (o.reconstruction_leaves & (o.reconstruction_leaves - 1)) == 0,
             "work_cap", "bounded dyadic leaf count required");
        need(q.columns.size() <= 4194304 / (15*static_cast<std::size_t>(o.reconstruction_leaves)),
             "work_cap", "retained polynomial coefficient cap");
        // Fixed represented coefficient, not an assertion of an exact
        // irrational tableau. Both durations and the second base are raw
        // binary64 proposals; the independent ODE residual owns their defects.
        r.gamma = 0x1.2bec333018867p-2;
        r.diagonal_duration_seconds = r.gamma * o.duration_seconds;
        r.off_diagonal_duration_seconds = (1-r.gamma) * o.duration_seconds;
        need(std::isfinite(r.diagonal_duration_seconds) && r.diagonal_duration_seconds > 0 &&
             std::isfinite(r.off_diagonal_duration_seconds) && r.off_diagonal_duration_seconds > 0,
             "invalid_input", "represented stage duration underflow or overflow");
        EnthalpyMeshRequest stage = q;
        stage.options.duration_seconds = r.diagonal_duration_seconds;
        stage.options.maximum_endpoint_error_j = std::numeric_limits<double>::max();
        stage.options.reconstruction_leaves = 1;
        ++r.stage_calls_started; r.first_stage = advance_enthalpy_mesh(stage); count(r, *r.first_stage);
        need(r.first_stage->accepted, "first_stage_refusal", "first physical BE primitive refused; see nested receipt");
        r.duration_sum_defect_seconds = b::sub(b::add(b::point(r.diagonal_duration_seconds),
            b::point(r.off_diagonal_duration_seconds)), b::point(o.duration_seconds));
        const I a = b::div(b::point(r.diagonal_duration_seconds), b::point(o.duration_seconds));
        const I beta = b::div(b::point(r.off_diagonal_duration_seconds), b::point(o.duration_seconds));
        r.second_order_coefficient_defect = b::sub(b::mul(a, b::add(a, b::mul(b::point(2), beta))), b::point(.5));
        r.tableau_bridges_available = true;
        r.first_stage_heating_w_m2.resize(q.columns.size()); r.second_stage_base_j_m2.resize(q.columns.size());
        r.second_stage_base_defect_j_m2.resize(q.columns.size());
        for (std::size_t i = 0; i < q.columns.size(); ++i) {
            const I f = r.first_stage->candidate_field.net_heating_w_m2[i];
            r.first_stage_heating_w_m2[i] = std::midpoint(f.lower, f.upper);
            const double increment = r.off_diagonal_duration_seconds * r.first_stage_heating_w_m2[i];
            r.second_stage_base_j_m2[i] = q.initial_enthalpy_j_m2[i] + increment;
            r.second_stage_base_defect_j_m2[i] = b::sub(b::point(r.second_stage_base_j_m2[i]),
                b::add(b::point(q.initial_enthalpy_j_m2[i]), b::mul(b::point(r.off_diagonal_duration_seconds), f)));
        }
        need(r.scalar_evaluations < o.maximum_scalar_evaluations, "work_cap", "shared scalar allowance exhausted before stage two");
        stage.initial_enthalpy_j_m2 = r.second_stage_base_j_m2;
        stage.options.maximum_sweeps = o.maximum_sweeps-r.sweeps_started;
        stage.options.maximum_scalar_evaluations = o.maximum_scalar_evaluations-r.scalar_evaluations;
        ++r.stage_calls_started; r.second_stage = advance_enthalpy_mesh(stage); count(r, *r.second_stage);
        need(r.second_stage->accepted, "second_stage_refusal", "second physical BE primitive refused; see nested receipt");
        certify(q, r);
        need(r.local_endpoint_error_upper_j <= o.maximum_endpoint_error_j, "endpoint_budget_refusal", "quadratic residual exceeds same-time endpoint target");
        r.final_enthalpy_j_m2 = *r.second_stage->final_enthalpy_j_m2; r.accepted = true;
    } catch (const std::bad_alloc&) { throw;
    } catch (const Refusal& e) { r.failure_code = e.code; r.detail = e.what();
    } catch (const std::exception& e) { r.failure_code = "enclosure_refusal"; r.detail = e.what(); }
    return r;
}
} // namespace magic_geo::detail
