#include "engine/internal.hpp"
#include "magic_geo/native.hpp"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <limits>
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

std::string json_object_value(const std::string& json, const std::string& key) {
    const std::string token = "\"" + key + "\":{";
    const std::size_t position = json.find(token);
    if (position == std::string::npos) {
        throw std::runtime_error("missing JSON object key: " + key);
    }
    return json_value(json.substr(position), key);
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

std::vector<double> json_double_array(
    const std::string& json,
    const std::string& key
) {
    const std::string value = json_value(json, key);
    if (value.size() < 2 || value.front() != '[' || value.back() != ']') {
        throw std::runtime_error("invalid JSON array: " + key);
    }
    std::vector<double> result;
    const char* cursor = value.c_str() + 1;
    const char* const end = value.c_str() + value.size() - 1;
    while (cursor < end) {
        if (*cursor == ',') {
            ++cursor;
            continue;
        }
        char* next = nullptr;
        const double number = std::strtod(cursor, &next);
        if (next == cursor || !std::isfinite(number) || next > end) {
            throw std::runtime_error("invalid JSON array number: " + key);
        }
        result.push_back(number);
        cursor = next;
    }
    return result;
}

std::vector<std::string> json_objects(const std::string& array) {
    if (array.size() < 2 || array.front() != '[' || array.back() != ']') {
        throw std::runtime_error("invalid JSON object array");
    }
    std::vector<std::string> objects;
    bool in_string = false;
    bool escaped = false;
    int depth = 0;
    std::size_t begin = std::string::npos;
    for (std::size_t index = 1; index + 1 < array.size(); ++index) {
        const char value = array[index];
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
        } else if (value == '{') {
            if (depth == 0) {
                begin = index;
            }
            ++depth;
        } else if (value == '}') {
            --depth;
            if (depth < 0 || (depth == 0 && begin == std::string::npos)) {
                throw std::runtime_error("malformed JSON object array");
            }
            if (depth == 0) {
                objects.push_back(array.substr(begin, index - begin + 1));
                begin = std::string::npos;
            }
        }
    }
    if (depth != 0 || in_string) {
        throw std::runtime_error("unterminated JSON object array");
    }
    return objects;
}

bool throws_partition_validation(
    const std::vector<magic_geo::detail::Cell>& cells,
    const std::vector<double>& source,
    const std::vector<double>& alluvium,
    const std::vector<double>& bedrock,
    double alluvium_volume,
    double bedrock_volume
) {
    try {
        magic_geo::detail::validate_sediment_source_partition(
            cells,
            source,
            alluvium,
            bedrock,
            alluvium_volume,
            bedrock_volume,
            "test"
        );
    } catch (const std::runtime_error&) {
        return true;
    }
    return false;
}

double reconstructed_volume(
    const std::vector<magic_geo::detail::Cell>& cells,
    const std::vector<double>& depth_m
) {
    long double volume = 0.0L;
    for (std::size_t index = 0; index < cells.size(); ++index) {
        volume += static_cast<long double>(cells[index].area_km2) *
            static_cast<long double>(depth_m[index]) / 1000.0L;
    }
    return static_cast<double>(volume);
}

