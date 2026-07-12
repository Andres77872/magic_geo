#include "engine/internal.hpp"

#include <iostream>

namespace {

using namespace magic_geo::detail;

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << "check failed at line " << __LINE__ << ": "          \
                      << #condition << '\n';                                    \
            return false;                                                       \
        }                                                                       \
    } while (false)

constexpr double MASS_FACTOR = 1.0e12;

Cell one_cell(double mass_kg) {
    Cell cell;
    cell.id = 0;
    cell.area_km2 = 1.0;
    cell.plate_id = 0;
    cell.crust_type = 0;
    cell.crust_thickness_km = mass_kg / MASS_FACTOR;
    cell.crust_density = 1.0;
    return cell;
}

CrustTransportPlan identity_plan() {
    CrustTransportPlan plan;
    plan.destination_offsets = {0, 1};
    plan.source_cell_ids = {0};
    plan.overlap_area_km2 = {1.0};
    return plan;
}

CrustMaterialShadowPacketTable shadow_packets(double mass_kg) {
    CrustMaterialShadowPacketTable table;
    table.cell_offsets = mass_kg > 0.0
        ? std::vector<int>{0, 1}
        : std::vector<int>{0, 0};
    if (mass_kg > 0.0) {
        table.origin_kind_ids = {0};
        table.origin_plate_ids = {0};
        table.origin_reason_ids = {-1};
        table.dry_rock_mass_kg = {mass_kg};
    }
    return table;
}

CrustMaterialShadowAdjustmentTable adjustment(
    int reason,
    double mass_kg,
    bool source
) {
    CrustMaterialShadowAdjustmentTable table;
    table.cell_offsets = mass_kg > 0.0
        ? std::vector<int>{0, 1}
        : std::vector<int>{0, 0};
    if (mass_kg > 0.0) {
        table.process_reason_ids = {reason};
        table.origin_kind_ids = {source ? 9 : 0};
        table.origin_plate_ids = {0};
        table.origin_reason_ids = {source ? reason : -1};
        table.dry_rock_mass_kg = {mass_kg};
    }
    return table;
}

CrustMaterialShadowStep shadow_step(
    int id,
    double transported_mass_kg,
    double closing_mass_kg,
    int reason,
    double source_mass_kg,
    double sink_mass_kg
) {
    CrustMaterialShadowStep step;
    step.id = id;
    step.plate_motion_history_id = id;
    step.stage = "manufactured_reservoir_step";
    step.cell_count = 1;
    step.transported_packets = shadow_packets(transported_mass_kg);
    step.closing_packets = shadow_packets(closing_mass_kg);
    step.unresolved_source_adjustments = adjustment(
        reason, source_mass_kg, true
    );
    step.unresolved_sink_adjustments = adjustment(
        reason, sink_mass_kg, false
    );
    step.unresolved_source_mass_kg_by_reason[
        static_cast<std::size_t>(reason)
    ] = source_mass_kg;
    step.unresolved_sink_mass_kg_by_reason[
        static_cast<std::size_t>(reason)
    ] = sink_mass_kg;
    return step;
}

CrustDryRockAccountingState initialized_state(double surface_mass_kg) {
    CrustDryRockAccountingState state;
    initialize_crust_dry_rock_accounting(
        {one_cell(surface_mass_kg)},
        1,
        0,
        0,
        -1,
        "manufactured_initial",
        state
    );
    return state;
}

void replace_one_cell_surface_packets(
    CrustDryRockAccountingState& state,
    std::size_t packet_count
) {
    auto& packets = state.surface_packets_by_cell.front();
    packets.clear();
    CrustDryRockPacketTable table;
    table.owner_offsets = {0, static_cast<int>(packet_count)};
    for (std::size_t index = 0; index < packet_count; ++index) {
        const int kind = static_cast<int>(index / 256);
        const int plate = static_cast<int>(index % 256);
        packets.push_back(CrustDryRockPacket{0, kind, plate, 1.0});
        table.origin_domain_ids.push_back(0);
        table.origin_kind_ids.push_back(kind);
        table.origin_plate_ids.push_back(plate);
        table.dry_rock_mass_kg.push_back(1.0);
    }
    state.history.back().closing_surface_packets = std::move(table);
    state.history.back().closing_surface_packet_count = static_cast<int>(
        packet_count
    );
}

