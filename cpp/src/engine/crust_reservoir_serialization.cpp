#include "internal.hpp"

namespace magic_geo::detail {

namespace {

constexpr int MASS_PRECISION = std::numeric_limits<double>::max_digits10;

std::string bool_array_json(const std::vector<int>& values) {
    std::string out = "[";
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index > 0) {
            out += ",";
        }
        if (values[index] == 0) {
            out += "false";
        } else if (values[index] == 1) {
            out += "true";
        } else {
            throw std::runtime_error(
                "finite dry-rock accounting boolean column is invalid"
            );
        }
    }
    out += "]";
    return out;
}

std::string packet_table_json(const CrustDryRockPacketTable& table) {
    std::string out = "{";
    bool first = true;
    add_raw(out, first, "owner_offsets", int_array_json(table.owner_offsets));
    add_raw(out, first, "origin_domain_ids",
        int_array_json(table.origin_domain_ids));
    add_raw(out, first, "origin_kind_ids",
        int_array_json(table.origin_kind_ids));
    add_raw(out, first, "origin_plate_ids",
        int_array_json(table.origin_plate_ids));
    add_raw(out, first, "dry_rock_mass_kg",
        double_array_json(table.dry_rock_mass_kg, MASS_PRECISION));
    out += "}";
    return out;
}

std::string transfer_table_json(const CrustDryRockTransferTable& table) {
    std::string out = "{";
    bool first = true;
    add_raw(out, first, "sequence_ids", int_array_json(table.sequence_ids));
    add_raw(out, first, "mechanism_ids", int_array_json(table.mechanism_ids));
    add_raw(out, first, "process_reason_ids",
        int_array_json(table.process_reason_ids));
    add_raw(out, first, "cell_ids", int_array_json(table.cell_ids));
    add_raw(out, first, "fragment_ids", int_array_json(table.fragment_ids));
    add_raw(out, first, "source_reservoir_ids",
        int_array_json(table.source_reservoir_ids));
    add_raw(out, first, "source_owner_ids",
        int_array_json(table.source_owner_ids));
    add_raw(out, first, "destination_reservoir_ids",
        int_array_json(table.destination_reservoir_ids));
    add_raw(out, first, "destination_owner_ids",
        int_array_json(table.destination_owner_ids));
    add_raw(out, first, "origin_domain_ids",
        int_array_json(table.origin_domain_ids));
    add_raw(out, first, "origin_kind_ids",
        int_array_json(table.origin_kind_ids));
    add_raw(out, first, "origin_plate_ids",
        int_array_json(table.origin_plate_ids));
    add_raw(out, first, "physical_basis_resolved",
        bool_array_json(table.physical_basis_resolved));
    add_raw(out, first, "dry_rock_mass_kg",
        double_array_json(table.dry_rock_mass_kg, MASS_PRECISION));
    out += "}";
    return out;
}

std::string reason_records_json(const CrustDryRockAccountingStep& step) {
    std::string out = "[";
    for (int reason = 0; reason < CRUST_PROCESS_REASON_COUNT; ++reason) {
        if (reason > 0) {
            out += ",";
        }
        out += "{";
        bool first = true;
        const std::size_t index = static_cast<std::size_t>(reason);
        add_int(out, first, "process_reason_id", reason);
        add_str(out, first, "process_reason", CRUST_PROCESS_REASON_NAMES[reason]);
        add_double(out, first, "requested_surface_source_mass_kg",
            step.requested_surface_source_mass_kg_by_reason[index],
            MASS_PRECISION);
        add_double(out, first, "requested_surface_sink_mass_kg",
            step.requested_surface_sink_mass_kg_by_reason[index],
            MASS_PRECISION);
        add_double(out, first, "fulfilled_surface_source_mass_kg",
            step.fulfilled_surface_source_mass_kg_by_reason[index],
            MASS_PRECISION);
        add_double(out, first, "fulfilled_surface_sink_mass_kg",
            step.fulfilled_surface_sink_mass_kg_by_reason[index],
            MASS_PRECISION);
        add_bool(out, first, "physical_source_sink_resolved", false);
        out += "}";
    }
    out += "]";
    return out;
}

}  // namespace

