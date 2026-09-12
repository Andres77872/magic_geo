#include "enthalpy_mesh_proof_codec.hpp"

#include <algorithm>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>

using namespace magic_geo::detail;
namespace fs=std::filesystem;
namespace {
int checks=0,failures=0;
void check(bool ok,const std::string& name) {
    ++checks;if(!ok)++failures;
    std::cout<<"{\"kind\":\"check\",\"name\":"<<std::quoted(name)<<",\"passed\":"<<(ok?"true":"false")<<"}\n";
}
std::vector<std::byte> read_file(const fs::path& path) {
    const auto n=fs::file_size(path);
    if(n>67108864)throw std::runtime_error("fixture file cap");
    std::vector<std::byte> out(n);std::ifstream in(path,std::ios::binary);
    in.read(reinterpret_cast<char*>(out.data()),static_cast<std::streamsize>(out.size()));
    if(!in)throw std::runtime_error("fixture read failed");
    return out;
}
std::string as_string(const std::vector<std::byte>& bytes) {
    return {reinterpret_cast<const char*>(bytes.data()),bytes.size()};
}
void write_file(const fs::path& path,const std::vector<std::byte>& bytes) {
    if(fs::exists(path))throw std::runtime_error("refusing to replace qualification output");
    std::ofstream out(path,std::ios::binary);out.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());
    if(!out)throw std::runtime_error("qualification output failed");
}
EnthalpyMeshProofCodecLimits limits() {
    EnthalpyMeshProofCodecLimits l;l.shape.max_nodes=128;l.shape.max_edges=256;
    l.shape.max_outer_leaves=32;l.shape.max_backward_euler_leaves_per_stage=32;
    l.shape.max_sweeps_per_stage=129;l.shape.max_polynomial_coefficients=9;
    l.max_frame_bytes=67108864;l.max_decoded_payload_bytes=67108864;l.max_legacy_json_bytes=67108864;
    return l;
}
EnthalpyMeshSdirk2Receipt decode(const std::vector<std::byte>& bytes,const EnthalpyMeshProofCodecLimits& l,
                               std::size_t& largest) {
    std::size_t pos=0;
    auto value=decode_enthalpy_mesh_proof([&](std::span<std::byte> block) {
        largest=std::max(largest,block.size());
        if(block.size()>bytes.size()-pos)throw std::runtime_error("short fixture callback");
        std::copy_n(bytes.data()+pos,block.size(),block.data());pos+=block.size();
    },bytes.size(),l);
    if(pos!=bytes.size())throw std::runtime_error("decoder did not consume declared extent");
    return value;
}
void promote(EnthalpyMeshSdirk2Receipt& r) {
    r.tableau_bridges_available=r.endpoint_error_available=true;
    for(auto& leaf:r.leaves)leaf.complete=true;
    for(auto* slot:{&r.first_stage,&r.second_stage})if(*slot) {
        auto& s=**slot;s.physical_domain_proved=s.candidate_available=s.stage_error_available=s.endpoint_error_available=true;
        for(auto& leaf:s.leaves)leaf.complete=true;
    }
}
template<class F> void refuses(const std::string& name,F f) {
    try {f();check(false,name);}catch(const EnthalpyMeshProofCodecError& e) {check(!e.code.empty(),name);}
}
void controls(const fs::path& inputs,const fs::path& outputs) {
    if(!fs::create_directory(outputs))throw std::runtime_error("output directory already exists");
    std::vector<fs::path> paths;
    for(const auto& e:fs::directory_iterator(inputs))if(e.path().extension()==".bin")paths.push_back(e.path());
    std::sort(paths.begin(),paths.end());check(!paths.empty(),"fixed_fixtures_present");
    const auto l=limits();const auto maximum=enthalpy_mesh_proof_codec_max_size(l.shape);
    std::size_t largest_source=0,largest_sink=0;std::uint64_t total=0;int originals=0;
    for(const auto& path:paths) {
        const auto name=path.stem().string();const auto bytes=read_file(path);
        auto r=decode(bytes,l,largest_source);const auto size=enthalpy_mesh_proof_codec_size(r,l);
        check(size.frame_bytes==bytes.size(),name+"_exact_wire_size");
        check(size.frame_bytes<=maximum.frame_bytes && size.decoded_payload_bytes<=maximum.decoded_payload_bytes &&
              size.total_vector_elements<=maximum.total_vector_elements && size.total_string_bytes<=maximum.total_string_bytes,
              name+"_complete_shape_envelope");
        if(name=="manufactured_maximum")check(size.frame_bytes==maximum.frame_bytes &&
            size.decoded_payload_bytes==maximum.decoded_payload_bytes && size.total_vector_elements==maximum.total_vector_elements &&
            size.total_string_bytes==maximum.total_string_bytes,"all_independent_shape_caps_reached");
        std::vector<std::byte> encoded;
        encode_enthalpy_mesh_proof(r,[&](std::span<const std::byte> block) {
            largest_sink=std::max(largest_sink,block.size());encoded.insert(encoded.end(),block.begin(),block.end());
        },l);
        check(encoded==bytes,name+"_all_structured_bits_roundtrip");write_file(outputs/(name+".roundtrip.bin"),encoded);
        std::vector<std::byte> json;
        stream_enthalpy_mesh_proof_legacy_json(r,[&](std::span<const std::byte> block) {
            largest_sink=std::max(largest_sink,block.size());json.insert(json.end(),block.begin(),block.end());
        },l);
        check(json.size()==enthalpy_mesh_proof_legacy_json_size(r,l),name+"_exact_streamed_json_size");
        check(as_string(json)==enthalpy_mesh_sdirk2_receipt_json(r),name+"_current_legacy_spelling_unchanged");
        if(fs::exists(inputs/(name+".original.json"))) {
            ++originals;check(json==read_file(inputs/(name+".original.json")),name+"_retained_original_bytes_unchanged");
        }
        write_file(outputs/(name+".legacy.json"),json);
        std::size_t cursor=0;std::vector<std::byte> expanded;
        expand_enthalpy_mesh_proof_legacy_json([&](std::span<std::byte> block) {
            if(block.size()>bytes.size()-cursor)throw std::runtime_error("short expansion callback");
            std::copy_n(bytes.data()+cursor,block.size(),block.data());cursor+=block.size();
        },bytes.size(),[&](std::span<const std::byte> block) {expanded.insert(expanded.end(),block.begin(),block.end());},l);
        check(expanded==json && cursor==bytes.size(),name+"_bounded_frame_expansion");
        promote(r);std::vector<std::byte> promoted;
        stream_enthalpy_mesh_proof_legacy_json(r,[&](std::span<const std::byte> block) {promoted.insert(promoted.end(),block.begin(),block.end());},l);
        write_file(outputs/(name+".promoted.json"),promoted);
        total+=size.frame_bytes;
        std::cout<<"{\"kind\":\"fixture\",\"name\":"<<std::quoted(name)<<",\"frame_bytes\":"<<size.frame_bytes
            <<",\"decoded_payload_bytes\":"<<size.decoded_payload_bytes<<",\"vector_elements\":"<<size.total_vector_elements
            <<",\"string_bytes\":"<<size.total_string_bytes<<",\"legacy_json_bytes\":"<<json.size()<<"}\n";
    }
    check(largest_source<=65536 && largest_sink<=65536,"bounded_codec_callback_spans");
    auto bytes=read_file(inputs/"manufactured_complete.bin");std::size_t ignored=0;auto full=decode(bytes,l,ignored);
    for(const auto& mode:{"magic","version","kind","boolean","truncated","short_body","trailing","string_count"}) {
        auto bad=bytes;
        if(std::string(mode)=="magic")bad[0]^=std::byte{1};
        if(std::string(mode)=="version")bad[8]^=std::byte{1};
        if(std::string(mode)=="kind")bad[12]^=std::byte{1};
        if(std::string(mode)=="boolean")bad[24]=std::byte{2};
        if(std::string(mode)=="truncated")bad.pop_back();
        if(std::string(mode)=="short_body") {
            bad.pop_back();const auto n=bad.size()-24;
            for(int j=0;j<8;++j)bad[16+j]=std::byte((n>>(8*j))&255);
        }
        if(std::string(mode)=="trailing") {
            bad.push_back(std::byte{0});const auto n=bad.size()-24;
            for(int j=0;j<8;++j)bad[16+j]=std::byte((n>>(8*j))&255);
        }
        if(std::string(mode)=="string_count")for(int j=25;j<29;++j)bad[j]=std::byte{255};
        refuses(std::string("malformed_")+mode,[&]{(void)decode(bad,l,ignored);});
    }
    for(const auto& mode:{"frame","decoded","elements","nodes"}) {
        auto small=l;
        if(std::string(mode)=="frame")small.max_frame_bytes=bytes.size()-1;
        if(std::string(mode)=="decoded")small.max_decoded_payload_bytes=1;
        if(std::string(mode)=="elements")small.max_total_vector_elements=0;
        if(std::string(mode)=="nodes")small.shape.max_nodes=1;
        refuses(std::string("decode_cap_")+mode,[&]{(void)decode(bytes,small,ignored);});
    }
    std::size_t callbacks=0;auto short_frame=l;short_frame.max_frame_bytes=bytes.size()-1;
    refuses("encode_cap_before_sink",[&]{encode_enthalpy_mesh_proof(full,[&](auto){++callbacks;},short_frame);});
    check(callbacks==0,"encode_cap_has_no_partial_sink");
    auto short_json=l;short_json.max_legacy_json_bytes=1;
    refuses("json_cap_before_sink",[&]{stream_enthalpy_mesh_proof_legacy_json(full,[&](auto){++callbacks;},short_json);});
    check(callbacks==0,"json_cap_has_no_partial_sink");
    auto huge=l.shape;huge.max_nodes=huge.max_edges=huge.max_outer_leaves=huge.max_backward_euler_leaves_per_stage=
        huge.max_polynomial_coefficients=huge.max_sweeps_per_stage=std::numeric_limits<std::uint32_t>::max();
    refuses("shape_envelope_checked_overflow",[&]{(void)enthalpy_mesh_proof_codec_max_size(huge);});
    std::cout<<"{\"kind\":\"summary\",\"checks\":"<<checks<<",\"failures\":"<<failures<<",\"fixtures\":"<<paths.size()
        <<",\"retained_originals\":"<<originals<<",\"total_frame_bytes\":"<<total<<",\"largest_source_span\":"<<largest_source
        <<",\"largest_sink_span\":"<<largest_sink<<",\"max_shape_frame_bytes\":"<<maximum.frame_bytes
        <<",\"native_physical_calls\":0,\"historical_numerical_reruns\":0}\n";
}
}
int main(int argc,char** argv) {
    try {
        if(argc!=3)return 2;
        controls(argv[1],argv[2]);return failures?1:0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
}
