#include "geographic_foundation_case.hpp"
#include "internal.hpp"
#include "world.hpp"
#include "../src/opencl_compute.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <type_traits>

using namespace magic_geo;
using namespace magic_geo::detail;
namespace {
int checks=0;
void require(bool ok,const char* message) {
    ++checks;
    if(!ok) throw std::runtime_error(message);
}
void write(const std::filesystem::path& path,const std::string& value) {
    std::ofstream file(path,std::ios::binary); file<<value; file.close();
    require(bool(file),"evidence write failed");
}
template<class F> void refuses(F f,const char* code) {
    try { f(); }
    catch(const TerrestrialWaterError& e) { require(e.code==code,e.what()); return; }
    throw std::runtime_error(std::string("missing refusal: ")+code);
}
void consumed(GeographicFoundation& f) {
    refuses([&]{(void)f.earth();},"foundation_consumed");
    refuses([&]{(void)f.params();},"foundation_consumed");
    refuses([&]{(void)f.enthalpy_context({});},"foundation_consumed");
    refuses([&]{(void)f.routing_graph();},"foundation_consumed");
    refuses([&]{(void)finish_legacy_generation(std::move(f),true);},"foundation_consumed");
}
void run(const std::filesystem::path& output) {
    std::filesystem::create_directories(output);
    static_assert(!std::is_copy_constructible_v<GeographicFoundation>);
    static_assert(std::is_nothrow_move_constructible_v<GeographicFoundation>);
    auto p=geographic_foundation_case();
    const auto original=p;
    ComputeOptions cpu; cpu.compute_backend=1;
    validate_compute_options(cpu); validate_params(p);
    ScopedThreadConfiguration threads(p.threads);
    ComputeSession compute(p,cpu);
    auto foundation=prepare_geographic_foundation(p);
    const auto& earth=foundation.earth();
    require(earth.cells.size()==128,"unexpected cell count");
    require(!earth.terrestrial_surface_finalized,"descendants prematurely finalized");
    require(!earth.finalized_enthalpy_planet,"late planet provenance published early");
    require(!earth.terrestrial_surface_epoch,"capture prematurely claimed an epoch");
    require(earth.terrestrial_owner_mode==TerrestrialOwnerMode::none,"owner published early");
    require(!earth.hydrologic_water_budget_history.empty(),"missing hydrology history");
    require(earth.hydrologic_water_budget_history.back().stage=="cryosphere_coupling",
            "last hydrology stabilizer did not finish");
    require(std::none_of(earth.feedback_history.begin(),earth.feedback_history.end(),
        [](const auto& step){return step.stage=="cryosphere_coupling";}),
        "deferred cryosphere feedback already published");
    const auto feedback_count=earth.feedback_history.size();
    require(earth.glacial_transport_history.size()==1,"glacial transport was not completed");
    p.name="mutated caller"; p.radius_km*=2; p.seed+=1;
    require(foundation.params().name==original.name && foundation.params().seed==original.seed &&
        foundation.params().radius_km==original.radius_km,"caller mutation changed owned parameters");
    FinalizedEnthalpyOptions options;
    options.lake_mixed_layer_depth_m=10; // Explicit qualification choice, not a default policy.
    constexpr std::uint64_t revision=41;
    const auto context=foundation.enthalpy_context(options,revision);
    const auto routing=foundation.routing_graph(revision);
    require(context.surface().surface_revision()==revision && routing.revision()==revision,"capture revision mismatch");
    require(context.matches(earth.cells,original) && routing.matches(earth.cells),"capture source mismatch");
    require(context.properties().columns.size()==128 && routing.nodes().size()==128,"incomplete capture");
    const auto context_json=finalized_enthalpy_context_json(context);
    const auto routing_json=seasonal_liquid_routing_graph_json(routing);
    write(output/"context.json",context_json);
    write(output/"routing.json",routing_json);
    auto invalid=options; invalid.lake_mixed_layer_depth_m=0;
    refuses([&]{(void)foundation.enthalpy_context(invalid,revision);},"invalid_finalized_context");
    require(!foundation.earth().terrestrial_surface_finalized &&
        context.matches(foundation.earth().cells,foundation.params()) &&
        routing.matches(foundation.earth().cells),"failed capture mutated foundation");
    auto moved=std::move(foundation);
    consumed(foundation);
    auto world=finish_legacy_generation(std::move(moved),true);
    consumed(moved);
    require(world.earth.terrestrial_surface_finalized && world.earth.finalized_enthalpy_planet,
        "finished world lacks late readiness");
    require(same_finalized_enthalpy_planet_inputs(*world.earth.finalized_enthalpy_planet,
        finalized_enthalpy_planet_inputs(original)),"finishing used mutated caller parameters");
    require(world.earth.feedback_history.size()==feedback_count+1 &&
        world.earth.feedback_history.back().stage=="cryosphere_coupling","deferred feedback not completed once");
    require(!world.calibration_checks.empty(),"calibration descendant missing");
    require(!world.natural.stratigraphic_columns.empty(),"natural descendant missing");
    require(world.society.availability.enabled,"society completion branch missing");
    require(context.matches(world.earth.cells,original),"descendants changed captured context operands");
    require(routing.matches(world.earth.cells),"descendants changed routing operands");
    require(finalized_enthalpy_context_json(context)==context_json &&
        seasonal_liquid_routing_graph_json(routing)==routing_json,"snapshot changed after consumption");
    write(output/"world.json",serialize_world(original,world));
    std::cout<<"{\"checks\":"<<checks<<",\"generation_calls\":1,\"layered_thermal_calls\":0,"
        "\"cell_count\":"<<world.earth.cells.size()<<",\"lake_count\":"<<context.lakes().size()
        <<",\"stratigraphic_columns\":"<<world.natural.stratigraphic_columns.size()
        <<",\"settlements\":"<<world.society.settlements.size()<<"}\n";
}
}
int main(int argc,char** argv) {
    try {
        if(argc==2 && std::string(argv[1])=="--inventory") {
            std::cout<<"{\"case\":\"geographic_foundation_handoff\",\"seed\":424271,"
                "\"cell_count\":128,\"plate_count\":8,\"erosion_iterations\":0,\"threads\":1,"
                "\"float_precision\":8,\"lake_mixed_layer_depth_m\":10,\"surface_revision\":41,"
                "\"include_society\":true,\"generation_calls\":0,\"layered_thermal_calls\":0}\n";
            return 0;
        }
        if(argc!=3 || std::string(argv[1])!="--run")
            throw std::runtime_error("usage: geographic_foundation_test --inventory | --run OUTPUT_DIRECTORY");
        run(argv[2]); return 0;
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
