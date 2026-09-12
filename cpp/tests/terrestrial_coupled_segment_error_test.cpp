#include "terrestrial_coupled_error.hpp"
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace magic_geo::detail;
namespace p = phase_segment_prototype;
namespace {
// Helper-consumed fields from the first retained radiative_sensible_dry
// segment, raw receipt SHA256 9cd19f413cfd9ff4bd8e06557068b5855233fb5f345e3cfc8cdaa8038aae5260.
// This regression replays error arithmetic only; it never invokes the solver.
p::Receipt retained() {
    p::Receipt r{};
    r.request.water = {1,1,1,1};
    r.request.column = {2,10,10,.5,1,0};
    r.request.water_mass_kg_m2 = 0;
    r.request.initial = {1,.5};
    r.request.maximum_duration_seconds = .0625;
    r.request.goal = p::Goal::within_branch;
    r.accepted = r.final_state_available = r.numerical_budget_passed = true;
    r.physical_budget_passed = r.physical_error_bounds_available = true;
    r.guard.domain_proved = r.guard.finite_horizon_tube_proved = true;
    r.guard.no_physical_hit_proved = true;
    r.physical_event_state_error_j_m2 = {-std::numeric_limits<double>::denorm_min(),
                                        0.0005377493275428027};
    r.physical_time_error_seconds = {0,0};
    r.selected_duration_seconds = .0625;
    r.final_state = {1.059200121512933,0.5032998737093851};
    return r;
}
int checks=0;
void require(bool ok,const char *why) {++checks;if(!ok)throw std::runtime_error(why);}
void run(const char *id,const p::Receipt &r,double inherited,bool expected) {
    const auto c=certify_coupled_segment(r,inherited,.02);
    std::cout << "{\"id\":" << std::quoted(id) << ",\"accepted\":" << c.accepted
        << ",\"failure_code\":" << std::quoted(c.failure_code)
        << ",\"inherited\":" << c.inherited_error_j_m2
        << ",\"local_upper\":" << c.local_same_time_error_upper_j_m2
        << ",\"time_transport\":" << c.time_transport_upper_j_m2
        << ",\"final_upper\":" << c.final_error_j_m2 << "}\n";
    require(c.accepted==expected,id);
    if(expected) {
        require(c.before_domain.accepted&&c.after_domain.accepted,"domain missing");
        require(c.local_same_time_error_upper_j_m2==r.physical_event_state_error_j_m2.upper,"upper changed");
        require(c.final_error_j_m2>=inherited+r.physical_event_state_error_j_m2.upper,"inherited error lost");
        require(c.time_transport_upper_j_m2==0,"no-hit timing changed");
    }
}
}
int main() {
    try {
        std::cout << std::setprecision(17) << std::boolalpha;
        auto r=retained();run("retained_negative_lower",r,0,true);
        run("retained_with_inherited_error",r,.01,true);
        r=retained();r.physical_event_state_error_j_m2={-2,-1};run("negative_local_upper",r,0,false);
        r=retained();r.physical_time_error_seconds={-.02,-.01};run("negative_time_upper",r,0,false);
        r=retained();r.physical_event_state_error_j_m2={1,0};run("reversed_interval",r,0,false);
        r=retained();r.accepted=false;run("native_refusal",r,0,false);
        std::cout << "{\"status\":\"passed\",\"cases\":6,\"checks\":" << checks << ",\"solver_calls\":0}\n";
    }catch(const std::exception &e) {std::cerr << e.what() << '\n';return 1;}
}
