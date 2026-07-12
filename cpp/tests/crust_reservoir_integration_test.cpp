#include "magic_geo/native.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << "check failed at line " << __LINE__ << ": "          \
                      << #condition << '\n';                                    \
            return false;                                                       \
        }                                                                       \
    } while (false)

std::string json_value(const std::string& json, const std::string& key) {
    const std::string token = "\"" + key + "\":";
    const std::size_t token_position = json.find(token);
    if (token_position == std::string::npos) {
        throw std::runtime_error("missing JSON key: " + key);
    }
    const std::size_t begin = token_position + token.size();
    if (begin >= json.size()) {
        throw std::runtime_error("truncated JSON value: " + key);
    }
    const char opening = json[begin];
    const char closing = opening == '{' ? '}' : opening == '[' ? ']' : '\0';
    if (closing == '\0') {
        std::size_t end = begin;
        while (
            end < json.size() && json[end] != ',' && json[end] != '}'
        ) {
            ++end;
        }
        return json.substr(begin, end - begin);
    }
    int depth = 0;
    bool in_string = false;
    bool escaped = false;
    for (std::size_t index = begin; index < json.size(); ++index) {
        const char value = json[index];
        if (in_string) {
            if (escaped) {
                escaped = false;
            } else if (value == '\\') {
                escaped = true;
            } else if (value == '"') {
                in_string = false;
            }
            continue;
        }
        if (value == '"') {
            in_string = true;
        } else if (value == opening) {
            ++depth;
        } else if (value == closing) {
            --depth;
            if (depth == 0) {
                return json.substr(begin, index - begin + 1);
            }
        }
    }
    throw std::runtime_error("unterminated JSON value: " + key);
}

double json_number(const std::string& json, const std::string& key) {
    const std::string value = json_value(json, key);
    char* end = nullptr;
    const double number = std::strtod(value.c_str(), &end);
    if (end == value.c_str() || *end != '\0' || !std::isfinite(number)) {
        throw std::runtime_error("invalid JSON number: " + key);
    }
    return number;
}

magic_geo::Params params(int threads, double radius_km, int iterations) {
    magic_geo::Params value;
    value.seed = 917245;
    value.name = "crust_reservoir_integration";
    value.radius_km = radius_km;
    value.cell_count = 128;
    value.neighbor_count = 6;
    value.plate_count = 4;
    value.erosion_iterations = iterations;
    value.threads = threads;
    value.include_cells = false;
    value.float_precision = 6;
    return value;
}

std::string generate(int threads, double radius_km, int iterations) {
    magic_geo::ComputeOptions compute;
    compute.compute_backend = 1;
    return magic_geo::generate_geo_world_json(
        params(threads, radius_km, iterations), compute
    );
}

bool schema_flags_and_empty_slab_are_truthful() {
    const std::string world = generate(1, 6371.0, 1);
    CHECK(world.find("\"error\":") == std::string::npos);
    const std::string model = json_value(
        world, "crust_dry_rock_accounting_model"
    );
    CHECK(model.find(
        "\"model_type\":\"finite_three_reservoir_dry_rock_accounting_v1\""
    ) != std::string::npos);
    CHECK(model.find(
        "\"closed_three_reservoir_dry_rock_accounting\":true"
    ) != std::string::npos);
    CHECK(model.find("\"physical_source_sink_resolved\":false") !=
        std::string::npos);
    CHECK(model.find("\"material_provenance_resolved\":false") !=
        std::string::npos);
    CHECK(model.find("\"subducted_slab_reservoir_resolved\":false") !=
        std::string::npos);
    CHECK(model.find("\"instantaneous_global_mantle_mixing_assumed\":true") !=
        std::string::npos);
    CHECK(model.find("\"maximum_surface_packets_per_owner\":1024") !=
        std::string::npos);
    CHECK(model.find("\"maximum_live_reservoir_packets\":1000000") !=
        std::string::npos);
    CHECK(model.find("\"maximum_proxy_transfers_per_step\":1000000") !=
        std::string::npos);
    CHECK(model.find(
        "\"operational_safety_limits_are_physical_flux_limits\":false"
    ) != std::string::npos);
    CHECK(model.find("\"mantle_origin_packets_homogenized\":false") !=
        std::string::npos);
    CHECK(model.find("\"mantle_spatial_transport_resolved\":false") !=
        std::string::npos);

    const std::string history = json_value(
        world, "crust_dry_rock_accounting_history"
    );
    CHECK(history.find(
        "\"opening_subducted_slab_packets\":{\"owner_offsets\":[0,0,0,0,0]"
    ) != std::string::npos);
    CHECK(history.find("\"closing_subducted_slab_mass_kg\":0") !=
        std::string::npos);
    CHECK(history.find("\"physical_basis_resolved\":[false") !=
        std::string::npos);
    CHECK(world.find(
        "\"maximum_crust_dry_rock_proxy_transfer_count_per_step\":"
    ) != std::string::npos);
    CHECK(world.find(
        "\"maximum_crust_dry_rock_closing_reservoir_packet_count_per_step\":"
    ) != std::string::npos);
    CHECK(world.find(
        "\"maximum_crust_dry_rock_surface_packet_count_per_owner\":"
    ) != std::string::npos);
    CHECK(world.find(
        "\"maximum_crust_dry_rock_live_reservoir_packet_count_per_step\":"
    ) != std::string::npos);
    return true;
}

bool accounting_history_is_thread_exact() {
    const std::string one_thread = generate(1, 6371.0, 2);
    const std::string four_threads = generate(4, 6371.0, 2);
    CHECK(one_thread.find("\"error\":") == std::string::npos);
    CHECK(four_threads.find("\"error\":") == std::string::npos);
    CHECK(
        json_value(one_thread, "crust_dry_rock_accounting_history") ==
        json_value(four_threads, "crust_dry_rock_accounting_history")
    );
    return true;
}

bool capacity_scales_with_surface_area() {
    const std::string small = generate(1, 3200.0, 0);
    const std::string large = generate(1, 6400.0, 0);
    CHECK(small.find("\"error\":") == std::string::npos);
    CHECK(large.find("\"error\":") == std::string::npos);
    const double small_capacity = json_number(
        json_value(small, "crust_dry_rock_accounting_history"),
        "surface_state_envelope_capacity_kg"
    );
    const double large_capacity = json_number(
        json_value(large, "crust_dry_rock_accounting_history"),
        "surface_state_envelope_capacity_kg"
    );
    CHECK(std::abs(large_capacity / small_capacity - 4.0) <= 2.0e-14);
    return true;
}

}  // namespace

int main() {
    if (
        !schema_flags_and_empty_slab_are_truthful() ||
        !accounting_history_is_thread_exact() ||
        !capacity_scales_with_surface_area()
    ) {
        return 1;
    }
    return 0;
}
