#include "layered_ice_forcing_history.hpp"

#include <bit>
#include <cstdint>
#include <iostream>
#include <set>
#include <stdexcept>
#include <vector>

using namespace magic_geo::detail;
namespace {
std::size_t checks=0;
void require(bool ok,const char* message) { ++checks; if(!ok) throw std::runtime_error(message); }
template<class Error,class F> void refuses(F action) {
    try { action(); } catch(const Error&) { ++checks; return; }
    throw std::runtime_error("missing container refusal");
}
LayeredIceOwnerForcing value(std::size_t window,std::size_t cells=128) {
    LayeredIceOwnerForcing f;
    f.id="storage_window_"+std::to_string(window);
    f.begin_seconds=static_cast<double>(window);
    f.end_seconds=static_cast<double>(window+1);
    for(std::size_t cell=0;cell<cells;++cell)
        f.absorbed_shortwave_w_m2.push_back(static_cast<double>(window*256+cell)/256);
    return f;
}
void run() {
    // Complete retained-count scale, with literal dyadic data. This constructs
    // no solar calendar, owner, graph, world or thermal trajectory.
    std::vector<LayeredIceForcingHistory> prefixes(1);
    for(std::size_t k=0;k<1080;++k) prefixes.push_back(prefixes.back().appended(value(k)));
    const auto& full=prefixes.back();
    std::set<const LayeredIceOwnerForcing*> entries;
    std::set<const double*> vectors;
    for(std::size_t k=0;k<prefixes.size();++k) {
        const auto& prefix=prefixes[k];
        require(prefix.size()==k && prefix.stored_values()==k*128,"prefix shape changed");
        require(full.has_prefix(prefix),"shared immutable prefix lost");
        std::size_t j=0;
        for(const auto& f:prefix) {
            require(&f==&full[j],"historical forcing entry duplicated");
            entries.insert(&f);vectors.insert(f.absorbed_shortwave_w_m2.data());++j;
        }
        require(j==k,"iterator length mismatch");
    }
    require(entries.size()==1080 && vectors.size()==1080,"unique forcing allocation count");
    for(std::size_t k=0;k<1080;++k) {
        const auto& f=full[k];
        require(f.id=="storage_window_"+std::to_string(k) && f.begin_seconds==k && f.end_seconds==k+1,
                "forcing identity or order changed");
        for(std::size_t cell=0;cell<128;++cell)
            require(f.absorbed_shortwave_w_m2[cell]==static_cast<double>(k*256+cell)/256,
                    "forcing payload changed");
    }
    auto supplied=value(500);auto branch=prefixes[500].appended(supplied);
    supplied.id="changed caller";supplied.absorbed_shortwave_w_m2[0]=-99;
    require(branch[500].id=="storage_window_500" && branch[500].absorbed_shortwave_w_m2[0]==500,
            "caller mutation changed immutable value");
    require(branch.has_prefix(prefixes[500]) && !branch.has_prefix(prefixes[501]) &&
            !full.has_prefix(branch),"distinct equal-value append forged prefix identity");
    auto iterator=branch.begin();auto moved=std::move(branch);
    require(branch.empty() && branch.stored_values()==0,"moved-from container invalid");
    require(iterator->id=="storage_window_0","iterator did not retain its immutable prefix");
    auto reused=branch.appended(value(7));require(reused.size()==1 && reused[0].id=="storage_window_7",
            "moved-from container could not be reused");
    LayeredIceForcingHistory assigned;assigned=std::move(moved);
    require(moved.empty() && assigned.has_prefix(prefixes[500]),"move assignment lost ownership");
    auto first=assigned.begin();auto post=first++;
    require(post->id=="storage_window_0" && first->id=="storage_window_1","forward iterator increment");
    refuses<std::out_of_range>([&]{(void)full[1080];});
    refuses<std::out_of_range>([&]{(void)*full.end();});

    auto capped=full;
    for(std::size_t i=capped.size();i<LayeredIceForcingHistory::maximum_records;++i)
        capped=capped.appended(value(i,0));
    refuses<std::length_error>([&]{(void)capped.appended(value(2048,0));});
    require(capped.size()==2048 && capped.has_prefix(full),"record-cap refusal changed source");
    LayeredIceOwnerForcing maximum;
    maximum.id="full_value_capacity";
    maximum.absorbed_shortwave_w_m2.resize(LayeredIceForcingHistory::maximum_values,0);
    auto large=LayeredIceForcingHistory().appended(std::move(maximum));
    require(large.stored_values()==2097152 && large.size()==1,"full value capacity unavailable");
    refuses<std::length_error>([&]{(void)large.appended(value(1,1));});
    require(large.size()==1 && large.stored_values()==2097152,"value-cap refusal changed source");
    LayeredIceOwnerForcing opaque;
    opaque.id="opaque_container_values";
    opaque.absorbed_shortwave_w_m2={-0.0,std::bit_cast<double>(UINT64_C(0x7ff8000000000019))};
    auto raw=LayeredIceForcingHistory().appended(opaque);
    require(std::bit_cast<std::uint64_t>(raw[0].absorbed_shortwave_w_m2[0])==UINT64_C(0x8000000000000000) &&
            std::bit_cast<std::uint64_t>(raw[0].absorbed_shortwave_w_m2[1])==UINT64_C(0x7ff8000000000019),
            "data container silently changed raw values");
    // Physical forcing validation remains the owner's responsibility.
    std::cout<<"{\"accepted\":true,\"checks\":"<<checks
        <<",\"prefixes\":1081,\"windows\":1080,\"cells\":128,\"unique_value_vectors\":"<<vectors.size()
        <<",\"unique_main_vector_payload_bytes\":1105920,\"old_two_snapshot_value_occurrences\":149299200,"
        "\"all_container_metadata_or_peak_RSS_bounded\":false,\"thermal_calls\":0,\"owner_calls\":0,"
        "\"calendar_calls\":0,\"world_calls\":0}\n";
}
}
int main(int argc,char** argv) {
    try {
        if(argc==2 && std::string(argv[1])=="--inventory") {
            std::cout<<"{\"scope\":\"immutable_forcing_storage_data_only\",\"windows\":1080,\"cells\":128,"
                "\"value_formula\":\"(window*256+cell)/256\",\"prefixes_retained\":1081,"
                "\"record_cap\":2048,\"value_cap\":2097152,\"thermal_calls\":0,"
                "\"owner_calls\":0,\"calendar_calls\":0,\"world_calls\":0}\n";return 0;
        }
        if(argc!=2 || std::string(argv[1])!="--run") throw std::runtime_error("use --inventory or --run");
        run();return 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
