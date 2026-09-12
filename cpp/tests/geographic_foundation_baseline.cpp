// Link this driver only against the retained pre-handoff native library.
#include "geographic_foundation_case.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>

int main(int argc,char** argv) {
    try {
        if(argc!=2) throw std::runtime_error("usage: baseline OUTPUT_JSON");
        const auto p=geographic_foundation_case();
        const auto json=magic_geo::generate_world_json(p);
        std::ofstream file(argv[1],std::ios::binary);
        file<<json; file.close();
        if(!file) throw std::runtime_error("baseline write failed");
        std::cout<<"{\"generation_calls\":1,\"bytes\":"<<json.size()<<"}\n";
        return 0;
    } catch(const std::exception& e) { std::cerr<<e.what()<<'\n'; return 1; }
}
