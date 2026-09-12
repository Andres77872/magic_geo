#include "terrestrial_coupled_error.hpp"
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>

using namespace magic_geo::detail;
namespace p = phase_segment_prototype;
namespace {
int checks = 0;
void require(bool ok, const char *why) { ++checks; if (!ok) throw std::runtime_error(why); }
void out(p::Interval x) { std::cout << '[' << x.lower << ',' << x.upper << ']'; }
void out(p::Energy x) { std::cout << '[' << x.surface_enthalpy_j_m2 << ',' << x.atmospheric_energy_j_m2 << ']'; }
void out(p::StateBox x) { std::cout << '[';out(x.surface_enthalpy_j_m2);std::cout << ',';out(x.atmospheric_energy_j_m2);std::cout << ']'; }
void out(const std::vector<CanonicalMovement> &xs) {
    std::cout << '['; bool first=true;
    for(const auto &x:xs) { if(!first)std::cout << ','; first=false;
        std::cout << '[' << x.mass_kg << ',' << x.carried_enthalpy_j << ']'; }
    std::cout << ']';
}
void out(const CoupledDomainCertificate &x) {
    std::cout << "{\"accepted\":" << x.accepted << ",\"failure_code\":" << std::quoted(x.failure_code)
              << ",\"box\":";out(x.uncertainty_box);
    std::cout << ",\"surface_floor\":";out(x.surface_floor_j_m2);
    std::cout << ",\"air_floor\":";out(x.air_floor_j_m2); std::cout << '}';
}
struct Case {
    const char *id;
    explicit Case(const char *value) : id(value) {}
    p::Water water{1,1,1,1};
    p::Column column{1,1,2,0,0,0};
    double Wi=2, Wf=2;
    p::Energy initial{1,2}, final{1,2};
    double inherited=.125, maximum=8;
    std::vector<CanonicalMovement> imports, withdrawals;
    bool expected=true;
};
void run(const Case &x) {
    const auto r=certify_canonical_jump(x.water,x.column,x.Wi,x.initial,x.Wf,x.final,
        x.inherited,x.imports,x.withdrawals,x.maximum);
    std::cout << "{\"kind\":\"jump\",\"id\":" << std::quoted(x.id) << ",\"water\":["
        << x.water.freezing_temperature_k << ',' << x.water.solid_heat_capacity_j_kg_k << ','
        << x.water.liquid_heat_capacity_j_kg_k << ',' << x.water.latent_heat_j_kg << "],\"column\":["
        << x.column.area_m2 << ',' << x.column.dry_heat_capacity_j_m2_k << ','
        << x.column.atmospheric_heat_capacity_j_m2_k << ',' << x.column.atmospheric_longwave_absorptivity
        << ',' << x.column.sensible_exchange_w_m2_k << ',' << x.column.surface_shortwave_albedo
        << "],\"Wi\":" << x.Wi << ",\"Wf\":" << x.Wf << ",\"initial\":";out(x.initial);
    std::cout << ",\"final\":";out(x.final);
    std::cout << ",\"inherited\":" << x.inherited << ",\"maximum\":" << x.maximum << ",\"imports\":";out(x.imports);
    std::cout << ",\"withdrawals\":";out(x.withdrawals);
    std::cout << ",\"certificate\":{\"accepted\":" << r.accepted << ",\"failure_code\":" << std::quoted(r.failure_code)
        << ",\"detail\":" << std::quoted(r.detail) << ",\"before_domain\":";out(r.before_domain);
    std::cout << ",\"after_domain\":";out(r.after_domain);
    std::cout << ",\"q\":";out(r.withdrawal_density_kg_m2);
    std::cout << ",\"I\":";out(r.import_energy_j_m2);
    std::cout << ",\"mass_projection\":";out(r.canonical_mass_projection_kg_m2);
    std::cout << ",\"G\":";out(r.ideal_jump_j_m2);
    std::cout << ",\"state_projection\":";out(r.state_projection_j_m2);
    std::cout << ",\"export_bridge\":";out(r.export_bridge_j_m2);
    std::cout << ",\"liquid_feasible\":" << r.liquid_feasibility_proved
        << ",\"inherited\":" << r.inherited_error_j_m2 << ",\"D\":" << r.jump_defect_upper_j_m2
        << ",\"E\":" << r.final_error_j_m2 << ",\"outbox\":" << r.outbox_error_upper_j << ",\"per_outbox\":[";
    for(std::size_t i=0;i<r.per_withdrawal_error_upper_j.size();++i) {
        if(i)std::cout << ',';
        std::cout << r.per_withdrawal_error_upper_j[i];
    }
    std::cout << "]}}\n";
    require(r.accepted==x.expected,x.id);
    if(r.accepted) {
        require(r.before_domain.accepted&&r.after_domain.accepted,"domain evidence missing");
        require(r.final_error_j_m2>=x.inherited,"inherited error reset");
    }
    if(std::string(x.id)=="event_publication_one_joule") require(r.jump_defect_upper_j_m2>=1,"one joule lost");
    if(std::string(x.id)=="empty_identity") require(r.final_error_j_m2==x.inherited,"empty error changed");
}
}
int main() {
    try {
        std::cout << std::setprecision(17) << std::boolalpha;
        Case x{"empty_identity"};run(x);
        x=Case{"solid_import"};x.Wi=0;x.Wf=1;x.initial={0,2};x.final={-.5,2};x.imports={{1,-.5}};run(x);
        x=Case{"plateau_withdrawal"};x.Wf=1.5;x.final={.5,2};x.withdrawals={{.5,.5}};run(x);
        x=Case{"warm_complete_drainage"};x.Wi=1;x.Wf=0;x.initial={3,2};x.final={1,2};x.withdrawals={{1,2}};run(x);
        x=Case{"q_zero_cold"};x.Wi=x.Wf=1;x.initial=x.final={-1,2};run(x);
        x=Case{"uncertain_inventory_refusal"};x.Wi=1;x.Wf=0;x.final={0,2};x.withdrawals={{1,1}};x.expected=false;run(x);
        x=Case{"import_cannot_refeed"};x.Wi=x.Wf=0;x.initial=x.final={0,2};x.inherited=0;x.imports={{1,1}};x.withdrawals={{1,1}};x.expected=false;run(x);
        x=Case{"air_bit_change"};x.initial={1,0};x.final={1,-0.0};x.expected=false;run(x);
        x=Case{"event_publication_one_joule"};x.Wi=0;x.Wf=1;x.initial=x.final={9007199254740992.,2};x.inherited=0;x.imports={{1,1}};x.column.atmospheric_heat_capacity_j_m2_k=0;x.initial.atmospheric_energy_j_m2=x.final.atmospheric_energy_j_m2=0;run(x);
        x=Case{"projected_W_floor_refusal"};x.column.area_m2=3;x.Wi=0;x.Wf=1./3;x.initial={-1,2};x.final={-4./3,2};x.inherited=0;x.imports={{1,-1}};x.expected=false;run(x);
        x=Case{"cumulative_budget_refusal"};x.Wi=0;x.Wf=1;x.initial=x.final={9007199254740992.,2};x.inherited=0;x.imports={{1,1}};x.maximum=.5;x.expected=false;run(x);
        x=Case{"outbox_multiple_ids"};x.Wi=2;x.Wf=1;x.initial={5,2};x.final={3,2};x.withdrawals={{.25,.5},{.75,1.5}};run(x);
        x=Case{"conservative_equality_refusal"};x.column.area_m2=3;x.Wi=2;x.Wf=0;x.initial={2,2};x.final={0,2};x.inherited=0;x.withdrawals={{6,6}};x.expected=false;run(x);
        std::cout << "{\"kind\":\"summary\",\"status\":\"passed\",\"jump_cases\":13,\"checks\":" << checks << ",\"solver_calls\":0}\n";
    } catch(const std::exception &e) { std::cerr << e.what() << '\n';return 1; }
}
