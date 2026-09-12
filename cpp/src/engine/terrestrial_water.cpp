#include "terrestrial_water.hpp"
#include "internal.hpp"
#include <bit>
#include <cfloat>
#include <set>
#include <utility>

#if !defined(MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER) && LDBL_MANT_DIG >= 64 &&                  \
    LDBL_MAX_EXP >= 16384
#define TERRESTRIAL_HAS_A 1
#else
#define TERRESTRIAL_HAS_A 0
#endif
namespace magic_geo::detail {
namespace {
using namespace cryosphere_prototype;
void need(bool ok, const char *code, const std::string &message) {
    if (!ok)
        throw TerrestrialWaterError(code, message);
}
void finite(double x, const char *name) {
    need(std::isfinite(x), "invalid_request", std::string(name) + " must be finite");
}
void positive(double x, const char *name) {
    finite(x, name);
    need(x > 0, "invalid_request", std::string(name) + " must be positive");
}
bool same(double a, double b) {
    return std::bit_cast<std::uint64_t>(a) == std::bit_cast<std::uint64_t>(b);
}
bool same(Vec3 a, Vec3 b) { return same(a.x, b.x) && same(a.y, b.y) && same(a.z, b.z); }
bool exposed(const Cell &c) { return !c.is_water && !c.is_lake; }
double finite_positive_result(double x, const char *name) {
    positive(x, name);
    return x;
}
void event_id(const std::string &id, std::size_t cap) {
    need(!id.empty() && id.size() <= cap, "invalid_event_id", "event identifier length");
    for (unsigned char ch : id)
        need(ch >= 33 && ch <= 126, "invalid_event_id", "event identifier must be visible ASCII");
}
struct OwnerBundle {
    TerrestrialWaterRestart restart;
    std::size_t committed_intervals = 0;
    std::shared_ptr<const TerrestrialIntervalReceipt> last;
};
} // namespace
TerrestrialWaterError::TerrestrialWaterError(std::string c, std::string message)
    : std::runtime_error(c + ": " + message), code(std::move(c)) {}
TerrestrialWaterCapability terrestrial_water_capability() {
    return {TERRESTRIAL_HAS_A != 0,
            TERRESTRIAL_HAS_A
                ? "extended_long_double_calorimeter_available"
                : "calorimeter_requires_64bit_significand_extended_range_long_double"};
}
struct TerrestrialSurfaceSnapshot::Data {
    std::uint64_t revision;
    std::vector<Cell> cells;
};
TerrestrialSurfaceSnapshot::TerrestrialSurfaceSnapshot(std::shared_ptr<const Data> d)
    : data_(std::move(d)) {}
std::uint64_t TerrestrialSurfaceSnapshot::surface_revision() const { return data_->revision; }
const std::vector<Cell> &TerrestrialSurfaceSnapshot::cells() const { return data_->cells; }
TerrestrialSurfaceSnapshot capture_terrestrial_surface(const std::vector<Cell> &cells,
                                                       std::uint64_t revision) {
    need(!cells.empty() && cells.size() <= 200000, "invalid_context",
         "native cell count outside context bound");
    for (std::size_t i = 0; i < cells.size(); ++i) {
        const auto &c = cells[i];
        need(c.id == static_cast<int>(i), "invalid_context", "noncanonical cell IDs");
        positive(c.area_km2, "cell area");
        finite_positive_result(c.area_km2 * 1e6, "cell area_m2");
        finite(c.elevation_m, "cell elevation");
        finite(c.lat, "latitude");
        finite(c.lon, "longitude");
        finite(c.p.x, "position x");
        finite(c.p.y, "position y");
        finite(c.p.z, "position z");
        need(!(c.is_water && c.is_lake), "invalid_context", "contradictory marine/lake flags");
        finite(c.water_depth_m, "water depth");
        need(c.water_depth_m >= 0, "invalid_context", "negative water depth");
        finite(c.temperature_c, "hydrology temperature");
        finite(c.precipitation_mm_y, "original precipitation");
        finite(c.sediment_thickness_m, "mobile sediment");
        need(c.sediment_thickness_m >= 0, "invalid_context", "negative sediment");
        std::set<int> ns;
        for (int n : c.neighbors)
            need(n >= 0 && n < static_cast<int>(cells.size()) && n != c.id && ns.insert(n).second,
                 "invalid_context", "invalid neighbor");
        for (const auto &v : c.control_volume_vertices) {
            finite(v.x, "vertex x");
            finite(v.y, "vertex y");
            finite(v.z, "vertex z");
        }
    }
    return TerrestrialSurfaceSnapshot(std::make_shared<const TerrestrialSurfaceSnapshot::Data>(
        TerrestrialSurfaceSnapshot::Data{revision, cells}));
}
bool same_terrestrial_surface_epoch(const TerrestrialSurfaceSnapshot &a,
                                    const TerrestrialSurfaceSnapshot &b) {
    return a.data_ == b.data_;
}
bool terrestrial_surface_matches(const TerrestrialSurfaceSnapshot &snapshot,
                                 const std::vector<Cell> &cells) {
    const auto &a = snapshot.cells();
    if (a.size() != cells.size())
        return false;
    for (std::size_t i = 0; i < a.size(); ++i) {
        const auto &x = a[i];
        const auto &y = cells[i];
        if (x.id != y.id || !same(x.area_km2, y.area_km2) || !same(x.elevation_m, y.elevation_m) ||
            !same(x.p, y.p) || !same(x.lat, y.lat) || !same(x.lon, y.lon) ||
            x.is_water != y.is_water || x.is_lake != y.is_lake || x.water_body != y.water_body ||
            !same(x.water_depth_m, y.water_depth_m) || x.neighbors != y.neighbors ||
            x.control_volume_edge_neighbor_ids != y.control_volume_edge_neighbor_ids ||
            x.control_volume_vertices.size() != y.control_volume_vertices.size() ||
            !same(x.temperature_c, y.temperature_c) ||
            !same(x.precipitation_mm_y, y.precipitation_mm_y) ||
            !same(x.sediment_thickness_m, y.sediment_thickness_m) || x.lithology != y.lithology)
            return false;
        for (std::size_t j = 0; j < x.control_volume_vertices.size(); ++j)
            if (!same(x.control_volume_vertices[j], y.control_volume_vertices[j]))
                return false;
    }
    return true;
}
TerrestrialLiquidSupplyProjection
project_terrestrial_liquid_supply(const TerrestrialSurfaceSnapshot &surface,
                                  const std::vector<TerrestrialLiquidHandoff> &outbox,
                                  double duration, double density, double year) {
    positive(duration, "projection duration");
    positive(density, "reference density");
    positive(year, "year duration");
    const auto &cells = surface.cells();
    std::vector<double> mass(cells.size(), 0), energy(cells.size(), 0), rates(cells.size(), 0),
        depth(cells.size(), 0);
    std::vector<bool> applicable;
    for (const auto &c : cells)
        applicable.push_back(exposed(c));
    for (const auto &movement : outbox) {
        need(movement.cell_id >= 0 && movement.cell_id < static_cast<int>(cells.size()) &&
                 applicable[movement.cell_id],
             "invalid_handoff", "wet/unknown recipient supply slot");
        positive(movement.mass_kg, "handoff mass");
        finite(movement.carried_enthalpy_j, "handoff energy");
        mass[movement.cell_id] += movement.mass_kg;
        energy[movement.cell_id] += movement.carried_enthalpy_j;
        finite(mass[movement.cell_id], "summed handoff mass");
        finite(energy[movement.cell_id], "summed handoff energy");
    }
    for (std::size_t i = 0; i < cells.size(); ++i)
        if (mass[i] > 0) {
            // Ordered binary64 conversions; intermediate underflow/overflow refuses.
            double value =
                finite_positive_result(mass[i] / (cells[i].area_km2 * 1e6), "delivered kg_m2");
            value = finite_positive_result(value / density, "delivered depth_m");
            depth[i] = finite_positive_result(value * 1000, "delivered depth_mm");
            value = finite_positive_result(depth[i] * year, "depth times year");
            rates[i] = finite_positive_result(value / duration, "annualized liquid supply");
        }
    TerrestrialLiquidSupplyProjection result;
    result.projected_cells = cells;
    try {
        project_hydrologic_liquid_supply_rates(result.projected_cells, rates, applicable);
    } catch (const std::exception &e) {
        throw TerrestrialWaterError("projection_refusal", e.what());
    }
    for (std::size_t i = 0; i < cells.size(); ++i) {
        const auto &c = result.projected_cells[i];
        for (double value :
             {c.hydrologic_potential_evapotranspiration_mm_y, c.actual_evapotranspiration_mm_y,
              c.infiltration_capacity_index, c.infiltration_mm_y, c.hydrologic_water_balance_mm_y,
              c.water_budget_runoff_mm_y, c.runoff_mm_y, c.runoff_budget_residual_mm_y,
              c.runoff_budget_consistency_index, c.hydrologic_deficit_mm_y,
              c.runoff_generation_fraction}) {
            need(std::isfinite(value), "projection_refusal", "nonfinite hydrology output");
        }
        const auto amount = [&](double rate) {
            need(rate >= 0, "projection_refusal", "negative allocation rate");
            if (rate == 0)
                return 0.0;
            return finite_positive_result(
                finite_positive_result(rate * duration, "rate times duration") / year,
                "interval allocation");
        };
        const double aet = amount(c.actual_evapotranspiration_mm_y);
        const double inf = amount(c.infiltration_mm_y);
        const double run = amount(c.runoff_mm_y);
        finite(aet, "interval AET");
        finite(inf, "interval infiltration");
        finite(run, "interval runoff");
        result.cells.push_back({static_cast<int>(i), applicable[i], cells[i].precipitation_mm_y,
                                mass[i], energy[i], depth[i], rates[i], aet, inf, run,
                                depth[i] - aet - inf - run});
    }
    return result;
}
struct TerrestrialIntervalCandidate::Data {
    std::shared_ptr<const int> owner;
    std::shared_ptr<const OwnerBundle> base, replacement;
};
TerrestrialIntervalCandidate::TerrestrialIntervalCandidate(std::shared_ptr<const Data> d)
    : data_(std::move(d)) {}
const TerrestrialIntervalReceipt &TerrestrialIntervalCandidate::receipt() const {
    return *data_->replacement->last;
}
struct TerrestrialWaterOwner::Impl {
    TerrestrialSurfaceSnapshot surface;
    TerrestrialWaterProperties properties;
    TerrestrialWaterLimits limits;
    std::shared_ptr<const int> anchor = std::make_shared<const int>(0);
    std::shared_ptr<const OwnerBundle> accepted;
    Impl(TerrestrialSurfaceSnapshot s, TerrestrialWaterProperties p, TerrestrialWaterLimits l)
        : surface(std::move(s)), properties(std::move(p)), limits(l) {}
};
TerrestrialWaterOwner::TerrestrialWaterOwner(TerrestrialSurfaceSnapshot surface,
                                             TerrestrialWaterProperties properties,
                                             TerrestrialWaterRestart initial,
                                             TerrestrialWaterLimits limits)
    : impl_(std::make_unique<Impl>(std::move(surface), std::move(properties), limits)) {
    need(terrestrial_water_capability().available, "capability_unavailable",
         terrestrial_water_capability().reason);
    const auto &cs = impl_->surface.cells();
    const auto &p = impl_->properties;
    need(limits.max_cells > 0 && limits.max_cells <= 4096 && limits.max_committed_intervals > 0 &&
             limits.max_committed_intervals <= 128 && limits.max_events_per_interval > 0 &&
             limits.max_events_per_interval <= 8192 && limits.max_consumed_event_ids > 0 &&
             limits.max_consumed_event_ids <= 65536 && limits.max_identifier_bytes > 0 &&
             limits.max_identifier_bytes <= 96,
         "invalid_limits", "limits must be positive and no larger than declared caps");
    need(cs.size() <= limits.max_cells && initial.state.size() == cs.size() &&
             p.dry_heat_capacity_j_m2_k.size() == cs.size(),
         "invalid_restart", "state/capacity coverage or cell cap");
    positive(p.reference_water_density_kg_m3, "reference density");
    positive(p.year_duration_seconds, "year duration");
    positive(p.water.freezing_temperature_k, "freezing temperature");
    positive(p.water.solid_heat_capacity_j_kg_k, "solid heat capacity");
    positive(p.water.liquid_heat_capacity_j_kg_k, "liquid heat capacity");
    positive(p.water.latent_heat_j_kg, "latent heat");
    finite(initial.elapsed_seconds, "elapsed seconds");
    need(initial.elapsed_seconds >= 0, "invalid_restart", "negative elapsed time");
    need(initial.consumed_event_ids.size() <= limits.max_consumed_event_ids, "event_cap",
         "restart consumed ID cap");
    std::set<std::string> ids;
    for (const auto &id : initial.consumed_event_ids) {
        event_id(id, limits.max_identifier_bytes);
        need(ids.insert(id).second, "duplicate_event", "duplicate restart event");
    }
    for (std::size_t i = 0; i < cs.size(); ++i) {
        const auto &x = initial.state[i];
        finite(x.water_mass_kg_m2, "restart W");
        finite(x.enthalpy_j_m2, "restart H");
        need(x.water_mass_kg_m2 >= 0, "invalid_restart", "negative W");
        if (!exposed(cs[i]))
            need(x.water_mass_kg_m2 == 0 && x.enthalpy_j_m2 == 0 &&
                     p.dry_heat_capacity_j_m2_k[i] == 0,
                 "invalid_restart", "wet slots require zero terrestrial W/H/capacity");
#if TERRESTRIAL_HAS_A
        else {
            positive(p.dry_heat_capacity_j_m2_k[i], "dry heat capacity");
            (void)phase_state(p.water, {cs[i].area_km2 * 1e6, p.dry_heat_capacity_j_m2_k[i]}, x);
        }
#endif
    }
    impl_->accepted = std::make_shared<const OwnerBundle>(OwnerBundle{std::move(initial), 0, {}});
}
TerrestrialWaterOwner::~TerrestrialWaterOwner() = default;
TerrestrialWaterOwner::TerrestrialWaterOwner(TerrestrialWaterOwner &&) noexcept = default;
TerrestrialWaterOwner &
TerrestrialWaterOwner::operator=(TerrestrialWaterOwner &&) noexcept = default;
const TerrestrialWaterRestart &TerrestrialWaterOwner::restart() const {
    return impl_->accepted->restart;
}
const TerrestrialIntervalReceipt *TerrestrialWaterOwner::last_receipt() const {
    return impl_->accepted->last.get();
}
const TerrestrialSurfaceSnapshot &TerrestrialWaterOwner::surface() const { return impl_->surface; }
const TerrestrialWaterProperties &TerrestrialWaterOwner::properties() const {
    return impl_->properties;
}
const TerrestrialWaterLimits &TerrestrialWaterOwner::limits() const { return impl_->limits; }
TerrestrialIntervalCandidate
TerrestrialWaterOwner::prepare(const TerrestrialIntervalRequest &request) const {
    const auto &base = impl_->accepted;
    const auto &initial = base->restart;
    const auto &cs = impl_->surface.cells();
    const auto &p = impl_->properties;
    const auto &limits = impl_->limits;
    need(request.expected_revision == initial.revision, "stale_revision",
         "request does not bind accepted revision");
    need(initial.revision < std::numeric_limits<std::uint64_t>::max() &&
             base->committed_intervals < limits.max_committed_intervals,
         "interval_cap", "revision/interval cap");
    positive(request.duration_seconds, "interval duration");
    const double end = initial.elapsed_seconds + request.duration_seconds;
    need(std::isfinite(end) && end > initial.elapsed_seconds, "invalid_clock",
         "elapsed endpoint outside increasing finite range");
    const double bp = end - initial.elapsed_seconds;
    const double remainder =
        (initial.elapsed_seconds - (end - bp)) + (request.duration_seconds - bp);
    need(remainder == 0, "invalid_clock", "elapsed+duration is not exactly representable");
    need(request.net_heat_flux_w_m2.size() == cs.size(), "invalid_request",
         "heat coverage mismatch");
    need(request.precipitation_imports.size() <= limits.max_events_per_interval &&
             request.initial_liquid_withdrawals.size() <= limits.max_events_per_interval,
         "event_cap", "individual event vector cap");
    const auto events =
        request.precipitation_imports.size() + request.initial_liquid_withdrawals.size();
    need(events <= limits.max_events_per_interval &&
             events <= limits.max_consumed_event_ids - initial.consumed_event_ids.size(),
         "event_cap", "interval or consumed event cap");
    std::set<std::string> ids(initial.consumed_event_ids.begin(), initial.consumed_event_ids.end());
    const auto claim = [&](const std::string &id, int cid, double mass) {
        event_id(id, limits.max_identifier_bytes);
        need(ids.insert(id).second, "duplicate_event", "event already consumed or repeated");
        need(cid >= 0 && cid < static_cast<int>(cs.size()) && exposed(cs[cid]), "invalid_event",
             "wet/unknown event cell");
        positive(mass, "event mass");
    };
    for (const auto &x : request.precipitation_imports) {
        claim(x.id, x.cell_id, x.mass_kg);
        finite(x.temperature_k, "precipitation temperature");
        need(x.temperature_k >= 0, "invalid_event", "negative absolute source temperature");
        need(x.phase == Phase::solid || x.phase == Phase::liquid, "invalid_event",
             "unsupported source phase");
        need(x.phase == Phase::solid ? x.temperature_k <= p.water.freezing_temperature_k
                                     : x.temperature_k >= p.water.freezing_temperature_k,
             "invalid_event", "source phase/temperature disagreement");
    }
    for (const auto &x : request.initial_liquid_withdrawals)
        claim(x.id, x.cell_id, x.mass_kg);
    std::vector<int> map(cs.size(), -1), column_ids;
    std::vector<Column> columns;
    std::vector<State> states;
    StepInput in{request.duration_seconds, {}, {}, {}, {}};
    for (std::size_t i = 0; i < cs.size(); ++i) {
        finite(request.net_heat_flux_w_m2[i], "heat flux");
        if (exposed(cs[i])) {
            map[i] = static_cast<int>(columns.size());
            column_ids.push_back(static_cast<int>(i));
            columns.push_back({cs[i].area_km2 * 1e6, p.dry_heat_capacity_j_m2_k[i]});
            states.push_back(initial.state[i]);
            in.net_heat_flux_w_m2.push_back(request.net_heat_flux_w_m2[i]);
        } else
            need(request.net_heat_flux_w_m2[i] == 0, "invalid_request", "wet heat must be zero");
    }
    for (const auto &x : request.precipitation_imports)
        in.imports.push_back(
            {static_cast<std::size_t>(map[x.cell_id]), x.phase, x.mass_kg, x.temperature_k});
    for (const auto &x : request.initial_liquid_withdrawals)
        in.exports.push_back({static_cast<std::size_t>(map[x.cell_id]), Phase::liquid, x.mass_kg});
    StepResult result{};
#if TERRESTRIAL_HAS_A
    if (!columns.empty()) {
        try {
            result = advance(p.water, columns, states, in);
        } catch (const cryosphere_prototype::Error &e) {
            throw TerrestrialWaterError("kernel_refusal", e.what());
        }
    }
#else
    throw TerrestrialWaterError("capability_unavailable", terrestrial_water_capability().reason);
#endif
    TerrestrialIntervalReceipt receipt{};
    receipt.surface_revision = impl_->surface.surface_revision();
    receipt.properties = p;
    receipt.limits = limits;
    receipt.surface_cells = cs;
    receipt.initial = initial;
    receipt.request = request;
    receipt.final = initial;
    receipt.final.revision++;
    receipt.final.elapsed_seconds = end;
    receipt.final.consumed_event_ids.assign(ids.begin(), ids.end());
    receipt.kernel_column_cell_ids = column_ids;
    receipt.kernel_result = std::move(result);
    for (std::size_t i = 0; i < column_ids.size(); ++i)
        receipt.final.state[column_ids[i]] = receipt.kernel_result.state[i];
    // Recover original event IDs by matching the kernel's canonical export
    // movement multiset. Equal withdrawals are interchangeable in canonical A;
    // retain stable original request order when linking indistinguishable ones.
    std::vector<bool> used(receipt.kernel_result.movements.size(), false);
    for (const auto &x : request.initial_liquid_withdrawals) {
        bool found = false;
        for (std::size_t j = 0; j < used.size(); ++j) {
            const auto &m = receipt.kernel_result.movements[j];
            if (!used[j] && m.donor == map[x.cell_id] && m.recipient == -1 &&
                m.phase == Phase::liquid && same(m.mass_kg, x.mass_kg)) {
                used[j] = true;
                found = true;
                receipt.liquid_outbox.push_back(
                    {x.id, x.cell_id, m.mass_kg, m.carried_enthalpy_j, j});
                break;
            }
        }
        need(found, "kernel_receipt", "export movement linkage missing");
    }
    receipt.projection = project_terrestrial_liquid_supply(
        impl_->surface, receipt.liquid_outbox, request.duration_seconds,
        p.reference_water_density_kg_m3, p.year_duration_seconds);
    auto completed = std::make_shared<const TerrestrialIntervalReceipt>(std::move(receipt));
    auto replacement = std::make_shared<const OwnerBundle>(
        OwnerBundle{completed->final, base->committed_intervals + 1, completed});
    return TerrestrialIntervalCandidate(std::make_shared<const TerrestrialIntervalCandidate::Data>(
        TerrestrialIntervalCandidate::Data{impl_->anchor, base, std::move(replacement)}));
}
void TerrestrialWaterOwner::commit(const TerrestrialIntervalCandidate &candidate) {
    need(candidate.data_ && candidate.data_->owner == impl_->anchor, "foreign_candidate",
         "candidate belongs to a different owner");
    need(candidate.data_->base == impl_->accepted, "stale_candidate",
         "candidate restart is no longer accepted");
    auto replacement = candidate.data_->replacement;
    impl_->accepted.swap(replacement); // Nothrow one-bundle publication.
}
} // namespace magic_geo::detail
