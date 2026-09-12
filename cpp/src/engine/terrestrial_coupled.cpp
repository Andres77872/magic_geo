#include "terrestrial_coupled.hpp"
#include "terrestrial_thermal/outward.hpp"

#include <algorithm>
#include <bit>
#include <cfloat>
#include <cfenv>
#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <set>
#include <sstream>
#include <utility>

#if !defined(MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER) && LDBL_MANT_DIG >= 64 && LDBL_MAX_EXP >= 16384
#define COUPLED_HAS_A 1
#else
#define COUPLED_HAS_A 0
#endif

namespace magic_geo::detail {
namespace {
namespace a = cryosphere_prototype;
namespace p = phase_segment_prototype;
namespace t = higher_order_thermal_prototype;
namespace b = p::bounds;

void need(bool condition, const char* code, const std::string& detail) {
    if (!condition) throw TerrestrialWaterError(code, detail);
}
bool finite(double x) { return std::isfinite(x); }
bool same(double x, double y) {
    return std::bit_cast<std::uint64_t>(x) == std::bit_cast<std::uint64_t>(y);
}
bool exposed(const Cell& cell) { return !cell.is_water && !cell.is_lake; }
void arithmetic_capability() {
    need(std::numeric_limits<double>::is_iec559 && std::numeric_limits<double>::digits == 53 &&
         std::fegetround() == FE_TONEAREST,"capability_unavailable","binary64 nearest arithmetic required");
    volatile double minimum_normal = std::numeric_limits<double>::min();
    volatile double minimum_subnormal = std::numeric_limits<double>::denorm_min();
    volatile double tenth = 0.1;
    volatile double one = 1.0;
    volatile double inexact_subnormal = minimum_normal*tenth;
    volatile double retained_subnormal = minimum_subnormal*one;
    need(inexact_subnormal > 0 && retained_subnormal > 0,"capability_unavailable",
         "gradual binary64 arithmetic required; FTZ/DAZ unsupported");
}
void positive(double x, const char* name) {
    need(finite(x) && x > 0, "invalid_input", std::string(name)+" must be finite and positive");
}
void identifier(const std::string& id, std::size_t cap) {
    need(!id.empty() && id.size() <= cap, "invalid_identifier", "identifier length");
    for (const unsigned char ch : id)
        need(ch >= 33 && ch <= 126, "invalid_identifier", "identifier must be visible ASCII");
}
bool exact_sum(double x, double y, double result) {
    if (!finite(result) || x+y != result) return false;
    const double bp = result-x;
    return (x-(result-bp))+(y-bp) == 0;
}
double duration(double start, double end) {
    need(finite(start) && finite(end) && start >= 0 && end > start,
         "clock_refusal", "nonincreasing or nonfinite interval");
    const double result = end-start;
    need(finite(result) && result > 0 && exact_sum(start, result, end),
         "clock_refusal", "duration does not close the exact clock");
    return result;
}
void lattice(double x, double quantum) {
    const double ticks = x/quantum;
    need(finite(ticks) && ticks >= 0 && ticks <= 9007199254740992.0 &&
             ticks == std::floor(ticks) && ticks*quantum == x,
         "clock_refusal", "clock is not on common endpoint lattice");
}
void increment(std::uint64_t& value, std::uint64_t amount = 1) {
    need(amount <= std::numeric_limits<std::uint64_t>::max()-value,
         "work_cap", "work counter overflow");
    value += amount;
}
t::Column column(const TerrestrialSurfaceSnapshot& surface, const CoupledProperties& props,
                 std::size_t i) {
    const auto& c = props.columns[i];
    return {surface.cells()[i].area_km2*1e6, c.dry_heat_capacity_j_m2_k,
            c.atmospheric_heat_capacity_j_m2_k, c.atmospheric_longwave_absorptivity,
            c.sensible_exchange_w_m2_k, c.surface_shortwave_albedo};
}
p::Energy energy(const CoupledColumnState& state) {
    return {state.surface_enthalpy_j_m2, state.atmospheric_energy_j_m2};
}
void limits_valid(const CoupledLimits& x) {
    const CoupledLimits cap;
#define CHECK_LIMIT(name) need(x.name > 0 && x.name <= cap.name, "invalid_limits", #name)
    CHECK_LIMIT(max_cells); CHECK_LIMIT(max_committed_intervals); CHECK_LIMIT(max_prepare_attempts);
    CHECK_LIMIT(max_events_per_interval); CHECK_LIMIT(max_consumed_event_ids); CHECK_LIMIT(max_identifier_bytes);
    CHECK_LIMIT(max_segments_per_cell); CHECK_LIMIT(max_segment_calls); CHECK_LIMIT(max_duration_trials);
    CHECK_LIMIT(max_stage_calls); CHECK_LIMIT(max_flux_evaluations);
    CHECK_LIMIT(max_reconstruction_leaves);
#undef CHECK_LIMIT
}
void forcing_valid(const CoupledForcingSpan& f, const TerrestrialSurfaceSnapshot& surface,
                   const CoupledLimits& limits) {
    identifier(f.id, std::min<std::size_t>(limits.max_identifier_bytes,64));
    (void)duration(f.begin_seconds, f.end_seconds);
    need(f.incident_shortwave_w_m2.size() == surface.cells().size(), "forcing_refusal", "forcing coverage");
    for (std::size_t i = 0; i < surface.cells().size(); ++i) {
        const double value = f.incident_shortwave_w_m2[i];
        need(finite(value) && value >= 0, "forcing_refusal", "invalid shortwave");
        need(exposed(surface.cells()[i]) || value == 0, "forcing_refusal", "wet shortwave must be zero");
    }
}
bool same_forcing(const CoupledForcingSpan& x, const CoupledForcingSpan& y) {
    if (x.id != y.id || !same(x.begin_seconds,y.begin_seconds) || !same(x.end_seconds,y.end_seconds) ||
        x.incident_shortwave_w_m2.size() != y.incident_shortwave_w_m2.size()) return false;
    for (std::size_t i = 0; i < x.incident_shortwave_w_m2.size(); ++i)
        if (!same(x.incident_shortwave_w_m2[i],y.incident_shortwave_w_m2[i])) return false;
    return true;
}
void compare_forcing(const CoupledForcingSpan& fresh, const CoupledForcingSpan& old) {
    if (fresh.id == old.id)
        need(same_forcing(fresh,old), "forcing_identity_refusal", "source ID changed its operands");
    else
        need(std::max(fresh.begin_seconds,old.begin_seconds) >= std::min(fresh.end_seconds,old.end_seconds),
             "forcing_identity_refusal", "distinct source windows overlap");
}
void plan_segment_valid(const CoupledSegmentPlan& s, const CoupledLimits& limits) {
    identifier(s.id, std::min<std::size_t>(limits.max_identifier_bytes,64));
    need(s.incoming_branch == p::Branch::dry || s.incoming_branch == p::Branch::solid ||
         s.incoming_branch == p::Branch::mixed || s.incoming_branch == p::Branch::liquid,
         "invalid_plan", "unknown incoming branch");
    need(s.goal == p::Goal::within_branch || s.goal == p::Goal::next_phase_boundary ||
         s.goal == p::Goal::fixed_duration,
         "invalid_plan", "unknown segment goal");
    need((s.endpoint_certificate == p::EndpointCertificate::direct_tube && s.reconstruction_leaves == 0) ||
         (s.endpoint_certificate == p::EndpointCertificate::hermite_residual &&
          s.goal == p::Goal::fixed_duration && s.reconstruction_leaves > 0 && s.reconstruction_leaves <= 64 &&
          (s.reconstruction_leaves & (s.reconstruction_leaves-1)) == 0),
         "invalid_plan", "endpoint certificate policy or dyadic work count invalid");
    for (const auto bound : {s.tube.surface_enthalpy_j_m2,s.tube.atmospheric_energy_j_m2})
        need(finite(bound.lower) && finite(bound.upper) && bound.lower <= bound.upper,
             "invalid_plan", "invalid proposed tube");
    positive(s.budgets.maximum_numerical_equation_defect_j_m2,"numerical defect budget");
    positive(s.budgets.maximum_locator_width_seconds,"locator budget");
    positive(s.budgets.maximum_physical_time_error_seconds,"time budget");
    positive(s.budgets.maximum_physical_event_state_error_j_m2,"state budget");
    need(s.work.maximum_duration_trials > 0 && s.work.maximum_duration_trials <= 64 &&
         s.work.maximum_air_iterations_per_trial > 0 && s.work.maximum_air_iterations_per_trial <= 96 &&
         s.work.maximum_stage_calls > 0 && s.work.maximum_stage_calls <= 64 &&
         s.work.maximum_total_flux_evaluations > 0 && s.work.maximum_total_flux_evaluations <= 32768,
         "work_cap", "segment work bounds");
    positive(s.stage_options.absolute_tolerance_w_m2,"stage absolute tolerance");
    need(finite(s.stage_options.relative_tolerance) && s.stage_options.relative_tolerance >= 0 &&
         s.stage_options.relative_tolerance <= 1 && s.stage_options.maximum_newton_iterations >= 0 &&
         s.stage_options.maximum_newton_iterations <= 100 && s.stage_options.maximum_backtracks >= 0 &&
         s.stage_options.maximum_backtracks <= 100, "invalid_plan", "stage options");
}
// Both owners use the same initial-inventory validation and canonical A jump.
std::set<std::string> validate_initial_events(
    const std::vector<TerrestrialPrecipitationImport>& imports,
    const std::vector<TerrestrialLiquidWithdrawal>& initial_liquid_withdrawals,
    const std::vector<Cell>& cs, const CoupledProperties& props,
    const CoupledRestart& initial, const CoupledLimits& limits) {
    const std::size_t event_count = imports.size()+initial_liquid_withdrawals.size();
    need(event_count <= limits.max_events_per_interval &&
         event_count <= limits.max_consumed_event_ids-initial.consumed_event_ids.size(),
         "event_cap","event count or retained ID cap");
    std::set<std::string> ids(initial.consumed_event_ids.begin(),initial.consumed_event_ids.end());
    const auto event_valid = [&](const std::string& id, int cell_id, double mass) {
        identifier(id,limits.max_identifier_bytes);
        need(ids.insert(id).second,"duplicate_event","event already consumed or repeated");
        need(cell_id >= 0 && static_cast<std::size_t>(cell_id) < cs.size() && exposed(cs[cell_id]),
             "invalid_event","wet or unknown event cell");
        positive(mass,"event mass");
    };
    for (const auto& x : imports) {
        event_valid(x.id,x.cell_id,x.mass_kg);
        need(finite(x.temperature_k) && x.temperature_k >= 0 &&
             ((x.phase == a::Phase::solid && x.temperature_k <= props.water.freezing_temperature_k) ||
              (x.phase == a::Phase::liquid && x.temperature_k >= props.water.freezing_temperature_k)),
             "invalid_event","import phase/temperature mismatch");
    }
    for (const auto& x : initial_liquid_withdrawals) event_valid(x.id,x.cell_id,x.mass_kg);
    return ids;
}
void apply_initial_events(
    const std::vector<TerrestrialPrecipitationImport>& imports,
    const std::vector<TerrestrialLiquidWithdrawal>& initial_liquid_withdrawals,
    const TerrestrialSurfaceSnapshot& surface, const CoupledProperties& props,
    const CoupledRestart& initial, double budget, CoupledWorkMeter& work,
    CoupledAttemptReceipt& r) {
    const auto& cs = surface.cells();
    const std::size_t event_count = imports.size()+initial_liquid_withdrawals.size();
    std::vector<int> kernel_map(cs.size(),-1);
    r.mass_error.resize(cs.size());
    std::vector<CoupledColumnState> post_mass = initial.state;
    for (std::size_t i = 0; i < cs.size(); ++i) {
        const bool active = exposed(cs[i]);
        if (active) {
            kernel_map[i] = static_cast<int>(r.kernel_columns.size());
            r.kernel_column_cell_ids.push_back(static_cast<int>(i));
            r.kernel_columns.push_back({cs[i].area_km2*1e6,props.columns[i].dry_heat_capacity_j_m2_k});
            r.kernel_initial.push_back({initial.state[i].water_mass_kg_m2,initial.state[i].surface_enthalpy_j_m2});
        }
    }
    for (const auto& x : imports)
        r.mass_request.imports.push_back({static_cast<std::size_t>(kernel_map[x.cell_id]),x.phase,x.mass_kg,x.temperature_k});
    for (const auto& x : initial_liquid_withdrawals)
        r.mass_request.exports.push_back({static_cast<std::size_t>(kernel_map[x.cell_id]),a::Phase::liquid,x.mass_kg});
    r.mass_request_available = event_count != 0;
    if (event_count != 0) {
        increment(work.mass_calls_started);
        r.mass_call_started = true;
#if COUPLED_HAS_A
        try {
            r.mass_receipt = a::apply_mass_events(props.water,r.kernel_columns,r.kernel_initial,r.mass_request);
        } catch (const a::Error& e) {
            throw TerrestrialWaterError("mass_refused",e.what());
        }
#else
        throw TerrestrialWaterError("capability_unavailable","calorimeter backend unavailable");
#endif
        increment(work.mass_calls_returned);
        r.mass_receipt_available = true;
        need(r.mass_receipt.state.size() == r.kernel_column_cell_ids.size(),"mass_protocol_refusal","state coverage");
        for (std::size_t j = 0; j < r.kernel_column_cell_ids.size(); ++j) {
            auto& x = post_mass[r.kernel_column_cell_ids[j]];
            x.water_mass_kg_m2 = r.mass_receipt.state[j].water_mass_kg_m2;
            x.surface_enthalpy_j_m2 = r.mass_receipt.state[j].enthalpy_j_m2;
        }
    }
    r.private_prefix.state = post_mass;
    std::vector<std::vector<CanonicalMovement>> canonical_imports(cs.size()), withdrawals(cs.size());
    std::vector<bool> used(r.mass_receipt.movements.size(),false);
    for (const auto& x : imports) {
        bool found = false;
        for (std::size_t j = 0; j < used.size(); ++j) {
            const auto& m = r.mass_receipt.movements[j];
            if (!used[j] && m.donor == -1 && m.recipient == kernel_map[x.cell_id] && m.phase == x.phase &&
                same(m.mass_kg,x.mass_kg) && same(m.temperature_k,x.temperature_k)) {
                used[j] = true; found = true;
                canonical_imports[x.cell_id].push_back({m.mass_kg,m.carried_enthalpy_j});
                break;
            }
        }
        need(found,"mass_protocol_refusal","import identity linkage missing");
    }
    for (const auto& x : initial_liquid_withdrawals) {
        bool found = false;
        for (std::size_t j = 0; j < used.size(); ++j) {
            const auto& m = r.mass_receipt.movements[j];
            if (!used[j] && m.donor == kernel_map[x.cell_id] && m.recipient == -1 &&
                m.phase == a::Phase::liquid && same(m.mass_kg,x.mass_kg)) {
                used[j] = true; found = true;
                withdrawals[x.cell_id].push_back({m.mass_kg,m.carried_enthalpy_j});
                r.private_liquid_outbox.push_back({x.id,x.cell_id,m.mass_kg,m.carried_enthalpy_j,j});
                break;
            }
        }
        need(found,"mass_protocol_refusal","withdrawal identity linkage missing");
    }
    need(std::all_of(used.begin(),used.end(),[](bool x){return x;}),"mass_protocol_refusal","unlinked movement");
    for (std::size_t i = 0; i < cs.size(); ++i) {
        if (!exposed(cs[i])) continue;
        need(same(post_mass[i].atmospheric_energy_j_m2,initial.state[i].atmospheric_energy_j_m2),
             "mass_protocol_refusal","mass event changed Ea");
        r.mass_error[i] = certify_canonical_jump(props.water,column(surface,props,i),
            initial.state[i].water_mass_kg_m2,energy(initial.state[i]),post_mass[i].water_mass_kg_m2,
            energy(post_mass[i]),initial.canonical_energy_error_j_m2[i],canonical_imports[i],withdrawals[i],
            budget);
        const auto& cert = r.mass_error[i];
        need(cert.accepted,"error_budget_refused",cert.failure_code+": "+cert.detail);
        r.private_prefix.canonical_energy_error_j_m2[i] = cert.final_error_j_m2;
    }
}
struct Bundle {
    CoupledRestart restart;
    std::size_t committed_intervals = 0;
    std::shared_ptr<const CoupledAttemptReceipt> last;
};
void add_finite(double& sum, double term) {
    need(finite(term), "ledger_refusal", "nonfinite ledger term");
    sum += term;
    need(finite(sum), "ledger_refusal", "ledger accumulation overflow");
}
} // namespace

struct CoupledIntervalCandidate::Data {
    std::shared_ptr<const int> owner;
    std::shared_ptr<const Bundle> base, replacement;
};
CoupledIntervalCandidate::CoupledIntervalCandidate(std::shared_ptr<const Data> data) : data_(std::move(data)) {}
const CoupledAttemptReceipt& CoupledIntervalCandidate::receipt() const { return *data_->replacement->last; }
struct TerrestrialCoupledOwner::Impl {
    TerrestrialSurfaceSnapshot surface;
    CoupledProperties properties;
    CoupledAcceptancePolicy policy;
    CoupledLimits limits;
    CoupledWorkMeter work;
    std::shared_ptr<const int> anchor = std::make_shared<const int>(0);
    std::shared_ptr<const Bundle> accepted;
    Impl(TerrestrialSurfaceSnapshot s, CoupledProperties p, CoupledAcceptancePolicy a, CoupledLimits l)
        : surface(std::move(s)), properties(std::move(p)), policy(a), limits(l) {}
};
TerrestrialCoupledOwner::TerrestrialCoupledOwner(TerrestrialSurfaceSnapshot surface, CoupledProperties props,
    CoupledRestart initial, CoupledAcceptancePolicy policy, CoupledLimits limits)
    : impl_(std::make_unique<Impl>(std::move(surface),std::move(props),policy,limits)) {
    need(terrestrial_water_capability().available, "capability_unavailable", terrestrial_water_capability().reason);
    arithmetic_capability();
    limits_valid(limits);
    positive(policy.max_joint_energy_error_j_m2,"maximum joint energy error");
    const auto& cs = impl_->surface.cells();
    const auto& p = impl_->properties;
    need(cs.size() <= limits.max_cells && p.columns.size() == cs.size() &&
         initial.state.size() == cs.size() && initial.canonical_energy_error_j_m2.size() == cs.size(),
         "invalid_restart", "complete cell/state/property/error coverage required");
    positive(p.reference_water_density_kg_m3,"reference water density");
    positive(p.year_duration_seconds,"year duration");
    positive(p.water.freezing_temperature_k,"freezing temperature");
    positive(p.water.solid_heat_capacity_j_kg_k,"solid heat capacity");
    positive(p.water.liquid_heat_capacity_j_kg_k,"liquid heat capacity");
    positive(p.water.latent_heat_j_kg,"latent heat");
    need(finite(initial.elapsed_seconds) && initial.elapsed_seconds >= 0,"invalid_restart","elapsed seconds");
    need(initial.consumed_event_ids.size() <= limits.max_consumed_event_ids &&
         initial.forcing_history.size() <= limits.max_committed_intervals,"invalid_restart","history caps");
    std::set<std::string> ids;
    for (const auto& id : initial.consumed_event_ids) {
        identifier(id,limits.max_identifier_bytes);
        need(ids.insert(id).second,"duplicate_event","restart event ID repeated");
    }
    std::set<std::string> forcing_ids;
    for (std::size_t i = 0; i < initial.forcing_history.size(); ++i) {
        const auto& f = initial.forcing_history[i];
        forcing_valid(f,impl_->surface,limits);
        need(forcing_ids.insert(f.id).second,"invalid_restart","duplicate forcing history");
        for (std::size_t j = 0; j < i; ++j) compare_forcing(f,initial.forcing_history[j]);
    }
    for (std::size_t i = 0; i < cs.size(); ++i) {
        const auto& x = initial.state[i];
        const auto& c = p.columns[i];
        const double e = initial.canonical_energy_error_j_m2[i];
        need(finite(x.water_mass_kg_m2) && x.water_mass_kg_m2 >= 0 && finite(x.surface_enthalpy_j_m2) &&
             finite(x.atmospheric_energy_j_m2) && finite(e) && e >= 0 && e <= policy.max_joint_energy_error_j_m2,
             "invalid_restart","invalid state or inherited error");
        for (double v : {c.dry_heat_capacity_j_m2_k,c.atmospheric_heat_capacity_j_m2_k,
                         c.atmospheric_longwave_absorptivity,c.sensible_exchange_w_m2_k,c.surface_shortwave_albedo})
            need(finite(v) && v >= 0,"invalid_restart","invalid column coefficient");
        if (!exposed(cs[i])) {
            need(x.water_mass_kg_m2 == 0 && x.surface_enthalpy_j_m2 == 0 && x.atmospheric_energy_j_m2 == 0 &&
                 e == 0 && c.dry_heat_capacity_j_m2_k == 0 && c.atmospheric_heat_capacity_j_m2_k == 0 &&
                 c.atmospheric_longwave_absorptivity == 0 && c.sensible_exchange_w_m2_k == 0 &&
                 c.surface_shortwave_albedo == 0,"invalid_restart","wet state/property/error must be zero");
        } else {
            need(c.dry_heat_capacity_j_m2_k > 0 && c.atmospheric_longwave_absorptivity <= 1 &&
                 c.surface_shortwave_albedo <= 1 && (c.atmospheric_heat_capacity_j_m2_k > 0 ||
                 (x.atmospheric_energy_j_m2 == 0 && c.atmospheric_longwave_absorptivity == 0 &&
                  c.sensible_exchange_w_m2_k == 0)),"invalid_restart","thermal parameter domain");
            const auto domain = certify_coupled_domain(p.water,column(impl_->surface,p,i),
                                                       x.water_mass_kg_m2,energy(x),e);
            need(domain.accepted,"invalid_restart",domain.failure_code+": "+domain.detail);
        }
    }
    impl_->accepted = std::make_shared<const Bundle>(Bundle{std::move(initial),0,{}});
}
TerrestrialCoupledOwner::~TerrestrialCoupledOwner() = default;
TerrestrialCoupledOwner::TerrestrialCoupledOwner(TerrestrialCoupledOwner&&) noexcept = default;
TerrestrialCoupledOwner& TerrestrialCoupledOwner::operator=(TerrestrialCoupledOwner&&) noexcept = default;
const TerrestrialSurfaceSnapshot& TerrestrialCoupledOwner::surface() const { return impl_->surface; }
const CoupledProperties& TerrestrialCoupledOwner::properties() const { return impl_->properties; }
const CoupledAcceptancePolicy& TerrestrialCoupledOwner::acceptance_policy() const { return impl_->policy; }
const CoupledLimits& TerrestrialCoupledOwner::limits() const { return impl_->limits; }
const CoupledRestart& TerrestrialCoupledOwner::restart() const { return impl_->accepted->restart; }
const CoupledWorkMeter& TerrestrialCoupledOwner::work_meter() const { return impl_->work; }
const CoupledAttemptReceipt* TerrestrialCoupledOwner::last_receipt() const { return impl_->accepted->last.get(); }

CoupledPreparation TerrestrialCoupledOwner::prepare(const CoupledIntervalPlan& request) {
    const auto base = impl_->accepted;
    const auto& initial = base->restart;
    const auto& cs = impl_->surface.cells();
    const auto& props = impl_->properties;
    const auto& limits = impl_->limits;
    auto& work = impl_->work;
    CoupledAttemptReceipt r;
    r.surface_revision = impl_->surface.surface_revision();
    r.properties = props;
    r.acceptance_policy = impl_->policy;
    r.limits = limits;
    r.surface_cells = cs;
    r.initial = initial;
    r.private_prefix = initial;
    r.work_before = work;
    try {
        increment(work.prepare_attempts);
        arithmetic_capability();
        // Retain bounded malformed requests too. Coverage/domain validation
        // below may refuse them before any physical call.
        bool bounded_request = request.imports.size() <= limits.max_events_per_interval &&
            request.initial_liquid_withdrawals.size() <= limits.max_events_per_interval &&
            request.columns.size() <= limits.max_cells &&
            request.forcing.incident_shortwave_w_m2.size() <= limits.max_cells &&
            request.forcing.id.size() <= limits.max_identifier_bytes;
        need(bounded_request,"invalid_plan","request retention cap");
        for (const auto& x : request.imports)
            bounded_request = bounded_request && x.id.size() <= limits.max_identifier_bytes;
        for (const auto& x : request.initial_liquid_withdrawals)
            bounded_request = bounded_request && x.id.size() <= limits.max_identifier_bytes;
        for (const auto& x : request.columns) {
            need(x.segments.size() <= limits.max_segments_per_cell,"invalid_plan","request retention cap");
            for (const auto& s : x.segments)
                bounded_request = bounded_request && s.id.size() <= limits.max_identifier_bytes;
        }
        need(bounded_request,"invalid_plan","request retention cap");
        r.request = request;
        r.request_available = true;
        need(work.prepare_attempts <= limits.max_prepare_attempts,"work_cap","prepare attempt cap");
        need(request.expected_revision == initial.revision,"stale_revision","request revision mismatch");
        need(initial.revision < std::numeric_limits<std::uint64_t>::max() &&
             base->committed_intervals < limits.max_committed_intervals,"interval_cap","revision or commit cap");
        const double dt = duration(initial.elapsed_seconds,request.end_seconds);
        const double quantum = std::nextafter(request.end_seconds,std::numeric_limits<double>::infinity())-
                               request.end_seconds;
        positive(quantum,"common clock quantum");
        lattice(initial.elapsed_seconds,quantum);
        lattice(request.end_seconds,quantum);
        lattice(dt,quantum);
        r.clock_quantum_seconds = quantum;
        need(request.imports.size() <= limits.max_events_per_interval &&
             request.initial_liquid_withdrawals.size() <= limits.max_events_per_interval &&
             request.columns.size() <= cs.size(),"invalid_plan","top-level request cap");
        const std::size_t event_count = request.imports.size()+request.initial_liquid_withdrawals.size();
        need(event_count <= limits.max_events_per_interval &&
             event_count <= limits.max_consumed_event_ids-initial.consumed_event_ids.size(),
             "event_cap","event count or retained ID cap");
        forcing_valid(request.forcing,impl_->surface,limits);
        need(request.forcing.begin_seconds <= initial.elapsed_seconds &&
             request.end_seconds <= request.forcing.end_seconds,"forcing_refusal","macro crosses source boundary");
        bool known_forcing = false;
        for (const auto& previous : initial.forcing_history) {
            compare_forcing(request.forcing,previous);
            known_forcing = known_forcing || previous.id == request.forcing.id;
        }
        need(known_forcing || initial.forcing_history.size() < limits.max_committed_intervals,
             "forcing_refusal","forcing history cap");
        const auto ids = validate_initial_events(request.imports,request.initial_liquid_withdrawals,
            cs,props,initial,limits);

        std::vector<int> plan_map(cs.size(),-1);
        std::size_t total_segments = 0, trials_reserved = 0, stages_reserved = 0, flux_reserved = 0;
        std::size_t leaves_reserved = 0;
        std::set<std::string> segment_ids;
        int previous_cell = -1;
        for (std::size_t j = 0; j < request.columns.size(); ++j) {
            const auto& plan = request.columns[j];
            need(plan.cell_id > previous_cell && static_cast<std::size_t>(plan.cell_id) < cs.size() &&
                 exposed(cs[plan.cell_id]),"invalid_plan","plans require canonical exposed-cell order");
            previous_cell = plan.cell_id;
            plan_map[plan.cell_id] = static_cast<int>(j);
            need(!plan.segments.empty() && plan.segments.size() <= limits.max_segments_per_cell,
                 "invalid_plan","per-cell segment count");
            for (std::size_t k = 0; k < plan.segments.size(); ++k) {
                const auto& s = plan.segments[k];
                plan_segment_valid(s,limits);
                need(segment_ids.insert(s.id).second,"invalid_plan","duplicate segment ID");
                need(s.latest_end_seconds > initial.elapsed_seconds && s.latest_end_seconds <= request.end_seconds,
                     "clock_refusal","segment horizon outside common interval");
                lattice(s.latest_end_seconds,quantum);
                if (s.skip_if_at_common_end)
                    need(k+1 == plan.segments.size() && s.goal == p::Goal::within_branch &&
                         same(s.latest_end_seconds,request.end_seconds),"invalid_plan","invalid terminal skip");
                ++total_segments;
                trials_reserved += static_cast<std::size_t>(s.work.maximum_duration_trials);
                stages_reserved += static_cast<std::size_t>(s.work.maximum_stage_calls);
                flux_reserved += static_cast<std::size_t>(s.work.maximum_total_flux_evaluations);
                leaves_reserved += static_cast<std::size_t>(s.reconstruction_leaves);
            }
        }
        need(total_segments <= limits.max_segment_calls && trials_reserved <= limits.max_duration_trials &&
             stages_reserved <= limits.max_stage_calls && flux_reserved <= limits.max_flux_evaluations &&
             leaves_reserved <= limits.max_reconstruction_leaves,
             "work_cap","complete planned work exceeds macro reservation");
        for (std::size_t i = 0; i < cs.size(); ++i)
            need((plan_map[i] >= 0) == exposed(cs[i]),"invalid_plan","complete exposed-cell plan coverage");
        r.segments.reserve(total_segments);
        r.coverage.reserve(cs.size());
        for (std::size_t i = 0; i < cs.size(); ++i) {
            const bool active = exposed(cs[i]);
            r.coverage.push_back({static_cast<int>(i),active,initial.elapsed_seconds,
                                 active ? initial.elapsed_seconds : request.end_seconds,0,!active});
        }
        apply_initial_events(request.imports,request.initial_liquid_withdrawals,
            impl_->surface,props,initial,impl_->policy.max_joint_energy_error_j_m2,work,r);
        for (const auto& cell_plan : request.columns) {
            const std::size_t i = static_cast<std::size_t>(cell_plan.cell_id);
            auto& carried = r.private_prefix.state[i];
            auto& error = r.private_prefix.canonical_energy_error_j_m2[i];
            auto& coverage = r.coverage[i];
            for (std::size_t j = 0; j < cell_plan.segments.size(); ++j) {
                const auto& plan = cell_plan.segments[j];
                r.segments.emplace_back();
                auto& observation = r.segments.back();
                observation.cell_id = cell_plan.cell_id;
                observation.plan_index = j;
                if (same(coverage.completed_end_seconds,request.end_seconds)) {
                    need(plan.skip_if_at_common_end,"unused_plan_refusal","nonempty suffix after common end");
                    observation.skipped_at_common_end = true;
                    continue;
                }
                const double h = duration(coverage.completed_end_seconds,plan.latest_end_seconds);
                lattice(h,quantum);
                auto& in = observation.generated_input;
                in.segment_id = plan.id;
                in.physical_boundary_id = request.forcing.id;
                in.is_water = cs[i].is_water;
                in.is_lake = cs[i].is_lake;
                in.water = props.water;
                in.column = column(impl_->surface,props,i);
                in.water_mass_kg_m2 = carried.water_mass_kg_m2;
                in.incident_shortwave_w_m2 = request.forcing.incident_shortwave_w_m2[i];
                in.initial = energy(carried);
                in.start_seconds = coverage.completed_end_seconds;
                in.physical_boundary_seconds = request.forcing.end_seconds;
                in.maximum_duration_seconds = h;
                in.clock_quantum_seconds = quantum;
                in.incoming_branch = plan.incoming_branch;
                in.goal = plan.goal;
                in.proposed_tube = plan.tube;
                in.budgets = plan.budgets;
                in.limits = plan.work;
                in.stage_options = plan.stage_options;
                in.endpoint_certificate = plan.endpoint_certificate;
                in.reconstruction_leaves = plan.reconstruction_leaves;
                observation.request_available = true;
                const auto domain = certify_coupled_domain(props.water,in.column,carried.water_mass_kg_m2,energy(carried),error);
                need(domain.accepted,"error_budget_refused",domain.failure_code+": "+domain.detail);
                increment(work.reserved_duration_trials,static_cast<std::uint64_t>(plan.work.maximum_duration_trials));
                increment(work.reserved_stage_calls,static_cast<std::uint64_t>(plan.work.maximum_stage_calls));
                increment(work.reserved_flux_evaluations,static_cast<std::uint64_t>(plan.work.maximum_total_flux_evaluations));
                increment(work.reserved_reconstruction_leaves,static_cast<std::uint64_t>(plan.reconstruction_leaves));
                increment(work.segment_calls_started);
                observation.call_started = true;
#if COUPLED_HAS_A
                try { observation.receipt = p::advance_phase_segment(in); }
                catch (...) { work.observed_work_counts_complete = false; throw; }
#else
                throw TerrestrialWaterError("capability_unavailable","thermal backend unavailable");
#endif
                increment(work.segment_calls_returned);
                observation.receipt_available = true;
                const auto& result = observation.receipt;
                const bool valid_counts = result.duration_trials_started >= 0 && result.duration_trials_started <= plan.work.maximum_duration_trials &&
                    result.stage_calls_started >= 0 && result.stage_calls_started <= plan.work.maximum_stage_calls &&
                    result.total_flux_evaluations >= 0 && result.total_flux_evaluations <= plan.work.maximum_total_flux_evaluations &&
                    result.reconstruction.leaves_started >= 0 &&
                    result.reconstruction.leaves_started <= plan.reconstruction_leaves;
                if (!valid_counts) work.observed_work_counts_complete = false;
                need(valid_counts,"thermal_protocol_refusal","returned work outside reservation");
                increment(work.duration_trials_started,static_cast<std::uint64_t>(result.duration_trials_started));
                increment(work.stage_calls_started,static_cast<std::uint64_t>(result.stage_calls_started));
                increment(work.scalar_flux_evaluations,static_cast<std::uint64_t>(result.total_flux_evaluations));
                increment(work.reconstruction_leaves_started,static_cast<std::uint64_t>(result.reconstruction.leaves_started));
                need(result.accepted && result.final_state_available,"thermal_refused",result.failure_code+": "+result.detail);
                need(result.selected_duration_seconds > 0 && result.selected_duration_seconds <= h &&
                     exact_sum(in.start_seconds,result.selected_duration_seconds,result.selected_end_seconds) &&
                     result.selected_end_seconds <= plan.latest_end_seconds && result.selected_end_seconds > in.start_seconds &&
                     result.remaining_duration_seconds >= 0 && exact_sum(result.selected_duration_seconds,result.remaining_duration_seconds,h),
                     "thermal_protocol_refusal","selected clock or remaining duration mismatch");
                lattice(result.selected_duration_seconds,quantum);
                lattice(result.selected_end_seconds,quantum);
                need(same(result.clock_quantum_seconds,quantum),"thermal_protocol_refusal","clock quantum changed");
                if (plan.goal == p::Goal::within_branch)
                    need(same(result.selected_end_seconds,plan.latest_end_seconds),"thermal_protocol_refusal","within-branch incomplete horizon");
                if (plan.goal == p::Goal::fixed_duration)
                    need(same(result.selected_end_seconds,plan.latest_end_seconds) &&
                         same(result.selected_duration_seconds,h) && result.remaining_duration_seconds == 0,
                         "thermal_protocol_refusal","fixed-duration incomplete horizon");
                observation.error = certify_coupled_segment(result,error,impl_->policy.max_joint_energy_error_j_m2);
                need(observation.error.accepted,"error_budget_refused",observation.error.failure_code+": "+observation.error.detail);
                carried.surface_enthalpy_j_m2 = result.final_state.surface_enthalpy_j_m2;
                carried.atmospheric_energy_j_m2 = result.final_state.atmospheric_energy_j_m2;
                error = observation.error.final_error_j_m2;
                coverage.completed_end_seconds = result.selected_end_seconds;
                ++coverage.completed_segments;
            }
            need(same(coverage.completed_end_seconds,request.end_seconds),"incomplete_plan","cell did not reach common T");
            coverage.complete = true;
        }
        need(std::all_of(r.coverage.begin(),r.coverage.end(),[](const auto& c){return c.complete;}),
             "incomplete_plan","not all cell scopes reached common T");
        r.projection = project_terrestrial_liquid_supply(impl_->surface,r.private_liquid_outbox,dt,
                                                        props.reference_water_density_kg_m3,props.year_duration_seconds);
        r.projection_available = true;
        auto& ledger = r.energy_ledger;
        ledger.canonical_external_enthalpy_j = r.mass_receipt_available ? r.mass_receipt.external_net_enthalpy_j : 0;
        for (std::size_t i = 0; i < cs.size(); ++i) if (exposed(cs[i])) {
            const double area = cs[i].area_km2*1e6;
            add_finite(ledger.surface_storage_j,area*(r.private_prefix.state[i].surface_enthalpy_j_m2-initial.state[i].surface_enthalpy_j_m2));
            add_finite(ledger.air_storage_j,area*(r.private_prefix.state[i].atmospheric_energy_j_m2-initial.state[i].atmospheric_energy_j_m2));
        }
        for (const auto& s : r.segments) if (!s.skipped_at_common_end) {
            need(s.receipt.quadrature_available,"ledger_refusal","accepted segment has no quadrature");
            add_finite(ledger.incident_shortwave_j,s.receipt.quadrature.incident_shortwave_j);
            add_finite(ledger.reflected_shortwave_j,s.receipt.quadrature.reflected_shortwave_j);
            add_finite(ledger.outgoing_longwave_j,s.receipt.quadrature.outgoing_longwave_j);
        }
        ledger.combined_residual_j = ledger.surface_storage_j;
        add_finite(ledger.combined_residual_j,ledger.air_storage_j);
        add_finite(ledger.combined_residual_j,-ledger.canonical_external_enthalpy_j);
        add_finite(ledger.combined_residual_j,-ledger.incident_shortwave_j);
        add_finite(ledger.combined_residual_j,ledger.reflected_shortwave_j);
        add_finite(ledger.combined_residual_j,ledger.outgoing_longwave_j);
        r.energy_ledger_available = true;
        r.private_prefix.revision = initial.revision+1;
        r.private_prefix.elapsed_seconds = request.end_seconds;
        r.private_prefix.consumed_event_ids.assign(ids.begin(),ids.end());
        if (!known_forcing) r.private_prefix.forcing_history.push_back(request.forcing);
        r.final = r.private_prefix;
        r.prepared = true;
    } catch (const std::bad_alloc&) {
        // A memory failure cannot promise a complete allocated diagnostic.
        // The accepted bundle remains untouched; the work meter is retained.
        throw;
    } catch (const TerrestrialWaterError& e) {
        r.failure_code = e.code;
        r.detail = e.what();
    } catch (const std::exception& e) {
        r.failure_code = "preparation_refused";
        r.detail = e.what();
    }
    if (!r.prepared) r.final.reset();
    if (r.request_available) r.observed_request_after = request;
    r.observed_accepted_after = impl_->accepted->restart;
    r.work_after = work;
    const auto diagnostic = std::make_shared<const CoupledAttemptReceipt>(std::move(r));
    if (!diagnostic->prepared) return {diagnostic,std::nullopt};
    const auto replacement = std::make_shared<const Bundle>(Bundle{*diagnostic->final,base->committed_intervals+1,diagnostic});
    const auto data = std::make_shared<const CoupledIntervalCandidate::Data>(
        CoupledIntervalCandidate::Data{impl_->anchor,base,replacement});
    return {diagnostic,CoupledIntervalCandidate(data)};
}
CoupledPreparation TerrestrialCoupledOwner::prepare(const CoupledAutomaticRequest& request) {
    const auto base = impl_->accepted;
    const auto& initial = base->restart;
    const auto& cs = impl_->surface.cells();
    const auto& props = impl_->properties;
    const auto& limits = impl_->limits;
    auto& work = impl_->work;
    CoupledAttemptReceipt r;
    r.automatic_mode = true;
    r.surface_revision = impl_->surface.surface_revision();
    r.properties = props; r.acceptance_policy = impl_->policy; r.limits = limits;
    r.surface_cells = cs; r.initial = initial; r.private_prefix = initial; r.work_before = work;
    try {
        increment(work.prepare_attempts);
        arithmetic_capability();
        need(request.forcing.incident_shortwave_w_m2.size() <= limits.max_cells &&
             request.forcing.id.size() <= limits.max_identifier_bytes,"invalid_plan","request retention cap");
        need(request.imports.size() <= limits.max_events_per_interval &&
             request.initial_liquid_withdrawals.size() <= limits.max_events_per_interval,
             "invalid_plan","request retention cap");
        for (const auto& x : request.imports)
            need(x.id.size() <= limits.max_identifier_bytes,"invalid_plan","request retention cap");
        for (const auto& x : request.initial_liquid_withdrawals)
            need(x.id.size() <= limits.max_identifier_bytes,"invalid_plan","request retention cap");
        r.automatic_request = request;
        need(work.prepare_attempts <= limits.max_prepare_attempts,"work_cap","prepare attempt cap");
        need(request.expected_revision == initial.revision,"stale_revision","request revision mismatch");
        need(initial.revision < std::numeric_limits<std::uint64_t>::max() &&
             base->committed_intervals < limits.max_committed_intervals,"interval_cap","revision or commit cap");
        const double dt = duration(initial.elapsed_seconds,request.end_seconds);
        const double q = std::nextafter(request.end_seconds,std::numeric_limits<double>::infinity())-request.end_seconds;
        positive(q,"common clock quantum");
        lattice(initial.elapsed_seconds,q); lattice(request.end_seconds,q); lattice(dt,q);
        r.clock_quantum_seconds = q;
        const auto begin_tick = static_cast<std::uint64_t>(initial.elapsed_seconds/q);
        const auto N = static_cast<std::uint64_t>(dt/q);
        forcing_valid(request.forcing,impl_->surface,limits);
        need(request.forcing.begin_seconds <= initial.elapsed_seconds && request.end_seconds <= request.forcing.end_seconds,
             "forcing_refusal","macro crosses source boundary");
        bool known_forcing = false;
        for (const auto& old : initial.forcing_history) {
            compare_forcing(request.forcing,old);
            known_forcing = known_forcing || old.id == request.forcing.id;
        }
        need(known_forcing || initial.forcing_history.size() < limits.max_committed_intervals,
             "forcing_refusal","forcing history cap");
        const auto ids = validate_initial_events(request.imports,request.initial_liquid_withdrawals,
            cs,props,initial,limits);
        const bool sourced = !request.imports.empty() || !request.initial_liquid_withdrawals.empty();
        const auto& o = request.options;
        positive(o.maximum_step_seconds,"maximum automatic step");
        need(finite(o.minimum_step_seconds) && o.minimum_step_seconds >= 0,"invalid_plan","minimum automatic step");
        const auto max_ticks = static_cast<std::uint64_t>(std::floor(std::min(dt,o.maximum_step_seconds)/q));
        if (o.minimum_step_seconds != 0) lattice(o.minimum_step_seconds,q);
        const auto min_ticks = o.minimum_step_seconds == 0 ? std::uint64_t{1}
            : static_cast<std::uint64_t>(o.minimum_step_seconds/q);
        need(min_ticks > 0 && max_ticks >= min_ticks,"clock_refusal","automatic step limits contain no clock tick");
        need(o.maximum_attempts_per_cell > 0 && o.maximum_attempts_per_cell <= 256 &&
             o.maximum_total_attempts > 0 && o.maximum_total_attempts <= 256 &&
             o.maximum_accepted_steps_per_cell > 0 && o.maximum_accepted_steps_per_cell <= 128 &&
             o.maximum_total_accepted_steps > 0 && o.maximum_total_accepted_steps <= 128 &&
             o.maximum_tube_passes_per_attempt > 0 && o.maximum_tube_passes_per_attempt <= 8 &&
             o.maximum_total_tube_passes > 0 && o.maximum_total_tube_passes <= 2048,
             "work_cap","automatic work policy outside finite limits");
        // Use the existing parameter validator without trusting a supplied tube,
        // branch or schedule. Fixed duration always permits exactly one trial.
        CoupledSegmentPlan policy{"automatic-policy",p::Branch::dry,p::Goal::fixed_duration,request.end_seconds,{},
            {o.maximum_numerical_equation_defect_j_m2,1,1,1},o.work,o.stage_options,false,
            p::EndpointCertificate::hermite_residual,o.reconstruction_leaves};
        plan_segment_valid(policy,limits);
        need(o.work.maximum_duration_trials == 1 && o.work.maximum_stage_calls == 2,
             "invalid_plan","automatic fixed duration requires one trial and two stage reservations");
        const std::size_t active = std::count_if(cs.begin(),cs.end(),exposed);
        need(active <= o.maximum_total_attempts && active <= o.maximum_total_accepted_steps,
             "work_cap","complete exposed-cell coverage exceeds automatic caps");
        const auto attempts = o.maximum_total_attempts;
        need(attempts <= limits.max_segment_calls && attempts*static_cast<std::size_t>(o.work.maximum_duration_trials) <= limits.max_duration_trials &&
             attempts*static_cast<std::size_t>(o.work.maximum_stage_calls) <= limits.max_stage_calls &&
             attempts*static_cast<std::size_t>(o.work.maximum_total_flux_evaluations) <= limits.max_flux_evaluations &&
             attempts*static_cast<std::size_t>(o.reconstruction_leaves) <= limits.max_reconstruction_leaves,
             "work_cap","complete automatic solve reservation exceeds macro limits");
        r.segments.reserve(attempts); r.coverage.reserve(cs.size());
        for (std::size_t i=0;i<cs.size();++i)
            r.coverage.push_back({static_cast<int>(i),exposed(cs[i]),initial.elapsed_seconds,
                exposed(cs[i]) ? initial.elapsed_seconds : request.end_seconds,0,!exposed(cs[i])});
        if (sourced) {
            apply_initial_events(request.imports,request.initial_liquid_withdrawals,
                impl_->surface,props,initial,impl_->policy.max_joint_energy_error_j_m2,work,r);
            r.thermal_initial = r.private_prefix;
        }
        std::size_t total_attempts=0, total_accepted=0, tube_reserved=0;
        const double B = impl_->policy.max_joint_energy_error_j_m2;
        for (std::size_t i=0;i<cs.size();++i) {
            if (!exposed(cs[i])) continue;
            auto& carried = r.private_prefix.state[i];
            auto& E = r.private_prefix.canonical_energy_error_j_m2[i];
            auto& coverage = r.coverage[i];
            const double E0 = E;
            const double headroom = std::max(0.0,b::sub(b::point(B),b::point(E0)).lower);
            std::uint64_t elapsed=0, proposed_ticks=std::min(max_ticks,N);
            std::size_t cell_attempts=0;
            while (elapsed < N) {
                need(cell_attempts < o.maximum_attempts_per_cell && total_attempts < attempts &&
                     coverage.completed_segments < o.maximum_accepted_steps_per_cell && total_accepted < o.maximum_total_accepted_steps,
                     "work_cap","automatic attempt or accepted-step cap exhausted");
                const auto n = std::min(proposed_ticks,N-elapsed);
                need(n >= min_ticks,"minimum_step_refusal","remaining duration below minimum step");
                const double h = static_cast<double>(n)*q;
                const double start = static_cast<double>(begin_tick+elapsed)*q;
                const double end = static_cast<double>(begin_tick+elapsed+n)*q;
                need(same(duration(start,end),h),"clock_refusal","derived tick duration does not close exactly");
                // Freeze allowance after the initial source jump. No remaining-budget feedback
                // and no upward floor can enlarge the exact n/N allocation.
                const double quota = b::mul(b::point(headroom),b::div(b::point(static_cast<double>(n)),b::point(static_cast<double>(N)))).lower;
                need(finite(quota) && quota > 0,"error_allocation_refused","no positive representable per-tick allowance");
                const auto domain = certify_coupled_domain(props.water,column(impl_->surface,props,i),carried.water_mass_kg_m2,energy(carried),E);
                need(domain.accepted,"error_budget_refused",domain.failure_code+": "+domain.detail);
                need(static_cast<std::size_t>(o.maximum_tube_passes_per_attempt) <= o.maximum_total_tube_passes-tube_reserved,
                     "work_cap","automatic tube reservation exhausted");
                tube_reserved += static_cast<std::size_t>(o.maximum_tube_passes_per_attempt);
                increment(work.reserved_tube_passes,o.maximum_tube_passes_per_attempt);
                ++cell_attempts; ++total_attempts; increment(work.automatic_attempts_started);
                r.segments.emplace_back();
                auto& obs = r.segments.back();
                obs.cell_id = static_cast<int>(i); obs.plan_index = cell_attempts-1; obs.automatic_trial = true;
                obs.begin_tick = begin_tick+elapsed; obs.duration_ticks=n; obs.interval_ticks=N;
                obs.interval_initial_error_j_m2=E0; obs.interval_headroom_lower_j_m2=headroom; obs.offered_error_j_m2=quota;
                auto& in = obs.generated_input;
                in.segment_id = "auto-"+std::to_string(i)+"-"+std::to_string(cell_attempts);
                in.physical_boundary_id=request.forcing.id; in.water=props.water; in.column=column(impl_->surface,props,i);
                in.water_mass_kg_m2=carried.water_mass_kg_m2; in.initial=energy(carried);
                in.incident_shortwave_w_m2=request.forcing.incident_shortwave_w_m2[i];
                in.start_seconds=start; in.maximum_duration_seconds=h; in.physical_boundary_seconds=request.forcing.end_seconds;
                in.clock_quantum_seconds=q; in.goal=p::Goal::fixed_duration;
                in.budgets={o.maximum_numerical_equation_defect_j_m2,1,1,quota};
                in.limits=o.work; in.stage_options=o.stage_options;
                in.endpoint_certificate=p::EndpointCertificate::hermite_residual; in.reconstruction_leaves=o.reconstruction_leaves;
                obs.automatic_skeleton=in;
                try { obs.tube_proposal=p::propose_fixed_duration_tube(in,o.maximum_tube_passes_per_attempt); }
                catch (...) { work.observed_work_counts_complete=false; throw; }
                const bool tube_counts=obs.tube_proposal.passes_started >= 0 && obs.tube_proposal.passes_started <= o.maximum_tube_passes_per_attempt &&
                    obs.tube_proposal.passes.size() == static_cast<std::size_t>(obs.tube_proposal.passes_started);
                if (!tube_counts) work.observed_work_counts_complete=false;
                need(tube_counts,"thermal_protocol_refusal","tube passes exceed reservation or receipt coverage");
                increment(work.tube_passes_started,obs.tube_proposal.passes_started);
                obs.request_available=obs.tube_proposal.input_available;
                if (obs.request_available) in=obs.tube_proposal.generated_input;
                need(!obs.tube_proposal.accepted || obs.request_available,"thermal_protocol_refusal","accepted tube has no input");
                if (!obs.tube_proposal.accepted) {
                    obs.automatic_failure_code=obs.tube_proposal.failure_code;
                    need(obs.automatic_failure_code == "tube_unproved" || obs.automatic_failure_code == "phase_domain_unproved",
                         "automatic_tube_refused",obs.tube_proposal.failure_code+": "+obs.tube_proposal.detail);
                } else {
                    increment(work.reserved_duration_trials,o.work.maximum_duration_trials);
                    increment(work.reserved_stage_calls,o.work.maximum_stage_calls);
                    increment(work.reserved_flux_evaluations,o.work.maximum_total_flux_evaluations);
                    increment(work.reserved_reconstruction_leaves,o.reconstruction_leaves);
                    increment(work.segment_calls_started); obs.call_started=true;
                    try { obs.receipt=p::advance_phase_segment(in); }
                    catch (...) { work.observed_work_counts_complete=false; throw; }
                    increment(work.segment_calls_returned); obs.receipt_available=true;
                    const auto& result=obs.receipt;
                    const bool counts=result.duration_trials_started >= 0 && result.duration_trials_started <= o.work.maximum_duration_trials &&
                        result.stage_calls_started >= 0 && result.stage_calls_started <= o.work.maximum_stage_calls &&
                        result.total_flux_evaluations >= 0 && result.total_flux_evaluations <= o.work.maximum_total_flux_evaluations &&
                        result.reconstruction.leaves_started >= 0 && result.reconstruction.leaves_started <= o.reconstruction_leaves;
                    if (!counts) work.observed_work_counts_complete=false;
                    need(counts,"thermal_protocol_refusal","returned work outside reservation");
                    increment(work.duration_trials_started,result.duration_trials_started);
                    increment(work.stage_calls_started,result.stage_calls_started);
                    increment(work.scalar_flux_evaluations,result.total_flux_evaluations);
                    increment(work.reconstruction_leaves_started,result.reconstruction.leaves_started);
                    if (!result.accepted) {
                        obs.automatic_failure_code=result.failure_code;
                        need(result.failure_code == "physical_budget_refusal" || result.failure_code == "numerical_budget_refusal" ||
                             result.failure_code == "stage_refusal" || result.failure_code == "stage_domain_refusal",
                             "thermal_refused",result.failure_code+": "+result.detail);
                    } else {
                        need(result.final_state_available && same(result.selected_duration_seconds,h) && same(result.selected_end_seconds,end) &&
                             same(result.clock_quantum_seconds,q) && result.remaining_duration_seconds == 0,
                             "thermal_protocol_refusal","fixed duration or quantum changed");
                        obs.error=certify_coupled_segment(result,E,B);
                        if (!obs.error.accepted) {
                            obs.automatic_failure_code=obs.error.failure_code;
                            need(obs.error.before_domain.accepted &&
                                 (obs.error.failure_code == "cumulative_error_budget" ||
                                  (obs.error.failure_code == "uncertain_physical_domain" && !obs.error.after_domain.accepted)),
                                 "error_budget_refused",obs.error.failure_code+": "+obs.error.detail);
                        } else {
                            obs.charged_increment_j_m2=b::sub(b::point(obs.error.final_error_j_m2),b::point(E));
                            obs.charged_increment_available=true;
                            need(obs.error.final_error_j_m2 >= E && obs.error.final_error_j_m2 <= B && obs.charged_increment_j_m2.upper >= 0,
                                 "thermal_protocol_refusal","invalid cumulative error increase");
                            if (obs.charged_increment_j_m2.upper > quota) obs.automatic_failure_code="rounded_charge_refusal";
                        }
                        if (obs.automatic_failure_code.empty()) {
                            carried.surface_enthalpy_j_m2=result.final_state.surface_enthalpy_j_m2;
                            carried.atmospheric_energy_j_m2=result.final_state.atmospheric_energy_j_m2;
                            E=obs.error.final_error_j_m2; elapsed+=n;
                            coverage.completed_end_seconds=end; ++coverage.completed_segments; ++total_accepted;
                            obs.accepted_for_private_carry=true;
                        }
                    }
                }
                if (obs.accepted_for_private_carry) proposed_ticks=std::min(max_ticks,n*2);
                else {
                    need(n/2 >= min_ticks,"minimum_step_refusal","rejected trial cannot be halved on permitted clock lattice");
                    proposed_ticks=n/2;
                }
            }
            need(same(coverage.completed_end_seconds,request.end_seconds),"incomplete_plan","cell did not reach common T");
            coverage.complete=true;
        }
        r.projection=project_terrestrial_liquid_supply(impl_->surface,r.private_liquid_outbox,dt,props.reference_water_density_kg_m3,props.year_duration_seconds);
        r.projection_available=true;
        auto& ledger=r.energy_ledger;
        if (r.mass_receipt_available) ledger.canonical_external_enthalpy_j=r.mass_receipt.external_net_enthalpy_j;
        for (std::size_t i=0;i<cs.size();++i) if (exposed(cs[i])) {
            const double area=cs[i].area_km2*1e6;
            add_finite(ledger.surface_storage_j,area*(r.private_prefix.state[i].surface_enthalpy_j_m2-initial.state[i].surface_enthalpy_j_m2));
            add_finite(ledger.air_storage_j,area*(r.private_prefix.state[i].atmospheric_energy_j_m2-initial.state[i].atmospheric_energy_j_m2));
        }
        for (const auto& s:r.segments) if (s.accepted_for_private_carry) {
            need(s.receipt.quadrature_available,"ledger_refusal","accepted segment has no quadrature");
            add_finite(ledger.incident_shortwave_j,s.receipt.quadrature.incident_shortwave_j);
            add_finite(ledger.reflected_shortwave_j,s.receipt.quadrature.reflected_shortwave_j);
            add_finite(ledger.outgoing_longwave_j,s.receipt.quadrature.outgoing_longwave_j);
        }
        ledger.combined_residual_j=ledger.surface_storage_j;
        add_finite(ledger.combined_residual_j,ledger.air_storage_j);
        if (sourced) add_finite(ledger.combined_residual_j,-ledger.canonical_external_enthalpy_j);
        add_finite(ledger.combined_residual_j,-ledger.incident_shortwave_j);
        add_finite(ledger.combined_residual_j,ledger.reflected_shortwave_j);
        add_finite(ledger.combined_residual_j,ledger.outgoing_longwave_j);
        r.energy_ledger_available=true;
        r.private_prefix.revision=initial.revision+1; r.private_prefix.elapsed_seconds=request.end_seconds;
        if (sourced) r.private_prefix.consumed_event_ids.assign(ids.begin(),ids.end());
        if (!known_forcing) r.private_prefix.forcing_history.push_back(request.forcing);
        r.final=r.private_prefix; r.prepared=true;
    } catch (const std::bad_alloc&) { throw;
    } catch (const TerrestrialWaterError& e) { r.failure_code=e.code; r.detail=e.what();
    } catch (const std::exception& e) { r.failure_code="preparation_refused"; r.detail=e.what(); }
    if (!r.prepared) r.final.reset();
    if (r.automatic_request) r.observed_automatic_request_after=request;
    r.observed_accepted_after=impl_->accepted->restart; r.work_after=work;
    const auto diagnostic=std::make_shared<const CoupledAttemptReceipt>(std::move(r));
    if (!diagnostic->prepared) return {diagnostic,std::nullopt};
    const auto replacement=std::make_shared<const Bundle>(Bundle{*diagnostic->final,base->committed_intervals+1,diagnostic});
    const auto data=std::make_shared<const CoupledIntervalCandidate::Data>(CoupledIntervalCandidate::Data{impl_->anchor,base,replacement});
    return {diagnostic,CoupledIntervalCandidate(data)};
}
void TerrestrialCoupledOwner::commit(const CoupledIntervalCandidate& candidate) {
    need(candidate.data_ && candidate.data_->owner == impl_->anchor,"foreign_candidate","candidate owner mismatch");
    need(candidate.data_->base == impl_->accepted,"stale_candidate","candidate accepted base changed");
    auto replacement = candidate.data_->replacement;
    impl_->accepted.swap(replacement);
}

namespace {
std::string json_quote(const std::string& text) {
    std::ostringstream out;
    out << '"';
    for (unsigned char ch : text) {
        if (ch == '"' || ch == '\\') out << '\\' << ch;
        else if (ch < 32 || ch > 126)
            out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << int(ch);
        else out << ch;
    }
    out << '"';
    return out.str();
}
std::string num(double value) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    if (finite(value)) out << std::setprecision(17) << value;
    else out << "{\"nonfinite_binary64_bits\":\"" << std::hex
             << std::bit_cast<std::uint64_t>(value) << "\"}";
    return out.str();
}
struct Object {
    std::string value = "{";
    void add(const char* name,const std::string& json) {
        if (value.size() > 1) value += ',';
        value += json_quote(name)+':'+json;
    }
    void number(const char* name,double x) { add(name,num(x)); }
    void flag(const char* name,bool x) { add(name,x ? "true" : "false"); }
    std::string finish() const { return value+'}'; }
};
template<class T,class F> std::string array(const std::vector<T>& values,F encode) {
    std::string result = "[";
    for (const auto& x : values) {
        if (result.size() > 1) result += ',';
        result += encode(x);
    }
    return result+']';
}
std::string vector3(const Vec3& x) { return '['+num(x.x)+','+num(x.y)+','+num(x.z)+']'; }
std::string surface_json(const Cell& c) {
    Object o;
    o.add("cell_id",std::to_string(c.id));
    o.flag("is_water",c.is_water); o.flag("is_lake",c.is_lake);
    o.add("water_body",std::to_string(c.water_body));
    o.number("area_km2",c.area_km2); o.number("canonical_area_m2",c.area_km2*1e6);
    o.number("elevation_m",c.elevation_m); o.number("lat",c.lat); o.number("lon",c.lon);
    o.add("position",vector3(c.p)); o.number("water_depth_m",c.water_depth_m);
    o.add("neighbors",array(c.neighbors,[](int x){return std::to_string(x);}));
    o.add("control_volume_vertices",array(c.control_volume_vertices,vector3));
    o.add("control_volume_edge_neighbor_ids",array(c.control_volume_edge_neighbor_ids,[](int x){return std::to_string(x);}));
    o.number("temperature_c",c.temperature_c); o.number("original_precipitation_mm_y",c.precipitation_mm_y);
    o.number("sediment_thickness_m",c.sediment_thickness_m); o.add("lithology",std::to_string(c.lithology));
    return o.finish();
}
std::string water_json(const a::WaterProperties& w) {
    Object o;
    o.number("freezing_temperature_k",w.freezing_temperature_k);
    o.number("solid_heat_capacity_j_kg_k",w.solid_heat_capacity_j_kg_k);
    o.number("liquid_heat_capacity_j_kg_k",w.liquid_heat_capacity_j_kg_k);
    o.number("latent_heat_j_kg",w.latent_heat_j_kg);
    return o.finish();
}
std::string properties_json(const CoupledProperties& p) {
    Object o;
    o.add("water",water_json(p.water));
    o.number("reference_water_density_kg_m3",p.reference_water_density_kg_m3);
    o.number("year_duration_seconds",p.year_duration_seconds);
    o.add("columns",array(p.columns,[](const auto& c){
        Object x;
        x.number("dry_heat_capacity_j_m2_k",c.dry_heat_capacity_j_m2_k);
        x.number("atmospheric_heat_capacity_j_m2_k",c.atmospheric_heat_capacity_j_m2_k);
        x.number("atmospheric_longwave_absorptivity",c.atmospheric_longwave_absorptivity);
        x.number("sensible_exchange_w_m2_k",c.sensible_exchange_w_m2_k);
        x.number("surface_shortwave_albedo",c.surface_shortwave_albedo);
        return x.finish();
    }));
    return o.finish();
}
std::string limits_json(const CoupledLimits& x) {
    Object o;
#define LIMIT(name) o.add(#name,std::to_string(x.name))
    LIMIT(max_cells); LIMIT(max_committed_intervals); LIMIT(max_prepare_attempts);
    LIMIT(max_events_per_interval); LIMIT(max_consumed_event_ids); LIMIT(max_identifier_bytes);
    LIMIT(max_segments_per_cell); LIMIT(max_segment_calls); LIMIT(max_duration_trials);
    LIMIT(max_stage_calls); LIMIT(max_flux_evaluations);
    if (x.max_reconstruction_leaves != CoupledLimits{}.max_reconstruction_leaves) { LIMIT(max_reconstruction_leaves); }
#undef LIMIT
    return o.finish();
}
std::string interval_json(p::Interval x) {
    return "{\"lower\":"+num(x.lower)+",\"upper\":"+num(x.upper)+'}';
}
std::string box_json(const p::StateBox& box) {
    return "{\"surface_enthalpy_j_m2\":"+interval_json(box.surface_enthalpy_j_m2)+
        ",\"atmospheric_energy_j_m2\":"+interval_json(box.atmospheric_energy_j_m2)+'}';
}
std::string domain_json(const CoupledDomainCertificate& x) {
    Object o;
    o.flag("accepted",x.accepted); o.add("failure_code",json_quote(x.failure_code)); o.add("detail",json_quote(x.detail));
    o.add("uncertainty_box",box_json(x.uncertainty_box));
    o.add("surface_floor_j_m2",interval_json(x.surface_floor_j_m2));
    o.add("air_floor_j_m2",interval_json(x.air_floor_j_m2));
    return o.finish();
}
std::string jump_json(const CoupledJumpCertificate& x) {
    Object o;
    o.flag("accepted",x.accepted); o.add("failure_code",json_quote(x.failure_code)); o.add("detail",json_quote(x.detail));
    o.add("before_domain",domain_json(x.before_domain)); o.add("after_domain",domain_json(x.after_domain));
    o.add("withdrawal_density_kg_m2",interval_json(x.withdrawal_density_kg_m2));
    o.add("import_energy_j_m2",interval_json(x.import_energy_j_m2));
    o.add("canonical_mass_projection_kg_m2",interval_json(x.canonical_mass_projection_kg_m2));
    o.add("ideal_jump_j_m2",interval_json(x.ideal_jump_j_m2));
    o.add("state_projection_j_m2",interval_json(x.state_projection_j_m2));
    o.add("export_bridge_j_m2",interval_json(x.export_bridge_j_m2));
    o.flag("liquid_feasibility_proved",x.liquid_feasibility_proved);
    o.number("inherited_error_j_m2",x.inherited_error_j_m2);
    o.number("jump_defect_upper_j_m2",x.jump_defect_upper_j_m2);
    o.number("final_error_j_m2",x.final_error_j_m2);
    o.number("outbox_error_upper_j",x.outbox_error_upper_j);
    o.add("per_withdrawal_error_upper_j",array(x.per_withdrawal_error_upper_j,num));
    return o.finish();
}
std::string segment_error_json(const CoupledSegmentCertificate& x) {
    Object o;
    o.flag("accepted",x.accepted); o.add("failure_code",json_quote(x.failure_code)); o.add("detail",json_quote(x.detail));
    o.add("before_domain",domain_json(x.before_domain)); o.add("after_domain",domain_json(x.after_domain));
    o.number("inherited_error_j_m2",x.inherited_error_j_m2);
    o.number("time_transport_upper_j_m2",x.time_transport_upper_j_m2);
    o.number("local_same_time_error_upper_j_m2",x.local_same_time_error_upper_j_m2);
    o.number("final_error_j_m2",x.final_error_j_m2);
    return o.finish();
}
std::string state_json(const CoupledColumnState& x) {
    return "{\"water_mass_kg_m2\":"+num(x.water_mass_kg_m2)+
        ",\"surface_enthalpy_j_m2\":"+num(x.surface_enthalpy_j_m2)+
        ",\"atmospheric_energy_j_m2\":"+num(x.atmospheric_energy_j_m2)+'}';
}
std::string forcing_json(const CoupledForcingSpan& x) {
    Object o;
    o.add("id",json_quote(x.id)); o.number("begin_seconds",x.begin_seconds); o.number("end_seconds",x.end_seconds);
    o.add("incident_shortwave_w_m2",array(x.incident_shortwave_w_m2,num));
    return o.finish();
}
std::string import_json(const TerrestrialPrecipitationImport& x) {
    Object o;
    o.add("id",json_quote(x.id)); o.add("cell_id",std::to_string(x.cell_id)); o.add("phase",std::to_string(static_cast<int>(x.phase)));
    o.number("mass_kg",x.mass_kg); o.number("temperature_k",x.temperature_k); return o.finish();
}
std::string withdrawal_json(const TerrestrialLiquidWithdrawal& x) {
    Object o;
    o.add("id",json_quote(x.id)); o.add("cell_id",std::to_string(x.cell_id)); o.number("mass_kg",x.mass_kg); return o.finish();
}
std::string segment_plan_json(const CoupledSegmentPlan& s) {
    Object o;
    o.add("id",json_quote(s.id)); o.add("incoming_branch",std::to_string(static_cast<int>(s.incoming_branch)));
    o.add("goal",std::to_string(static_cast<int>(s.goal))); o.number("latest_end_seconds",s.latest_end_seconds);
    o.add("tube",box_json(s.tube)); o.flag("skip_if_at_common_end",s.skip_if_at_common_end);
    Object budgets;
    budgets.number("maximum_numerical_equation_defect_j_m2",s.budgets.maximum_numerical_equation_defect_j_m2);
    budgets.number("maximum_locator_width_seconds",s.budgets.maximum_locator_width_seconds);
    budgets.number("maximum_physical_time_error_seconds",s.budgets.maximum_physical_time_error_seconds);
    budgets.number("maximum_physical_event_state_error_j_m2",s.budgets.maximum_physical_event_state_error_j_m2);
    o.add("budgets",budgets.finish());
    Object work;
    work.add("maximum_duration_trials",std::to_string(s.work.maximum_duration_trials));
    work.add("maximum_air_iterations_per_trial",std::to_string(s.work.maximum_air_iterations_per_trial));
    work.add("maximum_stage_calls",std::to_string(s.work.maximum_stage_calls));
    work.add("maximum_total_flux_evaluations",std::to_string(s.work.maximum_total_flux_evaluations));
    o.add("work",work.finish());
    Object options;
    options.number("absolute_tolerance_w_m2",s.stage_options.absolute_tolerance_w_m2);
    options.number("relative_tolerance",s.stage_options.relative_tolerance);
    options.add("maximum_newton_iterations",std::to_string(s.stage_options.maximum_newton_iterations));
    options.add("maximum_backtracks",std::to_string(s.stage_options.maximum_backtracks));
    o.add("stage_options",options.finish());
    if (s.endpoint_certificate != p::EndpointCertificate::direct_tube || s.reconstruction_leaves != 0) {
        o.add("endpoint_certificate",std::to_string(static_cast<int>(s.endpoint_certificate)));
        o.add("reconstruction_leaves",std::to_string(s.reconstruction_leaves));
    }
    return o.finish();
}
std::string a_state(const a::State& x) {
    return "{\"water_mass_kg_m2\":"+num(x.water_mass_kg_m2)+",\"enthalpy_j_m2\":"+num(x.enthalpy_j_m2)+'}';
}
std::string a_column(const a::Column& x) {
    return "{\"area_m2\":"+num(x.area_m2)+",\"dry_heat_capacity_j_m2_k\":"+num(x.dry_heat_capacity_j_m2_k)+'}';
}
std::string mass_request_json(const a::MassEventInput& x) {
    Object o;
    o.add("imports",array(x.imports,[](const a::Import& m){
        Object z; z.add("recipient",std::to_string(m.recipient)); z.add("phase",std::to_string(static_cast<int>(m.phase)));
        z.number("mass_kg",m.mass_kg); z.number("temperature_k",m.temperature_k); return z.finish();
    }));
    o.add("exports",array(x.exports,[](const a::Export& m){
        Object z; z.add("donor",std::to_string(m.donor)); z.add("phase",std::to_string(static_cast<int>(m.phase)));
        z.number("mass_kg",m.mass_kg); return z.finish();
    }));
    o.add("transfers",array(x.transfers,[](const a::Transfer& m){
        Object z; z.add("donor",std::to_string(m.donor)); z.add("recipient",std::to_string(m.recipient));
        z.add("phase",std::to_string(static_cast<int>(m.phase))); z.number("mass_kg",m.mass_kg); return z.finish();
    }));
    return o.finish();
}
std::string mass_receipt_json(const a::MassEventResult& r) {
    Object o;
    o.add("state",array(r.state,a_state));
    o.add("phase",array(r.phase,[](const a::PhaseState& x){
        Object z; z.number("temperature_k",x.temperature_k); z.number("solid_mass_kg_m2",x.solid_mass_kg_m2);
        z.number("liquid_mass_kg_m2",x.liquid_mass_kg_m2); return z.finish();
    }));
    o.add("movements",array(r.movements,[](const a::Movement& x){
        Object z; z.add("donor",std::to_string(x.donor)); z.add("recipient",std::to_string(x.recipient));
        z.add("phase",std::to_string(static_cast<int>(x.phase))); z.number("mass_kg",x.mass_kg);
        z.number("temperature_k",x.temperature_k); z.number("specific_enthalpy_j_kg",x.specific_enthalpy_j_kg);
        z.number("carried_enthalpy_j",x.carried_enthalpy_j); return z.finish();
    }));
    o.add("ledger",array(r.ledger,[](const a::MassEventLedger& x){
        Object z;
#define L(name) z.number(#name,x.name)
        L(imported_mass_kg_m2); L(exported_mass_kg_m2); L(imported_enthalpy_j_m2); L(exported_enthalpy_j_m2);
        L(mass_residual_kg_m2); L(energy_residual_j_m2); L(mass_roundoff_allowance_kg_m2); L(energy_roundoff_allowance_j_m2);
#undef L
        return z.finish();
    }));
#define G(name) o.number(#name,r.name)
    G(global_mass_change_kg); G(external_net_mass_kg); G(global_mass_residual_kg); G(global_mass_roundoff_allowance_kg);
    G(global_energy_change_j); G(external_net_enthalpy_j); G(global_energy_residual_j); G(global_energy_roundoff_allowance_j);
#undef G
    return o.finish();
}
std::string outbox_json(const TerrestrialLiquidHandoff& x) {
    Object o;
    o.add("id",json_quote(x.id)); o.add("cell_id",std::to_string(x.cell_id)); o.number("mass_kg",x.mass_kg);
    o.number("carried_enthalpy_j",x.carried_enthalpy_j); o.add("kernel_movement_index",std::to_string(x.kernel_movement_index));
    return o.finish();
}
std::string projection_json(const TerrestrialLiquidSupplyProjection& x) {
    Object o;
    o.add("cells",array(x.cells,[](const TerrestrialLiquidSupplyCell& c){
        Object z; z.add("cell_id",std::to_string(c.cell_id)); z.flag("applicable",c.applicable);
#define V(name) z.number(#name,c.name)
        V(original_precipitation_mm_y); V(delivered_liquid_mass_kg); V(delivered_liquid_enthalpy_j);
        V(delivered_liquid_depth_mm); V(liquid_supply_mm_y); V(actual_evapotranspiration_mm);
        V(infiltration_mm); V(runoff_mm); V(partition_residual_mm);
#undef V
        return z.finish();
    }));
    o.add("projected_cells",array(x.projected_cells,[](const Cell& c){
        Object z; z.add("cell_id",std::to_string(c.id));
#define V(name) z.number(#name,c.name)
        V(hydrologic_potential_evapotranspiration_mm_y); V(actual_evapotranspiration_mm_y);
        V(infiltration_capacity_index); V(infiltration_mm_y); V(hydrologic_water_balance_mm_y);
        V(water_budget_runoff_mm_y); V(runoff_mm_y); V(runoff_budget_residual_mm_y);
        V(runoff_budget_consistency_index); V(hydrologic_deficit_mm_y); V(runoff_generation_fraction);
#undef V
        return z.finish();
    }));
    o.add("scope",json_quote("ordered_binary64_annualized_liquid_partition_no_downstream_energy_certificate"));
    return o.finish();
}
std::string energy_ledger_json(const CoupledEnergyLedger& x) {
    Object o;
#define V(name) o.number(#name,x.name)
    V(canonical_external_enthalpy_j); V(surface_storage_j); V(air_storage_j);
    V(incident_shortwave_j); V(reflected_shortwave_j); V(outgoing_longwave_j); V(combined_residual_j);
#undef V
    o.add("aggregation",json_quote("ordered_binary64_separate_surface_air_storage_and_component_sums"));
    o.flag("aggregate_roundoff_certified",false);
    return o.finish();
}
} // namespace

