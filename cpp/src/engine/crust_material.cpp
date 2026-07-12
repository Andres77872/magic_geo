#include "internal.hpp"

#include <tuple>

namespace magic_geo::detail {

namespace {

constexpr int INITIAL_ORIGIN_REASON_ID = -1;
constexpr int UNRESOLVED_RULE_SOURCE_KIND_ID = 9;
constexpr double DRY_ROCK_MASS_KG_PER_DENSITY_WEIGHTED_KM3 = 1.0e12;

using Packet = CrustMaterialShadowPacket;
using Adjustment = CrustMaterialShadowAdjustment;

auto packet_key(const Packet& packet) {
    return std::tuple{
        packet.origin_kind_id,
        packet.origin_plate_id,
        packet.origin_reason_id,
    };
}

auto adjustment_key(const Adjustment& adjustment) {
    return std::tuple{
        adjustment.process_reason_id,
        adjustment.origin_kind_id,
        adjustment.origin_plate_id,
        adjustment.origin_reason_id,
    };
}

bool packet_key_less(const Packet& left, const Packet& right) {
    return packet_key(left) < packet_key(right);
}

bool packet_key_equal(const Packet& left, const Packet& right) {
    return packet_key(left) == packet_key(right);
}

bool adjustment_key_less(const Adjustment& left, const Adjustment& right) {
    return adjustment_key(left) < adjustment_key(right);
}

bool adjustment_key_equal(const Adjustment& left, const Adjustment& right) {
    return adjustment_key(left) == adjustment_key(right);
}

void validate_packet_key(const Packet& packet) {
    if (packet.origin_kind_id < 0 || packet.origin_kind_id > 9) {
        throw std::runtime_error(
            "crust material shadow packet has an invalid origin kind"
        );
    }
    if (packet.origin_plate_id < 0) {
        throw std::runtime_error(
            "crust material shadow packet has an invalid origin plate"
        );
    }
    if (packet.origin_kind_id == UNRESOLVED_RULE_SOURCE_KIND_ID) {
        if (
            packet.origin_reason_id < 0 ||
            packet.origin_reason_id >= CRUST_PROCESS_REASON_COUNT
        ) {
            throw std::runtime_error(
                "unresolved crust material packet has an invalid origin reason"
            );
        }
    } else if (packet.origin_reason_id != INITIAL_ORIGIN_REASON_ID) {
        throw std::runtime_error(
            "initial crust material packet has a non-initial origin reason"
        );
    }
}

void validate_packet(const Packet& packet) {
    validate_packet_key(packet);
    if (
        !std::isfinite(packet.dry_rock_mass_kg) ||
        packet.dry_rock_mass_kg <= 0.0
    ) {
        throw std::runtime_error(
            "crust material shadow packet mass is nonfinite or nonpositive"
        );
    }
}

void validate_adjustment(const Adjustment& adjustment) {
    if (
        adjustment.process_reason_id < 0 ||
        adjustment.process_reason_id >= CRUST_PROCESS_REASON_COUNT
    ) {
        throw std::runtime_error(
            "crust material shadow adjustment has an invalid process reason"
        );
    }
    validate_packet_key(Packet{
        adjustment.origin_kind_id,
        adjustment.origin_plate_id,
        adjustment.origin_reason_id,
        adjustment.dry_rock_mass_kg,
    });
    if (
        !std::isfinite(adjustment.dry_rock_mass_kg) ||
        adjustment.dry_rock_mass_kg <= 0.0
    ) {
        throw std::runtime_error(
            "crust material shadow adjustment mass is nonfinite or nonpositive"
        );
    }
}

double checked_mass(double area_km2, double thickness_km, double density) {
    if (
        !std::isfinite(area_km2) || area_km2 <= 0.0 ||
        !std::isfinite(thickness_km) || thickness_km < 0.0 ||
        !std::isfinite(density) || density < 0.0
    ) {
        throw std::runtime_error(
            "crust material shadow scalar state is nonfinite or negative "
            "(area_km2=" + std::to_string(area_km2) +
            ", thickness_km=" + std::to_string(thickness_km) +
            ", density_g_cm3=" + std::to_string(density) + ")"
        );
    }
    const double mass = area_km2 * thickness_km * density *
        DRY_ROCK_MASS_KG_PER_DENSITY_WEIGHTED_KM3;
    if (!std::isfinite(mass) || mass < 0.0) {
        throw std::runtime_error(
            "crust material shadow scalar mass is nonfinite or negative"
        );
    }
    return mass;
}

double checked_double(long double value, const char* message) {
    if (
        !std::isfinite(value) ||
        std::abs(value) > static_cast<long double>(
            std::numeric_limits<double>::max()
        )
    ) {
        throw std::runtime_error(message);
    }
    return static_cast<double>(value);
}

long double forward_error_bound(
    long double absolute_term_sum,
    std::size_t arithmetic_term_count
) {
    const long double count = static_cast<long double>(
        std::max<std::size_t>(1, arithmetic_term_count)
    );
    return std::max(
        1.0e-3L,
        128.0L * static_cast<long double>(
            std::numeric_limits<double>::epsilon()
        ) * count * (1.0L + std::abs(absolute_term_sum))
    );
}

void normalize_packets(std::vector<Packet>& packets) {
    packets.erase(
        std::remove_if(
            packets.begin(),
            packets.end(),
            [](const Packet& packet) {
                if (
                    !std::isfinite(packet.dry_rock_mass_kg) ||
                    packet.dry_rock_mass_kg < 0.0
                ) {
                    throw std::runtime_error(
                        "crust material shadow transport produced invalid packet mass"
                    );
                }
                return packet.dry_rock_mass_kg == 0.0;
            }
        ),
        packets.end()
    );
    std::sort(packets.begin(), packets.end(), packet_key_less);
    std::vector<Packet> merged;
    merged.reserve(packets.size());
    for (const Packet& packet : packets) {
        validate_packet(packet);
        if (!merged.empty() && packet_key_equal(merged.back(), packet)) {
            merged.back().dry_rock_mass_kg += packet.dry_rock_mass_kg;
            if (!std::isfinite(merged.back().dry_rock_mass_kg)) {
                throw std::runtime_error(
                    "crust material shadow packet coalescing overflowed"
                );
            }
        } else {
            merged.push_back(packet);
        }
    }
    packets = std::move(merged);
}

void normalize_adjustments(std::vector<Adjustment>& adjustments) {
    adjustments.erase(
        std::remove_if(
            adjustments.begin(),
            adjustments.end(),
            [](const Adjustment& adjustment) {
                if (
                    !std::isfinite(adjustment.dry_rock_mass_kg) ||
                    adjustment.dry_rock_mass_kg < 0.0
                ) {
                    throw std::runtime_error(
                        "crust material shadow produced invalid adjustment mass"
                    );
                }
                return adjustment.dry_rock_mass_kg == 0.0;
            }
        ),
        adjustments.end()
    );
    std::sort(adjustments.begin(), adjustments.end(), adjustment_key_less);
    std::vector<Adjustment> merged;
    merged.reserve(adjustments.size());
    for (const Adjustment& adjustment : adjustments) {
        validate_adjustment(adjustment);
        if (
            !merged.empty() &&
            adjustment_key_equal(merged.back(), adjustment)
        ) {
            merged.back().dry_rock_mass_kg += adjustment.dry_rock_mass_kg;
            if (!std::isfinite(merged.back().dry_rock_mass_kg)) {
                throw std::runtime_error(
                    "crust material shadow adjustment coalescing overflowed"
                );
            }
        } else {
            merged.push_back(adjustment);
        }
    }
    adjustments = std::move(merged);
}

void validate_canonical_packets(const std::vector<Packet>& packets) {
    for (std::size_t index = 0; index < packets.size(); ++index) {
        validate_packet(packets[index]);
        if (
            index > 0 &&
            !packet_key_less(packets[index - 1], packets[index])
        ) {
            throw std::runtime_error(
                "crust material shadow packets are not sorted and unique"
            );
        }
    }
}

CrustMaterialShadowPacketTable flatten_packets(
    const std::vector<std::vector<Packet>>& packets_by_cell
) {
    CrustMaterialShadowPacketTable table;
    table.cell_offsets.reserve(packets_by_cell.size() + 1);
    table.cell_offsets.push_back(0);
    for (const std::vector<Packet>& packets : packets_by_cell) {
        validate_canonical_packets(packets);
        for (const Packet& packet : packets) {
            table.origin_kind_ids.push_back(packet.origin_kind_id);
            table.origin_plate_ids.push_back(packet.origin_plate_id);
            table.origin_reason_ids.push_back(packet.origin_reason_id);
            table.dry_rock_mass_kg.push_back(packet.dry_rock_mass_kg);
        }
        if (
            table.dry_rock_mass_kg.size() >
            static_cast<std::size_t>(std::numeric_limits<int>::max())
        ) {
            throw std::runtime_error(
                "crust material shadow packet table exceeds integer offsets"
            );
        }
        table.cell_offsets.push_back(
            static_cast<int>(table.dry_rock_mass_kg.size())
        );
    }
    return table;
}

CrustMaterialShadowAdjustmentTable flatten_adjustments(
    std::vector<std::vector<Adjustment>>& adjustments_by_cell
) {
    CrustMaterialShadowAdjustmentTable table;
    table.cell_offsets.reserve(adjustments_by_cell.size() + 1);
    table.cell_offsets.push_back(0);
    for (std::vector<Adjustment>& adjustments : adjustments_by_cell) {
        normalize_adjustments(adjustments);
        for (std::size_t index = 0; index < adjustments.size(); ++index) {
            const Adjustment& adjustment = adjustments[index];
            validate_adjustment(adjustment);
            if (
                index > 0 &&
                !adjustment_key_less(adjustments[index - 1], adjustment)
            ) {
                throw std::runtime_error(
                    "crust material shadow adjustments are not sorted and unique"
                );
            }
            table.process_reason_ids.push_back(adjustment.process_reason_id);
            table.origin_kind_ids.push_back(adjustment.origin_kind_id);
            table.origin_plate_ids.push_back(adjustment.origin_plate_id);
            table.origin_reason_ids.push_back(adjustment.origin_reason_id);
            table.dry_rock_mass_kg.push_back(adjustment.dry_rock_mass_kg);
        }
        if (
            table.dry_rock_mass_kg.size() >
            static_cast<std::size_t>(std::numeric_limits<int>::max())
        ) {
            throw std::runtime_error(
                "crust material shadow adjustment table exceeds integer offsets"
            );
        }
        table.cell_offsets.push_back(
            static_cast<int>(table.dry_rock_mass_kg.size())
        );
    }
    return table;
}

CrustMaterialShadowAdjustmentTable empty_adjustment_table(
    std::size_t cell_count
) {
    CrustMaterialShadowAdjustmentTable table;
    table.cell_offsets.assign(cell_count + 1, 0);
    return table;
}

bool packet_tables_equal(
    const CrustMaterialShadowPacketTable& left,
    const CrustMaterialShadowPacketTable& right
) {
    return
        left.cell_offsets == right.cell_offsets &&
        left.origin_kind_ids == right.origin_kind_ids &&
        left.origin_plate_ids == right.origin_plate_ids &&
        left.origin_reason_ids == right.origin_reason_ids &&
        left.dry_rock_mass_kg == right.dry_rock_mass_kg;
}

long double packet_table_mass(
    const CrustMaterialShadowPacketTable& table
) {
    long double total = 0.0L;
    for (double mass : table.dry_rock_mass_kg) {
        if (!std::isfinite(mass) || mass <= 0.0) {
            throw std::runtime_error(
                "crust material shadow packet table contains invalid mass"
            );
        }
        total += static_cast<long double>(mass);
    }
    return total;
}

long double adjustment_table_mass(
    const CrustMaterialShadowAdjustmentTable& table
) {
    long double total = 0.0L;
    for (double mass : table.dry_rock_mass_kg) {
        if (!std::isfinite(mass) || mass <= 0.0) {
            throw std::runtime_error(
                "crust material shadow adjustment table contains invalid mass"
            );
        }
        total += static_cast<long double>(mass);
    }
    return total;
}

long double packet_table_cell_mass(
    const CrustMaterialShadowPacketTable& table,
    std::size_t cell_id
) {
    if (
        cell_id + 1 >= table.cell_offsets.size() ||
        table.cell_offsets[cell_id] < 0 ||
        table.cell_offsets[cell_id + 1] < table.cell_offsets[cell_id] ||
        static_cast<std::size_t>(table.cell_offsets[cell_id + 1]) >
            table.dry_rock_mass_kg.size()
    ) {
        throw std::runtime_error(
            "crust material shadow packet table has malformed cell offsets"
        );
    }
    long double total = 0.0L;
    for (
        int index = table.cell_offsets[cell_id];
        index < table.cell_offsets[cell_id + 1];
        ++index
    ) {
        total += table.dry_rock_mass_kg[static_cast<std::size_t>(index)];
    }
    return total;
}

long double adjustment_table_cell_mass(
    const CrustMaterialShadowAdjustmentTable& table,
    std::size_t cell_id
) {
    if (
        cell_id + 1 >= table.cell_offsets.size() ||
        table.cell_offsets[cell_id] < 0 ||
        table.cell_offsets[cell_id + 1] < table.cell_offsets[cell_id] ||
        static_cast<std::size_t>(table.cell_offsets[cell_id + 1]) >
            table.dry_rock_mass_kg.size()
    ) {
        throw std::runtime_error(
            "crust material shadow adjustment table has malformed cell offsets"
        );
    }
    long double total = 0.0L;
    for (
        int index = table.cell_offsets[cell_id];
        index < table.cell_offsets[cell_id + 1];
        ++index
    ) {
        total += table.dry_rock_mass_kg[static_cast<std::size_t>(index)];
    }
    return total;
}

void merge_packet(std::vector<Packet>& packets, const Packet& addition) {
    validate_packet(addition);
    const auto position = std::lower_bound(
        packets.begin(), packets.end(), addition, packet_key_less
    );
    if (position != packets.end() && packet_key_equal(*position, addition)) {
        position->dry_rock_mass_kg += addition.dry_rock_mass_kg;
        if (!std::isfinite(position->dry_rock_mass_kg)) {
            throw std::runtime_error(
                "crust material shadow rule addition overflowed"
            );
        }
    } else {
        packets.insert(position, addition);
    }
}

void append_adjustment(
    std::vector<Adjustment>& adjustments,
    const Adjustment& addition
) {
    validate_adjustment(addition);
    adjustments.push_back(addition);
}

struct TransportEdge {
    int source_cell_id = 0;
    int destination_cell_id = 0;
    int original_edge_index = 0;
    double overlap_area_km2 = 0.0;
};

}  // namespace

void initialize_crust_material_shadow(
    const std::vector<Cell>& cells,
    int plate_motion_history_id,
    int erosion_iteration,
    const std::string& stage,
    CrustMaterialShadowState& state
) {
    if (
        cells.empty() || state.step_open || !state.history.empty() ||
        !state.surface_packets_by_cell.empty()
    ) {
        throw std::runtime_error(
            "crust material shadow initialization state is malformed"
        );
    }
    if (plate_motion_history_id < 0 || stage.empty()) {
        throw std::runtime_error(
            "crust material shadow initial history linkage is invalid"
        );
    }

    state.surface_packets_by_cell.resize(cells.size());
    for (std::size_t cell_id = 0; cell_id < cells.size(); ++cell_id) {
        const Cell& cell = cells[cell_id];
        if (
            cell.crust_type < 0 || cell.crust_type > 8 ||
            cell.plate_id < 0
        ) {
            throw std::runtime_error(
                "crust material shadow initial provenance key is invalid"
            );
        }
        state.surface_packets_by_cell[cell_id].push_back(Packet{
            cell.crust_type,
            cell.plate_id,
            INITIAL_ORIGIN_REASON_ID,
            checked_mass(
                cell.area_km2,
                cell.crust_thickness_km,
                cell.crust_density
            ),
        });
    }
    state.unresolved_source_adjustments_by_cell.assign(cells.size(), {});
    state.unresolved_sink_adjustments_by_cell.assign(cells.size(), {});

    CrustMaterialShadowStep step;
    step.id = 0;
    step.plate_motion_history_id = plate_motion_history_id;
    step.erosion_iteration = erosion_iteration;
    step.stage = stage;
    step.cell_count = static_cast<int>(cells.size());
    step.opening_packets = flatten_packets(state.surface_packets_by_cell);
    step.transported_packets = step.opening_packets;
    step.closing_packets = step.opening_packets;
    step.unresolved_source_adjustments = empty_adjustment_table(cells.size());
    step.unresolved_sink_adjustments = empty_adjustment_table(cells.size());
    const long double total_mass = packet_table_mass(step.opening_packets);
    step.opening_surface_mass_kg = checked_double(
        total_mass,
        "crust material shadow initial mass overflowed"
    );
    step.transported_surface_mass_kg = step.opening_surface_mass_kg;
    step.closing_surface_mass_kg = step.opening_surface_mass_kg;
    step.closing_scalar_mass_kg = step.opening_surface_mass_kg;
    step.raw_transported_density_weighted_mass_kg =
        step.opening_surface_mass_kg;
    step.opening_packet_count = static_cast<int>(
        step.opening_packets.dry_rock_mass_kg.size()
    );
    step.transported_packet_count = step.opening_packet_count;
    step.closing_packet_count = step.opening_packet_count;
    state.history.push_back(std::move(step));
}

void begin_crust_material_shadow_step(
    const std::vector<Cell>& cells,
    const CrustTransportPlan& transport_plan,
    int plate_motion_history_id,
    int erosion_iteration,
    const std::string& stage,
    CrustMaterialShadowState& state
) {
    const std::size_t cell_count = cells.size();
    if (
        cell_count == 0 || state.step_open || state.history.empty() ||
        state.surface_packets_by_cell.size() != cell_count ||
        plate_motion_history_id != static_cast<int>(state.history.size()) ||
        stage.empty()
    ) {
        throw std::runtime_error(
            "crust material shadow step opening state or linkage is malformed"
        );
    }
    if (
        transport_plan.destination_offsets.size() != cell_count + 1 ||
        transport_plan.destination_offsets.front() != 0 ||
        transport_plan.source_cell_ids.size() !=
            transport_plan.overlap_area_km2.size() ||
        transport_plan.destination_offsets.back() !=
            static_cast<int>(transport_plan.source_cell_ids.size())
    ) {
        throw std::runtime_error(
            "crust material shadow received a malformed transport plan"
        );
    }

    CrustMaterialShadowStep pending;
    pending.id = static_cast<int>(state.history.size());
    pending.plate_motion_history_id = plate_motion_history_id;
    pending.erosion_iteration = erosion_iteration;
    pending.stage = stage;
    pending.cell_count = static_cast<int>(cell_count);
    pending.opening_packets = flatten_packets(state.surface_packets_by_cell);
    if (!packet_tables_equal(
            pending.opening_packets,
            state.history.back().closing_packets
        )) {
        throw std::runtime_error(
            "crust material shadow opening packets do not equal prior closing packets"
        );
    }

    std::vector<TransportEdge> edges;
    edges.reserve(transport_plan.source_cell_ids.size());
    for (std::size_t destination_id = 0;
         destination_id < cell_count;
         ++destination_id) {
        const int begin = transport_plan.destination_offsets[destination_id];
        const int end = transport_plan.destination_offsets[destination_id + 1];
        if (begin < 0 || end < begin || end > static_cast<int>(
                transport_plan.source_cell_ids.size()
            )) {
            throw std::runtime_error(
                "crust material shadow transport offsets are malformed"
            );
        }
        for (int edge_index = begin; edge_index < end; ++edge_index) {
            const int source_id = transport_plan.source_cell_ids[
                static_cast<std::size_t>(edge_index)
            ];
            const double area = transport_plan.overlap_area_km2[
                static_cast<std::size_t>(edge_index)
            ];
            if (
                source_id < 0 ||
                source_id >= static_cast<int>(cell_count) ||
                !std::isfinite(area) || area <= 0.0
            ) {
                throw std::runtime_error(
                    "crust material shadow transport edge is invalid"
                );
            }
            edges.push_back(TransportEdge{
                source_id,
                static_cast<int>(destination_id),
                edge_index,
                area,
            });
        }
    }
    std::sort(edges.begin(), edges.end(), [](const auto& left, const auto& right) {
        return std::tuple{
            left.source_cell_id,
            left.destination_cell_id,
            left.original_edge_index,
        } < std::tuple{
            right.source_cell_id,
            right.destination_cell_id,
            right.original_edge_index,
        };
    });

    std::vector<std::vector<Packet>> transported_by_cell(cell_count);
    std::size_t edge_cursor = 0;
    for (std::size_t source_id = 0; source_id < cell_count; ++source_id) {
        const std::size_t source_edge_begin = edge_cursor;
        double source_overlap_sum = 0.0;
        while (
            edge_cursor < edges.size() &&
            edges[edge_cursor].source_cell_id == static_cast<int>(source_id)
        ) {
            source_overlap_sum += edges[edge_cursor].overlap_area_km2;
            edge_cursor++;
        }
        if (
            edge_cursor == source_edge_begin ||
            !std::isfinite(source_overlap_sum) || source_overlap_sum <= 0.0
        ) {
            throw std::runtime_error(
                "crust material shadow source has no valid outgoing overlap"
            );
        }

        const std::vector<Packet>& source_packets =
            state.surface_packets_by_cell[source_id];
        validate_canonical_packets(source_packets);
        if (source_packets.empty()) {
            throw std::runtime_error(
                "crust material shadow source cell has no material packets"
            );
        }
        for (const Packet& packet : source_packets) {
            double allocated_mass = 0.0;
            for (std::size_t position = source_edge_begin;
                 position < edge_cursor;
                 ++position) {
                const bool last_edge = position + 1 == edge_cursor;
                const double edge_mass = last_edge
                    ? packet.dry_rock_mass_kg - allocated_mass
                    : packet.dry_rock_mass_kg *
                        (edges[position].overlap_area_km2 /
                            source_overlap_sum);
                if (!std::isfinite(edge_mass) || edge_mass < 0.0) {
                    throw std::runtime_error(
                        "crust material shadow edge allocation is invalid"
                    );
                }
                if (edge_mass > 0.0) {
                    Packet contribution = packet;
                    contribution.dry_rock_mass_kg = edge_mass;
                    transported_by_cell[static_cast<std::size_t>(
                        edges[position].destination_cell_id
                    )].push_back(contribution);
                }
                allocated_mass += edge_mass;
                if (!std::isfinite(allocated_mass)) {
                    throw std::runtime_error(
                        "crust material shadow edge allocation overflowed"
                    );
                }
            }
            if (
                std::abs(
                    static_cast<long double>(allocated_mass) -
                    static_cast<long double>(packet.dry_rock_mass_kg)
                ) > forward_error_bound(
                    static_cast<long double>(allocated_mass) +
                        packet.dry_rock_mass_kg,
                    edge_cursor - source_edge_begin + 1
                )
            ) {
                throw std::runtime_error(
                    "crust material shadow source packet allocation exceeded its forward-error bound"
                );
            }
        }
    }
    if (edge_cursor != edges.size()) {
        throw std::runtime_error(
            "crust material shadow transport edge traversal did not close"
        );
    }
    for (std::vector<Packet>& packets : transported_by_cell) {
        normalize_packets(packets);
    }

    pending.transported_packets = flatten_packets(transported_by_cell);
    const long double opening_mass = packet_table_mass(pending.opening_packets);
    const long double transported_mass = packet_table_mass(
        pending.transported_packets
    );
    const long double transport_residual = transported_mass - opening_mass;
    const long double transport_bound = forward_error_bound(
        opening_mass + transported_mass,
        pending.opening_packets.dry_rock_mass_kg.size() +
            pending.transported_packets.dry_rock_mass_kg.size() +
            edges.size()
    );
    if (std::abs(transport_residual) > transport_bound) {
        throw std::runtime_error(
            "crust material shadow normalized transport did not conserve global mass"
        );
    }

    state.surface_packets_by_cell = std::move(transported_by_cell);
    state.unresolved_source_adjustments_by_cell.assign(cell_count, {});
    state.unresolved_sink_adjustments_by_cell.assign(cell_count, {});
    pending.opening_surface_mass_kg = checked_double(
        opening_mass,
        "crust material shadow opening mass overflowed"
    );
    pending.transported_surface_mass_kg = checked_double(
        transported_mass,
        "crust material shadow transported mass overflowed"
    );
    pending.source_to_transport_residual_kg = checked_double(
        transport_residual,
        "crust material shadow transport residual overflowed"
    );
    pending.raw_transported_density_weighted_mass_kg =
        transport_plan.transported_density_weighted_crust_volume *
        DRY_ROCK_MASS_KG_PER_DENSITY_WEIGHTED_KM3;
    if (!std::isfinite(pending.raw_transported_density_weighted_mass_kg)) {
        throw std::runtime_error(
            "crust material shadow raw transported scalar mass is nonfinite"
        );
    }
    pending.shadow_minus_raw_transport_mass_kg = checked_double(
        transported_mass - static_cast<long double>(
            pending.raw_transported_density_weighted_mass_kg
        ),
        "crust material shadow raw transport residual overflowed"
    );
    pending.opening_packet_count = static_cast<int>(
        pending.opening_packets.dry_rock_mass_kg.size()
    );
    pending.transported_packet_count = static_cast<int>(
        pending.transported_packets.dry_rock_mass_kg.size()
    );

    const long double prior_scalar_residual = std::abs(
        static_cast<long double>(state.history.back().post_scalar_mirror_residual_kg)
    );
    const long double geometry_bound =
        prior_scalar_residual +
        4.0L * std::max(
            0.0,
            transport_plan.maximum_source_area_relative_closure_error
        ) * (1.0L + std::max(
            std::abs(opening_mass),
            std::abs(static_cast<long double>(
                pending.raw_transported_density_weighted_mass_kg
            ))
        )) +
        forward_error_bound(
            std::abs(opening_mass) +
                std::abs(static_cast<long double>(
                    pending.raw_transported_density_weighted_mass_kg
                )),
            edges.size() + pending.opening_packets.dry_rock_mass_kg.size()
        );
    if (
        std::abs(static_cast<long double>(
            pending.shadow_minus_raw_transport_mass_kg
        )) > geometry_bound
    ) {
        throw std::runtime_error(
            "crust material shadow/raw transported mass difference exceeded its geometry bound"
        );
    }

    state.pending_step = std::move(pending);
    state.step_open = true;
}

void apply_crust_material_shadow_transition(
    CrustMaterialShadowState& state,
    int cell_id,
    int current_plate_id,
    CrustProcessReason process_reason,
    double area_km2,
    double before_thickness_km,
    double before_density_g_cm3,
    double after_thickness_km,
    double after_density_g_cm3
) {
    if (
        !state.step_open || cell_id < 0 ||
        cell_id >= static_cast<int>(state.surface_packets_by_cell.size()) ||
        current_plate_id < 0 || process_reason < 0 ||
        process_reason >= CRUST_PROCESS_REASON_COUNT
    ) {
        throw std::runtime_error(
            "crust material shadow rule transition linkage is invalid"
        );
    }
    const double before_mass = checked_mass(
        area_km2,
        before_thickness_km,
        before_density_g_cm3
    );
    const double after_mass = checked_mass(
        area_km2,
        after_thickness_km,
        after_density_g_cm3
    );
    const double mass_delta = after_mass - before_mass;
    if (!std::isfinite(mass_delta)) {
        throw std::runtime_error(
            "crust material shadow rule mass delta is nonfinite"
        );
    }
    if (mass_delta == 0.0) {
        return;
    }

    const std::size_t index = static_cast<std::size_t>(cell_id);
    std::vector<Packet>& packets = state.surface_packets_by_cell[index];
    validate_canonical_packets(packets);
    if (mass_delta > 0.0) {
        const Packet addition{
            UNRESOLVED_RULE_SOURCE_KIND_ID,
            current_plate_id,
            static_cast<int>(process_reason),
            mass_delta,
        };
        merge_packet(packets, addition);
        append_adjustment(
            state.unresolved_source_adjustments_by_cell[index],
            Adjustment{
                static_cast<int>(process_reason),
                addition.origin_kind_id,
                addition.origin_plate_id,
                addition.origin_reason_id,
                addition.dry_rock_mass_kg,
            }
        );
        return;
    }

    if (packets.empty()) {
        throw std::runtime_error(
            "crust material shadow rule sink has no material packets"
        );
    }

    const double requested_removal = -mass_delta;
    double current_total = 0.0;
    std::size_t correction_index = 0;
    for (std::size_t packet_index = 0;
         packet_index < packets.size();
         ++packet_index) {
        current_total += packets[packet_index].dry_rock_mass_kg;
        if (
            packet_index == 0 ||
            packets[packet_index].dry_rock_mass_kg >
                packets[correction_index].dry_rock_mass_kg
        ) {
            correction_index = packet_index;
        }
    }
    if (!std::isfinite(current_total) || current_total <= 0.0) {
        throw std::runtime_error(
            "crust material shadow rule target mass is invalid"
        );
    }
    const long double under_removal_bound = forward_error_bound(
        static_cast<long double>(current_total) + requested_removal,
        packets.size() + 2
    );
    if (
        static_cast<long double>(requested_removal) >
        static_cast<long double>(current_total) + under_removal_bound
    ) {
        throw std::runtime_error(
            "crust material shadow rule sink exceeds available surface mass"
        );
    }
    if (requested_removal >= current_total) {
        // Exact exhaustion is valid.  A following ordered rule (normally a
        // thickness/density bound) may explicitly reseed this empty surface
        // row.  A request materially larger than the available shadow mass
        // was rejected by the under-removal check above.
        for (const Packet& packet : packets) {
            append_adjustment(
                state.unresolved_sink_adjustments_by_cell[index],
                Adjustment{
                    static_cast<int>(process_reason),
                    packet.origin_kind_id,
                    packet.origin_plate_id,
                    packet.origin_reason_id,
                    packet.dry_rock_mass_kg,
                }
            );
        }
        packets.clear();
        return;
    }

    std::vector<double> removals(packets.size(), 0.0);
    double provisional_removal = 0.0;
    for (std::size_t packet_index = 0;
         packet_index < packets.size();
         ++packet_index) {
        removals[packet_index] = requested_removal *
            packets[packet_index].dry_rock_mass_kg / current_total;
        provisional_removal += removals[packet_index];
    }
    removals[correction_index] +=
        requested_removal - provisional_removal;

    std::vector<Packet> retained;
    retained.reserve(packets.size());
    for (std::size_t packet_index = 0;
         packet_index < packets.size();
         ++packet_index) {
        const Packet& packet = packets[packet_index];
        const double removal = removals[packet_index];
        if (
            !std::isfinite(removal) || removal < 0.0 ||
            removal > packet.dry_rock_mass_kg
        ) {
            throw std::runtime_error(
                "crust material shadow proportional sink is invalid"
            );
        }
        if (removal > 0.0) {
            append_adjustment(
                state.unresolved_sink_adjustments_by_cell[index],
                Adjustment{
                    static_cast<int>(process_reason),
                    packet.origin_kind_id,
                    packet.origin_plate_id,
                    packet.origin_reason_id,
                    removal,
                }
            );
        }
        Packet remainder = packet;
        remainder.dry_rock_mass_kg -= removal;
        if (!std::isfinite(remainder.dry_rock_mass_kg) ||
            remainder.dry_rock_mass_kg < 0.0) {
            throw std::runtime_error(
                "crust material shadow proportional sink produced negative mass"
            );
        }
        if (remainder.dry_rock_mass_kg > 0.0) {
            retained.push_back(remainder);
        }
    }
    if (retained.empty()) {
        throw std::runtime_error(
            "crust material shadow proportional sink exhausted all packets"
        );
    }
    packets = std::move(retained);
    validate_canonical_packets(packets);
}

void finalize_crust_material_shadow_step(
    const std::vector<Cell>& cells,
    const CrustTransportPlan& transport_plan,
    CrustMaterialShadowState& state
) {
    if (
        !state.step_open || cells.empty() ||
        state.surface_packets_by_cell.size() != cells.size() ||
        state.unresolved_source_adjustments_by_cell.size() != cells.size() ||
        state.unresolved_sink_adjustments_by_cell.size() != cells.size() ||
        state.pending_step.cell_count != static_cast<int>(cells.size()) ||
        state.pending_step.id != static_cast<int>(state.history.size()) ||
        state.pending_step.plate_motion_history_id !=
            static_cast<int>(state.history.size())
    ) {
        throw std::runtime_error(
            "crust material shadow finalization state is malformed"
        );
    }

    CrustMaterialShadowStep& step = state.pending_step;
    step.closing_packets = flatten_packets(state.surface_packets_by_cell);
    step.unresolved_source_adjustments = flatten_adjustments(
        state.unresolved_source_adjustments_by_cell
    );
    step.unresolved_sink_adjustments = flatten_adjustments(
        state.unresolved_sink_adjustments_by_cell
    );

    const long double opening_mass = packet_table_mass(step.opening_packets);
    const long double transported_mass = packet_table_mass(
        step.transported_packets
    );
    const long double source_mass = adjustment_table_mass(
        step.unresolved_source_adjustments
    );
    const long double sink_mass = adjustment_table_mass(
        step.unresolved_sink_adjustments
    );
    const long double closing_mass = packet_table_mass(step.closing_packets);

    long double scalar_closing_mass = 0.0L;
    long double max_abs_cell_scalar_residual = 0.0L;
    long double max_abs_cell_adjustment_residual = 0.0L;
    long double scalar_absolute_terms = 0.0L;
    if (transport_plan.contributor_count_by_cell.size() != cells.size()) {
        throw std::runtime_error(
            "crust material shadow transport contributor diagnostics are malformed"
        );
    }
    const long double prior_max_cell_residual = std::abs(
        static_cast<long double>(
            state.history.back().max_abs_post_scalar_mirror_cell_residual_kg
        )
    );
    const long double geometry_relative_error = std::max(
        0.0,
        transport_plan.maximum_source_area_relative_closure_error
    );
    for (std::size_t cell_id = 0; cell_id < cells.size(); ++cell_id) {
        const Cell& cell = cells[cell_id];
        const long double scalar_cell_mass = checked_mass(
            cell.area_km2,
            cell.crust_thickness_km,
            cell.crust_density
        );
        const long double opening_cell_mass = packet_table_cell_mass(
            step.opening_packets,
            cell_id
        );
        const long double transported_cell_mass = packet_table_cell_mass(
            step.transported_packets,
            cell_id
        );
        const long double source_cell_mass = adjustment_table_cell_mass(
            step.unresolved_source_adjustments,
            cell_id
        );
        const long double sink_cell_mass = adjustment_table_cell_mass(
            step.unresolved_sink_adjustments,
            cell_id
        );
        const long double closing_cell_mass = packet_table_cell_mass(
            step.closing_packets,
            cell_id
        );
        (void)opening_cell_mass;
        scalar_closing_mass += scalar_cell_mass;
        scalar_absolute_terms += std::abs(scalar_cell_mass) +
            std::abs(closing_cell_mass);
        max_abs_cell_scalar_residual = std::max(
            max_abs_cell_scalar_residual,
            std::abs(closing_cell_mass - scalar_cell_mass)
        );
        const std::size_t local_packet_term_count = static_cast<std::size_t>(
            step.closing_packets.cell_offsets[cell_id + 1] -
            step.closing_packets.cell_offsets[cell_id] +
            step.transported_packets.cell_offsets[cell_id + 1] -
            step.transported_packets.cell_offsets[cell_id] +
            step.unresolved_source_adjustments.cell_offsets[cell_id + 1] -
            step.unresolved_source_adjustments.cell_offsets[cell_id] +
            step.unresolved_sink_adjustments.cell_offsets[cell_id + 1] -
            step.unresolved_sink_adjustments.cell_offsets[cell_id] + 6
        );
        const long double local_scalar_absolute_terms =
            std::abs(closing_cell_mass) +
            std::abs(scalar_cell_mass) +
            std::abs(transported_cell_mass) +
            std::abs(source_cell_mass) +
            std::abs(sink_cell_mass);
        const long double local_scalar_mirror_bound =
            prior_max_cell_residual * static_cast<long double>(std::max(
                1,
                transport_plan.contributor_count_by_cell[cell_id]
            )) +
            4.0L * geometry_relative_error *
                (1.0L + local_scalar_absolute_terms) +
            forward_error_bound(
                local_scalar_absolute_terms,
                local_packet_term_count
            );
        if (
            std::abs(closing_cell_mass - scalar_cell_mass) >
            local_scalar_mirror_bound
        ) {
            throw std::runtime_error(
                "crust material shadow cell scalar mirror residual is excessive"
            );
        }
        const long double cell_adjustment_residual =
            closing_cell_mass - transported_cell_mass - source_cell_mass +
            sink_cell_mass;
        max_abs_cell_adjustment_residual = std::max(
            max_abs_cell_adjustment_residual,
            std::abs(cell_adjustment_residual)
        );
        const long double cell_adjustment_bound = forward_error_bound(
            std::abs(closing_cell_mass) +
                std::abs(transported_cell_mass) +
                std::abs(source_cell_mass) +
                std::abs(sink_cell_mass),
            static_cast<std::size_t>(
                step.closing_packets.cell_offsets[cell_id + 1] -
                step.closing_packets.cell_offsets[cell_id] +
                step.transported_packets.cell_offsets[cell_id + 1] -
                step.transported_packets.cell_offsets[cell_id] +
                step.unresolved_source_adjustments.cell_offsets[cell_id + 1] -
                step.unresolved_source_adjustments.cell_offsets[cell_id] +
                step.unresolved_sink_adjustments.cell_offsets[cell_id + 1] -
                step.unresolved_sink_adjustments.cell_offsets[cell_id] + 4
            )
        );
        if (std::abs(cell_adjustment_residual) > cell_adjustment_bound) {
            throw std::runtime_error(
                "crust material shadow cell adjustments did not reconcile"
            );
        }
    }

    step.opening_surface_mass_kg = checked_double(
        opening_mass,
        "crust material shadow opening mass overflowed at finalization"
    );
    step.transported_surface_mass_kg = checked_double(
        transported_mass,
        "crust material shadow transported mass overflowed at finalization"
    );
    step.unresolved_source_mass_kg = checked_double(
        source_mass,
        "crust material shadow source adjustment mass overflowed"
    );
    step.unresolved_sink_mass_kg = checked_double(
        sink_mass,
        "crust material shadow sink adjustment mass overflowed"
    );
    step.closing_surface_mass_kg = checked_double(
        closing_mass,
        "crust material shadow closing mass overflowed"
    );
    step.closing_scalar_mass_kg = checked_double(
        scalar_closing_mass,
        "crust material shadow scalar closing mass overflowed"
    );
    step.source_to_transport_residual_kg = checked_double(
        transported_mass - opening_mass,
        "crust material shadow transport residual overflowed at finalization"
    );
    step.shadow_minus_raw_transport_mass_kg = checked_double(
        transported_mass - static_cast<long double>(
            step.raw_transported_density_weighted_mass_kg
        ),
        "crust material shadow/raw transport residual overflowed at finalization"
    );
    step.post_scalar_mirror_residual_kg = checked_double(
        closing_mass - scalar_closing_mass,
        "crust material shadow scalar mirror residual overflowed"
    );
    step.max_abs_post_scalar_mirror_cell_residual_kg = checked_double(
        max_abs_cell_scalar_residual,
        "crust material shadow maximum cell mirror residual overflowed"
    );
    const long double adjustment_residual =
        closing_mass - transported_mass - source_mass + sink_mass;
    step.ordered_adjustment_reconciliation_residual_kg = checked_double(
        adjustment_residual,
        "crust material shadow adjustment residual overflowed"
    );

    for (std::size_t index = 0;
         index < step.unresolved_source_adjustments.dry_rock_mass_kg.size();
         ++index) {
        const int reason = step.unresolved_source_adjustments.process_reason_ids[
            index
        ];
        step.unresolved_source_mass_kg_by_reason[
            static_cast<std::size_t>(reason)
        ] += step.unresolved_source_adjustments.dry_rock_mass_kg[index];
    }
    for (std::size_t index = 0;
         index < step.unresolved_sink_adjustments.dry_rock_mass_kg.size();
         ++index) {
        const int reason = step.unresolved_sink_adjustments.process_reason_ids[
            index
        ];
        step.unresolved_sink_mass_kg_by_reason[
            static_cast<std::size_t>(reason)
        ] += step.unresolved_sink_adjustments.dry_rock_mass_kg[index];
    }

    step.opening_packet_count = static_cast<int>(
        step.opening_packets.dry_rock_mass_kg.size()
    );
    step.transported_packet_count = static_cast<int>(
        step.transported_packets.dry_rock_mass_kg.size()
    );
    step.closing_packet_count = static_cast<int>(
        step.closing_packets.dry_rock_mass_kg.size()
    );
    step.unresolved_source_adjustment_count = static_cast<int>(
        step.unresolved_source_adjustments.dry_rock_mass_kg.size()
    );
    step.unresolved_sink_adjustment_count = static_cast<int>(
        step.unresolved_sink_adjustments.dry_rock_mass_kg.size()
    );

    const std::size_t arithmetic_terms =
        step.opening_packets.dry_rock_mass_kg.size() +
        step.transported_packets.dry_rock_mass_kg.size() +
        step.closing_packets.dry_rock_mass_kg.size() +
        step.unresolved_source_adjustments.dry_rock_mass_kg.size() +
        step.unresolved_sink_adjustments.dry_rock_mass_kg.size() +
        transport_plan.overlap_area_km2.size() + cells.size();
    const long double transport_bound = forward_error_bound(
        std::abs(opening_mass) + std::abs(transported_mass),
        arithmetic_terms
    );
    if (
        std::abs(transported_mass - opening_mass) > transport_bound
    ) {
        throw std::runtime_error(
            "crust material shadow source-to-transport residual is excessive"
        );
    }
    const long double adjustment_bound = forward_error_bound(
        std::abs(closing_mass) + std::abs(transported_mass) +
            std::abs(source_mass) + std::abs(sink_mass),
        arithmetic_terms
    );
    if (
        std::abs(adjustment_residual) > adjustment_bound ||
        max_abs_cell_adjustment_residual > adjustment_bound
    ) {
        throw std::runtime_error(
            "crust material shadow ordered adjustments have excessive residual"
        );
    }

    long double source_reason_total = 0.0L;
    long double sink_reason_total = 0.0L;
    for (int reason = 0; reason < CRUST_PROCESS_REASON_COUNT; ++reason) {
        source_reason_total += step.unresolved_source_mass_kg_by_reason[
            static_cast<std::size_t>(reason)
        ];
        sink_reason_total += step.unresolved_sink_mass_kg_by_reason[
            static_cast<std::size_t>(reason)
        ];
    }
    if (
        std::abs(source_reason_total - source_mass) > adjustment_bound ||
        std::abs(sink_reason_total - sink_mass) > adjustment_bound
    ) {
        throw std::runtime_error(
            "crust material shadow per-reason adjustments did not reconcile"
        );
    }

    const long double scalar_mirror_bound =
        prior_max_cell_residual * static_cast<long double>(cells.size()) +
        4.0L * geometry_relative_error * (1.0L + scalar_absolute_terms) +
        forward_error_bound(scalar_absolute_terms, arithmetic_terms);
    if (
        std::abs(closing_mass - scalar_closing_mass) >
            scalar_mirror_bound ||
        max_abs_cell_scalar_residual > scalar_mirror_bound
    ) {
        throw std::runtime_error(
            "crust material shadow scalar mirror residual is excessive"
        );
    }

    state.history.push_back(std::move(step));
    state.pending_step = CrustMaterialShadowStep{};
    state.step_open = false;
    state.unresolved_source_adjustments_by_cell.assign(cells.size(), {});
    state.unresolved_sink_adjustments_by_cell.assign(cells.size(), {});
}

}  // namespace magic_geo::detail