std::string crust_dry_rock_accounting_model_json() {
    std::string out = "{";
    bool first = true;
    add_str(out, first, "model_type",
        "finite_three_reservoir_dry_rock_accounting_v1");
    add_str(out, first, "mode", "finite_accounting_shadow");
    add_str(out, first, "mass_unit", "kg");
    add_str(out, first, "accounting_scope",
        "surface_basement_crust_upper_mantle_exchange_and_plate_resolved_subducted_slab");
    add_raw(out, first, "reservoir_order",
        "[\"surface_basement_crust\",\"upper_mantle_exchange\",\"subducted_slab\"]");
    add_raw(out, first, "origin_domain_order",
        "[\"initial_surface_crust\",\"initial_upper_mantle_exchange_reserve\"]");
    add_raw(out, first, "packet_key_fields",
        "[\"origin_domain_id\",\"origin_kind_id\",\"origin_plate_id\"]");
    add_str(out, first, "packet_sort_order",
        "origin_domain_id_then_origin_kind_id_then_origin_plate_id");
    add_str(out, first, "packet_coalescing_model", "sorted_equal_key_sum_v1");
    add_str(out, first, "surface_transport_model",
        "source_normalized_overlap_with_final_edge_remainder_v1");
    add_str(out, first, "capacity_model", "surface_state_envelope_v1");
    add_str(out, first, "capacity_formula",
        "sum_control_volume_area_km2_times_76_km_times_3.08_g_cm3_times_1e12");
    add_double(out, first, "capacity_maximum_surface_thickness_km",
        76.0, MASS_PRECISION);
    add_double(out, first, "capacity_maximum_surface_density_g_cm3",
        3.08, MASS_PRECISION);
    add_bool(out, first, "capacity_geophysically_calibrated", false);
    add_str(out, first, "capacity_semantics",
        "finite_numerical_surface_state_envelope_not_an_estimate_of_upper_mantle_mass");
    add_str(out, first, "operational_safety_limit_model",
        "incremental_fail_closed_packet_and_transfer_memory_caps_v1");
    add_u64(out, first, "maximum_surface_packets_per_owner",
        CRUST_DRY_ROCK_MAX_SURFACE_PACKETS_PER_OWNER);
    add_u64(out, first, "maximum_live_reservoir_packets",
        CRUST_DRY_ROCK_MAX_LIVE_RESERVOIR_PACKETS);
    add_u64(out, first, "maximum_proxy_transfers_per_step",
        CRUST_DRY_ROCK_MAX_PROXY_TRANSFERS_PER_STEP);
    add_bool(out, first, "operational_safety_limits_enforced_incrementally",
        true);
    add_bool(out, first, "operational_safety_limits_are_physical_flux_limits",
        false);
    add_str(out, first, "operational_safety_limit_semantics",
        "numerical_memory_safety_limits_not_physical_flux_or_reservoir_capacity_limits");
    add_str(out, first, "proxy_transaction_order",
        "process_reason_then_all_surface_sinks_by_ascending_cell_and_origin_key_then_all_surface_sources_by_ascending_cell_and_origin_key");
    add_str(out, first, "proxy_transfer_mechanism",
        "legacy_rule_mass_compensation_v1");
    add_str(out, first, "mantle_withdrawal_model",
        "initial_exchange_reserve_first_then_largest_packet_lowest_key_tie_break_v1");
    add_str(out, first, "mantle_exchange_topology",
        "single_global_packet_pool_shared_by_all_cells_without_spatial_coordinates_v1");
    add_bool(out, first, "instantaneous_global_mantle_mixing_assumed", true);
    add_bool(out, first, "mantle_origin_packets_homogenized", false);
    add_bool(out, first, "mantle_spatial_transport_resolved", false);
    add_str(out, first, "surface_sink_model",
        "proportional_packets_with_remainder_to_largest_packet_lowest_key_tie_break");
    add_str(out, first, "exact_exhaustion_semantics",
        "empty_reservoir_valid_and_reseed_requires_a_later_explicit_transfer");
    add_str(out, first, "insufficient_exchange_semantics",
        "fail_closed_without_publishing_partial_accounting_state");
    add_str(out, first, "subducted_slab_owner_semantics",
        "subducting_source_plate_id");
    add_str(out, first, "subducted_slab_phase_2_state",
        "plate_resolved_empty_reservoir_no_transfer_mechanism_enabled");
    add_str(out, first, "phase_s_request_source",
        "crust_material_shadow_history_unresolved_adjustments_replayed_as_finite_proxy_compensations");
    add_bool(out, first, "finite_three_reservoir_accounting_present", true);
    add_bool(out, first, "closed_three_reservoir_dry_rock_accounting", true);
    add_bool(out, first, "per_origin_accounting_closed", true);
    add_bool(out, first, "finite_exchange_inventory_enforced", true);
    add_bool(out, first, "legacy_proxy_compensations_exposed", true);
    add_bool(out, first, "plate_resolved_slab_accounting_state_present", true);
    add_bool(out, first, "authoritative_for_cell_state", false);
    add_bool(out, first, "physical_source_sink_resolved", false);
    add_bool(out, first, "material_provenance_resolved", false);
    add_bool(out, first, "upper_mantle_exchange_reservoir_resolved", false);
    add_bool(out, first, "subducted_slab_reservoir_resolved", false);
    add_bool(out, first, "global_crust_cycle_mass_conservation_resolved", false);
    add_bool(out, first, "solid_volume_resolved", false);
    add_bool(out, first, "phase_resolved", false);
    add_bool(out, first, "mass_weighted_age_resolved", false);
    add_bool(out, first, "sediment_coupled", false);
    add_bool(out, first, "coverage_membership_fate_resolved", false);
    add_bool(out, first, "subduction_polarity_resolved", false);
    out += "}";
    return out;
}