std::string coupled_restart_json(const CoupledRestart& r) {
    Object o;
    o.add("revision",std::to_string(r.revision)); o.number("elapsed_seconds",r.elapsed_seconds);
    o.add("state",array(r.state,state_json));
    o.add("canonical_energy_error_j_m2",array(r.canonical_energy_error_j_m2,num));
    o.add("consumed_event_ids",array(r.consumed_event_ids,json_quote));
    o.add("forcing_history",array(r.forcing_history,forcing_json));
    return o.finish();
}
std::string coupled_work_meter_json(const CoupledWorkMeter& r) {
    Object o;
#define V(name) o.add(#name,std::to_string(r.name))
    V(prepare_attempts); V(mass_calls_started); V(mass_calls_returned);
    V(segment_calls_started); V(segment_calls_returned); V(duration_trials_started);
    V(stage_calls_started); V(scalar_flux_evaluations); V(reserved_duration_trials);
    V(reserved_stage_calls); V(reserved_flux_evaluations);
    if (r.reserved_reconstruction_leaves != 0 || r.reconstruction_leaves_started != 0) {
        V(reserved_reconstruction_leaves); V(reconstruction_leaves_started);
    }
    if (r.automatic_attempts_started != 0 || r.reserved_tube_passes != 0 || r.tube_passes_started != 0) {
        V(automatic_attempts_started); V(reserved_tube_passes); V(tube_passes_started);
    }
#undef V
    o.flag("observed_work_counts_complete",r.observed_work_counts_complete);
    return o.finish();
}
std::string coupled_interval_plan_json(const CoupledIntervalPlan& r) {
    Object o;
    o.add("expected_revision",std::to_string(r.expected_revision)); o.number("end_seconds",r.end_seconds);
    o.add("forcing",forcing_json(r.forcing)); o.add("imports",array(r.imports,import_json));
    o.add("initial_liquid_withdrawals",array(r.initial_liquid_withdrawals,withdrawal_json));
    o.add("columns",array(r.columns,[](const CoupledCellPlan& c){
        Object z; z.add("cell_id",std::to_string(c.cell_id)); z.add("segments",array(c.segments,segment_plan_json)); return z.finish();
    }));
    return o.finish();
}
std::string coupled_automatic_request_json(const CoupledAutomaticRequest& r) {
    Object x, o;
    x.add("expected_revision",std::to_string(r.expected_revision)); x.number("end_seconds",r.end_seconds);
    x.add("forcing",forcing_json(r.forcing));
    const auto& a=r.options;
    o.number("maximum_step_seconds",a.maximum_step_seconds); o.number("minimum_step_seconds",a.minimum_step_seconds);
#define V(name) o.add(#name,std::to_string(a.name))
    V(maximum_attempts_per_cell); V(maximum_total_attempts); V(maximum_accepted_steps_per_cell);
    V(maximum_total_accepted_steps); V(maximum_tube_passes_per_attempt); V(maximum_total_tube_passes);
    V(reconstruction_leaves);
#undef V
    o.number("maximum_numerical_equation_defect_j_m2",a.maximum_numerical_equation_defect_j_m2);
    Object w,s;
#define V(name) w.add(#name,std::to_string(a.work.name))
    V(maximum_duration_trials); V(maximum_air_iterations_per_trial); V(maximum_stage_calls); V(maximum_total_flux_evaluations);
#undef V
    o.add("work",w.finish());
    s.number("absolute_tolerance_w_m2",a.stage_options.absolute_tolerance_w_m2);
    s.number("relative_tolerance",a.stage_options.relative_tolerance);
    s.add("maximum_newton_iterations",std::to_string(a.stage_options.maximum_newton_iterations));
    s.add("maximum_backtracks",std::to_string(a.stage_options.maximum_backtracks));
    o.add("stage_options",s.finish()); x.add("options",o.finish());
    if (!r.imports.empty() || !r.initial_liquid_withdrawals.empty()) {
        x.add("imports",array(r.imports,import_json));
        x.add("initial_liquid_withdrawals",array(r.initial_liquid_withdrawals,withdrawal_json));
    }
    return x.finish();
}
std::string coupled_attempt_receipt_json(const CoupledAttemptReceipt& r) {
    Object o;
    o.add("model",json_quote("explicit_independent_terrestrial_coupled_owner_v1"));
    o.add("error_scope",json_quote(coupled_error_scope)); o.flag("prepared",r.prepared);
    o.add("failure_code",json_quote(r.failure_code)); o.add("detail",json_quote(r.detail));
    o.add("surface_revision",std::to_string(r.surface_revision)); o.add("surface_cells",array(r.surface_cells,surface_json));
    o.add("properties",properties_json(r.properties)); o.add("limits",limits_json(r.limits));
    o.number("max_joint_energy_error_j_m2",r.acceptance_policy.max_joint_energy_error_j_m2);
    o.add("initial",coupled_restart_json(r.initial)); o.add("observed_accepted_after",coupled_restart_json(r.observed_accepted_after));
    o.flag("request_available",r.request_available);
    o.add("request",r.request_available ? coupled_interval_plan_json(r.request) : "null");
    o.add("observed_request_after",r.observed_request_after ? coupled_interval_plan_json(*r.observed_request_after) : "null");
    if (r.automatic_mode) {
        const bool sourced = r.automatic_request && (!r.automatic_request->imports.empty() ||
            !r.automatic_request->initial_liquid_withdrawals.empty());
        o.add("automatic_policy",json_quote(sourced ? "post_source_allowance_exact_tick_share_v1"
                                                  : "fixed_initial_allowance_exact_tick_share_v1"));
        if (sourced) o.add("thermal_initial",r.thermal_initial ? coupled_restart_json(*r.thermal_initial) : "null");
        o.add("automatic_request",r.automatic_request ? coupled_automatic_request_json(*r.automatic_request) : "null");
        o.add("observed_automatic_request_after",r.observed_automatic_request_after ? coupled_automatic_request_json(*r.observed_automatic_request_after) : "null");
    }
    o.number("clock_quantum_seconds",r.clock_quantum_seconds);
    o.flag("mass_request_available",r.mass_request_available);
    o.add("mass_request",r.mass_request_available ? mass_request_json(r.mass_request) : "null");
    o.add("kernel_column_cell_ids",array(r.kernel_column_cell_ids,[](int x){return std::to_string(x);}));
    o.add("kernel_columns",array(r.kernel_columns,a_column)); o.add("kernel_initial",array(r.kernel_initial,a_state));
    o.flag("mass_call_started",r.mass_call_started); o.flag("mass_receipt_available",r.mass_receipt_available);
    o.add("mass_receipt",r.mass_receipt_available ? mass_receipt_json(r.mass_receipt) : "null");
    o.add("mass_error",array(r.mass_error,jump_json));
    o.add("segments",array(r.segments,[](const CoupledSegmentObservation& x){
        Object z; z.add("cell_id",std::to_string(x.cell_id)); z.add("plan_index",std::to_string(x.plan_index));
        z.flag("skipped_at_common_end",x.skipped_at_common_end); z.flag("request_available",x.request_available);
        z.add("generated_input",x.request_available ? p::phase_segment_input_json(x.generated_input) : "null");
        z.flag("call_started",x.call_started); z.flag("receipt_available",x.receipt_available);
        z.add("receipt",x.receipt_available ? p::phase_segment_receipt_json(x.receipt) : "null");
        z.add("error",segment_error_json(x.error));
        if (x.automatic_trial) {
            z.add("begin_tick",std::to_string(x.begin_tick)); z.add("duration_ticks",std::to_string(x.duration_ticks));
            z.add("interval_ticks",std::to_string(x.interval_ticks));
            z.number("interval_initial_error_j_m2",x.interval_initial_error_j_m2);
            z.number("interval_headroom_lower_j_m2",x.interval_headroom_lower_j_m2);
            z.number("offered_error_j_m2",x.offered_error_j_m2);
            z.add("automatic_skeleton",p::phase_segment_input_json(x.automatic_skeleton));
            z.add("tube_proposal",p::tube_proposal_receipt_json(x.tube_proposal));
            z.flag("charged_increment_available",x.charged_increment_available);
            z.add("charged_increment_j_m2",x.charged_increment_available ? interval_json(x.charged_increment_j_m2) : "null");
            z.flag("accepted_for_private_carry",x.accepted_for_private_carry);
            z.add("automatic_failure_code",json_quote(x.automatic_failure_code));
        }
        return z.finish();
    }));
    o.add("coverage",array(r.coverage,[](const CoupledCellCoverage& x){
        Object z; z.add("cell_id",std::to_string(x.cell_id)); z.flag("applicable",x.applicable);
        z.number("begin_seconds",x.begin_seconds); z.number("completed_end_seconds",x.completed_end_seconds);
        z.add("completed_segments",std::to_string(x.completed_segments)); z.flag("complete",x.complete); return z.finish();
    }));
    o.add("private_prefix",coupled_restart_json(r.private_prefix));
    o.add("private_liquid_outbox",array(r.private_liquid_outbox,outbox_json));
    o.flag("projection_available",r.projection_available); o.add("projection",r.projection_available ? projection_json(r.projection) : "null");
    o.flag("energy_ledger_available",r.energy_ledger_available);
    o.add("energy_ledger",r.energy_ledger_available ? energy_ledger_json(r.energy_ledger) : "null");
    o.add("final",r.final ? coupled_restart_json(*r.final) : "null");
    o.add("work_before",coupled_work_meter_json(r.work_before)); o.add("work_after",coupled_work_meter_json(r.work_after));
    o.flag("original_source_accuracy_certified",r.original_source_accuracy_certified);
    o.flag("external_sink_delivery_acknowledged",false);
    return o.finish();
}
std::string coupled_owner_context_json(const TerrestrialCoupledOwner& owner) {
    Object o;
    o.add("model",json_quote("explicit_independent_terrestrial_coupled_owner_v1"));
    o.add("error_scope",json_quote(coupled_error_scope)); o.add("surface_revision",std::to_string(owner.surface().surface_revision()));
    o.add("surface_cells",array(owner.surface().cells(),surface_json)); o.add("properties",properties_json(owner.properties()));
    o.add("limits",limits_json(owner.limits())); o.number("max_joint_energy_error_j_m2",owner.acceptance_policy().max_joint_energy_error_j_m2);
    o.flag("original_source_accuracy_certified",false); o.flag("ordinary_generation_changed",false);
    return o.finish();
}
} // namespace magic_geo::detail