bool synthetic_invariants_cover_valid_zero_and_invalid_cases() {
    std::vector<magic_geo::detail::Cell> cells(3);
    cells[0].id = 0;
    cells[0].area_km2 = 10.0;
    cells[1].id = 1;
    cells[1].area_km2 = 25.0;
    cells[2].id = 2;
    cells[2].area_km2 = 40.0;
    const std::vector<double> source = {3.0, 2.0, 0.0};
    const std::vector<double> alluvium = {1.0, 2.0, 0.0};
    const std::vector<double> bedrock = {2.0, 0.0, 0.0};
    const double alluvium_volume = reconstructed_volume(cells, alluvium);
    const double bedrock_volume = reconstructed_volume(cells, bedrock);
    magic_geo::detail::validate_sediment_source_partition(
        cells,
        source,
        alluvium,
        bedrock,
        alluvium_volume,
        bedrock_volume,
        "test"
    );

    const std::vector<double> zero(3, 0.0);
    magic_geo::detail::validate_sediment_source_partition(
        cells, zero, zero, zero, 0.0, 0.0, "zero"
    );
    const std::vector<double> threshold_source = {5.0e-16, 0.0, 0.0};
    const std::vector<double> threshold_bedrock = threshold_source;
    magic_geo::detail::validate_sediment_source_partition(
        cells,
        threshold_source,
        zero,
        threshold_bedrock,
        0.0,
        reconstructed_volume(cells, threshold_bedrock),
        "threshold"
    );

    std::vector<double> invalid = alluvium;
    invalid[0] = -1.0;
    CHECK(throws_partition_validation(
        cells, source, invalid, bedrock, alluvium_volume, bedrock_volume
    ));
    invalid = alluvium;
    invalid[1] = std::numeric_limits<double>::infinity();
    CHECK(throws_partition_validation(
        cells, source, invalid, bedrock, alluvium_volume, bedrock_volume
    ));
    invalid = alluvium;
    invalid.pop_back();
    CHECK(throws_partition_validation(
        cells, source, invalid, bedrock, alluvium_volume, bedrock_volume
    ));
    invalid = bedrock;
    invalid[0] += 0.5;
    CHECK(throws_partition_validation(
        cells, source, alluvium, invalid, alluvium_volume, bedrock_volume
    ));
    CHECK(throws_partition_validation(
        cells, source, alluvium, bedrock, alluvium_volume + 0.01,
        bedrock_volume
    ));
    std::vector<magic_geo::detail::Cell> unlinked = cells;
    unlinked[1].id = 7;
    CHECK(throws_partition_validation(
        unlinked, source, alluvium, bedrock, alluvium_volume, bedrock_volume
    ));
    return true;
}

bool synthetic_interface_transitions_cover_material_and_datum_changes() {
    using magic_geo::detail::Cell;

    Cell zero;
    zero.id = 0;
    zero.elevation_m = 250.0;
    magic_geo::detail::initialize_sediment_interface(
        zero,
        "zero interface test"
    );
    CHECK(zero.bedrock_surface_elevation_m == 250.0);
    CHECK(zero.sediment_thickness_m == 0.0);
    CHECK(zero.elevation_m == 250.0);

    Cell cell;
    cell.id = 0;
    cell.elevation_m = 104.0;
    cell.sediment_thickness_m = 4.0;
    magic_geo::detail::initialize_sediment_interface(
        cell,
        "mixed interface test"
    );
    CHECK(cell.bedrock_surface_elevation_m == 100.0);

    // Pure alluvium entrainment lowers only the mobile layer and surface.
    magic_geo::detail::apply_sediment_interface_material_change(
        cell, 0.0, 0.0, 2.0, 0.0, "alluvium test"
    );
    CHECK(cell.bedrock_surface_elevation_m == 100.0);
    CHECK(cell.sediment_thickness_m == 2.0);
    CHECK(cell.elevation_m == 102.0);

    // Pure bedrock erosion lowers only the bedrock interface and surface.
    magic_geo::detail::apply_sediment_interface_material_change(
        cell, 0.0, 3.0, 0.0, 0.0, "bedrock test"
    );
    CHECK(cell.bedrock_surface_elevation_m == 97.0);
    CHECK(cell.sediment_thickness_m == 2.0);
    CHECK(cell.elevation_m == 99.0);

    // Deposition raises only the mobile layer and derived surface.
    magic_geo::detail::apply_sediment_interface_material_change(
        cell, 0.0, 0.0, 0.0, 5.0, "deposition test"
    );
    CHECK(cell.bedrock_surface_elevation_m == 97.0);
    CHECK(cell.sediment_thickness_m == 7.0);
    CHECK(cell.elevation_m == 104.0);

    // A combined transition represents tectonics plus mixed source material.
    magic_geo::detail::apply_sediment_interface_material_change(
        cell, 10.0, 1.0, 2.0, 3.0, "combined transition test"
    );
    CHECK(cell.bedrock_surface_elevation_m == 106.0);
    CHECK(cell.sediment_thickness_m == 8.0);
    CHECK(cell.elevation_m == 114.0);

    // A sea-level datum change shifts both elevations, never mobile thickness.
    magic_geo::detail::shift_sediment_interface_datum(
        cell, -20.0, "datum test"
    );
    CHECK(cell.bedrock_surface_elevation_m == 86.0);
    CHECK(cell.sediment_thickness_m == 8.0);
    CHECK(cell.elevation_m == 94.0);
    CHECK(
        magic_geo::detail::maximum_sediment_interface_closure_residual_m(
            std::vector<Cell>{zero, cell},
            "interface residual test"
        ) <= 1.0e-12
    );

    Cell invalid = cell;
    invalid.elevation_m += 1.0;
    bool threw = false;
    try {
        magic_geo::detail::validate_sediment_interface(
            invalid,
            "invalid closure test"
        );
    } catch (const std::runtime_error&) {
        threw = true;
    }
    CHECK(threw);

    const double before_over_entrainment_bedrock =
        cell.bedrock_surface_elevation_m;
    const double before_over_entrainment_mobile = cell.sediment_thickness_m;
    const double before_over_entrainment_surface = cell.elevation_m;
    threw = false;
    try {
        magic_geo::detail::apply_sediment_interface_material_change(
            cell, 0.0, 0.0, 9.0, 0.0, "over-entrainment test"
        );
    } catch (const std::runtime_error&) {
        threw = true;
    }
    CHECK(threw);
    CHECK(
        cell.bedrock_surface_elevation_m ==
        before_over_entrainment_bedrock
    );
    CHECK(cell.sediment_thickness_m == before_over_entrainment_mobile);
    CHECK(cell.elevation_m == before_over_entrainment_surface);

    // A late closing-surface overflow must reject without publishing either
    // individually representable canonical operand.
    Cell overflow;
    overflow.id = 0;
    overflow.elevation_m = std::numeric_limits<double>::max();
    overflow.sediment_thickness_m =
        std::numeric_limits<double>::max() / 2.0;
    magic_geo::detail::initialize_sediment_interface(
        overflow,
        "transactional overflow setup"
    );
    const double before_overflow_bedrock =
        overflow.bedrock_surface_elevation_m;
    const double before_overflow_mobile = overflow.sediment_thickness_m;
    const double before_overflow_surface = overflow.elevation_m;
    threw = false;
    try {
        magic_geo::detail::shift_sediment_interface_datum(
            overflow,
            std::numeric_limits<double>::max() / 2.0,
            "transactional overflow test"
        );
    } catch (const std::runtime_error&) {
        threw = true;
    }
    CHECK(threw);
    CHECK(overflow.bedrock_surface_elevation_m == before_overflow_bedrock);
    CHECK(overflow.sediment_thickness_m == before_overflow_mobile);
    CHECK(overflow.elevation_m == before_overflow_surface);
    return true;
}