std::string crust_dry_rock_accounting_history_json(
    const std::vector<CrustDryRockAccountingStep>& history
) {
    std::string out = "[";
    bool first_step = true;
    for (const CrustDryRockAccountingStep& step : history) {
        comma(out, first_step);
        out += "{";
        bool first = true;
        add_int(out, first, "id", step.id);
        add_int(out, first, "plate_motion_history_id",
            step.plate_motion_history_id);
        add_int(out, first, "crust_material_shadow_history_id",
            step.crust_material_shadow_history_id);
        add_str(out, first, "stage", step.stage);
        add_int(out, first, "erosion_iteration", step.erosion_iteration);
        add_int(out, first, "cell_count", step.cell_count);
        add_int(out, first, "plate_count", step.plate_count);
        add_raw(out, first, "opening_surface_packets",
            packet_table_json(step.opening_surface_packets));
        add_raw(out, first, "transported_surface_packets",
            packet_table_json(step.transported_surface_packets));
        add_raw(out, first, "closing_surface_packets",
            packet_table_json(step.closing_surface_packets));
        add_raw(out, first, "opening_upper_mantle_packets",
            packet_table_json(step.opening_upper_mantle_packets));
        add_raw(out, first, "closing_upper_mantle_packets",
            packet_table_json(step.closing_upper_mantle_packets));
        add_raw(out, first, "opening_subducted_slab_packets",
            packet_table_json(step.opening_subducted_slab_packets));
        add_raw(out, first, "closing_subducted_slab_packets",
            packet_table_json(step.closing_subducted_slab_packets));
        add_raw(out, first, "proxy_compensation_transfers",
            transfer_table_json(step.proxy_compensation_transfers));
        add_raw(out, first, "ordered_reason_transactions",
            reason_records_json(step));
        add_double(out, first, "surface_state_envelope_capacity_kg",
            step.surface_state_envelope_capacity_kg, MASS_PRECISION);
        add_double(out, first, "total_control_volume_area_km2",
            step.total_control_volume_area_km2, MASS_PRECISION);
        add_double(out, first, "opening_surface_mass_kg",
            step.opening_surface_mass_kg, MASS_PRECISION);
        add_double(out, first, "transported_surface_mass_kg",
            step.transported_surface_mass_kg, MASS_PRECISION);
        add_double(out, first, "closing_surface_mass_kg",
            step.closing_surface_mass_kg, MASS_PRECISION);
        add_double(out, first, "opening_upper_mantle_mass_kg",
            step.opening_upper_mantle_mass_kg, MASS_PRECISION);
        add_double(out, first, "closing_upper_mantle_mass_kg",
            step.closing_upper_mantle_mass_kg, MASS_PRECISION);
        add_double(out, first, "opening_subducted_slab_mass_kg",
            step.opening_subducted_slab_mass_kg, MASS_PRECISION);
        add_double(out, first, "closing_subducted_slab_mass_kg",
            step.closing_subducted_slab_mass_kg, MASS_PRECISION);
        add_double(out, first, "opening_global_mass_kg",
            step.opening_global_mass_kg, MASS_PRECISION);
        add_double(out, first, "closing_global_mass_kg",
            step.closing_global_mass_kg, MASS_PRECISION);
        add_double(out, first, "source_to_transport_residual_kg",
            step.source_to_transport_residual_kg, MASS_PRECISION);
        add_double(out, first, "global_accounting_residual_kg",
            step.global_accounting_residual_kg, MASS_PRECISION);
        add_double(out, first, "capacity_initialization_residual_kg",
            step.capacity_initialization_residual_kg, MASS_PRECISION);
        add_double(out, first, "maximum_absolute_origin_closure_residual_kg",
            step.maximum_absolute_origin_closure_residual_kg, MASS_PRECISION);
        add_double(out, first,
            "maximum_absolute_reservoir_transfer_residual_kg",
            step.maximum_absolute_reservoir_transfer_residual_kg,
            MASS_PRECISION);
        add_double(out, first, "closing_scalar_mass_kg",
            step.closing_scalar_mass_kg, MASS_PRECISION);
        add_double(out, first, "closing_scalar_mass_residual_kg",
            step.closing_scalar_mass_residual_kg, MASS_PRECISION);
        add_double(out, first,
            "maximum_absolute_cell_closing_scalar_mass_residual_kg",
            step.maximum_absolute_cell_closing_scalar_mass_residual_kg,
            MASS_PRECISION);
        add_double(out, first,
            "requested_minus_fulfilled_source_mass_kg",
            step.requested_minus_fulfilled_source_mass_kg, MASS_PRECISION);
        add_double(out, first,
            "requested_minus_fulfilled_sink_mass_kg",
            step.requested_minus_fulfilled_sink_mass_kg, MASS_PRECISION);
        add_int(out, first, "opening_surface_packet_count",
            step.opening_surface_packet_count);
        add_int(out, first, "transported_surface_packet_count",
            step.transported_surface_packet_count);
        add_int(out, first, "closing_surface_packet_count",
            step.closing_surface_packet_count);
        add_int(out, first, "opening_upper_mantle_packet_count",
            step.opening_upper_mantle_packet_count);
        add_int(out, first, "closing_upper_mantle_packet_count",
            step.closing_upper_mantle_packet_count);
        add_int(out, first, "opening_subducted_slab_packet_count",
            step.opening_subducted_slab_packet_count);
        add_int(out, first, "closing_subducted_slab_packet_count",
            step.closing_subducted_slab_packet_count);
        add_int(out, first, "proxy_compensation_transfer_count",
            step.proxy_compensation_transfer_count);
        add_int(out, first, "maximum_surface_packet_count_per_owner",
            step.maximum_surface_packet_count_per_owner);
        add_int(out, first, "maximum_live_reservoir_packet_count",
            step.maximum_live_reservoir_packet_count);
        out += "}";
    }
    out += "]";
    return out;
}

