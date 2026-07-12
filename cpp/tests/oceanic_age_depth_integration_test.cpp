#include "magic_geo/native.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

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
        while (end < json.size() && json[end] != ',' && json[end] != '}') {
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

std::vector<std::string> json_arrays(
    const std::string& json,
    const std::string& key
) {
    const std::string token = "\"" + key + "\":";
    std::vector<std::string> arrays;
    std::size_t search = 0;
    while (true) {
        const std::size_t position = json.find(token, search);
        if (position == std::string::npos) {
            break;
        }
        const std::size_t begin = position + token.size();
        if (begin >= json.size() || json[begin] != '[') {
            throw std::runtime_error("expected JSON array: " + key);
        }
        const std::size_t end = json.find(']', begin);
        if (end == std::string::npos) {
            throw std::runtime_error("unterminated JSON array: " + key);
        }
        arrays.push_back(json.substr(begin, end - begin + 1));
        search = end + 1;
    }
    return arrays;
}

std::vector<double> parse_number_array(const std::string& array) {
    if (array.size() < 2 || array.front() != '[' || array.back() != ']') {
        throw std::runtime_error("invalid numeric JSON array");
    }
    std::vector<double> values;
    const char* cursor = array.c_str() + 1;
    const char* const end = array.c_str() + array.size() - 1;
    while (cursor < end) {
        char* parsed_end = nullptr;
        const double value = std::strtod(cursor, &parsed_end);
        if (parsed_end == cursor || !std::isfinite(value)) {
            throw std::runtime_error("invalid finite array number");
        }
        values.push_back(value);
        cursor = parsed_end;
        if (cursor < end) {
            if (*cursor != ',') {
                throw std::runtime_error("invalid numeric array separator");
            }
            ++cursor;
        }
    }
    return values;
}

std::vector<double> json_numbers_for_key(
    const std::string& json,
    const std::string& key
) {
    const std::string token = "\"" + key + "\":";
    std::vector<double> values;
    std::size_t search = 0;
    while (true) {
        const std::size_t position = json.find(token, search);
        if (position == std::string::npos) {
            break;
        }
        const char* begin = json.c_str() + position + token.size();
        char* end = nullptr;
        const double value = std::strtod(begin, &end);
        if (end == begin || !std::isfinite(value)) {
            throw std::runtime_error("invalid keyed JSON number: " + key);
        }
        values.push_back(value);
        search = static_cast<std::size_t>(end - json.c_str());
    }
    return values;
}

std::string generate() {
    magic_geo::Params params;
    params.seed = 18491;
    params.name = "oceanic_age_depth_integration";
    params.cell_count = 128;
    params.neighbor_count = 6;
    params.plate_count = 4;
    params.erosion_iterations = 1;
    params.threads = 1;
    params.include_cells = true;
    params.float_precision = 4;
    magic_geo::ComputeOptions compute;
    compute.compute_backend = 1;
    return magic_geo::generate_geo_world_json(params, compute);
}

bool schema_and_serialized_checkpoints_are_consistent() {
    const std::string world = generate();
    CHECK(world.find("\"error\":") == std::string::npos);
    const std::string model = json_value(world, "oceanic_age_depth_model");
    CHECK(model.find(
        "\"model\":\"continuity_adjusted_parsons_sclater_relative_basement_subsidence_v1\""
    ) != std::string::npos);
    CHECK(model.find(
        "\"authority_scope\":\"relative_oceanic_thermal_subsidence_target_curve_only\""
    ) != std::string::npos);
    CHECK(model.find("\"continuity_at_transition_resolved\":true") !=
        std::string::npos);
    CHECK(model.find(
        "\"derivative_continuity_at_transition_resolved\":false"
    ) != std::string::npos);
    CHECK(model.find(
        "\"authoritative_for_relative_thermal_subsidence_target_curve\":true"
    ) != std::string::npos);
    CHECK(model.find(
        "\"thermal_subsidence_sign_formula\":"
        "\"thermal_subsidence_target_m=-S_m_for_oceanic_like_else_0\""
    ) != std::string::npos);
    const std::vector<double> target_difference_gains = json_numbers_for_key(
        model,
        "thermal_target_difference_gain"
    );
    CHECK(target_difference_gains.size() == 1);
    CHECK(target_difference_gains[0] == 1.0);
    CHECK(model.find(
        "\"thermal_target_difference_tendency_application\":"
        "\"full_target_difference_is_applied_outside_the_bounded_dynamic_"
        "relief_clamp_with_zero_unapplied_equilibrium_residual\""
    ) != std::string::npos);
    CHECK(model.find(
        "\"authoritative_formula_root\":"
        "\"plate_motion_history_crust_overlap_remapped_numeric_state_plus_"
        "same_step_process_deltas_and_step_categorical_state\""
    ) != std::string::npos);
    CHECK(model.find(
        "\"final_cell_crust_numeric_root_semantics\":"
        "\"binary64_round_trip_aliases_cross_checked_against_authoritative_"
        "history_roots\""
    ) != std::string::npos);
    for (const char* false_flag : {
            "absolute_basement_depth_calibrated",
            "physical_crust_creation_age_provenance",
            "ridge_age_distance_consistency",
            "thermal_structure_represented",
            "heat_flow_represented",
            "dynamic_topography_represented",
            "flexure_represented",
            "physical_dynamics_represented",
            "authoritative_for_realized_thermal_relief_component",
            "realized_thermal_relief_state_tracked",
            "thermal_relaxation_timescale_calibrated",
            "unapplied_thermal_tendency_residual_carried_forward",
        }) {
        CHECK(model.find("\"" + std::string(false_flag) + "\":false") !=
            std::string::npos);
    }
    for (const char* true_flag : {
            "unapplied_thermal_equilibrium_residual_zero_by_construction",
            "thermal_contribution_outside_bounded_dynamic_relief_clamp_resolved",
            "thermal_contribution_to_tectonic_elevation_change_replayed",
            "thermal_target_difference_tendency_application_replayed",
        }) {
        CHECK(model.find("\"" + std::string(true_flag) + "\":true") !=
            std::string::npos);
    }

    const std::string initial_age_model = json_value(
        world,
        "initial_oceanic_crust_age_model"
    );
    CHECK(initial_age_model.find(
        "\"model_type\":\"multi_source_nominal_ridge_graph_travel_time_v1\""
    ) != std::string::npos);
    CHECK(initial_age_model.find(
        "\"authoritative_age_field_location\":"
        "\"initial_oceanic_crust_age_ledger.age_ma_by_cell\""
    ) != std::string::npos);
    CHECK(initial_age_model.find("\"procedural_authority\":true") !=
        std::string::npos);
    CHECK(initial_age_model.find(
        "\"physical_seafloor_creation_resolved\":false"
    ) != std::string::npos);
    CHECK(initial_age_model.find(
        "\"seton_2020_age_grid_used_as_generation_input\":false"
    ) != std::string::npos);

    const std::string initial_age_ledger = json_value(
        world,
        "initial_oceanic_crust_age_ledger"
    );
    const std::vector<double> ledger_ages = parse_number_array(
        json_arrays(initial_age_ledger, "age_ma_by_cell").at(0)
    );
    const std::vector<double> ledger_unclamped_ages = parse_number_array(
        json_arrays(
            initial_age_ledger,
            "unclamped_graph_age_ma_by_cell"
        ).at(0)
    );
    const std::vector<double> ledger_statuses = parse_number_array(
        json_arrays(initial_age_ledger, "status_id_by_cell").at(0)
    );
    const std::vector<double> ledger_predecessors = parse_number_array(
        json_arrays(
            initial_age_ledger,
            "predecessor_cell_id_by_cell"
        ).at(0)
    );
    const std::vector<double> ledger_origins = parse_number_array(
        json_arrays(
            initial_age_ledger,
            "origin_ridge_seed_cell_id_by_cell"
        ).at(0)
    );
    const std::vector<double> ledger_cdf = parse_number_array(
        json_arrays(
            initial_age_ledger,
            "area_weighted_cdf_le_threshold"
        ).at(0)
    );
    CHECK(ledger_ages.size() == 128);
    CHECK(ledger_unclamped_ages.size() == ledger_ages.size());
    CHECK(ledger_statuses.size() == ledger_ages.size());
    CHECK(ledger_predecessors.size() == ledger_ages.size());
    CHECK(ledger_origins.size() == ledger_ages.size());
    CHECK(ledger_cdf.size() == 10);
    CHECK(ledger_cdf.back() == 1.0);
    CHECK(std::is_sorted(ledger_cdf.begin(), ledger_cdf.end()));

    const std::string serialized_cells = json_value(world, "cells");
    const std::vector<double> initial_cell_age_aliases = json_numbers_for_key(
        serialized_cells,
        "initial_crust_age_ma"
    );
    CHECK(initial_cell_age_aliases.size() == ledger_ages.size());

    const std::string initial_age_history = json_value(
        world,
        "plate_motion_history"
    );
    const std::vector<std::string> remapped_age_arrays = json_arrays(
        initial_age_history,
        "remapped_crust_age_ma_by_cell"
    );
    CHECK(remapped_age_arrays.size() == 2);
    const std::vector<double> initial_history_age_aliases =
        parse_number_array(remapped_age_arrays.front());
    CHECK(initial_history_age_aliases == initial_cell_age_aliases);
    for (std::size_t cell = 0; cell < ledger_ages.size(); ++cell) {
        const int status = static_cast<int>(ledger_statuses[cell]);
        CHECK(ledger_statuses[cell] == static_cast<double>(status));
        CHECK(status >= 0 && status <= 4);
        if (status == 0) {
            CHECK(ledger_ages[cell] == 0.0);
            CHECK(ledger_unclamped_ages[cell] == -1.0);
            CHECK(ledger_predecessors[cell] == -1.0);
            CHECK(ledger_origins[cell] == -1.0);
            continue;
        }
        CHECK(initial_cell_age_aliases[cell] == ledger_ages[cell]);
        if (status == 1) {
            CHECK(ledger_ages[cell] == 0.0);
            CHECK(ledger_unclamped_ages[cell] == 0.0);
            CHECK(ledger_predecessors[cell] == -1.0);
            CHECK(ledger_origins[cell] == static_cast<double>(cell));
        } else if (status == 2) {
            CHECK(ledger_ages[cell] == ledger_unclamped_ages[cell]);
            CHECK(ledger_predecessors[cell] >= 0.0);
            CHECK(ledger_origins[cell] >= 0.0);
        } else if (status == 3) {
            CHECK(ledger_unclamped_ages[cell] > ledger_ages[cell]);
            CHECK(ledger_predecessors[cell] >= 0.0);
            CHECK(ledger_origins[cell] >= 0.0);
        } else {
            CHECK(ledger_unclamped_ages[cell] == -1.0);
            CHECK(ledger_predecessors[cell] == -1.0);
            CHECK(ledger_origins[cell] == -1.0);
        }
    }

    const std::string history = json_value(world, "plate_motion_history");
    const std::vector<std::string> previous_isostatic_arrays = json_arrays(
        history,
        "previous_local_isostatic_equilibrium_m"
    );
    const std::vector<std::string> post_isostatic_arrays = json_arrays(
        history,
        "post_process_local_isostatic_equilibrium_m"
    );
    const std::vector<std::string> isostatic_change_arrays = json_arrays(
        history,
        "isostatic_equilibrium_change_m"
    );
    const std::vector<std::string> previous_arrays = json_arrays(
        history,
        "previous_local_thermal_subsidence_target_m"
    );
    const std::vector<std::string> post_arrays = json_arrays(
        history,
        "post_process_local_thermal_subsidence_target_m"
    );
    const std::vector<std::string> tendency_arrays = json_arrays(
        history,
        "thermal_target_difference_tendency_m"
    );
    const std::vector<std::string> thermal_change_arrays = json_arrays(
        history,
        "thermal_equilibrium_change_m"
    );
    const std::vector<std::string> unbounded_dynamic_arrays = json_arrays(
        history,
        "unbounded_dynamic_relief_change_m"
    );
    const std::vector<std::string> bounded_dynamic_arrays = json_arrays(
        history,
        "bounded_dynamic_relief_change_m"
    );
    const std::vector<std::string> tectonic_change_arrays = json_arrays(
        history,
        "tectonic_elevation_change_m_by_cell"
    );
    CHECK(previous_arrays.size() == 2);
    CHECK(previous_isostatic_arrays.size() == previous_arrays.size());
    CHECK(post_isostatic_arrays.size() == previous_arrays.size());
    CHECK(isostatic_change_arrays.size() == previous_arrays.size());
    CHECK(post_arrays.size() == previous_arrays.size());
    CHECK(tendency_arrays.size() == previous_arrays.size());
    CHECK(thermal_change_arrays.size() == previous_arrays.size());
    CHECK(unbounded_dynamic_arrays.size() == previous_arrays.size());
    CHECK(bounded_dynamic_arrays.size() == previous_arrays.size());
    CHECK(tectonic_change_arrays.size() == previous_arrays.size());
    bool saw_equilibrium_change_larger_than_dynamic_clamp = false;
    for (std::size_t step = 0; step < previous_arrays.size(); ++step) {
        const std::vector<double> previous_isostatic = parse_number_array(
            previous_isostatic_arrays[step]
        );
        const std::vector<double> post_isostatic = parse_number_array(
            post_isostatic_arrays[step]
        );
        const std::vector<double> isostatic_change = parse_number_array(
            isostatic_change_arrays[step]
        );
        const std::vector<double> previous = parse_number_array(
            previous_arrays[step]
        );
        const std::vector<double> post = parse_number_array(post_arrays[step]);
        const std::vector<double> tendency = parse_number_array(
            tendency_arrays[step]
        );
        const std::vector<double> thermal_change = parse_number_array(
            thermal_change_arrays[step]
        );
        const std::vector<double> unbounded_dynamic = parse_number_array(
            unbounded_dynamic_arrays[step]
        );
        const std::vector<double> bounded_dynamic = parse_number_array(
            bounded_dynamic_arrays[step]
        );
        const std::vector<double> tectonic_change = parse_number_array(
            tectonic_change_arrays[step]
        );
        CHECK(previous.size() == 128);
        CHECK(previous_isostatic.size() == previous.size());
        CHECK(post_isostatic.size() == previous.size());
        CHECK(isostatic_change.size() == previous.size());
        CHECK(post.size() == previous.size());
        CHECK(tendency.size() == previous.size());
        CHECK(thermal_change.size() == previous.size());
        CHECK(unbounded_dynamic.size() == previous.size());
        CHECK(bounded_dynamic.size() == previous.size());
        CHECK(tectonic_change.size() == previous.size());
        for (std::size_t cell = 0; cell < previous.size(); ++cell) {
            CHECK(isostatic_change[cell] ==
                post_isostatic[cell] - previous_isostatic[cell]);
            CHECK(thermal_change[cell] == post[cell] - previous[cell]);
            CHECK(tendency[cell] == thermal_change[cell]);
            CHECK(bounded_dynamic[cell] == std::clamp(
                unbounded_dynamic[cell],
                -180.0,
                220.0
            ));
            CHECK(tectonic_change[cell] ==
                isostatic_change[cell] + thermal_change[cell] +
                    bounded_dynamic[cell]);
            saw_equilibrium_change_larger_than_dynamic_clamp =
                saw_equilibrium_change_larger_than_dynamic_clamp ||
                std::abs(isostatic_change[cell] + thermal_change[cell]) > 220.0;
            if (step == 0) {
                CHECK(previous_isostatic[cell] == post_isostatic[cell]);
                CHECK(isostatic_change[cell] == 0.0);
                CHECK(previous[cell] == post[cell]);
                CHECK(tendency[cell] == 0.0);
                CHECK(unbounded_dynamic[cell] == 0.0);
                CHECK(bounded_dynamic[cell] == 0.0);
                CHECK(tectonic_change[cell] == 0.0);
            } else {
                CHECK(previous_isostatic[cell] ==
                    parse_number_array(post_isostatic_arrays[step - 1])[cell]);
                CHECK(previous[cell] ==
                    parse_number_array(post_arrays[step - 1])[cell]);
            }
        }
    }
    CHECK(saw_equilibrium_change_larger_than_dynamic_clamp);

    const std::string cells = json_value(world, "cells");
    const std::vector<double> final_cell_thermal = json_numbers_for_key(
        cells,
        "thermal_subsidence_target_m"
    );
    const std::vector<double> last_post = parse_number_array(
        post_arrays.back()
    );
    CHECK(final_cell_thermal.size() == 128);
    CHECK(final_cell_thermal == last_post);
    return true;
}

}  // namespace

int main() {
    return schema_and_serialized_checkpoints_are_consistent() ? 0 : 1;
}
