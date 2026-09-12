#include "cryosphere_enthalpy.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <string>
#include <tuple>
#include <utility>

namespace cryosphere_prototype {
namespace {
using Wide = long double;
static_assert(std::numeric_limits<Wide>::digits >= 64 &&
              std::numeric_limits<Wide>::max_exponent >= 16384,
              "Research prototype requires extended-range long double");

void require(bool condition, const std::string& path) {
    if (!condition) throw Error(path);
}

void positive(double x, const std::string& path) {
    require(std::isfinite(x) && x > 0, path + ": expected finite positive number");
}

void nonnegative(double x, const std::string& path) {
    require(std::isfinite(x) && x >= 0, path + ": expected finite nonnegative number");
}

double represented(Wide x, const std::string& path) {
    require(std::isfinite(x) && std::abs(x) <= std::numeric_limits<double>::max(),
            path + ": outside finite binary64 range");
    const double result = static_cast<double>(x);
    require(x == 0 || result != 0, path + ": nonzero quantity underflows binary64");
    return result;
}

Wide ulp(double x) {
    x = std::abs(x);
    require(std::isfinite(x), "roundoff parent is nonfinite");
    const double upper = std::nextafter(x, std::numeric_limits<double>::infinity());
    return std::isfinite(upper) ? static_cast<Wide>(upper) - x
        : static_cast<Wide>(x) - std::nextafter(x, 0.0);
}

double allowance(std::initializer_list<double> parents, const std::string& path) {
    Wide result = 0;
    for (const double x : parents) result += 8 * ulp(x);
    return represented(result, path);
}

// Error-free expansion of finite dyadic ledger amounts. Unlike one wide
// accumulator, this retains small remainders across large cancellation and
// permits exact gross-inventory comparisons. Products use an FMA residual.
// The final conversion is rounded; the physical ledger is not recentered.
class Expansion {
public:
    Expansion(Wide value=0) { add(value); }
    void add(Wide value) {
        require(std::isfinite(value), "nonfinite accounting term");
        std::vector<Wide> replacement;
        replacement.reserve(parts.size()+1);
        for (Wide term : parts) {
            if (std::abs(value)<std::abs(term)) std::swap(value,term);
            const Wide high=value+term;
            require(std::isfinite(high), "accounting accumulation overflow");
            const Wide low=term-(high-value);
            if (low!=0) replacement.push_back(low);
            value=high;
        }
        if (value!=0 || replacement.empty()) replacement.push_back(value);
        parts.swap(replacement);
    }
    void add(const Expansion& other) { for (Wide value:other.parts) add(value); }
    Expansion scaled(Wide factor) const {
        Expansion result;
        for (Wide value:parts) {
            const Wide high=value*factor;
            require(std::isfinite(high), "accounting product overflow");
            require(value==0 || factor==0 || high!=0, "accounting product underflow");
            const Wide low=std::fma(value,factor,-high);
            result.add(low); result.add(high);
        }
        return result;
    }
    Wide value() const { Wide result=0; for(Wide term:parts) result+=term; return result; }
    int sign() const { return parts.back()>0 ? 1 : parts.back()<0 ? -1 : 0; }
private:
    std::vector<Wide> parts;
};
Expansion difference(Expansion first,const Expansion& second) {
    first.add(second.scaled(-1)); return first;
}

void properties(const WaterProperties& p) {
    positive(p.freezing_temperature_k, "properties.freezing_temperature_k");
    positive(p.solid_heat_capacity_j_kg_k, "properties.solid_heat_capacity_j_kg_k");
    positive(p.liquid_heat_capacity_j_kg_k, "properties.liquid_heat_capacity_j_kg_k");
    positive(p.latent_heat_j_kg, "properties.latent_heat_j_kg");
}

struct WidePhase { Wide temperature, offset, solid, liquid; };

WidePhase invert(const WaterProperties& p, const Column& c, const State& s,
                 const std::string& path, bool pure_water = false) {
    positive(c.area_m2, path + ".area_m2");
    if (pure_water) {
        nonnegative(c.dry_heat_capacity_j_m2_k, path + ".dry_heat_capacity_j_m2_k");
        require(c.dry_heat_capacity_j_m2_k > 0 || s.water_mass_kg_m2 > 0, path + ": empty thermal storage");
    } else positive(c.dry_heat_capacity_j_m2_k, path + ".dry_heat_capacity_j_m2_k");
    nonnegative(s.water_mass_kg_m2, path + ".water_mass_kg_m2");
    require(std::isfinite(s.enthalpy_j_m2), path + ".enthalpy_j_m2: expected finite number");
    const Wide water = s.water_mass_kg_m2;
    const Wide heat = s.enthalpy_j_m2;
    const Expansion latent_exact=Expansion(water).scaled(p.latent_heat_j_kg);
    const Wide latent=latent_exact.value();
    const Expansion above_latent=difference(Expansion(heat),latent_exact);
    require(std::isfinite(latent) && latent>=0,path+": nonfinite internal latent inventory");
    WidePhase result;
    if (water == 0) {
        const Wide offset=heat/c.dry_heat_capacity_j_m2_k;
        auto above_zero=Expansion(c.dry_heat_capacity_j_m2_k).scaled(p.freezing_temperature_k);
        above_zero.add(heat);
        require(above_zero.sign()>=0,path+": state implies negative absolute temperature");
        result = {above_zero.value()/c.dry_heat_capacity_j_m2_k,offset,0,0};
    } else if (heat < 0) {
        auto capacity_exact=Expansion(water).scaled(p.solid_heat_capacity_j_kg_k);
        capacity_exact.add(c.dry_heat_capacity_j_m2_k);
        const Wide capacity=capacity_exact.value();
        require(std::isfinite(capacity) && capacity>0,path+": nonfinite internal solid capacity");
        const Wide offset=heat/capacity;
        auto above_zero=capacity_exact.scaled(p.freezing_temperature_k);
        above_zero.add(heat);
        require(above_zero.sign()>=0,path+": state implies negative absolute temperature");
        result = {above_zero.value()/capacity,offset,water,0};
    } else if (above_latent.sign()<=0) {
        const Wide liquid = heat / p.latent_heat_j_kg;
        const Wide solid=-above_latent.value()/p.latent_heat_j_kg;
        result = {p.freezing_temperature_k,0,solid,liquid};
    } else {
        const Wide capacity = c.dry_heat_capacity_j_m2_k + water * p.liquid_heat_capacity_j_kg_k;
        require(std::isfinite(capacity) && capacity>0,path+": nonfinite internal liquid capacity");
        const Wide offset=above_latent.value()/capacity;
        result = {p.freezing_temperature_k+offset,offset,0,water};
    }
    require(result.temperature >= 0, path + ": state implies negative absolute temperature");
    represented(result.temperature, path + ".temperature_k");
    represented(result.solid, path + ".solid_mass_kg_m2");
    represented(result.liquid, path + ".liquid_mass_kg_m2");
    return result;
}

PhaseState publish_phase(const WidePhase& p) {
    return {static_cast<double>(p.temperature), static_cast<double>(p.solid), static_cast<double>(p.liquid)};
}

void phase_valid(Phase phase) {
    require(phase == Phase::solid || phase == Phase::liquid, "movement.phase: unsupported phase");
}

Expansion specific_enthalpy(const WaterProperties& p, Phase phase, Wide offset) {
    phase_valid(phase);
    require(std::isfinite(offset), "movement: nonfinite temperature offset");
    if (phase == Phase::solid) {
        require(offset<=0, "solid temperature is warmer than freezing");
        return Expansion(offset).scaled(p.solid_heat_capacity_j_kg_k);
    }
    require(offset>=0, "liquid temperature is colder than freezing");
    auto result=Expansion(offset).scaled(p.liquid_heat_capacity_j_kg_k);
    result.add(p.latent_heat_j_kg);
    return result;
}

struct Totals { Expansion in_mass,out_mass,in_energy,out_energy,solid_out,liquid_out; };

struct EventAccounting {
    std::vector<Movement> movements;
    std::vector<Totals> totals;
    Expansion external_mass;
    Expansion external_energy;
};

// Shared canonical movement construction and exact initial-donor certification.
// Neither public entry can fund gross withdrawals from simultaneous receipts.
EventAccounting prepare_events(const WaterProperties& p, const std::vector<Column>& columns,
                               const std::vector<State>& initial,
                               const std::vector<WidePhase>& source,
                               const std::vector<Import>& imports,
                               const std::vector<Export>& exports,
                               const std::vector<Transfer>& transfers) {
    const std::size_t count = columns.size();
    auto index_valid = [count](std::size_t i) {
        require(i < count, "movement: unknown cell index");
    };
    EventAccounting result;
    auto movement = [&](int donor, int recipient, Phase phase, double mass, Wide temperature, Wide offset) {
        phase_valid(phase);
        positive(mass, "movement.mass_kg");
        const Expansion physical_specific=specific_enthalpy(p,phase,offset);
        const double specific=represented(physical_specific.value(),"movement.specific_enthalpy_j_kg");
        // The one represented amount below is both donor debit and recipient
        // credit; no independent multiplication with a different reference.
        const double energy=represented(physical_specific.scaled(mass).value(),"movement.carried_enthalpy_j");
        result.movements.push_back({donor, recipient, phase, mass,
            represented(temperature, "movement.temperature_k"), specific, energy});
    };
    for (const Import& item : imports) {
        index_valid(item.recipient);
        nonnegative(item.temperature_k, "import.temperature_k");
        movement(-1,static_cast<int>(item.recipient),item.phase,item.mass_kg,item.temperature_k,
                 static_cast<Wide>(item.temperature_k)-p.freezing_temperature_k);
    }
    for (const Export& item : exports) {
        index_valid(item.donor);
        movement(static_cast<int>(item.donor),-1,item.phase,item.mass_kg,
                 source[item.donor].temperature,source[item.donor].offset);
    }
    for (const Transfer& item : transfers) {
        index_valid(item.donor); index_valid(item.recipient);
        require(item.donor != item.recipient, "transfer: self transfer is not allowed");
        movement(static_cast<int>(item.donor), static_cast<int>(item.recipient), item.phase,
                 item.mass_kg,source[item.donor].temperature,source[item.donor].offset);
    }
    std::sort(result.movements.begin(), result.movements.end(), [](const Movement& a, const Movement& b) {
        return std::tie(a.donor,a.recipient,a.phase,a.mass_kg,a.temperature_k,a.specific_enthalpy_j_kg)
             < std::tie(b.donor,b.recipient,b.phase,b.mass_kg,b.temperature_k,b.specific_enthalpy_j_kg);
    });
    result.totals.resize(count);
    auto& totals = result.totals;
    auto& external_mass = result.external_mass;
    auto& external_energy = result.external_energy;
    for (const auto& item : result.movements) {
        if (item.donor >= 0) {
            auto& t = totals[static_cast<std::size_t>(item.donor)];
            t.out_mass.add(item.mass_kg); t.out_energy.add(item.carried_enthalpy_j);
            (item.phase==Phase::solid ? t.solid_out : t.liquid_out).add(item.mass_kg);
        } else { external_mass.add(item.mass_kg); external_energy.add(item.carried_enthalpy_j); }
        if (item.recipient >= 0) {
            auto& t = totals[static_cast<std::size_t>(item.recipient)];
            t.in_mass.add(item.mass_kg); t.in_energy.add(item.carried_enthalpy_j);
        } else { external_mass.add(-item.mass_kg); external_energy.add(-item.carried_enthalpy_j); }
    }
    // No mass/heat update occurs until every donor's gross demand is certified.
    for (std::size_t i=0; i<count; ++i) {
        const Expansion latent=Expansion(initial[i].water_mass_kg_m2).scaled(p.latent_heat_j_kg);
        const Expansion heat(initial[i].enthalpy_j_m2);
        const Expansion liquid_equivalent=initial[i].enthalpy_j_m2<=0 ? Expansion(0)
            : difference(heat,latent).sign()>=0 ? latent : heat;
        const Expansion solid_equivalent=difference(latent,liquid_equivalent);
        require(difference(totals[i].solid_out.scaled(p.latent_heat_j_kg),
                           solid_equivalent.scaled(columns[i].area_m2)).sign()<=0,
                "donor["+std::to_string(i)+"] insufficient initial solid inventory");
        require(difference(totals[i].liquid_out.scaled(p.latent_heat_j_kg),
                           liquid_equivalent.scaled(columns[i].area_m2)).sign()<=0,
                "donor["+std::to_string(i)+"] insufficient initial liquid inventory");
    }
    return result;
}

struct MassUpdate {
    State state;
    Expansion unrounded_energy;
};

MassUpdate mass_update(const WaterProperties& p, const Column& column, const State& initial,
                       const Totals& totals, std::size_t index, bool pure_water = false) {
    const Wide area = column.area_m2;
    auto remaining_mass = Expansion(initial.water_mass_kg_m2).scaled(area);
    remaining_mass.add(totals.in_mass);
    remaining_mass.add(totals.out_mass.scaled(-1));
    auto after_mass_energy = Expansion(initial.enthalpy_j_m2).scaled(area);
    after_mass_energy.add(totals.in_energy);
    after_mass_energy.add(totals.out_energy.scaled(-1));
    const double next_mass = represented(remaining_mass.value()/area, "final.water_mass_kg_m2");
    // The event must itself be admissible. Later heating may not conceal an
    // invalid intermediate reservoir or an overflow.
    const State event{next_mass, represented(after_mass_energy.value()/area, "mass_event.enthalpy_j_m2")};
    invert(p, column, event, "mass_event["+std::to_string(index)+"]", pure_water);
    return {event, after_mass_energy};
}
}  // namespace

PhaseState phase_state(const WaterProperties& p, const Column& c, const State& s) {
    properties(p);
    return publish_phase(invert(p, c, s, "state"));
}

StepResult advance(const WaterProperties& p, const std::vector<Column>& columns,
                   const std::vector<State>& initial, const StepInput& input) {
    properties(p);
    const std::size_t count = columns.size();
    require(count > 0 && count <= static_cast<std::size_t>(std::numeric_limits<int>::max()),
            "columns: expected nonempty bounded array");
    require(initial.size() == count, "initial: column coverage mismatch");
    require(input.net_heat_flux_w_m2.size() == count, "net_heat_flux_w_m2: column coverage mismatch");
    positive(input.duration_seconds, "duration_seconds");
    std::vector<WidePhase> source;
    source.reserve(count);
    for (std::size_t i=0; i<count; ++i) {
        source.push_back(invert(p, columns[i], initial[i], "initial["+std::to_string(i)+"]"));
        require(std::isfinite(input.net_heat_flux_w_m2[i]), "net_heat_flux_w_m2: nonfinite source");
    }
    auto event = prepare_events(p, columns, initial, source, input.imports, input.exports, input.transfers);
    StepResult result;
    result.movements = std::move(event.movements);
    const auto& totals = event.totals;
    const auto& external_mass = event.external_mass;
    const auto& external_energy = event.external_energy;
    Expansion mass_change,energy_change,heat_total;
    Wide mass_allowance=0,energy_allowance=0;
    for (std::size_t i=0; i<count; ++i) {
        const Wide area = columns[i].area_m2;
        const auto& t = totals[i];
        Ledger ledger{};
        ledger.imported_mass_kg_m2 = represented(t.in_mass.value()/area, "ledger.imported_mass_kg_m2");
        ledger.exported_mass_kg_m2 = represented(t.out_mass.value()/area, "ledger.exported_mass_kg_m2");
        ledger.imported_enthalpy_j_m2 = represented(t.in_energy.value()/area, "ledger.imported_enthalpy_j_m2");
        ledger.exported_enthalpy_j_m2 = represented(t.out_energy.value()/area, "ledger.exported_enthalpy_j_m2");
        ledger.prescribed_heat_j_m2 = represented(static_cast<Wide>(input.net_heat_flux_w_m2[i])*input.duration_seconds,
                                                "ledger.prescribed_heat_j_m2");
        const auto mass_event = mass_update(p, columns[i], initial[i], t, i);
        const double next_mass = mass_event.state.water_mass_kg_m2;
        // Keep the private expansion, never the rounded public event state.
        auto final_energy=mass_event.unrounded_energy;
        final_energy.add(Expansion(ledger.prescribed_heat_j_m2).scaled(area));
        const State next{next_mass,represented(final_energy.value()/area,"final.enthalpy_j_m2")};
        result.phase.push_back(publish_phase(invert(p, columns[i], next, "final["+std::to_string(i)+"]")));
        result.state.push_back(next);
        auto mass_residual=difference(Expansion(next.water_mass_kg_m2),Expansion(initial[i].water_mass_kg_m2));
        mass_residual.add(-ledger.imported_mass_kg_m2); mass_residual.add(ledger.exported_mass_kg_m2);
        ledger.mass_residual_kg_m2=represented(mass_residual.value(),"ledger.mass_residual_kg_m2");
        auto energy_residual=difference(Expansion(next.enthalpy_j_m2),Expansion(initial[i].enthalpy_j_m2));
        energy_residual.add(-ledger.imported_enthalpy_j_m2); energy_residual.add(ledger.exported_enthalpy_j_m2);
        energy_residual.add(-ledger.prescribed_heat_j_m2);
        ledger.energy_residual_j_m2=represented(energy_residual.value(),"ledger.energy_residual_j_m2");
        ledger.mass_roundoff_allowance_kg_m2 = allowance({next.water_mass_kg_m2,initial[i].water_mass_kg_m2,
            ledger.imported_mass_kg_m2,ledger.exported_mass_kg_m2}, "ledger.mass_roundoff_allowance_kg_m2");
        ledger.energy_roundoff_allowance_j_m2 = allowance({next.enthalpy_j_m2,initial[i].enthalpy_j_m2,
            ledger.imported_enthalpy_j_m2,ledger.exported_enthalpy_j_m2,ledger.prescribed_heat_j_m2},
            "ledger.energy_roundoff_allowance_j_m2");
        require(std::abs(ledger.mass_residual_kg_m2) <= ledger.mass_roundoff_allowance_kg_m2,
                "mass residual exceeds representational allowance");
        require(std::abs(ledger.energy_residual_j_m2) <= ledger.energy_roundoff_allowance_j_m2,
                "energy residual exceeds representational allowance");
        result.ledger.push_back(ledger);
        mass_change.add(difference(Expansion(next.water_mass_kg_m2),Expansion(initial[i].water_mass_kg_m2)).scaled(area));
        energy_change.add(difference(Expansion(next.enthalpy_j_m2),Expansion(initial[i].enthalpy_j_m2)).scaled(area));
        heat_total.add(Expansion(ledger.prescribed_heat_j_m2).scaled(area));
        mass_allowance += area*ledger.mass_roundoff_allowance_kg_m2;
        energy_allowance += area*ledger.energy_roundoff_allowance_j_m2;
    }
    result.global_mass_change_kg = represented(mass_change.value(), "global_mass_change_kg");
    result.external_net_mass_kg = represented(external_mass.value(), "external_net_mass_kg");
    result.global_mass_residual_kg = represented(difference(mass_change,external_mass).value(), "global_mass_residual_kg");
    result.global_energy_change_j = represented(energy_change.value(), "global_energy_change_j");
    result.external_net_enthalpy_j = represented(external_energy.value(), "external_net_enthalpy_j");
    result.prescribed_heat_j = represented(heat_total.value(), "prescribed_heat_j");
    result.global_energy_residual_j = represented(difference(difference(energy_change,external_energy),heat_total).value(), "global_energy_residual_j");
    result.global_mass_roundoff_allowance_kg = represented(mass_allowance+
        allowance({result.global_mass_change_kg,result.external_net_mass_kg}, "global mass rounding"),
        "global_mass_roundoff_allowance_kg");
    result.global_energy_roundoff_allowance_j = represented(energy_allowance+
        allowance({result.global_energy_change_j,result.external_net_enthalpy_j,result.prescribed_heat_j},
                  "global energy rounding"), "global_energy_roundoff_allowance_j");
    require(std::abs(result.global_mass_residual_kg) <= result.global_mass_roundoff_allowance_kg,
            "global mass residual exceeds representational allowance");
    require(std::abs(result.global_energy_residual_j) <= result.global_energy_roundoff_allowance_j,
            "global energy residual exceeds representational allowance");
    return result;
}

static MassEventResult mass_events_impl(const WaterProperties& p, const std::vector<Column>& columns,
                                 const std::vector<State>& initial, const MassEventInput& input, bool pure_water) {
    properties(p);
    const std::size_t count = columns.size();
    require(count > 0 && count <= static_cast<std::size_t>(std::numeric_limits<int>::max()),
            "columns: expected nonempty bounded array");
    require(initial.size() == count, "initial: column coverage mismatch");
    std::vector<WidePhase> source;
    source.reserve(count);
    for (std::size_t i = 0; i < count; ++i) {
        source.push_back(invert(p, columns[i], initial[i], "initial["+std::to_string(i)+"]", pure_water));
    }

    MassEventResult result{};
    if (input.imports.empty() && input.exports.empty() && input.transfers.empty()) {
        // No arithmetic projection, even for signed zero. Validation still
        // happens above; identity is not a way to accept an invalid reservoir.
        result.state = initial;
        result.ledger.resize(count);
        for (const auto& phase : source) result.phase.push_back(publish_phase(phase));
        return result;
    }

    auto event = prepare_events(p, columns, initial, source, input.imports, input.exports, input.transfers);
    result.movements = std::move(event.movements);
    Expansion mass_change, energy_change;
    Wide mass_allowance = 0, energy_allowance = 0;
    for (std::size_t i = 0; i < count; ++i) {
        const Wide area = columns[i].area_m2;
        const auto& totals = event.totals[i];
        MassEventLedger ledger{};
        ledger.imported_mass_kg_m2 = represented(totals.in_mass.value()/area, "ledger.imported_mass_kg_m2");
        ledger.exported_mass_kg_m2 = represented(totals.out_mass.value()/area, "ledger.exported_mass_kg_m2");
        ledger.imported_enthalpy_j_m2 = represented(totals.in_energy.value()/area, "ledger.imported_enthalpy_j_m2");
        ledger.exported_enthalpy_j_m2 = represented(totals.out_energy.value()/area, "ledger.exported_enthalpy_j_m2");
        const auto update = mass_update(p, columns[i], initial[i], totals, i, pure_water);
        const State next = update.state;
        result.phase.push_back(publish_phase(invert(p, columns[i], next, "final["+std::to_string(i)+"]", pure_water)));
        result.state.push_back(next);

        auto mass_residual = difference(Expansion(next.water_mass_kg_m2), Expansion(initial[i].water_mass_kg_m2));
        mass_residual.add(-ledger.imported_mass_kg_m2);
        mass_residual.add(ledger.exported_mass_kg_m2);
        ledger.mass_residual_kg_m2 = represented(mass_residual.value(), "ledger.mass_residual_kg_m2");
        auto energy_residual = difference(Expansion(next.enthalpy_j_m2), Expansion(initial[i].enthalpy_j_m2));
        energy_residual.add(-ledger.imported_enthalpy_j_m2);
        energy_residual.add(ledger.exported_enthalpy_j_m2);
        ledger.energy_residual_j_m2 = represented(energy_residual.value(), "ledger.energy_residual_j_m2");
        ledger.mass_roundoff_allowance_kg_m2 = allowance({next.water_mass_kg_m2, initial[i].water_mass_kg_m2,
            ledger.imported_mass_kg_m2, ledger.exported_mass_kg_m2}, "ledger.mass_roundoff_allowance_kg_m2");
        ledger.energy_roundoff_allowance_j_m2 = allowance({next.enthalpy_j_m2, initial[i].enthalpy_j_m2,
            ledger.imported_enthalpy_j_m2, ledger.exported_enthalpy_j_m2}, "ledger.energy_roundoff_allowance_j_m2");
        require(std::abs(ledger.mass_residual_kg_m2) <= ledger.mass_roundoff_allowance_kg_m2,
                "mass residual exceeds representational allowance");
        require(std::abs(ledger.energy_residual_j_m2) <= ledger.energy_roundoff_allowance_j_m2,
                "energy residual exceeds representational allowance");
        result.ledger.push_back(ledger);

        mass_change.add(difference(Expansion(next.water_mass_kg_m2), Expansion(initial[i].water_mass_kg_m2)).scaled(area));
        energy_change.add(difference(Expansion(next.enthalpy_j_m2), Expansion(initial[i].enthalpy_j_m2)).scaled(area));
        mass_allowance += area*ledger.mass_roundoff_allowance_kg_m2;
        energy_allowance += area*ledger.energy_roundoff_allowance_j_m2;
    }
    result.global_mass_change_kg = represented(mass_change.value(), "global_mass_change_kg");
    result.external_net_mass_kg = represented(event.external_mass.value(), "external_net_mass_kg");
    result.global_mass_residual_kg = represented(difference(mass_change, event.external_mass).value(), "global_mass_residual_kg");
    result.global_energy_change_j = represented(energy_change.value(), "global_energy_change_j");
    result.external_net_enthalpy_j = represented(event.external_energy.value(), "external_net_enthalpy_j");
    result.global_energy_residual_j = represented(difference(energy_change, event.external_energy).value(), "global_energy_residual_j");
    result.global_mass_roundoff_allowance_kg = represented(mass_allowance+
        allowance({result.global_mass_change_kg, result.external_net_mass_kg}, "global mass rounding"),
        "global_mass_roundoff_allowance_kg");
    result.global_energy_roundoff_allowance_j = represented(energy_allowance+
        allowance({result.global_energy_change_j, result.external_net_enthalpy_j}, "global energy rounding"),
        "global_energy_roundoff_allowance_j");
    require(std::abs(result.global_mass_residual_kg) <= result.global_mass_roundoff_allowance_kg,
            "global mass residual exceeds representational allowance");
    require(std::abs(result.global_energy_residual_j) <= result.global_energy_roundoff_allowance_j,
            "global energy residual exceeds representational allowance");
    return result;
}

MassEventResult apply_mass_events(const WaterProperties& p, const std::vector<Column>& columns,
                                 const std::vector<State>& initial, const MassEventInput& input) {
    return mass_events_impl(p, columns, initial, input, false);
}
MassEventResult apply_mass_events_pure_water(const WaterProperties& p, const std::vector<Column>& columns,
                                            const std::vector<State>& initial, const MassEventInput& input) {
    return mass_events_impl(p, columns, initial, input, true);
}

}  // namespace cryosphere_prototype