magic_geo::Params params(int threads) {
    magic_geo::Params value;
    value.seed = 917245;
    value.name = "sediment_partition_audit";
    value.radius_km = 6371.0;
    value.cell_count = 128;
    value.neighbor_count = 6;
    value.plate_count = 4;
    value.erosion_iterations = 2;
    value.threads = threads;
    value.include_cells = true;
    value.float_precision = 8;
    return value;
}

std::string generate(int threads) {
    magic_geo::ComputeOptions compute;
    compute.compute_backend = 1;
    return magic_geo::generate_geo_world_json(params(threads), compute);
}

std::vector<double> cell_areas(const std::string& world) {
    const std::vector<std::string> cells = json_objects(
        json_value(world, "cells")
    );
    std::vector<double> areas;
    areas.reserve(cells.size());
    for (std::size_t cell_id = 0; cell_id < cells.size(); ++cell_id) {
        if (
            static_cast<int>(json_number(cells[cell_id], "id")) !=
            static_cast<int>(cell_id)
        ) {
            throw std::runtime_error("serialized cells are not cell-id indexed");
        }
        areas.push_back(json_number(cells[cell_id], "area_km2"));
    }
    return areas;
}

bool verify_partition_stage(
    const std::string& stage,
    const std::vector<double>& area_km2,
    const char* mechanism
) {
    const int cell_count = static_cast<int>(json_number(stage, "cell_count"));
    CHECK(cell_count == static_cast<int>(area_km2.size()));
    const std::vector<double> source_demand = json_double_array(
        stage, "source_production_depth_m_by_cell"
    );
    const std::vector<double> alluvium = json_double_array(
        stage, "alluvium_entrainment_depth_m_by_cell"
    );
    const std::vector<double> bedrock = json_double_array(
        stage, "bedrock_erosion_depth_m_by_cell"
    );
    CHECK(source_demand.size() == area_km2.size());
    CHECK(alluvium.size() == area_km2.size());
    CHECK(bedrock.size() == area_km2.size());

    long double alluvium_volume = 0.0L;
    long double bedrock_volume = 0.0L;
    for (std::size_t cell_id = 0; cell_id < area_km2.size(); ++cell_id) {
        CHECK(std::isfinite(alluvium[cell_id]));
        CHECK(std::isfinite(bedrock[cell_id]));
        CHECK(std::isfinite(source_demand[cell_id]));
        CHECK(source_demand[cell_id] >= 0.0);
        CHECK(alluvium[cell_id] >= 0.0);
        CHECK(bedrock[cell_id] >= 0.0);
        CHECK(std::abs(
            alluvium[cell_id] + bedrock[cell_id] - source_demand[cell_id]
        ) <= std::max(1.0e-12, std::abs(source_demand[cell_id]) * 1.0e-14));
        alluvium_volume += static_cast<long double>(area_km2[cell_id]) *
            static_cast<long double>(alluvium[cell_id]) / 1000.0L;
        bedrock_volume += static_cast<long double>(area_km2[cell_id]) *
            static_cast<long double>(bedrock[cell_id]) / 1000.0L;
    }
    const double recorded_alluvium = json_number(
        stage, "alluvium_entrainment_volume_km3"
    );
    const double recorded_bedrock = json_number(
        stage, "bedrock_erosion_volume_km3"
    );
    CHECK(std::abs(
        static_cast<double>(alluvium_volume) - recorded_alluvium
    ) <= std::max(1.0e-7, std::abs(recorded_alluvium) * 1.0e-10));
    CHECK(std::abs(
        static_cast<double>(bedrock_volume) - recorded_bedrock
    ) <= std::max(1.0e-7, std::abs(recorded_bedrock) * 1.0e-10));

    std::vector<double> production_depth(area_km2.size(), 0.0);
    const std::string mechanism_name(mechanism);
    if (mechanism_name == "hillslope") {
        for (const std::string& edge : json_objects(json_value(stage, "edges"))) {
            const int source_id = static_cast<int>(
                json_number(edge, "source_cell_id")
            );
            CHECK(source_id >= 0 && source_id < cell_count);
            production_depth[static_cast<std::size_t>(source_id)] +=
                json_number(edge, "source_production_depth_m");
        }
    } else if (mechanism_name == "fluvial") {
        for (const std::string& step :
             json_objects(json_value(stage, "cell_steps"))) {
            const int source_id = static_cast<int>(
                json_number(step, "cell_id")
            );
            const double area = json_number(step, "cell_area_km2");
            CHECK(source_id >= 0 && source_id < cell_count && area > 0.0);
            production_depth[static_cast<std::size_t>(source_id)] =
                json_number(step, "local_source_volume_km3") * 1000.0 / area;
        }
    } else if (mechanism_name == "glacial") {
        for (const std::string& transfer :
             json_objects(json_value(stage, "transfers"))) {
            const int source_id = static_cast<int>(
                json_number(transfer, "source_cell_id")
            );
            CHECK(source_id >= 0 && source_id < cell_count);
            production_depth[static_cast<std::size_t>(source_id)] +=
                json_number(transfer, "source_production_depth_m");
        }
    } else {
        CHECK(false);
    }
    for (std::size_t cell_id = 0; cell_id < area_km2.size(); ++cell_id) {
        CHECK(std::abs(
            source_demand[cell_id] - production_depth[cell_id]
        ) <= std::max(1.0e-7, std::abs(production_depth[cell_id]) * 1.0e-7));
    }
    return true;
}

