#include "enthalpy_mesh_proof_codec.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <cstring>
#include <iomanip>
#include <limits>
#include <locale>
#include <sstream>
#include <string_view>
#include <type_traits>
#include <utility>

namespace magic_geo::detail {
namespace {
static_assert(sizeof(double) == 8 && std::numeric_limits<double>::is_iec559 &&
              std::numeric_limits<double>::digits == 53);
static_assert(std::numeric_limits<int>::digits >= 31);
constexpr std::array<std::byte, 8> magic{std::byte{'M'}, std::byte{'G'}, std::byte{'S'},
    std::byte{'D'}, std::byte{'I'}, std::byte{'R'}, std::byte{'K'}, std::byte{0}};
using Size = EnthalpyMeshProofCodecSize;
using Shape = EnthalpyMeshProofCodecShape;
using Limits = EnthalpyMeshProofCodecLimits;
[[noreturn]] void fail(const char* code, const char* detail) { throw EnthalpyMeshProofCodecError(code, detail); }
void need(bool condition, const char* code, const char* detail) { if (!condition) fail(code, detail); }
std::uint64_t add(std::uint64_t a, std::uint64_t b) {
    need(b <= UINT64_MAX-a, "size_overflow", "checked proof size addition overflow"); return a+b;
}
std::uint64_t mul(std::uint64_t a, std::uint64_t b) {
    need(a == 0 || b <= UINT64_MAX/a, "size_overflow", "checked proof size multiplication overflow"); return a*b;
}
void signed_range(int value) {
    need(value >= INT32_MIN && value <= INT32_MAX, "integer_range", "integer does not fit wire i32");
}

// One structural traversal drives exact sizing, encoding, decoding and the
// symbolic maximum-shape visitor. Flags never mask stored operands here.
template<class V, class T> void interval(V& v, T& x) { v.number(x.lower); v.number(x.upper); }
template<class V, class T> void doubles(V& v, T& x) {
    v.vector(x, v.shape.max_nodes, 8, [&](auto& z) { v.number(z); });
}
template<class V, class T> void intervals(V& v, T& x, std::uint32_t cap) {
    v.vector(x, cap, 16, [&](auto& z) { interval(v, z); });
}
template<class V, class T> void request(V& v, T& x) {
    v.number(x.water.freezing_temperature_k); v.number(x.water.solid_heat_capacity_j_kg_k);
    v.number(x.water.liquid_heat_capacity_j_kg_k); v.number(x.water.latent_heat_j_kg);
    v.vector(x.columns, v.shape.max_nodes, 24, [&](auto& c) {
        v.number(c.area_m2); v.number(c.heat_capacity_j_m2_k); v.number(c.longwave_emissivity);
    });
    v.vector(x.edges, v.shape.max_edges, 16, [&](auto& e) {
        v.integer(e.first_cell); v.integer(e.second_cell); v.number(e.conductance_w_k);
    });
    doubles(v, x.water_mass_kg_m2); doubles(v, x.initial_enthalpy_j_m2); doubles(v, x.absorbed_shortwave_w_m2);
    auto& o = x.options;
    v.number(o.duration_seconds); v.number(o.maximum_stage_error_j); v.number(o.maximum_endpoint_error_j);
    v.integer(o.maximum_sweeps); v.integer(o.maximum_coordinate_iterations); v.counter(o.maximum_scalar_evaluations);
    v.integer(o.reconstruction_leaves); v.flag(o.allow_pure_water_columns);
}
template<class V, class T> void field(V& v, T& x) {
    intervals(v, x.temperature_k, v.shape.max_nodes); intervals(v, x.emitted_longwave_w_m2, v.shape.max_nodes);
    intervals(v, x.edge_heat_w, v.shape.max_edges); intervals(v, x.heat_convergence_w_m2, v.shape.max_nodes);
    intervals(v, x.net_heating_w_m2, v.shape.max_nodes);
}
template<class V, class T> void backward_euler(V& v, T& x) {
    v.flag(x.accepted); v.string(x.failure_code, v.shape.max_string_bytes); v.string(x.detail, v.shape.max_string_bytes);
    v.optional(x.request, [&](auto& z) { request(v, z); });
    v.flag(x.physical_domain_proved); v.number(x.physical_temperature_upper_k);
    intervals(v, x.physical_floor_j_m2, v.shape.max_nodes);
    v.flag(x.candidate_available); v.flag(x.stage_error_available); doubles(v, x.candidate_enthalpy_j_m2);
    field(v, x.candidate_field); intervals(v, x.stage_residual_j_m2, v.shape.max_nodes);
    v.number(x.stage_error_upper_j); v.flag(x.stage_accepted);
    v.vector(x.sweeps, v.shape.max_sweeps_per_stage, 20, [&](auto& s) {
        v.integer(s.completed_sweeps); v.counter(s.scalar_evaluations); v.number(s.stage_error_upper_j);
    });
    v.vector(x.leaves, v.shape.max_backward_euler_leaves_per_stage, 41, [&](auto& l) {
        v.integer(l.index); v.flag(l.complete); intervals(v, l.enthalpy_range_j_m2, v.shape.max_nodes);
        field(v, l.field); intervals(v, l.residual_integral_j_m2, v.shape.max_nodes); v.number(l.weighted_residual_upper_j);
    });
    v.flag(x.endpoint_error_available); v.number(x.local_endpoint_error_upper_j);
    v.optional(x.final_enthalpy_j_m2, [&](auto& z) { doubles(v, z); });
    v.counter(x.scalar_evaluations); v.counter(x.field_evaluations);
    v.integer(x.sweeps_started); v.integer(x.coordinate_solves_started); v.integer(x.leaves_started);
}
template<class V, class T> void polynomials(V& v, T& x) {
    v.vector(x, v.shape.max_nodes, 4, [&](auto& p) { intervals(v, p, v.shape.max_polynomial_coefficients); });
}
template<class V, class T> void sdirk(V& v, T& x) {
    v.flag(x.accepted); v.string(x.failure_code, v.shape.max_string_bytes); v.string(x.detail, v.shape.max_string_bytes);
    v.optional(x.request, [&](auto& z) { request(v, z); });
    v.number(x.gamma); v.number(x.diagonal_duration_seconds); v.number(x.off_diagonal_duration_seconds);
    v.flag(x.tableau_bridges_available); interval(v, x.duration_sum_defect_seconds); interval(v, x.second_order_coefficient_defect);
    doubles(v, x.initial_heating_w_m2); doubles(v, x.first_stage_heating_w_m2); doubles(v, x.second_stage_base_j_m2);
    intervals(v, x.second_stage_base_defect_j_m2, v.shape.max_nodes);
    v.optional(x.first_stage, [&](auto& z) { backward_euler(v, z); });
    v.optional(x.second_stage, [&](auto& z) { backward_euler(v, z); });
    v.flag(x.physical_curve_proved); v.flag(x.endpoint_error_available);
    v.vector(x.leaves, v.shape.max_outer_leaves, 33, [&](auto& l) {
        v.integer(l.index); v.flag(l.complete);
        polynomials(v, l.enthalpy); polynomials(v, l.temperature); polynomials(v, l.residual);
        v.vector(l.temperature_branch, v.shape.max_nodes, 4, [&](auto& z) { v.string(z, v.shape.max_temperature_branch_bytes); });
        doubles(v, l.absolute_residual_integral_upper_j_m2); v.number(l.weighted_residual_upper_j);
    });
    v.number(x.local_endpoint_error_upper_j); v.optional(x.final_enthalpy_j_m2, [&](auto& z) { doubles(v, z); });
    v.counter(x.scalar_evaluations); v.counter(x.field_evaluations);
    v.integer(x.stage_calls_started); v.integer(x.sweeps_started); v.integer(x.coordinate_solves_started);
    v.integer(x.backward_euler_leaves_started); v.integer(x.certificate_leaves_started);
}

struct Meter {
    const Shape& shape;
    const Limits* limits;
    Size size{enthalpy_mesh_proof_codec_header_bytes, sizeof(EnthalpyMeshSdirk2Receipt), 0, 0};
    Meter(const Shape& s, const Limits* l) : shape(s), limits(l) { check(); }
    void check() const {
        if (!limits) return;
        need(size.frame_bytes <= limits->max_frame_bytes, "frame_cap", "proof frame exceeds selected byte cap");
        need(size.decoded_payload_bytes <= limits->max_decoded_payload_bytes,
             "decoded_payload_cap", "proof decoded payload exceeds selected cap");
        need(size.total_vector_elements <= limits->max_total_vector_elements,
             "element_cap", "proof total vector elements exceed selected cap");
    }
    void wire(std::uint64_t n) { size.frame_bytes = add(size.frame_bytes, n); check(); }
    void elements(std::uint64_t n, std::uint64_t element_size, std::uint32_t cap) {
        need(n <= cap && n <= UINT32_MAX, "shape_cap", "proof vector exceeds its field count cap");
        size.total_vector_elements = add(size.total_vector_elements, n);
        size.decoded_payload_bytes = add(size.decoded_payload_bytes, mul(n, element_size)); check();
    }
    void characters(std::uint64_t n, std::uint32_t cap) {
        need(n <= cap && n <= UINT32_MAX, "string_cap", "proof string exceeds its byte cap");
        size.total_string_bytes = add(size.total_string_bytes, n);
        size.decoded_payload_bytes = add(size.decoded_payload_bytes, add(n, 1)); check();
    }
};
struct Counter : Meter {
    using Meter::Meter;
    void number(double) { wire(8); }
    void integer(int x) { signed_range(x); wire(4); }
    void counter(std::uint64_t) { wire(8); }
    void flag(bool) { wire(1); }
    void string(const std::string& x, std::uint32_t cap) { wire(4); characters(x.size(), cap); wire(x.size()); }
    template<class T, class F> void vector(const std::vector<T>& x, std::uint32_t cap, std::uint64_t, F f) {
        wire(4); elements(x.size(), sizeof(T), cap); for (const auto& z : x) f(z);
    }
    template<class T, class F> void optional(const std::optional<T>& x, F f) { wire(1); if (x) f(*x); }
};
struct Maximum : Meter {
    explicit Maximum(const Shape& s) : Meter(s, nullptr) {}
    void number(double) { wire(8); }
    void integer(int) { wire(4); }
    void counter(std::uint64_t) { wire(8); }
    void flag(bool) { wire(1); }
    void string(const std::string&, std::uint32_t cap) { wire(4); characters(cap, cap); wire(cap); }
    template<class T, class F> void vector(const std::vector<T>&, std::uint32_t cap, std::uint64_t, F f) {
        wire(4); elements(cap, sizeof(T), cap);
        if (!cap) return;
        const auto before = size; T item{}; f(item);
#define REPEAT(name) size.name = add(size.name, mul(cap-1, size.name-before.name))
        REPEAT(frame_bytes); REPEAT(decoded_payload_bytes); REPEAT(total_vector_elements); REPEAT(total_string_bytes);
#undef REPEAT
    }
    template<class T, class F> void optional(const std::optional<T>&, F f) { wire(1); T item{}; f(item); }
};

class Output {
    const EnthalpyMeshProofSink& sink_;
    std::array<std::byte, enthalpy_mesh_proof_codec_io_buffer_bytes> buffer_{};
    std::size_t used_ = 0;
    std::uint64_t count_ = 0, cap_;
public:
    Output(const EnthalpyMeshProofSink& sink, std::uint64_t cap) : sink_(sink), cap_(cap) {
        need(static_cast<bool>(sink), "invalid_callback", "proof sink callback is absent");
    }
    void flush() {
        if (!used_) return;
        try { sink_(std::span<const std::byte>(buffer_.data(), used_)); }
        catch (...) { fail("sink_failure", "proof sink did not complete requested bytes"); }
        used_ = 0;
    }
    void write(std::span<const std::byte> bytes) {
        need(bytes.size() <= cap_-count_, "frame_cap", "proof output exceeds reserved extent");
        count_ += bytes.size();
        while (!bytes.empty()) {
            const auto n = std::min(bytes.size(), buffer_.size()-used_);
            std::memcpy(buffer_.data()+used_, bytes.data(), n); used_ += n; bytes = bytes.subspan(n);
            if (used_ == buffer_.size()) flush();
        }
    }
    std::uint64_t count() const { return count_; }
    void unsigned_value(std::uint64_t x, std::size_t bytes) {
        std::array<std::byte, 8> raw{};
        for (std::size_t i=0; i<bytes; ++i) { raw[i] = static_cast<std::byte>(x & 255); x >>= 8; }
        write(std::span<const std::byte>(raw.data(), bytes));
    }
};
class Input {
    const EnthalpyMeshProofSource& source_;
    std::array<std::byte, enthalpy_mesh_proof_codec_io_buffer_bytes> buffer_{};
    std::size_t begin_ = 0, end_ = 0;
    std::uint64_t read_ = 0, consumed_ = 0, extent_;
public:
    Input(const EnthalpyMeshProofSource& source, std::uint64_t extent) : source_(source), extent_(extent) {
        need(static_cast<bool>(source), "invalid_callback", "proof source callback is absent");
    }
    std::uint64_t remaining() const { return extent_-consumed_; }
    void read(std::span<std::byte> out) {
        need(out.size() <= remaining(), "truncated_frame", "proof field exceeds remaining frame bytes");
        while (!out.empty()) {
            if (begin_ == end_) {
                begin_ = 0; end_ = static_cast<std::size_t>(std::min<std::uint64_t>(buffer_.size(), extent_-read_));
                need(end_ != 0, "truncated_frame", "proof source extent exhausted");
                try { source_(std::span<std::byte>(buffer_.data(), end_)); }
                catch (...) { fail("source_failure", "proof source did not supply requested bytes"); }
                read_ += end_;
            }
            const auto n = std::min(out.size(), end_-begin_);
            std::memcpy(out.data(), buffer_.data()+begin_, n);
            begin_ += n; consumed_ += n; out = out.subspan(n);
        }
    }
    std::uint64_t unsigned_value(std::size_t bytes) {
        std::array<std::byte, 8> raw{}; read(std::span<std::byte>(raw.data(), bytes));
        std::uint64_t value = 0;
        for (std::size_t i=0; i<bytes; ++i) value |= std::uint64_t(std::to_integer<unsigned int>(raw[i])) << (8*i);
        return value;
    }
};
struct Encoder : Meter {
    Output& out;
    Encoder(Output& o, const Limits& l) : Meter(l.shape, &l), out(o) {}
    void number(double x) { wire(8); out.unsigned_value(std::bit_cast<std::uint64_t>(x), 8); }
    void integer(int x) { signed_range(x); wire(4); out.unsigned_value(std::bit_cast<std::uint32_t>(static_cast<std::int32_t>(x)), 4); }
    void counter(std::uint64_t x) { wire(8); out.unsigned_value(x, 8); }
    void flag(bool x) { wire(1); out.unsigned_value(x ? 1 : 0, 1); }
    void string(const std::string& x, std::uint32_t cap) {
        wire(4); characters(x.size(), cap); wire(x.size()); out.unsigned_value(x.size(), 4);
        out.write(std::as_bytes(std::span<const char>(x.data(), x.size())));
    }
    template<class T, class F> void vector(const std::vector<T>& x, std::uint32_t cap, std::uint64_t, F f) {
        wire(4); elements(x.size(), sizeof(T), cap); out.unsigned_value(x.size(), 4); for (const auto& z : x) f(z);
    }
    template<class T, class F> void optional(const std::optional<T>& x, F f) { flag(x.has_value()); if (x) f(*x); }
};
struct Decoder : Meter {
    Input& in;
    Decoder(Input& i, const Limits& l) : Meter(l.shape, &l), in(i) {}
    void number(double& x) { wire(8); x = std::bit_cast<double>(in.unsigned_value(8)); }
    void integer(int& x) { wire(4); x = std::bit_cast<std::int32_t>(static_cast<std::uint32_t>(in.unsigned_value(4))); }
    void counter(std::uint64_t& x) { wire(8); x = in.unsigned_value(8); }
    void flag(bool& x) {
        wire(1); const auto raw = in.unsigned_value(1);
        need(raw <= 1, "invalid_boolean", "proof boolean must be exactly zero or one"); x = raw != 0;
    }
    void string(std::string& x, std::uint32_t cap) {
        wire(4); const auto n = in.unsigned_value(4);
        need(n <= in.remaining(), "truncated_frame", "proof string exceeds remaining frame");
        characters(n, cap); wire(n);
        need(n <= x.max_size(), "allocation_cap", "proof string exceeds host container limit");
        x.resize(static_cast<std::size_t>(n)); in.read(std::as_writable_bytes(std::span<char>(x.data(), x.size())));
    }
    template<class T, class F> void vector(std::vector<T>& x, std::uint32_t cap, std::uint64_t minimum, F f) {
        wire(4); const auto n = in.unsigned_value(4);
        need(mul(n, minimum) <= in.remaining(), "truncated_frame", "proof vector minimum exceeds remaining frame");
        elements(n, sizeof(T), cap);
        need(n <= x.max_size(), "allocation_cap", "proof vector exceeds host container limit");
        x.resize(static_cast<std::size_t>(n)); for (auto& z : x) f(z);
    }
    template<class T, class F> void optional(std::optional<T>& x, F f) {
        bool present = false; flag(present); if (present) { x.emplace(); f(*x); } else x.reset();
    }
};

// JSON writer follows the existing serializers' public projection, including
// their conditional nulls and omission of a false pure-water request option.
class Json {
    Output* out_;
    std::uint64_t count_ = 0, cap_;
public:
    Json(Output* out, std::uint64_t cap) : out_(out), cap_(cap) {}
    void text(std::string_view value) {
        count_ = add(count_, value.size()); need(count_ <= cap_, "legacy_json_cap", "legacy JSON exceeds selected byte cap");
        if (out_) out_->write(std::as_bytes(std::span<const char>(value.data(), value.size())));
    }
    std::uint64_t count() const { return count_; }
    void quote(const std::string& value) {
        text("\"");
        for (unsigned char c : value) {
            if (c == '"' || c == '\\') { text("\\"); const char ch=static_cast<char>(c); text(std::string_view(&ch,1)); }
            else if (c < 32 || c > 126) {
                // The legacy quote helpers inherit the global stream locale.
                std::ostringstream escaped; escaped << "\\u" << std::hex << std::setw(4) << std::setfill('0') << int(c);
                text(escaped.str());
            } else { const char ch=static_cast<char>(c); text(std::string_view(&ch,1)); }
        }
        text("\"");
    }
    void number(double value) {
        std::ostringstream encoded; encoded.imbue(std::locale::classic());
        const auto bits = std::bit_cast<std::uint64_t>(value);
        if ((bits & UINT64_C(0x7ff0000000000000)) == UINT64_C(0x7ff0000000000000))
            encoded << "{\"nonfinite_binary64_bits\":\"" << std::hex << bits << "\"}";
        else encoded << std::setprecision(std::numeric_limits<double>::max_digits10) << value;
        text(encoded.str());
    }
    void flag(bool value) { text(value ? "true" : "false"); }
    template<class T> void integer(T value) { text(std::to_string(value)); }
    template<class T, class F> void array(const std::vector<T>& values, F f) {
        text("["); bool first=true; for (const auto& x : values) { if (!first) text(","); first=false; f(x); } text("]");
    }
};
class JsonObject {
    Json& j_; bool first_ = true;
public:
    explicit JsonObject(Json& j) : j_(j) { j_.text("{"); }
    void key(const char* key) { if (!first_) j_.text(","); first_=false; j_.quote(key); j_.text(":"); }
    void num(const char* key, double x) { this->key(key); j_.number(x); }
    void flag(const char* key, bool x) { this->key(key); j_.flag(x); }
    void string(const char* key, const std::string& x) { this->key(key); j_.quote(x); }
    template<class T> void integer(const char* key, T x) { this->key(key); j_.integer(x); }
    void end() { j_.text("}"); }
};
void json_interval(Json& j, EnthalpyMeshInterval x) { JsonObject o(j); o.num("lower",x.lower); o.num("upper",x.upper); o.end(); }
void json_doubles(Json& j, const std::vector<double>& x) { j.array(x,[&](double v){j.number(v);}); }
void json_intervals(Json& j, const std::vector<EnthalpyMeshInterval>& x) { j.array(x,[&](auto v){json_interval(j,v);}); }
void json_field(Json& j, const EnthalpyMeshField& x) {
    JsonObject o(j);
#define FIELD(name) o.key(#name); json_intervals(j,x.name)
    FIELD(temperature_k); FIELD(emitted_longwave_w_m2); FIELD(edge_heat_w);
    FIELD(heat_convergence_w_m2); FIELD(net_heating_w_m2);
#undef FIELD
    o.end();
}
void json_request(Json& j, const EnthalpyMeshRequest& q) {
    JsonObject o(j); o.key("water"); JsonObject w(j);
    w.num("freezing_temperature_k",q.water.freezing_temperature_k); w.num("solid_heat_capacity_j_kg_k",q.water.solid_heat_capacity_j_kg_k);
    w.num("liquid_heat_capacity_j_kg_k",q.water.liquid_heat_capacity_j_kg_k); w.num("latent_heat_j_kg",q.water.latent_heat_j_kg); w.end();
    o.key("columns"); j.array(q.columns,[&](const auto& c){JsonObject z(j);z.num("area_m2",c.area_m2);
        z.num("heat_capacity_j_m2_k",c.heat_capacity_j_m2_k);z.num("longwave_emissivity",c.longwave_emissivity);z.end();});
    o.key("edges"); j.array(q.edges,[&](const auto& e){JsonObject z(j);z.integer("first_cell",e.first_cell);
        z.integer("second_cell",e.second_cell);z.num("conductance_w_k",e.conductance_w_k);z.end();});
    o.key("water_mass_kg_m2");json_doubles(j,q.water_mass_kg_m2);
    o.key("initial_enthalpy_j_m2");json_doubles(j,q.initial_enthalpy_j_m2);
    o.key("absorbed_shortwave_w_m2");json_doubles(j,q.absorbed_shortwave_w_m2);
    o.key("options");JsonObject opt(j);const auto& a=q.options;
    opt.num("duration_seconds",a.duration_seconds);opt.num("maximum_stage_error_j",a.maximum_stage_error_j);
    opt.num("maximum_endpoint_error_j",a.maximum_endpoint_error_j);opt.integer("maximum_sweeps",a.maximum_sweeps);
    opt.integer("maximum_coordinate_iterations",a.maximum_coordinate_iterations);opt.integer("maximum_scalar_evaluations",a.maximum_scalar_evaluations);
    opt.integer("reconstruction_leaves",a.reconstruction_leaves);if(a.allow_pure_water_columns)opt.flag("allow_pure_water_columns",true);
    opt.end();o.end();
}
void json_be(Json& j, const EnthalpyMeshReceipt& r) {
    JsonObject o(j);
    o.string("model",r.request && r.request->options.allow_pure_water_columns ?
        "enthalpy_mesh_backward_euler_pure_water_v2" : "combined_temperature_enthalpy_mesh_backward_euler_v1");
    o.string("error_scope","canonical_point_fixed_W_area_weighted_L1_joules_v1");
    o.string("curve","exact_raw_endpoint_line_uniform_dyadic_v1");
    o.flag("original_source_accuracy_certified",false);o.flag("ordinary_generation_changed",false);
    o.flag("accepted",r.accepted);o.string("failure_code",r.failure_code);o.string("detail",r.detail);
    o.key("request");if(r.request)json_request(j,*r.request);else j.text("null");
    o.flag("physical_domain_proved",r.physical_domain_proved);
    o.key("physical_temperature_upper_k");if(r.physical_domain_proved)j.number(r.physical_temperature_upper_k);else j.text("null");
    o.key("physical_floor_j_m2");if(r.physical_domain_proved)json_intervals(j,r.physical_floor_j_m2);else j.text("null");
    o.flag("candidate_available",r.candidate_available);
    o.key("candidate_enthalpy_j_m2");if(r.candidate_available)json_doubles(j,r.candidate_enthalpy_j_m2);else j.text("null");
    o.flag("stage_error_available",r.stage_error_available);
    o.key("candidate_field");if(r.stage_error_available)json_field(j,r.candidate_field);else j.text("null");
    o.key("stage_residual_j_m2");if(r.stage_error_available)json_intervals(j,r.stage_residual_j_m2);else j.text("null");
    o.key("stage_error_upper_j");if(r.stage_error_available)j.number(r.stage_error_upper_j);else j.text("null");o.flag("stage_accepted",r.stage_accepted);
    o.key("sweeps");j.array(r.sweeps,[&](const auto& s){JsonObject z(j);z.integer("completed_sweeps",s.completed_sweeps);
        z.integer("scalar_evaluations",s.scalar_evaluations);z.num("stage_error_upper_j",s.stage_error_upper_j);z.end();});
    o.key("leaves");j.array(r.leaves,[&](const auto& l){JsonObject z(j);z.integer("index",l.index);z.flag("complete",l.complete);
        z.key("enthalpy_range_j_m2");if(l.complete)json_intervals(j,l.enthalpy_range_j_m2);else j.text("null");
        z.key("field");if(l.complete)json_field(j,l.field);else j.text("null");
        z.key("residual_integral_j_m2");if(l.complete)json_intervals(j,l.residual_integral_j_m2);else j.text("null");
        z.key("weighted_residual_upper_j");if(l.complete)j.number(l.weighted_residual_upper_j);else j.text("null");z.end();});
    o.flag("endpoint_error_available",r.endpoint_error_available);
    o.key("local_endpoint_error_upper_j");if(r.endpoint_error_available)j.number(r.local_endpoint_error_upper_j);else j.text("null");
    o.key("final_enthalpy_j_m2");if(r.final_enthalpy_j_m2)json_doubles(j,*r.final_enthalpy_j_m2);else j.text("null");
    o.integer("scalar_evaluations",r.scalar_evaluations);o.integer("field_evaluations",r.field_evaluations);
    o.integer("sweeps_started",r.sweeps_started);o.integer("coordinate_solves_started",r.coordinate_solves_started);
    o.integer("leaves_started",r.leaves_started);o.end();
}
void json_polynomials(Json& j,const std::vector<EnthalpyMeshPolynomial>& p) {
    j.array(p,[&](const auto& x){json_intervals(j,x);});
}
void json_sdirk(Json& j,const EnthalpyMeshSdirk2Receipt& r) {
    JsonObject o(j);
    o.string("model",r.request && r.request->options.allow_pure_water_columns ?
        "enthalpy_mesh_represented_sdirk2_pure_water_v2" : "combined_temperature_enthalpy_mesh_represented_sdirk2_v1");
    o.string("curve","exact_raw_endpoint_initial_tangent_quadratic_bernstein_v1");
    o.string("error_scope","canonical_point_fixed_W_area_weighted_L1_joules_v1");
    o.flag("original_source_accuracy_certified",false);o.flag("ordinary_generation_changed",false);
    o.flag("owner_dispatch_available",false);o.flag("exact_irrational_tableau",false);
    o.flag("accepted",r.accepted);o.string("failure_code",r.failure_code);o.string("detail",r.detail);
    o.key("request");if(r.request)json_request(j,*r.request);else j.text("null");
    o.num("gamma",r.gamma);o.num("diagonal_duration_seconds",r.diagonal_duration_seconds);
    o.num("off_diagonal_duration_seconds",r.off_diagonal_duration_seconds);o.flag("tableau_bridges_available",r.tableau_bridges_available);
    o.key("duration_sum_defect_seconds");if(r.tableau_bridges_available)json_interval(j,r.duration_sum_defect_seconds);else j.text("null");
    o.key("second_order_coefficient_defect");if(r.tableau_bridges_available)json_interval(j,r.second_order_coefficient_defect);else j.text("null");
    o.key("initial_heating_w_m2");json_doubles(j,r.initial_heating_w_m2);
    o.key("first_stage_heating_w_m2");json_doubles(j,r.first_stage_heating_w_m2);
    o.key("second_stage_base_j_m2");json_doubles(j,r.second_stage_base_j_m2);
    o.key("second_stage_base_defect_j_m2");json_intervals(j,r.second_stage_base_defect_j_m2);
    o.key("first_stage");if(r.first_stage)json_be(j,*r.first_stage);else j.text("null");
    o.key("second_stage");if(r.second_stage)json_be(j,*r.second_stage);else j.text("null");
    o.flag("physical_curve_proved",r.physical_curve_proved);
    o.key("leaves");j.array(r.leaves,[&](const auto& l){JsonObject z(j);z.integer("index",l.index);z.flag("complete",l.complete);
        z.key("enthalpy");json_polynomials(j,l.enthalpy);z.key("temperature");json_polynomials(j,l.temperature);
        z.key("temperature_branch");j.array(l.temperature_branch,[&](const auto& x){j.quote(x);});
        z.key("residual");if(l.complete)json_polynomials(j,l.residual);else j.text("null");
        z.key("absolute_residual_integral_upper_j_m2");if(l.complete)json_doubles(j,l.absolute_residual_integral_upper_j_m2);else j.text("null");
        z.key("weighted_residual_upper_j");if(l.complete)j.number(l.weighted_residual_upper_j);else j.text("null");z.end();});
    o.flag("endpoint_error_available",r.endpoint_error_available);
    o.key("local_endpoint_error_upper_j");if(r.endpoint_error_available)j.number(r.local_endpoint_error_upper_j);else j.text("null");
    o.key("final_enthalpy_j_m2");if(r.final_enthalpy_j_m2)json_doubles(j,*r.final_enthalpy_j_m2);else j.text("null");
    o.integer("scalar_evaluations",r.scalar_evaluations);o.integer("field_evaluations",r.field_evaluations);
    o.integer("stage_calls_started",r.stage_calls_started);o.integer("sweeps_started",r.sweeps_started);
    o.integer("coordinate_solves_started",r.coordinate_solves_started);o.integer("backward_euler_leaves_started",r.backward_euler_leaves_started);
    o.integer("certificate_leaves_started",r.certificate_leaves_started);o.end();
}
} // namespace

EnthalpyMeshProofCodecError::EnthalpyMeshProofCodecError(std::string c,std::string detail)
    : std::runtime_error(c+": "+detail), code(std::move(c)) {}
EnthalpyMeshProofCodecSize enthalpy_mesh_proof_codec_size(const EnthalpyMeshSdirk2Receipt& receipt,const Limits& limits) {
    Counter visitor(limits.shape,&limits);sdirk(visitor,receipt);return visitor.size;
}
EnthalpyMeshProofCodecSize enthalpy_mesh_proof_codec_max_size(const Shape& shape) {
    Maximum visitor(shape);EnthalpyMeshSdirk2Receipt empty;sdirk(visitor,empty);return visitor.size;
}
void encode_enthalpy_mesh_proof(const EnthalpyMeshSdirk2Receipt& receipt,const EnthalpyMeshProofSink& sink,const Limits& limits) {
    const auto expected=enthalpy_mesh_proof_codec_size(receipt,limits);
    Output output(sink,expected.frame_bytes);output.write(magic);
    output.unsigned_value(enthalpy_mesh_proof_codec_version,4);output.unsigned_value(1,4);
    output.unsigned_value(expected.frame_bytes-enthalpy_mesh_proof_codec_header_bytes,8);
    Encoder visitor(output,limits);sdirk(visitor,receipt);
    need(visitor.size.frame_bytes==expected.frame_bytes && output.count()==expected.frame_bytes,
         "size_mismatch","encoded proof differs from exact preflight size");output.flush();
}
EnthalpyMeshSdirk2Receipt decode_enthalpy_mesh_proof(const EnthalpyMeshProofSource& source,std::uint64_t extent,const Limits& limits) {
    need(extent>=enthalpy_mesh_proof_codec_header_bytes,"truncated_frame","proof frame has no complete header");
    need(extent<=limits.max_frame_bytes,"frame_cap","declared proof frame exceeds selected cap");
    Input input(source,extent);Decoder visitor(input,limits);
    std::array<std::byte,8> header{};input.read(header);need(header==magic,"unknown_schema","unknown proof frame magic");
    need(input.unsigned_value(4)==enthalpy_mesh_proof_codec_version,"unknown_schema","unknown proof frame version");
    need(input.unsigned_value(4)==1,"unknown_schema","unknown proof record kind");
    need(input.unsigned_value(8)==extent-enthalpy_mesh_proof_codec_header_bytes,"frame_length","proof header length differs from isolated extent");
    EnthalpyMeshSdirk2Receipt receipt;
    try {sdirk(visitor,receipt);} catch(const std::bad_alloc&) {fail("allocation_failure","host allocation refused bounded proof payload");}
    need(input.remaining()==0 && visitor.size.frame_bytes==extent,"trailing_bytes","bytes remain after complete proof receipt");
    return receipt;
}
std::uint64_t enthalpy_mesh_proof_legacy_json_size(const EnthalpyMeshSdirk2Receipt& receipt,const Limits& limits) {
    (void)enthalpy_mesh_proof_codec_size(receipt,limits);Json counter(nullptr,limits.max_legacy_json_bytes);json_sdirk(counter,receipt);return counter.count();
}
void stream_enthalpy_mesh_proof_legacy_json(const EnthalpyMeshSdirk2Receipt& receipt,const EnthalpyMeshProofSink& sink,const Limits& limits) {
    const auto expected=enthalpy_mesh_proof_legacy_json_size(receipt,limits);
    Output output(sink,expected);Json writer(&output,expected);json_sdirk(writer,receipt);
    need(writer.count()==expected,"size_mismatch","legacy JSON differs from exact preflight size");output.flush();
}
void expand_enthalpy_mesh_proof_legacy_json(const EnthalpyMeshProofSource& source,std::uint64_t extent,
    const EnthalpyMeshProofSink& sink,const Limits& limits) {
    const auto receipt=decode_enthalpy_mesh_proof(source,extent,limits);
    stream_enthalpy_mesh_proof_legacy_json(receipt,sink,limits);
}
} // namespace magic_geo::detail