std::string summary_with_crust_dry_rock_accounting_json(
    std::string summary,
    const std::vector<CrustDryRockAccountingStep>& history
) {
    if (summary.size() < 2 || summary.front() != '{' || summary.back() != '}') {
        throw std::runtime_error(
            "finite dry-rock accounting summary extension requires a JSON object"
        );
    }
    summary.pop_back();
    bool first = summary.size() == 1;
    std::uint64_t total_surface_packet_count = 0;
    std::uint64_t total_mantle_packet_count = 0;
    std::uint64_t total_slab_packet_count = 0;
    std::uint64_t total_transfer_count = 0;
    std::uint64_t maximum_closing_surface_packet_count = 0;
    std::uint64_t maximum_closing_mantle_packet_count = 0;
    std::uint64_t maximum_transfer_count_per_step = 0;
    std::uint64_t maximum_closing_reservoir_packet_count = 0;
    std::uint64_t maximum_surface_packet_count_per_owner = 0;
    std::uint64_t maximum_live_reservoir_packet_count = 0;
    double cumulative_requested_source_mass = 0.0;
    double cumulative_requested_sink_mass = 0.0;
    double cumulative_fulfilled_source_mass = 0.0;
    double cumulative_fulfilled_sink_mass = 0.0;
    double minimum_closing_mantle_mass = history.empty()
        ? 0.0
        : std::numeric_limits<double>::infinity();
    double maximum_absolute_global_residual = 0.0;
    double maximum_absolute_origin_residual = 0.0;
    double maximum_absolute_reservoir_residual = 0.0;
    double maximum_scalar_relative_residual = 0.0;
    double maximum_closing_slab_mass = 0.0;
    for (const CrustDryRockAccountingStep& step : history) {
        total_surface_packet_count += static_cast<std::uint64_t>(
            step.opening_surface_packet_count +
            step.transported_surface_packet_count +
            step.closing_surface_packet_count
        );
        total_mantle_packet_count += static_cast<std::uint64_t>(
            step.opening_upper_mantle_packet_count +
            step.closing_upper_mantle_packet_count
        );
        total_slab_packet_count += static_cast<std::uint64_t>(
            step.opening_subducted_slab_packet_count +
            step.closing_subducted_slab_packet_count
        );
        total_transfer_count += static_cast<std::uint64_t>(
            step.proxy_compensation_transfer_count
        );
        maximum_closing_surface_packet_count = std::max(
            maximum_closing_surface_packet_count,
            static_cast<std::uint64_t>(step.closing_surface_packet_count)
        );
        maximum_closing_mantle_packet_count = std::max(
            maximum_closing_mantle_packet_count,
            static_cast<std::uint64_t>(
                step.closing_upper_mantle_packet_count
            )
        );
        maximum_transfer_count_per_step = std::max(
            maximum_transfer_count_per_step,
            static_cast<std::uint64_t>(
                step.proxy_compensation_transfer_count
            )
        );
        maximum_closing_reservoir_packet_count = std::max(
            maximum_closing_reservoir_packet_count,
            static_cast<std::uint64_t>(
                step.closing_surface_packet_count +
                step.closing_upper_mantle_packet_count +
                step.closing_subducted_slab_packet_count
            )
        );
        maximum_surface_packet_count_per_owner = std::max(
            maximum_surface_packet_count_per_owner,
            static_cast<std::uint64_t>(
                step.maximum_surface_packet_count_per_owner
            )
        );
        maximum_live_reservoir_packet_count = std::max(
            maximum_live_reservoir_packet_count,
            static_cast<std::uint64_t>(
                step.maximum_live_reservoir_packet_count
            )
        );
        for (int reason = 0; reason < CRUST_PROCESS_REASON_COUNT; ++reason) {
            const std::size_t index = static_cast<std::size_t>(reason);
            cumulative_requested_source_mass +=
                step.requested_surface_source_mass_kg_by_reason[index];
            cumulative_requested_sink_mass +=
                step.requested_surface_sink_mass_kg_by_reason[index];
            cumulative_fulfilled_source_mass +=
                step.fulfilled_surface_source_mass_kg_by_reason[index];
            cumulative_fulfilled_sink_mass +=
                step.fulfilled_surface_sink_mass_kg_by_reason[index];
        }
        minimum_closing_mantle_mass = std::min(
            minimum_closing_mantle_mass,
            step.closing_upper_mantle_mass_kg
        );
        maximum_closing_slab_mass = std::max(
            maximum_closing_slab_mass,
            step.closing_subducted_slab_mass_kg
        );
        maximum_absolute_global_residual = std::max(
            maximum_absolute_global_residual,
            std::abs(step.global_accounting_residual_kg)
        );
        maximum_absolute_origin_residual = std::max(
            maximum_absolute_origin_residual,
            std::abs(step.maximum_absolute_origin_closure_residual_kg)
        );
        maximum_absolute_reservoir_residual = std::max(
            maximum_absolute_reservoir_residual,
            std::abs(step.maximum_absolute_reservoir_transfer_residual_kg)
        );
        maximum_scalar_relative_residual = std::max(
            maximum_scalar_relative_residual,
            std::abs(step.closing_scalar_mass_residual_kg) /
                std::max(1.0, std::abs(step.closing_scalar_mass_kg))
        );
    }
    add_u64(summary, first, "crust_dry_rock_accounting_history_step_count",
        static_cast<std::uint64_t>(history.size()));
    add_u64(summary, first, "total_crust_dry_rock_surface_packet_count",
        total_surface_packet_count);
    add_u64(summary, first, "total_crust_dry_rock_upper_mantle_packet_count",
        total_mantle_packet_count);
    add_u64(summary, first, "total_crust_dry_rock_subducted_slab_packet_count",
        total_slab_packet_count);
    add_u64(summary, first, "total_crust_dry_rock_proxy_transfer_count",
        total_transfer_count);
    add_u64(summary, first,
        "maximum_crust_dry_rock_closing_surface_packet_count_per_step",
        maximum_closing_surface_packet_count);
    add_u64(summary, first,
        "maximum_crust_dry_rock_closing_upper_mantle_packet_count_per_step",
        maximum_closing_mantle_packet_count);
    add_u64(summary, first,
        "maximum_crust_dry_rock_proxy_transfer_count_per_step",
        maximum_transfer_count_per_step);
    add_u64(summary, first,
        "maximum_crust_dry_rock_closing_reservoir_packet_count_per_step",
        maximum_closing_reservoir_packet_count);
    add_u64(summary, first,
        "maximum_crust_dry_rock_surface_packet_count_per_owner",
        maximum_surface_packet_count_per_owner);
    add_u64(summary, first,
        "maximum_crust_dry_rock_live_reservoir_packet_count_per_step",
        maximum_live_reservoir_packet_count);
    add_double(summary, first,
        "cumulative_crust_dry_rock_requested_surface_source_mass_kg",
        cumulative_requested_source_mass, MASS_PRECISION);
    add_double(summary, first,
        "cumulative_crust_dry_rock_requested_surface_sink_mass_kg",
        cumulative_requested_sink_mass, MASS_PRECISION);
    add_double(summary, first,
        "cumulative_crust_dry_rock_fulfilled_surface_source_mass_kg",
        cumulative_fulfilled_source_mass, MASS_PRECISION);
    add_double(summary, first,
        "cumulative_crust_dry_rock_fulfilled_surface_sink_mass_kg",
        cumulative_fulfilled_sink_mass, MASS_PRECISION);
    add_double(summary, first,
        "minimum_crust_dry_rock_closing_upper_mantle_mass_kg",
        history.empty() ? 0.0 : minimum_closing_mantle_mass,
        MASS_PRECISION);
    add_double(summary, first,
        "maximum_crust_dry_rock_closing_subducted_slab_mass_kg",
        maximum_closing_slab_mass, MASS_PRECISION);
    add_double(summary, first,
        "maximum_absolute_crust_dry_rock_global_accounting_residual_kg",
        maximum_absolute_global_residual, MASS_PRECISION);
    add_double(summary, first,
        "maximum_absolute_crust_dry_rock_origin_closure_residual_kg",
        maximum_absolute_origin_residual, MASS_PRECISION);
    add_double(summary, first,
        "maximum_absolute_crust_dry_rock_reservoir_transfer_residual_kg",
        maximum_absolute_reservoir_residual, MASS_PRECISION);
    add_double(summary, first,
        "maximum_crust_dry_rock_closing_scalar_relative_residual",
        maximum_scalar_relative_residual, MASS_PRECISION);
    summary += "}";
    return summary;
}

}  // namespace magic_geo::detail