bool exact_mantle_exhaustion_is_closed() {
    constexpr double surface_mass = MASS_FACTOR;
    CrustDryRockAccountingState state = initialized_state(surface_mass);
    CHECK(state.upper_mantle_packets.size() == 1);
    const double mantle_mass =
        state.upper_mantle_packets.front().dry_rock_mass_kg;
    const double closing_mass = surface_mass + mantle_mass;
    std::vector<Cell> cells{one_cell(closing_mass)};
    const CrustMaterialShadowStep step = shadow_step(
        1,
        surface_mass,
        closing_mass,
        CRUST_PROCESS_THICKNESS_BOUND_ENFORCEMENT,
        mantle_mass,
        0.0
    );
    advance_crust_dry_rock_accounting_step(
        cells, 1, identity_plan(), step, state
    );
    CHECK(state.history.size() == 2);
    CHECK(state.upper_mantle_packets.empty());
    CHECK(state.history.back().closing_upper_mantle_mass_kg == 0.0);
    CHECK(state.history.back().global_accounting_residual_kg == 0.0);
    CHECK(state.history.back().requested_minus_fulfilled_source_mass_kg == 0.0);
    return true;
}

bool empty_surface_can_be_explicitly_reseeded() {
    constexpr double surface_mass = MASS_FACTOR;
    CrustDryRockAccountingState state = initialized_state(surface_mass);
    std::vector<Cell> empty_cells{one_cell(0.0)};
    const CrustMaterialShadowStep exhaust = shadow_step(
        1,
        surface_mass,
        0.0,
        CRUST_PROCESS_DIVERGENT_CONTINENTAL_RIFTING,
        0.0,
        surface_mass
    );
    advance_crust_dry_rock_accounting_step(
        empty_cells, 1, identity_plan(), exhaust, state
    );
    CHECK(state.surface_packets_by_cell.front().empty());

    std::vector<Cell> reseeded_cells{one_cell(surface_mass)};
    const CrustMaterialShadowStep reseed = shadow_step(
        2,
        0.0,
        surface_mass,
        CRUST_PROCESS_THICKNESS_BOUND_ENFORCEMENT,
        surface_mass,
        0.0
    );
    advance_crust_dry_rock_accounting_step(
        reseeded_cells, 1, identity_plan(), reseed, state
    );
    CHECK(state.history.size() == 3);
    CHECK(!state.surface_packets_by_cell.front().empty());
    CHECK(
        std::abs(state.history.back().global_accounting_residual_kg) <=
        128.0 * std::numeric_limits<double>::epsilon() *
            state.history.back().opening_global_mass_kg
    );
    CHECK(
        state.history.back().proxy_compensation_transfer_count >= 1
    );
    return true;
}

bool mantle_depletion_does_not_fan_out_returned_origins() {
    constexpr double surface_mass = MASS_FACTOR;
    constexpr double cycle_mass = 0.25 * MASS_FACTOR;
    CrustDryRockAccountingState state = initialized_state(surface_mass);

    std::vector<Cell> after_sink_cells{one_cell(surface_mass - cycle_mass)};
    const CrustMaterialShadowStep sink = shadow_step(
        1,
        surface_mass,
        surface_mass - cycle_mass,
        CRUST_PROCESS_DIVERGENT_CONTINENTAL_RIFTING,
        0.0,
        cycle_mass
    );
    advance_crust_dry_rock_accounting_step(
        after_sink_cells, 1, identity_plan(), sink, state
    );
    CHECK(state.upper_mantle_packets.size() == 2);

    std::vector<Cell> after_source_cells{one_cell(surface_mass)};
    const CrustMaterialShadowStep source = shadow_step(
        2,
        surface_mass - cycle_mass,
        surface_mass,
        CRUST_PROCESS_THICKNESS_BOUND_ENFORCEMENT,
        cycle_mass,
        0.0
    );
    advance_crust_dry_rock_accounting_step(
        after_source_cells, 1, identity_plan(), source, state
    );
    CHECK(state.history.back().proxy_compensation_transfer_count == 1);
    CHECK(state.surface_packets_by_cell.front().size() <= 2);
    CHECK(
        state.history.back().closing_surface_packet_count <=
        state.history.back().opening_surface_packet_count + 1
    );
    return true;
}

