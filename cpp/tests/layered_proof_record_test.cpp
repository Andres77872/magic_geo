#include "engine/layered_proof_record.hpp"

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <span>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>
#ifdef __linux__
#include <fcntl.h>
#include <unistd.h>
#endif

// Data-only integration: opaque metadata is never treated as an owner schema.
// Decode the pinned prior manufactured fixture once. No kernel, owner,
// metadata writer, graph builder, physical solver or world generator is called.
using namespace magic_geo::detail;
namespace {
using Bytes=std::vector<std::byte>;
constexpr std::uint64_t fixture_bytes=8055;
constexpr const char* fixture_sha="de150708126afe07ab82c33efd33e22b78f24e7ace11e359ea19363578b34766";
constexpr std::uint64_t normal_payload=16384;
enum class Route { seed,thermal,material,record_cap,metadata_cap,thermal_cap,store_cap,
    short_source,long_source,throw_source,swallow_source,nonfresh,missing_source,
    magic,version,kind,thermal_offset,metadata_offset,length,reserved,metadata_zero,
    seed_thermal,short_thermal,bad_codec,short_codec,corrupt_payload };
struct Case { const char* name; Route route; const char* family; const char* code; std::uint64_t prefix; };
constexpr std::array<Case,26> cases={{
    {"seed",Route::seed,"","",0},{"thermal",Route::thermal,"","",0},
    {"material_opaque",Route::material,"","",0},
    {"record_payload_cap",Route::record_cap,"record","record_payload_extent",0},
    {"metadata_cap",Route::metadata_cap,"record","record_metadata_extent",0},
    {"thermal_cap",Route::thermal_cap,"codec","frame_cap",0},
    {"store_payload_cap",Route::store_cap,"store","payload_limit",64},
    {"short_source",Route::short_source,"record","record_metadata_extent",65},
    {"long_source",Route::long_source,"record","record_metadata_extent",64},
    {"throw_source",Route::throw_source,"runtime","fixed producer failure",65},
    {"swallowed_callback",Route::swallow_source,"record","record_metadata_source",66},
    {"nonfresh_writer",Route::nonfresh,"record","record_writer",6},
    {"missing_source",Route::missing_source,"record","record_metadata_source",0},
    {"bad_magic",Route::magic,"record","record_schema",0},
    {"bad_version",Route::version,"record","record_schema",0},
    {"bad_kind",Route::kind,"record","record_kind",0},
    {"bad_thermal_offset",Route::thermal_offset,"record","record_extent",0},
    {"bad_metadata_offset",Route::metadata_offset,"record","record_extent",0},
    {"bad_payload_length",Route::length,"record","record_extent",0},
    {"bad_reserved",Route::reserved,"record","record_extent",0},
    {"zero_metadata",Route::metadata_zero,"record","record_metadata_extent",0},
    {"seed_with_thermal",Route::seed_thermal,"record","record_kind",0},
    {"short_thermal_section",Route::short_thermal,"record","record_thermal_extent",0},
    {"bad_isolated_codec",Route::bad_codec,"codec","unknown_schema",0},
    {"short_isolated_codec",Route::short_codec,"codec","frame_length",0},
    {"corrupt_store_payload",Route::corrupt_payload,"store","integrity_failure",0}
}};
void quote(std::string_view s) {
    constexpr char hex[]="0123456789abcdef";std::cout<<'"';
    for(unsigned char c:s) {
        if(c=='"'||c=='\\')std::cout<<'\\'<<static_cast<char>(c);
        else if(c<32)std::cout<<"\\u00"<<hex[c>>4]<<hex[c&15];
        else std::cout<<static_cast<char>(c);
    }
    std::cout<<'"';
}
Bytes bytes(std::string_view s) {Bytes b;for(unsigned char c:s)b.push_back(std::byte(c));return b;}
Bytes file_bytes(const std::filesystem::path& path,std::uint64_t offset,std::size_t count) {
    std::ifstream f(path,std::ios::binary);f.seekg(static_cast<std::streamoff>(offset));Bytes out(count);
    if(count && !f.read(reinterpret_cast<char*>(out.data()),static_cast<std::streamsize>(count)))
        throw std::runtime_error("retained fixture read failed");
    return out;
}
EnthalpyMeshProofCodecLimits codec_limits() {
    EnthalpyMeshProofCodecLimits l;
    l.shape={128,256,129,32,32,9,4096,11};l.max_frame_bytes=fixture_bytes;
    l.max_decoded_payload_bytes=1048576;l.max_total_vector_elements=4096;l.max_legacy_json_bytes=1048576;
    return l;
}
LayeredProofRecordLimits record_limits(const Case& c) {
    LayeredProofRecordLimits l{normal_payload,8192,codec_limits()};
    if(c.route==Route::record_cap){l.maximum_payload_bytes=65;l.maximum_metadata_bytes=2;}
    if(c.route==Route::metadata_cap)l.maximum_metadata_bytes=1;
    if(c.route==Route::thermal_cap)--l.thermal.max_frame_bytes;
    return l;
}
LayeredProofStorePolicy policy(const Case& c) {
    const auto payload=c.route==Route::store_cap?65:normal_payload;
    return {256+payload+384,1,payload,50000,1,1,8};
}
LayeredProofStoreIdentity identity() {
    LayeredProofStoreIdentity id;
    for(std::size_t i=0;i<32;++i){id.store[i]=std::byte(i+1);id.source[i]=std::byte(i+65);}
    return id;
}
std::string metadata(const Case& c) {
    if(c.route==Route::seed)return "{\"opaque\":\"seed\"}";
    if(c.route==Route::thermal)return "{\"opaque\":\"thermal\"}";
    if(c.route==Route::material)return "{\"opaque\":\"material\"}";
    return "{}";
}
bool good(const Case& c){return c.route==Route::seed||c.route==Route::thermal||c.route==Route::material;}
bool raw_case(const Case& c){return c.route>=Route::magic && c.route<=Route::short_codec;}
void put(Bytes& out,std::size_t at,std::uint64_t value,unsigned count=8) {
    for(unsigned i=0;i<count;++i)out[at+i]=std::byte((value>>(i*8))&255);
}
Bytes header(std::uint32_t kind,std::uint64_t thermal,std::uint64_t meta) {
    Bytes out(64);const auto magic=bytes("LYRREC01");std::copy(magic.begin(),magic.end(),out.begin());
    put(out,8,1,4);put(out,12,kind,4);put(out,16,64);put(out,24,thermal);
    put(out,32,64+thermal);put(out,40,meta);put(out,48,64+thermal+meta);return out;
}
Bytes raw_record(const Case& c,const Bytes& fixture) {
    Bytes thermal;std::uint32_t kind=1;
    if(c.route==Route::short_thermal){kind=2;thermal.resize(23);}
    if(c.route==Route::bad_codec){kind=2;thermal.resize(24);}
    if(c.route==Route::short_codec){kind=2;thermal.assign(fixture.begin(),fixture.end()-1);}
    auto out=header(kind,thermal.size(),2);
    switch(c.route) {
        case Route::magic:out[0]=std::byte{0};break;
        case Route::version:put(out,8,2,4);break;
        case Route::kind:put(out,12,3,4);break;
        case Route::thermal_offset:put(out,16,65);break;
        case Route::metadata_offset:put(out,32,65);break;
        case Route::length:put(out,48,67);break;
        case Route::reserved:out[56]=std::byte{1};break;
        case Route::metadata_zero:put(out,40,0);break;
        case Route::seed_thermal:put(out,24,24);break;
        default:break;
    }
    out.insert(out.end(),thermal.begin(),thermal.end());const auto meta=bytes("{}");
    out.insert(out.end(),meta.begin(),meta.end());return out;
}
void stats_json(const LayeredProofStoreStats& s) {
    std::cout<<'{';
#define FIELD(n) std::cout<<"\"" #n "\":"<<s.n<<','
    FIELD(provisioned_bytes);FIELD(required_bytes);FIELD(reserved_payload_bytes);FIELD(attempts_started);
    FIELD(sealed_attempts);FIELD(aborted_attempts);FIELD(indeterminate_attempts);FIELD(committed_records);
    FIELD(payload_bytes_written);FIELD(total_bytes_written);FIELD(total_bytes_read);FIELD(payload_bytes_appended);
    FIELD(io_operations);FIELD(commit_sequence);FIELD(committed_revision);FIELD(active_writers);FIELD(active_readers);
    FIELD(io_buffer_bytes_live);FIELD(io_buffer_bytes_peak);FIELD(index_payload_bytes);FIELD(fenced);
    FIELD(commit_indeterminate);FIELD(directory_sync_completed);FIELD(known_volatile_filesystem);
#undef FIELD
    std::cout<<"\"filesystem_type\":"<<s.filesystem_type<<'}';
}
void spec_json(const Case& c) {
    const auto p=policy(c);const auto l=record_limits(c);
    std::cout<<"{\"name\":";quote(c.name);std::cout<<",\"relative_path\":";quote(std::string(c.name)+".bin");
    std::cout<<",\"metadata\":";quote(metadata(c));std::cout<<",\"family\":";quote(c.family);
    std::cout<<",\"code\":";quote(c.code);std::cout<<",\"expected_abort_prefix_bytes\":"<<c.prefix
        <<",\"store_policy\":{\"provisioned_bytes\":"<<p.provisioned_bytes
        <<",\"maximum_attempts\":1,\"maximum_payload_bytes\":"<<p.maximum_payload_bytes
        <<",\"maximum_io_operations\":50000,\"maximum_writers\":1,\"maximum_readers\":1,\"io_buffer_bytes\":8}"
        <<",\"record_limits\":{\"maximum_payload_bytes\":"<<l.maximum_payload_bytes
        <<",\"maximum_metadata_bytes\":"<<l.maximum_metadata_bytes
        <<",\"thermal\":{\"max_frame_bytes\":"<<l.thermal.max_frame_bytes
        <<",\"max_decoded_payload_bytes\":1048576,\"max_total_vector_elements\":4096,\"max_legacy_json_bytes\":1048576,"
          "\"shape\":{\"max_nodes\":128,\"max_edges\":256,\"max_sweeps_per_stage\":129,"
          "\"max_backward_euler_leaves_per_stage\":32,\"max_outer_leaves\":32,\"max_polynomial_coefficients\":9,"
          "\"max_string_bytes\":4096,\"max_temperature_branch_bytes\":11}}}}";
}
std::vector<std::string> check_names() {
    std::vector<std::string> out{"fixed_input_extent"};
    for(const auto& c:cases) {
        const std::string n=c.name;
        if(good(c)) {
            out.push_back(n+".exact_sections");out.push_back(n+".roundtrip");out.push_back(n+".released");
            if(c.route==Route::seed)out.push_back(n+".post_wrapper");
        } else {
            out.push_back(n+".typed");out.push_back(n+(raw_case(c)?".sealed_not_fenced":
                c.route==Route::corrupt_payload?".fenced":".aborted_prefix"));
        }
    }
    out.push_back("fixed_call_closure");return out;
}
struct Run {
    std::uint64_t checks=0,failures=0,errors=0,creates=0,begins=0,record_seals=0,record_reads=0;
    std::uint64_t raw_appends=0,raw_seals=0,explicit_aborts=0,source_decodes=0,equality_encodes=0,stats_rows=0;
    std::uint64_t metadata_producers=0;
    const std::vector<std::string> names=check_names();
    void check(const std::string& name,bool okay) {
        okay=okay && checks<names.size() && names[static_cast<std::size_t>(checks)]==name;
        ++checks;if(!okay)++failures;
        std::cout<<"{\"type\":\"check\",\"name\":";quote(name);std::cout<<",\"pass\":"<<okay<<"}\n";
    }
    template<class F>void error(const Case& c,F&& action) {
        std::string family="none",code="no_exception";bool fenced=false,ambiguous=false;
        try{action();}
        catch(const LayeredProofRecordError& e){family="record";code=e.code;}
        catch(const EnthalpyMeshProofCodecError& e){family="codec";code=e.code;}
        catch(const LayeredProofStoreError& e){family="store";code=e.code;fenced=e.fenced;ambiguous=e.commit_indeterminate;}
        catch(const std::runtime_error& e){family="runtime";code=e.what();}
        ++errors;std::cout<<"{\"type\":\"error\",\"name\":";quote(c.name);
        std::cout<<",\"family\":";quote(family);std::cout<<",\"code\":";quote(code);
        std::cout<<",\"fenced\":"<<fenced<<",\"commit_indeterminate\":"<<ambiguous<<"}\n";
        check(std::string(c.name)+".typed",family==c.family && code==c.code && !ambiguous
            && fenced==(c.route==Route::corrupt_payload));
    }
    LayeredProofRecordRead read(const LayeredProofHandle& h,Bytes& out,const LayeredProofRecordLimits& l) {
        ++record_reads;return read_layered_proof_record(h,[&](std::span<const std::byte> b){out.insert(out.end(),b.begin(),b.end());},l);
    }
    bool equal_thermal(const EnthalpyMeshSdirk2Receipt& r,const Bytes& fixture) {
        std::size_t at=0;bool equal=true;++equality_encodes;
        encode_enthalpy_mesh_proof(r,[&](std::span<const std::byte> b){
            if(at>fixture.size() || b.size()>fixture.size()-at)equal=false;
            else if(!std::equal(b.begin(),b.end(),fixture.begin()+static_cast<std::ptrdiff_t>(at)))equal=false;
            at+=b.size();
        },codec_limits());return equal && at==fixture.size();
    }
    void stats(const Case& c,const LayeredProofStore& store,const char* stage) {
        ++stats_rows;std::cout<<"{\"type\":\"stats\",\"name\":";quote(c.name);
        std::cout<<",\"stage\":";quote(stage);std::cout<<",\"value\":";stats_json(store.stats());std::cout<<"}\n";
    }
};
void corrupt(const std::filesystem::path& path) {
#ifdef __linux__
    const int fd=::open(path.c_str(),O_RDWR|O_CLOEXEC);if(fd<0)throw std::runtime_error("fault file open failed");
    unsigned char value=0;const auto offset=static_cast<off_t>(384+64);
    const bool read=::pread(fd,&value,1,offset)==1;value^=0x80;
    const bool write=read && ::pwrite(fd,&value,1,offset)==1;const int closed=::close(fd);
    if(!write || closed!=0)throw std::runtime_error("fault file mutation failed");
#else
    (void)path;throw std::runtime_error("Linux fixture required");
#endif
}
void execute_case(Run& t,const Case& c,const std::filesystem::path& dir,
                  const Bytes& fixture,const EnthalpyMeshSdirk2Receipt& thermal) {
    const auto path=dir/(std::string(c.name)+".bin");const auto l=record_limits(c);const auto meta=bytes(metadata(c));
    std::cout<<"{\"type\":\"case\",\"spec\":";spec_json(c);std::cout<<"}\n";
    std::uint64_t last_operation=0,read_operations=0;
    ++t.creates;
    std::optional<LayeredProofStore> s(LayeredProofStore::create(path.string(),policy(c),identity(),[&](const auto& op){
        last_operation=op.operation_number;
        if(op.kind==LayeredProofIoKind::read){++read_operations;return LayeredProofIoDirective{8,0};}
        return LayeredProofIoDirective{};
    }));
    LayeredProofHandle h;
    if(raw_case(c)) {
        const auto raw=raw_record(c,fixture);++t.begins;auto w=s->begin();++t.raw_appends;w.append(raw);
        ++t.raw_seals;h=w.seal();Bytes output;
        t.error(c,[&]{(void)t.read(h,output,l);});
        t.check(std::string(c.name)+".sealed_not_fenced",s->stats().sealed_attempts==1 && s->stats().aborted_attempts==0
            && s->stats().active_readers==0 && !s->stats().fenced && output.empty()
            && file_bytes(path,384,raw.size())==raw);
        t.stats(c,*s,"final");return;
    }
    const auto kind=c.route==Route::thermal||c.route==Route::material||c.route==Route::thermal_cap
        ?LayeredProofRecordKind::transaction:LayeredProofRecordKind::seed;
    const auto* receipt=c.route==Route::thermal||c.route==Route::thermal_cap?&thermal:nullptr;
    LayeredProofMetadataProducer producer=[&](const EnthalpyMeshProofSink& sink){
        ++t.metadata_producers;
        if(c.route==Route::short_source){sink(std::span<const std::byte>(meta).first(1));return;}
        if(c.route==Route::long_source){sink(bytes("{}x"));return;}
        if(c.route==Route::throw_source){sink(std::span<const std::byte>(meta).first(1));throw std::runtime_error("fixed producer failure");}
        sink(meta);
        if(c.route==Route::swallow_source){try{sink(bytes("x"));}catch(const LayeredProofRecordError&){} }
    };
    if(c.route==Route::missing_source)producer={};
    {
        ++t.begins;auto w=s->begin();
        if(c.route==Route::nonfresh){++t.raw_appends;w.append(bytes("prefix"));}
        const auto seal=[&]{++t.record_seals;h=seal_layered_proof_record(w,kind,receipt,meta.size(),producer,l);};
        if(!good(c) && c.route!=Route::corrupt_payload){
            t.error(c,seal);
            if(c.route==Route::nonfresh){++t.explicit_aborts;w.abort(77);}
            Bytes expected;
            if(c.route==Route::nonfresh)expected=bytes("prefix");
            else if(c.prefix){expected=header(1,0,2);const auto suffix=bytes("{}");
                expected.insert(expected.end(),suffix.begin(),suffix.begin()+static_cast<std::ptrdiff_t>(c.prefix-64));}
            t.check(std::string(c.name)+".aborted_prefix",s->stats().aborted_attempts==1 && s->stats().sealed_attempts==0
                && s->stats().payload_bytes_written==c.prefix && s->stats().payload_bytes_appended==c.prefix
                && s->stats().active_writers==0 && !s->stats().fenced && !h.valid()
                && file_bytes(path,384,static_cast<std::size_t>(c.prefix))==expected);
            t.stats(c,*s,"final");return;
        }
        seal();
    }
    if(c.route==Route::corrupt_payload){
        corrupt(path);Bytes output;t.error(c,[&]{(void)t.read(h,output,l);});
        t.check(std::string(c.name)+".fenced",s->stats().fenced && !s->stats().commit_indeterminate
            && s->stats().sealed_attempts==1 && s->stats().active_readers==0 && output.empty());
        t.stats(c,*s,"final");return;
    }
    const auto expected_header=header(static_cast<std::uint32_t>(kind),receipt?fixture_bytes:0,meta.size());
    bool exact=file_bytes(path,384,64)==expected_header && h.payload_bytes()==64+(receipt?fixture_bytes:0)+meta.size();
    if(receipt)exact=exact && file_bytes(path,448,fixture.size())==fixture;
    t.check(std::string(c.name)+".exact_sections",exact && file_bytes(path,448+(receipt?fixture_bytes:0),meta.size())==meta);
    Bytes output;const auto result=t.read(h,output,l);
    bool roundtrip=result.integrity_verified && output==meta && result.layout.thermal_offset==64
        && result.layout.thermal_bytes==(receipt?fixture_bytes:0) && result.layout.metadata_offset==64+(receipt?fixture_bytes:0)
        && result.layout.metadata_bytes==meta.size() && result.layout.payload_bytes==h.payload_bytes()
        && result.layout.kind==kind && result.thermal.has_value()==(receipt!=nullptr);
    if(result.thermal)roundtrip=roundtrip && t.equal_thermal(*result.thermal,fixture);
    t.check(std::string(c.name)+".roundtrip",roundtrip);
    t.check(std::string(c.name)+".released",s->stats().active_readers==0 && s->stats().active_writers==0
        && s->stats().io_buffer_bytes_live==0 && s->stats().io_buffer_bytes_peak==8
        && s->stats().sealed_attempts==1 && s->stats().aborted_attempts==0 && !s->stats().fenced && read_operations>=64);
    t.stats(c,*s,c.route==Route::seed?"before_wrapper_destruction":"final");
    if(c.route==Route::seed){
        const auto before=last_operation;s.reset();Bytes after;const auto decoded=t.read(h,after,l);
        t.check("seed.post_wrapper",decoded.integrity_verified && !decoded.thermal && after==meta && last_operation>before);
        std::cout<<"{\"type\":\"post_wrapper\",\"case\":\"seed\",\"before_io_operations\":"<<before
            <<",\"final_hook_operation_number\":"<<last_operation<<",\"read_operations\":"<<read_operations<<"}\n";
    }
}
void inventory(){
    std::cout<<"{\"type\":\"inventory\",\"schema\":\"layered_proof_record_qualification_v1\",\"fixture_bytes\":"
        <<fixture_bytes<<",\"fixture_sha256\":";quote(fixture_sha);
    std::cout<<",\"store_identity_bytes\":[";
    for(unsigned i=1;i<=32;++i){if(i!=1){std::cout<<',';}std::cout<<i;}
    std::cout<<"],\"source_identity_bytes\":[";
    for(unsigned i=65;i<=96;++i){if(i!=65){std::cout<<',';}std::cout<<i;}
    std::cout<<"],\"initial_revision\":0,\"maximum_real_read_bytes\":8,\"cases\":[";
    for(std::size_t i=0;i<cases.size();++i){if(i){std::cout<<',';}spec_json(cases[i]);}
    std::cout<<"],\"check_names\":[";const auto names=check_names();
    for(std::size_t i=0;i<names.size();++i){if(i){std::cout<<',';}quote(names[i]);}
    std::cout<<"],\"expected\":{\"checks\":58,\"errors\":23,\"cases\":26,\"stats_rows\":26,"
        "\"store_creates\":26,\"store_begins\":26,\"record_seals\":14,\"record_reads\":17,"
        "\"raw_appends\":13,\"raw_seals\":12,\"explicit_aborts\":1,\"source_decodes\":1,"
        "\"equality_encodes\":1,\"metadata_producers\":9},\"inventory_api_calls\":0,"
        "\"metadata_schema_validity_claim\":false,\"kernel_calls\":0,\"physical_calls\":0}\n";
}
int run(const std::filesystem::path& input,const std::filesystem::path& dir){
    if(!std::filesystem::create_directory(dir))throw std::runtime_error("new exclusive output directory required");
    Run t;t.check("fixed_input_extent",std::filesystem::file_size(input)==fixture_bytes);
    if(std::filesystem::file_size(input)!=fixture_bytes)throw std::runtime_error("fixed fixture extent differs");
    const auto fixture=file_bytes(input,0,fixture_bytes);std::size_t consumed=0;++t.source_decodes;
    const auto thermal=decode_enthalpy_mesh_proof([&](std::span<std::byte> out){
        if(out.size()>fixture.size()-consumed)throw std::runtime_error("fixed input exhausted");
        std::copy_n(fixture.begin()+static_cast<std::ptrdiff_t>(consumed),out.size(),out.begin());consumed+=out.size();
    },fixture_bytes,codec_limits());
    for(const auto& c:cases)execute_case(t,c,dir,fixture,thermal);
    t.check("fixed_call_closure",t.checks==57 && t.errors==23 && t.creates==26 && t.begins==26
        && t.record_seals==14 && t.record_reads==17 && t.raw_appends==13 && t.raw_seals==12
        && t.explicit_aborts==1 && t.source_decodes==1 && t.equality_encodes==1
        && t.stats_rows==26 && t.metadata_producers==9 && consumed==fixture.size());
    std::cout<<"{\"type\":\"summary\",\"checks\":"<<t.checks<<",\"failures\":"<<t.failures<<",\"errors\":"<<t.errors
        <<",\"cases\":"<<t.creates<<",\"stats_rows\":"<<t.stats_rows<<",\"store_creates\":"<<t.creates
        <<",\"store_begins\":"<<t.begins<<",\"record_seals\":"<<t.record_seals<<",\"record_reads\":"<<t.record_reads
        <<",\"raw_appends\":"<<t.raw_appends<<",\"raw_seals\":"<<t.raw_seals<<",\"explicit_aborts\":"<<t.explicit_aborts
        <<",\"source_decodes\":"<<t.source_decodes<<",\"equality_encodes\":"<<t.equality_encodes
        <<",\"metadata_producers\":"<<t.metadata_producers<<",\"kernel_calls\":0,\"owner_calls\":0,"
        "\"metadata_writer_calls\":0,\"physical_calls\":0,\"schedule_complete\":"<<(t.checks==t.names.size())<<"}\n";
    return t.failures || t.checks!=t.names.size()?1:0;
}
} // namespace
int main(int argc,char** argv){
    std::cout<<std::boolalpha;
    try{
        if(argc==2 && std::string_view(argv[1])=="--inventory"){inventory();return 0;}
        if(argc==4 && std::string_view(argv[1])=="--run")return run(argv[2],argv[3]);
        std::cerr<<"explicit --inventory or --run PINNED_INPUT NEW_DIR required\n";return 2;
    }catch(const std::exception& e){std::cout<<"{\"type\":\"fatal\",\"detail\":";quote(e.what());std::cout<<"}\n";return 1;}
}