bool generated_histories_reconstruct_and_are_thread_exact() {
    const std::string one_thread = generate(1);
    const std::string four_threads = generate(4);
    CHECK(one_thread.find("\"error\":") == std::string::npos);
    CHECK(four_threads.find("\"error\":") == std::string::npos);
    CHECK(one_thread.find(
        "\"per_cell_source_partition_audit_present\":true"
    ) != std::string::npos);
    CHECK(one_thread.find(
        "\"source_partition_audit_is_mass_claim\":false"
    ) != std::string::npos);
    CHECK(one_thread.find(
        "\"source_partition_audit_is_provenance_claim\":false"
    ) != std::string::npos);
    const std::string fluvial_model = json_object_value(
        one_thread,
        "fluvial_sediment_routing_model"
    );
    CHECK(fluvial_model.find(
        "\"stage_input_snapshot\":\"complete_cell_hydrology_topology_environment_and_provisional_surface_v1\""
    ) != std::string::npos);
    CHECK(fluvial_model.find(
        "\"stage_input_snapshot_cell_id_indexed\":true"
    ) != std::string::npos);
    CHECK(fluvial_model.find(
        "\"stage_input_snapshot_used_for_replay\":true"
    ) != std::string::npos);

    const std::string interface_model = json_value(
        one_thread,
        "sediment_interface_model"
    );
    CHECK(interface_model.find(
        "\"model_type\":\"explicit_bedrock_surface_mobile_sediment_interface_v1\""
    ) != std::string::npos);
    CHECK(interface_model.find(
        "\"authoritative_interface_geometry\":true"
    ) != std::string::npos);
    CHECK(interface_model.find(
        "\"surface_elevation_is_derived\":true"
    ) != std::string::npos);
    CHECK(interface_model.find("\"dry_rock_mass_resolved\":false") !=
        std::string::npos);
    CHECK(interface_model.find("\"sediment_density_resolved\":false") !=
        std::string::npos);
    CHECK(interface_model.find("\"porosity_resolved\":false") !=
        std::string::npos);
    CHECK(json_number(
        interface_model,
        "maximum_final_closure_residual_m"
    ) <= 1.0e-9);

    const std::string inventory_model = json_object_value(
        one_thread,
        "sediment_inventory_model"
    );
    CHECK(inventory_model.find(
        "\"mass_conserving_semantics\":\"bulk_reference_volume_only_not_dry_rock_mass\""
    ) != std::string::npos);
    CHECK(inventory_model.find("\"dry_rock_mass_resolved\":false") !=
        std::string::npos);

    for (const std::string& cell : json_objects(json_value(one_thread, "cells"))) {
        const double surface = json_number(cell, "elevation_m");
        const double bedrock = json_number(
            cell,
            "bedrock_surface_elevation_m"
        );
        const double mobile = json_number(cell, "sediment_thickness_m");
        CHECK(std::abs(surface - bedrock - mobile) <= 1.0e-5);
    }

    const std::vector<double> areas = cell_areas(one_thread);
    CHECK(areas.size() == 128);
    const std::vector<std::string> hillslope = json_objects(json_value(
        one_thread, "hillslope_sediment_transport_history"
    ));
    const std::vector<std::string> fluvial = json_objects(json_value(
        one_thread, "fluvial_sediment_routing_history"
    ));
    const std::vector<std::string> glacial = json_objects(json_value(
        one_thread, "glacial_sediment_transport_history"
    ));
    CHECK(hillslope.size() == 2);
    CHECK(fluvial.size() == 2);
    CHECK(glacial.size() == 1);
    for (const std::string& stage : hillslope) {
        CHECK(verify_partition_stage(stage, areas, "hillslope"));
    }
    for (const std::string& stage : fluvial) {
        const std::vector<std::string> input_cells = json_objects(
            json_value(stage, "input_cells")
        );
        CHECK(input_cells.size() == areas.size());
        CHECK(static_cast<std::size_t>(json_number(
            stage,
            "input_cell_count"
        )) == areas.size());
        for (std::size_t cell_id = 0; cell_id < input_cells.size(); ++cell_id) {
            CHECK(static_cast<std::size_t>(json_number(
                input_cells[cell_id],
                "cell_id"
            )) == cell_id);
            CHECK(std::abs(
                json_number(input_cells[cell_id], "cell_area_km2") -
                areas[cell_id]
            ) <= 1.0e-8);
        }
        CHECK(verify_partition_stage(stage, areas, "fluvial"));
    }
    CHECK(verify_partition_stage(glacial.front(), areas, "glacial"));

    CHECK(
        json_value(one_thread, "hillslope_sediment_transport_history") ==
        json_value(four_threads, "hillslope_sediment_transport_history")
    );
    CHECK(
        json_value(one_thread, "fluvial_sediment_routing_history") ==
        json_value(four_threads, "fluvial_sediment_routing_history")
    );
    CHECK(
        json_value(one_thread, "glacial_sediment_transport_history") ==
        json_value(four_threads, "glacial_sediment_transport_history")
    );
    CHECK(
        json_value(one_thread, "sediment_interface_model") ==
        json_value(four_threads, "sediment_interface_model")
    );
    return true;
}

}  // namespace

int main() {
    if (
        !synthetic_invariants_cover_valid_zero_and_invalid_cases() ||
        !synthetic_interface_transitions_cover_material_and_datum_changes() ||
        !generated_histories_reconstruct_and_are_thread_exact()
    ) {
        return 1;
    }
    return 0;
}
