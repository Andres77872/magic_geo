#pragma once

#include "../constants.hpp"

#include <array>
#include <cstddef>
#include <string>
#include <vector>

namespace magic_geo::detail {

// Operational memory-safety limits for the non-authoritative accounting
// shadow.  They are deliberately far above the measured 4,096-cell reference
// peaks and are not physical material-flux or reservoir-capacity limits.
inline constexpr std::size_t
    CRUST_DRY_ROCK_MAX_SURFACE_PACKETS_PER_OWNER = 1024;
inline constexpr std::size_t
    CRUST_DRY_ROCK_MAX_LIVE_RESERVOIR_PACKETS = 1000000;
inline constexpr std::size_t
    CRUST_DRY_ROCK_MAX_PROXY_TRANSFERS_PER_STEP = 1000000;

// Finite, closed dry-rock bookkeeping that is deliberately separate from the
// scalar-authoritative crust-material shadow.  Origin domain 0 denotes
// material present in the initial surface crust; domain 1 denotes the initial
// numerical upper-mantle exchange reserve.  Neither domain is a claim about
// mineralogy, phase, or a calibrated physical mantle inventory.
struct CrustDryRockPacket {
    int origin_domain_id = 0;
    int origin_kind_id = 0;
    int origin_plate_id = 0;
    double dry_rock_mass_kg = 0.0;
};

struct CrustDryRockPacketTable {
    std::vector<int> owner_offsets;
    std::vector<int> origin_domain_ids;
    std::vector<int> origin_kind_ids;
    std::vector<int> origin_plate_ids;
    std::vector<double> dry_rock_mass_kg;
};

struct CrustDryRockTransferTable {
    std::vector<int> sequence_ids;
    std::vector<int> mechanism_ids;
    std::vector<int> process_reason_ids;
    std::vector<int> cell_ids;
    std::vector<int> fragment_ids;
    std::vector<int> source_reservoir_ids;
    std::vector<int> source_owner_ids;
    std::vector<int> destination_reservoir_ids;
    std::vector<int> destination_owner_ids;
    std::vector<int> origin_domain_ids;
    std::vector<int> origin_kind_ids;
    std::vector<int> origin_plate_ids;
    std::vector<int> physical_basis_resolved;
    std::vector<double> dry_rock_mass_kg;
};

struct CrustDryRockAccountingStep {
    int id = 0;
    int plate_motion_history_id = 0;
    int crust_material_shadow_history_id = 0;
    int erosion_iteration = -1;
    std::string stage;
    int cell_count = 0;
    int plate_count = 0;

    CrustDryRockPacketTable opening_surface_packets;
    CrustDryRockPacketTable transported_surface_packets;
    CrustDryRockPacketTable closing_surface_packets;
    CrustDryRockPacketTable opening_upper_mantle_packets;
    CrustDryRockPacketTable closing_upper_mantle_packets;
    CrustDryRockPacketTable opening_subducted_slab_packets;
    CrustDryRockPacketTable closing_subducted_slab_packets;
    CrustDryRockTransferTable proxy_compensation_transfers;

    std::array<double, CRUST_PROCESS_REASON_COUNT>
        requested_surface_source_mass_kg_by_reason{};
    std::array<double, CRUST_PROCESS_REASON_COUNT>
        requested_surface_sink_mass_kg_by_reason{};
    std::array<double, CRUST_PROCESS_REASON_COUNT>
        fulfilled_surface_source_mass_kg_by_reason{};
    std::array<double, CRUST_PROCESS_REASON_COUNT>
        fulfilled_surface_sink_mass_kg_by_reason{};

    double surface_state_envelope_capacity_kg = 0.0;
    double total_control_volume_area_km2 = 0.0;
    double opening_surface_mass_kg = 0.0;
    double transported_surface_mass_kg = 0.0;
    double closing_surface_mass_kg = 0.0;
    double opening_upper_mantle_mass_kg = 0.0;
    double closing_upper_mantle_mass_kg = 0.0;
    double opening_subducted_slab_mass_kg = 0.0;
    double closing_subducted_slab_mass_kg = 0.0;
    double opening_global_mass_kg = 0.0;
    double closing_global_mass_kg = 0.0;
    double source_to_transport_residual_kg = 0.0;
    double global_accounting_residual_kg = 0.0;
    double capacity_initialization_residual_kg = 0.0;
    double maximum_absolute_origin_closure_residual_kg = 0.0;
    double maximum_absolute_reservoir_transfer_residual_kg = 0.0;
    double closing_scalar_mass_kg = 0.0;
    double closing_scalar_mass_residual_kg = 0.0;
    double maximum_absolute_cell_closing_scalar_mass_residual_kg = 0.0;
    double requested_minus_fulfilled_source_mass_kg = 0.0;
    double requested_minus_fulfilled_sink_mass_kg = 0.0;

    int opening_surface_packet_count = 0;
    int transported_surface_packet_count = 0;
    int closing_surface_packet_count = 0;
    int opening_upper_mantle_packet_count = 0;
    int closing_upper_mantle_packet_count = 0;
    int opening_subducted_slab_packet_count = 0;
    int closing_subducted_slab_packet_count = 0;
    int proxy_compensation_transfer_count = 0;
    int maximum_surface_packet_count_per_owner = 0;
    int maximum_live_reservoir_packet_count = 0;
};

struct CrustDryRockAccountingState {
    std::vector<std::vector<CrustDryRockPacket>> surface_packets_by_cell;
    std::vector<CrustDryRockPacket> upper_mantle_packets;
    std::vector<std::vector<CrustDryRockPacket>>
        subducted_slab_packets_by_plate;
    double surface_state_envelope_capacity_kg = 0.0;
    double total_control_volume_area_km2 = 0.0;
    std::vector<CrustDryRockAccountingStep> history;
};

}  // namespace magic_geo::detail
