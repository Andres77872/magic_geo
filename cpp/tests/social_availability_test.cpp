#include "internal.hpp"
#include "social_availability.hpp"
#include <fstream>
#include <iostream>
#include <tuple>
using namespace magic_geo;
using namespace magic_geo::detail;
namespace {
int checks = 0;
void check(bool value, const char* message) { ++checks; if (!value) throw std::runtime_error(message); }
struct Fixture {
    Params params;
    std::vector<Cell> cells;
    std::vector<Settlement> settlements;
    std::vector<PoliticalRegion> regions;
    std::vector<BorderSegment> borders;
    std::vector<Route> routes;
    std::vector<TradeFlow> trade;
    CulturalLayers culture;
    HistoricalLayers history;
    std::vector<PopulationRegion> population;
    std::vector<ConflictRecord> conflict;
    std::vector<DynastyRecord> dynasty;
    std::vector<TerritorialSnapshot> snapshots;
    SocialAvailability availability;
};
Fixture fixture(bool native = true) {
    Fixture f;
    f.params.float_precision = 8;
    f.params.radius_km = 6371;
    f.params.temperature_model = native ? ClimateTemperatureModel::prescribed_seasonal : ClimateTemperatureModel::legacy_empirical;
    f.availability.enabled = native;
    f.cells.resize(6); f.settlements.resize(2); f.regions.resize(2);
    for (int i=0; i<6; ++i) {
        auto& c=f.cells[i]; c.id=i; c.p={std::cos(i),std::sin(i),0}; c.lon=i; c.lat=0;
        c.area_km2=100; c.temperature_c=17; c.precipitation_mm_y=900; c.runoff_mm_y=500;
        c.temperature_monthly_c.fill(17); c.precipitation_monthly_mm.fill(75);
        c.settlement_climate_supported=true; c.settlement_score=.5; c.fertility=.6;
        c.elevation_m=100; c.crust_type=1; c.political_region_id=i/3;
        c.neighbors={(i+5)%6,(i+1)%6};
    }
    for (int i=0;i<2;++i) {
        auto& s=f.settlements[i];s.id=i;s.cell_id=i*3;s.region_id=i;s.score=.5;
        auto& p=f.regions[i];p.id=i;p.capital_settlement_id=i;p.settlement_count=1;p.settlement_ids={i};p.area_km2=300;p.mean_settlement_score=.5;
    }
    BorderSegment b;b.id=0;b.region_a=0;b.region_b=1;b.cell_a=2;b.cell_b=3;b.length_km=5;b.barrier_score=.3;f.borders={b};
    return f;
}
void run(Fixture& f) {
    auto* a=&f.availability;
    f.culture=generate_cultural_layers(f.params,f.cells,f.settlements,f.regions,f.borders,f.trade,a);
    f.history=generate_historical_layers(f.cells,f.settlements,f.regions,f.borders,f.trade,f.culture,a);
    f.population=generate_population_regions(f.cells,f.regions,f.culture,a);
    f.conflict=generate_conflicts(f.cells,f.regions,f.borders,f.trade,f.culture,f.population,a);
    f.dynasty=generate_dynasties(f.regions,f.culture,f.history,f.population,f.conflict,a);
    f.snapshots=generate_territorial_snapshots(f.params,f.cells,f.regions,f.settlements,f.culture,f.history,f.population,f.conflict,a);
}
Fixture selected_fixture(bool mixed, bool derive_environment = false) {
    Fixture f=fixture();f.cells.resize(64);
    for(int i=0;i<64;++i){
        auto& c=f.cells[i];c=f.cells[0];c.id=i;c.political_region_id=-1;
        const double z=1.0-2.0*(i+.5)/64.0;
        c.lon=std::remainder(i*2.399963229728653,2*PI);c.lat=std::asin(z);
        c.p={std::sqrt(1-z*z)*std::cos(c.lon),std::sqrt(1-z*z)*std::sin(c.lon),z};
        c.neighbors={(i+63)%64,(i+1)%64};c.settlement_score=.6;
    }
    if(mixed){f.cells[1].temperature_c=-18;f.cells[1].temperature_monthly_c.fill(-18);f.cells[1].settlement_climate_supported=false;f.cells[1].settlement_score=0;}
    if(derive_environment){
        for(auto& c:f.cells){c.is_river=true;c.lithology=5;c.sediment_thickness_m=1.0;}
        derive_soils_biomes_resources(f.params,f.cells);
        derive_landforms(f.cells);
        finalize_settlement_climate_applicability(f.params,f.cells);
    }
    f.settlements=generate_settlements(f.params,f.cells);
    f.routes=generate_routes(f.params,f.cells,f.settlements);
    f.regions=generate_political_regions(f.params,f.cells,f.settlements,f.routes);
    f.borders=generate_border_segments(f.params,f.cells);
    f.trade=generate_trade_flows(f.cells,f.settlements,f.routes);
    run(f);return f;
}
std::string output(const Fixture& f, bool native) {
    const std::string summary = summary_json(f.params,f.cells,{},{},{},{},{},{},f.regions,f.borders,f.trade,f.culture,f.history,f.population,f.conflict,f.dynasty,f.snapshots,{},f.settlements,f.routes,{},{},{},{},{},native ? &f.availability : nullptr);
    return "{\"summary\":"+summary+",\"planet_parameters\":{\"radius_km\":"+roundtrip_num(f.params.radius_km)+"},\"borders\":"+borders_json(f.borders,8)+",\"trade_flows\":"+trade_flows_json(f.trade,8)+",\"routes\":"+routes_json(f.routes,8)+",\"native_social_availability_model\":"+native_social_model_json()+
        ",\"native_social_availability\":"+native_social_data_json(f.availability)+
        ",\"cells\":"+cells_json(f.cells,8, f.params.temperature_model)+
        ",\"settlements\":"+settlements_json(f.cells,f.settlements,8)+
        ",\"political_regions\":"+political_regions_json(f.regions,8)+
        ",\"cultures\":"+cultures_json(f.culture.cultures,8,native)+
        ",\"language_regions\":"+language_regions_json(f.culture.language_regions,8)+
        ",\"ruins\":"+ruins_json(f.culture.ruins,8)+
        ",\"sacred_areas\":"+sacred_areas_json(f.culture.sacred_areas,8)+
        ",\"historical_eras\":"+historical_eras_json(f.history.eras,8,native)+
        ",\"historical_events\":"+historical_events_json(f.history.events,8,native)+
        ",\"population_regions\":"+population_regions_json(f.population,8,native)+
        ",\"conflicts\":"+conflicts_json(f.conflict,8)+
        ",\"dynasties\":"+dynasties_json(f.dynasty,8)+
        ",\"territorial_snapshots\":"+territorial_snapshots_json(f.snapshots,8,native)+"}";
}
void tests(const char* path) {
    auto healthy=fixture();run(healthy);
    auto legacy=fixture(false);run(legacy);
    check(healthy.availability.ruin_inference_available && healthy.availability.conflict_inference_available,"healthy rank coverage");
    check(cultures_json(healthy.culture.cultures,8)==cultures_json(legacy.culture.cultures,8),"complete culture legacy parity");
    check(language_regions_json(healthy.culture.language_regions,8)==language_regions_json(legacy.culture.language_regions,8),"language legacy parity");
    check(population_regions_json(healthy.population,8)==population_regions_json(legacy.population,8),"complete population legacy parity");
    check(historical_events_json(healthy.history.events,8)==historical_events_json(legacy.history.events,8),"complete history legacy parity");
    check(conflicts_json(healthy.conflict,8)==conflicts_json(legacy.conflict,8),"complete conflict legacy parity");
    check(dynasties_json(healthy.dynasty,8)==dynasties_json(legacy.dynasty,8),"complete dynasty legacy parity");
    check(territorial_snapshots_json(healthy.snapshots,8)==territorial_snapshots_json(legacy.snapshots,8),"complete snapshots legacy parity");
    check(population_regions_json(legacy.population,8).find("_available")==std::string::npos,"legacy keys unchanged");
    auto mixed=fixture();mixed.cells[1].temperature_c=-18;mixed.cells[1].settlement_climate_supported=false;mixed.cells[1].settlement_score=0;run(mixed);
    const auto& p=mixed.population[0];
    check(p.territory_cell_count==3 && p.territory_area_km2==300,"physical denominator");
    check(p.site_input_applicable_cell_count==3 && p.site_input_supported_cell_count==2 && !p.site_input_complete,"mixed exact input coverage");
    check(!p.capacity_estimate_available && !p.population_estimate_available && p.physical_means_available,"dependent capacity unavailable independently physical available");
    check(p.agricultural_capacity_index>0 && p.water_security_index>0 && p.migration_balance_available,"independent physical response retained");
    check(!mixed.availability.ruin_inference_available && mixed.culture.ruins.empty(),"global ruin refusal");
    check(mixed.availability.ruin_candidate_cell_count==4 && mixed.availability.ruin_supported_candidate_cell_count==3 && mixed.availability.ruin_unavailable_cell_ids==std::vector<int>{1},"ruin candidate scope");
    check(mixed.population[1].capacity_estimate_available && !mixed.population[1].population_estimate_available,"complete other territory capacity but globally affected culture continuity");
    check(!mixed.availability.conflict_inference_available && mixed.availability.conflict_candidate_pair_count==1 && mixed.availability.conflict_supported_pair_count==0 && mixed.conflict.empty(),"global conflict refuses incomplete pair");
    check(mixed.dynasty.empty() && !mixed.availability.dynasty_inference_available,"no dynasty fallback");
    check(mixed.snapshots.size()==4 && mixed.snapshots[0].regions.size()==2 && mixed.snapshots[0].regions[0].base_area_km2==300 && !mixed.snapshots[0].geometry_estimate_available,"snapshot physical geometry retained");
    check(population_regions_json(mixed.population,8,true).find("\"carrying_capacity\":null")!=std::string::npos,"null numerical publication");
    check(!mixed.history.eras[0].event_count_available && mixed.history.eras[0].migration_event_count_available,"era independent family count");
    bool migration=false;for(const auto& e:mixed.history.events) if(e.type==2){migration=true;check(!e.continuity_estimate_available,"migration continuity unavailable");}
    check(migration,"independent migration retained");
    check(language_regions_json(mixed.culture.language_regions,8)==language_regions_json(healthy.culture.language_regions,8),"language unaffected by missing site input");
    auto repeated=fixture();repeated.availability=mixed.availability;run(repeated);check(repeated.availability.territorial_snapshot_inference_available,"fresh stage result resets previous unavailable coverage");
    auto lake=fixture();lake.cells[1].is_lake=true;lake.cells[1].settlement_score=0;lake.cells[1].temperature_c=-30;lake.cells[1].settlement_climate_supported=false;run(lake);
    check(lake.population[0].site_input_complete && lake.population[0].site_strength_available && lake.population[0].structural_zero_site_cell_count==1 && lake.population[0].territory_area_km2==300,"lake known structural zero");
    check(lake.population[0].site_strength_index==1.0/3.0,"lake stays physical denominator");
    auto zero=fixture();zero.cells[1].settlement_score=0;run(zero);check(zero.population[0].site_input_complete && zero.population[0].population_estimate_available,"supported score zero available");
    auto unassigned=fixture();unassigned.cells[1].political_region_id=-1;unassigned.cells[1].temperature_c=-30;unassigned.cells[1].settlement_climate_supported=false;unassigned.cells[1].settlement_score=0;run(unassigned);check(unassigned.availability.ruin_inference_available && unassigned.population[0].population_estimate_available,"unassigned unsupported does not blanket mask");
    auto noarea=fixture();for(int i=0;i<3;++i)noarea.cells[i].area_km2=0;run(noarea);check(noarea.population[0].site_input_complete && !noarea.population[0].site_strength_available && !noarea.population[0].physical_means_available && noarea.population[0].estimate_scope_status==2,"vacuous coverage no defined mean");
    auto zeroarea=fixture();zeroarea.cells[1].area_km2=0;zeroarea.cells[1].temperature_c=-30;zeroarea.cells[1].settlement_climate_supported=false;zeroarea.cells[1].settlement_score=0;run(zeroarea);check(zeroarea.population[0].site_input_complete && !zeroarea.availability.ruin_inference_available,"unweighted ruin zeroarea input consumed");
    auto emptycandidate=fixture();emptycandidate.cells[4].is_water=true;emptycandidate.cells[4].settlement_score=0;emptycandidate.cells[5].is_water=true;emptycandidate.cells[5].settlement_score=0;emptycandidate.cells[1].temperature_c=-30;emptycandidate.cells[1].settlement_climate_supported=false;emptycandidate.cells[1].settlement_score=0;emptycandidate.borders.clear();run(emptycandidate);check(!emptycandidate.culture.cultures[0].continuity_estimate_available && emptycandidate.culture.cultures[1].continuity_estimate_available && emptycandidate.culture.cultures[1].ruin_count==0,"no candidate culture knows zero");check(emptycandidate.population[1].population_estimate_available && !emptycandidate.dynasty.empty() && !emptycandidate.availability.dynasty_inference_available,"per region dynasty partial coverage");
    auto invalid=fixture();invalid.cells[1].settlement_climate_supported=false;bool rejected=false;try{run(invalid);}catch(const std::runtime_error&){rejected=true;}check(rejected,"contradictory source rejected");
    for(int kind=0;kind<4;++kind){
        auto bad=fixture();
        if(kind==0)bad.cells[1].fertility=std::numeric_limits<double>::quiet_NaN();
        if(kind==1)bad.cells[1].area_km2=-1;
        if(kind==2)bad.cells[1].neighbors={99};
        if(kind==3){bad.cells[1].is_lake=true;bad.cells[1].settlement_score=.5;}
        bool rejected_bad=false;try{run(bad);}catch(const std::runtime_error&){rejected_bad=true;}
        check(rejected_bad,"malformed native physical source rejected");
    }
    auto oldhot=fixture(false);oldhot.cells[1].temperature_c=-30;oldhot.cells[1].settlement_climate_supported=false;oldhot.cells[1].settlement_score=.4;run(oldhot);check(oldhot.population[0].population_estimate_available,"legacy source semantics unchanged");
    auto selected=selected_fixture(false);auto selected_mixed=selected_fixture(true);
    check(!selected.settlements.empty() && !selected.regions.empty(),"actual selection fixture positive");
    check(!selected_mixed.availability.ruin_inference_available,"actual selection mixed source consumed");
    auto derived=selected_fixture(false,true);auto derived_mixed=selected_fixture(true,true);
    check(!derived.settlements.empty() && derived.availability.ruin_inference_available,"derived-environment healthy fixture positive");
    check(!derived_mixed.settlements.empty() && !derived_mixed.availability.ruin_inference_available,"derived-environment mixed fixture positive");
    std::ofstream out(path);if(!out)throw std::runtime_error("fixture output unavailable");
    out << "{\"scope\":\"native social stage unit fixtures; no world or climate generation\",\"healthy\":" << output(healthy,true) << ",\"mixed\":" << output(mixed,true) << ",\"lake\":" << output(lake,true) << ",\"noarea\":" << output(noarea,true) << ",\"unassigned\":" << output(unassigned,true) << ",\"empty_candidate_culture\":" << output(emptycandidate,true) << ",\"selection_stage_healthy\":" << output(selected,true) << ",\"selection_stage_mixed\":" << output(selected_mixed,true) << ",\"environment_stage_healthy\":" << output(derived,true) << ",\"environment_stage_mixed\":" << output(derived_mixed,true) << "}\n";
}
}
int main(int argc,char**argv){try{if(argc!=2)throw std::runtime_error("output required");tests(argv[1]);std::cout<<checks<<" native social checks passed\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