bool insufficient_mantle_rejects_without_publishing() {
    constexpr double surface_mass = MASS_FACTOR;
    CrustDryRockAccountingState state = initialized_state(surface_mass);
    const double mantle_mass =
        state.upper_mantle_packets.front().dry_rock_mass_kg;
    const double request = std::nextafter(
        mantle_mass,
        std::numeric_limits<double>::infinity()
    );
    std::vector<Cell> cells{one_cell(surface_mass + request)};
    const CrustMaterialShadowStep step = shadow_step(
        1,
        surface_mass,
        surface_mass + request,
        CRUST_PROCESS_THICKNESS_BOUND_ENFORCEMENT,
        request,
        0.0
    );
    const auto original_surface = state.surface_packets_by_cell;
    const auto original_mantle = state.upper_mantle_packets;
    bool rejected = false;
    try {
        advance_crust_dry_rock_accounting_step(
            cells, 1, identity_plan(), step, state
        );
    } catch (const std::runtime_error&) {
        rejected = true;
    }
    CHECK(rejected);
    CHECK(state.history.size() == 1);
    CHECK(
        state.surface_packets_by_cell.front().front().dry_rock_mass_kg ==
        original_surface.front().front().dry_rock_mass_kg
    );
    CHECK(
        state.upper_mantle_packets.front().dry_rock_mass_kg ==
        original_mantle.front().dry_rock_mass_kg
    );
    return true;
}

bool age_only_reason_mass_is_rejected() {
    constexpr double surface_mass = MASS_FACTOR;
    CrustDryRockAccountingState state = initialized_state(surface_mass);
    constexpr double request = 1.0e6;
    std::vector<Cell> cells{one_cell(surface_mass + request)};
    const CrustMaterialShadowStep step = shadow_step(
        1,
        surface_mass,
        surface_mass + request,
        CRUST_PROCESS_QUIET_OCEANIC_AGING,
        request,
        0.0
    );
    bool rejected = false;
    try {
        advance_crust_dry_rock_accounting_step(
            cells, 1, identity_plan(), step, state
        );
    } catch (const std::runtime_error&) {
        rejected = true;
    }
    CHECK(rejected);
    CHECK(state.history.size() == 1);
    return true;
}

bool surface_owner_cap_rejects_without_publishing() {
    const double surface_mass = static_cast<double>(
        CRUST_DRY_ROCK_MAX_SURFACE_PACKETS_PER_OWNER
    );
    CrustDryRockAccountingState state;
    initialize_crust_dry_rock_accounting(
        {one_cell(surface_mass)},
        256,
        0,
        0,
        -1,
        "manufactured_cap_initial",
        state
    );
    replace_one_cell_surface_packets(
        state,
        CRUST_DRY_ROCK_MAX_SURFACE_PACKETS_PER_OWNER
    );
    const auto original_surface = state.surface_packets_by_cell;
    const auto original_mantle = state.upper_mantle_packets;
    const auto original_history_size = state.history.size();
    const CrustMaterialShadowStep step = shadow_step(
        1,
        surface_mass,
        surface_mass + 1.0,
        CRUST_PROCESS_THICKNESS_BOUND_ENFORCEMENT,
        1.0,
        0.0
    );
    bool rejected = false;
    std::string rejection_message;
    try {
        advance_crust_dry_rock_accounting_step(
            {one_cell(surface_mass + 1.0)},
            256,
            identity_plan(),
            step,
            state
        );
    } catch (const std::runtime_error& error) {
        rejected = true;
        rejection_message = error.what();
    }
    CHECK(rejected);
    CHECK(
        rejection_message.find("surface-owner packet safety limit") !=
        std::string::npos
    );
    CHECK(state.history.size() == original_history_size);
    CHECK(
        state.surface_packets_by_cell.front().size() ==
        original_surface.front().size()
    );
    CHECK(
        state.upper_mantle_packets.front().dry_rock_mass_kg ==
        original_mantle.front().dry_rock_mass_kg
    );
    return true;
}

}  // namespace

int main() {
    if (
        !exact_mantle_exhaustion_is_closed() ||
        !empty_surface_can_be_explicitly_reseeded() ||
        !mantle_depletion_does_not_fan_out_returned_origins() ||
        !insufficient_mantle_rejects_without_publishing() ||
        !age_only_reason_mass_is_rejected() ||
        !surface_owner_cap_rejects_without_publishing()
    ) {
        return 1;
    }
    return 0;
}
